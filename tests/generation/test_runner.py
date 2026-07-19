from pgtp_editor.generation.runner import build_generate_command


def test_build_generate_command_basic():
    assert build_generate_command("gen.exe", "proj.pgtp", "out") == [
        "gen.exe",
        "proj.pgtp",
        "-output",
        "out",
        "-generate",
    ]


def test_build_generate_command_preserves_paths_with_spaces_without_quoting():
    # The list form is passed straight to QProcess.start(program, args), which
    # does its own argument quoting -- so spaces must be left untouched here.
    command = build_generate_command(
        r"C:\Program Files\PgGen\PgPHPGeneratorPro.exe",
        r"C:\My Projects\dev app.pgtp",
        r"C:\Out Folder\gen",
    )
    assert command == [
        r"C:\Program Files\PgGen\PgPHPGeneratorPro.exe",
        r"C:\My Projects\dev app.pgtp",
        "-output",
        r"C:\Out Folder\gen",
        "-generate",
    ]


def test_build_generate_command_is_five_elements_in_fixed_order():
    command = build_generate_command("e", "p", "o")
    assert len(command) == 5
    assert command[0] == "e"
    assert command[1] == "p"
    assert command[2] == "-output"
    assert command[3] == "o"
    assert command[4] == "-generate"


import inspect

from pgtp_editor.generation.runner import GeneratorRunner


def test_generator_runner_is_constructible(qtbot):
    runner = GeneratorRunner()
    assert runner is not None


def test_generator_runner_run_signature_is_the_injection_contract():
    # MainWindow injects a fake with this exact signature; keep them in lockstep.
    params = list(inspect.signature(GeneratorRunner.run).parameters)
    assert params == ["self", "command", "on_output", "on_finished", "cwd", "extra_env"]


def test_generator_runner_calls_on_finished_at_most_once(qtbot):
    # A crashed process fires both errorOccurred(Crashed) and finished(...);
    # on_finished must still reach the UI only once (no double result dialog).
    runner = GeneratorRunner()
    calls = []
    runner._on_finished = lambda code: calls.append(code)
    runner._finished_emitted = False

    runner._finish_once(2)   # e.g. errorOccurred(Crashed) path first
    runner._finish_once(2)   # then finished(...) for the same run
    assert calls == [2]


import logging


def test_run_logs_spawn_and_rc_seams(qtbot, caplog):
    # A nonexistent program still walks the full seam path: "generate:
    # spawning ..." at start, "generate: rc=..." when the failed start is
    # mapped to a nonzero finish.
    runner = GeneratorRunner()
    finished = []
    with caplog.at_level(logging.INFO, logger="pgtp_editor.generation.runner"):
        runner.run(
            ["definitely_not_a_real_generator_xyz.exe"],
            lambda line: None,
            finished.append,
        )
        qtbot.waitUntil(lambda: bool(finished), timeout=5000)
    messages = [r.message for r in caplog.records]
    assert any("generate: spawning" in m for m in messages)
    assert any(m.startswith("generate: rc=1") for m in messages)
    assert finished == [1]


def test_runner_applies_cwd_and_extra_env(qtbot, tmp_path):
    import sys
    from pathlib import Path

    from pgtp_editor.generation.runner import GeneratorRunner

    runner = GeneratorRunner()
    lines: list[str] = []
    codes: list[int] = []
    code = "import os; print(os.getcwd()); print(os.environ.get('PGTP_TEST_ENV', ''))"
    runner.run(
        [sys.executable, "-c", code],
        on_output=lines.append,
        on_finished=codes.append,
        cwd=str(tmp_path),
        extra_env={"PGTP_TEST_ENV": "hello"},
    )
    qtbot.waitUntil(lambda: bool(codes), timeout=10000)
    assert codes == [0]
    assert Path(lines[0]).resolve() == tmp_path.resolve()
    assert lines[1] == "hello"


def test_runner_without_cwd_env_unchanged(qtbot):
    """Existing callers pass neither param — behavior must be identical."""
    import sys

    from pgtp_editor.generation.runner import GeneratorRunner

    runner = GeneratorRunner()
    lines: list[str] = []
    codes: list[int] = []
    runner.run(
        [sys.executable, "-c", "print('plain')"],
        on_output=lines.append,
        on_finished=codes.append,
    )
    qtbot.waitUntil(lambda: bool(codes), timeout=10000)
    assert codes == [0] and lines == ["plain"]


def test_runner_falsy_cwd_and_env_treated_as_unset(qtbot):
    """An empty string / empty dict must not trip setWorkingDirectory or
    setProcessEnvironment (both are guarded by truthiness in run()); the child
    should behave exactly as if cwd/extra_env were omitted."""
    import sys

    from pgtp_editor.generation.runner import GeneratorRunner

    runner = GeneratorRunner()
    lines: list[str] = []
    codes: list[int] = []
    runner.run(
        [sys.executable, "-c", "print('plain')"],
        on_output=lines.append,
        on_finished=codes.append,
        cwd="",
        extra_env={},
    )
    qtbot.waitUntil(lambda: bool(codes), timeout=10000)
    assert codes == [0] and lines == ["plain"]


def test_runner_extra_env_preserves_rest_of_system_environment(qtbot, monkeypatch):
    """extra_env must be layered onto QProcessEnvironment.systemEnvironment(),
    not replace it wholesale -- an unrelated pre-existing variable must still
    reach the child process alongside the new one."""
    import sys

    from pgtp_editor.generation.runner import GeneratorRunner

    monkeypatch.setenv("PGTP_PRE_EXISTING_VAR", "still-here")

    runner = GeneratorRunner()
    lines: list[str] = []
    codes: list[int] = []
    code = (
        "import os; "
        "print(os.environ.get('PGTP_PRE_EXISTING_VAR', '<missing>')); "
        "print(os.environ.get('PGTP_TEST_ENV', '<missing>'))"
    )
    runner.run(
        [sys.executable, "-c", code],
        on_output=lines.append,
        on_finished=codes.append,
        extra_env={"PGTP_TEST_ENV": "hello"},
    )
    qtbot.waitUntil(lambda: bool(codes), timeout=10000)
    assert codes == [0]
    assert lines == ["still-here", "hello"]


def test_runner_extra_env_none_and_cwd_none_explicit(qtbot):
    """Callers may pass cwd=None / extra_env=None explicitly (same default as
    omitting them) -- must not raise and must behave identically to omission."""
    import sys

    from pgtp_editor.generation.runner import GeneratorRunner

    runner = GeneratorRunner()
    lines: list[str] = []
    codes: list[int] = []
    runner.run(
        [sys.executable, "-c", "print('plain')"],
        on_output=lines.append,
        on_finished=codes.append,
        cwd=None,
        extra_env=None,
    )
    qtbot.waitUntil(lambda: bool(codes), timeout=10000)
    assert codes == [0] and lines == ["plain"]


def test_runner_reuse_cleans_up_prior_qprocess(qtbot):
    """Reusing one runner across chained runs (pangen -> analyze) must not
    accumulate QProcess objects: run() disconnects and deleteLater()s the
    previous process before creating the new one. This locks that the cleanup
    happens without exceptions and that a fresh QProcess is installed; the
    lost-trailing-line race (a pending readyRead from the OLD process reading
    the NEW process's buffer) is not deterministically testable here."""
    import sys

    from pgtp_editor.generation.runner import GeneratorRunner

    runner = GeneratorRunner()
    lines1: list[str] = []
    codes1: list[int] = []
    runner.run(
        [sys.executable, "-c", "print('first')"],
        on_output=lines1.append,
        on_finished=codes1.append,
    )
    qtbot.waitUntil(lambda: bool(codes1), timeout=10000)
    assert codes1 == [0] and lines1 == ["first"]
    first = runner._process
    assert first is not None

    lines2: list[str] = []
    codes2: list[int] = []
    runner.run(
        [sys.executable, "-c", "print('second')"],
        on_output=lines2.append,
        on_finished=codes2.append,
    )
    # A fresh QProcess replaced the old one immediately on run().
    assert runner._process is not first
    qtbot.waitUntil(lambda: bool(codes2), timeout=10000)
    assert codes2 == [0] and lines2 == ["second"]
