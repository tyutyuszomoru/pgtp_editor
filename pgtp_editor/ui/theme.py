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

"""Light/Dark theme support (Sub-project D, #9).

Kept Qt-light and testable: ``light_palette()`` is pure (builds and returns a
QPalette without touching any application state) and ``apply_theme`` is the only
function that mutates the running QApplication. Tests assert palette roles
rather than pixels.
"""
from PySide6.QtGui import QColor, QPalette


def light_palette() -> QPalette:
    """Build a COMPLETE, detectably-light QPalette (white/near-white
    backgrounds, dark text, navy links). Pure: constructs and returns a fresh
    palette, mutating nothing.

    Every role the app actually surfaces is set explicitly -- including the
    ``Link`` role (navy) so About-box hyperlinks read on white instead of
    inheriting the dark-theme cyan, and the Disabled color group so greyed-out
    controls stay legible under the Fusion style."""
    palette = QPalette()
    role = QPalette.ColorRole

    text = QColor(0x1E, 0x1E, 0x1E)
    palette.setColor(role.Window, QColor(0xF0, 0xF0, 0xF0))
    palette.setColor(role.WindowText, text)
    palette.setColor(role.Base, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(role.AlternateBase, QColor(0xE9, 0xE9, 0xE9))
    palette.setColor(role.ToolTipBase, QColor(0xFF, 0xFF, 0xDC))
    palette.setColor(role.ToolTipText, text)
    palette.setColor(role.Text, text)
    palette.setColor(role.Button, QColor(0xE8, 0xE8, 0xE8))
    palette.setColor(role.ButtonText, text)
    palette.setColor(role.BrightText, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(role.Highlight, QColor(0x38, 0x74, 0xF2))
    palette.setColor(role.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(role.Link, QColor(0x0B, 0x3D, 0x91))
    palette.setColor(role.LinkVisited, QColor(0x55, 0x1A, 0x8B))
    palette.setColor(role.PlaceholderText, QColor(0x8A, 0x8A, 0x8A))

    disabled = QColor(0xA0, 0xA0, 0xA0)
    group = QPalette.ColorGroup.Disabled
    palette.setColor(group, role.Text, disabled)
    palette.setColor(group, role.WindowText, disabled)
    palette.setColor(group, role.ButtonText, disabled)
    return palette


def dark_palette() -> QPalette:
    """Build a COMPLETE, detectably-dark QPalette (dark backgrounds, light
    text, light-cyan links) -- the explicit, tested "Light Theme off" state
    (BUG-004). Previously "off" simply restored whatever the native/OS style
    happened to render at startup, which only looked dark on the one platform
    (Windows) the toggle was originally built and tested against; on any
    other native-style baseline, toggling the light theme off produced no
    reliably-dark result at all. Mirrors ``light_palette()``'s structure and
    role coverage so both states are equally complete and tested."""
    palette = QPalette()
    role = QPalette.ColorRole

    text = QColor(0xE0, 0xE0, 0xE0)
    palette.setColor(role.Window, QColor(0x2B, 0x2B, 0x2B))
    palette.setColor(role.WindowText, text)
    palette.setColor(role.Base, QColor(0x1E, 0x1E, 0x1E))
    palette.setColor(role.AlternateBase, QColor(0x2B, 0x2B, 0x2B))
    palette.setColor(role.ToolTipBase, QColor(0x3A, 0x3A, 0x3A))
    palette.setColor(role.ToolTipText, text)
    palette.setColor(role.Text, text)
    palette.setColor(role.Button, QColor(0x3A, 0x3A, 0x3A))
    palette.setColor(role.ButtonText, text)
    palette.setColor(role.BrightText, QColor(0xFF, 0x5C, 0x5C))
    palette.setColor(role.Highlight, QColor(0x38, 0x74, 0xF2))
    palette.setColor(role.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    palette.setColor(role.Link, QColor(0x6C, 0xB6, 0xFF))
    palette.setColor(role.LinkVisited, QColor(0xB1, 0x8C, 0xFF))
    palette.setColor(role.PlaceholderText, QColor(0x8A, 0x8A, 0x8A))

    disabled = QColor(0x6E, 0x6E, 0x6E)
    group = QPalette.ColorGroup.Disabled
    palette.setColor(group, role.Text, disabled)
    palette.setColor(group, role.WindowText, disabled)
    palette.setColor(group, role.ButtonText, disabled)
    return palette


# Cached QDarkStyleSheet text, one per theme (BUG-010; extended for the light
# QSS below). Loaded lazily -- qdarkstyle warns if loaded before a
# QApplication exists, and apply_theme always runs with one.
_qss_cache: dict[bool, str] = {}


def _qdarkstyle_stylesheet(light: bool) -> str:
    """The QDarkStyleSheet QSS (github.com/ColinDuquesnoy/QDarkStyleSheet, the
    `qdarkstyle` package) for the given theme -- adopted for BUG-010: Fusion +
    palette alone left checkable menu indicators outlined near-black on the
    dark menu background (Fusion derives the indicator frame from darkened
    Window/Button roles). Rather than hand-tuning per-widget QSS, the
    maintained stylesheet styles menus (QMenu::indicator included) and every
    other widget consistently -- for BOTH themes: qdarkstyle ships a
    `qdarkstyle.light.palette.LightPalette` alongside its `DarkPalette`, so
    the light theme gets the same professional chrome the dark theme always
    had, at no new dependency cost."""
    if light not in _qss_cache:
        import qdarkstyle
        from qdarkstyle.dark.palette import DarkPalette
        from qdarkstyle.light.palette import LightPalette

        _qss_cache[light] = qdarkstyle.load_stylesheet(
            qt_api="pyside6", palette=LightPalette if light else DarkPalette
        )
    return _qss_cache[light]


def apply_theme(app, light: bool) -> None:
    """Apply the light or dark theme: Fusion + ``light_palette()``/
    ``dark_palette()`` + the matching QDarkStyleSheet QSS (BUG-010, extended
    to cover light too).

    Symmetric by construction (BUG-004 fix): there is no third "restore
    whatever the native/OS style renders" state; both states are real,
    tested, and platform-independent, and now both carry a stylesheet.
    ``light_palette()``/``dark_palette()`` are still applied under the QSS
    because palette-reading custom widgets (XmlEditor's
    ``apply_theme_colors`` keys off its palette's Base lightness) and any
    non-stylesheet-covered rendering must agree with the stylesheet's look."""
    app.setStyle("Fusion")
    app.setPalette(light_palette() if light else dark_palette())
    app.setStyleSheet(_qdarkstyle_stylesheet(light))
