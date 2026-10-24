"""Persistent, non-secret settings. Secrets live in the OS keyring (see secrets.py)."""
from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

# Set this to your own server before building releases (users can change it in Settings).
DEFAULT_SERVER_URL = os.environ.get("WOODESK_SERVER_URL", "https://woodesk.wp-hub.org")
_save_lock = threading.Lock()


def data_dir() -> Path:
    override = os.environ.get("WOODESK_HOME")
    if override:
        d = Path(override)
    else:
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        d = base / "WooDesk"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Site:
    id: str
    name: str
    url: str
    wp_user: str = ""
    # True: WooCommerce consumer key/secret; False: reuse the WordPress application password
    use_woo_keys: bool = True


@dataclass
class AISettings:
    mode: str = "server"  # "server" (free tier from the project server) | "custom" (own key)
    provider_id: str = ""  # id from the dynamic AI catalog; empty = infer from api_format/base_url
    api_format: str = "openai"  # legacy protocol hint, kept in sync from the provider profile
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    server_model: str = ""  # selected model when mode == "server"
    temperature: float = 0.7
    output_language: str = "fa"
    gmail: str = ""  # required for server free AI tier



@dataclass
class NotificationSettings:
    enabled: bool = True
    out_of_stock: bool = True
    new_orders: bool = False
    interval_seconds: int = 60

    @property
    def active(self) -> bool:
        return bool(self.enabled and (self.out_of_stock or self.new_orders))


@dataclass
class SeoSettings:
    rendered: bool = True
    check_links: bool = True
    max_links: int = 8
    max_pages: int = 20
    delay_ms: int = 250
    perf_device: str = "mobile"
    perf_runs: int = 3


@dataclass
class Config:
    language: str = "fa"
    theme: str = "system"  # "system" | "light" | "dark"
    telemetry: bool = True  # anonymous usage statistics (opt-out)
    announcements: bool = True
    server_url: str = DEFAULT_SERVER_URL
    sites: list = field(default_factory=list)
    active_site: str = ""
    ai: AISettings = field(default_factory=AISettings)
    seo: SeoSettings = field(default_factory=SeoSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    install_id: str = ""
    seen_announcements: list = field(default_factory=list)
    last_telemetry: float = 0.0
    telemetry_notice_shown: bool = False

    # ---- persistence -------------------------------------------------
    @property
    def path(self) -> Path:
        return data_dir() / "config.json"

    def save(self) -> None:
        with _save_lock:
            raw = asdict(self)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    @classmethod
    def load(cls) -> "Config":
        c = cls()
        p = data_dir() / "config.json"
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return c
            known = {f.name for f in fields(cls)}
            for k, v in raw.items():
                if k not in known or k in ("sites", "ai", "seo", "notifications"):
                    continue
                setattr(c, k, v)
            site_keys = {f.name for f in fields(Site)}
            c.sites = [Site(**{k: v for k, v in s.items() if k in site_keys}) for s in raw.get("sites", [])]
            ai_keys = {f.name for f in fields(AISettings)}
            c.ai = AISettings(**{k: v for k, v in raw.get("ai", {}).items() if k in ai_keys})
            seo_keys = {f.name for f in fields(SeoSettings)}
            c.seo = SeoSettings(**{k: v for k, v in raw.get("seo", {}).items() if k in seo_keys})
            notify_keys = {f.name for f in fields(NotificationSettings)}
            c.notifications = NotificationSettings(**{
                k: v for k, v in raw.get("notifications", {}).items() if k in notify_keys
            })
            try:
                c.notifications.interval_seconds = max(30, min(900, int(c.notifications.interval_seconds)))
            except (TypeError, ValueError):
                c.notifications.interval_seconds = 60
        return c

    # ---- helpers -----------------------------------------------------
    def site(self, site_id: str | None = None) -> Site | None:
        sid = site_id or self.active_site
        for s in self.sites:
            if s.id == sid:
                return s
        return self.sites[0] if (self.sites and not site_id) else None

    def add_site(self, site: Site) -> None:
        self.sites.append(site)
        if not self.active_site:
            self.active_site = site.id

    def remove_site(self, site_id: str) -> None:
        self.sites = [s for s in self.sites if s.id != site_id]
        if self.active_site == site_id:
            self.active_site = self.sites[0].id if self.sites else ""


def new_id() -> str:
    return uuid.uuid4().hex[:12]


cfg = Config.load()
