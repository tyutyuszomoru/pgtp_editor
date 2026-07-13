# PGTP Editor — Column Sub-element Model + Differ Extension (Interface Text Collection Sub-project 1) Design Specification

**Date:** 2026-07-13
**Status:** Approved for planning
**Depends on:** [2026-07-11-pgtp-editor-model-design.md](2026-07-11-pgtp-editor-model-design.md) (Real Model sub-project — `pgtp_editor/model/nodes.py`, `pgtp_editor/model/parser.py`), [2026-07-12-pgtp-editor-differ-engine-design.md](2026-07-12-pgtp-editor-differ-engine-design.md) (differ engine — `pgtp_editor/diff/differ.py`, `pgtp_editor/diff/records.py`), and the diff/merge write-back sub-project ([2026-07-12-pgtp-editor-diff-merge-writeback-design.md](2026-07-12-pgtp-editor-diff-merge-writeback-design.md) — `pgtp_editor/diff/apply.py`).

## 1. Context and scope

This is **sub-project 1 of the "Interface Text Collection" feature area**, which supersedes the original design spec's §6.3 caption-only "Manage Captions" idea. Interface Text Collection is about letting a user see and edit, across a whole project, the *human-facing* and *presentation-shaping* properties of a database column: its caption, its `EditProperties` placeholder, its number/date `Format`, its `Lookup` (foreign-key display) wiring, and its `ViewProperties`/`EditProperties`. These properties are what a translator or UI reviewer actually cares about, and today they are buried one-column-at-a-time inside deeply nested `ColumnPresentation` elements.

The feature area is decomposed into three sequential sub-projects:

1. **Column sub-element model + differ extension** (this document) — the *data foundation*. Parse the four presentation sub-elements (`Format`, `Lookup`, `ViewProperties`, `EditProperties`) into the model, and teach the differ to compare them bracket-per-bracket, value-per-value. **No UI.**
2. **By-Column property browser dialog** (future) — a dialog that lists every column in the project and shows its caption / placeholder / Format / Lookup / View/Edit properties side by side, built on top of the model fields this sub-project adds.
3. **By-Table usage view** (future) — a view that groups columns by the database table they belong to, to spot inconsistent captions/placeholders for the same underlying field reused across pages.

**Why the data foundation comes first (and separately):** sub-projects 2 and 3 are both *readers* of column presentation data. Neither can be built until `ColumnNode` actually carries that data and the differ can report changes to it. Exactly as the Real Model sub-project laid the parsing groundwork before Properties could be built, and the Differ Engine laid the `Difference` record shape before any diff UI, this sub-project lays the column-sub-element groundwork — a set of new model fields plus a differ extension — that is fully unit-testable against synthetic node graphs and one real sample file, with zero Qt code.

**Terminology.** The two inputs the differ compares are **Source** and **Target**, matching the differ-engine spec. A "sub-element" here means one of the four optional, single-occurrence presentation children of a `ColumnPresentation`: `Format`, `Lookup`, `ViewProperties`, `EditProperties`.

## 2. Scope

### 2.1 In scope

- A new `ChildElement` dataclass in `pgtp_editor/model/nodes.py`, holding `attrib`, `sourceline`, and the retained lxml `element` reference — the same three-field shape every other model node already carries for its own element.
- Four new optional fields on `ColumnNode` — `format`, `lookup`, `view_properties`, `edit_properties` — each `ChildElement | None`, defaulting to `None` (absent in the common case).
- Extending `_parse_columns` in `pgtp_editor/model/parser.py` to populate those four fields from each `ColumnPresentation`'s sub-elements, preserving all existing `ColumnNode` construction.
- Extending `pgtp_editor/diff/differ.py` with a `_compare_child_element` helper, called from `_compare_columns` once per each of the four sub-element slots for every matched column pair, emitting `added` / `removed` / `changed` `Difference` records that mirror the existing attribute/column comparison exactly, threading the `ambiguous` flag.
- Four new `node_kind` strings on the `Difference` record: `"format"`, `"lookup"`, `"view_properties"`, `"edit_properties"` (see §4.3).
- A documented, justified decision (§4.6) on whether `pgtp_editor/diff/apply.py` can write these new difference kinds back to the real lxml tree, and either extending it or explicitly scoping apply-of-sub-element-changes out.
- Unit tests (model/parser + differ), a real-sample integration assertion, and a self-diff regression check.

### 2.2 Explicitly out of scope (this sub-project)

- **The By-Column property browser dialog** (sub-project 2) and **the By-Table usage view** (sub-project 3). This sub-project ships no dialog, no view, no menu wiring.
- **Any UI whatsoever** — no Qt import appears in any file this sub-project touches. `ChildElement` and the differ extension are pure data/logic, unit-testable without pytest-qt.
- **Wiring the existing "Manage Captions..." menu action.** It remains the stub it is today; this sub-project does not repurpose or remove it. (The Interface Text Collection dialogs of sub-projects 2–3 are what will eventually supersede it.)
- **LLM translation** of any collected text. Interface Text Collection sub-project 1 only *models and diffs* the text-bearing sub-elements; it does not translate them. The existing external translator toolchain is unaffected and untouched.
- **The `placeholder` value getting its own model field.** `placeholder` is an attribute *inside* `EditProperties`, reachable as `column.edit_properties.attrib.get("placeholder")` once `edit_properties` is parsed. No dedicated field, no special-casing — it falls out of the generic `EditProperties` capture for free (§4.4).
- **Recursing into a sub-element's own children.** `ViewProperties` can itself contain a nested `<Format>` child (see §4.1). `ChildElement` captures only the sub-element's own `attrib` (plus its retained `element` for future write-back); the differ compares sub-elements attribute-by-attribute only. A `<Format>` nested inside `ViewProperties` is captured **separately** as the `ColumnNode.format` field (§4.1), not by descending through `view_properties`.

## 3. Empirical grounding (real sample data)

Both decisions below were verified against the two real sample files present in the worktree (`sample/dev_Ferrara.pgtp` and `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp`, both gitignored), by parsing them with lxml and inspecting every `ColumnPresentation`.

### 3.1 The four sub-elements and their real attribute names

Grepped from `sample/dev_Ferrara.pgtp`, these are the exact attribute names each sub-element carries:

- **`Format`** — `type` (always `"number"` in the samples), `decimalSeparator`, `thousandSeparator`, `numberAfterDecimal`. Example: `<Format type="number" decimalSeparator="." thousandSeparator=","/>`.
- **`Lookup`** — `tableName`, `linkFieldName`, `displayFieldName`, `lookupFilter`, `useLookupOrdering`, `lookupOrdering`, and sometimes `allowAddNewItemsOnTheFly`. Example: `<Lookup tableName="pr.x_wbs" linkFieldName="wbs_id" displayFieldName="wbs_name" lookupFilter="" useLookupOrdering="true" lookupOrdering="0"/>`.
- **`ViewProperties`** — `type` (e.g. `"text"`), sometimes `maxLength`. Example: `<ViewProperties type="text" maxLength="75"/>`.
- **`EditProperties`** — `type` (e.g. `"textBox"`, `"autocomplete"`, `"dynamicCombobox"`, `"textArea"`), `maxLength`, and the text-bearing **`placeholder`**, plus type-specific attributes like `minimumInputLength`, `columnCount`, `rowCount`. Example: `<EditProperties type="textBox" maxLength="30" placeholder="Equipment tag number"/>`.

Because the differ compares these generically over `attrib` (never enumerating specific keys), it automatically covers every attribute the vendor format puts on a sub-element — consistent with the model layer's "capture everything generically" decision. The lists above are for grounding tests and future UI, not something the parser or differ hard-codes.

### 3.2 Prevalence, and the critical `Format` placement finding

In `sample/dev_Ferrara.pgtp` there are **2,453** `ColumnPresentation` elements. Every one has a direct-child `ViewProperties` (2,453) and a direct-child `EditProperties` (2,453); **418** have a direct-child `Lookup`.

**`Format` is never a direct child of `ColumnPresentation`.** In all 887 occurrences in `dev_Ferrara.pgtp` (and all 1,175 in the FRENCH sample), `Format`'s parent element is `ViewProperties` — i.e. `Format` is a *grandchild* of `ColumnPresentation`, nested one level down inside `ViewProperties`. It never appears inside `EditProperties` and never as a direct `ColumnPresentation` child. This directly contradicts the originally-sketched instruction to parse it with `col_el.find("Format")`, which would always return `None` and leave the `format` field permanently dead. The parser therefore locates it via `col_el.find("ViewProperties/Format")` instead — see §4.1, the primary judgment call of this sub-project.

## 4. Architecture

### 4.1 The `ChildElement` dataclass

Added to `pgtp_editor/model/nodes.py`, matching the exact dataclass style of the existing nodes (`@dataclass`; the `element` field typed and defaulted identically to how `ColumnNode` types its own `element`):

```python
@dataclass
class ChildElement:
    """A single-occurrence optional presentation child of a ColumnPresentation
    (one of <Format>, <Lookup>, <ViewProperties>, <EditProperties>).

    Holds only the child's own attributes plus a reference to the retained
    real lxml element (for future write-back — see diff/apply.py). Does not
    descend into the child's own children: a <Format> nested inside a
    <ViewProperties> is captured separately as ColumnNode.format (see
    parser._parse_columns), not by walking into ColumnNode.view_properties.
    """
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None
```

The `element` reference is retained for the same reason every other node retains one: so a later write-back step (diff/apply.py, or the sub-project-2/3 editors) can mutate the *real* element rather than reconstruct it. This sub-project does not itself mutate through it (see the apply decision in §4.6), but carrying it now avoids a breaking change to the dataclass shape later.

### 4.2 `ColumnNode`'s four new fields

```python
@dataclass
class ColumnNode:
    identity: str
    attrib: dict
    sourceline: int | None = None
    element: "etree._Element | None" = None
    format: "ChildElement | None" = None
    lookup: "ChildElement | None" = None
    view_properties: "ChildElement | None" = None
    edit_properties: "ChildElement | None" = None

    @property
    def field_name(self) -> str | None:
        return self.attrib.get("fieldName")
```

All four default to `None`. `format` and `lookup` are absent on most columns; `view_properties`/`edit_properties` happen to be present on essentially every column in the samples, but are still typed optional because the format does not *require* them and a synthetic or hand-edited file may omit them. Every existing field and the `field_name` property are preserved unchanged — this is purely additive, so no existing model or parser test changes.

Field names use `snake_case` (`view_properties`, `edit_properties`) per the module's Python convention, even though the XML tags are `PascalCase` — matching how `PageNode.file_name` maps to the `fileName` attribute.

### 4.3 The four new `node_kind` strings and their justification

The differ's `Difference.node_kind` currently ranges over `"page" | "detail" | "column" | "event"`. This sub-project adds four more, one per sub-element slot:

| Sub-element XML tag | `node_kind` string | `ColumnNode` field |
|---|---|---|
| `<Format>` | `"format"` | `format` |
| `<Lookup>` | `"lookup"` | `lookup` |
| `<ViewProperties>` | `"view_properties"` | `view_properties` |
| `<EditProperties>` | `"edit_properties"` | `edit_properties` |

**Justification for these exact strings:** they mirror the `snake_case` `ColumnNode` field names one-to-one, so a future UI (sub-projects 2–3) can map a `Difference.node_kind` back to the field it came from with a trivial lookup, and there is a single obvious spelling for each. They are lowercase like the existing four `node_kind` values (`"page"`, not `"Page"`). We deliberately do **not** reuse a single generic `node_kind="child_element"` with the tag in `path`, because downstream grouping ("show me all Format changes across the project") is far cleaner keyed on a distinct `node_kind` than on parsing the last non-attribute path segment — and it matches the existing pattern where each structural level already gets its own `node_kind`.

The `Difference` dataclass field itself is an unconstrained `str` (see `records.py`), so no code change to `records.py` is required; the comment enumerating the allowed values is updated to list the four new ones.

### 4.4 `path` structure for sub-element differences

The differ already builds a column's path as `parent_path + [field_name]` (e.g. `["development_equipment", "tag"]` for the `tag` column on the `development_equipment` page, or `["page", "pr.detail/Caption", "tag"]` for a column inside a nested Detail). Sub-element differences extend that by one more segment: **the sub-element's XML tag name** (`PascalCase`, matching the tag, not the `node_kind`).

- A **changed** sub-element attribute: `path = column_path + [sub_element_tag]`, with `attribute` = the differing attribute key. Example: a change to a column's decimal separator yields
  `path = ["development_equipment", "amount", "Format"]`, `node_kind="format"`, `attribute="decimalSeparator"`, `old_value=<target's value>`, `new_value=<source's value>`.
- An **added**/**removed** whole sub-element: `path = column_path + [sub_element_tag]`, `attribute=None`, and `new_value` (added) / `old_value` (removed) = the whole `ChildElement`.

Using the `PascalCase` tag (`"Format"`, `"Lookup"`, `"ViewProperties"`, `"EditProperties"`) as the path segment — rather than the `snake_case` `node_kind` — keeps `path` human-readable and consistent with the XML the user sees, while `node_kind` carries the machine-groupable key. This is the same split the differ already uses elsewhere (paths carry human-facing identity strings; `node_kind` carries the machine tag). A future By-Column UI can therefore render the path as `development_equipment › amount › Format › decimalSeparator` directly.

### 4.5 `_parse_columns` extension

The only parser change. Each of the four sub-elements is located and, if present, captured as a `ChildElement`. **`Format` is located via `col_el.find("ViewProperties/Format")`** — the empirically-correct path (§3.2) — while the other three are direct children found via `col_el.find(<tag>)`.

```python
def _parse_columns(container_el, parent_identity) -> list[ColumnNode]:
    columns_container = container_el.find("ColumnPresentations")
    if columns_container is None:
        return []

    columns = []
    for col_el in columns_container.findall("ColumnPresentation"):
        field_name = col_el.get("fieldName", "") or ""
        identity = _make_identity(parent_identity, field_name)
        columns.append(
            ColumnNode(
                identity=identity,
                attrib=dict(col_el.attrib),
                sourceline=col_el.sourceline,
                element=col_el,
                format=_child_element(col_el.find("ViewProperties/Format")),
                lookup=_child_element(col_el.find("Lookup")),
                view_properties=_child_element(col_el.find("ViewProperties")),
                edit_properties=_child_element(col_el.find("EditProperties")),
            )
        )
    return columns


def _child_element(el):
    """Wrap an optional sub-element into a ChildElement, or None if absent.
    `el` is an lxml element or None (the result of an ElementTree.find)."""
    if el is None:
        return None
    return ChildElement(attrib=dict(el.attrib), sourceline=el.sourceline, element=el)
```

`ChildElement` is added to the existing `from pgtp_editor.model.nodes import (...)` block at the top of `parser.py`. `Element.find` returns the first matching descendant for a path with a `/`, or the first matching direct child for a bare tag, or `None`; `_child_element(None)` returns `None`, so absent sub-elements leave the field `None` for free. All existing `ColumnNode` construction (`identity`, `attrib`, `sourceline`, `element`) is preserved verbatim.

**Note on the `Format`-inside-`ViewProperties` overlap.** Because `Format` lives inside `ViewProperties`, a column with a `Format` will populate *both* `column.format` (the nested `<Format>`'s attrib) and `column.view_properties` (the enclosing `<ViewProperties>`'s own attrib, e.g. `type="text"`). These are two distinct sub-elements with disjoint attribute sets, captured independently; the differ compares each on its own, so a decimal-separator change surfaces as a `"format"` diff and a `ViewProperties type` change surfaces as a `"view_properties"` diff, never conflated. `ChildElement` intentionally does not descend, so `view_properties.attrib` never contains `Format`'s attributes.

### 4.6 Differ extension: `_compare_child_element`

Per the user's explicit framing — "diff should compare bracket per bracket, value per value" — a new helper compares one sub-element slot for a matched column pair, and `_compare_columns` calls it four times (once per slot) after its existing attribute comparison. The behavior mirrors `_compare_attributes` / the column added/removed pattern exactly, and threads `ambiguous`.

```python
def _compare_child_element(
    source_child, target_child, path, node_kind, tag_name, ambiguous=False
) -> list[Difference]:
    """Compare one optional sub-element slot (Format/Lookup/ViewProperties/
    EditProperties) of a matched column pair.

    `source_child`/`target_child` are each a ChildElement or None.
    `path` is the enclosing column's path; `node_kind` is the sub-element
    kind ("format"/"lookup"/"view_properties"/"edit_properties");
    `tag_name` is the XML tag used as the trailing path segment ("Format"
    etc.). Behavior mirrors _compare_attributes / _compare_columns exactly:

    - present on source only  -> one `added` record (whole ChildElement)
    - present on target only   -> one `removed` record (whole ChildElement)
    - present on both          -> one `changed` record per differing attrib key
    - absent on both           -> nothing
    """
    child_path = path + [tag_name]

    if source_child is not None and target_child is None:
        return [
            Difference(
                kind="added",
                path=child_path,
                node_kind=node_kind,
                attribute=None,
                old_value=None,
                new_value=source_child,
                ambiguous=ambiguous,
            )
        ]
    if source_child is None and target_child is not None:
        return [
            Difference(
                kind="removed",
                path=child_path,
                node_kind=node_kind,
                attribute=None,
                old_value=target_child,
                new_value=None,
                ambiguous=ambiguous,
            )
        ]
    if source_child is None and target_child is None:
        return []

    # Present on both: compare attrib dicts key-by-key, exactly like
    # _compare_attributes, but scoped to this sub-element and its node_kind.
    differences: list[Difference] = []
    all_keys = set(source_child.attrib.keys()) | set(target_child.attrib.keys())
    for key in sorted(all_keys):
        source_value = source_child.attrib.get(key)
        target_value = target_child.attrib.get(key)
        if source_value != target_value:
            differences.append(
                Difference(
                    kind="changed",
                    path=child_path,
                    node_kind=node_kind,
                    attribute=key,
                    old_value=target_value,
                    new_value=source_value,
                    ambiguous=ambiguous,
                )
            )
    return differences
```

`_compare_columns` gains four calls, made only in the matched-pair branch (an added/removed *column* already emits a whole-`ColumnNode` record whose `new_value`/`old_value` carries the sub-element fields, so there is nothing extra to compare for a column that exists on only one side):

```python
        else:
            differences.extend(
                _compare_attributes(
                    source_column, target_column, path=column_path, node_kind="column", ambiguous=ambiguous
                )
            )
            for source_child, target_child, node_kind, tag_name in (
                (source_column.format, target_column.format, "format", "Format"),
                (source_column.lookup, target_column.lookup, "lookup", "Lookup"),
                (source_column.view_properties, target_column.view_properties, "view_properties", "ViewProperties"),
                (source_column.edit_properties, target_column.edit_properties, "edit_properties", "EditProperties"),
            ):
                differences.extend(
                    _compare_child_element(
                        source_child, target_child,
                        path=column_path, node_kind=node_kind, tag_name=tag_name,
                        ambiguous=ambiguous,
                    )
                )
```

`ambiguous` reaches `_compare_columns` from `compare_block` exactly as today (the existing signature already threads it), so a column pair inside an ambiguous duplicate-Detail group produces ambiguous sub-element records automatically — no new plumbing, and covered by a dedicated test.

### 4.7 The `apply.py` decision — sub-element changes are scoped OUT of write-back (documented limitation)

`pgtp_editor/diff/apply.py` dispatches in `_apply_one` on `(kind, node_kind, attribute)`:

- `kind == "added"` → `_apply_added`, which switches on `node_kind` over exactly `{"page", "detail", "column", "event"}` and **raises `_ApplyError` for any other `node_kind`** (`"unsupported node_kind for added: ..."`).
- `kind == "removed"` → `_apply_removed`, which is node-kind-agnostic: it removes `diff.old_value.element` from its parent. A `ChildElement` *does* carry an `.element`, so this branch would *happen* to work for a removed sub-element.
- `kind == "changed"` with `attribute is not None` → `_apply_changed_attribute`, which switches on `node_kind` over exactly `{"page", "detail", "column"}` and **raises `_ApplyError` for any other** (`"unsupported node_kind for attribute change: ..."`).

So today, out of the box: a **changed** sub-element attribute and an **added** sub-element would both hit an explicit `_ApplyError` and be reported as an `ApplyFailure` (not silently mis-applied); a **removed** sub-element would coincidentally succeed. This is an inconsistent, half-working state.

**Decision: scope apply-of-sub-element-changes OUT of this sub-project, and make the scope-out uniform and explicit rather than relying on the incidental behaviors above.** Rationale:

1. **This sub-project's job is the read/diff foundation, not write-back.** Its two named consumers (sub-projects 2 = By-Column browser, 3 = By-Table view) are *browsers/editors of column text*, and will define their own editing/save path against the retained `ChildElement.element` references. They do not consume `apply.py`'s diff-merge write-back for sub-elements. Building sub-element write-back now would be speculative work for a consumer that does not yet exist and whose editing model is undesigned.
2. **A correct sub-element write-back is non-trivial and deserves its own design.** Adding a sub-element means recreating the right nesting (a `Format` must be inserted *inside* the column's `ViewProperties`, creating `ViewProperties` first if absent — the grandchild placement from §3.2), and honoring vendor element ordering. Removing the last attribute of a `ViewProperties` that still hosts a `Format` must not orphan the `Format`. These are real correctness concerns that belong in the diff-merge write-back spec, not bolted on here.
3. **Consistency beats a half-working accident.** Rather than leave "removed works, changed/added fail," the differ's new records are uniformly *unappliable by the current diff-merge Apply step*, which is the honest state.

**What this means concretely:**

- **`apply.py` is not modified by this sub-project.** The differ will emit `node_kind` values (`"format"` etc.) that `_apply_one` does not recognize for `added`/`changed`, so `apply_differences` will record them as `ApplyFailure`s if the diff-merge UI ever hands them to it.
- **Documented limitation:** *if a user checks a sub-element difference in the (existing) Diff/Merge Apply panel, applying it will currently fail with an `ApplyFailure`* ("unsupported node_kind ...") for `added`/`changed`, and would incidentally succeed only for `removed`. Because that mixed behavior is itself surprising, the plan adds a **guard test** in `tests/diff/test_apply.py` asserting `apply_differences` returns the sub-element `changed`/`added` records in `ApplyResult.failed` (locking in that they fail cleanly rather than silently corrupting the tree), plus a note that removed-sub-element application is not exercised/relied upon and its incidental success is not a supported feature.
- **Follow-up hook:** when a future sub-project (or a diff-merge write-back v2) wants sub-element write-back, it must add `format`/`lookup`/`view_properties`/`edit_properties` branches to `_apply_added` and `_apply_changed_attribute` (locating the enclosing `ColumnPresentation` via the column path, then the sub-element inside it — with special nesting handling for `Format` inside `ViewProperties`), and should own the ordering/nesting correctness described in rationale #2. This is recorded here so the scope-out is a deliberate, resumable decision, not a silent gap.

### 4.8 Layering and non-goals

`model/` gains a dataclass and a parser branch; `diff/` gains one helper and four call-sites. No Qt import is introduced anywhere. `model/` still depends on nothing above it; `diff/` still depends only on `model/`. `apply.py` is untouched. The change is additive: no existing model, parser, differ, or apply test changes, and the two real-sample self-diff regression tests from the differ-engine sub-project must still yield zero differences (guarded by §5's self-diff check).

## 5. Testing strategy

All tests are pure Python (no pytest-qt); the model/parser tests parse real or synthetic lxml, and the differ tests build `ColumnNode`s directly.

### 5.1 Model / parser unit tests (`tests/model/test_parser.py` additions, or a new `tests/model/test_column_subelements.py`)

Build a small in-memory XML string containing a `ColumnPresentations` container and parse it via the real parser (or the smallest real entry point that reaches `_parse_columns`), asserting:

- **All four present** — a `ColumnPresentation` with a `<ViewProperties type="text"><Format type="number" decimalSeparator="."/></ViewProperties>`, a `<Lookup .../>`, and an `<EditProperties type="textBox" placeholder="Hi"/>`: assert `column.format`, `column.lookup`, `column.view_properties`, `column.edit_properties` are all non-`None` `ChildElement`s, with the correct `attrib` (e.g. `column.format.attrib["decimalSeparator"] == "."`, `column.edit_properties.attrib["placeholder"] == "Hi"`) and a populated `sourceline` and non-`None` `element`.
- **None present** — a bare `<ColumnPresentation fieldName="x"/>`: assert all four fields are `None`.
- **Some present** — a column with only `<ViewProperties>` and `<EditProperties>` (no `Lookup`, no nested `Format`): assert `view_properties`/`edit_properties` non-`None` and `lookup`/`format` `None`.
- **`placeholder` accessibility** — explicitly assert `column.edit_properties.attrib.get("placeholder")` returns the expected string, documenting that no dedicated field is needed (§4.4 / §2.2).
- **`Format`-nesting regression** — a column whose `<Format>` is nested inside `<ViewProperties>` (the real shape) populates `column.format`; assert it is non-`None`. This is the guard against the `col_el.find("Format")` bug (§3.2): a naive direct-child lookup would leave `format` `None` here.

### 5.2 Real-sample integration assertion (in the same test file, guarded to skip if the sample is absent)

Parse `sample/dev_Ferrara.pgtp` via `load_project`, locate a column known to have a `Lookup` + `Format` + `EditProperties` — the `wbs1` column on the top-level `development_equipment` page is a verified example (it has `<Lookup tableName="pr.x_wbs" ...>` and `<EditProperties type="dynamicCombobox">`) — and assert:

- `column.lookup.attrib["tableName"] == "pr.x_wbs"` (and `linkFieldName == "wbs_id"`, `displayFieldName == "wbs_name"`).
- `column.edit_properties.attrib["type"] == "dynamicCombobox"`.
- A column that has a numeric `Format` (e.g. the `id` column) has `column.format.attrib["type"] == "number"`.

The test skips (rather than fails) when `sample/dev_Ferrara.pgtp` is not present, since the sample is gitignored — matching how the existing real-sample tests guard themselves.

### 5.3 Differ unit tests (`tests/diff/test_differ.py` additions)

Synthetic `ColumnNode`s built directly (with `ChildElement`s constructed inline), one matched Page pair holding one matched column pair. For **each of the four sub-element kinds**:

- **Added** — source column has the sub-element, target does not: assert exactly one `Difference`, `kind="added"`, `node_kind=<the kind>`, `path == [page, field, <Tag>]`, `attribute is None`, `new_value` is the source `ChildElement`, `old_value is None`.
- **Removed** — symmetric: `kind="removed"`, `old_value` is the target `ChildElement`, `new_value is None`.
- **Changed attribute** — both present, one attribute differs (e.g. `Format.decimalSeparator` `.` → `,`): assert one `Difference`, `kind="changed"`, `node_kind=<the kind>`, `path == [page, field, <Tag>]`, `attribute == <key>`, `old_value == <target value>`, `new_value == <source value>`.

Plus:

- **No change** — both present, identical `attrib`: assert no `Difference` for that slot.
- **Multiple differing keys** — a sub-element with two changed attributes yields two `changed` records (one per key), sorted by key.
- **`ambiguous` propagation** — the same column pair nested inside a duplicate-`(tableName, caption)` sibling Detail group (reusing the differ-engine spec's ambiguous mechanism): assert the sub-element `Difference`s carry `ambiguous=True`.

### 5.4 Apply guard test (`tests/diff/test_apply.py` addition — per the §4.6 scope-out)

Construct a `Difference` with `node_kind="format"`, `kind="changed"`, `attribute="decimalSeparator"` (and one with `kind="added"`, `node_kind="lookup"`), hand them to `apply_differences`, and assert they land in `ApplyResult.failed` (not `applied`), with a message indicating an unsupported `node_kind` — locking in that unappliable sub-element diffs fail cleanly rather than silently corrupting the target tree. A short comment in the test points at §4.6 for the rationale and the follow-up hook.

### 5.5 Self-diff integration regression

Extend the existing self-diff regression (diff a real sample file against itself → empty list) to confirm the new comparison does not spuriously fire. Since the differ-engine sub-project already has a `sample/dev_Ferrara.pgtp` self-diff test asserting `diff_project(m, m) == []`, and the samples are dense with all four sub-elements, that existing test — re-run after this sub-project's changes — is itself the regression guard: if `_compare_child_element` misbehaved (e.g. treated a present-on-both sub-element as changed, or compared `Format` against `ViewProperties`), the self-diff would go non-empty. The plan explicitly re-runs it and asserts it still passes, and (if not already covering both samples) adds the second sample file's self-diff.

## 6. Summary of decisions

- **Interface Text Collection** supersedes the original §6.3 "Manage Captions" idea and is split into three sub-projects; this document is **sub-project 1**, the pure model + differ data foundation, with **no UI** and no touching of the "Manage Captions..." stub.
- A new **`ChildElement`** dataclass (`attrib`, `sourceline`, retained `element`) models an optional single-occurrence presentation child, matching the existing node style; `ColumnNode` gains four optional `ChildElement | None` fields: `format`, `lookup`, `view_properties`, `edit_properties`, all defaulting to `None`. `placeholder` needs no field — it lives in `edit_properties.attrib`.
- **Primary judgment call:** `Format` is empirically **never a direct child** of `ColumnPresentation` — it is always nested inside `ViewProperties` (887/887 in `dev_Ferrara`, 1175/1175 in the FRENCH sample). The parser therefore locates it via `col_el.find("ViewProperties/Format")`, **not** the originally-sketched `col_el.find("Format")` (which would leave the field permanently `None`). A dedicated regression test guards this. `ViewProperties` is still captured independently for its own attributes; the two do not conflate.
- The differ gains **`_compare_child_element`**, called four times from `_compare_columns` per matched column pair, emitting `added`/`removed`/`changed` records that mirror `_compare_attributes` exactly and thread `ambiguous`.
- **New `node_kind` strings:** `"format"`, `"lookup"`, `"view_properties"`, `"edit_properties"` (lowercase `snake_case`, one-to-one with the `ColumnNode` fields, for clean downstream grouping). **`path` structure:** `column_path + [<PascalCase tag>]` (e.g. `["development_equipment", "amount", "Format"]`), with `attribute` = the differing key for `changed` records — keeping paths human-readable while `node_kind` carries the machine key.
- **`apply.py` decision:** sub-element write-back is **scoped OUT** and left as a **documented limitation**. `apply.py` is unmodified; the new `node_kind`s are unrecognized by `_apply_added`/`_apply_changed_attribute` and will surface as clean `ApplyFailure`s (the incidental success of a *removed* sub-element via the node-kind-agnostic `_apply_removed` is noted but not relied upon or supported). A guard test locks in the clean-failure behavior, and §4.6 records the follow-up hook (add sub-element branches to apply, with `Format`-in-`ViewProperties` nesting correctness) for a future write-back sub-project. Rationale: this sub-project is the read/diff foundation; its consumers (sub-projects 2–3) will define their own editing path, and correct nested write-back deserves its own design.
- **Testing:** model/parser unit tests (all/none/some present, `placeholder` access, `Format`-nesting regression) + a real-sample integration assertion on `wbs1`/`id` + per-kind differ tests (added/removed/changed/no-change/multi-key/ambiguous) + an apply guard test + re-running the real-sample self-diff to prove no spurious firing.
