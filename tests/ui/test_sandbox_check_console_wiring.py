# tests/ui/test_sandbox_check_console_wiring.py
"""MainWindow's half of §18.5 D3a (the two Audit channels of a Check run) and
D4 (the Sandbox SQL Console + the "Run in Sandbox Console" bridge).

D3a: findings travel as OBJECTS on `check_findings` and only MainWindow can
render them clickable, so these tests pin the roles precisely -- a finding with
a line carries both `UserRole` (the line) and `UserRole+1` (the object's
`DdlObjectRef.key`), a `line is None` finding carries NEITHER (inert, never an
accidental Raw-XML navigation), and the narrative `check_reported` channel
carries no roles at all.

D4: no console TAB and no bridge button exists without a live session (the menu
ENTRY is present-and-reporting once a sandbox is configured -- FQ-023's narrowing
of carve-out 2, pinned in the last section of this module); the bridge copies
text and executes nothing; and there is no "run against target" affordance
anywhere in the Database menu.
"""
import pytest
from PySide6.QtCore import QSettings, Qt

from pgtp_editor.db.ddl_check import CheckRequest
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.introspect import TriggerInfo
from pgtp_editor.ui.ddl_object_editor import CHECK_PREFIX, DdlObjectRef
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui import modals
from tests.ui._menu_helpers import find_action, find_top_menu


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)



@pytest.fixture(autouse=True)
def comparison_modals(monkeypatch):
    """§30 guard for FQ-026's new modal.

    `Check Object in Sandbox` now ends in a one-line `QMessageBox.information`
    stating whether the buffer matches what the sandbox holds, so every test
    that runs the gesture would otherwise reach an un-patched modal. Patched
    through the `ui/modals.py` seam (never through `main_window`'s namespace),
    and RECORDING rather than silencing: the tests that are about the answer
    read `(title, text)` straight out of this list.
    """
    seen: list[tuple] = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "information",
        staticmethod(lambda *args, **kwargs: seen.append(tuple(args[1:3]))),
    )
    return seen


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    return window


_REF = DdlObjectRef(kind="function", schema="pr", name="recalc")
_SOURCE = "CREATE FUNCTION pr.recalc()\nRETURNS void AS $$\nBEGIN\nEND\n$$;\n"


class _Finding:
    """Duck-typed `db/ddl_check.py::CheckFinding` (attribute reads only)."""

    def __init__(self, severity, message, lineno=None, line=None, source_lineno=None):
        self.severity = severity
        self.message = message
        self.lineno = lineno
        self.line = line
        self.source_lineno = source_lineno


def _audit_texts(window):
    """The findings rows -- `[Check]` -- as the Results tab holds them."""
    panel = window.audit_panel
    return [panel.item(i).text() for i in range(panel.count())]


def _activity_texts(window):
    """The journalled rows -- `[SQL]` refusals, which FQ-028 routes to the
    Activity Log rather than to a findings surface."""
    return window.activity_panel.row_texts()


def _audit_items(window):
    panel = window.audit_panel
    return [panel.item(i) for i in range(panel.count())]


class _StubSession:
    """Stands in for a `SandboxSession` -- the provider's return value is only
    ever tested for None-ness by MainWindow."""

    params = None


# --- D3a: the narrative channel ------------------------------------------


def test_narrative_lines_are_appended_verbatim_and_carry_no_roles(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._report_check_lines([f"{CHECK_PREFIX}tier1: passed", f"{CHECK_PREFIX}  caveat: x"])

    assert _audit_texts(window) == [
        f"{CHECK_PREFIX}tier1: passed",
        f"{CHECK_PREFIX}  caveat: x",
    ]
    for item in _audit_items(window):
        assert item.data(Qt.ItemDataRole.UserRole) is None
        assert item.data(Qt.ItemDataRole.UserRole + 1) is None


def test_panel_check_reported_reaches_the_narrative_channel(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)

    panel.check_reported.emit([f"{CHECK_PREFIX}tier2: passed"])

    assert _audit_texts(window) == [f"{CHECK_PREFIX}tier2: passed"]


# --- D3a: the clickable channel ------------------------------------------


def test_finding_with_a_line_carries_both_roles(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._report_check_findings([_Finding("error", "syntax error", lineno=3)], _REF)

    item = _audit_items(window)[0]
    assert item.text() == f"{CHECK_PREFIX}ERROR line 3: syntax error"
    assert item.data(Qt.ItemDataRole.UserRole) == 3
    assert item.data(Qt.ItemDataRole.UserRole + 1) == _REF.key


def test_finding_without_a_line_carries_neither_role(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._report_check_findings([_Finding("warning", "unmappable")], _REF)

    item = _audit_items(window)[0]
    assert item.text() == f"{CHECK_PREFIX}WARNING: unmappable"
    assert item.data(Qt.ItemDataRole.UserRole) is None
    assert item.data(Qt.ItemDataRole.UserRole + 1) is None


def test_lineno_wins_over_line_and_source_lineno_is_never_read(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._report_check_findings(
        [_Finding("error", "m", lineno=7, line=99, source_lineno=2)], _REF
    )

    assert _audit_items(window)[0].data(Qt.ItemDataRole.UserRole) == 7


def test_line_is_read_when_lineno_is_absent(qtbot, tmp_path):
    """A `(severity, line, message)` test stub carries `line`, not `lineno`."""
    window = _window(qtbot, tmp_path)

    window._report_check_findings([_Finding("warning", "m", line=5)], _REF)

    assert _audit_items(window)[0].text() == f"{CHECK_PREFIX}WARNING line 5: m"


def test_notice_severity_renders_as_info(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._report_check_findings([_Finding("notice", "compat", lineno=1)], _REF)

    assert _audit_items(window)[0].text().startswith(f"{CHECK_PREFIX}INFO line 1:")


def test_unknown_severity_renders_warning_never_info(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._report_check_findings([_Finding("hilarious", "future level", lineno=2)], _REF)

    assert _audit_items(window)[0].text() == (
        f"{CHECK_PREFIX}WARNING line 2: future level"
    )


def test_panel_check_findings_reaches_the_clickable_channel_with_its_own_ref(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)

    panel.check_findings.emit([_Finding("error", "boom", lineno=2)])

    item = _audit_items(window)[0]
    assert item.data(Qt.ItemDataRole.UserRole + 1) == _REF.key


# --- D3a: click-to-navigate ---------------------------------------------


def test_clicking_a_finding_focuses_the_tab_and_moves_the_caret(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    window._report_check_findings([_Finding("error", "boom", lineno=3)], _REF)

    window._on_audit_item_clicked(_audit_items(window)[0])

    assert window.center_stage.currentWidget() is panel
    assert panel.editor.textCursor().blockNumber() == 2  # 0-based -> line 3


def test_clicking_a_lineless_finding_does_not_switch_tabs(qtbot, tmp_path):
    """Catches an accidental Raw-XML fallthrough: with neither role set the
    click is a no-op, not a navigation into a different document."""
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    before = window.center_stage.currentIndex()
    window._report_check_findings([_Finding("error", "no line")], _REF)

    window._on_audit_item_clicked(_audit_items(window)[0])

    assert window.center_stage.currentIndex() == before


def test_clicking_a_finding_whose_tab_was_closed_does_nothing(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    window._report_check_findings([_Finding("error", "boom", lineno=3)], _REF)
    window.center_stage.close_ddl_object_tab(_REF.key)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    before = window.center_stage.currentIndex()

    window._on_audit_item_clicked(_audit_items(window)[0])

    assert window.center_stage.currentIndex() == before
    assert window.center_stage.ddl_object_tab(_REF.key) is None


def test_navigation_resolves_a_checked_out_tab(qtbot, tmp_path):
    """A checked-out object's tab is keyed on `ref.key` like every other one
    (FQ-024 -- it used to be keyed on its `ddl/*.sql` path), and the
    `panel.ref.key` identity scan resolves it either way."""
    project_dir = tmp_path / "proj"
    save_settings(project_dir, ProjectSettings())
    window = _window(qtbot, tmp_path)
    window._ddl_project_ui.set_active_project(project_dir, ProjectSettings())

    window._edit_ddl_checked_out(_REF, _SOURCE)

    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel is not None
    assert window.center_stage.ddl_object_panels() == [panel]
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    window._report_check_findings([_Finding("error", "boom", lineno=3)], _REF)

    window._on_audit_item_clicked(_audit_items(window)[0])

    assert window.center_stage.currentWidget() is panel
    assert panel.editor.textCursor().blockNumber() == 2


# --- D4: the console command ---------------------------------------------


def test_with_no_provider_the_action_is_hidden_and_the_command_creates_nothing(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)

    # The provider is the controller's session accessor (stage 2), which has no
    # session until one is deliberately opened -- so the console is absent.
    assert window._sandbox_session_provider() is None
    assert not window._sandbox_console_action.isVisible()
    assert window._open_sandbox_sql_console() is None
    assert window.center_stage.sandbox_sql_tab() is None


def test_no_database_menu_action_mentions_target(qtbot, tmp_path):
    """§18.5 D4's safety boundary: no "run against target" affordance
    anywhere, not even a disabled one."""
    window = _window(qtbot, tmp_path)
    menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "Database"
    )

    for action in menu.actions():
        assert "target" not in action.text().lower()


def test_console_command_opens_exactly_one_tab_and_reinvoking_focuses_it(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    window._sandbox_session_provider = lambda: _StubSession()

    first = window._open_sandbox_sql_console()
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    second = window._open_sandbox_sql_console()

    assert second is first
    assert window.center_stage.sandbox_sql_tab() is first
    assert window.center_stage.currentWidget() is first


def test_refresh_shows_the_action_once_a_session_exists(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._sandbox_session_provider = lambda: _StubSession()

    window._refresh_sandbox_console_affordances()

    assert window._sandbox_console_action.isVisible()


def test_bridge_puts_text_in_the_console_focuses_it_and_runs_nothing(qtbot, tmp_path):
    """End-to-end: object tab selection -> console text + focus, with a stub
    `run_query` that must NEVER be called (one execution surface, and pressing
    Run is the user's act -- not the bridge's)."""
    calls = []
    window = _window(qtbot, tmp_path)
    window._sandbox_session_provider = lambda: _StubSession()
    # Pre-open the single-instance console with an execution stub wired in, so
    # the bridge's reuse of it can be observed to execute nothing.
    console = window.center_stage.open_sandbox_sql_tab(
        session_provider=window._sandbox_session_provider,
        run_query=lambda *a, **k: calls.append(a) or None,
    )
    window._on_ddl_edit_requested(_REF, _SOURCE)
    window._refresh_sandbox_console_affordances()
    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel.has_run_in_console

    focused = []
    console.focus_editor = lambda: focused.append(True)

    panel.editor.selectAll()
    assert panel.run_in_sandbox_console() is True

    assert window.center_stage.sandbox_sql_tab() is console
    assert _SOURCE.strip() in console.sql_text
    assert window.center_stage.currentWidget() is console
    # `hasFocus()` is unusable under the offscreen platform (no window is ever
    # activated), so the request itself is what is asserted.
    assert focused
    assert calls == []  # nothing executed
    assert console.result is None


def test_bridge_appends_rather_than_replaces(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._sandbox_session_provider = lambda: _StubSession()

    window._run_selection_in_sandbox_console("SELECT 1;")
    window._run_selection_in_sandbox_console("SELECT 2;")

    text = window.center_stage.sandbox_sql_tab().sql_text
    assert "SELECT 1;" in text and "SELECT 2;" in text


def test_a_dying_session_hides_the_action_closes_the_console_and_unwires_bridges(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    window._sandbox_session_provider = lambda: _StubSession()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    window._refresh_sandbox_console_affordances()
    window._open_sandbox_sql_console()
    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel.has_run_in_console

    window._sandbox_session_provider = lambda: None
    window._refresh_sandbox_console_affordances()

    assert not window._sandbox_console_action.isVisible()
    assert window.center_stage.sandbox_sql_tab() is None
    assert not panel.has_run_in_console


def test_bridge_is_absent_on_a_tab_opened_without_a_session(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, _SOURCE)

    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert not panel.has_run_in_console


def test_console_receives_the_schema_index(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._sandbox_session_provider = lambda: _StubSession()
    sentinel = object()
    window._ddl_schema_index = sentinel

    console = window._open_sandbox_sql_console()

    assert console.schema_index() is sentinel


def test_console_format_refusals_reach_the_sql_audit_channel(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._sandbox_session_provider = lambda: _StubSession()
    console = window._open_sandbox_sql_console()

    class _Issue:
        start_line = 4
        message = "unbalanced dollar quote"

    console.format_refused.emit([_Issue()])

    assert any(
        "[SQL] line 4: unbalanced dollar quote" in t for t in _activity_texts(window)
    )


# --- Stage 2: the SandboxController that makes any of this reachable -------


def _sync_run(fn, on_result, on_error=None):
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


class _FakeSession:
    """Minimal `SandboxSession` stand-in: records what was applied.

    Carries `executor` because the ladder's `CheckSession` protocol wants it --
    it is never used here, since every test replaces the ladder seam itself.
    """

    def __init__(self, database="pgtp_sandbox_x"):
        from pgtp_editor.db.config import ConnectionParams

        self.params = ConnectionParams(host="localhost", database=database)
        self.executor = None
        self.applied_calls = []

    def apply(self, ref, ddl_text):
        self.applied_calls.append((ref, ddl_text))


def _green_report(committed=True):
    """A four-tier all-passed `CheckReport`, as `apply_and_check` produces for a
    body that compiled and linted clean."""
    from pgtp_editor.db.ddl_check import CheckReport, TierOutcome

    passed = TierOutcome(status="passed", reason="")
    return CheckReport(
        tier0=passed, tier1=passed, tier2=passed, tier3=passed, committed=committed
    )


def _stub_ladder(controller, report=None, *, probe_report=None, raises=None):
    """Replace the controller's `apply_and_check` / `probe_check` seams with
    recorders, so an apply exercises the whole `run_apply` path without a server.

    Returns `(apply_calls, probe_calls)`; each entry is
    `(session, request, caps, ddl_text)`.
    """
    apply_calls = []
    probe_calls = []

    def applier(session, request, caps, *, ddl_text=None):
        apply_calls.append((session, request, caps, ddl_text))
        if raises is not None:
            raise raises
        return report if report is not None else _green_report()

    def prober(session, request, caps, *, ddl_text=None):
        probe_calls.append((session, request, caps, ddl_text))
        if raises is not None:
            raise raises
        return probe_report if probe_report is not None else _green_report(committed=False)

    controller._applier = applier
    controller._probe_checker = prober
    return apply_calls, probe_calls


class _RecordingOpener:
    """The controller's `_opener` seam as an object, so a test can both COUNT
    the opens (BUG-040's auto-open must not fire twice) and flip the sandbox
    between reachable and not without rebuilding the window."""

    def __init__(self, session, reachable=True):
        self.session = session
        self.reachable = reachable
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if not self.reachable:
            raise RuntimeError("could not connect to the sandbox")
        return self.session


def _project_window(
    qtbot, tmp_path, monkeypatch, sandbox_host="localhost", reachable=True
):
    """A window with an open project whose sandbox is configured, the
    controller's async made synchronous, and its opener/prober stubbed so no
    real connection is ever attempted.

    **Opening the project OPENS THE SESSION** (BUG-040), so with the default
    `reachable=True` the returned controller already holds `session`. Pass
    `reachable=False` for the sessionless states that used to be the default:
    since the manual `Open Sandbox Session` gesture is gone, the only way to sit
    in a configured-but-sessionless project is an auto-open that FAILED. The
    opener is a `_RecordingOpener`, so a test can flip `.reachable` back on and
    read `.calls`.
    """
    from pgtp_editor.db.config import ConnectionParams
    from pgtp_editor.db.sandbox import SandboxCapabilities

    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        sandbox=ConnectionParams(host=sandbox_host, database="pgtp_sandbox_x")
    )
    save_settings(project_dir, settings)
    window = _window(qtbot, tmp_path)
    window._run_async = _sync_run
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params, **kw: SandboxCapabilities(
        is_superuser=True
    )
    controller = window.sandbox_controller
    controller._run_async = _sync_run
    session = _FakeSession()
    controller._opener = _RecordingOpener(session, reachable=reachable)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    return window, controller, session


def _open_ddl_tab(window, ref=_REF, source=_SOURCE):
    """Open an object tab AND make it the active one -- since BUG-039 the two
    check gestures are visible only while a DDL object editor tab is in front,
    so a test that asserts on their visibility must say which tab it means."""
    window._on_ddl_edit_requested(ref, source)
    panel = window.center_stage.ddl_object_tab(ref.key)
    window.center_stage.setCurrentWidget(panel)
    return panel


def _accept_confirmations(monkeypatch):
    """Answer Yes to the apply confirmation. Patched on the QMessageBox the
    module imported (never on the window attribute): the panel captured the
    confirmation seam when `set_apply_seams` wired it, so a later attribute
    patch would not be seen -- and an unpatched modal would hang the run."""

    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.Yes),
    )


def test_the_window_owns_a_sandbox_controller(qtbot, tmp_path):
    from pgtp_editor.ui.sandbox_controller import SandboxController

    window = _window(qtbot, tmp_path)

    assert isinstance(window.sandbox_controller, SandboxController)
    assert window.sandbox_controller.session is None


def test_opening_a_project_binds_the_controller_and_opens_the_session(
    qtbot, tmp_path, monkeypatch
):
    """BUG-040 reversed FQ-023's *"don't open lazily"* ruling: binding a project
    whose sandbox is configured OPENS the session, with no user click and no
    menu entry -- Apply/Check just work."""
    window, controller, session = _project_window(qtbot, tmp_path, monkeypatch)

    assert controller.sandbox_params.host == "localhost"
    assert controller.session is session
    assert controller.can_check
    # Exactly ONE acquisition: the bind, not the bind plus something else.
    assert controller._opener.calls == 1
    # The lifecycle actions are DELETED, not hidden -- a hidden QAction stays
    # pinnable and a toolbar button bypasses menu visibility entirely.
    assert not hasattr(window, "_open_sandbox_session_action")
    assert not hasattr(window, "_close_sandbox_session_action")


def test_the_database_menu_offers_no_session_lifecycle_entries(qtbot, tmp_path):
    """BUG-040: `Open Sandbox Session` / `Close Sandbox Session` are gone from
    the menu entirely, in every state (projectless included -- a sandbox exists
    only in project mode, so they were reachable in no state at all)."""
    window = _window(qtbot, tmp_path)
    labels = [
        action.text() for action in find_top_menu(window, "Database").actions()
    ]

    assert "Open Sandbox Session" not in labels
    assert "Close Sandbox Session" not in labels
    assert not any("Sandbox Session" in label for label in labels)


def _setup_action(window):
    return find_action(find_top_menu(window, "Database"), "Sandbox Setup…")


def test_the_database_menu_offers_no_sandbox_setup_entry_projectless(qtbot, tmp_path):
    """`Sandbox Setup…` is DELETED (owner ruling, 2026-08-09) -- not hidden, and
    not projectless-only either. BUG-040 had hidden it in project mode on the
    premise that Project Settings already owned every piece of sandbox
    configuration; that premise was false (Provision / Reset / "create a sandbox
    database for me" existed nowhere else) and projectless the dialog was inert
    anyway, so the three gestures moved into Project Settings and the entry went
    away in every mode."""
    assert _setup_action(_window(qtbot, tmp_path)) is None


def test_the_database_menu_offers_no_sandbox_setup_entry_in_project_mode(
    qtbot, tmp_path, monkeypatch
):
    """Deleted rather than hidden for the same reason the session-lifecycle
    entries were: `ToolbarController._walk_menu_actions` never tests
    `isVisible()`, so a hidden action stays pinnable and a toolbar button would
    bypass the menu's visibility entirely."""
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)

    assert _setup_action(window) is None
    assert not any(
        "Sandbox Setup" in action.text()
        for action in find_top_menu(window, "Database").actions()
    )


def test_closing_the_project_does_not_bring_sandbox_setup_back(
    qtbot, tmp_path, monkeypatch
):
    """The entry is gone, not gated: no project transition can resurrect it."""
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)

    window._ddl_project_ui.close_project()

    assert _setup_action(window) is None


def test_no_session_is_opened_projectless(qtbot, tmp_path):
    """Projectless is untouched by construction: no project means no sandbox
    params, so the auto-open guard is a no-op rather than a special case."""
    window = _window(qtbot, tmp_path)
    controller = window.sandbox_controller
    controller._run_async = _sync_run
    opener = _RecordingOpener(_FakeSession())
    controller._opener = opener

    window._bind_sandbox_controller_to_project()

    assert window._ddl_project_settings is None
    assert window._configured_sandbox_params() is None
    assert controller.session is None
    assert opener.calls == 0


def test_a_project_with_no_sandbox_attempts_no_connection(
    qtbot, tmp_path, monkeypatch
):
    """The other half of the guard: a project is open, but it has no sandbox
    host, so nothing is dialled."""
    window, controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, sandbox_host=""
    )

    assert controller.session is None
    assert controller._opener.calls == 0


def test_an_unreachable_sandbox_degrades_to_the_no_session_state(
    qtbot, tmp_path, monkeypatch
):
    """Best-effort, never fatal, never modal: the project is open and usable,
    `has_session` is simply False, and the reason lands in the Audit panel
    through the existing `SandboxOperationResult` routing."""
    window, controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )

    assert controller._opener.calls == 1  # it was ATTEMPTED
    assert controller.session is None
    assert not controller.has_session
    assert window._ddl_project_folder == tmp_path / "proj"
    assert any("could not connect to the sandbox" in t for t in _audit_texts(window))


def test_recovering_from_a_failed_auto_open_reveals_the_console_and_the_checks(
    qtbot, tmp_path, monkeypatch
):
    """The one manual acquisition left (BUG-040): the `Open` button on the
    refusal dialog, which is `_open_sandbox_session()` -- the same chokepoint the
    auto-open uses."""
    window, controller, session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    _open_ddl_tab(window)
    assert not controller.has_session

    controller._opener.reachable = True
    window._open_sandbox_session()

    assert controller.session is session
    assert controller.can_check
    assert window._sandbox_check_action.isVisible()
    assert window._sandbox_console_action.isVisible()


def test_closing_the_project_leaves_no_stale_session(qtbot, tmp_path, monkeypatch):
    """There is no explicit close gesture any more: the project transition IS
    the closing mechanism (`set_project`/`clear_project`)."""
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    assert controller.has_session

    window._ddl_project_ui.close_project()

    assert controller.session is None
    assert not window._sandbox_check_action.isVisible()
    assert not window._sandbox_console_action.isVisible()
    assert window.center_stage.sandbox_sql_tab() is None


def test_the_controllers_ladder_seams_are_ddl_checks_real_entry_points():
    """The proof that tiers 0-2 actually compile on an apply: the default seams
    ARE `apply_and_check`/`probe_check`, not `recheck` (which applies nothing)."""
    from pgtp_editor.db import ddl_check
    from pgtp_editor.ui.sandbox_controller import SandboxController

    controller = SandboxController()

    assert controller._applier is ddl_check.apply_and_check
    assert controller._probe_checker is ddl_check.probe_check
    assert controller._checker is ddl_check.recheck


def test_apply_to_sandbox_runs_the_whole_ladder_against_the_session(
    qtbot, tmp_path, monkeypatch
):
    """§18.5 D3: Apply to Sandbox goes through `apply_and_check`, not the bare
    `SandboxSession.apply` -- so applying an object COMPILE-CHECKS it."""
    window, controller, session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    apply_calls, _probe = _stub_ladder(controller)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel.has_sandbox_apply  # the seam is wired -- the row is present
    _accept_confirmations(monkeypatch)

    assert panel.apply_to_sandbox() is True

    # The ladder ran, on the controller's own session, over the tab's buffer.
    assert len(apply_calls) == 1
    ladder_session, request, _caps, ddl_text = apply_calls[0]
    assert ladder_session is session
    assert ddl_text == _SOURCE
    assert request.working_set_ref == ("function", "pr", "recalc", "")
    # The bare `session.apply` path is gone: bookkeeping is the ladder's, in the
    # same transaction.
    assert session.applied_calls == []
    # The applied buffer is recorded for precondition 2, and marked as applied
    # because the report says it COMMITTED.
    assert panel.last_check_report() is not None
    assert panel.applied_sha1 == panel.text_sha1()


def test_a_bad_function_body_yields_a_real_clickable_compile_error(
    qtbot, tmp_path, monkeypatch
):
    """The whole point of the wire: a user pressing Apply to Sandbox on a broken
    body gets tier 2's compile error, as a CLICKABLE Audit finding.

    Only the psycopg call is faked -- the REAL `apply_and_check` composes the
    ladder and attributes the failing statement index to tier 2, so this pins the
    attribution rather than a hand-built report.
    """
    from pgtp_editor.db import ddl_check
    from pgtp_editor.db.apply import ApplyOutcome

    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()

    def fake_apply_ddl(target, statements, *, commit=True):
        # Statement 0 is the tier-1 SET; statement 1 is the DDL itself. Rejecting
        # the DDL is what a broken body really does.
        return ApplyOutcome.failed(
            'syntax error at or near "END"',
            statement_index=1,
            statement=statements[1],
            sqlstate="42601",
            # A real server reports a character position; `ApplyOutcome.failed`
            # derives the line from it in the ONE place that derivation is
            # allowed, and that line is what makes the Audit row clickable.
            position=_SOURCE.index("END\n") + 1,
            notices_captured=True,
        )

    controller._applier = lambda session, request, caps, **kwargs: (
        ddl_check.apply_and_check(
            session, request, caps, applier=fake_apply_ddl, **kwargs
        )
    )
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    _accept_confirmations(monkeypatch)

    panel.apply_to_sandbox()

    report = panel.last_check_report()
    assert report.tier2.status == "found_issues"
    assert "syntax error" in report.tier2.reason
    assert report.tier0.status == "found_issues"  # collapsed into tier 2
    assert not report.committed
    # The finding reached the CLICKABLE channel with the object's key on it.
    finding_items = [
        item
        for item in _audit_items(window)
        if "syntax error" in item.text() and item.text().startswith(CHECK_PREFIX)
    ]
    assert finding_items
    assert any(
        item.data(Qt.ItemDataRole.UserRole + 1) == _REF.key for item in finding_items
    )
    # And it never claims the sandbox now holds this text.
    assert panel.applied_sha1 is None


def test_a_rolled_back_apply_never_claims_the_buffer_was_applied(
    qtbot, tmp_path, monkeypatch
):
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    _stub_ladder(controller, report=_green_report(committed=False))
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    _accept_confirmations(monkeypatch)

    panel.apply_to_sandbox()

    assert panel.applied_sha1 is None
    assert any("was NOT applied" in text for text in _audit_texts(window))


def test_check_without_applying_runs_the_rolled_back_probe(
    qtbot, tmp_path, monkeypatch
):
    """§18.5 D3's probe: the same ladder, `commit=False`, and its result counts
    for precondition 2 without ever claiming the object was applied."""
    window, controller, session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    _apply_calls, probe_calls = _stub_ladder(controller)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    window.center_stage.setCurrentWidget(panel)

    assert window._sandbox_probe_check_action.isVisible()
    window._probe_check_active_ddl_object()

    assert len(probe_calls) == 1
    assert probe_calls[0][0] is session
    assert probe_calls[0][3] == _SOURCE
    assert _apply_calls == []
    assert panel.last_check_report() is not None
    assert panel.applied_sha1 is None  # nothing was applied
    assert session.applied_calls == []


def test_the_probe_gesture_shares_checks_presence_gate(qtbot, tmp_path, monkeypatch):
    """One predicate for both Check gestures -- and since FQ-023 that predicate
    is "is a sandbox configured", so a configured-but-sessionless project shows
    both rather than hiding both. Since BUG-039 it is composed with "a DDL
    object tab is active", which is what `_open_ddl_tab` supplies."""
    window, controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    _open_ddl_tab(window)
    assert not controller.has_session

    assert window._sandbox_probe_check_action.isVisible()
    assert window._sandbox_check_action.isVisible()

    controller._opener.reachable = True
    window._open_sandbox_session()
    assert window._sandbox_probe_check_action.isVisible()
    assert window._sandbox_check_action.isVisible()


# --- BUG-039: the check gestures are `Parsing` members, gated by TAB KIND ----


def test_the_check_gestures_are_hidden_off_a_ddl_object_tab(
    qtbot, tmp_path, monkeypatch
):
    """A live session is not enough: the gestures act on the ACTIVE DDL object
    tab, so on the Raw XML tab they are not offered at all."""
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    assert controller.has_session

    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    assert not window._sandbox_check_action.isVisible()
    assert not window._sandbox_probe_check_action.isVisible()
    # ...and the console entry, which is NOT tab-scoped, is untouched by that.
    assert window._sandbox_console_action.isVisible()


def test_activating_a_ddl_object_tab_reveals_both_check_gestures(
    qtbot, tmp_path, monkeypatch
):
    """The tab-change half of the gate: `_refresh_editor_menu_affordances` and
    `_refresh_sandbox_affordances` must BOTH reach the same helper, or the menu
    stays stale after whichever event the other one owns."""
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    _open_ddl_tab(window)

    assert window._sandbox_check_action.isVisible()
    assert window._sandbox_probe_check_action.isVisible()
    # The XML pair is hidden by the tab kind alone, which is the trade this menu
    # accepted: `Validate Project` is a DEFAULT toolbar button.
    assert not window._auto_parse_action.isVisible()
    assert not window._validate_project_action.isVisible()


def test_the_parsing_actions_are_the_check_handlers_themselves(
    qtbot, tmp_path, monkeypatch
):
    """One gesture, one home, one handler: triggering the Parsing entries runs
    the same ladder the Database entries used to -- there are no twins left to
    drift apart."""
    window, controller, session = _project_window(qtbot, tmp_path, monkeypatch)
    _apply_calls, probe_calls = _stub_ladder(controller)
    panel = _open_ddl_tab(window)
    checked = []
    controller._checker = lambda s, request, caps: checked.append(request) or None

    parsing = find_top_menu(window, "Parsing")
    find_action(parsing, "Check Object in Sandbox").trigger()
    find_action(parsing, "Check and rollback").trigger()

    assert len(checked) == 1 and checked[0].name == "recalc"
    assert len(probe_calls) == 1
    assert probe_calls[0][0] is session
    assert probe_calls[0][3] == panel.text()


def test_apply_affordance_is_absent_without_a_session(qtbot, tmp_path, monkeypatch):
    """The button row still follows the SESSION, not the configuration -- a
    button cannot state a reason. With the auto-open failed there is none."""
    window, _controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    window._on_ddl_edit_requested(_REF, _SOURCE)

    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert not panel.has_sandbox_apply


def test_a_dying_session_takes_the_apply_affordance_with_it(
    qtbot, tmp_path, monkeypatch
):
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel.has_sandbox_apply

    controller.close_session()

    assert not panel.has_sandbox_apply


def test_a_failed_apply_comes_back_as_a_stated_outcome(qtbot, tmp_path, monkeypatch):
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    # The ladder seam itself raising is the worst case: it must arrive as a
    # stated, reported failure (no report -> "apply did not run"), never as a
    # silent success.
    _stub_ladder(controller, raises=RuntimeError('syntax error at or near "BEGIN"'))
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    _accept_confirmations(monkeypatch)

    assert panel.apply_to_sandbox() is True  # the seam WAS invoked

    assert any("syntax error" in text for text in _audit_texts(window))


def test_the_check_gesture_renders_a_report_through_both_channels(
    qtbot, tmp_path, monkeypatch
):
    from pgtp_editor.db.ddl_check import CheckFinding, CheckReport, TierOutcome

    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    report = CheckReport(
        tier3=TierOutcome(status="found_issues", reason="1 finding"),
        findings=(
            CheckFinding(severity="error", message="boom", line=3, level="error"),
        ),
    )
    requests = []
    controller._checker = lambda session, request, caps: (
        requests.append(request) or report
    )

    window._check_active_ddl_object()

    texts = _audit_texts(window)
    # NARRATIVE channel: the tier line, unclickable.
    assert any(t.startswith(f"{CHECK_PREFIX}  tier3:") for t in texts)
    # CLICKABLE channel: the finding, with both roles.
    finding_items = [
        item
        for item in _audit_items(window)
        if item.data(Qt.ItemDataRole.UserRole) is not None
    ]
    assert len(finding_items) == 1
    assert finding_items[0].data(Qt.ItemDataRole.UserRole + 1) == _REF.key
    # The request was built in the host from the tab's own ref + buffer.
    assert requests[0].name == "recalc"
    assert requests[0].buffer_text == _SOURCE
    # And it was recorded for precondition 2.
    assert panel.last_check_report() is report


def test_a_check_that_produced_no_report_is_never_shown_as_clean(
    qtbot, tmp_path, monkeypatch
):
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)

    def explode(session, request, caps):
        raise RuntimeError("plpgsql_check exploded")

    controller._checker = explode

    window._check_active_ddl_object()

    assert any("plpgsql_check exploded" in text for text in _audit_texts(window))
    assert panel.last_check_report() is None


def test_a_failed_sandbox_operation_surfaces_its_reason(qtbot, tmp_path, monkeypatch):
    """Every distinguishable refusal reaches the Audit panel -- including the
    one BUG-040's auto-open can now raise on a foreign database, which nobody
    clicked for and which therefore must never be swallowed."""
    window, controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )

    def refuse(*a, **k):
        raise RuntimeError("not a PGTP-created database")

    controller._opener = refuse

    window._open_sandbox_session()

    assert any("not a PGTP-created database" in t for t in _audit_texts(window))
    assert controller.session is None


def test_the_trigger_functions_name_is_read_off_the_buffer_not_guessed(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="trigger", schema="pr", name="t_audit", table="orders")
    text = (
        "CREATE TRIGGER t_audit AFTER INSERT ON pr.orders\n"
        "FOR EACH ROW EXECUTE FUNCTION audit.log_row();\n"
    )

    assert window._trigger_function_for(ref, text) == {
        "function_schema": "audit",
        "function_name": "log_row",
    }
    # No EXECUTE clause -> nothing is guessed from the trigger's own name.
    assert window._trigger_function_for(ref, "CREATE TRIGGER t_audit ...") == {}


# --- BUG-038: a trigger FUNCTION tab carries its relation too ---------------

_TRIGGER_FN = (
    "CREATE OR REPLACE FUNCTION pr.log_row()\n"
    "RETURNS trigger LANGUAGE plpgsql AS $$\nBEGIN RETURN NEW; END;\n$$;\n"
)


class _IndexWithTrigger:
    """The one `SchemaIndex` method this path uses. Records its arguments so
    the reverse lookup is asserted to be asked about the FUNCTION, not the
    table."""

    def __init__(self, trigger):
        self._trigger = trigger
        self.asked = []

    def trigger_for_function(self, schema, name, arg_types=()):
        self.asked.append((schema, name, tuple(arg_types)))
        return self._trigger


def test_a_trigger_function_tab_binds_the_relation_its_trigger_fires_on(
    qtbot, tmp_path
):
    """The reported failure: checking a trigger FUNCTION errored with
    "missing trigger relation" because nothing told the request which table to
    bind. The relation is known — the trigger that calls it is in the index."""
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="log_row")
    index = _IndexWithTrigger(
        TriggerInfo(
            schema="pr",
            table="orders",
            name="t_audit",
            timing="after",
            function_name="log_row",
        )
    )
    window._ddl_schema_index = index

    assert window._trigger_relation_for(ref, _TRIGGER_FN) == {
        "relation_schema": "pr",
        "relation_table": "orders",
    }
    assert index.asked == [("pr", "log_row", ())]

    # End to end: the built request emits `relid`, which is the whole bug.
    request = CheckRequest.from_ref(
        ref,
        _TRIGGER_FN,
        **window._trigger_function_for(ref, _TRIGGER_FN),
        **window._trigger_relation_for(ref, _TRIGGER_FN),
    )
    assert request.regclass_text == '"pr"."orders"'


def test_a_plain_function_asks_the_index_nothing(qtbot, tmp_path):
    """`RETURNS trigger` is read off the buffer first, so a plain function does
    not even reach the reverse lookup."""
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="total")
    index = _IndexWithTrigger(None)
    window._ddl_schema_index = index

    body = "CREATE FUNCTION pr.total() RETURNS integer AS $$ SELECT 1 $$;"
    assert window._trigger_relation_for(ref, body) == {}
    assert index.asked == []


def test_an_unattached_trigger_function_binds_nothing_rather_than_guessing(
    qtbot, tmp_path
):
    """§18.6's unattached case. plpgsql_check genuinely cannot check one, and a
    fabricated relation would be worse than the stated refusal."""
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="log_row")
    window._ddl_schema_index = _IndexWithTrigger(None)
    assert window._trigger_relation_for(ref, _TRIGGER_FN) == {}

    # And with no index at all (no schema loaded yet), same answer.
    window._ddl_schema_index = None
    assert window._trigger_relation_for(ref, _TRIGGER_FN) == {}


def _index_for(schema="pr", table="orders", function_name="log_row"):
    return _IndexWithTrigger(
        TriggerInfo(
            schema=schema,
            table=table,
            name="t_audit",
            timing="after",
            function_name=function_name,
        )
    )


def test_the_check_gesture_carries_the_relation_into_the_request(
    qtbot, tmp_path, monkeypatch
):
    """End to end through the real gesture, not the helper: the request the
    ladder receives must already name the relation, or the server answers
    "missing trigger relation" exactly as reported."""
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._ddl_schema_index = _index_for()
    ref = DdlObjectRef(kind="function", schema="pr", name="log_row")
    _open_ddl_tab(window, ref=ref, source=_TRIGGER_FN)
    requests = []
    controller._checker = lambda s, request, caps: requests.append(request) or None

    window._check_active_ddl_object()

    assert requests[0].relation_schema == "pr"
    assert requests[0].relation_table == "orders"
    assert requests[0].regclass_text == '"pr"."orders"'


def test_the_probe_gesture_carries_the_relation_too(qtbot, tmp_path, monkeypatch):
    """The two call sites build the request separately, so the probe is pinned
    on its own -- a fix applied to one of them is the easy half-fix here."""
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._ddl_schema_index = _index_for()
    ref = DdlObjectRef(kind="function", schema="pr", name="log_row")
    _open_ddl_tab(window, ref=ref, source=_TRIGGER_FN)
    _apply_calls, probe_calls = _stub_ladder(controller)

    window._probe_check_active_ddl_object()

    assert probe_calls[0][1].relation_table == "orders"


def test_the_apply_path_carries_the_relation_as_well(qtbot, tmp_path, monkeypatch):
    """Apply runs the same ladder, and the reported failure arrived through it
    (`[Check] tier3: errored` on an Apply), so it gets its own pin."""
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._ddl_schema_index = _index_for()
    ref = DdlObjectRef(kind="function", schema="pr", name="log_row")
    panel = _open_ddl_tab(window, ref=ref, source=_TRIGGER_FN)
    apply_calls, _probe = _stub_ladder(controller)
    _accept_confirmations(monkeypatch)

    assert panel.apply_to_sandbox() is True

    assert apply_calls[0][1].relation_table == "orders"
    # ...and the working-set identity is still the FUNCTION's, not the table's.
    assert apply_calls[0][1].working_set_ref == ("function", "pr", "log_row", "")


def test_a_CREATE_TRIGGER_tab_keeps_using_the_trigger_path(qtbot, tmp_path):
    """The two helpers are disjoint: a trigger ref contributes a function, never
    a relation (its `table` already carries one)."""
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="trigger", schema="pr", name="t_audit", table="orders")
    window._ddl_schema_index = _IndexWithTrigger(None)
    assert window._trigger_relation_for(ref, "CREATE TRIGGER ... RETURNS trigger") == {}


# --- FQ-026: the picker's host surface is deleted ---------------------------
def test_no_menu_anywhere_offers_deploy_this_edit(qtbot, tmp_path):
    """FQ-009 put the picker on `Database` to make the destinations
    discoverable; FQ-020 made all three discoverable BY NAME on `Deployment`,
    and FQ-026 withdrew the picker on the owner's ruling that *"the picker is
    not needed if the other menus are explicit of the target"*.

    Asserted across BOTH menu bars, because the picker shipped on three
    always-present surfaces and a deduplication that leaves one behind has
    deduplicated nothing."""
    window = _window(qtbot, tmp_path)

    labels = {
        label for _command_id, label in window._toolbar_ui.all_menu_commands()
    }
    assert not [label for label in labels if "Deploy This Edit" in label]
    assert not [label for label in labels if "Deploy this edit" in label]
    # The host handler and its cached action go with it -- a surviving handler
    # is how a withdrawn gesture gets re-wired by accident.
    assert not hasattr(window, "_deploy_this_edit_action")
    assert not hasattr(window, "_deploy_active_ddl_object_edit")


def test_a_pinned_deploy_this_edit_button_is_dropped_not_left_dead(qtbot, tmp_path):
    """A deletion is not a move, so there is deliberately NO
    `RENAMED_ID_ALIASES` row: `resolve_ids` drops the id that no longer
    resolves, which is the `file.save` / `database.open-sandbox-session`
    precedent. The action was deleted rather than hidden for the usual reason
    -- a toolbar button bypasses menu visibility entirely."""
    path = str(tmp_path / "s.ini")
    seed = QSettings(path, QSettings.Format.IniFormat)
    seed.setValue("toolbarIds", ["database.deploy-this-edit", "file.open"])
    seed.sync()

    window = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    assert window._toolbar_ui.command_ids == ["file.open"]
    live = {command_id for command_id, _label in window._toolbar_ui.all_menu_commands()}
    assert "database.deploy-this-edit" not in live


def test_save_in_project_still_writes_the_file_the_picker_used_to(
    qtbot, tmp_path, monkeypatch
):
    """The surviving path for the picker's Save destination. It is the SAME
    host gesture the picker delegated to (`_save_ddl_object_editor`), reached
    one caller shorter -- so deleting the picker removed an entry point, not a
    capability."""
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    window.center_stage.setCurrentWidget(panel)
    destination = tmp_path / "recalc.sql"
    monkeypatch.setattr(panel, "_resolve_save_path", lambda: destination)

    assert window._save_active_ddl_object() is True

    assert destination.read_text(encoding="utf-8") == _SOURCE


def test_run_on_quality_in_project_mode_stays_blocked_and_says_why(
    qtbot, tmp_path, monkeypatch
):
    """FQ-020 wired the quality lane, but the PROJECT leg is still blocked on
    BUG-034: a project's `ProjectSettings.target` is never seeded from the
    `.pgtp`, so with a project open and no target profile there is nothing to
    resolve. The shipped matrix is therefore temporarily *projectless-only* --
    stated out loud because it inverts the expectation that a project can do
    more, not less.

    What must NOT happen is silence: the menu entry stays present and REPORTS
    (carve-out 2 narrowed to present-and-reporting), and the picker names the
    reason.
    """
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)

    assert panel.has_sandbox_apply is True
    assert panel.has_target_apply is False
    # FQ-026 deleted the in-tab affordances entirely (button row and the
    # context-menu apply entries), so "the gesture is unavailable" is now a
    # property of the SEAM plus the menu entry's own refusal below.
    labels = [a.text() for a in panel._build_context_menu().actions()]
    assert not [label for label in labels if "Apply" in label]

    # The menu entry is still THERE -- and clicking it states the reason rather
    # than no-opping.
    window.center_stage.setCurrentWidget(panel)
    action = find_action(find_top_menu(window, "Deployment"), "Apply to quality")
    assert action is not None and action.isVisible()
    action.trigger()
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("Apply to quality is unavailable" in line for line in lines)
    assert any(line.startswith("[Check] ") for line in lines)


# --- FQ-023: present-and-reporting, not absent ----------------------------
#
# Carve-out 2 is NARROWED, not overturned: absent when no sandbox is CONFIGURED
# (genuinely inapplicable), present-and-reporting when one is configured but no
# session is open (one click from applicable, and an absence cannot state a
# reason). The three gestures do NOT share one predicate -- the Checks read
# `SandboxController.can_check`, the console reads `_sandbox_console_available()`
# -- so each is pinned separately here.


def _answer_refusal(monkeypatch, button, seen=None):
    """Answer the missing-session offer. Patched on `modals.QMessageBox` (the
    stable target), and every test below MUST call it: without it the refusal is
    a real modal, which under offscreen hangs the run."""
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(
            lambda _p, _t, text, *a, **k: (
                seen.append(text) if seen is not None else None
            )
            or button
        ),
    )


def test_with_no_sandbox_configured_all_three_gestures_are_absent(
    qtbot, tmp_path, monkeypatch
):
    """Carve-out 2's surviving ABSENT case: nothing to open a session on."""
    window, controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, sandbox_host=""
    )
    _open_ddl_tab(window)  # the tab-kind half of the gate is satisfied...

    assert not controller.has_session
    # ...so what is asserted here is the sandbox half alone.
    assert not window._sandbox_check_action.isVisible()
    assert not window._sandbox_probe_check_action.isVisible()
    assert not window._sandbox_console_action.isVisible()


def test_a_configured_sandbox_without_a_session_shows_all_three(
    qtbot, tmp_path, monkeypatch
):
    """The FQ-023 defect, inverted: the user can now SEE the three gestures the
    moment a sandbox exists, without first guessing that a session must be
    opened. Since BUG-040 the sessionless state is reached by an auto-open that
    FAILED rather than by one nobody performed -- which is precisely the state
    that most needs a gesture able to state a reason."""
    window, controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    _open_ddl_tab(window)

    assert not controller.has_session
    assert window._sandbox_check_action.isVisible()
    assert window._sandbox_probe_check_action.isVisible()
    assert window._sandbox_console_action.isVisible()


def test_the_check_refusal_states_the_missing_session_and_runs_nothing(
    qtbot, tmp_path, monkeypatch
):
    """The refusal reuses the destination picker's sentence (FQ-009) -- one
    vocabulary for one fact, and no ladder run. BUG-040 deleted the menu entry
    that sentence used to name, so what it must NOT contain is now as
    load-bearing as what it must: the offer is the dialog's own `Open` button."""
    window, controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    apply_calls, probe_calls = _stub_ladder(controller)
    _open_ddl_tab(window)
    seen = []
    _answer_refusal(monkeypatch, modals.QMessageBox.StandardButton.Cancel, seen)

    window._check_active_ddl_object()

    assert "Check Object in Sandbox" in seen[0]
    assert "no sandbox session is open" in seen[0]
    assert "Open a sandbox session now?" in seen[0]
    assert "Open Sandbox Session" not in seen[0]
    assert apply_calls == [] and probe_calls == []
    assert not controller.has_session
    # Declining leaves the reason readable after the dialog is gone.
    message = window.statusBar().currentMessage()
    assert "no sandbox session is open" in message
    assert "Open Sandbox Session" not in message


def test_the_probe_gesture_refuses_under_its_own_name(qtbot, tmp_path, monkeypatch):
    window, _controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    seen = []
    _answer_refusal(monkeypatch, modals.QMessageBox.StandardButton.Cancel, seen)

    window._probe_check_active_ddl_object()

    assert "Check and rollback" in seen[0]  # FQ-026: its ONE name


def test_the_missing_session_is_reported_before_the_missing_tab(
    qtbot, tmp_path, monkeypatch
):
    """With no session AND no object tab, the answer is the one the gesture's new
    presence is advertising -- not "open a DDL object tab", which would send the
    user off to fix a different prerequisite."""
    window, _controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    seen = []
    _answer_refusal(monkeypatch, modals.QMessageBox.StandardButton.Cancel, seen)

    window._check_active_ddl_object()

    assert len(seen) == 1
    assert "DDL object tab" not in window.statusBar().currentMessage()


def test_taking_the_offer_opens_the_session_and_retries_nothing(
    qtbot, tmp_path, monkeypatch
):
    """The explicit-click half: a session opens because the user clicked Open,
    and the refused gesture is NOT replayed behind their back (`open_session` is
    async and reports through Audit; the user re-invokes it).

    Since BUG-040 this is the ONLY manual session-acquisition gesture left, so
    it is also the whole recovery story after a failed auto-open."""
    window, controller, session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    apply_calls, probe_calls = _stub_ladder(controller)
    _open_ddl_tab(window)
    controller._opener.reachable = True
    _answer_refusal(monkeypatch, modals.QMessageBox.StandardButton.Open)

    window._check_active_ddl_object()

    assert controller.session is session
    assert apply_calls == [] and probe_calls == []
    # ... and the gestures now work, because the affordance refresh ran.
    assert window._sandbox_check_action.isVisible()


def test_declining_the_offer_attempts_no_connection(qtbot, tmp_path, monkeypatch):
    """The owner's line, pinned: no connection is attempted without a click whose
    label says a session will be opened -- so a declined refusal must not even
    PROBE. (The auto-open's own attempt is over by now: `probes` is armed after
    the project bind, so only what the DECLINED gesture does is recorded.)"""
    window, _controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    probes = []
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params, **kw: probes.append(
        params
    )
    _answer_refusal(monkeypatch, modals.QMessageBox.StandardButton.Cancel)

    window._check_active_ddl_object()
    window._open_sandbox_sql_console()

    assert probes == []


def test_the_console_refusal_creates_no_console(qtbot, tmp_path, monkeypatch):
    """Present-and-reporting is about the MENU ENTRY: a console that would refuse
    every Run is still never created (§18.5 D4)."""
    window, _controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, reachable=False
    )
    seen = []
    _answer_refusal(monkeypatch, modals.QMessageBox.StandardButton.Cancel, seen)

    assert window._open_sandbox_sql_console() is None

    assert window.center_stage.sandbox_sql_tab() is None
    assert "Sandbox SQL Console" in seen[0]


def test_a_dying_session_still_closes_the_console_but_keeps_the_entry(
    qtbot, tmp_path, monkeypatch
):
    """The trap FQ-023 must not fall into: the ENTRY becomes present-and-
    reporting, the open console TAB is still closed when the session dies (and
    the object tabs' bridge buttons are still unwired -- a button cannot state a
    reason)."""
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    window._open_sandbox_sql_console()
    assert panel.has_run_in_console

    controller.close_session()

    assert window.center_stage.sandbox_sql_tab() is None
    assert not panel.has_run_in_console
    assert window._sandbox_console_action.isVisible()  # present, and reporting


def test_closing_the_project_takes_all_three_gestures_away(
    qtbot, tmp_path, monkeypatch
):
    """The narrowing does not resurrect a control for a project that is gone: no
    project means no configured sandbox, which is the ABSENT case."""
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    _open_ddl_tab(window)
    assert window._sandbox_check_action.isVisible()

    window._ddl_project_ui.close_project()

    assert not controller.has_session
    assert not window._sandbox_check_action.isVisible()
    assert not window._sandbox_probe_check_action.isVisible()
    assert not window._sandbox_console_action.isVisible()


def test_an_unconfigured_sandbox_refuses_without_a_modal(qtbot, tmp_path, monkeypatch):
    """Reachable through a toolbar button or a shortcut even while the menu entry
    is absent -- and an unexplained no-op is exactly what FQ-023 exists to kill.
    There is nothing to offer here, so the reason goes to the status bar and NO
    dialog is opened (the unpatched `question` below would hang if one were)."""
    window, _controller, _session = _project_window(
        qtbot, tmp_path, monkeypatch, sandbox_host=""
    )

    window._check_active_ddl_object()
    assert "none is configured" in window.statusBar().currentMessage()

    assert window._open_sandbox_sql_console() is None
    assert "none is configured" in window.statusBar().currentMessage()


# --- FQ-026: the one-line answer for `Check Object in Sandbox` --------------
#
# The gesture is clicked to ask a question one bit wide -- *am I in line with
# the sandbox?* -- and `recheck` answered it as a multi-tier narrative in which
# the YES case was not a sentence at all, only the ABSENCE of the stale-buffer
# caveat. An absence cannot answer a yes/no question, so both states speak.
#
# `recheck` itself is UNCHANGED: the whole ladder still runs and tier 3 still
# re-lints what is actually in the sandbox, which is the only thing that catches
# what changed *underneath* the object since it was applied.


from pgtp_editor.db.ddl_check import TIER_NOT_BUILT as _NOT_BUILT  # noqa: E402

def _recheck_report(*, applied_at="2026-08-10 09:00", stale=False):
    """A `recheck`-shaped report: tier 2 PASSED off the bookkeeping row, plus
    the stale caveat exactly when the recorded hash differs from the buffer --
    which is the comparison `db/ddl_check.py::_recheck_tier2` performs."""
    from pgtp_editor.db.ddl_check import (
        CAVEAT_STALE_BUFFER,
        REASON_ALREADY_APPLIED,
        CheckReport,
        TierOutcome,
    )

    return CheckReport(
        tier3=_NOT_BUILT,
        tier2=TierOutcome(
            status="passed", reason=REASON_ALREADY_APPLIED.format(applied_at=applied_at)
        ),
        caveats=(
            (CAVEAT_STALE_BUFFER.format(applied_at=applied_at),) if stale else ()
        ),
    )


def _run_recheck(qtbot, tmp_path, monkeypatch, report):
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    controller._checker = lambda session, request, caps: report
    window._check_active_ddl_object()
    return window


def test_a_matching_buffer_gets_an_affirmative_line(
    qtbot, tmp_path, monkeypatch, comparison_modals
):
    """The state that had NO sentence: a match used to be readable only as the
    absence of the stale-buffer caveat."""
    _run_recheck(qtbot, tmp_path, monkeypatch, _recheck_report())

    assert len(comparison_modals) == 1
    title, text = comparison_modals[0]
    assert title == "Check Object in Sandbox"
    assert text.startswith("pr.recalc() matches what the sandbox holds.")
    # And it still carries the ladder's own "applied when" fact, unrephrased.
    assert "2026-08-10 09:00" in text


def test_a_changed_buffer_gets_the_negative_line(
    qtbot, tmp_path, monkeypatch, comparison_modals
):
    _run_recheck(qtbot, tmp_path, monkeypatch, _recheck_report(stale=True))

    _title, text = comparison_modals[0]
    assert text.startswith("pr.recalc() does NOT match what the sandbox holds.")
    # The caveat rides along -- it is where the `applied at` timestamp lives.
    assert "has changed since it was last applied" in text


def test_an_object_the_sandbox_never_held_is_not_reported_as_a_mismatch(
    qtbot, tmp_path, monkeypatch, comparison_modals
):
    """Three-valued on purpose: "the sandbox has never held this" is a
    different answer from "your buffer differs", and collapsing it into the
    negative would tell the user to re-apply something that was never there."""
    from pgtp_editor.db.ddl_check import (
        REASON_NOT_IN_WORKING_SET,
        CheckReport,
        TierOutcome,
    )

    _run_recheck(
        qtbot,
        tmp_path,
        monkeypatch,
        CheckReport(
            tier3=_NOT_BUILT,
            tier2=TierOutcome(status="unavailable", reason=REASON_NOT_IN_WORKING_SET),
        ),
    )

    _title, text = comparison_modals[0]
    assert text.startswith("The sandbox does not hold pr.recalc() at all.")


def test_an_unreadable_working_set_is_unknown_never_a_no(
    qtbot, tmp_path, monkeypatch, comparison_modals
):
    """`_recheck_tier2` refuses to degrade an unreadable bookkeeping table to
    "not applied"; the modal must not undo that by answering "no"."""
    from pgtp_editor.db.ddl_check import CheckReport, TierOutcome

    _run_recheck(
        qtbot,
        tmp_path,
        monkeypatch,
        CheckReport(
            tier3=_NOT_BUILT,
            tier2=TierOutcome(
                status="unavailable", reason="the table could not be read"
            ),
        ),
    )

    _title, text = comparison_modals[0]
    assert text.startswith("Whether the sandbox holds pr.recalc() could not be determined.")
    assert "does NOT match" not in text


def test_the_modal_is_in_addition_to_the_audit_output_never_instead(
    qtbot, tmp_path, monkeypatch, comparison_modals
):
    """The owner asked for a one-line answer; they did not ask for the tier
    detail and the clickable findings to stop being reported."""
    window = _run_recheck(qtbot, tmp_path, monkeypatch, _recheck_report())

    assert len(comparison_modals) == 1
    texts = _audit_texts(window)
    assert any(t.startswith(f"{CHECK_PREFIX}  tier2:") for t in texts)


def test_the_probe_gesture_puts_up_no_comparison_modal(
    qtbot, tmp_path, monkeypatch, comparison_modals
):
    """`Check and rollback` answers a different question ("would this
    compile?"), and it applies nothing -- so there is no "are we in line?"
    verdict for it to state."""
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    controller._applier = lambda *a, **k: _recheck_report()

    window._probe_check_active_ddl_object()

    assert comparison_modals == []
