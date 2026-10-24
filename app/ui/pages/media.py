from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QListWidget,
                               QListWidgetItem, QVBoxLayout, QWidget)

from ...api.wp import media_thumb
from ...core.config import cfg
from ...core.i18n import t
from ...core.workers import run_async
from ..components import IMG_FILTER
from ..media_alt import BulkAltDialog
from ..widgets import PageHeader, Pager, SearchBox, button, confirm, load_pixmap, notify, show_error


class MediaPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx, self.page, self._loaded_once, self._req = ctx, 1, False, 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        head = PageHeader(t("Media"), t("Images and files in your WordPress library"))
        head.add_action(button(t("Refresh"), slot=lambda: self.load()))
        head.add_action(button("+ " + t("Upload"), primary=True, slot=self.upload))
        lay.addWidget(head)
        bar = QHBoxLayout()
        self.search = SearchBox()
        self.search.changed.connect(lambda _: self.load(1))
        bar.addWidget(self.search, 1)
        bar.addWidget(button(t("Copy URL"), slot=self.copy_url))
        bar.addWidget(button("✨ " + t("AI alt text"), slot=self.ai_alt))
        bar.addWidget(button(t("Edit alt text"), slot=self.edit_alt))
        bar.addWidget(button(t("Delete"), danger=True, slot=self.delete))
        lay.addLayout(bar)
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(130, 130))
        self.grid.setGridSize(QSize(150, 165))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setWordWrap(True)
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        lay.addWidget(self.grid, 1)
        self.pager = Pager()
        self.pager.page_changed.connect(self.load)
        lay.addWidget(self.pager)

    def on_show(self):
        if not self._loaded_once and self.ctx.has_site():
            self._loaded_once = True
            self.load(1)

    def site_changed(self):
        self._loaded_once = False
        self._req += 1
        self.grid.clear()

    def load(self, page=None):
        if page:
            self.page = page
        if not self.ctx.has_site():
            notify(t("Add a site in Settings first."), "warn")
            return
        pg, q = self.page, self.search.text().strip()
        self._req += 1
        req, site_id = self._req, cfg.active_site

        def current():
            return req == self._req and site_id == cfg.active_site

        run_async(lambda: self.ctx.wp().media(pg, 30, q),
                  ok=lambda r: self._fill(pg, r) if current() else None,
                  err=lambda e: show_error(e) if current() else None)

    def _fill(self, page, res):
        items, total, pages = res
        self.grid.clear()
        for m in items:
            it = QListWidgetItem((m.get("title") or {}).get("raw") or m.get("slug", ""))
            it.setData(Qt.UserRole, m)
            self.grid.addItem(it)
            if (m.get("mime_type") or "").startswith("image"):
                load_pixmap(media_thumb(m), lambda pm, i=it: i.setIcon(QIcon(pm)), 128)
        self.pager.set_state(page, pages, total)

    def _sel(self):
        return [i.data(Qt.UserRole) for i in self.grid.selectedItems()]

    def upload(self):
        if not self.ctx.has_site():
            notify(t("Add a site in Settings first."), "warn")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, t("Upload"), "", IMG_FILTER + ";;All files (*)")
        if paths:
            notify(t("Uploading..."), "info", 2000)
            run_async(lambda: [self.ctx.wp().upload_media(p) for p in paths],
                      ok=lambda r: (notify(f"{len(r)} " + t("files uploaded"), "ok"), self.load(1)), err=show_error)

    def copy_url(self):
        sel = self._sel()
        if sel:
            QGuiApplication.clipboard().setText("\n".join(m.get("source_url", "") for m in sel))
            notify(t("URL copied"), "ok")

    def ai_alt(self):
        selected = [m for m in self._sel() if (m.get("mime_type") or "").startswith("image")]
        if not selected:
            notify(t("Select one or more images first."), "warn")
            return
        if BulkAltDialog(self.ctx, selected, self).exec() == QDialog.Accepted:
            self.load()

    def edit_alt(self):
        sel = self._sel()
        if len(sel) != 1:
            return
        m = sel[0]
        alt, ok = QInputDialog.getText(self, t("Alt text"), t("Alt text:"), text=m.get("alt_text", ""))
        if ok:
            run_async(lambda: self.ctx.wp().update_media(m["id"], {"alt_text": alt}), ok=lambda _r: (notify(t("Saved"), "ok"), self.load()), err=show_error)

    def delete(self):
        sel = self._sel()
        if sel and confirm(self, f"{len(sel)} " + t("files will be deleted permanently. Continue?"), danger=True):
            run_async(lambda: [self.ctx.wp().delete_media(m["id"]) for m in sel],
                      ok=lambda _r: (notify(t("Deleted"), "ok"), self.load()), err=show_error)
