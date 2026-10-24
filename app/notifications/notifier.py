from __future__ import annotations

import logging
import shutil
import subprocess
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from ..resources import branding_path

log = logging.getLogger("woodesk.notifications")


def _icon_path():
    for name in ("woocommerce-logo-256.png", "woocommerce-logo-128.png", "woodesk.ico"):
        path = branding_path(name)
        if path.exists():
            return path
    return branding_path("woocommerce-logo-256.png")


def _icon() -> QIcon:
    path = _icon_path()
    icon = QIcon(str(path)) if path.exists() else QIcon()
    return icon


class Notifier:
    def __init__(self):
        self._notify_send = shutil.which("notify-send") if sys.platform.startswith("linux") else None
        self._children: list[subprocess.Popen] = []
        self._tray = None
        if not self._notify_send and QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(_icon())
            self._tray.setToolTip("WooDesk Notifications")
            self._tray.show()

    def send(self, title: str, body: str) -> bool:
        if self._notify_send:
            self._children = [child for child in self._children if child.poll() is None]
            try:
                self._children.append(subprocess.Popen(
                    [self._notify_send, "--app-name=WooDesk", "--urgency=normal",
                     f"--icon={_icon_path()}", str(title), str(body)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                ))
                return True
            except Exception as exc:
                log.warning("notify-send failed: %s", exc)
        if self._tray:
            self._tray.showMessage(str(title), str(body), QSystemTrayIcon.Information, 10000)
            return True
        log.warning("No desktop notification service is available")
        return False
