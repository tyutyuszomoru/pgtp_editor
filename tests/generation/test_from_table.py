# tests/generation/test_from_table.py
"""Tests for the page/detail/lookup synthesizer (generation.from_table)."""
import pytest

from pgtp_editor.db.introspect import ColumnInfo, DatabaseSchema, TableInfo
from pgtp_editor.generation import from_table


def _schema():
    """A small parent (equipment) + child-with-FK (part) + lookup (x_wbs)."""
    equipment = TableInfo(
        name="pr.equipment",
        kind="table",
        columns=[
            ColumnInfo("id", "integer", is_pk=True, is_fk=False, is_nullable=False, default=None),
            ColumnInfo("tag", "character varying(30)", is_pk=False, is_fk=False, is_nullable=True, default=None),
            ColumnInfo("active", "boolean", is_pk=False, is_fk=False, is_nullable=True, default=None),
        ],
    )
    part = TableInfo(
        name="pr.part",
        kind="table",
        columns=[
            ColumnInfo("id", "integer", is_pk=True, is_fk=False, is_nullable=False, default=None),
            ColumnInfo("equipment_id", "integer", is_pk=False, is_fk=True, is_nullable=False,
                       default=None, fk_target="pr.equipment.id"),
            ColumnInfo("qty", "numeric(10,2)", is_pk=False, is_fk=False, is_nullable=True, default=None),
        ],
    )
    wbs = TableInfo(
        name="pr.x_wbs",
        kind="table",
        columns=[
            ColumnInfo("wbs_id", "integer", is_pk=True, is_fk=False, is_nullable=False, default=None),
            ColumnInfo("wbs_name", "text", is_pk=False, is_fk=False, is_nullable=True, default=None),
        ],
    )
    return DatabaseSchema({t.name: t for t in (equipment, part, wbs)})


# -- build_page -------------------------------------------------------------

def test_build_page_identity_and_defaults():
    page = from_table.build_page(_schema(), "pr.equipment")
    assert page.tag == "Page"
    assert page.get("type") == "table"
    assert page.get("tableName") == "pr.equipment"
    assert page.get("fileName") == "equipment"  # bare table name, not schema-qualified
    assert page.get("caption") == "Equipment"
    assert page.get("shortCaption") == "Equipment"
    assert page.get("recordsPerPage") == "20"
    assert page.get("contentEncoding") == "UTF-8"


def test_build_page_has_column_presentation_per_column():
    page = from_table.build_page(_schema(), "pr.equipment")
    cps = page.find("ColumnPresentations")
    field_names = [cp.get("fieldName") for cp in cps.findall("ColumnPresentation")]
    assert field_names == ["id", "tag", "active"]
    # numeric id -> Format number
    id_cp = cps.findall("ColumnPresentation")[0]
    assert id_cp.find("ViewProperties/Format").get("type") == "number"
    # boolean active -> checkBox editor
    active_cp = cps.findall("ColumnPresentation")[2]
    assert active_cp.find("EditProperties").get("type") == "checkBox"


def test_build_page_has_all_ten_representations_with_pk_hidden():
    page = from_table.build_page(_schema(), "pr.equipment")
    columns = page.find("Columns")
    reps = [child.tag for child in columns]
    assert reps == [
        "List", "View", "Edit", "Insert", "QuickFilter",
        "FilterBuilder", "Print", "Export", "Compare", "MultiEdit",
    ]
    # every rep lists all three columns
    for rep in columns:
        assert [c.get("fieldName") for c in rep] == ["id", "tag", "active"]
    # id (PK) hidden in Edit/Insert/Compare/MultiEdit, visible elsewhere
    edit_id = columns.find("Edit").find("Column")
    assert edit_id.get("fieldName") == "id"
    assert edit_id.get("visible") == "false"
    list_id = columns.find("List").find("Column")
    assert list_id.get("visible") is None
    assert page.find("Details") is not None


def test_build_page_unknown_table_raises():
    with pytest.raises(from_table.GenerationError):
        from_table.build_page(_schema(), "nope.table")


# -- build_detail -----------------------------------------------------------

def test_build_detail_infers_master_foreign_from_single_fk():
    detail = from_table.build_detail(_schema(), "pr.part")
    assert detail.tag == "Detail"
    assert detail.get("caption") == "Part"
    inner = detail.find("Page")
    assert inner.get("tableName") == "pr.part"
    assert inner.get("fileName") == ""  # detail pages carry empty fileName
    field_map = detail.find("MasterForeignKeyColumnMap/FieldMap")
    assert field_map.get("foreginColumnName") == "equipment_id"  # vendor misspelling
    assert field_map.get("masterColumnName") == "id"


def test_build_detail_empty_placeholders_when_no_fk():
    detail = from_table.build_detail(_schema(), "pr.equipment")
    field_map = detail.find("MasterForeignKeyColumnMap/FieldMap")
    assert field_map.get("masterColumnName") == ""
    assert field_map.get("foreginColumnName") == ""


# -- build_lookup -----------------------------------------------------------

def test_build_lookup_uses_pk_and_display_field():
    lookup = from_table.build_lookup(_schema(), "pr.x_wbs")
    assert lookup.tag == "Lookup"
    assert lookup.get("tableName") == "pr.x_wbs"
    assert lookup.get("linkFieldName") == "wbs_id"
    assert lookup.get("displayFieldName") == "wbs_name"
    assert lookup.get("lookupFilter") == ""
    assert lookup.get("useLookupOrdering") == "true"
    assert lookup.get("lookupOrdering") == "0"


# -- serialize --------------------------------------------------------------

def test_serialize_is_tab_indented_and_collapses_empty():
    lookup = from_table.build_lookup(_schema(), "pr.x_wbs")
    text = from_table.serialize(lookup, indent=2)
    assert text.startswith("\t\t<Lookup ")
    assert text.rstrip().endswith("/>")  # empty element collapsed
    assert 'tableName="pr.x_wbs"' in text


def test_serialize_nested_page_structure():
    page = from_table.build_page(_schema(), "pr.x_wbs")
    text = from_table.serialize(page, indent=0)
    lines = text.splitlines()
    assert lines[0].startswith("<Page ")
    assert 'tableName="pr.x_wbs"' in lines[0]
    assert "\t<ColumnPresentations>" in text
    assert "\t\t<ColumnPresentation " in text
    assert text.rstrip().endswith("</Page>")


# -- edge cases: composite / missing PK -------------------------------------

def _table(name, columns, kind="table"):
    return TableInfo(name=name, kind=kind, columns=columns)


def _col(name, dtype, *, pk=False, fk=False, target=None):
    return ColumnInfo(name, dtype, is_pk=pk, is_fk=fk, is_nullable=True,
                      default=None, fk_target=target)


def test_build_lookup_composite_pk_leaves_link_empty():
    """>1 PK column is ambiguous → linkFieldName is an empty placeholder."""
    t = _table("pr.bridge", [
        _col("a_id", "integer", pk=True),
        _col("b_id", "integer", pk=True),
        _col("label", "text"),
    ])
    schema = DatabaseSchema({t.name: t})
    lookup = from_table.build_lookup(schema, "pr.bridge")
    assert lookup.get("linkFieldName") == ""
    # display still resolves to the first text-like non-PK column
    assert lookup.get("displayFieldName") == "label"


def test_build_lookup_no_pk_leaves_link_empty_and_picks_display():
    t = _table("pr.nopk", [
        _col("code", "varchar(10)"),
        _col("descr", "text"),
    ])
    schema = DatabaseSchema({t.name: t})
    lookup = from_table.build_lookup(schema, "pr.nopk")
    assert lookup.get("linkFieldName") == ""
    # first text-ish non-PK column
    assert lookup.get("displayFieldName") == "code"


def test_build_lookup_single_column_pk_only_display_falls_back_to_pk():
    t = _table("pr.only", [_col("only_id", "integer", pk=True)])
    schema = DatabaseSchema({t.name: t})
    lookup = from_table.build_lookup(schema, "pr.only")
    assert lookup.get("linkFieldName") == "only_id"
    # no non-PK columns → display falls back to the PK
    assert lookup.get("displayFieldName") == "only_id"


def test_build_lookup_display_skips_fk_but_falls_back_to_it():
    """Only candidate non-PK columns are numeric FKs → not text-like, so the
    guesser falls back to the first non-PK column (the FK)."""
    t = _table("pr.link", [
        _col("id", "integer", pk=True),
        _col("other_id", "integer", fk=True, target="pr.other.id"),
    ])
    schema = DatabaseSchema({t.name: t})
    lookup = from_table.build_lookup(schema, "pr.link")
    assert lookup.get("linkFieldName") == "id"
    assert lookup.get("displayFieldName") == "other_id"


# -- edge cases: page for view kind / no PK ---------------------------------

def test_build_page_for_view_kind():
    v = _table("pr.some_view", [
        _col("vid", "integer", pk=True),
        _col("vname", "text"),
    ], kind="view")
    schema = DatabaseSchema({v.name: v})
    page = from_table.build_page(schema, "pr.some_view")
    assert page.get("tableName") == "pr.some_view"
    assert page.get("fileName") == "some_view"
    field_names = [cp.get("fieldName")
                   for cp in page.find("ColumnPresentations")]
    assert field_names == ["vid", "vname"]


def test_build_page_no_pk_hides_nothing():
    t = _table("pr.flat", [
        _col("a", "integer"),
        _col("b", "text"),
    ])
    schema = DatabaseSchema({t.name: t})
    page = from_table.build_page(schema, "pr.flat")
    columns = page.find("Columns")
    for rep in columns:
        for entry in rep:
            assert entry.get("visible") is None  # nothing hidden without a PK


def test_build_page_empty_columns_raises():
    t = _table("pr.empty", [])
    schema = DatabaseSchema({t.name: t})
    with pytest.raises(from_table.GenerationError):
        from_table.build_page(schema, "pr.empty")


# -- edge cases: detail FK inference ----------------------------------------

def test_build_detail_multi_fk_empty_placeholders():
    """>1 FK column is ambiguous → empty master/foreign placeholders."""
    t = _table("pr.join", [
        _col("id", "integer", pk=True),
        _col("a_id", "integer", fk=True, target="pr.a.id"),
        _col("b_id", "integer", fk=True, target="pr.b.id"),
    ])
    schema = DatabaseSchema({t.name: t})
    detail = from_table.build_detail(schema, "pr.join")
    field_map = detail.find("MasterForeignKeyColumnMap/FieldMap")
    assert field_map.get("masterColumnName") == ""
    assert field_map.get("foreginColumnName") == ""


def test_build_detail_single_fk_unknown_target_empty_master():
    """A single FK with no known target column → foreign filled, master empty."""
    t = _table("pr.child", [
        _col("id", "integer", pk=True),
        _col("parent_id", "integer", fk=True, target=None),
    ])
    schema = DatabaseSchema({t.name: t})
    detail = from_table.build_detail(schema, "pr.child")
    field_map = detail.find("MasterForeignKeyColumnMap/FieldMap")
    assert field_map.get("foreginColumnName") == "parent_id"
    assert field_map.get("masterColumnName") == ""


# -- serialization: escaping ------------------------------------------------

def test_serialize_escapes_special_chars_in_attributes():
    from lxml import etree

    el = etree.Element("Lookup")
    el.set("lookupFilter", 'a < b & c > d "quoted"')
    text = from_table.serialize(el, indent=0)
    assert "&lt;" in text and "&gt;" in text
    assert "&amp;" in text and "&quot;" in text
    # No raw special chars leak into the attribute value.
    assert 'a < b' not in text


def test_serialize_escapes_special_chars_in_text():
    from lxml import etree

    el = etree.Element("BeforeGridText")
    el.text = "x < y & z"
    text = from_table.serialize(el, indent=0)
    assert "&lt;" in text and "&amp;" in text
    assert text.startswith("<BeforeGridText>")
    assert text.endswith("</BeforeGridText>")
