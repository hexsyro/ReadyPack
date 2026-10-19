"""Logic tests for ReadyPack."""

from __future__ import annotations

from readypack.logic import ReadyPackLogic, health_score, run


def report(tool, findings, warnings=None, summary=None):
    return {
        "tool": tool,
        "version": "0.1.0",
        "status": "success",
        "findings": findings,
        "warnings": warnings or [],
        "summary": summary or {},
    }


def finding(severity, record_id="r1"):
    return {"severity": severity, "field": "bot_confidence", "message": "x",
            "record_id": record_id, "metadata": {"check": "c"}}


def test_health_score_empty_is_perfect():
    assert health_score([]) == (100.0, "A")


def test_health_score_one_high():
    assert health_score([finding("high")]) == (78.9, "B")


def test_health_score_severity_is_case_insensitive():
    assert health_score([finding("High")]) == health_score([finding("high")])


def test_health_score_grade_bands():
    assert health_score([finding("low")])[1] == "A"
    assert health_score([finding("low")] * 5)[1] == "B"
    assert health_score([finding("low")] * 20)[1] == "C"
    assert health_score([finding("low")] * 100)[1] == "D"


def test_health_score_is_log_scaled_not_linear():
    one = health_score([finding("low")])[0]
    ten = health_score([finding("low")] * 10)[0]
    assert one > ten
    assert one - ten < 40


def test_aggregates_and_tags_source():
    rows = [{"id": "r1", "text": "hello"}]
    reports = [report("filtergap", [finding("high", "r1")]),
               report("linguacheck", [finding("low", "r1")])]
    result = run(rows, {"reports": reports})
    assert len(result.findings) == 2
    audits = {f["metadata"]["audit"] for f in result.findings}
    assert audits == {"filtergap", "linguacheck"}


def test_per_source_health():
    rows = [{"id": "r1", "text": "hello"}]
    reports = [report("filtergap", [finding("high")])]
    sources = run(rows, {"reports": reports}).summary["sources"]
    assert sources["filtergap"]["findings"] == 1
    assert sources["filtergap"]["by_severity"]["high"] == 1
    assert sources["filtergap"]["score"] == 78.9


def test_summary_carries_documents():
    result = run([{"id": "r1", "text": "x"}], {"reports": [report("filtergap", [finding("high")])],
                                               "name": "demo"})
    summary = result.summary
    assert summary["health_score"]["score"] < 100
    assert "# Datasheet: demo" in summary["datasheet"]
    assert summary["croissant"]["name"] == "demo"
    assert "# ReadyPack report: demo" in summary["report_md"]
    assert summary["changelog"]


def test_drop_ids_removes_rows():
    rows = [{"id": "r1", "text": "a"}, {"id": "r2", "text": "b"}]
    result = run(rows, {"drop_ids": ["r1"]})
    assert result.summary["dataset"]["row_count"] == 1
    assert result.summary["dataset"]["original_row_count"] == 2
    assert result.summary["drop_count"] == 1


def test_no_reports_documents_absence():
    result = run([{"id": "r1", "text": "a"}], {})
    assert result.findings == []
    assert "No audit reports were supplied" in result.summary["datasheet"]


def test_source_warnings_surfaced():
    reports = [report("decaywatch", [], warnings=["Snapshot comparison only."])]
    result = run([{"id": "r1", "text": "a"}], {"reports": reports})
    assert any("decaywatch: Snapshot comparison only." in w for w in result.warnings)


def test_always_warns_about_review():
    result = run([{"id": "r1", "text": "a"}], {})
    assert any("never silently deletes" in w for w in result.warnings)


def test_changelog_records_packaging():
    result = run([{"id": "r1", "text": "a"}], {"drop_ids": ["r1"]})
    event = result.summary["changelog"][-1]["event"]
    assert "Packaged" in event
    assert result.summary["changelog"][-1]["actor"] == "readypack"


def test_run_returns_toolresult():
    result = ReadyPackLogic().run([{"id": "r1", "text": "x"}], {})
    assert result.status == "success"
    assert isinstance(result.findings, list)
