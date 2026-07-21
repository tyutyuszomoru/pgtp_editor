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

"""Breeze toolbar icons: load vendored SVGs, recolor them, render QIcons.

The vendored Breeze SVGs (``resources/icons/breeze/``) express their color via
``fill:currentColor`` plus an embedded ``.ColorScheme-Text { color:#232629; }``
stylesheet. QtSvg does NOT reliably resolve ``currentColor``, so we substitute a
concrete fill into the SVG *text* before handing it to the renderer -- both the
``currentColor`` token and the stylesheet ``color:#232629`` value, belt and
suspenders, so a literal fill is always present.

The pure string helpers (``ACTION_ICON_FILES``, ``load_svg_text``,
``recolor_svg``) are Qt-free; only ``themed_icon`` touches Qt.
"""
import re
from importlib.resources import files

# Toolbar command id -> vendored Breeze SVG filename.
ACTION_ICON_FILES: dict[str, str] = {
    "open": "document-open.svg",
    "save": "document-save.svg",
    "undo": "edit-undo.svg",
    "redo": "edit-redo.svg",
    "find": "edit-find.svg",
    "validate": "dialog-ok-apply.svg",
    "generate": "run-build.svg",
}

# Breeze's ColorScheme-Text default color, matched case-insensitively.
_BREEZE_COLOR_RE = re.compile(r"#232629", re.IGNORECASE)


def load_svg_text(action_id: str) -> str:
    """Read the vendored Breeze SVG for `action_id` as UTF-8 text.

    Raises KeyError for an unknown id.
    """
    filename = ACTION_ICON_FILES[action_id]
    resource = (
        files("pgtp_editor") / "resources" / "icons" / "breeze" / filename
    )
    return resource.read_text(encoding="utf-8")


def recolor_svg(svg_text: str, hex_color: str) -> str:
    """Substitute a concrete fill color into a Breeze SVG.

    Replaces BOTH the ``currentColor`` token and the stylesheet
    ``color:#232629`` (case-insensitive) with `hex_color`, so QtSvg always has
    a literal fill regardless of whether it resolves ``currentColor``.
    """
    result = svg_text.replace("currentColor", hex_color)
    result = _BREEZE_COLOR_RE.sub(hex_color, result)
    return result


def themed_icon(action_id: str, color) -> "QIcon":
    """Build a QIcon for `action_id` recolored to `color`.

    `color` may be a QColor or a hex string. The recolored SVG is rendered over
    a transparent pixmap at 22px, with an additional 2x (44px) pixmap added for
    hi-dpi crispness.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    if isinstance(color, QColor):
        hex_color = color.name()
    else:
        hex_color = QColor(color).name()

    svg_text = recolor_svg(load_svg_text(action_id), hex_color)
    renderer = QSvgRenderer(bytearray(svg_text, encoding="utf-8"))

    icon = QIcon()
    for size in (22, 44):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            renderer.render(painter)
        finally:
            painter.end()
        icon.addPixmap(pixmap)
    return icon
