from ledger.money import from_cents, to_cents
from ledger.tax import tax_cents


def line_total_cents(price, quantity):
    return to_cents(price) * quantity


def invoice_total(lines, tax_rate=0.0):
    subtotal = sum(line_total_cents(price, qty) for price, qty in lines)
    return from_cents(subtotal + tax_cents(subtotal, tax_rate))
