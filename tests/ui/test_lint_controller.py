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
"""`ui/lint_controller.py` — the §22 host side that was missing.

**No `php` process is ever spawned here.** Every test injects either a whole
`LintService` stand-in or a fake `runner` into a real `LintService`, which is
precisely the seam `lint/service.py` documents for the purpose. Every modal is
behind an injected seam (`choose_executable`) or a patched
`pgtp_editor.ui.modals` attribute, and the whole lane runs headless off a
hand-built `UiShell` — never a `MainWindow`.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QListWidget, QWidget

from pgtp_editor.lint.config import load_lint_executable_path
from pgtp_editor.lint.findings import (
    LINT_AUDIT_TARGET,
    LINT_PREFIX,
    LintAuditLine,
    LintFinding,
    LintOutcome,
    LintStatus,
)
from pgtp_editor.lint.runner import LintProcessResult
from pgtp_editor.lint.service import LintService
from pgtp_editor.ui import modals
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.lint_controller import (
    LINT_LINE_ROLE,
    LINT_ON_SAVE_SETTINGS_KEY,
    LINT_TAB_KEY_ROLE,
    LINT_TARGET_ROLE,
    LintController,
)
from pgtp_editor.ui.software_settings_dialog import EXTERNAL_TOOLS_SETTINGS_PATH
from pgtp_editor.ui.ui_shell import UiShell


def _sync_run(fn, on_result=None, on_error=None, **kwargs):
    try:
        result = fn(**kwargs)
    except BaseException as exc:  # noqa: BLE001 -- mirrors run_async's contract
        if on_error is not None:
            on_error(exc)
        return
    if on_result is not None:
        on_result(result)


@pytest.fixture
def shell(qtbot, tmp_path):
    parent = QWidget()
    qtbot.addWidget(parent)
    stage = CenterStage()
    qtbot.addWidget(stage)
    audit = QListWidget()
    qtbot.addWidget(audit)
    messages: list[str] = []
    built = UiShell(
        window=parent,
        stage=stage,
        audit=audit,
        status=lambda text="", *rest: messages.append(str(text)),
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
        run_async=_sync_run,
        default_dir=lambda: "",
        reveal_left_panel=lambda widget: None,
        set_left_panel_visible=lambda widget, visible: None,
        reveal_raw_xml=lambda: None,
        is_light_theme=lambda: False,
    )
    return built, messages


@pytest.fixture
def controller(shell, tmp_path):
    built, messages = shell
    ctl = LintController(built, config_dir=tmp_path / "cfg")
    return ctl, built, messages


def _open_tab(shell_obj, ctl, path=None, text="<?php echo 1;"):
    """A PHP tab wired the way the host wires one, with a synchronous
    `run_async` so `request_lint` resolves inside the test."""
    tab = shell_obj.stage.open_php_file_tab(path, text)
    key = shell_obj.stage.php_file_tab_key(tab)
    ctl.attach_tab(tab, key)
    tab._run_async = _sync_run
    return tab, key


def _rows(audit):
    return [audit.item(i).text() for i in range(audit.count())]


def _service_returning(outcome):
    class _Stub:
        def lint_text(self, text, display_name=""):
            return outcome.with_display_name(display_name)

    return _Stub()


# -- the one service, and the tab_lint_settings seam --------------------------


def test_the_controller_owns_one_real_lint_service(controller):
    ctl, _built, _messages = controller
    assert isinstance(ctl.service, LintService)
    assert ctl.service is ctl.tab_lint_settings()[0]


def test_tab_lint_settings_is_what_the_php_lane_passes_to_open_php_file_tab(controller):
    ctl, _built, _messages = controller
    service, on_save = ctl.tab_lint_settings()
    assert service is ctl.service
    assert on_save is False


def test_the_service_reads_the_injected_config_dir_not_the_real_appdata(
    controller, tmp_path
):
    """§22 reuses §19's `generator_config.json`, and the base_dir override with
    it -- a test must never read or write the developer's real AppData file."""
    ctl, _built, _messages = controller
    assert ctl.service.configured_executable() is None

    from pgtp_editor.lint.config import save_lint_executable_path

    save_lint_executable_path("/usr/bin/php", base_dir=tmp_path / "cfg")
    assert ctl.service.configured_executable() == "/usr/bin/php"


# -- the on-save toggle -------------------------------------------------------


def test_lint_on_save_defaults_off_and_persists_when_flipped(controller, shell):
    ctl, built, _messages = controller
    assert ctl.lint_on_save is False

    ctl.set_lint_on_save(True)

    assert ctl.lint_on_save is True
    assert built.settings.value(LINT_ON_SAVE_SETTINGS_KEY, False, type=bool) is True


def test_a_persisted_toggle_is_restored_on_construction(shell, tmp_path):
    built, _messages = shell
    built.settings.setValue(LINT_ON_SAVE_SETTINGS_KEY, True)

    assert LintController(built, config_dir=tmp_path).lint_on_save is True


def test_flipping_the_toggle_reaches_tabs_that_are_already_open(controller):
    """A preference the user flips must not need every tab reopened."""
    ctl, built, _messages = controller
    first, _ = _open_tab(built, ctl)
    second, _ = _open_tab(built, ctl, text="<?php echo 2;")

    ctl.set_lint_on_save(True)
    assert first.lint_on_save is True and second.lint_on_save is True

    ctl.set_lint_on_save(False)
    assert first.lint_on_save is False and second.lint_on_save is False


# -- attach_tab ---------------------------------------------------------------


def test_attach_tab_hands_over_the_service_and_the_current_toggle(controller):
    ctl, built, _messages = controller
    ctl.set_lint_on_save(True)

    tab, _key = _open_tab(built, ctl)

    assert tab.lint_service is ctl.service
    assert tab.lint_on_save is True


def test_attach_tab_connects_lint_reported_to_the_audit_panel(controller):
    ctl, built, _messages = controller
    tab, _key = _open_tab(built, ctl)

    tab.lint_reported.emit([LintAuditLine(f"{LINT_PREFIX}hello", 4)])

    assert _rows(built.audit) == [f"{LINT_PREFIX}hello"]


# -- Tools ▸ Lint Current File -----------------------------------------------


def test_lint_with_no_php_tab_active_says_so_instead_of_staying_silent(controller):
    """§22's worst failure is silence read as "clean"."""
    ctl, built, messages = controller

    assert ctl.lint_active_file() is False
    rows = _rows(built.audit)
    assert len(rows) == 1
    assert rows[0].startswith(LINT_PREFIX)
    assert "no custom-PHP tab is active" in rows[0]
    assert any("no custom-PHP tab is active" in m for m in messages)


def test_the_not_run_row_is_inert_rather_than_navigating_nowhere(controller):
    ctl, built, _messages = controller
    ctl.lint_active_file()
    item = built.audit.item(0)
    assert item.data(LINT_LINE_ROLE) is None
    assert item.data(LINT_TARGET_ROLE) is None


def test_findings_reach_the_audit_panel_verbatim_and_navigably(controller):
    ctl, built, _messages = controller
    tab, key = _open_tab(built, ctl, text="<?php echo\n")
    tab.set_lint_service(
        _service_returning(
            LintOutcome(
                status=LintStatus.FINDINGS,
                findings=(
                    LintFinding(line=2, message="syntax error, unexpected end of file"),
                ),
            )
        )
    )

    assert ctl.lint_active_file() is True

    rows = _rows(built.audit)
    assert all(row.startswith(LINT_PREFIX) for row in rows)
    assert any("ERROR line 2: syntax error, unexpected end of file" in r for r in rows)
    # findings.py appends its own "php -l stops at the FIRST error" note; the
    # host must append it verbatim and not re-word or drop it.
    assert any("stops at the FIRST syntax error" in r for r in rows)

    finding_item = next(
        built.audit.item(i)
        for i in range(built.audit.count())
        if built.audit.item(i).data(LINT_LINE_ROLE) is not None
    )
    assert finding_item.data(LINT_LINE_ROLE) == 2
    assert finding_item.data(LINT_TARGET_ROLE) == LINT_AUDIT_TARGET
    assert finding_item.data(LINT_TAB_KEY_ROLE) == key


def test_a_clean_file_produces_one_inert_ok_row(controller):
    ctl, built, _messages = controller
    tab, _key = _open_tab(built, ctl)
    tab.set_lint_service(_service_returning(LintOutcome(status=LintStatus.CLEAN)))

    ctl.lint_active_file()

    rows = _rows(built.audit)
    assert len(rows) == 1 and "OK: no syntax errors" in rows[0]
    assert built.audit.item(0).data(LINT_LINE_ROLE) is None


def test_an_unconfigured_linter_is_reported_not_swallowed(controller):
    """The real (unconfigured) service goes down `NOT_CONFIGURED`, and the row
    names the action that fixes it."""
    ctl, built, _messages = controller
    _open_tab(built, ctl)

    assert ctl.lint_active_file() is True

    rows = _rows(built.audit)
    assert rows and "no PHP linter is configured" in rows[0]
    # Re-pointed by FQ-260812025705, which removed the menu item this named.
    assert EXTERNAL_TOOLS_SETTINGS_PATH in rows[0]


def test_a_tab_opened_without_a_service_still_lints(controller):
    """The service is a window-level fact, so a tab that predates this lane (or
    was opened by a caller that passed no service) is adopted on demand."""
    ctl, built, _messages = controller
    tab = built.stage.open_php_file_tab(None, "<?php echo 1;")
    tab._run_async = _sync_run
    assert tab.lint_service is None

    ctl.lint_active_file()

    assert tab.lint_service is ctl.service


def test_a_linter_that_blows_up_is_reported_and_never_raises(controller):
    """§22 is advisory: nothing in this lane may raise into a slot, because the
    on-save hook runs inside an already-committed save."""
    ctl, built, _messages = controller
    tab, _key = _open_tab(built, ctl)

    def exploding_runner(executable, text, timeout):
        raise OSError("Permission denied")

    tab.set_lint_service(
        LintService(
            executable_provider=lambda: "/usr/bin/php",
            resolver=lambda configured: configured,
            runner=exploding_runner,
        )
    )

    ctl.lint_active_file()  # no exception

    rows = _rows(built.audit)
    assert rows and "could not be started" in rows[0]
    assert "Permission denied" in rows[0]


def test_a_real_service_with_a_fake_runner_parses_php_l_output(controller):
    """End-to-end through the real `LintService`/`findings.py` with only the
    subprocess replaced -- no `php` is spawned anywhere in this suite."""
    ctl, built, _messages = controller
    tab, _key = _open_tab(built, ctl, text="<?php echo\n")
    tab.set_lint_service(
        LintService(
            executable_provider=lambda: "/usr/bin/php",
            resolver=lambda configured: configured,
            runner=lambda executable, text, timeout: LintProcessResult(
                stdout="Parse error: syntax error, unexpected end of file in /tmp/x.php on line 2\n",
                stderr="",
                exit_code=255,
            ),
        )
    )

    ctl.lint_active_file()

    rows = _rows(built.audit)
    assert any("ERROR line 2:" in row for row in rows)
    # `with_display_name` must have replaced the linter's temp path.
    assert not any("/tmp/x.php" in row for row in rows)


def test_lint_on_save_runs_the_linter_after_a_successful_save(controller, tmp_path):
    ctl, built, _messages = controller
    path = tmp_path / "saved.php"
    path.write_text("<?php echo 1;", encoding="utf-8")
    ctl.set_lint_on_save(True)
    tab, _key = _open_tab(built, ctl, path=path)
    tab.set_lint_service(_service_returning(LintOutcome(status=LintStatus.CLEAN)))

    tab.editor.setPlainText("<?php echo 2;")
    tab.editor.document().setModified(True)
    assert tab.save() is True

    assert path.read_text(encoding="utf-8") == "<?php echo 2;"
    assert any("OK: no syntax errors" in row for row in _rows(built.audit))


def test_a_lint_failure_never_unwinds_the_save(controller, tmp_path):
    ctl, built, _messages = controller
    path = tmp_path / "saved.php"
    path.write_text("<?php echo 1;", encoding="utf-8")
    ctl.set_lint_on_save(True)
    tab, _key = _open_tab(built, ctl, path=path)

    class _Exploding:
        def lint_text(self, text, display_name=""):
            raise RuntimeError("the linter itself is broken")

    tab.set_lint_service(_Exploding())

    tab.editor.setPlainText("<?php echo 3;")
    tab.editor.document().setModified(True)

    assert tab.save() is True
    assert tab.is_dirty() is False
    assert path.read_text(encoding="utf-8") == "<?php echo 3;"
    assert any("could not be started" in row for row in _rows(built.audit))


# -- locating the linter (now driven by Software settings ▸ External tools) ---


def test_locate_linter_persists_the_path_into_section_19s_config_file(
    controller, tmp_path
):
    ctl, _built, messages = controller
    ctl._choose_executable = lambda: "/usr/bin/php"

    ctl.locate_linter()

    assert load_lint_executable_path(tmp_path / "cfg") == "/usr/bin/php"
    assert any("PHP linter set: php" in m for m in messages)


def test_locate_linter_preserves_the_generator_path_in_the_shared_file(
    controller, tmp_path
):
    """§19 and §22 share one JSON object; locating the linter must not silently
    un-configure the generator."""
    from pgtp_editor.generation.config import load_executable_path, save_executable_path

    ctl, _built, _messages = controller
    save_executable_path("/opt/phpgen.exe", base_dir=tmp_path / "cfg")
    ctl._choose_executable = lambda: "/usr/bin/php"

    ctl.locate_linter()

    assert load_executable_path(base_dir=tmp_path / "cfg") == "/opt/phpgen.exe"
    assert load_lint_executable_path(tmp_path / "cfg") == "/usr/bin/php"


def test_cancelling_locate_linter_changes_nothing(controller, tmp_path):
    ctl, _built, messages = controller
    ctl._choose_executable = lambda: ""

    ctl.locate_linter()

    assert load_lint_executable_path(tmp_path / "cfg") is None
    assert messages == []


def test_an_unwritable_config_reports_a_modal_instead_of_crashing(
    controller, monkeypatch
):
    ctl, _built, _messages = controller
    ctl._choose_executable = lambda: "/usr/bin/php"
    shown = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "critical",
        classmethod(lambda cls, *args, **kwargs: shown.append(args)),
    )
    monkeypatch.setattr(
        "pgtp_editor.ui.lint_controller.save_lint_executable_path",
        lambda path, base_dir=None: (_ for _ in ()).throw(OSError("disk full")),
    )

    ctl.locate_linter()

    assert shown and "disk full" in shown[0][-1]


# -- report() robustness ------------------------------------------------------


def test_report_tolerates_an_empty_or_none_batch(controller):
    ctl, built, _messages = controller
    ctl.report([])
    ctl.report(None)
    assert built.audit.count() == 0


def test_report_uses_the_check_channels_role_conventions(controller):
    """`[Lint]` deliberately borrows `_report_check_findings`' convention: the
    1-based line on `UserRole`, a routing target on `UserRole + 1`."""
    ctl, built, _messages = controller

    ctl.report([LintAuditLine(f"{LINT_PREFIX}x", 7)], "some-key")

    item = built.audit.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == 7
    assert item.data(Qt.ItemDataRole.UserRole + 1) == LINT_AUDIT_TARGET
    assert item.data(Qt.ItemDataRole.UserRole + 2) == "some-key"


# -- host wiring: the Tools entries that make §22 reachable --------------------


def _window(qtbot, tmp_path):
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow(
        settings=QSettings(str(tmp_path / "w.ini"), QSettings.Format.IniFormat),
        generator_config_dir=tmp_path / "cfg",
    )
    qtbot.addWidget(window)
    return window


def _tools(window):
    from tests.ui._menu_helpers import find_top_menu

    return find_top_menu(window, "Tools")


def test_tools_lint_current_file_reports_into_the_audit_panel(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action

    window = _window(qtbot, tmp_path)
    # FQ-260812025705 gates this entry on a configured linter, and a disabled
    # QAction does not fire — so the gesture has to be reachable before it can
    # be driven. Configuring it through the lane's own write path is also what a
    # user does now (from the External tools pane).
    window._lint_ui._choose_executable = lambda: "/usr/bin/php"
    window._lint_ui.locate_linter()
    action = find_action(_tools(window), "Lint Current File")
    assert action is not None
    assert action.isEnabled() is True

    action.trigger()

    rows = _rows(window.audit_panel)
    assert rows and rows[-1].startswith(LINT_PREFIX)
    assert "no custom-PHP tab is active" in rows[-1]


def test_tools_no_longer_offers_locate_php_linter(qtbot, tmp_path):
    """FQ-260812025705 MOVED it into `Settings ▸ Software settings… ▸ External
    tools`. Removed, not duplicated — so `Tools` must not still carry it."""
    from tests.ui._menu_helpers import action_labels, find_action

    window = _window(qtbot, tmp_path)

    assert find_action(_tools(window), "Locate PHP Linter…") is None
    assert not [label for label in action_labels(_tools(window)) if "Locate" in label]


def test_both_tools_lint_entries_are_greyed_until_a_linter_is_configured(
    qtbot, tmp_path
):
    """The greyed entry is what REPLACED the Locate menu item as the cue, so it
    has to carry the address in its tooltip — a dead command with no explanation
    would be strictly worse than the error-on-trigger it replaced."""
    from tests.ui._menu_helpers import find_action

    window = _window(qtbot, tmp_path)
    entries = [
        find_action(_tools(window), "Lint Current File"),
        find_action(_tools(window), "Lint on Save"),
    ]

    for action in entries:
        assert action.isEnabled() is False
        assert EXTERNAL_TOOLS_SETTINGS_PATH in action.toolTip()

    window._lint_ui._choose_executable = lambda: "/usr/bin/php"
    window._lint_ui.locate_linter()  # what the External tools pane calls

    for action in entries:
        assert action.isEnabled() is True
        # An empty tooltip makes `QAction.toolTip()` fall back to the action's
        # own text, so the assertion is that the REASON is gone, not that the
        # string is empty.
        assert EXTERNAL_TOOLS_SETTINGS_PATH not in action.toolTip()


def test_locating_the_linter_regates_the_entries_without_a_restart(qtbot, tmp_path):
    """The core of the feature is the LIVE refresh: the pane sets the binary and
    the menus must follow in the same gesture."""
    window = _window(qtbot, tmp_path)
    lint_entry_enabled = lambda: window._lint_action.isEnabled()
    assert lint_entry_enabled() is False

    window._lint_ui._choose_executable = lambda: "/usr/bin/php"
    window._lint_ui.locate_linter()

    assert lint_entry_enabled() is True


def test_tools_lint_on_save_is_checkable_and_persists(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action

    settings_path = tmp_path / "w.ini"
    window = _window(qtbot, tmp_path)
    action = find_action(_tools(window), "Lint on Save")
    assert action.isCheckable() is True
    assert action.isChecked() is False

    action.setChecked(True)

    assert window._lint_ui.lint_on_save is True
    stored = QSettings(str(settings_path), QSettings.Format.IniFormat)
    assert stored.value(LINT_ON_SAVE_SETTINGS_KEY, False, type=bool) is True


def test_the_menu_item_reflects_the_persisted_toggle_on_startup(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action

    settings = QSettings(str(tmp_path / "w.ini"), QSettings.Format.IniFormat)
    settings.setValue(LINT_ON_SAVE_SETTINGS_KEY, True)
    settings.sync()

    window = _window(qtbot, tmp_path)

    assert window._lint_ui.lint_on_save is True
    assert find_action(_tools(window), "Lint on Save").isChecked() is True


def test_a_php_tab_opened_in_the_real_window_gets_the_one_lint_service(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = tmp_path / "wired.php"
    path.write_text("<?php echo 1;", encoding="utf-8")

    tab = window._php_tabs.open_path(path)

    assert tab.lint_service is window._lint_ui.service


def test_a_lint_finding_clicked_in_the_audit_panel_navigates_to_the_php_tab(
    qtbot, tmp_path
):
    """§22's click-to-navigate, end to end through the host's audit router."""
    window = _window(qtbot, tmp_path)
    path = tmp_path / "nav.php"
    path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    tab = window._php_tabs.open_path(path)
    key = window.center_stage.php_file_tab_key(tab)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    window._lint_ui.report([LintAuditLine(f"{LINT_PREFIX}ERROR line 3: x", 3)], key)
    window._on_audit_item_clicked(window.audit_panel.item(window.audit_panel.count() - 1))

    assert window.center_stage.currentWidget() is tab
    assert tab.editor.textCursor().blockNumber() == 2
