# pgtp_editor/ui/properties_panel.py
"""The Properties panel: a read-only, navigate-only viewer of the currently
selected Page/Detail/Column/Event tree node's attributes.

Row-building is implemented as plain functions over the model dataclasses in
pgtp_editor.model.nodes, deliberately kept Qt-free so they are unit-testable
without a QApplication. PropertiesPanel (added in a later task) is the only
place that turns a list[RowSpec] into actual QTableWidgetItems.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RowSpec:
    property_label: str
    value: str
    target_line: int | None
    attr_name: str | None  # None for rows with no single key="value" to refine onto


def _rows_for_attrib_node(node) -> list[RowSpec]:
    """Shared helper for Page/Column: one row per attrib key, all rows
    navigating to the node's own sourceline."""
    return [
        RowSpec(property_label=key, value=str(value), target_line=node.sourceline, attr_name=key)
        for key, value in node.attrib.items()
    ]


def _rows_for_detail(detail_node) -> list[RowSpec]:
    """One row per Detail attrib key, with a per-row line split: the
    'caption' row navigates to the outer <Detail> element's own line
    (detail_node.sourceline); every other row navigates to the nested
    <Page> element's line (detail_node.inner_sourceline), since real
    .pgtp files only ever put 'caption' on the outer <Detail> and
    everything else (tableName, ability modes, etc.) on the nested Page.
    """
    rows = []
    for key, value in detail_node.attrib.items():
        line = detail_node.sourceline if key == "caption" else detail_node.inner_sourceline
        rows.append(RowSpec(property_label=key, value=str(value), target_line=line, attr_name=key))
    return rows


_FUNCTION_DECL_RE = re.compile(r"\bfunction\s*[A-Za-z_$][A-Za-z0-9_$]*\s*\(|\bfunction\s*\(")


def _count_functions(text: str | None) -> int:
    """Approximate, regex-based count of JS/PHP function declarations
    (named and anonymous) in an event handler body. Not a real parser:
    misses ES6 arrow functions entirely, and cannot distinguish a
    'function' token inside a string/comment from a real declaration.
    Both gaps are accepted — see design spec §3.3.
    """
    return len(_FUNCTION_DECL_RE.findall(text or ""))


def _rows_for_event(event_node) -> list[RowSpec]:
    """Exactly three rows for an EventNode: Handler, Side, and a
    heuristic Functions count. All three navigate to the event's own
    <OnXxx> opening line; none of them is a key="value" attribute pair,
    so attr_name is None for all three (no column-precise refinement)."""
    side_label = "Client" if event_node.side == "C" else "Server"
    return [
        RowSpec("Handler", event_node.tag_name, event_node.sourceline, attr_name=None),
        RowSpec("Side", side_label, event_node.sourceline, attr_name=None),
        RowSpec("Functions", str(_count_functions(event_node.text)), event_node.sourceline, attr_name=None),
    ]


_REPRESENTATIONS_DIVIDER = "— Representations —"


def _rows_for_column(column_node) -> list[RowSpec]:
    """Column attribute rows, then (if the column carries representation
    visibilities) a divider and one row per representation showing
    visible / hidden / — (not listed). Representation rows navigate to that
    column's <Column> entry line (attr_name=None -> no attribute selection);
    the divider and not-listed rows are non-navigating."""
    rows = _rows_for_attrib_node(column_node)
    representations = column_node.representations
    if representations:
        rows.append(RowSpec(_REPRESENTATIONS_DIVIDER, "", target_line=None, attr_name=None))
        for rep in representations:
            if rep.visible is True:
                value = "visible"
            elif rep.visible is False:
                value = "hidden"
            else:
                value = "— (not listed)"
            rows.append(RowSpec(rep.name, value, target_line=rep.sourceline, attr_name=None))
    return rows


from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_EMPTY_STATE_MESSAGE = "Select a Page, Detail, Column, or Event to see its properties"

_ROW_BUILDERS = {
    "page": (lambda n: _rows_for_attrib_node(n), lambda n: f"Page: {n.file_name or n.identity}"),
    "detail": (_rows_for_detail, lambda n: f"Detail: {n.table_name}/{n.attrib.get('caption', '')}"),
    "column": (_rows_for_column, lambda n: f"Column: {n.field_name}"),
    "event": (_rows_for_event, lambda n: f"Event: {n.tag_name}"),
}


class PropertiesPanel(QWidget):
    """Read-only, navigate-only viewer for the currently selected Page,
    Detail, Column, or Event node. Never edits a value; clicking a row
    calls into an injected xml_editor object's navigate_to_line (and,
    for attribute rows, line_text/select_range_on_line) to jump to and
    highlight the corresponding source location.
    """

    def __init__(self, xml_editor, parent=None):
        super().__init__(parent)
        self._xml_editor = xml_editor
        self._current_rows: list[RowSpec] = []

        self._header_label = QLabel("")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self._on_row_clicked)

        self._populated_page = QWidget()
        populated_layout = QVBoxLayout(self._populated_page)
        populated_layout.setContentsMargins(0, 0, 0, 0)
        populated_layout.addWidget(self._header_label)
        populated_layout.addWidget(self.table)

        self._empty_label = QLabel(_EMPTY_STATE_MESSAGE)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._empty_label)
        self._stack.addWidget(self._populated_page)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self._stack)

        self._show_empty_state()

    def is_showing_empty_state(self) -> bool:
        return self._stack.currentWidget() is self._empty_label

    def header_text(self) -> str:
        return self._header_label.text()

    def show_node(self, node, kind: str | None) -> None:
        if node is None or kind is None:
            self._show_empty_state()
            return
        rows_fn, header_fn = _ROW_BUILDERS[kind]
        self._current_rows = rows_fn(node)
        self._populate_table(header_fn(node), self._current_rows)

    def _show_empty_state(self) -> None:
        self._current_rows = []
        self._stack.setCurrentWidget(self._empty_label)

    def _populate_table(self, header_text: str, rows: list[RowSpec]) -> None:
        self._header_label.setText(header_text)
        self.table.setRowCount(len(rows))
        for row_index, row_spec in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(row_spec.property_label))
            self.table.setItem(row_index, 1, QTableWidgetItem(row_spec.value))
        self._stack.setCurrentWidget(self._populated_page)

    def _on_row_clicked(self, row: int, _column: int) -> None:
        spec = self._current_rows[row]
        if spec.target_line is None:
            return
        self._xml_editor.navigate_to_line(spec.target_line)
        if spec.attr_name is not None:
            self._select_attribute_on_line(spec.target_line, spec.attr_name)

    def _select_attribute_on_line(self, line: int, attr_name: str) -> None:
        line_text = self._xml_editor.line_text(line)
        needle = f'{attr_name}="'
        start = line_text.find(needle)
        if start == -1:
            return
        value_start = start + len(needle)
        end = line_text.find('"', value_start)
        if end == -1:
            return
        self._xml_editor.select_range_on_line(line, start, end + 1)
