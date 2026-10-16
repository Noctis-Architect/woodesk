import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.dynamic_loader import DynamicModuleManager, DynamicLoaderError
from app.core.module_updater import ModuleUpdater, compute_sha256


def test_discovery_and_load(tmp_path):
    mgr = DynamicModuleManager(modules_dir=tmp_path)
    module_code = '''
__version__ = "1.0.0"

def calculate(x, y):
    return x + y
'''
    mod_file = tmp_path / "math_service.py"
    mod_file.write_text(module_code, encoding="utf-8")

    discovered = mgr.discover_modules()
    assert "math_service" in discovered

    mod = mgr.load_module("math_service")
    assert getattr(mod, "__version__") == "1.0.0"
    assert mgr.execute("math_service", "calculate", 3, 4) == 7


def test_hot_reload_success(tmp_path):
    mgr = DynamicModuleManager(modules_dir=tmp_path)
    mod_file = tmp_path / "greet_service.py"
    mod_file.write_text('__version__ = "1.0.0"\ndef greet(name): return f"Hello {name}"', encoding="utf-8")

    mgr.load_module("greet_service")
    assert mgr.execute("greet_service", "greet", "Alice") == "Hello Alice"

    # Update on disk
    mod_file.write_text('__version__ = "2.0.0"\ndef greet(name): return f"Welcome {name}!"', encoding="utf-8")
    reloaded = mgr.reload_module("greet_service")
    assert reloaded is True

    assert mgr.execute("greet_service", "greet", "Alice") == "Welcome Alice!"
    assert mgr.get_service("greet_service").__version__ == "2.0.0"


def test_hot_reload_fallback_on_syntax_error(tmp_path):
    mgr = DynamicModuleManager(modules_dir=tmp_path)
    mod_file = tmp_path / "faulty_service.py"
    mod_file.write_text('__version__ = "1.0.0"\ndef run(): return "stable"', encoding="utf-8")

    mgr.load_module("faulty_service")
    assert mgr.execute("faulty_service", "run") == "stable"

    # Corrupt the file with invalid syntax
    mod_file.write_text('__version__ = "2.0.0"\ndef run( broken syntax :::', encoding="utf-8")
    reloaded = mgr.reload_module("faulty_service")
    assert reloaded is False  # reload must fail gracefully

    # Should retain the previous working in-memory instance
    assert mgr.execute("faulty_service", "run") == "stable"
    assert mgr.get_service("faulty_service").__version__ == "1.0.0"


def test_module_updater_atomic_replace_and_sha_verification(tmp_path):
    mgr = DynamicModuleManager(modules_dir=tmp_path)
    service_file = tmp_path / "network_service.py"
    service_file.write_text('__version__ = "1.0.0"\ndef ping(): return "v1"', encoding="utf-8")
    mgr.load_module("network_service")

    v2_content = '__version__ = "2.0.0"\ndef ping(): return "v2_updated"'
    v2_sha = hashlib.sha256(v2_content.encode("utf-8")).hexdigest()

    manifest = {
        "modules": [
            {
                "name": "network_service",
                "version": "2.0.0",
                "url": "http://mock-server/network_service.py",
                "sha256": v2_sha
            }
        ]
    }

    def mock_transport(req: httpx.Request):
        if req.url.path.endswith("manifest.json"):
            return httpx.Response(200, json=manifest)
        if req.url.path.endswith("network_service.py"):
            return httpx.Response(200, text=v2_content)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    updater = ModuleUpdater("http://mock-server/manifest.json", loader=mgr)

    updated = updater.check_and_update(http_client=client)
    assert updated == ["network_service"]

    # Verify atomic update and hot reload
    assert mgr.execute("network_service", "ping") == "v2_updated"
    assert mgr.get_service("network_service").__version__ == "2.0.0"


def test_module_updater_rejects_mismatched_sha(tmp_path):
    mgr = DynamicModuleManager(modules_dir=tmp_path)
    service_file = tmp_path / "secure_service.py"
    service_file.write_text('__version__ = "1.0.0"\ndef verify(): return "original"', encoding="utf-8")
    mgr.load_module("secure_service")

    tampered_content = '__version__ = "2.0.0"\ndef verify(): return "tampered"'
    manifest = {
        "modules": [
            {
                "name": "secure_service",
                "version": "2.0.0",
                "url": "http://mock-server/secure_service.py",
                "sha256": "bad_sha_hash_value_1234567890"  # Invalid hash
            }
        ]
    }

    def mock_transport(req: httpx.Request):
        if req.url.path.endswith("manifest.json"):
            return httpx.Response(200, json=manifest)
        return httpx.Response(200, text=tampered_content)

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    updater = ModuleUpdater("http://mock-server/manifest.json", loader=mgr)

    updated = updater.check_and_update(http_client=client)
    assert updated == []  # Rejected

    # Original version remains untouched
    assert mgr.execute("secure_service", "verify") == "original"
    assert not list(tmp_path.glob("*.tmp*"))  # Temporary files must be cleaned up


def test_default_modules_directory_and_path_traversal_rejection():
    from app.core.dynamic_loader import dynamic_manager, validate_module_name

    # 1. Default directory is strictly 'modules/'
    assert dynamic_manager.modules_dir.name == "modules"
    assert (dynamic_manager.modules_dir / "remote_service.py").exists()

    # 2. Can load remote_service from dedicated modules/ directory
    mod = dynamic_manager.load_module("remote_service")
    assert getattr(mod, "__version__") == "1.0.0"
    payload = dynamic_manager.execute("remote_service", "prepare_ai_payload", [{"role": "user", "content": "hi"}])
    assert payload["model"] == "gpt-4o-mini"

    # 3. Path traversal attacks are rejected immediately
    with pytest.raises(ValueError):
        validate_module_name("../evil")

    with pytest.raises(ValueError):
        dynamic_manager.load_module("../outside")

    with pytest.raises(ValueError):
        dynamic_manager.load_module("sub/dir")

