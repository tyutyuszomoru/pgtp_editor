"""Live-PostgreSQL confirmation of assumptions the design rests on.

Everything here is **skipped unless** ``PGTP_TEST_SANDBOX_DSN`` is set, so the default
suite stays green on a machine with no server and CI is unaffected::

    PGTP_TEST_SANDBOX_DSN="host=127.0.0.1 port=5432 user=… password=… dbname=postgres" \
        QT_QPA_PLATFORM=offscreen python -m pytest tests/db/test_sandbox_live.py -q

The DSN must point at a database the role may ``CREATE DATABASE`` from; every test runs
against a throwaway database created and dropped by the fixture, so nothing the DSN names
is ever mutated.

Why these specific facts: each one is load-bearing for code that is already written, and
none can be established with a fake. A fake runner asserts what we *believe* psycopg and
PostgreSQL do; these assert what they actually do.

Verified 2026-08-02 against PostgreSQL 18.0.4 with plpgsql_check 2.10 — 14/14 held, except
that fact 7b corrected the tier-1 line-number design (see its docstring).
"""

from __future__ import annotations

import os

import pytest

DSN_ENV = "PGTP_TEST_SANDBOX_DSN"
_DSN = os.environ.get(DSN_ENV)

pytestmark = pytest.mark.skipif(
    not _DSN, reason=f"needs a live PostgreSQL; set {DSN_ENV}"
)

psycopg = pytest.importorskip("psycopg", reason="psycopg not installed")

SCRATCH = "pgtp_live_test_tmp"


def _scratch_dsn() -> str:
    """`_DSN` with its dbname swapped for the throwaway database."""
    parts = [p for p in _DSN.split() if not p.startswith("dbname=")]
    return " ".join(parts + [f"dbname={SCRATCH}"])


@pytest.fixture(scope="module")
def scratch_db():
    """Create a throwaway database for the module, drop it afterwards."""
    admin = psycopg.connect(_DSN, autocommit=True, connect_timeout=10)
    try:
        admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {SCRATCH}")
        yield _scratch_dsn()
    finally:
        try:
            admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        finally:
            admin.close()


@pytest.fixture
def conn(scratch_db):
    with psycopg.connect(scratch_db, autocommit=True, connect_timeout=10) as c:
        yield c


# --------------------------------------------------------------------------------------
# The ordering decision (db/migration_gen.py Task 3)
# --------------------------------------------------------------------------------------

def test_plpgsql_body_may_reference_a_function_that_does_not_exist_yet(conn):
    """THE load-bearing fact behind alphabetical (not topological) ordering.

    plpgsql bodies are not resolved at CREATE time, so a deployment script need not
    order routines by their call graph. If this ever fails, `generate_migration` must
    grow a topological sort or emitted scripts will fail partway through on a real
    deploy.
    """
    conn.execute(
        "CREATE OR REPLACE FUNCTION calls_missing() RETURNS int AS $$ "
        "BEGIN RETURN definitely_not_defined_yet(); END $$ LANGUAGE plpgsql"
    )  # must not raise


def test_language_sql_body_may_not_reference_a_missing_function(conn):
    """The stated exception to the rule above -- SQL bodies ARE analysed at creation.

    This is why `generate_migration` emits a header warning when a non-plpgsql routine
    is included: for those, statement order can matter.
    """
    with pytest.raises(psycopg.errors.UndefinedFunction):
        conn.execute(
            "CREATE OR REPLACE FUNCTION sql_calls_missing() RETURNS int "
            "LANGUAGE sql AS $$ SELECT definitely_not_defined_yet() $$"
        )


# --------------------------------------------------------------------------------------
# The write seam (db/apply.py) -- R1
# --------------------------------------------------------------------------------------

def test_non_row_returning_statements_have_no_description_and_cannot_be_fetched(conn):
    """`run_queries` fetchall()s unconditionally; every statement the ladder runs is
    non-row-returning. Without a `cursor.description is None` guard, tier 2 fails on
    its first statement.
    """
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE desc_probe (id int)")
        assert cur.description is None
        cur.execute("SET plpgsql.extra_warnings = 'all'")
        assert cur.description is None
        cur.execute("CREATE TABLE desc_probe2 (id int)")
        with pytest.raises(psycopg.ProgrammingError):
            cur.fetchall()


def test_create_database_cannot_run_inside_a_transaction_block(scratch_db):
    """Why sandbox provisioning needs `autocommit=True` specifically."""
    with psycopg.connect(_DSN, connect_timeout=10) as c:  # autocommit OFF
        with pytest.raises(psycopg.errors.ActiveSqlTransaction):
            c.execute("CREATE DATABASE pgtp_should_never_exist")


# --------------------------------------------------------------------------------------
# Tier 1 -- notices, not rows (R2)
# --------------------------------------------------------------------------------------

def test_extra_errors_is_settable_in_a_fresh_session(conn):
    """plpgsql need not already be loaded for the SET to be accepted."""
    conn.execute("SET plpgsql.extra_errors = 'all'")


def _capture(conn) -> list[dict]:
    """Register a handler that COPIES each diagnostic's fields immediately.

    psycopg's `Diagnostic` is only valid for the duration of the callback -- stash the
    object and read it later and every attribute comes back `None`. `db/apply.py`'s
    psycopg-free `Notice` normalization must therefore copy inside the handler, which
    is what `test_a_stored_diagnostic_object_goes_blank` pins.
    """
    out: list[dict] = []
    conn.add_notice_handler(
        lambda d: out.append(
            {
                "severity": d.severity,
                "message": d.message_primary,
                "detail": d.message_detail,
                "hint": d.message_hint,
                "context": d.context,
                "sqlstate": d.sqlstate,
                "position": d.statement_position,
            }
        )
    )
    return out


def test_extra_warnings_are_delivered_as_notices_not_rows(conn):
    """Tier 1 produces NOTHING without a notice handler -- it returns no rows at all."""
    notices = _capture(conn)
    conn.execute("SET plpgsql.extra_warnings = 'all'")
    with conn.cursor() as cur:
        cur.execute(
            "CREATE OR REPLACE FUNCTION f_shadow(id int) RETURNS int AS $$\n"
            "DECLARE id int;\n"
            "BEGIN id := 1; RETURN id; END $$ LANGUAGE plpgsql"
        )
        assert cur.description is None  # no result set to read findings from

    assert any(
        "shadows" in (n["message"] or "") for n in notices
    ), [n["message"] for n in notices]


def test_a_stored_diagnostic_object_goes_blank(conn):
    """psycopg's Diagnostic is only valid INSIDE the handler.

    Appending the object itself and reading it afterwards yields `None` for every
    field -- silently, with no error. A notice pipeline that stores diagnostics rather
    than copying their fields would report findings with no message, no severity and no
    position, which reads as "checked, nothing found".
    """
    raw = []
    conn.add_notice_handler(raw.append)
    conn.execute("SET plpgsql.extra_warnings = 'all'")
    conn.execute(
        "CREATE OR REPLACE FUNCTION f_blank(id int) RETURNS int AS $$\n"
        "DECLARE id int;\n"
        "BEGIN id := 1; RETURN id; END $$ LANGUAGE plpgsql"
    )
    assert raw, "expected at least one notice"
    assert all(d.message_primary is None for d in raw), [d.message_primary for d in raw]


def test_compile_time_notices_carry_position_not_context(conn):
    """CORRECTS THE DESIGN. Tier 1's line numbers cannot come from `context`.

    The plan and spec both assumed tier-1 findings would be located by regexing
    `Notice.context` for ``near line N``. Measured behaviour on PG 18:

    * **compile-time** warnings (what tier 1 actually sees, since it does
      ``SET extra_warnings`` then ``CREATE FUNCTION``) have ``context = None`` and
      carry ``statement_position`` -- a 1-based character offset into the statement
      we submitted, which *is* the editor buffer.
    * **runtime** warnings (only raised when the function is executed, which tier 1
      never does) are the ones with
      ``context = 'PL/pgSQL function f() line 3 at SQL statement'``.

    So tier 1 should map `statement_position` -> line the same way tier 2 maps a
    failure position (``buffer.count("\\n", 0, pos) + 1``), needing **no**
    prosrc->pg_get_functiondef offset at all. Regexing `context` would silently yield
    no line for every finding tier 1 can actually produce.
    """
    notices = _capture(conn)
    conn.execute("SET plpgsql.extra_warnings = 'all'")
    conn.execute(
        "CREATE OR REPLACE FUNCTION f_shadow2(id int) RETURNS int AS $$\n"
        "DECLARE id int;\n"
        "BEGIN id := 1; RETURN id; END $$ LANGUAGE plpgsql"
    )

    shadow = [n for n in notices if "shadows" in (n["message"] or "")]
    assert shadow, [n["message"] for n in notices]
    note = shadow[0]
    assert note["context"] is None, f"context unexpectedly populated: {note['context']!r}"
    assert note["position"] is not None
    assert int(note["position"]) > 0


# --------------------------------------------------------------------------------------
# Recovering the OID of a just-applied routine -- R6
# --------------------------------------------------------------------------------------

def test_xmin_recovers_the_routine_created_in_this_transaction(scratch_db):
    """The fallback for when the user edited the signature, so the rendered name is stale.

    Flagged as "too clever to trust unverified" -- this is the verification.
    """
    with psycopg.connect(scratch_db, connect_timeout=10) as c, c.cursor() as cur:
        cur.execute(
            "CREATE OR REPLACE FUNCTION oid_probe(a int, b text) RETURNS int AS $$ "
            "BEGIN RETURN 1; END $$ LANGUAGE plpgsql"
        )
        cur.execute(
            "SELECT oid::regprocedure::text FROM pg_proc "
            "WHERE xmin = pg_current_xact_id()::text::xid"
        )
        found = [r[0] for r in cur.fetchall()]
        assert any("oid_probe" in f for f in found), found
        c.commit()


def test_to_regprocedure_returns_null_exactly_when_the_signature_changed(conn):
    """Why the xmin fallback is NECESSARY rather than merely a nicety.

    The primary OID path renders a signature from the edited buffer. When the user
    changed the argument types -- precisely the R14 case the apply-time refusal must
    catch -- that signature resolves to NULL, so the primary path fails in exactly the
    situation where getting it right matters most.
    """
    conn.execute(
        "CREATE OR REPLACE FUNCTION sig_probe(a int, b text) RETURNS int AS $$ "
        "BEGIN RETURN 1; END $$ LANGUAGE plpgsql"
    )
    with conn.cursor() as cur:
        cur.execute("SELECT to_regprocedure('public.sig_probe(integer, text)')::oid")
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT to_regprocedure('public.sig_probe(bigint, text)')::oid")
        assert cur.fetchone()[0] is None


# --------------------------------------------------------------------------------------
# Tier 3 -- plpgsql_check call shape
# --------------------------------------------------------------------------------------

@pytest.fixture
def checked(conn):
    """A connection with plpgsql_check installed, or a skip explaining why not."""
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS plpgsql_check")
    except psycopg.Error as exc:  # not superuser, or the .so is not on the server
        pytest.skip(f"plpgsql_check unavailable: {exc}")
    return conn


def test_plpgsql_check_function_tb_column_order(checked):
    """Pinned because `CheckFinding` maps these positionally, and `position` must be
    double-quoted in the select list or it is a syntax error.
    """
    checked.execute("CREATE TABLE IF NOT EXISTS t (id int)")
    checked.execute(
        "CREATE OR REPLACE FUNCTION broken() RETURNS int AS $$\n"
        "DECLARE r record;\n"
        "BEGIN SELECT * INTO r FROM t; RETURN r.no_such_column; END $$ LANGUAGE plpgsql"
    )
    with checked.cursor() as cur:
        cur.execute(
            "SELECT * FROM plpgsql_check_function_tb('broken()'::regprocedure, "
            "fatal_errors => false, all_warnings => true)"
        )
        assert [d.name for d in cur.description] == [
            "functionid", "lineno", "statement", "sqlstate", "message",
            "detail", "hint", "level", "position", "query", "context",
        ]
        rows = cur.fetchall()

    assert any("no_such_column" in str(r[4]) for r in rows), rows
    # A finding may legitimately have lineno=None (e.g. the routine-level volatility
    # warning), which is why the line mapping must render "no line" rather than guess.
    assert any(r[1] is None for r in rows), rows


def test_the_polymorphic_parameter_is_misspelled_anyelememttype(checked):
    """Upstream ships `anyelememttype` (m for n). Named-notation calls must use the typo."""
    checked.execute(
        "CREATE OR REPLACE FUNCTION poly(x anyelement) RETURNS text AS $$ "
        "BEGIN RETURN x::text; END $$ LANGUAGE plpgsql"
    )
    with pytest.raises(psycopg.errors.UndefinedFunction):
        checked.execute(
            "SELECT * FROM plpgsql_check_function_tb('poly(anyelement)'::regprocedure, "
            "anyelementtype => 'int'::regtype)"
        )
    checked.execute(
        "SELECT * FROM plpgsql_check_function_tb('poly(anyelement)'::regprocedure, "
        "anyelememttype => 'int'::regtype)"
    )  # the typo is the working spelling


def test_a_trigger_function_requires_relid(checked):
    """Omitting `relid` errors outright rather than returning findings."""
    checked.execute(
        "CREATE OR REPLACE FUNCTION trg_fn() RETURNS trigger AS $$ "
        "BEGIN RETURN NEW; END $$ LANGUAGE plpgsql"
    )
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        checked.execute(
            "SELECT * FROM plpgsql_check_function_tb('trg_fn()'::regprocedure)"
        )
