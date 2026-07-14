# Column representation-visibility in Properties — Design

**Date:** 2026-07-14

## 1. Purpose

When a Column is selected in the tree, the Properties panel currently shows only the column's own `ColumnPresentation` attributes (and sub-elements). A `.pgtp` Page also has a sibling `<Columns>` block that lists, per **representation** (`List`, `View`, `Edit`, `Insert`, `QuickFilter`, `FilterBuilder`, `Print`, `Export`, `Compare`, `MultiEdit`), a `<Column fieldName="…"/>` entry whose `visible="false"` marks the column hidden in that representation. This feature surfaces that per-representation visibility for the selected column so the user can see, at a glance, where a column shows and where it's hidden.

## 2. Scope

**In scope**
- Parse the sibling `<Columns>` block for each Page / inner-Page and attach a per-column, ordered list of representation visibilities to each `ColumnNode`.
- Show those in the Properties panel (for a Column) as a divider row + one row per representation with value `visible` / `hidden` / `— (not listed)`, each navigating to that column's `<Column>` entry line in the representation.

**Out of scope**
- Editing visibility (read-only, like the rest of the panel).
- Any representation other than the fixed 10 (confirmed uniform across both sample files: each of the 10 tags appears exactly once per `<Columns>` block).
- Column-order information within a representation (only visibility is surfaced).
- Diff/merge or write-back of the `<Columns>` block.

## 3. Facts (verified against the samples)

- `<Columns>` is a direct child of a Page (or a Detail's inner `<Page>`), a sibling of `<ColumnPresentations>`.
- Its children are exactly the 10 representation elements, each containing `<Column fieldName="…"/>` entries (one per column, in every sample).
- `visible="false"` → hidden; the attribute absent (or any other value) → visible. Entry opening tags are single-line.

## 4. Model

### 4.1 `RepresentationVisibility` (new, `pgtp_editor/model/nodes.py`)
Frozen dataclass:
- `name: str` — the representation element tag (`"List"`, `"Edit"`, …).
- `visible: bool | None` — `True` visible, `False` hidden, `None` = the column has no entry in this representation (defensive; not seen in samples).
- `sourceline: int | None` — the `<Column>` entry's source line (for navigation); `None` when `visible is None`.

### 4.2 `ColumnNode.representations` (new field)
`representations: list[RepresentationVisibility] = field(default_factory=list)` — ordered by the fixed representation order (see §4.3). Empty list when the container has no `<Columns>` block.

### 4.3 Parser (`pgtp_editor/model/parser.py`)
- Module constant `REPRESENTATION_NAMES = ("List", "View", "Edit", "Insert", "QuickFilter", "FilterBuilder", "Print", "Export", "Compare", "MultiEdit")` — the fixed order.
- New helper `_parse_representations(container_el) -> dict[str, list[RepresentationVisibility-lite]]`… — actually simpler: a helper `_column_representations(columns_container_block, field_name)` is awkward; instead build **once per container** a map `field_name -> list[RepresentationVisibility]` and index into it while building each `ColumnNode`:
  - `_build_representation_index(container_el) -> dict[str, list[RepresentationVisibility]]`:
    - `columns_block = container_el.find("Columns")`; if `None` → return `{}` (every column gets an empty list).
    - For each `name` in `REPRESENTATION_NAMES`, `rep_el = columns_block.find(name)`; if `rep_el is None`, skip that representation entirely (it contributes nothing for any column).
    - For each present `rep_el`, iterate its `<Column>` children; for each, `fn = entry.get("fieldName")`, record `(name, visible = entry.get("visible") != "false", sourceline = entry.sourceline)` keyed under `fn`.
    - After collecting, for each field_name produce a list in `REPRESENTATION_NAMES` order; for a representation where the field has no entry, append `RepresentationVisibility(name, visible=None, sourceline=None)` **only if that representation element was present** (so a column genuinely missing from a present list shows "— (not listed)"); representations whose element is absent are omitted for everyone.
  - In `_parse_columns`, build the index once from `container_el`, then set `representations=index.get(field_name, [])` on each `ColumnNode`.
- This stays in the parser (the only lxml-touching module); `RepresentationVisibility` is a plain dataclass in `nodes.py`.

## 5. Properties panel (`pgtp_editor/ui/properties_panel.py`)

- Add `_rows_for_column(column_node) -> list[RowSpec]`:
  - The existing attribute rows (`_rows_for_attrib_node(column_node)`).
  - If `column_node.representations` is non-empty: a divider `RowSpec(property_label="— Representations —", value="", target_line=None, attr_name=None)`, then one `RowSpec` per representation: `property_label=rep.name`, `value = "visible" if rep.visible else ("hidden" if rep.visible is False else "— (not listed)")`, `target_line=rep.sourceline`, `attr_name=None`.
- Point the `"column"` entry of `_ROW_BUILDERS` at `_rows_for_column` (header unchanged: `Column: {field_name}`).
- Navigation: existing `_on_row_clicked` already handles `target_line is None` (divider / not-listed → no-op) and, since `attr_name is None` for representation rows, it navigates to the line without attempting attribute selection — i.e. it jumps to the `<Column>` entry line. No panel-navigation code changes needed beyond the new row builder.

## 6. Testing

- **Parser (`tests/model/test_parser.py`):** a fixture Page with a `<Columns>` block →
  - each `ColumnNode.representations` is length-10 in `REPRESENTATION_NAMES` order;
  - `visible="false"` → `visible is False`; absent attr → `True`; sourcelines populated;
  - a column missing from one present representation → that entry has `visible is None`;
  - a Page with **no** `<Columns>` block → `representations == []` for every column (no crash);
  - a Detail's inner-Page columns get their representations too.
- **Properties (`tests/ui/test_properties_panel.py` or the existing properties tests):** `_rows_for_column` yields the attribute rows, then the divider, then 10 representation rows with correct `visible`/`hidden`/`— (not listed)` values and target lines; divider + not-listed rows are non-navigating; Page/Detail/Event builders unchanged.
- **Real-sample smoke (skips if `sample/*.pgtp` absent):** for `dev_Ferrara.pgtp`, a known column shows expected values (e.g. `id` → `Edit: hidden`, `List: visible`), asserting against the actual file.

## 7. Components / isolation
- `RepresentationVisibility` dataclass in `nodes.py` (Qt-free data).
- `_build_representation_index` + `_parse_columns` change in `parser.py` (the only lxml module).
- `_rows_for_column` in `properties_panel.py` (Qt-free row-builder, unit-tested without a QApplication, matching the existing pattern).
- No change to the differ, apply, tree, or any other subsystem — purely additive.
