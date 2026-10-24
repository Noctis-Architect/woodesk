from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SKIP = object()

CATEGORY_WEIGHTS = {
    "technical": 25,
    "meta": 15,
    "content": 20,
    "media": 10,
    "links": 15,
    "structured": 10,
    "mobile": 5,
}
CATEGORY_ORDER = list(CATEGORY_WEIGHTS)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEVERITY_LABELS = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "info": "Info",
}


@dataclass
class Issue:
    code: str
    category: str
    severity: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: str = ""
    page: str = ""


@dataclass
class ImageInfo:
    src: str = ""
    alt: str = ""
    alt_present: bool = False
    width: str = ""
    height: str = ""
    loading: str = ""
    srcset: str = ""
    displayed_width: int | None = None
    displayed_height: int | None = None
    natural_width: int | None = None
    natural_height: int | None = None


@dataclass
class LinkInfo:
    href: str = ""
    text: str = ""
    rel: str = ""
    internal: bool = True
    status: int | None = None
    error: str = ""


@dataclass
class PageFacts:
    url: str = ""
    final_url: str = ""
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    html: str = ""
    rendered: bool = False
    elapsed_ms: int = 0
    title: str = ""
    meta_description: str = ""
    meta_robots: str = ""
    x_robots: str = ""
    canonical: str = ""
    lang: str = ""
    charset: str = ""
    viewport: str = ""
    h1: list[str] = field(default_factory=list)
    headings: list[tuple[str, str]] = field(default_factory=list)
    text: str = ""
    word_count: int = 0
    images: list[ImageInfo] = field(default_factory=list)
    links: list[LinkInfo] = field(default_factory=list)
    jsonld: list[Any] = field(default_factory=list)
    jsonld_raw: list[str] = field(default_factory=list)
    jsonld_invalid: list[str] = field(default_factory=list)
    og: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    hreflang: list[dict[str, str]] = field(default_factory=list)
    robots_txt: str = ""
    robots_allowed: bool | None = None
    sitemap_urls: list[str] = field(default_factory=list)
    sitemap_found: bool = False
    mixed_content: list[str] = field(default_factory=list)
    mobile_overflow: bool | None = None
    small_text_count: int = 0
    small_tap_count: int = 0
    html_bytes: int = 0

    @property
    def host(self) -> str:
        from urllib.parse import urlparse

        return (urlparse(self.final_url or self.url).hostname or "").lower()

    @property
    def noindex(self) -> bool:
        blob = f"{self.meta_robots} {self.x_robots}".lower()
        return "noindex" in blob or "none" in blob

    @property
    def jsonld_types(self) -> list[str]:
        return [str(t) for item in self.jsonld for t in _jsonld_types(item)]


def _jsonld_types(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return []
    kind = item.get("@type")
    if isinstance(kind, str):
        return [kind]
    if isinstance(kind, list):
        return [str(k) for k in kind]
    return []


@dataclass
class CategoryScore:
    category: str
    score: int
    passed: int
    failed: int
    skipped: int
    total: int


@dataclass
class AuditOptions:
    keyword: str = ""
    rendered: bool = True
    check_links: bool = True
    max_links: int = 8
    timeout: float = 20.0
    scope: str = "page"  # page | content
    max_pages: int = 20
    delay_ms: int = 250


@dataclass
class AuditResult:
    url: str
    final_url: str
    status: int
    rendered: bool
    fetched_at: str
    overall: int
    grade: str
    categories: list[CategoryScore]
    issues: list[Issue]
    facts: PageFacts
    duration_ms: int = 0
    note: str = ""
    ai: dict[str, Any] | None = None
    ai_cached: bool = False


@dataclass
class SiteAuditResult:
    url: str
    fetched_at: str
    overall: int
    grade: str
    pages: list[AuditResult]
    site_issues: list[Issue]
    sitemap_urls: list[str] = field(default_factory=list)
    crawled: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)
    ai: dict[str, Any] | None = None
    ai_cached: bool = False


def grade_for(score: int) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    if score >= 50:
        return "E"
    return "F"
