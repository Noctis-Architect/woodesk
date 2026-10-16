from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget, QInputDialog, QAbstractItemView, QHeaderView)
from PySide6.QtCore import QDate

from ...ai import prompts
from ...api.woo import combo_key, variation_combos
from ...core.config import cfg
from ...core.i18n import t
from ...core.workers import run_async
from ..ai_assist import AIButton, run_ai
from ..components import ImagesEditor, TaxonomyPicker
from ..widgets import HtmlEditor, button, label, ltr, notify, show_error

SEO_KEYS = {
    "yoast": ("_yoast_wpseo_title", "_yoast_wpseo_metadesc", "_yoast_wpseo_focuskw"),
    "rankmath": ("rank_math_title", "rank_math_description", "rank_math_focus_keyword"),
}


def _meta(p: dict, key: str) -> str:
    for m in p.get("meta_data", []) or []:
        if m.get("key") == key:
            return str(m.get("value") or "")
    return ""


class ProductEditor(QDialog):
    def __init__(self, ctx, product: dict | None = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.p = product or {}
        self.setWindowTitle(t("Edit product") if product else t("New product"))
        self.resize(900, 720)
        self.cats: list[dict] = []
        self.vars: list[dict] = []
        self.vars_dirty: set[int] = set()
        self._loading_vars = False

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self._general()
        self._inventory()
        self._images()
        self._taxonomy()
        self._variations()
        self._seo()
        self._shipping()
        row = QHBoxLayout()
        self.status_lbl = label("", muted=True)
        row.addWidget(self.status_lbl)
        row.addStretch()
        row.addWidget(button(t("Cancel"), slot=self.reject))
        self.save_btn = button(t("Save"), primary=True, slot=self.save)
        row.addWidget(self.save_btn)
        lay.addLayout(row)
        self._fill()
        run_async(self._load_taxonomy, ok=self._taxonomy_loaded, err=show_error)
        self._on_type()

    # ------------------------------------------------------------ tabs ---
    def _general(self):
        w = QWidget()
        f = QFormLayout(w)
        self.name = QLineEdit()
        self.slug = ltr(QLineEdit())
        self.type = QComboBox()
        for k, v in [("simple", "Simple"), ("variable", "Variable"), ("grouped", "Grouped"), ("external", "External/Affiliate")]:
            self.type.addItem(t(v), k)
        self.type.currentIndexChanged.connect(self._on_type)
        self.status = QComboBox()
        for k, v in [("publish", "Published"), ("draft", "Draft"), ("pending", "Pending review"), ("private", "Private")]:
            self.status.addItem(t(v), k)
        self.featured = QCheckBox(t("Featured product"))
        self.sku = ltr(QLineEdit())
        self.regular = ltr(QLineEdit())
        self.sale = ltr(QLineEdit())
        self.sale_from = QDateEdit(calendarPopup=True)
        self.sale_to = QDateEdit(calendarPopup=True)
        self.sched = QCheckBox(t("Schedule sale"))
        self.sched.toggled.connect(lambda on: (self.sale_from.setEnabled(on), self.sale_to.setEnabled(on)))
        self.sale_from.setEnabled(False)
        self.sale_to.setEnabled(False)
        self.sale_from.setDate(QDate.currentDate())
        self.sale_to.setDate(QDate.currentDate().addDays(7))
        self.ext_url = ltr(QLineEdit())
        self.ext_btn = QLineEdit()
        f.addRow(t("Name"), self.name)
        f.addRow(t("Slug"), self.slug)
        r1 = QHBoxLayout()
        r1.addWidget(self.type)
        r1.addWidget(self.status)
        r1.addWidget(self.featured)
        f.addRow(t("Type / Status"), r1)
        f.addRow("SKU", self.sku)
        r2 = QHBoxLayout()
        r2.addWidget(label(t("Regular price")))
        r2.addWidget(self.regular)
        r2.addWidget(label(t("Sale price")))
        r2.addWidget(self.sale)
        self.price_row = QWidget()
        self.price_row.setLayout(r2)
        r2.setContentsMargins(0, 0, 0, 0)
        f.addRow(t("Price"), self.price_row)
        r3 = QHBoxLayout()
        r3.addWidget(self.sched)
        r3.addWidget(self.sale_from)
        r3.addWidget(self.sale_to)
        self.sched_row = QWidget()
        self.sched_row.setLayout(r3)
        r3.setContentsMargins(0, 0, 0, 0)
        f.addRow("", self.sched_row)
        self.ext_row = QWidget()
        r4 = QHBoxLayout(self.ext_row)
        r4.setContentsMargins(0, 0, 0, 0)
        r4.addWidget(self.ext_url)
        r4.addWidget(self.ext_btn)
        self.ext_url.setPlaceholderText(t("Product URL"))
        self.ext_btn.setPlaceholderText(t("Button text"))
        f.addRow(t("External"), self.ext_row)
        self.general_form = f
        self.short = HtmlEditor(90)
        self.desc = HtmlEditor(220)
        self.ai_desc_btn = AIButton("Generate with AI", self.ai_description, "Write the description from the product name and attributes")
        self.ai_desc_btn.add("Improve selection / text", self.ai_improve)
        self.ai_desc_btn.add("Translate to English", lambda: self.ai_translate("en"))
        self.ai_desc_btn.add("Translate to Persian", lambda: self.ai_translate("fa"))
        self.desc.add_leading(self.ai_desc_btn)
        self.ai_short_btn = AIButton("Generate with AI", self.ai_short, "Write a short summary from the name and description")
        self.short.add_leading(self.ai_short_btn)
        f.addRow(t("Short description"), self.short)
        f.addRow(t("Description"), self.desc)
        self.tabs.addTab(w, t("General"))

    def _inventory(self):
        w = QWidget()
        f = QFormLayout(w)
        self.manage = QCheckBox(t("Manage stock"))
        self.qty = QSpinBox()
        self.qty.setRange(-100000, 10000000)
        self.stock_status = QComboBox()
        for k, v in [("instock", "In stock"), ("outofstock", "Out of stock"), ("onbackorder", "On backorder")]:
            self.stock_status.addItem(t(v), k)
        self.backorders = QComboBox()
        for k, v in [("no", "Do not allow"), ("notify", "Allow, notify customer"), ("yes", "Allow")]:
            self.backorders.addItem(t(v), k)
        self.sold_ind = QCheckBox(t("Sold individually"))
        self.manage.toggled.connect(lambda on: (self.qty.setEnabled(on), self.backorders.setEnabled(on), self.stock_status.setEnabled(not on)))
        f.addRow(self.manage)
        f.addRow(t("Quantity"), self.qty)
        f.addRow(t("Stock status"), self.stock_status)
        f.addRow(t("Backorders"), self.backorders)
        f.addRow(self.sold_ind)
        self.qty.setEnabled(False)
        self.backorders.setEnabled(False)
        self.tabs.addTab(w, t("Inventory"))

    def _shipping(self):
        w = QWidget()
        f = QFormLayout(w)
        self.weight = ltr(QLineEdit())
        self.dim_l, self.dim_w, self.dim_h = ltr(QLineEdit()), ltr(QLineEdit()), ltr(QLineEdit())
        row = QHBoxLayout()
        for x, ph in ((self.dim_l, "L"), (self.dim_w, "W"), (self.dim_h, "H")):
            x.setPlaceholderText(ph)
            row.addWidget(x)
        f.addRow(t("Weight"), self.weight)
        f.addRow(t("Dimensions"), row)
        self.tabs.addTab(w, t("Shipping"))

    def _images(self):
        self.images = ImagesEditor(self.ctx)
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(label(t("The first image is the main product image."), muted=True))
        v.addWidget(self.images)
        self.tabs.addTab(w, t("Images"))

    def _taxonomy(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(label(t("Categories"), "h2"))
        self.cat_picker = TaxonomyPicker(self.ctx.create_woo_category)
        v.addWidget(self.cat_picker)
        v.addWidget(label(t("Tags (comma separated)"), "h2"))
        self.tags = QLineEdit()
        v.addWidget(self.tags)
        self.ai_tags_btn = AIButton("Suggest tags", self.ai_tags)
        v.addWidget(self.ai_tags_btn)
        self.tabs.addTab(w, t("Categories & tags"))

    def _variations(self):
        self.var_tab = QWidget()
        v = QVBoxLayout(self.var_tab)
        v.addWidget(label(t("Attributes"), "h2"))
        self.attr_table = QTableWidget(0, 4)
        self.attr_table.setHorizontalHeaderLabels([t("Name"), t("Values (comma separated)"), t("Visible"), t("Used for variations")])
        self.attr_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.attr_table.setMaximumHeight(170)
        v.addWidget(self.attr_table)
        row = QHBoxLayout()
        row.addWidget(button(t("+ Attribute"), slot=self._add_attr))
        row.addWidget(button(t("Remove attribute"), danger=True, slot=self._del_attr))
        row.addStretch()
        v.addLayout(row)
        v.addWidget(label(t("Variations"), "h2"))
        self.var_table = QTableWidget(0, 6)
        self.var_table.setHorizontalHeaderLabels(["ID", t("Attributes"), "SKU", t("Regular price"), t("Sale price"), t("Stock")])
        self.var_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.var_table.itemChanged.connect(self._var_edited)
        v.addWidget(self.var_table)
        row = QHBoxLayout()
        row.addWidget(button(t("Generate all variations"), slot=self.generate_variations))
        row.addWidget(button(t("Set price for all"), slot=self.price_all))
        row.addWidget(button(t("Delete selected"), danger=True, slot=self.delete_variations))
        row.addStretch()
        v.addLayout(row)
        self.tabs.addTab(self.var_tab, t("Variations"))

    def _seo(self):
        w = QWidget()
        f = QFormLayout(w)
        self.seo_plugin = QComboBox()
        self.seo_plugin.addItem(t("None (don't write SEO fields)"), "")
        self.seo_plugin.addItem("Yoast SEO", "yoast")
        self.seo_plugin.addItem("Rank Math", "rankmath")
        self.seo_title = QLineEdit()
        self.seo_desc = QLineEdit()
        self.seo_kw = QLineEdit()
        self.ai_seo_btn = AIButton("Generate SEO fields", self.ai_seo)
        f.addRow(t("SEO plugin"), self.seo_plugin)
        f.addRow(t("Meta title"), self.seo_title)
        f.addRow(t("Meta description"), self.seo_desc)
        f.addRow(t("Focus keyword"), self.seo_kw)
        f.addRow("", self.ai_seo_btn)
        f.addRow("", label(t("Your SEO plugin must expose these meta fields to the REST API for them to be saved."), muted=True, wrap=True))
        self.tabs.addTab(w, "SEO")

    # ------------------------------------------------------------ data ---
    def _fill(self):
        p = self.p
        self.name.setText(p.get("name", ""))
        self.slug.setText(p.get("slug", ""))
        self._set_combo(self.type, p.get("type", "simple"))
        self._set_combo(self.status, p.get("status", "publish" if not p else "draft"))
        self.featured.setChecked(bool(p.get("featured")))
        self.sku.setText(p.get("sku", ""))
        self.regular.setText(str(p.get("regular_price", "") or ""))
        self.sale.setText(str(p.get("sale_price", "") or ""))
        if p.get("date_on_sale_from") or p.get("date_on_sale_to"):
            self.sched.setChecked(True)
            for ed, key in ((self.sale_from, "date_on_sale_from"), (self.sale_to, "date_on_sale_to")):
                if p.get(key):
                    ed.setDate(QDate.fromString(p[key][:10], "yyyy-MM-dd"))
        self.ext_url.setText(p.get("external_url", "") or "")
        self.ext_btn.setText(p.get("button_text", "") or "")
        self.short.set_text(p.get("short_description", ""))
        self.desc.set_text(p.get("description", ""))
        self.manage.setChecked(bool(p.get("manage_stock")))
        self.qty.setValue(int(p.get("stock_quantity") or 0))
        self._set_combo(self.stock_status, p.get("stock_status", "instock"))
        self._set_combo(self.backorders, p.get("backorders", "no"))
        self.sold_ind.setChecked(bool(p.get("sold_individually")))
        self.stock_status.setEnabled(not self.manage.isChecked())
        self.weight.setText(p.get("weight", "") or "")
        d = p.get("dimensions") or {}
        self.dim_l.setText(d.get("length", ""))
        self.dim_w.setText(d.get("width", ""))
        self.dim_h.setText(d.get("height", ""))
        self.images.set_images(p.get("images", []))
        self.tags.setText(", ".join(t_["name"] for t_ in p.get("tags", [])))
        for plugin, keys in SEO_KEYS.items():
            if any(_meta(p, k) for k in keys):
                self._set_combo(self.seo_plugin, plugin)
                self.seo_title.setText(_meta(p, keys[0]))
                self.seo_desc.setText(_meta(p, keys[1]))
                self.seo_kw.setText(_meta(p, keys[2]))
                break
        for a in p.get("attributes", []):
            self._add_attr(a)
        if p.get("id") and p.get("type") == "variable":
            self._load_variations()

    @staticmethod
    def _set_combo(cb: QComboBox, data) -> None:
        i = cb.findData(data)
        if i >= 0:
            cb.setCurrentIndex(i)

    def _on_type(self):
        ty = self.type.currentData()
        self.price_row.setEnabled(ty in ("simple", "external"))
        self.sched_row.setEnabled(ty in ("simple", "external"))
        self.general_form.setRowVisible(self.ext_row, ty == "external")
        self.tabs.setTabEnabled(self.tabs.indexOf(self.var_tab), ty in ("variable", "simple"))

    def _load_taxonomy(self):
        return self.ctx.woo_categories()  # cached per site: opening the editor again is instant

    def _taxonomy_loaded(self, cats):
        self.cats = cats
        self.cat_picker.set_categories(self.cats, {c["id"] for c in self.p.get("categories", [])})

    # ------------------------------------------------------ attributes ---
    def _add_attr(self, attr=None):
        attr = attr if isinstance(attr, dict) else {}
        r = self.attr_table.rowCount()
        self.attr_table.insertRow(r)
        name = QTableWidgetItem(attr.get("name", ""))
        name.setData(Qt.UserRole, attr.get("id", 0))
        self.attr_table.setItem(r, 0, name)
        self.attr_table.setItem(r, 1, QTableWidgetItem(", ".join(attr.get("options", []))))
        for c, key, default in ((2, "visible", True), (3, "variation", False)):
            it = QTableWidgetItem()
            it.setFlags((it.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            it.setCheckState(Qt.Checked if attr.get(key, default) else Qt.Unchecked)
            self.attr_table.setItem(r, c, it)

    def _del_attr(self):
        r = self.attr_table.currentRow()
        if r >= 0:
            self.attr_table.removeRow(r)

    def attributes(self) -> list[dict]:
        out = []
        for r in range(self.attr_table.rowCount()):
            name = self.attr_table.item(r, 0).text().strip()
            opts = [o.strip() for o in self.attr_table.item(r, 1).text().split(",") if o.strip()]
            if not name or not opts:
                continue
            out.append({
                "id": self.attr_table.item(r, 0).data(Qt.UserRole) or 0, "name": name, "position": r,
                "visible": self.attr_table.item(r, 2).checkState() == Qt.Checked,
                "variation": self.attr_table.item(r, 3).checkState() == Qt.Checked, "options": opts,
            })
        return out

    # ------------------------------------------------------ variations ---
    def _load_variations(self):
        run_async(lambda: self.ctx.woo().variations(self.p["id"]), ok=self._show_variations, err=show_error)

    def _show_variations(self, vs):
        self.vars = vs
        self.vars_dirty.clear()
        self._loading_vars = True
        self.var_table.setRowCount(len(vs))
        for r, v in enumerate(vs):
            desc = " / ".join(f"{a.get('name')}: {a.get('option')}" for a in v.get("attributes", []))
            self.var_table.setItem(r, 0, self._ro(str(v["id"])))
            self.var_table.setItem(r, 1, self._ro(desc))
            self.var_table.setItem(r, 2, QTableWidgetItem(v.get("sku", "")))
            self.var_table.setItem(r, 3, QTableWidgetItem(str(v.get("regular_price", ""))))
            self.var_table.setItem(r, 4, QTableWidgetItem(str(v.get("sale_price", ""))))
            self.var_table.setItem(r, 5, QTableWidgetItem("" if v.get("stock_quantity") is None else str(v["stock_quantity"])))
        self._loading_vars = False

    @staticmethod
    def _ro(text):
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        return it

    def _var_edited(self, item):
        if not self._loading_vars:
            self.vars_dirty.add(item.row())

    def _require_saved(self) -> bool:
        if not self.p.get("id"):
            notify(t("Save the product first (type: Variable), then manage variations."), "warn")
            return False
        return True

    def generate_variations(self):
        if not self._require_saved():
            return
        attrs = self.attributes()
        combos = variation_combos(attrs)
        existing = {combo_key(v.get("attributes", [])) for v in self.vars}
        new = [c for c in combos if combo_key(c) not in existing]
        if not new:
            notify(t("Nothing to generate. Mark attributes as 'Used for variations' and save first."), "warn")
            return
        pid = self.p["id"]

        def work():
            # attributes must be stored on the product before variations can reference them
            self.ctx.woo().save_product(pid, {"attributes": attrs})
            self.ctx.woo().batch_variations(pid, create=[{"attributes": c} for c in new])
            return self.ctx.woo().variations(pid)

        run_async(work, ok=lambda vs: (self._show_variations(vs), notify(f"{len(new)} " + t("variations created"), "ok")), err=show_error)

    def price_all(self):
        if not self.vars:
            return
        price, ok = QInputDialog.getText(self, t("Set price for all"), t("Regular price:"))
        if ok and price.strip():
            self._loading_vars = True
            for r in range(self.var_table.rowCount()):
                self.var_table.item(r, 3).setText(price.strip())
                self.vars_dirty.add(r)
            self._loading_vars = False

    def delete_variations(self):
        rows = sorted({i.row() for i in self.var_table.selectedIndexes()})
        if not rows or not self._require_saved():
            return
        ids = [self.vars[r]["id"] for r in rows]
        pid = self.p["id"]
        run_async(lambda: (self.ctx.woo().batch_variations(pid, delete=ids), self.ctx.woo().variations(pid))[1],
                  ok=self._show_variations, err=show_error)

    def _variation_updates(self) -> list[dict]:
        out = []
        for r in sorted(self.vars_dirty):
            if r >= len(self.vars):
                continue
            g = lambda c: self.var_table.item(r, c).text().strip()  # noqa: E731
            u = {"id": self.vars[r]["id"], "sku": g(2), "regular_price": g(3), "sale_price": g(4)}
            if g(5) != "":
                u["manage_stock"] = True
                u["stock_quantity"] = int(float(g(5)))
            out.append(u)
        return out

    # ------------------------------------------------------------- AI ---
    def _lang(self) -> str:
        return cfg.ai.output_language

    def _ai_context(self) -> str:
        """A short brief with everything the AI needs: title, type, status, price, categories, existing text."""
        cats = ", ".join(self.cat_picker.selected_names()) or "-"
        price = self.regular.text().strip() or "-"
        sale = self.sale.text().strip()
        price_str = f"{price} (sale: {sale})" if sale else price
        parts = [
            f"Title: {self.name.text().strip() or '-'}",
            f"Type: {self.type.currentText()}",
            f"Status: {self.status.currentText()}",
            f"Price: {price_str}",
            f"SKU: {self.sku.text().strip() or '-'}",
            f"Categories: {cats}",
            f"Short description: {self.short.text().strip() or '-'}",
        ]
        existing = self.desc.text().strip()
        if existing:
            parts.append(f"Current full description (may be improved/reused): {existing}")
        return "\n".join(parts)

    def ai_description(self):
        if not self.name.text().strip():
            notify(t("Enter the product name first."), "warn")
            return
        details = ", ".join(f"{a['name']}: {', '.join(a['options'])}" for a in self.attributes())
        msgs = prompts.product_description(self.name.text(), self._lang(), details, self.desc.text(), context=self._ai_context())
        run_ai(self, self.ctx, msgs, self.desc.set_text, t("Product description"), max_tokens=1500, busy=self.ai_desc_btn)

    def ai_improve(self):
        sel = self.desc.selected_text()
        text = sel or self.desc.text()
        if not text:
            return
        msgs = prompts.rewrite(text, self._lang())
        run_ai(self, self.ctx, msgs, (self.desc.replace_selection if sel else self.desc.set_text), t("Improve text"),
               max_tokens=1500, busy=self.ai_desc_btn)

    def ai_translate(self, lang: str):
        text = self.desc.selected_text() or self.desc.text()
        if text:
            sel = bool(self.desc.selected_text())
            run_ai(self, self.ctx, prompts.translate(text, lang), (self.desc.replace_selection if sel else self.desc.set_text),
                   t("Translate"), max_tokens=1500, busy=self.ai_desc_btn)

    def ai_short(self):
        if not self.name.text().strip():
            notify(t("Enter the product name first."), "warn")
            return
        msgs = prompts.product_short(self.name.text(), self._lang(), self.desc.text(), context=self._ai_context())
        run_ai(self, self.ctx, msgs, self.short.set_text, t("Short description"), max_tokens=300, busy=self.ai_short_btn)

    def ai_tags(self):
        msgs = prompts.suggest_tags(f"{self.name.text()}\n{self.desc.text()}", self._lang(), context=self._ai_context())
        run_ai(self, self.ctx, msgs, self.tags.setText, t("Tags"), max_tokens=200, busy=self.ai_tags_btn)

    def ai_seo(self):
        msgs = prompts.seo_meta(self.name.text(), self._lang(), self.desc.text(), self.seo_kw.text(), context=self._ai_context())

        def apply(d: dict):
            self.seo_title.setText(d.get("title", ""))
            self.seo_desc.setText(d.get("description", ""))
            self.seo_kw.setText(d.get("focus_keyword", self.seo_kw.text()))
            if d.get("slug") and not self.slug.text():
                self.slug.setText(d["slug"])
            if not self.seo_plugin.currentData():
                notify(t("Choose your SEO plugin above to save these fields."), "warn")

        run_ai(self, self.ctx, msgs, apply, "SEO", json_mode=True, max_tokens=400, busy=self.ai_seo_btn)

    # ----------------------------------------------------------- save ---
    def collect(self) -> dict:
        ty = self.type.currentData()
        d: dict = {
            "name": self.name.text().strip(), "type": ty, "status": self.status.currentData(),
            "featured": self.featured.isChecked(), "sku": self.sku.text().strip(),
            "short_description": self.short.text(), "description": self.desc.text(),
            "manage_stock": self.manage.isChecked(), "sold_individually": self.sold_ind.isChecked(),
            "weight": self.weight.text().strip(),
            "dimensions": {"length": self.dim_l.text().strip(), "width": self.dim_w.text().strip(), "height": self.dim_h.text().strip()},
            "categories": [{"id": i} for i in self.cat_picker.selected_ids()],
            "images": self.images.payload(),
        }
        if self.slug.text().strip():
            d["slug"] = self.slug.text().strip()
        if d["manage_stock"]:
            d["stock_quantity"] = self.qty.value()
            d["backorders"] = self.backorders.currentData()
        else:
            d["stock_status"] = self.stock_status.currentData()
        if ty in ("simple", "external"):
            d["regular_price"] = self.regular.text().strip()
            d["sale_price"] = self.sale.text().strip()
            if self.sched.isChecked():
                d["date_on_sale_from"] = self.sale_from.date().toString("yyyy-MM-dd") + "T00:00:00"
                d["date_on_sale_to"] = self.sale_to.date().toString("yyyy-MM-dd") + "T23:59:59"
            else:
                d["date_on_sale_from"] = d["date_on_sale_to"] = None
        if ty == "external":
            d["external_url"] = self.ext_url.text().strip()
            d["button_text"] = self.ext_btn.text().strip()
        d["attributes"] = self.attributes()
        plugin = self.seo_plugin.currentData()
        if plugin:
            kt, kd, kk = SEO_KEYS[plugin]
            d["meta_data"] = [{"key": kt, "value": self.seo_title.text()}, {"key": kd, "value": self.seo_desc.text()},
                              {"key": kk, "value": self.seo_kw.text()}]
        return d

    def save(self):
        d = self.collect()
        if not d["name"]:
            notify(t("Product name is required."), "warn")
            return
        try:
            var_updates = self._variation_updates()
        except ValueError:
            notify(t("Invalid stock quantity in variations."), "error")
            return
        tag_names = [x.strip() for x in self.tags.text().split(",") if x.strip()]
        pid = self.p.get("id")
        was_new = not pid
        self.save_btn.setEnabled(False)
        self.status_lbl.setText(t("Saving..."))

        def work():
            woo = self.ctx.woo()
            d["tags"] = [{"id": i} for i in woo.ensure_tags(tag_names)]
            saved = woo.save_product(pid, d)
            if var_updates and saved.get("id"):
                woo.batch_variations(saved["id"], update=var_updates)
            return saved

        def done(saved):
            self.p = saved
            self.save_btn.setEnabled(True)
            self.status_lbl.setText("")
            if was_new and saved.get("type") == "variable":
                notify(t("Saved. You can now generate variations."), "ok")
                self.setWindowTitle(t("Edit product"))
                return
            notify(t("Product saved"), "ok")
            self.accept()

        def fail(e):
            self.save_btn.setEnabled(True)
            self.status_lbl.setText("")
            show_error(e)

        run_async(work, ok=done, err=fail)
