from __future__ import annotations

import json
from pathlib import Path

from ..core.config import data_dir
from .models import AuditResult, SiteAuditResult


def _path() -> Path:
    return data_dir() / "seo_last.json"


def save_last(result: AuditResult | SiteAuditResult) -> None:
    if isinstance(result, SiteAuditResult):
        data = {
            "kind": "site",
            "url": result.url,
            "overall": result.overall,
            "grade": result.grade,
            "fetched_at": result.fetched_at,
            "issues": sum(len(page.issues) for page in result.pages) + len(result.site_issues),
            "pages": result.crawled,
            "sitemap": len(result.sitemap_urls),
        }
    else:
        data = {
            "kind": "page",
            "url": result.final_url or result.url,
            "overall": result.overall,
            "grade": result.grade,
            "fetched_at": result.fetched_at,
            "issues": len(result.issues),
            "pages": 1,
            "sitemap": 0,
        }
    try:
        tmp = _path().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_path())
    except Exception:
        pass


def load_last() -> dict | None:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None
