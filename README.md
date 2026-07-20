# PGTP Editor

A companion desktop editor for SQL Maestro's **PostgreSQL PHP Generator** (`.pgtp`) project files.

PHPGen's own GUI compiles a `.pgtp` XML project into a working PHP CRUD web application, but it doesn't support several workflows a development team needs day to day: diffing/merging two project files, keeping field captions consistent across a large project, checking a project against the live database, or safely hand-editing the raw XML. PGTP Editor adds those capabilities **without displacing the vendor GUI** — PHPGen remains the canonical thing that compiles `.pgtp` → PHP; this tool reads, diffs, checks, and (optionally) writes back `.pgtp` XML.

Full background, architecture rationale, and the reasoning behind every scope decision live in [`docs/superpowers/specs/`](docs/superpowers/specs/) and [`docs/superpowers/plans/`](docs/superpowers/plans/) — this README is a map of what's actually built, not a design document.

## Features

### Project shell
- Docked, resizable IDE-style layout: Project Tree (left), Properties (right), Audit/Problems (bottom), a tabbed center stage (Diff/Merge, Caption Management, Raw XML).
- Project Tree shows every Page/Detail/Column/Event in a `.pgtp` file with type prefixes (`(P)`/`(D)`/`(C)`/`(E)`), schema/table names, and client/server event-side indicators. Double-clicking a node jumps to it in the Raw XML editor.
- Full menu bar (File, Edit, View, Schema, Database, Tools, Generation, Help) with right-click context menus per tree node.
- Light/Dark theme toggle, a customizable icon toolbar (Customize Toolbar dialog lists every available action), and persisted window/dock geometry across sessions.

### Real model
- `pgtp_editor/model/` parses a `.pgtp` file (via `lxml`) into a typed `ProjectModel` — `PageNode`/`DetailNode`/`ColumnNode`/`EventNode`, each carrying its full observed attribute set (not a curated subset) plus source line numbers.
- Handles arbitrarily nested `Detail`-within-`Detail` structures and classifies every `EventHandlers` child as client- or server-side against the authoritative PHPGen event list.
- A malformed file never crashes the app or silently produces an empty tree — parse failures are surfaced clearly, and on a well-formedness failure the raw file opens with the offending line highlighted.

### XML Editor
- A real syntax-highlighting, line-numbered, **foldable** code editor (`pgtp_editor/ui/xml_editor.py`) powers the Raw XML tab — unclosed-quote propagation, current-line highlighting, auto-indent, and auto-closing brackets/quotes/tags.
- **Ctrl+Space attribute autocomplete**: schema-aware completion of attribute names and values (value suggestions chain from the observed schema), driven by the learned model and bundled XSD.
- **Navigation aids**: Ctrl+click a tag jumps to its matching open/close tag; Alt+click jumps to the parent tag's start. Matching-tag highlighting is cached per-revision so caret movement stays responsive on large files.
- **Search & Replace**: Find, Find Next, Find All (streaming results with a Stop control), Replace, and Replace All (with a replaced-count report).
- **Structural block selection**: Select Enclosing Block / Select Parent Block (`Ctrl+Shift+B` / `Ctrl+Shift+A`) grow the selection up the element tree, with correct copy/paste of folded regions.
- **Bookmarks**: toggle, next/previous, and clear-all, persisted per document.
- **Event-handler code editor**: a dedicated modal for editing the JS/PHP inside `EventHandlers`, integrated with the XML editor and tree insertion.
- `navigate_to_line`/`line_text`/`select_range_on_line` give other features a way to jump to and highlight an exact attribute, not just a line.

### Properties panel
- A read-only, click-to-navigate view (right dock) of everything set on whatever's selected in the Project Tree — every observed attribute for a Page/Detail/Column, or the handler name/side/function-count for an Event.
- Clicking a property scrolls the XML Editor to its exact line and selects the precise `key="value"` substring.
- For a Column, shows its visibility across the ten fixed representation lists (List, View, Edit, Insert, QuickFilter, FilterBuilder, Print, Export, Compare, MultiEdit) — visible vs hidden per representation.

### Diff / Merge
- **Differ engine** (`pgtp_editor/diff/`): a domain-aware structural differ — Pages matched by `fileName`, Details matched by `(tableName, caption)` scoped to their parent — producing `added`/`removed`/`changed` records, not a line-based text diff. Duplicate-sibling matches are flagged `ambiguous` rather than guessed at.
- **Viewer UI**: three ways to launch a comparison (whole-file, right-click a Page, right-click a Detail), a change-list tree with per-difference Apply/Skip checkboxes, Next/Prev Difference navigation, and a detail view (attribute old/new, whole-subtree content, or a unified diff for event-handler code).
- **Write-back**: "Apply Changes to Target" turns checked differences into real mutations of the Target file's `lxml` tree and writes it back with round-trip fidelity, keeping an automatic `.bak` backup. Refuses the whole batch (not per-item) if any checked difference is ambiguous.

### Caption Management (Interface Text)
- A dedicated tab for reviewing and editing interface text across the whole project — captions, plus the column sub-elements PHPGen scatters through the file.
- Filter by database table or column; a breadcrumb shows the current scope, and header dropdowns provide Excel-style checkbox/search filtering per column.
- Edits are staged with change markers (New Value / NULL / Changed colouring) before being written back; Go-to-line jumps from any row to its XML source, and Copy/Paste move values between cells.
- A shared Find / Filter / Replace modal supports plain, extended, and regex matching with match-case and scoping, plus **Bulk Transform** and **Unify** power tools for large-scale caption normalization.

### Schema learning & annotation
- Every file opened via File → Open is fed into a per-user, ever-growing structural model of the (otherwise undocumented) `.pgtp` format — element paths, attributes, inferred types, and observed enum values — reported into the Audit panel.
- **Annotate Schema Values** (Schema menu): a filterable table for attaching human-readable labels to the numeric/coded values the model has observed (e.g. `viewAbilityMode="3"` → "Modal window"), and an offer to fold newly-seen keys into the schema.
- **Open XSD** / **Open XSD Labels (JSON)** expose the generated schema and its label map directly; label meanings surface as value-hover tooltips in the XML editor.

### Validation
- **Validate Project** runs layered checks: Tier 1 well-formedness plus Tier 2 domain rules, reporting problems into the Audit panel with jump-to-source.

### Database
- **Connection Setup** stores a PostgreSQL connection; introspection is read-only via `pg_catalog` (`pgtp_editor/db/`), with `psycopg` imported lazily so the test suite never needs a live database or even the driver installed.
- **Check: XML → Database** and **Check: Database → XML** compare the project against the live schema in both directions, listing missing/extra tables and columns in a dockable results panel and offering reconcile actions.
- Double-clicking a Database result node lists all of its occurrences; **F3** steps through them.
- Running **Tools → Reparse Raw XML into Tree** also refreshes an open Database Check panel against the cached schema, so you immediately see how edits changed database completeness — without re-querying.
- **Create from DB table** (right-click a Database → XML table/view node): synthesize a `<Page>` inserted into the buffer before `</Pages>` (with automatic `fileName` de-duplication), or a `<Detail>`/`<Lookup>` fragment copied to the clipboard. Attribute parity is calibrated against a real clean-defaults capture (`tests/generation/fixtures/golden_newtable_1.*`) and driven by declarative rules in `generation/type_map.py`.

### Generation (vendor CLI + re_phpgen)
The Generation menu covers both the canonical vendor compile and an experimental in-house generator used for parity analysis.

- **Generate PHP...** runs the SQL Maestro PHP Generator CLI non-interactively
  (`PgPHPGeneratorPro.exe "<project.pgtp>" -output "<folder>" -generate`) via an async `QProcess`, streaming the merged generator log line-by-line into the Audit panel so the UI never freezes. **Locate PHP Generator Executable...** stores the path per-user; **Open Output Folder** reopens the last output.
- **panGen (Generate Own PHP)** runs the sibling **re_phpgen** project's own `.pgtp` → PHP generator (`python -m re_phpgen pangen ...`) into a `_pangen` sibling subfolder, so the manually-generated vendor baseline in the output folder is never overwritten. **Locate panGen Runtime...** stores the re_phpgen repo root; its own virtualenv is used when present.
- **rePHPgen (Analyze Gap)** runs the same repo's `analyze` command to compare the vendor output against our `_pangen` output and produce a **masked-parity gap report**: pages bucketed as ok / diff / missing / error, with ranked diff-cause markers, plus a warning when the vendor output is older than the project file. The human-readable summary is shown in a dialog and the underlying JSON kept for the session.
- **Save reJSON...** writes that gap JSON to a chosen location for sharing or tracking parity over time.
- Page-level defaults emitted for new pages are **calibrated against a real PHP Generator oracle** (the vendor default-options panel decoded to its XML attributes), so synthesized pages match what the vendor GUI would produce.

> **About re_phpgen.** `re_phpgen` is a separate, parity-first reverse-engineering project (its own repository) aiming to reproduce the vendor's `.pgtp` → PHP output before eventually owning the runtime. PGTP Editor does not embed it; it shells out to it through the Generation menu above. The generation-side glue (`pgtp_editor/generation/`) is fully unit-tested with golden fixtures and fakes, so the suite runs without either the vendor executable or the re_phpgen checkout present.

### Productivity & diagnostics
- **Undo/Redo** with a snapshot **History…** jump list; **Revert** restores the on-disk version (with `.bak` safety); **Close** guards unsaved changes.
- **Find Reused Tables** surfaces every table used by more than one page.
- **Manual** (Help → Manual) bundles an in-app English manual covering every shipped feature.
- **Debug mode**: launch with `pgtp_editor --debug` (or `PGTP_EDITOR_DEBUG=1`) for a full-detail diagnostic log — an automatic function tracer plus targeted seam logs and always-on crash capture. **Help → Open Log Folder** opens the log location.

## Planned / not yet built

- Deeper schema-aware inline validation and richer hover tooltips in the XML editor.
- re_phpgen parity is an ongoing effort tracked by the gap report above, not a finished 1:1 generator.

Two originally-planned features (dedicated Move/Copy-Detail tooling and Client/read-only-page generation) were dropped once the XML Editor's structural selection + ordinary clipboard operations made dedicated tooling for them unnecessary — see `docs/superpowers/specs/2026-07-11-pgtp-editor-design.md` for the full reasoning.

## Development setup

    pip install -e ".[dev]"

## Running the app

    python -m pgtp_editor.main

Add `--debug` for a full diagnostic log:

    python -m pgtp_editor.main --debug

## Running tests

    pytest

1519 tests passing as of this writing, spanning the model, diff, schema-learning, validation, database, generation (vendor + re_phpgen glue), and UI layers.

## Building a Windows release

    python optimized_build.py

Produces a size-optimized onedir PyInstaller bundle at `dist/PGTPEditor/`. Package it into a user-space installer with `docs/installer.iss` (Inno Setup) — see that file for the exact install/upgrade/file-association behavior.

## Licensing and credits

GPL-3.0. See Help → About in the running app for full OSS attribution ([BoomslangXML](https://github.com/driscollis/BoomslangXML), [QCodeEditor](https://github.com/luchko/QCodeEditor), and vendored runtime dependencies).
