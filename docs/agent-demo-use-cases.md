# TCR Agent 现状演示用例

版本日期：2026-07-14  
演示目标：向组内同事展示当前 Agent 已具备 CLI 独立运行入口和 FastAPI 服务化调用入口。  
建议演示顺序：先 CLI，再 API。

## 1. 演示定位

本次展示不强调“完整 PR 平台已经做完”，而是强调：

```text
Agent 核心链路已经能独立运行，并且已经被 FastAPI 包装成可被前端 / Java 后端调用的服务。
```

当前已完成链路：

```text
代码输入
  -> LLMTestGenerationAgent
  -> TestAgent
  -> ReportAgent
  -> FixAgent
  -> 结构化结果 / patch / fixed_files
```

两个演示入口：

| 入口 | 展示目的 | 面向对象 |
|---|---|---|
| CLI 命令行 | 证明 Agent 核心能力不依赖前端和 Java，能独立运行 | 后端、导师、开发同事 |
| FastAPI 接口 | 证明 Agent 已具备服务化对接能力，可供前端和 Java 调用 | 前端、Java 后端同事 |

## 2. 演示准备

进入项目目录：

```bash
cd "/Users/jianghj59/Documents/mgc project"
```

确认虚拟环境可用：

```bash
.venv/bin/python --version
```

如果要演示 LLM 能力，需要确认 `.env` 中配置了：

```text
LLM_GATEWAY_BASE_URL=...
LLM_GATEWAY_API_KEY=...
LLM_GATEWAY_MODEL=...
```

如果只是演示稳定本地链路，不需要 LLM 网关。

## 3. CLI 演示用例

### 用例 1：稳定演示，用户测试失败并生成报告

这个用例不依赖大模型，适合现场第一个跑。

示例代码：

```python
def add(a, b):
    return a - b
```

示例测试：

```python
self.assertEqual(add(1, 2), 3)
```

运行命令：

```bash
.venv/bin/python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --no-report-llm
```

预期展示点：

- `LLMTestGenerationAgent.status = skipped`
  - 因为用户已经提供了测试文件。
- `TestAgent.status = failed`
  - pytest 发现 `-1 != 3`。
- `py_compile.status = passed`
  - 说明代码语法没错，是逻辑错误。
- `ReportAgent.status = completed`
  - 自动归集为结构化问题。
- `report_result.risk_level = high`
  - 测试失败被归为高风险。
- `FixAgent.status = skipped`
  - 因为本用例未开启 `--fix`。

可以重点指给同事看的字段：

```text
test_result.status
test_result.test_results[0].failures[0].message
report_result.summary
report_result.issues
report_result.should_fix
```

### 用例 2：JSON 输入方式运行

这个用例展示 Agent 支持结构化项目输入，方便后端或平台生成任务。

运行命令：

```bash
.venv/bin/python run.py \
  --input examples/python_bug/project.json
```

预期展示点：

- Agent 可以从 Project JSON 启动。
- 输入格式接近后端系统可生成的数据结构。
- 输出仍然是统一的 GraphState JSON。

### 用例 3：启用 AI 代码审查

这个用例需要 LLM 网关可用。

运行命令：

```bash
.venv/bin/python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review \
  --no-report-llm
```

预期展示点：

- `test_result.compliance_results` 中会出现 `tool = llm_review`。
- AI 审查可以补充测试之外的代码问题判断。
- `--no-report-llm` 表示只让 TestAgent 做一次 AI 审查，不让 ReportAgent 再调用 LLM。

### 用例 4：没有测试文件时启用 LLM 自测

这个用例需要 LLM 网关可用。

运行命令：

```bash
.venv/bin/python run.py \
  --code examples/python_no_tests/order_pricing.py \
  --llm-generate-tests \
  --requirement "订单发票计算只统计 active=true 的商品，优惠后金额计税，返回 subtotal、discount、tax、total、item_count" \
  --no-report-llm
```

预期展示点：

- `LLMTestGenerationAgent` 会尝试生成 pytest 测试脚本。
- `generated_test_result.test_files` 中能看到生成的测试文件。
- `TestAgent` 会把 LLM 生成的测试写入沙箱并执行。
- 报告会标记 `oracle_source = llm_inferred`，表示这是模型推断测试，不等于人工确认验收标准。

### 用例 5：启用 FixAgent 沙箱修复

这个用例需要 LLM 网关可用。

运行命令：

```bash
.venv/bin/python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review \
  --fix \
  --no-report-llm
```

预期展示点：

- `FixAgent` 会读取报告问题。
- 只在临时 `workspace_dir` 中应用修复，不覆盖原始文件。
- `fix_result.patches` 会包含 unified diff。
- 如果修复成功，`fix_result.applied = true`。

可以重点说明：

```text
当前自动修复是“沙箱修复建议”，不是直接改用户仓库。
这对演示和安全边界更合适。
```

### 用例 5A：全部测试通过的绿色路径

这个用例不依赖大模型，适合在失败案例之后展示“正常项目不会误报”。

运行命令：

```bash
.venv/bin/python run.py \
  --input examples/python_passing/project.json
```

预期展示点：

- `TestAgent.status = passed`
- `test_result.test_results[0].passed = 3`
- `py_compile.status = passed`
- `ReportAgent.summary = 测试和合规检查未发现需要修复的问题。`
- `report_result.risk_level = info`
- `report_result.should_fix = false`

讲解重点：

```text
这个案例用来证明 Agent 不是只会报错。测试和合规都通过时，报告会明确给出 info 风险和无需修复的结论。
```

### 用例 5B：没有测试文件，但静态语法检查失败

这个用例不依赖大模型，适合展示“即使没有行为测试，基础合规检查仍然能发现问题”。

运行命令：

```bash
.venv/bin/python run.py \
  --input examples/python_syntax_error/project.json
```

预期展示点：

- `LLMTestGenerationAgent.status = skipped`
- `test_result.test_results[0].tool = static_only`
- `test_result.test_results[0].status = skipped`
- `test_result.compliance_results[0].tool = py_compile`
- `test_result.compliance_results[0].status = failed`
- `report_result.issues[0].source = py_compile`
- `report_result.risk_level = high`

讲解重点：

```text
这个案例把“行为测试缺失”和“语法/合规失败”分开展示：行为测试是 skipped，但 TestAgent 整体仍然因为 py_compile 失败而 failed。
```

### 用例 5C：多文件项目中的业务逻辑错误

这个用例不依赖大模型，适合展示真实项目里常见的跨文件导入和部分用例失败。

运行命令：

```bash
.venv/bin/python run.py \
  --input examples/python_multi_file/project.json
```

示例问题：

```python
subtotal += item["price"]
```

这里故意漏乘了 `quantity`。

预期展示点：

- `files` 中包含 `discounts.py`、`inventory.py`、`test_inventory.py`
- pytest 会运行 3 个测试，其中 2 个失败、1 个通过。
- `TestAgent.status = failed`
- `py_compile.status = passed`
- `ReportAgent` 会把测试失败聚合为高风险问题。

讲解重点：

```text
这个案例更接近普通业务代码：语法没有问题，基础合规也通过，但测试揭示了跨模块业务逻辑错误。
```

### 用例 5D：自定义测试命令

这个用例不依赖大模型，适合展示“项目测试命名不标准时仍然可以接入”。

运行命令：

```bash
.venv/bin/python run.py \
  --input examples/python_custom_command/project.json
```

这个项目的测试文件叫 `check_palindrome.py`，不是默认会被识别的 `test_*.py`。

预期展示点：

- `config.test_command` 指定了测试发现方式。
- `test_result.test_results[0].test_mode = command_test`
- `test_result.test_results[0].oracle_source = command`
- `TestAgent.status = passed`

讲解重点：

```text
如果接入现有仓库时测试命令比较特殊，可以由后端把项目自己的测试命令放进 Project JSON，不要求所有项目都改成统一测试文件名。
```

## 4. API 演示用例

### 4.1 启动 FastAPI 服务

本机演示：

```bash
.venv/bin/python -m uvicorn tcr_agent.api:app \
  --host 127.0.0.1 \
  --port 8010
```

公司内网联调演示：

```bash
.venv/bin/python -m uvicorn tcr_agent.api:app \
  --host 0.0.0.0 \
  --port 8010
```

访问文档：

```text
http://127.0.0.1:8010/docs
```

如果是内网联调，将 `127.0.0.1` 替换为你的内网 IP：

```text
http://你的内网IP:8010/docs
```

### 用例 6：API 稳定演示，上传源码和测试文件

这个用例不依赖 LLM，适合现场演示 API 闭环。

创建任务：

```bash
curl -s -X POST "http://127.0.0.1:8010/runs" \
  -F "files=@examples/python_bug/main.py" \
  -F "files=@examples/python_bug/test_main.py" \
  -F "ai_review=false" \
  -F "llm_generate_tests=false" \
  -F "report_use_llm=false" \
  -F "auto_fix=false"
```

预期响应：

```json
{
  "run_id": "run_xxx",
  "status": "queued",
  "links": {
    "self": "/runs/run_xxx",
    "report": "/runs/run_xxx/report",
    "patch": "/runs/run_xxx/diff.patch",
    "fixed_files": "/runs/run_xxx/fixed-files"
  }
}
```

查询状态：

```bash
curl -s "http://127.0.0.1:8010/runs/{run_id}"
```

预期展示点：

- `status` 从 `queued/running` 变为 `completed`。
- `steps` 展示四个 Agent 的状态。
- `summary` 展示报告摘要。
- `result.report_result.issues` 展示结构化问题。

获取报告：

```bash
curl -s "http://127.0.0.1:8010/runs/{run_id}/report"
```

获取 patch：

```bash
curl -s "http://127.0.0.1:8010/runs/{run_id}/diff.patch"
```

获取修复文件 JSON：

```bash
curl -s "http://127.0.0.1:8010/runs/{run_id}/fixed-files"
```

### 用例 7：API 全能力演示，启用 AI 审查、LLM 自测和自动修复

这个用例需要 LLM 网关可用。

```bash
curl -s -X POST "http://127.0.0.1:8010/runs" \
  -F "files=@examples/python_no_tests/order_pricing.py" \
  -F "requirement=订单发票计算只统计 active=true 的商品，优惠后金额计税，返回 subtotal、discount、tax、total、item_count" \
  -F "ai_review=true" \
  -F "llm_generate_tests=true" \
  -F "report_use_llm=true" \
  -F "auto_fix=true" \
  -F "fix_target_severities=critical,high,medium"
```

预期展示点：

- 没有用户测试文件时，LLMTestGenerationAgent 会尝试生成测试。
- TestAgent 会执行生成测试和合规检查。
- ReportAgent 会生成结构化报告。
- FixAgent 会尝试在沙箱中修复并产出 patch / fixed_files。

## 5. 推荐现场演示顺序

建议总时长控制在 10 到 15 分钟。

### 第一步：讲现状

可以这样说：

```text
当前 Agent 核心链路已经完成第一版，包含测试生成、测试执行、代码审查、报告生成和沙箱修复。今天展示两个入口：CLI 独立运行入口，以及 FastAPI 服务化入口。
```

### 第二步：跑 CLI 稳定用例

运行：

```bash
.venv/bin/python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --no-report-llm
```

讲解重点：

```text
这个例子里代码语法是通过的，但测试失败，说明 Agent 能区分语法问题和功能逻辑问题，并生成结构化报告。
```

### 第三步：展示 FastAPI 文档

启动服务后打开：

```text
http://127.0.0.1:8010/docs
```

讲解重点：

```text
这说明当前 Agent 已经不是只能命令行运行，而是可以通过 HTTP API 被前端或 Java 后端调用。
```

### 第四步：跑 API 上传和轮询

创建任务：

```bash
curl -s -X POST "http://127.0.0.1:8010/runs" \
  -F "files=@examples/python_bug/main.py" \
  -F "files=@examples/python_bug/test_main.py" \
  -F "ai_review=false" \
  -F "llm_generate_tests=false" \
  -F "report_use_llm=false" \
  -F "auto_fix=false"
```

然后查询：

```bash
curl -s "http://127.0.0.1:8010/runs/{run_id}"
curl -s "http://127.0.0.1:8010/runs/{run_id}/report"
```

讲解重点：

```text
Java 或前端只需要按这个异步任务模型对接：创建任务、轮询状态、取报告、下载产物。
```

### 第五步：说明增强能力和边界

可以这样说：

```text
如果 LLM 网关可用，我们还能演示 AI 审查、LLM 生成测试和自动修复。当前自动修复只写入沙箱，不覆盖原始代码；下载修复后文件的一键接口还在方案中，短期可以通过 fixed-files 或 patch 获取产物。
```

## 6. 给 Java 同事的对接提示

Java 同事需要关注的是 API 入口：

```http
POST /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/report
GET  /runs/{run_id}/diff.patch
GET  /runs/{run_id}/fixed-files
```

Java 可以先做本地 BFF：

```text
POST /api/tcr/runs
GET  /api/tcr/runs/{runId}
GET  /api/tcr/runs/{runId}/report
GET  /api/tcr/runs/{runId}/download
```

短期不依赖数据库：

- 用内存 Map 记录本地任务。
- 或用 H2 / SQLite / JSON 文件。
- 下载接口先基于 `/fixed-files` 聚合。

## 7. 给前端同事的对接提示

前端最小页面只需要：

- 上传文件。
- 填写需求说明。
- 调创建任务接口。
- 每 2 到 5 秒轮询状态。
- 展示 `summary`、`risk_level`、`issues`。
- 展示下载 patch / 修复文件按钮。

前端状态流：

```text
idle -> uploading -> queued -> running -> completed / failed
```

## 8. 演示风险与兜底

| 风险 | 兜底 |
|---|---|
| LLM 网关不可用 | 只演示不依赖 LLM 的稳定用例。 |
| 内网访问不通 | 本机 `127.0.0.1` 演示 API 文档和 curl。 |
| 自动修复不稳定 | 只展示 patch / fixed-files 的能力边界。 |
| 前端 Demo 尚未接好 | 用 FastAPI `/docs` 和 curl 证明服务接口可用。 |
| Java BFF 尚未完成 | 说明 Java 只需按 API 文档代理，Agent 已可独立提供服务。 |
