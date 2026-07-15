# Tree context-menu redesign + minor tweaks — Design

**Date:** 2026-07-15

A batch of refinements built as four sequential phases on one branch (`worktree-pgtp-editor-tree-context`), then run/tested together. Decisions locked with the user: Properties stays **read-only (explicit)**; "See … in caption mode" uses **exact tableName/fieldName filter context**.

## Shared conventions
- Headless offscreen + `--timeout=60`. NO test may reach an un-patched modal (`QMessageBox`/`QDialog.exec`/`QFileDialog`) or call a context `QMenu`'s `.exec()`; build menus in production only and drive the wired callbacks/methods directly in tests. Keep `caption_scan.py` Qt-free. Full suite green after each phase. Not merged until all phases + review pass.
- Current code: `ProjectTreePanel` (`project_tree.py`) is decoupled via injected callbacks (`on_selection_changed`, `on_compare_page`, `on_compare_detail`, plus stub actions); `build_page_menu`/`build_detail_menu`/`build_column_menu`. `XmlEditor` has `navigate_to_line(line)`, `select_enclosing_block()` (selects the element enclosing the cursor), `line_text`, structural-select. `MainWindow` owns the caption panel + `_enter_caption_mode`, and the Raw XML tab (`center_stage.raw_xml_tab_index`). Caption grid columns: Changed/Line/Breadcrumb/Element/Anchor/Attribute/Value/New Value; `_CaptionFilterProxyModel` has `set_value_filter`/`set_regex_filter`; `CaptionEntry{line, element_tag, anchor, attribute, value, breadcrumb}`.

---

## Phase A — Editor tweaks

### A.1 Ctrl+Shift+B collapses to selection START (`xml_editor.py`)
`select_enclosing_block` currently leaves the cursor/anchor such that focus is at the selection END. Change so that after selecting the block, the **visible cursor is at the block's start** (so the view shows the beginning of the selection, not the end) while the whole block stays selected. Implement by building the selection cursor with the anchor at the block END and position at the block START (`cursor.setPosition(end); cursor.setPosition(start, KeepAnchor)`), so `selectionStart==start` is where the caret sits, then `ensureCursorVisible()`. Keep `select_parent_block` behaviour consistent (also caret-at-start). Selected text is unchanged; only caret/scroll position changes. Tests: after the call, `editor.textCursor().position() == selectionStart` and the selected text is still the full block; the viewport is scrolled to the start.

### A.2 XML editor selection right-click → "Find" (`xml_editor.py`)
Add a **context menu** to the editor (override `contextMenuEvent`): start from the standard editable menu (`createStandardContextMenu()`), and when there is a non-empty selection, prepend a **"Find"** action that searches for the selected text. "Find" opens the existing Raw XML find bar pre-filled with the selection and runs Find Next — reuse the editor↔MainWindow path: emit a new `find_selected_text = Signal(str)` from the editor (with the selected text) that MainWindow connects to (reveal Raw XML tab + `find_replace_bar` prefill + find_next), OR call an injected callback. Keep it non-blocking; the context menu itself is fine to `exec` in production but tests must drive via the signal/callback, not `.exec()`. Tests: with a selection, the editor's context-menu construction includes a "Find" action wired to emit `find_selected_text` with the selected string; MainWindow handling reveals the Raw XML tab and prefills/searches.

---

## Phase B — Properties read-only (explicit)
The Properties panel is already navigate-only. Make the read-only contract explicit and unmistakable: ensure Value cells carry no `ItemIsEditable` flag (assert it), and add a subtle affordance (e.g. the panel's header/tooltip notes "read-only — click a row to edit in the XML editor", or set the table `editTriggers` to `NoEditTriggers`). No write-back. Tests: no Properties cell is editable (`flags() & ItemIsEditable == 0` for every cell of every node kind); the read-only hint is present.

---

## Phase C — Caption filter context + preset-filter entry + Clear-all-filters

### C.1 CaptionEntry gains table/field context (`caption_scan.py`)
Add `table_name: str = ""` and `field_name: str = ""` to `CaptionEntry`. In `scan_captions`, for each element compute:
- `field_name` = the element's own `fieldName` if it is a `ColumnPresentation` (else ""),
- `table_name` = the nearest ancestor-or-self `Page`/`Detail`/`OnTheFlyInsertPage` element's `tableName` (walk `iterancestors`, first one with a `tableName`; for a `ColumnPresentation` this is its owning page/detail's table). Both are exact strings for reliable filtering. Keep Qt-free. (These are extra context; existing columns/behaviour unchanged. Optionally expose them as hidden filterable data — see C.2.)

### C.2 Preset-filter entry (`caption_management_panel.py` + `main_window.py`)
Add panel methods that apply an exact filter after `load_entries`:
- `filter_to_table(table_name)` — show only rows whose `entry.table_name == table_name`.
- `filter_to_table_details(table_name)` — rows whose `table_name == table_name` AND whose element is within a `<Detail>` (i.e. the entry's element_tag is a detail-scoped element; concretely: the owning page/detail is a Detail, not a top-level Page). Purpose: see how the same DB table is captioned across its Detail embeds.
- `filter_to_field(table_name, field_name)` — rows whose `field_name == field_name` (optionally also `table_name`), and **select + scroll to** the matching row (highlighted via selection), so the specific column line stands out.
Implement these as either a dedicated predicate filter on the proxy (add `set_predicate_filter(fn)` ANDed with the others) or by extending value-filters keyed to the new table_name/field_name data (expose them via new hidden model columns or a `Qt.UserRole+N` data channel the proxy can read). Prefer a small `set_row_predicate(callable|None)` on the proxy that receives the source `CaptionEntry` — clean and exact.
`MainWindow` gains `enter_caption_mode_for_table(table_name)`, `enter_caption_mode_for_table_details(table_name)`, `enter_caption_mode_for_field(table_name, field_name)` that do the normal `_enter_caption_mode` (snapshot + scan + enter) THEN apply the corresponding panel filter. These are what the tree menu calls (Phase D).

### C.3 "Clear all filters" (caption right-click + method)
Add `CaptionManagementPanel.clear_all_filters()` — clears the regex/find filter, every header value filter, and any preset row-predicate; resets header indicators. Add it to the caption grid's right-click context menu as **"Clear all filters"**. Tests: after several filters + a preset predicate are active, `clear_all_filters()` shows all rows again and clears header indicators.

---

## Phase D — Tree context menus + double-click jump (`project_tree.py` + `main_window.py`)

### D.1 Double-click jumps the editor (single-click unchanged)
Keep single-click / current-item-change → Properties (`on_selection_changed`) as-is. Add: **double-click** a tree item → new injected `on_activate_node(node, kind)` callback; `MainWindow` wires it to switch to the Raw XML tab and `navigate_to_line(node.sourceline)` (for a detail, its outer `sourceline`). This replaces "jump on every selection" so the editor only jumps on explicit double-click.

### D.2 Page right-click — replace ALL current items with:
1. **"Jump to page xml"** → `on_jump_to_xml(node)` (editor → page's `sourceline`).
2. **"Select page xml"** → `on_select_xml_block(node)` — MainWindow navigates the cursor into the page's opening tag line then calls `xml_editor.select_enclosing_block()` (selects the whole `<Page>…</Page>` block for copy/paste/delete). Verify the cursor lands inside the opening tag so the enclosing element is the Page itself.
3. **"Add Event Handler"** → stub (`Not yet implemented`) for now.
4. **"See database table in caption mode"** → `on_see_table_in_caption(node)` → `enter_caption_mode_for_table(node.table_name)`.

### D.3 Detail right-click — ONLY:
1. **"Jump to detail xml"** → `on_jump_to_xml(node)` (detail outer `sourceline`).
2. **"Select detail xml"** → `on_select_xml_block(node)` (cursor into the `<Detail>` opening line + `select_enclosing_block`).
3. **"See database table in caption mode"** → `on_see_table_details_in_caption(node)` → `enter_caption_mode_for_table_details(node.table_name)`.

### D.4 Column right-click — replace ALL current items with:
1. **"Jump to column visibility in xml"** → `on_jump_to_column_visibility(node)` — jump the editor to the owning page/detail's `<Columns>` section. (Need the Columns block line: from the column's owning container, find its `<Columns>` element sourceline. The ColumnNode retains `element`; walk to its owning page's `<Columns>` child. If not resolvable, fall back to the column's own line.)
2. **"Jump to column presentation in xml"** → `on_jump_to_xml(node)` (the `<ColumnPresentation>` line = `column.sourceline`).
3. **"See column in caption mode"** → `on_see_column_in_caption(node)` → `enter_caption_mode_for_field(node's table_name, node.field_name)` (filters to that column's caption row and selects/highlights it).

### D.5 Wiring
All new callbacks are injected into `ProjectTreePanel.__init__` (default no-ops) and wired in `MainWindow` to the Phase-A/C capabilities. Remove the old Page/Detail/Column stub actions and the Compare-page/Compare-detail entries are **removed from Page/Detail menus per the "delete all actual ones" instruction** — BUT the Compare entry points also exist in the Diff/Merge menu, so removing them from the tree menu doesn't lose the feature. (Confirm the Diff/Merge menu still offers Compare; if the tree was the only entry point for "Compare This Detail With…", keep a way — otherwise it's fine to drop per instruction.) Multi-select menu may stay or be simplified; not in scope to expand.

## Testing (all phases)
- Editor: A.1 caret-at-start + full selection retained; A.2 Find action present on selection + emits/handles.
- Properties: no editable cells; hint present.
- Caption: scan sets table_name/field_name correctly (column → its fieldName + owning table; page/detail → their tableName); `filter_to_table`/`_details`/`_field` show the right rows and (field) select the row; `clear_all_filters` resets everything.
- Tree: double-click calls `on_activate_node`; single-click still Properties; each new menu action (page/detail/column) is present and its wired callback invoked with the right node; "Select … xml" selects the full element block; column caption/visibility/presentation jumps target the right lines. Drive callbacks directly; no `.exec()` in tests.
- Real-sample smoke (skips if absent): entering caption mode for a known table/field yields a non-empty, correctly-filtered grid.
