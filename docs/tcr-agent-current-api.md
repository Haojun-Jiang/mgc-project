# TCR Agent 当前接口文档

版本日期：2026-07-13  
服务入口：`tcr_agent.api:app`  
实现文件：`src/tcr_agent/api.py`

本文档描述当前代码中已经实现的 FastAPI 接口，用于前端、后端或其他系统对接。

## 1. 服务说明

TCR Agent 服务用于接收 Python 源码文件，异步执行测试生成、测试检查、AI 代码审查、报告生成和自动修复，并提供报告与修复产物查询接口。

当前执行链路：

```text
POST /runs
  -> LLMTestGenerationAgent
  -> TestAgent
  -> ReportAgent
  -> FixAgent
  -> GET /runs/{run_id}
  -> GET /runs/{run_id}/report
  -> GET /runs/{run_id}/fixed-files
```

建议前端最小对接流程：

```text
上传文件 -> 创建任务 -> 轮询任务状态 -> 展示报告 -> 下载修复文件或 patch
```

## 2. 服务启动

```bash
.venv/bin/python -m uvicorn tcr_agent.api:app --host 127.0.0.1 --port 8010
```

默认 Base URL：

```text
http://127.0.0.1:8010
```

FastAPI 自动生成文档：

```text
http://127.0.0.1:8010/docs
http://127.0.0.1:8010/openapi.json
```

运行产物目录：

```text
.tcr_runs/{run_id}/
```

可通过环境变量覆盖：

```text
TCR_RUNS_DIR=/path/to/tcr-runs
```

LLM 网关环境变量：

```text
LLM_GATEWAY_BASE_URL=https://api.example.com
LLM_GATEWAY_API_KEY=your-api-key
LLM_GATEWAY_MODEL=model-name
LLM_GATEWAY_TIMEOUT_SECONDS=60
LLM_GATEWAY_AUTH_HEADER=authorization
LLM_GATEWAY_VERIFY_SSL=true
LLM_GATEWAY_EXTRA_HEADERS_JSON={}
```

## 3. 接口总览

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/runs` | 上传源码文件并创建异步任务。 |
| `GET` | `/runs/{run_id}` | 查询任务状态、步骤、摘要和完整结果。 |
| `GET` | `/runs/{run_id}/report` | 获取结构化报告。 |
| `GET` | `/runs/{run_id}/diff.patch` | 获取自动修复生成的 unified diff。 |
| `GET` | `/runs/{run_id}/fixed-files` | 获取修复后文件列表和内容。 |
| `GET` | `/runs/{run_id}/artifacts/{name}` | 下载指定产物或指定修复文件。 |

当前没有实现以下接口：

- `GET /health`
- `GET /runs/{run_id}/download`
- 直接下载 zip 的接口
- 用户鉴权接口

## 4. 创建任务

```http
POST /runs
Content-Type: multipart/form-data
```

### 4.1 请求字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|---|
| `files` | file[] | 是 | 无 | 上传一个或多个 `.py` 文件。 |
| `requirement` | string | 否 | `""` | 需求说明，会传入 LLM 测试生成、报告和修复阶段。 |
| `ai_review` | boolean | 否 | `true` | 是否启用 AI 代码审查。 |
| `llm_generate_tests` | boolean | 否 | `true` | 无用户测试文件时是否生成 LLM 测试。 |
| `report_use_llm` | boolean | 否 | `true` | 报告阶段是否启用 LLM 增强。 |
| `auto_fix` | boolean | 否 | `true` | 是否启用自动修复。 |
| `fix_target_severities` | string | 否 | `critical,high,medium` | 自动修复目标级别，逗号分隔。 |

### 4.2 上传文件限制

- 当前仅支持 Python 文件，即文件名必须以 `.py` 结尾。
- 文件内容必须是 UTF-8 文本。
- 文件名不能为空。
- 不允许绝对路径。
- 不允许路径中包含 `..`。
- 不允许重复文件名。
- 当前服务会取上传路径的 basename 保存，例如上传 `src/main.py`，服务内部保存为 `main.py`。
- 如果上传文件中包含 `test_xxx.py` 或 `xxx_test.py`，服务会认为用户已经提供测试文件，并自动关闭 LLM 测试生成。

### 4.3 请求示例

```bash
curl -X POST "http://127.0.0.1:8010/runs" \
  -F "files=@examples/python_no_tests/order_pricing.py" \
  -F "requirement=订单金额计算需求" \
  -F "ai_review=true" \
  -F "llm_generate_tests=true" \
  -F "report_use_llm=true" \
  -F "auto_fix=true" \
  -F "fix_target_severities=critical,high,medium"
```

### 4.4 成功响应

```json
{
  "run_id": "run_1720840000_ab12cd34",
  "status": "queued",
  "links": {
    "self": "/runs/run_1720840000_ab12cd34",
    "report": "/runs/run_1720840000_ab12cd34/report",
    "patch": "/runs/run_1720840000_ab12cd34/diff.patch",
    "fixed_files": "/runs/run_1720840000_ab12cd34/fixed-files"
  }
}
```

### 4.5 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | string | 任务 ID，后续查询都使用该值。 |
| `status` | string | 初始状态，固定为 `queued`。 |
| `links.self` | string | 状态查询接口。 |
| `links.report` | string | 报告查询接口。 |
| `links.patch` | string | patch 查询接口。 |
| `links.fixed_files` | string | 修复文件查询接口。 |

## 5. 查询任务状态

```http
GET /runs/{run_id}
```

### 5.1 请求示例

```bash
curl "http://127.0.0.1:8010/runs/run_1720840000_ab12cd34"
```

### 5.2 响应字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | string | 任务 ID。 |
| `status` | string | 任务状态：`queued`、`running`、`completed`、`failed`。 |
| `steps` | array | 各 Agent 步骤状态。 |
| `summary` | string | 报告摘要；失败时可能是错误信息。 |
| `result` | object/null | 完整执行结果，任务完成前通常为 `null`。 |
| `links` | object | 相关接口链接。 |

### 5.3 运行中响应示例

```json
{
  "run_id": "run_1720840000_ab12cd34",
  "status": "running",
  "steps": [
    {"agent": "LLMTestGenerationAgent", "status": "pending"},
    {"agent": "TestAgent", "status": "pending"},
    {"agent": "ReportAgent", "status": "pending"},
    {"agent": "FixAgent", "status": "pending"}
  ],
  "summary": "",
  "result": null,
  "links": {
    "self": "/runs/run_1720840000_ab12cd34",
    "report": "/runs/run_1720840000_ab12cd34/report",
    "patch": "/runs/run_1720840000_ab12cd34/diff.patch",
    "fixed_files": "/runs/run_1720840000_ab12cd34/fixed-files"
  }
}
```

### 5.4 完成响应示例

```json
{
  "run_id": "run_1720840000_ab12cd34",
  "status": "completed",
  "steps": [
    {"agent": "LLMTestGenerationAgent", "status": "skipped"},
    {"agent": "TestAgent", "status": "passed"},
    {"agent": "ReportAgent", "status": "completed"},
    {"agent": "FixAgent", "status": "completed"}
  ],
  "summary": "发现 1 个高风险问题，已生成修复建议。",
  "result": {
    "generated_test_result": {},
    "test_result": {},
    "report_result": {},
    "fix_result": {},
    "errors": []
  },
  "links": {
    "self": "/runs/run_1720840000_ab12cd34",
    "report": "/runs/run_1720840000_ab12cd34/report",
    "patch": "/runs/run_1720840000_ab12cd34/diff.patch",
    "fixed_files": "/runs/run_1720840000_ab12cd34/fixed-files"
  }
}
```

### 5.5 轮询建议

- 前端或调用方每 2 到 5 秒轮询一次。
- `queued` 或 `running`：继续轮询。
- `completed`：停止轮询，展示报告和下载入口。
- `failed`：停止轮询，展示 `summary` 或错误信息。

## 6. 获取结构化报告

```http
GET /runs/{run_id}/report
```

该接口要求任务已经结束。如果任务仍在 `queued` 或 `running`，会返回 `409`。

### 6.1 请求示例

```bash
curl "http://127.0.0.1:8010/runs/run_1720840000_ab12cd34/report"
```

### 6.2 响应示例

```json
{
  "agent": "ReportAgent",
  "status": "completed",
  "summary": "发现 1 个高风险问题，建议修复。",
  "issues": [
    {
      "issue_id": "ISSUE-001",
      "source": "llm_review",
      "type": "logic_error",
      "severity": "high",
      "confidence": 0.9,
      "file": "order_pricing.py",
      "line_start": 12,
      "line_end": 12,
      "evidence": "折扣计算分支未处理边界值。",
      "root_cause": "输入校验和边界条件缺失。",
      "recommendation": "补充边界判断并添加测试。"
    }
  ],
  "risk_level": "high",
  "should_fix": true,
  "llm_used": true,
  "warnings": []
}
```

### 6.3 报告字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent` | string | 固定为 `ReportAgent`。 |
| `status` | string | 报告生成状态。 |
| `summary` | string | 报告摘要。 |
| `issues` | array | 问题列表。 |
| `risk_level` | string | 整体风险等级。 |
| `should_fix` | boolean | 是否建议修复。 |
| `llm_used` | boolean | 报告是否成功使用 LLM 增强。 |
| `warnings` | string[] | 非致命告警。 |

问题对象字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `issue_id` | string | 问题 ID。 |
| `source` | string | 问题来源，如 `pytest`、`py_compile`、`llm_review`。 |
| `type` | string | 问题类型。 |
| `severity` | string | `critical`、`high`、`medium`、`low`、`info`。 |
| `confidence` | number | 置信度，范围通常为 0 到 1。 |
| `file` | string | 关联文件。 |
| `line_start` | number/null | 起始行。 |
| `line_end` | number/null | 结束行。 |
| `evidence` | string | 问题证据。 |
| `root_cause` | string | 根因分析。 |
| `recommendation` | string | 修复建议。 |

## 7. 获取修复 patch

```http
GET /runs/{run_id}/diff.patch
Accept: text/x-diff
```

返回 FixAgent 生成的 unified diff。该接口返回文本。

### 7.1 请求示例

```bash
curl "http://127.0.0.1:8010/runs/run_1720840000_ab12cd34/diff.patch"
```

### 7.2 响应示例

```diff
--- a/order_pricing.py
+++ b/order_pricing.py
@@ -1 +1 @@
-old
+new
```

如果没有自动修复结果，可能返回空字符串。

## 8. 获取修复后文件内容

```http
GET /runs/{run_id}/fixed-files
```

该接口返回 JSON，不是文件流。适合前端展示预览，或由后端二次封装成下载接口。

### 8.1 请求示例

```bash
curl "http://127.0.0.1:8010/runs/run_1720840000_ab12cd34/fixed-files"
```

### 8.2 响应示例

```json
{
  "files": [
    {
      "path": "order_pricing.py",
      "content": "def fixed():\n    return True\n"
    }
  ]
}
```

### 8.3 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `files` | array | 修复后的文件列表。 |
| `files[].path` | string | 文件相对路径。 |
| `files[].content` | string | 修复后的 UTF-8 文本内容。 |

若 `files` 为空，说明没有可下载的自动修复文件。此时可以引导用户查看报告，或下载 `diff.patch`。

## 9. 下载指定产物

```http
GET /runs/{run_id}/artifacts/{name}
```

该接口返回文件流。可用于下载状态文件、完整结果、patch 或某个修复后的文件。

### 9.1 可下载产物

| `name` | 说明 |
|---|---|
| `status.json` | 任务状态文件。 |
| `result.json` | 完整执行结果。 |
| `fix.patch` | 修复 patch。 |
| `project.json` | 本次任务输入。 |
| 修复文件路径 | 从 `fixed-files` 返回的 `files[].path` 中选择。 |

### 9.2 请求示例

```bash
curl -OJ "http://127.0.0.1:8010/runs/run_1720840000_ab12cd34/artifacts/fix.patch"
curl -OJ "http://127.0.0.1:8010/runs/run_1720840000_ab12cd34/artifacts/order_pricing.py"
```

## 10. 状态枚举

任务状态：

```ts
type RunStatus = "queued" | "running" | "completed" | "failed";
```

Agent 步骤状态：

```ts
type StepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "passed"
  | "skipped"
  | "unknown";
```

风险等级：

```ts
type Severity = "critical" | "high" | "medium" | "low" | "info";
```

## 11. 错误响应

错误响应通常使用 FastAPI 默认格式：

```json
{
  "detail": "error message"
}
```

常见状态码：

| 状态码 | 场景 |
|---:|---|
| `400` | 文件名非法、非 `.py` 文件、非 UTF-8 文件、重复文件名等。 |
| `404` | `run_id` 不存在、产物不存在、结果不存在。 |
| `409` | 任务尚未完成时访问报告或修复文件。 |
| `422` | multipart 表单字段类型不合法。 |
| `500` | 服务内部异常。 |

错误示例：

```json
{
  "detail": "only .py files are supported: notes.txt"
}
```

```json
{
  "detail": "run is not complete"
}
```

## 12. 前端对接建议

### 12.1 最小页面能力

- 上传 `.py` 文件，支持多文件。
- 填写可选需求说明 `requirement`。
- 创建任务后轮询 `GET /runs/{run_id}`。
- 任务完成后展示：
  - `summary`
  - `report.risk_level`
  - `report.issues`
  - `report.warnings`
- 提供下载入口：
  - 下载 patch：`GET /runs/{run_id}/diff.patch`
  - 下载单个修复文件：`GET /runs/{run_id}/artifacts/{file_path}`
  - 如需 zip，需要调用方自行基于 `fixed-files` 打包。

### 12.2 TypeScript DTO 参考

```ts
interface RunCreated {
  run_id: string;
  status: "queued";
  links: {
    self: string;
    report: string;
    patch: string;
    fixed_files: string;
  };
}

interface RunStatusResponse {
  run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  steps: Array<{ agent: string; status: string }>;
  summary: string;
  result: Record<string, unknown> | null;
  links: {
    self: string;
    report: string;
    patch: string;
    fixed_files: string;
  };
}

interface ReportResponse {
  agent: "ReportAgent";
  status: string;
  summary: string;
  issues: ReportIssue[];
  risk_level: "critical" | "high" | "medium" | "low" | "info";
  should_fix: boolean;
  llm_used: boolean;
  warnings: string[];
}

interface ReportIssue {
  issue_id: string;
  source: string;
  type: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  confidence: number;
  file: string;
  line_start: number | null;
  line_end: number | null;
  evidence: string;
  root_cause: string;
  recommendation: string;
}

interface FixedFilesResponse {
  files: Array<{
    path: string;
    content: string;
  }>;
}
```

## 13. Java 或其他后端是否必须

当前接口已经可以由前端直接调用 FastAPI，但需要注意：

- 当前服务未配置 CORS。
- 当前服务未实现鉴权。
- 当前服务会执行上传的 Python 代码，生产环境必须考虑沙箱隔离、限流和任务队列。
- 当前没有 zip 下载接口。

因此：

- 内部 Demo 或本地演示：前端可以直接对接 FastAPI。
- 接入已有系统：可以让 Java 后端作为 BFF 或网关层。
- 生产部署：建议至少保留一层网关或后端服务处理鉴权、审计、限流、存储和下载聚合。

如果由 Java 后端代理，建议 Java 侧只暴露四个前端接口：

```http
POST /api/tcr/runs
GET  /api/tcr/runs/{runId}
GET  /api/tcr/runs/{runId}/report
GET  /api/tcr/runs/{runId}/download
```

其中 `/download` 由 Java 调用 FastAPI 的 `/fixed-files` 后自行返回单文件或 zip。

## 14. 当前限制

- 目前主要支持 Python 文件。
- 文件上传路径会被压平成 basename，暂不保留目录结构。
- 自动修复结果不会覆盖用户原文件，只保存到任务产物目录。
- 任务执行依赖 FastAPI 进程内 `BackgroundTasks`，高并发或长任务场景建议改为任务队列。
- 运行产物保存在本地磁盘，多实例部署时需要共享存储或粘性路由。
- LLM 自测是模型推断结果，不等价于用户确认的验收测试。

