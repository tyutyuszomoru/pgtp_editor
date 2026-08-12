# tests/ui/test_constraint_dialogs.py
"""Tests for the FQ-025 slice 2 constraint / foreign-key dialogs.

Same posture as slice 1's `test_alter_column_dialogs.py`: every dialog is
driven through its methods, none is ever `.exec()`-ed (modal-hang guardrail),
and none opens a connection — tables, columns and the existing constraints are
all injected as plain literals. Generated SQL is asserted against
`db/ddl_skeleton.py` where the point is "the dialog feeds the emitter", and
against a golden string where the point is "this is what the user sees pasted
into the tab".
"""
from dataclasses import dataclass, field

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from pgtp_editor.db.ddl_skeleton import (
    CONSTRAINT_TYPES,
    add_constraint_skeleton,
    drop_constraint_skeleton,
)
from pgtp_editor.ui.status_colours import STATUS_ERROR
from pgtp_editor.ui.constraint_dialogs import (
    AddConstraintDialog,
    AddForeignKeyDialog,
    DropConstraintDialog,
    RenameConstraintDialog,
)

TABLES = ["public.customers", "public.orders"]
COLUMNS = {
    "public.orders": ["id", "tenant", "code", "customer_id"],
    "public.customers": ["id", "tenant", "email"],
}


@dataclass(frozen=True)
class StubConstraint:
    """The duck-typed shape the dialogs accept — deliberately NOT
    `db.introspect.ConstraintInfo`: these dialogs must work on injected plain
    data alone, so the test proves the shape is the only requirement.

    `kind` is lowercase prose, exactly as `ConstraintInfo` supplies it; the
    upper-casing is the dialog's job.
    """

    name: str
    kind: str
    columns: list = field(default_factory=list)
    definition: str = ""


CONSTRAINTS = {
    "public.orders": [
        StubConstraint("orders_pkey", "primary key", ["id"]),
        StubConstraint("orders_customer_fk", "foreign key", ["customer_id"]),
        StubConstraint("orders_code_key", "unique", ["code"]),
        StubConstraint(
            "orders_sane", "check", [], definition="CHECK ((true))"
        ),
    ],
    "public.customers": [StubConstraint("customers_pkey", "primary key", ["id"])],
}


def _ok(dialog):
    return dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)


def _add_constraint(qtbot, table="public.orders", column="code"):
    dialog = AddConstraintDialog(
        table=table, column=column, tables=TABLES, columns=COLUMNS
    )
    qtbot.addWidget(dialog)
    return dialog


def _add_fk(qtbot, table="public.orders", column="customer_id", ref_table=""):
    dialog = AddForeignKeyDialog(
        table=table,
        column=column,
        tables=TABLES,
        columns=COLUMNS,
        ref_table=ref_table,
    )
    qtbot.addWidget(dialog)
    return dialog


def _drop(qtbot, table="public.orders", column="code", constraints=None):
    dialog = DropConstraintDialog(
        table=table,
        column=column,
        tables=TABLES,
        columns=COLUMNS,
        constraints=CONSTRAINTS if constraints is None else constraints,
    )
    qtbot.addWidget(dialog)
    return dialog


def _rename(qtbot, table="public.orders", column="code"):
    dialog = RenameConstraintDialog(
        table=table,
        column=column,
        tables=TABLES,
        columns=COLUMNS,
        constraints=CONSTRAINTS,
    )
    qtbot.addWidget(dialog)
    return dialog


_FACTORIES = (_add_constraint, _add_fk, _drop, _rename)

#: Every dialog except Drop needs something typed before it can render: a
#: constraint name, or a new name. Drop is valid the moment it opens, because
#: picking the first existing constraint IS a complete answer -- so it is
#: excluded from the "OK starts disabled" rules and gets its own test.
_INCOMPLETE_ON_OPEN = (_add_constraint, _add_fk, _rename)


# --- Shared slice-1 rules still hold ---------------------------------------
@pytest.mark.parametrize("factory", _FACTORIES)
def test_the_click_context_is_the_default_but_stays_changeable(qtbot, factory):
    dialog = factory(qtbot)
    assert dialog.table() == "public.orders"
    assert dialog.context_table() == "public.orders"
    assert dialog._table_combo.isEnabled()
    dialog._table_combo.setCurrentText("public.customers")
    assert dialog.table() == "public.customers"


@pytest.mark.parametrize("factory", _FACTORIES)
def test_the_click_context_is_also_stated_read_only(qtbot, factory):
    dialog = factory(qtbot)
    assert dialog.context_column() in ("code", "customer_id")


@pytest.mark.parametrize("factory", _INCOMPLETE_ON_OPEN)
def test_ok_starts_disabled_until_the_form_renders(qtbot, factory):
    dialog = factory(qtbot)
    assert not dialog.is_valid()
    assert not _ok(dialog).isEnabled()
    assert dialog.skeleton() == ""


def test_drop_is_the_one_dialog_that_is_valid_the_moment_it_opens(qtbot):
    # Nothing is left for the user to supply: the picker already names an
    # existing constraint, which is the entire input.
    dialog = _drop(qtbot)
    assert dialog.is_valid()
    assert _ok(dialog).isEnabled()
    assert dialog.skeleton()


@pytest.mark.parametrize("factory", _INCOMPLETE_ON_OPEN)
def test_the_error_label_shows_the_emitters_own_message(qtbot, factory):
    dialog = factory(qtbot)
    assert dialog._error_label.text() == dialog.validation_error()
    assert dialog._error_label.text()


# --- Add constraint ---------------------------------------------------------
def test_add_constraint_offers_every_type_and_not_foreign_key(qtbot):
    dialog = _add_constraint(qtbot)
    assert dialog.available_constraint_types() == list(CONSTRAINT_TYPES)
    assert "FOREIGN KEY" not in dialog.available_constraint_types()


def test_add_constraint_renders_a_single_column_key(qtbot):
    dialog = _add_constraint(qtbot)
    dialog._name_edit.setText("orders_code_key")
    dialog._type_combo.setCurrentText("UNIQUE")
    dialog.column_picker().set_selection(["code"])
    assert dialog.is_valid()
    assert dialog.skeleton() == add_constraint_skeleton(
        table="public.orders",
        name="orders_code_key",
        constraint_type="UNIQUE",
        columns=["code"],
    )


def test_add_constraint_plus_button_adds_a_column_in_order(qtbot):
    dialog = _add_constraint(qtbot)
    dialog._name_edit.setText("orders_pkey")
    dialog._type_combo.setCurrentText("PRIMARY KEY")
    picker = dialog.column_picker()
    assert picker.row_count() == 1

    picker.add_row()
    assert picker.row_count() == 2
    picker._rows[0][1].setCurrentText("tenant")
    picker._rows[1][1].setCurrentText("id")

    assert dialog.columns() == ["tenant", "id"]
    assert 'PRIMARY KEY ("tenant", "id")' in dialog.skeleton()


def test_add_constraint_minus_button_removes_the_added_row(qtbot):
    dialog = _add_constraint(qtbot)
    picker = dialog.column_picker()
    picker.add_row()
    picker.add_row()
    assert picker.row_count() == 3
    picker.remove_row(2)
    assert picker.row_count() == 2


def test_the_last_column_row_can_never_be_removed(qtbot):
    # Zero columns is not a state any constraint can be built from, so the
    # picker never offers it: the sole row's "-" is disabled AND a programmatic
    # removal is a no-op.
    dialog = _add_constraint(qtbot)
    picker = dialog.column_picker()
    assert picker.row_count() == 1
    assert not picker._rows[0][2].isEnabled()

    picker.remove_row(0)
    assert picker.row_count() == 1
    assert picker.columns()  # still naming a real column


def test_the_minus_buttons_re_enable_once_a_second_row_exists(qtbot):
    dialog = _add_constraint(qtbot)
    picker = dialog.column_picker()
    picker.add_row()
    assert all(row[2].isEnabled() for row in picker._rows)
    picker.remove_row(1)
    assert not picker._rows[0][2].isEnabled()


def test_changing_the_table_repopulates_the_picker_and_collapses_the_rows(qtbot):
    # Row two named a column of the PREVIOUS table; carrying it over would
    # build a key out of a name coincidence.
    dialog = _add_constraint(qtbot)
    picker = dialog.column_picker()
    picker.add_row()
    assert picker.row_count() == 2

    dialog._table_combo.setCurrentText("public.customers")
    assert picker.available_columns() == COLUMNS["public.customers"]
    assert picker.row_count() == 1


def test_add_constraint_check_uses_the_expression_not_the_column_picker(qtbot):
    dialog = _add_constraint(qtbot)
    dialog._name_edit.setText("orders_qty")
    dialog._type_combo.setCurrentText("CHECK")
    dialog._expression_edit.setText("qty > 0")
    assert dialog.is_valid()
    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" ADD CONSTRAINT "orders_qty" '
        "CHECK (qty > 0);\n"
    )


def test_add_constraint_hides_the_picker_for_expression_shaped_types(qtbot):
    dialog = _add_constraint(qtbot)
    dialog.show()
    dialog._type_combo.setCurrentText("PRIMARY KEY")
    assert dialog.column_picker().isVisible()
    assert not dialog._expression_edit.isVisible()

    dialog._type_combo.setCurrentText("CHECK")
    assert not dialog.column_picker().isVisible()
    assert dialog._expression_edit.isVisible()
    # The method dropdown belongs to EXCLUDE alone.
    assert not dialog._method_combo.isVisible()

    dialog._type_combo.setCurrentText("EXCLUDE")
    assert dialog._method_combo.isVisible()


def test_add_constraint_exclude_renders_the_method(qtbot):
    dialog = _add_constraint(qtbot)
    dialog._name_edit.setText("no_overlap")
    dialog._type_combo.setCurrentText("EXCLUDE")
    dialog._expression_edit.setText("code WITH =")
    assert "EXCLUDE USING gist (code WITH =)" in dialog.skeleton()


def test_add_constraint_reports_a_broken_check_expression_inline(qtbot):
    dialog = _add_constraint(qtbot)
    dialog._name_edit.setText("ck")
    dialog._type_combo.setCurrentText("CHECK")
    dialog._expression_edit.setText("qty > (0")
    assert not dialog.is_valid()
    assert "unbalanced parentheses" in dialog._error_label.text()
    assert not _ok(dialog).isEnabled()


def test_add_constraint_requires_a_name(qtbot):
    dialog = _add_constraint(qtbot)
    dialog._type_combo.setCurrentText("UNIQUE")
    dialog.column_picker().set_selection(["code"])
    assert "constraint name must not be empty" in dialog._error_label.text()
    dialog._name_edit.setText("orders_code_key")
    assert dialog.is_valid()


def test_add_constraint_refuses_a_hostile_name_with_the_emitters_words(qtbot):
    dialog = _add_constraint(qtbot)
    dialog._name_edit.setText('bad"name')
    assert not dialog.is_valid()
    assert dialog._error_label.text()


# --- Add foreign key --------------------------------------------------------
def test_add_foreign_key_golden_text(qtbot):
    dialog = _add_fk(qtbot, ref_table="public.customers")
    dialog._name_edit.setText("orders_customer_fk")
    dialog.column_picker().set_selection(["customer_id"])
    dialog.ref_column_picker().set_selection(["id"])
    assert dialog.is_valid()
    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" ADD CONSTRAINT "orders_customer_fk" '
        'FOREIGN KEY ("customer_id") REFERENCES "public"."customers" ("id");\n'
    )


def test_choosing_a_target_table_repopulates_the_target_column_list(qtbot):
    # The entry's headline requirement for this dialog.
    dialog = _add_fk(qtbot, ref_table="public.orders")
    assert dialog.available_ref_columns() == COLUMNS["public.orders"]

    dialog._ref_table_combo.setCurrentText("public.customers")
    assert dialog.ref_table() == "public.customers"
    assert dialog.available_ref_columns() == COLUMNS["public.customers"]


def test_the_target_table_is_independent_of_the_local_table(qtbot):
    dialog = _add_fk(qtbot, ref_table="public.customers")
    dialog._table_combo.setCurrentText("public.customers")
    # Changing the LOCAL table must not drag the target with it.
    assert dialog.ref_table() == "public.customers"
    dialog._ref_table_combo.setCurrentText("public.orders")
    assert dialog.table() == "public.customers"
    assert dialog.ref_table() == "public.orders"


def test_add_foreign_key_supports_multi_column_keys_on_both_sides(qtbot):
    dialog = _add_fk(qtbot, ref_table="public.customers")
    dialog._name_edit.setText("fk")
    dialog.column_picker().set_selection(["tenant", "customer_id"])
    dialog.ref_column_picker().set_selection(["tenant", "id"])
    assert dialog.columns() == ["tenant", "customer_id"]
    assert dialog.ref_columns() == ["tenant", "id"]
    assert (
        'FOREIGN KEY ("tenant", "customer_id") '
        'REFERENCES "public"."customers" ("tenant", "id")'
    ) in dialog.skeleton()


def test_add_foreign_key_mismatched_arity_is_explained_not_emitted(qtbot):
    dialog = _add_fk(qtbot, ref_table="public.customers")
    dialog._name_edit.setText("fk")
    dialog.column_picker().set_selection(["tenant", "customer_id"])
    dialog.ref_column_picker().set_selection(["id"])
    assert not dialog.is_valid()
    assert "exactly as many columns" in dialog._error_label.text()


def test_add_foreign_key_referential_actions_default_to_no_clause(qtbot):
    dialog = _add_fk(qtbot, ref_table="public.customers")
    dialog._name_edit.setText("fk")
    dialog.column_picker().set_selection(["customer_id"])
    dialog.ref_column_picker().set_selection(["id"])
    assert dialog.on_delete() is None
    assert dialog.on_update() is None
    assert "ON DELETE" not in dialog.skeleton()

    dialog._on_delete_combo.setCurrentText("CASCADE")
    assert dialog.on_delete() == "CASCADE"
    assert dialog.skeleton().endswith("ON DELETE CASCADE;\n")


def test_add_foreign_key_and_add_constraint_share_the_name_and_picker(qtbot):
    # The judgment call, pinned: the two ADDs share a base for exactly the
    # half they have in common.
    from pgtp_editor.ui.constraint_dialogs import _AddConstraintDialogBase

    assert issubclass(AddConstraintDialog, _AddConstraintDialogBase)
    assert issubclass(AddForeignKeyDialog, _AddConstraintDialogBase)
    for dialog in (_add_constraint(qtbot), _add_fk(qtbot)):
        assert dialog.constraint_name() == ""
        assert dialog.column_picker().row_count() == 1


# --- Drop constraint --------------------------------------------------------
def test_drop_constraint_lists_every_constraint_with_its_type(qtbot):
    # Without the type there is no way to tell a FK from a CHECK before
    # dropping it -- the whole reason the two menu items were unified into one.
    dialog = _drop(qtbot)
    labels = dialog.constraint_labels()
    assert labels == [
        "orders_pkey — PRIMARY KEY (id)",
        "orders_customer_fk — FOREIGN KEY (customer_id)",
        "orders_code_key — UNIQUE (code)",
        "orders_sane — CHECK — CHECK ((true))",
    ]


def test_a_column_less_check_shows_its_definition_not_empty_parentheses(qtbot):
    dialog = _drop(qtbot)
    dialog._constraint_combo.setCurrentIndex(3)
    assert dialog.constraint_name() == "orders_sane"
    assert "()" not in dialog.constraint_labels()[3]
    assert "CHECK ((true))" in dialog.constraint_labels()[3]


def test_drop_constraint_emits_the_bare_name_not_the_typed_label(qtbot):
    dialog = _drop(qtbot)
    dialog._constraint_combo.setCurrentIndex(1)
    assert dialog.constraint_name() == "orders_customer_fk"
    assert dialog.skeleton() == drop_constraint_skeleton(
        table="public.orders", name="orders_customer_fk"
    )


@pytest.mark.parametrize("index", range(4))
def test_drop_constraint_is_type_agnostic_in_the_dialog_too(qtbot, index):
    dialog = _drop(qtbot)
    dialog._constraint_combo.setCurrentIndex(index)
    name = dialog.constraint_name()
    assert dialog.skeleton() == (
        f'ALTER TABLE "public"."orders" DROP CONSTRAINT "{name}";\n'
    )


def test_drop_constraint_states_the_consequence_but_never_blocks(qtbot):
    # The judgment call: warn, do not refuse. Postgres gives the authoritative
    # answer when the generated tab is actually run.
    dialog = _drop(qtbot)
    dialog._constraint_combo.setCurrentIndex(0)  # the primary key
    assert "PRIMARY KEY" in dialog.note()
    assert dialog.is_valid()
    assert _ok(dialog).isEnabled()
    assert dialog._error_label.text() == ""


def test_the_note_is_not_the_error_label(qtbot):
    """A note explains; it must not shout. The note label carries no attention
    colour at all, while the error label beside it does.

    **Rewritten by BUG-260812063745, which found this assertion about to go
    silently vacuous.** It read `assert "color: red" not in
    ...styleSheet()` — pinned to the literal CSS name that bugfix deleted from
    the whole package, so from that commit onward it would have passed no
    matter what the note label was painted. An absence assertion with no
    presence anchor beside it proves nothing; the `_error_label` line below is
    that anchor, and it fails if the error kind ever stops being applied.
    """
    dialog = _drop(qtbot)
    dialog._constraint_combo.setCurrentIndex(0)
    assert dialog._note_label.text() == dialog.note()
    # The anchor: the error label IS in the error kind on this same dialog...
    assert dialog._error_label.status_kind() == STATUS_ERROR
    # ...and the note label carries no status colour whatsoever.
    assert not (dialog._note_label.styleSheet() or "")


def test_an_index_backed_constraint_says_so(qtbot):
    dialog = _drop(qtbot)
    dialog._constraint_combo.setCurrentIndex(2)  # UNIQUE
    assert "index" in dialog.note()
    assert dialog.is_valid()


@pytest.mark.parametrize("index", [1, 3])
def test_constraints_owning_no_index_get_no_note(qtbot, index):
    dialog = _drop(qtbot)
    dialog._constraint_combo.setCurrentIndex(index)  # FK, then CHECK
    assert dialog.note() == ""


def test_the_constraint_list_follows_the_table_dropdown(qtbot):
    dialog = _drop(qtbot)
    dialog._table_combo.setCurrentText("public.customers")
    assert dialog.available_constraints() == ["customers_pkey"]


def test_a_table_with_no_constraints_explains_itself(qtbot):
    dialog = _drop(qtbot, constraints={})
    assert dialog.available_constraints() == []
    assert not dialog.is_valid()
    assert "no named constraints" in dialog._error_label.text()


def test_bare_constraint_names_are_accepted_as_injected_data(qtbot):
    # The dialogs duck-type: a caller with nothing but names still works, and
    # the label simply carries no type to show.
    dialog = _drop(qtbot, constraints={"public.orders": ["orders_pkey"]})
    assert dialog.constraint_labels() == ["orders_pkey"]
    assert dialog.constraint_name() == "orders_pkey"


def test_a_callable_constraint_source_is_accepted(qtbot):
    dialog = _drop(qtbot, constraints=lambda table: CONSTRAINTS.get(table, []))
    assert dialog.available_constraints()[0] == "orders_pkey"


# --- Rename constraint ------------------------------------------------------
def test_rename_constraint_golden_text(qtbot):
    dialog = _rename(qtbot)
    dialog._constraint_combo.setCurrentIndex(2)
    dialog._new_name_edit.setText("orders_code_unique")
    assert dialog.is_valid()
    assert dialog.skeleton() == (
        'ALTER TABLE "public"."orders" RENAME CONSTRAINT "orders_code_key" '
        'TO "orders_code_unique";\n'
    )


def test_rename_constraint_also_shows_the_type_in_its_picker(qtbot):
    assert _rename(qtbot).constraint_labels()[0] == "orders_pkey — PRIMARY KEY (id)"


def test_rename_to_the_same_name_is_refused_with_the_emitters_message(qtbot):
    dialog = _rename(qtbot)
    dialog._new_name_edit.setText("orders_pkey")
    assert not dialog.is_valid()
    assert "same as the current one" in dialog._error_label.text()


def test_rename_requires_a_new_name(qtbot):
    dialog = _rename(qtbot)
    assert "new constraint name must not be empty" in dialog._error_label.text()


# --- Structural guarantees --------------------------------------------------
@pytest.mark.parametrize("factory", _FACTORIES)
def test_no_dialog_is_ever_modal(qtbot, factory):
    dialog = factory(qtbot)
    dialog.show()
    assert not dialog.isModal()


def test_no_dialog_module_imports_the_schema_model():
    # The injected-data rule, enforced structurally: these dialogs learn about
    # tables, columns and constraints only from what the caller hands them.
    import pgtp_editor.ui.constraint_dialogs as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "from pgtp_editor.db.introspect" not in source
    assert "import introspect" not in source


def test_the_expression_field_cannot_be_seeded(qtbot):
    # Free SQL is user-typed only: no constructor accepts an initial CHECK
    # body, and the widget is built by slice 1's `_user_typed_line_edit`.
    with pytest.raises(TypeError):
        AddConstraintDialog(
            table="public.orders", tables=TABLES, columns=COLUMNS,
            expression="qty > 0",
        )
    dialog = _add_constraint(qtbot)
    assert dialog._expression_edit.text() == ""
    assert dialog._expression_edit.completer() is None


@pytest.mark.parametrize("factory", _INCOMPLETE_ON_OPEN)
def test_a_programmatic_ok_click_cannot_smuggle_invalid_ddl_through(qtbot, factory):
    dialog = factory(qtbot)
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog._on_accept_clicked()
    assert accepted == []
