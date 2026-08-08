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
    """Carve-out 2: with no apply seam wired the panel ships no Apply/Check
    controls at all, rather than dead or permanently-disabled ones."""
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


# ===========================================================================
# Apply (§18.5): Apply to Sandbox, Apply to Target's four hard preconditions,
# and the "Deploy this edit…" destination picker.
#
# Every DB-touching step is an injected seam, so no test here reaches a real
# database, and the confirmation gate is injected too, so no test reaches an
# un-patched modal.
# ===========================================================================
from pgtp_editor.ui.ddl_object_editor import (  # noqa: E402
    CHECK_PREFIX,
    DEST_SANDBOX,
    DEST_SAVE,
    DEST_TARGET,
    parse_buffer_identity,
)

_TARGET_SRC = (
    "CREATE OR REPLACE FUNCTION pr.recalc() RETURNS void AS $$\n"
    "BEGIN\n"
    "  PERFORM 1;\n"
    "END;\n"
    "$$ LANGUAGE plpgsql;\n"
)


class _Tier:
    """A duck-typed `TierOutcome{status, reason, detail}` (§18.5 D3)."""

    def __init__(self, status, reason=""):
        self.status = status
        self.reason = reason
        self.detail = ""


class _Report:
    """A duck-typed `CheckReport{tier0..tier3, findings, caveats}`."""

    def __init__(self, statuses=("passed", "passed", "passed", "passed"), findings=(), caveats=()):
        self.tier0, self.tier1, self.tier2, self.tier3 = (
            s if isinstance(s, _Tier) else _Tier(s) for s in statuses
        )
        self.findings = list(findings)
        self.caveats = list(caveats)


def _green():
    return _Report()


class _Seams:
    """Recording stand-ins for every injected seam."""

    def __init__(self, *, confirm=True, live=None, sandbox_db="sbx on localhost:5432",
                 target_db="prod on db01:5432", report=None):
        self.sandbox_calls = []
        self.target_calls = []
        self.confirms = []
        self.identity_calls = []
        self._confirm = confirm
        self._live = live
        self._report = report if report is not None else _green()
        self.sandbox_db = sandbox_db
        self.target_db = target_db

    def apply_to_sandbox(self, ref, text):
        self.sandbox_calls.append((ref, text))
        return self._report

    def apply_to_target(self, ref, text):
        self.target_calls.append((ref, text))
        return type("Outcome", (), {"ok": True, "statement_index": None})()

    def live_identity(self, ref):
        self.identity_calls.append(ref)
        return self._live

    def confirm(self, title, text):
        self.confirms.append((title, text))
        answer = self._confirm
        if isinstance(answer, list):
            return answer.pop(0)
        return answer


def _wired(qtbot, seams, *, ref=_PLAIN, text=_TARGET_SRC, sandbox=True, target=True, confirm=True):
    panel = DdlObjectEditorPanel(
        ref,
        text,
        apply_to_sandbox=seams.apply_to_sandbox if sandbox else None,
        apply_to_target=seams.apply_to_target if target else None,
        live_identity=seams.live_identity if target else None,
        sandbox_database_label=lambda: seams.sandbox_db,
        target_database_label=lambda: seams.target_db,
        confirm=seams.confirm if confirm else None,
    )
    qtbot.addWidget(panel)
    return panel


def _audit(panel):
    """Collect the Audit lines the panel emits, as the host would."""
    lines = []
    panel.check_reported.connect(lambda batch: lines.extend(batch))
    return lines


# --- Apply to Sandbox -------------------------------------------------------
def test_apply_to_sandbox_invokes_the_injected_seam_with_ref_and_buffer(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams)

    assert panel.apply_to_sandbox() is True

    assert seams.sandbox_calls == [(_PLAIN, _TARGET_SRC)]


def test_apply_to_sandbox_confirmation_names_the_object_and_the_database(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams)

    panel.apply_to_sandbox()

    _, text = seams.confirms[0]
    assert "pr.recalc()" in text
    assert "sbx on localhost:5432" in text


def test_declined_confirmation_applies_nothing_to_the_sandbox(qtbot):
    seams = _Seams(confirm=False)
    panel = _wired(qtbot, seams)
    lines = _audit(panel)

    assert panel.apply_to_sandbox() is False

    assert seams.sandbox_calls == []
    assert panel.applied_sha1 is None
    assert any("cancelled" in line for line in lines)


def test_apply_to_sandbox_records_the_buffer_hash_and_the_report(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams)

    panel.apply_to_sandbox()

    assert panel.applied_sha1 == panel.text_sha1()
    assert panel.last_check_report() is seams._report


def test_a_report_stops_counting_once_the_buffer_changes(qtbot):
    """The precondition-2 gate is 'green FOR THIS BUFFER' -- a report against
    an older buffer must never read as this buffer's clearance."""
    seams = _Seams()
    panel = _wired(qtbot, seams)
    panel.apply_to_sandbox()
    assert panel.last_check_report() is not None

    panel.editor.insertPlainText("-- edited\n")

    assert panel.last_check_report() is None


def test_apply_to_sandbox_refuses_an_empty_buffer(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams, text="   \n")
    lines = _audit(panel)

    assert panel.apply_to_sandbox() is False

    assert seams.sandbox_calls == []
    assert seams.confirms == []
    assert any("empty" in line for line in lines)


def test_apply_refuses_when_the_database_cannot_be_named(qtbot):
    """A confirmation that does not say WHICH database is not compliant, so an
    unnameable destination is refused rather than confirmed vaguely."""
    seams = _Seams(sandbox_db="")
    panel = _wired(qtbot, seams)
    lines = _audit(panel)

    assert panel.apply_to_sandbox() is False

    assert seams.sandbox_calls == []
    assert seams.confirms == []
    assert any("must name the database" in line for line in lines)


# --- Affordances are absent when unwired (carve-out 2) ----------------------
def test_no_apply_buttons_when_no_seam_is_wired(qtbot):
    """Carve-out 2 applies to the two APPLY buttons, which need a seam. The row
    itself and its "Deploy this edit…" button survive (FQ-009): the picker's
    Save destination needs no seam, so that button is never a dead control."""
    panel = _panel(qtbot)
    assert panel.has_sandbox_apply is False
    assert panel.has_target_apply is False
    assert panel.apply_row is not None
    assert panel.deploy_button is not None
    assert panel.sandbox_button is None and panel.target_button is None
    assert panel.apply_to_sandbox() is False
    assert panel.apply_to_target() is False


def test_context_menu_omits_unwired_apply_entries(qtbot):
    panel = _panel(qtbot)
    labels = [a.text() for a in panel._build_context_menu().actions()]
    assert "Apply to Sandbox" not in labels
    assert "Apply to Target…" not in labels
    # The picker itself stays -- Save is always a reachable destination.
    assert "Deploy this edit…" in labels


def test_wired_seams_add_their_buttons_and_menu_entries(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams)
    assert panel.apply_row is not None
    assert panel.sandbox_button.text() == "Apply to Sandbox"
    assert panel.target_button.text() == "Apply to Target…"
    labels = [a.text() for a in panel._build_context_menu().actions()]
    assert "Apply to Sandbox" in labels and "Apply to Target…" in labels


def test_apply_buttons_appear_and_disappear_with_the_seams(qtbot):
    seams = _Seams()
    panel = _panel(qtbot)
    panel.set_apply_seams(
        apply_to_sandbox=seams.apply_to_sandbox,
        sandbox_database_label=lambda: seams.sandbox_db,
        confirm=seams.confirm,
    )
    assert panel.sandbox_button is not None
    assert panel.has_target_apply is False

    panel.set_apply_seams()

    assert panel.sandbox_button is None and panel.target_button is None
    # The row and the picker button outlive the seams -- see
    # test_no_apply_buttons_when_no_seam_is_wired.
    assert panel.apply_row is not None and panel.deploy_button is not None


def test_apply_is_absent_without_a_confirmation_gate(qtbot):
    """There is no unconfirmed apply path to fall back to, so a missing
    confirm seam removes the gesture rather than skipping the gate."""
    seams = _Seams()
    panel = _wired(qtbot, seams, confirm=False)
    assert panel.has_sandbox_apply is False
    assert panel.has_target_apply is False
    assert panel.apply_to_sandbox() is False
    assert panel.apply_to_target() is False
    assert seams.sandbox_calls == [] and seams.target_calls == []


def test_apply_to_target_is_absent_without_the_live_identity_seam(qtbot):
    """Precondition 1 cannot be enforced without it, and an unenforceable
    precondition must remove the gesture, not weaken it."""
    seams = _Seams()
    panel = DdlObjectEditorPanel(
        _PLAIN,
        _TARGET_SRC,
        apply_to_target=seams.apply_to_target,
        target_database_label=lambda: seams.target_db,
        confirm=seams.confirm,
    )
    qtbot.addWidget(panel)
    assert panel.has_target_apply is False
    assert panel.apply_to_target() is False
    assert seams.target_calls == []


# --- Apply to Target: the four hard preconditions ---------------------------
def _live_same():
    return DdlObjectRef(kind="function", schema="pr", name="recalc")


def test_apply_to_target_invokes_the_write_seam_when_everything_passes(qtbot):
    seams = _Seams(live=_live_same())
    panel = _wired(qtbot, seams)
    panel.record_check_report(_green())

    assert panel.apply_to_target() is True

    assert seams.target_calls == [(_PLAIN, _TARGET_SRC)]


def test_precondition_1_refuses_a_changed_signature_naming_the_mismatch(qtbot):
    """`CREATE OR REPLACE` on a changed (schema, name, argtypes) creates a
    SECOND function and leaves the old one live -- refused outright, with no
    override and no consent path."""
    seams = _Seams(live=DdlObjectRef(kind="function", schema="pr", name="recalc",
                                     arg_types=("integer",)))
    panel = _wired(
        qtbot,
        seams,
        text="CREATE OR REPLACE FUNCTION pr.recalc(p_id bigint) RETURNS void AS $$\n"
        "BEGIN END;\n$$ LANGUAGE plpgsql;\n",
    )
    panel.record_check_report(_green())
    lines = _audit(panel)

    assert panel.apply_to_target() is False

    assert seams.target_calls == []
    assert seams.confirms == []  # no override is offered for this one
    joined = " ".join(lines)
    assert "pr.recalc(bigint)" in joined and "pr.recalc(integer)" in joined


def test_precondition_1_refuses_a_buffer_whose_signature_cannot_be_parsed(qtbot):
    seams = _Seams(live=_live_same())
    panel = _wired(qtbot, seams, text="-- just a comment, no CREATE at all\n")
    panel.record_check_report(_green())
    lines = _audit(panel)

    assert panel.apply_to_target() is False

    assert seams.target_calls == []
    assert any("could not determine the object's signature" in line for line in lines)


def test_precondition_1_allows_an_object_the_target_does_not_have_yet(qtbot):
    seams = _Seams(live=None)
    panel = _wired(qtbot, seams)
    panel.record_check_report(_green())
    lines = _audit(panel)

    assert panel.apply_to_target() is True

    assert any("does not exist in the target catalog" in line for line in lines)


def test_precondition_2_hard_blocks_on_findings_with_no_override(qtbot):
    seams = _Seams(live=_live_same())
    panel = _wired(qtbot, seams)
    panel.record_check_report(
        _Report(statuses=("passed", "passed", "passed", "found_issues"),
                findings=[type("F", (), {"message": "column pr.orders.custmer_id does not exist"})()])
    )
    lines = _audit(panel)

    assert panel.apply_to_target() is False

    assert seams.target_calls == []
    assert seams.confirms == []  # a checked-and-failed result is not overridable
    assert any("was not green" in line for line in lines)


def test_precondition_2_blocks_when_the_ladder_never_ran_and_the_override_is_declined(qtbot):
    seams = _Seams(live=_live_same(), confirm=False)
    panel = _wired(qtbot, seams)
    lines = _audit(panel)

    assert panel.apply_to_target() is False

    assert seams.target_calls == []
    title, text = seams.confirms[0]
    assert "Without Full Validation" in title
    assert "has not been run over this buffer" in text
    assert any("override was declined" in line for line in lines)


def test_precondition_2_override_enumerates_exactly_what_could_not_be_checked(qtbot):
    """Never a generic 'proceed anyway': the dialog names the tiers and why."""
    seams = _Seams(live=_live_same(), confirm=[True, True])
    panel = _wired(qtbot, seams)
    panel.record_check_report(
        _Report(statuses=("passed", "passed", "passed",
                          _Tier("unavailable", "plpgsql_check is not installed")))
    )

    assert panel.apply_to_target() is True

    override = seams.confirms[0][1]
    assert "tier3" in override and "plpgsql_check is not installed" in override
    assert "tier0" not in override  # only the tiers that actually failed to run


def test_precondition_3_confirmation_states_the_transaction_and_the_missing_revert(qtbot):
    seams = _Seams(live=_live_same())
    panel = _wired(qtbot, seams)
    panel.record_check_report(_green())

    panel.apply_to_target()

    text = seams.confirms[-1][1]
    assert "transaction" in text and "rolls back" in text
    assert "no revert snapshot" in text


def test_precondition_4_confirmation_names_the_object_and_the_database(qtbot):
    seams = _Seams(live=_live_same())
    panel = _wired(qtbot, seams)
    panel.record_check_report(_green())

    panel.apply_to_target()

    title, text = seams.confirms[-1]
    assert title == "Apply to Target"
    assert "pr.recalc()" in text and "prod on db01:5432" in text


def test_declined_confirmation_applies_nothing_to_the_target(qtbot):
    seams = _Seams(live=_live_same(), confirm=False)
    panel = _wired(qtbot, seams)
    panel.record_check_report(_green())
    lines = _audit(panel)

    assert panel.apply_to_target() is False

    assert seams.target_calls == []
    assert any("cancelled" in line for line in lines)


def test_apply_to_target_refuses_an_empty_buffer(qtbot):
    seams = _Seams(live=_live_same())
    panel = _wired(qtbot, seams, text="\n\n")
    panel.record_check_report(_green())

    assert panel.apply_to_target() is False

    assert seams.target_calls == []


# --- Reporting under the [Check] prefix ------------------------------------
def test_results_are_reported_to_the_audit_panel_under_the_check_prefix(qtbot):
    seams = _Seams(report=_Report(caveats=["defaults and data are not reproduced"]))
    panel = _wired(qtbot, seams)
    lines = _audit(panel)

    panel.apply_to_sandbox()

    assert lines and all(line.startswith("[Check] ") for line in lines)
    # Never another feature's reserved prefix (§7/§18.4/§22).
    assert not any("[SQL]" in line or "[Lint]" in line for line in lines)
    assert CHECK_PREFIX == "[Check] "


def test_every_tier_is_reported_always_plus_one_line_per_caveat(qtbot):
    """An unavailable tier is stated, never collapsed into the overall OK
    state (§18.5 D3's hard rule)."""
    seams = _Seams(
        report=_Report(
            statuses=("passed", _Tier("unavailable", "no notice channel"), "passed", "passed"),
            caveats=["extensions are not reproduced"],
        )
    )
    panel = _wired(qtbot, seams)
    lines = _audit(panel)

    panel.apply_to_sandbox()

    joined = "\n".join(lines)
    for tier in ("tier0", "tier1", "tier2", "tier3"):
        assert tier in joined
    assert "unavailable -- no notice channel" in joined
    assert "caveat: extensions are not reproduced" in joined


# --- Two Audit channels (§18.5 D3a, overriding §28) -------------------------
class _Finding:
    """A duck-typed `db/ddl_check.py::CheckFinding` -- read by attribute only."""

    def __init__(self, severity, line, message):
        self.severity = severity
        self.line = line
        self.lineno = line
        self.message = message


def _findings(panel):
    """Collect the finding batches the panel emits on `check_findings`."""
    batches = []
    panel.check_findings.connect(lambda batch: batches.append(list(batch)))
    return batches


def test_findings_go_out_as_objects_on_check_findings_and_never_as_narrative(qtbot):
    """The ledger override asserted from BOTH sides: the clickable channel gets
    the objects, and the narrative channel gets no `finding:` line -- a
    pre-formatted string could not carry the line/target roles the host needs."""
    one = _Finding("error", 6, 'record has no field "foo"')
    two = _Finding("warning", None, "target variable is never read")
    seams = _Seams(report=_Report(statuses=("passed", "passed", "passed", "found_issues"),
                                  findings=[one, two]))
    panel = _wired(qtbot, seams)
    lines = _audit(panel)
    batches = _findings(panel)

    panel.apply_to_sandbox()

    # Clickable channel: exactly one batch, carrying the OBJECTS themselves.
    assert len(batches) == 1
    assert batches[0] == [one, two]
    assert batches[0][0] is one and batches[0][1] is two
    # Narrative channel: tiers are still there, findings are not -- not the
    # `finding:` label, not the messages, not even a pre-rendered line number.
    joined = "\n".join(lines)
    assert "tier3" in joined
    assert "finding" not in joined
    assert 'record has no field "foo"' not in joined
    assert "target variable is never read" not in joined


def test_a_report_with_no_findings_does_not_emit_the_findings_channel_at_all(qtbot):
    """An empty batch would render an empty Audit run -- so none is sent."""
    seams = _Seams(report=_Report(caveats=["data is not reproduced"]))
    panel = _wired(qtbot, seams)
    lines = _audit(panel)
    batches = _findings(panel)

    panel.apply_to_sandbox()

    assert batches == []
    assert any("caveat: data is not reproduced" in line for line in lines)


def test_report_check_result_emits_both_channels_with_no_headline(qtbot):
    """Making a Check result VISIBLE, as opposed to `record_check_report`,
    which only RECORDS it for precondition 2."""
    finding = _Finding("error", 12, "unbound record variable")
    report = _Report(statuses=("passed", "passed", "passed", "found_issues"),
                     findings=[finding], caveats=["dynamic EXECUTE is not analyzed"])
    panel = _panel(qtbot)
    lines = _audit(panel)
    batches = _findings(panel)

    panel.report_check_result(report)

    assert batches == [[finding]]
    joined = "\n".join(lines)
    assert "tier3: found_issues" in joined
    assert "caveat: dynamic EXECUTE is not analyzed" in joined
    assert "unbound record variable" not in joined
    # No headline: every line is a tier/caveat line, none an "applied …" notice.
    assert not any("applied" in line for line in lines)
    # Recording stays a separate act.
    assert panel.last_check_report() is None


# --- "Run in Sandbox Console" (§18.5 D4) -- a bridge that executes nothing ---
def test_run_in_console_entry_is_absent_while_the_seam_is_unwired(qtbot):
    panel = _panel(qtbot, text="select 1")
    assert panel.has_run_in_console is False
    labels = [a.text() for a in panel._build_context_menu().actions()]
    assert "Run in Sandbox Console" not in labels


def test_run_in_console_entry_is_present_but_disabled_without_a_selection(qtbot):
    panel = _panel(qtbot, text="select 1")
    panel.set_run_in_console(lambda text: None)
    assert panel.has_run_in_console is True
    action = next(
        a for a in panel._build_context_menu().actions() if a.text() == "Run in Sandbox Console"
    )
    assert action.isEnabled() is False
    assert action.shortcut().isEmpty()


def test_run_in_console_entry_is_enabled_with_a_selection(qtbot):
    panel = _panel(qtbot, text="select 1")
    panel.set_run_in_console(lambda text: None)
    _select_all(panel)
    action = next(
        a for a in panel._build_context_menu().actions() if a.text() == "Run in Sandbox Console"
    )
    assert action.isEnabled() is True


def test_run_in_console_hands_over_the_selection_with_real_newlines_and_executes_nothing(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams)
    handed = []
    panel.set_run_in_console(handed.append)
    _select_all(panel)

    action = next(
        a for a in panel._build_context_menu().actions() if a.text() == "Run in Sandbox Console"
    )
    action.trigger()

    # QTextCursor.selectedText() joins lines with U+2029; the console must get
    # real newlines, and the buffer must reach it unchanged otherwise.
    assert len(handed) == 1
    assert handed[0].splitlines() == _TARGET_SRC.splitlines()
    assert " " not in handed[0]
    assert "\n" in handed[0]
    # It is not an apply: no seam ran, no confirmation was asked for.
    assert seams.sandbox_calls == [] and seams.target_calls == []
    assert seams.confirms == []
    # And the buffer itself is untouched.
    assert panel.text() == _TARGET_SRC


def test_run_in_sandbox_console_is_a_noop_without_a_selection_or_a_console(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams)
    handed = []

    # No console at all.
    _select_all(panel)
    assert panel.run_in_sandbox_console() is False

    # A console, but nothing selected.
    panel.set_run_in_console(handed.append)
    cursor = panel.editor.textCursor()
    cursor.clearSelection()
    panel.editor.setTextCursor(cursor)
    assert panel.run_in_sandbox_console() is False

    assert handed == []
    assert seams.sandbox_calls == [] and seams.target_calls == []


# --- "Deploy this edit…" -- a picker in front of the three gestures ---------
def test_deploy_this_edit_delegates_to_apply_to_sandbox(qtbot, monkeypatch):
    seams = _Seams()
    panel = _wired(qtbot, seams)
    monkeypatch.setattr(panel, "_prompt_destination", lambda: DEST_SANDBOX)

    assert panel.deploy_this_edit() == DEST_SANDBOX

    assert seams.sandbox_calls == [(_PLAIN, _TARGET_SRC)]
    assert seams.target_calls == []


def test_deploy_this_edit_delegates_save_to_the_hosts_existing_save_gesture(qtbot, monkeypatch):
    """It writes no file of its own and touches no database."""
    seams = _Seams()
    panel = _wired(qtbot, seams)
    monkeypatch.setattr(panel, "_prompt_destination", lambda: DEST_SAVE)
    saves = []
    panel.save_requested.connect(lambda: saves.append(1))

    assert panel.deploy_this_edit() == DEST_SAVE

    assert saves == [1]
    assert seams.sandbox_calls == [] and seams.target_calls == []


def test_deploy_this_edit_target_still_runs_every_hard_precondition(qtbot, monkeypatch):
    seams = _Seams(live=DdlObjectRef(kind="function", schema="pr", name="recalc",
                                     arg_types=("integer",)))
    panel = _wired(qtbot, seams)
    panel.record_check_report(_green())
    monkeypatch.setattr(panel, "_prompt_destination", lambda: DEST_TARGET)
    lines = _audit(panel)

    panel.deploy_this_edit()

    # Signature mismatch: refused through the very same precondition 1.
    assert seams.target_calls == []
    assert any("differs from the live object" in line for line in lines)


def test_deploy_this_edit_cancelled_does_nothing(qtbot, monkeypatch):
    seams = _Seams(live=_live_same())
    panel = _wired(qtbot, seams)
    monkeypatch.setattr(panel, "_prompt_destination", lambda: None)
    saves = []
    panel.save_requested.connect(lambda: saves.append(1))

    assert panel.deploy_this_edit() is None

    assert seams.sandbox_calls == [] and seams.target_calls == [] and saves == []


def test_deploy_destinations_omit_gestures_whose_seam_is_unwired(qtbot):
    panel = _panel(qtbot)
    assert panel.deploy_destinations() == [DEST_SAVE]
    seams = _Seams()
    wired = _wired(qtbot, seams)
    assert wired.deploy_destinations() == [DEST_SANDBOX, DEST_SAVE, DEST_TARGET]


# --- FQ-009: the picker is discoverable, and says what is NOT on offer -------
def test_deploy_button_is_always_present_and_runs_the_picker(qtbot, monkeypatch):
    """The crux of FQ-009: the one gesture that answers "where does this edit
    go?" is a visible button, not a right-click-only entry -- and it is there
    with no seam wired at all, because Save always works."""
    panel = _panel(qtbot)
    assert panel.deploy_button is not None
    assert panel.deploy_button.text() == "Deploy this edit…"
    assert panel.deploy_button.isVisible() or panel.deploy_button.parent() is not None
    picked = []
    monkeypatch.setattr(panel, "_prompt_destination", lambda: picked.append(1) or None)

    panel.deploy_button.click()

    assert picked == [1]


def test_deploy_button_carries_no_shortcut_and_is_not_a_default_button(qtbot):
    """Discoverable is not the same as one keystroke away (§18.5)."""
    panel = _panel(qtbot)
    assert panel.deploy_button.shortcut().isEmpty()
    assert panel.deploy_button.autoDefault() is False
    assert panel.deploy_button.isDefault() is False


def test_unavailable_destinations_name_the_sandbox_and_target_with_reasons(qtbot):
    panel = _panel(qtbot)
    missing = dict(panel.unavailable_destinations())
    assert set(missing) == {DEST_SANDBOX, DEST_TARGET}
    assert "Open Sandbox Session" in missing[DEST_SANDBOX]
    assert "Precondition 1" in missing[DEST_TARGET]
    # FQ-020 wired the quality lane, so the reason is now a CONNECTION fact and
    # names both places a target can come from -- the old "not wired in this
    # build" wording would be a lie about a gesture that works projectless.
    assert "Connection Setup" in missing[DEST_TARGET]
    assert "not wired in this build" not in missing[DEST_TARGET]
    # Save is never listed -- it needs no seam.
    assert DEST_SAVE not in missing


def test_unavailable_destinations_shrinks_as_seams_are_wired(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams)
    assert panel.unavailable_destinations() == []


def test_deploy_prompt_text_states_why_a_destination_is_missing(qtbot):
    """The requester's complaint was that there was "no option to save to the
    database"; an absent entry cannot say why. The prose does."""
    panel = _panel(qtbot)
    text = panel.deploy_prompt_text()
    assert _PLAIN.qualified in text
    assert "Not available right now:" in text
    # FQ-020's labels: the picker and the `Deployment` menu must call the same
    # gesture the same thing, so both read `DESTINATION_LABELS`.
    assert "Run on sandbox" in text and "Run on quality" in text
    assert "Connection Setup" in text


def test_deploy_prompt_text_is_just_the_question_when_all_seams_are_wired(qtbot):
    seams = _Seams()
    panel = _wired(qtbot, seams)
    assert "Not available" not in panel.deploy_prompt_text()


# --- FQ-009: precondition 1 cannot be cleared by an unreachable target -------
def test_a_failing_live_identity_lookup_refuses_instead_of_reading_as_absent(
    qtbot,
):
    """`live_identity` returning None means "the target does not have this
    object" -- a real, precondition-1-clearing fact. A lookup that FAILED must
    never be reported that way, so any raise is a stated refusal."""

    def boom(_ref):
        raise RuntimeError("could not connect to quality")

    seams = _Seams()
    panel = _panel(
        qtbot,
        text=_TARGET_SRC,
        apply_to_target=seams.apply_to_target,
        live_identity=boom,
        target_database_label=lambda: seams.target_db,
        confirm=seams.confirm,
    )
    panel.record_check_report(_green())
    lines = _audit(panel)

    assert panel.apply_to_target() is False

    assert seams.target_calls == []
    assert seams.confirms == []
    assert any("could not read the live object's identity" in line for line in lines)
    assert any("could not connect to quality" in line for line in lines)


# --- No apply gesture is ever one keystroke away (a safety property) --------
def test_no_shortcut_is_bound_to_any_apply_gesture(qtbot):
    """Apply is deliberately unbound -- an irreversible outward effect must not
    be one keystroke away. Asserted three ways: the panel's QShortcut set, the
    context-menu actions, and a battery of plausible key presses."""
    from PySide6.QtGui import QShortcut

    seams = _Seams(live=_live_same())
    panel = _wired(qtbot, seams)
    panel.record_check_report(_green())

    sequences = {s.key().toString() for s in panel.findChildren(QShortcut)}
    # Format Selection, plus FQ-016's two Find/Replace-bar FOCUS shortcuts (which
    # move no data anywhere). Nothing that applies, deploys or executes.
    assert sequences == {"Ctrl+Alt+F", "Ctrl+F", "Ctrl+R"}

    for action in panel._build_context_menu().actions():
        if action.text() in ("Apply to Sandbox", "Apply to Target…", "Deploy this edit…"):
            assert action.shortcut().isEmpty(), action.text()

    ctrl = Qt.KeyboardModifier.ControlModifier
    ctrl_shift = ctrl | Qt.KeyboardModifier.ShiftModifier
    ctrl_alt = ctrl | Qt.KeyboardModifier.AltModifier
    for key, mods in (
        (Qt.Key.Key_Return, ctrl),
        (Qt.Key.Key_Enter, ctrl),
        (Qt.Key.Key_D, ctrl),
        (Qt.Key.Key_A, ctrl_alt),
        (Qt.Key.Key_S, ctrl_shift),
        (Qt.Key.Key_T, ctrl_alt),
        (Qt.Key.Key_P, ctrl_shift),
        (Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier),
    ):
        panel.eventFilter(panel.editor, _shortcut_override(key, mods))
        panel.eventFilter(panel.editor, _key_press(key, mods))
        QTest.keyClick(panel.editor, key, mods)

    assert seams.sandbox_calls == []
    assert seams.target_calls == []
    assert seams.confirms == []


# --- parse_buffer_identity (precondition 1's buffer half) -------------------
def test_parse_buffer_identity_reads_schema_name_and_argument_types():
    ref = parse_buffer_identity(
        "CREATE OR REPLACE FUNCTION pr.calc_total(p_id integer, p_when timestamp with time zone)\n"
        " RETURNS numeric AS $$ BEGIN END $$ LANGUAGE plpgsql;",
        _PLAIN,
    )
    assert ref.kind == "function"
    assert (ref.schema, ref.name) == ("pr", "calc_total")
    assert ref.arg_types == ("integer", "timestamp with time zone")


def test_parse_buffer_identity_drops_out_arguments_and_defaults():
    ref = parse_buffer_identity(
        "CREATE FUNCTION pr.f(IN p_a integer, OUT p_b text, p_c double precision DEFAULT 1.0)"
        " RETURNS void AS $$ $$ LANGUAGE sql;",
        _PLAIN,
    )
    assert ref.arg_types == ("integer", "double precision")


def test_parse_buffer_identity_handles_no_arguments_and_types_with_parens():
    assert parse_buffer_identity("CREATE FUNCTION pr.f() RETURNS void AS $$ $$;", _PLAIN).arg_types == ()
    ref = parse_buffer_identity("CREATE FUNCTION pr.f(p numeric(10,2)) RETURNS void AS $$ $$;", _PLAIN)
    assert ref.arg_types == ("numeric(10,2)",)


def test_parse_buffer_identity_falls_back_to_the_tabs_schema_when_unqualified():
    ref = parse_buffer_identity("CREATE PROCEDURE recalc() AS $$ $$;", _PLAIN)
    assert (ref.kind, ref.schema, ref.name) == ("procedure", "pr", "recalc")


def test_parse_buffer_identity_reads_a_trigger_name_and_table():
    ref = parse_buffer_identity(
        "CREATE TRIGGER trg_audit AFTER INSERT ON pr.orders\n"
        " FOR EACH ROW EXECUTE FUNCTION pr.audit();",
        _TRIGGER,
    )
    assert (ref.kind, ref.schema, ref.name, ref.table) == ("trigger", "pr", "trg_audit", "orders")


def test_parse_buffer_identity_returns_none_when_there_is_no_create():
    assert parse_buffer_identity("SELECT 1;", _PLAIN) is None
