# pgtp_editor/ui/activity_panel.py -> tests/ui/test_activity_panel.py
"""The Activity Log dock's widget (FQ-019).

The panel takes injected `ActivityEntry` data and never builds an `ActivityLog`,
so every test here is a widget plus two hand-built entries. Nothing calls
`.exec()` (§30): the click-through viewer is shown non-modally and asserted on
directly.

Note the owner's post-queue decision these tests pin: the timestamp format is
FIXED at `YYYY-MM-DD HH:MM` on every row -- the queue entry's dynamic
same-day/multi-day switch is dropped, so an entry from another day changes
nothing about the rows already shown.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from pgtp_editor.db.activity_log import (
    FILE_VERB_SAVED,
    SOURCE_PROJECT_FILES,
    SOURCE_QUALITY_FILES,
    SOURCE_SANDBOX_DB,
    ActivityEntry,
)
from pgtp_editor.ui.ddl_object_editor import (
    GESTURE_APPLY_TO_QUALITY,
    GESTURE_CHECK_AND_COMMIT,
    GESTURE_LABELS,
)
from pgtp_editor.ui.activity_panel import (
    EMPTY_TEXT,
    ENTRY_ROLE,
    ROW_TIME_FORMAT,
    VIEW_DDL,
    VIEW_ERROR,
    ActivityPanel,
)

LONG_DDL = (
    "CREATE OR REPLACE FUNCTION public.busy(a integer)\n"
    "RETURNS integer LANGUAGE plpgsql AS $$\nBEGIN\n  RETURN a;\nEND;\n$$;"
)
LONG_ERROR = (
    "ERROR: syntax error at or near \"RETRUN\"\nLINE 4:   RETRUN a;\n"
    "          ^\nCONTEXT: while compiling public.busy(integer)"
)


def ddl_entry(when=datetime(2026, 8, 8, 14, 3)) -> ActivityEntry:
    return ActivityEntry(
        timestamp=when,
        source=SOURCE_SANDBOX_DB,
        verb=GESTURE_LABELS[GESTURE_CHECK_AND_COMMIT],
        ddl_full=LONG_DDL,
    )


def file_entry(when=datetime(2026, 8, 8, 14, 5)) -> ActivityEntry:
    return ActivityEntry(
        timestamp=when,
        source=SOURCE_PROJECT_FILES,
        file_verb=FILE_VERB_SAVED,
    )


def failed_entry(when=datetime(2026, 8, 8, 14, 7)) -> ActivityEntry:
    return ActivityEntry(
        timestamp=when,
        source=SOURCE_SANDBOX_DB,
        verb=GESTURE_LABELS[GESTURE_APPLY_TO_QUALITY],
        ddl_full=LONG_DDL,
        status="error",
        error_full=LONG_ERROR,
    )


@pytest.fixture
def panel(qtbot):
    widget = ActivityPanel()
    qtbot.addWidget(widget)
    return widget


# --- rendering ---------------------------------------------------------------


def test_entries_render_in_file_order_oldest_first(panel):
    first, second, third = ddl_entry(), file_entry(), failed_entry()
    panel.set_entries([first, second, third])

    rows = panel.row_texts()
    assert len(rows) == 3
    assert rows[0].startswith("2026-08-08 14:03")
    assert rows[1].startswith("2026-08-08 14:05")
    assert rows[2].startswith("2026-08-08 14:07")
    assert FILE_VERB_SAVED in rows[1]
    # The panel shows the PREVIEW, never the full DDL.
    assert "CREATE OR REPLACE" in rows[0]
    assert "plpgsql" not in rows[0]
    assert len(panel.entries) == 3


def test_every_row_uses_the_one_fixed_timestamp_format(panel):
    """The owner's decision: `YYYY-MM-DD HH:MM` always, whatever the span."""
    assert ROW_TIME_FORMAT == "%Y-%m-%d %H:%M"
    panel.set_entries([ddl_entry(datetime(2026, 8, 8, 23, 59))])
    assert panel.row_texts()[0].startswith("2026-08-08 23:59")


def test_an_entry_from_another_day_leaves_the_existing_rows_untouched(panel):
    """With the dynamic format dropped, a post-midnight append is a pure append:
    the row already on screen must read exactly as it did before."""
    panel.set_entries([ddl_entry(datetime(2026, 8, 8, 23, 59))])
    before = panel.row_texts()

    panel.append(file_entry(datetime(2026, 8, 9, 0, 1)))

    rows = panel.row_texts()
    assert rows[0] == before[0]
    assert rows[1].startswith("2026-08-09 00:01")
    assert len(panel.entries) == 2


def test_the_row_payload_carries_its_stable_index(panel):
    panel.set_entries([ddl_entry(), file_entry()])
    assert [panel.list.item(i).data(ENTRY_ROLE) for i in range(2)] == [0, 1]
    assert panel.entry_at(panel.list.item(1)).file_verb == FILE_VERB_SAVED
    assert panel.entry_at(None) is None


def test_an_empty_log_renders_cleanly(panel):
    panel.set_entries([])
    assert panel.row_texts() == []
    assert panel.empty_label.isVisible() is not None  # constructed, not crashed
    assert panel.empty_label.text() == EMPTY_TEXT
    assert not panel.list.isVisible()

    panel.set_entries([ddl_entry()])
    panel.clear()
    assert panel.row_texts() == []
    assert panel.entries == ()


# --- failure and mode distinctions -------------------------------------------


def test_a_failed_entry_is_visually_distinguishable(panel):
    panel.set_entries([ddl_entry(), failed_entry()])
    ok_colour = panel.list.item(0).foreground().color()
    bad_colour = panel.list.item(1).foreground().color()
    assert bad_colour != ok_colour
    assert bad_colour.red() > bad_colour.green()
    # the error preview rides along on the row, truncated
    assert "ERROR: syntax error" in panel.row_texts()[1]
    assert "CONTEXT" not in panel.row_texts()[1]


def test_a_session_only_entry_is_marked(panel):
    panel.set_entries(
        [
            file_entry(),
            ActivityEntry(
                timestamp=datetime(2026, 8, 8, 14, 9),
                source=SOURCE_QUALITY_FILES,
                file_verb=FILE_VERB_SAVED,
            ),
        ]
    )
    assert not panel.list.item(0).font().italic()
    assert panel.list.item(1).font().italic()


# --- click routing to the full-text viewer -----------------------------------


def test_clicking_a_ddl_row_opens_a_read_only_viewer_with_the_full_text(panel):
    panel.set_entries([ddl_entry()])
    opened = []
    panel.viewer_opened.connect(opened.append)

    panel.list.itemClicked.emit(panel.list.item(0))

    assert len(opened) == 1
    viewer = opened[0]
    assert viewer.code() == LONG_DDL  # the FULL text, not the 20-char preview
    assert viewer._editor.isReadOnly()
    assert viewer.isVisible()
    viewer.close()


def test_clicking_a_failed_row_opens_the_full_error_and_the_ddl_stays_reachable(panel):
    panel.set_entries([failed_entry()])
    entry = panel.entries[0]

    assert panel.primary_viewer(entry) == VIEW_ERROR
    error_viewer = panel.open_viewer(entry, VIEW_ERROR)
    assert error_viewer.code() == LONG_ERROR
    assert error_viewer._editor.isReadOnly()

    # both payloads are offered by name, so a failed DDL row still reaches its
    # statement
    assert [kind for kind, _label in panel.viewer_actions(entry)] == [
        VIEW_DDL,
        VIEW_ERROR,
    ]
    ddl_viewer = panel.open_viewer(entry, VIEW_DDL)
    assert ddl_viewer.code() == LONG_DDL
    error_viewer.close()
    ddl_viewer.close()


def test_clicking_a_row_with_neither_ddl_nor_error_is_inert(panel):
    panel.set_entries([file_entry()])
    opened = []
    panel.viewer_opened.connect(opened.append)

    panel.list.itemClicked.emit(panel.list.item(0))

    assert opened == []
    assert panel.viewer_actions(panel.entries[0]) == []
    assert panel.primary_viewer(panel.entries[0]) is None
    assert panel.open_viewer(panel.entries[0], VIEW_DDL) is None
