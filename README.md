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
- **Writes the datasheet.** Composition, fields, per-audit findings, and a
  limitations section built from the warnings your audits emitted.
- **Emits Croissant metadata.** The mlcommons schema, so the pack is
  discoverable by dataset tooling.
- **Keeps a changelog.** Every packaged row and every reviewed removal is an
  event with a timestamp.
- **Packages it up.** `cleaned.csv`, `datasheet.md`, `croissant.json`,
  `changelog.json`, `report.md`, zipped into `package.zip`.
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
  "version": "0.1.0",
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
    "checked": 5,
    "name": "product-mentions-2026",
    "dataset": {"fields": ["id", "text", "language", "split"], "row_count": 4, "original_row_count": 5},
    "sources": {"filtergap": {"findings": 1, "by_severity": {"high": 1, "medium": 0, "low": 0}, "score": 78.9, "grade": "B"}},
    "findings_total": 1,
    "health_score": {"score": 78.9, "grade": "B", "weights": {"high": 6.0, "medium": 3.0, "low": 1.0}},
    "drop_count": 1,
    "datasheet": "# Datasheet: product-mentions-2026\n...",
    "croissant": {"@type": "sc:Dataset", "name": "product-mentions-2026"},
    "report_md": "# ReadyPack report: product-mentions-2026\n...",
    "changelog": [{"at": "2026-10-19T00:00:00+00:00", "actor": "readypack", "event": "Packaged 4 row(s)..."}]
  },
  "warnings": ["Review every finding before publishing — ReadyPack never silently deletes rows."]
}
```

The pack on disk (`--out`) contains `cleaned.csv`, `datasheet.md`,
`croissant.json`, `changelog.json`, `report.md`, and `package.zip`.

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
- **Croissant output is minimal.** Enough to be valid and discoverable, not the
  full vocabulary.

## License

MIT. See [LICENSE](LICENSE).
