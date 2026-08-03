from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.ddl_object_editor import DdlObjectEditorPanel, DdlObjectRef


def test_tabs_in_order(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.count() == 6
    assert stage.tabText(0) == "Diff / Merge"
    assert stage.tabText(1) == "Caption Management"
    assert stage.tabText(2) == "Raw XML"
    assert stage.tabText(3) == "Edit XSD"
    assert stage.tabText(4) == "DDL Explorer"
    assert stage.tabText(5) == "Manual"


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
    stage.ddl_explorer_visibility_changed.connect(got.append)

    stage.show_ddl_explorer()

    assert stage.isTabVisible(stage.ddl_tab_index) is True
    assert stage.currentIndex() == stage.ddl_tab_index
    assert got == [True]


def test_hide_ddl_explorer_hides_returns_to_raw_xml_and_emits_false(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.show_ddl_explorer()
    got = []
    stage.ddl_explorer_visibility_changed.connect(got.append)

    stage.hide_ddl_explorer()

    assert stage.isTabVisible(stage.ddl_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert got == [False]


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
    stage.ddl_explorer_visibility_changed.connect(got.append)

    stage.tabCloseRequested.emit(stage.ddl_tab_index)

    assert stage.isTabVisible(stage.ddl_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert got == [False]


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


def test_leave_caption_mode_restores_raw(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()
    stage.leave_caption_mode()
    assert stage.isTabVisible(stage.raw_xml_tab_index) is True
    assert stage.xml_editor.isReadOnly() is False
    assert stage.isTabVisible(stage.caption_management_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index


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
