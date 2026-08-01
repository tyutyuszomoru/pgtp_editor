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


def apply_theme(app, light: bool) -> None:
    """Apply the light or dark theme -- both explicit, complete QPalettes
    under the Fusion style, which honors QPalette fully (many native styles,
    e.g. Windows's, largely ignore it -- see the docstrings above).

    Symmetric by construction (BUG-004 fix): there is no third "restore
    whatever the native/OS style renders" state. ``light`` True/False always
    applies ``light_palette()``/``dark_palette()`` respectively, so both
    states are equally real, tested, and platform-independent."""
    app.setStyle("Fusion")
    app.setPalette(light_palette() if light else dark_palette())
