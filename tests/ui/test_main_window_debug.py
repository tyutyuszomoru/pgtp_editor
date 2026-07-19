"""Debug-mode UI surface: status chip, Help > Open Log Folder."""
import logging

from pgtp_editor.ui.main_window import MainWindow


def _help_action(window, text):
    for action in window.menuBar().actions():
        if action.text() == "Help":
            for sub in action.menu().actions():
                if sub.text() == text:
                    return sub
    return None


def test_no_debug_chip_by_default(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._debug_label is None


def test_debug_chip_when_path_given(qtbot, tmp_path):
    log = tmp_path / "debug_x.log"
    window = MainWindow(debug_log_path=log)
    qtbot.addWidget(window)
    assert window._debug_label is not None
    assert window._debug_label.text() == "DEBUG"


def test_open_log_folder_uses_opener_seam(qtbot, tmp_path, monkeypatch):
    opened = []
    window = MainWindow()
    qtbot.addWidget(window)
    window._open_log_folder(opener=lambda url: opened.append(url))
    assert len(opened) == 1


def test_help_menu_has_open_log_folder(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    action = _help_action(window, "Open Log Folder")
    assert action is not None


def test_open_project_file_logs_seam(qtbot, tmp_path, caplog):
    window = MainWindow()
    qtbot.addWidget(window)
    project = tmp_path / "p.pgtp"
    project.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><Project/>', encoding="utf-8"
    )
    with caplog.at_level(logging.INFO, logger="pgtp_editor.ui.main_window"):
        window.open_project_file(project)
    assert any("file: open" in r.message for r in caplog.records)


def test_save_logs_seam(qtbot, tmp_path, caplog):
    window = MainWindow()
    qtbot.addWidget(window)
    project = tmp_path / "p.pgtp"
    project.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><Project/>', encoding="utf-8"
    )
    window.open_project_file(project)
    with caplog.at_level(logging.INFO, logger="pgtp_editor.ui.main_window"):
        window._write_project_text(project)
    assert any("file: save" in r.message for r in caplog.records)
