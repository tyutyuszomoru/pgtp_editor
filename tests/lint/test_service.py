"""Tests for `lint/service.py` -- every §22 failure mode, no real process."""
import pytest

from pgtp_editor.lint.findings import LINT_PREFIX, LintStatus
from pgtp_editor.lint.runner import LintProcessResult
from pgtp_editor.lint.service import LintService

CLEAN = "No syntax errors detected in /tmp/pgtp_lint_x/buffer.php\n"
BROKEN = "Parse error: syntax error, unexpected ';' in /tmp/x/buffer.php on line 4\n"


def _service(result=None, executable="/usr/bin/php", runner=None, **kwargs):
    calls = []

    def _runner(exe, text, timeout):
        calls.append((exe, text, timeout))
        if isinstance(result, Exception):
            raise result
        return result

    service = LintService(
        executable_provider=lambda: executable,
        runner=runner or _runner,
        resolver=lambda path: path,  # "configured means usable" unless overridden
        **kwargs,
    )
    return service, calls


# --- The happy paths ---------------------------------------------------------
def test_clean_buffer():
    service, calls = _service(LintProcessResult(exit_code=0, stdout=CLEAN))
    outcome = service.lint_text("<?php\n", "page.php")
    assert outcome.status is LintStatus.CLEAN
    assert outcome.display_name == "page.php"
    assert calls == [("/usr/bin/php", "<?php\n", service._timeout)]


def test_findings_carry_the_tab_name_not_the_temp_path():
    service, _ = _service(LintProcessResult(exit_code=255, stdout=BROKEN))
    outcome = service.lint_text("<?php ;;", "page.php")
    assert outcome.status is LintStatus.FINDINGS
    assert outcome.findings[0].line == 4
    assert outcome.findings[0].file == "page.php"


def test_audit_line_convenience_wrapper_is_lint_prefixed():
    service, _ = _service(LintProcessResult(exit_code=255, stdout=BROKEN))
    lines = service.lint_text_as_audit_lines("x", "page.php")
    assert lines and all(ln.text.startswith(LINT_PREFIX) for ln in lines)
    assert not any("[Check]" in ln.text or "[SQL]" in ln.text for ln in lines)


# --- Every failure mode, distinguishable -------------------------------------
def test_not_configured():
    service, calls = _service(executable=None)
    outcome = service.lint_text("x", "page.php")
    assert outcome.status is LintStatus.NOT_CONFIGURED
    assert calls == []  # nothing was run


def test_configured_but_missing_executable():
    service = LintService(
        executable_provider=lambda: "/usr/bin/nope",
        runner=lambda *a: pytest.fail("must not run a missing linter"),
        resolver=lambda path: None,
    )
    outcome = service.lint_text("x", "page.php")
    assert outcome.status is LintStatus.EXECUTABLE_MISSING
    assert outcome.detail == "/usr/bin/nope"


def test_timeout():
    service, _ = _service(LintProcessResult(exit_code=None, timed_out=True), timeout=3)
    outcome = service.lint_text("x", "page.php")
    assert outcome.status is LintStatus.TIMEOUT
    assert "3s" in outcome.detail


def test_oserror_from_the_spawn_is_failed_to_start():
    service, _ = _service(OSError("Permission denied"))
    outcome = service.lint_text("x", "page.php")
    assert outcome.status is LintStatus.FAILED_TO_START
    assert "Permission denied" in outcome.detail


def test_any_other_runner_exception_is_also_reported_not_raised():
    service, _ = _service(RuntimeError("boom"))
    outcome = service.lint_text("x", "page.php")
    assert outcome.status is LintStatus.FAILED_TO_START
    assert "RuntimeError" in outcome.detail


def test_a_runner_returning_junk_never_claims_the_file_is_clean():
    service, _ = _service(runner=lambda *a: "totally not a result")
    outcome = service.lint_text("x", "page.php")
    assert outcome.status is LintStatus.FAILED_TO_START
    assert outcome.ok is False


def test_nonzero_exit_with_unparseable_output():
    service, _ = _service(
        LintProcessResult(exit_code=139, stderr="Segmentation fault\n")
    )
    outcome = service.lint_text("x", "page.php")
    assert outcome.status is LintStatus.UNPARSEABLE


def test_empty_output():
    service, _ = _service(LintProcessResult(exit_code=0))
    assert service.lint_text("x", "page.php").status is LintStatus.EMPTY


def test_a_provider_that_raises_is_treated_as_unconfigured():
    def _boom():
        raise ValueError("corrupt config")

    service = LintService(
        executable_provider=_boom,
        runner=lambda *a: pytest.fail("must not run"),
        resolver=lambda p: p,
    )
    assert service.lint_text("x", "p.php").status is LintStatus.NOT_CONFIGURED


def test_lint_text_never_raises_for_any_status():
    for result in (
        LintProcessResult(exit_code=0, stdout=CLEAN),
        LintProcessResult(exit_code=255, stdout=BROKEN),
        LintProcessResult(exit_code=None, timed_out=True),
        LintProcessResult(exit_code=139, stderr="junk"),
        OSError("gone"),
    ):
        service, _ = _service(result)
        service.lint_text("x", "p.php")  # must not raise


# --- is_available ------------------------------------------------------------
def test_is_available_reflects_configuration_and_resolution():
    assert LintService(lambda: "/usr/bin/php", resolver=lambda p: p).is_available()
    assert not LintService(lambda: None, resolver=lambda p: p).is_available()
    assert not LintService(lambda: "/x/php", resolver=lambda p: None).is_available()
