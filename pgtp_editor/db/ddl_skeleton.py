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

# pgtp_editor/db/ddl_skeleton.py
"""Render `CREATE` skeletons for brand-new triggers, functions and procedures
(FQ-002) — the starting text the DDL Explorer's creation dialogs paste into a
fresh editor tab.

Pure: no Qt, no psycopg, no I/O, no clock. Output is deterministic — identical
input yields byte-identical output — so the tests are plain golden strings.

**Nothing here executes SQL.** The result is text the user edits and then
applies through the normal §18.5 Apply / §18.3 Deploy paths, which is why a
skeleton must be *valid as emitted*: it lands in an editor a user may run
unchanged apart from filling in the body.

Two correctness rules this module exists to enforce, both easy to get wrong by
hand and both covered by tests:

- **`CREATE PROCEDURE` has no `RETURNS` clause.** Postgres procedures return
  nothing (they use `OUT` parameters); a return type is not merely optional for
  them, it is a syntax error. `procedure_skeleton` therefore takes no return
  type at all rather than accepting and ignoring one.
- **`RETURN NULL;` is invalid in a `void` function** ("RETURN cannot have a
  parameter in function returning void"). The generated body drops the
  `RETURN` for `void` instead of emitting a stub that fails on first run.

Identifiers follow the codebase's established **validated, not sanitized**
posture: they go through `sandbox.quote_ident`, which double-quotes a name only
after it passes a strict allowlist and otherwise raises `UnsafeIdentifierError`
— arbitrary content is never escaped into the output. Mixed case survives
correctly (`MyFunc` → `"MyFunc"`); a name with a space or an embedded quote is
refused, not mangled.
"""
from __future__ import annotations

import re

from .sandbox import quote_ident

#: Trigger firing time. `INSTEAD OF` is view-only in Postgres; that is the
#: caller's constraint to enforce, not this emitter's.
TRIGGER_TIMINGS = ("BEFORE", "AFTER", "INSTEAD OF")

#: Canonical event order. Emission always follows THIS order regardless of the
#: order the caller passes, so a dialog backed by an unordered set of checkbox
#: states still produces stable, diffable text.
TRIGGER_EVENTS = ("INSERT", "UPDATE", "DELETE")

#: Row- vs statement-level. Postgres has no transaction-level trigger — the
#: original FQ-002 request said "for each transaction" and was corrected.
TRIGGER_LEVELS = ("FOR EACH ROW", "FOR EACH STATEMENT")

_INDENT = "    "

# A datatype is NOT an identifier -- `character varying(255)`, `numeric(10,2)`
# and `integer[]` are all legitimate and none would survive `quote_ident`. It
# is also the one field a dialog can carry free text in, so it gets its own
# allowlist rather than being interpolated raw: letters, digits, underscores,
# spaces, dots (schema-qualified domains), parens/commas (precision) and square
# brackets (arrays). Quotes, semicolons and dollar signs are refused, which is
# what keeps a return type from closing the statement or the `$$` body.
_SAFE_DATATYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ .,()\[\]]*$")


class SkeletonError(ValueError):
    """Raised for input a valid skeleton cannot be built from.

    Refuse-don't-degrade, matching `migration_gen.UnsupportedDifference`: the
    caller renders the refusal and no half-formed SQL reaches the editor, where
    it would look authoritative and get run.
    """


def trigger_skeleton(
    *,
    name: str,
    table: str,
    timing: str,
    events: "list[str] | tuple[str, ...] | set[str]",
    level: str,
    function_name: str,
) -> str:
    """`CREATE TRIGGER` naming an **existing** trigger function.

    `table` may be schema-qualified (`public.orders`); each part is quoted
    separately so the dot stays a separator rather than becoming part of the
    name. `events` is combined with ` OR ` in `TRIGGER_EVENTS` order.
    """
    quoted_name = _identifier(name, "trigger name")
    quoted_table = _qualified(table, "table")
    quoted_function = _qualified(function_name, "trigger function")

    if timing not in TRIGGER_TIMINGS:
        raise SkeletonError(
            f"timing must be one of {', '.join(TRIGGER_TIMINGS)} — got {timing!r}"
        )
    if level not in TRIGGER_LEVELS:
        raise SkeletonError(
            f"level must be one of {', '.join(TRIGGER_LEVELS)} — got {level!r}"
        )

    unknown = [event for event in events if event not in TRIGGER_EVENTS]
    if unknown:
        raise SkeletonError(
            f"unknown trigger event(s): {', '.join(sorted(unknown))} — "
            f"expected any of {', '.join(TRIGGER_EVENTS)}"
        )
    # Canonical order, and de-duplicated: `INSERT OR INSERT` is a syntax error.
    ordered = [event for event in TRIGGER_EVENTS if event in set(events)]
    if not ordered:
        raise SkeletonError("a trigger needs at least one event")

    return (
        f"CREATE TRIGGER {quoted_name}\n"
        f"{timing} {' OR '.join(ordered)} ON {quoted_table}\n"
        f"{level}\n"
        f"EXECUTE FUNCTION {quoted_function}();\n"
    )


def function_skeleton(*, name: str, return_type: str) -> str:
    """`CREATE OR REPLACE FUNCTION` with a `LANGUAGE plpgsql` body stub.

    v1 takes no parameter list and no language choice — this is a plpgsql IDE,
    and the user fills in the signature in the editor.
    """
    quoted_name = _qualified(name, "function name")
    datatype = _datatype(return_type)

    return (
        f"CREATE OR REPLACE FUNCTION {quoted_name}()\n"
        f"RETURNS {datatype}\n"
        f"LANGUAGE plpgsql\n"
        f"AS $$\n"
        f"BEGIN\n"
        f"{_body_stub(datatype)}"
        f"END;\n"
        f"$$;\n"
    )


def procedure_skeleton(*, name: str) -> str:
    """`CREATE OR REPLACE PROCEDURE` — deliberately **no** `RETURNS` clause.

    Takes no return type by construction: a procedure that returned something
    would not be a procedure. Procedures arrived in PG 11 and
    `CREATE OR REPLACE PROCEDURE` has been valid for as long as they have, so
    the `OR REPLACE` costs no compatibility.
    """
    quoted_name = _qualified(name, "procedure name")

    return (
        f"CREATE OR REPLACE PROCEDURE {quoted_name}()\n"
        f"LANGUAGE plpgsql\n"
        f"AS $$\n"
        f"BEGIN\n"
        f"{_INDENT}-- TODO: implement\n"
        f"END;\n"
        f"$$;\n"
    )


def _body_stub(datatype: str) -> str:
    # `RETURN NULL;` is a runtime error in a void function, so a void stub is
    # the comment alone -- a plpgsql block whose body is only a comment is
    # valid, and a skeleton that fails the moment it is run is worse than one
    # that does nothing.
    if datatype.strip().lower() == "void":
        return f"{_INDENT}-- TODO: implement\n"
    return f"{_INDENT}-- TODO: implement\n{_INDENT}RETURN NULL;\n"


def _identifier(name: str, what: str) -> str:
    if not name or not name.strip():
        raise SkeletonError(f"{what} must not be empty")
    return quote_ident(name)


def _qualified(name: str, what: str) -> str:
    """Quote a possibly `schema.object` name, part by part."""
    if not name or not name.strip():
        raise SkeletonError(f"{what} must not be empty")
    parts = name.split(".")
    if any(not part for part in parts):
        raise SkeletonError(f"{what} has an empty name part: {name!r}")
    return ".".join(quote_ident(part) for part in parts)


def _datatype(return_type: str) -> str:
    if not return_type or not return_type.strip():
        raise SkeletonError("a function needs a return type")
    datatype = return_type.strip()
    if not _SAFE_DATATYPE_RE.match(datatype):
        raise SkeletonError(f"unsafe or malformed return type: {return_type!r}")
    return datatype
