from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView

from pgtp_editor.model.nodes import ColumnNode, DetailNode, EventNode, PageNode
from pgtp_editor.ui.properties_panel import PropertiesPanel


class _RecordingXmlEditorStub:
    """Test double standing in for the not-yet-merged XmlEditor. Records
    every call so tests can assert on navigation behavior without a real
    XML Editor widget existing in this worktree yet."""

    def __init__(self, line_text_by_line: dict[int, str] | None = None):
        self.navigate_calls: list[int] = []
        self.line_text_calls: list[int] = []
        self.select_range_calls: list[tuple[int, int, int]] = []
        self._line_text_by_line = line_text_by_line or {}

    def navigate_to_line(self, line: int) -> None:
        self.navigate_calls.append(line)

    def line_text(self, line: int) -> str:
        self.line_text_calls.append(line)
        return self._line_text_by_line.get(line, "")

    def select_range_on_line(self, line: int, start: int, end: int) -> None:
        self.select_range_calls.append((line, start, end))


def _page_node():
    return PageNode(
        identity="equipment",
        attrib={"fileName": "development_equipment", "tableName": "pr.equipment"},
        sourceline=5,
    )


def _column_node():
    return ColumnNode(identity="tag", attrib={"fieldName": "tag", "caption": "Tag"}, sourceline=42)


def _detail_node():
    return DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment"},
        sourceline=10,
        inner_sourceline=25,
    )


def _event_node():
    return EventNode(identity="e", tag_name="OnRowProcess", side="C", text="function foo() {}", sourceline=7)


def test_empty_state_when_no_node_selected(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(None, None)
    assert panel.is_showing_empty_state() is True


def test_page_population_row_count_and_header(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    assert panel.is_showing_empty_state() is False
    assert panel.table.rowCount() == 2
    assert panel.header_text() == "Page: development_equipment"
    assert panel.table.item(0, 0).text() == "fileName"
    assert panel.table.item(0, 1).text() == "development_equipment"


def test_column_population(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_column_node(), "column")
    assert panel.table.rowCount() == 2
    assert panel.header_text() == "Column: tag"


def test_detail_population(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_detail_node(), "detail")
    assert panel.table.rowCount() == 2
    assert panel.header_text() == "Detail: pr.attachment/Sub-item"


def test_event_population_shows_client_server_and_functions(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_event_node(), "event")
    assert panel.table.rowCount() == 3
    assert panel.header_text() == "Event: OnRowProcess"
    assert panel.table.item(0, 0).text() == "Handler"
    assert panel.table.item(0, 1).text() == "OnRowProcess"
    assert panel.table.item(1, 1).text() == "Client"
    assert panel.table.item(2, 0).text() == "Functions"
    assert panel.table.item(2, 1).text() == "1"


def test_show_node_with_none_after_population_returns_to_empty_state(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    assert panel.is_showing_empty_state() is False
    panel.show_node(None, None)
    assert panel.is_showing_empty_state() is True


def test_click_page_row_navigates_to_sourceline(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    panel._on_row_clicked(0, 0)
    assert stub.navigate_calls == [5]


def test_click_detail_caption_row_uses_outer_sourceline(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_detail_node(), "detail")
    # Row 0 is "caption" per attrib dict insertion order.
    assert panel._current_rows[0].property_label == "caption"
    panel._on_row_clicked(0, 0)
    assert stub.navigate_calls == [10]


def test_click_detail_non_caption_row_uses_inner_sourceline(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_detail_node(), "detail")
    # Row 1 is "tableName" per attrib dict insertion order.
    assert panel._current_rows[1].property_label == "tableName"
    panel._on_row_clicked(1, 0)
    assert stub.navigate_calls == [25]


def test_click_attribute_row_selects_attribute_span(qtbot):
    stub = _RecordingXmlEditorStub(
        line_text_by_line={5: '  <Page fileName="development_equipment" tableName="pr.equipment">'}
    )
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    panel._on_row_clicked(0, 0)  # "fileName" row
    assert stub.navigate_calls == [5]
    assert stub.line_text_calls == [5]
    line_text = '  <Page fileName="development_equipment" tableName="pr.equipment">'
    expected_start = line_text.find('fileName="')
    expected_end = line_text.find('"', expected_start + len('fileName="')) + 1
    assert stub.select_range_calls == [(5, expected_start, expected_end)]


def test_click_attribute_row_refinement_failure_falls_back_gracefully(qtbot):
    # line_text does not contain 'fileName="' at all.
    stub = _RecordingXmlEditorStub(line_text_by_line={5: "  <Page />"})
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_page_node(), "page")
    panel._on_row_clicked(0, 0)
    assert stub.navigate_calls == [5]
    assert stub.line_text_calls == [5]
    assert stub.select_range_calls == []  # graceful fallback, never a crash


def test_click_event_functions_row_navigates_but_never_refines(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    panel.show_node(_event_node(), "event")
    functions_row_index = next(
        i for i, r in enumerate(panel._current_rows) if r.property_label == "Functions"
    )
    panel._on_row_clicked(functions_row_index, 0)
    assert stub.navigate_calls == [7]
    assert stub.line_text_calls == []
    assert stub.select_range_calls == []


def test_table_has_no_edit_triggers(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    assert panel.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


def test_no_cell_is_editable_for_every_node_kind(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    cases = [
        (_page_node(), "page"),
        (_detail_node(), "detail"),
        (_column_node(), "column"),
        (_event_node(), "event"),
    ]
    for node, kind in cases:
        panel.show_node(node, kind)
        for row in range(panel.table.rowCount()):
            for column in range(panel.table.columnCount()):
                item = panel.table.item(row, column)
                assert item is not None
                assert item.flags() & Qt.ItemFlag.ItemIsEditable == Qt.ItemFlag(0), (
                    f"cell ({row},{column}) editable for kind={kind}"
                )


def test_read_only_hint_present(qtbot):
    panel = PropertiesPanel(xml_editor=_RecordingXmlEditorStub())
    qtbot.addWidget(panel)
    assert "read-only" in panel.table.toolTip().lower()


def test_click_detail_row_with_none_target_line_does_not_crash(qtbot):
    stub = _RecordingXmlEditorStub()
    panel = PropertiesPanel(xml_editor=stub)
    qtbot.addWidget(panel)
    detail = DetailNode(
        identity="pr.attachment",
        attrib={"caption": "Sub-item", "tableName": "pr.attachment"},
        sourceline=10,
        inner_sourceline=None,
    )
    panel.show_node(detail, "detail")
    table_name_row_index = next(
        i for i, r in enumerate(panel._current_rows) if r.property_label == "tableName"
    )
    panel._on_row_clicked(table_name_row_index, 0)  # target_line is None
    assert stub.navigate_calls == []  # never called; nothing to navigate to
