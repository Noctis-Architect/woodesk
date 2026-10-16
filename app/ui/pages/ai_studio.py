from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from ...ai import prompts
from ...core.config import cfg
from ...core.i18n import t
from ...core.workers import run_async
from ..ai_assist import ai_ready
from ..widgets import PageHeader, button, label, notify, show_error

TASKS = [
    ("free", "Free prompt"),
    ("product", "Product description (input = product name + details)"),
    ("post", "Blog article (input = topic)"),
    ("rewrite", "Rewrite / improve text"),
    ("translate_en", "Translate to English"),
    ("translate_fa", "Translate to Persian"),
]


class AIStudioPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.addWidget(PageHeader(t("AI Studio"), t("A scratchpad for any AI task - results can be copied into your products and posts")))
        top = QHBoxLayout()
        self.task = QComboBox()
        for k, v in TASKS:
            self.task.addItem(t(v), k)
        top.addWidget(self.task, 1)
        self.run_btn = button(t("Generate"), primary=True, slot=self.run)
        top.addWidget(self.run_btn)
        lay.addLayout(top)
        lay.addWidget(label(t("Input"), "h2"))
        self.inp = QPlainTextEdit()
        lay.addWidget(self.inp, 1)
        lay.addWidget(label(t("Result"), "h2"))
        self.out = QPlainTextEdit()
        lay.addWidget(self.out, 2)
        row = QHBoxLayout()
        self.info = label("", muted=True)
        row.addWidget(self.info)
        row.addStretch()
        row.addWidget(button(t("Copy result"), slot=lambda: (QGuiApplication.clipboard().setText(self.out.toPlainText()), notify(t("Copied"), "ok"))))
        lay.addLayout(row)

    def on_show(self):
        pass

    def site_changed(self):
        pass

    def run(self):
        text = self.inp.toPlainText().strip()
        if not text or not ai_ready():
            return
        lang, task = cfg.ai.output_language, self.task.currentData()
        if task == "product":
            msgs = prompts.product_description(text, lang)
        elif task == "post":
            msgs = prompts.post_draft(text, lang)
        elif task == "rewrite":
            msgs = prompts.rewrite(text, lang)
        elif task.startswith("translate_"):
            msgs = prompts.translate(text, task.split("_")[1])
        else:
            msgs = [{"role": "user", "content": text}]
        self.run_btn.setEnabled(False)
        self.out.setPlainText(t("Working..."))

        def done(res):
            self.run_btn.setEnabled(True)
            self.out.setPlainText(prompts.strip_fences(res.text))
            extra = f" | {t('remaining free requests')}: {res.remaining}" if res.remaining is not None else ""
            tok = res.usage.get("total_tokens")
            self.info.setText((f"{tok} tokens" if tok else "") + extra)

        def fail(e):
            self.run_btn.setEnabled(True)
            self.out.setPlainText("")
            show_error(e)

        run_async(self.ctx.ai_chat, msgs, ok=done, err=fail)
