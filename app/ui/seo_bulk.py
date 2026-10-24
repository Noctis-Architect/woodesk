from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from ..core.config import cfg
from ..core.i18n import t
from ..core.workers import run_async
from ..seo.audit import audit_content
from ..seo.messages import issue_text, severity_label
from ..seo.wp_meta import SEO_KEYS, meta_value
from .widgets import DataTable, button, show_error


def _seo_fields(item: dict) -> tuple[str, str, str]:
    for keys in SEO_KEYS.values():
        meta_title, meta_desc, keyword = (meta_value(item, key) for key in keys)
        if meta_title or meta_desc or keyword:
            return meta_title, meta_desc, keyword
    return "", "", ""


class SeoBulkDialog(QDialog):
    """Offline content-only SEO audit for a bounded batch. No site writes."""

    def __init__(self, ctx, items: list[dict], kind: str, parent=None):
        super().__init__(parent)
        self.ctx, self.items, self.kind = ctx, items, kind
        self._index = 0
        self._cancel = False
        self.setWindowTitle(t("Bulk SEO audit"))
        self.resize(820, 500)
        lay = QVBoxLayout(self)
        self.info = QLabel(t("This audit is content-only and reads the selected items. Nothing is written to your site."))
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.progress = QProgressBar()
        self.progress.setMaximum(max(1, len(items)))
        lay.addWidget(self.progress)
        self.table = DataTable([t("Name"), t("Score"), t("Grade"), t("Top issue")], checkable=False)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 70)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.start = button(t("Start"), primary=True, slot=self.run)
        row.addWidget(self.start)
        row.addStretch()
        row.addWidget(button(t("Close"), slot=self.reject))
        lay.addLayout(row)

    def reject(self):
        self._cancel = True
        super().reject()

    def run(self):
        self.start.setEnabled(False)
        self.table.setRowCount(0)
        self._index = 0
        self._next()

    def _next(self):
        if self._cancel:
            return
        if self._index >= len(self.items):
            self.start.setEnabled(True)
            self.info.setText(f"{len(self.items)} " + t("items audited. Nothing was written."))
            return
        item = self.items[self._index]

        def work():
            if self.kind == "product":
                full = self.ctx.woo().product(item["id"])
                title = html.unescape(str(full.get("name") or ""))
                body = f"{full.get('short_description') or ''}\n{full.get('description') or ''}"
                images = [{"src": image.get("src", ""), "alt": image.get("alt", "")}
                          for image in full.get("images", []) if image.get("src")]
                name = title
            else:
                full = self.ctx.wp().post(item["id"])
                title = html.unescape(str((full.get("title") or {}).get("raw") or ""))
                body = str((full.get("content") or {}).get("raw") or "")
                images = []
                name = title
            meta_title, meta_description, keyword = _seo_fields(full)
            result = audit_content(
                title, body,
                meta_title=meta_title,
                meta_description=meta_description,
                keyword=keyword,
                images=images,
            )
            return name or t("(no title)"), result

        def done(value):
            name, result = value
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, self.table.item_text(name))
            self.table.setItem(row, 1, self.table.item_text(str(result.overall)))
            self.table.setItem(row, 2, self.table.item_text(result.grade))
            if result.issues:
                issue_title, _detail, _fix = issue_text(result.issues[0], cfg.language)
                severity = severity_label(result.issues[0].severity, cfg.language)
                top = f"{severity} — {issue_title}"
            else:
                top = t("No issues")
            self.table.setItem(row, 3, self.table.item_text(top))
            self._index += 1
            self.progress.setValue(self._index)
            self._next()

        def fail(exc):
            show_error(exc)
            self._index += 1
            self.progress.setValue(self._index)
            self._next()

        run_async(work, ok=done, err=fail)
