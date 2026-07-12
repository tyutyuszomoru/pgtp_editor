# PGTP Editor

A companion desktop editor for SQL Maestro's **PostgreSQL PHP Generator** (`.pgtp`) project files.

PHPGen's own GUI compiles a `.pgtp` XML project into a working PHP CRUD web application, but it doesn't support several workflows a development team needs day to day: diffing/merging two project files, keeping field captions consistent across a large project, or safely hand-editing the raw XML. PGTP Editor adds those capabilities **without displacing the vendor GUI** — PHPGen remains the only thing that compiles `.pgtp` → PHP; this tool only reads, diffs, and (optionally) writes back `.pgtp` XML.

Full background, architecture rationale, and the reasoning behind every scope decision live in [`docs/superpowers/specs/`](docs/superpowers/specs/) and [`docs/superpowers/plans/`](docs/superpowers/plans/) — this README is a map of what's actually built, not a design document.

## Features

### Project shell
- Docked, resizable IDE-style layout: Project Tree (left), Properties (right), Audit/Problems (bottom), a tabbed center stage (Diff/Merge, Caption Management, Raw XML).
- Project Tree shows every Page/Detail/Column/Event in a `.pgtp` file with type prefixes (`(P)`/`(D)`/`(C)`/`(E)`), schema/table names, and client/server event-side indicators.
- Full menu bar (File, Edit, View, Diff/Merge, Schema, Tools, Generation, Help) with right-click context menus per tree node.

### Real model
- `pgtp_editor/model/` parses a `.pgtp` file (via `lxml`) into a typed `ProjectModel` — `PageNode`/`DetailNode`/`ColumnNode`/`EventNode`, each carrying its full observed attribute set (not a curated subset) plus source line numbers.
- Handles arbitrarily nested `Detail`-within-`Detail` structures and classifies every `EventHandlers` child as client- or server-side against the authoritative PHPGen event list.
- A malformed file never crashes the app or silently produces an empty tree — parse failures are surfaced clearly.

### Diff / Merge
- **Differ engine** (`pgtp_editor/diff/`): a domain-aware structural differ — Pages matched by `fileName`, Details matched by `(tableName, caption)` scoped to their parent — producing `added`/`removed`/`changed` records, not a line-based text diff. Duplicate-sibling matches are flagged `ambiguous` rather than guessed at.
- **Viewer UI**: three ways to launch a comparison (whole-file, right-click a Page, right-click a Detail), a change-list tree with per-difference Apply/Skip checkboxes, and a detail view (attribute old/new, whole-subtree content, or a unified diff for event-handler code).
- **Write-back**: "Apply Changes to Target" turns checked differences into real mutations of the Target file's `lxml` tree and writes it back with round-trip fidelity, keeping an automatic `.bak` backup. Refuses the whole batch (not per-item) if any checked difference is ambiguous.

### Schema Learning
- Every file opened via File → Open is fed into a per-user, ever-growing structural model of the (otherwise undocumented) `.pgtp` format — element paths, attributes, inferred types, and observed enum values — reported into the Audit panel.
- **Annotate Schema Values** (Schema menu): a filterable table for attaching human-readable labels to the numeric/coded values the model has observed (e.g. `viewAbilityMode="3"` → "Modal window"), so `schema.xsd` becomes self-documenting over time.

### XML Editor
- A real syntax-highlighting, line-numbered, foldable code editor (`pgtp_editor/ui/xml_editor.py`) powers the Raw XML tab — unclosed-quote propagation, current-line highlighting, auto-indent, and auto-closing brackets/quotes/tags.
- On a Tier-1 (well-formedness) parse failure, the app doesn't just show an error dialog: it opens the raw file in this editor with the exact failing line scrolled-to and highlighted.
- `navigate_to_line`/`line_text`/`select_range_on_line` give other features (like Properties, below) a way to jump to and highlight an exact attribute, not just a line.

### Properties panel
- A read-only, click-to-navigate view (right dock) of everything set on whatever's selected in the Project Tree — every observed attribute for a Page/Detail/Column, or the handler name/side/function-count for an Event.
- Clicking a property scrolls the XML Editor to its exact line and selects the precise `key="value"` substring — refining past the tree's own line-level navigation.

## Planned, not yet started

- **Interface Text Collection** — filter by database column or table across the whole project to review/edit captions, placeholders, `Format`/`Lookup`/`ViewProperties`/`EditProperties`, in one place.
- **XML Editor** follow-ons: bookmarks, search/replace, structural block selection (`Ctrl+Shift+B`/`A`, including correct copy/paste of folded regions — designed in `docs/superpowers/specs/2026-07-12-pgtp-editor-xml-structural-selection-design.md`, not yet implemented), and schema-aware hover tooltips/inline validation.

Two originally-planned features (dedicated Move/Copy-Detail tooling and Client/read-only-page generation) were dropped once the XML Editor's structural selection + ordinary clipboard operations made dedicated tooling for them unnecessary — see `docs/superpowers/specs/2026-07-11-pgtp-editor-design.md` for the full reasoning.

## Development setup

    pip install -e ".[dev]"

## Running the app

    python -m pgtp_editor.main

## Running tests

    pytest

421 tests passing as of this writing (model, diff, schema learning, and UI layers).

## Building a Windows release

    python optimized_build.py

Produces a size-optimized onedir PyInstaller bundle at `dist/PGTPEditor/`. Package it into a user-space installer with `docs/installer.iss` (Inno Setup) — see that file for the exact install/upgrade/file-association behavior.

## Licensing and credits

GPL-3.0. See Help → About in the running app for full OSS attribution ([BoomslangXML](https://github.com/driscollis/BoomslangXML), [QCodeEditor](https://github.com/luchko/QCodeEditor), and vendored runtime dependencies).
