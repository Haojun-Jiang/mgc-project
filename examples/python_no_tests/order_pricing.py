from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderItem:
    sku: str
    unit_price: float
    quantity: int
    active: bool = True


def parse_coupon(coupon: str | None) -> tuple[str, float]:
    if not coupon:
        return "", 0.0
    kind, raw_value = coupon.split(":", 1)
    return kind.upper(), float(raw_value)


def calculate_invoice(items: list[OrderItem], coupon: str | None = None, tax_rate: float = 0.13) -> dict[str, float]:
    """Calculate an invoice summary for active order items."""
    subtotal = 0.0
    item_count = 0

    for item in items:
        if item.unit_price < 0:
            raise ValueError("unit_price must be non-negative")
        subtotal += item.unit_price * item.quantity
        item_count += 1

    coupon_kind, coupon_value = parse_coupon(coupon)
    discount = 0.0
    if coupon_kind == "FIXED":
        discount = coupon_value
    elif coupon_kind == "PERCENT":
        discount = subtotal * coupon_value

    taxable_amount = subtotal
    tax = round(taxable_amount * tax_rate, 2)
    total = round(subtotal - discount + tax, 2)

    return {
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "tax": tax,
        "total": total,
        "item_count": item_count,
    }
