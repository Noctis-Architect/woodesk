import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.seo.audit import audit_content
from app.seo.extract import extract
from app.seo.fetch import normalize_url
from app.seo.models import AuditOptions
from app.seo.report import to_html, to_json
from app.seo.rules import RuleContext, run_rules
from app.seo.scoring import evaluate


def good_html() -> str:
    words = ("A complete guide to WooCommerce SEO helps store owners improve product pages, "
             "write useful descriptions and measure technical health. ") * 40
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WooCommerce SEO guide for store owners</title>
<meta name="description" content="A practical WooCommerce SEO guide covering product pages, technical health, content quality and the metrics that matter for store owners.">
<meta property="og:title" content="WooCommerce SEO guide">
<meta property="og:description" content="A practical guide for store owners.">
<meta property="og:image" content="https://example.com/cover.jpg">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="WooCommerce SEO guide">
<meta name="twitter:description" content="A practical guide for store owners.">
<link rel="canonical" href="https://example.com/guide">
<script type="application/ld+json">{json.dumps({"@context": "https://schema.org", "@type": "Product", "name": "Guide", "offers": {"@type": "Offer", "price": "10", "priceCurrency": "USD"}})}</script>
</head>
<body>
<h1>WooCommerce SEO guide</h1>
<p>{words} WooCommerce SEO is a repeatable process.</p>
<img src="/one.jpg" alt="one" width="640" height="480" loading="lazy">
<img src="/two.jpg" alt="two" width="640" height="480" loading="lazy">
<img src="/three.jpg" alt="three" width="640" height="480" loading="lazy">
<img src="/four.jpg" alt="four" width="640" height="480" loading="lazy">
<a href="/products">Products</a>
<a href="/blog">Blog</a>
<a href="/contact">Contact</a>
</body></html>"""


BAD_HTML = """<!doctype html><html><head><title></title></head><body>
<p>hi</p><img src="/no-alt.jpg"><img src="/also-no-alt.jpg"><a href="/x">click here</a>
</body></html>"""


def parse(html: str, url: str = "https://example.com/guide"):
    return extract(html, url, final_url=url, status=200, headers={"content-type": "text/html"})


def audit(facts, keyword: str = "woocommerce seo"):
    options = AuditOptions(keyword=keyword, rendered=False, check_links=False)
    ctx = RuleContext(options=options)
    results = run_rules(facts, ctx)
    return evaluate(facts, results)


def test_good_page_scores_high():
    facts = parse(good_html())
    issues, categories, overall, grade = audit(facts)
    codes = {issue.code for issue in issues}
    assert "meta.title_missing" not in codes
    assert "content.h1_missing" not in codes
    assert "media.alt_missing" not in codes
    assert overall >= 90, (overall, codes)
    assert grade in ("A", "A+")


def test_bad_page_flags_critical_issues_and_caps_score():
    facts = parse(BAD_HTML, "http://example.com/bad")
    issues, categories, overall, grade = audit(facts, keyword="")
    codes = {issue.code for issue in issues}
    assert "technical.https" in codes
    assert "meta.title_missing" in codes
    assert "meta.description_missing" in codes
    assert "content.h1_missing" in codes
    assert "media.alt_missing" in codes
    assert overall <= 50
    assert any(issue.severity == "critical" for issue in issues)


def test_canonical_mismatch_is_detected():
    html = good_html().replace('href="https://example.com/guide"', 'href="https://example.com/other"')
    facts = parse(html)
    issues, _categories, _overall, _grade = audit(facts)
    assert any(issue.code == "technical.canonical_mismatch" for issue in issues)


def test_keyword_checks():
    html = good_html().replace("WooCommerce SEO", "a different topic").replace("woocommerce seo", "a different topic")
    facts = parse(html)
    issues, _categories, _overall, _grade = audit(facts, keyword="woocommerce seo")
    codes = {issue.code for issue in issues}
    assert "content.title_keyword_missing" in codes
    assert "content.keyword_missing" in codes


def test_invalid_jsonld_is_detected():
    html = good_html().replace(
        '<script type="application/ld+json">',
        '<script type="application/ld+json">{not json}',
    )
    facts = parse(html)
    assert facts.jsonld_invalid
    issues, _categories, _overall, _grade = audit(facts)
    assert any(issue.code == "structured.invalid" for issue in issues)


def test_content_audit_offline():
    result = audit_content(
        "Demo product",
        "<p>Short description.</p>",
        meta_description="",
        keyword="demo product",
        images=[{"src": "https://example.com/a.jpg"}],
    )
    codes = {issue.code for issue in result.issues}
    assert "meta.description_missing" in codes
    assert "content.thin" in codes
    assert "media.alt_missing" in codes
    assert result.overall < 100


def test_skipped_rules_do_not_lower_score():
    facts = parse(good_html())
    options = AuditOptions(keyword="", rendered=False, check_links=False)
    ctx = RuleContext(options=options)
    results = run_rules(facts, ctx)
    _issues, _categories, overall, _grade = evaluate(facts, results)
    assert overall >= 90


def test_url_normalization_and_reports():
    assert normalize_url("example.com/page") == "https://example.com/page"
    assert normalize_url("http://example.com") == "http://example.com/"
    facts = parse(good_html())
    options = AuditOptions(keyword="", rendered=False, check_links=False)
    issues, categories, overall, grade = evaluate(facts, run_rules(facts, RuleContext(options=options)))
    from app.seo.models import AuditResult

    result = AuditResult(
        url="https://example.com/guide", final_url="https://example.com/guide", status=200,
        rendered=False, fetched_at="2026-01-01 00:00", overall=overall, grade=grade,
        categories=categories, issues=issues, facts=facts,
    )
    assert str(overall) in to_json(result)
    assert "WooDesk SEO Report" in to_html(result, "en")
