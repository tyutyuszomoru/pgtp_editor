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


def apply_theme(app, light: bool, default_palette=None, default_style=None) -> None:
    """Apply the light theme when ``light`` is True, otherwise restore the
    ORIGINAL captured style + palette.

    The native Windows style largely ignores QPalette, so a light palette
    barely takes effect under it. Light mode therefore switches to the Fusion
    style (which honors the palette fully) before applying ``light_palette()``.

    Restoring (``light`` False) puts back the captured ``default_style`` and
    ``default_palette`` -- the app's real original (OS-dark) look -- rather
    than the style's generic ``standardPalette()``, which is only used as a
    fallback when no default palette was captured (e.g. legacy callers)."""
    if light:
        app.setStyle("Fusion")
        app.setPalette(light_palette())
    else:
        if default_style is not None:
            app.setStyle(default_style)
        app.setPalette(
            default_palette
            if default_palette is not None
            else app.style().standardPalette()
        )
