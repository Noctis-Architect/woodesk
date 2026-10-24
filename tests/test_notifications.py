import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["WOODESK_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

from app.core.config import NotificationSettings, cfg
from app.notifications import autostart, controller, logic
from app.notifications.engine import detect_orders, detect_stock
from app.notifications.state import empty_state, load_state, mark_all_inactive, save_state, site_state
from app.notifications.worker import NotificationWorker


def _product(pid, name):
    return {"id": pid, "name": name, "sku": "", "quantity": 0, "url": "", "stock_status": "outofstock"}


def _order(oid, number):
    return {"id": oid, "number": number, "status": "processing", "total": "100", "currency": "USD", "created": ""}


def test_notification_defaults_are_stock_only():
    settings = NotificationSettings()
    assert settings.active is True
    assert settings.out_of_stock is True
    assert settings.new_orders is False
    assert NotificationSettings(out_of_stock=False, new_orders=False).active is False


def test_stock_detection_baselines_then_reports_new_items():
    state = {}
    events = detect_stock([_product(1, "Chair")], state, True, False, 100)
    assert events == []

    events = detect_stock([_product(1, "Chair"), _product(2, "Table")], state, True, True, 200)
    assert len(events) == 1
    assert events[0]["type"] == "out_of_stock" and events[0]["count"] == 1
    assert events[0]["products"][0]["name"] == "Table"

    events = detect_stock([_product(1, "Chair")], state, True, True, 300)
    assert events == []


def test_order_detection_deduplicates_and_initializes_baseline():
    state = {}
    events = detect_orders([_order(3, "1003")], state, True, False, 100)
    assert events == []

    events = detect_orders([_order(4, "1004"), _order(3, "1003")], state, True, True, 200)
    assert len(events) == 1 and events[0]["orders"][0]["id"] == 4

    events = detect_orders([_order(4, "1004"), _order(3, "1003")], state, True, True, 300)
    assert events == []


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_worker_site_checks_respect_enabled_types(app):
    class Site:
        id = "site-1"
        name = "Shop"

    class Client:
        def __init__(self):
            self.products = [_product(1, "Chair")]
            self.orders = []

        def all_pages(self, path, params, max_pages=20):
            return list(self.products)

        def page(self, path, params):
            return list(self.orders), len(self.orders), 1

    worker = NotificationWorker(app)
    worker.state = empty_state()
    client, site = Client(), Site()
    stock_only = NotificationSettings(out_of_stock=True, new_orders=False)

    assert worker._check_site(client, site, stock_only, 100) == []
    client.products.append(_product(2, "Table"))
    events = worker._check_site(client, site, stock_only, 200)
    assert len(events) == 1 and events[0]["type"] == "out_of_stock"
    assert events[0]["site_name"] == "Shop"
    assert worker.state["sites"]["site-1"]["active_types"] == ["out_of_stock"]

    orders_only = NotificationSettings(out_of_stock=False, new_orders=True)
    client.orders = [_order(10, "1010")]
    assert worker._check_site(client, site, orders_only, 300) == []
    client.orders.insert(0, _order(11, "1011"))
    events = worker._check_site(client, site, orders_only, 400)
    assert len(events) == 1 and events[0]["type"] == "new_orders"
    assert worker.state["sites"]["site-1"]["active_types"] == ["new_orders"]


def test_state_roundtrip_and_inactive_reset(tmp_path):
    path = tmp_path / "state.json"
    state = empty_state()
    current = site_state(state, "site-1")
    current["active_types"] = ["out_of_stock"]
    current["stock"] = {"ids": [1, 2], "initialized": True}
    save_state(state, path)
    loaded = load_state(path)
    assert loaded["sites"]["site-1"]["stock"]["ids"] == [1, 2]
    mark_all_inactive(loaded)
    assert loaded["sites"]["site-1"]["active_types"] == []


def test_dynamic_notification_formatter_and_policy():
    settings = NotificationSettings(out_of_stock=True, new_orders=False)
    stock = {"type": "out_of_stock", "count": 1, "site_name": "Shop", "products": [{"name": "Chair"}]}
    orders = {"type": "new_orders", "count": 1, "site_name": "Shop",
              "orders": [{"number": "42", "total": "10", "currency": "USD"}]}
    assert logic.should_notify(stock, settings) is True
    assert logic.should_notify(orders, settings) is False

    fa = logic.format_notification(stock, "fa")
    en = logic.format_notification(orders, "en")
    assert "Chair" in fa["body"] and "ناموجود" in fa["body"]
    assert "Order #42" in en["body"] and "10 USD" in en["body"]


def test_linux_autostart_entry_installs_and_removes(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    command = autostart.worker_command()
    assert command[0] == sys.executable
    assert command[-1] == "--notification-worker"
    assert autostart.install() is True
    path = tmp_path / "autostart" / "woodesk-notifications.desktop"
    content = path.read_text(encoding="utf-8")
    assert "--notification-worker" in content
    assert "Exec=" in content and "Terminal=false" in content
    assert autostart.installed() is True
    assert autostart.remove() is True
    assert autostart.installed() is False


def test_disabling_all_notifications_removes_background_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("WOODESK_HOME", str(tmp_path))
    calls = []
    monkeypatch.setattr(autostart, "install", lambda: calls.append("install") or True)
    monkeypatch.setattr(autostart, "remove", lambda: calls.append("remove") or True)
    original = (cfg.notifications.enabled, cfg.notifications.out_of_stock,
                cfg.notifications.new_orders, cfg.notifications.interval_seconds)
    try:
        cfg.notifications.enabled = True
        cfg.notifications.out_of_stock = True
        cfg.notifications.new_orders = False
        assert controller.sync_background(spawn=False) is True
        assert calls == ["install"]
        assert not controller.stop_path().exists()

        cfg.notifications.enabled = False
        assert controller.sync_background(spawn=False) is False
        assert calls[-1] == "remove"
        assert controller.stop_path().exists()
    finally:
        (cfg.notifications.enabled, cfg.notifications.out_of_stock,
         cfg.notifications.new_orders, cfg.notifications.interval_seconds) = original


def test_background_worker_lock_is_single_instance(tmp_path, monkeypatch):
    monkeypatch.setenv("WOODESK_HOME", str(tmp_path))
    lock = QLockFile(str(controller.lock_path()))
    assert lock.tryLock(100)
    assert controller.worker_running() is True
    lock.unlock()
    assert controller.worker_running() is False
