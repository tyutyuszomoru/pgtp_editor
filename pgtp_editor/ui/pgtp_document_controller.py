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
"""The open `.pgtp` **document** lane: open, reparse, save, close, discard
changes, and the one thing that hangs off "which file is open" — §7's
Discard Changes gating.

FQ-020 re-specified the last of those: `Revert` (reload `<path>.bak`, i.e. *undo
my last save*, leaving the buffer dirty) is replaced by **Discard Changes**
(reload from disk, leaving the buffer clean), gated on the **dirty flag** rather
than on a `.bak` existing. `backup_path()` and the `.bak` reader are gone; the
two remaining `.bak` writers (non-project `_write_project_text`, and the compare
target's in `diff_merge_controller`) are untouched.

FQ-010 removed the other one: there is no recent-files MRU here any more (no
`recentFiles` key, no `File ▸ Open Recent`). Recent *files* suited the
standalone-`.pgtp`-editor era the project has left; recent *projects* is the
memory a project-centric app should have, and is a separate, later entry. Do not
reintroduce an MRU in this lane.

What it owns
------------
The four pieces of state the whole window used to read off the host directly:

* :attr:`project` — the last successfully parsed ``ProjectModel``, or ``None``;
* :attr:`project_path` — the file a Save writes to (a ``str``, normalized on
  adoption so downstream ``path + ".bak"`` concatenation cannot hit a
  ``TypeError``);
* :attr:`dirty` — whether the buffer differs from disk;
* :attr:`loading` — the guard that makes a *programmatic* ``setPlainText``
  (open / discard-changes / close / parse-failure fallback) not count as a
  user edit.

``MainWindow`` keeps six permanent delegating properties over this lane and
``DdlProjectController`` (``_current_project``, ``_current_project_path``,
``_dirty``, ``_loading``, ``_ddl_project_folder``, ``_ddl_project_settings``) —
a **closed** list, not a shim to grow.

Three signals, and why the close path in particular is one
----------------------------------------------------------
* ``project_changed(object)`` is emitted with a freshly parsed model at the
  point the project tree must be rebuilt from it. Deliberately emitted
  *before* :attr:`project` is adopted, exactly where the old inline
  ``project_tree.populate_from_project(project)`` call stood: a subscriber that
  raised previously left the last-good model in place, and that must stay true.
* ``dirty_changed(bool)`` is what re-renders the window title.
* ``project_closed()`` is the load-bearing one. Before the extraction,
  :meth:`close` cleared **nine** areas inline — editor buffer, project tree,
  model, path, snapshot history, dirty flag, the coherence tab's visibility,
  the coherence panel's contents, the coherence toggle's check state and the
  cached schema/summary behind it. Four of those belong to this lane (buffer,
  model, path, dirty) and are still done here; the rest are **subscribers** the
  host wires up. That split is not cosmetic: BUG-011 was a coherence tab
  surviving a project close, and the only reason it cannot come back is that
  "what a close tears down" is now a broadcast every lane answers for itself
  (``CoherenceController.teardown_for_project_close``,
  ``SnapshotHistory.clear``, …) rather than a list of foreign attribute writes
  living in this file. Never re-inline one.

  It fires **only on a committed close**. A cancelled close (or a
  ``confirm="save"`` whose save was cancelled) returns before the emit, so the
  still-open project keeps its tab; :meth:`discard_changes` keeps the project
  loaded and therefore never tears down either.

``silent`` on :meth:`reparse` is KEYWORD-ONLY on purpose
--------------------------------------------------------
BUG-021's bug class is a ``triggered`` signal's ``checked: bool`` landing in a
handler's first positional parameter — ``False`` is not ``None``, so it read as
a real argument. Keyword-only makes that structurally impossible here, and a
silent parse failure returns *before* :meth:`_handle_reparse_failure`, so
§9's background auto-parse can never raise a modal or move the caret while the
user is mid-keystroke. Keep both properties.

The replaceable seams are ATTRIBUTES
------------------------------------
:attr:`confirm_close`, :attr:`confirm_discard_changes`, :attr:`prompt_open_mode`
and :attr:`save_project` are
plain instance attributes, not methods, because the suite assigns over them
(three modals and "a save that succeeds / a save that was cancelled"). Every
internal caller goes through the attribute, so an assignment on the finished
object is honoured.

Shape
-----
A ``QObject`` following ``ui/coherence_controller.py``: it takes a
:class:`~pgtp_editor.ui.ui_shell.UiShell`, constructs headless, and never
dereferences ``shell.window`` (it appears only as a dialog parent for the
``ui/modals`` statics). What the shell cannot reach is injected as callables,
never by importing another collaborator:

* ``resolve_project_path`` / ``link_pgtp`` / ``working_copy_path`` — the §18.2
  `.pgtp`-link triangle, owned by ``DdlProjectController``. Opening a `.pgtp`
  may redirect to a project's working copy, and a first open *creates* that
  working copy; both are the project lane's decisions, not the document's.
* ``import_pgtp_connection`` — BUG-034's "this `.pgtp`'s design-time connection
  becomes the project's target", host-side because the target-connection
  cluster is.
* ``has_ddl_project`` / ``new_ddl_project`` / ``open_ddl_project`` — the other
  half of the same triangle: :meth:`prompt_open_mode`'s New/Open/Standalone
  chooser. Injected callables resolved at CALL time, which is why the
  document ↔ project cycle needs no two-phase construction.
* ``history_push`` / ``history_clear`` — the snapshot history still lives on the
  host and moves to its own lane later.
* ``status_bar`` — ``busy_status`` needs an object with ``showMessage``, which
  ``UiShell.status`` (a bare callable) is not.
"""
from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from pgtp_editor.db.activity_log import (
    FILE_VERB_OPENED,
    FILE_VERB_REVERTED,
    FILE_VERB_SAVED,
)
from pgtp_editor.model.encoding import read_pgtp_text
from pgtp_editor.model.parser import (
    PgtpParseError,
    load_project,
    load_project_from_text,
)
from pgtp_editor.ui import modals
from pgtp_editor.ui.busy import busy_status, format_size
from pgtp_editor.ui.ui_shell import UiShell

_log = logging.getLogger(__name__)


class PgtpDocumentController(QObject):
    """Owns the open `.pgtp` document: its model, path, dirty/loading flags,
    and the open / reparse / save / close / discard-changes gestures over
    them."""

    #: A freshly parsed model, announced where the project tree is rebuilt from
    #: it (see the module docstring on the deliberate pre-adoption timing).
    project_changed = Signal(object)

    #: The dirty flag changed (or was re-asserted) — what refreshes the title.
    dirty_changed = Signal(bool)

    #: A close was COMMITTED. Every project-tied surface tears itself down off
    #: this; nothing about them is inlined into `close()`. See BUG-011.
    project_closed = Signal()

    def __init__(
        self,
        shell: UiShell,
        parent: QObject | None = None,
        *,
        status_bar: Callable[[], object],
        reset_properties: Callable[[], None],
        history_push: Callable[..., None],
        history_clear: Callable[[], None],
        enrich_schema: Callable[[str], None],
        refresh_coherence: Callable[[object], None],
        resolve_project_path: Callable[[object], str],
        link_pgtp: Callable[[], None],
        import_pgtp_connection: Callable[[], None],
        working_copy_path: Callable[[], "str | None"],
        has_ddl_project: Callable[[], bool],
        new_ddl_project: Callable[..., None],
        open_ddl_project: Callable[..., None],
        record_activity: "Callable[..., object] | None" = None,
    ):
        super().__init__(parent)
        self._shell = shell
        self._settings = shell.settings
        self._status_bar = status_bar
        self._reset_properties = reset_properties
        self._history_push = history_push
        self._history_clear = history_clear
        self._enrich_schema = enrich_schema
        self._refresh_coherence = refresh_coherence
        self._resolve_project_path = resolve_project_path
        self._link_pgtp = link_pgtp
        self._import_pgtp_connection = import_pgtp_connection
        self._working_copy_path = working_copy_path
        self._has_ddl_project = has_ddl_project
        self._new_ddl_project = new_ddl_project
        self._open_ddl_project = open_ddl_project
        #: FQ-019: `MainWindow.record_file_activity(file_verb, error=None)`, the
        #: Activity Log's file emit point. Optional and defaulted to a no-op so
        #: the ~40 tests that build this controller directly need no new
        #: argument; the lane emits a VERB only and never decides whether the
        #: action was standalone or project-scoped -- that is the host's one
        #: `_file_activity_source` call, and persistence is the core's decision.
        self._record_activity = record_activity or (lambda *a, **k: None)

        #: The last successfully parsed model, and the file a Save writes to.
        self._project = None
        self._path = None
        #: Document dirty-state tracking. `_loading` guards programmatic
        #: setPlainText calls (load/discard-changes/close) so they don't
        #: spuriously mark the buffer dirty.
        self._dirty = False
        self._loading = False

        #: File ▸ Discard Changes, handed over once the File menu is built (§7).
        #: None until then, which is also why
        #: `refresh_discard_changes_action` is guarded.
        self._discard_changes_action = None

        #: Replaceable seams -- ATTRIBUTES, not methods. See the module
        #: docstring: the suite assigns over them to keep two modals out of the
        #: run and to model a save that succeeds vs. one that was cancelled.
        self.confirm_close = self._confirm_close
        self.confirm_discard_changes = self._confirm_discard_changes
        self.prompt_open_mode = self._prompt_open_mode
        self.save_project = self._save_project

    # -- document state ------------------------------------------------------

    @property
    def project(self):
        """The last successfully parsed `ProjectModel`, or None."""
        return self._project

    @project.setter
    def project(self, value) -> None:
        self._project = value

    @property
    def project_path(self):
        """The file a Save writes to, as a `str`, or None."""
        return self._path

    @project_path.setter
    def project_path(self, value) -> None:
        self._path = value

    @property
    def dirty(self) -> bool:
        """Whether the buffer differs from what is on disk.

        A plain store on assignment (no title refresh, no signal) because that
        is what a direct `window._dirty = True` always did; :meth:`set_dirty` is
        the announcing setter."""
        return self._dirty

    @dirty.setter
    def dirty(self, value) -> None:
        self._dirty = value

    @property
    def loading(self) -> bool:
        """True while a programmatic buffer replacement is in flight."""
        return self._loading

    @loading.setter
    def loading(self, value) -> None:
        self._loading = value

    def set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        # FQ-020: Discard Changes is gated on THIS flag, so the gate can ride on
        # every keystroke -- which the old `.bak`-existence gate could not (it
        # would have meant a `stat` per keypress on a possibly-sshfs-mounted
        # path, see `refresh_discard_changes_action`).
        self.refresh_discard_changes_action()
        self.dirty_changed.emit(dirty)

    # -- read-only surface ---------------------------------------------------

    @property
    def discard_changes_action(self):
        """File ▸ Discard Changes, or None before the File menu is built (§7)."""
        return self._discard_changes_action

    # -- construction --------------------------------------------------------

    def set_discard_changes_action(self, action) -> None:
        """Adopt File ▸ Discard Changes and gate it immediately (§7).

        The host builds the File menu (most of it is not this lane's) and hands
        this one action over, mirroring `CoherenceController.set_toggle_action`.
        """
        self._discard_changes_action = action
        self.refresh_discard_changes_action()

    # -- seams ---------------------------------------------------------------

    def _confirm_close(self) -> str:
        """Ask the user how to resolve unsaved changes before closing.

        Returns "save", "discard", or "cancel". Reached through the replaceable
        `confirm_close` attribute so tests never drive a real modal (they can
        also pass `confirm=` straight to :meth:`close`).
        """
        result = modals.QMessageBox.question(
            # The ONE sanctioned use of shell.window: a dialog parent.
            self._shell.window,
            "Unsaved Changes",
            "The project has unsaved changes. Save before closing?",
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.Discard
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if result == modals.QMessageBox.StandardButton.Save:
            return "save"
        if result == modals.QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def _prompt_open_mode(self, path) -> None:
        """The first time a `.pgtp` is opened with no project active, ask how
        to work with it (§18.2): start a **New Project** around it, attach it
        to an existing project via **Open Project**, or **Edit Standalone**
        (today's plain behavior -- no project, no linking, unaffected). If
        the chooser is dismissed without a button (e.g. the window close
        box), defaults to Standalone -- the safe, non-destructive choice.

        Reached through the replaceable `prompt_open_mode` attribute."""
        box = modals.QMessageBox(self._shell.window)
        box.setWindowTitle("Open .pgtp")
        box.setText("How do you want to work with this file?")
        new_button = box.addButton("New Project…", modals.QMessageBox.ButtonRole.ActionRole)
        open_button = box.addButton("Open Project…", modals.QMessageBox.ButtonRole.ActionRole)
        box.addButton("Edit Standalone", modals.QMessageBox.ButtonRole.ActionRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is new_button:
            self._new_ddl_project(on_ready=lambda: self.open_file(path))
        elif clicked is open_button:
            self._open_ddl_project(on_ready=lambda: self.open_file(path))
        else:
            self.open_file(path)

    @staticmethod
    def read_raw_text(path) -> "str | None":
        """Read the file at `path` as text, or None if it can't be read.

        Uses the same CESU-8 repair as the model parser (see
        model/encoding.py) so the raw editor shows exactly what the parser
        saw -- including files with emoji that a strict UTF-8 read would
        choke on with UnicodeDecodeError. Guards the TOCTOU race where the
        file is deleted/becomes unreadable between an earlier successful
        step and this raw re-read (OSError), and treats a genuinely
        undecodable file (UnicodeDecodeError even after repair) the same
        way rather than letting it crash the open/fallback flow.
        """
        try:
            return read_pgtp_text(path)
        except (OSError, UnicodeDecodeError):
            return None

    # -- open ----------------------------------------------------------------

    def open_dialog(self) -> None:
        """File ▸ Open… — pick a `.pgtp` and route it through the one open path."""
        path, _filter = modals.QFileDialog.getOpenFileName(
            self._shell.window,
            "Open PGTP Project",
            self._shell.default_dir(),
            "PGTP files (*.pgtp)",
        )
        if not path:
            return
        self.open_pgtp_path(path)

    def open_pgtp_path(self, path) -> None:
        """Open a `.pgtp` the way File ▸ Open… does, given a path that came
        from somewhere other than that dialog (§21's drag-and-drop drops one
        here). Split out so no caller can fork the §18.2 decision."""
        if not self._has_ddl_project():
            self.prompt_open_mode(str(path))
        else:
            # A project is already active -- the user already committed to
            # project mode; just open (existing linking logic applies
            # silently, exactly as it does for any subsequent open).
            self.open_file(str(path))

    def open_file(self, path):
        """Load and display the .pgtp project at `path`.

        Split out from `open_dialog` so tests (and `main.py`) can drive the load
        without going through the QFileDialog. On parse failure, shows a clear
        error dialog, populates the Raw XML fallback view (see
        `_handle_parse_failure`), and leaves the currently-displayed tree
        (and the currently-tracked project) untouched (never a crash, never
        a silently-emptied tree or a silently-forgotten project).
        """
        path = self._resolve_project_path(path)
        _log.info("file: open %s", path)
        name = Path(path).name
        try:
            message = f"Opening {name} ({format_size(os.path.getsize(path))})…"
        except OSError:
            # Never fail the open over a stat hiccup; just drop the size.
            message = f"Opening {name}…"

        editor = self._shell.stage.xml_editor
        parse_error = None
        with busy_status(self._status_bar(), message):
            try:
                project = load_project(path)
            except PgtpParseError as exc:
                parse_error = exc
            else:
                self.project_changed.emit(project)
                self._project = project
                # Normalize to str so downstream string ops (e.g. the ".bak"
                # path concatenation in `_write_project_text`) never hit
                # a TypeError when a caller passes a pathlib.Path instead of the
                # QFileDialog string.
                self._path = str(path)
                self._link_pgtp()
                # BUG-034: the `.pgtp`'s design-time connection becomes the
                # project's target profile. Here, next to the link step,
                # because both are "this `.pgtp` just became part of this
                # project" bookkeeping and both need the freshly parsed tree.
                self._import_pgtp_connection()
                raw_text = self.read_raw_text(path)
                if raw_text is not None:
                    self._loading = True
                    try:
                        editor.setPlainText(raw_text)
                    finally:
                        self._loading = False
                self.set_dirty(False)
                # A newly-opened project is a fresh document: drop the previous
                # project's snapshots so undo never crosses between documents,
                # then seed the history with the freshly-loaded text.
                self._history_clear()
                self._history_push(
                    editor.toPlainText(),
                    f"Opened {name}",
                    baseline=True,
                )
                # Schema enrichment is the slowest part of open; keep it inside
                # the busy block so the hourglass covers it.
                self._enrich_schema(path)

        # Cursor restored here (busy_status __exit__), BEFORE any dialog.
        if parse_error is not None:
            # FQ-019: a `.pgtp` that failed to parse was still an OPEN the user
            # attempted, and the parse error is exactly the text the journal's
            # click-through viewer exists to show in full.
            self._record_activity(FILE_VERB_OPENED, error=f"{path}: {parse_error}")
            self._handle_parse_failure(path, parse_error)
            return
        self._record_activity(FILE_VERB_OPENED)
        # §7 Discard Changes gating: `set_dirty(False)` above already refreshed
        # it, but only on the SUCCESS path -- a failed parse must not advertise
        # the freshly-assigned path as discardable.
        self.refresh_discard_changes_action()
        self._shell.status(f"Opened: {path}", 5000)

    def _handle_parse_failure(self, path, exc: PgtpParseError) -> None:
        modals.QMessageBox.critical(
            self._shell.window,
            "Failed to Open Project",
            f"Could not open '{path}':\n\n{exc}",
        )
        raw_text = self.read_raw_text(path)
        if raw_text is None:
            # The file itself is unreadable (e.g. deleted between the
            # earlier parse attempt and this read, or a permissions error) --
            # nothing to show in the fallback view in that case; the dialog
            # above already reported the failure.
            return
        editor = self._shell.stage.xml_editor
        # The fallback view displays on-disk content of a file that FAILED to
        # open -- it is not a user edit, so it must not mark the document dirty
        # (and must never let a later Save overwrite the still-tracked good
        # project with this broken text). Guard the same way as the load path.
        self._loading = True
        try:
            editor.setPlainText(raw_text)
        finally:
            self._loading = False
        # Seed the snapshot history with the as-loaded (unparsed) text so undo
        # after fixing the broken file has a base to return to, mirroring a
        # normal open. Pushed after the `_loading` block so it reflects the
        # shown text.
        self._history_push(
            editor.toPlainText(),
            f"Opened (unparsed) {Path(path).name}",
            baseline=True,
        )
        if exc.line is not None:
            editor.highlight_error_line(exc.line)
        self._shell.reveal_raw_xml()

    # -- reparse (Tools ▸ Reparse, and §9 auto-parse) ------------------------

    def reparse(self, *, silent: bool = False):
        """Reparse the Raw XML buffer into the tree/model.

        `silent` is KEYWORD-ONLY and defaults to False, so every pre-existing
        caller -- Tools ▸ "Reparse Raw XML into Tree" (whose `triggered` signal
        passes no positional argument to a callable with no positional
        parameters), the coherence rename path and the tests -- keeps exactly
        today's behavior, modal failure dialog included. Only §9's auto-parse
        passes `silent=True`, which downgrades a `PgtpParseError` to a transient
        status-bar line: it fires while the user is mid-edit, where a modal (or a
        cursor jump) would be an interruption, and half-typed XML is expected to
        be malformed. Either way the last-good model and tree survive.
        """
        text = self._shell.stage.xml_editor.toPlainText()
        parse_error = None
        with busy_status(self._status_bar(), "Reparsing…"):
            try:
                project = load_project_from_text(text, source_description="<editor>")
            except PgtpParseError as exc:
                parse_error = exc
            else:
                # SUCCESS: rebuild tree + adopt the new model so click-sync realigns.
                self.project_changed.emit(project)
                self._project = project
                # Properties has no valid selection against the freshly rebuilt
                # tree (populate_from_project cleared it); show the empty state
                # until the user clicks again. show_node(None, None) resets it.
                self._reset_properties()
        # Cursor restored before any failure dialog.
        if parse_error is not None:
            if silent:
                # §9: NO modal and NO cursor jump while auto-parsing -- the user
                # is typing. A transient status-bar line only; the tree keeps its
                # last-good state (nothing above touched it on this path).
                self._shell.status(
                    "Auto-parse: XML not well-formed yet — tree not updated", 5000
                )
                return
            self._handle_reparse_failure(parse_error)
            return
        if silent:
            self._shell.status("Auto-parsed raw XML into tree", 3000)
        else:
            self._shell.status("Reparsed raw XML into tree", 5000)
        self._refresh_coherence(project)

    def _handle_reparse_failure(self, exc: PgtpParseError) -> None:
        # Mirror the Tier-1 open-failure pattern (_handle_parse_failure), but
        # WITHOUT re-reading a file and WITHOUT touching the existing model or
        # tree: the last-good state must survive a failed reparse so the user
        # can fix the XML and try again.
        modals.QMessageBox.critical(
            self._shell.window,
            "Reparse Failed",
            f"Could not reparse the raw XML:\n\n{exc}",
        )
        if exc.line is not None:
            self._shell.stage.xml_editor.highlight_error_line(exc.line)

    # -- save ----------------------------------------------------------------

    def _write_project_text(self, path) -> None:
        """Write the Raw XML editor buffer verbatim to `path` as UTF-8. If
        `path` already exists, copy it to `path + '.bak'` first (same .bak
        convention as Apply-to-Target) -- **unless** `path` is a local
        §18.2 project's `.pgtp` working copy, where the working copy itself
        is the safety net and no `.bak` is written, exactly like `ddl/*.sql`
        (§18.2, "the .pgtp file becomes a first-class checked-out
        artifact"). Scoped precisely to that case: no-project-mode saves are
        completely unaffected."""
        _log.info("file: save %s", path)
        if Path(path).exists() and not self.is_project_working_copy(path):
            shutil.copy2(path, str(path) + ".bak")
        Path(path).write_text(
            self._shell.stage.xml_editor.toPlainText(), encoding="utf-8", newline=""
        )

    def is_project_working_copy(self, path) -> bool:
        """Whether `path` IS the active §18.2 project's `.pgtp` working copy --
        the one case that gets no `.bak`. The link itself belongs to
        `DdlProjectController`, so the answer is read through the injected
        `working_copy_path` provider rather than duplicated here."""
        working_copy_path = self._working_copy_path()
        return working_copy_path is not None and str(path) == working_copy_path

    def _save_project(self) -> None:
        if not self._path:
            self.save_as()
            return
        try:
            self._write_project_text(self._path)
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window, "Save Failed", f"Could not save:\n\n{exc}"
            )
            self._record_activity(FILE_VERB_SAVED, error=f"{self._path}: {exc}")
            return
        self._record_activity(FILE_VERB_SAVED)
        # `set_dirty(False)` re-gates Discard Changes on its own now (FQ-020:
        # the gate is the dirty flag, and a just-saved buffer has nothing to
        # discard) -- no separate refresh call is needed here any more.
        self.set_dirty(False)
        self._shell.status(f"Saved {Path(self._path).name}", 5000)

    def save_as(self) -> None:
        path, _filter = modals.QFileDialog.getSaveFileName(
            self._shell.window,
            "Save Project As",
            self._shell.default_dir(),
            "PGTP files (*.pgtp)",
        )
        if not path:
            return
        try:
            self._write_project_text(path)
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window, "Save Failed", f"Could not save:\n\n{exc}"
            )
            self._record_activity(FILE_VERB_SAVED, error=f"{path}: {exc}")
            return
        self._record_activity(FILE_VERB_SAVED)
        self._path = path
        self.set_dirty(False)
        self._shell.status(f"Saved as {Path(path).name}", 5000)

    def ensure_saved(self, save_as: bool = False) -> bool:
        """`GenerationController`'s save seam: run the project's own Save (or
        Save As) and answer whether the project now exists on disk.

        The generation lane must not know *how* a project is saved -- it only
        needs "is the editor's content on disk now?", because the generator
        reads the `.pgtp` from there. False means there is nothing to generate
        from (Save As was cancelled).
        """
        if save_as:
            self.save_as()
        else:
            self.save_project()
        return bool(self._path)

    # -- close / discard changes ---------------------------------------------

    def close(self, confirm=None) -> None:
        """Close the current project, prompting to resolve unsaved changes.

        `confirm` is the test seam: "save"/"discard"/"cancel". When None and
        the buffer is dirty, `confirm_close()` decides; when None and clean,
        the close proceeds (treated as "discard").

        Only the document's OWN four pieces of state are cleared here; every
        other project-tied surface tears itself down off `project_closed`. See
        the module docstring — re-inlining any of them is how BUG-011 comes
        back.
        """
        if self._dirty:
            if confirm is None:
                confirm = self.confirm_close()
            outcome = {"save": "saved", "discard": "discarded"}.get(confirm, confirm)
        else:
            confirm = "discard"
            outcome = "clean"

        if confirm == "cancel":
            _log.info("file: close outcome=cancelled")
            return
        if confirm == "save":
            self.save_project()
            if self._dirty:
                # Save was cancelled (e.g. Save-As dialog dismissed) --
                # don't discard the user's changes.
                _log.info("file: close outcome=cancelled")
                return

        self._loading = True
        try:
            self._shell.stage.xml_editor.setPlainText("")
        finally:
            self._loading = False
        self._project = None
        self._path = None
        # No open file, nothing to discard -- `set_dirty` re-gates it (§7).
        self.set_dirty(False)
        # The committed-close broadcast: project tree, snapshot history and the
        # coherence surface (BUG-011) all hang off this. A cancelled close
        # returned above, and `discard_changes` keeps the project loaded so it
        # never tears down.
        self.project_closed.emit()
        _log.info("file: close outcome=%s", outcome)

    def refresh_discard_changes_action(self) -> None:
        """Gate File ▸ Discard Changes on there being something to discard --
        an open file whose buffer is dirty (§7, FQ-020).

        The gate is the **dirty flag**, deliberately not a re-read of the file:
        the command it now backs is *reload from disk*, so "the buffer differs
        from disk" is exactly what `_dirty` already tracks. That makes it
        *cheaper* than the `.bak`-existence gate it replaced, which had to be
        kept off `set_dirty` because `Path(...).exists()` on every keystroke is a
        `stat` on a possibly-sshfs-mounted path (§18.2). Guarded on the action
        existing because `set_discard_changes_action` refreshes during menu
        construction and earlier call paths run before the File menu exists.
        """
        action = self._discard_changes_action
        if action is None:
            return
        action.setEnabled(bool(self._path) and self._dirty)

    def _confirm_discard_changes(self) -> bool:
        """Confirm the discard, naming what is lost (§7). Its own method, and
        reassigned as a seam in `__init__`, so tests never drive a real modal."""
        return (
            modals.QMessageBox.question(
                self._shell.window,
                "Discard Changes",
                f"Discard all changes to {Path(self._path).name} and reload it "
                "from disk?\n\nEdits made since the last save will be lost.",
                modals.QMessageBox.StandardButton.Yes
                | modals.QMessageBox.StandardButton.No,
            )
            == modals.QMessageBox.StandardButton.Yes
        )

    def discard_changes(self, confirm=None) -> None:
        """File ▸ Discard Changes: **reload the document from disk**, throwing
        away the edits made since the last save (§7, FQ-020).

        This REPLACED `revert()`, which read `<path>.bak` -- *"undo my last
        save"* -- and left the buffer dirty. The two are genuinely different
        commands, which is why the label changed with the behaviour rather than
        the word being quietly redefined; `backup_path()` and the `.bak` reader
        are gone with it. Nothing here writes a `.bak` either, so the two
        remaining writers (`_write_project_text` in non-project mode, and
        `diff_merge_controller.apply_changes_to_target`, which writes beside the
        *compare target*) are untouched by the change.

        `confirm` is the test seam, mirroring `close(confirm=…)`: True/False
        short-circuits the dialog.
        """
        if not self._path:
            self._shell.status("No file is open — nothing to discard.", 5000)
            self.refresh_discard_changes_action()
            return
        if not self._dirty:
            # Still defended at runtime even though the action is gated on the
            # same condition: the toolbar mirrors the action, and a pinned button
            # can be clicked between refreshes.
            self._shell.status("No unsaved changes to discard.", 5000)
            self.refresh_discard_changes_action()
            return
        if confirm is None:
            confirm = self.confirm_discard_changes()
        if not confirm:
            _log.info("file: discard-changes outcome=cancelled")
            return

        path = self._path
        _log.info("file: discard-changes %s", path)
        try:
            project = load_project(path)
        except PgtpParseError as exc:
            # The file on disk is what failed to parse, so the buffer is left
            # exactly as it was -- discarding into an unparseable state would
            # lose the user's edits AND give them nothing back.
            # FQ-019: `Reverted` is the journal's name for this gesture (the
            # `.bak`-reading `revert()` FQ-020 replaced is gone; Discard Changes
            # is the surviving "put the file back" command).
            self._record_activity(FILE_VERB_REVERTED, error=f"{path}: {exc}")
            self._handle_parse_failure(path, exc)
            return

        editor = self._shell.stage.xml_editor
        raw_text = self.read_raw_text(path)
        if raw_text is not None:
            self._loading = True
            try:
                editor.setPlainText(raw_text)
            finally:
                self._loading = False
            # Seed the snapshot history with the on-disk text so undo/redo
            # semantics after a discard match a normal open.
            self._history_push(
                editor.toPlainText(),
                f"Discarded changes in {Path(path).name}",
                baseline=True,
            )
        self.project_changed.emit(project)
        self._project = project
        # The buffer now IS the file on disk -- the opposite of `revert()`, which
        # left it dirty because it had loaded a different file (`.bak`).
        self.set_dirty(False)
        self._record_activity(FILE_VERB_REVERTED)
        self._shell.status(f"Discarded changes in {Path(path).name}", 5000)
