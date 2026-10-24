from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import ImageInfo, LinkInfo, PageFacts

GENERIC_ANCHORS = {
    "click here", "here", "read more", "more", "learn more", "this link", "link",
    "اینجا", "اینجا کلیک کنید", "بیشتر", "ادامه مطلب", "لینک", "این لینک",
}
_WORD = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _meta_map(soup: BeautifulSoup) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        key = (tag.get("name") or tag.get("property") or tag.get("http-equiv") or "").strip().lower()
        content = tag.get("content")
        if key and content is not None and key not in out:
            out[key] = _text(content)
    return out


def _header(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def _first_srcset(value: str) -> str:
    return value.split(",")[0].strip().split(" ")[0] if value else ""


def _jsonld(soup: BeautifulSoup, facts: PageFacts) -> None:
    for tag in soup.find_all("script"):
        if "ld+json" not in (tag.get("type") or "").lower():
            continue
        raw = tag.string if tag.string is not None else tag.get_text()
        raw = (raw or "").strip()
        if not raw:
            continue
        facts.jsonld_raw.append(raw)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            facts.jsonld_invalid.append(raw[:500])
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                facts.jsonld.extend(x for x in graph if isinstance(x, dict))
            facts.jsonld.append(item)


def _images(soup: BeautifulSoup, base_url: str) -> list[ImageInfo]:
    out: list[ImageInfo] = []
    for tag in soup.find_all("img"):
        src = tag.get("src") or tag.get("data-src") or _first_srcset(tag.get("srcset") or "")
        if not src:
            continue
        src = urljoin(base_url, src)
        alt = tag.get("alt")
        out.append(ImageInfo(
            src=src,
            alt=_text(alt),
            alt_present=alt is not None,
            width=str(tag.get("width") or ""),
            height=str(tag.get("height") or ""),
            loading=str(tag.get("loading") or ""),
            srcset=str(tag.get("srcset") or ""),
        ))
        if len(out) >= 300:
            break
    return out


def _links(soup: BeautifulSoup, base_url: str) -> list[LinkInfo]:
    base_host = (urlparse(base_url).hostname or "").lower()
    out: list[LinkInfo] = []
    seen: set[str] = set()
    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        key = absolute.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(LinkInfo(
            href=key,
            text=_text(tag.get_text(" ", strip=True))[:160],
            rel=str(tag.get("rel") or "").lower(),
            internal=(parsed.hostname or "").lower() == base_host,
        ))
        if len(out) >= 500:
            break
    return out


def _mixed_content(soup: BeautifulSoup, final_url: str) -> list[str]:
    if not final_url.lower().startswith("https://"):
        return []
    found: list[str] = []
    for tag in soup.find_all(["img", "script", "link", "iframe", "source", "video", "audio"]):
        for attr in ("src", "href", "data-src"):
            value = str(tag.get(attr) or "").strip()
            if value.lower().startswith("http://"):
                resolved = urljoin(final_url, value)
                if resolved not in found:
                    found.append(resolved)
                    if len(found) >= 20:
                        return found
    return found


def extract(html: str, url: str, *, final_url: str = "", status: int = 200,
            headers: dict[str, str] | None = None, rendered: bool = False,
            elapsed_ms: int = 0, dom_metrics: dict[str, Any] | None = None) -> PageFacts:
    headers = headers or {}
    final_url = final_url or url
    dom_metrics = dom_metrics or {}
    soup = BeautifulSoup(html or "", "html.parser")
    meta = _meta_map(soup)
    facts = PageFacts(
        url=url,
        final_url=final_url,
        status=status,
        headers={k.lower(): v for k, v in headers.items()},
        html=html or "",
        rendered=rendered,
        elapsed_ms=elapsed_ms,
        title=_text(soup.title.get_text(" ", strip=True)) if soup.title else "",
        meta_description=meta.get("description", ""),
        meta_robots=" ".join(filter(None, (meta.get("robots", ""), meta.get("googlebot", "")))),
        x_robots=_header(headers, "x-robots-tag"),
        canonical="",
        lang=_text(soup.html.get("lang")) if soup.html else "",
        charset="",
        viewport=meta.get("viewport", ""),
        og={k: v for k, v in meta.items() if k.startswith("og:")},
        twitter={k: v for k, v in meta.items() if k.startswith("twitter:")},
        robots_txt="",
        html_bytes=len((html or "").encode("utf-8", errors="ignore")),
        mobile_overflow=dom_metrics.get("overflow") if isinstance(dom_metrics.get("overflow"), bool) else None,
        small_text_count=int(dom_metrics.get("small_text") or 0),
        small_tap_count=int(dom_metrics.get("small_taps") or 0),
    )

    canonical = soup.find("link", rel=lambda rel: rel and "canonical" in [r.lower() for r in (rel if isinstance(rel, list) else [rel])])
    if canonical and canonical.get("href"):
        facts.canonical = urljoin(final_url, str(canonical.get("href")).strip())

    charset = soup.find("meta", attrs={"charset": True})
    if charset:
        facts.charset = str(charset.get("charset") or "")
    elif "charset=" in meta.get("content-type", "").lower():
        facts.charset = meta.get("content-type", "").split("charset=", 1)[-1].strip()

    for tag in soup.find_all(re.compile(r"^h[1-6]$", re.I)):
        level = tag.name.lower()
        text = _text(tag.get_text(" ", strip=True))
        if text:
            facts.headings.append((level, text))
            if level == "h1":
                facts.h1.append(text)

    facts.hreflang = [
        {"lang": _text(tag.get("hreflang")), "href": urljoin(final_url, str(tag.get("href") or ""))}
        for tag in soup.find_all("link", hreflang=True, href=True)
        if _text(tag.get("hreflang"))
    ]

    _jsonld(soup, facts)
    facts.images = _images(soup, final_url)
    facts.links = _links(soup, final_url)
    facts.mixed_content = _mixed_content(soup, final_url)

    merge_images(facts.images, dom_metrics.get("images") or {})

    body = BeautifulSoup(html or "", "html.parser")
    for tag in body(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    facts.text = _text(body.get_text(" ", strip=True))
    facts.word_count = len(_WORD.findall(facts.text))
    return facts


def merge_images(images: list[ImageInfo], measured: dict[str, Any]) -> None:
    """Merge rendered natural/displayed sizes into the parsed image list (best effort)."""
    if not measured:
        return
    for image in images:
        data = measured.get(image.src)
        if not data:
            continue
        image.displayed_width = data.get("displayed_width")
        image.displayed_height = data.get("displayed_height")
        image.natural_width = data.get("natural_width")
        image.natural_height = data.get("natural_height")


def is_generic_anchor(text: str) -> bool:
    return text.strip().lower() in GENERIC_ANCHORS
