from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QRadioButton, QTabWidget,
                               QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from ... import __version__
from ...ai.client import PRESETS, AnthropicClient, OpenAICompatClient
from ...ai.prompts import LANG_NAMES
from ...api.http import domain_of, normalize_url
from ...api.woo import WooClient
from ...api.wp import WPClient
from ...core import secrets
from ...core.config import Site, cfg, new_id
from ...core.context import secret_key
from ...core.i18n import t
from ...core.workers import run_async
from ..widgets import PageHeader, button, confirm, label, ltr, notify, restart_app, show_error


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


class SiteDialog(QDialog):
    def __init__(self, ctx, site: Site | None = None, parent=None):
        super().__init__(parent)
        self.ctx, self.site = ctx, site
        self.setWindowTitle(t("Edit site") if site else t("Add site"))
        self.resize(560, 0)
        lay = QVBoxLayout(self)
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
        lay.addWidget(self.result)
        row = QHBoxLayout()
        self.test_btn = button(t("Test connection"), slot=self.test)
        row.addWidget(self.test_btn)
        row.addStretch()
        row.addWidget(button(t("Cancel"), slot=self.reject))
        row.addWidget(button(t("Save"), primary=True, slot=self.save))
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
        lay.setContentsMargins(24, 20, 24, 16)
        lay.addWidget(PageHeader(t("Settings")))
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self._sites_tab()
        self._ai_tab()
        self._privacy_tab()
        self._appearance_tab()
        self._about_tab()

    def on_show(self):
        self._refresh_sites()
        self._sync_theme_combo()

    def site_changed(self):
        self._refresh_sites()

    # ------------------------------------------------------------ sites ---
    def _sites_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.site_list = QListWidget()
        v.addWidget(self.site_list)
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
        w = QWidget()
        v = QVBoxLayout(w)
        self.r_custom = QRadioButton(t("Use my own API key (any provider)"))
        self.r_server = QRadioButton(t("Use the free AI from the project server (limited daily quota)"))
        (self.r_server if cfg.ai.mode == "server" else self.r_custom).setChecked(True)
        v.addWidget(self.r_custom)

        self.custom_box = QGroupBox()
        f = QFormLayout(self.custom_box)
        self.preset = QComboBox()
        for label_, fmt, url in PRESETS:
            self.preset.addItem(label_, (fmt, url))
        self.preset.currentIndexChanged.connect(self._preset)
        self.base_url = ltr(QLineEdit(cfg.ai.base_url))
        self.api_key = ltr(QLineEdit(secrets.get("ai:api_key")))
        self.api_key.setEchoMode(QLineEdit.Password)
        self.fmt = QComboBox()
        self.fmt.addItem("OpenAI-compatible", "openai")
        self.fmt.addItem("Anthropic", "anthropic")
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(cfg.ai.api_format)))
        self.model = ltr(QComboBox())
        self.model.setEditable(True)
        self.model.setCurrentText(cfg.ai.model)
        mrow = QHBoxLayout()
        mrow.addWidget(self.model, 1)
        mrow.addWidget(button(t("Fetch models"), slot=self.fetch_models))
        f.addRow(t("Provider"), self.preset)
        f.addRow(t("API format"), self.fmt)
        f.addRow("Base URL", self.base_url)
        f.addRow("API key", self.api_key)
        f.addRow(t("Model"), mrow)
        v.addWidget(self.custom_box)

        v.addWidget(self.r_server)
        self.server_box = QGroupBox(t("Server free AI settings"))
        sf = QFormLayout(self.server_box)
        self.gmail_input = ltr(QLineEdit(cfg.ai.gmail))
        self.gmail_input.setPlaceholderText("yourname@gmail.com")
        sf.addRow(t("Your Gmail (@gmail.com)"), self.gmail_input)
        self.server_model = ltr(QComboBox())
        self.server_model.setEditable(True)
        if cfg.ai.server_model:
            self.server_model.setCurrentText(cfg.ai.server_model)
        smrow = QHBoxLayout()
        smrow.addWidget(self.server_model, 1)
        smrow.addWidget(button(t("Refresh models & quota"), slot=self.check_quota))
        sf.addRow(t("Server model"), smrow)
        self.quota_lbl = QLabel("")
        self.quota_lbl.setWordWrap(True)
        sf.addRow(t("Quota status"), self.quota_lbl)
        v.addWidget(self.server_box)

        self.r_custom.toggled.connect(self._toggle_ai_mode)
        self._toggle_ai_mode(self.r_custom.isChecked())

        f2 = QFormLayout()
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0, 2)
        self.temp.setSingleStep(0.1)
        self.temp.setValue(cfg.ai.temperature)
        self.out_lang = QComboBox()
        for k, name in LANG_NAMES.items():
            self.out_lang.addItem(name, k)
        self.out_lang.setCurrentIndex(max(0, self.out_lang.findData(cfg.ai.output_language)))
        f2.addRow(t("Output language"), self.out_lang)
        f2.addRow(t("Creativity (temperature)"), self.temp)
        v.addLayout(f2)

        self.ai_result = QLabel("")
        self.ai_result.setWordWrap(True)
        v.addWidget(self.ai_result)
        row = QHBoxLayout()
        row.addWidget(button(t("Test AI"), slot=self.test_ai))
        row.addStretch()
        row.addWidget(button(t("Save"), primary=True, slot=self.save_ai))
        v.addLayout(row)
        v.addStretch()
        self.tabs.addTab(w, "AI")

    def _toggle_ai_mode(self, custom_on: bool):
        self.custom_box.setEnabled(custom_on)
        self.server_box.setEnabled(not custom_on)
        if not custom_on and not self.server_model.count() and cfg.server_url:
            self.check_quota()

    def _preset(self):
        fmt, url = self.preset.currentData()
        if url:
            self.base_url.setText(url)
        self.fmt.setCurrentIndex(self.fmt.findData(fmt))

    def _make_client(self):
        cls = AnthropicClient if self.fmt.currentData() == "anthropic" else OpenAICompatClient
        return cls(self.base_url.text(), self.api_key.text(), self.model.currentText())

    def fetch_models(self):
        c = self._make_client()
        run_async(c.list_models, ok=lambda ms: (self.model.clear(), self.model.addItems(ms), notify(f"{len(ms)} " + t("models found"), "ok")), err=show_error)

    def save_ai(self) -> bool:
        a = cfg.ai
        a.mode = "server" if self.r_server.isChecked() else "custom"
        gmail_val = self.gmail_input.text().strip().lower()
        if a.mode == "server":
            import re
            if not gmail_val or not re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", gmail_val):
                notify(t("A valid Gmail address (@gmail.com) is required to use the free AI tier."), "warn")
                self.gmail_input.setFocus()
                return False
        a.gmail = gmail_val
        a.api_format = self.fmt.currentData() or "openai"
        a.base_url = self.base_url.text().strip()
        a.model = self.model.currentText().strip()
        a.server_model = self.server_model.currentText().strip()
        a.temperature = self.temp.value()
        a.output_language = self.out_lang.currentData()
        secrets.set("ai:api_key", self.api_key.text().strip())
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
        if not cfg.server_url:
            notify(t("Free AI is not available right now."), "warn")
            return

        def work():
            cfg.ai.gmail = self.gmail_input.text().strip().lower()
            srv = self.ctx.ensure_registered()
            srv.gmail = cfg.ai.gmail
            return srv.config(), srv.quota()

        def done(res):
            conf, q = res
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
        w = QWidget()
        v = QVBoxLayout(w)
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

    # ------------------------------------------------------- appearance ---
    def _appearance_tab(self):
        w = QWidget()
        f = QFormLayout(w)
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
        self.tabs.addTab(w, t("Appearance"))

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
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(label(f"WooDesk {__version__}", "h1"))
        v.addWidget(label(t("Open-source WooCommerce & WordPress desktop manager with AI. MIT licence."), wrap=True))
        v.addWidget(label(t(ABOUT_TEXT), wrap=True))
        v.addWidget(label(t(CREDENTIALS_TEXT), muted=True, wrap=True))
        v.addStretch()
        self.tabs.addTab(w, t("About"))
