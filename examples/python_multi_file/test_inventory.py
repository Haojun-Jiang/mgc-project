from inventory import checkout_total


def test_checkout_counts_quantities():
    items = [{"price": 10.0, "quantity": 3, "active": True}]
    assert checkout_total(items) == 30.0


def test_checkout_ignores_inactive_items():
    items = [
        {"price": 10.0, "quantity": 1, "active": True},
        {"price": 99.0, "quantity": 5, "active": False},
    ]
    assert checkout_total(items) == 10.0


def test_member_discount_after_full_subtotal():
    items = [{"price": 10.0, "quantity": 3, "active": True}]
    assert checkout_total(items, member=True) == 27.0
