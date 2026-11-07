_ITEMS = {}


def reset():
    _ITEMS.clear()


def add_item(sku, name, quantity=0, retired=False):
    _ITEMS[sku] = {"sku": sku, "name": name, "quantity": quantity, "retired": retired}


def list_items():
    return [i for i in _ITEMS.values() if not i["retired"]]
