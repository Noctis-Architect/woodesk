# PyInstaller spec for WooDesk (Windows / Linux / macOS).
#
# Bundles the Python runtime, every third-party dependency, the UI assets and the dynamic
# `modules/` package into one self-contained folder (dist/WooDesk/), so end users do not need
# Python or any libraries installed. Build with:
#
#   python -m PyInstaller --noconfirm --clean packaging/woodesk.spec
#
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # project root (the spec lives in packaging/)

datas = [
    (str(ROOT / "app" / "assets"), "app/assets"),
    (str(ROOT / "modules"), "modules"),
] + collect_data_files("playwright")

hiddenimports = [
    "app.notifications.worker",
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
    "keyring.backends.libsecret",
    "keyring.backends.fail",
] + collect_submodules("keyring.backends") + collect_submodules("markdown.extensions") + collect_submodules("playwright")

icon = ROOT / "app" / "assets" / "branding" / "woodesk.ico"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WooDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon) if sys.platform == "win32" and icon.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WooDesk",
)
