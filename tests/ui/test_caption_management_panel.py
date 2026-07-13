from PySide6.QtCore import Qt

from pgtp_editor.ui.caption_scan import CaptionEntry
from pgtp_editor.ui.caption_management_panel import CaptionManagementPanel


def _entry(line, tag, anchor, attribute, value):
    return CaptionEntry(
        line=line, element_tag=tag, anchor=anchor, attribute=attribute, value=value
    )


def _sample_entries():
    return [
        _entry(2, "Page", "home", "caption", "Home"),
        _entry(3, "Detail", "orders", "caption", "Orders"),
        _entry(3, "Detail", "orders", "shortCaption", "Ord"),
    ]


def test_headers_are_line_element_anchor_attribute_value(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    model = panel._model
    headers = [
        model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for col in range(model.columnCount())
    ]
    assert headers == ["Line", "Element", "Anchor", "Attribute", "Value"]


def test_load_entries_populates_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    model = panel._model
    assert model.rowCount() == 3
    # Row 0 cells, in column order.
    assert model.index(0, 0).data() == "2"
    assert model.index(0, 1).data() == "Page"
    assert model.index(0, 2).data() == "home"
    assert model.index(0, 3).data() == "caption"
    assert model.index(0, 4).data() == "Home"


def test_only_value_column_is_editable(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    model = panel._model
    for col in range(5):
        flags = model.flags(model.index(0, col))
        editable = bool(flags & Qt.ItemFlag.ItemIsEditable)
        assert editable is (col == 4), f"column {col} editability wrong"


def test_load_entries_replaces_previous_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    panel.load_entries([_entry(9, "X", "a", "caption", "Solo")])
    assert panel._model.rowCount() == 1
    assert panel._model.index(0, 4).data() == "Solo"


def _visible_value_column(panel):
    proxy = panel._proxy
    return [
        proxy.index(r, 4).data(Qt.ItemDataRole.DisplayRole)
        for r in range(proxy.rowCount())
    ]


def test_filter_value_column_narrows_visible_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
            _entry(4, "Detail", "orders", "shortCaption", "Ord"),
        ]
    )
    # Column 4 is Value; filtering "ord" (case-insensitive) keeps Orders + Ord.
    panel._filter_fields[4].setText("ord")
    assert sorted(_visible_value_column(panel)) == ["Ord", "Orders"]


def test_filter_attribute_column(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "shortCaption", "Ord"),
        ]
    )
    panel._filter_fields[3].setText("shortcaption")  # case-insensitive
    assert _visible_value_column(panel) == ["Ord"]


def test_filters_are_anded_across_columns(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
            _entry(4, "Detail", "orders", "shortCaption", "Ord"),
        ]
    )
    panel._filter_fields[1].setText("detail")   # Element == Detail
    panel._filter_fields[3].setText("caption")  # Attribute contains "caption"
    # Both Detail rows have Attribute containing "caption" (caption AND
    # shortCaption), so ANDing keeps both.
    assert sorted(_visible_value_column(panel)) == ["Ord", "Orders"]

    panel._filter_fields[4].setText("orders")   # now also Value contains "orders"
    assert _visible_value_column(panel) == ["Orders"]


def test_empty_filter_shows_all_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
        ]
    )
    panel._filter_fields[4].setText("home")
    panel._filter_fields[4].setText("")  # cleared
    assert sorted(_visible_value_column(panel)) == ["Home", "Orders"]


def test_sorting_by_value_column(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Zebra"),
            _entry(3, "Detail", "orders", "caption", "Apple"),
        ]
    )
    panel._proxy.sort(4, Qt.SortOrder.AscendingOrder)
    assert _visible_value_column(panel) == ["Apple", "Zebra"]


def test_sorting_by_line_column_is_numeric(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(10, "Page", "a", "caption", "ten"),
            _entry(2, "Page", "b", "caption", "two"),
            _entry(3, "Page", "c", "caption", "three"),
        ]
    )
    panel._proxy.sort(0, Qt.SortOrder.AscendingOrder)
    proxy = panel._proxy
    lines = [proxy.index(r, 0).data(Qt.ItemDataRole.DisplayRole) for r in range(proxy.rowCount())]
    # Numeric order (2, 3, 10), NOT lexicographic (10, 2, 3).
    assert lines == ["2", "3", "10"]


def _set_value(panel, row, text):
    # Set through the source model's Value column, mirroring an editor commit.
    index = panel._model.index(row, 4)
    panel._model.setData(index, text, Qt.ItemDataRole.EditRole)


def test_editing_value_marks_row_changed(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_value(panel, 0, "Homepage")
    assert panel.changed_edits() == [(_sample_entries()[0], "Homepage")]


def test_unchanged_rows_are_not_emitted(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    assert panel.changed_edits() == []


def test_editing_then_restoring_original_value_is_not_dirty(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_value(panel, 0, "Homepage")
    _set_value(panel, 0, "Home")  # back to the original scanned value
    assert panel.changed_edits() == []


def test_apply_invokes_callback_with_edited_text(qtbot):
    captured = {}
    panel = CaptionManagementPanel(on_apply=lambda text: captured.setdefault("text", text))
    qtbot.addWidget(panel)
    snapshot = '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    entries = [_entry(2, "Page", "home", "caption", "Home")]
    panel.load_entries(entries, snapshot_text=snapshot)
    _set_value(panel, 0, "Homepage")
    panel.apply()
    assert captured["text"] == '<Root>\n  <Page caption="Homepage" fileName="home"/>\n</Root>'


def test_apply_with_no_edits_returns_identical_text(qtbot):
    captured = {}
    panel = CaptionManagementPanel(on_apply=lambda text: captured.setdefault("text", text))
    qtbot.addWidget(panel)
    snapshot = '<Root>\n  <Page caption="Home"/>\n</Root>'
    panel.load_entries([_entry(2, "Page", "home", "caption", "Home")], snapshot_text=snapshot)
    panel.apply()
    assert captured["text"] == snapshot


def test_close_invokes_close_callback(qtbot):
    calls = []
    panel = CaptionManagementPanel(on_close=lambda: calls.append(True))
    qtbot.addWidget(panel)
    panel.close_panel()
    assert calls == [True]


from pgtp_editor.ui.caption_management_panel import _INCONSISTENT_BACKGROUND


def _background(panel, row):
    return panel._model.index(row, 0).data(Qt.ItemDataRole.BackgroundRole)


def test_divergent_anchor_attribute_group_is_tinted(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    # Same (anchor="acct", attribute="caption") but different values -> both
    # rows flagged inconsistent.
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    assert _background(panel, 0) == _INCONSISTENT_BACKGROUND
    assert _background(panel, 1) == _INCONSISTENT_BACKGROUND


def test_consistent_group_is_not_tinted(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Account"),  # identical value
        ]
    )
    assert _background(panel, 0) is None
    assert _background(panel, 1) is None


def test_editing_a_value_can_clear_inconsistency(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    assert _background(panel, 0) == _INCONSISTENT_BACKGROUND
    # Align the second row's value with the first -> group now consistent.
    _set_value(panel, 1, "Account")
    assert _background(panel, 0) is None
    assert _background(panel, 1) is None


def test_different_attribute_same_anchor_not_grouped(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    # Same anchor, DIFFERENT attribute -> not the same group -> not tinted.
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(2, "Page", "acct", "shortCaption", "Acct"),
        ]
    )
    assert _background(panel, 0) is None
    assert _background(panel, 1) is None
