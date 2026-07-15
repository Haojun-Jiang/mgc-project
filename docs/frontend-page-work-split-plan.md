# 前端三页面分工方案

## 1. 目标

本次前端按三个页面拆分，由三位同事分别负责开发：

1. 上传页：上传文件并创建任务。
2. 处理中页：轮询后端状态，展示 loading。
3. 结果页：展示报告、Issue 和 Repair 文件。

整体流程：

```txt
上传文件 -> 创建任务 -> 轮询状态 -> 展示结果
```

## 2. 同事 A：上传页

页面路径：

```txt
/upload
```

主要负责：

- 页面标题展示。
- 上传文件按钮。
- 文件格式和大小校验。
- 调用上传接口。
- 上传成功后拿到 `run_id`，页面路由中可继续命名为 `taskId`。
- 跳转到处理中页。
- 上传失败提示。

交付内容：

- `UploadPage`
- `FileUploader`
- 上传接口调用逻辑

## 3. 同事 B：处理中页

页面路径：

```txt
/processing/:taskId
```

主要负责：

- loading 页面。
- 根据 `taskId` 轮询后端任务状态；这里的 `taskId` 实际等于 FastAPI 返回的 `run_id`。
- 展示当前处理阶段。
- 任务成功后跳转结果页。
- 任务失败时展示错误信息。
- 展示 VerifyAgent 验证阶段和修复轮次。
- 支持重新上传入口。

任务状态建议：

```ts
type TaskStatus = "queued" | "running" | "completed" | "failed";
```

交付内容：

- `ProcessingPage`
- `useTaskPolling`
- 轮询逻辑
- 成功 / 失败 / 超时处理

## 4. 同事 C：结果页

页面路径：

```txt
/result/:taskId
```

结果页建议按会议图做成左右布局：

```txt
左侧：原始文件、报告文件、修复文件预览
右侧：Issue 列表、Repair 文件列表
```

主要负责：

- 获取任务结果。
- 展示原始上传文件。
- 展示所有报告文件。
- 展示 Issue 列表。
- 展示 Repair 修复文件。
- 支持文件下载。
- 支持文件预览。
- 预留 diff 对比入口。

交付内容：

- `ResultPage`
- `ReportList`
- `IssuePanel`
- `RepairPanel`
- `FileCard`

## 5. 公共约定

三位同事开发前需要先对齐：

- 路由地址。
- 接口字段。
- 任务状态枚举。
- 文件展示字段。
- 错误提示方式。

建议公共目录：

```txt
src/
  pages/
    UploadPage/
    ProcessingPage/
    ResultPage/
  components/
    FileUploader/
    FileCard/
    IssuePanel/
    RepairPanel/
  hooks/
    useTaskPolling.ts
  services/
    taskApi.ts
  types/
    task.ts
```

## 6. 接口建议

当前前端直连 FastAPI 包装后端，默认地址：

```txt
http://127.0.0.1:8010
```

页面路由里的 `taskId` 实际等于 FastAPI 返回的 `run_id`。

上传文件：

```http
POST /runs
```

返回：

```ts
{
  run_id: string;
  status: "queued";
}
```

查询状态：

```http
GET /runs/:taskId
```

返回：

```ts
{
  status: "queued" | "running" | "completed" | "failed";
  summary?: string;
  steps?: [];
  verify_result?: object;
  fix_round?: number;
  max_fix_rounds?: number;
  message?: string;
}
```

获取结果：

```http
GET /runs/:taskId/report
```

返回：

```ts
{
  issues: [];
  summary: string;
  risk_level: string;
}
```

获取修复文件：

```http
GET /runs/:taskId/fixed-files
```

返回：

```ts
{
  files: Array<{
    path: string;
    content: string;
  }>;
}
```

获取修复 patch：

```http
GET /runs/:taskId/diff.patch
```

返回：

```ts
string
```

## 7. 联调顺序

1. 三人先确认接口字段和路由。
2. 先用 Mock 数据并行开发。
3. 同事 A 和同事 B 先联调上传到轮询链路。
4. 同事 B 和同事 C 再联调任务成功后进入结果页。
5. 最后统一处理失败、空数据、刷新页面等异常场景。

## 8. 验收标准

- 上传后可以拿到 `run_id`。
- loading 页可以正常轮询任务状态。
- 任务成功后可以跳转结果页。
- 任务失败时有明确提示。
- 结果页可以展示报告、Issue 和 Repair 文件。
- 文件可以下载或预览。
- 页面刷新后不丢失任务状态。
