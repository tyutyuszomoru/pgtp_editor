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
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from pgtp_editor.db.ddl_buffer import DdlObjectSpan
from pgtp_editor.db.introspect import DatabaseSchema
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

_SPAN_ROLE = Qt.ItemDataRole.UserRole

_TIMING_LETTERS = {"before": "B", "after": "A", "instead of": "I"}
_EVENT_LETTERS = {"insert": "I", "update": "U", "delete": "D", "truncate": "T"}


def _routine_marker(routine) -> str:
    """Three-way routine marker (§18.1): ``P``rocedure, ``T``rigger
    function (a function returning ``trigger``), or plain ``F``unction."""
    if routine.kind == "procedure":
        return "P"
    if routine.return_type == "trigger":
        return "T"
    return "F"


def resolve_edit_target(
    schema: DatabaseSchema, span: DdlObjectSpan
) -> tuple[DdlObjectRef, str] | None:
    """The `DdlObjectRef` + live source text for `span`, resolved against
    `schema` (spec §18.5, D1). Shared by both right-click ▸ Edit… entry
    points -- `BrowserPanel.tree` here and the read-only DDL `EditorPanel`'s
    buffer (`ddl_editor_panel.py`) -- so routine/trigger identity is derived
    in exactly one place. Returns None if `schema` no longer has the object
    (a stale span -- shouldn't happen within one `set_schema` generation,
    guarded defensively)."""
    if span.kind == "trigger":
        trigger = schema.triggers.get(f"{span.schema}.{span.table}.{span.name}")
        if trigger is None:
            return None
        ref = DdlObjectRef(
            kind="trigger", schema=span.schema, name=span.name, table=span.table
        )
        return ref, trigger.definition
    routine = schema.routines.get(span.signature) if span.signature else None
    if routine is None:
        return None
    overloaded = (
        sum(
            1
            for other in schema.routines.values()
            if other.schema == routine.schema and other.name == routine.name
        )
        > 1
    )
    ref = DdlObjectRef(
        kind=routine.kind,
        schema=routine.schema,
        name=routine.name,
        arg_types=tuple(routine.arg_types),
        disambiguate=overloaded,
    )
    return ref, routine.source


class BrowserPanel(QWidget):
    navigate_requested = Signal(int)  # 1-based line in the EditorPanel buffer

    #: Right-click ▸ Edit… on an object row (spec §18.5, D1 entry point 1).
    #: Carries the object's `DdlObjectRef` and its current source text (the
    #: live `RoutineInfo.source` / `TriggerInfo.definition` this tree was
    #: built from) -- everything MainWindow needs to open or focus the
    #: editable tab, with no second lookup back into the schema.
    edit_requested = Signal(object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        # The schema this tree was last built from, so a later right-click ▸
        # Edit… can resolve a routine/trigger's full source text and overload
        # status without the tree items carrying redundant copies of it.
        self._schema: DatabaseSchema | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

    def set_schema(self, schema: DatabaseSchema, spans: list[DdlObjectSpan]) -> None:
        """Rebuild the tree from ``schema`` (routines/triggers) and the
        ``DdlObjectSpan`` index of the buffer they were rendered into."""
        self._schema = schema
        self.tree.clear()

        # Routine spans are keyed by the full signature, not `(schema, name)`:
        # two overloads share a `schema.name`, so that key gave both tree items
        # the same (last-wins) span and navigated them into one body (BUG-018).
        span_by_routine: dict[str, DdlObjectSpan] = {}
        span_by_trigger: dict[tuple[str, str, str], DdlObjectSpan] = {}
        for span in spans:
            if span.kind == "trigger":
                span_by_trigger[(span.schema, span.table, span.name)] = span
            elif span.signature is not None:
                span_by_routine[span.signature] = span

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
                self._add_trigger_leaf(table_item, trigger, span)

    def _build_routines_branch(self, schema: DatabaseSchema, span_by_routine, span_by_trigger) -> None:
        triggers_by_function: dict[tuple[str, str], list] = {}
        for trigger in schema.triggers.values():
            triggers_by_function.setdefault(
                (trigger.schema, trigger.function_name), []
            ).append(trigger)

        routines_root = QTreeWidgetItem(["Functions & Procedures"])
        self.tree.addTopLevelItem(routines_root)
        # Argument types are the final sort key so two overloads sharing a
        # `schema.name` keep a stable, reproducible order -- the same tiebreak
        # `build_ddl_text` applies, so tree order matches buffer order.
        routines = sorted(
            schema.routines.values(),
            key=lambda r: (r.schema, r.name, tuple(r.arg_types)),
        )
        for routine in routines:
            marker = _routine_marker(routine)
            qualified = f"{routine.schema}.{routine.name}"
            # Only a zero-argument routine carries the empty "()" on its top
            # line; a routine with input args lists them as child leaves
            # instead of a parenthesised signature (§18.1).
            label = (
                f"{qualified} [{marker}]" if routine.args else f"{qualified}() [{marker}]"
            )
            routine_item = QTreeWidgetItem([label])
            span = span_by_routine.get(routine.signature)
            if span is not None:
                routine_item.setData(0, _SPAN_ROLE, span)
            routines_root.addChild(routine_item)

            for arg_name, arg_type in routine.args:
                # Argument leaves are pure labels -- no span, so clicking one
                # navigates nowhere.
                routine_item.addChild(QTreeWidgetItem([f"{arg_name} ({arg_type})"]))

            calling_triggers = sorted(
                triggers_by_function.get((routine.schema, routine.name), []),
                key=lambda t: t.name,
            )
            for trigger in calling_triggers:
                trigger_span = span_by_trigger.get(
                    (trigger.schema, trigger.table, trigger.name)
                )
                self._add_trigger_leaf(routine_item, trigger, trigger_span)

    def _add_trigger_leaf(self, parent: QTreeWidgetItem, trigger, span) -> None:
        """Composite trigger label, identical in both branches (§18.1):
        ``schema.table.name`` + timing indicator + one indicator per event."""
        timing = _TIMING_LETTERS.get(trigger.timing, "?")
        events = "".join(
            f"[{_EVENT_LETTERS.get(event, '?')}]" for event in trigger.events
        )
        label = f"{trigger.schema}.{trigger.table}.{trigger.name} [{timing}]{events}"
        leaf = QTreeWidgetItem([label])
        if span is not None:
            leaf.setData(0, _SPAN_ROLE, span)
        parent.addChild(leaf)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        span = item.data(0, _SPAN_ROLE)
        if span is not None:
            self.navigate_requested.emit(span.start_line)

    def _on_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        span = item.data(0, _SPAN_ROLE)
        # Argument-name child leaves carry no span (§18.1) -- only object rows
        # (routine leaves and both trigger occurrences) offer Edit….
        if span is None or self._schema is None:
            return
        resolved = resolve_edit_target(self._schema, span)
        if resolved is None:
            return
        ref, source = resolved
        menu = QMenu(self)
        menu.addAction(f"Edit {ref.qualified}…", lambda: self.edit_requested.emit(ref, source))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
