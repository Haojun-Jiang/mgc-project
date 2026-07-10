from __future__ import annotations

import importlib.util
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from .schemas import (
    CodeFile,
    CommandResult,
    ComplianceIssue,
    ComplianceResult,
    ProjectInput,
    Severity,
    Status,
    TestFailure,
    TestSummary,
)

MAX_OUTPUT_CHARS = 12000


def safe_relative_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe file path: {path}")
    return candidate


def write_project_to_workspace(project: ProjectInput) -> Path:
    workspace = Path(tempfile.mkdtemp(prefix=f"tcr_{project.run_id}_"))
    for code_file in project.files:
        write_code_file(workspace, code_file)
    return workspace


def write_code_file(workspace: Path, code_file: CodeFile) -> None:
    rel_path = safe_relative_path(code_file.path)
    target = workspace / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code_file.content, encoding="utf-8")


def run_command(tool_name: str, command: list[str], cwd: Path, timeout_seconds: int = 30) -> CommandResult:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        status = Status.PASSED if completed.returncode == 0 else Status.FAILED
        return CommandResult(
            tool_name=tool_name,
            command=command,
            cwd=str(cwd),
            status=status,
            exit_code=completed.returncode,
            duration_ms=int((time.monotonic() - start) * 1000),
            stdout=truncate(completed.stdout),
            stderr=truncate(completed.stderr),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            tool_name=tool_name,
            command=command,
            cwd=str(cwd),
            status=Status.FAILED,
            exit_code=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            stdout=truncate(exc.stdout or ""),
            stderr=truncate(exc.stderr or ""),
            error=f"command timed out after {timeout_seconds}s",
        )
    except OSError as exc:
        return CommandResult(
            tool_name=tool_name,
            command=command,
            cwd=str(cwd),
            status=Status.FAILED,
            exit_code=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=str(exc),
        )


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def run_python_tests(project: ProjectInput, workspace: Path) -> TestSummary:
    command = resolve_test_command(project)
    result = run_command("run_tests", command, workspace, int(project.config.get("test_timeout_seconds", 30)))
    summary = parse_test_output(result, command)
    summary.command_result = result
    return summary


def resolve_test_command(project: ProjectInput) -> list[str]:
    configured = project.config.get("test_command")
    if isinstance(configured, str) and configured.strip():
        return shlex.split(configured)
    if isinstance(configured, list) and configured:
        return [str(item) for item in configured]

    if has_test_files(project.files):
        if importlib.util.find_spec("pytest") is not None:
            return ["python3", "-m", "pytest", "-q"]
        return ["python3", "-m", "unittest", "discover", "-v"]

    python_files = [item.path for item in project.files if item.language == "python" or item.path.endswith(".py")]
    return ["python3", "-m", "py_compile", *python_files]


def has_test_files(files: list[CodeFile]) -> bool:
    for item in files:
        name = Path(item.path).name
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
    return False


def parse_test_output(result: CommandResult, command: list[str]) -> TestSummary:
    output = "\n".join(part for part in [result.stdout, result.stderr, result.error] if part)
    tool = "pytest" if "pytest" in command else "unittest" if "unittest" in command else "py_compile"
    status = Status.PASSED if result.status == Status.PASSED else Status.FAILED
    passed, failed = parse_counts(output)
    total = passed + failed
    failures = [] if status == Status.PASSED else [make_failure(output)]
    if total == 0:
        total = 1 if tool == "py_compile" else len(failures)
        failed = 0 if status == Status.PASSED else max(1, len(failures))
        passed = total - failed if status == Status.PASSED else 0
    return TestSummary(
        tool=tool,
        command=command,
        status=status,
        total=total,
        passed=passed,
        failed=failed,
        failures=failures,
    )


def parse_counts(output: str) -> tuple[int, int]:
    passed = 0
    failed = 0
    for count, word in re.findall(r"(\d+)\s+(passed|failed|errors?|skipped)", output):
        value = int(count)
        if word == "passed":
            passed += value
        elif word.startswith("failed") or word.startswith("error"):
            failed += value
    unittest_match = re.search(r"FAILED\s+\((?:failures=(\d+))?(?:,\s*)?(?:errors=(\d+))?\)", output)
    if unittest_match:
        failed += sum(int(item) for item in unittest_match.groups() if item)
    ok_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    if ok_match and "OK" in output:
        passed = int(ok_match.group(1))
    return passed, failed


def make_failure(output: str) -> TestFailure:
    lines = [line for line in output.splitlines() if line.strip()]
    message = lines[-1] if lines else "test command failed"
    return TestFailure(
        test_id="unknown",
        message=message,
        traceback=truncate(output),
    )


def run_python_compliance(project: ProjectInput, workspace: Path) -> list[ComplianceResult]:
    requested = project.config.get("lint_tools", ["py_compile"])
    results: list[ComplianceResult] = []
    for tool in requested:
        tool_name = str(tool)
        if tool_name == "py_compile":
            results.append(run_py_compile(project, workspace))
        elif tool_name in {"ruff", "semgrep"}:
            results.append(skip_unavailable_tool(tool_name))
        else:
            results.append(
                ComplianceResult(
                    tool=tool_name,
                    status=Status.SKIPPED,
                    issues=[
                        ComplianceIssue(
                            rule_id="unsupported_tool",
                            file="",
                            line=None,
                            message=f"Unsupported compliance tool: {tool_name}",
                            severity=Severity.INFO,
                        )
                    ],
                )
            )
    return results


def run_py_compile(project: ProjectInput, workspace: Path) -> ComplianceResult:
    python_files = [item.path for item in project.files if item.language == "python" or item.path.endswith(".py")]
    if not python_files:
        return ComplianceResult(tool="py_compile", status=Status.SKIPPED)
    result = run_command("run_compliance", ["python3", "-m", "py_compile", *python_files], workspace)
    issue = None
    if result.status == Status.FAILED:
        issue = ComplianceIssue(
            rule_id="python_compile_error",
            file="",
            line=None,
            message=result.stderr or result.stdout or result.error,
            severity=Severity.HIGH,
        )
    return ComplianceResult(
        tool="py_compile",
        status=result.status,
        issues=[issue] if issue else [],
        command_result=result,
    )


def skip_unavailable_tool(tool_name: str) -> ComplianceResult:
    return ComplianceResult(
        tool=tool_name,
        status=Status.SKIPPED,
        issues=[
            ComplianceIssue(
                rule_id="tool_not_configured",
                file="",
                line=None,
                message=f"{tool_name} integration is declared but not implemented in the MVP.",
                severity=Severity.INFO,
            )
        ],
    )
