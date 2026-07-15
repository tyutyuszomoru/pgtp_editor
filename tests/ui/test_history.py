"""Sub-project C -- SnapshotHistory (pure, Qt-free) unit tests."""
from pgtp_editor.ui.history import SnapshotHistory


def test_empty_history():
    h = SnapshotHistory()
    assert h.current_index == -1
    assert h.can_undo() is False
    assert h.can_redo() is False
    assert h.undo() is None
    assert h.redo() is None
    assert h.entries() == []


def test_push_appends_and_points_at_last():
    h = SnapshotHistory()
    h.push("a", "one")
    assert h.current_index == 0
    h.push("b", "two")
    assert h.current_index == 1
    assert h.entries() == [(0, "one"), (1, "two")]


def test_coalesce_identical_head_text():
    h = SnapshotHistory()
    h.push("a", "one")
    h.push("a", "dup")  # same text as head -> no-op
    assert h.current_index == 0
    assert h.entries() == [(0, "one")]


def test_coalesce_only_against_head_not_older():
    h = SnapshotHistory()
    h.push("a")
    h.push("b")
    h.push("a")  # differs from head "b" -> pushed
    assert [t for _, t in _texts(h)] == ["a", "b", "a"]


def test_can_undo_redo_flags():
    h = SnapshotHistory()
    h.push("a")
    assert h.can_undo() is False  # only one entry
    assert h.can_redo() is False
    h.push("b")
    assert h.can_undo() is True
    assert h.can_redo() is False


def test_undo_returns_previous_text():
    h = SnapshotHistory()
    h.push("a")
    h.push("b")
    assert h.undo() == "a"
    assert h.current_index == 0
    assert h.can_redo() is True
    assert h.undo() is None  # at start
    assert h.current_index == 0


def test_redo_returns_forward_text():
    h = SnapshotHistory()
    h.push("a")
    h.push("b")
    h.undo()
    assert h.redo() == "b"
    assert h.current_index == 1
    assert h.redo() is None


def test_push_after_undo_truncates_redo_tail():
    h = SnapshotHistory()
    h.push("a")
    h.push("b")
    h.push("c")
    h.undo()  # index 1 (b)
    h.undo()  # index 0 (a)
    h.push("d")
    assert [t for _, t in _texts(h)] == ["a", "d"]
    assert h.current_index == 1
    assert h.can_redo() is False


def test_cap_drops_oldest():
    h = SnapshotHistory(max_len=3)
    h.push("a")
    h.push("b")
    h.push("c")
    h.push("d")  # drops "a"
    assert [t for _, t in _texts(h)] == ["b", "c", "d"]
    assert h.current_index == 2


def test_cap_adjusts_current_index_after_undo():
    h = SnapshotHistory(max_len=3)
    h.push("a")
    h.push("b")
    h.push("c")
    h.undo()  # index 1 (b)
    # pushing after undo truncates tail (drops c) then appends -> a,b,x
    h.push("x")
    assert [t for _, t in _texts(h)] == ["a", "b", "x"]
    assert h.current_index == 2


def test_jump_to_bounds_and_text():
    h = SnapshotHistory()
    h.push("a")
    h.push("b")
    h.push("c")
    assert h.jump_to(0) == "a"
    assert h.current_index == 0
    assert h.jump_to(2) == "c"
    assert h.current_index == 2
    # out of bounds -> None, index unchanged
    assert h.jump_to(99) is None
    assert h.current_index == 2
    assert h.jump_to(-5) is None
    assert h.current_index == 2


def test_entries_order_oldest_to_newest():
    h = SnapshotHistory()
    h.push("a", "L0")
    h.push("b", "L1")
    assert h.entries() == [(0, "L0"), (1, "L1")]


def _texts(h):
    """Test helper: (index, text) pairs oldest->newest."""
    return [(i, snap) for i, snap in enumerate(h._texts())]


def test_clear_empties_history():
    from pgtp_editor.ui.history import SnapshotHistory

    h = SnapshotHistory(10)
    h.push("a", "one")
    h.push("b", "two")
    h.clear()
    assert h.current_index == -1
    assert h.entries() == []
    assert h.can_undo() is False
    assert h.can_redo() is False
    # Usable again after clear.
    h.push("c", "fresh")
    assert h.entries() == [(0, "fresh")]
