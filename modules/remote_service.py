"""Dynamic Remote Service module. Hot-reloadable network & server-facing business logic."""
from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlparse

__version__ = "1.0.1"


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


class RemoteService:
    """Encapsulates server-facing business routines with interface stability."""

    version = __version__

    @staticmethod
    def prepare_ai(messages: list[dict], model: str = "gpt-4o-mini", temperature: float = 0.7, max_tokens: int | None = None) -> dict:
        return prepare_ai_payload(messages, model, temperature, max_tokens)

    @staticmethod
    def parse_news(items: list[dict]) -> list[dict]:
        return parse_announcements(items)

    @staticmethod
    def build_telemetry(version: str, os_name: str, lang: str, sites: list[str]) -> dict:
        return build_telemetry_payload(version, os_name, lang, sites)
