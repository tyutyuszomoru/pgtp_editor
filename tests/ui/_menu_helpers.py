# tests/ui/_menu_helpers.py
"""Shared helpers for asserting on QMenu/QMenuBar contents in tests.
Not a test module itself — pytest only collects test_*.py files."""

from PySide6.QtWidgets import QMenu


def action_labels(menu):
    return [action.text() if not action.isSeparator() else "―" for action in menu.actions()]


def find_top_menu(window, title):
    menu_bar = window.menuBar()
    for menu in menu_bar.findChildren(QMenu):
        if menu.parent() is menu_bar and menu.title() == title:
            return menu
    return None


def all_top_level_menu_titles(window):
    menu_bar = window.menuBar()
    return [menu.title() for menu in menu_bar.findChildren(QMenu) if menu.parent() is menu_bar]


def find_action(menu, text):
    for action in menu.actions():
        if action.text() == text:
            return action
    return None
