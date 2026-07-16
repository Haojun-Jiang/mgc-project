"""约 150 行的 SaaS 订阅账单示例，内置 3 个业务缺陷用于联调。"""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Addon:
    code: str
    unit_price: float
    quantity: int = 1
    active: bool = True

@dataclass(frozen=True)
class Customer:
    customer_id: str
    customer_type: str = "standard"
    verified: bool = True

@dataclass(frozen=True)
class Coupon:
    code: str
    kind: str
    minimum_amount: float
    amount_off: float = 0.0
    percent_off: float = 0.0
    max_discount: float | None = None

PLANS = {
    "starter": {"price": 99.0, "included": 3, "extra_seat": 18.0},
    "pro": {"price": 299.0, "included": 10, "extra_seat": 25.0},
    "enterprise": {"price": 899.0, "included": 30, "extra_seat": 40.0},
}
CUSTOMER_DISCOUNTS = {"standard": 0.0, "startup": 0.10, "nonprofit": 0.15}
TAX_RATES = {"domestic": 0.06, "overseas": 0.0}
SENSITIVE_ADDONS = {"sso", "audit-log", "external-api"}

def money(value: float) -> float:
    return round(value + 1e-9, 2)

def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)

def validate_inputs(
    plan_code: str,
    seats: int,
    addons: list[Addon],
    customer: Customer,
    billing_cycle: str,
    coupon: Coupon | None,
    region: str,
) -> None:
    check(plan_code in PLANS, f"unsupported plan_code: {plan_code}")
    check(seats > 0, "seats must be positive")
    check(billing_cycle in {"monthly", "annual"}, f"unsupported billing_cycle: {billing_cycle}")
    check(region in TAX_RATES, f"unsupported region: {region}")
    check(bool(customer.customer_id.strip()), "customer_id is required")
    check(customer.customer_type in CUSTOMER_DISCOUNTS, f"unsupported customer_type: {customer.customer_type}")

    seen_addons: set[str] = set()
    for addon in addons:
        check(bool(addon.code.strip()), "addon code is required")
        check(addon.code not in seen_addons, f"duplicate addon code: {addon.code}")
        check(addon.unit_price >= 0, f"addon unit_price must be non-negative: {addon.code}")
        check(addon.quantity > 0, f"addon quantity must be positive: {addon.code}")
        seen_addons.add(addon.code)

    if coupon is None:
        return
    check(coupon.minimum_amount >= 0, "coupon minimum_amount must be non-negative")
    check(coupon.kind in {"fixed", "percent"}, f"unsupported coupon kind: {coupon.kind}")
    if coupon.kind == "fixed":
        check(coupon.amount_off >= 0, "coupon amount_off must be non-negative")
    else:
        check(0 <= coupon.percent_off <= 1, "coupon percent_off must be between 0 and 1")
        if coupon.max_discount is not None:
            check(coupon.max_discount >= 0, "coupon max_discount must be non-negative")


def billing_months(billing_cycle: str) -> int:
    return 11 if billing_cycle == "annual" else 1


def billable_addons(addons: list[Addon]) -> list[Addon]:
    return list(addons)


def coupon_discount(amount: float, coupon: Coupon | None) -> float:
    if coupon is None or amount <= coupon.minimum_amount:
        return 0.0
    if coupon.kind == "fixed":
        return money(min(amount, coupon.amount_off))
    cap = coupon.max_discount if coupon.max_discount is not None else amount
    return money(min(amount * coupon.percent_off, cap))


def calculate_subscription_invoice(
    plan_code: str,
    seats: int,
    addons: list[Addon],
    customer: Customer,
    billing_cycle: str = "monthly",
    coupon: Coupon | None = None,
    region: str = "domestic",
) -> dict[str, object]:
    """Calculate a SaaS subscription invoice according to requirement.txt."""
    validate_inputs(plan_code, seats, addons, customer, billing_cycle, coupon, region)
    months = billing_months(billing_cycle)
    active_addons = billable_addons(addons)
    plan = PLANS[plan_code]

    extra_seats = max(0, seats - int(plan["included"]))
    monthly_plan_amount = float(plan["price"]) + extra_seats * float(plan["extra_seat"])
    plan_amount = money(monthly_plan_amount * months)
    addon_amount = money(sum(addon.unit_price * addon.quantity * months for addon in active_addons))
    subtotal = money(plan_amount + addon_amount)

    customer_discount = money(subtotal * CUSTOMER_DISCOUNTS[customer.customer_type])
    after_customer_discount = money(subtotal - customer_discount)
    coupon_amount = coupon_discount(after_customer_discount, coupon)
    taxable_amount = money(after_customer_discount - coupon_amount)
    tax = money(taxable_amount * TAX_RATES[region])
    total = money(taxable_amount + tax)

    flags: list[str] = []
    if not customer.verified:
        flags.append("unverified_customer")
    if seats > int(plan["included"]) * 3:
        flags.append("large_seat_expansion")
    if any(addon.code in SENSITIVE_ADDONS for addon in active_addons):
        flags.append("sensitive_addon_enabled")
    if total > 10000:
        flags.append("high_value_subscription")

    return {
        "plan_subtotal": plan_amount,
        "addon_subtotal": addon_amount,
        "customer_discount": customer_discount,
        "coupon_discount": coupon_amount,
        "tax": tax,
        "total": total,
        "risk_flags": flags,
        "billable_addon_count": len(active_addons),
    }

if __name__ == "__main__":
    demo_addons = [Addon("sso", 80.0), Addon("audit-log", 120.0), Addon("legacy-support", 200.0, active=False)]
    demo_customer = Customer("cust-1001", customer_type="startup", verified=False)
    demo_coupon = Coupon("ANNUAL500", "fixed", minimum_amount=3000.0, amount_off=500.0)
    print(calculate_subscription_invoice("pro", 18, demo_addons, demo_customer, "annual", demo_coupon))
