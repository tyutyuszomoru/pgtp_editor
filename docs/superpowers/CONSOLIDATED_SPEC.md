# PGTP Editor — Consolidated Specification

> **Status:** living document · **Last synthesized:** 2026-08-02
> **Source of truth:** this file is the single reconciled specification for PGTP Editor, and the **only**
> place specification content is written. It was originally synthesized from the dated design specs under
> [`docs/superpowers/specs/`](specs/) — a folder now **frozen as historical record** (read for rationale;
> never added to or edited). All new and changed design is written **directly here**, using a
> **latest-wins** rule: where a later decision overrode an earlier one, only the later decision
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
    - [18.4 SQL/plpgsql selection formatter](#184-sqlplpgsql-selection-formatter) — *core implemented 2026-08-01; consumer designed (§18.5), not built*
    - [18.5 The DDL object editor, apply & sandbox validation](#185-the-ddl-object-editor-apply--sandbox-validation) — *planned; **the deliverable is the generated deployment SQL script**, over a stateful sandbox (the editable tab is specified here, once)*
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

**Product framing (the frame that ranks the roadmap, stated by the project owner).** The app exists to
help developers build **heavily plpgsql-centred applications safely and efficiently**. It is a direct
correction of what those developers hit in **DBeaver — "where the only possibility is to break the
database."** In DBeaver, editing a function and deploying it are the *same keystroke*: `CREATE OR
REPLACE` runs against the live database the moment you save, with no intermediate state, no preview and
no undo. **DBeaver's feature set is the floor, not the goal.** The direction is a smart IDE that keeps
the `.pgtp` XML and the database **in sync** for fast, safe function/procedure development. Consequently
the **edit → validate → apply loop (§18.5) is the core value proposition, not a side feature**, and
§18's ordering follows from that: the sandbox is the missing intermediate state where *"I changed this"*
and *"production changed"* are finally two different events; git versioning (§18.2), drift markers and
the reviewed deploy bundle (§18.3) are all downstream of that one separation.

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
│   │                  # introspect.py::run_queries is the sole READ seam — read-only, never commits
│   ├── ddl_buffer.py  # build_ddl_text(schema) → (text, [DdlObjectSpan]) — DDL Explorer buffer (§18.1)
│   ├── apply.py       # TARGET DESIGN, does not exist yet — the sole DB **write** seam: apply_ddl(...)
│   │                  # (explicit commit/rollback, ApplyOutcome); the codebase's first write path (§18.5)
│   ├── sandbox.py     # TARGET DESIGN — PostgresBackend protocol + LocalPostgresBackend +
│   │                  # SandboxCapabilities + the app-owned-database ownership guard (§18.5)
│   ├── ddl_check.py   # TARGET DESIGN — validation-ladder driver: CheckRequest →
│   │                  # CheckReport{per-tier outcome, [CheckFinding]} (§18.5)
│   ├── ddl_project.py # TARGET DESIGN, does not exist yet — pure DDL-project paths: object → ddl/*.sql
│   │                  # filename (overload disambiguation, sanitization), project.json/deployed.json
│   │                  # shapes; Qt-free & DB-free, mirroring ddl_buffer.py's precedent (§18.2)
│   ├── schema_diff.py # TARGET DESIGN — diff_schemas(source, target) → [SchemaDifference]; the shape is
│   │                  # §18.3's verbatim, first built by §18.5's Generate Deployment SQL with the
│   │                  # routine/trigger cases only (table/column deferred to §18.3)
│   └── migration_gen.py # TARGET DESIGN — generate_migration(differences, *, header) → str; pure,
│                      # deterministic; raises UnsupportedDifference on table/column (§18.5/§18.3)
├── analysis/
│   └── reused_tables.py   # collect_table_usages → TableUsage/TableReference
├── validation/
│   └── tier2.py       # validate_project → list[ValidationIssue]
├── sql/               # SQL/plpgsql selection formatter core (Qt-free) — §18.4
│   ├── __init__.py    # façade: format_selection / FormatResult / Issue / SQL_KEYWORDS (test-pinned __all__)
│   ├── keywords.py    # SQL_KEYWORDS — the ONE dialect source, shared with ui/code_editor.py's highlighter
│   ├── issues.py      # Issue{message, start, end, start_line/col, end_line/col, fatal} (+ .line alias)
│   ├── tokenizer.py   # Token + tokenize(text) → list[Token] (verbatim, never raises)
│   └── formatter.py   # format_selection(text, *, indent_unit="    ") → FormatResult; _Reindenter frame walk
└── ui/                # all PySide6 widgets (see below)
```

Key `ui/` modules: `main_window.py`, `center_stage.py`, `project_tree.py`, `xml_editor.py`,
`xml_structure.py`, `editor_gutter.py` (the one shared gutter/bookmark/fold implementation, §8),
`code_editor.py`, `event_body.py`, `properties_panel.py`, `find_replace_bar.py`,
`search.py`, `history.py`, `theme.py`, `toolbar_registry.py`, `customize_toolbar_dialog.py`,
`diff_merge_panel.py`, `caption_management_panel.py`, `caption_find_replace_dialog.py`,
`caption_scan.py`, `db_check_panel.py`,
`connection_setup_dialog.py`, `table_references_panel.py`, `ddl_editor_panel.py`,
`ddl_buffer_panel.py`, `manual_panel.py`, `about.py`, `icons.py`, plus the two off-GUI-thread helpers
`async_task.py` (`run_async(fn, on_result, on_error=None, pool=None)` — the executor behind MainWindow's
injectable `self._run_async`) and `busy.py` (`busy_status(status_bar, message)` context manager,
`format_size`).
**Target design, does not exist yet:** `ui/ddl_object_editor.py::DdlObjectEditorPanel` — the editable
single-object DDL tab (**specified once, in §18.5**), a distinct tab type from the read-only
`ddl_editor_panel.py::EditorPanel`, which stays read-only permanently.
(Deleted with the curated-XSD pivot, §11: `schema_learning/sync.py`, `schema_learning/merge.py`,
`ui/annotate_popover.py`, `ui/team_sync_dialog.py`, `ui/merge_conflicts_dialog.py`,
`ui/schema_viewer.py`, `ui/schema_viewer_data.py`.)

**Dependency rule:** `model/` touches lxml; nothing in `model/` or `ui/` depends on `diff/`; pure-logic
modules (`search`, `history`, `caption_scan`, `settings_index`, `xsd_load`, `xsd_verify`, `tier2`,
`analysis/*`, `type_map`, `from_table`, `xml_structure`, `sql/*`) are Qt-free and unit-testable without a
`QApplication`.

**`db/` is Qt-free with exactly one stated exception — `db/config.py`.** An earlier blanket claim that
`db/*` is Qt-free was **factually wrong** (see ledger, §28): `db/config.py` imports `QSettings` **at
module scope** (`from PySide6.QtCore import QSettings`, verified in the code) because the connection
store *is* QSettings, injected from MainWindow. That is `QtCore` only — no widgets, no `QApplication`
needed — and it is deliberate: the alternative is a second secrets/settings mechanism, which §17/§18.5
explicitly reject. Do **not** "fix" it by inventing a parallel store. The genuinely Qt-free `db/` modules
are therefore enumerated rather than assumed:

| `db/` module | Qt-free? | Status |
|---|---|---|
| `introspect.py`, `compare.py`, `rename.py`, `ddl_buffer.py` | yes | implemented |
| `apply.py`, `sandbox.py`, `ddl_check.py`, `ddl_project.py`, `schema_diff.py`, `migration_gen.py` | yes — **required** | target design (§18.5/§18.2/§18.3) |
| `config.py` | **no** — `QtCore.QSettings` at module scope | implemented; the one accepted exception |

The arrow points **ui → core, never core → ui**: `sql/` is the live, test-enforced
precedent — `ui/code_editor.py` imports `SQL_KEYWORDS` from `sql/keywords.py`, never the reverse, and
`tests/sql/test_package_purity.py` pins it (static AST scan for `PySide6`/DB/network/`pgtp_editor.ui`/
`pgtp_editor.db` imports **plus** a fresh-interpreter subprocess check that importing `pgtp_editor.sql`
loads no Qt module at all) — §18.4.

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
non-Raw-XML tabs hidden until invoked). Every one of those is a **fixed** tab, created in
`CenterStage.__init__` and addressed by a stored integer index (`raw_xml_tab_index`, `xsd_tab_index`,
`ddl_tab_index`, …), shown/hidden with `setTabVisible`.

> **Stated invariant — append-only creation, tail-only removal.** Runtime-created tabs (target design:
> the per-object DDL object editor tabs, §18.5, and §18.5's read-only deployment-script preview tab) are
> **always appended after the fixed set** (`addTab`, **never** `insertTab`) and removed only from the
> tail, and are addressed by a **key→widget map**, never a remembered index. This is not a stylistic
> preference: those **stored fixed indices are load-bearing in five places**, verified in the code —
> `main_window.py::_active_find_bar`, `_active_bookmark_editor`, `_save_active_tab` and
> `_on_ddl_navigate_requested` (all four compare `stage.currentIndex()` against `xsd_tab_index` /
> `ddl_tab_index`), plus **every** `CenterStage.hide_*`/`show_*` method (`hide_manual`, `hide_edit_xsd`,
> `hide_ddl_explorer`, `set_raw_xml_tab_visible`, `enter_caption_mode`/`leave_caption_mode`) and
> `_on_tab_close_requested`'s index dispatch. A
> single `insertTab` anywhere ahead of the fixed set silently re-points all of them. Because the
> invariant is otherwise implicit, **a regression test is mandatory, not optional**: open two dynamic
> tabs, close the first, and assert every fixed index still resolves to its original widget
> (`widget(raw_xml_tab_index) is raw_xml_tab`, …). `_on_tab_close_requested` gains a **first** branch
> that recognizes a dynamic tab by widget type and emits its close-request signal, *before* any
> static-index comparison.
>
> One convenient consequence and one trap. Convenient: `setTabsClosable(True)` is already global, so an
> appended tab gets its ✕ for free. Trap: the `_closable = (manual_tab_index, xsd_tab_index,
> ddl_tab_index)` loop that **strips** the ✕ from non-closable tabs runs **once, in `__init__`** — it
> never sees a runtime tab, which is exactly the behavior wanted, but it means the fixed set's closability
> is decided at construction and must not be recomputed later over a widened tab range.

Bottom is a
persistent **Audit/Problems** panel (`QListWidget`) shared by `[Schema]`, `[Validate]`, `[Find]`, `[PHP]`
lines. Three further prefixes are **reserved as target design and are reserved against each other in all
directions** — no feature may quietly annex another's prefix, and no fourth SQL-ish prefix may be added:

| Prefix | Owner | Reports |
|---|---|---|
| `[SQL]` | §18.4 formatter, hosted by §18.5's tab | **Format Selection refusals** — layout only, no DB involved |
| `[Check]` | §18.5 sandbox validation ladder | **SQL/plpgsql validation findings** (`db/ddl_check.py`) |
| `[Lint]` | §22 | **PHP** linting only (`php -l` / `phpcs`) |

Right dock is the **Properties** panel.

**Dock visibility is bidirectional (BUG-007).** In `_build_view_menu` each of the **three dock actions**
— "Project Tree" (`tree_dock`), "Properties Panel" (`properties_dock`), "Audit/Problems Panel"
(`audit_dock`) — is wired **both ways**: `action.toggled → dock.setVisible` **and**
`dock.visibilityChanged → action.setChecked`. Closing a dock via its title-bar ✕ (or any programmatic
hide/show) therefore keeps the menu checkbox honest. **No recursion guard is needed**: `QAction.toggled`
and `QDockWidget.visibilityChanged` only fire on *actual* state changes, so the pair settles immediately
(the same Qt signal-coalescing the `CenterStage` Manual-tab sync relies on). The other two View-menu
checkables are not docks and keep their one-way wiring: "Find table reference" drives
`_toggle_table_references` (a `left_tabs` tab, §15) and "Raw XML Panel" drives
`CenterStage.set_raw_xml_tab_visible` (a center tab).

**Document state:** `_dirty` + `_set_dirty()` (title gets " *"); editor `textChanged` marks dirty;
load/save/revert clears. **Theme toggles never dirty either document:** a theme change re-applies
character formats in **two stages** (BUG-013), and the `_applying_theme` guard wraps **every** batch of
both — never a single whole-document `rehighlight()`. `XmlEditor.apply_theme_colors` swaps the colors and
(coalescing repeated palette-change events via `_theme_rehighlight_pending` + the parented single-shot
`_theme_kickoff_timer`) schedules `_rehighlight_for_theme`, which (stage 1) `rehighlightBlock`s the
**visible region only**, inside the guard, so what is on screen recolors together with the app chrome;
it then starts `_theme_sweep_timer` (0 ms interval, parented) driving `_theme_sweep_tick`, which (stage 2)
sweeps the **rest of the document from block 0** at `_THEME_SWEEP_BLOCKS_PER_TICK = 400` blocks per
event-loop turn, each turn again wrapped in the guard, so a multi-MB document never freezes the UI. A
fresh theme change while a sweep runs restarts it from block 0 with the new colors. Every batch fires a
spurious `textChanged` with no text actually changed; MainWindow's dirty handlers for **both** the Raw XML
and Edit XSD editors consult `XmlEditor.is_applying_theme()` and no-op, and the editor's own
`textChanged` bookkeeping skips the format-only batches the same way (see the debounced structure rescan,
§8). `.bak` (single, overwritten, `shutil.copy2`) is written before overwriting an
existing file on save — never on Save-As to a new path, never on a failed/no-op write.
`_write_project_text(path)` writes editor `toPlainText()` as UTF-8 with `newline=""` (byte-preserving).
`_current_project_path` is normalized to `str`.

**Per-tab document routing** (curated-XSD pivot, §11): the Edit XSD tab hosts a second document with
its **own dirty state** (tab-title `*` marker, independent of the project's `_dirty`). The Edit-menu
Find/Replace actions (Find/Find Next/Find All/Replace/Replace All) route to the **active** center-stage
tab's `FindReplaceBar` via `main_window.py::_active_find_bar()`, which dispatches on
`center_stage.currentIndex()`: **Edit XSD/Edit AutoXSD tab** → `stage.xsd_find_replace_bar` (the
mode-aware XSD document, curated.xsd or learned.xsd per `_xsd_mode`, §11); **DDL Explorer tab** →
`stage.ddl_editor_panel.find_replace_bar` (the read-only DDL buffer's own bar, §18.1 — without this
branch Ctrl+F on the DDL tab bounced the user back to Raw XML); **the active DDL object editor tab**
— **target design, not yet implemented (§18.5)** — its own bar, where Replace is **live** rather than
inert; **any other tab** → reveal Raw XML (`_reveal_raw_xml_tab()`) and return `stage.find_replace_bar`.

**Ctrl+S routing.** `main_window.py::_save_active_tab()` routes Edit-XSD-vs-project today (XSD tab →
`_save_xsd()`, everything else → `_save_project()`), and — **target design (§18.5)** — gains a branch
for the active **DDL object editor tab**, persisting its text through the tab's *injected save callback*
(the live-object buffer in v1, the checked-out `ddl/*.sql` file once §18.2 exists). **Ctrl+S there is
`Save` only:** it **never executes anything against a database** — pushing DDL to a database is the
separate, explicitly confirmed **Apply** gesture (§18.5), never implied by a save and never automatic.
The read-only DDL Explorer buffer keeps **no** save branch at all — it is DB-synthesized and has no save
path, the deliberate asymmetry against `_active_find_bar`, which *does* branch for it. Project-level
state (`.bak`, `_current_project_path`, reparse) is untouched by XSD-tab and DDL-object-tab saves.

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

**Highlighting** (`XmlSyntaxHighlighter`): four categories (delimiters/names, attribute names, values,
text), applied by the unchanged module regexes `_TAG_OPEN_RE` / `_TAG_CLOSE_RE` / `_ATTR_NAME_RE` /
`_ATTR_VALUE_RE`; **quoted-value state is propagated across blocks via Qt block state, and that state is
tag-aware** (BUG-016).

- **Four block states**, module-level constants in `ui/xml_editor.py`: `STATE_NORMAL = 0` (text content,
  outside any tag), `STATE_IN_UNCLOSED_STRING = 1` (inside a double-quoted attribute value),
  `STATE_IN_TAG = 2` (inside `<…>`, not inside a value), `STATE_IN_SINGLE_QUOTED = 3` (inside a
  single-quoted attribute value). `highlightBlock` coerces any other `previousBlockState()` (including
  Qt's `-1`) to `STATE_NORMAL`.
- The end state is computed by the method `XmlSyntaxHighlighter._end_state(text, state)`, which iterates
  **only the state-changing characters** found by the module regex
  `_STATE_CHARS_RE = re.compile(r"""[<>"']""")` — one C-speed pass yields a handful of matches per line
  instead of a Python loop over every character.
- **A quote only opens a value INSIDE a tag.** In text content — where `.pgtp` keeps its PHP
  event-handler bodies, full of quotes and apostrophes — quotes are ordinary characters and never change
  the propagated state. (Inline `"…"` pairs in text content are still string-colored by
  `_ATTR_VALUE_RE`; only the *propagated state* is tag-aware.)
- **Resync rule (the rule that bounds the cascade):** while inside a quoted value, a raw `<` resyncs the
  state to `STATE_IN_TAG`, because `<` cannot appear inside a well-formed attribute value (it must be
  `&lt;`). Without it an unterminated quote inside a tag still flips every following block's state to
  EOF; with it the next tag snaps the state back and the cascade stops after a block or two. Documented
  trade-off: a raw `<` typed inside an attribute value ends that value's highlighting early — acceptable,
  since such a document is invalid XML and it self-corrects once the quote is closed or the `<` escaped.
- A value continued from the previous block is coloured up to `_continued_string_end(text, quote)` — past
  the closing quote, at a raw `<` (the same resync), or end of line — and the four formatting regexes are
  then applied **from that offset on**.
- `_end_state` and `_continued_string_end` are **methods on `XmlSyntaxHighlighter`, deliberately** (not
  module functions), so `debuglog.py`'s `("ui.xml_editor", "XmlSyntaxHighlighter.")` qualname-prefix
  flood exclusion keeps covering them.
- Superseded: the old rule was `_has_unterminated_quote(text, start)` = *odd count of `"` on the line*.
  Parity never re-synchronised, so one parity-flipping `"` flipped every following block's state in turn
  and Qt cascaded a re-highlight **to the end of the document** on every such keystroke (measured: 5,972
  `highlightBlock` calls / 45 ms on a 6,002-block file). That helper no longer exists.

**Debounced structure rescan** (BUG-015). The structure rescan (`_rescan_structure`) and the
code-region rebuild (`_refresh_code_region_selections`) are each **O(document)** — a full
`toPlainText()` copy plus a whole-document pass — and are **no longer connected to `textChanged`
directly**. Both run behind a **parented single-shot** `self._rescan_timer = QTimer(self)` with
`_RESCAN_DEBOUNCE_MS = 250` (same debounce shape as MainWindow's ~400 ms snapshot-history timer, §7, and
the 400 ms auto-parse timer, §9). Never `QTimer.singleShot` — an unparented timer fires on an
already-deleted editor (BUG-014).

- `textChanged` → `_on_text_changed_schedule_rescan()`, which absorbs the `_applying_theme` skip
  (format-only theme sweeps change no characters, so spans/code-regions cannot differ — nothing is even
  scheduled) and otherwise (re)starts the timer.
- `_rescan_now()` executes the work in order: structure → code regions → matching-tag highlight →
  `self._gutter.update()` (fold glyphs are derived from `_spans`).
- Measured on a 1 MB / 21,002-block document: plain typing **216.1 → 2.0 ms per character**.
- **`_update_matching_tag_highlight` (on `cursorPositionChanged`) must NOT rescan when it finds `_spans`
  stale** — it **suppresses** the matching-tag highlight (clears `_matching_tag_selections`, refreshes,
  returns) and lets `_rescan_now` re-invoke it a few hundred ms later. This is load-bearing: typing moves
  the caret, so a rescan-if-stale on the cursor path would have run the full scan per keystroke and
  defeated the debounce entirely. It is also the correct rendering: while stale, the cached spans' offsets
  refer to the **pre-edit** text, so highlighting from them would paint a visibly wrong range — worse
  than none.
- **Two consumers must see exact structure and therefore bypass the debounce:** `setPlainText` is
  overridden to call `_rescan_now()` **synchronously** (a document *swap* — file load, revert, rename
  write-through — whose callers read spans/fold regions/code regions immediately), and `_toggle_fold` is
  overridden to call `_flush_pending_rescan()` (runs `_rescan_now()` only if the timer is active) before
  deferring to the shared mixin. **Design constraint / non-obvious trap:** the flush deliberately does
  **not** live in `_foldable_region_starting_at` — the gutter's `paintEvent` calls that hook for every
  visible block, so rescanning there would fire on every repaint (i.e. every keystroke) and silently undo
  the whole debounce.

**Folding:** driven by the (debounced) `scan()` results cached in `_spans`; one foldable region per
multi-line non-self-closing span; `QTextBlock.setVisible()`; `_fold_state: dict[int,bool]`; reset on
`setPlainText`. Folding only hides rendering — the character stream is intact, so copy/cut of a folded
block yields the **full** underlying text (a hard requirement; tested with nested folds).

**Gutter (`_EditorGutter`, `ui/editor_gutter.py`)** — three zones left to right: a 12px **bookmark strip**
(`_BOOKMARK_STRIP_WIDTH = 12`), a 16px **fold-glyph zone** (`_FOLD_GLYPH_WIDTH = 16`), then the
right-aligned **line-number area**. `mousePressEvent` routes by `event.position().x()`: a click in the
bookmark strip toggles that line's bookmark (`self._editor.toggle_bookmark(block.blockNumber())`), a
click in the fold zone toggles that line's fold (`self._editor._toggle_fold(block)`); a **single** click
in the line-number zone is a no-op.

**Target design, not yet implemented — double-click on the line number also toggles a bookmark**
(settled 2026-08-01; a second, larger click target for the same toggle, alongside the existing 12px
strip): the block-lookup loop currently duplicated inside `mousePressEvent` is to be extracted into a
shared helper `_EditorGutter._block_at_y(click_y) -> QTextBlock | None`; a new `mouseDoubleClickEvent`
handler then checks `event.position().x() >= _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH` (i.e. the
line-number zone), and if so calls `toggle_bookmark` on `_block_at_y(event.position().y())` and repaints
the gutter. Purely additive: the single-click no-op in the line-number zone is unchanged.

**Shared gutter / bookmark / fold base (implemented — `ui/editor_gutter.py`, reused by every
`CodeEditor` incl. the DDL editor, §18.1):** the gutter (`_EditorGutter`), the bookmark set +
`toggle_bookmark`/`bookmarked_lines`/`next_bookmark`/`prev_bookmark`/`clear_bookmarks` (all
**block-number based**, hence generic), the **fold-state** machinery (`_fold_state`, `_toggle_fold`,
`_is_line_hidden_by_other_collapsed_fold`), the gutter width/geometry plumbing and the theme-aware
gutter colors (`_GUTTER_COLORS_DARK`/`_GUTTER_COLORS_LIGHT`, `_apply_gutter_theme_colors`) are **generic
to any `QPlainTextEdit`** and live in the **new module `ui/editor_gutter.py`** — a separate module
rather than a base inside `xml_editor.py`, so `code_editor.py` need not import from the ~1900-line
XML-specific module.

- The shared piece is a **mixin**, `GutterBookmarkFoldMixin`, not a base class: hosts declare it
  **before** `QPlainTextEdit` (`class XmlEditor(GutterBookmarkFoldMixin, QPlainTextEdit)`, likewise
  `CodeEditor`) so the mixin's `setPlainText`/`resizeEvent` sit ahead of Qt's in the MRO.
- The mixin deliberately has **no `__init__`**; each host calls `_init_gutter_bookmarks_folding()`
  explicitly from its own `__init__` after `super().__init__(parent)`. This is why no existing
  constructor ordering had to be inverted.
- Only the **foldable-region provider is pluggable**: the mixin calls
  `_foldable_region_starting_at(block)` → `(first_contained_block, last_contained_block)` (0-based) or
  `None`; the mixin's default folds nothing. `XmlEditor` overrides it with the **XML-span** provider
  (over `_spans`/`TagSpan`); `CodeEditor` overrides it with a lookup into regions installed from outside
  via `set_fold_regions(regions)` (see §8 "Code editor" below and §18.1).
- `ui/xml_editor.py` **re-exports** `_EditorGutter`, `_BOOKMARK_STRIP_WIDTH` and `_FOLD_GLYPH_WIDTH` so
  pre-existing importers (and tests) keep working unchanged, and re-declares **none** of the nine moved
  methods.

There is exactly **one** `class _EditorGutter` and **one** gutter `paintEvent` in the package — never a
second, near-duplicate gutter.

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
of the enclosing element are highlighted (self-closing → none), using the revision-guarded `_spans`
cache — which is refreshed by the **debounced** rescan above, so while the cache is stale the highlight
is **suppressed rather than recomputed** (see "Debounced structure rescan"). **Ctrl+click** jumps
between matching open/close tags; **Alt+click**
jumps to the parent element's open tag (both move caret + scroll, no selection; `event.accept()`
suppresses Qt's Alt-drag). Other modifier combos fall through.

**Right-click context menu:** `contextMenuEvent` first moves the caret to the actually-clicked
document position (`_prepare_context_menu_at(doc_pos)`) before building the menu, so
position-dependent entries (e.g. "Go To XSD", §11) reflect the clicked location rather than a
stale caret. **Selection right-click ▸ "Find"** prepends to the standard context menu when a selection
exists; emits `find_selected_text(str)` → MainWindow reveals Raw XML + prefills the Find bar.
**Line-wrap** toggle lives in the editor's right-click context menu (checkable), not the View menu.

**Bookmarks** (session-only, per-document; carried by **every** editor that mixes in
`GutterBookmarkFoldMixin` — `XmlEditor` *and* every `CodeEditor`, see "Gutter on every code editor"
below): `self._bookmarks: set[int]` (block numbers), reset on
`setPlainText`; `toggle_bookmark(block_number)`, `bookmarked_lines()` (sorted ascending),
`next_bookmark(from_line)`/`prev_bookmark(from_line)` (nearest strictly-after/-before, wrap-around,
`None` when empty), `clear_bookmarks()`, plus cursor-line wrappers `toggle_bookmark_at_cursor()` and
`goto_next_bookmark()`/`goto_prev_bookmark()` (center the target line). Rendered by
`_EditorGutter._draw_bookmark_tag` as an accent-colored (`_bookmark_color()`, theme-aware) rounded tag
in the gutter's bookmark strip — toggled by a single click in the strip, and (target design, not yet
implemented — see above) by a double-click in the line-number zone. **Bookmarks menu**
(`main_window.py::_build_bookmarks_menu`, top-level menu bar, between Tools and Generation — §26): Toggle
Bookmark (Ctrl+F2 → `toggle_bookmark_at_cursor`), Next Bookmark (F2 → `goto_next_bookmark`), Previous
Bookmark (Shift+F2 → `goto_prev_bookmark`), separator, Clear All Bookmarks (no shortcut →
`clear_bookmarks`). **The menu follows the active editor tab** (settled 2026-08-01): `_build_bookmarks_menu`
captures **no** editor at build time; each of the four actions is connected to a lambda that resolves its
target at **trigger** time via `main_window.py::_active_bookmark_editor()` — Edit XSD tab →
`stage.xsd_editor`, DDL Explorer tab → `stage.ddl_editor_panel.editor`, any other tab → `stage.xml_editor`.
This mirrors `_active_find_bar`'s per-tab dispatch with **one deliberate difference: it does NOT reveal /
switch to the Raw XML tab** as a fallback side effect (`_active_find_bar` calls `_reveal_raw_xml_tab()`;
this must not), because toggling a bookmark may never yank the user to a different tab; a non-editor tab
simply falls back to the Raw XML editor. The dispatch is the *only* thing needed, because
`GutterBookmarkFoldMixin` puts the identical bookmark API on all three editors. The **"Edit code…"
`CodeEditorDialog` is a separate dialog, not a center-stage tab**, so the main window's Bookmarks menu does
not reach it — its gutter bookmark strip stays mouse-only. Out-of-range block numbers
are ignored defensively. No persistence, no list panel, no names.

**Bookmarks menu is disabled during Caption Mode** (target design, not yet implemented; settled
2026-08-01 — see §13): `_build_bookmarks_menu` is to store the menu as `self._bookmarks_menu` and each
of its four actions as attributes, so `_enter_caption_mode`/`_close_caption_mode` can `setEnabled(False
/ True)` the menu **and every child action together** — disabling only the `QMenu` grays out the
menu-bar entry but does not disable the actions' keyboard shortcuts in Qt (the same reason
`_editor_find_action`/`_editor_replace_action` are disabled individually today, not just their menu).
**Gutter bookmark toggling (single-click strip and the planned double-click on the line number) is
explicitly NOT gated by Caption Mode** and stays usable — bookmarks are a UI overlay independent of the
read-only editing state; only the Bookmarks menu (and therefore its shortcuts) is gated.

**Event-handler code styling & editing:** event-body line ranges (`event_body_line_ranges(text)`) get a
distinct background + monospace and work read-only (Caption Mode). A gutter marker / "Edit code…"
context action opens `CodeEditorDialog` (below) with the body and `language_for_side(side)`; on save,
pure `replace_event_body(text, start_line, new_code)` swaps inner content preserving tags/indentation.

**Code editor** (`ui/code_editor.py`): `CodeEditor(GutterBookmarkFoldMixin, QPlainTextEdit, language)` — monospace,
per-language `_CodeHighlighter` (JS / PHP / SQL keyword sets, strings, `//`+`#` line comments, `/* */`,
numbers), auto-close + selection-wrap for `()[]{}`/quotes, **Ctrl+Shift+B** bracket-select via pure
`enclosing_bracket_span(text,pos)`. The **`language="sql"`** mode (added for the DDL Explorer, §18.1)
uses `_SQL_KEYWORDS` (stored lowercase; matching is **case-insensitive** — `pg_get_functiondef` emits
uppercase, hand-written bodies vary), `--` line comments, single-quoted strings with `''` doubling
(double-quoted text is an identifier, left unstyled), and the shared `/* */` block comments.
That keyword set is **not defined in `ui/`**: it lives in the Qt-free core as
`pgtp_editor/sql/keywords.py::SQL_KEYWORDS` (a `frozenset` of 115 lowercase members) and
`code_editor.py` does `from pgtp_editor.sql.keywords import SQL_KEYWORDS` then binds
`_SQL_KEYWORDS = SQL_KEYWORDS` — a plain re-bind of the **same object**, so the existing
`_highlighter._keywords is _SQL_KEYWORDS` assertions still hold. It is therefore the **one shared
dialect source** for both the highlighter and the SQL/plpgsql selection formatter (§18.4): extend the
dialect in `sql/keywords.py` and both consumers see it, and the two can never disagree on what counts as
a keyword.
`CodeEditor` also exposes `navigate_to_line(line)` (1-based; the same public navigation entry point
`XmlEditor` exposes, used by the BrowserPanel → EditorPanel jump, §18.1). In its **`language="sql"` DDL
mode** navigation is **top-aligned** (the target line lands at the top of the viewport, not centered) —
overriding the earlier `centerCursor()` — so a clicked DDL object's banner sits at the top with its body
below (§18.1); every other language keeps `centerCursor()`, and `XmlEditor.navigate_to_line` stays
centered. Top-alignment is `_scroll_line_to_top(block)`: it drives the **vertical scrollbar**, whose
values count **visible** blocks in a `QPlainTextEdit` (via `_visible_block_offset`), so a *collapsed
fold above the target does not overshoot*, and it clamps to `[bar.minimum(), bar.maximum()]` so a target
near EOF simply scrolls to the bottom rather than being rejected. A **4-character tab stop**
(`_SQL_TAB_STOP_CHARS = 4`, `setTabStopDistance(4 × mono-char-advance)`) is likewise applied **only** when
`language == "sql"` (§18.1).

**Gutter on every code editor (deliberate, 2026-08-01).** Because the shared mixin sits on `CodeEditor`
itself rather than on a DDL-only subclass, the **JS/PHP "Edit code…" event-handler dialogs
(`CodeEditorDialog`) also get the line-number gutter and line bookmarks**. Folding is **inert** there:
no host installs fold regions, `_fold_regions` stays empty, and the default provider returns `None`, so
the fold zone simply never draws a glyph. This side effect was surfaced to the project owner, who
**explicitly chose to keep it** rather than gate the mixin per language: line numbers in a code editor
are conventional, and gating would add a second code path through the one gutter implementation.
Foldable regions are installed from outside via `CodeEditor.set_fold_regions(regions)` — an iterable of
`(start_block, first_contained_block, last_contained_block)` triples, all **0-based** — which replaces
any previous set and **drops `_fold_state`** (old block numbers no longer mean anything). `CodeEditor`
also exposes
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
- **Reparse** — `_reparse_raw_xml(silent: bool = False)`: `load_project_from_text(editor_text)`; on
  success (shared by every caller, manual or automatic) repopulate tree, set `_current_project`, refresh
  the Table References panel if visible, clear Properties, show a status-bar confirmation, and refresh
  the Database Check panel if open (`_refresh_db_check_if_open`). On `PgtpParseError` the two modes
  diverge, both **preserving** the existing model/tree (neither re-reads the file nor touches the path):
  - `silent=False` (**Tools ▸ "Reparse Raw XML into Tree"**, the manual, explicit path) —
    `_handle_reparse_failure`: `QMessageBox.critical` + `highlight_error_line` jump to the error line.
  - `silent=True` (**auto-parse**, below) — no modal, no cursor jump; a transient status-bar message
    only ("Auto-parse: XML not well-formed yet — tree not updated"), leaving the tree in its last-good
    state.

  Reparse is the resync after manual edits, caption apply, code write-back, or create-from-table
  insertion — either explicitly triggered or, when auto-parse is enabled, automatically debounced off
  editor changes.

**Auto-parse XML** (Edit ▸ "Auto Parse XML", checkable, **off by default**, in-memory only — no
QSettings persistence, so it always starts unchecked on launch): when enabled, the app listens to
`XmlEditor.blockCountChanged` (a `QPlainTextEdit` signal that fires once whenever the document's line
count changes — Enter, multi-line paste, Ctrl+X, or Delete/Backspace joining lines — not once per line)
and, after a 400 ms debounce (`self._auto_parse_timer`, a singleShot `QTimer` mirroring the existing
`_snapshot_timer` debounce used for undo/redo history, §7), calls `_reparse_raw_xml(silent=True)`. The
timer restarts on each successive `blockCountChanged` firing (e.g. a held-down key), so it fires once
after the burst of edits settles rather than on every keystroke. Both the signal handler
(`_on_editor_block_count_changed`) and the debounced callback (`_auto_parse_now`) no-op whenever
`self._loading or self._restoring` is true or the toggle is off — the same guard flags that already gate
snapshot-history capture, so auto-parse never fires during programmatic text sets (file open, revert,
undo/redo restore). No Caption Mode gating is needed: the Raw XML editor is read-only while in Caption
Mode, so `blockCountChanged` cannot fire from user typing there. The manual Tools-menu action is
unaffected by the toggle and always uses `silent=False`.

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
`_enter_caption_mode`/`_close_caption_mode` gate individual `QAction`s (never just their parent menu, so
the underlying keyboard shortcut is actually disabled too): today the Raw XML editor's Find…/Replace…
actions (`_editor_find_action`/`_editor_replace_action`); target design (2026-08-01, not yet
implemented, §8) extends the same pattern to the **Bookmarks menu and its four actions**
(`self._bookmarks_menu` + Toggle/Next/Previous/Clear All), since Caption Mode's read-only editor makes
line-anchored bookmark navigation ambiguous alongside caption-grid navigation — but **not** to gutter
bookmark toggling itself, which stays a click-driven overlay independent of read-only state.

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
(Ctrl+R), Replace All (Ctrl+Alt+Return). Each handler routes through
`main_window.py::_active_find_bar()` to the **active** center-stage editing tab's `FindReplaceBar` — Edit
XSD tab → `stage.xsd_find_replace_bar`, **DDL Explorer tab → `stage.ddl_editor_panel.find_replace_bar`**
(§18.1), any other tab → reveal Raw XML and use `stage.find_replace_bar` (§7 per-tab routing) — and
delegates to the same `FindReplaceBar` method the button uses. The Edit XSD tab and the DDL Explorer tab
each host their own `FindReplaceBar` instance; the Edit XSD one has full Find All parity (the DDL buffer
is read-only, so its Replace path no-ops via `CodeEditor.replace_current_selection`, §8). (The old
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
  `seed_params`. **Not Qt-free** — it imports `QtCore.QSettings` at module scope, the one stated
  exception to §5's `db/` rule. Today it hardcodes a single QSettings group, `_GROUP = "db"`.

**Connection profiles — one keying scheme for both dimensions (target design, §18.2 + §18.5).** §18.2
needs a **per-project** key; §18.5 D2 needs a **profile role** (`target` | `sandbox`). These land as
*one* mechanism, never two:

| Piece | Contract |
|---|---|
| `ProfileKey(project: str = "", role: str = "target")` (frozen dataclass), `DEFAULT_PROFILE = ProfileKey()` | The single key type. Both dimensions, one value. |
| `_group_for(key) -> str` | `key == DEFAULT_PROFILE` → **the literal string `"db"`**, byte for byte the existing group. Otherwise `"db_profiles/<slug(project)>/<role>"`, where `slug` = `sha1(path.casefold())[:16]` (`""` → `"_global"`) because a QSettings group name cannot contain `/` or `\`. |
| `load_connection(settings, key=DEFAULT_PROFILE)`, `save_connection(settings, params, key=DEFAULT_PROFILE)`, `seed_params(tree, settings, key=DEFAULT_PROFILE)` | A **trailing defaulted** parameter on each; every existing call site keeps working unchanged. |

- **The compatibility trick is load-bearing and must be preserved:** routing the default profile back to
  the *same* `"db"` group means existing users' saved connections are **not migrated at all** — there is
  nothing to migrate, nothing to get wrong, and an older build still reads them. **Every existing test in
  `tests/db/test_config.py` (9 as of 2026-08-02) must pass unedited**; that is itself the compatibility
  proof, and new tests may only be *added*. This is why the scheme beats read-fallback-plus-dual-write.
- **`seed_params` for a `role="sandbox"` key must NOT fall back to the project's `<ConnectionOptions>`.**
  That element describes the **target** database; seeding the sandbox profile from it is exactly how
  someone ends up pointing "the sandbox" at production. Sandbox seeding = saved settings only, else
  blanks with a `localhost`/`5432` default.
- Loaders keep the existing contract: an absent or garbage group returns `None` and **never raises**.
- Two profiles means **two plaintext passwords** in QSettings — the existing plaintext caveat label must
  be shown for the sandbox profile too, and a *superuser* sandbox password (needed for one-click
  `CREATE EXTENSION`, §18.5) is a trade the user must be shown, not assumed to have accepted.
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

**DB Check results are project-tied and torn down on project close (BUG-011).** `_close_project`, on the
**committed-close path only**, hides the "Database Check" `left_tabs` tab
(`left_tabs.setTabVisible(db_check_tab_index, False)`) and clears the three cached fields
(`_last_db_check_direction` / `_last_db_schema` / `_last_db_summary` → `None`), so a later reparse or
rename cannot re-run against the closed project's stale state. A **cancelled** close returns before this
and leaves the still-open project's tab alone; `_revert_project` keeps the project loaded and so does not
tear down.

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
> **The 2026-08-01 §18.1 enhancement batch is also implemented and verified** (it was specified here
> ahead of implementation and has now landed): (a) editor affordances on the DDL `EditorPanel` — the
> line-number gutter, line bookmarks and code folding, via the **shared `GutterBookmarkFoldMixin` in the
> new module `ui/editor_gutter.py`** with its pluggable foldable-region provider (§8); (b) the
> **4-character** tab stop; (c) the revised BrowserPanel tree presentation — fully-qualified
> `schema.name`, the three-way `[F]`/`[P]`/`[T]` marker, per-argument `name (type)` children (backed by
> the new `RoutineInfo.args`), and composite trigger leaves with bracketed timing/event indicators; and
> (d) **top-aligned** DDL navigation. See the Supersession Ledger (§28) for each override.
>
> Still not built: `db/routine_refs.py` (XML cross-referencing — **the one remaining §18.1 piece**), and
> `db/schema_diff.py`/
> `db/schema_snapshot.py`/`db/migration_gen.py` (§18.3); those parts of this section remain target
> design, settled before implementation starts.
>
> **§18.4's SQL/plpgsql selection formatter core is implemented (2026-08-01); its consumer is now
> designed (2026-08-02) but not built.** The Qt-free package `pgtp_editor/sql/`
> (`__init__.py`/`keywords.py`/`issues.py`/`tokenizer.py`/`formatter.py`) and its mirror `tests/sql/`
> exist and are green; **nothing calls `format_selection` yet**. What changed on 2026-08-02 is that the
> host surface is no longer undesigned: the **DDL object editor** — the editable, per-object tab
> `ui/ddl_object_editor.py::DdlObjectEditorPanel` — is fully specified in **§18.5**, together with the
> **`Ctrl+Alt+F` / context-menu "Format Selection"** trigger (§26/§27 now carry the binding) and the
> **`[SQL]`** Audit-panel prefix for refusals. All of that is **target design**: no code exists for the
> tab, and the Audit-panel reporting path is still a **contract, not wiring**.
>
> **§18.5 (settled design 2026-08-02, not yet implemented)** specifies that editable tab **once**,
> together with the only thing that can give it a feedback loop: a **stateful, app-provisioned sandbox
> database** and a validation ladder over it. New modules: `db/apply.py` (the codebase's **first DB write
> path**), `db/sandbox.py`, `db/ddl_check.py`, `db/schema_diff.py`, `db/migration_gen.py`,
> `ui/ddl_object_editor.py`. The tab is deliberately **decoupled from §18.2's git project for v1** — no
> `ddl/` folder, no `deployed.json`, no `*`/`!` markers — and is written against an **injected load/save
> pair** so §18.2 layers on later by swapping only where the buffer loads from and saves to.
> **§18.5's headline deliverable is the generated deployment SQL script**, not the editable tab: the
> sandbox is the *desired state*, production is the *current state*, and the output is one reviewed
> migration script run once to upgrade the real database. See §18.5's ranked outputs.

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

Five parts. **Section order is not build order** — the numbering is historical and other documents
reference it, so it is kept stable:

| Part | Scope | Depends on |
|---|---|---|
| **§18.1** | Browses live routines/triggers in one synthesized read-only buffer (unchanged in shape from the original DDL Explorer design) | — (implemented) |
| **§18.5** | The **stateful sandbox as desired state**, the **generated deployment SQL script** (its headline deliverable), the validation ladder, and the **editable single-object DDL tab** (`ui/ddl_object_editor.py::DdlObjectEditorPanel`) with its Save/Apply gestures. **The editable tab is specified here and only here.** | §18.1 only — explicitly buildable **before** §18.2/§18.3 |
| **§18.2** | The "project" concept (git repo, `ddl/*.sql` file-per-object, `.ddlproject/` manifests), checkout-to-edit, and the `*`/`!` state markers. Adds **no new tab type**: it swaps §18.5's tab's injected load/save pair and adds marker rendering. | §18.1, §18.5 |
| **§18.3** | The reviewed **batch** deploy workflow, reusing §18.1's browsing UI and the shared diff/migration engine originally specified as a schema-compare-only tool | §18.2 |
| **§18.4** | The Qt-free SQL/plpgsql selection formatter core (implemented), whose one host surface is §18.5's tab | §18.5 for its consumer |

**Build order is therefore §18.1 → §18.5 → §18.2 → §18.3.** §18.5 was deliberately re-scoped to sit
before §18.2: a git project, a manifest, a hash scheme and a marker recompute is a large prerequisite to
place in front of "edit one function and find out whether it compiles" (§18.5 D1, §28).

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
  (input argument name+type pairs — IN/INOUT/VARIADIC — in declared order)**, return_type, language, source,
  kind("function"|"procedure")}` sourced from `pg_proc` joined `pg_language`, with source text
  via `pg_get_functiondef(oid)`. `arg_types` (types only) is **retained** — it still feeds
  `build_ddl_text`'s banner comment (`-- FUNCTION schema.name(argtypes) --`); the `args` field adds
  the **argument names** the BrowserPanel tree needs (see tree presentation below).
  `_ROUTINES_SQL` was widened to select, alongside the existing `proargtypes`-derived `arg_types`:
  `COALESCE(p.proallargtypes, p.proargtypes::oid[])` run through `format_type` (ordinality-preserved),
  `p.proargnames`, and `p.proargmodes::text[]`. Those three **parallel arrays are correlated in Python**
  by the pure helper `_input_args(all_arg_types, arg_names, arg_modes) -> list[tuple[str, str]]` —
  deliberately not in SQL, for the **same reason `_decode_trigger_type` is in Python: the correlation is
  unit-testable without a live database**. Rules: an absent/NULL `proargmodes` reads as all-IN (Postgres
  omits it in the common case); the kept modes are exactly the **arguments the caller passes in** —
  `_INPUT_ARG_MODES = frozenset("ibv")`, i.e. `i` (IN), `b` (INOUT) and `v` (**VARIADIC**) — while `o`
  (OUT) and `t` (TABLE) entries, which are outputs, are dropped. VARIADIC is kept deliberately: a
  variadic parameter is supplied by the caller, so excluding it silently hid a real parameter of e.g.
  `f(fixed int, VARIADIC rest text[])` from the tree.
  An unnamed argument yields `""` as its name; a routine with zero input arguments has
  `args == []`. `TriggerInfo{schema,
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
  **`language="sql"` mode** — the SQL/plpgsql `_CodeHighlighter` branch (case-insensitive
  `_SQL_KEYWORDS` matching — the keyword set itself lives in the Qt-free `sql/keywords.py`, §18.4 —
  `--` line comments, `''`-doubled single-quote strings, `/* */` block
  comments) added alongside the existing JS/PHP ones in that same file (§8). Has its own
  `FindReplaceBar` instance, following the same per-tab document-routing precedent as the Edit XSD tab
  (§7/§15) and the planned Custom PHP tabs (§21). The tab sits in `CenterStage` between Edit XSD and
  Manual (`ddl_tab_index`, hidden by default), and is **closable** via a tab-bar ✕ that hides it
  directly (`hide_ddl_explorer()`) — read-only, so unlike Edit XSD there is no dirty prompt to route
  through. `CenterStage` exposes `show_ddl_explorer()`/`hide_ddl_explorer()` and a
  `ddl_explorer_visibility_changed = Signal(bool)`. API: `EditorPanel.set_ddl_text(text, spans=None)`
  (a fresh `build_ddl_text` result — text plus its `DdlObjectSpan` list, which drives the fold regions,
  below; today the spans are converted to fold regions and then **dropped** — **target design (§18.5):
  the panel must additionally retain the span list** (e.g. `self._spans`), because the right-click ▸
  Edit entry point resolves the clicked line to the object whose `start_line..end_line` contains it)
  and `EditorPanel.navigate_to_line(line)` (delegates to
  `CodeEditor.navigate_to_line`, §8, then focuses the editor). This tab is **read-only, DB-sourced,
  live/synthesized** (`editor.setReadOnly(True)`; `CodeEditor.replace_current_selection` no-ops on
  read-only editors, the guard that actually protects the buffer since `QTextCursor` edits bypass
  `setReadOnly`) — and it is read-only **permanently, not provisionally**. The editable form is a
  **separate tab type**, the per-object DDL object editor of §18.5 (loading from the live introspected
  definition in v1, from the checked-out `ddl/*.sql` file once §18.2 exists). Nothing is ever pushed to a
  database from `EditorPanel`.
- **Implemented — editor affordances (parity with the Raw XML editor's `XmlEditor`, via the shared
  mixin — §8):** the DDL `CodeEditor` carries the **same three affordances `XmlEditor` has**: (i) a
  **line-number gutter**, (ii) **line bookmarks**, and (iii) **code folding**, all from
  `ui/editor_gutter.py::GutterBookmarkFoldMixin` (see §8) — **one** gutter/bookmark/fold implementation
  used by both editors, never a second parallel gutter. The mixin supplies the generic,
  block-number-based gutter + bookmark set + fold-state machinery; the **foldable-region provider is
  pluggable**. For the DDL buffer the foldable regions are **one per DDL object body**:
  `ddl_editor_panel.py::_fold_regions_for_spans(spans)` (pure) translates each `DdlObjectSpan` into the
  triple `(start_line - 1, start_line, end_line - 1)` — fold triggered on the **banner** block,
  containing the **body only**, so the banner stays visible when collapsed; a span with
  `end_line <= start_line` contributes **no** region. `EditorPanel.set_ddl_text(text, spans=None)` takes
  that span list alongside the text and installs the regions via `CodeEditor.set_fold_regions`; passing
  `None`/`[]` simply leaves nothing foldable. `XmlEditor` keeps its **XML-span** fold provider
  (`_foldable_region_starting_at` over `_spans`/`TagSpan`, §8).
- **Implemented — tab stop = 4 characters.** `CodeEditor` sets `setTabStopDistance(4 × mono-char
  advance)` (`_SQL_TAB_STOP_CHARS = 4`) when `language == "sql"`, overriding Qt's monospace default
  (~8–11 chars) so `pg_get_functiondef`'s tab-indented bodies read at a sane width.
- **Implemented — top-aligned navigation.** `EditorPanel.navigate_to_line(line)` scrolls so the target
  line lands at the **top** of the editor viewport (not centered) — the clicked DDL object's banner sits
  at the top edge, so the whole object is visible below it. This is **DDL-specific**: gated on
  `language == "sql"` inside `CodeEditor.navigate_to_line`, so JS/PHP `CodeEditor`s and
  `XmlEditor.navigate_to_line` all keep `centerCursor()` (Properties/tree-jump callers expect
  centering). See §8 for `_scroll_line_to_top`'s visible-block counting and scrollbar clamping.
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
`_add_trigger_leaf`) — implemented; the exact rendered labels (both worked examples below are
test-asserted byte-for-byte):**

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
- **Argument child leaves carry no span** (`_SPAN_ROLE` unset), so clicking one navigates nowhere —
  `_on_item_clicked` only emits `navigate_requested` when the clicked item has a span. Routine leaves
  and both trigger occurrences carry theirs.
- **Child order under a routine:** argument leaves first (declared order), then the triggers that invoke
  the routine, **sorted by trigger name**. Routines themselves are sorted by `(schema, name)`.

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
  window). On result: `text, spans = build_ddl_text(schema)` → `EditorPanel.set_ddl_text(text, spans)` +
  `BrowserPanel.set_schema(schema, spans)` + `show_ddl_explorer()` + a status-bar summary
  (`DDL Explorer: N routine(s), M trigger(s).`).
- **Standalone-mode friendly (§18):** connection params come from
  `seed_params(tree, self._settings)` where `tree` is the current project's lxml tree **or `None`**
  when no `.pgtp` is open — no project is required, only a configured connection. Missing host →
  status-bar message ("No database connection configured — set one up first."), uncheck the toggle,
  and open Connection Setup. Fetch error → status-bar message (`DDL Explorer failed: {exc}`) + uncheck
  the toggle. Params are logged redacted (`debuglog.redacted`).

**Editing is deliberately NOT hosted here.** The earlier "phase 2" sketch — making this multi-object
buffer editable in place and pushing `CREATE OR REPLACE FUNCTION …` from it, with the diff detected per
`DdlObjectSpan` — is **superseded** (§28). A regenerated, whole-schema browsing buffer cannot host
per-object validation, per-object apply, or per-object dirty state, and it conflicts with §18.2's
file-per-object model. `EditorPanel` is read-only **permanently**. The editable surface is §18.5's
separate single-object tab, which reaches this panel only through the right-click ▸ Edit entry point
(and therefore needs the retained span list noted above).

### 18.2 Projects, checkout & state markers

> **Status: target design, not yet implemented.** Nothing in this subsection exists in the codebase —
> there is no `db/ddl_project.py`, no project menu actions, no `.ddlproject/` handling and no marker
> rendering on `BrowserPanel`. §18.1's browsing substrate (which *is* implemented) and §18.5's editable
> tab (target design) are what this builds on.
>
> **This subsection adds no new tab type.** The editable single-object tab is
> `ui/ddl_object_editor.py::DdlObjectEditorPanel`, specified **once**, in **§18.5**. Everything here is
> the *versioning* layer around it: what a project is, how files are named, what checkout does to the
> tab's **injected load/save pair**, and the `*`/`!` drift markers. Do not restate the tab here.

**"Project" — a new concept, distinct from a `.pgtp` file.** A project = a git repo containing:

| Path | Committed? | Role |
|---|---|---|
| `.ddlproject/project.json` | yes | Project name, description, **non-secret** connection metadata only (host/port/database/user — explicitly **no password**), and the optional `.pgtp` link. |
| `ddl/*.sql` | yes | **One file per DDL object** (function/procedure/trigger) — see the naming scheme below. |
| `.ddlproject/deployed.json` | yes | The deploy manifest (content-hash + deployed commit id per object; see "last-deployed reference" below). |

- `ddl/` is deliberately **file-per-object** (not one big file) specifically so `git diff`/`git blame`
  work meaningfully per object. This is the git-tracked, human-readable form of what's in `EditorPanel`
  (§18.1's single-buffer read-only browsing view is the live/synthesized view; `ddl/*.sql` files are the
  versioned, checked-out, editable form).
- The `.pgtp` link is **optional** — a project may have **zero, one pre-existing, or one newly-created**
  `.pgtp`. Not required, not assumed. (Only when a `.pgtp` link exists does §18.1's XML cross-referencing
  angle apply.)

**Neither browsing nor single-object editing needs a project — only *versioning* does.** Opening the
DDL Explorer (§18.1) stays **connection-only**, exactly as implemented today. Right-click ▸ Edit…
(§18.5) is likewise connection-only: it loads the live introspected definition into the editable tab, so
"edit one function and find out whether it compiles" never requires a git repo. A project becomes
required only for the versioned workflow this subsection adds: **checked-out `ddl/` files, drift markers
and deploy**.

**Menu actions** (Database menu, §26, alongside the existing Connection Setup / Check / DDL Explorer
entries): **New DDL Project…**, **Open DDL Project…**, **Close DDL Project**.

**No project is ever created silently.** Invoking a **project-scoped** action with no project open —
Check Out for Versioning, Deploy, or anything that would write under `ddl/` — shows a **"DDL project
required"** dialog offering **Create… / Open… / Cancel**; on Create/Open the operation then proceeds
against the newly-active project, on Cancel nothing happens. Plain Edit… never raises this dialog.
Rationale, stated so it is not re-litigated: initializing a git repo on disk is an **outward effect**,
and this app confirms before outward effects (cf. Generate PHP's Save-vs-Save-As prompt §19, Diff/Merge's
Apply gate §12).

**File naming — disambiguate only when needed.**

| Case | Path | Example |
|---|---|---|
| Routine, sole holder of its `schema.name` | `ddl/<schema>.<name>.sql` | `ddl/public.recalc.sql` |
| Routine that is **overloaded** (≥ 2 routines share `schema.name`) | `ddl/<schema>.<name>(<argtypes>).sql` | `ddl/public.fmt(integer).sql`, `ddl/public.fmt(text).sql` |
| Trigger (always table-qualified — a trigger name is unique only per table) | `ddl/<schema>.<table>.<trigger>.sql` | `ddl/public.orders.trg_audit.sql` |

The flat `ddl/<schema>.<name>.sql` scheme this replaces (see the Supersession Ledger, §28) **collides**:
Postgres allows overloaded functions (`f(int)` and `f(text)` are distinct objects sharing
`schema.name`), and trigger names repeat across tables. Qualifying *only when needed* keeps the common
case short and keeps `git diff`/`git blame` readable — the stated reason for file-per-object above.
`<argtypes>` is `RoutineInfo.arg_types` comma-joined — the **same** list `build_ddl_text`'s banner
comment already prints (§18.1), so a file name and its banner never disagree; `<table>` is
`TriggerInfo.table`.

> **Accepted trade-off, stated plainly (not an oversight):** when a *second* overload of an
> already-checked-out routine first appears, the existing `ddl/public.fmt.sql` must be **renamed** to
> `ddl/public.fmt(integer).sql`. Git records that as delete+add unless the rename is performed
> deliberately (`git mv`), so the tool must do the rename deliberately rather than write-new + leave-old.
> The alternative — always qualifying every routine — was rejected because it makes the overwhelmingly
> common non-overloaded case noisy for no benefit.

**Path computation is pure and Qt-free.** The `object → ddl/*.sql` path function, the "is this
`schema.name` overloaded" decision (which needs the whole routine set, not one routine), and filename
sanitization (path separators, characters illegal on Windows, case-insensitive-filesystem collisions)
all live in the new pure module **`db/ddl_project.py`** — mirroring `db/ddl_buffer.py`'s precedent so
they are unit-testable without Qt and without a database. The same module owns the `project.json` /
`deployed.json` shapes.

**Password handling.** The plaintext password is explicitly **kept out of git**. Reuses the app's
**existing** `db/config.py::ConnectionParams`/`save_connection` local-settings mechanism (§17) rather
than inventing a new local-secrets file — but this **requires generalizing that store from
single-global-connection to keyed-per-project** (by project path or a project id), since today
(`db/config.py`, `_GROUP = "db"`, a single fixed QSettings group) it holds exactly one connection at a
time regardless of which project or `.pgtp` file is open. This is a **required change to the existing
`db/config.py`**, not a new parallel mechanism: `load_connection`/`save_connection`/`seed_params` gain a
trailing defaulted `ProfileKey(project, role)` parameter so each DDL-versioning project's connection
(host/port/database/user/password) persists independently. **§18.5 adds the second dimension to the same
generalization** — a `role` (`target` | `sandbox`) alongside the project key. Both dimensions are one
keyed-group scheme in `db/config.py`, and one `ConnectionSetupDialog` with a profile selector: never a
second settings store, never a second dialog. **The scheme is specified once, in §17** — including the
compatibility trick that keeps the default profile on the literal existing `"db"` group so no saved
connection needs migrating and every existing `tests/db/test_config.py` test passes unedited.

**Checkout-to-edit.** The gesture and the tab are §18.5's (right-click ▸ Edit… on `BrowserPanel.tree`
or inside an object's span in the read-only `EditorPanel` — see §18.5 for the entry-point table, the
widget idioms and the span resolution). What a project adds is a **second variant of that gesture**,
**Check Out for Versioning**, which performs the checkout below and *then* opens the same tab with its
injected load/save pair pointed at the checked-out file instead of the live definition. It is not a
second tab type and not a second editor.

**Checkout semantics (the operation itself):**

1. Resolve the object's `ddl/*.sql` path via `db/ddl_project.py` (naming scheme above).
2. **File absent** → **seed** it from the live introspected definition (`RoutineInfo.source`, i.e.
   `pg_get_functiondef`; `TriggerInfo.definition`, i.e. `pg_get_triggerdef` — §17/§18.1) and write it.
   That write **is** the checkout.
3. **File present** → open it from disk. **The local file is the editable truth and is never silently
   overwritten from the live DB.**
4. If the live DB has drifted from the last-deployed reference (the `!` marker, below), **surface it —
   an Audit line and the existing marker — but do not block editing.** This is the embrace-drift
   principle: the tool surfaces disagreement, it does not auto-resolve. (Drift blocks **deploy**, §18.3
   — never editing.)

Checkout itself never opens a database write transaction: it only reads, through
`db/introspect.py::run_queries` — the sole **read** seam, which only ever `execute`s + `fetchall`s and
never commits (§17). Database *writes* exist in exactly one place, the separate `db/apply.py` seam
introduced by §18.5, and checkout does not use it.

**Save vs. Apply under a project — and how this relates to §18.3.** Once the tab's save callback points
at a checked-out file, **Ctrl+S / Save writes that `ddl/*.sql` file and nothing else** (UTF-8;
**deliberately no `.bak` sidecar** — the file is git-tracked and git is the history, an intentional
divergence from §19's `.pgtp` save). **Apply remains the separate, explicitly confirmed §18.5 gesture**
and is unchanged by checkout: it can target the sandbox or the target database, each confirm-gated.
Saving never applies and applying never saves.

The two write-to-a-real-database paths are deliberately different gestures with different guardrails,
and **§18.3 is authoritative whenever both could apply**:

| | §18.5 single-object **Apply** | §18.3 **Deploy** |
|---|---|---|
| Scope | exactly one object, the one in the active tab | a **batch** of `*`-flagged objects |
| Review | a confirmation naming the object and the database | a reviewed, order-adjustable SQL bundle |
| Drift gate | none — drift is surfaced, not blocking | **any `!`-flagged object blocks the whole batch** |
| Manifest / git | writes nothing to `deployed.json`, makes no commit | updates `.ddlproject/deployed.json` + commits |
| Use it for | iterating on one routine | rolling a reviewed change set out |

Consequence, stated so the two never read as duplicates: a single-object Apply to the **target** database
is a legitimate, narrow, individually-confirmed action — but it is **not** a deploy. It does not record
last-deployed state, so the object will subsequently read as `!` (live DB differs from the last-deployed
reference), which is correct and intended: the versioned record of what is deployed is only ever written
by §18.3. **When a project is open and the objects involved are checked out, the reviewed §18.3 deploy is
the authoritative path**; single-object Apply exists for the edit/validate loop, not for rollout.

**Tab key under a project.** §18.5's dynamic-tab map is keyed by a stable per-object key; once an object
is checked out, that key is the **resolved absolute `ddl/*.sql` path**, so re-invoking Edit on a
checked-out object focuses the existing tab rather than opening a second one. (Project-less, the key is
the object's `DdlObjectSpan` identity — §18.5.)

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
   editable there** (editing only happens in the single-object editor tabs, §18.5). This is
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
  automate. **This non-goal is about *automatic* and *unreviewed* execution, not about all execution:**
  §18.5's single-object **Apply**, which does execute DDL against the sandbox or the target database, is
  compatible with it precisely because it is neither — it is one object, initiated by hand, behind a
  confirmation naming the object and the database. See §18.2's Apply-vs-Deploy table for which of the two
  is authoritative when both could apply (short answer: **Deploy**).
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

### 18.4 SQL/plpgsql selection formatter

> **Status: core implemented 2026-08-01 (`pgtp_editor/sql/`, `tests/sql/`); consumer designed
> 2026-08-02 (§18.5), not built.** Scoped as a standalone, Qt-free formatter **core only**, and it is
> still **not wired into anything** — nothing calls `format_selection`. What is no longer open is
> *where* it will be called from: the host surface is the **DDL object editor** (the editable per-object
> tab `ui/ddl_object_editor.py::DdlObjectEditorPanel`), fully specified in **§18.5**; the
> trigger is **`Ctrl+Alt+F`** plus a context-menu **"Format Selection"** item in that tab, enabled only
> with a selection (so §26/§27 now carry the binding); and refusals report to the Audit panel with the
> **`[SQL]`** prefix (distinct from §18.5's `[Check]` validation findings and §22's `[Lint]` — the
> three-way reservation is in §7). That host **does not exist yet** — building it is §18.5's scope, not
> this subsection's — so the Audit-panel reporting path below remains a **contract** (the `Issue` span
> exists so the host can underline the offending construct), **not wiring**. Unchanged: there is **no
> auto-format mode**, **no "Lint Selection" action**, and **no rule catalog** beyond the tokenize/balance
> floor.

**Problem framing.** Once §18.5's DDL object editor makes plpgsql function/trigger bodies hand-editable,
"uniformity" for that editing means **consistent indentation and line breaks only** — not keyword
casing, not identifier casing, not comma placement/style, not literal values. This subsection defines
the formatter that enforces that narrow notion of uniformity.

**Trigger & scope — explicit-only, no auto-mode, full stop:**

- Invoked **only** by an explicit user action on the current text **selection**: **`Ctrl+Alt+F`** or the
  **"Format Selection"** context-menu item in §18.5's DDL object editor tab, both enabled only when a
  selection exists (§18.5 owns that wiring; §26/§27 record the binding). There is **no** auto-format-on-
  edit and **no** format-on-save, and — unlike Auto Parse XML (§9, off-by-default but togglable) — this
  formatter has **no auto-mode at all**: the user explicitly rejected an auto-mode as "intrusive and
  counterintuitive" during design. Do not add one without a fresh design decision superseding this one.
- Operates on **arbitrary selections** — a complete statement, a bare fragment (`where a = 1`,
  `order by a, b`, `, b, c`, even `;` alone all format), or a chunk of plpgsql control-flow (e.g. a
  `BEGIN...END` block) — not necessarily a whole function or trigger body.
- There is **no "Lint Selection" action** and **no rule catalog** beyond the tokenize/balance floor
  described below (no keyword-casing rule, no comma-style rule, nothing semantic). If future prose
  anywhere implies otherwise, that implication is wrong per this design.

**Core algorithm — hand-built tokenizer + nesting-depth reindenter, not an adopted library:**

Covers both plain-SQL clause structure (`SELECT`/`FROM`/`WHERE`/`JOIN`, paren depth) and plpgsql block
structure (`BEGIN`/`END`, `IF`/`ELSIF`/`END IF`, `LOOP`/`END LOOP`, `CASE`/`WHEN`/`END`). Reindents
**whitespace and line breaks only** — keyword casing, identifier casing, comma placement/style, and
literal values are never touched.

**Module shape (five modules, Qt-free, no DB/network I/O; `tests/sql/` mirrors it):** the package
**`pgtp_editor/sql/`** (name follows the existing `db/`/`schema_learning/`/`analysis/`/`diff/` convention
of §5's layout) contains `keywords.py` (dialect set) → `tokenizer.py` (`Token`, `tokenize`) →
`formatter.py` (`FormatResult`, `format_selection`, the private `_Reindenter`) + `issues.py` (`Issue`),
with `__init__.py` as the façade.

**Public API:**

| Symbol | Shape |
|---|---|
| `format_selection` | `format_selection(text: str, *, indent_unit: str = DEFAULT_INDENT_UNIT) -> FormatResult` (`DEFAULT_INDENT_UNIT = "    "`, four spaces) |
| `FormatResult` | `@dataclass FormatResult{ok: bool, text: str, issues: list[Issue]}` — on refusal `ok=False` and `text` is the input **verbatim**, so even a caller that ignores `ok` cannot corrupt the selection |
| `Issue` | `@dataclass(frozen=True) Issue{message, start, end, start_line, start_col, end_line, end_col, fatal=True}` + property `line == start_line` |
| `tokenize` | `tokenize(text: str) -> list[Token]` — public on `pgtp_editor/sql/tokenizer.py` (lossless, verbatim, **never raises**) |
| `SQL_KEYWORDS` | the shared dialect set (see below) |

`sql/__init__.py`'s `__all__` is exactly `{"format_selection", "FormatResult", "Issue",
"SQL_KEYWORDS"}` and that surface is **test-pinned**; `tokenize`/`Token` are reached through
`pgtp_editor.sql.tokenizer` rather than the façade.

`Issue` **mirrors and extends** `schema_learning/xsd_verify.py`'s `Issue{line, message, fatal}` (§11):
same `message`/`fatal` framing, plus a precise span — 0-based `start`/`end` character offsets into the
input and 1-based `start_line`/`start_col`/`end_line`/`end_col` (`end_col` exclusive) — because this
feature must underline the exact offending construct, not just flag a line. `line` is kept as an alias of
`start_line` so the shape reads as a strict superset. This is a **pattern extension, not a shared
class**: `xsd_verify.Issue` is untouched and `sql.Issue` is a distinct type in the pure `sql/` package.

**Shared dialect source — `SQL_KEYWORDS` lives in the core, not in `ui/`:** the lowercase,
case-insensitively-matched keyword set is defined in **`pgtp_editor/sql/keywords.py::SQL_KEYWORDS`** (a
`frozenset` of 115 members: the highlighter's original §18.1 set plus the plpgsql control keywords the
tokenizer/block tracker need — `elseif`, `elsif`, `exit`, `continue`, `foreach`, `reverse`, `intersect`,
`while`), and `ui/code_editor.py` binds `_SQL_KEYWORDS = SQL_KEYWORDS` for `_CodeHighlighter`'s
`language="sql"` mode (§8). It is still exactly **one** source of truth shared by highlighter and
formatter — but on the correct side of §5's dependency arrow: `sql/` must be Qt-free, so importing the
set *from* `ui/` would have inverted **core must never import ui** (see the Supersession Ledger, §28).
Extend the dialect in `sql/keywords.py`; both consumers see it. `Token.keyword` is a **view** (lowercased
text when it is in the set, else `None`) — never a rewrite; `Token.text` stays verbatim.

**Tokenizer (`sql/tokenizer.py`) — lexical only, no grammar:** kinds are plain string constants
(`whitespace`, `newline`, `line_comment`, `block_comment`, `string`, `quoted_ident`, `dollar_string`,
`number`, `word`, `punct`), matching the codebase's existing `kind: str` convention (`db/ddl_buffer.py`).
`Token{kind, text, start, end, start_line, start_col, end_line, end_col, unterminated, tag}` with
`is_trivia`/`is_opaque`/`keyword`/`is_keyword`/`lowered` views. `OPAQUE_KINDS` = comments, strings,
quoted identifiers, dollar-quoted bodies: their **content is opaque and is never reindented or
line-broken internally**. Postgres specifics: `''`/`""` doubling is an escape (not a terminator), `E'…'`
additionally honors `\'`, `/* */` **nests**, `$$…$$`/`$tag$…$tag$` bodies are one token (`tag` recorded,
`""` for a bare `$$`), and an unterminated opaque region is **not** an exception — it becomes one token
with `unterminated=True` spanning from its opener to end-of-input, so the formatter can refuse with that
exact span.

**Unicode-aware identifiers and all three line endings** are guarantees, not incidentals (both came from
bugs found and fixed during verification):

- Word start/continue follow PostgreSQL's unquoted-identifier rule via `str.isalpha()` / `str.isalnum()`
  (`_` a start char, `_` and `$` continuation chars), so **accented identifiers are never split**
  (`ügyfél_száma` is one `word`). Splitting them let the reindenter insert spaces *inside* an identifier
  and corrupt the SQL.
- `\r\n`, a lone `\n` and a lone `\r` each count as **exactly one** line break for `Issue`/`Token`
  line/column bookkeeping (including a `\r\n` straddling two scan chunks), and dominant-EOL detection
  recognizes **CR-only** text — otherwise every span in classic-Mac text would point at the wrong line.

**Glue rules the tokenizer/spacer must honor** (a naive lexer plus "one space between tokens" would
change meaning, not just layout — the formatter only ever inserts single spaces between tokens, so
anything that must not be separated is kept as one unit or has its space suppressed):

| Construct | Rule |
|---|---|
| `::`, `:=`, `->>`, `#>>`, `#>`, `<=`, `<>`, `!=`, `\|\|`, `..`, `@>`, `<@`, `&&`, `~*`, `!~`, `^@`, … | multi-character operators are **one** `punct` token (longest match first) |
| `a.b`, `a::text`, `a, b` | no space around `.` / `::`; none before `,` `;` `)` `]` |
| `col%TYPE` / `col%ROWTYPE` | `%` glues when followed by `type`/`rowtype`; otherwise it is the modulo operator and keeps its spaces (`a % b`) |
| `$1` | positional parameter is one `word` token (`$ 1` is not valid SQL); a `$` opening a dollar-quote is tested first |
| `E'…'`, `U&'…'`, `B'…'`, `X'…'` | the prefix is glued to the opening quote (part of the `string` token); backslash escapes are honored only for the single-char `E`/`e` form |
| `1..10` | the `..` is the plpgsql range operator, never a fractional point |
| `f(x)`, `count(*)`, `"Q"(1)`, `f(a)(b)` | `(` glues to a preceding **non-keyword** word / quoted ident / `)` / `]` — but `in (1, 2)` and `values (1)` keep the space |
| `array[1]`, `a[i]`, `a[1][2]` | a subscript `[` always glues to its target (word, quoted ident, string, `)` or `]`) |
| unary `-`/`+` | glues to its operand when the token **before the sign** is an opener/operator/comma/keyword (`= -1`, `(-1)`, `, -1`, `select -1`); `a - 1` and `count(*) - 1` stay binary |

**Reindenter (`sql/formatter.py::_Reindenter`) — one frame stack does both indentation and balance,** so
there is a single implementation of "how deep are we". Frames: `root`, `paren`/`bracket`, the block
frames `begin`/`if`/`loop`/`case` (balance-relevant), and the soft frames `declare`/`when` (indent-only,
popped implicitly, never a refusal reason). It walks the significant tokens once (whitespace dropped,
each token carrying how many newlines preceded it), so deep nesting cannot blow the stack.

- **Indent** = `indent_unit` (default **4 spaces**) × open frames, with `exception` and a *statement*
  `else`/`elsif`/`elseif` **dedented one level** so they sit at their block's own level (in a `CASE`
  **expression** an `else` instead pops the branch's soft `when` frame, which aligns it with the `when`s),
  and **+1 level** for clause-continuation lines (a line continuing an open
  `select`/`from`/`where`/… clause at this nesting level).
- **Line breaks** happen before clause starters (`select from where group having order limit offset
  union except intersect join on values set returning with`), before block keywords
  (`begin declare exception else elsif elseif end when`), after `begin`/`declare`/`loop`/`exception`
  headers, after `;`, and after a `--` line comment (anything appended to it would be commented out). A
  JOIN phrase breaks **once**, before its first prefix word (`left outer join` stays on one line, and
  only when a `join` actually follows within three tokens).
- **Author line breaks are preserved wherever no rule applies.** A newline the author put in the source
  is honored, so hand-chosen layout — including **leading-comma style** — survives: this is how "never
  change comma placement or style" is honored while still line-breaking structurally. Blank lines between
  statements are **preserved but capped at one**, and leading blank lines are dropped.
- **`CASE` bodies stay on the `then` line** (expression-friendly: `when 1 then 'a'` is one line). Only a
  **statement** context — the nearest enclosing block being an `IF`, or a `BEGIN`'s `EXCEPTION` part —
  makes `then`/`else` force a break so the body starts on the next line.
- **Layout preservation:** the base indentation of the selection's **first content line** is re-applied
  to every emitted line (so a formatted block stays where it sat in the host document; tabs included);
  the **dominant EOL** (`\r\n` / `\n` / lone `\r`, ties → `\n`) is preserved; a trailing newline is
  preserved (and its absence too). **Empty / whitespace-only input is returned untouched with `ok=True`**
  (nothing to format, nothing to refuse).
- **Guaranteed invariants (test-pinned over a realistic corpus, an adversarial set and seeded fuzz):**
  the output's non-whitespace token texts equal the input's, in order, and only whitespace differs
  (`"".join(out.split()) == "".join(in.split())`); keyword casing, identifier casing, comma placement and
  literal values are never touched; formatting is **deterministic and idempotent**
  (`fmt(fmt(x)) == fmt(x)`, for any `indent_unit`); no input raises or stalls.

**False-positive guards (ordinary DDL must not hit the refusal gate).** These are load-bearing: without
them, everyday statements would be read as unbalanced plpgsql.

| Construct | Interpretation |
|---|---|
| `DROP TABLE IF EXISTS t;` / `CREATE … IF NOT EXISTS` | `IF` is a modifier, **not** a block opener |
| `BEGIN;` and `BEGIN TRANSACTION\|WORK\|ISOLATION …` | transaction control, **not** a plpgsql block — and a later bare `END;` at root level is then accepted instead of reported as unmatched |
| `DECLARE c CURSOR FOR …` (inline `CURSOR` before the next `;`) | a **statement**; a `DECLARE` that *ends its line* opens a plpgsql declaration section (told apart by layout), and that section's frame is popped by its `BEGIN` |
| `EXCEPTION` | **dedents** and marks the enclosing `BEGIN`'s exception part; it does **not** open a block |
| `END IF` / `END LOOP` / `END CASE` | two-token closers — the `if`/`loop`/`case` after `end` is never an opener, and never starts a new line |
| bare `LOOP` vs `FOR … LOOP` / `WHILE … LOOP` | a bare `LOOP` (at start, after `;`, or after `then`/`begin`/`else`/`exception`/`loop`/`declare`) opens a block on its own line; a loop **header** keeps its `LOOP` on the header line |
| `EXIT WHEN done` / `RAISE … WHEN` | ordinary statement tails — `WHEN` only opens an indented branch inside a `CASE` or an `EXCEPTION` part |

**Why build instead of adopt a library (record the investigation, not just the conclusion):**

| Candidate | Why ruled out |
|---|---|
| `sqlparse` | Token-based reformat, historically fragile around dollar-quoted (`$$...$$`) bodies. |
| `sqlfluff` | Confirmed via its own issue tracker (github.com/sqlfluff/sqlfluff #5864, "Linting doesn't work over plpgsql blocks") that it does not lint or fix inside plpgsql blocks. |
| `sqlglot` | Pure Python, real Postgres dialect + pretty-printer, but treats dollar-quoted bodies as **opaque string literals by design** — a generic SQL grammar can't safely reformat procedural plpgsql it doesn't model. Since selections here may themselves **be** plpgsql control-flow fragments (not just whole statements with an opaque body), this blocks the actual use case, not just an edge case. |
| `pgFormatter` / `pg_format` | The one mainstream tool with genuine plpgsql-aware reindentation (`BEGIN`/`END`, `IF`/`THEN`, loops) — but it's a **Perl CPAN module**. Ruled out on cross-platform packaging grounds: bundling/requiring a Perl runtime for a PySide6 desktop app distributed to Windows users is a real distribution liability, not hypothetical. |
| `pylintsql` (github.com/growdashtech/pylintsql) | Investigated because directly referenced during design. Wrong shape entirely: a thin CLI wrapper that scans `--sql`-marked strings inside **Python source files** and runs them through SQLFluff, project-wide — not an in-process function over an editor selection. Also inherits SQLFluff's same plpgsql-block limitation. Not used. |

**Conclusion:** no existing Python-ecosystem library handles plpgsql block reindentation, so a narrow
hand-built tokenizer (indentation/line-breaks only, not a full semantic parser) is the correct scope for
this feature — not a compromise forced by time pressure.

**Safety / refusal behavior — the only gate, unconditional:**

Formatting proceeds whenever the selection can be confidently tokenized and its parens/brackets/blocks
are balanced. If it cannot — an unmatched `BEGIN`/`IF`/`LOOP`/`CASE`/`END`, a stray or unmatched
paren/bracket, a wrong closer (`if … end loop;`), or a selection boundary that splits a string literal,
quoted identifier, `/* */` block comment or `$$…$$` dollar-quote in half — the formatter **refuses
entirely**: `ok=False`, `text` is the input **verbatim** (so the selection is left completely unchanged
even for a caller that ignores `ok`), and `issues` is non-empty with every entry `fatal=True`. Nothing is
guessed or partially applied. This is the project's existing "never a silent wrong result" ethos (cf.
Diff/Merge's ambiguity gate, §12) applied here. This tokenize/balance refusal is **unconditional and the
only thing that blocks formatting** — there is no separate semantic or lint gate layered on top (see the
explicit exclusions below). Clause-level incompleteness is *not* a refusal reason: a bare fragment
(`where a = 1`, `and x = 2`) is a legitimate selection.

- **All refusals are reported, sorted by offset** (`(start, end)`). An unclosed `IF` inside an unclosed
  `BEGIN` yields **two** issues; each carries the **opener's** span (the `begin`, the `if`, the `(`) or
  the offending closer's span (`end if`, `)`), with the line/column repeated in the message text
  (verbatim shape: `Unmatched IF -- no matching END IF in the selection (line 2, column 3).`). A wrong
  closer is reported **once**, against the opener, naming what was found instead
  (`... -- found END loop instead ...`).
- **Exception:** an unterminated string / quoted identifier / dollar-quote / block comment is reported
  **alone** and short-circuits **before** the balance walk, because any balance conclusion drawn past a
  broken quote is unreliable.
- **Reporting contract (designed, still not wiring):** on refusal, the host reports through the **Audit
  panel** (§7 — the app's single output surface for all actions, already used by
  `[Schema]`/`[Validate]`/`[Find]`/`[PHP]`-prefixed lines) under the **`[SQL]`** prefix, and uses the
  `Issue` span to **underline the exact construct** (e.g. the specific unmatched `BEGIN`) rather than
  flagging the whole line — the span is carried precisely for that. The designated host is §18.5's DDL
  object editor tab; **it does not exist yet**, so no code in the tree calls this today. The core is
  unchanged by the host's arrival.

**Explicitly out of scope of this subsection (deferred/future, not designed here):**

1. **The DDL object editor UI surface itself** — now **designed in §18.5** (a *new* editable per-object
   tab, `ui/ddl_object_editor.py::DdlObjectEditorPanel`; note it is **not** §18.1's read-only
   `EditorPanel` made editable — that panel stays read-only permanently). This subsection still covers
   only the reusable formatter core; the tab, its context menu, the `Ctrl+Alt+F` action, the
   selection-only enablement, the single-undo-step replacement and the `[SQL]` Audit reporting all
   belong to §18.5. As of today neither the tab nor the wiring exists — the formatter core is shipped
   and tested but has **no live consumer**.
2. **Semantic/existence linting** (verifying that referenced tables/columns/functions actually exist) —
   **no longer merely deferred: it is designed in §18.5** as the sandbox-backed validation ladder
   (schema-only scratch PostgreSQL + the `okbob/plpgsql_check` extension). It remains **entirely outside
   `format_selection`'s refusal gate**, which stays tokenize/balance only, runs offline, and never
   touches a database. The two are separate surfaces reporting under separate Audit prefixes (`[SQL]`
   formatter refusals vs. `[Check]` validation findings, §7).
3. To restate plainly: there is **no** "Lint Selection" action, **no** rule catalog beyond the
   tokenize/balance floor, and **no** auto-format mode. Any of these appearing designed elsewhere in this
   document would be drift from this settled decision.

### 18.5 The DDL object editor, apply & sandbox validation

> **Status: settled design (2026-08-02), not yet implemented.** Nothing described here exists in the
> codebase: `ui/ddl_object_editor.py`, `db/apply.py`, `db/sandbox.py`, `db/ddl_check.py`,
> `db/schema_diff.py` and `db/migration_gen.py` are all new,
> `CenterStage` has no dynamic tabs, there are no context menus on `BrowserPanel.tree` or the DDL
> `EditorPanel`, and the Database-menu entries below are not built. §18.1's browsing substrate (which
> *is* implemented) and §18.4's formatter core (which *is* implemented) are the only things this builds
> on.
>
> **This subsection is the single specification of the editable DDL tab.** §18.2 (projects, checkout,
> markers) references it and changes only *where the tab's buffer loads from and saves to*; it does not
> restate it and does not introduce a second editable surface. Two parallel design sessions on
> 2026-08-02 produced overlapping drafts of this tab; they are reconciled here, and the overrides are in
> the Supersession Ledger (§28).

#### The three outputs, ranked — read this before anything else

An earlier reading of this section as *"an editable tab with a lint target"* is **wrong** and is
superseded (§28). The feature's outputs are ranked by **value**, and the ranking is what the design must
serve:

| Rank | Output | What it is |
|---|---|---|
| **1** | **Generate Deployment SQL — THE deliverable** | Sandbox = **desired state**, production = **current state**, output = **one reviewed `.sql` migration script**, run once, to upgrade the real database. Built on `db/schema_diff.py` + `db/migration_gen.py` to §18.3's exact shapes. |
| **2** | **The stateful sandbox** | An accumulating, executable **desired state** you can prove is coherent (it compiles, it checks) *before* it is diffed. Not a scratch pad that resets between checks. |
| **3** | **Per-object Save / Apply** | A **convenience** and the **§18.2 precursor** — `Save As… .sql` is exactly §18.2's future `ddl/<schema>.<name>.sql` arriving early. Genuinely useful; **demoted from headline**. |

Build order follows the ranking's dependencies rather than the ranking itself: the write/read
capabilities and the connection profiles first (invisible infrastructure), then the sandbox
(`db/sandbox.py`) and the ladder (`db/ddl_check.py`), then the editable tab (which ships useful with **no
sandbox at all** — edit + Save As), then sandbox setup, then check wiring, and **finally the deployment
script**, which is worthless without validation: never ship a deployment script assembled from routines
nobody proved compile. The last thing built is the first thing the user cares about.

**Why the editor and the sandbox are one feature, not two.** A hand-editable DDL tab with no feedback
loop teaches the user nothing until the moment it is most expensive to learn. The alternatives to a
sandbox are all worse:

- **Deploy-time discovery** (§18.3) — the user finds out whether their plpgsql compiles at the exact
  moment the tool exists to make safe.
- **Apply-to-target discovery** — even with Apply's confirmation gate (below), *using production as your
  compiler* is precisely the outward effect this app is built to avoid; a confirm dialog makes an action
  deliberate, it does not make it a feedback loop.
- **Formatter-as-proxy** (§18.4) — the formatter is indentation and line breaks only, with no semantic
  rule and no database access at all. It can tell you your `BEGIN` is unmatched; it can never tell you
  `NEW.custmer_id` is a typo.

Reinforcing this: `pg_dump` sets `check_function_bodies = off` during restore, so a restored database has
had **zero** validation of its function bodies — "it restored cleanly" says nothing about whether the
routines compile. Editor and sandbox are therefore specified together and built together.

#### D1 — Editor scope: a single-object editable tab, project-decoupled for v1

The loop is **edit → validate against the sandbox → save, and/or explicitly apply**. Right-click an
object → **Edit…** opens a new **single-object editable tab** in `CenterStage` holding just that one
routine or trigger.

- **v1 has no `ddl/` folder, no `.ddlproject/deployed.json` manifest, and no `*`/`!` state markers.**
  All three are §18.2 concepts; **none is a prerequisite** for editing one function with feedback. The
  buffer is loaded from the live introspected definition (`RoutineInfo.source` /
  `TriggerInfo.definition`, §17/§18.1).
- **The tab is written against an injected load/save pair, never a hard-coded source.** This is a
  structural requirement, not a style preference: it is the entire mechanism by which §18.2 layers on
  later **without rework** — checkout swaps the pair (live definition → checked-out
  `ddl/<schema>.<name>.sql`) and adds marker rendering on `BrowserPanel`, and the tab, its command set,
  its validation and its Apply gestures are untouched. The tab must not import `db/ddl_project.py`, must
  not know what a project is, and must not branch on whether one is open.
- **Rejected: build full §18.2 first.** *(Operative rationale — this reverses an earlier decision, §28.)*
  A git project, a manifest, a hash scheme and a marker recompute is a large prerequisite to place in
  front of "edit one function and find out whether it compiles."
- **Rejected: make the multi-object `EditorPanel` buffer editable in place.** A regenerated whole-schema
  buffer cannot carry per-object dirty state, per-object validation or per-object apply, and it conflicts
  with §18.2's file-per-object model. `EditorPanel` stays read-only **permanently** (§18.1), not
  provisionally.

**Two entry points, both right-click, converging on one operation.**

| Entry point | Gesture | Resolution |
|---|---|---|
| `BrowserPanel.tree` (§18.1, left dock "DDL Objects") | right-click an **object row** ▸ **Edit…** | the row's `DdlObjectSpan` (`Qt.ItemDataRole.UserRole`, `_SPAN_ROLE`) |
| DDL `EditorPanel`'s read-only SQL buffer (center "DDL Explorer" tab) | right-click inside an object's span ▸ **Edit \<schema>.\<name>…** | the retained `DdlObjectSpan` whose `start_line..end_line` contains the clicked line |

- **`EditorPanel` must retain its span list** (e.g. `self._spans`) for the second entry point. Today
  `set_ddl_text(text, spans)` converts the spans to fold regions and **drops** them (§18.1) — that is a
  required amendment, not an optional one.
- **Left-click behavior is unchanged** on both surfaces: the tree still emits `navigate_requested(line)`
  and the buffer still navigates top-aligned (§18.1).
- **Argument-name child leaves are not editable targets** — they carry no span (`_SPAN_ROLE` unset,
  §18.1), so their context menu offers no Edit. Only object rows (routine leaves and both trigger
  occurrences) do.
- **Widget idioms, matching what this codebase already does:** the tree uses
  `setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)` + `customContextMenuRequested` (the
  `db_check_panel.py` / `project_tree.py` pattern); the editor overrides `contextMenuEvent` and extends
  `createStandardContextMenu()` (the `xml_editor.py` pattern), moving the caret to the clicked document
  position first so the resolved span reflects the click and not a stale caret.
- Neither entry point writes to a database. With a project open, §18.2 adds a second variant of the
  gesture — **Check Out for Versioning** — which performs a checkout first and then opens this same tab
  with its load/save pair repointed.

**Tab shape (`ui/ddl_object_editor.py::DdlObjectEditorPanel`).** A **new tab type**, distinct from the
read-only `EditorPanel`, **one tab per object**. It hosts the **existing**
`ui/code_editor.py::CodeEditor` in `language="sql"` mode made **editable** (`setReadOnly(False)`) — the
same widget, highlighter, 4-character tab stop and `ui/editor_gutter.py::GutterBookmarkFoldMixin`
gutter/bookmarks/folding the read-only DDL Explorer uses (§8/§18.1) — plus its own `FindReplaceBar`
instance, following the established per-tab document-routing precedent (Edit XSD, DDL Explorer; §7/§15).

- **Re-invoking Edit on an already-open object focuses the existing tab** — never a second tab for the
  same object.
- **Title** = the object's short identity (`recalc`, `fmt(integer)`, `orders.trg_audit`) plus a dirty
  marker (the `" *"` convention the Edit XSD tab already uses, §11); **tooltip** = the full source
  identity (the qualified object name in v1, the absolute file path once checked out).
- **Closable.** Closing with unsaved changes prompts — reusing the established Edit-XSD pattern where
  the **tab signals the MainWindow** to run the confirm (`CenterStage.xsd_close_requested` →
  `MainWindow._on_xsd_close_requested` → `_confirm_close_xsd()`), rather than the tab deciding for
  itself. Save / Discard / Cancel; on Cancel the tab stays open and dirty.
- **Deliberately no `.bak` sidecar** on the file-backed variant — unlike `.pgtp` save (§19) and unlike
  `curated.xsd` import (§11). The file is git-tracked and **git is the history**; a `.bak` beside it
  would be untracked noise inside a versioned tree. This divergence from §19 is intentional.
- **A small button row** carries the three sandbox gestures — **Apply to Sandbox** / **Check** / **Check
  without applying** — each of which merely **emits a signal**; MainWindow owns every piece of DB work,
  off-thread. The same three are reachable from the Database menu and the tab's context menu (§26).
- The panel holds an **`applied_sha1`** slot so it can render *"changed since you last applied it"*
  against the sandbox working set (D2), and so **Check** on a diverged buffer emits a `[Check]` caveat
  line instead of silently validating a stale version.
- **`resolve_save_path: Callable[[], Path | None]`** is the injected save half in concrete form: in v1 it
  returns the panel's remembered `_save_path` (`None` until Save As picks one, at which point subsequent
  Ctrl+S is silent). **§18.2's entire change is this one function returning
  `project.ddl_dir / <the §18.2 filename>`** — no restructure.

Consequences for existing wiring — **all extensions of existing dispatchers, no new machinery**:

- `main_window.py::_active_find_bar()` gains a branch for the active editable DDL tab (Ctrl+F / F3 /
  Ctrl+Shift+F, and Ctrl+R / Ctrl+Alt+Return, which are **live** here — unlike in the read-only DDL
  Explorer, where `CodeEditor.replace_current_selection` returns early on `isReadOnly()`).
- `_active_bookmark_editor()` gains the same branch — still with **no** tab-switching side effect (§8).
- `_save_active_tab()` gains a branch (§7). The read-only DDL Explorer still gets none: it is
  DB-synthesized and has no save path, which is why Ctrl+S's routing is asymmetric to Ctrl+F's.
- This tab is §18.4's **first consumer** (Format Selection, below).

**`CenterStage` needs dynamic tabs — the largest structural piece of this design.** Today every tab is
created in `CenterStage.__init__` with a stored integer index (`raw_xml_tab_index`,
`diff_merge_tab_index`, `caption_management_tab_index`, `xsd_tab_index`, `ddl_tab_index`,
`manual_tab_index`) and shown/hidden via `setTabVisible`; `_on_tab_close_requested` dispatches by
comparing the closed index to those constants. Per-object tabs are created at **runtime**, so:

- Dynamic object tabs are **always appended after the fixed set**, so the stored fixed indices never
  shift and every existing index comparison stays correct.
- Dynamic tabs are looked up through a **key → widget map**, never by a remembered index — close/reorder
  must not be able to make an index stale. The key is a stable per-object identity: the object's
  `DdlObjectSpan` identity (kind + schema + name + argtypes, or + table for a trigger) project-less, and
  the **resolved absolute `ddl/*.sql` path** once checked out (§18.2).
- Close dispatch must therefore fall through from the fixed-index comparisons to a map lookup.

**Editor command set.** Inherited from the generic code editor rather than reimplemented:

| Affordance | Source |
|---|---|
| Undo / redo | `QPlainTextEdit` built-in |
| Find / Find Next / Find All / Replace / Replace All | its own `FindReplaceBar` instance + a new branch in `_active_find_bar` (§7/§15) |
| Bookmarks (Ctrl+F2 / F2 / Shift+F2) + gutter + folding | `ui/editor_gutter.py::GutterBookmarkFoldMixin` (§8) + a new branch in `_active_bookmark_editor` |
| Auto-close & selection-wrap for brackets/quotes; bracket-select (Ctrl+Shift+B) | `CodeEditor.keyPressEvent` / `enclosing_bracket_span` (§8) — already generic, no change |
| 4-character tab stop, SQL highlighting, top-aligned `navigate_to_line` | `CodeEditor`'s `language="sql"` mode (§8/§18.1) — already generic |
| Standard context menu + the entries below | `createStandardContextMenu()` extended (the `xml_editor.py` idiom) |

**Two affordances are *not* inherited and are new work if wanted at all** (recorded because an earlier
draft wrongly listed them as inherited): a **wrap-lines toggle** — `CodeEditor.__init__` hard-sets
`QPlainTextEdit.LineWrapMode.NoWrap` and defines no context menu at all, so the Raw XML editor's
checkable wrap entry has no equivalent here; and **goto-line** — **no editor in the app has one**
(`Ctrl+G` is the caption grid's, §13). Neither is required by this design; if either is built it is an
additive `CodeEditor` feature in its own right, not a DDL-tab detail.

**Fold regions come from the object's own structure**, not from `EditorPanel`'s whole-buffer
`DdlObjectSpan` index: a single-object buffer has no banner spans. Regions are installed through the same
`CodeEditor.set_fold_regions(regions)` seam (§8).

**XML-editor affordances that deliberately do NOT apply here** (stated so a reader does not expect
them): **Select Parent Block** (Ctrl+Shift+A — XML tag hierarchy), **Add attribute ▸**, **Go To XSD**
(Ctrl+L), **Auto Parse XML**, attribute autocomplete and hover annotations, **Properties-panel sync**,
and **editor↔tree sync**. All are XML/schema-driven and meaningless for a SQL buffer.

#### Format Selection — §18.4's formatter finally gets its consumer

- **Format Selection**, bound to **`Ctrl+Alt+F`**, plus a **context-menu item** in this tab. Both are
  **enabled only when there is a selection**. `Ctrl+Shift+F` remains **Find All**, untouched
  (`main_window.py`) — §18.4 left the binding TBD and this is the choice.
- Calls `sql.format_selection(selected_text)` (§18.4).
- **On success** the selection is replaced as a **single undo step** (one `QTextCursor` edit block), so
  one Ctrl+Z reverts the whole reformat.
- **On refusal** (`ok=False`) the text is left **completely unchanged** — `FormatResult.text` is the
  input verbatim, so even a caller that ignored `ok` could not corrupt it — and **each `Issue` is
  reported to the Audit panel** (§7) with the **`[SQL]`** prefix. The offending span is additionally
  **underlined in the editor** using the `Issue`'s precise `start`/`end` — which is *why* §18.4's `Issue`
  carries a span at all. The underline is **transient** (cleared on the next edit or the next format
  attempt), not persistent state.
- Offered **only in this tab** — **not** in the read-only DDL Explorer buffer, where a reformat could not
  be applied anyway.
- Restated from §18.4 and unchanged: **selection-only**, **no auto-format mode**, **no "Lint
  Selection"**, and **no rule catalog beyond the tokenize/balance floor**.

#### Save and Apply are two distinct, explicit user gestures

**Neither is ever automatic, and neither is ever implied by the other.**

| Gesture | What it does | Trigger |
|---|---|---|
| **Save** | Persists the edited text through the tab's **injected save callback** — the in-session buffer in v1, the checked-out `ddl/*.sql` file under §18.2. **Touches no database, ever.** | `Ctrl+S` via `_save_active_tab` (§7), File ▸ Save |
| **Apply** | **Executes** the buffer's DDL against a database — the **sandbox** (where it is *meant* to persist, D2) or the **target** (behind the hard gates below) — through the write seam below. **Persists nothing to disk** and clears no dirty state. | Explicit menu / context-menu / panel action only. **Deliberately no keyboard shortcut** — an irreversible outward effect must not be one keystroke away. |

Validation (the ladder in D3) is a third, likewise explicit gesture. It comes in **two modes** and the
difference is user-visible: **Apply to Sandbox → Check** *commits* to the sandbox (that is the point —
the sandbox is the accumulating desired state, D2), while **Check without applying** runs the same
ladder inside a transaction that is explicitly rolled back. The earlier framing — *"validation writes
nothing durable anywhere; everything it does inside the sandbox is rolled back"* — is **retracted**
(§28).

#### The write seam — `db/apply.py`, the codebase's first database write path

Until now the app has had exactly one connection-opening function,
`db/introspect.py::run_queries(params, sql_list, connect_timeout=10)`, which opens one `psycopg`
connection, `execute`s each statement, `fetchall`s, and closes it in a `finally` — **no `COMMIT`, no
explicit `ROLLBACK`, no `autocommit`** (verified in the code). Apply is the first feature that needs to
write. The design is deliberately conservative:

- **A separate, clearly-named write seam: the new Qt-free module `db/apply.py`.** `run_queries` is
  **never widened** — not with an `autocommit` flag, not with a commit path, not with "just this one
  DDL statement". The read seam stays read-only so that *"does this code write to the database?"* stays
  answerable by **which function is called**, statically, without reading arguments. (Distinct from
  `diff/apply.py::apply_differences`, which mutates an lxml tree and touches no database — different
  package, different domain.)
  Nothing about the two-seam split costs the ladder anything, because the ladder's single
  session/transaction lives entirely on the write side.

> **Settled, not provisional — the competing proposal was withdrawn by its author.** Phase 1 of
> `plans/2026-08-02-ddl-object-editor-and-sandbox.md` instead widened `db/introspect.py::run_queries`
> with `autocommit=`, `notices=`, the `cursor.description is None` guard and a `QueryFailure` exception,
> keeping it "the sole psycopg call site". That design session **conceded the two-seam split on
> 2026-08-02** — *"does this code write to the database? stays answerable by which function is called,
> statically, without reading arguments"* — and dropped the widening task from its plan. Every capability
> that proposal needed now lives on `apply_ddl` (mixed-statement execution, notice capture,
> statement-indexed failure); `QueryFailure` is unnecessary because `ApplyOutcome.statement_index`
> carries the same information **as data** rather than as an exception. `run_queries` is never widened.
> The plan file's Phase 1 text is stale on this point — the spec is authoritative.
- **Shape.** `apply_ddl(params, statements: list[str], *, commit: bool, autocommit: bool = False,
  connect_timeout: int = 10) -> ApplyOutcome`. It opens one connection, executes the statements in
  order, then **explicitly** `commit()`s when `commit=True` and **explicitly** `rollback()`s otherwise —
  never relying on implicit close-time rollback for correctness — and closes in a `finally`.
  `autocommit=True` exists for the single statement PostgreSQL forbids inside a transaction block,
  `CREATE DATABASE` for an app-owned sandbox; it is invalid to combine with `commit=True` and callers
  other than sandbox provisioning must not use it.
- **It must execute a *mixed* statement list — this is a hard correctness requirement, not an
  optimization.** The ladder is necessarily **one** call: the session/transaction has to span
  `SET plpgsql.extra_*` → the DDL → the `plpgsql_check_function_tb` **SELECT**. So `apply_ddl` runs
  statements that return **no** result set (`SET`, `CREATE FUNCTION`, `CREATE TRIGGER`,
  `CREATE EXTENSION`, `CREATE DATABASE`, the bookkeeping `INSERT`) alongside statements that **do**
  (the check SELECT). **In psycopg 3, `cursor.fetchall()` after a non-row-returning statement raises
  `ProgrammingError: the last operation didn't produce a result`** — so `apply_ddl` **must guard on
  `cursor.description is None`** and record an empty row list for that statement instead of fetching.
  Results are returned **positionally 1:1 with the statement list** (`ApplyOutcome.rows`), which is what
  lets the caller attribute each result to the tier that produced it. `db/introspect.py::run_queries`
  does **not** get this guard, because it does not get writes — it keeps its unconditional `fetchall()`
  over read-only queries.
- **Notice capture is part of the seam, because tier 1 has no other channel.**
  `SET plpgsql.extra_warnings = 'all'` returns **no rows**; PostgreSQL delivers its findings as
  asynchronous `WARNING` diagnostics during `CREATE FUNCTION`. `apply_ddl` therefore registers a
  connection notice handler and normalizes each diagnostic into a **psycopg-free frozen
  `Notice{severity, message, detail, hint, context, sqlstate}`** (duck-typed `getattr` over the
  driver object), collected on `ApplyOutcome.notices`. Nothing downstream of the seam ever touches a
  psycopg object.
- **`ApplyOutcome`** captures failure as data rather than raising raw psycopg exceptions:
  `{ok: bool, statement_index: int | None, sqlstate, message, detail, hint, position, rows:
  list[list[tuple]], notices: list[Notice]}` — the diagnostic fields are the same ones `CheckFinding`
  carries, so a failed apply and a validation finding render identically. **`statement_index` is the
  tier-attribution mechanism**: without it, a `plpgsql_check` call that itself fails gets misreported as
  *"your DDL is broken"* — precisely the silent-wrong-result class this project refuses. Its `message`
  renders the driver's primary message **verbatim**, so `test_connection`'s `(False, str(exc))` contract
  and MainWindow's status-bar strings do not regress.
- **Injectable, like every other DB path:** every caller takes `applier: Applier = apply_ddl`, mirroring
  the existing `runner: Runner = run_queries` convention, so the whole suite runs with psycopg absent.
- **Off the GUI thread**, via `self._run_async` (`ui/async_task.py::run_async`) with `ui/busy.py`'s
  `busy_status` — a dead host must never freeze the window (§18.1's precedent).

**Applying to the sandbox** is guarded by the ownership rule in D2 — *the app owns its sandbox databases
by naming convention and refuses to apply DDL to a database it did not create* — enforced as a hard
precondition in `db/sandbox.py` before the applier is ever called.

**Applying to the target database has four hard preconditions, in this order.** A confirmation dialog is
the *last* of them, not the only one.

**1 — Refuse a changed signature. No override, no consent path.** Immediately before applying,
re-introspect the live catalog and compare the buffer's `(schema, name, argtypes)` against it. **If they
differ, refuse**, name the mismatch, and direct the user to the deployment-script path. The reason is
that no confirmation gate *can* catch this: **PostgreSQL identifies a function by
`(schema, name, argtypes)`**, so editing `calc_total(integer)` into `calc_total(bigint)` and applying
makes `CREATE OR REPLACE` **create a second function and leave the old one live**. Every existing caller
keeps hitting the old one. The statement **succeeds**, and the confirmation dialog was **truthful** —
there is nothing for a confirm-gate to refuse. This is a silent wrong result in production, the worst
possible place for one.

> **Stated plainly, because it is a real capability loss and it is the correct trade:** this makes
> **parameter renames and argument-type changes unreachable from Apply.** They belong in the reviewable
> deployment-script path, where the change surfaces as `removed` + `added` and the generator refuses (or
> demands an explicit guarded `DROP`) rather than emitting a bare `CREATE OR REPLACE`. **Routine identity
> must never degrade to `schema.name` anywhere in this pipeline.**

**Related, and different — the failure that is loud.** `CREATE OR REPLACE FUNCTION` also **hard-errors**
on a changed *return type* (*"cannot change return type of existing function"*) or a renamed *input
parameter* (*"cannot change name of input parameter"*). That one fails visibly rather than silently, so
it needs no refusal of its own here — but it is a standing reason not to aim single statements at
production, and the deployment generator must detect it during its pre-generate drift check and refuse
with a named blocker (see "Generate Deployment SQL" below) instead of emitting a script that errors
halfway through on production.

**2 — Gate on a green sandbox validation, with a *named* override.** Apply-to-target is disabled unless
the ladder (D3) last ran green for this buffer. When the sandbox is unavailable, or lacks a required
extension, the user may override — but the override dialog must **enumerate exactly what could not be
checked** (which tiers, and why), never a generic "proceed anyway". Both halves are deliberate:
**refusing silently would be worse than DBeaver; applying unvalidated *is* DBeaver.**

**3 — Apply runs inside a transaction and rolls back on failure. There is no revert snapshot.**
`apply_ddl(..., commit=True)` wraps the statements so a rejected statement leaves the target untouched.
**State the resulting gap rather than leaving it implied: a successful-but-wrong apply has no in-app way
back until §18.2's checkout ships.** The rollback covers what PostgreSQL *rejects*, not what compiles
fine and behaves badly. Recovery today is the user's own backup or their git history — this app has
neither for the target. **This raises the value of landing §18.2 sooner**, and is a reason to prefer the
deployment-script path for anything non-trivial.

**4 — An explicit confirmation naming both the object and the database**, e.g. *"Apply
`public.recalc(integer)` to database `prod` on `db01:5432`?"* — never a generic "Are you sure?". The
confirmation must make *which system* unmistakable, in the same spirit as Diff/Merge's ambiguity gate
(§12) and Generate PHP's Save-vs-Save-As prompt (§19).

Applying to the target is additionally refused outright when the buffer is empty, and the result
(success, or the `ApplyOutcome`'s sqlstate/message) is reported to the Audit panel under `[Check]` and to
the status bar.

**Relationship to §18.3, so the two never read as duplicates.** §18.3 remains the **reviewed batch
deploy** of many objects with the `!`-drift gate, the assembled bundle and the git commit. Single-object
Apply is a **different, narrower, individually-confirmed gesture** with no bundle, no drift gate and no
manifest write. **When both could apply — a project is open and the object is checked out — §18.3's
Deploy is authoritative**; Apply exists for the edit/validate loop, not for rollout. See §18.2's
Apply-vs-Deploy table.

#### D2 — Sandbox source: bring-your-own local PostgreSQL for v1

The user runs their own local PostgreSQL server. The app adds a **second connection profile** with
`role = sandbox` alongside the existing `role = target` connection, persisted through the **same**
generalized `db/config.py` keyed-group scheme §18.2 already requires (§17) — one store, two dimensions
(project key, profile role), never a second settings mechanism and **never a second connection dialog**:
`ui/connection_setup_dialog.py` gains a profile selector, it is not forked. The exact keying scheme
(`ProfileKey`, the `"db"` compatibility group, the sandbox's no-`<ConnectionOptions>`-fallback rule) is
specified once, in §17.

**The sandbox is STATEFUL and accumulates applied edits — that is its purpose.** The earlier framing —
*"apply in a transaction → always `ROLLBACK`; the sandbox database stays pristine across any number of
checks"* — is **retracted** (§28), both by decision (*"we're doing schema changes on a sandbox, rollback
is symbolic"*) and because it was a **design defect**: a pristine-baseline-per-check model **cannot
validate interdependent edits.** Edit `A`, which calls `B`, and also edit `B`; under
rollback-after-every-check, `A` is forever validated against the *old* `B`, and the combination the user
is actually building is never checked at all. The accumulating working set can check it; a pristine
baseline cannot.

- **Rollback survives in exactly one narrow role:** the **"Check without applying"** probe — a
  convenience for *"what would this do?"*, not a safety mechanism, and not threaded through the rest of
  the code.
- **The real safety property is the ownership guard** (below), enforced in **one place**, not rollback
  discipline scattered across call sites.
- The sandbox therefore **is** the desired state, and is the source the deployment script is generated
  from. It is meant to hold your changes between sessions.

**Working-set bookkeeping — the sandbox must be able to say what is in it.** Provisioning creates a
reserved schema `pgtp_editor_sandbox` holding one table:

```
applied(kind text, schema_name text, object_name text, table_name text,
        applied_at timestamptz, text_sha1 text,
        primary key (kind, schema_name, object_name, table_name))
```

- `SandboxSession.apply(ref, ddl_text)` is **one** committing, atomic call: the DDL plus the `applied`
  upsert in a single transaction.
- `SandboxSession.applied() -> list[AppliedObject]` is one `SELECT`, and is what the Sandbox Setup
  dialog's working-set list and the deployment generator both read.
- `SandboxSession.reset()` is **schema-level** — `DROP SCHEMA <each app schema> CASCADE` (never the
  reserved bookkeeping schema) followed by a re-run of the baseline — deliberately **not**
  `DROP DATABASE`, which fails while any session is connected and would need a maintenance-database
  connection and `WITH (FORCE)` (PG 13+). Schema-level reset is just as complete here and avoids all of
  it.
- **`text_sha1` is not bookkeeping garnish.** It is what lets the UI say *"this tab has changed since you
  last applied it"* and what makes **Check** refuse to silently validate a stale version. An in-memory
  list would forget across an app restart **while the sandbox still holds the edits** — a silent
  wrong-state trap.

**Baseline provisioning is not optional — an empty sandbox is actively harmful.** Against an empty
database, tiers 2 and 3 report `relation "pr.equipment" does not exist` for essentially every real
routine: a **false ERROR**, which reads *worse* than "could not check" because it looks like a genuine
finding. Provisioning is therefore core, not deferred.

- The deliberate simplification, and it is a large one: **`plpgsql_check` is catalog-based and reads no
  rows.** It needs relations, columns and types to *exist*; it does not care about primary keys, foreign
  keys, defaults, indexes or data. So the baseline provisions **schemas → types (domains and composites)
  → tables (columns + `format_type` + `attnotnull` only) → views/matviews → routines → triggers**, in
  that order, which is load-bearing.
- Routines are emitted under `SET check_function_bodies = off` so one bad pre-existing routine cannot
  block provisioning; triggers come after routines because `CREATE TRIGGER` resolves its function
  immediately.
- **Deliberately omitted:** PK, FK, `DEFAULT` (which also sidesteps `nextval('seq')` needing sequences),
  indexes, extensions, sequences and all data.
- **Recorded gap, must be closed by the implementation:** `DatabaseSchema` (§17) **models no view
  definitions** — it has `tables`/`routines`/`triggers` only, and `TableInfo` carries columns, not a
  definition. A **`pg_get_viewdef` query must be added** to `db/introspect.py` (plus a `pg_type` query
  for `typtype IN ('d','c')`), or **every routine touching a view fails to compile** in the sandbox and
  the ladder reports false errors.
- `snapshot_for_baseline(target_params, runner=run_queries) -> BaselineSnapshot` lives in
  `db/introspect.py` (reusing `SCHEMA_SQL` + `ROUTINE_TRIGGER_SQL` + the two new queries);
  `build_baseline_sql(snapshot) -> list[str]` lives in `db/sandbox.py` and is **pure — no I/O, no DB**.
  Every identifier is quoted through a strict allowlist helper; a schema named `weird"name` is
  **refused**, never string-interpolated.
- **The incompleteness must be stated in the UI, not buried.** The report's caveats carry it verbatim:
  extensions, sequences, constraints, defaults and data are not reproduced, so findings that reference
  them are unreliable.

**The rest of D2's contract:**

- **Zero bundled bytes.** The app ships no server, no client binaries, and invokes no external process.
  Everything goes over `psycopg` through the two seams above (§17's "no external `psql`" transport rule
  is **not** touched by v1).
- **Capability probe — three states plus "unknown", never a silent "absent".** On sandbox connect,
  `probe(params, runner=run_queries) -> SandboxCapabilities` runs a small module-level `PROBE_SQL` list
  (a sibling of `SCHEMA_SQL`): `current_setting('server_version_num')`; `current_setting('is_superuser')`
  (which works for non-superusers, unlike `pg_user.usesuper`); `SELECT extname FROM pg_extension`;
  `SELECT name FROM pg_available_extensions`; and `current_database()` +
  `shobj_description(oid, 'pg_database')` for the ownership marker. `SandboxCapabilities{server_version:
  tuple[int, ...], is_superuser: bool, installed_extensions: frozenset[str], available_extensions:
  frozenset[str], database: str, owner_marker: str | None, probe_error: str | None}` is cached, and
  **`probe` never raises** — a failure becomes `probe_error`. Its derived property
  `plpgsql_check_state ∈ {installed, installable, absent, unknown}` returns **`"unknown"` whenever
  `probe_error` is set** and never degrades to `"absent"`. What is missing is reported to the user as
  *missing*, never silently skipped (see D3).
- **One-click extension install, behind a pure gate.** `install_plpgsql_check(session)` runs
  `CREATE EXTENSION IF NOT EXISTS plpgsql_check` and is reachable **only through a `SandboxSession`**,
  which by construction means the database is app-owned. Whether to offer it at all is decided by the
  pure `install_gate(caps) -> tuple[bool, str]`: offered only when the state is `installable` **and**
  `caps.is_superuser`; otherwise it returns the exact reason string the UI shows — *"already
  installed."* / *"`CREATE EXTENSION` requires superuser; ask your DBA, or connect the sandbox profile as
  a superuser."* / the platform install text for `absent` (**the app cannot fix that one — it is a C
  library on disk**) / *"could not probe the server."* The install button lives **inside** the Sandbox
  Setup dialog next to the probe result it depends on, not as a separate menu item.
- **Backend interface.** All of this sits behind a Qt-free protocol in `db/sandbox.py` so a managed or
  bundled server can be added later (§29) without the choice leaking into the UI:

  | Member | Contract |
  |---|---|
  | `ensure_running() → dsn` | Return a usable DSN/`ConnectionParams` for the sandbox, starting the server if this backend owns one. For `LocalPostgresBackend` (v1) this is a no-op that returns the configured profile and fails loudly if it cannot connect. |
  | `capabilities() → SandboxCapabilities` | Delegates to `probe` (full field list above) and caches. **The ladder's tier availability is derived only from this** — never from a bare `try: … except: assume absent`. |

- **Ownership rule (safety, non-negotiable — stated verbatim as settled).** The app **owns its sandbox
  databases by naming convention** and **refuses to apply DDL to a database it did not create.** The
  refusal is a hard error surfaced to the user, not a warning: a user who points the sandbox profile at
  their production database must get "this is not a sandbox I created", never an executed DDL statement.
  This is the same "never a silent wrong result" stance as Diff/Merge's ambiguity gate (§12) and §18.4's
  refusal contract. **Now that the sandbox is stateful, this is the *only* safety property left** — it
  carries the weight rollback used to be imagined to carry, so its shape is pinned:

  | Piece | Contract |
  |---|---|
  | `SANDBOX_DB_PREFIX = "pgtp_sandbox_"`, `OWNER_MARKER_PREFIX = "pgtp-editor-sandbox:"` | Two markers, because one is not enough. |
  | `is_app_owned(database, owner_marker) -> bool` (pure) | True only when the name starts with the prefix **and** the `pg_database` comment starts with the marker prefix. **The name alone is spoofable** — a user can name production `pgtp_sandbox_prod`; the comment is written only by our own provisioning. |
  | `ForeignDatabaseError` (psycopg-free) | Message names the database and says plainly *"PGTP Editor did not create this database and will not write to it."* |
  | `open_sandbox(params, runner=run_queries) -> SandboxSession` | Probes, checks ownership, **raises `ForeignDatabaseError` if not owned.** **This is the only gate.** Everything that writes goes through the returned session; nothing else in the codebase re-checks ownership and no write path bypasses the session. Reads (probe, listing, introspecting the *target* for a baseline) are not gated. |
  | `create_sandbox_database(admin_params, name)` | `name` must match `^pgtp_sandbox_[a-z0-9_]{1,40}$` — **validated, not sanitized**: anything else is refused. Runs `CREATE DATABASE` + `COMMENT ON DATABASE … IS 'pgtp-editor-sandbox:<uuid>:<iso8601>'` with `autocommit=True` against the maintenance database, since PostgreSQL forbids `CREATE DATABASE` in a transaction block. This is the **one** `autocommit=True` call in the app, made from `db/sandbox.py` and nowhere else. |

- **The "create a sandbox for me" offer is a mandatory mitigation, not optional polish.** The ownership
  rule collides head-on with the most likely real setup: the realistic sandbox is a local restore of
  production named `myapp_dev`. `open_sandbox` **will** refuse it, and a bare refusal reads as *the tool
  being broken*. So wherever `ForeignDatabaseError` surfaces — principally **Sandbox Setup…** — the
  refusal must be shown **together with an explicit "Create a sandbox database for me" action**
  (`create_sandbox_database` + `build_baseline_sql` seeded from the **target** profile, off-thread with
  `busy_status`). A refusal without a way forward is the fastest route to the user concluding the tool is
  broken. *(A future "adopt this database" flow — stamp the marker after an explicit typed confirmation —
  is worth designing but is deliberately not specified here.)*

#### D3 — The validation ladder

Four tiers, applied in order, each independently available or unavailable. `db/ddl_check.py` (Qt-free)
drives them and returns a report carrying **per-tier outcome** as well as findings.

| Tier | Mechanism | Requires | Catches |
|---|---|---|---|
| 0 | Offline syntax check | nothing | syntax errors while typing — **collapses into tier 2**, see the licensing caveat below |
| 1 | `SET plpgsql.extra_warnings = 'all'` (+ `plpgsql.extra_errors`) before the DDL, **with the notice channel of `db/apply.py` active** | any server, **no superuser** | `shadowed_variables`, `strict_multi_assignment`, `too_many_rows` |
| 2 | Execute the DDL against the app-owned sandbox — **committing** for Apply, rolled back for the "check without applying" probe | write access to an app-owned sandbox DB | whether the DDL actually applies at all (parse + `check_function_bodies` + dependency resolution) |
| 3 | `plpgsql_check_function_tb()` on the object, in the **same session** as tier 2 | the extension installed in the sandbox DB | missing columns, wrong types, unresolved relations, trigger `NEW.x`/`OLD.x` misuse, dead code, missing `RETURN`, volatility violations, SQL-injection risk |

> **Tier 1 correction — it does not work the way an earlier draft of this table claimed (§28).**
> `SET plpgsql.extra_warnings = 'all'` delivers its findings as **asynchronous `WARNING` notices** during
> `CREATE FUNCTION`, and **the statements return no rows at all**. A row-fetching runner therefore yields
> **nothing** from tier 1, forever. Tier 1 is consequently specified as **dependent on the notice-capture
> channel on `db/apply.py`** (the normalized `Notice` records on `ApplyOutcome`, see the write seam): its
> findings are parsed out of `Notice.context` strings of the form
> `compilation of PL/pgSQL function "f" near line 3`. **Where that channel is not available, tier 1 must
> report `unavailable`, not `passed`.** Documenting a tier as working when it silently yields nothing is
> exactly the never-report-clean-when-unchecked violation this section otherwise forbids.
>
> Related and still unpinned: `SET plpgsql.extra_errors` with an invalid value errors *at SET time* once
> plpgsql is loaded, and plpgsql may not be loaded yet in a fresh session — this needs live-server
> confirmation before tier 1 ships.

**Three gestures, three entry points on `db/ddl_check.py`** — they differ in what they commit, and that
difference is user-visible:

| Entry point | Commits? | Notes |
|---|---|---|
| `probe_check(session, ref, ddl_text, caps)` — *"Check without applying"* | no | One call, explicitly rolled back. A convenience, not a guard. |
| `apply_and_check(session, ref, ddl_text, caps)` — *"Apply to Sandbox"* then check | **yes** | Tier 2's outcome **is** the apply's outcome; the working-set row is written in the same transaction. |
| `recheck(session, ref, caps)` — *"Check"* | no (nothing new applied) | Runs the ladder against the sandbox **as it currently stands**. Tier 2 reports `passed` with *"applied &lt;timestamp&gt;"* from the bookkeeping table. **If the caller's buffer hash differs from `applied.text_sha1`, the report carries a caveat saying so** — never silently check a stale version. |

Tier attribution uses the `ApplyOutcome.statement_index` of the statement list the driver built; a
failure in the `plpgsql_check` call must never be reported as *"your DDL is broken"*.

**The hard rule — an unavailable tier reports "could not check", never "clean."** This is the project's
"never a silent wrong result" invariant applied to validation: a green result must mean *checked and
found nothing*, never *not checked*. Concretely, the report distinguishes at least
`passed` / `found_issues` / `unavailable(reason)` / `errored(reason)` per tier, and the UI renders an
unavailable tier as an explicit, visible statement of what was **not** verified — it is never collapsed
into the overall OK state, never hidden behind a preference, and never degraded to a one-off toast the
user can miss.

**Report shape.** `CheckReport{tier0..tier3: TierOutcome, findings: list[CheckFinding], caveats:
list[str]}`, where `TierOutcome{status ∈ passed | found_issues | unavailable | errored, reason, detail}`.
`caveats` carries the honest text that must not be buried: the baseline's missing
extensions/sequences/constraints/defaults/data (D2), `plpgsql_check`'s known blind spots (below), and the
stale-buffer warning from `recheck`. The UI renders **one line per tier, always**, plus one line per
caveat.

**Why tier 2 may be run repeatedly, now that it commits.** PostgreSQL has **transactional DDL**, so the
probe variant leaves zero trace; the committing variant is *meant* to leave a trace — `CREATE OR REPLACE`
is idempotent, so re-applying the same object is a no-op, and the working-set table records what is in
there. Tier 3 runs in the **same session** as tier 2, after the object exists, which is what makes
catalog-based checking possible. (The earlier claim that the sandbox "stays pristine across any number of
checks" is retracted — see D2 and §28.)

**Line-number mapping is a correctness trap and is specified, not left to the implementer.**
`plpgsql_check` reports `lineno` relative to **`prosrc`** (the dollar-quoted body), while the tab's
buffer is **`pg_get_functiondef`** output (header + body). An off-by-header-length line number is exactly
the silent-wrong-result class this project refuses.

- `body_line_offset(buffer_text) -> int | None` locates the opening dollar-quote tag (`$$`, `$function$`,
  `$body$`, …) that begins the body and returns its **1-based line number** `L`.
- `map_lineno(buffer_text, lineno) -> int | None` → `L + lineno - 1`. `prosrc` begins with the newline
  that terminates the `AS $tag$` line, so `prosrc` line 1 **is** line `L`.
- **If the opener cannot be located, `lineno` is falsy, or the result is out of range, return `None`** and
  render the finding **with no line at all**. Never guess.
- **Tier-2 failures need no offset:** they carry a `position` — a character offset into the statement we
  sent, which *is* the buffer — so `line = buffer_text.count("\n", 0, position) + 1` is exact.
- **Tier-1 notices** arrive as `Notice.context` strings (`… near line 3`): regex the line, then apply the
  same `map_lineno`.
- The mapping must be pinned by fixture tests over a **verbatim captured `pg_get_functiondef` output**,
  plus a `LANGUAGE sql` variant, a body opened on the same line as `AS $$`, a `$body$`-tagged variant, a
  buffer with a `$$` inside a comment before the real opener, and a buffer with **no** opener →
  `None`. **A live-server confirmation of the `prosrc` ↔ `pg_get_functiondef` offset is the single
  highest-value live test in this feature and must exist before any finding is rendered against a line.**

**Recovering the applied object's OID for tier 3.** Primary:
`to_regprocedure(format('%s.%s(%s)', schema, name, argtypes))`, built from the `RoutineInfo` the tree
supplied. Fallback, for the case where the user edited the signature: `SELECT oid FROM pg_proc WHERE
xmin = pg_current_xact_id()::text::xid` inside the apply transaction — the catalog row just written is
the one carrying our xid. **The fallback is clever and therefore suspect: it must be confirmed against a
live server before it is relied on.** (Note that for Apply-to-target the signature-change case is refused
outright, above; this fallback exists only for the sandbox.)

**Tier 0 caveat — licensing.** The obvious offline choice, `pglast` (real PostgreSQL grammar via
libpg_query), is **GPL-3.0-or-later**. PGTP Editor is itself GPL-3.0 (§4), so it is usable *today*, but it
would become unusable if the project ever ships under a proprietary license — record the dependency as
license-load-bearing. The license-free alternative, which needs no new dependency at all, is to run a
throwaway `CREATE FUNCTION` inside a rolled-back transaction and let PostgreSQL's own parser be the
syntax checker — i.e. tier 0 collapses into tier 2 when a sandbox is available, and is simply reported
as unavailable when it is not. (§18.4's `format_selection` is **not** a tier: it is a layout formatter
whose tokenize/balance refusal is not a syntax check and must not be presented as one.)

#### Generate Deployment SQL — the deliverable (output rank 1)

**Sandbox = desired state. Production = current state. Output = one reviewed `.sql` migration script,
run once, to upgrade the real database.** The user who has edited three routines in the sandbox and
checked them green gets exactly one file — with an explicit refusal if production moved underneath them,
and an explicit statement of what the script does *not* cover.

**§18.3 reuse, not a parallel engine.** §18.3 already specifies `db/schema_diff.py::diff_schemas`,
`db/migration_gen.py::generate_migration`, `Database ▸ Compare Schemas…` and `Save Migration As…` under
*"one diff/generation engine, two entry points"*. §18.5 **creates those two modules with §18.3's exact
dataclass shape and signatures** and implements **only the routine/trigger cases**; the table/column
cases are defined in the type and left unimplemented. §18.3 later fills them in — **nothing built here is
thrown away, and no second "assemble SQL" mechanism is created.**

> **One divergence from §18.3, stated so it is not read as a contradiction.** §18.3 assumed the desired
> state comes from a checked-in JSON snapshot (`db/schema_snapshot.py`). **A live sandbox is a strictly
> better source** — you can execute against it, so the desired state is provably coherent before it is
> diffed. §18.5 therefore adds a **third** source alongside §18.3's "live connection or snapshot": the
> sandbox. It does **not** build `db/schema_snapshot.py`; that stays §18.3's.

**`db/schema_diff.py` (pure, Qt-free, no I/O).**

- `SchemaDifference{kind ∈ added|removed|changed, object_kind ∈ table|column|routine|trigger, identity:
  str, old_def: str | None, new_def: str | None}` — **verbatim §18.3**. Do not "improve" the field names;
  §18.3's full engine populates the same type.
- `diff_schemas(source: DatabaseSchema, target: DatabaseSchema) -> list[SchemaDifference]`, keyed on
  `DatabaseSchema.routines`/`.triggers`, which `fetch_routines_and_triggers` already populates for **any**
  connection — sandbox or production — with no new catalog query.
- **Routine identity is the full signature**, `schema.name(argtype, argtype)`, built from
  `RoutineInfo.arg_types` — **never** `schema.name`. This is the same load-bearing fact as the
  Apply-to-target signature refusal: a changed argument type is a *different function* to PostgreSQL, so
  it must surface as **`removed` + `added`**, never as `changed`.
- Trigger identity is `schema.table.name`, matching `DatabaseSchema.triggers`' existing key.
- `changed` is decided by **exact text comparison** of `RoutineInfo.source` / `TriggerInfo.definition`.
  Both come from `pg_get_functiondef` / `pg_get_triggerdef` on each side, so formatting is
  server-normalized and a cosmetic-only diff is impossible **within one server major**.
- **`table`/`column` are not implemented.** They are skipped and the omission is **returned**, not
  swallowed (an `unsupported: list[str]` or a module-level `SUPPORTED_OBJECT_KINDS` the caller checks),
  so the UI states *"table and column changes are not compared — §18.3"*. **A silently table-blind diff
  presented as a full migration is exactly the silent-wrong-result class this project refuses.**

**`db/migration_gen.py::generate_migration(differences, *, header: str = "") -> str` (pure,
deterministic — byte-identical output for identical input, so tests are golden-string assertions).**
Emission follows §18.3's CREATE→ALTER→guarded-DROP order with only the first and last stages populated:

1. **Header comment block:** generated-at; sandbox and production connection summaries
   (`user@host:port/db`, **redacted — never a password**, via `debuglog.redacted`'s shape); **both server
   versions**; which content model produced the script; which baseline model the sandbox was provisioned
   from; and the explicit *"table/column changes are not included"* limitation.
2. `added` + `changed` **routines** → the `new_def` verbatim (`pg_get_functiondef` already emits
   `CREATE OR REPLACE`).
3. `added` + `changed` **triggers** → `DROP TRIGGER IF EXISTS <name> ON <table>;` followed by the
   `new_def`. Triggers have no portable `OR REPLACE` below PG 14, and the drop-then-create pair is
   idempotent on every supported major — simpler than branching on the target's version.
4. `removed` routines/triggers → **commented-out** guarded `DROP` statements carrying a `-- REVIEW:`
   marker. **Never live DROP text.** An object absent from the sandbox far more likely means *"the user
   never touched it"* than *"delete this from production"*.

Every statement is `;`-terminated and blank-line separated, so the script is copy-pasteable into `psql`
and diffable in git. A `table`/`column` difference raises the module-defined `UnsupportedDifference`
(Qt-free, psycopg-free); the caller renders the refusal. **Never emit a partial script that silently
drops table changes on the floor.**

> **Module-docstring requirement (a real trap, not pedantry):** both modules land with their
> table/column halves deliberately hollow. The next contributor sees `db/migration_gen.py` and reasonably
> assumes it generates migrations. It generates **routine and trigger** migrations. Each module docstring
> must open with that limitation in its **first sentence**, and `UnsupportedDifference` must be a real,
> raised exception — never a silent skip.

**Dependency ordering — verified, and the obvious tool is the wrong one.** **Use stable alphabetical
ordering by identity, routines before triggers.** Do not make deployment-SQL generation depend on tier 3.

- **PL/pgSQL bodies are not resolved at CREATE time.** With `check_function_bodies = on`, the plpgsql
  validator parses the body's *statement structure* only; the SQL expressions inside it — including calls
  to other functions and references to tables — are parsed and planned lazily, at first execution. So
  `CREATE OR REPLACE FUNCTION a()` whose body calls `b()` **succeeds even when `b()` does not exist.**
  The strongest evidence is this feature's own premise: if CREATE-time validation resolved relations and
  callees, tier 3 would have nothing left to catch. **Forward references between plpgsql routines
  therefore need no ordering at all.**
- **Exception 1 — `LANGUAGE sql` routines** *are* parsed and analyzed at creation, and PG 14+
  `BEGIN ATOMIC` bodies additionally record **real catalog dependencies**. These genuinely need ordering.
- **Exception 2 — triggers.** `CREATE TRIGGER` resolves its function immediately (`pg_trigger.tgfoid` is
  a hard catalog reference) and the table must already exist. "Routines before triggers" is therefore a
  real constraint, not cosmetics.
- **`plpgsql_show_dependency_tb()` is REJECTED for this purpose, despite looking perfect.** It returns
  exactly the `FUNCTION`/`OPERATOR`/`RELATION` dependency set per routine and would drive a clean
  topological sort — but it is a `plpgsql_check` function, so **it covers only plpgsql routines: precisely
  the language that does not need ordering.** It cannot see inside the `LANGUAGE sql` routines that
  actually do. Adopting it would make generating a deployment script depend on tier 3 — an optional,
  per-database, superuser-gated C extension — in exchange for ordering information about the cases that
  were never at risk. **The deliverable must be producible on a bare PostgreSQL with no extensions.**
  Topological ordering is recorded as a possible **follow-on supplement**, never a replacement for
  handling the SQL-language case.
- If any emitted routine's `new_def` is non-plpgsql (detectable from `RoutineInfo.language`, which
  `fetch_routines_and_triggers` already populates — thread it onto the difference), emit a **header
  warning**: *"N non-PL/pgSQL routine(s) are included; statement order may need manual adjustment (their
  bodies are resolved at CREATE time)."* Honest, cheap, non-blocking.

**Mandatory pre-generate drift check.** Before generating, run `fetch_routines_and_triggers` against
production **off-thread** (one read-only introspection call — no new code) and compare it against the
sandbox's baseline-time definitions **for the objects in the applied set**. Any object whose production
definition changed since provisioning is a **`!` drift blocker**, reusing §18.3's *"any `!`-flagged
object blocks the batch"* all-or-nothing discipline, which itself reuses Diff/Merge's §12 ambiguity gate:
**refuse the whole script, name every blocker**, recovery = re-provision or re-apply, then re-run. This
is what stops a deployment script from silently overwriting a production hotfix made during the dev
cycle. The same introspection pass has both signatures in hand, so it is also where the
**`CREATE OR REPLACE` hard-failure cases are caught** — a changed *return type* or a renamed *input
parameter* is refused with a named blocker (*"pr.calc_total: return type changed; a deployment script
cannot replace this in place"*) rather than emitting a script that errors halfway through on production.

**Honest caveats the script must carry, because they are real:**

- **`pg_get_functiondef` text is not stable across server majors**, and sandbox and production are
  frequently different majors. Purely cosmetic rendering differences surface as **phantom `changed`
  entries**, producing a script full of idempotent no-op replacements. Harmless but noisy, and it erodes
  trust in the diff. Mitigation: report **both** server versions in the header and say so prominently
  when they differ. A normalizing comparison is a rabbit hole — do not start it.
- **The baseline's incompleteness (D2) propagates into the deliverable.** A routine valid *in the
  sandbox* may be invalid in production if it relies on a `DEFAULT nextval(...)`, a constraint or an
  extension the baseline omitted. The sandbox is a **structural approximation** of production, not a
  copy; the header must say which baseline model produced it.

**UI flow — review before write.** **Database ▸ Generate Deployment SQL…**, disabled unless a sandbox
profile is configured. Both introspection calls run off the GUI thread (`self._run_async` +
`busy_status`). Guards, each with its own specific message: no sandbox → open Sandbox Setup; empty
applied set → *"nothing has been applied to the sandbox yet"*; drift blockers → the §12-style refusal
naming every blocker; `UnsupportedDifference` → the table/column refusal. On success the script is shown
in a **read-only preview tab** reusing `CodeEditor(language="sql")` (a dynamic tab, appended per §7's
invariant) with a **Save Migration As…** button writing UTF-8 `newline=""`, mirroring `_save_xsd`
exactly. **Do not write a file the user has not read — this is DDL destined for production. The script is
never executed by this app; there is no execute path, not even a disabled one** (§18.3's hard non-goal,
inherited verbatim).

> **Not built here:** §18.3's own **Compare Schemas…** and **Save Migration As…** commands. §18.5 builds
> the engine those two will call; building their UI is §18.3's job, and its settled *"separate sibling
> command, no-project-required"* framing must not be pre-empted by a §18.5-shaped screen. Say so in the
> code comment so the next reader does not "finish" it wrongly.

#### Reuse map — what this feature builds on rather than duplicates

| Need | Existing thing to reuse |
|---|---|
| SQL **reads** | `db/introspect.py::run_queries` — the sole read seam, read-only; every new function takes `runner: Runner = run_queries` so the suite runs with psycopg absent |
| SQL **writes** | the new `db/apply.py::apply_ddl` — the sole write seam (above); `applier: Applier = apply_ddl` injectable the same way. **Never a third connection-opening function.** |
| Connection profile & dialog | `db/config.py::ConnectionParams` + `ui/connection_setup_dialog.py` — add a profile dimension (§17/§18.2); **no second dialog** |
| Diagnostics surface | the existing Audit/Problems panel (§7): `"[Check] SEVERITY line N: message"`, line on `UserRole`, target on `UserRole+1`, click-to-navigate — **no new diagnostics panel** |
| Diagnostic record | the shape of `validation/tier2.py::ValidationIssue{severity, message, line}` |
| Line mapping | `db/ddl_buffer.py::DdlObjectSpan` — translates a per-routine `lineno` into a buffer line (the *within-object* `prosrc` → buffer offset is D3's `map_lineno`) |
| Diff / migration generation | §18.3's `db/schema_diff.py` + `db/migration_gen.py` **shapes and signatures**, created here with the routine/trigger cases only — **one engine, two entry points**; never a parallel generator |
| Production introspection for the drift check | `db/introspect.py::fetch_routines_and_triggers` — already read-only, already exists, no new catalog query |
| Off-GUI-thread work | `ui/async_task.py::run_async` via MainWindow's injectable `self._run_async`, with `ui/busy.py::busy_status` for the status-bar busy state |
| External process (if ever) | `generation/runner.py::GeneratorRunner` (QProcess, streamed lines) — **v1 spawns nothing**; do not write a second process runner |
| Editor widget | `ui/code_editor.py::CodeEditor(language="sql")` + `ui/editor_gutter.py::GutterBookmarkFoldMixin` |
| Formatter | §18.4's `format_selection` — this tab is its first consumer |
| Menu home | the **Database** menu (`main_window.py::_build_database_menu`) — **no new top-level menu** |
| Verifying the sandbox matches | `Database ▸ Compare Schemas…` (§18.3) pointed at the sandbox |

**Findings type.** `db/ddl_check.py::CheckFinding` **mirrors and extends** `ValidationIssue`'s
`{severity, message, line}` shape — the same pattern-extension precedent §18.4 set with
`xsd_verify.Issue` — adding `sqlstate`, `level` (plpgsql_check's raw level string), `position`,
`statement`, `detail`, `hint`, `context` and the object identity. **Do not widen
`validation/tier2.py::ValidationIssue` itself**: its three fields are asserted by existing tests and it
belongs to `.pgtp` structural validation, a different domain.

**Line-number honesty** is specified in full in D3 above (`body_line_offset` / `map_lineno`, the exact
`position`-derived line for tier 2, the `near line N` regex for tier 1, and the mandatory `None` when the
opener cannot be located). It is not restated here.

#### Audit-panel prefix: `[Check]`

Findings from this feature use **`[Check]`** — `"[Check] ERROR line 42: record has no field \"foo\""` —
following the same click-to-navigate convention as `[Validate]`/`[Find]`. It is distinct from §18.4's
`[SQL]` (formatter refusals: layout only, no database) and from §22's `[Lint]` (PHP only). The three-way
reservation is recorded in §7 and on each owning section deliberately: several linter-shaped features
feeding one Audit panel must be distinguishable at a glance, none may annex another's prefix, and no
fourth SQL-ish prefix may be introduced.

#### `plpgsql_check` integration specifics

Verified against the shipped `plpgsql_check--2.10.sql`; these facts **constrain the implementation** and
are recorded so they are not rediscovered the hard way.

- **v2.10.4, MIT** (the `LICENSE` file; `META.json` wrongly claims BSD). Supports PostgreSQL 14–18.
- It is a **C extension, ABI-bound per PostgreSQL major**. The `.so`/`.dll` must already be present on
  the server — the app **cannot** install it over a psycopg connection. Detection, not installation, is
  the app's job.
- **`CREATE EXTENSION` requires superuser** (the control file omits both `trusted` and `superuser`, so
  PostgreSQL's default applies), and the extension is **per-database**. There is **no upgrade path**:
  updating means `DROP EXTENSION` + `CREATE EXTENSION`.
- **Calling** the check functions requires **no** privilege — there is no ACL gate in the source and no
  `REVOKE` in the install script. A DBA-installed extension on a shared server is usable by an ordinary
  user, so *"detect it on the user's own server and use it when present"* is a **first-class supported
  path**, not a fallback.
- **No `shared_preload_libraries` entry is needed** for active mode (`plpgsql_check.mode` defaults to
  `by_function`) — no config edit, no server restart, nothing the app would have to talk a user through.
- Availability, for the honest "how do I get it?" message: Linux
  `apt install postgresql-NN-plpgsql-check` (PGDG) / `dnf install plpgsql_check_NN`. Windows has no
  GitHub release asset, no StackBuilder entry and no upstream CI — only the author's personal build
  (`pgsql.cz`, **2.8.5, PG 17+18, x64 only**, ~350 KB: two DLLs + `.control` + `.sql`).

**API gotchas — all of these are call-shape requirements, not trivia:**

| Fact | Consequence for the caller |
|---|---|
| The parameter is misspelled **`anyelememttype`** (`m` for `n`) | named-notation calls must use the typo verbatim |
| Positional order is `other_warnings, performance_warnings, extra_warnings` — **not** the README's order | **always use named notation**; never rely on position |
| `format` (`text`/`json`/`xml`) exists on `plpgsql_check_function` only, **not** on `_tb` | use `_tb` and consume rows, not a formatted blob |
| `plpgsql_check_function_tb` returns **11 columns**: `(functionid regproc, lineno int, statement, sqlstate, message, detail, hint, level, "position" int, query, context)` | `"position"` **must be double-quoted** in the select list; the 11 columns map 1:1 onto `CheckFinding` |
| `fatal_errors` defaults to true | pass **`fatal_errors => false`** for a GUI, else you get exactly one finding per function |
| Warnings are off by default | pass **`all_warnings => true`** |
| **Trigger functions require `relid`** | omitting it errors *"missing trigger relation"*; pass the table OID, plus `oldtable => t.tgoldtable, newtable => t.tgnewtable` when the trigger declares transition tables |
| `level` values are `error`, `warning`, `warning extra`, `warning performance`, `warning security`, `compatibility` | map to the Audit panel's `SEVERITY` token; keep the raw string in `CheckFinding.level` |

**Known blind spots** (must be stated in the UI's "what was checked" text, per the never-silently-clean
rule): dynamic `EXECUTE`, `refcursor` fetched into a `record`, and temp tables created at runtime.
Escape hatches for false positives are `plpgsql_check_pragma('type: …')` inside the body and
`SET plpgsql.enable_check TO false`.

**Trigger tabs are a second, quieter special case** — easy to get 80% right and silently wrong on the
rest. The tab holds a `CREATE TRIGGER` statement, but tier 3 checks **functions**. So for a trigger tab,
**tier 2 is the `CREATE TRIGGER` itself** and **tier 3 checks the *referenced* function with `relid`
set**. Additionally, `CREATE OR REPLACE TRIGGER` exists only on **PG 14+**: below that the statement list
must be preceded by a `DROP TRIGGER IF EXISTS`, gated on `caps.server_version`.

**Bonus surface, not v1:** `plpgsql_show_dependency_tb()` returns `(type, oid, schema, name, params)` —
a ready-made "what does this routine touch" view that would slot into `BrowserPanel` as a further
relationship angle alongside §18.1's dual grouping. Noted, not designed. **It is explicitly rejected as
a dependency-ordering source for the deployment script** (see "Generate Deployment SQL" above) — it
covers only plpgsql routines, i.e. exactly the ones that need no ordering.

#### Invariants this feature must conform to

1. **Two seams, one direction each:** `db/introspect.py::run_queries` stays the sole **read** seam and
   stays read-only; `db/apply.py::apply_ddl` is the sole **write** seam. Every new path takes
   `runner: Runner = run_queries` / `applier: Applier = apply_ddl` so the whole suite runs without
   psycopg importable. Never a third connection-opening function.
2. Every module this feature adds under `db/` — `apply.py`, `sandbox.py`, `ddl_check.py`,
   `schema_diff.py`, `migration_gen.py` — and `validation/` stay **Qt-free**; only `ui/` imports PySide6
   (§5). The one pre-existing exception, `db/config.py`'s module-scope `QSettings`, is **not** to be
   "fixed" by inventing a second store (§5/§17).
3. Every connection-opening call runs **off the GUI thread** (`self._run_async`) with busy state
   (`ui/busy.py`) — a dead sandbox host must never freeze the window (§18.1's precedent).
4. Any new params type must be redactable through `debuglog.redacted(params)`; the redaction test is
   locked (§25).
5. Config persistence follows the existing pattern: injectable store, loaders tolerate
   absent/unreadable/malformed input and **never raise**.
6. The byte-for-byte `.pgtp` round-trip (§2) is untouched — **this feature never writes the project
   file**, and works with zero `.pgtp` files open (§18's standalone mode).
7. Tests mirror the package layout (`tests/db/test_apply.py`, `tests/db/test_sandbox.py`,
   `tests/db/test_ddl_check.py`, `tests/db/test_schema_diff.py`, `tests/db/test_migration_gen.py`,
   `tests/ui/test_ddl_object_editor.py`); dialogs use `show()`, never `.exec()`; context menus are built
   by a `_context_menu_for(item) -> QMenu | None` helper the test can trigger **without** `exec()`; no
   un-patched modal (§30). **Every Apply confirmation is a test seam** (an injectable `confirm=`
   callable, the `_confirm_close()` precedent) — a test must never be able to reach a real
   apply-to-target prompt, and must never be able to execute DDL by accident.
8. **No live PostgreSQL in the default suite.** Every DB path takes `runner=`/`applier=` and is driven by
   a fake, exactly as `tests/db/test_introspect.py` does today; `db/sandbox.py`'s pure predicates
   (`is_app_owned`, `install_gate`, `build_baseline_sql`) and both diff/generation modules are tested
   directly with no runner at all. The handful of facts that genuinely need a server live in **one
   env-gated file** (`tests/db/test_sandbox_live.py`, skipped unless a sandbox DSN env var is set),
   covering at minimum: `cursor.description is None` for `SET`/`CREATE FUNCTION`/`CREATE EXTENSION`; that
   `plpgsql.extra_warnings='all'` actually delivers notices and its `CONTEXT` matches the `near line N`
   regex; **the `prosrc` ↔ `pg_get_functiondef` line offset** (do not ship rendered line numbers without
   it); `plpgsql_check_function_tb`'s 11-column order, the `anyelememttype` typo and the trigger `relid`
   requirement; the `xmin = pg_current_xact_id()` OID-recovery fallback; that `CREATE DATABASE` requires
   autocommit and schema-level reset works with a live connection open; and the two ordering claims —
   that a plpgsql body calling a nonexistent function **creates fine**, and that the same is **not** true
   for a `LANGUAGE sql` function.
9. **`CenterStage`'s append-only / tail-only dynamic-tab invariant (§7) has a mandatory regression test**
   — this feature is the first to create runtime tabs, and five existing call sites depend on the fixed
   indices staying put.

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
1. **A PHP fold-region provider** for `CodeEditor` — the shared fold *machinery* already exists since the
   2026-08-01 `GutterBookmarkFoldMixin` extraction (§8, `ui/editor_gutter.py`): `CodeEditor` mixes the
   mixin in, overrides `_foldable_region_starting_at` as a lookup into `self._fold_regions`, and exposes
   `set_fold_regions(regions)` for hosts to install regions from outside. What is missing is only the
   **PHP-specific region computation** (brace/`{`…`}` blocks, function/class bodies, heredocs) plus the
   host wiring that calls `set_fold_regions()` — today no host installs regions for JS/PHP, so folding is
   inert there (§8). Mirrors how the DDL editor installs `DdlObjectSpan`-derived regions.
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
- **`[Lint]` is reserved for PHP linting, and only PHP linting.** SQL/plpgsql findings from §18.5's
  sandbox validation ladder use **`[Check]`**, and §18.4's formatter refusals use **`[SQL]`**. The
  three-way reservation is recorded here as well as in §7 and §18.5 deliberately: several
  linter-shaped features feeding one Audit panel must be distinguishable at a glance, and none may
  quietly annex another's prefix.
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
▸ Manual (F1)**. **20 `##` chapters**, in order: Getting Started · The Project Tree · Properties · The
Raw XML Editor · Bookmarks · Find, Replace & Find All · The Code Editor · Caption Management · Schema
Tools · Database Check · DDL Explorer · Table References · Diff / Merge · Validation · Generating PHP ·
A note on busy feedback · Appearance & Layout · Keyboard Shortcuts · The Manual · Troubleshooting: debug
mode. Offline, read-only (no editing/searching, single language).

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
  Select Parent Block (Ctrl+Shift+A), ☐ Auto Parse XML (§9; unchecked by default, in-memory only),
  Preferences.
- **View** (real order and labels): ☑ Project Tree, ☑ Properties Panel, ☐ Find table reference,
  ☑ Audit/Problems Panel, ☑ Raw XML Panel (checked by default), — , Expand All, Collapse All, — ,
  ☐ Light Theme, — , Customize Toolbar… (opens the toolbar customization dialog, §7). The three **dock**
  checkboxes (Project Tree / Properties Panel / Audit/Problems Panel) are bidirectional — closing a dock
  by its title-bar ✕ unchecks the menu item (BUG-007, §7).
- **Bookmarks:** Toggle Bookmark (Ctrl+F2), Next Bookmark (F2), Previous Bookmark (Shift+F2), Clear All
  Bookmarks. Between Tools and Generation. **All four actions follow the active editor tab** (§8): the
  target is resolved at trigger time by `_active_bookmark_editor()` — Edit XSD tab → `stage.xsd_editor`,
  DDL Explorer tab → `stage.ddl_editor_panel.editor`, any other tab → `stage.xml_editor` — and the menu
  never switches/reveals a tab. Target design (2026-08-01, not yet implemented, §8/§13): the whole menu
  and its four actions are disabled together while Caption Mode is active (gutter bookmark toggling stays
  usable).
- **Schema:** Edit XSD, Edit AutoXSD, Verify XSD, Export XSD, Import XSD — five items (§11). Verify /
  Export / Import act on the **active XSD** (curated or learned, per `_xsd_mode`), not curated-only.
  (Go To XSD is **not** a menu item: it is a window-level Ctrl+L `QAction` added via
  `MainWindow.addAction` plus a Raw XML editor context-menu entry; it always forces curated mode.)
- **Database:** Connection Setup…, ⎯, Check: XML→Database, Check: Database→XML, ⎯, ☐ DDL Explorer
  (checkable toggle, §18.1; kept in lockstep with the center tab's ✕). **Target design (2026-08-02, not
  yet implemented)** — everything §18 adds lives in **this** menu; no new top-level menu is created for
  it, and no "locate binary" action is added, because v1 spawns no external process:
  - ⎯ then (§18.5) **Sandbox Setup…** (the `role=sandbox` profile in the same `ConnectionSetupDialog`,
    plus the capability-probe result, the one-click **Install plpgsql_check** button *inside* that dialog
    next to the probe result, the working-set list and **Reset Sandbox**, and — when the configured
    database is not app-owned — the refusal together with the mandatory **"Create a sandbox database for
    me"** offer); **Check DDL Object** (runs the validation ladder against the active DDL object editor
    tab); **Apply to Sandbox**; **Apply to Target Database…** (the ellipsis marks the confirmation naming
    object + database, and it is additionally gated on a green sandbox validation and refused outright on
    a changed signature — §18.5); and **Generate Deployment SQL…** (the feature's rank-1 deliverable;
    disabled unless a sandbox profile is configured). **Check DDL Object / Apply to Sandbox / Apply to
    Target Database…** are **disabled unless a DDL object editor tab is active**, kept in sync on
    `center_stage.currentChanged`; Apply is never automatic and never implied by Save. Sandbox Setup and
    Generate Deployment SQL do **not** require an object tab. There is no "locate binary" action —
    v1 spawns no external process.
  - ⎯ then (§18.2) **New DDL Project…**, **Open DDL Project…**, **Close DDL Project**.
  - (§18.3) **Compare Schemas…** and **Save Schema Snapshot…**.

  ("Format Selection" is **not** a menu-bar item: it is a `Ctrl+Alt+F` action plus a context-menu entry
  scoped to the DDL object editor tab — see §27.)
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
| Ctrl+O / Ctrl+S / Ctrl+Shift+S / Ctrl+W | Open / Save / Save As / Close | Window (Save routes to the active center-stage tab: Raw XML, Edit XSD, or — target design 2026-08-02, §18.5 — the active DDL object editor tab, where Save persists text only and **never** executes DDL, §7) |
| Ctrl+Z / Ctrl+Y | Undo / Redo (single step) | Window |
| Ctrl+F / F3 / Ctrl+Shift+F | Find / Find Next / Find All | The **active center-stage tab's own** `FindReplaceBar`, resolved by `_active_find_bar()` — Edit XSD → `stage.xsd_find_replace_bar`, DDL Explorer → `stage.ddl_editor_panel.find_replace_bar`, the DDL object editor tab → its own bar (§18.5, target design 2026-08-02), otherwise `stage.find_replace_bar` (revealing the Raw XML tab) (§7/§15) |
| Ctrl+R / Ctrl+Alt+Return | Replace / Replace All | Same per-tab routing as Find, but **inert in the DDL Explorer** — that buffer is read-only (`CodeEditor.replace_current_selection` returns early on `isReadOnly()`) — and **live** in the DDL object editor tab (§18.5, target design) (caption: Ctrl+R = Caption Filter) |
| Ctrl+Shift+B / Ctrl+Shift+A | Select Enclosing / Parent Block | Raw XML editor (menu-owned) |
| Ctrl+click / Alt+click | Jump to matching tag / parent tag | Raw XML editor |
| Ctrl+F2 / F2 / Shift+F2 | Toggle / Next / Previous Bookmark | The **active editor tab** — Raw XML / Edit XSD / DDL Explorer, plus the DDL object editor tab (§18.5, target design 2026-08-02) — resolved at trigger time by `_active_bookmark_editor()`, never switching tabs (Bookmarks menu, §8; disabled in Caption Mode, §13 — target design 2026-08-01) |
| double-click (line-number gutter zone) | Toggle bookmark on that line | Raw XML editor gutter (target design 2026-08-01, not yet implemented, §8 — additive alongside the existing single-click 12px bookmark strip; NOT gated by Caption Mode) |
| Ctrl+L | Go To XSD (jump to the attribute's definition in curated.xsd; always forces curated mode) | Window-level QAction (also in the Raw XML editor context menu) |
| Ctrl+Alt+F | **Format Selection** (§18.4's `format_selection` on the current selection; single undo step on success, `[SQL]` Audit lines + transient underline on refusal) | DDL object editor tab only, and only with a non-empty selection (target design 2026-08-02, not yet implemented, §18.5). Also a context-menu item there. `Ctrl+Shift+F` stays Find All. |
| *(no shortcut, deliberately)* | **Check DDL Object** / **Check without applying** / **Apply to Sandbox** / **Apply to Target Database…** / **Generate Deployment SQL…** | Database menu, the DDL object editor tab's context menu, and (for the three check/apply gestures) its button row (§18.5, target design 2026-08-02). Apply is an **irreversible outward effect** and must not be one keystroke away; the target-database variant additionally requires a green sandbox validation, refuses a changed signature outright, and confirms naming the object **and** the database. |
| Ctrl+G | Go to line in XML | Caption grid |
| Ctrl+Shift+B | Bracket-select | Code editor dialog; DDL object editor tab (§18.5, target design) |
| Ctrl+S / Ctrl+W | Save / Cancel | Code editor dialog |
| F1 | Manual | Window |

**§18.5 introduces exactly one new binding** (`Ctrl+Alt+F`, which §18.4 had left TBD). Everything else it
needs joins the **existing** per-tab dispatchers rather than adding shortcuts: `_active_find_bar()`,
`_active_bookmark_editor()` and `_save_active_tab()` each gain one branch.

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
| 2026-08-01 | §8 gutter / bookmarks / folding existed **only** on `XmlEditor`; DDL `EditorPanel`'s `CodeEditor` had none (no gutter/line-numbers/bookmarks/folding, Qt-mono default tab stop) | Generic gutter + bookmark + fold-**state** machinery **extracted into a shared base** — realized as the mixin `GutterBookmarkFoldMixin` in the new module `ui/editor_gutter.py` — with a **pluggable foldable-region provider**, used by **both** `XmlEditor` (XML-span provider) and the DDL editor (DDL-object provider over the `DdlObjectSpan` index); DDL editor also gains a **4-character tab stop** — one gutter implementation, never a parallel second |
| 2026-08-01 | §8 gutter + line bookmarks were **Raw-XML-only** — the "Edit code…" JS/PHP event-handler editor (`CodeEditorDialog`/`CodeEditor`) had no gutter, no line numbers and no bookmarks | The shared `GutterBookmarkFoldMixin` (`ui/editor_gutter.py`) sits on **`CodeEditor` itself**, so **every** code editor — including the JS/PHP event-handler dialogs — now shows the line-number gutter and supports line bookmarks (folding inert there: no regions installed). Surfaced as a side effect of the extraction and **explicitly kept by the project owner** rather than gated per language: line numbers in a code editor are conventional, and gating would add a second code path. Bookmarks stay **session-only, per-document**; the "Edit code…" `CodeEditorDialog` is a dialog rather than a center-stage tab, so the Bookmarks menu does not reach it (its gutter strip stays mouse-only) |
| 2026-08-01 | The Bookmarks menu/shortcuts remained bound to the **Raw XML editor only** (the row above, same date) | **Per-tab dispatch:** `_build_bookmarks_menu` captures no editor; each of the four actions resolves its target at **trigger** time via `main_window.py::_active_bookmark_editor()` — Edit XSD tab → `stage.xsd_editor`, DDL Explorer tab → `stage.ddl_editor_panel.editor`, any other tab → `stage.xml_editor` — mirroring `_active_find_bar` but **without** its `_reveal_raw_xml_tab()` side effect (toggling a bookmark must never switch tabs). The `CodeEditorDialog` remains out of the menu's reach |
| 2026-08-01 | §18.4 formatter reuses **`_SQL_KEYWORDS` imported from `pgtp_editor/ui/code_editor.py`** as its shared dialect source (settled design, same date) | **Relocated, not imported:** the set lives in the Qt-free core as `pgtp_editor/sql/keywords.py::SQL_KEYWORDS` (a `frozenset` of 115 lowercase members; added `elseif`, `elsif`, `exit`, `continue`, `foreach`, `reverse`, `intersect`, `while`) and `ui/code_editor.py` binds `_SQL_KEYWORDS = SQL_KEYWORDS` (same object, so `_highlighter._keywords is _SQL_KEYWORDS` still holds). Importing from `ui/` would have inverted §5's dependency rule (core must never import ui; `sql/` must stay Qt-free, now test-enforced by `tests/sql/test_package_purity.py`) — still exactly one shared source of truth for the highlighter's `language="sql"` mode and the formatter, just on the correct side of the arrow |
| 2026-08-01 | §18.4 module shape sketched in §5's tree as a single `sql/formatter.py` ("name TBD") with entry point `format_selection(text) -> FormatResult` and a `FormatResult` that "is either the reformatted text or a refusal" (settled design, same date) | **Five modules** as shipped — `sql/__init__.py` façade + `keywords.py`/`issues.py`/`tokenizer.py`/`formatter.py` — with `format_selection(text: str, *, indent_unit: str = "    ") -> FormatResult`, `FormatResult(ok, text, issues)` whose `text` on refusal is the input **verbatim** (an `ok`-ignoring caller cannot corrupt the selection), frozen `Issue(message, start, end, start_line, start_col, end_line, end_col, fatal=True)` with `.line == start_line` for `xsd_verify.Issue` parity, and a public `tokenize(text) -> list[Token]` on `sql/tokenizer.py` (the façade's `__all__` stays the four documented names) |
| 2026-08-01 | Dark theme = Fusion + `dark_palette()` **palette-only** (the BUG-004 fix above, same date) — Fusion+palette alone rendered checkable menu indicators outlined near-black on the dark menu background (BUG-010) | Dark = Fusion + `dark_palette()` **+ the QDarkStyleSheet dark QSS** (`qdarkstyle>=3.2`, new runtime dependency, MIT-credited in About); light **always** clears the stylesheet (`app.setStyleSheet("")`) so round-trips leave no stale QSS; the palette stays applied beneath the QSS for palette-reading custom widgets; side effect: `app.style().objectName()` is empty in dark mode (`QStyleSheetStyle` wrapping) |
| 2026-08-01 | §8 `XmlEditor` ran the O(document) structure rescan (`_rescan_structure`) and code-region rebuild (`_refresh_code_region_selections`) **synchronously on every `textChanged`** — i.e. a full `toPlainText()` copy + whole-document pass per keystroke — and `_update_matching_tag_highlight` **rescanned when it found `_spans` stale** on `cursorPositionChanged` (BUG-015) | Both rescans **debounced** behind a parented single-shot `self._rescan_timer = QTimer(self)`, `_RESCAN_DEBOUNCE_MS = 250`, scheduled by `_on_text_changed_schedule_rescan` (which absorbs the `_applying_theme` skip) and executed by `_rescan_now()` (structure → code regions → matching-tag highlight → gutter repaint); `_update_matching_tag_highlight` now **suppresses** the highlight when spans are stale instead of rescanning (a rescan there would run per keystroke via the caret and defeat the debounce; stale offsets would paint a wrong range anyway); two exact-structure carve-outs bypass the debounce — `setPlainText` calls `_rescan_now()` synchronously (document swap) and `_toggle_fold` calls `_flush_pending_rescan()` first, with the flush deliberately **not** in `_foldable_region_starting_at` (the gutter `paintEvent` calls it per visible block). Measured 216.1 → 2.0 ms per typed character on a 1 MB / 21,002-block document |
| 2026-08-01 | §8 `XmlSyntaxHighlighter` block state = **odd-`"`-parity per line** (`_has_unterminated_quote(text, start)`), never re-synchronising, so one parity-flipping `"` cascaded a Qt re-highlight to the **end of the document** on every such keystroke (5,972 `highlightBlock` calls / 45 ms on a 6,002-block file; BUG-016) | **Tag-aware four-state machine** — `STATE_NORMAL`/`STATE_IN_UNCLOSED_STRING`/`STATE_IN_TAG`/`STATE_IN_SINGLE_QUOTED` computed by the method `XmlSyntaxHighlighter._end_state(text, state)` over the state-changing characters matched by `_STATE_CHARS_RE = [<>"']` — where a quote only opens a value **inside a tag** (quotes in text content, i.e. PHP handler bodies, are inert), plus the **`<` resync rule**: a raw `<` inside a quoted value snaps the state back to `STATE_IN_TAG`, bounding the cascade to a block or two (trade-off: a raw `<` inside an attribute value ends that value's highlighting early — the document is invalid XML anyway and it self-corrects). `_has_unterminated_quote` deleted; continuation handled by `_continued_string_end(text, quote)`; helpers kept as **methods** so `debuglog.py`'s `("ui.xml_editor", "XmlSyntaxHighlighter.")` flood exclusion still covers them |
| 2026-08-01 | §7 a theme toggle re-applied formats via **one synchronous whole-document `rehighlight()`** inside `XmlEditor.apply_theme_colors`'s `_applying_theme` guard — which blocked the UI ~1.5 s+ on a multi-MB document (BUG-013) | **Two-stage, guarded per batch:** `apply_theme_colors` swaps colors and schedules `_rehighlight_for_theme` (coalesced via `_theme_rehighlight_pending` + the parented single-shot `_theme_kickoff_timer`), which rehighlights the **visible region** first, then a parented 0 ms `_theme_sweep_timer` drives `_theme_sweep_tick` over the rest of the document at `_THEME_SWEEP_BLOCKS_PER_TICK = 400` blocks per event-loop turn; the `_applying_theme` guard wraps **every** batch, so `is_applying_theme()` still keeps both dirty handlers and the editor's own rescan bookkeeping quiet |
| 2026-08-01 | §7/§15 Ctrl+F & the Edit-menu Find/Replace actions routed to **Raw XML or Edit XSD only** — with the DDL Explorer tab active they fell through to the default branch, which *revealed the Raw XML tab* and used its bar | `_active_find_bar()` gains a **DDL Explorer branch** returning `stage.ddl_editor_panel.find_replace_bar`, so Ctrl+F on the DDL tab searches the DDL buffer in place. **Ctrl+S stays asymmetric on purpose:** `_save_active_tab()` still branches only Edit-XSD-vs-project, because the DDL buffer is read-only and has no save path |
| 2026-08-02 | §18.2 checked-out object file path = flat **`ddl/<schema>.<name>.sql`** for every object kind (2026-07-29) | **Disambiguate-only-when-needed** scheme: a routine that is the sole holder of its `schema.name` keeps `ddl/<schema>.<name>.sql`; an **overloaded** routine appends its argument types (`ddl/public.fmt(integer).sql`); a **trigger** is always table-qualified (`ddl/<schema>.<table>.<trigger>.sql`). The flat scheme collided — Postgres allows function overloads sharing `schema.name`, and trigger names are unique only per table. Accepted trade-off: the first overload's file must be **renamed** (deliberately, `git mv`) when a second overload appears. Path computation, the overload decision and filename sanitization live in the new pure Qt-free `db/ddl_project.py` |
| 2026-08-02 | §18.2 "Checkout-to-edit" as a **single paragraph** — right-click in `BrowserPanel`/`EditorPanel` opens "a new, single-object editable tab", with no design for how a project comes to exist, what the tab is, how it is titled/closed/saved, or how `CenterStage` hosts a runtime-created tab (2026-07-29) | Full editable-tab design (target design): two right-click entry points with named widget idioms; a **"DDL project required"** Create…/Open…/Cancel dialog plus three Database-menu project actions; checkout semantics (seed-from-live when the file is absent, open-from-disk when present, **never silently overwrite local from the DB**, drift surfaced but **never blocking edit**); `ui/ddl_object_editor.py::DdlObjectEditorPanel`, one tab per object, re-Edit **focuses** the existing tab, short-identity title + dirty marker, tooltip, MainWindow-owned close confirm (the Edit-XSD pattern), **deliberately no `.bak`** (git is the history — an intentional divergence from §19); `CenterStage` gains **dynamic tabs appended after the fixed set** and addressed by a **key→widget map**, never a remembered index. *(Later the same day: the tab material was relocated from §18.2 to §18.5 and the project-required dialog re-scoped to project actions only — see the de-duplication and scoping rows below.)* |
| 2026-08-02 | §18.4's trigger binding **TBD**, its host surface undesigned, and its Audit-panel prefix unchosen — "§26/§27 gain no entry" (2026-08-01) | **Settled: `Ctrl+Alt+F`** (plus a **"Format Selection"** context-menu item), scoped to the DDL object editor tab and enabled only with a selection; `Ctrl+Shift+F` stays **Find All**. Refusals report to the Audit panel under the **`[SQL]`** prefix with a **transient underline** over the `Issue`'s exact span; success replaces the selection as a **single undo step**. §26/§27 now carry the binding. Still unimplemented — the host tab does not exist yet |
| 2026-08-02 | §18.1's "explicitly phase 2" write-back sketch: the editable DDL surface = the **multi-object `EditorPanel` buffer made editable in place**, pushing `CREATE OR REPLACE FUNCTION …` straight to the live DB with the diff detected per `DdlObjectSpan` | The editable surface is a **separate single-object tab type** (`ui/ddl_object_editor.py::DdlObjectEditorPanel`, right-click ▸ Edit… from `BrowserPanel` or from a span in `EditorPanel`), and `EditorPanel` is read-only **permanently**, not provisionally — a regenerated multi-object browsing buffer cannot carry per-object dirty state, per-object validation or per-object apply, and it conflicts with §18.2's file-per-object model. Nothing is ever pushed to a database from `EditorPanel` |
| 2026-08-02 | Two parallel design sessions specified the **same** editable single-object DDL tab under two names in two places — `ui/ddl_object_editor.py::DdlObjectEditorPanel` described inside §18.2 ("the DDL Editor surface"), and `ui/ddl_object_panel.py` ("name TBD") described inside a separate §18.5 | **De-duplicated to one specification:** the module/class is **`ui/ddl_object_editor.py::DdlObjectEditorPanel`** everywhere (§5/§7/§8/§18.1–§18.5/§26/§27), and the tab is specified **once, in §18.5**, where the sandbox lives — validation and the edit→validate→apply loop are one feature. §18.2 is renamed **"Projects, checkout & state markers"**, keeps only the project/file-naming/marker/manifest material, and *references* the tab: checkout changes only its injected load/save pair and adds marker rendering. The `CenterStage` dynamic-tab requirement (fixed indices never shift; key→widget map), the two right-click entry points with the `EditorPanel`-retains-spans amendment, and the Format Selection block all moved from §18.2 into §18.5 unchanged in substance |
| 2026-08-02 | **Scoping: "build full §18.2 first"** — the editable tab was specified as part of the git-project/checkout workflow, so a project, `ddl/` files, `.ddlproject/deployed.json` and `*`/`!` markers were prerequisites for editing one object | **Reversed by the project owner after seeing both designs: §18.5's scoping wins.** The tab is **project-decoupled in v1** — no `ddl/` folder, no manifest, no markers required to edit one object; it loads from the live introspected definition. It is written against an **injected load/save pair**, not a hard-coded source, so §18.2 layers on later by swapping only *where the buffer loads from and saves to*. Operative rationale, preserved verbatim in §18.5 D1: *"a git project, a manifest, a hash scheme and a marker recompute is a large prerequisite in front of 'edit one function and find out whether it compiles'."* Build order is now §18.1 → §18.5 → §18.2 → §18.3 |
| 2026-08-02 | §18.2: *"Saving writes to that local file **only** — it never touches the live DB directly (DB writes only happen via the reviewed §18.3 deploy step)"* — the editable tab had no path to a database at all | **Save and Apply are two distinct, explicit user gestures**, never automatic and never implied by each other: **Save** persists the edited text (buffer in v1, `ddl/*.sql` once checked out) and touches no database; **Apply** executes the DDL against a database. **Apply targets BOTH the sandbox and the target database, each confirm-gated** — the sandbox behind §18.5's naming-convention ownership rule, the target behind an explicit confirmation **naming the object and the database**. §18.3 remains the **reviewed batch deploy** with the `!`-drift gate and is **authoritative whenever both could apply**; single-object Apply is a narrower, individually-confirmed gesture that writes no manifest and makes no commit (§18.2's Apply-vs-Deploy table) |
| 2026-08-02 | §18.5's deliberately-open question *"what apply commits to in a project-less v1"* — candidates were (a) the target database via a confirm-gated `CREATE OR REPLACE` or (b) only the local buffer, deferring all durable writes to §18.2/§18.3 | **Resolved: both destinations, each its own confirm-gated gesture** (sandbox and target), per the row above. Removed from §29 as an open question |
| 2026-08-02 | §17/§18 single-seam assumption: `db/introspect.py::run_queries` is the **only** connection-opening function and is implicitly read-only (verified: it `execute`s + `fetchall`s and closes in a `finally`, never committing). One competing draft proposed making it **the write path too**, adding an `autocommit: bool = False` parameter and relying on close-time implicit rollback | **Rejected in favor of a separate, clearly-named write seam:** the new Qt-free module **`db/apply.py::apply_ddl(params, statements, *, commit, autocommit=False)`** — the codebase's **first database write path** — with **explicit** `commit()`/`rollback()` (never implicit close-time rollback) and an `ApplyOutcome` that captures failure as data. `run_queries` is **never widened** and stays the read-only read seam, so *"does this code write to the database?"* remains answerable by **which function is called**. Injectable as `applier: Applier = apply_ddl`, mirroring `runner: Runner = run_queries`. Never a third connection-opening function |
| 2026-08-02 | §17/§18.1 assumed a **single** connection profile — one live "target" database per session (`db/config.py`, fixed QSettings group `"db"`), with §18.2's only planned generalization being a **project key** | **Two** profiles: the existing `role = target` plus a new **`role = sandbox`** (§18.5 D2), persisted through the **same** generalized keyed-group scheme in `db/config.py` — one store, two dimensions (project key + profile role), one `ConnectionSetupDialog` with a profile selector. Not a second settings mechanism and not a second dialog |
| 2026-08-02 | §18.5 read as *"an editable tab with a lint target"* — the editable single-object tab and its Save/Apply gestures were the headline, and no deployment artifact was specified at all | **Outputs explicitly ranked, Apply demoted:** **(1) Generate Deployment SQL is THE deliverable** — sandbox = *desired state*, production = *current state*, output = one reviewed `.sql` migration script run once to upgrade the real database, built on `db/schema_diff.py` + `db/migration_gen.py` **to §18.3's exact `SchemaDifference` shape and signatures**, implementing the routine/trigger cases and leaving table/column to §18.3 (honouring *"one diff/generation engine, two entry points"*, with a raised `UnsupportedDifference` rather than a silent skip); **(2) the stateful sandbox** as accumulating executable desired state; **(3) per-object Save / Apply** as a convenience and the §18.2 precursor. Build order re-ranked accordingly — the deployment script is built last (it is worthless without validation) and is the first thing the user cares about. Also settled here: **stable alphabetical ordering, routines before triggers** (plpgsql bodies are not resolved at CREATE time, so forward references need no ordering; `LANGUAGE sql`/`BEGIN ATOMIC` routines and triggers are the real exceptions), with **`plpgsql_show_dependency_tb()` explicitly REJECTED** as the ordering source — it covers only plpgsql routines, precisely the ones that need no ordering, and would make the deliverable depend on an optional superuser-gated C extension |
| 2026-08-02 | §18.5 D2/D3: *"apply in a transaction → always `ROLLBACK`"*; *"the sandbox database stays pristine across any number of checks — no cleanup step, no accumulating garbage"*; *"validation writes nothing durable anywhere: everything it does inside the sandbox is rolled back"* | **Retracted — the sandbox is STATEFUL and accumulates applied edits; that is its purpose.** Owner's framing: *"we're doing schema changes on a sandbox, rollback is symbolic."* It was also a **design defect**: a pristine-baseline-per-check model **cannot validate interdependent edits** — edit `A` which calls `B`, and also edit `B`, and `A` is forever checked against the old `B`. Rollback survives **only** as the narrow *"check without applying"* probe, a convenience and not a guard. **The ownership guard is now the only safety property** and is pinned accordingly (`SANDBOX_DB_PREFIX` **and** a `pg_database` comment marker, because a name alone is spoofable; `is_app_owned` pure; `ForeignDatabaseError`; `open_sandbox` as the single gate). Adds the `pgtp_editor_sandbox.applied` working-set table with `text_sha1`, schema-level `reset()`, and **mandatory baseline provisioning** (an empty sandbox makes tiers 2–3 *actively harmful* — a false `relation … does not exist` ERROR reads worse than "could not check"): schemas → types → tables (columns only) → views → routines → triggers, deliberately omitting PK/FK/defaults/indexes/data because `plpgsql_check` is catalog-based and reads no rows. **Recorded gap:** `DatabaseSchema` models no view definitions, so a `pg_get_viewdef` query must be added or every routine touching a view fails to compile. **R5 mitigation is mandatory:** the realistic sandbox is a local restore named `myapp_dev`, `open_sandbox` refuses it, and the refusal reads as the tool being broken — so the *"create a sandbox for me"* offer ships with the refusal, not as later polish |
| 2026-08-02 | §18.5 Apply-to-target gated **only** by an explicit confirmation naming the object and the database | **Four hard preconditions, the confirmation being the last.** (1) **A changed signature is refused outright — no override, no consent path.** PostgreSQL identifies a function by `(schema, name, argtypes)`, so editing `calc_total(integer)` into `calc_total(bigint)` and applying makes `CREATE OR REPLACE` **create a second function and leave the old one live**; every existing caller keeps hitting the old one, the statement **succeeds**, and the confirmation dialog was **truthful** — no confirm-gate can catch it because there is nothing to refuse (R14). This deliberately makes parameter renames and argument-type changes **unreachable from Apply**, which is correct: they belong in the reviewable script path. Recorded alongside it, R13: `CREATE OR REPLACE FUNCTION` **hard-errors** on a changed *return type* or a renamed *input parameter*, which fails loudly but is a standing reason not to aim single statements at production — the deployment generator refuses those as named blockers during its drift check. (2) **Gated on a green sandbox validation, with an override that NAMES what could not be checked** — refusing silently would be worse than DBeaver; applying unvalidated *is* DBeaver. (3) **Runs in a transaction and rolls back on failure, with no revert snapshot** — stated explicitly: **a successful-but-wrong apply has no in-app way back until §18.2's checkout ships**, since the rollback covers what PostgreSQL rejects, not what compiles fine and behaves badly; this raises the value of landing §18.2 sooner. (4) The confirmation, unchanged |
| 2026-08-02 | §18.5 D3 tier 1: *"`SET plpgsql.extra_warnings = 'all'` … catches `shadowed_variables`, `strict_multi_assignment`, `too_many_rows`"* — documented as a working tier over the existing row-fetching runner | **Corrected — as specced the tier yielded nothing.** Its findings are delivered as **asynchronous `WARNING` notices** and the statements **return no rows**, so a row-fetching runner discards them entirely. Tier 1 is now specified against a **notice-capture channel** on the write seam (a psycopg-free normalized `Notice{severity, message, detail, hint, context, sqlstate}` collected on `ApplyOutcome.notices`), with findings parsed from `Notice.context`'s `near line N` and mapped through `map_lineno`; **where that channel is unavailable the tier reports `unavailable`, never `passed`.** Related correction: **tier 2 cannot reuse a plain `fetchall()` path** — psycopg 3 raises `ProgrammingError` on `fetchall()` after `SET`/`CREATE FUNCTION`/`CREATE EXTENSION`, so the write seam **must guard on `cursor.description is None`** and return results positionally 1:1 with the statement list (the earlier claim that tier 2 *"needs no new write path — it is the existing runner, used as-is"* was wrong). Line mapping is likewise pinned rather than left open: `body_line_offset`/`map_lineno` (`prosrc` line 1 **is** the dollar-quote opener's line), the exact `position`-derived line for tier-2 failures, and a mandatory **`None`** (render with no line) when the opener cannot be located — never a guess |
| 2026-08-02 | §5 dependency rule listed **`db/*`** among the modules that "are Qt-free and unit-testable without a `QApplication`" | **Factually wrong claim corrected** (pre-existing error; the code was never at fault): `db/config.py` imports `QtCore.QSettings` **at module scope**, because the connection store *is* QSettings. §5 now **enumerates** the genuinely Qt-free `db/` modules (`introspect`, `compare`, `rename`, `ddl_buffer`, plus the target-design `apply`/`sandbox`/`ddl_check`/`ddl_project`/`schema_diff`/`migration_gen`) and names `config.py` as the one accepted exception — **not** to be "fixed" by inventing a second settings/secrets store, which §17/§18.5 explicitly reject |
| 2026-08-02 | §26/§27 named the ladder gesture **"Validate DDL Object"**, a single menu action, with no deployment entry | **"Check DDL Object"**, matching the `[Check]` Audit prefix and `db/ddl_check.py`, and **three distinct gestures** — *Apply to Sandbox* (commits), *Check* (`recheck` against the sandbox as it stands), *Check without applying* (the rolled-back probe) — surfaced on the tab's own button row as well as the menu and context menu; the Database menu additionally gains **Generate Deployment SQL…**, and the one-click *Install plpgsql_check* lives **inside** Sandbox Setup next to the probe result rather than as a fourth menu item |
| 2026-08-02 | §7 stated the append-after-the-fixed-set / key→widget-map rule for dynamic `CenterStage` tabs as a one-clause aside, with the underlying fragility left implicit | **Promoted to an explicitly stated invariant with a mandatory regression test:** append-only creation (`addTab`, never `insertTab`) and tail-only removal, because the stored fixed indices are **load-bearing in five verified places** — `_active_find_bar`, `_active_bookmark_editor`, `_save_active_tab`, `_on_ddl_navigate_requested` and every `CenterStage.hide_*` (plus `_on_tab_close_requested`'s index dispatch, which must gain a widget-type branch *before* any index comparison). One `insertTab` ahead of the fixed set silently re-points all of them |
| 2026-08-02 | §18.4 recorded semantic/existence linting (do the referenced tables/columns/functions exist?) as *"a separate, explicitly deferred idea — not designed here"*, a forward pointer only | **Designed, in §18.5**, as the sandbox-backed **four-tier validation ladder** (`db/ddl_check.py` + `db/sandbox.py`, `okbob/plpgsql_check`), with the hard rule that **an unavailable tier reports "could not check", never "clean."** It remains **entirely outside** `format_selection`'s refusal gate, which stays tokenize/balance-only and offline. Findings report under **`[Check]`**, distinct from §18.4's `[SQL]` and §22's `[Lint]` — a three-way prefix reservation recorded in §7, §18.4, §18.5 and §22 |

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
- **~~§18.4 formatter host, shortcut and audit prefix~~ — RESOLVED 2026-08-02 (§18.5):** the host is the
  DDL object editor tab (`ui/ddl_object_editor.py::DdlObjectEditorPanel`), the trigger is `Ctrl+Alt+F`
  plus a "Format Selection" context-menu item (selection-only), and refusals report under the `[SQL]`
  Audit prefix with a transient underline over the `Issue` span. §26/§27 now carry the binding. The
  wiring is still unbuilt because the host tab is unbuilt — that is a *not-yet-implemented* item, not an
  open question. **Still not open:** whether an auto-format mode exists — it does **not**, by explicit
  decision (§18.4).
- **~~What "Apply" writes to in a project-less v1 (§18.5)~~ — RESOLVED 2026-08-02:** **both** the
  sandbox and the target database, each its own explicit, confirm-gated gesture, through the new
  `db/apply.py` write seam; Save and Apply are separate gestures; §18.3's reviewed batch deploy stays
  authoritative when both could apply (§18.2/§18.5, ledger §28).
- **Overload-rename git handling (§18.2):** when a second overload of an already-checked-out routine
  first appears, `ddl/public.fmt.sql` must become `ddl/public.fmt(integer).sql`. *When* the tool performs
  that rename (eagerly at the next introspection, lazily at the next checkout of either overload, or only
  on explicit user confirmation), and whether it shells out to `git mv` at all — given §18.2's stated
  preference for keeping correctness-critical logic independent of git plumbing — is unresolved. Doing
  nothing is not an option: two overloads would otherwise contend for one path.
- **The deployment script's content model (§18.5)** — **(a) working set** (everything in the sandbox's
  `applied` table; already available, needs no extra connection, but may carry no-op statements for
  objects the user touched then reverted, and **cannot see production changing underneath the user**) vs.
  **(b) true diff against production at generate time** (`diff_schemas(sandbox, production)` — exactly
  the delta, catches drift by construction, at the cost of one extra read-only introspection). The
  mandatory pre-generate drift check is specified either way, which buys (b)'s single real safety benefit
  at a fraction of its scope; and because `diff_schemas` is written source-agnostic, switching is a
  one-line change at the call site. **Unresolved — and whichever way it goes, the script header must
  state which model produced it.**
- **Transaction-wrapping the generated deployment script (§18.5)** — PostgreSQL has transactional DDL, so
  `BEGIN; … COMMIT;` around the whole script makes deployment atomic, a very strong property for exactly
  this use case. But it changes how the user's own deploy tooling must invoke it. Candidate: emit the
  `BEGIN`/`COMMIT` pair **commented out** in the header with a one-line explanation and let the user
  choose. **Nobody has actually made this decision.**
- **Execution against the sandbox (§18.5)** — running a function and seeing its results is not designed.
  It is **the difference between a validator and an IDE**, and the sandbox makes it safe in a way DBeaver
  cannot. Scope it as a follow-on feature or fold it into v1 — undecided.
- **`db/routine_refs.py` (§18.1's one unbuilt piece)** — XML↔routine cross-referencing, answering *"which
  `.pgtp` pages break if I change this function?"* before a deployment script is generated. **No other
  tool can do this**, and it is the XML↔DB sync the owner describes as the point of the app (§1). Not
  designed; a strong candidate for the next design pass rather than an open question about existing
  design.
- **Project-relative paths when the repo moves (§18.2):** `project.json`, `deployed.json` and the
  per-project connection key are all anchored to the project. Whether the QSettings connection key is the
  absolute project path (breaks on move/clone) or a project id stored in `project.json` (survives, but
  needs generating and can be duplicated by a copy-paste of the folder), and whether the optional `.pgtp`
  link is stored relative to the project root or absolute, are unresolved.

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

1. **Keep this file in sync — it is the single write target for specification content.** Whenever a
   design decision is **settled** (a new feature designed after brainstorming, an intentional change to
   an existing feature, or a shipped feature that diverges from what this document says), the agent
   writes it **directly into this file** using latest-wins reconciliation — from the dispatching prompt,
   the feature's plan under [`docs/superpowers/plans/`](plans/), and the changed code — updates the
   affected section(s), and appends a row to the [Supersession Ledger](#28-supersession-ledger) for any
   override. It never leaves two contradictory statements in the body.
   **`docs/superpowers/specs/` is frozen historical record:** no new dated spec files are ever created
   there and the existing ones are never edited; they are read only for rationale and to back the
   ledger's evidence (per [`CLAUDE.md`](../../CLAUDE.md)).
2. **Gate brainstorming.** Whenever brainstorming runs for a new idea, the agent first locates where the
   idea belongs in this spec — flagging any existing feature that already covers most of it and any
   near-duplicate that should be *extended* rather than *forked*. The goal is cohesive, complex features
   over parallel functionalities that differ only marginally; the up-front design cost is deliberately
   accepted to avoid the larger cost of building then correcting/overwriting redundant work.

When editing: change the body to reflect the new decision, move the old decision into the ledger (do not
leave it in the body), update `Last synthesized`, and keep section numbers/anchors stable where possible.
