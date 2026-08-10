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

# pgtp_editor/sql/caret_context.py
"""Caret-context resolution for schema-aware Ctrl+Space completion (§18.6).

Pure and Qt-free (§5's dependency rule), alongside `sql/keywords.py` and
`sql/tokenizer.py`: given editor text and a caret offset, determines what kind
of identifier reference sits under the caret --

- a bare or dotted identifier path (``tab``, ``sch.``, ``sch.tab.``) -- the
  schema-qualified-table-reference context;
- a ``NEW.`` / ``OLD.`` reference -- the trigger-row-variable context;
- an ``alias.`` reference whose alias is bound by the caret's own FROM clause
  (``FROM hr.jobcard jc`` ... ``jc.``) -- the alias context;
- a ``local.`` reference whose name is declared by the routine the caret is in
  (``rec hr.jobcard%ROWTYPE`` ... ``rec.``) -- the local-symbol context.

This module knows nothing about a live schema, a `DatabaseSchema`, or
`db/schema_index.py` -- it only parses text. The caller (`ddl_object_editor.py`
via its injected `SchemaIndex`) turns the resolved context into actual
suggestions.

A caret inside a `$$ ... $$` routine body resolves against **the body**: the
tokenizer keeps a dollar-quoted body opaque for every other consumer, and this
module descends into it whenever the caret is inside -- the two halves of one
rule, the same one `sql/from_clause.py` states for FROM scopes. Without that,
`NEW.`/`OLD.` completion would be dead exactly where plpgsql is written, since
the DDL object editor's buffer is a whole `pg_get_functiondef` result whose
body is one token. Strings, comments and quoted identifiers *nested inside* the
body stay opaque and stay unresolvable.

`ALIAS_REF` and `LOCAL_REF` are **refinements of** `DOTTED_PATH`, not rivals to
it: the same `parts`/`prefix` are still filled in, and only the extra
`table_ref` / `local_symbol` is new. That is deliberate -- a one-segment path is
ambiguous between a schema name, a FROM alias and a plpgsql variable, and
nothing here can rule out that they share a spelling. A caller that finds the
refinement unhelpful can fall back to the `DOTTED_PATH` reading of the very
same context with no re-resolution.

When a one-segment name is *both* a FROM alias and a declared local (a `FOR rec
IN SELECT ...` loop variable spelled like an alias, say), `ALIAS_REF` wins: it
is the reading that actually resolves to a catalog table and therefore to
columns, while a local may resolve to nothing completable.
"""
from __future__ import annotations

from dataclasses import dataclass

from .from_clause import TableRef, analyze_from_scope
from .routine_scope import LocalSymbol, analyze_routine_scope
from .tokenizer import WORD, dollar_body_at, tokenize

#: How many nested dollar-quoted bodies the caret may be descended into --
#: mirrors `from_clause._MAX_BODY_DEPTH`. A bound rather than trust: malformed
#: nesting must not recurse forever on a resolver that runs per keystroke.
_MAX_BODY_DEPTH = 5

#: Kinds of resolved caret context.
DOTTED_PATH = "dotted_path"  # bare identifier or dotted schema[.table] prefix
ROW_VARIABLE = "row_variable"  # NEW.<prefix> / OLD.<prefix>
ALIAS_REF = "alias_ref"  # <alias>.<prefix>, alias bound by a FROM clause
LOCAL_REF = "local_ref"  # <local>.<prefix>, name declared by the routine


@dataclass(frozen=True)
class CaretContext:
    """What is "under the caret" for completion purposes.

    ``kind`` is `DOTTED_PATH`, `ROW_VARIABLE` or `ALIAS_REF`.

    For `DOTTED_PATH`: ``parts`` holds the dotted segments typed so far
    *before* the partial word at the caret (``()`` for a bare identifier,
    ``("sch",)`` for ``sch.tab``'s table segment, ``("sch", "tab")`` for a
    third segment) and ``prefix`` is the partial word being typed (matched
    case-insensitively against candidates, `_CompletionPopup`'s convention).

    For `ROW_VARIABLE`: ``row_variable`` is ``"NEW"`` or ``"OLD"`` and
    ``prefix`` is the partial column name typed after the dot.

    For `ALIAS_REF`: ``table_ref`` is the `sql/from_clause.py::TableRef` the
    single segment resolves to (use ``table_ref.qualified`` as the
    `SchemaIndex.known_columns()` key), ``prefix`` is the partial column name
    typed after the dot, and ``parts`` still holds that one segment so the
    `DOTTED_PATH` reading stays available as a fallback.

    For `LOCAL_REF`: ``local_symbol`` is the
    `sql/routine_scope.py::LocalSymbol` the single segment resolves to (use
    ``local_symbol.rowtype_qualified`` as the `SchemaIndex.known_columns()`
    key -- it is None for a local whose fields this module cannot know, e.g. a
    `record` or a loop variable, and offering nothing is then the right
    answer), ``prefix`` is the partial field name, and ``parts`` again keeps
    the `DOTTED_PATH` fallback available.
    """

    kind: str
    prefix: str = ""
    parts: tuple[str, ...] = ()
    row_variable: str | None = None
    table_ref: TableRef | None = None
    local_symbol: LocalSymbol | None = None


def resolve_caret_context(text: str, pos: int) -> CaretContext | None:
    """Resolve what completion context applies at character offset `pos` in
    `text`, or `None` if the caret is not in a resolvable position (inside a
    string literal, comment or quoted identifier, or with nothing
    identifier-shaped behind it).

    A **dollar-quoted body is the one opaque region this descends into**: to
    the tokenizer a `$$ ... $$` routine body is a single opaque token -- which
    is right for every other consumer (a `FROM` in there is not the enclosing
    statement's FROM clause, and `sql/formatter.py` must never reindent body
    text) -- but when the caret is *inside* that body, the body is the text the
    caret lives in. So the body is re-resolved as text of its own, exactly as
    `sql/from_clause.py::_analyze` re-analyzes it, via the shared
    `sql/tokenizer.py::dollar_body_at` locator and under the same depth bound.
    Because the body is re-tokenized, a string, comment or quoted identifier
    **nested inside** the body is still opaque and still yields `None`.

    `pos` is a 0-based character offset, the same convention `sql/tokenizer.py`
    and `sql/formatter.py` use throughout.

    Nothing in the returned `CaretContext` is an offset today (`prefix` is text
    the caller measures against its own caret, `parts`/`row_variable`/
    `table_ref` are text), so the body descent needs no rebasing to stay
    correct in the *original* buffer's coordinates. **Any future field that
    carries a position must be rebased by `+ body_start` at the recursion
    boundary below** -- inside the recursion, positions are body-relative.

    The `LOCAL_REF` promotion happens **here, on the original text**, not
    inside the body recursion: a routine's parameters are declared in its
    *header*, which is outside the body the recursion descends into, so
    resolving locals against body text alone would lose them.
    `sql/routine_scope.py` does its own body descent from the full text and
    sees both halves.
    """
    context = _resolve(text, pos, depth=0)
    if (
        context is not None
        and context.kind == DOTTED_PATH
        and len(context.parts) == 1
    ):
        symbol = analyze_routine_scope(text, pos).resolve(context.parts[0])
        if symbol is not None:
            return CaretContext(
                kind=LOCAL_REF,
                prefix=context.prefix,
                parts=context.parts,
                local_symbol=symbol,
            )
    return context


def _resolve(text: str, pos: int, *, depth: int) -> CaretContext | None:
    tokens = tokenize(text)

    # Descend into a dollar-quoted body *before* the opacity test -- but only
    # into that one kind. Everything else opaque still ends resolution here.
    body = dollar_body_at(tokens, pos)
    if body is not None:
        if depth >= _MAX_BODY_DEPTH:
            return None
        body_text, body_start = body
        return _resolve(body_text, pos - body_start, depth=depth + 1)

    if _caret_inside_opaque_token(tokens, pos):
        return None

    # The partial word being typed, if any: a WORD token whose span contains
    # or immediately touches pos (touching covers Ctrl+Space pressed right at
    # a word boundary, before or after the word).
    partial = ""
    last_consumed_index = -1
    for i, tok in enumerate(tokens):
        if tok.kind == WORD and tok.start <= pos <= tok.end:
            partial = tok.text[: pos - tok.start]
            last_consumed_index = i
            break
    else:
        # No WORD token touches pos: resolvable only if the caret sits right
        # after a '.' (about to type the next segment / the NEW./OLD. column).
        last_consumed_index = _last_token_index_ending_at_or_before(tokens, pos)

    # Walk backward collecting `.`-separated identifier segments before the
    # partial word: `a.b.<partial>`.
    segments: list[str] = []
    index = last_consumed_index - 1 if partial else last_consumed_index
    while index >= 0:
        dot_tok = tokens[index]
        if dot_tok.kind == WORD or dot_tok.text != ".":
            break
        word_index = index - 1
        if word_index < 0 or tokens[word_index].kind != WORD:
            break
        segments.insert(0, tokens[word_index].text)
        index = word_index - 1

    if segments:
        # NEW./OLD. detection: exactly one segment and it's NEW/OLD (row
        # variables are conventionally written uppercase in plpgsql, but the
        # match is case-insensitive like every other identifier here).
        if len(segments) == 1 and segments[0].upper() in ("NEW", "OLD"):
            return CaretContext(
                kind=ROW_VARIABLE,
                prefix=partial,
                row_variable=segments[0].upper(),
            )
        # A lone segment naming a table the caret's own FROM clause binds is an
        # alias reference, not a schema. Only a ref an actual table backs is
        # promoted: a derived-table alias (`FROM (SELECT ...) y`) has no columns
        # to offer, so leaving it a `DOTTED_PATH` keeps today's behavior.
        if len(segments) == 1:
            ref = analyze_from_scope(text, pos).resolve(segments[0])
            if ref is not None and not ref.is_derived:
                return CaretContext(
                    kind=ALIAS_REF,
                    prefix=partial,
                    parts=tuple(segments),
                    table_ref=ref,
                )
        return CaretContext(kind=DOTTED_PATH, prefix=partial, parts=tuple(segments))

    # No dotted prefix: still a resolvable bare-identifier context (schema or
    # table name typed with no '.' yet) whenever there is a partial word, or
    # the caret sits in plain code with nothing to type yet (offers schemas).
    return CaretContext(kind=DOTTED_PATH, prefix=partial, parts=())


def _last_token_index_ending_at_or_before(tokens, pos: int) -> int:
    """Index of the last token whose `end <= pos`, else -1."""
    index = -1
    for i, tok in enumerate(tokens):
        if tok.end <= pos:
            index = i
        else:
            break
    return index


def _caret_inside_opaque_token(tokens, pos: int) -> bool:
    """True if `pos` sits strictly inside an opaque token's span (a string,
    quoted identifier, comment, or dollar-quoted body) -- nothing under the
    caret is a completable identifier there."""
    return any(tok.is_opaque and tok.start < pos < tok.end for tok in tokens)
