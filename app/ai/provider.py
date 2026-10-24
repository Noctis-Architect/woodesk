from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import httpx

from ..api.http import ApiError, make_client, raise_for
from .client import AIClient, AIResult

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _render(value: Any, values: dict) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, values) for item in value]
    if not isinstance(value, str):
        return value
    exact = _PLACEHOLDER.fullmatch(value)
    if exact and exact.group(1) in values:
        return deepcopy(values[exact.group(1)])
    return _PLACEHOLDER.sub(
        lambda match: str(values.get(match.group(1), match.group(0))),
        value,
    )


def _path(value: Any, path: str) -> Any:
    current = value
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _messages_for(provider: dict, messages: list[dict]) -> dict:
    clean = []
    for message in messages:
        role = message.get("role", "user")
        if role not in ("system", "user", "assistant"):
            role = "user"
        clean.append({"role": role, "content": str(message.get("content", ""))})
    system = "\n".join(item["content"] for item in clean if item["role"] == "system")
    return {
        "messages": clean,
        "chat_messages": [item for item in clean if item["role"] != "system"],
        "system": system,
    }


class DynamicProviderClient(AIClient):
    """Executes a provider definition supplied by the dynamic AI catalog."""

    def __init__(self, provider: dict, base_url: str, api_key: str, model: str,
                 client: httpx.Client | None = None):
        self.provider = deepcopy(provider)
        self.base = (base_url or self.provider.get("base_url") or "").strip().rstrip("/")
        self.key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.http = client or make_client(timeout=120)

    @property
    def label(self) -> str:
        return str(self.provider.get("label") or self.provider.get("id") or "AI provider")

    def _auth(self) -> dict:
        auth = self.provider.get("auth") or {}
        if auth.get("required", True) and not self.key:
            raise ApiError(f"{self.label} API key is not set")
        headers = {str(key): str(value) for key, value in (self.provider.get("headers") or {}).items()}
        header = str(auth.get("header") or "").strip()
        if header and self.key:
            headers[header] = str(auth.get("prefix") or "") + self.key
        headers.setdefault("Accept", "application/json")
        params = {}
        query_param = str(auth.get("query_param") or "").strip()
        if query_param and self.key:
            params[query_param] = self.key
        return {"headers": headers, "params": params}

    def _url(self, path: str) -> str:
        if not self.base:
            raise ApiError(f"{self.label} base URL is not set")
        path = str(path or "")
        if path and self.base.endswith(path):
            return self.base
        return self.base + path

    def _chat_body(self, messages: list[dict], temperature: float, max_tokens: int | None) -> dict:
        values = _messages_for(self.provider, messages)
        values.update({
            "model": self.model,
            "temperature": max(0.0, min(float(temperature), 2.0)),
            "temperature_anthropic": max(0.0, min(float(temperature), 1.0)),
            "max_tokens": max_tokens,
            "max_tokens_or_4096": int(max_tokens or 4096),
        })
        body = _render((self.provider.get("chat") or {}).get("body") or {}, values)
        if not isinstance(body, dict):
            raise ApiError(f"{self.label} returned an invalid request body")
        return {key: value for key, value in body.items() if value is not None and value != ""}

    def chat(self, messages, temperature=0.7, max_tokens=None) -> AIResult:
        if not self.model:
            raise ApiError(f"{self.label} model is not set")
        chat = self.provider.get("chat") or {}
        method = str(chat.get("method") or "POST").upper()
        url = self._url(str(chat.get("path") or ""))
        auth = self._auth()
        params = {str(key): str(value) for key, value in (chat.get("query") or {}).items()}
        params.update(auth["params"])
        try:
            response = self.http.request(
                method, url, headers=auth["headers"], params=params or None,
                json=self._chat_body(messages, temperature, max_tokens),
            )
        except httpx.HTTPError as exc:
            raise ApiError(f"Connection failed: {exc}") from exc
        raise_for(response)
        try:
            data = response.json()
        except Exception as exc:
            raise ApiError(f"{self.label} did not return JSON") from exc
        response_map = self.provider.get("response") or {}
        content = _path(data, str(response_map.get("text") or "choices.0.message.content"))
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) for item in content
                if isinstance(item, dict) and item.get("type") in (None, "text")
            )
        if not isinstance(content, str):
            raise ApiError(f"Unexpected response shape from {self.label}")
        usage = _path(data, str(response_map.get("usage") or "usage"))
        return AIResult(content.strip(), usage if isinstance(usage, dict) else {})

    def list_models(self) -> list[str]:
        models = self.provider.get("models") or {}
        static = [str(model) for model in models.get("static") or [] if str(model).strip()]
        path = str(models.get("path") or "")
        if not path:
            return sorted(set(static))
        auth = self._auth()
        params = {str(key): str(value) for key, value in (models.get("query") or {}).items()}
        params.update(auth["params"])
        try:
            response = self.http.get(
                self._url(path), headers=auth["headers"], params=params or None,
            )
        except httpx.HTTPError as exc:
            raise ApiError(f"Connection failed: {exc}") from exc
        raise_for(response)
        try:
            data = response.json()
        except Exception as exc:
            raise ApiError(f"{self.label} did not return a JSON model list") from exc
        items = _path(data, str(models.get("list") or "data"))
        if not isinstance(items, list):
            raise ApiError(f"Unexpected model list from {self.label}")
        ids = []
        for item in items:
            value = _path(item, str(models.get("id") or "id")) if isinstance(item, dict) else item
            if value is not None and str(value).strip():
                model_id = str(value).strip()
                ids.append(model_id[len("models/"):] if model_id.startswith("models/") else model_id)
        return sorted(set(ids + static))
