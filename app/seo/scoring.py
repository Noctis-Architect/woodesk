from __future__ import annotations

from .models import (CATEGORY_ORDER, CATEGORY_WEIGHTS, SEVERITY_ORDER, SKIP, AuditResult, CategoryScore,
                     Issue, PageFacts, grade_for)
from .rules import Failure, Rule


def evaluate(facts: PageFacts, results: list[tuple[Rule, Failure | None | object]],
             page_url: str = "") -> tuple[list[Issue], list[CategoryScore], int, str]:
    totals: dict[str, dict[str, int]] = {}
    issues: list[Issue] = []
    for rule, outcome in results:
        if outcome is SKIP:
            bucket = totals.setdefault(rule.category, {"total": 0, "failed": 0, "passed": 0, "skipped": 0})
            bucket["skipped"] += 1
            continue
        bucket = totals.setdefault(rule.category, {"total": 0, "failed": 0, "passed": 0, "skipped": 0})
        bucket["total"] += rule.weight
        if outcome is None:
            bucket["passed"] += 1
            continue
        failure = outcome if isinstance(outcome, Failure) else Failure()
        bucket["failed"] += rule.weight
        issues.append(Issue(
            code=rule.code,
            category=rule.category,
            severity=rule.severity,
            data=failure.data,
            evidence=failure.evidence,
            page=page_url or facts.final_url or facts.url,
        ))

    categories: list[CategoryScore] = []
    weighted = 0.0
    weight_sum = 0.0
    for category in CATEGORY_ORDER:
        bucket = totals.get(category)
        if not bucket or not bucket["total"]:
            continue
        score = round(100 * (bucket["total"] - bucket["failed"]) / bucket["total"])
        categories.append(CategoryScore(
            category=category,
            score=max(0, min(100, score)),
            passed=bucket["passed"],
            failed=bucket["failed"],
            skipped=bucket["skipped"],
            total=bucket["passed"] + bucket["failed"],
        ))
        weight = CATEGORY_WEIGHTS.get(category, 0)
        weighted += score * weight
        weight_sum += weight
    overall = round(weighted / weight_sum) if weight_sum else 100
    overall = max(0, min(100, overall))
    if any(issue.severity == "critical" for issue in issues):
        overall = min(overall, 50)
    issues.sort(key=lambda issue: (SEVERITY_ORDER.get(issue.severity, 9), CATEGORY_ORDER.index(issue.category)
                                   if issue.category in CATEGORY_ORDER else 99, issue.code))
    return issues, categories, overall, grade_for(overall)


def finish_result(result: AuditResult) -> AuditResult:
    return result


def score_color(score: int) -> str:
    if score >= 80:
        return "success"
    if score >= 60:
        return "warning"
    return "danger"
