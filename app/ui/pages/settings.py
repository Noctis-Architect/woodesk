from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QRadioButton, QScrollArea, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from ... import __version__
from ...ai.catalog import catalog
from ...ai.provider import DynamicProviderClient
from ...api.http import domain_of, normalize_url
from ...api.woo import WooClient
from ...api.wp import WPClient
from ...core import secrets
from ...core.config import Site, cfg, new_id
from ...core.context import secret_key
from ...core.i18n import t
from ...core.workers import run_async
from ..widgets import PageHeader, button, confirm, h_align, label, ltr, notify, restart_app, show_error


ABOUT_TEXT = (
    "WooDesk is a free, open-source desktop app for managing your WooCommerce store and WordPress blog. "
    "You can browse, create and edit products, stock, prices, categories, tags, posts and media, all through "
    "your site's official REST API. The built-in AI assistant writes product descriptions, post drafts, excerpts, "
    "tags and SEO text in the language you choose.\n\n"
    "WooDesk talks directly to your own site using credentials you create yourself. Nothing is routed through "
    "third parties, and passwords and API keys are stored securely by your operating system's keyring. The "
    "optional anonymous statistics can be turned off in the Privacy tab."
)


CREDENTIALS_TEXT = (
    "Products and orders use a WooCommerce key (Settings > Advanced > REST API). "
    "Posts and media use a WordPress application password (Users > Profile > Application Passwords). "
    "Both are created by you and can be revoked at any time; only the access you grant is used."
)


def _scroll(w: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(w)
    return sa


def _tab_page() -> QWidget:
    w = QWidget()
    w.setObjectName("tabPage")
    return w


class SiteDialog(QDialog):
    def __init__(self, ctx, site: Site | None = None, parent=None):
        super().__init__(parent)
        self.ctx, self.site = ctx, site
        self.setWindowTitle(t("Edit site") if site else t("Add site"))
        self.resize(560, 0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        f = QFormLayout()
        self.name = QLineEdit(site.name if site else "")
        self.url = ltr(QLineEdit(site.url if site else ""))
        self.url.setPlaceholderText("https://example.com")
        f.addRow(t("Site name"), self.name)
        f.addRow(t("Site URL"), self.url)
        lay.addLayout(f)

        woobox = QGroupBox(t("WooCommerce - products & orders"))
        wv = QVBoxLayout(woobox)
        wv.addWidget(label(t("WooCommerce > Settings > Advanced > REST API > add a key with Read/Write access. Used for products and orders."), muted=True, wrap=True))
        wf = QFormLayout()
        self.ck = ltr(QLineEdit(secrets.get(secret_key(site.id, "ck")) if site else ""))
        self.cs = ltr(QLineEdit(secrets.get(secret_key(site.id, "cs")) if site else ""))
        self.cs.setEchoMode(QLineEdit.Password)
        self.ck.setPlaceholderText("ck_...")
        self.cs.setPlaceholderText("cs_...")
        wf.addRow(t("Consumer key"), self.ck)
        wf.addRow(t("Consumer secret"), self.cs)
        wv.addLayout(wf)
        lay.addWidget(woobox)

        wpbox = QGroupBox(t("WordPress - posts & media (optional)"))
        pv = QVBoxLayout(wpbox)
        pv.addWidget(label(t("WordPress > Users > Profile > Application Passwords. Only needed for posts and media - create one with any name."), muted=True, wrap=True))
        pf = QFormLayout()
        self.user = ltr(QLineEdit(site.wp_user if site else ""))
        self.app_pw = ltr(QLineEdit(secrets.get(secret_key(site.id, "wp_password")) if site else ""))
        self.app_pw.setEchoMode(QLineEdit.Password)
        self.app_pw.setPlaceholderText("xxxx xxxx xxxx xxxx xxxx xxxx")
        pf.addRow(t("WordPress username"), self.user)
        pf.addRow(t("Application password"), self.app_pw)
        pv.addLayout(pf)
        lay.addWidget(wpbox)

        lay.addWidget(label(t("Your credentials are stored securely by your operating system (keyring) and are never sent anywhere except your own site."), muted=True, wrap=True))
        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setAlignment(h_align() | Qt.AlignTop)
        lay.addWidget(self.result)
        row = QHBoxLayout()
        self.test_btn = button(t("Test connection"), slot=self.test)
        self.test_btn.setAutoDefault(False)
        row.addWidget(self.test_btn)
        row.addStretch()
        cancel = button(t("Cancel"), slot=self.reject)
        cancel.setAutoDefault(False)
        row.addWidget(cancel)
        self.save_btn = button(t("Save"), primary=True, slot=self.save)
        self.save_btn.setDefault(True)
        row.addWidget(self.save_btn)
        lay.addLayout(row)

    def _clients(self):
        url = normalize_url(self.url.text())
        wp = WPClient(url, self.user.text().strip(), self.app_pw.text().strip())
        if self.ck.text().strip() and self.cs.text().strip():
            woo = WooClient(url, self.ck.text().strip(), self.cs.text().strip())
        else:
            woo = WooClient(url, wp_user=self.user.text().strip(), wp_password=self.app_pw.text().strip())
        return wp, woo

    def _has_wp(self) -> bool:
        return bool(self.user.text().strip() and self.app_pw.text().strip())

    def test(self):
        if not self.url.text().strip():
            notify(t("Site URL is required."), "warn")
            return
        wp, woo = self._clients()
        self.test_btn.setEnabled(False)
        self.result.setText(t("Testing..."))
        has_wp = self._has_wp()

        def work():
            out = []
            if has_wp:
                try:
                    me = wp.me()
                    out.append(("ok", f"WordPress: {t('connected as')} {me.get('name') or me.get('slug')}"))
                except Exception as e:  # noqa: BLE001
                    out.append(("error", f"WordPress: {e}"))
            try:
                n = woo.ping()
                out.append(("ok", f"WooCommerce: OK ({n} {t('products')})"))
            except Exception as e:  # noqa: BLE001
                out.append(("error", f"WooCommerce: {e}"))
            return out

        def done(out):
            self.test_btn.setEnabled(True)
            self.result.setText("<br>".join(f"{'✅' if k == 'ok' else '❌'} {m}" for k, m in out))

        run_async(work, ok=done)

    def save(self):
        url = normalize_url(self.url.text())
        if not url:
            notify(t("Site URL is required."), "warn")
            return
        ck, cs = self.ck.text().strip(), self.cs.text().strip()
        user, pw = self.user.text().strip(), self.app_pw.text().strip()
        use_keys = bool(ck and cs)
        if not use_keys and not (user and pw):
            notify(t("Provide either WooCommerce keys or your WordPress username and application password."), "warn")
            return
        if pw and not user:
            notify(t("WordPress username is required with the application password."), "warn")
            return
        s = self.site or Site(id=new_id(), name="", url="")
        s.name = self.name.text().strip() or domain_of(url)
        s.url = url
        s.wp_user = user
        s.use_woo_keys = use_keys
        secrets.set(secret_key(s.id, "wp_password"), pw)
        secrets.set(secret_key(s.id, "ck"), ck if use_keys else "")
        secrets.set(secret_key(s.id, "cs"), cs if use_keys else "")
        if not self.site:
            cfg.add_site(s)
        cfg.save()
        self.site = s
        self.accept()


class SettingsPage(QWidget):
    def __init__(self, ctx, apply_theme):
        super().__init__()
        self.setObjectName("page")
        self.ctx, self.apply_theme = ctx, apply_theme
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(PageHeader(t("Settings")))
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self._sites_tab()
        self._ai_tab()
        self._privacy_tab()
        self._notifications_tab()
        self._appearance_tab()
        self._about_tab()

    def on_show(self):
        self._refresh_sites()
        self._sync_theme_combo()
        self._sync_catalog_ui()
        self._refresh_notification_status()

    def site_changed(self):
        self._refresh_sites()

    # ------------------------------------------------------------ sites ---
    def _sites_tab(self):
        w = _tab_page()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)
        v.addWidget(label(t("Manage the sites WooDesk connects to. The active site is used everywhere in the app."),
                          muted=True, wrap=True))
        self.site_list = QListWidget()
        v.addWidget(self.site_list, 1)
        row = QHBoxLayout()
        row.addWidget(button("+ " + t("Add site"), primary=True, slot=self.add_site))
        row.addWidget(button(t("Edit"), slot=self.edit_site))
        row.addWidget(button(t("Set as active"), slot=self.activate_site))
        row.addStretch()
        row.addWidget(button(t("Remove"), danger=True, slot=self.remove_site))
        v.addLayout(row)
        if not secrets.using_secure_store():
            v.addWidget(label("⚠ " + t("No OS keyring found: secrets are stored in a user-only file (not encrypted)."), muted=True, wrap=True))
        self.tabs.addTab(w, t("Sites"))

    def _refresh_sites(self):
        self.site_list.clear()
        for s in cfg.sites:
            it = QListWidgetItem(("● " if s.id == cfg.active_site else "○ ") + f"{s.name}  -  {s.url}")
            it.setData(Qt.UserRole, s.id)
            self.site_list.addItem(it)

    def _current_site(self) -> Site | None:
        it = self.site_list.currentItem()
        return cfg.site(it.data(Qt.UserRole)) if it else None

    def add_site(self):
        dlg = SiteDialog(self.ctx, None, self)
        if dlg.exec() == QDialog.Accepted:
            self.ctx.reload_clients()
            self._refresh_sites()

    def edit_site(self):
        s = self._current_site()
        if s and SiteDialog(self.ctx, s, self).exec() == QDialog.Accepted:
            self.ctx.reload_clients()
            self._refresh_sites()

    def activate_site(self):
        s = self._current_site()
        if s:
            self.ctx.set_active_site(s.id)
            self._refresh_sites()

    def remove_site(self):
        s = self._current_site()
        if s and confirm(self, t("Remove this site from the app? (Nothing is deleted on the site.)")):
            for k in ("wp_password", "ck", "cs"):
                secrets.delete(secret_key(s.id, k))
            cfg.remove_site(s.id)
            cfg.save()
            self.ctx.reload_clients()
            self._refresh_sites()

    # --------------------------------------------------------------- AI ---
    def _ai_tab(self):
        w = _tab_page()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(14)
        v.addWidget(label(
            t("Choose how WooDesk writes text with AI. The free server option only needs a Gmail and has a daily limit; "
              "your own API key has no limit."),
            muted=True, wrap=True))

        catalog_row = QHBoxLayout()
        self.catalog_lbl = label("", muted=True)
        catalog_row.addWidget(self.catalog_lbl, 1)
        catalog_row.addWidget(button(t("Refresh AI catalog"), slot=self.refresh_catalog))
        v.addLayout(catalog_row)

        mode = QGroupBox(t("How should the AI run?"))
        ml = QVBoxLayout(mode)
        ml.setContentsMargins(14, 18, 14, 14)
        ml.setSpacing(8)
        self.r_server = QRadioButton(t("Use the free AI from the project server (limited daily quota)"))
        self.r_custom = QRadioButton(t("Use my own API key (any provider)"))
        (self.r_server if cfg.ai.mode == "server" else self.r_custom).setChecked(True)
        ml.addWidget(self.r_server)
        ml.addWidget(self.r_custom)
        v.addWidget(mode)

        self.server_box = QGroupBox(t("Free server AI"))
        sf = QFormLayout(self.server_box)
        sf.setContentsMargins(14, 18, 14, 14)
        sf.setSpacing(10)
        self.server_url_input = ltr(QLineEdit(cfg.server_url))
        self.server_url_input.setPlaceholderText("https://")
        self.gmail_input = ltr(QLineEdit(cfg.ai.gmail))
        self.gmail_input.setPlaceholderText("yourname@gmail.com")
        self.server_model = ltr(QComboBox())
        self.server_model.setEditable(True)
        if cfg.ai.server_model:
            self.server_model.setCurrentText(cfg.ai.server_model)
        smrow = QHBoxLayout()
        smrow.addWidget(self.server_model, 1)
        smrow.addWidget(button(t("Refresh models & quota"), slot=self.check_quota))
        self.quota_lbl = QLabel("")
        self.quota_lbl.setWordWrap(True)
        self.quota_lbl.setAlignment(h_align() | Qt.AlignTop)
        sf.addRow(t("Server URL"), self.server_url_input)
        sf.addRow(t("Your Gmail (@gmail.com)"), self.gmail_input)
        sf.addRow(t("Server model"), smrow)
        sf.addRow(t("Quota status"), self.quota_lbl)
        v.addWidget(self.server_box)

        self.custom_box = QGroupBox(t("My own API key"))
        f = QFormLayout(self.custom_box)
        f.setContentsMargins(14, 18, 14, 14)
        f.setSpacing(10)
        self.preset = QComboBox()
        self.preset.currentIndexChanged.connect(self._preset)
        self.base_url = ltr(QLineEdit(cfg.ai.base_url))
        self.api_key = ltr(QLineEdit(""))
        self.api_key.setEchoMode(QLineEdit.Password)
        self._loaded_provider_id = None
        self.model = ltr(QComboBox())
        self.model.setEditable(True)
        self.model.setCurrentText(cfg.ai.model)
        mrow = QHBoxLayout()
        mrow.addWidget(self.model, 1)
        mrow.addWidget(button(t("Fetch models"), slot=self.fetch_models))
        f.addRow(t("Provider"), self.preset)
        f.addRow(t("Base URL"), self.base_url)
        f.addRow(t("API key"), self.api_key)
        f.addRow(t("Model"), mrow)
        v.addWidget(self.custom_box)

        gen = QGroupBox(t("General"))
        gf = QFormLayout(gen)
        gf.setContentsMargins(14, 18, 14, 14)
        gf.setSpacing(10)
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0, 2)
        self.temp.setSingleStep(0.1)
        self.temp.setValue(cfg.ai.temperature)
        self.out_lang = QComboBox()
        for k, name in catalog.languages().items():
            self.out_lang.addItem(name, k)
        self.out_lang.setCurrentIndex(max(0, self.out_lang.findData(cfg.ai.output_language)))
        gf.addRow(t("Output language"), self.out_lang)
        gf.addRow(t("Creativity (temperature)"), self.temp)
        v.addWidget(gen)

        self.r_custom.toggled.connect(self._toggle_ai_mode)
        self._toggle_ai_mode(self.r_custom.isChecked())
        self._sync_catalog_ui()

        self.ai_result = QLabel("")
        self.ai_result.setWordWrap(True)
        self.ai_result.setAlignment(h_align() | Qt.AlignTop)
        v.addWidget(self.ai_result)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button(t("Test AI"), slot=self.test_ai))
        row.addWidget(button(t("Save"), primary=True, slot=self.save_ai))
        v.addLayout(row)
        v.addStretch()
        self.tabs.addTab(_scroll(w), "AI")
        self._ai_index = self.tabs.count() - 1
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, idx: int):
        if (idx == getattr(self, "_ai_index", -1) and cfg.ai.mode == "server"
                and not self.server_model.count() and cfg.server_url):
            self.check_quota()

    def _toggle_ai_mode(self, custom_on: bool):
        self.custom_box.setEnabled(custom_on)
        self.server_box.setEnabled(not custom_on)

    def _selected_provider(self) -> dict:
        provider_id = self.preset.currentData() or cfg.ai.provider_id
        return catalog.resolve_provider(provider_id, self.base_url.text() or cfg.ai.base_url, cfg.ai.api_format)

    def _stored_provider_key(self, provider_id: str) -> str:
        key = secrets.get(f"ai:api_key:{provider_id}")
        if not key and not cfg.ai.provider_id:
            key = secrets.get("ai:api_key")
        return key

    def _load_provider_key(self, provider_id: str) -> None:
        if not provider_id or provider_id == self._loaded_provider_id:
            return
        self._loaded_provider_id = provider_id
        self.api_key.setText(self._stored_provider_key(provider_id))

    def _sync_catalog_ui(self) -> None:
        provider = self._selected_provider()
        selected = provider["id"]
        self.preset.blockSignals(True)
        self.preset.clear()
        for item in catalog.providers():
            self.preset.addItem(item["label"], item["id"])
        self.preset.setCurrentIndex(max(0, self.preset.findData(selected)))
        self.preset.blockSignals(False)
        self._load_provider_key(selected)
        needs_key = bool((provider.get("auth") or {}).get("required", True))
        self.api_key.setEnabled(needs_key)

        current_lang = self.out_lang.currentData() or cfg.ai.output_language
        self.out_lang.blockSignals(True)
        self.out_lang.clear()
        for code, name in catalog.languages().items():
            self.out_lang.addItem(name, code)
        self.out_lang.setCurrentIndex(max(0, self.out_lang.findData(current_lang)))
        self.out_lang.blockSignals(False)

        info = catalog.server_info()
        version = info.get("catalog_version") or catalog.version()
        source = t("server") if info else t("built-in")
        self.catalog_lbl.setText(f"{t('Dynamic AI catalog')}: {version} · {source}")
        if info.get("free_ai_enabled") and not self.server_model.count():
            models = info.get("models") or []
            if models:
                self.server_model.addItems(models)
                default = info.get("default_model")
                if default:
                    self.server_model.setCurrentText(default)

    def _preset(self):
        provider = catalog.provider(self.preset.currentData() or "")
        if provider and provider.get("base_url"):
            self.base_url.setText(provider["base_url"])
        static = (provider or {}).get("models", {}).get("static") or []
        self.model.clear()
        self.model.addItems(static)
        if static:
            self.model.setCurrentText(static[0])
        if provider:
            self._load_provider_key(provider["id"])
            self.api_key.setEnabled(bool((provider.get("auth") or {}).get("required", True)))

    def _make_client(self):
        provider = self._selected_provider()
        return DynamicProviderClient(
            provider,
            self.base_url.text().strip() or provider.get("base_url", ""),
            self.api_key.text(),
            self.model.currentText(),
        )

    def fetch_models(self):
        c = self._make_client()
        run_async(c.list_models,
                  ok=lambda ms: (self.model.clear(), self.model.addItems(ms), notify(f"{len(ms)} " + t("models found"), "ok")),
                  err=show_error)

    def refresh_catalog(self):
        url = normalize_url(self.server_url_input.text())
        self.catalog_lbl.setText(t("Refreshing AI catalog..."))

        def work():
            from ...core.dynamic_loader import dynamic_manager

            dynamic_manager.reload_module("remote_service")
            if url:
                return catalog.refresh_from_server(url)
            return catalog.snapshot()

        def done(_data):
            self._sync_catalog_ui()
            notify(t("AI catalog refreshed"), "ok")

        def failed(exc):
            self.catalog_lbl.setText(f"{t('Dynamic AI catalog')}: {catalog.version()}")
            show_error(exc)

        run_async(work, ok=done, err=failed)

    def save_ai(self) -> bool:
        a = cfg.ai
        a.mode = "server" if self.r_server.isChecked() else "custom"
        gmail_val = self.gmail_input.text().strip().lower()
        server_url = normalize_url(self.server_url_input.text())
        if a.mode == "server":
            import re
            if not server_url:
                notify(t("Server URL is required."), "warn")
                self.server_url_input.setFocus()
                return False
            if not gmail_val or not re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", gmail_val):
                notify(t("A valid Gmail address (@gmail.com) is required to use the free AI tier."), "warn")
                self.gmail_input.setFocus()
                return False
        provider = self._selected_provider()
        base_url = normalize_url(self.base_url.text().strip() or provider.get("base_url", ""))
        if a.mode == "custom" and (not base_url or not self.model.currentText().strip()):
            notify(t("Set the provider Base URL and model first."), "warn")
            (self.base_url if not base_url else self.model).setFocus()
            return False
        needs_key = bool((provider.get("auth") or {}).get("required", True))
        if a.mode == "custom" and needs_key and not self.api_key.text().strip():
            notify(t("This provider requires an API key."), "warn")
            self.api_key.setFocus()
            return False
        if server_url and server_url != cfg.server_url:
            cfg.server_url = server_url
            self.ctx.reset_server_session()
        self.server_url_input.setText(server_url)
        self.base_url.setText(base_url)
        a.gmail = gmail_val
        a.provider_id = provider["id"]
        a.api_format = provider.get("protocol") or "openai"
        a.base_url = base_url
        a.model = self.model.currentText().strip()
        a.server_model = self.server_model.currentText().strip()
        a.temperature = self.temp.value()
        a.output_language = self.out_lang.currentData()
        secrets.set(f"ai:api_key:{provider['id']}", self.api_key.text().strip())
        secrets.delete("ai:api_key")
        cfg.save()
        notify(t("AI settings saved"), "ok")
        return True

    def test_ai(self):
        if not self.save_ai():
            return
        self.ai_result.setText(t("Testing..."))
        run_async(lambda: self.ctx.ai_chat([{"role": "user", "content": "Reply with the single word: OK"}], 20, 0),
                  ok=lambda r: self.ai_result.setText("✅ " + r.text[:200]),
                  err=lambda e: self.ai_result.setText("❌ " + str(e)))

    def check_quota(self):
        server_url = normalize_url(self.server_url_input.text())
        if not server_url:
            notify(t("Server URL is required."), "warn")
            self.server_url_input.setFocus()
            return
        if server_url != cfg.server_url:
            cfg.server_url = server_url
            cfg.save()
            self.ctx.reset_server_session()
        if not cfg.server_url:
            notify(t("Free AI is not available right now."), "warn")
            return

        def work():
            try:
                catalog.refresh_from_server(cfg.server_url)
            except Exception:
                pass
            cfg.ai.gmail = self.gmail_input.text().strip().lower()
            srv = self.ctx.ensure_registered()
            srv.gmail = cfg.ai.gmail
            return srv.config(), srv.quota()

        def done(res):
            conf, q = res
            self._sync_catalog_ui()
            if not conf.get("free_ai_enabled"):
                self.quota_lbl.setText(t("The free AI is currently not available on this server."))
            else:
                models = conf.get("models") or ([conf["model"]] if conf.get("model") else [])
                if models:
                    cur = self.server_model.currentText() or cfg.ai.server_model or conf.get("model", "")
                    self.server_model.clear()
                    self.server_model.addItems(models)
                    idx = self.server_model.findText(cur)
                    if idx >= 0:
                        self.server_model.setCurrentIndex(idx)
                self.quota_lbl.setText(f"{t('Used today')}: {q['used']}/{q['limit']}  |  {t('Remaining')}: {q['remaining']}")

        run_async(work, ok=done, err=lambda e: self.quota_lbl.setText("❌ " + str(e)))


    # ---------------------------------------------------------- privacy ---
    def _privacy_tab(self):
        w = _tab_page()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)
        box = QGroupBox(t("Privacy"))
        bl = QVBoxLayout(box)
        bl.addWidget(label(
            t("WooDesk only sends simple, anonymous statistics to help improve the app: the app version and the operating system. "
              "It never sends passwords, keys, products, posts or customers."),
            muted=True, wrap=True))
        self.cb_tel = QCheckBox(t("Send simple anonymous statistics"))
        self.cb_tel.setChecked(cfg.telemetry)
        bl.addWidget(self.cb_tel)
        self.cb_news = QCheckBox(t("Receive announcements from the project"))
        self.cb_news.setChecked(cfg.announcements)
        bl.addWidget(self.cb_news)
        v.addWidget(box)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button(t("Save"), primary=True, slot=self.save_privacy))
        v.addLayout(row)
        v.addStretch()
        self.tabs.addTab(w, t("Privacy"))

    def save_privacy(self):
        if self.cb_tel.isChecked() != cfg.telemetry:
            self.ctx.set_telemetry(self.cb_tel.isChecked())
        cfg.announcements = self.cb_news.isChecked()
        cfg.save()
        notify(t("Saved"), "ok")

    # ---------------------------------------------------- notifications ---
    def _notifications_tab(self):
        w = _tab_page()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)
        v.addWidget(label(
            t("Stock and order alerts are delivered by a small background helper, not by the main window. "
              "It is enabled only while at least one alert type is selected."),
            muted=True, wrap=True))

        box = QGroupBox(t("Background notifications"))
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 18, 14, 14)
        bl.setSpacing(10)
        self.notify_enabled = QCheckBox(t("Enable background notifications"))
        self.notify_enabled.setChecked(cfg.notifications.enabled)
        self.notify_enabled.toggled.connect(self._toggle_notification_options)
        bl.addWidget(self.notify_enabled)

        self.notify_stock = QCheckBox(t("Out-of-stock alerts (recommended)"))
        self.notify_stock.setChecked(cfg.notifications.out_of_stock)
        self.notify_orders = QCheckBox(t("New order alerts"))
        self.notify_orders.setChecked(cfg.notifications.new_orders)
        self.notify_stock.toggled.connect(lambda _=False: self._refresh_notification_status())
        self.notify_orders.toggled.connect(lambda _=False: self._refresh_notification_status())
        bl.addWidget(self.notify_stock)
        bl.addWidget(self.notify_orders)
        bl.addWidget(label(
            t("New order alerts need WooCommerce read access to orders. Only the order number and total are shown."),
            muted=True, wrap=True))

        interval_row = QHBoxLayout()
        interval_row.addWidget(label(t("Check every")))
        self.notify_interval = QSpinBox()
        self.notify_interval.setRange(30, 900)
        self.notify_interval.setSingleStep(30)
        self.notify_interval.setValue(cfg.notifications.interval_seconds)
        self.notify_interval.setSuffix(" " + t("seconds"))
        interval_row.addWidget(self.notify_interval)
        interval_row.addStretch()
        bl.addLayout(interval_row)

        self.notify_status = QLabel("")
        self.notify_status.setWordWrap(True)
        self.notify_status.setProperty("muted", True)
        bl.addWidget(self.notify_status)
        v.addWidget(box)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button(t("Save"), primary=True, slot=self.save_notifications))
        v.addLayout(row)
        v.addStretch()
        self.tabs.addTab(_scroll(w), t("Notifications"))
        self._toggle_notification_options(self.notify_enabled.isChecked())
        self._refresh_notification_status()

    def _toggle_notification_options(self, enabled: bool):
        for widget in (self.notify_stock, self.notify_orders, self.notify_interval):
            widget.setEnabled(enabled)
        self._refresh_notification_status()

    def _refresh_notification_status(self):
        if not hasattr(self, "notify_status"):
            return
        from ...notifications import autostart

        active = bool(self.notify_enabled.isChecked() and
                      (self.notify_stock.isChecked() or self.notify_orders.isChecked()))
        if not active:
            text = t("Disabled. The background helper is not running.")
        elif autostart.installed():
            text = t("Active. The background helper starts automatically when you sign in.")
        else:
            text = t("Active now, but automatic startup could not be installed.")
        self.notify_status.setText(text)

    def save_notifications(self):
        n = cfg.notifications
        n.enabled = self.notify_enabled.isChecked()
        n.out_of_stock = self.notify_stock.isChecked()
        n.new_orders = self.notify_orders.isChecked()
        n.interval_seconds = self.notify_interval.value()
        cfg.save()
        from ...notifications.controller import sync_background

        sync_background()
        self._refresh_notification_status()
        if n.active:
            notify(t("Notification settings saved"), "ok")
        else:
            notify(t("Notifications disabled. Background helper stopped."), "info")

    # ------------------------------------------------------- appearance ---
    def _appearance_tab(self):
        w = _tab_page()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)
        v.addWidget(label(t("Changes to the theme apply immediately. Language changes need a restart."),
                          muted=True, wrap=True))
        box = QGroupBox(t("Appearance"))
        box.setMaximumWidth(560)
        f = QFormLayout(box)
        f.setContentsMargins(14, 18, 14, 14)
        f.setSpacing(12)
        self.theme = QComboBox()
        self.theme.addItem(t("Follow system"), "system")
        self.theme.addItem(t("Light"), "light")
        self.theme.addItem(t("Dark"), "dark")
        self.theme.setCurrentIndex(max(0, self.theme.findData(cfg.theme)))
        self.theme.currentIndexChanged.connect(self._theme_changed)
        self.lang = QComboBox()
        self.lang.addItem("فارسی", "fa")
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(self.lang.findData(cfg.language))
        self.lang.currentIndexChanged.connect(self._lang_changed)
        f.addRow(t("Theme"), self.theme)
        f.addRow(t("Language"), self.lang)
        row = QHBoxLayout()
        row.addWidget(box)
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        self.tabs.addTab(_scroll(w), t("Appearance"))

    def _theme_changed(self):
        cfg.theme = self.theme.currentData()
        cfg.save()
        self.apply_theme()

    def _sync_theme_combo(self):
        """The top-bar toggle can change the theme too; keep this combo in step."""
        self.theme.blockSignals(True)
        self.theme.setCurrentIndex(max(0, self.theme.findData(cfg.theme)))
        self.theme.blockSignals(False)

    def _lang_changed(self):
        cfg.language = self.lang.currentData()
        cfg.save()
        if confirm(self, t("Restart now to apply the language?")):
            restart_app()
        else:
            notify(t("Restart the app to apply the language."), "info", 5000)

    def _about_tab(self):
        w = _tab_page()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)
        v.addWidget(label(f"WooDesk {__version__}", "h1"))
        v.addWidget(label(t("Open-source WooCommerce & WordPress desktop manager with AI. MIT licence."), wrap=True))
        v.addWidget(label(t(ABOUT_TEXT), wrap=True))
        v.addWidget(label(t(CREDENTIALS_TEXT), muted=True, wrap=True))
        v.addStretch()
        self.tabs.addTab(_scroll(w), t("About"))
