from __future__ import annotations

from typing import Any


def function_tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


RUN_TESTS_TOOL = function_tool(
    "run_tests",
    "Run project tests in the sandbox and return a structured command result.",
    {
        "type": "object",
        "properties": {
            "command": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional command override, such as ['python', '-m', 'unittest', 'discover', '-v'].",
            }
        },
    },
)

RUN_COMPLIANCE_TOOL = function_tool(
    "run_compliance",
    "Run deterministic compliance checks such as py_compile, ruff, or semgrep.",
    {
        "type": "object",
        "properties": {
            "tools": {
                "type": "array",
                "items": {"type": "string", "enum": ["py_compile", "ruff", "semgrep"]},
                "description": "Compliance tools to run.",
            }
        },
    },
)

GENERATE_TESTS_TOOL = function_tool(
    "generate_tests",
    "Generate pytest tests from source code and an optional natural language requirement.",
    {
        "type": "object",
        "properties": {
            "requirement": {
                "type": "string",
                "description": "Optional natural language behavior requirement used as the test oracle hint.",
            },
            "max_cases": {
                "type": "integer",
                "description": "Maximum number of generated test cases.",
            },
        },
    },
)

APPLY_PATCH_TOOL = function_tool(
    "apply_patch",
    "Apply a unified diff patch to the sandbox workspace after validation.",
    {
        "type": "object",
        "properties": {
            "patches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "diff": {"type": "string"},
                        "issue_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["file", "diff"],
                },
            }
        },
        "required": ["patches"],
    },
)

TASK_DONE_TOOL = function_tool(
    "task_done",
    "Call this when the current agent task is complete.",
    {
        "type": "object",
        "properties": {
            "state": {"type": "string", "enum": ["DONE", "FAILED"]},
            "reason": {"type": "string"},
        },
        "required": ["state"],
    },
)

BASE_TOOL_DEFS = [
    RUN_TESTS_TOOL,
    RUN_COMPLIANCE_TOOL,
    GENERATE_TESTS_TOOL,
    APPLY_PATCH_TOOL,
    TASK_DONE_TOOL,
]
