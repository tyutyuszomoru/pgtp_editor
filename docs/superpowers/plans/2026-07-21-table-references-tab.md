# Table References Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the modal "Find Reused Tables" window with a persistent, navigable "Table references" tab in the left dock — selecting a reference drives Properties, double-clicking jumps to the exact `<Lookup>`/element line, and it toggles on/off from the View menu.

**Architecture:** Extend the Qt-free `reused_tables` analyzer so each usage carries the target node, its kind, a jump line, and a reference type (adding `(lookup with insert)`). A new `TableReferencesPanel(QTreeWidget)` renders these and emits `selection_changed`/`jump_requested` signals (mirroring the existing `DbCheckPanel`). MainWindow hosts it as a hidden tab in `left_tabs`, wires the signals to the existing `properties_panel.show_node` and `_tree_jump_to_line`, and gains a checkable View action.

**Tech Stack:** Python 3.10+, PySide6 (QtWidgets), lxml, pytest + pytest-qt. Tests run with `$env:QT_QPA_PLATFORM='offscreen'` using system `python`.

**Spec:** `docs/superpowers/specs/2026-07-21-table-references-tab-design.md`

---

## File structure

- **Modify** `pgtp_editor/analysis/reused_tables.py` — add `TableReference`, change `TableUsage` to hold `references` (keep a derived `breadcrumbs` property), attach node/kind/line/ref_type.
- **Modify** `tests/analysis/test_reused_tables.py` — add structured-reference tests; existing breadcrumb tests keep passing via the derived property.
- **Create** `pgtp_editor/ui/table_references_panel.py` — the tab widget.
- **Create** `tests/ui/test_table_references_panel.py` — panel tests.
- **Modify** `pgtp_editor/ui/main_window.py` — add hidden tab + View toggle + refresh-on-reparse; remove the Tools action, its handler, the `ReusedTablesWindow` import and `_reused_tables_window` reference.
- **Delete** `pgtp_editor/ui/reused_tables_window.py` and `tests/ui/test_reused_tables_window.py`.
- **Modify** `tests/ui/` — add MainWindow wiring tests (new file `tests/ui/test_table_references_wiring.py`).

---

## Task 1: Structured references in the analyzer

**Files:**
- Modify: `pgtp_editor/analysis/reused_tables.py`
- Test: `tests/analysis/test_reused_tables.py`

- [ ] **Step 1: Write failing tests for the structured references**

Append to `tests/analysis/test_reused_tables.py`:

```python
from lxml import etree

from pgtp_editor.analysis.reused_tables import TableReference


def _lookup_child(table, sourceline=None, with_insert=False):
    xml = f'<Lookup tableName="{table}">'
    xml += "<OnTheFlyInsertPage/>" if with_insert else ""
    xml += "</Lookup>"
    element = etree.fromstring(xml)
    return ChildElement(attrib=dict(element.attrib), sourceline=sourceline, element=element)


def test_page_reference_carries_node_kind_and_line():
    page = PageNode(identity="P", attrib={"tableName": "t", "caption": "P"}, sourceline=7)
    usage = collect_table_usages(ProjectModel(pages=[page]))[0]
    ref = usage.references[0]
    assert isinstance(ref, TableReference)
    assert ref.node is page
    assert ref.kind == "page"
    assert ref.line == 7
    assert ref.ref_type == "table"


def test_detail_reference_carries_detail_node_and_kind():
    detail = DetailNode(identity="d", attrib={"tableName": "lines", "caption": "L"}, sourceline=12)
    page = PageNode(identity="P", attrib={"tableName": "orders", "caption": "O"}, details=[detail])
    usages = {u.name: u for u in collect_table_usages(ProjectModel(pages=[page]))}
    ref = usages["lines"].references[0]
    assert ref.node is detail
    assert ref.kind == "detail"
    assert ref.line == 12


def test_lookup_reference_uses_lookup_line_and_column_node():
    col = ColumnNode(
        identity="c", attrib={"fieldName": "objecttype"}, sourceline=3,
        lookup=_lookup_child("kb.x_objecttype", sourceline=5),
    )
    page = PageNode(identity="P", attrib={"tableName": "orders", "caption": "O"}, columns=[col])
    usage = collect_table_usages(ProjectModel(pages=[page]))[0]
    ref = usage.references[0]
    assert ref.node is col
    assert ref.kind == "column"
    assert ref.line == 5              # the <Lookup> line, not the column's line 3
    assert ref.ref_type == "lookup"
    assert ref.breadcrumb == "Page 'O' ▸ Column 'objecttype' (lookup)"


def test_lookup_with_insert_reference_type_and_breadcrumb():
    col = ColumnNode(
        identity="c", attrib={"fieldName": "objecttype"}, sourceline=3,
        lookup=_lookup_child("kb.x_objecttype", sourceline=5, with_insert=True),
    )
    page = PageNode(identity="P", attrib={"tableName": "orders", "caption": "O"}, columns=[col])
    ref = collect_table_usages(ProjectModel(pages=[page]))[0].references[0]
    assert ref.ref_type == "lookup with insert"
    assert ref.breadcrumb == "Page 'O' ▸ Column 'objecttype' (lookup with insert)"


def test_lookup_line_falls_back_to_column_line_when_lookup_line_missing():
    col = ColumnNode(
        identity="c", attrib={"fieldName": "f"}, sourceline=9,
        lookup=_lookup_child("t", sourceline=None),
    )
    page = PageNode(identity="P", attrib={"tableName": "orders", "caption": "O"}, columns=[col])
    ref = collect_table_usages(ProjectModel(pages=[page]))[0].references[0]
    assert ref.line == 9


def test_breadcrumbs_property_still_returns_strings():
    page = PageNode(identity="P", attrib={"tableName": "t", "caption": "P"}, sourceline=1)
    usage = collect_table_usages(ProjectModel(pages=[page]))[0]
    assert usage.breadcrumbs == ["Page 'P'"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/analysis/test_reused_tables.py -q`
Expected: FAIL — `ImportError: cannot import name 'TableReference'` (and the new tests error).

- [ ] **Step 3: Rewrite `reused_tables.py` to build structured references**

Replace the whole body of `pgtp_editor/analysis/reused_tables.py` below the module docstring with:

```python
from __future__ import annotations

from dataclasses import dataclass, field

_SEP = " ▸ "  # " ▸ "


@dataclass(frozen=True)
class TableReference:
    """One place a table/view is referenced, with enough context to navigate.

    breadcrumb: human-readable path, e.g. "Page 'X' ▸ Column 'y' (lookup)".
    node:       the owning model node (PageNode | DetailNode | ColumnNode).
    kind:       "page" | "detail" | "column" (the Properties-panel node kind).
    line:       1-based source line to jump to, or None.
    ref_type:   "table" | "lookup" | "lookup with insert".
    """
    breadcrumb: str
    node: object
    kind: str
    line: "int | None"
    ref_type: str


@dataclass
class TableUsage:
    name: str
    references: list[TableReference] = field(default_factory=list)

    @property
    def breadcrumbs(self) -> list[str]:
        """The reference breadcrumbs as plain strings (convenience/back-compat)."""
        return [ref.breadcrumb for ref in self.references]


def _page_label(page) -> str:
    return page.attrib.get("caption") or page.file_name or page.table_name or ""


def _detail_label(detail) -> str:
    return detail.attrib.get("caption") or detail.table_name or ""


def _lookup_ref_type(lookup) -> str:
    """"lookup with insert" when the <Lookup> has a child <OnTheFlyInsertPage>,
    else "lookup". Falls back to "lookup" when the lxml element was not retained
    (e.g. a hand-built ChildElement in a unit test)."""
    element = getattr(lookup, "element", None)
    if element is not None and element.find("OnTheFlyInsertPage") is not None:
        return "lookup with insert"
    return "lookup"


def collect_table_usages(project) -> list[TableUsage]:
    """Return the table usages of ``project`` grouped by table name.

    References with a ``None``/empty table name are skipped. The list is sorted
    by table name; each table's references stay in document (traversal) order.
    """
    grouped: dict[str, list[TableReference]] = {}

    def record(name: str | None, ref: TableReference) -> None:
        if not name:
            return
        grouped.setdefault(name, []).append(ref)

    def visit_columns(columns, prefix: str) -> None:
        for column in columns:
            lookup = column.lookup
            if lookup is None:
                continue
            table = lookup.attrib.get("tableName")
            field_name = column.field_name or ""
            ref_type = _lookup_ref_type(lookup)
            line = lookup.sourceline if lookup.sourceline is not None else column.sourceline
            crumb = f"{prefix}{_SEP}Column '{field_name}' ({ref_type})"
            record(table, TableReference(crumb, column, "column", line, ref_type))

    def visit_detail(detail, prefix: str) -> None:
        crumb = f"{prefix}{_SEP}Detail '{_detail_label(detail)}'"
        record(
            detail.table_name,
            TableReference(crumb, detail, "detail", detail.sourceline, "table"),
        )
        visit_columns(detail.columns, crumb)
        for child in detail.details:
            visit_detail(child, crumb)

    for page in project.pages:
        crumb = f"Page '{_page_label(page)}'"
        record(
            page.table_name,
            TableReference(crumb, page, "page", page.sourceline, "table"),
        )
        visit_columns(page.columns, crumb)
        for detail in page.details:
            visit_detail(detail, crumb)

    return [TableUsage(name=name, references=grouped[name]) for name in sorted(grouped)]
```

Keep the existing module docstring at the top of the file unchanged.

- [ ] **Step 4: Run the analyzer tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/analysis/test_reused_tables.py -q`
Expected: PASS (new structured tests + existing breadcrumb tests via the derived property).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/analysis/reused_tables.py tests/analysis/test_reused_tables.py
git commit -m "Add structured TableReference (node/kind/line/ref_type) to reused_tables analyzer"
```

---

## Task 2: The `TableReferencesPanel` widget

**Files:**
- Create: `pgtp_editor/ui/table_references_panel.py`
- Test: `tests/ui/test_table_references_panel.py`

- [ ] **Step 1: Write the failing panel tests**

Create `tests/ui/test_table_references_panel.py`:

```python
from PySide6.QtCore import Qt

from pgtp_editor.analysis.reused_tables import TableReference, TableUsage
from pgtp_editor.ui.table_references_panel import TableReferencesPanel


def _usage():
    ref = TableReference(
        breadcrumb="Page 'O' ▸ Column 'objecttype' (lookup with insert)",
        node=object(), kind="column", line=5, ref_type="lookup with insert",
    )
    return TableUsage(name="kb.x_objecttype", references=[ref]), ref


def test_set_usages_builds_table_row_with_count_and_child(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, ref = _usage()

    panel.set_usages([usage])

    assert panel.tree.topLevelItemCount() == 1
    top = panel.tree.topLevelItem(0)
    assert top.text(0) == "kb.x_objecttype  (1)"
    assert top.childCount() == 1
    child = top.child(0)
    assert child.text(0) == ref.breadcrumb
    assert child.data(0, Qt.ItemDataRole.UserRole) is ref


def test_selection_of_reference_emits_node_and_kind(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, ref = _usage()
    panel.set_usages([usage])
    got = []
    panel.selection_changed.connect(lambda node, kind: got.append((node, kind)))

    child = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(child)

    assert got and got[-1] == (ref.node, "column")


def test_selection_of_table_row_emits_none(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, _ref = _usage()
    panel.set_usages([usage])
    got = []
    panel.selection_changed.connect(lambda node, kind: got.append((node, kind)))

    panel.tree.setCurrentItem(panel.tree.topLevelItem(0))

    assert got and got[-1] == (None, None)


def test_double_click_reference_emits_jump_with_line(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, ref = _usage()
    panel.set_usages([usage])
    got = []
    panel.jump_requested.connect(lambda line: got.append(line))

    child = panel.tree.topLevelItem(0).child(0)
    panel.tree.itemDoubleClicked.emit(child, 0)

    assert got == [5]


def test_set_usages_clears_previous_rows(qtbot):
    panel = TableReferencesPanel()
    qtbot.addWidget(panel)
    usage, _ = _usage()
    panel.set_usages([usage])
    panel.set_usages([])
    assert panel.tree.topLevelItemCount() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_table_references_panel.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.ui.table_references_panel'`.

- [ ] **Step 3: Implement the panel**

Create `pgtp_editor/ui/table_references_panel.py`:

```python
"""TableReferencesPanel: the left-dock "Table references" tree.

Renders the grouped output of
:func:`pgtp_editor.analysis.reused_tables.collect_table_usages`: top-level rows
are table/view names with a usage count; child rows are individual references
carrying their :class:`TableReference` (node, kind, line) as item data.

Non-modal and test-driven: selecting a reference emits ``selection_changed`` so
MainWindow can drive the Properties panel, and double-clicking a reference emits
``jump_requested`` with the line to navigate the Raw XML editor to.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

_REF_ROLE = Qt.ItemDataRole.UserRole


class TableReferencesPanel(QWidget):
    selection_changed = Signal(object, object)  # (node | None, kind:str | None)
    jump_requested = Signal(object)             # (line:int | None)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

    def set_usages(self, usages) -> None:
        self.tree.clear()
        for usage in usages:
            top = QTreeWidgetItem([f"{usage.name}  ({len(usage.references)})"])
            for ref in usage.references:
                child = QTreeWidgetItem([ref.breadcrumb])
                child.setData(0, _REF_ROLE, ref)
                top.addChild(child)
            self.tree.addTopLevelItem(top)

    def _on_current_changed(self, current, _previous) -> None:
        ref = current.data(0, _REF_ROLE) if current is not None else None
        if ref is None:
            self.selection_changed.emit(None, None)
        else:
            self.selection_changed.emit(ref.node, ref.kind)

    def _on_double_click(self, item, _column) -> None:
        ref = item.data(0, _REF_ROLE)
        if ref is not None:
            self.jump_requested.emit(ref.line)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_table_references_panel.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/table_references_panel.py tests/ui/test_table_references_panel.py
git commit -m "Add TableReferencesPanel widget with selection/jump signals"
```

---

## Task 3: Wire the panel into MainWindow (tab + View toggle) and remove the modal

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Delete: `pgtp_editor/ui/reused_tables_window.py`, `tests/ui/test_reused_tables_window.py`
- Test: `tests/ui/test_table_references_wiring.py` (create)

- [ ] **Step 1: Write the failing wiring tests**

Create `tests/ui/test_table_references_wiring.py`:

```python
from unittest.mock import patch

from pgtp_editor.ui.main_window import MainWindow

PGTP_WITH_LOOKUP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="orders" tableName="pr.orders" caption="Orders">
        <ColumnPresentations>
          <ColumnPresentation fieldName="objecttype">
            <Lookup tableName="kb.x_objecttype" linkFieldName="id">
              <OnTheFlyInsertPage fileName="x_objecttype" caption="X Objecttype"/>
            </Lookup>
          </ColumnPresentation>
        </ColumnPresentations>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def _open(window, tmp_path):
    path = tmp_path / "p.pgtp"
    path.write_text(PGTP_WITH_LOOKUP, encoding="utf-8")
    window.open_project_file(str(path))


def test_toggle_on_reveals_and_populates_table_references_tab(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)

    window._toggle_table_references(True)

    idx = window.table_refs_tab_index
    assert window.left_tabs.isTabVisible(idx) is True
    assert window.left_tabs.currentIndex() == idx
    assert window.table_refs_panel.tree.topLevelItemCount() == 1
    top = window.table_refs_panel.tree.topLevelItem(0)
    assert top.text(0).startswith("kb.x_objecttype")
    # ref type reflects the nested OnTheFlyInsertPage
    assert "(lookup with insert)" in top.child(0).text(0)


def test_toggle_off_hides_the_tab(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)

    window._toggle_table_references(False)

    assert window.left_tabs.isTabVisible(window.table_refs_tab_index) is False


def test_toggle_on_without_project_shows_message_and_unchecks(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._table_refs_action.setChecked(True)  # fires _toggle_table_references(True)

    assert window._table_refs_action.isChecked() is False
    assert window.left_tabs.isTabVisible(window.table_refs_tab_index) is False


def test_selection_drives_properties_panel(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)

    with patch.object(window.properties_panel, "show_node") as show:
        child = window.table_refs_panel.tree.topLevelItem(0).child(0)
        window.table_refs_panel.tree.setCurrentItem(child)

    assert show.called
    node, kind = show.call_args.args
    assert kind == "column"
    assert node is not None


def test_double_click_jumps_editor_to_lookup_line(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)

    with patch.object(window, "_tree_jump_to_line") as jump:
        child = window.table_refs_panel.tree.topLevelItem(0).child(0)
        window.table_refs_panel.tree.itemDoubleClicked.emit(child, 0)

    jump.assert_called_once()
    # The <Lookup> element's source line was passed (an int, > 1).
    (line,) = jump.call_args.args
    assert isinstance(line, int) and line > 1


def test_tools_menu_has_no_reused_tables_entry(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    labels = []
    for menu in window.menuBar().findChildren(type(window.menuBar().addMenu("x"))):
        for action in menu.actions():
            labels.append(action.text())
    assert not any("Reused Tables" in (t or "") for t in labels)
    assert any("Find table reference" in (t or "") for t in labels)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_table_references_wiring.py -q`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_toggle_table_references'`.

- [ ] **Step 3: Add the panel + tab in MainWindow `__init__`**

In `pgtp_editor/ui/main_window.py`, find the Database Check tab block (ends around line 220 with the `db_check_panel` signal connections). Immediately after `self.left_tabs.setTabVisible(self.db_check_tab_index, False)` and its connect lines, add:

```python
        # Table references ride in their own hidden tab, revealed by the
        # View > "Find table reference" toggle (mirrors the Database Check tab).
        self.table_refs_panel = TableReferencesPanel()
        self.table_refs_tab_index = self.left_tabs.addTab(
            self.table_refs_panel, "Table references"
        )
        self.left_tabs.setTabVisible(self.table_refs_tab_index, False)
        self.table_refs_panel.selection_changed.connect(self._on_table_ref_selection)
        self.table_refs_panel.jump_requested.connect(self._tree_jump_to_line)
```

- [ ] **Step 4: Update imports and remove the modal-window references**

In the import block near the top of `main_window.py`:
- Add: `from pgtp_editor.ui.table_references_panel import TableReferencesPanel`
- Remove: `from pgtp_editor.ui.reused_tables_window import ReusedTablesWindow`
- Keep: `from pgtp_editor.analysis.reused_tables import collect_table_usages`

Find and delete the `_reused_tables_window` initialization line (around line 169):

```python
        self._reused_tables_window = None
```

- [ ] **Step 5: Add the selection handler and toggle method**

Add these two methods next to `_on_tree_selection_changed` (around line 619):

```python
    def _on_table_ref_selection(self, node, kind):
        self.properties_panel.show_node(node, kind)

    def _toggle_table_references(self, checked: bool) -> None:
        """View > "Find table reference": show/hide the Table references tab.
        On show, (re)compute usages from the current project; if none is open,
        surface a status message and leave the action unchecked."""
        if checked:
            if self._current_project is None:
                self.statusBar().showMessage("Open a project first.", 5000)
                self._table_refs_action.setChecked(False)
                return
            self.table_refs_panel.set_usages(
                collect_table_usages(self._current_project)
            )
            self.left_tabs.setTabVisible(self.table_refs_tab_index, True)
            self.left_tabs.setCurrentIndex(self.table_refs_tab_index)
        else:
            self.left_tabs.setTabVisible(self.table_refs_tab_index, False)
```

- [ ] **Step 6: Add the View-menu action**

In `_build_menu_bar`, in the View menu section (after the `properties_action` block around line 1460, before the expand/collapse actions), add:

```python
        table_refs_action = menu.addAction("Find table reference")
        table_refs_action.setCheckable(True)
        table_refs_action.setChecked(False)
        table_refs_action.toggled.connect(self._toggle_table_references)
        self._table_refs_action = table_refs_action
```

- [ ] **Step 7: Remove the Tools-menu entry and its handler**

In `_build_tools_menu` (around line 2088), delete these three lines:

```python
        menu.addSeparator()
        reused_tables_action = menu.addAction("Find Reused Tables...")
        reused_tables_action.triggered.connect(self._open_reused_tables)
```

Then delete the entire `_open_reused_tables` method (around lines 2071-2080):

```python
    def _open_reused_tables(self):
        if self._current_project is None:
            self.statusBar().showMessage("Open a project first.", 5000)
            return
        if self._reused_tables_window is None:
            self._reused_tables_window = ReusedTablesWindow(self)
        self._reused_tables_window.set_usages(
            collect_table_usages(self._current_project)
        )
        self._reused_tables_window.show()
```

- [ ] **Step 8: Delete the obsolete modal window and its test**

```bash
git rm pgtp_editor/ui/reused_tables_window.py tests/ui/test_reused_tables_window.py
```

- [ ] **Step 9: Run the wiring tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_table_references_wiring.py -q`
Expected: PASS (6 passed).

- [ ] **Step 10: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_table_references_wiring.py
git commit -m "Wire Table references tab into MainWindow; remove Find Reused Tables modal"
```

---

## Task 4: Refresh the tab on reparse when visible

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_table_references_wiring.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_table_references_wiring.py`:

```python
PGTP_TWO_LOOKUPS = PGTP_WITH_LOOKUP.replace(
    "</Pages>",
    """  <Page fileName="items" tableName="pr.items" caption="Items">
        <ColumnPresentations>
          <ColumnPresentation fieldName="cat">
            <Lookup tableName="kb.x_category" linkFieldName="id"/>
          </ColumnPresentation>
        </ColumnPresentations>
      </Page>
</Pages>""",
)


def test_reparse_refreshes_visible_table_references_tab(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    window._toggle_table_references(True)
    assert window.table_refs_panel.tree.topLevelItemCount() == 1

    # Replace the buffer with a project that references a second table, then
    # reparse. The visible tab must reflect the new content.
    window.center_stage.xml_editor.setPlainText(PGTP_TWO_LOOKUPS)
    with patch("pgtp_editor.ui.main_window.QMessageBox.information"):
        window._reparse_raw_xml()

    names = {
        window.table_refs_panel.tree.topLevelItem(i).text(0).split("  ")[0]
        for i in range(window.table_refs_panel.tree.topLevelItemCount())
    }
    assert "kb.x_category" in names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_table_references_wiring.py::test_reparse_refreshes_visible_table_references_tab -q`
Expected: FAIL — the tab still shows only the original table.

- [ ] **Step 3: Refresh after a successful reparse**

In `main_window.py`, locate `_reparse_raw_xml`. After it repopulates the project tree (the `self.project_tree.populate_from_project(project)` call around line 1347) and has the fresh `project`/`self._current_project` set, add:

```python
        if self.left_tabs.isTabVisible(self.table_refs_tab_index):
            self.table_refs_panel.set_usages(
                collect_table_usages(self._current_project)
            )
```

Note: place this after `self._current_project` has been assigned the reparsed project, and guard nothing else — the tab-visible check is the gate.

- [ ] **Step 4: Run the test to verify it passes**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_table_references_wiring.py::test_reparse_refreshes_visible_table_references_tab -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_table_references_wiring.py
git commit -m "Refresh Table references tab on reparse when visible"
```

---

## Task 5: Full-suite verification and feature-tester gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
Expected: PASS — all tests green (the deleted `test_reused_tables_window.py` no longer collected; new analyzer/panel/wiring tests included).

- [ ] **Step 2: Manual smoke check (optional but recommended)**

Launch the app, open `sample/dev_Ferrara.pgtp`, toggle View > "Find table reference", confirm the tab appears with grouped tables, single-click a reference updates Properties, and double-click jumps the Raw XML editor to the `<Lookup>` line.

Run: `python -m pgtp_editor.main`

- [ ] **Step 3: Dispatch the feature-tester agent**

Per `CLAUDE.md`, dispatch the `feature-tester` subagent with:
- Feature name: "Table references tab (replaces Find Reused Tables modal)".
- Spec: `docs/superpowers/specs/2026-07-21-table-references-tab-design.md`.
- Changed files: `pgtp_editor/analysis/reused_tables.py`, `pgtp_editor/ui/table_references_panel.py`, `pgtp_editor/ui/main_window.py`, deleted `pgtp_editor/ui/reused_tables_window.py`.
- It appends the verified result to `docs/TEST_LOG.md`.

- [ ] **Step 4: Commit the test log**

```bash
git add docs/TEST_LOG.md
git commit -m "Record Table references tab in TEST_LOG"
```

---

## Self-review notes

- **Spec coverage:** req 1 (rename) → Task 3 Step 6; req 2 (View toggle) → Task 3 Steps 5-7; req 3 (tab, not modal) → Tasks 2-3 + deletion in Task 3 Step 8; req 4 (double-click jump) → Task 2 (`jump_requested`) + Task 3 (`_tree_jump_to_line` wiring) + wiring test; req 5 (`lookup with insert`) → Task 1 (`_lookup_ref_type`) + tests; req 6 (Properties) → Task 3 (`_on_table_ref_selection`) + wiring test. Confirmed decisions (jump to `<Lookup>` line; Tools entry removed; lookup Properties = owning column) → Task 1 line resolution, Task 3 Step 7, Task 1 `kind="column"`.
- **Placeholder scan:** none — every code step shows full code.
- **Type consistency:** `TableReference(breadcrumb, node, kind, line, ref_type)`, `TableUsage.references`, `TableReferencesPanel.selection_changed(node, kind)` / `jump_requested(line)`, `table_refs_panel` / `table_refs_tab_index` / `_table_refs_action` / `_toggle_table_references` / `_on_table_ref_selection` used consistently across Tasks 1-4.
