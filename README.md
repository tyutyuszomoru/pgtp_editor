# PGTP Editor

**An IDE for applications that use `.pgtp` for CRUD and PostgreSQL functions for business logic.**

Those applications have two halves. The CRUD half is a SQL Maestro **PostgreSQL PHP Generator** (PHPGen) project — a `.pgtp` XML file the vendor tool compiles into a PHP web application. The business-logic half lives in the database, as plpgsql functions, procedures and triggers. PGTP Editor is the tool for **both halves and the seam between them**: it edits and diffs the `.pgtp` XML, and it owns the database-side workflow end to end — browsing DDL, authoring and versioning it, checking it in a disposable sandbox, and deploying it deliberately.

**Why it exists.** The reference experience for the database half is DBeaver, *"where the only possibility is to break the database"*: editing a function and deploying it are the same keystroke, `CREATE OR REPLACE` against the live database with no intermediate state, no preview and no undo. PGTP Editor's core loop is **edit → check → apply**, with a sandbox database as the missing intermediate state where *"I changed this"* and *"production changed"* are finally two different events.

Two invariants run through everything:

- **Never a silent wrong result.** Every gesture that cannot do the right thing states why instead of guessing — an ambiguous merge is refused as a batch, an expansion that would destroy hand-written text declines, a check that could not map a line reports no line rather than a plausible one.
- **Byte-for-byte round-trip fidelity** on `.pgtp` files: attribute order, escaping, LF endings and absence of reformatting are preserved, or round-tripping through the vendor GUI breaks.

PHPGen remains the canonical thing that compiles `.pgtp` → PHP. This tool does not displace it.

**The specification is [`docs/superpowers/CONSOLIDATED_SPEC.md`](docs/superpowers/CONSOLIDATED_SPEC.md)** — the single authoritative source for current design, with a supersession ledger recording every overridden decision. (`docs/superpowers/specs/` is frozen historical record; read it for rationale, never for current behaviour. `docs/superpowers/plans/` holds per-feature implementation plans.) End users want **Help ▸ Manual** in the running app instead.

**How this project is built is itself documented:** [`docs/DEVELOPMENT_MANUAL.md`](docs/DEVELOPMENT_MANUAL.md) is the full development guide. Part I is the operational loop — sync `main`, open Claude Code at the repo root, cut a branch, run the tests, open a PR, and how the owner reviews and merges it. Part II describes the agent-driven build model — one orchestrating session, a cast of specialist subagents, and a set of queue files each with exactly one writer (spec, manual, test log, bug queue, feature queue, decision queue). Read it before contributing; it explains who owns which file and why nothing ships without its spec, its tests and its manual entry caught up.

## What it can do today

The app opens on a **launcher** offering its three modes — **Standalone** (a `.pgtp` file, no project), **Project** (a DDL project with target and sandbox databases) and **Maintenance** (one-off setup work on the app's own schema).

### Shell

- IDE-style docking. Left dock tabs: **Project tree**, **Contents** (manual), **Database/XML Coherence**, **DDL Objects**, **Findings**. Bottom dock: **Activity Log** (append-only per-project journal) and **Messages** (accumulated check/lint/validate output). Right dock: **Properties**.
- Two menu bars. The window bar — File, View, Schema, Database, Tools, Generation, **Settings** (Maintenance mode only), Help — and an **Editor menu bar** above the central pane holding editing commands: **History · Select · Parsing · Navigation · Deployment**. Every command on either bar is pinnable to the customizable toolbar and rebindable via **View ▸ Customize Shortcuts…**, which refuses a short, reasoned list of chords that widgets already answer rather than silently creating a double binding Qt would resolve by firing neither. `docs/KEYBINDINGS.md` is the register of every chord in the app, verified against the code by a test.
- A static status bar: a colour-coded mode indicator, a busy slot, and **Quality ●** / **Sandbox ●** connectivity dots polled every 30 s while the window is active. It is never a scrolling message board.
- Light/Dark themes, persisted geometry, and a searchable Breeze icon picker for toolbar buttons.

### `.pgtp` editing

- **Model.** `lxml`-backed parse into typed `PageNode`/`DetailNode`/`ColumnNode`/`EventNode`, each carrying its full observed attribute set and source line numbers, with arbitrarily nested `Detail`-in-`Detail` structures and every `EventHandlers` child classified client- or server-side against the authoritative 40-handler list. A malformed file never yields a silently empty tree.
- **Raw XML editor.** Syntax highlighting, folding, a multi-zone gutter, auto-indent and auto-close, Ctrl+click tag matching, structural block selection, bookmarks (persisted per project), and a permanently visible Find/Replace bar with streaming Find All.
- **Format Selection (`Ctrl+Alt+F`) on any XML surface** — Raw XML, Edit XSD and draft fragment tabs — reindenting by element depth and *only* that: never inside an opening tag, never touching element text (which is where entity-escaped PHP/JS handler bodies live), never entering a comment or CDATA section. Mis-nested or half-cut selections are refused whole rather than reformatted into a shape the document does not have. The same chord reindents SQL in the SQL editors; which engine answers is decided by the surface, never by guessing from the text. Both engines are configurable from **Settings ▸ Autoformatter settings…** (Maintenance mode) — indent unit, keyword casing, a per-clause break/indent grid — over a deliberately small set of options, small enough that the formatter is provably a fixed point of its own rules. The defaults are byte-identical to the unconfigurable formatter that preceded them.
- **Schema-aware completion.** Ctrl+Space completes attribute names and values from a hand-curated `curated.xsd`, editable in-app (Schema menu), with a learned second schema derived from every file opened.
- **Diff / Merge as a mode.** A domain-aware structural differ (Pages by `fileName`, Details by `(tableName, caption)`), per-difference Apply/Skip, and write-back with `.bak` backup. Ambiguous matches are flagged, and the whole batch is refused rather than guessed at.
- **Caption Management.** A dedicated grid for interface text across the project, with Excel-style header filters, staged edits, go-to-line, bulk transform and Unify.
- **Validation and DB coherence.** Tier-1 well-formedness plus Tier-2 domain rules; and a merged **Database/XML Coherence** view comparing the project against the live schema in one tree, with **Create from DB table** synthesizing a `Page`/`Detail`/`Lookup` calibrated against a real vendor capture.

### PostgreSQL DDL work

- **DDL Explorer.** Read-only introspection through `pg_catalog` into one synthesized DDL buffer plus a cross-referenced tree (Tables, and Functions & Procedures; triggers appear under both). Two instances can be open at once — **DDL Explorer (Quality)** and **DDL Explorer (Sandbox)**.
- **DDL object editor.** An editable single-object tab with schema-aware Ctrl+Space completion, `Ctrl+Alt+F` Format Selection, and a gutter that shows **body-relative line numbers** beside absolute ones, because `plpgsql_check` reports by body line.
- **Authoring aids.** Snippets (`Ctrl+Alt+E`), **Expand SELECT** into its column list (`Ctrl+Alt+C`), **JOIN on foreign key** (`Ctrl+Alt+J`) and **signature help** (`Ctrl+Shift+Space`). **Structural selection by keyboard:** `Ctrl+Shift+A` grows the selection one plpgsql structure at a time — the word, the enclosing parentheses, the clause, the statement, then each enclosing `IF` / `LOOP` / `CASE` / `BEGIN…END` — and `Ctrl+Shift+Z` steps it back inward. The span model that drives it is offline and refuses to guess: unbalanced text yields the spans it *could* close and no more, so the ladder tops out a rung early rather than selecting a range whose end was invented. Snippets are editable and stored per user in `snippets.json`, with explicit Export/Import for sharing (**Settings ▸ Edit Snippets…**, Maintenance mode).
- **Object creation and table ALTERing.** Add Trigger / New Function or Procedure, and an `Alter Table ▸` submenu of twelve column and constraint operations. All of them only generate DDL into an editable tab — nothing reaches a database until you say so.
- **Projects.** **New Project** creates the whole thing in one pass: the folder, an optional local sandbox (provisioned and tested for superuser there and then, with or without cloned data), an optional attached `.pgtp`, and — revealed by that attachment — the quality-server connection, pre-filled from the file's own connection block. Nothing about a project is inferred from the fact that opening one thing populates another.
- **The sandbox and the check ladder.** A local, disposable PostgreSQL sandbox (provisioned from **New Project** or **Project Settings ▸ Connections**, optionally cloned with data) runs a layered check: parse, apply, then `plpgsql_check`. Findings land as clickable `[Check]` rows. A **Sandbox SQL Console** tab runs ad-hoc SQL — sandbox-only, structurally, with a row cap and a mandatory statement timeout.
- **Deployment.** Every save and every outward effect is a named entry on the **Deployment** menu, per active tab: `Check and commit to sandbox`, `Apply to quality`, `Save in Project`, `Deploy .pgtp`, `Save XSD`, `Save PHP File`. **None of them carries a keyboard shortcut** — an irreversible outward effect must not be one keystroke away, and `Ctrl+S` is deliberately dead app-wide so a save reflex can never hit the wrong target.
- **Project Status.** A five-node diagram of the project, its `.pgtp`, the quality database and the sandbox, with per-node drill-down, refreshing while open.

### Generation, PHP and diagnostics

- **Generate PHP…** runs the vendor CLI asynchronously, streaming its log into the Activity Log. **panGen** and **rePHPgen (Analyze Gap)** shell out to the sibling `re_phpgen` project — a separate parity-first reverse-engineering effort — to produce a masked-parity gap report. The vendor generator is a Windows executable; panGen is not, and runs on Windows and Linux alike. The suite runs without either the vendor executable or the `re_phpgen` checkout present.
- **PHP file editing** with `php -l` linting, on demand or on save.
- **MCP server** (`Tools ▸ Start MCP Server`, or headless `--mcp`): six read-only tools exposing the project model and database introspection.
- **Debug mode** (`--debug` / `PGTP_EDITOR_DEBUG=1`): a full-detail trace log plus always-on crash capture; **Help ▸ Open Log Folder**.

## Where it is going

- **`.pgtp` ↔ database synchronization** is the direction of travel: keeping the XML project and the live schema in step, so a change in either is a visible, reviewable event rather than a discovery.
- **Git-backed DDL versioning** — checkout, drift markers and a reviewed deploy bundle — is designed and largely built; the git integration itself is an explicit placeholder.
- **`Generate Deployment SQL`** — a reviewed deployment script as the deliverable of the edit/check loop — is specified and not yet built.
- **An editing-primitive layer for the editors, specified as vim's command grammar.** The editors need relative count-motions, go-to-line and delete/change/yank by word, line and motion; the choice was to adopt a standard vocabulary or invent a parallel keymap of Ctrl-chords, and the standard one won — *"go down 42 lines"* is a count applied to a motion, which no menu and no Windows editor expresses. So `Esc` will put an editable editor into a **Command mode** beside the ordinary **Edit mode**, per tab, transient, with nothing persisted and no setting to turn on. **Edit mode gains nothing** — that is the point — and `:` addresses the app's own menu commands rather than inventing a second vocabulary. Specified, not yet built.
- **`re_phpgen`'s stated end goal is production replacement of the vendor generator.** That wall opens only when the falsifiable promotion criteria hold, and even then cutover is per-project and explicit. Today it is gap-analysis only.

## Development

    pip install -e ".[dev]"
    python -m pgtp_editor.main            # add --debug for a full diagnostic log

Tests mirror the package layout (`pgtp_editor/<area>/foo.py` → `tests/<area>/test_foo.py`) and run headless:

    QT_QPA_PLATFORM=offscreen python -m pytest -q -n 10

6674 passing / 51 skipped at the last full-suite run recorded in [`docs/TEST_LOG.md`](docs/TEST_LOG.md), spanning the model, diff, schema-learning, validation, SQL analysis, database, generation and UI layers. That log is the committed record of verified runs, and this line cites it rather than a number of its own — a count nothing verifies is stale by the next commit.

**Windows release:** `python optimized_build.py` produces a size-optimized onedir PyInstaller bundle at `dist/PGTPEditor/`; package it with `docs/installer.iss` (Inno Setup).

## Licensing and credits

GPL-3.0. Authors: Botond Zalai-Ruzsics and MDS — Maintenance Data Services. Not affiliated with or endorsed by SQL Maestro Group. See Help ▸ About in the running app for full OSS attribution ([BoomslangXML](https://github.com/driscollis/BoomslangXML), [QCodeEditor](https://github.com/luchko/QCodeEditor), [QDarkStyleSheet](https://github.com/ColinDuquesnoy/QDarkStyleSheet)).
