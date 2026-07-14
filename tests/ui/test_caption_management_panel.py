import pytest
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


def test_inline_filter_row_removed(qtbot):
    # Phase 4 removed the per-column inline QLineEdit filter row (superseded by
    # header value filters + the shared find/filter modal).
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    assert not hasattr(panel, "_filter_fields")
    assert not hasattr(panel, "_filter_row")


def test_find_filter_matches_any_cell(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
            _entry(4, "Detail", "orders", "shortCaption", "Ord"),
        ]
    )
    # Whole-row find filter, case-insensitive "ord": matches the two rows
    # whose anchor/value contain it.
    panel.apply_find_filter("ord", "normal", False)
    assert sorted(_visible_value_column(panel)) == ["Ord", "Orders"]


def test_find_filter_regex_mode(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "shortCaption", "Ord"),
        ]
    )
    panel.apply_find_filter(r"^Ord$", "regular", True)
    assert _visible_value_column(panel) == ["Ord"]


def test_empty_find_filter_shows_all_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "Home"),
            _entry(3, "Detail", "orders", "caption", "Orders"),
        ]
    )
    panel.apply_find_filter("home", "normal", False)
    panel.apply_find_filter("", "normal", False)
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
    # Find filter keeps rows matching "order" (any cell); value filter keeps
    # only "Orders". Intersection is just "Orders".
    panel._proxy.set_regex_filter("order", "normal", False)
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


# -- Phase 4: shared find / filter / replace on the panel -------------------


def _replace_entries():
    return [
        _entry(2, "Page", "home", "caption", "Home Page"),
        _entry(3, "Detail", "orders", "caption", "Orders Page"),
        _entry(4, "Detail", "cart", "caption", "Cart"),
    ]


def test_replace_all_global_writes_new_value_on_all_matches(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    count = panel.replace_all_find("Page", "Screen", "normal", True, in_selection=False)
    assert count == 2
    assert panel._model.new_value_at(0) == "Home Screen"
    assert panel._model.new_value_at(1) == "Orders Screen"
    assert panel._model.new_value_at(2) == ""  # "Cart" has no match -> untouched


def test_replace_all_in_selection_only_touches_visible_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    # Filter to rows matching "Home" -> only the first row is visible.
    panel.apply_find_filter("Home", "normal", False)
    count = panel.replace_all_find("Page", "Screen", "normal", True, in_selection=True)
    assert count == 1
    assert panel._model.new_value_at(0) == "Home Screen"
    assert panel._model.new_value_at(1) == ""  # filtered out -> untouched
    assert panel._model.new_value_at(2) == ""


def test_replace_all_regex_capture_group(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries([_entry(2, "Page", "p", "caption", "John Smith")])
    count = panel.replace_all_find(
        r"(\w+) (\w+)", r"\2 \1", "regular", True, in_selection=False
    )
    assert count == 1
    assert panel._model.new_value_at(0) == "Smith John"


def test_apply_find_filter_invalid_regex_raises(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    with pytest.raises(ValueError):
        panel.apply_find_filter("(", "regular", True)


def test_current_filter_pattern_reflects_active_filter(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Page", "normal", False)
    assert panel.current_filter_pattern() == "Page"


def test_find_filter_ands_with_value_filter(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Page", "normal", False)  # rows 0,1
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Orders Page"})  # row 1
    assert _visible_value_column(panel) == ["Orders Page"]


# -- Phase 5: bulk transform -------------------------------------------------


def test_bulk_transform_seeds_from_value_when_new_value_empty(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries([_entry(2, "Page", "home", "caption", "home page")])
    _select_source_rows(panel, [0])
    panel.bulk_transform_selection("title")
    assert panel._model.new_value_at(0) == "Home Page"
    # marked changed, Value untouched
    assert panel._model.index(0, _CHANGED_COLUMN).data() == "*"
    assert panel._model.index(0, _VALUE_COLUMN).data() == "home page"


def test_bulk_transform_seeds_from_new_value_when_set(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries([_entry(2, "Page", "home", "caption", "original")])
    panel._model.set_new_value(0, "edited value")
    _select_source_rows(panel, [0])
    panel.bulk_transform_selection("upper")
    assert panel._model.new_value_at(0) == "EDITED VALUE"
    assert panel._model.index(0, _VALUE_COLUMN).data() == "original"


def test_bulk_transform_applies_to_all_selected(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "a", "caption", "one"),
            _entry(3, "Page", "b", "caption", "two"),
            _entry(4, "Page", "c", "caption", "three"),
        ]
    )
    _select_source_rows(panel, [0, 2])
    panel.bulk_transform_selection("upper")
    assert panel._model.new_value_at(0) == "ONE"
    assert panel._model.new_value_at(1) == ""  # unselected untouched
    assert panel._model.new_value_at(2) == "THREE"


def test_bulk_transform_humanize_fills_empty_from_anchor_style_value(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries([_entry(2, "ColumnPresentation", "wbs_id", "caption", "wbs_id")])
    _select_source_rows(panel, [0])
    panel.bulk_transform_selection("humanize")
    assert panel._model.new_value_at(0) == "Wbs"


# -- Phase 5: unify ----------------------------------------------------------


def _unify_entries():
    # Three rows share (anchor="wbs", attribute="caption") with divergent
    # values; a fourth is a different group.
    return [
        _entry(2, "ColumnPresentation", "wbs", "caption", "WBS ID"),
        _entry(3, "ColumnPresentation", "wbs", "caption", "Wbs Id"),
        _entry(4, "ColumnPresentation", "wbs", "caption", "wbs"),
        _entry(5, "ColumnPresentation", "cost", "caption", "Cost"),
    ]


def test_unify_sets_divergent_siblings_only(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries())
    panel.unify_from_row(0)  # target = row 0's Value "WBS ID"
    assert panel._model.new_value_at(0) == ""  # source untouched
    assert panel._model.new_value_at(1) == "WBS ID"
    assert panel._model.new_value_at(2) == "WBS ID"
    assert panel._model.new_value_at(3) == ""  # other group untouched


def test_unify_leaves_already_matching_untouched(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    entries = [
        _entry(2, "ColumnPresentation", "wbs", "caption", "WBS"),
        _entry(3, "ColumnPresentation", "wbs", "caption", "WBS"),  # already matches
        _entry(4, "ColumnPresentation", "wbs", "caption", "other"),
    ]
    panel.load_entries(entries)
    panel.unify_from_row(0)
    assert panel._model.new_value_at(0) == ""
    assert panel._model.new_value_at(1) == ""  # already matched -> untouched
    assert panel._model.new_value_at(2) == "WBS"


def test_unify_target_uses_new_value_when_set(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries())
    panel._model.set_new_value(0, "Canonical")
    panel.unify_from_row(0)
    assert panel._model.new_value_at(1) == "Canonical"
    assert panel._model.new_value_at(2) == "Canonical"
    assert panel._model.new_value_at(3) == ""


def test_unify_current_uses_current_row(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries())
    _select_source_rows(panel, [0])
    panel.unify_current()
    assert panel._model.new_value_at(1) == "WBS ID"
    assert panel._model.new_value_at(2) == "WBS ID"
