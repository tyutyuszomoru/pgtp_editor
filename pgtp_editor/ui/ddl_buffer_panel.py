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

Two panel-level affordances ride above the tree and survive a rebuild:

* the **name filter** (`FQ-260810180336`, §18.1) -- an input, a five-way match
  mode, `Filter` and `Clear Filter` -- which HIDES non-matching object rows and
  changes nothing else. It is the tab's SECOND find-shaped control, and it is
  deliberately not `FindReplaceBar`: that one searches the DDL *text* of the
  centre pane and moves a caret; this one matches tree *names* and hides rows.
  The two are never wired to each other.
* the **danger selection colour** (`FQ-260810165518`, §18.7) -- the quality
  instance paints its selected row in the app's existing maintenance red, so
  the dangerous Explorer is recognisable at a glance from the disposable one.

Grouping/matching is re-derived from scratch on every `set_schema` call --
this panel holds no cache of its own, matching this app's "recompute fresh,
never trust prior state" posture for DB-sourced data (§18's truth model).
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.ddl_buffer import EDITABLE_SPAN_KINDS, DdlObjectSpan
from pgtp_editor.db.ddl_project import DriftMarkers, routine_ddl_paths, trigger_ddl_path
from pgtp_editor.db.introspect import DatabaseSchema
from pgtp_editor.ui.alter_column_dialogs import (
    OP_DROP_COLUMN,
    OP_DROP_DEFAULT,
    OP_DROP_NOT_NULL,
    OP_SET_NOT_NULL,
)
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.mode_indicator import MODE_MAINTENANCE, mode_colors
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
#: An object row's BARE, marker-free NAME -- `schema.table`, `schema.name`,
#: `schema.table.trigname` -- and the ONLY thing the name filter
#: (`FQ-260810180336`) ever matches against. Carried by exactly the three row
#: kinds §18.1 calls object rows; every other row (branch roots, the
#: `Columns  (N)` / `Constraints  (N)` / `Indexes  (N)` groups, column leaves,
#: constraint/index leaves and routine-argument leaves) leaves it unset and is
#: therefore not a match target.
#:
#: **It is a role of its own rather than a read of `_LABEL_ROLE`, and that is a
#: correction to the spec, not a shortcut.** §18.1's filter block says to match
#: against "the stored base label" on the ground that the rendered text carries
#: `*`/`!` drift markers -- true, but the base label carries the *other*
#: markers: `[F]`/`[P]`/`[T]` on a routine, `[B][D]` on a trigger, and the
#: `  (N)` trigger count on a table. Matching that base is the exact defect the
#: spec was trying to avoid, one bracket further in: `f` would match every
#: function and `d` every DELETE trigger. The name is what the user is looking
#: for, so the name is what is stored.
_FILTER_NAME_ROLE = Qt.ItemDataRole.UserRole + 6

#: The refusal a non-editable span states rather than silently offering
#: nothing (`FQ-260810183812` / FQ-023). Tables, views and matviews are in the
#: buffer to be READ: they are not part of §18.2's checkout model, and a
#: table's shape changes through `Alter Table ▸` alone -- so `Edit DDL` has
#: nothing to open, and saying why is not the same as leaving a dead menu.
NOT_EDITABLE_REFUSALS = {
    "table": "Tables are read-only here — change one with Alter Table ▸",
    "view": "Views are read-only here — this pane does not edit them",
    "matview": "Materialized views are read-only here — this pane does not edit them",
    "column": "Columns are read-only here — change one with Alter Table ▸",
    "constraint": "Constraints are read-only here — change one with Alter Table ▸",
    "index": "Indexes are read-only here — change one with Alter Table ▸",
}


def edit_refusal_for_span(span) -> str | None:
    """The reason `Edit DDL` is not offered for `span`, or None when it IS
    offered (a routine or a trigger).

    Shared by both right-click surfaces, exactly as `resolve_edit_target` is,
    so the two can never disagree about which kinds are editable."""
    kind = getattr(span, "kind", None)
    if kind in EDITABLE_SPAN_KINDS:
        return None
    return NOT_EDITABLE_REFUSALS.get(kind, "This object is read-only here")


_CONSTRAINT_MARKERS = {
    "primary key": "PK",
    "foreign key": "FK",
    "unique": "U",
    "check": "C",
    "exclude": "X",
}

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

#: Every operation EITHER entry point can emit -- the table node's sixteen plus
#: the column leaf's own comment entry. The host maps all seventeen in one place
#: (`MainWindow._alter_column_dialog`), so it needs the union rather than one
#: entry point's view of it.
ALTER_TABLE_ALL_ACTIONS: tuple[tuple[str, str], ...] = (
    *ALTER_TABLE_ACTIONS,
    *ALTER_TABLE_COLUMN_COMMENT_ACTIONS,
)

#: operation id -> the SQL statement that operation's emitter actually writes.
#: Only the operations whose statement is NOT `ALTER TABLE` appear; everything
#: absent gets `AlterDdlRef.statement`'s default, which is the honest answer for
#: the twelve column/constraint operations that really do emit one.
#:
#: It lives here, beside the ids themselves, because it is a statement of FACT
#: about each emitter in `db/ddl_skeleton.py` -- the same kind of fact as the
#: labels above, and belonging to the same vocabulary. The tab titles read off
#: it (see `AlterDdlRef.statement`), which is how a `Create Index…` generation
#: stopped being titled `ALTER <table>`: the submenu it was reached from is
#: `Alter Table ▸`, but the statement it produces is not an ALTER at all, and
#: the tab must be named after the buffer, not after the route to it.
ALTER_DDL_STATEMENTS: dict[str, str] = {
    OP_CREATE_TABLE: "CREATE TABLE",
    OP_DROP_TABLE: "DROP TABLE",
    OP_CREATE_INDEX: "CREATE INDEX",
    OP_DROP_INDEX: "DROP INDEX",
    OP_SET_TABLE_COMMENT: "COMMENT ON TABLE",
    OP_SET_COLUMN_COMMENT: "COMMENT ON COLUMN",
}

#: The statement every other operation emits, and the default the ref carries.
DEFAULT_ALTER_DDL_STATEMENT = "ALTER TABLE"


def alter_ddl_statement(operation: str) -> str:
    """The SQL statement `operation` generates."""
    return ALTER_DDL_STATEMENTS.get(operation, DEFAULT_ALTER_DDL_STATEMENT)


def _qualified_in_schema_of(name: str, qualified_table: str) -> str:
    """`name` in `qualified_table`'s schema, or `""` for an empty name. An
    index lives in its table's schema in Postgres, so this is not a guess."""
    if not name:
        return ""
    if "." in name:
        return name
    schema = qualified_table.rsplit(".", 1)[0] if "." in qualified_table else ""
    return f"{schema}.{name}" if schema else name


def alter_ddl_subject(dialog, operation: str, qualified_table: str) -> str:
    """What the generated statement NAMES, fully qualified -- the half of a tab
    title that no operation→label lookup can supply.

    Read off the DIALOG, because the dialog is the only place the answer
    exists: `DROP INDEX` names an index the user picked from a combo,
    `COMMENT ON COLUMN` names a column, and neither is anywhere in the
    `(schema, table)` pair `AlterDdlRef` is otherwise built from. That is
    exactly why a verb-mapping-only fix read *worse* than the old wrong title:
    the right verb over the wrong noun names a thing the statement never
    mentions.

    `""` means "the table", which `AlterDdlRef.qualified_subject` resolves --
    the correct answer for every `ALTER TABLE`, `CREATE TABLE`, `DROP TABLE`
    and `COMMENT ON TABLE`.

    Duck-typed via `getattr` throughout: this module already knows the ids, and
    making it import the dialog classes to isinstance-check them would invert
    the dependency `table_dialogs` has on it.
    """
    if operation in (OP_CREATE_INDEX, OP_DROP_INDEX):
        # `DropIndexDialog` hands back `schema.name` directly; `CreateIndexDialog`
        # has only the bare name the user typed.
        identity = (getattr(dialog, "index_identity", lambda: "")() or "").strip()
        if identity:
            return identity
        name = (getattr(dialog, "index_name", lambda: "")() or "").strip()
        return _qualified_in_schema_of(name, qualified_table)
    if operation == OP_SET_COLUMN_COMMENT:
        column = (getattr(dialog, "column", lambda: "")() or "").strip()
        return f"{qualified_table}.{column}" if column else ""
    return ""


#: The submenu these sit in, on both the table node and a column leaf.
ALTER_TABLE_MENU_TITLE = "Alter Table"

#: FQ-002's `New Function/Procedure…` and this are the two *creation* entries in
#: this tree, and they sit at the same level for the same reason -- see
#: `BrowserPanel.create_table_requested`.
CREATE_TABLE_LABEL = "Create Table…"

#: BUG-062's re-introspection gesture. ONE label for the whole command -- this
#: tree's context menu, the viewing pane's, and the host's Database-menu action --
#: because a command id is its label, and eight names for four operations is
#: recorded as a mistake not to repeat. It lives here rather than on either panel
#: so both can import it: `ddl_editor_panel` already imports from this module
#: (`resolve_edit_target`), and the reverse direction would be a cycle.
RELOAD_LABEL = "Reload DDL"

#: BUG-260810193333's checkout-drop gesture, for the same one-label reason as
#: `RELOAD_LABEL`: the tree entry, the host's Audit lines and the confirmation
#: title all say this, so there is exactly one string to move if it is renamed.
#: No trailing "…" -- the ellipsis in this app means "opens a dialog that asks
#: for input"; this one only asks for a Yes.
DISCARD_LOCAL_LABEL = "Discard local change"

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


#: The name filter's five match modes (`FQ-260810180336`, §18.1).
#:
#: A NEW predicate enum, deliberately NOT
#: `caption_management_panel.MODE_LABELS`: that one answers *how the search
#: STRING is interpreted* (plain / escapes / regex), this one answers *WHERE in
#: the name the match must sit*. The two questions are orthogonal, and one enum
#: expressing both can express neither -- there would be no way to ask for a
#: regex that must START a name, and every addition to either list would
#: silently grow the other. Only the SHAPE is reused: a module-level
#: `(label, value)` tuple fed to `QComboBox.addItem(label, value)`.
FILTER_MODE_CONTAINS = "contains"
FILTER_MODE_STARTS_WITH = "starts_with"
FILTER_MODE_NOT_CONTAINS = "not_contains"
FILTER_MODE_NOT_STARTS_WITH = "not_starts_with"
FILTER_MODE_ENDS_WITH = "ends_with"

FILTER_MODE_LABELS: tuple[tuple[str, str], ...] = (
    ("Contains", FILTER_MODE_CONTAINS),
    ("Starts with", FILTER_MODE_STARTS_WITH),
    ("Doesn't contain", FILTER_MODE_NOT_CONTAINS),
    ("Doesn't start with", FILTER_MODE_NOT_STARTS_WITH),
    ("Ends with", FILTER_MODE_ENDS_WITH),
)

#: Open question 3, settled: `Contains` -- the mode that needs the least
#: knowledge of the name being hunted, which is the state a search aid is used
#: from.
FILTER_MODE_DEFAULT = FILTER_MODE_CONTAINS

#: Open question 1, settled: matching is CASE-INSENSITIVE, with **no** exposed
#: `Match case` toggle. Insensitive because this is a search aid over
#: lower-case-by-convention Postgres identifiers; no toggle because the owner's
#: stated control set is exactly four (input, mode, Filter, Clear Filter) and a
#: fifth control that is right 99% of the time when left alone is cost without
#: a question it answers.
FILTER_CASE_SENSITIVE = False


def filter_matches(name: str, term: str, mode: str) -> bool:
    """Does the object called `name` survive `term` under `mode`?

    Pure and Qt-free, so every one of the five predicates is testable without a
    tree. An empty `term` matches everything, in every mode -- including the two
    negative ones, where "doesn't contain nothing" would otherwise hide the
    whole tree for a user who pressed `Filter` on an empty box.
    """
    if not term:
        return True
    if not FILTER_CASE_SENSITIVE:
        name = name.lower()
        term = term.lower()
    if mode == FILTER_MODE_STARTS_WITH:
        return name.startswith(term)
    if mode == FILTER_MODE_ENDS_WITH:
        return name.endswith(term)
    if mode == FILTER_MODE_NOT_CONTAINS:
        return term not in name
    if mode == FILTER_MODE_NOT_STARTS_WITH:
        return not name.startswith(term)
    return term in name


def filter_mode_label(mode: str) -> str:
    """The dropdown label for `mode` -- read by the banner, so the banner can
    never name a mode differently from the control that set it."""
    for label, value in FILTER_MODE_LABELS:
        if value == mode:
            return label
    return mode


#: Open question 2, settled: an active filter ANNOUNCES itself, and an
#: all-hidden tree says why. The `ui/coherence_panel.py` precedent, applied for
#: the reason §18.1 gives for it being stronger here than there -- this tree can
#: be left filtered while the user works in another tab, and a tree silently
#: missing objects is the shape of a silent wrong result. The Clear button is
#: NOT repeated in the banner (coherence has one because it has no other): this
#: bar's own `Clear Filter` is always on screen, and two buttons doing one thing
#: is a worse answer than one.
NO_FILTER_MATCHES_TEXT = (
    "No objects match the active filter — use “Clear Filter” to see everything."
)

#: The input's placeholder. Load-bearing rather than decorative: this panel's
#: tab now sits beside `EditorPanel`'s `FindReplaceBar`, so the placeholder is
#: one of the four things that tell a user which of the two inputs they are in
#: (the others: this bar lives in the LEFT DOCK above the tree while Find sits
#: in the CENTER tab below the editor, its buttons say `Filter`/`Clear Filter`
#: rather than `Find Next`/`Replace`, and it carries a mode dropdown Find has
#: no equivalent of).
FILTER_PLACEHOLDER = "Filter object names…"

FILTER_BUTTON_LABEL = "Filter"
CLEAR_FILTER_BUTTON_LABEL = "Clear Filter"


def danger_selection_colors(light: bool) -> tuple[str, str]:
    """`(selection background, selected text)` for the QUALITY tree
    (`FQ-260810165518`, §18.7).

    **Reuses `mode_indicator.mode_colors(light)[MODE_MAINTENANCE]` and derives
    NOTHING** -- no second red lives in this module, which is the trap
    `mode_indicator.py`'s own docstring records (*"never the DEBUG chip's
    hardcoded red that reads wrong in one theme"*).

    **The pair is used SWAPPED, and that is the answer to §18.7's open question
    1.** `MODE_MAINTENANCE` is a CHIP pair -- a pale wash behind strong text --
    and §18.7 flags exactly why it cannot be used as-is: its light background
    `#FDECEA` measures **1.10:1** against the tree's light chrome, so a
    selection painted in it would be invisible *as a selection*. Reading the
    pair the other way round -- the strong colour as the BAND, the pale one as
    the TEXT on it -- keeps both halves of a pair that was already tuned to be
    legible against each other (measured **7.98:1** light, **8.50:1** dark,
    against qdarkstyle's own **9.44:1** / **4.57:1**), while the band itself
    reads **8.74:1** / **9.28:1** against the chrome. So the answer is *reuse the
    pair*, not *add a sibling entry*: no new colour enters the app, which is
    what trap 3 ("this feature adds ONE colour, not a palette") asks for.
    """
    chip_background, chip_foreground = mode_colors(light)[MODE_MAINTENANCE]
    return chip_foreground, chip_background


def danger_selection_stylesheet(light: bool) -> str:
    """The widget-level QSS that paints `danger_selection_colors` on a tree.

    **A stylesheet and not a `setPalette`, because a palette override here is
    INERT** (§7, measured 2026-08-11): the app-level qdarkstyle sheet declares
    `QTreeView::item:selected:active` / `:!active` and a universal
    `QWidget { selection-background-color; selection-color }`, and QSS wins over
    QPalette on every property it sets. `BUG-260811021804` is the same mistake
    already shipped elsewhere. A widget-level sheet merges with, and outranks,
    the application one.

    **Both the active and the inactive selection redden** (open question 2,
    settled): the tree loses focus the instant the user clicks into the DDL
    pane, which is the state a quality Explorer is looked at from most of the
    time -- a danger marking that vanishes exactly then marks nothing.
    **Hover does NOT redden**: hover is where the pointer is, not where the
    user is acting, and reddening it would make moving the mouse look
    dangerous.

    **Three selectors, and the third was found by looking at pixels rather than
    by reading the app sheet.** Overriding only the two `::item` rules left the
    selected row's INDENT/branch column still painting the app-wide blue -- a
    measured 653 blue pixels inside a 5594-pixel red band -- because that strip
    is drawn from the universal `QWidget` rule's `selection-background-color`,
    not from `::item`. So the widget sheet restates that pair too, scoped to
    this one tree.
    """
    background, text = danger_selection_colors(light)
    return (
        f"QTreeWidget {{ selection-background-color: {background};"
        f" selection-color: {text}; }}"
        f" QTreeWidget::item:selected:active,"
        f" QTreeWidget::item:selected:!active"
        f" {{ background-color: {background}; color: {text}; }}"
    )


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

    #: Right-click ▸ Discard local change on a CHECKED-OUT object row
    #: (BUG-260810193333, §18.2). Carries the object's `DdlObjectRef` alone --
    #: unlike `edit_requested` it needs no source text, because discarding is
    #: about deleting the local `ddl/*.sql` and its last-deployed reference,
    #: never about rendering anything.
    #:
    #: The entry is offered ONLY when `set_checked_out_predicate`'s callable
    #: says this object is checked out, so the panel still knows nothing about
    #: projects -- and an unavailable gesture is absent rather than
    #: selectable-but-dead (carve-out 2). The predicate is consulted at
    #: menu-BUILD time, so a just-discarded object stops offering it with no
    #: refresh bookkeeping of its own.
    discard_local_requested = Signal(object)

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

    #: Right-click ▸ Reload DDL, anywhere in this tree (BUG-062). The twin of
    #: `EditorPanel.reload_requested` -- see that signal for why reload is a
    #: re-introspection rather than a re-render of a cached `SchemaIndex`, and why
    #: it carries no role.
    #:
    #: The one entry a `browse_only` tree DOES offer. Every other gesture here is
    #: an edit or a creation, which is why suppressing them all left the sandbox
    #: tree with no menu at all; reloading is neither, and it is the gesture a
    #: sandbox browse needs most (applying to a sandbox is exactly the operation
    #: whose result the user then wants to re-read).
    reload_requested = Signal()

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

        # Host-injected `ref -> bool`: "is this object checked out right now?"
        # Only the host knows (it owns the project folder and the `deployed`
        # manifest), and only it can answer for the CURRENT state -- so this is
        # a predicate consulted per right-click rather than a flag pushed on
        # every refresh. Unset means "no project / nothing is checked out",
        # which correctly hides `Discard local change` entirely.
        self._checked_out: Callable[[Any], bool] | None = None

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

        #: `(kind, schema, table, name) -> DdlObjectSpan` for the single-line
        #: column / constraint / index spans of the last `set_schema`
        #: (`FQ-260810183812`). Rebuilt wholesale with the tree, like every
        #: other derivation here.
        self._span_by_detail: dict[tuple[str, str, str, str], DdlObjectSpan] = {}

        #: The APPLIED filter -- `(mode, term)`, or `None` when nothing is
        #: filtering. Deliberately NOT read back off the two controls when the
        #: filter is re-applied: the controls hold what the user is *typing*,
        #: this holds what they *pressed Filter on*, and conflating the two
        #: would make an abandoned edit in the input take effect on the next
        #: `set_schema`.
        #:
        #: Held on the PANEL, exactly as `_dirty_keys` is and for the identical
        #: reason (open question 4, settled: **re-apply**): the tree is rebuilt
        #: wholesale by every `set_schema`, so anything keyed on an item would
        #: go stale -- and a filter that silently stopped filtering after a
        #: `Reload DDL` would leave the user reading a tree they believe is
        #: narrowed. The banner is what keeps the re-application from being
        #: silent, which is why the two open questions had one answer.
        self._filter: tuple[str, str] | None = None

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText(FILTER_PLACEHOLDER)
        # A text input beside a button that ignores Return is its own small
        # defect -- but nothing filters on a keystroke (§18.1: apply on the
        # button, not live-as-you-type).
        self.filter_input.returnPressed.connect(self.apply_filter)
        self.filter_mode_combo = QComboBox()
        for label, mode in FILTER_MODE_LABELS:
            self.filter_mode_combo.addItem(label, mode)
        self.filter_mode_combo.setCurrentIndex(
            [mode for _, mode in FILTER_MODE_LABELS].index(FILTER_MODE_DEFAULT)
        )
        self.filter_button = QPushButton(FILTER_BUTTON_LABEL)
        self.filter_button.clicked.connect(self.apply_filter)
        self.clear_filter_button = QPushButton(CLEAR_FILTER_BUTTON_LABEL)
        self.clear_filter_button.clicked.connect(self.clear_filter)

        self.filter_bar = QWidget()
        filter_row = QHBoxLayout(self.filter_bar)
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.addWidget(self.filter_input, 1)
        filter_row.addWidget(self.filter_mode_combo)
        filter_row.addWidget(self.filter_button)
        filter_row.addWidget(self.clear_filter_button)

        self.filter_banner_label = QLabel("")
        self.filter_banner_label.setWordWrap(True)
        self.filter_banner_label.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filter_bar)
        layout.addWidget(self.filter_banner_label)
        layout.addWidget(self.tree)

        #: `FQ-260810165518`: the QUALITY tree's selection band is the danger
        #: colour; the sandbox tree keeps the ordinary one, because the
        #: DIFFERENCE is the feature.
        #:
        #: Defaulted from `browse_only` rather than taking a parameter of its
        #: own, so no caller changes: the two instances §18.7 creates are
        #: exactly `BrowserPanel()` (quality) and `BrowserPanel(browse_only=True)`
        #: (sandbox). The two facts are not the same fact -- "may not edit" and
        #: "is the dangerous lane" merely coincide today -- so
        #: `set_danger_highlight` exists to state it independently the moment
        #: they stop coinciding.
        self._danger_highlight = not browse_only
        self._apply_danger_highlight()

    def set_checked_out_predicate(
        self, predicate: "Callable[[Any], bool] | None"
    ) -> None:
        """Inject the host's "is this object checked out?" answer, which gates
        the `Discard local change` entry (BUG-260810193333).

        Injected as a CALLABLE rather than pushed as a set, for the same reason
        `_menu_for_item` resolves the edit target from `_schema` on demand: the
        answer depends on project state the panel does not model, and it changes
        for one object at a time (a checkout, a discard) without the tree being
        rebuilt. Asking at menu-build time means the entry can never be stale.
        """
        self._checked_out = predicate

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
        # `FQ-260810183812`: relations, and the per-line detail spans for their
        # columns, constraints and indexes. Keyed by the same identities the
        # tree already builds its labels from, so a node finds its span with no
        # second derivation.
        span_by_relation: dict[tuple[str, str], DdlObjectSpan] = {}
        span_by_detail: dict[tuple[str, str, str, str], DdlObjectSpan] = {}
        for span in spans:
            if span.kind == "trigger":
                span_by_trigger[(span.schema, span.table, span.name)] = span
            elif span.kind in ("table", "view", "matview"):
                span_by_relation[(span.schema, span.name)] = span
            elif span.kind in ("column", "constraint", "index"):
                span_by_detail[(span.kind, span.schema, span.table, span.name)] = span
            elif span.signature is not None:
                span_by_routine[span.signature] = span
        self._span_by_detail = span_by_detail

        markers = drift_markers or {}
        self._build_tables_branch(schema, span_by_trigger, markers, span_by_relation)
        self._build_routines_branch(schema, span_by_routine, span_by_trigger, markers)
        # Re-apply the surviving unsaved-edit overlay to the rows that were
        # just rebuilt (BUG-033): a refresh must not drop the `*` of a tab
        # that is still open and still dirty.
        self._apply_dirty_markers()
        # ...and the surviving FILTER, for the same reason and by the same
        # mechanism (`FQ-260810180336`, open question 4). A tree rebuilt under a
        # live filter that came back unfiltered would be a box the user believes
        # is narrowed and is not.
        self._apply_filter_to_tree()

    # -- name filter (`FQ-260810180336`) --------------------------------------

    def apply_filter(self) -> None:
        """Apply what the bar currently holds (the `Filter` button, and Return
        in the input).

        An empty term is not a filter -- pressing `Filter` on an empty box
        clears rather than hiding everything under the two negative modes.
        """
        term = self.filter_input.text().strip()
        mode = self.filter_mode_combo.currentData() or FILTER_MODE_DEFAULT
        self._filter = (mode, term) if term else None
        self._apply_filter_to_tree()

    def clear_filter(self) -> None:
        """Restore every row and empty the input (the `Clear Filter` button)."""
        self._filter = None
        self.filter_input.clear()
        self._apply_filter_to_tree()

    def active_filter(self) -> tuple[str, str] | None:
        """The applied `(mode, term)`, or `None`. What is *typed* is not what is
        *applied*; this reports the latter."""
        return self._filter

    def filter_description(self) -> str:
        """The active filter in words, or `""` -- the banner's text, and the
        one place the mode is named, so the banner can never disagree with the
        dropdown that set it."""
        if self._filter is None:
            return ""
        mode, term = self._filter
        return f"name {filter_mode_label(mode).lower()} “{term}”"

    def _filter_predicate(self) -> "Callable[[str], bool] | None":
        if self._filter is None:
            return None
        mode, term = self._filter
        return lambda name: filter_matches(name, term, mode)

    def _apply_filter_to_tree(self) -> None:
        """Hide every object row that does not match, keep the ANCESTORS of the
        ones that do, and say so in the banner.

        `item.setHidden(...)`, walked recursively -- the shipped precedent is
        `ui/caption_management_panel.py`'s value-list filter. A
        `QSortFilterProxyModel` is not an option here: `self.tree` is an
        item-based `QTreeWidget`, so a proxy means converting the whole panel to
        model/view, and ancestor visibility is harder to express through a proxy
        than through the walk.

        **A hidden row is ONLY hidden.** Nothing here touches a span, a role, a
        selection or a signal, so a row that survives the filter behaves exactly
        as it did before there was one.
        """
        predicate = self._filter_predicate()
        matches = 0
        for index in range(self.tree.topLevelItemCount()):
            matches += self._filter_item(self.tree.topLevelItem(index), predicate)
        self._refresh_filter_banner(matches)

    def _filter_item(self, item: QTreeWidgetItem, predicate) -> int:
        """Apply `predicate` to `item`'s subtree; return how many object rows in
        it matched, and leave `item` hidden iff that count is zero.

        With no predicate every row is shown, which is what makes this one
        method both "filter" and "clear".
        """
        if predicate is None:
            self._show_subtree(item)
            return 0
        name = item.data(0, _FILTER_NAME_ROLE)
        if name is not None and predicate(name):
            # A matched object shows its whole subtree: its columns, its
            # constraints, its triggers. Hiding them would answer a different
            # question than the one asked.
            self._show_subtree(item)
            return 1 + sum(
                self._count_matches(item.child(i), predicate)
                for i in range(item.childCount())
            )
        matched = 0
        for index in range(item.childCount()):
            matched += self._filter_item(item.child(index), predicate)
        item.setHidden(matched == 0)
        if matched:
            # Only ancestors are auto-expanded, and only while filtering: a hit
            # buried under a collapsed branch root is a hit the user cannot see.
            item.setExpanded(True)
        return matched

    def _count_matches(self, item: QTreeWidgetItem, predicate) -> int:
        """Matches inside an already-shown subtree, counted without touching
        visibility -- the banner's number must include rows that rode along
        under a matched parent."""
        name = item.data(0, _FILTER_NAME_ROLE)
        matched = 1 if name is not None and predicate(name) else 0
        for index in range(item.childCount()):
            matched += self._count_matches(item.child(index), predicate)
        return matched

    @staticmethod
    def _show_subtree(item: QTreeWidgetItem) -> None:
        item.setHidden(False)
        for index in range(item.childCount()):
            BrowserPanel._show_subtree(item.child(index))

    def _object_row_count(self) -> int:
        total = 0
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value() is not None:
            if iterator.value().data(0, _FILTER_NAME_ROLE) is not None:
                total += 1
            iterator += 1
        return total

    def _refresh_filter_banner(self, matches: int) -> None:
        description = self.filter_description()
        if not description:
            self.filter_banner_label.setVisible(False)
            self.filter_banner_label.setText("")
            return
        if matches:
            total = self._object_row_count()
            text = f"Filtered: {description} — {matches} of {total} objects"
        else:
            text = NO_FILTER_MATCHES_TEXT
        self.filter_banner_label.setText(text)
        self.filter_banner_label.setVisible(True)

    # -- danger selection colour (`FQ-260810165518`) --------------------------

    def set_danger_highlight(self, enabled: bool) -> None:
        """Turn the quality tree's danger selection band on or off.

        Public so the target-vs-sandbox distinction can one day be stated by
        the host directly rather than inferred from `browse_only` -- see
        `_danger_highlight`.
        """
        self._danger_highlight = bool(enabled)
        self._apply_danger_highlight()

    def has_danger_highlight(self) -> bool:
        return self._danger_highlight

    def _palette_is_light(self) -> bool:
        return self.palette().color(QPalette.ColorRole.Base).lightness() > 128

    def _apply_danger_highlight(self) -> None:
        """(Re-)paint the selection band for the current theme.

        Idempotent and last-write-wins by construction -- it reads the live
        palette and assigns the whole sheet -- which is what makes it safe under
        the measured theme-flip mechanics: `PaletteChange` fires **four times**
        per flip and the first two still report the OLD lightness, so the only
        handler that can be right is one whose last call decides.
        """
        if not self._danger_highlight:
            self.tree.setStyleSheet("")
            return
        self.tree.setStyleSheet(danger_selection_stylesheet(self._palette_is_light()))

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Re-apply the danger colour on a theme flip.

        `PaletteChange` is the event that matters: `ApplicationPaletteChange`
        was measured NOT to reach a nested child, which is the trap the two
        other theme-aware panels in this app record. It is listened for anyway,
        harmlessly, because a re-apply is idempotent.
        """
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.PaletteChange,
        ):
            self._apply_danger_highlight()

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

    def _build_tables_branch(
        self, schema: DatabaseSchema, span_by_trigger, markers, span_by_relation=None
    ) -> None:
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
            qualified = f"{schema_name}.{table_name}"
            # The filter matches the NAME, never the label: `label` may carry a
            # `  (N)` trigger count, and `(2)` is not something anyone searches
            # a table by.
            table_item.setData(0, _FILTER_NAME_ROLE, qualified)
            table_info = schema.tables.get(qualified)
            if table_info is not None:
                table_item.setData(0, _TABLE_ROLE, table_info)
            # The relation's own span (`FQ-260810183812`): a table/view/matview
            # node now navigates into its synthesized DDL. It keeps `_TABLE_ROLE`
            # too -- the click is ADDITIVE (see `_on_item_clicked`), because
            # removing the Properties population would withdraw a working
            # behaviour to buy a new one.
            relation_span = (span_by_relation or {}).get((schema_name, table_name))
            if relation_span is not None:
                table_item.setData(0, _SPAN_ROLE, relation_span)
            tables_root.addChild(table_item)
            for trigger in triggers:
                span = span_by_trigger.get((trigger.schema, trigger.table, trigger.name))
                self._add_trigger_leaf(table_item, trigger, span, markers)
            self._add_columns_group(table_item, table_info, schema_name, table_name)
            self._add_constraints_group(
                table_item, schema.constraints_for(qualified), schema_name, table_name
            )
            self._add_indexes_group(
                table_item, schema.indexes_for(qualified), schema_name, table_name
            )

    def _detail_span(self, kind: str, schema_name: str, table_name: str, name: str):
        return self._span_by_detail.get((kind, schema_name, table_name, name))

    def _add_columns_group(
        self,
        table_item: QTreeWidgetItem,
        table_info,
        schema_name: str = "",
        table_name: str = "",
    ) -> None:
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
            # Open question 3, settled: a column node jumps to ITS OWN LINE
            # inside the `CREATE TABLE`, not to the table's banner. The line
            # index is what this feature builds; landing on the banner would
            # make the user search the column list by eye for the row they
            # just clicked, which is the work the jump exists to remove.
            span = self._detail_span("column", schema_name, table_name, column.name)
            if span is not None:
                leaf.setData(0, _SPAN_ROLE, span)
            group.addChild(leaf)

    def _add_constraints_group(
        self, table_item: QTreeWidgetItem, constraints, schema_name: str, table_name: str
    ) -> None:
        """The table's named constraints, under one `Constraints (N)` node
        (`FQ-260810183812`).

        Open question 1, settled: a constraint node jumps to its **inline
        constraint line inside the `CREATE TABLE`** rather than getting a
        statement of its own. That is the answer the owner's *"no ALTERs"*
        shape leaves: the synthesized DDL renders constraints inline, so an
        inline line is the only place a constraint exists in this buffer, and a
        dedicated `ALTER TABLE ADD CONSTRAINT` block would have to be invented
        to jump to -- exactly the kind of invention the reconstruction rule
        forbids.
        """
        constraints = sorted(constraints, key=lambda c: c.name)
        if not constraints:
            return
        group = QTreeWidgetItem([f"Constraints  ({len(constraints)})"])
        table_item.addChild(group)
        for constraint in constraints:
            marker = _CONSTRAINT_MARKERS.get(constraint.kind, "?")
            leaf = QTreeWidgetItem([f"{constraint.name} [{marker}]"])
            span = self._detail_span(
                "constraint", schema_name, table_name, constraint.name
            )
            if span is not None:
                leaf.setData(0, _SPAN_ROLE, span)
            group.addChild(leaf)

    def _add_indexes_group(
        self, table_item: QTreeWidgetItem, indexes, schema_name: str, table_name: str
    ) -> None:
        """The table's indexes, under one `Indexes (N)` node
        (`FQ-260810183812`).

        Constraint-backed indexes are listed like everything else (FQ-025's
        rule: hiding them makes a *"why is my unique index missing?"* mystery),
        but the buffer never renders a `CREATE INDEX` for one -- PostgreSQL
        would reject it, and the constraint already prints. So such a node
        navigates to the line of the CONSTRAINT that owns it, which is where
        that index genuinely is in this text.
        """
        indexes = sorted(indexes, key=lambda i: i.name)
        if not indexes:
            return
        group = QTreeWidgetItem([f"Indexes  ({len(indexes)})"])
        table_item.addChild(group)
        for index in indexes:
            marker = "U" if index.is_unique else "I"
            label = f"{index.name} [{marker}] ({index.method})" if index.method else (
                f"{index.name} [{marker}]"
            )
            leaf = QTreeWidgetItem([label])
            if index.is_constraint_backed:
                span = self._detail_span(
                    "constraint", schema_name, table_name, index.constraint_name
                )
            else:
                span = self._detail_span("index", schema_name, table_name, index.name)
            if span is not None:
                leaf.setData(0, _SPAN_ROLE, span)
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
            # `schema.name`, without the `[F]`/`[P]`/`[T]` marker and without
            # the zero-arg `()`: matching the label would make `f` hit every
            # function in the database.
            routine_item.setData(0, _FILTER_NAME_ROLE, qualified)
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
        # `schema.table.name`, without the `[B][D]` timing/event letters -- the
        # exact case §18.1 names, where matching the rendered text would make
        # `d` match every DELETE trigger. Both of a trigger's two occurrences
        # carry it, so one object is never half-hidden.
        leaf.setData(
            0, _FILTER_NAME_ROLE, f"{trigger.schema}.{trigger.table}.{trigger.name}"
        )
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
        """Navigate to whatever DDL the clicked item has, then populate the
        Properties panel for whatever table it belongs to.

        **Both, not either** (`FQ-260810183812`, open question 2): a table node
        already emitted `table_selected`, and withdrawing that to buy the new
        jump would trade a working behaviour for a new one. A routine or
        trigger row carries no table role, so it navigates and nothing more --
        exactly as before. An item with no span still navigates nowhere, which
        is what keeps this widening additive.
        """
        span = item.data(0, _SPAN_ROLE)
        if span is not None:
            self.navigate_requested.emit(span.start_line)
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
        menu = self.context_menu_for_item(self.tree.itemAt(pos))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def context_menu_for_item(self, item) -> QMenu:
        """The full menu for a right-click on `item` -- `item` being `None` for a
        click on the tree's empty area.

        `_menu_for_item`'s per-item gestures (when it offers any), plus
        **`Reload DDL`**, which BUG-062 requires "wherever in DDL Objects": every
        row, every branch root, the blank space below the last row, and the
        `browse_only` sandbox tree where `_menu_for_item` offers nothing at all.
        That is why this ALWAYS returns a menu while `_menu_for_item` may return
        None -- there is no longer a right-click here that offers nothing, so the
        "an empty menu under the cursor is worse than none" rule below stops
        being reachable rather than being overruled.

        Composed rather than folded into `_menu_for_item` so that method keeps
        meaning exactly "what does this ITEM offer", which is what its three
        keyed branches and their tests are about.

        NO `setShortcut` on the reload action: `Ctrl+Shift+R` has exactly one
        keyboard host, the `QShortcut` on the viewing pane (DEC-012).
        """
        menu = self._menu_for_item(item) if item is not None else None
        if menu is None:
            menu = QMenu(self)
        else:
            menu.addSeparator()
        menu.addAction(RELOAD_LABEL, self.reload_requested.emit)
        return menu

    def _is_checked_out(self, ref) -> bool:
        """Ask the host's predicate, treating "no predicate" and "the predicate
        raised" alike as NOT checked out.

        A raise is swallowed deliberately and only here: this runs while a
        context menu is being built, and the predicate reads the filesystem, so
        an unreadable project folder must cost the user one missing entry rather
        than an exception out of a right-click. The gesture it hides is
        destructive, so hiding is the safe direction."""
        if self._checked_out is None:
            return False
        try:
            return bool(self._checked_out(ref))
        except Exception:  # noqa: BLE001 -- see the docstring
            return False

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
        # A relation / column / constraint / index span is NAVIGABLE but not
        # EDITABLE (`FQ-260810183812`), so it must fall through to the branches
        # below rather than shadowing them -- a table node carries a span AND a
        # `_TABLE_ROLE`, and its `Alter Table ▸` menu is the one that matters.
        if span is not None and edit_refusal_for_span(span) is not None:
            span = None
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
            # BESIDE Edit DDL, and only for an object that actually HAS a local
            # working copy to throw away. Absent otherwise -- offering a
            # "discard" on something never checked out would be a dead entry
            # whose only possible outcome is an explanation.
            if self._is_checked_out(ref):
                menu.addAction(
                    DISCARD_LOCAL_LABEL,
                    lambda: self.discard_local_requested.emit(ref),
                )
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
            # nothing else, but it keeps the submenu rather than flattening its
            # entries: one shape for one action set, and the title is what tells
            # the user these act on the table rather than on the column in
            # place. (The title names the commonest case, not the output -- the
            # index, comment and drop entries emit `CREATE INDEX`/`DROP INDEX`/
            # `COMMENT ON`/`DROP TABLE`, never `ALTER TABLE`.)
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
