# Create Page / Detail / Lookup from a DB Table or View — design

**Date:** 2026-07-19
**Branch:** re-phpgen
**Status:** approved (Approach A), proceeding to implementation

## Goal

From the existing **Database → XML** treeview (`DbCheckPanel` in the
`db_to_xml` direction), let the user right-click a table/view node and:

1. **Create new page** — synthesize a full `<Page>` and **insert it at the end**
   of `Presentation/Pages` in the current editor buffer, then jump to and
   structurally select the new page.
2. **Create new detail** — synthesize a `<Detail>` (nested `<Page>` +
   `<MasterForeignKeyColumnMap>`) and **copy it to the clipboard**; tell the
   user it is on the clipboard to paste into the page they want.
3. **Create new lookup** — synthesize a `<Lookup .../>` element and **copy it to
   the clipboard**; tell the user.

Fidelity target: **full parity** with what PHP Generator emits for a new table.
Parity rules are authored in a declarative map and calibrated against golden
fixtures (the current baseline is derived from the observed sample corpus;
byte-exact parity will be tuned once a "freshly-added table" golden `.pgtp` is
supplied).

## Approach — A: pure builder module + declarative type map

Qt-free synthesizer isolated from the UI, mirroring the existing `db/` (logic)
vs `ui/` (wiring) split.

### Module layout

```
pgtp_editor/generation/type_map.py    NEW  declarative pg-type → presentation rules + page-level defaults
pgtp_editor/generation/from_table.py  NEW  build_page / build_detail / build_lookup (schema + table -> lxml element + serialized str)
pgtp_editor/db/introspect.py          EXT  capture FK target (referenced schema.table.column) for detail-link inference
pgtp_editor/ui/db_check_panel.py      EXT  context menu in db_to_xml direction; emits create_requested(kind, table_name)
pgtp_editor/ui/main_window.py         EXT  handlers: insert page into buffer / copy detail|lookup to clipboard; store last schema
tests/generation/test_type_map.py     NEW
tests/generation/test_from_table.py   NEW  golden-fixture + structural tests
tests/generation/fixtures/*.xml       NEW  golden page/detail/lookup fragments
```

### Boundaries

- `from_table` depends only on `db.introspect` dataclasses + `type_map` + lxml.
  No Qt, no I/O — fully unit-testable without a DB or GUI.
- `type_map` is pure data + tiny helpers — the single source of truth for parity
  rules; parity refinement happens here.
- UI layer constructs no XML; it only calls the builder and routes the result
  (insert vs clipboard).

## The synthesizer (`from_table.py`)

Public API (all pure):

```python
def build_page(schema: DatabaseSchema, table_key: str) -> etree._Element
def build_detail(schema: DatabaseSchema, table_key: str) -> etree._Element
def build_lookup(schema: DatabaseSchema, table_key: str) -> etree._Element
def serialize(element: etree._Element, indent: int) -> str   # deterministic, tab-indented to match samples
```

### Page structure produced

`<Page type="table" tableName=... fileName=... caption=... shortCaption=...>`
with page-level default attributes from `type_map.PAGE_DEFAULTS`
(recordsPerPage=20, NavigatorPosition=3, ability modes, export/print
availability, contentEncoding=UTF-8, etc. — the observed dominant values), then:

- `<BeforeGridText/>`, `<DetailedDescription/>`
- `<ColumnPresentations>` — one `<ColumnPresentation>` per column (see mapping)
- `<Columns>` — all 10 representations
  (`List, View, Edit, Insert, QuickFilter, FilterBuilder, Print, Export,
  Compare, MultiEdit`), each listing every column; PK columns get
  `visible="false"` in `Edit, Insert, Compare, MultiEdit`.
- `<Details/>` (empty)

`fileName` = schema-qualified table with `.`→`_`; `caption`/`shortCaption` =
humanized table name (last path segment, `_`→space, title-cased).

### Column → presentation mapping (`type_map.py`)

For each `ColumnInfo`, keyed on a normalized pg `data_type`:

| pg data_type (normalized)                | ViewProperties        | Format                    | EditProperties                     | selectedFilterOperators |
|------------------------------------------|-----------------------|---------------------------|------------------------------------|-------------------------|
| integer/bigint/smallint/numeric/decimal/real/double | `type="text"` | `<Format type="number" decimalSeparator="."/>` | `type="textBox" maxLength="0"`     | `1573119` (numeric)     |
| char/varchar/text (and unknown fallback) | `type="text"`         | —                         | `type="textBox" maxLength="<n|0>"` | `1589247` (string)      |
| boolean                                  | `type="checkBox"`     | —                         | `type="checkBox"`                  | `1573119`               |
| date                                     | `type="text"`         | —                         | `type="date"`                      | `1573119`               |
| timestamp/timestamptz/time              | `type="text"`         | —                         | `type="date"`                      | `1573119`               |

- `caption` per column = humanized field name (`_`→space, title-cased).
- `maxLength` for varchar/char pulled from the pg type modifier when present
  (e.g. `character varying(30)` → `30`); else `0`.
- The table is intentionally small and declarative so parity tuning is a data
  edit, not code surgery.

### Detail structure produced (`build_detail`)

```xml
<Detail caption="<humanized child table>">
  <Page type="table" tableName="<child>" fileName="" ...detail page attrs... >
    ...same ColumnPresentations + Columns as a page...
    <Details/>
  </Page>
  <MasterForeignKeyColumnMap>
    <FieldMap masterColumnName="<parent PK or ''>" foreginColumnName="<child FK or ''>"/>
  </MasterForeignKeyColumnMap>
</Detail>
```

- Detail-page attrs match a top-level page except `fileName=""` (per samples).
- **FK inference:** if the child table has exactly one FK column, use it as
  `foreginColumnName`, and its referenced column as `masterColumnName`. If
  ambiguous (0 or >1 FKs) or the referenced column is unknown, emit **empty
  placeholders** (`masterColumnName="" foreginColumnName=""`) for the user to
  fill after pasting. Note the vendor's misspelling `foreginColumnName` is
  reproduced verbatim (required by the format).

### Lookup structure produced (`build_lookup`)

```xml
<Lookup tableName="<table>" linkFieldName="<PK>" displayFieldName="<display>"
        lookupFilter="" useLookupOrdering="true" lookupOrdering="0"/>
```

- `linkFieldName` = the table's single PK column (if exactly one), else `""`.
- `displayFieldName` = first non-PK text-like column, else the PK, else `""`.

## Introspection extension (`introspect.py`)

`ColumnInfo` gains `fk_target: str | None` — the referenced `"schema.table.column"`
for FK columns (None otherwise). Sourced by extending `_CONSTRAINTS_SQL` to also
return, for `contype='f'`, the referenced relation+column via
`pg_constraint.confrelid`/`confkey` joined to `pg_attribute`. Existing
positional unpacking in `fetch_schema` is updated; the injectable `runner=`
test seam is unchanged (fakes just return the extra column). This is what lets
`build_detail` fill `masterColumnName`.

## UI wiring

- `DbCheckPanel`: add `create_requested = Signal(str, str)` (kind, table_name).
  In `_on_context_menu`, when `self._direction == "db_to_xml"` and the clicked
  node is a **table** node, show a menu with three actions
  ("Create new page from this table", "Create new detail…", "Create new
  lookup…") that emit `create_requested("page"|"detail"|"lookup", name)`.
  The existing `xml_to_db` rename menu is unchanged.
- `main_window`:
  - In `_run_db_check`'s `on_result`, store `self._last_db_schema = schema`.
  - Connect `create_requested` to `_on_db_create_requested(kind, name)`:
    - Guard: schema present and contains `name`; else status message.
    - **page:** `build_page` → serialize → insert text immediately before the
      closing `</Pages>` tag in the editor buffer (matched by indentation), via
      `setPlainText` (marks dirty, snapshots). Then locate the new page and
      `navigate_to_line` + `select_enclosing_block`. **Duplicate handling:** if a
      `<Page tableName="name">` already exists (or the derived `fileName`
      collides), show a warning dialog offering *proceed with de-duplicated
      fileName* or *cancel* (test seam like `_prompt_rename`).
    - **detail / lookup:** `build_detail` / `build_lookup` → serialize →
      `QGuiApplication.clipboard().setText(...)`; status message "Detail/Lookup
      for <table> copied to clipboard — paste it into the target page."

## Testing

Per project policy (`CLAUDE.md`): TDD while implementing; `feature-tester`
agent + `docs/TEST_LOG.md` entry gate completion.

- `test_type_map.py`: mapping correctness per pg type; caption humanization;
  maxLength extraction; filter-operator defaults.
- `test_from_table.py`:
  - golden-fixture equality for a small synthetic table (page/detail/lookup)
    against hand-authored `fixtures/*.xml` — locks structure & attribute set;
  - structural assertions (all 10 representation lists present; PK visibility
    rules; empty-placeholder FK path; single-FK inference path).
- `test_introspect.py` (extend): FK-target extraction from fake constraint rows.
- UI: extend `tests/ui/test_db_check_panel.py` for the new signal/menu (no
  modal `.exec`), and a `main_window` handler test with a canned schema
  verifying page-insert-before-`</Pages>` and clipboard set for detail/lookup
  (patch clipboard / warning seam).

## Open items / parity caveats

- Baseline defaults are corpus-derived, not vendor-confirmed. Byte-exact parity
  needs a golden "freshly-added table" `.pgtp` from PHP Generator; when supplied,
  calibrate `type_map` and re-baseline the golden fixtures.
- `caption` default rule (humanization) is an assumption; adjust to match the
  golden fixture.
- Ability-mode numeric codes are taken as the observed dominant values; the
  re-phpgen spec flags these as probe-derived in general, but for a *new page*
  the dominant sample values are the right default.
