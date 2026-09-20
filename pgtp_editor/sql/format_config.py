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

# pgtp_editor/sql/format_config.py
"""The SQL formatter's configuration -- a DELIBERATELY BOUNDED space (§18.4 A+B).

`FormatConfig` is everything the formatter can be told to do. It lives here, in
the Qt-free core, rather than in `ui/`, because the engine must never read
`QSettings` (§5's dependency rule, pinned by
`tests/sql/test_package_purity.py`); `ui/format_settings.py` owns persistence
and hands a finished `FormatConfig` in.

WHY THE SPACE IS SMALL, AND WHY THAT IS THE FEATURE
---------------------------------------------------
§18.4's hard design constraint: **the reachable config space must be small
enough that idempotence is provable by inspection, not merely tested.** A
formatter whose output is not a fixed point of its own rules is worse than an
unconfigurable one, because the damage shows up only on the second invocation.
So exactly four things are settable -- the indent unit, keyword casing, a
per-clause-starter break/indent pair, and the JOIN-phrase break -- and every one
of them is a bounded scalar. There is no rule language, no free text, no
predicate, and no way to reach the rules §18.4 fixes on purpose:

* the break after a `--` line comment (a flag there silently comments out code),
* the break after `;`,
* the `DECLARE`-header break and every guard decided BY LAYOUT (pass 1 would
  emit text pass 2 reads as a different construct -- idempotence would fail in
  the one way that also produces a refusal),
* the breaks before block keywords and the two-token `END IF`/`END LOOP`/
  `END CASE` closers (they are what the balance walk reads),
* author-newline preservation, the one-blank-line cap, leading-comma survival,
  the CASE-body-on-the-`then`-line rule and every glue rule,
* the refusal gate -- no configuration makes the formatter accept unbalanced
  input.

LENIENCY LIVES IN ONE PLACE
---------------------------
`FormatConfig.sanitized()` clamps out-of-range values and drops unknown clause
keywords **silently**, and it is the only gate that does so. §18.4 states the
reason this is not the app's usual "never overwrite what you could not read"
posture: nothing can be lost -- a formatter preference is re-derivable from the
dialog in ten seconds -- so refusing to load would be ceremony. Loading never
raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping

#: One indent level. Lives here (not in `formatter.py`) so `FormatConfig` can
#: default to it without importing the engine it configures.
DEFAULT_INDENT_UNIT = "    "

#: Clause keywords that start a new line (plain-SQL clause structure). The
#: per-clause break/indent grid is keyed by exactly these -- the set is
#: *engine-owned*, never frozen into a user's saved config, so adding a member
#: later needs no migration of anybody's settings (§18.4 B, consequence 1).
CLAUSE_STARTERS = frozenset(
    """
    select from where group having order limit offset union except intersect
    join on values set returning with
    """.split()
)

#: `indent_unit` is a width of spaces or a single tab -- nothing else.
MIN_INDENT_WIDTH = 1
MAX_INDENT_WIDTH = 8

#: A clause starter may be pushed 0..4 levels right of its own frame level.
MIN_CLAUSE_INDENT_LEVELS = 0
MAX_CLAUSE_INDENT_LEVELS = 4

#: Part C's XML indent width is bounded by the same MIN/MAX pair, but its
#: DEFAULT lives with its own engine (`xmlfmt/config.py`, two spaces because §2
#: fixes the on-disk `.pgtp` indentation unit at two spaces). Two engines, two
#: defaults, one set of bounds.


class KeywordCase(str, Enum):
    """What Format Selection does to keyword tokens (§18.4 A).

    `AS_IS` is the default and is **byte-identical to the pre-FQ-033 engine**:
    nobody's formatting changes until they ask for it.

    A `str` Enum on purpose: the value doubles as the persisted token, so
    `ui/format_settings.py` writes `"as-is"` rather than an int nobody can read
    in the ini file.
    """

    AS_IS = "as-is"
    UPPER = "upper"
    LOWER = "lower"

    @classmethod
    def parse(cls, value: object) -> "KeywordCase":
        """Lenient read: anything unrecognized becomes `AS_IS` (never raises)."""
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower() if value is not None else ""
        for member in cls:
            if text == member.value:
                return member
        return cls.AS_IS


@dataclass(frozen=True)
class ClauseRule:
    """One clause starter's layout: does it break, and how far is it pushed.

    `indent_levels` is relative to the clause's **own frame level**; the
    clause-continuation `+1` rule is unchanged by it and is not per keyword.
    """

    break_before: bool = True
    indent_levels: int = 0

    def sanitized(self) -> "ClauseRule":
        levels = self.indent_levels
        if not isinstance(levels, int) or isinstance(levels, bool):
            try:
                levels = int(levels)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                levels = MIN_CLAUSE_INDENT_LEVELS
        levels = max(MIN_CLAUSE_INDENT_LEVELS, min(MAX_CLAUSE_INDENT_LEVELS, levels))
        return ClauseRule(break_before=bool(self.break_before), indent_levels=levels)


#: The rule every clause starter has unless the config overrides it -- i.e.
#: today's shipped behaviour: break, no extra indent.
DEFAULT_CLAUSE_RULE = ClauseRule()


def indent_unit_for(width: int, use_tab: bool = False) -> str:
    """The `indent_unit` string for a bounded width / tab choice.

    One tab is one level (`width` is then irrelevant), which is why the dialog
    offers "tab" as a kind rather than as a ninth width.
    """
    if use_tab:
        return "\t"
    try:
        value = int(width)
    except (TypeError, ValueError):
        value = len(DEFAULT_INDENT_UNIT)
    value = max(MIN_INDENT_WIDTH, min(MAX_INDENT_WIDTH, value))
    return " " * value


@dataclass(frozen=True)
class FormatConfig:
    """The whole SQL formatter configuration, one object.

    `clause_rules` is **SPARSE**: it holds only the keywords that DIFFER from
    `DEFAULT_CLAUSE_RULE`, and a key absent from it means "the shipped rule".
    That is what keeps a saved config from freezing the keyword set (§18.4 B).
    """

    indent_unit: str = DEFAULT_INDENT_UNIT
    keyword_case: KeywordCase = KeywordCase.AS_IS
    clause_rules: Mapping[str, ClauseRule] = field(default_factory=dict)
    join_phrase_break: bool = True

    # -- reads the engine makes -------------------------------------------
    def rule_for(self, keyword: str) -> ClauseRule:
        """The rule for `keyword`, falling back to the shipped default."""
        return self.clause_rules.get(keyword, DEFAULT_CLAUSE_RULE)

    def case_of(self, text: str) -> str:
        """Apply `keyword_case` to one keyword token's verbatim text.

        Called at token emit and *only* for tokens the tokenizer already
        classified as keywords (`Token.keyword is not None`), which is why this
        function needs no set membership test of its own: identifiers, built-in
        types/functions, literals and every opaque region are never routed here.
        """
        if self.keyword_case is KeywordCase.UPPER:
            return text.upper()
        if self.keyword_case is KeywordCase.LOWER:
            return text.lower()
        return text

    # -- properties the dialog reads --------------------------------------
    @property
    def uses_tab(self) -> bool:
        return self.indent_unit == "\t"

    @property
    def indent_width(self) -> int:
        """The space width, or the default width when the unit is a tab."""
        if self.uses_tab:
            return len(DEFAULT_INDENT_UNIT)
        return len(self.indent_unit) or len(DEFAULT_INDENT_UNIT)

    # -- the single leniency gate -----------------------------------------
    def sanitized(self) -> "FormatConfig":
        """A copy with every value inside its documented domain.

        Unknown clause keywords are dropped, out-of-range numbers clamped, an
        unrecognized casing token read as `AS_IS`, and a nonsense indent unit
        replaced by the default. Never raises -- see the module docstring for
        why silence is right here specifically.
        """
        unit = self.indent_unit
        if unit == "\t":
            pass
        elif isinstance(unit, str) and unit and unit.strip(" ") == "":
            unit = indent_unit_for(len(unit))
        else:
            unit = DEFAULT_INDENT_UNIT
        rules = {
            keyword: rule.sanitized()
            for keyword, rule in (self.clause_rules or {}).items()
            if keyword in CLAUSE_STARTERS and isinstance(rule, ClauseRule)
        }
        # Sparse means sparse: an entry equal to the default carries no
        # information and would otherwise pin the keyword into saved settings.
        rules = {k: v for k, v in rules.items() if v != DEFAULT_CLAUSE_RULE}
        return replace(
            self,
            indent_unit=unit,
            keyword_case=KeywordCase.parse(self.keyword_case),
            clause_rules=rules,
            join_phrase_break=bool(self.join_phrase_break),
        )


#: Today's shipped behaviour, exactly: four spaces, no casing, every clause
#: starter breaking with no extra indent, the JOIN phrase breaking.
DEFAULT_FORMAT_CONFIG = FormatConfig()
