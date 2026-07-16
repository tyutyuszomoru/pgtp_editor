# Database Check (Design)

Validate a `.pgtp` project against a live PostgreSQL database, in both
directions, and let the user reconcile mismatches by renaming tables/columns in
the XML.

## Decisions (from brainstorming)

- **Transport:** `psycopg` (v3) with binary wheels — direct, cross-OS connection.
  No external `psql` binary; no "locate binary" menu. Added to `pyproject`
  dependencies as `psycopg[binary]`.
- **Connection fields seeded from the XML:** host, port, database, and `login`
  (→ user) default from the loaded project's `<ConnectionOptions>` element.
  Password is never taken from the XML (it's stored obfuscated there); it is
  entered by the user.
- **Password storage:** the connection (incl. password) is persisted to the
  injectable `self._settings` (plaintext — a one-line caveat is shown in the
  dialog). The password field pre-fills from saved settings if present, else blank.
- **Rename scope:** targeted attribute replace — `fieldName="old"`→`fieldName="new"`
  and `tableName="old"`→`tableName="new"` across the whole file (global for that
  attribute; the rename prompt states this).
- **Results:** one "Database Check" left-dock tab; each check run repopulates it,
  with a header line stating the direction and connection.
- **Introspection via `pg_catalog`** (not `information_schema`) so materialized
  views, relation kind, PK/FK, and pretty types are all available.
- **Display enrichment:** table rows show a kind prefix `(T)`/`(V)`/`(M)` and the
  XML invocation count `(×N)`; column rows show the datatype via `format_type`
  (e.g. `varchar(255)`), PK columns **underlined**, FK columns marked ` (fk)`,
  and NOT NULL / DEFAULT metadata. These are informational, not pass/fail criteria.
- **Extras:** double-click a result row jumps to it in the Raw XML editor; a
  "Show only mismatches" toggle + a mismatch count in the header.

## Background (existing code to reuse)

- `.pgtp` `<ConnectionOptions host="" port="" login="" password="" database="" ...>`
  (design-time connection — the DB the generator read the schema from). There is
  also `<ScriptConnectionOptions>` (runtime); we use `ConnectionOptions`.
- `pgtp_editor/model/nodes.py`: `ProjectModel.pages`, `PageNode`/`DetailNode`
  `.table_name` (attrib `tableName`), `.columns[].field_name` (attrib `fieldName`),
  nested `.details`; `ProjectModel.tree` (lxml tree).
- `pgtp_editor/analysis/reused_tables.py`: the page→detail(recursive)→column
  traversal to reuse for gathering table→columns.
- `pgtp_editor/generation/config.py` + `runner.py`: the injectable-runner +
  settings pattern to mirror for the DB.
- `main_window.left_tabs` (QTabWidget in the left dock): add a hidden-until-used
  "Database Check" tab, same pattern as the manual "Contents" tab.
- `main_window._write... ` / editor buffer write-backs: renames go through the Raw
  XML buffer so they are undoable and mark the document dirty.

## Architecture — new `pgtp_editor/db/` package (Qt-free logic)

### `db/config.py`
- `ConnectionParams` dataclass: `host, port, database, user, password`.
- `connection_from_tree(tree) -> ConnectionParams | None`: read the first
  `<ConnectionOptions>` element's `host`/`port`/`login`/`database` (password always
  `""`). Returns None if absent.
- `load_connection(settings) -> ConnectionParams | None` / `save_connection(settings, params)`:
  persist under a `db/` settings group (all fields incl. password).
- `seed_params(tree, settings) -> ConnectionParams`: non-password fields from the
  tree's `<ConnectionOptions>` (falling back to saved settings, then blanks);
  password from saved settings else `""`.

### `db/introspect.py` (psycopg lazily imported) — `pg_catalog`-based
Introspection uses `pg_catalog` (not `information_schema`) so it can report
materialized views, relation kind, PK/FK, and pretty types in one coherent model.

- `ColumnInfo` dataclass: `name, data_type (via format_type), is_pk, is_fk,
  is_nullable, default (str|None)`.
- `TableInfo` dataclass: `name ("schema.table"), kind ("table"|"view"|"matview"),
  columns: list[ColumnInfo]`.
- `DatabaseSchema`: `tables: dict[str, TableInfo]` keyed by schema-qualified name
  (matches XML `tableName` like `pr.equipment`). Helpers `has_table(name)`,
  `table(name) -> TableInfo | None`, `column(name, col) -> ColumnInfo | None`.
- `run_queries(params, sql_list) -> rows` — the ONLY function that imports psycopg
  and opens a connection (`psycopg.connect(host=, port=, dbname=, user=, password=)`).
  Injectable: `fetch_schema`/`test_connection` take an optional `runner=` callable
  (defaults to `run_queries`) so tests pass a fake returning canned catalog rows —
  no live DB, and psycopg need not be importable in tests.
- `fetch_schema(params, runner=run_queries) -> DatabaseSchema`: query
  `pg_class`/`pg_namespace`/`pg_attribute`/`pg_type` for relations with
  `relkind IN ('r','p','v','m')` (r/p→table, v→view, m→matview) in non-system
  schemas, their columns (`format_type(atttypid, atttypmod)`, `attnotnull`,
  `pg_get_expr(adbin, adrelid)` default), and `pg_constraint` (`contype='p'` → PK
  columns, `'f'` → FK columns). Build the `TableInfo` map.
- `test_connection(params, runner=run_queries) -> (ok: bool, message: str)`:
  runs `SELECT 1`; returns `(True, "Connected.")` or `(False, <error text>)`.
  Never raises.

### `db/compare.py` (pure)
- `xml_table_columns(project) -> dict[str, set[str]]`: table `tableName` →
  set of `fieldName`s of the columns under pages/details bound to that table
  (recursive over details; reuse the reused-tables traversal). Skips empty names.
- `xml_table_invocations(project) -> dict[str, int]`: table `tableName` → number of
  references in the XML (page/detail/lookup) — reuse the reused-tables usages count.
- `ColumnCheck(name, ok, info: ColumnInfo | None)` — `info` carries the DB metadata
  (data_type, is_pk, is_fk, is_nullable, default) when the column exists in the DB;
  `None` when it doesn't (e.g. an XML column with no DB match).
- `TableCheck(name, ok, kind: str | None, invocations: int, columns: list[ColumnCheck])`
  — `kind` is the DB relation kind ("table"/"view"/"matview") when known;
  `invocations` is the XML reference count.
- `check_xml_against_db(project, schema) -> list[TableCheck]` (#5): for each
  XML-referenced table — `ok = schema.has_table(table)`, `kind` from the DB (if
  present), `invocations` from the XML; for each XML column —
  `ok = schema.column(table, col) is not None`, attaching that `ColumnInfo` when
  found (so found columns show type/pk/fk/nullability). If the table is missing,
  its columns are all `ok=False`, `info=None`. Sorted by table; columns sorted.
- `check_db_against_xml(project, schema) -> list[TableCheck]` (#6): for each DB
  table — `ok = table in xml tables`, `kind` from the DB, `invocations` from the XML;
  each DB column becomes a `ColumnCheck` with its `ColumnInfo` and
  `ok = column present in the XML's columns for that table`. Sorted.

### `db/rename.py` (pure)
- `rename_field(text, old, new) -> (new_text, count)`: replace the literal token
  `fieldName="{old}"` with `fieldName="{new}"`; return the count.
- `rename_table(text, old, new) -> (new_text, count)`: same for `tableName="{old}"`.
- Attribute values are XML-escaped consistently; `old`/`new` are matched/inserted
  as-is (names are simple identifiers, optionally schema-qualified for tables).

## UI layer

### Database menu (`main_window._build_database_menu`)
- **Connection Setup…** → `_open_connection_setup`.
- **Check: XML → Database** → `_run_db_check("xml_to_db")`.
- **Check: Database → XML** → `_run_db_check("db_to_xml")`.
Placed after the Schema menu (before Tools) or adjacent — final placement per the
existing menu order; the menu title is "Database".

### `pgtp_editor/ui/connection_setup_dialog.py`
- `ConnectionSetupDialog(QDialog)`: line edits host/port/database/user, a
  password `QLineEdit` (EchoMode.Password), a **Test** button + inline status
  label, OK/Cancel, and a small caveat label ("Password is stored in app settings
  in plain text."). Non-modal-testable: `set_params(ConnectionParams)`,
  `params() -> ConnectionParams`, `test()` (calls an injected
  `test_connection`-style callable and sets the status label — never `.exec()` in
  tests). OK emits/accepts with the entered params.
- `main_window._open_connection_setup`: build the dialog seeded via
  `seed_params(tree, settings)`, show non-modally; on OK, `save_connection`.

### `pgtp_editor/ui/db_check_panel.py`
- `DbCheckPanel(QWidget)`: a header row (direction + `user@host:port/db` + a mismatch
  count, e.g. "3 mismatches") and a **"Show only mismatches"** checkbox, over a
  `QTreeWidget` (header hidden). `set_result(direction, table_checks, connection_summary)`
  builds the rows.
- **Table row:** `(T|V|M) schema.table (×N)` where the prefix comes from `kind`
  (table→T, view→V, matview→M; unknown→none) and `N` is `invocations` (the XML
  reference count). A green `✓` / red `✗` marker (text glyph + colored foreground so
  it reads in both themes).
- **Column row:** the column name, **underlined when `is_pk`**; then ` (fk)` when
  `is_fk`; then the datatype (`format_type`, e.g. `varchar(255)`); then a **NOT NULL**
  marker when not nullable and `DEFAULT <expr>` when a default exists; then the ✓/✗.
  (Datatype/pk/fk/nullability/default come from `ColumnInfo`; a column with no DB
  match shows just the name + ✗.)
- **Show only mismatches:** re-filters the tree to rows with `ok=False` (a table row
  is kept if it or any of its columns is a mismatch). The header mismatch count
  reflects the current result regardless of the filter.
- Emits `rename_requested(kind, old_name)` from a not-found node's context action
  (`kind` ∈ "table"/"column"); only offered for XML→DB not-found nodes.
- Emits `jump_requested(kind, name)` on **double-click** of a row → the main window
  navigates the Raw XML editor to that `tableName="…"`/`fieldName="…"` (reusing the
  existing editor navigation).
- Added to `main_window.left_tabs` as a hidden "Database Check" tab, revealed and
  focused when a check runs (mirrors the manual Contents tab).

### Rename flow (main_window)
- `_on_db_rename_requested(kind, old)`: prompt for the new name (a small
  input dialog seeded with `old`; test seam bypasses the prompt). Apply
  `rename_table`/`rename_field` to the Raw XML buffer via a guarded write that
  marks the document dirty (and pushes a normal snapshot). Show a status message
  with the replacement count. Then re-run the current check so the tree refreshes.

## Data flow

Database menu → `seed_params` / ensure a connection (open dialog if none) →
`fetch_schema(params)` (wrapped in try/except; connection/driver errors →
status-bar message, no crash) → `compare.check_*` against `_current_project` →
`DbCheckPanel.set_result(...)` → reveal the Database Check tab.

## Error handling

- No project loaded → status message ("Open a project first.").
- No/blank connection → open Connection Setup instead of failing.
- Connection/query failure (bad host, auth, psycopg missing) → the try/except in
  the run path shows the error text in the status bar; `test_connection` surfaces
  it inline in the dialog. Never crash the window.
- Missing `<ConnectionOptions>` → seed blanks; the user fills them in.

## Testing (headless, no modals, no live DB)

- `config`: `connection_from_tree` parses a synthetic tree's `<ConnectionOptions>`
  (password always blank); `seed_params` precedence (XML over settings for
  non-password; settings for password); `save`/`load` round-trip via injected
  QSettings.
- `introspect`: `fetch_schema`/`test_connection` with a fake `runner` returning
  canned `pg_catalog`-shaped rows → assert the `TableInfo`/`ColumnInfo` map incl.
  `kind` (table/view/matview), `format_type` data_type, `is_pk`, `is_fk`,
  `is_nullable`, `default`, and the ok/error results. psycopg is never imported.
- `compare` (pure): synthetic `ProjectModel` + `DatabaseSchema` → assert both
  directions' `TableCheck`/`ColumnCheck` (found/missing table, missing column,
  columns under a missing table all `ok=False`, `kind`, `invocations` count,
  `ColumnInfo` attached to found columns, sort order).
- `rename` (pure): counts + correctness; only the targeted attribute is touched;
  unrelated text with the same substring is untouched.
- UI: dialog `test()` sets the status via a stubbed tester; `DbCheckPanel.set_result`
  renders the right prefixes ((T)/(V)/(M)), `(×N)` counts, PK underline (item font),
  `(fk)`, datatype, NOT NULL/DEFAULT text, and ✓/✗ markers; "Show only mismatches"
  filters to `ok=False` rows and the header shows the mismatch count; the
  `rename_requested` and `jump_requested` signals fire; `_on_db_rename_requested`
  (prompt stubbed) applies the pure rename to the buffer, marks dirty, and re-runs;
  `_on_db_jump_requested` navigates the editor. Menu actions exist and are wired.
  No `.exec()`; no real connection.

## Build order (2 sub-projects, each build → review → merge)

1. **Connectivity:** `db/config`, `db/introspect`, the Database menu skeleton, and
   the Connection Setup dialog + Test. `psycopg[binary]` added to deps.
2. **Comparison & reconcile:** `db/compare` + `db/rename` (pure), the Database
   Check results tab, the two check menu items, and the rename→replace-all action
   with re-run.

## Non-goals

- Editing/writing the database (read-only introspection only).
- Decrypting the obfuscated XML password (ignored; entered fresh).
- Type/constraint validation as pass/fail (found/missing is name-based only; the
  datatype, PK, FK, nullability and default are shown as *informational* metadata,
  not validated against the XML).
- Scoping a column rename to a single table (global per-attribute replace by design).
- Using `<ScriptConnectionOptions>` (design-time `<ConnectionOptions>` only).
