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

# pgtp_editor/lint/service.py
"""`LintService` -- configured path + runner + parser, in that order (spec §22).

The blocking half of §22 and the only place the three pieces meet: it asks
`config.py` where the linter is, hands the buffer to the injected `runner`, and
feeds whatever comes back to `findings.parse_php_lint_output`. It is **Qt-free**
so it can be called straight from a `run_async` worker thread -- nothing here
touches a widget, and the caller marshals the returned `LintOutcome` back to the
GUI thread.

**`lint_text` never raises.** Not for a missing config key, not for a deleted
executable, not for a timeout, not for an `OSError` out of the spawn, not for an
unexpected exception in a third-party runner. §22 is advisory-only and its hook
sits inside `PhpFileTab.save()`; an exception escaping here could unwind a save
that already wrote correct bytes to disk, turning a lint problem into data loss.
Every failure becomes a distinct `LintStatus` instead, so the Audit panel says
which one happened rather than staying silent -- silence would read as "clean".
"""
from __future__ import annotations

from collections.abc import Callable

from pgtp_editor.lint.config import load_lint_executable_path
from pgtp_editor.lint.findings import (
    LintOutcome,
    LintStatus,
    audit_lines,
    parse_php_lint_output,
)
from pgtp_editor.lint.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    LintProcessResult,
    LintRunner,
    resolve_executable,
    run_php_lint,
)


class LintService:
    """Run the configured PHP linter over a text buffer and report findings.

    Every collaborator is injectable, which is what keeps the tests
    process-free: `executable_provider` stands in for the on-disk config,
    `resolver` for the "does this path exist and is it executable" filesystem
    check, and `runner` for the subprocess itself.
    """

    def __init__(
        self,
        executable_provider: Callable[[], str | None] = load_lint_executable_path,
        runner: LintRunner = run_php_lint,
        resolver: Callable[[str | None], str | None] = resolve_executable,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._executable_provider = executable_provider
        self._runner = runner
        self._resolver = resolver
        self._timeout = timeout

    # --- Configuration ----------------------------------------------------
    def configured_executable(self) -> str | None:
        """The raw configured path (unvalidated), or None. Tolerates a
        provider that itself blows up -- a corrupt config must not be able to
        crash a save."""
        try:
            return self._executable_provider()
        except Exception:  # noqa: BLE001 -- advisory feature, never fatal
            return None

    def is_available(self) -> bool:
        """True when a linter is configured *and* currently usable. Hosts use
        it to decide whether Tools ▸ Lint Current File is worth enabling --
        though §22 still wants the action to run and explain itself rather
        than sit disabled and silent."""
        configured = self.configured_executable()
        return bool(configured) and self._resolve(configured) is not None

    def _resolve(self, configured: str | None) -> str | None:
        try:
            return self._resolver(configured)
        except Exception:  # noqa: BLE001
            return None

    # --- The lint itself --------------------------------------------------
    def lint_text(self, text: str, display_name: str = "") -> LintOutcome:
        """Lint `text`, blocking, and return an outcome. Never raises.

        Call from a worker thread (`ui/async_task.py::run_async`); `php -l` on
        a slow or unreachable filesystem otherwise freezes the window for the
        whole timeout.
        """
        name = display_name or "the current file"

        configured = self.configured_executable()
        if not configured:
            return LintOutcome(status=LintStatus.NOT_CONFIGURED, display_name=name)

        resolved = self._resolve(configured)
        if resolved is None:
            return LintOutcome(
                status=LintStatus.EXECUTABLE_MISSING,
                detail=str(configured),
                display_name=name,
            )

        try:
            result = self._runner(resolved, text, self._timeout)
        except OSError as exc:
            return LintOutcome(
                status=LintStatus.FAILED_TO_START, detail=str(exc), display_name=name
            )
        except Exception as exc:  # noqa: BLE001 -- an injected runner may do anything
            return LintOutcome(
                status=LintStatus.FAILED_TO_START,
                detail=f"{type(exc).__name__}: {exc}",
                display_name=name,
            )

        if not isinstance(result, LintProcessResult):
            # A runner that returned something unexpected is a bug, not a
            # reason to claim the file is clean.
            return LintOutcome(
                status=LintStatus.FAILED_TO_START,
                detail=f"the lint runner returned {type(result).__name__}, "
                f"not a LintProcessResult",
                display_name=name,
            )

        if result.timed_out:
            return LintOutcome(
                status=LintStatus.TIMEOUT,
                detail=f"{self._timeout:g}s",
                display_name=name,
            )

        outcome = parse_php_lint_output(result.stdout, result.stderr, result.exit_code)
        return outcome.with_display_name(name)

    def lint_text_as_audit_lines(self, text: str, display_name: str = "") -> list:
        """`lint_text` rendered straight to `[Lint]` Audit rows -- the shape a
        host appends verbatim. Convenience only; the outcome is the API."""
        return audit_lines(self.lint_text(text, display_name))
