from __future__ import annotations

import html as html_lib
import time
from dataclasses import replace
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from .extract import extract
from .fetch import (RobotsInfo, UA, check_links, fetch_page, fetch_robots, fetch_sitemap, normalize_url)
from .models import (AuditOptions, AuditResult, PageFacts, SiteAuditResult, grade_for)
from .rules import RuleContext, run_rules, site_issues
from .scoring import evaluate

EXCLUDE_PARTS = ("/wp-admin", "/wp-login", "/wp-json", "/cart", "/checkout", "/my-account", "/search",
                 "/feed", "/xmlrpc.php", "add-to-cart", "/?s=", "?s=")
EXCLUDE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip", ".css", ".js",
               ".xml", ".json", ".ico", ".mp4", ".mp3")


class AuditCancelled(RuntimeError):
    pass


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def _report(progress, pct: int, key: str) -> None:
    if progress:
        progress(pct, key)


def _cancel(is_cancelled) -> None:
    if is_cancelled and is_cancelled():
        raise AuditCancelled("Audit cancelled")


def _crawlable(url: str, host: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() != host:
        return False
    lower = (parts.path or "/").lower()
    if any(part in lower for part in EXCLUDE_PARTS):
        return False
    if lower.endswith(EXCLUDE_EXT):
        return False
    return True


def audit_url(url: str, options: AuditOptions | None = None, *, progress=None, is_cancelled=None,
              with_site_meta: bool = True) -> AuditResult:
    options = options or AuditOptions()
    started = time.monotonic()
    address = normalize_url(url)
    _report(progress, 5, "Fetching the page")
    _cancel(is_cancelled)
    fetched = fetch_page(address, rendered=options.rendered, timeout=options.timeout)
    _report(progress, 42, "Parsing HTML and metadata")
    _cancel(is_cancelled)
    facts = extract(
        fetched.text, address,
        final_url=fetched.final_url, status=fetched.status, headers=fetched.headers,
        rendered=fetched.rendered, elapsed_ms=fetched.elapsed_ms, dom_metrics=fetched.dom_metrics,
    )

    link_status: dict[str, tuple[int | None, str]] = {}
    links_checked = False
    robots_checked = False
    sitemap_checked = False
    if with_site_meta:
        _report(progress, 55, "Checking robots.txt and sitemap")
        _cancel(is_cancelled)
        base = f"{urlsplit(fetched.final_url).scheme}://{urlsplit(fetched.final_url).netloc}"
        robots: RobotsInfo = fetch_robots(base)
        facts.robots_txt = robots.text
        facts.robots_allowed = robots.allowed
        robots_checked = True
        try:
            found, sitemap_urls = fetch_sitemap(base, robots)
            facts.sitemap_found = found
            facts.sitemap_urls = sitemap_urls
            sitemap_checked = True
        except Exception:  # noqa: BLE001 - sitemap is optional
            pass

    if options.check_links and facts.links:
        _report(progress, 70, "Checking internal links")
        _cancel(is_cancelled)
        link_status = check_links(facts.links, options.max_links)
        links_checked = bool(link_status)

    _report(progress, 86, "Applying SEO rules")
    _cancel(is_cancelled)
    ctx = RuleContext(
        options=options,
        link_status=link_status,
        links_checked=links_checked,
        robots_checked=robots_checked,
        sitemap_checked=sitemap_checked,
    )
    results = run_rules(facts, ctx)
    issues, categories, overall, grade = evaluate(facts, results, fetched.final_url)
    _report(progress, 100, "Done")
    return AuditResult(
        url=address,
        final_url=fetched.final_url,
        status=fetched.status,
        rendered=fetched.rendered,
        fetched_at=_now(),
        overall=overall,
        grade=grade,
        categories=categories,
        issues=issues,
        facts=facts,
        duration_ms=int((time.monotonic() - started) * 1000),
        note=fetched.note,
    )


def audit_content(title: str, body: str, *, meta_title: str = "", meta_description: str = "",
                  keyword: str = "", images: list[dict] | None = None) -> AuditResult:
    """Offline audit for an unsaved product/post. No network access."""
    image_html = ""
    for image in images or []:
        src = html_lib.escape(str(image.get("src") or ""), quote=True)
        if "alt" in image:
            alt = html_lib.escape(str(image.get("alt") or ""), quote=True)
            image_html += f'<img src="{src}" alt="{alt}">'
        else:
            image_html += f'<img src="{src}">'
    document = (
        '<!doctype html><html lang="fa"><head><meta charset="utf-8">'
        f"<title>{html_lib.escape(meta_title or title)}</title>"
        f'<meta name="description" content="{html_lib.escape(meta_description, quote=True)}">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>'
        f"<h1>{html_lib.escape(title)}</h1>{body or ''}{image_html}</body></html>"
    )
    facts = extract(document, "", final_url="", status=200, headers={"content-type": "text/html"})
    facts.url = ""
    facts.final_url = ""
    options = AuditOptions(keyword=keyword, rendered=False, check_links=False, scope="content")
    ctx = RuleContext(options=options)
    results = run_rules(facts, ctx, categories={"meta", "content", "media"})
    issues, categories, overall, grade = evaluate(facts, results)
    return AuditResult(
        url="", final_url="", status=200, rendered=False, fetched_at=_now(),
        overall=overall, grade=grade, categories=categories, issues=issues, facts=facts,
        note="Content-only audit (no live page).",
    )


def audit_site(url: str, options: AuditOptions | None = None, *, progress=None, is_cancelled=None) -> SiteAuditResult:
    options = options or AuditOptions()
    started = time.monotonic()
    address = normalize_url(url)
    _report(progress, 3, "Fetching the homepage")
    home = audit_url(address, options, progress=None, is_cancelled=is_cancelled, with_site_meta=True)
    base = f"{urlsplit(home.final_url).scheme}://{urlsplit(home.final_url).netloc}"
    host = (urlsplit(home.final_url).hostname or "").lower()
    robots = fetch_robots(base)
    try:
        _found, sitemap = fetch_sitemap(base, robots)
    except Exception:  # noqa: BLE001
        sitemap = []

    candidates: list[str] = [home.final_url]
    for candidate in [*sitemap, *[link.href for link in home.facts.links if link.internal]]:
        absolute = urljoin(base, candidate)
        if absolute not in candidates and _crawlable(absolute, host):
            candidates.append(absolute)
        if len(candidates) >= options.max_pages:
            break

    pages: list[AuditResult] = [home]
    errors: list[str] = []
    sub_options = replace(options, rendered=False, check_links=False)
    total = min(len(candidates), max(1, options.max_pages))
    for index, page_url in enumerate(candidates[1:total], start=1):
        _cancel(is_cancelled)
        if robots.text:
            try:
                from urllib.robotparser import RobotFileParser

                parser = RobotFileParser()
                parser.set_url(base + "/robots.txt")
                parser.parse(robots.text.splitlines())
                if not parser.can_fetch(UA, page_url):
                    continue
            except Exception:
                pass
        _report(progress, 5 + int(90 * index / max(total, 1)), f"Auditing page {index + 1}/{total}")
        try:
            pages.append(audit_url(page_url, sub_options, is_cancelled=is_cancelled, with_site_meta=False))
        except AuditCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - keep scanning the rest of the site
            errors.append(f"{page_url}: {exc}")
        if options.delay_ms:
            time.sleep(options.delay_ms / 1000)

    issues = site_issues([page.facts for page in pages])
    overall = round(sum(page.overall for page in pages) / len(pages)) if pages else 0
    overall = max(0, min(100, overall - 4 * len(issues)))
    _report(progress, 100, "Done")
    return SiteAuditResult(
        url=address,
        fetched_at=_now(),
        overall=overall,
        grade=grade_for(overall),
        pages=pages,
        site_issues=issues,
        sitemap_urls=sitemap,
        crawled=len(pages),
        duration_ms=int((time.monotonic() - started) * 1000),
        errors=errors,
    )
