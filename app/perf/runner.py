from __future__ import annotations

import statistics
import time
from datetime import datetime
from urllib.parse import urlsplit

from .browser import launch
from .models import PerfIssue, PerfMetrics, PerfResult, ResourceInfo, perf_grade

DEVICES = {
    "mobile": {
        "label": "Mobile · Slow 4G",
        "viewport": {"width": 412, "height": 823},
        "dpr": 1.75,
        "mobile": True,
        "touch": True,
        "cpu": 4,
        "latency": 150,
        "download": int(1.6 * 1024 * 1024 / 8),
        "upload": int(750 * 1024 / 8),
    },
    "desktop": {
        "label": "Desktop · Broadband",
        "viewport": {"width": 1350, "height": 940},
        "dpr": 1,
        "mobile": False,
        "touch": False,
        "cpu": 1,
        "latency": 40,
        "download": int(10 * 1024 * 1024 / 8),
        "upload": int(5 * 1024 * 1024 / 8),
    },
}

_INIT = r"""
(() => {
  window.__wd = {lcp: [], cls: 0, shifts: 0, longtasks: [], fcp: 0, events: []};
  const add = (fn) => { try { fn(); } catch (e) { window.__wd.error = String(e); } };
  add(() => new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      let el = '';
      try {
        if (e.element) el = e.element.tagName + (e.element.id ? '#' + e.element.id : '');
      } catch (_) {}
      window.__wd.lcp.push({t: e.startTime, el: el, url: e.url || ''});
    }
  }).observe({type: 'largest-contentful-paint', buffered: true}));
  add(() => new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (!e.hadRecentInput) { window.__wd.cls += e.value; window.__wd.shifts += 1; }
    }
  }).observe({type: 'layout-shift', buffered: true}));
  add(() => new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (e.duration > 50) window.__wd.longtasks.push({start: e.startTime, duration: e.duration});
    }
  }).observe({type: 'longtask', buffered: true}));
  add(() => new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (e.name === 'first-contentful-paint') window.__wd.fcp = e.startTime;
    }
  }).observe({type: 'paint', buffered: true}));
  add(() => new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (e.interactionId) window.__wd.events.push({duration: e.duration, name: e.name});
    }
  }).observe({type: 'event', buffered: true, durationThreshold: 16}));
})();
"""

_NAV_JS = r"""
() => {
  const n = performance.getEntriesByType('navigation')[0] || {};
  return {
    ttfb: Math.max(0, (n.responseStart || 0) - (n.startTime || 0)),
    dcl: Math.max(0, n.domContentLoadedEventEnd || 0),
    load: Math.max(0, n.loadEventEnd || 0),
  };
}
"""

_RENDER_BLOCKING_JS = r"""
() => [...document.querySelectorAll(
  'head link[rel="stylesheet"][href]:not([media="print"]), head script[src]:not([async]):not([defer]):not([type="module"])'
)].map(el => el.href || el.src).filter(Boolean).slice(0, 30)
"""

_IMAGES_JS = r"""
() => {
  const images = [...document.images].slice(0, 300);
  let missingDimensions = 0;
  let oversized = 0;
  let nextGen = 0;
  for (const img of images) {
    if (!img.getAttribute('width') || !img.getAttribute('height')) missingDimensions++;
    const dw = img.clientWidth || 0;
    const nw = img.naturalWidth || 0;
    if (dw > 0 && nw > 1200 && nw > dw * 1.5) oversized++;
    const src = (img.currentSrc || img.src || '').toLowerCase().split('?')[0];
    if (src.endsWith('.webp') || src.endsWith('.avif')) nextGen++;
  }
  return {total: images.length, missing_dimensions: missingDimensions, oversized: oversized, next_gen: nextGen};
}
"""


class PerfCancelled(RuntimeError):
    pass


class PerfError(RuntimeError):
    pass


def _check(is_cancelled) -> None:
    if is_cancelled and is_cancelled():
        raise PerfCancelled("Performance test cancelled")


def _report(progress, pct: int, key: str) -> None:
    if progress:
        progress(pct, key)


def _median(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 3) if values else None


def _site_key(host: str) -> str:
    parts = [p for p in (host or "").lower().split(".") if p]
    if len(parts) >= 3 and parts[-2] in ("co", "com", "net", "org", "gov", "ac"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else "")


def _headers_lower(headers: dict) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (headers or {}).items()}


def _metric_status(value: float, good: float, needs: float) -> int:
    if value <= good:
        return 0
    if value <= needs:
        return 1
    return 2


def _issues(metrics: PerfMetrics, resources: list[ResourceInfo], third_parties: list[dict],
            render_blocking: list[str], images: dict, page_bytes: int, requests: int) -> list[PerfIssue]:
    issues: list[PerfIssue] = []
    if metrics.lcp_ms > 2500:
        issues.append(PerfIssue("perf.lcp_slow", "high" if metrics.lcp_ms > 4000 else "medium",
                                {"ms": metrics.lcp_ms}))
    if metrics.cls > 0.1:
        issues.append(PerfIssue("perf.cls_high", "high" if metrics.cls > 0.25 else "medium",
                                {"cls": round(metrics.cls, 3)}))
    if metrics.tbt_ms > 200:
        issues.append(PerfIssue("perf.tbt_high", "high" if metrics.tbt_ms > 600 else "medium",
                                {"ms": metrics.tbt_ms}))
    if metrics.ttfb_ms > 800:
        issues.append(PerfIssue("perf.ttfb_slow", "high" if metrics.ttfb_ms > 1800 else "medium",
                                {"ms": metrics.ttfb_ms}))
    if metrics.fcp_ms > 1800:
        issues.append(PerfIssue("perf.fcp_slow", "medium" if metrics.fcp_ms > 3000 else "low",
                                {"ms": metrics.fcp_ms}))
    if metrics.inp_ms is not None and metrics.inp_ms > 500:
        issues.append(PerfIssue("perf.inp_lab", "low", {"ms": metrics.inp_ms}))
    if page_bytes > 2 * 1024 * 1024:
        issues.append(PerfIssue("perf.page_weight", "medium", {"mb": round(page_bytes / 1024 / 1024, 2)}))
    if requests > 50:
        issues.append(PerfIssue("perf.requests_high", "medium" if requests > 100 else "low",
                                {"count": requests}))
    if render_blocking:
        issues.append(PerfIssue("perf.render_blocking", "medium", {"count": len(render_blocking)},
                                "\n".join(render_blocking[:5])))
    if len(third_parties) > 5:
        issues.append(PerfIssue("perf.third_party", "medium" if len(third_parties) > 10 else "low",
                                {"count": len(third_parties)},
                                ", ".join(item["host"] for item in third_parties[:6])))
    if images.get("oversized"):
        issues.append(PerfIssue("perf.oversized_images", "medium", {"count": images["oversized"]}))
    if images.get("missing_dimensions"):
        issues.append(PerfIssue("perf.image_dimensions", "low", {"count": images["missing_dimensions"]}))
    slow = [r for r in resources if r.duration_ms > 1000 and r.kind in ("Document", "Script", "Stylesheet", "Image", "Font")]
    if slow:
        worst = max(slow, key=lambda r: r.duration_ms)
        issues.append(PerfIssue("perf.slow_resource", "low",
                                {"url": worst.url[:180], "ms": worst.duration_ms},
                                f"{worst.url} ({worst.duration_ms} ms, {worst.bytes} bytes)"))
    uncompressed = [r for r in resources if r.kind in ("Document", "Script", "Stylesheet", "XHR", "Fetch")
                    and r.status < 400 and r.bytes > 1024 and not r.content_encoding]
    if uncompressed:
        issues.append(PerfIssue("perf.no_compression", "low", {"count": len(uncompressed)},
                                "\n".join(r.url for r in uncompressed[:5])))
    uncached = [r for r in resources if r.kind in ("Script", "Stylesheet", "Image", "Font")
                and r.status == 200 and r.bytes > 20_000 and not r.cache_control]
    if uncached:
        issues.append(PerfIssue("perf.no_cache", "low", {"count": len(uncached)},
                                "\n".join(r.url for r in uncached[:5])))
    return issues


def _score(metrics: PerfMetrics, issues: list[PerfIssue], page_bytes: int, requests: int,
           third_parties: list[dict], render_blocking: list[str], images: dict) -> int:
    score = 100
    if metrics.lcp_ms:
        score -= (0, 10, 25)[_metric_status(metrics.lcp_ms, 2500, 4000)]
    if metrics.cls:
        score -= (0, 8, 16)[_metric_status(metrics.cls, 0.1, 0.25)]
    if metrics.tbt_ms:
        score -= (0, 8, 18)[_metric_status(metrics.tbt_ms, 200, 600)]
    if metrics.ttfb_ms:
        score -= (0, 5, 10)[_metric_status(metrics.ttfb_ms, 800, 1800)]
    if metrics.fcp_ms:
        score -= (0, 3, 7)[_metric_status(metrics.fcp_ms, 1800, 3000)]
    if metrics.inp_ms is not None and metrics.inp_ms > 500:
        score -= 4
    if page_bytes > 5 * 1024 * 1024:
        score -= 10
    elif page_bytes > 2 * 1024 * 1024:
        score -= 5
    if requests > 100:
        score -= 8
    elif requests > 50:
        score -= 4
    if render_blocking:
        score -= 5
    if len(third_parties) > 10:
        score -= 8
    elif len(third_parties) > 5:
        score -= 4
    if images.get("oversized"):
        score -= 4
    if any(issue.code == "perf.no_compression" for issue in issues):
        score -= 3
    if any(issue.code == "perf.no_cache" for issue in issues):
        score -= 2
    if any(issue.code == "perf.slow_resource" for issue in issues):
        score -= 3
    return max(0, min(100, score))


def run_perf(url: str, *, device: str = "mobile", runs: int = 3, timeout: float = 45.0,
             progress=None, is_cancelled=None) -> PerfResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PerfError("Playwright is not installed. Install it to run speed tests.") from exc

    profile = DEVICES.get(device) or DEVICES["mobile"]
    started = time.monotonic()
    run_metrics: list[dict] = []
    last_resources: list[ResourceInfo] = []
    last_third: list[dict] = []
    last_render_blocking: list[str] = []
    last_images: dict = {}
    last_final = url
    last_lcp_element = ""
    notes: list[str] = []
    browser_label = ""

    _report(progress, 3, "Starting headless Chromium")
    try:
        with sync_playwright() as playwright:
            browser, choice = launch(playwright, headless=True)
            browser_label = choice.describe()
            try:
                for index in range(max(1, min(5, runs))):
                    _check(is_cancelled)
                    _report(progress, 8 + int(84 * index / max(1, runs)), f"Run {index + 1}/{runs}")
                    context = browser.new_context(
                        viewport=profile["viewport"],
                        device_scale_factor=profile["dpr"],
                        is_mobile=profile["mobile"],
                        has_touch=profile["touch"],
                        locale="en-US",
                        ignore_https_errors=True,
                    )
                    page = context.new_page()
                    cdp = context.new_cdp_session(page)
                    requests: dict[str, dict] = {}
                    responses: dict[str, dict] = {}
                    finished: dict[str, dict] = {}

                    def on_request(event):
                        requests[event.get("requestId")] = {
                            "url": (event.get("request") or {}).get("url", ""),
                            "type": event.get("type", "Other"),
                            "start": event.get("timestamp", 0),
                        }

                    def on_response(event):
                        response = event.get("response") or {}
                        responses[event.get("requestId")] = {
                            "status": response.get("status", 0),
                            "headers": response.get("headers") or {},
                        }

                    def on_finished(event):
                        finished[event.get("requestId")] = {
                            "end": event.get("timestamp", 0),
                            "bytes": event.get("encodedDataLength", 0),
                        }

                    cdp.send("Network.enable")
                    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                    cdp.send("Network.emulateNetworkConditions", {
                        "offline": False,
                        "latency": profile["latency"],
                        "downloadThroughput": profile["download"],
                        "uploadThroughput": profile["upload"],
                    })
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": profile["cpu"]})
                    cdp.on("Network.requestWillBeSent", on_request)
                    cdp.on("Network.responseReceived", on_response)
                    cdp.on("Network.loadingFinished", on_finished)
                    page.add_init_script(_INIT)
                    navigated = True
                    try:
                        page.goto(url, wait_until="load", timeout=int(timeout * 1000))
                    except Exception as exc:  # noqa: BLE001 - partial loads still tell us something
                        navigated = False
                        notes.append(str(exc).splitlines()[0][:200])
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1600)
                    try:
                        page.keyboard.press("Tab")
                    except Exception:
                        pass
                    page.wait_for_timeout(300)
                    data = page.evaluate("window.__wd")
                    nav = page.evaluate(_NAV_JS)
                    render_blocking = page.evaluate(_RENDER_BLOCKING_JS) or []
                    images = page.evaluate(_IMAGES_JS) or {}
                    last_final = page.url or url
                    _check(is_cancelled)

                    fcp = float(data.get("fcp") or 0)
                    tasks = data.get("longtasks") or []
                    tbt = sum(max(0.0, float(task.get("duration", 0)) - 50) for task in tasks
                              if float(task.get("start", 0)) >= fcp)
                    lcp_entries = data.get("lcp") or []
                    lcp = max((float(entry.get("t") or 0) for entry in lcp_entries), default=0)
                    if lcp_entries:
                        best = max(lcp_entries, key=lambda entry: float(entry.get("t") or 0))
                        last_lcp_element = str(best.get("el") or "")
                    events = data.get("events") or []
                    inp = round(max((float(e.get("duration") or 0) for e in events), default=0), 1) if events else None
                    metrics = {
                        "ttfb_ms": int(nav.get("ttfb") or 0),
                        "fcp_ms": int(fcp),
                        "lcp_ms": int(lcp),
                        "cls": round(float(data.get("cls") or 0), 4),
                        "tbt_ms": int(tbt),
                        "inp_ms": inp,
                        "dcl_ms": int(nav.get("dcl") or 0),
                        "load_ms": int(nav.get("load") or 0),
                        "navigated": navigated,
                    }
                    resources = _resources(requests, responses, finished, last_final)
                    third = _third_parties(resources, last_final)
                    run_metrics.append(metrics)
                    last_resources = resources
                    last_third = third
                    last_render_blocking = render_blocking
                    last_images = images
                    context.close()
            finally:
                browser.close()
    except PerfCancelled:
        raise
    except PerfError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PerfError(f"Speed test failed: {str(exc).splitlines()[0]}") from exc

    successful = [m for m in run_metrics if m.get("navigated")]
    if not successful:
        raise PerfError("The page did not load in headless Chromium. " + (" ".join(notes)[:300]))
    metrics = PerfMetrics(
        ttfb_ms=int(_median([m["ttfb_ms"] for m in successful]) or 0),
        fcp_ms=int(_median([m["fcp_ms"] for m in successful]) or 0),
        lcp_ms=int(_median([m["lcp_ms"] for m in successful]) or 0),
        cls=float(_median([m["cls"] for m in successful]) or 0),
        tbt_ms=int(_median([m["tbt_ms"] for m in successful]) or 0),
        inp_ms=(int(_median([m["inp_ms"] for m in successful if m.get("inp_ms") is not None]))
                if any(m.get("inp_ms") is not None for m in successful) else None),
        dcl_ms=int(_median([m["dcl_ms"] for m in successful]) or 0),
        load_ms=int(_median([m["load_ms"] for m in successful]) or 0),
    )
    requests_count = len([r for r in last_resources if r.url])
    page_bytes = sum(r.bytes for r in last_resources)
    issues = _issues(metrics, last_resources, last_third, last_render_blocking, last_images, page_bytes, requests_count)
    score = _score(metrics, issues, page_bytes, requests_count, last_third, last_render_blocking, last_images)
    _report(progress, 100, "Done")
    return PerfResult(
        url=url,
        final_url=last_final,
        device=device,
        network=profile["label"],
        runs=len(successful),
        score=score,
        grade=perf_grade(score),
        metrics=metrics,
        issues=issues,
        resources=sorted(last_resources, key=lambda r: r.bytes, reverse=True)[:15],
        requests=requests_count,
        bytes=page_bytes,
        third_parties=last_third[:12],
        render_blocking=last_render_blocking,
        images=last_images,
        lcp_element=last_lcp_element,
        timestamp=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        duration_ms=int((time.monotonic() - started) * 1000),
        browser=browser_label,
        note=" ".join(notes)[:500],
        raw_runs=run_metrics,
    )


def _resources(requests: dict[str, dict], responses: dict[str, dict], finished: dict[str, dict],
               final_url: str) -> list[ResourceInfo]:
    target = _site_key((urlsplit(final_url).hostname or "").lower())
    out: list[ResourceInfo] = []
    for request_id, request in requests.items():
        url = str(request.get("url") or "")
        if not url or url.startswith(("data:", "blob:", "about:")):
            continue
        done = finished.get(request_id) or {}
        response = responses.get(request_id) or {}
        headers = _headers_lower(response.get("headers") or {})
        start = float(request.get("start") or 0)
        end = float(done.get("end") or 0)
        duration = int(max(0, (end - start) * 1000)) if end >= start else 0
        host = (urlsplit(url).hostname or "").lower()
        out.append(ResourceInfo(
            url=url,
            kind=str(request.get("type") or "Other"),
            status=int(response.get("status") or 0),
            bytes=int(done.get("bytes") or 0),
            duration_ms=duration,
            third_party=bool(target and _site_key(host) != target),
            cache_control=headers.get("cache-control", ""),
            content_encoding=headers.get("content-encoding", ""),
        ))
    return out


def _third_parties(resources: list[ResourceInfo], final_url: str) -> list[dict]:
    groups: dict[str, dict] = {}
    for resource in resources:
        if not resource.third_party:
            continue
        host = (urlsplit(resource.url).hostname or "").lower()
        item = groups.setdefault(host, {"host": host, "count": 0, "bytes": 0})
        item["count"] += 1
        item["bytes"] += resource.bytes
    return sorted(groups.values(), key=lambda item: item["bytes"], reverse=True)
