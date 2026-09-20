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

# pgtp_editor/db/pg_dump_mode.py
"""The dual-mode DDL verdict (FQ-260812022749 Part 1): is there a
correctly-versioned `pg_dump` on this machine, and therefore does the DDL
buffer show the **full** `pg_dump` view or today's **restricted** synthesized
DDL?

**This module owns the RULE and the WORDS, and nothing else.** It does not
render DDL, does not touch the buffer, and imports no Qt -- exactly like
`db/table_ddl.py` and `db/ddl_buffer.py`. Binary *resolution* and the
`pg_dump --version` *spawn* stay in `db/sandbox.py` (the module that already
owns `DATA_CLONE_TOOLS`, the `Which`/`ProcessRunner` seams and `_pg_env`);
this module composes them.

**The version rule, in one sentence: `pg_dump` major >= server major.**
`pg_dump` dumps happily from an *older* server and **refuses a server newer
than itself** (`aborting because of server version mismatch`), so
newer-than-server is fine and is NOT a mismatch. One comparison, and by owner
ruling (2026-08-12) there is **one version rule, not two**: quality and
sandbox must be the same PostgreSQL major, so the same `pg_dump`-vs-server
comparison answers for both Explorer roles. See `server_major_divergence` for
the check that rule was never given.

**Degrade, never guess.** Every failure shape -- binary absent, `--version`
unreadable, server version unknown -- lands in `RESTRICTED` mode with a
message that says which shape it was. There is no path from this module to a
hard failure: the fallback is what keeps a packaged install (which never
bundles the client tools) working at all.

**Every message names BOTH version numbers**, because a version message that
omits one of the two is the one that generates the support question.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum

from .sandbox import (
    PG_DUMP_VERSION_TIMEOUT_S,
    ProcessRunner,
    SandboxCapabilities,
    Which,
    pg_dump_version,
    resolve_tool,
)


class DdlMode(str, Enum):
    """Which renderer the DDL buffer uses (owner ruling, 2026-08-12)."""

    #: A correctly-versioned `pg_dump` is present: the buffer is its output.
    FULL = "full"
    #: Anything else: today's synthesized, catalog-reconstructed DDL.
    RESTRICTED = "restricted"


#: Why the verdict came out the way it did. Machine-readable beside the
#: human `message`, so a caller can branch (or a test assert) without
#: pattern-matching prose.
REASON_OK = "ok"
REASON_ABSENT = "absent"
REASON_OLDER = "older"
REASON_UNREADABLE = "unreadable"
REASON_UNKNOWN_SERVER = "unknown_server"

#: Appended to every RESTRICTED message. Restricted DDL is not merely
#: "incomplete" -- Part 5 settled that the complete DDL is a **clone source**,
#: so a developer who clones a partitioned or inherited table from restricted
#: text gets a plain table that looks right and executes fine. That is a
#: silent wrong result reaching a real database, which is why the warning is
#: part of the sentence rather than a footnote somewhere else.
RESTRICTED_CLONE_WARNING = (
    "Showing DDL reconstructed from pg_catalog — incomplete for inheritance "
    "and partitioning; do not clone a partitioned or inherited table from "
    "this text."
)


def _major(version: tuple[int, ...] | None) -> int | None:
    return version[0] if version else None


def _spell(version: tuple[int, ...] | None) -> str:
    """`(16, 2)` -> `"16.2"`, `()`/None -> `"unknown"`. Used for both numbers
    in every message, so the two are always spelled the same way."""
    if not version:
        return "unknown"
    return ".".join(str(part) for part in version)


@dataclass(frozen=True)
class DdlModeVerdict:
    """One probe's answer: the mode, why, both version numbers, and the
    sentence the `[DDL]` row shows.

    **Computed once, on connecting to the quality server** (owner ruling), and
    then reported on **every** DDL open from this cached value -- the notice
    repeats on purpose (*"this way the choice is clear"*), but the
    `pg_dump --version` spawn does not.
    """

    mode: DdlMode
    reason: str
    server_version: tuple[int, ...]
    pg_dump_path: str | None
    pg_dump_version: tuple[int, ...] | None
    #: The `[DDL]` row's text WITHOUT its prefix. The prefix's one home is
    #: `ui/audit_router.py::DDL_PREFIX`; this module stays Qt-free and does
    #: not re-spell it.
    message: str

    @property
    def full(self) -> bool:
        return self.mode is DdlMode.FULL


def decide_ddl_mode(
    server_version: tuple[int, ...],
    pg_dump_path: str | None,
    pg_dump_version_found: tuple[int, ...] | None,
) -> DdlModeVerdict:
    """The whole rule, as a **pure function** -- no I/O, no subprocess, no
    server. Every branch is testable from three plain values, which is the
    same posture that makes `table_ddl.py` testable.

    The four shapes, and their verdicts:

    ==========================  ==========  ============================
    Shape                       Mode        Detected by
    ==========================  ==========  ============================
    `pg_dump` not located       RESTRICTED  `pg_dump_path is None`
    located, version unreadable RESTRICTED  version is None
    server version unknown      RESTRICTED  `server_version` empty
    `pg_dump` major < server    RESTRICTED  the one comparison
    otherwise (incl. NEWER)     FULL        --
    ==========================  ==========  ============================
    """
    server_text = _spell(server_version)
    dump_text = _spell(pg_dump_version_found)

    if pg_dump_path is None:
        return DdlModeVerdict(
            mode=DdlMode.RESTRICTED,
            reason=REASON_ABSENT,
            server_version=server_version,
            pg_dump_path=None,
            pg_dump_version=None,
            message=(
                f"Restricted DDL — pg_dump was not found on PATH or in the "
                f"configured PostgreSQL binaries folder (pg_dump version "
                f"{dump_text}, server {server_text}). {RESTRICTED_CLONE_WARNING}"
            ),
        )

    if pg_dump_version_found is None:
        return DdlModeVerdict(
            mode=DdlMode.RESTRICTED,
            reason=REASON_UNREADABLE,
            server_version=server_version,
            pg_dump_path=pg_dump_path,
            pg_dump_version=None,
            message=(
                f"Restricted DDL — pg_dump was found at {pg_dump_path} but its "
                f"version could not be read (pg_dump version {dump_text}, "
                f"server {server_text}). {RESTRICTED_CLONE_WARNING}"
            ),
        )

    server_major = _major(server_version)
    if server_major is None:
        return DdlModeVerdict(
            mode=DdlMode.RESTRICTED,
            reason=REASON_UNKNOWN_SERVER,
            server_version=server_version,
            pg_dump_path=pg_dump_path,
            pg_dump_version=pg_dump_version_found,
            message=(
                f"Restricted DDL — the server version is unknown, so pg_dump "
                f"{dump_text} cannot be version-checked against it (pg_dump "
                f"version {dump_text}, server {server_text}). "
                f"{RESTRICTED_CLONE_WARNING}"
            ),
        )

    dump_major = _major(pg_dump_version_found)
    if dump_major is not None and dump_major < server_major:
        return DdlModeVerdict(
            mode=DdlMode.RESTRICTED,
            reason=REASON_OLDER,
            server_version=server_version,
            pg_dump_path=pg_dump_path,
            pg_dump_version=pg_dump_version_found,
            message=(
                f"Restricted DDL — pg_dump {dump_text} is older than server "
                f"{server_text}; pg_dump would refuse this server. "
                f"{RESTRICTED_CLONE_WARNING}"
            ),
        )

    return DdlModeVerdict(
        mode=DdlMode.FULL,
        reason=REASON_OK,
        server_version=server_version,
        pg_dump_path=pg_dump_path,
        pg_dump_version=pg_dump_version_found,
        message=f"Full DDL via pg_dump {dump_text} (server {server_text}).",
    )


def probe_ddl_mode(
    caps: SandboxCapabilities,
    *,
    bin_dir: str | None = None,
    which: Which = shutil.which,
    run: ProcessRunner = subprocess.run,
    timeout: int = PG_DUMP_VERSION_TIMEOUT_S,
) -> DdlModeVerdict:
    """Compose `db/sandbox.py`'s resolution and version seams into one
    verdict, from a `SandboxCapabilities` the caller already has in hand.

    **Never raises.** `resolve_tool` does not raise and `pg_dump_version`
    swallows every subprocess failure into None, so the worst case is a
    RESTRICTED verdict that says why -- which is the whole point of the
    fallback.

    `caps.pg_dump_path` is deliberately NOT trusted as the resolution here:
    it may have been probed before the project's binaries folder was set (or
    with a different one), and one stale path is how a "which one is right?"
    bug is manufactured. Resolution is re-run against the `bin_dir` in force
    now; the DB round trip is not.
    """
    pg_dump_path = resolve_tool("pg_dump", bin_dir=bin_dir, which=which)
    version = pg_dump_version(pg_dump_path, run, timeout=timeout)
    return decide_ddl_mode(caps.server_version, pg_dump_path, version)


# ---------------------------------------------------------------------------
# The one version rule applied ACROSS the two servers (owner, 2026-08-12)
# ---------------------------------------------------------------------------

def server_major_divergence(
    quality_version: tuple[int, ...],
    sandbox_version: tuple[int, ...],
) -> str | None:
    """The quality-vs-sandbox major comparison the owner's *"the two databases
    must be the same version"* principle requires -- and which **nothing in
    this app performed before this function existed**.

    Verified at the time of writing: `server_version` was produced only by
    `db/sandbox.py::probe` and consumed only by
    `db/ddl_check.py::needs_trigger_drop` (gating `CREATE OR REPLACE TRIGGER`
    at PG 14). The sameness rule was therefore **assumed, never enforced and
    never even checked** -- and §18.5 D2's sandbox is explicitly
    bring-your-own local PostgreSQL, so its major is whatever the user
    installed.

    Returns the sentence to report, or None when the two agree (or when
    either is unknown -- an unknown version is "could not check", which must
    never be reported the same way as a genuine divergence).
    """
    quality_major = _major(quality_version)
    sandbox_major = _major(sandbox_version)
    if quality_major is None or sandbox_major is None:
        return None
    if quality_major == sandbox_major:
        return None
    return (
        f"Quality server is PostgreSQL {_spell(quality_version)} but the "
        f"sandbox is PostgreSQL {_spell(sandbox_version)} — they must be the "
        "same major version. Sandbox results are not trustworthy until they "
        "match."
    )
