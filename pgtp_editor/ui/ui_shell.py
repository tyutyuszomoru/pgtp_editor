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
"""The narrow contract a collaborator object gets instead of ``MainWindow``.

Why this exists
---------------
``main_window.py`` grew into a god object: every feature lane reached into every
other lane through ``self``, so nothing could be read, tested or moved in
isolation. The decomposition replaces that with **collaborator objects** — one
per lane, each a plain ``QObject`` that constructs headless — and each of them
receives a :class:`UiShell` rather than the window.

``UiShell`` is deliberately **a bundle of bound callables, not the window**. A
collaborator can therefore do exactly the handful of host-level things a lane
legitimately needs (say something in the status bar, run work off the GUI
thread, reveal a left-dock panel) and *nothing else*. What it cannot do is grow
a new dependency on some unrelated lane's widget, because there is no path from
the shell to one. Adding a capability means adding a field here — a visible,
reviewable act — instead of typing ``self._window.some_other_panel``.

The ``window`` rule (load-bearing)
----------------------------------
``window`` is a **DIALOG PARENT ONLY**. In a collaborator, ``shell.window`` may
appear in exactly one syntactic position: as the ``parent=`` (or positional
parent) argument of a Qt dialog constructor or a modal static, e.g. ::

    modals.QMessageBox.question(self._shell.window, "Title", "Text")
    dialog = CustomizeToolbarDialog(commands, ids, self._shell.window, icons)

It must **never** be dereferenced for anything else — no
``self._shell.window.center_stage``, no ``self._shell.window._current_project``,
no ``self._shell.window.statusBar()``. One attribute access through the window
re-creates the god object with extra steps, which is why
``tests/ui/test_collaborator_boundaries.py`` fails the build on a regex match
for it. Everything a lane actually needs is a *named field* below; if what you
need is missing, add a field and a host-side accessor rather than reaching
through ``window``.

Late binding
------------
Every callable field is a **bound method of the host**, not a captured target.
That matters most for :attr:`run_async`: the whole suite injects a synchronous
stand-in by assigning ``window._run_async = _sync_run`` *after* the window is
constructed. Had the shell captured ``window._run_async`` at construction time,
those injections would silently miss and the affected tests would either hang
or assert against never-delivered results. The host therefore hands over a
trampoline that reads ``self._run_async`` at CALL time, and collaborators must
store it as ``self._run_async = shell.run_async`` and call it — never unwrap it
into a local or a default argument at construction.

The same reasoning applies to :attr:`status`, :attr:`default_dir`,
:attr:`is_light_theme` and the panel-reveal callables: all resolve host state
when invoked, so a collaborator built early in ``__init__`` still sees the
finished window.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget

from pgtp_editor.ui.center_stage import CenterStage


@dataclass(frozen=True)
class UiShell:
    """Host services handed to a collaborator object.

    Frozen so a collaborator cannot repoint the host's seams behind its back;
    tests that need a different seam replace the *collaborator's* attribute
    (``controller._run_async = ...``) or build a shell of their own.
    """

    #: DIALOG PARENT ONLY — see the module docstring. Never dereference.
    window: QWidget

    #: The center tab stack (Raw XML / XSD / Manual / DDL / Caption / ...).
    stage: CenterStage

    #: Where every lane reports its rows. Since FQ-028 this is the ROUTER
    #: (`ui/audit_router.py::AuditRouter`), not a widget: the same
    #: `addItem`/`count`/`item`/`takeItem` surface, but the prefix now names a
    #: DESTINATION (left-dock Findings tab / bottom Results tab / Activity Log)
    #: instead of competing for room in one panel. No lane had to change.
    audit: object

    #: ``statusBar().showMessage`` — ``(text)`` or ``(text, timeout_ms)``.
    #: FQ-028: the bar no longer PAINTS this; it journals it in the Activity
    #: Log (`ui/status_bar.py::StaticStatusBar`). Call sites are unchanged.
    status: Callable[..., None]

    #: The window's persistence store (an injected temp ini under test).
    settings: QSettings

    #: ``ui/async_task.py::run_async``, reached through the host's trampoline
    #: so post-construction injection of a synchronous stand-in is honoured.
    #: Signature: ``(fn, on_result, on_error=None, **kwargs)``.
    run_async: Callable[..., None]

    #: Directory an Open/Save dialog should default to: the active §18.2 local
    #: project folder, or ``""`` for Qt's own last-used default.
    default_dir: Callable[[], str]

    #: Make a left-dock tab visible **and** focus it (the "reveal" gesture the
    #: coherence / DDL-objects / Contents tabs all use).
    reveal_left_panel: Callable[[QWidget], None]

    #: Visibility only, without stealing focus.
    set_left_panel_visible: Callable[[QWidget, bool], None]

    #: Show + check + focus the center-stage Raw XML tab.
    reveal_raw_xml: Callable[[], None]

    #: Whether the View ▸ Light Theme toggle is currently on.
    is_light_theme: Callable[[], bool]
