# tests/ui/test_schema_compare_panel.py
"""Tests for §18.3's schema diff/migration viewer (headless, canned data).

Never a live DB and never a modal: schemas are built by hand exactly as
`tests/db/test_schema_diff.py` builds them, and saving goes through the
panel's injected callback.
"""
from PySide6.QtCore import Qt

from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
)
from pgtp_editor.db.schema_diff import SchemaDifference, SchemaDiffResult
from pgtp_editor.ui.schema_compare_panel import DIFFERENCE_ROLE, SchemaComparePanel


def _routine(name, source="BEGIN END", language="plpgsql"):
    return RoutineInfo(
        schema="pr",
        name=name,
        arg_types=[],
        return_type="void",
        language=language,
        source=source,
    )


def _trigger(name, definition="CREATE TRIGGER x"):
    return TriggerInfo(
        schema="pr",
        table="t",
        name=name,
        timing="before",
        events=["insert"],
        function_name="pr.f",
        definition=definition,
    )


def _table(name="pr.t"):
    return TableInfo(
        name=name,
        kind="table",
        columns=[ColumnInfo("id", "integer", True, False, False, None)],
    )


def _schema(routines=(), triggers=(), tables=()):
    return DatabaseSchema(
        tables={t.name: t for t in tables},
        routines={f"{r.schema}.{r.name}#{i}": r for i, r in enumerate(routines)},
        triggers={f"{t.schema}.{t.table}.{t.name}": t for t in triggers},
    )


def _panel(qtbot, **kwargs):
    panel = SchemaComparePanel(**kwargs)
    qtbot.addWidget(panel)
    return panel


def _items(panel):
    out = []
    for i in range(panel.tree.topLevelItemCount()):
        group = panel.tree.topLevelItem(i)
        out.extend(group.child(j) for j in range(group.childCount()))
    return out


def _routine_and_trigger_result():
    return SchemaDiffResult(
        [
            SchemaDifference("added", "routine", "pr.new()", None, "CREATE NEW"),
            SchemaDifference(
                "changed", "routine", "pr.old()", "CREATE OLD v1", "CREATE OLD v2"
            ),
            SchemaDifference("removed", "trigger", "pr.t.gone", "CREATE TRIGGER g", None),
        ]
    )


# --- rendering --------------------------------------------------------------


def test_differences_render_grouped_with_kind_labels(qtbot):
    panel = _panel(qtbot)
    panel.show_result(_routine_and_trigger_result())

    groups = [
        panel.tree.topLevelItem(i).text(0)
        for i in range(panel.tree.topLevelItemCount())
    ]
    assert groups == ["Routines", "Triggers"]

    rows = [(i.text(0), i.text(1), i.text(2)) for i in _items(panel)]
    assert rows == [
        ("pr.new()", "added", "routine"),
        ("pr.old()", "changed", "routine"),
        ("pr.t.gone", "removed", "trigger"),
    ]


def test_entries_start_unchecked(qtbot):
    panel = _panel(qtbot)
    panel.show_result(_routine_and_trigger_result())
    assert all(
        item.checkState(0) == Qt.CheckState.Unchecked for item in _items(panel)
    )
    assert panel.checked_differences() == []


def test_group_rows_are_not_checkable(qtbot):
    panel = _panel(qtbot)
    panel.show_result(_routine_and_trigger_result())
    group = panel.tree.topLevelItem(0)
    assert not group.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert group.data(0, DIFFERENCE_ROLE) is None


def test_compare_runs_the_engine_and_finds_the_changed_routine(qtbot):
    panel = _panel(qtbot)
    source = _schema(routines=[_routine("f", source="V2")], tables=[_table()])
    target = _schema(routines=[_routine("f", source="V1")], tables=[_table()])
    panel.compare(source, target, source_label="sandbox", target_label="prod")

    assert [(d.kind, d.identity) for d in panel.differences] == [("changed", "pr.f()")]
    assert "sandbox" in panel.status_label.text()
    assert "prod" in panel.status_label.text()


# --- detail pane ------------------------------------------------------------


def test_detail_pane_shows_selected_entry_definitions(qtbot):
    panel = _panel(qtbot)
    panel.show_result(_routine_and_trigger_result())

    panel.select_difference(1)  # the changed routine
    assert panel.old_def_text.toPlainText() == "CREATE OLD v1"
    assert panel.new_def_text.toPlainText() == "CREATE OLD v2"
    assert "pr.old()" in panel.old_def_label.text()

    panel.select_difference(0)  # added: absent from the target
    assert "absent from the target" in panel.old_def_text.toPlainText()
    assert panel.new_def_text.toPlainText() == "CREATE NEW"

    panel.select_difference(2)  # removed: absent from the source
    assert panel.old_def_text.toPlainText() == "CREATE TRIGGER g"
    assert "absent from the source" in panel.new_def_text.toPlainText()


def test_detail_pane_starts_on_the_placeholder(qtbot):
    panel = _panel(qtbot)
    panel.show_result(_routine_and_trigger_result())
    assert panel.detail_stack.currentWidget() is panel.placeholder_label


# --- migration text ---------------------------------------------------------


def test_migration_includes_only_checked_entries(qtbot):
    panel = _panel(qtbot)
    panel.show_result(_routine_and_trigger_result())
    panel.set_checked([0])

    text = panel.migration_text()
    assert "CREATE NEW" in text
    assert "CREATE OLD v2" not in text
    assert "pr.t.gone" not in text


def test_injected_save_callback_receives_the_text(qtbot):
    written = []
    panel = _panel(qtbot, save_migration=written.append)
    panel.show_result(_routine_and_trigger_result())
    panel.set_checked([0, 1])

    assert panel.request_save_migration() is True
    assert len(written) == 1
    assert "CREATE NEW" in written[0]
    assert "CREATE OLD v2" in written[0]
    assert "2 reviewed changes" in panel.status_label.text()


def test_save_with_nothing_checked_is_refused_without_calling_back(qtbot):
    written = []
    panel = _panel(qtbot, save_migration=written.append)
    panel.show_result(_routine_and_trigger_result())

    assert panel.request_save_migration() is False
    assert written == []
    assert "Nothing selected" in panel.status_label.text()


def test_status_message_signal_mirrors_the_outcome(qtbot):
    seen = []
    panel = _panel(qtbot, save_migration=lambda text: None)
    panel.status_message.connect(seen.append)
    panel.show_result(_routine_and_trigger_result())
    panel.set_checked([0])
    panel.request_save_migration()
    assert seen and "Migration written" in seen[-1]


# --- honesty about what is not covered --------------------------------------


def test_unsupported_tables_are_surfaced_not_hidden(qtbot):
    panel = _panel(qtbot)
    source = _schema(routines=[_routine("f", source="V2")], tables=[_table("pr.t")])
    target = _schema(routines=[_routine("f", source="V1")], tables=[_table("pr.u")])
    panel.compare(source, target)

    assert panel.unsupported == ["pr.t", "pr.u"]
    assert panel.unsupported_label.isVisibleTo(panel)
    text = panel.unsupported_label.text()
    assert "not compared" in text.lower()
    assert "pr.t" in text and "pr.u" in text
    # ... and it rides into the generated script's header too.
    assert "pr.t" in panel.migration_header()


def test_table_difference_is_listed_and_flagged(qtbot):
    panel = _panel(qtbot)
    panel.show_result(
        SchemaDiffResult(
            [SchemaDifference("changed", "table", "pr.t", "OLD", "NEW")],
            unsupported=["pr.t"],
        )
    )
    rows = [(i.text(0), i.text(2)) for i in _items(panel)]
    assert rows == [("⚠ pr.t", "table")]
    assert panel.unsupported_blockers(panel.differences) == ["pr.t"]


def test_unsupported_difference_is_reported_as_a_refusal(qtbot):
    written = []
    panel = _panel(qtbot, save_migration=written.append)
    panel.show_result(
        SchemaDiffResult(
            [
                SchemaDifference("added", "routine", "pr.new()", None, "CREATE NEW"),
                SchemaDifference("changed", "column", "pr.t.c", "int", "text"),
            ]
        )
    )
    panel.set_checked([0, 1])

    assert panel.request_save_migration() is False
    assert written == []
    message = panel.status_label.text()
    assert "Refusing" in message
    assert "pr.t.c" in message
    assert panel.unsupported_blockers() == ["pr.t.c"]


# --- the two empty states are different -------------------------------------


def test_nothing_compared_yet_differs_from_no_differences(qtbot):
    panel = _panel(qtbot)
    nothing_yet = panel.status_label.text()
    assert panel.has_compared is False
    assert "No comparison run yet" in nothing_yet
    assert panel.save_button.isEnabled() is False

    equal = _schema(routines=[_routine("f")])
    panel.compare(equal, equal)
    assert panel.has_compared is True
    assert panel.differences == []
    assert panel.status_label.text() != nothing_yet
    assert "No differences" in panel.status_label.text()
    assert panel.save_button.isEnabled() is False

    panel.clear()
    assert panel.has_compared is False
    assert "No comparison run yet" in panel.status_label.text()


# --- injected schema sources ------------------------------------------------


def test_sources_are_injected_seams(qtbot):
    calls = []
    snapshot = _schema(routines=[_routine("f", source="V1")])
    live = _schema(routines=[_routine("f", source="V2")])

    def loader(path):
        calls.append(("snapshot", path))
        return snapshot

    def fetch_live(target):
        calls.append(("live", target))
        return live

    panel = _panel(
        qtbot, snapshot_loader=loader, schema_fetchers={"live": fetch_live}
    )
    panel.compare_sources(("snapshot", "/tmp/snap.json"), ("live", "prod"))

    assert calls == [("snapshot", "/tmp/snap.json"), ("live", "prod")]
    assert [d.identity for d in panel.differences] == ["pr.f()"]
    assert "snapshot: /tmp/snap.json" in panel.status_label.text()


def test_missing_seam_raises_rather_than_pretending(qtbot):
    panel = _panel(qtbot)
    for call in (lambda: panel.load_snapshot("x"), lambda: panel.fetch_schema("live")):
        try:
            call()
        except RuntimeError:
            continue
        raise AssertionError("a missing seam must raise")


def test_panel_never_offers_execution(qtbot):
    """§18.3's hard non-goal: no Apply/Execute affordance anywhere."""
    from PySide6.QtWidgets import QAbstractButton

    panel = _panel(qtbot)
    labels = [b.text().lower() for b in panel.findChildren(QAbstractButton)]
    assert not [t for t in labels if "apply" in t or "execute" in t or "deploy" in t]
