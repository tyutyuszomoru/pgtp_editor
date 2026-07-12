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
