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

# pgtp_editor/lint/runner.py
"""The one place `php -l` is actually spawned (spec §22).

Isolated in its own module behind the `LintRunner` alias for the reason
`db/sandbox.py`'s `ProcessRunner` and `db/introspect.py`'s `runner=` exist:
**no test may spawn a process.** Everything interesting about §22 -- parsing,
the `[Lint]` prefix, the six failure modes, the never-block-a-save rule -- is
reachable by injecting a callable that returns canned `LintProcessResult`s, so
the suite stays deterministic and does not require PHP to be installed.

The buffer is linted through a **temporary copy**, not the file on disk. A tab
can be unsaved (`Untitled`) or dirty, and §22's on-save hook must lint what the
user is looking at; linting the last-saved bytes would report errors the user
already fixed, or -- far worse -- report clean while the buffer is broken.
`findings.LintOutcome.with_display_name` puts the real name back afterwards so
the temp path is never shown.

This runner blocks. It is meant to be called from a `ui/async_task.py::run_async`
worker (`php -l` on a network share is slow enough to freeze the window),
never directly on the GUI thread.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

#: `php -l` on a local file is milliseconds; ten seconds is "the tool is wedged
#: or the filesystem is gone", and killing it is better than a frozen feature.
DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class LintProcessResult:
    """What one linter invocation produced -- the runner seam's whole vocabulary.

    Deliberately dumb data (no Qt, no `Popen` handle) so a test's fake runner is
    a one-line lambda.
    """

    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    #: True when the process had to be killed. Kept separate from `exit_code`
    #: because "timed out" and "exited non-zero" need different Audit text --
    #: one means the file is unverified, the other means it has an error.
    timed_out: bool = False


#: Signature of the injectable runner: (executable, buffer text, timeout).
LintRunner = Callable[[str, str, float], LintProcessResult]


def build_php_lint_command(executable: str, file_path: str) -> list[str]:
    """`php -l <file>` -- pure, so the argv is assertable without running it.

    `-n` is deliberately NOT passed: the user's php.ini may register the very
    extensions their code relies on, and linting under a different
    configuration than the one that will run the code produces findings that do
    not reproduce.
    """
    return [executable, "-l", file_path]


def resolve_executable(executable: str | None) -> str | None:
    """Return a usable absolute path for `executable`, or None.

    Accepts either a full path or a bare name to look up on `PATH` (a user who
    typed `php` should not be told the file is missing). Returns None when the
    path does not exist, is a directory, or is not executable -- the caller
    turns that into `LintStatus.EXECUTABLE_MISSING`, which is a distinct
    message from "not configured": a path that used to work and now doesn't is
    a different problem from never having set one.
    """
    if not executable or not str(executable).strip():
        return None
    candidate = str(executable).strip()
    if os.sep in candidate or (os.altsep and os.altsep in candidate):
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        return None
    found = shutil.which(candidate)
    return found


def _no_window_kwargs() -> dict:
    """Keep a console window from flashing up on Windows for every save."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", None)
    return {"creationflags": flags} if flags else {}


def run_php_lint(
    executable: str,
    text: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> LintProcessResult:
    """Lint `text` with `php -l`, blocking. Never raises for a lint failure.

    A timeout comes back as `timed_out=True` rather than an exception, because
    §22 is advisory: a wedged linter must degrade into an Audit line, not into
    a traceback that could unwind an in-progress save. `OSError` (executable
    vanished between the check and the spawn) is left to propagate -- the
    service catches it and reports `FAILED_TO_START`, so the two causes stay
    distinguishable in the panel.
    """
    with tempfile.TemporaryDirectory(prefix="pgtp_lint_") as tmp_dir:
        temp_file = Path(tmp_dir) / "buffer.php"
        temp_file.write_text(text, encoding="utf-8", newline="")
        try:
            completed = subprocess.run(
                build_php_lint_command(executable, str(temp_file)),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                **_no_window_kwargs(),
            )
        except subprocess.TimeoutExpired:
            return LintProcessResult(exit_code=None, timed_out=True)
    return LintProcessResult(
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
