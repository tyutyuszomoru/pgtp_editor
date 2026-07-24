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


def test_format_size_zero_bytes():
    assert format_size(0) == "0 bytes"


def test_format_size_just_under_one_kb():
    # 1023 stays in the bytes branch; 1024 crosses into KB.
    assert format_size(1023) == "1023 bytes"


def test_format_size_exactly_one_kb():
    assert format_size(1024) == "1 KB"


def test_format_size_just_under_one_mb():
    # 1023 KB is the largest value still rendered as KB (kb < 1024).
    assert format_size(1023 * 1024) == "1023 KB"


def test_format_size_exactly_one_mb():
    assert format_size(1024 * 1024) == "1.0 MB"


def test_busy_status_message_is_sticky_no_timeout(qtbot):
    """The busy message must be shown WITHOUT a timeout (sticky) -- the caller
    owns the terminal timed message. A timeout arg here would let the in-progress
    text auto-clear mid-operation."""
    bar = QStatusBar()
    qtbot.addWidget(bar)
    calls = []
    bar.showMessage = lambda *a, **k: calls.append((a, k))

    with busy_status(bar, "Working…"):
        pass

    assert calls == [(("Working…",), {})]


def test_busy_status_balances_cursor_stack_when_nested(qtbot):
    """Each busy_status sets exactly one override cursor and restores exactly
    one, so nesting stays balanced: the inner exit leaves the outer override
    active, and the outer exit clears back to no override."""
    bar = QStatusBar()
    qtbot.addWidget(bar)
    assert QApplication.overrideCursor() is None

    with busy_status(bar, "Outer…"):
        with busy_status(bar, "Inner…"):
            assert QApplication.overrideCursor() is not None
        # Inner restored one level; the outer override is still active.
        assert QApplication.overrideCursor() is not None

    assert QApplication.overrideCursor() is None
