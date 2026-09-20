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
* **create page / detail / lookup from a DB table** (SP3), which since FQ-006
  opens each generated fragment as a **draft tab** in the center stage. It no
  longer splices a ``<Page>`` into the live buffer, no longer copies a
  ``<Detail>``/``<Lookup>`` to the clipboard, and no longer blocks on a
  duplicate-page modal or auto-renames a colliding ``fileName``: a collision is
  a non-blocking status-bar heads-up, because nothing reaches the real XML until
  the user pastes the draft in themselves.

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
:attr:`fetch_schema` and :attr:`prompt_rename` are plain instance attributes,
not methods, because the suite assigns over them (a live DB connection and a
modal respectively). :attr:`last_schema` and
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
* ``show_audit_dock`` / ``panel_visible`` — two dock/tab gestures ``UiShell``
  has no field for: listing occurrences must un-hide the Audit dock, and the
  reparse refresh is gated on the tab actually being visible.

  ``show_left_dock`` was a third, and is **gone** (BUG-260812023420): revealing
  a left-dock pane now un-hides the dock inside ``reveal_left_panel`` itself,
  so this controller no longer carries half of that gesture. Its counterpart
  ``set_left_panel_visible`` deliberately does *not* touch the dock — and note
  that **both production callers here pass ``False``** (``on_coherence_toggled``
  and ``teardown_for_project_close``). The ``True`` direction has no caller
  today; the seam is kept because without it *"make this tab available"* has no
  expression that is not also *"take the user there"*. ``refresh_if_open`` is
  NOT that caller — it reads ``panel_visible()`` and returns early, never
  touching visibility at all.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QSignalBlocker

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
        target_params: Callable[..., object] | None = None,
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
        #: BUG-034: "the target connection to use", selected by the host's ONE
        #: selector (`MainWindow.active_target_params`, via
        #: `_target_params_for_fetch`) -- with a §18.2 project open that is the
        #: project's own `ProjectSettings.target`, the store Project Settings
        #: displays. This lane used to call `seed_params` itself, so it could
        #: connect with app-level QSettings credentials while Project Settings
        #: showed something else entirely. Injected rather than duplicated;
        #: `None` (no host wired it) keeps the old `seed_params` behavior.
        self._target_params = target_params
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

        #: BUG-260812110307's twin in this lane. How many times the coherence
        #: view has been asked to run OR to close; `run_check` captures the
        #: value it bumped to and its `on_result` performs no visible act once
        #: the two disagree, so a close during an in-flight check WINS. Single
        #: instance, so a plain int rather than the per-role dict
        #: `MainWindow._ddl_fetch_epoch` needs.
        self._check_epoch = 0

        #: Replaceable seams -- ATTRIBUTES, not methods. See the module
        #: docstring: the suite assigns over them to keep a live DB connection
        #: and a modal out of the test run.
        self.fetch_schema = self._fetch_schema
        self.prompt_rename = self._prompt_rename

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

    # -- the coherence view --------------------------------------------------

    def _reveal_panel(self) -> None:
        # `reveal_left_panel` owns the whole gesture -- un-hide the dock, show
        # the tab, make it current (BUG-260812023420). This lane used to call an
        # injected `show_left_dock` first; that pairing was enforced by nothing,
        # so the seam absorbed it and the injection is gone.
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
            self._bump_check_epoch()
            self._shell.set_left_panel_visible(self._panel, False)

    def _bump_check_epoch(self) -> int:
        """Supersede whatever coherence check is in flight, and return the new
        epoch (BUG-260812110307).

        Called from every run (last requested wins) and from every close — the
        menu toggle off and the project-close teardown.
        """
        self._check_epoch += 1
        return self._check_epoch

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
        params = (
            self._target_params(project.tree)
            if self._target_params is not None
            else seed_params(project.tree, self._settings)
        )
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
        # BUG-260812110307: taken on the GUI thread, after the guards above (a
        # refused run started no fetch and must not supersede a live one).
        epoch = self._bump_check_epoch()

        def on_result(schema):
            summary = f"{params.user}@{params.host}:{params.port}/{params.database}"
            # BUG-260812110307, the DDL Explorer's defect in this lane: closing
            # the Database/XML Coherence tab while its fetch is out used to be
            # undone by the stale result, which revealed the panel again and
            # re-checked the menu entry. `refresh_if_open` already asks the right
            # question (`_panel_visible()`); this path could not, because on a
            # normal run the panel is still hidden here -- `_reveal_panel` below
            # is what shows it. Hence an epoch, not a visibility test.
            #
            # `on_error` stays deliberately unguarded: it reveals nothing, and a
            # failed check is worth reporting even for a closed panel.
            #
            # Unlike the DDL lane, this one keeps NOTHING from a superseded
            # result -- `last_schema`/`last_summary` are written below the guard
            # on purpose. One of the two closing gestures is
            # `teardown_for_project_close`, which drops that cache precisely so a
            # later reparse or rename cannot act on a closed project's state
            # (BUG-011, §17); writing it here would hand it straight back. No
            # other surface consumes it, so there is no §18.6-shaped reason to
            # keep it either.
            if self._check_epoch != epoch:
                self._shell.status(
                    "Database/XML Coherence: closed while checking — "
                    "the result was discarded.",
                    5000,
                )
                _log.info("db: coherence check finished stale=True")
                return
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
        self._bump_check_epoch()
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
        # token. The bar is permanently visible (FQ-016), so seeding it is the
        # whole gesture -- there is nothing left to reveal, and `set_find_text`
        # is the unconditional setter (the focus path only fills an empty field).
        bar = stage.find_replace_bar
        bar.set_find_text(token)
        # List every occurrence in the bottom panel (reuses Find All), and
        # reveal the panel in case a prior DB check left it hidden.
        self._find_all(token)
        self._show_audit_dock()
        # Select the first occurrence; F3 (Find Next) continues from there.
        bar.find_next()
        editor.setFocus()

    # -- Create page/detail/lookup from a DB table (SP3, FQ-006) -------------

    #: What each `what` is called in user-facing text.
    _CREATE_LABELS = {"page": "Page", "detail": "Detail", "lookup": "Lookup"}

    def on_create_requested(self, what, name) -> None:
        """Right-click on a relation node in the coherence view's Tables and
        Views branch: synthesize a page/detail/lookup and open it as a DRAFT in
        a new center-stage tab (FQ-006).

        All three kinds land in the same place. Nothing is written to the
        project buffer and nothing goes to the clipboard: the draft is the
        user's to review, edit and copy out of — or to close unused."""
        schema = self.last_schema
        if schema is None or schema.table(name) is None:
            self._shell.status(
                f"No schema for '{name}' — run Database/XML Coherence first.", 5000
            )
            return
        builders = {
            "page": table_gen.build_page,
            "detail": table_gen.build_detail,
            "lookup": table_gen.build_lookup,
        }
        build = builders.get(what)
        if build is None:
            return
        try:
            element = build(schema, name)
        except table_gen.GenerationError as exc:
            self._shell.status(f"Could not create {what}: {exc}", 8000)
            return
        self._open_draft_tab(what, name, element)

    def _open_draft_tab(self, what, name, element) -> None:
        """Serialize `element` at indent 0 (generation itself is untouched) and
        hand it to a fresh `CenterStage` draft tab."""
        # The duplicate scan runs BEFORE the tab opens but can never stop it:
        # since nothing auto-inserts into the real XML any more, a collision
        # only matters when the user manually pastes the draft in later — which
        # the app cannot observe — so this is a heads-up, not a gate (FQ-006).
        note = self._duplicate_note(name, element)
        self._shell.stage.open_draft_fragment_tab(
            what, name, table_gen.serialize(element, indent=0)
        )
        label = self._CREATE_LABELS.get(what, what)
        message = (
            f"{label} draft for '{name}' opened in a new tab — edit it, then "
            "copy it into your project when you are ready."
        )
        if note:
            message = f"{message} {note}"
        self._shell.status(message, 8000)

    def _duplicate_note(self, name, element) -> str:
        """A non-blocking heads-up about a fileName/tableName that already
        exists in the buffer, or "" when there is nothing to flag. Purely
        informational — the draft keeps whatever `fileName` the generator
        produced (FQ-006 dropped the old auto-rename outright)."""
        buffer = self._shell.stage.xml_editor.toPlainText()
        file_name = element.get("fileName") or ""
        if file_name and f'fileName="{file_name}"' in buffer:
            return (
                f'Note: fileName="{file_name}" already exists in the project — '
                "rename it in the draft before pasting."
            )
        if f'tableName="{name}"' in buffer:
            return f"Note: '{name}' is already referenced in the project XML."
        return ""
