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
"""The sandbox capability probe (§18.5 D2).

**Scope of this module today: the capability probe only.** `SandboxCapabilities`
and `probe()` are the whole of what's implemented -- the accumulating
`SandboxSession`, baseline provisioning (`build_baseline_sql`), the one-click
`plpgsql_check` install, and the ownership-by-naming-convention guard remain
target design (§18.5 D2/D3), not built yet.

This slice exists now because §18.2's **New Project** dialog reuses it as-is
for its local-sandbox **Test** button, whose specific job is verifying the
connected user is a **superuser** (`CREATE EXTENSION` requires it) -- not
merely "can connect". The spec is explicit that this must be *the same*
probe the later sandbox lane uses, not a second ad hoc superuser check.

Qt-free and, like `db/introspect.py`, opens no connection except through the
injectable `runner` seam -- the whole test suite runs with psycopg absent.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import ConnectionParams
from .introspect import Runner, run_queries

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


def probe(params: ConnectionParams, runner: Runner = run_queries) -> SandboxCapabilities:
    """Probe a Postgres connection's capabilities in one round trip.

    **Never raises** -- any failure (unreachable host, bad credentials, a
    server too old to know one of the settings queried) becomes
    `probe_error`, mirroring `db/introspect.py::test_connection`'s
    never-raises contract.
    """
    try:
        rows = runner(params, PROBE_SQL)
        version_rows, superuser_rows, installed_rows, available_rows, db_rows = rows
        server_version = _decode_server_version(str(version_rows[0][0]))
        is_superuser = str(superuser_rows[0][0]).strip().lower() in ("on", "true", "t", "1")
        installed_extensions = frozenset(row[0] for row in installed_rows)
        available_extensions = frozenset(row[0] for row in available_rows)
        database, owner_marker = db_rows[0]
    except Exception as exc:  # noqa: BLE001 -- surface any failure as probe_error
        return SandboxCapabilities(probe_error=str(exc))
    return SandboxCapabilities(
        server_version=server_version,
        is_superuser=is_superuser,
        installed_extensions=installed_extensions,
        available_extensions=available_extensions,
        database=database,
        owner_marker=owner_marker,
        probe_error=None,
    )
