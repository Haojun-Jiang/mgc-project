# 修补后代码文件下载能力方案

版本日期：2026-07-13  
关联实现：`src/tcr_agent/api.py`  
关联接口文档：`docs/tcr-agent-current-api.md`

## 1. 当前结论

“下载修补完成的代码文件”当前不是完全没有实现，而是只实现了底层能力，缺少一个适合前端直接使用的一键下载接口。

当前已经实现：

- `GET /runs/{run_id}/fixed-files`
  - 返回修复后文件的 JSON 列表。
  - 每个文件包含 `path` 和 `content`。
- `GET /runs/{run_id}/artifacts/{name}`
  - 可以下载指定产物。
  - 当前可以下载 `fix.patch`、`result.json`、`status.json`、`project.json`。
  - 也可以下载 `fixed_files` 目录下的单个修复文件，但现有路由参数是 `{name}`，不适合处理多级路径。
- `GET /runs/{run_id}/diff.patch`
  - 可以下载修复补丁文本。

当前缺少：

- `GET /runs/{run_id}/download`
  - 一键下载修复后代码文件。
  - 单文件时直接返回 `.py` 文件。
  - 多文件时返回 `.zip`。
- 统一的前端下载入口。
- 对“没有修复文件”场景的明确响应。
- 对多文件、多目录修复结果的完整下载支持。

因此，准确表述是：

```text
当前已有修复文件内容查询能力，但缺少面向前端的一键下载修复后代码文件能力。
```

## 2. 推荐目标

新增一个 FastAPI 直接可用的下载接口：

```http
GET /runs/{run_id}/download
```

目标行为：

| 场景 | 响应 |
|---|---|
| 任务未完成 | `409 run is not complete` |
| 任务失败或结果不存在 | 沿用现有 `ready_result` 行为 |
| 没有修复文件 | `404 fixed files not found` |
| 只有一个修复文件 | 直接返回该文件 |
| 有多个修复文件 | 返回 zip 包 |

前端只需要在任务完成后展示一个按钮：

```text
下载修复后代码
```

按钮请求：

```http
GET /runs/{run_id}/download
```

## 3. 接口设计

### 3.1 下载修复后代码

```http
GET /runs/{run_id}/download
```

### 3.2 单文件响应

当 `fixed_files` 中只有一个文件时，直接返回文件流。

示例响应头：

```http
HTTP/1.1 200 OK
Content-Type: text/x-python; charset=utf-8
Content-Disposition: attachment; filename="order_pricing.py"
```

响应体：

```python
def fixed():
    return True
```

### 3.3 多文件响应

当 `fixed_files` 中有多个文件时，返回 zip 文件。

示例响应头：

```http
HTTP/1.1 200 OK
Content-Type: application/zip
Content-Disposition: attachment; filename="tcr-fixed-files-run_1720840000_ab12cd34.zip"
```

zip 内部结构：

```text
tcr-fixed-files-run_1720840000_ab12cd34.zip
  order_pricing.py
  test_order_pricing.py
```

### 3.4 无修复文件响应

```http
HTTP/1.1 404 Not Found
Content-Type: application/json
```

```json
{
  "detail": "fixed files not found"
}
```

也可以根据产品偏好改成返回空 patch，但不推荐。因为“没有修复文件”和“有 patch 文件”是两个不同语义。

## 4. 实现方案

### 4.1 FastAPI 侧改动

在 `src/tcr_agent/api.py` 中新增：

```python
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.responses import FileResponse, PlainTextResponse, Response
```

新增接口：

```python
@app.get("/runs/{run_id}/download")
def download_fixed_files(run_id: str):
    run_dir = existing_run_dir(run_id)
    ready_result(run_id)
    fixed_dir = run_dir / "fixed_files"
    files = sorted(item for item in fixed_dir.rglob("*") if item.is_file()) if fixed_dir.exists() else []
    if not files:
        raise HTTPException(status_code=404, detail="fixed files not found")

    if len(files) == 1:
        path = files[0]
        return FileResponse(
            str(path),
            media_type="text/x-python; charset=utf-8",
            filename=path.name,
        )

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(fixed_dir).as_posix())
    buffer.seek(0)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="tcr-fixed-files-{run_id}.zip"',
        },
    )
```

实际落地时建议使用 `StreamingResponse` 或 `Response` 都可以。当前文件通常较小，`BytesIO + Response` 足够；如果后续文件可能很大，再改为临时 zip 文件加 `FileResponse`。

同时更新 `run_links`：

```python
def run_links(run_id: str) -> dict[str, str]:
    return {
        "self": f"/runs/{run_id}",
        "report": f"/runs/{run_id}/report",
        "patch": f"/runs/{run_id}/diff.patch",
        "fixed_files": f"/runs/{run_id}/fixed-files",
        "download": f"/runs/{run_id}/download",
    }
```

### 4.2 可选改动：增强 artifacts 路由

当前接口是：

```python
@app.get("/runs/{run_id}/artifacts/{name}")
```

如果未来保留目录结构，需要改成：

```python
@app.get("/runs/{run_id}/artifacts/{name:path}")
```

这样才能下载类似：

```http
GET /runs/{run_id}/artifacts/src/order_pricing.py
```

不过当前上传文件会压平成 basename，因此该项不是本次最小实现的强依赖。

### 4.3 可选改动：保留上传目录结构

当前 `normalize_upload_filename` 返回的是：

```python
return name
```

这会丢掉上传路径，只保留 basename。

如果后续需要支持多目录工程，应改为保留安全相对路径：

```python
return PurePosixPath(normalized).as_posix()
```

但这会影响现有输入、测试和修复路径匹配，建议作为第二阶段处理。

## 5. 测试方案

在 `tests/test_api.py` 中新增测试。

### 5.1 单文件下载

准备一个只修复 `order_pricing.py` 的 fake result。

验证：

- `GET /runs/{run_id}/download` 返回 `200`。
- `Content-Disposition` 包含 `order_pricing.py`。
- 响应内容包含修复后的代码。

### 5.2 多文件 zip 下载

准备两个修复文件。

验证：

- `GET /runs/{run_id}/download` 返回 `200`。
- `Content-Type` 为 `application/zip`。
- zip 内包含两个文件。
- zip 中文件内容正确。

### 5.3 无修复文件

准备 `fix_result.applied = false` 或没有 `fixed_files` 目录。

验证：

- `GET /runs/{run_id}/download` 返回 `404`。
- `detail = fixed files not found`。

### 5.4 任务未完成

构造 `status = running`。

验证：

- `GET /runs/{run_id}/download` 返回 `409`。
- `detail = run is not complete`。

## 6. 前端对接方案

任务完成前：

```text
禁用下载按钮
```

任务完成后：

```text
显示“下载修复后代码”按钮
```

点击按钮：

```ts
window.location.href = `${baseUrl}/runs/${runId}/download`;
```

或使用 fetch：

```ts
const response = await fetch(`${baseUrl}/runs/${runId}/download`);
if (!response.ok) {
  const error = await response.json();
  throw new Error(error.detail || "下载失败");
}
const blob = await response.blob();
```

前端无需判断单文件还是 zip，浏览器会根据响应头下载。

## 7. Java 后端对接方案

如果保留 Java 后端，Java 可以有两种做法。

### 7.1 推荐：直接代理 FastAPI download 接口

Java 暴露：

```http
GET /api/tcr/runs/{runId}/download
```

Java 转发：

```http
GET {agentBaseUrl}/runs/{runId}/download
```

优点：

- Java 不需要理解修复文件结构。
- 单文件和 zip 逻辑都由 FastAPI 统一处理。
- 前端只依赖 Java 的下载地址。

### 7.2 备选：Java 自行聚合 fixed-files

Java 调用：

```http
GET {agentBaseUrl}/runs/{runId}/fixed-files
```

然后：

- 一个文件：Java 返回单文件下载。
- 多个文件：Java 打 zip 返回。

优点是 Java 完全控制下载响应；缺点是重复实现打包逻辑。

## 8. 推荐实施顺序

第一阶段，最小闭环：

1. FastAPI 新增 `GET /runs/{run_id}/download`。
2. `run_links` 增加 `download` 链接。
3. 补充单文件、多文件、无修复文件测试。
4. 更新接口文档。
5. 前端接入 `links.download`。

第二阶段，工程化增强：

1. `artifacts/{name}` 改为 `artifacts/{name:path}`。
2. 上传文件保留安全相对路径。
3. 下载 zip 内保留原工程目录结构。
4. 增加 CORS、鉴权、文件大小限制和任务队列。

## 9. 最终推荐

推荐在 FastAPI Agent 服务中直接实现：

```http
GET /runs/{run_id}/download
```

原因：

- 这个能力属于 Agent 产物交付的一部分，放在 Agent 服务内语义最完整。
- 前端对接最简单。
- Java 后端如果存在，只需要透明代理。
- 后续无论是否保留 Java，这个能力都能复用。
