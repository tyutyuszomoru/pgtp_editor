"""DiffMergePanel: the shared viewer for all three Diff/Merge comparison
entry points (file-level, page-level, detail-level). Populates the
existing empty "Diff / Merge" center-stage tab with a change-list tree
(left) and a detail view (right). Read-only — no write-back to disk (see
docs/superpowers/specs/2026-07-12-pgtp-editor-diff-merge-viewer-ui-design.md).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

DIFFERENCE_ROLE = Qt.ItemDataRole.UserRole


class DiffMergePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.tree)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter)

    def show_differences(self, differences: list) -> None:
        """Build the change-list tree fresh from `differences`, clearing
        any previous content — one comparison session at a time."""
        self.tree.clear()
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


def leaf_label(diff) -> str:
    if diff.attribute is not None:
        label = f"{diff.attribute}: {diff.kind}"
    else:
        label = f"{diff.path[-1]}: {diff.kind}"
    return f"⚠ {label}" if diff.ambiguous else label
