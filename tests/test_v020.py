"""Regression tests for the 0.2.0 contract and new packaging features."""

from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

import readypack
from readypack import RESULT_SCHEMA_VERSION, ToolResult
from readypack.cli import main
from readypack.export import build_croissant, write_package
from readypack.logic import run

DATA = "id,text\nr1,hello\nr2,world\n"


def report(tool, findings=None, *, version="0.3.0", status="success", warnings=None):
    return {
        "tool": tool,
        "version": version,
        "status": status,
        "findings": findings or [],
        "warnings": warnings or [],
        "summary": {},
    }


def finding(severity, record_id="r1"):
    return {
        "severity": severity,
        "field": "bot_confidence",
        "message": "x",
        "record_id": record_id,
        "metadata": {"check": "c"},
    }


def write_file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_public_version_and_exports():
    assert readypack.__version__ == "0.2.0"
    assert RESULT_SCHEMA_VERSION == "1.1"
    assert "RESULT_SCHEMA_VERSION" in readypack.__all__
    assert "ToolResult" in readypack.__all__
    assert isinstance(run([]), ToolResult)


def test_summary_carries_result_contract():
    summary = run([{"id": "r1"}], {}).summary
    assert summary["result_schema_version"] == "1.1"
    assert summary["skipped"] is False
    assert summary["skip_reason"] is None


def test_malformed_library_options_never_raise():
    options = {
        "name": ["bad"],
        "description": 42,
        "reports": "not-a-list",
        "drop_ids": {"r1": True},
        "changelog": 7,
        "version_tag": {"x": 1},
    }
    result = run([{"id": "r1", "text": "x"}], options)
    assert isinstance(result, ToolResult)
    assert result.status == "success"
    assert result.summary["croissant"]["version"] == "0.2.0"


def test_cli_invalid_config_value_exits_two(tmp_path, capsys):
    data = write_file(tmp_path, "data.csv", DATA)
    config = write_file(tmp_path, "bad.json", json.dumps({"name": ["bad"], "drop_ids": {"r1": True}}))
    assert main([str(data), "--config", str(config)]) == 2
    captured = capsys.readouterr()
    assert "invalid config value" in captured.err
    assert "name" in captured.err and "drop_ids" in captured.err
    assert captured.out == ""


def test_cli_invalid_nested_report_config_exits_two(tmp_path, capsys):
    data = write_file(tmp_path, "data.csv", DATA)
    config = write_file(tmp_path, "bad.json", json.dumps({"reports": [{"tool": "a", "findings": "bad"}]}))
    assert main([str(data), "--config", str(config)]) == 2
    assert "reports[0].findings" in capsys.readouterr().err


def test_json_stdout_stays_clean_with_out(tmp_path, capsys):
    data = write_file(tmp_path, "data.csv", DATA)
    out = tmp_path / "pack"
    assert main([str(data), "--out", str(out), "--format", "json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["summary"]["result_schema_version"] == "1.1"
    assert "package written" in captured.err


def test_uppercase_severity_uses_correct_penalty():
    result = run([{"id": "r1"}], {"reports": [report("a", [finding("High")])]})
    assert result.summary["health_score"]["raw_penalty"] == 6.0
    assert result.summary["health_score"]["score"] == 78.9
    assert result.summary["health_score_detail"]["components"]["a"]["penalty"] == 6.0


def test_duplicate_tool_names_disambiguated():
    reports = [report("dup", [finding("high")]), report("dup", [finding("low")])]
    result = run([{"id": "r1"}], {"reports": reports})
    assert set(result.summary["sources"]) == {"dup", "dup_2"}
    assert any("Duplicate audit tool name" in warning for warning in result.warnings)
    assert {f["metadata"]["audit"] for f in result.findings} == {"dup", "dup_2"}


def test_fields_are_union_across_rows(tmp_path):
    rows = [{"id": "r1", "a": "1"}, {"id": "r2", "b": "2"}]
    summary = run(rows, {}).summary
    assert summary["dataset"]["fields"] == ["id", "a", "b"]
    out = tmp_path / "pack"
    write_package(out, rows=rows, summary=summary)
    header = (out / "cleaned.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "id,a,b"


def test_unknown_drop_ids_warn_and_are_reported():
    result = run([{"id": "r1"}, {"id": "r2"}], {"drop_ids": ["r99", "r1", "r98"]})
    assert result.summary["unknown_drop_ids"] == ["r98", "r99"]
    assert any("Unknown drop ids ignored: r98, r99." in w for w in result.warnings)


def test_unknown_drop_ids_warning_lists_at_most_ten():
    ids = [f"u{i:02d}" for i in range(1, 13)]
    result = run([{"id": "r1"}], {"drop_ids": ids})
    assert len(result.summary["unknown_drop_ids"]) == 12
    warning = next(w for w in result.warnings if "Unknown drop ids" in w)
    assert "u01" in warning and "u10" in warning
    assert "u11" not in warning and "and 2 more" in warning


def test_changelog_has_one_event_per_dropped_id():
    result = run(
        [{"id": "r1"}, {"id": "r2"}],
        {"drop_ids": ["r2", "r1"], "changelog": [{"at": "earlier", "actor": "human", "event": "seed"}]},
    )
    events = [item["event"] for item in result.summary["changelog"]]
    assert events[0] == "seed"
    assert sum("Removed row" in event for event in events) == 2
    assert "Packaged" in events[-1]


def test_croissant_full_metadata_and_checksum(tmp_path):
    rows = [
        {"id": "r1", "score": "3.5", "active": "yes", "when": "2026-11-19", "note": "hi"},
        {"id": "r2", "score": "4.0", "active": "no", "when": "2026-11-20", "note": "yo"},
    ]
    result = run(
        rows,
        {
            "name": "demo",
            "version_tag": "9.9.9",
            "reports": [report("filtergap", [finding("high")])],
        },
    )
    summary = result.summary
    croissant = summary["croissant"]
    assert croissant["dct:conformsTo"].startswith("https://mlcommons.org/croissant")
    assert croissant["version"] == "9.9.9"
    assert croissant["generatedAt"]
    types = {f["name"]: f["dataType"] for f in croissant["recordSet"][0]["field"]}
    assert types == {
        "id": "sc:Text",
        "score": "sc:Number",
        "active": "sc:Boolean",
        "when": "sc:Date",
        "note": "sc:Text",
    }
    assert croissant["wasGeneratedBy"][0] == {
        "tool": "filtergap",
        "version": "0.3.0",
        "status": "success",
        "findings": 1,
    }
    assert croissant["wasAttributedTo"][0]["name"] == "filtergap"
    assert "sha256" not in croissant["distribution"][0]

    out = tmp_path / "pack"
    write_package(out, rows=rows, summary=summary)
    raw = (out / "cleaned.csv").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    written = json.loads((out / "croissant.json").read_text(encoding="utf-8"))
    assert written["distribution"][0]["sha256"] == digest
    jsonld = json.loads((out / "dataset.jsonld").read_text(encoding="utf-8"))
    assert jsonld["distribution"][0]["sha256"] == digest


def test_croissant_defaults_and_backward_compatible_builder():
    assert run([]).summary["croissant"]["version"] == "0.2.0"
    legacy = build_croissant(name="x", description="", fields=["a"], row_count=1)
    assert legacy["version"] == "0.2.0"
    assert legacy["wasGeneratedBy"] == []
    assert "sha256" not in legacy["distribution"][0]


def test_machine_readable_documents(tmp_path):
    rows = [{"id": "r1", "text": "x"}]
    summary = run(
        rows, {"name": "demo", "version_tag": "4.2.0", "reports": [report("filtergap", [finding("high")])]}
    ).summary
    datasheet = json.loads(summary["datasheet_json"])
    for section in ("Motivation", "Composition", "Collection", "Preprocessing", "Uses", "Distribution", "Maintenance"):
        assert section in datasheet
    assert datasheet["Composition"]["audits"]["filtergap"]["findings"] == 1
    jsonld = json.loads(summary["dataset_jsonld"])
    assert jsonld["@type"] == "Dataset"
    assert jsonld["name"] == "demo"
    assert jsonld["version"] == "4.2.0"
    assert jsonld["license"]
    assert jsonld["distribution"][0]["contentUrl"] == "cleaned.csv"
    assert "text" in jsonld["keywords"]
    findings = json.loads(summary["findings_json"])
    assert set(findings[0]) >= {"severity", "tool", "field", "record_id", "message", "metadata"}
    assert findings[0]["tool"] == "filtergap"

    out = tmp_path / "pack"
    write_package(out, rows=rows, summary=summary)
    with zipfile.ZipFile(out / "package.zip") as zf:
        assert json.loads(zf.read("datasheet.json"))["Composition"]["row_count"] == 1
        assert json.loads(zf.read("dataset.jsonld"))["@type"] == "Dataset"
        assert json.loads(zf.read("findings.json"))[0]["severity"] == "high"


def test_health_score_detail_confidence():
    rows = [{"id": "r1"}]
    high = run(rows, {"reports": [report("a")]}).summary["health_score_detail"]
    assert high["weights"] == {"high": 6, "medium": 3, "low": 1}
    assert high["confidence"] == "high"
    assert high["components"]["a"] == {"findings": 0, "penalty": 0.0, "score": 100.0}

    medium = run(rows, {"reports": [report("a", warnings=["heads up"])]}).summary["health_score_detail"]
    assert medium["confidence"] == "medium"
    low = run(rows, {"reports": [report("a", status="error")]}).summary["health_score_detail"]
    assert low["confidence"] == "low"


def test_report_md_has_fair_section():
    report_md = run([{"id": "r1"}], {"reports": [report("a")]}).summary["report_md"]
    assert "## FAIR self-assessment" in report_md
    for label in ("F — Findable", "A — Accessible", "I — Interoperable", "R — Reusable"):
        assert label in report_md
    assert "summary.croissant.dct:conformsTo" in report_md


def test_extra_files_written_and_zipped(tmp_path):
    rows = [{"id": "r1", "text": "x"}]
    summary = run(rows, {}).summary
    out = tmp_path / "pack"
    write_package(out, rows=rows, summary=summary, extra_files={"run.json": '{"ok": true}', "meta/notes.txt": "hello"})
    assert json.loads((out / "run.json").read_text(encoding="utf-8")) == {"ok": True}
    assert (out / "meta" / "notes.txt").read_text(encoding="utf-8") == "hello"
    with zipfile.ZipFile(out / "package.zip") as zf:
        assert "run.json" in zf.namelist()
        assert "meta/notes.txt" in zf.namelist()
        assert json.loads(zf.read("run.json")) == {"ok": True}


def test_extra_files_reject_traversal_and_absolute(tmp_path):
    with pytest.raises(ValueError, match="\\.\\."):
        write_package(tmp_path / "pack", rows=[], summary={}, extra_files={"../evil.txt": "x"})
    with pytest.raises(ValueError, match="relative path"):
        write_package(tmp_path / "pack", rows=[], summary={}, extra_files={str(tmp_path / "absolute.txt"): "x"})
