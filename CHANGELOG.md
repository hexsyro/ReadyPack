# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-11-19

### Added

- Result schema contract: `result_schema_version="1.1"`, `skipped`, and `skip_reason` in every run summary; `RESULT_SCHEMA_VERSION` and `ToolResult` exported from `readypack`.
- Full Croissant 1.1-style metadata: `dct:conformsTo`, configurable `version` (`version_tag`, default 0.2.0), `generatedAt`, inferred `recordSet[].field` data types, `distribution[].sha256`, and PROV-O-style `wasGeneratedBy` / `wasAttributedTo` provenance per report.
- Machine-readable documents: `datasheet.json` (Datasheets-for-Datasets sections), `dataset.jsonld` (schema.org/Dataset), and `findings.json` (normalized findings). All are written to disk, included in `package.zip`, and available as text in the summary.
- `write_package(..., extra_files=...)` writes caller-provided documents (e.g. `run.json`) into the pack; nested relative paths are supported and `..` traversal is rejected.
- `summary.health_score_detail` with per-tool finding counts, penalties, scores, weights, and confidence; FAIR self-assessment table in `report.md`.
- One changelog event per reviewed drop id, in addition to the packaging event.

### Fixed

- The "package written to …" notice goes to stderr so `--format json` stdout stays parseable.
- Uppercase severities such as `High` are normalized before applying health penalties.
- Duplicate audit tool names get a numeric suffix and a warning instead of overwriting each other.
- Field lists and the CSV header use the union of keys across all rows, not just the first row.
- Unknown drop ids are warned about (first 10 listed) and recorded in `summary["unknown_drop_ids"]`.
- Invalid config value types exit 2 with a clear stderr message; malformed library options never raise out of `run()`.
- Pylint CI matrix updated to Python 3.10–3.13.

### Inspiration

- Croissant 1.1 + PROV-O provenance — <https://mlcommons.org/2026/02/croissant-1-1-standard>
- Croissant spec (version + checksums) — <https://docs.mlcommons.org/croissant/docs/croissant-spec-1.0.html>
- Datasheets for Datasets — <https://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/1803.09010.pdf>
- Croissant-RAI — <https://proceedings.neurips.cc/paper_files/paper/2024/file/9547b09b722f2948ff3ddb5d86002bc0-Paper-Datasets_and_Benchmarks_Track.pdf>
- schema.org/Dataset JSON-LD — <https://developers.google.com/search/docs/appearance/structured-data/dataset>
- HN "which code ran" — <https://news.ycombinator.com/item?id=49510632>

## [0.1.0] - 2026-10-19

### Added

- Initial release.
- Aggregates findings reports (JSON envelopes) from the other tools into one package, tagging each finding with its source audit.
- Data-health score: 0-100 with a letter grade, log-scaled finding penalties (high=6, medium=3, low=1), deterministic.
- Datasheet builder: composition, fields, per-audit findings, and a limitations section from audit warnings.
- Minimal Croissant (mlcommons) metadata export.
- Changelog with a timestamped event per packaging run and reviewed removal.
- Packaged output: cleaned.csv, datasheet.md, croissant.json, changelog.json, report.md, zipped into package.zip.
- Reviewed, id-explicit row removal; nothing is ever deleted silently.
- CSV formula-injection neutralization on exported cells.
- CLI with table/json/csv/md, --fail-on exit codes, JSON config.
- Importable library API: readypack.run(rows, options) and readypack.health_score(findings).
