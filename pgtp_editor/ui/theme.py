"""Light/Dark theme support (Sub-project D, #9).

Kept Qt-light and testable: ``light_palette()`` is pure (builds and returns a
QPalette without touching any application state) and ``apply_theme`` is the only
function that mutates the running QApplication. Tests assert palette roles
rather than pixels.
"""
from PySide6.QtGui import QColor, QPalette


def light_palette() -> QPalette:
    """Build a detectably-light QPalette (white/near-white backgrounds, dark
    text). Pure: constructs and returns a fresh palette, mutating nothing."""
    palette = QPalette()
    window = QColor(0xF0, 0xF0, 0xF0)
    base = QColor(0xFF, 0xFF, 0xFF)
    text = QColor(0x1E, 0x1E, 0x1E)
    button = QColor(0xE8, 0xE8, 0xE8)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    return palette


def apply_theme(app, light: bool) -> None:
    """Apply the light palette when ``light`` is True, otherwise restore the
    style's default palette."""
    if light:
        app.setPalette(light_palette())
    else:
        app.setPalette(app.style().standardPalette())
