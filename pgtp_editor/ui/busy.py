# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# pgtp_editor/ui/busy.py
"""Cosmetic "something is happening" indicator for blocking GUI operations.

`busy_status` shows a sticky status-bar message and a wait cursor, then forces
an immediate repaint BEFORE the blocking work runs so the user sees the app is
working rather than hung. It does NOT move work off the GUI thread -- the window
is still unresponsive to input during the operation (Approach C, cosmetic).

`processEvents(ExcludeUserInputEvents)` paints the pending message + cursor
without dispatching queued clicks/keys, so a double-triggered action cannot
re-enter the operation mid-flight. The cursor is always restored via `finally`.

Kept tiny and Qt-only, mirroring `ui/async_task.py`.
"""
from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication


def format_size(num_bytes: int) -> str:
    """Human-readable byte count: '500 bytes', '312 KB', '1.4 MB'."""
    if num_bytes < 1024:
        return f"{num_bytes} bytes"
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.0f} KB"
    return f"{kb / 1024:.1f} MB"


@contextmanager
def busy_status(status_bar, message: str):
    """Show `message` (sticky) + a wait cursor, painted immediately, for the
    duration of the wrapped block. Restores the cursor on exit, even on error.

    The caller is responsible for the terminal (done) message after the block.
    """
    status_bar.showMessage(message)
    QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
    try:
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        yield
    finally:
        QApplication.restoreOverrideCursor()
