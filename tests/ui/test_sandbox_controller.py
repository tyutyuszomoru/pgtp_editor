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
    """`set_project` is a MECHANISM: it records params and drops the previous
    session, and opens nothing itself.

    BUG-040 changed the POLICY, not this: the host
    (`MainWindow._bind_sandbox_controller_to_project`) calls `open_session`
    right after this, and that is where "a project opening connects" now lives.
    Keeping the split pinned here is what makes `open_sandbox` still the single
    ownership gate — one way in, with the host deciding when."""
    layer = Layer()
    controller, runner, _ = _controller(layer)

    assert controller.has_session is False
    assert controller.session is None
    assert controller.capabilities is None
    # Binding a project must not connect, provision, clone or reset.
    assert runner.calls == 0
    assert layer.probe_calls == [] and layer.provision_calls == []
    assert layer.open_calls == []


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


# ---------------------------------------------------------------------------
# 8. SandboxOperation.APPLY -- Apply to Sandbox (§18.5 D3)
# ---------------------------------------------------------------------------


class FakeLadderReport:
    """A duck-typed `ddl_check.CheckReport` as an APPLY reads it: `green`,
    `committed`, plus the four tiers."""

    def __init__(self, *, green=True, committed=True, tiers=None) -> None:
        self.green = green
        self.committed = committed
        default = FakeTier() if green else FakeTier("unavailable", "the reason")
        for name in ("tier0", "tier1", "tier2", "tier3"):
            setattr(self, name, (tiers or {}).get(name, default))
        self.findings = ()
        self.ran = green


class LadderLayer(Layer):
    """`Layer` plus the two writing ladder seams."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.apply_calls: list[tuple] = []
        self.probe_check_calls: list[tuple] = []
        self.ladder_report = FakeLadderReport()
        self.apply_error: BaseException | None = None

    def applier(self, session, request, caps, *, ddl_text=None):
        self.apply_calls.append((session, request, caps, ddl_text))
        if self.apply_error is not None:
            raise self.apply_error
        return self.ladder_report

    def probe_checker(self, session, request, caps, *, ddl_text=None):
        self.probe_check_calls.append((session, request, caps, ddl_text))
        return self.ladder_report


def _ladder_controller(layer: LadderLayer, **kwargs):
    controller, runner, results = _controller(
        layer, applier=layer.applier, probe_checker=layer.probe_checker, **kwargs
    )
    return controller, runner, results


def test_apply_is_a_named_operation():
    assert SandboxOperation.APPLY.value == "apply"


def test_apply_is_not_destructive():
    """`DESTRUCTIVE_OPERATIONS` means "drops and recreates schemas / overwrites
    the sandbox wholesale". An apply does none of that: `CREATE OR REPLACE` is
    idempotent and §18.5 D2 says the sandbox is MEANT to accumulate applied
    edits. Putting it behind the destructive prompt would train the user to click
    through the prompt that protects reset/provision/clone."""
    assert SandboxOperation.APPLY not in DESTRUCTIVE_OPERATIONS
    assert SandboxController.is_destructive(SandboxOperation.APPLY) is False
    assert SandboxController.destructive_warning(SandboxOperation.APPLY) == ""


def test_apply_never_consults_the_confirmation_seam():
    asked = []
    layer = LadderLayer()
    controller, _, results = _ladder_controller(
        layer, confirm=lambda warning: asked.append(warning) or True
    )
    controller.open_session()

    controller.run_apply("REQUEST")

    assert asked == []
    assert results[-1].operation is SandboxOperation.APPLY
    assert results[-1].ok is True


def test_apply_runs_the_ladder_off_the_gui_thread_and_reports_the_report():
    layer = LadderLayer()
    controller, runner, results = _ladder_controller(layer)
    controller.open_session()
    before = runner.calls

    controller.run_apply("REQUEST", ddl_text="CREATE FUNCTION ...")

    assert runner.calls == before + 1
    session, request, caps, ddl_text = layer.apply_calls[0]
    assert session is layer.session
    assert request == "REQUEST"
    assert caps is layer.caps
    assert ddl_text == "CREATE FUNCTION ..."
    assert results[-1].report is layer.ladder_report
    assert results[-1].ok is True
    assert results[-1].reason == ""


def test_apply_with_no_session_is_a_stated_refusal_not_a_clean_report():
    layer = LadderLayer()
    controller, _, results = _ladder_controller(layer)

    controller.run_apply("REQUEST")

    assert results[-1].operation is SandboxOperation.APPLY
    assert results[-1].ok is False
    assert results[-1].report is None
    assert "no sandbox session" in results[-1].reason
    assert layer.apply_calls == []


def test_apply_with_no_request_is_a_stated_refusal():
    layer = LadderLayer()
    controller, _, results = _ladder_controller(layer)
    controller.open_session()

    controller.run_apply(None)

    assert results[-1].ok is False
    assert "nothing to apply" in results[-1].reason


def test_an_unverified_tier_makes_the_apply_not_ok_and_names_it():
    """§18.5 D3's hard rule: an unavailable tier is never folded into the OK
    state, and the reason is that tier's own sentence."""
    layer = LadderLayer()
    layer.ladder_report = FakeLadderReport(
        green=False,
        tiers={"tier3": FakeTier("unavailable", "plpgsql_check is not installed")},
    )
    controller, _, results = _ladder_controller(layer)
    controller.open_session()

    controller.run_apply("REQUEST")

    assert results[-1].ok is False
    assert "plpgsql_check is not installed" in results[-1].reason
    assert results[-1].report is layer.ladder_report


def test_a_green_ladder_that_did_not_commit_is_not_a_successful_apply():
    """The one direction this must never be silent in -- the user pressed
    Apply."""
    layer = LadderLayer()
    layer.ladder_report = FakeLadderReport(green=True, committed=False)
    controller, _, results = _ladder_controller(layer)
    controller.open_session()

    controller.run_apply("REQUEST")

    assert results[-1].ok is False
    assert "NOTHING WAS APPLIED" in results[-1].reason


def test_probe_uses_the_probe_seam_and_is_never_reported_as_applied():
    layer = LadderLayer()
    layer.ladder_report = FakeLadderReport(green=True, committed=False)
    controller, _, results = _ladder_controller(layer)
    controller.open_session()

    controller.run_apply("REQUEST", probe=True)

    assert layer.apply_calls == []
    assert len(layer.probe_check_calls) == 1
    assert results[-1].ok is False
    assert "without applying" in results[-1].reason
    assert results[-1].report is layer.ladder_report


def test_an_exploding_ladder_reports_the_message_and_no_report():
    layer = LadderLayer()
    layer.apply_error = RuntimeError("thread pool died")
    controller, _, results = _ladder_controller(layer)
    controller.open_session()

    controller.run_apply("REQUEST")

    assert results[-1].ok is False
    assert "thread pool died" in results[-1].reason
    assert results[-1].report is None


def test_apply_probes_inside_the_worker_when_capabilities_are_unknown():
    """Capabilities come from the probe contract, never from a guess (D3a)."""
    layer = LadderLayer()
    controller, _, _ = _ladder_controller(layer)
    controller._session = layer.session
    controller._capabilities = None

    controller.run_apply("REQUEST")

    assert layer.probe_calls  # probed, rather than passing "unknown" off as fact
    assert layer.apply_calls[0][2] is layer.caps


def test_the_default_ladder_seams_are_ddl_checks_own_entry_points():
    from pgtp_editor.db.ddl_check import apply_and_check, probe_check

    controller = SandboxController()
    assert controller._applier is apply_and_check
    assert controller._probe_checker is probe_check


# ---------------------------------------------------------------------------
# 6. FQ-007 -- CREATE + provision an auto-named sandbox database
#
# The New Project step no longer asks for an existing database: the controller
# creates one, named by `generate_sandbox_database_names`, and provisions it. The
# only genuinely new decision here is *which* name gets created, so that is what
# these tests pin -- plus the two things this path must never do: overwrite an
# existing database, or leave the controller claiming a sandbox it did not build.
# ---------------------------------------------------------------------------
import re as _re  # noqa: E402 -- local to this section's name-shape assertions

from pgtp_editor.db.introspect import BaselineSnapshot  # noqa: E402
from pgtp_editor.db.sandbox import SANDBOX_DB_PREFIX  # noqa: E402
from pgtp_editor.ui.sandbox_controller import (  # noqa: E402
    MAINTENANCE_DATABASE,
    SandboxNameCollisionError,
    generate_sandbox_database_name,
    generate_sandbox_database_names,
    is_duplicate_database_error,
    sandbox_name_stem,
)

#: `db/sandbox.py::_SANDBOX_DB_NAME_RE`, restated here on purpose: a generated
#: name that does not satisfy it is refused by `create_sandbox_database`, so this
#: is the contract the generator has to meet.
_NAME_RE = _re.compile(r"^pgtp_sandbox_[a-z0-9_]{1,40}$")

ADMIN = ConnectionParams(host="localhost", port="5432", database=MAINTENANCE_DATABASE, user="me")
#: The sandbox *server* connection the New Project dialog now hands over --
#: no database name, because the database does not exist yet.
SERVER = ConnectionParams(host="localhost", port="5432", database="", user="me")


class DuplicateDatabase(Exception):
    """psycopg's `duplicate_database` as the controller reads it: duck-typed
    `sqlstate`, no driver import."""

    sqlstate = "42P04"

    def __init__(self, name: str) -> None:
        super().__init__(f'database "{name}" already exists')


def _new_db_controller(layer, *, confirm=True, mode=SandboxMode.SCHEMA_ONLY, target=TARGET):
    controller, runner, results = _controller(layer, confirm=confirm, mode=mode)
    controller.set_project(sandbox_params=SERVER, target_params=target, mode=mode)
    return controller, runner, results


# --- the name itself --------------------------------------------------------
def test_generated_names_satisfy_the_ownership_naming_convention():
    for project in ("ERP Overhaul", "", "  ", "árvíztűrő tükörfúrógép", "x" * 90):
        name = generate_sandbox_database_name(project)
        assert name.startswith(SANDBOX_DB_PREFIX)
        assert _NAME_RE.match(name), name


def test_generated_name_keeps_a_readable_project_stem_and_a_random_suffix():
    name = generate_sandbox_database_name("ERP Overhaul", suffix="abc12345")
    assert name == "pgtp_sandbox_erp_overhaul_abc12345"
    assert sandbox_name_stem("") == "project"  # never an empty stem


def test_generated_candidates_are_distinct():
    names = generate_sandbox_database_names("erp", count=5)
    assert len(names) == 5 and len(set(names)) == 5
    assert all(_NAME_RE.match(name) for name in names)


def test_duplicate_database_errors_are_recognised_by_sqlstate_or_message():
    assert is_duplicate_database_error(DuplicateDatabase("pgtp_sandbox_a")) is True
    assert is_duplicate_database_error(Exception('database "x" already exists')) is True
    assert is_duplicate_database_error(RuntimeError("permission denied")) is False


# --- the happy path ---------------------------------------------------------
def test_creates_the_first_candidate_provisions_it_and_reports_the_name():
    layer = Layer()
    controller, runner, results = _new_db_controller(layer)

    controller.provision_new_database(
        admin_params=ADMIN, name_candidates=["pgtp_sandbox_a", "pgtp_sandbox_b"]
    )

    assert runner.calls == 1  # off the GUI thread, like every DB-touching call
    assert layer.create_db_calls == [(ADMIN, "pgtp_sandbox_a")]
    # provisioned against the created database, not the empty server params
    _schema, params, mode, target = layer.provision_calls[0]
    assert params.database == "pgtp_sandbox_a" and params.host == "localhost"
    assert mode is SandboxMode.SCHEMA_ONLY and target is TARGET
    assert results[-1].ok is True
    assert results[-1].operation is SandboxOperation.PROVISION
    assert results[-1].database_name == "pgtp_sandbox_a"
    # and the controller now holds the session on exactly that database
    assert controller.has_session is True
    assert controller.sandbox_params.database == "pgtp_sandbox_a"
    assert layer.install_calls == [layer.session]


def test_the_baseline_comes_from_the_target_profile():
    layer = Layer()
    controller, _, _ = _new_db_controller(layer)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert layer.snapshot_calls == [TARGET]
    assert layer.provision_calls[0][0] == "SNAPSHOT"


# --- collisions -------------------------------------------------------------
def test_a_taken_name_is_skipped_for_the_next_generated_one():
    layer = Layer()
    taken = {"pgtp_sandbox_a", "pgtp_sandbox_b"}

    def creator(admin_params, name, **kwargs):
        layer.create_db_calls.append((admin_params, name))
        if name in taken:
            raise DuplicateDatabase(name)

    layer.database_creator = creator
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(
        admin_params=ADMIN,
        name_candidates=["pgtp_sandbox_a", "pgtp_sandbox_b", "pgtp_sandbox_c"],
    )

    assert [name for _params, name in layer.create_db_calls] == [
        "pgtp_sandbox_a", "pgtp_sandbox_b", "pgtp_sandbox_c",
    ]
    assert results[-1].ok is True and results[-1].database_name == "pgtp_sandbox_c"
    # the existing databases were never provisioned into -- nothing was destroyed
    assert layer.provision_calls[0][1].database == "pgtp_sandbox_c"


def test_every_name_taken_fails_without_touching_any_existing_database():
    layer = Layer()

    def creator(admin_params, name, **kwargs):
        layer.create_db_calls.append((admin_params, name))
        raise DuplicateDatabase(name)

    layer.database_creator = creator
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(
        admin_params=ADMIN, name_candidates=["pgtp_sandbox_a", "pgtp_sandbox_b"]
    )

    assert results[-1].ok is False
    assert "already exists" in results[-1].reason
    assert results[-1].database_name == ""
    assert layer.provision_calls == []  # never provisioned into someone else's DB
    assert controller.has_session is False


def test_a_non_collision_failure_is_reported_and_not_retried():
    layer = Layer()

    def creator(admin_params, name, **kwargs):
        layer.create_db_calls.append((admin_params, name))
        raise RuntimeError("permission denied for CREATE DATABASE")

    layer.database_creator = creator
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(
        admin_params=ADMIN, name_candidates=["pgtp_sandbox_a", "pgtp_sandbox_b"]
    )

    assert len(layer.create_db_calls) == 1  # not a collision -> no retry
    assert results[-1].ok is False
    assert "permission denied" in results[-1].reason
    assert controller.has_session is False


def test_the_collision_error_names_every_name_it_tried():
    error = SandboxNameCollisionError(["pgtp_sandbox_a", "pgtp_sandbox_b"])
    assert "pgtp_sandbox_a" in str(error) and "pgtp_sandbox_b" in str(error)
    assert "no existing database was touched" in str(error)


def test_no_candidates_is_a_stated_refusal_that_creates_nothing():
    layer = Layer()
    controller, runner, results = _new_db_controller(layer)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=[])

    assert results[-1].ok is False
    assert "no sandbox database name" in results[-1].reason
    assert layer.create_db_calls == [] and runner.calls == 0


# --- no target yet ----------------------------------------------------------
def test_with_no_target_the_sandbox_is_provisioned_empty_and_says_so():
    layer = Layer()
    controller, _, results = _new_db_controller(layer, target=ConnectionParams())

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert layer.snapshot_calls == []  # never connects to a target that isn't there
    assert isinstance(layer.provision_calls[0][0], BaselineSnapshot)
    assert results[-1].ok is True
    assert "created EMPTY" in results[-1].reason
    assert controller.has_session is True


def test_with_data_and_no_target_is_provisioned_schema_only_without_rewriting_the_mode():
    layer = Layer()
    controller, _, results = _new_db_controller(
        layer, mode=SandboxMode.WITH_DATA, target=ConnectionParams()
    )

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert layer.provision_calls[0][2] is SandboxMode.SCHEMA_ONLY
    assert "no data was cloned" in results[-1].reason
    # D2a: the recorded mode is the user's choice and is NOT rewritten here
    assert controller.mode is SandboxMode.WITH_DATA


# --- plpgsql_check installation degrades, never aborts ----------------------
def test_a_refused_plpgsql_check_install_still_leaves_a_working_sandbox():
    layer = Layer(caps=_caps(available_extensions=frozenset()))
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert layer.install_calls == []  # the pure gate said no
    assert results[-1].ok is True and controller.has_session is True
    assert "plpgsql_check was not installed" in results[-1].reason
    assert "C library" in results[-1].reason  # install_gate's own sentence


def test_a_failing_plpgsql_check_install_is_reported_not_swallowed():
    layer = Layer()
    layer.install_error = RuntimeError("must be superuser to create extension")
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert results[-1].ok is True and controller.has_session is True
    assert "must be superuser to create extension" in results[-1].reason


# --- destroys nothing, so confirms nothing ---------------------------------
def test_creating_a_brand_new_database_never_asks_the_destructive_confirmation():
    """It writes only into a database it just created; an existing one is skipped
    rather than overwritten, so there is nothing to confirm. The three operations
    that DO overwrite a sandbox keep their gate (asserted in section 3)."""
    asked = []
    layer = Layer()
    controller, _, results = _new_db_controller(
        layer, confirm=lambda warning: asked.append(warning) or True
    )

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert asked == []
    assert results[-1].ok is True


def test_it_works_with_no_confirmation_seam_at_all():
    layer = Layer()
    controller, _, results = _new_db_controller(layer, confirm=None)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert results[-1].ok is True and controller.has_session is True


# ---------------------------------------------------------------------------
# 6b. FQ-007 -- the seams between the generator and everything downstream
#
# Section 6 pins the flow; this section pins the *contracts* it depends on: that
# a generated name survives `create_sandbox_database`'s own "validated, not
# sanitized" gate (the whole ownership convention rests on that), that the retry
# only ever fires for a real duplicate-database error, and that a failure leaves
# nothing behind for the host to record.
# ---------------------------------------------------------------------------
from pgtp_editor.db.sandbox import (  # noqa: E402
    OWNER_MARKER_PREFIX,
    create_sandbox_database,
    install_gate,
    is_app_owned,
)
from pgtp_editor.ui.sandbox_controller import (  # noqa: E402
    DEFAULT_NAME_ATTEMPTS,
    DUPLICATE_DATABASE_SQLSTATE,
)


# --- the name is accepted by the real creator -------------------------------
def test_a_generated_name_passes_create_sandbox_databases_own_validation():
    """The one contract that matters: `create_sandbox_database` VALIDATES rather
    than sanitizes, so a generator that drifts out of `^pgtp_sandbox_[a-z0-9_]
    {1,40}$` would make every New Project sandbox refuse itself. Asserted against
    the real function (with the autocommit runner injected), not a copy of its
    regex, and all the way to `is_app_owned` seeing the marker it stamps."""
    statements: list[str] = []
    for project in ("ERP Overhaul", "", "árvíztűrő tükörfúrógép", "x" * 120, "9-9-9"):
        name = generate_sandbox_database_name(project)
        create_sandbox_database(
            ADMIN, name, runner=lambda _params, sql: statements.extend(sql)
        )
        create_sql, comment_sql = statements[-2:]
        assert create_sql == f'CREATE DATABASE "{name}"'
        marker = comment_sql.split(" IS ", 1)[1].strip().strip("'")
        assert marker.startswith(OWNER_MARKER_PREFIX)
        # Both halves of the §18.5 D2 ownership test hold for what we created.
        assert is_app_owned(name, marker) is True


def test_every_generated_candidate_passes_that_same_validation():
    for name in generate_sandbox_database_names("ERP Overhaul"):
        create_sandbox_database(ADMIN, name, runner=lambda _params, _sql: None)


# --- the stem's budget ------------------------------------------------------
def test_a_long_project_name_is_truncated_to_a_legal_stem_with_no_stray_underscore():
    name = generate_sandbox_database_name("a" * 25 + " " + "b" * 25, suffix="abc12345")
    assert _NAME_RE.match(name), name
    stem = name[len(SANDBOX_DB_PREFIX):-len("_abc12345")]
    assert not stem.startswith("_") and not stem.endswith("_")
    # truncation happens in the stem, not by shortening the random suffix
    assert name.endswith("_abc12345")


def test_a_name_that_truncates_onto_a_separator_keeps_no_trailing_underscore():
    # 30 characters then a space: naive truncation would leave "…_" as the stem.
    stem = sandbox_name_stem("c" * 30 + " tail")
    assert not stem.endswith("_")
    assert _NAME_RE.match(f"{SANDBOX_DB_PREFIX}{stem}")


def test_a_punctuation_only_project_name_still_yields_the_fallback_stem():
    for project in ("!!!", "---", "   ", "@@@ ###"):
        assert sandbox_name_stem(project) == "project"
        assert _NAME_RE.match(generate_sandbox_database_name(project))


def test_a_pinned_suffix_longer_than_the_budget_is_truncated_not_appended_whole():
    name = generate_sandbox_database_name("erp", suffix="deadbeefcafebabe")
    assert name == "pgtp_sandbox_erp_deadbeef"
    assert _NAME_RE.match(name)


# --- the candidate list -----------------------------------------------------
def test_the_default_candidate_count_is_the_declared_retry_bound():
    assert len(generate_sandbox_database_names("erp")) == DEFAULT_NAME_ATTEMPTS


def test_a_zero_or_negative_count_still_yields_one_usable_candidate():
    for count in (0, -3):
        names = generate_sandbox_database_names("erp", count=count)
        assert len(names) == 1 and _NAME_RE.match(names[0])


def test_two_projects_with_the_same_name_get_different_databases():
    """Every project creation ends with a brand-new, uniquely named sandbox --
    the whole reason the name carries a random suffix (FQ-007 Q2)."""
    first = generate_sandbox_database_names("ERP Overhaul")
    second = generate_sandbox_database_names("ERP Overhaul")
    assert not set(first) & set(second)


# --- what counts as a collision --------------------------------------------
def test_a_duplicate_database_error_is_recognised_through_psycopgs_diag():
    class WithDiag(Exception):
        diag = type("Diag", (), {"sqlstate": DUPLICATE_DATABASE_SQLSTATE})()

    assert is_duplicate_database_error(WithDiag("boom")) is True


def test_another_objects_already_exists_error_is_not_read_as_a_name_collision():
    """A retry must be reserved for "that database name is taken". Anything else
    -- a duplicate table, schema or extension inside the provisioning -- is a
    real failure, because retrying it would create databases in a loop."""
    assert is_duplicate_database_error(Exception('relation "t" already exists')) is False
    assert is_duplicate_database_error(Exception('schema "s" already exists')) is False
    assert is_duplicate_database_error(Exception("duplicate key value")) is False


def test_a_wrong_sqlstate_is_not_read_as_a_name_collision():
    class Insufficient(Exception):
        sqlstate = "42501"  # insufficient_privilege

    assert is_duplicate_database_error(Insufficient("permission denied")) is False


# --- failure leaves nothing to record ---------------------------------------
def test_an_unconfigured_sandbox_refuses_before_creating_anything():
    layer = Layer()
    controller, runner, results = _controller(layer)
    controller.clear_project()

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert results[-1].ok is False
    assert "no local sandbox configured" in results[-1].reason
    assert layer.create_db_calls == [] and runner.calls == 0


def test_a_failure_leaves_the_controller_pointing_at_no_sandbox_database():
    """The host records `result.database_name` -- so a failed run must not adopt
    a half-built database into the controller's own params either, or the tier it
    reports would describe a database nobody created."""
    layer = Layer()

    def creator(admin_params, name, **kwargs):
        layer.create_db_calls.append((admin_params, name))
        raise RuntimeError("permission denied for CREATE DATABASE")

    layer.database_creator = creator
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert results[-1].database_name == ""
    assert controller.sandbox_params.database == ""  # still the server-only params
    assert controller.has_session is False


def test_a_provisioning_failure_after_a_successful_create_still_reports_no_name():
    layer = Layer()
    layer.provisioner = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("baseline failed"))
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert layer.create_db_calls == [(ADMIN, "pgtp_sandbox_a")]
    assert results[-1].ok is False and results[-1].database_name == ""
    assert "baseline failed" in results[-1].reason
    assert controller.has_session is False


# --- the capability picture the host re-reads -------------------------------
def test_capabilities_are_reprobed_after_the_extension_install():
    """The result's capabilities have to describe the database AFTER the install,
    or the New Project flow would record tier 2 for a sandbox that can lint."""
    layer = Layer()
    before = _caps(installed_extensions=frozenset())
    after = _caps(installed_extensions=frozenset({"plpgsql_check"}))
    probed: list[ConnectionParams] = []

    def prober(params):
        probed.append(params)
        return before if len(probed) == 1 else after

    layer.prober = prober
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    assert len(probed) == 2
    assert all(params.database == "pgtp_sandbox_a" for params in probed)
    assert results[-1].capabilities is after
    assert controller.capabilities is after
    assert controller.capability_status().tier.value == "development"


def test_a_refused_install_carries_the_pure_gates_own_reason_verbatim():
    caps = _caps(available_extensions=frozenset())
    layer = Layer(caps=caps)
    controller, _, results = _new_db_controller(layer)

    controller.provision_new_database(admin_params=ADMIN, name_candidates=["pgtp_sandbox_a"])

    _offered, reason = install_gate(caps)
    assert reason and reason in results[-1].reason  # the shipped sentence, not a copy


def test_only_the_new_database_operation_reports_a_database_name():
    """`database_name` is empty for every other operation, so no caller can
    mistake an ordinary provision/open for "a database was created"."""
    layer = Layer()
    controller, _, results = _controller(layer)

    controller.open_session()
    assert results[-1].database_name == ""
    controller.provision(admin_params=ADMIN, database_name="pgtp_sandbox_dev")
    assert results[-1].operation is SandboxOperation.PROVISION
    assert results[-1].database_name == ""


def test_the_maintenance_database_is_one_constant_shared_with_the_setup_dialog():
    from pgtp_editor.ui import sandbox_setup_dialog

    assert MAINTENANCE_DATABASE == "postgres"
    assert sandbox_setup_dialog.DEFAULT_MAINTENANCE_DATABASE is MAINTENANCE_DATABASE
