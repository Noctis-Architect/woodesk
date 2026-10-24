from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from .. import __version__

UA = f"WooDesk SEO Tester/{__version__} (+https://woodesk.wp-hub.org)"
MAX_HTML = 8 * 1024 * 1024
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)


class FetchError(RuntimeError):
    pass


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    text: str
    elapsed_ms: int = 0
    rendered: bool = False
    note: str = ""
    dom_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class RobotsInfo:
    text: str = ""
    allowed: bool = True
    sitemaps: list[str] = field(default_factory=list)


def normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise FetchError("Enter a URL to audit.")
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise FetchError("Enter a valid http(s) URL.")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def _html_type(headers: dict[str, str]) -> bool:
    ctype = ""
    for key, value in headers.items():
        if key.lower() == "content-type":
            ctype = value.lower()
            break
    return not ctype or "html" in ctype or "text/plain" in ctype


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
        headers={"User-Agent": UA, "Accept-Language": "fa,en;q=0.8", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    )


def fetch_static(url: str, timeout: float = 20.0) -> FetchResult:
    started = time.monotonic()
    try:
        with _client(timeout) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not fetch the page: {exc}") from exc
    elapsed = int((time.monotonic() - started) * 1000)
    headers = {k.lower(): v for k, v in response.headers.items()}
    if not _html_type(headers):
        raise FetchError(f"The URL did not return HTML ({headers.get('content-type', 'unknown type')}).")
    if len(response.content) > MAX_HTML:
        raise FetchError("The HTML document is larger than 8 MB; refusing to parse it.")
    note = ""
    if str(response.url) != response.request.url:
        note = f"Redirected from {response.request.url}"
    return FetchResult(
        url=url,
        final_url=str(response.url),
        status=response.status_code,
        headers=headers,
        text=response.text,
        elapsed_ms=elapsed,
        rendered=False,
        note=note,
    )


_DOM_METRICS_JS = r"""
() => {
  const images = {};
  let imageCount = 0;
  for (const img of document.images) {
    const key = img.currentSrc || img.src;
    if (!key) continue;
    images[key] = {
      displayed_width: Math.round(img.clientWidth || 0),
      displayed_height: Math.round(img.clientHeight || 0),
      natural_width: Math.round(img.naturalWidth || 0),
      natural_height: Math.round(img.naturalHeight || 0),
    };
    if (++imageCount >= 300) break;
  }
  let smallText = 0;
  let considered = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (considered++ > 4000) break;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
    if (el.children.length || !(el.textContent || '').trim()) continue;
    const size = parseFloat(style.fontSize || '0');
    if (size > 0 && size < 12) smallText++;
  }
  let smallTaps = 0;
  for (const el of document.querySelectorAll('a,button,input,select,textarea,[role="button"]')) {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (rect.width < 48 || rect.height < 48) smallTaps++;
  }
  return {
    overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
    small_text: smallText,
    small_taps: smallTaps,
    images: images,
  };
}
"""


def fetch_rendered(url: str, timeout: float = 30.0) -> FetchResult:
    started = time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchError("Playwright is not installed.") from exc

    from ..perf.browser import BrowserUnavailable, launch

    try:
        with sync_playwright() as playwright:
            browser, _choice = launch(playwright, headless=True)
            try:
                context = browser.new_context(
                    viewport={"width": 412, "height": 823},
                    device_scale_factor=1.75,
                    is_mobile=True,
                    has_touch=True,
                    locale="fa-IR",
                    ignore_https_errors=True,
                )
                page = context.new_page()
                response = None
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
                except Exception:
                    # A slow subresource must not hide the document we already have.
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(700)
                html = page.content()
                headers = response.all_headers() if response else {}
                status = response.status if response else (200 if html else 0)
                final_url = page.url
                dom_metrics = page.evaluate(_DOM_METRICS_JS)
            finally:
                browser.close()
    except BrowserUnavailable as exc:
        raise FetchError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"Headless Chromium failed: {str(exc).splitlines()[0]}") from exc

    if not html.strip():
        raise FetchError("The browser returned an empty document.")
    if len(html.encode("utf-8", errors="ignore")) > MAX_HTML:
        raise FetchError("The rendered document is larger than 8 MB; refusing to parse it.")
    return FetchResult(
        url=url,
        final_url=final_url,
        status=status,
        headers={k.lower(): v for k, v in headers.items()},
        text=html,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        rendered=True,
        dom_metrics=dom_metrics or {},
    )


def fetch_page(url: str, rendered: bool = True, timeout: float = 20.0) -> FetchResult:
    if rendered:
        try:
            return fetch_rendered(url, max(timeout, 30.0))
        except FetchError as exc:
            static = fetch_static(url, timeout)
            static.note = f"JavaScript rendering was unavailable, so the static HTML was analyzed. {exc}"
            return static
    return fetch_static(url, timeout)


def fetch_robots(base_url: str, timeout: float = 10.0) -> RobotsInfo:
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        with _client(timeout) as client:
            response = client.get(robots_url)
    except httpx.HTTPError:
        return RobotsInfo()
    if response.status_code >= 400:
        return RobotsInfo()
    text = response.text[:500_000]
    allowed = True
    try:
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(text.splitlines())
        allowed = parser.can_fetch(UA, base_url)
    except Exception:
        pass
    sitemaps = []
    for line in text.splitlines():
        if line.strip().lower().startswith("sitemap:"):
            value = line.split(":", 1)[1].strip()
            if value and value not in sitemaps:
                sitemaps.append(value)
    return RobotsInfo(text=text, allowed=allowed, sitemaps=sitemaps)


def fetch_sitemap(base_url: str, robots: RobotsInfo, timeout: float = 10.0, limit: int = 500) -> tuple[bool, list[str]]:
    candidates = list(robots.sitemaps)
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
        value = urljoin(base_url, path)
        if value not in candidates:
            candidates.append(value)
    seen_sitemaps: set[str] = set()
    urls: list[str] = []
    found = False
    try:
        with _client(timeout) as client:
            queue = candidates[:3]
            while queue and len(seen_sitemaps) < 3 and len(urls) < limit:
                sm_url = queue.pop(0)
                if sm_url in seen_sitemaps:
                    continue
                seen_sitemaps.add(sm_url)
                try:
                    response = client.get(sm_url)
                except httpx.HTTPError:
                    continue
                if response.status_code >= 400 or "<" not in response.text[:200]:
                    continue
                found = True
                for loc in _LOC.findall(response.text):
                    loc = urljoin(sm_url, loc.strip())
                    if loc in seen_sitemaps or loc in urls:
                        continue
                    if loc.lower().endswith((".xml", ".xml.gz")) or "sitemap" in loc.lower():
                        if len(queue) < 3:
                            queue.append(loc)
                        continue
                    urls.append(loc)
                    if len(urls) >= limit:
                        break
    except Exception:
        pass
    return found, urls


def check_links(links: list[Any], max_links: int = 8, timeout: float = 8.0) -> dict[str, tuple[int | None, str]]:
    """Check a small sample of internal links. Returns href -> (status, error)."""
    results: dict[str, tuple[int | None, str]] = {}
    targets = []
    for link in links:
        if not getattr(link, "internal", False):
            continue
        href = getattr(link, "href", "")
        if href and href not in results and href not in targets:
            targets.append(href)
        if len(targets) >= max_links:
            break
    if not targets:
        return results
    with httpx.Client(follow_redirects=False, timeout=httpx.Timeout(timeout, connect=5.0),
                      headers={"User-Agent": UA}, limits=httpx.Limits(max_connections=3)) as client:
        for href in targets:
            try:
                response = client.head(href)
                if response.status_code in (403, 405, 501):
                    response = client.get(href)
                results[href] = (response.status_code, "")
            except httpx.HTTPError as exc:
                results[href] = (None, str(exc))
    return results
