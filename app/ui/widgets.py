from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from contextlib import contextmanager

import httpx
from PySide6.QtCore import (QBuffer, QEasingCurve, QEvent, QIODevice, QPoint, QPropertyAnimation, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser, QToolButton,
                               QVBoxLayout, QWidget)

from .. import __version__
from ..core.config import cfg, data_dir
from ..core.i18n import t
from ..core.workers import run_async
from ..resources import asset_path
from .theme import palette, preview_css


def svg_icon(name: str, color: str, size: int = 20) -> QIcon:
    source = QIcon(str(asset_path("icons", f"{name}.svg")))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    source.paint(painter, 0, 0, pm.width(), pm.height())
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pm.rect(), QColor(color))
    painter.end()
    return QIcon(pm)

# ---------------------------------------------------------------- toast ---
_main_window = None
_toasts: dict[QWidget, list["Toast"]] = {}


def set_main_window(w) -> None:
    global _main_window
    _main_window = w


def _toast_color(kind: str) -> str:
    p = palette(cfg.theme)
    return {"info": p["primary_bg"], "ok": p["success"], "error": p["danger"],
            "warn": p["warning"]}.get(kind, p["primary_bg"])


class Toast(QFrame):
    """A single animated notification. Toasts are stacked bottom-up and never overlap."""

    def __init__(self, window: QWidget, text: str, kind: str):
        super().__init__(window)
        self._window = window
        self._text = str(text)
        self._closing = False
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet(f"QFrame#toast {{ background: {_toast_color(kind)}; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        self.label = QLabel(self._text)
        self.label.setObjectName("toastText")
        self.label.setTextFormat(Qt.PlainText)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self._pos_anim: QPropertyAnimation | None = None
        self._fade_anim: QPropertyAnimation | None = None
        self._slide_anim: QPropertyAnimation | None = None
        self._size_for(self._max_width())
        window.installEventFilter(self)

    def _max_width(self) -> int:
        return max(220, min(560, self._window.width() - 56))

    def _size_for(self, max_w: int) -> None:
        self.label.ensurePolished()
        fm = self.label.fontMetrics()
        width = min(max_w, max(240, fm.horizontalAdvance(self._text) + 36))
        text_w = width - 32
        self.label.setFixedWidth(text_w)
        height = max(self.label.heightForWidth(text_w), fm.height())
        self.setFixedSize(width, max(42, height + 20))

    def move_to(self, x: int, y: int, animate: bool = True) -> None:
        target = QPoint(x, y)
        if not animate or self.pos() == target or not self.isVisible():
            if self._pos_anim:
                self._pos_anim.stop()
            self.move(target)
            return
        if self._pos_anim:
            self._pos_anim.stop()
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(target)
        anim.start()
        self._pos_anim = anim

    def enter(self) -> None:
        self.effect.setOpacity(0.0)
        fade = QPropertyAnimation(self.effect, b"opacity", self)
        fade.setDuration(170)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.start()
        self._fade_anim = fade
        target = self.pos()
        self.move(target + QPoint(0, 10))
        slide = QPropertyAnimation(self, b"pos", self)
        slide.setDuration(190)
        slide.setEasingCurve(QEasingCurve.OutCubic)
        slide.setStartValue(target + QPoint(0, 10))
        slide.setEndValue(target)
        slide.start()
        self._slide_anim = slide

    def dismiss(self, instant: bool = False) -> None:
        if self._closing:
            return
        self._closing = True
        self.timer.stop()
        if instant:
            self._finish()
            return
        fade = QPropertyAnimation(self.effect, b"opacity", self)
        fade.setDuration(160)
        fade.setEasingCurve(QEasingCurve.InCubic)
        fade.setStartValue(self.effect.opacity())
        fade.setEndValue(0.0)
        fade.finished.connect(self._finish)
        fade.start()
        self._fade_anim = fade

    def reparent(self, window: QWidget) -> None:
        if self._closing:
            return
        for anim in (self._pos_anim, self._fade_anim, self._slide_anim):
            if anim:
                anim.stop()
        self._window.removeEventFilter(self)
        self.setParent(window)
        self._window = window
        window.installEventFilter(self)
        self.effect.setOpacity(1.0)
        self.show()
        self.raise_()

    def _finish(self) -> None:
        items = _toasts.get(self._window)
        if items and self in items:
            items.remove(self)
            if not items:
                _toasts.pop(self._window, None)
            else:
                _relayout(self._window, animate=True)
        self.hide()
        self.deleteLater()

    def eventFilter(self, obj, event):
        if obj is self._window and event.type() == QEvent.Resize and not self._closing:
            _relayout(self._window, animate=False)
        return False


def _relayout(window: QWidget, animate: bool = True, new: "Toast | None" = None) -> None:
    toasts = [t for t in _toasts.get(window, []) if not t._closing]
    if not toasts:
        return
    max_w = max(220, min(560, window.width() - 56))
    bottom = window.height() - 24
    for toast in reversed(toasts):
        toast._size_for(max_w)
        y = bottom - toast.height()
        x = max(16, (window.width() - toast.width()) // 2)
        toast.move_to(x, y, animate and toast is not new)
        toast.raise_()
        bottom = y - 8


def _hook_window(window: QWidget) -> None:
    if getattr(window, "_woodesk_toast_hooked", False):
        return
    window._woodesk_toast_hooked = True
    if isinstance(window, QDialog):
        window.finished.connect(lambda *_: _evacuate(window))


def _evacuate(dialog: QWidget) -> None:
    """Move notifications out of a dialog before it closes, so success messages stay visible."""
    items = [t for t in _toasts.pop(dialog, []) if not t._closing]
    target = _main_window
    if not items or target is None or not target.isVisible():
        for toast in items:
            toast.dismiss(instant=True)
        return
    for toast in items:
        toast.reparent(target)
    _toasts.setdefault(target, []).extend(items)
    _relayout(target, animate=False)


def notify(text: str, kind: str = "info", ms: int = 3500) -> None:
    window = QApplication.activeModalWidget() or QApplication.activeWindow() or _main_window
    if window is None:
        return
    _hook_window(window)
    items = _toasts.setdefault(window, [])
    while len([t for t in items if not t._closing]) >= 3:
        next(t for t in items if not t._closing).dismiss(instant=True)
    toast = Toast(window, text, kind)
    items.append(toast)
    toast.show()
    _relayout(window, animate=True, new=toast)
    toast.raise_()
    toast.enter()
    toast.timer.start(max(800, ms))


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
def h_align() -> Qt.AlignmentFlag:
    """Explicit visual alignment for the current UI direction.

    Plain AlignRight/AlignLeft are flipped by QLabel for RTL *text*, which made Persian labels
    left-aligned while digits/URLs stayed right-aligned. AlignAbsolute keeps them consistent.
    """
    return (Qt.AlignRight if cfg.language == "fa" else Qt.AlignLeft) | Qt.AlignAbsolute


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
    lb.setAlignment(h_align() | Qt.AlignVCenter)
    return lb


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(8)


class StatCard(Card):
    def __init__(self, title: str, value: str = "-"):
        super().__init__()
        self.setMinimumHeight(92)
        align = h_align() | Qt.AlignVCenter
        self.value = QLabel(value)
        self.value.setObjectName("statValue")
        self.value.setAlignment(align)
        self.lay.addWidget(self.value)
        title_lbl = label(title, muted=True)
        title_lbl.setAlignment(align)
        self.lay.addWidget(title_lbl)

    def set(self, v) -> None:
        self.value.setText(str(v))


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(16)
        box = QVBoxLayout()
        box.setSpacing(4)
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
        self.returnPressed.connect(self._emit_now)

    def _emit_now(self) -> None:
        self._timer.stop()
        self.changed.emit(self.text().strip())


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
        hh.setDefaultAlignment(h_align() | Qt.AlignVCenter)
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
        it.setTextAlignment(align if align else h_align() | Qt.AlignVCenter)
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
