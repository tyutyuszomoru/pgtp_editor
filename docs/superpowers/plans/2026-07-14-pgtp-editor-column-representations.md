# Column representation-visibility in Properties — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a Column is selected, the Properties panel also shows its visibility across the 10 fixed representation lists (`List`, `View`, `Edit`, `Insert`, `QuickFilter`, `FilterBuilder`, `Print`, `Export`, `Compare`, `MultiEdit`) from the Page's `<Columns>` block — `visible` / `hidden` / `— (not listed)`, each navigating to that column's `<Column>` entry line.

**Architecture:** Parse the sibling `<Columns>` block once per container into a `field_name -> list[RepresentationVisibility]` index and attach the per-column slice to each `ColumnNode` (keeping `ColumnNode` self-contained — the Qt-free Properties row-builder just reads it). A new `_rows_for_column` appends a divider + one row per representation.

**Tech Stack:** Python 3.13, lxml, PySide6, pytest, pytest-qt. Suite runs headless offscreen with `--timeout=60`.

---

## Current-state facts (confirmed by reading this worktree)

- `pgtp_editor/model/nodes.py`: `@dataclass ColumnNode` has `identity, attrib, sourceline, element, format, lookup, view_properties, edit_properties` and a `field_name` property. `ChildElement` is a frozen-ish `@dataclass` above it. `field` is imported from `dataclasses` (used by `DetailNode`/`PageNode` list fields).
- `pgtp_editor/model/parser.py`: `_parse_columns(container_el, parent_identity)` finds `container_el.find("ColumnPresentations")`, iterates `ColumnPresentation`, builds each `ColumnNode` (with `_child_element(...)` sub-elements). `_make_identity` exists. `container_el` is the Page (or Detail's inner Page) element, so `container_el.find("Columns")` reaches the sibling block. The module imports `ChildElement, ColumnNode, DetailNode, EventNode, PageNode, ProjectModel, classify_event_side` from `pgtp_editor.model.nodes`.
- `pgtp_editor/ui/properties_panel.py`: Qt-free `RowSpec(property_label, value, target_line, attr_name)` dataclass and `_rows_for_attrib_node`, `_rows_for_detail`, `_rows_for_event` row-builders; `_ROW_BUILDERS = {"page": (...), "detail": (...), "column": (lambda n: _rows_for_attrib_node(n), ...), "event": (...)}`. `_on_row_clicked` navigates when `target_line is not None` and only selects an attribute when `attr_name is not None`.
- Tests: `tests/model/test_parser.py` (has a `write_pgtp(tmp_path, xml)` helper + `load_project` import used by the column-subelement tests), `tests/model/test_parser_real_samples.py` (`SAMPLE_DIR`, `pytest.skip` when absent), `tests/ui/test_properties_panel_rows.py` (imports the row-builders + `RowSpec` directly, Qt-free), `tests/ui/test_properties_panel.py` (pytest-qt panel tests).
- Fixed, uniform across both samples: the 10 representation tags each appear once per `<Columns>` block; `visible="false"` = hidden; entry tags are single-line.

---

## Task 1: `RepresentationVisibility` dataclass + `ColumnNode.representations` field

**Files:**
- Modify: `pgtp_editor/model/nodes.py`
- Test: `tests/model/test_nodes.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/model/test_nodes.py`:

```python
from pgtp_editor.model.nodes import ColumnNode, RepresentationVisibility


def test_representation_visibility_holds_name_visible_sourceline():
    rep = RepresentationVisibility(name="Edit", visible=False, sourceline=42)
    assert (rep.name, rep.visible, rep.sourceline) == ("Edit", False, 42)


def test_representation_visibility_defaults():
    rep = RepresentationVisibility(name="List")
    assert rep.visible is None
    assert rep.sourceline is None


def test_column_node_representations_defaults_to_empty_list():
    col = ColumnNode(identity="c", attrib={"fieldName": "c"})
    assert col.representations == []


def test_column_node_accepts_representations():
    reps = [RepresentationVisibility(name="List", visible=True, sourceline=10)]
    col = ColumnNode(identity="c", attrib={"fieldName": "c"}, representations=reps)
    assert col.representations is reps
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/model/test_nodes.py -v -k "representation"`
Expected: FAIL — `ImportError: cannot import name 'RepresentationVisibility'`.

- [ ] **Step 3: Implement**

In `pgtp_editor/model/nodes.py`, add the dataclass immediately **before** `ColumnNode`:

```python
@dataclass(frozen=True)
class RepresentationVisibility:
    """A column's visibility within one representation list of a Page's
    <Columns> block (List/View/Edit/Insert/QuickFilter/FilterBuilder/Print/
    Export/Compare/MultiEdit).

    visible:    True if shown, False if the entry carries visible="false",
                None if the column has no <Column> entry in this (present)
                representation ("not listed").
    sourceline: the <Column> entry's 1-based source line (for navigation);
                None when visible is None.
    """
    name: str
    visible: bool | None = None
    sourceline: int | None = None
```

Add the field to `ColumnNode` (after `edit_properties`):

```python
    representations: list["RepresentationVisibility"] = field(default_factory=list)
```

(`field` is already imported from `dataclasses`.)

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/model/test_nodes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/model/nodes.py tests/model/test_nodes.py
git commit -m "feat(model): add RepresentationVisibility + ColumnNode.representations"
```

---

## Task 2: Parse the `<Columns>` block into each ColumnNode

**Files:**
- Modify: `pgtp_editor/model/parser.py`
- Test: `tests/model/test_parser.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/model/test_parser.py` (reuses the module's `write_pgtp`/`load_project`):

```python
COLUMNS_BLOCK_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="dev_equipment" tableName="pr.equipment" caption="Equipment">
        <ColumnPresentations>
          <ColumnPresentation fieldName="id" caption="Id"/>
          <ColumnPresentation fieldName="descr" caption="Description"/>
          <ColumnPresentation fieldName="loner" caption="Loner"/>
        </ColumnPresentations>
        <Columns>
          <List>
            <Column fieldName="id"/>
            <Column fieldName="descr" visible="false"/>
          </List>
          <View>
            <Column fieldName="id"/>
            <Column fieldName="descr"/>
          </View>
          <Edit>
            <Column fieldName="id" visible="false"/>
            <Column fieldName="descr"/>
          </Edit>
          <Insert><Column fieldName="id"/><Column fieldName="descr"/></Insert>
          <QuickFilter><Column fieldName="id"/><Column fieldName="descr"/></QuickFilter>
          <FilterBuilder><Column fieldName="id"/><Column fieldName="descr"/></FilterBuilder>
          <Print><Column fieldName="id"/><Column fieldName="descr"/></Print>
          <Export><Column fieldName="id"/><Column fieldName="descr"/></Export>
          <Compare><Column fieldName="id"/><Column fieldName="descr"/></Compare>
          <MultiEdit><Column fieldName="id"/><Column fieldName="descr"/></MultiEdit>
        </Columns>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def _columns_by_field(tmp_path):
    project = load_project(write_pgtp(tmp_path, COLUMNS_BLOCK_PGTP))
    return {c.field_name: c for c in project.pages[0].columns}


def test_representations_length_and_order(tmp_path):
    from pgtp_editor.model.parser import REPRESENTATION_NAMES
    col = _columns_by_field(tmp_path)["id"]
    assert [r.name for r in col.representations] == list(REPRESENTATION_NAMES)


def test_representations_visible_and_hidden(tmp_path):
    reps = {r.name: r for r in _columns_by_field(tmp_path)["id"].representations}
    assert reps["List"].visible is True          # no visible attr -> visible
    assert reps["Edit"].visible is False         # visible="false" -> hidden
    assert reps["List"].sourceline is not None


def test_representations_hidden_for_descr_in_list(tmp_path):
    reps = {r.name: r for r in _columns_by_field(tmp_path)["descr"].representations}
    assert reps["List"].visible is False
    assert reps["View"].visible is True


def test_column_not_listed_in_present_representation_is_none(tmp_path):
    # 'loner' has a ColumnPresentation but appears in no representation list.
    reps = {r.name: r for r in _columns_by_field(tmp_path)["loner"].representations}
    assert reps["List"].visible is None
    assert reps["List"].sourceline is None
    # Still length-10 (every present representation contributes a row).
    assert len(_columns_by_field(tmp_path)["loner"].representations) == 10


def test_no_columns_block_gives_empty_representations(tmp_path):
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project><Presentation><Pages>
  <Page fileName="p" tableName="t" caption="P">
    <ColumnPresentations><ColumnPresentation fieldName="id"/></ColumnPresentations>
  </Page>
</Pages></Presentation></Project>
"""
    project = load_project(write_pgtp(tmp_path, xml))
    assert project.pages[0].columns[0].representations == []


def test_detail_inner_page_columns_get_representations(tmp_path):
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project><Presentation><Pages>
  <Page fileName="p" tableName="t" caption="P">
    <Details><Detail caption="D"><Page tableName="pr.child">
      <ColumnPresentations><ColumnPresentation fieldName="x"/></ColumnPresentations>
      <Columns><List><Column fieldName="x" visible="false"/></List></Columns>
    </Page></Detail></Details>
  </Page>
</Pages></Presentation></Project>
"""
    project = load_project(write_pgtp(tmp_path, xml))
    detail_col = project.pages[0].details[0].columns[0]
    reps = {r.name: r for r in detail_col.representations}
    # Only <List> is present in this block; absent representations are omitted.
    assert reps["List"].visible is False
    assert "Edit" not in reps
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/model/test_parser.py -v -k "representation or columns_block or not_listed or detail_inner"`
Expected: FAIL — `REPRESENTATION_NAMES` import error / `col.representations == []` (field exists but parser never fills it).

- [ ] **Step 3: Implement**

In `pgtp_editor/model/parser.py`:

1. Add `RepresentationVisibility` to the model import block:

```python
from pgtp_editor.model.nodes import (
    ChildElement,
    ColumnNode,
    DetailNode,
    EventNode,
    PageNode,
    ProjectModel,
    RepresentationVisibility,
    classify_event_side,
)
```

2. Add the module-level constant near the top (after the imports):

```python
# The fixed, ordered set of representation lists inside a Page's <Columns>
# block (verified uniform across sample files). Order is the display order.
REPRESENTATION_NAMES = (
    "List", "View", "Edit", "Insert", "QuickFilter",
    "FilterBuilder", "Print", "Export", "Compare", "MultiEdit",
)
```

3. Add the index builder (place after `_child_element`):

```python
def _build_representation_index(container_el) -> dict:
    """Map fieldName -> ordered list[RepresentationVisibility] from the
    container's sibling <Columns> block. Only representations whose element
    is actually present contribute rows; within a present representation, a
    column with no <Column> entry gets visible=None ("not listed"). Returns
    {} when there is no <Columns> block (every column then gets [])."""
    columns_block = container_el.find("Columns")
    if columns_block is None:
        return {}

    present_names = []
    # entries_by_rep[name][field_name] = (visible, sourceline)
    entries_by_rep: dict = {}
    field_names = set()
    for name in REPRESENTATION_NAMES:
        rep_el = columns_block.find(name)
        if rep_el is None:
            continue  # absent representation -> omitted for everyone
        present_names.append(name)
        per_field = {}
        for entry in rep_el.findall("Column"):
            fn = entry.get("fieldName", "") or ""
            per_field[fn] = (entry.get("visible") != "false", entry.sourceline)
            field_names.add(fn)
        entries_by_rep[name] = per_field

    index: dict = {}
    for fn in field_names:
        reps = []
        for name in present_names:
            per_field = entries_by_rep[name]
            if fn in per_field:
                visible, sourceline = per_field[fn]
                reps.append(RepresentationVisibility(name=name, visible=visible, sourceline=sourceline))
            else:
                reps.append(RepresentationVisibility(name=name, visible=None, sourceline=None))
        index[fn] = reps
    return index
```

4. In `_parse_columns`, build the index once and attach the per-column slice:

```python
def _parse_columns(container_el, parent_identity) -> list[ColumnNode]:
    columns_container = container_el.find("ColumnPresentations")
    if columns_container is None:
        return []

    representation_index = _build_representation_index(container_el)

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
                format=_child_element(col_el.find("ViewProperties/Format")),
                lookup=_child_element(col_el.find("Lookup")),
                view_properties=_child_element(col_el.find("ViewProperties")),
                edit_properties=_child_element(col_el.find("EditProperties")),
                representations=representation_index.get(field_name, []),
            )
        )
    return columns
```

> Note: a "not listed" column (present in `<ColumnPresentations>` but in no representation list) is absent from `field_names`, so `representation_index.get(field_name, [])` returns `[]` — which fails `test_column_not_listed_...` expecting a length-10 list of `None`s. Fix: after building `index`, also ensure any fieldName seen in `<ColumnPresentations>` gets a full "all-None (for present reps)" list. Simplest: pass the presentation field names in and backfill. Implement by having `_parse_columns` backfill:
>
> ```python
>     for col_el in columns_container.findall("ColumnPresentation"):
>         field_name = col_el.get("fieldName", "") or ""
>         reps = representation_index.get(field_name)
>         if reps is None:
>             # present in ColumnPresentations but in no representation list:
>             # every present representation lists it as "not listed".
>             reps = [
>                 RepresentationVisibility(name=n, visible=None, sourceline=None)
>                 for n in representation_index_present_names(representation_index)
>             ]
> ```
>
> To avoid a fragile helper, instead return **both** the index and the present-name list from `_build_representation_index` as `(index, present_names)`, and build the fallback list from `present_names`. Update the builder's `return` to `return index, present_names` and `_parse_columns` to unpack it. The tests above assume length-10 for a not-listed column in a full block (all 10 present), which this satisfies.

**Implementer:** adopt the `(index, present_names)` return shape — it's the clean version. Concretely: `_build_representation_index` returns `(index, present_names)`; in `_parse_columns`, `reps = index.get(field_name) or [RepresentationVisibility(n, None, None) for n in present_names]`.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/model/test_parser.py -v`
Expected: PASS (new + all pre-existing parser tests).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/model/parser.py tests/model/test_parser.py
git commit -m "feat(model): parse <Columns> block into ColumnNode.representations"
```

---

## Task 3: Properties panel shows representation rows

**Files:**
- Modify: `pgtp_editor/ui/properties_panel.py`
- Test: `tests/ui/test_properties_panel_rows.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/ui/test_properties_panel_rows.py`:

```python
from pgtp_editor.model.nodes import RepresentationVisibility
from pgtp_editor.ui.properties_panel import _rows_for_column


def _column_with_reps():
    return ColumnNode(
        identity="c",
        attrib={"fieldName": "id", "caption": "Id"},
        sourceline=5,
        representations=[
            RepresentationVisibility("List", True, 20),
            RepresentationVisibility("Edit", False, 30),
            RepresentationVisibility("Compare", None, None),
        ],
    )


def test_rows_for_column_starts_with_attribute_rows():
    rows = _rows_for_column(_column_with_reps())
    assert rows[0].property_label == "fieldName"
    assert rows[1].property_label == "caption"


def test_rows_for_column_has_divider_then_representation_rows():
    rows = _rows_for_column(_column_with_reps())
    labels = [r.property_label for r in rows]
    assert "— Representations —" in labels
    divider = labels.index("— Representations —")
    rep_rows = rows[divider + 1:]
    assert [(r.property_label, r.value) for r in rep_rows] == [
        ("List", "visible"),
        ("Edit", "hidden"),
        ("Compare", "— (not listed)"),
    ]


def test_rows_for_column_representation_navigation_targets():
    rows = _rows_for_column(_column_with_reps())
    by_label = {r.property_label: r for r in rows}
    assert by_label["List"].target_line == 20 and by_label["List"].attr_name is None
    assert by_label["Edit"].target_line == 30
    # "not listed" and the divider are non-navigating.
    assert by_label["Compare"].target_line is None
    assert by_label["— Representations —"].target_line is None


def test_rows_for_column_no_representations_has_no_divider():
    col = ColumnNode(identity="c", attrib={"fieldName": "id"}, sourceline=5)
    labels = [r.property_label for r in _rows_for_column(col)]
    assert "— Representations —" not in labels
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/ui/test_properties_panel_rows.py -v -k "column"`
Expected: FAIL — `ImportError: cannot import name '_rows_for_column'`.

- [ ] **Step 3: Implement**

In `pgtp_editor/ui/properties_panel.py`, add `_rows_for_column` (after `_rows_for_event`, before the QtWidgets import block):

```python
_REPRESENTATIONS_DIVIDER = "— Representations —"


def _rows_for_column(column_node) -> list[RowSpec]:
    """Column attribute rows, then (if the column carries representation
    visibilities) a divider and one row per representation showing
    visible / hidden / — (not listed). Representation rows navigate to that
    column's <Column> entry line (attr_name=None -> no attribute selection);
    the divider and not-listed rows are non-navigating."""
    rows = _rows_for_attrib_node(column_node)
    representations = getattr(column_node, "representations", [])
    if representations:
        rows.append(RowSpec(_REPRESENTATIONS_DIVIDER, "", target_line=None, attr_name=None))
        for rep in representations:
            if rep.visible is True:
                value = "visible"
            elif rep.visible is False:
                value = "hidden"
            else:
                value = "— (not listed)"
            rows.append(RowSpec(rep.name, value, target_line=rep.sourceline, attr_name=None))
    return rows
```

Point the `"column"` builder at it in `_ROW_BUILDERS`:

```python
    "column": (_rows_for_column, lambda n: f"Column: {n.field_name}"),
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/ui/test_properties_panel_rows.py -v`
Expected: PASS (new + pre-existing row-builder tests).

- [ ] **Step 5: Run the panel (pytest-qt) tests too**

Run: `python -m pytest tests/ui/test_properties_panel.py -v`
Expected: PASS — the panel renders the extra rows through the unchanged `_populate_table`; `_on_row_clicked` already no-ops on `target_line is None` and navigates without attribute-selection when `attr_name is None`.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/properties_panel.py tests/ui/test_properties_panel_rows.py
git commit -m "feat(ui): show column representation visibility in Properties"
```

---

## Task 4: Real-sample smoke + full suite

**Files:**
- Modify: `tests/model/test_parser_real_samples.py`

- [ ] **Step 1: Add the real-sample test (skips if absent)**

Append to `tests/model/test_parser_real_samples.py`:

```python
def test_real_sample_column_representations_populated():
    project = _load_dev_ferrara()   # existing helper; skips if sample absent
    page = next(p for p in project.pages if p.file_name == "development_equipment")
    columns = {c.field_name: c for c in page.columns}
    id_col = columns["id"]
    reps = {r.name: r for r in id_col.representations}
    # All 10 representations present for a real page.
    assert set(reps) == {
        "List", "View", "Edit", "Insert", "QuickFilter",
        "FilterBuilder", "Print", "Export", "Compare", "MultiEdit",
    }
    # 'id' is hidden in Edit but shown in List (per the real file).
    assert reps["Edit"].visible is False
    assert reps["List"].visible is True
```

> **If the assertions mismatch at execution time:** re-grep the real sample (`grep -n 'fieldName="id"' sample/dev_Ferrara.pgtp` and read the `<List>`/`<Edit>` entries) and correct the expected values to the real ones — do NOT weaken the test. If the existing helper is named differently than `_load_dev_ferrara`, use whatever the module already defines (it has a skip-if-absent loader).

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/model/test_parser_real_samples.py -v -k "representations"`
Expected: PASS (or SKIP if `sample/dev_Ferrara.pgtp` absent).

- [ ] **Step 3: Full suite**

Run: `python -m pytest -q`
Expected: all green (real-sample tests SKIP if the gitignored samples are absent; nothing FAILS). No Qt-free file gained a Qt import.

- [ ] **Step 4: Commit**

```bash
git add tests/model/test_parser_real_samples.py
git commit -m "test(model): real-sample smoke for column representations"
```

---

## Requirement → task traceability (self-review)
- `RepresentationVisibility` (name/visible/sourceline) + `ColumnNode.representations` → **Task 1** (spec §4.1, §4.2).
- Parse `<Columns>` block, fixed order, `visible="false"`→hidden, not-listed→None, no-block→[], Detail inner-page → **Task 2** (spec §4.3, §3).
- Properties divider + representation rows (visible/hidden/— (not listed)) + navigation to entry line → **Task 3** (spec §5).
- Real-sample smoke + full-suite verify → **Task 4** (spec §6).
- Out of scope (editing, other representations, column order, diff/write-back) → intentionally not built (spec §2).
