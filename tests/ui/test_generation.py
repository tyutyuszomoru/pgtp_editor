from pgtp_editor.generation.runner import GeneratorRunner
from pgtp_editor.ui.main_window import MainWindow


class FakeRunner:
    """Records the command and lets a test drive on_output/on_finished by hand.
    Mirrors GeneratorRunner.run's signature exactly (no real process spawned)."""

    def __init__(self):
        self.commands = []
        self._on_output = None
        self._on_finished = None

    def run(self, command, on_output, on_finished):
        self.commands.append(command)
        self._on_output = on_output
        self._on_finished = on_finished

    def emit_output(self, line):
        self._on_output(line)

    def emit_finished(self, exit_code):
        self._on_finished(exit_code)


def test_defaults_to_a_real_generator_runner(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    assert isinstance(window._generator_runner, GeneratorRunner)


def test_injected_runner_and_config_dir_are_stored(qtbot, tmp_path):
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=tmp_path, generator_runner=fake)
    qtbot.addWidget(window)
    assert window._generator_runner is fake
    assert window._generator_config_dir == tmp_path


def test_output_folder_starts_unset(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    assert window._current_output_folder is None
