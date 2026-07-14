# 前端与 FastAPI 后端交互逻辑

## 1. 对接原则

当前 Java 后端方案已废弃，前端直接调用工作区里的 FastAPI 包装后端。

```txt
前端页面 -> FastAPI TCR Agent 后端
```

FastAPI 默认地址：

```txt
http://127.0.0.1:8010
```

前端只需要关心三个事情：

1. 上传文件，拿到 `run_id`。
2. 根据 `run_id` 轮询任务状态。
3. 任务完成后展示报告、Issue、patch 和修复文件。

> 前端页面路由里可以继续叫 `taskId`，但它的值实际就是后端返回的 `run_id`。

## 2. 页面和接口关系

| 页面 | 触发时机 | 调用接口 | 前端动作 |
|---|---|---|---|
| 上传页 | 用户点击上传 | `POST /runs` | 上传文件，拿到 `run_id` 后跳转处理中页 |
| 处理中页 | 页面进入后自动触发 | `GET /runs/{run_id}` | 每 2 到 5 秒轮询一次 |
| 结果页 | 任务完成后进入 | `GET /runs/{run_id}/report` | 获取报告和 Issue |
| 结果页 | 展示修复文件 | `GET /runs/{run_id}/fixed-files` | 获取修复后文件列表和内容 |
| 结果页 | 查看 patch | `GET /runs/{run_id}/diff.patch` | 查看或下载修复 diff |
| 结果页 | 下载指定产物 | `GET /runs/{run_id}/artifacts/{name}` | 下载 `fix.patch` 或指定修复文件 |

## 3. 整体交互流程

```txt
1. 用户进入上传页
2. 用户选择 .py 文件并点击上传
3. 前端调用 POST /runs
4. FastAPI 返回 run_id
5. 前端跳转 /processing/:taskId
6. 处理中页用 taskId 作为 run_id，轮询 GET /runs/{run_id}
7. status = queued / running，继续轮询
8. status = completed，停止轮询并跳转 /result/:taskId
9. status = failed，停止轮询并展示错误
10. 结果页请求 report、fixed-files、diff.patch
```

## 4. 上传页交互

### 4.1 请求

```http
POST /runs
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---:|---:|---|---|
| `files` | `File[]` | 是 | 无 | 上传的 Python 文件，可多个 |
| `requirement` | `string` | 否 | `""` | 用户填写的需求说明 |
| `ai_review` | `boolean` | 否 | `true` | 是否启用 AI 代码审查 |
| `llm_generate_tests` | `boolean` | 否 | `true` | 是否让 LLM 生成测试 |
| `report_use_llm` | `boolean` | 否 | `true` | 报告是否使用 LLM 增强 |
| `auto_fix` | `boolean` | 否 | `true` | 是否自动修复 |
| `fix_target_severities` | `string` | 否 | `critical,high,medium` | 自动修复的问题级别 |

文件限制：

- 当前只支持 `.py` 文件。
- 文件内容必须是 UTF-8 文本。
- 文件名不能重复。
- 文件名不能包含绝对路径或 `..`。

前端示例：

```ts
const formData = new FormData();

files.forEach((file) => {
  formData.append("files", file);
});

formData.append("requirement", requirement);
formData.append("ai_review", "true");
formData.append("llm_generate_tests", "true");
formData.append("report_use_llm", "true");
formData.append("auto_fix", "true");
formData.append("fix_target_severities", "critical,high,medium");

const res = await fetch(`${API_BASE_URL}/runs`, {
  method: "POST",
  body: formData,
});

const data = await res.json();
const taskId = data.run_id;
```

### 4.2 响应

```ts
{
  run_id: string;
  status: "queued";
  links: {
    self: string;
    report: string;
    patch: string;
    fixed_files: string;
  };
}
```

示例：

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

### 4.3 前端处理

- 上传中：禁用上传按钮，展示提交中。
- 上传成功：把 `run_id` 当作页面里的 `taskId`，跳转 `/processing/:taskId`。
- 上传失败：展示 FastAPI 返回的 `detail`。

## 5. 处理中页交互

### 5.1 请求

```http
GET /runs/{run_id}
```

建议轮询间隔：2 到 5 秒。

### 5.2 响应

```ts
{
  run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  steps: Array<{
    agent: string;
    status: string;
  }>;
  summary: string;
  result: unknown | null;
  links: {
    self: string;
    report: string;
    patch: string;
    fixed_files: string;
  };
}
```

运行中示例：

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

### 5.3 前端处理

| 后端状态 | 前端行为 |
|---|---|
| `queued` | 任务已创建，继续轮询 |
| `running` | 任务处理中，继续轮询 |
| `completed` | 停止轮询，跳转 `/result/:taskId` |
| `failed` | 停止轮询，展示 `summary` 或接口错误 |

注意事项：

- 页面刷新后，可以直接从 URL 里读取 `taskId` 继续轮询。
- 组件卸载时要清理定时器，避免重复请求。
- 建议设置超时时间，例如超过 10 分钟仍未完成时提示用户稍后查看。

## 6. 结果页交互

结果页建议请求三个接口：

1. `GET /runs/{run_id}/report`：报告和 Issue。
2. `GET /runs/{run_id}/fixed-files`：修复后的文件内容。
3. `GET /runs/{run_id}/diff.patch`：修复 diff。

### 6.1 获取报告和 Issue

```http
GET /runs/{run_id}/report
```

任务未完成时，该接口会返回 `409`。

响应：

```ts
{
  agent: "ReportAgent";
  status: string;
  summary: string;
  issues: Array<{
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
  }>;
  risk_level: "critical" | "high" | "medium" | "low" | "info";
  should_fix: boolean;
  llm_used: boolean;
  warnings: string[];
}
```

前端展示：

- 顶部展示 `summary` 和 `risk_level`。
- 右侧展示 `issues` 列表。
- 点击 Issue 后展示文件名、行号、证据、根因和修复建议。

### 6.2 获取修复后文件

```http
GET /runs/{run_id}/fixed-files
```

响应：

```ts
{
  files: Array<{
    path: string;
    content: string;
  }>;
}
```

前端展示：

- `files.length > 0`：展示 Repair 文件列表。
- `files.length === 0`：展示“暂无修复文件”。
- `content` 可以直接做代码预览。

### 6.3 查看 patch

```http
GET /runs/{run_id}/diff.patch
```

返回文本：

```ts
const patchText = await fetch(`${API_BASE_URL}/runs/${taskId}/diff.patch`).then((res) => res.text());
```

前端展示：

- 有内容：展示 diff 预览。
- 无内容：展示“暂无 patch”。

### 6.4 下载指定产物

当前 FastAPI 没有一键 zip 下载接口，可以先使用已有产物接口：

```http
GET /runs/{run_id}/artifacts/{name}
```

可下载：

- `fix.patch`
- 修复文件名，例如 `order_pricing.py`

示例：

```tsx
<a href={`${API_BASE_URL}/runs/${taskId}/artifacts/fix.patch`}>
  下载 patch
</a>
```

如果要下载某个修复文件：

```tsx
<a href={`${API_BASE_URL}/runs/${taskId}/artifacts/${encodeURIComponent(file.path)}`}>
  下载修复文件
</a>
```

## 7. 前端建议封装

建议统一放到 `services/taskApi.ts`：

```ts
const API_BASE_URL = "http://127.0.0.1:8010";

export function createRun(formData: FormData) {
  return fetch(`${API_BASE_URL}/runs`, {
    method: "POST",
    body: formData,
  }).then((res) => res.json());
}

export function getRunStatus(taskId: string) {
  return fetch(`${API_BASE_URL}/runs/${taskId}`).then((res) => res.json());
}

export function getRunReport(taskId: string) {
  return fetch(`${API_BASE_URL}/runs/${taskId}/report`).then((res) => res.json());
}

export function getFixedFiles(taskId: string) {
  return fetch(`${API_BASE_URL}/runs/${taskId}/fixed-files`).then((res) => res.json());
}

export function getPatch(taskId: string) {
  return fetch(`${API_BASE_URL}/runs/${taskId}/diff.patch`).then((res) => res.text());
}
```

## 8. 前端状态定义

```ts
export type TaskStatus = "queued" | "running" | "completed" | "failed";

export type StepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "passed"
  | "skipped"
  | "unknown";

export type Severity = "critical" | "high" | "medium" | "low" | "info";
```

## 9. 异常处理约定

| 场景 | 前端处理 |
|---|---|
| `POST /runs` 返回 400 | 展示文件格式、编码、重复文件名等错误 |
| `POST /runs` 返回 500 | 展示“任务创建失败，请稍后重试” |
| `GET /runs/{run_id}` 返回 404 | 展示“任务不存在或已过期” |
| `GET /runs/{run_id}` 返回 `failed` | 展示 `summary` |
| `GET /runs/{run_id}/report` 返回 409 | 说明任务还没完成，回到处理中页或继续等待 |
| `GET /runs/{run_id}/fixed-files` 返回空数组 | 展示“暂无修复文件” |

## 10. 跨域说明

如果前端开发服务和 FastAPI 不同端口，浏览器会遇到跨域限制。二选一处理即可：

1. 前端 dev server 配置 proxy，把 `/api` 或 `/runs` 代理到 `http://127.0.0.1:8010`。
2. FastAPI 增加 CORS 配置，允许前端开发地址访问。

MVP 阶段更建议前端配置 proxy，这样前端代码里可以直接请求 `/runs`。

## 11. 前端联调顺序

1. 先联调上传页：确认可以拿到 `run_id`。
2. 再联调处理中页：确认 `queued -> running -> completed / failed` 状态流转。
3. 再联调结果页：确认报告和 Issue 能展示。
4. 再联调 `fixed-files`：确认 Repair 文件可以预览。
5. 最后联调 `diff.patch` 和 `artifacts`：确认 patch 和文件下载可用。

