from __future__ import annotations

import csv
import html
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
                               QMenu, QToolButton, QVBoxLayout, QWidget, QDialogButtonBox)

from ...core.i18n import t
from ...core.workers import run_async
from ..widgets import (DataTable, PageHeader, Pager, SearchBox, button, confirm, notify, show_error, table_thumb)
from .bulk_ai import BulkAIDialog
from .product_editor import ProductEditor

COL_IMG, COL_NAME, COL_SKU, COL_TYPE, COL_REG, COL_SALE, COL_STOCK, COL_STATUS, COL_CATS = range(1, 10)
STATUS_LABELS = {"publish": "Published", "draft": "Draft", "pending": "Pending", "private": "Private"}
CSV_FIELDS = ["id", "sku", "name", "type", "status", "regular_price", "sale_price", "stock_quantity", "stock_status", "categories"]


def plain(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def adjust_price(old: str, pct: float = 0.0, amount: float = 0.0) -> str:
    if old in ("", None):
        return ""
    v = float(old) * (1 + pct / 100.0) + amount
    v = max(v, 0)
    return str(int(round(v))) if "." not in str(old) else f"{v:.2f}"


class PriceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Adjust prices"))
        f = QFormLayout(self)
        self.mode = QComboBox()
        self.mode.addItem(t("Percent (+/-)"), "pct")
        self.mode.addItem(t("Fixed amount (+/-)"), "amt")
        self.val = QDoubleSpinBox()
        self.val.setRange(-1e9, 1e9)
        self.val.setDecimals(2)
        self.sale = QComboBox()
        self.sale.addItem(t("Regular price"), "regular_price")
        self.sale.addItem(t("Sale price"), "sale_price")
        f.addRow(t("Field"), self.sale)
        f.addRow(t("Mode"), self.mode)
        f.addRow(t("Value"), self.val)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class ProductsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        self.rows: list[dict] = []
        self._filling = False
        self._req = 0
        self.cats: list[dict] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        head = PageHeader(t("Products"), t("Manage your WooCommerce catalogue"))
        self.bulk = QToolButton()
        self.bulk.setText(t("Bulk actions") + " ▾")
        self.bulk.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self.bulk)
        for text, fn in [
            ("Set Published", lambda: self.bulk_status("publish")), ("Set Draft", lambda: self.bulk_status("draft")),
            ("Adjust prices...", self.bulk_price), ("Set stock status...", self.bulk_stock),
            ("✨ Generate descriptions with AI...", self.bulk_ai), (None, None),
            ("Export CSV", self.export_csv), ("Import CSV (update/create)", self.import_csv), (None, None),
            ("Move to trash", lambda: self.bulk_delete(False)), ("Delete permanently", lambda: self.bulk_delete(True)),
        ]:
            if text is None:
                m.addSeparator()
            else:
                m.addAction(t(text), fn)
        self.bulk.setMenu(m)
        head.add_action(self.bulk)
        head.add_action(button(t("Refresh"), slot=lambda: self.load()))
        head.add_action(button("+ " + t("New product"), primary=True, slot=self.new_product))
        lay.addWidget(head)

        bar = QHBoxLayout()
        self.search = SearchBox(t("Search products..."))
        self.search.changed.connect(lambda _: self.load(1))
        self.f_status = QComboBox()
        self.f_status.addItem(t("All statuses"), "any")
        for k, v in STATUS_LABELS.items():
            self.f_status.addItem(t(v), k)
        self.f_stock = QComboBox()
        self.f_stock.addItem(t("Any stock"), "")
        for k, v in [("instock", "In stock"), ("outofstock", "Out of stock"), ("onbackorder", "On backorder")]:
            self.f_stock.addItem(t(v), k)
        self.f_cat = QComboBox()
        self.f_cat.addItem(t("All categories"), 0)
        for w in (self.f_status, self.f_stock, self.f_cat):
            w.currentIndexChanged.connect(lambda _=0: self.load(1))
        bar.addWidget(self.search, 1)
        bar.addWidget(self.f_status)
        bar.addWidget(self.f_stock)
        bar.addWidget(self.f_cat)
        lay.addLayout(bar)

        self.table = DataTable([t("Image"), t("Name"), "SKU", t("Type"), t("Price"), t("Sale"), t("Stock"), t("Status"), t("Categories")])
        self.table.setColumnWidth(COL_IMG, 60)
        self.table.setColumnWidth(COL_NAME, 280)
        self.table.setColumnWidth(COL_SKU, 100)
        self.table.setColumnWidth(COL_TYPE, 80)
        self.table.setColumnWidth(COL_REG, 90)
        self.table.setColumnWidth(COL_SALE, 90)
        self.table.setColumnWidth(COL_STOCK, 90)
        self.table.setColumnWidth(COL_STATUS, 90)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self._double_click)
        self.table.itemChanged.connect(self._item_changed)
        lay.addWidget(self.table, 1)
        self.pager = Pager()
        self.pager.page_changed.connect(self.load)
        lay.addWidget(self.pager)
        self.page = 1
        self._loaded_once = False

    # ------------------------------------------------------------ load ---
    def on_show(self):
        if not self._loaded_once and self.ctx.has_site():
            self._loaded_once = True
            run_async(self.ctx.woo_categories, ok=self._cats_loaded, err=show_error)
            self.load(1)

    def site_changed(self):
        self._loaded_once = False
        self.table.setRowCount(0)

    def _cats_loaded(self, cats):
        self.cats = cats
        cur = self.f_cat.currentData()
        self.f_cat.blockSignals(True)
        self.f_cat.clear()
        self.f_cat.addItem(t("All categories"), 0)
        for c in sorted(cats, key=lambda x: x["name"]):
            self.f_cat.addItem(html.unescape(c["name"]), c["id"])
        i = self.f_cat.findData(cur)
        self.f_cat.setCurrentIndex(max(i, 0))
        self.f_cat.blockSignals(False)

    def load(self, page: int | None = None):
        if page:
            self.page = page
        if not self.ctx.has_site():
            notify(t("Add a site in Settings first."), "warn")
            return
        pg = self.page
        q, st, sk, cat = self.search.text().strip(), self.f_status.currentData(), self.f_stock.currentData(), self.f_cat.currentData()
        self._req += 1
        req = self._req  # typing/filtering fires several requests; answers can arrive out of order, show only the newest
        run_async(lambda: self.ctx.woo().products(pg, 20, q, st, cat or None, sk),
                  ok=lambda r: self._fill(pg, r) if req == self._req else None, err=show_error)

    def _fill(self, page, res):
        items, total, pages = res
        self.rows = items
        self._filling = True
        with self.table.bulk_update():  # one repaint + no per-cell signals instead of ~200
            self.table.setRowCount(len(items))
            for r, p in enumerate(items):
                self.table.add_check(r)
                variable = p.get("type") == "variable"
                self.table.setItem(r, COL_NAME, self.table.item_text(html.unescape(p.get("name", "")), data=p["id"]))
                self.table.setItem(r, COL_SKU, self.table.item_text(p.get("sku", "")))
                self.table.setItem(r, COL_TYPE, self.table.item_text(t(p.get("type", "").capitalize())))
                price_editable = not variable and p.get("type") != "grouped"
                self.table.setItem(r, COL_REG, self.table.item_text(p.get("regular_price", "") if price_editable else p.get("price", ""), editable=price_editable))
                self.table.setItem(r, COL_SALE, self.table.item_text(p.get("sale_price", "") if price_editable else "", editable=price_editable))
                if p.get("manage_stock"):
                    self.table.setItem(r, COL_STOCK, self.table.item_text(p.get("stock_quantity", 0), editable=True))
                else:
                    self.table.setItem(r, COL_STOCK, self.table.item_text(t({"instock": "In stock", "outofstock": "Out of stock", "onbackorder": "Backorder"}.get(p.get("stock_status"), "-"))))
                self.table.setItem(r, COL_STATUS, self.table.item_text(t(STATUS_LABELS.get(p.get("status"), p.get("status", "")))))
                self.table.setItem(r, COL_CATS, self.table.item_text(", ".join(html.unescape(c["name"]) for c in p.get("categories", []))))
                imgs = p.get("images") or []
                if imgs:
                    table_thumb(self.table, r, COL_IMG, imgs[0].get("src", ""))
        self._filling = False
        self.pager.set_state(page, pages, total)

    # ------------------------------------------------------ inline edit ---
    def _double_click(self, row, col):
        item = self.table.item(row, col)
        if item and not (item.flags() & Qt.ItemIsEditable) and col > 0:
            self.edit_row(row)

    def _item_changed(self, item):
        if self._filling or item.row() >= len(self.rows):
            return
        p, col, text = self.rows[item.row()], item.column(), item.text().strip()
        try:
            if col == COL_REG:
                data = {"regular_price": text}
            elif col == COL_SALE:
                data = {"sale_price": text}
            elif col == COL_STOCK:
                data = {"stock_quantity": int(float(text))}
            else:
                return
        except ValueError:
            notify(t("Invalid number"), "error")
            self.load()
            return
        run_async(lambda: self.ctx.woo().save_product(p["id"], data),
                  ok=lambda saved: (self.rows.__setitem__(item.row(), saved), notify(t("Saved"), "ok", 1500)),
                  err=lambda e: (show_error(e), self.load()))

    # --------------------------------------------------------- editing ---
    def new_product(self):
        if not self.ctx.has_site():
            notify(t("Add a site in Settings first."), "warn")
            return
        if ProductEditor(self.ctx, None, self).exec() == QDialog.Accepted:
            self.load(1)

    def edit_row(self, row: int):
        if row < len(self.rows):
            pid = self.rows[row]["id"]
            notify(t("Loading..."), "info", 1200)  # the list only carries a few fields; fetch the full product
            run_async(lambda: self.ctx.woo().product(pid), ok=self._open_editor, err=show_error)

    def _open_editor(self, product: dict):
        ProductEditor(self.ctx, product, self).exec()
        self.load()

    # ------------------------------------------------------------ bulk ---
    def _selected(self) -> list[dict]:
        return [self.rows[r] for r in self.table.checked_rows() if r < len(self.rows)]

    def _batch(self, update=None, delete=None, msg="Done"):
        run_async(lambda: self.ctx.woo().batch_products(update=update, delete=delete),
                  ok=lambda _r: (notify(t(msg), "ok"), self.load()), err=lambda e: (show_error(e), self.load()))

    def bulk_status(self, status: str):
        sel = self._selected()
        if sel:
            self._batch(update=[{"id": p["id"], "status": status} for p in sel])

    def bulk_stock(self):
        sel = self._selected()
        if not sel:
            return
        opts = [("instock", t("In stock")), ("outofstock", t("Out of stock")), ("onbackorder", t("On backorder"))]
        choice, ok = QInputDialog.getItem(self, t("Set stock status"), t("Stock status"), [o[1] for o in opts], 0, False)
        if ok:
            val = dict((o[1], o[0]) for o in opts)[choice]
            self._batch(update=[{"id": p["id"], "manage_stock": False, "stock_status": val} for p in sel])

    def bulk_price(self):
        sel = [p for p in self._selected() if p.get("type") in ("simple", "external")]
        if not sel:
            notify(t("Select simple products first."), "warn")
            return
        dlg = PriceDialog(self)
        if dlg.exec() != QDialog.Accepted or dlg.val.value() == 0:
            return
        field = dlg.sale.currentData()
        pct = dlg.val.value() if dlg.mode.currentData() == "pct" else 0.0
        amt = dlg.val.value() if dlg.mode.currentData() == "amt" else 0.0
        upd = [{"id": p["id"], field: adjust_price(p.get(field, ""), pct, amt)} for p in sel if p.get(field)]
        if upd and confirm(self, f"{len(upd)} " + t("prices will change. Continue?")):
            self._batch(update=upd, msg="Prices updated")

    def bulk_delete(self, force: bool):
        sel = self._selected()
        if not sel:
            return
        text = f"{len(sel)} " + (t("products will be deleted PERMANENTLY. Continue?") if force else t("products will be moved to trash. Continue?"))
        if confirm(self, text, danger=True):
            if force:
                self._batch(delete=[p["id"] for p in sel], msg="Deleted")
            else:
                run_async(lambda: [self.ctx.woo().delete_product(p["id"], False) for p in sel],
                          ok=lambda _r: (notify(t("Moved to trash"), "ok"), self.load()), err=show_error)

    def bulk_ai(self):
        sel = self._selected()
        if sel and BulkAIDialog(self.ctx, sel, self).exec():
            self.load()

    # ------------------------------------------------------------- csv ---
    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, t("Export CSV"), "products.csv", "CSV (*.csv)")
        if not path:
            return
        q, st, sk, cat = self.search.text().strip(), self.f_status.currentData(), self.f_stock.currentData(), self.f_cat.currentData()
        notify(t("Exporting..."), "info", 2000)

        def work():
            woo, out, page = self.ctx.woo(), [], 1
            while page <= 100:
                items, _t, pages = woo.products(page, 100, q, st, cat or None, sk)
                out.extend(items)
                if page >= pages:
                    break
                page += 1
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, CSV_FIELDS)
                w.writeheader()
                for p in out:
                    w.writerow({
                        "id": p["id"], "sku": p.get("sku", ""), "name": html.unescape(p.get("name", "")), "type": p.get("type", ""),
                        "status": p.get("status", ""), "regular_price": p.get("regular_price", ""), "sale_price": p.get("sale_price", ""),
                        "stock_quantity": "" if p.get("stock_quantity") is None else p["stock_quantity"],
                        "stock_status": p.get("stock_status", ""), "categories": "|".join(html.unescape(c["name"]) for c in p.get("categories", [])),
                    })
            return len(out)

        run_async(work, ok=lambda n: notify(f"{n} " + t("products exported"), "ok"), err=show_error)

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, t("Import CSV"), "", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except Exception as e:  # noqa: BLE001
            show_error(e)
            return
        if not rows or not confirm(self, f"{len(rows)} " + t("rows found. Existing products (matched by id or SKU) will be updated, others created. Continue?")):
            return

        def work():
            woo = self.ctx.woo()
            updates, creates = [], []
            for r in rows:
                data = {}
                for k in ("name", "status", "regular_price", "sale_price", "stock_status"):
                    if r.get(k) not in (None, ""):
                        data[k] = r[k]
                if r.get("stock_quantity") not in (None, ""):
                    data["manage_stock"] = True
                    data["stock_quantity"] = int(float(r["stock_quantity"]))
                pid = int(r["id"]) if str(r.get("id", "")).isdigit() else None
                if not pid and r.get("sku"):
                    found = woo.page("/products", {"sku": r["sku"], "per_page": 1})[0]
                    pid = found[0]["id"] if found else None
                if pid:
                    updates.append({"id": pid, **data})
                elif data.get("name"):
                    if r.get("sku"):
                        data["sku"] = r["sku"]
                    creates.append(data)
            woo.batch_products(create=creates, update=updates)
            return len(creates), len(updates)

        run_async(work, ok=lambda r: (notify(f"{r[0]} " + t("created") + f", {r[1]} " + t("updated"), "ok"), self.load()), err=show_error)
