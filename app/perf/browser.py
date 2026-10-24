from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class BrowserUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserChoice:
    kind: str  # "default" or "executable"
    path: str = ""
    label: str = ""

    def describe(self) -> str:
        return self.label or ("Playwright Chromium" if self.kind == "default" else self.path)


def _cache_roots() -> list[Path]:
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        return [Path(override)]
    home = Path.home()
    roots = [home / ".cache" / "ms-playwright"]
    if sys.platform == "darwin":
        roots.append(home / "Library" / "Caches" / "ms-playwright")
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local) / "ms-playwright")
    return roots


def _cached_candidates() -> list[Path]:
    out: list[Path] = []
    patterns = [
        "chromium-*/chrome-linux64/chrome",
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chromium-*/chrome-win/chrome.exe",
        "chromium-*/chrome-win64/chrome.exe",
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium_headless_shell-*/chrome-headless-shell-linux/chrome-headless-shell",
    ]
    for root in _cache_roots():
        if not root.exists():
            continue
        for pattern in patterns:
            out.extend(sorted(root.glob(pattern), reverse=True))
    return out


def _system_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("WOODESK_BROWSER_PATH")
    if override:
        candidates.append(Path(override))
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge"]
    for name in names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    if sys.platform == "win32":
        roots = [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""),
                 os.environ.get("LOCALAPPDATA", "")]
        rels = [
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
            r"Chromium\Application\chrome.exe",
        ]
        for root in roots:
            if root:
                for rel in rels:
                    candidates.append(Path(root) / rel)
    elif sys.platform == "darwin":
        candidates += [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    return candidates


def candidates() -> list[BrowserChoice]:
    out = [BrowserChoice("default", label="Playwright Chromium")]
    seen: set[str] = set()
    for path in [*_cached_candidates(), *_system_candidates()]:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        out.append(BrowserChoice("executable", key, key))
    return out


def launch(playwright, headless: bool = True):
    """Launch the first usable Chromium. Returns (browser, BrowserChoice)."""
    errors: list[str] = []
    args = ["--no-sandbox"] if hasattr(os, "geteuid") and os.geteuid() == 0 else []
    for choice in candidates():
        try:
            kwargs = {"headless": headless, "args": args}
            if choice.kind == "executable":
                kwargs["executable_path"] = choice.path
            browser = playwright.chromium.launch(**kwargs)
            return browser, choice
        except Exception as exc:  # noqa: BLE001 - try the next candidate
            errors.append(f"{choice.describe()}: {str(exc).splitlines()[0][:160]}")
    detail = "\n".join(errors[:4]) or "no Chromium binary found"
    raise BrowserUnavailable(
        "No usable Chromium found. Install Chrome/Edge/Chromium, or run "
        f"`{Path(sys.executable).name} -m playwright install chromium`.\n{detail}")


def install_chromium() -> tuple[bool, str]:
    """Download Playwright's Chromium. Blocking; call from a worker thread."""
    try:
        from playwright._impl._driver import compute_driver_executable

        node, cli = compute_driver_executable()
        command = [str(node), str(cli), "install", "chromium"]
    except Exception:
        command = [sys.executable, "-m", "playwright", "install", "chromium"]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=900)
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, output.strip()[-2000:]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def browser_note() -> str:
    return (
        "Speed tests use a hidden local Chromium. Install Chrome, Edge or Chromium, "
        "or download Playwright's Chromium from Settings."
    )
