# tests/ui/test_ddl_object_editor_wiring.py
"""MainWindow wiring for the editable DDL object tab (spec §18.5): opening
via BrowserPanel's Edit… context menu, Ctrl+S/Ctrl+F/bookmark dispatch to the
active tab, the Save-As-on-first-save flow, the close-confirmation prompt
(including "cancelling Save As from Close aborts the close"), the `[SQL]`
Audit reporting for Format Selection refusals, the mandatory Ctrl+Z
native-undo regression (carve-out 1) proving the Raw XML buffer is untouched,
and carve-out 5 (re-running DDL Explorer leaves open object tabs untouched).
"""
from lxml import etree
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

import pgtp_editor.ui.main_window as main_window_module
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.main_window import MainWindow


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    return window


_REF = DdlObjectRef(kind="function", schema="pr", name="recalc")


class _FakeProject:
    def __init__(self, tree):
        self.tree = tree


def _project_with_connection():
    tree = etree.ElementTree(
        etree.fromstring(
            b'<Project><ConnectionOptions host="h" port="5432" login="u" '
            b'database="d"/></Project>'
        )
    )
    return _FakeProject(tree)


def test_edit_requested_opens_a_new_tab_and_focuses_it(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window._on_ddl_edit_requested(_REF, "CREATE FUNCTION pr.recalc() ...")

    panel = window.center_stage.ddl_object_tab(_REF.key)
    assert panel is not None
    assert panel.text() == "CREATE FUNCTION pr.recalc() ..."
    assert window.center_stage.currentWidget() is panel


def test_edit_requested_again_focuses_the_existing_tab(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    first = window.center_stage.ddl_object_tab(_REF.key)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    window._on_ddl_edit_requested(_REF, "ignored -- already open")

    assert window.center_stage.ddl_object_tab(_REF.key) is first
    assert window.center_stage.currentWidget() is first


def test_ctrl_s_on_the_ddl_object_tab_routes_to_save_as_then_remembers_path(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "CREATE FUNCTION pr.recalc() ...")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("-- edited\n")
    dest = tmp_path / "pr.recalc.sql"
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(dest), "")),
    )

    window._save_active_tab()

    assert dest.read_text(encoding="utf-8") == panel.text()
    assert panel.is_dirty() is False
    assert window.center_stage.tabText(window.center_stage.indexOf(panel)) == "recalc"

    # A second save with a remembered path writes silently, no dialog.
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("dialog reopened"))),
    )
    panel.editor.insertPlainText("more\n")
    window._save_active_tab()
    assert dest.read_text(encoding="utf-8") == panel.text()


def test_ctrl_s_save_as_cancelled_leaves_tab_dirty_and_writes_nothing(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("x")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: ("", "")),  # Cancel
    )

    window._save_active_tab()

    assert panel.is_dirty() is True
    assert panel.save_path is None


def test_active_find_bar_and_bookmark_editor_route_to_the_ddl_object_tab(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)

    assert window._active_find_bar() is panel.find_replace_bar
    assert window._active_bookmark_editor() is panel.editor


def test_closing_a_clean_ddl_object_tab_closes_without_prompting(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    monkeypatch.setattr(
        window, "_confirm_close_ddl_object",
        lambda ref: (_ for _ in ()).throw(AssertionError("must not prompt")),
    )

    window.center_stage.tabCloseRequested.emit(window.center_stage.indexOf(panel))

    assert window.center_stage.ddl_object_tab(_REF.key) is None


def test_closing_a_dirty_tab_prompts_and_discard_closes_without_saving(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("x")
    monkeypatch.setattr(window, "_confirm_close_ddl_object", lambda ref: "discard")

    window.center_stage.tabCloseRequested.emit(window.center_stage.indexOf(panel))

    assert window.center_stage.ddl_object_tab(_REF.key) is None


def test_closing_a_dirty_tab_cancel_leaves_it_open(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("x")
    monkeypatch.setattr(window, "_confirm_close_ddl_object", lambda ref: "cancel")

    window.center_stage.tabCloseRequested.emit(window.center_stage.indexOf(panel))

    assert window.center_stage.ddl_object_tab(_REF.key) is panel


def test_closing_a_dirty_tab_save_writes_then_closes(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("x")
    expected_text = panel.text()
    dest = tmp_path / "pr.recalc.sql"
    monkeypatch.setattr(window, "_confirm_close_ddl_object", lambda ref: "save")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(dest), "")),
    )

    window.center_stage.tabCloseRequested.emit(window.center_stage.indexOf(panel))

    assert dest.read_text(encoding="utf-8") == expected_text
    assert window.center_stage.ddl_object_tab(_REF.key) is None


def test_closing_a_dirty_tab_save_then_cancelled_save_as_aborts_the_close(
    qtbot, tmp_path, monkeypatch
):
    """§18.5: cancelling Save As… reached from Close ▸ Save must abort the
    close exactly like Close ▸ Cancel -- never silently discard the edit."""
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("x")
    monkeypatch.setattr(window, "_confirm_close_ddl_object", lambda ref: "save")
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: ("", "")),  # Cancel
    )

    window.center_stage.tabCloseRequested.emit(window.center_stage.indexOf(panel))

    assert window.center_stage.ddl_object_tab(_REF.key) is panel
    assert panel.is_dirty() is True


def test_format_refusal_is_reported_to_audit_under_sql_prefix_not_clickable(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "begin\n  x := 1;")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    cursor = panel.editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    panel.editor.setTextCursor(cursor)

    panel.format_selection()

    texts = [window.audit_panel.item(i).text() for i in range(window.audit_panel.count())]
    matches = [t for t in texts if t.startswith("[SQL] ")]
    assert len(matches) == 1
    assert "Unmatched BEGIN" in matches[0]
    item = window.audit_panel.item(window.audit_panel.count() - 1)
    assert item.data(Qt.ItemDataRole.UserRole) is None  # not clickable, no line role


def test_ctrl_z_with_ddl_object_tab_focused_touches_only_its_own_buffer(qtbot, tmp_path):
    """End-to-end regression (§18.5 carve-out 1): with the object tab focused
    and a dirty Raw XML document, Ctrl+Z must revert the OBJECT buffer, leave
    Raw XML byte-identical, and never advance/rewind `MainWindow._history`
    (the project snapshot history that drives the window-level shortcut).

    Caveat verified during this test's audit: under this Qt/PySide6 version,
    `QPlainTextEdit` itself already claims the `ShortcutOverride` for its own
    standard Ctrl+Z/Ctrl+Y bindings before `DdlObjectEditorPanel`'s eventFilter
    is even relevant, so THIS test alone cannot discriminate "the panel's
    eventFilter exists" from "it doesn't" (verified by temporarily removing
    `DdlObjectEditorPanel`'s `installEventFilter` call -- this test still
    passed). It remains valuable as an end-to-end assertion that the observed
    behavior is correct; the mechanism-level proof that the panel's own
    eventFilter logic is what's responsible lives in
    `tests/ui/test_ddl_object_editor.py` (`test_event_filter_claims_ctrl_z_*`,
    which call `panel.eventFilter(...)` directly and DO fail if that logic is
    broken)."""
    window = _window(qtbot, tmp_path)
    window.show()
    raw_editor = window.center_stage.xml_editor
    raw_editor.setPlainText("<root>original</root>")
    original_raw_text = raw_editor.toPlainText()
    # Dirty the Raw XML buffer via the real snapshot-history path, exactly as
    # test_history_wiring.py does, so a leaked window shortcut would revert it.
    raw_editor.setPlainText("<root>edited</root>")
    window._capture_snapshot_now()
    dirtied_raw_text = raw_editor.toPlainText()
    history_index_before = window._history.current_index
    assert dirtied_raw_text != original_raw_text

    window._on_ddl_edit_requested(_REF, "alpha\n")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.setFocus()
    cursor = panel.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    panel.editor.setTextCursor(cursor)
    panel.editor.insertPlainText("beta")
    assert panel.text() == "alpha\nbeta"

    QTest.keyClick(panel.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    # The object tab's own buffer reverted...
    assert panel.text() == "alpha\n"
    # ...and Raw XML is completely untouched -- byte-identical, still dirty...
    assert raw_editor.toPlainText() == dirtied_raw_text
    # ...and the project snapshot history was never touched by _undo().
    assert window._history.current_index == history_index_before


def test_reopening_ddl_explorer_leaves_open_object_tabs_untouched(qtbot, tmp_path, monkeypatch):
    """Carve-out 5 (§18.5): a fresh Database ▸ DDL Explorer fetch rebuilds
    only the read-only buffer and the tree -- an already-open
    DdlObjectEditorPanel tab is not reloaded, not marked, not closed and not
    prompted about, even though its live definition may have changed
    underneath it."""
    window = _window(qtbot, tmp_path)
    window._current_project = _project_with_connection()
    window._on_ddl_edit_requested(_REF, "alpha\n")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("-- user's in-progress edit\n")
    assert panel.is_dirty() is True
    dirty_text = panel.text()
    tabs_before = window.center_stage.count()

    def _fake_run_async(fn, on_result, on_error=None):
        on_result(fn())

    monkeypatch.setattr(window, "_run_async", _fake_run_async)
    monkeypatch.setattr(
        window,
        "_fetch_ddl_schema",
        lambda params: DatabaseSchema(
            routines={
                "pr.recalc()": RoutineInfo(
                    schema="pr", name="recalc", arg_types=[], return_type="void",
                    language="plpgsql", source="-- a DIFFERENT live definition now",
                    kind="function",
                )
            }
        ),
    )

    window._open_ddl_explorer()

    # The object tab is untouched: same panel, same (still-dirty) buffer.
    assert window.center_stage.ddl_object_tab(_REF.key) is panel
    assert panel.text() == dirty_text
    assert panel.is_dirty() is True
    assert window.center_stage.count() == tabs_before
    # The read-only DDL Explorer buffer, meanwhile, DID refresh.
    assert "a DIFFERENT live definition now" in window.center_stage.ddl_editor_panel.editor.toPlainText()
