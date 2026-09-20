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

# pgtp_editor/lint/findings.py
"""Pure parsing of `php -l` output into findings and Audit lines (spec §22).

**Qt-free, subprocess-free, filesystem-free on purpose.** Turning linter text
into structured findings is plain string processing, so it lives behind a hard
seam from the process that produced the text: every case below -- clean file,
syntax error, garbage output, empty output, timeout, missing executable -- is
reachable in a unit test from canned strings alone. Without that split the only
way to cover "the linter printed something we don't recognise" would be to
install a broken PHP.

**`php -l` reports only the FIRST syntax error in a file.** It stops at the
first parse failure, so a single finding is *never* proof that the rest of the
file is clean -- fix it and lint again. `audit_lines()` says so out loud next to
the finding, because the failure mode this module exists to prevent is a user
reading one `[Lint]` line and believing the file has exactly one problem.

**`[Lint]` is this module's prefix and nothing else's.** §18.5's SQL/plpgsql
findings are `[Check]` and §18.4's formatter refusals are `[SQL]` (§7's
three-way reservation). Several linter-shaped features feed the one Audit
panel; a reader must be able to tell at a glance which tool spoke.

**phpcs is deliberately NOT parsed here.** §22 lists it as optional ("optionally
full `phpcs`"), and its report formats (`full`, `csv`, `checkstyle`, `json`)
were not available to verify against a real installation while this was written
-- so rather than ship a guessed regex that would silently mis-report, only
`php -l` is implemented. `LintStatus.UNPARSEABLE` is what a phpcs invocation
would currently produce: honest, not silent. Adding phpcs means a new
`parse_phpcs_*` function beside this one, never a widened `php -l` regex.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum

#: The Audit-panel prefix reserved for PHP linting (§7/§18.5/§22). Never
#: `[Check]` (SQL/plpgsql, §18.5) and never `[SQL]` (formatter refusals, §18.4).
LINT_PREFIX = "[Lint] "

#: Where a user now SETS the linter (FQ-260812025705 moved `Tools ▸ Locate PHP
#: Linter…` into the Software settings dialog). Spelled out here rather than
#: imported: `lint/` is pure and must not reach into `ui/`, which owns the
#: canonical `software_settings_dialog.EXTERNAL_TOOLS_SETTINGS_PATH`. A test
#: pins the two strings together, so the copy cannot drift.
EXTERNAL_TOOLS_SETTINGS_PATH = "Settings ▸ Software settings… ▸ External tools"

#: `UserRole + 1` target tag the host writes on a `[Lint]` audit item, so
#: `MainWindow._on_audit_item_clicked` routes the click to the PHP tab instead
#: of the Raw XML editor (the "xsd" tag's precedent).
LINT_AUDIT_TARGET = "php"

#: What `php -l` prints for a file it could parse.
_CLEAN_MARKER = "No syntax errors detected"

# `php -l` emits, on stdout and (when log_errors is on) again on stderr with a
# "PHP " prefix:
#     PHP Parse error:  syntax error, unexpected end of file in /t/x.php on line 5
#     Parse error: syntax error, unexpected end of file in /t/x.php on line 5
# Fatal errors (e.g. a redeclared function seen at compile time) take the same
# shape with "Fatal error" instead. Both are captured; the duplicate pair is
# de-duplicated below rather than reported twice.
_ERROR_RE = re.compile(
    r"^(?:PHP\s+)?(?P<kind>Parse|Fatal|Warning|Deprecated)\s+error:\s*"
    r"(?P<message>.*?)\s+in\s+(?P<file>.+?)\s+on line\s+(?P<line>\d+)\s*$",
    re.IGNORECASE,
)


class LintStatus(str, Enum):
    """Every distinguishable outcome of one lint attempt.

    They are separate members rather than a bool because "the file is clean"
    and "we never managed to look at the file" must never render the same way:
    a silent no-op would leave the user believing an unchecked file is clean,
    which is the single worst outcome this feature can have.
    """

    CLEAN = "clean"                          #: exit 0, "No syntax errors detected"
    FINDINGS = "findings"                    #: parseable error(s) with line numbers
    UNPARSEABLE = "unparseable"              #: ran, said something we don't recognise
    EMPTY = "empty"                          #: exit 0 but printed nothing at all
    NOT_CONFIGURED = "not_configured"        #: no `lint_executable_path` set
    EXECUTABLE_MISSING = "executable_missing"  #: path set, but absent / not executable
    TIMEOUT = "timeout"                      #: the linter had to be killed
    FAILED_TO_START = "failed_to_start"      #: OSError spawning the process

    @property
    def ran(self) -> bool:
        """True only when the linter actually inspected the file."""
        return self in (LintStatus.CLEAN, LintStatus.FINDINGS, LintStatus.UNPARSEABLE)


@dataclass(frozen=True)
class LintFinding:
    """One linter message, with the line the host can navigate to.

    `line` is 1-based, matching `CodeEditor.navigate_to_line` and the
    `[Validate]` items' `UserRole` payload. It is never None for a `php -l`
    finding -- an error without a line number cannot be parsed into a finding
    at all and becomes `UNPARSEABLE` instead, so a `[Lint]` item either
    navigates or is honestly marked as non-navigable.
    """

    line: int
    message: str
    file: str = ""
    severity: str = "error"


@dataclass(frozen=True)
class LintOutcome:
    """The whole result of one lint attempt: status, findings and raw text."""

    status: LintStatus
    findings: tuple[LintFinding, ...] = ()
    #: Free-text detail for the non-`ran` statuses (the path that was missing,
    #: the timeout in seconds, the OSError text). Never the findings' text.
    detail: str = ""
    #: The name shown to the user. The linter usually sees a temp file, so the
    #: service overwrites the findings' `file` with this before reporting.
    display_name: str = ""
    #: Whatever the process printed, kept verbatim so UNPARSEABLE can quote it
    #: instead of swallowing it.
    raw_output: str = ""
    exit_code: int | None = None

    @property
    def ok(self) -> bool:
        """True only for a file the linter inspected and found clean."""
        return self.status is LintStatus.CLEAN

    def with_display_name(self, name: str) -> "LintOutcome":
        """Rewrite the user-facing file name onto the outcome and its findings.

        The default runner lints a temp copy of the buffer (so an unsaved or
        dirty tab can be linted at all), which means the linter's own file name
        is a meaningless `/tmp/...` path. Showing it would be worse than
        useless -- it names a file the user cannot open.
        """
        return replace(
            self,
            display_name=name,
            findings=tuple(replace(f, file=name) for f in self.findings),
        )


@dataclass(frozen=True)
class LintAuditLine:
    """One ready-to-append Audit row: the text, and the line to navigate to.

    `line is None` marks a non-navigable row (a summary or a "did not run"
    notice) -- exactly the `[Validate]` convention, where
    `MainWindow._on_audit_item_clicked` no-ops on a null `UserRole`.
    """

    text: str
    line: int | None = None


def parse_php_lint_output(
    stdout: str, stderr: str = "", exit_code: int | None = 0
) -> LintOutcome:
    """Parse one `php -l` run into a `LintOutcome`. Pure; never raises.

    `php -l` exits 0 and prints "No syntax errors detected in <file>" on
    success, and exits non-zero (255 in practice) printing a
    "Parse error: ... in <file> on line N" pair -- once on stdout, and again
    on stderr with a leading "PHP " when `log_errors` is on. Both streams are
    scanned and identical (line, message) pairs collapse to one finding, so
    the default php.ini does not double-report.

    Unknown output is reported as `UNPARSEABLE` rather than silently treated as
    clean: an unrecognised linter that we call "OK" is a lie about the file.
    """
    combined = "\n".join(part for part in (stdout or "", stderr or "") if part)

    findings: list[LintFinding] = []
    seen: set[tuple[int, str]] = set()
    for raw_line in combined.splitlines():
        match = _ERROR_RE.match(raw_line.strip())
        if match is None:
            continue
        line_no = int(match.group("line"))
        message = " ".join(match.group("message").split())
        kind = match.group("kind").lower()
        key = (line_no, message)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            LintFinding(
                line=line_no,
                message=message,
                file=match.group("file").strip(),
                severity="error" if kind in ("parse", "fatal") else "warning",
            )
        )

    if findings:
        return LintOutcome(
            status=LintStatus.FINDINGS,
            findings=tuple(findings),
            raw_output=combined,
            exit_code=exit_code,
        )
    if _CLEAN_MARKER.lower() in combined.lower():
        # Trust the marker over the exit code: a php.ini warning on startup can
        # dirty the exit status of an otherwise clean lint.
        return LintOutcome(
            status=LintStatus.CLEAN, raw_output=combined, exit_code=exit_code
        )
    if not combined.strip():
        return LintOutcome(
            status=LintStatus.EMPTY, raw_output="", exit_code=exit_code
        )
    return LintOutcome(
        status=LintStatus.UNPARSEABLE, raw_output=combined, exit_code=exit_code
    )


#: How many raw output lines an UNPARSEABLE outcome quotes. Enough to diagnose,
#: not enough to flood the Audit panel with a runaway linter's stack trace.
_RAW_QUOTE_LIMIT = 5


def audit_lines(outcome: LintOutcome) -> list[LintAuditLine]:
    """Render an outcome as `[Lint]`-prefixed Audit rows. Never returns [].

    Every status produces at least one visible row, including the ones where
    nothing ran. Returning nothing for "no linter configured" would look
    identical to a clean file, and the user would trust an unchecked buffer.
    """
    name = outcome.display_name or "the current file"
    status = outcome.status

    if status is LintStatus.CLEAN:
        return [LintAuditLine(f"{LINT_PREFIX}OK: no syntax errors detected in {name}")]

    if status is LintStatus.FINDINGS:
        lines = [
            LintAuditLine(
                f"{LINT_PREFIX}{f.severity.upper()} line {f.line}: {f.message} ({name})",
                f.line,
            )
            for f in outcome.findings
        ]
        lines.append(
            LintAuditLine(
                f"{LINT_PREFIX}note: `php -l` stops at the FIRST syntax error — "
                f"fix it and lint again; more may follow."
            )
        )
        return lines

    if status is LintStatus.UNPARSEABLE:
        quoted = [ln for ln in outcome.raw_output.splitlines() if ln.strip()]
        head = quoted[:_RAW_QUOTE_LIMIT]
        lines = [
            LintAuditLine(
                f"{LINT_PREFIX}ERROR: the linter exited {outcome.exit_code} with output "
                f"that could not be parsed — {name} was NOT verified."
            )
        ]
        lines += [LintAuditLine(f"{LINT_PREFIX}  {ln.strip()}") for ln in head]
        if len(quoted) > len(head):
            lines.append(
                LintAuditLine(f"{LINT_PREFIX}  … {len(quoted) - len(head)} more line(s)")
            )
        return lines

    if status is LintStatus.EMPTY:
        return [
            LintAuditLine(
                f"{LINT_PREFIX}NOT RUN: the linter exited {outcome.exit_code} without "
                f"printing anything — {name} was NOT verified."
            )
        ]

    if status is LintStatus.NOT_CONFIGURED:
        return [
            LintAuditLine(
                f"{LINT_PREFIX}NOT RUN: no PHP linter is configured — "
                f"use {EXTERNAL_TOOLS_SETTINGS_PATH} to point at your `php` "
                f"executable."
            )
        ]

    if status is LintStatus.EXECUTABLE_MISSING:
        return [
            LintAuditLine(
                f"{LINT_PREFIX}NOT RUN: the configured PHP linter is missing or not "
                f"executable: {outcome.detail} — set it again in "
                f"{EXTERNAL_TOOLS_SETTINGS_PATH}."
            )
        ]

    if status is LintStatus.TIMEOUT:
        return [
            LintAuditLine(
                f"{LINT_PREFIX}NOT RUN: the linter timed out ({outcome.detail}) — "
                f"{name} was NOT verified."
            )
        ]

    return [
        LintAuditLine(
            f"{LINT_PREFIX}NOT RUN: the linter could not be started: {outcome.detail}"
        )
    ]
