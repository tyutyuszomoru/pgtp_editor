# tests/sql/test_block_spans.py
"""`sql/block_spans.py` -- the structural span model behind §8's ladder (FQ-034).

Three things are worth pinning here, and the third is the one a comment could
never have kept true:

1. **The chain**, smallest-first, with `inner`/`outer` per member -- the shape
   FQ-032's deferred text objects need, not a `next_larger` step function.
2. **The ladder's rung policy** -- inner-before-outer for a bracket group, the
   SPARSE clause rung, the derive-with-no-stack rule and why it is a no-op at the
   innermost span *without a special case*.
3. **The anti-fork guard** -- `sql/blocks.py`'s rules feed both this module and
   `formatter.py::_Reindenter`, so §18.4's adversarial corpus is pushed through
   BOTH and the block nesting they find is asserted equal.
"""
from __future__ import annotations

import pytest

from pgtp_editor.sql import block_spans, formatter
from pgtp_editor.sql.block_spans import (
    StructureSpan,
    expand_target,
    ladder_candidates,
    shrink_target,
    structure_chain,
)
from pgtp_editor.sql.blocks import significant_tokens
from pgtp_editor.sql.format_config import DEFAULT_FORMAT_CONFIG
from pgtp_editor.sql.tokenizer import tokenize
from tests.sql.test_formatter import SAMPLES

_BODY = """CREATE FUNCTION f() RETURNS int AS $$
DECLARE
    total int := 0;
BEGIN
    FOR r IN SELECT id FROM t WHERE id > 0 LOOP
        IF r.id > 5 THEN
            total := total + r.id;
        END IF;
    END LOOP;
    CASE total
        WHEN 1 THEN RAISE NOTICE 'one';
        ELSE RAISE NOTICE 'many';
    END CASE;
    RETURN total;
END
$$ LANGUAGE plpgsql;
"""


def chain_at(text: str, marker: str, offset: int = 0):
    return structure_chain(text, text.index(marker) + offset)


def texts(text: str, spans) -> list[str]:
    return [text[span.outer[0] : span.outer[1]] for span in spans]


def rungs(text: str, marker: str, offset: int = 0) -> list[str]:
    """The ranges one press each selects, as their text, smallest first."""
    candidates = ladder_candidates(chain_at(text, marker, offset))
    return [text[start:end] for start, end in candidates]


# --------------------------------------------------------------------------
# the chain's shape
# --------------------------------------------------------------------------


def test_the_chain_is_smallest_first_strictly_nested_and_depth_numbered():
    chain = chain_at(_BODY, "total + r.id")
    assert [span.kind for span in chain] == [
        "word",
        "statement",
        "if",
        "loop",
        "begin",
        "dollar_body",
        "statement",
    ]
    # Strictly nested, and `depth` counts inward from 0 at the outermost member.
    for inner, outer in zip(chain, chain[1:]):
        assert outer.outer[0] <= inner.outer[0] and outer.outer[1] >= inner.outer[1]
        assert outer.outer != inner.outer
    assert [span.depth for span in chain] == [6, 5, 4, 3, 2, 1, 0]


def test_every_member_carries_both_an_inner_and_an_outer_range():
    """FQ-032's `i(` / `a(` distinction is exactly this pair, which is why the
    published entry point is a chain and not a step function."""
    chain = chain_at("select coalesce(b, c) from t;", "b,")
    paren = next(span for span in chain if span.kind == "paren")
    assert isinstance(paren, StructureSpan)
    text = "select coalesce(b, c) from t;"
    assert text[paren.outer[0] : paren.outer[1]] == "(b, c)"
    assert text[paren.inner[0] : paren.inner[1]] == "b, c"
    # Kinds with no delimiters answer the same question with one range.
    statement = next(span for span in chain if span.kind == "statement")
    assert statement.inner == statement.outer


def test_the_block_ladder_is_a_recursive_climb_not_five_fixed_levels():
    """An `IF` inside a `FOR` inside a `BEGIN` is three separate presses."""
    assert rungs(_BODY, "total + r.id")[:5] == [
        "total",
        "total := total + r.id",
        _BODY[_BODY.index("IF r.id") : _BODY.index("END IF;") + len("END IF")],
        _BODY[_BODY.index("LOOP\n") : _BODY.index("END LOOP;") + len("END LOOP")],
        _BODY[_BODY.index("BEGIN\n") : _BODY.rindex("END\n") + len("END")],
    ]


def test_inside_a_case_the_when_branch_comes_before_the_whole_case():
    ladder = rungs(_BODY, "'one'")
    assert ladder[1] == "RAISE NOTICE 'one'"
    assert ladder[2] == "WHEN 1 THEN RAISE NOTICE 'one';"
    assert ladder[3].startswith("CASE total") and ladder[3].endswith("END CASE")


def test_a_declare_section_is_one_span_ending_at_its_begin():
    chain = chain_at(_BODY, "total int")
    declare = next(span for span in chain if span.kind == "declare")
    assert _BODY[declare.outer[0] : declare.outer[1]] == "DECLARE\n    total int := 0;"


# --------------------------------------------------------------------------
# the rung boundaries the owner ruled on (DEC-260810164602)
# --------------------------------------------------------------------------


def test_a_bracket_group_gives_inner_first_then_outer_two_presses():
    text = "select a, coalesce(b, c) from t where a = 1;"
    assert rungs(text, "b,") == [
        "b",
        "b, c",
        "(b, c)",
        "select a, coalesce(b, c)",
        "select a, coalesce(b, c) from t where a = 1",
    ]


def test_there_is_no_parameter_rung_word_goes_straight_to_the_paren_group():
    """`DEC-260810164602`: no rung selects `p_id integer DEFAULT 0` as one unit.

    It would exist only inside a signature, so press counts would differ by
    syntactic context -- and it is the rung most easily added later, because the
    chain is a list.
    """
    text = "CREATE FUNCTION f(p_id integer DEFAULT 0) RETURNS void AS $$ $$;"
    ladder = rungs(text, "integer")
    assert ladder[0] == "integer"
    assert ladder[1] == "p_id integer DEFAULT 0"  # the paren group's INNER, not a parameter
    assert ladder[2] == "(p_id integer DEFAULT 0)"


def test_the_clause_rung_is_sparse_absent_rather_than_present_and_empty():
    """`DEC-260810164602`'s criterion: a rung may be ABSENT, never
    PRESENT-AND-EMPTY. `RAISE NOTICE '...', x;` has no clause starter to anchor
    on, so there is simply no clause member and the press goes to the statement.
    """
    with_clause = "select a from t where a = 1;"
    assert any(span.kind == "clause" for span in chain_at(with_clause, "a =")) is True

    without = "raise notice 'hi', x;"
    assert any(span.kind == "clause" for span in chain_at(without, "x;")) is False
    # And every press that DOES happen advances -- no repeat of the same range.
    ladder = rungs(without, "x;")
    assert ladder == sorted(set(ladder), key=ladder.index)


def test_a_clause_that_is_the_whole_statement_is_one_rung_not_two():
    """The dedup that keeps the sparse rule honest from the other direction: in
    `select 1` the clause and the statement are the same range, so it is one
    press, and the chain names it `statement`."""
    ladder = rungs("select 1;", "1")
    assert ladder == ["1", "select 1"]


def test_a_clause_inside_a_subselect_belongs_to_that_subselect():
    text = "select a from (select b from c where b > 0) s;"
    ladder = rungs(text, "b > 0")
    assert ladder[1] == "where b > 0"
    assert ladder[2] == "select b from c where b > 0"


# --------------------------------------------------------------------------
# opaque regions: `$$` descended into, everything else one rung
# --------------------------------------------------------------------------


def test_a_dollar_body_is_descended_into_and_is_itself_two_rungs():
    ladder = rungs(_BODY, "total + r.id")
    assert ladder[5] == _BODY[_BODY.index("DECLARE") : _BODY.rindex("END\n") + len("END")]
    assert ladder[6].startswith("$$") and ladder[6].endswith("$$")


def test_a_string_or_comment_is_ONE_rung_with_no_structure_inside_it():
    """BUG-041's rule adopted rather than re-decided: a literal has nothing to
    climb, so the whole token is a rung and the next press leaves it.

    This is also what makes the paren rung TOKEN-level: the `(` inside the string
    below is not a bracket, where `ui/code_editor.py::enclosing_bracket_span`
    (a character scan, kept for the PHP/JS tabs) would count it.
    """
    text = "raise notice 'a (b c', x;"
    chain = chain_at(text, "(b")
    assert [span.kind for span in chain] == ["word", "statement"]
    assert texts(text, chain)[0] == "'a (b c'"
    assert not any(span.kind == "paren" for span in chain)

    comment = "select a; -- a (comment\nselect b;"
    assert not any(span.kind == "paren" for span in chain_at(comment, "(comment"))


def test_nested_dollar_bodies_are_descended_into_recursively():
    text = "DO $outer$ BEGIN EXECUTE $inner$ SELECT 1 $inner$; END $outer$;"
    kinds = [span.kind for span in chain_at(text, "SELECT 1")]
    assert kinds.count("dollar_body") == 2


# --------------------------------------------------------------------------
# never raises, never guesses
# --------------------------------------------------------------------------


def test_an_unclosed_block_contributes_no_span_so_the_ladder_tops_out_lower():
    """The never-a-silent-wrong-result rule applied to a gesture that REPLACES
    the user's selection: an invented end is worse than one rung fewer."""
    text = "BEGIN\n  x := 1;\n"
    assert not any(span.kind == "begin" for span in chain_at(text, "x :="))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "-- nothing but a comment",
        "'unterminated string",
        "$$ unterminated body",
        ")))",
        "END IF;",
        "select (a",
    ],
)
def test_structure_chain_never_raises_on_broken_input(text):
    for pos in range(len(text) + 1):
        chain = structure_chain(text, pos)
        assert isinstance(chain, tuple)


def test_positions_outside_the_text_are_clamped_not_an_error():
    assert structure_chain("select 1;", -5) == structure_chain("select 1;", 0)
    assert structure_chain("select 1;", 5000) == structure_chain("select 1;", 9)


# --------------------------------------------------------------------------
# the ladder filters
# --------------------------------------------------------------------------


def test_expand_target_is_the_smallest_rung_strictly_containing_the_selection():
    text = "select a, coalesce(b, c) from t;"
    pos = text.index("b,")
    selection = (pos, pos)
    seen = []
    for _ in range(6):
        target = expand_target(structure_chain(text, selection[0]), selection)
        if target is None:
            break
        selection = target
        seen.append(text[selection[0] : selection[1]])
    assert seen == ["b", "b, c", "(b, c)", "select a, coalesce(b, c)", "select a, coalesce(b, c) from t"]
    # Nothing larger left -> None, which the caller answers with a NO-OP rather
    # than a refusal: selecting mutates nothing (§8).
    assert expand_target(structure_chain(text, selection[0]), selection) is None


def test_shrink_with_no_stack_takes_the_largest_span_strictly_inside():
    text = "select a, coalesce(b, c) from t;"
    whole = (0, len(text) - 1)
    target = shrink_target(structure_chain(text, 1), whole)
    assert text[target[0] : target[1]] == "select a, coalesce(b, c)"


def test_deriving_IS_a_no_op_at_the_innermost_span_with_no_special_case():
    """`DEC-260810164601`'s deciding property: SUBSUMPTION.

    The conservative alternative was "with no stack, do nothing". Deriving
    *contains* it wherever that one is right -- at the innermost rung there is
    nothing strictly inside the selection, so `shrink_target` returns None on its
    own. Asserted here at EVERY structural position in a real routine body, so
    the claim is proved rather than argued: no branch in `shrink_target` mentions
    the innermost case, and none should be added.
    """
    for marker in ("total + r.id", "'one'", "id > 0", "total int"):
        pos = _BODY.index(marker)
        innermost = ladder_candidates(structure_chain(_BODY, pos))[0]
        probe = min(innermost[0] + 1, innermost[1])
        assert shrink_target(structure_chain(_BODY, probe), innermost) is None


def test_deriving_never_jumps_outside_the_selection():
    """The one boundary the implementation must honour: where the selection is a
    superset of no span, this is a no-op, never an arbitrary selection."""
    text = "select a from t;"
    # A selection cutting across two rungs and containing none of them whole.
    assert shrink_target(structure_chain(text, 5), (5, 9)) is None


def test_every_ladder_rung_strictly_contains_the_previous_one():
    """The ladder's contract, over the whole corpus: a press always widens, and
    never repeats a range -- which is what makes "a rung may be absent, never
    present-and-empty" checkable rather than aspirational."""
    for text in SAMPLES + [_BODY]:
        for pos in range(len(text) + 1):
            candidates = ladder_candidates(structure_chain(text, pos))
            for previous, following in zip(candidates, candidates[1:]):
                assert following != previous
                assert following[0] <= previous[0] and following[1] >= previous[1]


# --------------------------------------------------------------------------
# THE ANTI-FORK GUARD
# --------------------------------------------------------------------------


class _RecordingReindenter(formatter._Reindenter):
    """The reindenter, told to remember which frames it MATCHED.

    Its frame stack is throwaway by design (it drives indentation and the refusal
    verdict, and exposes no spans), which is exactly why `block_spans.py` exists.
    Recording the pops is the only way to compare the two walks without changing
    the engine.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.matched: set[tuple[str, int]] = set()

    def _record(self, before) -> None:
        for frame in before[len(self._frames) :]:
            if frame.token is None:
                continue
            if frame.kind in formatter._BLOCK_FRAMES or frame.kind in ("paren", "bracket"):
                self.matched.add((frame.kind, frame.token.start))

    def _close_block(self, index, tok):
        before = list(self._frames)
        super()._close_block(index, tok)
        self._record(before)

    def _close_bracket(self, tok):
        before = list(self._frames)
        super()._close_bracket(tok)
        self._record(before)


def reindenter_nesting(text: str) -> tuple[set[tuple[str, int]], bool]:
    items = significant_tokens(tokenize(text))
    engine = _RecordingReindenter(items, config=DEFAULT_FORMAT_CONFIG)
    _lines, issues = engine.run()
    return engine.matched, not issues


def span_model_nesting(text: str) -> set[tuple[str, int]]:
    """The same set, read out of the span model's ONE walk.

    Deliberately the private `_frame_spans` rather than the public
    `structure_chain`: the walk is what is being compared, and `structure_chain`
    additionally DESCENDS into a `$$` body (BUG-041's rule), where the reindenter
    treats the body as one opaque token. Comparing chains would therefore report
    the descent as a disagreement, when the descent is the specified behaviour and
    both consumers still read the identical rules at each level.
    """
    spans = block_spans._frame_spans(text, significant_tokens(tokenize(text)))
    return {
        (kind, outer[0])
        for kind, outer, _inner in spans
        if kind in ("begin", "if", "loop", "case", "paren", "bracket")
    }


@pytest.mark.parametrize("text", SAMPLES + [_BODY])
def test_the_span_model_and_the_reindenter_agree_on_block_nesting(text):
    """§18.4's adversarial corpus -- the same inputs the six false-positive guards
    exist for -- pushed through BOTH consumers of `sql/blocks.py`.

    A rule that lives in one module and is verified against the other consumer
    cannot silently diverge; a comment saying *"keep these in sync"* can. Only
    balanced samples are compared, because "matched" is only meaningful there:
    where the reindenter refuses, it pops a frame to report the defect while the
    span model drops it without inventing an end.
    """
    matched, balanced = reindenter_nesting(text)
    if not balanced:
        pytest.skip("unbalanced input: 'matched' has no shared meaning")
    assert span_model_nesting(text) == matched
