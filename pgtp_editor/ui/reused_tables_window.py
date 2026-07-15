"""ReusedTablesWindow: a non-modal window listing where each table is used.

Hosts a :class:`QTreeWidget` whose top-level rows are table/view names (with a
usage count) and whose children are the individual usage breadcrumbs produced
by :func:`pgtp_editor.analysis.reused_tables.collect_table_usages`. Intentionally
non-modal (a top-level ``QMainWindow`` shown via ``show()``, never ``exec()``);
MainWindow holds a reference so it is not garbage-collected and reuses the same
window on subsequent opens.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTreeWidget, QTreeWidgetItem


class ReusedTablesWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find Reused Tables")
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Table / Usage"])
        self.setCentralWidget(self.tree)
        self.resize(600, 500)

    def set_usages(self, usages) -> None:
        self.tree.clear()
        for usage in usages:
            top = QTreeWidgetItem([f"{usage.name}  ({len(usage.breadcrumbs)})"])
            for breadcrumb in usage.breadcrumbs:
                top.addChild(QTreeWidgetItem([breadcrumb]))
            self.tree.addTopLevelItem(top)
