# Medium Subscription Example

这个示例用于常规前端联调：`subscription.py` 是一个中等体量的 SaaS 订阅账单计算模块，包含套餐、席位、附加功能、客户类型折扣、优惠券、税费和风控标记。

文件中故意保留 3 个业务缺陷：

- 年付应按 10 个月计费，代码错误按 11 个月计费。
- `active=False` 的附加功能没有被过滤掉。
- 优惠券门槛用了 `>`，规则要求金额 `>= minimum_amount` 时可用。

前端使用方式：

1. 上传 `subscription.py`。
2. 将 `requirement.txt` 的内容复制到 Requirement 输入框。
3. 开启测试生成、自动修复和验证流程。

本地命令示例：

```bash
.venv/bin/python run.py --code examples/python_medium_subscription/subscription.py --llm-generate-tests --fix --requirement "$(cat examples/python_medium_subscription/requirement.txt)"
```
