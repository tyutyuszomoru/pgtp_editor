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

**Filtering is one composable mechanism, not several (FQ-008).** The mismatch
toggle and the three role filters ("P>1"/"D>1"/"L>1", over the very
`page_count`/`detail_count`/`lookup_count` numbers the relation badge already
prints) all feed one `_apply_filters` call on the model tree: the role filters
AND each other, and their result is AND-ed with the mismatch toggle, so ticking
another box can only ever narrow. Whatever is active is spelled out — combination
included — in the active-filter banner with a Clear button, because a filter the
reader cannot see is the bug BUG-020 was raised for.

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
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
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
    ROLE_COUNT_ATTRS,
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

#: The Caption panel's active-filter accent (`caption_management_panel.py`'s
#: `_FILTER_HEADER_FOREGROUND`), repeated as a literal rather than imported so
#: this panel keeps no dependency on that one; "a filter is active" should look
#: the same in both surfaces.
_FILTER_BANNER_FOREGROUND = QColor("#4fc3f7")

#: Badges that mean "this row is the problem", used to colour the badge cell.
_PROBLEM_BADGES = frozenset({BADGE_MISSING_IN_DB, BADGE_NOT_IN_XML, BADGE_UNREFERENCED})

#: Kinds whose rows can be navigated to in the XML when they carry a line.
_XML_KINDS = frozenset({"page", "detail", "lookup", "reference"})

NOT_COMPARED_TEXT = (
    "Nothing compared yet — run Database/XML Coherence from the Database menu."
)
COHERENT_TEXT = "Compared: the XML and the database agree. Nothing needs attention."
NO_MISMATCHES_TEXT = "No mismatches to show. Untick “Show only mismatches” to see everything."
#: The role filters (or a role filter combined with the mismatch toggle) matched
#: nothing. Distinct from NO_MISMATCHES_TEXT because "untick Show only
#: mismatches" would be wrong advice when a P/D/L box is what emptied the tree.
NO_MATCHES_TEXT = "No rows match the active filters — use “Clear filters” to see everything."

#: Role -> ("checkbox label", "what the filter means") for the P>1/D>1/L>1
#: filters (FQ-008). The short form matches the "(P# D# L#)" relation badge this
#: same view already prints, so the checkbox and the number it filters on are
#: recognizably the same thing; the long form is the tooltip and the wording the
#: active-filter banner uses, so nothing about the filter is left to guess.
_ROLE_FILTERS = (
    ("page", "P>1", "more than one Page"),
    ("detail", "D>1", "more than one Detail"),
    ("lookup", "L>1", "more than one Lookup"),
)

#: The banner's name for the mismatch toggle, in the same voice as the role
#: descriptions above so a combined filter reads as one sentence.
_MISMATCH_DESCRIPTION = "mismatches only"

#: How the banner joins two active filters. Spelled out because the composition
#: is the one thing a reader must not have to guess: every active condition has
#: to hold (AND), so ticking a second box always narrows the result.
_FILTER_CONJUNCTION = " AND "

#: Internal `CoherenceNode.kind` -> the host-facing kind vocabulary MainWindow's
#: name-based slots speak (`_on_db_jump_requested` / `_on_db_rename_requested`
#: both test `kind == "table"`, and §17 binds the carried-over
#: `jump_requested(kind, name)` / `(kind, name, ok, is_calculated)` shapes to
#: `DbCheckPanel`'s `"table"`). A DB relation is `"relation"` internally, so it
#: must be normalized on the way out — the omission of exactly this was BUG-032
#: facet A. `contextual_rename` already did it by hand; this is the one mapping.
_HOST_KIND = {"relation": "table"}

#: The internal kinds deliberately passed through to the host unchanged, i.e.
#: the ones whose internal spelling *is* the host spelling. Together with
#: `_HOST_KIND` this must cover every kind `db/coherence.py` can put in a node —
#: a kind in neither is an unmapped kind reaching MainWindow, which is exactly
#: BUG-032 facet A. `tests/ui/test_coherence_panel.py` asserts that totality
#: over the kinds a real tree actually contains, so adding a kind to the model
#: without deciding its host spelling fails there rather than in the host.
_IDENTITY_HOST_KINDS = frozenset(
    {"branch", "group", "column", "reference", "page", "detail", "lookup"}
)

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
            "down to each one. Combines with P>1/D>1/L>1: every ticked condition "
            "must hold."
        )
        self.filter_checkbox.toggled.connect(self._rebuild)

        # The P>1/D>1/L>1 role filters (FQ-008). Independent checkboxes, one
        # rebuild path shared with the mismatch toggle, and every active one
        # named in the banner below — a filter nobody can see is the bug
        # BUG-020 was raised for.
        self.role_checkboxes: dict[str, QCheckBox] = {}
        role_row = QHBoxLayout()
        role_row.setContentsMargins(0, 0, 0, 0)
        for role, short, description in _ROLE_FILTERS:
            box = QCheckBox(short)
            box.setToolTip(
                f"Show only relations the XML uses in {description} "
                f"({ROLE_COUNT_ATTRS[role].replace('_', ' ')} > 1, the same number the "
                "“(P# D# L#)” badge prints). Combines with the other boxes and "
                "with “Show only mismatches”: every ticked condition must hold."
            )
            box.toggled.connect(self._rebuild)
            self.role_checkboxes[role] = box
            role_row.addWidget(box)
        role_row.addStretch(1)

        # Active-filter banner (BUG-020's rule applied here): the moment any
        # filter is on, say which one — including the combination — and offer a
        # single way out. Deliberately the panel's own one-label row, not the
        # Caption panel's proxy-model apparatus: three booleans plus a toggle
        # need no proxy.
        self.filter_banner_label = QLabel("")
        self.filter_banner_label.setWordWrap(True)
        # The same accent the Caption panel's active-filter banner uses, so
        # "something is filtering" looks the same wherever the user meets it.
        self.filter_banner_label.setStyleSheet(
            f"font-weight: bold; color: {_FILTER_BANNER_FOREGROUND.name()};"
        )
        self.clear_filters_button = QPushButton("Clear filters")
        self.clear_filters_button.clicked.connect(self.clear_filters)
        self.filter_banner = QWidget()
        banner_row = QHBoxLayout(self.filter_banner)
        banner_row.setContentsMargins(0, 0, 0, 0)
        banner_row.addWidget(self.filter_banner_label, 1)
        banner_row.addWidget(self.clear_filters_button)
        self.filter_banner.setVisible(False)

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
        layout.addLayout(role_row)
        layout.addWidget(self.filter_banner)
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

    # -- filtering (FQ-008) --------------------------------------------------

    def active_roles(self) -> list[str]:
        """The ticked role filters, in P/D/L order."""
        return [
            role
            for role, _short, _desc in _ROLE_FILTERS
            if self.role_checkboxes[role].isChecked()
        ]

    def any_filter_active(self) -> bool:
        return self.filter_checkbox.isChecked() or bool(self.active_roles())

    def clear_filters(self) -> None:
        """Untick every filter and rebuild once (the banner's Clear button)."""
        boxes = [self.filter_checkbox, *self.role_checkboxes.values()]
        for box in boxes:
            box.blockSignals(True)
            box.setChecked(False)
            box.blockSignals(False)
        self._rebuild()

    def filter_description(self) -> str:
        """Every active filter, joined by " AND ", or "" when none is active.

        The order is fixed (mismatch toggle first, then P, D, L) so the same
        combination always reads the same way.
        """
        parts: list[str] = []
        if self.filter_checkbox.isChecked():
            parts.append(_MISMATCH_DESCRIPTION)
        parts += [
            f"{description} ({short})"
            for role, short, description in _ROLE_FILTERS
            if self.role_checkboxes[role].isChecked()
        ]
        return _FILTER_CONJUNCTION.join(parts)

    def _apply_filters(self, tree: CoherenceTree) -> CoherenceTree:
        """`tree` narrowed by every active filter.

        Composition, in one place: the role filters AND each other (a relation
        must satisfy every ticked one), and the result is AND-ed with the
        mismatch toggle. Mechanically the roles run first as a *scope* over
        relations and the mismatch toggle then selects rows *within* that scope
        — the reading that cannot silently drop a row, because a flagged column
        or reference under an in-scope relation has no role counts of its own
        and would vanish under a naive per-row AND.
        """
        roles = self.active_roles()
        if roles:
            tree = tree.scoped_to_tables(tree.role_qualifying_tables(roles))
        if self.filter_checkbox.isChecked():
            tree = tree.filtered()
        return tree

    def _refresh_filter_banner(self, shown: CoherenceTree | None) -> None:
        """Name the active filter combination and how much it hid. Hidden only
        when nothing is filtering."""
        description = self.filter_description()
        if self._tree is None or not description:
            self.filter_banner.setVisible(False)
            return
        total = self._tree.row_count
        visible = shown.row_count if shown is not None else 0
        self.filter_banner_label.setText(
            f"Filtered: {description} — showing {visible} of {total} rows"
        )
        self.filter_banner.setVisible(True)

    def _rebuild(self) -> None:
        self.tree.clear()
        if self._tree is None:
            self._refresh_filter_banner(None)
            self._show_placeholder(NOT_COMPARED_TEXT)
            return

        shown = self._apply_filters(self._tree)
        self._refresh_filter_banner(shown)
        branches = [self._make_branch_item(branch) for branch in shown.branches]
        if not any(branch.childCount() for branch in branches):
            # Three honest, distinguishable "nothing to show" states: the tree
            # is genuinely clean; the mismatch toggle alone hid everything; or a
            # role filter is part of what emptied it, where "untick Show only
            # mismatches" would be the wrong advice.
            if self.active_roles():
                text = NO_MATCHES_TEXT
            else:
                text = COHERENT_TEXT if self._tree.flagged_count == 0 else NO_MISMATCHES_TEXT
            self._show_placeholder(text)
            return

        self.tree.addTopLevelItems(branches)
        for branch in branches:
            branch.setExpanded(True)
        if self.any_filter_active():
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
                _HOST_KIND.get(node.kind, node.kind),
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
        # A reference row's model node is likewise the Page/Detail/Column that
        # does the referencing, and `node_kind` says which — without it those
        # rows rendered an empty Properties panel (BUG-032).
        self.selection_changed.emit(node.node, node.node_kind or node.kind)

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        node = self.node_for(item)
        if node is None:
            return
        if node.kind in _XML_KINDS and node.line is not None:
            self.jump_requested.emit(node.line)
            return
        if node.kind in ("relation", "column"):
            self.name_jump_requested.emit(
                _HOST_KIND.get(node.kind, node.kind), node.table_name or node.label
            )

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
