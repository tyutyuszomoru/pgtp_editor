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

# tests/ui/test_quality_console_wiring.py
"""MainWindow wiring for the Quality SQL Console (§18.5 D4b,
`FQ-260811020328`): the menu entry's availability, opening and single-instance
hosting, the window-close edge, and the target-vanished edge.

Nothing here opens a connection: the `QualitySession` is replaced with a fake
whose whole job is to record whether the window committed, discarded or leaked
it.
"""
import pytest
from PySide6.QtCore import QSettings

from pgtp_editor.db.activity_log import SOURCE_QUALITY_DB
from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.quality_query import (
    COMMITTED,
    DISCARDED,
    DISCARD_TARGET_GONE,
    DISCARD_WINDOW_CLOSED,
    TransactionOutcome,
)
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.sql_console_panel import (
    QUALITY_FLAVOUR,
    QUALITY_TAB_TITLE,
    SqlConsolePanel,
)

from ._sandbox_stubs import sync_run

TARGET = ConnectionParams(
    host="db01", port="5432", database="prod", user="app", password="s3cret"
)
TARGET_NO_PASSWORD = ConnectionParams(
    host="db01", port="5432", database="prod", user="app", password=""
)


def _window(qtbot, tmp_path):
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    window._run_async = sync_run
    return window


class FakeSession:
    """A `QualitySession` stand-in: records what the window did to it."""

    def __init__(self, pending=0):
        self.statements_pending = pending
        self.is_lost = False
        self.transaction_aborted = False
        self.closed: list[str] = []
        self.discarded: list[str] = []

    def close(self, reason):
        self.closed.append(reason)
        pending, self.statements_pending = self.statements_pending, 0
        return TransactionOutcome(DISCARDED, statements=pending, reason=reason)

    def discard(self, reason):
        self.discarded.append(reason)
        pending, self.statements_pending = self.statements_pending, 0
        return TransactionOutcome(DISCARDED, statements=pending, reason=reason)


def _with_target(window, params=TARGET):
    """Give the window a resolvable quality target with a password, without a
    project and without touching the password prompt."""
    window.active_target_params = lambda tree=None: params
    window._target_params_for_apply = lambda: (params if params.password else None)
    return window


# -- availability (§26: absent, not disabled, until reachable) --------------


def test_the_menu_entry_is_absent_with_no_quality_target(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._refresh_quality_console_affordances()
    assert window._quality_console_action is not None
    assert window._quality_console_action.isVisible() is False
    assert window._quality_console_available() is False


def test_the_menu_entry_appears_once_a_quality_target_resolves(qtbot, tmp_path):
    window = _with_target(_window(qtbot, tmp_path))
    window._refresh_quality_console_affordances()
    assert window._quality_console_available() is True
    assert window._quality_console_action.isVisible() is True


def test_the_menu_entry_carries_no_shortcut(qtbot, tmp_path):
    """Exactly like the sandbox open action. If a chord is ever wanted here it is
    an owner decision, not something to invent."""
    window = _window(qtbot, tmp_path)
    assert window._quality_console_action.shortcut().isEmpty()
    assert window._sandbox_console_action.shortcut().isEmpty()


def test_opening_without_a_password_creates_nothing_and_says_so(qtbot, tmp_path):
    """The ruling is *"available whenever a quality connection WITH A PASSWORD
    exists"*; the password question is answered at the gesture (like the Apply
    leg), and a declined answer must leave no console behind."""
    window = _with_target(_window(qtbot, tmp_path), TARGET_NO_PASSWORD)

    assert window._open_quality_sql_console() is None
    assert window.center_stage.quality_sql_tab() is None
    assert "password" in window.statusBar().currentMessage()


def test_opening_with_no_target_at_all_creates_nothing_and_says_so(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._open_quality_sql_console() is None
    assert window.center_stage.quality_sql_tab() is None
    assert "connection" in window.statusBar().currentMessage()


# -- opening and hosting ---------------------------------------------------


def test_opening_hosts_one_quality_console_with_the_quality_flavour(qtbot, tmp_path):
    window = _with_target(_window(qtbot, tmp_path))

    panel = window._open_quality_sql_console()

    assert isinstance(panel, SqlConsolePanel)
    assert panel.flavour is QUALITY_FLAVOUR
    assert window.center_stage.quality_sql_tab() is panel
    index = window.center_stage.indexOf(panel)
    assert window.center_stage.tabText(index) == QUALITY_TAB_TITLE


def test_re_invoking_the_command_focuses_the_same_console(qtbot, tmp_path):
    window = _with_target(_window(qtbot, tmp_path))
    first = window._open_quality_sql_console()
    second = window._open_quality_sql_console()
    assert second is first
    assert window.center_stage.count() == window.center_stage.indexOf(first) + 1


def test_the_window_holds_one_quality_session_across_runs(qtbot, tmp_path):
    """A second session would be a second transaction nobody can see."""
    window = _with_target(_window(qtbot, tmp_path))
    first = window._quality_session_provider()
    second = window._quality_session_provider()
    assert first is second
    assert first.params == TARGET


def test_a_lost_session_is_replaced_rather_than_handed_out_again(qtbot, tmp_path):
    window = _with_target(_window(qtbot, tmp_path))
    first = window._quality_session_provider()
    first._lost = True
    second = window._quality_session_provider()
    assert second is not first
    assert second.is_lost is False


def test_both_consoles_can_be_open_at_once(qtbot, tmp_path):
    """The two tabs are two keys in the same map, so neither displaces the
    other -- which is what the danger marking and the chord scoping assume."""
    window = _with_target(_window(qtbot, tmp_path))
    sandbox = window.center_stage.open_sandbox_sql_tab(
        session_provider=lambda: object()
    )
    quality = window._open_quality_sql_console()
    assert sandbox is not quality
    assert window.center_stage.sandbox_sql_tab() is sandbox
    assert window.center_stage.quality_sql_tab() is quality


# -- the window-close edge -------------------------------------------------


def test_closing_the_window_asks_about_an_uncommitted_run_and_can_be_declined(
    qtbot, tmp_path
):
    window = _with_target(_window(qtbot, tmp_path))
    panel = window._open_quality_sql_console()
    panel._pending_session = FakeSession(pending=2)
    asked: list[tuple] = []
    panel._confirm_discard = lambda title, text: (asked.append((title, text)), False)[1]

    assert window._confirm_close_quality_console() is False
    assert asked, "the window must not close over an uncommitted run silently"


def test_closing_the_window_discards_the_run_naming_the_window(qtbot, tmp_path):
    window = _with_target(_window(qtbot, tmp_path))
    panel = window._open_quality_sql_console()
    session = FakeSession(pending=1)
    panel._pending_session = session
    panel._confirm_discard = lambda _title, _text: True

    assert window._confirm_close_quality_console() is True
    assert session.closed == [DISCARD_WINDOW_CLOSED]


def test_the_held_session_is_released_when_the_window_closes(qtbot, tmp_path):
    """Belt and braces: a console opened and never run still holds no
    transaction, but the session must not survive the window either."""
    window = _with_target(_window(qtbot, tmp_path))
    window._open_quality_sql_console()
    session = FakeSession(pending=0)
    window._quality_session = session

    window.close()

    assert session.closed == [DISCARD_WINDOW_CLOSED]
    assert window._quality_session is None


def test_with_no_quality_console_open_the_close_is_unaffected(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._confirm_close_quality_console() is True


# -- the target-vanished edge ---------------------------------------------


def test_a_target_that_stops_resolving_closes_the_console_and_states_the_discard(
    qtbot, tmp_path
):
    window = _with_target(_window(qtbot, tmp_path))
    panel = window._open_quality_sql_console()
    session = FakeSession(pending=3)
    panel._pending_session = session
    window._quality_session = session

    _with_target(window, TARGET_NO_PASSWORD)
    window.active_target_params = lambda tree=None: ConnectionParams()
    window._refresh_quality_console_affordances()

    assert window.center_stage.quality_sql_tab() is None
    assert window._quality_console_action.isVisible() is False
    assert DISCARD_TARGET_GONE in session.closed
    assert DISCARD_TARGET_GONE in window.statusBar().currentMessage()


# -- the journal ----------------------------------------------------------


def test_only_a_committed_transaction_is_journalled_as_a_quality_db_run(
    qtbot, tmp_path
):
    """Under the explicit commit model a Run has changed nothing durable yet, so
    journalling it as a `Quality DB` action would assert something untrue. (The
    status-bar sentence is still journalled as a notice — `StaticStatusBar` is a
    journal sink — which is the "never silently" half.)"""
    window = _with_target(_window(qtbot, tmp_path))
    recorded: list[tuple] = []
    window.record_activity = lambda *args, **kwargs: recorded.append((args, kwargs))
    window._quality_run_sql = "DELETE FROM t"

    def db_runs():
        return [
            call for call in recorded
            if call[0][:1] == (SOURCE_QUALITY_DB,) and "ddl" in call[1]
        ]

    window._record_quality_transaction(
        TransactionOutcome(DISCARDED, statements=1, reason="you rolled it back")
    )
    assert db_runs() == []

    window._record_quality_transaction(TransactionOutcome(COMMITTED, statements=1))
    assert len(db_runs()) == 1
    assert db_runs()[0][1]["ddl"] == "DELETE FROM t"


def test_every_outcome_is_stated_in_the_status_bar(qtbot, tmp_path):
    window = _with_target(_window(qtbot, tmp_path))
    window._record_quality_transaction(
        TransactionOutcome(DISCARDED, statements=2, reason="you rolled it back")
    )
    assert "Rolled back" in window.statusBar().currentMessage()


@pytest.mark.parametrize("committed", [True, False])
def test_the_run_sql_is_remembered_for_the_commit(qtbot, tmp_path, committed):
    window = _with_target(_window(qtbot, tmp_path))

    class Result:
        sql = "UPDATE t SET x = 1"

    class Run:
        result = Result()

    class Report:
        runs = (Run(),)

    window._remember_quality_run(Report())
    assert window._quality_run_sql == "UPDATE t SET x = 1"
