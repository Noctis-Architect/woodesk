"""Client for the optional WooDesk server (free AI tier, stats, announcements)."""
from __future__ import annotations

import httpx

from ..ai.client import AIClient, AIResult, QuotaExceeded
from .http import ApiError, make_client, normalize_url, raise_for


class ServerClient(AIClient):
    def __init__(self, base_url: str, token: str = "", client: httpx.Client | None = None, gmail: str = ""):
        self.base = normalize_url(base_url)
        self.token = token
        self.gmail = gmail.strip().lower()
        self.http = client or make_client(timeout=90)

    def _headers(self) -> dict:
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.gmail:
            h["X-User-Gmail"] = self.gmail
        return h

    def _call(self, method: str, path: str, **kw):
        if not self.base:
            raise ApiError("Server URL is not set")
        try:
            r = self.http.request(method, self.base + path, headers=self._headers(), **kw)
        except httpx.HTTPError as e:
            raise ApiError(f"Connection to server failed: {e}") from e
        if r.status_code == 429:
            try:
                msg = r.json().get("detail", "Free quota reached")
            except Exception:
                msg = "Free quota reached"
            raise QuotaExceeded(str(msg), 429)
        raise_for(r)
        return r.json()

    # ---- public --------------------------------------------------------
    def config(self) -> dict:
        return self._call("GET", "/v1/config")

    def register(self, app_version: str, os_name: str) -> dict:
        return self._call("POST", "/v1/register", json={"app_version": app_version, "os": os_name})

    def announcements(self, version: str, lang: str) -> list[dict]:
        return self._call("GET", "/v1/announcements", params={"version": version, "lang": lang}).get("items", [])

    def free_models(self) -> list[str]:
        conf = self.config()
        return conf.get("models") or ([conf["model"]] if conf.get("model") else [])

    # ---- authenticated -------------------------------------------------
    def quota(self) -> dict:
        return self._call("GET", "/v1/quota")

    def telemetry(self, payload: dict) -> dict:
        return self._call("POST", "/v1/telemetry", json=payload)

    def telemetry_delete(self) -> dict:
        return self._call("DELETE", "/v1/telemetry")

    def chat(self, messages, temperature=0.7, max_tokens=None, model: str | None = None) -> AIResult:
        payload = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if model:
            payload["model"] = model
        if self.gmail:
            payload["gmail"] = self.gmail
        data = self._call("POST", "/v1/ai/chat", json=payload)
        return AIResult(data.get("content", ""), data.get("usage") or {}, data.get("remaining"))

    def send_feedback(self, subject: str, message: str, email: str = "", file_bytes: bytes | None = None, filename: str | None = None) -> dict:
        import base64
        payload = {
            "subject": subject.strip(),
            "message": message.strip(),
            "email": (email or self.gmail).strip(),
        }
        if file_bytes:
            payload["file_base64"] = base64.b64encode(file_bytes).decode("ascii")
            payload["filename"] = filename or "attachment"
        return self._call("POST", "/v1/feedback", json=payload)

