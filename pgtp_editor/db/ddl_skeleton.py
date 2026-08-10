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

FQ-025 slice 2 adds the constraint operations (`add_constraint_skeleton`,
`add_foreign_key_skeleton`, `drop_constraint_skeleton`,
`rename_constraint_skeleton`). Two module-level facts they exist to encode:

- **A foreign key *is* a constraint.** `ALTER TABLE … DROP CONSTRAINT name` is
  byte-identical for a FK, a CHECK and a primary key, so there is exactly ONE
  drop emitter and no `drop_foreign_key_skeleton` — a second function would be
  the same statement under a name that implies otherwise.
- **A `CHECK` body is free SQL, like `USING`.** It goes through the very same
  `_expression` guard and inherits the same rule: the dialog layer may fill it
  from the user's own typing and from nothing else.

FQ-025 slice 3 adds the index, comment and whole-table operations
(`create_index_skeleton`, `drop_index_skeleton`, `set_table_comment_skeleton`,
`set_column_comment_skeleton`, `create_table_skeleton`,
`drop_table_skeleton`). Three module-level facts they exist to encode:

- **An index is not an `ALTER TABLE`.** `CREATE INDEX` and `DROP INDEX` are
  their own statements, so they do not go through `_alter_column`, and
  `DROP INDEX` does not take a table at all — an index name is unique within
  its *schema*, so `schema.index_name` (not `schema.table.index_name`) is its
  identity, exactly as `introspect.IndexInfo.qualified_name` spells it.
  Conversely a `CREATE INDEX`'s own name is **bare**, never schema-qualified:
  the index is created in its table's schema and a dotted name there is a
  syntax error, which is why it goes through `_identifier` and not
  `_qualified`.
- **A comment is a VALUE, not an identifier.** `COMMENT ON … IS 'x'` takes a
  SQL string literal, so an apostrophe in ordinary English prose is *escaped*
  (doubled) rather than refused — the opposite of every identifier here. All
  four call sites share the one `_comment_on` renderer.
- **Removing a comment is `IS NULL`, and that is what blank means.** For the
  two dedicated comment operations an empty comment box is the *only* way to
  say "take the comment off", so it emits `IS NULL` rather than nothing.
  (`add_column_skeleton` predates them and keeps its own rule — there, blank
  means "this Add-column statement carries no comment clause at all", so no
  second statement is emitted.)
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

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


# ---------------------------------------------------------------------------
# FQ-025 slice 2 -- constraints and foreign keys on an EXISTING table
#
# Four emitters, not five: `drop_constraint_skeleton` covers foreign keys too
# (see the module docstring). Like slice 1 they take `table` explicitly, return
# one statement as a `str`, and never return anything partial.
#
# The constraint NAME is required by every one of them, including the two
# `ADD`s, even though Postgres would happily auto-name an unnamed constraint.
# An auto-generated name (`orders_qty_check1`) is exactly what makes the drop
# and rename dialogs a guessing game later; requiring the name here means every
# constraint this app creates can be found again by the person who created it.
# ---------------------------------------------------------------------------

#: The types the ONE `Add constraint` dialog offers. `FOREIGN KEY` is
#: deliberately absent: it needs a referenced table and column list, which is a
#: different form, so it gets `add_foreign_key_skeleton` instead.
CONSTRAINT_TYPES = ("PRIMARY KEY", "UNIQUE", "CHECK", "EXCLUDE")

#: Types whose definition is a **column list** (`PRIMARY KEY ("a", "b")`).
COLUMN_CONSTRAINT_TYPES = ("PRIMARY KEY", "UNIQUE")

#: Types whose definition is a free **expression**, not a column list. `CHECK
#: (qty > 0)` is obvious; `EXCLUDE` is here because its element list carries a
#: per-element operator (`room WITH =, during WITH &&`) that a column picker
#: cannot express — pretending otherwise would emit `EXCLUDE` constraints that
#: are syntactically valid and semantically wrong.
EXPRESSION_CONSTRAINT_TYPES = ("CHECK", "EXCLUDE")

#: Index methods an `EXCLUDE` constraint may be built with. `gist` first
#: because it is the only one that supports the overlap operators exclusion
#: constraints exist for; `btree` and `hash` only ever support `=`.
EXCLUDE_METHODS = ("gist", "btree", "spgist", "hash")

#: Referential actions for a foreign key's `ON DELETE` / `ON UPDATE`. `None`
#: means "emit no clause", which is Postgres's `NO ACTION` — the two are
#: equivalent at run time but only the first leaves the generated text quiet
#: about a choice the user did not make.
FK_ACTIONS = ("NO ACTION", "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT")


def add_constraint_skeleton(
    *,
    table: str,
    name: str,
    constraint_type: str,
    columns: Sequence[str] = (),
    expression: str | None = None,
    method: str = EXCLUDE_METHODS[0],
) -> str:
    """`ALTER TABLE … ADD CONSTRAINT … <PRIMARY KEY|UNIQUE|CHECK|EXCLUDE> …`.

    Which of the two remaining arguments is required is decided by
    `constraint_type`, and supplying the wrong one is refused rather than
    ignored:

    - `PRIMARY KEY` / `UNIQUE` take `columns` (one or more, in the caller's
      order — key order is semantic, so unlike `trigger_skeleton`'s events they
      are *not* re-sorted) and no `expression`;
    - `CHECK` / `EXCLUDE` take an `expression` and no `columns`. `EXCLUDE` also
      takes `method`, emitted as `USING <method>`.

    A silently ignored argument here would mean a dialog bug ships as a
    constraint that constrains the wrong thing.

    `expression` is arbitrary SQL and is validated by `_expression` exactly as
    `alter_column_type_skeleton`'s `USING` is — read that docstring for what is
    and is not guaranteed, including the rule that binds the dialog layer: this
    field may carry the user's own typed input and nothing else.
    """
    quoted_table = _qualified(table, "table")
    quoted_name = _identifier(name, "constraint name")

    if constraint_type not in CONSTRAINT_TYPES:
        raise SkeletonError(
            f"constraint type must be one of {', '.join(CONSTRAINT_TYPES)} — "
            f"got {constraint_type!r}"
        )

    if constraint_type in COLUMN_CONSTRAINT_TYPES:
        if expression is not None:
            raise SkeletonError(
                f"{constraint_type} is defined by a column list, not an expression"
            )
        column_list = _column_list(columns, f"a {constraint_type} constraint")
        definition = f"{constraint_type} ({column_list})"
    else:
        if columns:
            raise SkeletonError(
                f"{constraint_type} is defined by an expression, not a column list"
            )
        if expression is None:
            raise SkeletonError(f"a {constraint_type} constraint needs an expression")
        body = _expression(expression, f"{constraint_type} expression")
        if constraint_type == "CHECK":
            definition = f"CHECK ({body})"
        else:
            if method not in EXCLUDE_METHODS:
                raise SkeletonError(
                    f"index method must be one of {', '.join(EXCLUDE_METHODS)} — "
                    f"got {method!r}"
                )
            definition = f"EXCLUDE USING {method} ({body})"

    return (
        f"ALTER TABLE {quoted_table} ADD CONSTRAINT {quoted_name} {definition};\n"
    )


def add_foreign_key_skeleton(
    *,
    table: str,
    name: str,
    columns: Sequence[str],
    ref_table: str,
    ref_columns: Sequence[str],
    on_delete: str | None = None,
    on_update: str | None = None,
) -> str:
    """`ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY (…) REFERENCES … (…)`.

    The referenced column list is **required**, though Postgres permits its
    omission (in which case it silently means "the referenced table's primary
    key"). A generated statement that reads as if it names its target while
    depending on an invisible primary key is precisely the kind of text that
    looks authoritative and then binds to the wrong column after someone
    changes the PK; the dialog knows the target columns because it lists them,
    so it can say them.

    Both lists preserve caller order and must be the same length — a FK whose
    lists disagree is a Postgres error, and pairing is positional, so this is
    the one arity check the emitter can make on the caller's behalf.

    `on_delete` / `on_update` are `FK_ACTIONS` members or `None` for "no
    clause". They are keywords, never free text.
    """
    quoted_table = _qualified(table, "table")
    quoted_name = _identifier(name, "constraint name")
    quoted_ref_table = _qualified(ref_table, "referenced table")

    local = _column_list(columns, "a foreign key")
    referenced = _column_list(ref_columns, "a foreign key's referenced table")
    if len(list(columns)) != len(list(ref_columns)):
        raise SkeletonError(
            "a foreign key must reference exactly as many columns as it binds — "
            f"{len(list(columns))} local vs {len(list(ref_columns))} referenced"
        )

    clauses = ""
    if on_delete is not None:
        clauses += f" ON DELETE {_referential_action(on_delete, 'ON DELETE')}"
    if on_update is not None:
        clauses += f" ON UPDATE {_referential_action(on_update, 'ON UPDATE')}"

    return (
        f"ALTER TABLE {quoted_table} ADD CONSTRAINT {quoted_name} "
        f"FOREIGN KEY ({local}) "
        f"REFERENCES {quoted_ref_table} ({referenced}){clauses};\n"
    )


def drop_constraint_skeleton(*, table: str, name: str) -> str:
    """`ALTER TABLE … DROP CONSTRAINT …` — the ONE drop, for every type.

    There is no `drop_foreign_key_skeleton`, and adding one would be a bug: in
    Postgres a foreign key is a row in `pg_constraint` like any other, and this
    statement is character-for-character the same for a FK, a CHECK, a UNIQUE,
    an EXCLUDE and a primary key. The type only matters to the *picker*, which
    shows it so the user can tell what they are about to drop.

    No `CASCADE` and no `IF EXISTS`, for the same reason `drop_column_skeleton`
    omits them: dropping a primary key that other tables' foreign keys depend
    on must fail loudly, and a user who wants the cascade types the word into
    the tab they are about to run.
    """
    quoted_table = _qualified(table, "table")
    quoted_name = _identifier(name, "constraint name")
    return f"ALTER TABLE {quoted_table} DROP CONSTRAINT {quoted_name};\n"


def rename_constraint_skeleton(*, table: str, name: str, new_name: str) -> str:
    """`ALTER TABLE … RENAME CONSTRAINT … TO …`.

    Renaming to the current name is refused rather than emitted, matching
    `rename_column_skeleton`: Postgres errors on it, and a statement that fails
    on run is worse than one that was never generated.
    """
    quoted_table = _qualified(table, "table")
    quoted_name = _identifier(name, "constraint name")
    quoted_new = _identifier(new_name, "new constraint name")
    if quoted_name == quoted_new:
        raise SkeletonError(
            f"new constraint name is the same as the current one: {name!r}"
        )
    return (
        f"ALTER TABLE {quoted_table} "
        f"RENAME CONSTRAINT {quoted_name} TO {quoted_new};\n"
    )


# ---------------------------------------------------------------------------
# FQ-025 slice 3 -- indexes, comments and whole-table operations
#
# The first group here that is NOT an `ALTER TABLE`: `CREATE INDEX`,
# `DROP INDEX`, `COMMENT ON`, `CREATE TABLE` and `DROP TABLE` are five distinct
# statements, so none of them uses `_alter_column` and one of them
# (`drop_index_skeleton`) does not take a table at all.
# ---------------------------------------------------------------------------

#: Index access methods offered for a plain `CREATE INDEX`. A superset of
#: `EXCLUDE_METHODS`, which lists only the methods an EXCLUDE constraint can be
#: built with -- `gin` and `brin` support neither `=` nor the overlap operators
#: an exclusion constraint needs, but are perfectly ordinary index methods.
#: `btree` leads because it is Postgres's default and the right answer for
#: almost every index.
INDEX_METHODS = ("btree", "hash", "gist", "spgist", "gin", "brin")


@dataclass(frozen=True)
class ColumnSpec:
    """One column of a `CREATE TABLE` — the only compound argument in this
    module.

    A `dataclass` rather than a tuple or a dict because `create_table_skeleton`
    is the one emitter whose input is a *list of records*: a positional 4-tuple
    at a call site would say `("qty", "integer", False, None)` and leave the
    reader to count, and a dict would let a typo'd key mean "defaulted".

    `default` is free SQL (`0`, `now()`, `'pending'::text`) and is validated
    exactly like `set_column_default_skeleton`'s expression — read
    `alter_column_type_skeleton` for what that does and does not guarantee,
    including the rule binding the dialog layer: user-typed input only.
    """

    name: str
    datatype: str
    nullable: bool = True
    default: str | None = None


def create_index_skeleton(
    *,
    name: str,
    table: str,
    columns: Sequence[str],
    unique: bool = False,
    method: str = INDEX_METHODS[0],
) -> str:
    """`CREATE [UNIQUE] INDEX name ON table USING method (cols…)`.

    Three deliberate shapes:

    - **The index name is bare, the table's is qualified.** `CREATE INDEX` puts
      the index in its table's schema and rejects a dotted index name outright,
      so `name` goes through `_identifier` (which refuses a dot) while `table`
      goes through `_qualified`. Getting this backwards produces a statement
      that reads plausibly and fails on run.
    - **`USING <method>` is always emitted**, even for the `btree` default, so
      the generated text says which method it means rather than leaving the
      reader to know Postgres's default — the same reason
      `add_foreign_key_skeleton` always spells out its referenced columns.
    - **The column list is columns, not expressions.** Every entry is quoted as
      an identifier, so `lower(email)` is *refused*, not emitted: an expression
      index is written `((lower(email)))` with its own parenthesisation rules,
      and silently treating an expression as a column name would produce
      `("lower(email)")` — an index on a column that does not exist.

    `CONCURRENTLY` is not offered. It cannot run inside a transaction block,
    which is how the Apply paths execute generated statements, so a checkbox
    for it would produce text that fails there and works only if the user ran
    it elsewhere. A user who wants it types the word into the tab.
    """
    quoted_name = _identifier(name, "index name")
    quoted_table = _qualified(table, "table")
    if method not in INDEX_METHODS:
        raise SkeletonError(
            f"index method must be one of {', '.join(INDEX_METHODS)} — got {method!r}"
        )
    column_list = _column_list(columns, "an index")
    unique_keyword = "UNIQUE " if unique else ""
    return (
        f"CREATE {unique_keyword}INDEX {quoted_name} ON {quoted_table} "
        f"USING {method} ({column_list});\n"
    )


def drop_index_skeleton(*, index: str) -> str:
    """`DROP INDEX schema.index_name` — the ONE emitter here that takes no
    table.

    An index name is unique within its **schema**, not within its table, and
    `DROP INDEX` is spelled with that identity (`public.idx_orders_code`);
    there is no `DROP INDEX … ON table` in Postgres. So the argument is the
    index's own qualified name — `introspect.IndexInfo.qualified_name` —
    and passing `schema.table.index` here would emit a three-part name that
    Postgres reads as `database.schema.object` and rejects.

    No `CASCADE` and no `IF EXISTS`, matching `drop_column_skeleton` and
    `drop_constraint_skeleton`.

    **This emitter cannot tell a droppable index from a constraint-backed
    one** — it is handed a name, and the statement is identical either way.
    Postgres refuses `DROP INDEX` on the implicit index behind a PRIMARY KEY /
    UNIQUE / EXCLUDE constraint, so keeping those out of the picker (and
    *saying* that it did — see `introspect.IndexInfo`) is the dialog layer's
    job, not this function's.
    """
    quoted_index = _qualified(index, "index")
    return f"DROP INDEX {quoted_index};\n"


def set_table_comment_skeleton(*, table: str, comment: str | None) -> str:
    """`COMMENT ON TABLE … IS 'x'`, or `IS NULL` for a blank comment.

    Blank means **remove the comment**, because `IS NULL` is the only way
    Postgres offers to remove one and an empty box is the only way a user can
    ask. `IS ''` would leave an empty-string comment behind, which is a
    different (and invisible) state.
    """
    return _comment_on(f"TABLE {_qualified(table, 'table')}", comment)


def set_column_comment_skeleton(
    *, table: str, column: str, comment: str | None
) -> str:
    """`COMMENT ON COLUMN … IS 'x'`, or `IS NULL` for a blank comment.

    The same renderer `add_column_skeleton` has used since slice 1 — promoted
    rather than re-implemented, so there is exactly one place in the app that
    knows how a comment statement is spelled.
    """
    return _comment_on_column(
        _qualified(table, "table"), _identifier(column, "column name"), comment
    )


def create_table_skeleton(
    *,
    table: str,
    columns: Sequence[ColumnSpec],
    primary_key: Sequence[str] = (),
) -> str:
    """`CREATE TABLE … (…)` from a list of `ColumnSpec`s and an optional
    primary key.

    **What it deliberately does not express.** A `CREATE TABLE` can carry
    almost the whole DDL language; this builder covers columns (name, type,
    `NOT NULL`, `DEFAULT`) and a primary key, and *nothing else*:

    - no `FOREIGN KEY`, `UNIQUE`, `CHECK` or `EXCLUDE` constraints,
    - no indexes (an index is not part of `CREATE TABLE` at all),
    - no `GENERATED`/identity columns, collations, storage or compression,
    - no partitioning, inheritance, tablespace, `UNLOGGED` or `IF NOT EXISTS`.

    That is a refusal, not an oversight, and it is cheap precisely because of
    the shape of this feature: the other slice-2/3 dialogs add exactly those
    constraints and indexes to an existing table, and the generated text lands
    in an editor before anything runs. A checkbox-per-feature builder would
    instead have to guess at interactions (a `CHECK` referencing a column the
    user later renamed in the same dialog) and would emit subtly wrong DDL —
    the one outcome this module exists to prevent.

    **The primary key is emitted unnamed** (`PRIMARY KEY ("id")`), unlike
    slice 2's `add_constraint_skeleton`, which requires a name. The reason
    slice 2 requires one is that Postgres's auto-names for CHECK/UNIQUE
    constraints are unpredictable to a human (`orders_qty_check1`); a table's
    primary key is the one case where the auto-name is both deterministic and
    the convention everybody already uses (`orders_pkey`). Naming it here
    would produce noisier DDL that says the same thing.

    Every named `primary_key` column must be one of the defined columns —
    an unknown one is refused rather than emitted, since Postgres would reject
    it anyway and the dialog can fix it while the user is still looking.
    """
    quoted_table = _qualified(table, "table")

    specs = list(columns)
    if not specs:
        raise SkeletonError("a table needs at least one column")

    lines: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        quoted_column = _identifier(spec.name, "column name")
        if quoted_column in seen:
            raise SkeletonError(f"the table defines the same column twice: {quoted_column}")
        seen.add(quoted_column)

        line = f"{quoted_column} {_column_datatype(spec.datatype)}"
        if not spec.nullable:
            line += " NOT NULL"
        if spec.default is not None:
            line += (
                f" DEFAULT "
                f"{_expression(spec.default, f'default expression for {quoted_column}')}"
            )
        lines.append(line)

    key = list(primary_key)
    if key:
        quoted_key = _column_list(key, "a primary key")
        for column in key:
            if _identifier(column, "primary key column") not in seen:
                raise SkeletonError(
                    f"the primary key names a column the table does not define: "
                    f"{column!r}"
                )
        lines.append(f"PRIMARY KEY ({quoted_key})")

    body = f",\n{_INDENT}".join(lines)
    return f"CREATE TABLE {quoted_table} (\n{_INDENT}{body}\n);\n"


def drop_table_skeleton(*, table: str) -> str:
    """`DROP TABLE …`.

    **No confirmation, no typed-name dance, and no `CASCADE`.** The safeguard
    for this feature is architectural: generating `DROP TABLE t` executes
    nothing, the text lands in an editable tab, and running it is a separate
    explicit gesture (FQ-025's stated ruling). Adding a scary modal here would
    put the friction where nothing happens and leave it absent where something
    does.

    Omitting `CASCADE` is the same call `drop_column_skeleton` makes: a table
    another view or foreign key depends on must fail loudly rather than take
    its dependants with it silently.
    """
    return f"DROP TABLE {_qualified(table, 'table')};\n"


def _column_list(columns: Sequence[str], what: str) -> str:
    """`"a", "b"` — every name quoted, order preserved, duplicates refused.

    Order is preserved because a key's column order is semantic (it decides the
    backing index's usefulness and the FK's positional pairing), which is the
    opposite of `trigger_skeleton`'s canonicalised event set.

    A repeated column is refused rather than de-duplicated: `PRIMARY KEY (a, a)`
    is a Postgres error, and quietly collapsing it to `(a)` would emit a key the
    user did not ask for.
    """
    names = list(columns)
    if not names:
        raise SkeletonError(f"{what} needs at least one column")
    quoted = [_identifier(column, "column name") for column in names]
    seen: set[str] = set()
    for column in quoted:
        if column in seen:
            raise SkeletonError(f"{what} names the same column twice: {column}")
        seen.add(column)
    return ", ".join(quoted)


def _referential_action(action: str, what: str) -> str:
    if action not in FK_ACTIONS:
        raise SkeletonError(
            f"{what} must be one of {', '.join(FK_ACTIONS)} — got {action!r}"
        )
    return action


def _alter_column(table: str, column: str, action: str) -> str:
    """The shared `ALTER TABLE t ALTER COLUMN c <action>;` shape.

    `action` is never caller-supplied text — every call site above passes a
    literal, or a fragment whose only free part already went through
    `_expression`.
    """
    quoted_table = _qualified(table, "table")
    quoted_column = _identifier(column, "column name")
    return f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} {action};\n"


def _comment_on_column(
    quoted_table: str, quoted_column: str, comment: str | None
) -> str:
    """`COMMENT ON COLUMN t.c IS …` — the column flavour of `_comment_on`.

    Kept as a named helper (rather than inlined at its two call sites) because
    a column's comment target is the one that is *built* from two quoted parts
    joined by a dot, and that join is the part worth having in one place.
    """
    return _comment_on(f"COLUMN {quoted_table}.{quoted_column}", comment)


def _comment_on(target: str, comment: str | None) -> str:
    """The single `COMMENT ON <target> IS …` renderer for the whole app.

    `target` is never caller text: every call site passes a literal keyword
    plus already-quoted identifiers. `comment` is the opposite — a *value*, so
    it is emitted as a SQL string literal (embedded `'` doubled) rather than
    allowlisted, which is what lets an ordinary apostrophe through.

    `None`/blank renders `IS NULL`, Postgres's spelling for "remove the
    comment". `add_column_skeleton` never reaches that branch: it returns
    before calling this when its optional comment is blank, because there
    "blank" means the Add-column statement simply carries no comment.
    """
    if comment is None or not comment.strip():
        return f"COMMENT ON {target} IS NULL;\n"
    if "\x00" in comment:
        raise SkeletonError(f"comment contains a NUL character: {comment!r}")
    return f"COMMENT ON {target} IS {_sql_string_literal(comment)};\n"


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
