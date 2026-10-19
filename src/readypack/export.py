"""ReadyPack export step: package a dataset with its documentation.

Unlike the checker tools, ReadyPack's output is a downloadable pack: a cleaned
CSV plus a datasheet, Croissant metadata, a changelog, and a human-readable
report, all zipped together. The pure builders here (datasheet, Croissant,
report) are also used by ``logic.py`` so the summary carries the exact text
that gets written.
"""

from __future__ import annotations

import csv
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from readypack.common import as_str, find_id, safe_cell


def build_croissant(*, name: str, description: str, fields: list[str],
                    row_count: int, datasheet: str = "") -> dict:
    """Minimal Croissant metadata (mlcommons) for a packaged dataset."""
    return {
        "@context": {"@vocab": "https://schema.org/", "croissant": "https://mlcommons.org/croissant/"},
        "@type": "sc:Dataset",
        "name": name,
        "description": description or "Dataset packaged by ReadyPack.",
        "version": "1.0.0",
        "datePublished": datetime.now(UTC).date().isoformat(),
        "recordSet": [{
            "@type": "croissant:RecordSet",
            "name": "records",
            "description": datasheet[:500] if datasheet else "Packaged records.",
            "field": [{"name": f, "dataType": "sc:Text"} for f in fields],
            "data": [{"recordCount": row_count}],
        }],
        "distribution": [{
            "@type": "sc:FileObject",
            "name": "cleaned.csv",
            "contentUrl": "cleaned.csv",
            "encodingFormat": "text/csv",
        }],
    }


def build_datasheet(*, name: str, description: str, fields: list[str], row_count: int,
                    original_count: int, sources: dict[str, dict], warnings: list[str]) -> str:
    """Markdown datasheet (dataset card) for the packaged dataset."""
    lines = [
        f"# Datasheet: {name}",
        "",
        description or "No description provided.",
        "",
        "## Composition",
        "",
        f"- Rows packaged: {row_count} of {original_count} original row(s).",
        f"- Fields ({len(fields)}): {', '.join(fields) if fields else '—'}.",
        "",
        "## Audits",
        "",
    ]
    if sources:
        lines.append("| Tool | Findings | Health | Grade | High | Medium | Low |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for tool, info in sources.items():
            sev = info.get("by_severity", {})
            lines.append(
                f"| {tool} | {info.get('findings', 0)} | {info.get('score', '?')} | "
                f"{info.get('grade', '?')} | {sev.get('high', 0)} | {sev.get('medium', 0)} | "
                f"{sev.get('low', 0)} |"
            )
    else:
        lines.append("No audit reports were supplied — this pack documents the dataset but carries no findings.")
    lines += ["", "## Known limitations", ""]
    if warnings:
        lines += [f"- {w}" for w in warnings]
    else:
        lines.append("- None recorded.")
    lines += [
        "",
        "## Use",
        "",
        "Findings above are signals, not verdicts. Review each one before publishing; "
        "this pack was generated without silently changing the data beyond any "
        "explicitly reviewed removals.",
        "",
    ]
    return "\n".join(lines)


def build_report_md(*, name: str, health: dict, sources: dict[str, dict],
                    kept: int, dropped: int, findings: int) -> str:
    """Human-readable package report."""
    lines = [
        f"# ReadyPack report: {name}",
        "",
        f"Data-health score: {health.get('score')} ({health.get('grade')}).",
        f"Rows packaged: {kept} ({dropped} removed by reviewed ids). "
        f"{findings} finding(s) from {len(sources)} source(s).",
        "",
        "## Sources",
    ]
    if sources:
        for tool, info in sources.items():
            sev = info.get("by_severity", {})
            lines.append(
                f"- {tool}: {info.get('findings', 0)} finding(s) "
                f"(high {sev.get('high', 0)}, medium {sev.get('medium', 0)}, low {sev.get('low', 0)}), "
                f"health {info.get('score', '?')} ({info.get('grade', '?')})"
            )
    else:
        lines.append("- No audit reports supplied.")
    lines += [
        "",
        "## What gets packaged",
        "",
        "- cleaned.csv — the dataset, minus any explicitly reviewed removals.",
        "- datasheet.md — this dataset card.",
        "- croissant.json — Croissant (mlcommons) metadata.",
        "- changelog.json — the action history.",
        "- report.md — this file.",
        "",
        "Nothing was deleted without review. See changelog.json for the full history.",
    ]
    return "\n".join(lines)


def write_package(out_dir: str | Path, *, rows: list[dict], summary: dict,
                  drop_ids: list[str] | None = None) -> Path:
    """Write cleaned.csv + docs into ``out_dir`` and zip them into package.zip."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    dropped = {as_str(x) for x in (drop_ids or [])}

    fields = [str(k) for k in (rows[0].keys() if rows else [])]
    kept = [row for row in rows if _row_id(row) not in dropped]

    cleaned_path = root / "cleaned.csv"
    with open(cleaned_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["_empty"])
        writer.writeheader()
        for row in kept:
            writer.writerow({name: safe_cell(row.get(name, "")) for name in writer.fieldnames or []})

    members: dict[str, str] = {
        "datasheet.md": as_str(summary.get("datasheet")) or f"# Datasheet: {summary.get('name', 'dataset')}\n",
        "croissant.json": json.dumps(summary.get("croissant") or {}, indent=2),
        "changelog.json": json.dumps(summary.get("changelog") or [], indent=2),
        "report.md": as_str(summary.get("report_md")),
    }
    for filename, content in members.items():
        (root / filename).write_text(content, encoding="utf-8")

    archive = root / "package.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(cleaned_path, arcname="cleaned.csv")
        for filename, content in members.items():
            zf.writestr(filename, content)
    return archive


def _row_id(row: dict) -> str | None:
    value = find_id(row)
    return as_str(value) or None
