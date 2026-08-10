# tests/ui/test_alter_column_dialogs.py
"""Tests for the FQ-025 slice 1 column-operation dialogs.

Driven entirely by methods: no dialog is ever `.exec()`-ed (modal-hang
guardrail) and none opens a connection — the table and column lists are
injected as plain stubs, so these tests never touch a database. SQL is asserted
against `db/ddl_skeleton.py`'s output where the point is "the dialog feeds the
emitter", and against a golden string where the point is "this is what the user
sees pasted into the tab".
"""
import pytest
from PySide6.QtWidgets import QDialogButtonBox

from pgtp_editor.db.ddl_skeleton import (
    drop_column_skeleton,
    set_column_not_null_skeleton,
)
from pgtp_editor.ui.alter_column_dialogs import (
    OP_DROP_COLUMN,
    OP_DROP_DEFAULT,
    OP_DROP_NOT_NULL,
    OP_SET_NOT_NULL,
    AddColumnDialog,
    ChangeColumnTypeDialog,
    ColumnActionDialog,
    RenameColumnDialog,
    SetColumnDefaultDialog,
)

# Stub injected data — the shape the wiring pass will build from the already
# loaded `introspect.DatabaseSchema`, expressed here as literals.
TABLES = ["public.customers", "public.orders"]
COLUMNS = {
    "public.orders": ["id", "code", "placed_at"],
    "public.customers": ["id", "email"],
}


def _ok(dialog):
    return dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)


def _add(qtbot, dialog):
    qtbot.addWidget(dialog)
    return dialog


def _action(qtbot, operation=OP_DROP_COLUMN, table="public.orders", column="code"):
    return _add(
        qtbot,
        ColumnActionDialog(
            operation=operation,
            table=table,
            column=column,
            tables=TABLES,
            columns=COLUMNS,
        ),
    )


def _context_kwargs(table="public.orders", column="code"):
    return dict(table=table, column=column, tables=TABLES, columns=COLUMNS)


# --- The click context: defaults to it, but changeable --------------------
@pytest.mark.parametrize(
    "factory",
    [ColumnActionDialog, RenameColumnDialog, ChangeColumnTypeDialog, SetColumnDefaultDialog],
)
def test_table_and_column_default_to_the_click_context(qtbot, factory):
    kwargs = _context_kwargs()
    if factory is ColumnActionDialog:
        kwargs["operation"] = OP_DROP_COLUMN
    dialog = _add(qtbot, factory(**kwargs))

    assert dialog.table() == "public.orders"
    assert dialog.column() == "code"
    # ...and the origin is also stated read-only, independent of the dropdowns.
    assert dialog.context_table() == "public.orders"
    assert dialog.context_column() == "code"


def test_the_table_and_column_dropdowns_can_be_changed(qtbot):
    dialog = _action(qtbot)
    assert dialog.available_tables() == sorted(TABLES)

    dialog._table_combo.setCurrentText("public.customers")
    assert dialog.table() == "public.customers"
    # The column list follows the chosen table, and starts at its first column.
    assert dialog.available_columns() == ["id", "email"]
    assert dialog.column() == "id"

    dialog._column_combo.setCurrentText("email")
    assert dialog.skeleton() == drop_column_skeleton(
        table="public.customers", column="email"
    )
    # The click context is remembered even after the dropdowns moved away.
    assert dialog.context_table() == "public.orders"


def test_returning_to_the_origin_table_restores_the_clicked_column(qtbot):
    dialog = _action(qtbot)
    dialog._table_combo.setCurrentText("public.customers")
    dialog._table_combo.setCurrentText("public.orders")
    assert dialog.column() == "code"


def test_a_clicked_table_missing_from_the_injected_list_is_still_offered(qtbot):
    dialog = _add(
        qtbot,
        ColumnActionDialog(
            operation=OP_DROP_COLUMN,
            table="public.legacy",
            column="id",
            tables=TABLES,
            columns={"public.legacy": ["id"]},
        ),
    )
    assert "public.legacy" in dialog.available_tables()
    assert dialog.table() == "public.legacy"


# --- Injected data only: no database, no introspection --------------------
def test_dialogs_need_no_db_import_and_accept_callables(qtbot):
    import ast

    import pgtp_editor.ui.alter_column_dialogs as module

    with open(module.__file__, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    # The dialogs know about the emitter and the identifier allowlist, and
    # nothing that can reach a database.
    assert not any(
        name.endswith("introspect") or "psycopg" in name or name.endswith("connection")
        for name in imported
    ), sorted(imported)

    calls = []

    def columns_for(table):
        calls.append(table)
        return COLUMNS[table]

    dialog = _add(
        qtbot,
        ColumnActionDialog(
            operation=OP_SET_NOT_NULL,
            table="public.orders",
            column="code",
            tables=lambda: TABLES,
            columns=columns_for,
        ),
    )
    assert calls == ["public.orders"]
    assert dialog.skeleton() == set_column_not_null_skeleton(
        table="public.orders", column="code"
    )


def test_a_bare_column_sequence_describes_the_bound_table_only(qtbot):
    dialog = _add(
        qtbot,
        ColumnActionDialog(
            operation=OP_DROP_COLUMN,
            table="public.orders",
            column="code",
            tables=TABLES,
            columns=["id", "code"],
        ),
    )
    assert dialog.available_columns() == ["id", "code"]
    dialog._table_combo.setCurrentText("public.customers")
    # No fabricated column set for a table nobody described.
    assert dialog.available_columns() == []
    assert not _ok(dialog).isEnabled()


# --- ColumnActionDialog: the four "pick a column" operations --------------
@pytest.mark.parametrize(
    "operation,expected",
    [
        (OP_DROP_COLUMN, 'ALTER TABLE "public"."orders" DROP COLUMN "code";\n'),
        (
            OP_SET_NOT_NULL,
            'ALTER TABLE "public"."orders" ALTER COLUMN "code" SET NOT NULL;\n',
        ),
        (
            OP_DROP_NOT_NULL,
            'ALTER TABLE "public"."orders" ALTER COLUMN "code" DROP NOT NULL;\n',
        ),
        (
            OP_DROP_DEFAULT,
            'ALTER TABLE "public"."orders" ALTER COLUMN "code" DROP DEFAULT;\n',
        ),
    ],
)
def test_each_column_action_renders_its_statement(qtbot, operation, expected):
    dialog = _action(qtbot, operation=operation)
    assert dialog.operation() == operation
    assert dialog.is_valid()
    assert _ok(dialog).isEnabled()
    assert dialog.skeleton() == expected


def test_an_unknown_operation_is_refused_at_construction(qtbot):
    with pytest.raises(ValueError):
        ColumnActionDialog(operation="drop_database", table="public.orders")


# --- Accessors after `accepted` -------------------------------------------
def test_accepted_fires_and_the_accessors_read_back(qtbot):
    dialog = _add(
        qtbot,
        AddColumnDialog(table="public.orders", column="code", tables=TABLES, columns=COLUMNS),
    )
    dialog._name_edit.setText("nickname")
    dialog._type_combo.setCurrentText("text")
    dialog._nullable_check.setChecked(False)
    dialog._comment_edit.setText("what they go by")

    with qtbot.waitSignal(dialog.accepted, timeout=1000):
        _ok(dialog).click()

    assert dialog.table() == "public.orders"
    assert dialog.column_name() == "nickname"
    assert dialog.datatype() == "text"
    assert dialog.nullable() is False
    assert dialog.comment() == "what they go by"


def test_add_column_with_a_comment_reaches_the_caller_as_two_statements(qtbot):
    dialog = _add(
        qtbot,
        AddColumnDialog(table="public.orders", tables=TABLES, columns=COLUMNS),
    )
    dialog._name_edit.setText("nickname")
    dialog._type_combo.setCurrentText("text")
    dialog._comment_edit.setText("what they go by")

    with qtbot.waitSignal(dialog.accepted, timeout=1000):
        _ok(dialog).click()

    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" ADD COLUMN "nickname" text;\n'
        'COMMENT ON COLUMN "public"."orders"."nickname" '
        "IS 'what they go by';\n"
    )


def test_add_column_without_a_comment_is_one_statement(qtbot):
    dialog = _add(
        qtbot,
        AddColumnDialog(table="public.orders", tables=TABLES, columns=COLUMNS),
    )
    dialog._name_edit.setText("nickname")
    dialog._type_combo.setCurrentText("text")
    dialog._nullable_check.setChecked(False)
    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" ADD COLUMN "nickname" text NOT NULL;\n'
    )


def test_add_column_offers_no_column_dropdown_but_keeps_the_context(qtbot):
    dialog = _add(
        qtbot,
        AddColumnDialog(table="public.orders", column="code", tables=TABLES, columns=COLUMNS),
    )
    assert dialog.column() == ""
    assert dialog.context_column() == "code"


# --- Rename / change type / set default -----------------------------------
def test_rename_column_renders_and_refuses_the_same_name(qtbot):
    dialog = _add(qtbot, RenameColumnDialog(**_context_kwargs()))
    assert not _ok(dialog).isEnabled()

    dialog._new_name_edit.setText("order_code")
    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" RENAME COLUMN "code" TO "order_code";\n'
    )
    assert _ok(dialog).isEnabled()

    dialog._new_name_edit.setText("code")
    assert not _ok(dialog).isEnabled()
    assert "same as the current one" in dialog._error_label.text()


def test_change_type_without_using_omits_the_clause(qtbot):
    dialog = _add(qtbot, ChangeColumnTypeDialog(**_context_kwargs()))
    dialog._type_combo.setCurrentText("integer")
    assert dialog.using() == ""
    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" ALTER COLUMN "code" TYPE integer;\n'
    )


def test_change_type_with_a_typed_using_clause(qtbot):
    dialog = _add(qtbot, ChangeColumnTypeDialog(**_context_kwargs()))
    dialog._type_combo.setCurrentText("integer")
    dialog._using_edit.setText("trim(code)::integer")
    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" ALTER COLUMN "code" TYPE integer '
        "USING trim(code)::integer;\n"
    )


def test_set_default_renders_the_typed_expression(qtbot):
    dialog = _add(qtbot, SetColumnDefaultDialog(**_context_kwargs()))
    assert not _ok(dialog).isEnabled()
    dialog._expression_edit.setText("now()")
    assert dialog.default_expression() == "now()"
    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" ALTER COLUMN "code" SET DEFAULT now();\n'
    )
    assert _ok(dialog).isEnabled()


def test_the_free_sql_fields_take_no_injected_initial_value(qtbot):
    """Provenance rule: `USING` and `DEFAULT` carry typed input only, so no
    constructor here accepts a starting value for them."""
    with pytest.raises(TypeError):
        ChangeColumnTypeDialog(**_context_kwargs(), using="1")
    with pytest.raises(TypeError):
        SetColumnDefaultDialog(**_context_kwargs(), expression="1")


# --- OK gating and the emitter's own error text ---------------------------
def test_ok_is_disabled_until_the_input_is_valid(qtbot):
    dialog = _add(
        qtbot, AddColumnDialog(table="public.orders", tables=TABLES, columns=COLUMNS)
    )
    assert not _ok(dialog).isEnabled()
    assert not dialog.is_valid()

    dialog._name_edit.setText("nickname")
    assert _ok(dialog).isEnabled()
    assert dialog._error_label.text() == ""


def test_a_hostile_column_name_surfaces_the_emitters_refusal(qtbot):
    dialog = _add(
        qtbot, AddColumnDialog(table="public.orders", tables=TABLES, columns=COLUMNS)
    )
    dialog._name_edit.setText('bad"; DROP TABLE t; --')
    assert not _ok(dialog).isEnabled()
    assert 'bad"; DROP TABLE t; --' in dialog._error_label.text()
    assert dialog.skeleton() == ""


def test_an_empty_datatype_surfaces_the_emitters_message(qtbot):
    dialog = _add(
        qtbot, AddColumnDialog(table="public.orders", tables=TABLES, columns=COLUMNS)
    )
    dialog._name_edit.setText("nickname")
    dialog._type_combo.setCurrentText("")
    assert dialog._error_label.text() == "a column needs a datatype"
    assert not _ok(dialog).isEnabled()


def test_an_unbalanced_using_clause_surfaces_the_emitters_message(qtbot):
    dialog = _add(qtbot, ChangeColumnTypeDialog(**_context_kwargs()))
    dialog._type_combo.setCurrentText("integer")
    dialog._using_edit.setText("trim(code::integer")
    assert "unbalanced parentheses" in dialog._error_label.text()
    assert not _ok(dialog).isEnabled()


def test_a_default_expression_that_could_escape_the_statement_is_refused(qtbot):
    dialog = _add(qtbot, SetColumnDefaultDialog(**_context_kwargs()))
    dialog._expression_edit.setText("0 -- comment out the rest")
    assert "SQL comment" in dialog._error_label.text()
    assert not _ok(dialog).isEnabled()


def test_a_programmatic_accept_cannot_smuggle_invalid_ddl_through(qtbot):
    dialog = _add(
        qtbot, AddColumnDialog(table="public.orders", tables=TABLES, columns=COLUMNS)
    )
    fired = []
    dialog.accepted.connect(lambda: fired.append(True))
    dialog._buttons.accepted.emit()
    assert fired == []

    dialog._name_edit.setText("nickname")
    dialog._buttons.accepted.emit()
    assert fired == [True]


def test_no_columns_for_the_table_blocks_ok_with_an_explanation(qtbot):
    dialog = _add(
        qtbot,
        ColumnActionDialog(
            operation=OP_DROP_COLUMN,
            table="public.empty",
            tables=["public.empty"],
            columns={},
        ),
    )
    assert not _ok(dialog).isEnabled()
    assert "no columns" in dialog._error_label.text()
