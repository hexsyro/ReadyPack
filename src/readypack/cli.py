"""Command-line interface for ReadyPack.

Exit codes:
  0 — ran successfully
  1 — findings at or above the --fail-on severity
  2 — usage or input error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from readypack import __version__
from readypack.common import SEVERITY_RANK, load_report, load_rows, validate_options
from readypack.export import write_package
from readypack.logic import ReadyPackLogic
from readypack.output import render, worst_severity

TOOL = "readypack"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="Package a dataset with its findings reports into a documented, publishable pack.",
    )
    parser.add_argument("data", help="dataset file (.csv, .json, or .jsonl)")
    parser.add_argument(
        "--findings",
        action="append",
        metavar="FILE",
        default=[],
        help="a findings report (JSON envelope) from another tool; repeatable",
    )
    parser.add_argument("--out", metavar="DIR", help="write the package (cleaned.csv + docs + package.zip) to DIR")
    parser.add_argument("--name", metavar="NAME", help="dataset name for the datasheet and Croissant metadata")
    parser.add_argument("--description", metavar="TEXT", help="dataset description")
    parser.add_argument(
        "--drop-id",
        action="append",
        metavar="ID",
        default=[],
        help="drop a reviewed row id from the packaged export; repeatable",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["table", "json", "csv", "md", "markdown"],
        default="table",
        help="output format (default: table)",
    )
    parser.add_argument("--output", "-o", metavar="FILE", help="write the report to FILE instead of stdout")
    parser.add_argument(
        "--fail-on",
        choices=["none", "low", "medium", "high"],
        default="none",
        help="exit 1 if any finding is at or above this severity (default: none)",
    )
    parser.add_argument("--config", metavar="FILE", help="JSON file of options")
    parser.add_argument("--version", action="version", version=f"{TOOL} {__version__}")
    return parser


def _merge_options(args: argparse.Namespace) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if args.config:
        parsed = json.loads(Path(args.config).read_text(encoding="utf-8"))
        errors = validate_options(parsed)
        if errors:
            raise ValueError(f"{args.config}: invalid config value: {'; '.join(errors)}")
        options.update(parsed)
    reports = [load_report(path) for path in args.findings]
    if reports:
        options["reports"] = reports
    if args.name is not None:
        options["name"] = args.name
    if args.description is not None:
        options["description"] = args.description
    if args.drop_id:
        options["drop_ids"] = list(options.get("drop_ids") or []) + args.drop_id
    errors = validate_options(options)
    if errors:
        raise ValueError(f"invalid config value: {'; '.join(errors)}")
    return options


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        options = _merge_options(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"{TOOL}: {exc}", file=sys.stderr)
        return 2
    try:
        rows = load_rows(args.data)
    except FileNotFoundError:
        print(f"{TOOL}: file not found: {args.data}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"{TOOL}: {exc}", file=sys.stderr)
        return 2
    try:
        result = ReadyPackLogic().run(rows, options)
    except (TypeError, ValueError) as exc:
        print(f"{TOOL}: invalid config value: {exc}", file=sys.stderr)
        return 2
    run_json = render(result, "json", tool=TOOL, version=__version__)
    if args.out:
        try:
            archive = write_package(
                args.out, rows=rows, summary=result.summary,
                drop_ids=options.get("drop_ids"), extra_files={"run.json": run_json},
            )
        except (OSError, ValueError) as exc:
            print(f"{TOOL}: could not write package: {exc}", file=sys.stderr)
            return 2
        # Keep stdout clean: --format json must remain parseable.
        print(f"{TOOL}: package written to {archive}", file=sys.stderr)
    text = run_json if args.format == "json" else render(result, args.format, tool=TOOL, version=__version__)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    if args.fail_on != "none":
        worst = worst_severity(result)
        if worst and SEVERITY_RANK.get(worst, 0) >= SEVERITY_RANK[args.fail_on]:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
