# Complex Checkout Example

这个示例用于前端上传联调：`checkout.py` 是一个较长的单文件电商结算逻辑，包含分类促销、会员折扣、优惠券、运费、税费和风控标记。

文件中故意保留 3 个业务缺陷：

- `active=False` 商品没有被过滤掉。
- `platinum` 会员折扣写成了 10%，规则要求 15%。
- 优惠券门槛用了 `>`，规则要求金额 `>= minimum_amount` 时可用。

前端使用方式：

1. 上传 `checkout.py`。
2. 将 `requirement.txt` 的内容复制到 Requirement 输入框。
3. 开启测试生成、自动修复和验证流程。

本地命令示例：

```bash
.venv/bin/python run.py --code examples/python_complex_checkout/checkout.py --llm-generate-tests --fix --requirement "$(cat examples/python_complex_checkout/requirement.txt)"
```
