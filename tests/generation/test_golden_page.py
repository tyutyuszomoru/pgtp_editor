# tests/generation/test_golden_page.py
"""Golden-fixture parity test for build_page.

The fixture is a pair:
  * golden_gizmo.schema.json  — the generator INPUT (a DatabaseSchema), authored
    to match golden_gizmo.ddl.sql.
  * golden_gizmo.page.xml     — the EXPECTED <Page> serialization.

`build_page(schema)` serialized at indent 0 must equal the .xml byte-for-byte
(modulo trailing newline). To regenerate the .xml after an intended change to the
generator, run with UPDATE_GOLDEN=1:

    $env:UPDATE_GOLDEN='1'; python -m pytest tests/generation/test_golden_page.py -q

PROVENANCE: golden_gizmo.page.xml is currently a SELF-GENERATED snapshot (a
regression lock on the generator's own output), NOT yet a true parity oracle.
It becomes a parity oracle once it is replaced by the <Page> block that PHP
Generator itself emits for a freshly-added pr.gizmo table (see the capture
procedure in golden_gizmo.ddl.sql / fixtures/README.md). When that real output
is dropped in, this test will fail on every attribute the generator does not yet
match — that failure list is the parity to-do list; calibrate type_map.py until
it is green again.
"""
import json
import os
from pathlib import Path

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.generation import from_table

_FIXTURES = Path(__file__).parent / "fixtures"


def schema_from_json(path: Path) -> DatabaseSchema:
    """Load a one-table DatabaseSchema from a fixture JSON (see the format in
    golden_gizmo.schema.json). Unknown keys like "__doc__" are ignored."""
    data = json.loads(path.read_text(encoding="utf-8"))
    columns = [
        ColumnInfo(
            name=c["name"],
            data_type=c["data_type"],
            is_pk=c["is_pk"],
            is_fk=c["is_fk"],
            is_nullable=c["is_nullable"],
            default=c.get("default"),
            fk_target=c.get("fk_target"),
        )
        for c in data["columns"]
    ]
    table = TableInfo(name=data["table"], kind=data.get("kind", "table"), columns=columns)
    return DatabaseSchema(tables={table.name: table})


def test_golden_gizmo_page_matches():
    schema = schema_from_json(_FIXTURES / "golden_gizmo.schema.json")
    generated = from_table.serialize(from_table.build_page(schema, "pr.gizmo"), indent=0)

    golden_path = _FIXTURES / "golden_gizmo.page.xml"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden_path.write_text(generated + "\n", encoding="utf-8")

    expected = golden_path.read_text(encoding="utf-8").rstrip("\n")
    assert generated == expected
