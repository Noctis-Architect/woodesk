import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.perf.models import PerfIssue, PerfMetrics, PerfResult, ResourceInfo
from app.perf.report import to_html as perf_html, to_json as perf_json
from app.perf.runner import _issues, _median, _metric_status, _score, _site_key
from app.seo.audit import _crawlable
from app.seo.models import PageFacts
from app.seo.rules import site_issues


def test_median_and_site_key():
    assert _median([1, 2, 3]) == 2
    assert _median([]) is None
    assert _site_key("cdn.example.com") == "example.com"
    assert _site_key("example.com") == "example.com"


def test_metric_status_thresholds():
    assert _metric_status(2500, 2500, 4000) == 0
    assert _metric_status(3000, 2500, 4000) == 1
    assert _metric_status(5000, 2500, 4000) == 2


def test_perf_issues_and_score():
    metrics = PerfMetrics(ttfb_ms=900, fcp_ms=2000, lcp_ms=5000, cls=0.3, tbt_ms=700, inp_ms=600)
    issues = _issues(metrics, [], [], ["/app.css"], {"oversized": 2, "missing_dimensions": 1}, 3_000_000, 60)
    codes = {issue.code for issue in issues}
    assert {"perf.lcp_slow", "perf.cls_high", "perf.tbt_high", "perf.ttfb_slow",
            "perf.fcp_slow", "perf.inp_lab", "perf.page_weight", "perf.requests_high",
            "perf.render_blocking"} <= codes
    score = _score(metrics, issues, 3_000_000, 60, [], ["/app.css"], {"oversized": 2})
    assert 0 <= score < 60


def test_crawlable_filters_non_html_and_admin():
    host = "example.com"
    assert _crawlable("https://example.com/products", host)
    assert not _crawlable("https://example.com/wp-json/wp/v2/posts", host)
    assert not _crawlable("https://example.com/cart", host)
    assert not _crawlable("https://example.com/image.jpg", host)
    assert not _crawlable("https://other.com/products", host)


def test_perf_reports():
    result = PerfResult(
        url="https://example.com/", final_url="https://example.com/", device="mobile",
        network="Mobile", runs=1, score=88, grade="B",
        metrics=PerfMetrics(ttfb_ms=100, fcp_ms=800, lcp_ms=1200, cls=0.02, tbt_ms=80),
        issues=[PerfIssue("perf.tbt_high", "low", {"ms": 250})],
        resources=[ResourceInfo(url="https://example.com/app.js", kind="Script", bytes=2048, duration_ms=200)],
        requests=2, bytes=4096, timestamp="2026-01-01 00:00",
    )
    assert '"score": 88' in perf_json(result)
    assert "WooDesk Speed Report" in perf_html(result, "en")


def test_site_duplicate_issues():
    one = PageFacts(url="https://example.com/a", final_url="https://example.com/a", title="Same",
                    meta_description="Same description")
    two = PageFacts(url="https://example.com/b", final_url="https://example.com/b", title="Same",
                    meta_description="Same description")
    issues = site_issues([one, two])
    codes = {issue.code for issue in issues}
    assert "site.duplicate_titles" in codes
    assert "site.duplicate_descriptions" in codes
