# tests/ui/test_db_check_panel.py
"""Rendering + signal tests for DbCheckPanel (headless, no modal, no live DB)."""
from PySide6.QtCore import Qt

from pgtp_editor.db.compare import ColumnCheck, TableCheck
from pgtp_editor.db.introspect import ColumnInfo
from pgtp_editor.ui.db_check_panel import _BAD_COLOR, _CALC_COLOR, _OK_COLOR, DbCheckPanel


def _checks():
    a = TableCheck(
        name="pr.a",
        ok=True,
        kind="table",
        invocations=2,
        page_count=2,
        columns=[
            ColumnCheck(
                "id", True,
                ColumnInfo("id", "integer", True, False, False, "nextval('s')"),
            ),
            ColumnCheck(
                "name", True,
                ColumnInfo("name", "varchar(255)", False, False, True, None),
            ),
            ColumnCheck(
                "fk_c", True,
                ColumnInfo("fk_c", "integer", False, True, True, None),
            ),
            ColumnCheck("gone", False, None),
            # Calculated XML column (BUG-006): no DB counterpart (ok=False)
            # but never a mismatch.
            ColumnCheck("calc_total", False, None, is_calculated=True),
        ],
    )
    v = TableCheck(
        name="pr.v", ok=True, kind="view", invocations=1, page_count=1, columns=[],
    )
    # BUG-026: referenced only as a column-lookup target — ok=True (not a
    # mismatch) with an all-lookup role split.
    lookup_only = TableCheck(
        name="pr.lookonly", ok=True, kind="table", invocations=2,
        lookup_count=2, columns=[],
    )
    missing = TableCheck(
        name="pr.missing", ok=False, kind=None, invocations=1,
        columns=[ColumnCheck("x", False, None)],
    )
    return [a, v, lookup_only, missing]


def _top_items(panel):
    tree = panel.tree
    return [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]


def test_table_row_prefix_count_and_marker(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    items = {it.text(0): it for it in _top_items(panel)}
    a_text = next(t for t in items if "pr.a" in t)
    assert a_text.startswith("✓")
    assert "(T)" in a_text
    assert "pr.a" in a_text
    assert "(×2)" in a_text

    v_text = next(t for t in items if "pr.v" in t)
    assert "(V)" in v_text

    missing_text = next(t for t in items if "pr.missing" in t)
    assert missing_text.startswith("✗")
    # No kind prefix when kind is None.
    assert "(T)" not in missing_text and "(V)" not in missing_text


# -- role-split counts (BUG-026) ------------------------------------------


def test_db_to_xml_row_shows_role_split_count(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")

    texts = [it.text(0) for it in _top_items(panel)]
    a_text = next(t for t in texts if "pr.a" in t)
    assert "(P2 D0 L0)" in a_text
    assert "(×" not in a_text

    missing_text = next(t for t in texts if "pr.missing" in t)
    assert "(P0 D0 L0)" in missing_text


def test_lookup_only_table_is_green_and_role_split(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")

    item = next(it for it in _top_items(panel) if "pr.lookonly" in it.text(0))
    text = item.text(0)
    assert text.startswith("✓")
    assert "(P0 D0 L2)" in text
    assert item.foreground(0).color() == _OK_COLOR
    assert item.foreground(0).color() != _BAD_COLOR


def test_unreferenced_table_stays_red_in_db_to_xml(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")

    item = next(it for it in _top_items(panel) if "pr.missing" in it.text(0))
    assert item.text(0).startswith("✗")
    assert item.foreground(0).color() == _BAD_COLOR


def test_xml_to_db_keeps_aggregate_count(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    texts = [it.text(0) for it in _top_items(panel)]
    assert any("(×2)" in t for t in texts)
    assert not any("(P" in t for t in texts)


def test_column_row_metadata_and_pk_underline(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    cols = {a_item.child(i).text(0): a_item.child(i) for i in range(a_item.childCount())}

    id_text = next(t for t in cols if t.startswith("✓") and " id " in f" {t} ")
    id_item = cols[id_text]
    assert "integer" in id_text
    assert "NOT NULL" in id_text
    assert "DEFAULT nextval('s')" in id_text
    assert id_item.font(0).underline() is True  # PK underlined

    name_text = next(t for t in cols if "name" in t)
    assert "varchar(255)" in name_text
    assert "NOT NULL" not in name_text  # nullable
    assert cols[name_text].font(0).underline() is False

    fk_text = next(t for t in cols if "fk_c" in t)
    assert "(fk)" in fk_text

    gone_text = next(t for t in cols if "gone" in t)
    assert gone_text.startswith("✗")
    assert "integer" not in gone_text  # no info → just name + marker


def test_header_shows_direction_connection_and_mismatch_count(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    header = panel.header_label.text()
    assert "XML" in header and "Database" in header
    assert "u@h:5432/db" in header
    # Mismatches: pr.a.gone(1) + pr.missing table(1) + pr.missing.x(1) = 3;
    # pr.a.calc_total (calculated, BUG-006) is NOT counted despite ok=False,
    # and pr.lookonly (lookup-only, ok=True, BUG-026) is NOT counted either.
    assert "3 mismatches" in header
    assert "4 mismatches" not in header


def test_lookup_only_table_not_in_mismatch_count(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")
    # Same 3 as above: the lookup-only table contributes nothing.
    assert "3 mismatches" in panel.header_label.text()


def test_show_only_mismatches_filters(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    # Unfiltered: all four tables shown.
    assert panel.tree.topLevelItemCount() == 4

    panel.filter_checkbox.setChecked(True)
    names = [it.text(0) for it in _top_items(panel)]
    # pr.v (ok, no mismatch cols) dropped; pr.lookonly (lookup-only, ok=True,
    # BUG-026) dropped too; pr.a kept (has mismatch col); pr.missing kept.
    assert not any("pr.v" in n for n in names)
    assert not any("pr.lookonly" in n for n in names)
    assert any("pr.a" in n for n in names)
    assert any("pr.missing" in n for n in names)

    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    # Only the mismatch column remains under pr.a — the calculated
    # calc_total (ok=False but is_calculated) is excluded too (BUG-006).
    assert a_item.childCount() == 1
    assert "gone" in a_item.child(0).text(0)

    # Header count is independent of the filter.
    assert "3" in panel.header_label.text()


def test_double_click_emits_jump(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    received = []
    panel.jump_requested.connect(lambda k, n: received.append((k, n)))

    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    panel.tree.itemDoubleClicked.emit(a_item, 0)
    assert received == [("table", "pr.a")]

    received.clear()
    col_item = a_item.child(0)
    panel.tree.itemDoubleClicked.emit(col_item, 0)
    assert received[0][0] == "column"


def test_rename_requested_only_for_not_found_xml_to_db(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    received = []
    panel.rename_requested.connect(lambda k, n: received.append((k, n)))

    missing = next(it for it in _top_items(panel) if "pr.missing" in it.text(0))
    panel.contextual_rename(missing)
    assert received == [("table", "pr.missing")]

    # A found table offers no rename.
    received.clear()
    found = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    panel.contextual_rename(found)
    assert received == []


def test_rename_not_offered_for_db_to_xml(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")

    received = []
    panel.rename_requested.connect(lambda k, n: received.append((k, n)))
    missing = next(it for it in _top_items(panel) if "pr.missing" in it.text(0))
    panel.contextual_rename(missing)
    assert received == []


def test_create_menu_only_in_db_to_xml_for_table_nodes(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)

    # XML → Database: no create actions at all.
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")
    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    assert panel.create_menu_items(a_item) == []

    # Database → XML: table node offers the three create actions.
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")
    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    whats = [what for what, _label in panel.create_menu_items(a_item)]
    assert whats == ["page", "detail", "lookup"]

    # A column child node offers nothing.
    col_item = a_item.child(0)
    assert panel.create_menu_items(col_item) == []


def test_create_menu_offered_for_view_nodes(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")
    v_item = next(it for it in _top_items(panel) if "pr.v" in it.text(0))
    whats = [what for what, _label in panel.create_menu_items(v_item)]
    assert whats == ["page", "detail", "lookup"]


def test_request_create_emits_with_table_name(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")

    received = []
    panel.create_requested.connect(lambda w, n: received.append((w, n)))
    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    panel.request_create("page", a_item)
    panel.request_create("detail", a_item)
    assert received == [("page", "pr.a"), ("detail", "pr.a")]


# -- calculated columns (BUG-006) -----------------------------------------


def _calc_item(panel):
    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    return next(
        a_item.child(i)
        for i in range(a_item.childCount())
        if "calc_total" in a_item.child(i).text(0)
    )


def test_calculated_column_gets_tilde_marker_and_calc_color(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    calc = _calc_item(panel)
    text = calc.text(0)
    assert text.startswith("~")
    assert "✓" not in text and "✗" not in text
    assert calc.foreground(0).color() == _CALC_COLOR


def test_calculated_marker_overrides_ok_true(qtbot):
    # A calculated column that coincidentally shadows a real DB column
    # (ok=True) still renders as calculated, not as a green match.
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    shadow = TableCheck(
        name="pr.s", ok=True, kind="table", invocations=1,
        columns=[
            ColumnCheck(
                "shadow", True,
                ColumnInfo("shadow", "integer", False, False, True, None),
                is_calculated=True,
            ),
        ],
    )
    panel.set_result("xml_to_db", [shadow], "u@h:5432/db")
    item = _top_items(panel)[0].child(0)
    assert item.text(0).startswith("~")
    assert item.foreground(0).color() == _CALC_COLOR


def test_calculated_column_role_carries_is_calculated(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    calc = _calc_item(panel)
    kind, name, ok, is_calculated = calc.data(0, Qt.ItemDataRole.UserRole)
    assert (kind, name, ok, is_calculated) == ("column", "calc_total", False, True)


def test_no_rename_offered_for_calculated_column(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    received = []
    panel.rename_requested.connect(lambda k, n: received.append((k, n)))
    panel.contextual_rename(_calc_item(panel))
    assert received == []

    # Sanity: a genuinely missing column in the same tree still offers rename.
    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    gone = next(
        a_item.child(i)
        for i in range(a_item.childCount())
        if "gone" in a_item.child(i).text(0)
    )
    panel.contextual_rename(gone)
    assert received == [("column", "gone")]


def test_double_click_on_calculated_column_still_jumps(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    received = []
    panel.jump_requested.connect(lambda k, n: received.append((k, n)))
    panel.tree.itemDoubleClicked.emit(_calc_item(panel), 0)
    assert received == [("column", "calc_total")]


def test_row_data_role_carries_kind_name_ok(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")
    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    kind, name, ok, is_calculated = a_item.data(0, Qt.ItemDataRole.UserRole)
    assert (kind, name, ok, is_calculated) == ("table", "pr.a", True, False)


def test_role_split_renders_all_three_counters(qtbot):
    # BUG-026: the three counters are rendered independently and in P/D/L
    # order, so a table used in every role reads as such.
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    every_role = TableCheck(
        name="pr.every", ok=True, kind="table", invocations=6,
        page_count=1, detail_count=2, lookup_count=3, columns=[],
    )
    panel.set_result("db_to_xml", [every_role], "u@h:5432/db")
    assert "(P1 D2 L3)" in _top_items(panel)[0].text(0)


def test_direction_change_reruns_the_count_rendering(qtbot):
    # The same panel instance is reused for both directions; the count form
    # must follow the direction of the LAST set_result, not the first.
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")
    assert any("(P2 D0 L0)" in it.text(0) for it in _top_items(panel))

    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")
    texts = [it.text(0) for it in _top_items(panel)]
    assert any("(×2)" in t for t in texts)
    assert not any("(P" in t for t in texts)

    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")
    texts = [it.text(0) for it in _top_items(panel)]
    assert any("(P2 D0 L0)" in t for t in texts)
    assert not any("(×" in t for t in texts)


def test_role_split_row_keeps_kind_prefix_and_marker(qtbot):
    # The BUG-026 count change must not disturb the rest of the row format:
    # "<marker> <kind prefix><name> <count>".
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("db_to_xml", _checks(), "u@h:5432/db")
    v_text = next(t for t in (it.text(0) for it in _top_items(panel)) if "pr.v" in t)
    assert v_text == "✓ (V) pr.v (P1 D0 L0)"
