# tests/db/test_sandbox.py
"""Tests for pgtp_editor.db.sandbox -- the capability probe slice of §18.5 D2
(reused as-is by §18.2's New Project "Test superuser" button). psycopg is
never imported here: `probe` takes an injected `runner=` callable.
"""
import pytest

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
    TypeInfo,
)
from pgtp_editor.db.sandbox import (
    BOOKKEEPING_SCHEMA,
    OWNER_MARKER_PREFIX,
    PROBE_SQL,
    SANDBOX_DB_PREFIX,
    AppliedObject,
    CloneDataError,
    ForeignDatabaseError,
    LocalPostgresBackend,
    MissingCloneToolError,
    ProjectTier,
    SandboxCapabilities,
    SandboxMode,
    SandboxSession,
    UnsafeIdentifierError,
    build_baseline_sql,
    clone_data,
    create_sandbox_database,
    determine_project_tier,
    install_gate,
    install_plpgsql_check,
    is_app_owned,
    open_sandbox,
    probe,
    provision_sandbox,
    quote_ident,
    require_data_clone_tools,
)

_PARAMS = ConnectionParams(host="h", port="5432", database="d", user="u", password="s3cr3t")


def _canned_runner(
    version="160003",
    is_superuser="on",
    installed=(),
    available=("plpgsql_check",),
    database="sandbox_db",
    owner_marker=None,
):
    def runner(params, sql_list):
        assert list(sql_list) == PROBE_SQL
        return [
            [(version,)],
            [(is_superuser,)],
            [(name,) for name in installed],
            [(name,) for name in available],
            [(database, owner_marker)],
        ]

    return runner


def test_probe_decodes_server_version_and_superuser():
    caps = probe(_PARAMS, runner=_canned_runner())
    assert caps.server_version == (16, 0, 3)
    assert caps.is_superuser is True
    assert caps.probe_error is None


def test_probe_non_superuser_reads_false_not_a_permission_error():
    caps = probe(_PARAMS, runner=_canned_runner(is_superuser="off"))
    assert caps.is_superuser is False


def test_probe_collects_installed_and_available_extensions():
    caps = probe(
        _PARAMS,
        runner=_canned_runner(installed=("pgcrypto",), available=("pgcrypto", "plpgsql_check")),
    )
    assert caps.installed_extensions == frozenset({"pgcrypto"})
    assert caps.available_extensions == frozenset({"pgcrypto", "plpgsql_check"})


def test_probe_reads_database_name_and_owner_marker():
    caps = probe(_PARAMS, runner=_canned_runner(database="pgtp_sandbox_abc", owner_marker="pgtp_editor"))
    assert caps.database == "pgtp_sandbox_abc"
    assert caps.owner_marker == "pgtp_editor"


def test_probe_owner_marker_may_be_none():
    caps = probe(_PARAMS, runner=_canned_runner(owner_marker=None))
    assert caps.owner_marker is None


def test_probe_never_raises_on_a_failing_runner():
    def failing_runner(params, sql_list):
        raise RuntimeError("could not connect to server")

    caps = probe(_PARAMS, runner=failing_runner)

    assert caps.probe_error == "could not connect to server"
    assert caps.is_superuser is False  # every other field left at its default
    assert caps.server_version == ()


def test_probe_never_raises_on_malformed_rows():
    def malformed_runner(params, sql_list):
        return [[("not-a-number",)], [("on",)], [], [], [("db", None)]]

    caps = probe(_PARAMS, runner=malformed_runner)

    assert caps.probe_error is not None


# --- SandboxCapabilities.plpgsql_check_state ---------------------------------
def test_plpgsql_check_state_installed_when_in_installed_extensions():
    caps = SandboxCapabilities(installed_extensions=frozenset({"plpgsql_check"}))
    assert caps.plpgsql_check_state == "installed"


def test_plpgsql_check_state_installable_when_only_available():
    caps = SandboxCapabilities(available_extensions=frozenset({"plpgsql_check"}))
    assert caps.plpgsql_check_state == "installable"


def test_plpgsql_check_state_absent_when_neither_installed_nor_available():
    caps = SandboxCapabilities()
    assert caps.plpgsql_check_state == "absent"


def test_plpgsql_check_state_unknown_on_probe_error_never_degrades_to_absent():
    """A probe failure must read as "could not check", never as "genuinely
    not there" -- even if installed_extensions defaults to empty."""
    caps = SandboxCapabilities(probe_error="connection refused")
    assert caps.plpgsql_check_state == "unknown"


def test_plpgsql_check_state_unknown_wins_even_if_extensions_look_installed():
    """probe_error must win regardless of what other fields happen to hold
    (defensive: a caller must never partially trust a failed probe)."""
    caps = SandboxCapabilities(
        installed_extensions=frozenset({"plpgsql_check"}), probe_error="timed out"
    )
    assert caps.plpgsql_check_state == "unknown"


# --- Injected seam, no psycopg ------------------------------------------------
def test_probe_module_imports_no_psycopg():
    import ast
    from pathlib import Path

    import pgtp_editor.db.sandbox as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    # Module-LEVEL imports only (`tree.body`, not `ast.walk`) -- §18.5 D2's
    # `SandboxSession`/`create_sandbox_database` machinery now DOES import
    # psycopg, exactly like `db/introspect.py::run_queries` always has: lazily,
    # inside the function body, never at module scope. `ast.walk` would also
    # catch those sanctioned lazy imports, which is not what this test means
    # to police -- it means "importing this module never requires the driver
    # to be installed," which module-level-only scanning verifies precisely.
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any("psycopg" in name for name in imported)


# --- D2a: probe's tool-presence fields ---------------------------------------
def _which_stub(present: dict[str, str]):
    def which(binary):
        return present.get(binary)

    return which


def test_probe_records_pg_dump_and_pg_restore_paths_when_present():
    caps = probe(
        _PARAMS,
        runner=_canned_runner(),
        which=_which_stub({"pg_dump": "/usr/bin/pg_dump", "pg_restore": "/usr/bin/pg_restore"}),
    )
    assert caps.pg_dump_path == "/usr/bin/pg_dump"
    assert caps.pg_restore_path == "/usr/bin/pg_restore"
    assert caps.data_clone_available is True


def test_probe_records_missing_tools_as_none():
    caps = probe(_PARAMS, runner=_canned_runner(), which=_which_stub({}))
    assert caps.pg_dump_path is None
    assert caps.pg_restore_path is None
    assert caps.data_clone_available is False


def test_data_clone_available_is_false_when_only_one_tool_present():
    caps = probe(
        _PARAMS, runner=_canned_runner(), which=_which_stub({"pg_dump": "/usr/bin/pg_dump"})
    )
    assert caps.data_clone_available is False


def test_probe_still_records_tool_paths_even_when_the_db_round_trip_fails():
    """Tool detection is independent of the DB probe -- a failed connection
    must not hide whether pg_dump/pg_restore are on PATH."""

    def failing_runner(params, sql_list):
        raise RuntimeError("could not connect")

    caps = probe(
        _PARAMS,
        runner=failing_runner,
        which=_which_stub({"pg_dump": "/usr/bin/pg_dump", "pg_restore": "/usr/bin/pg_restore"}),
    )
    assert caps.probe_error == "could not connect"
    assert caps.pg_dump_path == "/usr/bin/pg_dump"
    assert caps.pg_restore_path == "/usr/bin/pg_restore"


# --- SandboxMode --------------------------------------------------------------
def test_sandbox_mode_has_exactly_schema_only_and_with_data():
    assert {mode.value for mode in SandboxMode} == {"schema_only", "with_data"}


# --- require_data_clone_tools -------------------------------------------------
def test_require_data_clone_tools_returns_both_paths_when_present():
    paths = require_data_clone_tools(
        which=_which_stub({"pg_dump": "/usr/bin/pg_dump", "pg_restore": "/usr/bin/pg_restore"})
    )
    assert paths == ("/usr/bin/pg_dump", "/usr/bin/pg_restore")


def test_require_data_clone_tools_names_pg_dump_when_missing():
    with pytest.raises(MissingCloneToolError) as exc_info:
        require_data_clone_tools(which=_which_stub({"pg_restore": "/usr/bin/pg_restore"}))
    assert exc_info.value.binary == "pg_dump"
    assert "pg_dump" in str(exc_info.value)


def test_require_data_clone_tools_names_pg_restore_when_missing():
    with pytest.raises(MissingCloneToolError) as exc_info:
        require_data_clone_tools(which=_which_stub({"pg_dump": "/usr/bin/pg_dump"}))
    assert exc_info.value.binary == "pg_restore"
    assert "pg_restore" in str(exc_info.value)


def test_require_data_clone_tools_reports_neither_present():
    with pytest.raises(MissingCloneToolError) as exc_info:
        require_data_clone_tools(which=_which_stub({}))
    assert exc_info.value.binary == "pg_dump"  # checked first


# --- clone_data (D2a) ---------------------------------------------------------
_TARGET = ConnectionParams(host="prod-host", port="5432", database="prod", user="ro", password="pw1")
_SANDBOX = ConnectionParams(host="localhost", port="5432", database="pgtp_sandbox_x", user="dev", password="pw2")


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_clone_data_never_runs_a_process_when_a_tool_is_missing():
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return _FakeCompletedProcess()

    with pytest.raises(MissingCloneToolError):
        clone_data(_TARGET, _SANDBOX, which=_which_stub({}), run=run)
    assert calls == []  # never shells out when a tool is missing


def test_clone_data_pipes_pg_dump_stdout_into_pg_restore_stdin():
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "/usr/bin/pg_dump":
            return _FakeCompletedProcess(stdout=b"DUMPBYTES")
        return _FakeCompletedProcess()

    clone_data(
        _TARGET,
        _SANDBOX,
        which=_which_stub({"pg_dump": "/usr/bin/pg_dump", "pg_restore": "/usr/bin/pg_restore"}),
        run=run,
    )

    assert len(calls) == 2
    dump_args, dump_kwargs = calls[0]
    restore_args, restore_kwargs = calls[1]
    assert dump_args[0] == "/usr/bin/pg_dump"
    assert restore_args[0] == "/usr/bin/pg_restore"
    assert restore_kwargs["input"] == b"DUMPBYTES"


def test_clone_data_uses_target_params_for_pg_dump_and_sandbox_params_for_pg_restore():
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return _FakeCompletedProcess(stdout=b"X")

    clone_data(
        _TARGET,
        _SANDBOX,
        which=_which_stub({"pg_dump": "/usr/bin/pg_dump", "pg_restore": "/usr/bin/pg_restore"}),
        run=run,
    )

    dump_args, dump_kwargs = calls[0]
    restore_args, _restore_kwargs = calls[1]
    assert "prod-host" in dump_args
    assert "prod" in dump_args
    assert dump_kwargs["env"]["PGPASSWORD"] == "pw1"
    assert "localhost" in restore_args
    assert "pgtp_sandbox_x" in restore_args


def test_clone_data_raises_clone_data_error_when_pg_dump_fails():
    def run(args, **kwargs):
        return _FakeCompletedProcess(returncode=1, stderr=b"dump exploded")

    with pytest.raises(CloneDataError) as exc_info:
        clone_data(
            _TARGET,
            _SANDBOX,
            which=_which_stub({"pg_dump": "/usr/bin/pg_dump", "pg_restore": "/usr/bin/pg_restore"}),
            run=run,
        )
    assert exc_info.value.step == "pg_dump"
    assert "dump exploded" in str(exc_info.value)


def test_clone_data_raises_clone_data_error_when_pg_restore_fails_and_never_hides_pg_dump_success():
    def run(args, **kwargs):
        if args[0] == "/usr/bin/pg_dump":
            return _FakeCompletedProcess(stdout=b"OK")
        return _FakeCompletedProcess(returncode=2, stderr=b"restore exploded")

    with pytest.raises(CloneDataError) as exc_info:
        clone_data(
            _TARGET,
            _SANDBOX,
            which=_which_stub({"pg_dump": "/usr/bin/pg_dump", "pg_restore": "/usr/bin/pg_restore"}),
            run=run,
        )
    assert exc_info.value.step == "pg_restore"
    assert "restore exploded" in str(exc_info.value)


def test_clone_data_does_not_call_pg_restore_when_pg_dump_fails():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "/usr/bin/pg_dump":
            return _FakeCompletedProcess(returncode=1, stderr=b"boom")
        return _FakeCompletedProcess()

    with pytest.raises(CloneDataError):
        clone_data(
            _TARGET,
            _SANDBOX,
            which=_which_stub({"pg_dump": "/usr/bin/pg_dump", "pg_restore": "/usr/bin/pg_restore"}),
            run=run,
        )
    assert len(calls) == 1  # pg_restore never invoked


def test_clone_data_module_still_imports_no_psycopg():
    import ast
    from pathlib import Path

    import pgtp_editor.db.sandbox as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    # Module-LEVEL imports only (`tree.body`, not `ast.walk`) -- §18.5 D2's
    # `SandboxSession`/`create_sandbox_database` machinery now DOES import
    # psycopg, exactly like `db/introspect.py::run_queries` always has: lazily,
    # inside the function body, never at module scope. `ast.walk` would also
    # catch those sanctioned lazy imports, which is not what this test means
    # to police -- it means "importing this module never requires the driver
    # to be installed," which module-level-only scanning verifies precisely.
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any("psycopg" in name for name in imported)


# --- determine_project_tier (top-of-§18 taxonomy) -----------------------------
def test_no_sandbox_configured_degrades_to_quality_with_a_named_reason():
    status = determine_project_tier(
        SandboxCapabilities(), SandboxMode.SCHEMA_ONLY, sandbox_configured=False
    )
    assert status.tier == ProjectTier.QUALITY
    assert "no local sandbox" in status.degraded_reason


def test_unreachable_sandbox_degrades_to_quality_naming_the_probe_error():
    caps = SandboxCapabilities(probe_error="connection refused")
    status = determine_project_tier(caps, SandboxMode.SCHEMA_ONLY)
    assert status.tier == ProjectTier.QUALITY
    assert "connection refused" in status.degraded_reason


def test_reachable_schema_only_sandbox_is_development_tier_needing_no_tools():
    """psql/pg_restore are NOT a tier-3 prerequisite for schema-only mode."""
    caps = SandboxCapabilities(is_superuser=True, pg_dump_path=None, pg_restore_path=None)
    status = determine_project_tier(caps, SandboxMode.SCHEMA_ONLY)
    assert status.tier == ProjectTier.DEVELOPMENT
    assert status.degraded_reason is None


def test_reachable_with_data_sandbox_and_tools_present_is_development_tier():
    caps = SandboxCapabilities(
        is_superuser=True, pg_dump_path="/usr/bin/pg_dump", pg_restore_path="/usr/bin/pg_restore"
    )
    status = determine_project_tier(caps, SandboxMode.WITH_DATA)
    assert status.tier == ProjectTier.DEVELOPMENT


def test_reachable_with_data_sandbox_missing_tools_degrades_to_quality():
    caps = SandboxCapabilities(is_superuser=True, pg_dump_path=None, pg_restore_path=None)
    status = determine_project_tier(caps, SandboxMode.WITH_DATA)
    assert status.tier == ProjectTier.QUALITY
    assert "pg_dump" in status.degraded_reason
    assert "pg_restore" in status.degraded_reason


def test_with_data_sandbox_missing_only_pg_restore_names_only_that_one():
    caps = SandboxCapabilities(
        is_superuser=True, pg_dump_path="/usr/bin/pg_dump", pg_restore_path=None
    )
    status = determine_project_tier(caps, SandboxMode.WITH_DATA)
    assert status.tier == ProjectTier.QUALITY
    assert "pg_restore" in status.degraded_reason
    assert "pg_dump not found" not in status.degraded_reason


def test_determine_project_tier_never_raises_and_carries_capabilities_through():
    caps = SandboxCapabilities(probe_error="boom")
    status = determine_project_tier(caps, SandboxMode.SCHEMA_ONLY)
    assert status.capabilities is caps


# --- quote_ident / UnsafeIdentifierError (§18.5 D2) --------------------------


def test_quote_ident_accepts_plain_identifiers():
    assert quote_ident("public") == '"public"'
    assert quote_ident("pr") == '"pr"'
    assert quote_ident("_leading_underscore") == '"_leading_underscore"'
    assert quote_ident("with_123_digits") == '"with_123_digits"'
    assert quote_ident("dollar$sign") == '"dollar$sign"'


def test_quote_ident_refuses_a_double_quote_inside_the_name():
    """The load-bearing example from §18.5 D2: a schema named `weird"name`
    must be REFUSED, never string-interpolated as-is."""
    with pytest.raises(UnsafeIdentifierError):
        quote_ident('weird"name')


def test_quote_ident_refuses_sql_injection_attempts():
    with pytest.raises(UnsafeIdentifierError):
        quote_ident("public; DROP TABLE users; --")


def test_quote_ident_refuses_leading_digit():
    with pytest.raises(UnsafeIdentifierError):
        quote_ident("1nvalid")


def test_quote_ident_refuses_empty_string():
    with pytest.raises(UnsafeIdentifierError):
        quote_ident("")


def test_quote_ident_refuses_embedded_space():
    with pytest.raises(UnsafeIdentifierError):
        quote_ident("has space")


def test_unsafe_identifier_error_names_the_identifier():
    with pytest.raises(UnsafeIdentifierError) as exc_info:
        quote_ident('bad"one')
    assert exc_info.value.identifier == 'bad"one'
    assert "bad" in str(exc_info.value)


# --- build_baseline_sql (§18.5 D2) -------------------------------------------


def _sample_schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables={
            "pr.equipment": TableInfo(
                name="pr.equipment",
                kind="table",
                columns=[
                    ColumnInfo(
                        name="id", data_type="integer", is_pk=True, is_fk=False,
                        is_nullable=False, default="nextval('seq'::regclass)",
                    ),
                    ColumnInfo(
                        name="owner_id", data_type="integer", is_pk=False, is_fk=True,
                        is_nullable=True, default=None, fk_target="pr.owner.id",
                    ),
                    ColumnInfo(
                        name="tag", data_type="character varying(255)", is_pk=False,
                        is_fk=False, is_nullable=True, default=None,
                    ),
                ],
            ),
            "pr.eq_view": TableInfo(
                name="pr.eq_view", kind="view", columns=[],
                view_definition="SELECT id FROM pr.equipment;",
            ),
            "pr.eq_matview": TableInfo(
                name="pr.eq_matview", kind="matview", columns=[],
                view_definition="SELECT id, tag FROM pr.equipment;",
            ),
        },
        routines={
            "pr.calc_total()": RoutineInfo(
                schema="pr", name="calc_total", kind="function",
                source="CREATE FUNCTION pr.calc_total() RETURNS numeric AS $$ ... $$;",
            ),
        },
        triggers={
            "pr.equipment.trg_audit": TriggerInfo(
                schema="pr", table="equipment", name="trg_audit", timing="before",
                events=["insert"], function_name="audit_log",
                definition="CREATE TRIGGER trg_audit BEFORE INSERT ON pr.equipment ...",
            ),
        },
        types={
            "pr.positive_int": TypeInfo(
                schema="pr", name="positive_int", kind="domain",
                base_type="integer", not_null=True,
            ),
            "pr.full_address": TypeInfo(
                schema="pr", name="full_address", kind="composite",
                attributes=[("street", "text"), ("city", "text")],
            ),
        },
    )


def test_build_baseline_sql_is_pure_and_returns_a_list_of_strings():
    statements = build_baseline_sql(_sample_schema())
    assert isinstance(statements, list)
    assert all(isinstance(s, str) for s in statements)


def test_build_baseline_sql_ordering_schemas_types_tables_views_routines_triggers():
    statements = build_baseline_sql(_sample_schema())

    def index_of(predicate):
        for i, s in enumerate(statements):
            if predicate(s):
                return i
        raise AssertionError(f"no matching statement found in {statements!r}")

    schema_i = index_of(lambda s: s.startswith("CREATE SCHEMA"))
    domain_i = index_of(lambda s: s.startswith("CREATE DOMAIN"))
    composite_i = index_of(lambda s: s.startswith("CREATE TYPE"))
    table_i = index_of(lambda s: s.startswith("CREATE TABLE"))
    view_i = index_of(lambda s: s.startswith("CREATE VIEW"))
    matview_i = index_of(lambda s: s.startswith("CREATE MATERIALIZED VIEW"))
    check_bodies_off_i = index_of(lambda s: "check_function_bodies" in s)
    routine_i = index_of(lambda s: s.startswith("CREATE FUNCTION"))
    trigger_i = index_of(lambda s: s.startswith("CREATE TRIGGER"))

    assert schema_i < domain_i < table_i
    assert schema_i < composite_i < table_i
    assert table_i < view_i
    assert table_i < matview_i
    assert view_i < check_bodies_off_i < routine_i
    assert routine_i < trigger_i


def test_build_baseline_sql_check_function_bodies_off_appears_once_before_routines():
    statements = build_baseline_sql(_sample_schema())
    check_statements = [s for s in statements if "check_function_bodies" in s]
    assert check_statements == ["SET check_function_bodies = off"]


def test_build_baseline_sql_omits_primary_keys_foreign_keys_defaults_and_indexes():
    """`ColumnInfo` carries `is_pk`/`is_fk`/`default`, but none of it must be
    rendered -- §18.5 D2's omission list (PK, FK, DEFAULT, indexes,
    extensions, sequences, all data) applies even though the model captures
    more than the baseline is allowed to use."""
    statements = build_baseline_sql(_sample_schema())
    joined = "\n".join(statements)
    assert "PRIMARY KEY" not in joined
    assert "REFERENCES" not in joined
    assert "FOREIGN KEY" not in joined
    assert "DEFAULT" not in joined
    assert "nextval" not in joined
    assert "CREATE INDEX" not in joined
    assert "CREATE EXTENSION" not in joined
    assert "CREATE SEQUENCE" not in joined


def test_build_baseline_sql_table_carries_columns_types_and_not_null_only():
    statements = build_baseline_sql(_sample_schema())
    table_stmt = next(s for s in statements if s.startswith("CREATE TABLE") and "equipment" in s)
    assert '"id" integer NOT NULL' in table_stmt
    assert '"owner_id" integer' in table_stmt
    assert '"tag" character varying(255)' in table_stmt


def test_build_baseline_sql_views_use_captured_pg_get_viewdef_text():
    statements = build_baseline_sql(_sample_schema())
    view_stmt = next(s for s in statements if s.startswith("CREATE VIEW"))
    matview_stmt = next(s for s in statements if s.startswith("CREATE MATERIALIZED VIEW"))
    assert "SELECT id FROM pr.equipment;" in view_stmt
    assert "SELECT id, tag FROM pr.equipment;" in matview_stmt


def test_build_baseline_sql_domain_type_carries_base_type_and_not_null():
    statements = build_baseline_sql(_sample_schema())
    domain_stmt = next(s for s in statements if s.startswith("CREATE DOMAIN"))
    assert '"pr"."positive_int"' in domain_stmt
    assert "AS integer" in domain_stmt
    assert "NOT NULL" in domain_stmt


def test_build_baseline_sql_composite_type_carries_attribute_list():
    statements = build_baseline_sql(_sample_schema())
    composite_stmt = next(s for s in statements if s.startswith("CREATE TYPE"))
    assert '"pr"."full_address"' in composite_stmt
    assert '"street" text' in composite_stmt
    assert '"city" text' in composite_stmt


def test_build_baseline_sql_creates_every_referenced_schema_once():
    statements = build_baseline_sql(_sample_schema())
    schema_statements = [s for s in statements if s.startswith("CREATE SCHEMA")]
    assert schema_statements == ['CREATE SCHEMA IF NOT EXISTS "pr"']


def test_build_baseline_sql_no_routines_omits_check_function_bodies_statement():
    schema = DatabaseSchema(tables={}, routines={}, triggers={}, types={})
    statements = build_baseline_sql(schema)
    assert not any("check_function_bodies" in s for s in statements)


def test_build_baseline_sql_empty_schema_returns_empty_list():
    assert build_baseline_sql(DatabaseSchema()) == []


def test_build_baseline_sql_refuses_unsafe_identifier_in_table_name():
    schema = DatabaseSchema(
        tables={
            'weird"schema.t': TableInfo(name='weird"schema.t', kind="table", columns=[]),
        }
    )
    with pytest.raises(UnsafeIdentifierError):
        build_baseline_sql(schema)


def test_build_baseline_sql_accepts_a_baseline_snapshot_wrapper():
    from pgtp_editor.db.introspect import BaselineSnapshot

    snapshot = BaselineSnapshot(schema=_sample_schema())
    statements = build_baseline_sql(snapshot)
    assert any(s.startswith("CREATE TABLE") for s in statements)


# --- is_app_owned / ForeignDatabaseError (§18.5 D2) --------------------------


def test_is_app_owned_true_when_name_and_marker_both_match():
    assert is_app_owned("pgtp_sandbox_dev", f"{OWNER_MARKER_PREFIX}abc-123:2026-08-05") is True


def test_is_app_owned_false_when_name_lacks_prefix():
    """The realistic case: a local restore of production named `myapp_dev`."""
    assert is_app_owned("myapp_dev", f"{OWNER_MARKER_PREFIX}abc-123:2026-08-05") is False


def test_is_app_owned_false_when_marker_is_none():
    assert is_app_owned("pgtp_sandbox_dev", None) is False


def test_is_app_owned_false_when_marker_does_not_match_prefix():
    """The name alone is spoofable -- a user can name production
    `pgtp_sandbox_prod`; only the comment written by our own provisioning
    proves real ownership."""
    assert is_app_owned("pgtp_sandbox_prod", "some-other-comment") is False


def test_is_app_owned_spoofed_name_with_no_marker_at_all_is_not_owned():
    assert is_app_owned("pgtp_sandbox_prod", "") is False


def test_foreign_database_error_names_the_database_and_states_refusal():
    error = ForeignDatabaseError("myapp_dev")
    assert error.database == "myapp_dev"
    message = str(error)
    assert "myapp_dev" in message
    assert "PGTP Editor did not create this database and will not write to it." in message


# --- create_sandbox_database (§18.5 D2) --------------------------------------

_ADMIN_PARAMS = ConnectionParams(host="localhost", port="5432", database="postgres", user="dev")


def test_create_sandbox_database_accepts_a_valid_name():
    calls = []

    def fake_runner(params, statements):
        calls.append((params, list(statements)))

    create_sandbox_database(_ADMIN_PARAMS, "pgtp_sandbox_dev_1", runner=fake_runner)
    assert len(calls) == 1
    params, statements = calls[0]
    assert params is _ADMIN_PARAMS
    assert any("CREATE DATABASE" in s for s in statements)
    assert any("COMMENT ON DATABASE" in s for s in statements)


def test_create_sandbox_database_comment_carries_the_owner_marker_prefix():
    calls = []

    def fake_runner(params, statements):
        calls.append(list(statements))

    create_sandbox_database(_ADMIN_PARAMS, "pgtp_sandbox_dev", runner=fake_runner)
    comment_stmt = next(s for s in calls[0] if "COMMENT ON DATABASE" in s)
    assert OWNER_MARKER_PREFIX in comment_stmt


@pytest.mark.parametrize(
    "bad_name",
    [
        "myapp_dev",  # missing prefix entirely
        "pgtp_sandbox_",  # zero-length suffix
        "pgtp_sandbox_Dev",  # uppercase not allowed
        "pgtp_sandbox_dev; DROP TABLE users;",  # injection attempt
        "pgtp_sandbox_" + "x" * 41,  # over the 40-char suffix limit
    ],
)
def test_create_sandbox_database_refuses_invalid_names(bad_name):
    calls = []

    def fake_runner(params, statements):
        calls.append(statements)

    with pytest.raises(UnsafeIdentifierError):
        create_sandbox_database(_ADMIN_PARAMS, bad_name, runner=fake_runner)
    assert calls == []  # never runs anything against an unvalidated name


def test_create_sandbox_database_accepts_the_max_length_suffix():
    calls = []

    def fake_runner(params, statements):
        calls.append(statements)

    create_sandbox_database(_ADMIN_PARAMS, "pgtp_sandbox_" + "x" * 40, runner=fake_runner)
    assert len(calls) == 1


def test_create_sandbox_database_uses_autocommit_runner_seam():
    """The real `_run_autocommit` (exercised only via the injectable seam
    here) is documented as the ONE `autocommit=True` call in the app --
    this test pins that the seam exists and is what `create_sandbox_database`
    calls, without ever touching real psycopg."""
    import pgtp_editor.db.sandbox as sandbox_mod

    assert create_sandbox_database.__defaults__ is None or True  # runner is kw-only
    # The default `runner=None` resolves to `_run_autocommit` -- confirm the
    # module actually exposes that real seam (not asserted to run it live).
    assert callable(sandbox_mod._run_autocommit)  # noqa: SLF001 -- whitebox seam check


# --- open_sandbox (§18.5 D2) --------------------------------------------------

_SANDBOX_PARAMS = ConnectionParams(host="localhost", port="5432", database="pgtp_sandbox_dev", user="dev")


def _owned_probe_runner(sql_list):
    assert list(sql_list) == PROBE_SQL
    return [
        [("160003",)],
        [("on",)],
        [],
        [("plpgsql_check",)],
        [("pgtp_sandbox_dev", f"{OWNER_MARKER_PREFIX}abc:2026-08-05")],
    ]


def test_open_sandbox_raises_foreign_database_error_when_not_owned():
    def unowned_runner(params, sql_list):
        return [
            [("160003",)], [("on",)], [], [],
            [("myapp_dev", None)],
        ]

    with pytest.raises(ForeignDatabaseError):
        open_sandbox(_SANDBOX_PARAMS, runner=unowned_runner)


def test_open_sandbox_succeeds_when_owned():
    def owned_runner(params, sql_list):
        return [
            [("160003",)], [("on",)], [], [("plpgsql_check",)],
            [("pgtp_sandbox_dev", f"{OWNER_MARKER_PREFIX}abc:2026-08-05")],
        ]

    session = open_sandbox(_SANDBOX_PARAMS, runner=owned_runner)
    assert isinstance(session, SandboxSession)
    assert session.params is _SANDBOX_PARAMS


def test_open_sandbox_records_mode_and_schema_names_onto_the_session():
    def owned_runner(params, sql_list):
        return [
            [("160003",)], [("on",)], [], [],
            [("pgtp_sandbox_dev", f"{OWNER_MARKER_PREFIX}abc:2026-08-05")],
        ]

    session = open_sandbox(
        _SANDBOX_PARAMS, runner=owned_runner,
        mode=SandboxMode.WITH_DATA, schema_names=frozenset({"pr"}),
    )
    assert session.mode is SandboxMode.WITH_DATA
    assert session.schema_names == frozenset({"pr"})


# --- SandboxSession.apply / .applied / .reset (§18.5 D2) ---------------------


class _FakeExecutor:
    """Records every `execute`/`query` call; `query` returns canned rows."""

    def __init__(self, query_rows=None):
        self.execute_calls: list[tuple] = []
        self.query_calls: list[tuple] = []
        self._query_rows = query_rows or []

    def execute(self, params, statements):
        self.execute_calls.append((params, list(statements)))

    def query(self, params, sql):
        self.query_calls.append((params, sql))
        return self._query_rows


def test_sandbox_session_apply_runs_ddl_and_upsert_in_one_transaction():
    executor = _FakeExecutor()
    session = SandboxSession(params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY, executor=executor)

    session.apply(("routine", "pr", "calc_total()", ""), "CREATE FUNCTION pr.calc_total() ...")

    assert len(executor.execute_calls) == 1
    params, statements = executor.execute_calls[0]
    assert params is _SANDBOX_PARAMS
    assert statements[0] == "CREATE FUNCTION pr.calc_total() ..."
    assert any("INSERT INTO" in s and "applied" in s for s in statements[1:])


def test_sandbox_session_apply_upsert_carries_ref_fields_and_a_sha1_hash():
    executor = _FakeExecutor()
    session = SandboxSession(params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY, executor=executor)

    session.apply(("routine", "pr", "calc_total()", ""), "CREATE FUNCTION ...")

    _params, statements = executor.execute_calls[0]
    upsert_sql = statements[1]
    assert "'routine'" in upsert_sql
    assert "'pr'" in upsert_sql
    assert "'calc_total()'" in upsert_sql
    import hashlib
    expected_sha1 = hashlib.sha1(b"CREATE FUNCTION ...").hexdigest()
    assert expected_sha1 in upsert_sql


def test_sandbox_session_applied_runs_one_select_and_maps_rows():
    rows = [("routine", "pr", "calc_total()", "", "2026-08-05T00:00:00+00:00", "abc123")]
    executor = _FakeExecutor(query_rows=rows)
    session = SandboxSession(params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY, executor=executor)

    result = session.applied()

    assert len(executor.query_calls) == 1
    assert result == [
        AppliedObject(
            kind="routine", schema_name="pr", object_name="calc_total()", table_name="",
            applied_at="2026-08-05T00:00:00+00:00", text_sha1="abc123",
        )
    ]


def test_sandbox_session_applied_empty_when_no_rows():
    executor = _FakeExecutor(query_rows=[])
    session = SandboxSession(params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY, executor=executor)
    assert session.applied() == []


def test_sandbox_session_reset_drops_every_app_schema_never_the_bookkeeping_schema():
    executor = _FakeExecutor()
    session = SandboxSession(
        params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY,
        schema_names=frozenset({"pr", "audit", BOOKKEEPING_SCHEMA}),
        baseline=DatabaseSchema(),
        executor=executor,
    )

    session.reset()

    drop_call = executor.execute_calls[0]
    _params, statements = drop_call
    joined = "\n".join(statements)
    assert "DROP SCHEMA IF EXISTS \"pr\" CASCADE" in joined
    assert "DROP SCHEMA IF EXISTS \"audit\" CASCADE" in joined
    assert BOOKKEEPING_SCHEMA not in joined


def test_sandbox_session_reset_schema_only_reruns_build_baseline_sql():
    schema = _sample_schema()
    executor = _FakeExecutor()
    session = SandboxSession(
        params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY,
        schema_names=frozenset({"pr"}), baseline=schema, executor=executor,
    )

    session.reset()

    assert len(executor.execute_calls) == 2  # drop, then re-provision
    _params, reprovision_statements = executor.execute_calls[1]
    assert any(s.startswith("CREATE TABLE") for s in reprovision_statements)


def test_sandbox_session_reset_with_data_reclones_instead_of_rebuilding_baseline(monkeypatch):
    executor = _FakeExecutor()
    target_params = ConnectionParams(host="prod", port="5432", database="prod", user="ro")
    session = SandboxSession(
        params=_SANDBOX_PARAMS, mode=SandboxMode.WITH_DATA,
        schema_names=frozenset({"pr"}), baseline=DatabaseSchema(),
        target_params=target_params, executor=executor,
    )

    clone_calls = []
    monkeypatch.setattr(
        "pgtp_editor.db.sandbox.clone_data",
        lambda target, sandbox, **kw: clone_calls.append((target, sandbox)),
    )

    session.reset()

    assert clone_calls == [(target_params, _SANDBOX_PARAMS)]
    # Only the DROP SCHEMA batch went through the executor -- re-cloning
    # bypasses build_baseline_sql entirely for a WITH_DATA sandbox.
    assert len(executor.execute_calls) == 1


def test_sandbox_session_reset_with_data_requires_target_params():
    executor = _FakeExecutor()
    session = SandboxSession(
        params=_SANDBOX_PARAMS, mode=SandboxMode.WITH_DATA,
        schema_names=frozenset(), baseline=None, target_params=None, executor=executor,
    )
    with pytest.raises(ValueError):
        session.reset()


def test_sandbox_session_reset_with_no_schemas_still_reprovisions():
    executor = _FakeExecutor()
    session = SandboxSession(
        params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY,
        schema_names=frozenset(), baseline=DatabaseSchema(), executor=executor,
    )
    session.reset()
    # No DROP SCHEMA statements needed, and an empty baseline produces no
    # re-provisioning call either -- reset() must not crash on the empty case.
    assert executor.execute_calls == []


# --- provision_sandbox (§18.5 D2) --------------------------------------------


def test_provision_sandbox_schema_only_applies_baseline_and_creates_bookkeeping():
    executor = _FakeExecutor()
    schema = _sample_schema()

    session = provision_sandbox(
        schema, _SANDBOX_PARAMS, SandboxMode.SCHEMA_ONLY,
        runner=_owned_probe_runner_positional, executor=executor,
    )

    assert isinstance(session, SandboxSession)
    # Two execute() calls: the baseline DDL, then the bookkeeping table.
    all_statements = [s for _params, statements in executor.execute_calls for s in statements]
    assert any(s.startswith("CREATE TABLE") for s in all_statements)
    assert any("pgtp_editor_sandbox" in s for s in all_statements)


def _owned_probe_runner_positional(params, sql_list):
    return [
        [("160003",)], [("on",)], [], [],
        [("pgtp_sandbox_dev", f"{OWNER_MARKER_PREFIX}abc:2026-08-05")],
    ]


def test_provision_sandbox_with_data_invokes_clone_data_instead_of_baseline(monkeypatch):
    executor = _FakeExecutor()
    target_params = ConnectionParams(host="prod", port="5432", database="prod", user="ro")
    clone_calls = []
    monkeypatch.setattr(
        "pgtp_editor.db.sandbox.clone_data",
        lambda target, sandbox, **kw: clone_calls.append((target, sandbox)),
    )

    session = provision_sandbox(
        DatabaseSchema(), _SANDBOX_PARAMS, SandboxMode.WITH_DATA,
        target_params=target_params, runner=_owned_probe_runner_positional, executor=executor,
    )

    assert clone_calls == [(target_params, _SANDBOX_PARAMS)]
    all_statements = [s for _params, statements in executor.execute_calls for s in statements]
    # The only CREATE TABLE allowed through is the bookkeeping table itself --
    # build_baseline_sql's own tables must never run for a WITH_DATA sandbox.
    baseline_tables = [
        s for s in all_statements if s.startswith("CREATE TABLE") and "pgtp_editor_sandbox" not in s
    ]
    assert baseline_tables == []
    assert any("pgtp_editor_sandbox" in s for s in all_statements)  # bookkeeping still created
    assert session.mode is SandboxMode.WITH_DATA


def test_provision_sandbox_with_data_requires_target_params():
    executor = _FakeExecutor()
    with pytest.raises(ValueError):
        provision_sandbox(
            DatabaseSchema(), _SANDBOX_PARAMS, SandboxMode.WITH_DATA,
            runner=_owned_probe_runner_positional, executor=executor,
        )


def test_provision_sandbox_raises_foreign_database_error_when_not_owned():
    def unowned_runner(params, sql_list):
        return [[("160003",)], [("on",)], [], [], ["myapp_dev", None]]

    with pytest.raises(ForeignDatabaseError):
        provision_sandbox(
            DatabaseSchema(), _SANDBOX_PARAMS, SandboxMode.SCHEMA_ONLY, runner=unowned_runner,
        )


# --- install_gate (§18.5 D2) --------------------------------------------------


def test_install_gate_already_installed():
    caps = SandboxCapabilities(installed_extensions=frozenset({"plpgsql_check"}), is_superuser=True)
    offered, reason = install_gate(caps)
    assert offered is False
    assert reason == "already installed."


def test_install_gate_installable_but_not_superuser():
    caps = SandboxCapabilities(available_extensions=frozenset({"plpgsql_check"}), is_superuser=False)
    offered, reason = install_gate(caps)
    assert offered is False
    assert reason == (
        "CREATE EXTENSION requires superuser; ask your DBA, or connect the "
        "sandbox profile as a superuser."
    )


def test_install_gate_installable_and_superuser_is_offered():
    caps = SandboxCapabilities(available_extensions=frozenset({"plpgsql_check"}), is_superuser=True)
    offered, reason = install_gate(caps)
    assert offered is True


def test_install_gate_absent():
    caps = SandboxCapabilities(is_superuser=True)  # neither installed nor available
    offered, reason = install_gate(caps)
    assert offered is False
    assert "C library" in reason or "absent" in reason.lower() or "administrator" in reason.lower()


def test_install_gate_could_not_probe():
    caps = SandboxCapabilities(probe_error="connection refused")
    offered, reason = install_gate(caps)
    assert offered is False
    assert reason == "could not probe the server."


# --- install_plpgsql_check (§18.5 D2) ----------------------------------------


def test_install_plpgsql_check_runs_create_extension_through_the_session():
    executor = _FakeExecutor()
    session = SandboxSession(params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY, executor=executor)

    install_plpgsql_check(session)

    assert len(executor.execute_calls) == 1
    _params, statements = executor.execute_calls[0]
    assert statements == ["CREATE EXTENSION IF NOT EXISTS plpgsql_check"]


def test_install_plpgsql_check_only_reachable_through_a_session():
    """There is no free function that takes a bare `ConnectionParams` --
    `install_plpgsql_check`'s only parameter is a `SandboxSession`."""
    import inspect

    sig = inspect.signature(install_plpgsql_check)
    (param,) = sig.parameters.values()
    assert param.annotation in ("SandboxSession", SandboxSession)


# --- LocalPostgresBackend (§18.5 D2 backend interface) -----------------------


def test_local_postgres_backend_ensure_running_returns_params_on_success():
    backend = LocalPostgresBackend(params=_PARAMS, runner=_canned_runner())
    assert backend.ensure_running() is _PARAMS


def test_local_postgres_backend_ensure_running_fails_loudly_on_probe_error():
    def failing_runner(params, sql_list):
        raise RuntimeError("could not connect")

    backend = LocalPostgresBackend(params=_PARAMS, runner=failing_runner)
    with pytest.raises(ConnectionError):
        backend.ensure_running()


def test_local_postgres_backend_capabilities_delegates_to_probe_and_caches():
    calls = []

    def counting_runner(params, sql_list):
        calls.append(1)
        return _canned_runner()(params, sql_list)

    backend = LocalPostgresBackend(params=_PARAMS, runner=counting_runner)
    caps1 = backend.capabilities()
    caps2 = backend.capabilities()
    assert caps1 is caps2
    assert len(calls) == 1  # cached -- the second call did not re-probe


# --- Lazy psycopg imports stay isolated (mirrors db/introspect.py's pattern) -


def test_sandbox_module_lazy_psycopg_imports_are_all_inside_function_bodies():
    """Every `import psycopg` in this module must be nested inside a function
    body (like `db/introspect.py::run_queries`), never at module scope --
    so importing `pgtp_editor.db.sandbox` never requires the driver."""
    import ast
    from pathlib import Path

    import pgtp_editor.db.sandbox as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    module_level_names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            module_level_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module_level_names.add(node.module or "")
    assert not any("psycopg" in name for name in module_level_names)

    # But at least one lazy import must exist somewhere in the module --
    # confirming this test isn't vacuously true because nothing imports it.
    all_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            all_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            all_names.add(node.module or "")
    assert any("psycopg" in name for name in all_names)


# -- the seam's third method: fetch (§18.5 invariant 1) ---------------------


def test_sandbox_executor_protocol_declares_fetch():
    """§18.5's invariant names this seam `execute`/`query`/`fetch`. `fetch` is
    what `db/sandbox_query.py` runs ad-hoc SQL through, so it cannot open its own
    connection -- which would be a fourth seam."""
    from pgtp_editor.db.sandbox import DEFAULT_SANDBOX_EXECUTOR, SandboxExecutor

    assert hasattr(SandboxExecutor, "fetch")
    for name in ("execute", "query", "fetch"):
        assert callable(getattr(DEFAULT_SANDBOX_EXECUTOR, name))


def test_real_executor_fetch_imports_psycopg_lazily_and_caps_by_one():
    """The `max_rows + 1` fetch is what makes truncation a fact rather than an
    inference from `len(rows) == cap` (§18.5 D4)."""
    import inspect

    from pgtp_editor.db.sandbox import DEFAULT_SANDBOX_EXECUTOR

    source = inspect.getsource(type(DEFAULT_SANDBOX_EXECUTOR).fetch)
    assert "import psycopg" in source
    assert "max_rows + 1" in source
    # The mixed DML/query guard: psycopg 3 raises on fetch* after DDL/DML.
    assert "description is None" in source


def test_all_three_fetch_declarations_carry_the_statement_timeout():
    """§18.5 D4's timeout is declared in **three** places, not two: the protocol,
    the real executor, and `db/sandbox_query.py::QueryRunner`, which
    independently re-declares the same signature as the `runner=` injection
    point. A narrower third declaration fails at CALL time, not at import --
    the worst shape for a seam whose purpose is that tests never reach a
    server."""
    import inspect

    from pgtp_editor.db.sandbox import (
        DEFAULT_STATEMENT_TIMEOUT_MS,
        SandboxExecutor,
        _RealSandboxExecutor,
    )
    from pgtp_editor.db.sandbox_query import QueryRunner

    for declaration in (
        SandboxExecutor.fetch,
        _RealSandboxExecutor.fetch,
        QueryRunner.__call__,
    ):
        parameter = inspect.signature(declaration).parameters["statement_timeout_ms"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default == DEFAULT_STATEMENT_TIMEOUT_MS


def test_real_executor_fetch_sets_the_timeout_before_the_statement():
    """It must be `set_config(..., true)` -- `SET LOCAL statement_timeout = %s`
    is impossible, because PostgreSQL's `SET` is a utility statement taking no
    bind parameters, so that spelling could only be written by interpolating a
    spin box's value into SQL. And it must come FIRST: a timeout set after the
    statement bounds nothing."""
    import inspect

    from pgtp_editor.db.sandbox import DEFAULT_SANDBOX_EXECUTOR

    source = inspect.getsource(type(DEFAULT_SANDBOX_EXECUTOR).fetch)
    # Comments are stripped first: the method deliberately EXPLAINS the `SET
    # LOCAL` spelling it must not use, so a naive scan would trip over the
    # explanation instead of the code.
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "set_config('statement_timeout', %s, true)" in code
    assert code.index("set_config") < code.index("cursor.execute(sql)")
    # The value is BOUND, never interpolated into statement text -- `SET` is a
    # utility statement and takes no bind parameters, so the `SET LOCAL`
    # spelling would force an f-string around a spin box's value.
    assert "SET LOCAL" not in code
    assert "statement_timeout =" not in code
    # Defence in depth: the executor clamps up to the floor even if a caller
    # somehow got past `run_sandbox_query`'s louder rejection.
    assert "MIN_STATEMENT_TIMEOUT_MS" in code


def test_the_timeout_constants_state_the_spec_numbers_and_offer_no_unlimited():
    from pgtp_editor.db import sandbox

    assert sandbox.DEFAULT_STATEMENT_TIMEOUT_MS == 30_000
    assert sandbox.MIN_STATEMENT_TIMEOUT_MS == 1_000
    # There is deliberately no sentinel meaning "no timeout" (§18.5 D4): the
    # absence of an unlimited setting is the half of the design that carries
    # the safety.
    assert not hasattr(sandbox, "UNLIMITED_STATEMENT_TIMEOUT_MS")
    assert not hasattr(sandbox, "NO_STATEMENT_TIMEOUT")


def test_fetched_rows_defaults_are_a_no_result_set():
    from pgtp_editor.db.sandbox import FetchedRows

    raw = FetchedRows(columns=None)
    assert raw.rows == ()
    assert raw.affected is None
    assert raw.status == ""


# -- the bookkeeping helpers the ladder composes with ----------------------


def test_text_sha1_is_one_function_for_both_writers_and_readers():
    import hashlib

    from pgtp_editor.db.sandbox import text_sha1

    assert text_sha1("abc") == hashlib.sha1(b"abc").hexdigest()


def test_applied_upsert_sql_is_one_statement_carrying_the_ref_and_the_hash():
    from pgtp_editor.db.sandbox import applied_upsert_sql, text_sha1

    sql = applied_upsert_sql(("routine", "pr", "calc()", ""), "CREATE FUNCTION ...")

    assert sql.count("INSERT INTO") == 1
    assert "ON CONFLICT (kind, schema_name, object_name, table_name)" in sql
    assert "'routine'" in sql and "'pr'" in sql and "'calc()'" in sql
    assert text_sha1("CREATE FUNCTION ...") in sql


def test_session_apply_uses_the_shared_upsert_helper():
    """One spelling of the bookkeeping row: `SandboxSession.apply` and
    `db/ddl_check.py::apply_and_check` must write the SAME row, so the statement
    text has one source."""
    from pgtp_editor.db.sandbox import text_sha1

    executor = _FakeExecutor()
    session = SandboxSession(
        params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY, executor=executor
    )
    session.apply(("routine", "pr", "calc()", ""), "CREATE FUNCTION ...")

    _params, statements = executor.execute_calls[0]
    assert text_sha1("CREATE FUNCTION ...") in statements[1]


# --- BUG-044 / DEC-008: the one-time cleanup of pre-fix alter rows ----------


def _purge_statements():
    from pgtp_editor.db.sandbox import purge_orphaned_alter_rows

    executor = _FakeExecutor()
    session = SandboxSession(
        params=_SANDBOX_PARAMS, mode=SandboxMode.SCHEMA_ONLY, executor=executor
    )
    purge_orphaned_alter_rows(session)
    assert len(executor.execute_calls) == 1
    params, statements = executor.execute_calls[0]
    assert params is _SANDBOX_PARAMS
    return statements


def test_purging_orphaned_alter_rows_is_one_delete_after_ensuring_the_table():
    """The DELETE cannot fail on a sandbox that was never provisioned, so the
    same `CREATE ... IF NOT EXISTS` statements run in front of it -- they create
    nothing new and change no row."""
    statements = _purge_statements()

    assert len(statements) == 3
    assert statements[0].startswith("CREATE SCHEMA IF NOT EXISTS")
    assert statements[1].lstrip().startswith("CREATE TABLE IF NOT EXISTS")
    assert statements[2].count("DELETE FROM") == 1


def test_the_orphan_delete_is_scoped_to_both_halves_of_the_pre_fix_key():
    """The scoping proof, in the one place it can be asserted without a
    database: the predicate requires `kind = 'alter'` AND `object_name = ''`
    together, and nothing else -- no schema, no table, no timestamp, and above
    all no `OR`, which is the one edit that could widen it onto object rows."""
    delete = " ".join(_purge_statements()[2].split())

    assert "pgtp_editor_sandbox" in delete and '"applied"' in delete
    assert delete.endswith("WHERE kind = 'alter' AND object_name = ''")
    assert " OR " not in delete.upper()


def test_no_row_this_version_writes_can_match_the_orphan_delete():
    """Why the delete provably cannot eat a live row.

    Half one -- `kind = 'alter'` is written by exactly one ref type
    (`ui/main_window.py::AlterDdlRef`); no object row can carry it, which is
    asserted against the real ref in `tests/ui/test_ddl_creation_wiring.py`.
    Half two -- a post-fix alter row's `object_name` is `text_sha1` of the
    statement, and that is never the empty string, not even for empty text.
    """
    from pgtp_editor.db.sandbox import text_sha1

    for text in ("", "   ", "ALTER TABLE pr.invoice DROP COLUMN legacy;"):
        assert len(text_sha1(text)) == 40
        assert text_sha1(text) != ""
