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

"""Document-level snapshot history for the Raw XML editor (Qt-free, pure).

A bounded list of committed XML-text snapshots with an undo/redo cursor,
independent of the editor's per-keystroke undo stack. See Sub-project C.
"""


class SnapshotHistory:
    """A capped, cursor-based history of text snapshots.

    ``current_index`` points at the "current" snapshot (-1 when empty). Undo
    moves the cursor toward older entries; redo toward newer. Pushing a new
    snapshot after undos discards the redo tail. The oldest entries are dropped
    once ``max_len`` is exceeded.
    """

    def __init__(self, max_len=10):
        self.max_len = max_len
        self._snapshots = []  # list of (text, label, baseline), oldest -> newest
        self.current_index = -1

    def clear(self):
        """Drop all snapshots (used when the document changes identity -- a new
        project is opened or the current one is closed -- so undo never crosses
        from one document into another)."""
        self._snapshots = []
        self.current_index = -1

    def push(self, text, label="", baseline=False):
        """Append a snapshot. No-op if ``text`` equals the current head's text
        (coalescing). Truncates any redo tail first, then enforces ``max_len``
        by dropping the oldest entries. Afterwards ``current_index`` points at
        the newly appended (last) entry.

        ``baseline=True`` marks a document-origin snapshot (the state produced by
        opening or reverting a file). Baselines are the floor that undo returns
        to, but they are NOT edits, so they are excluded from ``edit_entries``
        (the undo/redo jump list) -- you cannot "undo an open"."""
        if self._snapshots and self.current_index >= 0:
            if self._snapshots[self.current_index][0] == text:
                return
        # Drop any redo tail sitting after the cursor.
        if self.current_index < len(self._snapshots) - 1:
            del self._snapshots[self.current_index + 1 :]
        self._snapshots.append((text, label, baseline))
        # Enforce the cap by dropping the oldest.
        overflow = len(self._snapshots) - self.max_len
        if overflow > 0:
            del self._snapshots[:overflow]
        self.current_index = len(self._snapshots) - 1

    def can_undo(self):
        return self.current_index > 0

    def can_redo(self):
        return -1 <= self.current_index < len(self._snapshots) - 1

    def undo(self):
        if not self.can_undo():
            return None
        self.current_index -= 1
        return self._snapshots[self.current_index][0]

    def redo(self):
        if not self.can_redo():
            return None
        self.current_index += 1
        return self._snapshots[self.current_index][0]

    def jump_to(self, index):
        if not (0 <= index < len(self._snapshots)):
            return None
        self.current_index = index
        return self._snapshots[index][0]

    def entries(self):
        """(index, label) for all snapshots, oldest -> newest (incl. baselines)."""
        return [(i, label) for i, (_text, label, _base) in enumerate(self._snapshots)]

    def edit_entries(self):
        """(index, label) for non-baseline snapshots only, oldest -> newest.

        This is what the undo/redo jump list shows: actual edits, never the
        Open/Revert baseline (which is the floor undo returns to, not an item)."""
        return [
            (i, label)
            for i, (_text, label, base) in enumerate(self._snapshots)
            if not base
        ]

    def _texts(self):
        """Test seam: snapshot texts oldest -> newest."""
        return [text for text, _label, _base in self._snapshots]
