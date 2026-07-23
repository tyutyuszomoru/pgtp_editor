from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="orders" tableName="pr.orders" caption="Orders"/>
    </Pages>
  </Presentation>
</Project>
"""


def _open(window, tmp_path):
    path = tmp_path / "p.pgtp"
    path.write_text(VALID_PGTP, encoding="utf-8")
    window.open_project_file(str(path))


def _record_status(window, monkeypatch):
    messages = []
    monkeypatch.setattr(
        window.statusBar(), "showMessage",
        lambda msg, *a, **k: messages.append(msg),
    )
    return messages


def test_validate_shows_validating_message_and_restores_cursor(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    messages = _record_status(window, monkeypatch)

    window._validate_project()

    assert any(m.startswith("Validating ") for m in messages), messages
    assert QApplication.overrideCursor() is None


def test_reparse_shows_reparsing_message_and_restores_cursor(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    messages = _record_status(window, monkeypatch)

    window._reparse_raw_xml()

    assert any(m.startswith("Reparsing") for m in messages), messages
    assert any(m == "Reparsed raw XML into tree" for m in messages), messages
    assert QApplication.overrideCursor() is None


def test_reparse_parse_failure_restores_cursor_before_dialog(qtbot, tmp_path):
    """On a reparse failure the hourglass must be gone before the failure dialog
    appears -- no wait cursor sitting over a modal. Mirrors the file-open
    cursor-before-dialog contract for the editor -> tree reparse path."""
    window = MainWindow()
    qtbot.addWidget(window)
    _open(window, tmp_path)
    # Malformed XML in the editor so load_project_from_text raises.
    window.center_stage.xml_editor.setPlainText("<Project><Pages></Project>")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        mock_critical.side_effect = lambda *a, **k: (
            None if QApplication.overrideCursor() is None
            else (_ for _ in ()).throw(
                AssertionError("cursor not restored before dialog")
            )
        )
        window._reparse_raw_xml()

    mock_critical.assert_called_once()
    assert QApplication.overrideCursor() is None
