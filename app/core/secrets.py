"""Secret storage: Windows Credential Manager / macOS Keychain / Secret Service via `keyring`.

If no keyring backend is available we fall back to a user-only file. That fallback is
NOT encrypted; the UI shows a warning when it is in use.
"""
from __future__ import annotations

import base64
import json
import os

from .config import data_dir

SERVICE = "WooDesk"
_backend_ok: bool | None = None
_mem: dict[str, str] = {}  # keyring/Credential Manager calls are slow; read each secret from the OS once


def _keyring():
    global _backend_ok
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        if isinstance(keyring.get_keyring(), FailKeyring):
            _backend_ok = False
            return None
        _backend_ok = True
        return keyring
    except Exception:
        _backend_ok = False
        return None


def using_secure_store() -> bool:
    if _backend_ok is None:
        _keyring()
    return bool(_backend_ok)


def _file():
    return data_dir() / "secrets.json"


def _read_file() -> dict:
    p = _file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_file(d: dict) -> None:
    p = _file()
    p.write_text(json.dumps(d), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass


def get(name: str) -> str:
    if name in _mem:
        return _mem[name]
    v = _get(name)
    _mem[name] = v
    return v


def _get(name: str) -> str:
    kr = _keyring()
    if kr:
        try:
            v = kr.get_password(SERVICE, name)
            if v is not None:
                return v
        except Exception:
            pass
    v = _read_file().get(name, "")
    return base64.b64decode(v).decode() if v else ""


def set(name: str, value: str) -> None:  # noqa: A001
    _mem.pop(name, None)
    if not value:
        delete(name)
        return
    kr = _keyring()
    if kr:
        try:
            kr.set_password(SERVICE, name, value)
            return
        except Exception:
            pass
    d = _read_file()
    d[name] = base64.b64encode(value.encode()).decode()
    _write_file(d)


def delete(name: str) -> None:
    _mem.pop(name, None)
    kr = _keyring()
    if kr:
        try:
            kr.delete_password(SERVICE, name)
        except Exception:
            pass
    d = _read_file()
    if name in d:
        del d[name]
        _write_file(d)
