import csv

_ITEMS = {}


def reset():
    _ITEMS.clear()


def add_item(sku, name, quantity=0, retired=False):
    _ITEMS[sku] = {"sku": sku, "name": name, "quantity": quantity, "retired": retired}


def list_items():
    return [i for i in _ITEMS.values() if not i["retired"]]


def export_csv(path, include_retired=False):
    rows = sorted((i for i in _ITEMS.values() if include_retired or not i["retired"]), key=lambda i: i["sku"])
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sku", "name", "quantity"])
        writer.writerows([i["sku"], i["name"], i["quantity"]] for i in rows)
    return len(rows)
