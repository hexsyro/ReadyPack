"""ReadyPack export step: package a dataset with its documentation.

Unlike the checker tools, ReadyPack's output is a downloadable pack: a cleaned
CSV plus machine-readable and human-readable documentation, all zipped together.
The pure builders here (datasheet, Croissant, JSON-LD, report) are also used by
``logic.py`` so the summary carries the exact text that gets written.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from readypack.common import all_fields, as_str, find_id, parse_date, safe_cell

CROISSANT_CONFORMS_TO = "https://mlcommons.org/croissant/docs/croissant-1.1/"
LICENSE_PLACEHOLDER = "https://example.org/license-placeholder"  # replace before publication
_BOOL_WORDS = {"true", "false", "yes", "no", "y", "n", "on", "off"}
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _is_number(value: Any) -> bool:
    """Strict numeric check so identifiers like ``r1`` stay sc:Text."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    text = str(value).strip().replace(",", "")
    if text[-1:] in {"k", "K", "m", "M", "b", "B"}:
        text = text[:-1]
    return bool(_NUMBER_RE.fullmatch(text))


def _infer_data_type(values: list[Any]) -> str:
    """Infer a Croissant/sc:schema dataType from a column's sample values."""
    present = [value for value in values if value is not None and str(value).strip()]
    if not present:
        return "sc:Text"
    if all(
        isinstance(value, bool) or (isinstance(value, str) and value.strip().lower() in _BOOL_WORDS)
        for value in present
    ):
        return "sc:Boolean"
    if all(_is_number(value) for value in present):
        return "sc:Number"
    if all(parse_date(value) is not None for value in present):
        return "sc:Date"
    return "sc:Text"


def build_croissant(
    *,
    name: str,
    description: str,
    fields: list[str],
    row_count: int,
    datasheet: str = "",
    version_tag: str = "0.2.0",
    generated_at: str | None = None,
    sample_rows: list[dict] | None = None,
    provenance: list[dict] | None = None,
    checksums: dict[str, str] | None = None,
) -> dict:
    """Croissant 1.1-style metadata with inferred fields and PROV-O provenance."""
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    rows = sample_rows or []
    fields_meta = []
    for field in fields:
        values = [row.get(field) for row in rows if isinstance(row, dict) and field in row]
        fields_meta.append(
            {
                "@type": "croissant:Field",
                "name": field,
                "dataType": _infer_data_type(values),
            }
        )

    provenance = [dict(record) for record in (provenance or []) if isinstance(record, dict)]
    distributions = [
        {
            "@type": "sc:FileObject",
            "name": "cleaned.csv",
            "contentUrl": "cleaned.csv",
            "encodingFormat": "text/csv",
        }
    ]
    if checksums:
        for distribution in distributions:
            digest = checksums.get(distribution["name"])
            if digest:
                distribution["sha256"] = digest

    return {
        "@context": {
            "@vocab": "https://schema.org/",
            "sc": "https://schema.org/",
            "croissant": "https://mlcommons.org/croissant/",
            "dct": "http://purl.org/dc/terms/",
            "prov": "http://www.w3.org/ns/prov#",
        },
        "@type": "sc:Dataset",
        "dct:conformsTo": CROISSANT_CONFORMS_TO,
        "name": name,
        "description": description or "Dataset packaged by ReadyPack.",
        "license": LICENSE_PLACEHOLDER,
        "version": version_tag,
        "datePublished": timestamp[:10],
        "generatedAt": timestamp,
        "recordSet": [
            {
                "@type": "croissant:RecordSet",
                "name": "records",
                "description": datasheet[:500] if datasheet else "Packaged records.",
                "field": fields_meta,
                "data": [{"recordCount": row_count}],
            }
        ],
        "distribution": distributions,
        "wasGeneratedBy": provenance,
        "wasAttributedTo": [
            {
                "@type": "prov:Agent",
                "name": record.get("tool", ""),
                "version": record.get("version", ""),
                "status": record.get("status", "success"),
                "findings": record.get("findings", 0),
            }
            for record in provenance
        ],
    }


def build_datasheet(
    *,
    name: str,
    description: str,
    fields: list[str],
    row_count: int,
    original_count: int,
    sources: dict[str, dict],
    warnings: list[str],
) -> str:
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


def build_datasheet_json(
    *,
    name: str,
    description: str,
    fields: list[str],
    row_count: int,
    original_count: int,
    sources: dict[str, dict],
    warnings: list[str],
    dropped_ids: list[str] | None = None,
    unknown_drop_ids: list[str] | None = None,
    version: str = "0.2.0",
    generated_at: str | None = None,
) -> str:
    """Machine-readable Datasheets-for-Datasets document (JSON text)."""
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    document = {
        "Motivation": description or f"Dataset {name} packaged for publication by ReadyPack.",
        "Composition": {
            "row_count": row_count,
            "original_row_count": original_count,
            "fields": list(fields),
            "audits": {
                tool: {
                    "version": info.get("version", ""),
                    "status": info.get("status", "success"),
                    "findings": info.get("findings", 0),
                    "by_severity": info.get("by_severity", {}),
                }
                for tool, info in sources.items()
            },
        },
        "Collection": {
            "audit_sources": sorted(sources),
            "note": "Rows and audit reports are supplied by the caller; ReadyPack does not collect data.",
        },
        "Preprocessing": {
            "dropped_ids": list(dropped_ids or []),
            "unknown_drop_ids": list(unknown_drop_ids or []),
            "note": "Only explicitly reviewed row ids are removed; CSV cells are formula-neutralized.",
        },
        "Uses": {
            "intended": "Research and analysis with the accompanying audit findings and provenance.",
            "out_of_scope": "Automated decisions about people without independent review of the findings.",
        },
        "Distribution": {
            "formats": ["text/csv", "application/json"],
            "license": LICENSE_PLACEHOLDER,
            "files": [
                "cleaned.csv",
                "datasheet.md",
                "datasheet.json",
                "dataset.jsonld",
                "findings.json",
                "croissant.json",
                "changelog.json",
                "report.md",
            ],
        },
        "Maintenance": {
            "version": version,
            "generatedAt": timestamp,
            "warnings": list(warnings),
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=False)


def build_dataset_jsonld(
    *,
    name: str,
    description: str,
    fields: list[str],
    row_count: int,
    version: str = "0.2.0",
    generated_at: str | None = None,
    sources: dict[str, dict] | None = None,
    checksums: dict[str, str] | None = None,
) -> str:
    """schema.org/Dataset JSON-LD describing the packaged dataset (JSON text)."""
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    distribution: dict[str, Any] = {
        "@type": "DataDownload",
        "name": "cleaned.csv",
        "contentUrl": "cleaned.csv",
        "encodingFormat": "text/csv",
    }
    digest = (checksums or {}).get("cleaned.csv")
    if digest:
        distribution["sha256"] = digest
    keywords = ["readypack", "dataset", *fields, *(sources or {})]
    document = {
        "@context": "https://schema.org/",
        "@type": "Dataset",
        "name": name,
        "description": description or "Dataset packaged by ReadyPack.",
        "license": LICENSE_PLACEHOLDER,
        "version": version,
        "datePublished": timestamp[:10],
        "distribution": [distribution],
        "keywords": list(dict.fromkeys(keywords)),
        "variableMeasured": list(fields),
        "size": f"{row_count} rows",
    }
    return json.dumps(document, indent=2, ensure_ascii=False)


def build_findings_json(findings: list[dict]) -> str:
    """Normalized findings array (JSON text) with a stable key order."""
    normalized = [
        {
            "severity": finding.get("severity", "low"),
            "tool": (finding.get("metadata") or {}).get("audit", ""),
            "field": finding.get("field", ""),
            "record_id": finding.get("record_id"),
            "message": finding.get("message", ""),
            "metadata": finding.get("metadata") or {},
        }
        for finding in findings
        if isinstance(finding, dict)
    ]
    return json.dumps(normalized, indent=2, ensure_ascii=False, default=str)


def build_report_md(
    *,
    name: str,
    health: dict,
    sources: dict[str, dict],
    kept: int,
    dropped: int,
    findings: int,
    fair: dict | None = None,
) -> str:
    """Human-readable package report, including a FAIR self-assessment."""
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
        "## FAIR self-assessment",
        "",
        "| Principle | Rating | Evidence |",
        "| --- | --- | --- |",
    ]
    assessment = fair or {
        "F": {"status": "partial", "fields": "summary.dataset.fields"},
        "A": {"status": "partial", "fields": "package.zip"},
        "I": {"status": "partial", "fields": "summary.croissant"},
        "R": {"status": "partial", "fields": "summary.datasheet"},
    }
    labels = {
        "F": "F — Findable",
        "A": "A — Accessible",
        "I": "I — Interoperable",
        "R": "R — Reusable",
    }
    for principle in ("F", "A", "I", "R"):
        info = assessment.get(principle, {})
        lines.append(f"| {labels[principle]} | {info.get('status', 'partial')} | {info.get('fields', '—')} |")
    lines += [
        "",
        "## What gets packaged",
        "",
        "- cleaned.csv — the dataset, minus any explicitly reviewed removals.",
        "- datasheet.md / datasheet.json — human- and machine-readable dataset card.",
        "- croissant.json — Croissant 1.1 metadata with provenance and a content checksum.",
        "- dataset.jsonld — schema.org/Dataset JSON-LD.",
        "- findings.json — normalized findings with their source tool.",
        "- changelog.json — the action history.",
        "- report.md — this file.",
        "",
        "Nothing was deleted without review. See changelog.json for the full history.",
    ]
    return "\n".join(lines)


def _safe_extra_path(root: Path, name: str) -> Path:
    """Resolve an extra-file name inside ``root``; reject traversal and absolutes."""
    candidate = Path(name)
    if (
        not name
        or candidate.is_absolute()
        or any(part == ".." for part in candidate.parts)
        or candidate.name in {"", ".", ".."}
    ):
        raise ValueError(f"extra file name must be a relative path without '..': {name!r}")
    target = root / candidate
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"extra file name escapes the package directory: {name!r}") from exc
    return target


def write_package(
    out_dir: str | Path,
    *,
    rows: list[dict],
    summary: dict,
    drop_ids: list[str] | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Write cleaned.csv + docs into ``out_dir`` and zip them into package.zip."""
    rows = list(rows)
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    dropped = {as_str(x) for x in (drop_ids or []) if as_str(x)}

    fields = all_fields(rows)
    kept = [row for row in rows if _row_id(row) not in dropped]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields or ["_empty"])
    writer.writeheader()
    for row in kept:
        writer.writerow({name: safe_cell(row.get(name, "")) for name in writer.fieldnames or []})
    cleaned_text = buffer.getvalue()
    checksum = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()

    cleaned_path = root / "cleaned.csv"
    with open(cleaned_path, "w", newline="", encoding="utf-8") as handle:
        handle.write(cleaned_text)

    croissant = summary.get("croissant")
    if isinstance(croissant, dict):
        for distribution in croissant.get("distribution") or []:
            if isinstance(distribution, dict) and distribution.get("contentUrl") == "cleaned.csv":
                distribution["sha256"] = checksum
        summary["croissant"] = croissant

    jsonld_text = summary.get("dataset_jsonld")
    if isinstance(jsonld_text, str):
        try:
            jsonld = json.loads(jsonld_text)
        except json.JSONDecodeError:
            jsonld = None
        if isinstance(jsonld, dict):
            for distribution in jsonld.get("distribution") or []:
                if isinstance(distribution, dict):
                    distribution["sha256"] = checksum
            summary["dataset_jsonld"] = json.dumps(jsonld, indent=2, ensure_ascii=False)

    dataset_raw = summary.get("dataset")
    dataset: dict[str, Any] = dataset_raw if isinstance(dataset_raw, dict) else {}
    name = as_str(summary.get("name")) or "dataset"
    fields = list(dataset.get("fields") or fields)
    row_count = int(dataset.get("row_count") or len(kept))
    original_count = int(dataset.get("original_row_count") or len(rows))
    sources_raw = summary.get("sources")
    sources: dict[str, dict] = sources_raw if isinstance(sources_raw, dict) else {}
    warnings = [as_str(w) for w in (summary.get("warnings") or []) if as_str(w)]

    datasheet_json = summary.get("datasheet_json")
    if not isinstance(datasheet_json, str) or not datasheet_json:
        datasheet_json = build_datasheet_json(
            name=name,
            description=as_str(summary.get("description")),
            fields=fields,
            row_count=row_count,
            original_count=original_count,
            sources=sources,
            warnings=warnings,
        )
    jsonld_text = summary.get("dataset_jsonld")
    if not isinstance(jsonld_text, str) or not jsonld_text:
        jsonld_text = build_dataset_jsonld(
            name=name,
            description=as_str(summary.get("description")),
            fields=fields,
            row_count=row_count,
            checksums={"cleaned.csv": checksum},
        )
    findings_json = summary.get("findings_json")
    if not isinstance(findings_json, str) or not findings_json:
        findings_json = build_findings_json([])

    members: dict[str, str] = {
        "datasheet.md": as_str(summary.get("datasheet")) or f"# Datasheet: {name}\n",
        "datasheet.json": datasheet_json,
        "croissant.json": json.dumps(summary.get("croissant") or {}, indent=2),
        "dataset.jsonld": jsonld_text,
        "findings.json": findings_json,
        "changelog.json": json.dumps(summary.get("changelog") or [], indent=2),
        "report.md": as_str(summary.get("report_md")),
    }
    extra_arcnames: list[str] = []
    for filename, content in (extra_files or {}).items():
        target = _safe_extra_path(root, filename)
        arcname = target.relative_to(root).as_posix()
        if arcname in members or arcname in extra_arcnames:
            raise ValueError(f"duplicate package member: {arcname!r}")
        extra_arcnames.append(arcname)
        members[arcname] = as_str(content)

    for filename, content in members.items():
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    archive = root / "package.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(cleaned_path, arcname="cleaned.csv")
        for filename, content in members.items():
            zf.writestr(filename, content)
    return archive


def _row_id(row: dict) -> str | None:
    value = find_id(row)
    return as_str(value) or None
