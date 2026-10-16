from __future__ import annotations

import html

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QMenu, QPlainTextEdit, QSplitter, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from ...ai import prompts
from ...core.config import cfg
from ...core.i18n import t
from ...api.http import run_parallel
from ...core.workers import run_async
from ..ai_assist import AIButton, run_ai
from ..components import ImagesEditor, TaxonomyPicker
from ..widgets import DataTable, HtmlEditor, PageHeader, Pager, SearchBox, button, confirm, label, ltr, notify, show_error

STATUS = [("publish", "Published"), ("draft", "Draft"), ("pending", "Pending review"), ("future", "Scheduled"), ("private", "Private")]


class PostEditor(QDialog):
    def __init__(self, ctx, post: dict | None = None, parent=None):
        super().__init__(parent)
        self.ctx, self.p = ctx, post or {}
        self.setWindowTitle(t("Edit post") if post else t("New post"))
        self.resize(1000, 740)
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        left = QWidget()
        lv = QVBoxLayout(left)
        self.title = QLineEdit()
        self.title.setPlaceholderText(t("Post title"))
        self.title.setStyleSheet("font-size:18px;font-weight:bold;padding:10px;")
        lv.addWidget(self.title)
        self.content = HtmlEditor(380)
        self.ai_content_btn = AIButton("Generate with AI", self.ai_draft, "Write a full article from the title")
        self.ai_content_btn.add("Create outline", self.ai_outline)
        self.ai_content_btn.add("Improve selection / text", self.ai_improve)
        self.ai_content_btn.add("Translate to English", lambda: self.ai_translate("en"))
        self.ai_content_btn.add("Translate to Persian", lambda: self.ai_translate("fa"))
        self.content.add_leading(self.ai_content_btn)
        md = QToolButton()
        md.setText("MD→HTML")
        md.setToolTip(t("Convert Markdown in the editor to HTML"))
        md.clicked.connect(self.md_to_html)
        self.content.add_widget(md)
        lv.addWidget(self.content, 1)
        lv.addWidget(label(t("Excerpt"), "h2"))
        self.excerpt = QPlainTextEdit()
        self.excerpt.setMaximumHeight(80)
        lv.addWidget(self.excerpt)
        self.ai_excerpt_btn = AIButton("Generate with AI", self.ai_excerpt, "Write a short excerpt from the article")
        self.ai_excerpt_btn.add("Generate SEO title/description (slug)", self.ai_seo)
        lv.addWidget(self.ai_excerpt_btn)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        f = QFormLayout()
        self.status = QComboBox()
        for k, v in STATUS:
            self.status.addItem(t(v), k)
        self.status.currentIndexChanged.connect(self._status_changed)
        self.date = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.slug = ltr(QLineEdit())
        self.sticky = QCheckBox(t("Sticky"))
        f.addRow(t("Status"), self.status)
        f.addRow(t("Publish date"), self.date)
        f.addRow(t("Slug"), self.slug)
        f.addRow(self.sticky)
        rv.addLayout(f)
        tabs = QTabWidget()
        self.cats = TaxonomyPicker(self.ctx.create_wp_category)
        tabs.addTab(self.cats, t("Categories"))
        tw = QWidget()
        tv = QVBoxLayout(tw)
        tv.addWidget(label(t("Tags (comma separated)"), muted=True))
        self.tags = QLineEdit()
        tv.addWidget(self.tags)
        self.ai_tags_btn = AIButton("Suggest tags", self.ai_tags)
        tv.addWidget(self.ai_tags_btn)
        tv.addStretch()
        tabs.addTab(tw, t("Tags"))
        self.featured = ImagesEditor(ctx, max_images=1)
        tabs.addTab(self.featured, t("Featured image"))
        rv.addWidget(tabs, 1)
        split.addWidget(right)
        split.setSizes([650, 330])

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button(t("Cancel"), slot=self.reject))
        self.save_btn = button(t("Save"), primary=True, slot=self.save)
        row.addWidget(self.save_btn)
        root.addLayout(row)
        self._fill()
        run_async(self._load_tax, ok=self._tax_loaded, err=show_error)

    def _fill(self):
        p = self.p
        self.title.setText(html.unescape((p.get("title") or {}).get("raw", "")))
        self.content.set_text((p.get("content") or {}).get("raw", ""))
        self.excerpt.setPlainText((p.get("excerpt") or {}).get("raw", ""))
        i = self.status.findData(p.get("status", "draft"))
        self.status.setCurrentIndex(max(i, 0) if p else 1)
        if p.get("date") and p.get("status") == "future":
            self.date.setDateTime(QDateTime.fromString(p["date"][:19], "yyyy-MM-ddTHH:mm:ss"))
        self.slug.setText(p.get("slug", ""))
        self.sticky.setChecked(bool(p.get("sticky")))
        self._status_changed()
        if p.get("featured_media"):
            def show(m):
                from ...api.wp import media_thumb

                self.featured.set_images([{"id": m["id"], "src": m.get("source_url", ""), "thumb": media_thumb(m)}])

            run_async(lambda: self.ctx.wp().json("GET", f"/media/{p['featured_media']}"), ok=show, err=lambda e: None)

    def _status_changed(self):
        self.date.setEnabled(self.status.currentData() == "future")

    def _load_tax(self):
        # categories come from the per-site cache; only the tags this post already has are fetched (by id)
        ids = self.p.get("tags") or []
        return run_parallel([self.ctx.wp_categories, lambda: self.ctx.wp().tags_by_ids(ids)])

    def _tax_loaded(self, res):
        cats, tags = res
        self.tag_by_id = {t_["id"]: t_["name"] for t_ in tags}
        self.cats.set_categories(cats, set(self.p.get("categories", [])))
        if self.p.get("tags") and not self.tags.text():
            self.tags.setText(", ".join(self.tag_by_id.get(i, "") for i in self.p["tags"] if i in self.tag_by_id))

    # ---- AI ----
    def _lang(self):
        return cfg.ai.output_language

    def ai_draft(self):
        if not self.title.text().strip():
            notify(t("Enter a title first."), "warn")
            return
        run_ai(self, self.ctx, prompts.post_draft(self.title.text(), self._lang(), self.tags.text(), self.content.text()),
               self.content.set_text, t("Article draft"), max_tokens=4000, busy=self.ai_content_btn)

    def ai_outline(self):
        if not self.title.text().strip():
            notify(t("Enter a title first."), "warn")
            return
        run_ai(self, self.ctx, prompts.post_outline(self.title.text(), self._lang(), self.tags.text()), self.content.set_text,
               t("Outline"), max_tokens=1200, busy=self.ai_content_btn)

    def ai_improve(self):
        sel = self.content.selected_text()
        text = sel or self.content.text()
        if text:
            run_ai(self, self.ctx, prompts.rewrite(text, self._lang()), self.content.replace_selection if sel else self.content.set_text,
                   t("Improve text"), max_tokens=4000, busy=self.ai_content_btn)

    def ai_translate(self, lang):
        sel = self.content.selected_text()
        text = sel or self.content.text()
        if text:
            run_ai(self, self.ctx, prompts.translate(text, lang), self.content.replace_selection if sel else self.content.set_text,
                   t("Translate"), max_tokens=4000, busy=self.ai_content_btn)

    def ai_excerpt(self):
        if not self.content.text():
            notify(t("Write or generate the article first."), "warn")
            return
        run_ai(self, self.ctx, prompts.excerpt(self.content.text(), self._lang()), self.excerpt.setPlainText, t("Excerpt"),
               max_tokens=200, busy=self.ai_excerpt_btn)

    def ai_tags(self):
        run_ai(self, self.ctx, prompts.suggest_tags(self.title.text() + "\n" + self.content.text(), self._lang()), self.tags.setText,
               t("Tags"), max_tokens=200, busy=self.ai_tags_btn)

    def ai_seo(self):
        def apply(d):
            if d.get("description"):
                self.excerpt.setPlainText(d["description"])
            if d.get("slug") and not self.slug.text():
                self.slug.setText(d["slug"])
            if d.get("title") and not self.title.text():
                self.title.setText(d["title"])

        run_ai(self, self.ctx, prompts.seo_meta(self.title.text(), self._lang(), self.content.text()), apply, "SEO",
               json_mode=True, max_tokens=400, busy=self.ai_excerpt_btn)

    def md_to_html(self):
        import markdown

        self.content.set_text(markdown.markdown(self.content.text(), extensions=["extra", "sane_lists"]))

    # ---- save ----
    def save(self):
        title = self.title.text().strip()
        if not title:
            notify(t("Title is required."), "warn")
            return
        status = self.status.currentData()
        data = {"title": title, "content": self.content.text(), "excerpt": self.excerpt.toPlainText().strip(),
                "status": status, "sticky": self.sticky.isChecked(), "categories": self.cats.selected_ids()}
        if self.slug.text().strip():
            data["slug"] = self.slug.text().strip()
        if status == "future":
            data["date"] = self.date.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
        feat = self.featured.images()
        data["featured_media"] = feat[0]["id"] if feat and feat[0].get("id") else 0
        names = [x.strip() for x in self.tags.text().split(",") if x.strip()]
        pid = self.p.get("id")
        self.save_btn.setEnabled(False)

        def work():
            wp = self.ctx.wp()
            data["tags"] = wp.ensure_tags(names)
            return wp.save_post(pid, data)

        run_async(work, ok=lambda _r: (notify(t("Post saved"), "ok"), self.accept()),
                  err=lambda e: (self.save_btn.setEnabled(True), show_error(e)))


class PostsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx, self.rows, self.page, self._loaded_once, self._req = ctx, [], 1, False, 0
        self.cat_names: dict[int, str] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        head = PageHeader(t("Posts"), t("Write and manage blog articles"))
        self.bulk = QToolButton()
        self.bulk.setText(t("Bulk actions") + " ▾")
        self.bulk.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.bulk)
        m.addAction(t("Set Published"), lambda: self.bulk_status("publish"))
        m.addAction(t("Set Draft"), lambda: self.bulk_status("draft"))
        m.addSeparator()
        m.addAction(t("Move to trash"), lambda: self.bulk_delete(False))
        m.addAction(t("Delete permanently"), lambda: self.bulk_delete(True))
        self.bulk.setMenu(m)
        head.add_action(self.bulk)
        head.add_action(button(t("Refresh"), slot=lambda: self.load()))
        head.add_action(button("+ " + t("New post"), primary=True, slot=self.new_post))
        lay.addWidget(head)
        bar = QHBoxLayout()
        self.search = SearchBox(t("Search posts..."))
        self.search.changed.connect(lambda _: self.load(1))
        self.f_status = QComboBox()
        self.f_status.addItem(t("All statuses"), "any")
        for k, v in STATUS:
            self.f_status.addItem(t(v), k)
        self.f_status.currentIndexChanged.connect(lambda _=0: self.load(1))
        bar.addWidget(self.search, 1)
        bar.addWidget(self.f_status)
        lay.addLayout(bar)
        self.table = DataTable([t("Title"), t("Status"), t("Date"), t("Categories")])
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setColumnWidth(1, 380)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 140)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda r, c: self.edit_row(r))
        lay.addWidget(self.table, 1)
        self.pager = Pager()
        self.pager.page_changed.connect(self.load)
        lay.addWidget(self.pager)

    def on_show(self):
        if not self.ctx.has_wp():
            return
        if not self._loaded_once and self.ctx.has_site():
            self._loaded_once = True
            run_async(self.ctx.wp_categories, ok=lambda c: self.cat_names.update({x["id"]: x["name"] for x in c}), err=lambda e: None)
            self.load(1)

    def site_changed(self):
        self._loaded_once = False
        self.table.setRowCount(0)

    def load(self, page=None):
        if page:
            self.page = page
        if not self.ctx.has_site():
            notify(t("Add a site in Settings first."), "warn")
            return
        if not self.ctx.has_wp():
            notify(t("To manage posts and media, add your WordPress username and application password in Settings."), "warn")
            return
        pg, q, st = self.page, self.search.text().strip(), self.f_status.currentData()
        self._req += 1
        req = self._req  # answers can arrive out of order while typing; only the newest one is shown
        run_async(lambda: self.ctx.wp().posts(pg, 20, q, st), ok=lambda r: self._fill(pg, r) if req == self._req else None, err=show_error)

    def _fill(self, page, res):
        items, total, pages = res
        self.rows = items
        labels = dict(STATUS)
        with self.table.bulk_update():
            self.table.setRowCount(len(items))
            for r, p in enumerate(items):
                self.table.add_check(r)
                self.table.setItem(r, 1, self.table.item_text(html.unescape((p.get("title") or {}).get("raw") or t("(no title)"))))
                self.table.setItem(r, 2, self.table.item_text(t(labels.get(p.get("status"), p.get("status", "")))))
                self.table.setItem(r, 3, self.table.item_text((p.get("date") or "")[:10]))
                self.table.setItem(r, 4, self.table.item_text(", ".join(html.unescape(self.cat_names.get(i, "")) for i in p.get("categories", []) if i in self.cat_names)))
        self.pager.set_state(page, pages, total)

    def new_post(self):
        if not self.ctx.has_site():
            notify(t("Add a site in Settings first."), "warn")
            return
        if not self.ctx.has_wp():
            notify(t("To manage posts and media, add your WordPress username and application password in Settings."), "warn")
            return
        if PostEditor(self.ctx, None, self).exec() == QDialog.Accepted:
            self.load(1)

    def edit_row(self, row):
        if row < len(self.rows):
            pid = self.rows[row]["id"]
            notify(t("Loading..."), "info", 1200)  # the list only carries a few fields; fetch the full post
            run_async(lambda: self.ctx.wp().post(pid), ok=self._open_editor, err=show_error)

    def _open_editor(self, post):
        if PostEditor(self.ctx, post, self).exec() == QDialog.Accepted:
            self.load()

    def _selected(self):
        return [self.rows[r] for r in self.table.checked_rows() if r < len(self.rows)]

    def bulk_status(self, status):
        sel = self._selected()
        if sel:
            run_async(lambda: [self.ctx.wp().save_post(p["id"], {"status": status}) for p in sel],
                      ok=lambda _r: (notify(t("Done"), "ok"), self.load()), err=show_error)

    def bulk_delete(self, force):
        sel = self._selected()
        if sel and confirm(self, f"{len(sel)} " + (t("posts will be deleted PERMANENTLY. Continue?") if force else t("posts will be moved to trash. Continue?")), danger=True):
            run_async(lambda: [self.ctx.wp().delete_post(p["id"], force) for p in sel],
                      ok=lambda _r: (notify(t("Done"), "ok"), self.load()), err=show_error)
