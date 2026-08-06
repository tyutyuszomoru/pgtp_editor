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
"""The Compare / Merge lane (spec §7): the three entry points that fill the
Diff/Merge tab and the one gesture that writes the result back out.

What it owns
------------
* the **three comparison entry points** — whole-project
  (:meth:`compare_two_files`, Tools ▸ Compare / Merge Two Files…), one page
  (:meth:`compare_page_with`, the project tree's right-click) and one detail
  (:meth:`compare_detail_with`, likewise) — each of which picks a target
  ``.pgtp``, diffs against it, shows the differences in ``DiffMergePanel`` and
  raises the Diff/Merge tab;
* the **comparison target** those three establish and
  :meth:`apply_changes_to_target` consumes: :attr:`target_project` (the parsed
  model) and :attr:`target_path` (its path on disk). Nothing else in the app has
  a use for these, which is why they moved here wholesale;
* **Apply Changes to Target** (:meth:`apply_changes_to_target`): the ambiguity
  gate (§7.3 — positionally-paired duplicate siblings can never be applied
  blind), the deep-copy-and-apply onto a working tree so a partial failure
  writes nothing, the ``.bak`` beside the target, the serialize + write, and the
  reload of the just-written file.

Why the write path deep-copies first
------------------------------------
:meth:`apply_changes_to_target` applies onto ``copy.deepcopy(target.tree)``, not
onto the tracked target model, and bails out **before** touching the disk if any
difference fails. That is what makes the gesture all-or-nothing: a failure leaves
both the file and the in-memory comparison exactly as they were, so the user can
uncheck and retry against the same diff. Keep the copy.

Needs
-----
The shell covers the stage (``diff_merge_panel``, the tab index), the status bar,
the Open-dialog default directory, and the dialog parent. Two things it cannot
cover arrive injected:

* ``project()`` — the open project model, used as the *source* of a whole-project
  comparison when one is loaded (otherwise the user is prompted for a source file
  as well).
* ``reload(path)`` — re-open the file just written, so the editor shows what is
  now on disk. Points at the host's public ``open_project_file``, which stays on
  the host (``main.py`` calls it) and delegates to the document controller in a
  later wave; injecting it means only that one host wiring line changes then.

Shape
-----
A ``QObject`` following ``ui/xsd_controller.py``: it takes a
:class:`~pgtp_editor.ui.ui_shell.UiShell`, constructs headless, and never
dereferences ``shell.window`` (which appears solely as a dialog parent for the
``ui/modals`` statics).
"""
from __future__ import annotations

import copy
import shutil
from collections.abc import Callable

from lxml import etree
from PySide6.QtCore import QObject

from pgtp_editor.diff.apply import apply_differences
from pgtp_editor.diff.differ import compare_block, diff_project
from pgtp_editor.diff.resolve import ResolutionError, resolve_path
from pgtp_editor.model.parser import _build_project_model, load_project
from pgtp_editor.ui import modals
from pgtp_editor.ui.ui_shell import UiShell


class DiffMergeController(QObject):
    """Owns the three Compare entry points, the comparison target they set, and
    Apply Changes to Target."""

    def __init__(
        self,
        shell: UiShell,
        parent: QObject | None = None,
        *,
        project: Callable[[], object | None],
        reload: Callable[[str], None],
    ):
        super().__init__(parent)
        self._shell = shell
        #: The open project (comparison source when one is loaded) and the
        #: re-open of a just-written target -- see the module docstring.
        self._project = project
        self._reload = reload

        #: The comparison target the three Compare gestures establish and Apply
        #: consumes. None until a comparison has run.
        self._current_diff_target_project = None
        self._current_diff_target_path = None

    # -- read-only surface ---------------------------------------------------

    @property
    def target_project(self):
        """The parsed model of the last comparison target, or None."""
        return self._current_diff_target_project

    @property
    def target_path(self):
        """The path of the last comparison target, or None."""
        return self._current_diff_target_path

    # -- the three comparison entry points -----------------------------------

    def compare_two_files(self) -> None:
        """Tools ▸ Compare / Merge Two Files…: diff the open project (or, with
        nothing open, a source file the user picks) against a target."""
        source = self._project()
        if source is None:
            source_path, _filter = modals.QFileDialog.getOpenFileName(
                # The ONE sanctioned use of shell.window: a dialog parent.
                self._shell.window,
                "Select Source Project",
                self._shell.default_dir(),
                "PGTP files (*.pgtp)",
            )
            if not source_path:
                return
            try:
                source = load_project(source_path)
            except Exception as exc:
                modals.QMessageBox.critical(
                    self._shell.window,
                    "Failed to Open Source Project",
                    f"Could not open '{source_path}':\n\n{exc}",
                )
                return

        target_path, _filter = modals.QFileDialog.getOpenFileName(
            self._shell.window,
            "Select Target Project",
            self._shell.default_dir(),
            "PGTP files (*.pgtp)",
        )
        if not target_path:
            return
        try:
            target = load_project(target_path)
        except Exception as exc:
            modals.QMessageBox.critical(
                self._shell.window,
                "Failed to Open Target Project",
                f"Could not open '{target_path}':\n\n{exc}",
            )
            return

        self._current_diff_target_project = target
        self._current_diff_target_path = target_path
        differences = diff_project(source, target)
        stage = self._shell.stage
        stage.diff_merge_panel.show_differences(differences)
        stage.setCurrentIndex(stage.diff_merge_tab_index)

    def compare_page_with(self, page_node) -> None:
        """Project tree ▸ right-click on a Page: diff it against the same
        ``fileName`` in a target project."""
        target_path, _filter = modals.QFileDialog.getOpenFileName(
            self._shell.window,
            "Select Target Project",
            self._shell.default_dir(),
            "PGTP files (*.pgtp)",
        )
        if not target_path:
            return
        try:
            target = load_project(target_path)
        except Exception as exc:
            modals.QMessageBox.critical(
                self._shell.window,
                "Failed to Open Target Project",
                f"Could not open '{target_path}':\n\n{exc}",
            )
            return

        target_page = next((p for p in target.pages if p.file_name == page_node.file_name), None)
        if target_page is None:
            modals.QMessageBox.critical(
                self._shell.window,
                "Page Not Found",
                f"No Page with fileName '{page_node.file_name}' exists in '{target_path}'.",
            )
            return

        self._current_diff_target_project = target
        self._current_diff_target_path = target_path
        differences = compare_block(page_node, target_page, path=[page_node.file_name], node_kind="page")
        stage = self._shell.stage
        stage.diff_merge_panel.show_differences(differences)
        stage.setCurrentIndex(stage.diff_merge_tab_index)

    def compare_detail_with(self, detail_node, source_path) -> None:
        """Project tree ▸ right-click on a Detail: resolve the same structural
        path in a target project and diff the two blocks."""
        target_path_str, _filter = modals.QFileDialog.getOpenFileName(
            self._shell.window,
            "Select Target Project",
            self._shell.default_dir(),
            "PGTP files (*.pgtp)",
        )
        if not target_path_str:
            return
        try:
            target = load_project(target_path_str)
        except Exception as exc:
            modals.QMessageBox.critical(
                self._shell.window,
                "Failed to Open Target Project",
                f"Could not open '{target_path_str}':\n\n{exc}",
            )
            return

        result = resolve_path(target, source_path)
        if isinstance(result, ResolutionError):
            modals.QMessageBox.critical(
                self._shell.window, "Detail Not Found", result.message
            )
            return

        self._current_diff_target_project = target
        self._current_diff_target_path = target_path_str
        differences = compare_block(detail_node, result, path=source_path, node_kind="detail")
        stage = self._shell.stage
        stage.diff_merge_panel.show_differences(differences)
        stage.setCurrentIndex(stage.diff_merge_tab_index)

    # -- the write path ------------------------------------------------------

    def apply_changes_to_target(self) -> None:
        panel = self._shell.stage.diff_merge_panel
        checked = panel.checked_differences()
        if not checked:
            modals.QMessageBox.information(
                self._shell.window,
                "Apply Changes to Target",
                "No differences are checked to apply.",
            )
            return

        ambiguous = [d for d in checked if d.ambiguous]
        if ambiguous:
            details = "\n".join(
                f"- {'/'.join(d.path)} ({d.node_kind}/{d.attribute}: {d.kind})" for d in ambiguous
            )
            modals.QMessageBox.critical(
                self._shell.window,
                "Cannot Apply: Ambiguous Differences Checked",
                "The following checked differences are ambiguous (matched via "
                "positional pairing of duplicate siblings) and cannot be safely "
                "applied automatically. Uncheck them and re-run Apply, or verify "
                "the pairing by hand in the detail view first:\n\n" + details,
            )
            return

        target_project = self._current_diff_target_project
        target_path = self._current_diff_target_path

        working_tree = copy.deepcopy(target_project.tree)
        working_project = _build_project_model(working_tree, source_description=target_path)
        result = apply_differences(working_project, checked)

        if result.failed:
            details = "\n".join(f"- {'/'.join(f.difference.path)}: {f.message}" for f in result.failed)
            modals.QMessageBox.critical(
                self._shell.window,
                "Apply Failed -- No Changes Written",
                f"{len(result.failed)} of {len(checked)} checked differences could not "
                f"be applied (Target may have changed since this comparison was run). "
                f"No changes were written to '{target_path}'.\n\n" + details,
            )
            return

        backup_path = target_path + ".bak"
        shutil.copy2(target_path, backup_path)
        serialized = etree.tostring(
            working_tree, xml_declaration=False, encoding="UTF-8", pretty_print=False
        )
        with open(target_path, "wb") as f:
            f.write(serialized)

        modals.QMessageBox.information(
            self._shell.window,
            "Apply Changes to Target",
            f"Applied {len(checked)} change(s) to '{target_path}'.\nBackup saved to '{backup_path}'.",
        )
        self._reload(target_path)
