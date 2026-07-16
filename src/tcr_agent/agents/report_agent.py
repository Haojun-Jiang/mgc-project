from __future__ import annotations

import json
import re
from typing import Any

from ..llm_gateway import LLMGateway, LLMGatewayConfig, LLMGatewayError, build_llm_gateway
from ..schemas import (
    GraphState,
    LLMMessage,
    LLMRequest,
    ProjectInput,
    ReportAgentResult,
    ReportIssue,
    Severity,
    Status,
    parse_severity,
)

REPORT_SYSTEM_PROMPT = """你是测试-合规-纠正系统中的 ReportAgent。
你的任务是基于 TestAgent 的真实执行结果生成结构化报告。

要求：
1. 只基于输入中的测试/合规证据，不要编造文件或错误。
2. 输出必须是一个 JSON object，不要输出 Markdown 或解释性前后缀。
3. issues 中每个问题必须保留输入候选问题的 issue_id。
4. recommendation 要面向后续 FixAgent，可执行、具体、简洁。
5. 所有字符串字段必须是单行短文本，不要在 JSON 字符串中包含换行符。

JSON 结构：
{
  "summary": "一句话总结",
  "risk_level": "critical|high|medium|low|info",
  "should_fix": true,
  "issues": [
    {
      "issue_id": "ISSUE-001",
      "source": "unittest",
      "type": "logic_bug",
      "severity": "high",
      "confidence": 0.95,
      "file": "main.py",
      "line_start": 1,
      "line_end": 1,
      "evidence": "失败证据",
      "root_cause": "根因判断",
      "recommendation": "修复建议"
    }
  ]
}
"""


def run_report_agent(state: GraphState) -> GraphState:
    try:
        project = ProjectInput.from_dict(state["project"])
        test_result = state.get("test_result", {})
        report = generate_report(project, test_result)
        return {
            **state,
            "report_result": report.to_dict(),
        }
    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"ReportAgent failed: {exc}")
        return {
            **state,
            "errors": errors,
            "report_result": ReportAgentResult(
                agent="ReportAgent",
                status=Status.FAILED,
                summary=f"ReportAgent failed: {exc}",
                issues=[],
                warnings=[str(exc)],
            ).to_dict(),
        }


def generate_report(
    project: ProjectInput,
    test_result: dict[str, Any],
    gateway: LLMGateway | None = None,
) -> ReportAgentResult:
    candidate_issues = build_candidate_issues(test_result)
    if not candidate_issues:
        warnings = collect_test_warnings(test_result)
        summary = "测试和合规检查未发现需要修复的问题。"
        if has_static_only_test(test_result):
            summary = "未执行行为测试，仅完成静态/合规检查，未发现需要修复的问题。"
            warnings.append("No behavior tests were executed; result is static-only.")
        return ReportAgentResult(
            agent="ReportAgent",
            status=Status.COMPLETED,
            summary=summary,
            issues=[],
            risk_level=Severity.INFO,
            should_fix=False,
            warnings=warnings,
        )

    base_report = build_fallback_report(candidate_issues)
    if not project.config.get("report_use_llm", True):
        base_report.warnings.append("LLM report enhancement disabled by project config.")
        return base_report

    try:
        llm_report = call_llm_for_report(project, test_result, candidate_issues, gateway)
    except (LLMGatewayError, ValueError, json.JSONDecodeError) as exc:
        base_report.warnings.append(f"LLM report enhancement failed: {exc}")
        return base_report

    return merge_llm_report(base_report, llm_report)


def build_candidate_issues(test_result: dict[str, Any]) -> list[ReportIssue]:
    issues: list[ReportIssue] = []
    counter = 1

    for item in test_result.get("test_results", []):
        if item.get("status") != Status.FAILED.value:
            continue
        is_llm_generated = item.get("tool") == "llm_generated_tests" or item.get("test_mode") == "llm_generated_test"
        confidence = parse_confidence(item.get("confidence"), 0.85) if is_llm_generated else 0.85
        severity = Severity.HIGH
        issue_type = "test_failure"
        root_cause = "测试命令失败，需要结合失败堆栈定位代码逻辑或断言差异。"
        recommendation = "优先阅读失败用例和相关源码，修复导致测试失败的最小代码路径。"
        if is_llm_generated:
            severity = Severity.HIGH if confidence >= 0.8 else Severity.MEDIUM
            issue_type = "generated_test_failure"
            root_cause = "LLM 根据代码和可选需求推断出的行为测试未通过；该结论不是用户确认的验收标准。"
            recommendation = "检查源码是否符合 inferred_behavior；如果 LLM 推断不准确，应补充 requirement 或用户测试。"
        failures = item.get("failures") or [{}]
        for failure in failures:
            evidence = compact_text(failure.get("message") or failure.get("traceback") or "test failed")
            if is_llm_generated and item.get("inferred_behavior"):
                evidence = compact_text(f"{evidence}\nInferred behavior: {item.get('inferred_behavior')}")
            issues.append(
                ReportIssue(
                    issue_id=f"ISSUE-{counter:03d}",
                    source=str(item.get("tool", "test")),
                    type=issue_type,
                    severity=severity,
                    confidence=confidence,
                    file=str(failure.get("related_file") or failure.get("file") or ""),
                    line_start=failure.get("line"),
                    line_end=failure.get("line"),
                    evidence=evidence,
                    root_cause=root_cause,
                    recommendation=recommendation,
                )
            )
            counter += 1

    for item in test_result.get("compliance_results", []):
        for compliance_issue in item.get("issues", []):
            is_llm_review = item.get("tool") == "llm_review"
            if is_llm_review:
                if item.get("status") not in {Status.COMPLETED.value, Status.FAILED.value}:
                    continue
            elif item.get("status") not in {Status.FAILED.value, Status.SKIPPED.value}:
                continue
            severity = parse_severity(compliance_issue.get("severity"))
            category = str(compliance_issue.get("category") or "compliance")
            issues.append(
                ReportIssue(
                    issue_id=f"ISSUE-{counter:03d}",
                    source=str(item.get("tool", "compliance")),
                    type=category if is_llm_review else "compliance",
                    severity=severity,
                    confidence=float(compliance_issue.get("confidence") or (0.9 if item.get("status") == Status.FAILED.value else 0.4)),
                    file=str(compliance_issue.get("file", "")),
                    line_start=compliance_issue.get("line"),
                    line_end=compliance_issue.get("line_end") or compliance_issue.get("line"),
                    evidence=compact_text(compliance_issue.get("evidence") or compliance_issue.get("message", "")),
                    root_cause=str(
                        compliance_issue.get("root_cause")
                        or ("AI 代码审查报告了潜在问题。" if is_llm_review else "合规工具报告了代码质量、语法或工具配置问题。")
                    ),
                    recommendation=str(
                        compliance_issue.get("recommendation")
                        or ("根据 AI 审查建议检查并修复对应代码。" if is_llm_review else "根据合规工具的 rule_id 和 message 修改对应文件或调整项目配置。")
                    ),
                )
            )
            counter += 1

    return issues


def build_fallback_report(issues: list[ReportIssue]) -> ReportAgentResult:
    risk = highest_severity([item.severity for item in issues])
    failed_count = len([item for item in issues if item.severity in {Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM}])
    return ReportAgentResult(
        agent="ReportAgent",
        status=Status.COMPLETED,
        summary=f"发现 {len(issues)} 个问题，其中 {failed_count} 个需要优先处理。",
        issues=issues,
        risk_level=risk,
        should_fix=any(item.severity != Severity.INFO for item in issues),
        llm_used=False,
    )


def call_llm_for_report(
    project: ProjectInput,
    test_result: dict[str, Any],
    candidate_issues: list[ReportIssue],
    gateway: LLMGateway | None,
) -> dict[str, Any]:
    config = LLMGatewayConfig.from_env()
    active_gateway = gateway or build_llm_gateway(config)
    payload = {
        "project": {
            "run_id": project.run_id,
            "language": project.language,
            "file_paths": [item.path for item in project.files],
        },
        "candidate_issues": [item.to_dict() for item in candidate_issues],
        "test_agent_result": trim_for_prompt(test_result),
    }
    response = active_gateway.chat(
        LLMRequest(
            model=config.default_model,
            messages=[
                LLMMessage(role="system", content=REPORT_SYSTEM_PROMPT),
                LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
            ],
            max_tokens=int(project.config.get("report_max_tokens", 8192)),
            temperature=float(project.config.get("report_temperature", 0)),
        )
    )
    if not response.content.strip():
        raise ValueError("LLM returned empty report content")
    return extract_json_object(response.content)


def merge_llm_report(base_report: ReportAgentResult, data: dict[str, Any]) -> ReportAgentResult:
    candidate_by_id = {item.issue_id: item for item in base_report.issues}
    merged_issues: list[ReportIssue] = []
    for item in data.get("issues", []):
        issue_id = str(item.get("issue_id", ""))
        base_issue = candidate_by_id.get(issue_id)
        if base_issue is None:
            continue
        merged_issues.append(
            ReportIssue(
                issue_id=base_issue.issue_id,
                source=str(item.get("source") or base_issue.source),
                type=str(item.get("type") or base_issue.type),
                severity=parse_severity(item.get("severity") or base_issue.severity),
                confidence=float(item.get("confidence", base_issue.confidence)),
                file=str(item.get("file") or base_issue.file),
                line_start=item.get("line_start") if item.get("line_start") is not None else base_issue.line_start,
                line_end=item.get("line_end") if item.get("line_end") is not None else base_issue.line_end,
                evidence=str(item.get("evidence") or base_issue.evidence),
                root_cause=str(item.get("root_cause") or base_issue.root_cause),
                recommendation=str(item.get("recommendation") or base_issue.recommendation),
            )
        )

    if not merged_issues:
        merged_issues = base_report.issues

    risk = parse_severity(data.get("risk_level")) if data.get("risk_level") else highest_severity([item.severity for item in merged_issues])
    return ReportAgentResult(
        agent="ReportAgent",
        status=Status.COMPLETED,
        summary=str(data.get("summary") or base_report.summary),
        issues=merged_issues,
        risk_level=risk,
        should_fix=bool(data.get("should_fix", base_report.should_fix)),
        llm_used=True,
        warnings=base_report.warnings,
    )


def extract_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM report must be a JSON object")
    return parsed


def trim_for_prompt(data: dict[str, Any], limit: int = 9000) -> dict[str, Any]:
    raw = json.dumps(data, ensure_ascii=False)
    if len(raw) <= limit:
        return data
    return {"truncated": True, "content": raw[:limit]}


def compact_text(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def parse_confidence(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, value))


def collect_test_warnings(test_result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for item in test_result.get("test_results", []):
        warnings.extend(str(warning) for warning in item.get("warnings", []) if str(warning).strip())
    return warnings


def has_static_only_test(test_result: dict[str, Any]) -> bool:
    return any(item.get("test_mode") == "static_only" for item in test_result.get("test_results", []))


def highest_severity(severities: list[Severity]) -> Severity:
    rank = {
        Severity.CRITICAL: 5,
        Severity.HIGH: 4,
        Severity.MEDIUM: 3,
        Severity.LOW: 2,
        Severity.INFO: 1,
    }
    if not severities:
        return Severity.INFO
    return max(severities, key=lambda item: rank[item])
