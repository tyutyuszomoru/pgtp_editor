# PGTP Editor — Consolidated Specification

> **Status:** living document · **Last synthesized:** 2026-07-21
> **Source of truth:** this file is the single reconciled specification for PGTP Editor.
> It is synthesized from the dated design specs under [`docs/superpowers/specs/`](specs/) using a
> **latest-wins** rule: where a later spec overrode an earlier decision, only the later decision
> is stated in the body, and the change is recorded in the [Supersession Ledger](#20-supersession-ledger).
> Maintained by the **`spec-maintainer`** agent (`.claude/agents/spec-maintainer.md`) — see
> [§27 Maintenance protocol](#27-maintenance-protocol).

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
11. [Schema learning & labeling](#11-schema-learning--labeling)
12. [Diff / Merge](#12-diff--merge)
13. [Captions](#13-captions)
14. [Columns](#14-columns)
15. [Search, Find All & Table References](#15-search-find-all--table-references)
16. [Validation](#16-validation)
17. [Database](#17-database)
18. [PHP generation (vendor) & Save](#18-php-generation-vendor--save)
19. [re_phpgen — own generator & gap loop](#19-re_phpgen--own-generator--gap-loop)
20. [In-app manual](#20-in-app-manual)
21. [Debug mode](#21-debug-mode)
22. [Consolidated menu bar](#22-consolidated-menu-bar)
23. [Consolidated keyboard shortcuts](#23-consolidated-keyboard-shortcuts)
24. [Supersession ledger](#24-supersession-ledger)
25. [Open questions](#25-open-questions)
26. [Testing policy](#26-testing-policy)
27. [Maintenance protocol](#27-maintenance-protocol)

---

## 1. Purpose & scope

PGTP Editor is a **PySide6 (Qt6) desktop tool** for editing SQL Maestro PostgreSQL PHP Generator
("PHPGen" / the "vendor tool") `.pgtp` XML project files. It targets **`.pgtp` format version 22.8**.

**In scope:** parsing, viewing, structurally editing, diffing/merging, validating, and DB-checking
`.pgtp` files; invoking the vendor generator; and (as a separate sub-project) reverse-engineering the
vendor's `.pgtp`→`.php` transformation.

**Hard boundary:** `.pgtp` → `.php` compilation is **strictly one-way and owned by vendor tooling**.
PGTP Editor never edits or generates PHP as part of the editing workflow. (The `re_phpgen`
sub-project, §19, reconstructs the transformation in a *separate repo* — it does not change editor
behavior.)

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

**Licensing:** project is **GPL-3.0**. About box credits BoomslangXML (conceptual prior art),
QCodeEditor (MIT, ported). Authors: **Botond Zalai-Ruzsics** and **MDS — Maintenance Data Services**
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
├── schema_learning/   # vendored XSD-synthesis engine + storage + settings index
│   ├── model.py, parser.py (defusedxml), types.py, xsd_gen.py
│   ├── storage.py     # schema_model_path / schema_xsd_path (AppData)
│   └── settings_index.py  # kind/labels helpers, enum_hint, known_attributes/known_values
├── db/                # PostgreSQL introspection & comparison (Qt-free logic)
│   ├── config.py, introspect.py (psycopg lazy), compare.py, rename.py
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
`caption_scan.py`, `annotate_schema_values_dialog.py`, `schema_viewer.py`, `db_check_panel.py`,
`connection_setup_dialog.py`, `table_references_panel.py`, `manual_panel.py`, `about.py`, `icons.py`.

**Dependency rule:** `model/` touches lxml; nothing in `model/` or `ui/` depends on `diff/`; pure-logic
modules (`search`, `history`, `caption_scan`, `settings_index`, `tier2`, `db/*`, `analysis/*`,
`type_map`, `from_table`, `xml_structure`) are Qt-free and unit-testable without a `QApplication`.

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
  `edit_properties`; and `representations: list[RepresentationVisibility]`.
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
tree**, **Contents** (manual), **Database Check**, and **Table references** tabs (the latter two hidden
until invoked). Center is a tabbed `CenterStage` (Raw XML [default-visible working tab], Diff/Merge,
Caption Management, Manual — non-Raw-XML tabs hidden until invoked). Bottom is a persistent
**Audit/Problems** panel (`QListWidget`) shared by `[Schema]`, `[Validate]`, `[Find]`, `[PHP]` lines.
Right dock is the **Properties** panel.

**Document state:** `_dirty` + `_set_dirty()` (title gets " *"); editor `textChanged` marks dirty;
load/save/revert clears. `.bak` (single, overwritten, `shutil.copy2`) is written before overwriting an
existing file on save — never on Save-As to a new path, never on a failed/no-op write.
`_write_project_text(path)` writes editor `toPlainText()` as UTF-8 with `newline=""` (byte-preserving).
`_current_project_path` is normalized to `str`.

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

**Theme:** View ▸ "Light Theme" checkable toggles default vs `light_palette()` on the app; persisted in
`QSettings("MDS","PGTP Editor")`, re-applied at startup.

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

**Selection right-click ▸ "Find"** prepends to the standard context menu when a selection exists; emits
`find_selected_text(str)` → MainWindow reveals Raw XML + prefills the Find bar. **Line-wrap** toggle
lives in the editor's right-click context menu (checkable), not the View menu.

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
per-language `_CodeHighlighter` (JS / PHP keyword sets, strings, `//`+`#` line comments, `/* */`,
numbers), auto-close + selection-wrap for `()[]{}`/quotes, **Ctrl+Shift+B** bracket-select via pure
`enclosing_bracket_span(text,pos)`. `CodeEditorDialog(QDialog)` hosts it with `saved(str)`/`cancelled`
signals, **Ctrl+S** save / **Ctrl+W** cancel; never `.exec()` in tests.

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

## 11. Schema learning & labeling

Vendored XSD-synthesis engine feeds an ever-growing **per-user** schema `Model` from every opened
`.pgtp`, used for hover hints and autocomplete. `defusedxml`-based, independent of `model/parser.py`.

**Storage** (`schema_learning/storage.py`, `QStandardPaths.AppDataLocation`, injectable `base_dir`):
`schema_model_path()`→`schema_model.json`, `schema_xsd_path()`→`schema.xsd`. Per-user, not git-tracked;
`schema.xsd` regenerated on every enrichment.

**Model:** `Model.paths[chain]["attributes"][attr]` where `chain` = slash-joined tag path from root
(e.g. `PGTPProject/Pages/Page/Editor`, no indices). Each attribute entry carries engine-owned
`type`/`values`/`overflowed`/`attr_seen_count` **plus** labeler-owned `labels: dict[value→label]` and
`kind: "setting"|"content"|None`. The engine is purely additive and must never read/clear `labels` or
`kind`; readers use `.get(...)`. Enum overflow (`> ENUM_MAX_VALUES` → `overflowed=True, values=None`)
leaves stale labels harmlessly.

**Auto-enrich:** only **File ▸ Open** triggers it (appended to the end of `open_project_file` success
path, wrapped in try/except → one `[Schema] Could not update…` audit line on failure). Reports via
`_SCHEMA_REPORT_TEMPLATES` (`new_element`/`new_attribute`/`new_value`/`enum_overflow`/`now_optional`);
> 20 events collapse to one summary line. Diff/Merge file pickers do **not** enrich.

**settings_index.py** (Qt-free): `is_enum_candidate`, `attribute_kind`, `enum_hint(model, chain, attr)`
(one-line hint for **settings** only, e.g. `editFormMode — 1 = modal · 2 = new page · 3 = inline`),
`unused_setting_attributes` (kind-filtered), `known_attributes(model, chain, present)` (broad, **not**
kind-filtered), `known_values(model, chain, attr)` (→ `[(value, label|None)]`).

**Schema menu:** top-level "Schema" menu (between Diff/Merge and Tools — see consolidated menu):
- **Annotate Schema Values…** — a **two-pane** labeler (`annotate_schema_values_dialog.py`): left pane
  one row per enum-candidate `(path, attribute)` with a **Kind** combo (Unclassified/Setting/Content),
  #values, #labeled; filters = kind (default **Unclassified + Settings**) + text (path/attribute). Right
  pane = the selected Setting's values with editable labels. Kind/label edits re-save immediately.
  (This replaced the original flat one-row-per-value table.)
- **Open XSD** and **Open XSD Labels (JSON)** — read-only non-modal `SchemaViewerWindow` (`schema_viewer.py`,
  a read-only `XmlEditor`).

**Editor integration:**
- **Hover** over an attribute name/value in an opening tag shows a `QToolTip` with `enum_hint(...)`
  (settings only). Editor gets the model via `set_schema_model(model)` (MainWindow passes the freshly
  enriched model; `None` disables). Pure resolver `attribute_at_position(text,pos)`.
- **Right-click ▸ Add attribute ▸** submenu from `unused_setting_attributes` (kind-filtered); inserts
  ` name=""` with caret between quotes via pure `insert_attribute(text, tag_open_pos, name)`.
- **Ctrl+Space autocomplete:** `_CompletionPopup(QListWidget)` (frameless, non-modal). Attribute stage
  uses `known_attributes` (broad); on choose, inserts ` name=""` and, if `known_values` non-empty,
  chains a value popup (displays `value` or `value = label`, inserts bare value). ↑/↓ navigate,
  Enter/Tab/click choose, Esc/focus-out cancel, printable chars prefix-filter. Guarded by
  `not isReadOnly()` + model present + `enclosing_open_tag(...)` resolving.

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
(Ctrl+R), Replace All (Ctrl+Alt+Return). Each handler reveals the Raw XML tab then delegates to the same
`FindReplaceBar` method the button uses. (The old "Find & Replace…" Ctrl+H stub was removed.)

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
  traversal.
- `db/rename.py` (pure): `rename_field(text, old, new)` / `rename_table(...)` = literal global
  attribute replace.

**UI:** **Database** menu (Connection Setup…, Check: XML→Database, Check: Database→XML).
`ConnectionSetupDialog` (host/port/database/user, password EchoMode.Password, Test + status, plaintext
caveat; API `set_params`/`params()`/`test()`). `DbCheckPanel` (header: direction + `user@host:port/db` +
mismatch count; "Show only mismatches" toggle; `QTreeWidget` with `(T)`/`(V)`/`(M)` prefixes, `(×N)`
invocation counts, datatypes, PK underline, `(fk)`, ✓/✗ glyphs). Signals `rename_requested(kind, old)`
(XML→DB not-found nodes), `jump_requested(kind, name)` (double-click → Raw XML), and
`create_requested(kind, name)` (DB→XML table nodes). Added to `left_tabs` as a hidden tab.

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

## 18. PHP generation (vendor) & Save

Implements §6.6. Shells out to the vendor generator; because the generator reads from disk, this also
owns File Save / Save As.

- `generation/config.py` (`generator_config.json` in AppData; injectable `generator_config_dir`):
  `load_executable_path`/`save_executable_path` (`executable_path` key) and `re_phpgen_root` (§19).
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

## 19. re_phpgen — own generator & gap loop

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

---

## 20. In-app manual

English Markdown manual bundled at `pgtp_editor/resources/manual.md` (via
`[tool.setuptools.package-data]`). `ui/manual_panel.py`: `load_manual_text()` (via `importlib.resources`),
`parse_chapters(md)→list[Chapter{level, title}]` (ATX headings, skips fenced code), `ManualPanel(QTextBrowser)`
(read-only, external links, `set_markdown`, `scroll_to_chapter(index)`), `ManualContentsPanel(QWidget)`
(`QTreeWidget`, `chapter_selected(int)`). Center-stage **Manual** tab + left-dock **Contents** tab; **Help
▸ Manual (F1)**. 13 chapters incl. Generating PHP, Validation, Keyboard Shortcuts, Troubleshooting/debug.
Offline, read-only (no editing/searching, single language).

---

## 21. Debug mode

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

## 22. Consolidated menu bar

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
- **Schema:** Annotate Schema Values…, Open XSD, Open XSD Labels (JSON).
- **Database:** Connection Setup…, Check: XML→Database, Check: Database→XML.
- **Tools:** Manage Captions…, Caption Filter… (Ctrl+R in caption context), Reparse Raw XML into Tree,
  Validate Project, Compare/Merge Two Files…, Next/Previous Difference, Apply Changes to Target.
- **Generation:** Locate PHP Generator Executable…, Generate PHP…, Open Output Folder, panGen (Generate
  Own PHP), rePHPgen (Analyze Gap), Save reJSON…, Locate panGen Runtime….
- **Help:** Manual (F1), Open Log Folder, Documentation, About.

Toolbar default: Open, Save, Undo, Redo, Find, Validate, Generate (customizable).

---

## 23. Consolidated keyboard shortcuts

| Shortcut | Action | Context |
|---|---|---|
| Ctrl+O / Ctrl+S / Ctrl+Shift+S / Ctrl+W | Open / Save / Save As / Close | Window |
| Ctrl+Z / Ctrl+Y | Undo / Redo (single step) | Window |
| Ctrl+F / F3 / Ctrl+Shift+F | Find / Find Next / Find All | Window |
| Ctrl+R / Ctrl+Alt+Return | Replace / Replace All | Window (caption: Ctrl+R = Caption Filter) |
| Ctrl+Shift+B / Ctrl+Shift+A | Select Enclosing / Parent Block | Raw XML editor (menu-owned) |
| Ctrl+click / Alt+click | Jump to matching tag / parent tag | Raw XML editor |
| Ctrl+F2 / F2 / Shift+F2 | Toggle / Next / Previous Bookmark | Raw XML editor |
| Ctrl+G | Go to line in XML | Caption grid |
| Ctrl+Shift+B | Bracket-select | Code editor dialog |
| Ctrl+S / Ctrl+W | Save / Cancel | Code editor dialog |
| F1 | Manual | Window |

---

## 24. Supersession ledger

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

---

## 25. Open questions

- **Ability-code numeric mapping** (`*AbilityMode`): integer→label mapping still unknown; derive
  empirically. No longer blocking — powers editor hover tooltips.
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

## 26. Testing policy

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

## 27. Maintenance protocol

This document is maintained by the **`spec-maintainer`** agent (`.claude/agents/spec-maintainer.md`),
which has two duties:

1. **Keep this file in sync.** Whenever a new dated spec lands under `docs/superpowers/specs/` (or an
   existing one changes), the agent folds it in using latest-wins reconciliation, updates the affected
   section(s), and appends a row to the [Supersession Ledger](#24-supersession-ledger) for any override.
   It never leaves two contradictory statements in the body.
2. **Gate brainstorming.** Whenever brainstorming runs for a new idea, the agent first locates where the
   idea belongs in this spec — flagging any existing feature that already covers most of it and any
   near-duplicate that should be *extended* rather than *forked*. The goal is cohesive, complex features
   over parallel functionalities that differ only marginally; the up-front design cost is deliberately
   accepted to avoid the larger cost of building then correcting/overwriting redundant work.

When editing: change the body to reflect the new decision, move the old decision into the ledger (do not
leave it in the body), update `Last synthesized`, and keep section numbers/anchors stable where possible.
