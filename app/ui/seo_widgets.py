from __future__ import annotations

import html

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QProgressBar,
                               QScrollArea, QTextBrowser, QVBoxLayout, QWidget)

from ..core.config import cfg
from ..core.i18n import t
from ..perf.messages import perf_text
from ..seo.messages import category_label, issue_text, severity_label
from ..seo.models import CategoryScore
from .theme import palette
from .widgets import Card, button, label

_SEVERITY_COLORS = {
    "critical": "#e5484d",
    "high": "#e07a2f",
    "medium": "#b8860b",
    "low": "#6b7185",
    "info": "#6c5ce7",
}


def _lang() -> str:
    return "fa" if cfg.language == "fa" else "en"


def score_color(score: int) -> str:
    c = palette(cfg.theme)
    if score >= 80:
        return c["success"]
    if score >= 60:
        return c["warning"]
    return c["danger"]


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class ScoreRing(QWidget):
    def __init__(self, size: int = 148, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.score = 0
        self.grade = "-"

    def set_score(self, score: int, grade: str) -> None:
        self.score, self.grade = score, grade
        self.update()

    def paintEvent(self, _event) -> None:
        c = palette(cfg.theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = 11
        rect = QRectF(width / 2 + 2, width / 2 + 2, self.width() - width - 4, self.height() - width - 4)
        painter.setPen(QPen(QColor(c["border"]), width, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 90 * 16, -360 * 16)
        color = score_color(self.score)
        painter.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 90 * 16, int(-360 * 16 * max(0, min(100, self.score)) / 100))
        font = QFont(self.font())
        font.setPointSize(27)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(c["text"]))
        painter.drawText(rect.adjusted(0, 12, 0, -12), Qt.AlignCenter, str(self.score))
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(c["muted"]))
        painter.drawText(rect.adjusted(0, 76, 0, -20), Qt.AlignCenter, self.grade)


class CategoryBars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(8)

    def set_categories(self, categories: list[CategoryScore]) -> None:
        clear_layout(self.lay)
        c = palette(cfg.theme)
        lang = _lang()
        if not categories:
            self.lay.addWidget(label(t("No data"), muted=True))
            return
        for category in categories:
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(10)
            name = label(category_label(category.category, lang))
            name.setMinimumWidth(112)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(category.score)
            bar.setTextVisible(False)
            bar.setMinimumWidth(80)
            bar.setFixedHeight(9)
            color = score_color(category.score)
            bar.setStyleSheet(
                f"QProgressBar {{ border: none; background: {c['bg']}; border-radius: 4px; }}"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
            )
            value = label(str(category.score))
            value.setMinimumWidth(30)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_lay.addWidget(name)
            row_lay.addWidget(bar, 1)
            row_lay.addWidget(value)
            self.lay.addWidget(row)


class MetricCard(Card):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = label(title, muted=True)
        self.value = QLabel("-")
        font = self.value.font()
        font.setPointSize(20)
        font.setBold(True)
        self.value.setFont(font)
        self.status = label("", muted=True)
        self.lay.addWidget(self.title)
        self.lay.addWidget(self.value)
        self.lay.addWidget(self.status)

    def set_value(self, value: str, status: str = "", kind: str = "text", tooltip: str = "") -> None:
        c = palette(cfg.theme)
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {c.get(kind, c['text'])};")
        self.status.setText(status)
        self.status.setStyleSheet(f"color: {c.get(kind, c['muted'])};")
        if tooltip:
            self.setToolTip(tooltip)


class SerpPreview(Card):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = QLabel("-")
        font = self.title.font()
        font.setPointSize(15)
        self.title.setFont(font)
        self.title.setWordWrap(True)
        self.url = QLabel("-")
        self.url.setLayoutDirection(Qt.LeftToRight)
        self.url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.desc = label("-", muted=True, wrap=True)
        self.lay.addWidget(self.title)
        self.lay.addWidget(self.url)
        self.lay.addWidget(self.desc)

    def set_data(self, title: str, url: str, description: str) -> None:
        c = palette(cfg.theme)
        self.title.setText(title or "-")
        self.title.setStyleSheet(f"color: {c['primary']};")
        self.url.setText(url or "-")
        self.url.setStyleSheet(f"color: {c['success']}; font-size: 12px;")
        self.desc.setText(description or "-")


class AiPanel(Card):
    analyze_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        header = QHBoxLayout()
        header.addWidget(label(t("AI analysis"), "h2"))
        self.estimate = label("", muted=True)
        header.addWidget(self.estimate)
        header.addStretch()
        self.btn = button("✨ " + t("Analyze with AI"), slot=self.analyze_clicked.emit)
        self.btn.setProperty("ai", True)
        header.addWidget(self.btn)
        self.lay.addLayout(header)
        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(False)
        self.body.setMinimumHeight(120)
        self.body.hide()
        self.lay.addWidget(self.body)

    def set_estimate(self, tokens: int | None) -> None:
        self.estimate.setText(("~" + str(tokens) + " " + t("tokens")) if tokens else "")

    def set_busy(self, busy: bool) -> None:
        self.btn.setEnabled(not busy)
        self.btn.setText(("⏳ " + t("Analyzing...")) if busy else "✨ " + t("Analyze with AI"))

    def set_result(self, data: dict, cached: bool = False) -> None:
        self.btn.setEnabled(True)
        self.btn.setText("✨ " + t("Analyze with AI"))
        lang = _lang()
        summary = html.escape(str(data.get("summary") or ""))
        priorities = "".join(
            f"<li><b>{html.escape(str(item.get('issue') or ''))}</b>: {html.escape(str(item.get('action') or ''))}</li>"
            for item in data.get("priorities", []) if isinstance(item, dict)
        )
        quick = "".join(f"<li>{html.escape(str(item))}</li>" for item in data.get("quick_wins", []))
        prefix = f"<p><i>{html.escape(t('Cached result'))}</i></p>" if cached else ""
        heading = "تحلیل هوش مصنوعی" if lang == "fa" else "AI analysis"
        self.body.setHtml(
            f"<div dir='auto'>{prefix}"
            f"<h3>{heading}</h3><p>{summary}</p>"
            f"<h4>{'اولویت‌ها' if lang == 'fa' else 'Priorities'}</h4><ul>{priorities}</ul>"
            f"<h4>{'بردهای سریع' if lang == 'fa' else 'Quick wins'}</h4><ul>{quick}</ul></div>"
        )
        self.body.show()

    def clear(self) -> None:
        self.body.clear()
        self.body.hide()
        self.estimate.setText("")
        self.btn.setEnabled(True)
        self.btn.setText("✨ " + t("Analyze with AI"))


class IssueRow(QFrame):
    def __init__(self, issue, kind: str = "seo", lang: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("issue")
        c = palette(cfg.theme)
        self.setStyleSheet(f"QFrame#issue {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; }}")
        lang = lang or _lang()
        if kind == "perf":
            title, detail, fix = perf_text(issue, lang)
            category = "performance"
            page = ""
            severity = issue.severity
            evidence = issue.evidence
        else:
            title, detail, fix = issue_text(issue, lang)
            category = getattr(issue, "category", "")
            page = getattr(issue, "page", "")
            severity = issue.severity
            evidence = issue.evidence
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)
        head = QHBoxLayout()
        head.setSpacing(8)
        chip = QLabel(severity_label(severity, lang))
        color = _SEVERITY_COLORS.get(severity, c["muted"])
        chip.setStyleSheet(f"background: {color}; color: #ffffff; border-radius: 5px; padding: 2px 7px; font-size: 11px;")
        chip.setFixedHeight(22)
        head.addWidget(chip)
        title_label = QLabel(title)
        tf = title_label.font()
        tf.setBold(True)
        title_label.setFont(tf)
        title_label.setWordWrap(True)
        head.addWidget(title_label, 1)
        if page:
            page_label = QLabel(page)
            page_label.setLayoutDirection(Qt.LeftToRight)
            page_label.setStyleSheet(f"color: {c['muted']}; font-size: 11px;")
            page_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            head.addWidget(page_label)
        else:
            cat = label(category_label(category, lang), muted=True)
            head.addWidget(cat)
        lay.addLayout(head)
        if detail:
            lay.addWidget(label(detail, muted=True, wrap=True))
        if evidence:
            ev = QLabel(evidence[:900] + ("…" if len(evidence) > 900 else ""))
            ev.setTextFormat(Qt.PlainText)
            ev.setWordWrap(True)
            ev.setLayoutDirection(Qt.LeftToRight)
            ev.setStyleSheet(f"color: {c['muted']}; font-family: monospace; font-size: 11px;")
            ev.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(ev)
        if fix:
            lay.addWidget(label(("راه‌حل: " if lang == "fa" else "Fix: ") + fix, wrap=True))


class IssueList(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._issues: list = []
        self._kind = "seo"
        self._lang = _lang()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.filter = QComboBox()
        top.addWidget(self.filter)
        self.count = label("", muted=True)
        top.addWidget(self.count)
        top.addStretch()
        lay.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.items = QVBoxLayout(self.container)
        self.items.setContentsMargins(0, 4, 0, 4)
        self.items.setSpacing(8)
        self.scroll.setWidget(self.container)
        lay.addWidget(self.scroll, 1)
        self.filter.currentIndexChanged.connect(self._rebuild)

    def set_issues(self, issues: list, kind: str = "seo", lang: str | None = None) -> None:
        self._issues = list(issues or [])
        self._kind = kind
        self._lang = lang or _lang()
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem(t("All"), "all")
        for severity in ("critical", "high", "medium", "low", "info"):
            self.filter.addItem(severity_label(severity, self._lang), severity)
        self.filter.blockSignals(False)
        self._rebuild()

    def _rebuild(self) -> None:
        clear_layout(self.items)
        selected = self.filter.currentData() or "all"
        shown = [issue for issue in self._issues if selected == "all" or issue.severity == selected]
        self.count.setText(f"{len(shown)} / {len(self._issues)}")
        if not shown:
            self.items.addWidget(label(t("No issues found in this filter."), muted=True, wrap=True))
        for issue in shown:
            self.items.addWidget(IssueRow(issue, self._kind, self._lang))
        self.items.addStretch()


class ProgressRow(QWidget):
    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.text = label("", muted=True)
        self.cancel = button(t("Cancel"), slot=self.cancel_clicked.emit)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.text)
        lay.addWidget(self.cancel)
        self.hide()

    def start(self, text: str = "") -> None:
        self.bar.setValue(0)
        self.text.setText(text or t("Working..."))
        self.cancel.setEnabled(True)
        self.show()

    def set_progress(self, pct: int, key: str) -> None:
        self.bar.setValue(pct)
        if key.startswith("Run "):
            self.text.setText(t("Run") + " " + key[4:])
        elif key.startswith("Auditing page "):
            self.text.setText(t("Auditing page") + " " + key[len("Auditing page "):])
        else:
            self.text.setText(t(key))

    def finish(self) -> None:
        self.cancel.setEnabled(False)
        self.hide()
