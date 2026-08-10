# tests/ui/test_table_dialogs.py
"""Tests for the FQ-025 slice 3 index / comment / whole-table dialogs.

Same posture as slices 1 and 2 (`test_alter_column_dialogs.py`,
`test_constraint_dialogs.py`): every dialog is driven through its methods, none
is ever `.exec()`-ed (modal-hang guardrail), and none opens a connection —
tables, columns and the existing indexes are all injected as plain literals.
Generated SQL is asserted against `db/ddl_skeleton.py` where the point is "the
dialog feeds the emitter", and against a golden string where the point is "this
is what the user sees pasted into the tab".
"""
from dataclasses import dataclass, field

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from pgtp_editor.db.ddl_skeleton import (
    INDEX_METHODS,
    ColumnSpec,
    create_index_skeleton,
    create_table_skeleton,
    drop_index_skeleton,
    drop_table_skeleton,
    set_column_comment_skeleton,
    set_table_comment_skeleton,
)
from pgtp_editor.ui.table_dialogs import (
    OP_COLUMN_COMMENT,
    OP_TABLE_COMMENT,
    CreateIndexDialog,
    CreateTableDialog,
    DropIndexDialog,
    DropTableDialog,
    SetCommentDialog,
)

TABLES = ["public.customers", "public.orders"]
COLUMNS = {
    "public.orders": ["id", "tenant", "code", "customer_id"],
    "public.customers": ["id", "tenant", "email"],
}


@dataclass(frozen=True)
class StubIndex:
    """The duck-typed shape the dialogs accept — deliberately NOT
    `db.introspect.IndexInfo`: these dialogs must work on injected plain data
    alone, so the test proves the shape is the only requirement.

    `constraint_name` is `None` for a standalone index, exactly as `IndexInfo`
    supplies it, and non-None for the implicit index behind a PRIMARY KEY /
    UNIQUE / EXCLUDE constraint.
    """

    name: str
    columns: list = field(default_factory=list)
    is_unique: bool = False
    method: str = "btree"
    constraint_name: str | None = None
    schema: str = "public"

    @property
    def qualified_name(self) -> str:
        """`schema.name` — an index's identity, NOT `schema.table.name`."""
        return f"{self.schema}.{self.name}"


INDEXES = {
    "public.orders": [
        StubIndex("idx_orders_code", ["code"]),
        StubIndex("idx_orders_customer", ["customer_id"], method="hash"),
        # Constraint-backed: Postgres refuses DROP INDEX on these.
        StubIndex("orders_pkey", ["id"], is_unique=True, constraint_name="orders_pkey"),
        StubIndex(
            "orders_code_key",
            ["code"],
            is_unique=True,
            constraint_name="orders_code_key",
        ),
    ],
    "public.customers": [StubIndex("idx_customers_email", ["email"])],
}


def _ok(dialog):
    return dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)


def _create_index(qtbot, table="public.orders", column="code"):
    dialog = CreateIndexDialog(
        table=table, column=column, tables=TABLES, columns=COLUMNS
    )
    qtbot.addWidget(dialog)
    return dialog


def _drop_index(qtbot, table="public.orders", column="code", indexes=None):
    dialog = DropIndexDialog(
        table=table,
        column=column,
        tables=TABLES,
        columns=COLUMNS,
        indexes=INDEXES if indexes is None else indexes,
    )
    qtbot.addWidget(dialog)
    return dialog


def _table_comment(qtbot, table="public.orders", comment=""):
    dialog = SetCommentDialog(
        target=OP_TABLE_COMMENT,
        table=table,
        tables=TABLES,
        columns=COLUMNS,
        comment=comment,
    )
    qtbot.addWidget(dialog)
    return dialog


def _column_comment(qtbot, table="public.orders", column="code", comment=""):
    dialog = SetCommentDialog(
        target=OP_COLUMN_COMMENT,
        table=table,
        column=column,
        tables=TABLES,
        columns=COLUMNS,
        comment=comment,
    )
    qtbot.addWidget(dialog)
    return dialog


def _drop_table(qtbot, table="public.orders", column="code"):
    dialog = DropTableDialog(
        table=table, column=column, tables=TABLES, columns=COLUMNS
    )
    qtbot.addWidget(dialog)
    return dialog


def _create_table(qtbot, schema=""):
    dialog = CreateTableDialog(schema=schema, tables=TABLES)
    qtbot.addWidget(dialog)
    return dialog


#: Every dialog bound to an EXISTING table — the ones slice 1's context rules
#: apply to. `CreateTableDialog` is excluded on purpose: it has no table to be
#: summoned from (see its own section below).
_TABLE_BOUND = (_create_index, _drop_index, _table_comment, _column_comment, _drop_table)


# --- Shared slice-1 rules still hold ---------------------------------------
@pytest.mark.parametrize("factory", _TABLE_BOUND)
def test_the_click_context_is_the_default_but_stays_changeable(qtbot, factory):
    dialog = factory(qtbot)
    assert dialog.table() == "public.orders"
    assert dialog.context_table() == "public.orders"
    assert dialog._table_combo.isEnabled()
    dialog._table_combo.setCurrentText("public.customers")
    assert dialog.table() == "public.customers"


@pytest.mark.parametrize("factory", _TABLE_BOUND)
def test_no_dialog_is_ever_modal(qtbot, factory):
    # `.exec()` would hang a headless run; every dialog in this feature is
    # shown with `show()`.
    dialog = factory(qtbot)
    dialog.show()
    assert dialog.isVisible()
    assert not dialog.isModal()


@pytest.mark.parametrize("factory", _TABLE_BOUND)
def test_the_error_label_always_mirrors_the_validation_state(qtbot, factory):
    dialog = factory(qtbot)
    assert dialog._error_label.text() == (dialog.validation_error() or "")


# --- Create index -----------------------------------------------------------
def test_create_index_starts_invalid_until_it_is_named(qtbot):
    dialog = _create_index(qtbot)
    assert not dialog.is_valid()
    assert not _ok(dialog).isEnabled()
    assert dialog.skeleton() == ""
    assert "index name" in dialog.validation_error()


def test_create_index_renders_through_the_emitter(qtbot):
    dialog = _create_index(qtbot)
    dialog._name_edit.setText("idx_orders_code")
    dialog.column_picker().set_selection(["code"])
    assert dialog.is_valid()
    assert dialog.skeleton() == create_index_skeleton(
        name="idx_orders_code",
        table="public.orders",
        columns=["code"],
        unique=False,
        method="btree",
    )


def test_create_index_golden_text(qtbot):
    dialog = _create_index(qtbot)
    dialog._name_edit.setText("idx_orders_code")
    dialog.column_picker().set_selection(["code"])
    assert dialog.skeleton() == (
        'CREATE INDEX "idx_orders_code" ON "public"."orders" '
        'USING btree ("code");\n'
    )


def test_create_index_unique_toggle_changes_the_statement(qtbot):
    dialog = _create_index(qtbot)
    dialog._name_edit.setText("idx_orders_code")
    dialog.column_picker().set_selection(["code"])
    assert "UNIQUE" not in dialog.skeleton()
    dialog._unique_check.setChecked(True)
    assert dialog.unique()
    assert dialog.skeleton().startswith('CREATE UNIQUE INDEX "idx_orders_code"')


def test_create_index_offers_every_declared_method(qtbot):
    dialog = _create_index(qtbot)
    assert dialog.available_methods() == list(INDEX_METHODS)
    assert dialog.method() == "btree"


@pytest.mark.parametrize("method", INDEX_METHODS)
def test_create_index_method_dropdown_reaches_the_statement(qtbot, method):
    dialog = _create_index(qtbot)
    dialog._name_edit.setText("i")
    dialog._method_combo.setCurrentText(method)
    assert f"USING {method} (" in dialog.skeleton()


def test_create_index_plus_button_adds_a_column_in_order(qtbot):
    dialog = _create_index(qtbot)
    dialog._name_edit.setText("idx_multi")
    picker = dialog.column_picker()
    picker.set_selection(["tenant", "code"])
    assert dialog.columns() == ["tenant", "code"]
    assert '("tenant", "code")' in dialog.skeleton()


def test_create_index_columns_follow_the_table_dropdown(qtbot):
    dialog = _create_index(qtbot)
    assert dialog.column_picker().available_columns() == COLUMNS["public.orders"]
    dialog._table_combo.setCurrentText("public.customers")
    assert dialog.column_picker().available_columns() == COLUMNS["public.customers"]


def test_create_index_shows_the_emitters_own_refusal_for_a_dotted_name(qtbot):
    # `CREATE INDEX` puts the index in its table's schema; a dotted index name
    # is a syntax error, and the message the user reads is the emitter's.
    dialog = _create_index(qtbot)
    dialog._name_edit.setText("public.idx_orders_code")
    assert not dialog.is_valid()
    assert not _ok(dialog).isEnabled()
    assert "public.idx_orders_code" in dialog.validation_error()


def test_create_index_injects_no_database_access(qtbot):
    # The columns offered are exactly the injected ones, for a table name that
    # exists in no database anywhere.
    dialog = CreateIndexDialog(table="made.up", tables=["made.up"], columns={"made.up": ["a"]})
    qtbot.addWidget(dialog)
    assert dialog.column_picker().available_columns() == ["a"]


# --- Drop index -------------------------------------------------------------
def test_drop_index_lists_only_droppable_indexes(qtbot):
    dialog = _drop_index(qtbot)
    assert dialog.available_indexes() == ["idx_orders_code", "idx_orders_customer"]
    assert "orders_pkey" not in dialog.available_indexes()


def test_drop_index_says_what_it_hid_and_why(qtbot):
    # The stated rule from `introspect.IndexInfo`: silently omitting these
    # would make a "where did my unique index go?" mystery.
    dialog = _drop_index(qtbot)
    note = dialog.note()
    assert dialog.hidden_indexes() == ["orders_pkey", "orders_code_key"]
    assert "orders_pkey" in note
    assert "orders_code_key" in note
    assert "constraint" in note.lower()
    assert "Drop constraint" in note
    assert dialog._note_label.text() == note


def test_drop_index_note_is_not_an_error_and_never_gates_ok(qtbot):
    dialog = _drop_index(qtbot)
    assert dialog.note()
    assert dialog.is_valid()
    assert _ok(dialog).isEnabled()
    assert dialog._error_label.text() == ""


def test_drop_index_note_is_empty_when_nothing_was_hidden(qtbot):
    dialog = _drop_index(qtbot, indexes={"public.orders": [StubIndex("idx_only", ["code"])]})
    assert dialog.hidden_indexes() == []
    assert dialog.note() == ""
    assert dialog._note_label.text() == ""


def test_drop_index_note_is_singular_for_one_hidden_index(qtbot):
    dialog = _drop_index(
        qtbot,
        indexes={
            "public.orders": [
                StubIndex("idx_only", ["code"]),
                StubIndex("orders_pkey", ["id"], constraint_name="orders_pkey"),
            ]
        },
    )
    assert dialog.note().startswith("1 index is not listed")


def test_drop_index_is_valid_the_moment_it_opens(qtbot):
    # Picking the first existing index IS the entire input, like slice 2's
    # Drop constraint.
    dialog = _drop_index(qtbot)
    assert dialog.is_valid()
    assert dialog.skeleton()


def test_drop_index_uses_the_index_identity_not_the_table(qtbot):
    dialog = _drop_index(qtbot)
    assert dialog.index_identity() == "public.idx_orders_code"
    assert dialog.skeleton() == drop_index_skeleton(index="public.idx_orders_code")
    assert dialog.skeleton() == 'DROP INDEX "public"."idx_orders_code";\n'
    # Never `schema.table.index`, which Postgres reads as database.schema.object.
    assert "orders" not in dialog.skeleton().replace("idx_orders_code", "")


def test_drop_index_label_shows_uniqueness_method_and_columns(qtbot):
    dialog = _drop_index(
        qtbot,
        indexes={
            "public.orders": [StubIndex("idx_u", ["a", "b"], is_unique=True, method="gin")]
        },
    )
    assert dialog.index_labels() == ["idx_u — UNIQUE gin (a, b)"]


def test_drop_index_selection_data_is_the_identity_not_the_label(qtbot):
    dialog = _drop_index(qtbot)
    assert dialog.index_labels()[0] != dialog.index_identity()
    assert dialog.index_name() == "idx_orders_code"


def test_drop_index_follows_the_table_dropdown(qtbot):
    dialog = _drop_index(qtbot)
    dialog._table_combo.setCurrentText("public.customers")
    assert dialog.available_indexes() == ["idx_customers_email"]
    assert dialog.index_identity() == "public.idx_customers_email"


def test_drop_index_explains_a_table_with_no_droppable_index(qtbot):
    dialog = _drop_index(
        qtbot,
        indexes={
            "public.orders": [
                StubIndex("orders_pkey", ["id"], constraint_name="orders_pkey")
            ]
        },
    )
    assert not dialog.is_valid()
    assert not _ok(dialog).isEnabled()
    assert "no droppable indexes" in dialog.validation_error()
    # …and it still says WHY the one it knows about is missing.
    assert "orders_pkey" in dialog.note()


def test_drop_index_accepts_bare_names_and_borrows_the_tables_schema(qtbot):
    # A caller that injects plain strings still gets a valid DROP INDEX: an
    # index always lives in its table's schema.
    dialog = _drop_index(qtbot, indexes={"public.orders": ["idx_plain"]})
    assert dialog.index_identity() == "public.idx_plain"
    assert dialog.skeleton() == 'DROP INDEX "public"."idx_plain";\n'


def test_drop_index_bare_sequence_describes_only_the_context_table(qtbot):
    dialog = _drop_index(qtbot, indexes=[StubIndex("idx_ctx", ["code"])])
    assert dialog.available_indexes() == ["idx_ctx"]
    dialog._table_combo.setCurrentText("public.customers")
    assert dialog.available_indexes() == []


def test_drop_index_accepts_a_callable_source(qtbot):
    dialog = _drop_index(qtbot, indexes=lambda table: INDEXES.get(table, ()))
    assert dialog.available_indexes() == ["idx_orders_code", "idx_orders_customer"]


# --- Comments ---------------------------------------------------------------
def test_set_table_comment_golden_text(qtbot):
    dialog = _table_comment(qtbot)
    dialog._comment_edit.setText("Customer orders")
    assert dialog.skeleton() == (
        'COMMENT ON TABLE "public"."orders" IS \'Customer orders\';\n'
    )
    assert dialog.skeleton() == set_table_comment_skeleton(
        table="public.orders", comment="Customer orders"
    )


def test_set_column_comment_golden_text(qtbot):
    dialog = _column_comment(qtbot)
    dialog._comment_edit.setText("The order code")
    assert dialog.skeleton() == set_column_comment_skeleton(
        table="public.orders", column="code", comment="The order code"
    )
    assert 'COMMENT ON COLUMN "public"."orders"."code"' in dialog.skeleton()


def test_the_table_flavour_has_no_column_dropdown(qtbot):
    dialog = _table_comment(qtbot)
    assert dialog.column() == ""
    assert "COLUMN" not in dialog.skeleton()


def test_the_column_flavour_defaults_to_the_clicked_column(qtbot):
    dialog = _column_comment(qtbot, column="customer_id")
    assert dialog.column() == "customer_id"
    assert '"customer_id"' in dialog.skeleton()


def test_the_comment_target_is_fixed_by_the_menu_not_a_field(qtbot):
    assert _table_comment(qtbot).target() == OP_TABLE_COMMENT
    assert _column_comment(qtbot).target() == OP_COLUMN_COMMENT


def test_an_unknown_comment_target_is_refused(qtbot):
    with pytest.raises(ValueError, match="unknown comment target"):
        SetCommentDialog(target="the_database", table="public.orders")


@pytest.mark.parametrize("factory", [_table_comment, _column_comment])
def test_a_blank_comment_is_valid_and_removes_the_comment(qtbot, factory):
    # "Take that comment off" is a legitimate thing to want, so a blank box is
    # not an error — it emits `IS NULL`.
    dialog = factory(qtbot)
    assert dialog.comment() == ""
    assert dialog.removes_the_comment()
    assert dialog.is_valid()
    assert _ok(dialog).isEnabled()
    assert dialog.skeleton().endswith("IS NULL;\n")


@pytest.mark.parametrize("factory", [_table_comment, _column_comment])
def test_the_existing_comment_may_be_injected_for_editing(qtbot, factory):
    # A comment is a VALUE (escaped, not allowlisted), so unlike a USING clause
    # it may be pre-filled — editing beats retyping from memory.
    dialog = factory(qtbot, comment="the old text")
    assert dialog.comment() == "the old text"
    assert not dialog.removes_the_comment()
    assert "IS 'the old text'" in dialog.skeleton()


def test_a_comment_with_an_apostrophe_is_escaped_not_refused(qtbot):
    dialog = _table_comment(qtbot)
    dialog._comment_edit.setText("the user's orders")
    assert dialog.is_valid()
    assert "IS 'the user''s orders';\n" in dialog.skeleton()


def test_a_comment_containing_sql_stays_inside_the_literal(qtbot):
    dialog = _table_comment(qtbot)
    dialog._comment_edit.setText("'; DROP TABLE users; --")
    assert dialog.is_valid()
    assert dialog.skeleton().count(";\n") == 1


# --- Create table -----------------------------------------------------------
def test_create_table_has_no_pre_bound_table(qtbot):
    # The one dialog in this feature that is table-independent: it hides the
    # inherited "From:" line and table dropdown and names a NEW table instead.
    dialog = _create_table(qtbot)
    assert dialog.table() == ""
    # Row 0 is the read-only "From:" line, and the combo is the "Table:" row.
    assert not dialog._form.isRowVisible(0)
    assert not dialog._form.isRowVisible(dialog._table_combo)
    assert not dialog.is_valid()
    assert dialog.validation_error() == "Name the table to create."


def test_create_table_seeds_the_name_with_the_clicked_schema(qtbot):
    dialog = _create_table(qtbot, schema="public")
    assert dialog.table() == "public."
    # …but only as a prefix: the schema alone is not a table name.
    assert not dialog.is_valid()


def test_create_table_renders_through_the_emitter(qtbot):
    dialog = _create_table(qtbot)
    dialog._name_edit.setText("public.invoice")
    rows = dialog.column_rows()
    rows.set_row(0, name="id", datatype="bigint", nullable=False, primary_key=True)
    rows.set_row(1, name="code", datatype="text")
    assert dialog.is_valid()
    assert dialog.skeleton() == create_table_skeleton(
        table="public.invoice",
        columns=[
            ColumnSpec("id", "bigint", nullable=False),
            ColumnSpec("code", "text"),
        ],
        primary_key=["id"],
    )


def test_create_table_golden_text(qtbot):
    dialog = _create_table(qtbot)
    dialog._name_edit.setText("public.invoice")
    rows = dialog.column_rows()
    rows.set_row(0, name="id", datatype="bigint", nullable=False, primary_key=True)
    rows.set_row(1, name="created_at", datatype="timestamptz", default="now()")
    assert dialog.skeleton() == (
        'CREATE TABLE "public"."invoice" (\n'
        '    "id" bigint NOT NULL,\n'
        '    "created_at" timestamptz DEFAULT now(),\n'
        '    PRIMARY KEY ("id")\n'
        ");\n"
    )


def test_create_table_starts_with_one_empty_column_row(qtbot):
    dialog = _create_table(qtbot)
    rows = dialog.column_rows()
    assert rows.row_count() == 1
    assert rows.specs() == [ColumnSpec("", "text", True, None)]


def test_create_table_plus_and_minus_change_the_row_count(qtbot):
    dialog = _create_table(qtbot)
    rows = dialog.column_rows()
    rows.add_row()
    rows.add_row()
    assert rows.row_count() == 3
    rows.remove_row(1)
    assert rows.row_count() == 2


def test_create_table_last_column_row_can_never_be_removed(qtbot):
    # A table with zero columns is not a state any CREATE TABLE can be built
    # from, so it is not offered as a state.
    dialog = _create_table(qtbot)
    rows = dialog.column_rows()
    rows.remove_row(0)
    assert rows.row_count() == 1


def test_create_table_row_order_is_the_column_order(qtbot):
    dialog = _create_table(qtbot)
    dialog._name_edit.setText("t")
    rows = dialog.column_rows()
    rows.set_row(0, name="b", datatype="text")
    rows.set_row(1, name="a", datatype="text")
    text = dialog.skeleton()
    assert text.index('"b"') < text.index('"a"')


def test_create_table_primary_key_checkboxes_build_the_key_in_row_order(qtbot):
    dialog = _create_table(qtbot)
    dialog._name_edit.setText("t")
    rows = dialog.column_rows()
    rows.set_row(0, name="tenant", datatype="text", primary_key=True)
    rows.set_row(1, name="id", datatype="bigint", primary_key=True)
    assert dialog.primary_key() == ["tenant", "id"]
    assert 'PRIMARY KEY ("tenant", "id")' in dialog.skeleton()


def test_create_table_with_no_primary_key_checked_emits_none(qtbot):
    dialog = _create_table(qtbot)
    dialog._name_edit.setText("t")
    dialog.column_rows().set_row(0, name="a", datatype="text")
    assert dialog.primary_key() == []
    assert "PRIMARY KEY" not in dialog.skeleton()


def test_create_table_blank_default_means_no_default_clause(qtbot):
    dialog = _create_table(qtbot)
    dialog._name_edit.setText("t")
    dialog.column_rows().set_row(0, name="a", datatype="text", default="   ")
    assert dialog.specs()[0].default is None
    assert "DEFAULT" not in dialog.skeleton()


def test_create_table_shows_the_emitters_own_refusal(qtbot):
    dialog = _create_table(qtbot)
    dialog._name_edit.setText("t")
    dialog.column_rows().set_row(0, name="a", datatype="text", default="coalesce(x, 0")
    assert not dialog.is_valid()
    assert "unbalanced parentheses" in dialog.validation_error()
    assert dialog._error_label.text() == dialog.validation_error()


def test_create_table_refuses_a_hostile_table_name(qtbot):
    dialog = _create_table(qtbot)
    dialog._name_edit.setText('t"; DROP TABLE users; --')
    dialog.column_rows().set_row(0, name="a", datatype="text")
    assert not dialog.is_valid()
    assert not _ok(dialog).isEnabled()


def test_create_table_is_not_modal(qtbot):
    dialog = _create_table(qtbot)
    dialog.show()
    assert dialog.isVisible()
    assert not dialog.isModal()


# --- Drop table -------------------------------------------------------------
def test_drop_table_golden_text(qtbot):
    dialog = _drop_table(qtbot)
    assert dialog.skeleton() == 'DROP TABLE "public"."orders";\n'
    assert dialog.skeleton() == drop_table_skeleton(table="public.orders")


def test_drop_table_is_valid_the_moment_it_opens(qtbot):
    # The table IS the entire input, and the FQ-025 ruling is that the
    # generated tab is the safeguard.
    dialog = _drop_table(qtbot)
    assert dialog.is_valid()
    assert _ok(dialog).isEnabled()


def test_drop_table_has_no_typed_name_confirmation(qtbot):
    # Explicitly guarded: the entry rejected a typed-name gate, so a later
    # change that adds one has to delete this test to do it.
    dialog = _drop_table(qtbot)
    from PySide6.QtWidgets import QLineEdit

    assert dialog.findChildren(QLineEdit) == []
    assert dialog._error_label.text() == ""


def test_drop_table_follows_the_table_dropdown(qtbot):
    dialog = _drop_table(qtbot)
    dialog._table_combo.setCurrentText("public.customers")
    assert dialog.skeleton() == 'DROP TABLE "public"."customers";\n'


# --- No dialog here talks to a database ------------------------------------
def test_no_dialog_module_imports_the_schema_model():
    # The injected-data rule, enforced structurally rather than by convention:
    # the module may *mention* `IndexInfo` in prose (it documents the duck type
    # it accepts), but it must never import it or anything else that knows what
    # a database is.
    import pgtp_editor.ui.table_dialogs as module

    with open(module.__file__, encoding="utf-8") as handle:
        imports = [
            line
            for line in handle
            if line.startswith(("import ", "from ")) and "#" not in line
        ]
    assert imports, "the import block moved -- this guard needs updating"
    for line in imports:
        assert "introspect" not in line
        assert "psycopg" not in line
        assert "sandbox" not in line
