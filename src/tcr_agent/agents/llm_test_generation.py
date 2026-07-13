from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..llm_gateway import LLMGateway, LLMGatewayConfig, build_llm_gateway
from ..schemas import GeneratedTestFile, LLMMessage, LLMRequest, ProjectInput

DEFAULT_MAX_CHARS = 12000
DEFAULT_MAX_CASES = 5
DEFAULT_MAX_TOKENS = 2048
GENERATED_TEST_DIR = ".tcr_generated_tests"
DEFAULT_TEST_FILE = "test_generated_llm.py"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "templates" / "llm_test_generation_system.md"


@dataclass(slots=True)
class GeneratedTestResult:
    inferred_behavior: str = ""
    confidence: float = 0.0
    test_files: list[GeneratedTestFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def generate_llm_tests(
    project: ProjectInput,
    gateway: LLMGateway | None = None,
) -> GeneratedTestResult:
    config = LLMGatewayConfig.from_env()
    active_gateway = gateway or build_llm_gateway(config)
    response = active_gateway.chat(
        LLMRequest(
            model=config.default_model,
            messages=[
                LLMMessage(role="system", content=load_prompt()),
                LLMMessage(role="user", content=json.dumps(build_generation_payload(project), ensure_ascii=False)),
            ],
            max_tokens=int(project.config.get("llm_generated_tests_max_tokens", DEFAULT_MAX_TOKENS)),
            temperature=float(project.config.get("llm_generated_tests_temperature", 0)),
        )
    )
    if not response.content.strip():
        raise ValueError("LLM returned empty generated test content")

    data = extract_json_object(response.content)
    test_file = normalize_test_file(data.get("test_file") or DEFAULT_TEST_FILE)
    warnings = parse_warnings(data.get("warnings"))
    test_code = parse_code_content(data, "test_code", "test_code_lines").strip()
    if not test_code:
        detail = f": {'; '.join(warnings)}" if warnings else ""
        raise ValueError(f"LLM generated test_code is empty{detail}")

    return GeneratedTestResult(
        inferred_behavior=str(data.get("inferred_behavior") or ""),
        confidence=parse_confidence(data.get("confidence")),
        test_files=[GeneratedTestFile(path=test_file, content=test_code + "\n")],
        warnings=warnings,
    )


def build_generation_payload(project: ProjectInput) -> dict[str, Any]:
    max_chars = int(project.config.get("llm_generated_tests_max_chars", DEFAULT_MAX_CHARS))
    files = []
    remaining = max_chars
    truncated = False

    for item in project.files:
        if remaining <= 0:
            truncated = True
            break
        content = item.content
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
        "requirement": str(project.config.get("requirement") or ""),
        "max_cases": int(project.config.get("llm_generated_tests_max_cases", DEFAULT_MAX_CASES)),
        "truncated": truncated,
        "files": files,
    }


def normalize_test_file(raw: object) -> str:
    value = str(raw or DEFAULT_TEST_FILE).strip()
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.name != value:
        raise ValueError(f"unsafe generated test file path: {value}")
    if not value.startswith("test_") or not value.endswith(".py"):
        raise ValueError(f"generated test file must match test_*.py: {value}")
    return value


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
        raise ValueError("LLM generated tests response must be a JSON object")
    return parsed


def parse_confidence(raw: object) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, value))


def parse_warnings(raw: object) -> list[str]:
    if raw is None:
        return []
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, list):
        return [str(values)]
    return [str(item) for item in values if str(item or "").strip()]


def parse_code_content(data: dict[str, Any], string_key: str, lines_key: str) -> str:
    lines = data.get(lines_key)
    if isinstance(lines, list):
        return "\n".join(str(line) for line in lines)
    return str(data.get(string_key) or "")


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")
