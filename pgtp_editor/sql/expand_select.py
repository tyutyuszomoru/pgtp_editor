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

# pgtp_editor/sql/expand_select.py
"""Expand a bare `SELECT FROM hr.jobcard` into a column-listed skeleton (§18.6).

Pure and Qt-free (§5's dependency rule) and **schema-free**: this module never
touches `db/schema_index.py`. It is deliberately two calls, because the two
halves need different things:

1. `find_expand_select_site(text, pos)` -- pure text work. Locates the FROM
   item to expand, its exact span, and the clause landmarks around it. Its
   `qualified` is the key the caller looks up in `SchemaIndex.known_columns()`.
2. `render_expand_select(site, columns)` -- takes the column names the caller
   fetched and produces an `Expansion` (`sql/templates.py`): replacement text,
   the span it replaces, the caret, and tab stops.

Splitting there is what keeps the schema out of `sql/` and the SQL parsing out
of `ui/` at the same time -- the caller is a three-line adapter that owns
neither side.

ONE MECHANISM, NOT TWO
----------------------
The rendering goes through `sql/templates.py::expand_template`, the same engine
the static keyword snippets use. Expand-`SELECT` is simply the schema-dynamic
flavor: the column list, the table text and the alias arrive as template
`values`, and the `WHERE` condition stays a `{{0}}` tab stop. There is one
insertion mechanism in the editor, as FQ-030 requires.

WHAT IT REFUSES, AND WHY IT SAYS SO
-----------------------------------
The gesture rewrites a region of the user's buffer, so it applies only where
the rewrite is unambiguous:

- exactly **one** table reference in the caret's scope. Two or more, and
  "which one" would be a guess and the generated prefix would be wrong for the
  other;
- the reference must be a real named table -- not a subquery, a function call
  or a CTE-shaped bare name with no schema;
- **nothing already written between `SELECT` and `FROM`.** Overwriting a column
  list the user typed is the one unrecoverable outcome, so a written list is a
  refusal, not a merge.

Each refusal returns a falsy site carrying a `reason` fit to show the user --
FQ-023's rule that a gesture which cannot run states why instead of vanishing.

WHAT IT PRESERVES
-----------------
- **The typed schema, verbatim.** The replacement re-emits
  `text[item.name_start:item.name_end]` -- the exact characters the user typed,
  quoting and all. FQ-030 is explicit that expansion never rewrites the schema
  (its `pr.jobcard` example was a typo the user must see and fix themselves).
- **The typed keyword casing.** `FROM` yields `WHERE`, `from` yields `where`.
  That settles FQ-030's open question 3 for generated text without adding a
  setting: the statement stays in the case the author is already writing in.
- **An alias the user already wrote.** `SELECT FROM hr.jobcard jc` expands with
  `jc.` prefixes; deriving a fresh `j` beside it would be a rename.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .from_clause import FromItem, analyze_from_items
from .keywords import SQL_KEYWORDS
from .templates import Expansion, expand_template

#: The body rendered for the ordinary case: nothing but a `SELECT` and a FROM
#: item. Every schema-dependent part is a `value`; the one editable spot left
#: is the final caret, one space after `WHERE` -- exactly what FQ-030 asks for.
SELECT_TEMPLATE = " {{columns}} {{from}} {{table}} {{alias}} {{where}} {{0}}"

#: The same, for a statement that already has a `WHERE`: no second one is
#: written, and the caret stops after the alias.
SELECT_TEMPLATE_WITH_WHERE = " {{columns}} {{from}} {{table}} {{alias}}{{0}}"

#: What the column list falls back to when the caller knows no columns for the
#: table (schema not loaded, table not in the index). `*` is the honest answer:
#: it is what the user would have typed, and it is valid SQL -- inventing
#: column names would not be.
UNKNOWN_COLUMNS = "*"

#: Characters that need no quoting in an unquoted PostgreSQL identifier.
_BARE_EXTRA = "_$"


@dataclass(frozen=True)
class ExpandSite:
    """Where and how a bare `SELECT` may be expanded -- or why it may not.

    Falsy when `ok` is False, in which case only `reason` is meaningful.
    """

    ok: bool = False
    reason: str = ""
    item: FromItem | None = None
    #: `"schema.table"` -- the `SchemaIndex.known_columns()` key -- or None
    #: when the table was written bare (no schema is ever guessed here).
    qualified: str | None = None
    #: The table reference **verbatim**, as typed, for re-emission.
    table_text: str = ""
    #: The `FROM` keyword verbatim, for re-emission and casing.
    from_text: str = "FROM"
    #: The alias to prefix columns with: the one the user wrote, or derived.
    alias: str = ""
    #: How the alias is re-emitted. Verbatim when the user wrote one, so an
    #: `AS jc` stays `AS jc` rather than being normalized to `jc` behind their
    #: back; equal to `alias` when it was derived here.
    alias_text: str = ""
    #: Whether the alias was derived here (as opposed to already written).
    alias_derived: bool = False
    #: Region the expansion replaces: from just after `SELECT` to the end of
    #: the FROM item.
    start: int = 0
    end: int = 0
    #: Whether the statement already has a `WHERE` after the FROM item.
    has_where: bool = False

    def __bool__(self) -> bool:
        return self.ok


def find_expand_select_site(text: str, pos: int) -> ExpandSite:
    """Locate the expandable bare `SELECT` around the caret at `pos`.

    Returns a falsy `ExpandSite` carrying a `reason` -- never None, never an
    exception -- when the caret is not on one.
    """
    try:
        return _find(text, pos)
    except Exception:  # pragma: no cover - defensive: never raise at a keypress
        return ExpandSite(reason="this statement could not be read")


def render_expand_select(
    site: ExpandSite, columns: Sequence[str] = ()
) -> Expansion:
    """Turn a located `site` plus the table's `columns` into an `Expansion`.

    `columns` are bare column names in the order they should be listed --
    exactly what `SchemaIndex.known_columns()` returns. An empty sequence
    renders `*` rather than an empty select list.
    """
    if not site.ok or site.item is None:
        return Expansion(reason=site.reason or "there is nothing to expand")
    try:
        return _render(site, columns)
    except Exception:  # pragma: no cover - defensive: never raise at a keypress
        return Expansion(reason="the expansion could not be rendered")


def derive_alias(table: str, taken: Iterable[str] = ()) -> str:
    """The alias for `table` that no name in `taken` already uses.

    THE RULE (FQ-030 pins it; this is the one scheme, stated once):

    - the alias is the **first letter of the table name**, lowercased --
      `jobcard` -> `j`, `job_card` -> `j`, `"Orders"` -> `o`. The first letter,
      not an initialism: it is the rule a reader can apply in their head.
    - on collision, the smallest free **numeric suffix from 2 up** is appended:
      `j`, then `j2`, then `j3`. Numbering rather than more letters, because
      the second letter of a name is not more memorable than a digit and a
      longer prefix can collide all over again.
    - "first letter" means the first *alphabetic* character, so a name opening
      with `_` or a digit still yields a usable alias (`_tmp` -> `t`,
      `1st_try` -> `s`) instead of an unquotable one. A name with no letter at
      all (`"123"`, the empty name) falls back to `t`, then `t2`, `t3`.
    - a candidate that is a SQL keyword is skipped like a taken one, so a table
      whose initial spells one can never produce SQL that will not parse.

    `taken` is matched case-insensitively (unquoted identifiers fold), and is
    normally `FromItems.scope.names` -- every name already spoken for in the
    statement, derived tables included.
    """
    used = {name.lower() for name in taken if name}
    base = next((ch.lower() for ch in table or "" if ch.isalpha()), "t")

    def free(candidate: str) -> bool:
        return candidate not in used and candidate not in SQL_KEYWORDS

    if free(base):
        return base
    for suffix in range(2, len(used) + 3):
        candidate = f"{base}{suffix}"
        if free(candidate):
            return candidate
    return f"{base}{len(used) + 3}"  # pragma: no cover - loop above always hits


def quote_identifier(name: str) -> str:
    """`name` as it must be written in SQL: bare when it can be, quoted else.

    A name that is already lower-case, identifier-shaped and not a keyword is
    emitted bare; anything else (mixed case, spaces, a keyword) is
    double-quoted with embedded quotes doubled. Generated SQL that fails to
    parse would be worse than no gesture at all.
    """
    if not name:
        return '""'
    head = name[0]
    bare = (
        ((head.isalpha() and head.islower()) or head == "_")
        and all(ch.islower() or ch.isdigit() or ch in _BARE_EXTRA for ch in name)
        and name not in SQL_KEYWORDS
    )
    return name if bare else '"' + name.replace('"', '""') + '"'


# --- internals -------------------------------------------------------------


def _find(text: str, pos: int) -> ExpandSite:
    if not text:
        return ExpandSite(reason="there is no statement here")

    located = analyze_from_items(text, pos)
    select = located.clause("select")
    if select is None:
        return ExpandSite(reason="the caret is not inside a SELECT statement")
    if not located.items:
        return ExpandSite(reason="this SELECT has no FROM clause to expand")
    if len(located.items) > 1:
        return ExpandSite(
            reason="this SELECT reads several tables -- expand works on one"
        )

    item = located.items[0]
    if item.introducer != "from":
        return ExpandSite(reason="the caret is not inside a SELECT statement")
    if item.ref.is_derived or not item.ref.table:
        return ExpandSite(reason="a subquery has no columns to list")

    between = text[select.end : item.introducer_start]
    if between.strip():
        return ExpandSite(reason="this SELECT already lists its columns")

    where = located.clause_after(item.end, "where")
    alias = item.ref.alias
    # The item's own name is not "taken": the alias replaces it as the way to
    # refer to the table. Every *other* in-scope name is.
    taken = tuple(
        name
        for name in located.scope.names
        if name.lower() != item.ref.name.lower()
    )
    return ExpandSite(
        ok=True,
        item=item,
        qualified=item.ref.qualified,
        table_text=item.name_text(text),
        from_text=text[item.introducer_start : item.introducer_end],
        alias=alias or derive_alias(item.ref.table, taken),
        alias_text=(
            text[item.name_end : item.end].strip()
            if alias is not None
            else derive_alias(item.ref.table, taken)
        ),
        alias_derived=alias is None,
        start=select.end,
        end=item.end,
        has_where=where is not None,
    )


def _render(site: ExpandSite, columns: Sequence[str]) -> Expansion:
    listed = ", ".join(
        f"{site.alias}.{quote_identifier(column)}" for column in columns if column
    )
    template = (
        SELECT_TEMPLATE_WITH_WHERE if site.has_where else SELECT_TEMPLATE
    )
    return expand_template(
        template,
        at=site.start,
        end=site.end,
        values={
            "columns": listed or UNKNOWN_COLUMNS,
            "from": site.from_text,
            "table": site.table_text,
            "alias": site.alias_text or site.alias,
            "where": _match_case("where", site.from_text),
        },
    )


def _match_case(word: str, model: str) -> str:
    """`word` cased like `model` -- `FROM` -> `WHERE`, `from` -> `where`."""
    return word.upper() if model.isupper() else word.lower()
