from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from ..api.http import ApiError, make_client, raise_for

PRESETS = [
    # (label, api_format, base_url)
    ("OpenAI", "openai", "https://api.openai.com/v1"),
    ("OpenRouter", "openai", "https://openrouter.ai/api/v1"),
    ("Anthropic (Claude)", "anthropic", "https://api.anthropic.com"),
    ("Google Gemini", "openai", "https://generativelanguage.googleapis.com/v1beta/openai"),
    ("Groq", "openai", "https://api.groq.com/openai/v1"),
    ("DeepSeek", "openai", "https://api.deepseek.com/v1"),
    ("Mistral", "openai", "https://api.mistral.ai/v1"),
    ("Together AI", "openai", "https://api.together.xyz/v1"),
    ("Ollama (local)", "openai", "http://localhost:11434/v1"),
    ("Custom / Other", "openai", ""),
]


@dataclass
class AIResult:
    text: str
    usage: dict = field(default_factory=dict)
    remaining: int | None = None


class QuotaExceeded(ApiError):
    pass


class AIClient:
    def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int | None = None) -> AIResult:
        raise NotImplementedError


class OpenAICompatClient(AIClient):
    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.Client | None = None):
        self.base = (base_url or "").strip().rstrip("/")
        self.key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.http = client or make_client(timeout=120)

    def _root(self) -> str:
        b = self.base
        for suffix in ("/chat/completions", "/completions"):
            if b.endswith(suffix):
                b = b[: -len(suffix)]
        return b

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.key:
            h["Authorization"] = f"Bearer {self.key}"
        return h

    def chat(self, messages, temperature=0.7, max_tokens=None) -> AIResult:
        if not self.base:
            raise ApiError("AI base URL is not set")
        if not self.model:
            raise ApiError("AI model is not set")
        body = {"model": self.model, "messages": messages, "temperature": temperature}
        if max_tokens:
            body["max_tokens"] = max_tokens
        try:
            r = self.http.post(self._root() + "/chat/completions", json=body, headers=self._headers())
        except httpx.HTTPError as e:
            raise ApiError(f"Connection failed: {e}") from e
        raise_for(r)
        try:
            data = r.json()
            text = data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            raise ApiError("Unexpected response from the AI provider") from e
        return AIResult(text.strip(), data.get("usage") or {})

    def list_models(self) -> list[str]:
        try:
            r = self.http.get(self._root() + "/models", headers=self._headers())
        except httpx.HTTPError as e:
            raise ApiError(f"Connection failed: {e}") from e
        raise_for(r)
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        ids = []
        for m in items:
            mid = m.get("id") or m.get("name") if isinstance(m, dict) else str(m)
            if mid:
                ids.append(mid.replace("models/", ""))
        return sorted(ids)


class AnthropicClient(AIClient):
    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.Client | None = None):
        self.base = (base_url or "https://api.anthropic.com").strip().rstrip("/")
        if self.base.endswith("/v1/messages"):
            self.base = self.base[: -len("/v1/messages")]
        self.key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.http = client or make_client(timeout=120)

    def _headers(self):
        return {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def chat(self, messages, temperature=0.7, max_tokens=None) -> AIResult:
        if not self.model:
            raise ApiError("AI model is not set")
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        body = {"model": self.model, "messages": turns, "max_tokens": max_tokens or 4096, "temperature": min(temperature, 1.0)}
        if system:
            body["system"] = system
        try:
            r = self.http.post(self.base + "/v1/messages", json=body, headers=self._headers())
        except httpx.HTTPError as e:
            raise ApiError(f"Connection failed: {e}") from e
        raise_for(r)
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage") or {}
        return AIResult(text.strip(), {"total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)})

    def list_models(self) -> list[str]:
        try:
            r = self.http.get(self.base + "/v1/models", headers=self._headers())
        except httpx.HTTPError as e:
            raise ApiError(f"Connection failed: {e}") from e
        raise_for(r)
        return sorted(m["id"] for m in r.json().get("data", []))
