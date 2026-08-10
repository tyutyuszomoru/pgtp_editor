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

# pgtp_editor/sql/join_fk.py
"""JOIN-on-FK: write the `JOIN ... ON ...` a foreign key already implies (§18.6).

Pure and Qt-free (§5's dependency rule) and **schema-free**, exactly like
`sql/expand_select.py`, whose two-call shape this module repeats because the two
halves need different things:

1. `find_join_site(text, pos)` -- pure text work. Which tables are in scope at
   the caret, where a join clause would go, and which names are already taken.
   Its `qualified_names` are the `"schema.table"` keys the caller looks up.
2. `join_candidates(site, foreign_keys)` -- the caller injects **what the
   foreign keys are**; this layer decides **what the join should look like**.
3. `render_join(site, candidate)` -- one chosen candidate becomes an
   `Expansion` (`sql/templates.py`), the single insertion mechanism FQ-030
   mandates. No bespoke string building anywhere.

`ForeignKey` is deliberately a plain value type owned here rather than anything
out of `db/`: `db/introspect.py::ColumnInfo.fk_target` is a
`"schema.table.column"` string and `SchemaIndex` is the consumer's business.
`foreign_keys_from_targets` turns those raw strings into `ForeignKey`s, so the
one piece of knowledge about that string's shape is stated (and tested) once,
here, and the schema still never enters `sql/`.

ONE TOKENIZE, VIA AN EXISTING ANALYZER
--------------------------------------
Nothing here scans characters or tokens: the whole text side is one call to
`sql/from_clause.py::analyze_from_items`, whose spans and clause landmarks are
already exact. The caret path must not grow another pass over the token stream,
and this module adds none.

WHERE THE JOIN GOES
-------------------
Two shapes, and the site says which:

- The user has already typed a join lead (`FROM hr.jobcard j LEFT JOIN `) --
  the caret is the insertion point and the keyword they wrote is kept verbatim.
  This is the gesture FQ-030 describes ("after `... JOIN ` offer FK-related
  tables and auto-write the ON clause").
- Otherwise the clause is **appended after the last FROM item in scope** -- the
  one position that is always syntactically legal, since every following clause
  (`WHERE`, `GROUP BY`, `ORDER BY`) begins after it.

Either way the `Expansion` carries the span it edits (`start == end`: this is a
pure insertion), so the caller applies it with the same undo-block idiom it
already uses for expand-`SELECT` and for snippets, and never computes an offset.

AMBIGUITY IS A LIST, NOT A REFUSAL
----------------------------------
Two foreign keys between the same pair of tables (`created_by` and
`approved_by` both referencing `hr.person`) and a self-referencing key
(`employee.manager_id -> employee.id`) are the cases that tempt a guess. This
module guesses at neither and refuses at neither: **every candidate is
returned, in a deterministic order, for the caller to offer through the shared
completion popup**. Which foreign key the author meant is a question only the
author can answer, and §18.6 already owns a list-of-choices surface -- turning
two honest answers into a refusal would be worse than showing both.

A self-join is an ordinary candidate: the alias is derived against the names
already taken in the statement, so `hr.employee e` joined to itself yields
`JOIN hr.employee e2 ON e.manager_id = e2.id` -- correct SQL, no collision.

A falsy result with a user-facing `reason` (FQ-023's rule) is reserved for the
cases where there is genuinely nothing to offer: no FROM clause, no
schema-qualified table, or no foreign key touching anything in scope.

BOUNDARIES -- WHAT THIS DELIBERATELY DOES NOT KNOW
--------------------------------------------------
- **A CTE or derived item is never a join source.** `sql/from_clause.py` marks
  it `is_derived`, and a name with no catalog table behind it has no foreign
  keys. Its name still counts as *taken* for alias derivation.
- **A bare `FROM jobcard` is never a join source.** Without a schema there is
  no `"schema.table"` key to match a foreign key against, and no search path is
  guessed here (`sql/from_clause.py` states the same rule).
- **Composite (multi-column) foreign keys are only joined correctly when the
  caller says so.** `ColumnInfo.fk_target` is per column and carries no
  constraint name, so two columns of one composite key arrive as two unrelated
  `ForeignKey`s and become two single-column candidates. Pass `constraint=` on
  each `ForeignKey` and they are grouped into one candidate with an
  `ON a.x = b.x AND a.y = b.y` clause.
- **Incoming foreign keys are only as complete as what is injected.** A key
  pointing *at* an in-scope table is declared on some other table, which this
  layer cannot enumerate; the caller decides how wide to cast that net.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .expand_select import derive_alias, quote_identifier
from .from_clause import FromItem, analyze_from_items
from .templates import Expansion, expand_template

#: The clause when this module writes the join keyword itself.
JOIN_TEMPLATE = "{{lead}}{{join}} {{table}} {{alias}} {{on}} {{condition}}{{0}}"

#: The same, for a caret sitting after a join lead the user already typed.
JOIN_TEMPLATE_AFTER_KEYWORD = "{{lead}}{{table}} {{alias}} {{on}} {{condition}}{{0}}"

#: A join lead the user may already have typed before the caret. Every spelling
#: `sql/from_clause.py` tolerates, since the two must agree about what a join
#: introduction looks like. `CROSS`/`NATURAL` are matched so the gesture is not
#: offered a second keyword on top of them.
_JOIN_LEAD = re.compile(
    r"(?:natural\s+)?"
    r"(?:(?:left|right|full)(?:\s+outer)?|inner|cross)?"
    r"\s*join",
    re.IGNORECASE,
)

#: Candidate direction: the foreign key is declared **on** the in-scope table
#: (child -> parent), or **at** it (parent <- child).
OUTGOING = "outgoing"
INCOMING = "incoming"


@dataclass(frozen=True)
class ForeignKey:
    """One foreign-key column pair, in the vocabulary this module needs.

    Injected by the caller -- `sql/` never reads a catalog. `table` and
    `target_table` are `"schema.table"` keys (the same spelling
    `TableRef.qualified` and `SchemaIndex.known_columns()` use).

    `constraint` is the key's name when the caller knows it. It exists for one
    reason: it is the only thing that can tell two columns of one composite
    foreign key apart from two independent single-column keys. `None` means
    "unknown", and each row then stands alone.
    """

    table: str
    column: str
    target_table: str
    target_column: str
    constraint: str | None = None


@dataclass(frozen=True)
class JoinSite:
    """Where a join may be written at the caret -- or why it may not.

    Falsy when `ok` is False, in which case only `reason` is meaningful.
    """

    ok: bool = False
    reason: str = ""
    #: In-scope FROM items that can source a join: named, schema-qualified,
    #: not derived. Source order.
    items: tuple[FromItem, ...] = ()
    #: Every name already spoken for in the statement -- aliases, bare table
    #: names and derived-item names alike. What `derive_alias` must avoid.
    taken: tuple[str, ...] = ()
    #: Offset the clause is inserted at (a pure insertion: no text is replaced).
    insert_at: int = 0
    #: Whether the user already typed the join keyword before the caret.
    keyword_written: bool = False
    #: A keyword verbatim from the user's own statement, used as the casing
    #: model for the `JOIN` / `ON` this module generates.
    keyword_model: str = "FROM"
    #: Whitespace to emit before the clause: empty when the buffer already ends
    #: in whitespace at `insert_at`.
    lead: str = " "

    def __bool__(self) -> bool:
        return self.ok

    @property
    def qualified_names(self) -> tuple[str, ...]:
        """The distinct `"schema.table"` keys the caller must supply keys for."""
        seen: list[str] = []
        for item in self.items:
            qualified = item.ref.qualified
            if qualified and qualified not in seen:
                seen.append(qualified)
        return tuple(seen)


@dataclass(frozen=True)
class JoinCandidate:
    """One join this module is prepared to write.

    `pairs` are `(column on the in-scope table, column on the joined table)` in
    declaration order -- one entry for a single-column key, several for a
    composite one. The rendered `ON` clause is those pairs `AND`-ed together,
    always with the in-scope side on the left, so the clause reads in the same
    direction as the statement regardless of which way the key points.
    """

    #: What to write left of the dot for the table already in scope: its alias,
    #: or its bare name when it has none.
    source_name: str
    #: `"schema.table"` of the table already in scope.
    source_qualified: str
    #: `"schema.table"` being joined in.
    target_qualified: str
    #: Alias derived for the joined table, unique against the statement.
    alias: str
    pairs: tuple[tuple[str, str], ...]
    direction: str = OUTGOING
    is_self_join: bool = False
    #: Whether the joined table is already present in the statement.
    already_in_scope: bool = False
    constraint: str | None = None

    @property
    def target_schema(self) -> str:
        return self.target_qualified.rpartition(".")[0]

    @property
    def target_table(self) -> str:
        return self.target_qualified.rpartition(".")[2]

    @property
    def source_column(self) -> str:
        """First in-scope-side column -- the whole key for a single-column FK."""
        return self.pairs[0][0] if self.pairs else ""

    @property
    def target_column(self) -> str:
        """First joined-side column -- the whole key for a single-column FK."""
        return self.pairs[0][1] if self.pairs else ""

    @property
    def key(self) -> str:
        """A stable identity for this candidate, for a popup's `(key, display)`."""
        columns = "+".join(source for source, _ in self.pairs)
        return f"{self.target_qualified}:{self.source_name}.{columns}"

    @property
    def display(self) -> str:
        """A one-line description fit for the shared completion popup."""
        condition = " AND ".join(
            f"{self.source_name}.{source} = {self.alias}.{target}"
            for source, target in self.pairs
        )
        return f"{self.target_qualified} {self.alias} ON {condition}"


@dataclass(frozen=True)
class JoinOptions:
    """Every candidate join at one site, best first -- or why there is none.

    Empty and falsy is an answer, not a failure, and it always carries a
    `reason` fit to show the user. Iterable and sized, so a caller may loop
    over it without a None check.
    """

    candidates: tuple[JoinCandidate, ...] = ()
    reason: str = ""

    def __bool__(self) -> bool:
        return bool(self.candidates)

    def __len__(self) -> int:
        return len(self.candidates)

    def __iter__(self):
        return iter(self.candidates)

    def __getitem__(self, index):
        return self.candidates[index]

    @property
    def only(self) -> JoinCandidate | None:
        """The single candidate when there is exactly one, else None.

        For a caller that wants a one-keystroke gesture when the answer is
        unambiguous and a popup otherwise -- the check stated once, here.
        """
        return self.candidates[0] if len(self.candidates) == 1 else None


def find_join_site(text: str, pos: int) -> JoinSite:
    """Locate where a `JOIN` may be written for the caret at `pos`.

    Returns a falsy `JoinSite` carrying a `reason` -- never None, never an
    exception -- when the caret is not somewhere a join can be written.
    """
    try:
        return _find(text, pos)
    except Exception:  # pragma: no cover - defensive: never raise at a keypress
        return JoinSite(reason="this statement could not be read")


def join_candidates(
    site: JoinSite, foreign_keys: Iterable[ForeignKey] = ()
) -> JoinOptions:
    """Every join the injected `foreign_keys` imply at `site`, best first.

    Ordering is deterministic and stated so a caller may rely on it: a table
    not yet in the statement before one already there; then a key declared on
    the in-scope table before one pointing at it; then the in-scope tables in
    source order; then target name; then column name. The first entry is
    therefore the "most obviously meant" join, and `JoinOptions.only` is the
    unambiguous case.
    """
    if not site.ok:
        return JoinOptions(reason=site.reason or "there is nothing to join here")
    try:
        return _candidates(site, foreign_keys)
    except Exception:  # pragma: no cover - defensive: never raise at a keypress
        return JoinOptions(reason="the foreign keys could not be read")


def render_join(site: JoinSite, candidate: JoinCandidate | None) -> Expansion:
    """Turn one chosen `candidate` into an insertable `Expansion`.

    The caret lands after the written clause (`{{0}}`), which is where the next
    thing the author types belongs. Keyword casing follows the statement's own
    (`FROM` yields `JOIN`/`ON`, `from` yields `join`/`on`) -- the rule
    `sql/expand_select.py` already settled, applied identically here.
    """
    if not site.ok or candidate is None:
        return Expansion(reason=site.reason or "there is nothing to join here")
    try:
        return _render(site, candidate)
    except Exception:  # pragma: no cover - defensive: never raise at a keypress
        return Expansion(reason="the join could not be rendered")


def foreign_keys_from_targets(
    table: str, columns: Iterable[tuple[str, str | None]]
) -> tuple[ForeignKey, ...]:
    """`ForeignKey`s for `table` from `(column, fk_target)` pairs.

    `fk_target` is `db/introspect.py::ColumnInfo.fk_target` verbatim -- a
    `"schema.table.column"` string, or None for a column that is not a foreign
    key. This is the one place that string's shape is known, so the caller is a
    one-liner over `SchemaIndex.column_infos(table)` --
    `[(c.name, c.fk_target) for c in index.column_infos(table)]` --
    and `sql/` still never sees a schema.

    A target that is not exactly three segments is **skipped**, not guessed at:
    a two-segment target names no column and a four-segment one is not
    something this module can read, and inventing the missing half would put a
    wrong `ON` clause in the user's buffer.
    """
    found: list[ForeignKey] = []
    for column, target in columns:
        parsed = _parse_target(target)
        if parsed is None or not column:
            continue
        target_table, target_column = parsed
        found.append(ForeignKey(table, column, target_table, target_column))
    return tuple(found)


# --- internals -------------------------------------------------------------


def _parse_target(target: str | None) -> tuple[str, str] | None:
    """`"schema.table.column"` -> `("schema.table", "column")`, else None."""
    if not target:
        return None
    segments = target.split(".")
    if len(segments) != 3 or not all(segment for segment in segments):
        return None
    return f"{segments[0]}.{segments[1]}", segments[2]


def _find(text: str, pos: int) -> JoinSite:
    if not text:
        return JoinSite(reason="there is no statement here")

    located = analyze_from_items(text, pos)
    if not located.items:
        return JoinSite(reason="there is no FROM clause here to join to")

    sources = tuple(
        item
        for item in located.items
        if not item.ref.is_derived and item.ref.qualified
    )
    if not sources:
        return JoinSite(
            reason=(
                "a join needs a schema-qualified table in the FROM clause "
                "-- hr.jobcard, not jobcard"
            )
        )

    last_end = max(item.end for item in located.items)
    keyword_model = text[
        located.items[0].introducer_start : located.items[0].introducer_end
    ] or "FROM"

    insert_at = last_end
    keyword_written = False
    if pos > last_end:
        typed = text[last_end:pos]
        match = _JOIN_LEAD.fullmatch(typed.strip())
        if match is not None:
            insert_at = pos
            keyword_written = True
            keyword_model = match.group(0)

    lead = "" if insert_at <= 0 or text[insert_at - 1].isspace() else " "
    return JoinSite(
        ok=True,
        items=sources,
        taken=located.scope.names,
        insert_at=insert_at,
        keyword_written=keyword_written,
        keyword_model=keyword_model,
        lead=lead,
    )


def _candidates(site: JoinSite, foreign_keys: Iterable[ForeignKey]) -> JoinOptions:
    keys = tuple(foreign_keys)
    if not keys:
        return JoinOptions(reason="no foreign keys are known for these tables")

    qualified_in_scope = {
        item.ref.qualified.lower()
        for item in site.items
        if item.ref.qualified
    }

    # Grouped so a composite key named by the caller becomes ONE candidate with
    # every column pair, instead of one half-written join per column.
    grouped: dict[tuple, list[tuple[str, str]]] = {}
    order: list[tuple] = []
    for index, item in enumerate(site.items):
        source_qualified = item.ref.qualified or ""
        for key in keys:
            if _same(key.table, source_qualified):
                pair = (key.column, key.target_column)
                target = key.target_table
                direction = OUTGOING
            elif _same(key.target_table, source_qualified):
                pair = (key.target_column, key.column)
                target = key.table
                direction = INCOMING
            else:
                continue
            if not target or not all(pair):
                continue
            group = (
                index,
                item.ref.name,
                source_qualified,
                target,
                direction,
                key.constraint,
                None if key.constraint else pair,
            )
            if group not in grouped:
                grouped[group] = []
                order.append(group)
            if pair not in grouped[group]:
                grouped[group].append(pair)

    built: list[JoinCandidate] = []
    for group in order:
        index, source_name, source_qualified, target, direction, constraint, _ = group
        pairs = tuple(grouped[group])
        already = target.lower() in qualified_in_scope
        alias = derive_alias(target.rpartition(".")[2], site.taken)
        built.append(
            JoinCandidate(
                source_name=source_name,
                source_qualified=source_qualified,
                target_qualified=target,
                alias=alias,
                pairs=pairs,
                direction=direction,
                is_self_join=_same(target, source_qualified),
                already_in_scope=already,
                constraint=constraint,
            )
        )

    ordered = sorted(
        _dedupe(built),
        key=lambda candidate: (
            1 if candidate.already_in_scope else 0,
            0 if candidate.direction == OUTGOING else 1,
            _source_index(site, candidate),
            candidate.target_qualified.lower(),
            candidate.source_column.lower(),
        ),
    )
    if not ordered:
        return JoinOptions(
            reason="no foreign key relates these tables to anything known"
        )
    return JoinOptions(candidates=tuple(ordered))


def _source_index(site: JoinSite, candidate: JoinCandidate) -> int:
    for index, item in enumerate(site.items):
        if item.ref.name == candidate.source_name:
            return index
    return len(site.items)


def _dedupe(candidates: Sequence[JoinCandidate]) -> list[JoinCandidate]:
    """Drop candidates repeating an earlier one's join, keeping order.

    Two identical `ColumnInfo.fk_target` rows (the same key reported from both
    ends, say) must not become two identical popup entries.
    """
    seen: set[tuple] = set()
    unique: list[JoinCandidate] = []
    for candidate in candidates:
        identity = (
            candidate.source_name.lower(),
            candidate.target_qualified.lower(),
            candidate.pairs,
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(candidate)
    return unique


def _render(site: JoinSite, candidate: JoinCandidate) -> Expansion:
    condition = " AND ".join(
        f"{quote_identifier(candidate.source_name)}.{quote_identifier(source)}"
        f" = {candidate.alias}.{quote_identifier(target)}"
        for source, target in candidate.pairs
    )
    if not condition:
        return Expansion(reason="this foreign key names no columns to join on")
    template = (
        JOIN_TEMPLATE_AFTER_KEYWORD if site.keyword_written else JOIN_TEMPLATE
    )
    return expand_template(
        template,
        at=site.insert_at,
        values={
            "lead": site.lead,
            "join": _match_case("join", site.keyword_model),
            "table": _qualified_text(candidate.target_qualified),
            "alias": candidate.alias,
            "on": _match_case("on", site.keyword_model),
            "condition": condition,
        },
    )


def _qualified_text(qualified: str) -> str:
    """`"schema.table"` written as SQL -- each segment quoted only if it must be.

    The target name comes from a catalog, not from the buffer, so unlike
    expand-`SELECT`'s verbatim re-emission there is nothing typed to preserve
    and quoting is decided by `sql/expand_select.py::quote_identifier`.
    """
    schema, _, table = qualified.rpartition(".")
    if not schema:
        return quote_identifier(table)
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def _same(left: str | None, right: str | None) -> bool:
    """Case-insensitive `"schema.table"` comparison (unquoted names fold)."""
    return bool(left) and bool(right) and left.lower() == right.lower()


def _match_case(word: str, model: str) -> str:
    """`word` cased like `model` -- `FROM` -> `JOIN`, `from` -> `join`."""
    return word.upper() if model.isupper() else word.lower()
