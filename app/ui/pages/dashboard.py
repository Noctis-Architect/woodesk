from __future__ import annotations

import html
import webbrowser

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...api.http import run_parallel
from ...core.config import cfg
from ...core.i18n import t
from ...core.workers import run_async
from ..widgets import Card, PageHeader, StatCard, button, label, show_error


class DashboardPage(QWidget):
    def __init__(self, ctx, goto):
        super().__init__()
        self.setObjectName("page")
        self.ctx, self.goto = ctx, goto
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        self.head = PageHeader(t("Dashboard"), "")
        self.head.add_action(button(t("Refresh"), slot=self.load))
        lay.addWidget(self.head)
        self.stores = Card()
        self.stores.lay.addWidget(label(t("Your stores"), "h2"))
        self.stores_row = QVBoxLayout()
        self.stores.lay.addLayout(self.stores_row)
        lay.addWidget(self.stores)
        grid = QGridLayout()
        self.cards = {k: StatCard(title) for k, title in [
            ("products", t("Products")), ("published", t("Published products")), ("outofstock", t("Out of stock")),
            ("draft", t("Draft products")), ("posts", t("Published posts")), ("post_drafts", t("Draft posts"))]}
        for i, c in enumerate(self.cards.values()):
            grid.addWidget(c, i // 3, i % 3)
        lay.addLayout(grid)
        row = QHBoxLayout()
        self.recent = Card()
        self.recent.lay.addWidget(label(t("Recent products"), "h2"))
        self.recent_lbl = QLabel("-")
        self.recent_lbl.setWordWrap(True)
        self.recent.lay.addWidget(self.recent_lbl)
        self.news = Card()
        self.news.lay.addWidget(label(t("Announcements"), "h2"))
        self.news_lbl = QLabel(t("No announcements"))
        self.news_lbl.setWordWrap(True)
        self.news_lbl.setOpenExternalLinks(True)
        self.news.lay.addWidget(self.news_lbl)
        row.addWidget(self.recent, 1)
        row.addWidget(self.news, 1)
        lay.addLayout(row)
        quick = QHBoxLayout()
        quick.addWidget(button("+ " + t("New product"), primary=True, slot=lambda: goto("products", "new")))
        quick.addWidget(button("+ " + t("New post"), slot=lambda: goto("posts", "new")))
        quick.addWidget(button(t("Media"), slot=lambda: goto("media")))
        quick.addStretch()
        lay.addLayout(quick)
        lay.addStretch()
        self._loaded_once = False
        ctx.announcements_changed.connect(self.render_news)

    def on_show(self):
        self.render_news()
        self.render_stores()
        if not self._loaded_once and self.ctx.has_site():
            self._loaded_once = True
            self.load()

    def site_changed(self):
        self._loaded_once = False
        self.on_show()

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
            if not active:
                b.clicked.connect(lambda _=False, sid=s.id: self.ctx.set_active_site(sid))
            self.stores_row.addWidget(b)

    def load(self):
        if not self.ctx.has_site():
            return

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
            c = d["counts"]
            self.cards["products"].set(c["all"])
            self.cards["published"].set(c["publish"])
            self.cards["outofstock"].set(c["outofstock"])
            self.cards["draft"].set(c["draft"])
            self.cards["posts"].set(d["posts"])
            self.cards["post_drafts"].set(d["post_drafts"])
            self.recent_lbl.setText("<br>".join("• " + html.escape(html.unescape(p["name"])) for p in d["recent"]) or "-")

        run_async(work, ok=done, err=show_error)

    def render_news(self):
        items = self.ctx.announcements
        if not items:
            self.news_lbl.setText(t("No announcements"))
            return
        parts = []
        for a in items[:5]:
            link = f' <a href="{html.escape(a["url"])}">{t("Open")}</a>' if a.get("url") else ""
            parts.append(f"<b>{html.escape(a['title'])}</b><br>{html.escape(a.get('body', ''))}{link}")
        self.news_lbl.setText("<br><br>".join(parts))
