from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QVBoxLayout

from ..ai import prompts
from ..core.config import cfg
from ..core.i18n import t
from ..core.workers import run_async
from .ai_assist import ai_ready
from .widgets import DataTable, button, confirm, notify, show_error


class BulkAltDialog(QDialog):
    """Suggest alt text for several media items; nothing is written until Apply."""

    def __init__(self, ctx, media: list[dict], parent=None):
        super().__init__(parent)
        self.ctx, self.media = ctx, media
        self._pending: list[tuple[int, dict]] = []
        self._index = 0
        self._cancel = False
        self.setWindowTitle(t("AI alt text"))
        self.resize(860, 520)
        lay = QVBoxLayout(self)
        self.intro = QLabel(
            f"{len(media)} " + t("images selected. Review the suggestions before writing them to WordPress."))
        self.intro.setWordWrap(True)
        lay.addWidget(self.intro)
        self.skip = QCheckBox(t("Skip images that already have alt text"))
        self.skip.setChecked(True)
        lay.addWidget(self.skip)
        self.estimate = QLabel(t("Estimated ~{tokens} tokens.").replace("{tokens}", str(len(media) * 190)))
        self.estimate.setProperty("muted", True)
        lay.addWidget(self.estimate)
        self.bar = QProgressBar()
        self.bar.setMaximum(max(1, len(media)))
        lay.addWidget(self.bar)
        self.table = DataTable([t("Image"), t("Current alt text"), t("Suggested alt text")])
        self.table.setColumnWidth(1, 190)
        self.table.setColumnWidth(2, 220)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.start = button(t("Start"), primary=True, slot=self.run)
        self.apply = button(t("Apply selected"), primary=True, slot=self.apply_results)
        self.apply.setEnabled(False)
        row.addWidget(self.start)
        row.addStretch()
        row.addWidget(button(t("Close"), slot=self.reject))
        row.addWidget(self.apply)
        lay.addLayout(row)

    def reject(self):
        self._cancel = True
        super().reject()

    def _name(self, media: dict) -> str:
        title = (media.get("title") or {}).get("raw") or media.get("slug") or ""
        return html.unescape(str(title)) or str(media.get("source_url") or "").rsplit("/", 1)[-1]

    def run(self):
        if not ai_ready():
            return
        self.start.setEnabled(False)
        self.table.setRowCount(0)
        self._pending = []
        for media in self.media:
            if self.skip.isChecked() and (media.get("alt_text") or "").strip():
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.add_check(row)
            self.table.item(row, 0).setCheckState(Qt.Unchecked)
            self.table.setItem(row, 1, self.table.item_text(self._name(media)))
            self.table.setItem(row, 2, self.table.item_text(media.get("alt_text", "")))
            self.table.setItem(row, 3, self.table.item_text("", editable=True))
            self._pending.append((row, media))
        self.bar.setMaximum(max(1, len(self._pending)))
        self._index = 0
        if not self._pending:
            notify(t("Nothing to generate."), "warn")
            self.start.setEnabled(True)
            return
        self._next()

    def _next(self):
        if self._cancel:
            return
        if self._index >= len(self._pending):
            self.start.setEnabled(True)
            self.apply.setEnabled(True)
            notify(t("Generation finished. Review the results."), "ok")
            return
        row, media = self._pending[self._index]

        def work():
            reply = self.ctx.ai_chat(prompts.alt_text(self._name(media), cfg.ai.output_language), max_tokens=90)
            return prompts.strip_fences(reply.text).strip()

        def done(text):
            self.table.setItem(row, 3, self.table.item_text(text, editable=True))
            self.table.item(row, 0).setCheckState(Qt.Checked)
            self._index += 1
            self.bar.setValue(self._index)
            self._next()

        def fail(exc):
            show_error(exc)
            self._index += 1
            self.bar.setValue(self._index)
            self._next()

        run_async(work, ok=done, err=fail)

    def apply_results(self):
        updates = []
        for row, media in self._pending:
            if self.table.item(row, 0).checkState() != Qt.Checked:
                continue
            alt = self.table.item(row, 3).text().strip()
            if alt:
                updates.append((media["id"], alt))
        if not updates:
            notify(t("Select at least one suggestion."), "warn")
            return
        if not confirm(self, f"{len(updates)} " + t("alt texts will be written to WordPress. Continue?")):
            return
        wp = self.ctx.wp()
        self.apply.setEnabled(False)

        def work():
            for media_id, alt in updates:
                wp.update_media(media_id, {"alt_text": alt})
            return len(updates)

        def done(count):
            notify(f"{count} " + t("alt texts saved"), "ok")
            self.accept()

        run_async(work, ok=done, err=lambda e: (self.apply.setEnabled(True), show_error(e)))
