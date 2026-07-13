# PGTP Editor — Editor↔Tree Sync (Reveal in Tree) + Reparse Design Specification

**Date:** 2026-07-13
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md) (original shell design), the completed Real Model sub-project (`pgtp_editor/model/nodes.py`, `pgtp_editor/model/parser.py`, `pgtp_editor/model/encoding.py`), the **merged** XML Editor Foundation sub-project (sub-project A — `pgtp_editor/ui/xml_editor.py`'s `XmlEditor(QPlainTextEdit)`, its `highlight_error_line`/`navigate_to_line` line-navigation methods and the Tier-1 parse-failure fallback pattern), and the completed Properties Panel sub-project (`pgtp_editor/ui/properties_panel.py`, driven by the tree's `on_selection_changed` callback).

## 1. Context and scope

This is a new sub-project in the **XML Editor feature area**. Call it **Editor↔Tree Sync (Reveal in Tree) + Reparse**.

The XML Editor feature area was sketched across several sub-projects in the original design and in the XML Editor Foundation design (`2026-07-12-pgtp-editor-xml-editor-foundation-design.md`, §2.2):

- **Sub-project A — XML Editor Foundation** (done, merged): the `XmlEditor(QPlainTextEdit)` widget itself — syntax highlighting, gutter/line numbers, folding, auto-indent/auto-close, and the line-navigation entry points `navigate_to_line(line)`/`highlight_error_line(line)`/`line_text(line)`/`select_range_on_line(...)`. This is the foundation this sub-project builds on; confirmed present in this repo's `pgtp_editor/ui/xml_editor.py`.
- **Sub-projects B/C/E** (bookmarks, search & replace, schema integration): unrelated to this document.
- **Sub-project D — XML structural selection** (`Ctrl+Shift+B`/`Ctrl+Shift+A` block/parent-block selection, matching-tag highlighting): a **sibling sub-project in the same feature area, currently implementing on a separate branch, not yet merged.** It also extends `pgtp_editor/ui/xml_editor.py`. This sub-project must therefore keep its own edits to `xml_editor.py` small and localized to minimize eventual merge friction (see §3.3 and the explicit merge-risk callout in §5).

**What this sub-project delivers.** Two-way "reveal in tree" plus an explicit resync:

1. Click anywhere in the raw XML editor and the Project Tree selects the nearest enclosing node (Page/Detail/Column/Event) for that line — which, through the *already-wired* tree→Properties path, also repopulates the Properties panel. No new Properties code is needed.
2. A **Reparse** action that takes the editor's current text, parses it back into a `ProjectModel`, and — on success — rebuilds the tree and updates the live model so click-sync line numbers realign with the edited text. On failure it surfaces the error (Tier-1 pattern) while **leaving the last-good model/tree intact.**

This finally delivers the "edit raw XML, feed the corrected tree back into the live model" capability the XML Editor Foundation spec explicitly **deferred** (`2026-07-12-pgtp-editor-xml-editor-foundation-design.md` §2.2: *"reparsing an in-progress manual edit and feeding a corrected tree back into the app is a distinct, larger concern left for a future sub-project once this foundation exists"*). This is that future sub-project.

## 2. Scope

### 2.1 In scope — three pieces

1. **`node_at_line(project, line) -> PageNode | DetailNode | ColumnNode | EventNode | None`** — a new pure, Qt-free helper that resolves a 1-based source line number to the deepest model node whose source-line range contains it (§3.1). New module `pgtp_editor/model/line_index.py`.
2. **Editor-click → tree selection wiring** — on a click (mouse release, **not** live cursor movement) in `XmlEditor`, notify with the clicked 1-based line; `MainWindow` maps it via `node_at_line`, finds the matching `QTreeWidgetItem`, and calls `setCurrentItem`, which triggers the existing tree→Properties flow (§3.2, §3.3).
3. **Reparse action** — a new menu item that reparses the editor text via a new `load_project_from_text`-style entry point (reusing `_build_project_model` + `PgtpParseError`), rebuilding the tree and updating `_current_project` on success, or showing the Tier-1 error and preserving prior state on failure (§3.4, §3.5).

### 2.2 Explicitly out of scope

- **Live cursor-tracking sync.** Only a click triggers editor→tree sync. The user explicitly chose click-only; a `cursorPositionChanged`-driven live sync (updating the tree on every arrow-key move) is deliberately **not** built.
- **Any change to the Properties panel itself** (`pgtp_editor/ui/properties_panel.py`). Editor→tree→Properties is automatic: once click-sync sets the current tree item, the tree's existing `on_selection_changed` callback (→ `MainWindow._on_tree_selection_changed` → `PropertiesPanel.show_node`) already updates Properties. This sub-project does not touch Properties at all. Confirmed directly by reading `properties_panel.py` and `project_tree.py`.
- **Tree→editor scroll-on-selection.** Selecting a tree item is *not* being made to scroll the editor. That reverse direction is intentionally absent — and its absence is load-bearing for why click-sync cannot ping-pong (§3.3). (Note: Properties→editor navigation on property-row click already exists separately, via `PropertiesPanel._on_row_clicked` → `XmlEditor.navigate_to_line`; it is untouched here.)
- **Auto-reparse on every edit / live model updating.** Reparse is explicit/manual only — a menu action the user invokes. The model is not re-derived on every keystroke.
- **XML structural selection** (`Ctrl+Shift+B`/`Ctrl+Shift+A`, matching-tag highlighting) — that is the separate, not-yet-merged sub-project D.
- **Deep/normalizing round-trip guarantees.** Reparse parses whatever text is in the editor; it does not reconcile that text byte-for-byte with the on-disk file, nor re-run schema learning (that is bound to a file path in `_enrich_schema_from_file`, and there is no file path for editor text). See §3.5.

## 3. Architecture

### 3.1 `node_at_line` — the source-line-range index

**Location decision: new module `pgtp_editor/model/line_index.py`.** This helper operates purely over the `ProjectModel`/`PageNode`/`DetailNode`/`ColumnNode`/`EventNode` dataclasses and touches no lxml and no Qt, so it belongs in the `model/` package alongside `nodes.py`/`parser.py`. It is given its own small module rather than being added to `nodes.py` (which is deliberately a passive data-holder — its own docstring: *"plain data holders… Nothing here touches lxml directly"*) or to `parser.py` (which is scoped to lxml walking). A dedicated `line_index.py` keeps the line-range algorithm — its own concern with its own unit tests — cleanly separated, mirroring how the row-building logic lives apart from the panel widget in the Properties sub-project.

**What it resolves.** Given a 1-based `line`, return the **deepest** node whose source-line range contains `line`, i.e. the "nearest enclosing node":

- A click inside a Column's `<Format>`/`<Lookup>` sub-element resolves to that **Column** (the Column's range extends to just before the next node).
- A click on whitespace *inside* a Detail (but not inside any of its Columns/Events/nested Details) resolves to that **Detail**.
- A click above the first Page, or in the file header / `DataSources` area the model does not cover, resolves to **`None`** → the caller leaves the tree unchanged.

**The nodes and their anchor lines.** Every node the model builds carries a `sourceline` (confirmed in `nodes.py`: `PageNode`, `DetailNode`, `ColumnNode`, `EventNode` all have `sourceline: int | None`). `DetailNode` additionally has `inner_sourceline` (the nested `<Page>` element's line). **A Detail's range starts at its outer `sourceline`** (the `<Detail>` open tag), not at `inner_sourceline` — the outer `<Detail>` line and the inner `<Page>` line both belong to that Detail, and the Detail's children (its own Columns/Events/nested Details) live under the inner `<Page>`, so they carve out their own sub-ranges anyway. `inner_sourceline` is therefore **not** used as a range boundary by this algorithm; only `sourceline` values participate.

**The algorithm — document-order flat walk with depth.** Build the index once per model (cheaply, at click time, or memoized — see below):

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
    correctness depends only on start lines being monotonic in document
    order within each depth, which they are because the parser reads them
    straight off lxml's document-order .sourceline."""
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

**Why "next node at same-or-shallower depth" is the correct end boundary.** Walking in document order, a node's content ends exactly where the next sibling *or* an ancestor's next sibling begins — i.e. the next node that is not one of its own descendants. Any node appearing *after* it but *deeper* (`depth > entry.depth`) is a descendant and lives *inside* its range; those descendants get their own, narrower ranges, so the deepest-containing rule naturally returns the descendant for a click inside it and the ancestor for a click in the ancestor's own whitespace. A Column/Event has no model children, so its range simply runs from its `sourceline` to just before the next same-or-shallower node — which is why a click inside a Column's `<Format>`/`<Lookup>` sub-element (lines the model does not represent as nodes) still resolves to that Column.

**Duplicate-table Details are disambiguated for free.** Two Details with the same `tableName` occupy different document positions, hence different, non-overlapping line ranges — `node_at_line` returns whichever one's range contains the clicked line, with no special-casing.

**Above-the-first-page / uncovered regions → `None`.** Any `line` below the smallest `start` (or above the largest `end`, though in practice the last node runs to EOF) matches no entry, so `best` stays `None`. Lines in the file header, `DataSources`, or `Presentation` wrapper before the first `<Page>` are not represented by any node and correctly resolve to `None`.

**Cost / when to build.** The index is O(N) to flatten and O(N²) worst-case to assign end lines (a nested loop), where N is the total node count. Real projects have at most a few thousand nodes and a click is a rare, user-driven event, so building the index on each click is acceptable and is the simplest correct choice. If profiling ever shows it matters, `_assign_end_lines` can be made O(N) with a depth-indexed stack, and/or the index can be memoized on `_current_project` and invalidated on Reparse — but neither optimization is in scope now; the plan should implement the straightforward version.

### 3.2 Reverse node→item lookup

To act on the resolved node, `MainWindow` needs the `QTreeWidgetItem` that carries it. **Decision: build an `id(node) → QTreeWidgetItem` dict during `populate_from_project`, exposed as a method on `ProjectTreePanel`.** This is O(1) per lookup and built once per populate, versus a recursive tree walk comparing `MODEL_NODE_ROLE` on every click (O(items) per click, and re-implementing a traversal the panel is better placed to own). Keying on `id(node)` is safe because the exact same node object instances stored on the tree items (via `setData(0, MODEL_NODE_ROLE, node)`) are the ones `node_at_line` returns — both come from the single `ProjectModel` currently held in `_current_project`. The dict is rebuilt every `populate_from_project` (including after Reparse), so it never points at stale items.

```python
# pgtp_editor/ui/project_tree.py, ProjectTreePanel
    def populate_from_project(self, project):
        self.clear()
        self._item_by_node_id = {}          # NEW: reset the reverse index
        for page in project.pages:
            ...
            page_item.setData(0, MODEL_NODE_ROLE, page)
            self._item_by_node_id[id(page)] = page_item      # NEW
            self.addTopLevelItem(page_item)
            self._populate_details_and_events(page_item, page)

    def _populate_details_and_events(self, parent_item, node):
        for detail in node.details:
            ...
            detail_item.setData(0, MODEL_NODE_ROLE, detail)
            self._item_by_node_id[id(detail)] = detail_item  # NEW
            ...
        for column in node.columns:
            ...
            column_item.setData(0, MODEL_NODE_ROLE, column)
            self._item_by_node_id[id(column)] = column_item  # NEW
            ...
        for event in node.events:
            ...
            event_item.setData(0, MODEL_NODE_ROLE, event)
            self._item_by_node_id[id(event)] = event_item    # NEW

    def select_node(self, node) -> bool:
        """Select the tree item backing `node`, if present. Returns True if a
        matching item was found and selected, False otherwise (e.g. node is
        None, or is from a stale/other model). Setting the current item fires
        the existing currentItemChanged -> on_selection_changed -> Properties
        flow; no extra Properties wiring is needed here."""
        if node is None:
            return False
        item = self._item_by_node_id.get(id(node))
        if item is None:
            return False
        self.setCurrentItem(item)
        return True
```

`Column`/`Event` items already have `MODEL_NODE_ROLE` set today (confirmed in `_populate_details_and_events` — the Properties sub-project added that coverage), so no change to role coverage is needed; only the parallel `_item_by_node_id` inserts and the `select_node` method are added.

### 3.3 Editor-click notification mechanism

**Decision: add a `line_clicked = Signal(int)` Qt Signal to `XmlEditor`, emitted from a small `mouseReleaseEvent` override.** Justification:

- **Signal vs. injected callback.** The codebase's constructor-injected-callback convention (`on_selection_changed`/`on_stub_action`/`on_compare_page` on `ProjectTreePanel`) is the panel's *own* established surface — but `XmlEditor` is a `QPlainTextEdit` subclass that already uses Qt signals natively for its wiring (its `__init__` connects `blockCountChanged`, `updateRequest`, `textChanged`, `cursorPositionChanged`). Adding one more Qt `Signal` is the *smaller, more local, more idiomatic* change for this specific widget than retrofitting a constructor-callback parameter onto an editor that today takes only `parent`. `MainWindow` connects it exactly as it already connects Qt signals from `CenterStage`'s children (e.g. `diff_merge_panel.select_next_difference`). This is a case-by-case call, and for `XmlEditor` the Signal fits cleanest.
- **`mouseReleaseEvent`, not `cursorPositionChanged`.** The user explicitly chose click-only sync, *not* live cursor tracking. `cursorPositionChanged` fires on every arrow-key move and would give live tracking; gating it on "was the last change a mouse click" is fiddly. A `mouseReleaseEvent` override fires exactly once per click, after Qt has moved the cursor to the clicked position, so the line number is simply read from the post-click cursor. This is the minimal, click-only mechanism.

```python
# pgtp_editor/ui/xml_editor.py
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal   # add Signal

class XmlEditor(QPlainTextEdit):
    line_clicked = Signal(int)   # 1-based line of a mouse click in the text

    ...

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)   # let Qt place the cursor first
        if event.button() == Qt.MouseButton.LeftButton:
            line = self.textCursor().blockNumber() + 1   # 0-based -> 1-based
            self.line_clicked.emit(line)
```

**Merge-risk callout (explicit).** `pgtp_editor/ui/xml_editor.py` is being concurrently extended by the not-yet-merged **XML structural selection sub-project D** (`Ctrl+Shift+B`/`Ctrl+Shift+A`, matching-tag highlighting), which also adds behavior to this file and may itself touch mouse/cursor handling. To minimize eventual merge friction, this sub-project's edit to `xml_editor.py` is kept **small and localized**: one class-level `Signal` declaration, one `Signal` import addition, and one short `mouseReleaseEvent` override that calls `super()` first and only *reads* the cursor (it does not alter selection, folding, or the auto-close/auto-indent machinery). Whichever of D and this sub-project merges second should expect a trivial conflict confined to the top-of-class signal declarations and the mouse-event area, resolvable by keeping both additions. The plan should sequence accordingly and flag this in the PR description.

**MainWindow wiring:**

```python
# pgtp_editor/ui/main_window.py, MainWindow.__init__ (after center_stage exists)
        self.center_stage.xml_editor.line_clicked.connect(self._on_editor_line_clicked)

    def _on_editor_line_clicked(self, line: int) -> None:
        if self._current_project is None:
            return
        node = node_at_line(self._current_project, line)
        if node is None:
            return                       # click above first page / uncovered region: no-op
        self.project_tree.select_node(node)   # fires tree -> Properties automatically
```

**No feedback loop — and why a guard is not needed.** The wiring is strictly one-directional: editor click → `node_at_line` → `project_tree.select_node` → `setCurrentItem` → `currentItemChanged` → `on_selection_changed` → `PropertiesPanel.show_node`. Selecting a tree item updates **only** Properties; it does **not** scroll or re-select the editor (tree→editor scroll is explicitly out of scope, §2.2). Therefore `setCurrentItem` cannot re-trigger an editor click, and there is no cycle to break. A re-entrancy guard would be dead code here, so **none is added** — the absence of a tree→editor edge is what makes the wiring safe, and that fact is documented rather than papered over with an unnecessary flag. (If a future sub-project ever adds tree→editor scroll-on-selection, it must re-examine this; that is called out here so the assumption is not silently inherited.)

### 3.4 `load_project_from_text` — reparsing in-memory editor text

`load_project(path)` reads bytes from disk, CESU-8-repairs them, `etree.parse`s them, and calls `_build_project_model(tree, source_description=str(path))`. Reparse must do the same starting from an **in-memory string** (the editor's `toPlainText()`), never re-reading from disk. Add a sibling entry point to `pgtp_editor/model/parser.py` that shares `_build_project_model` and the same `PgtpParseError`/line handling:

```python
# pgtp_editor/model/parser.py
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

This mirrors `load_project` exactly except for the source (in-memory bytes vs. file) and the (deliberate) absence of the CESU-8 repair step — the repair operates on raw on-disk bytes to fix lone-surrogate sequences; text already decoded into a Python `str` and living in the editor has no such byte-level defect, and `str.encode("utf-8")` produces valid UTF-8. `_build_project_model` still raises `PgtpParseError` (with `line=None`) for a well-formed-but-structurally-unexpected document, exactly as it does for `load_project`.

### 3.5 The Reparse action

**Menu placement decision: `Tools → "Reparse Raw XML into Tree"`.** Placement is adjustable (a `View` or an editor-context-menu placement would also be defensible), but `Tools` is the best fit: it is where project-wide operations that act on the loaded document live (`Validate Project`, `Find Reused Tables…`), and Reparse is exactly such a whole-document operation. It is added as a **real** action (not an `_add_stub_action` stub), placed after a separator following the existing Tools entries:

```python
# pgtp_editor/ui/main_window.py, _build_tools_menu
    def _build_tools_menu(self):
        menu = self.menuBar().addMenu("Tools")
        self._add_stub_action(menu, "Manage Captions...")
        menu.addSeparator()
        self._add_stub_action(menu, "Find Reused Tables...")
        menu.addSeparator()
        self._add_stub_action(menu, "Validate Project")
        menu.addSeparator()
        reparse_action = menu.addAction("Reparse Raw XML into Tree")   # NEW
        reparse_action.triggered.connect(self._reparse_raw_xml)        # NEW
```

**The handler.** Take the editor's current text, reparse it, and branch:

```python
# pgtp_editor/ui/main_window.py
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

**On success:** the tree is rebuilt from the edited text (`populate_from_project`, which also rebuilds `_item_by_node_id` per §3.2), `_current_project` is replaced so subsequent `node_at_line` calls index the *edited* text's line numbers, and Properties is reset to its empty state (the previously-selected node no longer exists in the new model). `_current_project_path` is intentionally left unchanged — the file on disk has not changed; Reparse only updates the in-memory model. (Saving edited text back to disk is a separate, not-yet-designed concern.)

**On failure (`PgtpParseError`):** mirror the existing Tier-1 pattern from `_handle_parse_failure` — a `QMessageBox.critical` plus `highlight_error_line(exc.line)` on the editor when a line is known — **but critically preserve the existing model and tree.** Unlike the File→Open failure path (which is failing to load anything and populates the raw fallback from a file), the reparse failure path must **not** blank the tree, must **not** drop `_current_project`, and must **not** re-read any file: the editor already shows the user's in-progress text (that is the very thing that failed to parse), and the last-good tree/model stay exactly as they were. The user keeps their last-good state, fixes the XML, and reparses again. This is the key behavioral difference from `_handle_parse_failure` and is called out explicitly so the plan does not copy that method's tree-blanking/file-reading behavior wholesale.

### 3.6 Edited-editor behavior (best-effort click-sync between reparses)

Click-sync always maps the clicked line against **the last-loaded-or-last-reparsed model** (`_current_project`). After the user edits the editor text but *before* they Reparse, the model's stored `sourceline` values reflect the pre-edit text, so a click may resolve to a *neighboring* node if edits have shifted line numbers. This is accepted **best-effort** behavior — click-sync degrades gracefully (it selects a nearby node, never crashes), and **Reparse is the explicit resync** that realigns line numbers with the current text. This is stated plainly so it is understood as designed, not a bug: there is no attempt to track edits incrementally or keep the model live against every keystroke (that is explicitly out of scope, §2.2).

## 4. Testing strategy

### 4.1 Qt-free unit tests for `node_at_line` (`pgtp_editor/model/line_index.py`)

Built against synthetic `ProjectModel`s assembled directly from the `nodes.py` dataclasses (no lxml, no Qt), with hand-assigned `sourceline` values:

- **Deepest-enclosing at depth 1/2/3:** a Page (line 5) containing a Detail (line 10) containing a nested Detail (line 15) with a Column (line 18); assert a click on line 5 → Page, line 12 → the outer Detail, line 16 → the nested Detail, line 18 → the Column.
- **Non-node line inside a Column's sub-element → the Column:** a Column at line 20 with the next node (a sibling Column or the next Detail) at line 30; assert clicks on lines 21–29 (representing the Column's `<Format>`/`<Lookup>` body, which the model has no nodes for) all resolve to the Column.
- **Whitespace inside a Detail → the Detail:** a Detail at line 10 whose first child Column starts at line 14; assert a click on lines 11–13 (whitespace/`<ColumnPresentations>` open before any Column node) resolves to the Detail, not to any Column.
- **Line above the first page → `None`:** first Page at line 5; assert clicks on lines 1–4 return `None`.
- **Two duplicate-table Details disambiguated by line:** two Details with the same `tableName` at lines 10 and 40; assert a click at line 12 returns the first Detail *instance object* and a click at line 42 returns the second — verified by object identity (`is`), not by table name.
- **`sourceline is None` robustness:** a node with `sourceline=None` is dropped from the index and never returned (defensive; the parser always populates it in practice).
- **`project is None` / empty project:** returns `None` without raising.

### 4.2 Unit test for `load_project_from_text` (`pgtp_editor/model/parser.py`)

- **Valid text → `ProjectModel`:** a small well-formed `.pgtp` string (a `Presentation/Pages/Page` with a Column and an Event) parses into a `ProjectModel` with the expected pages/columns/events and populated `sourceline`s. Can reuse an existing sample fixture's text, or a minimal inline document.
- **Malformed text → `PgtpParseError` with a line number:** a string with a syntax error (e.g. an unclosed tag) raises `PgtpParseError` whose `.line` is the offending 1-based line (from `XMLSyntaxError.lineno`).
- **Well-formed-but-structurally-empty:** text with no `Presentation/Pages` yields a `ProjectModel` with `pages == []` (matching `_build_project_model`'s existing behavior), not an error.
- **Parity with `load_project`:** parsing a sample file via `load_project(path)` and parsing that same file's text via `load_project_from_text(text)` produce equivalent models (same page/column/event counts and identities), confirming the shared `_build_project_model` path.

### 4.3 `pytest-qt` tests

- **Editor click selects the correct tree item and updates Properties:** load a synthetic/sample project into a `MainWindow`; simulate a `line_clicked` emission (or a real `mouseReleaseEvent` at a known line) for a line inside a known Detail; assert `project_tree.currentItem()` is that Detail's item **and** `properties_panel` now shows that Detail (via the existing tree→Properties wiring — proving the end-to-end reveal, not just the tree half). Simulate a click on a line above the first page and assert the current tree item is **unchanged** (no-op path).
- **`select_node` reverse-lookup correctness:** after `populate_from_project`, `select_node(some_column_node)` selects that Column's item and returns `True`; `select_node(a_node_from_a_different_model)` returns `False` and changes nothing.
- **Reparse success rebuilds the tree from edited text:** put a valid (edited) `.pgtp` document into the editor, trigger `_reparse_raw_xml`, and assert the tree now reflects the edited structure (e.g. an added/removed Column shows up/disappears), `_current_project` is the new model, and Properties has reset to its empty state.
- **Reparse failure preserves prior state:** load a good project (tree populated, `_current_project` set); put malformed XML in the editor; trigger `_reparse_raw_xml`; assert (a) a critical dialog was shown, (b) the error line was highlighted (`highlight_error_line` called with the right line — via a spy/monkeypatch), and **(c) the tree still shows the previously-loaded structure and `_current_project` is the same object as before** (the last-good state survived).
- **Click-sync realigns after Reparse:** click a line resolving to node X; edit the text to shift lines; Reparse; click the (now-shifted) line for the same logical node and assert it resolves correctly against the rebuilt model — demonstrating Reparse as the explicit resync (§3.6).

`QMessageBox.critical` is monkeypatched in the failure tests (matching how the existing open-failure tests avoid a real modal dialog), and mouse simulation uses `QTest.mouseClick` on the editor viewport at a computed position for the line, or directly emits `line_clicked` where positional precision is not the thing under test.

## 5. Summary of decisions from brainstorming

- **This is a new sub-project in the XML Editor feature area — "Editor↔Tree Sync (Reveal in Tree) + Reparse"** — built on the merged XML Editor Foundation (sub-project A) and sibling to the not-yet-merged structural-selection sub-project D.
- **`node_at_line` lives in a new module `pgtp_editor/model/line_index.py`** (Qt-free, lxml-free), not in `nodes.py` (passive data holder) or `parser.py` (lxml-scoped). It builds a document-order flat index with depth, computes each node's end line as one before the next same-or-shallower node, and returns the deepest node whose range contains the line. A Detail's range starts at its outer `sourceline` (not `inner_sourceline`). Duplicate-table Details are disambiguated by document position for free; lines above the first page resolve to `None`.
- **Editor→tree only; click-only.** A click (mouse release), not live cursor movement, triggers the sync — the user's explicit choice. Live `cursorPositionChanged` tracking is out of scope.
- **Editor-click notification is a new Qt `Signal` (`line_clicked = Signal(int)`) on `XmlEditor`, emitted from a small `mouseReleaseEvent` override** — chosen over a constructor-injected callback because `XmlEditor` already wires natively with Qt signals, making the Signal the smaller, more idiomatic, and more merge-friendly change for this specific widget. The edit to `xml_editor.py` is kept deliberately tiny to reduce merge friction with the concurrent sub-project D, which is called out as an explicit sequencing/merge risk.
- **Reverse node→item lookup is an `id(node) → QTreeWidgetItem` dict built during `populate_from_project`**, exposed via a new `ProjectTreePanel.select_node(node)` method — O(1), rebuilt on every populate (including after Reparse), chosen over a per-click recursive `MODEL_NODE_ROLE` walk.
- **No re-entrancy guard is added, by design:** the wiring is strictly one-directional (editor→tree→Properties) with no tree→editor edge, so no ping-pong is possible; the absence of that edge is documented as the reason, rather than adding a defensive flag that would be dead code.
- **Reparse uses a new `load_project_from_text(text, source_description)` in `parser.py`**, sharing `_build_project_model` and `PgtpParseError`/line handling with `load_project`, parsing from `io.BytesIO(text.encode("utf-8"))`. CESU-8 repair is deliberately omitted (it operates on raw on-disk bytes; editor text is already a valid Python `str`).
- **Reparse is `Tools → "Reparse Raw XML into Tree"`** (placement adjustable), a real (non-stub) action. On success it rebuilds the tree, adopts the new model (`_current_project`), and resets Properties to empty. On failure it mirrors the Tier-1 pattern (`QMessageBox.critical` + `highlight_error_line`) **but preserves the existing model/tree** and does not re-read any file — the key difference from `_handle_parse_failure`.
- **This delivers the capability the XML Editor Foundation spec (§2.2) explicitly deferred** — editing raw XML and feeding the corrected tree back into the live model.
- **Click-sync between reparses is best-effort:** it maps against the last-loaded-or-reparsed model, so after edits it may select a neighboring node; **Reparse is the explicit resync.** Properties is never touched by this sub-project — editor→tree→Properties is automatic through existing wiring.
