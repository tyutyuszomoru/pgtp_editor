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
from PySide6.QtWidgets import (
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.ddl_buffer import DdlObjectSpan
from pgtp_editor.db.ddl_project import DriftMarkers, routine_ddl_paths, trigger_ddl_path
from pgtp_editor.db.introspect import DatabaseSchema
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

_SPAN_ROLE = Qt.ItemDataRole.UserRole
#: A table node's `TableInfo`, keyed on a role distinct from `_SPAN_ROLE` so
#: a table row (click -> Properties panel, §18.1) and a trigger/routine row
#: (click -> `navigate_requested`) never collide on the same item.
_TABLE_ROLE = Qt.ItemDataRole.UserRole + 1
#: Which top-level branch an item IS (not which branch it sits under) --
#: `"tables"` / `"routines"`. Only the two branch roots carry it, so the
#: context menu can offer FQ-002's creation entries on a root without
#: string-matching the visible label.
_BRANCH_ROLE = Qt.ItemDataRole.UserRole + 2
#: An object row's `DdlObjectRef.key` -- the SAME identity `CenterStage` keys
#: editable tabs on (BUG-033). Carried on the row so the "an open tab has
#: unsaved edits for this object" overlay can find its rows without
#: re-deriving overload disambiguation through `resolve_edit_target`, and
#: without any index-based tracking that a `set_schema` rebuild would stale.
_OBJKEY_ROLE = Qt.ItemDataRole.UserRole + 3
#: `(label without the unsaved-edit marker, drift already showed a "*")`, so
#: the overlay can be applied and removed repeatedly without re-parsing the
#: visible text or ever stacking two `*`s on one row.
_LABEL_ROLE = Qt.ItemDataRole.UserRole + 4

#: The one unsaved/changed glyph in this app (§11/§18.2/§18.5): the editable
#: tab's title marker and the §18.2 `locally_edited` drift marker are both
#: `*`, so the tree uses it too rather than inventing a third glyph.
_DIRTY_MARKER = "*"

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

    #: Right-click ▸ Check Out for Versioning on an object row (spec §18.2).
    #: Same payload shape as `edit_requested` -- checkout is a second variant
    #: of the Edit… gesture, not a second tab type or a second editor.
    checkout_requested = Signal(object, str)

    #: Left-click on a Tables-branch table node (spec §18.1, 2026-08-05):
    #: carries the clicked table's `TableInfo` so `MainWindow` can populate
    #: the shared `PropertiesPanel` (`show_node(table_info, "ddl_table")`).
    #: Click-only for Edit…/Check Out -- a whole table has no single
    #: `DdlObjectSpan`/source text for those to act on. It DOES carry a
    #: context menu for *creation* (see `add_trigger_requested`), which needs
    #: no source span precisely because the object does not exist yet.
    table_selected = Signal(object)

    #: Right-click ▸ Add Trigger… on a Tables-branch table node (FQ-002).
    #: Carries the clicked table's `TableInfo`. This is the carve-out to
    #: §18.1's original "table nodes have no context menu" rule: that rule
    #: exists because Edit…/Check Out need a source span, and a
    #: not-yet-created trigger has none to need.
    add_trigger_requested = Signal(object)

    #: Right-click ▸ New Function/Procedure… on the "Functions & Procedures"
    #: branch root (FQ-002). Carries nothing -- unlike a trigger, a routine is
    #: not scoped to a specific parent object, so there is no context to pass.
    new_routine_requested = Signal()

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

        #: `DdlObjectRef.key`s whose editable tab currently holds unsaved
        #: edits (BUG-033 layer a). Held on the PANEL, not on tree items: the
        #: tree is rebuilt wholesale by every `set_schema`, so anything keyed
        #: on an item/index would go stale on the next refresh -- this set
        #: survives the rebuild and is re-applied to the new rows.
        #:
        #: Deliberately independent of `drift_markers`, which is `None`
        #: projectless: an unsaved edit is a property of the editor buffer,
        #: not of a project's deploy state, so this marker works with no
        #: project open at all.
        self._dirty_keys: set[tuple] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

    def set_schema(
        self,
        schema: DatabaseSchema,
        spans: list[DdlObjectSpan],
        drift_markers: dict[str, DriftMarkers] | None = None,
    ) -> None:
        """Rebuild the tree from ``schema`` (routines/triggers) and the
        ``DdlObjectSpan`` index of the buffer they were rendered into.

        `drift_markers` (§18.2, keyed by `ddl/*.sql` relative path, from
        `db/ddl_project.py::compute_drift_markers`) renders the combinable
        `*`/`!` state markers on each object row when a project is open;
        `None` (no project) renders nothing, exactly as before."""
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

        markers = drift_markers or {}
        self._build_tables_branch(schema, span_by_trigger, markers)
        self._build_routines_branch(schema, span_by_routine, span_by_trigger, markers)
        # Re-apply the surviving unsaved-edit overlay to the rows that were
        # just rebuilt (BUG-033): a refresh must not drop the `*` of a tab
        # that is still open and still dirty.
        self._apply_dirty_markers()

    # -- unsaved-edit overlay (BUG-033) ---------------------------------------

    def set_object_dirty(self, ref, dirty: bool) -> None:
        """Record whether the editable tab for `ref` holds unsaved edits, and
        repaint its row(s) accordingly (BUG-033 layer a).

        `ref` is a `DdlObjectRef` (or any object exposing `.key`), or the key
        tuple itself. The `*` this adds is the SAME glyph §18.2's
        `locally_edited` drift marker uses, and the two collapse rather than
        stack: a row already carrying a drift `*` gains nothing, so the user
        never sees `**`. Semantically they are distinct facts ("the checked-out
        file differs from the last-deployed reference" vs. "an open tab has
        unsaved changes"), but both mean "this object has changes that are not
        in the database yet", which is what the glyph promises.

        Works with no project open -- see `_dirty_keys`.
        """
        key = getattr(ref, "key", ref)
        if dirty:
            self._dirty_keys.add(key)
        else:
            self._dirty_keys.discard(key)
        self._apply_dirty_markers()

    def is_object_dirty(self, ref) -> bool:
        """Whether `ref` is currently overlaid as having unsaved edits."""
        return getattr(ref, "key", ref) in self._dirty_keys

    def _apply_dirty_markers(self) -> None:
        """Relabel every object row from its stored base label + the current
        dirty overlay. Relabelling in place rather than re-running
        `set_schema` keeps this independent of the `spans` the tree was built
        from, so a dirty-state change costs no re-derivation."""
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value() is not None:
            item = iterator.value()
            stored = item.data(0, _LABEL_ROLE)
            if stored is not None:
                base, drift_text = stored
                marker = drift_text
                if item.data(0, _OBJKEY_ROLE) in self._dirty_keys and _DIRTY_MARKER not in marker:
                    # Prepended, not appended, so a `!`-drifted object with an
                    # unsaved edit reads as the established `*!` combination
                    # rather than a novel `! *`.
                    marker = _DIRTY_MARKER + marker
                item.setText(0, f"{base} {marker}" if marker else base)
            iterator += 1

    @staticmethod
    def _remember_label(item: QTreeWidgetItem, base: str, key: tuple, drift) -> None:
        """Stash an object row's identity, its marker-free label and its §18.2
        drift marker text, so `_apply_dirty_markers` can compose the two
        idempotently instead of string-editing the visible text."""
        item.setData(0, _OBJKEY_ROLE, key)
        item.setData(0, _LABEL_ROLE, (base, drift.marker_text if drift is not None else ""))

    def _build_tables_branch(self, schema: DatabaseSchema, span_by_trigger, markers) -> None:
        """Every table in `schema.tables` gets a node (2026-08-05 widening --
        the branch previously derived its whole node set from
        `schema.triggers`, so a table with zero triggers never got a node at
        all). Trigger grouping is folded in by `(schema_name, table_name)`
        lookup for whichever tables also appear in `by_table`; a table with
        triggers keeps its existing `(N)`-suffixed/nested presentation, a
        table with none is a plain leaf (bare `schema.table`, no children).

        `by_table`'s keys are also unioned in (not just `schema.tables`'s)
        so a trigger on a table this `DatabaseSchema` has no `TableInfo` for
        (e.g. callers/tests that populate `triggers` without `tables`) still
        renders exactly as before -- this widening is additive, never a
        narrowing of what used to show up."""
        by_table: dict[tuple[str, str], list] = {}
        for trigger in schema.triggers.values():
            by_table.setdefault((trigger.schema, trigger.table), []).append(trigger)

        table_keys: set[tuple[str, str]] = set(by_table)
        for qualified in schema.tables:
            schema_name, _, table_name = qualified.partition(".")
            table_keys.add((schema_name, table_name))

        tables_root = QTreeWidgetItem(["Tables"])
        tables_root.setData(0, _BRANCH_ROLE, "tables")
        self.tree.addTopLevelItem(tables_root)
        for schema_name, table_name in sorted(table_keys):
            triggers = sorted(by_table.get((schema_name, table_name), []), key=lambda t: t.name)
            if triggers:
                label = f"{schema_name}.{table_name}  ({len(triggers)})"
            else:
                label = f"{schema_name}.{table_name}"
            table_item = QTreeWidgetItem([label])
            table_info = schema.tables.get(f"{schema_name}.{table_name}")
            if table_info is not None:
                table_item.setData(0, _TABLE_ROLE, table_info)
            tables_root.addChild(table_item)
            for trigger in triggers:
                span = span_by_trigger.get((trigger.schema, trigger.table, trigger.name))
                self._add_trigger_leaf(table_item, trigger, span, markers)

    def _build_routines_branch(
        self, schema: DatabaseSchema, span_by_routine, span_by_trigger, markers
    ) -> None:
        triggers_by_function: dict[tuple[str, str], list] = {}
        for trigger in schema.triggers.values():
            triggers_by_function.setdefault(
                (trigger.schema, trigger.function_name), []
            ).append(trigger)

        routines_root = QTreeWidgetItem(["Functions & Procedures"])
        routines_root.setData(0, _BRANCH_ROLE, "routines")
        self.tree.addTopLevelItem(routines_root)
        # Argument types are the final sort key so two overloads sharing a
        # `schema.name` keep a stable, reproducible order -- the same tiebreak
        # `build_ddl_text` applies, so tree order matches buffer order.
        routines = sorted(
            schema.routines.values(),
            key=lambda r: (r.schema, r.name, tuple(r.arg_types)),
        )
        routine_paths = routine_ddl_paths(schema.routines) if markers else {}
        for routine in routines:
            marker = _routine_marker(routine)
            qualified = f"{routine.schema}.{routine.name}"
            # Only a zero-argument routine carries the empty "()" on its top
            # line; a routine with input args lists them as child leaves
            # instead of a parenthesised signature (§18.1).
            label = (
                f"{qualified} [{marker}]" if routine.args else f"{qualified}() [{marker}]"
            )
            drift = markers.get(routine_paths.get(routine.signature))
            # The §18.2 `*`/`!` marker text is NOT appended here: it is stored
            # alongside the base label and composed with the unsaved-edit
            # overlay by `_apply_dirty_markers`, which `set_schema` runs once
            # the whole tree is built. One place composes markers.
            routine_item = QTreeWidgetItem([label])
            self._remember_label(
                routine_item,
                label,
                (routine.kind, routine.schema, routine.name, None, tuple(routine.arg_types)),
                drift,
            )
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
                self._add_trigger_leaf(routine_item, trigger, trigger_span, markers)

    def _add_trigger_leaf(self, parent: QTreeWidgetItem, trigger, span, markers=None) -> None:
        """Composite trigger label, identical in both branches (§18.1):
        ``schema.table.name`` + timing indicator + one indicator per event.
        The `*`/`!` drift marker (§18.2) named by `markers` for this trigger's
        `ddl/*.sql` path is stored, not appended -- `_apply_dirty_markers`
        composes it with the unsaved-edit overlay (BUG-033)."""
        timing = _TIMING_LETTERS.get(trigger.timing, "?")
        events = "".join(
            f"[{_EVENT_LETTERS.get(event, '?')}]" for event in trigger.events
        )
        label = f"{trigger.schema}.{trigger.table}.{trigger.name} [{timing}]{events}"
        drift = None
        if markers:
            relpath = trigger_ddl_path(trigger.schema, trigger.table, trigger.name)
            drift = markers.get(relpath)
        leaf = QTreeWidgetItem([label])
        # A trigger renders as TWO leaves (Tables branch + under its function,
        # §18.1); both carry the same key, so the overlay marks both -- one
        # object, consistently marked wherever it is shown.
        self._remember_label(
            leaf, label, ("trigger", trigger.schema, trigger.name, trigger.table, ()), drift
        )
        if span is not None:
            leaf.setData(0, _SPAN_ROLE, span)
        parent.addChild(leaf)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        span = item.data(0, _SPAN_ROLE)
        if span is not None:
            self.navigate_requested.emit(span.start_line)
            return
        table_info = item.data(0, _TABLE_ROLE)
        if table_info is not None:
            self.table_selected.emit(table_info)

    def _on_context_menu(self, pos) -> None:
        """Three distinct menus, keyed on what the clicked item IS.

        Object rows offer the existing *edit* gestures, which need a source
        span. Table nodes and the routines branch root offer FQ-002's
        *creation* gestures, which deliberately need no span -- the object
        being created does not exist yet, so there is nothing to read a
        definition from. That asymmetry is why §18.1's original "table nodes
        have no context menu" rule could be carved out for creation without
        weakening the reason it was written.
        """
        item = self.tree.itemAt(pos)
        if item is None:
            return
        menu = self._menu_for_item(item)
        if menu is None:
            return
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _menu_for_item(self, item) -> "QMenu | None":
        """The menu for `item`, or `None` when it offers nothing.

        Split out from `_on_context_menu` so tests can assert the offered
        entries without driving a modal `exec()`.
        """
        span = item.data(0, _SPAN_ROLE)
        if span is not None:
            if self._schema is None:
                return None
            resolved = resolve_edit_target(self._schema, span)
            if resolved is None:
                return None
            ref, source = resolved
            menu = QMenu(self)
            menu.addAction(
                f"Edit {ref.qualified}…", lambda: self.edit_requested.emit(ref, source)
            )
            menu.addAction(
                "Check Out for Versioning",
                lambda: self.checkout_requested.emit(ref, source),
            )
            return menu

        table_info = item.data(0, _TABLE_ROLE)
        if table_info is not None:
            menu = QMenu(self)
            menu.addAction(
                "Add Trigger…",
                lambda: self.add_trigger_requested.emit(table_info),
            )
            return menu

        if item.data(0, _BRANCH_ROLE) == "routines":
            menu = QMenu(self)
            menu.addAction(
                "New Function/Procedure…",
                lambda: self.new_routine_requested.emit(),
            )
            return menu

        # Argument-name child leaves and the Tables branch root carry neither a
        # span nor a creation context -- no menu at all, rather than an empty
        # one popping up under the cursor.
        return None
