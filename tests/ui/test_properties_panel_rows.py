from pgtp_editor.model.nodes import ColumnNode, DetailNode, EventNode, PageNode
from pgtp_editor.ui.properties_panel import (
    RowSpec,
    _count_functions,
    _rows_for_attrib_node,
    _rows_for_detail,
    _rows_for_event,
)


def test_rows_for_page_one_row_per_attrib_key():
    page = PageNode(
        identity="equipment",
        attrib={"fileName": "development_equipment", "tableName": "pr.equipment"},
        sourceline=5,
    )
    rows = _rows_for_attrib_node(page)
    assert rows == [
        RowSpec(property_label="fileName", value="development_equipment", target_line=5, attr_name="fileName"),
        RowSpec(property_label="tableName", value="pr.equipment", target_line=5, attr_name="tableName"),
    ]


def test_rows_for_column_one_row_per_attrib_key():
    column = ColumnNode(identity="tag", attrib={"fieldName": "tag", "caption": "Tag"}, sourceline=42)
    rows = _rows_for_attrib_node(column)
    assert rows == [
        RowSpec(property_label="fieldName", value="tag", target_line=42, attr_name="fieldName"),
        RowSpec(property_label="caption", value="Tag", target_line=42, attr_name="caption"),
    ]


def test_rows_for_detail_caption_uses_outer_sourceline_others_use_inner():
    detail = DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment", "viewAbilityMode": "1"},
        sourceline=10,
        inner_sourceline=25,
    )
    rows = _rows_for_detail(detail)
    assert rows == [
        RowSpec(property_label="caption", value="Sub-item", target_line=10, attr_name="caption"),
        RowSpec(property_label="tableName", value="pr.attachment", target_line=25, attr_name="tableName"),
        RowSpec(property_label="viewAbilityMode", value="1", target_line=25, attr_name="viewAbilityMode"),
    ]


def test_rows_for_detail_missing_inner_sourceline_falls_back_to_none():
    detail = DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment"},
        sourceline=10,
        inner_sourceline=None,
    )
    rows = _rows_for_detail(detail)
    caption_row = next(r for r in rows if r.property_label == "caption")
    table_name_row = next(r for r in rows if r.property_label == "tableName")
    assert caption_row.target_line == 10
    assert table_name_row.target_line is None


def test_rows_for_event_client_side_label():
    event = EventNode(identity="e", tag_name="OnRowProcess", side="C", text="function foo() {}", sourceline=7)
    rows = _rows_for_event(event)
    assert rows == [
        RowSpec("Handler", "OnRowProcess", 7, attr_name=None),
        RowSpec("Side", "Client", 7, attr_name=None),
        RowSpec("Functions", "1", 7, attr_name=None),
    ]


def test_rows_for_event_server_side_label():
    event = EventNode(identity="e", tag_name="OnPreparePage", side="S", text="", sourceline=3)
    rows = _rows_for_event(event)
    side_row = next(r for r in rows if r.property_label == "Side")
    assert side_row.value == "Server"


def test_count_functions_named_declaration():
    assert _count_functions("function foo() {}") == 1


def test_count_functions_anonymous_no_space():
    assert _count_functions("function() {}") == 1


def test_count_functions_anonymous_with_space():
    assert _count_functions("function () {}") == 1


def test_count_functions_false_positive_substring_not_counted():
    assert _count_functions("functionallocation") == 0


def test_count_functions_arrow_function_not_counted_documented_gap():
    assert _count_functions("const f = (x) => x") == 0


def test_count_functions_empty_and_none_text():
    assert _count_functions("") == 0
    assert _count_functions(None) == 0


def test_count_functions_php_snippet_with_zero_functions():
    # Real OnCalculateFields-style body: a bare conditional, no function
    # declarations at all. "Functions: 0" is a common, correct result.
    body = "if ($fieldName == 'manning') { $value = $res[0]['manning']; }"
    assert _count_functions(body) == 0


def test_count_functions_synthetic_named_and_anonymous_mix():
    # A hand-built body exercising the same named+anonymous function mix
    # documented in the design spec's grounding pass against dev_Ferrara.pgtp's
    # real OnEditFormLoaded bodies (5 named functions plus several anonymous
    # callbacks passed as arguments). The real-sample regression test against
    # the actual file is added separately below, in test_parser_real_samples.py.
    body = """
    function setLoadingState() { }
    function setReadyState() { }
    function initLimit() { }
    function onOperationReady() { }
    function initJobcardDeps() { }
    setTimeout(function() { doStuff(); }, 100);
    $('.foo').setQueryFunction(function(term) { return term; });
    $('span.subs').each(function() { markDone(); });
    """
    assert _count_functions(body) == 8
