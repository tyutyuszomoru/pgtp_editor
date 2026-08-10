# pgtp_editor/ui/schema_gesture_seam.py -> tests/ui/test_schema_gestures.py
"""FQ-030's schema-fed caret gestures, where they meet a real panel.

Four surfaces, all explicit-trigger and all reading one injected `SchemaIndex`:

* the completion popup's **richer column rows** (slice 0) -- the display gains
  the type and the column's attributes while the KEY, which is what lands in
  the buffer, stays the bare column name;
* the dotted-path cascade's **third segment** (`hr.employee.` -> its columns);
* **JOIN-on-FK** (Ctrl+Alt+J), unambiguous and ambiguous;
* **signature help** (Ctrl+Shift+Space), which inserts nothing.

`SchemaIndex` is built from a canned `DatabaseSchema`, never from a live
connection -- the same style as `test_ddl_object_editor_completion.py`.
"""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
)
from pgtp_editor.db.schema_index import SchemaIndex
from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel, DdlObjectRef
from pgtp_editor.ui.schema_gesture_seam import describe_signature, signature_help_at


def _column(name, data_type, *, pk=False, fk=None, nullable=True):
    return ColumnInfo(
        name=name,
        data_type=data_type,
        is_pk=pk,
        is_fk=fk is not None,
        is_nullable=nullable,
        default=None,
        fk_target=fk,
    )


def _schema():
    """One employee/dept/paystub/jobcard shop.

    `hr.paystub` has exactly ONE foreign key, so a join from it is
    unambiguous; `hr.jobcard` has TWO into the same table (`employee_id` and
    `approver_id`), which is the case that must be OFFERED rather than guessed.
    """
    tables = {
        "hr.employee": TableInfo(
            name="hr.employee",
            kind="table",
            columns=[
                _column("id", "integer", pk=True, nullable=False),
                _column("full_name", "text", nullable=False),
            ],
        ),
        "hr.paystub": TableInfo(
            name="hr.paystub",
            kind="table",
            columns=[
                _column("id", "integer", pk=True, nullable=False),
                _column("employee_id", "integer", fk="hr.employee.id", nullable=False),
                _column("amount", "numeric", nullable=False),
            ],
        ),
        "hr.jobcard": TableInfo(
            name="hr.jobcard",
            kind="table",
            columns=[
                _column("id", "integer", pk=True, nullable=False),
                _column("employee_id", "integer", fk="hr.employee.id"),
                _column("approver_id", "integer", fk="hr.employee.id"),
            ],
        ),
    }
    routines = {
        "hr.calc_total(integer, text)": RoutineInfo(
            schema="hr",
            name="calc_total",
            arg_types=["integer", "text"],
            return_type="numeric",
            language="plpgsql",
            source="",
            kind="function",
            args=[("amount", "integer"), ("currency", "text")],
        ),
    }
    return DatabaseSchema(tables=tables, routines=routines)


def _index():
    return SchemaIndex(_schema())


def _panel(qtbot, text=""):
    panel = DdlObjectEditorPanel(
        DdlObjectRef(kind="function", schema="hr", name="recalc"), text
    )
    qtbot.addWidget(panel)
    panel.set_schema_index(_index())
    return panel


def _caret_after(panel, marker: str) -> None:
    text = panel.editor.toPlainText()
    cursor = panel.editor.textCursor()
    cursor.setPosition(text.index(marker) + len(marker))
    panel.editor.setTextCursor(cursor)


def _console(qtbot, text=""):
    from pgtp_editor.ui.sql_console_panel import SqlConsolePanel

    panel = SqlConsolePanel(session_provider=lambda: None)
    qtbot.addWidget(panel)
    panel.set_schema_index(_index())
    panel.set_sql(text)
    return panel


# --- slice 0: the richer popup row, and the bare key ------------------------
def test_column_rows_show_the_type_while_the_key_stays_the_bare_name(qtbot):
    panel = _panel(qtbot, text="select p. from hr.paystub p")
    _caret_after(panel, "select p.")

    panel._show_completions()

    popup = panel._completion_popup
    assert popup is not None and popup.isVisible()
    # The key is what gets inserted -- it must never carry the description.
    assert popup.visible_keys() == ["id", "employee_id", "amount"]
    rows = [popup.item(i).text() for i in range(popup.count())]
    assert rows[0] == "id  integer · PK · NOT NULL"
    assert "→ hr.employee.id" in rows[1]


def test_choosing_a_described_column_inserts_only_its_name(qtbot):
    panel = _panel(qtbot, text="select p.emp from hr.paystub p")
    _caret_after(panel, "select p.emp")

    panel._show_completions()
    popup = panel._completion_popup
    key = popup.visible_keys()[0]
    panel._complete_identifier(key)

    assert panel.editor.toPlainText() == "select p.employee_id from hr.paystub p"


# --- slice 0: the cascade's third segment -----------------------------------
def test_schema_dot_table_dot_offers_that_tables_columns(qtbot):
    panel = _panel(qtbot, text="select hr.paystub. from hr.paystub")
    _caret_after(panel, "select hr.paystub.")

    panel._show_completions()

    popup = panel._completion_popup
    assert popup is not None and popup.isVisible()
    assert popup.visible_keys() == ["id", "employee_id", "amount"]


def test_schema_dot_table_dot_filters_by_the_typed_prefix(qtbot):
    panel = _panel(qtbot, text="select hr.paystub.am from hr.paystub")
    _caret_after(panel, "select hr.paystub.am")

    panel._show_completions()

    assert panel._completion_popup.visible_keys() == ["amount"]


def test_an_unknown_third_segment_shows_nothing_rather_than_an_empty_popup(qtbot):
    panel = _panel(qtbot, text="select hr.nosuch. from hr.paystub")
    _caret_after(panel, "select hr.nosuch.")

    panel._show_completions()

    popup = panel._completion_popup
    assert popup is None or not popup.isVisible()


def test_the_console_cascades_to_columns_too(qtbot):
    console = _console(qtbot, text="SELECT hr.paystub. FROM hr.paystub")
    cursor = console.editor.textCursor()
    cursor.setPosition(len("SELECT hr.paystub."))
    console.editor.setTextCursor(cursor)

    console.show_completions()

    assert console._completion_popup.visible_keys() == ["id", "employee_id", "amount"]


def test_the_consoles_cascade_is_empty_for_an_unknown_table(qtbot):
    console = _console(qtbot, text="SELECT hr.nosuch. FROM hr.paystub")
    cursor = console.editor.textCursor()
    cursor.setPosition(len("SELECT hr.nosuch."))
    console.editor.setTextCursor(cursor)

    console.show_completions()

    popup = console._completion_popup
    assert popup is None or not popup.isVisible()


# --- slice 3: JOIN-on-FK ----------------------------------------------------
def test_one_foreign_key_writes_the_join_straight_into_the_buffer(qtbot):
    panel = _panel(qtbot, text="select * from hr.paystub p")
    _caret_after(panel, "hr.paystub p")

    assert panel.join_on_fk() is True

    text = panel.editor.toPlainText()
    assert text == "select * from hr.paystub p join hr.employee e on p.employee_id = e.id"
    # No popup for an unambiguous answer.
    assert panel._completion_popup is None or not panel._completion_popup.isVisible()


def test_ctrl_alt_j_is_the_key_for_it(qtbot):
    panel = _panel(qtbot, text="select * from hr.paystub p")
    _caret_after(panel, "hr.paystub p")
    panel.editor.setFocus()

    QTest.keyClick(
        panel.editor,
        Qt.Key.Key_J,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )

    assert "join hr.employee e on p.employee_id = e.id" in panel.editor.toPlainText()


def test_the_written_join_is_a_single_undo(qtbot):
    panel = _panel(qtbot, text="select * from hr.paystub p")
    _caret_after(panel, "hr.paystub p")
    panel.join_on_fk()

    panel.editor.undo()

    assert panel.editor.toPlainText() == "select * from hr.paystub p"


def test_two_foreign_keys_are_offered_rather_than_guessed_at(qtbot):
    panel = _panel(qtbot, text="select * from hr.jobcard j")
    _caret_after(panel, "hr.jobcard j")

    assert panel.join_on_fk() is True

    popup = panel._completion_popup
    assert popup is not None and popup.isVisible()
    displays = [popup.item(i).text() for i in range(popup.count())]
    assert len(displays) == 2
    assert any("j.approver_id" in row for row in displays)
    assert any("j.employee_id" in row for row in displays)
    # Nothing was written while the question is still open.
    assert panel.editor.toPlainText() == "select * from hr.jobcard j"


def test_choosing_one_of_the_offered_joins_writes_exactly_that_one(qtbot):
    panel = _panel(qtbot, text="select * from hr.jobcard j")
    _caret_after(panel, "hr.jobcard j")
    panel.join_on_fk()
    popup = panel._completion_popup
    chosen = next(
        key
        for key in popup.visible_keys()
        if "approver_id" in key
    )

    panel._apply_join_choice(chosen)

    assert "j.approver_id = e.id" in panel.editor.toPlainText()
    assert "employee_id" not in panel.editor.toPlainText()


def test_a_join_refusal_reaches_the_user(qtbot):
    """FQ-023: a gesture that cannot run says why -- here through the signal
    the host files as an Audit row, and the caret tooltip."""
    panel = _panel(qtbot, text="select * from jobcard j")  # no schema written
    _caret_after(panel, "jobcard j")
    reasons = []
    panel.editor.expansion_refused.connect(reasons.append)

    assert panel.join_on_fk() is False

    assert reasons and "schema-qualified" in reasons[0]
    assert panel.editor.toPlainText() == "select * from jobcard j"


def test_a_table_with_no_foreign_key_at_all_says_so(qtbot):
    panel = _panel(qtbot, text="select * from hr.employee e")
    _caret_after(panel, "hr.employee e")
    reasons = []
    panel.editor.expansion_refused.connect(reasons.append)

    assert panel.join_on_fk() is False

    assert reasons and "foreign key" in reasons[0]


def test_the_console_writes_joins_too(qtbot):
    console = _console(qtbot, text="SELECT * FROM hr.paystub p")
    cursor = console.editor.textCursor()
    cursor.setPosition(len("SELECT * FROM hr.paystub p"))
    console.editor.setTextCursor(cursor)

    assert console.join_on_fk() is True

    assert "JOIN hr.employee e ON p.employee_id = e.id" in console.editor.toPlainText()


def test_a_surface_with_no_schema_states_the_missing_prerequisite(qtbot):
    panel = DdlObjectEditorPanel(
        DdlObjectRef(kind="function", schema="hr", name="recalc"),
        "select * from hr.paystub p",
    )
    qtbot.addWidget(panel)
    reasons = []
    panel.editor.expansion_refused.connect(reasons.append)

    assert panel.join_on_fk() is False

    assert reasons and "schema" in reasons[0]


# --- slice 3: signature help ------------------------------------------------
def test_signature_help_names_the_parameter_the_caret_is_on(qtbot):
    panel = _panel(qtbot, text="select hr.calc_total(1, 'usd')")
    hints = []
    panel.editor.hint_shown.connect(hints.append)

    _caret_after(panel, "hr.calc_total(1")
    assert panel.show_signature_help() is True
    assert hints[-1].splitlines()[0] == (
        "hr.calc_total(amount integer, currency text) RETURNS numeric"
    )
    assert hints[-1].splitlines()[1] == "→ amount integer"

    _caret_after(panel, "hr.calc_total(1, 'us")
    panel.show_signature_help()
    assert hints[-1].splitlines()[1] == "→ currency text"


def test_signature_help_inserts_nothing(qtbot):
    panel = _panel(qtbot, text="select hr.calc_total(1, 'usd')")
    _caret_after(panel, "hr.calc_total(1")

    panel.show_signature_help()

    assert panel.editor.toPlainText() == "select hr.calc_total(1, 'usd')"


def test_ctrl_shift_space_is_the_key_for_it(qtbot):
    panel = _panel(qtbot, text="select hr.calc_total(1, 'usd')")
    _caret_after(panel, "hr.calc_total(1")
    panel.editor.setFocus()
    hints = []
    panel.editor.hint_shown.connect(hints.append)

    QTest.keyClick(
        panel.editor,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )

    assert hints and "calc_total" in hints[0]


def test_a_caret_outside_any_call_refuses_with_a_reason(qtbot):
    panel = _panel(qtbot, text="select 1")
    _caret_after(panel, "select 1")
    reasons = []
    panel.editor.expansion_refused.connect(reasons.append)

    assert panel.show_signature_help() is False

    assert reasons and reasons[0]


def test_an_unknown_routine_refuses_naming_it(qtbot):
    panel = _panel(qtbot, text="select hr.nosuch(1)")
    _caret_after(panel, "hr.nosuch(1")
    reasons = []
    panel.editor.expansion_refused.connect(reasons.append)

    assert panel.show_signature_help() is False

    assert reasons and "hr.nosuch" in reasons[0]


def test_the_console_answers_signature_help_too(qtbot):
    console = _console(qtbot, text="SELECT hr.calc_total(1, 'usd')")
    cursor = console.editor.textCursor()
    cursor.setPosition(len("SELECT hr.calc_total(1"))
    console.editor.setTextCursor(cursor)
    hints = []
    console.editor.hint_shown.connect(hints.append)

    assert console.show_signature_help() is True

    assert "amount integer" in hints[-1]


# --- the seam's own rendering ------------------------------------------------
def test_describe_signature_states_a_refusal_verbatim():
    help = signature_help_at(_index(), "select 1", len("select 1"))
    assert not help
    assert describe_signature(help) == help.reason


def test_signature_help_reads_no_database(qtbot):
    """§18.6's invariant: the gesture only ever consults the injected index."""
    import pgtp_editor.ui.schema_gesture_seam as mod

    source = open(mod.__file__, encoding="utf-8").read()
    assert "db.introspect" not in source
    assert "connect(" not in source


# --- nothing on an edit signal ----------------------------------------------
def test_typing_never_resolves_a_call_site_or_a_join_site(qtbot, monkeypatch):
    """The performance invariant, restated for slice 3: both analyzers are
    explicit-trigger only. `resolve_caret_context` already has this test; these
    two are the new temptations (signature help especially, which every other
    editor shows live)."""
    import pgtp_editor.ui.schema_gesture_seam as mod

    calls = []
    monkeypatch.setattr(mod, "find_call_site", lambda *a, **k: calls.append("call"))
    monkeypatch.setattr(mod, "find_join_site", lambda *a, **k: calls.append("join"))
    panel = _panel(qtbot, text="select hr.calc_total(")
    panel.editor.setFocus()

    QTest.keyClicks(panel.editor, "1, 'usd')")

    assert calls == []
