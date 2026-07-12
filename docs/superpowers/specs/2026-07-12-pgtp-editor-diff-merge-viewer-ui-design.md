# PGTP Editor — Diff/Merge Viewer UI (Diff/Merge Sub-project 2 of 3+) Design Specification

**Date:** 2026-07-12
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design, §5.2 menu bar, §5.3 context menus, §6.1 Diff/Merge), the completed Differ Engine sub-project ([2026-07-12-pgtp-editor-differ-engine-design.md](2026-07-12-pgtp-editor-differ-engine-design.md), `pgtp_editor/diff/differ.py`, `pgtp_editor/diff/records.py`), and the completed Real Model sub-project (`pgtp_editor/model/nodes.py`, `pgtp_editor/model/parser.py`).

## 1. Context and scope

This is the second of at least three sub-projects that together deliver the **Diff/Merge** feature sketched at a high level in §6.1 of the original design spec. The sub-projects, in dependency order:

1. **Differ engine** (done — [2026-07-12-pgtp-editor-differ-engine-design.md](2026-07-12-pgtp-editor-differ-engine-design.md), `pgtp_editor/diff/differ.py`, `pgtp_editor/diff/records.py`) — pure comparison logic that walks two loaded `ProjectModel` trees and produces a flat list of `Difference` records. No UI, no file I/O.
2. **Diff/Merge viewer UI** (this document) — the three ways to launch a comparison (file-level, page-level, detail-level), a read-only change-list tree and detail view populating the existing empty "Diff / Merge" center-stage tab, and Next/Prev Difference navigation. Depends on sub-project 1's engine. No write-back to disk.
3. **Serialization / round-trip fidelity + Apply** — the actual "Apply Changes to Target" behavior: turning a set of checked `Difference` records into mutations of the Target `ProjectModel`, serializing it back to `.pgtp` XML with round-trip fidelity, and the `.bak` backup mechanism. Depends on this document's UI (the Apply/Skip selections it collects). Gets its own brainstorm/spec/plan cycle once this one is built and merged.

This document covers only sub-project 2.

**Why the viewer comes before Apply:** sub-project 1 produced a `Difference` record shape and comparison algorithm, but nothing yet turns that into something a developer can look at and decide about. Before "Apply Changes to Target" can mean anything, there needs to be a concrete way to launch a comparison from the three entry points already sketched in the original design spec (§5.2, §5.3), a way to see the resulting differences organized by location in the tree, and a way to inspect what a specific difference actually contains (an attribute change, a whole added/removed subtree, or an event-handler text change) — all fully buildable and testable against synthetic `Difference` lists, without needing the write-back mechanism sub-project 3 will add.

**Terminology** (matching §6.1 of the original design and the differ-engine spec): the two inputs being compared are **Source** and **Target**. This sub-project's UI shows what the differ found; it does not patch anything.

## 2. Scope

### 2.1 In scope

- Three comparison entry points, all producing the same shared viewer:
  1. **File-level** — "Compare / Merge Two Files..." menu item (already stubbed in `main_window.py`'s `_build_diff_merge_menu`).
  2. **Page-level** — "Compare This Page With..." context-menu entry on a Page in the Project Tree (already stubbed in `project_tree.py`'s `build_page_menu`).
  3. **Detail-level** — "Compare This Detail With..." context-menu entry on a Detail in the Project Tree (already stubbed in `project_tree.py`'s `build_detail_menu`).
- A new `resolve_path(project, path) -> PageNode | DetailNode | None` helper (with structured failure information — see §3.4) that walks a `ProjectModel` down a path of identity segments, used by the Detail-level entry point.
- A new `pgtp_editor/ui/diff_merge_panel.py` widget populating the existing empty "Diff / Merge" center-stage tab (`CenterStage.diff_merge_tab_index`): a change-list tree, a detail view, and Apply/Skip checkboxes (selection state only — no write-back).
- Wiring "Next Difference" / "Prev Difference" (already stubbed in `main_window.py`'s `_build_diff_merge_menu`) to navigate the change-list tree's leaf nodes.
- Clear, specific error reporting (via `QMessageBox.critical`, matching the existing `_open_project`/`open_project_file` pattern) whenever a target file fails to parse, or a Page/Detail named in a comparison request can't be found in the target project — never a silent empty or wrong result.

### 2.2 Explicitly out of scope (this sub-project)

- Any writing of `.pgtp` files to disk, the `.bak` backup mechanism, and the actual "Apply Changes to Target" behavior. All sub-project 3. "Apply Changes to Target" stays exactly as currently stubbed (`_add_stub_action`, showing "Not yet implemented: Apply Changes to Target").
- The §6.4 reused-table coherence *feature* itself — the "Find Reused Tables..." scan and the "Compare with Other Instance..." menu item that lists other instances of the same table within one file. This sub-project only builds the underlying "compare any two resolved subtrees and show a viewer" capability (via `resolve_path` and the shared viewer) that a future reused-table sub-project would call into; it does not build the scanning/listing UI that finds candidate instances.
- Any change to the differ engine (`pgtp_editor/diff/differ.py`, `pgtp_editor/diff/records.py`) itself. This sub-project only consumes `diff_project`/`compare_block`/`Difference` as they already exist, plus the new `resolve_path` addition described in §3.4.
- Persisting Apply/Skip checkbox state across sessions, or between separate Compare invocations. It is fresh, in-memory, per-comparison-session state only, held in the tree widget itself.
- Colored/syntax-highlighted diff rendering for event-handler text. A stdlib-only, text-only unified diff is sufficient for this sub-project (see §3.3).

## 3. Architecture

### 3.1 Module layout

```
pgtp_editor/
├── diff/
│   ├── __init__.py
│   ├── differ.py        # unchanged — diff_project/compare_block from sub-project 1
│   ├── records.py        # unchanged — Difference dataclass from sub-project 1
│   └── resolve.py        # NEW: resolve_path(project, path) -> PageNode | DetailNode | None
├── ui/
│   ├── main_window.py     # gains real handlers for "Compare / Merge Two Files...",
│   │                       # "Next Difference", "Prev Difference"; tracks the
│   │                       # currently-open project (new attribute, see §3.5)
│   ├── project_tree.py    # "Compare This Page With..." / "Compare This Detail
│   │                       # With..." become real handlers instead of stub actions
│   ├── center_stage.py     # unchanged in shape — diff_merge_tab_index's QWidget
│   │                       # placeholder is replaced with a DiffMergePanel instance
│   └── diff_merge_panel.py # NEW: DiffMergePanel — change-list tree + detail view
```

**Why `resolve_path` lives in `diff/`, not `ui/`:** it walks a `ProjectModel` using exactly the same matching rules `differ.py` already uses internally (`fileName` for a top-level Page, `(tableName, caption)` scoped to a parent for a Detail) — it is a read of the model layer's identity scheme, not a UI concern. Putting it in `ui/diff_merge_panel.py` would mean the "what does it mean for two nodes to be the same" logic lives in two different layers (once inside `_compare_details`'s matching, once again in a UI module), which is exactly the kind of duplicated-identity-logic risk the differ-engine spec flagged for `_event_base_name` versus `classify_event_side` (see that document's §3.2 note). `diff/` already depends on `model/` and has zero Qt imports; `resolve.py` preserves that — it takes and returns plain `ProjectModel`/`PageNode`/`DetailNode` objects, no Qt types, so it stays unit-testable without a `QApplication`. This is also exactly the "reused at Detail-subtree scope later" wiring the differ-engine spec's §2.2 explicitly deferred ("expected to reuse this same engine at Detail-subtree scope later, but wiring that up is not part of this sub-project") — this sub-project is that later wiring, and `diff/` is where that wiring belongs since it's engine-adjacent, not viewer-specific.

### 3.2 The three entry points

All three end at the same place: a `list[Difference]` handed to `DiffMergePanel.show_differences(differences)`, which populates the change-list tree and switches the center stage to the "Diff / Merge" tab.

**1. File-level — "Compare / Merge Two Files..."**

```
_compare_merge_two_files():
    source = self._current_project   # see §3.5 — currently-open project, if any
    if source is None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Source Project", "", "PGTP files (*.pgtp)")
        if not path: return
        source = load_project(path)   # QMessageBox.critical on failure, matching open_project_file
    target_path, _ = QFileDialog.getOpenFileName(self, "Select Target Project", "", "PGTP files (*.pgtp)")
    if not target_path: return
    target = load_project(target_path)   # QMessageBox.critical on failure
    differences = diff_project(source, target)
    self.center_stage.diff_merge_panel.show_differences(differences)
    self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)
```

Source defaults to the currently-open project (see §3.5 for how "currently open" is tracked) without prompting; Target always prompts via `QFileDialog`, mirroring `_open_project`'s existing `QFileDialog.getOpenFileName(..., "PGTP files (*.pgtp)")` pattern and its `QMessageBox.critical` failure handling.

**2. Page-level — "Compare This Page With..." (Project Tree context menu)**

```
_compare_page_with(page_node):
    target_path, _ = QFileDialog.getOpenFileName(self, "Select Target Project", "", "PGTP files (*.pgtp)")
    if not target_path: return
    target = load_project(target_path)   # QMessageBox.critical on failure
    target_page = next((p for p in target.pages if p.file_name == page_node.file_name), None)
    if target_page is None:
        QMessageBox.critical(self, "Page Not Found",
            f"No Page with fileName '{page_node.file_name}' exists in '{target_path}'.")
        return
    differences = compare_block(page_node, target_page, path=[page_node.file_name], node_kind="page")
    self.center_stage.diff_merge_panel.show_differences(differences)
    self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)
```

`compare_block`'s real signature (confirmed from `pgtp_editor/diff/differ.py`) is `compare_block(source_node, target_node, path, node_kind, ambiguous=False)` — `ambiguous` defaults to `False` and does not need to be passed here; a single matched Page pair found by exact `fileName` match is never itself an ambiguous match (ambiguity is a property of the duplicate-sibling-Detail case inside the recursion, not of this top-level lookup).

The target Page is found by scanning `target.pages` for a matching `file_name` — the same global-uniqueness rule `diff_project` itself relies on (§3.3 of the differ-engine spec). If no match exists, this is reported with the specific missing `fileName`, never a silent empty comparison.

**3. Detail-level — "Compare This Detail With..." (Project Tree context menu)**

```
_compare_detail_with(detail_node, source_path):
    # source_path: list[str] of identity segments from the project root down to
    # detail_node, matching how Difference.path is built (see §3.3 below) —
    # constructed by the Project Tree from the ancestor chain of the clicked item.
    target_path_str, _ = QFileDialog.getOpenFileName(self, "Select Target Project", "", "PGTP files (*.pgtp)")
    if not target_path_str: return
    target = load_project(target_path_str)   # QMessageBox.critical on failure
    result = resolve_path(target, source_path)
    if result is None or isinstance(result, ResolutionError):
        QMessageBox.critical(self, "Detail Not Found", result.message)   # see §3.4
        return
    differences = compare_block(detail_node, result, path=source_path, node_kind="detail")
    self.center_stage.diff_merge_panel.show_differences(differences)
    self.center_stage.setCurrentIndex(self.center_stage.diff_merge_tab_index)
```

This is the one entry point that needs `resolve_path` (§3.4): the target Detail isn't found by a single top-level lookup, it's found by walking the same path down the target tree, resolving each segment with the exact matching rule the differ itself uses at that level.

### 3.3 Building `source_path` from the Project Tree

`resolve_path` needs a `path: list[str]` describing the clicked Detail's location using the same identity segments `compare_block`/`_compare_details` already use internally: the top-level Page's `file_name`, then each Detail's `(table_name, caption)` pair down to the clicked node. `_compare_details` (in `differ.py`) builds its own `Difference.path` segments as `f"{key[0]}/{key[1]}"` where `key = (detail.table_name, attrib.get("caption"))` — i.e. one combined `"tableName/caption"` string per Detail level, not two separate list entries. `resolve_path`'s `path` parameter uses this same one-segment-per-level convention (`[file_name, "tableName1/caption1", "tableName2/caption2", ...]`) so a `Difference.path` produced by the engine and a `path` passed into `resolve_path` are the same shape and can be built/parsed with the same logic. The Project Tree already holds, on each `QTreeWidgetItem`, the underlying model node (via the existing `NODE_KIND_ROLE`/`TABLE_NAME_ROLE` item-data pattern in `project_tree.py`); the handler walks up from the clicked item to the root, reading each ancestor's `PageNode.file_name` or `DetailNode.table_name`/`attrib.get("caption")` to build the path in root-to-leaf order.

### 3.4 `resolve_path`

New module `pgtp_editor/diff/resolve.py`:

```python
def resolve_path(project: ProjectModel, path: list[str]) -> PageNode | DetailNode | ResolutionError:
    ...
```

Signature notes:

- `path` is non-empty; `path[0]` is always a top-level Page's `file_name`, and `path[1:]` are `"tableName/caption"` Detail segments, per §3.3.
- Returns the resolved `PageNode` (if `len(path) == 1`) or `DetailNode` (otherwise) on success.
- On failure, returns a `ResolutionError` (a small dataclass: `segment_index: int`, `message: str`) rather than a bare `None`, so the calling UI code can build a precise error message naming exactly which segment failed (e.g. `"no Page named 'development_equipment'"` at index 0, or `"no Detail matching (tableName='r_characteristic', caption='Attachment') under development_equipment/pr_attachment"` at a deeper index) — this is why the function signature above is written as `PageNode | DetailNode | ResolutionError` rather than `... | None`: a bare `None` cannot carry "which segment, and why," and the brainstorm requirement is that an unresolvable path must "show a clear error naming the specific unresolvable segment," never a silent empty/wrong result.
- Matching rule per level, mirroring `differ.py` exactly (not a re-derivation of it): at segment 0, find the Page in `project.pages` with `file_name == path[0]` (same lookup `diff_project` and `_compare_page_with` already use). At each subsequent segment, parse it back into `(table_name, caption)` and find the Detail in the current node's `.details` with a matching `_detail_identity_key`-equivalent pair, scoped to the current node only (never searching the whole project) — the same scoping rule `_compare_details` uses. If more than one sibling Detail matches the same `(table_name, caption)` at that level (the duplicate-sibling case `_compare_details` handles with positional pairing), `resolve_path` picks the first match rather than attempting positional pairing itself — there is no "positional" concept to align against here since `resolve_path` is locating a single already-chosen source node's counterpart, not diffing two whole sibling groups; this is a deliberate simplification for this sub-project, not an attempt to replicate the differ's ambiguous-pairing logic in reverse.

### 3.5 Tracking the "currently open" project

`MainWindow` currently has no attribute holding the last-loaded `ProjectModel` — `open_project_file` loads it, calls `self.project_tree.populate_from_project(project)`, and lets the local `project` variable go out of scope. This sub-project adds `self._current_project: ProjectModel | None = None` (and, for symmetry with the tree's own display needs, `self._current_project_path: str | None = None`), set at the end of `open_project_file` alongside the existing `populate_from_project` call. "Compare / Merge Two Files..." reads `self._current_project` to decide whether to prompt for Source (see §3.2); the Page-level and Detail-level entry points don't need this attribute at all, since their Source is always the specific node that was right-clicked in the already-populated tree.

### 3.6 `DiffMergePanel` (`pgtp_editor/ui/diff_merge_panel.py`)

Replaces the placeholder `QWidget()` currently installed at `CenterStage.diff_merge_tab_index`. Internally a `QSplitter` (horizontal orientation: change-list tree on the left, detail view on the right) — this follows the same "resizable, dockable panels" spirit already established for the app's docked panels (§5.1 of the original design spec), applied here within a single center-stage tab rather than as a separate dock, since the change-list and detail view are two halves of one tab's content rather than independently toggleable panels.

**Change-list tree (`QTreeWidget`, left pane)**

Built fresh from a flat `list[Difference]` each time `show_differences` is called (clearing any previous content — one comparison session at a time, per the out-of-scope note on cross-session state in §2.2). Construction walks each `Difference.path` and creates or reuses intermediate `QTreeWidgetItem` nodes for shared path prefixes:

```
build_tree(differences):
    root_items_by_prefix: dict[tuple[str, ...], QTreeWidgetItem] = {}
    for diff in differences:
        *prefix_segments, _ = diff.path
        parent = None
        accumulated: tuple[str, ...] = ()
        for segment in prefix_segments:
            accumulated += (segment,)
            item = root_items_by_prefix.get(accumulated)
            if item is None:
                item = QTreeWidgetItem([segment])
                (parent.addChild(item) if parent else tree.addTopLevelItem(item))
                root_items_by_prefix[accumulated] = item
            parent = item
        leaf = QTreeWidgetItem([leaf_label(diff)])
        leaf.setData(0, DIFFERENCE_ROLE, diff)
        (parent.addChild(leaf) if parent else tree.addTopLevelItem(leaf))
```

This is the same general shape as `ProjectTreePanel`'s own tree-building (`populate_from_project`/`_populate_details_and_events`), adapted from walking a `ProjectModel`'s real parent/child object graph to walking a flat list of `Difference.path` lists and de-duplicating shared prefixes via a dict keyed by the accumulated path tuple, since there is no pre-built node graph to recurse over here — only a flat list of records, each carrying its own full path from the root.

*Leaf label formatting* (`leaf_label(diff)`) combines `node_kind`, `attribute` (when present), and `kind`:

| Example `Difference` | Label |
|---|---|
| `node_kind="detail"`, `attribute="caption"`, `kind="changed"` | `caption: changed` |
| `node_kind="event"`, `attribute=None`, `kind="added"`, path ends in `"OnRowProcess"` | `OnRowProcess: added` |
| `node_kind="detail"`, `attribute=None`, `kind="removed"`, path ends in `"pr.attachment/Sub-item"` | `pr.attachment/Sub-item: removed` |

General rule: `f"{attribute}: {kind}"` when `attribute` is not `None`; otherwise `f"{path[-1]}: {kind}"` (the last path segment — the node's own identity — stands in for a per-attribute name on a whole-subtree `added`/`removed` record, or an event's tag name on an event record).

*Checkboxes:* each leaf item gets `Qt.ItemFlag.ItemIsUserCheckable` added to its flags and `setCheckState(0, Qt.CheckState.Unchecked)` — **default unchecked (Skip)**, per §6.1's "nothing changes until explicitly chosen." Check state is tracked purely in the widget's own per-item state; no external state object is introduced for this sub-project, since there is no Apply/write-back step yet to consume that state (sub-project 3's job). Intermediate group nodes (the path-prefix nodes) are plain, non-checkable `QTreeWidgetItem`s — only leaves (actual `Difference` records) are checkable.

*Ambiguous marker:* a leaf whose `Difference.ambiguous` is `True` gets its label prefixed with `"⚠ "` (e.g. `"⚠ caption: changed"`), so an ambiguous match (from the duplicate-`(tableName, caption)`-sibling or duplicate-event-base-name positional-pairing fallback in the differ) is never visually indistinguishable from a confident one. Group/prefix nodes are not marked even if all their descendants are ambiguous — the marker is a per-leaf, per-record property, not a rolled-up summary.

**Detail view (right pane)**

A `QStackedWidget` (or equivalent — three mutually-exclusive views selected by what kind of leaf is currently selected), shown when a leaf item is selected in the tree (selecting a group/prefix node clears the detail view to empty, since a group node has no single `Difference` to show):

1. **Attribute `"changed"`** (`attribute is not None`): a simple two-row read-only display, `"Old: {old_value}"` / `"New: {new_value}"`.
2. **Whole-subtree `"added"`/`"removed"`** (`attribute is None`, `node_kind` in `{"page", "detail", "column"}`, and the non-`None` one of `old_value`/`new_value` is a `PageNode`/`DetailNode`/`ColumnNode`): a read-only key-value table listing that node's `attrib` dict — there's no "change" to show, just the full content of what's present on only one side.
3. **Event `"changed"`** (`node_kind == "event"`, `attribute is None`, `kind == "changed"`): a line-level unified diff of `old_value`/`new_value` (both raw `EventNode.text` strings) via stdlib `difflib.unified_diff(old_value.splitlines(), new_value.splitlines(), lineterm="")`, joined with `"\n"` and displayed in a read-only `QPlainTextEdit` (`setReadOnly(True)`). No colored syntax highlighting in this sub-project — plain text with the standard `+`/`-`/` ` unified-diff prefixes is sufficient, consistent with the brainstorm's "stdlib only, no new dependency" decision. (An event `"added"`/`"removed"` record falls under case 2 above, not this case — `old_value`/`new_value` there is a whole `EventNode`, not raw text to diff.)

**Next Difference / Prev Difference**

Wired to the already-stubbed menu items in `main_window.py`'s `_build_diff_merge_menu`, replacing their `_add_stub_action` wiring with real handlers that delegate to `DiffMergePanel.select_next_difference()` / `select_previous_difference()`. Both walk the tree's leaves in display order (a simple flatten of the `QTreeWidgetItem` hierarchy, filtering to items carrying a `Difference` via `DIFFERENCE_ROLE` — i.e. skipping path-prefix group nodes, which are not themselves a difference), find the currently-selected leaf's position in that flattened order (or treat "nothing selected" as position -1), and select the next/previous one, wrapping is not required (stopping at the first/last leaf is sufficient — no requirement was stated for wraparound). Selecting a leaf this way updates the detail view exactly as a mouse click would, since both go through the tree widget's normal `currentItemChanged` signal. Pure in-memory navigation — no disk I/O, no re-running the differ.

**"Apply Changes to Target"** stays exactly as currently stubbed in `main_window.py` (`_add_stub_action`, showing "Not yet implemented: Apply Changes to Target"). Sub-project 3's job.

## 4. Testing strategy

- **`pytest-qt` tests for the change-list tree**, building it from synthetic `list[Difference]` objects (no real files, no `ProjectModel` needed) — covering:
  - Hierarchy construction from `Difference.path` lists sharing common prefixes (e.g. two differences both starting with `["development_equipment", "r_characteristic/Attachment"]` produce one shared intermediate node, not two).
  - Leaf label formatting for each `kind`/`node_kind`/`attribute` combination from the table in §3.6 (attribute change, whole-subtree added/removed, event added/removed/changed).
  - Checkbox default state (`Qt.CheckState.Unchecked`) on every leaf.
  - The `"⚠ "` ambiguous marker appearing only when `Difference.ambiguous is True`, and never on group/prefix nodes.
- **Unit tests for `resolve_path`** against synthetic `ProjectModel` trees (built directly in test code, same style as the differ engine's synthetic fixtures):
  - Found at depth 1 (Page only, matched by `file_name`).
  - Found at depth 2+ (Page → Detail → nested Detail, each matched by `(table_name, caption)` scoped to its immediate parent).
  - Not-found at each possible depth: a bad top-level `file_name`, and a bad `(table_name, caption)` pair at various nesting levels — asserting the returned `ResolutionError` carries the correct `segment_index` and a message naming the specific unresolvable segment, not just that the result is falsy.
- **One integration test per real sample file** (`sample/dev_Ferrara.pgtp`, `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`), running the full file-level compare flow's underlying logic (i.e. `load_project` twice on the same path + `diff_project`, then `DiffMergePanel.show_differences`, without driving the actual `QFileDialog`) against itself, asserting the resulting change-list tree has no leaf nodes — mirroring the differ engine's own self-diff-is-empty regression test, but exercised through the UI-facing code path this time.

## 5. Summary of decisions from brainstorming

- Diff/Merge's viewer UI was scoped as its own sub-project, sequenced after the differ engine and before serialization/Apply, because the engine needed to exist and be stable first (concrete `Difference` shape, concrete matching rules) before a viewer could be designed against it, and because Apply/write-back is a large enough concern (round-trip fidelity, `.bak` backups) to deserve its own brainstorm/spec/plan cycle rather than being bundled with "build a viewer."
- All three comparison entry points from the original design spec (§5.2's "Compare / Merge Two Files...", §5.3's "Compare This Page With..." and "Compare This Detail With...") converge on one shared viewer (`DiffMergePanel.show_differences`) rather than three separate UIs, since they differ only in how Source/Target are located, not in how the resulting differences are displayed.
- The Detail-level entry point requires resolving a target node by walking a path, not a single lookup — this is exactly the `resolve_path`-shaped capability the differ-engine spec's §2.2 explicitly deferred ("expected to reuse this same engine at Detail-subtree scope later, but wiring that up is not part of this sub-project"); this document is that later wiring, delivered as a new `resolve_path` function.
- `resolve_path` was placed in the `diff/` package (`pgtp_editor/diff/resolve.py`), not in `ui/`, because it reimplements the differ's own per-level matching rules (`fileName` for Pages, `(tableName, caption)` scoped to parent for Details) rather than any UI-specific concern, and keeping it Qt-free preserves the same testability the engine itself has.
- `resolve_path` returns a small `ResolutionError` (segment index + message) on failure rather than a bare `None`, specifically so the UI layer can report which exact path segment failed to resolve, matching the explicit requirement that an unresolvable comparison path must never produce a silent empty/wrong result.
- The change-list tree is built fresh from a flat `list[Difference]` each time, reusing intermediate nodes for shared `path` prefixes — deliberately similar in spirit to, but a different algorithm from, the Project Tree's own construction, since there is no pre-existing parent/child object graph to walk here, only path lists to de-duplicate.
- Apply/Skip selection is tracked purely as native Qt checkbox state on the tree widget itself, default unchecked, with explicitly no external state object and no persistence across sessions or invocations — introducing that machinery is deferred to sub-project 3, where it will actually be consumed by a write-back step.
- Event-handler text changes are rendered as a plain stdlib `difflib.unified_diff` in a read-only `QPlainTextEdit`, with no colored syntax highlighting — kept deliberately simple and dependency-free for this sub-project, consistent with the project's general preference (already established in the original design spec's §4.1 rationale for `lxml` and §9's licensing care around new dependencies) for not introducing new libraries without a demonstrated need.
- `MainWindow` gains a small new piece of state, `self._current_project` (and `self._current_project_path`), to support "Compare / Merge Two Files..." defaulting its Source to whatever project is currently loaded in the main tree — the shell previously had no need to remember this across the lifetime of a loaded project, since `open_project_file` only ever pushed data into the tree and discarded its own local reference.
