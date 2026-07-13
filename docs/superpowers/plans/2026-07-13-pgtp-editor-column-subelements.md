# PGTP Editor — Column Sub-element Model + Differ Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `ColumnNode` four new optional fields (`format`, `lookup`, `view_properties`, `edit_properties`) parsed from a `ColumnPresentation`'s presentation sub-elements, and teach the differ to compare those sub-elements bracket-per-bracket, value-per-value — the pure data foundation for the Interface Text Collection feature area (no UI).

**Architecture:** A new `ChildElement` dataclass in `pgtp_editor/model/nodes.py` (holding `attrib`, `sourceline`, and the retained lxml `element`) models one optional single-occurrence presentation child. `_parse_columns` in `pgtp_editor/model/parser.py` populates the four `ColumnNode` fields — critically locating `<Format>` via `ViewProperties/Format` (it is always a grandchild, never a direct child, of `ColumnPresentation`). A new `_compare_child_element` helper in `pgtp_editor/diff/differ.py`, called four times from `_compare_columns` per matched column pair, emits `added`/`removed`/`changed` `Difference` records mirroring `_compare_attributes` exactly and threading `ambiguous`, using four new `node_kind` strings (`"format"`, `"lookup"`, `"view_properties"`, `"edit_properties"`). Write-back of these new difference kinds through `pgtp_editor/diff/apply.py` is deliberately scoped OUT and locked in as a clean-failure guard test (see spec §4.6).

**Tech Stack:** Python 3.10+, lxml, pytest (no pytest-qt — every file this plan touches is Qt-free), dataclasses, the existing `pgtp_editor.model` and `pgtp_editor.diff` packages.

---

## Before you start

This plan builds on already-merged code. It assumes these exist and does **not** re-implement them:

- `pgtp_editor.model.nodes.ColumnNode` — `@dataclass` with `identity: str`, `attrib: dict`, `sourceline: int | None = None`, `element: "etree._Element | None" = None`, and a `field_name` property returning `attrib.get("fieldName")`.
- Sibling nodes `PageNode`, `DetailNode`, `EventNode` in the same file, using `@dataclass`, `field(default_factory=...)` for list fields, and the `element: "etree._Element | None" = None` typing convention.
- `pgtp_editor.model.parser._parse_columns(container_el, parent_identity) -> list[ColumnNode]` — builds one `ColumnNode` per `<ColumnPresentation>` from `container_el.find("ColumnPresentations")`.
- `pgtp_editor.model.parser._build_project_model(tree, source_description) -> ProjectModel` and `load_project(path) -> ProjectModel`.
- `pgtp_editor.diff.records.Difference` — `@dataclass` with `kind`, `path: list[str]`, `node_kind`, `attribute`, `old_value`, `new_value`, `ambiguous: bool = False`. `node_kind` is an unconstrained `str`, so adding new values needs no change to this file.
- `pgtp_editor.diff.differ.diff_project`, `compare_block(source_node, target_node, path, node_kind, ambiguous=False)`, `_compare_attributes(..., ambiguous=False)`, and `_compare_columns(source_node, target_node, path, ambiguous=False)`. `_compare_columns` matches columns by `field_name`, emits `added`/`removed` whole-column records, and calls `_compare_attributes` for matched pairs.
- `pgtp_editor.diff.apply.apply_differences(target, differences) -> ApplyResult` with `ApplyResult(applied, failed)` and `ApplyFailure(difference, message)`. `_apply_one` raises `_ApplyError` (caught → `ApplyFailure`) for any `node_kind` it does not recognize in the `added`/`changed` branches.

**Empirical fact this plan depends on (verified against both sample files):** `<Format>` is *never* a direct child of `<ColumnPresentation>` — it is always nested inside `<ViewProperties>` (887/887 in `dev_Ferrara.pgtp`, 1175/1175 in the FRENCH sample). So it must be found via `ViewProperties/Format`, not `Format`. See spec §3.2.

This plan covers **no UI**, does **not** wire the "Manage Captions..." stub, does **not** add LLM translation, and does **not** extend `apply.py` (write-back of sub-element changes is scoped out — see spec §4.6 and Task 5 here). Full out-of-scope list: spec §2.2.

Refer to `docs/superpowers/specs/2026-07-13-pgtp-editor-column-subelements-design.md` throughout.

---

### Task 1: `ChildElement` dataclass + four `ColumnNode` fields

**Files:**
- Modify: `pgtp_editor/model/nodes.py`
- Test: `tests/model/test_nodes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/model/test_nodes.py (append)
from pgtp_editor.model.nodes import ChildElement, ColumnNode


def test_child_element_holds_attrib_sourceline_element():
    child = ChildElement(attrib={"type": "number"}, sourceline=42, element=None)
    assert child.attrib == {"type": "number"}
    assert child.sourceline == 42
    assert child.element is None


def test_child_element_defaults_sourceline_and_element_to_none():
    child = ChildElement(attrib={"type": "text"})
    assert child.sourceline is None
    assert child.element is None


def test_column_node_sub_element_fields_default_to_none():
    col = ColumnNode(identity="tag", attrib={"fieldName": "tag"})
    assert col.format is None
    assert col.lookup is None
    assert col.view_properties is None
    assert col.edit_properties is None


def test_column_node_accepts_sub_element_fields():
    fmt = ChildElement(attrib={"type": "number", "decimalSeparator": "."})
    edit = ChildElement(attrib={"type": "textBox", "placeholder": "Hi"})
    col = ColumnNode(
        identity="tag",
        attrib={"fieldName": "tag"},
        format=fmt,
        edit_properties=edit,
    )
    assert col.format is fmt
    assert col.edit_properties is edit
    # placeholder is reached through edit_properties.attrib, no dedicated field:
    assert col.edit_properties.attrib.get("placeholder") == "Hi"
    assert col.lookup is None
    assert col.view_properties is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/model/test_nodes.py -v`
Expected: FAIL with `ImportError: cannot import name 'ChildElement' from 'pgtp_editor.model.nodes'`

- [ ] **Step 3: Add `ChildElement` and the four `ColumnNode` fields**

In `pgtp_editor/model/nodes.py`, add the `ChildElement` dataclass immediately **before** the existing `ColumnNode` dataclass (so `ColumnNode`'s field annotations can reference it), and add the four fields to `ColumnNode`:

```python
@dataclass
class ChildElement:
    """A single-occurrence optional presentation child of a ColumnPresentation
    (one of <Format>, <Lookup>, <ViewProperties>, <EditProperties>).

    Holds only the child's own attributes plus a reference to the retained
    real lxml element (for future write-back). Does not descend into the
    child's own children: a <Format> nested inside a <ViewProperties> is
    captured separately as ColumnNode.format (see parser._parse_columns),
    not by walking into ColumnNode.view_properties.
    """
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None


@dataclass
class ColumnNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None
    format: "ChildElement | None" = None
    lookup: "ChildElement | None" = None
    view_properties: "ChildElement | None" = None
    edit_properties: "ChildElement | None" = None

    @property
    def field_name(self) -> str | None:
        return self.attrib.get("fieldName")
```

(Replace the existing `ColumnNode` definition with the version above — it preserves `identity`, `attrib`, `sourceline`, `element`, and the `field_name` property verbatim and only adds four fields.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/model/test_nodes.py -v`
Expected: PASS (all 4 new tests pass; any pre-existing tests in the file still pass)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/model/nodes.py tests/model/test_nodes.py
git commit -m "feat(model): add ChildElement dataclass and ColumnNode sub-element fields"
```

---

### Task 2: `_parse_columns` populates the four sub-element fields

**Files:**
- Modify: `pgtp_editor/model/parser.py`
- Test: `tests/model/test_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/model/test_parser.py (append — reuses the module's existing
# write_pgtp(tmp_path, xml_text) helper and load_project import)

COLUMNS_WITH_SUBELEMENTS = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="dev_equipment" tableName="pr.equipment" caption="Equipment">
        <ColumnPresentations>
          <ColumnPresentation fieldName="all_four" caption="All Four">
            <Lookup tableName="pr.x_wbs" linkFieldName="wbs_id" displayFieldName="wbs_name"/>
            <ViewProperties type="text" maxLength="75">
              <Format type="number" decimalSeparator="."/>
            </ViewProperties>
            <EditProperties type="textBox" maxLength="30" placeholder="Hi"/>
          </ColumnPresentation>
          <ColumnPresentation fieldName="none_present" caption="None"/>
          <ColumnPresentation fieldName="some_present" caption="Some">
            <ViewProperties type="text"/>
            <EditProperties type="dynamicCombobox"/>
          </ColumnPresentation>
        </ColumnPresentations>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def _columns_by_field_name(tmp_path):
    path = write_pgtp(tmp_path, COLUMNS_WITH_SUBELEMENTS)
    project = load_project(path)
    columns = project.pages[0].columns
    return {c.field_name: c for c in columns}


def test_parse_columns_all_four_sub_elements_populated(tmp_path):
    col = _columns_by_field_name(tmp_path)["all_four"]

    assert col.lookup is not None
    assert col.lookup.attrib["tableName"] == "pr.x_wbs"
    assert col.lookup.attrib["linkFieldName"] == "wbs_id"
    assert col.lookup.attrib["displayFieldName"] == "wbs_name"

    assert col.view_properties is not None
    assert col.view_properties.attrib["type"] == "text"
    assert col.view_properties.attrib["maxLength"] == "75"

    assert col.edit_properties is not None
    assert col.edit_properties.attrib["type"] == "textBox"
    # placeholder falls out of the generic EditProperties capture, no field:
    assert col.edit_properties.attrib.get("placeholder") == "Hi"

    # sourceline populated, real element retained:
    assert col.lookup.sourceline is not None
    assert col.edit_properties.element is not None


def test_parse_columns_format_nested_in_view_properties_is_captured(tmp_path):
    # Regression guard: <Format> is a GRANDCHILD (inside ViewProperties),
    # never a direct child of ColumnPresentation, so a naive
    # col_el.find("Format") would leave this None. It must be found via
    # ViewProperties/Format. See spec §3.2.
    col = _columns_by_field_name(tmp_path)["all_four"]
    assert col.format is not None
    assert col.format.attrib["type"] == "number"
    assert col.format.attrib["decimalSeparator"] == "."
    # view_properties captures only its OWN attribs, not Format's:
    assert "decimalSeparator" not in col.view_properties.attrib


def test_parse_columns_none_present_leaves_all_four_none(tmp_path):
    col = _columns_by_field_name(tmp_path)["none_present"]
    assert col.format is None
    assert col.lookup is None
    assert col.view_properties is None
    assert col.edit_properties is None


def test_parse_columns_some_present_gives_correct_mix(tmp_path):
    col = _columns_by_field_name(tmp_path)["some_present"]
    assert col.view_properties is not None
    assert col.edit_properties is not None
    assert col.format is None   # no nested <Format>
    assert col.lookup is None   # no <Lookup>
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/model/test_parser.py -v`
Expected: FAIL — the new tests fail with `AttributeError` or `assert None is not None`, because `_parse_columns` does not yet populate the sub-element fields (they stay at their `None` default).

- [ ] **Step 3: Extend `_parse_columns` and add the `_child_element` helper**

In `pgtp_editor/model/parser.py`, first add `ChildElement` to the existing model-import block:

```python
from pgtp_editor.model.nodes import (
    ChildElement,
    ColumnNode,
    DetailNode,
    EventNode,
    PageNode,
    ProjectModel,
    classify_event_side,
)
```

Then replace the `ColumnNode(...)` construction inside `_parse_columns` to populate the four fields, and add a module-level `_child_element` helper. The full updated `_parse_columns` plus the new helper:

```python
def _parse_columns(container_el, parent_identity) -> list[ColumnNode]:
    columns_container = container_el.find("ColumnPresentations")
    if columns_container is None:
        return []

    columns = []
    for col_el in columns_container.findall("ColumnPresentation"):
        field_name = col_el.get("fieldName", "") or ""
        identity = _make_identity(parent_identity, field_name)
        columns.append(
            ColumnNode(
                identity=identity,
                attrib=dict(col_el.attrib),
                sourceline=col_el.sourceline,
                element=col_el,
                # <Format> is always nested inside <ViewProperties>, never a
                # direct child of <ColumnPresentation> -- see spec §3.2.
                format=_child_element(col_el.find("ViewProperties/Format")),
                lookup=_child_element(col_el.find("Lookup")),
                view_properties=_child_element(col_el.find("ViewProperties")),
                edit_properties=_child_element(col_el.find("EditProperties")),
            )
        )
    return columns


def _child_element(el):
    """Wrap an optional sub-element into a ChildElement, or None if absent.

    `el` is an lxml element or None (the result of an ElementTree.find).
    Absent sub-elements (find returned None) naturally leave the ColumnNode
    field at its None default.
    """
    if el is None:
        return None
    return ChildElement(attrib=dict(el.attrib), sourceline=el.sourceline, element=el)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/model/test_parser.py -v`
Expected: PASS (the 4 new tests pass; all pre-existing parser tests still pass)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/model/parser.py tests/model/test_parser.py
git commit -m "feat(model): parse Format/Lookup/View/EditProperties into ColumnNode"
```

---

### Task 3: Real-sample integration assertion for the new fields

**Files:**
- Modify: `tests/model/test_parser_real_samples.py`

- [ ] **Step 1: Write the test (skips if the gitignored sample is absent)**

```python
# tests/model/test_parser_real_samples.py (append)
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
```

> **Note if the assertions mismatch at execution time:** the `wbs1`/`id` attribute values above were read from the real `sample/dev_Ferrara.pgtp` at planning time (spec §3.2, §5.2). If the on-disk sample differs, do NOT weaken the test to pass — re-grep the sample (`grep -n 'fieldName="wbs1"' sample/dev_Ferrara.pgtp` and read the following `<Lookup>`/`<EditProperties>`/`<ViewProperties>` lines) and correct the expected values to the real ones, keeping the assertions specific.

- [ ] **Step 2: Run the test**

Run: `pytest tests/model/test_parser_real_samples.py::test_real_sample_column_sub_elements_populated -v`
Expected: PASS (or SKIP if `sample/dev_Ferrara.pgtp` is not on disk)

- [ ] **Step 3: Commit**

```bash
git add tests/model/test_parser_real_samples.py
git commit -m "test(model): assert real-sample column sub-elements parse correctly"
```

---

### Task 4: `_compare_child_element` + four call-sites in `_compare_columns`

**Files:**
- Modify: `pgtp_editor/diff/differ.py`
- Test: `tests/diff/test_differ.py`

- [ ] **Step 1: Write the failing tests**

These reuse the existing `make_page`/`make_column` helpers already defined near the top of `tests/diff/test_differ.py` (see the differ-engine plan). Add a `ChildElement` import and a local `make_child` helper, then one added/removed/changed test per sub-element kind plus no-change, multi-key, and ambiguous-propagation tests.

```python
# tests/diff/test_differ.py (append)
from pgtp_editor.model.nodes import ChildElement, DetailNode


def make_child(**attrib):
    return ChildElement(attrib=dict(attrib))


def _one_column_pair(source_col, target_col):
    """Wrap a source/target ColumnNode pair into matching single-column pages
    and return diff_project's result."""
    source_page = make_page("shared_page")
    source_page.columns = [source_col]
    target_page = make_page("shared_page")
    target_page.columns = [target_col]
    return diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))


# ---- Format ----------------------------------------------------------------

def test_sub_element_format_added():
    src = make_column("amount", caption="Amount")
    src.format = make_child(type="number", decimalSeparator=".")
    tgt = make_column("amount", caption="Amount")

    result = _one_column_pair(src, tgt)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.node_kind == "format"
    assert diff.path == ["shared_page", "amount", "Format"]
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is src.format
    assert diff.ambiguous is False


def test_sub_element_format_removed():
    src = make_column("amount", caption="Amount")
    tgt = make_column("amount", caption="Amount")
    tgt.format = make_child(type="number", decimalSeparator=".")

    result = _one_column_pair(src, tgt)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.node_kind == "format"
    assert diff.path == ["shared_page", "amount", "Format"]
    assert diff.old_value is tgt.format
    assert diff.new_value is None


def test_sub_element_format_attribute_changed():
    src = make_column("amount", caption="Amount")
    src.format = make_child(type="number", decimalSeparator=",")
    tgt = make_column("amount", caption="Amount")
    tgt.format = make_child(type="number", decimalSeparator=".")

    result = _one_column_pair(src, tgt)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.node_kind == "format"
    assert diff.path == ["shared_page", "amount", "Format"]
    assert diff.attribute == "decimalSeparator"
    assert diff.old_value == "."
    assert diff.new_value == ","


# ---- Lookup ----------------------------------------------------------------

def test_sub_element_lookup_added():
    src = make_column("wbs1")
    src.lookup = make_child(tableName="pr.x_wbs")
    tgt = make_column("wbs1")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "added"
    assert result[0].node_kind == "lookup"
    assert result[0].path == ["shared_page", "wbs1", "Lookup"]
    assert result[0].new_value is src.lookup


def test_sub_element_lookup_removed():
    src = make_column("wbs1")
    tgt = make_column("wbs1")
    tgt.lookup = make_child(tableName="pr.x_wbs")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "removed"
    assert result[0].node_kind == "lookup"
    assert result[0].old_value is tgt.lookup


def test_sub_element_lookup_attribute_changed():
    src = make_column("wbs1")
    src.lookup = make_child(tableName="pr.x_wbs_new")
    tgt = make_column("wbs1")
    tgt.lookup = make_child(tableName="pr.x_wbs")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "changed"
    assert result[0].node_kind == "lookup"
    assert result[0].attribute == "tableName"
    assert result[0].old_value == "pr.x_wbs"
    assert result[0].new_value == "pr.x_wbs_new"


# ---- ViewProperties --------------------------------------------------------

def test_sub_element_view_properties_added():
    src = make_column("descr")
    src.view_properties = make_child(type="text")
    tgt = make_column("descr")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "added"
    assert result[0].node_kind == "view_properties"
    assert result[0].path == ["shared_page", "descr", "ViewProperties"]


def test_sub_element_view_properties_removed():
    src = make_column("descr")
    tgt = make_column("descr")
    tgt.view_properties = make_child(type="text")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "removed"
    assert result[0].node_kind == "view_properties"


def test_sub_element_view_properties_attribute_changed():
    src = make_column("descr")
    src.view_properties = make_child(type="text", maxLength="100")
    tgt = make_column("descr")
    tgt.view_properties = make_child(type="text", maxLength="75")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "changed"
    assert result[0].node_kind == "view_properties"
    assert result[0].attribute == "maxLength"
    assert result[0].old_value == "75"
    assert result[0].new_value == "100"


# ---- EditProperties --------------------------------------------------------

def test_sub_element_edit_properties_added():
    src = make_column("tag")
    src.edit_properties = make_child(type="textBox", placeholder="Tag no.")
    tgt = make_column("tag")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "added"
    assert result[0].node_kind == "edit_properties"
    assert result[0].path == ["shared_page", "tag", "EditProperties"]


def test_sub_element_edit_properties_removed():
    src = make_column("tag")
    tgt = make_column("tag")
    tgt.edit_properties = make_child(type="textBox")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "removed"
    assert result[0].node_kind == "edit_properties"


def test_sub_element_edit_properties_placeholder_changed():
    src = make_column("tag")
    src.edit_properties = make_child(type="textBox", placeholder="New hint")
    tgt = make_column("tag")
    tgt.edit_properties = make_child(type="textBox", placeholder="Old hint")

    result = _one_column_pair(src, tgt)
    assert len(result) == 1
    assert result[0].kind == "changed"
    assert result[0].node_kind == "edit_properties"
    assert result[0].attribute == "placeholder"
    assert result[0].old_value == "Old hint"
    assert result[0].new_value == "New hint"


# ---- No-change, multi-key, ambiguous propagation ---------------------------

def test_sub_element_no_change_emits_nothing():
    src = make_column("tag")
    src.edit_properties = make_child(type="textBox", placeholder="Same")
    src.view_properties = make_child(type="text")
    tgt = make_column("tag")
    tgt.edit_properties = make_child(type="textBox", placeholder="Same")
    tgt.view_properties = make_child(type="text")

    assert _one_column_pair(src, tgt) == []


def test_sub_element_multiple_changed_keys_emits_one_record_per_key_sorted():
    src = make_column("amount")
    src.format = make_child(type="number", decimalSeparator=",", thousandSeparator=".")
    tgt = make_column("amount")
    tgt.format = make_child(type="number", decimalSeparator=".", thousandSeparator=",")

    result = _one_column_pair(src, tgt)
    assert len(result) == 2
    # sorted by attribute key: decimalSeparator before thousandSeparator
    assert [d.attribute for d in result] == ["decimalSeparator", "thousandSeparator"]
    assert all(d.node_kind == "format" and d.kind == "changed" for d in result)


def test_sub_element_ambiguous_flag_propagates_from_enclosing_pair():
    # Two source + two target Details share (tableName, caption), forcing the
    # duplicate-sibling positional-pairing fallback (ambiguous=True), which
    # threads through to a column pair's sub-element diff.
    def detail_with_format(sep):
        col = make_column("amount")
        col.format = make_child(type="number", decimalSeparator=sep)
        d = DetailNode(identity="pr.op/Op", attrib={"tableName": "pr.op", "caption": "Op"})
        d.columns = [col]
        return d

    source_page = make_page("shared_page")
    source_page.details = [detail_with_format(","), detail_with_format(",")]
    target_page = make_page("shared_page")
    target_page.details = [detail_with_format("."), detail_with_format(".")]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    # Each of the two positionally-paired Details yields one Format change.
    format_diffs = [d for d in result if d.node_kind == "format"]
    assert len(format_diffs) == 2
    assert all(d.ambiguous is True for d in format_diffs)
    assert all(d.attribute == "decimalSeparator" for d in format_diffs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_differ.py -v`
Expected: FAIL — sub-elements are not compared yet, so the added/removed/changed tests get an empty result (`len(result) == 1` fails), and the ambiguous test finds no `"format"` diffs.

- [ ] **Step 3: Add `_compare_child_element` and wire four call-sites into `_compare_columns`**

In `pgtp_editor/diff/differ.py`, add the new helper (place it after `_compare_columns`):

```python
def _compare_child_element(
    source_child, target_child, path, node_kind, tag_name, ambiguous=False
) -> list[Difference]:
    """Compare one optional sub-element slot (Format/Lookup/ViewProperties/
    EditProperties) of a matched column pair, bracket-per-bracket,
    value-per-value.

    `source_child`/`target_child` are each a ChildElement or None.
    `path` is the enclosing column's path; `node_kind` is the sub-element
    kind ("format"/"lookup"/"view_properties"/"edit_properties"); `tag_name`
    is the XML tag used as the trailing path segment ("Format" etc.).

    - present on source only -> one `added` record (whole ChildElement)
    - present on target only -> one `removed` record (whole ChildElement)
    - present on both        -> one `changed` record per differing attrib key
    - absent on both         -> nothing
    Mirrors _compare_attributes / _compare_columns exactly, threading
    `ambiguous`.
    """
    child_path = path + [tag_name]

    if source_child is not None and target_child is None:
        return [
            Difference(
                kind="added",
                path=child_path,
                node_kind=node_kind,
                attribute=None,
                old_value=None,
                new_value=source_child,
                ambiguous=ambiguous,
            )
        ]
    if source_child is None and target_child is not None:
        return [
            Difference(
                kind="removed",
                path=child_path,
                node_kind=node_kind,
                attribute=None,
                old_value=target_child,
                new_value=None,
                ambiguous=ambiguous,
            )
        ]
    if source_child is None and target_child is None:
        return []

    differences: list[Difference] = []
    all_keys = set(source_child.attrib.keys()) | set(target_child.attrib.keys())
    for key in sorted(all_keys):
        source_value = source_child.attrib.get(key)
        target_value = target_child.attrib.get(key)
        if source_value != target_value:
            differences.append(
                Difference(
                    kind="changed",
                    path=child_path,
                    node_kind=node_kind,
                    attribute=key,
                    old_value=target_value,
                    new_value=source_value,
                    ambiguous=ambiguous,
                )
            )
    return differences
```

Then, in `_compare_columns`, extend the **matched-pair** `else:` branch (the one that currently only calls `_compare_attributes`) to also compare the four sub-element slots. The updated branch:

```python
        else:
            differences.extend(
                _compare_attributes(
                    source_column, target_column, path=column_path, node_kind="column", ambiguous=ambiguous
                )
            )
            for source_child, target_child, node_kind, tag_name in (
                (source_column.format, target_column.format, "format", "Format"),
                (source_column.lookup, target_column.lookup, "lookup", "Lookup"),
                (
                    source_column.view_properties,
                    target_column.view_properties,
                    "view_properties",
                    "ViewProperties",
                ),
                (
                    source_column.edit_properties,
                    target_column.edit_properties,
                    "edit_properties",
                    "EditProperties",
                ),
            ):
                differences.extend(
                    _compare_child_element(
                        source_child,
                        target_child,
                        path=column_path,
                        node_kind=node_kind,
                        tag_name=tag_name,
                        ambiguous=ambiguous,
                    )
                )
```

Leave the added-column and removed-column branches unchanged: a column present on only one side already emits a whole-`ColumnNode` record whose `new_value`/`old_value` carries the sub-element fields, so there is nothing extra to compare.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_differ.py -v`
Expected: PASS (all new sub-element tests pass; every pre-existing differ test still passes)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/differ.py tests/diff/test_differ.py
git commit -m "feat(diff): compare column Format/Lookup/View/EditProperties sub-elements"
```

---

### Task 5: Apply guard test — sub-element write-back is scoped out (fails cleanly)

Per spec §4.6, this sub-project does **not** teach `apply.py` to write sub-element changes back. `apply.py` is left unmodified. This task locks in that the new difference kinds fail *cleanly* (recorded as `ApplyFailure`, never silently mis-applied) rather than leaving the behavior undocumented.

**Files:**
- Modify: `tests/diff/test_apply.py`
- Modify: none of `pgtp_editor/` (deliberately — see spec §4.6)

- [ ] **Step 1: Write the guard test**

```python
# tests/diff/test_apply.py (append — reuses the module's build_project(xml_text)
# helper and the SIMPLE_TARGET fixture, plus its apply_differences/Difference imports)

def test_apply_sub_element_changed_attribute_fails_cleanly():
    # A changed Format attribute is NOT applied by this sub-project (spec §4.6:
    # sub-element write-back is scoped out and left a documented limitation).
    # It must land in ApplyResult.failed, not silently corrupt the tree.
    target = build_project(SIMPLE_TARGET)
    diff = Difference(
        kind="changed",
        path=["development_equipment", "some_field", "Format"],
        node_kind="format",
        attribute="decimalSeparator",
        old_value=".",
        new_value=",",
    )

    result = apply_differences(target, [diff])

    assert result.applied == []
    assert len(result.failed) == 1
    assert result.failed[0].difference is diff
    assert "format" in result.failed[0].message


def test_apply_sub_element_added_fails_cleanly():
    # An added Lookup sub-element is likewise not applied (spec §4.6).
    target = build_project(SIMPLE_TARGET)
    diff = Difference(
        kind="added",
        path=["development_equipment", "some_field", "Lookup"],
        node_kind="lookup",
        attribute=None,
        old_value=None,
        new_value=None,  # value irrelevant: it fails before dereferencing it
    )

    result = apply_differences(target, [diff])

    assert result.applied == []
    assert len(result.failed) == 1
    assert result.failed[0].difference is diff
    assert "lookup" in result.failed[0].message
```

> **Judgment-call note for the implementer:** `_apply_added` builds its `_ApplyError` message as `f"unsupported node_kind for added: {diff.node_kind!r}"`, and `_apply_changed_attribute` as `f"unsupported node_kind for attribute change: {diff.node_kind!r}"`. Both embed the `node_kind` (`'format'` / `'lookup'`) via `!r`, so the substring assertions (`"format" in ...`, `"lookup" in ...`) hold. If at execution time the real messages differ, assert against the actual `_ApplyError` text rather than weakening the test to `len(result.failed) == 1` alone — the point is to prove it fails *and* names the offending kind.

- [ ] **Step 2: Run the guard test**

Run: `pytest tests/diff/test_apply.py -v`
Expected: PASS — the two new tests pass immediately, because `apply.py` already raises `_ApplyError` (→ `ApplyFailure`) for any `node_kind` outside its known set in the `added`/`changed` branches. No production code change. All pre-existing apply tests still pass.

- [ ] **Step 3: Commit**

```bash
git add tests/diff/test_apply.py
git commit -m "test(diff): lock in that sub-element diffs fail cleanly in apply (scoped out)"
```

---

### Task 6: Self-diff regression — no spurious sub-element differences

Confirm the new comparison does not fire when a real file is diffed against itself. The existing `tests/diff/test_differ_integration.py` already asserts `diff_project(m, m) == []` for both sample files; re-running it after Tasks 1–4 is the regression guard (if `_compare_child_element` misbehaved — e.g. compared `Format` against `ViewProperties`, or reported a present-on-both sub-element as changed — the self-diff would go non-empty). This task verifies that guard still holds and adds an explicit note pinning it to this sub-project.

**Files:**
- Modify: `tests/diff/test_differ_integration.py`

- [ ] **Step 1: Add a docstring note tying the existing self-diff tests to this sub-project**

At the top of `tests/diff/test_differ_integration.py`, append a sentence to the module docstring (do not change the existing tests — they already cover both samples):

```python
"""Regression tests: diffing a real sample file against itself must produce
an empty list. This is a strong sanity check that the algorithm doesn't
spuriously report differences from e.g. dict-ordering assumptions or
unstable duplicate-pairing, when there are none.

Also guards the Interface Text Collection sub-project 1 addition: since the
real samples are dense with Format/Lookup/ViewProperties/EditProperties
sub-elements, a self-diff staying empty proves _compare_child_element does
not spuriously fire (e.g. by comparing a present-on-both sub-element as
changed, or crossing Format against ViewProperties). See
docs/superpowers/specs/2026-07-13-pgtp-editor-column-subelements-design.md §5.5.

Requires sample/*.pgtp to be present on disk (gitignored — see Task 10 of
docs/superpowers/plans/2026-07-12-pgtp-editor-differ-engine.md for how to
populate it if missing).
"""
```

- [ ] **Step 2: Run the self-diff regression (both samples)**

Run: `pytest tests/diff/test_differ_integration.py -v`
Expected: PASS (both `test_dev_ferrara_self_diff_is_empty` and `test_sdman_renco_strikes_back_self_diff_is_empty` pass — or SKIP if the gitignored samples are not on disk).

- [ ] **Step 3: Commit**

```bash
git add tests/diff/test_differ_integration.py
git commit -m "test(diff): note self-diff guards new sub-element comparison"
```

---

### Task 7: Full-suite verification

**Files:**
- Modify: none

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -q`
Expected: PASS — every test green (real-sample tests SKIP if the gitignored `sample/*.pgtp` files are absent; nothing FAILS or ERRORS). No pre-existing model/parser/differ/apply test changed behavior, since this sub-project is purely additive.

- [ ] **Step 2: Confirm no Qt import crept into the touched files**

Run: `grep -rniE "PySide6|PyQt|from .*qt" pgtp_editor/model/nodes.py pgtp_editor/model/parser.py pgtp_editor/diff/differ.py`
Expected: no output (these files stay Qt-free — spec §4.8).

- [ ] **Step 3: Final commit if anything is uncommitted**

```bash
git status
# if clean, nothing to do; otherwise:
git add -A
git commit -m "chore: finalize column sub-element model + differ extension"
```

---

## Build order recap

1. **Task 1** — `ChildElement` dataclass + four `ColumnNode` fields.
2. **Task 2** — `_parse_columns` populates them (incl. `Format` via `ViewProperties/Format`).
3. **Task 3** — real-sample integration assertion (`wbs1`/`id`).
4. **Task 4** — `_compare_child_element` + four `_compare_columns` call-sites (per-kind tests, no-change, multi-key, ambiguous propagation).
5. **Task 5** — apply guard test (sub-element write-back scoped out, fails cleanly).
6. **Task 6** — self-diff regression note + re-run.
7. **Task 7** — full-suite verification + Qt-free check.
