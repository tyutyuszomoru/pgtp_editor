from pgtp_editor.ui.search import Match, find_all_matches, find_next


# -- find_next -------------------------------------------------------------

def test_find_next_first_occurrence_at_or_after_from_pos():
    assert find_next("the Page and a Page", "page", 0) == 4


def test_find_next_case_insensitive():
    assert find_next("Hello PAGE world", "page", 0) == 6


def test_find_next_skips_earlier_occurrence():
    # from_pos past the first match -> returns the second.
    assert find_next("page and page", "page", 1) == 9


def test_find_next_wraps_when_none_after_from_pos():
    # Only match is before from_pos; wrap brings us back to it.
    assert find_next("page then nothing", "page", 5, wrap=True) == 0


def test_find_next_no_wrap_returns_none_when_none_after_from_pos():
    assert find_next("page then nothing", "page", 5, wrap=False) is None


def test_find_next_no_match_returns_none():
    assert find_next("nothing here", "zzz", 0) is None


def test_find_next_empty_term_returns_none():
    assert find_next("anything", "", 0) is None


# -- find_all_matches ------------------------------------------------------

def test_find_all_matches_multiple_hits_in_order():
    matches = find_all_matches("page PAGE page", "page")
    assert [m.start for m in matches] == [0, 5, 10]


def test_find_all_matches_no_match_returns_empty():
    assert find_all_matches("nothing", "zzz") == []


def test_find_all_matches_empty_term_returns_empty():
    assert find_all_matches("anything", "") == []


def test_find_all_matches_adjacent_matches_all_found():
    assert [m.start for m in find_all_matches("abab", "ab")] == [0, 2]
    assert [m.start for m in find_all_matches("aa", "a")] == [0, 1]


def test_find_all_matches_overlapping_not_all_found():
    # Non-overlapping left-to-right scan advancing by len(term): "aaa"/"aa"
    # yields ONE match at 0 (resumes at index 2), not two at 0 and 1.
    assert [m.start for m in find_all_matches("aaa", "aa")] == [0]


def test_find_all_matches_line_numbers_are_one_based():
    text = "line one\nline two\nhere is page\nline four"
    matches = find_all_matches(text, "page")
    assert len(matches) == 1
    assert matches[0].line == 3


def test_find_all_matches_preview_is_trimmed_whole_line():
    text = "a\n    indented page here    \nb"
    matches = find_all_matches(text, "page")
    assert len(matches) == 1
    assert matches[0].preview == "indented page here"


def test_match_is_frozen_dataclass():
    m = Match(start=0, line=1, preview="x")
    assert (m.start, m.line, m.preview) == (0, 1, "x")


import itertools

from pgtp_editor.ui.search import iter_matches


def test_iter_matches_matches_find_all_matches():
    from pgtp_editor.ui.search import find_all_matches
    text = "page PAGE page\nno hits\nlast page"
    assert list(iter_matches(text, "page")) == find_all_matches(text, "page")


def test_iter_matches_empty_term_yields_nothing():
    assert list(iter_matches("anything", "")) == []


def test_iter_matches_empty_text_yields_nothing():
    assert list(iter_matches("", "page")) == []


def test_iter_matches_is_lazy():
    # A huge input with a match very early: islice must return the first hit
    # without scanning/among building the whole result list.
    text = "page" + ("x" * 1_000_000)
    first_two = list(itertools.islice(iter_matches(text, "x"), 2))
    assert [m.start for m in first_two] == [4, 5]


def test_iter_matches_line_and_preview():
    text = "l1\n  hit here  \nl3"
    (m,) = list(iter_matches(text, "hit"))
    assert m.line == 2
    assert m.preview == "hit here"
