# PGTP Editor — Empty Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the empty application shell for PGTP Editor — the main window, docking layout, full menu bar, and right-click context menus, all wired to stub handlers — so it can be reviewed before any real `.pgtp` model/diff/move-copy/caption logic is built on top of it.

**Architecture:** A PySide6 `QMainWindow` with a project tree docked left, an audit/problems panel docked bottom, and a 4-tab center stage (Properties / Diff-Merge / Caption Management / Raw XML, the last hidden by default). The project tree is populated with hardcoded placeholder data (clearly marked as such) purely so right-click context menus have something real to attach to and can be reviewed structurally. Every menu/context-menu action not yet implemented is wired to one shared "not implemented yet" status-bar stub — nothing is a dead click, but nothing does real work either.

**Tech Stack:** Python 3.13, PySide6 (Qt6) for the GUI, pytest + pytest-qt for tests. All three are already installed in this environment.

**Relationship to the full design:** This plan implements only §4.4 (as placeholder data), §5.1, §5.2, and §5.3 of [docs/superpowers/specs/2026-07-11-pgtp-editor-design.md](../specs/2026-07-11-pgtp-editor-design.md) — the UI shell. It deliberately does **not** implement any of §6 (feature logic), §2's `lxml` model, or real validation — those get their own plans in later phases, per the agile/incremental approach the project owner chose. Nothing in this plan should need to be rewritten by later phases; later phases replace the placeholder tree data and stub handlers with real logic behind the same seams established here.

**One resolved ambiguity from the spec:** §5.1 describes the center stage as tabbed "(Properties / Diff-Merge / Caption Management)" while §5.2's View menu lists a toggleable "Raw XML (text editor) Panel" without saying where it lives. This plan treats Raw XML as a fourth tab in the same center stage (hidden by default, shown via the View menu or later by the Tier-1 validation-failure recovery flow from spec §6.7) rather than a separate dock widget — this keeps the docking areas to exactly the two the spec's layout mockups showed (tree left, audit bottom) and matches "Properties Panel" *also* being a toggleable tab rather than a dock widget.

---

## Task 1: Project scaffolding and a blank window that boots

**Files:**
- Create: `pyproject.toml`
- Create: `pgtp_editor/__init__.py`
- Create: `pgtp_editor/ui/__init__.py`
- Create: `pgtp_editor/ui/main_window.py`
- Create: `pgtp_editor/main.py`
- Create: `tests/__init__.py`
- Create: `tests/ui/__init__.py`
- Test: `tests/ui/test_main_window.py`

- [ ] **Step 1: Create the package/test directory skeleton**

Create empty files: `pgtp_editor/__init__.py`, `pgtp_editor/ui/__init__.py`, `tests/__init__.py`, `tests/ui/__init__.py` (all zero-byte).

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "pgtp-editor"
version = "0.1.0"
description = "Companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp project files"
requires-python = ">=3.10"
license = { text = "GPL-3.0-only" }
dependencies = [
    "PySide6>=6.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.4",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["pgtp_editor*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
qt_api = "pyside6"
```

- [ ] **Step 3: Install the package in editable mode**

Run: `pip install -e ".[dev]"`
Expected: installs cleanly (PySide6/pytest/pytest-qt are already present, so this mainly registers the `pgtp_editor` package itself).

- [ ] **Step 4: Write the failing test**

```python
# tests/ui/test_main_window.py
from pgtp_editor.ui.main_window import MainWindow


def test_window_title(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "PGTP Editor"


def test_default_size(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.size().width() == 1400
    assert window.size().height() == 900
```

- [ ] **Step 5: Run the test, verify it fails**

Run: `pytest tests/ui/test_main_window.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.ui.main_window'`

- [ ] **Step 6: Implement `MainWindow`**

```python
# pgtp_editor/ui/main_window.py
from PySide6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)
```

- [ ] **Step 7: Run the test, verify it passes**

Run: `pytest tests/ui/test_main_window.py -v`
Expected: 2 passed

- [ ] **Step 8: Write the entry point**

```python
# pgtp_editor/main.py
import sys

from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9: Manually verify the window opens**

Run: `python -m pgtp_editor.main`
Expected: a window titled "PGTP Editor" opens at roughly 1400x900. Close it.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml pgtp_editor tests
git commit -m "feat: scaffold PGTP Editor package with a blank main window"
```

---

## Task 2: Docking layout — tree (left), audit (bottom), 4-tab center stage

**Files:**
- Create: `pgtp_editor/ui/project_tree.py`
- Create: `pgtp_editor/ui/center_stage.py`
- Modify: `pgtp_editor/ui/main_window.py`
- Create: `tests/ui/test_project_tree.py`
- Create: `tests/ui/test_center_stage.py`
- Modify: `tests/ui/test_main_window.py`

- [ ] **Step 1: Write the failing test for the center stage's tabs**

```python
# tests/ui/test_center_stage.py
from pgtp_editor.ui.center_stage import CenterStage


def test_four_tabs_in_order(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.count() == 4
    assert stage.tabText(0) == "Properties"
    assert stage.tabText(1) == "Diff / Merge"
    assert stage.tabText(2) == "Caption Management"
    assert stage.tabText(3) == "Raw XML"


def test_raw_xml_tab_hidden_by_default(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.isTabVisible(stage.raw_xml_tab_index) is False
    assert stage.isTabVisible(stage.properties_tab_index) is True


def test_set_raw_xml_tab_visible(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.set_raw_xml_tab_visible(True)
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True


def test_set_properties_tab_visible(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.set_properties_tab_visible(False)
    assert stage.isTabVisible(stage.properties_tab_index) is False
```

- [ ] **Step 2: Run it, verify it fails**

Run: `pytest tests/ui/test_center_stage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.ui.center_stage'`

- [ ] **Step 3: Implement `CenterStage`**

```python
# pgtp_editor/ui/center_stage.py
from PySide6.QtWidgets import QTabWidget, QWidget


class CenterStage(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.properties_tab_index = self.addTab(QWidget(), "Properties")
        self.diff_merge_tab_index = self.addTab(QWidget(), "Diff / Merge")
        self.caption_management_tab_index = self.addTab(QWidget(), "Caption Management")
        self.raw_xml_tab_index = self.addTab(QWidget(), "Raw XML")
        self.setTabVisible(self.raw_xml_tab_index, False)

    def set_properties_tab_visible(self, visible):
        self.setTabVisible(self.properties_tab_index, visible)

    def set_raw_xml_tab_visible(self, visible):
        self.setTabVisible(self.raw_xml_tab_index, visible)
```

- [ ] **Step 4: Run it, verify it passes**

Run: `pytest tests/ui/test_center_stage.py -v`
Expected: 4 passed

- [ ] **Step 5: Write the failing test for the (still-empty) project tree widget existing**

```python
# tests/ui/test_project_tree.py
from pgtp_editor.ui.project_tree import ProjectTreePanel


def test_tree_has_no_columns_header(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    assert tree.isHeaderHidden() is True
```

- [ ] **Step 6: Run it, verify it fails**

Run: `pytest tests/ui/test_project_tree.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.ui.project_tree'`

- [ ] **Step 7: Implement the minimal `ProjectTreePanel`**

```python
# pgtp_editor/ui/project_tree.py
from PySide6.QtWidgets import QTreeWidget


class ProjectTreePanel(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
```

- [ ] **Step 8: Run it, verify it passes**

Run: `pytest tests/ui/test_project_tree.py -v`
Expected: 1 passed

- [ ] **Step 9: Write the failing test for the docking layout in `MainWindow`**

Append to `tests/ui/test_main_window.py`:

```python
from PySide6.QtCore import Qt


def test_tree_dock_on_left(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.tree_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.tree_dock.windowTitle() == "Project Tree"


def test_audit_dock_on_bottom(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.dockWidgetArea(window.audit_dock) == Qt.DockWidgetArea.BottomDockWidgetArea
    assert window.audit_dock.windowTitle() == "Audit / Problems"


def test_center_stage_is_central_widget(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.centralWidget() is window.center_stage
```

- [ ] **Step 10: Run it, verify it fails**

Run: `pytest tests/ui/test_main_window.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute 'tree_dock'`

- [ ] **Step 11: Wire the docking layout into `MainWindow`**

```python
# pgtp_editor/ui/main_window.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QListWidget, QMainWindow

from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.project_tree import ProjectTreePanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PGTP Editor")
        self.resize(1400, 900)

        self.project_tree = ProjectTreePanel()
        self.tree_dock = QDockWidget("Project Tree", self)
        self.tree_dock.setObjectName("tree_dock")
        self.tree_dock.setWidget(self.project_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_dock)

        self.audit_panel = QListWidget()
        self.audit_dock = QDockWidget("Audit / Problems", self)
        self.audit_dock.setObjectName("audit_dock")
        self.audit_dock.setWidget(self.audit_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.audit_dock)

        self.center_stage = CenterStage()
        self.setCentralWidget(self.center_stage)
```

- [ ] **Step 12: Run all UI tests, verify they pass**

Run: `pytest tests/ui -v`
Expected: all passed (10 tests so far)

- [ ] **Step 13: Manually verify**

Run: `python -m pgtp_editor.main`
Expected: window shows a docked "Project Tree" panel on the left, a docked "Audit / Problems" panel on the bottom, and a tabbed center area with 3 visible tabs (Properties, Diff / Merge, Caption Management) — no "Raw XML" tab visible. Close it.

- [ ] **Step 14: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add docking layout with project tree, audit panel, and center stage"
```

---

## Task 3: Placeholder project-tree data and reused-table detection

**Files:**
- Modify: `pgtp_editor/ui/project_tree.py`
- Modify: `tests/ui/test_project_tree.py`

This introduces clearly-marked placeholder data (`PLACEHOLDER_PROJECT`) purely so later tasks have real tree items to build context menus against. It is deleted wholesale in the future phase that adds the real `lxml`-backed model.

- [ ] **Step 1: Write the failing tests for placeholder population**

Append to `tests/ui/test_project_tree.py`:

```python
from PySide6.QtCore import Qt


def test_two_placeholder_pages(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    assert tree.topLevelItemCount() == 2
    assert tree.topLevelItem(0).text(0) == "Equipment"
    assert tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole) == "page"
    assert tree.topLevelItem(1).text(0) == "Work Orders"


def test_equipment_page_has_two_details(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    assert equipment.childCount() == 2
    assert equipment.child(0).text(0) == "Sub-item"
    assert equipment.child(0).data(0, Qt.ItemDataRole.UserRole) == "detail"
    assert equipment.child(1).text(0) == "Attachments"


def test_detail_has_field_children(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    sub_item = equipment.child(0)
    assert sub_item.childCount() == 2
    assert sub_item.child(0).text(0) == "tag"
    assert sub_item.child(0).data(0, Qt.ItemDataRole.UserRole) == "field"


def test_reused_table_detected_across_pages(qtbot):
    tree = ProjectTreePanel()
    qtbot.addWidget(tree)
    equipment = tree.topLevelItem(0)
    attachments_detail = equipment.child(1)
    assert tree.has_duplicate_table(attachments_detail) is True

    sub_item_detail = equipment.child(0)
    assert tree.has_duplicate_table(sub_item_detail) is False
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `pytest tests/ui/test_project_tree.py -v`
Expected: FAIL — `topLevelItemCount()` is 0, `has_duplicate_table` doesn't exist.

- [ ] **Step 3: Implement placeholder data and population**

```python
# pgtp_editor/ui/project_tree.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

NODE_KIND_ROLE = Qt.ItemDataRole.UserRole
TABLE_NAME_ROLE = Qt.ItemDataRole.UserRole + 1

# Placeholder data only — replaced wholesale once the real lxml-backed
# model exists. "Attachments" and "Characteristics" intentionally share
# a tableName to exercise the reused-table detection below.
PLACEHOLDER_PROJECT = {
    "Equipment": {
        "table": "pr.equipment",
        "details": {
            "Sub-item": {"table": "pr.attachment", "fields": ["tag", "description"]},
            "Attachments": {"table": "pr.r_characteristic", "fields": ["cvalue"]},
        },
    },
    "Work Orders": {
        "table": "pr.x_workorder",
        "details": {
            "Characteristics": {"table": "pr.r_characteristic", "fields": ["cvalue"]},
        },
    },
}


class ProjectTreePanel(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._populate_placeholder()

    def _populate_placeholder(self):
        for page_name, page_data in PLACEHOLDER_PROJECT.items():
            page_item = QTreeWidgetItem([page_name])
            page_item.setData(0, NODE_KIND_ROLE, "page")
            self.addTopLevelItem(page_item)
            for detail_name, detail_data in page_data["details"].items():
                detail_item = QTreeWidgetItem([detail_name])
                detail_item.setData(0, NODE_KIND_ROLE, "detail")
                detail_item.setData(0, TABLE_NAME_ROLE, detail_data["table"])
                page_item.addChild(detail_item)
                for field_name in detail_data["fields"]:
                    field_item = QTreeWidgetItem([field_name])
                    field_item.setData(0, NODE_KIND_ROLE, "field")
                    detail_item.addChild(field_item)

    def iter_detail_items(self):
        for i in range(self.topLevelItemCount()):
            page_item = self.topLevelItem(i)
            for j in range(page_item.childCount()):
                yield page_item.child(j)

    def has_duplicate_table(self, detail_item):
        table_name = detail_item.data(0, TABLE_NAME_ROLE)
        count = sum(
            1 for item in self.iter_detail_items()
            if item.data(0, TABLE_NAME_ROLE) == table_name
        )
        return count > 1
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `pytest tests/ui/test_project_tree.py -v`
Expected: all passed

- [ ] **Step 5: Manually verify**

Run: `python -m pgtp_editor.main`
Expected: the Project Tree panel shows "Equipment" and "Work Orders" as top-level items, each expandable to their Details, each Detail expandable to Field leaves.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: populate project tree with placeholder data and reused-table detection"
```

---

## Task 4: Right-click context menus (Page / Detail / Field / multi-select)

**Files:**
- Modify: `pgtp_editor/ui/project_tree.py`
- Modify: `pgtp_editor/ui/main_window.py`
- Create: `tests/ui/_menu_helpers.py`
- Modify: `tests/ui/test_project_tree.py`

Introduces the single shared "not implemented yet" stub slot on `MainWindow`, threaded into `ProjectTreePanel` so context-menu tests don't need a full `MainWindow` to check menu contents.

- [ ] **Step 1: Write the shared test helper for reading menu contents**

`find_top_menu` deliberately uses `findChildren(QMenu)` plus a parent check rather than iterating `menuBar().actions()` and calling `.menu()` on each — the latter is a real PySide6/shiboken lifetime trap: the `QMenu` returned by `action.menu()` gets deleted as soon as the loop's temporary `QAction` wrapper is garbage-collected (verified: it crashes with `RuntimeError: libshiboken: Internal C++ object (PySide6.QtWidgets.QMenu) already deleted` the moment the caller touches the returned menu). `findChildren` walks the real Qt object tree instead, which doesn't have this problem. `open_recent` (a submenu, added via `menu.addMenu(...)` in Task 5) would also show up in `findChildren(QMenu)`, so the parent check is what limits results to top-level menus only.

```python
# tests/ui/_menu_helpers.py
"""Shared helpers for asserting on QMenu/QMenuBar contents in tests.
Not a test module itself — pytest only collects test_*.py files."""

from PySide6.QtWidgets import QMenu


def action_labels(menu):
    return [action.text() if not action.isSeparator() else "―" for action in menu.actions()]


def find_top_menu(window, title):
    menu_bar = window.menuBar()
    for menu in menu_bar.findChildren(QMenu):
        if menu.parent() is menu_bar and menu.title() == title:
            return menu
    return None


def all_top_level_menu_titles(window):
    menu_bar = window.menuBar()
    return [menu.title() for menu in menu_bar.findChildren(QMenu) if menu.parent() is menu_bar]


def find_action(menu, text):
    for action in menu.actions():
        if action.text() == text:
            return action
    return None
```

- [ ] **Step 2: Write the failing tests for context-menu contents**

Append to `tests/ui/test_project_tree.py`:

```python
from tests.ui._menu_helpers import action_labels, find_action


def test_page_context_menu(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    menu = tree.build_page_menu(tree.topLevelItem(0))
    assert action_labels(menu) == [
        "Edit Properties", "―",
        "Copy", "Paste", "Duplicate", "Copy to Other Open Project...", "―",
        "Add Detail...", "―",
        "Create Client (Readonly) Page", "Compare This Page With...", "―",
        "Find Field Usages...", "Rename / Unify Captions...", "―",
        "Delete Page",
    ]


def test_detail_context_menu_shows_compare_instance_when_table_reused(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    attachments_detail = tree.topLevelItem(0).child(1)
    menu = tree.build_detail_menu(attachments_detail)
    assert action_labels(menu) == [
        "Edit Properties", "―",
        "Cut", "Copy", "Paste", "Duplicate", "Move to Parent Page...", "Copy to Other Open Project...", "―",
        "Add Nested Detail...", "―",
        "Create Client (Readonly) Page", "Compare This Detail With...", "Compare with Other Instance...", "―",
        "Delete Detail (+ nested)",
    ]


def test_detail_context_menu_hides_compare_instance_when_table_unique(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    sub_item_detail = tree.topLevelItem(0).child(0)
    menu = tree.build_detail_menu(sub_item_detail)
    assert "Compare with Other Instance..." not in action_labels(menu)


def test_field_context_menu(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    field_item = tree.topLevelItem(0).child(0).child(0)
    menu = tree.build_field_menu(field_item)
    assert action_labels(menu) == [
        "Edit Caption / Hint / Short Caption", "―",
        "Find All Usages of This Field", "Unify Captions Across Pages...", "―",
        "Delete Field",
    ]


def test_multi_select_menu(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    menu = tree.build_multi_select_menu()
    assert action_labels(menu) == [
        "Compare Selected", "Create Client Pages for Selected", "Copy Selected to...",
    ]


def test_stub_action_callback_invoked(qtbot):
    calls = []
    tree = ProjectTreePanel(on_stub_action=calls.append)
    qtbot.addWidget(tree)
    menu = tree.build_page_menu(tree.topLevelItem(0))
    find_action(menu, "Delete Page").trigger()
    assert calls == ["Delete Page"]


def test_menu_for_position_dispatches_by_kind(qtbot):
    tree = ProjectTreePanel(on_stub_action=lambda label: None)
    qtbot.addWidget(tree)
    page_item = tree.topLevelItem(0)
    rect = tree.visualItemRect(page_item)
    menu = tree.menu_for_position(rect.center())
    assert action_labels(menu)[0] == "Edit Properties"
```

- [ ] **Step 3: Run the tests, verify they fail**

Run: `pytest tests/ui/test_project_tree.py -v`
Expected: FAIL — `ProjectTreePanel() got an unexpected keyword argument 'on_stub_action'`, `build_page_menu` doesn't exist.

- [ ] **Step 4: Add the shared stub-action helper**

Both `ProjectTreePanel` (this task) and `MainWindow` (Task 5 onward) need the exact same "add a menu action that calls back with its own label" logic. Rather than defining it twice, it's a single free function both classes delegate to.

```python
# pgtp_editor/ui/_stub_action.py
"""Shared helper: a menu action wired to a not-yet-implemented callback.

Used by both ProjectTreePanel (context menus) and MainWindow (menu bar)
so the wiring pattern lives in exactly one place.
"""


def add_stub_action(menu, label, callback):
    action = menu.addAction(label)
    action.triggered.connect(lambda checked=False, l=label: callback(l))
    return action
```

- [ ] **Step 5: Implement the context-menu system in `ProjectTreePanel`**

```python
# pgtp_editor/ui/project_tree.py
# (add these imports at the top, alongside the existing ones)
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from pgtp_editor.ui._stub_action import add_stub_action


class ProjectTreePanel(QTreeWidget):
    def __init__(self, parent=None, on_stub_action=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._on_stub_action = on_stub_action or (lambda label: None)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._populate_placeholder()

    # ... _populate_placeholder, iter_detail_items, has_duplicate_table unchanged ...

    def _add_stub_action(self, menu, label):
        return add_stub_action(menu, label, self._on_stub_action)

    def build_page_menu(self, item):
        menu = QMenu(self)
        self._add_stub_action(menu, "Edit Properties")
        menu.addSeparator()
        self._add_stub_action(menu, "Copy")
        self._add_stub_action(menu, "Paste")
        self._add_stub_action(menu, "Duplicate")
        self._add_stub_action(menu, "Copy to Other Open Project...")
        menu.addSeparator()
        self._add_stub_action(menu, "Add Detail...")
        menu.addSeparator()
        self._add_stub_action(menu, "Create Client (Readonly) Page")
        self._add_stub_action(menu, "Compare This Page With...")
        menu.addSeparator()
        self._add_stub_action(menu, "Find Field Usages...")
        self._add_stub_action(menu, "Rename / Unify Captions...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Page")
        return menu

    def build_detail_menu(self, item):
        menu = QMenu(self)
        self._add_stub_action(menu, "Edit Properties")
        menu.addSeparator()
        self._add_stub_action(menu, "Cut")
        self._add_stub_action(menu, "Copy")
        self._add_stub_action(menu, "Paste")
        self._add_stub_action(menu, "Duplicate")
        self._add_stub_action(menu, "Move to Parent Page...")
        self._add_stub_action(menu, "Copy to Other Open Project...")
        menu.addSeparator()
        self._add_stub_action(menu, "Add Nested Detail...")
        menu.addSeparator()
        self._add_stub_action(menu, "Create Client (Readonly) Page")
        self._add_stub_action(menu, "Compare This Detail With...")
        if self.has_duplicate_table(item):
            self._add_stub_action(menu, "Compare with Other Instance...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Detail (+ nested)")
        return menu

    def build_field_menu(self, item):
        menu = QMenu(self)
        self._add_stub_action(menu, "Edit Caption / Hint / Short Caption")
        menu.addSeparator()
        self._add_stub_action(menu, "Find All Usages of This Field")
        self._add_stub_action(menu, "Unify Captions Across Pages...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Field")
        return menu

    def build_multi_select_menu(self):
        menu = QMenu(self)
        self._add_stub_action(menu, "Compare Selected")
        self._add_stub_action(menu, "Create Client Pages for Selected")
        self._add_stub_action(menu, "Copy Selected to...")
        return menu

    def menu_for_position(self, pos):
        if len(self.selectedItems()) > 1:
            return self.build_multi_select_menu()
        item = self.itemAt(pos)
        if item is None:
            return None
        kind = item.data(0, NODE_KIND_ROLE)
        if kind == "page":
            return self.build_page_menu(item)
        if kind == "detail":
            return self.build_detail_menu(item)
        if kind == "field":
            return self.build_field_menu(item)
        return None

    def _show_context_menu(self, pos):
        menu = self.menu_for_position(pos)
        if menu is not None:
            menu.exec(self.viewport().mapToGlobal(pos))
```

- [ ] **Step 6: Run the tests, verify they pass**

Run: `pytest tests/ui/test_project_tree.py -v`
Expected: all passed

- [ ] **Step 7: Add the shared stub slot to `MainWindow` and wire it into the tree**

```python
# pgtp_editor/ui/main_window.py — modify the ProjectTreePanel construction line
        self.project_tree = ProjectTreePanel(on_stub_action=self._not_implemented)
```

Add the method:

```python
    def _not_implemented(self, label):
        self.statusBar().showMessage(f"Not yet implemented: {label}", 5000)
```

- [ ] **Step 8: Write the failing test for the stub slot**

Append to `tests/ui/test_main_window.py`:

```python
def test_not_implemented_shows_status_message(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._not_implemented("Delete Page")
    assert window.statusBar().currentMessage() == "Not yet implemented: Delete Page"
```

- [ ] **Step 9: Run it, verify it fails, then passes after Step 7's code is in place**

Run: `pytest tests/ui/test_main_window.py -v`
Expected: FAIL first (before Step 7 is saved) with `AttributeError`, then PASS once `_not_implemented` exists.

- [ ] **Step 10: Manually verify**

Run: `python -m pgtp_editor.main`
Expected: right-clicking "Equipment" shows the Page menu; right-clicking "Attachments" (under Equipment) shows the Detail menu *including* "Compare with Other Instance..."; right-clicking "Sub-item" shows the Detail menu *without* that item; right-clicking a field leaf shows the Field menu; clicking any action shows a "Not yet implemented: ..." message in the status bar for 5 seconds. Ctrl-click two Page items and right-click to see the multi-select menu.

- [ ] **Step 11: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add right-click context menus for Page/Detail/Field/multi-select nodes"
```

---

## Task 5: File menu

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Create: `tests/ui/test_menus.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_menus.py
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import action_labels, find_action, find_top_menu


def test_file_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    assert file_menu is not None
    labels = action_labels(file_menu)
    assert labels == [
        "New Project", "Open...", "Open Recent", "Save", "Save As...", "Close", "―", "Exit",
    ]


def test_open_recent_is_an_empty_submenu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    open_recent_action = find_action(file_menu, "Open Recent")
    open_recent_menu = open_recent_action.menu()
    assert open_recent_menu is not None
    assert open_recent_menu.actions() == []


def test_exit_action_closes_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    file_menu = find_top_menu(window, "File")
    find_action(file_menu, "Exit").trigger()
    assert window.isVisible() is False


def test_other_file_actions_show_stub_message(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    find_action(file_menu, "New Project").trigger()
    assert window.statusBar().currentMessage() == "Not yet implemented: New Project"
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `pytest tests/ui/test_menus.py -v`
Expected: FAIL — `find_top_menu` returns `None` (no menu bar built yet).

- [ ] **Step 3: Build the File menu in `MainWindow`**

```python
# pgtp_editor/ui/main_window.py — add to __init__, after the docking layout is set up
        self._build_menu_bar()
```

Add the import (same shared helper `ProjectTreePanel` already uses, from Task 4) and the methods:

```python
# pgtp_editor/ui/main_window.py — add alongside the existing imports
from pgtp_editor.ui._stub_action import add_stub_action
```

```python
    def _build_menu_bar(self):
        self._build_file_menu()

    def _build_file_menu(self):
        menu = self.menuBar().addMenu("File")
        self._add_stub_action(menu, "New Project")
        self._add_stub_action(menu, "Open...")
        menu.addMenu("Open Recent")
        self._add_stub_action(menu, "Save")
        self._add_stub_action(menu, "Save As...")
        self._add_stub_action(menu, "Close")
        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.close)

    def _add_stub_action(self, menu, label):
        return add_stub_action(menu, label, self._not_implemented)
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `pytest tests/ui/test_menus.py -v`
Expected: all passed

- [ ] **Step 5: Manually verify**

Run: `python -m pgtp_editor.main`
Expected: a "File" menu with the items above; "Open Recent" is present but expands to nothing; "Exit" actually closes the window; everything else shows the status-bar stub message.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add File menu"
```

---

## Task 6: Edit menu

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_menus.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_menus.py`:

```python
def test_edit_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    assert action_labels(edit_menu) == [
        "Undo", "Redo", "―",
        "Cut", "Copy", "Paste", "Delete", "―",
        "Find...", "Find & Replace...", "―",
        "Preferences...",
    ]


def test_find_and_replace_has_ctrl_h_shortcut(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    edit_menu = find_top_menu(window, "Edit")
    action = find_action(edit_menu, "Find & Replace...")
    assert action.shortcut().toString() == "Ctrl+H"
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `pytest tests/ui/test_menus.py -v`
Expected: FAIL — `find_top_menu(window, "Edit")` returns `None`.

- [ ] **Step 3: Build the Edit menu**

```python
# pgtp_editor/ui/main_window.py
    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()

    def _build_edit_menu(self):
        menu = self.menuBar().addMenu("Edit")
        self._add_stub_action(menu, "Undo")
        self._add_stub_action(menu, "Redo")
        menu.addSeparator()
        self._add_stub_action(menu, "Cut")
        self._add_stub_action(menu, "Copy")
        self._add_stub_action(menu, "Paste")
        self._add_stub_action(menu, "Delete")
        menu.addSeparator()
        self._add_stub_action(menu, "Find...")
        find_replace = self._add_stub_action(menu, "Find & Replace...")
        find_replace.setShortcut("Ctrl+H")
        menu.addSeparator()
        self._add_stub_action(menu, "Preferences...")
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `pytest tests/ui/test_menus.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add Edit menu"
```

---

## Task 7: View menu — real dock/tab visibility toggles

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_menus.py`

Unlike every other menu in this plan, View's checkable items get **real** behavior — toggling visibility of already-built panels is pure UI wiring, no model needed, and it's the main thing worth reviewing about this menu.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_menus.py`:

```python
def test_view_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert action_labels(view_menu) == [
        "Project Tree", "Properties Panel", "Audit/Problems Panel", "Raw XML Panel", "―",
        "Expand All", "Collapse All",
    ]


def test_view_menu_default_checked_states(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    assert find_action(view_menu, "Project Tree").isChecked() is True
    assert find_action(view_menu, "Properties Panel").isChecked() is True
    assert find_action(view_menu, "Audit/Problems Panel").isChecked() is True
    assert find_action(view_menu, "Raw XML Panel").isChecked() is False


def test_toggling_project_tree_hides_dock(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.tree_dock.isVisible() is True
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Project Tree").trigger()
    assert window.tree_dock.isVisible() is False


def test_toggling_audit_panel_hides_dock(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.audit_dock.isVisible() is True
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Audit/Problems Panel").trigger()
    assert window.audit_dock.isVisible() is False


def test_toggling_properties_panel_hides_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Properties Panel").trigger()
    assert window.center_stage.isTabVisible(window.center_stage.properties_tab_index) is False


def test_toggling_raw_xml_panel_shows_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Raw XML Panel").trigger()
    assert window.center_stage.isTabVisible(window.center_stage.raw_xml_tab_index) is True


def test_expand_all_shows_stub_message(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    find_action(view_menu, "Expand All").trigger()
    assert window.statusBar().currentMessage() == "Not yet implemented: Expand All"
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `pytest tests/ui/test_menus.py -v`
Expected: FAIL — no "View" menu yet.

- [ ] **Step 3: Build the View menu with real toggle wiring**

```python
# pgtp_editor/ui/main_window.py
    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()

    def _build_view_menu(self):
        menu = self.menuBar().addMenu("View")

        tree_action = menu.addAction("Project Tree")
        tree_action.setCheckable(True)
        tree_action.setChecked(True)
        tree_action.toggled.connect(self.tree_dock.setVisible)

        properties_action = menu.addAction("Properties Panel")
        properties_action.setCheckable(True)
        properties_action.setChecked(True)
        properties_action.toggled.connect(self.center_stage.set_properties_tab_visible)

        audit_action = menu.addAction("Audit/Problems Panel")
        audit_action.setCheckable(True)
        audit_action.setChecked(True)
        audit_action.toggled.connect(self.audit_dock.setVisible)

        raw_xml_action = menu.addAction("Raw XML Panel")
        raw_xml_action.setCheckable(True)
        raw_xml_action.setChecked(False)
        raw_xml_action.toggled.connect(self.center_stage.set_raw_xml_tab_visible)

        menu.addSeparator()
        self._add_stub_action(menu, "Expand All")
        self._add_stub_action(menu, "Collapse All")
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `pytest tests/ui/test_menus.py -v`
Expected: all passed

- [ ] **Step 5: Manually verify**

Run: `python -m pgtp_editor.main`
Expected: unchecking "Project Tree" hides the left dock; unchecking "Audit/Problems Panel" hides the bottom dock; unchecking "Properties Panel" removes that tab from the center stage; checking "Raw XML Panel" makes a 4th tab appear.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add View menu with real dock/tab visibility toggles"
```

---

## Task 8: Diff/Merge menu

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_menus.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_menus.py`:

```python
def test_diff_merge_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Diff / Merge")
    assert action_labels(menu) == [
        "Compare / Merge Two Files...", "―",
        "Next Difference", "Prev Difference", "Apply Changes to Target",
    ]
```

- [ ] **Step 2: Run it, verify it fails**

Run: `pytest tests/ui/test_menus.py -v`
Expected: FAIL — no "Diff / Merge" menu yet.

- [ ] **Step 3: Build the Diff/Merge menu**

```python
# pgtp_editor/ui/main_window.py
    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_diff_merge_menu()

    def _build_diff_merge_menu(self):
        menu = self.menuBar().addMenu("Diff / Merge")
        self._add_stub_action(menu, "Compare / Merge Two Files...")
        menu.addSeparator()
        self._add_stub_action(menu, "Next Difference")
        self._add_stub_action(menu, "Prev Difference")
        self._add_stub_action(menu, "Apply Changes to Target")
```

- [ ] **Step 4: Run it, verify it passes**

Run: `pytest tests/ui/test_menus.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add Diff/Merge menu"
```

---

## Task 9: Tools menu

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_menus.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_menus.py`:

```python
def test_tools_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Tools")
    assert action_labels(menu) == [
        "Create Client (Readonly) Page...", "Move/Copy Detail...", "―",
        "Manage Captions...", "―",
        "Find Reused Tables...", "―",
        "Validate Project",
    ]
```

- [ ] **Step 2: Run it, verify it fails**

Run: `pytest tests/ui/test_menus.py -v`
Expected: FAIL — no "Tools" menu yet.

- [ ] **Step 3: Build the Tools menu**

```python
# pgtp_editor/ui/main_window.py
    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_diff_merge_menu()
        self._build_tools_menu()

    def _build_tools_menu(self):
        menu = self.menuBar().addMenu("Tools")
        self._add_stub_action(menu, "Create Client (Readonly) Page...")
        self._add_stub_action(menu, "Move/Copy Detail...")
        menu.addSeparator()
        self._add_stub_action(menu, "Manage Captions...")
        menu.addSeparator()
        self._add_stub_action(menu, "Find Reused Tables...")
        menu.addSeparator()
        self._add_stub_action(menu, "Validate Project")
```

- [ ] **Step 4: Run it, verify it passes**

Run: `pytest tests/ui/test_menus.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add Tools menu"
```

---

## Task 10: Generation menu

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_menus.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_menus.py`:

```python
def test_generation_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Generation")
    assert action_labels(menu) == [
        "Locate PHP Generator Executable...", "―",
        "Generate PHP...", "―",
        "Open Output Folder",
    ]
```

- [ ] **Step 2: Run it, verify it fails**

Run: `pytest tests/ui/test_menus.py -v`
Expected: FAIL — no "Generation" menu yet.

- [ ] **Step 3: Build the Generation menu**

```python
# pgtp_editor/ui/main_window.py
    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_diff_merge_menu()
        self._build_tools_menu()
        self._build_generation_menu()

    def _build_generation_menu(self):
        menu = self.menuBar().addMenu("Generation")
        self._add_stub_action(menu, "Locate PHP Generator Executable...")
        menu.addSeparator()
        self._add_stub_action(menu, "Generate PHP...")
        menu.addSeparator()
        self._add_stub_action(menu, "Open Output Folder")
```

- [ ] **Step 4: Run it, verify it passes**

Run: `pytest tests/ui/test_menus.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add Generation menu"
```

---

## Task 11: Help menu and About dialog

**Files:**
- Create: `pgtp_editor/ui/about.py`
- Modify: `pgtp_editor/ui/main_window.py`
- Create: `tests/ui/test_about.py`
- Modify: `tests/ui/test_menus.py`

The About dialog's credits text is fully specified by spec §9 — this is real content, not a stub, since it costs nothing to get right now and there's nothing left to design.

- [ ] **Step 1: Write the failing test for the credits text**

```python
# tests/ui/test_about.py
from pgtp_editor.ui.about import ABOUT_TEXT


def test_credits_mention_all_three_projects():
    assert "BoomslangXML" in ABOUT_TEXT
    assert "QCodeEditor" in ABOUT_TEXT
    assert "SuperNano" in ABOUT_TEXT


def test_credits_mention_license():
    assert "GPL-3.0" in ABOUT_TEXT
```

- [ ] **Step 2: Run it, verify it fails**

Run: `pytest tests/ui/test_about.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.ui.about'`

- [ ] **Step 3: Write the About module**

```python
# pgtp_editor/ui/about.py
from PySide6.QtWidgets import QMessageBox

ABOUT_TEXT = (
    "<h3>PGTP Editor</h3>"
    "<p>A companion editor for SQL Maestro PostgreSQL PHP Generator "
    "<code>.pgtp</code> project files. Licensed under GPL-3.0.</p>"
    "<p><b>Credits:</b></p>"
    "<ul>"
    "<li><a href=\"https://github.com/driscollis/BoomslangXML\">BoomslangXML</a> "
    "(Mike Driscoll) &mdash; prior art for the tree-based XML editing approach.</li>"
    "<li><a href=\"https://github.com/luchko/QCodeEditor\">QCodeEditor</a> "
    "(luchko, MIT License) &mdash; the code-editor widget is a PySide6 port "
    "of this project's approach.</li>"
    "<li><a href=\"https://github.com/LcfherShell/SuperNano\">SuperNano</a> "
    "(LcfherShell, GPL-3.0) &mdash; evaluated during design; not used as a "
    "runtime dependency.</li>"
    "</ul>"
)


def show_about_dialog(parent):
    QMessageBox.about(parent, "About PGTP Editor", ABOUT_TEXT)
```

- [ ] **Step 4: Run it, verify it passes**

Run: `pytest tests/ui/test_about.py -v`
Expected: 2 passed

- [ ] **Step 5: Write the failing test for the Help menu**

Append to `tests/ui/test_menus.py`:

```python
def test_help_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    menu = find_top_menu(window, "Help")
    assert action_labels(menu) == ["Documentation", "About"]
```

- [ ] **Step 6: Run it, verify it fails**

Run: `pytest tests/ui/test_menus.py -v`
Expected: FAIL — no "Help" menu yet.

- [ ] **Step 7: Build the Help menu**

```python
# pgtp_editor/ui/main_window.py — add the import
from pgtp_editor.ui.about import show_about_dialog
```

```python
    def _build_menu_bar(self):
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_diff_merge_menu()
        self._build_tools_menu()
        self._build_generation_menu()
        self._build_help_menu()

    def _build_help_menu(self):
        menu = self.menuBar().addMenu("Help")
        self._add_stub_action(menu, "Documentation")
        about_action = menu.addAction("About")
        about_action.triggered.connect(lambda: show_about_dialog(self))
```

- [ ] **Step 8: Run it, verify it passes**

Run: `pytest tests/ui/test_menus.py -v`
Expected: all passed

- [ ] **Step 9: Manually verify**

Run: `python -m pgtp_editor.main`
Expected: Help → About opens a dialog listing all three credited projects and the GPL-3.0 license. Close it. Help → Documentation shows the status-bar stub.

- [ ] **Step 10: Commit**

```bash
git add pgtp_editor tests
git commit -m "feat: add Help menu and About dialog with OSS credits"
```

---

## Task 12: Full-shell smoke test, README, and final review pass

**Files:**
- Modify: `tests/ui/test_menus.py`
- Modify: `README.md`

- [ ] **Step 1: Write a whole-menu-bar smoke test**

Append to `tests/ui/test_menus.py` (add `all_top_level_menu_titles` to the existing `_menu_helpers` import line):

```python
from tests.ui._menu_helpers import action_labels, all_top_level_menu_titles, find_action, find_top_menu


def test_all_top_level_menus_present_in_order(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    titles = all_top_level_menu_titles(window)
    assert titles == ["File", "Edit", "View", "Diff / Merge", "Tools", "Generation", "Help"]
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest tests -v`
Expected: all 42 tests across every task in this plan pass.

- [ ] **Step 3: Update README with dev setup and run instructions**

```markdown
# pgtp_editor
Complementary editor for pgtp files

## Development setup

    pip install -e ".[dev]"

## Running the app

    python -m pgtp_editor.main

## Running tests

    pytest
```

- [ ] **Step 4: Full manual walkthrough**

Run: `python -m pgtp_editor.main`

Walk through: every top-level menu opens and shows the items reviewed task-by-task above; every right-click context menu on Page/Detail/Field nodes (and multi-select) shows the right items; View menu toggles work; Help → About shows credits; File → Exit closes the window. This is the full shell — confirm it matches [docs/superpowers/specs/2026-07-11-pgtp-editor-design.md](../specs/2026-07-11-pgtp-editor-design.md) §5.1-5.3 before considering this phase done.

- [ ] **Step 5: Commit**

```bash
git add tests README.md
git commit -m "test: add full menu-bar smoke test, document dev setup in README"
```

---

## What's deliberately not in this plan

Per the agile/incremental approach: no `.pgtp` parsing (`model/`), no differ (`diff/`), no mutating operations (`ops/`), no validation (`validate/`), no PHP Generator subprocess wrapper (`external/`), no Raw XML code-editor widget content (the tab exists and toggles, but is an empty `QWidget` — the real `QPlainTextEdit`-based editor from spec §4.3 is its own future phase), and no Preferences dialog (referenced by several stub actions but not built). Every one of these is a future phase's plan, built against the seams this plan establishes (the `_not_implemented` stub slot gets replaced action-by-action with real handlers; `PLACEHOLDER_PROJECT` gets replaced wholesale by the real model).
