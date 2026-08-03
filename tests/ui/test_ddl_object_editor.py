# tests/ui/test_ddl_object_editor.py
"""DdlObjectEditorPanel: the EDITABLE single-object DDL tab (spec §18.5, v1).

The editable counterpart of §18.1's read-only EditorPanel: same CodeEditor in
"sql" mode plus its own FindReplaceBar, project-decoupled, no database access,
no sandbox button row (carve-out 2).
"""
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.code_editor import CodeEditor, _SQL_KEYWORDS
from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel, DdlObjectRef
from pgtp_editor.ui.find_replace_bar import FindReplaceBar

_SRC = (
    "CREATE FUNCTION pr.recalc() RETURNS void AS $$\n"
    "BEGIN\n"
    "  PERFORM 1;\n"
    "END;\n"
    "$$ LANGUAGE plpgsql;\n"
)

_PLAIN = DdlObjectRef(kind="function", schema="pr", name="recalc")
_NOARG = DdlObjectRef(kind="function", schema="pr", name="recalc", arg_types=())
_OVERLOAD = DdlObjectRef(
    kind="function", schema="pr", name="fmt", arg_types=("integer",), disambiguate=True
)
_TRIGGER = DdlObjectRef(kind="trigger", schema="pr", name="trg_audit", table="orders")


def _panel(qtbot, ref=_PLAIN, text=_SRC, **kwargs):
    panel = DdlObjectEditorPanel(ref, text, **kwargs)
    qtbot.addWidget(panel)
    return panel


# --- DdlObjectRef -----------------------------------------------------------
def test_short_title_of_a_sole_holder_routine_is_the_bare_name():
    assert _PLAIN.short_title == "recalc"


def test_short_title_of_a_no_arg_routine_is_not_rendered_with_empty_parens():
    """`recalc`, never `recalc()` -- the caller only disambiguates overloads."""
    assert _NOARG.short_title == "recalc"
    assert "(" not in _NOARG.short_title


def test_short_title_of_an_overloaded_routine_carries_the_signature():
    assert _OVERLOAD.short_title == "fmt(integer)"


def test_short_title_of_a_trigger_is_table_dot_name():
    assert _TRIGGER.short_title == "orders.trg_audit"


def test_qualified_is_the_full_identity():
    assert _PLAIN.qualified == "pr.recalc()"
    assert _OVERLOAD.qualified == "pr.fmt(integer)"
    assert _TRIGGER.qualified == "pr.orders.trg_audit"


def test_key_distinguishes_two_overloads_and_is_usable_as_a_dict_key():
    one = DdlObjectRef(kind="function", schema="pr", name="fmt", arg_types=("integer",))
    two = DdlObjectRef(kind="function", schema="pr", name="fmt", arg_types=("text",))
    assert one.key != two.key
    tabs = {one.key: "tab-1", two.key: "tab-2"}
    assert len(tabs) == 2
    assert hash(one.key) == hash(one.key)
    # Presentation-only disambiguation must not change the tab identity.
    same = DdlObjectRef(
        kind="function", schema="pr", name="fmt", arg_types=("integer",), disambiguate=True
    )
    assert same.key == one.key


def test_key_distinguishes_two_triggers_sharing_a_name_on_different_tables():
    a = DdlObjectRef(kind="trigger", schema="pr", name="trg_audit", table="orders")
    b = DdlObjectRef(kind="trigger", schema="pr", name="trg_audit", table="items")
    assert a.key != b.key


def test_default_file_name_follows_the_18_2_scheme():
    assert _PLAIN.default_file_name == "pr.recalc.sql"
    assert _TRIGGER.default_file_name == "pr.orders.trg_audit.sql"


# --- The panel: editor identity --------------------------------------------
def test_panel_hosts_an_EDITABLE_sql_code_editor(qtbot):
    panel = _panel(qtbot)
    assert isinstance(panel.editor, CodeEditor)
    assert panel.editor.isReadOnly() is False
    assert panel.editor._highlighter._keywords is _SQL_KEYWORDS
    assert panel.text() == _SRC
    assert panel.ref is _PLAIN


def test_panel_has_no_sandbox_button_row(qtbot):
    """Carve-out 2: v1 ships no Apply/Check controls rather than dead ones."""
    from PySide6.QtWidgets import QPushButton

    panel = _panel(qtbot)
    labels = {b.text() for b in panel.findChildren(QPushButton)}
    assert not {label for label in labels if "Apply" in label or "Check" in label}


def test_applied_sha1_is_an_inert_seam_defaulting_to_none(qtbot):
    panel = _panel(qtbot)
    assert panel.applied_sha1 is None


def test_find_replace_bar_is_per_instance_and_wired_to_its_own_editor(qtbot):
    a = _panel(qtbot)
    b = _panel(qtbot, ref=_OVERLOAD)
    assert isinstance(a.find_replace_bar, FindReplaceBar)
    assert a.find_replace_bar is not b.find_replace_bar
    assert a.find_replace_bar._editor is a.editor
    assert b.find_replace_bar._editor is b.editor
    assert a.find_replace_bar.parent() is a


def test_find_all_is_inert_and_never_reports_a_false_zero_matches(qtbot):
    """Carve-out 3 (§18.5): Find All is present (the shared FindReplaceBar)
    but produces no results at all here -- the panel wires no on_find_all
    callback, so the bar's constructor default (`lambda term: None`) is what
    runs. Calling it must not raise and must not flip find-all-running state
    (which only a real results-reporting host would do), so nothing reports
    a false "0 matches" as though the buffer had been searched."""
    panel = _panel(qtbot, text="needle needle needle")
    panel.find_replace_bar._find_field.setText("needle")

    panel.find_replace_bar.find_all()  # must not raise

    assert panel.find_replace_bar._find_all_running is False


def test_replace_current_selection_actually_replaces_here(qtbot):
    """The behavioral difference from the read-only EditorPanel, whose
    replace_current_selection early-returns on isReadOnly()."""
    panel = _panel(qtbot, text="alpha beta\n")
    cursor = panel.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(
        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 5
    )
    panel.editor.setTextCursor(cursor)
    panel.editor.replace_current_selection("gamma")
    assert panel.text() == "gamma beta\n"


def test_gutter_bookmark_and_fold_api_is_present_via_the_shared_mixin(qtbot):
    panel = _panel(qtbot)
    editor = panel.editor
    assert hasattr(editor, "_gutter")
    for api in ("toggle_bookmark", "next_bookmark", "prev_bookmark", "set_fold_regions"):
        assert callable(getattr(editor, api))
    editor.navigate_to_line(2)
    editor.toggle_bookmark_at_cursor()
    assert editor.bookmarked_lines() == [1]  # 0-based block of 1-based line 2
    assert editor.next_bookmark(0) == 1
    # Folding: the single-object buffer's own structure drives the regions.
    editor.set_fold_regions([(0, 1, 4)])
    assert editor._foldable_region_starting_at(editor.document().firstBlock()) == (1, 4)


def test_navigate_to_line_moves_the_caret(qtbot):
    panel = _panel(qtbot)
    panel.navigate_to_line(3)
    assert panel.editor.textCursor().block().text() == "  PERFORM 1;"


# --- Dirty state ------------------------------------------------------------
def test_set_text_loads_the_buffer_without_dirtying_it(qtbot):
    panel = _panel(qtbot)
    assert panel.is_dirty() is False
    panel.set_text("-- other\n")
    assert panel.text() == "-- other\n"
    assert panel.is_dirty() is False


def test_user_typing_dirties_the_panel(qtbot):
    panel = _panel(qtbot)
    qtbot.keyClicks(panel.editor, "-- note")
    assert panel.is_dirty() is True
    assert panel.text().startswith("-- note")


def test_programmatic_edit_dirties_and_mark_clean_clears(qtbot):
    panel = _panel(qtbot)
    panel.editor.insertPlainText("x")
    assert panel.is_dirty() is True
    panel.mark_clean()
    assert panel.is_dirty() is False


def test_dirty_changed_fires_on_transitions_only(qtbot):
    panel = _panel(qtbot)
    seen: list[bool] = []
    panel.dirty_changed.connect(seen.append)
    panel.editor.insertPlainText("abc")   # one clean->dirty transition
    panel.editor.insertPlainText("def")   # already dirty: no further signal
    assert seen == [True]
    panel.mark_clean()
    assert seen == [True, False]
    panel.mark_clean()                    # already clean: no further signal
    assert seen == [True, False]


# --- Tab title / tooltip ----------------------------------------------------
def test_tab_title_carries_the_dirty_marker(qtbot):
    panel = _panel(qtbot)
    assert panel.tab_title() == "recalc"
    panel.editor.insertPlainText("x")
    assert panel.tab_title() == "recalc *"
    panel.mark_clean()
    assert panel.tab_title() == "recalc"


def test_tab_title_and_tooltip_for_an_overload_and_a_trigger(qtbot):
    overload = _panel(qtbot, ref=_OVERLOAD)
    assert overload.tab_title() == "fmt(integer)"
    assert overload.tab_tooltip() == "pr.fmt(integer)"
    trigger = _panel(qtbot, ref=_TRIGGER)
    assert trigger.tab_title() == "orders.trg_audit"
    assert trigger.tab_tooltip() == "pr.orders.trg_audit"


# --- The §18.2 save seam ----------------------------------------------------
def test_resolve_save_path_is_none_until_a_path_is_remembered(qtbot, tmp_path):
    panel = _panel(qtbot)
    assert panel.resolve_save_path() is None
    target = tmp_path / "pr.recalc.sql"
    panel.remember_save_path(target)
    assert panel.resolve_save_path() == target
    assert panel.save_path == target


def test_an_injected_resolver_replaces_the_default_entirely(qtbot, tmp_path):
    """§18.2's whole change: this callable returns the project's ddl/ path."""
    injected = tmp_path / "ddl" / "pr.recalc.sql"
    calls: list[int] = []

    def resolver() -> Path | None:
        calls.append(1)
        return injected

    panel = _panel(qtbot, resolve_save_path=resolver)
    assert panel.resolve_save_path() == injected
    assert calls == [1]
    # The injected resolver is authoritative; the panel does not fall back.
    panel.remember_save_path(tmp_path / "elsewhere.sql")
    assert panel.resolve_save_path() == injected


def test_panel_module_imports_nothing_db_or_project_related():
    """v1 is project-decoupled and never opens a connection: assert it against
    the module's actual import statements, not its prose."""
    import ast

    import pgtp_editor.ui.ddl_object_editor as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    joined = " ".join(imported)
    for forbidden in ("introspect", "psycopg", "ddl_project", "QFileDialog", "QMessageBox"):
        assert forbidden not in joined, forbidden


# --- Ctrl+Z / Ctrl+Y native-undo carve-out (§18.5 carve-out 1) --------------
def _move_cursor_to_end(panel) -> None:
    cursor = panel.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    panel.editor.setTextCursor(cursor)


def test_ctrl_z_uses_the_editors_own_native_undo(qtbot):
    """A real Ctrl+Z key press reverts the editor's OWN document, not a
    project-level history the panel knows nothing about (there is none to
    know about here -- this is the panel-level half of the mandatory
    regression; the MainWindow-level half lives in test_main_window.py and
    proves the Raw XML buffer stays untouched)."""
    panel = _panel(qtbot, text="alpha\n")
    panel.editor.setFocus()
    _move_cursor_to_end(panel)
    panel.editor.insertPlainText("beta")
    assert panel.text() == "alpha\nbeta"

    QTest.keyClick(panel.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    assert panel.text() == "alpha\n"


def test_ctrl_y_uses_the_editors_own_native_redo(qtbot):
    panel = _panel(qtbot, text="alpha\n")
    panel.editor.setFocus()
    _move_cursor_to_end(panel)
    panel.editor.insertPlainText("beta")
    QTest.keyClick(panel.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert panel.text() == "alpha\n"

    QTest.keyClick(panel.editor, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)

    assert panel.text() == "alpha\nbeta"


# --- Format Selection (§18.4's consumer, §18.5) -----------------------------
def _select_all(panel) -> None:
    cursor = panel.editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    panel.editor.setTextCursor(cursor)


def test_format_selection_reindents_in_place_as_one_undo_step(qtbot):
    panel = _panel(qtbot, text="select a,b from t where a=1")
    _select_all(panel)

    panel.format_selection()

    assert panel.text() == "select a, b\nfrom t\nwhere a = 1"
    # One undo step reverts the whole reformat.
    panel.editor.undo()
    assert panel.text() == "select a,b from t where a=1"


def test_format_selection_shortcut_is_disabled_without_a_selection(qtbot):
    panel = _panel(qtbot, text="select a,b from t where a=1")
    assert panel._format_shortcut.isEnabled() is False
    _select_all(panel)
    assert panel._format_shortcut.isEnabled() is True


def test_ctrl_alt_f_triggers_format_selection(qtbot):
    panel = _panel(qtbot, text="select a,b from t where a=1")
    panel.editor.setFocus()
    _select_all(panel)

    QTest.keyClick(
        panel.editor,
        Qt.Key.Key_F,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )

    assert panel.text() == "select a, b\nfrom t\nwhere a = 1"


def test_format_selection_on_refusal_leaves_text_untouched_and_emits_issues(qtbot):
    panel = _panel(qtbot, text="begin\n  x := 1;")
    _select_all(panel)
    seen = []
    panel.format_refused.connect(seen.append)

    panel.format_selection()

    assert panel.text() == "begin\n  x := 1;"  # verbatim, untouched
    assert len(seen) == 1
    issues = seen[0]
    assert len(issues) == 1
    assert issues[0].message.startswith("Unmatched BEGIN")


def test_format_selection_refusal_underlines_the_offending_span(qtbot):
    panel = _panel(qtbot, text="begin\n  x := 1;")
    _select_all(panel)

    panel.format_selection()

    selections = panel.editor.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.selectedText() == "begin"


def test_format_selection_underline_clears_on_next_edit(qtbot):
    panel = _panel(qtbot, text="begin\n  x := 1;")
    _select_all(panel)
    panel.format_selection()
    assert panel.editor.extraSelections()

    panel.editor.insertPlainText("z")

    assert panel.editor.extraSelections() == []


def test_format_selection_underline_clears_on_next_format_attempt(qtbot):
    panel = _panel(qtbot, text="begin\n  x := 1;\nbegin\n  y := 2;")
    cursor = panel.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(
        QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, 2
    )
    panel.editor.setTextCursor(cursor)
    panel.format_selection()
    assert panel.editor.extraSelections()

    _select_all(panel)
    panel.format_selection()

    # Cleared before the second attempt runs, then repopulated fresh with
    # BOTH unmatched BEGINs (not 3 -- which would mean the first attempt's
    # underline leaked into the second instead of being cleared first).
    assert len(panel.editor.extraSelections()) == 2


def test_format_selection_noop_without_a_selection(qtbot):
    panel = _panel(qtbot, text="select a,b from t")
    panel.format_selection()
    assert panel.text() == "select a,b from t"


# --- Format Selection context-menu item (spec §18.5) ------------------------
def test_context_menu_has_a_format_selection_entry(qtbot):
    panel = _panel(qtbot, text="select a,b from t where a=1")
    menu = panel._build_context_menu()
    actions = [a for a in menu.actions() if a.text() == "Format Selection"]
    assert len(actions) == 1


def test_context_menu_format_selection_disabled_without_a_selection(qtbot):
    panel = _panel(qtbot, text="select a,b from t where a=1")
    menu = panel._build_context_menu()
    action = next(a for a in menu.actions() if a.text() == "Format Selection")
    assert action.isEnabled() is False


def test_context_menu_format_selection_enabled_with_a_selection_and_triggers_it(qtbot):
    panel = _panel(qtbot, text="select a,b from t where a=1")
    _select_all(panel)
    menu = panel._build_context_menu()
    action = next(a for a in menu.actions() if a.text() == "Format Selection")
    assert action.isEnabled() is True

    action.trigger()

    assert panel.text() == "select a, b\nfrom t\nwhere a = 1"


# --- ShortcutOverride claim (§18.5 carve-out 1, mechanism-level) ------------
#
# `QTest.keyClick`/`QApplication.sendEvent` cannot prove the PANEL's own
# eventFilter is what claims Ctrl+Z/Ctrl+Y: verified (by temporarily removing
# the panel's `installEventFilter` call) that a bare `QPlainTextEdit` already
# accepts the `ShortcutOverride` for its OWN standard Undo/Redo key sequences
# before the panel's filter is ever relevant, in this Qt/PySide6 version --
# so `event.isAccepted()` after `sendEvent` is `True` for Ctrl+Z/Ctrl+Y with
# or without the panel's filter installed, and cannot discriminate the two.
# `Ctrl+Alt+F` has no such native binding, so it CAN be (and is) proven this
# way. For Ctrl+Z/Ctrl+Y the tests below instead call `panel.eventFilter(...)`
# directly -- unit-testing the panel's own documented logic (it claims the
# ShortcutOverride and, on the KeyPress, calls its own `editor.undo()`/
# `redo()`) independent of which widget would have won the ambiguous Qt
# dispatch on any given platform.


def _shortcut_override(key, modifiers) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.ShortcutOverride, key, modifiers)


def _key_press(key, modifiers) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


def test_event_filter_claims_ctrl_z_shortcut_override(qtbot):
    panel = _panel(qtbot, text="alpha\n")
    event = _shortcut_override(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    handled = panel.eventFilter(panel.editor, event)

    assert handled is True
    assert event.isAccepted() is True


def test_event_filter_claims_ctrl_y_shortcut_override(qtbot):
    panel = _panel(qtbot, text="alpha\n")
    event = _shortcut_override(Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)

    handled = panel.eventFilter(panel.editor, event)

    assert handled is True
    assert event.isAccepted() is True


def test_event_filter_ctrl_z_key_press_calls_the_panels_own_undo(qtbot):
    """The KeyPress branch (not just ShortcutOverride) must drive the
    editor's OWN undo/redo -- never MainWindow's project-history `_undo`,
    which the panel does not even import."""
    panel = _panel(qtbot, text="alpha\n")
    panel.editor.setFocus()
    _move_cursor_to_end(panel)
    panel.editor.insertPlainText("beta")
    assert panel.text() == "alpha\nbeta"
    event = _key_press(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    handled = panel.eventFilter(panel.editor, event)

    assert handled is True
    assert panel.text() == "alpha\n"


def test_shortcut_override_claims_ctrl_alt_f(qtbot):
    """Unlike Ctrl+Z/Ctrl+Y, Ctrl+Alt+F has no native QPlainTextEdit binding,
    so this genuinely proves the panel's own QShortcut/eventFilter claims it
    -- verified to FAIL if `installEventFilter` is removed."""
    panel = _panel(qtbot, text="alpha\n")
    modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    event = _shortcut_override(Qt.Key.Key_F, modifiers)

    QApplication.sendEvent(panel.editor, event)

    assert event.isAccepted() is True


def test_shortcut_override_does_not_claim_unrelated_keys(qtbot):
    """The eventFilter must not blanket-accept every ShortcutOverride on the
    editor -- only the specific sequences it claims (Ctrl+Z/Ctrl+Y/Ctrl+Alt+F).
    An unrelated key with no editor-native binding (e.g. Ctrl+Alt+G) must be
    left alone so other shortcuts keep working."""
    panel = _panel(qtbot, text="alpha\n")
    modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    event = _shortcut_override(Qt.Key.Key_G, modifiers)

    QApplication.sendEvent(panel.editor, event)

    assert event.isAccepted() is False
