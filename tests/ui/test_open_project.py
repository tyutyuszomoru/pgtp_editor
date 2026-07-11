"""Tests for the real File -> Open flow wired to pgtp_editor.model.parser.

These drive MainWindow.open_project_file(path) directly rather than going
through QFileDialog (which would block on a modal dialog in a headless
test run) — QFileDialog wiring itself is a single trivial call in
_open_project and isn't independently tested here.
"""
from unittest.mock import patch

from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Equipment">
        <EventHandlers>
          <OnPreparePage>echo 'hi';</OnPreparePage>
        </EventHandlers>
      </Page>
    </Pages>
  </Presentation>
</Project>
"""

MALFORMED_PGTP = "<Project><Presentation><Pages><Page></Pages></Presentation></Project>"


def test_open_project_file_populates_tree(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(path))

    assert window.project_tree.topLevelItemCount() == 1
    assert window.project_tree.topLevelItem(0).text(0) == "(P) Equipment [pr.equipment]"


def test_open_project_file_shows_error_dialog_on_malformed_xml(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window.open_project_file(str(path))

    mock_critical.assert_called_once()
    assert window.project_tree.topLevelItemCount() == 0


def test_open_project_file_does_not_crash_on_missing_file(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    missing_path = tmp_path / "does_not_exist.pgtp"

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window.open_project_file(str(missing_path))

    mock_critical.assert_called_once()


def test_open_project_file_does_not_clear_tree_on_failure_after_success(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    valid_path = tmp_path / "valid.pgtp"
    valid_path.write_text(VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(valid_path))
    assert window.project_tree.topLevelItemCount() == 1

    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")
    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    # Previously-loaded tree stays intact — a failed open never silently
    # empties the tree.
    assert window.project_tree.topLevelItemCount() == 1


def test_open_action_triggers_file_dialog(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(path), "PGTP files (*.pgtp)"),
    ):
        window._open_project()

    assert window.project_tree.topLevelItemCount() == 1


def test_open_action_cancelled_dialog_does_nothing(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=("", ""),
    ):
        window._open_project()

    assert window.project_tree.topLevelItemCount() == 0
