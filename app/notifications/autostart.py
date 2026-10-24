from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

APP_ID = "woodesk-notifications"
WINDOWS_VALUE = "WooDesk Notifications"


def worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), "--notification-worker"]
    python = Path(sys.executable)
    if os.name == "nt":
        windowless = python.with_name("pythonw.exe")
        if windowless.exists():
            python = windowless
    root = Path(__file__).resolve().parents[2]
    return [str(python), str(root / "run.py"), "--notification-worker"]


def _desktop_quote(value: str) -> str:
    value = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    value = value.replace("`", "\\`").replace("$", "\\$")
    return f'"{value}"'


def _desktop_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / f"{APP_ID}.desktop"


def _mac_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "org.woodesk.notifications.plist"


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def install() -> bool:
    try:
        command = worker_command()
        if sys.platform == "win32":
            import winreg

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.SetValueEx(key, WINDOWS_VALUE, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            return True
        if sys.platform == "darwin":
            path = _mac_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "Label": "org.woodesk.notifications",
                "ProgramArguments": command,
                "RunAtLoad": True,
                "ProcessType": "Interactive",
            }
            path.write_bytes(plistlib.dumps(payload))
            return True
        if sys.platform.startswith("linux"):
            path = _desktop_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            root = _source_root() if not getattr(sys, "frozen", False) else Path(sys.executable).resolve().parent
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=WooDesk Notifications\n"
                "Comment=Background stock and order notifications for WooDesk\n"
                f"Exec={' '.join(_desktop_quote(part) for part in command)}\n"
                f"Path={root}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
                "NoDisplay=true\n"
            )
            path.write_text(content, encoding="utf-8")
            return True
    except Exception:
        return False
    return False


def remove() -> bool:
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, WINDOWS_VALUE)
            return True
        if sys.platform == "darwin":
            _mac_path().unlink(missing_ok=True)
            return True
        if sys.platform.startswith("linux"):
            _desktop_path().unlink(missing_ok=True)
            return True
    except FileNotFoundError:
        return True
    except Exception:
        return False
    return False


def installed() -> bool:
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_QUERY_VALUE) as key:
                winreg.QueryValueEx(key, WINDOWS_VALUE)
            return True
        if sys.platform == "darwin":
            return _mac_path().exists()
        if sys.platform.startswith("linux"):
            return _desktop_path().exists()
    except Exception:
        return False
    return False
