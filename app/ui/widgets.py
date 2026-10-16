from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from contextlib import contextmanager

import httpx
from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QToolButton, QVBoxLayout, QWidget, QAbstractItemView)

from .. import __version__
from ..core.config import cfg, data_dir
from ..core.i18n import t
from ..core.workers import run_async
from .theme import palette, preview_css

# ---------------------------------------------------------------- toast ---
_main_window = None


def set_main_window(w) -> None:
    global _main_window
    _main_window = w


def notify(text: str, kind: str = "info", ms: int = 3500) -> None:
    w = _main_window
    if w is None:
        return
    colors = {"info": "#4b5563", "ok": "#2fa36b", "error": "#e5484d", "warn": "#d9822b"}
    lbl = QLabel(text, w)
    lbl.setObjectName("toast")
    lbl.setStyleSheet(f"background:{colors.get(kind, colors['info'])};")
    lbl.setWordWrap(True)
    lbl.setMaximumWidth(max(300, w.width() - 80))
    lbl.adjustSize()
    lbl.move((w.width() - lbl.width()) // 2, w.height() - lbl.height() - 28)
    lbl.show()
    lbl.raise_()
    QTimer.singleShot(ms, lbl.deleteLater)


def error_text(e: Exception) -> str:
    return str(e) or e.__class__.__name__


def show_error(e: Exception) -> None:
    notify(error_text(e), "error", 6000)


def confirm(parent, text: str, danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    box.setText(text)
    yes = box.addButton(t("Yes"), QMessageBox.AcceptRole)
    box.addButton(t("Cancel"), QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes


def restart_app() -> None:
    """Relaunch the program (used to apply a language change, which needs a fresh UI)."""
    import sys

    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
    QProcess.startDetached(sys.executable, args)
    QApplication.quit()


# ----------------------------------------------------------- primitives ---
def ltr(w: QWidget) -> QWidget:
    """Keep technical values (URLs, SKUs, prices, API keys, slugs) left-to-right inside the RTL Persian UI."""
    w.setLayoutDirection(Qt.LeftToRight)
    return w


def style_html_source(edit: QPlainTextEdit) -> None:
    """HTML source is code: tags must stay in LTR order (an RTL base turns </p> into <p/>).
    In the Persian UI the lines are still flush-right so the text reads naturally."""
    edit.setLayoutDirection(Qt.LeftToRight)
    if cfg.language == "fa":
        doc = edit.document()
        opt = doc.defaultTextOption()
        opt.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        doc.setDefaultTextOption(opt)


def button(text: str, primary: bool = False, danger: bool = False, slot=None) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if primary:
        b.setProperty("primary", True)
    if danger:
        b.setProperty("danger", True)
    if slot:
        b.clicked.connect(slot)
    return b


def label(text: str, name: str = "", muted: bool = False, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    if muted:
        lb.setProperty("muted", True)
    lb.setWordWrap(wrap)
    return lb


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 14, 16, 14)


class StatCard(Card):
    def __init__(self, title: str, value: str = "-"):
        super().__init__()
        align = Qt.AlignRight if cfg.language == "fa" else Qt.AlignLeft
        self.value = QLabel(value)
        self.value.setObjectName("statValue")
        self.value.setAlignment(align | Qt.AlignVCenter)
        self.lay.addWidget(self.value)
        title_lbl = label(title, muted=True)
        title_lbl.setAlignment(align | Qt.AlignVCenter)
        self.lay.addWidget(title_lbl)

    def set(self, v) -> None:
        self.value.setText(str(v))


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        box = QVBoxLayout()
        box.addWidget(label(title, "h1"))
        if subtitle:
            box.addWidget(label(subtitle, muted=True))
        lay.addLayout(box)
        lay.addStretch()
        self.actions = QHBoxLayout()
        lay.addLayout(self.actions)

    def add_action(self, w: QWidget) -> None:
        self.actions.addWidget(w)


class SearchBox(QLineEdit):
    """Emits `changed` 400ms after the user stops typing."""
    changed = Signal(str)

    def __init__(self, placeholder: str = ""):
        super().__init__()
        self.setPlaceholderText(placeholder or t("Search..."))
        self.setClearButtonEnabled(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(lambda: self.changed.emit(self.text().strip()))
        self.textChanged.connect(lambda _=None: self._timer.start())
        self.returnPressed.connect(lambda: self.changed.emit(self.text().strip()))


class Pager(QWidget):
    page_changed = Signal(int)

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.info = label("", muted=True)
        self.prev = QToolButton()
        rtl = cfg.language == "fa"
        self.prev.setText("›" if rtl else "‹")
        self.next = QToolButton()
        self.next.setText("‹" if rtl else "›")
        self.lbl = ltr(QLabel("1 / 1"))
        lay.addWidget(self.info)
        lay.addStretch()
        lay.addWidget(self.prev)
        lay.addWidget(self.lbl)
        lay.addWidget(self.next)
        self.page, self.pages = 1, 1
        self.prev.clicked.connect(lambda: self._go(self.page - 1))
        self.next.clicked.connect(lambda: self._go(self.page + 1))

    def _go(self, p: int) -> None:
        if 1 <= p <= self.pages and p != self.page:
            self.page = p
            self._refresh()
            self.page_changed.emit(p)

    def set_state(self, page: int, pages: int, total: int) -> None:
        self.page, self.pages = page, max(1, pages)
        self.info.setText(f"{total} " + t("items"))
        self._refresh()

    def _refresh(self) -> None:
        self.lbl.setText(f"{self.page} / {self.pages}")
        self.prev.setEnabled(self.page > 1)
        self.next.setEnabled(self.page < self.pages)


class DataTable(QTableWidget):
    def __init__(self, headers: list[str], checkable: bool = True):
        super().__init__(0, len(headers) + (1 if checkable else 0))
        self.checkable = checkable
        self.offset = 1 if checkable else 0
        labels = ([""] if checkable else []) + headers
        self.setHorizontalHeaderLabels(labels)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setIconSize(QSize(44, 44))
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(52)
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        hh = self.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        if checkable:
            self.setColumnWidth(0, 34)
            hh.setSectionResizeMode(0, QHeaderView.Fixed)

    @contextmanager
    def bulk_update(self):
        """Fill many cells without a repaint/itemChanged signal per cell (much faster)."""
        self.setUpdatesEnabled(False)
        self.blockSignals(True)
        try:
            yield
        finally:
            self.blockSignals(False)
            self.setUpdatesEnabled(True)

    def item_text(self, text, editable=False, align=None, data=None) -> QTableWidgetItem:
        it = QTableWidgetItem(str(text))
        if not editable:
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        if align:
            it.setTextAlignment(align)
        if data is not None:
            it.setData(Qt.UserRole, data)
        return it

    def add_check(self, row: int) -> None:
        it = QTableWidgetItem()
        it.setFlags((it.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
        it.setCheckState(Qt.Unchecked)
        self.setItem(row, 0, it)

    def checked_rows(self) -> list[int]:
        rows = [r for r in range(self.rowCount()) if self.item(r, 0) and self.item(r, 0).checkState() == Qt.Checked]
        if rows:
            return rows
        return sorted({i.row() for i in self.selectedIndexes()})

    def set_all_checked(self, state: bool) -> None:
        for r in range(self.rowCount()):
            if self.item(r, 0):
                self.item(r, 0).setCheckState(Qt.Checked if state else Qt.Unchecked)


# ----------------------------------------------------------- thumbnails ---
# Pipeline: worker thread downloads -> decodes at reduced size -> caches a small PNG on disk ->
# UI thread only wraps the finished QImage in a QPixmap. Full-size product photos are never decoded on
# the UI thread, and the second time a photo is shown it comes from disk (no network at all).
THUMB = 96
_MEM_LIMIT = 400
_pix_cache: "OrderedDict[tuple, QPixmap]" = OrderedDict()
_pending: dict[tuple, list] = {}
_http: httpx.Client | None = None
_http_lock = threading.Lock()


def _client() -> httpx.Client:
    global _http
    if _http is None:
        with _http_lock:
            if _http is None:
                _http = httpx.Client(
                    timeout=httpx.Timeout(20, connect=8), follow_redirects=True,
                    headers={"User-Agent": f"WooDesk/{__version__}"},
                    limits=httpx.Limits(max_connections=12, max_keepalive_connections=8, keepalive_expiry=60))
    return _http


def _thumb_path(url: str, size: int):
    d = data_dir() / "cache" / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}_{size}.png"


def _decode(data: bytes, size: int) -> QImage:
    buf = QBuffer()
    buf.setData(data)
    buf.open(QIODevice.ReadOnly)
    reader = QImageReader(buf)
    reader.setAutoTransform(True)
    src = reader.size()
    if src.isValid() and max(src.width(), src.height()) > size * 2:
        reader.setScaledSize(src.scaled(size * 2, size * 2, Qt.KeepAspectRatio))  # decoder-side downscale
    img = reader.read()
    if img.isNull():
        img = QImage.fromData(data)
    return img


def _fetch_thumb(url: str, size: int) -> QImage:
    """Runs in a worker thread (QImage is thread-safe, QPixmap is not)."""
    path = _thumb_path(url, size)
    if path.exists():
        img = QImage(str(path))
        if not img.isNull():
            return img
    r = _client().get(url)
    r.raise_for_status()
    img = _decode(r.content, size)
    if img.isNull():
        raise ValueError("unsupported image")
    if max(img.width(), img.height()) > size:
        img = img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    try:
        img.save(str(path), "PNG")
    except Exception:  # noqa: BLE001 - cache is best effort
        pass
    return img


def load_pixmap(url: str, cb, size: int = THUMB) -> None:
    """Calls cb(QPixmap) on the UI thread (immediately if cached). Duplicate requests share one download."""
    if not url:
        return
    key = (url, size)
    pm = _pix_cache.get(key)
    if pm is not None:
        _pix_cache.move_to_end(key)
        cb(pm)
        return
    waiting = _pending.get(key)
    if waiting is not None:
        waiting.append(cb)
        return
    _pending[key] = [cb]

    def done(img: QImage):
        pm = QPixmap.fromImage(img)
        _pix_cache[key] = pm
        while len(_pix_cache) > _MEM_LIMIT:
            _pix_cache.popitem(last=False)
        for f in _pending.pop(key, []):
            try:
                f(pm)
            except RuntimeError:
                pass  # the widget/item it was meant for is gone (table reloaded, dialog closed)

    run_async(_fetch_thumb, url, size, ok=done, err=lambda e: _pending.pop(key, None))


class ThumbLabel(QLabel):
    def __init__(self, size: int = 44):
        super().__init__()
        self.sz = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border-radius:6px;")

    def set_url(self, url: str) -> None:
        load_pixmap(url, lambda pm: self.setPixmap(pm.scaled(self.sz, self.sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)))


def table_thumb(table: DataTable, row: int, col: int, url: str, size: int = 44) -> None:
    """Show a thumbnail as the cell's icon (far lighter than a QLabel per cell). The callback is bound to the
    item itself, so a late download can never land on the wrong row after the table was reloaded."""
    item = table.item(row, col)
    if item is None:
        item = QTableWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row, col, item)
    load_pixmap(url, lambda pm, it=item: it.setIcon(QIcon(pm)))


# ---------------------------------------------------------- HTML editor ---
class HtmlEditor(QWidget):
    """Source editor with a tag toolbar and a rendered preview."""
    textChanged = Signal()

    def __init__(self, min_height: int = 180):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.bar = QHBoxLayout()
        for text, tip, before, after in [
            ("B", "Bold", "<strong>", "</strong>"), ("I", "Italic", "<em>", "</em>"),
            ("H2", "Heading 2", "<h2>", "</h2>"), ("H3", "Heading 3", "<h3>", "</h3>"),
            ("•", "Bullet list", "<ul>\n  <li>", "</li>\n</ul>"), ("¶", "Paragraph", "<p>", "</p>"),
        ]:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(t(tip))
            b.clicked.connect(lambda _=False, a=before, z=after: self.wrap(a, z))
            self.bar.addWidget(b)
        link = QToolButton()
        link.setText("🔗")
        link.setToolTip(t("Insert link"))
        link.clicked.connect(self._link)
        self.bar.addWidget(link)
        self.bar.addStretch()
        self.toggle = QPushButton(t("Preview"))
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._toggle)
        self.bar.addWidget(self.toggle)
        lay.addLayout(self.bar)
        self.source = QPlainTextEdit()
        self.source.setMinimumHeight(min_height)
        self.source.setTabChangesFocus(True)
        style_html_source(self.source)
        self.preview = QTextBrowser()
        self.preview.setMinimumHeight(min_height)
        self.preview.hide()
        lay.addWidget(self.source)
        lay.addWidget(self.preview)
        self.source.textChanged.connect(self.textChanged)

    def add_widget(self, w: QWidget) -> None:
        self.bar.insertWidget(self.bar.count() - 2, w)

    def add_leading(self, w: QWidget) -> None:
        """Put a widget (e.g. the AI button) first in the toolbar, where it is seen first."""
        self.bar.insertWidget(0, w)

    def wrap(self, before: str, after: str) -> None:
        c = self.source.textCursor()
        sel = c.selectedText().replace("\u2029", "\n")
        c.insertText(f"{before}{sel}{after}")
        self.source.setFocus()

    def _link(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        url, ok = QInputDialog.getText(self, t("Insert link"), "URL:")
        if ok and url:
            self.wrap(f'<a href="{url}">', "</a>")

    def _toggle(self, on: bool) -> None:
        if on:
            self.preview.document().setDefaultStyleSheet(preview_css(palette(cfg.theme)))
            body = self.source.toPlainText()
            self.preview.setHtml(f'<div dir="rtl">{body}</div>' if cfg.language == "fa" else body)
        self.source.setVisible(not on)
        self.preview.setVisible(on)

    def text(self) -> str:
        return self.source.toPlainText().strip()

    def set_text(self, s: str) -> None:
        self.source.setPlainText(s or "")

    def selected_text(self) -> str:
        return self.source.textCursor().selectedText().replace("\u2029", "\n")

    def replace_selection(self, s: str) -> None:
        self.source.textCursor().insertText(s)
