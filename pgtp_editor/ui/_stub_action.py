# pgtp_editor/ui/_stub_action.py
"""Shared helper: a menu action wired to a not-yet-implemented callback.

Used by both ProjectTreePanel (context menus) and MainWindow (menu bar)
so the wiring pattern lives in exactly one place.
"""


def add_stub_action(menu, label, callback):
    action = menu.addAction(label)
    action.triggered.connect(lambda checked=False, l=label: callback(l))
    return action
