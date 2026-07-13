from __future__ import annotations

import json
from typing import Any

from ..llm_gateway import LLMGateway, LLMGatewayError
from ..schemas import GraphState, LLMTestGenerationAgentResult, ProjectInput, Status
from ..tools import has_test_files
from .llm_test_generation import generate_llm_tests


def run_llm_test_generation_agent(state: GraphState, gateway: LLMGateway | None = None) -> GraphState:
    try:
        project = ProjectInput.from_dict(state["project"])
        result = generate_result(project, gateway=gateway)
        return {
            **state,
            "run_id": project.run_id,
            "generated_test_result": result.to_dict(),
        }
    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"LLMTestGenerationAgent failed: {exc}")
        return {
            **state,
            "errors": errors,
            "generated_test_result": LLMTestGenerationAgentResult(
                agent="LLMTestGenerationAgent",
                status=Status.FAILED,
                attempted=False,
                generated=False,
                warnings=[str(exc)],
            ).to_dict(),
        }


def generate_result(
    project: ProjectInput,
    gateway: LLMGateway | None = None,
) -> LLMTestGenerationAgentResult:
    if has_configured_test_command(project.config):
        return skipped_result("test_command provided; LLM test generation skipped.", attempted=False)
    if has_test_files(project.files):
        return skipped_result("User tests detected; LLM test generation skipped.", attempted=False)
    if not project.config.get("llm_generated_tests_enabled", False):
        return skipped_result("llm_generated_tests_enabled disabled by project config.", attempted=False)

    try:
        generated = generate_llm_tests(project, gateway=gateway)
    except (LLMGatewayError, ValueError, json.JSONDecodeError) as exc:
        return skipped_result(f"LLM generated tests skipped: {exc}", attempted=True)

    return LLMTestGenerationAgentResult(
        agent="LLMTestGenerationAgent",
        status=Status.COMPLETED,
        attempted=True,
        generated=True,
        confidence=generated.confidence,
        inferred_behavior=generated.inferred_behavior,
        test_files=generated.test_files,
        warnings=generated.warnings,
    )


def skipped_result(warning: str, attempted: bool) -> LLMTestGenerationAgentResult:
    return LLMTestGenerationAgentResult(
        agent="LLMTestGenerationAgent",
        status=Status.SKIPPED,
        attempted=attempted,
        generated=False,
        warnings=[warning],
    )


def has_configured_test_command(config: dict[str, Any]) -> bool:
    configured = config.get("test_command")
    if isinstance(configured, str):
        return bool(configured.strip())
    if isinstance(configured, list):
        return bool(configured)
    return False
