# Caption Management — Advanced Editing & Filtering — Design

**Date:** 2026-07-14

Extends the merged Caption Management feature. Built as five sequential phases on a single branch (`worktree-pgtp-editor-caption-advanced`) so the whole thing can be run and tested together. Each phase is committed separately.

## Shared conventions (all phases)

- **Current state:** `pgtp_editor/ui/caption_scan.py` (`CaptionEntry{line, element_tag, anchor, attribute, value}`, `scan_captions(text)`, `apply_caption_edits(text, edits)` where `edits = list[(CaptionEntry, new_value)]`, boundary-safe attribute replace + XML escaping). `pgtp_editor/ui/caption_management_panel.py` (`_CaptionTableModel`, `_CaptionFilterProxyModel`, `CaptionManagementPanel`) — columns `("Line","Element","Anchor","Attribute","Value")`, in-place editable Value, inline per-column substring filter row, inconsistency tint `#3a2f1d`, `on_apply`/`on_close` callbacks, sort on EditRole (Line numeric). `main_window.py` wires Tools → "Manage Captions…" via `_enter_caption_mode`/`_apply_caption_edits`/`_close_caption_mode`; `center_stage.py` has `enter_caption_mode`/`leave_caption_mode` (currently hides Raw XML). Raw XML is the default-visible center tab.
- **Test harness:** headless offscreen `conftest.py` + `--timeout=60`. NO test may reach an un-patched modal (`QMessageBox.*`/`QDialog.exec()`/`QFileDialog.*`) — it hangs and is killed. Every new modal dialog must expose its logic in a way tests can drive without `.exec()` (construct the dialog, call methods, read/set fields — never call the blocking `exec()` in a test), and any static modal call in a handler must be patchable.
- **Qt-free core:** keep `caption_scan.py` Qt-free and unit-tested.
- **Not merged:** this branch is for testing; do not merge to main.

---

## Phase 1 — Mode model (read-only XML + status indicator)

**Goal:** In Caption Mode the Raw XML editor stays visible but read-only, a persistent status-bar label shows the mode, and edit attempts on the read-only editor give a non-modal hint.

- `XmlEditor` (`xml_editor.py`): add `read_only_edit_attempted = Signal()`. Override `keyPressEvent`: when `self.isReadOnly()` and the event is text-modifying (has printable `event.text()`, or key in {Backspace, Delete, Return, Enter}, or matches paste `Ctrl+V`), emit `read_only_edit_attempted` and return without calling super (the base already blocks the edit; emitting the signal is the only added behavior). Otherwise behave as today. Navigation keys and existing shortcuts still work.
- `CenterStage`: `enter_caption_mode` → keep `raw_xml_tab` visible, `self.xml_editor.setReadOnly(True)`, reveal + `setCurrentIndex(caption_management_tab_index)`. `leave_caption_mode` → `self.xml_editor.setReadOnly(False)`, hide caption tab, `setCurrentIndex(raw_xml_tab_index)`. (Raw XML tab is no longer hidden during caption mode.)
- `MainWindow`: create a permanent status-bar `QLabel` `self._mode_label` via `self.statusBar().addPermanentWidget(...)`, initial text `"Editing Mode"`. `_enter_caption_mode` sets it to `"Caption Mode (XML read-only)"`; `_close_caption_mode` resets to `"Editing Mode"`. Connect `self.center_stage.xml_editor.read_only_edit_attempted` to a slot that flashes `self.statusBar().showMessage("Raw XML is read-only in Caption Mode — close Caption Mode to edit.", 4000)`.
- **Tests:** `XmlEditor` read-only keypress emits the signal + leaves text unchanged; editable keypress does not emit and mutates normally. `CenterStage` enter → raw visible + `isReadOnly()` True + caption current; leave → editable + caption hidden + raw current. `MainWindow` label flips on enter/close; edit-attempt flashes the hint. Update the existing caption-mode tests that assert Raw XML hidden-on-enter (now visible + read-only).

---

## Phase 2 — Grid rework (breadcrumb, New Value + NULL, Changed marker/coloring, Go-to-line, Copy/Paste)

**Goal:** Non-destructive editing via a separate New Value column, structural breadcrumb context, a filterable changed-marker column with coloring, go-to-line navigation, and Excel-style copy/paste.

### 2.1 Breadcrumb (`caption_scan.py`)
- Add `breadcrumb: str` to `CaptionEntry`. In `scan_captions`, for each element compute the structural path from its ancestors: walk `element.iterancestors()`, collecting each `Page`/`Detail`/`OnTheFlyInsertPage` ancestor's `caption` (fallback `fileName` → `tableName` → tag), outermost first; append the element's own label (its `fieldName` for a `ColumnPresentation`, else its `caption`/tag). Join with `" → "`. Example: `Equipment → Attachments → wbs_id`.

### 2.2 New Value column + NULL (`caption_management_panel.py`, `caption_scan.py`)
- New grid columns: `("Changed","Line","Breadcrumb","Element","Anchor","Attribute","Value","New Value")`. **Value** becomes read-only (old value stays visible). **New Value** is the only editable column.
- Edit model: a row is *changed* iff its New Value cell is non-empty. Empty New Value → row untouched. The literal sentinel **`<NULL>`** in New Value → the caption is set to empty string (`caption=""`).
- `changed_edits()` returns `(entry, resolved_new_value)` for rows whose New Value is non-empty, where `resolved_new_value = "" if new_value == "<NULL>" else new_value`. `apply_caption_edits` is unchanged (it already writes whatever string it's given; `""` yields `caption=""`).
- Right-click menu action **"Insert NULL to empty field"** sets the selected New Value cell(s) to `<NULL>`.

### 2.3 Changed marker + coloring (`caption_management_panel.py`)
- **Changed** column (col 0): shows `"*"` when the row's New Value is non-empty, else `""`. Sortable/filterable so the user can isolate changed rows.
- Changed rows get a distinct background (e.g. `#26343a` — a cool tint, clearly different from the warm inconsistency tint `#3a2f1d`). If a row is both changed and inconsistent, **changed wins** (its own color). Apply BackgroundRole across the whole row for changed rows.

### 2.4 Go-to-line (`caption_management_panel.py` + `main_window.py`)
- Right-click menu **"Go to line in XML"** and shortcut **Ctrl+G** on the current row: invoke an injected `on_go_to_line(line: int)` callback with the row's source line. `MainWindow` wires it to switch to the Raw XML tab and `xml_editor.navigate_to_line(line)` (the editor is read-only in Caption Mode — that's the intended read-only inspection).

### 2.5 Copy / Paste (`caption_management_panel.py`)
- **Ctrl+C**: copy the selected cells' displayed text to the clipboard, tab-separated per row, newline between rows (Excel-compatible). For a single-column selection this is one value per line.
- **Ctrl+V**: paste into the New Value column of the selected rows. Split the clipboard text into lines; write line *i* into the New Value of selected row *i* (Excel-style vertical fill). If one line and many rows selected → fill that line into all selected rows ("replace all selected"). Only the New Value column is written (Value is read-only).

---

## Phase 3 — Excel-style column header filters

**Goal:** Click a column header → a dropdown listing that column's distinct values with checkboxes (all checked by default) to include/exclude, plus (Select all / Clear). Rows are shown only if their value in each filtered column is in that column's checked set. ANDs with the Phase-4 regexp filters.

- A `_HeaderFilter` popup (a `QWidget`/`QMenu`-based dropdown, NOT a modal `.exec()` dialog — use a non-blocking popup so tests can drive it) triggered from the header section (e.g. a filter icon or header click). Holds a `QListWidget` of checkable distinct values for that column (computed from the source model) + "Select all"/"Clear"/"OK".
- `_CaptionFilterProxyModel` gains a per-column allowed-value set: `set_value_filter(column, allowed: set[str] | None)` (None = no value filter). `filterAcceptsRow` ANDs the value-set filters with the regexp filters (Phase 4).
- Header shows an indicator (e.g. ▾ or a bold header) when a column has an active value filter.
- **Tests:** distinct values computed correctly; unchecking a value hides those rows; ANDing across columns; "Select all" clears the filter. Drive the popup's model/methods directly (no `.exec()`).

---

## Phase 4 — Shared Find/Filter/Replace modal (Notepad++-style)

**Goal:** One reusable dialog (Tools → "Caption Filter…" and Ctrl+R) providing regexp-or-string matching and, in Replace mode, scoped replacement — inspired by the Notepad++ Replace dialog the user referenced.

- A `CaptionFindReplaceDialog(QDialog)` with:
  - **Find what** field; **Replace with** field (shown only in Replace mode).
  - **Search Mode** radios: **Normal (plain string)**, **Extended** (`\n \t \0 \xNN`), **Regular expression**.
  - **Match case** checkbox.
  - **Scope** radios: **In selection (filtered rows)** vs **Global (all rows)** — default In selection.
  - Buttons: **Filter** (apply as a grid filter), **Replace All** (in scope), **Close**. (No per-field "Find Next" needed for a grid; Replace All is the mass operation.)
- **As a filter (Tools → Caption Filter…):** the Find-what pattern (honoring Search Mode + Match case) becomes a whole-row text filter on the grid via the proxy (`set_regex_filter(pattern, mode, case)`); replaces the removed inline filter row. Filtering ANDs with Phase-3 value filters.
- **As Replace (Ctrl+R):** pre-loads the grid's currently-active filter pattern into Find-what (editable). Replace All applies the find→replace transform to the **Value** of each row in scope, writing the result into that row's **New Value** (non-destructive — old value preserved). Scope "In selection" = currently-filtered/visible rows; "Global" = all rows.
- **Testability:** all logic lives in dialog methods and a Qt-free helper `apply_find_replace(value, find, replacement, mode, case) -> str | None` (returns the transformed string, or None if no match) in `caption_scan.py` — fully unit-tested (string/extended/regex/case, capture groups). Tests construct the dialog, set fields, call `filter()`/`replace_all()` directly; never call `.exec()`.
- Remove the inline per-column filter `QLineEdit` row from Phase 0's panel (superseded by header filters + this modal).

---

## Phase 5 — Surprise: Bulk-transform & Unify power tools

**Goal:** Two right-click power actions that make mass caption cleanup fast — the "great editing tool".

### 5.1 Bulk Transform (selected New Value cells)
Right-click → **Transform ▸** submenu operating on the selected rows' New Value (seeding New Value from the current Value when the New Value cell is empty, so a transform is a one-click "edit"):
- **Title Case** (`wbs id` → `Wbs Id`), **UPPERCASE**, **lowercase**, **Sentence case**, **Trim whitespace**, and **Humanize field name** (`physicallocation_id` → `Physical Location`: split on `_`, drop a trailing `id`, title-case) — the last is especially handy for filling empty captions from a column's `fieldName`.
- Pure, unit-tested transform functions in `caption_scan.py` (`transform_caption(text, kind)`); the panel maps the menu action to the selection.

### 5.2 Unify to this value (coherence one-click)
Right-click a row → **"Unify: set all inconsistent siblings to this value"** — for every other row sharing this row's `(anchor, attribute)` whose Value differs, set its New Value to this row's Value (or New Value if set). This directly resolves the inconsistency the tint already flags, in one click — the original §6.3 coherence goal, now a power action.

- **Tests:** each transform function (pure); bulk transform seeds-from-Value and writes New Value for the selection; Unify sets New Value on exactly the divergent siblings and leaves already-matching rows untouched.

---

## Cross-cutting testing & risks
- Every phase keeps the full suite green (`python -m pytest -q`), no timeouts, real-sample tests skip if fixtures absent.
- Colors are constants so tests assert them.
- The Phase-4 dialog and Phase-3 popup must be non-blocking / method-drivable so no test calls `.exec()`.
- Undo of grid edits is out of scope for now (New Value column already preserves the old value, so edits are reversible by clearing the cell).
