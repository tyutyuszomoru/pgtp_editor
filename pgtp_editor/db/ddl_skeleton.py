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
(FQ-002) — and `ALTER TABLE` statements for column operations on existing
tables (FQ-025 slice 1) — the starting text the DDL Explorer's dialogs paste
into a fresh editor tab.

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

FQ-025 slice 1 adds the column operations (`add_column_skeleton` and friends).
They obey every rule above and add two fields that are *inherently* free SQL
text — a `USING` expression for a type change and a `DEFAULT` expression — for
which the allowlist posture is impossible by construction. See
`_expression` for exactly what is and is not guaranteed about those.
"""
from __future__ import annotations

import re

# `_sql_string_literal` is imported rather than re-implemented so the app has
# exactly ONE place that knows how a SQL string literal is quoted -- the same
# reason every identifier goes through the one `quote_ident`.
from .sandbox import _sql_string_literal, quote_ident

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


# ---------------------------------------------------------------------------
# FQ-025 slice 1 -- column operations on an EXISTING table
#
# Every function below takes `table` (optionally `schema.table`) and `column`
# explicitly: "which table / which column" is never inferred from ambient
# state, so the dialog layer must state it and the emitted text can always be
# read back against the click context that produced it.
#
# All return a single `str`, like every skeleton above, because the product is
# text for an editable tab -- not a statement list for a driver. The one
# operation that needs two statements (Add column *with a comment*: a column
# comment is `COMMENT ON COLUMN`, which `ALTER TABLE` has no clause for) still
# returns one string containing both statements, each terminated by `;\n`.
# `build_baseline_sql`'s list-of-statements shape is the wrong analogue here:
# that list is fed to a driver, this text is fed to a human.
# ---------------------------------------------------------------------------
def add_column_skeleton(
    *,
    table: str,
    column: str,
    datatype: str,
    nullable: bool = True,
    comment: str | None = None,
) -> str:
    """`ALTER TABLE … ADD COLUMN`, plus `COMMENT ON COLUMN` when `comment` is
    given (two statements in one returned string — see the module note above).

    `nullable=False` emits `NOT NULL`; note that on a table that already has
    rows this only succeeds if a default is supplied or the table is empty.
    That is Postgres's rule to report, not this emitter's to pre-empt: the text
    lands in an editor and running it is a separate, explicit gesture.

    `comment` is a *value*, not an identifier, so it is emitted as a SQL string
    literal via `sandbox._sql_string_literal` (embedded `'` doubled) rather
    than allowlisted — the same treatment the sandbox owner-marker comment
    gets. An empty/blank comment is treated as "no comment" and emits no second
    statement at all, rather than an `IS ''` that means something different.
    """
    quoted_table = _qualified(table, "table")
    quoted_column = _identifier(column, "column name")
    column_type = _column_datatype(datatype)

    null_clause = "" if nullable else " NOT NULL"
    statement = (
        f"ALTER TABLE {quoted_table} "
        f"ADD COLUMN {quoted_column} {column_type}{null_clause};\n"
    )
    if comment is None or not comment.strip():
        return statement
    return statement + _comment_on_column(quoted_table, quoted_column, comment)


def drop_column_skeleton(*, table: str, column: str) -> str:
    """`ALTER TABLE … DROP COLUMN`.

    No `CASCADE`: dropping a column that a view or constraint depends on will
    fail loudly, which is the safer default for generated DDL. A user who
    genuinely wants the cascade types the word in the editor tab — an
    irreversible widening should be a deliberate keystroke, not a checkbox
    default.
    """
    quoted_table = _qualified(table, "table")
    quoted_column = _identifier(column, "column name")
    return f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_column};\n"


def rename_column_skeleton(*, table: str, column: str, new_name: str) -> str:
    """`ALTER TABLE … RENAME COLUMN … TO …`.

    Renaming a column to its current name is a Postgres error, so it is
    refused here rather than emitted — a no-op statement that fails on run is
    exactly the "looks authoritative, then breaks" outcome this module avoids.
    """
    quoted_table = _qualified(table, "table")
    quoted_column = _identifier(column, "column name")
    quoted_new = _identifier(new_name, "new column name")
    if quoted_column == quoted_new:
        raise SkeletonError(
            f"new column name is the same as the current one: {column!r}"
        )
    return (
        f"ALTER TABLE {quoted_table} "
        f"RENAME COLUMN {quoted_column} TO {quoted_new};\n"
    )


def alter_column_type_skeleton(
    *,
    table: str,
    column: str,
    datatype: str,
    using: str | None = None,
) -> str:
    """`ALTER TABLE … ALTER COLUMN … TYPE …`, with an optional `USING` clause.

    `USING` is load-bearing rather than decorative: Postgres will only change a
    column's type without one when an assignment cast exists, so a `text` →
    `integer` change on real data fails outright unless the caller supplies
    e.g. `USING trim(code)::integer`.

    **How the free text is handled, and what remains risky.** A `USING`
    expression is arbitrary SQL by definition — it can call functions, cast,
    and reference other columns — so it *cannot* be allowlisted the way an
    identifier or a datatype is, and this module does not pretend otherwise.
    It is emitted verbatim after three checks that are about the *statement
    staying one statement*, not about the expression's meaning:

    - it must be non-blank if supplied (an empty `USING` is a syntax error);
    - its single quotes must be balanced and its parentheses must nest and
      close — an unterminated literal would otherwise swallow every following
      statement in the returned text into a string;
    - it must contain no SQL comment introducer (`--` or `/*`) outside a
      string literal — a trailing `--` would comment out the terminating `;`
      and silently fuse this statement with the next.

    The residual risk is real and deliberate: an expression like
    `1); DROP TABLE t; --` is caught by the checks above, but a *legitimately
    shaped* expression that calls a destructive function is not, and cannot be.
    The mitigation is architectural, not lexical — the text is generated into
    an editable tab, nothing here executes anything, and running it is the
    separate explicit §18.5 Apply gesture. The dialog layer must therefore only
    ever populate `using` from the user's own typed input; it must never pass
    through a value that originated in a database, a file, or a .pgtp project.
    """
    quoted_table = _qualified(table, "table")
    quoted_column = _identifier(column, "column name")
    column_type = _column_datatype(datatype)

    clause = ""
    if using is not None:
        clause = f" USING {_expression(using, 'USING clause')}"
    return (
        f"ALTER TABLE {quoted_table} "
        f"ALTER COLUMN {quoted_column} TYPE {column_type}{clause};\n"
    )


def set_column_not_null_skeleton(*, table: str, column: str) -> str:
    """`ALTER TABLE … ALTER COLUMN … SET NOT NULL`."""
    return _alter_column(table, column, "SET NOT NULL")


def drop_column_not_null_skeleton(*, table: str, column: str) -> str:
    """`ALTER TABLE … ALTER COLUMN … DROP NOT NULL`.

    A separate function from `set_column_not_null_skeleton` rather than one
    function with a boolean: the two are different operations in the menu, and
    a boolean argument at a call site (`not_null=False`) reads as a modifier
    when it is in fact the choice of statement.
    """
    return _alter_column(table, column, "DROP NOT NULL")


def set_column_default_skeleton(*, table: str, column: str, expression: str) -> str:
    """`ALTER TABLE … ALTER COLUMN … SET DEFAULT <expression>`.

    `expression` is free SQL text (`0`, `now()`, `'pending'::text`) and is
    validated exactly like `alter_column_type_skeleton`'s `USING` clause — read
    that docstring for what is and is not guaranteed. It is required: a blank
    default is not "no default", it is a syntax error, and the operation that
    removes a default is `drop_column_default_skeleton`.
    """
    return _alter_column(
        table,
        column,
        f"SET DEFAULT {_expression(expression, 'default expression')}",
    )


def drop_column_default_skeleton(*, table: str, column: str) -> str:
    """`ALTER TABLE … ALTER COLUMN … DROP DEFAULT`."""
    return _alter_column(table, column, "DROP DEFAULT")


def _alter_column(table: str, column: str, action: str) -> str:
    """The shared `ALTER TABLE t ALTER COLUMN c <action>;` shape.

    `action` is never caller-supplied text — every call site above passes a
    literal, or a fragment whose only free part already went through
    `_expression`.
    """
    quoted_table = _qualified(table, "table")
    quoted_column = _identifier(column, "column name")
    return f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} {action};\n"


def _comment_on_column(quoted_table: str, quoted_column: str, comment: str) -> str:
    if "\x00" in comment:
        raise SkeletonError(f"comment contains a NUL character: {comment!r}")
    return (
        f"COMMENT ON COLUMN {quoted_table}.{quoted_column} "
        f"IS {_sql_string_literal(comment)};\n"
    )


def _column_datatype(datatype: str) -> str:
    """`_datatype` with a column-shaped error message.

    Shares the one `_SAFE_DATATYPE_RE` allowlist with the function return type
    -- `character varying(255)`, `numeric(10,2)` and `integer[]` are the same
    grammar in both places, and a second, looser pattern for columns would be a
    second thing to get wrong.
    """
    if not datatype or not datatype.strip():
        raise SkeletonError("a column needs a datatype")
    stripped = datatype.strip()
    if not _SAFE_DATATYPE_RE.match(stripped):
        raise SkeletonError(f"unsafe or malformed datatype: {datatype!r}")
    return stripped


def _expression(text: str, what: str) -> str:
    """Validate a free-text SQL expression as far as it *can* be validated.

    See `alter_column_type_skeleton` for the full argument. In short: the
    expression's meaning is not checkable, but its ability to break out of the
    statement it sits in is. This refuses anything that would leave the
    returned text malformed -- an unbalanced quote or paren, or a comment
    introducer that could eat the terminating semicolon -- so the module's
    "never a partial return" promise still holds: what comes back is one
    well-formed statement or an exception.
    """
    if not text or not text.strip():
        raise SkeletonError(f"{what} must not be empty")
    expression = text.strip()

    if any(ch in expression for ch in ("\x00", "\r")):
        raise SkeletonError(f"{what} contains a control character: {text!r}")

    in_string = False
    depth = 0
    index = 0
    length = len(expression)
    while index < length:
        char = expression[index]
        if in_string:
            if char == "'":
                # A doubled '' is an escaped quote inside the literal, not the
                # end of it.
                if index + 1 < length and expression[index + 1] == "'":
                    index += 2
                    continue
                in_string = False
            index += 1
            continue
        if char == "'":
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise SkeletonError(f"{what} has unbalanced parentheses: {text!r}")
        elif expression.startswith("--", index) or expression.startswith("/*", index):
            raise SkeletonError(
                f"{what} must not contain a SQL comment -- it would comment out "
                f"the rest of the statement: {text!r}"
            )
        index += 1

    if in_string:
        raise SkeletonError(f"{what} has an unterminated string literal: {text!r}")
    if depth:
        raise SkeletonError(f"{what} has unbalanced parentheses: {text!r}")
    return expression


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
