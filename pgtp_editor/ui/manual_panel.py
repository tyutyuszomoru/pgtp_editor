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

from dataclasses import dataclass
from importlib.resources import files

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class Chapter:
    level: int
    title: str


def load_manual_text() -> str:
    resource = files("pgtp_editor") / "resources" / "manual.md"
    return resource.read_text(encoding="utf-8")


def parse_chapters(md_text: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    in_fence = False
    fence_marker = ""
    for raw in md_text.splitlines():
        stripped = raw.strip()
        if in_fence:
            if stripped.startswith(fence_marker):
                in_fence = False
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = True
            fence_marker = stripped[:3]
            continue
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            rest = stripped[hashes:]
            # ATX heading requires a space after the hashes (CommonMark/Qt).
            if 1 <= hashes <= 6 and rest.startswith(" "):
                title = rest.strip()
                if title:
                    chapters.append(Chapter(hashes, title))
    return chapters


class ManualPanel(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self._markdown = ""

    def set_markdown(self, text: str) -> None:
        self._markdown = text
        self.setMarkdown(text)

    def scroll_to_chapter(self, index: int) -> None:
        if index < 0:
            return
        doc = self.document()
        seen = -1
        block = doc.begin()
        while block.isValid():
            if block.blockFormat().headingLevel() > 0:
                seen += 1
                if seen == index:
                    cursor = QTextCursor(block)
                    self.setTextCursor(cursor)
                    top = self.cursorRect().top()
                    bar = self.verticalScrollBar()
                    bar.setValue(bar.value() + top)
                    return
            block = block.next()


class ManualContentsPanel(QWidget):
    chapter_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)
        self.tree.itemClicked.connect(self._on_item_clicked)

    def set_chapters(self, chapters) -> None:
        self.tree.clear()
        last_h2 = None
        title_item = None
        for index, ch in enumerate(chapters):
            item = QTreeWidgetItem([ch.title])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            if ch.level <= 1:
                self.tree.addTopLevelItem(item)
                title_item = item
                last_h2 = None
            elif ch.level == 2:
                if title_item is not None:
                    title_item.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                last_h2 = item
            else:  # level >= 3
                parent = last_h2 or title_item
                if parent is not None:
                    parent.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
        self.tree.expandAll()

    def _on_item_clicked(self, item, _column) -> None:
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.chapter_selected.emit(int(index))
