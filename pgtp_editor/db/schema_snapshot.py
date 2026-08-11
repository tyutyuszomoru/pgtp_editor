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

# pgtp_editor/db/schema_snapshot.py
"""Round-trip a `DatabaseSchema` through git-committable JSON (§18.3).

`db/schema_diff.py::diff_schemas` compares two `DatabaseSchema` values, and
until now both had to come from a live introspection — so "does production
match the schema we agreed on?" could only ever be asked DB-to-DB, against
whatever a second server happened to contain at that moment. This module makes
one side of that comparison a **file**: dump a schema, commit the JSON, and the
committed file becomes the versioned desired state.

Two properties make that usable, and both are load-bearing rather than polish:

* **Determinism.** Same schema in, byte-identical text out — same rationale as
  `migration_gen`'s: the artifact lives in git, so an unchanged schema must
  produce a zero-line diff. Mapping keys are sorted; *sequence* fields are NOT
  (see `_encode_table`) because their order is semantic.
* **Refuse, never degrade.** A truncated, hand-edited or foreign JSON file
  raises `SnapshotFormatError`; an unrecognized format marker raises
  `UnsupportedSnapshotVersion`. Neither ever yields a half-populated
  `DatabaseSchema`, because a schema that silently lost its routines would diff
  as "everything was removed" and `generate_migration` would hand the user a
  script of DROPs. That is the one genuinely dangerous failure mode here, so
  loading validates every key and every type and rejects unknown keys outright.

Nothing here connects to a database or executes DDL (§18.3's hard non-goal); the
output is data for review. **No connection identity is recorded at all** — not
host, not user, not a `connection_summary`, and obviously not a password — since
the file is destined for a repository. Which server a snapshot came from is the
caller's metadata to keep elsewhere.

Pure but for `read_snapshot`/`write_snapshot`: `dump_schema`/`load_schema` are
text-in/text-out and carry the whole contract, so the serialization is testable
without a filesystem.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    ConstraintInfo,
    IndexInfo,
    TableInfo,
    TriggerInfo,
    TypeInfo,
)

#: Marker identifying the payload as *this* project's schema snapshot, so a
#: foreign JSON file of the right general shape is refused rather than parsed.
SNAPSHOT_FORMAT = "pgtp-editor.schema-snapshot"

#: Bumped only on an incompatible payload change. `load_schema` refuses any
#: other value instead of guessing, which is what lets a future version add or
#: rename fields without old code misreading a newer file as a schema that
#: happens to be missing things.
#:
#: **2 (FQ-025):** `DatabaseSchema` gained `constraints` and `indexes`, so the
#: payload gained two sections. A v1 file is REFUSED rather than loaded with
#: those sections empty — this module's whole posture is refuse-never-degrade,
#: and "loaded, but every constraint is missing" is precisely the shape that
#: makes `diff_schemas` hand the user a script of DROPs. Costless in practice:
#: `Save Schema Snapshot…` has never been built, so no snapshot can exist that
#: was written by the app.
#:
#: **3 (2026-08-09):** `TableInfo` gained `comment` (the table's own
#: `pg_description` row, so `Set Table Comment…` can seed the existing text
#: instead of blanking it). This is a weaker change than 1→2's — one optional
#: field on one record, not two whole sections — but the version still moves,
#: for two reasons. First, `_record`/`_exact_keys` demand an EXACT key set, so
#: a v2 table record would be refused anyway; the only question is *which*
#: refusal the user reads, and "your reader is the wrong version" is true and
#: actionable where "this file is truncated or hand-edited" is neither.
#: Second, silently accepting a missing `comment` (the only alternative that
#: would not move the version) would default it to `None` — i.e. load a schema
#: asserting "no table has a comment", which is precisely the degraded state
#: this module refuses to produce. Costless for the same reason as before:
#: `Save Schema Snapshot…` has never been built, so no app-written snapshot of
#: any version exists in the wild.
#:
#: **4 (2026-08-11, `DEC-260811022536`):** `ColumnInfo` gained `identity` and
#: `generated`, so the synthesized `CREATE TABLE` can render
#: `GENERATED ... AS IDENTITY` and `GENERATED ALWAYS AS (<expr>) STORED` instead
#: of omitting them. Same reasoning as 3 in every respect, and the degraded
#: reading is even louder here: a v3 column record accepted with the two fields
#: defaulted would assert **"no column in this schema is an identity or
#: generated column"** — about a schema whose surrogate keys are exactly what a
#: diff would then propose to rewrite.
SNAPSHOT_VERSION = 4

# The exact field set each record carries, in the dataclasses' own order. Used
# twice: to build the payload, and to reject a record whose keys do not match
# *exactly* (missing key -> truncated/hand-edited file; extra key -> foreign or
# newer file). `tests/db/test_schema_snapshot.py` asserts these against
# `dataclasses.fields`, so a field added to `introspect.py` cannot be silently
# dropped from snapshots.
COLUMN_FIELDS = (
    "name",
    "data_type",
    "is_pk",
    "is_fk",
    "is_nullable",
    "default",
    "fk_target",
    "comment",
    "identity",
    "generated",
)
TABLE_FIELDS = ("name", "kind", "columns", "view_definition", "comment")
ROUTINE_FIELDS = (
    "schema",
    "name",
    "arg_types",
    "return_type",
    "language",
    "source",
    "kind",
    "args",
)
TRIGGER_FIELDS = ("schema", "table", "name", "timing", "events", "function_name",
                  "definition")
TYPE_FIELDS = ("schema", "name", "kind", "base_type", "not_null", "attributes")
CONSTRAINT_FIELDS = (
    "schema",
    "table",
    "name",
    "kind",
    "columns",
    "definition",
)
INDEX_FIELDS = (
    "schema",
    "table",
    "name",
    "columns",
    "is_unique",
    "is_primary",
    "method",
    "definition",
    "constraint_name",
)
SCHEMA_SECTIONS = ("tables", "routines", "triggers", "types", "constraints", "indexes")
_PAYLOAD_KEYS = ("format", "version", "schema")


class SnapshotError(Exception):
    """Base for every refusal in this module — never raised directly."""


class SnapshotFormatError(SnapshotError):
    """The text is not a valid snapshot of the current version.

    Malformed JSON, a missing or extra key, a value of the wrong type, a
    non-string mapping key. Same posture as `migration_gen.UnsupportedDifference`
    and `ddl_skeleton.SkeletonError`: the caller renders the refusal and no
    partial `DatabaseSchema` is produced.
    """


class UnsupportedSnapshotVersion(SnapshotError):
    """The payload announces a `version` this build does not understand.

    Distinct from `SnapshotFormatError` because the recovery differs: the file
    is intact, the *reader* is too old (or too new). Guessing at it is exactly
    how a version skew turns into a destructive migration.
    """


# --- dumping ----------------------------------------------------------------


def dump_schema(schema: DatabaseSchema) -> str:
    """Serialize `schema` to deterministic, diffable JSON text.

    Two-space indented, mapping keys sorted, one trailing newline — a text file
    a reviewer can read in a pull request. Two dumps of equal schemas are
    byte-identical regardless of the insertion order of the source dicts.
    """
    payload = {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "schema": {
            "tables": {key: _encode_table(value) for key, value in schema.tables.items()},
            "routines": {
                key: _encode_routine(value) for key, value in schema.routines.items()
            },
            "triggers": {
                key: _encode_trigger(value) for key, value in schema.triggers.items()
            },
            "types": {key: _encode_type(value) for key, value in schema.types.items()},
            "constraints": {
                key: _encode_constraint(value)
                for key, value in schema.constraints.items()
            },
            "indexes": {
                key: _encode_index(value) for key, value in schema.indexes.items()
            },
        },
    }
    # sort_keys reaches every nested mapping, which is what makes the output
    # independent of dict insertion order; ensure_ascii=False keeps comments and
    # routine bodies readable in the committed file rather than \uXXXX escapes.
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_snapshot(schema: DatabaseSchema, path: str | Path) -> Path:
    """Write `dump_schema(schema)` to `path` as UTF-8 with LF newlines.

    `newline="\\n"` is explicit: the file is compared byte-for-byte in git, so
    it must not pick up CRLF from the platform the snapshot happened to be
    taken on (development happens on both Windows and Linux).
    """
    target = Path(path)
    target.write_text(dump_schema(schema), encoding="utf-8", newline="\n")
    return target


def _encode_table(table: TableInfo) -> dict[str, Any]:
    # `columns` keeps introspection order (attnum) -- it is the table's column
    # order, so sorting it here would destroy real information and make a
    # reordered table compare equal to the original. Same for `arg_types`/`args`
    # (a routine's argument order is its identity) and `events`. Only *mapping*
    # keys are sorted.
    return {
        "name": table.name,
        "kind": table.kind,
        "columns": [_encode_column(column) for column in table.columns],
        "view_definition": table.view_definition,
        "comment": table.comment,
    }


def _encode_column(column: ColumnInfo) -> dict[str, Any]:
    return {name: getattr(column, name) for name in COLUMN_FIELDS}


def _encode_routine(routine: RoutineInfo) -> dict[str, Any]:
    return {
        "schema": routine.schema,
        "name": routine.name,
        "arg_types": list(routine.arg_types),
        "return_type": routine.return_type,
        "language": routine.language,
        "source": routine.source,
        "kind": routine.kind,
        # (name, type) tuples become 2-element arrays: JSON has no tuple, and
        # `_decode_routine` restores the tuple so the frozen dataclass compares
        # equal to the original (a list would not).
        "args": [[arg_name, arg_type] for arg_name, arg_type in routine.args],
    }


def _encode_trigger(trigger: TriggerInfo) -> dict[str, Any]:
    return {
        "schema": trigger.schema,
        "table": trigger.table,
        "name": trigger.name,
        "timing": trigger.timing,
        "events": list(trigger.events),
        "function_name": trigger.function_name,
        "definition": trigger.definition,
    }


def _encode_constraint(constraint: ConstraintInfo) -> dict[str, Any]:
    return {
        "schema": constraint.schema,
        "table": constraint.table,
        "name": constraint.name,
        "kind": constraint.kind,
        "columns": list(constraint.columns),
        "definition": constraint.definition,
    }


def _encode_index(index: IndexInfo) -> dict[str, Any]:
    return {
        "schema": index.schema,
        "table": index.table,
        "name": index.name,
        "columns": list(index.columns),
        "is_unique": index.is_unique,
        "is_primary": index.is_primary,
        "method": index.method,
        "definition": index.definition,
        "constraint_name": index.constraint_name,
    }


def _encode_type(type_info: TypeInfo) -> dict[str, Any]:
    return {
        "schema": type_info.schema,
        "name": type_info.name,
        "kind": type_info.kind,
        "base_type": type_info.base_type,
        "not_null": type_info.not_null,
        "attributes": [[attr_name, attr_type] for attr_name, attr_type in
                       type_info.attributes],
    }


# --- loading ----------------------------------------------------------------


def load_schema(text: str) -> DatabaseSchema:
    """Parse snapshot `text` back into an equal `DatabaseSchema`.

    `load_schema(dump_schema(s)) == s` for every field of every record, which is
    what makes a snapshot safe to `diff_schemas` against a live schema.

    Raises `SnapshotFormatError` for anything that is not a well-formed snapshot
    of this version, and `UnsupportedSnapshotVersion` for a payload announcing a
    different `version`. It never returns a partially populated schema — see the
    module docstring for why that matters more here than anywhere else.
    """
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SnapshotFormatError(f"snapshot is not valid JSON: {exc}") from exc

    payload = _mapping(payload, "snapshot")
    _exact_keys(payload, _PAYLOAD_KEYS, "snapshot")

    if payload["format"] != SNAPSHOT_FORMAT:
        raise SnapshotFormatError(
            f"not a PGTP Editor schema snapshot: format is {payload['format']!r}, "
            f"expected {SNAPSHOT_FORMAT!r}"
        )
    # `True` is an `int` in Python, so the bool is excluded explicitly rather
    # than letting `{"version": true}` read as version 1.
    version = payload["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise SnapshotFormatError(
            f"snapshot version must be an integer, got {type(version).__name__}"
        )
    if version != SNAPSHOT_VERSION:
        raise UnsupportedSnapshotVersion(
            f"snapshot format version {version} is not supported by this build "
            f"(expected {SNAPSHOT_VERSION}); refusing to guess at its contents"
        )

    body = _mapping(payload["schema"], "snapshot.schema")
    _exact_keys(body, SCHEMA_SECTIONS, "snapshot.schema")
    return DatabaseSchema(
        tables=_decode_section(body["tables"], "tables", _decode_table),
        routines=_decode_section(body["routines"], "routines", _decode_routine),
        triggers=_decode_section(body["triggers"], "triggers", _decode_trigger),
        types=_decode_section(body["types"], "types", _decode_type),
        constraints=_decode_section(
            body["constraints"], "constraints", _decode_constraint
        ),
        indexes=_decode_section(body["indexes"], "indexes", _decode_index),
    )


def read_snapshot(path: str | Path) -> DatabaseSchema:
    """`load_schema` the UTF-8 text at `path`.

    A missing or unreadable file raises `SnapshotFormatError` too: from the
    caller's point of view "this snapshot cannot be trusted" is one outcome with
    one recovery, and letting an `OSError` through would invite a bare
    `except SnapshotError` to miss it.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SnapshotFormatError(f"cannot read snapshot {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise SnapshotFormatError(f"snapshot {path} is not UTF-8 text: {exc}") from exc
    return load_schema(text)


def _decode_section(section: Any, name: str, decode) -> dict:
    mapping = _mapping(section, f"snapshot.schema.{name}")
    decoded = {}
    for key, value in mapping.items():
        # JSON object keys are always strings, but a caller may hand
        # `load_schema` a dict-derived payload; keys are the DatabaseSchema
        # mapping keys and are preserved verbatim (never recomputed from the
        # record) so the round trip is exact.
        if not isinstance(key, str):
            raise SnapshotFormatError(
                f"snapshot.schema.{name} key must be a string, got "
                f"{type(key).__name__}"
            )
        decoded[key] = decode(value, f"snapshot.schema.{name}[{key!r}]")
    return decoded


def _decode_table(value: Any, where: str) -> TableInfo:
    record = _record(value, TABLE_FIELDS, where)
    columns = _sequence(record["columns"], f"{where}.columns")
    return TableInfo(
        name=_text(record["name"], f"{where}.name"),
        kind=_text(record["kind"], f"{where}.kind"),
        columns=[
            _decode_column(column, f"{where}.columns[{index}]")
            for index, column in enumerate(columns)
        ],
        view_definition=_opt_text(record["view_definition"], f"{where}.view_definition"),
        comment=_opt_text(record["comment"], f"{where}.comment"),
    )


def _decode_column(value: Any, where: str) -> ColumnInfo:
    record = _record(value, COLUMN_FIELDS, where)
    return ColumnInfo(
        name=_text(record["name"], f"{where}.name"),
        data_type=_text(record["data_type"], f"{where}.data_type"),
        is_pk=_flag(record["is_pk"], f"{where}.is_pk"),
        is_fk=_flag(record["is_fk"], f"{where}.is_fk"),
        is_nullable=_flag(record["is_nullable"], f"{where}.is_nullable"),
        default=_opt_text(record["default"], f"{where}.default"),
        fk_target=_opt_text(record["fk_target"], f"{where}.fk_target"),
        comment=_opt_text(record["comment"], f"{where}.comment"),
        identity=_opt_text(record["identity"], f"{where}.identity"),
        generated=_opt_text(record["generated"], f"{where}.generated"),
    )


def _decode_routine(value: Any, where: str) -> RoutineInfo:
    record = _record(value, ROUTINE_FIELDS, where)
    return RoutineInfo(
        schema=_text(record["schema"], f"{where}.schema"),
        name=_text(record["name"], f"{where}.name"),
        arg_types=_text_list(record["arg_types"], f"{where}.arg_types"),
        return_type=_opt_text(record["return_type"], f"{where}.return_type"),
        language=_text(record["language"], f"{where}.language"),
        source=_text(record["source"], f"{where}.source"),
        kind=_text(record["kind"], f"{where}.kind"),
        args=_pair_list(record["args"], f"{where}.args"),
    )


def _decode_trigger(value: Any, where: str) -> TriggerInfo:
    record = _record(value, TRIGGER_FIELDS, where)
    return TriggerInfo(
        schema=_text(record["schema"], f"{where}.schema"),
        table=_text(record["table"], f"{where}.table"),
        name=_text(record["name"], f"{where}.name"),
        timing=_text(record["timing"], f"{where}.timing"),
        events=_text_list(record["events"], f"{where}.events"),
        function_name=_text(record["function_name"], f"{where}.function_name"),
        definition=_text(record["definition"], f"{where}.definition"),
    )


def _decode_constraint(value: Any, where: str) -> ConstraintInfo:
    record = _record(value, CONSTRAINT_FIELDS, where)
    return ConstraintInfo(
        schema=_text(record["schema"], f"{where}.schema"),
        table=_text(record["table"], f"{where}.table"),
        name=_text(record["name"], f"{where}.name"),
        kind=_text(record["kind"], f"{where}.kind"),
        columns=_text_list(record["columns"], f"{where}.columns"),
        definition=_text(record["definition"], f"{where}.definition"),
    )


def _decode_index(value: Any, where: str) -> IndexInfo:
    record = _record(value, INDEX_FIELDS, where)
    return IndexInfo(
        schema=_text(record["schema"], f"{where}.schema"),
        table=_text(record["table"], f"{where}.table"),
        name=_text(record["name"], f"{where}.name"),
        columns=_text_list(record["columns"], f"{where}.columns"),
        is_unique=_flag(record["is_unique"], f"{where}.is_unique"),
        is_primary=_flag(record["is_primary"], f"{where}.is_primary"),
        method=_text(record["method"], f"{where}.method"),
        definition=_text(record["definition"], f"{where}.definition"),
        constraint_name=_opt_text(
            record["constraint_name"], f"{where}.constraint_name"
        ),
    )


def _decode_type(value: Any, where: str) -> TypeInfo:
    record = _record(value, TYPE_FIELDS, where)
    return TypeInfo(
        schema=_text(record["schema"], f"{where}.schema"),
        name=_text(record["name"], f"{where}.name"),
        kind=_text(record["kind"], f"{where}.kind"),
        base_type=_opt_text(record["base_type"], f"{where}.base_type"),
        not_null=_flag(record["not_null"], f"{where}.not_null"),
        attributes=_pair_list(record["attributes"], f"{where}.attributes"),
    )


# --- validation primitives --------------------------------------------------
#
# Every one of these raises rather than coercing. A snapshot that "mostly"
# loaded is worse than one that did not load at all.


def _mapping(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise SnapshotFormatError(
            f"{where} must be a JSON object, got {type(value).__name__}"
        )
    return value


def _sequence(value: Any, where: str) -> list:
    if not isinstance(value, list):
        raise SnapshotFormatError(
            f"{where} must be a JSON array, got {type(value).__name__}"
        )
    return value


def _exact_keys(mapping: dict, expected: tuple[str, ...], where: str) -> None:
    """Require exactly `expected` — no missing key, no extra one.

    Missing means truncated or hand-edited (and defaulting it would fabricate
    schema). Extra means a foreign or newer file that slipped past the version
    check, which is likewise something to say out loud rather than ignore.
    """
    present = set(mapping)
    missing = sorted(set(expected) - present)
    unknown = sorted(present - set(expected))
    if missing:
        raise SnapshotFormatError(
            f"{where} is missing required key(s): {', '.join(missing)}"
        )
    if unknown:
        raise SnapshotFormatError(
            f"{where} has unrecognized key(s): {', '.join(unknown)}"
        )


def _record(value: Any, expected: tuple[str, ...], where: str) -> dict:
    record = _mapping(value, where)
    _exact_keys(record, expected, where)
    return record


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise SnapshotFormatError(
            f"{where} must be a string, got {type(value).__name__}"
        )
    return value


def _opt_text(value: Any, where: str) -> str | None:
    return None if value is None else _text(value, where)


def _flag(value: Any, where: str) -> bool:
    # Not `bool(value)`: a `1` or `"false"` in a hand-edited file is a mistake
    # worth surfacing, and `bool("false")` is True.
    if not isinstance(value, bool):
        raise SnapshotFormatError(
            f"{where} must be true or false, got {type(value).__name__}"
        )
    return value


def _text_list(value: Any, where: str) -> list[str]:
    items = _sequence(value, where)
    return [_text(item, f"{where}[{index}]") for index, item in enumerate(items)]


def _pair_list(value: Any, where: str) -> list[tuple[str, str]]:
    """`[[name, type], ...]` -> `[(name, type), ...]`.

    The tuple is not cosmetic: `RoutineInfo`/`TypeInfo` are frozen dataclasses
    compared by value, and `[("a", "int")] != [["a", "int"]]`, so a loaded
    snapshot carrying lists here would never compare equal to the schema it was
    dumped from.
    """
    items = _sequence(value, where)
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(items):
        pair = _sequence(item, f"{where}[{index}]")
        if len(pair) != 2:
            raise SnapshotFormatError(
                f"{where}[{index}] must be a [name, type] pair, got "
                f"{len(pair)} element(s)"
            )
        pairs.append(
            (
                _text(pair[0], f"{where}[{index}][0]"),
                _text(pair[1], f"{where}[{index}][1]"),
            )
        )
    return pairs
