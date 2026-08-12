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
"""The schema lane (spec §11): the Schema menu, the Edit-XSD tab, and the
curated-schema feed everything else completes and hovers against.

What it owns
------------
The whole §11 surface and nothing else:

* the **Schema menu** (Edit XSD / Edit AutoXSD / Verify / Export / Import) plus
  the window-level "Go To XSD" (Ctrl+L) action — a menu owned outright by one
  collaborator moves with it;
* the shared **Edit-XSD tab**: which of the two schemas it currently holds
  (:attr:`mode`), its dirty flag, its programmatic-load guard, its tab title;
* the on-disk artifacts under the schema storage directory — the hand-owned
  ``curated.xsd``, the auto-learned ``learned.xsd``, the learning engine's
  ``schema_model.json`` — including the one-time bootstrap and the
  open-a-``.pgtp`` enrichment pass that grows the learned model;
* the parsed :attr:`curated_schema`, the SOLE source feeding completion/hover.

Why this lane was extracted early
---------------------------------
It is the largest **cohesive** block in ``main_window.py`` and it holds **zero
document state** — nothing here reads ``_current_project``, ``_dirty``, the
snapshot history or the DDL/sandbox lanes. The XSD tab's dirty flag is its own
(``dirty`` below), deliberately distinct from the document's, and the two
confirmation prompts never share state.

Shape
-----
A ``QObject`` following ``ui/toolbar_controller.py``: it takes a
:class:`~pgtp_editor.ui.ui_shell.UiShell`, constructs headless, and never
dereferences ``shell.window`` (it appears only as a dialog parent for the
``ui/modals`` statics). Two things it cannot reach through the shell are
injected by the host instead:

* ``feed_properties_schema`` — the Properties panel is not a §11 surface, but a
  freshly parsed curated schema has to reach it. Injected as a callable rather
  than grown as a shell field, because exactly one lane needs it.
* ``add_window_action`` (an argument of :meth:`build_menu`) — ``Ctrl+L`` is a
  window-level ``QAction``, and ``QMainWindow.addAction`` is a host gesture, the
  same way ``ToolbarController.build`` receives ``addToolBar``.

The confirm seam is an ATTRIBUTE
-------------------------------
:attr:`confirm_close` is a plain instance attribute, not a method, because the
suite replaces it in over a dozen places (``controller.confirm_close = lambda:
"discard"``) to keep a real modal off the screen. Keep it assignable: turning it
back into a method would break every one of those tests at once.
"""
from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QListWidgetItem

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.parser import walk_document
from pgtp_editor.schema_learning.storage import (
    CURATED_BUNDLED_VERSION,
    bundled_curated_xsd_text,
    curated_xsd_path,
    learned_xsd_path,
    schema_model_path,
)
from pgtp_editor.schema_learning.xsd_gen import generate_curated_xsd, generate_xsd
from pgtp_editor.schema_learning.xsd_load import XsdLoadError, load_curated
from pgtp_editor.schema_learning.xsd_verify import verify_curated
from pgtp_editor.ui import modals
from pgtp_editor.ui.ui_shell import UiShell

_log = logging.getLogger(__name__)

# Placeholder shown in the Edit-XSD tab when its backing file does not exist yet.
_EMPTY_XSD_SKELETON = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'elementFormDefault="qualified">\n</xs:schema>\n'
)

#: The Schema-menu label of the one sanctioned re-seed (BUG-260812002307 part
#: C). Named here because the two load-failure messages point the user at it:
#: telling someone their curated.xsd is broken without naming the way back is
#: half a message.
RESTORE_BUNDLED_LABEL = "Restore Bundled Curated Schema…"

_SCHEMA_REPORT_TEMPLATES = {
    "new_element": "[Schema] NEW ELEMENT: {path} (first seen in {source})",
    "new_attribute": "[Schema] NEW ATTRIBUTE: {path}@{attr} (first seen in {source})",
    "new_value": '[Schema] NEW ATTR VALUE: {path}@{attr} += "{value}" (from {source})',
    "enum_overflow": "[Schema] ENUM OVERFLOWED: {path}@{attr} now free-form string (from {source})",
    "now_optional": "[Schema] NOW OPTIONAL: {path}@{attr} (previously required, from {source})",
}


class XsdController(QObject):
    """Owns the Schema menu, the Edit-XSD tab and the curated-schema feed."""

    def __init__(
        self,
        shell: UiShell,
        schema_storage_dir: Path | None = None,
        parent: QObject | None = None,
        *,
        feed_properties_schema: Callable[[object], None] | None = None,
    ):
        super().__init__(parent)
        self._shell = shell
        #: Root of the schema artifacts (``None`` = the real per-user AppData
        #: location, resolved by `schema_learning/storage.py`). Handed over by
        #: the host, which keeps it as its injectable constructor seam.
        self._schema_storage_dir = schema_storage_dir
        #: The Properties panel's schema feed -- see the module docstring.
        self._feed_properties_schema = feed_properties_schema
        # The parsed curated.xsd (spec §11) — the sole schema source feeding
        # completion/hover. None until `load_curated` succeeds at least once.
        self._curated_schema = None
        # Edit XSD tab (spec §11): dirty tracking. `_loading` guards
        # programmatic setPlainText calls so they don't spuriously mark dirty.
        self._dirty = False
        self._loading = False
        # Which schema the shared Edit-XSD tab currently holds: "curated"
        # (Schema ▸ Edit XSD) or "learned" (Schema ▸ Edit AutoXSD). Save /
        # Verify / Export / Import all act on the active mode (spec §11).
        self._mode = "curated"
        #: The window-level Ctrl+L action, set by `build_menu`.
        self._goto_xsd_action = None
        #: Set once the "no schema at all" warning has been shown for the
        #: current broken state, and cleared by the next successful load, so a
        #: user who opens six .pgtp files with a corrupt curated.xsd is told
        #: once rather than six times (BUG-260812002307 part B).
        self._reported_broken_curated = False
        #: Schema ▸ Restore Bundled Curated Schema…, set by `build_menu`.
        self._restore_bundled_action = None
        #: Replaceable seam -- an ATTRIBUTE, not a method. See the module
        #: docstring: the suite assigns over it to avoid a real modal.
        self.confirm_close = self._confirm_close_xsd

        # This lane's own center-stage signals, wired here rather than by the
        # host: all three are §11 gestures (the XSD editor's dirty tracking,
        # the Edit-XSD tab's ✕, and Raw XML's "Go To XSD"), and the shell
        # already hands over the stage they live on -- so the host's only
        # contact with this lane is constructing it.
        stage = shell.stage
        stage.xsd_editor.textChanged.connect(self._on_xsd_text_changed)
        stage.xsd_close_requested.connect(self.on_close_requested)
        stage.xml_editor.goto_xsd_requested.connect(self.goto)

    # -- read/write surface --------------------------------------------------

    @property
    def dirty(self) -> bool:
        """Whether the Edit-XSD tab holds unsaved edits."""
        return self._dirty

    @property
    def mode(self) -> str:
        """Which schema the tab currently holds: ``"curated"`` | ``"learned"``."""
        return self._mode

    @property
    def curated_schema(self):
        """The parsed ``curated.xsd`` feeding completion/hover, or None.

        Writable: the suite clears it (``controller.curated_schema = None``) to
        exercise the first-run path after deleting the seeded file.
        """
        return self._curated_schema

    @curated_schema.setter
    def curated_schema(self, schema) -> None:
        self._curated_schema = schema

    @property
    def schema_storage_dir(self) -> Path | None:
        """Root of the schema artifacts, as handed over by the host."""
        return self._schema_storage_dir

    # -- construction --------------------------------------------------------

    def build_menu(self, menu_bar, add_window_action: Callable[[QAction], None]) -> None:
        """Add the Schema menu to `menu_bar` and register the Ctrl+L action.

        `add_window_action` is the host's ``addAction`` -- the ``QMainWindow``
        gesture stays on the host (mirroring ``ToolbarController.build``'s
        ``addToolBar``), this lane only decides what goes on it.
        """
        menu = menu_bar.addMenu("Schema")
        edit_action = menu.addAction("Edit XSD")
        # BUG-021: wrapped so `triggered`'s `checked: bool` argument is never
        # taken for `open`'s `mode` -- `open` has a default parameter, unlike
        # the no-argument slots below.
        edit_action.triggered.connect(lambda: self.open())
        edit_auto_action = menu.addAction("Edit AutoXSD")
        edit_auto_action.triggered.connect(self.open_auto)
        verify_action = menu.addAction("Verify XSD")
        verify_action.triggered.connect(self.verify)
        export_action = menu.addAction("Export XSD")
        export_action.triggered.connect(self.export)
        import_action = menu.addAction("Import XSD")
        import_action.triggered.connect(self.import_)
        # BUG-260812002307 part C: the only in-app way back from a curated.xsd
        # the user broke by hand. It carries NO shortcut — it is a menu command
        # form, so under DEC-012 it would have exactly one keyboard host and
        # the chord would have to clear `docs/KEYBINDINGS.md` first; a menu
        # entry with no chord needs no ledger row.
        restore_action = menu.addAction(RESTORE_BUNDLED_LABEL)
        restore_action.triggered.connect(self.restore_bundled)
        self._restore_bundled_action = restore_action
        # "Go To XSD" (Ctrl+L) lives as a window-level action, not a menu
        # entry -- the Schema menu proper is Edit XSD / Edit AutoXSD / Verify /
        # Export / Import.
        goto_xsd_action = QAction("Go To XSD", self)
        goto_xsd_action.setShortcut(QKeySequence("Ctrl+L"))
        goto_xsd_action.triggered.connect(self.goto_at_cursor)
        add_window_action(goto_xsd_action)
        self._goto_xsd_action = goto_xsd_action

    # -- the curated-schema feed ---------------------------------------------

    def load_curated(self) -> bool:
        """Parse curated.xsd and feed completion/hover from it — the SOLE
        schema source (spec §11). On parse failure the last good in-memory
        schema stays live; returns False.

        **Neither failure is silent any more (BUG-260812002307 part B).** The
        reported symptom was "XSD is not loaded" with nothing on screen saying
        so: the missing-file exit returned False without a word, and the parse
        exit wrote one Activity-Log line. Both now NAME THE RESOLVED PATH,
        because the whole confusion in that report is *which* curated.xsd is in
        play — the pristine bundled resource, or the user's hand-owned app-data
        copy that the bootstrap will never overwrite.

        The escalation rule is "is there any schema at all?", not "did a load
        fail":

        * a broken file **with a last good schema live** is the mild case the
          message already described — completion keeps working, so an audit
          line is proportionate and a modal would be nagging (it fires on every
          save of half-typed XSD text);
        * a broken file **with no schema live** — a fresh start, exactly the
          reported case — means completion, hover and the Properties labels are
          running against ``None``. That gets a modal, once per broken state,
          naming the file and the way back.
        """
        path = curated_xsd_path(self._schema_storage_dir)
        if not path.exists():
            # Previously `return False` with nothing emitted at all. At startup
            # `ensure_bootstrap` runs first and has already audited whatever
            # stopped it from seeding, so this stays a journal line: no modal.
            self._shell.audit.addItem(
                f"[Schema] No curated XSD at {path} — completion, hover and "
                f"Properties labels have no schema until it is restored "
                f"(Schema ▸ {RESTORE_BUNDLED_LABEL})."
            )
            return False
        try:
            schema = load_curated(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, XsdLoadError) as exc:
            if self._curated_schema is not None:
                self._shell.audit.addItem(
                    f"[Schema] Curated XSD has XML errors: {exc} — keeping last "
                    f"good schema ({path})"
                )
                return False
            self._shell.audit.addItem(
                f"[Schema] Curated XSD has XML errors: {exc} — no schema is "
                f"loaded; completion, hover and Properties labels are off "
                f"({path})"
            )
            self._warn_no_curated_schema(path, exc)
            return False
        self._reported_broken_curated = False
        self._curated_schema = schema
        self._shell.stage.xml_editor.set_schema_model(schema.model)
        if self._feed_properties_schema is not None:
            self._feed_properties_schema(schema.model)
        return True

    def _warn_no_curated_schema(self, path: Path, exc: object) -> None:
        """The escalation beyond the audit panel, once per broken state.

        A `QMessageBox` and not a status-bar notice **on purpose**: since
        FQ-028 `shell.status` does not paint anything — `StaticStatusBar.
        showMessage` journals into the Activity Log and
        `displayed_message()` is permanently `""` — so "escalate to the status
        bar" would have moved the message from one journal to the same journal
        and left the bug exactly as reported.
        """
        if self._reported_broken_curated:
            return
        self._reported_broken_curated = True
        modals.QMessageBox.warning(
            self._shell.window,
            "Curated Schema Not Loaded",
            "The curated schema could not be read, so completion, hover and "
            "the Properties panel's labels have no schema behind them.\n\n"
            f"{path}\n\n{exc}\n\n"
            "Fix that file in Schema ▸ Edit XSD, or replace it with the schema "
            f"shipped with the app: Schema ▸ {RESTORE_BUNDLED_LABEL}",
        )

    def ensure_bootstrap(self) -> None:
        """One-time seed of the user's curated.xsd when it is absent — never
        overwrites an existing file (curated.xsd is hand-owned, spec §11).
        Prefers copying the schema bundled with the app (see
        `CURATED_BUNDLED_VERSION`); falls
        back to generating one from the learning engine's state only when no
        bundled resource is present."""
        curated = curated_xsd_path(self._schema_storage_dir)
        if curated.exists():
            return

        bundled = bundled_curated_xsd_text()
        if bundled is not None:
            try:
                curated.parent.mkdir(parents=True, exist_ok=True)
                curated.write_text(bundled, encoding="utf-8")
            except OSError as exc:
                self._shell.audit.addItem(
                    f"[Schema] Could not seed curated.xsd: {exc}"
                )
                return
            self._shell.audit.addItem(
                f"[Schema] Seeded curated.xsd from the bundled schema "
                f"(v{CURATED_BUNDLED_VERSION})"
            )
            return

        # Fallback: no bundled resource — generate from the learned model.
        model_path = schema_model_path(self._schema_storage_dir)
        if not model_path.exists():
            return
        try:
            model = Model.load(model_path)
            curated.parent.mkdir(parents=True, exist_ok=True)
            curated.write_text(generate_curated_xsd(model), encoding="utf-8")
        except Exception as exc:
            self._shell.audit.addItem(
                f"[Schema] Could not bootstrap curated.xsd: {exc}"
            )
            return
        self._shell.audit.addItem(
            "[Schema] Bootstrapped curated.xsd from the learned schema (labels preserved)"
        )

    def enrich_from_file(self, path) -> None:
        """Grow the learned model (and learned.xsd) from an opened .pgtp."""
        try:
            model_path = schema_model_path(self._schema_storage_dir)
            xsd_path = learned_xsd_path(self._schema_storage_dir)
            model_path.parent.mkdir(parents=True, exist_ok=True)

            if model_path.exists():
                model = Model.load(model_path)
            else:
                model = Model()

            events = []
            for elem_path, attrib, child_tag_counts, has_text in walk_document(path):
                events.extend(model.merge_element(elem_path, attrib, child_tag_counts, has_text))

            model.save(model_path)
            xsd_path.write_text(generate_xsd(model), encoding="utf-8")

            self.report_schema_events(events, path)
            _log.info("schema: enriched %s", path)

            self.ensure_bootstrap()
            if self._curated_schema is None:
                self.load_curated()
        except Exception as exc:
            self._shell.audit.addItem(
                f"[Schema] Could not update schema knowledge: {exc}"
            )

    def report_schema_events(self, events, source_path) -> None:
        """Audit-log what the last enrichment learned, collapsing to a single
        summary line past 20 events."""
        source_name = Path(source_path).name
        if len(events) > 20:
            self._shell.audit.addItem(
                f"[Schema] Learned {len(events)} new structural facts from {source_name}"
            )
            return
        for event in events:
            template = _SCHEMA_REPORT_TEMPLATES[event["kind"]]
            self._shell.audit.addItem(template.format(source=source_name, **event))

    # -- Edit XSD tab (spec §11) ---------------------------------------------

    def _on_xsd_text_changed(self) -> None:
        # A theme toggle's rehighlight() also fires textChanged with no text
        # actually changed; ignored via is_applying_theme() (see
        # XmlEditor.apply_theme_colors).
        if self._loading or self._shell.stage.xsd_editor.is_applying_theme():
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        stage = self._shell.stage
        base = self._tab_label(self._mode)
        stage.setTabText(stage.xsd_tab_index, f"{base} *" if dirty else base)

    @staticmethod
    def _tab_label(mode: str) -> str:
        """Tab title for the Edit-XSD tab in each mode (spec §11)."""
        return "Edit AutoXSD" if mode == "learned" else "Edit XSD"

    def _path_for_mode(self, mode: str) -> Path:
        """The on-disk file backing each Edit-XSD mode: the hand-curated
        schema, or the auto-learned discovery artifact (spec §11)."""
        if mode == "learned":
            return learned_xsd_path(self._schema_storage_dir)
        return curated_xsd_path(self._schema_storage_dir)

    def open_auto(self) -> None:
        """Schema ▸ Edit AutoXSD: open the auto-learned schema (learned.xsd)
        in the same tab so it can be analysed against the curated one."""
        self.open("learned")

    def open(self, mode: str = "curated") -> None:
        """Load the XSD file for `mode` ("curated" | "learned") into the shared
        Edit-XSD tab and switch to it. Unsaved edits in the current mode are
        preserved when re-opening the same mode; switching to the other mode
        prompts save/discard/cancel first (spec §11)."""
        stage = self._shell.stage
        if self._dirty and mode != self._mode:
            choice = self.confirm_close()
            if choice == "cancel":
                return
            if choice == "save":
                self.save()
                if self._dirty:
                    # Save failed (e.g. disk error): don't drop the edits.
                    return
        elif self._dirty and mode == self._mode:
            # Same schema, unsaved edits: keep them; just reveal the tab.
            stage.show_edit_xsd()
            return

        path = self._path_for_mode(mode)
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                self._shell.status(f"Could not read {path.name}: {exc}", 5000)
                return
        else:
            text = _EMPTY_XSD_SKELETON
            if mode == "learned":
                self._shell.status(
                    "No auto-learned schema yet — open a .pgtp to build it.", 5000
                )
        self._mode = mode
        self._loading = True
        try:
            stage.xsd_editor.setPlainText(text)
        finally:
            self._loading = False
        self._set_dirty(False)
        stage.show_edit_xsd()

    def on_close_requested(self) -> None:
        """Edit XSD tab ✕ clicked. Reuses `confirm_close`'s save/discard/
        cancel prompt (same pattern as `open`/the host's closeEvent) when
        dirty; never invents a second confirmation path."""
        if self._dirty:
            choice = self.confirm_close()
            if choice == "cancel":
                return
            if choice == "save":
                self.save()
                if self._dirty:
                    # Save failed (e.g. disk error): don't drop the edits.
                    return
        self._shell.stage.hide_edit_xsd()

    def confirm_close_for_exit(self) -> bool:
        """Resolve unsaved XSD edits on window close; False = abort the close.

        The host's ``closeEvent`` owns the ``QCloseEvent`` (and the project's
        own prompt); this answers only the §11 half of the question, so the
        save/discard/cancel logic is not duplicated on the host.
        """
        if not self._dirty:
            return True
        choice = self.confirm_close()
        if choice == "cancel":
            return False
        if choice == "save":
            self.save()
            if self._dirty:
                # Save failed (e.g. disk error) -- don't discard changes.
                return False
        return True

    # -- navigation ----------------------------------------------------------

    def goto_at_cursor(self) -> None:
        """Ctrl+L / context-menu "Go To XSD": resolve the caret in the Raw
        XML editor and jump to its curated XSD definition."""
        editor = self._shell.stage.xml_editor
        if editor.schema_model() is None or not editor.request_goto_xsd():
            self._shell.status(
                "Place the cursor inside an element in the Raw XML first.", 5000
            )

    def goto(self, tag_chain: str, attr: str) -> None:
        """Open the Edit XSD tab and select the attribute's definition;
        fall back to the element's type definition; else status message.
        Lines come from the last successful parse -- navigation targets the
        saved file content."""
        schema = self._curated_schema
        if schema is None:
            self._shell.status(
                "No curated XSD loaded yet — Schema ▸ Edit XSD.", 5000
            )
            return
        line = schema.attribute_lines.get((tag_chain, attr))
        if line is None:
            line = schema.element_lines.get(tag_chain)
        if line is None:
            self._shell.status(
                f"'{tag_chain}' is not in the curated XSD yet.", 5000
            )
            return
        self.open()
        self._shell.stage.xsd_editor.navigate_to_line(line)

    def reveal_line(self, line: int, mode: str | None = None) -> None:
        """Show the Edit-XSD tab with the caret on `line`.

        `mode` re-opens that schema first, so a Verify finding's line number
        matches the file it was found in (same load-from-disk-if-clean behavior
        as Schema ▸ Edit XSD / Edit AutoXSD). Falsy `mode` (a Find-All-in-XSD
        hit, which carries no mode tag) targets whatever the tab already shows.
        """
        if mode:
            self.open(mode)
        else:
            self._shell.stage.show_edit_xsd()
        self._shell.stage.xsd_editor.navigate_to_line(line)

    # -- save / verify / export / import -------------------------------------

    def save(self) -> None:
        """Save the Edit-XSD tab to whichever schema it currently holds
        (curated or auto). The text is ALWAYS written (user text is never
        lost); a malformed file keeps the last good schema live. Saving the
        curated schema re-feeds completion; saving the auto schema does not
        (learned.xsd never feeds completion, spec §11)."""
        mode = self._mode
        path = self._path_for_mode(mode)
        text = self._shell.stage.xsd_editor.toPlainText()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window, "Save Failed", f"Could not save:\n\n{exc}"
            )
            return
        self._set_dirty(False)
        self._shell.status(f"Saved {path.name}", 5000)
        if mode == "curated":
            self.load_curated()
        self._report_verify_issues(verify_curated(text))

    def verify(self) -> None:
        """Schema ▸ Verify XSD: check dialect rules against whatever the user
        is currently looking at -- the Edit-XSD tab's live text when it has
        unsaved edits, otherwise the active mode's saved file on disk."""
        stage = self._shell.stage
        if self._dirty:
            text = stage.xsd_editor.toPlainText()
        else:
            path = self._path_for_mode(self._mode)
            if not path.exists():
                self._shell.status(
                    f"No {self._tab_label(self._mode)} file yet.", 5000
                )
                return
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                self._shell.status(f"Could not read {path.name}: {exc}", 5000)
                return
        self._report_verify_issues(verify_curated(text))

    def export(self) -> None:
        """Schema ▸ Export XSD: copy the active mode's saved file to a chosen
        destination (curated.xsd or learned.xsd, per the open tab)."""
        mode = self._mode
        source = self._path_for_mode(mode)
        if not source.exists():
            self._shell.status(f"No {self._tab_label(mode)} file yet.", 5000)
            return
        if self._dirty:
            self._shell.status(
                "The XSD tab has unsaved changes — save it first "
                "(Deployment ▸ Save XSD).",
                5000,
            )
            return
        default_dir = self._shell.default_dir
        dest, _filter = modals.QFileDialog.getSaveFileName(
            self._shell.window,
            "Export XSD",
            str(Path(default_dir()) / source.name) if default_dir() else source.name,
            "XSD files (*.xsd)",
        )
        if not dest:
            return
        try:
            shutil.copyfile(source, dest)
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window, "Export Failed", f"Could not export:\n\n{exc}"
            )
            return
        self._shell.status(f"Exported to {Path(dest).name}", 5000)

    def import_(self) -> None:
        """Schema ▸ Import XSD: replace the active mode's file with an external
        one -- verify first (hard refuse malformed XML; dialect warnings
        importable), back up, replace, then re-feed completion when the active
        mode is curated (spec §11)."""
        mode = self._mode
        source, _filter = modals.QFileDialog.getOpenFileName(
            self._shell.window,
            "Import XSD",
            self._shell.default_dir(),
            "XSD files (*.xsd);;All files (*)",
        )
        if not source:
            return
        try:
            text = Path(source).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            modals.QMessageBox.critical(
                self._shell.window, "Import Failed", f"Could not read:\n\n{exc}"
            )
            return
        issues = verify_curated(text)
        if any(issue.fatal for issue in issues):
            modals.QMessageBox.critical(
                self._shell.window, "Import Refused",
                "The file is not well-formed XML:\n\n" + issues[0].message,
            )
            return
        if issues:
            answer = modals.QMessageBox.question(
                self._shell.window, "Import With Warnings",
                f"The file has {len(issues)} dialect warning(s). Import anyway?",
                modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
            )
            if answer != modals.QMessageBox.StandardButton.Yes:
                return
        tab_was_dirty = self._dirty
        target = self._path_for_mode(mode)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.copy2(target, str(target) + ".bak")
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window, "Import Failed", f"Could not write:\n\n{exc}"
            )
            return
        self._set_dirty(False)
        if mode == "curated":
            self.load_curated()
        stage = self._shell.stage
        if stage.xsd_editor.toPlainText():
            self._loading = True
            try:
                stage.xsd_editor.setPlainText(text)
            finally:
                self._loading = False
        label = self._tab_label(mode)
        notice = f"[Schema] Imported {label} from {Path(source).name}"
        if tab_was_dirty:
            notice += " (unsaved XSD tab edits were replaced)"
        self._shell.audit.addItem(notice)
        self._report_verify_issues(issues)

    def restore_bundled(self) -> None:
        """Schema ▸ Restore Bundled Curated Schema…: overwrite the user's
        app-data ``curated.xsd`` with the copy shipped inside the app, then
        re-feed completion.

        **This is the one sanctioned exception to §11's "curated.xsd is
        hand-owned and never overwritten" (BUG-260812002307 part C.)** The rule
        itself is untouched — `ensure_bootstrap` still refuses to overwrite,
        because it runs unattended at startup and must never eat a hand
        curation. This is the opposite situation: the user asked for it by name
        and confirmed a prompt that says what is destroyed. Without it, a
        corrupted app-data copy is unrecoverable from inside the app, since the
        pristine bundled resource is never re-read once a file exists.

        Mirrors `import_` for the write-then-reload half, including its `.bak`
        beside the replaced file.
        """
        path = curated_xsd_path(self._schema_storage_dir)
        bundled = bundled_curated_xsd_text()
        if bundled is None:
            modals.QMessageBox.critical(
                self._shell.window,
                "No Bundled Schema",
                "This build does not carry a bundled curated schema, so there "
                "is nothing to restore from.",
            )
            return
        answer = modals.QMessageBox.question(
            self._shell.window,
            "Restore Bundled Curated Schema",
            f"Replace\n\n{path}\n\nwith the curated schema shipped with the "
            f"app (v{CURATED_BUNDLED_VERSION})?\n\n"
            "Every hand edit in that file will be DESTROYED. A .bak copy is "
            "kept beside it.",
            modals.QMessageBox.StandardButton.Yes | modals.QMessageBox.StandardButton.No,
        )
        if answer != modals.QMessageBox.StandardButton.Yes:
            return
        tab_was_dirty = self._dirty and self._mode == "curated"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                shutil.copy2(path, str(path) + ".bak")
            path.write_text(bundled, encoding="utf-8")
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window,
                "Restore Failed",
                f"Could not write the curated schema:\n\n{exc}",
            )
            return
        # A freshly written file is a new chance for the "no schema at all"
        # warning to be useful, so the once-per-broken-state latch is dropped
        # here as well as on a successful load.
        self._reported_broken_curated = False
        self.load_curated()
        if self._mode == "curated":
            self._loading = True
            try:
                self._shell.stage.xsd_editor.setPlainText(bundled)
            finally:
                self._loading = False
            self._set_dirty(False)
        notice = (
            f"[Schema] Restored curated.xsd from the bundled schema "
            f"(v{CURATED_BUNDLED_VERSION}) — {path}"
        )
        if tab_was_dirty:
            notice += " (unsaved XSD tab edits were replaced)"
        self._shell.audit.addItem(notice)

    # -- reporting -----------------------------------------------------------

    def _report_verify_issues(self, issues) -> None:
        """Append Verify XSD results to the audit panel. Each issue line is
        clickable -- routed through the host's `_on_audit_item_clicked`
        (line, target) UserRole/UserRole+1 convention, with target "xsd" so
        the click opens the Edit XSD tab at that line. The active XSD mode is
        stashed in UserRole+2 so the click re-opens the schema the issue was
        found in (curated vs auto)."""
        audit = self._shell.audit
        # FQ-028: Verify results ACCUMULATE in the Messages tab, so each run
        # opens its own separated block instead of merging into the last one.
        begin_run = getattr(audit, "begin_results_run", None)
        if begin_run is not None:
            begin_run()
        if not issues:
            audit.addItem("[Schema] VERIFY: no issues found.")
            return
        for issue in issues:
            item = QListWidgetItem(f"[Schema] VERIFY line {issue.line}: {issue.message}")
            item.setData(Qt.ItemDataRole.UserRole, issue.line)
            item.setData(Qt.ItemDataRole.UserRole + 1, "xsd")
            item.setData(Qt.ItemDataRole.UserRole + 2, self._mode)
            audit.addItem(item)

    def _confirm_close_xsd(self) -> str:
        """Ask the user how to resolve unsaved Edit XSD changes before
        closing. Returns "save", "discard", or "cancel". Reached through the
        replaceable `confirm_close` attribute so tests never drive a real
        modal."""
        result = modals.QMessageBox.question(
            self._shell.window,
            "Unsaved Changes",
            "The XSD has unsaved changes. Save before closing?",
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.Discard
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if result == modals.QMessageBox.StandardButton.Save:
            return "save"
        if result == modals.QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"
