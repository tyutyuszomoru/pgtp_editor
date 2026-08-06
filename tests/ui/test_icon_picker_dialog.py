"""FQ-004 -- IconPickerDialog tests.

The picker is driven through its seam (`set_filter`, `visible_icon_ids`,
`select_icon`, `chosen_icon_id`); never `.exec()`'d.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog

from pgtp_editor.ui import icons
from pgtp_editor.ui.icon_picker_dialog import DEFAULT_CHOICE, IconPickerDialog

COLOR = QColor("#ff0000")


def _picker(qtbot, current_icon_id=None):
    dialog = IconPickerDialog(current_icon_id, COLOR)
    qtbot.addWidget(dialog)
    return dialog


def test_picker_lists_the_whole_catalog_by_default(qtbot):
    dialog = _picker(qtbot)
    assert dialog.visible_icon_ids() == icons.catalog_ids()


def test_picker_always_offers_the_reset_to_default_choice(qtbot):
    dialog = _picker(qtbot)
    assert dialog.has_default_choice()
    dialog.set_filter("zoom")
    assert dialog.has_default_choice()
    dialog.set_filter("zzzz-no-such-icon")
    assert dialog.visible_icon_ids() == []
    assert dialog.has_default_choice()


def test_default_cell_is_row_zero_and_yields_the_sentinel(qtbot):
    dialog = _picker(qtbot, "zoom-in")
    assert dialog.chosen_icon_id() == "zoom-in"
    dialog.icon_list.setCurrentRow(0)
    assert dialog.chosen_icon_id() is DEFAULT_CHOICE


def test_picker_filters_by_search_text(qtbot):
    dialog = _picker(qtbot)
    dialog.set_filter("zoom")
    visible = dialog.visible_icon_ids()
    assert visible
    assert all("zoom" in icon_id for icon_id in visible)
    assert len(visible) < len(icons.catalog_ids())


def test_search_edit_drives_the_filter(qtbot):
    dialog = _picker(qtbot)
    dialog.search_edit.setText("zoom")
    assert all("zoom" in icon_id for icon_id in dialog.visible_icon_ids())
    dialog.search_edit.setText("")
    assert dialog.visible_icon_ids() == icons.catalog_ids()


def test_filtering_is_case_insensitive_and_matches_human_names(qtbot):
    dialog = _picker(qtbot)
    dialog.set_filter("Save As")
    assert "document-save-as" in dialog.visible_icon_ids()


def test_initial_selection_is_the_current_icon(qtbot):
    dialog = _picker(qtbot, "document-save-as")
    assert dialog.chosen_icon_id() == "document-save-as"
    item = dialog.icon_list.currentItem()
    assert item is not None
    assert item.text() == "Document Save As"


def test_no_current_icon_selects_the_default_cell(qtbot):
    dialog = _picker(qtbot)
    assert dialog.chosen_icon_id() is DEFAULT_CHOICE
    assert dialog.icon_list.currentRow() == 0


def test_select_icon_updates_the_choice(qtbot):
    dialog = _picker(qtbot)
    dialog.select_icon("zoom-in")
    assert dialog.chosen_icon_id() == "zoom-in"
    dialog.select_icon(None)
    assert dialog.chosen_icon_id() is DEFAULT_CHOICE


def test_selection_survives_a_filter_that_still_shows_it(qtbot):
    dialog = _picker(qtbot, "zoom-in")
    dialog.set_filter("zoom")
    assert dialog.chosen_icon_id() == "zoom-in"


def test_selection_falls_back_to_default_when_filtered_away(qtbot):
    dialog = _picker(qtbot, "zoom-in")
    dialog.set_filter("document")
    assert dialog.chosen_icon_id() is DEFAULT_CHOICE


def test_selecting_an_unknown_id_falls_back_to_default(qtbot):
    dialog = _picker(qtbot, "no-such-icon")
    assert dialog.chosen_icon_id() is DEFAULT_CHOICE


def test_every_listed_cell_carries_a_rendered_icon(qtbot):
    dialog = _picker(qtbot)
    dialog.set_filter("zoom")
    for row in range(dialog.icon_list.count()):
        item = dialog.icon_list.item(row)
        if row == 0:
            continue  # the Default cell is intentionally icon-less
        assert not item.icon().isNull(), item.text()


def test_double_click_accepts_with_that_icon(qtbot):
    dialog = _picker(qtbot)
    dialog.set_filter("zoom")
    item = dialog.icon_list.item(1)
    dialog._on_double_clicked(item)
    assert dialog.chosen_icon_id() == item.data(Qt.ItemDataRole.UserRole)
    assert dialog.result() == int(QDialog.DialogCode.Accepted)
