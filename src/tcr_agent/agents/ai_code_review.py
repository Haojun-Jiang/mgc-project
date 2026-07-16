from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..llm_gateway import LLMGateway, LLMGatewayConfig, LLMGatewayError, build_llm_gateway
from ..schemas import ComplianceIssue, ComplianceResult, LLMMessage, LLMRequest, ProjectInput, Severity, Status, parse_optional_int, parse_severity

DEFAULT_MAX_CHARS = 40000
DEFAULT_MAX_TOKENS = 8192
PROMPT_PATH = Path(__file__).resolve().parents[1] / "templates" / "ai_code_review_system.md"


def run_ai_code_review(project: ProjectInput, gateway: LLMGateway | None = None) -> ComplianceResult:
    if not project.config.get("ai_code_review_enabled", False):
        return ComplianceResult(tool="llm_review", status=Status.SKIPPED)

    try:
        response = call_llm_review(project, gateway)
        parsed = extract_json_object(response)
        issues = parse_review_issues(parsed)
    except (LLMGatewayError, ValueError, json.JSONDecodeError) as exc:
        return ComplianceResult(
            tool="llm_review",
            status=Status.SKIPPED,
            warnings=[f"LLM code review skipped: {exc}"],
        )

    return ComplianceResult(
        tool="llm_review",
        status=review_status(issues),
        issues=issues,
    )


def call_llm_review(project: ProjectInput, gateway: LLMGateway | None) -> str:
    config = LLMGatewayConfig.from_env()
    active_gateway = gateway or build_llm_gateway(config)
    response = active_gateway.chat(
        LLMRequest(
            model=config.default_model,
            messages=[
                LLMMessage(role="system", content=load_prompt()),
                LLMMessage(role="user", content=json.dumps(build_review_payload(project), ensure_ascii=False)),
            ],
            max_tokens=int(project.config.get("ai_code_review_max_tokens", DEFAULT_MAX_TOKENS)),
            temperature=float(project.config.get("ai_code_review_temperature", 0)),
        )
    )
    if not response.content.strip():
        raise ValueError("LLM returned empty code review content")
    return response.content


def build_review_payload(project: ProjectInput) -> dict[str, Any]:
    max_chars = int(project.config.get("ai_code_review_max_chars", DEFAULT_MAX_CHARS))
    files = []
    remaining = max_chars
    truncated = False

    for item in project.files:
        content = item.content
        if remaining <= 0:
            truncated = True
            break
        if len(content) > remaining:
            content = content[:remaining]
            truncated = True
        remaining -= len(content)
        files.append(
            {
                "path": item.path,
                "language": item.language,
                "content": content,
            }
        )

    return {
        "run_id": project.run_id,
        "language": project.language,
        "truncated": truncated,
        "files": files,
    }


def parse_review_issues(data: dict[str, Any]) -> list[ComplianceIssue]:
    issues = []
    for item in data.get("issues", []):
        if not isinstance(item, dict):
            continue
        severity = parse_severity(item.get("severity"))
        category = normalize_category(item.get("category"))
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        issues.append(
            ComplianceIssue(
                rule_id=f"llm_review:{category}",
                file=str(item.get("file") or ""),
                line=parse_optional_int(item.get("line")),
                line_end=parse_optional_int(item.get("line_end")),
                message=message,
                severity=severity,
                category=category,
                confidence=parse_confidence(item.get("confidence")),
                evidence=str(item.get("evidence") or ""),
                root_cause=str(item.get("root_cause") or ""),
                recommendation=str(item.get("recommendation") or ""),
            )
        )
    return issues


def review_status(issues: list[ComplianceIssue]) -> Status:
    if any(item.severity in {Severity.CRITICAL, Severity.HIGH} for item in issues):
        return Status.FAILED
    return Status.COMPLETED


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
        raise ValueError("LLM code review must be a JSON object")
    return parsed


def normalize_category(raw: Any) -> str:
    value = str(raw or "other").lower()
    allowed = {"bug", "security", "performance", "maintainability", "test", "style", "other"}
    return value if value in allowed else "other"


def parse_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, value))


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")
