"""Small loyalty points example with 3 intentional logic bugs."""
from __future__ import annotations

from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class Order:
    order_id: str
    amount: float
    channel: str = "web"
    refunded: bool = False
    days_ago: int = 0


TIER_MULTIPLIERS = {"basic": 1.0, "plus": 1.25, "vip": 1.4}
CHANNEL_BONUS = {"web": 0.0, "store": 0.0, "app": 0.10}


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def validate_orders(orders: list[Order], tier: str) -> None:
    if tier not in TIER_MULTIPLIERS:
        raise ValueError(f"unsupported tier: {tier}")
    if not orders:
        raise ValueError("orders must not be empty")
    seen_ids: set[str] = set()
    for order in orders:
        if not order.order_id.strip():
            raise ValueError("order_id is required")
        if order.order_id in seen_ids:
            raise ValueError(f"duplicate order_id: {order.order_id}")
        if order.amount < 0:
            raise ValueError(f"amount must be non-negative: {order.order_id}")
        if order.days_ago < 0:
            raise ValueError(f"days_ago must be non-negative: {order.order_id}")
        if order.channel not in CHANNEL_BONUS:
            raise ValueError(f"unsupported channel: {order.channel}")
        seen_ids.add(order.order_id)


def eligible_orders(orders: list[Order]) -> list[Order]:
    return list(orders)


def channel_bonus_points(orders: list[Order]) -> int:
    bonus = 0.0
    for order in orders:
        bonus += order.amount * CHANNEL_BONUS[order.channel]
    return floor(bonus)


def recent_bonus(orders: list[Order], eligible_amount: float) -> int:
    has_recent = any(order.days_ago < 7 for order in orders)
    return 100 if has_recent and eligible_amount >= 200 else 0


def calculate_loyalty_points(orders: list[Order], tier: str = "basic") -> dict[str, float | int]:
    """Calculate loyalty points according to requirement.txt."""
    validate_orders(orders, tier)
    eligible = eligible_orders(orders)
    eligible_amount = money(sum(order.amount for order in eligible))
    base_points = floor(eligible_amount * TIER_MULTIPLIERS[tier])
    bonus_points = channel_bonus_points(eligible) + recent_bonus(eligible, eligible_amount)
    total_points = min(5000, base_points + bonus_points)
    return {
        "eligible_amount": eligible_amount,
        "base_points": base_points,
        "bonus_points": bonus_points,
        "total_points": total_points,
        "order_count": len(eligible),
    }


if __name__ == "__main__":
    demo = [Order("o1", 120, "app", days_ago=7), Order("o2", 99, refunded=True)]
    print(calculate_loyalty_points(demo, tier="vip"))
