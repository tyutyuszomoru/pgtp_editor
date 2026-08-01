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

"""BrowserPanel: the left-dock "DDL Explorer" tree (§18.1).

Dual-grouped, cross-referenced view over a freshly-introspected
`DatabaseSchema`'s routines and triggers: a "Tables" branch groups triggers by
the table they fire on; a "Functions & Procedures" branch lists every routine
with the triggers that invoke it nested beneath. A trigger therefore appears
as two leaves pointing at the same underlying `DdlObjectSpan` -- clicking
either emits the same `navigate_requested(line)`, mirroring the existing
Table References panel's precedent (§15, `TableUsage.references`) of showing
one object from multiple relationship angles rather than forcing a single
parent.

Grouping/matching is re-derived from scratch on every `set_schema` call --
this panel holds no cache of its own, matching this app's "recompute fresh,
never trust prior state" posture for DB-sourced data (§18's truth model).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from pgtp_editor.db.ddl_buffer import DdlObjectSpan
from pgtp_editor.db.introspect import DatabaseSchema

_SPAN_ROLE = Qt.ItemDataRole.UserRole


class BrowserPanel(QWidget):
    navigate_requested = Signal(int)  # 1-based line in the EditorPanel buffer

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

    def set_schema(self, schema: DatabaseSchema, spans: list[DdlObjectSpan]) -> None:
        """Rebuild the tree from ``schema`` (routines/triggers) and the
        ``DdlObjectSpan`` index of the buffer they were rendered into."""
        self.tree.clear()

        span_by_routine: dict[tuple[str, str], DdlObjectSpan] = {}
        span_by_trigger: dict[tuple[str, str, str], DdlObjectSpan] = {}
        for span in spans:
            if span.kind == "trigger":
                span_by_trigger[(span.schema, span.table, span.name)] = span
            else:
                span_by_routine[(span.schema, span.name)] = span

        self._build_tables_branch(schema, span_by_trigger)
        self._build_routines_branch(schema, span_by_routine, span_by_trigger)

    def _build_tables_branch(self, schema: DatabaseSchema, span_by_trigger) -> None:
        by_table: dict[tuple[str, str], list] = {}
        for trigger in schema.triggers.values():
            by_table.setdefault((trigger.schema, trigger.table), []).append(trigger)

        tables_root = QTreeWidgetItem(["Tables"])
        self.tree.addTopLevelItem(tables_root)
        for schema_name, table_name in sorted(by_table):
            triggers = sorted(by_table[(schema_name, table_name)], key=lambda t: t.name)
            table_item = QTreeWidgetItem([f"{schema_name}.{table_name}  ({len(triggers)})"])
            tables_root.addChild(table_item)
            for trigger in triggers:
                span = span_by_trigger.get((trigger.schema, trigger.table, trigger.name))
                self._add_trigger_leaf(table_item, trigger, span, show_table=False)

    def _build_routines_branch(self, schema: DatabaseSchema, span_by_routine, span_by_trigger) -> None:
        triggers_by_function: dict[tuple[str, str], list] = {}
        for trigger in schema.triggers.values():
            triggers_by_function.setdefault(
                (trigger.schema, trigger.function_name), []
            ).append(trigger)

        routines_root = QTreeWidgetItem(["Functions & Procedures"])
        self.tree.addTopLevelItem(routines_root)
        for routine in sorted(schema.routines.values(), key=lambda r: (r.schema, r.name)):
            marker = "F" if routine.kind == "function" else "P"
            args = ", ".join(routine.arg_types)
            routine_item = QTreeWidgetItem([f"{routine.name}({args})  [{marker}]"])
            span = span_by_routine.get((routine.schema, routine.name))
            if span is not None:
                routine_item.setData(0, _SPAN_ROLE, span)
            routines_root.addChild(routine_item)

            calling_triggers = sorted(
                triggers_by_function.get((routine.schema, routine.name), []),
                key=lambda t: t.name,
            )
            for trigger in calling_triggers:
                trigger_span = span_by_trigger.get(
                    (trigger.schema, trigger.table, trigger.name)
                )
                self._add_trigger_leaf(routine_item, trigger, trigger_span, show_table=True)

    def _add_trigger_leaf(self, parent: QTreeWidgetItem, trigger, span, *, show_table: bool) -> None:
        events = ",".join(trigger.events)
        if show_table:
            label = f"{trigger.name}  ({trigger.timing}/{events}) on {trigger.table}"
        else:
            label = f"{trigger.name}  ({trigger.timing}/{events}) → {trigger.function_name}"
        leaf = QTreeWidgetItem([label])
        if span is not None:
            leaf.setData(0, _SPAN_ROLE, span)
        parent.addChild(leaf)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        span = item.data(0, _SPAN_ROLE)
        if span is not None:
            self.navigate_requested.emit(span.start_line)
