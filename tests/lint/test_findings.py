"""Tests for `lint/findings.py` -- §22's pure parsing layer.

Everything here runs on canned linter text: no subprocess, no filesystem, no
Qt. That is the point of the module's seam.
"""
import re
from pathlib import Path

import pytest

from pgtp_editor.lint.findings import (
    EXTERNAL_TOOLS_SETTINGS_PATH,
    LINT_AUDIT_TARGET,
    LINT_PREFIX,
    LintFinding,
    LintOutcome,
    LintStatus,
    audit_lines,
    parse_php_lint_output,
)

CLEAN_STDOUT = "No syntax errors detected in /tmp/pgtp_lint_x/buffer.php\n"

# The real shape of a `php -l` failure with default php.ini: the same message
# on stdout and, prefixed with "PHP ", on stderr.
ERROR_STDOUT = (
    "Parse error: syntax error, unexpected end of file, expecting ';' "
    "in /tmp/pgtp_lint_x/buffer.php on line 7\n"
    "Errors parsing /tmp/pgtp_lint_x/buffer.php\n"
)
ERROR_STDERR = (
    "PHP Parse error:  syntax error, unexpected end of file, expecting ';' "
    "in /tmp/pgtp_lint_x/buffer.php on line 7\n"
)


# --- The module is provably Qt-free / subprocess-free ------------------------
def test_parsing_layer_imports_no_qt_and_no_subprocess():
    source = Path(
        __import__("pgtp_editor.lint.findings", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")
    body = "\n".join(
        ln for ln in source.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "PySide6" not in body
    assert "import subprocess" not in body


# --- Clean output ------------------------------------------------------------
def test_clean_output_is_parsed_as_clean():
    outcome = parse_php_lint_output(CLEAN_STDOUT, "", 0)
    assert outcome.status is LintStatus.CLEAN
    assert outcome.ok is True
    assert outcome.findings == ()


def test_clean_output_wins_over_a_dirty_exit_code():
    # A php.ini startup warning can dirty the status of an otherwise clean lint.
    outcome = parse_php_lint_output(CLEAN_STDOUT, "PHP Warning: ini junk\n", 255)
    assert outcome.status is LintStatus.CLEAN


# --- Error output ------------------------------------------------------------
def test_parse_error_yields_a_finding_with_its_line_number():
    outcome = parse_php_lint_output(ERROR_STDOUT, ERROR_STDERR, 255)
    assert outcome.status is LintStatus.FINDINGS
    assert len(outcome.findings) == 1
    finding = outcome.findings[0]
    assert finding.line == 7
    assert "unexpected end of file" in finding.message
    assert finding.severity == "error"
    assert finding.file.endswith("buffer.php")


def test_the_stdout_stderr_duplicate_pair_collapses_to_one_finding():
    outcome = parse_php_lint_output(ERROR_STDOUT, ERROR_STDERR, 255)
    assert len(outcome.findings) == 1


def test_fatal_error_is_parsed_too():
    outcome = parse_php_lint_output(
        "Fatal error: Cannot redeclare foo() in /t/buffer.php on line 12\n", "", 255
    )
    assert outcome.status is LintStatus.FINDINGS
    assert outcome.findings[0].line == 12


def test_two_distinct_errors_become_two_findings():
    outcome = parse_php_lint_output(
        "Parse error: a in /t/b.php on line 3\n"
        "Parse error: b in /t/b.php on line 9\n",
        "",
        255,
    )
    assert [f.line for f in outcome.findings] == [3, 9]


# --- Degenerate output -------------------------------------------------------
def test_unrecognisable_output_is_unparseable_not_clean():
    outcome = parse_php_lint_output("", "Segmentation fault (core dumped)\n", 139)
    assert outcome.status is LintStatus.UNPARSEABLE
    assert outcome.ok is False


def test_empty_output_is_its_own_status():
    outcome = parse_php_lint_output("", "", 0)
    assert outcome.status is LintStatus.EMPTY
    assert outcome.ok is False


def test_an_error_without_a_line_number_does_not_fake_one():
    outcome = parse_php_lint_output("Could not open input file: buffer.php\n", "", 1)
    assert outcome.status is LintStatus.UNPARSEABLE
    assert outcome.findings == ()


# --- display name remapping --------------------------------------------------
def test_with_display_name_replaces_the_temp_path_everywhere():
    outcome = parse_php_lint_output(ERROR_STDOUT, ERROR_STDERR, 255).with_display_name(
        "page.php"
    )
    assert outcome.display_name == "page.php"
    assert outcome.findings[0].file == "page.php"
    assert outcome.findings[0].line == 7  # untouched


# --- Audit lines: the [Lint] prefix and its reservation ----------------------
ALL_STATUSES = list(LintStatus)


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_every_status_produces_at_least_one_lint_prefixed_line(status):
    findings = (LintFinding(line=4, message="boom"),) if status is LintStatus.FINDINGS else ()
    outcome = LintOutcome(
        status=status,
        findings=findings,
        detail="detail",
        display_name="page.php",
        raw_output="junk output",
        exit_code=255,
    )
    lines = audit_lines(outcome)
    assert lines, f"{status} rendered nothing -- a silent no-op reads as 'clean'"
    assert all(line.text.startswith(LINT_PREFIX) for line in lines)


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_no_status_ever_emits_the_check_or_sql_prefixes(status):
    findings = (LintFinding(line=4, message="boom"),) if status is LintStatus.FINDINGS else ()
    outcome = LintOutcome(
        status=status,
        findings=findings,
        detail="d",
        display_name="page.php",
        raw_output="x",
        exit_code=1,
    )
    for line in audit_lines(outcome):
        assert "[Check]" not in line.text  # §18.5's prefix
        assert "[SQL]" not in line.text  # §18.4's prefix


def test_finding_lines_carry_the_navigable_line_number():
    outcome = parse_php_lint_output(ERROR_STDOUT, ERROR_STDERR, 255).with_display_name(
        "page.php"
    )
    lines = audit_lines(outcome)
    navigable = [ln for ln in lines if ln.line is not None]
    assert [ln.line for ln in navigable] == [7]
    assert re.search(r"line 7:", navigable[0].text)
    assert "page.php" in navigable[0].text


def test_findings_are_followed_by_the_first_error_only_caveat():
    outcome = parse_php_lint_output(ERROR_STDOUT, "", 255).with_display_name("p.php")
    texts = [ln.text for ln in audit_lines(outcome)]
    assert any("FIRST syntax error" in t for t in texts)


def test_clean_and_not_run_rows_are_not_navigable():
    for outcome in (
        LintOutcome(status=LintStatus.CLEAN, display_name="p.php"),
        LintOutcome(status=LintStatus.NOT_CONFIGURED, display_name="p.php"),
        LintOutcome(status=LintStatus.EXECUTABLE_MISSING, detail="/x/php", display_name="p.php"),
        LintOutcome(status=LintStatus.TIMEOUT, detail="10s", display_name="p.php"),
        LintOutcome(status=LintStatus.EMPTY, exit_code=0, display_name="p.php"),
    ):
        assert all(line.line is None for line in audit_lines(outcome))


def test_each_failure_mode_says_something_different():
    texts = {}
    for status, kwargs in (
        (LintStatus.NOT_CONFIGURED, {}),
        (LintStatus.EXECUTABLE_MISSING, {"detail": "/usr/bin/nope"}),
        (LintStatus.TIMEOUT, {"detail": "10s"}),
        (LintStatus.FAILED_TO_START, {"detail": "OSError: denied"}),
        (LintStatus.EMPTY, {"exit_code": 0}),
        (LintStatus.UNPARSEABLE, {"raw_output": "boom", "exit_code": 139}),
    ):
        texts[status] = audit_lines(
            LintOutcome(status=status, display_name="p.php", **kwargs)
        )[0].text
    assert len(set(texts.values())) == len(texts), texts
    assert "/usr/bin/nope" in texts[LintStatus.EXECUTABLE_MISSING]
    # FQ-260812025705 moved where a linter is SET, so the remedy this row names
    # moved with it. `EXTERNAL_TOOLS_SETTINGS_PATH` is `lint/`'s own copy of the
    # address (`lint/` must not import `ui/`); the copy is pinned to the UI
    # constant by `tests/ui/test_software_settings_dialog.py`.
    assert EXTERNAL_TOOLS_SETTINGS_PATH in texts[LintStatus.NOT_CONFIGURED]
    assert "timed out" in texts[LintStatus.TIMEOUT]
    assert "OSError: denied" in texts[LintStatus.FAILED_TO_START]


def test_unparseable_quotes_the_output_but_caps_it():
    raw = "\n".join(f"line {i}" for i in range(20))
    lines = audit_lines(
        LintOutcome(
            status=LintStatus.UNPARSEABLE,
            raw_output=raw,
            exit_code=139,
            display_name="p.php",
        )
    )
    assert any("more line(s)" in ln.text for ln in lines)
    assert len(lines) < 10


def test_the_navigation_target_tag_is_exported():
    assert LINT_AUDIT_TARGET == "php"


def test_status_ran_flag_separates_inspected_from_never_looked_at():
    assert LintStatus.CLEAN.ran and LintStatus.FINDINGS.ran and LintStatus.UNPARSEABLE.ran
    assert not LintStatus.EMPTY.ran
    assert not LintStatus.NOT_CONFIGURED.ran
    assert not LintStatus.EXECUTABLE_MISSING.ran
    assert not LintStatus.TIMEOUT.ran
    assert not LintStatus.FAILED_TO_START.ran
