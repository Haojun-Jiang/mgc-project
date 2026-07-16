from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Region = Literal["domestic", "remote", "international"]
MemberTier = Literal["regular", "silver", "gold", "platinum"]
CouponKind = Literal["fixed", "percent"]


@dataclass(frozen=True)
class CartItem:
    sku: str
    name: str
    category: str
    unit_price: float
    quantity: int
    active: bool = True
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CustomerProfile:
    customer_id: str
    member_tier: MemberTier = "regular"
    total_orders: int = 0
    blocked: bool = False


@dataclass(frozen=True)
class Coupon:
    code: str
    kind: CouponKind
    minimum_amount: float
    amount_off: float = 0.0
    percent_off: float = 0.0
    max_discount: float | None = None


@dataclass(frozen=True)
class CheckoutSummary:
    subtotal: float
    promotion_discount: float
    member_discount: float
    coupon_discount: float
    shipping_fee: float
    tax: float
    total: float
    risk_flags: list[str]
    line_count: int


CATEGORY_PROMOTIONS = {
    "groceries": {"threshold": 200.0, "rate": 0.05},
    "electronics": {"threshold": 1000.0, "rate": 0.08},
}

MEMBER_DISCOUNTS: dict[MemberTier, float] = {
    "regular": 0.0,
    "silver": 0.03,
    "gold": 0.08,
    "platinum": 0.10,
}

SHIPPING_RULES: dict[Region, dict[str, float | None]] = {
    "domestic": {"base_fee": 12.0, "free_threshold": 300.0},
    "remote": {"base_fee": 35.0, "free_threshold": 800.0},
    "international": {"base_fee": 95.0, "free_threshold": None},
}

TAX_RATES: dict[Region, float] = {
    "domestic": 0.06,
    "remote": 0.04,
    "international": 0.0,
}


def money(value: float) -> float:
    """Round money values in one place to keep the public result stable."""
    return round(value + 1e-9, 2)


def normalize_region(region: str) -> Region:
    normalized = region.strip().lower().replace("_", "-")
    aliases = {
        "cn": "domestic",
        "china": "domestic",
        "domestic": "domestic",
        "remote": "remote",
        "cn-remote": "remote",
        "international": "international",
        "intl": "international",
        "overseas": "international",
    }
    if normalized not in aliases:
        raise ValueError(f"unsupported destination region: {region}")
    return aliases[normalized]  # type: ignore[return-value]


def validate_customer(customer: CustomerProfile) -> None:
    if not customer.customer_id.strip():
        raise ValueError("customer_id is required")
    if customer.blocked:
        raise ValueError("blocked customer cannot checkout")
    if customer.total_orders < 0:
        raise ValueError("total_orders must be non-negative")


def validate_items(items: list[CartItem]) -> None:
    if not items:
        raise ValueError("cart must contain at least one item")

    seen_skus: set[str] = set()
    for item in items:
        if not item.sku.strip():
            raise ValueError("sku is required")
        if item.sku in seen_skus:
            raise ValueError(f"duplicate sku: {item.sku}")
        seen_skus.add(item.sku)
        if item.unit_price < 0:
            raise ValueError(f"unit_price must be non-negative: {item.sku}")
        if item.quantity <= 0:
            raise ValueError(f"quantity must be positive: {item.sku}")


def eligible_items(items: list[CartItem]) -> list[CartItem]:
    return [item for item in items]


def line_subtotal(item: CartItem) -> float:
    return item.unit_price * item.quantity


def category_subtotals(items: list[CartItem]) -> dict[str, float]:
    subtotals: dict[str, float] = {}
    for item in items:
        subtotals[item.category] = subtotals.get(item.category, 0.0) + line_subtotal(item)
    return subtotals


def category_quantities(items: list[CartItem]) -> dict[str, int]:
    quantities: dict[str, int] = {}
    for item in items:
        quantities[item.category] = quantities.get(item.category, 0) + item.quantity
    return quantities


def calculate_promotion_discount(items: list[CartItem]) -> float:
    subtotals = category_subtotals(items)
    quantities = category_quantities(items)
    discount = 0.0

    for category, rule in CATEGORY_PROMOTIONS.items():
        category_total = subtotals.get(category, 0.0)
        if category_total >= rule["threshold"]:
            discount += category_total * rule["rate"]

    if quantities.get("books", 0) >= 3:
        discount += subtotals.get("books", 0.0) * 0.10

    return money(discount)


def calculate_member_discount(amount_after_promotions: float, tier: MemberTier) -> float:
    if tier not in MEMBER_DISCOUNTS:
        raise ValueError(f"unsupported member tier: {tier}")
    return money(amount_after_promotions * MEMBER_DISCOUNTS[tier])


def validate_coupon(coupon: Coupon | None) -> None:
    if coupon is None:
        return
    if coupon.minimum_amount < 0:
        raise ValueError("coupon minimum_amount must be non-negative")
    if coupon.kind == "fixed":
        if coupon.amount_off < 0:
            raise ValueError("coupon amount_off must be non-negative")
    elif coupon.kind == "percent":
        if coupon.percent_off < 0 or coupon.percent_off > 1:
            raise ValueError("coupon percent_off must be between 0 and 1")
        if coupon.max_discount is not None and coupon.max_discount < 0:
            raise ValueError("coupon max_discount must be non-negative")
    else:
        raise ValueError(f"unsupported coupon kind: {coupon.kind}")


def calculate_coupon_discount(subtotal_after_member: float, coupon: Coupon | None) -> float:
    if coupon is None:
        return 0.0

    if subtotal_after_member > coupon.minimum_amount:
        if coupon.kind == "fixed":
            return money(min(subtotal_after_member, coupon.amount_off))

        cap = coupon.max_discount if coupon.max_discount is not None else subtotal_after_member
        return money(min(subtotal_after_member * coupon.percent_off, cap))

    return 0.0


def calculate_shipping_fee(region: Region, merchandise_after_coupon: float) -> float:
    rule = SHIPPING_RULES[region]
    free_threshold = rule["free_threshold"]
    if free_threshold is not None and merchandise_after_coupon >= free_threshold:
        return 0.0
    return money(float(rule["base_fee"]))


def calculate_tax(region: Region, taxable_amount: float) -> float:
    return money(taxable_amount * TAX_RATES[region])


def build_risk_flags(
    *,
    items: list[CartItem],
    customer: CustomerProfile,
    coupon: Coupon | None,
    merchandise_after_coupon: float,
    total: float,
) -> list[str]:
    flags: list[str] = []

    if total > 3000:
        flags.append("high_value_order")
    if any("fragile" in item.tags for item in items):
        flags.append("contains_fragile_item")
    if customer.total_orders == 0 and merchandise_after_coupon > 500:
        flags.append("first_time_large_order")
    if coupon is not None and customer.member_tier == "platinum":
        flags.append("manual_review_for_vip_coupon")

    return flags


def calculate_checkout(
    items: list[CartItem],
    customer: CustomerProfile,
    coupon: Coupon | None = None,
    destination_region: str = "domestic",
) -> dict[str, float | int | list[str]]:
    """Calculate the checkout result according to the module-level rules."""
    validate_customer(customer)
    validate_items(items)
    validate_coupon(coupon)

    region = normalize_region(destination_region)
    active_items = eligible_items(items)
    if not active_items:
        raise ValueError("cart must contain at least one active item")

    subtotal = money(sum(line_subtotal(item) for item in active_items))
    promotion_discount = calculate_promotion_discount(active_items)
    after_promotions = money(subtotal - promotion_discount)

    member_discount = calculate_member_discount(after_promotions, customer.member_tier)
    after_member = money(after_promotions - member_discount)

    coupon_discount = calculate_coupon_discount(after_member, coupon)
    merchandise_after_coupon = money(after_member - coupon_discount)

    shipping_fee = calculate_shipping_fee(region, merchandise_after_coupon)
    tax = calculate_tax(region, merchandise_after_coupon + shipping_fee)
    total = money(merchandise_after_coupon + shipping_fee + tax)

    summary = CheckoutSummary(
        subtotal=subtotal,
        promotion_discount=promotion_discount,
        member_discount=member_discount,
        coupon_discount=coupon_discount,
        shipping_fee=shipping_fee,
        tax=tax,
        total=total,
        risk_flags=build_risk_flags(
            items=active_items,
            customer=customer,
            coupon=coupon,
            merchandise_after_coupon=merchandise_after_coupon,
            total=total,
        ),
        line_count=len(active_items),
    )
    return asdict(summary)


if __name__ == "__main__":
    demo_items = [
        CartItem("sku-001", "rice pack", "groceries", 88.0, 2),
        CartItem("sku-002", "monitor", "electronics", 1099.0, 1, tags=("fragile",)),
        CartItem("sku-003", "novel set", "books", 45.0, 3),
        CartItem("sku-004", "inactive warranty", "services", 499.0, 1, active=False),
    ]
    demo_customer = CustomerProfile("cust-001", member_tier="platinum", total_orders=0)
    demo_coupon = Coupon("WELCOME100", kind="fixed", minimum_amount=1000.0, amount_off=100.0)
    print(calculate_checkout(demo_items, demo_customer, demo_coupon, "domestic"))
