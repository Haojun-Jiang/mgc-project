# Small Inventory Example

快速前端联调用例。上传 `reorder.py`，将 `requirement.txt` 复制到 Requirement。

内置 3 个业务缺陷：

- `active=False` 商品没有被过滤。
- 可用库存计算漏掉了 `incoming`。
- 达到阈值时不应补货，代码错误使用了 `<=`。
