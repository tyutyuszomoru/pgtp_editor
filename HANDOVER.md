# PGTP Editor — Handover

A PySide6 desktop companion for SQL Maestro **PostgreSQL PHP Generator** `.pgtp`
project files. This doc is for picking the project up on another machine.

## Get running on a new PC

```bash
git clone https://github.com/tyutyuszomoru/pgtp_editor.git
cd pgtp_editor
python -m venv .venv && .venv\Scripts\activate      # optional; Python 3.10+ (dev machine uses 3.13)
pip install -e ".[dev]"                              # PySide6, lxml, defusedxml, psycopg[binary] + pytest tooling
python -m pgtp_editor.main                           # launch the app
```

Run the tests (headless Qt is forced by `conftest.py`, but setting it explicitly is fine):

```bash
# bash:      QT_QPA_PLATFORM=offscreen python -m pytest -q
# PowerShell: $env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q
```
Current status: **~1271 passing, ~32 skipped, 0 failures** (skips are real-sample
tests that need the private `.pgtp` files, which are not in the repo).

## What the app does (feature map)

- **Project tree** (left dock): pages / details / columns / event handlers. Single-click
  → Properties; double-click → jump to Raw XML. Rich right-click menus per node.
- **Raw XML editor** (center): syntax highlighting, folding (fine chevron glyphs),
  current-line/matching-tag highlight, `Ctrl+Shift+B` block-select, code-region styling,
  hover tooltips for schema-labelled attribute values, right-click "Add attribute"
  (unused settings-keys) and "Edit code…", **bookmarks** (gutter strip + `Ctrl+F2`,
  `F2`/`Shift+F2`, Bookmarks menu).
- **Find / Replace** bar: streaming Find All + Stop + counts.
- **Code Editor** (modal): JS/PHP event-handler bodies — highlighting, auto-close,
  selection-wrap, `Ctrl+S`/`Ctrl+W`; opens at 80% of the host window.
- **Caption Management** mode: bulk grid over captions (breadcrumb, New Value/`<NULL>`,
  Changed marker/coloring, header filters + search, Find/Filter/Replace modal,
  Bulk Transform, Unify, Go-to-line, copy/paste).
- **Diff / Merge** (under Tools): compare/merge two `.pgtp` files.
- **Schema** menu: Open XSD / Open XSD Labels (read-only viewers); **Annotate Schema
  Values** (mark attributes setting/content, label enum values → editor hover hints).
- **Database** menu: Connection Setup (+ Test), **Check XML→DB** and **DB→XML** →
  results in the "Database Check" left-dock tab: `(T/V/M)` kind + `(×N)` invocation
  count, PK underline, `(fk)`, `format_type` datatype, NOT NULL/DEFAULT, ✓/✗,
  show-only-mismatches, double-click→jump, rename-not-found→replace-all + re-run.
- **Validation** (Tools): structural checks (dup page fileName, missing attrs, …).
- **Generation** menu: locate PHP Generator exe, Generate (save prompt, output folder).
- **View**: dock toggles, Expand/Collapse all, Wrap (editor right-click), **Light/Dark
  theme** toggle, **Customize Toolbar…**. Window geometry/state + theme + toolbar layout
  persist (QSettings, IniFormat). File: Open/Save/Save As/**Close**(prompt)/**Revert**(.bak);
  `Ctrl+O/S/Shift+S/W`. Edit: **Undo/Redo/History** (10-snapshot XML history).
- **Manual**: Help ▸ Manual (F1) — bundled `resources/manual.md` in a center tab +
  left-dock Contents.

## Layout

```
pgtp_editor/
  main.py                 app entry
  ui/                     all Qt widgets: main_window, xml_editor, center_stage,
                          project_tree, properties_panel, caption_*, code_editor,
                          connection_setup_dialog, db_check_panel, async_task,
                          theme, toolbar_registry, customize_toolbar_dialog,
                          manual_panel, schema_viewer*, history, icons, about
  model/                  .pgtp parser + nodes + encoding (CESU-8 repair) + line_index
  db/                     config (connection + settings), introspect (pg_catalog via
                          psycopg, lazy import + injectable runner), compare, rename
  diff/                   differ / apply / resolve
  schema_learning/        model, parser, xsd_gen, settings_index, storage
  analysis/               reused_tables
  validation/             tier2
  generation/             config + runner
  resources/              manual.md, icons/breeze/* (LGPL-3.0)
docs/superpowers/         specs/ and plans/ for every feature (design history)
tests/                    pytest + pytest-qt suite
```

## How this project is built (workflow conventions)

Each feature goes **brainstorm → spec (`docs/superpowers/specs/`) → plan
(`docs/superpowers/plans/`) → TDD implementation → spec + code-quality review →
`git merge --no-ff` to `main`**, in an isolated git worktree under
`.claude/worktrees/`. Nothing is pushed unless explicitly requested.

**Hard rules that keep the suite healthy — keep following them:**
- **Modal-hang guardrail:** no test may reach an unpatched `QMessageBox` /
  `QDialog.exec()` / `QFileDialog` — it blocks the event loop forever. Dialogs are
  non-modal (`show()`), driven by methods/signals; blocking calls (DB, prompts) go
  through injectable seams (`_run_async`, `_fetch_db_schema`, `_prompt_rename`,
  `tester=`, `runner=`) that tests stub synchronously.
- **QSettings isolation:** the root `conftest.py` redirects QSettings to a per-test
  temp dir; the app uses IniFormat under UserScope (not the native registry).
- **Byte-preserving save:** `_write_project_text` uses `newline=""` (no LF→CRLF) and
  writes UTF-8; there's a round-trip fidelity test. Don't regress it.
- Pure logic (db/compare, db/rename, settings_index, history, analysis) is Qt-free
  and unit-tested; Qt layers stay thin.

## Gotchas / environment notes

- **`localhost` hangs the DB connect on Windows** (libpq tries IPv6 `::1` first and
  stalls); **use `127.0.0.1`**. The connect runs off the GUI thread with a
  `connect_timeout`, so a stall now surfaces a bounded status-bar error instead of
  freezing. Saved connection settings win over the `.pgtp`'s `<ConnectionOptions>`.
- The DB password is stored in QSettings in **plain text** (by design choice); it is
  never read from the `.pgtp` (stored obfuscated there).
- `git worktree remove` sometimes hits a Windows "Permission denied" file lock — the
  branch still deletes; run `git worktree prune` after.
- LF→CRLF git warnings on Windows are benign.
- Real-sample tests skip unless the private samples are present under `sample/`.

## Open threads / possible next steps

- **Window-close (X) does not prompt on unsaved changes** — only File ▸ Close does
  (deliberate, to avoid a teardown-hang). Add an X-prompt if wanted.
- DB check enhancements to consider: tune the `connect_timeout`; optionally offer to
  rewrite `localhost`→`127.0.0.1`; reparse tree into the model after a rename so the
  Project tree (not just the check) reflects it.
- The design specs in `docs/superpowers/specs/` are the source of truth for each
  feature's intended behavior and non-goals — read the relevant one before extending.
```
