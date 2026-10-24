"""Dynamic Remote Service module. Hot-reloadable server-facing business logic.

The app keeps an identical built-in fallback in `app/api/server_logic.py`. If this module is
missing or fails to load, the app transparently uses that fallback. Update this file from the
server admin panel to change how WooDesk talks to your server without shipping a new app build.
"""
from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlparse

__version__ = "1.2.0"

# Server endpoint paths. Change these per deployment without touching the client build.
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

# How often anonymous statistics may be sent, in seconds.
TELEMETRY_INTERVAL_SECONDS = 20 * 3600


def endpoint(name: str) -> str:
    """Returns the configured path for a server endpoint, falling back to a sensible default."""
    return ENDPOINTS.get(name, f"/v1/{name}")


def server_headers(token: str = "", gmail: str = "") -> dict[str, str]:
    """Builds the authentication / identification headers for server requests."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if gmail:
        headers["X-User-Gmail"] = gmail.strip().lower()
    return headers


def ai_catalog_overrides() -> dict[str, Any]:
    """Edit providers, prompts or languages here; changes reload without rebuilding the app.

    The same production catalog can also be published through /v1/ai/catalog. Keep API keys
    out of this file: provider definitions contain header schemes, never secret values.
    """
    return {}


def sanitize_domain(url_or_domain: str) -> str:
    """Extracts and sanitizes domain name from a URL or raw domain string."""
    s = (url_or_domain or "").strip().lower()
    if not s:
        return ""
    parsed = urlparse(s if "://" in s else f"//{s}", scheme="http")
    return (parsed.hostname or s.split("/")[0].split(":")[0]).strip()


def prepare_ai_payload(
    messages: list[dict[str, str]],
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Validates and packages chat messages for upstream AI execution."""
    cleaned_messages = []
    for m in messages:
        role = m.get("role", "user")
        if role not in ("system", "user", "assistant"):
            role = "user"
        content = str(m.get("content", ""))
        cleaned_messages.append({"role": role, "content": content})

    payload: dict[str, Any] = {
        "model": model,
        "messages": cleaned_messages,
        "temperature": max(0.0, min(float(temperature), 2.0)),
    }
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    return payload


def ai_chat_request(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int | None = None,
    model: str | None = None,
    gmail: str = "",
) -> dict[str, Any]:
    """Builds the AI chat request: {path, json} ready for the client's HTTP transport."""
    payload = prepare_ai_payload(messages, model or "gpt-4o-mini", temperature, max_tokens)
    payload.pop("model", None)
    if model:
        payload["model"] = model
    if gmail:
        payload["gmail"] = gmail.strip().lower()
    return {"path": endpoint("ai_chat"), "json": payload}


def parse_ai_response(data: dict[str, Any]) -> dict[str, Any]:
    """Normalizes the AI chat response into {content, usage, remaining}."""
    data = data or {}
    return {
        "content": data.get("content", ""),
        "usage": data.get("usage") or {},
        "remaining": data.get("remaining"),
    }


def parse_announcements(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enriches and standardizes remote announcement items."""
    processed = []
    for item in raw_items:
        title = html.unescape(str(item.get("title", "")).strip())
        body = html.unescape(str(item.get("body", "")).strip())
        url = str(item.get("url", "")).strip()
        level = item.get("level", "info")
        is_popup = bool(item.get("is_popup", False) or level == "urgent")

        processed.append({
            "id": item.get("id"),
            "title": title,
            "body": body,
            "url": url,
            "level": level,
            "is_popup": is_popup,
            "created": item.get("created"),
        })
    return processed


def extract_announcements(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extracts the announcement list from a server response and normalizes it."""
    data = data or {}
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    return parse_announcements(items)


def announcements_params(version: str, lang: str) -> dict[str, str]:
    """Query parameters for the announcements endpoint."""
    return {"version": version, "lang": lang}


def build_telemetry_payload(
    app_version: str,
    os_name: str,
    lang: str,
    sites: list[str],
) -> dict[str, Any]:
    """Builds an anonymous telemetry payload ensuring no sensitive details are included."""
    clean_domains = sorted({sanitize_domain(s) for s in sites if s and sanitize_domain(s)})
    return {
        "app_version": app_version,
        "os": os_name,
        "lang": lang,
        "sites": clean_domains,
    }


def telemetry_interval_seconds() -> int:
    """Minimum number of seconds between two anonymous statistics submissions."""
    return TELEMETRY_INTERVAL_SECONDS


def should_send_telemetry(enabled: bool, last_ts: float, now: float, interval: int | None = None) -> bool:
    """Decides whether anonymous statistics should be sent right now."""
    if not enabled:
        return False
    span = telemetry_interval_seconds() if interval is None else int(interval)
    return (now - (last_ts or 0)) > span


class RemoteService:
    """Encapsulates server-facing business routines with interface stability."""

    version = __version__

    @staticmethod
    def headers(token: str = "", gmail: str = "") -> dict:
        return server_headers(token, gmail)

    @staticmethod
    def endpoint(name: str) -> str:
        return endpoint(name)

    @staticmethod
    def prepare_ai(messages: list[dict], model: str = "gpt-4o-mini", temperature: float = 0.7, max_tokens: int | None = None) -> dict:
        return prepare_ai_payload(messages, model, temperature, max_tokens)

    @staticmethod
    def ai_request(messages: list[dict], temperature: float = 0.7, max_tokens: int | None = None, model: str | None = None, gmail: str = "") -> dict:
        return ai_chat_request(messages, temperature, max_tokens, model, gmail)

    @staticmethod
    def parse_ai(data: dict) -> dict:
        return parse_ai_response(data)

    @staticmethod
    def parse_news(items: list[dict]) -> list[dict]:
        return parse_announcements(items)

    @staticmethod
    def build_telemetry(version: str, os_name: str, lang: str, sites: list[str]) -> dict:
        return build_telemetry_payload(version, os_name, lang, sites)

    @staticmethod
    def telemetry_interval() -> int:
        return telemetry_interval_seconds()

    @staticmethod
    def should_send_telemetry(enabled: bool, last_ts: float, now: float, interval: int | None = None) -> bool:
        return should_send_telemetry(enabled, last_ts, now, interval)
