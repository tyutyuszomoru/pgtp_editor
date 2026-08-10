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

# pgtp_editor/sql/signature_help.py
"""Signature help: which parameter the caret is on, and what it expects (§18.6).

Pure and Qt-free (§5's dependency rule) and **schema-free**, in the same two-call
shape as `sql/expand_select.py` and `sql/join_fk.py`:

1. `find_call_site(text, pos)` -- pure text work. Which call the caret is
   inside, what it is called, which argument the caret is on, and where each
   argument is written.
2. `signature_help(site, signatures)` -- the caller injects **what the shop's
   routines look like**; this layer decides **which one applies and which of
   its parameters is live**.

This is a **query, not an insertion**: it returns data and the UI renders it.
Nothing here produces an `Expansion`, and nothing here knows what a popup or a
tooltip is. `RoutineSignature` is a plain value type owned here;
`routine_signature(...)` builds one straight from
`db/introspect.py::RoutineInfo`'s `args` / `return_type`, so the caller is a
one-liner and `db/` still never enters `sql/`.

WHAT IS PARSED, AND HOW MUCH
----------------------------
Exactly as much as answering "which argument is the caret on" requires, and no
grammar beyond it:

- **The innermost enclosing *call*.** Parentheses are tracked as a stack, and
  the frame reported is the innermost one whose `(` is preceded by a name. A
  grouping paren (`f(a, (b + c)<caret>`) is therefore stepped over rather than
  mistaken for a call with one argument, and a nested call
  (`outer(a, inner(x, <caret>))`) reports `inner`, argument 1 -- which is what
  breaks naive comma counting.
- **Arguments are separated by commas at that frame's own depth.** A comma
  inside a nested call, a row constructor, an array subscript or a type
  modifier (`cast(x as numeric(12,2))`) belongs to a deeper frame and is not
  counted.
- **A caret inside a string argument is still on that argument.** Strings,
  quoted identifiers, comments and dollar-quoted bodies are single opaque
  tokens to `sql/tokenizer.py`, so a comma inside one is not a separator --
  this falls out of reusing the tokenizer instead of scanning characters, and
  needs no special case. Unlike `sql/caret_context.py`, which refuses inside an
  opaque token because there is no identifier to complete there, this module
  answers: the author typing inside `'...'` still wants to know what parameter
  they are filling in.
- **A `;` behind the caret discards every unclosed frame**, and a `;` ahead of
  it ends the scan. Statement scoping without a second analyzer: a stray `(`
  in an earlier statement cannot pull the caret into a phantom call.

Deliberately NOT parsed -- a partial answer that knows it is partial:

- **Named-notation arguments** (`f(b => 2, a => 1)`) are counted positionally
  like any other, so the active parameter is the caret's *position*, not the
  name it wrote. Reading `=>` would mean picking an overload before the
  argument list is finished.
- **A keyword callee is never a call.** `IN (`, `VALUES (`, `EXISTS (` and
  friends are syntax, not routines; so are `LEFT(`/`RIGHT(`, which are also
  keywords. The shop's own routines -- the ones FQ-030 asks about -- can never
  be spelled with a keyword, so the whole class is excluded rather than
  enumerated.
- **Overload resolution by argument type.** Nothing here evaluates an
  expression's type. Overloads are ranked by *arity fit* only and all of them
  are returned, best first, so the UI can offer the set (LSP's own model).

ONE TOKENIZE, AND ONE ONLY
--------------------------
`find_call_site` tokenizes once. It takes an optional `tokens=` so a caller
that already tokenized the same text hands its list over instead, and it uses
the shared `sql/tokenizer.py::dollar_body_at` locator -- under the same depth
bound as `sql/from_clause.py` and `sql/caret_context.py` -- to descend into a
`$$ ... $$` routine body, since that is exactly where plpgsql calls are
written. Every offset reported is rebased into the original buffer on the way
out, so a caller always slices the text it passed in.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .tokenizer import (
    PUNCT,
    QUOTED_IDENT,
    WORD,
    Token,
    dollar_body_at,
    tokenize,
)

#: How many nested dollar-quoted bodies the caret may be descended into --
#: mirrors `from_clause._MAX_BODY_DEPTH` / `caret_context._MAX_BODY_DEPTH`.
_MAX_BODY_DEPTH = 5

#: Kinds that can spell one segment of a callee's name.
_NAME_KINDS = frozenset({WORD, QUOTED_IDENT})


@dataclass(frozen=True)
class Argument:
    """One written argument of a call, as a span in the original buffer.

    `start`/`end` bound the argument's text with surrounding whitespace already
    trimmed, so `text[start:end]` is what the author typed. An argument not yet
    typed (the empty slot after a trailing comma, or an empty argument list) is
    an empty span at the position it would occupy -- present, so the indices
    never shift under the caller.
    """

    index: int
    start: int
    end: int

    def text_in(self, text: str) -> str:
        return text[self.start : self.end]


@dataclass(frozen=True)
class CallSite:
    """The call the caret sits inside -- or why it does not sit in one.

    Falsy when `ok` is False, in which case only `reason` is meaningful.
    """

    ok: bool = False
    reason: str = ""
    #: The callee **verbatim**, as typed (`"hr.calc_total"`, `"Calc"`).
    callee: str = ""
    #: Schema segment as written, or None when the call was written bare.
    schema: str | None = None
    #: Bare routine name as written.
    name: str = ""
    #: Span of the callee's dotted name in the buffer.
    name_start: int = 0
    name_end: int = 0
    #: Offset of the opening `(`, and of the matching `)` when one is written.
    open_paren: int = 0
    close_paren: int | None = None
    #: Every argument slot of this call, in order.
    arguments: tuple[Argument, ...] = ()
    #: Which slot the caret is on, 0-based. Always a valid index into
    #: `arguments`; `0` for an empty argument list.
    argument_index: int = 0
    #: Whether the caret sits inside a string / comment / quoted identifier.
    #: The answer is still given (see the module docstring); the flag is there
    #: for a caller that wants to style it differently.
    in_literal: bool = False

    def __bool__(self) -> bool:
        return self.ok

    @property
    def argument_count(self) -> int:
        """How many argument slots are written -- `0` for `f()`.

        A slot counts once it exists, even while still empty: `f(a, <caret>`
        has written two, which is what ranking an overload set needs to know.
        Only a lone empty slot -- an argument list with nothing in it at all --
        counts as none.
        """
        if len(self.arguments) == 1 and self.arguments[0].start == self.arguments[0].end:
            return 0
        return len(self.arguments)

    @property
    def qualified(self) -> str:
        """`"schema.name"` when a schema was written, else the bare name."""
        return f"{self.schema}.{self.name}" if self.schema else self.name


@dataclass(frozen=True)
class Parameter:
    """One parameter of a routine, in the vocabulary this module needs."""

    name: str = ""
    type_text: str = ""
    #: `"in"` / `"out"` / `"inout"` / `"variadic"`, or `""` when unknown.
    mode: str = ""

    @property
    def is_variadic(self) -> bool:
        return self.mode.lower() == "variadic"

    @property
    def label(self) -> str:
        """`"name type"`, degrading to whichever half is known."""
        parts = [part for part in (self.name, self.type_text) if part]
        prefix = f"{self.mode.upper()} " if self.mode and self.mode != "in" else ""
        return prefix + " ".join(parts)


@dataclass(frozen=True)
class RoutineSignature:
    """One routine the caller knows about, injected -- never read from a DB.

    `name` is `"schema.name"` or a bare name, whichever the caller keys on.
    """

    name: str
    parameters: tuple[Parameter, ...] = ()
    return_type: str | None = None
    kind: str = "function"

    @property
    def schema(self) -> str | None:
        head, sep, _ = self.name.rpartition(".")
        return head if sep else None

    @property
    def bare_name(self) -> str:
        return self.name.rpartition(".")[2] or self.name

    @property
    def is_variadic(self) -> bool:
        return bool(self.parameters) and self.parameters[-1].is_variadic

    @property
    def label(self) -> str:
        """`"hr.calc(a integer, b text) RETURNS numeric"` -- one line for a tip."""
        rendered = ", ".join(parameter.label for parameter in self.parameters)
        head = f"{self.name}({rendered})"
        if self.return_type:
            return f"{head} RETURNS {self.return_type}"
        return head

    def accepts(self, index: int) -> bool:
        """Whether a 0-based argument at `index` fits this signature."""
        if index < len(self.parameters):
            return True
        return self.is_variadic

    def parameter_at(self, index: int) -> Parameter | None:
        """The parameter an argument at `index` fills, or None if there is none.

        A trailing `VARIADIC` parameter absorbs every further argument, so it is
        returned for any index at or past it.
        """
        if index < len(self.parameters):
            return self.parameters[index]
        if self.is_variadic and self.parameters:
            return self.parameters[-1]
        return None


@dataclass(frozen=True)
class SignatureHelp:
    """What to show for the caret's call -- or why there is nothing to show.

    Falsy when `ok` is False. `signatures` is every routine matching the name,
    best first (arity fit, then closeness of arity), and `active_signature`
    indexes it -- the LSP model, so an overload set is offered rather than one
    of them being guessed at.
    """

    ok: bool = False
    reason: str = ""
    callee: str = ""
    signatures: tuple[RoutineSignature, ...] = ()
    active_signature: int = 0
    #: Which argument the caret is on, 0-based -- straight from the `CallSite`.
    active_parameter: int = 0
    argument_count: int = 0

    def __bool__(self) -> bool:
        return self.ok

    @property
    def signature(self) -> RoutineSignature | None:
        """The signature being shown, or None when there is none."""
        if 0 <= self.active_signature < len(self.signatures):
            return self.signatures[self.active_signature]
        return None

    @property
    def parameter(self) -> Parameter | None:
        """The parameter the caret is filling in, or None when past the last."""
        signature = self.signature
        if signature is None:
            return None
        return signature.parameter_at(self.active_parameter)

    @property
    def too_many_arguments(self) -> bool:
        """Whether the caret is past the last parameter every overload declares."""
        return bool(self.signatures) and not any(
            signature.accepts(self.active_parameter) for signature in self.signatures
        )

    @property
    def label(self) -> str:
        """The active signature's one-line label, or empty."""
        signature = self.signature
        return signature.label if signature is not None else ""


def find_call_site(
    text: str, pos: int, *, tokens: Sequence[Token] | None = None
) -> CallSite:
    """Locate the call whose argument list contains the caret at `pos`.

    Returns a falsy `CallSite` carrying a `reason` -- never None, never an
    exception -- when the caret is not inside one. Pass `tokens` when the
    caller already tokenized this exact `text`, so no second pass is made.
    """
    try:
        return _find(text, pos, tokens=tokens, depth=0, base=0)
    except Exception:  # pragma: no cover - defensive: never raise at a keystroke
        return CallSite(reason="this call could not be read")


def signature_help(
    site: CallSite, signatures: Iterable[RoutineSignature] = ()
) -> SignatureHelp:
    """Match the caret's call against the injected `signatures`.

    Overloads are ranked by arity fit -- a signature that has a parameter for
    the caret's argument first, then by how close its parameter count is to
    what is written. All matches are returned so a caller can offer the set.
    """
    if not site.ok:
        return SignatureHelp(reason=site.reason or "the caret is not inside a call")
    try:
        return _help(site, signatures)
    except Exception:  # pragma: no cover - defensive: never raise at a keystroke
        return SignatureHelp(reason="the signature could not be read")


def routine_signature(
    name: str,
    args: Iterable[tuple[str, str]] = (),
    return_type: str | None = None,
    kind: str = "function",
) -> RoutineSignature:
    """Build a `RoutineSignature` from `db/introspect.py::RoutineInfo`'s parts.

    `args` is that dataclass's `args` verbatim -- `(name, type)` pairs in
    declared order -- so the caller's adapter is one expression and the shape of
    `RoutineInfo` stays entirely the caller's business. A `VARIADIC` prefix
    written into a type is recognized, since that is how PostgreSQL spells it.
    """
    parameters: list[Parameter] = []
    for entry in args or ():
        try:
            arg_name, arg_type = entry
        except (TypeError, ValueError):
            continue
        mode = ""
        type_text = (arg_type or "").strip()
        lowered = type_text.lower()
        for candidate in ("variadic", "inout", "out", "in"):
            if lowered.startswith(candidate + " "):
                mode = candidate
                type_text = type_text[len(candidate) :].strip()
                break
        parameters.append(
            Parameter(name=arg_name or "", type_text=type_text, mode=mode)
        )
    return RoutineSignature(
        name=name,
        parameters=tuple(parameters),
        return_type=return_type,
        kind=kind,
    )


# --- internals -------------------------------------------------------------


@dataclass
class _Frame:
    """One open paren while scanning: where it is and what (if anything) calls it."""

    open_token: int
    open_end: int
    callee_first: int | None
    boundaries: list[int]  # argument start offsets, first is just after `(`
    comma_ends: list[int]  # argument end offsets, one per comma seen


def _find(
    text: str,
    pos: int,
    *,
    tokens: Sequence[Token] | None,
    depth: int,
    base: int,
) -> CallSite:
    if not text:
        return CallSite(reason="there is no call here")
    pos = max(0, min(pos, len(text)))

    stream = list(tokens) if tokens is not None else tokenize(text)

    body = dollar_body_at(stream, pos)
    if body is not None:
        if depth >= _MAX_BODY_DEPTH:
            return CallSite(reason="this routine body is nested too deeply to read")
        body_text, body_offset = body
        return _find(
            body_text,
            pos - body_offset,
            tokens=None,
            depth=depth + 1,
            base=base + body_offset,
        )

    frame, close_at = _enclosing_call(stream, pos)
    if frame is None:
        return CallSite(reason="the caret is not inside a call's argument list")

    return _site(text, pos, stream, frame, close_at, base)


def _enclosing_call(
    stream: Sequence[Token], pos: int
) -> tuple[_Frame | None, int | None]:
    """The innermost *call* frame containing `pos`, and its `)` when written."""
    stack: list[_Frame] = []
    for index, tok in enumerate(stream):
        if tok.kind != PUNCT:
            continue
        if tok.text == ";":
            # Behind the caret: every still-open frame belongs to a finished
            # statement and cannot contain the caret. Ahead of it: the caret's
            # statement is over, so nothing further can close its frames.
            if tok.start < pos:
                stack.clear()
                continue
            break
        if tok.text == "(":
            stack.append(
                _Frame(
                    open_token=index,
                    open_end=tok.end,
                    callee_first=_callee_first(stream, index),
                    boundaries=[tok.end],
                    comma_ends=[],
                )
            )
            continue
        if tok.text == "," and stack:
            frame = stack[-1]
            frame.comma_ends.append(tok.start)
            frame.boundaries.append(tok.end)
            continue
        if tok.text == ")" and stack:
            frame = stack.pop()
            if frame.open_end <= pos <= tok.start and frame.callee_first is not None:
                return frame, tok.start
            continue
    # Unclosed frames: the normal state while typing. Innermost call wins.
    for frame in reversed(stack):
        if frame.open_end <= pos and frame.callee_first is not None:
            return frame, None
    return None, None


def _callee_first(stream: Sequence[Token], open_index: int) -> int | None:
    """Index of the first token of the dotted name calling the `(` at
    `open_index`, or None when nothing calls it.

    A keyword name is never a callee (see the module docstring): `IN (`,
    `VALUES (` and `LEFT(` are syntax, not routines the shop wrote.
    """
    last = open_index - 1
    if last < 0 or stream[last].kind not in _NAME_KINDS:
        return None
    if stream[last].kind == WORD and stream[last].is_keyword:
        return None
    first = last
    while (
        first - 2 >= 0
        and stream[first - 1].kind == PUNCT
        and stream[first - 1].text == "."
        and stream[first - 2].kind in _NAME_KINDS
    ):
        first -= 2
    return first


def _site(
    text: str,
    pos: int,
    stream: Sequence[Token],
    frame: _Frame,
    close_at: int | None,
    base: int,
) -> CallSite:
    first = frame.callee_first or 0
    last = frame.open_token - 1
    segments = [
        _identifier(tok)
        for tok in stream[first : last + 1]
        if tok.kind in _NAME_KINDS
    ]
    name = segments[-1] if segments else ""
    schema = segments[-2] if len(segments) >= 2 else None

    end_of_args = close_at if close_at is not None else len(text)
    ends = list(frame.comma_ends) + [end_of_args]
    arguments = tuple(
        Argument(index, *_trim(text, start, end))
        for index, (start, end) in enumerate(zip(frame.boundaries, ends))
    )

    active = sum(1 for comma_end in frame.boundaries[1:] if comma_end <= pos)
    active = max(0, min(active, len(arguments) - 1)) if arguments else 0

    return CallSite(
        ok=True,
        callee=text[stream[first].start : stream[last].end],
        schema=schema,
        name=name,
        name_start=base + stream[first].start,
        name_end=base + stream[last].end,
        open_paren=base + frame.open_end - 1,
        close_paren=None if close_at is None else base + close_at,
        arguments=tuple(
            Argument(arg.index, arg.start + base, arg.end + base)
            for arg in arguments
        ),
        argument_index=active,
        in_literal=_in_opaque(stream, pos),
    )


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """`(start, end)` with surrounding whitespace removed (empty stays empty)."""
    end = max(start, end)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _in_opaque(stream: Sequence[Token], pos: int) -> bool:
    """Whether `pos` sits strictly inside a string / comment / quoted name."""
    return any(tok.is_opaque and tok.start < pos < tok.end for tok in stream)


def _identifier(tok: Token) -> str:
    """A name token's identifier text: `"Quoted"` unwrapped, else verbatim."""
    if tok.kind == QUOTED_IDENT and len(tok.text) >= 2 and tok.text.startswith('"'):
        inner = tok.text[1:-1] if tok.text.endswith('"') else tok.text[1:]
        return inner.replace('""', '"')
    return tok.text


def _help(
    site: CallSite, signatures: Iterable[RoutineSignature]
) -> SignatureHelp:
    matching = [
        signature for signature in signatures if _name_matches(site, signature)
    ]
    if not matching:
        return SignatureHelp(
            reason=f"no known routine is named {site.qualified}",
            callee=site.callee,
            active_parameter=site.argument_index,
            argument_count=site.argument_count,
        )

    index = site.argument_index
    written = site.argument_count
    ranked = sorted(
        matching,
        key=lambda signature: (
            0 if signature.accepts(index) else 1,
            abs(len(signature.parameters) - written),
            len(signature.parameters),
            signature.name.lower(),
        ),
    )
    return SignatureHelp(
        ok=True,
        callee=site.callee,
        signatures=tuple(ranked),
        active_signature=0,
        active_parameter=index,
        argument_count=written,
    )


def _name_matches(site: CallSite, signature: RoutineSignature) -> bool:
    """Whether `signature` is a routine the caret's call could be naming.

    Case-insensitive, like every identifier comparison in the completion
    machinery (§18.6). A bare call matches on the bare name (no search path is
    guessed -- offering every schema's `calc` is the honest answer and the
    caller can narrow it); a schema-qualified call must match the schema too,
    unless the injected signature carries none.
    """
    if site.name.lower() != signature.bare_name.lower():
        return False
    if not site.schema or signature.schema is None:
        return True
    return site.schema.lower() == signature.schema.lower()
