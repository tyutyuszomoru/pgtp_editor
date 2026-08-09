# tests/ui/test_ddl_object_editor_wiring.py
"""MainWindow wiring for the editable DDL object tab (spec §18.5): opening
via BrowserPanel's Edit… context menu, `Deployment ▸ Save in Project` (FQ-020 --
was Ctrl+S) / Ctrl+F / bookmark dispatch to the
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

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui import modals


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    return window


_REF = DdlObjectRef(kind="function", schema="pr", name="recalc")

#: BUG-034: a project's own `ProjectSettings.target` is the connection every
#: fetch gesture uses, so a project used in a fetch test must carry one.
_TARGET = ConnectionParams(host="h", port="5432", database="d", user="u", password="p")


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


def test_save_in_project_on_the_ddl_object_tab_runs_save_as_then_remembers_path(
    qtbot, tmp_path, monkeypatch
):
    """FQ-020: was `test_ctrl_s_on_the_ddl_object_tab_...`. §18.5's Save-As flow
    is unchanged -- dialog on the first save, silent writes to the remembered path
    after -- only its trigger moved from `Ctrl+S` to `Deployment ▸ Save in
    Project`."""
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "CREATE FUNCTION pr.recalc() ...")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("-- edited\n")
    dest = tmp_path / "pr.recalc.sql"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(dest), "")),
    )

    # Driven through the real menu entry, so the wiring is asserted end to end
    # rather than the handler being called directly.
    from tests.ui._menu_helpers import find_action, find_top_menu

    action = find_action(find_top_menu(window, "Deployment"), "Save in Project")
    assert action is not None and action.isVisible()
    assert action.shortcut().isEmpty()
    action.trigger()

    assert dest.read_text(encoding="utf-8") == panel.text()
    assert panel.is_dirty() is False
    assert window.center_stage.tabText(window.center_stage.indexOf(panel)) == "recalc"

    # A second save with a remembered path writes silently, no dialog.
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("dialog reopened"))),
    )
    panel.editor.insertPlainText("more\n")
    window._save_active_ddl_object()
    assert dest.read_text(encoding="utf-8") == panel.text()


def test_save_in_project_save_as_cancelled_leaves_tab_dirty_and_writes_nothing(
    qtbot, tmp_path, monkeypatch
):
    """The cancel semantics §18.5 calls a data-loss guard, unchanged by FQ-020."""
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("x")
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: ("", "")),  # Cancel
    )

    window._save_active_ddl_object()

    assert panel.is_dirty() is True
    assert panel.save_path is None


def test_active_find_bar_and_bookmark_editor_route_to_the_ddl_object_tab(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, "text")
    panel = window.center_stage.ddl_object_tab(_REF.key)

    assert window._find_ui.active_find_bar() is panel.find_replace_bar
    assert window._find_ui.active_bookmark_editor() is panel.editor


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
        modals.QFileDialog, "getSaveFileName",
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
        modals.QFileDialog, "getSaveFileName",
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


# --- BUG-033: the DDL Objects tree must show the edit ------------------------
def _recalc_schema(source="-- live recalc\n"):
    return DatabaseSchema(
        routines={
            "pr.recalc()": RoutineInfo(
                schema="pr", name="recalc", arg_types=[], return_type="void",
                language="plpgsql", source=source, kind="function",
            )
        }
    )


def _load_explorer(window, monkeypatch, schema=None):
    """Populate the tree the way a real fetch does, with no DB and no modal."""
    monkeypatch.setattr(window, "_run_async", lambda fn, on_result, on_error=None: on_result(fn()))
    monkeypatch.setattr(window, "_fetch_ddl_schema", lambda params: schema or _recalc_schema())
    window._open_ddl_explorer()


def _recalc_row(window):
    return window.ddl_browser_panel.tree.topLevelItem(1).child(0)


def test_editing_an_open_tab_marks_its_row_in_the_ddl_objects_tree(qtbot, tmp_path, monkeypatch):
    """The verbatim report: a modified function's DDL shows no `*` in the DDL
    Objects window. `dirty_changed` reached only the tab title before."""
    window = _window(qtbot, tmp_path)
    window._current_project = _project_with_connection()
    _load_explorer(window, monkeypatch)
    window._on_ddl_edit_requested(_REF, "-- live recalc\n")
    assert _recalc_row(window).text(0) == "pr.recalc() [F]"

    window.center_stage.ddl_object_tab(_REF.key).editor.insertPlainText("-- edited\n")

    assert _recalc_row(window).text(0) == "pr.recalc() [F] *"


def test_the_unsaved_marker_works_with_no_project_open(qtbot, tmp_path, monkeypatch):
    """An unsaved edit is a property of the editor buffer, not of a project's
    deploy state, so it must mark the row projectless -- where `drift_markers`
    is None and the §18.2 `*` channel does not exist at all."""
    window = _window(qtbot, tmp_path)
    window._current_project = _project_with_connection()
    _load_explorer(window, monkeypatch)
    assert window._ddl_project_folder is None
    window._on_ddl_edit_requested(_REF, "-- live recalc\n")

    window.center_stage.ddl_object_tab(_REF.key).editor.insertPlainText("x")

    assert _recalc_row(window).text(0).endswith("*")


def test_saving_the_tab_clears_the_unsaved_marker(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    window._current_project = _project_with_connection()
    _load_explorer(window, monkeypatch)
    window._on_ddl_edit_requested(_REF, "-- live recalc\n")
    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("-- edited\n")
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "pr.recalc.sql"), "")),
    )

    window._save_ddl_object_editor(panel)

    assert _recalc_row(window).text(0) == "pr.recalc() [F]"


def test_discarding_a_dirty_tab_drops_the_marker(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    window._current_project = _project_with_connection()
    _load_explorer(window, monkeypatch)
    window._on_ddl_edit_requested(_REF, "-- live recalc\n")
    window.center_stage.ddl_object_tab(_REF.key).editor.insertPlainText("-- edited\n")
    assert _recalc_row(window).text(0).endswith("*")
    monkeypatch.setattr(window, "_confirm_close_ddl_object", lambda ref: "discard")

    window._on_ddl_object_close_requested(_REF.key)

    assert _recalc_row(window).text(0) == "pr.recalc() [F]"


def test_saving_a_checked_out_object_makes_the_file_level_star_appear(qtbot, tmp_path, monkeypatch):
    """Layer (b): after Save the §18.2 file-vs-last-deployed `*` must be
    recomputed immediately, not only after a manual Explorer refresh."""
    from pgtp_editor.db.ddl_project import ProjectSettings, load_settings, save_settings

    window = _window(qtbot, tmp_path)
    window._current_project = _project_with_connection()
    project_dir = tmp_path / "proj"
    # BUG-034: with a project open, its own target is what the fetch uses.
    settings = ProjectSettings(target=_TARGET)
    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    _load_explorer(window, monkeypatch)

    window._edit_ddl_checked_out(_REF, "-- live recalc\n")
    # A fresh checkout is NOT locally edited -- the reference recorded is the
    # live definition it was taken from.
    assert _recalc_row(window).text(0) == "pr.recalc() [F]"
    assert load_settings(project_dir).deployed["ddl/pr.recalc.sql"].content_hash != ""

    panel = window.center_stage.ddl_object_tab(_REF.key)
    panel.editor.insertPlainText("-- edited\n")
    window._save_ddl_object_editor(panel)

    # Clean tab (no overlay), but the FILE now differs from the reference.
    assert panel.is_dirty() is False
    assert _recalc_row(window).text(0) == "pr.recalc() [F] *"


def test_checkout_registers_the_live_hash_and_never_overwrites_a_real_reference(
    qtbot, tmp_path, monkeypatch
):
    from pgtp_editor.db.ddl_project import (
        DeployedObject,
        ProjectSettings,
        load_settings,
        save_settings,
    )

    window = _window(qtbot, tmp_path)
    window._current_project = _project_with_connection()
    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        target=_TARGET,
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash="the-real-deploy")},
    )
    save_settings(project_dir, settings)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    _load_explorer(window, monkeypatch)

    window._edit_ddl_checked_out(_REF, "-- live recalc\n")

    assert load_settings(project_dir).deployed["ddl/pr.recalc.sql"].content_hash == (
        "the-real-deploy"
    )


# --- FQ-019: the DDL gestures are journalled --------------------------------
# The Activity Log's four most audit-worthy rows come from here: the two Apply
# actions, the two check gestures, and the tab's own Save. Each is driven
# through the real gesture, so what is asserted is the WIRING, not `record`.


class _FakeCheckReport:
    """Just enough of `db/ddl_check.py::CheckReport` for the journal's reading
    of it: `committed`, plus the tier/finding shape `report_blockers` walks."""

    def __init__(self, committed=True, findings=()):
        self.committed = committed
        self.findings = tuple(findings)
        self.caveats = ()
        self.tier0 = self.tier1 = self.tier2 = self.tier3 = None


class _FakeApplyResult:
    def __init__(self, report):
        self.report = report


def _open_tab(window, text="CREATE FUNCTION pr.recalc() RETURNS void AS $$ $$;"):
    window._on_ddl_edit_requested(_REF, text)
    return window.center_stage.ddl_object_tab(_REF.key)


def test_saving_a_ddl_object_tab_journals_a_saved_entry(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    panel = _open_tab(window)
    dest = tmp_path / "pr.recalc.sql"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(dest), "")),
    )

    assert window._save_ddl_object_editor(panel) is True

    entry = window.activity_log.entries[-1]
    assert entry.file_verb == "Saved"
    assert entry.status == "success"


def test_a_failed_ddl_object_save_journals_the_failure_with_the_os_error(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    panel = _open_tab(window)
    unwritable = tmp_path / "missing_dir" / "pr.recalc.sql"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(unwritable), "")),
    )
    monkeypatch.setattr(
        modals.QMessageBox, "critical", staticmethod(lambda *a, **k: None)
    )

    assert window._save_ddl_object_editor(panel) is False

    entry = window.activity_log.entries[-1]
    assert entry.file_verb == "Saved"
    assert entry.failed
    assert "pr.recalc.sql" in entry.error_full


def test_an_apply_to_sandbox_journals_the_ddl_against_the_sandbox_source(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    panel = _open_tab(window)
    text = panel.text()
    captured = {}

    class _Session:
        pass

    monkeypatch.setattr(
        type(window.sandbox_controller), "session", property(lambda self: _Session())
    )
    monkeypatch.setattr(
        window.sandbox_controller,
        "run_apply",
        lambda request, on_done, **kwargs: captured.setdefault("on_done", on_done),
    )

    window._apply_ddl_object_to_sandbox(_REF, text)
    captured["on_done"](_FakeApplyResult(_FakeCheckReport(committed=True)))

    entry = window.activity_log.entries[-1]
    assert entry.source == "Sandbox DB"
    assert entry.verb == "Apply to Sandbox"
    assert entry.ddl_full == text
    assert entry.status == "success"


def test_an_apply_to_sandbox_that_did_not_commit_is_journalled_as_failed(
    qtbot, tmp_path, monkeypatch
):
    """An apply is judged on `committed`: "it ran but was rolled back" is not a
    success, and the journal must not render it as one."""
    window = _window(qtbot, tmp_path)
    panel = _open_tab(window)
    captured = {}

    class _Session:
        pass

    monkeypatch.setattr(
        type(window.sandbox_controller), "session", property(lambda self: _Session())
    )
    monkeypatch.setattr(
        window.sandbox_controller,
        "run_apply",
        lambda request, on_done, **kwargs: captured.setdefault("on_done", on_done),
    )

    window._apply_ddl_object_to_sandbox(_REF, panel.text())
    captured["on_done"](_FakeApplyResult(_FakeCheckReport(committed=False)))

    entry = window.activity_log.entries[-1]
    assert entry.failed
    assert entry.error_full


def test_a_check_gesture_journals_the_linted_verb_and_is_not_judged_on_commit(
    qtbot, tmp_path, monkeypatch
):
    """A probe rolls back and a recheck applies nothing, so neither ever
    reports `committed` -- and neither may therefore be journalled as failed
    just for that."""
    window = _window(qtbot, tmp_path)
    panel = _open_tab(window)
    window.center_stage.setCurrentWidget(panel)
    captured = {}

    monkeypatch.setattr(
        type(window.sandbox_controller), "can_check", property(lambda self: True)
    )
    monkeypatch.setattr(
        window.sandbox_controller,
        "run_check",
        lambda request, on_done, **kwargs: captured.setdefault("on_done", on_done),
    )

    window._check_active_ddl_object()
    captured["on_done"](_FakeApplyResult(_FakeCheckReport(committed=False)))

    entry = window.activity_log.entries[-1]
    assert entry.source == "Sandbox DB"
    assert entry.verb == "linted"
    assert entry.status == "success"
    assert entry.ddl_full == panel.text()


def test_an_apply_to_target_journals_the_irreversible_write(qtbot, tmp_path, monkeypatch):
    """The single most audit-worthy action, journalled against `Quality DB`
    with the FULL DDL retained."""
    window = _window(qtbot, tmp_path)
    text = "CREATE FUNCTION pr.recalc() RETURNS void AS $$ $$;"
    captured = {}
    monkeypatch.setattr(
        window, "_target_params_for_apply", lambda: _TARGET
    )
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.run_async",
        lambda parent, work, on_result, on_error: captured.update(
            on_result=on_result, on_error=on_error
        ),
    )

    window._apply_ddl_object_to_target(_REF, text)

    class _Outcome:
        committed = True
        message = ""

    captured["on_result"](_Outcome())

    entry = window.activity_log.entries[-1]
    assert entry.source == "Quality DB"
    assert entry.verb == "Apply to Target"
    assert entry.ddl_full == text
    assert entry.status == "success"


def test_an_apply_to_target_that_did_not_commit_is_journalled_as_failed(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    captured = {}
    monkeypatch.setattr(window, "_target_params_for_apply", lambda: _TARGET)
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.run_async",
        lambda parent, work, on_result, on_error: captured.update(
            on_result=on_result, on_error=on_error
        ),
    )
    window._apply_ddl_object_to_target(_REF, "CREATE FUNCTION pr.recalc();")

    class _Outcome:
        committed = False
        message = "permission denied for schema pr"

    captured["on_result"](_Outcome())

    entry = window.activity_log.entries[-1]
    assert entry.failed
    assert entry.error_full == "permission denied for schema pr"
