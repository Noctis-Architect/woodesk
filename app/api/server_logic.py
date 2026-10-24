"""Built-in fallback logic for server-facing AI + telemetry.

The hot-reloadable `remote_service` dynamic module may override any of these functions at runtime
so server communication can be updated without a new app build. If that module is missing or
fails, `call()` transparently falls back to the frozen implementations below.
"""
from __future__ import annotations

import html
import logging
from typing import Any
from urllib.parse import urlparse

from ..core.dynamic_loader import dynamic_manager

logger = logging.getLogger(__name__)

MODULE_NAME = "remote_service"

ENDPOINTS: dict[str, str] = {
    "config": "/v1/config",
    "register": "/v1/register",
    "announcements": "/v1/announcements",
    "quota": "/v1/quota",
    "telemetry": "/v1/telemetry",
    "ai_chat": "/v1/ai/chat",
    "ai_catalog": "/v1/ai/catalog",
    "feedback": "/v1/feedback",
}

TELEMETRY_INTERVAL_SECONDS = 20 * 3600


def call(name: str, *args, **kwargs) -> Any:
    """Runs the dynamic module's function if available, else the built-in fallback.

    If the dynamic function exists but raises at call time, the built-in is used so a bad remote
    update can never break AI or telemetry.
    """
    module = None
    try:
        module = dynamic_manager.get_service(MODULE_NAME)
    except Exception:
        module = None
    if module is not None:
        fn = getattr(module, name, None)
        if callable(fn):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.warning("Dynamic '%s.%s' failed, using built-in fallback: %s", MODULE_NAME, name, e)
    return globals()[name](*args, **kwargs)


# ---- built-in implementations (mirror of modules/remote_service.py) ------
def endpoint(name: str) -> str:
    return ENDPOINTS.get(name, f"/v1/{name}")


def server_headers(token: str = "", gmail: str = "") -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if gmail:
        headers["X-User-Gmail"] = gmail.strip().lower()
    return headers


def ai_catalog_overrides() -> dict:
    """Local catalog edits shipped by the hot-reloadable remote_service module."""
    return {}


def sanitize_domain(url_or_domain: str) -> str:
    s = (url_or_domain or "").strip().lower()
    if not s:
        return ""
    parsed = urlparse(s if "://" in s else f"//{s}", scheme="http")
    return (parsed.hostname or s.split("/")[0].split(":")[0]).strip()


def prepare_ai_payload(messages: list[dict], model: str = "gpt-4o-mini", temperature: float = 0.7, max_tokens: int | None = None) -> dict:
    cleaned = []
    for m in messages:
        role = m.get("role", "user")
        if role not in ("system", "user", "assistant"):
            role = "user"
        cleaned.append({"role": role, "content": str(m.get("content", ""))})
    payload: dict[str, Any] = {
        "model": model,
        "messages": cleaned,
        "temperature": max(0.0, min(float(temperature), 2.0)),
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    return payload


def ai_chat_request(messages: list[dict], temperature: float = 0.7, max_tokens: int | None = None, model: str | None = None, gmail: str = "") -> dict:
    payload = prepare_ai_payload(messages, model or "gpt-4o-mini", temperature, max_tokens)
    payload.pop("model", None)
    if model:
        payload["model"] = model
    if gmail:
        payload["gmail"] = gmail.strip().lower()
    return {"path": endpoint("ai_chat"), "json": payload}


def parse_ai_response(data: dict) -> dict:
    data = data or {}
    return {"content": data.get("content", ""), "usage": data.get("usage") or {}, "remaining": data.get("remaining")}


def parse_announcements(raw_items: list[dict]) -> list[dict]:
    processed = []
    for item in raw_items:
        level = item.get("level", "info")
        processed.append({
            "id": item.get("id"),
            "title": html.unescape(str(item.get("title", "")).strip()),
            "body": html.unescape(str(item.get("body", "")).strip()),
            "url": str(item.get("url", "")).strip(),
            "level": level,
            "is_popup": bool(item.get("is_popup", False) or level == "urgent"),
            "created": item.get("created"),
        })
    return processed


def extract_announcements(data: dict) -> list[dict]:
    data = data or {}
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    return parse_announcements(items)


def announcements_params(version: str, lang: str) -> dict[str, str]:
    return {"version": version, "lang": lang}


def build_telemetry_payload(app_version: str, os_name: str, lang: str, sites: list[str]) -> dict:
    clean_domains = sorted({sanitize_domain(s) for s in sites if s and sanitize_domain(s)})
    return {"app_version": app_version, "os": os_name, "lang": lang, "sites": clean_domains}


def telemetry_interval_seconds() -> int:
    return TELEMETRY_INTERVAL_SECONDS


def should_send_telemetry(enabled: bool, last_ts: float, now: float, interval: int | None = None) -> bool:
    if not enabled:
        return False
    span = telemetry_interval_seconds() if interval is None else int(interval)
    return (now - (last_ts or 0)) > span
