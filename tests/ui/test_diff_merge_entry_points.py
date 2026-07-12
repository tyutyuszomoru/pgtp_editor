"""Tests for the three Diff/Merge comparison entry points wired into
MainWindow and ProjectTreePanel: "Compare / Merge Two Files...",
"Compare This Page With...", and "Compare This Detail With...".
"""
from unittest.mock import patch

from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

CHANGED_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Changed Caption">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

MALFORMED_PGTP = "<Project><Presentation><Pages><Page></Pages></Presentation></Project>"


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_compare_merge_two_files_prompts_for_source_when_none_open(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", VALID_PGTP)
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._compare_merge_two_files()

    assert window.center_stage.currentIndex() == window.center_stage.diff_merge_tab_index
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1


def test_compare_merge_two_files_uses_current_project_as_source_without_prompting(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    current_path = _write(tmp_path, "current.pgtp", VALID_PGTP)
    window.open_project_file(current_path)
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ) as mock_dialog:
        window._compare_merge_two_files()

    mock_dialog.assert_called_once()
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1


def test_compare_merge_two_files_cancelled_target_dialog_does_nothing(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", VALID_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), ("", "")],
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._compare_merge_two_files()

    # Cancelling the target dialog is a no-op: no comparison is run, so the
    # change-list tree stays empty. (Note: diff_merge_tab_index is tab 0,
    # which is already CenterStage's default current tab on construction,
    # so asserting on currentIndex() alone can't distinguish "never
    # navigated" from "navigated but happens to still be tab 0" — the tree
    # content is the reliable signal here.)
    assert window.center_stage.diff_merge_panel._flattened_leaves() == []
    # A cancelled dialog must be a clean no-op, not a fallthrough into
    # load_project("") raising PgtpParseError which happens to be caught by
    # the same except-block and also leaves the tree empty. That coincidence
    # would let a deleted `if not target_path: return` early-exit go
    # undetected, so we additionally assert no error dialog was shown.
    mock_critical.assert_not_called()


def test_compare_merge_two_files_shows_error_on_target_parse_failure(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", VALID_PGTP)
    broken_path = _write(tmp_path, "broken.pgtp", MALFORMED_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (broken_path, "")],
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._compare_merge_two_files()

    mock_critical.assert_called_once()


from tests.ui._menu_helpers import find_action, find_top_menu


DUAL_CAPTION_CHANGED_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Changed A" ability="Changed B">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_next_and_prev_difference_menu_actions_navigate_the_panel(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", DUAL_CAPTION_CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._compare_merge_two_files()

    menu = find_top_menu(window, "Diff / Merge")
    next_action = find_action(menu, "Next Difference")
    prev_action = find_action(menu, "Prev Difference")

    panel = window.center_stage.diff_merge_panel
    leaves = panel._flattened_leaves()
    assert len(leaves) == 2

    next_action.trigger()
    assert panel.tree.currentItem() is leaves[0]
    next_action.trigger()
    assert panel.tree.currentItem() is leaves[1]

    prev_action.trigger()
    assert panel.tree.currentItem() is leaves[0]


def test_compare_this_page_with_real_handler(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", VALID_PGTP))
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    page_item = window.project_tree.topLevelItem(0)
    menu = window.project_tree.build_page_menu(page_item)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ):
        find_action(menu, "Compare This Page With...").trigger()

    assert window.center_stage.currentIndex() == window.center_stage.diff_merge_tab_index
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1


def test_compare_this_page_with_shows_error_when_page_not_found_in_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", VALID_PGTP))
    other_page_pgtp = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="a_totally_different_page" tableName="pr.other" caption="Other">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""
    target_path = _write(tmp_path, "target.pgtp", other_page_pgtp)

    page_item = window.project_tree.topLevelItem(0)
    menu = window.project_tree.build_page_menu(page_item)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        find_action(menu, "Compare This Page With...").trigger()

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert "development_equipment" in args[2]


SOURCE_WITH_DETAIL_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <Details>
          <Detail caption="Equipment\\Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item" ability="insert,edit">
            </Page>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

TARGET_WITH_CHANGED_DETAIL_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <Details>
          <Detail caption="Equipment\\Sub-item">
            <Page fileName="" tableName="pr.attachment" caption="Sub-item" ability="view">
            </Page>
          </Detail>
        </Details>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

TARGET_MISSING_DETAIL_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
      </Page>
    </Pages>
  </Presentation>
</Project>
"""


def test_compare_this_detail_with_real_handler(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", SOURCE_WITH_DETAIL_PGTP))
    target_path = _write(tmp_path, "target.pgtp", TARGET_WITH_CHANGED_DETAIL_PGTP)

    detail_item = window.project_tree.topLevelItem(0).child(0)
    menu = window.project_tree.build_detail_menu(detail_item)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ):
        find_action(menu, "Compare This Detail With...").trigger()

    assert window.center_stage.currentIndex() == window.center_stage.diff_merge_tab_index
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1


def test_compare_this_detail_with_shows_error_when_detail_not_found_in_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", SOURCE_WITH_DETAIL_PGTP))
    target_path = _write(tmp_path, "target.pgtp", TARGET_MISSING_DETAIL_PGTP)

    detail_item = window.project_tree.topLevelItem(0).child(0)
    menu = window.project_tree.build_detail_menu(detail_item)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        find_action(menu, "Compare This Detail With...").trigger()

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert "pr.attachment" in args[2]


def test_compare_merge_two_files_tracks_current_diff_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", VALID_PGTP)
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._compare_merge_two_files()

    assert window._current_diff_target_path == target_path
    assert window._current_diff_target_project is not None
    assert window._current_diff_target_project.pages[0].file_name == "development_equipment"


def test_compare_this_page_with_tracks_current_diff_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", VALID_PGTP))
    target_path = _write(tmp_path, "target.pgtp", CHANGED_PGTP)

    page_item = window.project_tree.topLevelItem(0)
    menu = window.project_tree.build_page_menu(page_item)
    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ):
        find_action(menu, "Compare This Page With...").trigger()

    assert window._current_diff_target_path == target_path
    assert window._current_diff_target_project is not None


def test_compare_this_detail_with_tracks_current_diff_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_project_file(_write(tmp_path, "source.pgtp", SOURCE_WITH_DETAIL_PGTP))
    target_path = _write(tmp_path, "target.pgtp", TARGET_WITH_CHANGED_DETAIL_PGTP)

    detail_item = window.project_tree.topLevelItem(0).child(0)
    menu = window.project_tree.build_detail_menu(detail_item)
    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(target_path, ""),
    ):
        find_action(menu, "Compare This Detail With...").trigger()

    assert window._current_diff_target_path == target_path
    assert window._current_diff_target_project is not None
