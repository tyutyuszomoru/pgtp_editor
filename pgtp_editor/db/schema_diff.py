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

# pgtp_editor/db/schema_diff.py
"""Diff two `DatabaseSchema` objects into `SchemaDifference` records.

**Routines and triggers only.** Tables and columns are deliberately *not*
compared; every table seen on either side is reported in the result's
`unsupported` list so a caller can say "table and column changes are not
compared" rather than presenting a table-blind diff as a complete one
(§18.3 fills the table/column cases in later).

Mirrors `diff/differ.py::diff_project`'s contract shape — a flat list of
records, `kind ∈ added|removed|changed` — but keyed on DB objects rather than
XML nodes. Pure: no Qt, no psycopg, no I/O, no runner. `source` is the desired
state (e.g. the sandbox), `target` is the current state (e.g. production), so
`added` means "present in the desired state, missing from the current one".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Annotations only -- guarded so this module stays genuinely Qt-free at
    # runtime. `db/introspect.py` imports `db/config.py`, which imports
    # `QSettings` at module scope, so an unguarded import silently dragged
    # PySide6 into the deployment engine and made this docstring's "Pure: no
    # Qt" claim false. `routine_identity` reaches `RoutineInfo.signature` by
    # attribute access on the passed object, which needs no runtime import.
    from .introspect import DatabaseSchema, RoutineInfo, TriggerInfo


@dataclass(frozen=True)
class SchemaDifference:
    """One DB-object-level difference (§18.3's record, verbatim).

    The first five fields are §18.3's contract and must not be renamed — the
    full engine will populate this same type for `table`/`column` too.
    `language` is a sibling carried for the emitter's benefit: it drives
    `migration_gen`'s non-PL/pgSQL ordering warning. It is the routine's
    language (source side when present, else target side) and is `""` for
    triggers.
    """

    kind: str  # "added" | "removed" | "changed"
    object_kind: str  # "table" | "column" | "routine" | "trigger"
    identity: str
    old_def: str | None
    new_def: str | None
    language: str = ""


class SchemaDiffResult(list):
    """§18.3's `list[SchemaDifference]`, carrying the not-compared sidecar.

    A `list` subclass rather than a wrapper so `diff_schemas`' return value
    still *is* the list §18.3 specifies (it compares equal to `[]`, iterates
    and indexes normally), while `unsupported` travels with it instead of
    needing a second call the UI could forget to make.

    **Read `.unsupported` at the call site, before transforming the list.**
    The operations that build a new container are overridden below to carry
    the sidecar forward (slicing, `+`, `.copy()`), but two very ordinary ones
    *cannot* be:

    * a list comprehension — `[d for d in result if ...]`
    * `sorted(result)` / `list(result)` / `reversed()`

    Both always construct a plain `list`, by language rule, and the sidecar is
    gone with no error and no warning. Losing it means a UI reports a diff as
    complete when table and column changes were never compared — the exact
    silent-wrong-result this module refuses. So: capture `unsupported` first,
    filter second.
    """

    def __init__(self, differences=(), unsupported=()):
        super().__init__(differences)
        #: Names of objects this diff did NOT compare (tables, today).
        self.unsupported: list[str] = list(unsupported)

    def _derive(self, differences) -> SchemaDiffResult:
        return SchemaDiffResult(differences, self.unsupported)

    def __getitem__(self, index):
        item = super().__getitem__(index)
        # A slice of a partial diff is still a partial diff.
        return self._derive(item) if isinstance(index, slice) else item

    def __add__(self, other) -> SchemaDiffResult:
        # Merging two results unions their unsupported names; concatenating a
        # plain list keeps this one's.
        return SchemaDiffResult(
            list(self) + list(other), _merge_unsupported(self, other)
        )

    def __radd__(self, other) -> SchemaDiffResult:
        # Reached for `plain_list + result`: Python tries the subclass's
        # reflected operator first, so the sidecar survives either operand
        # order. Merging two results unions their unsupported names.
        merged = _merge_unsupported(other, self)
        return SchemaDiffResult(list(other) + list(self), merged)

    def copy(self) -> SchemaDiffResult:
        return self._derive(list(self))


def _merge_unsupported(*results) -> list[str]:
    names: set[str] = set()
    for result in results:
        names.update(getattr(result, "unsupported", ()))
    return sorted(names)


def routine_identity(routine: RoutineInfo) -> str:
    """`schema.name(argtype, argtype)` — the *full signature*.

    PostgreSQL identifies a function by `(schema, name, argument types)`, so
    this is the only correct identity: `schema.name` alone would collapse two
    overloads into one and would make an argument-type change look like a
    `changed` routine. A bare `CREATE OR REPLACE` for that "change" creates a
    *second* function and leaves the old one live, silently breaking every
    existing caller (R14). Never degrade this to `schema.name`.

    Delegates to `RoutineInfo.signature`, which is the one implementation of
    this string (BUG-018) -- shared with the `DatabaseSchema.routines` dict key
    and `db/ddl_buffer.py`'s banner comment. This function keeps its name and
    its place because §18.3 names it and the migration generator imports it.
    """
    return routine.signature


def trigger_identity(trigger: TriggerInfo) -> str:
    """`schema.table.name` — trigger names are unique only per table."""
    return f"{trigger.schema}.{trigger.table}.{trigger.name}"


def _by_identity(objects, identity_of) -> dict:
    # Keyed off the object's own fields, never off the DatabaseSchema dict
    # key. `fetch_routines_and_triggers` now keys routines by the full
    # signature (BUG-018), but a schema handed to the diff can come from
    # anywhere, so the identity is still recomputed from the object rather
    # than trusted from the mapping.
    return {identity_of(obj): obj for obj in objects}


def diff_schemas(source: DatabaseSchema, target: DatabaseSchema) -> SchemaDiffResult:
    """Compare desired `source` against current `target` (§18.3's signature).

    Returns routine differences first, then trigger differences, each group
    sorted by identity, so the result is deterministic for a given input.
    `changed` is exact text comparison of `RoutineInfo.source` /
    `TriggerInfo.definition`; both sides come from `pg_get_functiondef` /
    `pg_get_triggerdef`, so formatting is server-normalized and a
    cosmetic-only diff is impossible within one server version (across two
    server majors it is not — R16).

    The returned `SchemaDiffResult` is a `list[SchemaDifference]` (§18.3's
    signature) plus a `.unsupported` sidecar naming the tables that were *not*
    compared. **Read `.unsupported` here, at the call site, before filtering
    or sorting** — a list comprehension or `sorted()` produces a plain `list`
    and drops it silently, which would let a UI present a table-blind diff as
    a complete one. See `SchemaDiffResult` for which operations do carry it.
    """
    differences: list[SchemaDifference] = []
    differences.extend(
        _diff_group(
            _by_identity(source.routines.values(), routine_identity),
            _by_identity(target.routines.values(), routine_identity),
            object_kind="routine",
            definition_of=lambda routine: routine.source,
            language_of=lambda routine: routine.language,
        )
    )
    differences.extend(
        _diff_group(
            _by_identity(source.triggers.values(), trigger_identity),
            _by_identity(target.triggers.values(), trigger_identity),
            object_kind="trigger",
            definition_of=lambda trigger: trigger.definition,
            language_of=lambda _trigger: "",
        )
    )
    # Tables are skipped, not compared -- and said so out loud.
    unsupported = sorted(set(source.tables) | set(target.tables))
    return SchemaDiffResult(differences, unsupported)


def _diff_group(
    source_objects: dict,
    target_objects: dict,
    *,
    object_kind: str,
    definition_of,
    language_of,
) -> list[SchemaDifference]:
    differences: list[SchemaDifference] = []
    for identity in sorted(set(source_objects) | set(target_objects)):
        source_object = source_objects.get(identity)
        target_object = target_objects.get(identity)
        old_def = None if target_object is None else definition_of(target_object)
        new_def = None if source_object is None else definition_of(source_object)
        language = language_of(source_object if source_object is not None else target_object)

        if target_object is None:
            kind = "added"
        elif source_object is None:
            kind = "removed"
        elif old_def == new_def:
            continue
        else:
            kind = "changed"

        differences.append(
            SchemaDifference(
                kind=kind,
                object_kind=object_kind,
                identity=identity,
                old_def=old_def,
                new_def=new_def,
                language=language,
            )
        )
    return differences
