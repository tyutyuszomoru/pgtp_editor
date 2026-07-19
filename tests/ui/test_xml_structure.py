from pgtp_editor.ui.xml_structure import TagSpan, scan
from pgtp_editor.ui.xml_structure import find_enclosing_open_tag, nesting_depth_at
from pgtp_editor.ui.xml_structure import (
    closing_tag_start,
    matching_tag_target,
    parent_tag_target,
)


def test_scan_well_formed_nesting_produces_correct_depths_and_offsets():
    text = "<Page><Detail><Column/></Detail></Page>"
    spans = scan(text)

    by_name = {span.name: span for span in spans}
    assert set(by_name) == {"Page", "Detail", "Column"}

    page = by_name["Page"]
    assert page.depth == 0
    assert page.self_closing is False
    assert text[page.open_start:page.open_end] == "<Page>"
    assert page.close_end is not None
    assert text[page.close_end - len("</Page>"):page.close_end] == "</Page>"

    detail = by_name["Detail"]
    assert detail.depth == 1
    assert detail.self_closing is False
    assert text[detail.open_start:detail.open_end] == "<Detail>"
    assert text[detail.close_end - len("</Detail>"):detail.close_end] == "</Detail>"

    column = by_name["Column"]
    assert column.depth == 2
    assert column.self_closing is True
    assert text[column.open_start:column.open_end] == "<Column/>"
    assert column.close_end == column.open_end


def test_scan_returns_empty_list_for_empty_text():
    assert scan("") == []


def test_scan_returns_empty_list_for_text_with_no_tags():
    assert scan("just some plain text, no tags here") == []


def test_scan_tolerates_unclosed_tags_no_closes_at_all():
    text = "<Page><Detail>"
    spans = scan(text)

    assert len(spans) == 2
    by_name = {span.name: span for span in spans}
    assert by_name["Page"].close_end is None
    assert by_name["Detail"].close_end is None


def test_scan_tolerates_mismatched_tag_closing_outer_before_inner():
    text = "<Page><Detail></Page>"
    spans = scan(text)

    by_name = {span.name: span for span in spans}
    assert by_name["Page"].close_end == len(text)
    assert by_name["Detail"].close_end is None


def test_scan_tolerates_truncated_document_mid_attribute():
    text = '<Page fileName="foo'
    spans = scan(text)

    # The regex simply doesn't match an incomplete tag token: nothing
    # crashes, nothing incorrect is fabricated.
    assert spans == []


def test_scan_tolerates_stray_closing_tag_matching_nothing():
    text = "</Orphan><Page></Page>"
    spans = scan(text)

    by_name = {span.name: span for span in spans}
    assert set(by_name) == {"Page"}
    assert by_name["Page"].close_end == len(text)


def test_find_enclosing_open_tag_inside_nested_element():
    text = "<Page><Detail>text</Detail></Page>"
    # Position inside "text", between Detail's open tag and its close tag.
    position = text.index("text")
    assert find_enclosing_open_tag(text, position) == "Detail"


def test_find_enclosing_open_tag_at_top_level_between_children():
    text = "<Page><Detail></Detail><Detail></Detail></Page>"
    position = text.index("><Detail></Detail></Page>") + 1  # just after first </Detail>
    assert find_enclosing_open_tag(text, position) == "Page"


def test_find_enclosing_open_tag_inside_unclosed_tag():
    text = "<Page><Detail>"
    position = len(text)
    assert find_enclosing_open_tag(text, position) == "Detail"


def test_find_enclosing_open_tag_returns_none_after_everything_closed():
    text = "<Page></Page>"
    position = len(text)
    assert find_enclosing_open_tag(text, position) is None


def test_find_enclosing_open_tag_returns_none_for_position_before_any_tag():
    text = "  <Page></Page>"
    assert find_enclosing_open_tag(text, 0) is None


def test_nesting_depth_at_matches_enclosing_tag_depth():
    text = "<Page><Detail><Column/></Detail></Page>"
    position = text.index("<Column/>")
    assert nesting_depth_at(text, position) == 1  # inside Detail, which is depth 1


def test_nesting_depth_at_is_zero_when_no_enclosing_tag():
    text = "<Page></Page>"
    assert nesting_depth_at(text, len(text)) == 0


from pgtp_editor.ui.xml_structure import enclosing_tag_span, parent_tag_span


def test_enclosing_tag_span_inside_text_content_returns_innermost():
    text = "<Page><Detail>text</Detail></Page>"
    span = enclosing_tag_span(text, text.index("text"))
    assert span is not None
    assert span.name == "Detail"
    assert span.depth == 1


def test_enclosing_tag_span_inside_open_tag_delimiters_returns_that_span():
    text = "<Page><Detail>text</Detail></Page>"
    # Position between '<' and '>' of the <Detail> open tag.
    position = text.index("<Detail>") + 1
    span = enclosing_tag_span(text, position)
    assert span is not None
    assert span.name == "Detail"


def test_enclosing_tag_span_at_open_start_boundary_is_included():
    text = "<Page><Detail>text</Detail></Page>"
    position = text.index("<Detail>")  # exactly at Detail's open_start
    span = enclosing_tag_span(text, position)
    assert span is not None
    assert span.name == "Detail"


def test_enclosing_tag_span_in_intersibling_whitespace_returns_parent():
    text = "<Page>\n  <Detail></Detail>\n  <Detail></Detail>\n</Page>"
    # Position on the blank spot between the two </Detail> and <Detail>.
    first_close_end = text.index("</Detail>") + len("</Detail>")
    span = enclosing_tag_span(text, first_close_end + 1)  # in the "\n  " gap
    assert span is not None
    assert span.name == "Page"
    assert span.depth == 0


def test_enclosing_tag_span_outside_every_element_returns_none():
    text = "  <Page></Page>  "
    assert enclosing_tag_span(text, 0) is None  # leading whitespace
    assert enclosing_tag_span(text, len(text)) is None  # trailing whitespace


def test_enclosing_tag_span_self_closing_returns_that_span():
    text = "<Page><Column/></Page>"
    position = text.index("<Column/>") + 2  # inside the self-closing token
    span = enclosing_tag_span(text, position)
    assert span is not None
    assert span.name == "Column"
    assert span.self_closing is True
    assert text[span.open_start:span.close_end] == "<Column/>"


def test_enclosing_tag_span_repeated_sibling_names_returns_correct_instance():
    text = "<Root><Item>A</Item><Item>B</Item></Root>"
    span = enclosing_tag_span(text, text.index("B"))
    assert span is not None
    assert span.name == "Item"
    # The correct instance is the SECOND <Item>, identified by open_start.
    assert span.open_start == text.rindex("<Item>")


def test_enclosing_tag_span_tolerates_unclosed_tag():
    text = "<Page><Detail>"
    span = enclosing_tag_span(text, len(text))
    assert span is not None
    assert span.name == "Detail"


def test_parent_tag_span_of_leaf_returns_immediate_parent():
    text = "<Page><Detail><Column/></Detail></Page>"
    spans = scan(text)
    column = next(s for s in spans if s.name == "Column")
    parent = parent_tag_span(spans, column)
    assert parent is not None
    assert parent.name == "Detail"
    assert parent.depth == 1


def test_parent_tag_span_of_mid_level_returns_one_up():
    text = "<Page><Detail><Column/></Detail></Page>"
    spans = scan(text)
    detail = next(s for s in spans if s.name == "Detail")
    parent = parent_tag_span(spans, detail)
    assert parent is not None
    assert parent.name == "Page"
    assert parent.depth == 0


def test_parent_tag_span_of_top_level_returns_none():
    text = "<Page><Detail></Detail></Page>"
    spans = scan(text)
    page = next(s for s in spans if s.name == "Page")
    assert parent_tag_span(spans, page) is None


def test_parent_tag_span_repeated_sibling_names_finds_correct_single_parent():
    text = "<Root><Group><Item>A</Item></Group><Group><Item>B</Item></Group></Root>"
    spans = scan(text)
    # The <Item> containing "B" -- identified by open_start, not name.
    item_b = next(
        s for s in spans if s.name == "Item" and s.open_start == text.rindex("<Item>")
    )
    parent = parent_tag_span(spans, item_b)
    assert parent is not None
    assert parent.name == "Group"
    # It must be the SECOND Group (the one that actually contains item_b),
    # not the first Group with the same name.
    assert parent.open_start == text.rindex("<Group>")


_DOC = "<root>\n  <page>\n    <col/>\n  </page>\n</root>\n"


def test_closing_tag_start_finds_close_token():
    spans = scan(_DOC)
    page = next(s for s in spans if s.name == "page")
    assert closing_tag_start(_DOC, page) == _DOC.index("</page>")


def test_closing_tag_start_none_for_self_closing():
    spans = scan(_DOC)
    col = next(s for s in spans if s.name == "col")
    assert closing_tag_start(_DOC, col) is None


def test_matching_tag_target_open_to_close():
    spans = scan(_DOC)
    pos = _DOC.index("<page>") + 2  # inside the opening <page> tag
    assert matching_tag_target(spans, _DOC, pos) == _DOC.index("</page>")


def test_matching_tag_target_close_to_open():
    spans = scan(_DOC)
    pos = _DOC.index("</page>") + 2  # inside the closing </page> tag
    assert matching_tag_target(spans, _DOC, pos) == _DOC.index("<page>")


def test_matching_tag_target_self_closing_is_none():
    spans = scan(_DOC)
    pos = _DOC.index("<col/>") + 2
    assert matching_tag_target(spans, _DOC, pos) is None


def test_matching_tag_target_in_text_content_is_none():
    # position on the whitespace/text between <page> and <col/>, not on a tag
    spans = scan(_DOC)
    pos = _DOC.index("<page>") + len("<page>")  # just past '>' , in content
    assert matching_tag_target(spans, _DOC, pos) is None


def test_matching_tag_target_nested_resolves_own_partner():
    doc = "<a><b>x</b></a>"
    spans = scan(doc)
    pos = doc.index("<b>") + 1
    assert matching_tag_target(spans, doc, pos) == doc.index("</b>")


def test_parent_tag_target_nested_returns_parent_open_start():
    spans = scan(_DOC)
    pos = _DOC.index("<col/>") + 2      # enclosing = col, parent = page
    assert parent_tag_target(spans, pos) == _DOC.index("<page>")


def test_parent_tag_target_top_level_is_none():
    spans = scan(_DOC)
    pos = _DOC.index("<root>") + 2      # enclosing = root (top-level)
    assert parent_tag_target(spans, pos) is None


def test_parent_tag_target_outside_any_element_is_none():
    spans = scan(_DOC)
    assert parent_tag_target(spans, len(_DOC)) is None  # trailing newline, outside root


# --- deeper-nesting / edge cases (feature-tester gap fill) ---

_DEEP = "<a><b><c><d>x</d></c></b></a>"


def test_matching_tag_target_deep_nesting_resolves_innermost_not_ancestor():
    # Clicking the innermost <d> open tag must jump to </d>, never an
    # ancestor's close tag.
    spans = scan(_DEEP)
    pos = _DEEP.index("<d>") + 1
    assert matching_tag_target(spans, _DEEP, pos) == _DEEP.index("</d>")


def test_matching_tag_target_deep_nesting_close_resolves_own_open():
    spans = scan(_DEEP)
    pos = _DEEP.index("</c>") + 2
    assert matching_tag_target(spans, _DEEP, pos) == _DEEP.index("<c>")


def test_parent_tag_target_from_grandchild_returns_immediate_parent():
    # Enclosing of position in <d>'s content is <d>; its parent is <c>,
    # NOT the root <a>.
    spans = scan(_DEEP)
    pos = _DEEP.index("x")
    assert parent_tag_target(spans, pos) == _DEEP.index("<c>")


def test_parent_tag_target_from_mid_level_open_tag_returns_one_up():
    # Position inside <c>'s open tag -> enclosing is <c>, parent is <b>.
    spans = scan(_DEEP)
    pos = _DEEP.index("<c>") + 1
    assert parent_tag_target(spans, pos) == _DEEP.index("<b>")


def test_matching_tag_target_on_attribute_resolves_to_close():
    # The opening-tag region is [open_start, open_end), which includes the
    # attribute area. Per the spec's formal region definition a click anywhere
    # inside the open tag (attributes included) jumps to the close tag. (Note:
    # the spec/docstring prose "attribute value -> None" contradicts this
    # formal definition; the implementation follows the formal definition.)
    doc = '<page fileName="foo"><col/></page>'
    spans = scan(doc)
    pos = doc.index('"foo"') + 1
    assert matching_tag_target(spans, doc, pos) == doc.index("</page>")


def test_matching_tag_target_repeated_siblings_resolves_correct_instance():
    doc = "<root><item>A</item><item>B</item></root>"
    spans = scan(doc)
    # Click the SECOND <item> open tag; must jump to the SECOND </item>.
    pos = doc.rindex("<item>") + 1
    assert matching_tag_target(spans, doc, pos) == doc.rindex("</item>")
