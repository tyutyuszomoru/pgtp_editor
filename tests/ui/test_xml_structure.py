from pgtp_editor.ui.xml_structure import TagSpan, scan


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
