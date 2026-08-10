"""`w` / `b` / `e` by **vim's own character-class rule** (FQ-032 §8).

The rule under test, and the reason it is a rule rather than a preference: a vim
word is **not a SQL token**, and the editing-mode layer serves XML, PHP and JS
buffers as well as SQL, so these motions may never reach `sql/tokenizer.py`.
"""
from __future__ import annotations

import pytest

from pgtp_editor.vim import (
    CLASS_KEYWORD,
    CLASS_PUNCTUATION,
    CLASS_WHITESPACE,
    char_class,
    word_backward,
    word_end,
    word_forward,
)


@pytest.mark.parametrize(
    "char,expected",
    [
        ("a", CLASS_KEYWORD),
        ("Z", CLASS_KEYWORD),
        ("7", CLASS_KEYWORD),
        ("_", CLASS_KEYWORD),
        ("(", CLASS_PUNCTUATION),
        (".", CLASS_PUNCTUATION),
        ("=", CLASS_PUNCTUATION),
        (" ", CLASS_WHITESPACE),
        ("\t", CLASS_WHITESPACE),
        ("\n", CLASS_WHITESPACE),
        ("", CLASS_WHITESPACE),
    ],
)
def test_the_three_character_classes(char, expected):
    assert char_class(char) == expected


def test_underscore_is_a_KEYWORD_character_so_an_identifier_is_one_word():
    text = "my_table_name next"
    assert word_forward(text, 0) == text.index("next")


def test_w_stops_at_a_punctuation_run_because_it_is_its_own_word():
    text = "a.b"
    assert word_forward(text, 0) == 1  # the '.'
    assert word_forward(text, 1) == 2  # the 'b'


def test_w_crosses_a_line_boundary_the_way_vim_does():
    text = "one\ntwo"
    assert word_forward(text, 0) == 4


def test_w_at_the_end_of_the_buffer_answers_the_end_rather_than_raising():
    text = "word"
    assert word_forward(text, 4) == 4
    assert word_forward(text, 99) == 4


def test_b_goes_to_the_start_of_the_previous_word():
    text = "alpha beta gamma"
    assert word_backward(text, text.index("gamma")) == text.index("beta")
    assert word_backward(text, text.index("beta")) == 0


def test_b_from_inside_a_word_goes_to_that_words_start():
    text = "alpha beta"
    assert word_backward(text, text.index("beta") + 2) == text.index("beta")


def test_b_at_the_start_of_the_buffer_answers_zero():
    assert word_backward("alpha", 0) == 0


def test_e_lands_ON_the_last_character_which_is_what_makes_it_inclusive():
    text = "alpha beta"
    assert word_end(text, 0) == 4  # the 'a' of "alpha"
    assert text[word_end(text, 0)] == "a"


def test_e_from_the_end_of_a_word_moves_to_the_next_words_end():
    text = "alpha beta"
    assert word_end(text, 4) == len(text) - 1


def test_e_on_an_empty_buffer_answers_zero_rather_than_raising():
    assert word_end("", 0) == 0


def test_e_past_the_end_answers_the_last_character():
    text = "alpha"
    assert word_end(text, 99) == len(text) - 1


def test_a_punctuation_run_is_one_word_for_e_too():
    text = "a===b"
    assert word_end(text, 0) == 3  # the last '='


def test_none_of_these_functions_needs_a_language():
    """The same call answers the same way on XML, PHP and SQL text -- which is the
    whole reason they are character-class rules."""
    for text in ('<Page name="x">', "$row['id'] = 1;", "select a from t"):
        assert 0 <= word_forward(text, 0) <= len(text)
        assert 0 <= word_backward(text, len(text)) <= len(text)
        assert 0 <= word_end(text, 0) < max(1, len(text))
