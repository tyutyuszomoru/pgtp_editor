"""FQ-010 — the startup launcher: four groups, suppression, and the two hard
constraints that keep it out of the suite's way.

The lane lives in `ui/launcher_dialog.py`. Tests drive `LauncherDialog`'s seam
(`entry_ids`, `choose`, `cancel`, `set_suppressed`) and pass `exec_dialog=` to
`show_launcher` — **no test calls `.exec()`**, and no test lets a launcher-picked
action actually open a real modal (every action is a stand-in unless the test is
specifically checking identity with the menu's own QAction).

`main()`-side coverage (the seam, the `--mcp` unreachability, `args.file`) is in
`tests/test_main.py`.
"""
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog

from pgtp_editor.ui.launcher_dialog import (
    LAUNCHER_GROUPS,
    LAUNCHER_SUPPRESSED_SETTINGS_KEY,
    LauncherDialog,
    launcher_suppressed,
    resolve_menu_entries,
    set_launcher_suppressed,
    show_launcher,
)
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import find_action, find_top_menu


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


def _fake_entries(command_ids, fired=None):
    """`command_id -> (label, QAction)` with recording actions, so a test never
    triggers a real File/Schema/Generation slot."""
    entries = {}
    for command_id in command_ids:
        action = QAction(command_id)
        if fired is not None:
            action.triggered.connect(
                lambda _checked=False, cid=command_id: fired.append(cid)
            )
        entries[command_id] = (command_id.replace(".", " › "), action)
    return entries


def _all_group_ids():
    return [cid for _title, ids in LAUNCHER_GROUPS for cid in ids]


# -- the four groups ---------------------------------------------------------


def test_there_are_exactly_four_groups():
    assert len(LAUNCHER_GROUPS) == 4
    assert [title for title, _ids in LAUNCHER_GROUPS] == [
        "Open a pgtp for editing",
        "New Project / Open Project",
        "Open other files",
        "Maintenance mode",
    ]


def test_group_membership_is_the_owners_taxonomy():
    groups = dict(LAUNCHER_GROUPS)
    assert groups["Open a pgtp for editing"] == ("file.open",)
    assert groups["New Project / Open Project"] == (
        "file.new-project",
        "file.open-project",
    )
    assert groups["Open other files"] == ("file.open-php-file",)


def test_maintenance_group_is_xsd_plus_the_four_section_20_entries():
    """Owner's ruling: XSD only, plus the §20 re_phpgen/panGen entries. §19's
    vendor PHP-generation entries are OUT — they are ordinary development."""
    groups = dict(LAUNCHER_GROUPS)
    assert groups["Maintenance mode"] == (
        "schema.edit-xsd",
        "schema.edit-autoxsd",
        "schema.verify-xsd",
        "schema.export-xsd",
        "schema.import-xsd",
        "generation.locate-pangen-runtime",
        "generation.pangen-generate-own-php",
        "generation.rephpgen-analyze-gap",
        "generation.save-rejson",
    )


@pytest.mark.parametrize(
    "excluded",
    [
        "generation.locate-php-generator-executable",
        "generation.generate-php",
        "generation.open-output-folder",
    ],
)
def test_section_19_vendor_generation_is_not_in_any_group(excluded):
    assert excluded not in _all_group_ids()


def test_every_group_id_resolves_to_a_real_menu_action(qtbot, tmp_path):
    """The launcher never reimplements a gesture: every id must name a live menu
    command, and the entry must BE the menu's own QAction."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    entries = resolve_menu_entries(window)
    missing = [cid for cid in _all_group_ids() if cid not in entries]
    assert missing == []
    _label, open_action = entries["file.open"]
    assert open_action is find_action(find_top_menu(window, "File"), "Open...")


def test_dialog_offers_every_group_id_in_order():
    entries = _fake_entries(_all_group_ids())
    dialog = LauncherDialog(entries)
    assert dialog.entry_ids() == _all_group_ids()


def test_dialog_labels_are_the_menu_path_labels():
    entries = _fake_entries(["file.open"])
    dialog = LauncherDialog(entries)
    assert dialog.button_for("file.open").text() == "file › open"


def test_a_disabled_menu_action_gives_a_disabled_button():
    """Shares the menu item's enabled state: `Generation ▸ Save reJSON…` starts
    disabled, and a button that looks clickable but does nothing is worse."""
    entries = _fake_entries(["file.open", "generation.save-rejson"])
    entries["generation.save-rejson"][1].setEnabled(False)
    dialog = LauncherDialog(
        entries,
        groups=(("G", ("file.open", "generation.save-rejson")),),
    )
    assert dialog.button_for("file.open").isEnabled() is True
    assert dialog.button_for("generation.save-rejson").isEnabled() is False


def test_a_group_whose_ids_are_all_missing_is_dropped_not_crashed():
    """Defensive: a renamed menu must never stop the app from starting."""
    dialog = LauncherDialog(
        _fake_entries(["file.open"]),
        groups=(("Real", ("file.open",)), ("Gone", ("nope.nothing",))),
    )
    assert dialog.entry_ids() == ["file.open"]


# -- picking an entry --------------------------------------------------------


def test_choosing_an_entry_accepts_and_records_it():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    dialog.choose("file.open")
    assert dialog.chosen_command_id == "file.open"
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_choose_does_not_trigger_the_action_itself():
    """The action fires only once the modal is down (`show_launcher`), so an
    action that opens its own QFileDialog is never stacked on the launcher."""
    fired = []
    dialog = LauncherDialog(_fake_entries(["file.open"], fired))
    dialog.choose("file.open")
    assert fired == []


def test_choosing_an_unknown_id_is_ignored():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    dialog.choose("file.nonsense")
    assert dialog.chosen_command_id is None


def test_show_launcher_triggers_the_chosen_action_and_returns_its_id(tmp_path):
    fired = []
    entries = _fake_entries(_all_group_ids(), fired)
    settings = _ini_settings(tmp_path)
    chosen = show_launcher(
        None,
        settings,
        resolve_entries=lambda _window: entries,
        exec_dialog=lambda dialog: dialog.choose("file.new-project"),
    )
    assert chosen == "file.new-project"
    assert fired == ["file.new-project"]


def test_show_launcher_runs_the_menus_own_action(qtbot, tmp_path):
    """End-to-end against a real window: picking group 1 triggers `File ▸
    Open...`, whose slot is replaced so no QFileDialog is reached."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    opened = []
    window._doc_ui.open_dialog = lambda: opened.append(True)
    show_launcher(
        window,
        window._settings,
        exec_dialog=lambda dialog: dialog.choose("file.open"),
    )
    assert opened == [True]


# -- Escape / close: land in the app, never quit -----------------------------


def test_cancel_rejects_with_no_pick():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    dialog.cancel()
    assert dialog.chosen_command_id is None
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_escape_lands_in_the_app_rather_than_quitting(qtbot, tmp_path):
    """FQ-010: cancelling must leave the window up and running. Nothing here
    closes, hides or quits anything — the app is simply still there."""
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()
    fired = []
    result = show_launcher(
        window,
        window._settings,
        resolve_entries=lambda _w: _fake_entries(_all_group_ids(), fired),
        exec_dialog=lambda dialog: dialog.cancel(),
    )
    assert result is None
    assert fired == []
    assert window.isVisible() is True


def test_close_button_is_wired_to_reject():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    dialog.button_box.rejected.emit()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.chosen_command_id is None


# -- suppression -------------------------------------------------------------


def test_suppression_defaults_to_off(tmp_path):
    assert launcher_suppressed(_ini_settings(tmp_path)) is False


def test_suppression_round_trips_through_a_fresh_settings_object(tmp_path):
    """The ini backend hands booleans back as "true"/"false" strings, so the
    reader must go through `type=bool` — this is what proves it does."""
    settings = _ini_settings(tmp_path)
    set_launcher_suppressed(settings, True)
    settings.sync()
    reread = _ini_settings(tmp_path)
    assert reread.value(LAUNCHER_SUPPRESSED_SETTINGS_KEY) in ("true", True)
    assert launcher_suppressed(reread) is True

    set_launcher_suppressed(reread, False)
    reread.sync()
    assert launcher_suppressed(_ini_settings(tmp_path)) is False


def test_ticking_the_box_and_closing_persists_the_choice(tmp_path):
    settings = _ini_settings(tmp_path)
    show_launcher(
        None,
        settings,
        resolve_entries=lambda _w: _fake_entries(["file.open"]),
        exec_dialog=lambda dialog: (dialog.set_suppressed(True), dialog.cancel()),
    )
    assert launcher_suppressed(settings) is True


def test_ticking_the_box_and_picking_an_entry_also_persists(tmp_path):
    """Read on EVERY exit path, not just cancel."""
    settings = _ini_settings(tmp_path)
    fired = []
    show_launcher(
        None,
        settings,
        resolve_entries=lambda _w: _fake_entries(["file.open"], fired),
        exec_dialog=lambda dialog: (
            dialog.set_suppressed(True),
            dialog.choose("file.open"),
        ),
    )
    assert launcher_suppressed(settings) is True
    assert fired == ["file.open"]


def test_a_suppressed_launcher_is_not_shown_at_all(tmp_path):
    settings = _ini_settings(tmp_path)
    set_launcher_suppressed(settings, True)
    shown = []
    assert (
        show_launcher(
            None,
            settings,
            resolve_entries=lambda _w: shown.append(True) or {},
            exec_dialog=lambda dialog: shown.append("exec"),
        )
        is None
    )
    assert shown == []


def test_the_dialog_starts_with_the_persisted_state_unticked_by_default():
    dialog = LauncherDialog(_fake_entries(["file.open"]))
    assert dialog.suppress_requested is False


def test_force_bypasses_suppression(tmp_path):
    """What `File ▸ Show Launcher…` passes, so the tick is never a one-way door."""
    settings = _ini_settings(tmp_path)
    set_launcher_suppressed(settings, True)
    execs = []
    show_launcher(
        None,
        settings,
        force=True,
        resolve_entries=lambda _w: _fake_entries(["file.open"]),
        exec_dialog=lambda dialog: execs.append(True),
    )
    assert execs == [True]


def test_showing_it_forced_and_unticking_clears_the_flag(tmp_path):
    settings = _ini_settings(tmp_path)
    set_launcher_suppressed(settings, True)
    show_launcher(
        None,
        settings,
        force=True,
        resolve_entries=lambda _w: _fake_entries(["file.open"]),
        exec_dialog=lambda dialog: (dialog.set_suppressed(False), dialog.cancel()),
    )
    assert launcher_suppressed(settings) is False


# -- the hard constraint: MainWindow construction never reaches a modal ------


def test_constructing_a_main_window_never_shows_the_launcher(
    qtbot, tmp_path, monkeypatch
):
    """FQ-010's first hard constraint. 49 test files construct a MainWindow; if
    the launcher were shown from __init__ every one of them would hang."""
    import pgtp_editor.ui.launcher_dialog as launcher_mod

    def _boom(*args, **kwargs):
        raise AssertionError("MainWindow.__init__ must never show the launcher")

    monkeypatch.setattr(launcher_mod, "show_launcher", _boom)
    monkeypatch.setattr(launcher_mod.LauncherDialog, "exec", _boom, raising=False)

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()
    assert window.isVisible() is True


def test_show_launcher_menu_entry_forces_it(qtbot, tmp_path, monkeypatch):
    """`File ▸ Show Launcher…` is the reversibility escape hatch: a USER-
    triggered modal, and it always passes force=True."""
    import pgtp_editor.ui.launcher_dialog as launcher_mod

    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    set_launcher_suppressed(window._settings, True)

    calls = []
    monkeypatch.setattr(
        launcher_mod,
        "show_launcher",
        lambda win, settings, **kwargs: calls.append((win, settings, kwargs)),
    )
    find_action(find_top_menu(window, "File"), "Show Launcher…").trigger()

    assert len(calls) == 1
    win, settings, kwargs = calls[0]
    assert win is window
    assert settings is window._settings
    assert kwargs == {"force": True}
