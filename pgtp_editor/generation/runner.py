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

# pgtp_editor/generation/runner.py
"""Invoke the SQL Maestro PostgreSQL PHP Generator CLI.

Two pieces:
- `build_generate_command`: a PURE function assembling the exact argument
  vector. This holds the load-bearing correctness and is fully unit-tested.
- `GeneratorRunner`: a thin QProcess wrapper (added in a later task) that runs
  the command asynchronously, streaming merged stdout/stderr line-by-line so
  the UI never freezes. It is injectable into MainWindow so tests use a fake
  and never spawn a real process.

The confirmed CLI shape is:
    PgPHPGeneratorPro.exe "<project.pgtp>" -output "<output-folder>" -generate
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment

_log = logging.getLogger(__name__)


def build_generate_command(executable: str, pgtp_path: str, output_folder: str) -> list[str]:
    """Return the argument vector for a non-interactive generation run.

    Returned as a list (not a shell string) so QProcess.start(program, args)
    handles quoting -- paths with spaces need no manual escaping here.
    """
    return [executable, pgtp_path, "-output", output_folder, "-generate"]


class GeneratorRunner(QObject):
    """Runs a generator command asynchronously via QProcess, streaming merged
    stdout+stderr to `on_output` line-by-line and calling `on_finished(exit_code)`
    when it ends. Injectable into MainWindow (default: a real instance); tests
    inject a fake exposing the same `run(command, on_output, on_finished)`.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._on_output: Callable[[str], None] = lambda line: None
        self._on_finished: Callable[[int], None] = lambda code: None
        self._finished_emitted = False
        self._started_at = 0.0

    def run(
        self,
        command: list[str],
        on_output: Callable[[str], None],
        on_finished: Callable[[int], None],
        cwd: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        # Clean up the previous run's QProcess before installing a new one:
        # without this, reusing one runner across chained runs (pangen ->
        # analyze) leaks a QProcess per run, and a still-pending readyRead
        # event from the OLD process would fire _emit_output, which reads
        # self._process -- i.e. the NEW process's (empty) buffer -- losing the
        # old run's trailing output line.
        if self._process is not None:
            try:
                self._process.readyReadStandardOutput.disconnect(self._emit_output)
                self._process.finished.disconnect(self._emit_finished)
                self._process.errorOccurred.disconnect(self._on_error)
            except (TypeError, RuntimeError):
                # Already-deleted C++ object or never-connected signal --
                # must not crash a new run.
                pass
            self._process.deleteLater()
            self._process = None

        self._on_output = on_output
        self._on_finished = on_finished
        self._finished_emitted = False

        process = QProcess(self)
        # Merge stderr into stdout so all generator chatter is captured in order.
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._emit_output)
        process.finished.connect(self._emit_finished)
        # A failure to start (e.g. exe no longer exists) never emits finished;
        # map it to a diagnostic line + a nonzero finish so callers see a failure.
        process.errorOccurred.connect(self._on_error)
        if cwd:
            process.setWorkingDirectory(cwd)
        if extra_env:
            env = QProcessEnvironment.systemEnvironment()
            for key, value in extra_env.items():
                env.insert(key, value)
            process.setProcessEnvironment(env)
        self._process = process

        program, *args = command
        _log.info("generate: spawning %s (cwd=%s)", command, os.getcwd())
        self._started_at = time.monotonic()
        process.start(program, args)

    def _emit_output(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            self._on_output(line)

    def _finish_once(self, exit_code: int) -> None:
        """Call on_finished exactly once per run. A crashed process fires BOTH
        errorOccurred(Crashed) and finished(...), and a failed start fires
        errorOccurred; this guard prevents the UI seeing two result dialogs."""
        if self._finished_emitted:
            return
        self._finished_emitted = True
        _log.info(
            "generate: rc=%s (%.1fs)",
            int(exit_code),
            time.monotonic() - self._started_at,
        )
        self._on_finished(int(exit_code))

    def _emit_finished(self, exit_code: int, _exit_status) -> None:
        self._finish_once(exit_code)

    def _on_error(self, _error) -> None:
        if self._process is None:
            return
        self._on_output(f"Failed to start generator: {self._process.errorString()}")
        self._finish_once(1)
