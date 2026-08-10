# tests/ui/test_ddl_editor_panel.py
"""EditorPanel: the CenterStage "DDL Explorer" tab (spec §18.1) -- a read-only
sql-mode CodeEditor plus its own FindReplaceBar instance (the same per-tab
routing precedent as the Edit XSD tab)."""
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent

from pgtp_editor.ui.code_editor import CodeEditor, _SQL_KEYWORDS
from pgtp_editor.ui.ddl_editor_panel import EditorPanel
from pgtp_editor.ui.find_replace_bar import FindReplaceBar

_TEXT = (
    "-- FUNCTION pr.calc_total(integer) --\n"
    "CREATE FUNCTION pr.calc_total(a integer) RETURNS numeric AS $$\n"
    "BEGIN\n"
    "  RETURN a * 2;\n"
    "END;\n"
    "$$ LANGUAGE plpgsql;\n"
)


def test_panel_hosts_a_read_only_sql_code_editor(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    assert isinstance(panel.editor, CodeEditor)
    assert panel.editor.isReadOnly() is True
    # sql language mode: the highlighter consumes the SQL keyword set.
    assert panel.editor._highlighter._keywords is _SQL_KEYWORDS


def test_set_ddl_text_replaces_the_buffer(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT)
    assert panel.editor.toPlainText() == _TEXT
    # A second load REPLACES (fresh build_ddl_text result), never appends.
    panel.set_ddl_text("-- TRIGGER pr.t ON x --\ndef\n")
    assert panel.editor.toPlainText() == "-- TRIGGER pr.t ON x --\ndef\n"


def test_navigate_to_line_jumps_the_editor(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT)
    panel.navigate_to_line(3)
    cursor = panel.editor.textCursor()
    assert cursor.blockNumber() == 2  # 1-based line 3
    assert cursor.block().text() == "BEGIN"


def test_panel_has_its_own_find_replace_bar_wired_to_the_sql_editor(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    assert isinstance(panel.find_replace_bar, FindReplaceBar)
    assert panel.find_replace_bar._editor is panel.editor
    assert panel.find_replace_bar.parent() is panel


def test_find_replace_bar_replace_cannot_edit_the_read_only_buffer(qtbot):
    """The bar's Replace goes through replace_current_selection, whose
    read-only guard is what actually protects the DDL buffer (QTextCursor
    edits bypass setReadOnly)."""
    from PySide6.QtGui import QTextCursor

    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT)
    cursor = panel.editor.textCursor()
    cursor.setPosition(0)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
    panel.editor.setTextCursor(cursor)
    panel.editor.replace_current_selection("VANDALIZED")
    assert panel.editor.toPlainText() == _TEXT


# --- Shared fold base, DDL-object provider (spec §8 / §18.1) ---------------


def _schema_with_two_objects():
    from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TriggerInfo

    return DatabaseSchema(
        tables={},
        routines={
            "pr.calc_total(integer)": RoutineInfo(
                schema="pr",
                name="calc_total",
                kind="function",
                arg_types=["integer"],
                args=[],
                source=(
                    "CREATE FUNCTION pr.calc_total(a integer) RETURNS numeric AS $$\n"
                    "BEGIN\n"
                    "  RETURN a * 2;\n"
                    "END;\n"
                    "$$ LANGUAGE plpgsql;"
                ),
            )
        },
        triggers={
            "pr.orders.t_audit": TriggerInfo(
                schema="pr",
                table="orders",
                name="t_audit",
                timing="AFTER",
                events=["INSERT"],
                function_name="pr.audit",
                definition="CREATE TRIGGER t_audit AFTER INSERT ON pr.orders\n  EXECUTE FUNCTION pr.audit();",
            )
        },
    )


def test_panel_editor_carries_the_shared_gutter_bookmark_fold_base(qtbot):
    from pgtp_editor.ui.editor_gutter import _EditorGutter, GutterBookmarkFoldMixin

    panel = EditorPanel()
    qtbot.addWidget(panel)
    assert isinstance(panel.editor, GutterBookmarkFoldMixin)
    assert type(panel.editor._gutter) is _EditorGutter
    panel.set_ddl_text(_TEXT)
    panel.editor.toggle_bookmark(2)
    assert panel.editor.bookmarked_lines() == [2]


def test_set_ddl_text_installs_one_fold_region_per_ddl_object(qtbot):
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    text, spans = build_ddl_text(_schema_with_two_objects())
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans)

    assert len(spans) == 2
    document = panel.editor.document()
    for span in spans:
        banner_block = document.findBlockByNumber(span.start_line - 1)
        assert banner_block.text().startswith("-- ")  # the banner line
        region = panel.editor._foldable_region_starting_at(banner_block)
        # Contained = the object's BODY: banner+1 .. end_line (1-based),
        # i.e. start_line .. end_line-1 as 0-based block numbers.
        assert region == (span.start_line, span.end_line - 1)
    # Exactly one region per object; no others anywhere in the buffer.
    starts = {block for block in range(document.blockCount())
              if panel.editor._foldable_region_starting_at(
                  document.findBlockByNumber(block)) is not None}
    assert starts == {span.start_line - 1 for span in spans}


def test_folding_a_ddl_object_collapses_its_body_under_the_banner(qtbot):
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    text, spans = build_ddl_text(_schema_with_two_objects())
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans)

    document = panel.editor.document()
    first = spans[0]
    banner_block = document.findBlockByNumber(first.start_line - 1)
    panel.editor._toggle_fold(banner_block)

    assert banner_block.isVisible() is True  # the banner stays
    for line in range(first.start_line, first.end_line):  # 0-based body blocks
        assert document.findBlockByNumber(line).isVisible() is False
    # The other object is untouched.
    second = spans[1]
    assert document.findBlockByNumber(second.start_line).isVisible() is True
    # Folding only hides rendering; the character stream is intact.
    assert panel.editor.toPlainText() == text

    panel.editor._toggle_fold(banner_block)
    for line in range(first.start_line, first.end_line):
        assert document.findBlockByNumber(line).isVisible() is True


def test_set_ddl_text_without_spans_leaves_nothing_foldable(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT)
    document = panel.editor.document()
    assert all(
        panel.editor._foldable_region_starting_at(document.findBlockByNumber(i)) is None
        for i in range(document.blockCount())
    )


def test_panel_editor_uses_a_four_character_tab_stop(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    assert panel.editor.tabStopDistance() == 4 * panel.editor.fontMetrics().horizontalAdvance(" ")


def test_panel_navigate_to_line_puts_the_banner_at_the_top(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text("\n".join(f"line {i}" for i in range(1, 401)))
    panel.editor.resize(400, 200)
    panel.show()
    qtbot.waitExposed(panel)
    panel.navigate_to_line(100)
    assert panel.editor.textCursor().blockNumber() == 99
    assert panel.editor.verticalScrollBar().value() == 99


# --- _fold_regions_for_spans, pure (§18.1) --------------------------------


def test_fold_regions_for_spans_translates_banner_to_end_line():
    from pgtp_editor.db.ddl_buffer import DdlObjectSpan
    from pgtp_editor.ui.ddl_editor_panel import _fold_regions_for_spans

    spans = [
        DdlObjectSpan(kind="function", schema="pr", name="f", table=None,
                      start_line=1, end_line=6),
        DdlObjectSpan(kind="trigger", schema="pr", name="t", table="orders",
                      start_line=8, end_line=10),
    ]
    # (start_block, first_contained_block, last_contained_block), 0-based.
    assert _fold_regions_for_spans(spans) == [(0, 1, 5), (7, 8, 9)]


def test_fold_regions_for_spans_skips_a_span_with_no_body():
    """Defensive: a span whose end_line does not exceed its banner line has
    nothing to collapse and contributes no region."""
    from pgtp_editor.db.ddl_buffer import DdlObjectSpan
    from pgtp_editor.ui.ddl_editor_panel import _fold_regions_for_spans

    spans = [
        DdlObjectSpan(kind="function", schema="pr", name="f", table=None,
                      start_line=3, end_line=3),
        DdlObjectSpan(kind="function", schema="pr", name="g", table=None,
                      start_line=5, end_line=4),
    ]
    assert _fold_regions_for_spans(spans) == []


def test_fold_regions_for_spans_of_a_one_line_body():
    """The real minimum from build_ddl_text: a single-line definition still
    folds (banner + exactly one contained line)."""
    from pgtp_editor.db.ddl_buffer import build_ddl_text
    from pgtp_editor.db.introspect import DatabaseSchema, TriggerInfo
    from pgtp_editor.ui.ddl_editor_panel import _fold_regions_for_spans

    schema = DatabaseSchema(
        triggers={
            "pr.orders.t": TriggerInfo(
                schema="pr", table="orders", name="t", timing="after",
                events=["insert"], function_name="fn",
                definition="CREATE TRIGGER t AFTER INSERT ON pr.orders;",
            ),
        },
    )
    _, spans = build_ddl_text(schema)
    assert _fold_regions_for_spans(spans) == [(0, 1, 1)]


# --- Fold behaviour across sibling objects, in the panel -------------------


def test_folding_one_object_leaves_the_other_collapsed_state_alone(qtbot):
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    text, spans = build_ddl_text(_schema_with_two_objects())
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans)
    document = panel.editor.document()

    first, second = spans[0], spans[1]
    panel.editor._toggle_fold(document.findBlockByNumber(first.start_line - 1))
    panel.editor._toggle_fold(document.findBlockByNumber(second.start_line - 1))
    assert all(
        document.findBlockByNumber(line).isVisible() is False
        for line in range(second.start_line, second.end_line)
    )

    # Expanding the FIRST object must not reveal the still-collapsed second.
    panel.editor._toggle_fold(document.findBlockByNumber(first.start_line - 1))
    assert all(
        document.findBlockByNumber(line).isVisible() is True
        for line in range(first.start_line, first.end_line)
    )
    assert all(
        document.findBlockByNumber(line).isVisible() is False
        for line in range(second.start_line, second.end_line)
    )
    assert panel.editor.toPlainText() == text  # character stream intact


def test_reloading_the_buffer_resets_folds_and_reinstalls_regions(qtbot):
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    text, spans = build_ddl_text(_schema_with_two_objects())
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans)
    panel.editor._toggle_fold(panel.editor.document().findBlockByNumber(spans[0].start_line - 1))
    assert panel.editor._fold_state

    panel.set_ddl_text(text, spans)  # a fresh introspection result
    assert panel.editor._fold_state == {}
    document = panel.editor.document()
    assert all(document.findBlockByNumber(i).isVisible() for i in range(document.blockCount()))
    assert (
        panel.editor._foldable_region_starting_at(
            document.findBlockByNumber(spans[0].start_line - 1)
        )
        is not None
    )


def test_reloading_without_spans_clears_the_previous_fold_regions(qtbot):
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    text, spans = build_ddl_text(_schema_with_two_objects())
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans)
    panel.set_ddl_text(_TEXT)  # no spans this time
    document = panel.editor.document()
    assert all(
        panel.editor._foldable_region_starting_at(document.findBlockByNumber(i)) is None
        for i in range(document.blockCount())
    )


def test_bookmarks_survive_folding_and_reset_on_reload(qtbot):
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    text, spans = build_ddl_text(_schema_with_two_objects())
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans)
    panel.editor.toggle_bookmark(spans[0].start_line)  # a body line
    panel.editor._toggle_fold(panel.editor.document().findBlockByNumber(spans[0].start_line - 1))
    assert panel.editor.bookmarked_lines() == [spans[0].start_line]

    panel.set_ddl_text(text, spans)
    assert panel.editor.bookmarked_lines() == []


def test_navigate_to_line_focuses_the_editor(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT)
    panel.show()
    qtbot.waitExposed(panel)
    panel.navigate_to_line(3)
    # focusWidget() rather than hasFocus(): offscreen windows are never
    # activated, but the in-window focus target is still recorded.
    assert panel.focusWidget() is panel.editor
    assert panel.editor.textCursor().blockNumber() == 2


def test_navigate_to_a_span_puts_that_objects_banner_at_the_top(qtbot):
    """End-to-end of the BrowserPanel jump: the clicked object's banner line
    is the first visible line, with its body below (§18.1)."""
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    text, spans = build_ddl_text(_schema_with_two_objects())
    padded = text + "\n".join(f"-- filler {i}" for i in range(200))
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(padded, spans)
    panel.editor.resize(400, 120)
    panel.show()
    qtbot.waitExposed(panel)

    second = spans[1]
    panel.navigate_to_line(second.start_line)
    assert panel.editor.verticalScrollBar().value() == second.start_line - 1
    first_visible = panel.editor.firstVisibleBlock()
    assert first_visible.blockNumber() == second.start_line - 1
    assert first_visible.text().startswith("-- TRIGGER ")


# --- Right-click ▸ Edit… (spec §18.5, D1 entry point 2) ---------------------
def _local_pos_for_line(panel, line: int) -> QPoint:
    """Editor-widget coordinates for `line`'s (1-based) top-left corner."""
    block = panel.editor.document().findBlockByNumber(line - 1)
    rect = panel.editor.blockBoundingGeometry(block).translated(
        panel.editor.contentOffset()
    )
    return rect.topLeft().toPoint() + QPoint(1, 1)


def _edit_action_target(menu):
    """The "Edit DDL: …" QAction in `menu`, or None -- inspects the built menu
    directly rather than ever driving a real modal `QMenu.exec` (the
    xml_editor.py `_build_context_menu` precedent)."""
    for action in menu.actions():
        if action.text().startswith("Edit DDL"):
            return action
    return None


def test_the_span_context_menu_offers_exactly_one_editing_entry(qtbot):
    """FQ-024: `Check Out for Versioning` is withdrawn -- the span menu holds
    ONE editing entry, and the panel no longer even declares the signal it
    used to emit."""
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    schema = _schema_with_two_objects()
    text, spans = build_ddl_text(schema)
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans, schema=schema)

    routine_span = next(s for s in spans if s.kind != "trigger")
    pos = _local_pos_for_line(panel, routine_span.start_line + 1)
    menu = panel._build_context_menu_at(pos)

    ddl_entries = [a.text() for a in menu.actions() if a.text().startswith("Edit DDL")]
    assert ddl_entries == ["Edit DDL: pr.calc_total(integer)"]
    assert not any(
        a.text() == "Check Out for Versioning" for a in menu.actions()
    )
    assert not hasattr(panel, "checkout_requested")


def test_right_click_inside_a_routine_span_offers_edit_with_its_qualified_name(qtbot):
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    schema = _schema_with_two_objects()
    text, spans = build_ddl_text(schema)
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans, schema=schema)
    got = []
    panel.edit_requested.connect(lambda ref, source: got.append((ref, source)))

    routine_span = next(s for s in spans if s.kind != "trigger")
    pos = _local_pos_for_line(panel, routine_span.start_line + 1)  # inside the body
    menu = panel._build_context_menu_at(pos)
    action = _edit_action_target(menu)
    assert action is not None
    assert action.text() == "Edit DDL: pr.calc_total(integer)"
    action.trigger()

    assert len(got) == 1
    ref, source = got[0]
    assert ref.kind == "function"
    assert ref.name == "calc_total"
    assert "RETURN a * 2" in source


def test_right_click_inside_a_trigger_span_offers_edit(qtbot):
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    schema = _schema_with_two_objects()
    text, spans = build_ddl_text(schema)
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans, schema=schema)
    got = []
    panel.edit_requested.connect(lambda ref, source: got.append((ref, source)))

    trigger_span = next(s for s in spans if s.kind == "trigger")
    pos = _local_pos_for_line(panel, trigger_span.start_line)  # the banner line itself
    menu = panel._build_context_menu_at(pos)
    action = _edit_action_target(menu)
    assert action is not None
    action.trigger()

    assert len(got) == 1
    ref, source = got[0]
    assert ref.kind == "trigger"
    assert ref.table == "orders"
    assert ref.name == "t_audit"


def test_right_click_outside_any_span_offers_no_edit(qtbot):
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(_TEXT + "\n-- not inside any span\n", spans=[])

    menu = panel._build_context_menu_at(_local_pos_for_line(panel, 1))

    assert _edit_action_target(menu) is None


def test_right_click_moves_the_caret_to_the_clicked_line_first(qtbot):
    """The resolved span must reflect the CLICK, not a stale caret (§18.5,
    D1) -- start with the caret elsewhere, right-click a different span."""
    from pgtp_editor.db.ddl_buffer import build_ddl_text

    schema = _schema_with_two_objects()
    text, spans = build_ddl_text(schema)
    panel = EditorPanel()
    qtbot.addWidget(panel)
    panel.set_ddl_text(text, spans, schema=schema)
    panel.navigate_to_line(1)  # caret starts on the routine's banner
    got = []
    panel.edit_requested.connect(lambda ref, source: got.append((ref, source)))

    trigger_span = next(s for s in spans if s.kind == "trigger")
    pos = _local_pos_for_line(panel, trigger_span.start_line)
    menu = panel._build_context_menu_at(pos)
    _edit_action_target(menu).trigger()

    assert len(got) == 1
    ref, _source = got[0]
    assert ref.kind == "trigger"
    assert panel.editor.textCursor().blockNumber() == trigger_span.start_line - 1


# -- BUG-048: the undo chords are CLAIMED and ANSWERED here -------------------


def _key_event(kind, key, mods):
    return QKeyEvent(kind, key, mods)


def _deliver(panel, kind, key, mods):
    """Send `panel.editor` an event exactly as Qt would, through the panel's
    installed filter, and report whether the filter consumed it."""
    event = _key_event(kind, key, mods)
    consumed = panel.eventFilter(panel.editor, event)
    return consumed, event


_CTRL = Qt.KeyboardModifier.ControlModifier
_CTRL_SHIFT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def test_the_panel_claims_the_shortcut_override_for_the_undo_chords(qtbot):
    """The half that actually stops the window-level Ctrl+Z QShortcut. A
    read-only QPlainTextEdit does not accept the ShortcutOverride itself (it has
    no undo to offer), which is how the shortcut used to fire here and revert the
    Raw XML project buffer — a different document than this tab shows."""
    panel = EditorPanel()
    qtbot.addWidget(panel)

    for key, mods in (
        (Qt.Key.Key_Z, _CTRL),
        (Qt.Key.Key_Y, _CTRL),
        (Qt.Key.Key_Z, _CTRL_SHIFT),  # the second redo chord (BUG-050)
    ):
        consumed, event = _deliver(
            panel, QEvent.Type.ShortcutOverride, key, mods
        )
        assert consumed is True
        assert event.isAccepted() is True


def test_the_panel_states_why_there_is_nothing_to_undo(qtbot, monkeypatch):
    """The other half: claiming the key without answering it would trade a
    wrong-document mutation for a silent dead key (FQ-023 — state the reason)."""
    panel = EditorPanel()
    qtbot.addWidget(panel)
    said = []
    monkeypatch.setattr(panel.editor, "report_refusal", said.append)

    consumed, _ = _deliver(panel, QEvent.Type.KeyPress, Qt.Key.Key_Z, _CTRL)

    assert consumed is True
    assert said == ["this buffer is read only — there is nothing to undo here"]


def test_other_keys_still_fall_through_the_panel_filter(qtbot):
    """The filter must not become a key sink: anything else goes to super()."""
    panel = EditorPanel()
    qtbot.addWidget(panel)

    consumed, _ = _deliver(panel, QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier)
    assert consumed is False
    consumed, _ = _deliver(panel, QEvent.Type.KeyPress, Qt.Key.Key_F, _CTRL)
    assert consumed is False
