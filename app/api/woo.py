from __future__ import annotations

import itertools

from .http import RestBase, run_parallel


# The product list only needs these fields. Asking for them (instead of the whole product, which can
# carry 10-20 KB of SEO/_links/meta data each) makes list loading several times faster.
LIST_FIELDS = ("id,name,slug,type,status,sku,price,regular_price,sale_price,manage_stock,stock_quantity,"
               "stock_status,categories,images,description,short_description")


class WooClient(RestBase):
    """WooCommerce REST v3. Auth: consumer key/secret, or a WP user + application password."""

    tags_path = "/products/tags"

    def __init__(self, base_url: str, key: str = "", secret: str = "", wp_user: str = "", wp_password: str = "", client=None):
        if key:
            auth = (key.strip(), secret.strip())
        else:
            auth = (wp_user, (wp_password or "").strip())
        super().__init__(base_url, auth, "/wc/v3", client)

    def ping(self) -> int:
        _d, total, _p = self.page("/products", {"per_page": 1})
        return total

    # ---- products ------------------------------------------------------
    def products(self, page=1, per_page=20, search="", status="any", category=None,
                 stock_status="", ptype="", orderby="date", order="desc"):
        params = {"page": page, "per_page": per_page, "status": status, "orderby": orderby, "order": order,
                  "_fields": LIST_FIELDS}
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        if stock_status:
            params["stock_status"] = stock_status
        if ptype:
            params["type"] = ptype
        return self.page("/products", params)

    def product(self, pid: int) -> dict:
        return self.json("GET", f"/products/{pid}")

    def save_product(self, pid: int | None, data: dict) -> dict:
        if pid:
            return self.json("PUT", f"/products/{pid}", json=data)
        return self.json("POST", "/products", json=data)

    def delete_product(self, pid: int, force: bool = False) -> dict:
        return self.json("DELETE", f"/products/{pid}", params={"force": "true" if force else "false"})

    def batch_products(self, create=None, update=None, delete=None) -> dict:
        """Chunked batch call (WooCommerce allows 100 operations per request)."""
        return self._batch("/products/batch", create, update, delete)

    def _batch(self, path: str, create=None, update=None, delete=None) -> dict:
        create, update, delete = list(create or []), list(update or []), list(delete or [])
        result = {"create": [], "update": [], "delete": []}
        ops = [("create", x) for x in create] + [("update", x) for x in update] + [("delete", x) for x in delete]
        for i in range(0, len(ops), 100):
            body: dict = {}
            for kind, item in ops[i:i + 100]:
                body.setdefault(kind, []).append(item)
            res = self.json("POST", path, json=body)
            for k in result:
                result[k].extend(res.get(k, []))
        return result

    def counts(self) -> dict:
        def total(**params):
            _d, t, _p = self.page("/products", {"per_page": 1, "_fields": "id", **params})
            return t

        keys = {"all": {"status": "any"}, "publish": {"status": "publish"}, "draft": {"status": "draft"},
                "outofstock": {"stock_status": "outofstock"}}
        vals = run_parallel([(lambda p=p: total(**p)) for p in keys.values()])
        return dict(zip(keys, vals))

    # ---- taxonomies ----------------------------------------------------
    def categories(self) -> list:
        return self.all_pages("/products/categories", {"hide_empty": "false"})

    def create_category(self, name: str, parent: int = 0) -> dict:
        return self.json("POST", "/products/categories", json={"name": name, "parent": parent})

    def tags(self) -> list:
        return self.all_pages("/products/tags")

    def create_tag(self, name: str) -> dict:
        from .http import ApiError

        try:
            return self.json("POST", "/products/tags", json={"name": name})
        except ApiError as e:
            if isinstance(e.payload, dict) and e.payload.get("code") == "term_exists":
                return {"id": e.payload.get("data", {}).get("resource_id"), "name": name}
            raise

    # ---- variations ----------------------------------------------------
    def variations(self, pid: int) -> list:
        return self.all_pages(f"/products/{pid}/variations")

    def batch_variations(self, pid: int, create=None, update=None, delete=None) -> dict:
        return self._batch(f"/products/{pid}/variations/batch", create, update, delete)


def variation_combos(attributes: list[dict]) -> list[list[dict]]:
    """Cartesian product of all attributes flagged for variations."""
    usable = [a for a in attributes if a.get("variation") and a.get("options")]
    if not usable:
        return []
    lists = [[{"id": a.get("id", 0), "name": a["name"], "option": o} for o in a["options"]] for a in usable]
    return [list(c) for c in itertools.product(*lists)]


def combo_key(attrs: list[dict]) -> tuple:
    return tuple(sorted((a.get("name", "").lower(), str(a.get("option", "")).lower()) for a in attrs))
