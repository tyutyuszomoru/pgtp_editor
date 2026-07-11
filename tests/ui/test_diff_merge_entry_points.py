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
    ):
        window._compare_merge_two_files()

    # Cancelling the target dialog is a no-op: no comparison is run, so the
    # change-list tree stays empty. (Note: diff_merge_tab_index is tab 0,
    # which is already CenterStage's default current tab on construction,
    # so asserting on currentIndex() alone can't distinguish "never
    # navigated" from "navigated but happens to still be tab 0" — the tree
    # content is the reliable signal here.)
    assert window.center_stage.diff_merge_panel._flattened_leaves() == []


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
