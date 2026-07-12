from pgtp_editor.ui.xml_structure import TagSpan, scan
from pgtp_editor.ui.xml_structure import find_enclosing_open_tag, nesting_depth_at


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
