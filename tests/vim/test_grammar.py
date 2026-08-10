"""The Command-mode command grammar (FQ-032 §8, `pgtp_editor/vim/grammar.py`).

The pending-state machine is the part most likely to be got subtly wrong, which is
why it is pure and why it is tested here rather than through a widget. **Counts are
LOAD-BEARING**: `42j` is the whole motivating case and has no alternative anywhere
in the app.
"""
from __future__ import annotations

import pytest

from pgtp_editor.vim import LINEWISE, REDO_KEY, VimGrammar


def feed(keys: str | list[str]):
    """Feed `keys` and return the list of commands they resolved to."""
    grammar = VimGrammar()
    resolved = []
    for key in keys:
        command = grammar.feed(key)
        if command is not None:
            resolved.append(command)
    return grammar, resolved


# -- counts -------------------------------------------------------------------
def test_the_motivating_case_42j_is_one_command_with_a_count_of_42():
    _grammar, resolved = feed("42j")
    assert len(resolved) == 1
    assert resolved[0].motion == "j"
    assert resolved[0].count == 42
    assert resolved[0].operator is None
    assert resolved[0].has_count


def test_a_bare_motion_has_a_count_of_one_and_says_it_was_not_typed():
    _grammar, resolved = feed("j")
    assert resolved[0].count == 1
    assert not resolved[0].has_count


def test_counts_before_and_after_an_operator_multiply_as_they_do_in_vim():
    _grammar, resolved = feed("2d3w")
    assert len(resolved) == 1
    assert (resolved[0].operator, resolved[0].motion, resolved[0].count) == ("d", "w", 6)


def test_digits_leave_the_machine_PENDING_until_a_motion_arrives():
    grammar = VimGrammar()
    assert grammar.feed("4") is None
    assert grammar.is_pending
    assert grammar.pending_text == "4"
    assert grammar.feed("2") is None
    assert grammar.pending_text == "42"
    assert grammar.feed("j") is not None
    assert not grammar.is_pending


def test_zero_is_the_start_of_line_MOTION_when_no_count_is_under_way():
    _grammar, resolved = feed("0")
    assert resolved[0].motion == "0"
    assert resolved[0].count == 1


def test_zero_is_a_DIGIT_once_a_count_is_under_way():
    _grammar, resolved = feed("10j")
    assert (resolved[0].motion, resolved[0].count) == ("j", 10)


def test_d0_deletes_to_the_start_of_the_line_rather_than_parsing_a_count():
    _grammar, resolved = feed("d0")
    assert (resolved[0].operator, resolved[0].motion) == ("d", "0")


# -- motions ------------------------------------------------------------------
@pytest.mark.parametrize("motion", ["h", "j", "k", "l", "w", "b", "e", "0", "^", "$", "%", "{", "}"])
def test_every_simple_v1_motion_resolves_on_its_own_key(motion):
    _grammar, resolved = feed(motion)
    assert resolved[0].motion == motion
    assert resolved[0].operator is None
    assert resolved[0].action is None


def test_gg_needs_two_keys_and_is_pending_after_the_first():
    grammar = VimGrammar()
    assert grammar.feed("g") is None
    assert grammar.is_pending and grammar.pending_text == "g"
    command = grammar.feed("g")
    assert command.motion == "gg"


def test_g_followed_by_anything_else_is_DISCARDED_rather_than_guessed_at():
    grammar = VimGrammar()
    grammar.feed("g")
    assert grammar.feed("z") is None
    assert not grammar.is_pending


def test_NG_carries_the_count_and_says_a_count_was_typed():
    _grammar, resolved = feed("42G")
    assert (resolved[0].motion, resolved[0].count, resolved[0].has_count) == ("G", 42, True)


def test_bare_G_is_distinguishable_from_1G_by_has_count():
    """`G` means the LAST line and `1G` means line 1, and `count == 1` cannot tell
    them apart -- which is exactly why the fact that a count was typed is carried
    rather than inferred."""
    _grammar, bare = feed("G")
    _grammar, counted = feed("1G")
    assert not bare[0].has_count
    assert counted[0].has_count


@pytest.mark.parametrize("motion", ["f", "t", "F", "T"])
def test_the_character_motions_take_one_more_key_as_their_target(motion):
    grammar = VimGrammar()
    assert grammar.feed(motion) is None
    assert grammar.is_pending
    command = grammar.feed(";")
    assert (command.motion, command.target) == (motion, ";")


def test_a_character_motion_with_a_count_keeps_it():
    _grammar, resolved = feed("3fx")
    assert (resolved[0].motion, resolved[0].target, resolved[0].count) == ("f", "x", 3)


# -- operators ----------------------------------------------------------------
@pytest.mark.parametrize("operator", ["d", "c", "y"])
def test_an_operator_is_pending_until_a_motion_completes_it(operator):
    grammar = VimGrammar()
    assert grammar.feed(operator) is None
    assert grammar.is_pending and grammar.pending_text == operator
    command = grammar.feed("w")
    assert (command.operator, command.motion) == (operator, "w")


@pytest.mark.parametrize("operator", ["d", "c", "y"])
def test_a_doubled_operator_is_LINEWISE(operator):
    _grammar, resolved = feed(operator + operator)
    assert resolved[0].operator == operator
    assert resolved[0].motion == LINEWISE
    assert resolved[0].is_linewise


def test_a_count_before_a_doubled_operator_survives():
    _grammar, resolved = feed("3dd")
    assert (resolved[0].operator, resolved[0].count, resolved[0].is_linewise) == ("d", 3, True)


def test_two_DIFFERENT_operators_are_discarded_rather_than_guessed_at():
    grammar = VimGrammar()
    grammar.feed("d")
    assert grammar.feed("y") is None
    assert not grammar.is_pending


def test_an_operator_followed_by_a_non_motion_is_discarded():
    """`di` is a text object, which is explicitly OUT of v1 -- so it resolves to
    nothing rather than to a half-guessed delete."""
    grammar = VimGrammar()
    grammar.feed("d")
    assert grammar.feed("i") is None
    assert not grammar.is_pending


@pytest.mark.parametrize(
    "key,operator,motion",
    [
        ("x", "d", "l"),
        ("X", "d", "h"),
        ("D", "d", "$"),
        ("C", "c", "$"),
        ("Y", "y", LINEWISE),
        ("s", "c", "l"),
        ("S", "c", LINEWISE),
    ],
)
def test_the_shorthands_resolve_to_operator_motion_pairs(key, operator, motion):
    """Resolved HERE so the widget has one code path per operator rather than
    seven more branches."""
    _grammar, resolved = feed(key)
    assert (resolved[0].operator, resolved[0].motion) == (operator, motion)


def test_the_inclusive_motions_are_vims_own_set():
    _grammar, inclusive = feed("de")
    _grammar, exclusive = feed("dw")
    assert inclusive[0].is_inclusive
    assert not exclusive[0].is_inclusive


# -- actions ------------------------------------------------------------------
@pytest.mark.parametrize("key", ["i", "a", "I", "A", "o", "O"])
def test_the_insert_entry_keys_are_actions(key):
    _grammar, resolved = feed(key)
    assert resolved[0].action == key


@pytest.mark.parametrize("key", ["v", "V"])
def test_v_and_V_are_INSERT_ENTRY_aliases_because_there_is_no_visual_mode(key):
    """They drop to Edit mode so the user selects the Windows-native way. The
    contract consequence a vim user will otherwise hit as a bug: the
    select-with-`v`-then-`d` reflex does not exist here."""
    _grammar, resolved = feed(key)
    assert resolved[0].action == key
    assert resolved[0].operator is None


def test_u_and_ctrl_r_are_the_undo_and_redo_actions():
    grammar = VimGrammar()
    assert grammar.feed("u").action == "u"
    assert grammar.feed(REDO_KEY).action == "redo"


def test_the_redo_token_cannot_collide_with_a_bare_letter():
    assert len(REDO_KEY) > 1


def test_p_and_P_are_the_two_paste_actions():
    grammar = VimGrammar()
    assert grammar.feed("p").action == "p"
    assert grammar.feed("P").action == "P"


def test_r_takes_a_replacement_character():
    grammar = VimGrammar()
    assert grammar.feed("r") is None
    assert grammar.is_pending
    command = grammar.feed("z")
    assert (command.action, command.target) == ("r", "z")


def test_r_with_a_count_replaces_that_many():
    _grammar, resolved = feed("3rz")
    assert (resolved[0].action, resolved[0].target, resolved[0].count) == ("r", "z", 3)


def test_dr_is_not_a_command():
    grammar = VimGrammar()
    grammar.feed("d")
    assert grammar.feed("r") is None
    assert not grammar.is_pending


def test_search_and_the_palette_are_actions_not_motions():
    grammar = VimGrammar()
    assert grammar.feed("/").action == "search"
    assert grammar.feed("n").action == "find-next"
    assert grammar.feed("N").action == "find-previous"
    assert grammar.feed(":").action == "palette"


# -- resets -------------------------------------------------------------------
def test_an_unknown_key_discards_any_pending_state():
    grammar = VimGrammar()
    grammar.feed("4")
    grammar.feed("d")
    assert grammar.feed("!") is None
    assert not grammar.is_pending


def test_reset_is_idempotent_and_clears_everything():
    grammar = VimGrammar()
    grammar.feed("4")
    grammar.feed("d")
    grammar.reset()
    grammar.reset()
    assert not grammar.is_pending
    assert grammar.pending_text == ""


def test_the_grammar_carries_NO_register_field():
    """One shared SYSTEM clipboard, no vim registers -- so there is nothing here
    to hold one."""
    _grammar, resolved = feed("yy")
    assert not hasattr(resolved[0], "register")
