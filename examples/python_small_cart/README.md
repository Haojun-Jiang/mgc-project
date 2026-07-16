# Small Cart Example

快速前端联调用例。上传 `cart_pricing.py`，将 `requirement.txt` 复制到 Requirement。

内置 3 个业务缺陷：

- `active=False` 商品没有被过滤。
- `gold` 会员折扣写成了 8%，规则要求 10%。
- 优惠券门槛用了 `>`，规则要求金额 `>= minimum_amount` 时可用。
