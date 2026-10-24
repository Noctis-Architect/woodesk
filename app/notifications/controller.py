from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QLockFile

from ..core.config import NotificationSettings, cfg, data_dir
from . import autostart
from .state import mark_inactive

log = logging.getLogger("woodesk.notifications")


def lock_path() -> Path:
    return data_dir() / "notifications.lock"


def stop_path() -> Path:
    return data_dir() / "notifications.stop"


def log_path() -> Path:
    return data_dir() / "logs" / "notifications.log"


def stderr_path() -> Path:
    return data_dir() / "logs" / "notifications-stderr.log"


def notifications_active(settings: NotificationSettings | None = None) -> bool:
    settings = settings or cfg.notifications
    return settings.active


def worker_running() -> bool:
    probe = QLockFile(str(lock_path()))
    if probe.tryLock(0):
        probe.unlock()
        return False
    return True


def _spawn_worker() -> bool:
    if worker_running():
        return True
    command = autostart.worker_command()
    log_file = stderr_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {"cwd": str(Path(__file__).resolve().parents[2]), "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        with log_file.open("a", encoding="utf-8") as stderr:
            subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=stderr, **kwargs)
        return True
    except Exception as exc:
        log.warning("Could not start notification worker: %s", exc)
        return False


def sync_background(spawn: bool = True) -> bool:
    """Enable or fully disable the background notification process and its autostart entry."""
    if notifications_active():
        try:
            if stop_path().exists():
                mark_inactive()
            stop_path().unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not clear notification stop marker: %s", exc)
        autostart.install()
        if spawn:
            _spawn_worker()
        return True

    try:
        stop_path().write_text("disabled\n", encoding="utf-8")
    except OSError as exc:
        log.warning("Could not write notification stop marker: %s", exc)
    autostart.remove()
    return False
