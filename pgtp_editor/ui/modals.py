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
"""The one module every collaborator reaches modal Qt through.

Why this module exists
----------------------
``CLAUDE.md`` states the hard rule: *never let a test reach an un-patched modal
Qt call* (``QDialog.exec``, ``QMessageBox.*``, ``QFileDialog.*``) — they must be
monkeypatched. In practice tests patch those calls **through the namespace of
the module that calls them**, e.g. historically
``patch("pgtp_editor.ui.main_window.QMessageBox.question")``.

That couples every patch target to the *current physical location* of the code.
As ``main_window.py`` is decomposed into collaborator objects, a call site that
moves from ``main_window`` to some new module silently invalidates its patch:

* class-attribute patches such as
  ``patch("pgtp_editor.ui.main_window.QMessageBox.question")`` keep **passing**
  while patching a class that the moved code no longer reaches through that
  module — i.e. testing nothing — and then fail *en masse* the moment
  ``main_window.py`` drops its now-unused import. In between, an offscreen run
  can reach a **real** modal dialog, which is exactly what the rule forbids.
* whole-object patches such as
  ``patch("pgtp_editor.ui.main_window.QMessageBox", _FakeBox)`` break outright.

Routing every modal through this module makes the patch target **stable**: it
names the modal surface, not whoever happens to call it. Code moving between
collaborators no longer moves any test's patch target.

How to use it
-------------
Always import the *module* and use attribute access::

    from pgtp_editor.ui import modals

    modals.QMessageBox.question(self, "Title", "Text")
    path, _filter = modals.QFileDialog.getOpenFileName(self, "Open", "", "*.x")

Never ``from pgtp_editor.ui.modals import QMessageBox``: that rebinds the class
into the caller's namespace, so a whole-object patch of
``pgtp_editor.ui.modals.QMessageBox`` would no longer be seen. Attribute access
is what makes **both** whole-object and method-level patches bite.

This module is a pure re-export — no wrappers, no defaults, no behavior. It
holds exactly the modal entry points actually in use, so it cannot drift from Qt
(``tests/ui/test_modals.py`` asserts object identity with PySide6) or accumulate
exports nothing calls.
"""

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

__all__ = [
    "QDesktopServices",
    "QFileDialog",
    "QInputDialog",
    "QMessageBox",
]
