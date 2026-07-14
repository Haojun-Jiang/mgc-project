def apply_member_discount(amount, member):
    if not member:
        return round(amount, 2)
    return round(amount * 0.9, 2)
