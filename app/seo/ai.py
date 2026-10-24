from __future__ import annotations

import hashlib
import json
import threading
import time
from ..ai.catalog import catalog
from ..ai.prompts import parse_json_loose, seo_audit
from ..core.config import cfg, data_dir
from .messages import issue_text
from .models import AuditResult, SiteAuditResult

_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 7 * 24 * 3600
_CACHE_VERSION = 1


def _payload(result: AuditResult) -> dict:
    lang = cfg.ai.output_language
    issues = []
    for issue in result.issues[:20]:
        title, _detail, _fix = issue_text(issue, lang)
        issues.append({
            "code": issue.code,
            "severity": issue.severity,
            "category": issue.category,
            "title": title,
            "evidence": issue.evidence[:220],
        })
    facts = result.facts
    return {
        "url": result.final_url or result.url,
        "status": result.status,
        "score": result.overall,
        "grade": result.grade,
        "categories": [{"category": item.category, "score": item.score,
                        "passed": item.passed, "failed": item.failed} for item in result.categories],
        "issues": issues,
        "page": {
            "title": facts.title[:180],
            "meta_description": facts.meta_description[:220],
            "h1": facts.h1[:5],
            "word_count": facts.word_count,
            "images": len(facts.images),
            "internal_links": sum(1 for link in facts.links if link.internal),
            "jsonld_types": facts.jsonld_types[:8],
            "rendered": result.rendered,
        },
    }


def estimate_tokens(result: AuditResult) -> int:
    raw = json.dumps(_payload(result), ensure_ascii=False)
    return max(900, int(len(raw) / 3.5) + 650)


def _cache_path() -> Path:
    return data_dir() / "seo_ai_cache.json"


def _read_cache() -> dict:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(data: dict) -> None:
    path = _cache_path()
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def _key(result: AuditResult) -> str:
    raw = json.dumps(_payload(result), ensure_ascii=False, sort_keys=True)
    settings = (f"{cfg.ai.mode}|{cfg.ai.provider_id}|{cfg.ai.base_url}|{cfg.ai.model}|"
                f"{cfg.ai.server_model}|{cfg.ai.output_language}|{catalog.version()}")
    return hashlib.sha256(f"{_CACHE_VERSION}|{settings}|{raw}".encode("utf-8")).hexdigest()


def analyze(ctx, result: AuditResult, *, use_cache: bool = True) -> tuple[dict, bool]:
    """Blocking. Returns (analysis, from_cache)."""
    key = _key(result)
    if use_cache:
        with _CACHE_LOCK:
            cache = _read_cache()
        entry = cache.get(key)
        if isinstance(entry, dict) and time.time() - float(entry.get("ts", 0)) < _CACHE_TTL:
            data = entry.get("data")
            if isinstance(data, dict):
                return data, True

    reply = ctx.ai_chat(seo_audit(_payload(result), cfg.ai.output_language), max_tokens=900, temperature=0.2)
    data = parse_json_loose(reply.text)
    data = _normalise(data)
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
                "issue": str(item.get("issue") or item.get("code") or "")[:300],
                "impact": str(item.get("impact") or "")[:400],
                "action": str(item.get("action") or "")[:500],
            })
        elif item:
            priorities.append({"issue": str(item)[:300], "impact": "", "action": ""})
    quick = [str(item)[:400] for item in data.get("quick_wins", [])[:8]]
    meta = data.get("suggested_meta") or data.get("content_suggestions") or {}
    if not isinstance(meta, dict):
        meta = {}
    return {
        "summary": str(data.get("summary") or "")[:1500],
        "priorities": priorities,
        "quick_wins": quick,
        "suggested_meta": {
            "title": str(meta.get("title") or "")[:200],
            "description": str(meta.get("description") or "")[:400],
        },
    }


def site_payload(result: SiteAuditResult) -> dict:
    worst = sorted(result.pages, key=lambda page: page.overall)[:8]
    return {
        "url": result.url,
        "score": result.overall,
        "crawled": result.crawled,
        "site_issues": [{"code": issue.code, "severity": issue.severity,
                         "evidence": issue.evidence[:300]} for issue in result.site_issues],
        "worst_pages": [{
            "url": page.final_url or page.url,
            "score": page.overall,
            "issues": [{"code": issue.code, "severity": issue.severity} for issue in page.issues[:8]],
        } for page in worst],
    }


def estimate_site_tokens(result: SiteAuditResult) -> int:
    return max(1200, int(len(json.dumps(site_payload(result), ensure_ascii=False)) / 3.5) + 700)


def analyze_site(ctx, result: SiteAuditResult) -> tuple[dict, bool]:
    """Site-level analysis based on the worst pages, not the full HTML."""
    reply = ctx.ai_chat(seo_audit(site_payload(result), cfg.ai.output_language), max_tokens=1000, temperature=0.2)
    return _normalise(parse_json_loose(reply.text)), False


def clear_cache() -> None:
    try:
        _cache_path().unlink(missing_ok=True)
    except Exception:
        pass
