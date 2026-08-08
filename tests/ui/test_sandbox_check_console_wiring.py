# tests/ui/test_sandbox_check_console_wiring.py
"""MainWindow's half of §18.5 D3a (the two Audit channels of a Check run) and
D4 (the Sandbox SQL Console + the "Run in Sandbox Console" bridge).

D3a: findings travel as OBJECTS on `check_findings` and only MainWindow can
render them clickable, so these tests pin the roles precisely -- a finding with
a line carries both `UserRole` (the line) and `UserRole+1` (the object's
`DdlObjectRef.key`), a `line is None` finding carries NEITHER (inert, never an
accidental Raw-XML navigation), and the narrative `check_reported` channel
carries no roles at all.

D4: the console is ABSENT, not disabled, without a live session; the bridge
copies text and executes nothing; and there is no "run against target"
affordance anywhere in the Database menu.
"""
from PySide6.QtCore import QSettings, Qt

from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.ui.ddl_object_editor import CHECK_PREFIX, DdlObjectRef
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui import modals


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


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
    panel = window.audit_panel
    return [panel.item(i).text() for i in range(panel.count())]


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

    assert _audit_texts(window) == ["[SQL] line 4: unbalanced dollar quote"]


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


def _project_window(qtbot, tmp_path, monkeypatch, sandbox_host="localhost"):
    """A window with an open project whose sandbox is configured, the
    controller's async made synchronous, and its opener/prober stubbed so no
    real connection is ever attempted."""
    from pgtp_editor.db.config import ConnectionParams
    from pgtp_editor.db.sandbox import SandboxCapabilities

    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        sandbox=ConnectionParams(host=sandbox_host, database="pgtp_sandbox_x")
    )
    save_settings(project_dir, settings)
    window = _window(qtbot, tmp_path)
    window._run_async = _sync_run
    window._ddl_project_ui.probe_sandbox_capabilities = lambda params: SandboxCapabilities(
        is_superuser=True
    )
    controller = window.sandbox_controller
    controller._run_async = _sync_run
    session = _FakeSession()
    controller._opener = lambda *a, **k: session
    window._ddl_project_ui.set_active_project(project_dir, settings)
    return window, controller, session


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


def test_opening_a_project_binds_the_controller_without_connecting(
    qtbot, tmp_path, monkeypatch
):
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)

    assert controller.sandbox_params.host == "localhost"
    assert controller.session is None  # no connection as a project side effect
    assert window._open_sandbox_session_action.isVisible()
    assert not window._close_sandbox_session_action.isVisible()
    assert not window._sandbox_check_action.isVisible()


def test_opening_a_session_reveals_the_console_and_the_check_gesture(
    qtbot, tmp_path, monkeypatch
):
    window, controller, session = _project_window(qtbot, tmp_path, monkeypatch)

    window._open_sandbox_session()

    assert controller.session is session
    assert controller.can_check
    assert window._sandbox_check_action.isVisible()
    assert window._sandbox_console_action.isVisible()
    assert window._close_sandbox_session_action.isVisible()
    assert not window._open_sandbox_session_action.isVisible()


def test_closing_the_project_leaves_no_stale_session(qtbot, tmp_path, monkeypatch):
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
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


def test_the_probe_gesture_is_absent_without_a_session(qtbot, tmp_path, monkeypatch):
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)

    assert not window._sandbox_probe_check_action.isVisible()

    window._open_sandbox_session()
    assert window._sandbox_probe_check_action.isVisible()


def test_apply_affordance_is_absent_without_a_session(qtbot, tmp_path, monkeypatch):
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
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
    window, controller, _session = _project_window(qtbot, tmp_path, monkeypatch)

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


# --- FQ-009: the "Deploy this edit…" picker, host side ----------------------
def test_deploy_this_edit_is_a_database_menu_entry_that_needs_no_sandbox(
    qtbot, tmp_path
):
    """FQ-009's discoverability half. Unlike the two check gestures the entry is
    always visible: its Save destination works with no database at all."""
    window = _window(qtbot, tmp_path)

    action = window._deploy_this_edit_action
    assert action is not None
    assert action.text() == "Deploy This Edit…"
    assert action.isVisible()
    # §18.5: no shortcut on anything that can write outward.
    assert action.shortcut().isEmpty()


def test_deploy_this_edit_menu_entry_runs_the_active_tabs_picker(
    qtbot, tmp_path, monkeypatch
):
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    window.center_stage.setCurrentWidget(panel)
    monkeypatch.setattr(panel, "_prompt_destination", lambda: None)

    assert window._deploy_active_ddl_object_edit() is None


def test_deploy_this_edit_with_no_object_tab_states_it_instead_of_crashing(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)

    assert window._deploy_active_ddl_object_edit() is None
    assert "open one first" in window.statusBar().currentMessage()


def test_the_pickers_save_destination_actually_writes_the_file(
    qtbot, tmp_path, monkeypatch
):
    """`save_requested` had no host connection, so choosing Save in the picker
    was a silent no-op. It now runs the host's one existing save gesture."""
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)
    window.center_stage.setCurrentWidget(panel)
    destination = tmp_path / "recalc.sql"
    monkeypatch.setattr(panel, "_resolve_save_path", lambda: destination)
    monkeypatch.setattr(panel, "_prompt_destination", lambda: "save")

    window._deploy_active_ddl_object_edit()

    assert destination.read_text(encoding="utf-8") == _SOURCE


def test_apply_to_target_stays_absent_and_the_picker_says_why(
    qtbot, tmp_path, monkeypatch
):
    """FQ-009 wired the sandbox leg's discoverability, NOT the target leg: the
    live-identity seam precondition 1 needs has no trustworthy source until
    BUG-034/BUG-030 land. The gesture is absent (carve-out 2) -- but the picker
    now states that, and points at the reviewable deployment-script path,
    instead of leaving a silent gap."""
    window, _controller, _session = _project_window(qtbot, tmp_path, monkeypatch)
    window._open_sandbox_session()
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = window.center_stage.ddl_object_tab(_REF.key)

    assert panel.has_sandbox_apply is True
    assert panel.has_target_apply is False
    assert panel.target_button is None
    labels = [a.text() for a in panel._build_context_menu().actions()]
    assert "Apply to Target…" not in labels

    prompt = panel.deploy_prompt_text()
    assert "Apply to Target" in prompt
    assert "Compare Schemas" in prompt
