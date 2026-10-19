"""ReadyPack — packaging, not a checker.

ReadyPack takes a dataset plus any number of findings reports produced by the
other tools (EnrichAudit, LinguaCheck, SourceLock, WhyChanged, NuanceBench,
FilterGap, DecayWatch) and turns them into a documented, publishable pack: a
data-health score, a datasheet, Croissant metadata, a changelog, and a
human-readable report.

Nothing is ever silently deleted. Rows only leave the packaged export when the
caller hands over explicit ids for review-approved removals, and every action
is written to the changelog.

The headline number is a 0-100 data-health score: log-scaled finding penalties
(high=6, medium=3, low=1), so the first issues cost the most and a long tail of
minor notes can't sink an otherwise good dataset. It is deterministic.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from readypack.common import ToolResult, as_str, find_id, opt_dict, opt_list
from readypack.export import build_croissant, build_datasheet, build_report_md

HEALTH_WEIGHTS = {"high": 6.0, "medium": 3.0, "low": 1.0}

REVIEW_WARNING = "Review every finding before publishing — ReadyPack never silently deletes rows."


def health_score(findings: list[dict]) -> tuple[float, str]:
    """Composite 0-100 score plus letter grade from finding severities."""
    raw = sum(HEALTH_WEIGHTS.get(str(f.get("severity", "low")).lower(), 1.0) for f in findings)
    score = round(100 - min(100.0, 25 * math.log10(1 + raw)), 1)
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"
    return score, grade


class ReadyPackLogic:
    """Packaging orchestrator: aggregate findings, score, document, package."""

    def run(self, rows: list[dict], options: dict[str, Any]) -> ToolResult:
        name = as_str(options.get("name") or options.get("dataset_name")) or "dataset"
        description = as_str(options.get("description"))
        reports = [r for r in (options.get("reports") or []) if isinstance(r, dict)]
        drop_ids = {as_str(x) for x in opt_list(options.get("drop_ids")) if as_str(x)}

        findings: list[dict] = []
        warnings: list[str] = [REVIEW_WARNING]
        sources: dict[str, dict] = {}
        for report in reports:
            tool = as_str(report.get("tool") or report.get("name")) or "audit"
            audit_findings = [f for f in (report.get("findings") or []) if isinstance(f, dict)]
            for finding in audit_findings:
                tagged = dict(finding)
                meta = dict(finding.get("metadata") or {})
                meta["audit"] = tool
                tagged["metadata"] = meta
                findings.append(tagged)
            score, grade = health_score(audit_findings)
            source_warnings = [as_str(w) for w in (report.get("warnings") or []) if as_str(w)]
            sources[tool] = {
                "findings": len(audit_findings),
                "by_severity": _severity_counts(audit_findings),
                "score": score,
                "grade": grade,
                "warnings": len(source_warnings),
            }
            for warning in source_warnings[:2]:
                warnings.append(f"{tool}: {warning}")

        score, grade = health_score(findings)
        fields = [str(k) for k in (rows[0].keys() if rows else [])]
        kept_rows = [r for r in rows if _row_id(r) not in drop_ids]
        dropped = [rid for rid in (as_str(_row_id(r)) for r in rows) if rid in drop_ids]

        total_raw = round(
            sum(HEALTH_WEIGHTS.get(str(f.get("severity", "low")), 1.0) for f in findings), 1
        )
        health = {
            "score": score,
            "grade": grade,
            "weights": HEALTH_WEIGHTS,
            "raw_penalty": total_raw,
            "per_source": {tool: {"score": s["score"], "grade": s["grade"]} for tool, s in sources.items()},
        }

        changelog = [*opt_list(options.get("changelog")), {
            "at": datetime.now(UTC).isoformat(),
            "actor": "readypack",
            "event": f"Packaged {len(kept_rows)} row(s); {len(dropped)} row(s) dropped per reviewed ids; "
                     f"{len(findings)} finding(s) from {len(sources)} source(s).",
        }]

        datasheet = build_datasheet(
            name=name,
            description=description,
            fields=fields,
            row_count=len(kept_rows),
            original_count=len(rows),
            sources=sources,
            warnings=warnings,
        )
        croissant = build_croissant(
            name=name,
            description=description,
            fields=fields,
            row_count=len(kept_rows),
            datasheet=datasheet,
        )
        report_md = build_report_md(
            name=name,
            health=health,
            sources=sources,
            kept=len(kept_rows),
            dropped=len(dropped),
            findings=len(findings),
        )

        summary: dict[str, Any] = {
            "checked": len(rows),
            "name": name,
            "dataset": {
                "fields": fields,
                "row_count": len(kept_rows),
                "original_row_count": len(rows),
            },
            "sources": sources,
            "findings_total": len(findings),
            "health_score": health,
            "drop_count": len(dropped),
            "dropped_ids": sorted(set(dropped)),
            "datasheet": datasheet,
            "croissant": croissant,
            "report_md": report_md,
            "changelog": changelog,
        }
        return ToolResult(status="success", findings=findings, warnings=warnings, summary=summary)


def _severity_counts(findings: list[dict]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        severity = str(finding.get("severity", "low")).lower()
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _row_id(row: dict) -> str | None:
    value = find_id(row)
    return as_str(value) or None


def run(rows: list[dict], options: dict[str, Any] | None = None) -> ToolResult:
    return ReadyPackLogic().run(rows, options or {})
