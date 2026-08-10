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

# pgtp_editor/ui/snippet_controller.py
"""The snippet lane (FQ-030): the store's LOCATION, and the gestures over it.

Three jobs, and nothing else:

1. **Where the file is.** `sql/snippet_store.py` is Qt-free and takes a `Path`;
   resolving that path is the one part that needs app knowledge, so it is here.
2. **Loading it at startup and pushing the result into the editors**, so a
   saved snippet is live in every SQL editor without a restart.
3. **`Schema ▸ Edit Snippets…` and its Export / Import**, including the
   collision question, which is the only modal in this lane.

WHERE THE STORE LIVES, AND WHY THAT DIRECTORY
---------------------------------------------
`snippets.json` sits in the application's per-user data directory — the same
folder that already holds `generator_config.json` (§19/§22) and the learned
schema (`schema_learning/storage.py`), resolved the same way
(`QStandardPaths.AppDataLocation`, overridable by an injected `base_dir`).

That is the concrete reading of DEC-001's *"the software's folder, editable by
the users"*: the app already HAS a per-user folder and the user already has
reason to visit it, so a snippet store there is findable, while a new
convention invented for one feature would not be. It is deliberately **not**:

- **inside the `.pgtp` project** — DEC-001's core ruling. The project is a
  movable artifact; a typing shortcut is not part of the schema and must not
  ride along with it.
- **a key inside `generator_config.json`** — sharing is a file you send a
  colleague, and burying snippets in a config file that also holds this
  machine's executable paths would make export a *transformation* rather than a
  copy. A separate file means the store and the export format are literally the
  same file.
- **QSettings** — an INI whose values are multi-line SQL bodies is not
  "editable by the users" in any real sense, and it has no natural share unit.

THE `config_dir` INJECTION IS NOT OPTIONAL DECORATION
-----------------------------------------------------
`config_dir` is `MainWindow`'s existing `generator_config_dir` — the SAME
override §22 reuses from §19, never a second one. Under test it is a
`tmp_path`, which is what keeps the suite from writing snippets into the
developer's real config directory. A test that reaches the real folder is a
defect, so nothing here ever calls `_app_data_dir()` when a `config_dir` was
given.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths

from pgtp_editor.sql.snippet_store import (
    SNIPPETS_FILENAME,
    apply_import,
    load_snippets,
    parse_snippets,
    plan_import,
    save_snippets,
)
from pgtp_editor.sql.templates import DEFAULT_SNIPPETS
from pgtp_editor.ui import modals
from pgtp_editor.ui.edit_snippets_dialog import EditSnippetsDialog

#: The audit prefix this lane reports under (§ house style: one prefix per lane).
_PREFIX = "[Snippets] "

_JSON_FILTER = "Snippet files (*.json);;All files (*)"


def snippets_path(base_dir: Path | None = None) -> Path:
    """Where the one per-user store lives. `base_dir` is the test override."""
    if base_dir is None:
        base_dir = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
        )
    return Path(base_dir) / SNIPPETS_FILENAME


class SnippetController(QObject):
    """Owns the snippet set in force and the `Schema ▸ Edit Snippets…` gesture."""

    def __init__(
        self,
        shell,
        parent: QObject | None = None,
        *,
        config_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._shell = shell
        self._config_dir = config_dir
        self._snippets = DEFAULT_SNIPPETS
        self._load_error: str | None = None
        self._dialog: EditSnippetsDialog | None = None

    # -- read-only surface ---------------------------------------------------

    @property
    def path(self) -> Path:
        return snippets_path(self._config_dir)

    def snippets(self):
        """The set in force — the shipped defaults until a store is loaded."""
        return self._snippets

    def load_error(self) -> str | None:
        """Why the store on disk was not used, or None. Non-None means the lane
        is READ-ONLY: see `sql/snippet_store.py` on why a file we could not
        parse must not be written over."""
        return self._load_error

    def dialog(self) -> EditSnippetsDialog | None:
        """The open editor, or None (tests drive it through this)."""
        return self._dialog

    # -- startup -------------------------------------------------------------

    def load(self) -> None:
        """Read the store and push it into the editors. Never raises.

        Called once at startup. A missing file is the normal fresh-install
        state and says nothing; a broken one says so exactly once, in the audit
        log, naming the file so the user can go fix it by hand — which is the
        whole point of a human-editable format.
        """
        loaded = load_snippets(self.path)
        self._snippets = loaded.snippets
        self._load_error = loaded.error
        if loaded.error:
            self._audit(
                f"{self.path} {loaded.error} — the built-in snippets are in "
                "force and the file will not be overwritten."
            )
        self.apply()

    def apply(self) -> None:
        """Install the set in force on every SQL editor, now and future.

        Routed through `CenterStage.set_snippets` rather than reaching for
        editors here: the stage is the one place SQL panels are created, so it
        is the only place that can serve tabs opened *later* as well as the
        ones open now.
        """
        stage = getattr(self._shell, "stage", None)
        setter = getattr(stage, "set_snippets", None)
        if callable(setter):
            setter(self._snippets)

    # -- Schema ▸ Edit Snippets… ---------------------------------------------

    def open_editor(self) -> EditSnippetsDialog:
        """Show the editor (single-instance, non-modal, house style).

        Non-modal because the user's reason for opening it is usually a snippet
        they just wanted while writing SQL, and a modal would hide the very
        code they are copying the body out of.
        """
        if self._dialog is not None:
            self._dialog.raise_()
            self._dialog.activateWindow()
            return self._dialog

        note = ""
        if self._load_error:
            note = (
                f"{self.path.name} {self._load_error}. The built-in snippets "
                "are shown; saving is disabled so your file is not overwritten "
                "— fix or move it, then reopen the application."
            )
        dialog = EditSnippetsDialog(
            self._snippets,
            self._shell.window,
            read_only=bool(self._load_error),
            note=note,
        )
        dialog.accepted.connect(self._on_accepted)
        dialog.finished.connect(self._on_finished)
        dialog.export_requested.connect(self._on_export)
        dialog.import_requested.connect(self._on_import)
        self._dialog = dialog
        dialog.show()
        return dialog

    def _on_finished(self, _result) -> None:
        self._dialog = None

    def _on_accepted(self) -> None:
        dialog = self._dialog
        if dialog is None:
            return
        self.save(dialog.result_snippets())

    def save(self, snippets) -> bool:
        """Persist `snippets` as the store and make them live. Reports failure.

        Refuses outright while the store is unreadable — the one rule that
        makes a corrupt file recoverable instead of fatal.
        """
        if self._load_error:
            self._audit(
                "Not saving: the existing store could not be read, and "
                "overwriting it would lose whatever it holds."
            )
            return False
        snippets = tuple(snippets)
        try:
            save_snippets(self.path, snippets)
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window,
                "Could Not Save Snippets",
                f"Could not write {self.path}:\n\n{exc}",
            )
            return False
        self._snippets = snippets
        self.apply()
        self._audit(f"Saved {len(snippets)} snippet(s) to {self.path}")
        self._shell.status(f"Saved {len(snippets)} snippet(s).", 5000)
        return True

    # -- export / import -----------------------------------------------------
    #
    # Both gestures live on the editor rather than on the menu, because both
    # are about a SET the user is looking at: export writes the rows as they
    # currently stand (edits included, without needing to save first) and
    # import lands in the same rows, so the result is reviewable before OK
    # commits it. That also means an import is undoable by pressing Cancel —
    # which matters much more than menu convenience, given the collision rule.

    def _on_export(self) -> None:
        dialog = self._dialog
        if dialog is None:
            return
        default_dir = self._shell.default_dir()
        target, _filter = modals.QFileDialog.getSaveFileName(
            self._shell.window,
            "Export Snippets",
            str(Path(default_dir) / SNIPPETS_FILENAME)
            if default_dir
            else SNIPPETS_FILENAME,
            _JSON_FILTER,
        )
        if not target:
            return
        snippets = dialog.result_snippets()
        try:
            save_snippets(Path(target), snippets)
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window, "Export Failed", f"Could not write:\n\n{exc}"
            )
            return
        dialog.show_message(
            f"Exported {len(snippets)} snippet(s) to {Path(target).name}."
        )
        self._audit(f"Exported {len(snippets)} snippet(s) to {target}")

    def _on_import(self) -> None:
        """Read a file into the open editor's rows, asking about collisions.

        THE COLLISION RULE, as the user meets it: snippets whose trigger word
        is new are added; snippets whose trigger word already exists are
        **never** applied without an explicit Yes. The question names them, and
        No still imports the new ones — so a colleague's file is useful even
        when part of it clashes, and nothing the user wrote is replaced behind
        their back.
        """
        dialog = self._dialog
        if dialog is None:
            return
        source, _filter = modals.QFileDialog.getOpenFileName(
            self._shell.window,
            "Import Snippets",
            self._shell.default_dir(),
            _JSON_FILTER,
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
        loaded = parse_snippets(text)
        if loaded.error:
            modals.QMessageBox.critical(
                self._shell.window,
                "Import Refused",
                f"{Path(source).name} {loaded.error}.",
            )
            return

        current = dialog.result_snippets()
        plan = plan_import(current, loaded.snippets)
        if plan.is_empty:
            dialog.show_message(f"{Path(source).name} holds no snippets.")
            return

        overwrite = False
        if plan.colliding:
            names = ", ".join(s.prefix for s in plan.colliding)
            answer = modals.QMessageBox.question(
                self._shell.window,
                "Trigger Words Already Exist",
                f"{len(plan.colliding)} imported snippet(s) use a trigger word "
                f"you already have:\n\n{names}\n\n"
                "Replace yours with the imported ones?\n"
                "No keeps yours and imports only the "
                f"{len(plan.added)} new one(s).",
                modals.QMessageBox.StandardButton.Yes
                | modals.QMessageBox.StandardButton.No
                | modals.QMessageBox.StandardButton.Cancel,
            )
            if answer == modals.QMessageBox.StandardButton.Cancel:
                dialog.show_message("Import cancelled — nothing changed.")
                return
            overwrite = answer == modals.QMessageBox.StandardButton.Yes

        dialog.set_snippets(apply_import(current, loaded.snippets, overwrite=overwrite))
        kept = 0 if overwrite else len(plan.colliding)
        summary = (
            f"Imported {len(plan.added)} new snippet(s) from "
            f"{Path(source).name}"
        )
        if plan.colliding:
            summary += (
                f", replaced {len(plan.colliding)}"
                if overwrite
                else f", kept your {kept} existing one(s)"
            )
        summary += ". Press OK to save."
        dialog.show_message(summary)
        self._audit(summary)

    # -- internals -----------------------------------------------------------

    def _audit(self, text: str) -> None:
        audit = getattr(self._shell, "audit", None)
        if audit is not None:
            audit.addItem(_PREFIX + text)
