# tests/generation/test_golden_page.py
"""Golden-fixture parity test for build_page.

Each fixture is a pair:
  * <name>.schema.json  — the generator INPUT (a DatabaseSchema), authored to
    match <name>.ddl.sql.
  * <name>.page.xml      — the EXPECTED <Page>.

Comparison is whitespace-normalized: both the generated element and the parsed
.page.xml are run through `from_table.serialize`, so PHP Generator's space
indentation and our tab indentation compare equal while attribute order (which
IS parity-significant) is preserved.

Fixtures are of two kinds:
  * REAL oracles (`_REAL_ORACLES`): the verbatim <Page> PHP Generator produced
    for a clean, no-edits table add. Ground truth — the generator must reproduce
    them. UPDATE_GOLDEN must NOT overwrite these.
  * self-generated snapshots: regression locks on our own output, pending a real
    capture (see fixtures/README.md). UPDATE_GOLDEN regenerates these:

        UPDATE_GOLDEN=1 python -m pytest tests/generation/test_golden_page.py -q
"""
import json
import os
from pathlib import Path

import pytest
from lxml import etree

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.generation import from_table

_FIXTURES = Path(__file__).parent / "fixtures"

# Real PHP Generator clean-defaults captures — ground-truth parity oracles.
_REAL_ORACLES = {"golden_newtable_1"}

# All fixture base names (each has <name>.schema.json + <name>.page.xml).
_GOLDEN_FIXTURES = [
    "golden_newtable_1",
    "golden_gizmo",
    "golden_gizmo_tag",
    "golden_memo",
]


def schema_from_json(path: Path) -> DatabaseSchema:
    """Load a one-table DatabaseSchema from a fixture JSON (see the format in
    golden_newtable_1.schema.json). Unknown keys like "__doc__" are ignored."""
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


def _normalize(xml_text: str) -> str:
    """Re-serialize an XML fragment through the generator's serializer so
    indentation is normalized while attribute order is preserved."""
    element = etree.fromstring(xml_text.encode("utf-8"))
    return from_table.serialize(element, indent=0)


@pytest.mark.parametrize("name", _GOLDEN_FIXTURES)
def test_golden_page_matches(name):
    schema = schema_from_json(_FIXTURES / f"{name}.schema.json")
    (table_key,) = schema.tables  # single-table fixture
    generated = from_table.serialize(from_table.build_page(schema, table_key), indent=0)

    golden_path = _FIXTURES / f"{name}.page.xml"
    if os.environ.get("UPDATE_GOLDEN") == "1" and name not in _REAL_ORACLES:
        golden_path.write_text(generated + "\n", encoding="utf-8")

    expected = _normalize(golden_path.read_text(encoding="utf-8"))
    assert generated == expected
