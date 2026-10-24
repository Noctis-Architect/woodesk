"""Client for the optional WooDesk server (free AI tier, stats, announcements).

The HTTP transport lives here (httpx) and stays fixed, while endpoint paths, payload shaping,
response parsing and telemetry policy are resolved through `server_logic.call`, which prefers the
hot-reloadable `remote_service` dynamic module and falls back to the built-in implementation.
"""
from __future__ import annotations

import httpx

from ..ai.client import AIClient, AIResult, QuotaExceeded
from .http import ApiError, make_client, normalize_url, raise_for
from . import server_logic


class ServerClient(AIClient):
    def __init__(self, base_url: str, token: str = "", client: httpx.Client | None = None, gmail: str = ""):
        self.base = normalize_url(base_url)
        self.token = token
        self.gmail = gmail.strip().lower()
        self.http = client or make_client(timeout=90)

    def _headers(self) -> dict:
        return server_logic.call("server_headers", self.token, self.gmail)

    def _path(self, name: str) -> str:
        return server_logic.call("endpoint", name)

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
        return self._call("GET", self._path("config"))

    def register(self, app_version: str, os_name: str) -> dict:
        return self._call("POST", self._path("register"), json={"app_version": app_version, "os": os_name})

    def announcements(self, version: str, lang: str) -> list[dict]:
        params = server_logic.call("announcements_params", version, lang)
        data = self._call("GET", self._path("announcements"), params=params)
        return server_logic.call("extract_announcements", data)

    def catalog(self) -> dict:
        return self._call("GET", self._path("ai_catalog"))

    def free_models(self) -> list[str]:
        conf = self.config()
        return conf.get("models") or ([conf["model"]] if conf.get("model") else [])

    # ---- authenticated -------------------------------------------------
    def quota(self) -> dict:
        return self._call("GET", self._path("quota"))

    def telemetry(self, payload: dict) -> dict:
        return self._call("POST", self._path("telemetry"), json=payload)

    def telemetry_delete(self) -> dict:
        return self._call("DELETE", self._path("telemetry"))

    def chat(self, messages, temperature=0.7, max_tokens=None, model: str | None = None) -> AIResult:
        req = server_logic.call("ai_chat_request", messages, temperature, max_tokens, model, self.gmail)
        data = self._call("POST", req["path"], json=req["json"])
        parsed = server_logic.call("parse_ai_response", data)
        return AIResult(parsed.get("content", ""), parsed.get("usage") or {}, parsed.get("remaining"))

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
        return self._call("POST", self._path("feedback"), json=payload)
