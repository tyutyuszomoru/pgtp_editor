from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor

from pgtp_editor.ui.center_stage import (
    DRAFT_TAB_KEY_KIND,
    CenterStage,
    DraftFragmentTab,
)
from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel, DdlObjectRef
from pgtp_editor.ui.sql_console_panel import CONSOLE_TAB_KEY, SqlConsolePanel


def test_tabs_in_order(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.count() == 7
    assert stage.tabText(0) == "Diff / Merge"
    assert stage.tabText(1) == "Caption Management"
    assert stage.tabText(2) == "Raw XML"
    assert stage.tabText(3) == "Edit XSD"
    # Two Explorer tabs since §18.7 (FQ-022), both labelled by connection role.
    assert stage.tabText(4) == "DDL Explorer (Quality)"
    assert stage.tabText(5) == "DDL Explorer (Sandbox)"
    assert stage.tabText(6) == "Manual"


def test_default_tab_visibility_raw_xml_shown_others_hidden(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    # New default (spec §6.1): Raw XML is the working tab; Diff/Merge and
    # Caption Management are revealed only when invoked.
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.isTabVisible(stage.diff_merge_tab_index) is False
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index


def test_set_raw_xml_tab_visible(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.set_raw_xml_tab_visible(True)
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True


from pgtp_editor.ui.diff_merge_panel import DiffMergePanel


def test_diff_merge_tab_holds_a_real_diff_merge_panel(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.diff_merge_panel, DiffMergePanel)
    assert stage.widget(stage.diff_merge_tab_index) is stage.diff_merge_panel


from pgtp_editor.ui.xml_editor import XmlEditor


def test_raw_xml_tab_holds_a_real_xml_editor(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.xml_editor, XmlEditor)
    # The Raw XML tab now hosts a container widget (editor + find/replace
    # bar); xml_editor remains the accessor and lives inside that container.
    assert stage.widget(stage.raw_xml_tab_index) is stage.raw_xml_tab
    assert stage.xml_editor.parent() is stage.raw_xml_tab


from pgtp_editor.ui.find_replace_bar import FindReplaceBar


def test_raw_xml_tab_container_holds_find_replace_bar(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.find_replace_bar, FindReplaceBar)
    assert stage.find_replace_bar.parent() is stage.raw_xml_tab


from pgtp_editor.ui.caption_management_panel import CaptionManagementPanel


def test_caption_management_tab_holds_the_panel(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.caption_management_panel, CaptionManagementPanel)
    assert stage.widget(stage.caption_management_tab_index) is stage.caption_management_panel


from pgtp_editor.ui.ddl_editor_panel import EditorPanel


def test_ddl_explorer_tab_holds_the_editor_panel_and_starts_hidden(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert isinstance(stage.ddl_editor_panel, EditorPanel)
    assert stage.widget(stage.ddl_tab_index) is stage.ddl_editor_panel
    assert stage.isTabVisible(stage.ddl_tab_index) is False


def test_show_ddl_explorer_reveals_switches_and_emits_true(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    got = []
    stage.ddl_explorer_visibility_changed.connect(lambda role, visible: got.append((role, visible)))

    stage.show_ddl_explorer()

    assert stage.isTabVisible(stage.ddl_tab_index) is True
    assert stage.currentIndex() == stage.ddl_tab_index
    assert got == [("target", True)]


def test_hide_ddl_explorer_hides_returns_to_raw_xml_and_emits_false(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.show_ddl_explorer()
    got = []
    stage.ddl_explorer_visibility_changed.connect(lambda role, visible: got.append((role, visible)))

    stage.hide_ddl_explorer()

    assert stage.isTabVisible(stage.ddl_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert got == [("target", False)]


def test_hide_ddl_explorer_when_not_current_does_not_steal_current_tab(qtbot):
    # Mirrors hide_manual / hide_edit_xsd's not-current guard.
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.show_ddl_explorer()
    stage.show_manual()  # switch current away while DDL stays visible
    assert stage.currentIndex() == stage.manual_tab_index

    stage.hide_ddl_explorer()

    assert stage.isTabVisible(stage.ddl_tab_index) is False
    assert stage.currentIndex() == stage.manual_tab_index


def test_ddl_tab_close_button_hides_directly(qtbot):
    """Unlike Edit XSD (dirty-check via xsd_close_requested), the read-only
    DDL Explorer tab's ✕ hides the tab directly -- nothing to prompt for."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.show_ddl_explorer()
    got = []
    stage.ddl_explorer_visibility_changed.connect(lambda role, visible: got.append((role, visible)))

    stage.tabCloseRequested.emit(stage.ddl_tab_index)

    assert stage.isTabVisible(stage.ddl_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert got == [("target", False)]


def test_ddl_tab_has_close_button_structural_tabs_do_not(qtbot):
    from PySide6.QtWidgets import QTabBar

    stage = CenterStage()
    qtbot.addWidget(stage)
    bar = stage.tabBar()
    right = QTabBar.ButtonPosition.RightSide
    left = QTabBar.ButtonPosition.LeftSide
    assert (bar.tabButton(stage.ddl_tab_index, right) is not None
            or bar.tabButton(stage.ddl_tab_index, left) is not None)
    for index in (stage.raw_xml_tab_index, stage.diff_merge_tab_index,
                  stage.caption_management_tab_index):
        assert bar.tabButton(index, right) is None
        assert bar.tabButton(index, left) is None


def test_enter_caption_mode_keeps_raw_visible_readonly_shows_caption(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()
    # Phase 1: Raw XML stays VISIBLE but read-only (no longer hidden).
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.xml_editor.isReadOnly() is True
    assert stage.isTabVisible(stage.caption_management_tab_index) is True
    assert stage.currentIndex() == stage.caption_management_tab_index
    # BUG-037: the tab itself says why it refuses keystrokes. The status-bar
    # `_mode_label` cue is at the far bottom of the window, not on the tab the
    # user is typing into.
    assert (
        stage.tabText(stage.raw_xml_tab_index)
        == "Raw XML (read only in caption mode)"
    )


def test_leave_caption_mode_restores_raw(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()
    stage.leave_caption_mode()
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.xml_editor.isReadOnly() is False
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert stage.tabText(stage.raw_xml_tab_index) == "Raw XML"


def test_the_read_only_flag_and_the_tab_title_cannot_drift(qtbot):
    """BUG-037's root cause was that these were set in different places (the
    flag in the mode methods, the title nowhere). One helper owns both, so a
    future second read-only mode cannot re-introduce the mismatch by setting
    only one of them."""
    from pgtp_editor.ui.center_stage import RAW_XML_TAB_TITLE

    stage = CenterStage()
    qtbot.addWidget(stage)
    for reason in ("read only in caption mode", "locked while diffing", None):
        stage._set_raw_xml_read_only(reason)
        title = stage.tabText(stage.raw_xml_tab_index)
        assert stage.xml_editor.isReadOnly() is (reason is not None)
        # Read-only <=> the title carries a reason, in both directions.
        assert (title != RAW_XML_TAB_TITLE) is (reason is not None)
        if reason is not None:
            assert reason in title


# --- Dynamic DDL object editor tabs (spec §18.5) ----------------------------
_REF = DdlObjectRef(kind="function", schema="pr", name="recalc")
_REF_2 = DdlObjectRef(kind="function", schema="pr", name="other")


def test_open_ddl_object_tab_appends_after_the_fixed_set(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()

    panel = stage.open_ddl_object_tab(_REF, "CREATE FUNCTION ...")

    assert isinstance(panel, DdlObjectEditorPanel)
    assert stage.count() == fixed_count + 1
    assert stage.indexOf(panel) == fixed_count  # appended, not inserted
    assert stage.currentWidget() is panel
    assert stage.tabText(stage.indexOf(panel)) == "recalc"


def test_open_ddl_object_tab_focuses_the_existing_tab_never_a_second(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    first = stage.open_ddl_object_tab(_REF, "text")
    after_first_open = stage.count()
    stage.setCurrentIndex(stage.raw_xml_tab_index)

    second = stage.open_ddl_object_tab(_REF, "ignored -- already open")

    assert second is first
    assert stage.count() == after_first_open  # no new tab
    assert stage.currentWidget() is first


def test_ddl_object_tab_lookup_by_key(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.ddl_object_tab(_REF.key) is None
    panel = stage.open_ddl_object_tab(_REF, "text")
    assert stage.ddl_object_tab(_REF.key) is panel


def test_two_different_objects_get_two_independent_tabs(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    one = stage.open_ddl_object_tab(_REF, "one")
    two = stage.open_ddl_object_tab(_REF_2, "two")

    assert one is not two
    assert stage.indexOf(two) == stage.indexOf(one) + 1  # tail-only append
    assert stage.ddl_object_tab(_REF.key) is one
    assert stage.ddl_object_tab(_REF_2.key) is two


def test_active_ddl_object_panel_reflects_current_tab(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.active_ddl_object_panel() is None
    panel = stage.open_ddl_object_tab(_REF, "text")
    assert stage.active_ddl_object_panel() is panel
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    assert stage.active_ddl_object_panel() is None


def test_update_ddl_object_tab_reflects_dirty_marker_in_title_and_tooltip(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    panel = stage.open_ddl_object_tab(_REF, "text")
    index = stage.indexOf(panel)
    assert stage.tabText(index) == "recalc"

    panel.editor.insertPlainText("x")
    stage.update_ddl_object_tab(_REF)

    assert stage.tabText(index) == "recalc *"
    assert stage.tabToolTip(index) == "pr.recalc()"


def test_close_ddl_object_tab_removes_it_and_forgets_the_key(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    stage.open_ddl_object_tab(_REF, "text")

    stage.close_ddl_object_tab(_REF.key)

    assert stage.count() == fixed_count
    assert stage.ddl_object_tab(_REF.key) is None


def test_close_ddl_object_tab_leaves_fixed_indices_unchanged(qtbot):
    """Tail-only removal (spec §7 dynamic-tab invariant): removing a dynamic
    tab must never shift any of the fixed *_tab_index constants."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed = {
        "raw": stage.raw_xml_tab_index,
        "xsd": stage.xsd_tab_index,
        "ddl": stage.ddl_tab_index,
        "manual": stage.manual_tab_index,
    }
    stage.open_ddl_object_tab(_REF, "one")
    stage.open_ddl_object_tab(_REF_2, "two")

    stage.close_ddl_object_tab(_REF.key)

    assert stage.raw_xml_tab_index == fixed["raw"]
    assert stage.xsd_tab_index == fixed["xsd"]
    assert stage.ddl_tab_index == fixed["ddl"]
    assert stage.manual_tab_index == fixed["manual"]


def test_ddl_object_tab_close_button_emits_close_requested_with_the_key(qtbot):
    """The ✕ must fall through the fixed-index dispatch to the dynamic-tab
    map lookup (spec §18.5) -- and never call close_ddl_object_tab directly,
    since MainWindow's unsaved-changes prompt runs first."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    panel = stage.open_ddl_object_tab(_REF, "text")
    got = []
    stage.ddl_object_close_requested.connect(got.append)

    stage.tabCloseRequested.emit(stage.indexOf(panel))

    assert got == [_REF.key]
    # Never closed directly -- only the request was signaled.
    assert stage.ddl_object_tab(_REF.key) is panel


def test_ddl_object_tab_has_a_close_button_by_default(qtbot):
    from PySide6.QtWidgets import QTabBar

    stage = CenterStage()
    qtbot.addWidget(stage)
    panel = stage.open_ddl_object_tab(_REF, "text")
    bar = stage.tabBar()
    index = stage.indexOf(panel)
    right = QTabBar.ButtonPosition.RightSide
    left = QTabBar.ButtonPosition.LeftSide
    assert bar.tabButton(index, right) is not None or bar.tabButton(index, left) is not None


# --- Key override (checked-out objects key on their ddl/*.sql path, §18.2) --
def test_open_ddl_object_tab_key_override_is_used_instead_of_ref_key(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)

    panel = stage.open_ddl_object_tab(_REF, "text", key="ddl/pr.recalc.sql")

    assert stage.ddl_object_tab("ddl/pr.recalc.sql") is panel
    assert stage.ddl_object_tab(_REF.key) is None  # not keyed by identity here


def test_open_ddl_object_tab_with_the_same_override_key_focuses_not_duplicates(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    first = stage.open_ddl_object_tab(_REF, "text", key="ddl/pr.recalc.sql")
    stage.setCurrentIndex(stage.raw_xml_tab_index)

    second = stage.open_ddl_object_tab(_REF, "ignored", key="ddl/pr.recalc.sql")

    assert second is first
    assert stage.currentWidget() is first


def test_update_ddl_object_tab_key_override(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    panel = stage.open_ddl_object_tab(_REF, "text", key="ddl/pr.recalc.sql")
    index = stage.indexOf(panel)
    panel.editor.insertPlainText("x")

    stage.update_ddl_object_tab(_REF, key="ddl/pr.recalc.sql")

    assert stage.tabText(index) == "recalc *"


def test_close_ddl_object_tab_with_override_key(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    stage.open_ddl_object_tab(_REF, "text", key="ddl/pr.recalc.sql")

    stage.close_ddl_object_tab("ddl/pr.recalc.sql")

    assert stage.count() == fixed_count
    assert stage.ddl_object_tab("ddl/pr.recalc.sql") is None


# --- Sandbox SQL Console tab (spec §18.5 D4) --------------------------------
def test_open_sandbox_sql_tab_appends_after_the_fixed_set(qtbot):
    """Tail-only append (spec §7 dynamic-tab invariant): the console must land
    after the fixed set and leave every fixed *_tab_index untouched."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    fixed = {
        "diff": stage.diff_merge_tab_index,
        "caption": stage.caption_management_tab_index,
        "raw": stage.raw_xml_tab_index,
        "xsd": stage.xsd_tab_index,
        "ddl": stage.ddl_tab_index,
        "manual": stage.manual_tab_index,
    }

    panel = stage.open_sandbox_sql_tab()

    assert isinstance(panel, SqlConsolePanel)
    assert stage.count() == fixed_count + 1
    assert stage.indexOf(panel) == fixed_count  # appended, not inserted
    assert stage.currentWidget() is panel
    assert stage.tabText(stage.indexOf(panel)) == panel.tab_title()
    assert stage.tabToolTip(stage.indexOf(panel))  # names the sandbox boundary
    assert stage.diff_merge_tab_index == fixed["diff"]
    assert stage.caption_management_tab_index == fixed["caption"]
    assert stage.raw_xml_tab_index == fixed["raw"]
    assert stage.xsd_tab_index == fixed["xsd"]
    assert stage.ddl_tab_index == fixed["ddl"]
    assert stage.manual_tab_index == fixed["manual"]


def test_open_sandbox_sql_tab_is_single_instance(qtbot):
    """§18.5 D4: re-invoking the command focuses the existing console rather
    than opening a second one."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    first = stage.open_sandbox_sql_tab()
    after_first_open = stage.count()
    stage.setCurrentIndex(stage.raw_xml_tab_index)

    second = stage.open_sandbox_sql_tab()

    assert second is first
    assert stage.count() == after_first_open  # no new tab
    assert stage.currentWidget() is first


def test_sandbox_sql_tab_shares_the_object_map_but_not_ddl_object_panels(qtbot):
    """It is filed under ("sandbox-sql",) in the per-object key->widget map,
    yet must never be handed to callers expecting `.ref`/`.is_dirty()`."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.sandbox_sql_tab() is None

    console = stage.open_sandbox_sql_tab()
    obj = stage.open_ddl_object_tab(_REF, "text")

    assert stage.sandbox_sql_tab() is console
    assert stage.ddl_object_tab(CONSOLE_TAB_KEY) is console
    assert CONSOLE_TAB_KEY == ("sandbox-sql",)
    assert stage.ddl_object_panels() == [obj]
    assert console not in stage.ddl_object_panels()
    assert stage.active_ddl_object_panel() is obj
    stage.setCurrentWidget(console)
    assert stage.active_ddl_object_panel() is None


def test_sandbox_sql_tab_close_button_closes_directly_without_signaling(qtbot):
    """Crash regression: the console shares the object-tab map, so its ✕ must
    be intercepted before the object loop. Emitting
    ddl_object_close_requested(("sandbox-sql",)) would reach MainWindow's
    handler and call `is_dirty()` on the console -- an AttributeError."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    console = stage.open_sandbox_sql_tab()
    got = []
    stage.ddl_object_close_requested.connect(got.append)

    stage.tabCloseRequested.emit(stage.indexOf(console))

    assert got == []  # no unsaved-changes round trip -- nothing to save
    assert stage.sandbox_sql_tab() is None
    assert stage.ddl_object_tab(CONSOLE_TAB_KEY) is None
    assert stage.count() == fixed_count


# --- Generated-fragment draft tabs (FQ-006) ---------------------------------
def test_open_draft_fragment_tab_appends_after_the_fixed_set(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    fixed = (
        stage.diff_merge_tab_index,
        stage.caption_management_tab_index,
        stage.raw_xml_tab_index,
        stage.xsd_tab_index,
        stage.ddl_tab_index,
        stage.manual_tab_index,
    )

    tab = stage.open_draft_fragment_tab("page", "pr.customers", "<Page/>")

    assert isinstance(tab, DraftFragmentTab)
    assert stage.count() == fixed_count + 1
    assert stage.indexOf(tab) == fixed_count  # appended, not inserted
    assert stage.currentWidget() is tab
    assert stage.tabText(stage.indexOf(tab)) == "New Page: pr.customers"
    assert stage.tabToolTip(stage.indexOf(tab))
    assert tab.toPlainText() == "<Page/>"
    assert tab.kind == "page"
    assert tab.table_name == "pr.customers"
    assert fixed == (
        stage.diff_merge_tab_index,
        stage.caption_management_tab_index,
        stage.raw_xml_tab_index,
        stage.xsd_tab_index,
        stage.ddl_tab_index,
        stage.manual_tab_index,
    )


def test_open_draft_fragment_tab_is_multi_instance(qtbot):
    """Explicitly NOT single-instance (the console's rule inverted): the same
    kind + table twice must yield two independently-keyed tabs."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()

    first = stage.open_draft_fragment_tab("page", "pr.customers", "a")
    second = stage.open_draft_fragment_tab("page", "pr.customers", "b")

    assert second is not first
    assert stage.count() == fixed_count + 2
    assert first.toPlainText() == "a"
    assert second.toPlainText() == "b"
    keys = list(stage.draft_fragment_tabs())
    assert len(set(keys)) == 2
    assert stage.draft_fragment_tab_key(first) != stage.draft_fragment_tab_key(second)


def test_draft_keys_cannot_collide_with_object_or_console_keys(qtbot):
    """Draft keys are 4-tuples, a `DdlObjectRef.key` is a 5-tuple, a
    checked-out object's override key is a `str`, the console's key is a
    1-tuple."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    tab = stage.open_draft_fragment_tab("detail", "pr.orders", "<Detail/>")
    key = stage.draft_fragment_tab_key(tab)

    assert key[0] == DRAFT_TAB_KEY_KIND
    assert len(key) == 4
    assert len(_REF.key) == 5
    assert len(CONSOLE_TAB_KEY) == 1


def test_draft_tabs_share_the_object_map_but_not_ddl_object_panels(qtbot):
    """A draft has no `.ref`/`.is_dirty()`, so it must never be handed to a
    caller of `ddl_object_panels()` / `active_ddl_object_panel()`."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    obj = stage.open_ddl_object_tab(_REF, "text")
    draft = stage.open_draft_fragment_tab("lookup", "pr.customers", "<Lookup/>")

    assert stage.ddl_object_panels() == [obj]
    assert draft not in stage.ddl_object_panels()
    assert stage.active_ddl_object_panel() is None  # the draft is current
    assert stage.sandbox_sql_tab() is None
    assert list(stage.draft_fragment_tabs().values()) == [draft]
    stage.setCurrentWidget(obj)
    assert stage.active_ddl_object_panel() is obj


def test_draft_tab_close_button_closes_directly_without_signaling(qtbot):
    """Crash regression, the console's lesson applied to drafts: the ✕ must be
    intercepted before the object loop, or ddl_object_close_requested reaches
    MainWindow and calls `is_dirty()` on a widget that has none. No dirty
    prompt either — a draft was never saved anywhere (FQ-006)."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    draft = stage.open_draft_fragment_tab("page", "pr.customers", "<Page/>")
    draft.editor.setPlainText("edited since")  # "dirty" by any other tab's rule
    got = []
    stage.ddl_object_close_requested.connect(got.append)

    stage.tabCloseRequested.emit(stage.indexOf(draft))

    assert got == []  # no unsaved-changes round trip
    assert stage.draft_fragment_tabs() == {}
    assert stage.count() == fixed_count


def test_closing_one_draft_leaves_the_others_open(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    first = stage.open_draft_fragment_tab("page", "pr.a", "<Page/>")
    second = stage.open_draft_fragment_tab("detail", "pr.b", "<Detail/>")

    stage.tabCloseRequested.emit(stage.indexOf(first))

    assert list(stage.draft_fragment_tabs().values()) == [second]
    assert stage.count() == fixed_count + 1


def test_close_draft_fragment_tab_is_idempotent(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    tab = stage.open_draft_fragment_tab("page", "pr.customers", "<Page/>")
    key = stage.draft_fragment_tab_key(tab)

    stage.close_draft_fragment_tab(key)
    stage.close_draft_fragment_tab(key)  # no-op, must not raise

    assert stage.count() == fixed_count
    assert stage.draft_fragment_tabs() == {}
    assert stage.draft_fragment_tab_key(tab) is None


def test_draft_tab_has_its_own_editor_and_find_bar(qtbot):
    """Reuses `XmlEditor` + `FindReplaceBar`; independent of the Raw XML one."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.xml_editor.setPlainText("<Project/>")
    tab = stage.open_draft_fragment_tab("page", "pr.customers", "<Page/>")

    assert tab.editor is not stage.xml_editor
    assert tab.find_replace_bar.parent() is tab
    tab.editor.setPlainText("<Page>edited</Page>")
    assert stage.xml_editor.toPlainText() == "<Project/>"


def test_close_sandbox_sql_tab_is_idempotent(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed_count = stage.count()
    stage.open_sandbox_sql_tab()

    stage.close_sandbox_sql_tab()
    stage.close_sandbox_sql_tab()  # no-op, must not raise

    assert stage.count() == fixed_count
    assert stage.sandbox_sql_tab() is None


# --- §22's injection seam on the custom-PHP tab -----------------------------
# The two `lint_service` / `lint_on_save` parameters exist so a host can
# physically inject §22's service into a tab it opens; without them the four
# remaining §22 wiring items have nowhere to attach. They must default exactly
# as `PhpFileTab.__init__` defaults them, so every pre-§22 caller is unchanged.
from pgtp_editor.ui.php_file_tab import PhpFileTab, php_tab_key


class _StubLintService:
    """Stands in for `lint/service.py::LintService`: the tab must store it and
    hand it back untouched, so nothing here needs to run a linter."""


def test_open_php_file_tab_injects_the_lint_seams_into_the_tab(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    path = tmp_path / "page.php"
    path.write_text("<?php\n", encoding="utf-8")
    service = _StubLintService()

    tab = stage.open_php_file_tab(
        path, "<?php\n", lint_service=service, lint_on_save=True
    )

    assert isinstance(tab, PhpFileTab)
    assert tab.lint_service is service
    assert tab.lint_on_save is True
    assert stage.php_file_tab(php_tab_key(path)) is tab


def test_open_php_file_tab_without_the_lint_seams_is_unchanged(qtbot, tmp_path):
    """The pre-§22 call: neither parameter given, so the tab is linting-free
    and costs nothing -- the defaults must match `PhpFileTab.__init__`."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    path = tmp_path / "page.php"
    path.write_text("<?php\n", encoding="utf-8")

    tab = stage.open_php_file_tab(path, "<?php\n")

    assert tab.lint_service is None
    assert tab.lint_on_save is False


def test_open_php_file_tab_lint_seams_reach_an_untitled_buffer_too(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    service = _StubLintService()

    tab = stage.open_php_file_tab(None, "<?php\n", lint_service=service)

    assert tab.lint_service is service
    assert tab.lint_on_save is False


# --- BUG-049: a draft's Ctrl+Z is a live key, not a swallowed one ------------


def _press(editor, key, mods=Qt.KeyboardModifier.ControlModifier):
    """Drive `XmlEditor.keyPressEvent` directly — the draft's editor CONSUMES
    the undo chords there and re-emits them, so this is the layer under test."""
    editor.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods))


def test_a_draft_tabs_ctrl_z_undoes_its_own_edit(qtbot):
    """`XmlEditor` routes Ctrl+Z to `undo_requested` instead of its native undo,
    so an unwired instance swallows the key forever and silently. A draft has no
    snapshot history (no save path, no dirty concept), so the signal goes
    straight back into the editor — the Edit XSD tab's precedent."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    tab = stage.open_draft_fragment_tab("page", "pr.customers", "<Page/>")
    tab.editor.setFocus()
    cursor = tab.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    tab.editor.setTextCursor(cursor)
    tab.editor.insertPlainText("<Extra/>")
    assert tab.toPlainText() == "<Page/><Extra/>"

    _press(tab.editor, Qt.Key.Key_Z)

    assert tab.toPlainText() == "<Page/>"

    # ...and Ctrl+Y puts it back, as does the second redo chord.
    _press(tab.editor, Qt.Key.Key_Y)
    assert tab.toPlainText() == "<Page/><Extra/>"
    _press(tab.editor, Qt.Key.Key_Z)
    assert tab.toPlainText() == "<Page/>"
    _press(
        tab.editor,
        Qt.Key.Key_Z,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert tab.toPlainText() == "<Page/><Extra/>"


def test_every_draft_gets_its_own_wiring(qtbot):
    """Wired in the TAB, not in MainWindow: drafts are created dynamically and
    multiply, so a self-contained tab cannot be forgotten by the next caller."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    first = stage.open_draft_fragment_tab("page", "t", "a")
    second = stage.open_draft_fragment_tab("detail", "t", "b")

    for tab, seed in ((first, "a"), (second, "b")):
        tab.editor.insertPlainText("X")
        assert tab.toPlainText() != seed
        _press(tab.editor, Qt.Key.Key_Z)
        assert tab.toPlainText() == seed
