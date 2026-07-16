"""Small inventory reorder example with 3 intentional logic bugs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockItem:
    sku: str
    on_hand: int
    reserved: int
    incoming: int
    min_stock: int
    target_stock: int
    safety_stock: int = 0
    active: bool = True
    critical: bool = False
    lead_time_days: int = 3


def validate_item(item: StockItem) -> None:
    if not item.sku.strip():
        raise ValueError("sku is required")
    values = {
        "on_hand": item.on_hand,
        "reserved": item.reserved,
        "incoming": item.incoming,
        "min_stock": item.min_stock,
        "target_stock": item.target_stock,
        "safety_stock": item.safety_stock,
        "lead_time_days": item.lead_time_days,
    }
    for name, value in values.items():
        if value < 0:
            raise ValueError(f"{name} must be non-negative: {item.sku}")
    if item.target_stock < item.min_stock:
        raise ValueError(f"target_stock must be >= min_stock: {item.sku}")


def active_items(items: list[StockItem]) -> list[StockItem]:
    return list(items)


def available_stock(item: StockItem) -> int:
    return item.on_hand - item.reserved


def priority_for(item: StockItem) -> str:
    return "high" if item.critical or item.lead_time_days > 7 else "normal"


def plan_reorders(items: list[StockItem]) -> list[dict[str, int | str]]:
    """Build reorder recommendations according to requirement.txt."""
    if not items:
        raise ValueError("items must not be empty")
    seen_skus: set[str] = set()
    for item in items:
        validate_item(item)
        if item.sku in seen_skus:
            raise ValueError(f"duplicate sku: {item.sku}")
        seen_skus.add(item.sku)

    recommendations: list[dict[str, int | str]] = []
    for item in active_items(items):
        available = available_stock(item)
        threshold = item.min_stock + item.safety_stock
        if available <= threshold:
            recommendations.append(
                {
                    "sku": item.sku,
                    "available": available,
                    "order_quantity": max(0, item.target_stock - available),
                    "priority": priority_for(item),
                }
            )
    return sorted(recommendations, key=lambda row: str(row["sku"]))


if __name__ == "__main__":
    demo = [
        StockItem("A-100", 5, 1, 10, 8, 20),
        StockItem("B-200", 2, 0, 0, 5, 15, active=False),
    ]
    print(plan_reorders(demo))
