# PGTP Editor — Consolidated Specification

> **Status:** living document · **Last synthesized:** 2026-08-01
> **Source of truth:** this file is the single reconciled specification for PGTP Editor.
> It is synthesized from the dated design specs under [`docs/superpowers/specs/`](specs/) using a
> **latest-wins** rule: where a later spec overrode an earlier decision, only the later decision
> is stated in the body, and the change is recorded in the [Supersession Ledger](#28-supersession-ledger).
> Maintained by the **`spec-maintainer`** agent (`.claude/agents/spec-maintainer.md`) — see
> [§31 Maintenance protocol](#31-maintenance-protocol).

---

## Table of contents

1. [Purpose & scope](#1-purpose--scope)
2. [`.pgtp` file format & invariants](#2-pgtp-file-format--invariants)
3. [Element hierarchy](#3-element-hierarchy)
4. [Technology choices](#4-technology-choices)
5. [Package / module layout](#5-package--module-layout)
6. [Data model](#6-data-model)
7. [App shell](#7-app-shell)
8. [Raw XML editor](#8-raw-xml-editor)
9. [Editor ↔ Tree sync & Reparse](#9-editor--tree-sync--reparse)
10. [Properties panel](#10-properties-panel)
11. [Schema: curated XSD, learning & completion](#11-schema-curated-xsd-learning--completion)
12. [Diff / Merge](#12-diff--merge)
13. [Captions](#13-captions)
14. [Columns](#14-columns)
15. [Search, Find All & Table References](#15-search-find-all--table-references)
16. [Validation](#16-validation)
17. [Database](#17-database)
18. [DDL versioning (standalone Postgres mode)](#18-ddl-versioning-standalone-postgres-mode) — *planned*
    - [18.1 Routines & triggers browsing (DDL Explorer)](#181-routines--triggers-browsing-ddl-explorer) — *implemented (except XML cross-refs)*
    - [18.2 Projects, checkout & state markers](#182-projects-checkout--state-markers) — *planned*
    - [18.3 Deploy workflow & schema diff/migration](#183-deploy-workflow--schema-diffmigration) — *planned*
19. [PHP generation (vendor) & Save](#19-php-generation-vendor--save)
20. [re_phpgen — own generator & gap loop](#20-re_phpgen--own-generator--gap-loop)
    - [20.4 Production cutover](#204-production-cutover-target-design--not-yet-reached) — *planned*
21. [Custom PHP editing](#21-custom-php-editing) — *planned*
22. [Lint integration](#22-lint-integration) — *planned*
23. [MCP integration](#23-mcp-integration) — *planned*
24. [In-app manual](#24-in-app-manual)
25. [Debug mode](#25-debug-mode)
26. [Consolidated menu bar](#26-consolidated-menu-bar)
27. [Consolidated keyboard shortcuts](#27-consolidated-keyboard-shortcuts)
28. [Supersession ledger](#28-supersession-ledger)
29. [Open questions](#29-open-questions)
30. [Testing policy](#30-testing-policy)
31. [Maintenance protocol](#31-maintenance-protocol)

---

## 1. Purpose & scope

PGTP Editor is a **PySide6 (Qt6) desktop tool** for editing SQL Maestro PostgreSQL PHP Generator
("PHPGen" / the "vendor tool") `.pgtp` XML project files. It targets **`.pgtp` format version 22.8**.
It also functions as a **standalone Postgres DDL-versioning tool** (§18) — usable with **zero `.pgtp`
files involved** — sharing the app's existing DB connection, code editor, and diff infrastructure
rather than being a separate product.

**In scope:** parsing, viewing, structurally editing, diffing/merging, validating, and DB-checking
`.pgtp` files; invoking the vendor generator; (as a separate sub-project) reverse-engineering the
vendor's `.pgtp`→`.php` transformation; and — independent of `.pgtp` entirely — versioning PostgreSQL
routine/trigger DDL against git with live-DB drift detection and reviewed deploy (§18). This last item
is a deliberate broadening of the app's purpose beyond `.pgtp` editing: it was designed, and chosen to
live **in this same app as an independent mode**, rather than as a separate tool/repo (the alternative
modeled by `re_phpgen`, §20/§20.4) — see §18 for the rationale.

**Hard boundary (staged, with a named exit):** *today*, `.pgtp` → `.php` compilation is **one-way and
owned by vendor tooling**; PGTP Editor never edits or generates PHP as part of the editing workflow.
`re_phpgen` (§20) stays **gap-analysis-only**, invoked **read-only as a subprocess** — phpgen (the
vendor CLI/GUI) remains the tool of record. This is not a permanent wall: `re_phpgen`'s **stated end
goal is production replacement of the vendor generator**. The wall only opens once **all** of the
falsifiable promotion criteria in §20.4 hold, and even then cutover is **per-project and explicit**
(never silent, never automatic) — see §20.4 for the full criteria and cutover mechanism. phpgen remains
available indefinitely afterward as the fallback/reference oracle.

**Formally dropped features** (see ledger): Move/Copy of `Detail` blocks and Client read-only page
generation — both superseded by the Raw XML editor's structural block-select + OS clipboard, which can
cut/copy/paste even folded blocks.

---

## 2. `.pgtp` file format & invariants

These are load-bearing; every editing path must preserve them.

- Single-root `<Project>` XML. **UTF-8, no XML declaration, no BOM, LF line endings, no CDATA.**
- Inline PHP/JS event-handler code is stored as **entity-escaped text directly inside elements**
  (no CDATA wrapping). `<` and `&` must be XML-escaped when writing handler bodies.
- **Byte-for-byte round-trip fidelity is the master invariant:** attribute order, escaping, LF
  endings, and absence of reformatting must be preserved, or round-tripping through the vendor GUI
  breaks. Saving writes the **raw editor text** (the authoritative surface) — the parsed model is
  never re-serialized on save.
- An element's opening tag (all its attributes) is on a **single line** — relied upon by
  line-anchored edits (captions, DB rename).
- On-disk indentation unit: **two spaces**.
- One known benign residual: libxml2 un-escapes `&quot;` inside element *text* (not attribute values)
  to a literal `"` on reserialization. Round-trip tests normalize this; it is not a bug.
- Sample files (`sample/dev_Ferrara.pgtp`, `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`)
  contain live plaintext DB/SSH credentials. `sample/` and `.superpowers/` are git-ignored and must
  never be committed. Tests needing them skip gracefully when absent.

**Vendor generator CLI (confirmed):**
```
PgPHPGeneratorPro.exe "<project.pgtp>" -output "<output-folder>" -generate
```
Positional = absolute `.pgtp` path; `-output` = target dir; `-generate` = non-interactive. Nonzero
exit **or any stderr** = failure. The vendor CLI's `-generate` is **not trusted for automation** (it
uses a stricter XML parser than the GUI and hangs on a modal `EInvalidXML` dialog).

---

## 3. Element hierarchy

Parent→child whitelist (used by Tier-2 validation and by the model layer):

```
Project
├── ConnectionOptions / ScriptConnectionOptions   (DB+SSH creds — passed through untouched)
├── DataSources → DataSource                        (one per table/view; PK fields, CRUD SQL)
├── Presentation
│   ├── Groups → Group                              (menu groups, referenced by Page@groupName)
│   └── Pages → Page                                (top-level pages)
│       ├── ColumnPresentations → ColumnPresentation
│       │       children: ViewProperties (→ Format), EditProperties, Lookup
│       ├── Columns → {List,View,Edit,Insert,QuickFilter,FilterBuilder,Print,
│       │       Export,Compare,MultiEdit,DefaultSortedColumns} → Column   (~10 context lists)
│       ├── Details → Detail → Page(nested) + MasterForeignKeyColumnMap → FieldMap  (arbitrary depth)
│       ├── PartitionNavigators → PartitionNavigator → Partition → Values → Value
│       └── EventHandlers (OnXxx… inline PHP/JS text)
├── UserCSS / PdfUserStyles / PrintUserStyles / UserJS
├── ExcludedPaths, DefaultPageProperties, DefaultDataFormats
```

Notes:
- Nested `Detail` pages compile to PHP classes named by the full table-ancestry chain.
- **`Format` is never a direct child of `ColumnPresentation`** — it is always nested inside
  `ViewProperties` (grandchild). Verified 887/887 and 1175/1175 in the two samples. Parsers must use
  `col_el.find("ViewProperties/Format")`.
- The same DB table is frequently embedded as a `Detail` in multiple locations as fully-duplicated
  subtrees (PHPGen has no "shared detail" concept) — motivates the reused-table / table-references
  feature.

**Page "Abilities"** (multi-value enums, stored in `*AbilityMode` attributes):
View (Disabled/Separated Page[default]/Modal), Edit & Insert & Copying (…/Inline/Modal), Multi-edit
(Disabled/Separated/Modal), Delete & Multi-delete (Enabled[default]/Disabled). **The numeric-code →
label mapping is not yet fully known** (derive empirically; now powers editor hover tooltips only —
no longer blocks any feature).

---

## 4. Technology choices

| Concern | Choice |
|---|---|
| Language | Python (system interpreter, editable install) |
| GUI | PySide6 (Qt6), genuine `QDockWidget`/`QMainWindow` docking (LGPLv3) |
| XML (model) | `lxml` — preserves attribute order; fast on 4 MB+ files |
| XML (editor scanner) | lenient regex scanner (`ui/xml_structure.py`), **not** lxml (tolerates mid-edit malformed XML) |
| XML (schema learning) | `defusedxml` — independent second parse |
| DB | `psycopg` v3 (`psycopg[binary]`) via `pg_catalog` |
| Diff | custom domain-aware structural differ (identity-keyed, not line-based) |
| Code editor | custom, built on `QPlainTextEdit` |
| Dark theme QSS | QDarkStyleSheet via `qdarkstyle>=3.2` (MIT) — dark mode only; light clears the stylesheet (§7) |

**Licensing:** project is **GPL-3.0**. About box credits BoomslangXML (conceptual prior art),
QCodeEditor (MIT, ported), and QDarkStyleSheet (Colin Duquesnoy, MIT — the dark theme's QSS via the
`qdarkstyle` package, §7). Authors: **Botond Zalai-Ruzsics** and **MDS — Maintenance Data Services**
(https://maint-data.com). Not affiliated with / endorsed by SQL Maestro Group; as-is, no warranty.
(SuperNano credit removed.)

---

## 5. Package / module layout

Actual package (`pgtp_editor/`), reconciling the original design's `ops/`/`external/`/`validate/`
naming with what shipped:

```
pgtp_editor/
├── main.py            # argparse (--debug, optional positional file), QApplication bootstrap
├── debuglog.py        # always-on error log + --debug tracing
├── model/             # lxml-backed model — the ONLY code touching raw lxml
│   ├── nodes.py       # PageNode/DetailNode/ColumnNode/EventNode/ChildElement/RepresentationVisibility, identity, classify_event_side
│   ├── parser.py      # load_project(path) / load_project_from_text(text) / _build_project_model(tree)
│   ├── event_handlers.py  # authoritative 40-handler list, language_for_side
│   ├── line_index.py  # node_at_line(project, line) for click-to-tree
│   └── encoding.py
├── diff/              # domain-aware differ (Qt-free)
│   ├── records.py     # Difference dataclass
│   ├── differ.py      # diff_project / compare_block
│   ├── resolve.py     # resolve_path → node | ResolutionError
│   └── apply.py       # apply_differences (write-back)
├── generation/        # vendor CLI + own-generator wiring + create-from-table
│   ├── config.py      # generator_config.json (executable_path, re_phpgen_root)
│   ├── runner.py      # build_generate_command + GeneratorRunner(QProcess)
│   ├── re_runner.py   # subprocess to re_phpgen
│   ├── type_map.py    # pg-type → presentation rules + PAGE_DEFAULTS (parity source of truth)
│   ├── from_table.py  # build_page/build_detail/build_lookup/serialize
│   └── gap_summary.py
├── schema_learning/   # curated-XSD schema source + vendored learning engine + settings index
│   ├── model.py, parser.py (defusedxml), types.py, xsd_gen.py
│   ├── xsd_load.py    # Qt-free expat loader (DTD refused): curated.xsd → CuratedSchema (§11)
│   ├── xsd_verify.py  # Qt-free expat dialect verifier: verify_curated(text) → list[Issue] (§11)
│   ├── storage.py     # schema_model_path / curated_xsd_path / learned_xsd_path (AppData)
│   └── settings_index.py  # enum_hint, sums (additive-value) derivation, known_attributes/known_values, unused_setting_attributes
├── db/                # PostgreSQL introspection & comparison (Qt-free logic)
│   ├── config.py, introspect.py (psycopg lazy), compare.py, rename.py
│   └── ddl_buffer.py  # build_ddl_text(schema) → (text, [DdlObjectSpan]) — DDL Explorer buffer (§18.1)
├── analysis/
│   └── reused_tables.py   # collect_table_usages → TableUsage/TableReference
├── validation/
│   └── tier2.py       # validate_project → list[ValidationIssue]
└── ui/                # all PySide6 widgets (see below)
```

Key `ui/` modules: `main_window.py`, `center_stage.py`, `project_tree.py`, `xml_editor.py`,
`xml_structure.py`, `code_editor.py`, `event_body.py`, `properties_panel.py`, `find_replace_bar.py`,
`search.py`, `history.py`, `theme.py`, `toolbar_registry.py`, `customize_toolbar_dialog.py`,
`diff_merge_panel.py`, `caption_management_panel.py`, `caption_find_replace_dialog.py`,
`caption_scan.py`, `db_check_panel.py`,
`connection_setup_dialog.py`, `table_references_panel.py`, `ddl_editor_panel.py`,
`ddl_buffer_panel.py`, `manual_panel.py`, `about.py`, `icons.py`.
(Deleted with the curated-XSD pivot, §11: `schema_learning/sync.py`, `schema_learning/merge.py`,
`ui/annotate_popover.py`, `ui/team_sync_dialog.py`, `ui/merge_conflicts_dialog.py`,
`ui/schema_viewer.py`, `ui/schema_viewer_data.py`.)

**Dependency rule:** `model/` touches lxml; nothing in `model/` or `ui/` depends on `diff/`; pure-logic
modules (`search`, `history`, `caption_scan`, `settings_index`, `xsd_load`, `xsd_verify`, `tier2`, `db/*`,
`analysis/*`, `type_map`, `from_table`, `xml_structure`) are Qt-free and unit-testable without a
`QApplication`.

---

## 6. Data model

`model/parser.py::load_project(path) → ProjectModel` uses `lxml.etree.parse()`. Refactored into a thin
path wrapper + `_build_project_model(tree, source_description)` (accepts an already-parsed tree);
`load_project_from_text(text, source_description="<editor>")` parses editor buffer via `io.BytesIO`.
`PgtpParseError(message, line=None)` carries the failing line for XMLSyntaxError.

**Nodes** (`model/nodes.py`), each carries its **identity key**, the full `dict(element.attrib)`
(generic capture — "everything phpgen lets you set" needs no model change), its `sourceline`, and a
retained reference to its live `lxml` element (for write-back):

- `PageNode` — identity `fileName` (fallback `tableName`+`caption`); `attrib`, `sourceline`,
  `element`, child `DetailNode`s, `ColumnNode`s, `EventNode`s.
- `DetailNode` — identity = parent identity + `tableName`; same shape as `PageNode` **including its own
  child `DetailNode`s (recurse)**; carries `sourceline` (outer `<Detail>`), `inner_sourceline` (nested
  `<Page>`), `element` (outer) **and** `inner_page_element` (nested). Merged attributes: nested `<Page>`
  precedence (`merged_attrib.update(inner_page_el.attrib)`).
- `ColumnNode` — identity = parent + `fieldName`; `attrib`, `sourceline`, `element`; four optional
  presentation children as `ChildElement | None`: `format`, `lookup`, `view_properties`,
  `edit_properties`; and `representations: list[RepresentationVisibility]`. Typed property
  `is_calculated` → `attrib.get("isCalculated") == "true"` (lowercase-string boolean convention,
  same as `visible="false"`); consumed by the DB check (§17).
- `EventNode` — identity = parent + handler tag; `{tag_name, side("C"/"S"), text, sourceline, element}`.
- `ChildElement` — `{attrib, sourceline, element}`; does not descend into its own children.
- `RepresentationVisibility` — `{name, visible: bool|None, sourceline: int|None}`.
- `ProjectModel` — `pages`, plus retained `tree: etree._ElementTree` (needed for serialization).

Parser currently parses `Page`, `Detail` (recursive), `ColumnPresentation` (→ columns), `EventHandlers`
(→ events). `DataSources`, `Groups`, `Partitions` are preserved untouched in the tree but not yet
modeled (no consumer). `startup tree is genuinely empty` — no placeholder project.

**Identity keys** (foundational to diff / resolve / rename / coherence):

| Element | Key |
|---|---|
| DataSource | `name` |
| Page (top-level) | `fileName` (fallback `tableName`+`caption`) |
| Detail | parent Page identity + `tableName` (+`caption` for matching) |
| ColumnPresentation | parent identity + `fieldName` |
| Column | parent identity + context + `fieldName` |
| Value | parent `Values` identity + `name` |
| Group | `groupName` |

Duplicate top-level `Page@fileName` is a **hard-blocking** validation rule (it would make identity
ambiguous).

**Event side classification:** authoritative **9 client / 31 server** handler list in
`model/event_handlers.py` as `EVENT_HANDLERS: list[tuple[tag, side]]`; `CLIENT_SIDE_EVENT_NAMES` (9) in
`model/nodes.py`; `classify_event_side(tag) → "C"/"S"`; `language_for_side(side) → "js"|"php"`. This
suffix-normalizing classifier is a **shared contract** — differ and code-editor reuse it; do not
reimplement.

- **Client (9):** OnBeforePageLoad, OnAfterPageLoad, OnInsertFormLoaded, OnEditFormLoaded,
  OnInsertFormEditorValueChanged, OnEditFormEditorValueChanged, OnInsertFormValidate,
  OnEditFormValidate, OnCalculateControlValues.
- **Server (31):** OnBeforePageExecute, OnPreparePage, OnGetCustomPagePermissions,
  OnGetCustomRecordPermissions, OnAddEnvironmentVariables, OnPageLoaded, OnPrepareColumnFilter,
  OnPrepareFilterBuilder, OnGetSelectionFilters, OnGetCustomFormLayout, OnGetCustomColumnGroup,
  OnCustomCompareValues, OnFileUpload, OnGetCustomExportOptions, OnCustomHTMLHeader,
  OnGetCustomTemplate, OnCustomRenderColumn, OnCustomRenderPrintColumn, OnCustomRenderExportColumn,
  OnCustomDrawRow, OnExtendedCustomDrawRow, OnCustomRenderTotals, OnCustomDefaultValues,
  OnCalculateFields, OnGetFieldValue, OnBeforeInsertRecord, OnBeforeUpdateRecord, OnBeforeDeleteRecord,
  OnAfterInsertRecord, OnAfterUpdateRecord, OnAfterDeleteRecord.

---

## 7. App shell

**Layout:** IDE-style docked panels. Left dock is a `QTabWidget` (`self.left_tabs`) hosting **Project
tree**, **Contents** (manual), **Database Check**, **Table references**, and **DDL Objects** (§18.1)
tabs (the latter three hidden until invoked). Center is a tabbed `CenterStage` (Raw XML
[default-visible working tab], Diff/Merge, Caption Management, Manual, Edit XSD, DDL Explorer —
non-Raw-XML tabs hidden until invoked). Bottom is a persistent
**Audit/Problems** panel (`QListWidget`) shared by `[Schema]`, `[Validate]`, `[Find]`, `[PHP]` lines.
Right dock is the **Properties** panel.

**Document state:** `_dirty` + `_set_dirty()` (title gets " *"); editor `textChanged` marks dirty;
load/save/revert clears. **Theme toggles never dirty either document:** `XmlEditor.apply_theme_colors`
sets an `_applying_theme` guard around its `rehighlight()` (which fires a spurious `textChanged` with
no text actually changed); MainWindow's dirty handlers for **both** the Raw XML and Edit XSD editors
consult `XmlEditor.is_applying_theme()` and no-op. `.bak` (single, overwritten, `shutil.copy2`) is written before overwriting an
existing file on save — never on Save-As to a new path, never on a failed/no-op write.
`_write_project_text(path)` writes editor `toPlainText()` as UTF-8 with `newline=""` (byte-preserving).
`_current_project_path` is normalized to `str`.

**Per-tab document routing** (curated-XSD pivot, §11): the Edit XSD tab hosts a second document with
its **own dirty state** (tab-title `*` marker, independent of the project's `_dirty`). **Ctrl+S** and
the Edit-menu Find/Replace actions (Find/Find Next/Find All/Replace/Replace All) route to the
**active** center-stage tab's editor + `FindReplaceBar` — Raw XML when the Raw XML tab is active, the
mode-aware XSD document (curated.xsd or learned.xsd per `_xsd_mode`, §11) when the Edit XSD/Edit AutoXSD
tab is active. Project-level state (`.bak`, `_current_project_path`, reparse) is untouched by XSD-tab
saves.

- **File ▸ Close** (Ctrl+W): if dirty, 3-way Save/Discard/Cancel (`_confirm_close()`, test-seam
  `confirm=`); clears editor+tree, resets state.
- **File ▸ Revert:** enabled only when `<current>.bak` exists; reloads from `.bak`, keeps real path,
  marks dirty.
- **Startup file:** `main()` opens a `.pgtp` passed as `argv[1]` (Windows "Edit with PGTP Editor"
  verb) when it is an existing file; else logs a warning.

**Undo/redo snapshot history** (`ui/history.py`, Qt-free): `SnapshotHistory(max_len=10)` with
`push/undo/redo/jump_to/entries/current_index`, coalescing identical consecutive text, truncating the
redo tail on a new push. Editor `textChanged` is debounced (~400 ms QTimer) and pushes only on change;
apply is guarded by a `_restoring` flag. **Ctrl+Z**/**Ctrl+Y** single-step; Edit ▸ Undo/Redo open a
non-modal newest-first `QListWidget` jump popup.

**Theme** (`ui/theme.py`): View ▸ "Light Theme" checkable toggles between **two explicit, symmetric,
platform-independent themes** — there is no third "restore the native/OS style+palette" state.
`light_palette()` and `dark_palette()` are pure functions (build and return a fresh `QPalette`,
mutating nothing) each setting a **complete** role set — every role the app surfaces, including
`Link`/`LinkVisited` (navy on light, light-cyan on dark, so About-box hyperlinks read on both) and an
explicit Disabled color group so greyed-out controls stay legible under Fusion. Light = white/near-white
backgrounds with dark text; dark = dark Window/Base with light text. `apply_theme(app, light: bool)` is
the only function that mutates the running QApplication: it **always** sets the Fusion style (Fusion
honors QPalette fully; many native styles largely ignore it) and applies `light_palette()` when `light`
is true, `dark_palette()` otherwise — and (BUG-010) sets the application stylesheet: **dark
additionally applies the QDarkStyleSheet dark QSS** (the `qdarkstyle` package,
`qdarkstyle.load_stylesheet(qt_api="pyside6")`, lazily loaded and cached in module-global
`_dark_qss_cache` via `_dark_stylesheet()` — qdarkstyle warns if loaded before a `QApplication`
exists), while **light always assigns the empty stylesheet** (`app.setStyleSheet("")`) so a
light↔dark round-trip never leaves stale dark QSS behind. Dark is therefore no longer palette-only:
Fusion + `dark_palette()` alone rendered checkable menu indicators outlined near-black on the dark
menu background (Fusion derives the indicator frame from darkened Window/Button roles); the
maintained stylesheet styles `QMenu::indicator` and every other widget consistently.
`dark_palette()` is still applied **beneath** the QSS because palette-reading custom widgets
(`XmlEditor.apply_theme_colors` keys off the palette's Base lightness) and any
non-stylesheet-covered rendering must agree with the stylesheet's dark look. Known side effect: an
app-level QSS wraps the active style in `QStyleSheetStyle`, so `app.style().objectName()` is empty
in dark mode (tests must not assert `"fusion"` there). `qdarkstyle>=3.2` is a runtime dependency
(pyproject + requirements.txt); the About box credits QDarkStyleSheet (Colin Duquesnoy, MIT).
Persisted as QSettings bool `"lightTheme"` in
`QSettings("MDS","PGTP Editor")`; `MainWindow._restore_theme` applies the persisted theme
**unconditionally at startup for both states** (no startup capture of a default palette/style key
exists). Toolbar icons are re-tinted (`_refresh_toolbar_icons`) on every theme change and on startup
restore. Tests assert palette roles rather than pixels.

**Window-state persistence:** `closeEvent` saves `saveGeometry()`/`saveState()` to QSettings; restored
on construction (default size on a fresh install). Tests use a temp QSettings scope.

**Toolbar:** a `QToolBar` driven by a stable action-id registry (`toolbar_registry.py`). Default set:
Open, Save, Undo, Redo, Find, Validate, Generate. **Customize Toolbar** dialog (two lists +
Add/Remove/Up/Down) writes an ordered id list, persisted in QSettings. The **Available list shows all
registry commands in registry order, always**; commands already on the toolbar are shown **disabled**
(not removed). Test seams `selected_ids()`/`set_ids()`; never `.exec()` in tests.

---

## 8. Raw XML editor

`ui/xml_editor.py::XmlEditor(QPlainTextEdit)` with syntax highlighting, folding, a multi-zone gutter,
auto-indent/auto-close, structural selection, tag navigation, bookmarks, and event-code styling.

**Lenient scanner** (`ui/xml_structure.py`, Qt-free, never raises):
`@dataclass TagSpan{name, open_start, open_end, close_end|None, depth, self_closing}`;
`scan(text)→list[TagSpan]`; primitives `find_enclosing_open_tag`, `nesting_depth_at`,
`enclosing_tag_span(text,pos)` / `enclosing_tag_span_from_spans(spans,pos)`, `parent_tag_span`,
`matching_tag_target`, `parent_tag_target`, `closing_tag_start` (public).

**Highlighting:** four categories (delimiters/names, attribute names, values, text); unclosed-quote
state propagated across blocks via Qt block state.

**Folding:** driven by `scan()` re-run on `textChanged`; one foldable region per multi-line
non-self-closing span; `QTextBlock.setVisible()`; `_fold_state: dict[int,bool]`; reset on `setPlainText`.
Folding only hides rendering — the character stream is intact, so copy/cut of a folded block yields the
**full** underlying text (a hard requirement; tested with nested folds).

**Gutter (`_EditorGutter`)** — three zones: left **bookmark strip**, line-number area, fold-glyph zone.
Click in the bookmark strip toggles that line's bookmark; click on a fold triangle toggles the fold.

**Shared gutter / bookmark / fold base (extracted, reused by the DDL editor — §18.1):** the gutter
(`_EditorGutter`), the bookmark set + `toggle_bookmark`/`bookmarked_lines`/`next_bookmark`/`prev_bookmark`
(all **block-number based**, hence generic), and the **fold-state** machinery (`_fold_state`,
`_toggle_fold`, `_is_line_hidden_by_other_collapsed_fold`) are **generic to any `QPlainTextEdit`** and
are extracted into a **shared base (base class or mixin)** used by **both** `XmlEditor` and the DDL
`CodeEditor` (§18.1). Only the **foldable-region provider is pluggable**: the base calls a
provider method that returns `(first_contained_block, last_contained_block)` for the region starting on a
given block. `XmlEditor` supplies the **XML-span** provider (`_foldable_region_starting_at` over `_spans`/
`TagSpan`); the DDL editor supplies a **DDL-object** provider driven by the `DdlObjectSpan` index (one
foldable region per object body, banner→`end_line`). This deliberately avoids a second, near-duplicate
gutter implementation — there is exactly **one** gutter/bookmark/fold implementation in the codebase.

**Auto-indent / auto-close:** Enter inherits leading whitespace, +2 spaces when just after an opening
tag's `>`. Typing `<`→`<>`, `"`/`'` after `=`→ paired quotes, `>` completing an opening tag inserts
`</name>`; type-through when the next char is the auto-inserted one.

**Extra-selections infrastructure** — a single `_refresh_extra_selections()` is the only caller of
`setExtraSelections`, concatenating (bottom→top): `_current_line_selections`, `_matching_tag_selections`,
`_error_line_selection`. Each feature sets its own named list then calls the refresher.

**Public navigation API** (consumed by Properties, captions, DB check, table references, diff):
`navigate_to_line(line)` (1-based; center + one-shot full-line highlight), `line_text(line)`,
`select_range_on_line(line, start, end)`, `highlight_error_line(line)` (one-shot). `highlight_error_line`
is reimplemented in terms of `navigate_to_line`.

**Structural selection** (Edit-menu actions, not editor-owned QShortcuts):
- **Select Enclosing Block** (Ctrl+Shift+B): selects `text[open_start:close_end]` (uniform; self-closing
  = open span). No-op when outside all elements.
- **Select Parent Block** (Ctrl+Shift+A): stateless, re-derived from `cursor.selectionStart()`; walks up
  one level per press; no-op at top level.
- Both build the selection **caret-at-start** (anchor at end, position at start) then
  `ensureCursorVisible()`. Selections are built purely from character offsets — never from visual
  hit-testing — so they work with folded content.

**Matching-tag highlight & navigation:** on `cursorPositionChanged`, both the opening and closing tag
of the enclosing element are highlighted (self-closing → none), using cached spans kept fresh on
`textChanged` (revision-guarded). **Ctrl+click** jumps between matching open/close tags; **Alt+click**
jumps to the parent element's open tag (both move caret + scroll, no selection; `event.accept()`
suppresses Qt's Alt-drag). Other modifier combos fall through.

**Right-click context menu:** `contextMenuEvent` first moves the caret to the actually-clicked
document position (`_prepare_context_menu_at(doc_pos)`) before building the menu, so
position-dependent entries (e.g. "Go To XSD", §11) reflect the clicked location rather than a
stale caret. **Selection right-click ▸ "Find"** prepends to the standard context menu when a selection
exists; emits `find_selected_text(str)` → MainWindow reveals Raw XML + prefills the Find bar.
**Line-wrap** toggle lives in the editor's right-click context menu (checkable), not the View menu.

**Bookmarks** (session-only, Raw-XML-only): `self._bookmarks: set[int]` (block numbers), reset wherever
`_fold_state` resets; `toggle_bookmark`, `bookmarked_lines`, `next_bookmark`/`prev_bookmark` (wrap),
`clear_bookmarks`, plus cursor-line wrappers. Rendered as an accent-colored rounded tag in the gutter
strip (theme-aware). **Bookmarks menu:** Toggle (Ctrl+F2), Next (F2), Previous (Shift+F2), Clear All.
Out-of-range block numbers are ignored defensively. No persistence, no list panel, no names.

**Event-handler code styling & editing:** event-body line ranges (`event_body_line_ranges(text)`) get a
distinct background + monospace and work read-only (Caption Mode). A gutter marker / "Edit code…"
context action opens `CodeEditorDialog` (below) with the body and `language_for_side(side)`; on save,
pure `replace_event_body(text, start_line, new_code)` swaps inner content preserving tags/indentation.

**Code editor** (`ui/code_editor.py`): `CodeEditor(QPlainTextEdit, language)` — monospace,
per-language `_CodeHighlighter` (JS / PHP / SQL keyword sets, strings, `//`+`#` line comments, `/* */`,
numbers), auto-close + selection-wrap for `()[]{}`/quotes, **Ctrl+Shift+B** bracket-select via pure
`enclosing_bracket_span(text,pos)`. The **`language="sql"`** mode (added for the DDL Explorer, §18.1)
uses `_SQL_KEYWORDS` (stored lowercase; matching is **case-insensitive** — `pg_get_functiondef` emits
uppercase, hand-written bodies vary), `--` line comments, single-quoted strings with `''` doubling
(double-quoted text is an identifier, left unstyled), and the shared `/* */` block comments.
`CodeEditor` also exposes `navigate_to_line(line)` (1-based; the same public navigation entry point
`XmlEditor` exposes, used by the BrowserPanel → EditorPanel jump, §18.1). In its **`language="sql"` DDL
mode** navigation is **top-aligned** (the target line lands at the top of the viewport, not centered) —
overriding the earlier `centerCursor()` — so a clicked DDL object's banner sits at the top with its body
below (§18.1); `XmlEditor.navigate_to_line` stays centered. The DDL `CodeEditor` also carries the shared
gutter/bookmark/fold base (line-number gutter, line bookmarks, code folding per DDL-object body) and a
**4-character tab stop** (§18.1). `CodeEditor` also exposes
`replace_current_selection(text)` (FindReplaceBar's Replace contract, mirroring `XmlEditor`), which
**no-ops on a read-only editor** — `QTextCursor` edits bypass `setReadOnly`, so this guard is what
actually protects read-only DDL buffers. `CodeEditorDialog(QDialog)` hosts it with
`saved(str)`/`cancelled` signals, **Ctrl+S** save / **Ctrl+W** cancel; never `.exec()` in tests.

**Tier-1 fallback:** on `PgtpParseError`, `_handle_parse_failure` keeps the `QMessageBox.critical`
dialog **and** re-reads the file, `setPlainText`, `highlight_error_line(exc.line)`, reveals + checks +
selects the Raw XML tab. Does not update `_current_project`/path or repopulate the tree.

---

## 9. Editor ↔ Tree sync & Reparse

- **Click-to-tree:** `model/line_index.py::node_at_line(project, line)` (document-order flat walk with
  depth-assigned end lines; Detail range starts at the outer `sourceline`; duplicate-table Details
  disambiguated by document position). `XmlEditor.line_clicked = Signal(int)` (1-based, from
  `mouseReleaseEvent`, left button only). MainWindow maps line → node → `project_tree.select_node(node)`
  → fires `currentItemChanged` → `PropertiesPanel.show_node`. `ProjectTreePanel` keeps an
  `id(node)→QTreeWidgetItem` map for O(1) selection. Wiring is one-directional (editor→tree→properties);
  no re-entrancy guard.
- **Double-click a tree node** → reveal Raw XML + `navigate_to_line(node.sourceline)`. Single click →
  Properties only.
- **Reparse** — **Tools ▸ "Reparse Raw XML into Tree"**: `load_project_from_text(editor_text)`; on
  success repopulate tree + set `_current_project` + clear Properties; on `PgtpParseError`,
  `QMessageBox.critical` + `highlight_error_line`, **preserving** the existing model/tree (does not
  re-read file or touch the path). Reparse is the explicit resync after manual edits, caption apply,
  code write-back, or create-from-table insertion.

---

## 10. Properties panel

`ui/properties_panel.py::PropertiesPanel(QWidget)` — **strictly read-only / navigate-only** (no cell is
editable, no write path). Header label + two-column (`Property`/`Value`) table + empty state.

`show_node(node, kind)` dispatches on `"page"|"detail"|"column"|"event"` (else empty state) to a
`RowSpec`-building pure function. `RowSpec{property_label, value, target_line, attr_name}`:

**Curated-label display** (§11): an attribute row whose value has a label in the curated XSD (explicit
`label="…"` or derived `sums` combination) renders the value as `value — label` (e.g.
`phpDriver: 1 — php-psql`). Display-only; the row's navigate-on-click behavior is unchanged.
- Page/Column: one row per `attrib` key, `target_line=node.sourceline`, `attr_name=key`.
- Detail: `caption` → outer `sourceline`; every other key → `inner_sourceline` (None → row click is a
  no-op).
- Event: exactly 3 rows — Handler (`tag_name`), Side (Client/Server), Functions (count via
  `_count_functions`, an approximate `function`-declaration regex).
- Column also appends a `— Representations —` divider then one row per `RepresentationVisibility`
  ("visible"/"hidden"/"— (not listed)", `target_line=rep.sourceline`).

Clicking a row → `navigate_to_line(target_line)`; if `attr_name` set, `_select_attribute_on_line`
selects the `attr="…"` span (silent no-op on miss; never crash).

---

## 11. Schema: curated XSD, learning & completion

Two XSD files with strictly separated roles, plus the learning engine's private JSON state. **The
hand-curated XSD is the official schema and the sole source feeding completion, hover hints, and the
Properties panel.** The vendored learning engine keeps running, but only as a discovery aid.

**Files** (`schema_learning/storage.py`, `QStandardPaths.AppDataLocation`, injectable `base_dir`):

| File | Path fn | Role |
|---|---|---|
| `curated.xsd` | `curated_xsd_path()` | **Official schema.** Hand-edited only (Edit XSD tab); never machine-written except the one-time first-run seed. Sole feed for completion / hover / Properties labels — **no learned fallback**. |
| `learned.xsd` | `learned_xsd_path()` | Generated discovery artifact. Regenerated by auto-learning on File ▸ Open; a reference for newly observed elements/attributes/values; never feeds completion; never touches `curated.xsd`. Openable read/write for analysis via **Schema ▸ Edit AutoXSD** in the same center-stage tab as Edit XSD (mode-aware, below). |
| bundled `resources/curated.xsd` | `storage.bundled_curated_xsd_text()` | **Curated v1.2** shipped with the app (`pgtp_editor/resources/curated.xsd`, in `[tool.setuptools.package-data]`; 109 elements / 252 attribute definitions, hand-commented, curated dialect). Version-marked by the XML comment `<!-- PGTP Editor curated schema v1.2 -->` and `storage.CURATED_BUNDLED_VERSION = "1.2"`. The **primary** seed source for the user's `curated.xsd` on first run. |
| `schema_model.json` | `schema_model_path()` | The learning engine's **private internal state** (counts, enum overflow). Feeds `learned.xsd` only. |

**One-time first-run seed:** on first run, if `curated.xsd` is absent, it is seeded by **copying the
bundled `resources/curated.xsd` (Curated v1.2)** — the real, hand-commented curated schema shipped with
the app (`storage.bundled_curated_xsd_text()`). Only when **no bundled resource is present** does the
app **fall back** to generating from the current learned model, emitting existing labels as `label="…"`
attributes (`xsd_gen.generate_curated_xsd`; `xsd_gen` gains a label-attribute emit mode). Seeding
happens **only when `curated.xsd` is absent** and **never overwrites an existing user file** — so
shipping a newer bundled version does **not** auto-upgrade a user who already has a `curated.xsd` (see
§29, open). After the seed the app never writes it (Import XSD replaces it wholesale, by explicit user
action).

**Dialect** — plain XSD plus three extensions of ours. Nothing external consumes the file; **Verify
checks our dialect, not W3C validity**:

- `label="…"` on `<xs:enumeration>` — the value's display meaning, e.g.
  `<xs:enumeration value="1" label="php-psql"/>`.
- `sums="true"` on `<xs:attribute>` — values are **additive**: the user labels only atomic values
  (1, 2, 4, 8, …); the app **derives** every combination's label (`3 = A+B` … `7 = A+B+C`,
  '+'-joined in ascending atomic order) for completion and hover. The Ctrl+Space value list offers
  **all** combinations (2^n − 1 rows) with derived labels — **capped at
  `settings_index.SUMS_MAX_ATOMS = 16` labeled atoms**: beyond 16, derivation is skipped entirely
  (2^n growth would freeze the UI) and only explicit enumeration labels are shown; Verify flags the
  attribute. An explicit enumeration row for a composite value overrides its derived label.
- `hint="…"` on `<xs:attribute>` — free-form attribute with a described meaning but no fixed values
  (no restriction block); the hint shows in hover; no value list in completion.

Curation of junk = **deleting enumeration rows**. There are no `kind`/`notes`/`enum_mode` concepts —
the file's structure is the entire vocabulary. An `xs:attribute` without enumerations completes by
name only.

**Engine model (private):** `Model.paths[chain]["attributes"][attr]` where `chain` = slash-joined tag
path from root (e.g. `PGTPProject/Pages/Page/Editor`, no indices). Attribute entries carry the
engine-owned `type`/`values`/`overflowed`/`attr_seen_count` only — the former labeler-owned fields
(`labels`/`kind`/`notes`/`enum_mode`) are gone. Enum overflow (`> ENUM_MAX_VALUES` →
`overflowed=True, values=None`): in `learned.xsd` an overflowed attribute emits the plain
non-enumerated XSD attribute form with no enumeration (test-pinned: `xsd_gen` only emits the
enumerated form when `not overflowed`). Overflow never applies to `curated.xsd` — it is hand-owned.

**Auto-learning** (unchanged trigger, new output): only **File ▸ Open** enriches (appended to the end
of the `open_project_file` success path, wrapped in try/except → one `[Schema] Could not update…`
audit line on failure). Reports via `_SCHEMA_REPORT_TEMPLATES`
(`new_element`/`new_attribute`/`new_value`/`enum_overflow`/`now_optional`); > 20 events collapse to
one summary line. Diff/Merge file pickers do **not** enrich. Enrichment updates `schema_model.json`
and regenerates **`learned.xsd` only**.

**Feeding pipeline:** `schema_learning/xsd_load.py` (Qt-free; streaming stdlib **expat** with a
`StartDoctypeDeclHandler` that raises `XsdLoadError` — **DTDs refused**, the same defensive posture as
defusedxml; the DTD-refusal message carries the offending line number, `line {n}: DTD declarations are
not allowed in the curated XSD`) parses `curated.xsd` via `load_curated(text) → CuratedSchema`:

```
CuratedSchema{
    model: Model,                                    # the existing in-memory Model shape
    attribute_lines: dict[(chain, attr) → line],     # 1-based source lines, power Go To XSD
    element_lines:   dict[chain → line],
}
```

Tag matching is **prefix-agnostic** (`xs:attribute` vs any prefix — only the local name matters, since
the user may use any namespace prefix in their curated file). Chains are built by a **type-reference
walk** from top-level `<element name=… type=…>` roots through named `complexType` child elements, with
a per-path **cycle guard** (`stack | {type_name}`): a recursive type stops, but a type reachable via
two different paths yields **both** chains. An **inline (unnamed) `complexType`** pushes a `None` frame
on the loader's type stack: attributes declared inside it land nowhere (they never leak into the
enclosing named type), while attributes declared **after** it closes correctly belong to the enclosing
named type again — Verify flags inline complexTypes as off-dialect. Per-attribute entries carry
`type` (base mapped to boolean/integer/decimal/string with **prefix-agnostic local-part fallback** —
`xsd:integer` still maps to integer, unknown bases default to string), `values`, `labels`,
`use`, and optional `sums`/`hint`; unknown structures are silently ignored — dialect complaints are
Verify's job, not the loader's. The loaded model feeds the `settings_index` query API — `known_attributes(model,
chain, present)`, `known_values(model, chain, attr)` (→ `[(value, label|None)]`), `enum_hint(model,
chain, attr)` (one-line hint, e.g. `editFormMode — 1 = modal · 2 = new page · 3 = inline`),
`unused_setting_attributes` — and therefore the completion/hover code keep their contracts. Loaded at
startup and on every Edit-XSD-tab save; handed to the editor via the existing
`set_schema_model(model)` (`None` disables). Semantics under the dialect: for a `sums` attribute,
`known_values` includes **all derived combinations**; `enum_hint` builds its hint from enumeration
labels (explicit and derived) or the `hint="…"` text; `unused_setting_attributes` = attributes the
curated schema knows for the chain that are absent from the tag — the old kind filter is gone: an
attribute is completion-worthy iff it exists in `curated.xsd`. The `sums` derivation is pure and
Qt-free in `settings_index.py` (composite label by decomposition into labeled atomic values; explicit
enumeration row wins; skipped when the labeled atoms exceed `SUMS_MAX_ATOMS = 16`).

**Disk-read guards:** every `curated.xsd` read catches **`OSError` and `UnicodeDecodeError`** (not just
parse errors). Startup / reload (`_load_curated_schema`, which also catches `XsdLoadError`) emits the
`[Schema] Curated XSD has XML errors: {error} — keeping last good schema` audit line and keeps the last
good in-memory schema live; opening the Edit XSD tab or running Verify against the saved file shows a
status-bar message (`Could not read curated.xsd: {error}`) and aborts.

**Mode-aware Edit XSD / Edit AutoXSD tab** (center stage): a **single** dedicated `CenterStage` tab —
one second `XmlEditor` instance with its own `FindReplaceBar` (full find/replace/Find All parity with
Raw XML) — that holds **either** the curated schema **or** the learned/auto schema. Which one is
tracked by `_xsd_mode ∈ {"curated","learned"}`:

- **Schema ▸ Edit XSD** loads `curated.xsd` into the tab in `"curated"` mode (title **"Edit XSD"**).
- **Schema ▸ Edit AutoXSD** loads `learned.xsd` (the auto-learning discovery artifact, regenerated on
  every File ▸ Open) into the **same** tab in `"learned"` mode (title **"Edit AutoXSD"**). Its purpose
  is **analysis** — comparing what auto-learning discovered against the hand-curated schema to decide
  what to hand-add to curated.

The tab title reflects the mode ("Edit XSD" vs "Edit AutoXSD") plus the existing dirty `" *"` suffix.
The tab owns its dirty state; Ctrl+S and Edit-menu Find/Replace route to the **active** tab (per-tab
document routing, §7). **Switching modes** (Edit XSD ↔ Edit AutoXSD) while the tab has unsaved edits
prompts the same three-way **Save/Discard/Cancel** used by `closeEvent`.

The tab is **closable** via a tab-bar ✕ (alongside Manual and DDL Explorer; Diff/Merge, Caption
Management, and Raw XML remain structural/non-closable, toggled only by their own entry points). Clicking it emits
`CenterStage.xsd_close_requested`, handled by `MainWindow._on_xsd_close_requested`, which reuses the
**same** `_confirm_close_xsd()` Save/Discard/Cancel prompt already used for mode-switching and
`closeEvent` — no separate confirmation dialog. On discard, on a clean tab, or after a successful
close-time save, `CenterStage.hide_edit_xsd()` hides the tab (mirroring `hide_manual()`) and the view
falls back to Raw XML; on cancel the tab stays open, visible, and dirty; a save failure during the
close-time save also leaves the tab open.

**Save / Verify / Export / Import act on the currently-open XSD** (the file the tab holds in its
current mode):

- **Save** (`"curated"`) → write `curated.xsd` (UTF-8, `newline=""`) → re-parse via `xsd_load` →
  refresh completion/hover/Properties immediately → auto-run Verify report-only on the saved text.
- **Save** (`"learned"`) → write `learned.xsd` (UTF-8, `newline=""`) → auto-run Verify report-only,
  but **does NOT feed completion/hover/Properties** (the learned schema never feeds completion — §11
  invariant preserved).
- **Verify / Export / Import** target whichever file the tab currently holds (curated or auto), not
  curated-only.

**Malformed XML on save** (curated mode): the text is still written (user text is never lost), the
audit line `[Schema] Curated XSD has XML errors: {error} — keeping last good schema` is emitted, and
the last good in-memory schema stays live.

**First-run seed audit line:** copying the bundled resource emits its seed audit line; the learned-model
**fallback** emits `[Schema] Bootstrapped curated.xsd from the learned schema (labels preserved)`
(failure → `[Schema] Could not bootstrap curated.xsd: {error}`).

**Go To XSD:** a **window-level `QAction`** (`Ctrl+L`, registered via `self.addAction(...)` on
MainWindow — deliberately **not** a Schema-menu item) plus a Raw XML editor right-click
**"Go To XSD"** context-menu entry. It **always forces curated mode** (it navigates to curated
attribute definitions; if the tab is in `"learned"` mode it switches back to `"curated"`, honoring the
unsaved-edits Save/Discard/Cancel prompt). It resolves the caret's attribute/element context (pure
`attribute_at_position` / `attribute_value_at_position` resolvers), activates the Edit XSD tab in
curated mode, and navigates to the `<xs:attribute name="…">` definition line via
`CuratedSchema.attribute_lines[(chain, attr)]`; if the attribute is absent, falls back to
`element_lines[chain]` (the element's type definition); otherwise a status-bar message. Lines come
from the **last successful parse** — navigation targets the saved file content, not unsaved tab edits.

**Schema menu — five items** (between Bookmarks and Database; see consolidated menu, §26):
- **Edit XSD** — open (or switch) the mode-aware tab in curated mode.
- **Edit AutoXSD** — open (or switch) the same tab in learned mode on `learned.xsd` (analysis).
- **Verify XSD** — dialect rules via `schema_learning/xsd_verify.py::verify_curated(text) →
  list[Issue{line, message, fatal}]` (streaming expat, prefix-agnostic). Checks as shipped:
  **duplicate enumeration values** (per `xs:attribute`), **`label` off-enumeration** (`label="…"` on
  any non-enumeration tag), **`sums` off-attribute** (`sums` on any non-attribute tag), **`hint`
  off-attribute** (`hint` on any non-attribute tag), **unknown base type** (lenient: a base is accepted
  with *any* prefix whose local part is one of boolean/integer/decimal/string), **unresolved type
  references** (element `type=` naming no `complexType`), **duplicate type names**, **inline (unnamed)
  `complexType`** ("not part of the dialect"), **sums attribute with no labeled atomic values**,
  **sums attribute exceeding the derivation cap** ("too many values for derivation
  ({n} > 16)" when its enumeration count exceeds `SUMS_MAX_ATOMS`; both sums rules report at the
  attribute's start line), and **duplicate attribute name within one `complexType`** (a second
  `xs:attribute name="…"` inside the same `complexType` silently overwrote the first before this check
  existed; the seen-names set resets on every `complexType` start since complexTypes never nest in this
  dialect; reports at the line of the second/overwriting occurrence,
  `"duplicate attribute name '{name}' in this complexType"`). Malformed XML or a DTD declaration → a **single fatal Issue**
  (`XML error: …`, at the offending line). Issues are **sorted by line**. Menu action verifies the
  **active XSD** (curated or learned, per `_xsd_mode`): the XSD tab's live text when it has unsaved
  edits, else the saved file for the current mode; also auto-runs report-only on every Edit-XSD-tab
  save and on import. Audit output: one clickable line per issue,
  `[Schema] VERIFY line {n}: {message}` (line on `UserRole`, target `"xsd"` on `UserRole+1` — the same
  item-data click convention Find All uses; click activates the Edit XSD tab at that line), or
  `[Schema] VERIFY: no issues found.` when clean.
- **Export XSD** — Save-As copy of the **active XSD** (`curated.xsd` in curated mode, `learned.xsd` in
  learned mode; `shutil.copyfile`); refused with a status-bar message while the XSD tab has unsaved
  edits ("save it first").
- **Import XSD** — Open dialog → **verify the incoming file first** (hard refuse malformed XML with an
  "Import Refused" dialog; non-fatal dialect warnings prompt a `QMessageBox.question` Yes/No
  "Import With Warnings" confirm) → back up the **active file** (`curated.xsd.bak` / `learned.xsd.bak`)
  → replace → re-parse → refresh (curated-mode import re-feeds completion; learned-mode import does
  not). Read failures catch **`OSError` and `UnicodeDecodeError`** → "Import Failed"
  critical dialog; a write failure (`OSError`) → "Import Failed" as well. Success emits
  `[Schema] Imported curated XSD from {name}`, with the suffix
  `" (unsaved XSD tab edits were replaced)"` appended when the XSD tab was dirty, followed by the
  verify report. Team sharing = plain file exchange via Export/Import.

**Editor integration** (mechanics unchanged; source now exclusively `curated.xsd`):
- **Hover** over an attribute name/value in an opening tag shows a `QToolTip` with `enum_hint(...)`,
  including derived `sums` labels and `hint="…"` text. Pure resolver `attribute_at_position(text,pos)`.
- **Right-click ▸ Add attribute ▸** submenu from `unused_setting_attributes`; inserts ` name=""` with
  caret between quotes via pure `insert_attribute(text, insert_pos, name)`.
- **Ctrl+Space autocomplete:** `_CompletionPopup(QListWidget)` (frameless, non-modal). Attribute stage
  uses `known_attributes`; on choose, inserts ` name=""` and, if `known_values` non-empty, chains a
  value popup (displays `value` or `value = label`, inserts bare value; derived `sums` labels shown
  like explicit ones; a `hint` attribute offers no value list). ↑/↓ navigate, Enter/Tab/click choose,
  Esc/focus-out cancel, printable chars prefix-filter. Guarded by `not isReadOnly()` + model present +
  `enclosing_open_tag(...)` resolving.

---

## 12. Diff / Merge

Three dependency-ordered sub-projects. Inputs are always **Source** and **Target**; differences flow
Source→Target and **only Target is ever mutated/written**. Ethos: never a silent wrong result.

**Engine** (`diff/differ.py` + `diff/records.py`, Qt-free, operates only on loaded `ProjectModel`s —
no I/O, no mutation): `diff_project(source, target)→list[Difference]`; recursive
`compare_block(source_node, target_node, path, node_kind, ambiguous=False)`.
- Page matching: global by `fileName`. Detail matching: `(tableName, caption)` **scoped to the parent
  pair**. Column: by `fieldName`. Event: by base handler name via `classify_event_side` normalization.
- `Difference{kind: added|removed|changed, path: list[str], node_kind: page|detail|column|event|
  format|lookup|view_properties|edit_properties, attribute: str|None, old_value(Target), new_value(Source),
  ambiguous: bool}`. Attribute `changed` → `attribute` set; whole-subtree add/remove and event-text
  change → `attribute=None`. Event text change carries raw texts in old/new.
- Duplicate siblings sharing `(tableName, caption)` under one parent → paired **positionally**, every
  resulting `Difference` marked `ambiguous=True`.
- **No `moved` detection** (a relocation = one removed + one added).
- Column sub-elements (`format`/`lookup`/`view_properties`/`edit_properties`) are diffed via
  `_compare_child_element` (one `changed` per differing attrib key).

**resolve.py** — `resolve_path(project, path) → PageNode | DetailNode | ResolutionError`
(`ResolutionError{segment_index, message}`, never bare `None`). Path segments: `path[0]`=Page
`fileName`; `path[1:]`=`"tableName/caption"` Detail segments. Mirrors the differ's matching; duplicate
siblings → first match.

**Viewer** (`diff_merge_panel.py::DiffMergePanel`, replaces the placeholder at
`CenterStage.diff_merge_tab_index`) — horizontal splitter: a change-list `QTreeWidget` (rebuilt each
`show_differences`, shared prefixes reused; leaves carry the `Difference` and are the only checkable
items, **default unchecked = Skip**; ambiguous leaves prefixed `"⚠ "`) + a detail view (3 mutually
exclusive: Old/New rows for attribute change; read-only attrib table for whole-subtree add/remove;
stdlib `difflib.unified_diff` in a read-only `QPlainTextEdit` for event-text change). Next/Prev
Difference walk the flattened leaves (no wraparound).

**Three entry points** all converge on `show_differences`: Tools ▸ "Compare/Merge Two Files…" (Source
defaults to current project, Target prompted); Project-tree Page ▸ "Compare This Page With…";
Project-tree Detail ▸ "Compare This Detail With…" (uses `resolve_path`).

**Write-back** (`diff/apply.py::apply_differences(target, differences)→ApplyResult{applied, failed}`) —
mutates the retained `lxml` tree in place: `changed`→`element.set/del`; event `changed`→`element.text`;
`added`→`copy.deepcopy` the Source element and insert (append into the appropriate container, creating
`<Details>`/`<EventHandlers>` as needed); `removed`→`element.getparent().remove(element)`. Target
element located via `resolve_path` (+ one flat scan for column/event granularity).
- **Ambiguity gate** (in MainWindow, not apply.py): if **any** checked difference is ambiguous, refuse
  the **entire** batch with a `QMessageBox.critical` naming each; recovery = uncheck & re-run.
- **All-or-nothing:** apply to a `copy.deepcopy` of the tree; only if every checked non-ambiguous
  difference applies do we write. `.bak` via `shutil.copy2` immediately before writing; serialize with
  `etree.tostring(tree, xml_declaration=False, encoding="UTF-8", pretty_print=False)`, `"wb"`.
- After a successful Apply, Target is **auto-reloaded** (`open_project_file`); the change-list is **not**
  auto-cleared or auto-re-diffed (preserves review boundary). `.bak` is the only recovery (no in-app
  revert-merge).

---

## 13. Captions

A single Excel-style, filterable grid to review/edit every user-facing caption-like string.

**Pure core** (`ui/caption_scan.py`, Qt-free): caption-like attributes scanned =
`caption, shortCaption, headerHint, insertFormCaption, groupName`.
`CaptionEntry{line, element_tag, anchor, attribute, value, breadcrumb}` — `anchor` = `fieldName` else
`fileName` else `tableName` else tag; `breadcrumb` = ancestor Page/Detail captions joined ` → ` + own
label. `scan_captions(text)` (lxml; `[]` if not well-formed). `apply_caption_edits(text, edits)` operates
per source line with a **boundary-safe** regex (negative lookbehind so `caption` never matches inside
`shortCaption`/`insertFormCaption`), XML-attribute-escaping the new value; unmatched lines left
unchanged. Helpers `apply_find_replace(value, find, repl, mode, case)` and
`transform_caption(text, kind)` (Title Case / UPPERCASE / lowercase / Sentence case / Trim / Humanize).

**Grid** (`caption_management_panel.py::CaptionManagementPanel`) — columns
`Changed · Line · Breadcrumb · Element · Anchor · Attribute · Value · New Value`. **Value is read-only;
New Value is the only editable column.** A row is *changed* iff New Value is non-empty; the literal
sentinel `<NULL>` means set the caption to empty string. `changed_edits()` resolves that. Changed rows
tinted `#26343a`; inconsistency (same `(anchor, attribute)`, differing values) tinted `#3a2f1d`;
changed wins. **Filtering:** Excel-style per-column **header filter** popups (non-modal, checkable
distinct values) via proxy `set_value_filter(column, allowed|None)`, AND-ed with a regex filter
(`set_regex_filter(pattern, mode, case)`). (The earlier inline per-column QLineEdit filter row was
removed.) Right-click: Insert NULL, Go to line in XML (Ctrl+G, injected `on_go_to_line`), **Transform ▸**,
**Unify** (set all inconsistent siblings to this value). Ctrl+C copies cells tab/newline-separated;
Ctrl+V fills New Value (Excel vertical fill). Decoupled from MainWindow via injected callbacks.

**Caption find/replace modal** (`caption_find_replace_dialog.py::CaptionFindReplaceDialog`) — Tools ▸
"Caption Filter…" / Ctrl+R. Find/Replace fields, Search Mode (Normal/Extended/Regex), Match case, Scope
(In selection[default] / Global), buttons Filter / Replace All / Close (no Find Next). As a filter it
sets the proxy regex filter; as replace it writes results into each in-scope row's **New Value**
(non-destructive). Never `.exec()` in tests.

**Caption Mode** (`center_stage.py` + `main_window.py`): Tools ▸ "Manage Captions…". On enter, the Raw
XML editor **stays visible but read-only** (a persistent status-bar label reads "Caption Mode (XML
read-only)"; edit attempts flash a hint via a new `read_only_edit_attempted` signal). Reveal the Caption
Management tab, `scan_captions` the snapshot, `load_entries`. Apply computes
`apply_caption_edits(snapshot, changed_edits)` into the Raw XML buffer **in memory only** (no disk, no
`.bak`, no auto-reparse); the snapshot updates so line numbers stay valid. Close restores editing mode.

---

## 14. Columns

Two additive extensions to `ColumnNode`, both built inside `_parse_columns`.

**Sub-element model** (`nodes.py`/`parser.py`, no UI): `ChildElement{attrib, sourceline, element}`;
`ColumnNode` gains `format`, `lookup`, `view_properties`, `edit_properties` (all `ChildElement|None`).
`Format` is located at `ViewProperties/Format` (grandchild); the other three are direct children.
Real attribute names (grounding): `Format`(type, decimalSeparator, thousandSeparator, numberAfterDecimal);
`Lookup`(tableName, linkFieldName, displayFieldName, lookupFilter, useLookupOrdering, lookupOrdering,
allowAddNewItemsOnTheFly?); `ViewProperties`(type, maxLength?); `EditProperties`(type ∈
textBox/autocomplete/dynamicCombobox/textArea, maxLength, placeholder, …). Differ threads these as four
new `node_kind`s; `apply.py` write-back for these is **scoped out** (documented limitation; a clean
`ApplyFailure` is produced for added/changed).

**Representation visibility** (surfaced read-only in Properties): 10 fixed representations
(`List, View, Edit, Insert, QuickFilter, FilterBuilder, Print, Export, Compare, MultiEdit`) each
appearing once per `<Columns>` block. `RepresentationVisibility{name, visible: bool|None, sourceline}`
(`visible="false"`→hidden, absent entry→visible, representation-present-but-field-absent→None).
`ColumnNode.representations: list[...]` built by `_build_representation_index(container_el)` in
`REPRESENTATION_NAMES` order. No editing, no diff/merge/write-back.

---

## 15. Search, Find All & Table References

**Search core** (`ui/search.py`, Qt-free) — **plain case-insensitive substring only** (no
regex/whole-word/case toggles, no options UI): `find_next(text, term, from_pos, *, wrap=True)`,
`iter_matches(text, term)` (lazy generator), `find_all_matches = list(iter_matches(...))`.
`Match{start, line(1-based), preview}`. Non-overlapping scan (advance by `len(term)`).

**Find/Replace bar** (`ui/find_replace_bar.py::FindReplaceBar(QWidget)`) — modeless, shown **below** the
editor inside the Raw XML tab (`center_stage.raw_xml_tab` container). Constructed with the editor +
injected callbacks (`on_find_all`, `on_stop_find_all`, `on_status`). Find/Replace fields + Find Next /
Find All(↔Stop) / Replace / Replace All. `show_find`/`show_replace` prefill from selection; Esc hides &
returns focus. Replace-all rewrites all matches in one undo block (right-to-left). The editor gains
`replace_current_selection(text)`.

**Edit menu** (real actions): Find… (Ctrl+F), Find Next (F3), Find All (Ctrl+Shift+F), Replace…
(Ctrl+R), Replace All (Ctrl+Alt+Return). Each handler routes to the **active** center-stage editing
tab's `FindReplaceBar` (Raw XML, or Edit XSD when that tab is active — §7 per-tab routing; when
neither is active, Raw XML is revealed) and delegates to the same `FindReplaceBar` method the button
uses. The Edit XSD tab hosts its own `FindReplaceBar` instance with full Find All parity. (The old
"Find & Replace…" Ctrl+H stub was removed.)

**Find All → Audit panel, streaming:** `_populate_find_all_results(term)` starts a chunked,
`QTimer`-driven run (batch **200** matches/tick, snapshot text once, cancel any in-flight run). Items
`"[Find] line N: preview"` (line on `UserRole`) + a trailing `"[Find] N match(es) for \"term\""` summary.
`_clear_find_results` removes only `[Find]` items. Status bar: `Finding "term"… found N` / `Found N
item(s)` / `Find All stopped — found N item(s)` / `N replacement(s) for "term"`. The Find All button
toggles to **Stop** while running. Single-threaded chunking only (no threads, no progress bar, no caps).

**Table References tab** (`analysis/reused_tables.py` + `ui/table_references_panel.py`) — replaces the
old "Find Reused Tables" modal:
- `collect_table_usages(project)→list[TableUsage]`; `TableUsage.references: list[TableReference]`;
  `TableReference{breadcrumb, node, kind(page|detail|column), line|None, ref_type(table|lookup|lookup with
  insert)}`. Line = page/detail `sourceline`, lookup = `<Lookup>` sourceline (`column.lookup.sourceline`,
  fallback `column.sourceline`). `(lookup with insert)` when `<Lookup>` has an `<OnTheFlyInsertPage>`
  child. Grouped by table name, sorted, document order within a table.
- `TableReferencesPanel(QTreeWidget)`: top-level `"<table>  (<count>)"`, children = reference
  breadcrumbs; `selection_changed(node, kind)` → Properties (a lookup reference targets its owning
  `ColumnNode`); `jump_requested(line)` → `_tree_jump_to_line` (reveal Raw XML + `navigate_to_line`).
- Added to `left_tabs` as a hidden tab "Table references". **View menu** checkable "Find table
  reference": on → reveal/focus + repopulate; off → hide; refreshed on reparse when visible. The old
  Tools ▸ "Find Reused Tables…" action, its handler, and `reused_tables_window.py` are removed/deleted.

---

## 16. Validation

Two tiers of §6.7.

**Tier 1 — well-formedness (blocking):** enforced where raw text bypasses the model (file open, Raw XML
panel, diff/merge manual-edit escape hatch). lxml reparse attempted; on failure the Tier-1 fallback
(§8) shows the dialog + opens the raw file with the error line highlighted.

**Tier 2 — structural sanity (on-demand, low false positive)** — `validation/tier2.py`:
`validate_project(project)→list[ValidationIssue{severity, message, line}]` over `tree.getroot()` in
document order. Checks: (1) **duplicate top-level `Page@fileName` = ERROR** (direct `<Pages>` children
only, nested Detail pages excluded); (2) missing required attrs = WARNING (`Page` missing
fileName/tableName; `ColumnPresentation` missing fieldName); (3) unexpected container child = WARNING
(`<Pages>`→`<Page>`, `<Details>`→`<Detail>`, `<ColumnPresentations>`→`<ColumnPresentation>`). Wired to
Tools ▸ Validate Project → Audit panel with `"[Validate] SEVERITY line N: message"` items (line on
`UserRole`, click navigates). Out of scope: deep referential integrity, full whitelist enforcement.

---

## 17. Database

Validate a `.pgtp` against a live PostgreSQL DB bidirectionally, reconcile by renaming, and synthesize
new elements from a DB table. All logic Qt-free in `db/`.

**Transport:** `psycopg` v3 (`psycopg[binary]`), no external `psql`. Connection seeded from XML
`<ConnectionOptions>` (design-time, **not** `<ScriptConnectionOptions>`) — host/port/database/`login`→user;
the **password is never read from XML** (obfuscated there) — entered by the user and persisted
**plaintext** to injectable `self._settings` (caveat shown in the dialog). Introspection uses
`pg_catalog` (not `information_schema`): `relkind IN (r,p,v,m)`, columns via `format_type` + `attnotnull`
+ `pg_get_expr`, PK/FK via `pg_constraint`.

- `db/config.py`: `ConnectionParams(host, port, database, user, password)` with `redacted()`
  (password→`***`); `connection_from_tree` (password `""`); `load_connection`/`save_connection`;
  `seed_params`.
- `db/introspect.py` (psycopg lazily imported): `ColumnInfo(name, data_type, is_pk, is_fk, is_nullable,
  default, fk_target)`; `TableInfo(name, kind(table|view|matview), columns)`; `DatabaseSchema.tables`
  keyed schema-qualified (`pr.equipment`). `run_queries(params, sql)` is the **only** connection-opening
  fn; `fetch_schema`/`test_connection` take `runner=` for fakes. `test_connection` runs `SELECT 1`,
  returns `(ok, message)`, never raises.
- `db/compare.py` (pure): `check_xml_against_db` (XML→DB) and `check_db_against_xml` (DB→XML) →
  `TableCheck{name, ok, kind, invocations, columns:[ColumnCheck]}`; reuses `analysis/reused_tables.py`
  traversal. `ColumnCheck{name, ok, info: ColumnInfo|None = None, is_calculated: bool = False}` —
  `is_calculated` (last, defaulted, so `check_db_against_xml`'s constructions need no change) carries
  the XML-side `isCalculated="true"` flag via `ColumnNode.is_calculated` (§6). `xml_table_columns`
  returns `dict[str, dict[str, bool]]` (`tableName` → `fieldName` → is_calculated), **OR-unioned**
  across pages/details bound to the same table (calculated anywhere it appears → calculated); name
  membership (`in`) still works for callers needing only the field-name set. `ok` deliberately stays
  "does a matching DB column literally exist" (informational — a calculated column can shadow a real
  DB column, yielding `ok=True` **and** `is_calculated=True`); consumers treat `is_calculated` as
  **overriding** `ok` for mismatch display/counting. `check_db_against_xml` is unchanged
  (membership-only use of `xml_table_columns`).
- `db/rename.py` (pure): `rename_field(text, old, new)` / `rename_table(...)` = literal global
  attribute replace.

**UI:** **Database** menu (Connection Setup…, Check: XML→Database, Check: Database→XML, and — after a
separator — the checkable **DDL Explorer** toggle, §18.1).
`ConnectionSetupDialog` (host/port/database/user, password EchoMode.Password, Test + status, plaintext
caveat; API `set_params`/`params()`/`test()`). `DbCheckPanel` (header: direction + `user@host:port/db` +
mismatch count; "Show only mismatches" toggle; `QTreeWidget` with `(T)`/`(V)`/`(M)` prefixes, `(×N)`
invocation counts, datatypes, PK underline, `(fk)`). **Three-way column glyph/color convention:**
calculated (`ColumnCheck.is_calculated`) → orange `~` (`_CALC_COLOR = QColor("#d08a1a")`); else
`ok` → green ✓ (`_OK_COLOR`); else red ✗ (`_BAD_COLOR`). Calculated columns are **never counted as
mismatches** — excluded from the header mismatch count and hidden under "Show only mismatches" —
and rename is gated off for them (both the contextual-rename path and the context menu skip
calculated columns, alongside `ok` ones). Tree items carry a uniform 4-tuple UserRole payload
`(kind, name, ok, is_calculated)` on both table and column items (tables always `False`). Signals
`rename_requested(kind, old)` (XML→DB not-found, non-calculated nodes), `jump_requested(kind, name)`
(double-click → Raw XML), and `create_requested(kind, name)` (DB→XML table nodes). Added to
`left_tabs` as a hidden tab.

**Reparse refreshes an open DB Check** against the **cached schema** (`_last_db_schema` /
`_last_db_check_direction` / `_last_db_summary`), no live re-query — via `_populate_db_check(...)` and
`_refresh_db_check_if_open()` (guarded on tab visibility + valid buffer).

**Create Page/Detail/Lookup from a DB table** (`generation/type_map.py` + `generation/from_table.py`,
pure): right-click a table/view node (DB→XML) → **create page** (insert before `</Pages>`, jump +
select), **create detail** (copy `<Detail>` to clipboard), **create lookup** (copy `<Lookup/>` to
clipboard). Aims at full PHP-Generator new-table parity via `type_map` (single source of parity truth,
keyed on normalized pg type: numeric/char/text/boolean/date/timestamp families → presentation +
`Format`/`EditProperties`/filterOps rules) + `PAGE_DEFAULTS` (recordsPerPage=20, editAbilityMode=3,
export/print flags, contentEncoding=UTF-8, …). Page emits `<ColumnPresentations>` + all 10 `<Columns>`
representations (PK cols hidden in Edit/Insert/Compare/MultiEdit). FK inference: exactly one child FK →
use it, else empty placeholders. **The vendor misspelling `foreginColumnName` is reproduced verbatim.**
`ColumnInfo.fk_target` = `"schema.table.column"` via `pg_constraint`. Parity is calibrated against a
golden "freshly-added table" oracle; defaults are corpus-derived and **not yet fully vendor-confirmed**.

---

## 18. DDL versioning (standalone Postgres mode)

> **Status: §18.1 read-only browsing is fully implemented, wired, and tested — with the single
> exception of the XML cross-referencing angle; §18.2/§18.3 remain target design, not yet
> implemented.** Shipped exactly as specified below: `RoutineInfo`/`TriggerInfo`/
> `DatabaseSchema.routines`/`.triggers` (`db/introspect.py`), `db/ddl_buffer.py`/`DdlObjectSpan`,
> `ui/ddl_buffer_panel.py::BrowserPanel`, `ui/ddl_editor_panel.py::EditorPanel` (the CenterStage
> "DDL Explorer" tab), the `language="sql"` highlighter mode in `ui/code_editor.py` (§8), the
> Database-menu "DDL Explorer" checkable toggle, and the full main-window wiring (hidden left-dock
> "DDL Objects" tab, `navigate_requested` navigation, async fetch).
>
> **A settled batch of §18.1 enhancements (2026-08-01) is specified below but not yet in the code**
> (design settled ahead of implementation): (a) editor affordances on the DDL `EditorPanel` — a
> line-number gutter, line bookmarks, and code folding via a **shared base extracted from `XmlEditor`**
> with a pluggable foldable-region provider (§8); (b) a **4-character** editor tab stop; (c) the revised
> BrowserPanel tree presentation — fully-qualified `schema.name`, the three-way `[F]`/`[P]`/`[T]` marker,
> per-argument `name (type)` children (requiring `RoutineInfo.args`), and composite trigger leaves with
> bracketed timing/event indicators; and (d) **top-aligned** DDL navigation. See the Supersession Ledger
> (§28) for each override.
>
> Still not built: `db/routine_refs.py` (XML cross-referencing), and `db/schema_diff.py`/
> `db/schema_snapshot.py`/`db/migration_gen.py` (§18.3); those parts of this section remain target
> design, settled before implementation starts.

**Strategic framing.** This is **not** a feature bolted onto `.pgtp` editing — it is a standalone
Postgres DDL-versioning mode, independent of phpgen/`.pgtp` entirely, usable with zero `.pgtp` files
involved (§1). The project owner explicitly considered and **rejected** the `re_phpgen` precedent
(§20/§20.4 — the one place in this codebase where genuinely independent tooling was split into a
**separate repo**, invoked as a subprocess) for this workflow: DDL versioning stays **in the same app,
as an independent mode**, directly sharing the app's existing DB connection (§17), code editor
(`ui/code_editor.py::CodeEditor`, §8), and diff infrastructure (§12) — deliberately no
subprocess/repo split. Consequently this section was pulled out of §17 as its own top-level section
rather than left as a `§17.x` subsection: it broadens the app's stated purpose (§1), not just its
Database menu. Generic DB introspection primitives it depends on (`RoutineInfo`/`TriggerInfo`/
`DatabaseSchema.routines`/`.triggers`, §17) stay in §17, reused by both the pre-existing DB-check
features and this workflow.

Three parts, in dependency order: **§18.1** browses live routines/triggers in one synthesized buffer
(unchanged in shape from the original DDL Explorer design); **§18.2** introduces the "project" concept,
checkout-to-edit, and the `*`/`!` state markers; **§18.3** is the deploy workflow, which reuses §18.1's
browsing UI and the diff/migration engine originally specified as a schema-compare-only tool.

**Truth model (first-class design principle, not an implementation footnote): the database is the
sole source of truth; git is a history/audit log only, never authoritative for "current state."**
Consequence, stated explicitly: on every project load (§18.2), the tool re-verifies every local `ddl/`
file against the live DB by fresh introspection — it never trusts git history, or any cached/prior-
session state, as representing current DB state. State markers (§18.2) are recomputed fresh on every
load, not persisted/cached across sessions.

### 18.1 Routines & triggers browsing (DDL Explorer)

Extends database introspection to routines and triggers, synthesizes them into one shared browsable
buffer (the same architecture the app already trusts for its main document), and cross-references them
into the XML. This subsection is the browsing substrate that §18.2's checkout-to-edit and §18.3's deploy
workflow both build on directly — it is not a separate, self-contained feature.

**Introspection (lives in §17, reused here) — implemented:**

- `db/introspect.py` has: `RoutineInfo{schema, name, arg_types: list[str], **args: list[tuple[str, str]]
  (input argument name+type pairs, in declared order)**, return_type, language, source,
  kind("function"|"procedure")}` sourced from `pg_proc` joined `pg_language`, with source text
  via `pg_get_functiondef(oid)`. `arg_types` (types only) is **retained** — it still feeds
  `build_ddl_text`'s banner comment (`-- FUNCTION schema.name(argtypes) --`); the new `args` field adds
  the **argument names** the BrowserPanel tree needs (see tree presentation below). The introspection
  query sources input-argument name+type pairs in declared order (implementation chooses the exact
  `pg_catalog` mechanism — e.g. `pg_get_function_arguments`, or `proargnames`/`proargtypes`/`proargmodes`
  correlated positionally; spec stays at the design level: name+type pairs, declared order, **IN/INOUT
  input arguments only**). A routine with zero input arguments has `args == []`. `TriggerInfo{schema,
  table, name, timing, events: list[str],
  function_name, definition}` sourced from `pg_trigger` + `pg_get_triggerdef(oid)` (trigger
  timing/events decoded from the raw `pg_trigger.tgtype` bitmask by `_decode_trigger_type`, in Python
  rather than SQL, so the mapping is unit-testable without a live database). The `DatabaseSchema`
  dataclass (`db/introspect.py`) has `.routines` and `.triggers` fields alongside `.tables`
  (backward-compatible, all default to empty).
- Fetched by `fetch_routines_and_triggers(params, runner=run_queries) -> DatabaseSchema`
  (`ROUTINE_TRIGGER_SQL` = `[_ROUTINES_SQL, _TRIGGERS_SQL]`) — a **separate fetch path from
  `fetch_schema`**, not merged into it: an implementation choice to avoid touching `fetch_schema`'s
  existing 3-query contract and its tests, since the DB Check features never need routine/trigger data.
  The `DatabaseSchema` it returns always has an empty `.tables`; only `.routines`/`.triggers` are
  populated.

**One synthesized buffer, not per-object viewers — reuses the Raw XML editor's proven shape
(`TagSpan`/§8 + `node_at_line`/§9: one shared text buffer, a structural span index over it, and a tree
that navigates into it via line numbers) instead of opening a bespoke read-only viewer per routine or
trigger:**

- **Implemented:** pure module `db/ddl_buffer.py`: `build_ddl_text(schema: DatabaseSchema) → tuple[str,
  list[DdlObjectSpan]]`. Synthesizes **one** text buffer concatenating every routine and trigger
  definition, in deterministic order (schema, then kind — functions/procedures before triggers — then
  name), each preceded by a banner comment anchoring its span (e.g.
  `-- FUNCTION public.foo(integer) --`). `DdlObjectSpan{kind: "function"|"procedure"|"trigger", schema,
  name, table: str|None (triggers only — the table it fires on), start_line, end_line}` plays the same
  role for this buffer that `TagSpan` (§8, `ui/xml_structure.py`) plays for the Raw XML buffer and that
  `node_at_line` (§9, `model/line_index.py`) plays for click-to-tree sync.
- **Implemented:** CenterStage tab `ui/ddl_editor_panel.py::EditorPanel(QWidget)` hosts the
  synthesized buffer in the **existing** `ui/code_editor.py::CodeEditor` widget under its
  **`language="sql"` mode** — the SQL/plpgsql `_CodeHighlighter` keyword set (`_SQL_KEYWORDS`,
  case-insensitive matching, `--` line comments, `''`-doubled single-quote strings, `/* */` block
  comments) added alongside the existing JS/PHP ones in that same file (§8). Has its own
  `FindReplaceBar` instance, following the same per-tab document-routing precedent as the Edit XSD tab
  (§7/§15) and the planned Custom PHP tabs (§21). The tab sits in `CenterStage` between Edit XSD and
  Manual (`ddl_tab_index`, hidden by default), and is **closable** via a tab-bar ✕ that hides it
  directly (`hide_ddl_explorer()`) — read-only, so unlike Edit XSD there is no dirty prompt to route
  through. `CenterStage` exposes `show_ddl_explorer()`/`hide_ddl_explorer()` and a
  `ddl_explorer_visibility_changed = Signal(bool)`. API: `EditorPanel.set_ddl_text(text)` (a fresh
  `build_ddl_text` result) and `EditorPanel.navigate_to_line(line)` (delegates to
  `CodeEditor.navigate_to_line`, §8, then focuses the editor). This tab is **read-only, DB-sourced,
  live/synthesized** (`editor.setReadOnly(True)`; `CodeEditor.replace_current_selection` no-ops on
  read-only editors, the guard that actually protects the buffer since `QTextCursor` edits bypass
  `setReadOnly`) — the checked-out, editable form lives in `ddl/*.sql` files (§18.2), edited in a
  separate tab type.
- **Editor affordances (parity with the Raw XML editor's `XmlEditor`, via a shared base — §8):** the
  DDL `CodeEditor` gains the **same three affordances `XmlEditor` has**: (i) a **line-number gutter**,
  (ii) **line bookmarks**, and (iii) **code folding**. These are provided by a **shared
  gutter/bookmark/fold base extracted from `XmlEditor`** (see §8 for the extraction), so there is **one**
  gutter/bookmark/fold implementation used by both editors — never a second parallel gutter. The base
  supplies the generic, block-number-based gutter + bookmark set + fold-state machinery; the
  **foldable-region provider is pluggable**. For the DDL buffer the foldable regions are **one per DDL
  object body** — the object's `DdlObjectSpan` banner line (`start_line`) through its `end_line` — which
  `EditorPanel` already holds from the `build_ddl_text` span list (folding a DDL object collapses its
  source under the banner). `XmlEditor` keeps its **XML-span** fold provider (`_foldable_region_starting_at`
  over `_spans`/`TagSpan`, §8).
- **Tab stop = 4 characters.** The DDL editor sets its tab-stop distance to **4 character widths**
  (`setTabStopDistance(4 × mono-char-width)`), overriding Qt's monospace default (~8–11 chars) so
  `pg_get_functiondef`'s tab-indented bodies read at a sane width.
- **Top-aligned navigation.** `EditorPanel.navigate_to_line(line)` scrolls so the target line lands at
  the **top** of the editor viewport (not centered) — the first line of the clicked DDL object's banner
  sits at the top edge, so the whole object is visible below it. This is **DDL-editor-specific**: it does
  **not** change `XmlEditor.navigate_to_line`, which stays **centered** (its Properties/tree-jump callers
  expect centering). Implementation-wise the DDL `CodeEditor.navigate_to_line` (§8) is what changes from
  `centerCursor()` to a top-alignment scroll (e.g. moving the target block to the top via the vertical
  scrollbar / `setTextCursor` + top-of-viewport positioning); `XmlEditor._scroll_and_highlight_whole_line`
  keeps `centerCursor()`.
- **Implemented:** left-dock tree tab `ui/ddl_buffer_panel.py::BrowserPanel(QWidget)` — a `QWidget`
  wrapping an internal `self.tree = QTreeWidget()` (composition), matching this codebase's real
  convention for left-dock panels (`TableReferencesPanel`, `DbCheckPanel` — both `QWidget` subclasses
  wrapping an internal tree), not literal `QTreeWidget` subclassing. Built from the `DdlObjectSpan`
  index via `set_schema(schema, spans)` — one shared buffer plus a structural tree index, the same
  relationship the Raw XML tree bears to `xml_editor.py`. Emits `navigate_requested(line: int)` on leaf
  click, wired in MainWindow to `_on_ddl_navigate_requested(line)` → activate the center DDL Explorer
  tab + `EditorPanel.navigate_to_line(line)`. Lives in a hidden `left_tabs` tab titled **"DDL
  Objects"** (`ddl_browser_tab_index`), revealed/hidden in lockstep with the center tab. This is the
  tree that §18.2's `*`/`!` state markers will render on.

**Dual-grouped, cross-referenced tree — a deliberate design choice by the project owner:** a trigger
appears in the tree in **both** of its relationship places, not just one:

- **Tables** (top-level group): each table lists the triggers defined on it (via `TriggerInfo.table`).
- **Functions & Procedures** (top-level group): each function/procedure additionally lists the triggers
  that invoke it (reverse reference via `TriggerInfo.function_name`).
- A trigger is therefore **two tree leaves pointing at the same underlying `DdlObjectSpan`** (same
  buffer location) — clicking either jumps to the identical line in the `EditorPanel` tab. This mirrors
  the existing Table References panel's precedent (§15, `TableUsage.references`) of showing the same
  object from multiple relationship angles rather than forcing a single parent — it is **not** a novel
  pattern, it already exists elsewhere in the app.
- Click on any leaf in `BrowserPanel` (function, procedure, or either trigger occurrence) → reveal the
  `EditorPanel` tab + `navigate_to_line(span.start_line)`, reusing the existing navigation API already
  described in §8 ("Public navigation API") and used by Properties/captions/DB check/table
  references/diff. DDL navigation is **top-aligned** (the object's first line lands at the top of the
  viewport — see EditorPanel navigation below), not centered.

**Tree presentation (`BrowserPanel._build_routines_branch` / `_build_tables_branch` /
`_add_trigger_leaf`) — the exact rendered labels:**

*Routine node (Functions & Procedures branch)* — top line = the **fully-qualified** name
`schema.name`, a **three-way** marker, and — only for a routine with **zero** input arguments — an empty
`()`:

| Kind | Marker | Condition |
|---|---|---|
| Procedure | `[P]` | `kind == "procedure"` |
| Trigger function | `[T]` | `kind == "function"` and `return_type == "trigger"` |
| Function | `[F]` | any other `kind == "function"` |

- A routine **with** input arguments (`args` non-empty) renders its top line as `schema.name [marker]`
  (**no** parenthesised argument list on the top line) and lists **one second-level child per input
  argument**, in declared order, labeled `name (type)`.
- A routine with **zero** input arguments (`args == []`) renders its top line as `schema.name() [marker]`
  (empty parens) and has **no** argument-child nodes.
- (Note: the top-line arg-list omission is a **tree-label** decision only; `build_ddl_text`'s banner
  comment in the buffer still carries the full `(argtypes)` from `arg_types` — §18.1 buffer, unchanged.)

*Trigger leaf* — used in **both** the Tables branch and the Functions & Procedures branch — the label is
the **composite** name `schema.table.triggername` followed by a **timing indicator** then **one event
indicator per event**, each bracketed:

| Timing | Letter | | Event | Letter |
|---|---|---|---|---|
| before | `[B]` | | insert | `[I]` |
| after | `[A]` | | update | `[U]` |
| instead of | `[I]` | | delete | `[D]` |
| | | | truncate | `[T]` |

Events render in the introspected order of `TriggerInfo.events` (`_decode_trigger_type` yields
insert → update → delete → truncate order). Example: a `BEFORE DELETE` trigger → `[B][D]`; an
`AFTER INSERT OR UPDATE` trigger → `[A][I][U]`. (The timing letter `[I]` "instead of" and the event
letter `[I]` "insert" collide as glyphs but never within one label position — timing is always the
first bracket, events follow; the composite `schema.table.triggername` prefix disambiguates in
practice.)

**Worked examples (reproduce exactly):**

Regular function with args — `CREATE OR REPLACE FUNCTION public.get_working_days_in_month(year integer,
month integer) RETURNS integer`:

```
public.get_working_days_in_month [F]
├─ year (integer)
└─ month (integer)
```

Trigger function (no args, `RETURNS trigger`) plus its trigger — `CREATE OR REPLACE FUNCTION
public.dont_delete_standards() RETURNS trigger` and `CREATE TRIGGER dont_delete_model_users BEFORE
DELETE ON public.phpgen_users FOR EACH ROW EXECUTE FUNCTION dont_delete_standards()`:

```
public.dont_delete_standards() [T]
└─ public.phpgen_users.dont_delete_model_users [B][D]
```

**XML cross-references — a third relationship angle, still not implemented (the one remaining §18.1
piece), unchanged in mechanism:**

- `db/routine_refs.py` (does not exist yet): cross-references routine/trigger names against the XML (event-handler bodies
  via `EventNode.text`, and SQL-bearing attributes) via **best-effort name matching** — same "no false
  confidence" ethos as `analysis/reused_tables.py` — producing `RoutineReference{routine_name, node,
  kind, line}` so a DB-side routine can be traced to where the XML calls it. This is **approximate, not
  guaranteed-complete**: it is name matching, not a SQL parser, and must not claim completeness it
  cannot deliver. Unlike the table/function tree groupings (which navigate within the single DDL
  buffer), this angle navigates **across** buffers — `EditorPanel` tab → Raw XML tab — two separate
  documents, two separate `navigate_to_line` targets, not the same underlying span. This angle only
  applies when a project has a linked `.pgtp` (§18.2) — it is meaningless in a `.pgtp`-free project.

**Database menu & main-window wiring — implemented:**

- The Database menu gains a **checkable "DDL Explorer" toggle** (`self._ddl_explorer_action`), after a
  separator following the existing three items (Connection Setup…, Check: XML→Database,
  Check: Database→XML). Toggle on → `_open_ddl_explorer()`; toggle off →
  `center_stage.hide_ddl_explorer()`.
- **Bidirectional lockstep** (the BUG-007 lesson — the tab has its own ✕):
  `CenterStage.ddl_explorer_visibility_changed(bool)` drives
  `_on_ddl_explorer_visibility_changed(visible)`, which shows/hides the left "DDL Objects" tab (making
  the tree dock visible and current when shown) **and** re-syncs the menu action's checked state, so
  closing via the tab ✕ unchecks the menu and vice versa.
- **Async fetch:** `_open_ddl_explorer()` runs `_fetch_ddl_schema(params)` (an **injectable seam** —
  a one-line wrapper around `fetch_routines_and_triggers(params)`, mirroring `_fetch_db_schema`; tests
  patch it to return a canned `DatabaseSchema`) through the shared `self._run_async` threadpool seam
  (the same off-thread executor the Database Check fetch uses, so a slow/dead host never freezes the
  window). On result: `build_ddl_text(schema)` → `EditorPanel.set_ddl_text(text)` +
  `BrowserPanel.set_schema(schema, spans)` + `show_ddl_explorer()` + a status-bar summary
  (`DDL Explorer: N routine(s), M trigger(s).`).
- **Standalone-mode friendly (§18):** connection params come from
  `seed_params(tree, self._settings)` where `tree` is the current project's lxml tree **or `None`**
  when no `.pgtp` is open — no project is required, only a configured connection. Missing host →
  status-bar message ("No database connection configured — set one up first."), uncheck the toggle,
  and open Connection Setup. Fetch error → status-bar message (`DDL Explorer failed: {exc}`) + uncheck
  the toggle. Params are logged redacted (`debuglog.redacted`).

**Explicitly phase 2, not built alongside phase 1 read-only browsing:** DB-side write-back — editing a
routine's source inline in the `EditorPanel` tab itself and pushing `CREATE OR REPLACE FUNCTION …`
straight to the live DB, with the diff detected per `DdlObjectSpan`. This is distinct from — and not a
prerequisite for — §18.2/§18.3's checkout/deploy workflow, which edits a separate `ddl/*.sql` file and
never writes to `EditorPanel` itself. If/when phase-2 inline write-back is built, it would be gated
behind a diff-preview + explicit confirm, all-or-nothing, mirroring the Diff/Merge Apply discipline
(§12).

### 18.2 Projects, checkout & state markers

**"Project" — a new concept, distinct from a `.pgtp` file.** A project = a git repo containing:

- A **committed** project JSON: project name, description, and **non-secret** connection metadata only
  (host/port/database/user — explicitly **no password**).
- A `ddl/` folder: **one file per DDL object** (function/procedure/trigger) — deliberately
  file-per-object (not one big file) specifically so `git diff`/`git blame` work meaningfully per
  object. This is the git-tracked, human-readable form of what's in `EditorPanel` (§18.1's single-buffer
  read-only browsing view is the live/synthesized view; `ddl/*.sql` files are the versioned,
  checked-out, editable form).
- An **optional** link to a `.pgtp` file — a project may have **zero, one pre-existing, or one
  newly-created** `.pgtp`. Not required, not assumed. (Only when a `.pgtp` link exists does §18.1's XML
  cross-referencing angle apply.)

**Password handling.** The plaintext password is explicitly **kept out of git**. Reuses the app's
**existing** `db/config.py::ConnectionParams`/`save_connection` local-settings mechanism (§17) rather
than inventing a new local-secrets file — but this **requires generalizing that store from
single-global-connection to keyed-per-project** (by project path or a project id), since today
(`db/config.py`, `_GROUP = "db"`, a single fixed QSettings group) it holds exactly one connection at a
time regardless of which project or `.pgtp` file is open. This is a **required change to the existing
`db/config.py`**, not a new parallel mechanism: `load_connection`/`save_connection` gain a project-key
parameter (or an equivalent keyed-group scheme) so each DDL-versioning project's connection (host/port/
database/user/password) persists independently.

**Checkout-to-edit.** Right-click an object in `BrowserPanel` (§18.1) — or its span in `EditorPanel` —
opens a new, single-object **editable** tab, a distinct tab type from the read-only `EditorPanel`,
editing just that one `ddl/<schema>.<name>.sql` file. Saving writes to that local file **only** — it
never touches the live DB directly (DB writes only happen via the reviewed §18.3 deploy step).

**State markers — combinable, not a new third symbol.** Rendered on `BrowserPanel` (§18.1) tree items:

- `*` = the local file has an unsaved-to-deploy edit (differs from the last-deployed reference for that
  object).
- `!` = the **live DB** has drifted from the last-deployed reference for that object.
- These are **independent booleans that render together** when both are true (e.g. `*!`) — there is
  **no separate third state/symbol** for "both." This is a deliberate embrace-drift philosophy: the
  tool surfaces disagreement, it does not attempt to auto-resolve it.

> **Settled: "last-deployed reference" = a git-tracked deploy manifest, target design.** A per-project
> deploy manifest (`.ddlproject/deployed.json`, git-tracked — non-secret provenance data) records, per
> DDL object, **both** a content-hash and a deployed commit id, with distinct roles:
>
> - **Content-hash** — the mechanism actually used for all drift comparisons: `*` = hash(local `ddl/`
>   file) != stored hash; `!` = hash(live DB introspected definition) != stored hash. This keeps the
>   correctness-critical comparison independent of git plumbing entirely — no shelling out to git, no
>   dependency on history staying intact — consistent with the "database is truth, git is history only"
>   principle stated above.
> - **Deployed commit id** — stored purely for human traceability ("this object was deployed as of
>   commit X"), not consulted by the comparison logic itself.
> - Implementation requirement: the hash must be computed the **same way** in all three places it's
>   used (local file content, live DB introspection via `pg_get_functiondef`/`pg_get_triggerdef`, and
>   the stored reference), so formatting/whitespace normalization doesn't produce false drift.
> - The manifest is written atomically at the moment §18.3's deploy step succeeds, alongside the git
>   commit of the deploy itself, and is git-tracked so "last-deployed" state travels correctly across
>   machines/clones rather than living only in one local session.

Markers are recomputed **fresh on every project load** per the truth-model principle above — never
cached or trusted from a prior session.

### 18.3 Deploy workflow & schema diff/migration

**Deploy workflow:**

1. Locally `*`-flagged objects (§18.2) are candidates for a deploy bundle.
2. **Any `!`-flagged object blocks deploy of the batch it's part of** — reuses the exact
   ambiguity-gate/all-or-nothing discipline already established by Diff/Merge (§12: refuse the entire
   batch naming each blocker, recovery = resolve then re-run) rather than inventing new machinery. Do
   not let a stale local edit silently overwrite a live DB change that happened independently.
3. Assembled into a single reviewed SQL bundle — **statement order is adjustable, content is not
   editable there** (editing only happens in the single-object checkout tabs, §18.2). This is
   explicitly **NOT** a second diff/generation engine — it invokes the **same** underlying
   diff/assembly machinery specified below, just from an edit-driven entry point (comparing local
   `ddl/` files against the last-deployed reference) rather than a schema-compare-driven entry point
   (comparing two `DatabaseSchema` snapshots). **One diff/generation engine, two entry points** — there
   are not two separate "assemble SQL" mechanisms.
4. Once the bundle is approved: (a) commit/push to git with versioning — **explicit placeholder, not
   designed, mechanism TBD** — and (b) execute against the live database. Reuses the existing "never
   auto-execute DDL silently" non-goal below — this is a reviewed, explicit action, not automatic.

**Schema diff & migration engine (shared by both entry points):**

- New pure module `db/schema_diff.py` (mirrors `diff/differ.py`'s contract shape but is
  DB-object-keyed, not XML-node-keyed): `SchemaDifference{kind: added|removed|changed, object_kind:
  table|column|routine|trigger, identity: str, old_def, new_def}`; `diff_schemas(source:
  DatabaseSchema, target: DatabaseSchema) → list[SchemaDifference]`.
- `db/schema_snapshot.py`: `dump_schema`/`load_schema` — lets a live DB be diffed against a checked-in
  JSON snapshot file, not only DB-to-DB, so a target/desired schema can be versioned.
- `db/migration_gen.py::generate_migration(differences) → str` — ordered CREATE→ALTER→(guarded,
  opt-in)DROP SQL text.
- New viewer reusing `diff_merge_panel.py`'s split layout (change list + detail pane,
  default-unchecked = skip — same review discipline as §12).
- **Hard non-goal, stated explicitly:** this never auto-executes DDL against a live database from the
  diff view. It only emits a reviewed `.sql` file (**"Save Migration As…"**) for the user's own deploy
  path, or (§18.3 step 4) the explicit, reviewed deploy action above. Auto-apply of DDL is out of scope
  — DDL against production is exactly the class of hard-to-reverse action this tool must not silently
  automate.
- **Database menu** gains **"Compare Schemas…"** (source/target: live connection or snapshot file) and
  **"Save Schema Snapshot…"**.

> **Settled: separate commands, one shared engine, target design.** The schema-compare entry point
> above stays a **fully separate sibling command**, not absorbed into the deploy workflow's UI — the
> "one diff/generation engine, two entry points" framing already stated above was correct all along;
> what was actually undecided was the UI surface, not the engine:
>
> - **`Database ▸ "Compare Schemas…"`** stays its own lightweight, **no-project-required** command
>   (live-vs-live, live-vs-snapshot) — useful even with zero DDL-versioning projects involved (e.g.
>   comparing staging vs. prod ad hoc).
> - The DDL-versioning project's **`Deploy`** command (§18.3 steps 1–4 above) is a separate, dedicated
>   flow — it carries the checkout-awareness, the `!`-blocks-batch ambiguity gate, and the git-commit
>   step that a generic compare tool should not be burdened with.
> - Both commands invoke the **same** `db/schema_diff.py`/`db/migration_gen.py` engine underneath — no
>   duplicated diff/generation logic, just two distinct entry points with two distinct UIs suited to
>   their two distinct audiences/guardrails.
> - **Rejected alternative:** a single unified Compare/Deploy screen. Rejected because it would either
>   overload the simple compare tool with project/git machinery it doesn't need, or dilute the deploy
>   workflow's guardrails into a generic diff viewer.

---

## 19. PHP generation (vendor) & Save

Implements §6.6. Shells out to the vendor generator; because the generator reads from disk, this also
owns File Save / Save As.

- `generation/config.py` (`generator_config.json` in AppData; injectable `generator_config_dir`):
  `load_executable_path`/`save_executable_path` (`executable_path` key) and `re_phpgen_root` (§20).
- `generation/runner.py`: `build_generate_command(exe, pgtp_path, output_folder)` (pure) →
  `[exe, pgtp_path, "-output", output_folder, "-generate"]`. `GeneratorRunner` wraps `QProcess`
  (`run(command, on_output, on_finished, cwd=None, extra_env=None)`, merged stderr; injectable).
- **Save / Save As:** write raw editor text UTF-8 (`.bak` first if overwriting). Save → `_current_project_path`
  (else Save As). Save As → `getSaveFileName` (`PGTP files (*.pgtp)`).
- **Generate PHP flow:** guard no-project / no-exe; prompt Save vs Save As (so disk matches editor);
  output folder prefilled from `Project@outputPath` else project dir; run with streaming `[PHP]` audit
  lines; finish → summary + success/critical dialog. **Locate PHP Generator Executable…**
  (`getOpenFileName`). **Open Output Folder** via `QDesktopServices.openUrl` (enabled after a run).

---

## 20. re_phpgen — own generator & gap loop

A **separate standalone repo** (`C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen`, branch `master`)
that reverse-engineers the vendor `.pgtp`→`.php` transformation. Design/spec/plan docs live in the
pgtp_editor repo; implementation lives in re_phpgen. Strategy: **parity-first** — emit per-page `.php`
byte-identical (after normalization) to freshly-regenerated vendor output, running against the vendor's
**unmodified** runtime; a future Phase 2 uses the harvested runtime-contract map to begin owning the
runtime.

- **Pipeline:** parse `.pgtp` (reuse pgtp_editor's model layer read-only; must expose `DataSources`) →
  intermediate model → per-page emit. Template + procedural hybrid: a **single** `page_class.php.tmpl`
  serves both master and detail classes (master vs detail = two slot differences: `EXTENDS`, `CMDRG`);
  all conditionality lives in Python slot-computation, never the template language. Modules: `catalog.py`
  (`detail_tree`), `skeleton.py` (`emit_page_file`), `pangen.py` (`emit_project`, best-effort),
  `gap.py` (`CAUSE_MARKERS`), `cli.py`/`__main__.py`.
- **Oracle & corpus:** vendor CLI is the test oracle; corpus = 37 real projects (`input/01..37.pgtp`).
  **Hard rule: regenerate, never trust stale pairs.** Normalizer (`normalize(php)`) folds
  non-determinism; comparison mode `masked-skeleton-v1` masks handler code + method bodies symmetrically.
- **Verified derivation rules** (master/detail slice): Detail emits a class **iff FK valid** (every
  `FieldMap@foreginColumnName` names a field in the detail's own field set), else the subtree drops;
  class order = depth-first **post-order** (children before parent, master last); detail class name =
  `"_".join(sanitize(t) for t in ancestry)+"Page"` with file-global 2-digit ordinals on duplicate stems;
  DetailPage skeleton = master skeleton − `CreateMasterDetailRecordGrid` + `extends DetailPage`; the
  global-handler block + `GetEnable*` flags + page parameters map from attributes by corpus correlation
  (residual ambiguity → manual GUI probe, never guessed).
- **Gap loop (editor integration):** the vendor baseline is produced **manually from the GUI** (the CLI
  is untrusted for automation). The editor calls re_phpgen **as a subprocess, never imports it**;
  `re_phpgen_root` config key resolves the runtime (`<root>\venv\Scripts\python.exe` if present else
  `sys.executable`; **Locate panGen Runtime…** overrides, validated to contain `src\re_phpgen`). CLI:
  `pangen <project> --out <dir>` and `analyze <project> --vendor <dir> --ours <dir> --json <path>` (writes
  a `schema_version 1` gap JSON with per-page statuses ok/diff/missing/error, cause buckets, capped
  `difflib` hunks). Editor menu actions (Generation menu conventions): **panGen (Generate Own PHP)** →
  `pangen … --out <folder>\_pangen`; **rePHPgen (Analyze Gap)** → require a vendor `.php` present, then
  pangen + analyze → summary; **Save reJSON…** (enabled after an analysis); **Locate panGen Runtime…**.

> **Branch-model note:** the re-phpgen work was folded into `main` and the branch deleted 2026-07-20; the
> project is now single-branch. Some re_phpgen spec headers still say `Branch: re-phpgen` (stale).

### 20.4 Production cutover (target design — not yet reached)

> **Status: target state, not yet implemented.** No promotion has happened; nothing described here
> exists in the codebase yet. This subsection formalizes the exit criteria referenced by §1's staged
> hard boundary.

`re_phpgen`'s end goal is to **replace** the vendor generator for real deployments, not to remain a
permanent gap-analysis-only tool. Promotion out of gap-analysis-only status requires **all three**
falsifiable criteria to hold simultaneously — none is sufficient alone:

1. **100% byte-parity** (post-normalization, `masked-skeleton-v1` comparison mode, §20) across the
   **full 37-project corpus** — the gap-analysis JSON must show zero `missing`, zero `error`, and zero
   residual-`diff` statuses for every page in every project.
2. **Verified determinism** — a twice-generate diff (same project, same `re_phpgen` run twice) must be
   empty. Currently unverified (§29 Open questions).
3. **The 8 parked edge-case pages** (471/479 cap, §20/§29) are resolved (parity achieved) or explicitly
   accepted as known-unsupported (documented, not silently dropped).

**Cutover mechanism, once all three hold:** promotion is **per-project and explicit** — a deliberate
user action via a new **Generation menu** action (name/placement TBD at implementation time, alongside
the existing panGen/rePHPgen actions, §26) — never silent, never automatic based on crossing a parity
percentage threshold. phpgen (vendor CLI/GUI) remains available **indefinitely** afterward as the
fallback/reference oracle: parity regressions in `re_phpgen` output are caught by diffing against
phpgen, never assumed away once cutover happens.

**Deferred, not designed here:** once production cutover and/or the custom-PHP editing surface (new
top-level section, below) exist, a minimal Git integration scoped to `re_phpgen`'s per-project output
folder becomes a natural next step (status/commit/diff, subprocess-based) — see the forward-reference
note in the "Custom PHP editing" section; no section number is spent on it yet.

---

## 21. Custom PHP editing

> **Status: target design, not yet implemented.** Nothing in this section exists in the codebase yet
> — this whole section is specification only, written ahead of build to keep the big picture clear.
> Scope is deliberately narrow, in the owner's own words: *"php ide from my point of view is a rich
> text editor like we already have, adding features one by one. the goal is to have something as
> useful as notepad++."* This is **not** a new IDE architecture and **not** code intelligence/LSP —
> it reuses the existing `ui/code_editor.py::CodeEditor` widget (already implemented; already does PHP
> syntax highlighting for inline event-handler bodies, §8) as a general multi-file editor, with
> features added incrementally.

**Phase 1 (the "Notepad++" baseline):**
- **File ▸ "Open PHP File…"** (+ drag-drop) opens any `.php`/text file in a new `CenterStage` tab
  (closable, dirty-marked) — the same per-tab document routing precedent as the Edit XSD tab (§7).
  Multiple files open concurrently as ordinary tabs. **No structural tie to a `.pgtp` project is
  required at this level** — any file opens standalone, independent of whether a project is loaded.
- Each tab hosts the **existing** `CodeEditor` in `language="php"` mode with its own
  `FindReplaceBar` instance (same pattern as Edit XSD, §7/§15) and its own Ctrl+S/undo, independent of
  the project document's dirty state.

**Explicitly sequenced, incremental follow-ups** (named as the roadmap only — not designed in detail
here; build one at a time, in this order, matching "adding features one by one"):
1. **PHP folding** for `CodeEditor` — mirrors the Raw XML editor's folding (§8); `CodeEditor` currently
   has none.
2. **A file-tree dock tab** for a configured "custom code" folder (parallel to Project Tree, §7),
   giving the scattered Gantt/print/loader-style files one browsable home instead of ad-hoc opening —
   folder configured per-project, analogous to `Project@outputPath`.
3. **Find in Files** across that folder — extends §15's search core to multi-file.

**Explicit non-goal:** no code intelligence — no LSP, no parse-based autocomplete. This is a recorded
scope decision, not a gap to eventually fill.

**Forward reference (deferred, not designed here):** once this section and §20.4 (Production cutover)
both exist, a minimal **Git integration** — status/commit/diff/pull/push, subprocess-based wrapper, not
a full client — scoped to this section's custom-PHP folder and/or `re_phpgen`'s per-project output
folder is the natural next step. Explicitly deferred; no section number spent on it yet.

---

## 22. Lint integration

> **Status: target design, not yet implemented.** Depends on §21 (Custom PHP editing) existing first —
> there is nothing to lint before a custom-PHP tab exists. Sequence this **after** §21 in any future
> work, not concurrently with it.

- Runs an external linter (`php -l`, optionally full `phpcs`) against the active custom-PHP tab's
  content (§21), either on save (toggleable) or via **Tools ▸ "Lint Current File"**.
- Executable path configured with the same pattern as `generation/config.py`'s `executable_path`
  (§19): a new `lint_executable_path` key + a "Locate PHP Linter…" action.
- Output feeds the existing Audit panel (§7) with a new `[Lint]` prefix, following the same
  click-to-navigate convention as `[Validate]`/`[Find]`.
- **Non-blocking:** advisory only — never prevents Save.

---

## 23. MCP integration

> **Status: target design, not yet implemented.** No MCP server/adapter exists in the codebase yet.

- An optional embedded MCP server, **off by default** (opt-in in Preferences) — it exposes project
  data to any connected MCP client, so it must not be silent or default-on.
- Exposes the app's already-Qt-free pure layers (`model/`, `diff/`, `db/`, `analysis/` — per §5's
  existing dependency rule, these have no Qt dependency) as MCP tools via a thin adapter, with **no new
  business logic**: e.g. `read_project(path)`, `list_pages(path)`, `get_node(path, identity)`,
  `diff_projects(source, target)`, `list_db_tables(connection)`, `list_db_routines(connection)` (the
  last two build on §18.1's DDL Explorer introspection, which now exists).
- Runs over **stdio**; started via **Tools ▸ "Start MCP Server"** or a `--mcp` CLI flag for headless
  use. When the GUI is running it shares the currently-open in-memory model; running headless it
  operates file-path-driven instead.

---

## 24. In-app manual

English Markdown manual bundled at `pgtp_editor/resources/manual.md` (via
`[tool.setuptools.package-data]`). `ui/manual_panel.py`: `load_manual_text()` (via `importlib.resources`),
`parse_chapters(md)→list[Chapter{level, title}]` (ATX headings, skips fenced code), `ManualPanel(QTextBrowser)`
(read-only, external links, `set_markdown`, `scroll_to_chapter(index)`), `ManualContentsPanel(QWidget)`
(`QTreeWidget`, `chapter_selected(int)`). Center-stage **Manual** tab + left-dock **Contents** tab; **Help
▸ Manual (F1)**. 13 chapters incl. Generating PHP, Validation, Keyboard Shortcuts, Troubleshooting/debug.
Offline, read-only (no editing/searching, single language).

---

## 25. Debug mode

Activated by `--debug` or `PGTP_EDITOR_DEBUG=1`; `debuglog.setup(debug=)` runs **before** `QApplication`.
Only new module: `debuglog.py`. Log dir `%LOCALAPPDATA%\MDS\PGTP Editor\logs\` (fallback
`~/.pgtp_editor/logs`, pure `log_dir()`): `errors.log` always-on (WARNING+, rotating 3×1 MB) +
`debug_YYYYMMDD_HHMMSS.log` per session (unrotated).

- **Always captured:** session header, uncaught exceptions (`sys.excepthook` + `threading.excepthook` +
  Qt slot path), Qt messages (`qInstallMessageHandler`), Python warnings.
- **Debug adds:** (a) auto-trace via `sys.monitoring` (3.12+, `PROFILER_ID`, PY_START/PY_RETURN/RAISE),
  scoped to `pgtp_editor` files with a hot-path exclusion list, TRACE level (5) to the debug file, args/
  returns not logged; (b) ~15 semantic seam logs (open/save/close, parse/reparse, undo/redo, DB
  connect/test/check/rename, generation command+exit+duration, schema enrich, diff/merge, caption,
  theme/toolbar/dock, dialog open/close). **Redaction:** `ConnectionParams.redacted()` (locked by test).
- UI: status-bar "DEBUG" chip; **Help ▸ Open Log Folder** (injectable `opener=` seam). Failure-safe
  (tracer failure → WARNING + continue).

---

## 26. Consolidated menu bar

Final reconciled state (after all overrides — the original top-level "Diff/Merge" menu was folded into
Tools; "New Project" removed; line-wrap moved to editor context menu):

- **File:** Open (Ctrl+O), Open Recent, Save (Ctrl+S), Save As (Ctrl+Shift+S), Close (Ctrl+W), Revert,
  Exit.
- **Edit:** Undo (Ctrl+Z), Redo (Ctrl+Y), Cut/Copy/Paste/Delete, Find… (Ctrl+F), Find Next (F3), Find All
  (Ctrl+Shift+F), Replace… (Ctrl+R), Replace All (Ctrl+Alt+Return), Select Enclosing Block (Ctrl+Shift+B),
  Select Parent Block (Ctrl+Shift+A), Preferences.
- **View:** ☑ Project Tree, ☑ Properties, ☑ Audit, ☑ Raw XML Panel (checked by default), Expand All,
  Collapse All, ☐ Light Theme, ☑/☐ Find table reference.
- **Bookmarks:** Toggle Bookmark (Ctrl+F2), Next Bookmark (F2), Previous Bookmark (Shift+F2), Clear All
  Bookmarks.
- **Schema:** Edit XSD, Edit AutoXSD, Verify XSD, Export XSD, Import XSD — five items (§11). Verify /
  Export / Import act on the **active XSD** (curated or learned, per `_xsd_mode`), not curated-only.
  (Go To XSD is **not** a menu item: it is a window-level Ctrl+L `QAction` added via
  `MainWindow.addAction` plus a Raw XML editor context-menu entry; it always forces curated mode.)
- **Database:** Connection Setup…, Check: XML→Database, Check: Database→XML, ☐ DDL Explorer
  (checkable toggle after a separator, §18.1; kept in lockstep with the center tab's ✕).
- **Tools:** Manage Captions…, Caption Filter… (Ctrl+R in caption context), Reparse Raw XML into Tree,
  Validate Project, Compare/Merge Two Files…, Next/Previous Difference, Apply Changes to Target.
- **Generation:** Locate PHP Generator Executable…, Generate PHP…, Open Output Folder, panGen (Generate
  Own PHP), rePHPgen (Analyze Gap), Save reJSON…, Locate panGen Runtime….
- **Help:** Manual (F1), Open Log Folder, Documentation, About.

Toolbar default: Open, Save, Undo, Redo, Find, Validate, Generate (customizable).

---

## 27. Consolidated keyboard shortcuts

| Shortcut | Action | Context |
|---|---|---|
| Ctrl+O / Ctrl+S / Ctrl+Shift+S / Ctrl+W | Open / Save / Save As / Close | Window (Save routes to the active center-stage tab: Raw XML or Edit XSD, §7) |
| Ctrl+Z / Ctrl+Y | Undo / Redo (single step) | Window |
| Ctrl+F / F3 / Ctrl+Shift+F | Find / Find Next / Find All | Window |
| Ctrl+R / Ctrl+Alt+Return | Replace / Replace All | Window (caption: Ctrl+R = Caption Filter) |
| Ctrl+Shift+B / Ctrl+Shift+A | Select Enclosing / Parent Block | Raw XML editor (menu-owned) |
| Ctrl+click / Alt+click | Jump to matching tag / parent tag | Raw XML editor |
| Ctrl+F2 / F2 / Shift+F2 | Toggle / Next / Previous Bookmark | Raw XML editor |
| Ctrl+L | Go To XSD (jump to the attribute's definition in curated.xsd; always forces curated mode) | Window-level QAction (also in the Raw XML editor context menu) |
| Ctrl+G | Go to line in XML | Caption grid |
| Ctrl+Shift+B | Bracket-select | Code editor dialog |
| Ctrl+S / Ctrl+W | Save / Cancel | Code editor dialog |
| F1 | Manual | Window |

---

## 28. Supersession ledger

Chronological record of decisions where a later spec overrode an earlier one. **Only the later decision
is authoritative** (and is what appears in the body above).

| Date | Superseded | Replaced by |
|---|---|---|
| 2026-07-12 | Original §6.2 Move/Copy of Detail blocks | Raw XML structural block-select + OS clipboard (incl. folded blocks) — **feature dropped** |
| 2026-07-12 | Original §6.5 Client read-only page generation | Same (copy page in raw XML, set `*AbilityMode` by hand) — **feature dropped** |
| 2026-07-12 | Properties "Real Raw XML display" (model roadmap SP2) | Folded into the XML Editor foundation |
| 2026-07-12 | Properties: `highlight_error_line` as primary API | Generalized `navigate_to_line`; `highlight_error_line` reimplemented on it; `line_text`/`select_range_on_line` added |
| 2026-07-12 | Original §6.1 `moved` difference kind | Dropped — a relocation = one removed + one added (no project-wide Detail identity) |
| 2026-07-12 | `resolve_path` nullable return | `ResolutionError{segment_index, message}` (never bare `None`) |
| 2026-07-12 | Model layer "discards the lxml tree" | Tree + per-node `element` retained (enables byte-faithful write-back) |
| 2026-07-13 | Original §6.3 grouped-coherence caption audit | Flat line-anchored caption grid (coherence re-added later as the one-click "Unify") |
| 2026-07-14 | Caption mode hides Raw XML + 5-col Value-editable grid + inline filter row | Raw XML visible-but-read-only; 8-col grid with read-only Value + editable New Value; header filters + find/replace modal |
| 2026-07-15 | Original View-menu "Wrap Raw XML Lines" | Moved to the Raw XML editor's right-click context menu |
| 2026-07-15 | Original top-level "Diff / Merge" menu | Items moved into the Tools menu; top-level menu removed |
| 2026-07-15 | Original File-menu "New Project" | Removed |
| 2026-07-15 | Original View-menu Raw XML unchecked-by-default | Raw XML tab visible/checked by default |
| 2026-07-15 | Editor-owned `QShortcut`s for block select | Edit-menu actions own Ctrl+Shift+B / Ctrl+Shift+A (WindowShortcut) |
| 2026-07-15 | Structural-select caret-at-end | Caret-at-start (anchor end, position start) + `ensureCursorVisible` |
| 2026-07-15 | Annotate UI flat one-row-per-value table (2026-07-12 SP B) | Two-pane labeler + `kind` classification; hover hints; XSD annotations |
| 2026-07-15 | About box SuperNano credit | Removed; MDS/author credits, format v22.8 |
| 2026-07-15 | Edit-menu "Find & Replace…" (Ctrl+H) stub | Real Find/Replace actions (Ctrl+F/F3/Ctrl+Shift+F/Ctrl+R/Ctrl+Alt+Return) |
| 2026-07-13 | Synchronous Find All | Streaming chunked Find All with Stop + counts |
| 2026-07-19 | `_closing_tag_start` private in xml_editor | Promoted to public `closing_tag_start` in `xml_structure` |
| 2026-07-19 | re_phpgen `page_skeleton.php.tmpl`; two-template master/detail | Single `page_class.php.tmpl` + `file_frame.php.tmpl`, Python slot-computation |
| 2026-07-19 | Vendor CLI trusted as automation oracle (for the editor gap loop) | Manual GUI vendor baseline (CLI hangs on modal `EInvalidXML`) |
| 2026-07-20 | DB-check populate inline in `on_result`; Toolbar Available = registry-minus-present | `_populate_db_check` + cached-schema reparse refresh; Available = all commands, present ones disabled |
| 2026-07-20 | Multi-branch model (incl. re-phpgen branch) | Single-branch (`main`); re-phpgen folded in & branch deleted |
| 2026-07-21 | "Find Reused Tables" modal (`ReusedTablesWindow`) + `TableUsage.breadcrumbs` | Table References dock tab + `TableUsage.references: list[TableReference]`; modal deleted |
| 2026-07-23 | Two-pane Annotate Schema Values dialog (`annotate_schema_values_dialog.py`) + Schema ▸ "Annotate Schema Values…" (2026-07-15) | Annotate-at-cursor popover in the XML editor (Ctrl+L / value context menu) authoring `labels`/`kind`/`notes`/`enum_mode` + unlabeled-value dotted underlines + Next Unlabeled Value navigation; dialog and menu action deleted |
| 2026-07-23 | `known_values` = engine-observed values only | Union of engine-observed values and labeler-added label keys |
| 2026-07-24 | Annotate-at-cursor popover (`ui/annotate_popover.py`, Ctrl+L, context-menu "Annotate value…") (2026-07-23) | Direct hand-editing of `curated.xsd` in the Edit XSD tab; popover deleted; **Ctrl+L reassigned to Go To XSD** |
| 2026-07-24 | Unlabeled-value dotted underlines + Next Unlabeled Value (Ctrl+Shift+L) (2026-07-23) | Removed (curation happens in the XSD, not the document); Ctrl+Shift+L freed |
| 2026-07-24 | Labeler-owned model fields `labels`/`kind`/`notes`/`enum_mode` + bitflag derivation in `settings_index` | XSD dialect `label=`/`sums=`/`hint=` on `curated.xsd`; additive-value derivation reimplemented against `sums`; `kind`/`notes` concepts dropped |
| 2026-07-24 | Team schema-model sharing via git — `schema_learning/sync.py`, `schema_learning/merge.py`, `ui/team_sync_dialog.py`, `ui/merge_conflicts_dialog.py`, Schema ▸ Publish/Fetch/Merge/Team Sync Settings, `schema_sync/*` QSettings keys, `team_repo_dir`, the sum-based count-merge accepted-limitation | Schema ▸ **Export XSD / Import XSD** plain file exchange (verify-before-import, `curated.xsd.bak` backup) |
| 2026-07-24 | Read-only `SchemaViewerWindow` + Schema ▸ Open XSD / Open XSD Labels (JSON) (`ui/schema_viewer.py`, `ui/schema_viewer_data.py`) | Editable **Edit XSD** center-stage tab (second `XmlEditor` + own `FindReplaceBar`) |
| 2026-07-24 | "`schema.xsd` is a generated, read-only artifact — hand-edits do not persist"; per-user JSON model as local source of truth for completion | **Inverted:** `curated.xsd` is the official, hand-edited-only schema and sole completion/hover/Properties source; the generated-artifact role moves to `learned.xsd`; `schema_model.json` demoted to the engine's private state |
| 2026-07-24 | Endgame "freeze master → bundle XSD into the app" (learning-period close-out) | Superseded — the curated XSD is official from day one; no learning-period endgame exists |
| 2026-07-27 | Unbounded `sums` derivation — completion offers all 2^n − 1 combinations for any number of labeled atoms (2026-07-24) | Capped at `settings_index.SUMS_MAX_ATOMS = 16` labeled atoms: beyond that, derivation is skipped (explicit labels only, UI-freeze guard) and Verify flags the attribute |
| 2026-07-29 | §1 "Hard boundary" as a **permanent, no-exit** wall — `.pgtp`→`.php` compilation strictly one-way and vendor-owned, with no stated path for `re_phpgen` (§20) to ever become the tool of record | **Staged** boundary with named exit criteria: the wall holds exactly as before *today* (`re_phpgen` stays gap-analysis-only, invoked read-only as a subprocess; phpgen remains tool of record), but `re_phpgen`'s stated end goal is production replacement of the vendor generator, gated by three falsifiable promotion criteria (100% byte-parity across the 37-project corpus, verified determinism, the 8 parked edge pages resolved-or-accepted) formalized in new §20.4 "Production cutover" (target design, not yet reached); cutover is per-project and explicit via a future Generation-menu action, never silent/automatic; phpgen remains available indefinitely as fallback/reference oracle |
| 2026-07-29 | §17.1 DDL Explorer as `ui/ddl_explorer_panel.py::DdlExplorerPanel`, a tree grouped by kind only (Functions / Procedures / Triggers), with each leaf opening its own separate read-only source viewer (reusing `CodeEditor` per object) | Single synthesized DDL buffer (`db/ddl_buffer.py::build_ddl_text` + `DdlObjectSpan` index) hosted in one new `CodeEditor` tab under a new `language="sql"` mode, paired with a dual-grouped (Tables **and** Functions & Procedures) cross-referenced left-dock tree where triggers appear as two leaves pointing at the same span — reusing the Raw XML editor's `TagSpan`/`node_at_line` buffer-plus-span-index architecture (§8/§9) instead of per-object viewers |
| 2026-07-29 | §1 scope: PGTP Editor described purely as a `.pgtp`-editing tool (plus its vendor-generation and re_phpgen sub-projects), with no standalone/DB-only usage mode | Scope explicitly **broadened**: PGTP Editor also functions as a **standalone Postgres DDL-versioning tool**, usable with zero `.pgtp` files, sharing the app's DB connection/code editor/diff infrastructure as an independent mode (not a separate repo, unlike the `re_phpgen` precedent) — new top-level §18 |
| 2026-07-29 | §17.1 "Routines & triggers (DDL Explorer)" as a `§17.x` Database subsection, scoped to read-only browsing only, with phase-2 write-back sketched as inline `EditorPanel` DB push | **Relocated and reframed** as §18.1 "Routines & triggers browsing (DDL Explorer)" — a subsection of new top-level §18 "DDL versioning (standalone Postgres mode)" — now explicitly the shared browsing substrate for §18.2's checkout-to-edit and §18.3's deploy workflow, not a self-contained DB-menu feature; `RoutineInfo`/`TriggerInfo`/`DatabaseSchema.routines`/`.triggers` stay generic introspection in §17, reused by both the pre-existing DB-check features and the new §18 workflow |
| 2026-07-29 | §17.2 "Schema diff & migration" as a standalone `§17.x` Database subsection (schema-compare-only entry point: live-vs-live or live-vs-snapshot `DatabaseSchema` diff, "Compare Schemas…"/"Save Schema Snapshot…") | **Relocated** into §18.3 "Deploy workflow & schema diff/migration" as the shared diff/migration engine (`db/schema_diff.py`/`db/schema_snapshot.py`/`db/migration_gen.py`) now also invoked from §18.3's edit-driven deploy entry point (comparing local `ddl/` files against the last-deployed reference) — **one diff/generation engine, two entry points**. Whether the original schema-compare entry point should be fully absorbed into §18.3 or remain a sibling feature sharing only the diff core is an **explicit open question** (§29), not resolved by this relocation |
| 2026-07-29 | Both mechanisms left as explicit open questions pending owner sign-off (§18.2 "last-deployed reference" mechanism; §18.3 vs. original §17.2 schema-compare — absorb or sibling) | Settled, target design: **content-hash + commit-id git-tracked deploy manifest** (`.ddlproject/deployed.json`) as the last-deployed reference, hash-based drift comparison independent of git plumbing (§18.2); **separate `Compare Schemas…`/`Deploy` commands sharing one `db/schema_diff.py`/`db/migration_gen.py` engine**, unified screen explicitly rejected (§18.3) |
| 2026-07-30 | `curated.xsd` seeded on first run by **generating from the learned model** (2026-07-24) | Seeded by **copying the bundled `resources/curated.xsd` (Curated v1.2)**; learned-model generation is now the **fallback** used only when no bundled resource exists |
| 2026-07-30 | Single-purpose curated-only **Edit XSD** tab; **Schema menu = exactly these four** (Edit XSD, Verify, Export, Import); Verify/Export/Import curated-only (2026-07-24) | **Mode-aware** Edit XSD / Edit AutoXSD tab (`_xsd_mode ∈ {"curated","learned"}`, opens `learned.xsd` for analysis); Verify/Export/Import act on the **active XSD**; **Schema menu has five items** (Edit XSD, Edit AutoXSD, Verify, Export, Import) |
| 2026-08-01 | Edit XSD / Edit AutoXSD tab had **no close affordance at all** once revealed (only Raw XML/other-tab clicks or app close ended it; BUG-001) | **Closable** via tab-bar ✕ (`CenterStage.xsd_close_requested` → `MainWindow._on_xsd_close_requested`), reusing the existing `_confirm_close_xsd()` Save/Discard/Cancel prompt; hides via `hide_edit_xsd()` and falls back to Raw XML |
| 2026-08-01 | "Light Theme" **off** = restore the native/OS style+palette captured at startup (`_default_palette`/`_default_style_key`; `apply_theme(app, light, default_palette, default_style)`), with `_restore_theme` a no-op when `lightTheme` was False — dark only "worked" on the one native-dark platform (Windows) it was built on (BUG-004) | Symmetric explicit themes (commit 7ec792f): new pure `dark_palette()` mirroring `light_palette()`'s complete role coverage; `apply_theme(app, light: bool)` always sets Fusion + one of the two palettes; startup capture removed and `_restore_theme` applies the persisted theme unconditionally for both states; QSettings bool `"lightTheme"` unchanged |
| 2026-08-01 | §18.1 `RoutineInfo` carried argument **types only** (`arg_types: list[str]`), no argument names | `RoutineInfo` gains `args: list[tuple[str, str]]` (input argument **name+type pairs**, declared order, IN/INOUT only); the introspection query sources argument names; `arg_types` retained for `build_ddl_text`'s banner |
| 2026-08-01 | §18.1 BrowserPanel routine top-line = bare `name(argtypes)  [marker]` with a **binary** marker (`[F]` function / `[P]` procedure); no per-argument children | Top-line = **fully-qualified** `schema.name` with a **three-way** marker (`[P]` procedure / `[T]` trigger-function `return_type=="trigger"` / `[F]` other function); a routine **with** inputs lists each as a `name (type)` second-level child and carries **no** parens on the top line; a **zero-input** routine shows empty `()` on the top line and no children |
| 2026-08-01 | §18.1 BrowserPanel trigger leaf = `name  (timing/events) on table` (Tables branch) / `name  (timing/events) → function` (Functions branch) | Composite `schema.table.triggername` + bracketed **timing indicator** (`[B]`before / `[A]`after / `[I]`instead of) + **one bracketed event indicator per event** (`[I]`insert / `[U]`update / `[D]`delete / `[T]`truncate), e.g. `[B][D]`, in both branches |
| 2026-08-01 | §18.1 DDL `EditorPanel`/`CodeEditor` navigation **centered** (`CodeEditor.navigate_to_line` used `centerCursor()`) | DDL navigation **top-aligned** — the object's first line lands at the top of the viewport; DDL-editor-specific, `XmlEditor.navigate_to_line` stays **centered** (its Properties/tree-jump callers expect centering) |
| 2026-08-01 | §8 gutter / bookmarks / folding existed **only** on `XmlEditor`; DDL `EditorPanel`'s `CodeEditor` had none (no gutter/line-numbers/bookmarks/folding, Qt-mono default tab stop) | Generic gutter + bookmark + fold-**state** machinery **extracted into a shared base (class/mixin)** with a **pluggable foldable-region provider**, used by **both** `XmlEditor` (XML-span provider) and the DDL editor (DDL-object provider over the `DdlObjectSpan` index); DDL editor also gains a **4-character tab stop** — one gutter implementation, never a parallel second |
| 2026-08-01 | Dark theme = Fusion + `dark_palette()` **palette-only** (the BUG-004 fix above, same date) — Fusion+palette alone rendered checkable menu indicators outlined near-black on the dark menu background (BUG-010) | Dark = Fusion + `dark_palette()` **+ the QDarkStyleSheet dark QSS** (`qdarkstyle>=3.2`, new runtime dependency, MIT-credited in About); light **always** clears the stylesheet (`app.setStyleSheet("")`) so round-trips leave no stale QSS; the palette stays applied beneath the QSS for palette-reading custom widgets; side effect: `app.style().objectName()` is empty in dark mode (`QStyleSheetStyle` wrapping) |

---

## 29. Open questions

- **Ability-code numeric mapping** (`*AbilityMode`): integer→label mapping still unknown; derive
  empirically. No longer blocking — powers editor hover tooltips.
- **Bundled-curated version upgrades:** shipping a newer bundled `curated.xsd` (e.g. v1.3) does **not**
  update an existing user's hand-owned `curated.xsd` — seeding is seed-only-when-absent
  (`CURATED_BUNDLED_VERSION` marks the bundled version). Whether/how to offer an opt-in re-seed or a
  merge on version bump is unresolved.
- **Create-from-table parity is not yet vendor-confirmed:** `type_map` defaults and caption humanization
  are corpus-derived; needs a golden "freshly-added table" `.pgtp` from PHP Generator to calibrate and
  re-baseline the golden fixtures.
- **re_phpgen:** caption localization (verbatim vs `Project@localizationFileName`), alias/handler counter
  numbering scheme, DataSource-schema origin (`.pgtp` vs live DB), determinism (unverified until the
  twice-generate diff runs); flag-mapping residual ambiguity; 8 parked edge pages (471/479 cap).
- **Event tag naming variants** (e.g. `_SimpleHandler` suffix) — verify normalization before matching the
  9/31 list.
- **Handler body storage** — confirmed plain XML-escaped text (not CDATA); `<`/`&` escaped on write.
- **Debug** exclusion list + exact seam set finalized during implementation; `PROFILER_ID` may be taken
  (must fail gracefully).
- **Fold re-scan performance** and `line_index` O(N²) — accepted for now; optimize only if profiling
  demands.

---

## 30. Testing policy

(Authoritative in [`CLAUDE.md`](../../CLAUDE.md); summarized here.)

- Every completed feature triggers the **`feature-tester`** agent and produces a `docs/TEST_LOG.md`
  entry (append-only, newest at top). A feature without a green feature-tester run + log entry is not
  done.
- Use the **system `python`** (editable install with pytest/pytest-qt); the repo `venv\` is bare.
  Full suite: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`.
- Tests mirror the package: `pgtp_editor/<area>/foo.py` → `tests/<area>/test_foo.py`.
- **Never let a test reach an un-patched modal Qt call** (`QDialog.exec`, `QMessageBox.*`,
  `QFileDialog.*`, `QMenu.exec`) — monkeypatch them. Widgets expose test seams (`selected_ids`,
  `set_params`, `changed_edits`, `filter()`/`replace_all()`, `_history_jump`, `confirm=`, injectable
  `runner=`/`opener=`/config dirs) precisely so tests drive logic without modal loops.
- Real-sample tests skip gracefully when the git-ignored sample files are absent.
- The self-diff regression guard (`diff_project(m, m) == []`) and byte-for-byte round-trip
  (load→save→diff) must stay green — they protect the master serialization invariant.

---

## 31. Maintenance protocol

This document is maintained by the **`spec-maintainer`** agent (`.claude/agents/spec-maintainer.md`),
which has two duties:

1. **Keep this file in sync.** Whenever a new dated spec lands under `docs/superpowers/specs/` (or an
   existing one changes), the agent folds it in using latest-wins reconciliation, updates the affected
   section(s), and appends a row to the [Supersession Ledger](#28-supersession-ledger) for any override.
   It never leaves two contradictory statements in the body.
2. **Gate brainstorming.** Whenever brainstorming runs for a new idea, the agent first locates where the
   idea belongs in this spec — flagging any existing feature that already covers most of it and any
   near-duplicate that should be *extended* rather than *forked*. The goal is cohesive, complex features
   over parallel functionalities that differ only marginally; the up-front design cost is deliberately
   accepted to avoid the larger cost of building then correcting/overwriting redundant work.

When editing: change the body to reflect the new decision, move the old decision into the ledger (do not
leave it in the body), update `Last synthesized`, and keep section numbers/anchors stable where possible.
