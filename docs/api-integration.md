# TCR Agent 接口对接文档

> 2026-07-14 更新：Java 后端 / BFF 方案已废弃。当前 MVP 阶段前端直接调用工作区里的 FastAPI 包装后端。前端同事优先阅读 `docs/frontend-backend-interaction-flow.md`。

本文档面向后端和前端联调。当前 Agent 能力已经由 FastAPI 包装，核心实现位于 `src/tcr_agent/api.py`。

## 1. 服务定位

当前 MVP 直连模式：

```text
Browser
  -> FastAPI TCR Agent Service
    -> LLMTestGenerationAgent
    -> TestAgent
    -> ReportAgent
    -> FixAgent
```

下面的 Java Backend 定位为历史方案，仅作为后续如果重新引入 BFF 时参考。

```text
Browser
  -> Java Backend
    -> FastAPI TCR Agent Service
      -> LLMTestGenerationAgent
      -> TestAgent
      -> ReportAgent
      -> FixAgent
```

FastAPI Agent 服务负责：

- 接收 Python 源码文件和需求说明。
- 异步执行测试生成、测试/合规检查、报告生成、自动修复。
- 提供运行状态、结构化报告、patch 和修复后文件内容。

Java 后端建议负责：

- 鉴权、用户态任务记录、文件大小限制、审计日志。
- 将前端上传的文件转发给 FastAPI。
- 轮询或转发任务状态。
- 将修复后文件内容打包成单文件或 zip 供前端下载。

## 2. FastAPI Agent 服务

### 2.1 启动方式

```bash
.venv/bin/python -m uvicorn tcr_agent.api:app --host 127.0.0.1 --port 8010
```

默认 Base URL：

```text
http://127.0.0.1:8010
```

运行产物默认保存到：

```text
.tcr_runs/{run_id}/
```

可通过环境变量覆盖：

```text
TCR_RUNS_DIR=/path/to/runs
```

LLM 网关相关环境变量：

```text
LLM_GATEWAY_BASE_URL=https://api.example.com
LLM_GATEWAY_API_KEY=your-api-key
LLM_GATEWAY_MODEL=model-name
LLM_GATEWAY_TIMEOUT_SECONDS=60
LLM_GATEWAY_AUTH_HEADER=authorization
LLM_GATEWAY_VERIFY_SSL=true
LLM_GATEWAY_EXTRA_HEADERS_JSON={}
```

FastAPI 自带文档地址：

```text
GET /docs
GET /openapi.json
```

## 3. FastAPI 接口清单

### 3.1 创建异步任务

```http
POST /runs
Content-Type: multipart/form-data
```

#### 请求字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|---|
| `files` | file[] | 是 | 无 | 一个或多个 `.py` 文件，必须是 UTF-8 文本。 |
| `requirement` | string | 否 | `""` | 自然语言需求说明，用于 LLM 自测、报告和修复。 |
| `ai_review` | boolean | 否 | `true` | 是否启用 AI 代码审查。 |
| `llm_generate_tests` | boolean | 否 | `true` | 没有用户测试文件时，是否让 LLM 生成 pytest 测试。 |
| `report_use_llm` | boolean | 否 | `true` | ReportAgent 是否使用 LLM 增强报告。 |
| `auto_fix` | boolean | 否 | `true` | 是否启用 FixAgent 自动修复。 |
| `fix_target_severities` | string | 否 | `critical,high,medium` | 允许自动修复的问题级别，逗号分隔。 |

#### 文件规则

- 当前仅支持 `.py` 文件。
- 文件名不能是空值，不能包含绝对路径或 `..`。
- 上传文件会按文件名归一化，当前实现会保留 basename，例如 `src/main.py` 会保存为 `main.py`。
- 不允许重复文件名。
- 如果上传了用户测试文件，如 `test_xxx.py` 或 `xxx_test.py`，服务会自动关闭 LLM 生成测试，避免重复生成测试。

#### curl 示例

```bash
curl -F "files=@examples/python_no_tests/order_pricing.py" \
  -F "requirement=订单金额计算需求" \
  -F "ai_review=true" \
  -F "llm_generate_tests=true" \
  -F "report_use_llm=true" \
  -F "auto_fix=true" \
  http://127.0.0.1:8010/runs
```

#### 成功响应

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

### 3.2 查询任务状态

```http
GET /runs/{run_id}
```

#### 响应字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | string | 任务 ID。 |
| `status` | string | 任务状态：`queued`、`running`、`completed`、`failed`。 |
| `steps` | array | Agent 步骤状态。 |
| `summary` | string | 报告摘要；失败时可能是错误信息。 |
| `result` | object/null | 完整 Agent 结果。任务完成前通常为 `null`。 |
| `links` | object | 后续接口链接。 |

#### 运行中响应示例

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

#### 完成响应示例

```json
{
  "run_id": "run_1720840000_ab12cd34",
  "status": "completed",
  "steps": [
    {"agent": "LLMTestGenerationAgent", "status": "skipped"},
    {"agent": "TestAgent", "status": "passed"},
    {"agent": "ReportAgent", "status": "completed"},
    {"agent": "FixAgent", "status": "skipped"}
  ],
  "summary": "未发现需要修复的问题。",
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

#### 前端轮询建议

- 轮询间隔建议 2 到 5 秒。
- `queued`、`running`：继续轮询。
- `completed`：停止轮询，展示报告和下载入口。
- `failed`：停止轮询，展示错误信息。

### 3.3 获取结构化报告

```http
GET /runs/{run_id}/report
```

任务完成后返回 `report_result`。

#### 响应示例

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

#### 主要字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `summary` | string | 报告摘要，前端可直接展示。 |
| `risk_level` | string | `critical`、`high`、`medium`、`low`、`info`。 |
| `should_fix` | boolean | 是否建议修复。 |
| `issues` | array | 问题列表。 |
| `issues[].severity` | string | 问题级别。 |
| `issues[].file` | string | 关联文件。 |
| `issues[].line_start` | number/null | 起始行。 |
| `issues[].evidence` | string | 证据。 |
| `issues[].root_cause` | string | 根因。 |
| `issues[].recommendation` | string | 修复建议。 |
| `warnings` | array | 非致命告警。 |

### 3.4 下载 unified diff

```http
GET /runs/{run_id}/diff.patch
Accept: text/x-diff
```

返回 FixAgent 生成的 unified diff。

#### 响应示例

```diff
--- a/order_pricing.py
+++ b/order_pricing.py
@@ -1 +1 @@
-old
+new
```

如果没有可应用修复，可能返回空字符串。

### 3.5 获取修复后文件内容

```http
GET /runs/{run_id}/fixed-files
```

返回修复后文件列表和文件内容。当前接口返回 JSON，不是文件流。

#### 响应示例

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

前端如果只需要“下载修改好的文件”，建议由 Java 后端调用该接口后转换为文件下载：

- 只有一个修复文件：直接返回该文件。
- 多个修复文件：打包为 zip。
- 没有修复文件：可提示“暂无自动修复结果”，或提供 `diff.patch` 下载。

### 3.6 下载指定产物

```http
GET /runs/{run_id}/artifacts/{name}
```

可下载的产物：

| name | 说明 |
|---|---|
| `status.json` | 当前任务状态文件。 |
| `result.json` | 完整 Agent 结果。 |
| `fix.patch` | 修复补丁。 |
| `project.json` | 本次任务输入。 |
| 修复文件路径 | `fixed_files` 下的具体修复文件。 |

示例：

```http
GET /runs/run_1720840000_ab12cd34/artifacts/fix.patch
GET /runs/run_1720840000_ab12cd34/artifacts/order_pricing.py
```

## 4. 错误响应

FastAPI 默认错误格式：

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
| `409` | 任务尚未完成时访问报告、patch 或修复文件。 |
| `422` | multipart 表单字段类型不合法。 |
| `500` | 服务内部异常。 |

## 5. 历史方案：建议的 Java 后端接口

本节是 Java / BFF 方案时期的接口建议。当前 MVP 阶段已不采用，前端请直接使用 FastAPI 接口：`POST /runs`、`GET /runs/{run_id}`、`GET /runs/{run_id}/report`、`GET /runs/{run_id}/fixed-files`、`GET /runs/{run_id}/diff.patch`。

前端只需要四类能力：上传、轮询、展示报告、下载修复文件。若后续重新引入 Java 后端，可以参考本节暴露更贴近页面的接口，避免前端直接依赖 Agent 内部字段。

### 5.1 创建任务

```http
POST /api/tcr/runs
Content-Type: multipart/form-data
```

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
|---|---:|---:|---|
| `files` | file[] | 是 | 前端上传的 Python 文件。 |
| `requirement` | string | 否 | 需求说明。 |
| `autoFix` | boolean | 否 | 是否自动修复，默认 `true`。 |

Java 后端转发到 FastAPI：

```text
POST {agentBaseUrl}/runs
```

#### 响应给前端

```json
{
  "taskId": "run_1720840000_ab12cd34",
  "status": "queued",
  "pollUrl": "/api/tcr/runs/run_1720840000_ab12cd34"
}
```

### 5.2 查询任务

```http
GET /api/tcr/runs/{taskId}
```

#### 响应给前端

```json
{
  "taskId": "run_1720840000_ab12cd34",
  "status": "completed",
  "summary": "发现 1 个高风险问题，已生成修复结果。",
  "steps": [
    {"name": "LLMTestGenerationAgent", "status": "skipped"},
    {"name": "TestAgent", "status": "passed"},
    {"name": "ReportAgent", "status": "completed"},
    {"name": "FixAgent", "status": "completed"}
  ],
  "report": {
    "riskLevel": "high",
    "shouldFix": true,
    "issues": [
      {
        "id": "ISSUE-001",
        "severity": "high",
        "file": "order_pricing.py",
        "lineStart": 12,
        "evidence": "折扣计算分支未处理边界值。",
        "rootCause": "输入校验和边界条件缺失。",
        "recommendation": "补充边界判断并添加测试。"
      }
    ]
  },
  "downloadUrl": "/api/tcr/runs/run_1720840000_ab12cd34/download"
}
```

建议 Java 后端在 `completed` 后把 FastAPI 的 `report_result` 转成前端 camelCase DTO。任务未完成时，`report` 可以为 `null`。

### 5.3 获取报告

如果页面希望状态接口保持轻量，也可以单独提供报告接口：

```http
GET /api/tcr/runs/{taskId}/report
```

Java 后端转发：

```text
GET {agentBaseUrl}/runs/{run_id}/report
```

### 5.4 下载修复文件

```http
GET /api/tcr/runs/{taskId}/download
```

建议 Java 后端实现逻辑：

1. 调用 `GET {agentBaseUrl}/runs/{run_id}/fixed-files`。
2. 如果 `files.length == 1`，返回单文件流。
3. 如果 `files.length > 1`，打包为 zip 返回。
4. 如果 `files.length == 0`，可返回 `404` 或改为返回 `fix.patch`。

单文件响应头示例：

```http
Content-Type: text/x-python; charset=utf-8
Content-Disposition: attachment; filename="order_pricing.py"
```

zip 响应头示例：

```http
Content-Type: application/zip
Content-Disposition: attachment; filename="tcr-fixed-files.zip"
```

如果产品希望明确下载 patch，可额外提供：

```http
GET /api/tcr/runs/{taskId}/patch
```

后端转发：

```text
GET {agentBaseUrl}/runs/{run_id}/diff.patch
```

## 6. 前端调用流程

```text
1. 用户选择文件，填写可选需求说明。
2. POST /api/tcr/runs 上传文件。
3. 拿到 taskId 后，每 2 到 5 秒调用 GET /api/tcr/runs/{taskId}。
4. status = queued/running 时展示进度。
5. status = completed 时展示 summary、riskLevel、issues。
6. 如果 downloadUrl 存在，展示“下载修复文件”按钮。
7. status = failed 时展示错误信息并停止轮询。
```

前端状态枚举：

```ts
type TaskStatus = "queued" | "running" | "completed" | "failed";
type StepStatus = "pending" | "running" | "completed" | "failed" | "passed" | "skipped" | "unknown";
type Severity = "critical" | "high" | "medium" | "low" | "info";
```

建议的前端 DTO：

```ts
interface TcrRunStatus {
  taskId: string;
  status: TaskStatus;
  summary: string;
  steps: Array<{ name: string; status: StepStatus }>;
  report: TcrReport | null;
  downloadUrl?: string;
}

interface TcrReport {
  riskLevel: Severity;
  shouldFix: boolean;
  issues: TcrIssue[];
}

interface TcrIssue {
  id: string;
  severity: Severity;
  file: string;
  lineStart: number | null;
  lineEnd?: number | null;
  evidence: string;
  rootCause: string;
  recommendation: string;
}
```

## 7. 对接注意事项

- 当前 FastAPI 未配置 CORS。推荐前端只访问 Java 后端，由 Java 后端访问 FastAPI。
- 当前 FastAPI 无鉴权。生产环境建议只允许内网访问，鉴权放在 Java 后端。
- 当前任务使用 FastAPI `BackgroundTasks` 在服务进程内执行。长任务或高并发场景建议后续接入独立队列。
- 当前产物保存在本地磁盘。多实例部署时需要共享存储，或保证同一 `run_id` 路由回同一实例。
- 当前主要支持 Python 文件。
- 当前修复结果写入临时沙箱和 `.tcr_runs/{run_id}/fixed_files/`，不会覆盖用户原始文件。
- 当前没有直接返回 zip 的 FastAPI 接口。若前端需要一键下载，建议由 Java 后端聚合 `fixed-files` 后返回。
- LLM 自测是模型推断，不等价于用户确认的验收标准。报告中会通过 `oracle_source=llm_inferred` 标记。
