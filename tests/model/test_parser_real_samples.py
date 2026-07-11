"""Integration/regression tests against the real sample .pgtp files.

These are slower and stay a small separate suite (per the spec's testing
strategy), not the bulk of coverage — the synthetic-XML tests in
test_parser.py cover the detailed behavior.
"""
from pathlib import Path

import pytest

from pgtp_editor.model.nodes import CLIENT_SIDE_EVENT_NAMES, classify_event_side
from pgtp_editor.model.parser import load_project

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"

SAMPLE_FILES = [
    SAMPLE_DIR / "dev_Ferrara.pgtp",
    SAMPLE_DIR / "Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp",
]


def _require_sample(path):
    if not path.exists():
        pytest.skip(f"sample file not present: {path}")


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_parsing_real_file_does_not_crash(sample_path):
    _require_sample(sample_path)
    project = load_project(sample_path)
    assert project is not None


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_real_file_has_sane_page_count(sample_path):
    _require_sample(sample_path)
    project = load_project(sample_path)
    assert len(project.pages) > 0
    # Sanity upper bound: no real .pgtp project has thousands of top-level
    # pages; this just guards against accidentally parsing the wrong node set.
    assert len(project.pages) < 1000


def _iter_all_nodes(page):
    yield page
    for detail in page.details:
        yield from _iter_all_details(detail)


def _iter_all_details(detail):
    yield detail
    for nested in detail.details:
        yield from _iter_all_details(nested)


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_real_file_event_classification_matches_authoritative_list(sample_path):
    _require_sample(sample_path)
    project = load_project(sample_path)

    all_events = []
    for page in project.pages:
        for node in _iter_all_nodes(page):
            all_events.extend(node.events)

    assert len(all_events) > 0

    for event in all_events:
        expected_side = classify_event_side(event.tag_name)
        assert event.side == expected_side
        base_name = event.tag_name.split("_", 1)[0]
        if base_name in CLIENT_SIDE_EVENT_NAMES:
            assert event.side == "C"
        else:
            assert event.side == "S"


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_real_file_nodes_have_identity_and_sourceline(sample_path):
    _require_sample(sample_path)
    project = load_project(sample_path)

    for page in project.pages:
        assert page.identity
        assert page.sourceline is not None and page.sourceline > 0
        for node in _iter_all_nodes(page):
            for column in node.columns:
                assert column.identity
                assert column.sourceline is not None
            for event in node.events:
                assert event.identity
                assert event.sourceline is not None
