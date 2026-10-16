"""A tiny in-memory fake of the WordPress + WooCommerce REST API (plus an OpenAI-compatible
endpoint) for developing and testing WooDesk without a real shop.

    python -m dev.fake_store            # serves on http://127.0.0.1:8099
"""
from __future__ import annotations

import itertools
import struct
import zlib
from datetime import datetime

from fastapi import FastAPI, Request, Response

app = FastAPI()
_ids = itertools.count(1000)


def png(color=(108, 92, 231), size=64) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * size for _ in range(size))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


BASE = "http://127.0.0.1:8099"
CATS = [{"id": i, "name": n, "parent": p, "slug": n.lower()} for i, n, p in
        [(1, "Furniture", 0), (2, "Sofas", 1), (3, "Tables", 1), (4, "Lighting", 0), (5, "Decor", 0)]]
TAGS = [{"id": 50, "name": "new", "slug": "new"}, {"id": 51, "name": "sale", "slug": "sale"}]
MEDIA: list[dict] = []
POSTS: list[dict] = []
PRODUCTS: list[dict] = []
VARS: dict[int, list[dict]] = {}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def mk_media(title: str, color=(108, 92, 231)) -> dict:
    mid = next(_ids)
    m = {"id": mid, "title": {"raw": title}, "slug": title.lower().replace(" ", "-"), "source_url": f"{BASE}/files/{mid}.png",
         "mime_type": "image/png", "alt_text": "", "media_details": {"sizes": {}}, "_color": color}
    MEDIA.append(m)
    return m


def product(i: int) -> dict:
    img = mk_media(f"Product {i}", ((i * 37) % 255, (i * 91) % 255, (i * 53) % 255))
    variable = i % 9 == 0
    p = {
        "id": 100 + i, "name": f"Test product {i}", "slug": f"test-product-{i}", "type": "variable" if variable else "simple",
        "status": "draft" if i % 7 == 0 else "publish", "sku": f"SKU-{i:03d}", "regular_price": "" if variable else str(100000 + i * 5000),
        "sale_price": str(90000 + i * 5000) if i % 4 == 0 and not variable else "", "price": str(100000 + i * 5000),
        "description": "" if i % 3 == 0 else f"<p>Description of product {i}</p>", "short_description": "",
        "manage_stock": i % 2 == 0, "stock_quantity": i if i % 2 == 0 else None,
        "stock_status": "outofstock" if i % 5 == 0 else "instock", "backorders": "no", "sold_individually": False,
        "categories": [CATS[i % 5]], "tags": [], "images": [{"id": img["id"], "src": img["source_url"], "alt": ""}],
        "attributes": [{"id": 0, "name": "Color", "position": 0, "visible": True, "variation": True, "options": ["Red", "Blue"]}] if variable else [],
        "meta_data": [], "weight": "", "dimensions": {"length": "", "width": "", "height": ""}, "featured": False,
    }
    if variable:
        VARS[p["id"]] = [{"id": next(_ids), "sku": f"V-{i}-{c}", "regular_price": "150000", "sale_price": "", "stock_quantity": 5,
                          "attributes": [{"id": 0, "name": "Color", "option": c}]} for c in ("Red", "Blue")]
    return p


for i in range(1, 46):
    PRODUCTS.append(product(i))
for i in range(1, 13):
    POSTS.append({"id": 500 + i, "title": {"raw": f"Sample article {i}"}, "content": {"raw": f"<p>Body {i}</p>"}, "excerpt": {"raw": ""},
                  "status": "draft" if i % 4 == 0 else "publish", "date": now(), "slug": f"article-{i}", "categories": [1 + i % 3], "tags": [], "featured_media": 0, "sticky": False})


def paged(items: list, request: Request, resp: Response):
    q = request.query_params
    page, per = int(q.get("page", 1)), int(q.get("per_page", 10))
    resp.headers["X-WP-Total"] = str(len(items))
    resp.headers["X-WP-TotalPages"] = str(max(1, -(-len(items) // per)))
    return items[(page - 1) * per: page * per]


# ------------------------------------------------------------------ WP ---
@app.get("/wp-json/wp/v2/users/me")
def me():
    return {"id": 1, "name": "Admin", "slug": "admin"}


@app.get("/wp-json/wp/v2/posts")
def posts(request: Request, response: Response):
    q = request.query_params
    items = [p for p in POSTS if q.get("status", "any") in ("any", p["status"]) and q.get("search", "").lower() in p["title"]["raw"].lower()]
    return paged(sorted(items, key=lambda p: -p["id"]), request, response)


@app.post("/wp-json/wp/v2/posts")
async def post_create(request: Request):
    d = await request.json()
    p = {"id": next(_ids), "date": now(), "categories": [], "tags": [], "featured_media": 0, "sticky": False, "slug": "", "excerpt": {"raw": ""}, **{}}
    p["title"], p["content"] = {"raw": d.get("title", "")}, {"raw": d.get("content", "")}
    p["excerpt"] = {"raw": d.get("excerpt", "")}
    for k in ("status", "categories", "tags", "featured_media", "sticky", "slug"):
        if k in d:
            p[k] = d[k]
    POSTS.append(p)
    return p


@app.post("/wp-json/wp/v2/posts/{pid}")
async def post_update(pid: int, request: Request):
    d = await request.json()
    p = next(x for x in POSTS if x["id"] == pid)
    for k, v in d.items():
        p[k] = {"raw": v} if k in ("title", "content", "excerpt") else v
    return p


@app.delete("/wp-json/wp/v2/posts/{pid}")
def post_delete(pid: int):
    POSTS[:] = [p for p in POSTS if p["id"] != pid]
    return {"deleted": True}


def tax_routes(prefix: str, store: list, kind: str):
    @app.get(prefix + kind)
    def lst(request: Request, response: Response):
        return paged(store, request, response)

    @app.post(prefix + kind)
    async def create(request: Request):
        d = await request.json()
        if any(x["name"].lower() == d["name"].lower() for x in store):
            ex = next(x for x in store if x["name"].lower() == d["name"].lower())
            return Response(status_code=400, media_type="application/json",
                            content='{"code":"term_exists","message":"exists","data":{"term_id":%d,"resource_id":%d}}' % (ex["id"], ex["id"]))
        item = {"id": next(_ids), "name": d["name"], "parent": d.get("parent", 0), "slug": d["name"].lower()}
        store.append(item)
        return item


tax_routes("/wp-json/wp/v2", CATS, "/categories")
tax_routes("/wp-json/wp/v2", TAGS, "/tags")
tax_routes("/wp-json/wc/v3/products", CATS, "/categories")
tax_routes("/wp-json/wc/v3/products", TAGS, "/tags")


@app.get("/wp-json/wp/v2/media")
def media(request: Request, response: Response):
    s = request.query_params.get("search", "").lower()
    return paged([m for m in reversed(MEDIA) if s in m["title"]["raw"].lower()], request, response)


@app.get("/wp-json/wp/v2/media/{mid}")
def media_get(mid: int):
    return next(m for m in MEDIA if m["id"] == mid)


@app.post("/wp-json/wp/v2/media")
async def media_upload(request: Request):
    body = await request.body()
    name = request.headers.get("content-disposition", "").split("filename=")[-1].strip('"')
    m = mk_media(name or "upload")
    m["_bytes"] = body
    return m


@app.post("/wp-json/wp/v2/media/{mid}")
async def media_update(mid: int, request: Request):
    m = next(x for x in MEDIA if x["id"] == mid)
    m.update(await request.json())
    return m


@app.delete("/wp-json/wp/v2/media/{mid}")
def media_delete(mid: int):
    MEDIA[:] = [m for m in MEDIA if m["id"] != mid]
    return {"deleted": True}


@app.get("/files/{mid}.png")
def files(mid: int):
    m = next((x for x in MEDIA if x["id"] == mid), None)
    return Response(m.get("_bytes") or png(m["_color"] if m else (0, 0, 0)), media_type="image/png")


# ------------------------------------------------------------------ Woo ---
@app.get("/wp-json/wc/v3/products")
def products(request: Request, response: Response):
    q = request.query_params
    items = PRODUCTS
    if q.get("status", "any") != "any":
        items = [p for p in items if p["status"] == q["status"]]
    if q.get("stock_status"):
        items = [p for p in items if p["stock_status"] == q["stock_status"]]
    if q.get("search"):
        items = [p for p in items if q["search"].lower() in p["name"].lower()]
    if q.get("sku"):
        items = [p for p in items if p["sku"] == q["sku"]]
    if q.get("category"):
        items = [p for p in items if any(str(c["id"]) == q["category"] for c in p["categories"])]
    return paged(sorted(items, key=lambda p: -p["id"]), request, response)


def apply(p: dict, d: dict) -> dict:
    cat_by_id = {c["id"]: c for c in CATS}
    tag_by_id = {t["id"]: t for t in TAGS}
    for k, v in d.items():
        if k == "categories":
            p[k] = [cat_by_id[c["id"]] for c in v if c["id"] in cat_by_id]
        elif k == "tags":
            p[k] = [tag_by_id[t["id"]] for t in v if t["id"] in tag_by_id]
        elif k == "images":
            p[k] = [{"id": i.get("id", 0), "src": i.get("src") or next((m["source_url"] for m in MEDIA if m["id"] == i.get("id")), ""), "alt": ""} for i in v]
        else:
            p[k] = v
    if "regular_price" in d:
        p["price"] = d.get("sale_price") or d["regular_price"]
    return p


@app.post("/wp-json/wc/v3/products")
async def product_create(request: Request):
    d = await request.json()
    p = {"id": next(_ids), "slug": "", "type": "simple", "status": "publish", "sku": "", "regular_price": "", "sale_price": "", "price": "",
         "description": "", "short_description": "", "manage_stock": False, "stock_quantity": None, "stock_status": "instock",
         "categories": [], "tags": [], "images": [], "attributes": [], "meta_data": [], "dimensions": {}}
    PRODUCTS.append(apply(p, d))
    return p


@app.put("/wp-json/wc/v3/products/{pid}")
async def product_update(pid: int, request: Request):
    p = next(x for x in PRODUCTS if x["id"] == pid)
    return apply(p, await request.json())


@app.get("/wp-json/wc/v3/products/{pid}")
def product_get(pid: int):
    return next(x for x in PRODUCTS if x["id"] == pid)


@app.delete("/wp-json/wc/v3/products/{pid}")
def product_delete(pid: int):
    PRODUCTS[:] = [p for p in PRODUCTS if p["id"] != pid]
    return {"deleted": True}


@app.post("/wp-json/wc/v3/products/batch")
async def products_batch(request: Request):
    d = await request.json()
    out = {"create": [], "update": [], "delete": []}
    for c in d.get("create", []):
        out["create"].append(await product_create_dict(c))
    for u in d.get("update", []):
        p = next((x for x in PRODUCTS if x["id"] == u["id"]), None)
        out["update"].append(apply(p, {k: v for k, v in u.items() if k != "id"}) if p else {"error": "missing"})
    for pid in d.get("delete", []):
        PRODUCTS[:] = [p for p in PRODUCTS if p["id"] != pid]
        out["delete"].append({"id": pid})
    return out


async def product_create_dict(d: dict) -> dict:
    p = {"id": next(_ids), "slug": "", "type": "simple", "status": "publish", "sku": "", "regular_price": "", "sale_price": "", "price": "",
         "description": "", "short_description": "", "manage_stock": False, "stock_quantity": None, "stock_status": "instock",
         "categories": [], "tags": [], "images": [], "attributes": [], "meta_data": [], "dimensions": {}}
    PRODUCTS.append(apply(p, d))
    return p


@app.get("/wp-json/wc/v3/products/{pid}/variations")
def variations(pid: int, request: Request, response: Response):
    return paged(VARS.get(pid, []), request, response)


@app.post("/wp-json/wc/v3/products/{pid}/variations/batch")
async def variations_batch(pid: int, request: Request):
    d = await request.json()
    out = {"create": [], "update": [], "delete": []}
    lst = VARS.setdefault(pid, [])
    for c in d.get("create", []):
        v = {"id": next(_ids), "sku": "", "regular_price": "", "sale_price": "", "stock_quantity": None, **c}
        lst.append(v)
        out["create"].append(v)
    for u in d.get("update", []):
        v = next(x for x in lst if x["id"] == u["id"])
        v.update(u)
        out["update"].append(v)
    for vid in d.get("delete", []):
        lst[:] = [v for v in lst if v["id"] != vid]
        out["delete"].append({"id": vid})
    return out


# --------------------------------------------------------- fake AI API ---
@app.post("/v1/chat/completions")
async def chat(request: Request):
    d = await request.json()
    prompt = d["messages"][-1]["content"]
    if "Return ONLY a JSON object" in prompt:
        text = '{"title": "Great title", "description": "A fine meta description.", "slug": "great-title", "focus_keyword": "kw"}'
    elif "comma-separated" in prompt:
        text = "alpha, beta, gamma"
    else:
        text = "<p>Generated text for: " + prompt[:60].replace("\n", " ") + "</p>"
    return {"choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"total_tokens": 42}}


@app.get("/v1/models")
def models():
    return {"data": [{"id": "fake-model-1"}, {"id": "fake-model-2"}]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8099)
