# PGTP Editor — Differ Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `pgtp_editor/diff/` package — a pure, Qt-free comparison engine that walks two loaded `ProjectModel` trees (Source and Target) and produces a flat `list[Difference]` describing every Page/Detail/Column/EventHandler that was added, removed, or changed between them.

**Architecture:** Two new modules. `pgtp_editor/diff/records.py` defines the `Difference` dataclass (the only data shape the engine emits). `pgtp_editor/diff/differ.py` defines `diff_project(source, target) -> list[Difference]` (top-level Page matching by `fileName`) plus a shared recursive helper `compare_block(source_node, target_node, path, node_kind)` that both the Page-pair and every Detail-pair comparison route through, since `DetailNode` and `PageNode` expose the same shape (`attrib`, `columns`, `events`, `details`). The engine imports only from `pgtp_editor.model.nodes` (`ProjectModel`, `PageNode`, `DetailNode`, `ColumnNode`, `EventNode`, `classify_event_side`) and never touches `pgtp_editor.model.parser` or any Qt module. Built test-first: dataclass shape, then empty-project base case, then Page add/remove/change, then Column diffing, then Event diffing (reusing the model layer's suffix-normalization), then Detail diffing (scoped matching + recursion), then nested Details, then the ambiguous-duplicate-sibling case, then two real-sample-file self-diff regression tests.

**Tech Stack:** Python 3.10+, pytest (no pytest-qt needed — this package has zero Qt dependency), dataclasses, existing `pgtp_editor.model` package (assumed already merged into this branch).

---

## Before you start

This plan assumes `pgtp_editor/model/nodes.py` and `pgtp_editor/model/parser.py` (from the completed Real Model sub-project) already exist in this codebase, exposing:

- `pgtp_editor.model.nodes.ProjectModel` — dataclass with field `pages: list[PageNode]`.
- `pgtp_editor.model.nodes.PageNode` — dataclass with fields `identity: str`, `attrib: dict`, `sourceline: int | None`, `details: list[DetailNode]`, `columns: list[ColumnNode]`, `events: list[EventNode]`; properties `file_name` (reads `attrib["fileName"]`) and `table_name` (reads `attrib["tableName"]`).
- `pgtp_editor.model.nodes.DetailNode` — same shape as `PageNode` (dataclass with `identity`, `attrib`, `sourceline`, `details`, `columns`, `events`) plus a `table_name` property. No `file_name` property (Details don't have one — `tableName`/`caption` come from `attrib` directly).
- `pgtp_editor.model.nodes.ColumnNode` — dataclass with `identity: str`, `attrib: dict`, `sourceline: int | None`; property `field_name` (reads `attrib["fieldName"]`).
- `pgtp_editor.model.nodes.EventNode` — dataclass with `identity: str`, `tag_name: str`, `side: str`, `text: str`, `sourceline: int | None`.
- `pgtp_editor.model.nodes.classify_event_side(tag_name: str) -> str` — internally does `tag_name.split("_", 1)[0]` to strip a suffix before classifying. This plan reuses that same `split("_", 1)[0]` normalization (imported indirectly isn't possible since it's inlined in `classify_event_side`, so Task 6 duplicates only the one-line split expression, not the classification logic itself — see Task 6's judgment-call note).
- `pgtp_editor.model.parser.load_project(path) -> ProjectModel`.

Do not re-implement or duplicate any of the above — only import and use it.

This plan does **not** cover any UI, the Diff/Merge menu, the Apply step, or line-based text diffing of event bodies — see the design spec's §2.2 for the full out-of-scope list.

---

### Task 1: `Difference` dataclass

**Files:**
- Create: `pgtp_editor/diff/__init__.py`
- Create: `pgtp_editor/diff/records.py`
- Test: `tests/diff/__init__.py`
- Test: `tests/diff/test_records.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/diff/test_records.py
from pgtp_editor.diff.records import Difference


def test_difference_holds_all_fields():
    diff = Difference(
        kind="changed",
        path=["development_equipment"],
        node_kind="page",
        attribute="caption",
        old_value="Old Caption",
        new_value="New Caption",
        ambiguous=False,
    )
    assert diff.kind == "changed"
    assert diff.path == ["development_equipment"]
    assert diff.node_kind == "page"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Caption"
    assert diff.new_value == "New Caption"
    assert diff.ambiguous is False


def test_difference_ambiguous_defaults_to_false():
    diff = Difference(
        kind="added",
        path=["some_page"],
        node_kind="page",
        attribute=None,
        old_value=None,
        new_value="a page node placeholder",
    )
    assert diff.ambiguous is False
```

- [ ] **Step 2: Create empty test package files**

```python
# tests/diff/__init__.py
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/diff/test_records.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.diff'`

- [ ] **Step 4: Write minimal implementation**

```python
# pgtp_editor/diff/__init__.py
```

```python
# pgtp_editor/diff/records.py
"""The `Difference` record shape emitted by `pgtp_editor.diff.differ`.

Pure data holder, no logic. Mirrors the model layer's own `@dataclass`
style (see `pgtp_editor/model/nodes.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Difference:
    kind: str  # "added" | "removed" | "changed"
    path: list[str]
    node_kind: str  # "page" | "detail" | "column" | "event"
    attribute: str | None
    old_value: Any
    new_value: Any
    ambiguous: bool = False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/diff/test_records.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/diff/__init__.py pgtp_editor/diff/records.py tests/diff/__init__.py tests/diff/test_records.py
git commit -m "feat(diff): add Difference dataclass"
```

---

### Task 2: `diff_project` base case — empty projects and Page added

**Files:**
- Create: `pgtp_editor/diff/differ.py`
- Test: `tests/diff/test_differ.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_differ.py
from pgtp_editor.model.nodes import PageNode, ProjectModel
from pgtp_editor.diff.differ import diff_project


def make_page(file_name, **extra_attrib):
    attrib = {"fileName": file_name}
    attrib.update(extra_attrib)
    return PageNode(identity=file_name, attrib=attrib)


def test_diff_project_two_empty_projects_returns_empty_list():
    source = ProjectModel(pages=[])
    target = ProjectModel(pages=[])
    assert diff_project(source, target) == []


def test_diff_project_page_added_in_source():
    page = make_page("new_page", tableName="pr.new", caption="New Page")
    source = ProjectModel(pages=[page])
    target = ProjectModel(pages=[])

    result = diff_project(source, target)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["new_page"]
    assert diff.node_kind == "page"
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is page
    assert diff.ambiguous is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_differ.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgtp_editor.diff.differ'`

- [ ] **Step 3: Write minimal implementation**

```python
# pgtp_editor/diff/differ.py
"""Comparison algorithm: diff_project() walks two ProjectModel trees and
produces a flat list of Difference records. Pure logic — no Qt, no file I/O.

See docs/superpowers/specs/2026-07-12-pgtp-editor-differ-engine-design.md
for the full algorithm description.
"""
from __future__ import annotations

from pgtp_editor.model.nodes import ProjectModel
from pgtp_editor.diff.records import Difference


def diff_project(source: ProjectModel, target: ProjectModel) -> list[Difference]:
    differences: list[Difference] = []

    target_pages_by_file_name = {p.file_name: p for p in target.pages}
    matched_target_file_names: set[str] = set()

    for source_page in source.pages:
        target_page = target_pages_by_file_name.get(source_page.file_name)
        if target_page is None:
            differences.append(
                Difference(
                    kind="added",
                    path=[source_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=None,
                    new_value=source_page,
                )
            )
        else:
            matched_target_file_names.add(source_page.file_name)

    for target_page in target.pages:
        if target_page.file_name not in matched_target_file_names and target_page.file_name not in {
            p.file_name for p in source.pages
        }:
            differences.append(
                Difference(
                    kind="removed",
                    path=[target_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=target_page,
                    new_value=None,
                )
            )

    return differences
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_differ.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/differ.py tests/diff/test_differ.py
git commit -m "feat(diff): add diff_project base case (empty projects, page added)"
```

---

### Task 3: Page removed and Page attribute changed

**Files:**
- Modify: `pgtp_editor/diff/differ.py`
- Test: `tests/diff/test_differ.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_differ.py (append)

def test_diff_project_page_removed_from_target():
    page = make_page("old_page", tableName="pr.old", caption="Old Page")
    source = ProjectModel(pages=[])
    target = ProjectModel(pages=[page])

    result = diff_project(source, target)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.path == ["old_page"]
    assert diff.node_kind == "page"
    assert diff.attribute is None
    assert diff.old_value is page
    assert diff.new_value is None
    assert diff.ambiguous is False


def test_diff_project_page_attribute_changed():
    source_page = make_page("shared_page", tableName="pr.shared", caption="New Caption")
    target_page = make_page("shared_page", tableName="pr.shared", caption="Old Caption")
    source = ProjectModel(pages=[source_page])
    target = ProjectModel(pages=[target_page])

    result = diff_project(source, target)

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page"]
    assert diff.node_kind == "page"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Caption"
    assert diff.new_value == "New Caption"
    assert diff.ambiguous is False


def test_diff_project_matched_pages_no_differences():
    source_page = make_page("shared_page", tableName="pr.shared", caption="Same")
    target_page = make_page("shared_page", tableName="pr.shared", caption="Same")
    source = ProjectModel(pages=[source_page])
    target = ProjectModel(pages=[target_page])

    assert diff_project(source, target) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_differ.py -v`
Expected: FAIL — `test_diff_project_page_removed_from_target` fails because the current
implementation's "removed" branch has a bug: it checks `target_page.file_name not in {
p.file_name for p in source.pages}` which is always true when `matched_target_file_names`
is empty, but more importantly `test_diff_project_page_attribute_changed` fails because
matched pages are never compared for attribute differences at all yet.

- [ ] **Step 3: Rewrite `diff_project` to fix removed-page logic and add attribute comparison**

Replace the entire contents of `pgtp_editor/diff/differ.py`:

```python
# pgtp_editor/diff/differ.py
"""Comparison algorithm: diff_project() walks two ProjectModel trees and
produces a flat list of Difference records. Pure logic — no Qt, no file I/O.

See docs/superpowers/specs/2026-07-12-pgtp-editor-differ-engine-design.md
for the full algorithm description.
"""
from __future__ import annotations

from pgtp_editor.model.nodes import ProjectModel
from pgtp_editor.diff.records import Difference


def diff_project(source: ProjectModel, target: ProjectModel) -> list[Difference]:
    differences: list[Difference] = []

    target_pages_by_file_name = {p.file_name: p for p in target.pages}
    source_file_names = {p.file_name for p in source.pages}

    for source_page in source.pages:
        target_page = target_pages_by_file_name.get(source_page.file_name)
        if target_page is None:
            differences.append(
                Difference(
                    kind="added",
                    path=[source_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=None,
                    new_value=source_page,
                )
            )
        else:
            differences.extend(
                _compare_attributes(
                    source_page,
                    target_page,
                    path=[source_page.file_name],
                    node_kind="page",
                )
            )

    for target_page in target.pages:
        if target_page.file_name not in source_file_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=[target_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=target_page,
                    new_value=None,
                )
            )

    return differences


def _compare_attributes(source_node, target_node, path, node_kind) -> list[Difference]:
    """Compare source_node.attrib vs target_node.attrib, emitting one
    Changed record per differing attribute key. Covers keys present on
    either side (a key missing on one side counts as differing from
    whatever value the other side has, defaulting the missing side to
    None)."""
    differences: list[Difference] = []
    all_keys = set(source_node.attrib.keys()) | set(target_node.attrib.keys())
    for key in sorted(all_keys):
        source_value = source_node.attrib.get(key)
        target_value = target_node.attrib.get(key)
        if source_value != target_value:
            differences.append(
                Difference(
                    kind="changed",
                    path=list(path),
                    node_kind=node_kind,
                    attribute=key,
                    old_value=target_value,
                    new_value=source_value,
                    ambiguous=False,
                )
            )
    return differences
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_differ.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/differ.py tests/diff/test_differ.py
git commit -m "feat(diff): add page-removed detection and attribute comparison"
```

---

### Task 4: Column diffing (added, removed, changed) within a matched Page pair

**Files:**
- Modify: `pgtp_editor/diff/differ.py`
- Test: `tests/diff/test_differ.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_differ.py (append)
from pgtp_editor.model.nodes import ColumnNode


def make_column(field_name, **extra_attrib):
    attrib = {"fieldName": field_name}
    attrib.update(extra_attrib)
    return ColumnNode(identity=field_name, attrib=attrib)


def test_diff_project_column_added():
    col = make_column("new_field", caption="New Field")
    source_page = make_page("shared_page")
    source_page.columns = [col]
    target_page = make_page("shared_page")

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["shared_page", "new_field"]
    assert diff.node_kind == "column"
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is col


def test_diff_project_column_removed():
    col = make_column("old_field", caption="Old Field")
    source_page = make_page("shared_page")
    target_page = make_page("shared_page")
    target_page.columns = [col]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.path == ["shared_page", "old_field"]
    assert diff.node_kind == "column"
    assert diff.attribute is None
    assert diff.old_value is col
    assert diff.new_value is None


def test_diff_project_column_attribute_changed():
    source_page = make_page("shared_page")
    source_page.columns = [make_column("tag", caption="New Caption")]
    target_page = make_page("shared_page")
    target_page.columns = [make_column("tag", caption="Old Caption")]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page", "tag"]
    assert diff.node_kind == "column"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Caption"
    assert diff.new_value == "New Caption"


def test_diff_project_matched_columns_no_differences():
    source_page = make_page("shared_page")
    source_page.columns = [make_column("tag", caption="Same")]
    target_page = make_page("shared_page")
    target_page.columns = [make_column("tag", caption="Same")]

    assert diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page])) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_differ.py -v`
Expected: FAIL — columns are not compared yet, so all four new tests fail (empty list
returned instead of expected diffs, or extra column diffs missing).

- [ ] **Step 3: Add column comparison to `diff_project`**

Modify `pgtp_editor/diff/differ.py` — replace the `_compare_attributes` call site for
matched pages, and add a new `_compare_columns` helper:

```python
    for source_page in source.pages:
        target_page = target_pages_by_file_name.get(source_page.file_name)
        if target_page is None:
            differences.append(
                Difference(
                    kind="added",
                    path=[source_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=None,
                    new_value=source_page,
                )
            )
        else:
            path = [source_page.file_name]
            differences.extend(
                _compare_attributes(source_page, target_page, path=path, node_kind="page")
            )
            differences.extend(_compare_columns(source_page, target_page, path=path))
```

Add the new helper function after `_compare_attributes`:

```python
def _compare_columns(source_node, target_node, path) -> list[Difference]:
    """Diff Columns (children) of a matched Page/Detail pair, matched by
    fieldName, scoped to this parent pair only."""
    differences: list[Difference] = []

    target_columns_by_field_name = {c.field_name: c for c in target_node.columns}
    source_field_names = {c.field_name for c in source_node.columns}

    for source_column in source_node.columns:
        target_column = target_columns_by_field_name.get(source_column.field_name)
        column_path = path + [source_column.field_name]
        if target_column is None:
            differences.append(
                Difference(
                    kind="added",
                    path=column_path,
                    node_kind="column",
                    attribute=None,
                    old_value=None,
                    new_value=source_column,
                )
            )
        else:
            differences.extend(
                _compare_attributes(source_column, target_column, path=column_path, node_kind="column")
            )

    for target_column in target_node.columns:
        if target_column.field_name not in source_field_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=path + [target_column.field_name],
                    node_kind="column",
                    attribute=None,
                    old_value=target_column,
                    new_value=None,
                )
            )

    return differences
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_differ.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/differ.py tests/diff/test_differ.py
git commit -m "feat(diff): add Column diffing scoped to matched Page pair"
```

---

### Task 5: Extract `compare_block` to unify attribute + column comparison

Before adding Event and Detail diffing, consolidate the per-pair comparison logic
(currently inlined in `diff_project`'s matched-page branch) into the shared recursive
helper the design spec calls for, so Task 6/7 add event/detail handling to one place
that both Pages and Details will route through.

**Files:**
- Modify: `pgtp_editor/diff/differ.py`
- Test: `tests/diff/test_differ.py`

- [ ] **Step 1: Write a test asserting the public entry point still behaves identically**

This is a refactor with no behavior change, so re-run the existing suite as the
regression check rather than adding a new test. No new test file changes in this step.

- [ ] **Step 2: Refactor `differ.py` to introduce `compare_block`**

Replace the entire contents of `pgtp_editor/diff/differ.py`:

```python
# pgtp_editor/diff/differ.py
"""Comparison algorithm: diff_project() walks two ProjectModel trees and
produces a flat list of Difference records. Pure logic — no Qt, no file I/O.

See docs/superpowers/specs/2026-07-12-pgtp-editor-differ-engine-design.md
for the full algorithm description.
"""
from __future__ import annotations

from pgtp_editor.model.nodes import ProjectModel
from pgtp_editor.diff.records import Difference


def diff_project(source: ProjectModel, target: ProjectModel) -> list[Difference]:
    differences: list[Difference] = []

    target_pages_by_file_name = {p.file_name: p for p in target.pages}
    source_file_names = {p.file_name for p in source.pages}

    for source_page in source.pages:
        target_page = target_pages_by_file_name.get(source_page.file_name)
        if target_page is None:
            differences.append(
                Difference(
                    kind="added",
                    path=[source_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=None,
                    new_value=source_page,
                )
            )
        else:
            differences.extend(
                compare_block(
                    source_page,
                    target_page,
                    path=[source_page.file_name],
                    node_kind="page",
                )
            )

    for target_page in target.pages:
        if target_page.file_name not in source_file_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=[target_page.file_name],
                    node_kind="page",
                    attribute=None,
                    old_value=target_page,
                    new_value=None,
                )
            )

    return differences


def compare_block(source_node, target_node, path, node_kind) -> list[Difference]:
    """Compare a matched pair of nodes that share the Page/Detail shape
    (attrib, columns, events, details), emitting Difference records for:
    - attribute differences on this node itself
    - Column diffs (added/removed/changed), scoped to this parent pair
    (Event and Detail diffing are added in later tasks.)

    `node_kind` is the caller's responsibility ("page" or "detail") since
    this helper itself is shape-agnostic.
    """
    differences: list[Difference] = []
    differences.extend(_compare_attributes(source_node, target_node, path=path, node_kind=node_kind))
    differences.extend(_compare_columns(source_node, target_node, path=path))
    return differences


def _compare_attributes(source_node, target_node, path, node_kind) -> list[Difference]:
    """Compare source_node.attrib vs target_node.attrib, emitting one
    Changed record per differing attribute key. Covers keys present on
    either side (a key missing on one side counts as differing from
    whatever value the other side has, defaulting the missing side to
    None)."""
    differences: list[Difference] = []
    all_keys = set(source_node.attrib.keys()) | set(target_node.attrib.keys())
    for key in sorted(all_keys):
        source_value = source_node.attrib.get(key)
        target_value = target_node.attrib.get(key)
        if source_value != target_value:
            differences.append(
                Difference(
                    kind="changed",
                    path=list(path),
                    node_kind=node_kind,
                    attribute=key,
                    old_value=target_value,
                    new_value=source_value,
                    ambiguous=False,
                )
            )
    return differences


def _compare_columns(source_node, target_node, path) -> list[Difference]:
    """Diff Columns (children) of a matched Page/Detail pair, matched by
    fieldName, scoped to this parent pair only."""
    differences: list[Difference] = []

    target_columns_by_field_name = {c.field_name: c for c in target_node.columns}
    source_field_names = {c.field_name for c in source_node.columns}

    for source_column in source_node.columns:
        target_column = target_columns_by_field_name.get(source_column.field_name)
        column_path = path + [source_column.field_name]
        if target_column is None:
            differences.append(
                Difference(
                    kind="added",
                    path=column_path,
                    node_kind="column",
                    attribute=None,
                    old_value=None,
                    new_value=source_column,
                )
            )
        else:
            differences.extend(
                _compare_attributes(source_column, target_column, path=column_path, node_kind="column")
            )

    for target_column in target_node.columns:
        if target_column.field_name not in source_field_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=path + [target_column.field_name],
                    node_kind="column",
                    attribute=None,
                    old_value=target_column,
                    new_value=None,
                )
            )

    return differences
```

- [ ] **Step 3: Run full suite to verify no regressions**

Run: `pytest tests/diff/ -v`
Expected: PASS (9 passed) — identical results to before the refactor.

- [ ] **Step 4: Commit**

```bash
git add pgtp_editor/diff/differ.py
git commit -m "refactor(diff): extract compare_block to unify page/detail comparison"
```

---

### Task 6: Event diffing (added, removed, changed text), reusing suffix normalization

**Files:**
- Modify: `pgtp_editor/diff/differ.py`
- Test: `tests/diff/test_differ.py`

**Judgment call:** the design spec (§3.2) says to reuse "the same normalization the
model layer already applies for client/server classification" for matching
EventHandlers by base name. Reading `pgtp_editor/model/nodes.py`, `classify_event_side`
does not expose the base-name split as a separate importable helper — the split
(`tag_name.split("_", 1)[0]`) is inlined inside `classify_event_side` itself, which
returns `"C"`/`"S"`, not the base name. There is no separate public function to import
for just the base-name computation. Rather than modify `model/nodes.py` (out of scope —
this plan only imports from the model layer) or reimplement a *second, possibly
divergent* rule, this task duplicates the exact one-line expression
`tag_name.split("_", 1)[0]` inline in `differ.py` with a comment pointing back at
`classify_event_side` as the source of truth for this rule, so if the vendor's suffix
convention ever changes, a future maintainer knows to check both places. This keeps the
rule textually identical without requiring a cross-package refactor of the model layer
that this plan is not scoped to perform.

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_differ.py (append)
from pgtp_editor.model.nodes import EventNode


def make_event(tag_name, text, side="S"):
    return EventNode(identity=tag_name, tag_name=tag_name, side=side, text=text)


def test_diff_project_event_added():
    event = make_event("OnRowProcess", "echo 'new';")
    source_page = make_page("shared_page")
    source_page.events = [event]
    target_page = make_page("shared_page")

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["shared_page", "OnRowProcess"]
    assert diff.node_kind == "event"
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is event


def test_diff_project_event_removed():
    event = make_event("OnRowProcess", "echo 'old';")
    source_page = make_page("shared_page")
    target_page = make_page("shared_page")
    target_page.events = [event]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.path == ["shared_page", "OnRowProcess"]
    assert diff.node_kind == "event"
    assert diff.attribute is None
    assert diff.old_value is event
    assert diff.new_value is None


def test_diff_project_event_text_changed():
    source_page = make_page("shared_page")
    source_page.events = [make_event("OnRowProcess", "echo 'new text';")]
    target_page = make_page("shared_page")
    target_page.events = [make_event("OnRowProcess", "echo 'old text';")]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page", "OnRowProcess"]
    assert diff.node_kind == "event"
    assert diff.attribute is None
    assert diff.old_value == "echo 'old text';"
    assert diff.new_value == "echo 'new text';"


def test_diff_project_matched_events_no_differences():
    source_page = make_page("shared_page")
    source_page.events = [make_event("OnRowProcess", "same();")]
    target_page = make_page("shared_page")
    target_page.events = [make_event("OnRowProcess", "same();")]

    assert diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page])) == []


def test_diff_project_event_suffix_variants_match_by_base_name():
    # CustomDrawRow_SimpleHandler and CustomDrawRow_OtherHandler both
    # normalize to base name "CustomDrawRow" and should be matched as the
    # same event (base-name matching, per classify_event_side's suffix rule).
    source_page = make_page("shared_page")
    source_page.events = [make_event("CustomDrawRow_SimpleHandler", "new_impl();")]
    target_page = make_page("shared_page")
    target_page.events = [make_event("CustomDrawRow_OtherHandler", "old_impl();")]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.node_kind == "event"
    assert diff.old_value == "old_impl();"
    assert diff.new_value == "new_impl();"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_differ.py -v`
Expected: FAIL — events are not compared yet, so all five new tests fail.

- [ ] **Step 3: Add event comparison to `compare_block` and a new `_compare_events` helper**

Modify `pgtp_editor/diff/differ.py` — update `compare_block` to call the new helper,
and add `_compare_events`:

```python
def compare_block(source_node, target_node, path, node_kind) -> list[Difference]:
    """Compare a matched pair of nodes that share the Page/Detail shape
    (attrib, columns, events, details), emitting Difference records for:
    - attribute differences on this node itself
    - Column diffs (added/removed/changed), scoped to this parent pair
    - EventHandler diffs (added/removed/changed text), scoped to this parent pair
    (Detail diffing is added in a later task.)

    `node_kind` is the caller's responsibility ("page" or "detail") since
    this helper itself is shape-agnostic.
    """
    differences: list[Difference] = []
    differences.extend(_compare_attributes(source_node, target_node, path=path, node_kind=node_kind))
    differences.extend(_compare_columns(source_node, target_node, path=path))
    differences.extend(_compare_events(source_node, target_node, path=path))
    return differences
```

```python
def _event_base_name(tag_name: str) -> str:
    """Strip the suffix-variant portion of an event tag name, matching
    the exact normalization rule in pgtp_editor.model.nodes.classify_event_side
    (split on the first underscore, keep the left side). Duplicated here as a
    one-line expression rather than imported, because classify_event_side
    itself returns "C"/"S", not the base name in isolation — see Task 6's
    note in the differ-engine plan for the rationale."""
    return tag_name.split("_", 1)[0]


def _compare_events(source_node, target_node, path) -> list[Difference]:
    """Diff EventHandlers (children) of a matched Page/Detail pair, matched
    by base handler name (after suffix normalization), scoped to this
    parent pair only."""
    differences: list[Difference] = []

    target_events_by_base_name = {_event_base_name(e.tag_name): e for e in target_node.events}
    source_base_names = {_event_base_name(e.tag_name) for e in source_node.events}

    for source_event in source_node.events:
        base_name = _event_base_name(source_event.tag_name)
        target_event = target_events_by_base_name.get(base_name)
        event_path = path + [source_event.tag_name]
        if target_event is None:
            differences.append(
                Difference(
                    kind="added",
                    path=event_path,
                    node_kind="event",
                    attribute=None,
                    old_value=None,
                    new_value=source_event,
                )
            )
        elif source_event.text != target_event.text:
            differences.append(
                Difference(
                    kind="changed",
                    path=event_path,
                    node_kind="event",
                    attribute=None,
                    old_value=target_event.text,
                    new_value=source_event.text,
                )
            )

    for target_event in target_node.events:
        base_name = _event_base_name(target_event.tag_name)
        if base_name not in source_base_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=path + [target_event.tag_name],
                    node_kind="event",
                    attribute=None,
                    old_value=target_event,
                    new_value=None,
                )
            )

    return differences
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_differ.py -v`
Expected: PASS (18 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/differ.py tests/diff/test_differ.py
git commit -m "feat(diff): add EventHandler diffing with base-name normalization"
```

---

### Task 7: Detail diffing — scoped `(tableName, caption)` matching with recursion

**Files:**
- Modify: `pgtp_editor/diff/differ.py`
- Test: `tests/diff/test_differ.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_differ.py (append)
from pgtp_editor.model.nodes import DetailNode


def make_detail(table_name, caption, **extra_attrib):
    attrib = {"tableName": table_name, "caption": caption}
    attrib.update(extra_attrib)
    return DetailNode(identity=f"{table_name}/{caption}", attrib=attrib)


def test_diff_project_detail_added():
    detail = make_detail("pr.attachment", "Sub-item")
    source_page = make_page("shared_page")
    source_page.details = [detail]
    target_page = make_page("shared_page")

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["shared_page", "pr.attachment/Sub-item"]
    assert diff.node_kind == "detail"
    assert diff.attribute is None
    assert diff.old_value is None
    assert diff.new_value is detail


def test_diff_project_detail_removed():
    detail = make_detail("pr.attachment", "Sub-item")
    source_page = make_page("shared_page")
    target_page = make_page("shared_page")
    target_page.details = [detail]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "removed"
    assert diff.path == ["shared_page", "pr.attachment/Sub-item"]
    assert diff.node_kind == "detail"
    assert diff.old_value is detail
    assert diff.new_value is None


def test_diff_project_detail_attribute_changed():
    source_detail = make_detail("pr.attachment", "Sub-item", caption="Sub-item")
    source_detail.attrib["ability"] = "insert,edit"
    target_detail = make_detail("pr.attachment", "Sub-item", caption="Sub-item")
    target_detail.attrib["ability"] = "view"

    source_page = make_page("shared_page")
    source_page.details = [source_detail]
    target_page = make_page("shared_page")
    target_page.details = [target_detail]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page", "pr.attachment/Sub-item"]
    assert diff.node_kind == "detail"
    assert diff.attribute == "ability"
    assert diff.old_value == "view"
    assert diff.new_value == "insert,edit"


def test_diff_project_detail_recurses_columns_and_events():
    source_detail = make_detail("pr.attachment", "Sub-item")
    source_detail.columns = [make_column("cvalue", caption="New Caption")]
    target_detail = make_detail("pr.attachment", "Sub-item")
    target_detail.columns = [make_column("cvalue", caption="Old Caption")]

    source_page = make_page("shared_page")
    source_page.details = [source_detail]
    target_page = make_page("shared_page")
    target_page.details = [target_detail]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["shared_page", "pr.attachment/Sub-item", "cvalue"]
    assert diff.node_kind == "column"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Caption"
    assert diff.new_value == "New Caption"


def test_diff_project_matched_details_no_differences():
    source_detail = make_detail("pr.attachment", "Sub-item")
    target_detail = make_detail("pr.attachment", "Sub-item")

    source_page = make_page("shared_page")
    source_page.details = [source_detail]
    target_page = make_page("shared_page")
    target_page.details = [target_detail]

    assert diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page])) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_differ.py -v`
Expected: FAIL — Details are not compared yet, so all five new tests fail.

- [ ] **Step 3: Add Detail comparison to `compare_block` and a new `_compare_details` helper**

Modify `pgtp_editor/diff/differ.py` — update `compare_block` to call the new helper
last (recursion happens after this node's own attribute/column/event comparison), and
add `_compare_details`:

```python
def compare_block(source_node, target_node, path, node_kind) -> list[Difference]:
    """Compare a matched pair of nodes that share the Page/Detail shape
    (attrib, columns, events, details), emitting Difference records for:
    - attribute differences on this node itself
    - Column diffs (added/removed/changed), scoped to this parent pair
    - EventHandler diffs (added/removed/changed text), scoped to this parent pair
    - child Detail diffs (added/removed/changed), recursing into matched pairs

    `node_kind` is the caller's responsibility ("page" or "detail") since
    this helper itself is shape-agnostic.
    """
    differences: list[Difference] = []
    differences.extend(_compare_attributes(source_node, target_node, path=path, node_kind=node_kind))
    differences.extend(_compare_columns(source_node, target_node, path=path))
    differences.extend(_compare_events(source_node, target_node, path=path))
    differences.extend(_compare_details(source_node, target_node, path=path))
    return differences


def _detail_identity_key(detail) -> tuple[str | None, str | None]:
    return (detail.table_name, detail.attrib.get("caption"))
```

Add `_compare_details` after `_compare_events` (the duplicate-sibling ambiguous case is
deliberately deferred to Task 8 — this step handles only the simple 0-or-1-per-key
case; Task 8 will replace this function body to add positional pairing for groups of
size 2+):

```python
def _compare_details(source_node, target_node, path) -> list[Difference]:
    """Diff child Details of a matched Page/Detail pair, matched by
    (tableName, caption), scoped to this parent pair only. Recurses into
    matched pairs via compare_block."""
    differences: list[Difference] = []

    target_details_by_key: dict[tuple, list] = {}
    for target_detail in target_node.details:
        target_details_by_key.setdefault(_detail_identity_key(target_detail), []).append(target_detail)

    source_details_by_key: dict[tuple, list] = {}
    for source_detail in source_node.details:
        source_details_by_key.setdefault(_detail_identity_key(source_detail), []).append(source_detail)

    all_keys = set(source_details_by_key.keys()) | set(target_details_by_key.keys())

    for key in all_keys:
        source_group = source_details_by_key.get(key, [])
        target_group = target_details_by_key.get(key, [])

        for i in range(max(len(source_group), len(target_group))):
            source_detail = source_group[i] if i < len(source_group) else None
            target_detail = target_group[i] if i < len(target_group) else None

            if source_detail is not None and target_detail is not None:
                detail_path = path + [source_detail.identity.rsplit("/", 1)[-1] if False else f"{key[0]}/{key[1]}"]
                differences.extend(
                    compare_block(source_detail, target_detail, path=detail_path, node_kind="detail")
                )
            elif source_detail is not None:
                differences.append(
                    Difference(
                        kind="added",
                        path=path + [f"{key[0]}/{key[1]}"],
                        node_kind="detail",
                        attribute=None,
                        old_value=None,
                        new_value=source_detail,
                    )
                )
            else:
                differences.append(
                    Difference(
                        kind="removed",
                        path=path + [f"{key[0]}/{key[1]}"],
                        node_kind="detail",
                        attribute=None,
                        old_value=target_detail,
                        new_value=None,
                    )
                )

    return differences
```

Note the `detail_path` line has dead code (`source_detail.identity.rsplit(...) if False else ...`)
that must be cleaned up — fix it now to just:

```python
            if source_detail is not None and target_detail is not None:
                detail_path = path + [f"{key[0]}/{key[1]}"]
                differences.extend(
                    compare_block(source_detail, target_detail, path=detail_path, node_kind="detail")
                )
```

(Replace the messier line before running tests — the version above is the one to
actually put in the file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_differ.py -v`
Expected: PASS (23 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/differ.py tests/diff/test_differ.py
git commit -m "feat(diff): add Detail diffing scoped to (tableName, caption) with recursion"
```

---

### Task 8: Nested Details at 2+ levels

**Files:**
- Modify: none (verifies existing recursion handles depth correctly)
- Test: `tests/diff/test_differ.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/diff/test_differ.py (append)

def test_diff_project_nested_details_two_levels_deep_change_detected():
    # top_page -> Detail(pr.level1) -> Detail(pr.level2) with a changed
    # column caption at the deepest level.
    source_level2 = make_detail("pr.level2", "Level2")
    source_level2.columns = [make_column("deep_field", caption="New Deep Caption")]
    source_level1 = make_detail("pr.level1", "Level1")
    source_level1.details = [source_level2]
    source_page = make_page("top_page")
    source_page.details = [source_level1]

    target_level2 = make_detail("pr.level2", "Level2")
    target_level2.columns = [make_column("deep_field", caption="Old Deep Caption")]
    target_level1 = make_detail("pr.level1", "Level1")
    target_level1.details = [target_level2]
    target_page = make_page("top_page")
    target_page.details = [target_level1]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "changed"
    assert diff.path == ["top_page", "pr.level1/Level1", "pr.level2/Level2", "deep_field"]
    assert diff.node_kind == "column"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Deep Caption"
    assert diff.new_value == "New Deep Caption"


def test_diff_project_nested_detail_added_at_second_level():
    source_level1 = make_detail("pr.level1", "Level1")
    source_level1.details = [make_detail("pr.level2", "Level2")]
    source_page = make_page("top_page")
    source_page.details = [source_level1]

    target_level1 = make_detail("pr.level1", "Level1")
    target_page = make_page("top_page")
    target_page.details = [target_level1]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.path == ["top_page", "pr.level1/Level1", "pr.level2/Level2"]
    assert diff.node_kind == "detail"


def test_diff_project_identical_nested_details_no_differences():
    def build_tree():
        level2 = make_detail("pr.level2", "Level2")
        level2.columns = [make_column("deep_field", caption="Same")]
        level1 = make_detail("pr.level1", "Level1")
        level1.details = [level2]
        page = make_page("top_page")
        page.details = [level1]
        return page

    assert diff_project(ProjectModel(pages=[build_tree()]), ProjectModel(pages=[build_tree()])) == []
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `pytest tests/diff/test_differ.py -v`
Expected: PASS immediately — the recursion added in Task 7 (`compare_block` calling
`_compare_details` calling `compare_block` again) already handles arbitrary depth with
no further code changes. This task exists to lock that behavior in with an explicit
regression test, not to add new implementation.

- [ ] **Step 3: Commit**

```bash
git add tests/diff/test_differ.py
git commit -m "test(diff): add regression coverage for 2+ level nested Detail diffing"
```

---

### Task 9: Duplicate-sibling `(tableName, caption)` ambiguous case with positional pairing

**Files:**
- Modify: `pgtp_editor/diff/differ.py`
- Test: `tests/diff/test_differ.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/diff/test_differ.py (append)

def test_diff_project_duplicate_sibling_details_paired_positionally_and_flagged_ambiguous():
    # Two source Details and two target Details share the same
    # (tableName, caption) = ("pr.operation", "Operation"). They should be
    # paired positionally (1st with 1st, 2nd with 2nd) and every resulting
    # Difference record marked ambiguous=True.
    source_first = make_detail("pr.operation", "Operation")
    source_first.attrib["ability"] = "first-source-ability"
    source_second = make_detail("pr.operation", "Operation")
    source_second.attrib["ability"] = "second-source-ability"

    target_first = make_detail("pr.operation", "Operation")
    target_first.attrib["ability"] = "first-target-ability"
    target_second = make_detail("pr.operation", "Operation")
    target_second.attrib["ability"] = "second-target-ability"

    source_page = make_page("shared_page")
    source_page.details = [source_first, source_second]
    target_page = make_page("shared_page")
    target_page.details = [target_first, target_second]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 2
    for diff in result:
        assert diff.ambiguous is True
        assert diff.kind == "changed"
        assert diff.node_kind == "detail"
        assert diff.attribute == "ability"

    by_old_value = {d.old_value: d for d in result}
    assert by_old_value["first-target-ability"].new_value == "first-source-ability"
    assert by_old_value["second-target-ability"].new_value == "second-source-ability"


def test_diff_project_duplicate_sibling_details_extra_on_source_side_marked_ambiguous():
    # 2 source Details, 1 target Detail sharing the same key: the 1st pair
    # matches (ambiguous, since the group has size > 1), the 2nd source
    # Detail has no target counterpart and is an ambiguous Added record.
    source_first = make_detail("pr.operation", "Operation")
    source_second = make_detail("pr.operation", "Operation")
    target_first = make_detail("pr.operation", "Operation")

    source_page = make_page("shared_page")
    source_page.details = [source_first, source_second]
    target_page = make_page("shared_page")
    target_page.details = [target_first]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    diff = result[0]
    assert diff.kind == "added"
    assert diff.node_kind == "detail"
    assert diff.new_value is source_second
    assert diff.ambiguous is True


def test_diff_project_single_detail_per_key_not_marked_ambiguous():
    # Sanity check: a group of size 1 on both sides (the normal case,
    # already covered by Task 7's tests) must NOT be flagged ambiguous.
    source_detail = make_detail("pr.attachment", "Sub-item")
    source_detail.attrib["ability"] = "new-ability"
    target_detail = make_detail("pr.attachment", "Sub-item")
    target_detail.attrib["ability"] = "old-ability"

    source_page = make_page("shared_page")
    source_page.details = [source_detail]
    target_page = make_page("shared_page")
    target_page.details = [target_detail]

    result = diff_project(ProjectModel(pages=[source_page]), ProjectModel(pages=[target_page]))

    assert len(result) == 1
    assert result[0].ambiguous is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/diff/test_differ.py -v`
Expected: FAIL — the current `_compare_details` never sets `ambiguous=True`, so the
first two new tests fail (they assert `ambiguous is True` but get `False`). The third
test already passes (no regression risk there, but keep it to lock in the non-ambiguous
default).

- [ ] **Step 3: Update `_compare_details` to flag ambiguous groups and propagate the flag through recursion**

Replace `_compare_details` in `pgtp_editor/diff/differ.py`. Because a `changed` record
for an ambiguous pair must have `ambiguous=True` even when it's discovered several
levels deep inside `compare_block`'s recursive attribute/column/event comparison, add an
`ambiguous` parameter to `compare_block` and thread it through:

```python
def compare_block(source_node, target_node, path, node_kind, ambiguous=False) -> list[Difference]:
    """Compare a matched pair of nodes that share the Page/Detail shape
    (attrib, columns, events, details), emitting Difference records for:
    - attribute differences on this node itself
    - Column diffs (added/removed/changed), scoped to this parent pair
    - EventHandler diffs (added/removed/changed text), scoped to this parent pair
    - child Detail diffs (added/removed/changed), recursing into matched pairs

    `node_kind` is the caller's responsibility ("page" or "detail") since
    this helper itself is shape-agnostic. `ambiguous` is True when this pair
    itself was matched via the duplicate-(tableName, caption)-sibling
    positional-pairing fallback (see _compare_details) and propagates to
    every Difference record produced for this node and its descendants,
    since none of them can be trusted as confidently as an unambiguous match.
    """
    differences: list[Difference] = []
    differences.extend(
        _compare_attributes(source_node, target_node, path=path, node_kind=node_kind, ambiguous=ambiguous)
    )
    differences.extend(_compare_columns(source_node, target_node, path=path, ambiguous=ambiguous))
    differences.extend(_compare_events(source_node, target_node, path=path, ambiguous=ambiguous))
    differences.extend(_compare_details(source_node, target_node, path=path, ambiguous=ambiguous))
    return differences
```

Update `_compare_attributes`, `_compare_columns`, and `_compare_events` to accept and
propagate an `ambiguous` parameter (default `False` to keep every earlier task's
tests passing unchanged):

```python
def _compare_attributes(source_node, target_node, path, node_kind, ambiguous=False) -> list[Difference]:
    """Compare source_node.attrib vs target_node.attrib, emitting one
    Changed record per differing attribute key. Covers keys present on
    either side (a key missing on one side counts as differing from
    whatever value the other side has, defaulting the missing side to
    None)."""
    differences: list[Difference] = []
    all_keys = set(source_node.attrib.keys()) | set(target_node.attrib.keys())
    for key in sorted(all_keys):
        source_value = source_node.attrib.get(key)
        target_value = target_node.attrib.get(key)
        if source_value != target_value:
            differences.append(
                Difference(
                    kind="changed",
                    path=list(path),
                    node_kind=node_kind,
                    attribute=key,
                    old_value=target_value,
                    new_value=source_value,
                    ambiguous=ambiguous,
                )
            )
    return differences


def _compare_columns(source_node, target_node, path, ambiguous=False) -> list[Difference]:
    """Diff Columns (children) of a matched Page/Detail pair, matched by
    fieldName, scoped to this parent pair only."""
    differences: list[Difference] = []

    target_columns_by_field_name = {c.field_name: c for c in target_node.columns}
    source_field_names = {c.field_name for c in source_node.columns}

    for source_column in source_node.columns:
        target_column = target_columns_by_field_name.get(source_column.field_name)
        column_path = path + [source_column.field_name]
        if target_column is None:
            differences.append(
                Difference(
                    kind="added",
                    path=column_path,
                    node_kind="column",
                    attribute=None,
                    old_value=None,
                    new_value=source_column,
                    ambiguous=ambiguous,
                )
            )
        else:
            differences.extend(
                _compare_attributes(
                    source_column, target_column, path=column_path, node_kind="column", ambiguous=ambiguous
                )
            )

    for target_column in target_node.columns:
        if target_column.field_name not in source_field_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=path + [target_column.field_name],
                    node_kind="column",
                    attribute=None,
                    old_value=target_column,
                    new_value=None,
                    ambiguous=ambiguous,
                )
            )

    return differences


def _event_base_name(tag_name: str) -> str:
    """Strip the suffix-variant portion of an event tag name, matching
    the exact normalization rule in pgtp_editor.model.nodes.classify_event_side
    (split on the first underscore, keep the left side). Duplicated here as a
    one-line expression rather than imported, because classify_event_side
    itself returns "C"/"S", not the base name in isolation — see Task 6's
    note in the differ-engine plan for the rationale."""
    return tag_name.split("_", 1)[0]


def _compare_events(source_node, target_node, path, ambiguous=False) -> list[Difference]:
    """Diff EventHandlers (children) of a matched Page/Detail pair, matched
    by base handler name (after suffix normalization), scoped to this
    parent pair only."""
    differences: list[Difference] = []

    target_events_by_base_name = {_event_base_name(e.tag_name): e for e in target_node.events}
    source_base_names = {_event_base_name(e.tag_name) for e in source_node.events}

    for source_event in source_node.events:
        base_name = _event_base_name(source_event.tag_name)
        target_event = target_events_by_base_name.get(base_name)
        event_path = path + [source_event.tag_name]
        if target_event is None:
            differences.append(
                Difference(
                    kind="added",
                    path=event_path,
                    node_kind="event",
                    attribute=None,
                    old_value=None,
                    new_value=source_event,
                    ambiguous=ambiguous,
                )
            )
        elif source_event.text != target_event.text:
            differences.append(
                Difference(
                    kind="changed",
                    path=event_path,
                    node_kind="event",
                    attribute=None,
                    old_value=target_event.text,
                    new_value=source_event.text,
                    ambiguous=ambiguous,
                )
            )

    for target_event in target_node.events:
        base_name = _event_base_name(target_event.tag_name)
        if base_name not in source_base_names:
            differences.append(
                Difference(
                    kind="removed",
                    path=path + [target_event.tag_name],
                    node_kind="event",
                    attribute=None,
                    old_value=target_event,
                    new_value=None,
                    ambiguous=ambiguous,
                )
            )

    return differences


def _detail_identity_key(detail) -> tuple[str | None, str | None]:
    return (detail.table_name, detail.attrib.get("caption"))


def _compare_details(source_node, target_node, path, ambiguous=False) -> list[Difference]:
    """Diff child Details of a matched Page/Detail pair, matched by
    (tableName, caption), scoped to this parent pair only. Recurses into
    matched pairs via compare_block.

    If more than one sibling Detail on either side shares the same
    (tableName, caption) key, the extras are paired positionally (1st extra
    with 1st extra, 2nd with 2nd, etc.) and every Difference record produced
    from that group -- including all descendants found via recursion -- is
    marked ambiguous=True, per the design spec's duplicate-sibling handling.
    A group of size 1 on both sides is the normal, unambiguous case and is
    not affected by the `ambiguous` flag introduced here (unless the caller
    itself already passed ambiguous=True, e.g. because this Detail pair is
    nested inside an outer ambiguous group).
    """
    differences: list[Difference] = []

    target_details_by_key: dict[tuple, list] = {}
    for target_detail in target_node.details:
        target_details_by_key.setdefault(_detail_identity_key(target_detail), []).append(target_detail)

    source_details_by_key: dict[tuple, list] = {}
    for source_detail in source_node.details:
        source_details_by_key.setdefault(_detail_identity_key(source_detail), []).append(source_detail)

    all_keys = set(source_details_by_key.keys()) | set(target_details_by_key.keys())

    for key in all_keys:
        source_group = source_details_by_key.get(key, [])
        target_group = target_details_by_key.get(key, [])
        group_is_ambiguous = ambiguous or len(source_group) > 1 or len(target_group) > 1

        for i in range(max(len(source_group), len(target_group))):
            source_detail = source_group[i] if i < len(source_group) else None
            target_detail = target_group[i] if i < len(target_group) else None
            detail_path = path + [f"{key[0]}/{key[1]}"]

            if source_detail is not None and target_detail is not None:
                differences.extend(
                    compare_block(
                        source_detail,
                        target_detail,
                        path=detail_path,
                        node_kind="detail",
                        ambiguous=group_is_ambiguous,
                    )
                )
            elif source_detail is not None:
                differences.append(
                    Difference(
                        kind="added",
                        path=detail_path,
                        node_kind="detail",
                        attribute=None,
                        old_value=None,
                        new_value=source_detail,
                        ambiguous=group_is_ambiguous,
                    )
                )
            else:
                differences.append(
                    Difference(
                        kind="removed",
                        path=detail_path,
                        node_kind="detail",
                        attribute=None,
                        old_value=target_detail,
                        new_value=None,
                        ambiguous=group_is_ambiguous,
                    )
                )

    return differences
```

**Judgment call on tie-break within positional pairing:** the spec (§3.2) says "pair
the extras positionally (1st extra with 1st extra, 2nd with 2nd, etc.)" but doesn't
specify what "extra" means when the groups aren't the same size (e.g. 2 source vs 1
target, as in the second new test above). This implementation treats the *whole* group
positionally by index from the start — i.e. `source_group[0]` pairs with
`target_group[0]` (not just the "extras" beyond the first match), and any index beyond
the shorter list's length becomes a plain Added/Removed record. This is the simplest
interpretation consistent with "positionally" and matches the second test's expectation
(`source_second`, at index 1, has no `target_group[1]`, so it's Added). No other order
(e.g. matching by which attributes happen to be more similar) is implied by the spec,
and adding similarity-based matching would contradict the spec's explicit preference for
positional (i.e. order-based, not content-based) pairing in the ambiguous case.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/diff/test_differ.py -v`
Expected: PASS (26 passed)

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/diff/differ.py tests/diff/test_differ.py
git commit -m "feat(diff): handle duplicate-sibling Detail matching with positional pairing and ambiguous flag"
```

---

### Task 10: Confirm `sample/` fixtures are present before writing integration tests

**Files:** none (verification step only)

The two sample `.pgtp` files needed for Task 11 live under `sample/` at the repo root.
That directory is listed in `.gitignore`, so it is never committed — it must be present
on disk already, copied in manually by whoever set up the worktree.

- [ ] **Step 1: Check whether `sample/` already has both files**

Run (from the repo root):

```bash
ls sample/dev_Ferrara.pgtp sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp
```

Expected: both files listed, no "No such file or directory" errors.

- [ ] **Step 2: If either file is missing, copy it from the model sub-project's worktree**

Only run this if Step 1 reported a missing file. Adjust the source path if the model
worktree lives elsewhere on the machine running this plan:

```bash
mkdir -p sample
cp "../pgtp-editor-model/sample/dev_Ferrara.pgtp" sample/dev_Ferrara.pgtp
cp "../pgtp-editor-model/sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp" sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp
```

- [ ] **Step 3: Re-verify both files are now present**

Run:

```bash
ls sample/dev_Ferrara.pgtp sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp
```

Expected: both files listed. No commit for this task — `sample/` is gitignored and
must never be added to git.

---

### Task 11: Integration tests — real sample files self-diff to an empty list

**Files:**
- Create: `tests/diff/test_differ_integration.py`

- [ ] **Step 1: Write the tests**

```python
# tests/diff/test_differ_integration.py
"""Regression tests: diffing a real sample file against itself must produce
an empty list. This is a strong sanity check that the algorithm doesn't
spuriously report differences from e.g. dict-ordering assumptions or
unstable duplicate-pairing, when there are none.

Requires sample/*.pgtp to be present on disk (gitignored — see Task 10 of
docs/superpowers/plans/2026-07-12-pgtp-editor-differ-engine.md for how to
populate it if missing).
"""
from pathlib import Path

import pytest

from pgtp_editor.model.parser import load_project
from pgtp_editor.diff.differ import diff_project

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"


def _load_twice(filename):
    path = SAMPLE_DIR / filename
    if not path.exists():
        pytest.skip(f"sample fixture not present on disk: {path}")
    return load_project(path), load_project(path)


def test_dev_ferrara_self_diff_is_empty():
    source, target = _load_twice("dev_Ferrara.pgtp")
    assert diff_project(source, target) == []


def test_sdman_renco_strikes_back_self_diff_is_empty():
    source, target = _load_twice("Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp")
    assert diff_project(source, target) == []
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/diff/test_differ_integration.py -v`
Expected: PASS (2 passed) if `sample/` was populated in Task 10. If either fixture is
still missing, the corresponding test reports SKIPPED rather than FAILED or ERROR —
revisit Task 10 before treating this task as complete.

- [ ] **Step 3: If a test fails (not skips) with a non-empty diff list, debug before proceeding**

A failure here (as opposed to a skip) means the algorithm has a real bug — e.g. an
attribute comparison that's sensitive to dict key order, or a duplicate-sibling group
whose positional pairing isn't stable between two independent parses of the same file.
Print the failing diffs to investigate:

```bash
pytest tests/diff/test_differ_integration.py -v -s
```

Add a temporary `print(result)` in the test if needed to inspect which `Difference`
records appeared unexpectedly, find the root cause in `differ.py`, fix it, and re-run
before moving on. Do not weaken the test (e.g. by excluding fields from comparison) to
make it pass — the whole point of this test is that self-diff must be exactly empty.

- [ ] **Step 4: Commit**

```bash
git add tests/diff/test_differ_integration.py
git commit -m "test(diff): add real-sample-file self-diff integration tests"
```

---

### Task 12: Full suite verification

**Files:** none (verification step only)

- [ ] **Step 1: Run the entire `diff` test package**

Run: `pytest tests/diff/ -v`
Expected: all tests PASS (28 passed, assuming both sample fixtures were present for
Task 11; 26 passed + 2 skipped if fixtures were unavailable and Task 10's copy step
could not be completed on this machine).

- [ ] **Step 2: Run the entire project test suite to confirm no cross-package regressions**

Run: `pytest -v`
Expected: all tests PASS, including the pre-existing `tests/ui/` suite and the model
layer's `tests/model/` suite (once merged), plus every new `tests/diff/` test.

- [ ] **Step 3: Confirm no Qt import leaked into the diff package**

Run:

```bash
grep -rn "PySide6\|PyQt" pgtp_editor/diff/
```

Expected: no output (empty match) — confirms the diff package has zero Qt dependency,
per the design spec's §3.1 layering rule.

No commit for this task — it's verification only, and Task 11 already committed the
last substantive change.

---

## Self-review notes

Spec coverage checked section by section:

- §2.1/§3.1 module layout (`diff/__init__.py`, `diff/differ.py`, `diff/records.py`) — Task 1 (`__init__.py`, `records.py`), Task 2 (`differ.py`).
- §3.2 algorithm: Page matching by `fileName` — Task 2/3. `compare_block` shared recursive helper — Task 5 (extraction), used by both Page pairs (Task 2/3) and Detail pairs (Task 7).
- §3.2 attribute comparison over `source_node.attrib`/`target_node.attrib` — Task 3's `_compare_attributes`.
- §3.2 Column diffing matched by `fieldName`, scoped to parent pair — Task 4.
- §3.2 EventHandler diffing matched by base name after suffix normalization, reusing the model layer's rule — Task 6.
- §3.2 Detail diffing matched by `(tableName, caption)` scoped to parent, recursing via `compare_block` — Task 7.
- §3.2 duplicate-sibling positional pairing + `ambiguous` flag — Task 9.
- §3.3 Detail matching scoped to parent, not global — Task 7 (matching keyed within `_compare_details`, never across the whole project).
- §3.4 no cross-parent "moved" detection — never implemented anywhere in this plan; a relocated Detail naturally falls out as a Removed record from `_compare_details` under the old parent and an Added record under the new parent, with no special-casing needed (implicit correctness, not a separate task, since the parent-scoping in Task 7 already guarantees this).
- §3.5 `Difference` record shape, exact field names and types — Task 1.
- §4 testing strategy: synthetic fixtures for Page/Column/Event add-remove-changed — Tasks 2-3-4-6. Nested Detail 2+ levels — Task 8. Duplicate-sibling ambiguous case — Task 9. Integration tests against both real sample files — Task 10 (fixture check) + Task 11 (tests).

Placeholder scan: no "TBD"/"similar to Task N"/"add appropriate handling" language remains; every step shows complete code. Task 8 intentionally has no implementation step because the spec's requirement (2+ level nesting) is already satisfied by Task 7's recursive `compare_block`/`_compare_details` pairing — this is called out explicitly in Task 8 rather than left implicit, and is backed by a real regression test, not just an assertion in prose.

Type/name consistency checked: `Difference.kind` uses only `"added"`/`"removed"`/`"changed"` string literals across every task (Tasks 2-3-4-6-7-9). `node_kind` uses only `"page"`/`"detail"`/`"column"`/`"event"` across every task. `compare_block(source_node, target_node, path, node_kind, ambiguous=False)` signature is introduced in Task 5 and extended (not renamed) in Task 9 by adding the `ambiguous` parameter with a default, so every earlier call site (Task 5's `diff_project`, Task 7's `_compare_details`) keeps working unchanged. `_compare_attributes`/`_compare_columns`/`_compare_events`/`_compare_details` all gain the same `ambiguous=False`-defaulted parameter in Task 9, keeping every earlier task's direct-call test still valid without modification.

**One inconsistency found and fixed during review:** Task 7's first draft of `_compare_details` contained a dead-code conditional expression (`source_detail.identity.rsplit("/", 1)[-1] if False else f"{key[0]}/{key[1]}"`) left over from drafting. The step's final code block was corrected in place to the clean `f"{key[0]}/{key[1]}"` form before the task's "run tests" step, with an explicit note in the task telling the implementer to use the corrected version — this is called out inline rather than silently left in, since a worker executing tasks out of order or copy-pasting the first block verbatim would otherwise ship dead code.
</content>
