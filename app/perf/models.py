from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PerfIssue:
    code: str
    severity: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: str = ""


@dataclass
class ResourceInfo:
    url: str = ""
    kind: str = ""
    status: int = 0
    bytes: int = 0
    duration_ms: int = 0
    third_party: bool = False
    cache_control: str = ""
    content_encoding: str = ""


@dataclass
class PerfMetrics:
    ttfb_ms: int = 0
    fcp_ms: int = 0
    lcp_ms: int = 0
    cls: float = 0.0
    tbt_ms: int = 0
    inp_ms: int | None = None
    dcl_ms: int = 0
    load_ms: int = 0


@dataclass
class PerfResult:
    url: str
    final_url: str
    device: str
    network: str
    runs: int
    score: int
    grade: str
    metrics: PerfMetrics
    issues: list[PerfIssue]
    resources: list[ResourceInfo]
    requests: int = 0
    bytes: int = 0
    third_parties: list[dict[str, Any]] = field(default_factory=list)
    render_blocking: list[str] = field(default_factory=list)
    images: dict[str, Any] = field(default_factory=dict)
    lcp_element: str = ""
    timestamp: str = ""
    duration_ms: int = 0
    browser: str = ""
    note: str = ""
    raw_runs: list[dict[str, Any]] = field(default_factory=list)


def perf_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "E"
