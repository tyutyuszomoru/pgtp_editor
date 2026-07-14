"""Tests for the real File -> Open flow wired to pgtp_editor.model.parser.

These drive MainWindow.open_project_file(path) directly rather than going
through QFileDialog (which would block on a modal dialog in a headless
test run) — QFileDialog wiring itself is a single trivial call in
_open_project and isn't independently tested here.
"""
from unittest.mock import patch

import pytest

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


def test_open_project_file_tracks_current_project_and_path(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(path))

    assert window._current_project is not None
    assert window._current_project.pages[0].file_name == "development_equipment"
    assert window._current_project_path == str(path)


def test_current_project_is_none_before_any_open(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._current_project is None
    assert window._current_project_path is None


def test_open_project_file_does_not_overwrite_current_project_on_parse_failure(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    valid_path = tmp_path / "valid.pgtp"
    valid_path.write_text(VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(valid_path))
    first_project = window._current_project

    broken_path = tmp_path / "broken.pgtp"
    broken_path.write_text(MALFORMED_PGTP, encoding="utf-8")
    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(broken_path))

    assert window._current_project is first_project
    assert window._current_project_path == str(valid_path)


def test_open_project_file_populates_xml_editor_with_raw_text(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")

    window.open_project_file(str(path))

    assert window.center_stage.xml_editor.toPlainText() == VALID_PGTP


MALFORMED_PGTP_WITH_KNOWN_LINE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<Project>\n"
    "  <Presentation>\n"
    "    <Pages>\n"
    "      <Page>\n"
    "    </Pages>\n"
    "  </Presentation>\n"
    "</Project>\n"
)


def test_parse_failure_populates_and_shows_raw_xml_tab(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP_WITH_KNOWN_LINE, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(path))

    assert window.center_stage.isTabVisible(window.center_stage.raw_xml_tab_index) is True
    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index
    assert window.center_stage.xml_editor.toPlainText() == MALFORMED_PGTP_WITH_KNOWN_LINE


def test_parse_failure_syncs_raw_xml_panel_checkbox(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP_WITH_KNOWN_LINE, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(path))

    assert window._raw_xml_panel_action.isChecked() is True


def test_parse_failure_highlights_the_reported_error_line(qtbot, tmp_path):
    from lxml import etree

    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP_WITH_KNOWN_LINE, encoding="utf-8")

    # Establish, independently of this test's assumptions, what line lxml
    # itself reports for this fixture -- rather than hard-coding a guessed
    # line number.
    try:
        etree.parse(str(path))
        expected_line = None
    except etree.XMLSyntaxError as exc:
        expected_line = exc.lineno
    assert expected_line is not None

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(path))

    selections = window.center_stage.xml_editor.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.blockNumber() == expected_line - 1


def test_parse_failure_still_shows_dialog(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "broken.pgtp"
    path.write_text(MALFORMED_PGTP_WITH_KNOWN_LINE, encoding="utf-8")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window.open_project_file(str(path))

    mock_critical.assert_called_once()


def test_open_project_file_succeeds_even_when_raw_reread_hits_oserror(qtbot, tmp_path):
    """The success path re-reads the file from disk to populate the raw XML
    editor after `load_project` already succeeded -- a TOCTOU race (the file
    could vanish or become unreadable between the two reads). That second
    read failing must not crash the otherwise-successful open: the project
    tree/model still populate normally, only the raw-text editor population
    is skipped."""
    window = MainWindow()
    qtbot.addWidget(window)
    path = tmp_path / "valid.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")

    # Simulate the *second* read (the raw-text re-read for the editor)
    # failing while load_project's own read succeeded, by making the shared
    # read helper raise for main_window only. load_project uses the model
    # layer's own read path and is unaffected.
    with patch("pgtp_editor.ui.main_window.read_pgtp_text", side_effect=OSError("boom")):
        window.open_project_file(str(path))

    assert window.project_tree.topLevelItemCount() == 1
    assert window._current_project is not None
    assert window._current_project_path == str(path)
    assert window.center_stage.xml_editor.toPlainText() == ""


def test_parse_failure_does_not_crash_when_file_unreadable_after_initial_parse_attempt(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    missing_path = tmp_path / "does_not_exist.pgtp"

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(missing_path))

    # A missing file raises PgtpParseError via the OSError branch in
    # load_project; _handle_parse_failure's own re-read then also fails with
    # OSError, and must not crash -- it simply leaves the Raw XML tab alone.
    # Under the new default (spec §6.1) the Raw XML tab is visible; the
    # unreadable-file branch returns early without touching its visibility, so
    # it remains visible.
    assert window.center_stage.isTabVisible(window.center_stage.raw_xml_tab_index) is True


from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample"


def test_open_real_sample_file_populates_editor_byte_for_byte(qtbot):
    sample_path = SAMPLE_DIR / "dev_Ferrara.pgtp"
    if not sample_path.exists():
        pytest.skip(f"sample fixture not present: {sample_path}")

    window = MainWindow()
    qtbot.addWidget(window)

    window.open_project_file(str(sample_path))

    expected_text = sample_path.read_text(encoding="utf-8")
    actual_text = window.center_stage.xml_editor.toPlainText()
    # QPlainTextEdit.toPlainText() is a known, Qt-internal lossy round-trip
    # for U+00A0 (non-breaking space): QTextDocument stores NBSP as a regular
    # space plus a non-breakable-text flag (for line-wrapping purposes), and
    # toPlainText() discards that flag, silently downgrading NBSP to U+0020.
    # (QTextDocument.toRawText() does preserve it -- confirmed directly
    # against this same widget -- so the character isn't actually lost from
    # the document model, only from what toPlainText() reports.) This sample
    # file contains 3 real NBSP characters in a caption attribute value, so
    # normalize both sides the same way before comparing; every other
    # character must still match exactly.
    assert actual_text.replace("\xa0", " ") == expected_text.replace("\xa0", " ")
