# Table References tab — design

## Goal

Turn the one-shot "Find Reused Tables" modal into a persistent, navigable
**Table references** tab in the left dock. Selecting a reference shows its
Properties; double-clicking jumps the Raw XML editor to the exact mention.
The result: database-table structural mentions become a second way to scroll
through the XML (alongside the Project tree).

Replaces the modal `ReusedTablesWindow`.

## Requirements (from the request)

1. Rename the menu entry "Find Reused Tables" → **"Find table reference"**.
2. Move it to the **View** menu as a checkable on/off toggle.
3. Show results in the left dock as a **new tab** (not a modal window).
4. **Double-click** a reference → jump to its line in the Raw XML editor
   (same behavior as the Project tree).
5. In addition to the existing `(lookup)` reference label, add
   **`(lookup with insert)`** when an `<OnTheFlyInsertPage>` element follows
   the `<Lookup>` (i.e. is a child of it).
6. Selecting a reference drives the **Properties** panel (as the Project tree
   does).

## Confirmed decisions

- **Jump target for a lookup reference:** the `<Lookup>` element's own line
  (the actual `tableName` mention), not the enclosing column presentation.
  Page/detail references jump to their own open-tag line.
- **Tools menu:** the old "Find Reused Tables..." action is **removed**. The
  feature lives only as the View toggle.
- **Properties target for a lookup reference:** the owning `ColumnNode`
  (`kind="column"`), since that is the node the lookup belongs to.

## Architecture

Three units, following patterns already in the codebase.

### 1. `pgtp_editor/analysis/reused_tables.py` — structured references

Currently `collect_table_usages` returns `TableUsage(name, breadcrumbs:
list[str])`. Strings alone cannot drive Properties or jump-to-line, so each
usage becomes a structured record.

New dataclass:

```
@dataclass(frozen=True)
class TableReference:
    breadcrumb: str          # human label, e.g. "Page 'Equipment' ▸ Column 'objecttype' (lookup with insert)"
    node: object             # PageNode | DetailNode | ColumnNode
    kind: str                # "page" | "detail" | "column"
    line: int | None         # line to jump to (see below)
    ref_type: str            # "table" | "lookup" | "lookup with insert"
```

`TableUsage.breadcrumbs: list[str]` → `TableUsage.references: list[TableReference]`.

Line resolution:
- page / detail reference → `node.sourceline`.
- lookup reference → the `<Lookup>` element's `sourceline`
  (`column.lookup.sourceline`, falling back to `column.sourceline`).

`(lookup with insert)` detection: the column's `<Lookup>` retains its lxml
element as `column.lookup.element`; a reference is "lookup with insert" when
`column.lookup.element.find("OnTheFlyInsertPage") is not None`, else "lookup".

The grouping/sorting behavior (group by table name, sort by name, keep
document order within a table) is unchanged.

### 2. `pgtp_editor/ui/table_references_panel.py` — the tab widget

`TableReferencesPanel(QTreeWidget)`, mirroring `DbCheckPanel`:

- Top-level items: `"<table>  (<count>)"`.
- Child items: the reference breadcrumb. Each child stores its
  `TableReference` (node, kind, line) via `setData(0, role, ...)`.
- Signals:
  - `selection_changed(object node, str kind)` — emitted on current-item
    change; emits `(None, None)` for a table (top-level) row.
  - `jump_requested(object line)` — emitted on double-click of a reference
    row (`line` may be `None`, handled downstream as a no-op).
- `set_usages(usages)` populates the tree.

The modal `pgtp_editor/ui/reused_tables_window.py` is deleted.

### 3. `pgtp_editor/ui/main_window.py` — wiring

- Construct `TableReferencesPanel`, add it to `left_tabs` as a hidden tab
  titled "Table references" (same hidden-tab pattern as Database Check /
  Contents).
- Connect:
  - `panel.selection_changed` → `self.properties_panel.show_node(node, kind)`
    (req 6).
  - `panel.jump_requested` → `self._tree_jump_to_line(line)` (req 4). This
    already reveals the Raw XML tab and calls `navigate_to_line`.
- **View menu:** add a checkable action **"Find table reference"**:
  - toggled on → reveal + focus the tab and repopulate it via
    `collect_table_usages(self._current_project)` (no-op message if no
    project is open).
  - toggled off → hide the tab.
  - Keep the action's checked state in sync if the tab is closed/switched
    (best-effort, matching existing panel toggles).
- Refresh the panel on reparse when the tab is visible (so it tracks edits),
  consistent with how the Database Check tab is refreshed.
- **Tools menu:** remove the "Find Reused Tables..." action and its handler
  `_open_reused_tables`; drop the `ReusedTablesWindow` import and the
  `_reused_tables_window` reference.

## Data flow

```
project → collect_table_usages() → [TableUsage(name, [TableReference...])]
       → TableReferencesPanel.set_usages()
select row  → selection_changed(node, kind) → properties_panel.show_node()
double-click→ jump_requested(line)          → _tree_jump_to_line(line)
                                              → Raw XML tab + navigate_to_line
```

## Error handling / edge cases

- No project open when toggled on: status-bar message, tab stays empty.
- A reference with `line is None`: `_tree_jump_to_line` already no-ops.
- Table (top-level) row selected: Properties clears (`show_node(None, None)`).
- Reparse invalidates node identities: repopulate from the fresh project (as
  the Project tree does).

## Testing

- `tests/analysis/test_reused_tables.py`: update for the new `references`
  structure; add cases for `(lookup)` vs `(lookup with insert)` and for the
  lookup line resolving to the `<Lookup>` sourceline.
- `tests/ui/test_table_references_panel.py` (new): `set_usages` builds the
  tree; child items carry node/kind/line; `selection_changed` and
  `jump_requested` fire with the right payloads.
- `tests/ui/` main-window wiring: View toggle shows + populates the tab;
  selection drives Properties; double-click drives the jump; Tools no longer
  has the entry. Patch any modal calls per project policy.
- Remove `tests/ui/test_reused_tables_window.py` (window deleted).
- Run the `feature-tester` agent at completion; record in `docs/TEST_LOG.md`.

## Out of scope

- Generalized attribute/expression query builder (this feature keeps the
  fixed "by table name" grouping; richer contextual queries are a later idea).
- Replace/edit from the references tab (navigation + Properties only).
