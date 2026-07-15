"""XmlEditor light/dark theming: the editor swaps its gutter, current-line,
highlight and syntax colors between a dark set (default) and a light set, and
does so automatically when the application palette flips."""
from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor, QPalette

from pgtp_editor.ui.theme import light_palette
from pgtp_editor.ui.xml_editor import XmlEditor


def test_editor_defaults_to_dark_colors(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    assert editor._gutter_bg_color == QColor("#2b2b2b")
    assert editor._gutter_fg_color == QColor("#858585")
    assert editor._current_line_color == QColor("#2d2d30")
    assert editor._highlighter._tag_format.foreground().color() == QColor("#569cd6")


def test_apply_theme_colors_light_then_dark(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)

    editor.apply_theme_colors(True)
    assert editor._gutter_bg_color == QColor("#f0f0f0")
    assert editor._gutter_fg_color == QColor("#888888")
    assert editor._current_line_color == QColor("#eef1f7")
    assert editor._highlighter._tag_format.foreground().color() == QColor("#0000ff")

    editor.apply_theme_colors(False)
    assert editor._gutter_bg_color == QColor("#2b2b2b")
    assert editor._current_line_color == QColor("#2d2d30")
    assert editor._highlighter._tag_format.foreground().color() == QColor("#569cd6")


def test_palette_change_to_light_flips_editor(qtbot):
    """Setting a light palette on the widget and delivering an
    ApplicationPaletteChange makes the editor adopt the light color set."""
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPalette(light_palette())
    editor.changeEvent(QEvent(QEvent.Type.ApplicationPaletteChange))
    assert editor._gutter_bg_color == QColor("#f0f0f0")
    assert editor._highlighter._tag_format.foreground().color() == QColor("#0000ff")


def test_palette_change_to_dark_keeps_dark(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
    editor.setPalette(dark)
    editor.changeEvent(QEvent(QEvent.Type.ApplicationPaletteChange))
    assert editor._gutter_bg_color == QColor("#2b2b2b")
    assert editor._highlighter._tag_format.foreground().color() == QColor("#569cd6")
