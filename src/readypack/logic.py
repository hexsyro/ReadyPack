"""ReadyPack — packaging, not a checker.

ReadyPack takes a dataset plus any number of findings reports produced by the
other tools (EnrichAudit, LinguaCheck, SourceLock, WhyChanged, NuanceBench,
FilterGap, DecayWatch) and turns them into a documented, publishable pack: a
data-health score, a datasheet, Croissant 1.1 metadata, a changelog, and a
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
from datetime import datetime, timezone
from typing import Any

from readypack.common import (
    RESULT_SCHEMA_VERSION,
    ToolResult,
    all_fields,
    as_str,
    find_id,
    opt_dict,
    opt_items,
    opt_list,
    opt_str,
)
from readypack.export import (
    build_croissant,
    build_dataset_jsonld,
    build_datasheet,
    build_datasheet_json,
    build_findings_json,
    build_report_md,
)

HEALTH_WEIGHTS = {"high": 6.0, "medium": 3.0, "low": 1.0}
REVIEW_WARNING = "Review every finding before publishing — ReadyPack never silently deletes rows."


def _penalty(findings: list[dict]) -> float:
    """Raw severity penalty, with uppercase severities normalized."""
    return round(sum(HEALTH_WEIGHTS.get(str(f.get("severity", "low")).lower(), 1.0) for f in findings), 1)


def health_score(findings: list[dict]) -> tuple[float, str]:
    """Composite 0-100 score plus letter grade from finding severities."""
    raw = _penalty(findings)
    score = round(100 - min(100.0, 25 * math.log10(1 + raw)), 1)
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"
    return score, grade


class ReadyPackLogic:
    """Packaging orchestrator: aggregate findings, score, document, package."""

    def run(self, rows: list[dict], options: dict[str, Any]) -> ToolResult:
        try:
            rows = [row for row in list(rows) if isinstance(row, dict)]
        except TypeError:
            rows = []
        options = opt_dict(options)

        name = opt_str(options.get("name") or options.get("dataset_name")) or "dataset"
        description = opt_str(options.get("description"))
        version_tag = opt_str(options.get("version_tag")) or "0.2.0"
        reports_value = options.get("reports")
        if isinstance(reports_value, dict):
            reports = [reports_value]
        elif isinstance(reports_value, (list, tuple)):
            reports = [r for r in reports_value if isinstance(r, dict)]
        else:
            reports = []
        drop_ids = {opt_str(x) for x in opt_list(options.get("drop_ids")) if opt_str(x)}

        findings: list[dict] = []
        warnings: list[str] = [REVIEW_WARNING]
        sources: dict[str, dict] = {}
        report_warning_count = 0
        used_tools: set[str] = set()
        for report in reports:
            base_tool = opt_str(report.get("tool") or report.get("name")) or "audit"
            tool = base_tool
            suffix = 2
            while tool in used_tools:
                tool = f"{base_tool}_{suffix}"
                suffix += 1
            used_tools.add(tool)
            if tool != base_tool:
                warnings.append(f"Duplicate audit tool name {base_tool!r}; recorded as {tool!r}.")

            audit_findings = [f for f in opt_items(report.get("findings")) if isinstance(f, dict)]
            for finding in audit_findings:
                tagged = dict(finding)
                meta = opt_dict(finding.get("metadata"))
                meta["audit"] = tool
                tagged["metadata"] = meta
                findings.append(tagged)
            score, grade = health_score(audit_findings)
            source_warnings = [opt_str(w) for w in opt_items(report.get("warnings")) if opt_str(w)]
            report_warning_count += len(source_warnings)
            status = opt_str(report.get("status")) or "success"
            sources[tool] = {
                "tool": tool,
                "version": opt_str(report.get("version")),
                "status": status,
                "findings": len(audit_findings),
                "by_severity": _severity_counts(audit_findings),
                "penalty": _penalty(audit_findings),
                "score": score,
                "grade": grade,
                "warnings": len(source_warnings),
            }
            for warning in source_warnings:
                warnings.append(f"{tool}: {warning}")

        score, grade = health_score(findings)
        fields = all_fields(rows)
        row_ids = [_row_id(row) for row in rows]
        known_ids = {rid for rid in row_ids if rid}
        unknown = sorted(drop_ids - known_ids)
        if unknown:
            shown = ", ".join(unknown[:10])
            extra = f" (and {len(unknown) - 10} more)" if len(unknown) > 10 else ""
            warnings.append(f"Unknown drop ids ignored: {shown}{extra}.")
        kept_rows = [row for row, rid in zip(rows, row_ids, strict=True) if rid not in drop_ids]
        dropped = [rid for rid in row_ids if rid in drop_ids]

        confidence = (
            "low"
            if any(s["status"] == "error" for s in sources.values())
            else "medium"
            if report_warning_count
            else "high"
        )
        health = {
            "score": score,
            "grade": grade,
            "weights": HEALTH_WEIGHTS,
            "raw_penalty": _penalty(findings),
            "per_source": {tool: {"score": s["score"], "grade": s["grade"]} for tool, s in sources.items()},
        }
        health_detail = {
            "components": {
                tool: {"findings": s["findings"], "penalty": s["penalty"], "score": s["score"]}
                for tool, s in sources.items()
            },
            "weights": {key: int(value) for key, value in HEALTH_WEIGHTS.items()},
            "confidence": confidence,
        }

        generated_at = datetime.now(timezone.utc).isoformat()
        changelog = [*opt_items(options.get("changelog"))]
        for rid in sorted(set(dropped)):
            changelog.append(
                {
                    "at": generated_at,
                    "actor": "readypack",
                    "event": f"Removed row {rid!r} per reviewed drop id.",
                }
            )
        changelog.append(
            {
                "at": generated_at,
                "actor": "readypack",
                "event": f"Packaged {len(kept_rows)} row(s); {len(dropped)} row(s) dropped per reviewed ids; "
                f"{len(findings)} finding(s) from {len(sources)} source(s).",
            }
        )

        datasheet = build_datasheet(
            name=name,
            description=description,
            fields=fields,
            row_count=len(kept_rows),
            original_count=len(rows),
            sources=sources,
            warnings=warnings,
        )
        provenance = [_provenance_record(source) for source in sources.values()]
        croissant = build_croissant(
            name=name,
            description=description,
            fields=fields,
            row_count=len(kept_rows),
            datasheet=datasheet,
            version_tag=version_tag,
            generated_at=generated_at,
            sample_rows=rows,
            provenance=provenance,
        )
        datasheet_json = build_datasheet_json(
            name=name,
            description=description,
            fields=fields,
            row_count=len(kept_rows),
            original_count=len(rows),
            sources=sources,
            warnings=warnings,
            dropped_ids=sorted(set(dropped)),
            unknown_drop_ids=unknown,
            version=version_tag,
            generated_at=generated_at,
        )
        dataset_jsonld = build_dataset_jsonld(
            name=name,
            description=description,
            fields=fields,
            row_count=len(kept_rows),
            version=version_tag,
            generated_at=generated_at,
            sources=sources,
        )
        findings_json = build_findings_json(findings)
        fair = _fair_assessment(croissant, datasheet)
        report_md = build_report_md(
            name=name,
            health=health,
            sources=sources,
            kept=len(kept_rows),
            dropped=len(dropped),
            findings=len(findings),
            fair=fair,
        )

        summary: dict[str, Any] = {
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "skipped": False,
            "skip_reason": None,
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
            "health_score_detail": health_detail,
            "drop_count": len(dropped),
            "dropped_ids": sorted(set(dropped)),
            "unknown_drop_ids": unknown,
            "datasheet": datasheet,
            "datasheet_json": datasheet_json,
            "croissant": croissant,
            "dataset_jsonld": dataset_jsonld,
            "findings_json": findings_json,
            "report_md": report_md,
            "fair_assessment": fair,
            "provenance": provenance,
            "changelog": changelog,
        }
        return ToolResult(status="success", findings=findings, warnings=warnings, summary=summary)


def _provenance_record(source: dict) -> dict:
    """PROV-O-style record describing one contributing audit report."""
    return {
        "tool": source.get("tool", ""),
        "version": source.get("version", ""),
        "status": source.get("status", "success"),
        "findings": source.get("findings", 0),
    }


def _fair_assessment(croissant: dict, datasheet: str) -> dict[str, dict]:
    """Small, honest FAIR self-assessment; every rating cites its evidence."""
    distribution = croissant.get("distribution") or []
    return {
        "F": {
            "status": "pass" if croissant.get("name") and croissant.get("recordSet") else "partial",
            "fields": "summary.croissant.name, summary.croissant.recordSet, summary.dataset.fields",
        },
        "A": {
            "status": "pass" if distribution else "fail",
            "fields": "summary.croissant.distribution[].contentUrl, package.zip",
        },
        "I": {
            "status": "pass" if croissant.get("dct:conformsTo") else "partial",
            "fields": "summary.croissant.dct:conformsTo, summary.dataset_jsonld",
        },
        "R": {
            "status": "pass"
            if croissant.get("wasGeneratedBy") and croissant.get("license") and datasheet
            else "partial"
            if datasheet
            else "fail",
            "fields": "summary.datasheet, summary.croissant.wasGeneratedBy, summary.croissant.license",
        },
    }


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
