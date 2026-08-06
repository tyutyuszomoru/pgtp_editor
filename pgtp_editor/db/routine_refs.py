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

# pgtp_editor/db/routine_refs.py
"""Where does the XML call this database routine? (pure, best-effort)

The DDL Explorer (§18.1) browses routines and triggers that live in the
**database**; the `.pgtp` separately names database objects in its
event-handler bodies and its SQL-bearing attributes. Nothing connects the two,
so the question this module exists to answer — *"which pages break if I change
this function?"* — is today answered by grepping the XML by hand, and the
failure it prevents is the silent one: a `CREATE OR REPLACE` (or a deploy
script, §18.3) that changes a routine's shape while a page still calls the old
one, discovered at runtime by a user.

**Best-effort name matching, and it says so.** This is not a SQL parser and
must never claim completeness it cannot deliver — the same "no false
confidence" ethos as `analysis/reused_tables.py`. Concretely:

* A routine matches on a **call-shaped** occurrence — `name(` or
  `schema.name(`, case-insensitively, because unquoted PostgreSQL identifiers
  fold. Requiring the open paren is what keeps ordinary prose attributes
  (a caption reading "Orders") out of the result; it also means a routine
  referenced only by `regprocedure` literal or through dynamic SQL is missed.
* `other_schema.foo(` does **not** match `public.foo` — the leading
  `(?<![\\w.])` guard is the whole reason a qualified call to somebody else's
  function is not attributed here.
* A **trigger** has no call syntax, so it matches as a bare whole word. That
  is a weaker signal than a call and is labelled as such (`ref_type`).
* Occurrences inside SQL comments or string literals are not excluded.

**Overloads are not conflated, and not invented either.** A routine's identity
is `RoutineInfo.signature` — `schema.name(argtypes)` (§18.1, BUG-018) — so two
overloads of `public.f` produce two separate `RoutineUsage` records, keyed by
their distinct signatures. But `f(...)` in the XML names only `f`: name
matching cannot tell the overloads apart, so both usages carry the same
references and both are marked `ambiguous`. Reporting the ambiguity is honest;
guessing an overload from the argument count would not be.

This angle navigates **across** buffers — the DDL Explorer's `EditorPanel` tab
to the Raw XML tab, two documents and two `navigate_to_line` targets — unlike
the tree's table/function groupings, which stay inside the one DDL buffer. It
only applies when a project has a linked `.pgtp` (§18.2); with no project there
is nothing to cross-reference, and `collect_routine_references` returns an
empty list rather than a list of routines it would have to call "referenced
nowhere".

The page/detail/column walk itself is *not* re-implemented here: the labelling
of a page and a detail (the caption/fileName/tableName fallback order) is
imported from `analysis/reused_tables.py` so breadcrumbs read the same in this
panel as in the coherence tree (§17). The traversal is separate only because
that walk visits `<Lookup tableName=…>` targets, and this one visits event
bodies and every attribute value — different haystacks over the same tree.
Qt-free, psycopg-free, I/O-free.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Same import posture as `db/coherence.py`: reuse the label fallback order
# rather than spell it a second time and let the two drift.
from pgtp_editor.analysis.reused_tables import _SEP, _detail_label, _page_label

from .introspect import DatabaseSchema, RoutineInfo, TriggerInfo

#: A call-shaped occurrence of a function/procedure name.
REF_TYPE_CALL = "call"
#: A bare-word occurrence of a trigger name — weaker evidence than a call.
REF_TYPE_MENTION = "mention"


@dataclass(frozen=True)
class RoutineReference:
    """One place in the XML that appears to reference a database routine.

    routine_name: the DB-side name that matched — `schema.name` for a routine,
                  `schema.table.name` for a trigger. (The *matched text* may be
                  the unqualified form; this is the object it was attributed
                  to.)
    breadcrumb:   human-readable path, e.g.
                  "Page 'Orders' ▸ Event 'OnBeforeInsert'".
    node:         the owning model node (PageNode | DetailNode | ColumnNode |
                  EventNode) — what the Properties panel selects.
    kind:         "page" | "detail" | "column" | "event".
    line:         1-based source line in the `.pgtp` to jump to, or None. For a
                  multi-line event body this is the node's own line plus the
                  newlines preceding the match, which is exact for text nodes
                  and approximate for a wrapped attribute value.
    ref_type:     REF_TYPE_CALL | REF_TYPE_MENTION.
    """

    routine_name: str
    breadcrumb: str
    node: object
    kind: str
    line: int | None
    ref_type: str


@dataclass
class RoutineUsage:
    """One database routine or trigger, with every XML reference found for it.

    key:        `RoutineInfo.signature` for a routine (`schema.name(argtypes)`,
                consumed verbatim — never re-rendered, BUG-018), or
                `schema.table.name` for a trigger, matching how
                `DatabaseSchema.triggers` is keyed.
    name:       the name matching was done on — `schema.name` / trigger name.
    kind:       "function" | "procedure" | "trigger" (`RoutineInfo.kind`).
    ambiguous:  the DB has more than one overload under this name, so these
                references cannot be attributed to one of them.
    info:       the `RoutineInfo`/`TriggerInfo` this was built from.
    references: matches in document order (pages in order, then within a page
                its attributes, events, columns and nested details).
    """

    key: str
    name: str
    kind: str
    ambiguous: bool = False
    info: "RoutineInfo | TriggerInfo | None" = None
    references: list[RoutineReference] = field(default_factory=list)

    @property
    def referenced(self) -> bool:
        """Whether the XML appears to reference this object at all."""
        return bool(self.references)


# --- matching ---------------------------------------------------------------


def _call_pattern(schema: str, name: str) -> re.Pattern[str]:
    """`schema.name(` or a bare `name(`, never `other.name(`."""
    qualified = rf"{re.escape(schema)}\s*\.\s*{re.escape(name)}"
    return re.compile(
        rf"(?<![\w.])(?:{qualified}|{re.escape(name)})\s*\(",
        re.IGNORECASE,
    )


def _mention_pattern(name: str) -> re.Pattern[str]:
    """A bare whole word. Unlike a call it may be dot-qualified on the left
    (`public.orders.trg_x`): a trigger name has no call syntax, so the word
    itself is the only signal there is."""
    return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)


def _match_lines(pattern: re.Pattern[str], text: str, base_line: int | None) -> list[int | None]:
    """The distinct lines of `text` at which `pattern` matches, in order.

    Several hits on one line collapse to one reference — the navigation target
    is a line, so a second entry for it would be a duplicate row.
    """
    lines: list[int | None] = []
    seen: set[int | None] = set()
    for match in pattern.finditer(text):
        line = None if base_line is None else base_line + text.count("\n", 0, match.start())
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return lines


# --- the XML haystacks ------------------------------------------------------


@dataclass(frozen=True)
class _Haystack:
    """One searchable chunk of XML with everything a reference needs."""

    text: str
    breadcrumb: str
    node: object
    kind: str
    line: int | None


def _attribute_haystacks(node, attrib, crumb: str, kind: str, line: int | None):
    """Every attribute value of one element, keys in sorted order.

    Which attributes are "SQL-bearing" is deliberately *not* enumerated: PHP
    Generator's attribute vocabulary is large and undocumented here, and a
    hard-coded list would silently miss whichever attribute the user's project
    actually keeps its SQL in. Scanning all of them is safe precisely because
    the call-shaped match requirement (above) is what rejects prose.
    """
    for key in sorted(attrib):
        value = attrib.get(key)
        if isinstance(value, str) and value:
            yield _Haystack(value, f"{crumb} @{key}", node, kind, line)


def _column_haystacks(columns, prefix: str):
    for column in columns:
        crumb = f"{prefix}{_SEP}Column '{column.field_name or ''}'"
        yield from _attribute_haystacks(
            column, column.attrib, crumb, "column", column.sourceline
        )
        for child_name in ("format", "lookup", "view_properties", "edit_properties"):
            child = getattr(column, child_name, None)
            if child is None:
                continue
            child_line = child.sourceline if child.sourceline is not None else column.sourceline
            yield from _attribute_haystacks(
                column,
                child.attrib,
                f"{crumb}{_SEP}<{_CHILD_TAGS[child_name]}>",
                "column",
                child_line,
            )


_CHILD_TAGS = {
    "format": "Format",
    "lookup": "Lookup",
    "view_properties": "ViewProperties",
    "edit_properties": "EditProperties",
}


def _event_haystacks(events, prefix: str):
    for event in events:
        yield _Haystack(
            event.text or "",
            f"{prefix}{_SEP}Event '{event.tag_name}'",
            event,
            "event",
            event.sourceline,
        )


def _haystacks(project) -> list[_Haystack]:
    """Every searchable chunk of the project, in document order.

    Per container: its own attributes, then its event handlers, then its
    columns, then (recursively) its details — the order references come out in.
    """
    found: list[_Haystack] = []

    def visit_detail(detail, prefix: str) -> None:
        crumb = f"{prefix}{_SEP}Detail '{_detail_label(detail)}'"
        found.extend(
            _attribute_haystacks(detail, detail.attrib, crumb, "detail", detail.sourceline)
        )
        found.extend(_event_haystacks(detail.events, crumb))
        found.extend(_column_haystacks(detail.columns, crumb))
        for child in detail.details:
            visit_detail(child, crumb)

    for page in project.pages:
        crumb = f"Page '{_page_label(page)}'"
        found.extend(_attribute_haystacks(page, page.attrib, crumb, "page", page.sourceline))
        found.extend(_event_haystacks(page.events, crumb))
        found.extend(_column_haystacks(page.columns, crumb))
        for detail in page.details:
            visit_detail(detail, crumb)

    return found


# --- construction -----------------------------------------------------------


def _references(
    haystacks: list[_Haystack],
    pattern: re.Pattern[str],
    routine_name: str,
    ref_type: str,
) -> list[RoutineReference]:
    refs: list[RoutineReference] = []
    for hay in haystacks:
        for line in _match_lines(pattern, hay.text, hay.line):
            refs.append(
                RoutineReference(
                    routine_name=routine_name,
                    breadcrumb=hay.breadcrumb,
                    node=hay.node,
                    kind=hay.kind,
                    line=line,
                    ref_type=ref_type,
                )
            )
    return refs


def collect_routine_references(project, schema: DatabaseSchema) -> list[RoutineUsage]:
    """Cross-reference every DB routine and trigger against the XML.

    Every routine and trigger in `schema` gets exactly one `RoutineUsage`,
    including the ones referenced nowhere (an empty `references` list is the
    answer to "can I change this freely?", so it is not filtered out). Routines
    come first, ordered by signature, then triggers ordered by their
    `schema.table.name` key — stable and independent of dict insertion order.

    `project` is `None` (or page-less) when no `.pgtp` is linked (§18.2); this
    angle is meaningless then, so the result is empty rather than a list of
    routines misleadingly labelled unreferenced.
    """
    if project is None or not getattr(project, "pages", None):
        return []

    haystacks = _haystacks(project)

    # One match pass per distinct `schema.name`, shared by that name's
    # overloads — see the module docstring on why they cannot be told apart.
    overloads: dict[str, list[RoutineInfo]] = {}
    for routine in schema.routines.values():
        overloads.setdefault(f"{routine.schema}.{routine.name}", []).append(routine)

    usages: list[RoutineUsage] = []
    for qualified in sorted(overloads):
        siblings = overloads[qualified]
        first = siblings[0]
        refs = _references(
            haystacks, _call_pattern(first.schema, first.name), qualified, REF_TYPE_CALL
        )
        ambiguous = len(siblings) > 1
        for routine in sorted(siblings, key=lambda r: r.signature):
            usages.append(
                RoutineUsage(
                    key=routine.signature,
                    name=qualified,
                    kind=routine.kind,
                    ambiguous=ambiguous,
                    info=routine,
                    references=list(refs),
                )
            )

    for key in sorted(schema.triggers):
        trigger = schema.triggers[key]
        usages.append(
            RoutineUsage(
                key=key,
                name=trigger.name,
                kind="trigger",
                ambiguous=False,
                info=trigger,
                references=_references(
                    haystacks, _mention_pattern(trigger.name), trigger.name, REF_TYPE_MENTION
                ),
            )
        )

    return usages


def routine_reference_index(project, schema: DatabaseSchema) -> dict[str, RoutineUsage]:
    """`collect_routine_references` keyed by `RoutineUsage.key`.

    The lookup the tree does: a `BrowserPanel` leaf already holds the routine's
    signature (or the trigger's `schema.table.name`), which is exactly this
    key, so it can ask for its own references without a scan.
    """
    return {usage.key: usage for usage in collect_routine_references(project, schema)}
