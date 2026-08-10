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

# pgtp_editor/sql/templates.py
"""Template expansion with tab stops -- the ONE insertion mechanism (§18.6).

Pure and Qt-free like the rest of `pgtp_editor/sql/` (§5's dependency rule):
**a template plus values in, text plus a caret plus tab stops out.** It does
not insert anything, does not know what a `QTextCursor` is, and never touches a
document. The editor half (a `CodeEditor` that applies an `Expansion` in one
undo block and walks its stops on Tab) is a separate pass over `ui/`.

ONE ENGINE, TWO FLAVORS
-----------------------
FQ-030 records the insight this module exists to honor: expand-`SELECT` (slice
1) and keyword snippets (slice 2) are **one mechanism** -- template expansion
with tab stops -- and must not become two insertion paths.

- A **static** snippet (`case` -> a full `CASE` expression) is a template with
  no values: every editable spot is a tab stop.
- A **schema-dynamic** template (`sql/expand_select.py`) is the same template
  language with `values` filled from the live schema: the column list and the
  derived alias arrive as values, the `WHERE` condition stays a tab stop.

Both go through `expand_template` and both come back as an `Expansion`, so the
editor learns exactly one way to apply a change.

WHY `{{1}}` AND NOT `$1`
------------------------
The obvious TextMate-style syntax is unusable here, because this is a
*PostgreSQL* editor: `$1` is a positional parameter, `$$` opens a routine body
and `$tag$` a tagged one -- all three appear inside the very snippets that must
be shippable (the trigger-function skeleton is nothing but `$$`). A `$`-based
placeholder syntax would need escaping in the most common snippet in the set.

`{{n}}` collides with nothing in SQL: braces occur only inside array literals
and string bodies, and never doubled. `{{{{` escapes a literal `{{` for the
one caller who ever needs it.

TEMPLATE SYNTAX (all of it)
---------------------------
- ``{{1}}`` / ``{{2}}`` ... -- a tab stop, visited in numeric order.
- ``{{1:placeholder}}`` -- a tab stop whose placeholder text is inserted and
  spanned by the stop, so the editor can select it for overtyping.
- ``{{0}}`` -- the **final** caret. Visited last; it is where the caret lands
  when the expansion is applied.
- ``{{name}}`` / ``{{name:fallback}}`` -- substitution from `values`. A name
  missing from `values` yields its fallback (empty when none) rather than an
  error: half a template beats an exception in a key handler.
- ``{{{{`` -- a literal ``{{``.
- Anything else between braces is emitted **verbatim**, braces included, and an
  unclosed ``{{`` is emitted verbatim too. A malformed template degrades to
  text; it never raises and never silently swallows the rest of the body.

Substituted values are inserted literally and are **never rescanned**: a column
or table name that happens to contain `{{` is data, not markup.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

_OPEN = "{{"
_CLOSE = "}}"

#: Identifier shape a `{{name}}` substitution must have. Anything else between
#: the braces is not markup and is emitted verbatim.
_NAME_START = "_"


@dataclass(frozen=True)
class TabStop:
    """One editable spot in an applied expansion.

    `start`/`end` are **absolute buffer offsets** (the expansion's `start` is
    already added in), so the editor selects `text[start:end]` with no further
    arithmetic. They are equal for a stop with no placeholder.

    `number` is the stop's declared number; `0` is the final caret and is
    always visited last (see `Expansion.stops`).
    """

    number: int
    start: int
    end: int
    placeholder: str = ""

    @property
    def is_final(self) -> bool:
        return self.number == 0


@dataclass(frozen=True)
class Expansion:
    """A ready-to-apply edit: replace `[start, end)` with `text`.

    `caret` and every `TabStop` are absolute offsets **in the buffer as it will
    be after the replacement**, which is the only coordinate system an editor
    can act on without recomputing anything.

    An unusable expansion is `ok=False` with a `reason` fit to show the user
    (FQ-023's rule: a gesture that cannot run states why instead of vanishing),
    and is falsy -- so `if expansion:` is the guard.
    """

    text: str = ""
    start: int = 0
    end: int = 0
    caret: int = 0
    stops: tuple[TabStop, ...] = ()
    ok: bool = False
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok

    def apply(self, buffer: str) -> str:
        """`buffer` with the replacement made -- the pure model of the edit.

        The editor does this through its own undo-block idiom; this exists so
        the result can be asserted on in a test without a widget, and so a
        caller can preview.
        """
        if not self.ok:
            return buffer
        return buffer[: self.start] + self.text + buffer[self.end :]


def expand_template(
    template: str,
    *,
    at: int = 0,
    end: int | None = None,
    values: Mapping[str, str] | None = None,
) -> Expansion:
    """Expand `template` into an `Expansion` replacing `[at, end)`.

    `end` defaults to `at` -- a pure insertion. Pass a wider span to *rewrite*
    a region (what expand-`SELECT` does to a bare `SELECT ... FROM t`).

    The caret lands on the `{{0}}` stop when the template declares one, and at
    the end of the inserted text otherwise. Returns `ok=False` only for an
    empty template; every other malformation degrades to literal text (see the
    module docstring), because this runs from a key handler.
    """
    try:
        return _expand(template, at, end, values or {})
    except Exception:  # pragma: no cover - defensive: never raise at a keypress
        return Expansion(reason="the template could not be expanded")


def render(template: str, values: Mapping[str, str] | None = None) -> str:
    """Just the text of `expand_template` -- placeholders in, no offsets out.

    For callers that want the body of a snippet as a string (a preview, a
    settings editor showing what a keyword expands to).
    """
    return expand_template(template, values=values).text


# --- the shipped default snippet set ---------------------------------------


@dataclass(frozen=True)
class Snippet:
    """One keyword -> body pair. Exactly that -- FQ-030 rejected a builder GUI.

    `prefix` is the word the user types (matched case-insensitively);
    `title` is a one-line description for a list; `template` is the body in the
    syntax above.
    """

    prefix: str
    title: str
    template: str


#: The shipped plpgsql set FQ-030 names. User-defined pairs (persistence and
#: the Maintenance-mode editor) are a later pass and belong outside `sql/`;
#: this module only supplies the defaults and the lookup, so the store can
#: layer over it without forking the engine.
DEFAULT_SNIPPETS: tuple[Snippet, ...] = (
    Snippet(
        "case",
        "CASE expression",
        "CASE WHEN {{1:condition}} THEN {{2:result}}\n"
        "     ELSE {{3:result}}\n"
        "END{{0}}",
    ),
    Snippet(
        "forloop",
        "FOR ... IN SELECT ... LOOP",
        "FOR {{1:rec}} IN {{2:SELECT * FROM tbl}} LOOP\n"
        "    {{0}}\n"
        "END LOOP;",
    ),
    Snippet(
        "if",
        "IF ... THEN",
        "IF {{1:condition}} THEN\n    {{0}}\nEND IF;",
    ),
    Snippet(
        "ifelse",
        "IF / ELSIF / ELSE",
        "IF {{1:condition}} THEN\n"
        "    {{2}}\n"
        "ELSIF {{3:condition}} THEN\n"
        "    {{4}}\n"
        "ELSE\n"
        "    {{0}}\n"
        "END IF;",
    ),
    Snippet(
        "begin",
        "BEGIN ... EXCEPTION ... END",
        "BEGIN\n"
        "    {{1}}\n"
        "EXCEPTION WHEN {{2:others}} THEN\n"
        "    {{0}}\n"
        "END;",
    ),
    Snippet(
        "raise",
        "RAISE NOTICE",
        "RAISE NOTICE '{{1:message}} %', {{0:value}};",
    ),
    Snippet(
        "cursor",
        "cursor declaration",
        "{{1:cur}} CURSOR FOR\n    {{0:SELECT * FROM tbl}};",
    ),
    Snippet(
        "trigfn",
        "trigger function skeleton",
        "CREATE OR REPLACE FUNCTION {{1:schema}}.{{2:name}}()\n"
        "RETURNS trigger\n"
        "LANGUAGE plpgsql\n"
        "AS $$\n"
        "BEGIN\n"
        "    {{0}}\n"
        "    RETURN NEW;\n"
        "END;\n"
        "$$;",
    ),
)


def find_snippet(
    word: str, snippets: Iterable[Snippet] = DEFAULT_SNIPPETS
) -> Snippet | None:
    """The snippet `word` triggers, or None.

    Matched case-insensitively, like every other identifier comparison in the
    completion machinery (§18.6). None means "this word is not a snippet",
    which is the normal answer for almost every word, not a failure.
    """
    if not word:
        return None
    wanted = word.strip().lower()
    for snippet in snippets:
        if snippet.prefix.lower() == wanted:
            return snippet
    return None


# --- internals -------------------------------------------------------------


def _expand(
    template: str, at: int, end: int | None, values: Mapping[str, str]
) -> Expansion:
    if not template:
        return Expansion(reason="the template is empty")

    at = max(0, at)
    end = at if end is None else max(at, end)

    out: list[str] = []
    stops: list[TabStop] = []
    length = 0  # characters emitted so far, == len("".join(out))
    i = 0
    n = len(template)

    while i < n:
        opened = template.find(_OPEN, i)
        if opened == -1:
            out.append(template[i:])
            length += n - i
            break

        literal = template[i:opened]
        out.append(literal)
        length += len(literal)

        # `{{{{` -- an escaped literal `{{`.
        if template.startswith(_OPEN + _OPEN, opened):
            out.append(_OPEN)
            length += len(_OPEN)
            i = opened + 2 * len(_OPEN)
            continue

        closed = template.find(_CLOSE, opened + len(_OPEN))
        if closed == -1:
            # Unclosed: the rest is text, not a swallowed template.
            out.append(template[opened:])
            length += n - opened
            break

        body = template[opened + len(_OPEN) : closed]
        i = closed + len(_CLOSE)

        name, _, default = body.partition(":")
        emitted = _placeholder_text(name, default, body, values)
        if _is_stop(name):
            stops.append(
                TabStop(
                    number=int(name),
                    start=at + length,
                    end=at + length + len(emitted),
                    placeholder=emitted,
                )
            )
        out.append(emitted)
        length += len(emitted)

    text = "".join(out)
    ordered = _ordered_stops(stops)
    final = next((stop for stop in ordered if stop.is_final), None)
    return Expansion(
        text=text,
        start=at,
        end=end,
        caret=final.start if final is not None else at + len(text),
        stops=ordered,
        ok=True,
    )


def _is_stop(name: str) -> bool:
    """Whether `{{name...}}` declares a tab stop (a bare non-negative number)."""
    return name.isdigit()


def _is_value_name(name: str) -> bool:
    """Whether `{{name...}}` names a substitution value."""
    if not name:
        return False
    head = name[0]
    if not (head.isalpha() or head == _NAME_START):
        return False
    return all(ch.isalnum() or ch == _NAME_START for ch in name)


def _placeholder_text(
    name: str, default: str, body: str, values: Mapping[str, str]
) -> str:
    """The text one `{{...}}` contributes."""
    if _is_stop(name):
        return default
    if _is_value_name(name):
        value = values.get(name)
        return default if value is None else value
    # Not markup at all -- emit it back exactly as written.
    return _OPEN + body + _CLOSE


def _ordered_stops(stops: list[TabStop]) -> tuple[TabStop, ...]:
    """Tab order: 1, 2, 3 ... then every `{{0}}` last.

    Ties (two stops declared with the same number -- a mirror) keep source
    order; this engine inserts both but does not link them, and saying so is
    better than pretending a mirror is supported.
    """
    return tuple(
        sorted(
            stops,
            key=lambda stop: (1 if stop.is_final else 0, stop.number, stop.start),
        )
    )
