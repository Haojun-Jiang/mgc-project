from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

from ..llm_gateway import LLMGateway, LLMGatewayConfig, LLMGatewayError, build_llm_gateway
from ..schemas import (
    FixAgentResult,
    FixPatch,
    GraphState,
    LLMMessage,
    LLMRequest,
    ProjectInput,
    ReportIssue,
    Severity,
    Status,
    parse_severity,
)
from ..tools import safe_relative_path

DEFAULT_TARGET_SEVERITIES = {Severity.CRITICAL, Severity.HIGH}
DEFAULT_MAX_CHARS = 40000
DEFAULT_MAX_ISSUES = 3
DEFAULT_MAX_TOKENS = 8192
PROMPT_PATH = Path(__file__).resolve().parents[1] / "templates" / "fix_agent_system.md"


def run_fix_agent(state: GraphState, gateway: LLMGateway | None = None) -> GraphState:
    try:
        project = ProjectInput.from_dict(state["project"])
        result = generate_fix(
            project=project,
            test_result=state.get("test_result", {}),
            report_result=state.get("report_result", {}),
            gateway=gateway,
        )
        return {
            **state,
            "fix_result": result.to_dict(),
        }
    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"FixAgent failed: {exc}")
        return {
            **state,
            "errors": errors,
            "fix_result": FixAgentResult(
                agent="FixAgent",
                status=Status.FAILED,
                llm_used=False,
                applied=False,
                workspace_dir=str(state.get("test_result", {}).get("workspace_dir", "")),
                target_issue_ids=[],
                warnings=[str(exc)],
            ).to_dict(),
        }


def generate_fix(
    project: ProjectInput,
    test_result: dict[str, Any],
    report_result: dict[str, Any],
    gateway: LLMGateway | None = None,
) -> FixAgentResult:
    workspace_dir = str(test_result.get("workspace_dir") or "")
    if not project.config.get("auto_fix", False):
        return skipped_result(workspace_dir, "auto_fix disabled by project config.")

    if not report_result.get("should_fix", False):
        return skipped_result(workspace_dir, "ReportAgent did not request fixes.")

    if not workspace_dir:
        return skipped_result(workspace_dir, "workspace_dir is missing from TestAgent result.")

    workspace = Path(workspace_dir)
    if not workspace.exists():
        return skipped_result(workspace_dir, f"workspace_dir does not exist: {workspace_dir}")

    allowed_paths = normalize_project_paths(project)
    target_issues, warnings = select_target_issues(project, report_result, allowed_paths)
    target_issue_ids = [issue.issue_id for issue in target_issues]
    if not target_issues:
        return FixAgentResult(
            agent="FixAgent",
            status=Status.SKIPPED,
            llm_used=False,
            applied=False,
            workspace_dir=workspace_dir,
            target_issue_ids=[],
            warnings=warnings or ["No fixable issues matched FixAgent severity/path filters."],
        )

    try:
        response = call_llm_for_fix(project, workspace, test_result, report_result, target_issues, gateway)
        parsed = extract_json_object(response)
    except (LLMGatewayError, ValueError, json.JSONDecodeError) as exc:
        return FixAgentResult(
            agent="FixAgent",
            status=Status.FAILED,
            llm_used=True,
            applied=False,
            workspace_dir=workspace_dir,
            target_issue_ids=target_issue_ids,
            warnings=[*warnings, f"LLM fix generation failed: {exc}"],
        )

    fix_plan, patches, apply_warnings = apply_fix_response(project, workspace, target_issues, parsed)
    applied = any(patch.applied for patch in patches)
    all_warnings = [*warnings, *apply_warnings]
    if not applied:
        all_warnings.append("FixAgent produced no applied changes.")

    return FixAgentResult(
        agent="FixAgent",
        status=Status.COMPLETED if applied else Status.FAILED,
        llm_used=True,
        applied=applied,
        workspace_dir=workspace_dir,
        target_issue_ids=target_issue_ids,
        fix_plan=fix_plan,
        patches=patches,
        warnings=all_warnings,
    )


def skipped_result(workspace_dir: str, warning: str) -> FixAgentResult:
    return FixAgentResult(
        agent="FixAgent",
        status=Status.SKIPPED,
        llm_used=False,
        applied=False,
        workspace_dir=workspace_dir,
        target_issue_ids=[],
        warnings=[warning],
    )


def select_target_issues(
    project: ProjectInput,
    report_result: dict[str, Any],
    allowed_paths: dict[str, str],
) -> tuple[list[ReportIssue], list[str]]:
    severities = configured_target_severities(project.config.get("fix_target_severities"))
    max_issues = max(1, int(project.config.get("fix_max_issues", DEFAULT_MAX_ISSUES)))
    selected: list[ReportIssue] = []
    warnings: list[str] = []

    for raw_issue in report_result.get("issues", []):
        if not isinstance(raw_issue, dict):
            continue
        issue = ReportIssue.from_dict(raw_issue)
        if issue.severity not in severities:
            continue
        if issue.file and not issue_file_is_allowed(issue, allowed_paths, warnings):
            continue
        selected.append(issue)
        if len(selected) >= max_issues:
            break

    return selected, warnings


def configured_target_severities(raw: Any) -> set[Severity]:
    if raw is None:
        return set(DEFAULT_TARGET_SEVERITIES)
    values = [raw] if isinstance(raw, str) else raw
    severities = {parse_severity(item) for item in values if str(item or "").strip()}
    severities.discard(Severity.INFO)
    return severities or set(DEFAULT_TARGET_SEVERITIES)


def issue_file_is_allowed(issue: ReportIssue, allowed_paths: dict[str, str], warnings: list[str]) -> bool:
    try:
        normalized = safe_relative_path(issue.file).as_posix()
    except ValueError as exc:
        warnings.append(f"Skipped issue {issue.issue_id}: unsafe issue file path: {exc}")
        return False
    if normalized not in allowed_paths:
        warnings.append(f"Skipped issue {issue.issue_id}: issue file is not part of project input: {issue.file}")
        return False
    return True


def call_llm_for_fix(
    project: ProjectInput,
    workspace: Path,
    test_result: dict[str, Any],
    report_result: dict[str, Any],
    target_issues: list[ReportIssue],
    gateway: LLMGateway | None,
) -> str:
    config = LLMGatewayConfig.from_env()
    active_gateway = gateway or build_llm_gateway(config)
    response = active_gateway.chat(
        LLMRequest(
            model=config.default_model,
            messages=[
                LLMMessage(role="system", content=load_prompt()),
                LLMMessage(
                    role="user",
                    content=json.dumps(
                        build_fix_payload(project, workspace, test_result, report_result, target_issues),
                        ensure_ascii=False,
                    ),
                ),
            ],
            max_tokens=int(project.config.get("fix_max_tokens", DEFAULT_MAX_TOKENS)),
            temperature=float(project.config.get("fix_temperature", 0)),
        )
    )
    if not response.content.strip():
        raise ValueError("LLM returned empty fix content")
    return response.content


def build_fix_payload(
    project: ProjectInput,
    workspace: Path,
    test_result: dict[str, Any],
    report_result: dict[str, Any],
    target_issues: list[ReportIssue],
) -> dict[str, Any]:
    max_chars = int(project.config.get("fix_max_chars", DEFAULT_MAX_CHARS))
    files: list[dict[str, Any]] = []
    remaining = max_chars
    truncated = False

    for item in project.files:
        if remaining <= 0:
            truncated = True
            break
        rel_path = safe_relative_path(item.path)
        path = workspace / rel_path
        content = path.read_text(encoding="utf-8") if path.exists() else item.content
        if len(content) > remaining:
            content = content[:remaining]
            truncated = True
        remaining -= len(content)
        files.append(
            {
                "path": rel_path.as_posix(),
                "language": item.language,
                "content": content,
            }
        )

    return {
        "run_id": project.run_id,
        "language": project.language,
        "truncated": truncated,
        "target_issues": [issue.to_dict() for issue in target_issues],
        "report": {
            "summary": report_result.get("summary", ""),
            "risk_level": report_result.get("risk_level", ""),
            "should_fix": report_result.get("should_fix", False),
        },
        "test_result": trim_json(test_result),
        "files": files,
    }


def apply_fix_response(
    project: ProjectInput,
    workspace: Path,
    target_issues: list[ReportIssue],
    data: dict[str, Any],
) -> tuple[str, list[FixPatch], list[str]]:
    fix_plan = str(data.get("fix_plan") or "")
    warnings = parse_warnings(data.get("warnings"))
    raw_files = data.get("files")
    if not isinstance(raw_files, list):
        return fix_plan, [], [*warnings, "LLM fix response field `files` must be a list."]

    allowed_paths = normalize_project_paths(project)
    target_by_id = {issue.issue_id: issue for issue in target_issues}
    patches: list[FixPatch] = []

    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            warnings.append("Skipped malformed file fix item.")
            continue
        patches.append(apply_one_file_fix(workspace, allowed_paths, target_by_id, raw_file))

    return fix_plan, patches, warnings


def apply_one_file_fix(
    workspace: Path,
    allowed_paths: dict[str, str],
    target_by_id: dict[str, ReportIssue],
    raw_file: dict[str, Any],
) -> FixPatch:
    file_path = str(raw_file.get("file") or "")
    issue_ids = parse_issue_ids(raw_file.get("issue_ids"))
    patch = FixPatch(file=file_path, issue_ids=issue_ids, change_type="modify")

    try:
        normalized = safe_relative_path(file_path).as_posix()
    except ValueError as exc:
        patch.error = f"unsafe file path: {exc}"
        return patch

    patch.file = normalized
    if normalized not in allowed_paths:
        patch.error = f"file is not part of project input: {normalized}"
        return patch
    if not issue_ids:
        patch.error = "issue_ids must contain at least one target issue id"
        return patch
    unknown_issue_ids = [issue_id for issue_id in issue_ids if issue_id not in target_by_id]
    if unknown_issue_ids:
        patch.error = f"unknown target issue ids: {', '.join(unknown_issue_ids)}"
        return patch
    if is_test_file(normalized) and not issue_ids_point_to_file(issue_ids, normalized, target_by_id):
        patch.error = "test files can only be modified when a target issue explicitly points to that test file"
        return patch

    content = parse_file_content(raw_file)
    if not isinstance(content, str):
        patch.error = "content must be a string"
        return patch

    target = workspace / safe_relative_path(normalized)
    if not target.exists():
        patch.error = f"target file does not exist in workspace: {normalized}"
        return patch

    old_content = target.read_text(encoding="utf-8")
    patch.diff = make_unified_diff(normalized, old_content, content)
    if not patch.diff:
        patch.error = "no changes produced for target file"
        return patch

    target.write_text(content, encoding="utf-8")
    patch.applied = True
    return patch


def normalize_project_paths(project: ProjectInput) -> dict[str, str]:
    paths = {}
    for item in project.files:
        normalized = safe_relative_path(item.path).as_posix()
        paths[normalized] = item.path
    return paths


def parse_issue_ids(raw: Any) -> list[str]:
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, list):
        return []
    return [str(item) for item in values if str(item or "").strip()]


def parse_warnings(raw: Any) -> list[str]:
    if raw is None:
        return []
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, list):
        return [str(values)]
    return [str(item) for item in values if str(item or "").strip()]


def parse_file_content(raw_file: dict[str, Any]) -> str | None:
    lines = raw_file.get("content_lines")
    if isinstance(lines, list):
        return "\n".join(str(line) for line in lines) + "\n"
    content = raw_file.get("content")
    return content if isinstance(content, str) else None


def issue_ids_point_to_file(issue_ids: list[str], file_path: str, target_by_id: dict[str, ReportIssue]) -> bool:
    for issue_id in issue_ids:
        issue = target_by_id.get(issue_id)
        if issue and issue.file:
            try:
                if safe_relative_path(issue.file).as_posix() == file_path:
                    return True
            except ValueError:
                continue
    return False


def is_test_file(path: str) -> bool:
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py")


def make_unified_diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
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
        raise ValueError("LLM fix response must be a JSON object")
    return parsed


def trim_json(data: dict[str, Any], limit: int = 5000) -> dict[str, Any]:
    raw = json.dumps(data, ensure_ascii=False)
    if len(raw) <= limit:
        return data
    return {"truncated": True, "content": raw[:limit]}


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")
