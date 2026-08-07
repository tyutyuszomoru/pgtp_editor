# tests/ui/_menu_helpers.py
"""Shared helpers for asserting on QMenu/QMenuBar contents in tests.
Not a test module itself — pytest only collects test_*.py files."""

from PySide6.QtWidgets import QMenu


def action_labels(menu):
    return [action.text() if not action.isSeparator() else "―" for action in menu.actions()]


def _menu_bars(window):
    """Both of the app's menu bars (FQ-016), window bar first.

    `find_top_menu`/`all_top_level_menu_titles` search across both on purpose:
    a menu MOVING between the two bars (as Bookmarks did) is not something every
    caller of these helpers should have to care about. Tests that specifically
    assert WHICH bar a menu is on use `window.menuBar()` /
    `window.editor_menu_bar` directly — see test_menus.py.
    """
    bars = [window.menuBar()]
    editor_bar = getattr(window, "editor_menu_bar", None)
    if editor_bar is not None:
        bars.append(editor_bar)
    return bars


def _menus_of(menu_bar):
    # The menu bar owns an internal, EMPTY-TITLED overflow/"extension" QMenu
    # (the chevron shown when the bar is too narrow) that findChildren picks
    # up as a phantom entry. Under the native offscreen style it only existed
    # after show(); under Fusion (applied by every MainWindow() since the
    # BUG-004 theme rework) it exists immediately, so filter it out by its
    # empty title — real top-level menus always have one. (Enumerating via
    # menu_bar.actions()/action.menu() instead looks cleaner but trips a
    # PySide6/shiboken ownership bug: GC of the transient QAction wrappers
    # deletes the underlying C++ QMenus.)
    return [
        menu
        for menu in menu_bar.findChildren(QMenu)
        if menu.parent() is menu_bar and menu.title()
    ]


def _top_level_menus(window):
    return [menu for bar in _menu_bars(window) for menu in _menus_of(bar)]


def window_menu_titles(window):
    """Top-level titles on the WINDOW menu bar only."""
    return [menu.title() for menu in _menus_of(window.menuBar())]


def editor_menu_titles(window):
    """Top-level titles on the Editor menu bar only (FQ-016)."""
    return [menu.title() for menu in _menus_of(window.editor_menu_bar)]


def find_top_menu(window, title):
    for menu in _top_level_menus(window):
        if menu.title() == title:
            return menu
    return None


def all_top_level_menu_titles(window):
    return [menu.title() for menu in _top_level_menus(window)]


def find_action(menu, text):
    for action in menu.actions():
        if action.text() == text:
            return action
    return None
