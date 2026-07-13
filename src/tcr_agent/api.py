from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from .graph import run_graph
from .tools import safe_relative_path


app = FastAPI(title="TCR Agent API", version="0.1.0")

RUN_ID_PATTERN = re.compile(r"^run_[A-Za-z0-9_-]+$")
STATUS_FILE = "status.json"
RESULT_FILE = "result.json"
PATCH_FILE = "fix.patch"


@app.post("/runs")
async def create_run(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    requirement: str = Form(""),
    ai_review: bool = Form(True),
    llm_generate_tests: bool = Form(True),
    report_use_llm: bool = Form(True),
    auto_fix: bool = Form(True),
    fix_target_severities: str = Form("critical,high,medium"),
) -> dict[str, Any]:
    run_id = make_run_id()
    run_dir = run_dir_for(run_id)
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=False)

    code_files = []
    seen_paths: set[str] = set()
    for upload in files:
        path = normalize_upload_filename(upload.filename)
        if path in seen_paths:
            raise HTTPException(status_code=400, detail=f"duplicate file name: {path}")
        seen_paths.add(path)

        raw = await upload.read()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"file must be UTF-8 text: {path}") from exc

        (input_dir / path).write_text(content, encoding="utf-8")
        code_files.append({"path": path, "language": "python", "content": content})

    if not code_files:
        raise HTTPException(status_code=400, detail="at least one .py file is required")

    has_user_tests = any(is_test_file(item["path"]) for item in code_files)
    project = {
        "run_id": run_id,
        "language": "python",
        "files": code_files,
        "config": build_config(
            requirement=requirement,
            ai_review=ai_review,
            llm_generate_tests=llm_generate_tests and not has_user_tests,
            report_use_llm=report_use_llm,
            auto_fix=auto_fix,
            fix_target_severities=fix_target_severities,
        ),
    }
    write_json(run_dir / "project.json", project)
    write_status(run_dir, run_id, "queued")
    background_tasks.add_task(run_agent_job, run_id, project)

    return {
        "run_id": run_id,
        "status": "queued",
        "links": run_links(run_id),
    }


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run_dir = existing_run_dir(run_id)
    status = read_json(run_dir / STATUS_FILE)
    result = read_optional_json(run_dir / RESULT_FILE)
    return {
        "run_id": run_id,
        "status": status.get("status", "unknown"),
        "steps": build_steps(result),
        "summary": build_summary(status, result),
        "result": result,
        "links": run_links(run_id),
    }


@app.get("/runs/{run_id}/report")
def get_report(run_id: str) -> dict[str, Any]:
    result = ready_result(run_id)
    return result.get("report_result") or {}


@app.get("/runs/{run_id}/diff.patch")
def get_patch(run_id: str):
    run_dir = existing_run_dir(run_id)
    patch_path = run_dir / PATCH_FILE
    if not patch_path.exists():
        ready_result(run_id)
        patch_path.write_text("", encoding="utf-8")
    return PlainTextResponse(patch_path.read_text(encoding="utf-8"), media_type="text/x-diff")


@app.get("/runs/{run_id}/fixed-files")
def get_fixed_files(run_id: str) -> dict[str, Any]:
    run_dir = existing_run_dir(run_id)
    ready_result(run_id)
    fixed_dir = run_dir / "fixed_files"
    files = []
    if fixed_dir.exists():
        for path in sorted(item for item in fixed_dir.rglob("*") if item.is_file()):
            files.append(
                {
                    "path": path.relative_to(fixed_dir).as_posix(),
                    "content": path.read_text(encoding="utf-8"),
                }
            )
    return {"files": files}


@app.get("/runs/{run_id}/artifacts/{name}")
def get_artifact(run_id: str, name: str):
    run_dir = existing_run_dir(run_id)
    artifact = artifact_path(run_dir, name)
    if not artifact.exists() or not artifact.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(artifact), filename=artifact.name)


def run_agent_job(run_id: str, project: dict[str, Any]) -> None:
    run_dir = run_dir_for(run_id)
    write_status(run_dir, run_id, "running")
    try:
        result = run_graph(project)
        write_json(run_dir / RESULT_FILE, result)
        write_artifacts(run_dir, result)
        write_status(run_dir, run_id, "completed", result_ref=RESULT_FILE)
    except Exception as exc:
        write_status(run_dir, run_id, "failed", error=str(exc))


def build_config(
    requirement: str,
    ai_review: bool,
    llm_generate_tests: bool,
    report_use_llm: bool,
    auto_fix: bool,
    fix_target_severities: str,
) -> dict[str, Any]:
    severities = [item.strip() for item in fix_target_severities.split(",") if item.strip()]
    return {
        "lint_tools": ["py_compile"],
        "test_timeout_seconds": 30,
        "ai_code_review_enabled": bool(ai_review),
        "llm_generated_tests_enabled": bool(llm_generate_tests),
        "llm_generated_tests_max_cases": 5,
        "llm_generated_tests_max_chars": 12000,
        "llm_generated_tests_max_tokens": 2048,
        "llm_generated_tests_temperature": 0,
        "requirement": requirement or "",
        "report_use_llm": bool(report_use_llm),
        "auto_fix": bool(auto_fix),
        "fix_target_severities": severities or ["critical", "high", "medium"],
        "fix_max_issues": 3,
        "fix_max_chars": 12000,
        "fix_max_tokens": 2048,
        "fix_temperature": 0,
        "max_fix_rounds": 2,
    }


def write_artifacts(run_dir: Path, result: dict[str, Any]) -> None:
    patch_text = merged_patch_text(result)
    (run_dir / PATCH_FILE).write_text(patch_text, encoding="utf-8")
    copy_fixed_files(run_dir, result)


def merged_patch_text(result: dict[str, Any]) -> str:
    chunks = []
    for patch in result.get("fix_result", {}).get("patches", []):
        diff = str(patch.get("diff") or "")
        if diff:
            chunks.append(diff if diff.endswith("\n") else diff + "\n")
    return "\n".join(chunks)


def copy_fixed_files(run_dir: Path, result: dict[str, Any]) -> None:
    fix_result = result.get("fix_result", {})
    if not fix_result.get("applied"):
        return
    workspace = Path(str(fix_result.get("workspace_dir") or ""))
    if not workspace.exists():
        return
    fixed_dir = run_dir / "fixed_files"
    fixed_dir.mkdir(exist_ok=True)
    for patch in fix_result.get("patches", []):
        if not patch.get("applied"):
            continue
        try:
            rel_path = safe_relative_path(str(patch.get("file") or ""))
        except ValueError:
            continue
        source = workspace / rel_path
        if not source.exists() or not source.is_file():
            continue
        target = fixed_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def build_steps(result: dict[str, Any] | None) -> list[dict[str, str]]:
    if not result:
        return [
            {"agent": "LLMTestGenerationAgent", "status": "pending"},
            {"agent": "TestAgent", "status": "pending"},
            {"agent": "ReportAgent", "status": "pending"},
            {"agent": "FixAgent", "status": "pending"},
        ]
    return [
        {"agent": "LLMTestGenerationAgent", "status": str(result.get("generated_test_result", {}).get("status", "unknown"))},
        {"agent": "TestAgent", "status": str(result.get("test_result", {}).get("status", "unknown"))},
        {"agent": "ReportAgent", "status": str(result.get("report_result", {}).get("status", "unknown"))},
        {"agent": "FixAgent", "status": str(result.get("fix_result", {}).get("status", "unknown"))},
    ]


def build_summary(status: dict[str, Any], result: dict[str, Any] | None) -> str:
    if result:
        return str(result.get("report_result", {}).get("summary") or "")
    return str(status.get("error") or "")


def normalize_upload_filename(raw_filename: str | None) -> str:
    raw = str(raw_filename or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="file name is required")
    normalized = raw.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if normalized.startswith("/") or ".." in parts:
        raise HTTPException(status_code=400, detail=f"unsafe file name: {raw}")
    name = PurePosixPath(normalized).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="file name is required")
    if not name.endswith(".py"):
        raise HTTPException(status_code=400, detail=f"only .py files are supported: {name}")
    return name


def is_test_file(path: str) -> bool:
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py")


def artifact_path(run_dir: Path, name: str) -> Path:
    if name in {STATUS_FILE, RESULT_FILE, PATCH_FILE, "project.json"}:
        return run_dir / name
    safe_name = normalize_artifact_name(name)
    return run_dir / "fixed_files" / safe_name


def normalize_artifact_name(name: str) -> Path:
    try:
        return safe_relative_path(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unsafe artifact name: {name}") from exc


def ready_result(run_id: str) -> dict[str, Any]:
    run_dir = existing_run_dir(run_id)
    status = read_json(run_dir / STATUS_FILE)
    if status.get("status") in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="run is not complete")
    result = read_optional_json(run_dir / RESULT_FILE)
    if result is None:
        raise HTTPException(status_code=404, detail="result not found")
    return result


def run_links(run_id: str) -> dict[str, str]:
    return {
        "self": f"/runs/{run_id}",
        "report": f"/runs/{run_id}/report",
        "patch": f"/runs/{run_id}/diff.patch",
        "fixed_files": f"/runs/{run_id}/fixed-files",
    }


def existing_run_dir(run_id: str) -> Path:
    run_dir = run_dir_for(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run not found")
    return run_dir


def run_dir_for(run_id: str) -> Path:
    if not RUN_ID_PATTERN.match(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    return runs_root() / run_id


def runs_root() -> Path:
    return Path(os.getenv("TCR_RUNS_DIR", ".tcr_runs")).resolve()


def make_run_id() -> str:
    return f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def write_status(
    run_dir: Path,
    run_id: str,
    status: str,
    error: str = "",
    result_ref: str = "",
) -> None:
    existing = read_optional_json(run_dir / STATUS_FILE) or {}
    created_at = existing.get("created_at") or utc_now()
    write_json(
        run_dir / STATUS_FILE,
        {
            "run_id": run_id,
            "status": status,
            "created_at": created_at,
            "updated_at": utc_now(),
            "error": error,
            "result_ref": result_ref,
        },
    )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return read_json(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
