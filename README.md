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

## In progress / not yet merged

These are designed and (in some cases) implemented in separate worktrees, pending review and merge into this branch:

- **XML Editor** — a real syntax-highlighting, line-numbered, foldable code editor for the Raw XML tab, with Tier-1 parse-failure fallback (opens the raw file with the error line highlighted). Planned follow-ons: bookmarks, search/replace, structural block selection (`Ctrl+Shift+B`/`A`, including correct copy/paste of folded regions), and schema-aware hover tooltips/inline validation.
- **Properties panel** — a read-only, click-to-navigate view of everything set on the selected tree node, refining past the tree's line-level navigation to the exact attribute in the XML Editor.
- **Interface Text Collection** — filter by database column or table across the whole project to review/edit captions, placeholders, `Format`/`Lookup`/`ViewProperties`/`EditProperties`, in one place.

Two originally-planned features (dedicated Move/Copy-Detail tooling and Client/read-only-page generation) were dropped once the XML Editor's structural selection + ordinary clipboard operations made dedicated tooling for them unnecessary — see `docs/superpowers/specs/2026-07-11-pgtp-editor-design.md` for the full reasoning.

## Development setup

    pip install -e ".[dev]"

## Running the app

    python -m pgtp_editor.main

## Running tests

    pytest

258 tests passing as of this writing (model, diff, schema learning, and UI layers).

## Licensing and credits

GPL-3.0. See Help → About in the running app for full OSS attribution ([BoomslangXML](https://github.com/driscollis/BoomslangXML), [QCodeEditor](https://github.com/luchko/QCodeEditor), and vendored runtime dependencies).
