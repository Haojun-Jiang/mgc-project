from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Literal, TypedDict


class Status(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PASSED = "passed"
    SKIPPED = "skipped"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(slots=True)
class CodeFile:
    path: str
    content: str
    language: str = "python"
    sha256: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodeFile":
        return cls(
            path=str(data["path"]),
            content=str(data.get("content", "")),
            language=str(data.get("language", "python")),
            sha256=str(data.get("sha256", "")),
        )


@dataclass(slots=True)
class ProjectInput:
    run_id: str
    language: str
    files: list[CodeFile]
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectInput":
        files = [CodeFile.from_dict(item) for item in data.get("files", [])]
        if not files:
            raise ValueError("project.files must contain at least one file")
        return cls(
            run_id=str(data["run_id"]),
            language=str(data.get("language", "python")),
            files=files,
            config=dict(data.get("config", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CommandResult:
    tool_name: str
    command: list[str]
    cwd: str
    status: Status
    exit_code: int | None
    duration_ms: int
    stdout: str = ""
    stderr: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(slots=True)
class TestFailure:
    test_id: str
    file: str = ""
    line: int | None = None
    message: str = ""
    traceback: str = ""
    related_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TestSummary:
    tool: str
    command: list[str]
    status: Status
    total: int = 0
    passed: int = 0
    failed: int = 0
    failures: list[TestFailure] = field(default_factory=list)
    command_result: CommandResult | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["failures"] = [item.to_dict() for item in self.failures]
        data["command_result"] = self.command_result.to_dict() if self.command_result else None
        return data


@dataclass(slots=True)
class ComplianceIssue:
    rule_id: str
    file: str
    line: int | None
    message: str
    severity: Severity = Severity.INFO

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


@dataclass(slots=True)
class ComplianceResult:
    tool: str
    status: Status
    issues: list[ComplianceIssue] = field(default_factory=list)
    command_result: CommandResult | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["issues"] = [item.to_dict() for item in self.issues]
        data["command_result"] = self.command_result.to_dict() if self.command_result else None
        return data


@dataclass(slots=True)
class TestAgentResult:
    agent: Literal["TestAgent"]
    status: Status
    test_results: list[TestSummary]
    compliance_results: list[ComplianceResult]
    raw_logs_ref: str = ""
    workspace_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status.value,
            "test_results": [item.to_dict() for item in self.test_results],
            "compliance_results": [item.to_dict() for item in self.compliance_results],
            "raw_logs_ref": self.raw_logs_ref,
            "workspace_dir": self.workspace_dir,
        }


@dataclass(slots=True)
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not self.tool_call_id:
            data.pop("tool_call_id")
        return data


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LLMRequest:
    model: str
    messages: list[LLMMessage]
    tools: list[dict[str, Any]] = field(default_factory=list)
    max_tokens: int = 4096

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [item.to_dict() for item in self.messages],
            "tools": self.tools,
            "max_tokens": self.max_tokens,
        }


@dataclass(slots=True)
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": [item.to_dict() for item in self.tool_calls],
            "raw": self.raw,
        }


class GraphState(TypedDict, total=False):
    run_id: str
    project: dict[str, Any]
    test_result: dict[str, Any]
    report_result: dict[str, Any]
    fix_result: dict[str, Any]
    verify_result: dict[str, Any]
    errors: list[str]
