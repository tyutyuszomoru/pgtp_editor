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

# pgtp_editor/ui/status_bar.py
"""`StaticStatusBar` — the status bar after FQ-028 Part 2.

The owner's rule, and the test for every decision here: *"the status bar needs
to avoid being a message board — it should have some well defined information
on it constantly."* A slot either always shows a defined fact, or it does not
belong in the bar. So the bar carries permanent widgets only:

* the **mode indicator** (major, plus minor when there is one),
* the **busy slot**, with a live elapsed-seconds counter,
* the two **connectivity dots**, present whenever a project is open,
* the DEBUG chip, when debug logging is on.

**The ~40 transient `showMessage` call sites did not move — the sink did.**
Rewriting forty call sites (plus `ui/busy.py` and the `_shell_status`
trampoline every collaborator writes through) would have left forty chances to
reintroduce a message-board write. Instead `showMessage` is overridden here: it
never paints, and hands the text to the Activity Log through the host's
`notice_sink`. A producer that wants to say something transient keeps saying
it; it simply lands in the journal, which is where FQ-028 routes it.

`currentMessage()` deliberately keeps returning the last such text. It is the
NOTICE that was emitted, not something on screen — `displayed_message()` is the
honest answer to "what does the bar actually paint", and it is always `""`.
Keeping `currentMessage()` meaningful is what lets a caller (and the suite's
~80 existing assertions) keep asking "did that gesture report anything?"
without asserting that the bar is a message board again.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QStatusBar

#: What the busy slot shows when nothing is running. Never blank: the slot is a
#: permanent element and states its fact.
IDLE_TEXT = "Idle"

#: How the busy slot renders a run in flight.
BUSY_FORMAT = "{message} {seconds}s"

#: The elapsed counter's tick, in milliseconds.
BUSY_TICK_MS = 1000


def busy_text(message: str, seconds: int) -> str:
    """The busy slot's text for `message` after `seconds` — pure, so the
    format is asserted without a clock."""
    return BUSY_FORMAT.format(message=str(message).rstrip("… "), seconds=int(seconds))


class BusySlot(QLabel):
    """The status bar's in-progress element: `Validating… 3s`, ticking.

    Re-entrant by depth, because a blocking gesture can nest another: the slot
    shows the OUTERMOST message and only returns to idle when the last one
    ends, so a nested operation cannot leave the bar claiming to be idle while
    the outer one still runs.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("busy_slot")
        self._depth = 0
        self._message = ""
        self._seconds = 0
        self._timer = QTimer(self)
        self._timer.setInterval(BUSY_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._render()

    @property
    def running(self) -> bool:
        return self._depth > 0

    def begin(self, message: str) -> None:
        self._depth += 1
        if self._depth == 1:
            self._message = str(message)
            self._seconds = 0
            self._timer.start()
            self._render()

    def end(self) -> None:
        if self._depth == 0:
            return
        self._depth -= 1
        if self._depth == 0:
            self._timer.stop()
            self._message = ""
            self._seconds = 0
            self._render()

    def _tick(self) -> None:
        self._seconds += 1
        self._render()

    def _render(self) -> None:
        self.setText(
            busy_text(self._message, self._seconds) if self._depth else IDLE_TEXT
        )


class StaticStatusBar(QStatusBar):
    """A status bar that shows permanent indicators and never scrolling text."""

    def __init__(self, parent=None, notice_sink: Callable[[str], None] | None = None):
        super().__init__(parent)
        self.notice_sink = notice_sink
        self._last_notice = ""
        self.busy_slot = BusySlot(self)
        self.addPermanentWidget(self.busy_slot)

    # -- the message-board seam, permanently closed --------------------------
    def showMessage(self, message: str, timeout: int = 0) -> None:  # noqa: N802
        """Journal `message` instead of painting it. `timeout` is accepted and
        ignored: a notice has no expiry once it is a log line."""
        self._last_notice = str(message)
        if self.notice_sink is not None and self._last_notice.strip():
            self.notice_sink(self._last_notice)

    def clearMessage(self) -> None:  # noqa: N802
        self._last_notice = ""

    def currentMessage(self) -> str:  # noqa: N802
        """The last notice emitted — NOT something on screen (see the module
        docstring); `displayed_message()` is that."""
        return self._last_notice

    def displayed_message(self) -> str:
        """What the bar's own message area actually paints. Always `""` —
        this is the assertion that the bar is not a message board."""
        return QStatusBar.currentMessage(self)

    # -- the busy slot, for `ui/busy.py` -------------------------------------
    def begin_busy(self, message: str) -> None:
        """Start the busy slot — and journal the message too.

        A long operation announcing itself ("Opening orders.pgtp (312 KB)…")
        is worth a log line as well as a slot: the slot answers "is something
        running right now", the journal answers "what ran". They are different
        questions, so the message serves both."""
        self.showMessage(message)
        self.busy_slot.begin(message)

    def end_busy(self) -> None:
        self.busy_slot.end()
