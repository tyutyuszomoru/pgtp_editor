import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence

from pgtp_editor.ui.caption_scan import CaptionEntry
from pgtp_editor.ui.caption_management_panel import (
    CaptionFindReplaceBar,
    CaptionManagementPanel,
    NULL_SENTINEL,
    _CHANGED_BACKGROUND,
    _CHANGED_FOREGROUND,
    _INCONSISTENT_BACKGROUND,
    _INCONSISTENT_FOREGROUND,
    _FILTER_HEADER_FOREGROUND,
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


def _foreground(panel, row):
    return panel._model.index(row, 0).data(Qt.ItemDataRole.ForegroundRole)


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


def test_changed_row_gets_changed_foreground(qtbot):
    """BUG-005: a matching foreground must accompany the changed tint so its
    text stays readable against the dark background under any theme."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    _set_new_value(panel, 0, "Homepage")
    assert _foreground(panel, 0) == _CHANGED_FOREGROUND


def test_inconsistent_row_gets_inconsistent_foreground(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    assert _foreground(panel, 0) == _INCONSISTENT_FOREGROUND
    assert _foreground(panel, 1) == _INCONSISTENT_FOREGROUND


def test_changed_foreground_beats_inconsistency_foreground(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    _set_new_value(panel, 0, "AccountX")
    assert _foreground(panel, 0) == _CHANGED_FOREGROUND
    assert _foreground(panel, 1) == _INCONSISTENT_FOREGROUND


def test_consistent_unchanged_row_has_no_foreground(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Account"),
        ]
    )
    assert _foreground(panel, 0) is None
    assert _foreground(panel, 1) is None


def test_group_of_three_plus_inconsistent_rows_all_get_foreground(qtbot):
    """BUG-005: _recompute_inconsistency's group-of-3+ case (not just pairs)
    must still resolve the matching foreground for every divergent member of
    the group."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries())  # 3-row "wbs" group + 1-row "cost" group
    assert _foreground(panel, 0) == _INCONSISTENT_FOREGROUND
    assert _foreground(panel, 1) == _INCONSISTENT_FOREGROUND
    assert _foreground(panel, 2) == _INCONSISTENT_FOREGROUND
    # The unrelated single-row "cost" group is consistent by itself.
    assert _foreground(panel, 3) is None


def test_unify_reverts_foreground_to_none_once_group_becomes_consistent(qtbot):
    """BUG-005 + BUG-003-adjacent regression: a row that WAS inconsistent-
    tinted must have its foreground revert to None (not linger as the warm
    tint) once its group becomes fully consistent -- exercised through the
    batched set_new_values path (unify_from_row), matching how the app's
    Unify action actually mutates rows."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries())
    assert _foreground(panel, 1) == _INCONSISTENT_FOREGROUND
    assert _foreground(panel, 2) == _INCONSISTENT_FOREGROUND

    panel.unify_from_row(0)  # unifies rows 1 and 2 onto row 0's value "WBS ID"

    # Rows 1/2 now carry a non-empty New Value equal to the group's target, so
    # the whole "wbs" group's effective values agree -> no longer inconsistent.
    # Changed rows get the changed tint, not None -- row 0 (the unify source)
    # was never written and has no New Value, so it must now show NO tint at
    # all (neither warm nor cool) since its group is consistent again.
    assert _foreground(panel, 0) is None
    assert _background(panel, 0) is None
    assert _foreground(panel, 1) == _CHANGED_FOREGROUND
    assert _foreground(panel, 2) == _CHANGED_FOREGROUND


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
    # BUG-028: the find filter is represented in the active-filter banner, with
    # its whole-row scope stated explicitly.
    assert panel._filter_banner.isVisibleTo(panel)
    banner = panel._filter_banner_label.text()
    assert 'Find "ord"' in banner
    assert "all columns" in banner
    assert "showing 2 of 3 rows" in banner
    # Getters mirroring find_pattern() (BUG-028).
    assert panel._proxy.find_pattern() == "ord"
    assert panel._proxy.find_mode() == "normal"
    assert panel._proxy.find_case() is False


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
    # BUG-028: non-default mode/case are named in the banner descriptor.
    assert panel._filter_banner.isVisibleTo(panel)
    banner = panel._filter_banner_label.text()
    assert 'Find "^Ord$"' in banner
    assert "regex" in banner
    assert "case-sensitive" in banner
    assert "all columns" in banner
    assert panel._proxy.find_mode() == "regular"
    assert panel._proxy.find_case() is True


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
    assert panel._filter_banner.isVisibleTo(panel)
    panel.apply_find_filter("", "normal", False)
    assert sorted(_visible_value_column(panel)) == ["Home", "Orders"]
    # BUG-028: with no preset predicate active, clearing the pattern hides the
    # banner again.
    assert panel._filter_banner.isHidden()


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


# -- header filter popup search box (Excel-style) ---------------------------


def _hidden_states(popup):
    return [popup._list.item(i).isHidden() for i in range(popup._list.count())]


def test_popup_search_hides_nonmatching_and_checks_matches(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    labels = popup.item_labels()  # ["Cart", "Home", "Orders"]

    popup._on_search("art")  # substring of "Cart" only

    cart = labels.index("Cart")
    home = labels.index("Home")
    orders = labels.index("Orders")
    # Matching row visible, non-matching hidden.
    assert popup._list.item(cart).isHidden() is False
    assert popup._list.item(home).isHidden() is True
    assert popup._list.item(orders).isHidden() is True
    # Non-empty search checks matches, unchecks non-matches.
    assert popup.is_checked(cart) is True
    assert popup.is_checked(home) is False
    assert popup.is_checked(orders) is False


def test_popup_search_then_checked_values_and_apply(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    captured = []
    popup = _open_popup_capturing(panel, captured)
    qtbot.addWidget(popup)

    popup._on_search("art")

    assert popup.checked_values() == {"Cart"}
    popup.apply_filter()
    assert captured == [(_VALUE_COLUMN, {"Cart"})]


def _open_popup_capturing(panel, captured):
    from pgtp_editor.ui.caption_management_panel import _HeaderFilterPopup

    return _HeaderFilterPopup(
        _VALUE_COLUMN,
        panel.cascaded_distinct_values(_VALUE_COLUMN),
        panel._proxy.value_filter(_VALUE_COLUMN),
        on_apply=lambda col, allowed: captured.append((col, allowed)),
    )


def test_popup_empty_search_shows_all_and_preserves_checks(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    labels = popup.item_labels()
    orders = labels.index("Orders")

    # Manual uncheck before any search.
    popup.set_checked(orders, False)
    # Type then clear.
    popup._on_search("art")
    popup._on_search("")

    # All rows revealed again.
    assert _hidden_states(popup) == [False, False, False]
    # Empty search leaves check states unchanged (manual uncheck preserved).
    assert popup.is_checked(orders) is False


def test_popup_select_all_under_search_affects_visible_only(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    labels = popup.item_labels()

    popup._on_search("o")  # matches "Home" and "Orders", not "Cart"
    popup.clear_all()  # clears only visible (Home, Orders)
    popup.select_all()  # selects only visible (Home, Orders)

    assert popup.is_checked(labels.index("Home")) is True
    assert popup.is_checked(labels.index("Orders")) is True
    # Hidden "Cart" untouched by visible-only clear/select.
    assert popup.is_checked(labels.index("Cart")) is False


def test_popup_clear_all_under_search_affects_visible_only(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    labels = popup.item_labels()

    popup._on_search("o")  # visible: Home, Orders; hidden+unchecked: Cart
    popup.clear_all()

    assert popup.is_checked(labels.index("Home")) is False
    assert popup.is_checked(labels.index("Orders")) is False


def test_popup_search_full_flow_filters_proxy(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "home", "caption", "AI Home"),
            _entry(3, "Detail", "orders", "caption", "AI Orders"),
            _entry(4, "Detail", "cart", "caption", "Cart"),
        ]
    )
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)

    popup._on_search("AI")
    popup.apply_filter()

    assert sorted(_visible_value_column(panel)) == ["AI Home", "AI Orders"]


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
    assert header(_VALUE_COLUMN) == "Value ▼"
    # Full select-all (all distinct values) is treated as no filter -> None.
    panel._proxy.set_value_filter(_VALUE_COLUMN, None)
    assert header(_VALUE_COLUMN) == "Value"


def test_filtered_column_header_is_bold_and_colored(qtbot):
    # Issue #6: a filtered column's header must be unmistakable — bold FontRole
    # AND a distinct foreground color AND a clear ▼ marker.
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_value_filter_entries())
    model = panel._model

    def role(col, data_role):
        return model.headerData(col, Qt.Orientation.Horizontal, data_role)

    # Unfiltered: no bold, no special foreground.
    assert role(_VALUE_COLUMN, Qt.ItemDataRole.FontRole) is None
    assert role(_VALUE_COLUMN, Qt.ItemDataRole.ForegroundRole) is None

    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home"})

    font = role(_VALUE_COLUMN, Qt.ItemDataRole.FontRole)
    assert font is not None and font.bold()
    assert role(_VALUE_COLUMN, Qt.ItemDataRole.ForegroundRole) == _FILTER_HEADER_FOREGROUND
    assert role(_VALUE_COLUMN, Qt.ItemDataRole.DisplayRole) == "Value ▼"
    # An unfiltered sibling stays plain.
    assert role(_ATTRIBUTE_COLUMN, Qt.ItemDataRole.FontRole) is None


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

    assert header(_ATTRIBUTE_COLUMN) == "Attribute ▼"
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
    # BUG-028: the banner must not advertise a filter that was rejected.
    assert panel._filter_banner.isHidden()


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


def test_bulk_transform_humanize_seeds_from_field_name_not_caption(qtbot):
    # Humanize derives a caption from the fieldName (the anchor), NOT from the
    # existing caption value -- that's its whole point (fill a caption from the
    # column's field name). Anchor differs from Value here to prove it.
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [_entry(2, "ColumnPresentation", "physical_location_id", "caption", "Old Caption")]
    )
    _select_source_rows(panel, [0])
    panel.bulk_transform_selection("humanize")
    assert panel._model.new_value_at(0) == "Physical Location"


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


# -- BUG-023: Unify scope prompt when a filter is active --------------------


def _unify_entries_with_breadcrumb():
    """Like _unify_entries but with a distinguishing Breadcrumb per row so a
    value filter on Breadcrumb can narrow to a strict subset of the
    "wbs"/"caption" sibling group (rows 0-2), leaving row 1 out of the
    filtered view while row 0 (source) and row 2 stay in."""
    return [
        _entry(2, "ColumnPresentation", "wbs", "caption", "WBS ID", breadcrumb="in"),
        _entry(3, "ColumnPresentation", "wbs", "caption", "Wbs Id", breadcrumb="out"),
        _entry(4, "ColumnPresentation", "wbs", "caption", "wbs", breadcrumb="in"),
        _entry(5, "ColumnPresentation", "cost", "caption", "Cost", breadcrumb="in"),
    ]


def test_unify_current_no_prompt_when_no_filter_active(qtbot, monkeypatch):
    """No filter active -> unify_current runs project-wide with no prompt at
    all (unchanged behavior); _confirm_unify_scope must not even be called."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries())
    _select_source_rows(panel, [0])

    def _boom():
        raise AssertionError("_confirm_unify_scope should not be called")

    monkeypatch.setattr(panel, "_confirm_unify_scope", _boom)
    panel.unify_current()
    assert panel._model.new_value_at(1) == "WBS ID"
    assert panel._model.new_value_at(2) == "WBS ID"


def test_unify_current_prompts_and_applies_filtered_scope(qtbot, monkeypatch):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries_with_breadcrumb())
    panel._proxy.set_value_filter(_BREADCRUMB_COLUMN, {"in"})
    _select_source_rows(panel, [0])

    monkeypatch.setattr(panel, "_confirm_unify_scope", lambda: "filtered")
    panel.unify_current()
    # Row 2 ("in", visible) is unified; row 1 ("out", filtered out) is not.
    assert panel._model.new_value_at(2) == "WBS ID"
    assert panel._model.new_value_at(1) == ""


def test_unify_current_prompts_and_applies_project_scope(qtbot, monkeypatch):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries_with_breadcrumb())
    panel._proxy.set_value_filter(_BREADCRUMB_COLUMN, {"in"})
    _select_source_rows(panel, [0])

    monkeypatch.setattr(panel, "_confirm_unify_scope", lambda: "project")
    panel.unify_current()
    # Entire project: both siblings unified, including the filtered-out row.
    assert panel._model.new_value_at(1) == "WBS ID"
    assert panel._model.new_value_at(2) == "WBS ID"


def test_unify_current_prompts_and_cancel_applies_nothing(qtbot, monkeypatch):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries_with_breadcrumb())
    panel._proxy.set_value_filter(_BREADCRUMB_COLUMN, {"in"})
    _select_source_rows(panel, [0])

    monkeypatch.setattr(panel, "_confirm_unify_scope", lambda: "cancel")
    panel.unify_current()
    assert panel._model.new_value_at(1) == ""
    assert panel._model.new_value_at(2) == ""


def test_unify_from_row_restrict_to_limits_eligible_siblings(qtbot):
    """Direct unify_from_row API: restrict_to limits which sibling rows are
    eligible, independent of the prompt/panel plumbing."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_unify_entries())
    # Only rows 0 and 2 are eligible; row 1 is excluded even though it shares
    # the (anchor, attribute) key and differs from the target.
    panel.unify_from_row(0, restrict_to=[0, 2])
    assert panel._model.new_value_at(1) == ""
    assert panel._model.new_value_at(2) == "WBS ID"


# -- inconsistency from EFFECTIVE values ------------------------------------


def test_inconsistency_uses_effective_value_not_scanned_value(qtbot):
    # Two siblings with divergent scanned Values are inconsistent. After setting
    # the New Value of one to match the other's effective value, the group is
    # consistent and NEITHER row is flagged inconsistent.
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(2, "Page", "acct", "caption", "Account"),
            _entry(9, "Detail", "acct", "caption", "Accounts"),
        ]
    )
    model = panel._model
    assert model._is_inconsistent(0) is True
    assert model._is_inconsistent(1) is True
    # Make row 1's effective value match row 0's ("Account").
    panel._model.set_new_value(1, "Account")
    # Group now agrees on the effective value -> neither is inconsistent.
    assert model._is_inconsistent(0) is False
    assert model._is_inconsistent(1) is False
    # The edited row still shows the changed tint (changed wins); the unedited
    # sibling no longer shows the warm inconsistency tint.
    assert _background(panel, 1) == _CHANGED_BACKGROUND
    assert _background(panel, 0) is None


def test_set_new_values_emits_data_changed_once(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    emissions = []
    panel._model.dataChanged.connect(
        lambda tl, br, roles: emissions.append((tl, br, roles))
    )
    panel._model.set_new_values({0: "A", 2: "B"})
    assert len(emissions) == 1
    tl, br, roles = emissions[0]
    # Spans the whole grid.
    assert (tl.row(), tl.column()) == (0, _CHANGED_COLUMN)
    assert (br.row(), br.column()) == (
        panel._model.rowCount() - 1,
        panel._model.columnCount() - 1,
    )
    assert panel._model.new_value_at(0) == "A"
    assert panel._model.new_value_at(2) == "B"
    # BUG-005: ForegroundRole must ride alongside BackgroundRole so a row
    # transitioning into/out of a tinted state repaints its text color too.
    assert Qt.ItemDataRole.ForegroundRole in roles
    assert Qt.ItemDataRole.BackgroundRole in roles


def test_single_edit_data_changed_includes_foreground_role(qtbot):
    """Same BUG-005 requirement, but for the singular setData/_emit_row_changed
    path (_set_new_value) rather than the batched set_new_values path above."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_sample_entries())
    emissions = []
    panel._model.dataChanged.connect(
        lambda tl, br, roles: emissions.append(roles)
    )
    _set_new_value(panel, 0, "Homepage")
    background_roles = [roles for roles in emissions if Qt.ItemDataRole.BackgroundRole in roles]
    assert background_roles  # the whole-grid background repaint emission happened
    assert Qt.ItemDataRole.ForegroundRole in background_roles[0]


# -- sort-active proxy->source mapping under bulk ops -----------------------


def test_paste_multiline_under_active_sort_maps_to_source_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    # Source order by line 10, 2, 3; sorting Line ascending reorders the VIEW to
    # source rows 1, 2, 0. Selecting the first two visible rows must paste onto
    # the correct SOURCE rows, in visual order.
    panel.load_entries(
        [
            _entry(10, "Page", "a", "caption", "ten"),
            _entry(2, "Page", "b", "caption", "two"),
            _entry(3, "Page", "c", "caption", "three"),
        ]
    )
    panel._proxy.sort(_LINE_COLUMN, Qt.SortOrder.AscendingOrder)
    # Visible order is now source rows [1 (line 2), 2 (line 3), 0 (line 10)].
    # Select the first two visible rows (source rows 1 and 2).
    _select_source_rows(panel, [1, 2])
    QGuiApplication.clipboard().setText("First\nSecond")
    panel.paste_into_new_value()
    # Line i -> visual row i: source row 1 gets "First", source row 2 "Second".
    assert panel._model.new_value_at(1) == "First"
    assert panel._model.new_value_at(2) == "Second"
    assert panel._model.new_value_at(0) == ""  # visible last, unselected


def test_replace_all_in_selection_under_active_sort_maps_to_source(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(
        [
            _entry(10, "Page", "a", "caption", "ten Page"),
            _entry(2, "Page", "b", "caption", "two Page"),
            _entry(3, "Page", "c", "caption", "three Page"),
        ]
    )
    # Sort descending by Line, then filter to two rows; replace within scope.
    panel._proxy.sort(_LINE_COLUMN, Qt.SortOrder.DescendingOrder)
    panel.apply_find_filter("two Page", "normal", False)  # only source row 1
    count = panel.replace_all_find(
        "Page", "Screen", "normal", True, in_selection=True
    )
    assert count == 1
    # The replacement landed on the correct SOURCE row (row 1), not a proxy row.
    assert panel._model.new_value_at(1) == "two Screen"
    assert panel._model.new_value_at(0) == ""
    assert panel._model.new_value_at(2) == ""


# -- Issue #4: row-click toggles the value-filter checkbox ------------------


def _breadcrumb_anchor_entries():
    return [
        _entry(2, "Page", "home", "caption", "Home", breadcrumb="A → x"),
        _entry(3, "Detail", "orders", "caption", "Orders", breadcrumb="A → y"),
        _entry(4, "Detail", "cart", "caption", "Cart", breadcrumb="B → z"),
    ]


def _visible_column(panel, column):
    proxy = panel._proxy
    return [
        proxy.index(r, column).data(Qt.ItemDataRole.DisplayRole)
        for r in range(proxy.rowCount())
    ]


def test_row_click_toggles_checkbox_flow_breadcrumb(qtbot):
    # Issue #4 full flow: open popup -> clear all -> click ONE row (via the
    # itemClicked handler) -> apply -> exactly the matching rows are visible.
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_breadcrumb_anchor_entries())
    popup = panel.open_header_filter(_BREADCRUMB_COLUMN)
    qtbot.addWidget(popup)
    popup.clear_all()
    labels = popup.item_labels()
    target = labels.index("A → y")
    # Simulate clicking the row (not just the tiny indicator): drive the handler
    # the itemClicked signal is wired to.
    popup._toggle_item(popup._list.item(target))
    assert popup.is_checked(target)
    popup.apply_filter()
    assert _visible_column(panel, _BREADCRUMB_COLUMN) == ["A → y"]


def test_row_click_toggles_checkbox_flow_anchor(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_breadcrumb_anchor_entries())
    popup = panel.open_header_filter(_ANCHOR_COLUMN)
    qtbot.addWidget(popup)
    popup.clear_all()
    labels = popup.item_labels()
    target = labels.index("cart")
    popup._toggle_item(popup._list.item(target))
    popup.apply_filter()
    assert _visible_column(panel, _ANCHOR_COLUMN) == ["cart"]


def test_row_click_toggle_is_reversible(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_breadcrumb_anchor_entries())
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    item = popup._list.item(0)
    assert popup.is_checked(0)  # checked by default
    popup._toggle_item(item)
    assert not popup.is_checked(0)
    popup._toggle_item(item)
    assert popup.is_checked(0)


# -- Issue #5: cascading distinct values ------------------------------------


def test_cascaded_distinct_values_reflects_other_active_filters(qtbot):
    # Filter column A (Breadcrumb) to one value; the popup for column B (Value)
    # then lists only B-values co-occurring with that A value.
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_breadcrumb_anchor_entries())
    # A = Breadcrumb filtered to "A → x" and "A → y" (both start with "A").
    panel._proxy.set_value_filter(_BREADCRUMB_COLUMN, {"A → x", "A → y"})
    # Cascaded distinct Values: only Home and Orders co-occur; Cart is excluded.
    assert panel.cascaded_distinct_values(_VALUE_COLUMN) == ["Home", "Orders"]


def test_cascaded_distinct_values_excludes_own_filter(qtbot):
    # The target column's OWN filter must NOT restrict its own listed values,
    # so the user can still see and re-check values they filtered out.
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_breadcrumb_anchor_entries())
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Home"})
    # All three Values still appear (own filter ignored).
    assert panel.cascaded_distinct_values(_VALUE_COLUMN) == ["Cart", "Home", "Orders"]


def test_cascaded_distinct_values_honors_find_filter(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_breadcrumb_anchor_entries())
    panel._proxy.set_regex_filter("Orders", "normal", False)
    assert panel.cascaded_distinct_values(_VALUE_COLUMN) == ["Orders"]


def test_open_header_filter_uses_cascaded_values(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_breadcrumb_anchor_entries())
    panel._proxy.set_value_filter(_BREADCRUMB_COLUMN, {"B → z"})
    popup = panel.open_header_filter(_VALUE_COLUMN)
    qtbot.addWidget(popup)
    # Only "Cart" co-occurs with breadcrumb "B → z".
    assert popup.item_labels() == ["Cart"]


# -- Issue #2: clear exit-caption-mode button -------------------------------


def test_exit_button_labelled_and_wired(qtbot):
    calls = []
    panel = CaptionManagementPanel(on_close=lambda: calls.append(True))
    qtbot.addWidget(panel)
    assert panel._close_button.text() == "Exit Caption Mode"
    panel._close_button.click()
    assert calls == [True]


# -- FQ-017: Ctrl+F / Ctrl+R FOCUS the permanent bar ------------------------


def test_panel_owns_panel_scoped_focus_shortcuts_for_ctrl_f_and_ctrl_r(qtbot):
    """FQ-017: the window-scoped, mode-gated MainWindow shortcuts that opened
    the deleted Caption Filter modal are gone. The panel owns Ctrl+F / Ctrl+R
    itself now, scoped to the panel and its children (so they are inert
    whenever the caption grid is not the focused surface) and bound to FOCUS,
    never to show anything."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    assert panel._focus_find_shortcut.key() == QKeySequence("Ctrl+F")
    assert panel._focus_replace_shortcut.key() == QKeySequence("Ctrl+R")
    for shortcut in (panel._focus_find_shortcut, panel._focus_replace_shortcut):
        assert shortcut.context() == Qt.ShortcutContext.WidgetWithChildrenShortcut
        assert shortcut.isEnabled()
        assert shortcut.parent() is panel


def test_ctrl_f_focuses_the_find_field_and_ctrl_r_the_replace_field(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    panel.focus_find_replace_bar()
    assert panel.focusWidget() is bar.find_field
    panel.focus_replace_field()
    assert panel.focusWidget() is bar.replace_field
    # Neither gesture ever hid or showed the bar.
    assert bar.isHidden() is False


# -- Phase C.2: preset-filter entry (row predicate) -------------------------


def _ctx_entry(line, tag, anchor, attribute, value, table_name="", field_name="", in_detail=False):
    return CaptionEntry(
        line=line,
        element_tag=tag,
        anchor=anchor,
        attribute=attribute,
        value=value,
        table_name=table_name,
        field_name=field_name,
        in_detail=in_detail,
    )


def _context_entries():
    return [
        # top-level page on pr.equip
        _ctx_entry(2, "Page", "equip", "caption", "Equipment", table_name="pr.equip"),
        # a column on the top-level page
        _ctx_entry(4, "ColumnPresentation", "wbs_id", "caption", "WBS",
                   table_name="pr.equip", field_name="wbs_id"),
        # a detail on pr.att
        _ctx_entry(6, "Detail", "att", "caption", "Attachments", table_name="pr.att"),
        # a column inside a detail whose owning table is pr.att
        _ctx_entry(9, "ColumnPresentation", "att_name", "caption", "Name",
                   table_name="pr.att", field_name="att_name", in_detail=True),
        # unrelated page on another table
        _ctx_entry(12, "Page", "other", "caption", "Other", table_name="pr.other"),
    ]


def test_set_row_predicate_filters_by_table(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel._proxy.set_row_predicate(lambda e: e.table_name == "pr.equip")
    assert sorted(_visible_value_column(panel)) == ["Equipment", "WBS"]


def test_set_row_predicate_none_clears(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel._proxy.set_row_predicate(lambda e: e.table_name == "pr.equip")
    assert len(_visible_value_column(panel)) == 2
    panel._proxy.set_row_predicate(None)
    assert len(_visible_value_column(panel)) == 5


def test_set_row_predicate_accepts_optional_label(qtbot):
    """BUG-020: set_row_predicate gains an optional label, stored alongside
    the predicate; the old single-arg call sites keep working (label
    defaults to "")."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel._proxy.set_row_predicate(lambda e: e.table_name == "pr.equip")
    assert panel._proxy.row_predicate_label() == ""
    panel._proxy.set_row_predicate(
        lambda e: e.table_name == "pr.equip", "Table = pr.equip"
    )
    assert panel._proxy.row_predicate_label() == "Table = pr.equip"
    panel._proxy.set_row_predicate(None)
    assert panel._proxy.row_predicate_label() == ""


def test_row_predicate_ands_with_value_and_find_filters(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    # Predicate limits to pr.equip (Equipment, WBS); value filter to WBS.
    panel._proxy.set_row_predicate(lambda e: e.table_name == "pr.equip")
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"WBS"})
    assert _visible_value_column(panel) == ["WBS"]
    # A find filter that excludes WBS -> empty.
    panel._proxy.set_regex_filter("Equipment", "normal", False)
    assert _visible_value_column(panel) == []


def test_entry_at_accessor(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    entries = _context_entries()
    panel.load_entries(entries)
    assert panel._model.entry_at(0).table_name == "pr.equip"
    assert panel._model.entry_at(1).field_name == "wbs_id"


def test_filter_to_table_shows_only_that_table(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel.filter_to_table("pr.equip")
    assert sorted(_visible_value_column(panel)) == ["Equipment", "WBS"]
    # BUG-020: the preset filter must be visibly represented via the banner.
    assert panel._filter_banner.isVisibleTo(panel)
    assert "Table = pr.equip" in panel._filter_banner_label.text()
    assert "showing 2 of 5 rows" in panel._filter_banner_label.text()


def test_filter_to_table_details_shows_only_detail_rows(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel.filter_to_table_details("pr.att")
    # Only the in-detail column (Name) matches: table pr.att AND in_detail.
    # The <Detail> caption row itself (Attachments) is NOT in_detail.
    assert _visible_value_column(panel) == ["Name"]
    assert panel._filter_banner.isVisibleTo(panel)
    assert "Table = pr.att" in panel._filter_banner_label.text()
    assert "showing 1 of 5 rows" in panel._filter_banner_label.text()


def test_filter_to_field_shows_and_selects_matching_row(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    entries = _context_entries()
    panel.load_entries(entries)
    panel.filter_to_field("wbs_id")
    assert _visible_value_column(panel) == ["WBS"]
    # The matching row is selected.
    selected = panel._table.selectionModel().selectedRows()
    assert len(selected) == 1
    source_row = panel._proxy.mapToSource(selected[0]).row()
    assert panel._model.entry_at(source_row).field_name == "wbs_id"
    # BUG-020: banner reflects the field-level preset filter.
    assert panel._filter_banner.isVisibleTo(panel)
    assert "Field = wbs_id" in panel._filter_banner_label.text()
    assert "showing 1 of 5 rows" in panel._filter_banner_label.text()


def test_filter_to_field_with_table_builds_combined_banner_label(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel.filter_to_field("wbs_id", table_name="pr.equip")
    assert panel._filter_banner.isVisibleTo(panel)
    label = panel._filter_banner_label.text()
    assert "Field = wbs_id" in label
    assert "Table = pr.equip" in label


def test_banner_combines_preset_predicate_and_find_filter(qtbot):
    """BUG-028: with both a preset row predicate and a find filter active, the
    single banner shows both descriptors joined by the `·` separator, and the
    existing single clear path hides it."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel.filter_to_field("wbs_id", table_name="pr.equip")
    panel.apply_find_filter("WBS", "normal", False)
    assert panel._filter_banner.isVisibleTo(panel)
    label = panel._filter_banner_label.text()
    assert "Field = wbs_id" in label
    assert "Table = pr.equip" in label
    assert 'Find "WBS"' in label
    assert "all columns" in label
    assert "·" in label
    assert "showing 1 of 5 rows" in label
    panel.clear_all_filters()
    assert panel._filter_banner.isHidden()


def test_filter_to_field_selects_row_regardless_of_latched_shift_modifier(qtbot):
    """BUG-018: QTableView.selectRow reads the process-global keyboard
    modifiers and silently selects nothing if Shift happens to be latched
    from an unrelated prior action -- confirm the fix is modifier-independent."""
    from PySide6.QtTest import QTest

    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())

    QTest.keyClick(panel, Qt.Key.Key_A, Qt.KeyboardModifier.ShiftModifier)
    try:
        panel.filter_to_field("wbs_id")
        selected = panel._table.selectionModel().selectedRows()
        assert len(selected) == 1
        source_row = panel._proxy.mapToSource(selected[0]).row()
        assert panel._model.entry_at(source_row).field_name == "wbs_id"
    finally:
        QTest.keyClick(panel, Qt.Key.Key_Shift, Qt.KeyboardModifier.NoModifier)


# -- Phase C.3: clear all filters -------------------------------------------


def test_clear_all_filters_resets_everything(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel.apply_find_filter("Name", "normal", False)
    # BUG-028: the find filter alone already makes the banner visible, before
    # any preset predicate is set.
    assert panel._filter_banner.isVisibleTo(panel)
    assert 'Find "Name"' in panel._filter_banner_label.text()
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Name"})
    panel.filter_to_table("pr.att")
    # Sanity: everything narrows to one row.
    assert _visible_value_column(panel) == ["Name"]
    assert panel._filter_banner.isVisibleTo(panel)
    panel.clear_all_filters()
    # All rows visible again.
    assert len(_visible_value_column(panel)) == 5
    # Header indicators cleared.
    assert panel._proxy.filtered_columns() == set()
    assert panel._model._filtered_columns == set()
    assert panel._proxy.find_pattern() == ""
    # BUG-020: the active-filter banner hides and its label clears.
    assert panel._filter_banner.isHidden()
    assert panel._proxy.row_predicate_label() == ""


def test_clear_all_filters_in_context_menu_wired(qtbot, monkeypatch):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    # Capture the menu built by _show_context_menu without exec-ing it.
    captured = {}

    class _FakeMenu:
        def __init__(self, *a, **k):
            self._actions = []

        def addAction(self, label, cb=None):
            self._actions.append((label, cb))
            return (label, cb)

        def addSeparator(self):
            pass

        def addMenu(self, label):
            return _FakeMenu()

        def exec(self, *a, **k):
            captured["actions"] = self._actions

    monkeypatch.setattr(
        "pgtp_editor.ui.caption_management_panel.QMenu", _FakeMenu
    )
    panel._show_context_menu(panel._table.viewport().rect().center())
    labels = [label for label, _ in captured["actions"]]
    assert "Clear all filters" in labels
    # The wired callback is clear_all_filters.
    cb = dict(captured["actions"])["Clear all filters"]
    assert cb == panel.clear_all_filters


# -- BUG-028: find-filter banner descriptor, remaining qualifier cases ------


def test_find_banner_extended_mode_is_named(qtbot):
    """The third search mode gets its own qualifier word (`extended`), not the
    regex one — the banner must not misdescribe how the pattern is read."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "extended", False)
    banner = panel._filter_banner_label.text()
    assert 'Find "Home"' in banner
    assert "extended" in banner
    assert "regex" not in banner
    assert "case-sensitive" not in banner
    assert "all columns" in banner


def test_find_banner_omits_mode_for_default_normal_search(qtbot):
    """A plain case-insensitive Normal search stays terse: scope only."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "normal", False)
    banner = panel._filter_banner_label.text()
    assert 'Find "Home" (all columns)' in banner
    assert "regex" not in banner
    assert "extended" not in banner
    assert "case-sensitive" not in banner


def test_find_banner_names_case_sensitivity_without_naming_normal_mode(qtbot):
    """Mode and case are independent qualifiers: case-sensitive Normal names
    only the case flag."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "normal", True)
    banner = panel._filter_banner_label.text()
    assert 'Find "Home" (case-sensitive, all columns)' in banner
    assert "regex" not in banner
    assert "extended" not in banner


def test_header_value_filter_alone_does_not_show_the_banner(qtbot):
    """Header value filters are deliberately NOT represented in the banner —
    they carry their own per-column ▼ marker (BUG-020/028)."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel._proxy.set_value_filter(_VALUE_COLUMN, {"Cart"})
    assert panel._filter_banner.isHidden()


def test_rejected_regex_leaves_the_previous_banner_intact(qtbot):
    """BUG-028: `apply_find_filter` refreshes only after `set_regex_filter`
    returns normally, so a rejected pattern neither replaces nor clears the
    description of the filter that IS active."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "normal", False)
    before = panel._filter_banner_label.text()

    with pytest.raises(ValueError):
        panel.apply_find_filter("(", "regular", True)

    assert panel._filter_banner.isVisibleTo(panel)
    assert panel._filter_banner_label.text() == before
    assert panel._proxy.find_pattern() == "Home"


def test_clear_all_filters_keeps_mode_and_case_while_clearing_the_pattern(qtbot):
    """clear_all_filters clears the PATTERN through the public getters rather
    than resetting the user's mode/case choices (BUG-028 replaced the private
    `_find_mode`/`_find_case` reads here)."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "regular", True)
    panel.clear_all_filters()
    assert panel._proxy.find_pattern() == ""
    assert panel._proxy.find_mode() == "regular"
    assert panel._proxy.find_case() is True
    assert panel._filter_banner.isHidden()


def test_banner_stays_visible_for_preset_predicate_after_find_is_cleared(qtbot):
    """The banner hides only when NEITHER descriptor is present: clearing just
    the find pattern must leave the preset predicate's banner standing."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel.filter_to_table("pr.equip")
    panel.apply_find_filter("WBS", "normal", False)
    assert 'Find "WBS"' in panel._filter_banner_label.text()

    panel.apply_find_filter("", "normal", False)
    assert panel._filter_banner.isVisibleTo(panel)
    label = panel._filter_banner_label.text()
    assert "Table = pr.equip" in label
    assert "Find" not in label


def test_find_banner_row_counts_track_the_find_filter(qtbot):
    """The banner is refreshed AFTER the proxy is invalidated, so the counts
    describe the post-filter view."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Page", "normal", False)
    assert "showing 2 of 3 rows" in panel._filter_banner_label.text()
    panel.apply_find_filter("Cart", "normal", False)
    assert "showing 1 of 3 rows" in panel._filter_banner_label.text()


# ---------------------------------------------------------------------------
# The Caption grid's live Find/Replace bar (§13)
# ---------------------------------------------------------------------------


def _new_value_column(panel):
    """Every SOURCE row's New Value, in source order (the preview writes into
    source rows, so this sees rows the filter currently hides too)."""
    model = panel._model
    return [
        model.index(r, _NEW_VALUE_COLUMN).data(Qt.ItemDataRole.DisplayRole)
        for r in range(model.rowCount())
    ]


def test_bar_is_a_permanent_non_modal_child_widget(qtbot):
    """FQ-017: the bar is never hidden and has no show/close lifecycle, so the
    Caption Filter modal it duplicated could be deleted outright."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    bar = panel.find_replace_bar
    assert isinstance(bar, CaptionFindReplaceBar)
    assert bar.parent() is panel
    assert bar.isHidden() is False
    assert bar.is_active() is False
    # Not a dialog: there is nothing to exec().
    assert not hasattr(bar, "exec")
    # The show/hide lifecycle is gone, not merely unused.
    for gone in ("show_bar", "close_bar", "close_button"):
        assert not hasattr(bar, gone), gone


def test_bar_offers_the_three_real_search_modes(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    combo = panel.find_replace_bar.mode_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    modes = [combo.itemData(i) for i in range(combo.count())]
    assert labels == [
        "Normal (plain string)",
        "Extended (\\n \\t \\0 \\xNN)",
        "Regular expression",
    ]
    assert modes == ["normal", "extended", "regular"]
    assert panel.find_replace_bar.selected_mode() == "normal"


def test_live_replace_updates_proposals_as_the_pattern_is_typed(qtbot):
    """The headline behavior: the preview is LIVE — each keystroke rewrites the
    New Value column, and the previous keystroke's proposal is rolled back
    rather than accumulated. (Replace All exists too, but only to reach the
    project-wide scope and to commit; it is not what drives this.)"""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")

    bar.find_field.setText("P")
    assert _new_value_column(panel) == ["Home Screenage", "Orders Screenage", ""]

    # Typing one more character re-derives from the ORIGINAL values.
    bar.find_field.setText("Pa")
    assert _new_value_column(panel) == ["Home Screenge", "Orders Screenge", ""]

    bar.find_field.setText("Page")
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]

    # Editing the replacement is just as live.
    bar.replace_field.setText("View")
    assert _new_value_column(panel) == ["Home View", "Orders View", ""]

    # Clearing Find restores the grid exactly.
    bar.find_field.setText("")
    assert _new_value_column(panel) == ["", "", ""]


def test_live_replace_reports_the_proposed_row_count(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    assert bar.status_label.text() == "2 row(s) proposed"
    bar.find_field.setText("zzz")
    assert bar.status_label.text() == ""


def test_live_replace_never_touches_the_read_only_value_column(qtbot):
    """Replace in caption mode populates PROPOSED new values; the scanned
    Value column and the XML behind it are untouched."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    assert _visible_value_column(panel) == ["Home Page", "Orders Page", "Cart"]
    assert [e.value for e in panel._model.entries()] == [
        "Home Page",
        "Orders Page",
        "Cart",
    ]
    # The proposals are ordinary changed_edits, ready for the explicit Apply.
    assert [v for _, v in panel.changed_edits()] == ["Home Screen", "Orders Screen"]


def test_live_replace_normal_mode_is_case_insensitive_until_match_case(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("X")
    bar.find_field.setText("home")
    assert _new_value_column(panel) == ["X Page", "", ""]
    bar.match_case_checkbox.setChecked(True)
    assert _new_value_column(panel) == ["", "", ""]


def test_live_replace_extended_mode_decodes_escapes(qtbot):
    """Extended mode reaches apply_find_replace's escape decoding: \\x20 is a
    space, so it matches where the literal string "\\x20" never would."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("_")
    bar.find_field.setText("\\x20")
    # Still Normal mode: the literal backslash-x-2-0 matches nothing.
    assert _new_value_column(panel) == ["", "", ""]
    bar.set_mode("extended")
    assert bar.selected_mode() == "extended"
    assert _new_value_column(panel) == ["Home_Page", "Orders_Page", ""]


def test_live_replace_regular_mode_supports_capture_groups(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.set_mode("regular")
    bar.replace_field.setText(r"\1!")
    bar.find_field.setText(r"^(\w+) Page$")
    assert _new_value_column(panel) == ["Home!", "Orders!", ""]


def test_invalid_regex_shows_an_inline_message_instead_of_raising(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.set_mode("regular")
    bar.replace_field.setText("X")
    bar.find_field.setText("Page")
    assert _new_value_column(panel) == ["Home X", "Orders X", ""]

    # A half-typed group is invalid: reported inline, and the stale preview is
    # rolled back rather than left behind.
    bar.find_field.setText("Page(")
    assert "Invalid regular expression" in bar.error_label.text()
    assert bar.status_label.text() == ""
    assert _new_value_column(panel) == ["", "", ""]

    # Completing the pattern clears the error and previews again.
    bar.find_field.setText("(Page)")
    assert bar.error_label.text() == ""
    assert _new_value_column(panel) == ["Home X", "Orders X", ""]


def test_invalid_regex_is_reported_even_when_no_rows_are_in_scope(qtbot):
    """The pattern is compile-checked up front, so an empty scope cannot
    silently swallow a broken regex."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("no-such-caption", "normal", False)
    assert panel._proxy.rowCount() == 0
    bar = panel.find_replace_bar
    bar.set_mode("regular")
    bar.find_field.setText("Page(")
    assert "Invalid regular expression" in bar.error_label.text()


def test_bar_filter_button_pushes_the_find_filter_and_refreshes_the_banner(qtbot):
    """Filter stays an explicit button press (not live) and goes through the
    same apply_find_filter path the modal uses."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.find_field.setText("Page")
    # Typing alone must not have filtered anything.
    assert panel._proxy.rowCount() == 3
    bar.apply_filter()
    assert _visible_value_column(panel) == ["Home Page", "Orders Page"]
    assert 'Find "Page"' in panel._filter_banner_label.text()
    assert "showing 2 of 3 rows" in panel._filter_banner_label.text()


def test_bar_filter_button_reports_invalid_regex_inline(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.set_mode("regular")
    bar.set_find_text("Page(")
    bar.apply_filter()
    assert "Invalid regular expression" in bar.error_label.text()
    # BUG-028's ordering invariant still holds: a rejected pattern never
    # reaches the proxy and never advertises itself in the banner.
    assert panel._proxy.find_pattern() == ""
    assert panel._filter_banner.isHidden()


def test_live_replace_is_scoped_to_the_visible_rows_when_a_filter_is_active(qtbot):
    """DECISION (spec silent): the live preview only ever writes into rows the
    active filters leave visible — a live edit the user cannot see contradicts
    §13's visible-state discipline. Project-wide stays behind the scope dropdown
    plus an explicit Replace All press (FQ-017)."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "normal", False)
    assert _visible_value_column(panel) == ["Home Page"]
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    # "Orders Page" also matches the pattern but is filtered out: untouched.
    assert _new_value_column(panel) == ["Home Screen", "", ""]


def test_live_replace_rescopes_when_the_filter_moves(qtbot):
    """Rows that leave the visible set get their previous New Value back; rows
    that enter it pick the proposal up."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "normal", False)
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    assert _new_value_column(panel) == ["Home Screen", "", ""]

    # Widen the filter: the second row is now in scope, the first still is.
    panel.apply_find_filter("Page", "normal", False)
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]

    # Narrow to the other row: the first row's proposal is rolled back.
    panel.apply_find_filter("Orders", "normal", False)
    assert _new_value_column(panel) == ["", "Orders Screen", ""]

    # clear_all_filters — the single clear path — widens the scope to the
    # whole grid and does NOT clear the (non-filter) live preview.
    panel.clear_all_filters()
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]
    assert panel._filter_banner.isHidden()


def test_live_replace_rescopes_for_a_preset_predicate_filter(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("-")
    bar.find_field.setText("t")
    before = _new_value_column(panel)
    # "Equipment", "Attachments", "Other" contain a "t"; "WBS"/"Name" do not.
    assert before == ["Equipmen-", "", "A--achmen-s", "", "O-her"]
    panel.filter_to_table("pr.equip")
    assert _new_value_column(panel) == ["Equipmen-", "", "", "", ""]


def test_live_replace_rescopes_for_a_header_value_filter(qtbot):
    """The header popup's OK re-scopes the preview too — without putting the
    header filter into the banner (it keeps its exclusive ▼ marker)."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]

    popup = panel.open_header_filter(_ANCHOR_COLUMN)
    qtbot.addWidget(popup)
    for i, label in enumerate(popup.item_labels()):
        popup.set_checked(i, label == "home")
    popup.apply_filter()
    assert _new_value_column(panel) == ["Home Screen", "", ""]
    assert panel._proxy.filtered_columns() == {_ANCHOR_COLUMN}
    assert panel._filter_banner.isHidden()


def test_live_replace_preserves_a_hand_typed_new_value_it_overwrote(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel._model.set_new_value(0, "Hand written")
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]
    bar.find_field.setText("")
    assert _new_value_column(panel) == ["Hand written", "", ""]


def test_replace_all_commits_the_preview_and_stops_tracking(qtbot):
    """FQ-017: Replace All is the handoff the deleted Close button used to be.
    Same contract as the old close_bar: the proposals survive as ordinary New
    Values, and nothing rewrites them afterwards."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    assert panel._live_replace_baseline != {}
    bar.replace_all_button.click()
    assert bar.isHidden() is False
    assert bar.is_active() is False
    assert panel._live_replace_baseline == {}
    assert bar.status_label.text() == "2 row(s) replaced"
    # The proposals survive as ordinary New Values.
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]
    # And a later filter change no longer rewrites them.
    panel.apply_find_filter("Cart", "normal", False)
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]


def test_a_hand_edit_after_replace_all_is_never_silently_reverted(qtbot):
    """⚠️ THE failure mode FQ-017 (d) exists to prevent. With the bar permanent
    there is no Close to release the rollback baseline, so a re-run could
    resurrect the pre-preview value over a hand edit — or, once the baseline is
    forgotten, overwrite the hand edit from the row's Value with no way back.
    Replace All ends the reversible phase, so every later re-scope leaves the
    hand edit alone."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    bar.replace_all_button.click()

    panel._model.set_new_value(0, "Hand written after the fact")
    # Every gesture that re-scopes the preview, with the Find field still full.
    panel.apply_find_filter("Cart", "normal", False)
    panel.clear_all_filters()
    panel.filter_to_field("orders")
    panel.clear_all_filters()
    assert _new_value_column(panel) == [
        "Hand written after the fact",
        "Orders Screen",
        "",
    ]


def test_touching_a_field_after_replace_all_re_arms_a_reversible_preview(qtbot):
    """The commit is not a one-way door: editing the pattern starts a fresh
    preview whose baseline is the committed (and any hand-edited) values, so
    clearing Find still restores them."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    bar.replace_all_button.click()
    panel._model.set_new_value(0, "Hand written after the fact")

    bar.replace_field.setText("View")
    assert bar.is_active() is True
    assert panel._live_replace_baseline[0] == "Hand written after the fact"
    assert _new_value_column(panel) == ["Home View", "Orders View", ""]
    bar.find_field.setText("")
    assert _new_value_column(panel) == [
        "Hand written after the fact",
        "Orders Screen",
        "",
    ]


def test_focus_find_replace_bar_seeds_from_the_active_pattern_without_previewing(qtbot):
    """Seeding Find-what must not fire the live replace: with an empty
    Replace-with that would instantly propose deleting the pattern. The seeding
    that show_bar used to do lives on the focus path now (FQ-017 (b))."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Page", "normal", False)
    panel.focus_find_replace_bar()
    bar = panel.find_replace_bar
    assert bar.find_field.text() == "Page"
    assert bar.is_active() is True
    assert _new_value_column(panel) == ["", "", ""]


def test_focus_never_clobbers_text_the_user_already_typed(qtbot):
    """Seeding is conditional: a focus gesture must not overwrite a half-typed
    pattern with the grid's active filter pattern."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Page", "normal", False)
    bar = panel.find_replace_bar
    bar.set_find_text("Cart")
    panel.focus_find_replace_bar()
    assert bar.find_field.text() == "Cart"


def test_find_replace_bar_in_context_menu_wired(qtbot, monkeypatch):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    captured = {}

    class _FakeMenu:
        def __init__(self, *a, **k):
            self._actions = []

        def addAction(self, label, cb=None):
            self._actions.append((label, cb))
            return (label, cb)

        def addSeparator(self):
            pass

        def addMenu(self, label):
            return _FakeMenu()

        def exec(self, *a, **k):
            captured["actions"] = self._actions

    monkeypatch.setattr("pgtp_editor.ui.caption_management_panel.QMenu", _FakeMenu)
    panel._show_context_menu(panel._table.viewport().rect().center())
    cb = dict(captured["actions"])["Focus Find / Replace bar"]
    assert cb == panel.focus_find_replace_bar


def test_escape_returns_focus_to_the_grid_without_hiding_the_bar(qtbot):
    """FQ-017: Escape is a focus gesture, not a hide gesture — the bar is
    permanent, so there is nothing to hide."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.find_field.setFocus()
    qtbot.keyClick(bar, Qt.Key.Key_Escape)
    assert bar.isHidden() is False
    assert panel.focusWidget() is panel._table


# ---------------------------------------------------------------------------
# FQ-017: the permanent bar's control layout, scope dropdown and Clear filter
# ---------------------------------------------------------------------------


def test_bar_control_layout_after_the_modal_was_deleted(qtbot):
    """The exact inventory FQ-017 specifies: Close is gone; Replace All, Clear
    filter and the scope dropdown are new; everything else is retained."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    bar = panel.find_replace_bar
    for kept in (
        "find_field",
        "mode_combo",
        "match_case_checkbox",
        "filter_button",
        "replace_field",
        "status_label",
        "error_label",
    ):
        assert hasattr(bar, kept), kept
    assert bar.filter_button.text() == "Filter"
    assert bar.clear_filter_button.text() == "Clear filter"
    assert bar.replace_all_button.text() == "Replace All"
    # The scope dropdown sits immediately before Replace All, in the row that
    # also holds the Replace-with field.
    row = bar.replace_all_button.parentWidget().layout().itemAt(1).layout()
    widgets = [row.itemAt(i).widget() for i in range(row.count())]
    assert widgets[:3] == [bar.replace_field, bar.scope_combo, bar.replace_all_button]


def test_scope_dropdown_offers_two_scopes_and_defaults_to_filtered(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    combo = panel.find_replace_bar.scope_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    scopes = [combo.itemData(i) for i in range(combo.count())]
    assert labels == ["in filtered results", "in all project"]
    assert scopes == ["filtered", "project"]
    assert panel.find_replace_bar.selected_scope() == "filtered"


def test_replace_all_in_filtered_results_matches_the_live_preview(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "normal", False)
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    previewed = _new_value_column(panel)
    assert previewed == ["Home Screen", "", ""]
    bar.replace_all_button.click()
    # Nothing new to write: the filtered scope was already live.
    assert _new_value_column(panel) == previewed
    assert bar.status_label.text() == "1 row(s) replaced"


def test_replace_all_in_all_project_reaches_rows_the_filter_hides(qtbot):
    """The capability the deleted modal was the only route to. It is reachable
    ONLY by pressing the button — see the next test."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "normal", False)
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    bar.set_scope("project")
    assert bar.selected_scope() == "project"
    bar.replace_all_button.click()
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]
    assert bar.status_label.text() == "2 row(s) replaced"
    # Still non-destructive: only New Value moved.
    assert [e.value for e in panel._model.entries()] == [
        "Home Page",
        "Orders Page",
        "Cart",
    ]


def test_choosing_the_project_scope_does_not_drive_the_live_preview(qtbot):
    """⚠️ Explicitly rejected alternative: if the dropdown fed the live preview,
    a single keystroke would rewrite every caption in the project."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    panel.apply_find_filter("Home", "normal", False)
    bar = panel.find_replace_bar
    bar.set_scope("project")
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    # The preview is still filtered-scoped, unchanged by the dropdown.
    assert _new_value_column(panel) == ["Home Screen", "", ""]
    bar.set_scope("filtered")
    bar.set_scope("project")
    assert _new_value_column(panel) == ["Home Screen", "", ""]


def test_replace_all_reports_invalid_regex_inline_and_commits_nothing(qtbot):
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.set_mode("regular")
    bar.find_field.setText("Page(")
    bar.replace_all_button.click()
    assert "Invalid regular expression" in bar.error_label.text()
    assert bar.status_label.text() == ""
    assert bar._committed is False


def test_clear_filter_button_uses_the_single_clear_all_filters_path(qtbot):
    """Bound to clear_all_filters — no new clear path — so it also drops the
    tree-set row predicate the retained banner is the only surface for."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel.filter_to_table("pr.equip")
    panel.apply_find_filter("Equip", "normal", False)
    assert panel._filter_banner.isVisibleTo(panel)
    bar = panel.find_replace_bar
    bar.clear_filter_button.click()
    assert panel._proxy.find_pattern() == ""
    assert not panel._proxy.row_predicate_label()
    assert panel._filter_banner.isHidden()


def test_clear_filter_leaves_the_find_field_and_its_preview_alone(qtbot):
    """Emptying Find would silently roll the live preview back, so the button
    clears the grid's filters, not the bar's pattern."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_replace_entries())
    bar = panel.find_replace_bar
    bar.replace_field.setText("Screen")
    bar.find_field.setText("Page")
    bar.apply_filter()
    bar.clear_filter_button.click()
    assert bar.find_field.text() == "Page"
    assert _new_value_column(panel) == ["Home Screen", "Orders Screen", ""]


def test_the_active_filter_banner_survives_the_permanent_bar(qtbot):
    """FQ-017: retiring the banner would re-create BUG-020 — a text field cannot
    express a row-predicate filter set by a tree gesture."""
    panel = CaptionManagementPanel()
    qtbot.addWidget(panel)
    panel.load_entries(_context_entries())
    panel.filter_to_field("wbs_id")
    assert panel._filter_banner.isVisibleTo(panel)
    assert "Field = wbs_id" in panel._filter_banner_label.text()
    assert panel._filter_banner_clear_button.text() == "Clear"
