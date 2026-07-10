from __future__ import annotations

from pathlib import Path

from ..schemas import GraphState, ProjectInput, Status, TestAgentResult
from ..tools import run_python_compliance, run_python_tests, write_project_to_workspace


def run_test_agent(state: GraphState) -> GraphState:
    try:
        project = ProjectInput.from_dict(state["project"])
        workspace = write_project_to_workspace(project)
        test_result = run_python_tests(project, workspace)
        compliance_results = run_python_compliance(project, workspace)

        status = resolve_status(test_result.status, [item.status for item in compliance_results])
        raw_logs_ref = write_raw_logs(workspace, test_result, compliance_results)
        agent_result = TestAgentResult(
            agent="TestAgent",
            status=status,
            test_results=[test_result],
            compliance_results=compliance_results,
            raw_logs_ref=raw_logs_ref,
            workspace_dir=str(workspace),
        )
        return {
            **state,
            "run_id": project.run_id,
            "test_result": agent_result.to_dict(),
        }
    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"TestAgent failed: {exc}")
        return {
            **state,
            "errors": errors,
            "test_result": {
                "agent": "TestAgent",
                "status": Status.FAILED.value,
                "test_results": [],
                "compliance_results": [],
            },
        }


def resolve_status(test_status: Status, compliance_statuses: list[Status]) -> Status:
    if test_status == Status.FAILED:
        return Status.FAILED
    if any(item == Status.FAILED for item in compliance_statuses):
        return Status.FAILED
    return Status.PASSED


def write_raw_logs(workspace: Path, test_result, compliance_results) -> str:
    artifacts = workspace / ".tcr_artifacts"
    artifacts.mkdir(exist_ok=True)
    target = artifacts / "test_agent_logs.txt"
    chunks = ["# TestAgent logs\n"]
    if test_result.command_result:
        chunks.append("## Test command\n")
        chunks.append(" ".join(test_result.command_result.command))
        chunks.append("\n\n## stdout\n")
        chunks.append(test_result.command_result.stdout)
        chunks.append("\n\n## stderr\n")
        chunks.append(test_result.command_result.stderr)
    for item in compliance_results:
        if item.command_result:
            chunks.append(f"\n\n## compliance: {item.tool}\n")
            chunks.append(" ".join(item.command_result.command))
            chunks.append("\n\n## stdout\n")
            chunks.append(item.command_result.stdout)
            chunks.append("\n\n## stderr\n")
            chunks.append(item.command_result.stderr)
    target.write_text("".join(chunks), encoding="utf-8")
    return str(target)
