# tests/ui/test_db_check_panel.py
"""Rendering + signal tests for DbCheckPanel (headless, no modal, no live DB)."""
from PySide6.QtCore import Qt

from pgtp_editor.db.compare import ColumnCheck, TableCheck
from pgtp_editor.db.introspect import ColumnInfo
from pgtp_editor.ui.db_check_panel import DbCheckPanel


def _checks():
    a = TableCheck(
        name="pr.a",
        ok=True,
        kind="table",
        invocations=2,
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
        ],
    )
    v = TableCheck(name="pr.v", ok=True, kind="view", invocations=1, columns=[])
    missing = TableCheck(
        name="pr.missing", ok=False, kind=None, invocations=1,
        columns=[ColumnCheck("x", False, None)],
    )
    return [a, v, missing]


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
    # Mismatches: pr.a.gone(1) + pr.missing table(1) + pr.missing.x(1) = 3.
    assert "3" in header


def test_show_only_mismatches_filters(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")

    # Unfiltered: all three tables shown.
    assert panel.tree.topLevelItemCount() == 3

    panel.filter_checkbox.setChecked(True)
    names = [it.text(0) for it in _top_items(panel)]
    # pr.v (ok, no mismatch cols) dropped; pr.a kept (has mismatch col); pr.missing kept.
    assert not any("pr.v" in n for n in names)
    assert any("pr.a" in n for n in names)
    assert any("pr.missing" in n for n in names)

    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    # Only the mismatch column remains under pr.a.
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


def test_row_data_role_carries_kind_name_ok(qtbot):
    panel = DbCheckPanel()
    qtbot.addWidget(panel)
    panel.set_result("xml_to_db", _checks(), "u@h:5432/db")
    a_item = next(it for it in _top_items(panel) if "pr.a" in it.text(0))
    kind, name, ok = a_item.data(0, Qt.ItemDataRole.UserRole)
    assert (kind, name, ok) == ("table", "pr.a", True)
