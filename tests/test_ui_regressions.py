import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("WOODESK_HOME", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.core import secrets
from app.core.config import cfg
from app.core.context import AppContext
from app.ui.main_window import PageStack
from app.ui.pages.products import ProductsPage
from app.ui.widgets import SearchBox


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeContext:
    def has_site(self):
        return True

    def woo(self):
        return self


def test_search_enter_emits_only_once(app):
    search = SearchBox()
    search.setText("chair")
    emitted = []
    search.changed.connect(emitted.append)

    QTest.keyClick(search, Qt.Key_Return)
    QTest.qWait(450)

    assert emitted == ["chair"]


def test_products_ignore_response_after_site_change(app, monkeypatch):
    pending = {}

    def capture(fn, *args, **kwargs):
        pending.update(kwargs)

    monkeypatch.setattr("app.ui.pages.products.run_async", capture)
    page = ProductsPage(FakeContext())
    page.load(1)
    page.site_changed()

    pending["ok"](([], 0, 1))

    assert page.table.rowCount() == 0
    assert page.rows == []


def test_page_transition_finishes_without_retaining_graphics_effect(app):
    stack = PageStack()
    first, second = QWidget(), QWidget()
    stack.addWidget(first)
    stack.addWidget(second)
    stack.show()

    stack.show_page(second)
    assert stack.currentWidget() is second
    QTest.qWait(250)

    assert second.graphicsEffect() is None
    stack.close()


def test_context_uses_provider_specific_key(app):
    original = (cfg.ai.mode, cfg.ai.provider_id, cfg.ai.base_url, cfg.ai.model, cfg.ai.api_format)
    try:
        cfg.ai.mode = "custom"
        cfg.ai.provider_id = "openai"
        cfg.ai.base_url = "https://api.openai.com/v1"
        cfg.ai.model = "gpt-test"
        cfg.ai.api_format = "openai"
        secrets.set("ai:api_key", "legacy-key")
        secrets.set("ai:api_key:openai", "openai-key")
        secrets.set("ai:api_key:anthropic", "anthropic-key")

        assert AppContext().ai_client().key == "openai-key"

        cfg.ai.provider_id = "anthropic"
        cfg.ai.api_format = "anthropic"
        assert AppContext().ai_client().key == "anthropic-key"
    finally:
        (cfg.ai.mode, cfg.ai.provider_id, cfg.ai.base_url, cfg.ai.model, cfg.ai.api_format) = original
        secrets.delete("ai:api_key")
        secrets.delete("ai:api_key:openai")
        secrets.delete("ai:api_key:anthropic")
