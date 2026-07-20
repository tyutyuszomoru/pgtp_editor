# Reparse→DB-Check refresh + Customize-Toolbar all-actions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) `Tools ▸ Reparse Raw XML into Tree` also refreshes an open Database Check panel by re-comparing the reparsed buffer against the *cached* DB schema (no re-query). (2) The Customize Toolbar dialog's Available pane always lists all commands, greying those already on the toolbar.

**Architecture:** Part 1 factors the DB-check compare+populate out of `_run_db_check`'s `on_result` into a shared `_populate_db_check` helper, adds a `_last_db_summary` cache field, and calls a guarded `_refresh_db_check_if_open(project)` at the end of `_reparse_raw_xml`'s success branch (reusing the project it already parsed — no re-parse). Part 2 changes `CustomizeToolbarDialog.set_ids` to list every command and disable present ones, with a defensive guard in `_add_selected` and a new `_available_enabled_ids` test seam. Both are small, localized, Qt-thin.

**Tech Stack:** PySide6, pytest + pytest-qt (offscreen). Spec: `docs/superpowers/specs/2026-07-20-pgtp-editor-reparse-dbcheck-and-toolbar-list-design.md`. Facts verified: `_reparse_raw_xml` (main_window.py:1007) already binds `project` on success; `_last_db_check_direction`/`_last_db_schema` init at main_window.py:173/176; `on_result` sets them at 1876-1877 and builds `summary`; `db_check_tab_index` exists (211-215); `test_db_check_wiring.py` provides `_RAW_XML`, `_schema()`, `_sync_run`, `_window_with_project`.

---

### Task 1: Part 1 — Reparse refreshes an open Database Check

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_db_check_wiring.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_db_check_wiring.py` (reuse its existing `_RAW_XML`, `_schema`, `_sync_run`, `_window_with_project`):

```python
def _run_initial_check(window, direction="xml_to_db"):
    """Do one real (patched-fetch) check so the cache + panel are populated
    and the tab is revealed."""
    window._run_db_check(direction)


def test_run_db_check_captures_summary(qtbot):
    window = _window_with_project(qtbot)
    _run_initial_check(window)
    assert window._last_db_check_direction == "xml_to_db"
    assert window._last_db_schema is not None
    assert window._last_db_summary == "u@h:5432/d"


def test_reparse_refreshes_open_db_check_with_cached_schema(qtbot):
    window = _window_with_project(qtbot)
    fetches = []
    base_fetch = window._fetch_db_schema
    window._fetch_db_schema = lambda params: (fetches.append(1), base_fetch(params))[1]
    _run_initial_check(window)
    assert fetches == [1]                      # one fetch for the initial check

    # Edit the buffer (add a column that IS in the schema was already; instead
    # remove the page's only column reference to change the mismatch set), then
    # spy on set_result so we see only the reparse-driven repopulate.
    calls = []
    real_set = window.db_check_panel.set_result
    window.db_check_panel.set_result = lambda *a: (calls.append(a), real_set(*a))[1]

    edited = _RAW_XML.replace('fieldName="id"', 'fieldName="nonexistent"')
    window.center_stage.xml_editor.setPlainText(edited)

    window._reparse_raw_xml()

    assert fetches == [1]                       # NO re-query — cached schema reused
    assert len(calls) == 1                       # panel repopulated once by reparse
    direction, checks, summary = calls[0]
    assert direction == "xml_to_db"
    assert summary == "u@h:5432/d"
    # checks reflect the EDITED buffer against the cached schema:
    from pgtp_editor.model.project_loader import load_project_from_text
    from pgtp_editor.db.compare import check_xml_against_db
    proj = load_project_from_text(edited, source_description="<editor>")
    assert checks == check_xml_against_db(proj, window._last_db_schema)


def test_reparse_no_refresh_when_db_tab_hidden(qtbot):
    window = _window_with_project(qtbot)
    _run_initial_check(window)
    window.left_tabs.setTabVisible(window.db_check_tab_index, False)
    calls = []
    window.db_check_panel.set_result = lambda *a: calls.append(a)
    window._reparse_raw_xml()
    assert calls == []


def test_reparse_no_refresh_without_prior_check(qtbot):
    window = _window_with_project(qtbot)
    # no check run: cache empty, tab hidden by default
    calls = []
    window.db_check_panel.set_result = lambda *a: calls.append(a)
    window._reparse_raw_xml()
    assert calls == []
```

Adjust the `load_project_from_text` import path in the test if the real module path differs (grep `def load_project_from_text` — it is imported in main_window.py; reuse that import path).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_db_check_wiring.py -k "reparse or summary" -q`
Expected: FAIL — `_last_db_summary` missing / reparse doesn't repopulate.

- [ ] **Step 3: Implement in `main_window.py`**

(a) Init the new cache field next to the others (~line 176, after `self._last_db_schema = None`):

```python
        self._last_db_summary = None
```

(b) Add the shared populate helper (near `_run_db_check`):

```python
    def _populate_db_check(self, direction, schema, project, summary):
        """Compare `project` against `schema` for `direction` and show the
        result. Shared by the live check (_run_db_check) and the cached-schema
        refresh (_refresh_db_check_if_open)."""
        if direction == "xml_to_db":
            checks = check_xml_against_db(project, schema)
        else:
            checks = check_db_against_xml(project, schema)
        self.db_check_panel.set_result(direction, checks, summary)
```

(c) Refactor `on_result` inside `_run_db_check` to store the summary and use the helper:

```python
        def on_result(schema):
            summary = f"{params.user}@{params.host}:{params.port}/{params.database}"
            self._last_db_check_direction = direction
            self._last_db_schema = schema
            self._last_db_summary = summary
            self._populate_db_check(direction, schema, project, summary)
            self._reveal_db_check_tab()
            self.statusBar().showMessage("Database check complete.", 3000)
            _log.info("db: check %s finished", direction)
```

(d) Add the guarded refresh and call it from the reparse success branch. In
`_reparse_raw_xml`, after `self.statusBar().showMessage("Reparsed raw XML into tree", 5000)`:

```python
        self._refresh_db_check_if_open(project)
```

and the method:

```python
    def _refresh_db_check_if_open(self, project) -> None:
        """After a reparse, re-run the last DB check's comparison against the
        CACHED schema (no re-query) so the open panel reflects the edited XML.
        No-op unless the Database Check tab is visible and a check already ran.
        `project` is the freshly parsed model from _reparse_raw_xml."""
        if (
            not self.left_tabs.isTabVisible(self.db_check_tab_index)
            or self._last_db_check_direction is None
            or self._last_db_schema is None
        ):
            return
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

(This deviates from the spec's self-parsing helper: since `_reparse_raw_xml`
only reaches this call on a *successful* parse, we reuse that `project` instead
of re-parsing — same behavior, no double parse, and the invalid-buffer case is
already handled by `_handle_reparse_failure` returning early.)

`check_xml_against_db` / `check_db_against_xml` are already imported in
main_window.py (used by the old `on_result`); confirm and keep.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_db_check_wiring.py -q`
Expected: PASS (existing DB-check tests + 4 new).

- [ ] **Step 5: Commit**

```bash
git add pgtp_editor/ui/main_window.py tests/ui/test_db_check_wiring.py
git commit -m "feat: Reparse refreshes open Database Check against cached schema"
```

---

### Task 2: Part 2 — Customize Toolbar lists all actions

**Files:**
- Modify: `pgtp_editor/ui/customize_toolbar_dialog.py`
- Test: `tests/ui/test_customize_toolbar_dialog.py`

- [ ] **Step 1: Update existing tests + add new ones**

The 4 existing assertions that treat Available as the "complement" must change to
the new contract (Available = all commands; present ones disabled). Rewrite them
and add coverage. New/updated `tests/ui/test_customize_toolbar_dialog.py` cases:

```python
from PySide6.QtCore import Qt


def _enabled(dialog):
    return dialog._available_enabled_ids()


def _all_available(dialog):
    return dialog._available_ids()


def test_available_lists_all_commands_present_ones_disabled(qtbot):
    # default toolbar = all commands -> Available lists all, all disabled
    dialog = CustomizeToolbarDialog(AVAILABLE_COMMANDS, ["open", "save", "undo",
                                    "redo", "find", "validate", "generate"])
    qtbot.addWidget(dialog)
    assert _all_available(dialog) == ["open", "save", "undo", "redo", "find",
                                      "validate", "generate"]
    assert _enabled(dialog) == []            # everything already on the toolbar


def test_partial_toolbar_disables_only_present(qtbot):
    dialog = CustomizeToolbarDialog(AVAILABLE_COMMANDS, ["open", "save"])
    qtbot.addWidget(dialog)
    assert _all_available(dialog) == ["open", "save", "undo", "redo", "find",
                                      "validate", "generate"]
    assert _enabled(dialog) == ["undo", "redo", "find", "validate", "generate"]


def test_result_ids_matches_selected(qtbot):
    dialog = CustomizeToolbarDialog(AVAILABLE_COMMANDS, ["open", "save"])
    qtbot.addWidget(dialog)
    assert dialog.result_ids() == ["open", "save"]


def test_add_enabled_command_moves_to_toolbar_and_disables_in_available(qtbot):
    dialog = CustomizeToolbarDialog(AVAILABLE_COMMANDS, ["open"])
    qtbot.addWidget(dialog)
    dialog._select_available("undo")
    dialog._add_selected()
    assert dialog.result_ids() == ["open", "undo"]
    assert "undo" not in _enabled(dialog)          # now greyed
    assert "undo" in _all_available(dialog)        # still listed


def test_remove_reenables_in_available(qtbot):
    dialog = CustomizeToolbarDialog(AVAILABLE_COMMANDS, ["open", "save"])
    qtbot.addWidget(dialog)
    dialog._select_toolbar("save")
    dialog._remove_selected()
    assert dialog.result_ids() == ["open"]
    assert "save" in _enabled(dialog)              # re-enabled


def test_add_on_present_id_is_noop(qtbot):
    dialog = CustomizeToolbarDialog(AVAILABLE_COMMANDS, ["open", "save"])
    qtbot.addWidget(dialog)
    dialog._select_available("open")   # already on toolbar (disabled)
    dialog._add_selected()
    assert dialog.result_ids() == ["open", "save"]   # unchanged, no duplicate
```

Delete/replace the old `test_constructed_splits_current_and_available`,
`test_set_ids_resets_both_lists`, `test_add_selected_moves_from_available_to_toolbar`,
and `test_remove_selected_moves_back_to_available_in_registry_order` assertions
that asserted the complement — the move/reorder tests (`test_move_*`,
`test_result_ids_matches_selected`) stay. Keep whatever still holds; only the
Available-content expectations change.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/ui/test_customize_toolbar_dialog.py -q`
Expected: FAIL — `_available_enabled_ids` missing; Available currently the complement, not all.

- [ ] **Step 3: Implement in `customize_toolbar_dialog.py`**

Rewrite the `available_list` population in `set_ids` to list all ids, disabling
present ones:

```python
    def set_ids(self, ids):
        """Reset both lists: `ids` populate the On-Toolbar list in that order;
        Available lists EVERY command in registry order, with commands already
        on the toolbar shown disabled so they can't be added twice."""
        current = [cid for cid in ids if cid in self._labels]
        self.toolbar_list.clear()
        for cid in current:
            self.toolbar_list.addItem(self._make_item(cid))
        current_set = set(current)
        self.available_list.clear()
        for cid in self._registry_order:
            item = self._make_item(cid)
            if cid in current_set:
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEnabled
                    & ~Qt.ItemFlag.ItemIsSelectable
                )
            self.available_list.addItem(item)
```

Guard `_add_selected` against a disabled/already-present id:

```python
    def _add_selected(self):
        item = self.available_list.currentItem()
        if item is None:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid in set(self.selected_ids()):
            return
        self.set_ids(self.selected_ids() + [cid])
        self._select_toolbar(cid)
```

Add the enabled-ids seam near `_available_ids`:

```python
    def _available_enabled_ids(self):
        """Available ids whose item is enabled (i.e. addable — not already on
        the toolbar). Test seam."""
        out = []
        for row in range(self.available_list.count()):
            item = self.available_list.item(row)
            if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out
```

`_remove_selected`, `_move_up`, `_move_down`, `result_ids`, `selected_ids`,
`_available_ids` unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ui/test_customize_toolbar_dialog.py -q`
Expected: PASS.

- [ ] **Step 5: Sanity-check the MainWindow caller still works**

Run: `python -m pytest tests/ui/ -k "toolbar or customize" -q`
Expected: PASS — `_open_customize_toolbar` passes `AVAILABLE_COMMANDS` +
`self._toolbar_ids`; `result_ids()` (toolbar order) is unchanged, so
apply/persist logic is unaffected.

- [ ] **Step 6: Commit**

```bash
git add pgtp_editor/ui/customize_toolbar_dialog.py tests/ui/test_customize_toolbar_dialog.py
git commit -m "fix: Customize Toolbar Available lists all actions (present ones disabled)"
```

---

### Task 3: Feature-tester gate + full suite

**Files:** none (verification only, plus `docs/TEST_LOG.md`).

- [ ] **Step 1: Full suite**

Run: `python -m pytest -q`
Expected: baseline + new tests, 0 failures.

- [ ] **Step 2: Feature-tester agent (testing policy)**

Per CLAUDE.md, dispatch the `feature-tester` agent: feature "Reparse refreshes
DB Check + Customize Toolbar all-actions list", spec
`docs/superpowers/specs/2026-07-20-pgtp-editor-reparse-dbcheck-and-toolbar-list-design.md`,
this plan, changed files (`pgtp_editor/ui/main_window.py`,
`pgtp_editor/ui/customize_toolbar_dialog.py`, the two test files). It reviews
coverage, adds any gap tests (candidates: `db_to_xml` direction refresh; reparse
after an edit that *resolves* a mismatch shows fewer problems; toolbar add-all
then Available all-disabled), iterates to green, runs the full suite, and appends
a verified entry to `docs/TEST_LOG.md`.

- [ ] **Step 3: Commit the test log**

```bash
git add docs/TEST_LOG.md tests/
git commit -m "test: feature-tester coverage for reparse DB-check refresh + toolbar list"
```

---

## Verification (whole plan)

`python -m pytest -q` green. Manual smoke (optional, headed): open a project, run
a DB check, edit the XML to remove a referenced column, `Tools ▸ Reparse Raw XML
into Tree` → the Database Check panel updates without a new connection; open
`View ▸ Customize Toolbar…` on a default toolbar → Available lists all seven
commands (greyed), Remove one → it un-greys. Then two-stage review, `--no-ff`
merge, merge `main` into `re-phpgen`.

## Self-review notes

- **Spec coverage:** Part 1 cached-schema re-compare + guards + shared helper +
  `_last_db_summary` (Task 1); Part 2 Available=all/present-disabled + add guard +
  seam + updated tests (Task 2); testing policy (Task 3).
- **Deviation (noted):** `_refresh_db_check_if_open` takes the already-parsed
  `project` from `_reparse_raw_xml` rather than re-parsing — equivalent behavior,
  avoids a second parse; invalid-buffer is handled upstream by the early return
  in `_reparse_raw_xml`.
- **Type consistency:** `_populate_db_check(direction, schema, project, summary)`
  used by both the live check and the refresh; `result_ids()` still the toolbar
  order; `_available_enabled_ids()` new seam alongside `_available_ids()`.
- **Executor judgment point:** confirm the exact import name/path for
  `load_project_from_text` used in the Task 1 test matches main_window's import.
