from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from ..core.config import data_dir

_MAX_IDS = 1000


def empty_state() -> dict:
    return {"version": 1, "sites": {}}


def load_state(path: Path | None = None) -> dict:
    path = path or (data_dir() / "notification_state.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("sites"), dict):
            return raw
    except Exception:
        pass
    return empty_state()


def save_state(state: dict, path: Path | None = None) -> None:
    path = path or (data_dir() / "notification_state.json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def site_state(state: dict, site_id: str) -> dict:
    sites = state.setdefault("sites", {})
    current = sites.setdefault(site_id, {})
    current.setdefault("active_types", [])
    return current


def mark_all_inactive(state: dict) -> None:
    for current in state.get("sites", {}).values():
        if isinstance(current, dict):
            current["active_types"] = []


def cap_ids(ids) -> list[int]:
    result = []
    seen = set()
    for item in ids:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result[-_MAX_IDS:]


def mark_inactive() -> None:
    path = data_dir() / "notification_state.json"
    state = load_state(path)
    mark_all_inactive(state)
    state["inactive_since"] = int(time.time())
    save_state(state, path)
