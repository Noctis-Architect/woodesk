from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .core.config import cfg
from .core.context import AppContext
from .core.dynamic_loader import dynamic_manager
from .core.module_updater import ModuleUpdater
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def resource_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)  # PyInstaller
    return Path(base) / "app" if base else Path(__file__).parent


def load_font() -> str:
    family = "Segoe UI"
    fonts = resource_dir() / "assets" / "fonts"
    if fonts.exists():
        for f in sorted(fonts.glob("*.ttf")):
            fid = QFontDatabase.addApplicationFont(str(f))
            if fid >= 0:
                family = QFontDatabase.applicationFontFamilies(fid)[0]
    return family


def make_icon() -> QIcon:
    pm = QPixmap(128, 128)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#6c5ce7"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 120, 120, 28, 28)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", 54)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "W")
    p.end()
    return QIcon(pm)


def create_app(argv=None):
    app = QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    family = load_font()
    app.setFont(QFont(family, 10))
    app.setLayoutDirection(Qt.RightToLeft if cfg.language == "fa" else Qt.LeftToRight)
    apply_theme(app, family, cfg.theme)
    ctx = AppContext()
    win = MainWindow(ctx, family, make_icon())
    return app, ctx, win


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("WooDesk")

    # 1. Initialize Dynamic Module Manager & preload core dynamic modules
    try:
        dynamic_manager.load_module("remote_service")
        logger.info("Dynamic remote_service loaded successfully.")
    except Exception as e:
        logger.warning("Could not preload dynamic module on startup: %s", e)

    # 2. Setup background ModuleUpdater if server URL is configured
    updater: ModuleUpdater | None = None
    if cfg.server_url:
        manifest_url = f"{cfg.server_url.rstrip('/')}/v1/modules/manifest.json"
        updater = ModuleUpdater(manifest_url, loader=dynamic_manager, poll_interval_seconds=1800)
        updater.start_background_updater()

    app, ctx, win = create_app()

    # Graceful shutdown of updater thread on exit
    if updater:
        app.aboutToQuit.connect(updater.stop_background_updater)

    win.show()
    ctx.start_background()
    QTimer.singleShot(800, win.first_run_notice)
    sys.exit(app.exec())

