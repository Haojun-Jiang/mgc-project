"""用于手动验证 TCR Agent 测试生成能力的示例代码。

业务规则：
1. 只统计 active=True 的商品。
2. 商品单价和数量不能为负数。
3. 满 100 元打 9 折。
4. 最终金额保留两位小数。

文件中故意保留了一个逻辑错误，便于验证 Agent 能否生成测试并发现问题。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Product:
    name: str
    price: float
    quantity: int
    active: bool = True


def calculate_total(products: list[Product]) -> float:
    """按照模块顶部的业务规则计算订单总金额。"""
    subtotal = 0.0

    for product in products:
        if product.price < 0:
            raise ValueError("price must be non-negative")
        if product.quantity < 0:
            raise ValueError("quantity must be non-negative")

        # 故意遗漏 active 状态判断，测试应当能够发现这个问题。
        subtotal += product.price * product.quantity

    if subtotal >= 100:
        subtotal *= 0.9

    return round(subtotal, 2)


if __name__ == "__main__":
    demo_products = [
        Product("keyboard", 80.0, 1),
        Product("mouse", 30.0, 1),
        Product("disabled item", 999.0, 1, active=False),
    ]
    print(calculate_total(demo_products))
