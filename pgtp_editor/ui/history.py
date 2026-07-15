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
        self._snapshots = []  # list of (text, label), oldest -> newest
        self.current_index = -1

    def push(self, text, label=""):
        """Append a snapshot. No-op if ``text`` equals the current head's text
        (coalescing). Truncates any redo tail first, then enforces ``max_len``
        by dropping the oldest entries. Afterwards ``current_index`` points at
        the newly appended (last) entry."""
        if self._snapshots and self.current_index >= 0:
            if self._snapshots[self.current_index][0] == text:
                return
        # Drop any redo tail sitting after the cursor.
        if self.current_index < len(self._snapshots) - 1:
            del self._snapshots[self.current_index + 1 :]
        self._snapshots.append((text, label))
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
        """(index, label) for all snapshots, oldest -> newest."""
        return [(i, label) for i, (_text, label) in enumerate(self._snapshots)]

    def _texts(self):
        """Test seam: snapshot texts oldest -> newest."""
        return [text for text, _label in self._snapshots]
