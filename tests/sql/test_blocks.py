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

    **Both halves of the guard are live now (BUG-260810194657).** They did not use
    to be: the phrase half matched through `Token.keyword`, which is non-None only
    for members of `sql/keywords.py::SQL_KEYWORDS`, and neither `transaction` nor
    `work` is a member -- so `BEGIN TRANSACTION; ... COMMIT;` opened a plpgsql
    frame that `COMMIT` could not close and the formatter *refused valid SQL*,
    while the bare-`BEGIN;` spelling of the same statement formatted fine.

    The fix matches the phrase on `Token.lowered`, and `SQL_KEYWORDS` was
    deliberately **not** widened: it drives `Token.keyword`, which the formatter
    reads for call-paren gluing and unary minus (`select work(1)` would become
    `select work (1)`, `select t.work - 1` would become `select t.work -1`), and it
    is shared *by identity* with the editor's highlighter, so a column named `work`
    would paint as a keyword app-wide. That is the `declare_is_cursor` precedent
    below -- `cursor` is absent from the set too.
    """
    assert blocks.begin_is_transaction(items("begin;"), 0) is True
    text = "begin\nx := 1;\nend;"
    assert blocks.begin_is_transaction(items(text), index_of(text, "begin")) is False

    # The half that used to be dormant, and is not any more.
    assert blocks.begin_is_transaction(items("begin transaction;"), 0) is True
    assert blocks.begin_is_transaction(items("begin work;"), 0) is True
    assert blocks.begin_is_transaction(items("begin transaction"), 0) is True  # end of input
    assert (
        blocks.begin_is_transaction(items("begin transaction isolation level serializable;"), 0)
        is True
    )
    # The noise word may be omitted: the mode list can follow `BEGIN` directly.
    assert blocks.begin_is_transaction(items("begin isolation level serializable;"), 0) is True
    assert blocks.begin_is_transaction(items("begin read only;"), 0) is True
    assert blocks.begin_is_transaction(items("begin read write;"), 0) is True
    assert blocks.begin_is_transaction(items("begin not deferrable;"), 0) is True
    assert blocks.begin_is_transaction(items("begin deferrable;"), 0) is True


def test_a_block_whose_first_statement_assigns_to_work_is_still_a_block():
    """The false positive the `Token.keyword` accident was accidentally suppressing.

    Matching the phrase on `lowered` *alone* would read `BEGIN work := 1; END;` --
    a plpgsql block assigning to a variable named `work` -- as transaction control,
    and the formatter would then swallow the real `END;` as a `COMMIT` synonym,
    silently dropping a block frame. That is worse than the bug being fixed, so the
    phrase is only believed when what follows it is a `;`, the end of the input, or
    a transaction mode word. `:=` is none of those.
    """
    for text in ("begin\nwork := 1;\nend;", "begin\ntransaction := 1;\nend;"):
        assert blocks.begin_is_transaction(items(text), index_of(text, "begin")) is False
    # Same shape one token further out: a mode HEAD used as a variable name.
    for text in ("begin\nread := 1;\nend;", "begin\nisolation := 1;\nend;"):
        assert blocks.begin_is_transaction(items(text), index_of(text, "begin")) is False
    # And a block that simply starts with a call, whose first token is a word.
    text = "begin\nperform f();\nend;"
    assert blocks.begin_is_transaction(items(text), index_of(text, "begin")) is False


def test_the_begin_phrase_tables_carry_no_dead_entries():
    """A dead table is what produced BUG-260810194657 -- keep them separated by role."""
    assert blocks.BEGIN_NOT_BLOCK_FOLLOWERS == {"transaction", "work"}
    assert "isolation" in blocks.BEGIN_TRANSACTION_MODE_HEADS  # a mode head, not a noise word
    # Every mode head may also continue a mode list (`READ ONLY, READ WRITE`), so
    # the heads are a subset -- if they ever diverge, one of the two is unreachable.
    assert blocks.BEGIN_TRANSACTION_MODE_HEADS <= blocks.BEGIN_TRANSACTION_MODE_WORDS


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


def test_next_lowered_sees_phrase_words_that_next_keyword_cannot():
    """The reason the helper exists: a phrase word need not be a dialect keyword.

    `transaction`, `work` and `cursor` are all absent from `SQL_KEYWORDS` (and must
    stay absent -- see `test_transaction_begin_is_told_apart_from_a_plpgsql_begin`),
    so `Token.keyword` is None for them while `next_lowered` reads them fine.
    """
    item_list = items("BEGIN Transaction;")
    assert blocks.next_keyword(item_list, 0) is None
    assert blocks.next_lowered(item_list, 0) == "transaction"  # case-folded
    # Punctuation and literals are not words: a phrase word is a word.
    assert blocks.next_lowered(item_list, 1) is None  # the `;`
    assert blocks.next_lowered(items("select 'Work'"), 0) is None  # a string literal
    # Bounds-safe in both directions, like `next_keyword`.
    assert blocks.next_lowered(item_list, 2) is None
    assert blocks.next_lowered(item_list, 0, offset=-5) is None
    assert blocks.next_lowered(item_list, 0, offset=0) == "begin"
