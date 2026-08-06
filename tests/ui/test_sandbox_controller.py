"""§18.5 D2/D2a sandbox lane controller (ui/sandbox_controller.py).

The controller owns no sandbox logic — `db/sandbox.py` does — so these tests
never assert what that module already proves (ownership, baseline SQL, tier
derivation). They assert the four things a *lifecycle host* alone can get wrong:

1. **Session ownership.** None initially, exactly one after a successful open,
   released on close, and never opened as a side effect of binding a project.
2. **Distinguishable failures.** Unreachable, non-superuser, missing
   `pg_dump`/`pg_restore` and a foreign database each surface their own
   human-readable reason, in `db/sandbox.py`'s existing vocabulary.
3. **Nothing destructive by accident.** Clone/reset/provision refuse without the
   injected confirmation seam, and cloning is refused outright for a
   schema-only sandbox.
4. **Nothing on the GUI thread.** Every DB-touching operation goes through the
   injected `_run_async` seam; the refusals go through none.

The whole sandbox layer is injected as fakes — no PostgreSQL, no `pg_dump`, no
psycopg — and no dialog exists to reach, because the controller opens none.
"""
import pytest

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.sandbox import (
    ForeignDatabaseError,
    MissingCloneToolError,
    SandboxCapabilities,
    SandboxMode,
    SandboxSession,
)
from pgtp_editor.ui.sandbox_controller import (
    DESTRUCTIVE_OPERATIONS,
    SandboxController,
    SandboxOperation,
)

pytestmark = pytest.mark.usefixtures("qapp")


SANDBOX = ConnectionParams(host="localhost", port="5432", database="pgtp_sandbox_dev", user="me")
TARGET = ConnectionParams(host="db.example", port="5432", database="prod", user="me")


# ---------------------------------------------------------------------------
# fakes -- the whole db/sandbox.py surface the controller touches
# ---------------------------------------------------------------------------
def _caps(**kwargs) -> SandboxCapabilities:
    """A healthy tier-3 probe result unless a test says otherwise."""
    defaults = dict(
        server_version=(16, 0, 3),
        is_superuser=True,
        installed_extensions=frozenset(),
        available_extensions=frozenset({"plpgsql_check"}),
        database="pgtp_sandbox_dev",
        owner_marker="pgtp-editor-sandbox:abc:2026-08-06T00:00:00+00:00",
        pg_dump_path="/usr/bin/pg_dump",
        pg_restore_path="/usr/bin/pg_restore",
    )
    return SandboxCapabilities(**{**defaults, **kwargs})


class FakeExecutor:
    """A `SandboxExecutor` that records instead of connecting."""

    def __init__(self) -> None:
        self.executed: list[list[str]] = []

    def execute(self, params, statements) -> None:
        self.executed.append(list(statements))

    def query(self, params, sql):
        return []


class RecordingSession(SandboxSession):
    """A real `SandboxSession` (so the controller sees the real type) whose
    `reset()` is recorded rather than run against a server."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("params", SANDBOX)
        kwargs.setdefault("mode", SandboxMode.SCHEMA_ONLY)
        kwargs.setdefault("executor", FakeExecutor())
        super().__init__(**kwargs)
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1


class FakeTier:
    """A duck-typed `ddl_check.TierOutcome` -- the controller reads `status`,
    `reason` and (through the report) `ran`, nothing else."""

    def __init__(self, status="passed", reason="") -> None:
        self.status = status
        self.reason = reason


class FakeReport:
    """A duck-typed `ddl_check.CheckReport`. The controller must read reports by
    attribute (the same discipline `tier_outcomes`/`report_blockers` use), so a
    three-attribute stub has to be enough -- if it ever isn't, the controller has
    started depending on `ddl_check`'s concrete types."""

    def __init__(self, *, ran=True, findings=(), tier3=None) -> None:
        self.ran = ran
        self.findings = tuple(findings)
        self.tier3 = tier3 if tier3 is not None else FakeTier()


class Layer:
    """One recording stand-in for every injected `db/sandbox.py` seam."""

    def __init__(self, *, caps=None, session=None) -> None:
        self.caps = caps if caps is not None else _caps()
        self.session = session if session is not None else RecordingSession()
        self.probe_calls: list[ConnectionParams] = []
        self.open_calls: list[dict] = []
        self.provision_calls: list[tuple] = []
        self.create_db_calls: list[tuple] = []
        self.clone_calls: list[tuple] = []
        self.install_calls: list[SandboxSession] = []
        self.snapshot_calls: list[ConnectionParams] = []
        #: Set to an exception to make the matching seam raise.
        self.check_calls: list[tuple] = []
        #: What the injected ladder seam hands back (§18.5 D3a).
        self.report = FakeReport()
        #: Set to an exception to make the matching seam raise.
        self.open_error: BaseException | None = None
        self.clone_error: BaseException | None = None
        self.install_error: BaseException | None = None
        self.check_error: BaseException | None = None

    def prober(self, params):
        self.probe_calls.append(params)
        return self.caps

    def opener(self, params, **kwargs):
        self.open_calls.append({"params": params, **kwargs})
        if self.open_error is not None:
            raise self.open_error
        return self.session

    def provisioner(self, schema, sandbox_params, mode, *, target_params=None, **kwargs):
        self.provision_calls.append((schema, sandbox_params, mode, target_params))
        return self.session

    def database_creator(self, admin_params, name, **kwargs):
        self.create_db_calls.append((admin_params, name))

    def cloner(self, target_params, sandbox_params, **kwargs):
        self.clone_calls.append((target_params, sandbox_params))
        if self.clone_error is not None:
            raise self.clone_error

    def installer(self, session):
        self.install_calls.append(session)
        if self.install_error is not None:
            raise self.install_error

    def snapshotter(self, target_params, **kwargs):
        self.snapshot_calls.append(target_params)
        return "SNAPSHOT"

    def checker(self, session, request, caps, **kwargs):
        self.check_calls.append((session, request, caps))
        if self.check_error is not None:
            raise self.check_error
        return self.report


class SyncRunner:
    """The synchronous stand-in for `ui/async_task.py::run_async` — records
    every off-thread hand-off, then runs it inline so the test stays
    deterministic. Its `calls` list is the proof that a DB-touching operation
    never ran on the GUI thread."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, fn, on_result, on_error=None, pool=None):
        self.calls += 1
        try:
            value = fn()
        except Exception as exc:  # noqa: BLE001 — mirrors run_async's contract
            if on_error is not None:
                on_error(exc)
            return None
        on_result(value)
        return None


def _controller(layer: Layer, *, confirm=True, mode=SandboxMode.SCHEMA_ONLY, **kwargs):
    """A controller wired to `layer`, bound to a project, with a synchronous
    executor seam. Returns `(controller, runner, results)`."""
    if callable(confirm):  # a spy, for tests that assert it is NOT consulted
        confirm_seam = confirm
    else:
        confirm_seam = None if confirm is None else (lambda warning: confirm)
    controller = SandboxController(
        confirm_destructive=confirm_seam,
        prober=layer.prober,
        opener=layer.opener,
        provisioner=layer.provisioner,
        database_creator=layer.database_creator,
        cloner=layer.cloner,
        installer=layer.installer,
        snapshotter=layer.snapshotter,
        checker=layer.checker,
        **kwargs,
    )
    runner = SyncRunner()
    controller._run_async = runner
    results = []
    controller.operation_finished.connect(results.append)
    controller.set_project(sandbox_params=SANDBOX, target_params=TARGET, mode=mode)
    return controller, runner, results


# ---------------------------------------------------------------------------
# 1. session ownership
# ---------------------------------------------------------------------------
def test_no_session_initially_and_binding_a_project_opens_nothing():
    layer = Layer()
    controller, runner, _ = _controller(layer)

    assert controller.has_session is False
    assert controller.session is None
    assert controller.capabilities is None
    # Binding a project must not connect, provision, clone or reset.
    assert runner.calls == 0
    assert layer.probe_calls == [] and layer.provision_calls == []


def test_open_succeeds_exposes_capabilities_and_the_session():
    layer = Layer()
    controller, runner, results = _controller(layer)
    changed = []
    controller.session_changed.connect(changed.append)

    controller.open_session()

    assert controller.has_session is True
    assert controller.session is layer.session
    assert controller.capabilities is layer.caps
    assert changed == [True]
    assert results[-1].ok is True
    assert results[-1].operation is SandboxOperation.OPEN
    # Off the GUI thread, and the recorded mode/target rode through to the gate.
    assert runner.calls == 1
    assert layer.open_calls[0]["mode"] is SandboxMode.SCHEMA_ONLY
    assert layer.open_calls[0]["target_params"] is TARGET


def test_close_releases_the_session():
    layer = Layer()
    controller, _, _ = _controller(layer)
    controller.open_session()
    changed = []
    controller.session_changed.connect(changed.append)

    controller.close_session()

    assert controller.has_session is False
    assert controller.session is None
    assert changed == [False]
    # Idempotent: closing again is silent.
    controller.close_session()
    assert changed == [False]


def test_set_project_drops_the_previous_projects_session():
    layer = Layer()
    controller, _, _ = _controller(layer)
    controller.open_session()

    controller.set_project(sandbox_params=None, configured=False)

    assert controller.has_session is False
    assert controller.capabilities is None


# ---------------------------------------------------------------------------
# 2. distinguishable failures, in db/sandbox.py's own vocabulary
# ---------------------------------------------------------------------------
def test_open_fails_unreachable_with_the_probe_error_named():
    layer = Layer(caps=_caps(probe_error="connection refused"))
    controller, _, results = _controller(layer)

    controller.open_session()

    assert controller.has_session is False
    assert results[-1].ok is False
    assert results[-1].reason == "sandbox unreachable: connection refused"
    assert results[-1].capabilities is layer.caps
    assert layer.open_calls == []  # never reached the ownership gate


def test_open_fails_for_a_non_superuser_with_the_install_gates_wording():
    layer = Layer(caps=_caps(is_superuser=False))
    controller, _, results = _controller(layer)

    controller.open_session()

    assert controller.has_session is False
    reason = results[-1].reason
    assert "superuser" in reason and "CREATE EXTENSION" in reason
    assert reason != "sandbox unreachable: None"
    assert layer.open_calls == []


def test_open_fails_when_clone_tools_are_missing_only_under_with_data():
    caps = _caps(pg_dump_path=None, pg_restore_path="/usr/bin/pg_restore")

    # Schema-only needs neither binary -- it opens fine.
    schema_only = Layer(caps=caps)
    controller, _, results = _controller(schema_only, mode=SandboxMode.SCHEMA_ONLY)
    controller.open_session()
    assert controller.has_session is True

    with_data = Layer(caps=caps)
    controller2, _, results2 = _controller(with_data, mode=SandboxMode.WITH_DATA)
    controller2.open_session()
    assert controller2.has_session is False
    assert results2[-1].reason == "sandbox unavailable: pg_dump not found on PATH"


def test_open_reports_a_foreign_database_refusal_verbatim():
    layer = Layer()
    layer.open_error = ForeignDatabaseError("myapp_dev")
    controller, _, results = _controller(layer)

    controller.open_session()

    assert controller.has_session is False
    assert "did not create this database" in results[-1].reason


def test_open_without_a_configured_sandbox_never_touches_the_thread_pool():
    layer = Layer()
    controller, runner, results = _controller(layer)
    controller.set_project(sandbox_params=None, configured=False)

    controller.open_session()

    assert results[-1].reason == "no local sandbox configured for this project"
    assert runner.calls == 0


def test_capability_status_before_any_probe_is_degraded_not_a_lie():
    layer = Layer()
    controller, _, _ = _controller(layer)

    status = controller.capability_status()

    assert status.tier.value == "quality"
    assert "not been probed" in (status.degraded_reason or "")


def test_refresh_capabilities_reprobes_off_thread_without_opening_a_session():
    layer = Layer()
    controller, runner, results = _controller(layer)

    controller.refresh_capabilities()

    assert controller.capabilities is layer.caps
    assert controller.has_session is False
    assert runner.calls == 1
    assert results[-1].ok is True


# ---------------------------------------------------------------------------
# 3. nothing destructive by accident
# ---------------------------------------------------------------------------
def test_data_clone_is_refused_for_a_schema_only_sandbox():
    layer = Layer()
    controller, runner, results = _controller(layer, mode=SandboxMode.SCHEMA_ONLY)
    controller.open_session()
    before = runner.calls

    controller.run_data_clone()

    assert layer.clone_calls == []
    assert runner.calls == before  # refused before any hand-off
    assert results[-1].ok is False
    assert "without data" in results[-1].reason


def test_data_clone_runs_off_thread_under_with_data():
    layer = Layer(session=RecordingSession(mode=SandboxMode.WITH_DATA))
    controller, runner, results = _controller(layer, mode=SandboxMode.WITH_DATA)
    controller.open_session()
    before = runner.calls

    controller.run_data_clone()

    assert layer.clone_calls == [(TARGET, SANDBOX)]
    assert runner.calls == before + 1
    assert results[-1].ok is True


def test_data_clone_reports_a_missing_binary_by_name():
    layer = Layer(session=RecordingSession(mode=SandboxMode.WITH_DATA))
    layer.clone_error = MissingCloneToolError("pg_restore", "/usr/bin")
    controller, _, results = _controller(layer, mode=SandboxMode.WITH_DATA)
    controller.open_session()

    controller.run_data_clone()

    assert results[-1].ok is False
    assert "pg_restore" in results[-1].reason and "/usr/bin" in results[-1].reason


def test_destructive_operations_are_refused_without_a_confirmation_seam():
    layer = Layer(session=RecordingSession(mode=SandboxMode.WITH_DATA))
    controller, runner, results = _controller(
        layer, confirm=None, mode=SandboxMode.WITH_DATA
    )
    controller.open_session()
    before = runner.calls

    controller.run_data_clone()
    controller.reset_session()
    controller.provision()

    assert layer.clone_calls == [] and layer.provision_calls == []
    assert layer.session.reset_calls == 0
    assert runner.calls == before
    assert all(not result.ok for result in results[-3:])
    assert all("not confirmed" in result.reason for result in results[-3:])


def test_a_declined_confirmation_stops_the_operation():
    layer = Layer(session=RecordingSession(mode=SandboxMode.WITH_DATA))
    controller, _, results = _controller(
        layer, confirm=False, mode=SandboxMode.WITH_DATA
    )
    controller.open_session()

    controller.run_data_clone()

    assert layer.clone_calls == []
    assert results[-1].ok is False


def test_every_destructive_operation_is_named_and_carries_a_warning():
    destructive = {
        SandboxOperation.PROVISION,
        SandboxOperation.CLONE_DATA,
        SandboxOperation.RESET,
    }
    for operation in SandboxOperation:
        assert SandboxController.is_destructive(operation) is (operation in destructive)
        warning = SandboxController.destructive_warning(operation)
        assert bool(warning) is (operation in destructive)


# ---------------------------------------------------------------------------
# 4. provisioning, reset and the plpgsql_check install
# ---------------------------------------------------------------------------
def test_provision_snapshots_the_target_and_holds_the_new_session():
    layer = Layer()
    controller, runner, results = _controller(layer)

    controller.provision()

    assert layer.snapshot_calls == [TARGET]
    assert layer.provision_calls == [("SNAPSHOT", SANDBOX, SandboxMode.SCHEMA_ONLY, TARGET)]
    assert controller.session is layer.session
    assert runner.calls == 1
    assert results[-1].ok is True


def test_provision_can_create_the_sandbox_database_first():
    layer = Layer()
    controller, _, _ = _controller(layer)
    admin = ConnectionParams(host="localhost", database="postgres", user="me")

    controller.provision(admin_params=admin, database_name="pgtp_sandbox_dev")

    assert layer.create_db_calls == [(admin, "pgtp_sandbox_dev")]


def test_reset_reprovisions_through_the_session_off_thread():
    layer = Layer()
    controller, runner, results = _controller(layer)
    controller.open_session()
    before = runner.calls

    controller.reset_session()

    assert layer.session.reset_calls == 1
    assert controller.has_session is True  # reset re-provisions; it does not invalidate
    assert runner.calls == before + 1
    assert results[-1].ok is True


def test_reset_without_a_session_is_a_stated_refusal():
    layer = Layer()
    controller, runner, results = _controller(layer)

    controller.reset_session()

    assert results[-1].ok is False
    assert "no sandbox session" in results[-1].reason
    assert runner.calls == 0


def test_install_plpgsql_check_delegates_to_the_real_function():
    layer = Layer()
    controller, runner, results = _controller(layer)
    controller.open_session()
    before = runner.calls

    controller.install_plpgsql_check()

    assert layer.install_calls == [layer.session]
    assert runner.calls == before + 1
    assert results[-1].ok is True
    assert results[-1].operation is SandboxOperation.INSTALL_PLPGSQL_CHECK


def test_install_plpgsql_check_reports_a_failing_create_extension():
    layer = Layer()
    layer.install_error = RuntimeError("permission denied for database")
    controller, _, results = _controller(layer)
    controller.open_session()

    controller.install_plpgsql_check()

    assert results[-1].ok is False
    assert results[-1].reason == "permission denied for database"


def test_install_plpgsql_check_is_a_no_op_success_when_already_installed():
    layer = Layer(caps=_caps(installed_extensions=frozenset({"plpgsql_check"})))
    controller, runner, results = _controller(layer)
    controller.open_session()
    before = runner.calls

    controller.install_plpgsql_check()

    assert layer.install_calls == []
    assert runner.calls == before
    assert results[-1].ok is True
    assert results[-1].reason == "already installed."


def test_install_plpgsql_check_reports_the_gates_reason_when_absent():
    layer = Layer(caps=_caps(available_extensions=frozenset()))
    controller, _, results = _controller(layer)
    controller.open_session()

    controller.install_plpgsql_check()

    assert layer.install_calls == []
    assert results[-1].ok is False
    assert "C library on disk" in results[-1].reason


# ---------------------------------------------------------------------------
# 5. §18.5 D3a -- the Check run
#
# The ladder itself lives in db/ddl_check.py and is proven there; these tests
# assert only what the *host* can get wrong: that CHECK is non-destructive, that
# it runs off the GUI thread, and that no outcome of it is ever silent.
# ---------------------------------------------------------------------------
REQUEST = object()  # opaque on purpose: the controller must pass it through


def test_check_is_not_a_destructive_operation():
    assert SandboxOperation.CHECK not in DESTRUCTIVE_OPERATIONS
    assert SandboxController.is_destructive(SandboxOperation.CHECK) is False
    assert SandboxController.destructive_warning(SandboxOperation.CHECK) == ""


def test_a_check_run_never_consults_the_confirmation_seam():
    asked = []
    layer = Layer()
    controller, _, results = _controller(layer, confirm=lambda warning: asked.append(warning) or True)
    controller.open_session()

    controller.run_check(REQUEST)

    assert asked == []  # D3a: non-destructive -- no confirm_destructive prompt
    assert results[-1].operation is SandboxOperation.CHECK
    assert results[-1].ok is True


def test_check_runs_off_thread_and_reports_the_report_it_got():
    layer = Layer()
    controller, runner, results = _controller(layer)
    controller.open_session()
    before = runner.calls

    controller.run_check(REQUEST)

    # The ladder was called once, with the live session, the request verbatim
    # and the probed capabilities -- and off the GUI thread.
    assert layer.check_calls == [(layer.session, REQUEST, layer.caps)]
    assert runner.calls == before + 1
    result = results[-1]
    assert result.operation is SandboxOperation.CHECK
    assert result.ok is True and result.reason == ""
    assert result.report is layer.report


def test_check_with_findings_is_not_ok_and_still_delivers_the_report():
    layer = Layer()
    layer.report = FakeReport(
        findings=(("ERROR", 3, "too few parameters"), ("WARNING", 4, "unused")),
        tier3=FakeTier(status="found_issues"),
    )
    controller, _, results = _controller(layer)
    controller.open_session()

    controller.run_check(REQUEST)

    assert results[-1].ok is False
    assert "2 findings" in results[-1].reason
    # The findings channel is the report, not the reason string.
    assert results[-1].report is layer.report


def test_an_unavailable_tier_reports_that_tiers_own_reason_verbatim():
    layer = Layer()
    layer.report = FakeReport(
        ran=False,
        tier3=FakeTier(status="unavailable", reason="plpgsql_check is not installed."),
    )
    controller, _, results = _controller(layer)
    controller.open_session()

    controller.run_check(REQUEST)

    assert results[-1].ok is False
    assert results[-1].reason == "plpgsql_check is not installed."
    assert results[-1].report is layer.report


def test_a_report_that_did_not_run_and_states_nothing_is_still_not_clean():
    layer = Layer()
    layer.report = FakeReport(ran=False, tier3=FakeTier(status="", reason=""))
    controller, _, results = _controller(layer)
    controller.open_session()

    controller.run_check(REQUEST)

    assert results[-1].ok is False
    assert "did not run" in results[-1].reason


def test_a_raising_ladder_is_a_stated_failure_not_an_exception():
    layer = Layer()
    layer.check_error = RuntimeError("relation \"pg_proc\" does not exist")
    controller, _, results = _controller(layer)
    controller.open_session()

    controller.run_check(REQUEST)  # must not raise

    assert results[-1].ok is False
    assert results[-1].reason == 'relation "pg_proc" does not exist'
    assert results[-1].report is None  # no report is NOT a clean report


def test_check_without_a_session_is_a_stated_refusal_and_no_gesture():
    layer = Layer()
    controller, runner, results = _controller(layer)

    assert controller.can_check is False  # the host hides the control entirely
    controller.run_check(REQUEST)

    assert results[-1].operation is SandboxOperation.CHECK
    assert results[-1].ok is False
    assert "no sandbox session" in results[-1].reason
    assert results[-1].report is None
    assert layer.check_calls == [] and runner.calls == 0


def test_can_check_follows_the_live_session():
    layer = Layer()
    controller, _, _ = _controller(layer)
    controller.open_session()
    assert controller.can_check is True

    controller.close_session()
    assert controller.can_check is False


def test_can_check_stays_true_when_plpgsql_check_is_absent():
    # An unavailable tier 3 is a reported OUTCOME, not a missing gesture.
    layer = Layer(caps=_caps(available_extensions=frozenset()))
    controller, _, _ = _controller(layer)
    controller.open_session()

    assert controller.can_check is True


def test_check_without_a_request_is_a_stated_refusal():
    layer = Layer()
    controller, runner, results = _controller(layer)
    controller.open_session()
    before = runner.calls

    controller.run_check(None)

    assert results[-1].ok is False
    assert "nothing to check" in results[-1].reason
    assert layer.check_calls == [] and runner.calls == before


def test_check_probes_inside_the_worker_when_capabilities_are_unknown():
    layer = Layer()
    controller, _, results = _controller(layer)
    controller.open_session()
    controller._capabilities = None  # as if nothing had probed yet
    before = len(layer.probe_calls)

    controller.run_check(REQUEST)

    # Capabilities are never guessed: a fresh probe feeds the ladder's gate,
    # and the result is cached and reported.
    assert len(layer.probe_calls) == before + 1
    assert layer.check_calls[-1][2] == layer.caps
    assert controller.capabilities == layer.caps
    assert results[-1].capabilities == layer.caps


def test_zero_argument_adapters_match_the_project_status_panels_callbacks():
    layer = Layer(session=RecordingSession(mode=SandboxMode.WITH_DATA))
    controller, _, _ = _controller(layer, mode=SandboxMode.WITH_DATA)
    controller.open_session()

    controller.on_run_data_clone()
    controller.on_install_plpgsql_check()

    assert layer.clone_calls == [(TARGET, SANDBOX)]
    assert layer.install_calls == [layer.session]
