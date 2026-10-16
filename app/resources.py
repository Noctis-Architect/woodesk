"""Locate bundled resources (assets, branding) in source, PyInstaller and Nuitka builds."""
from __future__ import annotations

import sys
from pathlib import Path


def resource_dir() -> Path:
    """Directory that contains the bundled `assets/` folder, regardless of build layout."""
    meipass = getattr(sys, "_MEIPASS", None)  # PyInstaller onefile/onedir
    if meipass:
        candidate = Path(meipass) / "app"
        return candidate if candidate.exists() else Path(meipass)

    if getattr(sys, "frozen", False):  # Nuitka / other frozen builds
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (exe_dir / "app", exe_dir / "_internal" / "app", exe_dir):
            if (candidate / "assets").exists():
                return candidate

    return Path(__file__).resolve().parent


def asset_path(*parts: str) -> Path:
    return resource_dir() / "assets" / Path(*parts)


def branding_path(name: str) -> Path:
    return asset_path("branding", name)
