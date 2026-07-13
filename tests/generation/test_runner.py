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
    assert params == ["self", "command", "on_output", "on_finished"]
