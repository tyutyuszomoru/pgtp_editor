# PGTP Editor — Editor↔Tree Sync (Reveal in Tree) + Reparse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clicking anywhere in the raw XML editor selects the nearest enclosing tree node (which repopulates Properties through existing wiring), and a `Tools → "Reparse Raw XML into Tree"` action rebuilds the tree/model from the editor's current text — surfacing parse errors while preserving the last-good state on failure.

**Architecture:** A new Qt-free `pgtp_editor/model/line_index.py` provides `node_at_line(project, line)`, resolving a 1-based source line to the deepest enclosing `PageNode`/`DetailNode`/`ColumnNode`/`EventNode` via a document-order flat walk with per-node line ranges. `pgtp_editor/model/parser.py` gains a `load_project_from_text(text, source_description)` sibling of `load_project` that parses in-memory editor text through the shared `_build_project_model`. `pgtp_editor/ui/xml_editor.py` gains a `line_clicked = Signal(int)` emitted from a small `mouseReleaseEvent` override. `pgtp_editor/ui/project_tree.py` gains an `id(node) → QTreeWidgetItem` index built during `populate_from_project` and a `select_node(node)` method. `pgtp_editor/ui/main_window.py` connects `line_clicked` → `node_at_line` → `select_node`, and adds the Reparse action.

**Tech Stack:** Python 3.13, PySide6 (Qt widgets), lxml (existing parser dependency), pytest, pytest-qt.

---

## Current-state facts confirmed by reading this worktree's code (do not re-derive these — just use them)

- `pgtp_editor/model/nodes.py`: `PageNode` has `identity`, `attrib`, `sourceline: int | None = None`, `element`, `details`, `columns`, `events`. `DetailNode` has all of those plus `inner_page_element`, `inner_sourceline: int | None = None`. `ColumnNode` has `identity`, `attrib`, `sourceline`, `element`. `EventNode` has `identity`, `tag_name`, `side`, `text`, `sourceline`, `element`. `ProjectModel` has `pages: list[PageNode]` and `tree`. Nested Details live under a Detail's own `details` list (recursive); a Page's own children are `details`, `columns`, `events`.
- `pgtp_editor/model/parser.py`: `load_project(path)` reads bytes via `read_pgtp_bytes(path)`, `etree.parse(io.BytesIO(data))`, catches `(etree.XMLSyntaxError, OSError)` and raises `PgtpParseError(f"Could not parse '{path}': {exc}", line=<lineno or None>)`, then calls `_build_project_model(tree, source_description=str(path))`. `_build_project_model(tree, source_description)` walks `root.find("Presentation/Pages")` and raises `PgtpParseError(...)` (with `line=None`) on any structural surprise; a well-formed doc with no `Presentation/Pages` yields `ProjectModel(pages=[], tree=tree)`. `PgtpParseError(message, line=None)` carries `.line`. `import io` and `from lxml import etree` are already at the top of the file.
- `pgtp_editor/ui/xml_editor.py`: `XmlEditor(QPlainTextEdit)`. Its imports line is `from PySide6.QtCore import QPoint, QRect, QSize, Qt` (no `Signal` yet). `__init__(self, parent=None)` connects Qt signals (`blockCountChanged`, `updateRequest`, `textChanged`, `cursorPositionChanged`) and installs two `QShortcut`s (`Ctrl+Shift+B` → `select_enclosing_block`, `Ctrl+Shift+A` → `select_parent_block`). **There is NO `mouseReleaseEvent` override today** — the only mouse handler in the file is `_EditorGutter.mousePressEvent` (a different widget). `keyPressEvent` is overridden. It exposes `navigate_to_line`, `highlight_error_line`, `line_text`, `select_range_on_line`, `select_enclosing_block`, `select_parent_block`, `set_line_wrap_enabled`. There is no class-level attribute block; `line_clicked` will be the first class-level declaration, placed immediately after `class XmlEditor(QPlainTextEdit):` and before `def __init__`.
- `pgtp_editor/ui/project_tree.py`: `ProjectTreePanel(QTreeWidget)`. `populate_from_project(project)` calls `self.clear()`, then for each page builds a `QTreeWidgetItem`, `setData(0, MODEL_NODE_ROLE, page)`, `addTopLevelItem`, and `self._populate_details_and_events(page_item, page)`. `_populate_details_and_events(parent_item, node)` builds Detail items (recursing), Column items, Event items — **all three already call `setData(0, MODEL_NODE_ROLE, <node>)` today** (the Properties sub-project added Column/Event coverage). `currentItemChanged` is wired to `_on_current_item_changed`, which reads `MODEL_NODE_ROLE`/`NODE_KIND_ROLE` and calls `self._on_selection_changed(node, kind)`. `MODEL_NODE_ROLE = Qt.ItemDataRole.UserRole + 2`. `setCurrentItem(item)` therefore fires the existing tree→Properties path.
- `pgtp_editor/ui/main_window.py`: `MainWindow.__init__` builds `self.project_tree = ProjectTreePanel(..., on_selection_changed=self._on_tree_selection_changed)`, then `self.center_stage = CenterStage()`, then `self.properties_panel = PropertiesPanel(xml_editor=self.center_stage.xml_editor)`. So **`self.center_stage.xml_editor` is real and already referenced** in `__init__` (the XML Editor Foundation and Properties sub-projects are both merged here). `self._current_project = None` and `self._current_project_path = None` are set near the end of `__init__`, followed by `self._build_menu_bar()`. `_on_tree_selection_changed(node, kind)` calls `self.properties_panel.show_node(node, kind)`. `open_project_file(path)` sets `_current_project`/`_current_project_path` and calls `populate_from_project`. `_handle_parse_failure(path, exc)` shows `QMessageBox.critical`, populates the raw fallback view from a file re-read, and (if `exc.line`) calls `highlight_error_line` — this is the pattern to **mirror but NOT copy wholesale** (reparse must preserve the model/tree and must NOT re-read a file). `_build_tools_menu` currently ends with `self._add_stub_action(menu, "Validate Project")`. `_add_stub_action(menu, label)` wraps `add_stub_action(menu, label, self._not_implemented)`. `QMessageBox` and `load_project`, `PgtpParseError`, `_build_project_model` are already imported at the top (`from pgtp_editor.model.parser import PgtpParseError, _build_project_model, load_project`).
- `tests/ui/test_menus.py`: `test_tools_menu_contents` asserts the Tools menu labels are exactly `["Manage Captions...", "―", "Find Reused Tables...", "―", "Validate Project"]`. Adding the Reparse action changes this — Task 6 updates it. `action_labels`/`find_top_menu`/`find_action` come from `tests/ui/_menu_helpers.py`; separators render as `"―"`.
- Test conventions: `tests/model/test_parser.py` defines `write_pgtp(tmp_path, xml_text, name="test.pgtp")` and a module-level `SIMPLE_PROJECT` XML string (a `Project/Presentation/Pages` with two Pages, the first having Columns/Events/one nested Detail). `tests/ui/` uses `qtbot` (pytest-qt), `qtbot.addWidget(...)`, and `tests/ui/_sample_project.py`'s `build_sample_project()` for synthetic `ProjectModel`s — but **every node in `build_sample_project()` has `sourceline=1`**, so it is useless for `node_at_line`/click tests; those tasks build bespoke models with distinct sourcelines. `tests/model/test_parser_real_samples.py` guards real-sample tests with `_require_sample`/`pytest.skip`.

---

## File structure

- **Create** `pgtp_editor/model/line_index.py` — Qt-free, lxml-free `node_at_line(project, line)` plus its private `_Entry`/`_flatten`/`_assign_end_lines` helpers. One responsibility: turn a 1-based line into the deepest enclosing model node.
- **Create** `tests/model/test_line_index.py` — Qt-free unit tests for `node_at_line`.
- **Modify** `pgtp_editor/model/parser.py` — add `load_project_from_text(text, source_description="<editor>")`.
- **Modify** `tests/model/test_parser.py` — add `load_project_from_text` unit tests (append; reuse `write_pgtp`/`SIMPLE_PROJECT`).
- **Modify** `pgtp_editor/ui/project_tree.py` — add the `id(node) → item` index in `populate_from_project`/`_populate_details_and_events` and a `select_node(node)` method.
- **Modify** `tests/ui/test_project_tree.py` — add `select_node` tests.
- **Modify** `pgtp_editor/ui/xml_editor.py` — add `line_clicked = Signal(int)`, import `Signal`, add `mouseReleaseEvent` override.
- **Modify** `tests/ui/test_xml_editor.py` — add `line_clicked` emission test.
- **Modify** `pgtp_editor/ui/main_window.py` — connect `line_clicked`, add `_on_editor_line_clicked`; add the Reparse action and `_reparse_raw_xml`/`_handle_reparse_failure`.
- **Modify** `tests/ui/test_main_window.py` — add click-sync and Reparse tests.
- **Modify** `tests/ui/test_menus.py` — update `test_tools_menu_contents` for the new Reparse entry.

**Build order (dependency-respecting):** Task 1 `node_at_line` (Qt-free) → Task 2 `load_project_from_text` (Qt-free) → Task 3 `select_node` + index → Task 4 `line_clicked` + `mouseReleaseEvent` → Task 5 MainWindow click wiring → Task 6 Reparse action + menu-test update → Task 7 full-suite verification.

---

## Task 1: `node_at_line` — the source-line-range index (Qt-free)

**Files:**
- Create: `pgtp_editor/model/line_index.py`
- Test: `tests/model/test_line_index.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/model/test_line_index.py`:

```python
from pgtp_editor.model.line_index import node_at_line
from pgtp_editor.model.nodes import (
    ColumnNode,
    DetailNode,
    EventNode,
    PageNode,
    ProjectModel,
)


def _nested_depth_project():
    """Page (line 5) > Detail (line 10, inner Page line 11)
    > nested Detail (line 15, inner Page line 16) > Column (line 18).
    The next node after the Column is the second top-level Page at line 30.
    """
    column = ColumnNode(identity="c", attrib={"fieldName": "c"}, sourceline=18)
    nested_detail = DetailNode(
        identity="d/nd",
        attrib={"tableName": "nd"},
        sourceline=15,
        inner_sourceline=16,
        columns=[column],
    )
    outer_detail = DetailNode(
        identity="d",
        attrib={"tableName": "d"},
        sourceline=10,
        inner_sourceline=11,
        details=[nested_detail],
    )
    page = PageNode(
        identity="p",
        attrib={"tableName": "p"},
        sourceline=5,
        details=[outer_detail],
    )
    second_page = PageNode(identity="p2", attrib={"tableName": "p2"}, sourceline=30)
    return ProjectModel(pages=[page, second_page]), page, outer_detail, nested_detail, column


def test_click_on_page_open_line_returns_page():
    project, page, _outer, _nested, _column = _nested_depth_project()
    assert node_at_line(project, 5) is page


def test_click_in_outer_detail_whitespace_returns_outer_detail():
    project, _page, outer, _nested, _column = _nested_depth_project()
    # Line 12: inside the outer Detail (open line 10, inner Page line 11)
    # but before the nested Detail (line 15) — resolves to the outer Detail.
    assert node_at_line(project, 12) is outer


def test_click_on_nested_detail_line_returns_nested_detail():
    project, _page, _outer, nested, _column = _nested_depth_project()
    assert node_at_line(project, 16) is nested


def test_click_on_column_line_returns_column():
    project, _page, _outer, _nested, column = _nested_depth_project()
    assert node_at_line(project, 18) is column


def test_click_inside_column_subelement_returns_column():
    """A Column at line 20 with the next node (a sibling Column) at line 30.
    Lines 21-29 are the Column's <Format>/<Lookup> body — no node of their
    own — and all resolve to the Column."""
    first_col = ColumnNode(identity="c1", attrib={"fieldName": "c1"}, sourceline=20)
    second_col = ColumnNode(identity="c2", attrib={"fieldName": "c2"}, sourceline=30)
    page = PageNode(
        identity="p", attrib={"tableName": "p"}, sourceline=5, columns=[first_col, second_col]
    )
    project = ProjectModel(pages=[page])
    for line in range(21, 30):
        assert node_at_line(project, line) is first_col, f"line {line}"


def test_click_in_detail_whitespace_before_first_column_returns_detail():
    """A Detail at line 10 whose first child Column starts at line 14.
    Lines 11-13 (whitespace / <ColumnPresentations> open before any Column
    node) resolve to the Detail, not to any Column."""
    column = ColumnNode(identity="c", attrib={"fieldName": "c"}, sourceline=14)
    detail = DetailNode(
        identity="d", attrib={"tableName": "d"}, sourceline=10, inner_sourceline=11, columns=[column]
    )
    page = PageNode(identity="p", attrib={"tableName": "p"}, sourceline=5, details=[detail])
    project = ProjectModel(pages=[page])
    for line in (11, 12, 13):
        assert node_at_line(project, line) is detail, f"line {line}"
    assert node_at_line(project, 14) is column


def test_line_above_first_page_returns_none():
    page = PageNode(identity="p", attrib={"tableName": "p"}, sourceline=5)
    project = ProjectModel(pages=[page])
    for line in (1, 2, 3, 4):
        assert node_at_line(project, line) is None, f"line {line}"


def test_duplicate_table_details_disambiguated_by_line_identity():
    """Two Details with the same tableName at different document positions.
    node_at_line returns the specific instance whose range contains the line,
    verified by object identity (`is`), not table name."""
    first = DetailNode(identity="d1", attrib={"tableName": "dup"}, sourceline=10, inner_sourceline=11)
    second = DetailNode(identity="d2", attrib={"tableName": "dup"}, sourceline=40, inner_sourceline=41)
    page = PageNode(
        identity="p", attrib={"tableName": "p"}, sourceline=5, details=[first, second]
    )
    project = ProjectModel(pages=[page])
    assert node_at_line(project, 12) is first
    assert node_at_line(project, 42) is second


def test_node_with_none_sourceline_is_dropped():
    good = ColumnNode(identity="good", attrib={"fieldName": "good"}, sourceline=10)
    bad = ColumnNode(identity="bad", attrib={"fieldName": "bad"}, sourceline=None)
    page = PageNode(identity="p", attrib={"tableName": "p"}, sourceline=5, columns=[bad, good])
    project = ProjectModel(pages=[page])
    # The None-sourceline column is never returned; line 10 resolves to `good`.
    assert node_at_line(project, 10) is good
    result = node_at_line(project, 999)
    assert result is not bad


def test_project_none_returns_none():
    assert node_at_line(None, 5) is None


def test_empty_project_returns_none():
    assert node_at_line(ProjectModel(pages=[]), 5) is None


def test_event_node_resolved_at_its_line():
    event = EventNode(identity="e", tag_name="OnRowProcess", side="C", text="", sourceline=8)
    page = PageNode(identity="p", attrib={"tableName": "p"}, sourceline=5, events=[event])
    project = ProjectModel(pages=[page])
    assert node_at_line(project, 8) is event
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/model/test_line_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.model.line_index'`

- [ ] **Step 3: Create `line_index.py`**

Create `pgtp_editor/model/line_index.py`:

```python
# pgtp_editor/model/line_index.py
"""Resolve a 1-based source line number to the nearest enclosing model node.

Pure and Qt-free: operates only on the ProjectModel dataclasses in
pgtp_editor.model.nodes. Used by the editor->tree click-sync (MainWindow)
to turn an editor click position into the tree node to select.
"""
from __future__ import annotations

from dataclasses import dataclass

from pgtp_editor.model.nodes import ProjectModel


@dataclass
class _Entry:
    node: object          # PageNode | DetailNode | ColumnNode | EventNode
    depth: int
    start: int            # 1-based start line (node.sourceline)
    end: int | None       # 1-based inclusive end line; filled in a second pass


def _flatten(project: ProjectModel) -> list[_Entry]:
    """Walk the model in document order, emitting one _Entry per node with
    its depth and start line. Order within a container matches the tree's
    own display/emit order (nested Details, then Columns, then Events) — but
    correctness depends only on start lines being monotonic in document order,
    which they are because the parser reads them straight off lxml's
    document-order .sourceline. A Detail's range starts at its OUTER
    sourceline (the <Detail> open tag), never inner_sourceline."""
    entries: list[_Entry] = []

    def visit_container(node, depth: int) -> None:
        # A Page or Detail: its own children are details, columns, events.
        for detail in getattr(node, "details", []):
            entries.append(_Entry(detail, depth + 1, detail.sourceline, None))
            visit_container(detail, depth + 1)
        for column in getattr(node, "columns", []):
            entries.append(_Entry(column, depth + 1, column.sourceline, None))
        for event in getattr(node, "events", []):
            entries.append(_Entry(event, depth + 1, event.sourceline, None))

    for page in project.pages:
        entries.append(_Entry(page, 0, page.sourceline, None))
        visit_container(page, 0)

    # Drop any node whose start line is unknown (sourceline is None) — it
    # cannot participate in a line-range lookup. In practice sourceline is
    # always populated by the parser off a real lxml element.
    entries = [e for e in entries if e.start is not None]
    # Sort strictly by document position (start line). Ties should not occur
    # for distinct elements (each element opens on its own line in real
    # .pgtp files); a stable sort preserves emit order if they ever did.
    entries.sort(key=lambda e: e.start)
    return entries


def _assign_end_lines(entries: list[_Entry], total_lines: int | None = None) -> None:
    """Each entry's end line is one before the start of the next entry (in
    document order) at the SAME OR SHALLOWER depth — i.e. the next entry that
    is not a descendant of this one. The last such node runs to the end of
    the document (or, when unknown, to a large sentinel)."""
    n = len(entries)
    for i, entry in enumerate(entries):
        end = None
        for j in range(i + 1, n):
            if entries[j].depth <= entry.depth:
                end = entries[j].start - 1
                break
        if end is None:
            end = total_lines if total_lines is not None else 10**9
        entry.end = end


def node_at_line(project, line: int):
    """Return the deepest node whose [start, end] line range contains `line`,
    or None if `line` falls above the first node / outside any node's range
    (e.g. the file header or DataSources area the model does not cover)."""
    if project is None:
        return None
    entries = _flatten(project)
    _assign_end_lines(entries)
    # Deepest-first: among all entries whose range contains `line`, return the
    # one with the greatest depth. Because ranges of deeper nodes are nested
    # strictly inside their ancestors', the deepest containing entry is the
    # nearest enclosing node.
    best = None
    for entry in entries:
        if entry.start <= line <= entry.end:
            if best is None or entry.depth > best.depth:
                best = entry
    return best.node if best is not None else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/model/test_line_index.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/model/line_index.py tests/model/test_line_index.py
git commit -m "feat: add node_at_line source-line-range index"
```

---

## Task 2: `load_project_from_text` — reparse in-memory editor text (Qt-free)

**Files:**
- Modify: `pgtp_editor/model/parser.py` (add `load_project_from_text` after `load_project`)
- Test: `tests/model/test_parser.py` (append; reuse existing `write_pgtp`/`SIMPLE_PROJECT`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/model/test_parser.py` (the file already imports `PgtpParseError`, `load_project` and defines `write_pgtp`/`SIMPLE_PROJECT` at module level — add `load_project_from_text` to the existing parser import and reuse the rest):

```python
import textwrap  # already imported at top of file — do not duplicate


def test_load_project_from_text_valid_returns_model():
    from pgtp_editor.model.parser import load_project_from_text

    project = load_project_from_text(textwrap.dedent(SIMPLE_PROJECT))
    assert len(project.pages) == 2
    first = project.pages[0]
    assert first.file_name == "development_equipment"
    assert [c.field_name for c in first.columns] == ["tag", "description"]
    assert [e.tag_name for e in first.events] == ["OnPreparePage", "OnRowProcess"]
    # sourceline is populated off the in-memory parse, exactly like load_project.
    assert first.sourceline is not None


def test_load_project_from_text_malformed_raises_with_line():
    from pgtp_editor.model.parser import load_project_from_text

    bad = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="UTF-8"?>
        <Project>
          <Presentation>
            <Pages>
              <Page fileName="x" tableName="t" caption="X">
            </Pages>
          </Presentation>
        </Project>
        """
    )
    with pytest.raises(PgtpParseError) as excinfo:
        load_project_from_text(bad)
    assert excinfo.value.line is not None
    assert isinstance(excinfo.value.line, int)


def test_load_project_from_text_wellformed_but_no_pages_yields_empty_model():
    from pgtp_editor.model.parser import load_project_from_text

    text = "<Project><Other/></Project>"
    project = load_project_from_text(text)
    assert project.pages == []


def test_load_project_from_text_parity_with_load_project(tmp_path):
    from pgtp_editor.model.parser import load_project_from_text

    path = write_pgtp(tmp_path, SIMPLE_PROJECT)
    from_file = load_project(path)
    from_text = load_project_from_text(path.read_text(encoding="utf-8"))
    assert len(from_file.pages) == len(from_text.pages)
    assert [p.file_name for p in from_file.pages] == [p.file_name for p in from_text.pages]
    assert (
        [c.field_name for c in from_file.pages[0].columns]
        == [c.field_name for c in from_text.pages[0].columns]
    )


def test_load_project_from_text_source_description_in_error_message():
    from pgtp_editor.model.parser import load_project_from_text

    with pytest.raises(PgtpParseError) as excinfo:
        load_project_from_text("<Project><unclosed></Project>", source_description="<my-editor>")
    assert "<my-editor>" in str(excinfo.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/model/test_parser.py -v -k "from_text"`
Expected: FAIL — `ImportError: cannot import name 'load_project_from_text' from 'pgtp_editor.model.parser'`

- [ ] **Step 3: Add `load_project_from_text`**

In `pgtp_editor/model/parser.py`, add this function immediately after `load_project` (before `_build_project_model`). `io` and `etree` are already imported at the top of the file:

```python
def load_project_from_text(text: str, source_description: str = "<editor>") -> ProjectModel:
    """Parse an in-memory .pgtp document `text` into a ProjectModel.

    The in-memory sibling of `load_project`: used by the Reparse action to
    feed the raw-XML editor's current contents back into the model without
    round-tripping through a file on disk. Shares `_build_project_model` and
    the same PgtpParseError/line-number handling as `load_project`.

    The text is already a Python str held in the editor, so CESU-8 repair
    (which operates on raw bytes off disk) does not apply — any astral-plane
    characters are already proper Python characters. Encode to UTF-8 bytes so
    lxml parses from a byte stream exactly as `load_project` does.
    """
    try:
        tree = etree.parse(io.BytesIO(text.encode("utf-8")))
    except etree.XMLSyntaxError as exc:
        raise PgtpParseError(
            f"Could not parse {source_description}: {exc}", line=exc.lineno
        ) from exc
    return _build_project_model(tree, source_description=source_description)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/model/test_parser.py -v -k "from_text"`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/model/parser.py tests/model/test_parser.py
git commit -m "feat: add load_project_from_text for in-memory reparse"
```

---

## Task 3: `ProjectTreePanel.select_node` + `id(node) → item` index

**Files:**
- Modify: `pgtp_editor/ui/project_tree.py` (`populate_from_project`, `_populate_details_and_events`, add `select_node`)
- Test: `tests/ui/test_project_tree.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_project_tree.py`. Use the existing imports already at the top of that file (`from pgtp_editor.ui.project_tree import ProjectTreePanel, MODEL_NODE_ROLE`) and the `build_sample_project` helper it already imports from `tests.ui._sample_project`; if either import is not already present, add `from pgtp_editor.ui.project_tree import ProjectTreePanel` and `from tests.ui._sample_project import build_sample_project`:

```python
def test_select_node_selects_the_backing_item_and_returns_true(qtbot):
    project = build_sample_project()
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(project)

    page_node = project.pages[0]
    assert tree.select_node(page_node) is True
    current = tree.currentItem()
    assert current is not None
    assert current.data(0, MODEL_NODE_ROLE) is page_node


def test_select_node_selects_a_deep_column_node(qtbot):
    project = build_sample_project()
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(project)

    # Equipment page -> first Detail ("Sub-item") -> first Column ("tag").
    column_node = project.pages[0].details[0].columns[0]
    assert tree.select_node(column_node) is True
    assert tree.currentItem().data(0, MODEL_NODE_ROLE) is column_node


def test_select_node_fires_selection_changed_to_properties(qtbot):
    calls = []
    project = build_sample_project()
    tree = ProjectTreePanel(on_selection_changed=lambda node, kind: calls.append((node, kind)))
    qtbot.addWidget(tree)
    tree.populate_from_project(project)

    detail_node = project.pages[0].details[0]
    tree.select_node(detail_node)
    assert calls[-1][0] is detail_node
    assert calls[-1][1] == "detail"


def test_select_node_none_returns_false_and_changes_nothing(qtbot):
    project = build_sample_project()
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(project)
    tree.setCurrentItem(tree.topLevelItem(0))
    before = tree.currentItem()

    assert tree.select_node(None) is False
    assert tree.currentItem() is before


def test_select_node_foreign_node_returns_false_and_changes_nothing(qtbot):
    project = build_sample_project()
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    tree.populate_from_project(project)
    tree.setCurrentItem(tree.topLevelItem(0))
    before = tree.currentItem()

    # A node object never inserted into this tree (from a different model).
    foreign = build_sample_project().pages[0]
    assert tree.select_node(foreign) is False
    assert tree.currentItem() is before


def test_index_is_rebuilt_on_repopulate(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)

    first_project = build_sample_project()
    tree.populate_from_project(first_project)
    stale_node = first_project.pages[0]

    second_project = build_sample_project()
    tree.populate_from_project(second_project)

    # The stale node from the first populate is no longer in the index.
    assert tree.select_node(stale_node) is False
    # The fresh node from the second populate is.
    assert tree.select_node(second_project.pages[0]) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_project_tree.py -v -k "select_node or index_is_rebuilt"`
Expected: FAIL — `AttributeError: 'ProjectTreePanel' object has no attribute 'select_node'`

- [ ] **Step 3: Add the index and `select_node`**

In `pgtp_editor/ui/project_tree.py`, modify `populate_from_project` to reset and populate the index (add the `self._item_by_node_id = {}` reset and the `self._item_by_node_id[id(page)] = page_item` line):

```python
    def populate_from_project(self, project):
        """Populate the tree from a parsed ProjectModel (see
        pgtp_editor.model.parser.load_project). Replaces any existing
        content — call this after a successful File -> Open.
        """
        self.clear()
        self._item_by_node_id = {}
        for page in project.pages:
            page_name = page.attrib.get("caption") or page.file_name or page.identity
            page_table = page.table_name or ""
            page_item = QTreeWidgetItem([f"(P) {page_name} [{page_table}]"])
            page_item.setData(0, NODE_KIND_ROLE, "page")
            page_item.setData(0, TABLE_NAME_ROLE, page_table)
            page_item.setData(0, MODEL_NODE_ROLE, page)
            self._item_by_node_id[id(page)] = page_item
            self.addTopLevelItem(page_item)
            self._populate_details_and_events(page_item, page)
```

Then modify `_populate_details_and_events` to add each Detail/Column/Event item to the index (add the three `self._item_by_node_id[id(...)] = ...` lines):

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
            self._item_by_node_id[id(detail)] = detail_item
            parent_item.addChild(detail_item)
            self._populate_details_and_events(detail_item, detail)
        for column in node.columns:
            column_item = QTreeWidgetItem([f"(C) {column.field_name}"])
            column_item.setData(0, NODE_KIND_ROLE, "column")
            column_item.setData(0, MODEL_NODE_ROLE, column)
            self._item_by_node_id[id(column)] = column_item
            parent_item.addChild(column_item)
        for event in node.events:
            event_item = QTreeWidgetItem([f"(E) {event.side}.{event.tag_name}"])
            event_item.setData(0, NODE_KIND_ROLE, "event")
            event_item.setData(0, MODEL_NODE_ROLE, event)
            self._item_by_node_id[id(event)] = event_item
            parent_item.addChild(event_item)
```

Then add the `select_node` method (place it after `_populate_details_and_events`, before `iter_detail_items`):

```python
    def select_node(self, node) -> bool:
        """Select the tree item backing `node`, if present. Returns True if a
        matching item was found and selected, False otherwise (e.g. node is
        None, or is from a stale/other model). Setting the current item fires
        the existing currentItemChanged -> _on_selection_changed -> Properties
        flow; no extra Properties wiring is needed here."""
        if node is None:
            return False
        item = getattr(self, "_item_by_node_id", {}).get(id(node))
        if item is None:
            return False
        self.setCurrentItem(item)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_project_tree.py -v -k "select_node or index_is_rebuilt"`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the whole project-tree test file (regression)**

Run: `python -m pytest tests/ui/test_project_tree.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/project_tree.py tests/ui/test_project_tree.py
git commit -m "feat: add ProjectTreePanel.select_node with id(node) index"
```

---

## Task 4: `XmlEditor.line_clicked` Signal + `mouseReleaseEvent`

**Files:**
- Modify: `pgtp_editor/ui/xml_editor.py` (import `Signal`, add class-level `line_clicked`, add `mouseReleaseEvent`)
- Test: `tests/ui/test_xml_editor.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_xml_editor.py` (add whatever of these imports the file does not already have at its top: `from PySide6.QtCore import QPoint, Qt`, `from PySide6.QtGui import QTextCursor`, `from PySide6.QtTest import QTest`, `from pgtp_editor.ui.xml_editor import XmlEditor`):

```python
def test_line_clicked_signal_exists():
    # Class-level Signal is present and typed for one int argument.
    assert hasattr(XmlEditor, "line_clicked")


def test_mouse_release_emits_one_based_line_from_cursor(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two\nline three\nline four")

    # Place the cursor on the 3rd block (0-based blockNumber 2) so the
    # override reads it after super() runs. We drive mouseReleaseEvent
    # directly with a synthetic position on that line's rect.
    block = editor.document().findBlockByNumber(2)
    cursor = QTextCursor(block)
    editor.setTextCursor(cursor)

    emitted = []
    editor.line_clicked.connect(emitted.append)

    rect = editor.cursorRect(editor.textCursor())
    pos = rect.center()
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)

    assert emitted, "line_clicked should have fired on a left mouse release"
    # Whatever line the click landed on, it must be reported 1-based and match
    # the post-click cursor's own block number + 1.
    assert emitted[-1] == editor.textCursor().blockNumber() + 1


def test_right_click_does_not_emit_line_clicked(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("line one\nline two")

    emitted = []
    editor.line_clicked.connect(emitted.append)

    rect = editor.cursorRect(editor.textCursor())
    QTest.mouseClick(
        editor.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, rect.center()
    )
    assert emitted == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k "line_clicked or mouse_release or right_click"`
Expected: FAIL — `AttributeError: type object 'XmlEditor' has no attribute 'line_clicked'`

- [ ] **Step 3: Add the `Signal` import, the class attribute, and `mouseReleaseEvent`**

In `pgtp_editor/ui/xml_editor.py`, change the `QtCore` import line to add `Signal`:

```python
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
```

Add the class-level `line_clicked` declaration as the first line inside `class XmlEditor(QPlainTextEdit):`, immediately before `def __init__`:

```python
class XmlEditor(QPlainTextEdit):
    line_clicked = Signal(int)  # 1-based line of a left-mouse click in the text

    def __init__(self, parent=None):
```

Add the `mouseReleaseEvent` override. Place it directly after `keyPressEvent` (i.e. after `keyPressEvent`'s final `super().keyPressEvent(event)` return, before `_character_before_cursor`) so it composes with, but does not disturb, the existing key/auto-close machinery:

```python
    def mouseReleaseEvent(self, event) -> None:
        # Let Qt place the text cursor at the clicked position first, then
        # read the resulting 1-based line and notify listeners. This is the
        # editor->tree click-sync entry point (see MainWindow). It only reads
        # the cursor; it does not alter selection, folding, or the
        # auto-close/auto-indent state.
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            line = self.textCursor().blockNumber() + 1  # 0-based -> 1-based
            self.line_clicked.emit(line)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_xml_editor.py -v -k "line_clicked or mouse_release or right_click"`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the whole xml-editor test file (regression — confirm no interference with D's block-selection / auto-close behavior)**

Run: `python -m pytest tests/ui/test_xml_editor.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/xml_editor.py tests/ui/test_xml_editor.py
git commit -m "feat: add XmlEditor.line_clicked signal on mouse release"
```

---

## Task 5: MainWindow click-sync wiring (editor click → tree select → Properties)

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (import `node_at_line`; connect `line_clicked`; add `_on_editor_line_clicked`)
- Test: `tests/ui/test_main_window.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_main_window.py`. These build a `MainWindow`, load a real parsed model (so `sourceline`s are genuine) from an inline `.pgtp` string via `load_project_from_text`, set it as `_current_project`, populate the tree, and drive `_on_editor_line_clicked` directly (positional mouse precision is covered by Task 4; here the mapping is under test):

```python
_CLICK_SYNC_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="equipment" tableName="pr.equipment" caption="Equipment">
        <ColumnPresentations>
          <ColumnPresentation fieldName="tag" caption="Tag"/>
        </ColumnPresentations>
        <Details>
          <Detail caption="Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item">
              <ColumnPresentations>
                <ColumnPresentation fieldName="cvalue" caption="Value"/>
              </ColumnPresentations>
            </Page>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def _load_click_sync_window(qtbot):
    import textwrap

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    project = load_project_from_text(textwrap.dedent(_CLICK_SYNC_PGTP))
    window._current_project = project
    window.project_tree.populate_from_project(project)
    return window, project


def test_editor_click_selects_enclosing_node_and_updates_properties(qtbot):
    window, project = _load_click_sync_window(qtbot)
    detail = project.pages[0].details[0]

    # A click on the outer <Detail> open line resolves to that Detail.
    window._on_editor_line_clicked(detail.sourceline)

    current = window.project_tree.currentItem()
    from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE

    assert current is not None
    assert current.data(0, MODEL_NODE_ROLE) is detail
    # Tree->Properties fired automatically through existing wiring.
    assert window.properties_panel.is_showing_empty_state() is False
    assert window.properties_panel.header_text().startswith("Detail:")


def test_editor_click_on_column_line_selects_column(qtbot):
    window, project = _load_click_sync_window(qtbot)
    column = project.pages[0].columns[0]
    window._on_editor_line_clicked(column.sourceline)

    from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE

    assert window.project_tree.currentItem().data(0, MODEL_NODE_ROLE) is column


def test_editor_click_above_first_page_is_noop(qtbot):
    window, project = _load_click_sync_window(qtbot)
    window.project_tree.setCurrentItem(window.project_tree.topLevelItem(0))
    before = window.project_tree.currentItem()

    window._on_editor_line_clicked(1)  # line 1 is the <?xml ...?> header
    assert window.project_tree.currentItem() is before


def test_editor_click_with_no_current_project_is_noop(qtbot):
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None
    # Must not raise even with no project loaded.
    window._on_editor_line_clicked(5)


def test_line_clicked_signal_is_connected_to_handler(qtbot):
    window, project = _load_click_sync_window(qtbot)
    detail = project.pages[0].details[0]
    # Emitting the editor's signal drives the same end-to-end selection.
    window.center_stage.xml_editor.line_clicked.emit(detail.sourceline)

    from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE

    assert window.project_tree.currentItem().data(0, MODEL_NODE_ROLE) is detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "editor_click or line_clicked_signal_is_connected"`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_on_editor_line_clicked'`

- [ ] **Step 3: Wire the signal and add the handler**

In `pgtp_editor/ui/main_window.py`, add the import of `node_at_line` near the existing parser import:

```python
from pgtp_editor.model.line_index import node_at_line
```

In `MainWindow.__init__`, connect the signal. Add this line after `self.center_stage = CenterStage()` (the `xml_editor` attribute already exists by then), e.g. immediately after `self.setCentralWidget(self.center_stage)`:

```python
        self.center_stage.xml_editor.line_clicked.connect(self._on_editor_line_clicked)
```

Add the handler method next to `_on_tree_selection_changed`:

```python
    def _on_editor_line_clicked(self, line: int) -> None:
        if self._current_project is None:
            return
        node = node_at_line(self._current_project, line)
        if node is None:
            return  # click above first page / uncovered region: no-op
        self.project_tree.select_node(node)  # fires tree -> Properties automatically
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_main_window.py -v -k "editor_click or line_clicked_signal_is_connected"`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the whole main-window test file (regression)**

Run: `python -m pytest tests/ui/test_main_window.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat: wire editor click-sync to tree selection in MainWindow"
```

---

## Task 6: Reparse action (`Tools → "Reparse Raw XML into Tree"`)

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (import `load_project_from_text`; add the menu action in `_build_tools_menu`; add `_reparse_raw_xml` and `_handle_reparse_failure`)
- Test: `tests/ui/test_main_window.py` (append)
- Test: `tests/ui/test_menus.py` (update `test_tools_menu_contents`)

- [ ] **Step 1: Update the Tools-menu assertion (failing test)**

In `tests/ui/test_menus.py`, replace the body of `test_tools_menu_contents` so it expects the new action after a separator:

```python
def test_tools_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Tools")
    assert action_labels(menu) == [
        "Manage Captions...", "―",
        "Find Reused Tables...", "―",
        "Validate Project", "―",
        "Reparse Raw XML into Tree",
    ]
```

- [ ] **Step 2: Write the failing behavior tests**

Append to `tests/ui/test_main_window.py`. The success test edits the editor text (adds a second Page) then reparses; the failure test loads a good model, puts malformed XML in the editor, reparses, and asserts the last-good tree/model survived and the error line was highlighted. `QMessageBox.critical` is monkeypatched to avoid a real modal dialog (matching the existing open-failure test convention):

```python
_REPARSE_ONE_PAGE = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="equipment" tableName="pr.equipment" caption="Equipment"/>
    </Pages>
  </Presentation>
</Project>
"""

_REPARSE_TWO_PAGES = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="equipment" tableName="pr.equipment" caption="Equipment"/>
      <Page fileName="work_orders" tableName="pr.x_workorder" caption="Work Orders"/>
    </Pages>
  </Presentation>
</Project>
"""


def _reparse_menu_action(window):
    from tests.ui._menu_helpers import find_action, find_top_menu

    menu = find_top_menu(window, "Tools")
    return find_action(menu, "Reparse Raw XML into Tree")


def test_reparse_action_exists_and_is_not_a_stub(qtbot):
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    action = _reparse_menu_action(window)
    assert action is not None
    # A stub action would set the "Not yet implemented" status message.
    action.trigger()
    assert window.statusBar().currentMessage() != "Not yet implemented: Reparse Raw XML into Tree"


def test_reparse_success_rebuilds_tree_and_adopts_new_model(qtbot):
    import textwrap

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    # Start with a one-page model loaded.
    project = load_project_from_text(textwrap.dedent(_REPARSE_ONE_PAGE))
    window._current_project = project
    window.project_tree.populate_from_project(project)
    assert window.project_tree.topLevelItemCount() == 1

    # User edits the editor to a two-page document, then reparses.
    window.center_stage.xml_editor.setPlainText(textwrap.dedent(_REPARSE_TWO_PAGES))
    window._reparse_raw_xml()

    assert window.project_tree.topLevelItemCount() == 2
    assert window._current_project is not project
    assert len(window._current_project.pages) == 2
    # Properties reset to empty after the rebuild cleared the selection.
    assert window.properties_panel.is_showing_empty_state() is True


def test_reparse_failure_preserves_model_and_tree_and_highlights_line(qtbot, monkeypatch):
    import textwrap

    from PySide6.QtWidgets import QMessageBox

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    project = load_project_from_text(textwrap.dedent(_REPARSE_ONE_PAGE))
    window._current_project = project
    window.project_tree.populate_from_project(project)
    items_before = window.project_tree.topLevelItemCount()

    # Suppress the real modal dialog and record that it was shown.
    critical_calls = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: critical_calls.append(args)
    )
    # Spy on the editor's error-line highlight.
    highlighted = []
    monkeypatch.setattr(
        window.center_stage.xml_editor,
        "highlight_error_line",
        lambda line: highlighted.append(line),
    )

    window.center_stage.xml_editor.setPlainText(
        "<Project><Presentation><Pages><Page></Pages></Presentation></Project>"
    )
    window._reparse_raw_xml()

    assert critical_calls, "expected QMessageBox.critical to be shown"
    assert highlighted, "expected highlight_error_line to be called for the error line"
    # Last-good state survived: same model object, same tree contents.
    assert window._current_project is project
    assert window.project_tree.topLevelItemCount() == items_before


def test_reparse_failure_without_line_number_still_shows_dialog(qtbot, monkeypatch):
    import textwrap

    from PySide6.QtWidgets import QMessageBox

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    project = load_project_from_text(textwrap.dedent(_REPARSE_ONE_PAGE))
    window._current_project = project
    window.project_tree.populate_from_project(project)

    critical_calls = []
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: critical_calls.append(args)
    )
    highlighted = []
    monkeypatch.setattr(
        window.center_stage.xml_editor,
        "highlight_error_line",
        lambda line: highlighted.append(line),
    )

    # Force a PgtpParseError with line=None by monkeypatching the parser
    # entry point MainWindow calls.
    import pgtp_editor.ui.main_window as mw
    from pgtp_editor.model.parser import PgtpParseError

    def _raise_no_line(text, source_description="<editor>"):
        raise PgtpParseError("structural surprise", line=None)

    monkeypatch.setattr(mw, "load_project_from_text", _raise_no_line)
    window._reparse_raw_xml()

    assert critical_calls, "dialog still shown when line is unknown"
    assert highlighted == []  # no line to highlight
    assert window._current_project is project  # state preserved


def test_reparse_realigns_click_sync_after_line_shift(qtbot):
    import textwrap

    from pgtp_editor.model.parser import load_project_from_text
    from pgtp_editor.ui.main_window import MainWindow
    from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE

    window = MainWindow()
    qtbot.addWidget(window)
    project = load_project_from_text(textwrap.dedent(_REPARSE_ONE_PAGE))
    window._current_project = project
    window.project_tree.populate_from_project(project)

    # Edit: prepend two blank comment lines so the <Page> shifts down by 2,
    # then reparse so the model's sourcelines realign to the edited text.
    shifted = "<!-- a -->\n<!-- b -->\n" + textwrap.dedent(_REPARSE_ONE_PAGE)
    window.center_stage.xml_editor.setPlainText(shifted)
    window._reparse_raw_xml()

    new_page = window._current_project.pages[0]
    # Clicking the page's (now-shifted) line resolves to the rebuilt node.
    window._on_editor_line_clicked(new_page.sourceline)
    assert window.project_tree.currentItem().data(0, MODEL_NODE_ROLE) is new_page
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_menus.py::test_tools_menu_contents tests/ui/test_main_window.py -v -k "reparse or tools_menu_contents"`
Expected: FAIL — `test_tools_menu_contents` fails on the missing label, and the reparse tests fail with `AttributeError: 'MainWindow' object has no attribute '_reparse_raw_xml'`.

- [ ] **Step 4: Add the import, the menu action, and the handlers**

In `pgtp_editor/ui/main_window.py`, extend the existing parser import to add `load_project_from_text`:

```python
from pgtp_editor.model.parser import (
    PgtpParseError,
    _build_project_model,
    load_project,
    load_project_from_text,
)
```

Modify `_build_tools_menu` to add the real action after a separator:

```python
    def _build_tools_menu(self):
        menu = self.menuBar().addMenu("Tools")
        self._add_stub_action(menu, "Manage Captions...")
        menu.addSeparator()
        self._add_stub_action(menu, "Find Reused Tables...")
        menu.addSeparator()
        self._add_stub_action(menu, "Validate Project")
        menu.addSeparator()
        reparse_action = menu.addAction("Reparse Raw XML into Tree")
        reparse_action.triggered.connect(self._reparse_raw_xml)
```

Add the two handler methods (place them after `_handle_parse_failure`):

```python
    def _reparse_raw_xml(self):
        text = self.center_stage.xml_editor.toPlainText()
        try:
            project = load_project_from_text(text, source_description="<editor>")
        except PgtpParseError as exc:
            self._handle_reparse_failure(exc)
            return
        # SUCCESS: rebuild tree + adopt the new model so click-sync realigns.
        self.project_tree.populate_from_project(project)
        self._current_project = project
        # Properties has no valid selection against the freshly rebuilt tree
        # (populate_from_project cleared it); show the empty state until the
        # user clicks again. show_node(None, None) is the panel's own reset.
        self.properties_panel.show_node(None, None)
        self.statusBar().showMessage("Reparsed raw XML into tree", 5000)

    def _handle_reparse_failure(self, exc: PgtpParseError) -> None:
        # Mirror the Tier-1 open-failure pattern (_handle_parse_failure), but
        # WITHOUT re-reading a file and WITHOUT touching the existing model or
        # tree: the last-good state must survive a failed reparse so the user
        # can fix the XML and try again.
        QMessageBox.critical(
            self,
            "Reparse Failed",
            f"Could not reparse the raw XML:\n\n{exc}",
        )
        if exc.line is not None:
            self.center_stage.xml_editor.highlight_error_line(exc.line)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_menus.py::test_tools_menu_contents tests/ui/test_main_window.py -v -k "reparse or tools_menu_contents"`
Expected: PASS (test_tools_menu_contents plus the 5 reparse tests).

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_main_window.py tests/ui/test_menus.py
git commit -m "feat: add Tools > Reparse Raw XML into Tree action"
```

---

## Task 7: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest -q`
Expected: all tests pass — the new `tests/model/test_line_index.py`, the appended `load_project_from_text` tests, the `select_node` tests, the `line_clicked`/`mouseReleaseEvent` tests, the click-sync tests, the Reparse tests, and the updated `test_tools_menu_contents`, with no regressions in any existing file (`test_xml_editor.py`, `test_project_tree.py`, `test_main_window.py`, `test_menus.py`, model tests).

- [ ] **Step 2: Confirm the merge-risk note for sub-project D is captured in the eventual PR**

No code change. When this branch's PR is opened, include in the description: `xml_editor.py` gained one `Signal` import, one class-level `line_clicked = Signal(int)`, and one `mouseReleaseEvent` override — a small, localized change that will trivially conflict with the concurrent structural-selection sub-project D (which also edits `xml_editor.py`); resolve by keeping both additions (the top-of-class signal declaration and the mouse-event method compose cleanly, since `mouseReleaseEvent` only calls `super()` and reads the cursor).

- [ ] **Step 3: Final commit if anything is uncommitted**

```bash
git status
# If any stray changes remain:
git add -A
git commit -m "chore: editor-tree sync + reparse sub-project complete"
```

---

## Notes on decisions carried from the spec (for the implementing engineer)

- **`node_at_line` end-line rule:** each node's range ends one line before the next node at the same-or-shallower depth (the next non-descendant); the last such node runs to a large sentinel (`10**9`). The deepest containing entry wins, so a click inside a Column's `<Format>`/`<Lookup>` body resolves to the Column, and a click in a Detail's own whitespace (before its first child node) resolves to the Detail. A Detail's range starts at its **outer** `sourceline`, never `inner_sourceline`.
- **No re-entrancy guard, by design:** the wiring is strictly one-directional (editor click → tree select → Properties). Selecting a tree item does not scroll or re-select the editor (tree→editor scroll is out of scope), so no ping-pong is possible and no guard is added.
- **Reparse failure preserves state:** unlike `_handle_parse_failure` (which blanks the tree and re-reads a file), `_handle_reparse_failure` must NOT touch `_current_project`, the tree, or re-read any file — only show the dialog and highlight the error line. `_current_project_path` is intentionally left unchanged on reparse success too (the on-disk file has not changed).
- **CESU-8 repair is deliberately omitted from `load_project_from_text`:** editor text is already a valid Python `str`; `str.encode("utf-8")` produces valid UTF-8 bytes for lxml.
- **Click-sync between reparses is best-effort:** it maps against the last-loaded/last-reparsed model, so after edits it may select a neighboring node; Reparse is the explicit resync (verified by `test_reparse_realigns_click_sync_after_line_shift`).
