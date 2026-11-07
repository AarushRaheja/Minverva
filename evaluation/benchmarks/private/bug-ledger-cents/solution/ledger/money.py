def to_cents(amount):
    """Dollars as a float, converted to whole cents."""
    return int(round(amount * 100))


def from_cents(cents):
    return cents / 100
