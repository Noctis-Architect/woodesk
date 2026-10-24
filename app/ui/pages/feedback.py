"""Developer Feedback & Support page.
Sends user criticisms, suggestions, and attachments directly to the developer server without storing local history.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QVBoxLayout, QWidget)

from ...core.config import cfg
from ...core.context import AppContext
from ...core.i18n import t
from ...core.workers import run_async
from ..widgets import PageHeader, button, label, ltr, notify, show_error


class FeedbackPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        self._file_bytes: bytes | None = None
        self._filename: str = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lay.addWidget(PageHeader(t("Developer Feedback & Support")))
        lay.addWidget(label(t("Send your criticisms, suggestions, or bug reports directly to the developer. Your message and optional attachment are received on the server, and no history is kept on your device."),
                            muted=True, wrap=True))

        # Main Form Box
        box = QGroupBox(t("Send Feedback Message"))
        flay = QFormLayout(box)
        flay.setContentsMargins(14, 18, 14, 14)
        flay.setSpacing(12)

        # 1. Subject Category
        self.category = QComboBox()
        self.category.addItems([
            t("Suggestion / New Feature"),
            t("Bug Report / Technical Issue"),
            t("Criticism / UI Feedback"),
            t("Question / Support"),
            t("Other"),
        ])
        flay.addRow(t("Category / Subject:"), self.category)

        # 2. Email / Gmail
        self.email_input = ltr(QLineEdit(cfg.ai.gmail))
        self.email_input.setPlaceholderText("yourname@gmail.com (" + t("Optional") + ")")
        flay.addRow(t("Your Email / Contact:"), self.email_input)

        # 3. Message Body
        self.msg_edit = QPlainTextEdit()
        self.msg_edit.setPlaceholderText(t("Write your message, feedback, or describe the issue in detail..."))
        self.msg_edit.setMinimumHeight(150)
        flay.addRow(t("Message Text:"), self.msg_edit)

        # 4. Attachment row
        att_row = QHBoxLayout()
        self.btn_attach = button(t("📎 Attach File (Screenshot, Log, Zip...)"), slot=self._choose_file)
        att_row.addWidget(self.btn_attach)

        self.file_label = label(t("No file attached (Max 15 MB)"), muted=True)
        att_row.addWidget(self.file_label, 1)

        self.btn_remove_file = button("✕", slot=self._remove_file)
        self.btn_remove_file.setToolTip(t("Remove attachment"))
        self.btn_remove_file.setVisible(False)
        att_row.addWidget(self.btn_remove_file)

        flay.addRow(t("Attachment:"), att_row)
        lay.addWidget(box)

        # Bottom Actions Row
        action_row = QHBoxLayout()
        self.status_lbl = label("", muted=True)
        action_row.addWidget(self.status_lbl, 1)

        self.btn_send = button(t("🚀 Send to Developer"), primary=True, slot=self._send)
        self.btn_send.setMinimumWidth(160)
        action_row.addWidget(self.btn_send)

        lay.addLayout(action_row)
        lay.addStretch()

    def on_show(self):
        if not self.email_input.text().strip():
            self.email_input.setText(cfg.ai.gmail)

    def site_changed(self):
        pass

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("Choose Attachment"),
            "",
            t("All Files (*.*);;Images (*.png *.jpg *.jpeg);;Logs & Text (*.txt *.log *.json);;Archives (*.zip *.tar.gz)")
        )
        if not path:
            return
        p = Path(path)
        try:
            size = p.stat().st_size
            if size > 15 * 1024 * 1024:
                notify(t("File size exceeds 15 MB limit."), "warn")
                return
            self._file_bytes = p.read_bytes()
            self._filename = p.name
            size_kb = size / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{(size_kb/1024):.1f} MB"
            self.file_label.setText(f"📄 {self._filename} ({size_str})")
            self._file_label_state(True)
            self.btn_remove_file.setVisible(True)
        except Exception as e:
            show_error(e)

    def _file_label_state(self, attached: bool) -> None:
        self.file_label.setProperty("success", attached)
        self.file_label.style().unpolish(self.file_label)
        self.file_label.style().polish(self.file_label)

    def _remove_file(self):
        self._file_bytes = None
        self._filename = ""
        self.file_label.setText(t("No file attached (Max 15 MB)"))
        self._file_label_state(False)
        self.btn_remove_file.setVisible(False)

    def _send(self):
        if not cfg.server_url:
            notify(t("Server URL is not configured. Please set the server URL in Settings > AI."), "warn")
            return

        msg = self.msg_edit.toPlainText().strip()
        if not msg:
            notify(t("Please write a message before sending."), "warn")
            self.msg_edit.setFocus()
            return

        subject = self.category.currentText().strip()
        email = self.email_input.text().strip()
        file_bytes = self._file_bytes
        filename = self._filename

        self.btn_send.setEnabled(False)
        self.status_lbl.setText("⏳ " + t("Sending feedback to developer..."))

        def work():
            return self.ctx.send_feedback(subject, msg, email, file_bytes, filename)

        def ok(_res):
            self.btn_send.setEnabled(True)
            self.status_lbl.setText("")
            # Clear form on success - no local history kept!
            self.msg_edit.clear()
            self._remove_file()
            notify(t("Your feedback has been sent successfully to the developer. Thank you!"), "ok", 5000)

        def err(e):
            self.btn_send.setEnabled(True)
            self.status_lbl.setText("")
            show_error(e)

        run_async(work, ok=ok, err=err)
