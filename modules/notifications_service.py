"""Hot-reloadable notification policy and message formatting.

The background worker calls this module every poll. It never receives site credentials.
Update this file locally, or publish a new version through the server's dynamic-module panel.
"""
from __future__ import annotations

__version__ = "1.0.0"


def should_notify(event: dict, settings) -> bool:
    if event.get("type") == "out_of_stock":
        return bool(settings.out_of_stock)
    if event.get("type") == "new_orders":
        return bool(settings.new_orders)
    return False


def normalise_interval(seconds: int) -> int:
    return max(30, min(900, int(seconds or 60)))


def format_notification(event: dict, lang: str) -> dict:
    site = str(event.get("site_name") or event.get("site_id") or "")
    count = max(1, int(event.get("count") or 1))
    kind = event.get("type")

    if kind == "out_of_stock":
        products = event.get("products") or []
        if count == 1 and products:
            name = str(products[0].get("name") or "")
            return {
                "title": "اتمام موجودی" if lang == "fa" else "Out of stock",
                "body": f"{name} در {site} ناموجود شد." if lang == "fa" else f"{name} is now out of stock in {site}.",
                "kind": kind,
            }
        return {
            "title": "هشدار موجودی" if lang == "fa" else "Stock alert",
            "body": (f"{count} محصول در {site} ناموجود شدند." if lang == "fa"
                     else f"{count} products are now out of stock in {site}."),
            "kind": kind,
        }

    if kind == "new_orders":
        orders = event.get("orders") or []
        if count == 1 and orders:
            order = orders[0]
            number = str(order.get("number") or order.get("id") or "")
            total = " ".join(part for part in (str(order.get("total") or ""), str(order.get("currency") or "")) if part)
            if lang == "fa":
                body = f"سفارش #{number} در {site}" + (f" به مبلغ {total}" if total else "")
            else:
                body = f"Order #{number} in {site}" + (f" for {total}" if total else "")
            return {"title": "سفارش جدید" if lang == "fa" else "New order", "body": body, "kind": kind}
        return {
            "title": "سفارش‌های جدید" if lang == "fa" else "New orders",
            "body": (f"{count} سفارش جدید در {site} ثبت شد." if lang == "fa"
                     else f"{count} new orders were placed in {site}."),
            "kind": kind,
        }

    return {"title": "WooDesk", "body": site, "kind": str(kind or "info")}
