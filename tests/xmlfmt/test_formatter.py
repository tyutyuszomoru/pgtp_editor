"""`pgtp_editor.xmlfmt.format_xml_selection` -- §18.4 part C's XML indenter.

Organized around the guarantees the spec makes, because each one is the reason
this engine is safe to run on a `.pgtp`:

* part C's three hard rules (opening tags never broken, element text never
  touched, opaque constructs never entered);
* base depth taken from the selection's **position in the document**, not from
  its own first-line indentation -- the one deliberate divergence from the SQL
  engine;
* the refusal set, and just as importantly the two neighbouring cases that must
  **not** refuse;
* idempotence, which the spec makes a hard requirement, checked by re-running
  the formatter over the region the output now occupies.
"""
from __future__ import annotations

import pytest

from pgtp_editor.sql import FormatResult, Issue
from pgtp_editor.xmlfmt import (
    DEFAULT_XML_FORMAT_CONFIG,
    XmlFormatConfig,
    format_xml_selection,
)
from pgtp_editor.xmlfmt.scanner import TEXT, scan

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def whole(document: str, **kwargs) -> FormatResult:
    return format_xml_selection(document, 0, len(document), **kwargs)


def reformatted(document: str, start: int, end: int, **kwargs) -> tuple[str, int, int]:
    """Apply the formatter to `[start, end)` and return the new document+span."""
    result = format_xml_selection(document, start, end, **kwargs)
    assert result.ok, [issue.message for issue in result.issues]
    new_document = document[:start] + result.text + document[end:]
    return new_document, start, start + len(result.text)


def assert_idempotent(document: str, start: int, end: int, **kwargs) -> str:
    """Formatting, then reformatting the region the output occupies, is a no-op."""
    first = format_xml_selection(document, start, end, **kwargs)
    new_document = document[:start] + first.text + document[end:]
    second = format_xml_selection(new_document, start, start + len(first.text), **kwargs)
    assert second.ok == first.ok
    assert second.text == first.text
    return first.text


def significant(text: str) -> str:
    """The input minus every whitespace-only run between constructs.

    The preservation invariant is asserted through this: apart from inter-tag
    whitespace, the output bytes must be the input bytes.
    """
    return "".join(tok.text for tok in scan(text) if not (tok.kind == TEXT and not tok.text.strip()))


PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<Project>\n"
    '<Page name="customers">\n'
    "<!-- <Page/> in here is not an element -->\n"
    "<Fields>\n"
    '<Field name="id" type="int"/>\n'
    '<Field name="name" type="string"/>\n'
    "</Fields>\n"
    "</Page>\n"
    "</Project>\n"
)


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_pgtp_shaped_document_is_indented_by_element_depth():
    result = whole(PGTP)
    assert result.ok and result.issues == []
    assert result.text == (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Project>\n"
        '  <Page name="customers">\n'
        "    <!-- <Page/> in here is not an element -->\n"
        "    <Fields>\n"
        '      <Field name="id" type="int"/>\n'
        '      <Field name="name" type="string"/>\n'
        "    </Fields>\n"
        "  </Page>\n"
        "</Project>\n"
    )
    assert significant(result.text) == significant(PGTP)


def test_xsd_shaped_input_with_a_comment_and_a_pi():
    source = (
        '<?xml version="1.0"?>\n'
        "<!-- generated -->\n"
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        '<xs:element name="root">\n'
        "<xs:complexType>\n"
        '<xs:attribute name="id" type="xs:int"/>\n'
        "</xs:complexType>\n"
        "</xs:element>\n"
        "</xs:schema>\n"
    )
    text = assert_idempotent(source, 0, len(source))
    assert text == (
        '<?xml version="1.0"?>\n'
        "<!-- generated -->\n"
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        '  <xs:element name="root">\n'
        "    <xs:complexType>\n"
        '      <xs:attribute name="id" type="xs:int"/>\n'
        "    </xs:complexType>\n"
        "  </xs:element>\n"
        "</xs:schema>\n"
    )


def test_minified_input_is_expanded_one_element_per_line():
    source = "<a><b><c/></b><d/></a>"
    text = assert_idempotent(source, 0, len(source))
    assert text == "<a>\n  <b>\n    <c/>\n  </b>\n  <d/>\n</a>"
    assert significant(text) == significant(source)


def test_blank_lines_are_preserved_rather_than_collapsed():
    source = "<a>\n<b/>\n\n\n<c/>\n</a>"
    assert assert_idempotent(source, 0, len(source)) == "<a>\n  <b/>\n\n\n  <c/>\n</a>"


def test_indent_unit_is_configurable():
    source = "<a><b/></a>"
    tabs = whole(source, config=XmlFormatConfig(indent_unit="\t"))
    assert tabs.text == "<a>\n\t<b/>\n</a>"
    wide = whole(source, config=XmlFormatConfig(indent_unit="    "))
    assert wide.text == "<a>\n    <b/>\n</a>"
    assert whole(source).text == whole(source, config=DEFAULT_XML_FORMAT_CONFIG).text


# --------------------------------------------------------------------------
# Rule 1: never break inside an opening tag
# --------------------------------------------------------------------------


def test_attribute_heavy_opening_tag_is_never_broken():
    long_tag = (
        "<Field " + " ".join(f'attr{i}="value-{i}"' for i in range(40)) + ">"
    )
    source = f"<Fields>{long_tag}</Field></Fields>"
    text = assert_idempotent(source, 0, len(source))
    assert long_tag in text
    assert text == f"<Fields>\n  {long_tag}\n  </Field>\n</Fields>"


def test_a_self_closing_tag_is_not_rewritten_into_a_pair():
    assert whole("<a><b   /></a>").text == "<a>\n  <b   />\n</a>"


def test_attribute_order_case_and_quotes_are_untouched():
    source = "<A B='1' c=\"2\" xmlns:Z='u'><d/></A>"
    text = whole(source).text
    assert "<A B='1' c=\"2\" xmlns:Z='u'>" in text
    assert significant(text) == significant(source)


# --------------------------------------------------------------------------
# Rule 2: never touch element text
# --------------------------------------------------------------------------


def test_an_element_with_text_keeps_its_tags_and_content_byte_for_byte():
    body = 'if ($a &lt; 1) {\n    echo "hi";\n  }'
    source = f'<Project>\n<Event name="OnLoad">{body}</Event>\n</Project>'
    text = assert_idempotent(source, 0, len(source))
    assert f'<Event name="OnLoad">{body}</Event>' in text
    assert text == f'<Project>\n  <Event name="OnLoad">{body}</Event>\n</Project>'


def test_mixed_content_makes_the_whole_element_verbatim():
    """Rule 2 is about the element, not just the text run: an element with any
    non-whitespace direct text keeps its children's layout too."""
    inner = "<b>bold</b> and <i>italic</i>"
    source = f"<a>{inner}</a>"
    text = assert_idempotent(source, 0, len(source))
    assert text == source


def test_surrounding_whitespace_of_a_text_element_is_kept_when_the_opener_is_outside():
    """A bare text fragment: with no owning element in the selection, the
    whitespace around it is still that element's text and stays put."""
    document = "<a>\n  some text\n  <b/>\n</a>"
    start, end = document.index("some"), document.index("</a>")
    text = assert_idempotent(document, start, end)
    # The run between the text and <b/> is that element's mixed content and is
    # copied; only the trailing run (which spans lines) is re-cut, to depth 1.
    assert text == "some text\n  <b/>\n  "


def test_whitespace_only_content_is_not_text_and_is_reindented():
    assert whole("<a>   \n   </a>").text == "<a>\n</a>"


def test_a_nested_text_element_does_not_freeze_its_ancestors():
    source = "<a>\n<b>\n<c>text</c>\n</b>\n</a>"
    assert assert_idempotent(source, 0, len(source)) == (
        "<a>\n  <b>\n    <c>text</c>\n  </b>\n</a>"
    )


# --------------------------------------------------------------------------
# Rule 3: opaque constructs
# --------------------------------------------------------------------------


def test_phantom_tags_inside_a_comment_do_not_affect_depth():
    source = "<a>\n<!-- <b><c><d> -->\n<e/>\n</a>"
    assert assert_idempotent(source, 0, len(source)) == (
        "<a>\n  <!-- <b><c><d> -->\n  <e/>\n</a>"
    )


def test_phantom_tags_inside_cdata_do_not_affect_depth_and_bytes_are_kept():
    payload = "<![CDATA[ <b>  keep\n   me </b> ]]>"
    source = f"<a>\n{payload}\n<c/>\n</a>"
    text = assert_idempotent(source, 0, len(source))
    assert payload in text
    assert text == f"<a>\n  {payload}\n  <c/>\n</a>"


def test_processing_instruction_and_doctype_are_opaque():
    source = "<!DOCTYPE root [ <!ELEMENT a (b)> ]>\n<root>\n<?php echo '</root>'; ?>\n<a/>\n</root>"
    text = assert_idempotent(source, 0, len(source))
    assert "<?php echo '</root>'; ?>" in text
    assert text == (
        "<!DOCTYPE root [ <!ELEMENT a (b)> ]>\n"
        "<root>\n"
        "  <?php echo '</root>'; ?>\n"
        "  <a/>\n"
        "</root>"
    )


def test_a_comment_inside_the_document_prefix_does_not_inflate_the_base_depth():
    document = "<!-- <a><b><c> -->\n<root>\n<x/>\n</root>"
    start, end = document.index("<x/>"), document.index("\n</root>")
    text = assert_idempotent(document, start, end)
    assert text == "<x/>"  # depth 1, and no leading whitespace in the selection


# --------------------------------------------------------------------------
# Base depth from the document, not from the selection's own indentation
# --------------------------------------------------------------------------


def test_base_depth_comes_from_the_document_prefix_not_the_selections_indentation():
    document = (
        "<Project>\n"
        "  <Page>\n"
        "        <Fields>\n"  # deliberately wrong indentation
        "<Field a='1'/>\n"
        "  </Fields>\n"
        "  </Page>\n"
        "</Project>\n"
    )
    start = document.index("        <Fields>") + len("        ")
    end = document.index("</Fields>") + len("</Fields>")
    text = assert_idempotent(document, start, end)
    # Depth 2 inside <Project><Page>, regardless of the 8 spaces it sat behind.
    assert text == "<Fields>\n      <Field a='1'/>\n    </Fields>"


def test_the_leading_run_is_rewritten_when_it_spans_lines_and_kept_when_it_does_not():
    document = "<a>\n<b>\n<c/>\n</b>\n</a>"
    # Selection starting at the newline before <b>: the run spans lines, so it
    # is re-cut to the right depth.
    start = document.index("\n<b>")
    end = document.index("</b>") + len("</b>")
    assert assert_idempotent(document, start, end) == "\n  <b>\n    <c/>\n  </b>"

    # Selection starting mid-line: the bytes before the first tag are not ours.
    mid = "<a>  <b/></a>"
    assert whole(mid[:0] + mid).text.startswith("<a>")
    inner = format_xml_selection(mid, 3, len(mid) - len("</a>"))
    assert inner.ok and inner.text == "  <b/>"


def test_a_close_tag_whose_opener_is_outside_the_selection_dedents():
    document = "<a>\n  <b>\n    <c/>\n  </b>\n</a>\n"
    start = document.index("<c/>")
    end = document.index("</a>")
    text = assert_idempotent(document, start, end)
    assert text == "<c/>\n  </b>\n  "


def test_total_indent_is_clamped_at_zero():
    document = "<a><b>\n</b></a>"
    start = document.index("\n</b>")
    result = format_xml_selection(document, start, len(document))
    assert result.ok
    # base depth 2, three closes seen -> clamped, never negative indentation.
    assert result.text == "\n  </b>\n</a>"
    assert "\n   " not in result.text


# --------------------------------------------------------------------------
# Non-refusals
# --------------------------------------------------------------------------


def test_empty_selection_is_returned_untouched_and_ok():
    result = format_xml_selection("<a><b/></a>", 3, 3)
    assert (result.ok, result.text, result.issues) == (True, "", [])


@pytest.mark.parametrize("blank", ["   ", "\n", "\r\n  \r\n", "\t \t"])
def test_whitespace_only_selection_is_returned_untouched_and_ok(blank):
    document = f"<a>{blank}</a>"
    result = format_xml_selection(document, 3, 3 + len(blank))
    assert result.ok and result.text == blank and result.issues == []


def test_an_unmatched_open_tag_is_a_legitimate_fragment():
    document = "<a>\n<b>\n<c/>\n</b>\n</a>"
    end = document.index("\n</b>")
    result = format_xml_selection(document, 0, end)
    assert result.ok and result.issues == []
    assert result.text == "<a>\n  <b>\n    <c/>"


def test_a_stray_close_tag_is_a_legitimate_fragment():
    result = format_xml_selection("</b></a>", 0, 8)
    assert result.ok and result.text == "</b>\n</a>"


def test_selection_offsets_are_clamped_and_reversed_order_tolerated():
    document = "<a><b/></a>"
    assert format_xml_selection(document, -50, 5000).text == "<a>\n  <b/>\n</a>"
    assert format_xml_selection(document, 7, 3).ok  # end < start -> empty


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def assert_refused(document: str, start: int, end: int) -> list[Issue]:
    result = format_xml_selection(document, start, end)
    assert result.ok is False
    assert result.text == document[start:end], "a refusal must hand back the slice verbatim"
    assert result.issues, "a refusal must say why"
    assert all(issue.fatal for issue in result.issues)
    assert result.issues == sorted(result.issues, key=lambda i: (i.start, i.end))
    return result.issues


@pytest.mark.parametrize(
    "document, construct",
    [
        ('<a><Field name="x"/></a>', '<Field name="x"/>'),
        ("<a><!-- comment --></a>", "<!-- comment -->"),
        ("<a><![CDATA[ payload ]]></a>", "<![CDATA[ payload ]]>"),
        ("<a><?php echo 1; ?></a>", "<?php echo 1; ?>"),
        ("<!DOCTYPE root SYSTEM 'x'>\n<a/>", "<!DOCTYPE root SYSTEM 'x'>"),
    ],
)
def test_a_boundary_that_splits_a_construct_refuses_with_that_constructs_span(
    document, construct
):
    at = document.index(construct)
    # Cut the construct in half from the left, then from the right.
    for start, end in ((0, at + 3), (at + 3, len(document))):
        issues = assert_refused(document, start, end)
        assert len(issues) == 1
        assert (issues[0].start, issues[0].end) == (at, at + len(construct))
        assert "splits" in issues[0].message


def test_issue_offsets_and_line_columns_are_absolute_into_the_document():
    document = "<a>\n  <b>\n    <!-- here -->\n  </b>\n</a>\n"
    at = document.index("<!--")
    issues = assert_refused(document, document.index("<b>"), at + 6)
    assert (issues[0].start, issues[0].end) == (at, at + len("<!-- here -->"))
    assert (issues[0].start_line, issues[0].start_col) == (3, 5)
    assert issues[0].line == issues[0].start_line
    assert (issues[0].end_line, issues[0].end_col) == (3, 18)


@pytest.mark.parametrize(
    "document",
    [
        "<a><!-- unterminated",
        "<a><![CDATA[ unterminated",
        "<a><?php unterminated",
        "<a><!DOCTYPE unterminated",
        "<a><b unterminated",
    ],
)
def test_an_unterminated_construct_refuses_alone(document):
    issues = assert_refused(document, 0, len(document))
    assert len(issues) == 1, "reported alone -- no depth conclusion is drawn past it"
    assert "Unterminated" in issues[0].message
    assert (issues[0].start, issues[0].end) == (3, len(document))


def test_an_unterminated_construct_short_circuits_a_mis_nesting_that_follows_it():
    document = "<a><b></a></b><!-- x"
    issues = assert_refused(document, 0, len(document))
    assert len(issues) == 1 and "Unterminated" in issues[0].message


@pytest.mark.parametrize(
    "document, close_tag",
    [
        ("<a><b></a></b>", "</a>"),
        ("<Fields><Field></Fields></Field>", "</Fields>"),
        ("<a>\n  <b>\n  </c>\n</a>", "</c>"),
    ],
)
def test_mis_nested_tags_within_the_selection_refuse(document, close_tag):
    issues = assert_refused(document, 0, len(document))
    assert len(issues) == 1
    at = document.index(close_tag)
    assert (issues[0].start, issues[0].end) == (at, at + len(close_tag))
    assert "Mis-nested" in issues[0].message


def test_mis_nesting_outside_the_selection_does_not_refuse():
    document = "<a><b></a></b>\n<c>\n<d/>\n</c>"
    start = document.index("<c>")
    result = format_xml_selection(document, start, len(document))
    assert result.ok, [issue.message for issue in result.issues]


def test_case_differing_close_tag_is_mis_nesting_because_xml_is_case_sensitive():
    issues = assert_refused("<Page></page>", 0, len("<Page></page>"))
    assert "Mis-nested" in issues[0].message


# --------------------------------------------------------------------------
# EOL handling
# --------------------------------------------------------------------------


@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"])
def test_the_dominant_eol_of_the_selection_is_preserved(eol):
    source = eol.join(["<a>", "<b>", "<c/>", "</b>", "</a>"])
    text = assert_idempotent(source, 0, len(source))
    assert text == eol.join(["<a>", "  <b>", "    <c/>", "  </b>", "</a>"])
    other = {"\n", "\r\n", "\r"} - {eol}
    for candidate in other:
        if candidate == "\r" and eol == "\r\n":
            continue  # \r is a substring of \r\n
        if candidate == "\n" and eol == "\r\n":
            continue
        assert candidate not in text


def test_a_minified_selection_with_no_eol_at_all_uses_lf():
    assert whole("<a><b/></a>").text == "<a>\n  <b/>\n</a>"


def test_a_mixed_eol_selection_converges_on_the_winner():
    source = "<a>\r\n<b/>\r\n<c/>\n</a>"
    text = assert_idempotent(source, 0, len(source))
    assert text == "<a>\r\n  <b/>\r\n  <c/>\r\n</a>"


# --------------------------------------------------------------------------
# Idempotence and the preservation invariant, over the whole corpus
# --------------------------------------------------------------------------


CORPUS = [
    PGTP,
    "<a><b><c/></b><d>x</d></a>",
    "<a>\n<!-- <b/> -->\n<![CDATA[<c/>]]>\n<?pi <d/> ?>\n</a>",
    '<Project>\n<Event name="x">a\n  b</Event>\n<Fields>\n<Field/>\n</Fields>\n</Project>',
    "<a>\r\n\t<b>\r\n<c/>\r\n\t</b>\r\n</a>",
    "<a>   </a>",
    "<a></a>",
    "<a/>",
    "text only, no tags at all",
    "<a>mixed <b>content</b> here</a>\n<e/>",
    "<!DOCTYPE x [ <!ELEMENT a (b)> ]>\n<x>\n<y/>\n</x>",
]


@pytest.mark.parametrize("source", CORPUS)
def test_formatting_is_idempotent_over_the_corpus(source):
    assert_idempotent(source, 0, len(source))


@pytest.mark.parametrize("source", CORPUS)
def test_non_whitespace_bytes_are_preserved_over_the_corpus(source):
    result = whole(source)
    assert result.ok
    assert significant(result.text) == significant(source)


@pytest.mark.parametrize(
    "document, start, end",
    [
        (PGTP, PGTP.index("<Fields>"), PGTP.index("</Fields>") + len("</Fields>")),
        (PGTP, 0, PGTP.index("<Fields>")),
        (PGTP, PGTP.index("<Field "), PGTP.index("</Page>")),
    ],
)
def test_formatting_a_sub_selection_is_idempotent(document, start, end):
    assert_idempotent(document, start, end)


@pytest.mark.parametrize(
    "document, start, end",
    [
        ("<a><!-- x --></a>", 0, len("<a><!-- x")),
        ("<a><b></a></b>", 0, 14),
        ("<a><!-- x", 0, 9),
    ],
)
def test_refusal_is_idempotent_too(document, start, end):
    """A refused selection is handed back verbatim, so refusing again is the
    same refusal -- a caller that blindly writes `text` back changes nothing."""
    first = format_xml_selection(document, start, end)
    assert not first.ok
    assert document[:start] + first.text + document[end:] == document
    second = format_xml_selection(document, start, start + len(first.text))
    assert second.ok is False and second.text == first.text
    assert [i.message for i in second.issues] == [i.message for i in first.issues]


def test_result_shape_is_the_sql_engines_own_types():
    """Not a twin: the host renders one span-underline for both engines."""
    result = whole("<a/>")
    assert isinstance(result, FormatResult)
    refused = format_xml_selection("<a><b></a></b>", 0, 14)
    assert all(isinstance(issue, Issue) for issue in refused.issues)
