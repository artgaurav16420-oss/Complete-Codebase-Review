import sqlite3

_DB = sqlite3.connect(":memory:", check_same_thread=False)
_DB.execute("CREATE TABLE items (order_id INTEGER, name TEXT, price REAL)")
_DB.executemany(
    "INSERT INTO items VALUES (?, ?, ?)",
    [(1, "Widget", 9.99), (2, "Gadget", 24.99)],
)

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
    rows = _DB.execute(
        "SELECT name, price FROM items WHERE order_id = ?", (order_id,)
    ).fetchall()
    return [{"name": row[0], "price": row[1]} for row in rows]
