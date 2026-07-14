from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..schemas import GraphState, ProjectInput, Status, VerifyAgentResult
from ..tools import run_python_compliance, run_python_tests
from .test_agent import resolve_status

DEFAULT_MAX_FIX_ROUNDS = 2


def run_verify_agent(state: GraphState) -> GraphState:
    try:
        project = ProjectInput.from_dict(state["project"])
        max_rounds = configured_max_fix_rounds(project, state)
        round_number = int(state.get("fix_round", 0)) + 1
        result = verify_fix(project, state, round_number, max_rounds)
        verify_dict = result.to_dict()
        return {
            **state,
            "test_result": verify_dict["test_result"],
            "verify_result": verify_dict,
            "fix_round": round_number,
            "max_fix_rounds": max_rounds,
            "test_history": append_history(state.get("test_history", []), state.get("test_result")),
            "report_history": append_history(state.get("report_history", []), state.get("report_result")),
            "fix_history": append_history(state.get("fix_history", []), state.get("fix_result")),
            "verify_history": append_history(state.get("verify_history", []), verify_dict),
        }
    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"VerifyAgent failed: {exc}")
        project = ProjectInput.from_dict(state["project"])
        max_rounds = configured_max_fix_rounds(project, state)
        round_number = int(state.get("fix_round", 0)) + 1
        verify_dict = VerifyAgentResult(
            agent="VerifyAgent",
            status=Status.FAILED,
            passed=False,
            round=round_number,
            max_rounds=max_rounds,
            workspace_dir=str(state.get("fix_result", {}).get("workspace_dir", "")),
            test_result={},
            warnings=[str(exc)],
        ).to_dict()
        return {
            **state,
            "errors": errors,
            "verify_result": verify_dict,
            "fix_round": round_number,
            "max_fix_rounds": max_rounds,
            "verify_history": append_history(state.get("verify_history", []), verify_dict),
        }


def verify_fix(
    project: ProjectInput,
    state: GraphState,
    round_number: int,
    max_rounds: int,
) -> VerifyAgentResult:
    fix_result = state.get("fix_result", {})
    workspace_dir = str(fix_result.get("workspace_dir") or "")
    if not fix_result.get("applied"):
        return skipped_result(round_number, max_rounds, workspace_dir, "FixAgent did not apply changes.")
    if not workspace_dir:
        return skipped_result(round_number, max_rounds, workspace_dir, "workspace_dir is missing from FixAgent result.")

    workspace = Path(workspace_dir)
    if not workspace.exists():
        return skipped_result(round_number, max_rounds, workspace_dir, f"workspace_dir does not exist: {workspace_dir}")

    clear_python_bytecode(workspace)
    test_summary = run_python_tests(project, workspace, state.get("generated_test_result"))
    compliance_results = run_python_compliance(project, workspace)
    status = resolve_status(test_summary.status, [item.status for item in compliance_results])
    raw_logs_ref = write_verify_logs(workspace, round_number, test_summary, compliance_results)
    test_result = {
        "agent": "VerifyAgent",
        "status": status.value,
        "test_results": [test_summary.to_dict()],
        "compliance_results": [item.to_dict() for item in compliance_results],
        "raw_logs_ref": raw_logs_ref,
        "workspace_dir": str(workspace),
    }
    passed = status == Status.PASSED
    return VerifyAgentResult(
        agent="VerifyAgent",
        status=Status.PASSED if passed else Status.FAILED,
        passed=passed,
        round=round_number,
        max_rounds=max_rounds,
        workspace_dir=str(workspace),
        test_result=test_result,
    )


def skipped_result(round_number: int, max_rounds: int, workspace_dir: str, warning: str) -> VerifyAgentResult:
    return VerifyAgentResult(
        agent="VerifyAgent",
        status=Status.SKIPPED,
        passed=False,
        round=round_number,
        max_rounds=max_rounds,
        workspace_dir=workspace_dir,
        test_result={},
        warnings=[warning],
    )


def configured_max_fix_rounds(project: ProjectInput, state: GraphState) -> int:
    raw = state.get("max_fix_rounds", project.config.get("max_fix_rounds", DEFAULT_MAX_FIX_ROUNDS))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_FIX_ROUNDS


def append_history(history: list[dict[str, Any]], item: Any) -> list[dict[str, Any]]:
    if not isinstance(item, dict) or not item:
        return list(history)
    return [*history, item]


def clear_python_bytecode(workspace: Path) -> None:
    for cache_dir in workspace.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
    for pyc_file in workspace.rglob("*.pyc"):
        if pyc_file.is_file():
            pyc_file.unlink()


def write_verify_logs(workspace: Path, round_number: int, test_summary, compliance_results) -> str:
    artifacts = workspace / ".tcr_artifacts"
    artifacts.mkdir(exist_ok=True)
    target = artifacts / f"verify_agent_round_{round_number}.txt"
    chunks = [f"# VerifyAgent round {round_number} logs\n"]
    if test_summary.command_result:
        chunks.append("## test command\n")
        chunks.append(" ".join(test_summary.command_result.command))
        chunks.append("\n\n## stdout\n")
        chunks.append(test_summary.command_result.stdout)
        chunks.append("\n\n## stderr\n")
        chunks.append(test_summary.command_result.stderr)
    if getattr(test_summary, "warnings", []):
        chunks.append("\n\n## test warnings\n")
        chunks.append("\n".join(f"WARNING: {warning}" for warning in test_summary.warnings))
    for item in compliance_results:
        chunks.append(f"\n\n## compliance: {item.tool}\n")
        if item.warnings:
            chunks.append("\n".join(f"WARNING: {warning}" for warning in item.warnings))
            chunks.append("\n")
        if item.issues:
            chunks.append("\nIssues:\n")
            for issue in item.issues:
                chunks.append(f"- [{issue.severity.value}] {issue.rule_id} {issue.file}:{issue.line} {issue.message}\n")
        if item.command_result:
            chunks.append(" ".join(item.command_result.command))
            chunks.append("\n\n## stdout\n")
            chunks.append(item.command_result.stdout)
            chunks.append("\n\n## stderr\n")
            chunks.append(item.command_result.stderr)
    target.write_text("".join(chunks), encoding="utf-8")
    return str(target)
