# tests/db/test_ddl_check.py
"""Tests for the tier-3 validation driver (`db/ddl_check.py`) — no Qt, no live DB.

Every case is canned: `run_plpgsql_check` takes an injectable `query=` seam, so
nothing here opens a connection and psycopg need not be importable. The last
test in this file asserts exactly that.

The recurring theme is the module's one hard correctness property: a check that
did not run must never be reportable as clean. Each "could not check" path is
asserted to produce its OWN reason, not merely a falsy finding list.
"""

import dataclasses

import pytest

from pgtp_editor.db import ddl_check
from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_check import (
    CHECK_COLUMNS,
    CheckFinding,
    CheckReport,
    CheckRequest,
    MalformedCheckOutputError,
    STATUS_ERRORED,
    STATUS_FOUND_ISSUES,
    STATUS_PASSED,
    STATUS_UNAVAILABLE,
    body_line_offset,
    build_check_sql,
    build_resolve_sql,
    capability_outcome,
    map_lineno,
    parse_findings,
    recheck,
    run_plpgsql_check,
    severity_for_level,
)
from pgtp_editor.db.sandbox import (
    REASON_REQUIRES_SUPERUSER,
    AppliedObject,
    SandboxCapabilities,
    UnsafeIdentifierError,
)

PARAMS = ConnectionParams(host="h", port=5432, database="pgtp_sandbox_x", user="u")

BUFFER = """CREATE OR REPLACE FUNCTION pr.f(i integer)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
  SELECT missing FROM pr.t;
  RETURN;
END;
$function$
"""


class _Session:
    """The two attributes `CheckSession` needs. `executor.query` raises if it
    is ever reached -- every test injects `query=` instead."""

    def __init__(self):
        self.params = PARAMS
        self.executor = self

    def query(self, params, sql):  # pragma: no cover -- must never be called
        raise AssertionError("the default executor must never be reached in tests")


def _caps(state="installed", **kwargs):
    """SandboxCapabilities whose `plpgsql_check_state` is `state`."""
    if state == "installed":
        kwargs.setdefault("installed_extensions", frozenset({"plpgsql_check"}))
    elif state == "installable":
        kwargs.setdefault("available_extensions", frozenset({"plpgsql_check"}))
    elif state == "unknown":
        kwargs.setdefault("probe_error", "connection refused")
    caps = SandboxCapabilities(**kwargs)
    assert caps.plpgsql_check_state == state
    return caps


def _request(**kwargs):
    kwargs.setdefault("kind", "function")
    kwargs.setdefault("schema", "pr")
    kwargs.setdefault("name", "f")
    kwargs.setdefault("arg_types", ("integer",))
    kwargs.setdefault("buffer_text", BUFFER)
    return CheckRequest(**kwargs)


def _row(lineno=6, level="error", message="record has no field \"foo\"", **over):
    """One `plpgsql_check_function_tb` row, in its documented 11-column order."""
    values = {
        "functionid": "pr.f",
        "lineno": lineno,
        "statement": "SQL statement",
        "sqlstate": "42703",
        "message": message,
        "detail": "detail text",
        "hint": "hint text",
        "level": level,
        "position": 12,
        "query": "SELECT missing FROM pr.t",
        "context": "context text",
    }
    values.update(over)
    return tuple(values[name.strip('"')] for name in CHECK_COLUMNS)


class _Query:
    """A canned `query=` seam: returns the queued results in order and records
    the SQL it was asked to run."""

    def __init__(self, *results):
        self.results = list(results)
        self.sql = []

    def __call__(self, params, sql):
        self.sql.append(sql)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _resolved(funcoid=1234, relid=None):
    return [(funcoid, relid)]


# --- findings: level / message / line -------------------------------------

def test_findings_carry_level_message_and_mapped_line():
    query = _Query(_resolved(), [_row(lineno=3)])
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=query)

    assert report.tier3.status == STATUS_FOUND_ISSUES
    (finding,) = report.findings
    assert finding.level == "error"
    assert finding.severity == "error"
    assert finding.message == 'record has no field "foo"'
    # `AS $function$` is buffer line 4, so prosrc line 3 is buffer line 6.
    assert body_line_offset(BUFFER) == 4
    assert finding.line == 6
    assert finding.source_lineno == 3
    assert finding.identity == "pr.f(integer)"


def test_finding_lineno_alias_is_the_buffer_line_not_the_prosrc_line():
    # ui/ddl_object_editor.py::_result_lines prefers `lineno` over `line`; if
    # the raw prosrc number were exposed under that name every rendered
    # finding would point at the wrong statement.
    query = _Query(_resolved(), [_row(lineno=3)])
    (finding,) = run_plpgsql_check(_Session(), _request(), _caps(), query=query).findings
    assert finding.lineno == finding.line == 6
    assert finding.lineno != finding.source_lineno


def test_finding_without_a_mappable_line_degrades_to_none_and_says_so():
    request = _request(buffer_text="CREATE FUNCTION pr.f() RETURNS void LANGUAGE sql")
    query = _Query(_resolved(), [_row(lineno=3)])
    report = run_plpgsql_check(_Session(), request, _caps(), query=query)
    (finding,) = report.findings
    assert finding.line is None
    assert finding.source_lineno == 3
    assert ddl_check.CAVEAT_UNMAPPED_LINES in report.caveats


def test_every_ran_report_states_the_blind_spots():
    query = _Query(_resolved(), [])
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=query)
    for caveat in ddl_check.BLIND_SPOT_CAVEATS:
        assert caveat in report.caveats


@pytest.mark.parametrize(
    "level,severity",
    [
        ("error", "error"),
        ("warning", "warning"),
        ("warning extra", "warning"),
        ("warning performance", "warning"),
        ("warning security", "warning"),
        # §18.5 D3a pins `compatibility` to the INFO token, i.e. "notice".
        ("compatibility", "notice"),
        ("notice", "notice"),
        ("something new", "warning"),  # never demoted to notice
    ],
)
def test_severity_mapping_keeps_the_raw_level(level, severity):
    assert severity_for_level(level) == severity
    query = _Query(_resolved(), [_row(level=level)])
    (finding,) = run_plpgsql_check(_Session(), _request(), _caps(), query=query).findings
    assert finding.level == level
    assert finding.severity == severity


@pytest.mark.parametrize(
    "level",
    ["error", "warning", "warning extra", "warning performance", "warning security",
     "compatibility"],
)
def test_a_level_the_table_knows_is_not_annotated_onto_the_message(level):
    # The six levels §18.5 D3a's table names carry no parenthetical: the raw
    # level is already fully described by the mapped SEVERITY token.
    assert ddl_check.is_known_level(level) is True
    query = _Query(_resolved(), [_row(level=level, message="m")])
    (finding,) = run_plpgsql_check(_Session(), _request(), _caps(), query=query).findings
    assert finding.message == "m"
    assert finding.level == level


@pytest.mark.parametrize("level", ["something new", "deprecation", "WARNING SOMETHING-NEW"])
def test_an_unknown_level_is_warning_and_appended_to_the_message(level):
    # §18.5 D3a: anything the table does not know maps to WARNING *and* has its
    # raw level appended in parentheses -- never dropped, never mapped to INFO.
    assert ddl_check.is_known_level(level) is False
    assert severity_for_level(level) == "warning"
    query = _Query(_resolved(), [_row(level=level, message="m")])
    (finding,) = run_plpgsql_check(_Session(), _request(), _caps(), query=query).findings
    assert finding.severity == "warning"
    assert finding.message == f"m ({level})"
    # The raw level stays on the finding as well -- the parenthetical is for the
    # Audit renderer, which shows only severity/line/message.
    assert finding.level == level


def test_a_future_warning_subclass_counts_as_unknown_and_is_named():
    # The boundary decision: `startswith("warning")` gets the SEVERITY right,
    # but the table lists exactly four warning variants, so a new warning class
    # is still a level this build has never heard of and must be named.
    level = "warning brand-new"
    assert ddl_check.is_known_level(level) is False
    assert severity_for_level(level) == "warning"
    query = _Query(_resolved(), [_row(level=level, message="m")])
    (finding,) = run_plpgsql_check(_Session(), _request(), _caps(), query=query).findings
    assert finding.message == "m (warning brand-new)"
    assert finding.severity == "warning"


def test_a_blank_level_adds_no_empty_parenthetical():
    # Nothing to preserve, so "m ()" would be noise rather than information.
    query = _Query(_resolved(), [_row(level="", message="m")])
    (finding,) = run_plpgsql_check(_Session(), _request(), _caps(), query=query).findings
    assert finding.message == "m"
    assert finding.severity == "warning"


@pytest.mark.parametrize(
    "level",
    ["", "  ", "ERROR", " Warning Extra ", "Compatibility", "notice", "info",
     "something new", "warning brand-new", "error also-new", "ünicode",
     "12345"],
)
def test_the_level_mapping_is_total(level):
    # §18.5 D3a calls the mapping "fixed and total": no level input, however
    # odd, can produce an unmapped severity or crash.
    assert severity_for_level(level) in ("error", "warning", "notice")
    assert isinstance(ddl_check.message_for_level("m", level), str)


def test_the_mapping_lives_in_exactly_one_place():
    # D3a: "applied in exactly one place". parse_findings must not re-derive a
    # severity of its own -- it delegates, so patching the single mapping
    # changes every finding.
    assert parse_findings([_row(level="compatibility")], _request())[0].severity == "notice"


# --- clean vs. impossible --------------------------------------------------

def test_clean_run_is_passed_and_distinguishable_from_an_impossible_one():
    clean = run_plpgsql_check(_Session(), _request(), _caps(), query=_Query(_resolved(), []))
    impossible = run_plpgsql_check(_Session(), _request(), _caps("absent"), query=_Query())

    assert clean.findings == () and impossible.findings == ()
    assert clean.tier3.status == STATUS_PASSED
    assert clean.ran is True
    assert impossible.tier3.status == STATUS_UNAVAILABLE
    assert impossible.ran is False
    # The one property that matters: an empty finding list alone cannot be
    # mistaken for a clean result.
    assert clean.tier3.status != impossible.tier3.status


def test_a_report_that_did_not_run_carries_no_blind_spot_caveats():
    report = run_plpgsql_check(_Session(), _request(), _caps("absent"), query=_Query())
    assert report.caveats == ()


# --- the four capability states -------------------------------------------

def test_capability_installed_is_the_only_runnable_state():
    assert capability_outcome(_caps("installed")) is None


@pytest.mark.parametrize("state", ["installable", "absent", "unknown"])
def test_non_installed_capability_states_never_run_a_query(state):
    query = _Query()  # empty: popping from it would IndexError
    report = run_plpgsql_check(_Session(), _request(), _caps(state), query=query)
    assert report.tier3.status == STATUS_UNAVAILABLE
    assert report.tier3.reason
    assert query.sql == []


def test_the_three_non_installed_states_give_three_distinct_reasons():
    reasons = {
        "installable": capability_outcome(_caps("installable", is_superuser=True)).reason,
        "absent": capability_outcome(_caps("absent")).reason,
        "unknown": capability_outcome(_caps("unknown")).reason,
    }
    assert len(set(reasons.values())) == 3
    assert reasons["installable"] == ddl_check.REASON_NOT_INSTALLED
    assert reasons["unknown"] == ddl_check.REASON_UNKNOWN_CAPABILITY
    assert "administrator" in reasons["absent"]


def test_installable_names_the_one_click_install_and_where_it_lives():
    # §18.5 D3a: the `installable` case must name the install and both places
    # it is reachable from -- verbatim.
    reason = capability_outcome(_caps("installable", is_superuser=True)).reason
    assert (
        "Install it from Database ▸ Sandbox Setup…, or the Project Status "
        "window's plpgsql_check node." in reason
    )
    assert "NOT been linted" in reason


def test_installable_without_superuser_shows_install_gates_own_sentence():
    # Not re-typed here: the sentence comes from install_gate, and pointing a
    # non-superuser at a button they are not offered would be worse than mute.
    reason = capability_outcome(_caps("installable", is_superuser=False)).reason
    assert REASON_REQUIRES_SUPERUSER in reason
    assert "Sandbox Setup" not in reason
    assert reason == f"{ddl_check.REASON_NOT_INSTALLED_BASE} {REASON_REQUIRES_SUPERUSER}"
    # It is still `unavailable` -- never a clean or green result.
    assert capability_outcome(_caps("installable")).status == STATUS_UNAVAILABLE


def test_unknown_capability_carries_the_probe_error_as_detail():
    outcome = capability_outcome(_caps("unknown"))
    assert outcome.detail == "connection refused"


# --- tiers 0-2 are reported as unbuilt, never omitted ----------------------

def test_tiers_zero_to_two_are_explicitly_unavailable():
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=_Query(_resolved(), []))
    for tier in (report.tier0, report.tier1, report.tier2):
        assert tier.status == STATUS_UNAVAILABLE
        assert "db/apply.py" in tier.reason
        assert tier.verified is False


# --- trigger invocation differs -------------------------------------------

def test_trigger_check_targets_the_function_and_passes_relid():
    request = CheckRequest(
        kind="trigger",
        schema="pr",
        name="trg_audit",
        table="orders",
        function_schema="pr",
        function_name="audit_fn",
        buffer_text=BUFFER,
    )
    query = _Query(_resolved(funcoid=99, relid=77), [])
    report = run_plpgsql_check(_Session(), request, _caps(), query=query)

    resolve_sql, check_sql = query.sql
    assert 'to_regprocedure(\'"pr"."audit_fn"()\')' in resolve_sql
    assert 'to_regclass(\'"pr"."orders"\')' in resolve_sql
    assert "funcoid => 99" in check_sql
    assert "relid => 77" in check_sql
    assert report.tier3.status == STATUS_PASSED
    # A trigger's own ref args are never sent: a trigger function takes none.
    assert request.checked_arg_types == ()
    assert request.identity == "pr.audit_fn()"


def test_non_trigger_check_sends_no_relid():
    query = _Query(_resolved(), [])
    run_plpgsql_check(_Session(), _request(), _caps(), query=query)
    assert "relid =>" not in query.sql[1]
    assert "NULL::oid" in query.sql[0]


def test_trigger_transition_tables_are_passed_through():
    request = CheckRequest(
        kind="trigger",
        schema="pr",
        name="trg",
        table="orders",
        function_schema="pr",
        function_name="fn",
        oldtable="old_rows",
        newtable="new_rows",
    )
    query = _Query(_resolved(funcoid=1, relid=2), [])
    run_plpgsql_check(_Session(), request, _caps(), query=query)
    assert "oldtable => 'old_rows'" in query.sql[1]
    assert "newtable => 'new_rows'" in query.sql[1]


def test_trigger_whose_function_is_unknown_reports_unavailable():
    request = CheckRequest(kind="trigger", schema="pr", name="trg", table="orders")
    query = _Query()
    report = run_plpgsql_check(_Session(), request, _caps(), query=query)
    assert report.tier3.status == STATUS_UNAVAILABLE
    assert report.tier3.reason == ddl_check.REASON_TRIGGER_FUNCTION_UNKNOWN
    assert query.sql == []


def test_trigger_whose_relation_is_missing_reports_unavailable():
    request = CheckRequest(
        kind="trigger",
        schema="pr",
        name="trg",
        table="orders",
        function_schema="pr",
        function_name="fn",
    )
    query = _Query(_resolved(funcoid=5, relid=None))
    report = run_plpgsql_check(_Session(), request, _caps(), query=query)
    assert report.tier3.status == STATUS_UNAVAILABLE
    assert report.tier3.reason == ddl_check.REASON_RELATION_ABSENT


# --- call shape ------------------------------------------------------------

def test_check_sql_uses_named_notation_and_gui_friendly_flags():
    sql = build_check_sql(_request(), 42)
    assert "plpgsql_check_function_tb(" in sql
    assert "funcoid => 42" in sql
    assert "fatal_errors => false" in sql
    assert "all_warnings => true" in sql
    assert '"position"' in sql  # reserved word, must stay quoted
    assert sql.count(",") >= 10  # all eleven columns selected


def test_resolve_sql_uses_to_regprocedure_not_a_cast():
    sql = build_resolve_sql(_request())
    assert "to_regprocedure" in sql
    assert "::regprocedure" not in sql


def test_hostile_identifiers_are_refused_not_interpolated():
    with pytest.raises(UnsafeIdentifierError):
        build_resolve_sql(_request(name='f"; DROP TABLE t; --'))
    with pytest.raises(UnsafeIdentifierError):
        build_resolve_sql(_request(arg_types=("integer'); DROP TABLE t; --",)))


# --- the object is not in the sandbox (e.g. it never compiled) -------------

def test_object_absent_from_the_sandbox_is_unavailable_not_clean():
    query = _Query(_resolved(funcoid=None))
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=query)
    assert report.tier3.status == STATUS_UNAVAILABLE
    assert report.tier3.reason == ddl_check.REASON_OBJECT_ABSENT
    assert report.findings == ()
    assert len(query.sql) == 1  # the check itself was never attempted


def test_empty_resolution_result_is_unavailable_not_clean():
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=_Query([]))
    assert report.tier3.status == STATUS_UNAVAILABLE
    assert report.tier3.reason == ddl_check.REASON_OBJECT_ABSENT


# --- executor errors -------------------------------------------------------

def test_executor_error_during_resolution_is_errored():
    query = _Query(RuntimeError("connection lost"))
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=query)
    assert report.tier3.status == STATUS_ERRORED
    assert "connection lost" in report.tier3.reason
    assert report.findings == ()


def test_executor_error_during_the_check_call_is_errored():
    query = _Query(_resolved(), RuntimeError("function plpgsql_check_function_tb does not exist"))
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=query)
    assert report.tier3.status == STATUS_ERRORED
    assert "does not exist" in report.tier3.reason


# --- malformed output ------------------------------------------------------

def test_malformed_row_is_errored_never_a_shorter_finding_list():
    query = _Query(_resolved(), [_row(), ("too", "few")])
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=query)
    assert report.tier3.status == STATUS_ERRORED
    assert "2 column(s)" in report.tier3.reason
    assert report.findings == ()


def test_parse_findings_raises_on_a_non_row():
    with pytest.raises(MalformedCheckOutputError):
        parse_findings([123], _request())


# --- line mapping ----------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        (BUFFER, 4),
        ("CREATE FUNCTION f() RETURNS void AS $$ BEGIN END $$", 1),
        ("-- a $$ in a comment\nAS $body$\nBEGIN", 2),
        ("CREATE FUNCTION f() LANGUAGE sql RETURN 1", None),
        ("", None),
    ],
)
def test_body_line_offset(text, expected):
    assert body_line_offset(text) == expected


@pytest.mark.parametrize("lineno", [0, None, -1])
def test_map_lineno_refuses_a_falsy_lineno(lineno):
    assert map_lineno(BUFFER, lineno) is None


def test_map_lineno_refuses_an_out_of_range_result():
    assert map_lineno(BUFFER, 999) is None


def test_map_lineno_first_prosrc_line_is_the_opener_line():
    assert map_lineno(BUFFER, 1) == body_line_offset(BUFFER)


# --- shape the DDL object editor panel consumes ---------------------------

def test_report_shape_matches_what_ddl_object_editor_reads():
    from pgtp_editor.ui import ddl_object_editor as panel

    query = _Query(_resolved(), [_row(lineno=3)])
    report = run_plpgsql_check(_Session(), _request(), _caps(), query=query)

    names = [name for name, _ in panel.tier_outcomes(report)]
    assert names == ["tier0", "tier1", "tier2", "tier3"]
    # Findings are a hard, non-overridable Apply-to-Target blocker...
    assert panel.report_blockers(report)
    # ...and the unbuilt tiers are enumerated as "could not check".
    unverified = panel.report_unverified(report)
    assert any(line.startswith("tier0: unavailable") for line in unverified)
    assert not any(line.startswith("tier3:") for line in unverified)


def test_clean_report_has_no_blockers_for_the_panel():
    from pgtp_editor.ui import ddl_object_editor as panel

    report = run_plpgsql_check(_Session(), _request(), _caps(), query=_Query(_resolved(), []))
    assert panel.report_blockers(report) == []


def test_recheck_is_the_check_gesture_and_applies_nothing():
    session = _Session()
    query = _Query(_resolved(), [])
    report = recheck(session, _request(), _caps(), query=query)
    assert report.tier3.status == STATUS_PASSED
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in query.sql)


def test_from_ref_reads_a_duck_typed_ddl_object_ref():
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    ref = DdlObjectRef(kind="function", schema="pr", name="f", arg_types=("integer",))
    request = CheckRequest.from_ref(ref, BUFFER)
    assert request.identity == "pr.f(integer)"
    assert request.buffer_text == BUFFER


# --- the working-set sweep (§18.5 D3a) ------------------------------------
#
# The sweep is specified as a PURE LOOP over `SandboxSession.applied()` that
# calls the same `recheck` entry point per row, so these tests assert the seam
# and the loop -- never a second reporting path. A stub session and a stub
# `recheck` mean nothing here can reach a database.

class _SweepSession:
    """A `SandboxSession` slice with a canned `applied()` working set."""

    def __init__(self, *rows):
        self.params = PARAMS
        self.executor = self
        self.rows = list(rows)

    def applied(self):
        return list(self.rows)

    def query(self, params, sql):  # pragma: no cover -- must never be called
        raise AssertionError("the sweep must never reach an executor")


def _applied(kind="function", schema_name="pr", object_name="f", table_name=""):
    """One real `applied` bookkeeping row -- the shape the sweep iterates."""
    return AppliedObject(
        kind=kind,
        schema_name=schema_name,
        object_name=object_name,
        table_name=table_name,
        applied_at="2026-08-06T00:00:00+00:00",
        text_sha1="deadbeef",
    )


class _StubRecheck:
    """A stub `recheck`: records every call and returns a queued report (or
    raises a queued exception) per invocation."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, session, request, caps, *, query=None):
        self.calls.append((session, request, caps, query))
        result = self.results.pop(0) if self.results else _passed("queued out")
        if isinstance(result, Exception):
            raise result
        return result


def _passed(reason="clean"):
    return CheckReport(tier3=ddl_check.TierOutcome(status=STATUS_PASSED, reason=reason))


def test_sweep_of_an_empty_working_set_is_an_empty_dict():
    stub = _StubRecheck()
    reports = ddl_check.check_working_set(_SweepSession(), _caps(), recheck=stub)
    assert reports == {}
    assert stub.calls == []


def test_sweep_maps_each_row_to_its_own_report():
    session = _SweepSession(
        _applied(object_name="f"),
        _applied(kind="procedure", object_name="p"),
        _applied(kind="trigger", object_name="trg", table_name="orders"),
    )
    first, second, third = _passed("f"), _passed("p"), _passed("trg")
    stub = _StubRecheck(first, second, third)

    reports = ddl_check.check_working_set(session, _caps(), recheck=stub)

    assert reports == {
        ("function", "pr", "f", ""): first,
        ("procedure", "pr", "p", ""): second,
        ("trigger", "pr", "trg", "orders"): third,
    }
    # Every value is the report `recheck` produced, untouched -- the sweep is
    # not a second reporting path.
    assert [r.tier3.reason for r in reports.values()] == ["f", "p", "trg"]


def test_sweep_calls_the_recheck_seam_once_per_row_with_that_row_s_ref():
    session = _SweepSession(
        _applied(object_name="f"),
        _applied(schema_name="app", object_name="g"),
    )
    stub = _StubRecheck()
    query = _Query()  # never popped from: the stub never runs SQL

    ddl_check.check_working_set(session, _caps(), recheck=stub, query=query)

    assert len(stub.calls) == len(session.rows)
    identities = [call[1].identity for call in stub.calls]
    assert identities == ["pr.f()", "app.g()"]
    for call_session, _request, caps, passed_query in stub.calls:
        assert call_session is session       # the same session, not a copy
        assert caps is not None and passed_query is query
    assert query.sql == []


def test_sweep_passes_no_sql_of_its_own_and_composes_no_request_for_a_trigger():
    # A trigger row carries no referenced function, so the request the sweep
    # builds is the one `recheck` already reports as unavailable -- the sweep
    # does not invent a function name for it.
    session = _SweepSession(_applied(kind="trigger", object_name="trg", table_name="orders"))
    stub = _StubRecheck()
    ddl_check.check_working_set(session, _caps(), recheck=stub)
    (request,) = [call[1] for call in stub.calls]
    assert request.is_trigger
    assert request.function_name is None
    assert request.table == "orders"
    # ...and the real entry point reports that honestly rather than guessing.
    report = recheck(_Session(), request, _caps(), query=_Query())
    assert report.tier3.status == STATUS_UNAVAILABLE
    assert report.tier3.reason == ddl_check.REASON_TRIGGER_FUNCTION_UNKNOWN


def test_sweep_row_whose_recheck_raises_does_not_abort_the_sweep():
    session = _SweepSession(
        _applied(object_name="f"),
        _applied(object_name="boom"),
        _applied(object_name="g"),
    )
    good, other = _passed("f"), _passed("g")
    stub = _StubRecheck(good, UnsafeIdentifierError("boom"), other)

    reports = ddl_check.check_working_set(session, _caps(), recheck=stub)

    # Every applied row still has an entry -- a dropped row would read as a
    # smaller working set.
    assert set(reports) == {
        ("function", "pr", "f", ""),
        ("function", "pr", "boom", ""),
        ("function", "pr", "g", ""),
    }
    failed = reports[("function", "pr", "boom", "")]
    assert failed.tier3.status == STATUS_ERRORED
    assert "boom" in failed.tier3.reason
    assert failed.ran is False        # never readable as green
    assert failed.findings == ()
    # The rows after the failure were still checked.
    assert reports[("function", "pr", "g", "")] is other
    assert len(stub.calls) == 3


def test_sweep_default_recheck_is_the_modules_own_gesture():
    import inspect

    default = inspect.signature(ddl_check.check_working_set).parameters["recheck"].default
    assert default is ddl_check.recheck


def test_request_from_applied_degrades_honestly_rather_than_guessing():
    request = ddl_check.request_from_applied(_applied(object_name="f"))
    assert request.arg_types == ()      # the bookkeeping table records none
    assert request.buffer_text == ""    # so findings get no line, not a wrong one
    assert ddl_check.applied_ref(_applied()) == ("function", "pr", "f", "")


def test_sweep_reads_the_real_applied_object_shape():
    # Guards against the row shape being guessed from prose: these are the
    # bookkeeping table's actual columns.
    assert [f.name for f in dataclasses.fields(AppliedObject)] == [
        "kind",
        "schema_name",
        "object_name",
        "table_name",
        "applied_at",
        "text_sha1",
    ]


# --- read-only / no connection --------------------------------------------

def test_the_driver_only_ever_issues_read_only_selects():
    query = _Query(_resolved(), [_row()])
    run_plpgsql_check(_Session(), _request(), _caps(), query=query)
    for sql in query.sql:
        assert sql.lstrip().upper().startswith("SELECT")
        for forbidden in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"):
            assert forbidden not in sql.upper()


def test_no_test_in_this_module_spawns_a_connection():
    # The driver never imports psycopg (it has no connection code at all), and
    # every test above injected `query=`, so the session's real executor -- the
    # only thing that could connect -- was never reached (it asserts if it is).
    with open(ddl_check.__file__, encoding="utf-8") as handle:
        text = handle.read()
    assert "import psycopg" not in text
    assert "connect(" not in text


def test_dataclasses_are_frozen():
    for cls in (CheckFinding, CheckReport, CheckRequest, ddl_check.TierOutcome):
        assert cls.__dataclass_params__.frozen
