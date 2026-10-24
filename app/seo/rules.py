from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

from .extract import is_generic_anchor
from .models import SKIP, AuditOptions, Issue, PageFacts


@dataclass
class Failure:
    data: dict = field(default_factory=dict)
    evidence: str = ""


@dataclass
class RuleContext:
    options: AuditOptions
    link_status: dict[str, tuple[int | None, str]] = field(default_factory=dict)
    links_checked: bool = False
    robots_checked: bool = False
    sitemap_checked: bool = False


@dataclass(frozen=True)
class Rule:
    code: str
    category: str
    severity: str
    weight: int
    check: Callable[[PageFacts, RuleContext], Failure | None | object]


def _same_url(left: str, right: str) -> bool:
    try:
        a, b = urlsplit(left), urlsplit(right)
    except ValueError:
        return left.rstrip("/") == right.rstrip("/")
    return (
        a.scheme.lower() == b.scheme.lower()
        and (a.hostname or "").lower() == (b.hostname or "").lower()
        and a.path.rstrip("/") == b.path.rstrip("/")
        and a.query == b.query
    )


def _jsonld_nodes(facts: PageFacts) -> list[dict]:
    return [node for node in facts.jsonld if isinstance(node, dict)]


def _has_type(nodes: list[dict], name: str) -> bool:
    for node in nodes:
        kind = node.get("@type")
        values = kind if isinstance(kind, list) else [kind]
        if name in [str(v) for v in values]:
            return True
    return False


def _check_https(facts: PageFacts, _ctx: RuleContext):
    if urlsplit(facts.final_url or facts.url).scheme != "https":
        return Failure(evidence=facts.final_url or facts.url)


def _check_status(facts: PageFacts, _ctx: RuleContext):
    if facts.status == 0 or facts.status >= 400:
        return Failure({"status": facts.status or "no response"}, f"HTTP {facts.status or '-'}")


def _check_redirect(facts: PageFacts, _ctx: RuleContext):
    if facts.final_url and not _same_url(facts.url, facts.final_url):
        return Failure({"final_url": facts.final_url}, f"{facts.url} -> {facts.final_url}")


def _check_noindex(facts: PageFacts, _ctx: RuleContext):
    if facts.noindex:
        return Failure(evidence=(facts.meta_robots or facts.x_robots)[:300])


def _check_canonical_missing(facts: PageFacts, _ctx: RuleContext):
    if facts.status < 400 and not facts.canonical:
        return Failure()


def _check_canonical_mismatch(facts: PageFacts, _ctx: RuleContext):
    if facts.canonical and facts.final_url and not _same_url(facts.canonical, facts.final_url):
        return Failure({"canonical": facts.canonical, "final_url": facts.final_url},
                       f"canonical: {facts.canonical}")


def _check_viewport(facts: PageFacts, _ctx: RuleContext):
    if not facts.viewport:
        return Failure()


def _check_lang(facts: PageFacts, _ctx: RuleContext):
    if not facts.lang:
        return Failure()


def _check_charset(facts: PageFacts, _ctx: RuleContext):
    if not facts.charset:
        return Failure()


def _check_sitemap(facts: PageFacts, ctx: RuleContext):
    if ctx.sitemap_checked and not facts.sitemap_found:
        return Failure()


def _check_robots(facts: PageFacts, ctx: RuleContext):
    if ctx.robots_checked and facts.robots_allowed is False:
        return Failure(evidence=facts.url)


def _check_mixed_content(facts: PageFacts, _ctx: RuleContext):
    if facts.mixed_content:
        return Failure({"count": len(facts.mixed_content)}, "\n".join(facts.mixed_content[:5]))


def _check_title_missing(facts: PageFacts, _ctx: RuleContext):
    if not facts.title:
        return Failure()


def _check_title_length(facts: PageFacts, _ctx: RuleContext):
    if facts.title and not 30 <= len(facts.title) <= 60:
        return Failure({"length": len(facts.title)}, facts.title[:160])


def _check_description_missing(facts: PageFacts, _ctx: RuleContext):
    if not facts.meta_description:
        return Failure()


def _check_description_length(facts: PageFacts, _ctx: RuleContext):
    if facts.meta_description and not 70 <= len(facts.meta_description) <= 155:
        return Failure({"length": len(facts.meta_description)}, facts.meta_description[:200])


def _check_og(facts: PageFacts, _ctx: RuleContext):
    missing = [key for key in ("og:title", "og:description", "og:image") if not facts.og.get(key)]
    if missing:
        return Failure({"missing": ", ".join(missing)})


def _check_twitter(facts: PageFacts, _ctx: RuleContext):
    missing = [key for key in ("twitter:card", "twitter:title", "twitter:description") if not facts.twitter.get(key)]
    if missing:
        return Failure({"missing": ", ".join(missing)})


def _check_h1_missing(facts: PageFacts, _ctx: RuleContext):
    if not facts.h1:
        return Failure()


def _check_h1_multiple(facts: PageFacts, _ctx: RuleContext):
    if len(facts.h1) > 1:
        return Failure({"count": len(facts.h1)}, " | ".join(facts.h1[:4])[:300])


def _check_thin(facts: PageFacts, _ctx: RuleContext):
    if facts.word_count < 300:
        return Failure({"words": facts.word_count})


def _keyword(facts: PageFacts, keyword: str) -> str:
    return keyword.strip().lower()


def _check_keyword_missing(facts: PageFacts, ctx: RuleContext):
    keyword = _keyword(facts, ctx.options.keyword)
    if not keyword:
        return SKIP
    if keyword not in facts.text.lower():
        return Failure({"keyword": ctx.options.keyword.strip()})


def _check_title_keyword(facts: PageFacts, ctx: RuleContext):
    keyword = _keyword(facts, ctx.options.keyword)
    if not keyword:
        return SKIP
    if keyword not in facts.title.lower():
        return Failure({"keyword": ctx.options.keyword.strip()}, facts.title[:160])


def _check_description_keyword(facts: PageFacts, ctx: RuleContext):
    keyword = _keyword(facts, ctx.options.keyword)
    if not keyword:
        return SKIP
    if keyword not in facts.meta_description.lower():
        return Failure({"keyword": ctx.options.keyword.strip()}, facts.meta_description[:200])


def _check_keyword_density(facts: PageFacts, ctx: RuleContext):
    keyword = _keyword(facts, ctx.options.keyword)
    if not keyword or facts.word_count < 50:
        return SKIP
    count = facts.text.lower().count(keyword)
    density = round(count * 100 / max(facts.word_count, 1), 1)
    if density > 4.0:
        return Failure({"density": density, "count": count}, f"{count} × {keyword}")


def _check_alt(facts: PageFacts, _ctx: RuleContext):
    if not facts.images:
        return SKIP
    missing = [image for image in facts.images if not image.alt_present]
    if missing:
        return Failure({"count": len(missing), "total": len(facts.images)},
                       "\n".join(image.src for image in missing[:3]))


def _check_dimensions(facts: PageFacts, _ctx: RuleContext):
    if not facts.images:
        return SKIP
    missing = [image for image in facts.images if not image.width or not image.height]
    if missing:
        return Failure({"count": len(missing)}, "\n".join(image.src for image in missing[:3]))


def _check_lazy(facts: PageFacts, _ctx: RuleContext):
    if len(facts.images) <= 3:
        return SKIP
    missing = [image for image in facts.images[3:] if image.loading.lower() != "lazy"]
    if len(missing) > len(facts.images) / 2:
        return Failure({"count": len(missing)}, "\n".join(image.src for image in missing[:3]))


def _check_internal_links(facts: PageFacts, _ctx: RuleContext):
    count = sum(1 for link in facts.links if link.internal)
    if count < 3:
        return Failure({"count": count})


def _check_broken_links(facts: PageFacts, ctx: RuleContext):
    if not ctx.links_checked:
        return SKIP
    broken = []
    for href, (status, error) in ctx.link_status.items():
        if status is None or status >= 400:
            broken.append(f"{href} ({status or error})")
    if broken:
        return Failure({"count": len(broken)}, "\n".join(broken[:5]))


def _check_redirect_links(facts: PageFacts, ctx: RuleContext):
    if not ctx.links_checked:
        return SKIP
    redirected = [href for href, (status, _error) in ctx.link_status.items()
                  if status in (301, 302, 303, 307, 308)]
    if redirected:
        return Failure({"count": len(redirected)}, "\n".join(redirected[:5]))


def _check_generic_anchors(facts: PageFacts, _ctx: RuleContext):
    generic = [link for link in facts.links if is_generic_anchor(link.text)]
    if generic:
        return Failure({"count": len(generic)}, "\n".join(link.href for link in generic[:3]))


def _check_structured_missing(facts: PageFacts, _ctx: RuleContext):
    if facts.status < 400 and not facts.jsonld and not facts.jsonld_invalid:
        return Failure()


def _check_structured_invalid(facts: PageFacts, _ctx: RuleContext):
    if facts.jsonld_invalid:
        return Failure({"count": len(facts.jsonld_invalid)}, facts.jsonld_invalid[0][:250])


def _check_product_offer(facts: PageFacts, _ctx: RuleContext):
    nodes = _jsonld_nodes(facts)
    if not _has_type(nodes, "Product"):
        return SKIP
    products = [node for node in nodes if "Product" in str(node.get("@type"))]
    if not any(node.get("offers") or node.get("price") for node in products):
        return Failure(evidence=str(products[0])[:200])


def _check_article_headline(facts: PageFacts, _ctx: RuleContext):
    nodes = _jsonld_nodes(facts)
    if not (_has_type(nodes, "Article") or _has_type(nodes, "BlogPosting") or _has_type(nodes, "NewsArticle")):
        return SKIP
    articles = [node for node in nodes if any(k in str(node.get("@type")) for k in ("Article", "BlogPosting", "NewsArticle"))]
    if not any(node.get("headline") for node in articles):
        return Failure(evidence=str(articles[0])[:200])


def _check_mobile_overflow(facts: PageFacts, _ctx: RuleContext):
    if facts.mobile_overflow is None:
        return SKIP
    if facts.mobile_overflow:
        return Failure()


def _check_small_text(facts: PageFacts, _ctx: RuleContext):
    if facts.mobile_overflow is None:
        return SKIP
    if facts.small_text_count:
        return Failure({"count": facts.small_text_count})


def _check_small_taps(facts: PageFacts, _ctx: RuleContext):
    if facts.mobile_overflow is None:
        return SKIP
    if facts.small_tap_count:
        return Failure({"count": facts.small_tap_count})


RULES: list[Rule] = [
    Rule("technical.https", "technical", "critical", 10, _check_https),
    Rule("technical.status", "technical", "critical", 12, _check_status),
    Rule("technical.redirect", "technical", "medium", 4, _check_redirect),
    Rule("technical.noindex", "technical", "critical", 12, _check_noindex),
    Rule("technical.canonical_missing", "technical", "high", 6, _check_canonical_missing),
    Rule("technical.canonical_mismatch", "technical", "high", 6, _check_canonical_mismatch),
    Rule("technical.viewport_missing", "technical", "high", 6, _check_viewport),
    Rule("technical.lang_missing", "technical", "low", 2, _check_lang),
    Rule("technical.charset_missing", "technical", "low", 1, _check_charset),
    Rule("technical.sitemap_missing", "technical", "medium", 3, _check_sitemap),
    Rule("technical.robots_disallow", "technical", "critical", 8, _check_robots),
    Rule("technical.mixed_content", "technical", "medium", 3, _check_mixed_content),
    Rule("meta.title_missing", "meta", "critical", 10, _check_title_missing),
    Rule("meta.title_length", "meta", "medium", 5, _check_title_length),
    Rule("meta.description_missing", "meta", "high", 8, _check_description_missing),
    Rule("meta.description_length", "meta", "medium", 4, _check_description_length),
    Rule("meta.og_missing", "meta", "low", 2, _check_og),
    Rule("meta.twitter_missing", "meta", "low", 1, _check_twitter),
    Rule("content.h1_missing", "content", "high", 10, _check_h1_missing),
    Rule("content.h1_multiple", "content", "medium", 4, _check_h1_multiple),
    Rule("content.thin", "content", "medium", 6, _check_thin),
    Rule("content.keyword_missing", "content", "medium", 5, _check_keyword_missing),
    Rule("content.title_keyword_missing", "content", "medium", 4, _check_title_keyword),
    Rule("content.description_keyword_missing", "content", "low", 2, _check_description_keyword),
    Rule("content.keyword_density_high", "content", "low", 2, _check_keyword_density),
    Rule("media.alt_missing", "media", "high", 8, _check_alt),
    Rule("media.dimensions_missing", "media", "low", 2, _check_dimensions),
    Rule("media.lazy_missing", "media", "low", 2, _check_lazy),
    Rule("links.internal_low", "links", "medium", 5, _check_internal_links),
    Rule("links.broken", "links", "high", 10, _check_broken_links),
    Rule("links.redirect", "links", "low", 2, _check_redirect_links),
    Rule("links.generic_anchor", "links", "low", 2, _check_generic_anchors),
    Rule("structured.missing", "structured", "medium", 4, _check_structured_missing),
    Rule("structured.invalid", "structured", "high", 5, _check_structured_invalid),
    Rule("structured.product_offer", "structured", "medium", 3, _check_product_offer),
    Rule("structured.article_headline", "structured", "medium", 3, _check_article_headline),
    Rule("mobile.overflow", "mobile", "medium", 4, _check_mobile_overflow),
    Rule("mobile.small_text", "mobile", "low", 2, _check_small_text),
    Rule("mobile.small_taps", "mobile", "low", 2, _check_small_taps),
]

RULES_BY_CATEGORY: dict[str, list[Rule]] = {}
for _rule in RULES:
    RULES_BY_CATEGORY.setdefault(_rule.category, []).append(_rule)


def run_rules(facts: PageFacts, ctx: RuleContext, categories: set[str] | None = None) -> list[tuple[Rule, Failure | None | object]]:
    out: list[tuple[Rule, Failure | None | object]] = []
    for rule in RULES:
        if categories is not None and rule.category not in categories:
            continue
        try:
            result = rule.check(facts, ctx)
        except Exception as exc:  # noqa: BLE001 - a broken rule must not break the audit
            result = Failure({"error": str(exc)})
        out.append((rule, result))
    return out


def site_issues(pages: list[PageFacts]) -> list[Issue]:
    issues: list[Issue] = []
    titles: dict[str, list[str]] = {}
    descriptions: dict[str, list[str]] = {}
    for page in pages:
        if page.title:
            titles.setdefault(page.title.strip().lower(), []).append(page.final_url or page.url)
        if page.meta_description:
            descriptions.setdefault(page.meta_description.strip().lower(), []).append(page.final_url or page.url)
    duplicate_titles = [urls for urls in titles.values() if len(urls) > 1]
    duplicate_descriptions = [urls for urls in descriptions.values() if len(urls) > 1]
    if duplicate_titles:
        flat = [url for group in duplicate_titles for url in group]
        issues.append(Issue("site.duplicate_titles", "site", "medium", {"count": len(flat)},
                            "\n".join(flat[:8])))
    if duplicate_descriptions:
        flat = [url for group in duplicate_descriptions for url in group]
        issues.append(Issue("site.duplicate_descriptions", "site", "medium", {"count": len(flat)},
                            "\n".join(flat[:8])))
    return issues
