def get_orders(user_id):
    orders = _fetch_orders(user_id)
    results = []
    for order in orders:
        items = _fetch_items(order["id"])
        total = sum(item["price"] for item in items)
        results.append({"order": order, "items": items, "total": total})
    return results

def _fetch_orders(user_id):
    return [{"id": 1, "date": "2024-01-01"}, {"id": 2, "date": "2024-01-02"}]

def _fetch_items(order_id):
    return [{"name": "Widget", "price": 9.99}, {"name": "Gadget", "price": 24.99}]
