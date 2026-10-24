from __future__ import annotations

import html

from .state import cap_ids

STOCK_FIELDS = "id,name,sku,stock_quantity,stock_status,permalink"
ORDER_FIELDS = "id,number,status,total,currency,date_created"


def stock_snapshot(woo) -> list[dict]:
    items = woo.all_pages("/products", {"status": "publish", "stock_status": "outofstock", "_fields": STOCK_FIELDS}, max_pages=10)
    products = []
    for item in items:
        if item.get("stock_status") != "outofstock":
            continue
        products.append({
            "id": item.get("id"),
            "name": html.unescape(str(item.get("name") or "")).strip() or f"#{item.get('id')}",
            "sku": str(item.get("sku") or ""),
            "quantity": item.get("stock_quantity"),
            "url": str(item.get("permalink") or ""),
        })
    return [item for item in products if item["id"] is not None]


def orders_snapshot(woo, per_page: int = 100) -> list[dict]:
    items, _total, _pages = woo.page("/orders", {
        "per_page": min(max(per_page, 1), 100),
        "orderby": "date",
        "order": "desc",
        "_fields": ORDER_FIELDS,
    })
    orders = []
    for item in items:
        if item.get("id") is None:
            continue
        orders.append({
            "id": item["id"],
            "number": str(item.get("number") or item.get("id")),
            "status": str(item.get("status") or ""),
            "total": str(item.get("total") or ""),
            "currency": str(item.get("currency") or ""),
            "created": str(item.get("date_created") or ""),
        })
    return orders


def detect_stock(products: list[dict], current: dict, enabled: bool, was_active: bool, now: float) -> list[dict]:
    bucket = current.setdefault("stock", {})
    previous = set(cap_ids(bucket.get("ids", [])))
    current_ids = [int(item["id"]) for item in products]
    should_notify = bool(enabled and was_active and bucket.get("initialized"))
    events = []
    if should_notify:
        new_products = [item for item in products if int(item["id"]) not in previous]
        if new_products:
            events.append({
                "type": "out_of_stock",
                "count": len(new_products),
                "products": new_products[:8],
                "detected_at": int(now),
            })
    if enabled:
        bucket["ids"] = cap_ids(current_ids)
        bucket["initialized"] = True
        bucket["checked"] = int(now)
    return events


def detect_orders(orders: list[dict], current: dict, enabled: bool, was_active: bool, now: float) -> list[dict]:
    bucket = current.setdefault("orders", {})
    previous = set(cap_ids(bucket.get("ids", [])))
    current_ids = [int(item["id"]) for item in orders]
    should_notify = bool(enabled and was_active and bucket.get("initialized"))
    events = []
    if should_notify:
        new_orders = [item for item in orders if int(item["id"]) not in previous]
        if new_orders:
            events.append({
                "type": "new_orders",
                "count": len(new_orders),
                "orders": new_orders[:8],
                "detected_at": int(now),
            })
    if enabled:
        bucket["ids"] = cap_ids(list(previous) + current_ids)
        bucket["initialized"] = True
        bucket["checked"] = int(now)
    return events
