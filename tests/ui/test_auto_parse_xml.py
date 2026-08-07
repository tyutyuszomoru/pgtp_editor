"""§9 Edit ▸ Auto Parse XML — the checkable toggle, the `blockCountChanged`
listener, the 400 ms debounce, and `PgtpDocumentController.reparse(silent=True)`'s
status-bar-only failure mode.

The whole point of `silent=True` is that a failure fires WHILE THE USER IS
TYPING, so it must not raise a modal and must not move the caret. Every test
here that provokes a parse failure would hang on an unpatched `QMessageBox`, so
the modal is monkeypatched to a recorder and asserted NOT to have been called.
"""
from pgtp_editor.ui import modals
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.pgtp_document_controller import PgtpDocumentController
from tests.ui._menu_helpers import find_action, find_top_menu

_MINIMAL_PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Project fileName="demo">\n'
    '  <Page fileName="p1" tableName="pr.equipment" caption="Equipment"/>\n'
    "</Project>\n"
)


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    return window


def _no_modals(monkeypatch):
    """Replace the reparse-failure modal with a call recorder."""
    calls = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "critical",
        lambda *args, **kwargs: calls.append(args),
    )
    return calls


# -- the menu item ----------------------------------------------------------


def test_auto_parse_action_is_checkable_and_off_by_default(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    # Moved off the (now dissolved) Edit menu onto the Editor menu bar's
    # Parsing menu (FQ-016).
    action = find_action(find_top_menu(window, "Parsing"), "Auto Parse XML")
    assert action is not None
    assert action.isCheckable() is True
    assert action.isChecked() is False
    assert window._auto_parse_action is action


def test_auto_parse_state_is_not_persisted(qtbot, tmp_path):
    """§9: in-memory only -- no QSettings key, so it always starts unchecked."""
    window = _window(qtbot, tmp_path)
    window._auto_parse_action.setChecked(True)
    window.close()

    second = _window(qtbot, tmp_path)
    assert second._auto_parse_action.isChecked() is False
    keys = list(second._settings.allKeys())
    assert not [k for k in keys if "autoparse" in k.lower().replace("_", "")]


# -- the debounce -----------------------------------------------------------


def test_timer_is_a_400ms_single_shot(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._auto_parse_timer.isSingleShot() is True
    assert window._auto_parse_timer.interval() == 400


def test_block_count_change_does_nothing_while_the_toggle_is_off(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project>\n</Project>\n")
    assert window._auto_parse_timer.isActive() is False


def test_block_count_change_starts_the_timer_when_enabled(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._auto_parse_action.setChecked(True)

    # setPlainText changes the line count, so blockCountChanged fires.
    window.center_stage.xml_editor.setPlainText("<Project>\n</Project>\n")

    assert window._auto_parse_timer.isActive() is True


def test_the_timer_restarts_rather_than_queueing_a_second_run(qtbot, tmp_path):
    """A burst of edits must produce ONE reparse after it settles."""
    window = _window(qtbot, tmp_path)
    window._auto_parse_action.setChecked(True)
    window.center_stage.xml_editor.setPlainText("<Project>\n</Project>\n")
    timer = window._auto_parse_timer
    window._on_editor_block_count_changed(5)
    window._on_editor_block_count_changed(6)
    # Still exactly one single-shot timer, still pending.
    assert window._auto_parse_timer is timer
    assert timer.isActive() is True


def test_programmatic_text_sets_never_trigger_auto_parse(qtbot, tmp_path):
    """`_loading` / `_restoring` are the same guards that gate snapshot capture,
    so file open, revert and an undo/redo restore cannot auto-parse."""
    window = _window(qtbot, tmp_path)
    window._auto_parse_action.setChecked(True)

    window._loading = True
    window._on_editor_block_count_changed(3)
    assert window._auto_parse_timer.isActive() is False

    window._loading = False
    window._restoring = True
    window._on_editor_block_count_changed(4)
    assert window._auto_parse_timer.isActive() is False


def test_turning_the_toggle_off_cancels_a_pending_reparse(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._auto_parse_action.setChecked(True)
    window.center_stage.xml_editor.setPlainText("<Project>\n</Project>\n")
    assert window._auto_parse_timer.isActive() is True

    window._auto_parse_action.setChecked(False)

    assert window._auto_parse_timer.isActive() is False


def test_fire_time_handler_re_checks_the_toggle(qtbot, tmp_path, monkeypatch):
    """The toggle can flip during the 400 ms window."""
    window = _window(qtbot, tmp_path)
    calls = []
    monkeypatch.setattr(
        PgtpDocumentController, "reparse", lambda self, **kw: calls.append(kw)
    )
    window._auto_parse_now()
    assert calls == []

    window._auto_parse_action.setChecked(True)
    window._auto_parse_now()
    assert calls == [{"silent": True}]


# -- what a successful auto-parse does --------------------------------------


def test_auto_parse_rebuilds_the_tree_and_adopts_the_model(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._auto_parse_action.setChecked(True)
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)

    window._auto_parse_now()

    assert window._current_project is not None
    assert window.statusBar().currentMessage() == "Auto-parsed raw XML into tree"

    # A second auto-parse of changed text adopts a NEW model object -- the
    # tree/model really are rebuilt, not left pointing at the first parse.
    first = window._current_project
    window.center_stage.xml_editor.setPlainText(
        _MINIMAL_PGTP.replace("Equipment", "Machines")
    )
    window._auto_parse_now()
    assert window._current_project is not first


# -- the silent failure mode ------------------------------------------------


def test_silent_failure_raises_no_modal_and_does_not_move_the_caret(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    modal_calls = _no_modals(monkeypatch)
    highlighted = []
    monkeypatch.setattr(
        type(window.center_stage.xml_editor),
        "highlight_error_line",
        lambda self, line: highlighted.append(line),
    )
    # Establish a last-good model first.
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    window._doc_ui.reparse()
    good_project = window._current_project
    assert good_project is not None

    window.center_stage.xml_editor.setPlainText("<Project><Page")
    window._doc_ui.reparse(silent=True)

    assert modal_calls == []
    assert highlighted == []
    assert "Auto-parse" in window.statusBar().currentMessage()
    assert "not well-formed" in window.statusBar().currentMessage()
    # The last-good model and tree survive.
    assert window._current_project is good_project


def test_the_manual_path_still_raises_the_modal(qtbot, tmp_path, monkeypatch):
    """`silent` defaults to False, so Tools ▸ Reparse Raw XML into Tree and every
    other pre-existing caller keep today's modal failure dialog."""
    window = _window(qtbot, tmp_path)
    modal_calls = _no_modals(monkeypatch)
    window.center_stage.xml_editor.setPlainText("<Project><Page")

    window._doc_ui.reparse()

    assert len(modal_calls) == 1


def test_the_tools_menu_action_passes_no_silent_argument(qtbot, tmp_path, monkeypatch):
    """`triggered` carries a `checked: bool`; `silent` is keyword-only precisely
    so it can never be filled by it."""
    window = _window(qtbot, tmp_path)
    seen = []
    monkeypatch.setattr(
        PgtpDocumentController, "reparse", lambda self, **kw: seen.append(kw)
    )
    find_action(find_top_menu(window, "Tools"), "Reparse Raw XML into Tree").trigger()
    assert seen == [{}]
