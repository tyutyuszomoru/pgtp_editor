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
  (``FROM hr.jobcard jc`` ... ``jc.``) -- the alias context.

This module knows nothing about a live schema, a `DatabaseSchema`, or
`db/schema_index.py` -- it only parses text. The caller (`ddl_object_editor.py`
via its injected `SchemaIndex`) turns the resolved context into actual
suggestions.

`ALIAS_REF` is a **refinement of** `DOTTED_PATH`, not a rival to it: the same
`parts`/`prefix` are still filled in, and only the extra `table_ref` is new.
That is deliberate -- a one-segment path is ambiguous between a schema name and
an alias, and nothing here can rule out that a schema and an in-scope alias
share a spelling. A caller that finds `table_ref` unhelpful can fall back to
the `DOTTED_PATH` reading of the very same context with no re-resolution.
"""
from __future__ import annotations

from dataclasses import dataclass

from .from_clause import TableRef, analyze_from_scope
from .tokenizer import WORD, tokenize

#: Kinds of resolved caret context.
DOTTED_PATH = "dotted_path"  # bare identifier or dotted schema[.table] prefix
ROW_VARIABLE = "row_variable"  # NEW.<prefix> / OLD.<prefix>
ALIAS_REF = "alias_ref"  # <alias>.<prefix>, alias bound by a FROM clause


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
    """

    kind: str
    prefix: str = ""
    parts: tuple[str, ...] = ()
    row_variable: str | None = None
    table_ref: TableRef | None = None


def resolve_caret_context(text: str, pos: int) -> CaretContext | None:
    """Resolve what completion context applies at character offset `pos` in
    `text`, or `None` if the caret is not in a resolvable position (inside a
    string/comment/quoted identifier, or with nothing identifier-shaped
    behind it).

    `pos` is a 0-based character offset, the same convention `sql/tokenizer.py`
    and `sql/formatter.py` use throughout.
    """
    tokens = tokenize(text)

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
