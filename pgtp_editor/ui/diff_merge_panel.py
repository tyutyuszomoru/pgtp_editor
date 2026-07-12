"""DiffMergePanel: the shared viewer for all three Diff/Merge comparison
entry points (file-level, page-level, detail-level). Populates the
existing empty "Diff / Merge" center-stage tab with a change-list tree
(left) and a detail view (right). Read-only — no write-back to disk (see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-viewer-ui-design.md).
"""
from __future__ import annotations

import difflib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

DIFFERENCE_ROLE = Qt.ItemDataRole.UserRole

# node_kind values whose old_value/new_value (for an added/removed record)
# is a whole PageNode/DetailNode/ColumnNode, per spec §3.6 case 2.
SUBTREE_NODE_KINDS = {"page", "detail", "column"}


def leaf_label(diff) -> str:
    if diff.attribute is not None:
        label = f"{diff.attribute}: {diff.kind}"
    else:
        label = f"{diff.path[-1]}: {diff.kind}"
    return f"⚠ {label}" if diff.ambiguous else label


class DiffMergePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)

        self._build_detail_views()

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.detail_stack)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter)

    def _build_detail_views(self):
        self.detail_stack = QStackedWidget()

        self.empty_view = QWidget()
        self.detail_stack.addWidget(self.empty_view)

        self.attribute_view = QWidget()
        self.attribute_old_label = QLabel()
        self.attribute_new_label = QLabel()
        attribute_layout = QVBoxLayout(self.attribute_view)
        attribute_layout.addWidget(self.attribute_old_label)
        attribute_layout.addWidget(self.attribute_new_label)
        self.detail_stack.addWidget(self.attribute_view)

        self.subtree_view = QWidget()
        self.subtree_table = QTableWidget(0, 2)
        self.subtree_table.setHorizontalHeaderLabels(["Attribute", "Value"])
        subtree_layout = QVBoxLayout(self.subtree_view)
        subtree_layout.addWidget(self.subtree_table)
        self.detail_stack.addWidget(self.subtree_view)

        self.event_diff_view = QWidget()
        self.event_diff_text = QPlainTextEdit()
        self.event_diff_text.setReadOnly(True)
        event_diff_layout = QVBoxLayout(self.event_diff_view)
        event_diff_layout.addWidget(self.event_diff_text)
        self.detail_stack.addWidget(self.event_diff_view)

        self.detail_stack.setCurrentWidget(self.empty_view)

    def show_differences(self, differences: list) -> None:
        """Build the change-list tree fresh from `differences`, clearing
        any previous content — one comparison session at a time."""
        self.tree.clear()
        self.detail_stack.setCurrentWidget(self.empty_view)
        items_by_prefix: dict[tuple, QTreeWidgetItem] = {}

        for diff in differences:
            *prefix_segments, _ = diff.path
            parent = None
            accumulated: tuple = ()
            for segment in prefix_segments:
                accumulated += (segment,)
                item = items_by_prefix.get(accumulated)
                if item is None:
                    item = QTreeWidgetItem([segment])
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                    if parent is not None:
                        parent.addChild(item)
                    else:
                        self.tree.addTopLevelItem(item)
                    items_by_prefix[accumulated] = item
                parent = item

            leaf = QTreeWidgetItem([leaf_label(diff)])
            leaf.setData(0, DIFFERENCE_ROLE, diff)
            leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            leaf.setCheckState(0, Qt.CheckState.Unchecked)
            if parent is not None:
                parent.addChild(leaf)
            else:
                self.tree.addTopLevelItem(leaf)

    def _on_current_item_changed(self, current, previous):
        diff = current.data(0, DIFFERENCE_ROLE) if current is not None else None
        if diff is None:
            self.detail_stack.setCurrentWidget(self.empty_view)
            return
        self._show_difference_detail(diff)

    def _show_difference_detail(self, diff):
        if diff.attribute is not None:
            self.attribute_old_label.setText(f"Old: {diff.old_value}")
            self.attribute_new_label.setText(f"New: {diff.new_value}")
            self.detail_stack.setCurrentWidget(self.attribute_view)
            return

        if diff.node_kind == "event" and diff.kind == "changed":
            old_lines = (diff.old_value or "").splitlines()
            new_lines = (diff.new_value or "").splitlines()
            diff_text = "\n".join(difflib.unified_diff(old_lines, new_lines, lineterm=""))
            self.event_diff_text.setPlainText(diff_text)
            self.detail_stack.setCurrentWidget(self.event_diff_view)
            return

        if diff.node_kind in SUBTREE_NODE_KINDS:
            node = diff.new_value if diff.new_value is not None else diff.old_value
            attrib = node.attrib
            self.subtree_table.setRowCount(len(attrib))
            for row, (key, value) in enumerate(attrib.items()):
                self.subtree_table.setItem(row, 0, QTableWidgetItem(str(key)))
                self.subtree_table.setItem(row, 1, QTableWidgetItem(str(value)))
            self.detail_stack.setCurrentWidget(self.subtree_view)
            return

        # An event added/removed record (whole EventNode, not raw text) —
        # still a whole-subtree case, but EventNode has no .attrib dict, so
        # render its tag_name/side/text as key-value rows instead.
        node = diff.new_value if diff.new_value is not None else diff.old_value
        rows = [("tag_name", node.tag_name), ("side", node.side), ("text", node.text)]
        self.subtree_table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.subtree_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.subtree_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.detail_stack.setCurrentWidget(self.subtree_view)

    def _flattened_leaves(self) -> list[QTreeWidgetItem]:
        leaves: list[QTreeWidgetItem] = []

        def visit(item: QTreeWidgetItem):
            if item.data(0, DIFFERENCE_ROLE) is not None:
                leaves.append(item)
            for i in range(item.childCount()):
                visit(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))
        return leaves

    def checked_differences(self) -> list:
        """Enumerate the Difference object for every leaf whose checkbox is
        checked, in the same tree order _flattened_leaves() already walks.
        Group/prefix nodes have no DIFFERENCE_ROLE payload and are never
        checkable, so they never appear here."""
        return [
            leaf.data(0, DIFFERENCE_ROLE)
            for leaf in self._flattened_leaves()
            if leaf.checkState(0) == Qt.CheckState.Checked
        ]

    def _current_leaf_position(self, leaves: list[QTreeWidgetItem]) -> int:
        current = self.tree.currentItem()
        if current is None:
            return -1
        try:
            return leaves.index(current)
        except ValueError:
            return -1

    def select_next_difference(self) -> None:
        leaves = self._flattened_leaves()
        if not leaves:
            return
        position = self._current_leaf_position(leaves)
        next_position = min(position + 1, len(leaves) - 1)
        self.tree.setCurrentItem(leaves[next_position])

    def select_previous_difference(self) -> None:
        leaves = self._flattened_leaves()
        if not leaves:
            return
        position = self._current_leaf_position(leaves)
        previous_position = max(position - 1, 0)
        self.tree.setCurrentItem(leaves[previous_position])
