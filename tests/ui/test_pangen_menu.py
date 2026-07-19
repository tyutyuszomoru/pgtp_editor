"""Generation-menu panGen / rePHPgen / Save reJSON actions (Task 8).

Fixture pattern mirrors tests/ui/test_generation.py: a FakeRunner is injected,
`_generator_config_dir` is a tmp override, and every modal (QMessageBox.*,
QFileDialog.*) is monkeypatched so no test reaches an un-patched modal.
"""
import json
import os

from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from pgtp_editor.generation.config import load_re_phpgen_root, save_re_phpgen_root
from pgtp_editor.ui.main_window import MainWindow


class FakeRunner:
    def __init__(self):
        self.calls = []          # (command, cwd, extra_env)
        self.pending = []        # on_finished callbacks in order

    def run(self, command, on_output, on_finished, cwd=None, extra_env=None):
        self.calls.append((command, cwd, extra_env))
        self.pending.append(on_finished)


def _make_root(tmp_path):
    """A folder that passes validate_re_phpgen_root (has src/re_phpgen)."""
    root = tmp_path / "re_root"
    (root / "src" / "re_phpgen").mkdir(parents=True)
    return root


def _configured_window(qtbot, tmp_path, with_root=True):
    """Window with a fake runner and (optionally) a valid re_phpgen root saved."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    fake = FakeRunner()
    window = MainWindow(generator_config_dir=cfg, generator_runner=fake)
    qtbot.addWidget(window)
    root = None
    if with_root:
        root = _make_root(tmp_path)
        save_re_phpgen_root(str(root), base_dir=cfg)
    else:
        # Save an explicitly invalid root so the runtime check fails
        # deterministically (the machine default may happen to exist locally).
        save_re_phpgen_root(str(tmp_path / "no_such_runtime"), base_dir=cfg)
    return window, fake, cfg, root


def _prep_project(window, tmp_path):
    window.center_stage.xml_editor.setPlainText("<Project/>")
    window._current_project_path = str(tmp_path / "proj.pgtp")


# --------------------------------------------------------------------------- #
# 1. _pangen runs the CLI with the right command/cwd/env.
# --------------------------------------------------------------------------- #
def test_pangen_runs_cli_with_command_cwd_and_pythonpath(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._pangen()

    assert len(fake.calls) == 1
    command, cwd, extra_env = fake.calls[0]
    assert command[1:4] == ["-m", "re_phpgen", "pangen"]
    assert command[-1].endswith("_pangen")
    assert cwd == str(root)
    assert extra_env["PYTHONPATH"].startswith(str(root / "src"))


def test_pangen_without_runtime_shows_guidance_and_stops(qtbot, tmp_path):
    window, fake, cfg, _ = _configured_window(qtbot, tmp_path, with_root=False)
    _prep_project(window, tmp_path)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._pangen()

    assert mock_info.called
    assert fake.calls == []


# --------------------------------------------------------------------------- #
# 2. _re_phpgen_analyze precondition: no vendor .php -> info + no runs.
# --------------------------------------------------------------------------- #
def test_analyze_without_vendor_php_shows_info_and_stops(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()  # empty: no .php

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ), patch(
        "pgtp_editor.ui.main_window.QMessageBox.information"
    ) as mock_info:
        window._re_phpgen_analyze()

    assert mock_info.called
    assert "vendor output" in mock_info.call_args.args[2]
    assert fake.calls == []


def test_analyze_rejects_pangen_output_folder_as_vendor_baseline(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    # Pick the _pangen subfolder itself as the "output" folder; it contains a
    # .php file (our own generated output) so the old vendor-php precondition
    # would have passed and compared _pangen against _pangen\_pangen nonsense.
    pangen_dir = tmp_path / "out" / "_pangen"
    pangen_dir.mkdir(parents=True)
    (pangen_dir / "page.php").write_text("<?php", encoding="utf-8")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(pangen_dir),
    ), patch(
        "pgtp_editor.ui.main_window.QMessageBox.information"
    ) as mock_info:
        window._re_phpgen_analyze()

    assert mock_info.called
    assert "panGen's own output" in mock_info.call_args.args[2]
    assert fake.calls == []


# --------------------------------------------------------------------------- #
# 3. _re_phpgen_analyze happy path + chaining + failure branch.
# --------------------------------------------------------------------------- #
def _valid_gap_json(path):
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "pages": 3,
                    "ok": 2,
                    "diff": 1,
                    "missing_vendor": 0,
                    "missing_ours": 0,
                    "error": 0,
                    "causes": {"whitespace": 1},
                }
            }
        ),
        encoding="utf-8",
    )


def test_analyze_chains_pangen_then_analyze_and_summarizes(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "page.php").write_text("<?php", encoding="utf-8")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._re_phpgen_analyze()

    # First call is pangen.
    assert len(fake.calls) == 1
    assert fake.calls[0][0][3] == "pangen"
    assert window._save_rejson_action.isEnabled() is False

    # pangen succeeds -> analyze is launched.
    fake.pending[0](0)
    assert len(fake.calls) == 2
    assert fake.calls[1][0][3] == "analyze"
    assert window._save_rejson_action.isEnabled() is False

    # analyze produces a gap JSON at the work path; firing its finished
    # callback summarizes it and enables the save action.
    _valid_gap_json(window._gap_json_work_path())
    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        fake.pending[1](0)

    assert window._is_generating is False
    assert window._save_rejson_action.isEnabled() is True
    assert window._last_gap_json == window._gap_json_work_path()
    assert "pages" in mock_info.call_args.args[2]


def test_analyze_pangen_failure_skips_analyze_and_warns(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "page.php").write_text("<?php", encoding="utf-8")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._re_phpgen_analyze()

    with patch("pgtp_editor.ui.main_window.QMessageBox.warning") as mock_warn:
        fake.pending[0](1)

    assert mock_warn.called
    assert len(fake.calls) == 1  # no analyze call
    assert window._is_generating is False


# --------------------------------------------------------------------------- #
# 4. _save_rejson copies the last gap JSON to the chosen target.
# --------------------------------------------------------------------------- #
def test_save_rejson_copies_last_gap_json(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    src = tmp_path / "last_gap.json"
    src.write_text('{"summary": {}}', encoding="utf-8")
    window._last_gap_json = src
    target = tmp_path / "saved_gap.json"

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(target), "JSON (*.json)"),
    ):
        window._save_rejson()

    assert target.read_text(encoding="utf-8") == '{"summary": {}}'


def test_save_rejson_without_gap_json_is_a_noop(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    assert window._last_gap_json is None

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName"
    ) as mock_save:
        window._save_rejson()

    assert not mock_save.called
    assert "rePHPgen" in window.statusBar().currentMessage()


# --------------------------------------------------------------------------- #
# 5. _locate_pangen_runtime rejects invalid, accepts valid.
# --------------------------------------------------------------------------- #
def test_locate_runtime_rejects_invalid_dir(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path, with_root=False)
    bad = tmp_path / "not_a_repo"
    bad.mkdir()

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(bad),
    ), patch("pgtp_editor.ui.main_window.QMessageBox.warning") as mock_warn:
        window._locate_pangen_runtime()

    assert mock_warn.called
    # Nothing valid saved: still the machine default (bad root not persisted).
    assert load_re_phpgen_root(base_dir=cfg) != str(bad)


def test_locate_runtime_accepts_valid_dir(qtbot, tmp_path):
    window, fake, cfg, _ = _configured_window(qtbot, tmp_path, with_root=False)
    root = _make_root(tmp_path)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(root),
    ):
        window._locate_pangen_runtime()

    assert load_re_phpgen_root(base_dir=cfg) == str(root)


# --------------------------------------------------------------------------- #
# 6. PYTHONPATH merge-prepend preserves the user's pre-existing entries.
# --------------------------------------------------------------------------- #
def test_pythonpath_merge_prepends_user_entries(qtbot, tmp_path, monkeypatch):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    monkeypatch.setenv("PYTHONPATH", r"C:\userlibs")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._pangen()

    extra_env = fake.calls[0][2]
    assert extra_env["PYTHONPATH"] == str(root / "src") + os.pathsep + r"C:\userlibs"


# --------------------------------------------------------------------------- #
# Menu wiring.
# --------------------------------------------------------------------------- #
def test_generation_menu_has_new_actions(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    menu = find_top_menu(window, "Generation")

    assert find_action(menu, "Locate panGen Runtime...") is not None
    assert find_action(menu, "panGen (Generate Own PHP)") is not None
    assert find_action(menu, "rePHPgen (Analyze Gap)") is not None
    assert find_action(menu, "Save reJSON...") is not None
    # Save reJSON starts disabled.
    assert find_action(menu, "Save reJSON...").isEnabled() is False


# --------------------------------------------------------------------------- #
# 7. _prepare_generation_run preamble guards (shared by panGen + rePHPgen).
# --------------------------------------------------------------------------- #
def test_pangen_blocked_while_generation_in_flight(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    window._is_generating = True

    # The in-flight guard fires before any dialog is reached, so nothing to patch.
    window._pangen()

    assert fake.calls == []
    assert "already in progress" in window.statusBar().currentMessage()


def test_pangen_without_open_project_stops(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    # No project loaded and the XML editor is empty: guard fires before dialogs.
    window.center_stage.xml_editor.setPlainText("")
    window._current_project = None
    window._current_project_path = None

    window._pangen()

    assert fake.calls == []
    assert "Open a project first" in window.statusBar().currentMessage()


def test_pangen_cancel_save_prompt_stops(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Cancel,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory"
    ) as mock_dir:
        window._pangen()

    assert fake.calls == []
    # Cancelling the save prompt short-circuits before the folder dialog.
    assert not mock_dir.called
    assert window._is_generating is False


def test_pangen_cancel_output_folder_stops(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value="",  # user cancelled the folder dialog
    ):
        window._pangen()

    assert fake.calls == []
    assert window._is_generating is False


def test_pangen_saveall_uses_save_as_and_runs(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    saved_pgtp = tmp_path / "saved.pgtp"

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.SaveAll,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(saved_pgtp), "PGTP files (*.pgtp)"),
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._pangen()

    assert len(fake.calls) == 1
    command = fake.calls[0][0]
    # SaveAll routed through _save_project_as, which set the project path used
    # to build the pangen command.
    assert str(saved_pgtp) in command
    assert saved_pgtp.is_file()


# --------------------------------------------------------------------------- #
# 8. _on_pangen_finished failure branch for the standalone panGen action.
# --------------------------------------------------------------------------- #
def test_pangen_nonzero_exit_warns_and_clears_flag(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._pangen()

    assert window._is_generating is True  # runner is "running"
    with patch("pgtp_editor.ui.main_window.QMessageBox.warning") as mock_warn:
        fake.pending[0](3)

    assert mock_warn.called
    assert window._is_generating is False
    assert "exit 3" in window.statusBar().currentMessage()


# --------------------------------------------------------------------------- #
# 9. rePHPgen analyze-step failure branch (pangen ok, analyze non-zero).
# --------------------------------------------------------------------------- #
def test_analyze_step_failure_warns_and_leaves_save_disabled(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "page.php").write_text("<?php", encoding="utf-8")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._re_phpgen_analyze()

    fake.pending[0](0)  # pangen succeeds -> analyze launched
    assert len(fake.calls) == 2
    with patch("pgtp_editor.ui.main_window.QMessageBox.warning") as mock_warn:
        fake.pending[1](2)  # analyze fails

    assert mock_warn.called
    assert window._is_generating is False
    assert window._save_rejson_action.isEnabled() is False
    assert window._last_gap_json is None


def test_analyze_without_runtime_shows_guidance_and_stops(qtbot, tmp_path):
    window, fake, cfg, _ = _configured_window(qtbot, tmp_path, with_root=False)
    _prep_project(window, tmp_path)

    with patch("pgtp_editor.ui.main_window.QMessageBox.information") as mock_info:
        window._re_phpgen_analyze()

    assert mock_info.called
    assert fake.calls == []


# --------------------------------------------------------------------------- #
# 10. The analyze command targets the same work path that summarize reads.
# --------------------------------------------------------------------------- #
def test_analyze_command_json_matches_work_path(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    _prep_project(window, tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "page.php").write_text("<?php", encoding="utf-8")

    with patch(
        "pgtp_editor.ui.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Save,
    ), patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value=str(out_dir),
    ):
        window._re_phpgen_analyze()

    fake.pending[0](0)  # launch analyze
    analyze_cmd = fake.calls[1][0]
    assert analyze_cmd[3] == "analyze"
    # The --json argument is the same file summarize_gap_json / Save reJSON use.
    json_arg = analyze_cmd[analyze_cmd.index("--json") + 1]
    assert json_arg == str(window._gap_json_work_path())
    # --ours is the _pangen sibling of the chosen vendor output folder.
    ours_arg = analyze_cmd[analyze_cmd.index("--ours") + 1]
    assert ours_arg.endswith("_pangen")
    assert analyze_cmd[analyze_cmd.index("--vendor") + 1] == str(out_dir)


# --------------------------------------------------------------------------- #
# 11. Dialog-cancel no-ops for Save reJSON and Locate runtime.
# --------------------------------------------------------------------------- #
def test_save_rejson_cancel_dialog_writes_nothing(qtbot, tmp_path):
    window, fake, cfg, root = _configured_window(qtbot, tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    src = work / "last_gap.json"
    src.write_text('{"summary": {}}', encoding="utf-8")
    window._last_gap_json = src

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=("", ""),  # user cancelled
    ):
        window._save_rejson()  # must not raise

    # No target file was written next to the project; source untouched.
    assert list(tmp_path.glob("*_gap.json")) == []
    assert src.read_text(encoding="utf-8") == '{"summary": {}}'


def test_locate_runtime_cancel_dialog_is_noop(qtbot, tmp_path):
    window, fake, cfg, _ = _configured_window(qtbot, tmp_path, with_root=False)
    before = load_re_phpgen_root(base_dir=cfg)

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getExistingDirectory",
        return_value="",  # cancelled
    ), patch("pgtp_editor.ui.main_window.QMessageBox.warning") as mock_warn:
        window._locate_pangen_runtime()

    assert not mock_warn.called
    assert load_re_phpgen_root(base_dir=cfg) == before
