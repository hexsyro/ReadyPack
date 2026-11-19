"""CLI tests for ReadyPack."""

from __future__ import annotations

import csv
import json
import zipfile

from readypack.cli import main


def write_file(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


DATA_CSV = "id,text,split\nr1,hello,train\nr2,world,test\nr3,=SUM(A1),train\n"

FINDINGS_JSON = json.dumps(
    {
        "tool": "filtergap",
        "version": "0.1.0",
        "status": "success",
        "findings": [
            {
                "severity": "high",
                "field": "bot_confidence",
                "message": "bot",
                "record_id": "r1",
                "metadata": {"check": "bot_confidence"},
            }
        ],
        "warnings": [],
        "summary": {},
    }
)


def test_json_output(tmp_path, capsys):
    p = write_file(tmp_path, "data.csv", DATA_CSV)
    assert main([str(p), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tool"] == "readypack"
    assert payload["summary"]["health_score"]["grade"] == "A"


def test_findings_and_fail_on(tmp_path, capsys):
    p = write_file(tmp_path, "data.csv", DATA_CSV)
    f = write_file(tmp_path, "findings.json", FINDINGS_JSON)
    assert main([str(p), "--findings", str(f), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["findings_total"] == 1
    assert payload["summary"]["health_score"]["score"] == 78.9
    assert main([str(p), "--findings", str(f), "--fail-on", "high", "--format", "json"]) == 1


def test_out_writes_package(tmp_path):
    p = write_file(tmp_path, "data.csv", DATA_CSV)
    f = write_file(tmp_path, "findings.json", FINDINGS_JSON)
    out = tmp_path / "pack"
    assert main([str(p), "--findings", str(f), "--drop-id", "r1", "--name", "demo", "--out", str(out)]) == 0
    for filename in (
        "cleaned.csv",
        "datasheet.md",
        "datasheet.json",
        "croissant.json",
        "dataset.jsonld",
        "findings.json",
        "changelog.json",
        "report.md",
        "run.json",
        "package.zip",
    ):
        assert (out / filename).exists()
    rows = list(csv.DictReader((out / "cleaned.csv").read_text(encoding="utf-8").splitlines()))
    assert {r["id"] for r in rows} == {"r2", "r3"}
    text = (out / "cleaned.csv").read_text(encoding="utf-8")
    assert "'=SUM(A1)" in text
    with zipfile.ZipFile(out / "package.zip") as zf:
        assert set(zf.namelist()) == {
            "cleaned.csv",
            "datasheet.md",
            "datasheet.json",
            "croissant.json",
            "dataset.jsonld",
            "findings.json",
            "changelog.json",
            "report.md",
            "run.json",
        }


def test_config_file(tmp_path, capsys):
    p = write_file(tmp_path, "data.csv", DATA_CSV)
    cfg = write_file(tmp_path, "c.json", json.dumps({"name": "from-config", "drop_ids": ["r1"]}))
    assert main([str(p), "--config", str(cfg), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["name"] == "from-config"
    assert payload["summary"]["drop_count"] == 1


def test_bad_findings_returns_two(tmp_path):
    p = write_file(tmp_path, "data.csv", DATA_CSV)
    f = write_file(tmp_path, "bad.json", "{not json")
    assert main([str(p), "--findings", str(f)]) == 2


def test_missing_file_returns_two(tmp_path):
    assert main([str(tmp_path / "nope.csv")]) == 2


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "readypack" in capsys.readouterr().out
