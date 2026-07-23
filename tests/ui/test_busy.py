from PySide6.QtWidgets import QApplication, QStatusBar

from pgtp_editor.ui.busy import busy_status, format_size


def test_format_size_bytes():
    assert format_size(500) == "500 bytes"


def test_format_size_kb():
    assert format_size(312 * 1024) == "312 KB"


def test_format_size_mb():
    # 1.4 MB exactly, avoiding a .5 rounding boundary
    assert format_size(int(1.4 * 1024 * 1024)) == "1.4 MB"


def test_busy_status_sets_message_and_cursor_then_restores(qtbot):
    bar = QStatusBar()
    qtbot.addWidget(bar)
    assert QApplication.overrideCursor() is None

    with busy_status(bar, "Working…"):
        assert bar.currentMessage() == "Working…"
        assert QApplication.overrideCursor() is not None

    assert QApplication.overrideCursor() is None


def test_busy_status_restores_cursor_on_exception(qtbot):
    bar = QStatusBar()
    qtbot.addWidget(bar)

    class Boom(Exception):
        pass

    try:
        with busy_status(bar, "Working…"):
            raise Boom()
    except Boom:
        pass

    assert QApplication.overrideCursor() is None
