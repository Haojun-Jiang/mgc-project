# Demo Examples

这些样例用于现场演示 TCR Agent 的不同路径。默认都可以不依赖 LLM 网关运行，除非特别说明。

| 目录 | 演示重点 | 预期结果 |
|---|---|---|
| `python_bug` | 单文件逻辑错误，用户测试失败 | `TestAgent.status = failed`，`risk_level = high` |
| `python_passing` | 全部测试通过的绿色路径 | `TestAgent.status = passed`，`risk_level = info` |
| `python_syntax_error` | 没有行为测试，仅静态语法检查失败 | `py_compile.status = failed`，报告生成合规问题 |
| `python_multi_file` | 多文件项目、跨模块导入、部分测试失败 | pytest 展示多个用例，报告聚合失败 |
| `python_custom_command` | 非 `test_*.py` 命名，通过自定义测试命令运行 | `test_mode = command_test` |
| `python_no_tests` | 无用户测试，由 LLM 生成测试和修复 | 需要 LLM 网关 |
| `python_small_cart` | 100 行以内购物车计价逻辑、内置 3 个业务缺陷 | 需要 LLM 网关，适合快速前端联调 |
| `python_small_inventory` | 100 行以内库存补货逻辑、内置 3 个业务缺陷 | 需要 LLM 网关，适合快速前端联调 |
| `python_small_loyalty` | 100 行以内会员积分逻辑、内置 3 个业务缺陷 | 需要 LLM 网关，适合快速前端联调 |
| `python_medium_subscription` | 中等体量订阅账单逻辑、无用户测试、内置 3 个业务缺陷 | 需要 LLM 网关，适合常规前端联调 |
| `python_complex_checkout` | 复杂单文件结算逻辑、无用户测试、内置 3 个业务缺陷 | 需要 LLM 网关，适合前端上传联调 |

常用命令：

```bash
.venv/bin/python run.py --input examples/python_passing/project.json
.venv/bin/python run.py --input examples/python_syntax_error/project.json
.venv/bin/python run.py --input examples/python_multi_file/project.json
.venv/bin/python run.py --input examples/python_custom_command/project.json
.venv/bin/python run.py --code examples/python_small_cart/cart_pricing.py --llm-generate-tests --fix --requirement "$(cat examples/python_small_cart/requirement.txt)"
.venv/bin/python run.py --code examples/python_small_inventory/reorder.py --llm-generate-tests --fix --requirement "$(cat examples/python_small_inventory/requirement.txt)"
.venv/bin/python run.py --code examples/python_small_loyalty/loyalty.py --llm-generate-tests --fix --requirement "$(cat examples/python_small_loyalty/requirement.txt)"
.venv/bin/python run.py --code examples/python_medium_subscription/subscription.py --llm-generate-tests --fix --requirement "$(cat examples/python_medium_subscription/requirement.txt)"
.venv/bin/python run.py --code examples/python_complex_checkout/checkout.py --llm-generate-tests --fix --requirement "$(cat examples/python_complex_checkout/requirement.txt)"
```
