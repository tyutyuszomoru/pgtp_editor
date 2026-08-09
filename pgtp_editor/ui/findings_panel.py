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

# pgtp_editor/ui/findings_panel.py
"""The two list surfaces the old "Audit / Problems" dock was split into
(FQ-028 Parts 1 and 3).

**ONE widget class, two instances** — the implementer's call, recorded here
because FQ-028 left it open. The left-dock **Findings** tab and the bottom-dock
**Results** tab differ in exactly one axis: what happens when a new run starts.
Everything else — the row shape, the `Qt.UserRole+N` payload convention, the
click that jumps into the centre editor — is identical, and duplicating a
`QListWidget` subclass to vary one boolean would have produced two surfaces
free to drift apart. The axis is the ``accumulate`` flag:

* ``accumulate=False`` (**Findings**, left dock): a new run WIPES the tab.
  Last-operation-wins across types — run Find-All then List Bookmarks and the
  bookmarks replace the finds, because both are "where do I want to go next"
  and only one such question is live at a time.
* ``accumulate=True`` (**Results**, bottom dock): a new run appends a
  **run separator** and keeps everything before it. Validation history is
  exactly what the owner asked to be saved across runs.

**Decoration rows.** The separator (a blank line, a timestamp header and a
40-character dashed rule) is furniture, not a finding. Each such row carries
``DECORATION_ROLE`` so the router's virtual view can exclude it: a caller that
counts findings must not count the rule that separates them, and a click on one
must not try to navigate anywhere.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

#: Tab titles. Named here so the panel, the host wiring and the tests spell
#: them once.
FINDINGS_TAB_TITLE = "Findings"
RESULTS_TAB_TITLE = "Results"

#: Marks a row as run-separator furniture rather than a finding.
DECORATION_ROLE = Qt.ItemDataRole.UserRole + 8

#: The run separator, EXACTLY as the owner specified it: a blank line, then a
#: header line, then a 40-character dashed rule.
RUN_RULE = "-" * 40

#: FQ-028 open question 2, decided: `HH:MM:SS` is appended to the owner's
#: literal `YYYY-MM-DD`, because a date alone cannot tell two runs of the same
#: check on the same day apart — which is the whole point of keeping history.
RUN_HEADER_FORMAT = "%Y-%m-%d %H:%M:%S"


def run_header(stamp: datetime | None = None) -> str:
    """The separator's header line for `stamp` (now by default)."""
    return (stamp or datetime.now()).strftime(RUN_HEADER_FORMAT)


class FindingsPanel(QListWidget):
    """A list of navigable findings.

    Rows are added with the plain `QListWidget` API (`addItem`), so every
    existing producer's `Qt.UserRole` line number and `UserRole+1` target keep
    working unchanged — FQ-028 explicitly preserves the click routing.
    """

    def __init__(self, parent=None, *, accumulate: bool = False) -> None:
        super().__init__(parent)
        #: Whether a new run appends (Results) or replaces (Findings).
        self.accumulate = bool(accumulate)

    # -- run lifecycle -------------------------------------------------------
    def begin_run(self, stamp: datetime | None = None) -> None:
        """Start a new run.

        Ephemeral panel: clears. Accumulating panel: writes the separator —
        and writes nothing at all when the panel is still empty, so the very
        first run does not open with a stray blank line.
        """
        if not self.accumulate:
            self.clear()
            return
        if self.count():
            self._add_decoration("")
        self._add_decoration(run_header(stamp))
        self._add_decoration(RUN_RULE)

    def _add_decoration(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setData(DECORATION_ROLE, True)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        super().addItem(item)

    # -- read-only surface ---------------------------------------------------
    def is_decoration(self, item) -> bool:
        """Whether `item` is separator furniture rather than a finding."""
        return bool(item is not None and item.data(DECORATION_ROLE))

    def finding_items(self) -> list[QListWidgetItem]:
        """Every non-decoration row, in order."""
        return [
            self.item(row)
            for row in range(self.count())
            if not self.is_decoration(self.item(row))
        ]

    def row_texts(self) -> list[str]:
        """Every row's text, decorations included — what the panel shows."""
        return [self.item(row).text() for row in range(self.count())]
