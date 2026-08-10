"""Unit tests for the SQL/plpgsql tokenizer (spec §18.4). Pure, no Qt."""
from __future__ import annotations

import re
import unicodedata

import pytest

from pgtp_editor.sql.keywords import SQL_KEYWORDS
from pgtp_editor.sql.tokenizer import (
    BLOCK_COMMENT,
    DOLLAR_STRING,
    LINE_COMMENT,
    NEWLINE,
    NUMBER,
    PUNCT,
    QUOTED_IDENT,
    STRING,
    WHITESPACE,
    WORD,
    _Cursor,
    dollar_body_at,
    tokenize,
)


def kinds(text):
    return [tok.kind for tok in tokenize(text)]


def texts(text):
    return [tok.text for tok in tokenize(text)]


def code(text):
    """Non-trivia token texts, in order."""
    return [tok.text for tok in tokenize(text) if not tok.is_trivia]


def test_tokenize_is_lossless_and_verbatim():
    text = "SELECT a /* c */, 'x' -- t\nFROM \"T\";\r\n"
    assert "".join(texts(text)) == text


def test_empty_input_yields_no_tokens():
    assert tokenize("") == []


def test_words_numbers_and_punctuation():
    assert kinds("a1 + 2.5") == [WORD, WHITESPACE, PUNCT, WHITESPACE, NUMBER]
    assert code("count(*)") == ["count", "(", "*", ")"]
    assert code("1e-3 .5 1.5") == ["1e-3", ".5", "1.5"]
    # `1..10` is a plpgsql range, not `1.` + `.10`.
    assert code("for i in 1..10") == ["for", "i", "in", "1", "..", "10"]


def test_keyword_view_is_case_insensitive_and_never_rewrites_text():
    tokens = [tok for tok in tokenize("SeLeCt foo") if tok.kind == WORD]
    assert tokens[0].text == "SeLeCt"  # verbatim
    assert tokens[0].keyword == "select"
    assert tokens[0].is_keyword
    assert tokens[1].keyword is None
    assert not tokens[1].is_keyword


def test_keyword_view_uses_the_shared_dialect_set():
    assert "begin" in SQL_KEYWORDS
    for word in ("elseif", "elsif", "while", "exit", "continue", "loop", "end", "then"):
        assert word in SQL_KEYWORDS, word


def test_line_comment_stops_before_the_newline():
    tokens = tokenize("a -- hi\nb")
    comment = next(tok for tok in tokens if tok.kind == LINE_COMMENT)
    assert comment.text == "-- hi"
    assert tokens[tokens.index(comment) + 1].kind == NEWLINE


def test_block_comment_nests_like_postgres():
    text = "/* a /* b */ c */x"
    tokens = tokenize(text)
    assert tokens[0].kind == BLOCK_COMMENT
    assert tokens[0].text == "/* a /* b */ c */"
    assert tokens[1].text == "x"


def test_single_quoted_string_doubling_and_escape_prefix():
    assert code("'a''b'") == ["'a''b'"]
    # E'' honors backslash escapes; the prefix stays glued to the quote.
    assert code("e'a\\'b'") == ["e'a\\'b'"]
    assert code("U&'x'") == ["U&'x'"]


def test_double_quoted_identifier_doubling():
    tokens = tokenize('"He""llo" x')
    assert tokens[0].kind == QUOTED_IDENT
    assert tokens[0].text == '"He""llo"'


def test_dollar_quote_bare_and_tagged():
    bare = tokenize("$$ any 'thing' $$")[0]
    assert bare.kind == DOLLAR_STRING
    assert bare.tag == ""
    tagged = tokenize("$fn$ begin $$ end $fn$")[0]
    assert tagged.kind == DOLLAR_STRING
    assert tagged.tag == "fn"
    assert tagged.text == "$fn$ begin $$ end $fn$"


def test_dollar_parameter_is_one_token():
    assert code("id = $1") == ["id", "=", "$1"]


def test_multi_character_operators_stay_whole():
    assert code("a::text") == ["a", "::", "text"]
    assert code("x := 1") == ["x", ":=", "1"]
    assert code("a->>'k'") == ["a", "->>", "'k'"]
    assert code("a <> b") == ["a", "<>", "b"]


def test_offsets_and_line_columns_are_consistent():
    text = "select a\nfrom t"
    for tok in tokenize(text):
        assert text[tok.start : tok.end] == tok.text
    from_tok = next(tok for tok in tokenize(text) if tok.text == "from")
    assert (from_tok.start_line, from_tok.start_col) == (2, 1)
    assert (from_tok.end_line, from_tok.end_col) == (2, 5)


def test_crlf_is_a_single_newline_token():
    tokens = tokenize("a\r\nb")
    assert tokens[1].kind == NEWLINE
    assert tokens[1].text == "\r\n"
    assert tokens[2].text == "b"


def test_unterminated_regions_are_flagged_not_raised():
    for text, kind in (
        ("select 'abc", STRING),
        ('select "abc', QUOTED_IDENT),
        ("select $$abc", DOLLAR_STRING),
        ("select /* abc", BLOCK_COMMENT),
        ("select $tag$abc", DOLLAR_STRING),
    ):
        last = tokenize(text)[-1]
        assert last.kind == kind, text
        assert last.unterminated, text
        assert last.end == len(text), text


def test_opaque_kinds_are_marked_opaque():
    for text in ("'s'", '"i"', "$$b$$", "-- c", "/* c */"):
        assert tokenize(text)[0].is_opaque, text
    assert not tokenize("word")[0].is_opaque


# --------------------------------------------------------------------------
# Losslessness / span bookkeeping over adversarial text. The formatter builds
# its refusal spans straight out of these fields, so they must tile the input
# exactly -- a token whose offsets drift would underline the wrong characters.
# --------------------------------------------------------------------------

TRICKY = [
    "",
    "   ",
    "\n\n",
    "\r",
    "\r\n",
    "select a\r\nfrom \"T\" -- c\r\n/* x\ny */ 'z';",
    "select 'a''b', \"C\"\"D\", e'x\\'y', U&'z', b'101', x'ff' from t;",
    "select $$ any 'thing' -- here $$, $tag$ nested $$ inside $tag$ from t;",
    "select a -- $$ not a dollar quote\nfrom t;",
    "/* a /* b */ c */ select 1;",
    "select 1e-3, .5, 1.5, 1..10, -2, +3 from t;",
    "begin\n  if a then\n    x := 1;\n  end if;\nend;",
    "select 'abc",  # unterminated by a selection boundary
    'select "abc',
    "select $$abc",
    "select /* abc",
    r"select e'a\'",
    "\x0b\x0c\t select 1",
    "select a\rfrom t\nwhere b = 1\r\norder by a",  # all three endings at once
    "select ügyfél.árvíztűrő from közös.tábla where szám = 1;",  # accented (NFC)
    unicodedata.normalize("NFD", "select tábla.ár from séma.tábla"),  # accented (NFD)
    "select $tág$ opaque $tág$ from t;",  # accented dollar-quote tag
    "select \U00010330_col, \U00020000col from t",  # non-BMP letters
]


@pytest.mark.parametrize("text", TRICKY, ids=range(len(TRICKY)))
def test_tokenizing_is_lossless_for_tricky_text(text):
    assert "".join(texts(text)) == text


@pytest.mark.parametrize("text", TRICKY, ids=range(len(TRICKY)))
def test_token_offsets_tile_the_input_without_gaps_or_overlap(text):
    pos = 0
    for tok in tokenize(text):
        assert tok.start == pos, tok
        assert tok.end > tok.start, tok
        assert text[tok.start : tok.end] == tok.text, tok
        pos = tok.end
    assert pos == len(text)


def _line_col(text: str, offset: int) -> tuple[int, int]:
    """Independently computed 1-based line/column of `offset`."""
    lines = re.split(r"\r\n|\n|\r", text[:offset])
    return len(lines), len(lines[-1]) + 1


@pytest.mark.parametrize("text", TRICKY, ids=range(len(TRICKY)))
def test_line_and_column_match_an_independent_computation(text):
    for tok in tokenize(text):
        assert (tok.start_line, tok.start_col) == _line_col(text, tok.start), tok
        assert (tok.end_line, tok.end_col) == _line_col(text, tok.end), tok


def test_lone_cr_advances_the_line_counter():
    last = tokenize("a\rb")[-1]
    assert last.text == "b"
    assert (last.start_line, last.start_col) == (2, 1)


# --------------------------------------------------------------------------
# Lexical edge cases the formatter depends on.
# --------------------------------------------------------------------------


def test_dollar_sign_inside_an_identifier_does_not_open_a_dollar_quote():
    assert code("a$b") == ["a$b"]
    # ...but a real `$$` opener right after an identifier does end the word.
    assert [(tok.kind, tok.text) for tok in tokenize("a$$b$$")] == [
        (WORD, "a"),
        (DOLLAR_STRING, "$$b$$"),
    ]


def test_empty_dollar_quote_is_one_token():
    tok = tokenize("$$$$")[0]
    assert (tok.kind, tok.text, tok.tag) == (DOLLAR_STRING, "$$$$", "")


def test_empty_string_and_empty_quoted_identifier():
    assert code("'' \"\"") == ["''", '""']


def test_dollar_quote_inside_a_line_comment_is_just_comment_text():
    tokens = [tok for tok in tokenize("a -- $$ x\nb") if not tok.is_trivia]
    assert [tok.kind for tok in tokens] == [WORD, LINE_COMMENT, WORD]
    assert tokens[1].text == "-- $$ x"


def test_double_dash_inside_a_string_is_not_a_comment():
    assert code("'a -- b' c") == ["'a -- b'", "c"]


def test_bit_and_hex_string_prefixes_stay_glued_to_the_quote():
    assert code("b'101' x'ff'") == ["b'101'", "x'ff'"]


def test_escape_string_with_a_dangling_backslash_quote_is_unterminated():
    tok = tokenize(r"e'a\'")[0]
    assert tok.kind == STRING
    assert tok.unterminated


def test_nested_block_comment_missing_one_closer_is_unterminated():
    tok = tokenize("/* a /* b */ c")[0]
    assert tok.kind == BLOCK_COMMENT
    assert tok.unterminated
    assert tok.end == len("/* a /* b */ c")


def test_tagged_and_bare_dollar_quotes_do_not_swallow_each_other():
    tokens = [tok for tok in tokenize("$tag$ a $tag$ $$ b $$") if not tok.is_trivia]
    assert [tok.text for tok in tokens] == ["$tag$ a $tag$", "$$ b $$"]


def test_lone_cr_is_its_own_newline_token():
    tokens = tokenize("a\rb")
    assert tokens[1].kind == NEWLINE
    assert tokens[1].text == "\r"


def test_lowered_is_a_view_and_never_replaces_text():
    tok = tokenize("MiXeD")[0]
    assert tok.text == "MiXeD"
    assert tok.lowered == "mixed"


def test_non_ascii_identifier_is_a_single_word_token():
    tokens = [tok for tok in tokenize("select tábla from x") if not tok.is_trivia]
    assert [tok.text for tok in tokens] == ["select", "tábla", "from", "x"]


def test_non_ascii_identifier_continues_with_digits_underscores_and_dollars():
    assert code("Ügyfél_2$a árvíztűrő") == ["Ügyfél_2$a", "árvíztűrő"]
    assert [tok.kind for tok in tokenize("tábla") if not tok.is_trivia] == [WORD]


# --------------------------------------------------------------------------
# Unicode identifiers beyond Latin-1: a split identifier would let the
# formatter insert a space inside it, so word boundaries must follow
# Postgres' "any letter" rule, not a codepoint range.
# --------------------------------------------------------------------------


def test_non_bmp_letter_identifier_is_a_single_word_token():
    # Gothic (U+10330) and CJK Ext-B (U+20000) are letters outside the BMP:
    # any surrogate-pair-blind scan would cut them in half.
    for ident in ("\U00010330_col", "\U00020000col", "col\U00010330"):
        tokens = [tok for tok in tokenize(f"select {ident} from t") if not tok.is_trivia]
        assert [tok.kind for tok in tokens] == [WORD, WORD, WORD, WORD], ident
        assert tokens[1].text == ident, ident


def test_accented_dollar_quote_tag_is_one_opaque_token():
    tok = tokenize("$tág$ if a then not code $tág$")[0]
    assert tok.kind == DOLLAR_STRING
    assert tok.tag == "tág"
    assert tok.text == "$tág$ if a then not code $tág$"
    assert tok.is_opaque
    assert not tok.unterminated


def test_accented_dollar_tag_does_not_match_a_differently_accented_closer():
    # `$tag$` must not close `$tág$` -- the tags differ, so the region runs on
    # to the end of the selection and is reported unterminated.
    tok = tokenize("$tág$ body $tag$")[0]
    assert tok.kind == DOLLAR_STRING
    assert tok.unterminated


def test_positional_parameters_stay_separate_from_dollar_quotes():
    assert code("select $1 || $$x$$ from t") == ["select", "$1", "||", "$$x$$", "from", "t"]
    assert code("where a = $10 and b = $2") == ["where", "a", "=", "$10", "and", "b", "=", "$2"]
    params = [tok for tok in tokenize("select $1, $$b$$") if not tok.is_trivia]
    assert params[1].kind == WORD  # `$1` is a word-shaped token, not a dollar quote
    assert params[1].tag is None
    assert params[-1].kind == DOLLAR_STRING


def test_accented_identifier_stays_whole_next_to_glue_operators():
    assert code("select á::szöveg from tábla") == [
        "select", "á", "::", "szöveg", "from", "tábla",
    ]
    assert code("séma.tábla.á") == ["séma", ".", "tábla", ".", "á"]
    assert code("v tábla.á%TYPE;") == ["v", "tábla", ".", "á", "%", "TYPE", ";"]
    assert code("függ(tábla.á[1])") == ["függ", "(", "tábla", ".", "á", "[", "1", "]", ")"]


# --------------------------------------------------------------------------
# Line-break bookkeeping: CR, LF and CRLF each count as exactly one break,
# including across the internal chunks `_Cursor.advance_to` walks. Issue spans
# are built straight out of these numbers.
# --------------------------------------------------------------------------


def test_mixed_line_endings_each_count_as_exactly_one_break():
    text = "a\rb\nc\r\nd"
    words = [tok for tok in tokenize(text) if tok.kind == WORD]
    assert [tok.text for tok in words] == ["a", "b", "c", "d"]
    assert [(tok.start_line, tok.start_col) for tok in words] == [(1, 1), (2, 1), (3, 1), (4, 1)]


def test_crlf_split_across_two_cursor_advances_counts_one_break():
    # The tokenizer emits `\r\n` as one token, but the cursor must still be
    # correct if a caller consumes the CR and the LF separately -- otherwise a
    # future token kind that ends between them would silently gain a line.
    cursor = _Cursor("a\r\nb")
    cursor.advance_to(1)
    assert (cursor.line, cursor.col) == (1, 2)
    cursor.advance_to(2)  # the CR only
    assert (cursor.line, cursor.col) == (2, 1)
    cursor.advance_to(3)  # the LF only -- same line, still column 1
    assert (cursor.line, cursor.col) == (2, 1)
    cursor.advance_to(4)
    assert (cursor.line, cursor.col) == (2, 2)


def test_cursor_handles_a_chunk_that_starts_with_lf_after_text_and_cr():
    cursor = _Cursor("x\r\nabc")
    cursor.advance_to(2)  # "x\r"
    assert (cursor.line, cursor.col) == (2, 1)
    cursor.advance_to(6)  # "\nabc" -- the LF is the tail of the CRLF, not a break
    assert (cursor.line, cursor.col) == (2, 4)


@pytest.mark.parametrize(
    "opaque",
    ["$$a\rb$$", "$$a\r\nb$$", "$$a\nb$$", "/* a\rb */", "/* a\r\nb */", "'a\rb'", '"a\r\nb"'],
)
def test_line_numbers_survive_a_multi_line_opaque_token(opaque):
    text = f"{opaque}\nx"
    tokens = [tok for tok in tokenize(text) if not tok.is_trivia]
    assert len(tokens) == 2
    assert tokens[0].start_line == 1
    assert tokens[0].end_line == 2  # one break inside the opaque region
    assert (tokens[1].start_line, tokens[1].start_col) == (3, 1)


# --------------------------------------------------------------------------
# Decomposed (NFD) accented identifiers -- what a macOS clipboard or a PDF
# copy yields. Regression: a combining mark (U+0301) is neither isalpha() nor
# isalnum(), so the identifier was shredded into WORD/PUNCT/WORD and the
# formatter then inserted spaces inside it.
# --------------------------------------------------------------------------


def test_decomposed_nfd_identifier_is_a_single_word_token():
    nfd = unicodedata.normalize("NFD", "tábla")
    assert nfd != "tábla"  # guard: this really is the decomposed form
    tokens = [tok for tok in tokenize(f"select * from {nfd}") if not tok.is_trivia]
    assert [tok.text for tok in tokens] == ["select", "*", "from", nfd]


def test_decomposed_nfd_dollar_quote_tag_is_one_opaque_token():
    # Regression: _dollar_tag_at stopped at the combining mark, so the whole
    # $tag$...$tag$ body lost its opacity and got reindented as code.
    tag = unicodedata.normalize("NFD", "tág")
    text = f"${tag}$ if a then not code ${tag}$"
    tok = tokenize(text)[0]
    assert tok.kind == DOLLAR_STRING
    assert tok.text == text


# --------------------------------------------------------------------------
# dollar_body_at -- the shared body locator (BUG-041 / option D).
#
# Promoted here from `from_clause._dollar_body_at` so `from_clause.py` (FROM
# scope) and `caret_context.py` (completion context) descend into a routine
# body through one implementation instead of two that drift apart on tag
# length and unterminated bodies.
# --------------------------------------------------------------------------


def _body(text, pos):
    return dollar_body_at(tokenize(text), pos)


def test_dollar_body_at_returns_none_outside_any_body():
    text = "select * from t"
    assert _body(text, len(text)) is None
    text = "create function f() as $$ x $$ language sql"
    assert _body(text, 0) is None
    assert _body(text, len(text)) is None


def test_dollar_body_at_bare_body_text_and_offset():
    text = "create function f() as $$ begin end $$ language sql"
    caret = text.index("begin")
    body, start = _body(text, caret)
    assert body == " begin end "
    assert start == text.index("$$") + 2
    # The offset is the contract: rebasing lands on the same character.
    assert text[start + (caret - start)] == "b"
    assert body[caret - start :].startswith("begin")


def test_dollar_body_at_accounts_for_the_tag_length():
    text = "create function f() as $function$ begin end $function$ language sql"
    caret = text.index("begin")
    body, start = _body(text, caret)
    assert body == " begin end "
    assert start == text.index("$function$") + len("$function$")
    assert body[caret - start :].startswith("begin")


def test_dollar_body_at_unterminated_body_runs_to_end_of_text():
    """The normal state while typing: the opener is there, the closer is not."""
    text = "create function f() as $$ select * from hr.secret s"
    body, start = _body(text, len(text) - 1)
    assert body == " select * from hr.secret s"
    assert start == text.index("$$") + 2


def test_dollar_body_at_counts_the_end_of_an_unterminated_body_as_inside():
    """Where the author's caret actually is while typing a new routine: the
    end of an unterminated body is the end of the buffer, not a boundary to
    fall outside of."""
    text = "create function f() as $$ select * from hr.secret s"
    assert _body(text, len(text)) == (" select * from hr.secret s", text.index("$$") + 2)


def test_dollar_body_at_caret_inside_the_closing_tag_yields_an_empty_body():
    text = "create function f() as $function$ begin end $function$ language sql"
    caret = text.rindex("$function$") + 3  # inside the closing tag itself
    assert _body(text, caret) == ("", text.index("$function$") + len("$function$"))


def test_dollar_body_at_boundaries_are_not_inside():
    text = "select $$ x $$"
    opener = text.index("$$")
    assert _body(text, opener) is None  # right before the opener
    assert _body(text, len(text)) is None  # right after the closer
