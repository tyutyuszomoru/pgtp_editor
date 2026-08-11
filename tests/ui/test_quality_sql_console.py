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

# tests/ui/test_quality_sql_console.py
"""Tests for the **Quality SQL Console** — the second flavour of
`ui/sql_console_panel.py::SqlConsolePanel` (§18.5 D4b, `FQ-260811020328`).

The panel is the same class as the sandbox console, so everything the sandbox
tests already pin (splitting, completion, the reserved chords, the row cap)
holds here by construction and is not re-asserted. What IS asserted here is
everything the two consoles do **differently**:

* the explicit commit model (`DEC-260811023646`) — a Run leaves nothing durable,
  Commit does, Roll Back discards, and all three lifecycle edges are defined;
* `Ctrl+Return` runs but does **not** commit, and the commit gesture carries no
  shortcut — the safety property `DEC-260811025132` rests on;
* two consoles open at once, each chord firing only for its own tab;
* the danger marking, asserted in **rendered pixels** in both themes.

The connection is an injected fake, so nothing here opens one — but the
transaction bookkeeping is the real `QualitySession`, because "nothing is
committed yet" is exactly the property a stubbed session would fake away.
"""
from collections import Counter

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.quality_query import (
    DISCARD_TAB_CLOSED,
    DISCARD_WINDOW_CLOSED,
    QualityConnectionLost,
    QualitySession,
    run_quality_query,
)
from pgtp_editor.db.sandbox_query import RawResult
from pgtp_editor.ui.ddl_buffer_panel import danger_selection_colors
from pgtp_editor.ui.sql_console_panel import (
    COMMIT_EXPLICIT,
    COMMIT_LABEL,
    COMMIT_PER_STATEMENT,
    DANGER_BANNER_TEXT,
    NO_QUALITY_TARGET_TEXT,
    QUALITY_FLAVOUR,
    QUALITY_TAB_KEY,
    QUALITY_TAB_TITLE,
    ROLLBACK_LABEL,
    SANDBOX_FLAVOUR,
    ObjectChangeConfirmation,
    SqlConsolePanel,
    object_change_prompt,
)
from pgtp_editor.ui.theme import apply_theme

PARAMS = ConnectionParams(
    host="db01", port=5432, database="prod", user="app", password="s3cret"
)


def sync_run_async(fn, on_result, on_error=None, **_kwargs):
    """The suite's synchronous stand-in for `ui/async_task.py::run_async`."""
    try:
        value = fn()
    except BaseException as exc:  # noqa: BLE001 -- mirrors run_async's contract
        if on_error is not None:
            on_error(exc)
        return None
    on_result(value)
    return None


class FakeConnection:
    """A `db/quality_query.py::QualityConnection` that records everything."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.executed: list[str] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def execute(self, sql, *, max_rows, statement_timeout_ms):
        self.executed.append(sql)
        answer = self.answers.get(sql)
        if isinstance(answer, BaseException):
            raise answer
        if answer is not None:
            return answer
        return RawResult(columns=None, rows=(), affected=1, status="UPDATE 1")

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


class RecordingConfirm:
    """The object-change seam. Never a modal (§30)."""

    def __init__(self, *, confirmed=True, remember=False):
        self.answer = ObjectChangeConfirmation(confirmed=confirmed, remember=remember)
        self.prompts: list[tuple[str, str]] = []

    def __call__(self, title, text):
        self.prompts.append((title, text))
        return self.answer


class RecordingDiscardConfirm:
    """The *"discard the uncommitted run?"* seam — a plain `-> bool`, and its own
    seam precisely because the object-change dialog's "don't ask again" checkbox
    must never be offered for this question."""

    def __init__(self, answer=True):
        self.answer = answer
        self.prompts: list[tuple[str, str]] = []

    def __call__(self, title, text):
        self.prompts.append((title, text))
        return self.answer


def show_and_focus(qtbot, window, widget):
    """Show `window`, ACTIVATE it, and put focus in `widget`.

    All three steps are required for a `QShortcut` to fire under the offscreen
    platform, and the `wait` is too: without it the focus event has not been
    delivered when the key arrives, and the chord is silently answered by
    nothing. (Offscreen Qt does fire QShortcuts — the "offscreen is unreliable"
    folklore in this repo was about unshown widgets.)
    """
    window.show()
    qtbot.waitExposed(window)
    window.activateWindow()
    widget.setFocus()
    qtbot.wait(1)


def press_ctrl_return(qtbot, widget):
    qtbot.keyClick(
        widget, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
    )


def make_quality_console(qtbot, answers=None, *, confirm=None, discard=None,
                         register=True):
    connection = FakeConnection(answers)
    session = QualitySession(PARAMS, connector=lambda _p: connection)
    console = SqlConsolePanel(
        session_provider=lambda: session,
        run_query=run_quality_query,
        run_async=sync_run_async,
        confirm=confirm if confirm is not None else RecordingConfirm(),
        confirm_discard=discard if discard is not None else RecordingDiscardConfirm(),
        flavour=QUALITY_FLAVOUR,
    )
    if register:
        # Not registered when the caller re-parents it: pytest-qt closes every
        # registered widget, and closing the parent first deletes the child.
        qtbot.addWidget(console)
    return console, session, connection


# -- identity and composition ----------------------------------------------


def test_the_quality_console_is_its_own_tab_with_its_own_title(qtbot):
    console, _session, _connection = make_quality_console(qtbot)
    assert console.tab_key() == QUALITY_TAB_KEY
    assert console.tab_title() == QUALITY_TAB_TITLE
    assert console.tab_title() != SANDBOX_FLAVOUR.tab_title
    assert QUALITY_TAB_KEY != SANDBOX_FLAVOUR.tab_key


def test_the_two_flavours_declare_two_commit_models(qtbot):
    assert QUALITY_FLAVOUR.commit_model == COMMIT_EXPLICIT
    assert SANDBOX_FLAVOUR.commit_model == COMMIT_PER_STATEMENT
    assert QUALITY_FLAVOUR.explicit_commit is True
    assert SANDBOX_FLAVOUR.explicit_commit is False


def test_the_quality_console_carries_the_commit_row_and_the_danger_banner(qtbot):
    console, _session, _connection = make_quality_console(qtbot)
    assert console.commit_button is not None
    assert console.rollback_button is not None
    assert console.danger_banner is not None
    assert console.danger_banner.text() == DANGER_BANNER_TEXT
    # Nothing has run: neither gesture has a subject yet.
    assert console.commit_button.isEnabled() is False
    assert console.rollback_button.isEnabled() is False


def test_the_sandbox_console_grows_neither_of_them(qtbot):
    """The parameterization must not leak: a second "safe" colour and an
    inapplicable Commit button would each say something false (§18.7 trap 3)."""
    console = SqlConsolePanel(
        session_provider=lambda: object(),
        run_query=lambda *a, **k: None,
        run_async=sync_run_async,
        confirm=RecordingConfirm(),
    )
    qtbot.addWidget(console)
    assert console.commit_button is None
    assert console.rollback_button is None
    assert console.danger_banner is None
    assert console.pending_label is None


def test_with_no_quality_target_run_is_refused_with_a_stated_reason(qtbot):
    console = SqlConsolePanel(
        session_provider=lambda: None,
        run_query=run_quality_query,
        run_async=sync_run_async,
        confirm=RecordingConfirm(),
        confirm_discard=RecordingDiscardConfirm(),
        flavour=QUALITY_FLAVOUR,
    )
    qtbot.addWidget(console)
    console.editor.setPlainText("SELECT 1")
    console.run()
    assert console.results.status_label.text() == NO_QUALITY_TARGET_TEXT
    assert console.results.run_button.isEnabled() is False


# -- the commit model (DEC-260811023646) -----------------------------------


def test_a_run_commits_nothing_and_the_banner_says_so(qtbot):
    console, _session, connection = make_quality_console(qtbot)
    console.editor.setPlainText("UPDATE t SET x = 1;")

    console.run()

    assert connection.executed == ["UPDATE t SET x = 1"]
    assert connection.commits == 0
    assert console.has_uncommitted_run is True
    assert console.pending_statements() == 1
    banner = console.pending_label.text()
    assert "UNCOMMITTED" in banner
    assert "Commit" in banner
    assert console.pending_label.isVisibleTo(console) is True
    assert console.commit_button.isEnabled() is True
    assert console.rollback_button.isEnabled() is True


def test_the_commit_gesture_is_what_makes_it_durable(qtbot):
    console, _session, connection = make_quality_console(qtbot)
    outcomes = []
    console.transaction_finished.connect(outcomes.append)
    console.editor.setPlainText("UPDATE t SET x = 1;\nUPDATE u SET y = 2;")
    console.run()

    console.commit_run()

    assert connection.commits == 1
    assert outcomes and outcomes[-1].committed is True
    assert outcomes[-1].statements == 2
    assert "COMMITTED" in console.pending_label.text()
    assert console.has_uncommitted_run is False
    assert console.commit_button.isEnabled() is False
    assert console.rollback_button.isEnabled() is False


def test_the_rollback_gesture_discards_and_reaches_the_database_with_nothing(qtbot):
    console, _session, connection = make_quality_console(qtbot)
    console.editor.setPlainText("DELETE FROM t;")
    console.run()

    console.rollback_run()

    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert connection.closed == 0  # the console stays usable
    assert "Rolled back" in console.pending_label.text()
    assert console.has_uncommitted_run is False


def test_a_failed_run_is_rolled_back_at_once_and_never_reported_as_committed(qtbot):
    """The sandbox strip's *"N earlier statements already ran and COMMITTED"*
    would be false here — inside one transaction the server aborted, nothing was
    committed, and saying otherwise on production is the silently-wrong-result
    class this project refuses."""
    boom = RuntimeError("ERROR: boom")
    console, _session, connection = make_quality_console(
        qtbot, {"UPDATE b SET y = 2": boom}
    )
    console.editor.setPlainText("UPDATE a SET x = 1;\nUPDATE b SET y = 2;")

    console.run()

    assert connection.commits == 0
    assert connection.rollbacks == 1
    strip = console.results.status_label.text()
    assert "COMMITTED" not in strip
    assert "NOTHING was committed" in strip
    assert "NOTHING was committed" in console.pending_label.text()
    assert console.commit_button.isEnabled() is False


def test_connection_loss_disables_both_gestures_and_states_the_loss(qtbot):
    console, _session, connection = make_quality_console(
        qtbot, {"UPDATE b SET y = 2": QualityConnectionLost("gone")}
    )
    console.editor.setPlainText("UPDATE a SET x = 1;\nUPDATE b SET y = 2;")

    console.run()

    assert connection.closed == 1
    assert connection.commits == 0
    assert "lost" in console.pending_label.text()
    assert "NOTHING was committed" in console.pending_label.text()
    assert console.commit_button.isEnabled() is False
    assert console.rollback_button.isEnabled() is False
    assert console.has_uncommitted_run is False


# -- the three lifecycle edges --------------------------------------------


def test_closing_the_tab_with_an_uncommitted_run_asks_first(qtbot):
    discard = RecordingDiscardConfirm(answer=True)
    console, _session, connection = make_quality_console(qtbot, discard=discard)
    console.editor.setPlainText("DELETE FROM t;")
    console.run()

    assert console.request_close() is True

    assert discard.prompts, "the user must be asked before the run is discarded"
    title, text = discard.prompts[0]
    assert "Uncommitted" in title
    assert "NOT committed" in text
    assert "rolls the transaction back" in text
    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert connection.closed == 1, "the held connection must not outlive the tab"


def test_a_declined_close_vetoes_it_and_keeps_the_transaction(qtbot):
    discard = RecordingDiscardConfirm(answer=False)
    console, _session, connection = make_quality_console(qtbot, discard=discard)
    console.editor.setPlainText("DELETE FROM t;")
    console.run()

    assert console.request_close() is False

    assert connection.rollbacks == 0
    assert connection.closed == 0
    assert console.has_uncommitted_run is True


def test_the_window_close_edge_asks_about_the_window_and_closes_the_connection(qtbot):
    discard = RecordingDiscardConfirm(answer=True)
    console, _session, connection = make_quality_console(qtbot, discard=discard)
    console.editor.setPlainText("DELETE FROM t;")
    console.run()

    assert console.request_close(what="the window") is True

    _title, text = discard.prompts[0]
    assert "the window" in text
    assert connection.closed == 1
    assert connection.commits == 0


def test_closing_with_nothing_uncommitted_asks_nothing_but_still_closes(qtbot):
    """No question where there is nothing to lose — and still no leak: a console
    that ran and committed still holds an open connection."""
    discard = RecordingDiscardConfirm(answer=True)
    console, _session, connection = make_quality_console(qtbot, discard=discard)
    console.editor.setPlainText("DELETE FROM t;")
    console.run()
    console.commit_run()

    assert console.request_close() is True

    assert discard.prompts == []
    assert connection.closed == 1


def test_discard_pending_names_its_reason_and_reports_it(qtbot):
    console, _session, connection = make_quality_console(qtbot)
    console.editor.setPlainText("DELETE FROM t;")
    console.run()

    outcome = console.discard_pending(DISCARD_WINDOW_CLOSED)

    assert outcome.discarded is True
    assert outcome.reason == DISCARD_WINDOW_CLOSED
    assert connection.closed == 1


def test_the_sandbox_console_never_vetoes_a_close(qtbot):
    console = SqlConsolePanel(
        session_provider=lambda: object(),
        run_query=lambda *a, **k: None,
        run_async=sync_run_async,
        confirm=RecordingConfirm(),
    )
    qtbot.addWidget(console)
    assert console.request_close() is True
    assert console.pending_statements() == 0


# -- the keyboard (DEC-260811025132) ---------------------------------------


def test_ctrl_return_runs_but_does_not_commit(qtbot):
    """The safety property the ruling rests on, asserted directly: the chord is
    allowed to be one keystroke away precisely because the COMMIT is not."""
    console, _session, connection = make_quality_console(qtbot)
    console.editor.setPlainText("DELETE FROM t;")
    show_and_focus(qtbot, console, console.editor)

    press_ctrl_return(qtbot, console.editor)

    assert connection.executed == ["DELETE FROM t"]
    assert connection.commits == 0
    assert console.has_uncommitted_run is True


# -- the commit row, pressed as a real CLICK ---------------------------------
# Every transaction test above reaches `commit_run()` / `rollback_run()`
# directly. That is the wrong end of the gesture to pin on its own: the commit
# row is the ONLY way a user makes anything durable here (the chord is
# deliberately withheld), and both buttons are bound through an
# argument-dropping `lambda _checked=False:` — because `clicked(bool)` connected
# straight to a zero-argument slot is what killed the Edit Snippets buttons in
# BUG-260812001455. A suite that only calls the seams stays green while the one
# durable gesture in the app does nothing.


def test_the_commit_BUTTON_CLICK_is_what_reaches_the_database(qtbot):
    console, _session, connection = make_quality_console(qtbot)
    console.editor.setPlainText("UPDATE t SET x = 1;")
    console.run()
    assert console.has_uncommitted_run is True
    assert connection.commits == 0

    console.commit_button.click()

    assert connection.commits == 1
    assert console.has_uncommitted_run is False
    assert "COMMITTED" in console.pending_label.text()


def test_the_ROLLBACK_BUTTON_CLICK_discards_the_run(qtbot):
    console, _session, connection = make_quality_console(qtbot)
    console.editor.setPlainText("DELETE FROM t;")
    console.run()

    console.rollback_button.click()

    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert console.has_uncommitted_run is False


def test_a_DISABLED_commit_button_click_commits_NOTHING(qtbot):
    """The buttons start disabled and are re-disabled the moment a transaction
    ends, so "nothing pending" must be unreachable through the row rather than
    merely discouraged — a second Commit click must not reach the connection."""
    console, _session, connection = make_quality_console(qtbot)

    assert console.commit_button.isEnabled() is False
    console.commit_button.click()
    console.rollback_button.click()
    assert connection.commits == 0
    assert connection.rollbacks == 0

    console.editor.setPlainText("UPDATE t SET x = 1;")
    console.run()
    console.commit_button.click()
    assert connection.commits == 1

    console.commit_button.click()  # the double-press
    assert connection.commits == 1


def test_the_commit_gesture_has_no_keyboard_shortcut_of_any_kind(qtbot):
    """Do not add one, and do not let it inherit one — that is the whole basis of
    `DEC-260811025132`. A mnemonic (`&Commit`) and an auto-default button both
    count as one keystroke away, so both are excluded."""
    console, _session, _connection = make_quality_console(qtbot)

    for button in (console.commit_button, console.rollback_button):
        assert button.shortcut().isEmpty()
        assert "&" not in button.text()
        assert button.autoDefault() is False
        assert button.isDefault() is False
    assert console.commit_button.text() == COMMIT_LABEL
    assert console.rollback_button.text() == ROLLBACK_LABEL


def test_with_both_consoles_open_each_ctrl_return_hits_its_own_tab(qtbot):
    """`WidgetWithChildrenShortcut` is what makes two live consoles possible;
    `WindowShortcut` would make Qt fire NEITHER. Verified rather than assumed."""
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)

    sandbox_calls: list[str] = []
    sandbox = SqlConsolePanel(
        session_provider=lambda: object(),
        run_query=lambda _s, sql, **_k: sandbox_calls.append(sql),
        run_async=sync_run_async,
        confirm=RecordingConfirm(),
    )
    quality, _session, connection = make_quality_console(qtbot, register=False)
    layout.addWidget(sandbox)
    layout.addWidget(quality)
    sandbox.editor.setPlainText("SELECT 'sandbox';")
    quality.editor.setPlainText("SELECT 'quality';")
    show_and_focus(qtbot, host, quality.editor)

    press_ctrl_return(qtbot, quality.editor)
    assert connection.executed == ["SELECT 'quality'"]
    assert sandbox_calls == []

    sandbox.editor.setFocus()
    qtbot.wait(1)
    press_ctrl_return(qtbot, sandbox.editor)
    assert sandbox_calls == ["SELECT 'sandbox'"]
    assert connection.executed == ["SELECT 'quality'"]


# -- the object-change confirmation names the target ----------------------


def test_the_object_change_prompt_names_the_quality_database(qtbot):
    confirm = RecordingConfirm(confirmed=True)
    console, _session, _connection = make_quality_console(qtbot, confirm=confirm)
    console.editor.setPlainText("DROP TABLE t;")

    console.run()

    title, text = confirm.prompts[0]
    assert "QUALITY" in title
    assert "the quality database" in text
    assert "there is no Reset" in text
    assert "sandbox" not in text.lower()


def test_the_sandbox_prompt_is_unchanged():
    """D4's wording is the default, so the sandbox console cannot drift."""
    from pgtp_editor.sql.statements import split_statements

    statements = split_statements("DROP TABLE t;")
    text = object_change_prompt(statements, ["ddl"])
    assert "objects in the sandbox" in text
    assert "Run these statements against the sandbox?" in text
    quality = object_change_prompt(statements, ["ddl"], flavour=QUALITY_FLAVOUR)
    assert "Run these statements against the quality database?" in quality


# -- the danger marking, in PIXELS -----------------------------------------
#
# A per-widget `setPalette` is INERT under the app-level QSS
# (`BUG-260811021804`), and a stylesheet read-back proves only that a string was
# stored. Only rendered pixels are evidence.


def rendered(name: str) -> str:
    """A colour spelled the way `QImage.pixelColor().name()` spells it."""
    return QColor(name).name()


def pixel_counts(widget) -> Counter:
    image = widget.grab().toImage()
    counts: Counter = Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            counts[image.pixelColor(x, y).name()] += 1
    return counts


@pytest.fixture
def themed_quality_console(qtbot, qapp):
    def build(light: bool):
        apply_theme(qapp, light)
        console, session, connection = make_quality_console(qtbot)
        console.resize(760, 560)
        console.show()
        qapp.processEvents()
        return console, session, connection

    return build


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_danger_band_is_actually_painted(themed_quality_console, light):
    console, _session, _connection = themed_quality_console(light)
    band, _text = danger_selection_colors(light)
    assert pixel_counts(console.danger_banner)[rendered(band)] > 0


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_the_danger_band_survives_a_theme_flip(themed_quality_console, light, qapp):
    """`changeEvent` fires several times per flip and the first ones still report
    the OLD palette, so the marking must be re-derived from the live palette
    every time rather than stored."""
    console, _session, _connection = themed_quality_console(light)
    apply_theme(qapp, not light)
    qapp.processEvents()

    flipped_band, _text = danger_selection_colors(not light)
    stale_band, _stale = danger_selection_colors(light)
    counts = pixel_counts(console.danger_banner)
    assert counts[rendered(flipped_band)] > 0
    if rendered(stale_band) != rendered(flipped_band):
        assert counts[rendered(stale_band)] == 0
    # Restore, so a later test in this process is not read under a flipped theme.
    apply_theme(qapp, light)


def test_the_danger_colour_is_the_explorers_and_not_a_third_red(qtbot):
    """Reuse, not derivation: the console must read `danger_selection_colors`,
    which reads `mode_colors`' MODE_MAINTENANCE entry. No literal here."""
    from pgtp_editor.ui.mode_indicator import MODE_MAINTENANCE, mode_colors

    for light in (True, False):
        band, text = danger_selection_colors(light)
        chip_background, chip_foreground = mode_colors(light)[MODE_MAINTENANCE]
        assert (band, text) == (chip_foreground, chip_background)
