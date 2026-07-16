"""Small shopping cart pricing example with 3 intentional logic bugs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CartItem:
    sku: str
    price: float
    quantity: int
    active: bool = True


MEMBER_DISCOUNTS = {"regular": 0.0, "silver": 0.05, "gold": 0.08}
COUPONS = {
    "WELCOME10": {"kind": "fixed", "minimum": 50.0, "value": 10.0, "cap": None},
    "SAVE20": {"kind": "percent", "minimum": 100.0, "value": 0.20, "cap": 30.0},
}
TAX_RATES = {"domestic": 0.05, "overseas": 0.0}


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def validate_inputs(items: list[CartItem], member_level: str, coupon_code: str | None, region: str) -> None:
    if member_level not in MEMBER_DISCOUNTS:
        raise ValueError(f"unsupported member_level: {member_level}")
    if coupon_code is not None and coupon_code not in COUPONS:
        raise ValueError(f"unsupported coupon_code: {coupon_code}")
    if region not in TAX_RATES:
        raise ValueError(f"unsupported region: {region}")
    if not items:
        raise ValueError("cart must contain at least one item")
    for item in items:
        if not item.sku.strip():
            raise ValueError("sku is required")
        if item.price < 0:
            raise ValueError(f"price must be non-negative: {item.sku}")
        if item.quantity <= 0:
            raise ValueError(f"quantity must be positive: {item.sku}")


def billable_items(items: list[CartItem]) -> list[CartItem]:
    return list(items)


def calculate_coupon_discount(amount: float, coupon_code: str | None) -> float:
    if coupon_code is None:
        return 0.0
    coupon = COUPONS[coupon_code]
    if amount <= float(coupon["minimum"]):
        return 0.0
    if coupon["kind"] == "fixed":
        return money(min(amount, float(coupon["value"])))
    discount = amount * float(coupon["value"])
    cap = coupon["cap"]
    return money(min(discount, float(cap) if cap is not None else amount))


def calculate_cart_total(
    items: list[CartItem],
    member_level: str = "regular",
    coupon_code: str | None = None,
    region: str = "domestic",
) -> dict[str, float | int]:
    """Calculate cart total according to requirement.txt."""
    validate_inputs(items, member_level, coupon_code, region)
    active_items = billable_items(items)
    subtotal = money(sum(item.price * item.quantity for item in active_items))
    member_discount = money(subtotal * MEMBER_DISCOUNTS[member_level])
    after_member = money(subtotal - member_discount)
    coupon_discount = calculate_coupon_discount(after_member, coupon_code)
    taxable_amount = money(after_member - coupon_discount)
    tax = money(taxable_amount * TAX_RATES[region])
    return {
        "subtotal": subtotal,
        "member_discount": member_discount,
        "coupon_discount": coupon_discount,
        "tax": tax,
        "total": money(taxable_amount + tax),
        "item_count": sum(item.quantity for item in active_items),
    }


if __name__ == "__main__":
    demo = [CartItem("book", 50, 2), CartItem("warranty", 99, 1, active=False)]
    print(calculate_cart_total(demo, member_level="gold", coupon_code="SAVE20"))
