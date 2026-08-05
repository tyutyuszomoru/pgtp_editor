"""XmlEditor light/dark theming: the editor swaps its gutter, current-line,
highlight and syntax colors between a dark set (default) and a light set, and
does so automatically when the application palette flips."""
import shiboken6
from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor, QPalette

from pgtp_editor.ui.theme import apply_theme, light_palette
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


def test_app_wide_apply_theme_flips_editor_both_ways(qtbot, qapp):
    """BUG-010 integration: the real apply_theme() path (Fusion + palette +,
    in dark mode, the app-global QDarkStyleSheet QSS) still drives XmlEditor's
    palette-keyed changeEvent -- the QSS must not break the editor's
    Base-lightness detection in either direction. Uses genuine Qt event
    delivery (app.setPalette/setStyleSheet), not a hand-built QEvent."""
    editor = XmlEditor()
    qtbot.addWidget(editor)

    apply_theme(qapp, True)
    qapp.processEvents()
    assert editor._gutter_bg_color == QColor("#f0f0f0")
    assert editor._highlighter._tag_format.foreground().color() == QColor("#0000ff")

    apply_theme(qapp, False)
    qapp.processEvents()
    assert editor._gutter_bg_color == QColor("#2b2b2b")
    assert editor._highlighter._tag_format.foreground().color() == QColor("#569cd6")


def test_palette_change_to_dark_keeps_dark(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
    editor.setPalette(dark)
    editor.changeEvent(QEvent(QEvent.Type.ApplicationPaletteChange))
    assert editor._gutter_bg_color == QColor("#2b2b2b")
    assert editor._highlighter._tag_format.foreground().color() == QColor("#569cd6")


def test_deferred_theme_rehighlight_does_not_fire_on_deleted_editor(qtbot, qapp):
    """BUG-014: apply_theme_colors defers step-2 rehighlight to the next
    event-loop turn. The kickoff timer must be PARENTED to the editor so a
    widget destroyed between the toggle and that turn cancels the pending
    tick -- an unparented QTimer.singleShot fired _rehighlight_for_theme on
    an already-deleted C++ XmlEditor (RuntimeError: Internal C++ object
    already deleted), caught by pytest-qt's event-loop hook (which is exactly
    how this surfaced as the Find-All tests' failures). With the parented
    timer this test's processEvents raises nothing."""
    editor = XmlEditor()
    editor.setPlainText("<a b='c'/>\n<d/>\n")
    # The kickoff timer is a child of the editor, so ~QObject cancels it.
    assert editor._theme_kickoff_timer.parent() is editor

    editor.apply_theme_colors(True)  # schedules the deferred step-2 kickoff
    assert editor._theme_rehighlight_pending is True

    # Force-delete the C++ object immediately, before the queued 0ms tick can
    # run -- the deterministic analog of a parent widget being torn down
    # mid-toggle. A parented timer dies with it; an unparented singleShot
    # would survive and fire _rehighlight_for_theme on the dead editor.
    shiboken6.delete(editor)
    assert not shiboken6.isValid(editor)
    qapp.processEvents()  # bug: RuntimeError in the loop -> pytest-qt fails
    qapp.processEvents()
