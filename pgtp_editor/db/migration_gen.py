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

# pgtp_editor/db/migration_gen.py
"""Emit *routine and trigger* migration SQL — NOT table or column migrations.

Read that first line again before extending this module (R18): despite the
name, `generate_migration` covers exactly two of §18.3's four `object_kind`s.
A `table` or `column` difference raises `UnsupportedDifference` — it is never
silently dropped from the script, because a migration that quietly omits
table changes is precisely the silent-wrong-result class this project refuses.

Pure: no Qt, no psycopg, no I/O, no clock. Output is deterministic — identical
input yields byte-identical output — which is what makes the tests plain
golden strings and the generated file diffable in git. Anything time- or
connection-dependent (generated-at stamp, server versions, which content model
produced the run) is the caller's, passed in via `header=`.

Nothing here executes SQL. The result is text for the user to review and save
(§18.3's hard non-goal: this never auto-executes DDL against a live database).
"""
from __future__ import annotations

from collections.abc import Iterable

from .schema_diff import SchemaDifference

_SUPPORTED_OBJECT_KINDS = ("routine", "trigger")
_KINDS = ("added", "removed", "changed")

# Routines before triggers: `CREATE TRIGGER` resolves its function immediately
# (`pg_trigger.tgfoid` is a hard catalog reference), so this rank is a real
# constraint, not cosmetics. Within a group, alphabetical by identity --
# stable, dependency-free and testable. PL/pgSQL bodies are not resolved at
# CREATE time, so forward references between them need no ordering at all;
# `LANGUAGE sql` routines are the exception, and they get the header warning
# below rather than a topological sort. (Deliberately NOT using
# `plpgsql_show_dependency_tb`: it only covers plpgsql routines -- precisely
# the ones that do not need ordering -- and would make the deliverable depend
# on an optional, superuser-gated C extension.)
_OBJECT_KIND_RANK = {"routine": 0, "trigger": 1}

_NOTE = (
    "-- NOTE: table and column changes are NOT included in this script; it covers\n"
    "--       routine and trigger changes only (CONSOLIDATED_SPEC.md 18.3)."
)

_REVIEW = (
    "-- REVIEW: {identity} is absent from the source schema. The DROP below is\n"
    "--         commented out deliberately -- an object missing from the source far\n"
    "--         more likely means it was never touched than that it should be\n"
    "--         removed. Uncomment it only if you mean to drop it."
)


class UnsupportedDifference(Exception):
    """A difference this emitter refuses to handle rather than skip.

    Raised for `object_kind` outside routine/trigger — today that is §18.3's
    `table`/`column`, which this module does not implement. The caller renders
    the refusal; no partial script is produced.
    """


def connection_summary(params) -> str:
    """`user@host:port/database` for the header block — never the password.

    Same discipline as `debuglog.redacted`: the password field is not rendered
    at all, so it cannot leak into a file the user commits or emails. Duck-typed
    on `ConnectionParams` (host/port/database/user) so this module stays free of
    the Qt-importing `db.config`.
    """
    return f"{params.user}@{params.host}:{params.port}/{params.database}"


def generate_migration(differences: Iterable[SchemaDifference], *, header: str = "") -> str:
    """Render `differences` as one reviewable migration script (§18.3).

    Order is §18.3's CREATE→ALTER→guarded-DROP with only the first and last
    populated: header block, then `added`/`changed` routines, then
    `added`/`changed` triggers (each `DROP TRIGGER IF EXISTS` + create), then
    `removed` objects as **commented-out** DROPs. Every statement ends in `;`
    and blocks are blank-line separated, so the text pastes into `psql`
    unedited.

    `header` is free text supplied by the caller (connection summaries, server
    versions, generated-at); each line is comment-prefixed. Build the
    connection lines with `connection_summary` so no password can appear.
    """
    differences = list(differences)
    _reject_unsupported(differences)

    emitted = sorted(
        (d for d in differences if d.kind in ("added", "changed")), key=_sort_key
    )
    removed = sorted((d for d in differences if d.kind == "removed"), key=_sort_key)

    blocks = [_header_block(header, emitted)]
    for difference in emitted:
        if difference.object_kind == "trigger":
            # No portable `CREATE OR REPLACE TRIGGER` below PG 14; the
            # drop-then-create pair is idempotent on every supported major and
            # simpler than branching on the target's version.
            blocks.append(f"{_drop_trigger(difference.identity)};")
        blocks.append(_terminated(difference.new_def))
    for difference in removed:
        blocks.append(_review_block(difference))

    return "\n\n".join(blocks) + "\n"


def _reject_unsupported(differences: list[SchemaDifference]) -> None:
    # Checked up front, before a single line is rendered: the caller gets a
    # refusal, never a script with the unsupported half quietly missing.
    for difference in differences:
        if difference.object_kind not in _SUPPORTED_OBJECT_KINDS:
            raise UnsupportedDifference(
                f"{difference.object_kind} differences are not supported by "
                f"migration_gen (offending object: {difference.identity}); this "
                "module generates routine and trigger migrations only"
            )
        if difference.kind not in _KINDS:
            raise ValueError(
                f"unknown difference kind {difference.kind!r} for {difference.identity}"
            )


def _sort_key(difference: SchemaDifference) -> tuple[int, str]:
    return (_OBJECT_KIND_RANK[difference.object_kind], difference.identity)


def _header_block(header: str, emitted: list[SchemaDifference]) -> str:
    lines = [f"-- {line}".rstrip() for line in header.splitlines()]
    lines.append(_NOTE)

    non_plpgsql = sum(
        1
        for difference in emitted
        if difference.object_kind == "routine"
        and difference.language
        and difference.language.lower() != "plpgsql"
    )
    if non_plpgsql:
        lines.append(
            f"-- WARNING: {non_plpgsql} non-PL/pgSQL routine(s) are included; statement "
            "order may need\n"
            "--          manual adjustment (their bodies are resolved at CREATE time)."
        )
    return "\n".join(lines)


def _drop_trigger(identity: str) -> str:
    # identity is "schema.table.name"; the trigger name is the last segment.
    # Names are emitted unquoted, exactly as introspected -- a mixed-case
    # trigger name would make the CREATE fail loudly ("already exists"), never
    # silently do the wrong thing.
    qualified_table, _, name = identity.rpartition(".")
    return f"DROP TRIGGER IF EXISTS {name} ON {qualified_table}"


def _terminated(definition: str | None) -> str:
    # `pg_get_functiondef`/`pg_get_triggerdef` do not include the terminator.
    text = (definition or "").rstrip()
    return text if text.endswith(";") else f"{text};"


def _review_block(difference: SchemaDifference) -> str:
    if difference.object_kind == "trigger":
        drop = _drop_trigger(difference.identity)
    else:
        # DROP ROUTINE (PG 11+) covers both functions and procedures; the
        # difference record does not distinguish them, and guessing FUNCTION
        # for a procedure would put wrong text in front of the reviewer.
        drop = f"DROP ROUTINE {difference.identity}"
    return _REVIEW.format(identity=difference.identity) + f"\n-- {drop};"
