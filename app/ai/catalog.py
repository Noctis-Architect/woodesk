"""Versioned AI catalog: providers, languages and prompt templates.

The built-in catalog is the offline fallback. Local overrides come from the hot-reloadable
remote_service module; a catalog fetched from the project server has the final say.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..core.config import data_dir

SCHEMA_VERSION = 1
MAX_PAYLOAD_BYTES = 512 * 1024
log = logging.getLogger("woodesk.ai.catalog")

DEFAULT_SYSTEM = (
    "You are an expert e-commerce copywriter, blogger and SEO specialist working inside a "
    "WordPress/WooCommerce management app. Follow the instructions exactly. Output ONLY the "
    "requested content - no preface, no explanations, no markdown code fences. Never invent "
    "technical specifications, prices, certifications or claims that were not provided."
)
HTML_RULE = "Format as clean HTML using only <p>, <h2>, <h3>, <ul>, <li>, <strong>, <em>. No <html>/<body>/<h1> tags."

PROVIDERS = [
    {
        "id": "openai", "label": "OpenAI", "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": True},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "openrouter", "label": "OpenRouter", "protocol": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": True},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "anthropic", "label": "Anthropic (Claude)", "protocol": "anthropic",
        "base_url": "https://api.anthropic.com",
        "auth": {"header": "x-api-key", "prefix": "", "required": True},
        "headers": {"Content-Type": "application/json", "anthropic-version": "2023-06-01"},
        "chat": {
            "method": "POST", "path": "/v1/messages",
            "body": {
                "model": "{model}", "messages": "{chat_messages}", "system": "{system}",
                "temperature": "{temperature_anthropic}", "max_tokens": "{max_tokens_or_4096}",
            },
        },
        "response": {"text": "content", "usage": "usage"},
        "models": {"path": "/v1/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "gemini", "label": "Google Gemini", "protocol": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": True},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "groq", "label": "Groq", "protocol": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": True},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "deepseek", "label": "DeepSeek", "protocol": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": True},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "mistral", "label": "Mistral", "protocol": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": True},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "together", "label": "Together AI", "protocol": "openai",
        "base_url": "https://api.together.xyz/v1",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": True},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "ollama", "label": "Ollama (local)", "protocol": "openai",
        "base_url": "http://localhost:11434/v1",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": False},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
    {
        "id": "custom", "label": "Custom / Other", "protocol": "openai", "base_url": "",
        "auth": {"header": "Authorization", "prefix": "Bearer ", "required": True},
        "headers": {"Content-Type": "application/json"},
        "chat": {
            "method": "POST", "path": "/chat/completions",
            "body": {"model": "{model}", "messages": "{messages}", "temperature": "{temperature}", "max_tokens": "{max_tokens}"},
        },
        "response": {"text": "choices.0.message.content", "usage": "usage"},
        "models": {"path": "/models", "list": "data", "id": "id", "query": {}, "static": []},
    },
]

LANGUAGES = {
    "fa": "Persian (Farsi)", "en": "English", "ar": "Arabic", "tr": "Turkish",
    "de": "German", "fr": "French", "es": "Spanish", "ru": "Russian",
}

PROMPTS = {
    "product_description": {
        "system": DEFAULT_SYSTEM,
        "user": (
            "Write a complete product description in {language} for the product below.\n"
            "Product name: {name}\nProduct metadata (from the shop): {context}\n"
            "Known details: {details}\nFocus keywords: {keywords}\n"
            "Existing description (improve/reuse facts if present): {existing}\nTone: {tone}.\n"
            "Structure: short intro paragraph, a bullet list of key features, a closing paragraph. {html_rule}"
        ),
    },
    "product_short": {
        "system": DEFAULT_SYSTEM,
        "user": (
            "Write a short product summary (max 2 sentences, ~40 words) in {language} for '{name}'.\n"
            "Product metadata (from the shop): {context}\n"
            "Base it on this description if available: {description}\nOutput plain HTML with a single <p>."
        ),
    },
    "seo_meta": {
        "system": DEFAULT_SYSTEM,
        "user": (
            "Create SEO metadata in {language} for the page below.\nTitle: {title}\nFocus keyword: {keyword}\n"
            "Page metadata: {context}\nContent: {content}\n"
            'Return ONLY a JSON object: {"title": "<=60 chars", "description": "<=155 chars", '
            '"slug": "latin-lowercase-hyphenated", "focus_keyword": "..."}'
        ),
    },
    "rewrite": {
        "system": DEFAULT_SYSTEM,
        "user": (
            "Rewrite the text below in {language}. Instruction: {instruction}.\n"
            "Keep any HTML tags/structure that already exist.\n\nTEXT:\n{text}"
        ),
    },
    "translate": {
        "system": DEFAULT_SYSTEM,
        "user": "Translate the text below into {language}. Keep HTML tags unchanged.\n\nTEXT:\n{text}",
    },
    "post_outline": {
        "system": DEFAULT_SYSTEM,
        "user": (
            "Create a detailed blog article outline in {language} about: {topic}\n"
            "Article metadata (from the site): {context}\nKeywords: {keywords}\n"
            "Return a list of H2 headings, each with 2-3 bullet points. {html_rule}"
        ),
    },
    "post_draft": {
        "system": DEFAULT_SYSTEM,
        "user": (
            "Write a complete, original blog article in {language} (about {words} words) on: {topic}\n"
            "Article metadata (from the site): {context}\n"
            "Keywords to include naturally: {keywords}\nOutline to follow (optional): {outline}\n"
            "Use an engaging introduction, H2/H3 sections and a conclusion. {html_rule}"
        ),
    },
    "excerpt": {
        "system": DEFAULT_SYSTEM,
        "user": (
            "Write a 2-sentence excerpt in {language} (plain text, <=40 words) for this article:\n"
            "Article metadata: {context}\n{content}"
        ),
    },
    "suggest_tags": {
        "system": DEFAULT_SYSTEM,
        "user": (
            "Suggest 5-8 short tags in {language} for the content below. "
            "Return them comma-separated on one line.\nContext: {context}\n{content}"
        ),
    },
    "alt_text": {
        "system": DEFAULT_SYSTEM,
        "user": "Write a concise image alt text (<=100 chars) in {language} for a product photo of: {name}",
    },
    "seo_audit": {
        "system": (
            "You are a senior technical SEO auditor. You receive deterministic audit findings from a crawl. "
            "Use ONLY the supplied data; never invent facts, metrics or pages. Prioritize issues by impact on "
            "search visibility and conversion. Be concrete and concise. Output ONLY a JSON object, no markdown."
        ),
        "user": (
            "Analyze this SEO audit and write the result in {language}.\n"
            "Return a JSON object with these keys:\n"
            '  "summary": short overall assessment (2-4 sentences),\n'
            '  "priorities": array of up to 6 objects {"issue": "...", "impact": "...", "action": "..."},\n'
            '  "quick_wins": array of up to 6 short actionable strings,\n'
            '  "suggested_meta": {"title": "...", "description": "..."} respecting 60/155 character limits.\n'
            "Reference issue codes when useful. Do not repeat every finding. Do not suggest black-hat tactics.\n"
            "DATA:\n{data}"
        ),
    },
    "perf_analysis": {
        "system": (
            "You are a web performance engineer. You receive lab Core Web Vitals measurements and resource "
            "findings from a local headless Chromium. Use ONLY the supplied data; never invent numbers. "
            "Explain what is slow, why it matters and what to fix first. Output ONLY a JSON object."
        ),
        "user": (
            "Analyze this performance test and write the result in {language}.\n"
            'Return JSON with keys: "summary" (2-4 sentences), '
            '"priorities" (array of up to 6 objects with "issue", "impact", "action"), '
            '"quick_wins" (array of up to 6 strings).\n'
            "DATA:\n{data}"
        ),
    },
}

BUILTIN = {
    "schema_version": SCHEMA_VERSION,
    "version": "builtin-1",
    "providers": PROVIDERS,
    "languages": LANGUAGES,
    "prompts": PROMPTS,
}

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")


class CatalogError(ValueError):
    pass


def _safe_text(value, limit: int) -> str:
    text = str(value if value is not None else "")
    if len(text) > limit:
        raise CatalogError("Catalog field is too large")
    return text


def _safe_path(value, field: str) -> str:
    path = _safe_text(value, 1000).strip()
    if path and (not path.startswith("/") or ".." in path or "\n" in path or "\r" in path):
        raise CatalogError(f"Invalid {field}")
    return path


def _validate_provider(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise CatalogError("Provider must be an object")
    pid = _safe_text(raw.get("id"), 64).strip()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", pid):
        raise CatalogError("Invalid provider id")
    base_url = _safe_text(raw.get("base_url"), 1000).strip().rstrip("/")
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise CatalogError(f"Invalid base URL for provider {pid}")
    auth = raw.get("auth") if isinstance(raw.get("auth"), dict) else {}
    header = _safe_text(auth.get("header", ""), 100).strip()
    if header and not _HEADER_NAME.fullmatch(header):
        raise CatalogError(f"Invalid auth header for provider {pid}")
    prefix = _safe_text(auth.get("prefix", ""), 200)
    if "\n" in prefix or "\r" in prefix:
        raise CatalogError(f"Invalid auth prefix for provider {pid}")
    query_param = _safe_text(auth.get("query_param", ""), 100).strip()
    if query_param and not re.fullmatch(r"[A-Za-z0-9_-]+", query_param):
        raise CatalogError(f"Invalid auth query parameter for provider {pid}")
    required = bool(auth.get("required", True))
    if required and not header and not query_param:
        raise CatalogError(f"Provider {pid} requires an auth header or query parameter")
    headers = raw.get("headers") if isinstance(raw.get("headers"), dict) else {}
    clean_headers = {}
    for key, value in list(headers.items())[:30]:
        key, value = _safe_text(key, 100), _safe_text(value, 1000)
        if not _HEADER_NAME.fullmatch(key) or "\n" in value or "\r" in value:
            raise CatalogError(f"Invalid header for provider {pid}")
        clean_headers[key] = value
    chat = raw.get("chat") if isinstance(raw.get("chat"), dict) else {}
    body = chat.get("body") if isinstance(chat.get("body"), dict) else raw.get("body")
    if not isinstance(body, dict):
        raise CatalogError(f"Chat body is required for provider {pid}")
    response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
    models = raw.get("models") if isinstance(raw.get("models"), dict) else {}
    static_models = [str(m)[:200] for m in models.get("static", []) if str(m).strip()][:200]
    return {
        "id": pid,
        "label": _safe_text(raw.get("label") or pid, 120),
        "protocol": _safe_text(raw.get("protocol") or "openai", 40),
        "base_url": base_url,
        "auth": {"header": header, "prefix": prefix, "query_param": query_param, "required": required},
        "headers": clean_headers,
        "chat": {
            "method": _safe_text(chat.get("method") or "POST", 10).upper(),
            "path": _safe_path(chat.get("path", "/chat/completions"), "chat path"),
            "query": deepcopy(chat.get("query") or {}) if isinstance(chat.get("query"), dict) else {},
            "body": deepcopy(body),
        },
        "response": {
            "text": _safe_text(response.get("text") or "choices.0.message.content", 300),
            "usage": _safe_text(response.get("usage") or "usage", 300),
        },
        "models": {
            "path": _safe_path(models.get("path", "/models"), "models path"),
            "list": _safe_text(models.get("list") or "data", 300),
            "id": _safe_text(models.get("id") or "id", 300),
            "query": deepcopy(models.get("query") or {}) if isinstance(models.get("query"), dict) else {},
            "static": static_models,
        },
    }


def validate_remote(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise CatalogError("AI catalog must be a JSON object")
    if int(payload.get("schema_version", 0) or 0) != SCHEMA_VERSION:
        raise CatalogError("Unsupported AI catalog schema version")
    providers = payload.get("providers") or []
    prompts = payload.get("prompts") or {}
    languages = payload.get("languages") or {}
    if not isinstance(providers, list) or len(providers) > 50:
        raise CatalogError("Invalid providers list")
    if not isinstance(prompts, dict) or len(prompts) > 100:
        raise CatalogError("Invalid prompts")
    if not isinstance(languages, dict) or len(languages) > 50:
        raise CatalogError("Invalid languages")
    clean_prompts = {}
    for pid, raw in prompts.items():
        if not isinstance(pid, str) or not re.fullmatch(r"[a-zA-Z0-9_]+", pid) or not isinstance(raw, dict):
            raise CatalogError("Invalid prompt id")
        item = {}
        for key in ("system", "user"):
            if key in raw:
                item[key] = _safe_text(raw[key], 20000)
        if not item:
            continue
        if pid in PROMPTS:
            allowed = set()
            for key in ("system", "user"):
                allowed.update(_PLACEHOLDER.findall(PROMPTS[pid].get(key, "")))
            used = set()
            for text in item.values():
                used.update(_PLACEHOLDER.findall(text))
            unknown = used - allowed - {"html_rule"}
            if unknown:
                raise CatalogError(f"Unknown prompt variables for {pid}: {', '.join(sorted(unknown))}")
        clean_prompts[pid] = item
    clean_langs = {}
    for code, name in list(languages.items())[:50]:
        code, name = _safe_text(code, 12).strip(), _safe_text(name, 120).strip()
        if code and name:
            clean_langs[code] = name
    return {
        "schema_version": SCHEMA_VERSION,
        "version": _safe_text(payload.get("version") or "remote", 80),
        "providers": [_validate_provider(item) for item in providers],
        "prompts": clean_prompts,
        "languages": clean_langs,
        "server": deepcopy(payload.get("server") or {}) if isinstance(payload.get("server"), dict) else {},
    }


def _merge_dict(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _merge_prompts(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        current = result.get(key)
        if not isinstance(current, dict):
            continue
        merged = dict(current)
        merged.update(value)
        result[key] = merged
    return result


def _merge_providers(base: list[dict], override: list[dict]) -> list[dict]:
    result = deepcopy(base)
    by_id = {item["id"]: index for index, item in enumerate(result)}
    for item in override:
        if item["id"] in by_id:
            result[by_id[item["id"]]] = deepcopy(item)
        else:
            by_id[item["id"]] = len(result)
            result.append(deepcopy(item))
    return result


class AICatalog:
    def __init__(self):
        self._lock = threading.RLock()
        self._remote = self._read_cache()

    def _cache_path(self) -> Path:
        return data_dir() / "cache" / "ai_catalog.json"

    def _read_cache(self) -> dict:
        try:
            raw = json.loads(self._cache_path().read_text(encoding="utf-8"))
            if len(json.dumps(raw, ensure_ascii=False)) <= MAX_PAYLOAD_BYTES:
                return validate_remote(raw)
        except Exception:
            pass
        return {}

    def _write_cache(self, payload: dict) -> None:
        try:
            path = self._cache_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def _local_overrides(self) -> dict:
        try:
            from ..api import server_logic

            data = server_logic.call("ai_catalog_overrides")
            if isinstance(data, dict):
                return validate_remote({
                    "schema_version": SCHEMA_VERSION,
                    "version": "local",
                    "providers": data.get("providers") or [],
                    "prompts": data.get("prompts") or {},
                    "languages": data.get("languages") or {},
                })
        except Exception as exc:
            log.warning("Local AI catalog overrides failed: %s", exc)
        return {}

    def snapshot(self) -> dict:
        with self._lock:
            remote = deepcopy(self._remote)
        local = self._local_overrides()
        merged = deepcopy(BUILTIN)
        merged["providers"] = _merge_providers(merged["providers"], local.get("providers") or [])
        merged["prompts"] = _merge_prompts(merged["prompts"], local.get("prompts") or {})
        merged["languages"] = _merge_dict(merged["languages"], local.get("languages") or {})
        if remote:
            merged["providers"] = _merge_providers(merged["providers"], remote.get("providers") or [])
            merged["prompts"] = _merge_prompts(merged["prompts"], remote.get("prompts") or {})
            merged["languages"] = _merge_dict(merged["languages"], remote.get("languages") or {})
            merged["version"] = remote.get("version") or "remote"
            merged["server"] = remote.get("server") or {}
        return merged

    def providers(self) -> list[dict]:
        return self.snapshot()["providers"]

    def provider(self, provider_id: str) -> dict | None:
        for provider in self.providers():
            if provider["id"] == provider_id:
                return provider
        return None

    def resolve_provider(self, provider_id: str = "", base_url: str = "", api_format: str = "") -> dict:
        if provider_id:
            found = self.provider(provider_id)
            if found:
                return found
        normalized = (base_url or "").strip().rstrip("/")
        for provider in self.providers():
            if normalized and provider["base_url"] and normalized == provider["base_url"]:
                return provider
        wanted = "anthropic" if api_format == "anthropic" else "custom"
        return self.provider(wanted) or self.providers()[0]

    def languages(self) -> dict[str, str]:
        return self.snapshot()["languages"]

    def language(self, code: str) -> str:
        languages = self.languages()
        return languages.get(code, code)

    def prompt(self, action: str) -> dict:
        prompts = self.snapshot()["prompts"]
        spec = prompts.get(action)
        if not isinstance(spec, dict) or not isinstance(spec.get("user"), str):
            raise CatalogError(f"Prompt '{action}' is not available")
        return spec

    def server_info(self) -> dict:
        return self.snapshot().get("server") or {}

    def version(self) -> str:
        return str(self.snapshot().get("version") or "builtin-1")

    def apply_remote(self, payload: dict, persist: bool = True) -> dict:
        clean = validate_remote(payload)
        with self._lock:
            self._remote = clean
        if persist:
            self._write_cache(clean)
        return clean

    def reset_remote(self) -> None:
        with self._lock:
            self._remote = {}
        try:
            self._cache_path().unlink(missing_ok=True)
        except Exception:
            pass

    def refresh_from_server(self, server_url: str) -> dict:
        base = (server_url or "").strip().rstrip("/")
        if not base:
            raise CatalogError("Server URL is not set")
        from ..api import server_logic

        path = server_logic.call("endpoint", "ai_catalog")
        try:
            with httpx.Client(timeout=httpx.Timeout(20, connect=8), follow_redirects=True) as client:
                response = client.get(
                    base + path,
                    params={"version": SCHEMA_VERSION},
                    headers={"Accept": "application/json"},
                )
            response.raise_for_status()
            if len(response.content) > MAX_PAYLOAD_BYTES:
                raise CatalogError("AI catalog response is too large")
            return self.apply_remote(response.json())
        except httpx.HTTPError as exc:
            raise CatalogError(f"Could not refresh AI catalog: {exc}") from exc

    def render(self, action: str, values: dict) -> list[dict]:
        spec = self.prompt(action)
        merged = dict(values)
        merged.setdefault("html_rule", HTML_RULE)
        user = self.render_text(spec["user"], merged)
        system = spec.get("system", DEFAULT_SYSTEM)
        messages = []
        if system:
            messages.append({"role": "system", "content": self.render_text(system, merged, strict=False)})
        messages.append({"role": "user", "content": user})
        return messages

    @staticmethod
    def render_text(template: str, values: dict, strict: bool = True) -> str:
        missing = set()

        def replace(match):
            key = match.group(1)
            if key not in values:
                missing.add(key)
                return match.group(0)
            value = values[key]
            return str(value if value is not None else "")

        text = _PLACEHOLDER.sub(replace, template)
        if strict and missing:
            raise CatalogError(f"Prompt is missing values: {', '.join(sorted(missing))}")
        return text


catalog = AICatalog()
