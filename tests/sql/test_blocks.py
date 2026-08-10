# tests/sql/test_blocks.py
"""`sql/blocks.py` -- the lifted plpgsql block-balance rules (FQ-034, §8).

The point of this module is that ONE rule set serves two consumers, so most of
what is worth asserting is *identity*: `formatter.py` must read the very same
objects, not equal copies. A copy would pass an equality test and then drift.
"""
from __future__ import annotations

from pgtp_editor.sql import blocks, formatter
from pgtp_editor.sql.tokenizer import tokenize


def items(text: str):
    return blocks.significant_tokens(tokenize(text))


def index_of(text: str, keyword: str) -> int:
    """Index into `items(text)` of the first token spelling `keyword`."""
    for position, (tok, _newlines) in enumerate(items(text)):
        if tok.lowered == keyword:
            return position
    raise AssertionError(f"{keyword!r} not in {text!r}")


# --------------------------------------------------------------------------
# the lift itself
# --------------------------------------------------------------------------


def test_formatter_reads_the_very_same_rule_objects_not_copies():
    """A plain re-bind, exactly as FQ-033 did for `CLAUSE_STARTERS`.

    `is` and not `==`: two equal frozensets would let one consumer's rule change
    without the other's, which is the fork this module exists to prevent.
    """
    assert formatter._BLOCK_STARTERS is blocks.BLOCK_STARTERS
    assert formatter._LOOP_STARTERS is blocks.LOOP_STARTERS
    assert formatter._IF_NOT_BLOCK_FOLLOWERS is blocks.IF_NOT_BLOCK_FOLLOWERS
    assert formatter._BEGIN_NOT_BLOCK_FOLLOWERS is blocks.BEGIN_NOT_BLOCK_FOLLOWERS
    assert formatter._SOFT_FRAMES is blocks.SOFT_FRAMES
    assert formatter._BLOCK_FRAMES is blocks.BLOCK_FRAMES
    assert formatter._UNMATCHED_BLOCK_HINT is blocks.UNMATCHED_BLOCK_HINT
    assert formatter._significant is blocks.significant_tokens


def test_blocks_never_imports_the_engine_it_configures():
    """A rules module must not import the engine that reads it (§5's arrow).

    Checked on the module object rather than by reading the source, so an
    indirect import through another `sql/` module would fail too.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path(blocks.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("formatter" in name for name in imported), imported


def test_the_two_token_closers_are_exactly_end_if_end_loop_end_case():
    assert blocks.BLOCK_CLOSERS == {"end"}
    assert blocks.TWO_TOKEN_CLOSERS == {"if", "loop", "case"}
    assert blocks.end_closes("if") == "if"
    assert blocks.end_closes("loop") == "loop"
    assert blocks.end_closes("case") == "case"
    # A bare END names nothing: it closes a BEGIN or a CASE expression, and the
    # caller decides which -- so this must be None, never a guess.
    assert blocks.end_closes(None) is None
    assert blocks.end_closes("if_not_a_closer") is None


def test_openers_are_the_four_balance_relevant_keywords():
    assert blocks.BLOCK_OPENERS == {"begin", "if", "loop", "case"}
    assert blocks.BLOCK_FRAMES == blocks.BLOCK_OPENERS
    # `declare`/`when`/`exception` are soft: they indent and they can be
    # selected, but they never make text unbalanced.
    assert blocks.SOFT_FRAMES == {"declare", "when", "exception"}
    assert not blocks.SOFT_FRAMES & blocks.BLOCK_FRAMES


# --------------------------------------------------------------------------
# the six false-positive guards
# --------------------------------------------------------------------------


def test_if_exists_is_a_modifier_but_a_real_if_is_not():
    text = "drop table if exists t;"
    assert blocks.if_is_modifier(items(text), index_of(text, "if")) is True
    text = "drop table if not exists t;"
    assert blocks.if_is_modifier(items(text), index_of(text, "if")) is True
    text = "if a then x := 1; end if;"
    assert blocks.if_is_modifier(items(text), index_of(text, "if")) is False


def test_transaction_begin_is_told_apart_from_a_plpgsql_begin():
    """`BEGIN;` is transaction control; `BEGIN` followed by a body is a block.

    **Pinned as-is, including a limitation this lift did NOT change.**
    `BEGIN TRANSACTION` / `BEGIN WORK` are matched through `Token.keyword`, which
    is non-None only for members of `sql/keywords.py::SQL_KEYWORDS` -- and neither
    `transaction` nor `work` is a member, so `BEGIN_NOT_BLOCK_FOLLOWERS` never
    fires for them and only the `;` half of the guard is live. That was already
    true of `_Reindenter` before the rules moved here; this test records it rather
    than silently "fixing" it, because widening `SQL_KEYWORDS` would change the
    formatter's indentation and refusal verdicts, which is not FQ-034's business.
    """
    assert blocks.begin_is_transaction(items("begin;"), 0) is True
    text = "begin\nx := 1;\nend;"
    assert blocks.begin_is_transaction(items(text), index_of(text, "begin")) is False
    # The dormant half, asserted as dormant so the day it is fixed this test says so.
    assert blocks.begin_is_transaction(items("begin transaction;"), 0) is False


def test_a_bare_loop_opens_but_the_loop_in_end_loop_closes():
    text = "loop exit when done; end loop;"
    item_list = items(text)
    first = index_of(text, "loop")
    assert blocks.loop_opens_block(item_list, first, prev_keyword=None) is True
    # The second `loop` is the one in `END LOOP`, and the previous keyword is
    # the whole guard -- which is why it is a parameter rather than re-derived.
    assert blocks.loop_opens_block(item_list, first + 4, prev_keyword="end") is False


def test_declare_section_and_declare_cursor_are_told_apart_by_layout():
    section = "declare\nx int;\nbegin\nx := 1;\nend;"
    assert blocks.declare_is_cursor(items(section), index_of(section, "declare")) is False
    statement = "declare c cursor for select 1;"
    assert blocks.declare_is_cursor(items(statement), index_of(statement, "declare")) is True


def test_when_opens_a_branch_only_inside_a_case_or_an_exception_part():
    assert blocks.when_opens_branch("case", in_exception=False) is True
    assert blocks.when_opens_branch("begin", in_exception=True) is True
    # `EXIT WHEN done` / `RAISE ... WHEN` sit directly in a LOOP or a BEGIN with
    # no exception part -- the two false positives this guard exists for.
    assert blocks.when_opens_branch("loop", in_exception=False) is False
    assert blocks.when_opens_branch("begin", in_exception=False) is False
    assert blocks.when_opens_branch(None, in_exception=False) is False


def test_significant_tokens_drops_whitespace_and_counts_newlines():
    stream = blocks.significant_tokens(tokenize("a\n\n  b"))
    assert [(tok.text, newlines) for tok, newlines in stream] == [("a", 0), ("b", 2)]


def test_next_keyword_and_next_token_are_bounds_safe():
    item_list = items("select 1")
    assert blocks.next_keyword(item_list, 0) is None  # `1` is a number, not a keyword
    assert blocks.next_keyword(item_list, 1) is None  # off the end
    assert blocks.next_token(item_list, 1) is None
    assert blocks.next_token(item_list, 0).text == "1"
