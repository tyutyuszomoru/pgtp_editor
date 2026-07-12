# PGTP Editor — Properties Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only, navigate-only Properties panel that shows every attribute phpgen lets you set on the currently-selected Page/Detail/Column/Event tree node, and jumps to (and highlights) the corresponding line/attribute in the XML Editor when a row is clicked.

**Architecture:** A new `pgtp_editor/ui/properties_panel.py` module holds pure, Qt-free row-building functions (one per node kind) plus a `PropertiesPanel(QWidget)` that turns rows into a `QTableWidget` and wires row-clicks to an injected navigation object. `pgtp_editor/model/nodes.py`/`parser.py` gain a small `DetailNode.inner_sourceline` field so Detail rows can split their navigation target between the outer `<Detail>` element and its nested `<Page>`. `pgtp_editor/ui/project_tree.py` gains `MODEL_NODE_ROLE` coverage for Column/Event items plus a `currentItemChanged`-driven `on_selection_changed` callback. `pgtp_editor/ui/main_window.py` wires the tree's selection callback to a real `PropertiesPanel` instance, replacing today's placeholder `QWidget()`.

Because the sibling XML Editor Foundation sub-project (which will provide the real `XmlEditor` widget) is not yet merged into this worktree, this plan builds and tests all navigation-call logic against a small hand-written **test double** (`_RecordingXmlEditorStub`, defined directly inside the panel's test file) that implements the three methods this document's design spec calls for: `navigate_to_line(line)`, `line_text(line)`, `select_range_on_line(line, start, end)`. `PropertiesPanel` takes this object (or, eventually, a real `XmlEditor`) via constructor injection, so no test or production code here hard-codes a dependency on `XmlEditor` existing. The final task wires `MainWindow` to construct `PropertiesPanel` using a small local stand-in (see Task 9) with a clearly marked follow-up comment for the day `CenterStage.xml_editor` is real; a true end-to-end integration test against a real `XmlEditor` is explicitly out of scope until that sub-project merges (see "Blocked work" at the end of this document).

**Tech Stack:** Python 3.13, PySide6 (Qt widgets), lxml (existing parser dependency), pytest, pytest-qt.

---

## Current-state facts confirmed by reading this worktree's code (do not re-derive these — just use them)

- `pgtp_editor/model/nodes.py`: `DetailNode` currently has `identity`, `attrib`, `sourceline: int | None = None`, `details`, `columns`, `events`. No `inner_sourceline` field exists yet.
- `pgtp_editor/model/parser.py`'s `_parse_detail` reads `inner_page_el = detail_el.find("Page")` and uses `inner_page_el.sourceline` implicitly only via `merged_attrib`/`columns`/`events`/`nested_details` — the raw `inner_page_el.sourceline` value itself is never stored today.
- `pgtp_editor/ui/project_tree.py` already defines `NODE_KIND_ROLE = Qt.ItemDataRole.UserRole`, `TABLE_NAME_ROLE = Qt.ItemDataRole.UserRole + 1`, `MODEL_NODE_ROLE = Qt.ItemDataRole.UserRole + 2`. Page and Detail items already get `.setData(0, MODEL_NODE_ROLE, node)` in `populate_from_project`/`_populate_details_and_events`. Column and Event items (built in `_populate_details_and_events`) currently only get `NODE_KIND_ROLE` set — no `MODEL_NODE_ROLE`.
- `ProjectTreePanel.__init__` signature today: `def __init__(self, parent=None, on_stub_action=None, on_compare_page=None, on_compare_detail=None)`. No `currentItemChanged`/`itemSelectionChanged` wiring exists anywhere in the file.
- `pgtp_editor/ui/main_window.py`'s `MainWindow.__init__` builds `self.project_tree = ProjectTreePanel(on_stub_action=..., on_compare_page=..., on_compare_detail=...)`, then later `self.properties_panel = QWidget()` wrapped in `self.properties_dock`, and separately `self.center_stage = CenterStage()` (constructed *after* the docks, as `self.centralWidget()`).
- `pgtp_editor/ui/center_stage.py`'s `CenterStage` has **no `xml_editor` attribute at all** today — its "Raw XML" tab is a bare placeholder `QWidget()` (`self.raw_xml_tab_index = self.addTab(QWidget(), "Raw XML")`). The XML Editor Foundation sub-project (which will add a real `XmlEditor` there) is not merged into this worktree yet. This plan does not invent or touch `CenterStage.xml_editor` — see Task 9's stand-in approach.
- `tests/model/` already exists in this worktree, from the earlier Real Model sub-project, containing `__init__.py`, `test_parser.py` (synthetic-XML parser tests), and `test_parser_real_samples.py` (real-sample-file regression tests, using `pytest.skip` if the sample files are absent). Task 1/Task 2 add a new `tests/model/test_nodes.py` and extend the existing `test_parser.py` — they do not recreate `__init__.py`.
- `sample/*.pgtp` files (gitignored, listed in `.gitignore` as `sample/`) **do exist** in this worktree's working tree today: `sample/dev_Ferrara.pgtp` and `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`. This was directly verified by loading `sample/dev_Ferrara.pgtp` through `pgtp_editor.model.parser.load_project` and running the design spec's own `_count_functions` regex against its real `OnEditFormLoaded` event bodies: two real bodies of length 3561 and 3572 characters yield counts of 14 and 12 respectively, exactly matching the spec's §3.3 claim (allowing for the spec's own approximate "3579/3572-character" phrasing). Task 6 therefore reads real sample data directly via `load_project`, following the same pattern already established by `tests/model/test_parser_real_samples.py`, rather than reconstructing approximate fixture text.
- Existing test conventions: `tests/ui/test_project_tree.py` and `tests/ui/test_main_window.py` use `qtbot` (pytest-qt) fixtures, `qtbot.addWidget(...)`, and a shared `tests/ui/_sample_project.py` helper (`build_sample_project()`) for synthetic `ProjectModel` data.

---

## Task 1: `DetailNode.inner_sourceline` model field

**Files:**
- Modify: `pgtp_editor/model/nodes.py`
- Test: `tests/model/test_nodes.py` (new file)

- [ ] **Step 1: Write the failing test**

`tests/model/` already exists in this worktree (from the earlier Real Model sub-project, containing `__init__.py`, `test_parser.py`, `test_parser_real_samples.py`) — no directory or `__init__.py` needs to be created. Create the new file `tests/model/test_nodes.py`:

```python
from pgtp_editor.model.nodes import DetailNode


def test_detail_node_inner_sourceline_defaults_to_none():
    detail = DetailNode(identity="x", attrib={}, sourceline=10)
    assert detail.inner_sourceline is None


def test_detail_node_inner_sourceline_can_be_set():
    detail = DetailNode(identity="x", attrib={}, sourceline=10, inner_sourceline=25)
    assert detail.sourceline == 10
    assert detail.inner_sourceline == 25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/test_nodes.py -v`
Expected: FAIL — `TypeError: DetailNode.__init__() got an unexpected keyword argument 'inner_sourceline'`

- [ ] **Step 3: Add the field**

In `pgtp_editor/model/nodes.py`, modify the `DetailNode` dataclass:

```python
@dataclass
class DetailNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    inner_sourceline: int | None = None
    details: list["DetailNode"] = field(default_factory=list)
    columns: list[ColumnNode] = field(default_factory=list)
    events: list[EventNode] = field(default_factory=list)

    @property
    def table_name(self) -> str | None:
        return self.attrib.get("tableName")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/model/test_nodes.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/model/test_nodes.py pgtp_editor/model/nodes.py
git commit -m "feat: add DetailNode.inner_sourceline field"
```

---

## Task 2: Populate `inner_sourceline` in the parser

**Files:**
- Modify: `pgtp_editor/model/parser.py:98-105` (`_parse_detail`'s `return DetailNode(...)`)
- Modify (append test): `tests/model/test_parser.py` (already exists, from the earlier Real Model sub-project — reuses its existing `write_pgtp`/`SIMPLE_PROJECT` fixtures already defined at the top of the file, do not redefine them)

- [ ] **Step 1: Write the failing test**

Append to `tests/model/test_parser.py` (the file already imports `write_pgtp` and defines `SIMPLE_PROJECT` at module level — reuse both, don't redefine):

```python
def test_detail_inner_sourceline_is_nested_page_own_line(tmp_path):
    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    project = load_project(path)
    detail = project.pages[0].details[0]
    # In SIMPLE_PROJECT (after textwrap.dedent), line 15 is
    # '<Detail caption="Equipment\\Sub-item">' and line 16 is the nested
    # '<Page fileName="" tableName="pr.attachment" caption="Sub-item">'.
    assert detail.sourceline == 15
    assert detail.inner_sourceline == 16
    assert detail.sourceline != detail.inner_sourceline
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/test_parser.py -v -k inner_sourceline`
Expected: FAIL — `AssertionError: assert None == 15` (since `inner_sourceline` defaults to `None` and is never populated yet)

- [ ] **Step 3: Populate the field in `_parse_detail`**

In `pgtp_editor/model/parser.py`, modify the `return DetailNode(...)` statement inside `_parse_detail`:

```python
    return DetailNode(
        identity=identity,
        attrib=merged_attrib,
        sourceline=detail_el.sourceline,
        inner_sourceline=inner_page_el.sourceline,
        details=nested_details,
        columns=columns,
        events=events,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/model/test_parser.py tests/model/test_nodes.py -v -k "inner_sourceline or test_detail_node"`
Expected: PASS (3 passed: the 2 tests from Task 1 plus this new one)

- [ ] **Step 5: Run the full test suite to check nothing else broke**

Run: `python -m pytest -q`
Expected: all existing tests still pass, plus the 3 new ones.

- [ ] **Step 6: Commit**

```bash
git add tests/model/test_parser.py pgtp_editor/model/parser.py
git commit -m "feat: populate DetailNode.inner_sourceline from nested Page element"
```

---

## Task 3: `MODEL_NODE_ROLE` on Column and Event tree items

**Files:**
- Modify: `pgtp_editor/ui/project_tree.py:38-57` (`_populate_details_and_events`)
- Test: `tests/ui/test_project_tree.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_project_tree.py` (after the existing `test_detail_item_carries_model_node`, keeping the existing `from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE` import already present near the bottom of the file):

```python
def test_column_item_carries_model_node(qtbot):
    tree = make_populated_tree(qtbot)
    column_item = tree.topLevelItem(0).child(0).child(0)
    node = column_item.data(0, MODEL_NODE_ROLE)
    assert node.field_name == "tag"


def test_event_item_carries_model_node(qtbot):
    tree = make_populated_tree(qtbot)
    event_item = tree.topLevelItem(0).child(2)
    node = event_item.data(0, MODEL_NODE_ROLE)
    assert node.tag_name == "OnPreparePage"
    assert node.side == "S"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_project_tree.py -v -k "carries_model_node"`
Expected: FAIL on the two new tests — `AttributeError: 'NoneType' object has no attribute 'field_name'` / `'tag_name'` (since `MODEL_NODE_ROLE` is never set on Column/Event items, `.data(...)` returns `None`)

- [ ] **Step 3: Set `MODEL_NODE_ROLE` on Column and Event items**

In `pgtp_editor/ui/project_tree.py`, modify `_populate_details_and_events`:

```python
    def _populate_details_and_events(self, parent_item, node):
        # Ordering matches the tree's established display shape: nested
        # Details first, then this node's own Columns, then its Events.
        for detail in node.details:
            detail_name = detail.attrib.get("caption") or detail.table_name or detail.identity
            detail_table = detail.table_name or ""
            detail_item = QTreeWidgetItem([f"(D) {detail_name} [{detail_table}]"])
            detail_item.setData(0, NODE_KIND_ROLE, "detail")
            detail_item.setData(0, TABLE_NAME_ROLE, detail_table)
            detail_item.setData(0, MODEL_NODE_ROLE, detail)
            parent_item.addChild(detail_item)
            self._populate_details_and_events(detail_item, detail)
        for column in node.columns:
            column_item = QTreeWidgetItem([f"(C) {column.field_name}"])
            column_item.setData(0, NODE_KIND_ROLE, "column")
            column_item.setData(0, MODEL_NODE_ROLE, column)
            parent_item.addChild(column_item)
        for event in node.events:
            event_item = QTreeWidgetItem([f"(E) {event.side}.{event.tag_name}"])
            event_item.setData(0, NODE_KIND_ROLE, "event")
            event_item.setData(0, MODEL_NODE_ROLE, event)
            parent_item.addChild(event_item)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_project_tree.py -v`
Expected: all tests pass, including the 2 new ones.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/project_tree.py tests/ui/test_project_tree.py
git commit -m "feat: set MODEL_NODE_ROLE on Column and Event tree items"
```

---

## Task 4: `ProjectTreePanel`'s `on_selection_changed` callback

**Files:**
- Modify: `pgtp_editor/ui/project_tree.py:12-20` (`ProjectTreePanel.__init__`)
- Test: `tests/ui/test_project_tree.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_project_tree.py`:

```python
def test_selection_changed_callback_invoked_with_node_and_kind(qtbot):
    calls = []
    tree = ProjectTreePanel(on_selection_changed=lambda node, kind: calls.append((node, kind)))
    qtbot.addWidget(tree)
    tree.populate_from_project(build_sample_project())

    page_item = tree.topLevelItem(0)
    tree.setCurrentItem(page_item)

    assert len(calls) == 1
    node, kind = calls[0]
    assert kind == "page"
    assert node.table_name == "pr.equipment"


def test_selection_changed_callback_invoked_with_none_when_cleared(qtbot):
    calls = []
    tree = ProjectTreePanel(on_selection_changed=lambda node, kind: calls.append((node, kind)))
    qtbot.addWidget(tree)
    tree.populate_from_project(build_sample_project())

    tree.setCurrentItem(tree.topLevelItem(0))
    tree.setCurrentItem(None)

    assert calls[-1] == (None, None)


def test_selection_changed_callback_defaults_to_noop(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(build_sample_project())
    # Must not raise even though no callback was supplied.
    tree.setCurrentItem(tree.topLevelItem(0))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_project_tree.py -v -k "selection_changed"`
Expected: FAIL — `TypeError: ProjectTreePanel.__init__() got an unexpected keyword argument 'on_selection_changed'`

- [ ] **Step 3: Add the callback and signal connection**

In `pgtp_editor/ui/project_tree.py`, modify `ProjectTreePanel.__init__`:

```python
class ProjectTreePanel(QTreeWidget):
    def __init__(
        self,
        parent=None,
        on_stub_action=None,
        on_compare_page=None,
        on_compare_detail=None,
        on_selection_changed=None,
    ):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._on_stub_action = on_stub_action or (lambda label: None)
        self._on_compare_page = on_compare_page or (lambda page_node: None)
        self._on_compare_detail = on_compare_detail or (lambda detail_node, source_path: None)
        self._on_selection_changed = on_selection_changed or (lambda node, kind: None)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.currentItemChanged.connect(self._on_current_item_changed)

    def _on_current_item_changed(self, current, _previous):
        if current is None:
            self._on_selection_changed(None, None)
            return
        node = current.data(0, MODEL_NODE_ROLE)
        kind = current.data(0, NODE_KIND_ROLE)
        self._on_selection_changed(node, kind)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_project_tree.py -v`
Expected: all tests pass, including the 3 new ones.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/project_tree.py tests/ui/test_project_tree.py
git commit -m "feat: add on_selection_changed callback to ProjectTreePanel"
```

---

## Task 5: `RowSpec` and row-building functions for Page/Column/Detail (Qt-free)

**Files:**
- Create: `pgtp_editor/ui/properties_panel.py`
- Test: `tests/ui/test_properties_panel_rows.py` (new file — kept Qt-free per the spec's §4.1 testing strategy)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_properties_panel_rows.py`:

```python
from pgtp_editor.model.nodes import ColumnNode, DetailNode, PageNode
from pgtp_editor.ui.properties_panel import (
    RowSpec,
    _rows_for_attrib_node,
    _rows_for_detail,
)


def test_rows_for_page_one_row_per_attrib_key():
    page = PageNode(
        identity="equipment",
        attrib={"fileName": "development_equipment", "tableName": "pr.equipment"},
        sourceline=5,
    )
    rows = _rows_for_attrib_node(page)
    assert rows == [
        RowSpec(property_label="fileName", value="development_equipment", target_line=5, attr_name="fileName"),
        RowSpec(property_label="tableName", value="pr.equipment", target_line=5, attr_name="tableName"),
    ]


def test_rows_for_column_one_row_per_attrib_key():
    column = ColumnNode(identity="tag", attrib={"fieldName": "tag", "caption": "Tag"}, sourceline=42)
    rows = _rows_for_attrib_node(column)
    assert rows == [
        RowSpec(property_label="fieldName", value="tag", target_line=42, attr_name="fieldName"),
        RowSpec(property_label="caption", value="Tag", target_line=42, attr_name="caption"),
    ]


def test_rows_for_detail_caption_uses_outer_sourceline_others_use_inner():
    detail = DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment", "viewAbilityMode": "1"},
        sourceline=10,
        inner_sourceline=25,
    )
    rows = _rows_for_detail(detail)
    assert rows == [
        RowSpec(property_label="caption", value="Sub-item", target_line=10, attr_name="caption"),
        RowSpec(property_label="tableName", value="pr.attachment", target_line=25, attr_name="tableName"),
        RowSpec(property_label="viewAbilityMode", value="1", target_line=25, attr_name="viewAbilityMode"),
    ]


def test_rows_for_detail_missing_inner_sourceline_falls_back_to_none():
    detail = DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment"},
        sourceline=10,
        inner_sourceline=None,
    )
    rows = _rows_for_detail(detail)
    caption_row = next(r for r in rows if r.property_label == "caption")
    table_name_row = next(r for r in rows if r.property_label == "tableName")
    assert caption_row.target_line == 10
    assert table_name_row.target_line is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_properties_panel_rows.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.ui.properties_panel'`

- [ ] **Step 3: Create `properties_panel.py` with `RowSpec` and the Page/Column/Detail row builders**

Create `pgtp_editor/ui/properties_panel.py`:

```python
# pgtp_editor/ui/properties_panel.py
"""The Properties panel: a read-only, navigate-only viewer of the currently
selected Page/Detail/Column/Event tree node's attributes.

Row-building is implemented as plain functions over the model dataclasses in
pgtp_editor.model.nodes, deliberately kept Qt-free so they are unit-testable
without a QApplication. PropertiesPanel (added in a later task) is the only
place that turns a list[RowSpec] into actual QTableWidgetItems.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RowSpec:
    property_label: str
    value: str
    target_line: int | None
    attr_name: str | None  # None for rows with no single key="value" to refine onto


def _rows_for_attrib_node(node) -> list[RowSpec]:
    """Shared helper for Page/Column: one row per attrib key, all rows
    navigating to the node's own sourceline."""
    return [
        RowSpec(property_label=key, value=str(value), target_line=node.sourceline, attr_name=key)
        for key, value in node.attrib.items()
    ]


def _rows_for_detail(detail_node) -> list[RowSpec]:
    """One row per Detail attrib key, with a per-row line split: the
    'caption' row navigates to the outer <Detail> element's own line
    (detail_node.sourceline); every other row navigates to the nested
    <Page> element's line (detail_node.inner_sourceline), since real
    .pgtp files only ever put 'caption' on the outer <Detail> and
    everything else (tableName, ability modes, etc.) on the nested Page.
    """
    rows = []
    for key, value in detail_node.attrib.items():
        line = detail_node.sourceline if key == "caption" else detail_node.inner_sourceline
        rows.append(RowSpec(property_label=key, value=str(value), target_line=line, attr_name=key))
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_properties_panel_rows.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/properties_panel.py tests/ui/test_properties_panel_rows.py
git commit -m "feat: add RowSpec and Page/Column/Detail row-building for Properties panel"
```

---

## Task 6: Event row-building and the `_count_functions` heuristic

**Files:**
- Modify: `pgtp_editor/ui/properties_panel.py` (add `_rows_for_event`, `_FUNCTION_DECL_RE`, `_count_functions`)
- Test: `tests/ui/test_properties_panel_rows.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_properties_panel_rows.py` (update the import line at the top to include the new names):

```python
from pgtp_editor.model.nodes import ColumnNode, DetailNode, EventNode, PageNode
from pgtp_editor.ui.properties_panel import (
    RowSpec,
    _count_functions,
    _rows_for_attrib_node,
    _rows_for_detail,
    _rows_for_event,
)
```

Then append these test functions:

```python
def test_rows_for_event_client_side_label():
    event = EventNode(identity="e", tag_name="OnRowProcess", side="C", text="function foo() {}", sourceline=7)
    rows = _rows_for_event(event)
    assert rows == [
        RowSpec("Handler", "OnRowProcess", 7, attr_name=None),
        RowSpec("Side", "Client", 7, attr_name=None),
        RowSpec("Functions", "1", 7, attr_name=None),
    ]


def test_rows_for_event_server_side_label():
    event = EventNode(identity="e", tag_name="OnPreparePage", side="S", text="", sourceline=3)
    rows = _rows_for_event(event)
    side_row = next(r for r in rows if r.property_label == "Side")
    assert side_row.value == "Server"


def test_count_functions_named_declaration():
    assert _count_functions("function foo() {}") == 1


def test_count_functions_anonymous_no_space():
    assert _count_functions("function() {}") == 1


def test_count_functions_anonymous_with_space():
    assert _count_functions("function () {}") == 1


def test_count_functions_false_positive_substring_not_counted():
    assert _count_functions("functionallocation") == 0


def test_count_functions_arrow_function_not_counted_documented_gap():
    assert _count_functions("const f = (x) => x") == 0


def test_count_functions_empty_and_none_text():
    assert _count_functions("") == 0
    assert _count_functions(None) == 0


def test_count_functions_php_snippet_with_zero_functions():
    # Real OnCalculateFields-style body: a bare conditional, no function
    # declarations at all. "Functions: 0" is a common, correct result.
    body = "if ($fieldName == 'manning') { $value = $res[0]['manning']; }"
    assert _count_functions(body) == 0


def test_count_functions_synthetic_named_and_anonymous_mix():
    # A hand-built body exercising the same named+anonymous function mix
    # documented in the design spec's grounding pass against dev_Ferrara.pgtp's
    # real OnEditFormLoaded bodies (5 named functions plus several anonymous
    # callbacks passed as arguments). The real-sample regression test against
    # the actual file is added separately below, in test_parser_real_samples.py.
    body = """
    function setLoadingState() { }
    function setReadyState() { }
    function initLimit() { }
    function onOperationReady() { }
    function initJobcardDeps() { }
    setTimeout(function() { doStuff(); }, 100);
    $('.foo').setQueryFunction(function(term) { return term; });
    $('span.subs').each(function() { markDone(); });
    """
    assert _count_functions(body) == 8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_properties_panel_rows.py -v`
Expected: FAIL — `ImportError: cannot import name '_count_functions'` (and `_rows_for_event`)

- [ ] **Step 3: Add `_rows_for_event`, `_FUNCTION_DECL_RE`, and `_count_functions`**

Append to `pgtp_editor/ui/properties_panel.py` (after `_rows_for_detail`):

```python
_FUNCTION_DECL_RE = re.compile(r"\bfunction\s*[A-Za-z_$][A-Za-z0-9_$]*\s*\(|\bfunction\s*\(")


def _count_functions(text: str | None) -> int:
    """Approximate, regex-based count of JS/PHP function declarations
    (named and anonymous) in an event handler body. Not a real parser:
    misses ES6 arrow functions entirely, and cannot distinguish a
    'function' token inside a string/comment from a real declaration.
    Both gaps are accepted — see design spec §3.3.
    """
    return len(_FUNCTION_DECL_RE.findall(text or ""))


def _rows_for_event(event_node) -> list[RowSpec]:
    """Exactly three rows for an EventNode: Handler, Side, and a
    heuristic Functions count. All three navigate to the event's own
    <OnXxx> opening line; none of them is a key="value" attribute pair,
    so attr_name is None for all three (no column-precise refinement)."""
    side_label = "Client" if event_node.side == "C" else "Server"
    return [
        RowSpec("Handler", event_node.tag_name, event_node.sourceline, attr_name=None),
        RowSpec("Side", side_label, event_node.sourceline, attr_name=None),
        RowSpec("Functions", str(_count_functions(event_node.text)), event_node.sourceline, attr_name=None),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_properties_panel_rows.py -v`
Expected: PASS (all tests, including the 9 new ones)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/properties_panel.py tests/ui/test_properties_panel_rows.py
git commit -m "feat: add Event row-building and function-count heuristic"
```

- [ ] **Step 7: Add a real-sample regression test grounding the heuristic against actual `EventHandlers` bodies**

`sample/dev_Ferrara.pgtp` exists in this worktree's working tree (gitignored, per `.gitignore`'s `sample/` entry, but present on disk today) alongside the existing `tests/model/test_parser_real_samples.py`, which already has a `_require_sample`/`pytest.skip` guard for environments where the sample files are absent. Add a new test to that same file (not `tests/ui/test_properties_panel_rows.py`, since this test needs `load_project` and belongs with the other real-sample parser regression tests) — append to `tests/model/test_parser_real_samples.py`:

```python
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
```

Run: `python -m pytest tests/model/test_parser_real_samples.py -v -k "function"`
Expected: PASS (2 passed) -- verified directly during this plan's own authoring by loading `sample/dev_Ferrara.pgtp` through `load_project` and running the exact `_count_functions` regex against its real `OnEditFormLoaded`/`OnCalculateFields` bodies: two real `OnEditFormLoaded` bodies of length 3561 and 3572 yielded counts of 14 and 12 respectively, and a real `OnCalculateFields` body yielded 0, all matching the values asserted above.

- [ ] **Step 8: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: all tests pass.

```bash
git add tests/model/test_parser_real_samples.py
git commit -m "test: ground _count_functions heuristic against real sample EventHandlers bodies"
```

---

## Task 7: `PropertiesPanel` widget — population per node kind and empty state

**Files:**
- Modify: `pgtp_editor/ui/properties_panel.py` (add `PropertiesPanel(QWidget)`)
- Test: `tests/ui/test_properties_panel.py` (new file — `pytest-qt`, real `QTableWidget`)

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_properties_panel.py`:

```python
from pgtp_editor.model.nodes import ColumnNode, DetailNode, EventNode, PageNode
from pgtp_editor.ui.properties_panel import PropertiesPanel


class _RecordingXmlEditorStub:
    """Test double standing in for the not-yet-merged XmlEditor. Records
    every call so tests can assert on navigation behavior without a real
    XML Editor widget existing in this worktree yet."""

    def __init__(self, line_text_by_line: dict[int, str] | None = None):
        self.navigate_calls: list[int] = []
        self.line_text_calls: list[int] = []
        self.select_range_calls: list[tuple[int, int, int]] = []
        self._line_text_by_line = line_text_by_line or {}

    def navigate_to_line(self, line: int) -> None:
        self.navigate_calls.append(line)

    def line_text(self, line: int) -> str:
        self.line_text_calls.append(line)
        return self._line_text_by_line.get(line, "")

    def select_range_on_line(self, line: int, start: int, end: int) -> None:
        self.select_range_calls.append((line, start, end))


def _page_node():
    return PageNode(
        identity="equipment",
        attrib={"fileName": "development_equipment", "tableName": "pr.equipment"},
        sourceline=5,
    )


def _column_node():
    return ColumnNode(identity="tag", attrib={"fieldName": "tag", "caption": "Tag"}, sourceline=42)


def _detail_node():
    return DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment"},
        sourceline=10,
        inner_sourceline=25,
    )


def _event_node():
    return EventNode(identity="e", tag_name="OnRowProcess", side="C", text="function foo() {}", sourceline=7)


def test_empty_state_when_no_node_selected(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(None, None)
    assert panel.is_showing_empty_state() is True


def test_page_population_row_count_and_header(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    assert panel.is_showing_empty_state() is False
    assert panel.table.rowCount() == 2
    assert panel.header_text() == "Page: development_equipment"
    assert panel.table.item(0, 0).text() == "fileName"
    assert panel.table.item(0, 1).text() == "development_equipment"


def test_column_population(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_column_node(), "column")
    assert panel.table.rowCount() == 2
    assert panel.header_text() == "Column: tag"


def test_detail_population(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_detail_node(), "detail")
    assert panel.table.rowCount() == 2
    assert panel.header_text() == "Detail: pr.attachment/Sub-item"


def test_event_population_shows_client_server_and_functions(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_event_node(), "event")
    assert panel.table.rowCount() == 3
    assert panel.header_text() == "Event: OnRowProcess"
    assert panel.table.item(0, 0).text() == "Handler"
    assert panel.table.item(0, 1).text() == "OnRowProcess"
    assert panel.table.item(1, 1).text() == "Client"
    assert panel.table.item(2, 0).text() == "Functions"
    assert panel.table.item(2, 1).text() == "1"


def test_show_node_with_none_after_population_returns_to_empty_state(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    assert panel.is_showing_empty_state() is False
    panel.show_node(None, None)
    assert panel.is_showing_empty_state() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_properties_panel.py -v`
Expected: FAIL — `ImportError: cannot import name 'PropertiesPanel'`

- [ ] **Step 3: Add `PropertiesPanel` to `properties_panel.py`**

Append to `pgtp_editor/ui/properties_panel.py`:

```python
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_EMPTY_STATE_MESSAGE = "Select a Page, Detail, Column, or Event to see its properties"

_ROW_BUILDERS = {
    "page": (lambda n: _rows_for_attrib_node(n), lambda n: f"Page: {n.file_name or n.identity}"),
    "detail": (_rows_for_detail, lambda n: f"Detail: {n.table_name}/{n.attrib.get('caption', '')}"),
    "column": (lambda n: _rows_for_attrib_node(n), lambda n: f"Column: {n.field_name}"),
    "event": (_rows_for_event, lambda n: f"Event: {n.tag_name}"),
}


class PropertiesPanel(QWidget):
    """Read-only, navigate-only viewer for the currently selected Page,
    Detail, Column, or Event node. Never edits a value; clicking a row
    calls into an injected xml_editor object's navigate_to_line (and,
    for attribute rows, line_text/select_range_on_line) to jump to and
    highlight the corresponding source location.
    """

    def __init__(self, xml_editor, parent=None):
        super().__init__(parent)
        self._xml_editor = xml_editor
        self._current_rows: list[RowSpec] = []

        self._header_label = QLabel("")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self._on_row_clicked)

        self._populated_page = QWidget()
        populated_layout = QVBoxLayout(self._populated_page)
        populated_layout.setContentsMargins(0, 0, 0, 0)
        populated_layout.addWidget(self._header_label)
        populated_layout.addWidget(self.table)

        self._empty_label = QLabel(_EMPTY_STATE_MESSAGE)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._empty_label)
        self._stack.addWidget(self._populated_page)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self._stack)

        self._show_empty_state()

    def is_showing_empty_state(self) -> bool:
        return self._stack.currentWidget() is self._empty_label

    def header_text(self) -> str:
        return self._header_label.text()

    def show_node(self, node, kind: str | None) -> None:
        if node is None or kind is None:
            self._show_empty_state()
            return
        rows_fn, header_fn = _ROW_BUILDERS[kind]
        self._current_rows = rows_fn(node)
        self._populate_table(header_fn(node), self._current_rows)

    def _show_empty_state(self) -> None:
        self._current_rows = []
        self._stack.setCurrentWidget(self._empty_label)

    def _populate_table(self, header_text: str, rows: list[RowSpec]) -> None:
        self._header_label.setText(header_text)
        self.table.setRowCount(len(rows))
        for row_index, row_spec in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(row_spec.property_label))
            self.table.setItem(row_index, 1, QTableWidgetItem(row_spec.value))
        self._stack.setCurrentWidget(self._populated_page)

    def _on_row_clicked(self, row: int, _column: int) -> None:
        spec = self._current_rows[row]
        if spec.target_line is None:
            return
        self._xml_editor.navigate_to_line(spec.target_line)
        if spec.attr_name is not None:
            self._select_attribute_on_line(spec.target_line, spec.attr_name)

    def _select_attribute_on_line(self, line: int, attr_name: str) -> None:
        line_text = self._xml_editor.line_text(line)
        needle = f'{attr_name}="'
        start = line_text.find(needle)
        if start == -1:
            return
        value_start = start + len(needle)
        end = line_text.find('"', value_start)
        if end == -1:
            return
        self._xml_editor.select_range_on_line(line, start, end + 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_properties_panel.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/properties_panel.py tests/ui/test_properties_panel.py
git commit -m "feat: add PropertiesPanel widget with per-kind population and empty state"
```

---

## Task 8: Click-to-navigate wiring against the recording stub

**Files:**
- Modify: `tests/ui/test_properties_panel.py` (add click-behavior tests; no production code changes — `_on_row_clicked`/`_select_attribute_on_line` were already written in Task 7)

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_properties_panel.py`:

```python
def test_click_page_row_navigates_to_sourceline(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    panel._on_row_clicked(0, 0)
    assert stub.navigate_calls == [5]


def test_click_detail_caption_row_uses_outer_sourceline(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_detail_node(), "detail")
    # Row 0 is "caption" per attrib dict insertion order.
    assert panel._current_rows[0].property_label == "caption"
    panel._on_row_clicked(0, 0)
    assert stub.navigate_calls == [10]


def test_click_detail_non_caption_row_uses_inner_sourceline(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_detail_node(), "detail")
    # Row 1 is "tableName" per attrib dict insertion order.
    assert panel._current_rows[1].property_label == "tableName"
    panel._on_row_clicked(1, 0)
    assert stub.navigate_calls == [25]


def test_click_attribute_row_selects_attribute_span(qtbot):
    stub = _RecordingXmlEditorStub(
        line_text_by_line={5: '  <Page fileName="development_equipment" tableName="pr.equipment">'}
    )
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    panel._on_row_clicked(0, 0)  # "fileName" row
    assert stub.navigate_calls == [5]
    assert stub.line_text_calls == [5]
    line_text = '  <Page fileName="development_equipment" tableName="pr.equipment">'
    expected_start = line_text.find('fileName="')
    expected_end = line_text.find('"', expected_start + len('fileName="')) + 1
    assert stub.select_range_calls == [(5, expected_start, expected_end)]


def test_click_attribute_row_refinement_failure_falls_back_gracefully(qtbot):
    # line_text does not contain 'fileName="' at all.
    stub = _RecordingXmlEditorStub(line_text_by_line={5: "  <Page />"})
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    panel._on_row_clicked(0, 0)
    assert stub.navigate_calls == [5]
    assert stub.line_text_calls == [5]
    assert stub.select_range_calls == []  # graceful fallback, never a crash


def test_click_event_functions_row_navigates_but_never_refines(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_event_node(), "event")
    functions_row_index = next(
        i for i, r in enumerate(panel._current_rows) if r.property_label == "Functions"
    )
    panel._on_row_clicked(functions_row_index, 0)
    assert stub.navigate_calls == [7]
    assert stub.line_text_calls == []
    assert stub.select_range_calls == []


def test_click_detail_row_with_none_target_line_does_not_crash(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    detail = DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment"},
        sourceline=10,
        inner_sourceline=None,
    )
    panel.show_node(detail, "detail")
    table_name_row_index = next(
        i for i, r in enumerate(panel._current_rows) if r.property_label == "tableName"
    )
    panel._on_row_clicked(table_name_row_index, 0)  # target_line is None
    assert stub.navigate_calls == []  # never called; nothing to navigate to
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `python -m pytest tests/ui/test_properties_panel.py -v -k "click"`
Expected: Since `_on_row_clicked`/`_select_attribute_on_line` were already implemented in Task 7, these should **already PASS** on the first run — this step is a verification pass, not a red/green cycle. If any fail, fix `_on_row_clicked`/`_select_attribute_on_line` in `pgtp_editor/ui/properties_panel.py` (defined in Task 7) to match, then re-run.

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/ui/test_properties_panel.py
git commit -m "test: add click-to-navigate coverage for PropertiesPanel against a recording stub"
```

---

## Task 9: Wire `PropertiesPanel` into `MainWindow`

**Files:**
- Modify: `pgtp_editor/ui/main_window.py:36-71` (`MainWindow.__init__`)
- Test: `tests/ui/test_main_window.py`

**Note on the not-yet-merged `XmlEditor`:** `CenterStage` has no `xml_editor` attribute today (confirmed in the "Current-state facts" section above — its Raw XML tab is a bare placeholder `QWidget()`). This task therefore constructs `PropertiesPanel` with a small private no-op stand-in object defined directly in `main_window.py`, `_NullXmlEditor`, so `MainWindow` does not reference `self.center_stage.xml_editor` before it exists. This is marked with a `# TODO` comment pointing at the real wiring to do once the XML Editor Foundation sub-project is merged: replace `_NullXmlEditor()` with `self.center_stage.xml_editor`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_main_window.py`:

```python
from pgtp_editor.ui.properties_panel import PropertiesPanel


def test_properties_panel_is_a_real_properties_panel(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert isinstance(window.properties_panel, PropertiesPanel)
    assert window.properties_dock.widget() is window.properties_panel


def test_selecting_tree_item_populates_properties_panel(qtbot):
    from tests.ui._sample_project import build_sample_project

    window = MainWindow()
    qtbot.addWidget(window)
    window.project_tree.populate_from_project(build_sample_project())

    page_item = window.project_tree.topLevelItem(0)
    window.project_tree.setCurrentItem(page_item)

    assert window.properties_panel.is_showing_empty_state() is False
    assert window.properties_panel.header_text().startswith("Page:")


def test_clearing_tree_selection_returns_properties_panel_to_empty_state(qtbot):
    from tests.ui._sample_project import build_sample_project

    window = MainWindow()
    qtbot.addWidget(window)
    window.project_tree.populate_from_project(build_sample_project())
    window.project_tree.setCurrentItem(window.project_tree.topLevelItem(0))
    window.project_tree.setCurrentItem(None)

    assert window.properties_panel.is_showing_empty_state() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "properties_panel"`
Expected: FAIL — `AssertionError` (since `window.properties_panel` is currently a bare `QWidget()`, not a `PropertiesPanel`, and there is no selection wiring)

- [ ] **Step 3: Wire `PropertiesPanel` into `MainWindow`**

In `pgtp_editor/ui/main_window.py`, add the import:

```python
from pgtp_editor.ui.properties_panel import PropertiesPanel
```

Then replace the relevant section of `MainWindow.__init__` (currently lines 43-66, from `self.project_tree = ProjectTreePanel(...)` through `self.setCentralWidget(self.center_stage)`):

```python
        self.project_tree = ProjectTreePanel(
            on_stub_action=self._not_implemented,
            on_compare_page=self._compare_page_with,
            on_compare_detail=self._compare_detail_with,
            on_selection_changed=self._on_tree_selection_changed,
        )
        self.tree_dock = QDockWidget("Project Tree", self)
        self.tree_dock.setObjectName("tree_dock")
        self.tree_dock.setWidget(self.project_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_dock)

        self.audit_panel = QListWidget()
        self.audit_dock = QDockWidget("Audit / Problems", self)
        self.audit_dock.setObjectName("audit_dock")
        self.audit_dock.setWidget(self.audit_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.audit_dock)

        # TODO(xml-editor-foundation): once the XML Editor Foundation
        # sub-project is merged and CenterStage exposes a real
        # `xml_editor` attribute (an XmlEditor with navigate_to_line/
        # line_text/select_range_on_line), replace `_NullXmlEditor()`
        # below with `self.center_stage.xml_editor`. CenterStage must
        # then also be constructed before PropertiesPanel, same as today.
        self.properties_panel = PropertiesPanel(xml_editor=_NullXmlEditor())
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_dock.setObjectName("properties_dock")
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        self.center_stage = CenterStage()
        self.setCentralWidget(self.center_stage)
```

Add the `_NullXmlEditor` stand-in class near the top of `main_window.py` (after the imports, before `_SCHEMA_REPORT_TEMPLATES`):

```python
class _NullXmlEditor:
    """No-op stand-in for the not-yet-merged XmlEditor widget. Satisfies
    the navigate_to_line/line_text/select_range_on_line interface
    PropertiesPanel depends on, without doing anything, until the XML
    Editor Foundation sub-project is merged and CenterStage.xml_editor
    is real (see the TODO in MainWindow.__init__)."""

    def navigate_to_line(self, line: int) -> None:
        pass

    def line_text(self, line: int) -> str:
        return ""

    def select_range_on_line(self, line: int, start: int, end: int) -> None:
        pass
```

Finally, add the new handler method next to `_not_implemented`:

```python
    def _on_tree_selection_changed(self, node, kind):
        self.properties_panel.show_node(node, kind)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_main_window.py -v`
Expected: all tests pass, including the 3 new ones.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat: wire PropertiesPanel into MainWindow via tree selection"
```

---

## Blocked work (explicitly deferred, not part of this plan's remaining tasks)

Per the design spec §4.3, the following cannot be completed until the sibling XML Editor Foundation sub-project is merged into this worktree's lineage:

1. Adding `navigate_to_line(line)`, `line_text(line)`, and `select_range_on_line(line, start, end)` to the real `XmlEditor` class (and reimplementing `highlight_error_line` in terms of `navigate_to_line`) — this is a change to the *other* sub-project's code, not this one's, and must happen there.
2. Replacing `_NullXmlEditor()` in `MainWindow.__init__` (Task 9) with `self.center_stage.xml_editor`, once that attribute exists.
3. A true end-to-end integration test: load a real sample `.pgtp` file, select a Detail node in the tree, click its `tableName` row, and assert the real `XmlEditor`'s cursor position and text selection — not achievable against `_RecordingXmlEditorStub`/`_NullXmlEditor`, since neither has real document/cursor state to assert against.

These three items should be scheduled as a short follow-up task once the XML Editor Foundation sub-project merges; this plan intentionally does not fabricate a stand-in test claiming to verify them.
