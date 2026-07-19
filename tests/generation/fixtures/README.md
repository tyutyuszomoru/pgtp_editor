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

| Base name | Shape it covers |
|-----------|-----------------|
| `golden_gizmo` | Single-column serial PK + one of each column type (varchar/text/numeric/boolean/date/timestamp) and a single FK. |
| `golden_gizmo_tag` | **Composite PK** junction table (both key columns hidden in Edit/Insert/Compare/MultiEdit); key columns are also FKs. |

The fixture set is parametrized in `test_golden_page.py` (`_GOLDEN_FIXTURES`).

## Current status

Both `.page.xml` files are **self-generated snapshots** — a regression lock on
the generator's *own* output. They are **not yet parity oracles**: they have
never been compared against real PHP Generator output. They guard against
accidental changes, nothing more.

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
