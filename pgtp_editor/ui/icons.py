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

The pure string helpers (``ACTION_ICON_FILES``, the catalog functions,
``load_svg_text``, ``recolor_svg``) are Qt-free; only ``themed_icon`` touches
Qt.

FQ-004 widened the vendored pack from the original seven SVGs to a curated
common-action subset, and added an *enumerable catalog* over it so the
Customize Toolbar icon picker can list, search and assign any of them. The
catalog is a directory scan of ``resources/icons/breeze/`` performed once,
lazily, on first use -- a checked-in manifest would be one more thing to keep
in sync with the folder.

Two id spaces meet here, deliberately:

* the seven **legacy action ids** (``open``, ``save``, ...), which name the
  default icon of the legacy toolbar commands, and
* **catalog icon ids**, which are simply the SVG filename stems
  (``document-save-as``). These are what a user-chosen assignment stores.

``load_svg_text``/``themed_icon`` accept either, legacy first.
"""
import re
from importlib.resources import files

# Toolbar command id -> vendored Breeze SVG filename.
#
# `"find": "edit-find.svg"` was RETIRED with the `find` legacy alias (FQ-016):
# Find lost its menu home when the Edit menu dissolved, so no command id can
# resolve to it any more and a dangling default would be dead weight. The file
# itself stays in `resources/icons/breeze/` and therefore in the picker's
# catalog under the icon id `edit-find`, assignable to any command.
ACTION_ICON_FILES: dict[str, str] = {
    "open": "document-open.svg",
    "save": "document-save.svg",
    "undo": "edit-undo.svg",
    "redo": "edit-redo.svg",
    "validate": "dialog-ok-apply.svg",
    "generate": "run-build.svg",
}

# Breeze's ColorScheme-Text default color, matched case-insensitively.
_BREEZE_COLOR_RE = re.compile(r"#232629", re.IGNORECASE)

# Lazily built once: [(icon_id, filename, human_name), ...] sorted by icon_id.
_CATALOG_CACHE: list[tuple[str, str, str]] | None = None


def _breeze_dir():
    return files("pgtp_editor") / "resources" / "icons" / "breeze"


def human_name_for(icon_id: str) -> str:
    """A Breeze filename stem as a readable label:
    ``document-save-as`` -> ``Document Save As``."""
    return " ".join(
        word.capitalize() for word in icon_id.replace("_", "-").split("-") if word
    )


def icon_catalog() -> list[tuple[str, str, str]]:
    """Every vendored Breeze icon as ``(icon_id, filename, human_name)``,
    sorted by icon_id.

    Built by scanning the vendored folder once and cached; Qt-free.
    """
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        entries = []
        for resource in _breeze_dir().iterdir():
            name = resource.name
            if not name.endswith(".svg"):
                continue
            icon_id = name[: -len(".svg")]
            entries.append((icon_id, name, human_name_for(icon_id)))
        _CATALOG_CACHE = sorted(entries)
    return list(_CATALOG_CACHE)


def catalog_ids() -> list[str]:
    """Just the icon ids of `icon_catalog()`, in the same order."""
    return [icon_id for icon_id, _filename, _label in icon_catalog()]


def catalog_filename(icon_id: str) -> str | None:
    """The vendored filename for a catalog icon id, or None if unknown."""
    for candidate, filename, _label in icon_catalog():
        if candidate == icon_id:
            return filename
    return None


def search_catalog(query: str) -> list[tuple[str, str, str]]:
    """Catalog entries matching `query`: every whitespace-separated term must
    appear (case-insensitively) in the icon id or its human name. An empty
    query matches everything."""
    terms = (query or "").lower().split()
    if not terms:
        return icon_catalog()
    return [
        entry
        for entry in icon_catalog()
        if all(
            term in entry[0].lower() or term in entry[2].lower() for term in terms
        )
    ]


def load_svg_text(action_id: str) -> str:
    """Read the vendored Breeze SVG for `action_id` as UTF-8 text.

    `action_id` may be a legacy action id (`ACTION_ICON_FILES`) or a catalog
    icon id (an SVG filename stem). Raises KeyError for an unknown id.
    """
    filename = ACTION_ICON_FILES.get(action_id) or catalog_filename(action_id)
    if filename is None:
        raise KeyError(action_id)
    resource = _breeze_dir() / filename
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
