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

# pgtp_editor/vim/grammar.py
"""The Command-mode command GRAMMAR -- pure, Qt-free, document-free (FQ-032, §8).

**Why this is a package and not a widget method.** The pending-state machine
--*"digits, then optionally an operator, then a motion or a doubled operator"*--
is the most testable part of the feature and the part most likely to be got
subtly wrong, so it does not live in a widget. It takes keystrokes and returns a
resolved :class:`Command` (count, operator, motion, target, action) and **knows
nothing about Qt, about documents, or about which editor it serves**. The Qt half
-- turning a resolved command into `QTextCursor` work -- is
`ui/vim_mode.py::VimModeMixin`.

**Terminology.** The two editing modes are **Edit mode** (ordinary Windows-style
typing) and **Command mode** (the `Esc`-entered state this grammar parses). The
word *"normal"* is not used anywhere in this feature: it collides with vim's own
NORMAL and would make every sentence ambiguous about which vocabulary it speaks.

**No registers.** There is one shared SYSTEM clipboard, so a resolved command
carries no register field and there is nothing here to hold one.

**No visual mode.** `v` / `V` are insert-entry aliases (the user selects the
Windows-native way), so there is no selection state in this machine either.

The v1 vocabulary, exactly:

* **motions** -- ``h j k l`` · ``w b e`` · ``0 ^ $`` · ``gg G`` · ``NG`` ·
  ``f t F T`` · ``%`` · ``{ }``
* **counts** -- ``N{motion}``, and ``N`` before or after an operator (they
  multiply, as in vim: ``2d3w`` is ``d6w``)
* **operators** -- ``d`` ``c`` ``y`` + motion, the doubled ``dd yy cc``, and the
  shorthands ``x X D C Y s S`` which resolve to operator+motion pairs here
  rather than as separate actions in the widget
* **actions** -- the insert-entry keys ``i a I A o O v V``, ``p`` ``P``,
  ``r{char}``, ``u``, ``Ctrl-R`` (fed as :data:`REDO_KEY`), ``n`` ``N``, ``/``
  and ``:``

Anything else resets the machine and resolves to nothing: a half-typed command
that cannot be completed is discarded rather than guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The token the widget feeds for `Ctrl-R` (Command-mode-only redo,
#: `DEC-260810193638`). Spelled as a multi-character token so it can never
#: collide with a bare letter the user typed.
REDO_KEY = "<C-r>"

#: vim's own linewise motion, and the motion a doubled operator (`dd`, `yy`,
#: `cc`) and `Y` / `S` resolve to. Using vim's spelling rather than inventing a
#: `linewise: bool` flag keeps the resolved command one shape.
LINEWISE = "_"

#: The three operators. `x X D C Y s S` are shorthands for pairs of these and a
#: motion, resolved here so the widget has one code path per operator.
OPERATORS = frozenset("dcy")

#: Motions that need no further keystroke.
SIMPLE_MOTIONS = frozenset({"h", "j", "k", "l", "w", "b", "e", "0", "^", "$", "G", "gg", "%", "{", "}"})

#: Motions that take one more keystroke: the character to search the line for.
CHAR_MOTIONS = frozenset("ftFT")

#: Motions vim treats as INCLUSIVE of the character they land on when an
#: operator consumes them. `$` is deliberately absent: it resolves to the
#: position *after* the last character, so it is already an exclusive end.
INCLUSIVE_MOTIONS = frozenset({"e", "f", "t", "%"})

#: The keys that leave Command mode for Edit mode without touching the buffer.
#: `v` / `V` are in here because **there is no visual mode**: they drop to Edit
#: mode so the user selects the Windows-native way (owner: selection is a
#: Windows method).
INSERT_ENTRY_ACTIONS = frozenset({"i", "a", "I", "A", "o", "O", "v", "V"})

#: Operator shorthands: key -> (operator, motion).
_SHORTHANDS = {
    "x": ("d", "l"),
    "X": ("d", "h"),
    "D": ("d", "$"),
    "C": ("c", "$"),
    "Y": ("y", LINEWISE),
    "s": ("c", "l"),
    "S": ("c", LINEWISE),
}

#: Actions that are neither motions nor operators. `u` / `redo` route to the
#: surface's own undo answer; `search` / `find-next` / `find-previous` route to
#: the app's EXISTING Find bar (no second search engine); `palette` opens the
#: `:` command line, whose namespace is the app's own menu tree.
_ACTIONS = {
    "p": "p",
    "P": "P",
    "u": "u",
    REDO_KEY: "redo",
    "n": "find-next",
    "N": "find-previous",
    "/": "search",
    ":": "palette",
}


@dataclass(frozen=True)
class Command:
    """One resolved Command-mode command.

    Exactly one of :attr:`action`, :attr:`operator` and :attr:`motion` decides
    what the widget does with it, in that order of precedence:

    * ``action`` set -- a standalone gesture (`i`, `p`, `u`, `r`, `/`, `:` ...).
      `r` carries the replacement character in :attr:`target`.
    * ``operator`` set -- `d` / `c` / `y` over the range :attr:`motion` names.
    * ``motion`` only -- move the caret.
    """

    count: int = 1
    operator: str | None = None
    motion: str | None = None
    target: str | None = None
    action: str | None = None
    #: Whether the user actually TYPED a count. `G` and `42G` are different
    #: commands (last line vs line 42) and `count == 1` cannot tell them apart,
    #: so the fact that a count was given is carried rather than inferred.
    has_count: bool = False

    @property
    def is_linewise(self) -> bool:
        """Whether the operator's range is whole lines (`dd`, `yy`, `cc`, `Y`, `S`)."""
        return self.motion == LINEWISE

    @property
    def is_inclusive(self) -> bool:
        """Whether an operator consuming this motion includes the character it
        lands on (vim's inclusive/exclusive distinction)."""
        return self.motion in INCLUSIVE_MOTIONS


class VimGrammar:
    """The pending-state machine: feed it keys, get :class:`Command`s back.

    :meth:`feed` returns a resolved command, or ``None`` when the machine is
    either **waiting for more input** (:attr:`is_pending` is then True) or has
    **discarded** an input it cannot use (:attr:`is_pending` is then False).
    Distinguishing the two is the caller's business only for display; either
    way the keystroke has been consumed by Command mode.

    `Esc` is not fed here. It is answered by the widget, which calls
    :meth:`reset` -- one reset path, exactly as the mode itself has one.
    """

    def __init__(self) -> None:
        self.reset()

    # -- state --------------------------------------------------------------
    def reset(self) -> None:
        """Discard every half-typed command. Idempotent."""
        self._pre_count = ""
        self._post_count = ""
        self._operator: str | None = None
        self._pending_g = False
        self._pending_char: str | None = None

    @property
    def is_pending(self) -> bool:
        """Whether a command is half-typed (`42`, `d`, `d2`, `g`, `f`)."""
        return bool(
            self._pre_count
            or self._post_count
            or self._operator is not None
            or self._pending_g
            or self._pending_char is not None
        )

    @property
    def pending_text(self) -> str:
        """The half-typed command, for a display that wants to echo it."""
        parts = [self._pre_count]
        if self._operator:
            parts.append(self._operator)
        parts.append(self._post_count)
        if self._pending_g:
            parts.append("g")
        if self._pending_char:
            parts.append(self._pending_char)
        return "".join(parts)

    # -- parsing ------------------------------------------------------------
    def feed(self, key: str) -> Command | None:
        """Consume one keystroke; return a resolved command or None."""
        if self._pending_char is not None:
            return self._resolve_char_target(key)
        if self._pending_g:
            self._pending_g = False
            if key == "g":
                return self._resolve_motion("gg")
            self.reset()
            return None
        if self._is_count_digit(key):
            if self._operator is None:
                self._pre_count += key
            else:
                self._post_count += key
            return None
        if key == "g":
            self._pending_g = True
            return None
        if key in OPERATORS:
            return self._feed_operator(key)
        if key in CHAR_MOTIONS:
            self._pending_char = key
            return None
        if key == "r":
            if self._operator is not None:
                self.reset()  # `dr` is not a command; discard rather than guess
                return None
            self._pending_char = "r"
            return None
        if key in SIMPLE_MOTIONS:
            return self._resolve_motion(key)
        if key in _SHORTHANDS or key in INSERT_ENTRY_ACTIONS or key in _ACTIONS:
            if self._operator is not None:
                self.reset()  # an operator followed by a non-motion: discard
                return None
            return self._resolve_standalone(key)
        self.reset()
        return None

    # -- internals ----------------------------------------------------------
    def _is_count_digit(self, key: str) -> bool:
        """`0` starts no count -- bare `0` is the start-of-line MOTION, and
        `d0` deletes to it. It is a digit only once a count is under way."""
        if key not in "0123456789":
            return False
        if key != "0":
            return True
        buffer = self._post_count if self._operator is not None else self._pre_count
        return bool(buffer)

    def _count(self) -> int:
        pre = int(self._pre_count) if self._pre_count else 1
        post = int(self._post_count) if self._post_count else 1
        return pre * post

    def _has_count(self) -> bool:
        return bool(self._pre_count or self._post_count)

    def _feed_operator(self, key: str) -> Command | None:
        if self._operator == key:
            command = Command(
                count=self._count(),
                operator=key,
                motion=LINEWISE,
                has_count=self._has_count(),
            )
            self.reset()
            return command
        if self._operator is not None:
            self.reset()  # `dy` is not a command
            return None
        self._operator = key
        return None

    def _resolve_motion(self, motion: str, target: str | None = None) -> Command:
        command = Command(
            count=self._count(),
            operator=self._operator,
            motion=motion,
            target=target,
            has_count=self._has_count(),
        )
        self.reset()
        return command

    def _resolve_char_target(self, key: str) -> Command | None:
        pending = self._pending_char
        self._pending_char = None
        if len(key) != 1 or not key.isprintable():
            self.reset()
            return None
        if pending == "r":
            command = Command(
                count=self._count(),
                action="r",
                target=key,
                has_count=self._has_count(),
            )
            self.reset()
            return command
        return self._resolve_motion(pending, target=key)

    def _resolve_standalone(self, key: str) -> Command:
        count = self._count()
        has_count = self._has_count()
        self.reset()
        if key in _SHORTHANDS:
            operator, motion = _SHORTHANDS[key]
            return Command(
                count=count, operator=operator, motion=motion, has_count=has_count
            )
        if key in INSERT_ENTRY_ACTIONS:
            return Command(count=count, action=key, has_count=has_count)
        return Command(count=count, action=_ACTIONS[key], has_count=has_count)
