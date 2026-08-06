"""§26 File ▸ Open Recent — the MRU store and the submenu built from it.

The submenu existed as an empty `menu.addMenu("Open Recent")` with no store
behind it. This covers: persistence through the window's own injectable
`QSettings`, the cap, pruning of files that no longer exist, and the rule that
an entry opens through the ONE existing project-open path.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import action_labels, find_action, find_top_menu

_MINIMAL_PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Project fileName="demo">\n'
    '  <Page fileName="p1" tableName="pr.equipment" caption="Equipment"/>\n'
    "</Project>\n"
)


def _ini_settings(tmp_path):
    return QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path, settings=None):
    window = MainWindow(
        generator_config_dir=tmp_path,
        settings=settings if settings is not None else _ini_settings(tmp_path),
    )
    qtbot.addWidget(window)
    return window


def _make_project(tmp_path, name="demo.pgtp"):
    path = tmp_path / name
    path.write_text(_MINIMAL_PGTP, encoding="utf-8", newline="")
    return path


def _recent_menu(window):
    return find_action(find_top_menu(window, "File"), "Open Recent").menu()


# -- the store --------------------------------------------------------------


def test_opening_a_project_records_it(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)

    window.open_project_file(str(path))

    assert window._recent_files() == [str(path)]


def test_the_list_is_most_recent_first_and_deduplicated(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    first = _make_project(tmp_path, "a.pgtp")
    second = _make_project(tmp_path, "b.pgtp")

    window.open_project_file(str(first))
    window.open_project_file(str(second))
    window.open_project_file(str(first))

    assert window._recent_files() == [str(first), str(second)]


def test_the_list_is_capped(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    paths = [_make_project(tmp_path, f"p{i}.pgtp") for i in range(15)]
    for path in paths:
        window.open_project_file(str(path))

    recent = window._recent_files()
    assert len(recent) == MainWindow._RECENT_FILES_MAX == 10
    # The most recent survive; the oldest fall off the tail.
    assert recent[0] == str(paths[-1])
    assert str(paths[0]) not in recent


def test_entries_whose_file_is_gone_are_dropped(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    kept = _make_project(tmp_path, "kept.pgtp")
    doomed = _make_project(tmp_path, "doomed.pgtp")
    window.open_project_file(str(doomed))
    window.open_project_file(str(kept))

    doomed.unlink()

    assert window._recent_files() == [str(kept)]


def test_the_list_persists_across_windows(qtbot, tmp_path):
    """Through the SAME injectable QSettings store the window already uses for
    geometry/theme. A FRESH QSettings on the same ini backs the second window, so
    the value really round-trips through the file (a single-element QStringList
    comes back as a bare string, which `_recent_files` handles)."""
    first_window = _window(qtbot, tmp_path, settings=_ini_settings(tmp_path))
    path = _make_project(tmp_path)
    first_window.open_project_file(str(path))
    first_window.close()

    second_window = _window(qtbot, tmp_path, settings=_ini_settings(tmp_path))

    assert second_window._recent_files() == [str(path)]
    assert action_labels(_recent_menu(second_window)) == ["demo.pgtp"]


def test_a_failed_open_is_not_recorded(qtbot, tmp_path, monkeypatch):
    """A file that would not parse is not something to offer re-opening."""
    from pgtp_editor.ui import modals

    monkeypatch.setattr(modals.QMessageBox, "critical", lambda *a, **k: None)
    window = _window(qtbot, tmp_path)
    broken = tmp_path / "broken.pgtp"
    broken.write_text("<Project><Page", encoding="utf-8")

    window.open_project_file(str(broken))

    assert window._recent_files() == []


def test_save_as_records_the_new_path(qtbot, tmp_path, monkeypatch):
    from pgtp_editor.ui import modals

    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    target = tmp_path / "saved-as.pgtp"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "")
    )

    window._save_project_as()

    assert window._recent_files() == [str(target)]


# -- the submenu ------------------------------------------------------------


def test_the_submenu_is_rebuilt_from_the_store_on_show(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    menu = _recent_menu(window)
    assert action_labels(menu) == ["(no recent files)"]

    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    menu.aboutToShow.emit()

    assert action_labels(menu) == ["demo.pgtp"]
    assert menu.actions()[0].toolTip() == str(path)


def test_a_vanished_file_disappears_from_the_submenu_on_next_show(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    menu = _recent_menu(window)
    menu.aboutToShow.emit()
    assert action_labels(menu) == ["demo.pgtp"]

    path.unlink()
    menu.aboutToShow.emit()

    assert action_labels(menu) == ["(no recent files)"]


def test_triggering_an_entry_goes_through_the_existing_open_path(qtbot, tmp_path):
    """`_open_pgtp_path` -- so §18.2's New/Open/Edit-Standalone chooser still
    applies and no second loader exists."""
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    opened = []
    window._open_pgtp_path = lambda target: opened.append(target)

    menu = _recent_menu(window)
    menu.aboutToShow.emit()
    menu.actions()[0].trigger()

    assert opened == [str(path)]


def test_each_entry_binds_its_own_path(qtbot, tmp_path):
    """Regression guard for the classic late-binding closure bug: every entry
    must open ITS file, not the last one in the loop."""
    window = _window(qtbot, tmp_path)
    first = _make_project(tmp_path, "a.pgtp")
    second = _make_project(tmp_path, "b.pgtp")
    window.open_project_file(str(first))
    window.open_project_file(str(second))
    opened = []
    window._open_pgtp_path = lambda target: opened.append(target)

    menu = _recent_menu(window)
    menu.aboutToShow.emit()
    for action in menu.actions():
        action.trigger()

    assert opened == [str(second), str(first)]


def test_the_submenu_is_never_offered_to_the_toolbar(qtbot, tmp_path):
    """§7: Open Recent's children are transient per-session entries and must
    never be pinnable."""
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    _recent_menu(window).aboutToShow.emit()

    ids = [command_id for command_id, _label in window._toolbar_ui.all_menu_commands()]

    assert not [i for i in ids if i.startswith("file.open-recent")]
