from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from ...ai import prompts
from ...core.config import cfg
from ...core.i18n import t
from ...core.workers import run_async
from ..ai_assist import ai_ready
from ..widgets import DataTable, button, notify, show_error


class BulkAIDialog(QDialog):
    """Generate descriptions for many products, review them, then write the accepted ones to the shop."""

    def __init__(self, ctx, products: list[dict], parent=None):
        super().__init__(parent)
        self.ctx, self.products = ctx, products
        self.results: list[dict] = []
        self._i = 0
        self._cancel = False
        self.setWindowTitle(t("Generate descriptions with AI"))
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"{len(products)} " + t("products selected. Nothing is written to your shop until you press Apply.")))
        opts = QHBoxLayout()
        self.cb_desc = QCheckBox(t("Full description"))
        self.cb_desc.setChecked(True)
        self.cb_short = QCheckBox(t("Short description"))
        self.cb_short.setChecked(True)
        self.cb_skip = QCheckBox(t("Skip products that already have a description"))
        for c in (self.cb_desc, self.cb_short, self.cb_skip):
            opts.addWidget(c)
        opts.addStretch()
        lay.addLayout(opts)
        self.bar = QProgressBar()
        self.bar.setMaximum(len(products))
        lay.addWidget(self.bar)
        self.table = DataTable([t("Product"), t("New short description"), t("New description")])
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 340)
        lay.addWidget(self.table)
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

    def run(self):
        if not ai_ready() or not (self.cb_desc.isChecked() or self.cb_short.isChecked()):
            return
        self.start.setEnabled(False)
        self.results.clear()
        self.table.setRowCount(0)
        self._i = 0
        self._next()

    def _next(self):
        if self._cancel:
            return
        while self._i < len(self.products):
            p = self.products[self._i]
            if self.cb_skip.isChecked() and p.get("description"):
                self._i += 1
                self.bar.setValue(self._i)
                continue
            break
        if self._i >= len(self.products):
            self.apply.setEnabled(bool(self.results))
            self.start.setEnabled(True)
            notify(t("Generation finished. Review the results."), "ok")
            return
        p = self.products[self._i]

        def work():
            name, lang = html.unescape(p.get("name", "")), cfg.ai.output_language
            out = {"id": p["id"], "name": name}
            desc = p.get("description", "")
            if self.cb_desc.isChecked():
                out["description"] = prompts.strip_fences(self.ctx.ai_chat(prompts.product_description(name, lang, existing=desc)).text)
                desc = out["description"]
            if self.cb_short.isChecked():
                out["short_description"] = prompts.strip_fences(self.ctx.ai_chat(prompts.product_short(name, lang, desc), 300).text)
            return out

        def done(out):
            self.results.append(out)
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.add_check(r)
            self.table.item(r, 0).setCheckState(Qt.Checked)
            self.table.setItem(r, 1, self.table.item_text(out["name"]))
            self.table.setItem(r, 2, self.table.item_text(_strip(out.get("short_description", ""))))
            self.table.setItem(r, 3, self.table.item_text(_strip(out.get("description", ""))))
            self._i += 1
            self.bar.setValue(self._i)
            self._next()

        def fail(e):
            show_error(e)
            self.start.setEnabled(True)
            self.apply.setEnabled(bool(self.results))

        run_async(work, ok=done, err=fail)

    def apply_results(self):
        upd = []
        for r, res in enumerate(self.results):
            if self.table.item(r, 0).checkState() == Qt.Checked:
                upd.append({k: v for k, v in res.items() if k in ("id", "description", "short_description")})
        if not upd:
            return
        self.apply.setEnabled(False)
        run_async(lambda: self.ctx.woo().batch_products(update=upd),
                  ok=lambda _r: (notify(f"{len(upd)} " + t("products updated"), "ok"), self.accept()),
                  err=lambda e: (show_error(e), self.apply.setEnabled(True)))


def _strip(s: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()
