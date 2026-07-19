# Golden fixtures — create-page-from-table parity

A golden fixture is a **pair**:

| File | Role |
|------|------|
| `<name>.ddl.sql` | The `CREATE TABLE` script — the ground truth for the column types. |
| `<name>.schema.json` | The generator **input** (a `DatabaseSchema`), authored to match the DDL. |
| `<name>.page.xml` | The **expected** `<Page>` serialization. |

`tests/generation/test_golden_page.py` feeds the `.schema.json` to `build_page`,
serializes at indent 0, and asserts equality with the `.page.xml`.

## Fixtures

| Base name | Kind | Shape it covers |
|-----------|------|-----------------|
| `golden_newtable_1` | **REAL oracle** | Clean no-edits capture from PHP Generator: serial PK + integer + bare varchar + bare numeric + boolean. The generator reproduces it exactly. |
| `golden_gizmo` | snapshot | Single-column serial PK + one of each column type (varchar/text/numeric/boolean/date/timestamp) and a single FK. |
| `golden_gizmo_tag` | snapshot | **Composite PK** junction table (both key columns hidden in Edit/Insert/Compare/MultiEdit); key columns are also FKs. |
| `golden_memo` | snapshot | **No PK, all-nullable, text-heavy** — nothing hidden in any representation; varchar(n)/char(n) carry their length as maxLength while text/citext fall back to maxLength="0". |

The fixture set is parametrized in `test_golden_page.py`; real oracles are listed
in `_REAL_ORACLES` and are never overwritten by `UPDATE_GOLDEN`.

## Current status

`golden_newtable_1` is a **real parity oracle** — the verbatim `<Page>` PHP
Generator emitted for a no-edits table add, which the generator now reproduces
exactly (comparison is whitespace-normalized via `test_golden_page._normalize`,
so phpgen's space indentation and our tab indentation compare equal while
attribute order is preserved). Calibrating against it fixed several defaults:
`editAbilityMode=3`, `deleteSelectedAbilityMode`/`highlightRowOnMouseHover`/
`condensedTable`, per-column `showColumnFilter="false"` (all but boolean) and
`canSetNull="true"` (nullable), integer `thousandSeparator` / numeric
`numberAfterDecimal` Format, boolean `1572867` + `displayType="image"`, and the
bare-table-name `fileName`.

The other three `.page.xml` files remain **self-generated snapshots** — a
regression lock on the generator's own output, not independently verified. They
inherit the calibrated defaults but have not themselves been compared against
real PHP Generator output. Capturing real oracles for a composite-PK table and a
no-PK/date/timestamp table would be the next parity wins.

## Turning it into a real parity oracle (the capture)

1. Run `golden_gizmo.ddl.sql` in a scratch PostgreSQL database.
2. In **PHP Generator**: connect to that DB, add data source `pr.gizmo` as a
   top-level page, and **accept all defaults** — do not touch captions, editors,
   column visibility, ability modes, etc. (Any manual edit pollutes the oracle.)
3. Save the project as a `.pgtp`.
4. Open the `.pgtp`, find the `<Page ... tableName="pr.gizmo"> … </Page>` block,
   and paste it verbatim over the contents of `golden_gizmo.page.xml`.
5. Run `python -m pytest tests/generation/test_golden_page.py -q`.
   - Every assertion diff is a place our generator disagrees with PHP Generator
     — i.e. the **parity to-do list**.
6. Calibrate `pgtp_editor/generation/type_map.py` (and the builders if needed)
   until the test is green. That green run is verified parity for this table.

Note serialization/formatting differences (indentation, attribute order) may
need normalizing before the comparison is meaningful; if PHP Generator's
attribute order differs from ours, we compare on a normalized form rather than
forcing byte-identical whitespace. Adjust the test's comparison at that point.

## Regenerating the snapshot after an *intended* generator change

```
UPDATE_GOLDEN=1 python -m pytest tests/generation/test_golden_page.py -q   # bash
$env:UPDATE_GOLDEN='1'; python -m pytest tests/generation/test_golden_page.py -q   # PowerShell
```

Only do this when the change to the generator is deliberate and reviewed.

## Adding more fixtures

Pick a table shape not yet covered (composite PK, no PK, view, all-nullable,
long text, money/enum types), add the `.ddl.sql` + `.schema.json` pair, capture
the `.page.xml`, and parametrize `test_golden_page.py` over the fixture set.
