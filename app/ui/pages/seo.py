from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ...core.config import cfg
from ...core.i18n import t
from ...core.jobs import Job, JobCancelled
from ...core.workers import run_async
from ...perf.ai import analyze as analyze_perf, estimate_tokens as perf_tokens
from ...perf.browser import install_chromium
from ...perf.report import filename as perf_filename, to_html as perf_html, to_json as perf_json
from ...perf.runner import DEVICES, PerfCancelled, run_perf
from ...seo.ai import (analyze as analyze_seo, analyze_site, estimate_site_tokens,
                       estimate_tokens as seo_tokens)
from ...seo.audit import AuditCancelled, audit_site, audit_url
from ...seo.fetch import FetchError, normalize_url
from ...seo.history import save_last
from ...seo.models import AuditOptions, CategoryScore, SiteAuditResult
from ...seo.report import (filename as seo_filename, site_to_html, site_to_json, to_html as seo_html,
                           to_json as seo_json)
from ..ai_assist import ai_ready
from ..seo_widgets import AiPanel, CategoryBars, IssueList, MetricCard, ProgressRow, ScoreRing, SerpPreview
from ..widgets import Card, DataTable, PageHeader, button, confirm, label, ltr, notify, show_error


class SeoPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.audit_result = None
        self.perf_result = None
        self._job: Job | None = None
        self.setObjectName("page")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)
        head = PageHeader(t("SEO"), t("Technical SEO audit and local Core Web Vitals"))
        head.add_action(button(t("Clear results"), slot=self.clear_results))
        root.addWidget(head)

        url_card = Card()
        url_row = QHBoxLayout()
        url_row.addWidget(label(t("URL") + ":", muted=True))
        self.url = ltr(QLineEdit())
        self.url.setPlaceholderText("https://example.com/page")
        url_row.addWidget(self.url, 1)
        self.site_hint = label("", muted=True)
        url_row.addWidget(self.site_hint)
        url_card.lay.addLayout(url_row)
        root.addWidget(url_card)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._audit_tab(), t("SEO audit"))
        self.tabs.addTab(self._speed_tab(), t("Speed test"))
        root.addWidget(self.tabs, 1)
        self.on_show()

    # ------------------------------------------------------------ tabs ---
    def _audit_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        options = QHBoxLayout()
        options.addWidget(label(t("Focus keyword") + ":", muted=True))
        self.keyword = QLineEdit()
        self.keyword.setPlaceholderText(t("Optional"))
        options.addWidget(self.keyword, 1)
        self.audit_rendered = QCheckBox(t("Render JavaScript"))
        self.audit_rendered.setChecked(cfg.seo.rendered)
        self.audit_links = QCheckBox(t("Check internal links"))
        self.audit_links.setChecked(cfg.seo.check_links)
        options.addWidget(self.audit_rendered)
        options.addWidget(self.audit_links)
        self.scan_site = QCheckBox(t("Scan multiple pages"))
        self.scan_site.toggled.connect(self._scan_toggled)
        options.addWidget(self.scan_site)
        self.max_pages = QSpinBox()
        self.max_pages.setRange(2, 50)
        self.max_pages.setValue(max(2, min(50, cfg.seo.max_pages)))
        self.max_pages.setEnabled(False)
        self.max_pages.setFixedWidth(64)
        self.max_pages.setToolTip(t("Max pages"))
        options.addWidget(self.max_pages)
        self.run_audit_btn = button(t("Run SEO audit"), primary=True, slot=self.start_audit)
        options.addWidget(self.run_audit_btn)
        lay.addLayout(options)
        self.audit_progress = ProgressRow()
        self.audit_progress.cancel_clicked.connect(self.cancel_job)
        lay.addWidget(self.audit_progress)

        self.audit_empty = Card()
        self.audit_empty.lay.addWidget(label(
            t("Enter a URL and run the audit. The tester only reads the page; it never changes your site."),
            muted=True, wrap=True))
        self.audit_empty.lay.addStretch()

        self.audit_results = QWidget()
        results = QVBoxLayout(self.audit_results)
        results.setContentsMargins(0, 0, 0, 0)
        results.setSpacing(10)
        split = QSplitter(Qt.Horizontal)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(10)
        summary = Card()
        score_row = QHBoxLayout()
        self.audit_ring = ScoreRing(132)
        score_row.addWidget(self.audit_ring)
        score_box = QVBoxLayout()
        score_box.addWidget(label(t("Overall score"), "h2"))
        self.audit_grade = label("", muted=True, wrap=True)
        score_box.addWidget(self.audit_grade)
        score_box.addStretch()
        score_row.addLayout(score_box, 1)
        summary.lay.addLayout(score_row)
        self.audit_cats = CategoryBars()
        summary.lay.addWidget(self.audit_cats)
        self.audit_facts = label("", muted=True, wrap=True)
        summary.lay.addWidget(self.audit_facts)
        self.audit_note = label("", muted=True, wrap=True)
        self.audit_note.hide()
        summary.lay.addWidget(self.audit_note)
        left_lay.addWidget(summary)
        self.audit_serp = SerpPreview()
        left_lay.addWidget(self.audit_serp)
        export_row = QHBoxLayout()
        self.export_audit_btn = button(t("Export HTML"), slot=lambda: self.export_audit(False))
        self.export_audit_json = button(t("Export JSON"), slot=lambda: self.export_audit(True))
        export_row.addWidget(self.export_audit_btn)
        export_row.addWidget(self.export_audit_json)
        export_row.addStretch()
        left_lay.addLayout(export_row)
        left_lay.addStretch()
        left_scroll.setWidget(left)
        split.addWidget(left_scroll)

        issues_card = Card()
        issues_head = QHBoxLayout()
        issues_head.addWidget(label(t("Issues"), "h2"))
        issues_head.addStretch()
        issues_card.lay.addLayout(issues_head)
        self.audit_issues = IssueList()
        issues_card.lay.addWidget(self.audit_issues, 1)
        split.addWidget(issues_card)
        split.setSizes([470, 430])
        results.addWidget(split, 1)
        self.audit_ai = AiPanel()
        self.audit_ai.analyze_clicked.connect(self.run_audit_ai)
        results.addWidget(self.audit_ai)
        self.audit_results.setMinimumHeight(470)
        self.audit_results.hide()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.addWidget(self.audit_empty)
        body_lay.addWidget(self.audit_results)
        body_lay.addStretch()
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        return tab

    def _speed_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        options = QHBoxLayout()
        options.addWidget(label(t("Device") + ":", muted=True))
        self.device = QComboBox()
        for key, profile in DEVICES.items():
            self.device.addItem(t(profile["label"]), key)
        index = self.device.findData(cfg.seo.perf_device)
        self.device.setCurrentIndex(max(0, index))
        options.addWidget(self.device)
        options.addWidget(label(t("Runs") + ":", muted=True))
        self.speed_runs = QSpinBox()
        self.speed_runs.setRange(1, 5)
        self.speed_runs.setValue(max(1, min(5, cfg.seo.perf_runs)))
        options.addWidget(self.speed_runs)
        options.addStretch()
        self.download_btn = button(t("Download Chromium"), slot=self.download_browser)
        self.download_btn.setToolTip(t("Download a local Chromium for speed tests (~170 MB)."))
        options.addWidget(self.download_btn)
        self.run_speed_btn = button(t("Run speed test"), primary=True, slot=self.start_speed)
        options.addWidget(self.run_speed_btn)
        lay.addLayout(options)
        self.speed_progress = ProgressRow()
        self.speed_progress.cancel_clicked.connect(self.cancel_job)
        lay.addWidget(self.speed_progress)

        self.speed_empty = Card()
        self.speed_empty.lay.addWidget(label(
            t("The speed test runs a hidden local Chromium and reports Core Web Vitals. "
              "The real INP requires user interactions; TBT is shown as the primary lab signal."),
            muted=True, wrap=True))
        self.speed_empty.lay.addStretch()

        self.speed_results = QWidget()
        results = QVBoxLayout(self.speed_results)
        results.setContentsMargins(0, 0, 0, 0)
        results.setSpacing(10)
        top = QHBoxLayout()
        score_card = Card()
        score_card.setFixedWidth(180)
        score_card.setMinimumHeight(170)
        self.speed_ring = ScoreRing(104)
        score_card.lay.addWidget(self.speed_ring)
        self.speed_label = label("", muted=True, wrap=True)
        score_card.lay.addWidget(self.speed_label)
        top.addWidget(score_card)
        grid = QGridLayout()
        self.metric_cards = {}
        for i, (key, title) in enumerate([
            ("lcp", "LCP"), ("cls", "CLS"), ("tbt", "TBT"),
            ("inp", t("INP (lab)")), ("fcp", "FCP"), ("ttfb", "TTFB"),
        ]):
            card = MetricCard(title)
            card.setMinimumHeight(96)
            self.metric_cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        top.addLayout(grid, 1)
        results.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        issues_card = Card()
        issues_card.lay.addWidget(label(t("Issues"), "h2"))
        self.speed_issues = IssueList()
        issues_card.lay.addWidget(self.speed_issues, 1)
        split.addWidget(issues_card)
        res_card = Card()
        res_card.lay.addWidget(label(t("Heavy resources"), "h2"))
        self.speed_meta = label("", muted=True, wrap=True)
        res_card.lay.addWidget(self.speed_meta)
        self.resource_table = DataTable([t("URL"), t("Type"), t("Size"), t("Time")], checkable=False)
        self.resource_table.setMinimumHeight(100)
        self.resource_table.verticalHeader().setDefaultSectionSize(36)
        hh = self.resource_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        res_card.lay.addWidget(self.resource_table, 1)
        split.addWidget(res_card)
        split.setSizes([430, 470])
        split.setMinimumHeight(220)
        results.addWidget(split, 1)
        self.speed_ai = AiPanel()
        self.speed_ai.analyze_clicked.connect(self.run_speed_ai)
        results.addWidget(self.speed_ai)
        export_row = QHBoxLayout()
        self.export_speed_btn = button(t("Export HTML"), slot=lambda: self.export_speed(False))
        self.export_speed_json = button(t("Export JSON"), slot=lambda: self.export_speed(True))
        export_row.addWidget(self.export_speed_btn)
        export_row.addWidget(self.export_speed_json)
        export_row.addStretch()
        results.addLayout(export_row)
        self.speed_results.setMinimumHeight(570)
        self.speed_results.hide()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.addWidget(self.speed_empty)
        body_lay.addWidget(self.speed_results)
        body_lay.addStretch()
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        return tab

    # ----------------------------------------------------------- state ---
    def on_show(self) -> None:
        if not self.url.text().strip() and cfg.site():
            self.url.setText(cfg.site().url)
            self.site_hint.setText(cfg.site().name)

    def site_changed(self) -> None:
        if cfg.site():
            self.site_hint.setText(cfg.site().name)
            if not self.url.text().strip():
                self.url.setText(cfg.site().url)

    def _scan_toggled(self, on: bool) -> None:
        self.max_pages.setEnabled(on)

    def _set_busy(self, busy: bool) -> None:
        self.run_audit_btn.setEnabled(not busy)
        self.run_speed_btn.setEnabled(not busy)

    def clear_results(self) -> None:
        if self._job:
            self._job.cancel()
        self.audit_result = None
        self.perf_result = None
        self.audit_results.hide()
        self.speed_results.hide()
        self.audit_empty.show()
        self.speed_empty.show()
        self.audit_ai.clear()
        self.speed_ai.clear()
        self.audit_issues.set_issues([])
        self.speed_issues.set_issues([], "perf")
        self.resource_table.setRowCount(0)
        self._set_busy(False)

    def _failed(self, exc: Exception) -> None:
        self._set_busy(False)
        self.audit_progress.finish()
        self.speed_progress.finish()
        self._job = None
        show_error(exc)

    def _cancelled(self) -> None:
        self._set_busy(False)
        self.audit_progress.finish()
        self.speed_progress.finish()
        self._job = None
        notify(t("Cancelled"), "info")

    def cancel_job(self) -> None:
        if self._job:
            self._job.cancel()
            self.audit_progress.text.setText(t("Cancelling..."))
            self.speed_progress.text.setText(t("Cancelling..."))
            self.audit_progress.cancel.setEnabled(False)
            self.speed_progress.cancel.setEnabled(False)

    def _target_url(self) -> str | None:
        try:
            url = normalize_url(self.url.text())
        except FetchError as exc:
            notify(str(exc), "warn")
            return None
        self.url.setText(url)
        return url

    # ----------------------------------------------------------- audit ---
    def start_audit(self) -> None:
        url = self._target_url()
        if not url:
            return
        cfg.seo.rendered = self.audit_rendered.isChecked()
        cfg.seo.check_links = self.audit_links.isChecked()
        cfg.seo.max_pages = self.max_pages.value()
        cfg.save()
        options = AuditOptions(
            keyword=self.keyword.text().strip(),
            rendered=cfg.seo.rendered,
            check_links=cfg.seo.check_links,
            max_links=cfg.seo.max_links,
            timeout=20.0,
            max_pages=cfg.seo.max_pages,
        )
        scan_site = self.scan_site.isChecked()
        self._set_busy(True)
        self.audit_empty.hide()
        self.audit_results.hide()
        self.audit_progress.start(t("Starting audit..."))

        def work(job: Job):
            try:
                if scan_site:
                    return audit_site(url, options, progress=job.report, is_cancelled=lambda: job.cancelled)
                return audit_url(url, options, progress=job.report, is_cancelled=lambda: job.cancelled)
            except AuditCancelled as exc:
                raise JobCancelled() from exc

        job = Job(work, self)
        self._job = job
        job.progress.connect(self.audit_progress.set_progress)
        job.finished.connect(self._audit_done)
        job.failed.connect(self._failed)
        job.cancelled_signal.connect(self._cancelled)
        job.start()

    def _audit_done(self, result) -> None:
        self.audit_result = result
        self._job = None
        self._set_busy(False)
        self.audit_progress.finish()
        self.audit_results.show()
        save_last(result)
        if isinstance(result, SiteAuditResult):
            self._site_done(result)
        else:
            self._page_done(result)
        notify(t("Audit finished"), "ok")

    def _page_done(self, result) -> None:
        self.audit_ai.clear()
        self.audit_ai.set_estimate(seo_tokens(result))
        self.audit_ring.set_score(result.overall, result.grade)
        self.audit_grade.setText(f"{result.grade} · {result.overall}/100 · {result.fetched_at}")
        self.audit_cats.set_categories(result.categories)
        facts = result.facts
        bits = [
            f"<b>{t('Title')}:</b> {html.escape(facts.title or '-')}",
            f"<b>{t('Meta description')}:</b> {html.escape(facts.meta_description or '-')}",
            f"<b>H1:</b> {html.escape(' | '.join(facts.h1) or '-')}",
            f"<b>{t('Words')}:</b> {facts.word_count}",
            f"<b>{t('Images')}:</b> {len(facts.images)}",
            f"<b>{t('Internal links')}:</b> {sum(1 for link in facts.links if link.internal)}",
        ]
        self.audit_facts.setText("<br>".join(bits))
        self.audit_serp.set_data(facts.title, result.final_url, facts.meta_description)
        self.audit_issues.set_issues(result.issues, "seo")
        if result.note:
            self.audit_note.setText(result.note)
            self.audit_note.show()
        else:
            self.audit_note.hide()

    def _site_done(self, result: SiteAuditResult) -> None:
        self.audit_ai.clear()
        self.audit_ai.set_estimate(estimate_site_tokens(result))
        self.audit_ring.set_score(result.overall, result.grade)
        self.audit_grade.setText(
            f"{result.grade} · {result.overall}/100 · {result.crawled} {t('pages')} · {result.fetched_at}")
        by_category: dict[str, list[CategoryScore]] = {}
        for page in result.pages:
            for category in page.categories:
                by_category.setdefault(category.category, []).append(category)
        categories = [
            CategoryScore(
                category=name,
                score=round(sum(item.score for item in items) / len(items)),
                passed=sum(item.passed for item in items),
                failed=sum(item.failed for item in items),
                skipped=sum(item.skipped for item in items),
                total=sum(item.total for item in items),
            )
            for name, items in by_category.items()
        ]
        categories.sort(key=lambda item: next(
            (index for index, name in enumerate(("technical", "meta", "content", "media", "links", "structured", "mobile"))
             if name == item.category), 99))
        self.audit_cats.set_categories(categories)
        bits = [
            f"<b>{t('Pages audited')}:</b> {result.crawled}",
            f"<b>{t('Sitemap URLs')}:</b> {len(result.sitemap_urls)}",
            f"<b>{t('Site-wide issues')}:</b> {len(result.site_issues)}",
        ]
        self.audit_facts.setText("<br>".join(bits))
        home = result.pages[0] if result.pages else None
        if home:
            self.audit_serp.set_data(home.facts.title, home.final_url, home.facts.meta_description)
        issues = list(result.site_issues)
        for page in result.pages:
            for issue in page.issues:
                if not issue.page:
                    issue.page = page.final_url or page.url
                issues.append(issue)
        self.audit_issues.set_issues(issues[:300], "seo")
        if result.errors:
            self.audit_note.setText("\n".join(result.errors[:4]))
            self.audit_note.show()
        else:
            self.audit_note.hide()

    # ----------------------------------------------------------- speed ---
    def download_browser(self) -> None:
        if not confirm(self, t("Download Chromium for local speed tests (~170 MB)?")):
            return
        self.download_btn.setEnabled(False)
        notify(t("Downloading Chromium..."), "info", 4000)

        def done(result) -> None:
            self.download_btn.setEnabled(True)
            ok, output = result
            if ok:
                notify(t("Chromium downloaded"), "ok")
            else:
                show_error(RuntimeError(output[-500:] or t("Download failed")))

        def fail(exc: Exception) -> None:
            self.download_btn.setEnabled(True)
            show_error(exc)

        run_async(install_chromium, ok=done, err=fail)

    def start_speed(self) -> None:
        url = self._target_url()
        if not url:
            return
        cfg.seo.perf_device = self.device.currentData() or "mobile"
        cfg.seo.perf_runs = self.speed_runs.value()
        cfg.save()
        device = cfg.seo.perf_device
        runs = cfg.seo.perf_runs
        self._set_busy(True)
        self.speed_empty.hide()
        self.speed_results.hide()
        self.speed_progress.start(t("Starting speed test..."))

        def work(job: Job):
            try:
                return run_perf(url, device=device, runs=runs, timeout=45.0,
                                progress=job.report, is_cancelled=lambda: job.cancelled)
            except PerfCancelled as exc:
                raise JobCancelled() from exc

        job = Job(work, self)
        self._job = job
        job.progress.connect(self.speed_progress.set_progress)
        job.finished.connect(self._speed_done)
        job.failed.connect(self._failed)
        job.cancelled_signal.connect(self._cancelled)
        job.start()

    def _speed_done(self, result) -> None:
        self.perf_result = result
        self._job = None
        self._set_busy(False)
        self.speed_progress.finish()
        self.speed_results.show()
        self.speed_ai.clear()
        self.speed_ai.set_estimate(perf_tokens(result))
        self.speed_ring.set_score(result.score, result.grade)
        self.speed_label.setText(f"{t(result.network)} · {result.runs} {t('runs')}")
        self.speed_label.setToolTip(result.browser)
        m = result.metrics
        self.metric_cards["lcp"].set_value(
            f"{m.lcp_ms / 1000:.2f}s", self._status(m.lcp_ms, 2500, 4000), self._kind(m.lcp_ms, 2500, 4000),
            "LCP good ≤ 2.5s · needs improvement ≤ 4s")
        self.metric_cards["cls"].set_value(
            f"{m.cls:.3f}", self._status(m.cls, 0.1, 0.25), self._kind(m.cls, 0.1, 0.25),
            "CLS good ≤ 0.1 · needs improvement ≤ 0.25")
        self.metric_cards["tbt"].set_value(
            f"{m.tbt_ms} ms", self._status(m.tbt_ms, 200, 600), self._kind(m.tbt_ms, 200, 600),
            "TBT good ≤ 200ms · needs improvement ≤ 600ms")
        if m.inp_ms is None:
            self.metric_cards["inp"].set_value("—", t("Lab approximation"), "muted",
                                               "Real INP needs real user interactions; TBT is the primary lab signal.")
        else:
            self.metric_cards["inp"].set_value(
                f"{m.inp_ms} ms", self._status(m.inp_ms, 200, 500), self._kind(m.inp_ms, 200, 500),
                t("Synthetic lab interaction; not field INP."))
        self.metric_cards["fcp"].set_value(
            f"{m.fcp_ms / 1000:.2f}s", self._status(m.fcp_ms, 1800, 3000), self._kind(m.fcp_ms, 1800, 3000))
        self.metric_cards["ttfb"].set_value(
            f"{m.ttfb_ms} ms", self._status(m.ttfb_ms, 800, 1800), self._kind(m.ttfb_ms, 800, 1800))
        self.speed_issues.set_issues(result.issues, "perf")
        self._fill_resources(result)
        extra = f"{result.requests} {t('requests')} · {result.bytes / 1024 / 1024:.2f} MB"
        if result.third_parties:
            extra += " · " + t("Third parties") + ": " + ", ".join(
                f"{item['host']} ({item['count']})" for item in result.third_parties[:4])
        if result.lcp_element:
            extra += f" · LCP: {result.lcp_element}"
        if result.note:
            extra += " · " + result.note
        self.speed_meta.setText(extra)
        notify(t("Speed test finished"), "ok")

    def _status(self, value: float, good: float, needs: float) -> str:
        if value <= good:
            return t("Good")
        if value <= needs:
            return t("Needs improvement")
        return t("Poor")

    def _kind(self, value: float, good: float, needs: float) -> str:
        if value <= good:
            return "success"
        if value <= needs:
            return "warning"
        return "danger"

    def _fill_resources(self, result) -> None:
        self.resource_table.setRowCount(0)
        for resource in result.resources:
            row = self.resource_table.rowCount()
            self.resource_table.insertRow(row)
            size = f"{resource.bytes / 1024 / 1024:.2f} MB" if resource.bytes > 1024 * 1024 else f"{resource.bytes / 1024:.1f} KB"
            items = [
                self.resource_table.item_text(resource.url),
                self.resource_table.item_text(resource.kind + (" · 3rd" if resource.third_party else "")),
                self.resource_table.item_text(size),
                self.resource_table.item_text(f"{resource.duration_ms} ms"),
            ]
            items[0].setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            for column, item in enumerate(items):
                self.resource_table.setItem(row, column, item)

    # -------------------------------------------------------------- AI ---
    def _confirm_ai(self, tokens: int) -> bool:
        message = t("Send the summary to AI? Estimated ~{tokens} tokens.").replace("{tokens}", str(tokens))
        return confirm(self, message)

    def run_audit_ai(self) -> None:
        if not self.audit_result or not ai_ready():
            return
        is_site = isinstance(self.audit_result, SiteAuditResult)
        estimate = estimate_site_tokens(self.audit_result) if is_site else seo_tokens(self.audit_result)
        if not self._confirm_ai(estimate):
            return
        self.audit_ai.set_busy(True)
        function = analyze_site if is_site else analyze_seo

        def done(value) -> None:
            data, cached = value
            self.audit_result.ai = data
            self.audit_result.ai_cached = cached
            self.audit_ai.set_result(data, cached)

        def fail(exc: Exception) -> None:
            self.audit_ai.set_busy(False)
            show_error(exc)

        run_async(function, self.ctx, self.audit_result, ok=done, err=fail)

    def run_speed_ai(self) -> None:
        if not self.perf_result or not ai_ready():
            return
        if not self._confirm_ai(perf_tokens(self.perf_result)):
            return
        self.speed_ai.set_busy(True)

        def done(value) -> None:
            data, cached = value
            self.speed_ai.set_result(data, cached)

        def fail(exc: Exception) -> None:
            self.speed_ai.set_busy(False)
            show_error(exc)

        run_async(analyze_perf, self.ctx, self.perf_result, ok=done, err=fail)

    # ----------------------------------------------------------- export ---
    def _save(self, text: str, suggested: str, filters: str) -> None:
        path, _ = QFileDialog.getSaveFileName(self, t("Save report"), str(Path.home() / suggested), filters)
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            notify(t("Saved"), "ok")
        except Exception as exc:  # noqa: BLE001
            show_error(exc)

    def export_audit(self, as_json: bool) -> None:
        if not self.audit_result:
            return
        name = seo_filename(self.audit_result)
        is_site = isinstance(self.audit_result, SiteAuditResult)
        if as_json:
            text = site_to_json(self.audit_result) if is_site else seo_json(self.audit_result)
            self._save(text, name + ".json", "JSON (*.json)")
        else:
            text = site_to_html(self.audit_result, cfg.language) if is_site else seo_html(self.audit_result, cfg.language)
            self._save(text, name + ".html", "HTML (*.html)")

    def export_speed(self, as_json: bool) -> None:
        if not self.perf_result:
            return
        name = perf_filename(self.perf_result)
        if as_json:
            self._save(perf_json(self.perf_result), name + ".json", "JSON (*.json)")
        else:
            self._save(perf_html(self.perf_result, cfg.language), name + ".html", "HTML (*.html)")
