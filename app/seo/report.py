from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime

from .messages import category_label, issue_text, severity_label
from .models import AuditResult, Issue, SiteAuditResult

_COLORS = {"critical": "#e5484d", "high": "#e07a2f", "medium": "#b8860b", "low": "#6b7185", "info": "#6c5ce7"}


def _score_color(score: int) -> str:
    if score >= 80:
        return "#2fa36b"
    if score >= 60:
        return "#b8860b"
    return "#e5484d"


def _issue_html(issue: Issue, lang: str) -> str:
    title, detail, fix = issue_text(issue, lang)
    color = _COLORS.get(issue.severity, "#6b7185")
    evidence = f"<pre>{html.escape(issue.evidence)}</pre>" if issue.evidence else ""
    return (
        f'<div class="issue" style="border-left-color:{color}">'
        f'<div class="issue-head"><span class="sev" style="background:{color}">{html.escape(severity_label(issue.severity, lang))}</span>'
        f'<b>{html.escape(title)}</b><span class="cat">{html.escape(category_label(issue.category, lang))}</span></div>'
        f'<p>{html.escape(detail)}</p>{evidence}'
        f'<p class="fix"><b>{"راه‌حل" if lang == "fa" else "Fix"}:</b> {html.escape(fix)}</p></div>'
    )


def summary(result: AuditResult) -> dict:
    facts = result.facts
    return {
        "url": result.url,
        "final_url": result.final_url,
        "status": result.status,
        "rendered": result.rendered,
        "fetched_at": result.fetched_at,
        "overall": result.overall,
        "grade": result.grade,
        "duration_ms": result.duration_ms,
        "categories": [asdict(category) for category in result.categories],
        "issues": [asdict(issue) for issue in result.issues],
        "facts": {
            "title": facts.title,
            "meta_description": facts.meta_description,
            "canonical": facts.canonical,
            "lang": facts.lang,
            "viewport": facts.viewport,
            "h1": facts.h1,
            "word_count": facts.word_count,
            "images": len(facts.images),
            "links": len(facts.links),
            "internal_links": sum(1 for link in facts.links if link.internal),
            "jsonld_types": facts.jsonld_types,
            "sitemap_found": facts.sitemap_found,
            "robots_allowed": facts.robots_allowed,
        },
        "note": result.note,
        "ai": result.ai,
    }


def to_json(result: AuditResult) -> str:
    return json.dumps(summary(result), ensure_ascii=False, indent=2)


def to_html(result: AuditResult, lang: str = "fa") -> str:
    text = "گزارش سئوی WooDesk" if lang == "fa" else "WooDesk SEO Report"
    labels = {
        "score": "امتیاز" if lang == "fa" else "Score",
        "url": "آدرس" if lang == "fa" else "URL",
        "date": "تاریخ" if lang == "fa" else "Date",
        "mode": "حالت" if lang == "fa" else "Mode",
        "rendered": "رندرشده با JavaScript" if lang == "fa" else "Rendered with JavaScript",
        "static": "HTML استاتیک" if lang == "fa" else "Static HTML",
        "categories": "دسته‌ها" if lang == "fa" else "Categories",
        "issues": "مشکلات" if lang == "fa" else "Issues",
        "no_issues": "مشکلی پیدا نشد." if lang == "fa" else "No issues found.",
        "title": "عنوان" if lang == "fa" else "Title",
        "description": "توضیحات متا" if lang == "fa" else "Meta description",
        "h1": "H1" if lang == "fa" else "H1",
        "words": "کلمات" if lang == "fa" else "Words",
        "images": "تصاویر" if lang == "fa" else "Images",
        "links": "لینک‌ها" if lang == "fa" else "Links",
        "ai": "تحلیل هوش مصنوعی" if lang == "fa" else "AI analysis",
        "summary": "خلاصه" if lang == "fa" else "Summary",
        "priorities": "اولویت‌ها" if lang == "fa" else "Priorities",
        "quick_wins": "بردهای سریع" if lang == "fa" else "Quick wins",
    }
    facts = result.facts
    categories = "".join(
        f'<tr><td>{html.escape(category_label(category.category, lang))}</td>'
        f'<td><div class="bar"><span style="width:{category.score}%;background:{_score_color(category.score)}"></span></div></td>'
        f'<td>{category.score}</td></tr>'
        for category in result.categories
    )
    issues = "".join(_issue_html(issue, lang) for issue in result.issues) or f"<p>{labels['no_issues']}</p>"
    ai_html = ""
    if result.ai:
        ai = result.ai
        summary_text = html.escape(str(ai.get("summary") or ""))
        priorities = "".join(
            f"<li><b>{html.escape(str(item.get('issue') or ''))}</b>: {html.escape(str(item.get('action') or ''))}</li>"
            for item in ai.get("priorities", []) if isinstance(item, dict)
        )
        quick = "".join(f"<li>{html.escape(str(item))}</li>" for item in ai.get("quick_wins", []))
        ai_html = (
            f"<h2>{labels['ai']}</h2><p>{summary_text}</p>"
            f"<h3>{labels['priorities']}</h3><ul>{priorities}</ul>"
            f"<h3>{labels['quick_wins']}</h3><ul>{quick}</ul>"
        )
    direction = ' dir="rtl"' if lang == "fa" else ""
    return f"""<!doctype html>
<html lang="{lang}"{direction}><head><meta charset="utf-8">
<title>{html.escape(text)}</title>
<style>
body {{ font-family: Tahoma, Arial, sans-serif; background:#f4f5f9; color:#1c2033; margin:0; padding:32px; }}
.wrap {{ max-width: 960px; margin: auto; background:#fff; border:1px solid #e3e5ec; border-radius:14px; padding:28px; }}
h1 {{ margin:0 0 8px; }} h2 {{ margin-top:28px; border-bottom:1px solid #e3e5ec; padding-bottom:6px; }}
.meta {{ color:#6b7185; font-size:13px; line-height:1.9; }}
.score {{ float:{'left' if lang == 'fa' else 'right'}; text-align:center; border:8px solid {_score_color(result.overall)};
border-radius:50%; width:120px; height:120px; display:flex; flex-direction:column; justify-content:center; }}
.score b {{ font-size:38px; color:{_score_color(result.overall)}; }}
table {{ width:100%; border-collapse:collapse; }} td {{ padding:8px; vertical-align:middle; }}
.bar {{ height:10px; background:#eef0f7; border-radius:6px; overflow:hidden; min-width:180px; }}
.bar span {{ display:block; height:100%; }}
.issue {{ border:1px solid #e3e5ec; border-left:5px solid; border-radius:8px; padding:12px 14px; margin:10px 0; }}
.issue-head {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
.sev {{ color:#fff; border-radius:5px; padding:2px 7px; font-size:12px; }}
.cat {{ color:#6b7185; font-size:12px; margin-inline-start:auto; }}
.issue p {{ margin:8px 0 0; line-height:1.7; }} .issue .fix {{ color:#3a4058; }}
pre {{ background:#f4f5f9; padding:8px; border-radius:6px; white-space:pre-wrap; word-break:break-all; font-size:12px; }}
</style></head><body><div class="wrap">
<h1>{html.escape(text)}</h1>
<div class="score"><b>{result.overall}</b><span>{html.escape(result.grade)}</span></div>
<div class="meta"><b>{labels['url']}:</b> {html.escape(result.final_url or result.url)}<br>
<b>{labels['date']}:</b> {html.escape(result.fetched_at)}<br>
<b>{labels['mode']}:</b> {labels['rendered'] if result.rendered else labels['static']}</div>
<h2>{labels['categories']}</h2><table>{categories}</table>
<h2>{labels['title']} / {labels['description']} / {labels['h1']}</h2>
<div class="meta">{html.escape(facts.title or '-')}<br>{html.escape(facts.meta_description or '-')}<br>
{html.escape(' | '.join(facts.h1) or '-')}<br>
{labels['words']}: {facts.word_count} · {labels['images']}: {len(facts.images)} · {labels['links']}: {len(facts.links)}</div>
<h2>{labels['issues']} ({len(result.issues)})</h2>{issues}
{ai_html}
<p class="meta">WooDesk SEO Score</p>
</div></body></html>"""


def site_summary(result: SiteAuditResult) -> dict:
    return {
        "url": result.url,
        "fetched_at": result.fetched_at,
        "overall": result.overall,
        "grade": result.grade,
        "crawled": result.crawled,
        "duration_ms": result.duration_ms,
        "sitemap_urls": len(result.sitemap_urls),
        "errors": result.errors,
        "site_issues": [asdict(issue) for issue in result.site_issues],
        "pages": [summary(page) for page in result.pages],
        "ai": result.ai,
    }


def site_to_json(result: SiteAuditResult) -> str:
    return json.dumps(site_summary(result), ensure_ascii=False, indent=2)


def site_to_html(result: SiteAuditResult, lang: str = "fa") -> str:
    text = "گزارش سئوی سایت WooDesk" if lang == "fa" else "WooDesk Site SEO Report"
    rows = "".join(
        f'<tr><td><a href="{html.escape(page.final_url or page.url)}">{html.escape(page.final_url or page.url)}</a></td>'
        f'<td>{page.overall}</td><td>{page.grade}</td><td>{len(page.issues)}</td></tr>'
        for page in result.pages
    )
    site = "".join(_issue_html(issue, lang) for issue in result.site_issues)
    direction = ' dir="rtl"' if lang == "fa" else ""
    return f"""<!doctype html><html lang="{lang}"{direction}><head><meta charset="utf-8"><title>{html.escape(text)}</title>
<style>body{{font-family:Tahoma,Arial,sans-serif;background:#f4f5f9;color:#1c2033;padding:32px}}
.wrap{{max-width:960px;margin:auto;background:#fff;border:1px solid #e3e5ec;border-radius:14px;padding:28px}}
h1{{margin:0 0 8px}} h2{{margin-top:24px;border-bottom:1px solid #e3e5ec;padding-bottom:6px}}
table{{width:100%;border-collapse:collapse}} td,th{{padding:8px;border-bottom:1px solid #e3e5ec;text-align:start}}
.meta{{color:#6b7185;font-size:13px}} .score{{font-size:44px;font-weight:bold;color:{_score_color(result.overall)}}}
.issue{{border:1px solid #e3e5ec;border-left:5px solid #e07a2f;border-radius:8px;padding:12px 14px;margin:10px 0}}
.sev{{color:#fff;background:#e07a2f;border-radius:5px;padding:2px 7px;font-size:12px}} pre{{background:#f4f5f9;padding:8px;white-space:pre-wrap}}</style></head>
<body><div class="wrap"><h1>{html.escape(text)}</h1>
<div class="score">{result.overall} <small>{html.escape(result.grade)}</small></div>
<p class="meta">{html.escape(result.url)} · {html.escape(result.fetched_at)} · {result.crawled} pages · {result.duration_ms} ms</p>
<h2>Pages</h2><table><tr><th>URL</th><th>Score</th><th>Grade</th><th>Issues</th></tr>{rows}</table>
<h2>Site-wide issues</h2>{site or '<p>No site-wide issues found.</p>'}
</div></body></html>"""


def filename(result: AuditResult | SiteAuditResult, prefix: str = "woodesk-seo") -> str:
    host = ""
    if isinstance(result, AuditResult):
        from urllib.parse import urlsplit

        host = urlsplit(result.final_url or result.url).hostname or "site"
    else:
        from urllib.parse import urlsplit

        host = urlsplit(result.url).hostname or "site"
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"{prefix}-{host}-{stamp}"
