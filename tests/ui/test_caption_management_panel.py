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
