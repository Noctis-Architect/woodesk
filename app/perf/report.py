from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime
from urllib.parse import urlsplit

from .messages import perf_text
from .models import PerfResult

_COLORS = {"critical": "#e5484d", "high": "#e07a2f", "medium": "#b8860b", "low": "#6b7185", "info": "#6c5ce7"}


def summary(result: PerfResult) -> dict:
    return {
        "url": result.url,
        "final_url": result.final_url,
        "device": result.device,
        "network": result.network,
        "runs": result.runs,
        "score": result.score,
        "grade": result.grade,
        "timestamp": result.timestamp,
        "metrics": asdict(result.metrics),
        "requests": result.requests,
        "bytes": result.bytes,
        "third_parties": result.third_parties,
        "render_blocking": result.render_blocking,
        "images": result.images,
        "lcp_element": result.lcp_element,
        "issues": [asdict(issue) for issue in result.issues],
        "resources": [asdict(resource) for resource in result.resources],
        "browser": result.browser,
        "note": result.note,
        "raw_runs": result.raw_runs,
        "ai": None,
    }


def to_json(result: PerfResult) -> str:
    return json.dumps(summary(result), ensure_ascii=False, indent=2)


def _metric_value(key: str, value) -> str:
    if value is None:
        return "—"
    if key == "lcp_ms" or key == "fcp_ms" or key == "ttfb_ms" or key == "tbt_ms":
        return f"{value / 1000:.2f} s"
    if key == "cls":
        return f"{value:.3f}"
    return str(value)


def to_html(result: PerfResult, lang: str = "fa") -> str:
    labels = {
        "title": "گزارش سرعت WooDesk" if lang == "fa" else "WooDesk Speed Report",
        "score": "امتیاز" if lang == "fa" else "Score",
        "url": "آدرس" if lang == "fa" else "URL",
        "device": "دستگاه" if lang == "fa" else "Device",
        "runs": "اجرا" if lang == "fa" else "Runs",
        "metrics": "متریک‌ها" if lang == "fa" else "Metrics",
        "issues": "مشکلات" if lang == "fa" else "Issues",
        "resources": "منابع سنگین" if lang == "fa" else "Heavy resources",
        "requests": "درخواست" if lang == "fa" else "Requests",
        "weight": "حجم" if lang == "fa" else "Transfer",
        "no_issues": "مشکلی پیدا نشد." if lang == "fa" else "No issues found.",
        "fix": "راه‌حل" if lang == "fa" else "Fix",
        "who": "مرورگر" if lang == "fa" else "Browser",
    }
    metrics = [
        ("LCP", result.metrics.lcp_ms, "ms"), ("CLS", result.metrics.cls, ""),
        ("TBT", result.metrics.tbt_ms, "ms"), ("INP (lab)", result.metrics.inp_ms, "ms"),
        ("FCP", result.metrics.fcp_ms, "ms"), ("TTFB", result.metrics.ttfb_ms, "ms"),
    ]
    cards = "".join(
        f"<div class='card'><b>{name}</b><span>{_metric_value(name.lower() + '_ms' if name != 'CLS' else 'cls', value)}</span></div>"
        for name, value, _unit in metrics
    )
    issues = ""
    for issue in result.issues:
        title, detail, fix = perf_text(issue, lang)
        color = _COLORS.get(issue.severity, "#6b7185")
        evidence = f"<pre>{html.escape(issue.evidence)}</pre>" if issue.evidence else ""
        issues += (
            f"<div class='issue' style='border-left-color:{color}'><span class='sev' style='background:{color}'>"
            f"{html.escape(issue.severity)}</span> <b>{html.escape(title)}</b>"
            f"<p>{html.escape(detail)}</p>{evidence}<p><b>{labels['fix']}:</b> {html.escape(fix)}</p></div>"
        )
    if not issues:
        issues = f"<p>{labels['no_issues']}</p>"
    rows = "".join(
        f"<tr><td>{html.escape(resource.url)}</td><td>{html.escape(resource.kind)}</td>"
        f"<td>{resource.bytes / 1024:.1f} KB</td><td>{resource.duration_ms} ms</td></tr>"
        for resource in result.resources[:10]
    )
    direction = ' dir="rtl"' if lang == "fa" else ""
    return f"""<!doctype html><html lang="{lang}"{direction}><head><meta charset="utf-8"><title>{html.escape(labels['title'])}</title>
<style>body{{font-family:Tahoma,Arial,sans-serif;background:#f4f5f9;color:#1c2033;margin:0;padding:32px}}
.wrap{{max-width:960px;margin:auto;background:#fff;border:1px solid #e3e5ec;border-radius:14px;padding:28px}}
h1{{margin:0 0 6px}} h2{{margin-top:24px;border-bottom:1px solid #e3e5ec;padding-bottom:6px}}
.meta{{color:#6b7185;font-size:13px}} .score{{font-size:40px;font-weight:bold;color:#6c5ce7}}
.cards{{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}} .card{{border:1px solid #e3e5ec;border-radius:9px;padding:12px 18px;min-width:120px}}
.card b{{display:block;color:#6b7185;font-size:12px}} .card span{{font-size:20px;font-weight:bold}}
.issue{{border:1px solid #e3e5ec;border-left:5px solid;border-radius:8px;padding:12px 14px;margin:10px 0}}
.sev{{color:#fff;border-radius:5px;padding:2px 7px;font-size:12px}} pre{{background:#f4f5f9;padding:8px;white-space:pre-wrap;word-break:break-all}}
table{{width:100%;border-collapse:collapse}} td,th{{padding:7px;border-bottom:1px solid #e3e5ec;text-align:start;font-size:13px}}</style></head>
<body><div class="wrap"><h1>{html.escape(labels['title'])}</h1>
<div class="score">{result.score} <small>{html.escape(result.grade)}</small></div>
<p class="meta">{html.escape(result.final_url or result.url)} · {html.escape(result.timestamp)} · {html.escape(result.network)} · {result.runs} runs</p>
<p class="meta">{result.requests} requests · {result.bytes / 1024 / 1024:.2f} MB · LCP element: {html.escape(result.lcp_element or '-')}</p>
<h2>{labels['metrics']}</h2><div class="cards">{cards}</div>
<h2>{labels['issues']}</h2>{issues}
<h2>{labels['resources']}</h2><table><tr><th>URL</th><th>Type</th><th>Size</th><th>Time</th></tr>{rows}</table>
<p class="meta">{labels['who']}: {html.escape(result.browser)}</p>
</div></body></html>"""


def filename(result: PerfResult, prefix: str = "woodesk-speed") -> str:
    host = urlsplit(result.final_url or result.url).hostname or "site"
    return f"{prefix}-{host}-{datetime.now().strftime('%Y%m%d-%H%M')}"
