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
