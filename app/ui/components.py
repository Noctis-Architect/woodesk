"""Reusable editor components: taxonomy picker, image list, media library dialog."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
                               QListWidgetItem, QVBoxLayout, QWidget, QAbstractItemView)

from ..api.wp import media_thumb
from ..core.i18n import t
from ..core.workers import run_async
from .widgets import Pager, SearchBox, button, load_pixmap, notify, show_error

IMG_FILTER = "Images (*.png *.jpg *.jpeg *.gif *.webp *.avif)"


class TaxonomyPicker(QWidget):
    """Checkable, hierarchical category list with search and quick-add."""

    def __init__(self, create_fn=None):
        super().__init__()
        self.create_fn = create_fn
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(t("Filter categories..."))
        self.filter.textChanged.connect(self._apply_filter)
        row.addWidget(self.filter)
        if create_fn:
            row.addWidget(button(t("+ New"), slot=self._add))
        lay.addLayout(row)
        self.list = QListWidget()
        lay.addWidget(self.list)
        self._cats: list[dict] = []
        self._checked: set[int] = set()

    def set_categories(self, cats: list[dict], checked: set[int] | None = None) -> None:
        if checked is not None:
            self._checked = set(checked)
        else:
            self._checked = set(self.selected_ids())
        self._cats = cats
        by_parent: dict[int, list[dict]] = {}
        for c in cats:
            by_parent.setdefault(c.get("parent", 0), []).append(c)
        self.list.clear()

        def walk(parent: int, depth: int):
            for c in sorted(by_parent.get(parent, []), key=lambda x: x["name"]):
                it = QListWidgetItem(("— " * depth) + c["name"].replace("&amp;", "&"))
                it.setData(Qt.UserRole, c["id"])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if c["id"] in self._checked else Qt.Unchecked)
                self.list.addItem(it)
                walk(c["id"], depth + 1)

        ids = {c["id"] for c in cats}
        roots = [p for p in by_parent if p not in ids]  # parent 0 or orphaned
        for r in roots:
            walk(r, 0)

    def selected_ids(self) -> list[int]:
        if self.list.count() == 0:
            return sorted(self._checked)
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def selected_names(self) -> list[str]:
        ids = set(self.selected_ids())
        return [c["name"] for c in self._cats if c.get("id") in ids]

    def _apply_filter(self, text: str) -> None:
        text = text.lower()
        for i in range(self.list.count()):
            self.list.item(i).setHidden(bool(text) and text not in self.list.item(i).text().lower())

    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, t("New category"), t("Name:"))
        if not (ok and name.strip()):
            return

        def done(cat):
            self._cats.append(cat)
            self._checked = set(self.selected_ids()) | {cat["id"]}
            self.set_categories(self._cats, self._checked)

        run_async(self.create_fn, name.strip(), ok=done, err=show_error)


class MediaPickerDialog(QDialog):
    def __init__(self, ctx, multi: bool = False, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.selected: list[dict] = []
        self.setWindowTitle(t("Media library"))
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = SearchBox()
        self.search.changed.connect(lambda _: self.load(1))
        top.addWidget(self.search)
        top.addWidget(button(t("Upload"), slot=self.upload))
        lay.addLayout(top)
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(120, 120))
        self.grid.setGridSize(QSize(140, 150))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setWordWrap(True)
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection if multi else QAbstractItemView.SingleSelection)
        self.grid.itemDoubleClicked.connect(lambda _i: self._choose())
        lay.addWidget(self.grid)
        self.pager = Pager()
        self.pager.page_changed.connect(self.load)
        lay.addWidget(self.pager)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button(t("Cancel"), slot=self.reject))
        row.addWidget(button(t("Select"), primary=True, slot=self._choose))
        lay.addLayout(row)
        self.load(1)

    def load(self, page: int = 1) -> None:
        q = self.search.text().strip()
        run_async(lambda: self.ctx.wp().media(page, 30, q, "image"),
                  ok=lambda r: self._fill(page, r), err=show_error)

    def _fill(self, page, res) -> None:
        items, total, pages = res
        self.grid.clear()
        for m in items:
            it = QListWidgetItem((m.get("title") or {}).get("raw") or m.get("slug", ""))
            it.setData(Qt.UserRole, m)
            self.grid.addItem(it)
            load_pixmap(media_thumb(m), lambda pm, i=it: i.setIcon(QIcon(pm)), 128)
        self.pager.set_state(page, pages, total)

    def upload(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, t("Upload"), "", IMG_FILTER)
        if not paths:
            return

        def work():
            return [self.ctx.wp().upload_media(p) for p in paths]

        run_async(work, ok=lambda _r: (notify(t("Uploaded"), "ok"), self.load(1)), err=show_error)

    def _choose(self) -> None:
        self.selected = [i.data(Qt.UserRole) for i in self.grid.selectedItems()]
        if self.selected:
            self.accept()


class ImagesEditor(QWidget):
    """List of images ({id, src, alt}). Upload, pick from library, add by URL, reorder."""

    def __init__(self, ctx, max_images: int = 0):
        super().__init__()
        self.ctx, self.max = ctx, max_images
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(button(t("Upload files"), slot=self.upload))
        row.addWidget(button(t("From library"), slot=self.library))
        row.addWidget(button(t("From URL"), slot=self.from_url))
        row.addStretch()
        row.addWidget(button("↑", slot=lambda: self.move(-1)))
        row.addWidget(button("↓", slot=lambda: self.move(1)))
        row.addWidget(button(t("Remove"), danger=True, slot=self.remove))
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(96, 96))
        self.list.setGridSize(QSize(112, 116))
        self.list.setMovement(QListWidget.Static)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMinimumHeight(150)
        lay.addWidget(self.list)

    def _add_item(self, img: dict) -> None:
        if self.max and self.list.count() >= self.max:
            self.list.clear()
        it = QListWidgetItem(f"#{img['id']}" if img.get("id") else "URL")
        it.setData(Qt.UserRole, img)
        self.list.addItem(it)
        load_pixmap(img.get("thumb") or img.get("src", ""), lambda pm, i=it: i.setIcon(QIcon(pm)))

    def set_images(self, imgs: list[dict]) -> None:
        self.list.clear()
        for i in imgs:
            self._add_item({"id": i.get("id", 0), "src": i.get("src") or i.get("source_url", ""), "alt": i.get("alt", "")})

    def images(self) -> list[dict]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def payload(self) -> list[dict]:
        out = []
        for im in self.images():
            out.append({"id": im["id"]} if im.get("id") else {"src": im["src"]})
        return out

    def upload(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, t("Upload files"), "", IMG_FILTER)
        if not paths:
            return
        if self.max:
            paths = paths[:1]
        notify(t("Uploading..."), "info", 2000)

        def work():
            return [self.ctx.wp().upload_media(p) for p in paths]

        def done(items):
            for m in items:
                self._add_item({"id": m["id"], "src": m.get("source_url", ""), "thumb": media_thumb(m), "alt": ""})
            notify(t("Uploaded"), "ok")

        run_async(work, ok=done, err=show_error)

    def library(self) -> None:
        dlg = MediaPickerDialog(self.ctx, multi=not self.max, parent=self)
        if dlg.exec() == QDialog.Accepted:
            for m in dlg.selected:
                self._add_item({"id": m["id"], "src": m.get("source_url", ""), "thumb": media_thumb(m), "alt": m.get("alt_text", "")})

    def from_url(self) -> None:
        url, ok = QInputDialog.getText(self, t("From URL"), "URL:")
        if ok and url.strip().startswith("http"):
            self._add_item({"id": 0, "src": url.strip(), "alt": ""})

    def move(self, d: int) -> None:
        r = self.list.currentRow()
        n = r + d
        if r < 0 or not (0 <= n < self.list.count()):
            return
        imgs = self.images()
        imgs[r], imgs[n] = imgs[n], imgs[r]
        self.set_images(imgs)
        self.list.setCurrentRow(n)

    def remove(self) -> None:
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)
