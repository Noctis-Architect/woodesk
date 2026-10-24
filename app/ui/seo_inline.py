from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from ..core.config import cfg
from ..core.i18n import t
from ..seo.audit import audit_content
from ..seo.messages import issue_text, severity_label
from .seo_widgets import ScoreRing, clear_layout
from .theme import palette
from .widgets import Card, button, label

_SEV_COLORS = {"critical": "#e5484d", "high": "#e07a2f", "medium": "#b8860b", "low": "#6b7185", "info": "#6c5ce7"}


class SeoScoreCard(Card):
    """Live, offline SEO score for the current editor content (no network access)."""

    def __init__(self, getter, parent=None):
        super().__init__(parent)
        self.getter = getter
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self.refresh)
        top = QHBoxLayout()
        self.ring = ScoreRing(82)
        top.addWidget(self.ring)
        box = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(label(t("SEO score"), "h2"))
        head.addStretch()
        head.addWidget(button(t("Check now"), slot=self.refresh))
        box.addLayout(head)
        self.summary = label("", muted=True, wrap=True)
        box.addWidget(self.summary)
        self.counters = label("", muted=True, wrap=True)
        self.counters.setTextFormat(Qt.RichText)
        box.addWidget(self.counters)
        box.addStretch()
        top.addLayout(box, 1)
        self.lay.addLayout(top)
        self.issues = QVBoxLayout()
        self.issues.setContentsMargins(0, 2, 0, 0)
        self.issues.setSpacing(3)
        self.lay.addLayout(self.issues)
        self.refresh()

    def schedule(self) -> None:
        self._timer.start()

    def refresh(self) -> None:
        try:
            title, body, meta_title, meta_description, keyword, images = self.getter()
        except Exception:
            return
        result = audit_content(
            title, body,
            meta_title=meta_title,
            meta_description=meta_description,
            keyword=keyword,
            images=images,
        )
        lang = "fa" if cfg.language == "fa" else "en"
        self.ring.set_score(result.overall, result.grade)
        self.summary.setText(f"{result.grade} · {result.overall}/100 · {len(result.issues)} {t('Issues')}")
        title_len, desc_len = len(meta_title or ""), len(meta_description or "")
        c = palette(cfg.theme)
        title_color = c["success"] if 30 <= title_len <= 60 else c["warning"]
        desc_color = c["success"] if 70 <= desc_len <= 155 else c["warning"]
        self.counters.setText(
            f"<span style='color:{title_color}'>{t('Meta title')}: {title_len}/60</span> · "
            f"<span style='color:{desc_color}'>{t('Meta description')}: {desc_len}/155</span>"
        )
        clear_layout(self.issues)
        for issue in result.issues[:3]:
            issue_title, _detail, _fix = issue_text(issue, lang)
            sever = severity_label(issue.severity, lang)
            color = _SEV_COLORS.get(issue.severity, c["muted"])
            row = QLabel(f"<span style='color:{color};font-weight:bold'>{sever}</span> — {issue_title}")
            row.setWordWrap(True)
            row.setTextFormat(Qt.RichText)
            row.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.issues.addWidget(row)
        if not result.issues:
            row = QLabel(t("No SEO issues found in this content."))
            row.setStyleSheet(f"color: {c['success']};")
            row.setWordWrap(True)
            self.issues.addWidget(row)
