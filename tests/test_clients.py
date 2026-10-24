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
from app.ai.catalog import AICatalog, CatalogError, catalog, validate_remote  # noqa: E402
from app.ai.client import QuotaExceeded  # noqa: E402
from app.ai.provider import DynamicProviderClient  # noqa: E402
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


def test_config_save_is_safe_when_called_concurrently(tmp_path, monkeypatch):
    monkeypatch.setenv("WOODESK_HOME", str(tmp_path))
    config = Config(language="fa", theme="dark")
    errors = []

    def save():
        try:
            config.save()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=save) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert json.loads(config.path.read_text(encoding="utf-8"))["theme"] == "dark"


def test_dynamic_provider_request_headers_response_and_models():
    def h(req):
        if req.url.path == "/v1/ask":
            body = json.loads(req.content)
            assert body == {"engine": "m1", "input": [{"role": "user", "content": "x"}], "limit": 7}
            assert req.headers["x-api-key"] == "Token KEY"
            assert req.url.params["key"] == "KEY" and req.url.params["api-version"] == "2026-01-01"
            return httpx.Response(200, json={"result": [{"output": " hi "}], "meta": {"total_tokens": 5}})
        assert req.url.path == "/v1/catalog"
        assert req.url.params["key"] == "KEY"
        return httpx.Response(200, json={"payload": {"items": [{"slug": "b"}, {"slug": "models/a"}]}})

    profile = validate_remote({
        "schema_version": 1,
        "version": "test",
        "providers": [{
            "id": "custom-test", "label": "Custom Test", "base_url": "https://api.x.com/v1",
            "auth": {"header": "X-API-Key", "prefix": "Token ", "query_param": "key", "required": True},
            "headers": {"Content-Type": "application/json"},
            "chat": {
                "method": "POST", "path": "/ask", "query": {"api-version": "2026-01-01"},
                "body": {"engine": "{model}", "input": "{messages}", "limit": "{max_tokens}"},
            },
            "response": {"text": "result.0.output", "usage": "meta"},
            "models": {"path": "/catalog", "list": "payload.items", "id": "slug"},
        }],
    })["providers"][0]
    c = DynamicProviderClient(profile, profile["base_url"], "KEY", "m1", client_with(h))
    r = c.chat([{"role": "user", "content": "x"}], max_tokens=7)
    assert r.text == "hi" and r.usage["total_tokens"] == 5
    assert c.list_models() == ["a", "b"]


def test_anthropic_catalog_profile_splits_system():
    def h(req):
        body = json.loads(req.content)
        assert body["system"] == "sys" and body["messages"] == [{"role": "user", "content": "q"}]
        assert req.headers["x-api-key"] == "K" and req.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 2, "output_tokens": 3}})

    profile = catalog.provider("anthropic")
    c = DynamicProviderClient(profile, profile["base_url"], "K", "claude", client_with(h))
    r = c.chat([{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}])
    assert r.text == "ok" and r.usage["input_tokens"] == 2


def test_remote_catalog_overrides_prompts_and_rejects_unknown_variables():
    original = catalog.snapshot()
    try:
        catalog.apply_remote({
            "schema_version": 1,
            "version": "remote-test",
            "providers": [],
            "languages": {"fa": "Persian custom"},
            "prompts": {"translate": {"user": "Translate into {language}.\n{text}"}},
        }, persist=False)
        messages = prompts.translate("hello", "fa")
        assert "Persian custom" in messages[-1]["content"]
        assert "{text}" not in messages[-1]["content"] and "hello" in messages[-1]["content"]
        with pytest.raises(CatalogError):
            catalog.apply_remote({
                "schema_version": 1,
                "providers": [],
                "prompts": {"translate": {"user": "Use {unsupported_variable}"}},
            }, persist=False)
    finally:
        catalog.apply_remote({
            "schema_version": 1, "version": original["version"],
            "providers": [], "prompts": {}, "languages": {},
        }, persist=False)
        catalog.reset_remote()


def test_remote_catalog_is_cached_for_offline_use(tmp_path, monkeypatch):
    monkeypatch.setenv("WOODESK_HOME", str(tmp_path))
    payload = {
        "schema_version": 1,
        "version": "offline-cache-1",
        "providers": [],
        "languages": {"xx": "Test language"},
        "prompts": {"alt_text": {"user": "Alt text for {name} in {language}"}},
    }
    first = AICatalog()
    first.apply_remote(payload)

    second = AICatalog()
    assert second.version() == "offline-cache-1"
    assert second.language("xx") == "Test language"
    assert "Alt text for" in second.prompt("alt_text")["user"]
    second.reset_remote()


def test_every_builtin_prompt_renders_from_catalog():
    rendered = [
        prompts.product_description("Chair", "fa", context="SKU 1"),
        prompts.product_short("Chair", "fa", description="A chair"),
        prompts.seo_meta("Chair", "fa", content="Body", keyword="chair"),
        prompts.rewrite("Text", "fa"),
        prompts.translate("Text", "en"),
        prompts.post_outline("Topic", "fa"),
        prompts.post_draft("Topic", "fa"),
        prompts.excerpt("Article", "fa"),
        prompts.suggest_tags("Article", "fa"),
        prompts.alt_text("Chair", "fa"),
        prompts.seo_audit({"score": 80}, "fa"),
        prompts.perf_analysis({"score": 90}, "fa"),
    ]
    for messages in rendered:
        assert [message["role"] for message in messages] == ["system", "user"]
        assert messages[-1]["content"].strip()


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
    c.notifications.new_orders = True
    c.notifications.interval_seconds = 120
    c.save()
    raw = json.loads(c.path.read_text())
    raw["future_key"] = 1
    raw["sites"][0]["future_site_key"] = 2
    c.path.write_text(json.dumps(raw))
    c2 = Config.load()
    assert c2.sites[0].id == "a" and c2.ai.model == "gpt" and c2.telemetry is False and c2.active_site == "a"
    assert c2.notifications.new_orders is True and c2.notifications.interval_seconds == 120


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
        if req.url.path == "/v1/feedback":
            return httpx.Response(200, json={"ok": True, "id": 42})
        if req.url.path == "/v1/telemetry":
            return httpx.Response(200, json={"ok": True})
        if req.url.path == "/v1/ai/chat":
            body = json.loads(req.content)
            if body["messages"][0]["content"] == "quota_fail":
                return httpx.Response(429, json={"detail": "Quota exceeded"})
            return httpx.Response(200, json={"content": "mock pong", "usage": {"total_tokens": 5}, "remaining": 9})
        return httpx.Response(404)

    sc = ServerClient("http://127.0.0.1:8097", client=httpx.Client(transport=httpx.MockTransport(h)), gmail="test@gmail.com")
    assert sc.config()["free_ai_enabled"] is True
    assert sc.free_models() == ["gpt-4o-mini"]
    reg = sc.register("0.1.0", "Windows 11")
    assert reg["token"] == "tok123"

    sc.token = reg["token"]
    assert sc.quota()["used"] == 1
    assert len(sc.announcements("0.1.0", "fa")) == 1
    sc.telemetry({"app_version": "0.1.0"})
    sc.telemetry_delete()

    fb_res = sc.send_feedback("پیشنهاد", "متن بازخورد", file_bytes=b"sample", filename="sample.txt")
    assert fb_res["ok"] is True and fb_res["id"] == 42

    res = sc.chat([{"role": "user", "content": "hi"}])
    assert res.text == "mock pong" and res.remaining == 9

    with pytest.raises(QuotaExceeded):
        sc.chat([{"role": "user", "content": "quota_fail"}])


# ---- real client <-> real server contract ----------------------------------
def test_server_client_against_real_server(tmp_path):
    server_dir = os.path.join(os.path.dirname(__file__), "..", "server")
    if not os.path.isdir(server_dir):
        pytest.skip("server directory not present")

    os.environ.update(ADMIN_TOKEN="adm", FREE_AI_API_KEYS="k", FREE_DAILY_REQUESTS="2", RATE_PER_MINUTE="50",
                      REGISTER_PER_IP_PER_DAY="1000", DATABASE_PATH=str(tmp_path / "s.db"))
    try:
        import uvicorn
        sys.path.insert(0, server_dir)
        import importlib
        for name in [n for n in list(sys.modules.keys()) if "woodesk_server" in n]:
            del sys.modules[name]
        srv = importlib.import_module("woodesk_server.main")
        srv.settings = srv.Settings()
    except ImportError as e:
        pytest.skip(f"server dependencies not available: {e}")

    srv.UPSTREAM_TRANSPORT = httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}], "usage": {"total_tokens": 7}}))
    server = uvicorn.Server(uvicorn.Config(srv.app, host="127.0.0.1", port=8097, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    time.sleep(1)
    try:
        sc = ServerClient("http://127.0.0.1:8097")
        assert sc.config()["free_ai_enabled"] is True
        reg = sc.register("0.1.0", "Windows 11")
        sc = ServerClient("http://127.0.0.1:8097", reg["token"], gmail="test@gmail.com")
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
