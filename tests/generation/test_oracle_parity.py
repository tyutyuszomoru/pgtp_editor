# tests/generation/test_oracle_parity.py
"""Element-level parity assertions against the REAL clean-defaults oracle
(golden_newtable_1) and the calibrated type_map defaults.

test_golden_page.py already compares the whole <Page> as normalized text; this
module adds *structural* guarantees that the text comparison implies but does
not spell out — most importantly that build_page reproduces the oracle
attribute-by-attribute in the exact emitted order (order is parity-significant),
and the individual calibration rules the recalibration introduced:

  * integer Format has thousandSeparator and NOT decimalSeparator
  * numeric Format is scale-aware (numeric(10,2) -> numberAfterDecimal="2")
  * boolean omits showColumnFilter and uses displayType="image"
  * canSetNull appears only on nullable columns
  * _normalize / serialize preserve attribute order (must NOT sort — C14N would)
"""
import json
from pathlib import Path

from lxml import etree

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.generation import from_table

_FIXTURES = Path(__file__).parent / "fixtures"
_ORACLE = "golden_newtable_1"


def _schema_from_json(path: Path) -> DatabaseSchema:
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


def _assert_elements_equal(generated, expected, path="Page"):
    """Deep, order-sensitive element comparison: tag, attribute (name, value)
    pairs IN ORDER, text, and children in order. Attribute order is asserted
    explicitly because it is the whole point of the parity claim."""
    assert generated.tag == expected.tag, f"tag mismatch at {path}"
    gen_attrs = list(generated.attrib.items())
    exp_attrs = list(expected.attrib.items())
    assert gen_attrs == exp_attrs, (
        f"attribute mismatch at {path}:\n  generated={gen_attrs}\n  expected ={exp_attrs}"
    )
    gen_children = list(generated)
    exp_children = list(expected)
    assert len(gen_children) == len(exp_children), (
        f"child count mismatch at {path}: "
        f"{[c.tag for c in gen_children]} vs {[c.tag for c in exp_children]}"
    )
    for i, (g, e) in enumerate(zip(gen_children, exp_children)):
        _assert_elements_equal(g, e, path=f"{path}/{e.tag}[{i}]")


def _oracle_page():
    xml = (_FIXTURES / f"{_ORACLE}.page.xml").read_text(encoding="utf-8")
    return etree.fromstring(xml.encode("utf-8"))


def _generated_page():
    schema = _schema_from_json(_FIXTURES / f"{_ORACLE}.schema.json")
    (table_key,) = schema.tables
    return from_table.build_page(schema, table_key)


# -- the core parity claim, at the element level ----------------------------

def test_build_page_reproduces_real_oracle_element_for_element():
    """build_page(golden_newtable_1) must equal the verbatim phpgen <Page>
    attribute-by-attribute, in order, recursively."""
    _assert_elements_equal(_generated_page(), _oracle_page())


def test_page_root_attribute_order_matches_oracle():
    generated = _generated_page()
    expected = _oracle_page()
    assert list(generated.attrib.keys()) == list(expected.attrib.keys())
    # spot-check the recalibrated page defaults are actually present
    assert generated.get("editAbilityMode") == "3"
    assert generated.get("deleteSelectedAbilityMode") == "3"
    assert generated.get("highlightRowOnMouseHover") == "true"
    assert generated.get("condensedTable") == "true"


# -- per-column calibration rules -------------------------------------------

def _cp(page, field_name):
    for cp in page.find("ColumnPresentations"):
        if cp.get("fieldName") == field_name:
            return cp
    raise AssertionError(f"no ColumnPresentation for {field_name}")


def test_integer_format_has_thousand_not_decimal_separator():
    page = _generated_page()
    fmt = _cp(page, "integer").find("ViewProperties/Format")
    assert fmt.get("type") == "number"
    assert fmt.get("thousandSeparator") == ","
    assert fmt.get("decimalSeparator") is None
    assert fmt.get("numberAfterDecimal") is None
    # exact attribute order: type then thousandSeparator only
    assert list(fmt.attrib.items()) == [("type", "number"), ("thousandSeparator", ",")]


def test_numeric_format_is_scale_aware():
    # oracle's bare numeric -> default 4
    page = _generated_page()
    fmt = _cp(page, "numeric").find("ViewProperties/Format")
    assert list(fmt.attrib.items()) == [
        ("type", "number"),
        ("numberAfterDecimal", "4"),
        ("decimalSeparator", "."),
        ("thousandSeparator", ","),
    ]
    # scaled numeric(10,2) -> 2, via a synthesized schema
    t = TableInfo(
        name="pr.money", kind="table",
        columns=[
            ColumnInfo("id", "integer", True, False, False, None),
            ColumnInfo("amount", "numeric(10,2)", False, False, True, None),
        ],
    )
    scaled_page = from_table.build_page(DatabaseSchema({t.name: t}), "pr.money")
    scaled_fmt = _cp(scaled_page, "amount").find("ViewProperties/Format")
    assert scaled_fmt.get("numberAfterDecimal") == "2"


def test_boolean_omits_show_column_filter_and_uses_image_display():
    page = _generated_page()
    boolean_cp = _cp(page, "boolean")
    assert boolean_cp.get("showColumnFilter") is None
    assert boolean_cp.get("selectedFilterOperators") == "1572867"
    view = boolean_cp.find("ViewProperties")
    assert view.get("type") == "checkBox"
    assert view.get("displayType") == "image"
    assert view.find("Format") is None
    assert boolean_cp.find("EditProperties").get("type") == "checkBox"


def test_show_column_filter_false_on_all_non_boolean_columns():
    page = _generated_page()
    for field_name in ("serial", "integer", "comment", "numeric"):
        assert _cp(page, field_name).get("showColumnFilter") == "false", field_name


def test_can_set_null_only_on_nullable_columns():
    page = _generated_page()
    # serial is NOT NULL (the PK) -> no canSetNull
    assert _cp(page, "serial").get("canSetNull") is None
    # the rest are nullable -> canSetNull="true"
    for field_name in ("integer", "comment", "numeric", "boolean"):
        assert _cp(page, field_name).get("canSetNull") == "true", field_name


def test_column_presentation_attribute_order_matches_oracle():
    """Attribute order within each <ColumnPresentation> is parity-significant:
    fieldName, caption, [showColumnFilter], [canSetNull], selectedFilterOperators."""
    generated = _generated_page()
    expected = _oracle_page()
    gen_cps = list(generated.find("ColumnPresentations"))
    exp_cps = list(expected.find("ColumnPresentations"))
    assert len(gen_cps) == len(exp_cps)
    for g, e in zip(gen_cps, exp_cps):
        assert list(g.attrib.items()) == list(e.attrib.items()), e.get("fieldName")


# -- serializer / normalizer must not reorder attributes --------------------

def test_serialize_preserves_attribute_order_not_alphabetical():
    """serialize must emit attributes in insertion order, never sorted (a C14N
    canonicalization would sort them and break parity)."""
    el = etree.Element("Page")
    # deliberately non-alphabetical insertion order
    el.set("type", "table")
    el.set("addSeparator", "false")
    el.set("recordsPerPage", "20")
    text = from_table.serialize(el, indent=0)
    assert text == '<Page type="table" addSeparator="false" recordsPerPage="20"/>'
    # sorted order would put addSeparator first — assert it does NOT.
    assert not text.startswith('<Page addSeparator=')


def test_normalize_roundtrip_preserves_attribute_order():
    """Parsing the oracle and re-serializing must keep the source attribute
    order (the golden test relies on this — sorting would silently pass a broken
    generator)."""
    raw = (_FIXTURES / f"{_ORACLE}.page.xml").read_text(encoding="utf-8")
    element = etree.fromstring(raw.encode("utf-8"))
    reserialized = from_table.serialize(element, indent=0)
    first_line = reserialized.splitlines()[0]
    # The oracle's root starts type -> tableName -> numberByDataSource -> fileName.
    assert first_line.startswith(
        '<Page type="table" tableName="public.newtable_1" '
        'numberByDataSource="0" fileName="newtable_1" caption="Newtable 1"'
    )
