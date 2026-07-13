"""Integration/regression tests against the real sample .pgtp files.

These are slower and stay a small separate suite (per the spec's testing
strategy), not the bulk of coverage — the synthetic-XML tests in
test_parser.py cover the detailed behavior.
"""
from pathlib import Path

import pytest

from pgtp_editor.model.nodes import CLIENT_SIDE_EVENT_NAMES
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
        base_name = event.tag_name.split("_", 1)[0]
        if base_name in CLIENT_SIDE_EVENT_NAMES:
            assert event.side == "C"
        else:
            assert event.side == "S"


def test_real_file_known_client_and_server_events_classified_correctly():
    """Hardcoded, independent check against tags confirmed (via grep) to
    actually appear in sample/dev_Ferrara.pgtp.

    This intentionally does NOT call classify_event_side() and compare its
    result to itself (that would be tautological, since EventNode.side is
    populated by that very function during parsing). Instead it asserts
    literal "C"/"S" expectations derived by inspecting the real file.
    """
    sample_path = SAMPLE_DIR / "dev_Ferrara.pgtp"
    _require_sample(sample_path)
    project = load_project(sample_path)

    all_events = []
    for page in project.pages:
        for node in _iter_all_nodes(page):
            all_events.extend(node.events)

    sides_by_tag = {}
    for event in all_events:
        sides_by_tag.setdefault(event.tag_name, event.side)

    # Confirmed present via: grep -oE '<On[A-Za-z_]+' sample/dev_Ferrara.pgtp
    expected_client_side_tags = [
        "OnEditFormLoaded",
        "OnInsertFormLoaded",
        "OnEditFormEditorValueChanged",
        "OnInsertFormEditorValueChanged",
    ]
    expected_server_side_tags = [
        "OnPreparePage",
        "OnPageLoaded",
        "OnCalculateFields",
    ]

    for tag in expected_client_side_tags:
        assert tag in sides_by_tag, f"expected tag {tag!r} to appear in {sample_path.name}"
        assert sides_by_tag[tag] == "C"

    for tag in expected_server_side_tags:
        assert tag in sides_by_tag, f"expected tag {tag!r} to appear in {sample_path.name}"
        assert sides_by_tag[tag] == "S"


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


from pgtp_editor.ui.properties_panel import _count_functions


def _iter_all_events(project):
    for page in project.pages:
        for node in _iter_all_nodes(page):
            yield from node.events


def test_real_on_edit_form_loaded_bodies_function_counts():
    """Grounds _count_functions directly against real OnEditFormLoaded
    bodies in dev_Ferrara.pgtp: a 3561-character body is expected to
    yield 14 (5 named functions + ~9 anonymous callbacks) and a
    3572-character body is expected to yield 12, matching the design
    spec's own grounding pass (2026-07-12-pgtp-editor-properties-panel-
    design.md, §3.3)."""
    sample_path = SAMPLE_DIR / "dev_Ferrara.pgtp"
    _require_sample(sample_path)
    project = load_project(sample_path)

    edit_form_loaded_bodies = [
        event.text
        for event in _iter_all_events(project)
        if event.tag_name == "OnEditFormLoaded"
    ]
    assert edit_form_loaded_bodies, "expected at least one OnEditFormLoaded body in dev_Ferrara.pgtp"

    body_3561 = next((t for t in edit_form_loaded_bodies if len(t) == 3561), None)
    body_3572 = next((t for t in edit_form_loaded_bodies if len(t) == 3572), None)
    assert body_3561 is not None, "expected a 3561-character OnEditFormLoaded body"
    assert body_3572 is not None, "expected a 3572-character OnEditFormLoaded body"
    assert _count_functions(body_3561) == 14
    assert _count_functions(body_3572) == 12


def test_real_on_calculate_fields_body_has_zero_functions():
    """A real OnCalculateFields body in dev_Ferrara.pgtp is a bare PHP
    conditional with no function declarations at all -- "Functions: 0"
    is the correct, expected result, not an edge case to special-case
    away (design spec §3.3)."""
    sample_path = SAMPLE_DIR / "dev_Ferrara.pgtp"
    _require_sample(sample_path)
    project = load_project(sample_path)

    zero_function_bodies = [
        event.text
        for event in _iter_all_events(project)
        if event.tag_name == "OnCalculateFields" and _count_functions(event.text) == 0
    ]
    assert zero_function_bodies, "expected at least one zero-function OnCalculateFields body"


from pathlib import Path

import pytest

from pgtp_editor.model.parser import load_project

_SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"


def _load_dev_ferrara():
    path = _SAMPLE_DIR / "dev_Ferrara.pgtp"
    if not path.exists():
        pytest.skip(f"sample fixture not present on disk: {path}")
    return load_project(path)


def test_real_sample_column_sub_elements_populated():
    project = _load_dev_ferrara()

    # The top-level development_equipment page carries the columns verified
    # in spec §3/§5.2: `wbs1` (Lookup pr.x_wbs + dynamicCombobox edit) and
    # `id` (numeric Format nested in ViewProperties).
    page = next(p for p in project.pages if p.file_name == "development_equipment")
    columns = {c.field_name: c for c in page.columns}

    wbs1 = columns["wbs1"]
    assert wbs1.lookup is not None
    assert wbs1.lookup.attrib["tableName"] == "pr.x_wbs"
    assert wbs1.lookup.attrib["linkFieldName"] == "wbs_id"
    assert wbs1.lookup.attrib["displayFieldName"] == "wbs_name"
    assert wbs1.edit_properties is not None
    assert wbs1.edit_properties.attrib["type"] == "dynamicCombobox"

    id_col = columns["id"]
    assert id_col.format is not None
    assert id_col.format.attrib["type"] == "number"
    assert id_col.view_properties is not None
