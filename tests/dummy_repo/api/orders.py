def get_orders(user_id):
    orders = _fetch_orders(user_id)

    order_ids = [order["id"] for order in orders]
    items_by_order = _fetch_items_bulk(order_ids)

    results = []
    for order in orders:
        items = items_by_order.get(order["id"], [])
        total = sum(item["price"] for item in items)
        results.append({"order": order, "items": items, "total": total})
    return results

def _fetch_orders(user_id):
    return [{"id": 1, "date": "2024-01-01"}, {"id": 2, "date": "2024-01-02"}]

def _fetch_items(order_id):
    return [{"name": "Widget", "price": 9.99}, {"name": "Gadget", "price": 24.99}]

def _fetch_items_bulk(order_ids):
    # Dummy implementation for tests to work
    results = {}
    for order_id in order_ids:
        results[order_id] = _fetch_items(order_id)
    return results
