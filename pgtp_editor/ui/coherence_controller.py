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
"""The Database/XML Coherence lane (spec §17, FQ-003) and the "create from a DB
table" gestures that hang off it (SP3).

What it owns
------------
* the **Database ▸ "Database/XML Coherence"** checkable toggle — handed over by
  the host after the Database menu is built (:meth:`set_toggle_action`), because
  the rest of that menu belongs to the DDL lanes;
* the **merged coherence view**: running the check, populating
  ``CoherencePanel``, revealing its left-dock tab, and refreshing it against the
  cached schema after a reparse;
* the **cached schema + connection summary** of the last successful run
  (:attr:`last_schema` / :attr:`last_summary`) — what makes a reparse refresh
  and a "create page/detail/lookup" free of a second round trip;
* the **rename-in-XML** gesture and the **name jump** into Find-All;
* **create page / detail / lookup from a DB table** (SP3), including the
  duplicate-page prompt, the ``fileName`` de-duplication and the ``</Pages>``
  splice.

It parses the BUFFER, not the project model
-------------------------------------------
Every path here reads ``shell.stage.xml_editor``'s text and parses that, never
the host's last-parsed ``ProjectModel``. That is deliberate and load-bearing:
the buffer may hold unsaved edits (in particular the rename this lane just
made), and the §17 reconcile loop only converges if the re-run sees them. Do not
"improve" this into a project-model read — :meth:`refresh_if_open` is the one
entry point that takes a parsed project, and it is handed one by the caller (the
host's reparse) rather than fetching it.

Two spellings of one kind (BUG-032 facet A)
-------------------------------------------
``kind`` is the host-facing vocabulary the retired ``DbCheckPanel`` established
and §17 carried over: a relation is ``"table"``. ``coherence_panel.py``
normalizes ``"relation" -> "table"`` on the way out (its ``_HOST_KIND`` map), and
:meth:`on_jump_requested` accepts **both** spellings anyway, so a future caller
emitting the internal node kind cannot silently reintroduce a ``fieldName=``
search for a table name. Both halves of that fix are needed; keep both.

The replaceable seams are ATTRIBUTES
------------------------------------
:attr:`fetch_schema`, :attr:`prompt_rename` and :attr:`confirm_duplicate_page`
are plain instance attributes, not methods, because the suite assigns over them
(a live DB connection and two modals respectively). :attr:`last_schema` and
:attr:`last_summary` are plain writable attributes for the same reason and one
sharper one: the create/rename tests *write* ``last_schema`` and then invoke the
handler that reads it, so the write must land on the very object the handler
dereferences. A read-only property, or routing the value through a signal, would
leave those tests green while testing nothing.

Shape
-----
A ``QObject`` following ``ui/xsd_controller.py``: it takes a
:class:`~pgtp_editor.ui.ui_shell.UiShell`, constructs headless, and never
dereferences ``shell.window`` (it appears only as a dialog parent for the
``ui/modals`` statics). What the shell cannot reach is injected as callables,
never by importing another collaborator:

* ``find_all`` — the Find-All machinery still lives on the host and moves to
  ``FindValidateController`` in a later wave; injecting the host's current
  method means only the host's one wiring line changes then.
* ``prompt_missing_connection`` — the shared "no connection configured" reroute
  (BUG-024) belongs to the DDL-explorer area and moves with it.
* ``show_left_dock`` / ``show_audit_dock`` / ``panel_visible`` — three dock/tab
  gestures ``UiShell`` has no field for. Revealing the coherence tab must also
  un-hide the left dock, listing occurrences must un-hide the Audit dock, and
  the reparse refresh is gated on the tab actually being visible.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QSignalBlocker
from PySide6.QtWidgets import QApplication

from pgtp_editor import debuglog
from pgtp_editor.db.coherence import build_coherence_tree
from pgtp_editor.db.config import seed_params
from pgtp_editor.db.introspect import fetch_schema as db_fetch_schema
from pgtp_editor.db.rename import rename_field, rename_table
from pgtp_editor.generation import from_table as table_gen
from pgtp_editor.model.parser import PgtpParseError, load_project_from_text
from pgtp_editor.ui import modals
from pgtp_editor.ui.ui_shell import UiShell

_log = logging.getLogger(__name__)


class CoherenceController(QObject):
    """Owns the §17/FQ-003 coherence view, its cached schema and the SP3
    create-from-table gestures."""

    def __init__(
        self,
        shell: UiShell,
        panel,
        parent: QObject | None = None,
        *,
        find_all: Callable[..., None],
        prompt_missing_connection: Callable[[], None],
        show_left_dock: Callable[[], None],
        show_audit_dock: Callable[[], None],
        panel_visible: Callable[[], bool],
    ):
        super().__init__(parent)
        self._shell = shell
        self._settings = shell.settings
        #: The merged Database/XML Coherence view (`ui/coherence_panel.py`).
        self._panel = panel
        self._find_all = find_all
        self._prompt_missing_connection = prompt_missing_connection
        self._show_left_dock = show_left_dock
        self._show_audit_dock = show_audit_dock
        self._panel_visible = panel_visible

        #: The Database-menu toggle, handed over by `set_toggle_action` once the
        #: Database menu is built. None until then.
        self._toggle_action = None

        #: Cached schema + connection summary from the last successful run: a
        #: reparse refreshes the panel without re-querying, and a right-click
        #: "create from table" reuses the column metadata without re-querying.
        #: PLAIN WRITABLE ATTRIBUTES -- see the module docstring.
        self.last_schema = None
        self.last_summary = None

        #: Replaceable seams -- ATTRIBUTES, not methods. See the module
        #: docstring: the suite assigns over them to keep a live DB connection
        #: and two modals out of the test run.
        self.fetch_schema = self._fetch_schema
        self.prompt_rename = self._prompt_rename
        self.confirm_duplicate_page = self._confirm_duplicate_page

    # -- read-only surface ---------------------------------------------------

    @property
    def toggle_action(self):
        """The Database ▸ "Database/XML Coherence" checkable ``QAction``."""
        return self._toggle_action

    @property
    def panel(self):
        """The ``CoherencePanel`` this lane populates."""
        return self._panel

    # -- construction --------------------------------------------------------

    def set_toggle_action(self, action) -> None:
        """Adopt the Database-menu toggle and wire it to this lane.

        The host builds the Database menu (most of it belongs to the DDL lanes)
        and hands this one action over, mirroring how ``ToolbarController.build``
        receives ``addToolBar`` instead of reaching for the window.
        """
        self._toggle_action = action
        action.toggled.connect(self.on_coherence_toggled)

    # -- seams ---------------------------------------------------------------

    def _fetch_schema(self, params):
        """Introspect the database. Reached through the replaceable
        `fetch_schema` attribute so tests can return a canned `DatabaseSchema`
        with no live connection (or psycopg) present."""
        return db_fetch_schema(params)

    def _prompt_rename(self, old):
        """Ask for a new name (modal QInputDialog). Reached through the
        replaceable `prompt_rename` attribute so tests bypass the modal.
        Returns the new name, or None if cancelled."""
        text, ok = modals.QInputDialog.getText(
            # The ONE sanctioned use of shell.window: a dialog parent.
            self._shell.window,
            "Rename in XML",
            f"New name for '{old}' — replaces every matching "
            "fieldName/tableName occurrence in the file:",
            text=old,
        )
        return text if ok else None

    def _confirm_duplicate_page(self, table_name):
        """Warn that a page for `table_name` already exists; return True to
        proceed (with a de-duplicated fileName) or False to cancel. Reached
        through the replaceable `confirm_duplicate_page` attribute so tests
        bypass the modal."""
        choice = modals.QMessageBox.question(
            self._shell.window,
            "Page Already Exists",
            f"A page for '{table_name}' already exists in this project.\n\n"
            "Create another one anyway (with a de-duplicated fileName)?",
            modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
            modals.QMessageBox.StandardButton.No,
        )
        return choice == modals.QMessageBox.StandardButton.Yes

    # -- the coherence view --------------------------------------------------

    def _reveal_panel(self) -> None:
        self._show_left_dock()
        self._shell.reveal_left_panel(self._panel)

    def _populate(self, schema, project, summary) -> None:
        """Build the coherence tree for `project` against `schema` and show it.
        Shared by the live run (`run_check`) and the cached-schema refresh
        (`refresh_if_open`)."""
        self._panel.set_result(build_coherence_tree(project, schema), summary)

    def _uncheck_toggle(self) -> None:
        """Un-check the Database-menu toggle after a failed/refused run, so the
        menu never claims a view is open that is not (the BUG-007 lesson)."""
        if self._toggle_action is not None and self._toggle_action.isChecked():
            self._toggle_action.setChecked(False)

    def on_coherence_toggled(self, checked) -> None:
        """Database ▸ "Database/XML Coherence" (checkable, no shortcut).

        On → fetch the schema and reveal the tab; on any failure the action
        un-checks itself so the menu never lies about what is on screen.
        Off → just hide the tab (the cached schema survives, so toggling back
        on is a fresh, honest re-run rather than a stale redisplay)."""
        if checked:
            self.run_check()
        else:
            self._shell.set_left_panel_visible(self._panel, False)

    def run_check(self) -> None:
        # Compare against a model parsed from the CURRENT buffer, not the
        # host's last-parsed project -- so renames (and any manual edit) made
        # since the last load are reflected and the reconcile loop actually
        # resolves. Falls back to no-op with a status message when the buffer is
        # empty or not valid XML.
        text = self._shell.stage.xml_editor.toPlainText()
        if not text.strip():
            self._shell.status("Open a project first.", 5000)
            self._uncheck_toggle()
            return
        try:
            project = load_project_from_text(text, source_description="<editor>")
        except PgtpParseError as exc:
            self._shell.status(f"Database check needs valid XML: {exc}", 8000)
            self._uncheck_toggle()
            return
        params = seed_params(project.tree, self._settings)
        if not params.host:
            self._uncheck_toggle()
            self._prompt_missing_connection()
            return
        # The schema fetch opens a DB connection -- move ONLY that off the GUI
        # thread. Everything above (buffer parse, seed, guards) is fast and stays
        # here; the compare + panel population happen in on_result, back on the
        # GUI thread, so they may safely touch widgets.
        self._shell.status("Checking database…")
        _log.info("db: coherence check started %s", debuglog.redacted(params))

        def on_result(schema):
            summary = f"{params.user}@{params.host}:{params.port}/{params.database}"
            self.last_schema = schema
            self.last_summary = summary
            self._populate(schema, project, summary)
            self._reveal_panel()
            # Sync the menu's checkmark WITHOUT re-entering the toggle slot:
            # a plain setChecked here would fire toggled(True) and start a
            # second fetch (the run can also be entered from the rename
            # re-run, not only from the menu).
            if self._toggle_action is not None:
                blocker = QSignalBlocker(self._toggle_action)
                self._toggle_action.setChecked(True)
                del blocker
            self._shell.status("Database/XML Coherence complete.", 3000)
            _log.info("db: coherence check finished")

        def on_error(exc):
            _log.info("db: coherence check failed %s", exc)
            self._shell.status(f"Database check failed: {exc}", 8000)
            self._uncheck_toggle()

        self._shell.run_async(
            lambda: self.fetch_schema(params),
            on_result=on_result,
            on_error=on_error,
        )

    def refresh_if_open(self, project) -> None:
        """After a reparse, rebuild the coherence tree against the CACHED
        schema (no re-query) so the open view reflects the edited XML. No-op
        unless the coherence tab is visible and a run already happened.
        `project` is the freshly parsed model handed over by the host's
        reparse -- the one path in this lane that is given a project rather
        than parsing the buffer itself."""
        if not self._panel_visible() or self.last_schema is None:
            return
        self._populate(self.last_schema, project, self.last_summary or "")
        self._shell.status(
            "Database/XML Coherence refreshed against the last database snapshot.",
            4000,
        )

    def teardown_for_project_close(self) -> None:
        """Coherence results are project-tied (BUG-011, §17): hide the tab,
        clear the panel and drop the cached schema/summary so a later reparse
        or rename re-run can't act on the closed project's stale state.

        Called only on the host's committed-close path -- a cancelled close must
        leave the still-open project's tab alone, and a revert keeps the project
        loaded so it does not tear down either.
        """
        self._shell.set_left_panel_visible(self._panel, False)
        self._panel.clear()
        if self._toggle_action is not None:
            self._toggle_action.setChecked(False)
        self.last_schema = None
        self.last_summary = None

    # -- rename / jump -------------------------------------------------------

    def on_rename_requested(self, kind, old) -> None:
        new = self.prompt_rename(old)
        if not new or new == old:
            return
        editor = self._shell.stage.xml_editor
        current = editor.toPlainText()
        if kind == "table":
            updated, count = rename_table(current, old, new)
        else:
            updated, count = rename_field(current, old, new)
        _log.info("db: rename %s -> %s (%d replacements)", old, new, count)
        # Write through the buffer so the change marks the document dirty and
        # pushes a snapshot (the editor's textChanged handler does both).
        editor.setPlainText(updated)
        self._shell.status(
            f"Renamed {kind} '{old}' → '{new}' ({count} occurrence(s)).", 5000
        )
        # Re-run the coherence check so the rename's effect shows immediately.
        # Gated on a prior run: without a cached schema there is nothing the
        # user asked to keep in sync (§17).
        if self.last_schema is not None:
            self.run_check()

    def on_jump_requested(self, kind, name) -> None:
        """Double-click on a DB tree node: list EVERY occurrence of the node's
        attribute token in the Find-all results panel, select the first one, and
        seed the Find bar so Find Next / F3 steps through them (reusing the
        existing Find All + Find Next machinery rather than a one-shot jump)."""
        # `kind` is the host-facing vocabulary DbCheckPanel established and §17
        # carried over: a relation is "table". `CoherencePanel` normalizes
        # "relation" -> "table" on the way out (BUG-032 facet A), and
        # "relation" is accepted here as well so a future caller emitting the
        # internal node kind cannot silently reintroduce a fieldName= search
        # for a table name.
        is_table = kind in ("table", "relation")
        token = f'tableName="{name}"' if is_table else f'fieldName="{name}"'
        stage = self._shell.stage
        editor = stage.xml_editor
        if token not in editor.toPlainText():
            # A genuine miss is now meaningful (it is what an "unreferenced"
            # relation looks like), so say what was searched and what that
            # means instead of the bare "not found" that the token bug made
            # indistinguishable from a malfunction.
            self._shell.status(
                f"No {token} in the buffer — the XML does not reference {name}.", 5000
            )
            return
        stage.setCurrentIndex(stage.raw_xml_tab_index)
        # Clear any selection so the first Find Next lands on the first match.
        cursor = editor.textCursor()
        cursor.setPosition(0)
        editor.setTextCursor(cursor)
        # Seed the Find bar so Find Next / F3 step through occurrences of the
        # token. show_find()'s prefill is a no-op now that the selection is clear.
        bar = stage.find_replace_bar
        bar.set_find_text(token)
        bar.show_find()
        # List every occurrence in the bottom panel (reuses Find All), and
        # reveal the panel in case a prior DB check left it hidden.
        self._find_all(token)
        self._show_audit_dock()
        # Select the first occurrence; F3 (Find Next) continues from there.
        bar.find_next()
        editor.setFocus()

    # -- Create page/detail/lookup from a DB table (SP3) ---------------------

    def on_create_requested(self, what, name) -> None:
        """Right-click on a relation node in the coherence view's Tables and
        Views branch: synthesize a page (insert into the buffer) or a
        detail/lookup (copy to clipboard)."""
        schema = self.last_schema
        if schema is None or schema.table(name) is None:
            self._shell.status(
                f"No schema for '{name}' — run Database/XML Coherence first.", 5000
            )
            return
        try:
            if what == "page":
                self._create_page_from_table(schema, name)
            elif what == "detail":
                element = table_gen.build_detail(schema, name)
                self._copy_fragment_to_clipboard(element, "Detail", name)
            elif what == "lookup":
                element = table_gen.build_lookup(schema, name)
                self._copy_fragment_to_clipboard(element, "Lookup", name)
        except table_gen.GenerationError as exc:
            self._shell.status(f"Could not create {what}: {exc}", 8000)

    def _copy_fragment_to_clipboard(self, element, label, name) -> None:
        text = table_gen.serialize(element, indent=0)
        QApplication.clipboard().setText(text)
        self._shell.status(
            f"{label} for '{name}' copied to clipboard — paste it into the "
            "target page.",
            6000,
        )

    def _create_page_from_table(self, schema, name) -> None:
        element = table_gen.build_page(schema, name)
        stage = self._shell.stage
        buffer = stage.xml_editor.toPlainText()

        file_name = element.get("fileName")
        if f'tableName="{name}"' in buffer or f'fileName="{file_name}"' in buffer:
            if not self.confirm_duplicate_page(name):
                self._shell.status("Page creation cancelled.", 3000)
                return
            file_name = self._dedupe_file_name(buffer, file_name)
            element.set("fileName", file_name)

        updated, insert_line = self._insert_page_before_pages_close(buffer, element)
        if updated is None:
            self._shell.status(
                "Could not find </Pages> to insert the new page.", 8000
            )
            return
        stage.xml_editor.setPlainText(updated)
        stage.setCurrentIndex(stage.raw_xml_tab_index)
        stage.xml_editor.navigate_to_line(insert_line)
        stage.xml_editor.select_enclosing_block()
        self._shell.status(f"Page for '{name}' added.", 5000)

    @staticmethod
    def _dedupe_file_name(buffer, file_name):
        candidate = file_name
        suffix = 2
        while f'fileName="{candidate}"' in buffer:
            candidate = f"{file_name}_{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def _insert_page_before_pages_close(buffer, element):
        """Splice a serialized <Page> immediately before </Pages>, indented to
        match the existing <Page> depth. Returns (new_text, page_open_line) or
        (None, 0) if </Pages> is absent."""
        close_index = buffer.rfind("</Pages>")
        if close_index == -1:
            return None, 0
        line_start = buffer.rfind("\n", 0, close_index) + 1
        close_indent = buffer[line_start:close_index]
        indent_depth = close_indent.count("\t") + 1  # one level deeper than </Pages>
        fragment = table_gen.serialize(element, indent=indent_depth)
        new_text = buffer[:line_start] + fragment + "\n" + buffer[line_start:]
        page_open_line = buffer.count("\n", 0, line_start) + 1
        return new_text, page_open_line
