# Small Loyalty Example

快速前端联调用例。上传 `loyalty.py`，将 `requirement.txt` 复制到 Requirement。

内置 3 个业务缺陷：

- refunded=True 的订单没有被过滤。
- `vip` 积分倍率写成了 1.4，规则要求 1.5。
- 近 7 天奖励错误使用 `< 7`，规则要求 `<= 7`。
