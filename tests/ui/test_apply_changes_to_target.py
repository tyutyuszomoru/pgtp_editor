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
