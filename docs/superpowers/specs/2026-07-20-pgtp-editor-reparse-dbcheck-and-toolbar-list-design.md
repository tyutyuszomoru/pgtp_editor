# Reparse refreshes DB Check + Customize-Toolbar shows all actions — Design

**Date:** 2026-07-20
**Components:** `pgtp_editor/ui/main_window.py` (reparse → DB-check refresh),
`pgtp_editor/ui/customize_toolbar_dialog.py` (Available-list behavior).

Two small, independent UX fixes delivered as one batch.

---

## Part 1 — Reparse also refreshes an open Database Check

### Goal
`Tools ▸ Reparse Raw XML into Tree` currently rebuilds the project tree from the
editor buffer but leaves the Database Check panel showing stale results. After
reparsing, if the Database Check panel is open and a check was already run this
session, the panel should re-evaluate the (edited) buffer so the user sees how
their changes affected database completeness — **without** re-querying the live
database.

### Behavior
- **Cached-schema re-compare.** The refresh reuses the schema captured by the
  last completed check (`self._last_db_schema`); it does **not** open a DB
  connection. This is instant, works offline, and isolates "how did my XML edits
  change completeness" from any DB drift. (The results therefore reflect the DB
  snapshot from the last full check — acceptable and expected for this action.)
- **Guarded.** The refresh runs only when **all** hold: the Database Check tab is
  visible (`self.left_tabs.isTabVisible(self.db_check_tab_index)`),
  `self._last_db_check_direction is not None`, and `self._last_db_schema is not
  None`. Otherwise Reparse behaves exactly as today (tree rebuild only).
- **Invalid buffer.** If the current buffer no longer parses as a project, the
  tree reparse already reports its own error; the DB-check refresh is skipped
  with a brief status message and the panel keeps its previous contents (never
  cleared to a misleading empty state).
- **Order.** Tree rebuild first, then the DB-check refresh, so a status message
  from the refresh is the last thing shown.

### Structure
- Extend the DB-check result cache: when `_run_db_check`'s `on_result` fires,
  also store `self._last_db_summary` (the `user@host:port/database` line it
  already builds). Initialize `self._last_db_summary = None` where the other
  `_last_db_*` fields are initialized.
- Factor the compare-and-populate step out of `on_result` into a helper:

  ```python
  def _populate_db_check(self, direction, schema, project, summary):
      checks = (
          check_xml_against_db(project, schema)
          if direction == "xml_to_db"
          else check_db_against_xml(project, schema)
      )
      self.db_check_panel.set_result(direction, checks, summary)
  ```

  `on_result` calls this (after setting `_last_db_check_direction`,
  `_last_db_schema`, `_last_db_summary`) then reveals the tab, unchanged
  otherwise.
- In the reparse handler (the `Tools ▸ Reparse Raw XML into Tree` slot — locate
  it by the "Reparse Raw XML into Tree" action wiring), after the existing tree
  rebuild add a `_refresh_db_check_if_open()` call:

  ```python
  def _refresh_db_check_if_open(self) -> None:
      if (
          not self.left_tabs.isTabVisible(self.db_check_tab_index)
          or self._last_db_check_direction is None
          or self._last_db_schema is None
      ):
          return
      text = self.center_stage.xml_editor.toPlainText()
      try:
          project = load_project_from_text(text, source_description="<editor>")
      except PgtpParseError:
          return  # tree reparse already surfaced the error
      self._populate_db_check(
          self._last_db_check_direction,
          self._last_db_schema,
          project,
          self._last_db_summary or "",
      )
      self.statusBar().showMessage(
          "Database check refreshed against the last database snapshot.", 4000
      )
  ```

  The cache (direction/schema/summary) is reused, never overwritten, by the
  refresh path.

### Testing (offscreen Qt, no DB, no modals)
- Reparse with the DB-check tab visible and injected `_last_db_check_direction` /
  `_last_db_schema` / `_last_db_summary` → `db_check_panel.set_result` is called
  with checks computed from the **current** buffer against the cached schema (use
  a synthetic `DatabaseSchema` and a buffer whose reparse changes the mismatch
  set; assert the panel's new checks differ from a pre-edit run).
- No-op guards: tab hidden → no `set_result`; `_last_db_check_direction is None`
  → no `set_result`; both verified by spying on the panel.
- Invalid buffer → refresh skipped, panel untouched, no exception.
- `_run_db_check` still populates via the shared helper (existing DB-check tests
  stay green; extend one to assert `_last_db_summary` is captured).

---

## Part 2 — Customize Toolbar: Available list shows all actions

### Goal
The Customize Toolbar dialog's **Available** pane is empty on first launch
because the default toolbar contains every command and Available was populated as
"registry minus what's already on the toolbar." Make Available always show the
full palette so the dialog is immediately usable.

### Behavior
- **Available = all registry commands**, in registry order, always. A command
  that is currently on the toolbar appears in Available but **disabled** (greyed,
  non-selectable) so it cannot be added a second time.
- **Add** appends the selected (enabled) Available command to the toolbar; that
  command then shows disabled in Available.
- **Remove** takes a command off the toolbar; it re-enables in Available.
- Up/Down and the OK result are unchanged: `result_ids()` remains the toolbar
  list's order.

### Structure (in `customize_toolbar_dialog.py`)
- `set_ids(ids)`: toolbar_list unchanged (current ids in order). available_list
  now adds **every** `self._registry_order` id; for each id already in the
  current set, disable the item:

  ```python
  item = self._make_item(cid)
  if cid in current_set:
      item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled
                    & ~Qt.ItemFlag.ItemIsSelectable)
  self.available_list.addItem(item)
  ```
- `_add_selected`: add a guard so a disabled/already-present id is a no-op:

  ```python
  item = self.available_list.currentItem()
  if item is None:
      return
  cid = item.data(Qt.ItemDataRole.UserRole)
  if cid in set(self.selected_ids()):
      return
  self.set_ids(self.selected_ids() + [cid])
  self._select_toolbar(cid)
  ```
- `_remove_selected`, `_move_up`, `_move_down`, `result_ids`, `selected_ids`
  unchanged — they operate on the toolbar list and rebuild via `set_ids`.
- `_available_ids()` now returns the full palette rather than the complement;
  it is only a test seam, so callers are unaffected.

### Testing (`tests/ui/test_customize_toolbar_dialog.py`)
- On construction with the default (all-commands) toolbar, Available lists **all**
  command ids (not empty), and every one is disabled; toolbar lists all.
- With a partial toolbar (e.g. `["open", "save"]`), Available still lists all
  ids; `open`/`save` disabled, the rest enabled.
- Add an enabled command → it moves onto the toolbar and becomes disabled in
  Available; `result_ids()` gains it in order.
- Remove a toolbar command → it re-enables in Available; `result_ids()` drops it.
- Add on a disabled/already-present id (drive `_add_selected` directly with that
  id selected) → no-op.
- Update the existing tests that asserted Available == complement to the new
  "all, present-ones-disabled" contract.

---

## Delivery

One feature branch in a worktree off `main`; TDD; feature-tester run at
completion with a `docs/TEST_LOG.md` entry; two-stage review; `--no-ff` merge,
then merge `main` into `re-phpgen`. Manual: no new user-facing concept for Part 1
(Reparse just does more); Part 2 is a bug fix (no manual change needed). Not
pushed.
