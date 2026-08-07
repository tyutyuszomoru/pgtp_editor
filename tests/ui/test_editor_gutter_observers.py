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
"""§8 — the shared gutter mixin's bookmark NOTIFICATIONS (FQ-013/FQ-014).

The mixin is a Qt-widget-level shared base and must stay ignorant of projects,
stores and docks: it publishes `(editor, reason)` and never interprets. These
tests pin that contract -- the three reasons, the fact that `restore_bookmarks`
is silent (it is the *answer* to a notification, not a new event), and the
lifetime rules that keep one gutter click from raising.
"""
import pytest

from pgtp_editor.ui import editor_gutter
from pgtp_editor.ui.code_editor import CodeEditor


@pytest.fixture
def events():
    """A subscribed recorder, always unsubscribed again: the registry is
    module-level, so a leaked observer would hear another test's editors."""
    recorded = []

    def observer(editor, reason):
        recorded.append(reason)

    editor_gutter.add_bookmark_observer(observer)
    try:
        yield recorded
    finally:
        # Only ever remove OUR observer: the registry is shared, and a window
        # built by another test in this process is legitimately subscribed to it.
        editor_gutter.remove_bookmark_observer(observer)


def test_a_toggle_publishes_the_toggled_reason(qtbot, events):
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb")
    events.clear()

    editor.toggle_bookmark(0)
    editor.toggle_bookmark(0)  # and again, removing it

    assert events == [editor_gutter.BOOKMARKS_TOGGLED] * 2


def test_clear_publishes_cleared_and_a_document_load_publishes_reset(qtbot, events):
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb")
    events.clear()

    editor.clear_bookmarks()
    editor.setPlainText("a\nb")

    assert events == [editor_gutter.BOOKMARKS_CLEARED, editor_gutter.BOOKMARKS_RESET]


def test_the_reset_is_published_with_the_new_document_already_in_place(qtbot):
    """An observer that restores a stored set must see the FINAL block count, or
    it would drop lines the new document does have."""
    seen = []

    def observer(editor, reason):
        seen.append((reason, editor.blockCount(), editor.bookmarked_lines()))

    editor_gutter.add_bookmark_observer(observer)
    try:
        editor = CodeEditor("sql")
        qtbot.addWidget(editor)
        editor.setPlainText("a\nb\nc\nd")
    finally:
        editor_gutter.remove_bookmark_observer(observer)

    assert seen[-1] == (editor_gutter.BOOKMARKS_RESET, 4, [])


def test_restore_bookmarks_is_silent_and_drops_out_of_range_lines(qtbot, events):
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc")
    events.clear()

    editor.restore_bookmarks([0, 2, 9, -1])

    assert editor.bookmarked_lines() == [0, 2]
    assert events == []  # the answer to a notification, never a new one


def test_registering_the_same_bound_method_twice_registers_it_once(qtbot):
    class Recorder:
        def __init__(self):
            self.count = 0

        def on_change(self, editor, reason):
            self.count += 1

    recorder = Recorder()
    editor_gutter.add_bookmark_observer(recorder.on_change)
    editor_gutter.add_bookmark_observer(recorder.on_change)
    try:
        editor = CodeEditor("sql")
        qtbot.addWidget(editor)
        editor.setPlainText("a")
        editor.toggle_bookmark(0)
    finally:
        editor_gutter.remove_bookmark_observer(recorder.on_change)

    assert recorder.count == 2  # one reset + one toggle, not four


def test_a_garbage_collected_observer_owner_is_dropped_not_raised(qtbot):
    """Bound methods are held weakly, so an observer never keeps its window
    alive -- and a notification after its owner died must not raise into the
    gutter click that produced it."""
    class Recorder:
        def on_change(self, editor, reason):
            raise AssertionError("must not be called after its owner is gone")

    recorder = Recorder()
    editor_gutter.add_bookmark_observer(recorder.on_change)
    registered = len(editor_gutter._bookmark_observers)
    del recorder

    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb")
    editor.toggle_bookmark(1)  # no raise

    assert len(editor_gutter._bookmark_observers) == registered - 1


def test_an_observer_whose_qt_object_is_gone_is_dropped(qtbot):
    """The stale-window case: a `RuntimeError` from a deleted C++ object drops
    the observer instead of failing a click. Any OTHER exception is a real bug
    and is deliberately not swallowed."""
    def dead(editor, reason):
        raise RuntimeError("wrapped C/C++ object has been deleted")

    editor_gutter.add_bookmark_observer(dead)
    try:
        editor = CodeEditor("sql")
        qtbot.addWidget(editor)
        editor.setPlainText("a\nb")
        assert dead not in editor_gutter._bookmark_observers
    finally:
        editor_gutter.remove_bookmark_observer(dead)


def test_a_real_bug_in_an_observer_is_not_swallowed(qtbot):
    def broken(editor, reason):
        raise ValueError("a real bug")

    editor_gutter.add_bookmark_observer(broken)
    try:
        editor = CodeEditor("sql")
        qtbot.addWidget(editor)
        with pytest.raises(ValueError):
            editor.setPlainText("a\nb")
    finally:
        editor_gutter.remove_bookmark_observer(broken)
