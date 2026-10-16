from __future__ import annotations

import html
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QStackedWidget, QSystemTrayIcon, QTextBrowser, QToolButton, QVBoxLayout,
                               QWidget, QButtonGroup)

from .. import APP_NAME, __version__
from ..core.config import cfg
from ..core.i18n import t
from .pages.ai_studio import AIStudioPage
from .pages.dashboard import DashboardPage
from .pages.feedback import FeedbackPage
from .pages.media import MediaPage
from .pages.posts import PostsPage
from .pages.products import ProductsPage
from .pages.settings import SettingsPage
from .theme import apply_theme, resolve_theme
from .widgets import button, set_main_window


class MainWindow(QMainWindow):
    def __init__(self, ctx, font_family: str, icon: QIcon):
        super().__init__()
        self.ctx, self.font_family = ctx, font_family
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(icon)
        self.resize(1280, 800)
        self.setMinimumSize(980, 640)
        set_main_window(self)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- sidebar
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(210)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 0, 10, 12)
        logo = QLabel("🛒 " + APP_NAME)
        logo.setObjectName("logo")
        sl.addWidget(logo)
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.nav: dict[str, QPushButton] = {}
        self.pages["dashboard"] = DashboardPage(ctx, self.goto)
        self.pages["products"] = ProductsPage(ctx)
        self.pages["posts"] = PostsPage(ctx)
        self.pages["media"] = MediaPage(ctx)
        self.pages["ai"] = AIStudioPage(ctx)
        self.pages["feedback"] = FeedbackPage(ctx)
        self.pages["settings"] = SettingsPage(ctx, self.apply_theme)
        for key, icon_, text in [("dashboard", "🏠", "Dashboard"), ("products", "📦", "Products"), ("posts", "📝", "Posts"),
                                 ("media", "🖼", "Media"), ("ai", "✨", "AI Studio"), ("feedback", "💬", "Feedback"), ("settings", "⚙", "Settings")]:
            if key == "feedback":
                sl.addStretch()
            b = QPushButton(f"{icon_}  {t(text)}")
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("text-align: %s;" % ("right" if cfg.language == "fa" else "left"))
            b.clicked.connect(lambda _=False, k=key: self.goto(k))
            self.group.addButton(b)
            self.nav[key] = b
            sl.addWidget(b)
            self.stack.addWidget(self.pages[key])
        root.addWidget(side)

        # ---- content
        right = QVBoxLayout()
        right.setSpacing(0)
        top = QWidget()
        top.setObjectName("topbar")
        top.setFixedHeight(56)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 0, 20, 0)
        tl.addWidget(QLabel(t("Site") + ":"))
        self.site_combo = QComboBox()
        self.site_combo.setMinimumWidth(260)
        self.site_combo.currentIndexChanged.connect(self._site_picked)
        tl.addWidget(self.site_combo)
        tl.addStretch()
        self.theme_btn = QToolButton()
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        tl.addWidget(self.theme_btn)
        self.bell = QToolButton()
        self.bell.clicked.connect(self.show_announcements)
        tl.addWidget(self.bell)
        right.addWidget(top)
        right.addWidget(self.stack, 1)
        root.addLayout(right, 1)

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            self.tray.show()

        ctx.site_changed.connect(self._site_reloaded)
        ctx.announcements_changed.connect(self._update_bell)
        ctx.new_announcements.connect(self._popup_new)
        ctx.popup_message.connect(self._show_modal_popup)

        self._fill_sites()
        self._update_bell()
        self._update_theme_btn()
        try:  # theme "Follow system": react when the OS switches between light and dark
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: cfg.theme == "system" and self.apply_theme())
        except Exception:
            pass
        self.goto("dashboard" if ctx.has_site() else "settings")

    # ---- navigation
    def goto(self, key: str, action: str | None = None) -> None:
        self.nav[key].setChecked(True)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        page.on_show()
        if action == "new":
            (page.new_product if key == "products" else page.new_post)()

    # ---- sites
    def _fill_sites(self) -> None:
        self.site_combo.blockSignals(True)
        self.site_combo.clear()
        for s in cfg.sites:
            self.site_combo.addItem(f"{s.name}  ({s.url})", s.id)
        i = self.site_combo.findData(cfg.active_site)
        self.site_combo.setCurrentIndex(max(i, 0))
        self.site_combo.blockSignals(False)
        if not cfg.sites:
            self.site_combo.addItem(t("No site yet - add one in Settings"))

    def _site_picked(self) -> None:
        sid = self.site_combo.currentData()
        if sid and sid != cfg.active_site:
            self.ctx.set_active_site(sid)

    def _site_reloaded(self) -> None:
        self._fill_sites()
        for p in self.pages.values():
            p.site_changed()
        cur = self.stack.currentWidget()
        cur.on_show()

    # ---- theme
    def apply_theme(self) -> None:
        apply_theme(QApplication.instance(), self.font_family, cfg.theme)
        self._update_theme_btn()

    def toggle_theme(self) -> None:
        cfg.theme = "light" if resolve_theme(cfg.theme) == "dark" else "dark"
        cfg.save()
        self.apply_theme()

    def _update_theme_btn(self) -> None:
        dark = resolve_theme(cfg.theme) == "dark"
        self.theme_btn.setText("☀" if dark else "🌙")
        self.theme_btn.setToolTip(t("Switch to light theme") if dark else t("Switch to dark theme"))

    # ---- announcements
    def _update_bell(self) -> None:
        n = len(self.ctx.unseen_announcements())
        self.bell.setText("🔔" + (f" {n}" if n else ""))
        self.bell.setToolTip(t("Announcements"))

    def show_announcements(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(t("Announcements"))
        dlg.resize(520, 420)
        lay = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        if self.ctx.announcements:
            view.setHtml("<hr>".join(
                f"<h3>{html.escape(a['title'])}</h3><p>{html.escape(a.get('body', ''))}</p>"
                + (f'<p><a href="{html.escape(a["url"])}">{html.escape(a["url"])}</a></p>' if a.get("url") else "")
                for a in self.ctx.announcements))
        else:
            view.setHtml(f"<p>{t('No announcements')}</p>")
        lay.addWidget(view)
        lay.addWidget(button(t("Close"), slot=dlg.accept))
        dlg.exec()
        self.ctx.mark_announcements_seen()

    def _popup_new(self, items: list) -> None:
        if self.tray:
            a = items[0]
            self.tray.showMessage(a["title"], a.get("body", "")[:200], QSystemTrayIcon.Information, 8000)
        self._update_bell()

    def _show_modal_popup(self, a: dict) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(a.get("title") or t("Announcement"))
        dlg.resize(480, 320)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        icon_str = "🚨 " if a.get("level") == "urgent" else "📢 "
        title_lbl = QLabel(icon_str + html.escape(a.get("title", "")))
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_lbl.setWordWrap(True)
        lay.addWidget(title_lbl)

        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml(f"<div style='font-size:14px; line-height:1.6;'>{html.escape(a.get('body', '')).replace(chr(10), '<br>')}</div>")
        lay.addWidget(view, 1)

        btn_row = QHBoxLayout()
        if a.get("url"):
            btn_row.addWidget(button(t("Open link"), primary=True, slot=lambda: webbrowser.open(a["url"])))
        btn_row.addStretch()
        btn_row.addWidget(button(t("Got it"), slot=dlg.accept))
        lay.addLayout(btn_row)

        dlg.exec()
        self.ctx.mark_announcements_seen()

    # ---- first run
    def first_run_notice(self) -> None:
        if cfg.telemetry_notice_shown or not cfg.server_url:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(t("Anonymous statistics"))
        box.setText(t("WooDesk is open source and sends anonymous usage statistics to help the project (app version, OS, language and the domains of connected sites - never passwords, keys or store data). You can turn this off any time in Settings > Server & privacy."))
        keep = box.addButton(t("OK, keep enabled"), QMessageBox.AcceptRole)
        off = box.addButton(t("Disable"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is off:
            self.ctx.set_telemetry(False)
        cfg.telemetry_notice_shown = True
        cfg.save()
