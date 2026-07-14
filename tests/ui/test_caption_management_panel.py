from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from pgtp_editor.ui.caption_scan import CaptionEntry
from pgtp_editor.ui.caption_management_panel import (
    CaptionManagementPanel,
    NULL_SENTINEL,
    _CHANGED_BACKGROUND,
    _INCONSISTENT_BACKGROUND,
    _CHANGED_COLUMN,
    _LINE_COLUMN,
    _BREADCRUMB_COLUMN,
    _ELEMENT_COLUMN,
    _ANCHOR_COLUMN,
    _ATTRIBUTE_COLUMN,
    _VALUE_COLUMN,
    _NEW_VALUE_COLUMN,
)


def _entry(line, tag, anchor, attribute, value, breadcrumb=""):
    return CaptionEntry(
        line=line,
        element_tag=tag,
        anchor=anchor,
        attribute=attribute,
        value=value,
        breadcrumb=breadcrumb,
    )


def _sample_entries():
    return [
        _entry(2, "Page", "home", "caption", "Home"),
        _entry(3, "Detail", "orders", "caption", "Orders"),
        _entry(3, "Detail", "orders", "shortCaption", "Ord"),
    ]


def test_headers_are_full_column_set(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    model = panel._model
    headers = [
        model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for col in range(model.columnCount())
    ]
    assert headers == [
        "Changed",
        "Line",
        "Breadcrumb",
        "Element",
        "Anchor",
        "Attribute",
        "Value",
        "New Value",
    ]


def test_load_entries_populates_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [_entry(2, "Page", "home", "caption", "Home", breadcrumb="Home")]
    )
    model = panel._model
    assert model.rowCount() == 1
    assert model.index(0, _CHANGED_COLUMN).data() == ""
    assert model.index(0, _LINE_COLUMN).data() == "2"
    assert model.index(0, _BREADCRUMB_COLUMN).data() == "Home"
    assert model.index(0, _ELEMENT_COLUMN).data() == "Page"
    assert model.index(0, _ANCHOR_COLUMN).data() == "home"
    assert model.index(0, _ATTRIBUTE_COLUMN).data() == "caption"
    assert model.index(0, _VALUE_COLUMN).data() == "Home"
    assert model.index(0, _NEW_VALUE_COLUMN).data() == ""


def test_only_new_value_column_is_editable(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    model = panel._model
    for col in range(model.columnCount()):
        flags = model.flags(model.index(0, col))
        editable = bool(flags & Qt.ItemFlag.ItemIsEditable)
        assert editable is (col == _NEW_VALUE_COLUMN), f"column {col} editability wrong"


def test_value_column_setData_is_rejected(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    model = panel._model
    assert model.setData(model.index(0, _VALUE_COLUMN), "X", Qt.ItemDataRole.EditRole) is False
    # Value stays the scanned original.
    assert model.index(0, _VALUE_COLUMN).data() == "Home"


def test_load_entries_replaces_previous_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    panel.load_entries([_entry(9, "X", "a", "caption", "Solo")])
    assert panel._model.rowCount() == 1
    assert panel._model.index(0, _VALUE_COLUMN).data() == "Solo"


# -- New Value editing / changed marker ------------------------------------


def _set_new_value(panel, row, text):
    index = panel._model.index(row, _NEW_VALUE_COLUMN)
    panel._model.setData(index, text, Qt.ItemDataRole.EditRole)


def test_editing_new_value_marks_row_changed_and_star(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_new_value(panel, 0, "Homepage")
    assert panel._model.index(0, _CHANGED_COLUMN).data() == "*"
    assert panel.changed_edits() == [(_sample_entries()[0], "Homepage")]


def test_empty_new_value_not_in_changed_edits(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    assert panel.changed_edits() == []
    assert panel._model.index(0, _CHANGED_COLUMN).data() == ""


def test_null_sentinel_resolves_to_empty_string(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_new_value(panel, 0, NULL_SENTINEL)
    assert panel.changed_edits() == [(_sample_entries()[0], "")]
    # Still marked changed.
    assert panel._model.index(0, _CHANGED_COLUMN).data() == "*"


def test_null_sentinel_apply_writes_empty_caption(qtbot):
    captured = {}
    panel = CaptionManagementPanel(on_apply=lambda text: captured.setdefault("text", text))
    qtbot.addWidget(panel)
    snapshot = '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    panel.load_entries([_entry(2, "Page", "home", "caption", "Home")], snapshot_text=snapshot)
    _set_new_value(panel, 0, NULL_SENTINEL)
    panel.apply()
    assert captured["text"] == '<Root>\n  <Page caption="" fileName="home"/>\n</Root>'


# -- coloring ---------------------------------------------------------------


def _background(panel, row):
    return panel._model.index(row, 0).data(Qt.ItemDataRole.BackgroundRole)


def test_changed_row_gets_changed_background(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_new_value(panel, 0, "Homepage")
    assert _background(panel, 0) == _CHANGED_BACKGROUND


def test_changed_color_beats_inconsistency_tint(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    # Both start inconsistent (warm tint).
    assert _background(panel, 0) == _INCONSISTENT_BACKGROUND
    _set_new_value(panel, 0, "AccountX")
    # Changed row now cool tint; unchanged sibling stays warm.
    assert _background(panel, 0) == _CHANGED_BACKGROUND
    assert _background(panel, 1) == _INCONSISTENT_BACKGROUND


def test_unchanged_inconsistent_row_keeps_warm_tint(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    assert _background(panel, 0) == _INCONSISTENT_BACKGROUND
    assert _background(panel, 1) == _INCONSISTENT_BACKGROUND


def test_consistent_unchanged_row_has_no_background(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Account"),
        ]
    )
    assert _background(panel, 0) is None
    assert _background(panel, 1) is None


# -- Insert NULL action -----------------------------------------------------


def _select_source_rows(panel, rows):
    from PySide6.QtCore import QItemSelection, QItemSelectionModel

    sel = panel._table.selectionModel()
    sel.clearSelection()
    for r in rows:
        proxy_index = panel._proxy.mapFromSource(panel._model.index(r, _NEW_VALUE_COLUMN))
        sel.select(proxy_index, QItemSelectionModel.SelectionFlag.Select)
    if rows:
        first = panel._proxy.mapFromSource(panel._model.index(rows[0], _NEW_VALUE_COLUMN))
        sel.setCurrentIndex(first, QItemSelectionModel.SelectionFlag.NoUpdate)


def test_insert_null_action_sets_sentinel(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _select_source_rows(panel, [0, 2])
    panel.insert_null_into_selection()
    assert panel._model.new_value_at(0) == NULL_SENTINEL
    assert panel._model.new_value_at(1) == ""
    assert panel._model.new_value_at(2) == NULL_SENTINEL


# -- Go to line -------------------------------------------------------------


def test_go_to_line_invokes_callback_with_row_line(qtbot):
    calls = []
    panel = CaptionManagementPanel(on_go_to_line=lambda line: calls.append(line))
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _select_source_rows(panel, [1])
    panel.go_to_line_current()
    assert calls == [3]  # row 1 is line 3


def test_go_to_line_default_noop_when_no_selection(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    panel._table.selectionModel().clearSelection()
    panel._table.selectionModel().clearCurrentIndex()
    # Should not raise.
    panel.go_to_line_current()


# -- Copy / Paste -----------------------------------------------------------


def test_copy_selection_produces_tsv(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    from PySide6.QtCore import QItemSelectionModel

    sel = panel._table.selectionModel()
    sel.clearSelection()
    # Select Value column of rows 0 and 1 plus Attribute of row 0 -> 2 rows, 2 cols.
    for (r, c) in [(0, _ATTRIBUTE_COLUMN), (0, _VALUE_COLUMN), (1, _ATTRIBUTE_COLUMN), (1, _VALUE_COLUMN)]:
        idx = panel._proxy.mapFromSource(panel._model.index(r, c))
        sel.select(idx, QItemSelectionModel.SelectionFlag.Select)
    panel.copy_selection()
    text = QGuiApplication.clipboard().text()
    # Row order by proxy row (0 then 1); columns sorted (Attribute < Value).
    assert text == "caption\tHome\ncaption\tOrders"


def test_paste_single_line_fills_all_selected(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    QGuiApplication.clipboard().setText("Filled")
    _select_source_rows(panel, [0, 2])
    panel.paste_into_new_value()
    assert panel._model.new_value_at(0) == "Filled"
    assert panel._model.new_value_at(1) == ""
    assert panel._model.new_value_at(2) == "Filled"


def test_paste_multiline_vertical_fill(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    QGuiApplication.clipboard().setText("A\nB")
    _select_source_rows(panel, [0, 1])
    panel.paste_into_new_value()
    assert panel._model.new_value_at(0) == "A"
    assert panel._model.new_value_at(1) == "B"


def test_paste_only_writes_new_value_not_value(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    QGuiApplication.clipboard().setText("X")
    _select_source_rows(panel, [0])
    panel.paste_into_new_value()
    assert panel._model.index(0, _VALUE_COLUMN).data() == "Home"  # untouched
    assert panel._model.new_value_at(0) == "X"


# -- filtering (still targets the right columns) ---------------------------


def _visible_value_column(panel):
    proxy = panel._proxy
    return [
        proxy.index(r, _VALUE_COLUMN).data(Qt.ItemDataRole.DisplayRole)
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
    panel._filter_fields[_VALUE_COLUMN].setText("ord")
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
    panel._filter_fields[_ATTRIBUTE_COLUMN].setText("shortcaption")
    assert _visible_value_column(panel) == ["Ord"]


def test_filter_changed_column_isolates_changed_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_new_value(panel, 1, "New")
    panel._filter_fields[_CHANGED_COLUMN].setText("*")
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
    panel._filter_fields[_VALUE_COLUMN].setText("home")
    panel._filter_fields[_VALUE_COLUMN].setText("")
    assert sorted(_visible_value_column(panel)) == ["Home", "Orders"]


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
    panel._proxy.sort(_LINE_COLUMN, Qt.SortOrder.AscendingOrder)
    proxy = panel._proxy
    lines = [
        proxy.index(r, _LINE_COLUMN).data(Qt.ItemDataRole.DisplayRole)
        for r in range(proxy.rowCount())
    ]
    assert lines == ["2", "3", "10"]


# -- apply / close ----------------------------------------------------------


def test_apply_invokes_callback_with_edited_text(qtbot):
    captured = {}
    panel = CaptionManagementPanel(on_apply=lambda text: captured.setdefault("text", text))
    qtbot.addWidget(panel)
    snapshot = '<Root>\n  <Page caption="Home" fileName="home"/>\n</Root>'
    panel.load_entries([_entry(2, "Page", "home", "caption", "Home")], snapshot_text=snapshot)
    _set_new_value(panel, 0, "Homepage")
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


# -- Phase 3: Excel-style header value filters ------------------------------


def _value_filter_entries():
    return [
        _entry(2, "Page", "home", "caption", "Home"),
        _entry(3, "Detail", "orders", "caption", "Orders"),
        _entry(4, "Detail", "cart", "caption", "Cart"),
    ]


def test_set_value_filter_hides_unchecked_values(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home", "Cart"})
    assert sorted(_visible_value_column(panel)) == ["Cart", "Home"]


def test_set_value_filter_none_clears(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home"})
    assert _visible_value_column(panel) == ["Home"]
    panel._proxy.set_value_filter(_VALUE_COLUMN, None)
    assert sorted(_visible_value_column(panel)) == ["Cart", "Home", "Orders"]


def test_set_value_filter_empty_set_hides_all(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    panel._proxy.set_value_filter(_VALUE_COLUMN, set())
    assert _visible_value_column(panel) == []


def test_value_filter_ands_with_substring_filter(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Order Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
            _entry(4, "Detail", "cart", "caption", "Cart"),
        ]
    )
    # Substring filter keeps rows containing "order"; value filter keeps only
    # "Orders". Intersection is just "Orders".
    panel._proxy.set_column_filter(_VALUE_COLUMN, "order")
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Orders"})
    assert _visible_value_column(panel) == ["Orders"]


def test_value_filter_ands_across_columns(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "shortCaption", "Home"),
            _entry(4, "Detail", "cart", "caption", "Cart"),
        ]
    )
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home"})
    panel._proxy.set_value_filter(_ATTRIBUTE_COLUMN, {"caption"})
    # Only row 0 has Value "Home" AND Attribute "caption".
    assert _visible_value_column(panel) == ["Home"]


def test_distinct_values_deduped_and_sorted(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Beta"),
            _entry(3, "Detail", "orders", "caption", "Alpha"),
            _entry(4, "Detail", "cart", "caption", "Beta"),
        ]
    )
    assert panel.distinct_values(_VALUE_COLUMN) == ["Alpha", "Beta"]


def test_distinct_values_uses_source_not_filtered_view(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    # Filter the view down to one row...
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home"})
    # ...distinct values still reflect the full source model.
    assert panel.distinct_values(_VALUE_COLUMN) == ["Cart", "Home", "Orders"]


# -- header filter popup ----------------------------------------------------


def test_popup_builds_checkable_item_per_distinct_value(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    labels = popup.item_labels()
    assert labels == ["Cart", "Home", "Orders"]
    # All checked initially.
    assert all(popup.is_checked(i) for i in range(len(labels)))


def test_popup_clear_then_apply_hides_all(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    popup.clear_all()
    popup.apply_filter()
    assert _visible_value_column(panel) == []


def test_popup_select_all_then_apply_clears_filter(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    # Start with an active filter.
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home"})
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    popup.select_all()
    popup.apply_filter()
    assert sorted(_visible_value_column(panel)) == ["Cart", "Home", "Orders"]


def test_popup_apply_subset_filters_to_checked(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    # Uncheck "Orders" (index 2 in sorted order Cart/Home/Orders).
    labels = popup.item_labels()
    popup.set_checked(labels.index("Orders"), False)
    popup.apply_filter()
    assert sorted(_visible_value_column(panel)) == ["Cart", "Home"]


def test_popup_reflects_existing_filter_state(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home", "Cart"})
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    labels = popup.item_labels()
    checked = {labels[i] for i in range(len(labels)) if popup.is_checked(i)}
    assert checked == {"Home", "Cart"}


# -- active-filter header indicator -----------------------------------------


def test_header_indicator_appears_and_disappears(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    model = panel._model

    def header(col):
        return model.headerData(
            col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
        )

    assert header(_VALUE_COLUMN) == "Value"
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home"})
    assert header(_VALUE_COLUMN) == "Value ▾"
    # Full select-all (all distinct values) is treated as no filter -> None.
    panel._proxy.set_value_filter(_VALUE_COLUMN, None)
    assert header(_VALUE_COLUMN) == "Value"


def test_header_indicator_only_on_filtered_column(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    model = panel._model
    panel._proxy.set_value_filter(_ATTRIBUTE_COLUMN, {"caption"})

    def header(col):
        return model.headerData(
            col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
        )

    assert header(_ATTRIBUTE_COLUMN) == "Attribute ▾"
    assert header(_VALUE_COLUMN) == "Value"
