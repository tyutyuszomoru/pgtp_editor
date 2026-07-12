"""Tests for MainWindow._apply_changes_to_target -- see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-writeback-design.md §7.
"""
from unittest.mock import patch

from PySide6.QtCore import Qt

from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Old Caption"/>
    </Pages>
  </Presentation>
</Project>
"""

CHANGED_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="New Caption"/>
    </Pages>
  </Presentation>
</Project>
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _compare(window, source_path, target_path):
    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._compare_merge_two_files()


def test_apply_with_nothing_checked_shows_information_and_does_not_touch_target(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    _compare(window, source_path, target_path)
    original_target_bytes = open(target_path, "rb").read()

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._apply_changes_to_target()

    mock_info.assert_called_once()
    assert open(target_path, "rb").read() == original_target_bytes


def test_apply_with_ambiguous_checked_difference_refuses_entire_batch(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    _compare(window, source_path, target_path)
    original_target_bytes = open(target_path, "rb").read()

    panel = window.center_stage.diff_merge_panel
    leaves = panel._flattened_leaves()
    assert len(leaves) == 1
    diff = leaves[0].data(0, Qt.ItemDataRole.UserRole)
    diff.ambiguous = True
    leaves[0].setCheckState(0, Qt.CheckState.Checked)

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._apply_changes_to_target()

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert "Ambiguous" in args[1] or "ambiguous" in args[2].lower()
    assert not (tmp_path / "target.pgtp.bak").exists()
    assert open(target_path, "rb").read() == original_target_bytes


import os

from PySide6.QtCore import Qt


def _check_all_leaves(panel):
    for leaf in panel._flattened_leaves():
        leaf.setCheckState(0, Qt.CheckState.Checked)


def test_apply_successful_writes_bak_and_mutates_target_and_reloads_project_tree(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    original_target_bytes = open(target_path, "rb").read()
    _compare(window, source_path, target_path)

    panel = window.center_stage.diff_merge_panel
    _check_all_leaves(panel)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._apply_changes_to_target()

    mock_info.assert_called_once()

    bak_path = target_path + ".bak"
    assert os.path.exists(bak_path)
    assert open(bak_path, "rb").read() == original_target_bytes

    new_target_bytes = open(target_path, "rb").read()
    assert b'caption="New Caption"' in new_target_bytes

    # Project Tree / _current_project refreshed to the post-merge state.
    assert window._current_project is not None
    assert window._current_project.pages[0].attrib["caption"] == "New Caption"
    assert window._current_project_path == target_path

    # The change-list tree itself is left showing the just-applied
    # comparison as-is -- NOT cleared, NOT re-diffed.
    assert len(panel._flattened_leaves()) == 1


def test_apply_second_run_overwrites_previous_bak_with_first_runs_merged_content(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    _compare(window, source_path, target_path)
    panel = window.center_stage.diff_merge_panel
    _check_all_leaves(panel)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information"):
        window._apply_changes_to_target()

    first_merged_bytes = open(target_path, "rb").read()

    # Re-run Apply a second time on the same (now-stale) checked-differences
    # list without re-comparing.
    with patch("pgtp_editor.ui.main_window.QMessageBox.information"):
        window._apply_changes_to_target()

    bak_path = target_path + ".bak"
    assert open(bak_path, "rb").read() == first_merged_bytes


def test_apply_partial_failure_writes_nothing_and_names_the_unresolvable_difference(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    original_target_bytes = open(target_path, "rb").read()
    _compare(window, source_path, target_path)

    panel = window.center_stage.diff_merge_panel
    _check_all_leaves(panel)
    # Corrupt the one checked Difference's path so resolve_path fails inside
    # apply_differences, simulating Target having changed on disk since
    # compare-time.
    leaves = panel._flattened_leaves()
    diff = leaves[0].data(0, Qt.ItemDataRole.UserRole)
    diff.path = ["page_that_no_longer_exists"]

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._apply_changes_to_target()

    mock_critical.assert_called_once()
    args, _kwargs = mock_critical.call_args
    assert "page_that_no_longer_exists" in args[2]
    assert not os.path.exists(target_path + ".bak")
    assert open(target_path, "rb").read() == original_target_bytes
