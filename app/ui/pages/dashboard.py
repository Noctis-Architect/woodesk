from __future__ import annotations

import html
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ...api.http import run_parallel
from ...core.config import cfg
from ...core.i18n import t
from ...core.workers import run_async
from ...seo.history import load_last
from ..widgets import Card, PageHeader, StatCard, button, h_align, label, show_error


class DashboardPage(QWidget):
    def __init__(self, ctx, goto):
        super().__init__()
        self.setObjectName("page")
        self.ctx, self.goto = ctx, goto
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        self.head = PageHeader(t("Dashboard"), "")
        self.head.add_action(button(t("Refresh"), slot=self.load))
        self.head.add_action(button("+ " + t("New post"), slot=lambda: goto("posts", "new")))
        self.head.add_action(button("+ " + t("New product"), primary=True, slot=lambda: goto("products", "new")))
        lay.addWidget(self.head)
        self.stores = Card()
        self.stores.lay.addWidget(label(t("Your stores"), "h2"))
        self.stores_row = QVBoxLayout()
        self.stores.lay.addLayout(self.stores_row)
        lay.addWidget(self.stores)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.cards = {k: StatCard(title) for k, title in [
            ("products", t("Products")), ("published", t("Published products")), ("outofstock", t("Out of stock")),
            ("draft", t("Draft products")), ("posts", t("Published posts")), ("post_drafts", t("Draft posts"))]}
        for i, c in enumerate(self.cards.values()):
            grid.addWidget(c, i // 3, i % 3)
        lay.addLayout(grid)
        self.seo_card = Card()
        seo_head = QHBoxLayout()
        seo_head.addWidget(label(t("SEO health"), "h2"))
        seo_head.addStretch()
        seo_head.addWidget(button(t("Open SEO"), slot=lambda: goto("seo")))
        self.seo_card.lay.addLayout(seo_head)
        self.seo_value = QLabel("-")
        self.seo_value.setObjectName("statValue")
        self.seo_value.setAlignment(h_align() | Qt.AlignVCenter)
        self.seo_card.lay.addWidget(self.seo_value)
        self.seo_detail = label("", muted=True, wrap=True)
        self.seo_card.lay.addWidget(self.seo_detail)
        lay.addWidget(self.seo_card)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.recent = Card()
        self.recent.lay.addWidget(label(t("Recent products"), "h2"))
        self.recent_lbl = QLabel("-")
        self.recent_lbl.setWordWrap(True)
        self.recent_lbl.setAlignment(h_align() | Qt.AlignTop)
        self.recent.lay.addWidget(self.recent_lbl)
        self.news = Card()
        self.news.lay.addWidget(label(t("Announcements"), "h2"))
        self.news_lbl = QLabel(t("No announcements"))
        self.news_lbl.setWordWrap(True)
        self.news_lbl.setAlignment(h_align() | Qt.AlignTop)
        self.news_lbl.setOpenExternalLinks(True)
        self.news.lay.addWidget(self.news_lbl)
        row.addWidget(self.recent, 1)
        row.addWidget(self.news, 1)
        lay.addLayout(row)
        lay.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll)
        self._loaded_once = False
        self._req = 0
        ctx.announcements_changed.connect(self.render_news)

    def on_show(self):
        self.render_news()
        self.render_stores()
        self.render_seo()
        if not self._loaded_once and self.ctx.has_site():
            self._loaded_once = True
            self.load()

    def site_changed(self):
        self._loaded_once = False
        self._req += 1
        self.on_show()

    def render_seo(self):
        data = load_last()
        if not data:
            self.seo_value.setText("-")
            self.seo_detail.setText(t("No SEO audit yet"))
            return
        self.seo_value.setText(f"{data.get('overall', '-')} · {data.get('grade', '')}")
        self.seo_detail.setText(
            f"{data.get('url', '')} · {data.get('fetched_at', '')} · "
            f"{data.get('issues', 0)} {t('Issues')} · "
            f"{data.get('pages', 1)} {t('pages')}")

    def render_stores(self):
        while self.stores_row.count():
            item = self.stores_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not cfg.sites:
            self.stores_row.addWidget(label(t("No site yet - add one in Settings"), muted=True))
            return
        for s in cfg.sites:
            active = s.id == cfg.active_site
            b = button(("● " if active else "○ ") + f"{s.name}    {s.url}", primary=active)
            b.setProperty("store", True)
            b.setToolTip(t("Active store") if active else t("Switch to this store"))
            if not active:
                b.clicked.connect(lambda _=False, sid=s.id: self.ctx.set_active_site(sid))
            self.stores_row.addWidget(b)

    def load(self):
        if not self.ctx.has_site():
            return
        self._req += 1
        req, site_id = self._req, cfg.active_site

        def work():
            woo = self.ctx.woo()
            tasks = [woo.counts, lambda: woo.products(1, 5)[0]]
            has_wp = self.ctx.has_wp()
            if has_wp:
                wp = self.ctx.wp()
                tasks += [lambda: wp.count_posts("publish"), lambda: wp.count_posts("draft")]
            res = run_parallel(tasks)
            return {"counts": res[0], "recent": res[1],
                    "posts": res[2] if has_wp else "-", "post_drafts": res[3] if has_wp else "-"}

        def done(d):
            if req != self._req or site_id != cfg.active_site:
                return
            c = d["counts"]
            self.cards["products"].set(c["all"])
            self.cards["published"].set(c["publish"])
            self.cards["outofstock"].set(c["outofstock"])
            self.cards["draft"].set(c["draft"])
            self.cards["posts"].set(d["posts"])
            self.cards["post_drafts"].set(d["post_drafts"])
            self.recent_lbl.setText("<br>".join("• " + html.escape(html.unescape(p["name"])) for p in d["recent"]) or "-")

        run_async(work, ok=done,
                  err=lambda e: show_error(e) if req == self._req and site_id == cfg.active_site else None)

    def render_news(self):
        items = self.ctx.announcements
        self.news_lbl.setEnabled(bool(items))
        if not items:
            self.news_lbl.setText(t("No announcements"))
            return
        parts = []
        for a in items[:5]:
            link = f' <a href="{html.escape(a["url"])}">{t("Open")}</a>' if a.get("url") else ""
            parts.append(f"<b>{html.escape(a['title'])}</b><br>{html.escape(a.get('body', ''))}{link}")
        self.news_lbl.setText("<br><br>".join(parts))
