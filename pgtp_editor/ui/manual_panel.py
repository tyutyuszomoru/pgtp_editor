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
