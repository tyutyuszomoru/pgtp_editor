# Diff/Merge Viewer UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Diff/Merge viewer UI sub-project: three comparison entry points (file-level, page-level, detail-level) that all converge on a shared `DiffMergePanel` widget showing a read-only change-list tree and per-difference detail view, plus Next/Prev Difference navigation — consuming the already-implemented `diff_project`/`compare_block`/`Difference` engine with no write-back to disk.

**Architecture:** A new Qt-free `pgtp_editor/diff/resolve.py` module (`ResolutionError` + `resolve_path`) resolves a Detail-level comparison's target node by walking a path of identity segments, mirroring the differ's own per-level matching rules. A new `pgtp_editor/ui/diff_merge_panel.py` widget (`DiffMergePanel`) builds a `QTreeWidget` change-list tree from a flat `list[Difference]` (deduplicating shared path prefixes into intermediate group nodes), plus a `QStackedWidget`-based detail view with three mutually exclusive renderings (attribute change, whole-subtree added/removed, event unified diff), plus checkbox selection state and next/prev navigation. `main_window.py` and `project_tree.py` gain real handlers for the three entry points, replacing their current stub wiring, and `center_stage.py` is extended with a small accessor so the real `DiffMergePanel` instance replaces its placeholder `QWidget` at `diff_merge_tab_index`. `project_tree.py` also gains storage of the actual `PageNode`/`DetailNode` object on each tree item (it currently stores only `node_kind` and `table_name`), since building a Detail's `path` requires walking real ancestor attributes (`file_name`, `table_name`, `attrib.get("caption")`), not just display strings.

**Tech Stack:** Python 3.10+, PySide6 (Qt widgets: `QTreeWidget`, `QStackedWidget`, `QPlainTextEdit`, `QSplitter`, `QFileDialog`, `QMessageBox`), lxml (via existing `pgtp_editor.model.parser`), stdlib `difflib`, pytest + pytest-qt.

---

## Before you start

- Work in this worktree, on this branch, exactly as already checked out — do not create a new worktree.
- Run tests with `pytest` from the repo root (matches the existing test suite's invocation; no `QT_QPA_PLATFORM` override exists anywhere in this repo today, so don't invent one — if a test window pops up visibly during a local run, that's expected on this platform and does not indicate a problem).
- `sample/dev_Ferrara.pgtp` and `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp` already exist on disk in this worktree (gitignored — confirmed present). The two real-sample-file integration tests in Task 11 will run against them directly; they are not skipped in this environment.
- Commit after every task (not just at the end) — this plan is written so each task leaves the repo in a fully passing state.

---

### Task 1: `ResolutionError` dataclass

**Files:**
- Create: `pgtp_editor/diff/resolve.py`
- Test: `tests/diff/test_resolve.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/diff/test_resolve.py
from pgtp_editor.diff.resolve import ResolutionError


def test_resolution_error_holds_segment_index_and_message():
    error = ResolutionError(segment_index=0, message="no Page named 'missing_page'")
    assert error.segment_index == 0
    assert error.message == "no Page named 'missing_page'"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/diff/test_resolve.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.diff.resolve'` (or `ImportError`).

- [ ] **Step 3: Write minimal implementation**

```python
# pgtp_editor/diff/resolve.py
"""resolve_path(project, path) walks a ProjectModel down a path of identity
segments (matching Difference.path's shape — see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-viewer-ui-design.md
§3.3-3.4) to find the PageNode/DetailNode a Detail-level comparison request
is pointing at. Pure logic — no Qt, mirrors differ.py's own per-level
matching rules rather than re-deriving them.
"""
from __future__ import annotations

from dataclasses import dataclass

from pgtp_editor.model.nodes import DetailNode, PageNode, ProjectModel


@dataclass
class ResolutionError:
    segment_index: int
    message: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/diff/test_resolve.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/resolve.py tests/diff/test_resolve.py
git commit -m "feat(diff): add ResolutionError dataclass"
```

---

### Task 2: `resolve_path` — depth-1 (Page-only) success case

**Files:**
- Modify: `pgtp_editor/diff/resolve.py`
- Test: `tests/diff/test_resolve.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/diff/test_resolve.py`:

```python
from pgtp_editor.model.nodes import PageNode, ProjectModel
from pgtp_editor.diff.resolve import resolve_path


def make_page(file_name, **extra_attrib):
    attrib = {"fileName": file_name}
    attrib.update(extra_attrib)
    return PageNode(identity=file_name, attrib=attrib)


def test_resolve_path_finds_page_at_depth_one():
    page = make_page("development_equipment", tableName="pr.equipment", caption="Equipment")
    project = ProjectModel(pages=[page])

    result = resolve_path(project, ["development_equipment"])

    assert result is page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/diff/test_resolve.py::test_resolve_path_finds_page_at_depth_one -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_path'`

- [ ] **Step 3: Write minimal implementation**

```python
# pgtp_editor/diff/resolve.py — add below ResolutionError
def resolve_path(project: ProjectModel, path: list[str]) -> "PageNode | DetailNode | ResolutionError":
    """Walk `project` down `path` (a list of identity segments matching
    Difference.path's shape, per spec §3.3): path[0] is a top-level Page's
    file_name, path[1:] are "tableName/caption" Detail segments each scoped
    to their immediate parent's .details only.

    Returns the resolved PageNode (len(path) == 1) or DetailNode
    (otherwise) on success, or a ResolutionError naming the first
    unresolvable segment on failure.
    """
    page = next((p for p in project.pages if p.file_name == path[0]), None)
    if page is None:
        return ResolutionError(
            segment_index=0,
            message=f"no Page named '{path[0]}'",
        )

    current = page
    for index, segment in enumerate(path[1:], start=1):
        table_name, _, caption = segment.partition("/")
        match = next(
            (
                d for d in current.details
                if d.table_name == table_name and d.attrib.get("caption") == caption
            ),
            None,
        )
        if match is None:
            resolved_prefix = "/".join(path[:index])
            return ResolutionError(
                segment_index=index,
                message=(
                    f"no Detail matching (tableName='{table_name}', caption='{caption}') "
                    f"under {resolved_prefix}"
                ),
            )
        current = match

    return current
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/diff/test_resolve.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/resolve.py tests/diff/test_resolve.py
git commit -m "feat(diff): resolve_path finds Page at depth 1"
```

---

### Task 3: `resolve_path` — depth-1 not-found case

**Files:**
- Modify: `tests/diff/test_resolve.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_resolve_path_page_not_found_at_depth_one():
    project = ProjectModel(pages=[make_page("existing_page")])

    result = resolve_path(project, ["missing_page"])

    assert isinstance(result, ResolutionError)
    assert result.segment_index == 0
    assert result.message == "no Page named 'missing_page'"
```

- [ ] **Step 2: Run test to verify it passes (implementation already covers this)**

Run: `pytest tests/diff/test_resolve.py -v`
Expected: PASS (3 passed) — Task 2's implementation already handles this branch; this step locks the behavior in with an explicit regression test.

- [ ] **Step 3: Commit**

```bash
git add tests/diff/test_resolve.py
git commit -m "test(diff): cover resolve_path not-found at depth 1"
```

---

### Task 4: `resolve_path` — depth-2+ (Detail) success case

**Files:**
- Modify: `tests/diff/test_resolve.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
from pgtp_editor.model.nodes import DetailNode


def make_detail(table_name, caption, details=None):
    return DetailNode(
        identity=f"{table_name}/{caption}",
        attrib={"tableName": table_name, "caption": caption},
        details=details or [],
    )


def test_resolve_path_finds_detail_at_depth_two():
    sub_item = make_detail("pr.attachment", "Sub-item")
    page = make_page("development_equipment", tableName="pr.equipment")
    page.details = [sub_item]
    project = ProjectModel(pages=[page])

    result = resolve_path(project, ["development_equipment", "pr.attachment/Sub-item"])

    assert result is sub_item


def test_resolve_path_finds_nested_detail_at_depth_three():
    level2 = make_detail("pr.level2", "Level2")
    level1 = make_detail("pr.level1", "Level1", details=[level2])
    page = make_page("top_page")
    page.details = [level1]
    project = ProjectModel(pages=[page])

    result = resolve_path(
        project,
        ["top_page", "pr.level1/Level1", "pr.level2/Level2"],
    )

    assert result is level2
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/diff/test_resolve.py -v`
Expected: PASS (5 passed) — Task 2's implementation already handles multi-segment paths since the loop is general; this locks the behavior in explicitly.

- [ ] **Step 3: Commit**

```bash
git add tests/diff/test_resolve.py
git commit -m "test(diff): cover resolve_path at depth 2 and 3"
```

---

### Task 5: `resolve_path` — not-found at deeper segments, and first-match-wins for duplicate siblings

**Files:**
- Modify: `tests/diff/test_resolve.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_resolve_path_detail_not_found_at_depth_two():
    page = make_page("development_equipment")
    page.details = [make_detail("pr.attachment", "Sub-item")]
    project = ProjectModel(pages=[page])

    result = resolve_path(
        project,
        ["development_equipment", "pr.r_characteristic/Attachment"],
    )

    assert isinstance(result, ResolutionError)
    assert result.segment_index == 1
    assert result.message == (
        "no Detail matching (tableName='pr.r_characteristic', caption='Attachment') "
        "under development_equipment"
    )


def test_resolve_path_detail_not_found_at_depth_three_names_full_resolved_prefix():
    level1 = make_detail("pr.level1", "Level1", details=[])
    page = make_page("top_page")
    page.details = [level1]
    project = ProjectModel(pages=[page])

    result = resolve_path(
        project,
        ["top_page", "pr.level1/Level1", "pr.level2/Level2"],
    )

    assert isinstance(result, ResolutionError)
    assert result.segment_index == 2
    assert result.message == (
        "no Detail matching (tableName='pr.level2', caption='Level2') "
        "under top_page/pr.level1/Level1"
    )


def test_resolve_path_duplicate_sibling_details_first_match_wins():
    first = make_detail("pr.operation", "Operation")
    first.attrib["ability"] = "first"
    second = make_detail("pr.operation", "Operation")
    second.attrib["ability"] = "second"
    page = make_page("shared_page")
    page.details = [first, second]
    project = ProjectModel(pages=[page])

    result = resolve_path(project, ["shared_page", "pr.operation/Operation"])

    assert result is first
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/diff/test_resolve.py -v`
Expected: PASS (8 passed) — Task 2's `next(...)` lookup already returns the first match and already produces a `ResolutionError` naming `resolved_prefix` at any depth; this task locks in both behaviors with explicit assertions per spec §3.4's requirement that failures name the specific unresolvable segment and duplicate siblings resolve first-match-wins (not positional pairing).

- [ ] **Step 3: Commit**

```bash
git add tests/diff/test_resolve.py
git commit -m "test(diff): cover resolve_path not-found at depth 2-3 and duplicate-sibling first-match-wins"
```

---

### Task 6: `DiffMergePanel` — change-list tree hierarchy from shared path prefixes

**Files:**
- Create: `pgtp_editor/ui/diff_merge_panel.py`
- Test: `tests/ui/test_diff_merge_panel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_diff_merge_panel.py
from pgtp_editor.diff.records import Difference
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel


def make_diff(path, node_kind, kind, attribute=None, old_value=None, new_value=None, ambiguous=False):
    return Difference(
        kind=kind,
        path=path,
        node_kind=node_kind,
        attribute=attribute,
        old_value=old_value,
        new_value=new_value,
        ambiguous=ambiguous,
    )


def test_show_differences_builds_shared_prefix_hierarchy(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(
            ["development_equipment", "pr.r_characteristic/Attachment", "caption"],
            node_kind="detail", kind="changed", attribute="caption",
            old_value="Old", new_value="New",
        ),
        make_diff(
            ["development_equipment", "pr.r_characteristic/Attachment", "ability"],
            node_kind="detail", kind="changed", attribute="ability",
            old_value="view", new_value="insert",
        ),
    ]

    panel.show_differences(diffs)

    assert panel.tree.topLevelItemCount() == 1
    page_item = panel.tree.topLevelItem(0)
    assert page_item.text(0) == "development_equipment"
    assert page_item.childCount() == 1
    detail_item = page_item.child(0)
    assert detail_item.text(0) == "pr.r_characteristic/Attachment"
    assert detail_item.childCount() == 2


def test_show_differences_clears_previous_content(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]

    panel.show_differences(diffs)
    assert panel.tree.topLevelItemCount() == 1

    panel.show_differences(diffs)
    assert panel.tree.topLevelItemCount() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.ui.diff_merge_panel'`

- [ ] **Step 3: Write minimal implementation**

```python
# pgtp_editor/ui/diff_merge_panel.py
"""DiffMergePanel: the shared viewer for all three Diff/Merge comparison
entry points (file-level, page-level, detail-level). Populates the
existing empty "Diff / Merge" center-stage tab with a change-list tree
(left) and a detail view (right). Read-only — no write-back to disk (see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-viewer-ui-design.md).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

DIFFERENCE_ROLE = Qt.ItemDataRole.UserRole


class DiffMergePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.tree)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter)

    def show_differences(self, differences: list) -> None:
        """Build the change-list tree fresh from `differences`, clearing
        any previous content — one comparison session at a time."""
        self.tree.clear()
        items_by_prefix: dict[tuple, QTreeWidgetItem] = {}

        for diff in differences:
            *prefix_segments, _ = diff.path
            parent = None
            accumulated: tuple = ()
            for segment in prefix_segments:
                accumulated += (segment,)
                item = items_by_prefix.get(accumulated)
                if item is None:
                    item = QTreeWidgetItem([segment])
                    if parent is not None:
                        parent.addChild(item)
                    else:
                        self.tree.addTopLevelItem(item)
                    items_by_prefix[accumulated] = item
                parent = item

            leaf = QTreeWidgetItem([leaf_label(diff)])
            leaf.setData(0, DIFFERENCE_ROLE, diff)
            if parent is not None:
                parent.addChild(leaf)
            else:
                self.tree.addTopLevelItem(leaf)


def leaf_label(diff) -> str:
    if diff.attribute is not None:
        return f"{diff.attribute}: {diff.kind}"
    return f"{diff.path[-1]}: {diff.kind}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/diff_merge_panel.py tests/ui/test_diff_merge_panel.py
git commit -m "feat(ui): add DiffMergePanel change-list tree with shared-prefix dedup"
```

---

### Task 7: `leaf_label` — full formatting table coverage

**Files:**
- Modify: `tests/ui/test_diff_merge_panel.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
from pgtp_editor.ui.diff_merge_panel import leaf_label


def test_leaf_label_attribute_changed():
    diff = make_diff(
        ["development_equipment", "pr.attachment/Sub-item", "caption"],
        node_kind="detail", kind="changed", attribute="caption",
        old_value="Old", new_value="New",
    )
    assert leaf_label(diff) == "caption: changed"


def test_leaf_label_event_added_uses_last_path_segment():
    diff = make_diff(
        ["development_equipment", "OnRowProcess"],
        node_kind="event", kind="added", attribute=None,
        old_value=None, new_value=object(),
    )
    assert leaf_label(diff) == "OnRowProcess: added"


def test_leaf_label_detail_removed_uses_last_path_segment():
    diff = make_diff(
        ["development_equipment", "pr.attachment/Sub-item"],
        node_kind="detail", kind="removed", attribute=None,
        old_value=object(), new_value=None,
    )
    assert leaf_label(diff) == "pr.attachment/Sub-item: removed"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: PASS — Task 6's `leaf_label` implementation already covers every row of spec §3.6's formatting table; this task locks each case in with its own explicit test.

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_diff_merge_panel.py
git commit -m "test(ui): cover full leaf_label formatting table"
```

---

### Task 8: Checkboxes (default unchecked) and ambiguous marker

**Files:**
- Modify: `pgtp_editor/ui/diff_merge_panel.py`
- Modify: `tests/ui/test_diff_merge_panel.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_diff_merge_panel.py`:

```python
def test_leaf_items_are_checkable_and_unchecked_by_default(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]

    panel.show_differences(diffs)

    page_item = panel.tree.topLevelItem(0)
    leaf = page_item.child(0)
    assert bool(leaf.flags() & Qt.ItemFlag.ItemIsUserCheckable)
    assert leaf.checkState(0) == Qt.CheckState.Unchecked


def test_group_prefix_items_are_not_checkable(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]

    panel.show_differences(diffs)

    page_item = panel.tree.topLevelItem(0)
    assert not bool(page_item.flags() & Qt.ItemFlag.ItemIsUserCheckable)


def test_ambiguous_leaf_gets_warning_marker(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(
            ["page_a", "pr.operation/Operation", "caption"],
            node_kind="detail", kind="changed", attribute="caption",
            old_value="Old", new_value="New", ambiguous=True,
        )
    ]

    panel.show_differences(diffs)

    leaf = panel.tree.topLevelItem(0).child(0).child(0)
    assert leaf.text(0) == "⚠ caption: changed"


def test_non_ambiguous_leaf_has_no_marker(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption")]

    panel.show_differences(diffs)

    leaf = panel.tree.topLevelItem(0).child(0)
    assert leaf.text(0) == "caption: changed"


def test_group_prefix_items_not_marked_even_if_all_children_ambiguous(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(
            ["page_a", "pr.operation/Operation", "caption"],
            node_kind="detail", kind="changed", attribute="caption",
            ambiguous=True,
        )
    ]

    panel.show_differences(diffs)

    detail_group_item = panel.tree.topLevelItem(0).child(0)
    assert detail_group_item.text(0) == "pr.operation/Operation"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: FAIL on the checkbox and ambiguous-marker tests (leaves currently have no checkable flag and `leaf_label` doesn't prepend the marker).

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/diff_merge_panel.py`:

```python
def leaf_label(diff) -> str:
    if diff.attribute is not None:
        label = f"{diff.attribute}: {diff.kind}"
    else:
        label = f"{diff.path[-1]}: {diff.kind}"
    return f"⚠ {label}" if diff.ambiguous else label
```

And in `show_differences`, replace the leaf-construction block:

```python
            leaf = QTreeWidgetItem([leaf_label(diff)])
            leaf.setData(0, DIFFERENCE_ROLE, diff)
            leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            leaf.setCheckState(0, Qt.CheckState.Unchecked)
            if parent is not None:
                parent.addChild(leaf)
            else:
                self.tree.addTopLevelItem(leaf)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/diff_merge_panel.py tests/ui/test_diff_merge_panel.py
git commit -m "feat(ui): add leaf checkboxes (default unchecked) and ambiguous marker"
```

---

### Task 9: Detail view — three mutually exclusive renderings

**Files:**
- Modify: `pgtp_editor/ui/diff_merge_panel.py`
- Modify: `tests/ui/test_diff_merge_panel.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_diff_merge_panel.py`:

```python
from pgtp_editor.model.nodes import DetailNode, EventNode


def test_selecting_attribute_changed_leaf_shows_old_and_new(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diff = make_diff(
        ["page_a", "caption"], node_kind="page", kind="changed",
        attribute="caption", old_value="Old Caption", new_value="New Caption",
    )
    panel.show_differences([diff])

    leaf = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(leaf)

    assert panel.detail_stack.currentWidget() is panel.attribute_view
    assert panel.attribute_old_label.text() == "Old: Old Caption"
    assert panel.attribute_new_label.text() == "New: New Caption"


def test_selecting_whole_subtree_added_leaf_shows_attrib_table(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    detail = DetailNode(identity="d1", attrib={"tableName": "pr.attachment", "caption": "Sub-item"})
    diff = make_diff(
        ["page_a", "pr.attachment/Sub-item"], node_kind="detail", kind="added",
        attribute=None, old_value=None, new_value=detail,
    )
    panel.show_differences([diff])

    leaf = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(leaf)

    assert panel.detail_stack.currentWidget() is panel.subtree_view
    assert panel.subtree_table.rowCount() == 2
    values = {
        panel.subtree_table.item(row, 0).text(): panel.subtree_table.item(row, 1).text()
        for row in range(panel.subtree_table.rowCount())
    }
    assert values == {"tableName": "pr.attachment", "caption": "Sub-item"}


def test_selecting_event_text_changed_leaf_shows_unified_diff(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diff = make_diff(
        ["page_a", "OnRowProcess"], node_kind="event", kind="changed",
        attribute=None, old_value="echo 'old';", new_value="echo 'new';",
    )
    panel.show_differences([diff])

    leaf = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(leaf)

    assert panel.detail_stack.currentWidget() is panel.event_diff_view
    text = panel.event_diff_text.toPlainText()
    assert "-echo 'old';" in text
    assert "+echo 'new';" in text


def test_selecting_group_node_clears_detail_view(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diff = make_diff(
        ["page_a", "pr.attachment/Sub-item", "caption"], node_kind="detail",
        kind="changed", attribute="caption", old_value="Old", new_value="New",
    )
    panel.show_differences([diff])

    leaf = panel.tree.topLevelItem(0).child(0).child(0)
    panel.tree.setCurrentItem(leaf)
    assert panel.detail_stack.currentWidget() is panel.attribute_view

    group_item = panel.tree.topLevelItem(0).child(0)
    panel.tree.setCurrentItem(group_item)
    assert panel.detail_stack.currentWidget() is panel.empty_view
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: FAIL — `panel.detail_stack`, `panel.attribute_view`, etc. don't exist yet.

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `pgtp_editor/ui/diff_merge_panel.py`:

```python
# pgtp_editor/ui/diff_merge_panel.py
"""DiffMergePanel: the shared viewer for all three Diff/Merge comparison
entry points (file-level, page-level, detail-level). Populates the
existing empty "Diff / Merge" center-stage tab with a change-list tree
(left) and a detail view (right). Read-only — no write-back to disk (see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-viewer-ui-design.md).
"""
from __future__ import annotations

import difflib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

DIFFERENCE_ROLE = Qt.ItemDataRole.UserRole

# node_kind values whose old_value/new_value (for an added/removed record)
# is a whole PageNode/DetailNode/ColumnNode, per spec §3.6 case 2.
SUBTREE_NODE_KINDS = {"page", "detail", "column"}


def leaf_label(diff) -> str:
    if diff.attribute is not None:
        label = f"{diff.attribute}: {diff.kind}"
    else:
        label = f"{diff.path[-1]}: {diff.kind}"
    return f"⚠ {label}" if diff.ambiguous else label


class DiffMergePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)

        self._build_detail_views()

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.detail_stack)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter)

    def _build_detail_views(self):
        self.detail_stack = QStackedWidget()

        self.empty_view = QWidget()
        self.detail_stack.addWidget(self.empty_view)

        self.attribute_view = QWidget()
        self.attribute_old_label = QLabel()
        self.attribute_new_label = QLabel()
        attribute_layout = QVBoxLayout(self.attribute_view)
        attribute_layout.addWidget(self.attribute_old_label)
        attribute_layout.addWidget(self.attribute_new_label)
        self.detail_stack.addWidget(self.attribute_view)

        self.subtree_view = QWidget()
        self.subtree_table = QTableWidget(0, 2)
        self.subtree_table.setHorizontalHeaderLabels(["Attribute", "Value"])
        subtree_layout = QVBoxLayout(self.subtree_view)
        subtree_layout.addWidget(self.subtree_table)
        self.detail_stack.addWidget(self.subtree_view)

        self.event_diff_view = QWidget()
        self.event_diff_text = QPlainTextEdit()
        self.event_diff_text.setReadOnly(True)
        event_diff_layout = QVBoxLayout(self.event_diff_view)
        event_diff_layout.addWidget(self.event_diff_text)
        self.detail_stack.addWidget(self.event_diff_view)

        self.detail_stack.setCurrentWidget(self.empty_view)

    def show_differences(self, differences: list) -> None:
        """Build the change-list tree fresh from `differences`, clearing
        any previous content — one comparison session at a time."""
        self.tree.clear()
        self.detail_stack.setCurrentWidget(self.empty_view)
        items_by_prefix: dict[tuple, QTreeWidgetItem] = {}

        for diff in differences:
            *prefix_segments, _ = diff.path
            parent = None
            accumulated: tuple = ()
            for segment in prefix_segments:
                accumulated += (segment,)
                item = items_by_prefix.get(accumulated)
                if item is None:
                    item = QTreeWidgetItem([segment])
                    if parent is not None:
                        parent.addChild(item)
                    else:
                        self.tree.addTopLevelItem(item)
                    items_by_prefix[accumulated] = item
                parent = item

            leaf = QTreeWidgetItem([leaf_label(diff)])
            leaf.setData(0, DIFFERENCE_ROLE, diff)
            leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            leaf.setCheckState(0, Qt.CheckState.Unchecked)
            if parent is not None:
                parent.addChild(leaf)
            else:
                self.tree.addTopLevelItem(leaf)

    def _on_current_item_changed(self, current, previous):
        diff = current.data(0, DIFFERENCE_ROLE) if current is not None else None
        if diff is None:
            self.detail_stack.setCurrentWidget(self.empty_view)
            return
        self._show_difference_detail(diff)

    def _show_difference_detail(self, diff):
        if diff.attribute is not None:
            self.attribute_old_label.setText(f"Old: {diff.old_value}")
            self.attribute_new_label.setText(f"New: {diff.new_value}")
            self.detail_stack.setCurrentWidget(self.attribute_view)
            return

        if diff.node_kind == "event" and diff.kind == "changed":
            old_lines = (diff.old_value or "").splitlines()
            new_lines = (diff.new_value or "").splitlines()
            diff_text = "\n".join(difflib.unified_diff(old_lines, new_lines, lineterm=""))
            self.event_diff_text.setPlainText(diff_text)
            self.detail_stack.setCurrentWidget(self.event_diff_view)
            return

        if diff.node_kind in SUBTREE_NODE_KINDS:
            node = diff.new_value if diff.new_value is not None else diff.old_value
            attrib = node.attrib
            self.subtree_table.setRowCount(len(attrib))
            for row, (key, value) in enumerate(attrib.items()):
                self.subtree_table.setItem(row, 0, QTableWidgetItem(str(key)))
                self.subtree_table.setItem(row, 1, QTableWidgetItem(str(value)))
            self.detail_stack.setCurrentWidget(self.subtree_view)
            return

        # An event added/removed record (whole EventNode, not raw text) —
        # still a whole-subtree case, but EventNode has no .attrib dict, so
        # render its tag_name/side/text as key-value rows instead.
        node = diff.new_value if diff.new_value is not None else diff.old_value
        rows = [("tag_name", node.tag_name), ("side", node.side), ("text", node.text)]
        self.subtree_table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.subtree_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.subtree_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.detail_stack.setCurrentWidget(self.subtree_view)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/diff_merge_panel.py tests/ui/test_diff_merge_panel.py
git commit -m "feat(ui): add three-way detail view (attribute/subtree/event-diff)"
```

---

### Task 10: Next/Prev Difference navigation

**Files:**
- Modify: `pgtp_editor/ui/diff_merge_panel.py`
- Modify: `tests/ui/test_diff_merge_panel.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_diff_merge_panel.py`:

```python
def test_select_next_difference_walks_leaves_in_display_order(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption"),
        make_diff(["page_a", "ability"], node_kind="page", kind="changed", attribute="ability"),
        make_diff(["page_b", "caption"], node_kind="page", kind="changed", attribute="caption"),
    ]
    panel.show_differences(diffs)

    panel.select_next_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[0]

    panel.select_next_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[1]

    panel.select_next_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[2]

    # Stops at the last leaf — no wraparound required.
    panel.select_next_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[2]


def test_select_previous_difference_walks_leaves_backward(qtbot):
    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    diffs = [
        make_diff(["page_a", "caption"], node_kind="page", kind="changed", attribute="caption"),
        make_diff(["page_a", "ability"], node_kind="page", kind="changed", attribute="ability"),
    ]
    panel.show_differences(diffs)

    panel.tree.setCurrentItem(panel.tree.topLevelItem(0).child(1))
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[1]

    panel.select_previous_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[0]

    # Stops at the first leaf — no wraparound required.
    panel.select_previous_difference()
    assert panel.tree.currentItem().data(0, DIFFERENCE_ROLE) is diffs[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: FAIL — `select_next_difference`/`select_previous_difference` don't exist yet.

- [ ] **Step 3: Write minimal implementation**

Add to `DiffMergePanel` in `pgtp_editor/ui/diff_merge_panel.py`:

```python
    def _flattened_leaves(self) -> list[QTreeWidgetItem]:
        leaves: list[QTreeWidgetItem] = []

        def visit(item: QTreeWidgetItem):
            if item.data(0, DIFFERENCE_ROLE) is not None:
                leaves.append(item)
            for i in range(item.childCount()):
                visit(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))
        return leaves

    def _current_leaf_position(self, leaves: list[QTreeWidgetItem]) -> int:
        current = self.tree.currentItem()
        if current is None:
            return -1
        try:
            return leaves.index(current)
        except ValueError:
            return -1

    def select_next_difference(self) -> None:
        leaves = self._flattened_leaves()
        if not leaves:
            return
        position = self._current_leaf_position(leaves)
        next_position = min(position + 1, len(leaves) - 1)
        self.tree.setCurrentItem(leaves[next_position])

    def select_previous_difference(self) -> None:
        leaves = self._flattened_leaves()
        if not leaves:
            return
        position = self._current_leaf_position(leaves)
        previous_position = max(position - 1, 0)
        self.tree.setCurrentItem(leaves[previous_position])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_panel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/diff_merge_panel.py tests/ui/test_diff_merge_panel.py
git commit -m "feat(ui): add Next/Prev Difference navigation to DiffMergePanel"
```

---

### Task 11: Store the real model node on Project Tree items (prerequisite for path-building)

**Files:**
- Modify: `pgtp_editor/ui/project_tree.py`
- Modify: `tests/ui/test_project_tree.py`

`resolve_path` and the Detail-level entry point both need a `path: list[str]` built by walking ancestors' `file_name`/`table_name`/`attrib.get("caption")`. `ProjectTreePanel` currently stores only `NODE_KIND_ROLE` (a string) and `TABLE_NAME_ROLE` (a string) on each item — not the underlying `PageNode`/`DetailNode` object itself. This task adds a `MODEL_NODE_ROLE` storing the actual node object, purely additive (no existing role is removed or changed), so existing tests keep passing unmodified.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_project_tree.py`:

```python
from pgtp_editor.ui.project_tree import MODEL_NODE_ROLE


def test_page_item_carries_model_node(qtbot):
    tree = make_populated_tree(qtbot)
    page_item = tree.topLevelItem(0)
    node = page_item.data(0, MODEL_NODE_ROLE)
    assert node.file_name == "development_equipment" or node.attrib.get("caption") == "Equipment"
    assert node.table_name == "pr.equipment"


def test_detail_item_carries_model_node(qtbot):
    tree = make_populated_tree(qtbot)
    detail_item = tree.topLevelItem(0).child(0)
    node = detail_item.data(0, MODEL_NODE_ROLE)
    assert node.table_name == "pr.attachment"
    assert node.attrib.get("caption") == "Sub-item"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_project_tree.py -v`
Expected: FAIL with `ImportError: cannot import name 'MODEL_NODE_ROLE'`

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/project_tree.py`:

```python
NODE_KIND_ROLE = Qt.ItemDataRole.UserRole
TABLE_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
MODEL_NODE_ROLE = Qt.ItemDataRole.UserRole + 2
```

In `populate_from_project`, after `page_item.setData(0, TABLE_NAME_ROLE, page_table)`:

```python
            page_item.setData(0, MODEL_NODE_ROLE, page)
```

In `_populate_details_and_events`, after `detail_item.setData(0, TABLE_NAME_ROLE, detail_table)`:

```python
            detail_item.setData(0, MODEL_NODE_ROLE, detail)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_project_tree.py -v`
Expected: PASS (all previous tests still pass, plus the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/project_tree.py tests/ui/test_project_tree.py
git commit -m "feat(ui): store model node reference on Project Tree items"
```

---

### Task 12: `CenterStage` exposes a real `DiffMergePanel` instance

**Files:**
- Modify: `pgtp_editor/ui/center_stage.py`
- Modify: `tests/ui/test_center_stage.py`

`CenterStage.diff_merge_tab_index` currently holds a placeholder `QWidget()`. This task swaps that placeholder for a real `DiffMergePanel` instance, exposed as `self.diff_merge_panel`, without changing the tab's index, title, or the shape of the other two tabs — so existing `test_center_stage.py` assertions (`stage.count() == 3`, tab texts/order, raw XML tab visibility toggle) keep passing unmodified.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_center_stage.py`:

```python
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel


def test_diff_merge_tab_holds_a_real_diff_merge_panel(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.diff_merge_panel, DiffMergePanel)
    assert stage.widget(stage.diff_merge_tab_index) is stage.diff_merge_panel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_center_stage.py -v`
Expected: FAIL with `AttributeError: 'CenterStage' object has no attribute 'diff_merge_panel'`

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/center_stage.py`:

```python
from PySide6.QtWidgets import QTabWidget, QWidget

from pgtp_editor.ui.diff_merge_panel import DiffMergePanel


class CenterStage(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.diff_merge_panel = DiffMergePanel()
        self.diff_merge_tab_index = self.addTab(self.diff_merge_panel, "Diff / Merge")
        self.caption_management_tab_index = self.addTab(QWidget(), "Caption Management")
        self.raw_xml_tab_index = self.addTab(QWidget(), "Raw XML")
        self.setTabVisible(self.raw_xml_tab_index, False)

    def set_raw_xml_tab_visible(self, visible):
        self.setTabVisible(self.raw_xml_tab_index, visible)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_center_stage.py -v`
Expected: PASS (all previous tests still pass, plus the new one)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/center_stage.py tests/ui/test_center_stage.py
git commit -m "feat(ui): CenterStage installs a real DiffMergePanel at diff_merge_tab_index"
```

---

### Task 13: `MainWindow` tracks the currently-open project

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_open_project.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_open_project.py`:

```python
def test_open_project_file_tracks_current_project_and_path(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(path))

    assert window._current_project is not None
    assert window._current_project.pages[0].file_name == "development_equipment"
    assert window._current_project_path == str(path)


def test_current_project_is_none_before_any_open(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None
    assert window._current_project_path is None


def test_open_project_file_does_not_overwrite_current_project_on_parse_failure(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    valid_path = tmp_path / "valid.pgtp"
    valid_path.write_text(VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(valid_path))
    first_project = window._current_project

    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")
    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    assert window._current_project is first_project
    assert window._current_project_path == str(valid_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_open_project.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute '_current_project'`

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/main_window.py`. In `__init__`, after `self.center_stage = CenterStage()` / `self.setCentralWidget(self.center_stage)`:

```python
        self._current_project = None
        self._current_project_path = None
```

Modify `open_project_file`:

```python
    def open_project_file(self, path):
        """Load and display the .pgtp project at `path`.

        Split out from `_open_project` so tests can drive the load without
        going through the QFileDialog. On parse failure, shows a clear
        error dialog and leaves the currently-displayed tree (and the
        currently-tracked project) untouched (never a crash, never a
        silently-emptied tree or a silently-forgotten project).
        """
        try:
            project = load_project(path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Failed to Open Project",
                f"Could not open '{path}':\n\n{exc}",
            )
            return
        self.project_tree.populate_from_project(project)
        self._current_project = project
        self._current_project_path = path
        self.statusBar().showMessage(f"Opened: {path}", 5000)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_open_project.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_open_project.py
git commit -m "feat(ui): track currently-open project on MainWindow"
```

---

### Task 14: Wire "Compare / Merge Two Files..." to a real handler

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_menus.py`

The "Compare / Merge Two Files..." action is currently wired via `_add_stub_action`. This task replaces that wiring with a real handler and updates the one existing test that would otherwise assert stub behavior for it (`test_diff_merge_menu_contents` only checks labels, which stay the same, so it needs no change — but we add new tests covering the real behavior; no existing assertion is broken since no test currently asserts a stub message specifically for this action).

- [ ] **Step 1: Write the failing tests**

Create/extend a new test file `tests/ui/test_diff_merge_entry_points.py`:

```python
"""Tests for the three Diff/Merge comparison entry points wired into
MainWindow and ProjectTreePanel: "Compare / Merge Two Files...",
"Compare This Page With...", and "Compare This Detail With...".
"""
from unittest.mock import patch

from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

CHANGED_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Changed Caption">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

MALFORMED_PGTP = "<Project><Presentation><Pages><Page></Pages></Presentation></Project>"


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_compare_merge_two_files_prompts_for_source_when_none_open(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", VALID_PGTP)
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._compare_merge_two_files()

    assert window.center_stage.currentIndex() == window.center_stage.diff_merge_tab_index
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1


def test_compare_merge_two_files_uses_current_project_as_source_without_prompting(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    current_path = _write(tmp_path, "current.pgtp", VALID_PGTP)
    window.open_project_file(current_path)
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ) as mock_dialog:
        window._compare_merge_two_files()

    mock_dialog.assert_called_once()
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1


def test_compare_merge_two_files_cancelled_target_dialog_does_nothing(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", VALID_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), ("", "")],
    ):
        window._compare_merge_two_files()

    assert window.center_stage.currentIndex() != window.center_stage.diff_merge_tab_index


def test_compare_merge_two_files_shows_error_on_target_parse_failure(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", VALID_PGTP)
    broken_path = _write(tmp_path, "broken.pgtp", MALFORMED_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (broken_path, "")],
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._compare_merge_two_files()

    mock_critical.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_entry_points.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute '_compare_merge_two_files'`

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/main_window.py`. Add the import:

```python
from pgtp_editor.diff.differ import diff_project
```

Add the handler method (near `open_project_file`):

```python
    def _compare_merge_two_files(self):
        source = self._current_project
        if source is None:
            source_path, _filter = QFileDialog.getOpenFileName(
                self, "Select Source Project", "", "PGTP files (*.pgtp)"
            )
            if not source_path:
                return
            try:
                source = load_project(source_path)
            except Exception as exc:
                QMessageBox.critical(
                    self, "Failed to Open Source Project", f"Could not open '{source_path}':\n\n{exc}"
                )
                return

        target_path, _filter = QFileDialog.getOpenFileName(
            self, "Select Target Project", "", "PGTP files (*.pgtp)"
        )
        if not target_path:
            return
        try:
            target = load_project(target_path)
        except Exception as exc:
            QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path}':\n\n{exc}"
            )
            return

        differences = diff_project(source, target)
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)
```

Replace the stub wiring in `_build_diff_merge_menu`:

```python
    def _build_diff_merge_menu(self):
        menu = self.menuBar().addMenu("Diff / Merge")
        compare_action = menu.addAction("Compare / Merge Two Files...")
        compare_action.triggered.connect(self._compare_merge_two_files)
        menu.addSeparator()
        self._add_stub_action(menu, "Next Difference")
        self._add_stub_action(menu, "Prev Difference")
        self._add_stub_action(menu, "Apply Changes to Target")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_entry_points.py tests/ui/test_menus.py -v`
Expected: PASS (all pass, including the still-unmodified `test_diff_merge_menu_contents`)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_diff_merge_entry_points.py
git commit -m "feat(ui): wire Compare / Merge Two Files... to a real handler"
```

---

### Task 15: Wire "Next Difference" / "Prev Difference" to `DiffMergePanel`

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_diff_merge_entry_points.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_diff_merge_entry_points.py`:

```python
from tests.ui._menu_helpers import find_action, find_top_menu


DUAL_CAPTION_CHANGED_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Changed A" ability="Changed B">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_next_and_prev_difference_menu_actions_navigate_the_panel(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", DUAL_CAPTION_CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._compare_merge_two_files()

    menu = find_top_menu(window, "Diff / Merge")
    next_action = find_action(menu, "Next Difference")
    prev_action = find_action(menu, "Prev Difference")

    panel = window.center_stage.diff_merge_panel
    leaves = panel._flattened_leaves()
    assert len(leaves) == 2

    next_action.trigger()
    assert panel.tree.currentItem() is leaves[0]
    next_action.trigger()
    assert panel.tree.currentItem() is leaves[1]

    prev_action.trigger()
    assert panel.tree.currentItem() is leaves[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_entry_points.py -v`
Expected: FAIL — clicking "Next Difference" currently only sets a stub status-bar message, so `panel.tree.currentItem()` never changes.

- [ ] **Step 3: Write minimal implementation**

Replace the stub wiring in `_build_diff_merge_menu` in `pgtp_editor/ui/main_window.py`:

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
        self._add_stub_action(menu, "Apply Changes to Target")
```

Note: `_build_diff_merge_menu` runs from `_build_menu_bar`, called at the end of `__init__` after `self.center_stage = CenterStage()` is already assigned — no ordering change is needed, `self.center_stage.diff_merge_panel` already exists by the time this method runs.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_entry_points.py tests/ui/test_menus.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_diff_merge_entry_points.py
git commit -m "feat(ui): wire Next/Prev Difference menu actions to DiffMergePanel navigation"
```

---

### Task 16: Wire "Compare This Page With..." to a real handler

**Files:**
- Modify: `pgtp_editor/ui/project_tree.py`
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_diff_merge_entry_points.py`

The Page-level entry point lives on `ProjectTreePanel`'s context menu but needs to reach `MainWindow`'s `center_stage` and show a `QMessageBox`/`QFileDialog` — the same pattern already used for `on_stub_action` being a callback `ProjectTreePanel` invokes without knowing about `MainWindow`. This task adds a second callback, `on_compare_page`, following that established pattern (constructor injection), rather than giving `ProjectTreePanel` a direct reference to `MainWindow`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_diff_merge_entry_points.py`:

```python
def test_compare_this_page_with_real_handler(qtbot, tmp_path):
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

    assert window.center_stage.currentIndex() == window.center_stage.diff_merge_tab_index
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1


def test_compare_this_page_with_shows_error_when_page_not_found_in_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", VALID_PGTP))
    other_page_pgtp = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="a_totally_different_page" tableName="pr.other" caption="Other">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""
    target_path = _write(tmp_path, "target.pgtp", other_page_pgtp)

    page_item = window.project_tree.topLevelItem(0)
    menu = window.project_tree.build_page_menu(page_item)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        find_action(menu, "Compare This Page With...").trigger()

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert "development_equipment" in args[2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_entry_points.py -v`
Expected: FAIL — `build_page_menu`'s "Compare This Page With..." action still only invokes the stub callback, so no dialog is triggered and `center_stage.currentIndex()` never changes.

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/project_tree.py`. Constructor gains a new optional callback:

```python
class ProjectTreePanel(QTreeWidget):
    def __init__(self, parent=None, on_stub_action=None, on_compare_page=None, on_compare_detail=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self._on_stub_action = on_stub_action or (lambda label: None)
        self._on_compare_page = on_compare_page or (lambda page_node: None)
        self._on_compare_detail = on_compare_detail or (lambda detail_node, source_path: None)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
```

Replace the stub entry in `build_page_menu`:

```python
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
        compare_action = menu.addAction("Compare This Page With...")
        compare_action.triggered.connect(
            lambda checked=False, i=item: self._on_compare_page(i.data(0, MODEL_NODE_ROLE))
        )
        menu.addSeparator()
        self._add_stub_action(menu, "Find Column Usages...")
        self._add_stub_action(menu, "Rename / Unify Captions...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Page")
        return menu
```

Modify `pgtp_editor/ui/main_window.py`. Add imports:

```python
from pgtp_editor.diff.differ import compare_block, diff_project
```

(replacing the earlier `from pgtp_editor.diff.differ import diff_project` import added in Task 14 with this combined one).

Wire the new callback when constructing `ProjectTreePanel` in `__init__`:

```python
        self.project_tree = ProjectTreePanel(
            on_stub_action=self._not_implemented,
            on_compare_page=self._compare_page_with,
            on_compare_detail=self._compare_detail_with,
        )
```

(The `on_compare_detail` callback is wired here now and implemented in Task 17 — passing it in this task keeps the constructor call written once.)

Add the handler:

```python
    def _compare_page_with(self, page_node):
        target_path, _filter = QFileDialog.getOpenFileName(
            self, "Select Target Project", "", "PGTP files (*.pgtp)"
        )
        if not target_path:
            return
        try:
            target = load_project(target_path)
        except Exception as exc:
            QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path}':\n\n{exc}"
            )
            return

        target_page = next((p for p in target.pages if p.file_name == page_node.file_name), None)
        if target_page is None:
            QMessageBox.critical(
                self,
                "Page Not Found",
                f"No Page with fileName '{page_node.file_name}' exists in '{target_path}'.",
            )
            return

        differences = compare_block(page_node, target_page, path=[page_node.file_name], node_kind="page")
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_entry_points.py tests/ui/test_project_tree.py -v`
Expected: FAIL still on any `_compare_detail_with` reference since it doesn't exist yet — add a temporary no-op stub so Task 16 is independently green:

```python
    def _compare_detail_with(self, detail_node, source_path):
        pass  # implemented in Task 17
```

Run again: `pytest tests/ui/test_diff_merge_entry_points.py tests/ui/test_project_tree.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/project_tree.py pgtp_editor/ui/main_window.py tests/ui/test_diff_merge_entry_points.py
git commit -m "feat(ui): wire Compare This Page With... to a real handler"
```

---

### Task 17: Wire "Compare This Detail With..." to a real handler (using `resolve_path`)

**Files:**
- Modify: `pgtp_editor/ui/project_tree.py`
- Modify: `pgtp_editor/ui/main_window.py`
- Modify: `tests/ui/test_diff_merge_entry_points.py`

This is the entry point that needs `resolve_path` (Task 1-5) and the ancestor-walking `path` construction described in spec §3.3: walk from the clicked Detail up to the root Page, reading each ancestor's `file_name` (Page) or `table_name`/`attrib.get("caption")` (Detail), in root-to-leaf order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_diff_merge_entry_points.py`:

```python
SOURCE_WITH_DETAIL_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <Details>
          <Detail caption="Equipment\\Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item" ability="insert,edit">
            </Page>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

TARGET_WITH_CHANGED_DETAIL_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <Details>
          <Detail caption="Equipment\\Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item" ability="view">
            </Page>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

TARGET_MISSING_DETAIL_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_compare_this_detail_with_real_handler(qtbot, tmp_path):
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

    assert window.center_stage.currentIndex() == window.center_stage.diff_merge_tab_index
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1


def test_compare_this_detail_with_shows_error_when_detail_not_found_in_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", SOURCE_WITH_DETAIL_PGTP))
    target_path = _write(tmp_path, "target.pgtp", TARGET_MISSING_DETAIL_PGTP)

    detail_item = window.project_tree.topLevelItem(0).child(0)
    menu = window.project_tree.build_detail_menu(detail_item)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        find_action(menu, "Compare This Detail With...").trigger()

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert "pr.attachment" in args[2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_entry_points.py -v`
Expected: FAIL — `_compare_detail_with` is still the no-op stub from Task 16, and `build_detail_menu`'s "Compare This Detail With..." action doesn't build a `source_path` or invoke the callback yet.

- [ ] **Step 3: Write minimal implementation**

Modify `pgtp_editor/ui/project_tree.py`. Add a path-building helper and wire the menu action in `build_detail_menu`:

```python
    def _build_source_path(self, item) -> list[str]:
        """Walk from `item` up to the root Page, reading each ancestor's
        identity segment (Page's file_name, or Detail's tableName/caption)
        in root-to-leaf order, per spec §3.3."""
        segments: list[str] = []
        current = item
        while current is not None:
            node = current.data(0, MODEL_NODE_ROLE)
            kind = current.data(0, NODE_KIND_ROLE)
            if kind == "page":
                segments.append(node.file_name)
            else:
                segments.append(f"{node.table_name}/{node.attrib.get('caption')}")
            current = current.parent()
        segments.reverse()
        return segments
```

Replace the stub entry in `build_detail_menu`:

```python
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
        compare_action = menu.addAction("Compare This Detail With...")
        compare_action.triggered.connect(
            lambda checked=False, i=item: self._on_compare_detail(
                i.data(0, MODEL_NODE_ROLE), self._build_source_path(i)
            )
        )
        if self.has_duplicate_table(item):
            self._add_stub_action(menu, "Compare with Other Instance...")
        menu.addSeparator()
        self._add_stub_action(menu, "Delete Detail (+ nested)")
        return menu
```

Modify `pgtp_editor/ui/main_window.py`. Add the import:

```python
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
```

Replace the Task 16 no-op stub with the real implementation:

```python
    def _compare_detail_with(self, detail_node, source_path):
        target_path_str, _filter = QFileDialog.getOpenFileName(
            self, "Select Target Project", "", "PGTP files (*.pgtp)"
        )
        if not target_path_str:
            return
        try:
            target = load_project(target_path_str)
        except Exception as exc:
            QMessageBox.critical(
                self, "Failed to Open Target Project", f"Could not open '{target_path_str}':\n\n{exc}"
            )
            return

        result = resolve_path(target, source_path)
        if isinstance(result, ResolutionError):
            QMessageBox.critical(self, "Detail Not Found", result.message)
            return

        differences = compare_block(detail_node, result, path=source_path, node_kind="detail")
        self.center_stage.diff_merge_panel.show_differences(differences)
        self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_entry_points.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `pytest -v`
Expected: PASS (all tests across the whole suite green)

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/project_tree.py pgtp_editor/ui/main_window.py tests/ui/test_diff_merge_entry_points.py
git commit -m "feat(ui): wire Compare This Detail With... to a real handler using resolve_path"
```

---

### Task 18: Real-sample-file integration tests

**Files:**
- Create: `tests/ui/test_diff_merge_panel_integration.py`

One integration test per real sample file, running the full file-level compare flow's underlying logic (`load_project` twice + `diff_project` + `DiffMergePanel.show_differences`) against itself, asserting zero leaf nodes — mirroring `tests/diff/test_differ_integration.py`'s own self-diff-is-empty pattern, exercised through the UI-facing code this time.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_diff_merge_panel_integration.py
"""Regression tests: running the full file-level compare flow's underlying
logic (load_project twice + diff_project + DiffMergePanel.show_differences)
against a real sample file and itself must produce a change-list tree with
zero leaf nodes. Mirrors tests/diff/test_differ_integration.py's own
self-diff-is-empty pattern, exercised through the UI-facing code path.

Requires sample/*.pgtp to be present on disk (gitignored).
"""
from pathlib import Path

import pytest

from pgtp_editor.diff.differ import diff_project
from pgtp_editor.model.parser import load_project
from pgtp_editor.ui.diff_merge_panel import DiffMergePanel

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"


def _load_twice(filename):
    path = SAMPLE_DIR / filename
    if not path.exists():
        pytest.skip(f"sample fixture not present on disk: {path}")
    return load_project(path), load_project(path)


def test_dev_ferrara_self_compare_has_no_leaf_differences(qtbot):
    source, target = _load_twice("dev_Ferrara.pgtp")
    differences = diff_project(source, target)

    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    panel.show_differences(differences)

    assert panel._flattened_leaves() == []


def test_sdman_renco_strikes_back_self_compare_has_no_leaf_differences(qtbot):
    source, target = _load_twice("Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp")
    differences = diff_project(source, target)

    panel = DiffMergePanel()
    qtbot.addWidget(panel)
    panel.show_differences(differences)

    assert panel._flattened_leaves() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_diff_merge_panel_integration.py -v`
Expected: FAIL only if the sample files were absent (they are present in this worktree, per the "Before you start" note, so this should actually PASS immediately since `diff_project` on an identical tree already returns `[]`, which `show_differences([])` renders with zero leaves). If it unexpectedly fails, run `pytest tests/diff/test_differ_integration.py -v` first to confirm the underlying engine's self-diff-is-empty guarantee still holds; a failure here would point to a UI-layer defect, not an engine defect, since the engine-level version of this same test already passes on main.

- [ ] **Step 3: No implementation step needed**

This task exercises already-built code (`diff_project`, `DiffMergePanel.show_differences`, `_flattened_leaves`) — there is nothing new to implement. If Step 2 surprises you with a failure, treat it as a bug report against `DiffMergePanel` and fix `show_differences`/`_flattened_leaves` before proceeding (do not weaken the test).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_diff_merge_panel_integration.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/ui/test_diff_merge_panel_integration.py
git commit -m "test(ui): add real-sample-file self-compare integration tests for DiffMergePanel"
```

---

### Task 19: Full suite regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -v`
Expected: PASS — every test across `tests/diff/`, `tests/model/`, and `tests/ui/` green, including all pre-existing tests untouched by this plan (`test_about.py`, `test_main_window.py`, the unmodified portions of `test_menus.py`, `test_open_project.py`, `test_project_tree.py`, `test_center_stage.py`, and all of `tests/diff/` and `tests/model/`).

- [ ] **Step 2: Spot-check no stub language remains for the three wired entry points**

Run: `pytest tests/ui/test_menus.py::test_diff_merge_menu_contents tests/ui/test_project_tree.py::test_page_context_menu tests/ui/test_project_tree.py::test_detail_context_menu_shows_compare_instance_when_table_reused -v`
Expected: PASS — these tests assert only menu *labels* (unchanged by this plan) and were never asserting stub *behavior* for the three now-real entry points, so no test needed to be deleted; this step is a final confirmation that label-only assertions still hold after the behavior swap.

- [ ] **Step 3: Commit (only if Step 1 or 2 required a fix)**

If everything already passed, there is nothing to commit for this task — it is a verification checkpoint, not a code change. If a fix was needed, commit it with a message describing the regression found and fixed.

---

## Summary of new/modified files

| File | Change |
|---|---|
| `pgtp_editor/diff/resolve.py` | New — `ResolutionError`, `resolve_path` |
| `pgtp_editor/ui/diff_merge_panel.py` | New — `DiffMergePanel`, `leaf_label`, `DIFFERENCE_ROLE` |
| `pgtp_editor/ui/center_stage.py` | Modified — installs real `DiffMergePanel` at `diff_merge_tab_index`, exposes `self.diff_merge_panel` |
| `pgtp_editor/ui/main_window.py` | Modified — `_current_project`/`_current_project_path` state, `_compare_merge_two_files`, `_compare_page_with`, `_compare_detail_with`, real Next/Prev Difference wiring |
| `pgtp_editor/ui/project_tree.py` | Modified — `MODEL_NODE_ROLE`, `on_compare_page`/`on_compare_detail` callbacks, `_build_source_path`, real "Compare This Page/Detail With..." wiring |
| `tests/diff/test_resolve.py` | New |
| `tests/ui/test_diff_merge_panel.py` | New |
| `tests/ui/test_diff_merge_panel_integration.py` | New |
| `tests/ui/test_diff_merge_entry_points.py` | New |
| `tests/ui/test_center_stage.py` | Modified — additive test |
| `tests/ui/test_open_project.py` | Modified — additive tests |
| `tests/ui/test_project_tree.py` | Modified — additive tests |
