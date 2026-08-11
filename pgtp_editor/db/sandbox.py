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

# pgtp_editor/db/sandbox.py
"""The sandbox capability probe, provisioning and lifecycle (§18.5 D2), plus
"with data" clone tooling (D2a).

**This module now covers all of D2's core:** the capability probe
(`SandboxCapabilities`/`probe`); the pure, in-process schema-only baseline
builder (`build_baseline_sql`); the ownership-by-naming-convention guard
(`is_app_owned`/`ForeignDatabaseError`/`open_sandbox`/`create_sandbox_database`);
the stateful, accumulating `SandboxSession` (`apply`/`applied`/`reset`) and its
`provision`/`provision_sandbox` entry point; and the one-click `plpgsql_check`
install (`install_gate`/`install_plpgsql_check`). D2a's data-clone tool
detection/invocation (`clone_data`) composes with all of the above without
being touched by it.

This slice was already reused by §18.2's **New Project** dialog for its
local-sandbox **Test** button, whose specific job is verifying the connected
user is a **superuser** (`CREATE EXTENSION` requires it) -- not merely "can
connect". The spec is explicit that this must be *the same* probe the rest of
the sandbox lane uses, not a second ad hoc superuser check.

**D2a ("with data" cloning) is a deliberate, narrowly-scoped exception** to
this module's otherwise-holding "zero bundled bytes, no external process"
invariant: `clone_data` shells out to the `pg_dump`/`pg_restore` binaries on
the user's `PATH` (never bundled). This exception applies ONLY to the
with-data clone path -- the schema-only baseline path (`build_baseline_sql`)
stays in-process/`psycopg`-only, and `psql`/`pg_restore` are never required
just to run a schema-only sandbox.

Qt-free and, like `db/introspect.py`, opens no connection/process except
through the injectable `runner`/`which`/`run` seams -- the whole test suite
runs with psycopg absent and no real `pg_dump`/`pg_restore` binaries on disk.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from .config import ConnectionParams
from .introspect import (
    BaselineSnapshot,
    ColumnInfo,
    DatabaseSchema,
    Runner,
    TableInfo,
    TypeInfo,
    run_queries,
)

#: Injectable seam over `shutil.which`, mirroring `Runner` above -- tests
#: never need real binaries on `PATH` to exercise tool-detection logic.
Which = Callable[[str], "str | None"]

#: Injectable seam over `subprocess.run` for the `pg_dump`/`pg_restore`
#: invocations (D2a) -- tests supply a canned stand-in, never a real process.
ProcessRunner = Callable[..., "subprocess.CompletedProcess[bytes]"]

#: The external binaries D2a's "with data" clone path needs on `PATH`. Per
#: the taxonomy at the top of §18, these are required ONLY for the "with
#: data" clone variant -- the schema-only baseline path needs neither.
DATA_CLONE_TOOLS = ("pg_dump", "pg_restore")

#: Sibling of `db/introspect.py::SCHEMA_SQL` -- run as ONE call so the whole
#: probe is one connection, one round trip (§18.5 D2).
PROBE_SQL = [
    "SELECT current_setting('server_version_num')",
    "SELECT current_setting('is_superuser')",
    "SELECT extname FROM pg_extension",
    "SELECT name FROM pg_available_extensions",
    "SELECT current_database(), shobj_description("
    "(SELECT oid FROM pg_database WHERE datname = current_database()), 'pg_database')",
]


@dataclass(frozen=True)
class SandboxCapabilities:
    """What `probe` learned about a Postgres connection -- three real states
    plus `"unknown"`, never a silent `"absent"` (§18.5 D2).

    `is_superuser` is read via `current_setting('is_superuser')`, which
    (unlike `pg_user.usesuper`) also works for a non-superuser connection --
    it never raises a permissions error just for asking.
    """

    server_version: tuple[int, ...] = ()
    is_superuser: bool = False
    installed_extensions: frozenset[str] = frozenset()
    available_extensions: frozenset[str] = frozenset()
    database: str = ""
    owner_marker: str | None = None
    #: Set instead of raising when `probe` could not reach/query the server.
    #: Every other field is left at its default in that case.
    probe_error: str | None = None
    #: D2a -- absolute paths of `pg_dump`/`pg_restore` if found on `PATH`,
    #: else None. Irrelevant to the schema-only baseline path (which needs
    #: neither); only consulted when the user chooses "with data" cloning.
    pg_dump_path: str | None = None
    pg_restore_path: str | None = None

    @property
    def data_clone_available(self) -> bool:
        """Whether D2a's "with data" clone path can run at all -- both
        `pg_dump` and `pg_restore` must be present on `PATH`. Never implies
        anything about the schema-only path, which needs neither."""
        return self.pg_dump_path is not None and self.pg_restore_path is not None

    @property
    def plpgsql_check_state(self) -> str:
        """`"installed" | "installable" | "absent" | "unknown"`.

        Returns `"unknown"` whenever `probe_error` is set and never degrades
        to `"absent"` -- a probe failure means "could not check", which must
        never be reported the same way as "genuinely not there" (§18.5 D2/D3
        embrace-drift discipline: report what's missing as missing, not as
        silently absent).
        """
        if self.probe_error is not None:
            return "unknown"
        if "plpgsql_check" in self.installed_extensions:
            return "installed"
        if "plpgsql_check" in self.available_extensions:
            return "installable"
        return "absent"


def _decode_server_version(raw: str) -> tuple[int, ...]:
    """`server_version_num` (e.g. `"160003"`) -> `(16, 0, 3)` -- PostgreSQL's
    `MMmmpp` integer encoding (major, always-00 minor since PG10, patch)."""
    number = int(raw)
    major, remainder = divmod(number, 10000)
    minor, patch = divmod(remainder, 100)
    return (major, minor, patch)


def probe(
    params: ConnectionParams,
    runner: Runner = run_queries,
    which: Which = shutil.which,
) -> SandboxCapabilities:
    """Probe a Postgres connection's capabilities in one round trip, plus
    (D2a) whether `pg_dump`/`pg_restore` are on `PATH`.

    **Never raises** -- any failure (unreachable host, bad credentials, a
    server too old to know one of the settings queried) becomes
    `probe_error`, mirroring `db/introspect.py::test_connection`'s
    never-raises contract. Tool detection is independent of the DB round
    trip and never itself fails the probe -- `shutil.which` doesn't raise.
    """
    pg_dump_path = which("pg_dump")
    pg_restore_path = which("pg_restore")
    try:
        rows = runner(params, PROBE_SQL)
        version_rows, superuser_rows, installed_rows, available_rows, db_rows = rows
        server_version = _decode_server_version(str(version_rows[0][0]))
        is_superuser = str(superuser_rows[0][0]).strip().lower() in ("on", "true", "t", "1")
        installed_extensions = frozenset(row[0] for row in installed_rows)
        available_extensions = frozenset(row[0] for row in available_rows)
        database, owner_marker = db_rows[0]
    except Exception as exc:  # noqa: BLE001 -- surface any failure as probe_error
        return SandboxCapabilities(
            probe_error=str(exc),
            pg_dump_path=pg_dump_path,
            pg_restore_path=pg_restore_path,
        )
    return SandboxCapabilities(
        server_version=server_version,
        is_superuser=is_superuser,
        installed_extensions=installed_extensions,
        available_extensions=available_extensions,
        database=database,
        owner_marker=owner_marker,
        probe_error=None,
        pg_dump_path=pg_dump_path,
        pg_restore_path=pg_restore_path,
    )


# ---------------------------------------------------------------------------
# Identifier quoting (§18.5 D2: "every identifier is quoted through a strict
# allowlist helper; a schema named `weird"name` is refused, never
# string-interpolated")
# ---------------------------------------------------------------------------

#: A conservative, safe subset of valid PostgreSQL identifiers: starts with a
#: letter or underscore, then letters/digits/underscores/`$`. This is
#: deliberately NARROWER than everything Postgres itself allows (e.g. it
#: rejects identifiers that need double-quoting to spell at all) -- the
#: point is a strict allowlist that refuses anything even slightly
#: adversarial, not maximal coverage of legal catalog names.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class UnsafeIdentifierError(ValueError):
    """Raised by `quote_ident` when a would-be identifier fails the strict
    allowlist (§18.5 D2) -- never silently escaped/interpolated instead."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(
            f"refusing to quote {identifier!r} as a SQL identifier -- it does "
            "not match the safe identifier allowlist "
            f"({_SAFE_IDENTIFIER_RE.pattern})"
        )


def quote_ident(name: str) -> str:
    """Double-quote `name` for safe interpolation into generated DDL --
    but ONLY after validating it against `_SAFE_IDENTIFIER_RE`. Raises
    `UnsafeIdentifierError` for anything else (e.g. a schema literally named
    `weird"name`) rather than escaping arbitrary content, which is exactly
    the "validated, not sanitized" posture `create_sandbox_database` also
    uses for database names (§18.5 D2).
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise UnsafeIdentifierError(name)
    return f'"{name}"'


# ---------------------------------------------------------------------------
# D2a -- optional "with data" sandbox cloning
# ---------------------------------------------------------------------------
class SandboxMode(str, Enum):
    """How a sandbox database was (or will be) provisioned (§18.5 D2a).

    **Chosen once, at sandbox-creation time, and recorded -- never
    re-derived.** `reset()` must re-run whichever mode the sandbox was
    originally created with, so the mode is stored alongside the sandbox's
    other project-scoped state (`db/ddl_project.py::ProjectSettings`), not
    guessed at from the database's current contents.
    """

    #: The default -- today's existing in-process `build_baseline_sql` path.
    #: Zero rows, zero external processes.
    SCHEMA_ONLY = "schema_only"
    #: D2a's optional mode -- `pg_dump`/`pg_restore` clone the target
    #: database's data into the sandbox, instead of `build_baseline_sql`.
    WITH_DATA = "with_data"


class MissingCloneToolError(RuntimeError):
    """A named, actionable failure (§18.5 D2a: "a missing `pg_dump`/
    `pg_restore`/local-Postgres is a named, surfaced failure -- never a
    silent fallback to schema-only"). Carries which binary was missing and
    what `PATH` was searched, so the message can be shown verbatim."""

    def __init__(self, binary: str, path_searched: str) -> None:
        self.binary = binary
        self.path_searched = path_searched
        super().__init__(
            f"'{binary}' was not found on PATH ({path_searched}). Install "
            f"PostgreSQL client tools (providing '{binary}') or add them to "
            f"PATH, or choose 'without data' sandbox provisioning instead."
        )


class CloneDataError(RuntimeError):
    """`pg_dump`/`pg_restore` ran but one of them failed (non-zero exit) --
    a named, surfaced failure, never a silent fallback to schema-only."""

    def __init__(self, step: str, returncode: int, stderr: str) -> None:
        self.step = step
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"{step} failed (exit {returncode}): {stderr.strip() or '(no stderr output)'}"
        )


def require_data_clone_tools(which: Which = shutil.which) -> tuple[str, str]:
    """Locate `pg_dump`/`pg_restore` on `PATH`, or raise `MissingCloneToolError`
    naming exactly which binary is missing. Called before `clone_data` so the
    failure is reported up front, not mid-pipeline. Returns
    `(pg_dump_path, pg_restore_path)`.
    """
    path_searched = os.environ.get("PATH", "")
    pg_dump_path = which("pg_dump")
    if pg_dump_path is None:
        raise MissingCloneToolError("pg_dump", path_searched)
    pg_restore_path = which("pg_restore")
    if pg_restore_path is None:
        raise MissingCloneToolError("pg_restore", path_searched)
    return pg_dump_path, pg_restore_path


def _pg_env(params: ConnectionParams) -> dict[str, str]:
    """`pg_dump`/`pg_restore` read the password from `PGPASSWORD`, never a
    CLI argument (which would leak it into `ps`/shell history)."""
    env = dict(os.environ)
    if params.password:
        env["PGPASSWORD"] = params.password
    return env


def clone_data(
    target_params: ConnectionParams,
    sandbox_params: ConnectionParams,
    *,
    which: Which = shutil.which,
    run: ProcessRunner = subprocess.run,
) -> None:
    """D2a's "with data" clone: `pg_dump` (custom format) the **target**
    database, then `pg_restore` it into the (already `create_sandbox_database`-
    provisioned) **sandbox** database, as two external subprocesses.

    This is the one place in the module that shells out -- a deliberate,
    narrowly-scoped exception to "zero bundled bytes, no external process"
    (§18.5 D2a), which continues to hold for the schema-only baseline path.

    Raises `MissingCloneToolError` if either binary is absent from `PATH`
    (checked up front, before anything runs) and `CloneDataError` if either
    subprocess exits non-zero -- never silently falls back to schema-only.
    Both `which` and `run` are injectable so tests never need real binaries
    or a real Postgres server.
    """
    pg_dump_path, pg_restore_path = require_data_clone_tools(which=which)

    dump_result = run(
        [
            pg_dump_path,
            "--format=custom",
            "--host", target_params.host,
            "--port", str(target_params.port),
            "--username", target_params.user,
            "--dbname", target_params.database,
        ],
        env=_pg_env(target_params),
        capture_output=True,
    )
    dump_stdout = getattr(dump_result, "stdout", b"") or b""
    if dump_result.returncode != 0:
        stderr = (getattr(dump_result, "stderr", b"") or b"").decode("utf-8", errors="replace")
        raise CloneDataError("pg_dump", dump_result.returncode, stderr)

    restore_result = run(
        [
            pg_restore_path,
            "--host", sandbox_params.host,
            "--port", str(sandbox_params.port),
            "--username", sandbox_params.user,
            "--dbname", sandbox_params.database,
            "--no-owner",
            "--no-privileges",
        ],
        input=dump_stdout,
        env=_pg_env(sandbox_params),
        capture_output=True,
    )
    if restore_result.returncode != 0:
        stderr = (getattr(restore_result, "stderr", b"") or b"").decode("utf-8", errors="replace")
        raise CloneDataError("pg_restore", restore_result.returncode, stderr)


# ---------------------------------------------------------------------------
# Three operating modes -- tier determination (top of §18, settled 2026-08-05)
# ---------------------------------------------------------------------------
class ProjectTier(str, Enum):
    """Which of §18's three operating modes a project is currently running
    in. Tier 1 ("standalone") has no project open at all and is therefore
    never returned by `determine_project_tier`, which only ever compares
    tier 2 against tier 3 for an already-open project."""

    #: A local project with **no working sandbox** -- either never
    #: configured, or the environment doesn't currently support one. This is
    #: graceful degradation, never an error.
    QUALITY = "quality"
    #: A quality project **plus** a working local sandbox.
    DEVELOPMENT = "development"


@dataclass(frozen=True)
class ProjectCapabilityStatus:
    """The result of one capability probe for an open project (top of §18)
    -- what tier the project is running in right now, plus, if degraded,
    exactly why (never a bare "sandbox unavailable" with no reason). This is
    the value the not-yet-designed "Project Status" screen will eventually
    render; nothing consumes it here except storing it for that later use.
    """

    tier: ProjectTier
    capabilities: SandboxCapabilities
    #: Human-readable reason the project is NOT in tier 3, or None when it
    #: is. Never populated when `tier is DEVELOPMENT`.
    degraded_reason: str | None = None


def determine_project_tier(
    capabilities: SandboxCapabilities,
    sandbox_mode: SandboxMode,
    sandbox_configured: bool = True,
) -> ProjectCapabilityStatus:
    """Decide tier 2 ("quality project") vs. tier 3 ("development project")
    from a capability probe and the project's recorded sandbox mode (top of
    §18's "Three operating modes" taxonomy).

    **A working sandbox requires:** a sandbox connection was configured at
    all (`sandbox_configured` -- tier 2's "either the user never configured
    one" branch); the probe reached the server with no `probe_error` (a
    reachable local Postgres); and, ONLY when `sandbox_mode is WITH_DATA`,
    that `pg_dump`/`pg_restore` are ALSO on `PATH` (`data_clone_available`).
    A schema-only sandbox needs neither tool, matching D2/D2a's "psql/
    pg_restore are NOT a tier-3 prerequisite in general -- only for the
    with-data variant."

    Never raises -- missing capability requirements degrade the result to
    `QUALITY` with a named reason, exactly the embrace-drift posture the
    `*`/`!` markers already use elsewhere; they are never treated as errors.
    """
    if not sandbox_configured:
        return ProjectCapabilityStatus(
            tier=ProjectTier.QUALITY,
            capabilities=capabilities,
            degraded_reason="no local sandbox configured for this project",
        )
    if capabilities.probe_error is not None:
        return ProjectCapabilityStatus(
            tier=ProjectTier.QUALITY,
            capabilities=capabilities,
            degraded_reason=f"sandbox unreachable: {capabilities.probe_error}",
        )
    if sandbox_mode is SandboxMode.WITH_DATA and not capabilities.data_clone_available:
        missing = [
            name
            for name, path in (
                ("pg_dump", capabilities.pg_dump_path),
                ("pg_restore", capabilities.pg_restore_path),
            )
            if path is None
        ]
        return ProjectCapabilityStatus(
            tier=ProjectTier.QUALITY,
            capabilities=capabilities,
            degraded_reason=f"sandbox unavailable: {' and '.join(missing)} not found on PATH",
        )
    return ProjectCapabilityStatus(tier=ProjectTier.DEVELOPMENT, capabilities=capabilities)


# ---------------------------------------------------------------------------
# Baseline provisioning -- schemas -> types -> tables -> views -> routines ->
# triggers, in that LOAD-BEARING order (§18.5 D2)
# ---------------------------------------------------------------------------

#: Prepended once, before any routine, so one bad pre-existing routine cannot
#: block provisioning of the rest of the baseline (§18.5 D2). A single
#: session-level `SET`, not repeated per routine -- it stays in effect for
#: every subsequent `CREATE FUNCTION`/`CREATE PROCEDURE` in the same session.
_CHECK_FUNCTION_BODIES_OFF_SQL = "SET check_function_bodies = off"


def _split_qualified(name: str) -> tuple[str, str]:
    """`"schema.name"` -> `(schema, name)` -- every model key in
    `DatabaseSchema` (`TableInfo.name`, `TypeInfo.qualified_name`) is exactly
    one `.`-joined pair; `RoutineInfo`/`TriggerInfo` already carry `.schema`
    separately and don't go through this helper."""
    schema, _, rest = name.partition(".")
    return schema, rest


def build_baseline_sql(snapshot: DatabaseSchema | BaselineSnapshot) -> list[str]:
    """Build the ordered DDL statement list that provisions a fresh sandbox
    from `snapshot` (§18.5 D2). **Pure -- no I/O, no DB** -- the caller is
    responsible for executing the returned statements (`provision_sandbox`
    does, through a `SandboxSession`).

    **Order is load-bearing:** schemas -> types (domains and composites) ->
    tables (columns + `format_type` + `attnotnull` only) -> views/matviews ->
    routines -> triggers. `plpgsql_check` is catalog-based and reads no
    rows -- it needs relations, columns and types to *exist*, nothing more --
    so this is exactly the minimum catalog shape that satisfies it, no more.

    **Deliberately omitted:** primary keys, foreign keys, `DEFAULT` (which
    also sidesteps `nextval('seq')` needing sequences), indexes, extensions,
    sequences, and all data. `ColumnInfo.is_pk`/`is_fk`/`default` are read
    from `snapshot` for other purposes elsewhere but never rendered here.

    Routines are emitted after a single `SET check_function_bodies = off`
    statement, so one bad pre-existing routine cannot block provisioning of
    the rest. Triggers come after routines because `CREATE TRIGGER` resolves
    its function immediately and would fail against a not-yet-created one.

    Every identifier goes through `quote_ident` -- a schema/table/column
    named with adversarial content is refused (`UnsafeIdentifierError`),
    never string-interpolated as-is.
    """
    schema = snapshot.schema if isinstance(snapshot, BaselineSnapshot) else snapshot

    statements: list[str] = []

    schema_names = _collect_schema_names(schema)
    for schema_name in sorted(schema_names):
        statements.append(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema_name)}")

    for type_info in sorted(schema.types.values(), key=lambda t: t.qualified_name):
        statements.append(_build_type_sql(type_info))

    tables_only = [t for t in schema.tables.values() if t.kind == "table"]
    for table in sorted(tables_only, key=lambda t: t.name):
        statements.append(_build_table_sql(table))

    views_only = [t for t in schema.tables.values() if t.kind in ("view", "matview")]
    for table in sorted(views_only, key=lambda t: t.name):
        statements.append(_build_view_sql(table))

    if schema.routines:
        statements.append(_CHECK_FUNCTION_BODIES_OFF_SQL)
        for routine in sorted(schema.routines.values(), key=lambda r: r.signature):
            statements.append(routine.source)

    for trigger in sorted(schema.triggers.values(), key=lambda t: (t.schema, t.table, t.name)):
        statements.append(trigger.definition)

    return statements


def _collect_schema_names(schema: DatabaseSchema) -> set[str]:
    """Every distinct schema referenced by tables, types, routines or
    triggers -- `CREATE SCHEMA IF NOT EXISTS` is emitted once per name."""
    names: set[str] = set()
    for table in schema.tables.values():
        table_schema, _ = _split_qualified(table.name)
        if table_schema:
            names.add(table_schema)
    for type_info in schema.types.values():
        names.add(type_info.schema)
    for routine in schema.routines.values():
        names.add(routine.schema)
    for trigger in schema.triggers.values():
        names.add(trigger.schema)
    return names


def _build_type_sql(type_info: TypeInfo) -> str:
    """`CREATE DOMAIN`/`CREATE TYPE ... AS (...)` for one `TypeInfo`.

    Domains carry base type + `NOT NULL` only -- `CHECK` constraints are
    deliberately not reconstructed here (§18.5 D2's catalog-based baseline
    omits constraint fidelity the same way it does for tables)."""
    qualified = f"{quote_ident(type_info.schema)}.{quote_ident(type_info.name)}"
    if type_info.kind == "domain":
        sql = f"CREATE DOMAIN {qualified} AS {type_info.base_type}"
        if type_info.not_null:
            sql += " NOT NULL"
        return sql
    attrs = ", ".join(
        f"{quote_ident(attr_name)} {attr_type}" for attr_name, attr_type in type_info.attributes
    )
    return f"CREATE TYPE {qualified} AS ({attrs})"


def _build_table_sql(table: TableInfo) -> str:
    """`CREATE TABLE` with columns + `format_type` + `attnotnull` only --
    never PK/FK/DEFAULT/indexes (§18.5 D2's omission list)."""
    schema_name, table_name = _split_qualified(table.name)
    qualified = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"
    columns_sql = ", ".join(_build_column_sql(column) for column in table.columns)
    return f"CREATE TABLE {qualified} ({columns_sql})"


def _build_column_sql(column: ColumnInfo) -> str:
    sql = f"{quote_ident(column.name)} {column.data_type}"
    if not column.is_nullable:
        sql += " NOT NULL"
    return sql


def _build_view_sql(table: TableInfo) -> str:
    """`CREATE VIEW`/`CREATE MATERIALIZED VIEW` from the captured
    `pg_get_viewdef` text (§18.5 D2's "recorded gap" closure). A missing
    `view_definition` (e.g. an older snapshot taken before this closure)
    degrades to an empty-body stub rather than raising -- the surrounding
    `CREATE TABLE`s it may depend on still get created."""
    schema_name, view_name = _split_qualified(table.name)
    qualified = f"{quote_ident(schema_name)}.{quote_ident(view_name)}"
    keyword = "CREATE MATERIALIZED VIEW" if table.kind == "matview" else "CREATE VIEW"
    definition = table.view_definition
    if not definition:
        return f"{keyword} {qualified} AS SELECT NULL WHERE FALSE"
    return f"{keyword} {qualified} AS {definition}"


# ---------------------------------------------------------------------------
# Ownership guard -- the only safety property left (§18.5 D2)
# ---------------------------------------------------------------------------

#: Two markers, because one is not enough (§18.5 D2): the database NAME
#: alone is spoofable (a user can name production `pgtp_sandbox_prod`), so
#: ownership additionally requires a `pg_database` COMMENT written only by
#: our own provisioning.
SANDBOX_DB_PREFIX = "pgtp_sandbox_"
OWNER_MARKER_PREFIX = "pgtp-editor-sandbox:"

#: `create_sandbox_database`'s name validation -- VALIDATED, not sanitized;
#: anything else is refused outright (§18.5 D2).
_SANDBOX_DB_NAME_RE = re.compile(r"^pgtp_sandbox_[a-z0-9_]{1,40}$")

#: The reserved bookkeeping schema `SandboxSession.reset()` must NEVER drop
#: (§18.5 D2: "never the reserved bookkeeping schema").
BOOKKEEPING_SCHEMA = "pgtp_editor_sandbox"


def is_app_owned(database: str, owner_marker: str | None) -> bool:
    """True only when `database` starts with `SANDBOX_DB_PREFIX` **and**
    `owner_marker` (the `pg_database` comment) starts with
    `OWNER_MARKER_PREFIX` (§18.5 D2). Pure -- no I/O.

    The name alone is spoofable (a user can name production
    `pgtp_sandbox_prod`); the comment is written only by our own
    `create_sandbox_database`, so both must agree.
    """
    if not database.startswith(SANDBOX_DB_PREFIX):
        return False
    if owner_marker is None:
        return False
    return owner_marker.startswith(OWNER_MARKER_PREFIX)


class ForeignDatabaseError(RuntimeError):
    """Raised by `open_sandbox` when the connected database is not
    app-owned (§18.5 D2) -- psycopg-free, a hard error surfaced to the user,
    never a silently-executed DDL statement against someone's real database.
    """

    def __init__(self, database: str) -> None:
        self.database = database
        super().__init__(
            f"{database!r} is not a sandbox PGTP Editor created: PGTP Editor "
            "did not create this database and will not write to it."
        )


def create_sandbox_database(
    admin_params: ConnectionParams,
    name: str,
    *,
    runner: "AutocommitRunner | None" = None,
) -> None:
    """Create a fresh app-owned sandbox database named `name` and stamp its
    ownership marker (§18.5 D2).

    `name` is **validated, not sanitized** against `_SANDBOX_DB_NAME_RE`:
    anything else is refused via `UnsafeIdentifierError` rather than being
    coerced into something safe. Runs `CREATE DATABASE` then
    `COMMENT ON DATABASE ... IS 'pgtp-editor-sandbox:<uuid>:<iso8601>'` with
    `autocommit=True` against `admin_params`'s (maintenance) database --
    PostgreSQL forbids `CREATE DATABASE` inside a transaction block. **This
    is the ONE `autocommit=True` call in the app**, made from this module
    and nowhere else.

    `runner` is the injectable autocommit-execution seam (defaults to the
    real `_run_autocommit`, the only other psycopg touchpoint besides
    `db/introspect.py::run_queries` and `SandboxSession`'s own executor);
    tests supply a fake that records the statements it was given.
    """
    if not _SANDBOX_DB_NAME_RE.match(name):
        raise UnsafeIdentifierError(name)
    if runner is None:
        runner = _run_autocommit
    marker = f"{OWNER_MARKER_PREFIX}{uuid.uuid4()}:{datetime.now(timezone.utc).isoformat()}"
    statements = [
        f"CREATE DATABASE {quote_ident(name)}",
        f"COMMENT ON DATABASE {quote_ident(name)} IS {_sql_string_literal(marker)}",
    ]
    runner(admin_params, statements)


def _sql_string_literal(text: str) -> str:
    """A single-quoted SQL string literal, with embedded single quotes
    doubled -- used only for the marker comment's own VALUE (never an
    identifier; identifiers always go through `quote_ident`)."""
    return "'" + text.replace("'", "''") + "'"


#: Injectable seam for a single `autocommit=True` connection running a list
#: of statements in order -- used ONLY by `create_sandbox_database` (§18.5
#: D2: "the ONE autocommit=True call in the app").
AutocommitRunner = Callable[[ConnectionParams, list[str]], None]


def _run_autocommit(params: ConnectionParams, statements: list[str]) -> None:
    """The real `AutocommitRunner` -- opens ONE `autocommit=True` connection
    and runs each statement in order. Lazily imports psycopg exactly like
    `db/introspect.py::run_queries` does, so the module stays importable
    (and this whole test suite runnable) without the driver installed."""
    import psycopg  # noqa: PLC0415 -- lazy on purpose (see module docstring)

    connection = psycopg.connect(
        host=params.host or None,
        port=params.port or None,
        dbname=params.database or None,
        user=params.user or None,
        password=params.password or None,
        autocommit=True,
    )
    try:
        for statement in statements:
            with connection.cursor() as cursor:
                cursor.execute(statement)
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# SandboxSession -- the accumulating, working-set-tracked sandbox connection
# (§18.5 D2)
# ---------------------------------------------------------------------------

#: The reserved bookkeeping table's columns, verbatim from §18.5 D2:
#: `applied(kind text, schema_name text, object_name text, table_name text,
#: applied_at timestamptz, text_sha1 text, primary key (kind, schema_name,
#: object_name, table_name))`.
_APPLIED_TABLE_QUALIFIED = f"{quote_ident(BOOKKEEPING_SCHEMA)}.{quote_ident('applied')}"

_CREATE_BOOKKEEPING_SQL = [
    f"CREATE SCHEMA IF NOT EXISTS {quote_ident(BOOKKEEPING_SCHEMA)}",
    f"""CREATE TABLE IF NOT EXISTS {_APPLIED_TABLE_QUALIFIED} (
        kind text NOT NULL,
        schema_name text NOT NULL,
        object_name text NOT NULL,
        table_name text NOT NULL,
        applied_at timestamptz NOT NULL,
        text_sha1 text NOT NULL,
        PRIMARY KEY (kind, schema_name, object_name, table_name)
    )""",
]

#: **The one-time cleanup of pre-BUG-044 alter rows (DEC-008).**
#:
#: Before BUG-044 every ALTER-family buffer on one table wrote the single key
#: `(kind='alter', schema, object_name='', table)` and silently overwrote the
#: previous one. Those rows carry no attribution to any statement -- the value
#: that would identify them was never recorded -- so they can only ever produce
#: a wrong answer or none, and nothing of value is lost by deleting them.
#: They survive `SandboxSession.reset()`, which deliberately spares
#: `BOOKKEEPING_SCHEMA`, which is why a cleanup is needed at all rather than
#: waiting for the next reset.
#:
#: **Why this predicate cannot touch an object row.** It requires BOTH halves:
#: - `kind = 'alter'` is written by exactly one ref type, `ui/main_window.py::
#:   AlterDdlRef`, whose `kind` is the frozen default `"alter"`. No
#:   `DdlObjectRef` ever carries it (its kinds are `function`/`procedure`/
#:   `trigger`), so no object row can match this half at all -- the predicate
#:   is already precise before the second half is considered.
#: - `object_name = ''` cannot match a *post-fix* alter row either: those carry
#:   `text_sha1(statement)`, a 40-character hex digest that is never empty --
#:   `text_sha1("")` is a hash, not `""`. So the delete cannot eat a row this
#:   version wrote, only rows the buggy version wrote.
#: An object row would have to be an unnamed function to match, and an object
#: with no name is not writable through any path: `working_set_ref` takes
#: `object_name` from `CheckRequest.name`, and a nameless request cannot reach
#: apply (tier 3 and `regprocedure_text` both key off the same value).
_DELETE_ORPHANED_ALTER_ROWS_SQL = (
    f"DELETE FROM {_APPLIED_TABLE_QUALIFIED} "
    f"WHERE kind = 'alter' AND object_name = ''"
)


@dataclass(frozen=True)
class AppliedObject:
    """One row of the `pgtp_editor_sandbox.applied` bookkeeping table
    (§18.5 D2) -- mirrors its columns exactly. `text_sha1` is what lets the
    UI say "this tab has changed since you last applied it" and what makes
    **Check** refuse to silently validate a stale version.
    """

    kind: str
    schema_name: str
    object_name: str
    table_name: str
    applied_at: str
    text_sha1: str


def text_sha1(ddl_text: str) -> str:
    """The `applied.text_sha1` fingerprint of one object's DDL text.

    One function, because two callers need the *same* number for the same
    text: `SandboxSession.apply` writes it, and §18.5 D3's `recheck` compares
    the caller's buffer against it to refuse to silently validate a stale
    version. Two independent hashings of "the buffer" would drift the moment
    one of them normalized whitespace.
    """
    return hashlib.sha1(ddl_text.encode("utf-8")).hexdigest()  # noqa: S324 -- content fingerprint, not security


def applied_upsert_sql(ref: Sequence[str], ddl_text: str) -> str:
    """The `applied` bookkeeping upsert for one object, as **one statement**.

    Exposed (rather than inlined in `SandboxSession.apply`) because §18.5 D3's
    `apply_and_check` must write this row **inside the ladder's own
    transaction** -- the DDL, the bookkeeping row and the `plpgsql_check`
    SELECT share one `db/apply.py::apply_ddl` call, so the ladder needs the
    statement text, not a second committing round trip that could land without
    the DDL (or vice versa). `db/ddl_check.py` composes it; this module still
    owns what the row *is*.
    """
    kind, schema_name, object_name, table_name = ref
    applied_at = datetime.now(timezone.utc).isoformat()
    return f"""
            INSERT INTO {_APPLIED_TABLE_QUALIFIED}
                (kind, schema_name, object_name, table_name, applied_at, text_sha1)
            VALUES ({_sql_string_literal(kind)}, {_sql_string_literal(schema_name)},
                    {_sql_string_literal(object_name)}, {_sql_string_literal(table_name)},
                    {_sql_string_literal(applied_at)}, {_sql_string_literal(text_sha1(ddl_text))})
            ON CONFLICT (kind, schema_name, object_name, table_name)
            DO UPDATE SET applied_at = EXCLUDED.applied_at, text_sha1 = EXCLUDED.text_sha1
        """


@dataclass(frozen=True)
class FetchedRows:
    """What `SandboxExecutor.fetch` hands back -- the driver's raw answer to
    **one** capped statement, before any truncation decision or timing.

    Deliberately dumb: the executor's whole job is the wire, and every
    decision about truncation, timing and presentation is made by its caller
    (`db/sandbox_query.py::run_sandbox_query`) where it is testable without a
    database.

    `columns is None` **exactly** when the statement produced no result set
    (psycopg leaves `cursor.description` None for DML/DDL) -- the single signal
    separating "rows" from "no rows", taken from the driver rather than guessed
    by pattern-matching the SQL text. The same signal
    `db/apply.py::StatementResult` uses.

    `rows` may carry **one row more** than the caller's cap; that extra row is
    how truncation becomes a *fact* rather than an inference from
    `len(rows) == cap`, and it is dropped before it reaches a `QueryResult`.

    Lives here, not in `db/sandbox_query.py`, because it is the return type of
    a `SandboxExecutor` method and the seam owns its own vocabulary
    (`sandbox_query` re-exports it under its historical name `RawResult`).
    """

    columns: tuple[str, ...] | None
    rows: Sequence[Sequence[Any]] = ()
    #: `cursor.rowcount` -- rows affected by a DML statement, or -1/None when
    #: the driver does not know.
    affected: int | None = None
    #: `cursor.statusmessage` (e.g. `"UPDATE 3"`, `"CREATE FUNCTION"`), shown
    #: verbatim rather than re-worded.
    status: str = ""


#: §18.5 D4's mandatory per-statement timeout, in milliseconds -- the console's
#: **primary** safety control (the row cap only bounds what comes back; this
#: bounds how long the server works). 30 s is long enough for any statement a
#: person waits at a console for, and short enough that a runaway one frees the
#: connection while they are still looking at the screen.
#:
#: **Lives here, not beside `DEFAULT_MAX_ROWS` in `db/sandbox_query.py`**, even
#: though that is the intuitive home: `sandbox_query` imports `sandbox` and never
#: the reverse, so declaring it there and importing it back into the executor
#: would be an import cycle. Same reasoning that moved `FetchedRows` here -- the
#: seam owns its own vocabulary; `sandbox_query` re-exports it.
DEFAULT_STATEMENT_TIMEOUT_MS = 30_000

#: The floor, in milliseconds. **There is deliberately no "unlimited" setting
#: anywhere in this lane** -- that absence is the half of the design that
#: carries the safety, so a caller can pick a longer timeout but never no
#: timeout. A sub-second floor would additionally make the control a foot-gun
#: (every statement cancelled before the planner finishes).
MIN_STATEMENT_TIMEOUT_MS = 1_000


class SandboxExecutor(Protocol):
    """The execution seam `SandboxSession` needs -- distinct from
    `db/introspect.py::Runner`, which is read-only-oriented (one connection,
    each SQL run and its rows collected, no explicit transaction semantics).
    `SandboxSession.apply` needs an atomic multi-statement transaction (DDL
    + the `applied` upsert together); `reset`/provisioning need to run a
    batch of DDL as one committing unit; `applied()` needs a plain read;
    D4's ad-hoc SQL console needs a **capped** single-statement run that may
    or may not return a result set (`fetch`).

    Implementations open ONE connection per call (mirroring `run_queries`),
    matching PostgreSQL's transactional-DDL semantics: every statement in
    `statements` commits together, or none of them do.

    **`fetch` is the third method deliberately, not a fourth seam.** §18.5's
    invariant 1 names exactly three connection-opening seams -- `run_queries`
    (read), `apply_ddl` (DDL write) and this one (the sandbox lane) -- and
    spells this protocol out as `execute`/`query`/`fetch`. Before it existed,
    `db/sandbox_query.py` opened its own psycopg connection, which was a
    fourth: ad-hoc SQL's whole safety argument is that it can reach nothing
    but an ownership-gated `SandboxSession`, and a private connection inside
    that module put its connection discipline outside the seam that guarantees
    it.
    """

    def execute(self, params: ConnectionParams, statements: Sequence[str]) -> None:
        """Run `statements` in order inside one transaction; commit at the
        end, or propagate the underlying exception (leaving nothing
        committed) if any statement fails."""
        ...

    def query(self, params: ConnectionParams, sql: str) -> list[tuple]:
        """Run one read-only `sql` statement and return its rows."""
        ...

    def fetch(
        self,
        params: ConnectionParams,
        sql: str,
        *,
        max_rows: int,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> FetchedRows:
        """Run **one** statement, which may be DML/DDL or a query, and return
        at most `max_rows + 1` rows plus the driver's own metadata.

        The extra row is fetched on purpose so the caller can distinguish a
        result set exactly at the cap from a truncated one (§18.5 D4:
        `truncated` is a fact, never inferred). `max_rows` is passed *down*
        rather than applied afterwards so a real implementation can
        `fetchmany` instead of dragging a million rows across the wire and
        discarding them.

        `statement_timeout_ms` is §18.5 D4's **mandatory** timeout, applied
        inside the statement's own transaction. It carries a default rather
        than being required so that "mandatory" means *there is always a
        timeout in force* -- an implementation (or an older caller) that says
        nothing gets 30 s, not forever. Values below
        `MIN_STATEMENT_TIMEOUT_MS` are clamped up; there is no value meaning
        "unlimited". A statement the server cancels comes back as an exception
        with sqlstate `57014`, which `db/sandbox_query.py::timeout_error` turns
        into D4's sentence.

        Commits on success, because an ad-hoc statement may legitimately be
        DML against the (disposable) sandbox and leaving it in a rolled-back
        limbo would be the surprising behaviour; a failure rolls back and
        propagates, so nothing lands half-applied.
        """
        ...


class _RealSandboxExecutor:
    """The real `SandboxExecutor` -- lazily imports psycopg exactly like
    `db/introspect.py::run_queries` and `_run_autocommit` do, so importing
    this module never requires the driver to be installed."""

    def execute(self, params: ConnectionParams, statements: Sequence[str]) -> None:
        import psycopg  # noqa: PLC0415 -- lazy on purpose (see module docstring)

        connection = psycopg.connect(
            host=params.host or None,
            port=params.port or None,
            dbname=params.database or None,
            user=params.user or None,
            password=params.password or None,
        )
        try:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def query(self, params: ConnectionParams, sql: str) -> list[tuple]:
        import psycopg  # noqa: PLC0415 -- lazy on purpose (see module docstring)

        connection = psycopg.connect(
            host=params.host or None,
            port=params.port or None,
            dbname=params.database or None,
            user=params.user or None,
            password=params.password or None,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            connection.close()

    def fetch(
        self,
        params: ConnectionParams,
        sql: str,
        *,
        max_rows: int,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> FetchedRows:
        import psycopg  # noqa: PLC0415 -- lazy on purpose (see module docstring)

        connection = psycopg.connect(
            host=params.host or None,
            port=params.port or None,
            dbname=params.database or None,
            user=params.user or None,
            password=params.password or None,
        )
        try:
            with connection.cursor() as cursor:
                # §18.5 D4's mandatory timeout, set FIRST and inside this
                # statement's own transaction.
                #
                # **`set_config(..., true)`, not `SET LOCAL statement_timeout =
                # %s`.** PostgreSQL's `SET` is a *utility* statement and takes
                # no bind parameters, so the `SET LOCAL` spelling could only be
                # written by interpolating a number that arrives from a spin box
                # into SQL. `set_config`'s third argument `true` IS `SET LOCAL`
                # scope (transaction-local, discarded at commit) and it does
                # take a parameter. psycopg 3 is not in autocommit here (this
                # method commits explicitly below), so a transaction is open and
                # the local scope covers the statement.
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    (
                        f"{max(int(statement_timeout_ms), MIN_STATEMENT_TIMEOUT_MS)}ms",
                    ),
                )
                cursor.execute(sql)
                description = cursor.description
                if description is None:
                    # DML/DDL: psycopg 3 RAISES on fetch* here, so the guard is
                    # required, not defensive (§18.5's write-seam correction).
                    result = FetchedRows(
                        columns=None,
                        rows=(),
                        affected=cursor.rowcount,
                        status=cursor.statusmessage or "",
                    )
                else:
                    result = FetchedRows(
                        columns=tuple(str(column[0]) for column in description),
                        rows=cursor.fetchmany(max_rows + 1),
                        affected=cursor.rowcount,
                        status=cursor.statusmessage or "",
                    )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


#: The default, real `SandboxExecutor` -- module-level so `open_sandbox`/
#: `provision_sandbox` can default to it exactly like `probe`/`fetch_schema`
#: default to `run_queries`.
DEFAULT_SANDBOX_EXECUTOR: SandboxExecutor = _RealSandboxExecutor()


@dataclass
class SandboxSession:
    """A live, app-owned sandbox connection and its accumulating working
    set (§18.5 D2). **Creatable only through `open_sandbox`**, which is the
    single ownership gate -- nothing else in the codebase re-checks
    ownership and no write path bypasses the session.

    `mode` and `schema_names` are recorded at construction time (never
    re-derived) so `reset()` can re-run the correct provisioning without any
    further input beyond, for a `WITH_DATA` sandbox, the target params to
    re-clone from.
    """

    params: ConnectionParams
    mode: SandboxMode
    #: Every app schema the baseline (or clone) created -- what `reset()`
    #: drops with `DROP SCHEMA ... CASCADE`. Never includes
    #: `BOOKKEEPING_SCHEMA`.
    schema_names: frozenset[str] = frozenset()
    #: The `DatabaseSchema`/`BaselineSnapshot` this session was provisioned
    #: from -- `reset()` re-runs `build_baseline_sql` against this same
    #: snapshot for a `SCHEMA_ONLY` sandbox. Unused (may be None) for a
    #: `WITH_DATA` sandbox, whose reset instead re-clones from
    #: `target_params`.
    baseline: DatabaseSchema | BaselineSnapshot | None = None
    #: Needed only to re-clone on `reset()` for a `WITH_DATA` sandbox.
    target_params: ConnectionParams | None = None
    executor: SandboxExecutor = field(default=DEFAULT_SANDBOX_EXECUTOR)

    def apply(self, ref: str, ddl_text: str) -> None:
        """Apply one DDL object's text and record it in the `applied`
        working-set table -- **one committing, atomic call**: the DDL plus
        the bookkeeping upsert together, in a single transaction (§18.5 D2).

        `ref` is the object's `kind/schema_name/object_name/table_name`
        4-tuple already assembled into `AppliedObject`-shaped values by the
        caller (`db/ddl_check.py`, not built in this pass) -- accepted here
        as a `(kind, schema_name, object_name, table_name)` tuple so this
        module makes no assumption about how callers derive it.
        """
        self.executor.execute(
            self.params, [ddl_text, applied_upsert_sql(ref, ddl_text)]
        )

    def applied(self) -> list[AppliedObject]:
        """One `SELECT` over the `applied` bookkeeping table (§18.5 D2).

        The deployment generator is now its ONLY reader: the Sandbox Setup
        dialog's working-set list was the other, and that dialog was deleted on
        2026-08-09 when its provisioning gestures moved into Project Settings.
        Nothing in the app currently SHOWS the working set."""
        rows = self.executor.query(
            self.params,
            f"SELECT kind, schema_name, object_name, table_name, applied_at, text_sha1 "
            f"FROM {_APPLIED_TABLE_QUALIFIED}",
        )
        return [
            AppliedObject(
                kind=kind,
                schema_name=schema_name,
                object_name=object_name,
                table_name=table_name,
                applied_at=str(applied_at),
                text_sha1=text_sha1,
            )
            for kind, schema_name, object_name, table_name, applied_at, text_sha1 in rows
        ]

    def reset(self) -> None:
        """Schema-level reset (§18.5 D2): `DROP SCHEMA <each app schema>
        CASCADE` for every schema in `self.schema_names` (never
        `BOOKKEEPING_SCHEMA`), then re-runs whichever mode this sandbox was
        created with -- `build_baseline_sql` against `self.baseline` for
        `SCHEMA_ONLY`, or a fresh `clone_data` from `self.target_params` for
        `WITH_DATA`. Deliberately never `DROP DATABASE` (forbidden while any
        session is connected, and would need a maintenance-database
        connection plus `WITH (FORCE)`, PG13+) -- schema-level reset is just
        as complete here.
        """
        drop_statements = [
            f"DROP SCHEMA IF EXISTS {quote_ident(name)} CASCADE"
            for name in sorted(self.schema_names)
            if name != BOOKKEEPING_SCHEMA
        ]
        if drop_statements:
            self.executor.execute(self.params, drop_statements)

        if self.mode is SandboxMode.WITH_DATA:
            if self.target_params is None:
                raise ValueError(
                    "SandboxSession.reset() for a WITH_DATA sandbox requires "
                    "target_params to re-clone from, but none were recorded"
                )
            clone_data(self.target_params, self.params)
        elif self.baseline is not None:
            statements = build_baseline_sql(self.baseline)
            if statements:
                self.executor.execute(self.params, statements)


def open_sandbox(
    params: ConnectionParams,
    runner: Runner = run_queries,
    *,
    executor: SandboxExecutor = DEFAULT_SANDBOX_EXECUTOR,
    mode: SandboxMode = SandboxMode.SCHEMA_ONLY,
    schema_names: frozenset[str] = frozenset(),
    baseline: DatabaseSchema | BaselineSnapshot | None = None,
    target_params: ConnectionParams | None = None,
) -> SandboxSession:
    """Probe `params`, check ownership, and return a `SandboxSession` --
    **the only gate** (§18.5 D2). Raises `ForeignDatabaseError` if the
    connected database is not app-owned. Everything that writes goes
    through the returned session; nothing else in the codebase re-checks
    ownership and no write path bypasses the session. Reads (probe,
    listing, introspecting the target for a baseline) are not gated.

    `mode`/`schema_names`/`baseline`/`target_params` are recorded onto the
    returned session for `reset()` to use later -- callers that already
    know these (e.g. `provision_sandbox`, or re-opening a previously
    provisioned sandbox whose `ProjectSettings` recorded its mode) pass them
    through; a caller that only wants to read/apply without ever calling
    `reset()` may omit them.
    """
    caps = probe(params, runner=runner)
    if not is_app_owned(caps.database, caps.owner_marker):
        raise ForeignDatabaseError(caps.database)
    return SandboxSession(
        params=params,
        mode=mode,
        schema_names=schema_names,
        baseline=baseline,
        target_params=target_params,
        executor=executor,
    )


def purge_orphaned_alter_rows(session: SandboxSession) -> None:
    """Delete the pre-BUG-044 alter bookkeeping rows -- **once, at session
    open** (DEC-008). Idempotent: after the first run there is nothing to
    delete, and a sandbox that never held such a row deletes nothing.

    Ensures the bookkeeping table exists first (the same
    `CREATE ... IF NOT EXISTS` statements `provision_sandbox` runs, so this
    creates nothing new and changes no row) purely so the DELETE cannot fail on
    a sandbox that has not been provisioned yet.

    See `_DELETE_ORPHANED_ALTER_ROWS_SQL` for why the predicate is provably
    incapable of touching an object row, and why the orphans are worthless
    rather than merely stale.
    """
    session.executor.execute(
        session.params,
        [*_CREATE_BOOKKEEPING_SQL, _DELETE_ORPHANED_ALTER_ROWS_SQL],
    )


def provision_sandbox(
    schema: DatabaseSchema | BaselineSnapshot,
    sandbox_params: ConnectionParams,
    mode: SandboxMode = SandboxMode.SCHEMA_ONLY,
    *,
    target_params: ConnectionParams | None = None,
    runner: Runner = run_queries,
    executor: SandboxExecutor = DEFAULT_SANDBOX_EXECUTOR,
) -> SandboxSession:
    """Provision a fresh, already-`create_sandbox_database`-created sandbox
    from `schema` and return a working `SandboxSession` (§18.5 D2).

    Composes the rest of the module rather than duplicating it: calls
    `open_sandbox` (the ownership gate), builds the baseline DDL via
    `build_baseline_sql` and executes it through the session's executor,
    ensures the `pgtp_editor_sandbox.applied` bookkeeping table exists, and
    -- when `mode is SandboxMode.WITH_DATA` -- invokes the existing
    `clone_data()` (requiring `target_params`) **instead of** the baseline
    DDL, matching D2a's "the two are alternative provisioning strategies for
    the same one-time setup step, never both run in sequence."

    The returned session remembers its `mode`/schema set/baseline/
    `target_params` so a later `reset()` needs no further input.
    """
    inner_schema = schema.schema if isinstance(schema, BaselineSnapshot) else schema
    schema_names = _collect_schema_names(inner_schema)

    session = open_sandbox(
        sandbox_params,
        runner=runner,
        executor=executor,
        mode=mode,
        schema_names=frozenset(schema_names),
        baseline=schema,
        target_params=target_params,
    )

    if mode is SandboxMode.WITH_DATA:
        if target_params is None:
            raise ValueError("provision_sandbox(mode=WITH_DATA) requires target_params")
        clone_data(target_params, sandbox_params)
    else:
        statements = build_baseline_sql(schema)
        if statements:
            session.executor.execute(session.params, statements)

    session.executor.execute(session.params, list(_CREATE_BOOKKEEPING_SQL))
    return session


# ---------------------------------------------------------------------------
# One-click plpgsql_check install (§18.5 D2)
# ---------------------------------------------------------------------------

_INSTALL_PLPGSQL_CHECK_SQL = "CREATE EXTENSION IF NOT EXISTS plpgsql_check"

#: The four exact reason strings `install_gate` returns, verbatim from §18.5
#: D2 -- matched closely because the UI shows them as-is.
_REASON_ALREADY_INSTALLED = "already installed."
#: Public: `install_gate` only hands this out when the extension is
#: `installable`, but a UI host needs the same sentence to explain a
#: superuser-blocked install it detected itself. Exported so the wording lives
#: in exactly one place rather than being re-typed at the call site.
REASON_REQUIRES_SUPERUSER = (
    "CREATE EXTENSION requires superuser; ask your DBA, or connect the "
    "sandbox profile as a superuser."
)
_REASON_REQUIRES_SUPERUSER = REASON_REQUIRES_SUPERUSER
_REASON_ABSENT = (
    "plpgsql_check is not available on this server -- it must be installed "
    "as a C library on disk by a database administrator before PGTP Editor "
    "can enable it."
)
_REASON_COULD_NOT_PROBE = "could not probe the server."


def install_gate(caps: SandboxCapabilities) -> tuple[bool, str]:
    """Pure gate deciding whether to offer the one-click `plpgsql_check`
    install button (§18.5 D2): offered (`True`) only when
    `caps.plpgsql_check_state == "installable"` **and** `caps.is_superuser`.

    Otherwise returns `(False, reason)` with the exact reason string the UI
    shows verbatim:
    - `"already installed."` when already installed.
    - the `CREATE EXTENSION`-requires-superuser text when installable but
      not a superuser.
    - the platform-install text when genuinely `absent` (a C library on
      disk the app cannot fix).
    - `"could not probe the server."` when the state is `unknown` (a failed
      probe).
    """
    state = caps.plpgsql_check_state
    if state == "installed":
        return False, _REASON_ALREADY_INSTALLED
    if state == "installable":
        if caps.is_superuser:
            return True, ""
        return False, _REASON_REQUIRES_SUPERUSER
    if state == "absent":
        return False, _REASON_ABSENT
    return False, _REASON_COULD_NOT_PROBE


def install_plpgsql_check(session: SandboxSession) -> None:
    """Run `CREATE EXTENSION IF NOT EXISTS plpgsql_check` (§18.5 D2).

    Reachable **only through a `SandboxSession`** -- which by construction
    (via `open_sandbox`'s ownership gate) means the database is app-owned.
    There is no free function that runs this against an arbitrary
    `ConnectionParams`, by design.
    """
    session.executor.execute(session.params, [_INSTALL_PLPGSQL_CHECK_SQL])


# ---------------------------------------------------------------------------
# Backend interface (§18.5 D2: "so a managed or bundled server can be added
# later (§29) without the choice leaking into the UI")
# ---------------------------------------------------------------------------
class PostgresBackend(Protocol):
    """Qt-free protocol both today's `LocalPostgresBackend` and any future
    managed/bundled backend implement identically, so the UI never branches
    on which one is in play (§18.5 D2)."""

    def ensure_running(self) -> ConnectionParams:
        """Return a usable DSN/`ConnectionParams` for the sandbox, starting
        the server if this backend owns one."""
        ...

    def capabilities(self) -> SandboxCapabilities:
        """Delegates to `probe` (the full field list) and caches. The
        ladder's tier availability is derived only from this -- never from
        a bare `try: ... except: assume absent`."""
        ...


@dataclass
class LocalPostgresBackend:
    """v1's only `PostgresBackend`: bring-your-own local PostgreSQL (§18.5
    D2). `ensure_running()` is a no-op that returns the already-configured
    profile and fails loudly (raises) if it cannot connect at all -- this
    backend does not own/start any server process. `capabilities()`
    delegates to and caches `probe`.
    """

    params: ConnectionParams
    runner: Runner = run_queries
    which: Which = shutil.which
    _cached_capabilities: SandboxCapabilities | None = field(default=None, init=False, repr=False)

    def ensure_running(self) -> ConnectionParams:
        """No-op for v1's bring-your-own backend -- fails loudly (raises
        `ConnectionError`) if the configured profile cannot be reached at
        all, rather than silently returning params that don't work."""
        caps = probe(self.params, runner=self.runner, which=self.which)
        if caps.probe_error is not None:
            raise ConnectionError(
                f"could not connect to the configured local Postgres sandbox: {caps.probe_error}"
            )
        return self.params

    def capabilities(self) -> SandboxCapabilities:
        if self._cached_capabilities is None:
            self._cached_capabilities = probe(self.params, runner=self.runner, which=self.which)
        return self._cached_capabilities
