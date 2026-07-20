import json

from pgtp_editor.generation.gap_summary import summarize_gap_json

REPORT = {
    "schema_version": 1,
    "vendor_older_than_project": True,
    "summary": {"pages": 40, "ok": 3, "diff": 35, "missing_vendor": 1,
                "missing_ours": 0, "error": 1,
                "causes": {"master-detail": 20, "unclassified": 15}},
}


def test_summarize_gap_json(tmp_path):
    path = tmp_path / "gap.json"
    path.write_text(json.dumps(REPORT), encoding="utf-8")
    text = summarize_gap_json(path)
    assert "3 ok" in text and "35 diff" in text and "40 pages" in text
    assert "master-detail: 20" in text
    assert "WARNING" in text and "older" in text     # staleness surfaced


def test_causes_ranked_by_count(tmp_path):
    path = tmp_path / "gap.json"
    path.write_text(json.dumps(REPORT), encoding="utf-8")
    text = summarize_gap_json(path)
    assert text.index("master-detail: 20") < text.index("unclassified: 15")


def test_no_warning_when_fresh(tmp_path):
    fresh = dict(REPORT, vendor_older_than_project=False)
    path = tmp_path / "gap.json"
    path.write_text(json.dumps(fresh), encoding="utf-8")
    assert "WARNING" not in summarize_gap_json(path)


def test_summarize_malformed_json_returns_error_text(tmp_path):
    path = tmp_path / "gap.json"
    path.write_text("{not json", encoding="utf-8")
    assert "Could not read gap JSON" in summarize_gap_json(path)


def test_summarize_missing_file_returns_error_text(tmp_path):
    assert "Could not read gap JSON" in summarize_gap_json(tmp_path / "absent.json")
