from __future__ import annotations

import json
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from ..ai.prompts import parse_json_loose, strip_fences
from ..core.config import cfg
from ..core.i18n import t
from ..core.workers import run_async
from .widgets import HtmlEditor, button, notify, show_error, style_html_source

_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


def ai_ready() -> bool:
    a = cfg.ai
    if a.mode == "server":
        if not cfg.server_url:
            notify(t("Free AI needs a server URL (Settings > AI)."), "warn")
            return False
        return True
    from ..ai.catalog import catalog
    from ..core import secrets

    provider = catalog.resolve_provider(a.provider_id, a.base_url, a.api_format)
    base_url = a.base_url.strip() or provider.get("base_url", "")
    key = secrets.get(f"ai:api_key:{provider['id']}")
    if not key and not a.provider_id:
        key = secrets.get("ai:api_key")
    needs_key = bool((provider.get("auth") or {}).get("required", True))
    if not base_url or not a.model.strip() or (needs_key and not key):
        notify(t("Configure your AI provider first (Settings > AI)."), "warn")
        return False
    return True


class ResultDialog(QDialog):
    """Shows the AI result for review. The user can edit it, or type an extra instruction
    (e.g. "shorter", "more formal") and regenerate - the AI then revises the current text."""

    def __init__(self, parent, title: str, text: str, json_mode: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 540)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(t("Review and edit the result before applying it:")))
        if not json_mode and _TAG.search(text):
            self.edit = HtmlEditor(300)  # HTML result: toolbar + live preview
            self.edit.set_text(text)
        else:
            self.edit = QPlainTextEdit(text)
            if json_mode:
                style_html_source(self.edit)  # JSON is code: keep it LTR
        lay.addWidget(self.edit, 1)
        row = QHBoxLayout()
        self.instr = QLineEdit()
        self.instr.setPlaceholderText(t("Extra instruction (optional), e.g. shorter, more formal, mention warranty"))
        self.instr.returnPressed.connect(lambda: self.done(2))
        self.regen = button(t("Regenerate"))
        self.regen.clicked.connect(lambda: self.done(2))
        row.addWidget(self.instr, 1)
        row.addWidget(self.regen)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addStretch()
        cancel = button(t("Cancel"), slot=self.reject)
        cancel.setAutoDefault(False)
        row.addWidget(cancel)
        apply_btn = button(t("Apply"), primary=True, slot=self.accept)
        apply_btn.setDefault(True)
        row.addWidget(apply_btn)
        lay.addLayout(row)

    def text(self) -> str:
        if isinstance(self.edit, HtmlEditor):
            return self.edit.text()
        return self.edit.toPlainText().strip()

    def instruction(self) -> str:
        return self.instr.text().strip()


def _revise(messages: list[dict], draft: str, instruction: str) -> list[dict]:
    """Append the user's extra instruction (and the current draft) to the last user message."""
    msgs = [dict(m) for m in messages]
    msgs[-1]["content"] += (
        f"\n\nCURRENT DRAFT (the user may have edited it):\n{draft}\n\n"
        f"Revise the draft according to this instruction: {instruction}\n"
        "Output only the revised content, in the same format as the draft."
    )
    return msgs


class AIButton(QWidget):
    """One-click "Generate with AI" button. An optional dropdown (▾) holds the less common actions."""

    def __init__(self, label: str, callback, tooltip: str = ""):
        super().__init__()
        self.label = "✨ " + t(label)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.main = QPushButton(self.label)
        self.main.setProperty("ai", True)
        self.main.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.main.setToolTip(t(tooltip))
        self.main.clicked.connect(lambda _=False: callback())
        lay.addWidget(self.main)
        self.more = QToolButton()
        self.more.setText("▾")
        self.more.setProperty("ai", True)
        self.more.setPopupMode(QToolButton.InstantPopup)
        self.menu_ = QMenu(self.more)
        self.more.setMenu(self.menu_)
        self.more.hide()
        lay.addWidget(self.more)

    def add(self, text: str, callback) -> "AIButton":
        self.menu_.addAction(t(text), callback)
        self.more.show()
        return self

    def set_busy(self, busy: bool) -> None:
        self.main.setEnabled(not busy)
        self.more.setEnabled(not busy)
        self.main.setText(("⏳ " + t("Generating...")) if busy else self.label)


class AIMenuButton(QToolButton):
    """Dropdown of AI actions (used for secondary actions such as tags / SEO)."""

    def __init__(self, label: str = "✨ AI"):
        super().__init__()
        self.setText(label)
        self.setProperty("ai", True)
        self.setPopupMode(QToolButton.InstantPopup)
        self.menu_ = QMenu(self)
        self.setMenu(self.menu_)

    def add(self, text: str, callback) -> None:
        self.menu_.addAction(t(text), callback)

    def set_busy(self, busy: bool) -> None:
        self.setEnabled(not busy)


def run_ai(parent, ctx, messages: list[dict], on_apply, title: str = "AI", json_mode: bool = False,
           max_tokens: int | None = None, busy=None) -> None:
    """Ask the AI, show the result for review, then call on_apply(value).
    `busy` is any object with set_busy(bool) (AIButton): it shows "Generating..." while we wait."""
    if not ai_ready():
        return
    notify(t("AI is working..."), "info", 2500)
    if busy:
        busy.set_busy(True)

    def finish():
        if busy:
            try:
                busy.set_busy(False)
            except RuntimeError:
                pass  # the editor was closed while waiting

    def done(res):
        finish()
        text = strip_fences(res.text)
        if json_mode:
            try:
                text = json.dumps(parse_json_loose(text), ensure_ascii=False, indent=2)
            except Exception:
                notify(t("AI did not return valid JSON, try again."), "error")
                return
        dlg = ResultDialog(parent, title, text, json_mode)
        r = dlg.exec()
        if r == QDialog.Accepted:
            val = dlg.text()
            if json_mode:
                try:
                    val = json.loads(val)
                except Exception:
                    notify(t("Invalid JSON."), "error")
                    return
            on_apply(val)
        elif r == 2:
            extra = dlg.instruction()
            msgs = _revise(messages, dlg.text(), extra) if extra else messages
            run_ai(parent, ctx, msgs, on_apply, title, json_mode, max_tokens, busy)

    def fail(e):
        finish()
        show_error(e)

    run_async(ctx.ai_chat, messages, max_tokens, ok=done, err=fail)
