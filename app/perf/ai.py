from __future__ import annotations

import hashlib
import json
import threading
import time

from ..ai.catalog import catalog
from ..ai.prompts import parse_json_loose, perf_analysis
from ..core.config import cfg, data_dir
from .models import PerfResult

_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 7 * 24 * 3600
_CACHE_VERSION = 1


def payload(result: PerfResult) -> dict:
    metrics = result.metrics
    return {
        "url": result.final_url or result.url,
        "device": result.device,
        "network": result.network,
        "score": result.score,
        "metrics": {
            "ttfb_ms": metrics.ttfb_ms,
            "fcp_ms": metrics.fcp_ms,
            "lcp_ms": metrics.lcp_ms,
            "cls": metrics.cls,
            "tbt_ms": metrics.tbt_ms,
            "inp_lab_ms": metrics.inp_ms,
            "load_ms": metrics.load_ms,
        },
        "requests": result.requests,
        "bytes": result.bytes,
        "third_parties": result.third_parties[:8],
        "images": result.images,
        "lcp_element": result.lcp_element,
        "issues": [
            {"code": issue.code, "severity": issue.severity, "data": issue.data,
             "evidence": issue.evidence[:240]}
            for issue in result.issues[:15]
        ],
        "note": "INP is a synthetic lab approximation; TBT is the primary lab signal.",
    }


def estimate_tokens(result: PerfResult) -> int:
    raw = json.dumps(payload(result), ensure_ascii=False)
    return max(700, int(len(raw) / 3.5) + 550)


def _cache_path():
    return data_dir() / "perf_ai_cache.json"


def _key(result: PerfResult) -> str:
    raw = json.dumps(payload(result), ensure_ascii=False, sort_keys=True)
    settings = (f"{cfg.ai.mode}|{cfg.ai.provider_id}|{cfg.ai.base_url}|{cfg.ai.model}|"
                f"{cfg.ai.server_model}|{cfg.ai.output_language}|{catalog.version()}")
    return hashlib.sha256(f"{_CACHE_VERSION}|{settings}|{raw}".encode("utf-8")).hexdigest()


def _read_cache() -> dict:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(data: dict) -> None:
    try:
        tmp = _cache_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_cache_path())
    except Exception:
        pass


def analyze(ctx, result: PerfResult, *, use_cache: bool = True) -> tuple[dict, bool]:
    key = _key(result)
    if use_cache:
        with _CACHE_LOCK:
            cache = _read_cache()
        entry = cache.get(key)
        if isinstance(entry, dict) and time.time() - float(entry.get("ts", 0)) < _CACHE_TTL:
            data = entry.get("data")
            if isinstance(data, dict):
                return data, True
    reply = ctx.ai_chat(perf_analysis(payload(result), cfg.ai.output_language), max_tokens=850, temperature=0.2)
    data = _normalise(parse_json_loose(reply.text))
    with _CACHE_LOCK:
        cache = _read_cache()
        cache[key] = {"ts": time.time(), "data": data}
        cutoff = time.time() - _CACHE_TTL
        cache = {k: v for k, v in cache.items() if isinstance(v, dict) and float(v.get("ts", 0)) >= cutoff}
        _write_cache(cache)
    return data, False


def _normalise(data: dict) -> dict:
    priorities = []
    for item in data.get("priorities", [])[:8]:
        if isinstance(item, dict):
            priorities.append({
                "issue": str(item.get("issue") or "")[:300],
                "impact": str(item.get("impact") or "")[:400],
                "action": str(item.get("action") or "")[:500],
            })
    return {
        "summary": str(data.get("summary") or "")[:1500],
        "priorities": priorities,
        "quick_wins": [str(item)[:400] for item in data.get("quick_wins", [])[:8]],
    }
