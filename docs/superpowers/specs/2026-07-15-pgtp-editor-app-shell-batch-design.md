# App-shell batch (Design)

Thirteen related improvements to the application shell: file lifecycle, undo,
menus/shortcuts, theming, a customizable toolbar, window-state persistence, a
reused-tables finder, and an About rewrite. Grouped into six sub-projects (A–F),
each built → reviewed → merged in sequence on one branch.

Shared context (current code): `main_window.py` tracks `self._current_project`
and `self._current_project_path` (set in `open_project_file`). Save/Save-As go
through `_write_project_text(path)`. No dirty-tracking, no `closeEvent`, no
QSettings yet. The Raw XML editor is `center_stage.xml_editor`
(QPlainTextEdit-based); the project tree is `project_tree` (a QTreeWidget).

---

## Sub-project A — Document state foundation → Close + Revert (#2, #3)

**Dirty tracking.** Add `self._dirty: bool` and a helper `_set_dirty(bool)` that
updates the window title (append " *" when dirty). The Raw XML editor's
`textChanged` marks dirty; loading/saving/reverting clears it. `open_project_file`
and every write clears dirty.

**`.bak` on save.** In `_write_project_text` (or `_save_project`), before
overwriting an existing file, copy the current on-disk file to `<path>.bak`
(overwriting any previous `.bak`). Save-As to a new path writes no `.bak` (nothing
to back up). Expose the pure decision as a helper if convenient, but the copy is a
small `shutil.copy2` guarded by "target exists".

**Close (#2).** File ▸ Close (and Ctrl+W, wired in B). `_close_project()`:
- If `_dirty`, show a non-blocking 3-button prompt (Save / Discard / Cancel). To
  stay testable, factor the decision into `_confirm_close() -> "save"|"discard"|"cancel"`
  that in production uses `QMessageBox.question`/`StandardButton`, and in tests is
  monkeypatched or the branchless `_close_project(confirm="discard")` seam is used.
  On Save → run `_save_project` (which may route to Save-As); on Cancel → abort.
- On proceed: clear the editor, clear the tree (`project_tree.clear()`), reset
  `_current_project`/`_current_project_path`/`_dirty`, update title.

**Revert (#3).** File ▸ Revert. `_revert_project()`: only enabled when a
`<current>.bak` exists. Reloads the project from the `.bak` content into the editor
and tree (reusing the load path against the `.bak` bytes), leaving
`_current_project_path` pointing at the real file and marking dirty (the buffer now
differs from disk). If no `.bak`, status-bar message.

**Testing:** dirty flag transitions; `.bak` written on overwrite but not on
first Save-As; Close with confirm=discard clears state; Close with confirm=cancel
preserves state; Revert with/without a `.bak`. No real modal in tests (use the
`confirm=`/monkeypatch seam).

---

## Sub-project B — Menu & shortcut cleanup (#1, #4, #6, #7, #8)

- **#1** Remove the "New Project" stub from the File menu.
- **#4** Shortcuts: Open `Ctrl+O`, Save `Ctrl+S`, Save As `Ctrl+Shift+S`, Close
  `Ctrl+W`. Set via `setShortcut` on the existing File actions (Close/Revert from A).
- **#6a** The "Raw XML Panel" View checkbox must reflect real visibility. The Raw
  XML tab is visible by default, so its action starts **checked**; keep it in sync
  with `center_stage`'s raw-xml tab visibility (set checked True at build; when
  `_reveal_raw_xml_tab` runs it already sets it True — ensure no path leaves it
  stale).
- **#6b** Move "Wrap Raw XML Lines" out of the View menu into the Raw XML editor's
  right-click context menu as a checkable item bound to
  `xml_editor.set_line_wrap_enabled` (reflecting current state).
- **#7** Implement Expand All / Collapse All in the View menu, calling
  `project_tree.expandAll()` / `collapseAll()`.
- **#8** Move the Diff/Merge menu's items into the **Tools** menu as a new section
  (a separator + "Compare / Merge Two Files…", "Next Difference", "Prev Difference",
  "Apply Changes to Target"), and remove the top-level "Diff / Merge" menu.

**Testing:** File menu no longer has New Project; the four shortcuts are set on the
right actions; Raw XML Panel action is checked at startup; Wrap action is absent
from View and present+checkable in the editor context menu; Expand/Collapse All
call through to the tree; Tools menu contains the diff actions and there is no
top-level Diff/Merge menu.

---

## Sub-project C — Undo/redo snapshot history + jump list (#5)

A document-level history of **XML-text snapshots**, independent of the editor's
character-level undo.

**`pgtp_editor/ui/history.py`** (new, Qt-free): `SnapshotHistory(max_len=10)` with
`push(text, label)` (drops the oldest beyond 10; truncates any redo tail when a new
snapshot is pushed after undos), `can_undo()`, `can_redo()`, `undo() -> text`,
`redo() -> text`, `jump_to(index) -> text`, `entries() -> list[(index,label)]`,
`current_index`. Coalescing: identical consecutive text is not pushed.

**Wiring in main_window:** capture a snapshot when the XML changes in a
*committed* way — on load (initial), and after each programmatic mutation
(code-editor write-back, add-attribute, caption apply) and after typing settles.
To keep it simple and match "steps that changed XML", debounce the editor's
`textChanged` with a short QTimer (e.g. 400 ms) and push a snapshot only when the
text actually differs from the current history head. Applying an undo/redo/jump
sets the editor text via a guarded setter that does NOT re-push (a `_restoring`
flag).

**Jump list UI:** Ctrl+Z = `undo`, Ctrl+Y = `redo` (single step). Edit ▸ Undo and
Edit ▸ Redo open a small non-modal list (a `QListWidget` in a popup or a reused
lightweight dialog) of `entries()` newest-first; selecting one calls `jump_to` and
applies. Expose `_history_entries()` and `_history_jump(index)` as the test seam;
the popup is not `.exec()`'d in tests.

**Testing:** SnapshotHistory unit tests (cap at 10, redo-tail truncation,
coalescing, jump). Main-window: a programmatic edit pushes one snapshot; undo/redo
restore text without re-pushing; jump_to sets the editor to that snapshot.

---

## Sub-project D — Window-state persistence + Light/Dark toggle (#11, #9)

- **#11** In `closeEvent`, save `saveGeometry()`/`saveState()` to `QSettings`
  ("MDS"/"PGTP Editor"); on construction, restore them if present. Guard so a fresh
  install with no settings uses the current default size.
- **#9** A View ▸ "Light Theme" checkable action toggles between the default
  palette and a light `QPalette` applied to `QApplication`. Persist the choice in
  QSettings and re-apply on startup. Factor palette construction into a pure-ish
  `light_palette() -> QPalette` and `apply_theme(app, light: bool)` so it's testable
  without asserting pixels.

**Testing:** QSettings round-trip is driven with a temp `QSettings` scope (or an
injected settings object) — save writes keys, restore reads them; `apply_theme`
toggles a detectable palette role (e.g. Window color differs light vs default).
Avoid depending on a real registry: use `QSettings` with a temp path/format or
inject a settings dir. No modal.

---

## Sub-project E — Customizable icon bar + Customize dialog (#10)

A `QToolBar` ("Main Toolbar") of actions, plus a **Customize Toolbar** dialog to
choose which of the app's actions appear and in what order; persisted in QSettings.

- Maintain a registry mapping stable action-ids → QAction (built from existing menu
  actions; give each a short id and, where available, an icon or text label).
- Default toolbar set: Open, Save, Undo, Redo, Find, Validate, Generate.
- **Customize dialog** (`pgtp_editor/ui/customize_toolbar_dialog.py`): two lists
  (Available / On toolbar) with Add/Remove/Up/Down buttons; OK writes the ordered
  id list. Non-modal-testable: expose `selected_ids()` / `set_ids(list)` and drive
  the buttons' slots directly; the dialog is shown, never `.exec()` in tests.
- `main_window` applies an id list by clearing and repopulating the toolbar, and
  persists it to QSettings; restores on startup (falling back to the default set).

**Testing:** the id→action registry resolves; applying an id list yields a toolbar
with those actions in order; the dialog's add/remove/reorder mutate its id list
correctly; persistence round-trips via the temp QSettings seam.

---

## Sub-project F — Find Reused Tables + About rewrite (#13, #12)

**#13 Find Reused Tables.** A pure analyzer over the loaded `ProjectModel`:
`collect_table_usages(project) -> list[TableUsage]` where each `TableUsage` has a
`name` and a list of `breadcrumbs` (strings like `Page 'Orders' ▸ Detail
'OrderItems'`). Sources of a "reference" (every reference, per decision):
- every `PageNode.table_name`,
- every `DetailNode.table_name` (recursively, including nested details),
- every column **lookup** table (from `ColumnNode.lookup` child-element attribs —
  the lookup's table attribute; inspect the attrib keys to find the table-name
  attribute, e.g. `lookupTable`/`table`).
Group by table name (case-sensitive as stored); each usage contributes one
breadcrumb. The result is sorted by table name.

UI: Tools ▸ "Find Reused Tables…" opens a non-modal window with a `QTreeWidget`:
top-level rows are table/view names (with a usage count); expanding a row lists its
breadcrumbs. If no project is loaded, status-bar message. Build it from
`collect_table_usages(self._current_project)`.

**Testing:** `collect_table_usages` is pure and unit-tested against a synthetic
ProjectModel (page tables, nested detail tables, and a column lookup) — asserts
grouping, breadcrumb text, and sort order. A light widget test asserts the tree is
populated (top-level count == distinct tables; children == breadcrumbs).

**#12 About rewrite** (`pgtp_editor/ui/about.py`): replace `ABOUT_TEXT`:
- Drop the SuperNano ("nano") credit (unused).
- Authors (no copyright line): **Botond Zalai-Ruzsics** and **MDS — Maintenance
  Data Services** (link `https://maint-data.com`).
- Disclaimer: PGTP Editor / MDS is **not affiliated with, endorsed by, or connected
  to SQL Maestro Group**; provided as-is with **no warranty**; the authors accept
  **no liability for damaged or corrupted `.pgtp` files** — keep backups. Credit
  link to `https://www.sqlmaestro.com`.
- Note it targets **PHP Generator `.pgtp` format version 22.8**.
- Keep the GPL-3.0 note and the genuine code credits (BoomslangXML, QCodeEditor).
The disclaimer is phrased professionally (not verbatim/profane).

**Testing:** `ABOUT_TEXT` contains the author names, the maint-data.com and
sqlmaestro.com links, the not-affiliated disclaimer, the v22.8 note, and does NOT
contain "SuperNano"/"nano".

---

## Cross-cutting constraints

- **Modal-hang guardrail:** no test may reach an unpatched `QMessageBox` /
  `QDialog.exec()` / `QFileDialog`. Every confirm/dialog gets a test seam
  (a `confirm=` parameter, a `selected_ids()` accessor, or monkeypatched
  `QMessageBox`), and dialogs are shown non-modally / driven by method.
- Pure logic (SnapshotHistory, collect_table_usages, palette/theme, toolbar id
  registry) is Qt-light and unit-tested; Qt layers stay thin.
- QSettings in tests uses a temp scope/dir (never the real user registry).
- Preserve existing behavior and byte-preserving save (`_write_project_text` with
  `newline=""`).

## Non-goals

- Drag-from-menu toolbar customization (a Customize dialog is used instead).
- A full multi-theme system (single Light/Dark toggle only).
- Multi-level `.bak` history (Revert restores the single most-recent `.bak`).
