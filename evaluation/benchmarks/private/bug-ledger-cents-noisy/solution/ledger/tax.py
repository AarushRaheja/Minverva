from decimal import ROUND_HALF_UP, Decimal


def tax_cents(subtotal_cents, rate):
    exact = Decimal(subtotal_cents) * Decimal(str(rate))
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))
