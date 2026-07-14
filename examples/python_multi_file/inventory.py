from discounts import apply_member_discount


def checkout_total(items, member=False):
    subtotal = 0.0
    for item in items:
        if not item.get("active", True):
            continue
        subtotal += item["price"]
    return apply_member_discount(subtotal, member)
