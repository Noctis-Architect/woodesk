"""Application-wide state: active site clients, AI client, server session, background jobs."""
from __future__ import annotations

import platform
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .. import __version__
from ..ai.client import AIClient, AIResult, AnthropicClient, OpenAICompatClient
from ..api.http import ApiError, domain_of
from ..api.server import ServerClient
from ..api.woo import WooClient
from ..api.wp import WPClient
from . import secrets
from .config import cfg
from .workers import run_async

TELEMETRY_INTERVAL = 20 * 3600
ANNOUNCE_INTERVAL = 3 * 3600


class NotConfigured(ApiError):
    pass


def secret_key(site_id: str, name: str) -> str:
    return f"site:{site_id}:{name}"


class AppContext(QObject):
    site_changed = Signal()
    announcements_changed = Signal()
    new_announcements = Signal(list)
    popup_message = Signal(dict)

    def __init__(self):
        super().__init__()
        self._wp: WPClient | None = None
        self._woo: WooClient | None = None
        self._ai_cache: tuple | None = None  # (settings signature, client) - keeps the HTTPS connection warm
        self._srv_cache: tuple | None = None
        self._cache: dict = {}  # per-site lookups (categories) that rarely change
        self.announcements: list[dict] = []
        self._last_announce = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ---- sites ---------------------------------------------------------
    def site(self):
        return cfg.site()

    def has_site(self) -> bool:
        return cfg.site() is not None

    def has_wp(self) -> bool:
        """True when WordPress credentials (username + application password) are configured."""
        s = cfg.site()
        return bool(s and s.wp_user and secrets.get(secret_key(s.id, "wp_password")))

    def reload_clients(self) -> None:
        self._wp = self._woo = None
        self._cache.clear()
        self.site_changed.emit()

    def set_active_site(self, site_id: str) -> None:
        cfg.active_site = site_id
        cfg.save()
        self.reload_clients()

    def wp(self) -> WPClient:
        s = cfg.site()
        if not s:
            raise NotConfigured("No site configured. Add a site in Settings first.")
        if self._wp is None:
            self._wp = WPClient(s.url, s.wp_user, secrets.get(secret_key(s.id, "wp_password")))
        return self._wp

    def woo(self) -> WooClient:
        s = cfg.site()
        if not s:
            raise NotConfigured("No site configured. Add a site in Settings first.")
        if self._woo is None:
            if s.use_woo_keys:
                self._woo = WooClient(s.url, secrets.get(secret_key(s.id, "ck")), secrets.get(secret_key(s.id, "cs")))
            else:
                self._woo = WooClient(s.url, wp_user=s.wp_user, wp_password=secrets.get(secret_key(s.id, "wp_password")))
        return self._woo

    # ---- cached lookups (call from worker threads) -----------------------
    def _cached(self, key: str, fn, refresh: bool = False):
        k = (cfg.active_site, key)
        if refresh or k not in self._cache:
            self._cache[k] = fn()
        return list(self._cache[k])

    def woo_categories(self, refresh: bool = False) -> list:
        return self._cached("woo_cats", lambda: self.woo().categories(), refresh)

    def wp_categories(self, refresh: bool = False) -> list:
        return self._cached("wp_cats", lambda: self.wp().categories(), refresh)

    def create_woo_category(self, name: str) -> dict:
        cat = self.woo().create_category(name)
        self._cache.pop((cfg.active_site, "woo_cats"), None)
        return cat

    def create_wp_category(self, name: str) -> dict:
        cat = self.wp().create_category(name)
        self._cache.pop((cfg.active_site, "wp_cats"), None)
        return cat

    # ---- server session --------------------------------------------------
    def server(self) -> ServerClient:
        if not cfg.server_url:
            raise NotConfigured("Server URL is not set (Settings > Server & privacy).")
        return ServerClient(cfg.server_url, secrets.get("server:token"), gmail=cfg.ai.gmail)

    def ensure_registered(self) -> ServerClient:
        """Blocking - call from a worker thread."""
        srv = self.server()
        if srv.token and cfg.install_id:
            sig = (cfg.server_url, srv.token, cfg.ai.gmail)
            if self._srv_cache and self._srv_cache[0] == sig:
                return self._srv_cache[1]
            self._srv_cache = (sig, srv)
            return srv
        res = srv.register(__version__, f"{platform.system()} {platform.release()}")
        cfg.install_id = res["install_id"]
        secrets.set("server:token", res["token"])
        cfg.save()
        return ServerClient(cfg.server_url, res["token"], gmail=cfg.ai.gmail)

    def reset_server_session(self) -> None:
        cfg.install_id = ""
        self._srv_cache = None
        secrets.delete("server:token")
        cfg.save()

    def send_feedback(self, subject: str, message: str, email: str = "", file_bytes: bytes | None = None, filename: str | None = None) -> dict:
        """Sends feedback and optional attachment to the server. No local history kept."""
        srv = self.ensure_registered()
        return srv.send_feedback(subject, message, email or cfg.ai.gmail, file_bytes, filename)

    # ---- AI ------------------------------------------------------------
    def ai_client(self) -> AIClient:
        a = cfg.ai
        if a.mode == "server":
            return self.ensure_registered()
        key = secrets.get("ai:api_key")
        sig = (a.api_format, a.base_url, a.model, key)
        if self._ai_cache and self._ai_cache[0] == sig:
            return self._ai_cache[1]
        cls = AnthropicClient if a.api_format == "anthropic" else OpenAICompatClient
        client = cls(a.base_url, key, a.model)
        self._ai_cache = (sig, client)
        return client

    def ai_chat(self, messages: list[dict], max_tokens: int | None = None, temperature: float | None = None, model: str | None = None) -> AIResult:
        """Blocking - call from a worker thread."""
        temp = cfg.ai.temperature if temperature is None else temperature
        client = self.ai_client()
        try:
            if isinstance(client, ServerClient):
                chosen_model = model or cfg.ai.server_model or None
                return client.chat(messages, temp, max_tokens, model=chosen_model)
            return client.chat(messages, temp, max_tokens)
        except ApiError as e:
            if cfg.ai.mode == "server" and e.status == 401:
                self.reset_server_session()
                return self.ai_chat(messages, max_tokens, temperature, model)
            raise

    # ---- telemetry & announcements ---------------------------------------
    def start_background(self) -> None:
        self._timer.start(30 * 60 * 1000)
        QTimer.singleShot(1500, self._tick)

    def _tick(self) -> None:
        if not cfg.server_url:
            return
        run_async(self._background_work, ok=self._background_done)

    def _background_work(self):
        now = time.time()
        if cfg.telemetry and now - cfg.last_telemetry > TELEMETRY_INTERVAL:
            try:
                srv = self.ensure_registered()
                srv.telemetry({
                    "app_version": __version__,
                    "os": f"{platform.system()} {platform.release()}",
                    "lang": cfg.language,
                    "sites": sorted({domain_of(s.url) for s in cfg.sites if s.url}),
                })
                cfg.last_telemetry = now
                cfg.save()
            except Exception:
                pass  # statistics must never disturb the user
        items = None
        if cfg.announcements:
            try:
                items = ServerClient(cfg.server_url).announcements(__version__, cfg.language)
                self._last_announce = now
            except Exception:
                items = None
        return items

    def _background_done(self, items) -> None:
        if items is None:
            return
        old = {a["id"] for a in self.announcements}
        self.announcements = items
        self.announcements_changed.emit()
        fresh = [a for a in items if a["id"] not in old and a["id"] not in cfg.seen_announcements]
        if fresh:
            self.new_announcements.emit(fresh)
            for a in fresh:
                if a.get("is_popup") or a.get("level") == "urgent":
                    self.popup_message.emit(a)


    def unseen_announcements(self) -> list[dict]:
        return [a for a in self.announcements if a["id"] not in cfg.seen_announcements]

    def mark_announcements_seen(self) -> None:
        cfg.seen_announcements = sorted(set(cfg.seen_announcements) | {a["id"] for a in self.announcements})[-200:]
        cfg.save()
        self.announcements_changed.emit()

    def set_telemetry(self, enabled: bool) -> None:
        cfg.telemetry = enabled
        cfg.save()
        if not enabled and cfg.server_url and secrets.get("server:token"):
            run_async(lambda: self.server().telemetry_delete())  # best effort: remove stored site list
        elif enabled:
            cfg.last_telemetry = 0
            self._tick()
