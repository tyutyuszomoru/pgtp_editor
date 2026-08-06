"""§22's hard test rule, enforced rather than merely intended: **no test in
this package may spawn a process.**

The runner is an injectable seam precisely so the suite never depends on a PHP
installation. This autouse fixture makes a violation fail loudly the moment
someone wires the default runner into a test by accident, instead of producing
a test that quietly passes on the author's machine and hangs on CI.
"""
import subprocess

import pytest


@pytest.fixture(autouse=True)
def no_subprocesses(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "a lint test tried to spawn a real process -- inject the runner seam"
        )

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(subprocess, "check_output", _forbidden)
