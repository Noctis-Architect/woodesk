from __future__ import annotations

import logging
import sys
import time
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QLockFile, QObject, QTimer
from PySide6.QtWidgets import QApplication

from ..api.woo import WooClient
from ..core import secrets
from ..core.config import Config
from ..core.dynamic_loader import dynamic_manager
from ..core.module_updater import ModuleUpdater
from ..core.workers import run_async
from . import autostart, logic
from .controller import lock_path, log_path, stop_path
from .engine import detect_orders, detect_stock, orders_snapshot, stock_snapshot
from .notifier import Notifier
from .state import load_state, mark_inactive, save_state, site_state

log = logging.getLogger("woodesk.notifications")


def _secret_key(site_id: str, name: str) -> str:
    return f"site:{site_id}:{name}"


def _woo_for(site) -> WooClient | None:
    if site.use_woo_keys:
        key = secrets.get(_secret_key(site.id, "ck"))
        secret = secrets.get(_secret_key(site.id, "cs"))
        if not key or not secret:
            return None
        return WooClient(site.url, key, secret)
    password = secrets.get(_secret_key(site.id, "wp_password"))
    if not site.wp_user or not password:
        return None
    return WooClient(site.url, wp_user=site.wp_user, wp_password=password)


class NotificationWorker(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.notifier = Notifier()
        self.state = load_state()
        self._busy = False
        self._interval = 60
        self._updater: ModuleUpdater | None = None
        self._manifest_url = ""
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(60_000)
        self.poll_timer.timeout.connect(self.poll)
        self.control_timer = QTimer(self)
        self.control_timer.setInterval(3_000)
        self.control_timer.timeout.connect(self.control)

    def start(self) -> None:
        for name in ("remote_service", "notifications_service"):
            try:
                dynamic_manager.load_module(name)
            except Exception as exc:
                log.warning("Could not load dynamic module %s: %s", name, exc)
        self.control()
        self.control_timer.start()
        self.poll_timer.start()
        QTimer.singleShot(6_000, self.poll)

    def control(self) -> None:
        current = Config.load()
        settings = current.notifications
        if stop_path().exists() or not settings.active:
            autostart.remove()
            mark_inactive()
            log.info("Notifications disabled; background worker exiting")
            self.app.quit()
            return
        interval = logic.call("normalise_interval", settings.interval_seconds)
        if interval != self._interval:
            self._interval = interval
            self.poll_timer.setInterval(interval * 1000)
        self._ensure_updater(current.server_url)

    def _ensure_updater(self, server_url: str) -> None:
        manifest = f"{server_url.rstrip('/')}/v1/modules/manifest.json" if server_url else ""
        if manifest == self._manifest_url:
            return
        if self._updater:
            self._updater.stop_background_updater()
            self._updater = None
        self._manifest_url = manifest
        if not manifest:
            return
        self._updater = ModuleUpdater(manifest, loader=dynamic_manager, poll_interval_seconds=1800)
        self._updater.start_background_updater()

    def poll(self) -> None:
        if self._busy:
            return
        current = Config.load()
        if not current.notifications.active:
            self.control()
            return
        if not current.sites:
            return
        self._busy = True
        settings = current.notifications
        language = current.language
        sites = list(current.sites)
        run_async(self._check_all, sites, settings, language, ok=self._deliver,
                  err=self._failed)

    def _check_all(self, sites, settings, language: str) -> list[dict]:
        secrets.clear_cache()
        messages = []
        now = time.time()
        for site in sites:
            client = _woo_for(site)
            if client is None:
                log.warning("Notifications skipped for %s: WooCommerce credentials are missing", site.name)
                continue
            try:
                events = self._check_site(client, site, settings, now)
                for event in events:
                    if not logic.call("should_notify", event, settings):
                        continue
                    rendered = logic.call("format_notification", event, language)
                    if not isinstance(rendered, dict):
                        continue
                    title, body = str(rendered.get("title") or "").strip(), str(rendered.get("body") or "").strip()
                    if title and body:
                        messages.append({"title": title[:160], "body": body[:700]})
            except Exception as exc:
                log.warning("Notification check failed for %s: %s", site.name, exc)
            finally:
                try:
                    client.http.close()
                except Exception:
                    pass
        save_state(self.state)
        return messages[:8]

    def _check_site(self, client: WooClient, site, settings, now: float) -> list[dict]:
        current = site_state(self.state, site.id)
        active = set(current.get("active_types") or [])
        events = []

        if settings.out_of_stock:
            try:
                products = stock_snapshot(client)
                found = detect_stock(products, current, True, "out_of_stock" in active, now)
                for event in found:
                    event.update(site_id=site.id, site_name=site.name)
                    events.append(event)
                active.add("out_of_stock")
            except Exception as exc:
                log.warning("Stock check failed for %s: %s", site.name, exc)
        else:
            active.discard("out_of_stock")

        if settings.new_orders:
            try:
                orders = orders_snapshot(client)
                found = detect_orders(orders, current, True, "new_orders" in active, now)
                for event in found:
                    event.update(site_id=site.id, site_name=site.name)
                    events.append(event)
                active.add("new_orders")
            except Exception as exc:
                log.warning("Order check failed for %s: %s", site.name, exc)
        else:
            active.discard("new_orders")

        current["active_types"] = sorted(active)
        current["last_poll"] = int(now)
        save_state(self.state)
        return events

    def _deliver(self, messages: list[dict]) -> None:
        self._busy = False
        if stop_path().exists() or not Config.load().notifications.active:
            return
        for message in messages[:8]:
            self.notifier.send(message["title"], message["body"])

    def _failed(self, exc: Exception) -> None:
        self._busy = False
        log.warning("Background notification poll failed: %s", exc)

    def shutdown(self) -> None:
        self.control_timer.stop()
        self.poll_timer.stop()
        if self._updater:
            self._updater.stop_background_updater()


def _configure_logging() -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
    )


def main() -> int:
    _configure_logging()
    app = QApplication(["woodesk-notifications"])
    app.setApplicationName("WooDesk Notifications")
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(str(lock_path()))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(200):
        return 0

    try:
        config = Config.load()
        if stop_path().exists() or not config.notifications.active:
            autostart.remove()
            mark_inactive()
            return 0
        worker = NotificationWorker(app)
        app.aboutToQuit.connect(worker.shutdown)
        worker.start()
        return app.exec()
    finally:
        lock.unlock()


if __name__ == "__main__":
    sys.exit(main())
