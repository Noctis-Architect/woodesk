import json
import os
import sys
import tempfile
import threading
import time

os.environ["WOODESK_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import PySide6
except ImportError:
    from unittest.mock import MagicMock
    sys.modules["PySide6"] = MagicMock()
    sys.modules["PySide6.QtCore"] = MagicMock()
    sys.modules["PySide6.QtWidgets"] = MagicMock()
    sys.modules["PySide6.QtGui"] = MagicMock()

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.ai import prompts  # noqa: E402
from app.ai.client import AnthropicClient, OpenAICompatClient, QuotaExceeded  # noqa: E402
from app.api.http import ApiError, domain_of, normalize_url  # noqa: E402
from app.api.server import ServerClient  # noqa: E402
from app.api.woo import WooClient, combo_key, variation_combos  # noqa: E402
from app.api.wp import WPClient  # noqa: E402
from app.core.config import Config, Site  # noqa: E402
from app.ui.pages.products import adjust_price  # noqa: E402



def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_url_helpers():
    assert normalize_url("shop.ir/") == "https://shop.ir"
    assert normalize_url("http://a.com/x/") == "http://a.com/x"
    assert domain_of("https://WWW.Shop.IR/path") == "www.shop.ir"


def test_wp_list_headers_and_auth():
    seen = {}

    def h(req):
        seen["auth"] = req.headers.get("authorization")
        seen["url"] = str(req.url)
        return httpx.Response(200, json=[{"id": 1}], headers={"X-WP-Total": "41", "X-WP-TotalPages": "3"})

    wp = WPClient("shop.ir", "admin", "abcd efgh", client_with(h))
    items, total, pages = wp.posts(page=2, search="x", status="draft")
    assert (total, pages) == (41, 3) and items == [{"id": 1}]
    assert seen["auth"].startswith("Basic ") and "/wp-json/wp/v2/posts" in seen["url"] and "page=2" in seen["url"]


def test_wp_error_message_and_tag_exists():
    def h(req):
        if req.method == "POST" and "tags" in req.url.path:
            return httpx.Response(400, json={"code": "term_exists", "message": "exists", "data": {"term_id": 77}})
        return httpx.Response(401, json={"code": "rest_forbidden", "message": "Sorry, you are not allowed"})

    wp = WPClient("https://shop.ir", "a", "b", client_with(h))
    assert wp.create_tag("x")["id"] == 77
    with pytest.raises(ApiError) as e:
        wp.me()
    assert e.value.status == 401 and "not allowed" in str(e.value)


def test_woo_batch_is_chunked_to_100():
    batches = []

    def h(req):
        body = json.loads(req.content)
        batches.append(body)
        return httpx.Response(200, json={"update": [{"id": u["id"]} for u in body.get("update", [])]})

    woo = WooClient("https://shop.ir", "ck_a", "cs_b", client=client_with(h))
    res = woo.batch_products(update=[{"id": i} for i in range(250)])
    assert [len(b["update"]) for b in batches] == [100, 100, 50] and len(res["update"]) == 250


def test_woo_auth_modes():
    seen = []
    h = lambda req: (seen.append(req.headers["authorization"]), httpx.Response(200, json=[], headers={"X-WP-Total": "0"}))[1]  # noqa: E731
    WooClient("https://s.ir", "ck", "cs", client=client_with(h)).ping()
    WooClient("https://s.ir", wp_user="u", wp_password="p", client=client_with(h)).ping()
    assert seen[0] != seen[1]


def test_variation_combos():
    attrs = [{"name": "Color", "options": ["Red", "Blue"], "variation": True}, {"name": "Size", "options": ["S", "M", "L"], "variation": True},
             {"name": "Material", "options": ["Wood"], "variation": False}]
    combos = variation_combos(attrs)
    assert len(combos) == 6
    existing = {combo_key([{"name": "color", "option": "RED"}, {"name": "Size", "option": "s"}])}
    assert sum(combo_key(c) in existing for c in combos) == 1


def test_adjust_price():
    assert adjust_price("100000", pct=10) == "110000"
    assert adjust_price("99.50", pct=-10) == "89.55"
    assert adjust_price("1000", amount=-2000) == "0"
    assert adjust_price("", pct=5) == ""


def test_openai_compat_and_models():
    def h(req):
        if req.url.path.endswith("/chat/completions"):
            body = json.loads(req.content)
            assert body["model"] == "m1" and req.headers["authorization"] == "Bearer KEY"
            return httpx.Response(200, json={"choices": [{"message": {"content": " hi "}}], "usage": {"total_tokens": 5}})
        return httpx.Response(200, json={"data": [{"id": "b"}, {"id": "a"}]})

    c = OpenAICompatClient("https://api.x.com/v1/chat/completions", "KEY", "m1", client_with(h))
    r = c.chat([{"role": "user", "content": "x"}])
    assert r.text == "hi" and r.usage["total_tokens"] == 5
    assert c.list_models() == ["a", "b"]


def test_anthropic_client_splits_system():
    def h(req):
        body = json.loads(req.content)
        assert body["system"] == "sys" and body["messages"] == [{"role": "user", "content": "q"}]
        assert req.headers["x-api-key"] == "K"
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 2, "output_tokens": 3}})

    c = AnthropicClient("https://api.anthropic.com", "K", "claude", client_with(h))
    r = c.chat([{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}])
    assert r.text == "ok" and r.usage["total_tokens"] == 5


def test_prompts_json_parsing():
    assert prompts.parse_json_loose('```json\n{"title": "a"}\n```')["title"] == "a"
    assert prompts.parse_json_loose('Sure! {"x": 1} done')["x"] == 1
    with pytest.raises(ValueError):
        prompts.parse_json_loose("no json")
    assert prompts.strip_fences("```html\n<p>x</p>\n```") == "<p>x</p>"


def test_config_roundtrip_and_unknown_keys():
    c = Config.load()
    c.add_site(Site(id="a", name="A", url="https://a.com", wp_user="u"))
    c.ai.model = "gpt"
    c.telemetry = False
    c.save()
    raw = json.loads(c.path.read_text())
    raw["future_key"] = 1
    raw["sites"][0]["future_site_key"] = 2
    c.path.write_text(json.dumps(raw))
    c2 = Config.load()
    assert c2.sites[0].id == "a" and c2.ai.model == "gpt" and c2.telemetry is False and c2.active_site == "a"


def test_server_client_mock():
    seen = []

    def h(req: httpx.Request):
        seen.append((req.method, req.url.path))
        if req.url.path == "/v1/config":
            return httpx.Response(200, json={"free_ai_enabled": True, "models": ["gpt-4o-mini"]})
        if req.url.path == "/v1/register":
            return httpx.Response(200, json={"token": "tok123"})
        if req.url.path == "/v1/quota":
            return httpx.Response(200, json={"used": 1, "limit": 10})
        if req.url.path == "/v1/announcements":
            return httpx.Response(200, json={"items": [{"id": 1, "text": "hello"}]})
        if req.url.path == "/v1/telemetry":
            return httpx.Response(200, json={"ok": True})
        if req.url.path == "/v1/ai/chat":
            body = json.loads(req.content)
            if body["messages"][0]["content"] == "quota_fail":
                return httpx.Response(429, json={"detail": "Quota exceeded"})
            return httpx.Response(200, json={"content": "mock pong", "usage": {"total_tokens": 5}, "remaining": 9})
        return httpx.Response(404)

    sc = ServerClient("http://127.0.0.1:8097", client=httpx.Client(transport=httpx.MockTransport(h)))
    assert sc.config()["free_ai_enabled"] is True
    assert sc.free_models() == ["gpt-4o-mini"]
    reg = sc.register("0.1.0", "Windows 11")
    assert reg["token"] == "tok123"

    sc.token = reg["token"]
    assert sc.quota()["used"] == 1
    assert len(sc.announcements("0.1.0", "fa")) == 1
    sc.telemetry({"app_version": "0.1.0"})
    sc.telemetry_delete()

    res = sc.chat([{"role": "user", "content": "hi"}])
    assert res.text == "mock pong" and res.remaining == 9

    with pytest.raises(QuotaExceeded):
        sc.chat([{"role": "user", "content": "quota_fail"}])


# ---- real client <-> real server contract ----------------------------------
def test_server_client_against_real_server(tmp_path):
    server_dir = os.path.join(os.path.dirname(__file__), "..", "server")
    if not os.path.isdir(server_dir):
        pytest.skip("server directory not present")

    try:
        import uvicorn
        sys.path.insert(0, server_dir)
        import importlib
        for name in [n for n in sys.modules if n.startswith("woodesk_server")]:
            del sys.modules[name]
        srv = importlib.import_module("woodesk_server.main")
    except ImportError as e:
        pytest.skip(f"server dependencies not available: {e}")

    os.environ.update(ADMIN_TOKEN="adm", FREE_AI_API_KEYS="k", FREE_DAILY_REQUESTS="2", RATE_PER_MINUTE="50",
                      REGISTER_PER_IP_PER_DAY="1000", DATABASE_PATH=str(tmp_path / "s.db"))
    srv.UPSTREAM_TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}], "usage": {"total_tokens": 7}}))
    server = uvicorn.Server(uvicorn.Config(srv.app, host="127.0.0.1", port=8097, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    time.sleep(1)
    try:
        sc = ServerClient("http://127.0.0.1:8097")
        assert sc.config()["free_ai_enabled"] is True
        reg = sc.register("0.1.0", "Windows 11")
        sc = ServerClient("http://127.0.0.1:8097", reg["token"])
        r = sc.chat([{"role": "user", "content": "ping"}])
        assert r.text == "pong" and r.remaining == 1
        assert sc.quota()["used"] == 1
        sc.telemetry({"app_version": "0.1.0", "os": "W", "lang": "fa", "sites": ["a.com"]})
        sc.chat([{"role": "user", "content": "ping"}])
        with pytest.raises(QuotaExceeded):
            sc.chat([{"role": "user", "content": "ping"}])
        assert sc.announcements("0.1.0", "fa") == []
    finally:
        server.should_exit = True
        for name in [n for n in sys.modules if n.startswith("woodesk_server")]:
            del sys.modules[name]


def test_all_pages_loads_remaining_pages_in_order():
    def h(req):
        page = int(req.url.params["page"])
        return httpx.Response(200, json=[{"id": page * 10}], headers={"X-WP-Total": "3", "X-WP-TotalPages": "3"})

    wp = WPClient("https://shop.ir", "a", "b", client_with(h))
    assert [c["id"] for c in wp.all_pages("/categories")] == [10, 20, 30]


def test_ensure_tags_searches_instead_of_downloading_all_tags():
    seen = []

    def h(req):
        seen.append((req.method, req.url.path, dict(req.url.params)))
        if req.method == "GET":
            return httpx.Response(200, json=[{"id": 5, "name": "Sale &amp; Co"}, {"id": 6, "name": "sale"}])
        return httpx.Response(201, json={"id": 99, "name": "brand new"})

    woo = WooClient("https://shop.ir", "ck", "cs", client=client_with(h))
    assert woo.ensure_tags(["sale", "Sale & Co", "SALE", "brand new"]) == [6, 5, 99]
    assert all(p.get("search") for m, _p, p in seen if m == "GET")  # server-side search, never the full list
    assert sum(1 for m, *_ in seen if m == "POST") == 1


def test_product_list_requests_only_needed_fields():
    seen = {}

    def h(req):
        seen.update(dict(req.url.params))
        return httpx.Response(200, json=[], headers={"X-WP-Total": "0", "X-WP-TotalPages": "1"})

    WooClient("https://shop.ir", "ck", "cs", client=client_with(h)).products()
    assert "_fields" in seen and "description" in seen["_fields"] and "yoast_head" not in seen["_fields"]
