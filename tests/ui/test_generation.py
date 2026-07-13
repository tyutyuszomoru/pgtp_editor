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


from unittest.mock import patch

from pgtp_editor.generation.config import load_executable_path


def test_locate_generator_saves_chosen_path(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    exe = tmp_path / "PgPHPGeneratorPro.exe"
    exe.write_text("", encoding="utf-8")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(exe), "Executables (*.exe)"),
    ):
        window._locate_generator()

    assert load_executable_path(base_dir=tmp_path) == str(exe)
    assert window.statusBar().currentMessage() == f"PHP Generator set: {exe.name}"


def test_locate_generator_cancel_is_a_noop(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=("", ""),
    ):
        window._locate_generator()

    assert load_executable_path(base_dir=tmp_path) is None


def test_locate_generator_menu_action_is_wired(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    exe = tmp_path / "gen.exe"
    exe.write_text("", encoding="utf-8")
    menu = find_top_menu(window, "Generation")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getOpenFileName",
        return_value=(str(exe), "Executables (*.exe)"),
    ):
        find_action(menu, "Locate PHP Generator Executable...").trigger()

    assert load_executable_path(base_dir=tmp_path) == str(exe)


from PySide6.QtWidgets import QMessageBox

from pgtp_editor.generation.runner import build_generate_command


def _configured_window(qtbot, tmp_path, exe_name="gen.exe"):
    """A window with a configured exe and a fake runner injected."""
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=tmp_path, generator_runner=fake)
    qtbot.addWidget(window)
    exe = tmp_path / exe_name
    exe.write_text("", encoding="utf-8")
    from pgtp_editor.generation.config import save_executable_path
    save_executable_path(str(exe), base_dir=tmp_path)
    return window, fake, exe


def test_generate_with_no_open_project_stops(qtbot, tmp_path):
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=tmp_path, generator_runner=fake)
    qtbot.addWidget(window)
    # editor empty and no current project
    window._generate_php()
    assert fake.commands == []


def test_generate_with_no_configured_exe_shows_info_and_stops(qtbot, tmp_path):
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=tmp_path, generator_runner=fake)
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("<Project/>")

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._generate_php()

    assert mock_info.called
    assert fake.commands == []


def test_generate_happy_path_builds_and_runs_command(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    project_path = tmp_path / "proj.pgtp"
    window._current_project_path = str(project_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._generate_php()

    assert fake.commands == [build_generate_command(str(exe), str(project_path), str(out_dir))]
    assert window._current_output_folder == str(out_dir)


def test_generate_cancel_at_save_prompt_stops(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    window._current_project_path = str(tmp_path / "proj.pgtp")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Cancel,
    ):
        window._generate_php()

    assert fake.commands == []


def test_generate_cancel_at_output_folder_stops(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    window._current_project_path = str(tmp_path / "proj.pgtp")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value="",
    ):
        window._generate_php()

    assert fake.commands == []


def test_generate_streams_output_lines_into_audit_panel(qtbot, tmp_path):
    window, fake, exe = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    window._current_project_path = str(tmp_path / "proj.pgtp")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._generate_php()

    fake.emit_output("Generating page 1")
    fake.emit_output("Generating page 2")

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    assert "[PHP] Generating page 1" in texts
    assert "[PHP] Generating page 2" in texts


def test_generate_output_folder_prefilled_from_project_output_path(qtbot, tmp_path):
    from pgtp_editor.model.parser import load_project_from_text

    window, fake, exe = _configured_window(qtbot, tmp_path)
    out_attr = str(tmp_path / "declared_out")
    xml = f'<Project outputPath="{out_attr}"><Presentation><Pages/></Presentation></Project>'
    window.center_stage.xml_editor.setPlainText(xml)
    window._current_project = load_project_from_text(xml)
    window._current_project_path = str(tmp_path / "proj.pgtp")

    captured = {}

    def fake_dir(parent, caption, directory):
        captured["directory"] = directory
        return ""

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        side_effect=fake_dir,
    ):
        window._generate_php()

    assert captured["directory"] == out_attr
