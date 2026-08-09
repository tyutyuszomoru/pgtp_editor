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
from pgtp_editor.ui.alter_column_dialogs import (
    OP_DROP_COLUMN,
    OP_DROP_DEFAULT,
    OP_DROP_NOT_NULL,
    OP_SET_NOT_NULL,
)
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.table_dialogs import OP_COLUMN_COMMENT, OP_TABLE_COMMENT

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
#: A column leaf's `(TableInfo, column name)` (FQ-025 slice 1). Its own role,
#: not `_TABLE_ROLE`, precisely because a column row must NOT behave like a
#: table row: it carries the click context an "Alter Table ▸" dialog defaults
#: its column dropdown to, which a table row has nothing to say about.
_COLUMN_ROLE = Qt.ItemDataRole.UserRole + 5

#: FQ-025 slice 1's eight column operations (slice 2's four constraint ones
#: follow below), as `(operation id, menu label)` pairs.
#:
#: The four ids `alter_column_dialogs.ColumnActionDialog` already owns are
#: IMPORTED rather than respelled here -- a second spelling of `"drop_column"`
#: is exactly how a menu item comes to open the wrong dialog. The other four
#: are declared here because each has a dialog class of its own and so needed
#: no id over there; the host maps all eight in one place
#: (`MainWindow._alter_column_dialog`).
OP_ADD_COLUMN = "add_column"
OP_RENAME_COLUMN = "rename_column"
OP_CHANGE_COLUMN_TYPE = "change_column_type"
OP_SET_DEFAULT = "set_default"

#: FQ-025 slice 2's four constraint operations. Their ids live here for the
#: same reason the four above do -- one spelling, read by the panel that emits
#: it and by the host that maps it to a dialog.
#:
#: There is deliberately NO `drop_foreign_key`: in Postgres a foreign key IS a
#: constraint and `DROP CONSTRAINT` is the identical statement for every type,
#: so the type is shown in `DropConstraintDialog`'s picker labels rather than
#: split across two menu entries that would generate the same SQL. That one
#: entry is also where a constraint-backed INDEX has to be dropped from (see
#: `db.introspect.IndexInfo`), so a future `Drop index` picker has somewhere to
#: route those rows to.
OP_ADD_CONSTRAINT = "add_constraint"
OP_ADD_FOREIGN_KEY = "add_foreign_key"
OP_DROP_CONSTRAINT = "drop_constraint"
OP_RENAME_CONSTRAINT = "rename_constraint"

#: FQ-025 slice 3's operations. Two are declared here like the ones above; the
#: two comment ids are IMPORTED from `table_dialogs`, where `SetCommentDialog`
#: already owns them as its `target=` values -- the same rule slice 1 followed
#: for `ColumnActionDialog`'s four, and for the same reason: a second spelling
#: of `"column_comment"` is how a menu item comes to open the wrong mode.
#:
#: `OP_CREATE_INDEX` and `OP_DROP_INDEX` sit on the `Alter Table ▸` submenu
#: although NEITHER emits `ALTER TABLE` (`CREATE INDEX … ON t` and
#: `DROP INDEX schema.name` are their own statements, and the latter names no
#: table at all). The submenu groups what is *scoped to this table* -- which is
#: the question the user is answering when they right-click one -- and its title
#: is the label of the commonest case, not a promise about the generated verb.
#: `OP_DROP_TABLE` rides along for the same reason, at the bottom.
OP_CREATE_INDEX = "create_index"
OP_DROP_INDEX = "drop_index"
OP_SET_TABLE_COMMENT = OP_TABLE_COMMENT
OP_SET_COLUMN_COMMENT = OP_COLUMN_COMMENT
OP_DROP_TABLE = "drop_table"

#: `Create Table…` -- NOT on the submenu, and not on `alter_column_requested`
#: either (see `create_table_requested`). It exists as an id only so the tab the
#: generation opens can name the operation it came from, exactly as the others
#: do via `AlterDdlRef.operation`.
OP_CREATE_TABLE = "create_table"

#: The groups the `Alter Table ▸` submenu is built from, in menu order.
#: Grouped rather than one flat tuple ONLY so separators can sit between them:
#: "what this table's columns are", "what its constraints are", "what its
#: indexes are", "what it says about itself" and "whether it exists at all" are
#: five different questions, and sixteen undifferentiated entries would read as
#: one long list. Everything else -- ids, labels, order -- still comes from
#: here alone.
ALTER_TABLE_COLUMN_ACTIONS: tuple[tuple[str, str], ...] = (
    (OP_ADD_COLUMN, "Add Column…"),
    (OP_DROP_COLUMN, "Drop Column…"),
    (OP_RENAME_COLUMN, "Rename Column…"),
    (OP_CHANGE_COLUMN_TYPE, "Change Column Type…"),
    (OP_SET_NOT_NULL, "Set NOT NULL…"),
    (OP_DROP_NOT_NULL, "Drop NOT NULL…"),
    (OP_SET_DEFAULT, "Set DEFAULT…"),
    (OP_DROP_DEFAULT, "Drop DEFAULT…"),
)

ALTER_TABLE_CONSTRAINT_ACTIONS: tuple[tuple[str, str], ...] = (
    (OP_ADD_CONSTRAINT, "Add Constraint…"),
    (OP_ADD_FOREIGN_KEY, "Add Foreign Key…"),
    (OP_DROP_CONSTRAINT, "Drop Constraint…"),
    (OP_RENAME_CONSTRAINT, "Rename Constraint…"),
)

ALTER_TABLE_INDEX_ACTIONS: tuple[tuple[str, str], ...] = (
    (OP_CREATE_INDEX, "Create Index…"),
    (OP_DROP_INDEX, "Drop Index…"),
)

#: The comment group, which is the ONE place the two entry points differ: a
#: comment entry names its subject, and the subject is whatever was
#: right-clicked. A `Set Column Comment…` offered from the table node would name
#: a column the user never pointed at (the dropdown's first one), and a
#: `Set Table Comment…` offered from a column leaf would quietly retarget the
#: click one level up. Both are single-entry tuples so the assembly below stays
#: one uniform "groups, separated" loop.
ALTER_TABLE_TABLE_COMMENT_ACTIONS: tuple[tuple[str, str], ...] = (
    (OP_SET_TABLE_COMMENT, "Set Table Comment…"),
)

ALTER_TABLE_COLUMN_COMMENT_ACTIONS: tuple[tuple[str, str], ...] = (
    (OP_SET_COLUMN_COMMENT, "Set Column Comment…"),
)

#: `Drop Table…` gets a group (and therefore a separator) to itself rather than
#: joining the index pair above: it is the one entry here that removes the
#: object the whole menu is about, and it sits last so it is nowhere near a
#: mis-click on `Drop Index…`. It carries NO confirmation, deliberately -- see
#: `table_dialogs.DropTableDialog`: generating `DROP TABLE t` executes nothing,
#: and the editable tab is the safeguard.
ALTER_TABLE_DROP_TABLE_ACTIONS: tuple[tuple[str, str], ...] = (
    (OP_DROP_TABLE, "Drop Table…"),
)


def alter_table_action_groups(
    column: str = "",
) -> tuple[tuple[tuple[str, str], ...], ...]:
    """The submenu's groups for a click that came from `column` (`""` = the
    table node itself).

    A function rather than one module constant because slice 3 introduced the
    first operation whose *presence* depends on the entry point -- the comment
    pair above. Everything else is identical from both, and deliberately so:
    one builder still produces both menus, so the table node and a column leaf
    can never come to offer different constraint or index sets.
    """
    return (
        ALTER_TABLE_COLUMN_ACTIONS,
        ALTER_TABLE_CONSTRAINT_ACTIONS,
        ALTER_TABLE_INDEX_ACTIONS,
        ALTER_TABLE_COLUMN_COMMENT_ACTIONS
        if column
        else ALTER_TABLE_TABLE_COMMENT_ACTIONS,
        ALTER_TABLE_DROP_TABLE_ACTIONS,
    )


#: The table node's groups -- the shape a caller means when it says "the
#: submenu" without qualifying which click opened it.
ALTER_TABLE_ACTION_GROUPS: tuple[tuple[tuple[str, str], ...], ...] = (
    alter_table_action_groups()
)

#: Every operation the table node's submenu offers, flattened, in menu order.
ALTER_TABLE_ACTIONS: tuple[tuple[str, str], ...] = tuple(
    action for group in ALTER_TABLE_ACTION_GROUPS for action in group
)

#: Every operation EITHER entry point can emit -- the table node's fifteen plus
#: the column leaf's own comment entry. The host maps all sixteen in one place
#: (`MainWindow._alter_column_dialog`), so it needs the union rather than one
#: entry point's view of it.
ALTER_TABLE_ALL_ACTIONS: tuple[tuple[str, str], ...] = (
    *ALTER_TABLE_ACTIONS,
    *ALTER_TABLE_COLUMN_COMMENT_ACTIONS,
)

#: The submenu these sit in, on both the table node and a column leaf.
ALTER_TABLE_MENU_TITLE = "Alter Table"

#: FQ-002's `New Function/Procedure…` and this are the two *creation* entries in
#: this tree, and they sit at the same level for the same reason -- see
#: `BrowserPanel.create_table_requested`.
CREATE_TABLE_LABEL = "Create Table…"

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
    `schema` (spec §18.5, D1). Shared by both right-click ▸ Edit DDL entry
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

    #: Right-click ▸ Edit DDL on an object row (spec §18.5, D1 entry point 1).
    #: Carries the object's `DdlObjectRef` and its current source text (the
    #: live `RoutineInfo.source` / `TriggerInfo.definition` this tree was
    #: built from) -- everything MainWindow needs to open or focus the
    #: editable tab, with no second lookup back into the schema.
    #:
    #: The ONLY editing signal since FQ-024: the withdrawn `checkout_requested`
    #: asked the user to pick between two gestures whose real difference is
    #: project state, so checkout became a branch of MainWindow's handler for
    #: THIS signal rather than a second menu entry (§18.1/§18.2). The panel
    #: still knows nothing about projects.
    edit_requested = Signal(object, str)

    #: Left-click on a Tables-branch table node (spec §18.1, 2026-08-05):
    #: carries the clicked table's `TableInfo` so `MainWindow` can populate
    #: the shared `PropertiesPanel` (`show_node(table_info, "ddl_table")`).
    #: Click-only for Edit DDL -- a whole table has no single
    #: `DdlObjectSpan`/source text for those to act on. It DOES carry a
    #: context menu for *creation* (see `add_trigger_requested`), which needs
    #: no source span precisely because the object does not exist yet.
    table_selected = Signal(object)

    #: Right-click ▸ Add Trigger… on a Tables-branch table node (FQ-002).
    #: Carries the clicked table's `TableInfo`. This is the carve-out to
    #: §18.1's original "table nodes have no context menu" rule: that rule
    #: exists because Edit DDL needs a source span, and a
    #: not-yet-created trigger has none to need.
    add_trigger_requested = Signal(object)

    #: Right-click ▸ New Function/Procedure… on the "Functions & Procedures"
    #: branch root (FQ-002). Carries nothing -- unlike a trigger, a routine is
    #: not scoped to a specific parent object, so there is no context to pass.
    new_routine_requested = Signal()

    #: Right-click ▸ Alter Table ▸ <one of `ALTER_TABLE_ACTIONS`> on a table
    #: node or on one of its column leaves (FQ-025 slices 1 and 2). Carries
    #: `(operation id, TableInfo, column name)`, where the column name is `""`
    #: for a click that came from the table node itself -- the dialog then opens
    #: with its column dropdown on that table's first column instead of a
    #: pre-selected one.
    #:
    #: **Slice 2's four constraint operations ride this same signal**, not a
    #: parallel one: they carry exactly the same context (which table, and which
    #: column the click came from, which the ADDs pre-select in their column
    #: picker and the others show in the read-only "From:" line). A second
    #: signal would have been the same three arguments under another name, and
    #: two places for the host to forget to connect. Hence the name is now
    #: slightly narrower than what it carries; renaming it would touch every
    #: slice-1 connection for no behavioural gain.
    #:
    #: Deliberately the SAME shape as `add_trigger_requested`: the panel states
    #: what was clicked and knows nothing about dialogs, and the host builds,
    #: populates and hosts the dialog (§18.1's creation-gesture wiring). The
    #: operation id rides along rather than becoming eight signals, because all
    #: eight carry identical context and differ only in which dialog the host
    #: opens.
    alter_column_requested = Signal(str, object, str)

    #: Right-click ▸ Create Table… on the "Tables" branch root or on a table
    #: node (FQ-025 slice 3). Carries the schema the new table should default
    #: into (`"pr"` from a click on `pr.orders`, `""` from the branch root,
    #: which names no schema).
    #:
    #: **Its own signal, not `alter_column_requested`.** That one's three
    #: arguments are "which existing table, and which of its columns" -- a
    #: table that does not exist yet has neither, and passing `None` for the
    #: `TableInfo` would make every connected handler test for it. Creating a
    #: table is also not an alteration of one, which is exactly why FQ-025 puts
    #: this at the menu's TOP LEVEL beside FQ-002's `Add Trigger…` /
    #: `New Function/Procedure…` rather than inside `Alter Table ▸`: those two
    #: are the tree's other creation gestures, and all three answer "make a new
    #: object" rather than "change this one".
    create_table_requested = Signal(str)

    def __init__(
        self, parent: QWidget | None = None, *, browse_only: bool = False
    ) -> None:
        """`browse_only` makes this tree a pure viewer: no `Edit DDL`, no
        `Add Trigger…`, no `New Function/Procedure…`, and no `Alter Table ▸`
        (§18.7, FQ-022/FQ-025).

        The SANDBOX Explorer instance passes it, for the reason recorded on
        `EditorPanel.__init__`: `Edit DDL` from the sandbox tree would take
        MainWindow's checkout branch in project mode and seed `ddl/*.sql` from
        the sandbox's definition, poisoning §18.2's drift baseline. The two
        *creation* entries are suppressed with it because they open FQ-002's
        dialogs, whose product is a new object for the project/target lane --
        offering them on a sandbox tree would state a scope the gesture does not
        have. FQ-025's column operations are suppressed for the stronger form of
        the same reason: they are schema MUTATIONS, and §18.7's sandbox Explorer
        exists to look at a sandbox, never to reshape it from the tree.

        Suppression happens at menu-BUILD time rather than by leaving the signals
        unconnected: an entry that emits into nothing is a dead control, which is
        exactly what carve-out 2's posture forbids.

        Off by default, so the target instance keeps today's behaviour.
        """
        super().__init__(parent)
        #: Whether this instance offers the edit/create gestures (see above).
        self._browse_only = browse_only
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        # The schema this tree was last built from, so a later right-click ▸
        # Edit DDL can resolve a routine/trigger's full source text and overload
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
            self._add_columns_group(table_item, table_info)

    @staticmethod
    def _add_columns_group(table_item: QTreeWidgetItem, table_info) -> None:
        """The table's columns, under one collapsible `Columns (N)` node
        (FQ-025 slice 1).

        Column rows exist so a right-click can carry *which column* into the
        `Alter Table ▸` dialogs -- the entry's core interaction rule ("defaulting
        to the table and the column the click was coming from"). Before this
        there was no column row in the tree at all, so that context could only
        ever have come from the table.

        **Grouped rather than listed flat**, and added AFTER the trigger leaves:
        a table's triggers are the thing this branch has always been about, and
        thirty columns spilled directly under the table node would bury them.
        The group node itself carries no role, so it clicks nowhere and offers no
        menu -- it is a container, not a target.

        Nothing is added for a table with no `TableInfo` (a trigger-only node) or
        no columns: an empty `Columns (0)` folder states nothing.
        """
        columns = list(getattr(table_info, "columns", ()) or ())
        if not columns:
            return
        group = QTreeWidgetItem([f"Columns  ({len(columns)})"])
        table_item.addChild(group)
        for column in columns:
            # `TableInfo.columns`' own declared order, not alphabetical -- the
            # same choice `properties_panel._rows_for_ddl_table` makes, so the
            # two surfaces show one table the same way round.
            leaf = QTreeWidgetItem([f"{column.name} ({column.data_type})"])
            leaf.setData(0, _COLUMN_ROLE, (table_info, column.name))
            group.addChild(leaf)

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
            return
        column_context = item.data(0, _COLUMN_ROLE)
        if column_context is not None:
            # A column row shows its OWNING TABLE in the Properties panel
            # (§18.1), which is where that column's type/default/comment already
            # render -- the same node the user would have clicked one level up,
            # reached without collapsing the group they are working in.
            self.table_selected.emit(column_context[0])

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

        A `browse_only` instance (§18.7's sandbox tree) offers nothing anywhere:
        all three menus below are edit/create gestures, so there is no partial
        menu left to build.
        """
        if self._browse_only:
            return None
        span = item.data(0, _SPAN_ROLE)
        if span is not None:
            if self._schema is None:
                return None
            resolved = resolve_edit_target(self._schema, span)
            if resolved is None:
                return None
            ref, source = resolved
            menu = QMenu(self)
            # ONE editing entry (FQ-024). The clicked row already names the
            # object, so the entry does not repeat it -- unlike `EditorPanel`'s
            # equivalent, where the click landed in a multi-object buffer and
            # two overloads' entries must read differently.
            menu.addAction("Edit DDL", lambda: self.edit_requested.emit(ref, source))
            return menu

        table_info = item.data(0, _TABLE_ROLE)
        if table_info is not None:
            menu = QMenu(self)
            # FQ-002's *creation* entry stays at the TOP LEVEL: it creates a new
            # object, which is a different act from altering this one, and
            # burying it in the mutation submenu would say otherwise.
            menu.addAction(
                "Add Trigger…",
                lambda: self.add_trigger_requested.emit(table_info),
            )
            # The second creation entry, beside the first and above the
            # mutation submenu. Offered from a table node -- not only from the
            # branch root -- because a table node is the one place in this tree
            # that names a SCHEMA, which is what pre-seeds the new table's name
            # so it lands where the click was. Offered on a view's node too:
            # what you create is a table regardless of what you clicked, which
            # is why this is not inside the table-only submenu.
            self._add_create_table_entry(menu, self._schema_of(table_info))
            self._add_alter_table_submenu(menu, table_info, column="")
            return menu

        column_context = item.data(0, _COLUMN_ROLE)
        if column_context is not None:
            column_table, column_name = column_context
            menu = QMenu(self)
            # The SAME submenu, carrying the clicked column. A column row offers
            # nothing else, but it keeps the submenu rather than flattening the
            # twelve entries: one shape for one action set, and the title is what
            # tells the user these produce `ALTER TABLE` rather than acting on
            # the column in place.
            if self._add_alter_table_submenu(menu, column_table, column=column_name) is None:
                # A view's column: the submenu declined, and it was this menu's
                # only content -- an empty menu under the cursor is worse than
                # none (the same reason the fall-through below returns None).
                return None
            return menu

        if item.data(0, _BRANCH_ROLE) == "routines":
            menu = QMenu(self)
            menu.addAction(
                "New Function/Procedure…",
                lambda: self.new_routine_requested.emit(),
            )
            return menu

        if item.data(0, _BRANCH_ROLE) == "tables":
            # The exact mirror of the routines root above, and the reason the
            # Tables root -- which offered nothing until FQ-025 slice 3 -- has a
            # menu at all: each branch root offers "create a new one of the kind
            # this branch lists". No schema is passed, because the root names
            # none; the dialog opens with an empty name field.
            menu = QMenu(self)
            self._add_create_table_entry(menu, "")
            return menu

        # Argument-name child leaves and the `Columns` group node carry neither
        # a span nor a creation context -- no menu at all, rather than an empty
        # one popping up under the cursor.
        return None

    @staticmethod
    def _schema_of(table_info) -> str:
        """`"pr"` from a `TableInfo` named `pr.orders`, `""` from an unqualified
        one -- the click context `Create Table…` seeds its name field with."""
        name = getattr(table_info, "name", "") or ""
        return name.split(".", 1)[0] if "." in name else ""

    def _add_create_table_entry(self, menu: QMenu, schema: str) -> None:
        menu.addAction(
            CREATE_TABLE_LABEL,
            lambda: self.create_table_requested.emit(schema),
        )

    def _add_alter_table_submenu(self, menu: QMenu, table_info, *, column: str):
        """FQ-025's `Alter Table ▸` submenu, on `menu` -- slice 1's eight column
        operations, then slice 2's four constraint ones, then slice 3's two
        index ones, the comment entry for whatever was clicked, and
        `Drop Table…`, each group separated from the last.

        One builder for both entry points, so the table node and a column leaf
        can never come to offer different operation sets -- they differ in
        exactly two things, both derived from the one `column` parameter: which
        column the dialogs pre-select, and which comment entry is offered (see
        `alter_table_action_groups`). It is also the reason slice 2 was four
        lines of data and slice 3 mostly three more: extending the groups
        reaches both entry points at once, and there is no second copy that
        could have been missed.

        **What lands here versus at the top level.** Everything on this submenu
        is scoped to the clicked table, including the two index entries and
        `Drop Table…`, none of which emits the literal words `ALTER TABLE`.
        `Create Table…` is the one FQ-025 entry that is NOT scoped to it, and is
        therefore the one that stays outside (see `create_table_requested`).

        Returns the submenu (or `None` when none was added) so callers and tests
        can read its membership without re-deriving it.

        **Views and materialized views get no submenu.** Nearly every operation
        here emits `ALTER TABLE` or `DROP TABLE`, and offering a table mutation
        on a view would generate DDL the server refuses -- the
        tab-is-the-safeguard principle covers *running* generated DDL, not
        generating DDL that cannot be right. Slice 3's comment entries and
        `Create Index…` do have legal view spellings (`COMMENT ON VIEW`, an
        index on a materialized view), but the emitters behind them render
        `TABLE`/an ordinary `CREATE INDEX`, so offering them here would still
        produce the wrong statement; a view-shaped action set is a feature this
        one does not claim to be.
        """
        if getattr(table_info, "kind", "table") != "table":
            return None
        # Built explicitly and then added, never `menu.addMenu("title")`: that
        # overload hands the new QMenu's ownership to Python, so the submenu is
        # garbage-collected out from under the menu that is showing it.
        submenu = QMenu(ALTER_TABLE_MENU_TITLE, menu)
        menu.addMenu(submenu)
        for index, group in enumerate(alter_table_action_groups(column)):
            if index:
                submenu.addSeparator()
            for operation, label in group:
                submenu.addAction(
                    label,
                    lambda operation=operation: self.alter_column_requested.emit(
                        operation, table_info, column
                    ),
                )
        return submenu
