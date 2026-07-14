# TCR Agent Frontend

TCR Agent 的前端工作台，包含上传、处理中和结果三个页面。

## 本地启动

要求 Node.js 22.13+ 和 pnpm。

```bash
pnpm install
pnpm dev
```

默认访问地址：`http://localhost:3000/upload`。

前端通过 `/api/tcr/*` 代理访问 FastAPI，FastAPI 默认地址为
`http://127.0.0.1:8010`。如果地址不同，可在启动前设置：

```bash
TCR_API_BASE_URL=http://your-api-host:8010 pnpm dev
```

## 页面

- `/upload`：上传 Python 文件、填写需求并创建检测任务。
- `/processing/:taskId`：轮询整体任务状态，完成后自动进入结果页。
- `/result/:taskId`：查看报告、原始文件、生成测试、Issue、修复文件和 Patch。

## 验证

```bash
pnpm build
```
