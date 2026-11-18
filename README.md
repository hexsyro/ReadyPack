# ReadyPack

A dataset without a datasheet is a folder of CSV. ReadyPack takes your dataset
plus the findings your audits already produced and hands back a publishable
pack: a data-health score, a datasheet, Croissant metadata, a changelog, and a
plain report.

## Why this exists

You can run six honesty checks over a dataset and still ship something no one
can reproduce, because the results live in six terminals and the dataset lives
in a seventh. Packaging is the unglamorous step everyone skips. ReadyPack does
that step and refuses to do it silently.

## What it does

- **Aggregates findings reports.** Point it at the JSON envelopes from the
  other tools (EnrichAudit, LinguaCheck, SourceLock, WhyChanged, NuanceBench,
  FilterGap, DecayWatch) and it folds them into one report, tagging each
  finding with the audit it came from.
- **Scores data health.** A single 0–100 score with a letter grade. Penalties
  are log-scaled (high=6, medium=3, low=1), so the first problems cost the
  most and a long tail of minor notes can't sink an otherwise good dataset.
  `summary.health_score_detail` exposes the per-source components, weights, and
  a confidence rating; the report includes a FAIR self-assessment.
- **Writes the datasheet.** Composition, fields, per-audit findings, and a
  limitations section built from the warnings your audits emitted, as both
  Markdown and a machine-readable Datasheets-for-Datasets JSON document.
- **Emits Croissant 1.1 metadata.** `dct:conformsTo`, a version, a generation
  timestamp, inferred field data types, a SHA-256 of `cleaned.csv`, and a
  PROV-O-style record of which audit tool, version, and status contributed each
  finding. A schema.org/Dataset JSON-LD document is included too.
- **Keeps a changelog.** Every reviewed removal and the packaging run are
  timestamped events.
- **Packages it up.** `cleaned.csv`, the datasheets, `croissant.json`,
  `dataset.jsonld`, `findings.json`, `changelog.json`, `run.json`, and
  `report.md`, zipped into `package.zip`.
- **Never silently deletes.** Rows only leave the export when you hand over ids
  you already reviewed. The tool's default is to change nothing.

## What it is not

It is not a checker. It does not look for leaks, gaps, PII, or bots — the other
tools in the family do that. ReadyPack's job starts once you have findings and
ends with a documented, packaged dataset.

## Install

Python 3.10+, no runtime dependencies.

```bash
git clone https://github.com/hexsyro/ReadyPack.git
cd ReadyPack
python -m pip install .
```

For development:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Usage

```bash
readypack dataset.csv \
  --findings filtergap-report.json \
  --findings linguacheck-report.json \
  --name "product-mentions-2026" \
  --description "Mentions collected for the launch study." \
  --drop-id r003 \
  --out ./pack
```

Without `--findings`, ReadyPack still documents and packages the dataset — it
just has no audits to fold in. Without `--out`, it prints the report and writes
nothing.

## Options

| Flag | What it does |
| --- | --- |
| `--findings FILE` | A findings report (JSON envelope) from another tool; repeatable |
| `--out DIR` | Write the package (cleaned.csv + docs + package.zip) to DIR |
| `--name NAME` | Dataset name for the datasheet and Croissant metadata |
| `--description TEXT` | Dataset description |
| `--drop-id ID` | Drop a reviewed row id from the packaged export; repeatable |
| `--config FILE` | JSON config; explicit flags win |
| `--format {table,json,csv,md}` | Output format (default `table`) |
| `--output FILE` | Write the report to FILE instead of stdout |
| `--fail-on {none,low,medium,high}` | Exit 1 if any finding is at or above this severity |
| `--version` | Print version and exit |

## Output (json)

```json
{
  "tool": "readypack",
  "version": "0.2.0",
  "status": "success",
  "findings": [
    {
      "severity": "high",
      "field": "bot_confidence",
      "message": "Mention scored 0.95 bot/spam confidence (threshold 0.50).",
      "record_id": "r003",
      "metadata": {"check": "bot_confidence", "confidence": 0.95, "audit": "filtergap"}
    }
  ],
  "summary": {
    "result_schema_version": "1.1",
    "skipped": false,
    "skip_reason": null,
    "checked": 5,
    "name": "product-mentions-2026",
    "dataset": {"fields": ["id", "text", "language", "split"], "row_count": 4, "original_row_count": 5},
    "sources": {"filtergap": {"findings": 1, "by_severity": {"high": 1, "medium": 0, "low": 0}, "score": 78.9, "grade": "B"}},
    "findings_total": 1,
    "health_score": {"score": 78.9, "grade": "B", "weights": {"high": 6.0, "medium": 3.0, "low": 1.0}},
    "health_score_detail": {"components": {}, "weights": {"high": 6, "medium": 3, "low": 1}, "confidence": "high"},
    "drop_count": 1,
    "unknown_drop_ids": [],
    "datasheet": "# Datasheet: product-mentions-2026\n...",
    "datasheet_json": "{\"Motivation\": ...}",
    "dataset_jsonld": "{\"@type\": \"Dataset\", ...}",
    "findings_json": "[{\"severity\": \"high\", \"tool\": \"filtergap\", ...}]",
    "croissant": {"@type": "sc:Dataset", "name": "product-mentions-2026"},
    "report_md": "# ReadyPack report: product-mentions-2026\n...",
    "changelog": [{"at": "2026-10-19T00:00:00+00:00", "actor": "readypack", "event": "Packaged 4 row(s)..."}]
  },
  "warnings": ["Review every finding before publishing — ReadyPack never silently deletes rows."]
}
```

The pack on disk (`--out`) contains `cleaned.csv`, `datasheet.md`,
`datasheet.json`, `croissant.json`, `dataset.jsonld`, `findings.json`,
`changelog.json`, `run.json`, `report.md`, and `package.zip`. The
"package written to …" notice goes to stderr so `--format json` stays valid.

## Using it in CI

```bash
readypack dataset.csv --findings audit.json --fail-on high || exit 1
```

Exit codes: `0` ran fine, `1` gate tripped, `2` input broken.

## Library use

```python
from readypack import run, health_score

result = run(rows, {"name": "demo", "reports": [filtergap_report]})
result.summary["health_score"]["score"]

health_score([{"severity": "high"}])  # (78.9, "B")
```

## Limitations, honestly

- **It trusts your reports.** ReadyPack folds in the findings it is given. If
  an audit was wrong, the score is wrong. It scores findings, not truth.
- **The score is a summary, not a judgment.** A 92 with one high finding is
  still a dataset with a high finding. Read the findings, not just the grade.
- **Dropping rows is manual on purpose.** You pass the ids. ReadyPack will not
  infer them, because the whole point is that a human decided.
- **Croissant output is focused, not exhaustive.** It covers the core dataset,
  record-set, distribution, provenance, and checksum concepts; it is not a
  complete implementation of every Croissant 1.1 extension.
- **The license is a placeholder.** Replace `license` in `dataset.jsonld` and
  `croissant.json` before publishing.

## [0.2.0] - 2026-11-19

### Added

- Full Croissant 1.1-style metadata: `dct:conformsTo`, dataset version, `generatedAt`,
  inferred `recordSet[].field` data types, `distribution[].sha256`, and a PROV-O-style
  `wasGeneratedBy` / `wasAttributedTo` block per source report.
- Machine-readable `datasheet.json`, `dataset.jsonld` (schema.org/Dataset), and
  `findings.json`, written to disk, zipped into `package.zip`, and available as text in
  the result summary. `write_package(..., extra_files=...)` adds caller documents such as
  `run.json` (nested relative paths allowed, `..` rejected).
- `summary.health_score_detail` with per-tool components, weights, and confidence, plus a
  FAIR self-assessment table in the Markdown report.
- Result-contract fields `result_schema_version="1.1"`, `skipped`, and `skip_reason`;
  `RESULT_SCHEMA_VERSION` and `ToolResult` exported from the package.
- Changelog events for each reviewed drop id in addition to the packaging event.

### Fixed

- `--format json` stdout is no longer corrupted by the "package written to …" notice;
  the notice goes to stderr.
- Uppercase finding severities (e.g. `High`) now receive the correct health penalty.
- Duplicate audit tool names no longer overwrite each other; they get a numeric suffix
  and a warning.
- Field lists and the CSV header use the union of keys across all rows, not just row 1.
- Unknown drop ids produce a warning (first 10 shown) and `summary["unknown_drop_ids"]`.
- Invalid config value types are rejected by the CLI with exit 2 and a clear stderr
  message; library calls coerce defensively instead of raising.
- Pylint CI now runs on Python 3.10–3.13.

### Inspiration

- Croissant 1.1 + PROV-O provenance — <https://mlcommons.org/2026/02/croissant-1-1-standard>
- Croissant spec (version + checksums) — <https://docs.mlcommons.org/croissant/docs/croissant-spec-1.0.html>
- Datasheets for Datasets — <https://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/1803.09010.pdf>
- Croissant-RAI — <https://proceedings.neurips.cc/paper_files/paper/2024/file/9547b09b722f2948ff3ddb5d86002bc0-Paper-Datasets_and_Benchmarks_Track.pdf>
- schema.org/Dataset JSON-LD — <https://developers.google.com/search/docs/appearance/structured-data/dataset>
- HN "which code ran" — <https://news.ycombinator.com/item?id=49510632>

## License

MIT. See [LICENSE](LICENSE).
