# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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


def _rows_for_ddl_table(table) -> list[RowSpec]:
    """Two `RowSpec` rows per column of a DDL Explorer `TableInfo` (§18.1,
    2026-08-05) -- the Properties panel's first non-XML source, and its
    first "grouped pair of rows per record" (every other `_rows_for_*`
    builder here emits exactly one row per logical attribute).

    Row 1 (identity line) -- `property_label` is the column name, `value` is
    `"{data_type}, {NULL|NOT NULL}"`. Row 2 (detail line) -- `property_label`
    is blank so it visually reads as a continuation of row 1 rather than a
    new named property, `value` is `"default: {...}  comment: {...}"` (`—`
    standing in for an unset default/comment). Both rows carry
    `attr_name=None` and `target_line=None`: a DDL table has no single XML
    source line a column maps to, so these rows are navigate-to-nothing,
    exactly like the Representations divider row above.

    Columns are emitted in `TableInfo.columns`'s own declared order --
    reproducing that order (not re-sorting) is the settled part; pixel/color
    pairing treatment between column-pairs is `PropertiesPanel`'s job, not
    this pure function's."""
    rows: list[RowSpec] = []
    for column in table.columns:
        nullability = "NULL" if column.is_nullable else "NOT NULL"
        rows.append(
            RowSpec(
                property_label=column.name,
                value=f"{column.data_type}, {nullability}",
                target_line=None,
                attr_name=None,
            )
        )
        rows.append(
            RowSpec(
                property_label="",
                value=f"default: {column.default or '—'}  comment: {column.comment or '—'}",
                target_line=None,
                attr_name=None,
            )
        )
    return rows


from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.schema_learning.settings_index import value_label

_READ_ONLY_HINT = "Read-only — click a row to edit in the XML editor"

#: Alternating-shade pairing cue for `_rows_for_ddl_table`'s two-rows-per-
#: column grouping (§18.1, 2026-08-05) -- the first "these N rows are one
#: record" convention this panel has needed. A subtle tint, applied to every
#: other column-pair (rows 0-1, then 4-5, then 8-9, ...) so the eye groups
#: each identity/detail row pair without a third "group ID" field on
#: `RowSpec` itself -- purely a row-index computation (2 rows per record).
_PAIR_SHADE_COLOR = QColor(0, 0, 0, 18)

_EMPTY_STATE_MESSAGE = "Select a Page, Detail, Column, or Event to see its properties"

_ROW_BUILDERS = {
    "page": (lambda n: _rows_for_attrib_node(n), lambda n: f"Page: {n.file_name or n.identity}"),
    "detail": (_rows_for_detail, lambda n: f"Detail: {n.table_name}/{n.attrib.get('caption', '')}"),
    "column": (_rows_for_column, lambda n: f"Column: {n.field_name}"),
    # §17/FQ-003's merged coherence view mints lookup rows whose model node IS
    # the owning ColumnNode (the column carrying the <Lookup>), so the column
    # builder and header are exactly right -- no separate lookup builder.
    "lookup": (_rows_for_column, lambda n: f"Column: {n.field_name}"),
    "event": (_rows_for_event, lambda n: f"Event: {n.tag_name}"),
    # DDL Explorer's Tables branch (§18.1, 2026-08-05) -- the panel's first
    # non-XML source. `t` is a `db.introspect.TableInfo`.
    "ddl_table": (_rows_for_ddl_table, lambda t: f"Table: {t.name}"),
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
        self._schema_model = None

        self._header_label = QLabel("")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        # Explicit read-only contract: no cell may ever be edited via the UI.
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setToolTip(_READ_ONLY_HINT)
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
        builder = _ROW_BUILDERS.get(kind)
        if builder is None:
            # An unknown kind is a wiring gap, not a user error: degrade to the
            # empty state instead of letting a KeyError escape into the Qt slot
            # that called us (BUG-032 facet B).
            self._show_empty_state()
            return
        rows_fn, header_fn = builder
        self._current_rows = rows_fn(node)
        self._populate_table(header_fn(node), self._current_rows, paired=(kind == "ddl_table"))

    def set_schema_model(self, model) -> None:
        """Inject the curated schema model (or None). Labels decorate
        attribute values as 'value — label' (spec §10); display-only."""
        self._schema_model = model

    def _display_value(self, spec: RowSpec) -> str:
        if (
            self._schema_model is None
            or spec.attr_name is None
            or spec.target_line is None
        ):
            return spec.value
        line_text = self._xml_editor.line_text(spec.target_line)
        needle = f'{spec.attr_name}="'
        index = line_text.find(needle)
        if index == -1:
            return spec.value
        block = self._xml_editor.document().findBlockByNumber(spec.target_line - 1)
        if not block.isValid():
            return spec.value
        resolved = self._xml_editor.resolve_attribute_at(block.position() + index + 1)
        if resolved is None:
            return spec.value
        chain, attr = resolved
        label = value_label(self._schema_model, chain, attr, spec.value)
        return f"{spec.value} — {label}" if label else spec.value

    def _show_empty_state(self) -> None:
        self._current_rows = []
        self._stack.setCurrentWidget(self._empty_label)

    def _populate_table(self, header_text: str, rows: list[RowSpec], paired: bool = False) -> None:
        self._header_label.setText(header_text)
        self.table.setRowCount(len(rows))
        for row_index, row_spec in enumerate(rows):
            # Every other 2-row record gets a subtle shade (rows 0-1, then
            # 4-5, ...) so the eye groups each pair (§18.1's ddl_table rows,
            # 2026-08-05) -- a no-op shade=False for every other `kind`,
            # which still emits exactly one row per attribute and never asks
            # for pairing.
            shaded = paired and (row_index // 2) % 2 == 1
            self.table.setItem(row_index, 0, self._make_item(row_spec.property_label, shaded))
            self.table.setItem(row_index, 1, self._make_item(self._display_value(row_spec), shaded))
        self._stack.setCurrentWidget(self._populated_page)

    @staticmethod
    def _make_item(text: str, shaded: bool = False) -> QTableWidgetItem:
        """Build a read-only table item: the editable flag is explicitly
        cleared so no cell can ever be edited (belt-and-suspenders with the
        table's NoEditTriggers). `shaded` paints a subtle background tint --
        the ddl_table column-pair grouping cue (§18.1, 2026-08-05)."""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if shaded:
            item.setBackground(_PAIR_SHADE_COLOR)
        return item

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
