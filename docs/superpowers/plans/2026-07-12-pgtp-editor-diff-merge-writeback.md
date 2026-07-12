# PGTP Editor — Diff/Merge Write-Back Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "Apply Changes to Target" real: retain live `lxml.etree.Element` references on the parsed model, mutate a Target's real XML tree according to checked `Difference` records, write a `.bak` safety copy, and serialize the result back over the Target file — with round-trip fidelity for everything the merge doesn't touch.

**Architecture:** Four layers, built bottom-up. (1) `pgtp_editor/model/nodes.py` and `pgtp_editor/model/parser.py` gain retained-element fields and a reusable `_build_project_model(tree, source_description)` split out of `load_project`, verified against both real sample files with an empirically-pinned round-trip fidelity regression test. (2) A new `pgtp_editor/diff/apply.py` module applies a list of `Difference` records to a Target's retained `lxml` tree, reusing `resolve_path` for Page/Detail location and adding one small Column/Event lookup step of its own. (3) `pgtp_editor/ui/diff_merge_panel.py` gains `checked_differences()` to read Qt checkbox state back out as `Difference` objects. (4) `pgtp_editor/ui/main_window.py` wires a real `_apply_changes_to_target` handler: gather checked differences, refuse on any ambiguous item, apply all to a disposable deep-copied working tree, refuse all-or-nothing on any failure, write `.bak`, serialize, report success/failure, and reload Target via the existing `open_project_file`.

**Tech Stack:** Python 3.10+, PySide6/Qt (`Qt.CheckState`, `QMessageBox`), `lxml.etree` 6.1.1, pytest + pytest-qt, existing `pgtp_editor.diff`/`pgtp_editor.model` packages already in this codebase.

---

## Before you start

This plan assumes the following already exist in this codebase (do not re-implement, only import/extend as directed):

- `pgtp_editor.model.nodes`: `ProjectModel(pages: list[PageNode])`; `PageNode(identity, attrib, sourceline, details, columns, events)` with `.file_name`/`.table_name` properties; `DetailNode(identity, attrib, sourceline, details, columns, events)` with `.table_name` property; `ColumnNode(identity, attrib, sourceline)` with `.field_name` property; `EventNode(identity, tag_name, side, text, sourceline)`; `classify_event_side(tag_name)`.
- `pgtp_editor.model.parser`: `load_project(path) -> ProjectModel`, `PgtpParseError`. Internal helpers `_parse_page`, `_parse_details`, `_parse_detail`, `_parse_columns`, `_parse_events`, `_make_identity`.
- `pgtp_editor.diff.records.Difference(kind, path, node_kind, attribute, old_value, new_value, ambiguous=False)`.
- `pgtp_editor.diff.differ`: `diff_project(source, target) -> list[Difference]`, `compare_block(source_node, target_node, path, node_kind, ambiguous=False)`.
- `pgtp_editor.diff.resolve`: `resolve_path(project, path) -> PageNode | DetailNode | ResolutionError`; `ResolutionError(segment_index, message)`.
- `pgtp_editor.ui.diff_merge_panel.DiffMergePanel`: `show_differences(differences)`, `_flattened_leaves() -> list[QTreeWidgetItem]`, `DIFFERENCE_ROLE` constant, `select_next_difference()`/`select_previous_difference()`.
- `pgtp_editor.ui.main_window.MainWindow`: `open_project_file(path)`, `_compare_merge_two_files`, `_compare_page_with`, `_compare_detail_with`, `_build_diff_merge_menu`, `_current_project`/`_current_project_path` attributes, `self.center_stage.diff_merge_panel`.

Real sample fixtures used by the round-trip and integration tests: `sample/dev_Ferrara.pgtp` (2,810,140 bytes) and `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp` (4,124,768 bytes), both already present in this worktree.

Authoritative design reference for every decision below: `docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md`. This plan does not revisit any of that document's judgment calls — it only breaks them into bite-sized, test-first tasks.

This plan does **not** touch the differ engine's comparison algorithm, the `Difference` record shape, the change-list tree's construction/labeling in `DiffMergePanel.show_differences`, any ambiguity-resolution UI, undo beyond `.bak`, Source-side mutation (never happens), or automatic re-diffing after Apply (explicitly not done — see spec §7.4/§7.5).

---

### Task 1: Retain `lxml` elements on `nodes.py` dataclasses

**Files:**
- Modify: `pgtp_editor/model/nodes.py`
- Test: `tests/model/test_nodes.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/model/test_nodes.py
"""Tests for the retained-lxml-element fields added to the model dataclasses
for the Diff/Merge write-back feature. See
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md §3.2.
"""
from lxml import etree

from pgtp_editor.model.nodes import ColumnNode, DetailNode, EventNode, PageNode, ProjectModel


def test_page_node_element_defaults_to_none():
    page = PageNode(identity="p", attrib={})
    assert page.element is None


def test_page_node_element_can_be_set():
    el = etree.fromstring("<Page fileName='p'/>")
    page = PageNode(identity="p", attrib={}, element=el)
    assert page.element is el


def test_detail_node_has_element_and_inner_page_element_fields():
    detail_el = etree.fromstring("<Detail/>")
    inner_page_el = etree.fromstring("<Page tableName='t'/>")
    detail = DetailNode(
        identity="d", attrib={}, element=detail_el, inner_page_element=inner_page_el
    )
    assert detail.element is detail_el
    assert detail.inner_page_element is inner_page_el


def test_detail_node_element_fields_default_to_none():
    detail = DetailNode(identity="d", attrib={})
    assert detail.element is None
    assert detail.inner_page_element is None


def test_column_node_element_defaults_to_none_and_can_be_set():
    col = ColumnNode(identity="c", attrib={})
    assert col.element is None
    el = etree.fromstring("<ColumnPresentation fieldName='c'/>")
    col2 = ColumnNode(identity="c", attrib={}, element=el)
    assert col2.element is el


def test_event_node_element_defaults_to_none_and_can_be_set():
    event = EventNode(identity="e", tag_name="OnRowProcess", side="S", text="")
    assert event.element is None
    el = etree.fromstring("<OnRowProcess>echo 1;</OnRowProcess>")
    event2 = EventNode(identity="e", tag_name="OnRowProcess", side="S", text="", element=el)
    assert event2.element is el


def test_project_model_tree_defaults_to_none_and_can_be_set():
    project = ProjectModel(pages=[])
    assert project.tree is None
    tree = etree.ElementTree(etree.fromstring("<Project/>"))
    project2 = ProjectModel(pages=[], tree=tree)
    assert project2.tree is tree
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/test_nodes.py -v`
Expected: FAIL with `TypeError: PageNode.__init__() got an unexpected keyword argument 'element'` (or equivalent for the other classes) — the fields don't exist yet.

- [ ] **Step 3: Add the retained-element fields**

Replace the dataclass definitions in `pgtp_editor/model/nodes.py` (everything from `@dataclass\nclass ColumnNode:` to the end of the file):

```python
@dataclass
class ColumnNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None

    @property
    def field_name(self) -> str | None:
        return self.attrib.get("fieldName")


@dataclass
class EventNode:
    identity: str
    tag_name: str
    side: str
    text: str
    sourceline: int | None = None
    element: "etree._Element | None" = None


@dataclass
class DetailNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None
    inner_page_element: "etree._Element | None" = None
    details: list["DetailNode"] = field(default_factory=list)
    columns: list[ColumnNode] = field(default_factory=list)
    events: list[EventNode] = field(default_factory=list)

    @property
    def table_name(self) -> str | None:
        return self.attrib.get("tableName")


@dataclass
class PageNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None
    details: list[DetailNode] = field(default_factory=list)
    columns: list[ColumnNode] = field(default_factory=list)
    events: list[EventNode] = field(default_factory=list)

    @property
    def file_name(self) -> str | None:
        return self.attrib.get("fileName")

    @property
    def table_name(self) -> str | None:
        return self.attrib.get("tableName")


@dataclass
class ProjectModel:
    pages: list[PageNode] = field(default_factory=list)
    tree: "etree._ElementTree | None" = None
```

Also add the string-quoted-friendly import at the top of the file (right after the module docstring, before `from dataclasses import ...`), guarded so `nodes.py` still doesn't hard-depend on `lxml` at runtime for anything except type hints:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxml import etree
```

(The `from __future__ import annotations` line already exists at the top of the file — keep it; only add the `TYPE_CHECKING` import block right below it, before the existing `from dataclasses import dataclass, field` line stays where it is.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/test_nodes.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Run the full existing test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: PASS — every existing test still passes unchanged (new fields all default to `None`, so no existing construction call site breaks).

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/model/nodes.py tests/model/test_nodes.py
git commit -m "feat(model): add retained lxml element fields to node dataclasses"
```

---

### Task 2: Split `load_project` into a path wrapper plus reusable `_build_project_model`, and populate the new fields

**Files:**
- Modify: `pgtp_editor/model/parser.py`
- Test: `tests/model/test_parser.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/model/test_parser.py`:

```python
# tests/model/test_parser.py (append)
from lxml import etree

from pgtp_editor.model.parser import _build_project_model


def test_load_project_populates_tree_field(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    assert project.tree is not None
    assert project.tree.getroot().tag == "Project"


def test_page_element_is_the_real_lxml_element(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    page = project.pages[0]
    assert page.element is not None
    assert page.element.tag == "Page"
    assert page.element.get("fileName") == "development_equipment"


def test_column_element_is_the_real_lxml_element(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    column = project.pages[0].columns[0]
    assert column.element is not None
    assert column.element.tag == "ColumnPresentation"
    assert column.element.get("fieldName") == "tag"


def test_event_element_is_the_real_lxml_element(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    event = next(e for e in project.pages[0].events if e.tag_name == "OnPreparePage")
    assert event.element is not None
    assert event.element.tag == "OnPreparePage"


def test_detail_element_and_inner_page_element_are_the_two_real_elements(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    detail = project.pages[0].details[0]
    assert detail.element is not None
    assert detail.element.tag == "Detail"
    assert detail.inner_page_element is not None
    assert detail.inner_page_element.tag == "Page"
    assert detail.inner_page_element.get("tableName") == "pr.attachment"


def test_build_project_model_accepts_an_already_parsed_tree(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    tree = etree.parse(str(path))
    project = _build_project_model(tree, source_description=str(path))
    assert len(project.pages) == 2
    assert project.tree is tree
    assert project.pages[0].element is tree.getroot().find("Presentation/Pages/Page")


def test_build_project_model_wraps_structural_errors_with_source_description(tmp_path):
    path = tmp_path / "broken.pgtp"
    path.write_text(
        "<Project><Presentation><Pages><Page></Pages></Presentation></Project>",
        encoding="utf-8",
    )
    tree = etree.parse(str(path))
    from pgtp_editor.model.parser import PgtpParseError

    with pytest.raises(PgtpParseError) as excinfo:
        _build_project_model(tree, source_description="my-custom-description")
    assert "my-custom-description" in str(excinfo.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/model/test_parser.py -v`
Expected: FAIL — `project.tree` is `AttributeError`-free (field doesn't exist to read... actually `ProjectModel.tree` exists from Task 1 but is never populated, so it's `None`, failing the `is not None` assertions), and `_build_project_model` doesn't exist yet (`ImportError`).

- [ ] **Step 3: Refactor `load_project` and populate every retained-element field**

Replace the entire contents of `pgtp_editor/model/parser.py`:

```python
# pgtp_editor/model/parser.py
"""Parses a real .pgtp file (XML) into a ProjectModel using lxml.

This is the only module that touches lxml directly. UI code should only
ever read from the ProjectModel/PageNode/DetailNode/ColumnNode/EventNode
data objects in pgtp_editor.model.nodes.
"""
from __future__ import annotations

from lxml import etree

from pgtp_editor.model.nodes import (
    ColumnNode,
    DetailNode,
    EventNode,
    PageNode,
    ProjectModel,
    classify_event_side,
)


class PgtpParseError(Exception):
    """Raised when a .pgtp file cannot be parsed into a ProjectModel."""


def load_project(path) -> ProjectModel:
    """Parse the .pgtp file at `path` and return a ProjectModel.

    Raises PgtpParseError on malformed/unexpected XML so callers (e.g. the
    UI's File -> Open handler) can surface a clear error instead of letting
    an lxml exception bubble up uncaught or silently returning an empty
    project.

    Thin wrapper around `_build_project_model`, which does the actual
    element-walking and can also be called directly against an
    already-in-memory tree (e.g. a deep copy made during Apply — see
    pgtp_editor/diff/apply.py and MainWindow._apply_changes_to_target).
    """
    try:
        tree = etree.parse(str(path))
    except (etree.XMLSyntaxError, OSError) as exc:
        raise PgtpParseError(f"Could not parse '{path}': {exc}") from exc
    return _build_project_model(tree, source_description=str(path))


def _build_project_model(tree, source_description: str) -> ProjectModel:
    """Walk an already-parsed lxml tree and build a ProjectModel from it,
    retaining a reference to every real lxml element visited.

    Split out of `load_project` so the same walking logic can be re-run
    against an in-memory tree (e.g. a `copy.deepcopy` of a Target's tree
    made during Apply) without writing it to disk and reparsing it.
    """
    root = tree.getroot()

    try:
        pages_container = root.find("Presentation/Pages")
        page_elements = [] if pages_container is None else pages_container.findall("Page")
        pages = [_parse_page(page_el, parent_identity=None) for page_el in page_elements]
    except Exception as exc:  # defensive: any unexpected structural surprise
        raise PgtpParseError(f"Could not parse '{source_description}': {exc}") from exc

    return ProjectModel(pages=pages, tree=tree)


def _parse_page(page_el, parent_identity) -> PageNode:
    file_name = page_el.get("fileName", "") or ""
    identity = _make_identity(parent_identity, file_name)

    columns = _parse_columns(page_el, identity)
    events = _parse_events(page_el, identity)
    details = _parse_details(page_el, identity)

    return PageNode(
        identity=identity,
        attrib=dict(page_el.attrib),
        sourceline=page_el.sourceline,
        element=page_el,
        details=details,
        columns=columns,
        events=events,
    )


def _parse_details(page_el, parent_identity) -> list[DetailNode]:
    details_container = page_el.find("Details")
    if details_container is None:
        return []

    details = []
    for detail_el in details_container.findall("Detail"):
        details.append(_parse_detail(detail_el, parent_identity))
    return details


def _parse_detail(detail_el, parent_identity) -> DetailNode:
    inner_page_el = detail_el.find("Page")
    if inner_page_el is None:
        raise ValueError(f"Detail element (line {detail_el.sourceline}) has no nested Page")

    table_name = inner_page_el.get("tableName", "") or ""
    identity = _make_identity(parent_identity, table_name)

    columns = _parse_columns(inner_page_el, identity)
    events = _parse_events(inner_page_el, identity)
    nested_details = _parse_details(inner_page_el, identity)

    # Merge Detail's own attributes with the nested Page's attributes: the
    # nested Page carries the substantive data (tableName, caption, ability
    # modes, etc.) while Detail itself typically only carries a caption.
    merged_attrib = dict(detail_el.attrib)
    merged_attrib.update(inner_page_el.attrib)

    return DetailNode(
        identity=identity,
        attrib=merged_attrib,
        sourceline=detail_el.sourceline,
        element=detail_el,
        inner_page_element=inner_page_el,
        details=nested_details,
        columns=columns,
        events=events,
    )


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
            )
        )
    return columns


def _parse_events(container_el, parent_identity) -> list[EventNode]:
    events_container = container_el.find("EventHandlers")
    if events_container is None:
        return []

    events = []
    for event_el in events_container:
        tag_name = event_el.tag
        identity = _make_identity(parent_identity, tag_name)
        events.append(
            EventNode(
                identity=identity,
                tag_name=tag_name,
                side=classify_event_side(tag_name),
                text=event_el.text or "",
                sourceline=event_el.sourceline,
                element=event_el,
            )
        )
    return events


def _make_identity(parent_identity, key_part) -> str:
    if parent_identity:
        return f"{parent_identity}/{key_part}"
    return key_part
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/model/test_parser.py -v`
Expected: PASS (all tests, including the pre-existing ones — 19 total: 13 pre-existing + 6 new)

- [ ] **Step 5: Run full suite for regressions**

Run: `pytest tests/ -v`
Expected: PASS — this is a byte-for-byte-behavior-preserving refactor of `load_project` for every existing call site (`main_window.py`, `differ.py`, `resolve.py`), with new fields populated as a pure addition.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/model/parser.py tests/model/test_parser.py
git commit -m "refactor(model): split load_project into path wrapper + _build_project_model, retain lxml elements"
```

---

### Task 3: Empirical round-trip fidelity regression tests against both real sample files

**Files:**
- Create: `tests/model/test_round_trip_fidelity.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/model/test_round_trip_fidelity.py
"""Pins down the empirically-measured round-trip fidelity result from
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md
§4: with `etree.tostring(tree, xml_declaration=False, encoding="UTF-8",
pretty_print=False)`, both real sample files round-trip byte-for-byte
except that `&quot;` entities inside element TEXT content (never inside
attribute values) are normalized to a literal `"` by libxml2's serializer.

This test exists so a future lxml upgrade or an accidental change to the
adopted tostring() settings can't silently regress round-trip fidelity
without a test failing.
"""
import re
from pathlib import Path

import pytest
from lxml import etree

from pgtp_editor.diff.differ import diff_project
from pgtp_editor.model.parser import load_project

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"

SAMPLE_FILES = [
    SAMPLE_DIR / "dev_Ferrara.pgtp",
    SAMPLE_DIR / "Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp",
]

TOSTRING_KWARGS = dict(xml_declaration=False, encoding="UTF-8", pretty_print=False)


def _require_sample(path):
    if not path.exists():
        pytest.skip(f"sample file not present: {path}")


def _unescape_quot_in_text_content_only(xml_bytes: bytes) -> bytes:
    """Mirror the exact normalization used to characterize the residual
    difference in spec §4.3: replace `&quot;` with a literal `"` only when
    it occurs in element text (i.e. NOT inside a double-quoted attribute
    value). A `&quot;` is "in an attribute value" if it appears between an
    opening `="` and the next unescaped `"` within the same start-tag; this
    regex instead takes the simpler, equivalent-for-this-format approach of
    only touching `&quot;` occurrences that are NOT immediately preceded by
    `="` or immediately followed by `"` closing an attribute -- in practice,
    for this test, we replicate the exact known-good rule from the spec by
    unescaping every `&quot;` that lies OUTSIDE any `<...>` tag span, since
    tag spans are exactly where attribute values live.
    """
    result = bytearray()
    i = 0
    depth_inside_tag = False
    while i < len(xml_bytes):
        ch = xml_bytes[i:i + 1]
        if ch == b"<":
            depth_inside_tag = True
            result += ch
            i += 1
        elif ch == b">":
            depth_inside_tag = False
            result += ch
            i += 1
        elif xml_bytes[i:i + 6] == b"&quot;" and not depth_inside_tag:
            result += b'"'
            i += 6
        else:
            result += ch
            i += 1
    return bytes(result)


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_reserialize_matches_original_after_normalizing_known_residual(sample_path):
    _require_sample(sample_path)
    original_bytes = sample_path.read_bytes()

    tree = etree.parse(str(sample_path))
    reserialized = etree.tostring(tree, **TOSTRING_KWARGS)

    normalized_original = _unescape_quot_in_text_content_only(original_bytes)
    assert reserialized == normalized_original


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_no_xml_declaration_is_emitted(sample_path):
    _require_sample(sample_path)
    tree = etree.parse(str(sample_path))
    reserialized = etree.tostring(tree, **TOSTRING_KWARGS)
    assert not reserialized.startswith(b"<?xml")


@pytest.mark.parametrize("sample_path", SAMPLE_FILES)
def test_zero_difference_no_op_merge_end_to_end(sample_path):
    """A true end-to-end 'no-op merge changes nothing meaningful' test:
    load, reserialize via load_project's own tree (not a bespoke tostring
    call), write to a temp path, reload, and diff against the original --
    expecting an empty difference list. Layers on top of the differ
    engine's own 'diff a file against itself' test."""
    _require_sample(sample_path)
    project = load_project(sample_path)

    reserialized = etree.tostring(project.tree, **TOSTRING_KWARGS)

    reloaded_from_original = load_project(sample_path)
    import tempfile
    import os

    fd, tmp_name = tempfile.mkstemp(suffix=".pgtp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(reserialized)
        reloaded_from_reserialized = load_project(tmp_name)
    finally:
        os.remove(tmp_name)

    differences = diff_project(reloaded_from_original, reloaded_from_reserialized)
    assert differences == []
```

- [ ] **Step 2: Run tests to verify they fail or pass as expected**

Run: `pytest tests/model/test_round_trip_fidelity.py -v`
Expected: PASS immediately if the empirical measurement from the spec was correct (this test encodes an already-measured result, not new behavior to implement) — 6 passed (2 sample files x 3 tests). If any test fails, this indicates either the `lxml` version installed differs from the one the spec measured against (6.1.1), or a real regression; do not weaken the normalization helper to force a pass — investigate first (see the spec's §4.3 root cause for what a genuine failure would mean).

- [ ] **Step 3: Commit**

```bash
git add tests/model/test_round_trip_fidelity.py
git commit -m "test(model): pin round-trip fidelity result against both real sample files"
```

---

### Task 4: `apply.py` — `ApplyFailure`/`ApplyResult` dataclasses and attribute `"changed"` on a Page

**Files:**
- Create: `pgtp_editor/diff/apply.py`
- Test: `tests/diff/test_apply.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_apply.py
"""Tests for pgtp_editor.diff.apply.apply_differences -- see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md §5.
"""
from lxml import etree

from pgtp_editor.diff.apply import ApplyFailure, ApplyResult, apply_differences
from pgtp_editor.diff.records import Difference
from pgtp_editor.model.parser import _build_project_model


def build_project(xml_text):
    tree = etree.fromstring(xml_text.encode("utf-8")).getroottree()
    return _build_project_model(tree, source_description="<test fixture>")


SIMPLE_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Old Caption"/>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_result_dataclass_shape():
    result = ApplyResult(applied=[], failed=[])
    assert result.applied == []
    assert result.failed == []


def test_apply_failure_dataclass_shape():
    diff = Difference(kind="changed", path=["p"], node_kind="page", attribute="x", old_value=None, new_value=None)
    failure = ApplyFailure(difference=diff, message="boom")
    assert failure.difference is diff
    assert failure.message == "boom"


def test_apply_changed_page_attribute_sets_value_on_real_element():
    target = build_project(SIMPLE_TARGET)
    diff = Difference(
        kind="changed",
        path=["development_equipment"],
        node_kind="page",
        attribute="caption",
        old_value="Old Caption",
        new_value="New Caption",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    assert result.applied == [diff]
    page_el = target.tree.getroot().find("Presentation/Pages/Page")
    assert page_el.get("caption") == "New Caption"


def test_apply_changed_page_attribute_leaves_other_attributes_untouched():
    target = build_project(SIMPLE_TARGET)
    diff = Difference(
        kind="changed",
        path=["development_equipment"],
        node_kind="page",
        attribute="caption",
        old_value="Old Caption",
        new_value="New Caption",
    )

    apply_differences(target, [diff])

    page_el = target.tree.getroot().find("Presentation/Pages/Page")
    assert page_el.get("fileName") == "development_equipment"
    assert page_el.get("tableName") == "pr.equipment"


def test_apply_changed_attribute_with_none_new_value_deletes_attribute():
    xml = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p" ability="view,edit"/>
    </Pages>
  </Presentation>
</Project>
"""
    target = build_project(xml)
    diff = Difference(
        kind="changed", path=["p"], node_kind="page", attribute="ability",
        old_value="view,edit", new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    page_el = target.tree.getroot().find("Presentation/Pages/Page")
    assert "ability" not in page_el.attrib
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_apply.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.diff.apply'`

- [ ] **Step 3: Write the initial `apply.py` covering `ApplyResult`/`ApplyFailure` and Page attribute changes**

```python
# pgtp_editor/diff/apply.py
"""Applies checked Difference records to a Target ProjectModel's retained
real lxml tree. See
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md
§5 for the full per-kind/per-node_kind behavior this module implements.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pgtp_editor.diff.records import Difference
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.nodes import ProjectModel


@dataclass
class ApplyFailure:
    difference: Difference
    message: str


@dataclass
class ApplyResult:
    applied: list[Difference]
    failed: list[ApplyFailure]


def apply_differences(target: ProjectModel, differences: list[Difference]) -> ApplyResult:
    """Mutate target's retained lxml tree in place for each Difference in
    `differences` (already filtered to just the checked/Apply-selected
    ones by the caller -- see DiffMergePanel.checked_differences).

    This function applies whatever list it is handed -- it does not filter
    out ambiguous=True differences itself (that gate is main_window.py's
    responsibility) and it does not roll back partial mutations on failure
    (the caller is responsible for only serializing target.tree if
    ApplyResult.failed is empty, by operating on a disposable deep copy --
    see the design spec §7.3).
    """
    applied: list[Difference] = []
    failed: list[ApplyFailure] = []

    for diff in differences:
        try:
            _apply_one(target, diff)
        except _ApplyError as exc:
            failed.append(ApplyFailure(difference=diff, message=str(exc)))
        else:
            applied.append(diff)

    return ApplyResult(applied=applied, failed=failed)


class _ApplyError(Exception):
    """Internal-only: raised by _apply_one, caught by apply_differences."""


def _apply_one(target: ProjectModel, diff: Difference) -> None:
    if diff.kind == "changed" and diff.attribute is not None:
        _apply_changed_attribute(target, diff)
    else:
        raise _ApplyError(f"unsupported difference (kind={diff.kind!r}, node_kind={diff.node_kind!r})")


def _apply_changed_attribute(target: ProjectModel, diff: Difference) -> None:
    if diff.node_kind not in ("page", "detail"):
        raise _ApplyError(f"attribute changes are only supported for page/detail in this task (got {diff.node_kind!r})")

    resolved = resolve_path(target, diff.path)
    if isinstance(resolved, ResolutionError):
        raise _ApplyError(resolved.message)

    element = resolved.element
    if diff.new_value is None:
        element.attrib.pop(diff.attribute, None)
    else:
        element.set(diff.attribute, diff.new_value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_apply.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/apply.py tests/diff/test_apply.py
git commit -m "feat(diff): add apply_differences with Page attribute 'changed' support"
```

---

### Task 5: `apply.py` — attribute `"changed"` on a Detail (outer element vs. nested Page element)

**Files:**
- Modify: `pgtp_editor/diff/apply.py`
- Test: `tests/diff/test_apply.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_apply.py (append)

DETAIL_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <Details>
          <Detail caption="Equipment\\Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item" ability="view"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_changed_detail_attribute_on_nested_page_element():
    target = build_project(DETAIL_TARGET)
    diff = Difference(
        kind="changed",
        path=["development_equipment", "pr.attachment/Sub-item"],
        node_kind="detail",
        attribute="ability",
        old_value="view",
        new_value="insert,edit",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail = target.pages[0].details[0]
    assert detail.inner_page_element.get("ability") == "insert,edit"
    # The outer <Detail> element itself carries no "ability" attribute in
    # this fixture and must remain untouched.
    assert "ability" not in detail.element.attrib


def test_apply_changed_detail_attribute_on_outer_detail_element_when_key_lives_there():
    xml = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <Details>
          <Detail caption="Old Detail Caption">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""
    target = build_project(xml)
    diff = Difference(
        kind="changed",
        path=["p", "pr.attachment/Sub-item"],
        node_kind="detail",
        attribute="caption",
        old_value="Old Detail Caption",
        new_value="New Detail Caption",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail = target.pages[0].details[0]
    # "caption" exists on BOTH the outer Detail element (the raw attrib
    # used to build the Detail element="Old Detail Caption") and the
    # nested Page element (attrib.get("caption") == "Sub-item"). Per the
    # merge order in _parse_detail (nested Page's own attrib wins in the
    # *merged* dict), but this specific fixture's "caption" key at the
    # *raw element* level actually differs: the outer Detail's raw
    # attribute is "Old Detail Caption", overwritten in merged_attrib by
    # the nested Page's "Sub-item". Since the merged/displayed value here
    # is "Sub-item", not "Old Detail Caption", this test instead exercises
    # the case where the key exists on the OUTER element only (nested Page
    # has no "caption" set at all) -- see the corrected fixture below.
    assert detail.inner_page_element.get("caption") == "Sub-item"
```

The second test above documents a subtlety worth catching *before* writing more code: per `_parse_detail`'s actual merge order (`merged_attrib = dict(detail_el.attrib); merged_attrib.update(inner_page_el.attrib)`), a `caption` key present on **both** raw elements always resolves to the nested Page's value in the merged view — so a `Difference.attribute="caption"` can never have `old_value` equal to the outer Detail's own raw value when the nested Page also defines `caption`. Rewrite the second test to actually exercise "key lives only on the outer Detail element":

```python
# tests/diff/test_apply.py -- replace the previous
# test_apply_changed_detail_attribute_on_outer_detail_element_when_key_lives_there
# with this corrected version:

def test_apply_changed_detail_attribute_on_outer_detail_element_when_key_lives_there():
    xml = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <Details>
          <Detail caption="Sub-item" outerOnlyFlag="old-value">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""
    target = build_project(xml)
    diff = Difference(
        kind="changed",
        path=["p", "pr.attachment/Sub-item"],
        node_kind="detail",
        attribute="outerOnlyFlag",
        old_value="old-value",
        new_value="new-value",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail = target.pages[0].details[0]
    assert detail.element.get("outerOnlyFlag") == "new-value"
    assert "outerOnlyFlag" not in detail.inner_page_element.attrib


def test_apply_changed_detail_attribute_new_key_defaults_to_inner_page_element():
    xml = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <Details>
          <Detail caption="Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""
    target = build_project(xml)
    # brandNewKey exists on neither real element yet (Source added it) --
    # per spec §5.1, defaults to inner_page_element (the substantive-data element).
    diff = Difference(
        kind="changed",
        path=["p", "pr.attachment/Sub-item"],
        node_kind="detail",
        attribute="brandNewKey",
        old_value=None,
        new_value="brand-new-value",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail = target.pages[0].details[0]
    assert detail.inner_page_element.get("brandNewKey") == "brand-new-value"
    assert "brandNewKey" not in detail.element.attrib
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_apply.py -v`
Expected: FAIL — `_apply_changed_attribute`'s current implementation (Task 4) always calls `resolved.element` unconditionally, which for a `DetailNode` result sets/deletes on the **outer** `<Detail>` element only, so `test_apply_changed_detail_attribute_on_nested_page_element` and `test_apply_changed_detail_attribute_new_key_defaults_to_inner_page_element` fail (they expect the nested `<Page>` element to be mutated).

- [ ] **Step 3: Update `_apply_changed_attribute` to pick the correct real element for a Detail**

Replace `_apply_changed_attribute` in `pgtp_editor/diff/apply.py`:

```python
def _apply_changed_attribute(target: ProjectModel, diff: Difference) -> None:
    if diff.node_kind not in ("page", "detail"):
        raise _ApplyError(f"attribute changes are only supported for page/detail in this task (got {diff.node_kind!r})")

    resolved = resolve_path(target, diff.path)
    if isinstance(resolved, ResolutionError):
        raise _ApplyError(resolved.message)

    element = _target_element_for_attribute(resolved, diff.attribute)
    if diff.new_value is None:
        element.attrib.pop(diff.attribute, None)
    else:
        element.set(diff.attribute, diff.new_value)


def _target_element_for_attribute(resolved, attribute: str):
    """Return the real lxml element a given attribute key should be
    mutated on. A PageNode/ColumnNode/EventNode has exactly one real
    element. A DetailNode has two (the outer <Detail> and the nested
    <Page>) -- per spec §5.1, prefer whichever real element already
    carries that attribute key, checking inner_page_element first (since
    _parse_detail's merge order lets the nested Page's own attributes win
    in the merged view), and defaulting to inner_page_element (the
    substantive-data element) if the key exists on neither yet.
    """
    if getattr(resolved, "inner_page_element", None) is None:
        return resolved.element

    if attribute in resolved.inner_page_element.attrib:
        return resolved.inner_page_element
    if attribute in resolved.element.attrib:
        return resolved.element
    return resolved.inner_page_element
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_apply.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/apply.py tests/diff/test_apply.py
git commit -m "feat(diff): pick correct real element (outer Detail vs nested Page) for attribute changes"
```

---

### Task 6: `apply.py` — attribute `"changed"` on a Column, and event-text `"changed"`

**Files:**
- Modify: `pgtp_editor/diff/apply.py`
- Test: `tests/diff/test_apply.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_apply.py (append)

COLUMN_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <ColumnPresentations>
          <ColumnPresentation fieldName="tag" caption="Old Tag Caption"/>
        </ColumnPresentations>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_changed_column_attribute():
    target = build_project(COLUMN_TARGET)
    diff = Difference(
        kind="changed",
        path=["p", "tag"],
        node_kind="column",
        attribute="caption",
        old_value="Old Tag Caption",
        new_value="New Tag Caption",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    column_el = target.tree.getroot().find("Presentation/Pages/Page/ColumnPresentations/ColumnPresentation")
    assert column_el.get("caption") == "New Tag Caption"


def test_apply_changed_column_attribute_fails_when_field_name_not_found():
    target = build_project(COLUMN_TARGET)
    diff = Difference(
        kind="changed",
        path=["p", "does_not_exist"],
        node_kind="column",
        attribute="caption",
        old_value="Old",
        new_value="New",
    )

    result = apply_differences(target, [diff])

    assert result.applied == []
    assert len(result.failed) == 1
    assert result.failed[0].difference is diff


EVENT_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="p" tableName="pr.p">
        <EventHandlers>
          <OnRowProcess>echo 'old';</OnRowProcess>
        </EventHandlers>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_changed_event_text_replaces_element_text():
    target = build_project(EVENT_TARGET)
    diff = Difference(
        kind="changed",
        path=["p", "OnRowProcess"],
        node_kind="event",
        attribute=None,
        old_value="echo 'old';",
        new_value="echo 'new';",
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    event_el = target.tree.getroot().find("Presentation/Pages/Page/EventHandlers/OnRowProcess")
    assert event_el.text == "echo 'new';"


def test_apply_changed_event_text_fails_when_tag_not_found():
    target = build_project(EVENT_TARGET)
    diff = Difference(
        kind="changed",
        path=["p", "OnDoesNotExist"],
        node_kind="event",
        attribute=None,
        old_value="echo 'old';",
        new_value="echo 'new';",
    )

    result = apply_differences(target, [diff])

    assert result.applied == []
    assert len(result.failed) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_apply.py -v`
Expected: FAIL — `_apply_one` currently only handles `attribute is not None` for `node_kind in ("page", "detail")`; a Column attribute change raises `_ApplyError("attribute changes are only supported for page/detail...")` (wrong message, but also not applying), and event-text changes (`attribute is None`) hit the `else: raise _ApplyError("unsupported difference...")` branch entirely.

- [ ] **Step 3: Add Column attribute support and Event text support**

Replace `_apply_one` and `_apply_changed_attribute` in `pgtp_editor/diff/apply.py`, and add two new functions:

```python
def _apply_one(target: ProjectModel, diff: Difference) -> None:
    if diff.kind == "changed" and diff.node_kind == "event" and diff.attribute is None:
        _apply_changed_event_text(target, diff)
    elif diff.kind == "changed" and diff.attribute is not None:
        _apply_changed_attribute(target, diff)
    else:
        raise _ApplyError(f"unsupported difference (kind={diff.kind!r}, node_kind={diff.node_kind!r})")


def _apply_changed_attribute(target: ProjectModel, diff: Difference) -> None:
    if diff.node_kind in ("page", "detail"):
        resolved = resolve_path(target, diff.path)
        if isinstance(resolved, ResolutionError):
            raise _ApplyError(resolved.message)
        element = _target_element_for_attribute(resolved, diff.attribute)
    elif diff.node_kind == "column":
        element = _find_column_element(target, diff.path)
    else:
        raise _ApplyError(f"unsupported node_kind for attribute change: {diff.node_kind!r}")

    if diff.new_value is None:
        element.attrib.pop(diff.attribute, None)
    else:
        element.set(diff.attribute, diff.new_value)


def _find_column_element(target: ProjectModel, path: list[str]):
    parent_result = resolve_path(target, path[:-1])
    if isinstance(parent_result, ResolutionError):
        raise _ApplyError(parent_result.message)

    field_name = path[-1]
    match = next((c for c in parent_result.columns if c.field_name == field_name), None)
    if match is None:
        raise _ApplyError(f"no Column with fieldName '{field_name}' under {'/'.join(path[:-1])}")
    return match.element


def _find_event_element(target: ProjectModel, path: list[str]):
    parent_result = resolve_path(target, path[:-1])
    if isinstance(parent_result, ResolutionError):
        raise _ApplyError(parent_result.message)

    tag_name = path[-1]
    match = next((e for e in parent_result.events if e.tag_name == tag_name), None)
    if match is None:
        raise _ApplyError(f"no Event with tag_name '{tag_name}' under {'/'.join(path[:-1])}")
    return match.element


def _apply_changed_event_text(target: ProjectModel, diff: Difference) -> None:
    element = _find_event_element(target, diff.path)
    element.text = diff.new_value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_apply.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/apply.py tests/diff/test_apply.py
git commit -m "feat(diff): add Column attribute and Event text 'changed' support to apply_differences"
```

---

### Task 7: `apply.py` — `"removed"` for Page/Detail/Column/Event

**Files:**
- Modify: `pgtp_editor/diff/apply.py`
- Test: `tests/diff/test_apply.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_apply.py (append)

REMOVE_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="keep_me" tableName="pr.keep"/>
      <Page fileName="remove_me" tableName="pr.remove">
        <ColumnPresentations>
          <ColumnPresentation fieldName="doomed_column" caption="Doomed"/>
        </ColumnPresentations>
        <EventHandlers>
          <OnRowProcess>echo 'doomed';</OnRowProcess>
        </EventHandlers>
        <Details>
          <Detail caption="Doomed\\Sub">
            <Page fileName="" tableName="pr.doomed_sub" caption="Sub"/>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_removed_page_deletes_element_from_parent():
    target = build_project(REMOVE_TARGET)
    doomed_page = next(p for p in target.pages if p.file_name == "remove_me")
    diff = Difference(
        kind="removed", path=["remove_me"], node_kind="page",
        attribute=None, old_value=doomed_page, new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    remaining = target.tree.getroot().findall("Presentation/Pages/Page")
    assert [p.get("fileName") for p in remaining] == ["keep_me"]


def test_apply_removed_column_deletes_element():
    target = build_project(REMOVE_TARGET)
    page = next(p for p in target.pages if p.file_name == "remove_me")
    column = page.columns[0]
    diff = Difference(
        kind="removed", path=["remove_me", "doomed_column"], node_kind="column",
        attribute=None, old_value=column, new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    columns_container = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='remove_me']/ColumnPresentations"
    )
    assert columns_container.findall("ColumnPresentation") == []


def test_apply_removed_event_deletes_element():
    target = build_project(REMOVE_TARGET)
    page = next(p for p in target.pages if p.file_name == "remove_me")
    event = page.events[0]
    diff = Difference(
        kind="removed", path=["remove_me", "OnRowProcess"], node_kind="event",
        attribute=None, old_value=event, new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    events_container = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='remove_me']/EventHandlers"
    )
    assert list(events_container) == []


def test_apply_removed_detail_deletes_whole_outer_element_including_nested_page():
    target = build_project(REMOVE_TARGET)
    page = next(p for p in target.pages if p.file_name == "remove_me")
    detail = page.details[0]
    diff = Difference(
        kind="removed", path=["remove_me", "pr.doomed_sub/Sub"], node_kind="detail",
        attribute=None, old_value=detail, new_value=None,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    details_container = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='remove_me']/Details"
    )
    assert details_container.findall("Detail") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_apply.py -v`
Expected: FAIL — `_apply_one` has no branch for `diff.kind == "removed"`, so every new test hits the final `else: raise _ApplyError(...)` and `result.failed` is non-empty where the tests expect `[]`.

- [ ] **Step 3: Add `"removed"` handling**

Update `_apply_one` in `pgtp_editor/diff/apply.py` and add `_apply_removed`:

```python
def _apply_one(target: ProjectModel, diff: Difference) -> None:
    if diff.kind == "removed":
        _apply_removed(diff)
    elif diff.kind == "changed" and diff.node_kind == "event" and diff.attribute is None:
        _apply_changed_event_text(target, diff)
    elif diff.kind == "changed" and diff.attribute is not None:
        _apply_changed_attribute(target, diff)
    else:
        raise _ApplyError(f"unsupported difference (kind={diff.kind!r}, node_kind={diff.node_kind!r})")


def _apply_removed(diff: Difference) -> None:
    """A whole-subtree removed record: diff.old_value is itself the
    Target-side node carrying its own retained .element -- no resolve_path
    lookup is needed at all, since the node object *is* the thing to
    remove. For a Detail, removing the outer <Detail> element also removes
    everything nested under it (including the inner <Page>) in one call.
    """
    node = diff.old_value
    element = node.element
    parent = element.getparent()
    if parent is None:
        raise _ApplyError("cannot remove an element with no parent (already detached)")
    parent.remove(element)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_apply.py -v`
Expected: PASS (16 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/apply.py tests/diff/test_apply.py
git commit -m "feat(diff): add 'removed' support for Page/Detail/Column/Event to apply_differences"
```

---

### Task 8: `apply.py` — `"added"` for Page/Detail/Column/Event via `copy.deepcopy` from Source

**Files:**
- Modify: `pgtp_editor/diff/apply.py`
- Test: `tests/diff/test_apply.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_apply.py (append)
import copy

ADD_SOURCE = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="existing_page" tableName="pr.existing">
        <ColumnPresentations>
          <ColumnPresentation fieldName="new_field" caption="Brand New Field"/>
        </ColumnPresentations>
        <EventHandlers>
          <OnRowProcess>echo 'new handler';</OnRowProcess>
        </EventHandlers>
        <Details>
          <Detail caption="Existing\\NewSub">
            <Page fileName="" tableName="pr.new_sub" caption="NewSub">
              <Details>
                <Detail caption="Existing\\NewSub\\Deeper">
                  <Page fileName="" tableName="pr.deeper" caption="Deeper"/>
                </Detail>
              </Details>
            </Page>
          </Detail>
        </Details>
      </Page>
      <Page fileName="brand_new_page" tableName="pr.brand_new" caption="Brand New Page"/>
    </Pages>
  </Presentation>
</Project>
"""

ADD_TARGET = """\
<Project>
  <Presentation>
    <Pages>
      <Page fileName="existing_page" tableName="pr.existing"/>
    </Pages>
  </Presentation>
</Project>
"""


def test_apply_added_page_appends_deepcopy_to_pages_container():
    source = build_project(ADD_SOURCE)
    target = build_project(ADD_TARGET)
    new_page = next(p for p in source.pages if p.file_name == "brand_new_page")
    diff = Difference(
        kind="added", path=["brand_new_page"], node_kind="page",
        attribute=None, old_value=None, new_value=new_page,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    pages = target.tree.getroot().findall("Presentation/Pages/Page")
    assert [p.get("fileName") for p in pages] == ["existing_page", "brand_new_page"]
    assert pages[1].get("caption") == "Brand New Page"
    # Confirm it's a deep copy, not a reference into Source's own tree.
    assert pages[1] is not new_page.element


def test_apply_added_column_appends_to_column_presentations():
    source = build_project(ADD_SOURCE)
    target = build_project(ADD_TARGET)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_column = source_page.columns[0]
    diff = Difference(
        kind="added", path=["existing_page", "new_field"], node_kind="column",
        attribute=None, old_value=None, new_value=new_column,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    columns = target.tree.getroot().findall(
        "Presentation/Pages/Page[@fileName='existing_page']/ColumnPresentations/ColumnPresentation"
    )
    assert len(columns) == 1
    assert columns[0].get("fieldName") == "new_field"
    assert columns[0].get("caption") == "Brand New Field"


def test_apply_added_column_creates_column_presentations_container_if_absent():
    # ADD_TARGET's existing_page has no ColumnPresentations element at all.
    target = build_project(ADD_TARGET)
    page_el = target.tree.getroot().find("Presentation/Pages/Page[@fileName='existing_page']")
    assert page_el.find("ColumnPresentations") is None

    source = build_project(ADD_SOURCE)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_column = source_page.columns[0]
    diff = Difference(
        kind="added", path=["existing_page", "new_field"], node_kind="column",
        attribute=None, old_value=None, new_value=new_column,
    )

    apply_differences(target, [diff])

    assert page_el.find("ColumnPresentations") is not None


def test_apply_added_event_appends_to_event_handlers_creating_container_if_absent():
    target = build_project(ADD_TARGET)
    source = build_project(ADD_SOURCE)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_event = source_page.events[0]
    diff = Difference(
        kind="added", path=["existing_page", "OnRowProcess"], node_kind="event",
        attribute=None, old_value=None, new_value=new_event,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    event_el = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='existing_page']/EventHandlers/OnRowProcess"
    )
    assert event_el is not None
    assert event_el.text == "echo 'new handler';"


def test_apply_added_detail_with_nested_details_survives_intact():
    target = build_project(ADD_TARGET)
    source = build_project(ADD_SOURCE)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_detail = source_page.details[0]
    diff = Difference(
        kind="added", path=["existing_page", "pr.new_sub/NewSub"], node_kind="detail",
        attribute=None, old_value=None, new_value=new_detail,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    detail_el = target.tree.getroot().find(
        "Presentation/Pages/Page[@fileName='existing_page']/Details/Detail"
    )
    assert detail_el is not None
    inner_page = detail_el.find("Page")
    assert inner_page.get("tableName") == "pr.new_sub"
    # The whole nested subtree (a second level of Details/Detail/Page) must
    # have survived the deepcopy+insert intact.
    deeper_inner_page = inner_page.find("Details/Detail/Page")
    assert deeper_inner_page is not None
    assert deeper_inner_page.get("tableName") == "pr.deeper"


def test_apply_added_detail_creates_details_container_if_absent():
    target = build_project(ADD_TARGET)
    page_el = target.tree.getroot().find("Presentation/Pages/Page[@fileName='existing_page']")
    assert page_el.find("Details") is None

    source = build_project(ADD_SOURCE)
    source_page = next(p for p in source.pages if p.file_name == "existing_page")
    new_detail = source_page.details[0]
    diff = Difference(
        kind="added", path=["existing_page", "pr.new_sub/NewSub"], node_kind="detail",
        attribute=None, old_value=None, new_value=new_detail,
    )

    apply_differences(target, [diff])

    assert page_el.find("Details") is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_apply.py -v`
Expected: FAIL — `"added"` has no branch in `_apply_one` yet, so every new test hits the `else: raise _ApplyError(...)` path.

- [ ] **Step 3: Add `"added"` handling**

Update `_apply_one` and add the new helpers to `pgtp_editor/diff/apply.py`. Add `import copy` and `from lxml import etree` to the top of the file:

```python
from __future__ import annotations

import copy

from dataclasses import dataclass
from typing import Any

from lxml import etree

from pgtp_editor.diff.records import Difference
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.nodes import ProjectModel
```

```python
def _apply_one(target: ProjectModel, diff: Difference) -> None:
    if diff.kind == "added":
        _apply_added(target, diff)
    elif diff.kind == "removed":
        _apply_removed(diff)
    elif diff.kind == "changed" and diff.node_kind == "event" and diff.attribute is None:
        _apply_changed_event_text(target, diff)
    elif diff.kind == "changed" and diff.attribute is not None:
        _apply_changed_attribute(target, diff)
    else:
        raise _ApplyError(f"unsupported difference (kind={diff.kind!r}, node_kind={diff.node_kind!r})")


def _apply_added(target: ProjectModel, diff: Difference) -> None:
    if diff.node_kind == "page":
        _apply_added_page(target, diff)
    elif diff.node_kind == "detail":
        _apply_added_detail(target, diff)
    elif diff.node_kind == "column":
        _apply_added_column(target, diff)
    elif diff.node_kind == "event":
        _apply_added_event(target, diff)
    else:
        raise _ApplyError(f"unsupported node_kind for added: {diff.node_kind!r}")


def _apply_added_page(target: ProjectModel, diff: Difference) -> None:
    pages_container = target.tree.getroot().find("Presentation/Pages")
    if pages_container is None:
        raise _ApplyError("Target has no Presentation/Pages container to add a Page under")
    new_element = copy.deepcopy(diff.new_value.element)
    pages_container.append(new_element)


def _resolve_parent_for_add(target: ProjectModel, path: list[str]):
    parent_path = path[:-1]
    if not parent_path:
        raise _ApplyError("cannot add a top-level node without a parent path segment")
    parent_result = resolve_path(target, parent_path)
    if isinstance(parent_result, ResolutionError):
        raise _ApplyError(parent_result.message)
    return parent_result


def _container_element_for_parent(parent_node, container_tag: str):
    """The element a Detail/Column/Event child should be appended under is
    scoped to the parent's own substantive-data element: for a PageNode
    that's `.element` itself; for a DetailNode it's `.inner_page_element`
    (the nested <Page>, which is where _parse_columns/_parse_events/
    _parse_details already read children from -- see parser.py)."""
    host_element = getattr(parent_node, "inner_page_element", None) or parent_node.element
    container = host_element.find(container_tag)
    if container is None:
        container = etree.SubElement(host_element, container_tag)
    return container


def _apply_added_detail(target: ProjectModel, diff: Difference) -> None:
    parent_node = _resolve_parent_for_add(target, diff.path)
    details_container = _container_element_for_parent(parent_node, "Details")
    new_element = copy.deepcopy(diff.new_value.element)
    details_container.append(new_element)


def _apply_added_column(target: ProjectModel, diff: Difference) -> None:
    parent_node = _resolve_parent_for_add(target, diff.path)
    columns_container = _container_element_for_parent(parent_node, "ColumnPresentations")
    new_element = copy.deepcopy(diff.new_value.element)
    columns_container.append(new_element)


def _apply_added_event(target: ProjectModel, diff: Difference) -> None:
    parent_node = _resolve_parent_for_add(target, diff.path)
    events_container = _container_element_for_parent(parent_node, "EventHandlers")
    new_element = copy.deepcopy(diff.new_value.element)
    events_container.append(new_element)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_apply.py -v`
Expected: PASS (22 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/apply.py tests/diff/test_apply.py
git commit -m "feat(diff): add 'added' support for Page/Detail/Column/Event via deepcopy from Source"
```

---

### Task 9: `apply.py` — ambiguity is not filtered internally, and mid-list failure leaves earlier successes applied

**Files:**
- Modify: none (regression tests only, per spec §9's explicit call-out)
- Test: `tests/diff/test_apply.py`

- [ ] **Step 1: Write the tests**

```python
# tests/diff/test_apply.py (append)

def test_apply_differences_does_not_filter_ambiguous_differences_itself():
    """apply.py has no special-cased 'ignore ambiguous' logic of its own --
    the ambiguity gate is entirely main_window.py's responsibility (spec
    §7.2). This locks in that apply_differences applies whatever list it's
    handed, ambiguous or not."""
    target = build_project(SIMPLE_TARGET)
    diff = Difference(
        kind="changed",
        path=["development_equipment"],
        node_kind="page",
        attribute="caption",
        old_value="Old Caption",
        new_value="New Caption",
        ambiguous=True,
    )

    result = apply_differences(target, [diff])

    assert result.failed == []
    assert result.applied == [diff]
    page_el = target.tree.getroot().find("Presentation/Pages/Page")
    assert page_el.get("caption") == "New Caption"


def test_apply_differences_mid_list_failure_still_applies_earlier_successes_to_the_tree():
    """A failing resolve_path lookup mid-list (simulating Target having
    changed since compare-time) must not prevent earlier, successful
    differences in the same call from being reflected in the tree --
    it is the caller's (main_window.py's) job per spec §7.3 to discard the
    whole working copy on any failure, not apply_differences's job to roll
    anything back itself."""
    target = build_project(SIMPLE_TARGET)
    good_diff = Difference(
        kind="changed", path=["development_equipment"], node_kind="page",
        attribute="caption", old_value="Old Caption", new_value="New Caption",
    )
    bad_diff = Difference(
        kind="changed", path=["page_that_does_not_exist"], node_kind="page",
        attribute="caption", old_value="X", new_value="Y",
    )

    result = apply_differences(target, [good_diff, bad_diff])

    assert result.applied == [good_diff]
    assert len(result.failed) == 1
    assert result.failed[0].difference is bad_diff
    page_el = target.tree.getroot().find("Presentation/Pages/Page")
    assert page_el.get("caption") == "New Caption"
```

- [ ] **Step 2: Run tests to verify they pass immediately**

Run: `pytest tests/diff/test_apply.py -v`
Expected: PASS immediately (24 passed) — no new implementation needed; `apply_differences`'s existing per-item try/except loop (Task 4) already has exactly this behavior. This task exists to lock it in with an explicit regression test, per the design spec §9's own call-out that this is "a design choice worth a regression test."

- [ ] **Step 3: Commit**

```bash
git add tests/diff/test_apply.py
git commit -m "test(diff): lock in no-ambiguity-filtering and partial-success-preserved-in-tree behavior"
```

---

### Task 10: `DiffMergePanel.checked_differences()`

**Files:**
- Modify: `pgtp_editor/ui/diff_merge_panel.py`
- Test: `tests/ui/test_diff_merge_panel.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_diff_merge_panel.py`:

```python
# tests/ui/test_diff_merge_panel.py (append)

def test_checked_differences_returns_only_checked_leaves_in_tree_order(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption"),
        make_diff(["page_a", "ability"], node_kind="page", kind="changed", attribute="ability"),
        make_diff(["page_b", "caption"], node_kind="page", kind="changed", attribute="caption"),
    ]
    panel.show_differences(diffs)

    leaves = panel._flattened_leaves()
    leaves[0].setCheckState(0, Qt.CheckState.Checked)
    leaves[2].setCheckState(0, Qt.CheckState.Checked)
    # leaves[1] stays Unchecked (default).

    checked = panel.checked_differences()

    assert checked == [diffs[0], diffs[2]]


def test_checked_differences_returns_empty_list_when_nothing_checked(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]
    panel.show_differences(diffs)

    assert panel.checked_differences() == []


def test_checked_differences_never_includes_group_prefix_nodes(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(
            ["development_equipment", "pr.attachment/Sub-item", "caption"],
            node_kind="detail", kind="changed", attribute="caption",
        ),
    ]
    panel.show_differences(diffs)

    leaves = panel._flattened_leaves()
    leaves[0].setCheckState(0, Qt.CheckState.Checked)

    checked = panel.checked_differences()

    assert checked == [diffs[0]]
    assert len(checked) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: FAIL with `AttributeError: 'DiffMergePanel' object has no attribute 'checked_differences'`

- [ ] **Step 3: Add `checked_differences`**

Add this method to `pgtp_editor/ui/diff_merge_panel.py`, placed right after `_flattened_leaves` (before `_current_leaf_position`):

```python
    def checked_differences(self) -> list:
        """Enumerate the Difference object for every leaf whose checkbox is
        checked, in the same tree order _flattened_leaves() already walks.
        Group/prefix nodes have no DIFFERENCE_ROLE payload and are never
        checkable, so they never appear here."""
        return [
            leaf.data(0, DIFFERENCE_ROLE)
            for leaf in self._flattened_leaves()
            if leaf.checkState(0) == Qt.CheckState.Checked
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: PASS (all tests, including pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/diff_merge_panel.py tests/ui/test_diff_merge_panel.py
git commit -m "feat(ui): add DiffMergePanel.checked_differences()"
```

---

### Task 11: Track the current diff Target project/path in `MainWindow`

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_diff_merge_entry_points.py`

Each of the three comparison entry points currently drops its `target`/`target_path` local variable once `show_differences` is called. `_apply_changes_to_target` (Task 13) needs to know which file Target actually was, so this task adds that tracking first, on its own, verified directly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_diff_merge_entry_points.py`:

```python
# tests/ui/test_diff_merge_entry_points.py (append)

def test_compare_merge_two_files_tracks_current_diff_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", VALID_PGTP)
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._compare_merge_two_files()

    assert window._current_diff_target_path == target_path
    assert window._current_diff_target_project is not None
    assert window._current_diff_target_project.pages[0].file_name == "development_equipment"


def test_compare_this_page_with_tracks_current_diff_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", VALID_PGTP))
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    page_item = window.project_tree.topLevelItem(0)
    menu = window.project_tree.build_page_menu(page_item)
    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ):
        find_action(menu, "Compare This Page With...").trigger()

    assert window._current_diff_target_path == target_path
    assert window._current_diff_target_project is not None


def test_compare_this_detail_with_tracks_current_diff_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", SOURCE_WITH_DETAIL_PGTP))
    target_path = _write(tmp_path, "target.pgtp", TARGET_WITH_CHANGED_DETAIL_PGTP)

    detail_item = window.project_tree.topLevelItem(0).child(0)
    menu = window.project_tree.build_detail_menu(detail_item)
    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ):
        find_action(menu, "Compare This Detail With...").trigger()

    assert window._current_diff_target_path == target_path
    assert window._current_diff_target_project is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui/test_diff_merge_entry_points.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute '_current_diff_target_path'`

- [ ] **Step 3: Add the tracking attributes and stash calls**

In `pgtp_editor/ui/main_window.py`, add the two new attributes next to the existing ones in `__init__`:

```python
        self._current_project = None
        self._current_project_path = None
        self._current_diff_target_project = None
        self._current_diff_target_path = None
```

In `_compare_merge_two_files`, right before the existing `differences = diff_project(source, target)` line, add:

```python
        self._current_diff_target_project = target
        self._current_diff_target_path = target_path
        differences = diff_project(source, target)
```

In `_compare_page_with`, right before `differences = compare_block(page_node, target_page, path=[page_node.file_name], node_kind="page")`, add:

```python
        self._current_diff_target_project = target
        self._current_diff_target_path = target_path
        differences = compare_block(page_node, target_page, path=[page_node.file_name], node_kind="page")
```

In `_compare_detail_with`, right before `differences = compare_block(detail_node, result, path=source_path, node_kind="detail")`, add:

```python
        self._current_diff_target_project = target
        self._current_diff_target_path = target_path_str
        differences = compare_block(detail_node, result, path=source_path, node_kind="detail")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_diff_merge_entry_points.py -v`
Expected: PASS (all tests, including pre-existing ones)

- [ ] **Step 5: Run full suite for regressions**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_diff_merge_entry_points.py
git commit -m "feat(ui): track current diff Target project/path across all three comparison entry points"
```

---

### Task 12: Ambiguity refusal gate in a standalone `_apply_changes_to_target` (no working-copy/write logic yet)

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_apply_changes_to_target.py` (new)

Building `_apply_changes_to_target` in two passes: this task wires the menu action and adds only the "no checked differences" and "ambiguous checked differences" early-exit behavior (spec §7.2), deferring the actual apply/write/backup logic to Task 13. This keeps each task's diff small and independently testable.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_apply_changes_to_target.py
"""Tests for MainWindow._apply_changes_to_target -- see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md §7.
"""
from unittest.mock import patch

from PySide6.QtCore import Qt

from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Old Caption"/>
    </Pages>
  </Presentation>
</Project>
"""

CHANGED_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="New Caption"/>
    </Pages>
  </Presentation>
</Project>
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _compare(window, source_path, target_path):
    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._compare_merge_two_files()


def test_apply_with_nothing_checked_shows_information_and_does_not_touch_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    _compare(window, source_path, target_path)
    original_target_bytes = open(target_path, "rb").read()

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._apply_changes_to_target()

    mock_info.assert_called_once()
    assert open(target_path, "rb").read() == original_target_bytes


def test_apply_with_ambiguous_checked_difference_refuses_entire_batch(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    _compare(window, source_path, target_path)
    original_target_bytes = open(target_path, "rb").read()

    panel = window.center_stage.diff_merge_panel
    leaves = panel._flattened_leaves()
    assert len(leaves) == 1
    diff = leaves[0].data(0, Qt.ItemDataRole.UserRole)
    diff.ambiguous = True
    leaves[0].setCheckState(0, Qt.CheckState.Checked)

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._apply_changes_to_target()

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert "Ambiguous" in args[1] or "ambiguous" in args[2].lower()
    assert not (tmp_path / "target.pgtp.bak").exists()
    assert open(target_path, "rb").read() == original_target_bytes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui/test_apply_changes_to_target.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute '_apply_changes_to_target'`

- [ ] **Step 3: Wire the menu action and add the two early-exit checks**

In `pgtp_editor/ui/main_window.py`, replace the `_build_diff_merge_menu` method:

```python
    def _build_diff_merge_menu(self):
        menu = self.menuBar().addMenu("Diff / Merge")
        compare_action = menu.addAction("Compare / Merge Two Files...")
        compare_action.triggered.connect(self._compare_merge_two_files)
        menu.addSeparator()
        next_action = menu.addAction("Next Difference")
        next_action.triggered.connect(self.center_stage.diff_merge_panel.select_next_difference)
        prev_action = menu.addAction("Prev Difference")
        prev_action.triggered.connect(self.center_stage.diff_merge_panel.select_previous_difference)
        apply_action = menu.addAction("Apply Changes to Target")
        apply_action.triggered.connect(self._apply_changes_to_target)
```

Add a new method, right after `_compare_detail_with`:

```python
    def _apply_changes_to_target(self):
        checked = self.center_stage.diff_merge_panel.checked_differences()
        if not checked:
            QMessageBox.information(
                self, "Apply Changes to Target", "No differences are checked to apply."
            )
            return

        ambiguous = [d for d in checked if d.ambiguous]
        if ambiguous:
            details = "\n".join(
                f"- {'/'.join(d.path)} ({d.node_kind}/{d.attribute}: {d.kind})" for d in ambiguous
            )
            QMessageBox.critical(
                self,
                "Cannot Apply: Ambiguous Differences Checked",
                "The following checked differences are ambiguous (matched via "
                "positional pairing of duplicate siblings) and cannot be safely "
                "applied automatically. Uncheck them and re-run Apply, or verify "
                "the pairing by hand in the detail view first:\n\n" + details,
            )
            return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_apply_changes_to_target.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run full suite for regressions**

Run: `pytest tests/ -v`
Expected: PASS. `tests/ui/test_menus.py::test_diff_merge_menu_contents` only asserts the menu's action *labels* (`"Apply Changes to Target"` still appears, unchanged) and does not exercise the old stub's `_not_implemented` trigger behavior, so it keeps passing unmodified — no changes needed there. No other existing test triggers this action expecting the old stub status-bar message, so no test deletions are needed in this task.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_apply_changes_to_target.py
git commit -m "feat(ui): wire Apply Changes to Target menu action with no-checked/ambiguous refusal gates"
```

---

### Task 13: Full end-to-end apply/backup/write/reload flow

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_apply_changes_to_target.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_apply_changes_to_target.py`:

```python
# tests/ui/test_apply_changes_to_target.py (append)
import os

from PySide6.QtCore import Qt


def _check_all_leaves(panel):
    for leaf in panel._flattened_leaves():
        leaf.setCheckState(0, Qt.CheckState.Checked)


def test_apply_successful_writes_bak_and_mutates_target_and_reloads_project_tree(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    original_target_bytes = open(target_path, "rb").read()
    _compare(window, source_path, target_path)

    panel = window.center_stage.diff_merge_panel
    _check_all_leaves(panel)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._apply_changes_to_target()

    mock_info.assert_called_once()

    bak_path = target_path + ".bak"
    assert os.path.exists(bak_path)
    assert open(bak_path, "rb").read() == original_target_bytes

    new_target_bytes = open(target_path, "rb").read()
    assert b'caption="New Caption"' in new_target_bytes

    # Project Tree / _current_project refreshed to the post-merge state.
    assert window._current_project is not None
    assert window._current_project.pages[0].attrib["caption"] == "New Caption"
    assert window._current_project_path == target_path

    # The change-list tree itself is left showing the just-applied
    # comparison as-is -- NOT cleared, NOT re-diffed.
    assert len(panel._flattened_leaves()) == 1


def test_apply_second_run_overwrites_previous_bak_with_first_runs_merged_content(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    _compare(window, source_path, target_path)
    panel = window.center_stage.diff_merge_panel
    _check_all_leaves(panel)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information"):
        window._apply_changes_to_target()

    first_merged_bytes = open(target_path, "rb").read()

    # Re-run Apply a second time on the same (now-stale) checked-differences
    # list without re-comparing.
    with patch("pgtp_editor.ui.main_window.QMessageBox.information"):
        window._apply_changes_to_target()

    bak_path = target_path + ".bak"
    assert open(bak_path, "rb").read() == first_merged_bytes


def test_apply_partial_failure_writes_nothing_and_names_the_unresolvable_difference(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    original_target_bytes = open(target_path, "rb").read()
    _compare(window, source_path, target_path)

    panel = window.center_stage.diff_merge_panel
    _check_all_leaves(panel)
    # Corrupt the one checked Difference's path so resolve_path fails inside
    # apply_differences, simulating Target having changed on disk since
    # compare-time.
    leaves = panel._flattened_leaves()
    diff = leaves[0].data(0, Qt.ItemDataRole.UserRole)
    diff.path = ["page_that_no_longer_exists"]

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._apply_changes_to_target()

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert "page_that_no_longer_exists" in args[2]
    assert not os.path.exists(target_path + ".bak")
    assert open(target_path, "rb").read() == original_target_bytes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui/test_apply_changes_to_target.py -v`
Expected: FAIL — `_apply_changes_to_target` currently returns after the ambiguity check with no further behavior, so nothing is ever written/backed-up/reloaded; `mock_info`/`mock_critical` for the success/failure paths are never called as expected.

- [ ] **Step 3: Complete `_apply_changes_to_target`**

Add the required imports at the top of `pgtp_editor/ui/main_window.py`:

```python
import shutil

from lxml import etree
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from pgtp_editor.diff.apply import apply_differences
from pgtp_editor.diff.differ import compare_block, diff_project
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.parser import _build_project_model, load_project
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.project_tree import ProjectTreePanel
```

Replace the `_apply_changes_to_target` method body (everything after the ambiguity-check `return` added in Task 12) so the full method reads:

```python
    def _apply_changes_to_target(self):
        checked = self.center_stage.diff_merge_panel.checked_differences()
        if not checked:
            QMessageBox.information(
                self, "Apply Changes to Target", "No differences are checked to apply."
            )
            return

        ambiguous = [d for d in checked if d.ambiguous]
        if ambiguous:
            details = "\n".join(
                f"- {'/'.join(d.path)} ({d.node_kind}/{d.attribute}: {d.kind})" for d in ambiguous
            )
            QMessageBox.critical(
                self,
                "Cannot Apply: Ambiguous Differences Checked",
                "The following checked differences are ambiguous (matched via "
                "positional pairing of duplicate siblings) and cannot be safely "
                "applied automatically. Uncheck them and re-run Apply, or verify "
                "the pairing by hand in the detail view first:\n\n" + details,
            )
            return

        target_project = self._current_diff_target_project
        target_path = self._current_diff_target_path

        import copy

        working_tree = copy.deepcopy(target_project.tree)
        working_project = _build_project_model(working_tree, source_description=target_path)
        result = apply_differences(working_project, checked)

        if result.failed:
            details = "\n".join(f"- {'/'.join(f.difference.path)}: {f.message}" for f in result.failed)
            QMessageBox.critical(
                self,
                "Apply Failed -- No Changes Written",
                f"{len(result.failed)} of {len(checked)} checked differences could not "
                f"be applied (Target may have changed since this comparison was run). "
                f"No changes were written to '{target_path}'.\n\n" + details,
            )
            return

        backup_path = target_path + ".bak"
        shutil.copy2(target_path, backup_path)
        serialized = etree.tostring(
            working_tree, xml_declaration=False, encoding="UTF-8", pretty_print=False
        )
        with open(target_path, "wb") as f:
            f.write(serialized)

        QMessageBox.information(
            self,
            "Apply Changes to Target",
            f"Applied {len(checked)} change(s) to '{target_path}'.\nBackup saved to '{backup_path}'.",
        )
        self.open_project_file(target_path)
```

Move the `import copy` line to the top of the file alongside the other imports instead of inline (cleaner, matches the rest of the file's style) — final top-of-file import block for `pgtp_editor/ui/main_window.py`:

```python
import copy
import shutil

from lxml import etree
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from pgtp_editor.diff.apply import apply_differences
from pgtp_editor.diff.differ import compare_block, diff_project
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.parser import _build_project_model, load_project
from pgtp_editor.ui._stub_action import add_stub_action
from pgtp_editor.ui.about import show_about_dialog
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.project_tree import ProjectTreePanel
```

And remove the inline `import copy` line inside `_apply_changes_to_target` itself (now redundant with the top-of-file import) — the method's body up through the `working_project = ...` line becomes:

```python
        target_project = self._current_diff_target_project
        target_path = self._current_diff_target_path

        working_tree = copy.deepcopy(target_project.tree)
        working_project = _build_project_model(working_tree, source_description=target_path)
        result = apply_differences(working_project, checked)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ui/test_apply_changes_to_target.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run full suite for regressions**

Run: `pytest tests/ -v`
Expected: PASS — every prior test (differ, resolve, parser, nodes, round-trip fidelity, diff_merge_panel, diff_merge_entry_points, apply) continues to pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_apply_changes_to_target.py
git commit -m "feat(ui): complete end-to-end Apply Changes to Target flow (apply, backup, write, reload)"
```

---

### Task 14: Integration test against a real sample file

**Files:**
- Create: `tests/ui/test_apply_changes_to_target_real_sample.py`

- [ ] **Step 1: Write the test**

```python
# tests/ui/test_apply_changes_to_target_real_sample.py
"""End-to-end integration test for Apply Changes to Target against a real
sample .pgtp file, per
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md
§9's testing strategy: construct a small deliberate diff between two temp
copies of a real sample file, check some differences, Apply, and verify the
target file changed correctly and a .bak exists with the original content.
"""
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

from pgtp_editor.model.parser import load_project
from pgtp_editor.ui.main_window import MainWindow

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"
SAMPLE_FILE = SAMPLE_DIR / "dev_Ferrara.pgtp"


def _require_sample():
    if not SAMPLE_FILE.exists():
        pytest.skip(f"sample file not present: {SAMPLE_FILE}")


def test_apply_changes_to_target_against_real_sample_file(qtbot, tmp_path):
    _require_sample()

    # Two independent temp copies: Source will be edited, Target stays as
    # a pristine copy of the real sample so Apply's mutation is checked
    # against a known-real-world XML shape.
    source_path = tmp_path / "source.pgtp"
    target_path = tmp_path / "target.pgtp"
    shutil.copy2(SAMPLE_FILE, source_path)
    shutil.copy2(SAMPLE_FILE, target_path)
    original_target_bytes = target_path.read_bytes()

    # Make one small, deliberate, unambiguous change in Source: alter the
    # first top-level Page's "caption" attribute.
    project = load_project(source_path)
    first_page = project.pages[0]
    original_caption = first_page.attrib.get("caption")
    new_caption = (original_caption or "") + " (edited by test)"
    first_page.element.set("caption", new_caption)
    from lxml import etree

    serialized = etree.tostring(
        project.tree, xml_declaration=False, encoding="UTF-8", pretty_print=False
    )
    source_path.write_bytes(serialized)

    window = MainWindow()
    qtbot.addWidget(window)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(str(source_path), ""), (str(target_path), "")],
    ):
        window._compare_merge_two_files()

    panel = window.center_stage.diff_merge_panel
    leaves = panel._flattened_leaves()
    caption_leaves = [
        leaf for leaf in leaves
        if leaf.data(0, Qt.ItemDataRole.UserRole).attribute == "caption"
        and leaf.data(0, Qt.ItemDataRole.UserRole).path == [first_page.file_name]
    ]
    assert len(caption_leaves) == 1
    caption_leaves[0].setCheckState(0, Qt.CheckState.Checked)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._apply_changes_to_target()

    mock_info.assert_called_once()

    bak_path = Path(str(target_path) + ".bak")
    assert bak_path.exists()
    assert bak_path.read_bytes() == original_target_bytes

    merged_project = load_project(target_path)
    merged_first_page = next(
        p for p in merged_project.pages if p.file_name == first_page.file_name
    )
    assert merged_first_page.attrib.get("caption") == new_caption
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/ui/test_apply_changes_to_target_real_sample.py -v`
Expected: PASS (1 passed). If the sample file is not present in the environment running this test, it is skipped rather than failing (matching the existing convention in `tests/model/test_parser_real_samples.py`).

- [ ] **Step 3: Run the full test suite one final time**

Run: `pytest tests/ -v`
Expected: PASS — full suite green, including every test added across all fourteen tasks in this plan.

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_apply_changes_to_target_real_sample.py
git commit -m "test(ui): add end-to-end Apply Changes to Target integration test against real sample file"
```

---

## Summary of files touched

- `pgtp_editor/model/nodes.py` — retained-element fields (Task 1)
- `pgtp_editor/model/parser.py` — `load_project`/`_build_project_model` split, element retention (Task 2)
- `pgtp_editor/diff/apply.py` — new module, `ApplyResult`/`ApplyFailure`/`apply_differences` (Tasks 4-9)
- `pgtp_editor/ui/diff_merge_panel.py` — `checked_differences()` (Task 10)
- `pgtp_editor/ui/main_window.py` — Target tracking, real `_apply_changes_to_target` (Tasks 11-13)
- New tests: `tests/model/test_nodes.py`, `tests/model/test_round_trip_fidelity.py`, `tests/diff/test_apply.py`, `tests/ui/test_apply_changes_to_target.py`, `tests/ui/test_apply_changes_to_target_real_sample.py`, plus additions to `tests/model/test_parser.py`, `tests/ui/test_diff_merge_panel.py`, `tests/ui/test_diff_merge_entry_points.py`. `tests/ui/test_menus.py` needs no changes (it only asserts action labels, which are unchanged).
