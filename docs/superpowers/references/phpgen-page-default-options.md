# PHP Generator page-level "options" → XML attribute decode

Source: the PHP Generator page **Options** panel with **"Use default options"**
checked, cross-referenced against the clean-defaults capture
`tests/generation/fixtures/golden_newtable_1.page.xml`. This resolves the
ability-mode numeric codes the re-phpgen spec flagged as needing "differential
probing" — for the DEFAULT state.

## Action ability modes (emitted with a numeric value)

At default every action is **"Modal window"** (delete actions "Enabled"), which
is the numeric code **`3`**:

| GUI option | Default | XML attribute | Default value |
|------------|---------|---------------|---------------|
| View | Modal window | `viewAbilityMode` | `3` |
| Edit | Modal window | `editAbilityMode` | `3` |
| Multi-edit | Modal window | `multiEditAbility` | `3` |
| Fields to be updated by default | None | `includeAllFieldsForMultiEditByDefault` | `false` |
| Insert | Modal window | `insertAbilityMode` | `3` |
| Copy | Modal window | `copyAbilityMode` | `3` |
| Delete | Enabled | `deleteAbilityMode` | `3` |
| Multi-delete | Enabled | `deleteSelectedAbilityMode` | `3` |

**Enum (partially known):** `3` = Modal window / Enabled (default). `2` is
observed on a customized page (`sample/dev_Ferrara.pgtp` `editAbilityMode="2"`),
almost certainly "Inline / on the page". `0` is almost certainly "Disabled".
The exact codes for every dropdown value are NOT fully probed — capturing them
requires toggling each dropdown and diffing the saved `.pgtp`.

`Quick edit` (default "List and view") did not surface as an attribute in the
default capture — likely `quickEditAbility` omitted at default (XSD lists it as
optional).

## Filtering / Sorting / Additional toggles (OMITTED at default)

All default to **"Enabled"**, and at default they are **absent** from the
`<Page>` entirely — a corresponding attribute appears only when set to a
non-default value. Confirmed by `golden_newtable_1` carrying none of these:

| GUI option | Default | Likely attribute (when non-default) |
|------------|---------|--------------------------------------|
| Quick search | Enabled | (QuickFilter representation / quick-filter columns) |
| Filter builder | Enabled | `filterBuilderAvailable` |
| Column filter | Enabled | `showColumnFilter` per column (see below) |
| Selection filter | Enabled | `selectionFilterAvailable` |
| Sorting by click | Enabled | `sortingByClickAvailable` |
| Sorting by dialog | Enabled | `sortingByDialogAvailable` |
| Runtime customization | Enabled | `runtimeCustomizationAvailable` |
| Record comparison | Enabled | `recordsComparisionAvailable` (note vendor spelling) |
| Refresh | Enabled | (page reload / refresh control) |

Note: **Column filter** is a per-column concern — the generator emits
`showColumnFilter="false"` on non-boolean columns (boolean keeps its column
filter). That is a column-presentation default, distinct from the page-level
"Column filter: Enabled" master toggle above.

## Implication for the generator

`pgtp_editor/generation/type_map.py` `PAGE_DEFAULTS` already encodes the `3`
ability modes and omits the Filtering/Sorting/Additional attributes, matching
this default state. No change required; this doc is the rationale.
