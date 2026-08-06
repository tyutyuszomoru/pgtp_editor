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
"""The generation lane: the Generation menu, the vendor PHP Generator run, and
panGen / rePHPgen (our own generator plus its gap analysis).

What it owns
------------
Everything about *turning the open project into PHP* and nothing else:

* the **Generation menu** (Locate PHP Generator Executable / Generate PHP /
  Open Output Folder / Locate panGen Runtime / panGen / rePHPgen / Save reJSON)
  — a menu owned outright by one collaborator moves with it, so this lane builds
  it;
* the vendor-executable and re_phpgen-runtime locations on disk (read and
  written through ``generation/config.py`` under :attr:`config_dir`);
* the single in-flight run: the injected :attr:`runner`, the
  :attr:`is_generating` guard that keeps a second run from orphaning the first
  ``QProcess``, and the ``[PHP]``-prefixed Audit lines the run streams;
* the last output folder (:attr:`output_folder`, what Open Output Folder
  reveals) and the last gap JSON (:attr:`last_gap_json`, what Save reJSON
  copies) plus the Save reJSON action's enabled state.

The first lane that consumes document state
-------------------------------------------
Unlike the toolbar and schema lanes, generation genuinely needs the open
project: the generator reads the ``.pgtp`` **from disk**, so every run must save
first, and the command line is built from the project's path. That state does not
belong here and is not reachable through :class:`~pgtp_editor.ui.ui_shell.UiShell`
either, so it arrives as four injected **providers** rather than as a reference
to whoever currently holds it:

* ``project()`` — the parsed project model, or ``None``; only ever truth-tested
  (is anything open?) and read for ``Project@outputPath``.
* ``project_path()`` — the ``.pgtp``'s path on disk, or falsy.
* ``ensure_saved(save_as)`` — run the project's Save (or Save As) and answer
  whether the project now exists on disk. The **prompt** stays here (its wording
  differs between Generate PHP and panGen), only the saving is delegated.
* ``default_output_dir()`` — the active §18.2 local project folder, or ``""``.
  Injected rather than read off a DDL attribute so this lane never learns that
  §18.2 exists; it only knows "the host may suggest a folder".

Today the host wires all four at its own state. When ``PgtpDocumentController``
lands, only those wiring lines move — this module does not change, does not
import it, and must not anticipate it. That is the whole point of the
indirection.

Writable seams are ATTRIBUTES/setters
-------------------------------------
:attr:`is_generating` and :attr:`last_gap_json` are settable properties, not
read-only ones, because the suite ASSIGNS them to set up a state a real run
would take a subprocess to reach (an in-flight run, a previously produced gap
JSON). Keep them assignable.

Shape
-----
A ``QObject`` following ``ui/xsd_controller.py``: it takes a ``UiShell``,
constructs headless, and never dereferences ``shell.window`` (which appears
solely as a dialog parent for the ``ui/modals`` statics).
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QUrl

from pgtp_editor.generation.config import (
    generator_config_path,
    load_executable_path,
    load_re_phpgen_root,
    save_executable_path,
    save_re_phpgen_root,
)
from pgtp_editor.generation.gap_summary import summarize_gap_json
from pgtp_editor.generation.re_runner import (
    PANGEN_SUBFOLDER,
    build_analyze_command,
    build_pangen_command,
    resolve_re_phpgen_python,
    validate_re_phpgen_root,
)
from pgtp_editor.generation.runner import GeneratorRunner, build_generate_command
from pgtp_editor.ui import modals
from pgtp_editor.ui.file_filters import executable_filter
from pgtp_editor.ui.ui_shell import UiShell

_log = logging.getLogger(__name__)

#: Audit prefix every generator line carries, so `_clear_generator_output` can
#: drop this lane's rows without touching [Find]/[Schema]/[Check] ones.
GENERATOR_OUTPUT_PREFIX = "[PHP] "


class GenerationController(QObject):
    """Owns the Generation menu and every PHP-generation run."""

    def __init__(
        self,
        shell: UiShell,
        config_dir: Path | None = None,
        parent: QObject | None = None,
        *,
        runner=None,
        project: Callable[[], object | None],
        project_path: Callable[[], str | None],
        ensure_saved: Callable[[bool], bool],
        default_output_dir: Callable[[], str],
    ):
        super().__init__(parent)
        self._shell = shell
        #: Root the generator/runtime locations are read from and written to
        #: (``None`` = the real per-user location, resolved by
        #: `generation/config.py`). Handed over by the host, which keeps it as
        #: its injectable constructor seam because the §22 lint lane reads the
        #: same directory.
        self._config_dir = config_dir
        #: The process runner (injectable so tests never spawn a real process).
        self._runner = runner if runner is not None else GeneratorRunner()
        #: Document-state providers -- see the module docstring.
        self._project = project
        self._project_path = project_path
        self._ensure_saved = ensure_saved
        self._default_output_dir = default_output_dir
        # The folder the last run wrote into (what Open Output Folder reveals).
        self._current_output_folder = None
        # One run at a time: a second start would orphan the first QProcess.
        self._is_generating = False
        # The last gap JSON rePHPgen produced, what Save reJSON copies.
        self._last_gap_json: Path | None = None
        #: The Save reJSON menu action, created by `build_menu` and enabled only
        #: once a gap analysis has succeeded.
        self._save_rejson_action = None

    # -- read/write surface --------------------------------------------------

    @property
    def config_dir(self) -> Path | None:
        """Root of the generator config, as handed over by the host."""
        return self._config_dir

    @property
    def runner(self):
        """The process runner this lane drives."""
        return self._runner

    @property
    def output_folder(self):
        """The folder the last run wrote into, or None before any run."""
        return self._current_output_folder

    @property
    def save_rejson_action(self):
        """The Save reJSON ``QAction`` (None before :meth:`build_menu`)."""
        return self._save_rejson_action

    @property
    def is_generating(self) -> bool:
        """Whether a run is in flight.

        Writable: the suite assigns it to stage an in-flight run without
        spawning a process (see the module docstring).
        """
        return self._is_generating

    @is_generating.setter
    def is_generating(self, value: bool) -> None:
        self._is_generating = bool(value)

    @property
    def last_gap_json(self) -> Path | None:
        """The last gap JSON rePHPgen produced, or None.

        Writable: the suite assigns a hand-written JSON to exercise Save reJSON
        without running the analyzer.
        """
        return self._last_gap_json

    @last_gap_json.setter
    def last_gap_json(self, value) -> None:
        self._last_gap_json = value

    # -- construction --------------------------------------------------------

    def build_menu(self, menu_bar) -> None:
        """Add the Generation menu to `menu_bar`."""
        menu = menu_bar.addMenu("Generation")
        locate_action = menu.addAction("Locate PHP Generator Executable...")
        locate_action.triggered.connect(self.locate_generator)
        menu.addSeparator()
        generate_action = menu.addAction("Generate PHP...")
        generate_action.triggered.connect(self.generate_php)
        menu.addSeparator()
        open_output_action = menu.addAction("Open Output Folder")
        open_output_action.triggered.connect(self.open_output_folder)
        menu.addSeparator()
        locate_pangen_action = menu.addAction("Locate panGen Runtime...")
        locate_pangen_action.triggered.connect(self.locate_pangen_runtime)
        pangen_action = menu.addAction("panGen (Generate Own PHP)")
        pangen_action.triggered.connect(self.pangen)
        re_phpgen_action = menu.addAction("rePHPgen (Analyze Gap)")
        re_phpgen_action.triggered.connect(self.analyze_gap)
        self._save_rejson_action = menu.addAction("Save reJSON...")
        self._save_rejson_action.triggered.connect(self.save_rejson)
        self._save_rejson_action.setEnabled(False)

    # -- the vendor PHP Generator --------------------------------------------

    def locate_generator(self) -> None:
        path, _filter = modals.QFileDialog.getOpenFileName(
            self._shell.window,
            "Locate PHP Generator Executable",
            "",
            executable_filter(),
        )
        if not path:
            return
        save_executable_path(path, base_dir=self._config_dir)
        self._shell.status(f"PHP Generator set: {Path(path).name}", 5000)

    def _project_output_folder_default(self) -> str:
        """Prefill for the output-folder dialog: when a local §18.2 project
        is open, its folder wins ahead of both fallbacks below -- still a
        prefill, not a silent redirect (the picker itself is unchanged, the
        user can always choose differently). Otherwise: the project's
        Project@outputPath if readable, else the directory of the current
        project file, else ''. Inert in no-project mode (§18.2's "no-project
        mode is completely unaffected" principle)."""
        host_default = self._default_output_dir()
        if host_default:
            return host_default
        project = self._project()
        if project is not None and project.tree is not None:
            root = project.tree.getroot()
            if root is not None:
                declared = root.get("outputPath")
                if declared:
                    return declared
        project_path = self._project_path()
        if project_path:
            return str(Path(project_path).parent)
        return ""

    def _clear_generator_output(self) -> None:
        """Remove only prior [PHP]-prefixed Audit entries (leave [Find]/[Schema])."""
        audit = self._shell.audit
        for row in range(audit.count() - 1, -1, -1):
            if audit.item(row).text().startswith(GENERATOR_OUTPUT_PREFIX):
                audit.takeItem(row)

    def generate_php(self) -> None:
        # 0. Reject a second run while one is in flight (avoid overlapping
        # QProcess instances orphaning the first).
        if self._is_generating:
            self._shell.status("A generation is already in progress.", 5000)
            return

        # 1. Require an open project (a tracked model or non-empty editor).
        if (
            self._project() is None
            and not self._shell.stage.xml_editor.toPlainText().strip()
        ):
            self._shell.status("Open a project before generating.", 5000)
            return

        # 2. Require a configured executable.
        exe = load_executable_path(base_dir=self._config_dir)
        if exe is None:
            modals.QMessageBox.information(
                self._shell.window,
                "Generate PHP",
                "Locate the PHP Generator executable first (Generation > Locate PHP Generator Executable...).",
            )
            return

        # 3. Save vs Save As vs Cancel so on-disk content matches the editor.
        if not self._prompt_and_save(
            "Save Before Generating",
            "The generator reads the project from disk. Save the current editor "
            "contents before generating?",
        ):
            return

        # 4. Output folder (prefilled).
        output_folder = modals.QFileDialog.getExistingDirectory(
            self._shell.window,
            "Select Output Folder",
            self._project_output_folder_default(),
        )
        if not output_folder:
            return

        # 5. Run via the injected runner.
        self._clear_generator_output()
        command = build_generate_command(exe, self._project_path(), output_folder)
        self._current_output_folder = output_folder
        self._is_generating = True
        self._shell.status("Generating PHP…")
        _log.info("generate: started")
        self._runner.run(
            command,
            on_output=self._append_generator_output,
            on_finished=self._on_generation_finished,
        )

    def _prompt_and_save(self, title: str, text: str) -> bool:
        """The Save / Save As / Cancel prompt every run shares, resolved through
        the injected `ensure_saved`. False = stop (cancelled, or Save As was
        cancelled so nothing is on disk to generate from)."""
        choice = modals.QMessageBox.question(
            self._shell.window,
            title,
            text,
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.SaveAll  # used as the "Save As..." button
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if choice == modals.QMessageBox.StandardButton.Cancel:
            return False
        # `Save` delegates to Save As itself when there's no path yet.
        return bool(
            self._ensure_saved(choice == modals.QMessageBox.StandardButton.SaveAll)
        )

    def _append_generator_output(self, line: str) -> None:
        self._shell.audit.addItem(f"{GENERATOR_OUTPUT_PREFIX}{line}")

    def _on_generation_finished(self, exit_code: int) -> None:
        _log.info("generate: rc=%s", exit_code)
        self._is_generating = False
        self._shell.audit.addItem(
            f"{GENERATOR_OUTPUT_PREFIX}Generation finished (exit {exit_code})"
        )
        if exit_code == 0:
            modals.QMessageBox.information(
                self._shell.window, "Generate PHP", "Generation succeeded."
            )
            self._shell.status("Generation succeeded", 5000)
        else:
            modals.QMessageBox.critical(
                self._shell.window,
                "Generate PHP",
                f"Generation failed (exit {exit_code}). See the Audit / Problems panel for the generator log.",
            )
            self._shell.status(f"Generation failed (exit {exit_code})", 5000)

    def open_output_folder(self) -> None:
        if not self._current_output_folder:
            self._shell.status("No output folder yet — run Generate PHP first.", 5000)
            return
        modals.QDesktopServices.openUrl(
            QUrl.fromLocalFile(self._current_output_folder)
        )

    # -- panGen / rePHPgen (own generator + gap analysis) --------------------

    def gap_json_work_path(self) -> Path:
        """Scratch path for the analyze command's JSON output (next to the
        generator config, out of the user's project tree)."""
        return generator_config_path(self._config_dir).parent / "last_gap.json"

    def _re_phpgen_runtime(self) -> tuple[str, str, dict[str, str]] | None:
        """(python, root, extra_env) or None after showing guidance."""
        root = load_re_phpgen_root(base_dir=self._config_dir)
        if not validate_re_phpgen_root(root):
            modals.QMessageBox.information(
                self._shell.window,
                "panGen",
                "re_phpgen runtime not found. Set it via "
                "Generation > Locate panGen Runtime...",
            )
            return None
        python = resolve_re_phpgen_python(root)
        # Merge-prepend PYTHONPATH: our src first (wins shadowing), user's
        # pre-existing entries preserved (never clobber their environment).
        src = str(Path(root) / "src")
        existing = os.environ.get("PYTHONPATH", "")
        pythonpath = src + (os.pathsep + existing if existing else "")
        return python, root, {"PYTHONPATH": pythonpath}

    def _prepare_generation_run(self) -> str | None:
        """Shared preamble: in-flight guard, open project, save prompt, output
        folder. Returns the output folder or None. Mirrors generate_php's steps
        (no vendor-exe check)."""
        if self._is_generating:
            self._shell.status("A generation is already in progress.", 5000)
            return None
        if (
            self._project() is None
            and not self._shell.stage.xml_editor.toPlainText().strip()
        ):
            self._shell.status("Open a project first.", 5000)
            return None
        if not self._prompt_and_save(
            "Save Before Running",
            "panGen reads the project from disk. Save the current editor contents first?",
        ):
            return None
        output_folder = modals.QFileDialog.getExistingDirectory(
            self._shell.window,
            "Select Output Folder",
            self._project_output_folder_default(),
        )
        return output_folder or None

    def pangen(self) -> None:
        runtime = self._re_phpgen_runtime()
        if runtime is None:
            return
        python, root, extra_env = runtime
        output_folder = self._prepare_generation_run()
        if output_folder is None:
            return
        self._clear_generator_output()
        self._current_output_folder = output_folder
        self._is_generating = True
        self._shell.status("panGen: generating…")
        _log.info("pangen: started")
        self._runner.run(
            build_pangen_command(python, self._project_path(), output_folder),
            on_output=self._append_generator_output,
            on_finished=self._on_pangen_finished,
            cwd=root,
            extra_env=extra_env,
        )

    def _on_pangen_finished(self, exit_code: int) -> None:
        _log.info("pangen: rc=%s", exit_code)
        self._is_generating = False
        if exit_code == 0:
            self._shell.status("panGen finished", 5000)
        else:
            modals.QMessageBox.warning(
                self._shell.window,
                "panGen",
                f"panGen failed (exit {exit_code}). See the Audit / Problems panel "
                "for the generator log.",
            )
            self._shell.status(f"panGen failed (exit {exit_code})", 5000)

    def analyze_gap(self) -> None:
        runtime = self._re_phpgen_runtime()
        if runtime is None:
            return
        python, root, extra_env = runtime
        output_folder = self._prepare_generation_run()
        if output_folder is None:
            return
        if Path(output_folder).name == PANGEN_SUBFOLDER:
            modals.QMessageBox.information(
                self._shell.window, "rePHPgen",
                "This is panGen's own output subfolder — select the folder that "
                "contains the vendor-generated .php files instead.",
            )
            return
        if not any(Path(output_folder).glob("*.php")):
            modals.QMessageBox.information(
                self._shell.window,
                "rePHPgen",
                "No vendor output found in this folder. Generate the project from "
                "the PHP Generator GUI into this folder first, then run rePHPgen.",
            )
            return

        self._clear_generator_output()
        self._current_output_folder = output_folder
        self._is_generating = True
        self._save_rejson_action.setEnabled(False)
        json_path = self.gap_json_work_path()
        pgtp = self._project_path()
        pangen_command = build_pangen_command(python, pgtp, output_folder)
        analyze_command = build_analyze_command(python, pgtp, output_folder, str(json_path))
        self._shell.status("rePHPgen: generating…")
        _log.info("re_phpgen: pangen started")

        def _on_analyze_finished(exit_code: int) -> None:
            _log.info("re_phpgen: analyze rc=%s", exit_code)
            self._is_generating = False
            if exit_code != 0:
                modals.QMessageBox.warning(
                    self._shell.window,
                    "rePHPgen",
                    f"Gap analysis failed (exit {exit_code}). See the Audit / "
                    "Problems panel for the log.",
                )
                self._shell.status(f"rePHPgen failed (exit {exit_code})", 5000)
                return
            self._last_gap_json = json_path
            self._save_rejson_action.setEnabled(True)
            summary = summarize_gap_json(json_path)
            self._append_generator_output(summary.replace("\n", " | "))
            self._shell.status("rePHPgen: gap analysis complete", 5000)
            modals.QMessageBox.information(
                self._shell.window, "rePHPgen — Gap Summary", summary
            )

        def _on_pangen_done(exit_code: int) -> None:
            _log.info("re_phpgen: pangen rc=%s", exit_code)
            if exit_code != 0:
                self._is_generating = False
                modals.QMessageBox.warning(
                    self._shell.window,
                    "rePHPgen",
                    f"panGen failed (exit {exit_code}). See the Audit / Problems "
                    "panel for the generator log.",
                )
                self._shell.status(f"rePHPgen failed (exit {exit_code})", 5000)
                return
            _log.info("re_phpgen: analyze started")
            self._runner.run(
                analyze_command,
                on_output=self._append_generator_output,
                on_finished=_on_analyze_finished,
                cwd=root,
                extra_env=extra_env,
            )

        self._runner.run(
            pangen_command,
            on_output=self._append_generator_output,
            on_finished=_on_pangen_done,
            cwd=root,
            extra_env=extra_env,
        )

    def save_rejson(self) -> None:
        if self._last_gap_json is None or not Path(self._last_gap_json).is_file():
            self._shell.status("No gap JSON yet — run rePHPgen first.", 5000)
            return
        project_path = self._project_path()
        stem = Path(project_path).stem if project_path else "project"
        default_dir = self._current_output_folder or ""
        path, _filter = modals.QFileDialog.getSaveFileName(
            self._shell.window,
            "Save reJSON",
            str(Path(default_dir) / f"{stem}_gap.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        Path(path).write_text(
            Path(self._last_gap_json).read_text(encoding="utf-8"), encoding="utf-8"
        )
        self._shell.status(f"Saved reJSON to {Path(path).name}", 5000)

    def locate_pangen_runtime(self) -> None:
        root = modals.QFileDialog.getExistingDirectory(
            self._shell.window,
            "Locate panGen Runtime (re_phpgen repo)",
            load_re_phpgen_root(base_dir=self._config_dir),
        )
        if not root:
            return
        if not validate_re_phpgen_root(root):
            modals.QMessageBox.warning(
                self._shell.window,
                "panGen",
                "That folder does not look like the re_phpgen repo "
                "(missing src\\re_phpgen).",
            )
            return
        save_re_phpgen_root(root, base_dir=self._config_dir)
        self._shell.status(f"panGen runtime set: {root}", 5000)
