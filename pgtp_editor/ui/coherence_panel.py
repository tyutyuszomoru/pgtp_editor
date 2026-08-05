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

# pgtp_editor/ui/coherence_panel.py
"""CoherencePanel: the left-dock "Database/XML Coherence" tree (§17).

Renders a `db/coherence.py::CoherenceTree` — the one surface that replaced
three: the XML → Database check, the Database → XML check and the standalone
"Table references" tab. **The live database is the truth; the XML is the
interface being checked against it**, so there is no direction control here:
each relation shows its DB columns and its XML references side by side, and the
Pages branch shows the XML's own recursion (Page ▸ Detail ▸ Detail ▸ … ▸ lookup)
at whatever depth the document actually has.

**Structural choice: two top-level roots in one `QTreeWidget`, not two
sub-tabs.** The mismatch toggle is specified as *one global control spanning
both branches*; behind sub-tabs it would silently hide half of what it just
filtered, and the honest "compared, and fully coherent" state would have to be
answered twice, once per tab. One tree also lets the two branch rows carry their
own flagged counts next to each other, which is the first thing a reader wants
after flipping the toggle. Two columns — label, then badges — keep the badge
text out of the deep Pages indentation so it stays readable at depth.

Nothing here re-derives state. `flagged`, the badges, the recursion and the
pruning all come from `db/coherence.py`; the panel only maps them to glyphs,
colours and rows. It opens no connection and runs no SQL.

Carried over from `DbCheckPanel` unchanged: the header (`user@host:port/db` plus
a mismatch count, minus the direction label), the `(T)`/`(V)`/`(M)` relation
prefixes, the three-way column glyph convention (calculated → orange ``~``, ok →
green ``✓``, else red ``✗``), and the uniform ``(kind, name, ok,
is_calculated)`` UserRole payload.

Non-modal and test-driven: the tree, header label, checkbox and empty-state
label are exposed; `contextual_rename` / `create_menu_items` / the double-click
handler emit their signals directly, with no `.exec()` on any path a test
reaches.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QHeaderView,
    QLabel,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.coherence import (
    BADGE_CALCULATED,
    BADGE_MISSING_IN_DB,
    BADGE_NOT_IN_XML,
    BADGE_UNREFERENCED,
    CoherenceNode,
    CoherenceTree,
    flagged_count,
)

# The shipped DbCheckPanel palette, kept verbatim (§17: "the shipped three-way
# glyph/color convention carries over unchanged"). These are foreground colours
# chosen to read against both the dark QSS and the cleared light stylesheet;
# every *other* colour in this panel comes from the palette, never a literal.
_OK_COLOR = QColor("#1a9e1a")
_BAD_COLOR = QColor("#d02020")
_CALC_COLOR = QColor("#d08a1a")

_KIND_PREFIX = {"table": "(T) ", "view": "(V) ", "matview": "(M) "}

#: Badges that mean "this row is the problem", used to colour the badge cell.
_PROBLEM_BADGES = frozenset({BADGE_MISSING_IN_DB, BADGE_NOT_IN_XML, BADGE_UNREFERENCED})

#: Kinds whose rows can be navigated to in the XML when they carry a line.
_XML_KINDS = frozenset({"page", "detail", "lookup", "reference"})

NOT_COMPARED_TEXT = (
    "Nothing compared yet — run Database/XML Coherence from the Database menu."
)
COHERENT_TEXT = "Compared: the XML and the database agree. Nothing needs attention."
NO_MISMATCHES_TEXT = "No mismatches to show. Untick “Show only mismatches” to see everything."

_ROW_ROLE = Qt.ItemDataRole.UserRole  # (kind, name, ok, is_calculated) — DbCheckPanel shape
_NODE_ROLE = Qt.ItemDataRole.UserRole + 1  # the CoherenceNode itself

_BADGE_SEPARATOR = " · "


class CoherencePanel(QWidget):
    """Render one `CoherenceTree`. See the module docstring for the layout."""

    # (node | None, kind:str | None) — drives the Properties panel; mirrors
    # TableReferencesPanel so MainWindow can reuse its existing slot.
    selection_changed = Signal(object, object)
    # (line:int | None) — double-click on an XML-sourced row.
    jump_requested = Signal(object)
    # (kind, name) — double-click on a DB-sourced relation/column row.
    name_jump_requested = Signal(str, str)
    # (kind, old_name) — "rename in XML…" on a row the DB does not have.
    rename_requested = Signal(str, str)
    # (what: page|detail|lookup, table_name) — create-from-relation.
    create_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tree: CoherenceTree | None = None
        self._connection_summary = ""

        self.header_label = QLabel("")
        self.header_label.setWordWrap(True)

        self.filter_checkbox = QCheckBox("Show only mismatches")
        self.filter_checkbox.setToolTip(
            "Prune both branches to the rows needing attention, keeping the path "
            "down to each one."
        )
        self.filter_checkbox.toggled.connect(self._rebuild)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Node", "Details"])
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        # A deep Pages branch is the normal case, not the exotic one: a tight
        # indent keeps a level-four Detail's label on screen in a narrow dock.
        self.tree.setIndentation(14)
        self.tree.setExpandsOnDoubleClick(False)  # double-click navigates instead
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        self.empty_label = QLabel(NOT_COMPARED_TEXT)
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMargin(12)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header_label)
        layout.addWidget(self.filter_checkbox)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.empty_label, 1)

        self.clear()

    # -- population ----------------------------------------------------------

    def set_result(self, tree: CoherenceTree, connection_summary: str) -> None:
        """Show `tree`, compared against the database named by
        `connection_summary` (`user@host:port/db`)."""
        self._tree = tree
        self._connection_summary = connection_summary
        self._update_header()
        self._rebuild()

    def clear(self) -> None:
        """Back to the "nothing compared yet" state (project close, §17)."""
        self._tree = None
        self._connection_summary = ""
        self.tree.clear()
        self._update_header()
        self._rebuild()

    @property
    def result(self) -> CoherenceTree | None:
        """The unfiltered tree currently shown, or None."""
        return self._tree

    def _update_header(self) -> None:
        if self._tree is None:
            self.header_label.setText("Database/XML Coherence — not compared yet")
            return
        count = self._tree.flagged_count
        noun = "mismatch" if count == 1 else "mismatches"
        # The count is of the whole tree, independent of the filter — as in
        # DbCheckPanel, the header answers "how bad is it", not "what is shown".
        self.header_label.setText(
            f"Database/XML Coherence   {self._connection_summary}   —   {count} {noun}"
        )

    def _rebuild(self) -> None:
        self.tree.clear()
        if self._tree is None:
            self._show_placeholder(NOT_COMPARED_TEXT)
            return

        only_mismatches = self.filter_checkbox.isChecked()
        shown = self._tree.filtered() if only_mismatches else self._tree
        branches = [self._make_branch_item(branch) for branch in shown.branches]
        if not any(branch.childCount() for branch in branches):
            # Two honest, distinguishable "nothing to show" states: the tree is
            # genuinely clean, versus the filter hid everything that was there.
            self._show_placeholder(
                COHERENT_TEXT if self._tree.flagged_count == 0 else NO_MISMATCHES_TEXT
            )
            return

        self.tree.addTopLevelItems(branches)
        for branch in branches:
            branch.setExpanded(True)
        if only_mismatches:
            # The pruned tree is small and every surviving row is there for a
            # reason — showing it collapsed would hide the answer.
            self.tree.expandAll()
        self._show_tree()

    def _show_placeholder(self, text: str) -> None:
        self.empty_label.setText(text)
        self.empty_label.setVisible(True)
        self.tree.setVisible(False)

    def _show_tree(self) -> None:
        self.empty_label.setVisible(False)
        self.tree.setVisible(True)

    # -- item builders -------------------------------------------------------

    def _make_branch_item(self, branch: CoherenceNode) -> QTreeWidgetItem:
        item = self._make_item(branch)
        flagged = flagged_count(branch)  # the model's own count, not a re-walk
        noun = "row" if flagged == 1 else "rows"
        item.setText(1, f"{flagged} flagged {noun}" if flagged else "no flags")
        item.setForeground(1, QBrush(_BAD_COLOR if flagged else _OK_COLOR))
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        return item

    def _make_item(self, node: CoherenceNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([self._label_for(node), self._badge_text(node)])
        self._apply_glyph_colour(item, node)
        self._apply_badge_colour(item, node)
        item.setData(0, _NODE_ROLE, node)
        item.setData(
            0,
            _ROW_ROLE,
            (
                node.kind,
                node.table_name or node.label,
                not node.flagged,
                BADGE_CALCULATED in node.badges,
            ),
        )
        tooltip = node.label
        if node.badges:
            tooltip = f"{tooltip}\n{_BADGE_SEPARATOR.join(node.badges)}"
        if node.line is not None:
            tooltip = f"{tooltip}\nXML line {node.line} — double-click to jump"
        item.setToolTip(0, tooltip)
        if node.kind == "column" and self._is_pk(node):
            font = item.font(0)
            font.setUnderline(True)
            item.setFont(0, font)
        for child in node.children:
            item.addChild(self._make_item(child))
        return item

    # -- presentation rules --------------------------------------------------

    @staticmethod
    def _is_pk(node: CoherenceNode) -> bool:
        info = getattr(node.payload, "info", None)
        return bool(getattr(info, "is_pk", False))

    def _label_for(self, node: CoherenceNode) -> str:
        glyph = self._glyph_for(node)
        prefix = ""
        if node.kind == "relation":
            # (T)/(V)/(M), from the kind badge the model already put there.
            for badge in node.badges:
                prefix = _KIND_PREFIX.get(badge, "")
                if prefix:
                    break
        return f"{glyph} {prefix}{node.label}".strip()

    def _glyph_for(self, node: CoherenceNode) -> str:
        if node.kind in ("branch", "group"):
            return ""
        if node.kind == "column" and BADGE_CALCULATED in node.badges:
            # BUG-006: calculated columns are DB-less by design — orange and
            # informational, never a red mismatch.
            return "~"
        return "✗" if node.flagged else "✓"

    def _colour_for(self, node: CoherenceNode) -> QColor | None:
        if node.kind in ("branch", "group"):
            return None
        if node.kind == "column" and BADGE_CALCULATED in node.badges:
            return _CALC_COLOR
        return _BAD_COLOR if node.flagged else _OK_COLOR

    def _apply_glyph_colour(self, item: QTreeWidgetItem, node: CoherenceNode) -> None:
        colour = self._colour_for(node)
        if colour is not None:
            item.setForeground(0, QBrush(colour))

    def _badge_text(self, node: CoherenceNode) -> str:
        badges = list(node.badges)
        if node.kind == "relation":
            # §17 keeps BUG-026's role split as the relation-level badge. The
            # numbers are read straight off the TableCheck the model attached —
            # no second counting pass anywhere in this panel.
            check = node.payload
            if check is not None:
                badges.insert(
                    0,
                    f"(P{check.page_count} D{check.detail_count} L{check.lookup_count})",
                )
        return _BADGE_SEPARATOR.join(badge for badge in badges if badge)

    def _apply_badge_colour(self, item: QTreeWidgetItem, node: CoherenceNode) -> None:
        if _PROBLEM_BADGES.intersection(node.badges):
            item.setForeground(1, QBrush(_BAD_COLOR))
            return
        if BADGE_CALCULATED in node.badges:
            item.setForeground(1, QBrush(_CALC_COLOR))
            return
        # Everything else is secondary information: palette-derived so it dims
        # correctly under both the dark QSS and the light theme.
        item.setForeground(1, QBrush(self.palette().placeholderText().color()))
        font = item.font(1)
        font.setItalic(True)
        item.setFont(1, font)

    # -- interaction ---------------------------------------------------------

    @staticmethod
    def node_for(item: QTreeWidgetItem | None) -> CoherenceNode | None:
        """The `CoherenceNode` behind a tree row, or None."""
        if item is None:
            return None
        node = item.data(0, _NODE_ROLE)
        return node if isinstance(node, CoherenceNode) else None

    def _on_current_changed(self, current, _previous) -> None:
        node = self.node_for(current)
        if node is None or node.node is None:
            self.selection_changed.emit(None, None)
            return
        # A lookup row's model node is the owning ColumnNode — the semantic the
        # Table References panel already had, kept so Properties behaves the same.
        self.selection_changed.emit(node.node, node.kind)

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        node = self.node_for(item)
        if node is None:
            return
        if node.kind in _XML_KINDS and node.line is not None:
            self.jump_requested.emit(node.line)
            return
        if node.kind in ("relation", "column"):
            self.name_jump_requested.emit(node.kind, node.table_name or node.label)

    def rename_menu_label(self, item: QTreeWidgetItem | None) -> str | None:
        """The "rename in XML…" label for `item`, or None when it does not
        apply. Pure, so tests can assert the menu without a popup.

        Offered only where the XML names something the database does not have —
        the direction-free replacement for `DbCheckPanel`'s `xml_to_db` gate.
        Calculated columns (BUG-006) never qualify: they have no DB-side name to
        reconcile with.
        """
        node = self.node_for(item)
        if node is None or not node.flagged or BADGE_CALCULATED in node.badges:
            return None
        if node.kind == "column" and BADGE_MISSING_IN_DB in node.badges:
            return "Rename column in XML…"
        if node.kind in ("page", "detail", "lookup") and node.table_name:
            return "Rename table in XML…"
        return None

    def contextual_rename(self, item: QTreeWidgetItem | None) -> None:
        """Emit `rename_requested` for a row the database does not have."""
        if self.rename_menu_label(item) is None:
            return
        node = self.node_for(item)
        if node.kind == "column":
            self.rename_requested.emit("column", node.label)
        else:
            self.rename_requested.emit("table", node.table_name)

    # "what" -> menu label, for the create actions on a Tables-and-Views row.
    _CREATE_ACTIONS = (
        ("page", "Create new page from this table"),
        ("detail", "Create new detail from this table…"),
        ("lookup", "Create new lookup from this table…"),
    )

    def create_menu_items(self, item: QTreeWidgetItem | None) -> list[tuple[str, str]]:
        """The (what, label) create actions available for `item`. Only
        relation rows in the Tables and Views branch qualify. Pure — no popup —
        so tests can assert the menu contents without a modal."""
        node = self.node_for(item)
        if node is None or node.kind != "relation":
            return []
        return list(self._CREATE_ACTIONS)

    def request_create(self, what: str, item: QTreeWidgetItem) -> None:
        """Emit `create_requested(what, table_name)` for a relation row."""
        node = self.node_for(item)
        if node is None or node.kind != "relation" or not node.table_name:
            return
        self.create_requested.emit(what, node.table_name)

    def _on_context_menu(self, pos) -> None:  # pragma: no cover - GUI popup
        item = self.tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self.tree)
        rename_label = self.rename_menu_label(item)
        if rename_label is not None:
            action = menu.addAction(rename_label)
            action.triggered.connect(lambda _checked=False: self.contextual_rename(item))
        create_items = self.create_menu_items(item)
        if create_items:
            if not menu.isEmpty():
                menu.addSeparator()
            for what, label in create_items:
                action = menu.addAction(label)
                action.triggered.connect(
                    lambda _checked=False, w=what: self.request_create(w, item)
                )
        if menu.isEmpty():
            return
        menu.exec(self.tree.viewport().mapToGlobal(pos))
