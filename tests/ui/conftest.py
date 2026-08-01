"""Shared fixtures for tests/ui/.

Autouse app-style/palette reset: BUG-004 made MainWindow's theme restore
(``_restore_theme``) unconditional -- every ``MainWindow()`` construction now
explicitly sets the QApplication's style to "Fusion" and applies a real
light/dark palette (``pgtp_editor.ui.theme.apply_theme``), even in tests that
never touch theming at all. QApplication is a process-wide singleton shared
across the whole pytest session, so that mutation would otherwise leak
forward into whatever test constructs a widget next -- confirmed to break
``test_menus.py``'s menu-bar assertions, since Fusion renders (and can
overflow) the menu bar differently than the native offscreen-platform style
those tests were written against. Reset unconditionally after every test in
this package so no test's app-style/palette mutation, from theming or
otherwise, can leak into another.
"""
import pytest
from PySide6.QtGui import QPalette


@pytest.fixture(autouse=True)
def _reset_app_style_and_palette(qapp):
    original_style = qapp.style().objectName()
    original_palette = QPalette(qapp.palette())
    # The dark theme also sets an app-global stylesheet (BUG-010's
    # QMenu::indicator QSS) -- restore it too, or a dark-theme test would
    # leak menu styling into every later widget test.
    original_stylesheet = qapp.styleSheet()
    try:
        yield
    finally:
        qapp.setStyle(original_style)
        qapp.setPalette(original_palette)
        qapp.setStyleSheet(original_stylesheet)
