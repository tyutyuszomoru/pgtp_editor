# tests/ui/_menu_helpers.py
"""Shared helpers for asserting on QMenu/QMenuBar contents in tests.
Not a test module itself — pytest only collects test_*.py files."""

from PySide6.QtWidgets import QMenu


def action_labels(menu):
    return [action.text() if not action.isSeparator() else "―" for action in menu.actions()]


def _top_level_menus(window):
    # The menu bar owns an internal, EMPTY-TITLED overflow/"extension" QMenu
    # (the chevron shown when the bar is too narrow) that findChildren picks
    # up as a phantom entry. Under the native offscreen style it only existed
    # after show(); under Fusion (applied by every MainWindow() since the
    # BUG-004 theme rework) it exists immediately, so filter it out by its
    # empty title — real top-level menus always have one. (Enumerating via
    # menu_bar.actions()/action.menu() instead looks cleaner but trips a
    # PySide6/shiboken ownership bug: GC of the transient QAction wrappers
    # deletes the underlying C++ QMenus.)
    menu_bar = window.menuBar()
    return [
        menu
        for menu in menu_bar.findChildren(QMenu)
        if menu.parent() is menu_bar and menu.title()
    ]


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
