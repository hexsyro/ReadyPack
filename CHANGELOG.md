# Changelog

All notable changes to this project will be documented in this file.

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
