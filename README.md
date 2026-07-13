# TCR Agent Prototype

TCR Agent 是一个“测试-合规-纠正”智能体原型。目前已完成第一版测试、报告和沙箱修复链路：

```text
代码输入
  -> TestAgent: 运行测试、语法/合规检查、可选 AI 代码审查
  -> ReportAgent: 汇总测试/合规/AI 审查结果并生成结构化报告
  -> FixAgent: 根据报告生成修复并应用到临时沙箱
```

当前 LangGraph 流程：

```text
START -> TestAgent -> ReportAgent -> FixAgent -> END
```

## 已实现功能

- `TestAgent`
  - 将输入代码写入临时沙箱目录。
  - 自动运行 Python 测试，优先使用 `pytest`，否则回退到 `unittest`。
  - 没有用户测试时，可选让 LLM 生成 pytest 测试并在沙箱中真实执行。
  - 执行 `py_compile` 语法/合规检查。
  - 可选调用大模型做 AI 代码审查，结果作为 `llm_review` 合规检查输出。

- `ReportAgent`
  - 读取 `TestAgent` 的测试失败、合规问题、AI 审查问题。
  - 生成统一的 `issues` 报告。
  - 可选再次调用大模型，对报告进行摘要、归因和修复建议增强。

- `FixAgent`
  - 根据 `ReportAgent` 的 `issues` 筛选需要修复的问题。
  - 可选调用大模型生成修复后的完整文件内容。
  - 只在 `TestAgent` 创建的临时 `workspace_dir` 中应用修改，不覆盖用户原始文件。
  - 本地生成 unified diff，写入 `fix_result.patches`。

- `LLMGateway`
  - 支持 OpenAI-compatible `/chat/completions` 接口。
  - 支持 DeepSeek 或公司内部兼容 OpenAI 格式的大模型网关。
  - 支持 `.env` 配置。

- 入口方式
  - 支持 Project JSON 输入。
  - 支持直接传入现成 `.py` 源码文件和测试文件。
  - 支持根目录 `run.py` 一键启动。

## 项目结构

```text
.
  run.py                              根目录启动入口
  requirements.txt                    运行依赖
  .env.example                        LLM 网关配置模板
  examples/python_bug/
    main.py                           示例源码，故意包含 bug
    test_main.py                      示例测试
    project.json                      JSON 输入示例
    project_ai_review.json            开启 AI 审查的 JSON 输入示例
    project_llm_generated_tests.json  开启 LLM 自测的 JSON 输入示例
  src/tcr_agent/
    cli.py                            CLI 参数解析
    graph.py                          LangGraph 编排
    schemas.py                        Agent 输入输出字段定义
    tools.py                          本地沙箱、测试和合规工具
    llm_gateway.py                    大模型网关
    agents/test_agent.py              TestAgent
    agents/report_agent.py            ReportAgent
    agents/ai_code_review.py          AI 代码审查检查项
    agents/llm_test_generation.py     LLM 测试生成
    agents/fix_agent.py               FixAgent
    templates/ai_code_review_system.md AI 审查 prompt 模板
    templates/llm_test_generation_system.md LLM 自测 prompt 模板
    templates/fix_agent_system.md      修复 prompt 模板
```

## 环境安装

推荐 Python 3.12。

```bash
cd "/Users/jianghj59/Documents/mgc project"

python3.12 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install -e ".[dev]"
```

如果已经有 `.venv`，直接激活即可：

```bash
source .venv/bin/activate
```

运行单元测试：

```bash
python -m unittest tests/test_test_agent.py tests/test_llm_gateway.py tests/test_report_agent.py tests/test_fix_agent.py
```

## LLM 网关配置

复制配置模板：

```bash
cp .env.example .env
```

示例配置：

```bash
LLM_GATEWAY_BASE_URL=https://api.deepseek.com
LLM_GATEWAY_API_KEY=your-api-key
LLM_GATEWAY_MODEL=deepseek-v4-pro
LLM_GATEWAY_TIMEOUT_SECONDS=60
LLM_GATEWAY_AUTH_HEADER=authorization
LLM_GATEWAY_VERIFY_SSL=true
LLM_GATEWAY_EXTRA_HEADERS_JSON={}
```

`LLM_GATEWAY_BASE_URL` 可以是：

```text
https://api.deepseek.com
https://api.deepseek.com/v1
https://your-company-gateway/v1
```

程序会自动拼接 `/chat/completions`。如果你的 URL 已经以 `/chat/completions` 结尾，也可以直接使用完整地址。

如果公司网络代理注入了自签名证书，可能会出现：

```text
CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain
```

临时测试可以设置：

```bash
LLM_GATEWAY_VERIFY_SSL=false
```

长期建议把公司 CA 证书安装到系统或 Python/OpenSSL 信任链中。

## 使用方法

### 1. 使用现成 JSON 输入

不启用 AI 审查：

```bash
python run.py --input examples/python_bug/project.json
```

启用 AI 审查：

```bash
python run.py --input examples/python_bug/project_ai_review.json
```

启用 LLM 自测：

```bash
python run.py --input examples/python_bug/project_llm_generated_tests.json
```

### 2. 直接传入 Python 源码和测试文件

只运行测试、合规检查和本地报告：

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --no-report-llm
```

运行完整代码审查任务：

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review
```

这个命令会执行：

```text
pytest 测试
py_compile 合规检查
llm_review AI 代码审查
ReportAgent LLM 报告增强
```

### 3. 启用 FixAgent 沙箱修复

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review \
  --fix \
  --no-report-llm
```

`--fix` 会设置 `auto_fix=true`。FixAgent 会调用大模型生成修复，并只修改输出中的临时 `workspace_dir` 文件。

### 4. 没有测试文件时启用 LLM 自测

```bash
python run.py \
  --code examples/python_bug/main.py \
  --llm-generate-tests \
  --requirement "add(a, b) 应返回 a 与 b 的和" \
  --no-report-llm
```

LLM 自测会执行：

```text
LLM 推断行为并生成 pytest 测试
写入 workspace/.tcr_generated_tests/test_generated_llm.py
运行 python -m pytest -q .tcr_generated_tests
将失败结果标记为 llm_generated_tests
```

这类测试的 `oracle_source` 是 `llm_inferred`，表示它来自 LLM 根据代码和需求推断出的测试假设，不等价于用户确认的验收标准。

### 5. 只调用一次大模型

如果你只想让 `TestAgent` 做 AI 代码审查，不想让 `ReportAgent` 再调用一次大模型：

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review \
  --no-report-llm
```

### 6. 保存结果

```bash
python run.py \
  --code examples/python_bug/main.py \
  --test examples/python_bug/test_main.py \
  --ai-review > full_review_result.json
```

## 示例测试用例

示例代码：

```python
def add(a, b):
    return a - b
```

示例测试：

```python
self.assertEqual(add(1, 2), 3)
```

预期结果：

- `pytest` 失败，因为实际结果是 `-1`。
- `py_compile` 通过，因为语法没有问题。
- 开启 `--ai-review` 后，`llm_review` 会识别 `return a - b` 是逻辑错误。
- `ReportAgent` 会汇总出来自 `pytest` 和 `llm_review` 的问题。

## 输出字段说明

最终输出是一个 JSON object，主要字段如下：

```text
test_result
  TestAgent 输出

test_result.test_results
  测试执行结果，例如 pytest/unittest

test_result.test_results[].test_mode
  测试策略，例如 command_test、user_test、llm_generated_test、static_only

test_result.test_results[].oracle_source
  测试 oracle 来源，例如 command、user_provided、llm_inferred、none

test_result.test_results[].generated_test_ref
  LLM 自测生成的测试文件路径

test_result.compliance_results
  合规检查结果，例如 py_compile、llm_review

report_result
  ReportAgent 输出

report_result.issues
  统一问题列表，包含 issue_id、source、severity、evidence、root_cause、recommendation

fix_result
  FixAgent 输出

fix_result.patches
  沙箱修复补丁，包含 file、issue_ids、diff、applied、error

report_result.warnings
  非致命告警，例如 LLM 调用失败后回退到本地报告
```

`llm_review` 的结果位于：

```text
test_result.compliance_results 中 tool = "llm_review" 的对象
```

如果 `llm_review.status = failed`，说明 AI 审查发现了 `critical` 或 `high` 问题。

如果 `report_result.llm_used = true`，说明 ReportAgent 成功调用了大模型做报告增强。

## 当前限制

- 目前主要支持 Python 文件。
- 当前只完成 `TestAgent -> ReportAgent -> FixAgent`，还未实现 `VerifyAgent` 复测闭环。
- FixAgent 第一版只修改临时沙箱文件，不会自动覆盖用户原始文件。
- AI 审查默认关闭，必须通过 `--ai-review` 或 JSON 配置显式开启。
- LLM 自测默认关闭，必须通过 `--llm-generate-tests` 或 JSON 配置显式开启。
- LLM 自测来自模型推断，报告会标记 `oracle_source=llm_inferred`，不能等同于用户提供的确定性验收测试。
- `ruff`、`semgrep` 目前仅预留为合规工具扩展点，MVP 中未完整实现。
