# Database Check — Implementation Plan

> Use TDD. Steps use checkbox syntax. Modal-hang guardrail applies (no unpatched
> QMessageBox/QDialog.exec()/QFileDialog in tests). Headless offscreen is forced by
> conftest; QSettings isolated by the autouse fixture. No live DB in tests.

**Goal:** Validate a `.pgtp` against a live PostgreSQL schema in both directions,
reconcile mismatches by renaming in the XML.

**Spec:** `docs/superpowers/specs/2026-07-16-pgtp-editor-database-check-design.md`.

**Two sub-projects** (each build → review → merge):
- **SP1 — Connectivity:** `db/config`, `db/introspect` (pg_catalog, injectable
  runner, lazy psycopg), Database menu + Connection Setup dialog + Test, and the
  `psycopg[binary]` dependency.
- **SP2 — Comparison & reconcile:** `db/compare` + `db/rename` (pure), the Database
  Check results tab, the two check menu items, rename→replace-all + re-run,
  double-click jump, show-only-mismatches.

---

## SP1 — Connectivity

### Task 1: `db/config.py`
**Files:** create `pgtp_editor/db/__init__.py`, `pgtp_editor/db/config.py`;
test `tests/db/test_config.py`.

- `ConnectionParams` frozen dataclass: `host, port, database, user, password`
  (all str; port str for simplicity of the line edit).
- `connection_from_tree(tree) -> ConnectionParams | None`: find the first
  `<ConnectionOptions>` element (`tree.getroot().iter("ConnectionOptions")` first
  match); return params with host/port/login→user/database from its attribs and
  `password=""`. None if the element is absent.
- `load_connection(settings) -> ConnectionParams | None`: read keys under group
  `"db"` (`host/port/database/user/password`); None if host is absent.
- `save_connection(settings, params)`: write those keys.
- `seed_params(tree, settings) -> ConnectionParams`: non-password fields from the
  tree's `<ConnectionOptions>` when present, else from saved settings, else "";
  password from saved settings else "".

Tests: parse a synthetic tree (build with lxml `etree.fromstring`) with a
`<ConnectionOptions host="h" port="5432" login="u" password="XXX" database="d"/>`
→ params host=h,port=5432,user=u,database=d,password=""; missing element → None;
save/load round-trip via an injected `QSettings(ini)`; `seed_params` precedence
(tree over settings for non-password; settings for password).

### Task 2: `db/introspect.py` — model + injectable runner
**Files:** create `pgtp_editor/db/introspect.py`; test `tests/db/test_introspect.py`.

- Dataclasses: `ColumnInfo(name, data_type, is_pk, is_fk, is_nullable, default)`;
  `TableInfo(name, kind, columns: list[ColumnInfo])`; `DatabaseSchema(tables: dict[str, TableInfo])`
  with `has_table(name)`, `table(name)`, `column(name, col)`.
- `SCHEMA_SQL`: module-level list of the pg_catalog queries (relations, columns,
  constraints) — kept as constants so tests can assert the runner is asked for them.
- `run_queries(params, sql_list) -> list[list[rows]]`: the ONLY psycopg user.
  `import psycopg` INSIDE the function (lazy). Open one connection
  (`psycopg.connect(host=params.host, port=params.port or None, dbname=params.database,
  user=params.user, password=params.password)`), run each SQL, return a list of
  row-lists. Close in a finally.
- `fetch_schema(params, runner=run_queries) -> DatabaseSchema`: call the runner with
  `SCHEMA_SQL`, assemble `TableInfo`/`ColumnInfo`. Relation kind mapping:
  `r`,`p`→"table", `v`→"view", `m`→"matview". Column data_type is the pre-formatted
  `format_type` string from the query. PK/FK membership from the constraint rows.
  Keys are `"{schema}.{table}"`.
- `test_connection(params, runner=run_queries) -> (bool, str)`: run `["SELECT 1"]`;
  return `(True, "Connected.")`; on any Exception return `(False, str(exc))`. Never
  raises.

Tests: a fake `runner(params, sql_list)` returns canned rows shaped like the
queries (relations: (schema, name, relkind); columns: (schema, table, colname,
format_type, notnull, default); constraints: (schema, table, colname, contype)).
Assert `fetch_schema` builds the map with correct kind, data_type, is_pk (contype
'p'), is_fk (contype 'f'), is_nullable (not notnull), default. `test_connection`:
runner returning normally → (True, ...); runner raising → (False, msg). psycopg is
NEVER imported by the tests (only `run_queries` would, and tests don't call it).

### Task 3: `pgtp_editor/ui/connection_setup_dialog.py`
**Files:** create it; test `tests/ui/test_connection_setup_dialog.py`.

- `ConnectionSetupDialog(QDialog)`: QLineEdits host/port/database/user + password
  (`setEchoMode(QLineEdit.EchoMode.Password)`), a **Test** QPushButton + a status
  QLabel, a caveat QLabel ("Password is stored in app settings in plain text."),
  and OK/Cancel (`QDialogButtonBox`). Constructor takes an optional
  `tester=test_connection` callable (injectable).
- Methods: `set_params(ConnectionParams)` fills the edits; `params() -> ConnectionParams`
  reads them; `test()` calls `self._tester(self.params())` and sets the status label
  to the returned message (green/red by ok). NEVER `.exec()`; Test button → `test`.
- Non-modal: shown via `show()`; OK triggers `accept()` (drive `params()` in tests).

Tests: `set_params`/`params` round-trip; password echo mode is Password;
`test()` with a stub tester returning (True,"ok")/(False,"bad") sets the status
text; no modal.

### Task 4: main_window — Database menu + Connection Setup wiring
**Files:** modify `pgtp_editor/ui/main_window.py`; test `tests/ui/test_database_menu.py`.

- Add `_build_database_menu()` (call it from `_build_menu_bar` after the Schema
  menu): a "Database" menu with "Connection Setup…" → `_open_connection_setup`.
  (The two Check items are added in SP2.)
- `_open_connection_setup`: build `ConnectionSetupDialog(tester=test_connection, parent=self)`,
  seed it via `seed_params(self._current_project.tree if self._current_project else None, self._settings)`
  (guard None tree → seed_params must accept None tree and skip the XML step), hold
  it on `self._connection_dialog` (no GC), connect its `accepted` to save via
  `save_connection(self._settings, dialog.params())`, and `show()`.
- `seed_params` must tolerate `tree=None` (no project loaded) — return settings/blank
  params. (Adjust Task 1 accordingly: `connection_from_tree(None)` returns None.)

Tests: the Database menu exists with "Connection Setup…"; `_open_connection_setup`
with a loaded project seeds the dialog from `<ConnectionOptions>` (password blank)
and holds it on `self._connection_dialog`; calling the dialog's accept path saves to
the injected settings; with no project it still opens (seeded from settings/blanks),
no crash. No modal/exec.

### Task 5: dependency + packaging
**Files:** modify `pyproject.toml`.
- Add `"psycopg[binary]>=3.1"` to `[project].dependencies`.
- `pip install -e .` (or `pip install "psycopg[binary]"`) in the worktree so a real
  launch can connect. If the binary wheel fails to install in this environment,
  report it — tests still pass (they never import psycopg), and the feature degrades
  to a clear connection-error message at runtime.

### Task 6: full-suite verification
- `python -m pytest -q` green (baseline 1181 + new tests). No timeouts. Commit.

---

## SP2 — Comparison & reconcile (outline; detailed at SP2 time)
`db/compare.py` (xml_table_columns, xml_table_invocations, check_xml_against_db,
check_db_against_xml with TableCheck/ColumnCheck carrying kind/invocations/ColumnInfo),
`db/rename.py` (rename_field, rename_table targeted attribute replace),
`ui/db_check_panel.py` (tree with (T)/(V)/(M) prefixes, ×N counts, PK underline,
(fk), format_type, NOT NULL/DEFAULT, show-only-mismatches + count), the two Database
menu Check items, rename→replace-all+re-run, and double-click jump to XML.

## Self-review
- Spec coverage: SP1 covers config (incl. XML seeding + settings), introspection
  engine (pg_catalog, injectable, lazy psycopg), connection dialog + Test, Database
  menu, dependency. SP2 covers comparison, rendering, reconcile, extras.
- Names consistent: ConnectionParams, connection_from_tree, seed_params,
  DatabaseSchema/TableInfo/ColumnInfo, run_queries/fetch_schema/test_connection,
  ConnectionSetupDialog.set_params/params/test.
- No live DB or modal in any test (injectable runner + tester stubs).
