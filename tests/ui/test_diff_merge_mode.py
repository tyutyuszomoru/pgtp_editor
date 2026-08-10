"""FQ-021: Compare/Merge is a MODE (spec §12), and the Raw XML editor's
read-only state is a SET OF NAMED REASONS rather than a shared boolean (§8).

A separate file from test_center_stage.py because the feature spans three
modules -- `CenterStage`'s reasons set and mode pair, `DiffMergePanel`'s
panel-owned exit, and `DiffMergeController`'s leave-before-reload ordering --
and reads as one story only when they sit together.
"""
from unittest.mock import patch

from PySide6.QtCore import Qt

from pgtp_editor.ui.center_stage import (
    RAW_XML_READ_ONLY_CAPTION_MODE,
    RAW_XML_READ_ONLY_DIFF_MERGE_MODE,
    RAW_XML_TAB_TITLE,
    CenterStage,
)
from pgtp_editor.ui.main_window import MainWindow

VALID_PGTP = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="development_equipment" tableName="pr.equipment" caption="Old Caption"/>
    </Pages>
  </Presentation>
</Project>
"""

CHANGED_PGTP = VALID_PGTP.replace("Old Caption", "New Caption")


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _compare(window, source_path, target_path):
    with patch(
        "pgtp_editor.ui.modals.QFileDialog.getOpenFileName",
        side_effect=[(source_path, ""), (target_path, "")],
    ):
        window._diff_ui.compare_two_files()


# --- the reasons SET (§8) ----------------------------------------------------


def test_two_modes_hold_the_lock_and_leaving_one_does_not_release_it(qtbot):
    """§8's MANDATORY test, and the exact bug a shared boolean produced: both
    `leave_*` methods used to call `setReadOnly(False)` unconditionally, so
    leaving one mode re-enabled editing while the other still held the editor
    -- silently voiding the invariant that mode exists to enforce."""
    stage = CenterStage()
    qtbot.addWidget(stage)

    stage.enter_caption_mode()
    stage.enter_diff_merge_mode()
    assert stage.raw_xml_read_only_reasons() == {
        RAW_XML_READ_ONLY_CAPTION_MODE,
        RAW_XML_READ_ONLY_DIFF_MERGE_MODE,
    }

    stage.leave_diff_merge_mode()

    assert stage.xml_editor.isReadOnly() is True
    assert stage.raw_xml_read_only_reasons() == {RAW_XML_READ_ONLY_CAPTION_MODE}
    # And the tab names the SURVIVING reason, so the user knows which mode is
    # still holding the editor (the whole point of naming reasons, BUG-037).
    title = stage.tabText(stage.raw_xml_tab_index)
    assert RAW_XML_READ_ONLY_CAPTION_MODE in title
    assert RAW_XML_READ_ONLY_DIFF_MERGE_MODE not in title

    stage.leave_caption_mode()
    assert stage.xml_editor.isReadOnly() is False
    assert stage.raw_xml_read_only_reasons() == set()
    assert stage.tabText(stage.raw_xml_tab_index) == RAW_XML_TAB_TITLE


def test_leaving_caption_mode_does_not_release_the_diff_lock_either(qtbot):
    """The mirror direction -- both `leave_*` methods discard only their own
    reason, so neither ordering can unlock the other's editor."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_diff_merge_mode()
    stage.enter_caption_mode()

    stage.leave_caption_mode()

    assert stage.xml_editor.isReadOnly() is True
    assert stage.raw_xml_read_only_reasons() == {RAW_XML_READ_ONLY_DIFF_MERGE_MODE}
    assert RAW_XML_READ_ONLY_DIFF_MERGE_MODE in stage.tabText(stage.raw_xml_tab_index)


def test_the_tab_title_lists_every_active_reason_deterministically(qtbot):
    """With two modes active the title has to say something sensible: it lists
    both, in a stable (sorted) order -- a set has no order, and a title that
    reshuffled between runs would be its own small bug."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()
    stage.enter_diff_merge_mode()

    assert stage.tabText(stage.raw_xml_tab_index) == (
        f"{RAW_XML_TAB_TITLE} (read only in "
        f"{RAW_XML_READ_ONLY_CAPTION_MODE} + {RAW_XML_READ_ONLY_DIFF_MERGE_MODE})"
    )


def test_re_entering_a_mode_does_not_stack_a_second_copy_of_its_reason(qtbot):
    """A set, not a counter: the three compare entry points may all be used in
    one session, and a second `enter_diff_merge_mode()` must still be undone by
    a single `leave_diff_merge_mode()`."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_diff_merge_mode()
    stage.enter_diff_merge_mode()

    stage.leave_diff_merge_mode()

    assert stage.xml_editor.isReadOnly() is False
    assert stage.raw_xml_read_only_reasons() == set()


def test_leaving_a_mode_that_was_never_entered_is_a_no_op(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_caption_mode()

    stage.leave_diff_merge_mode()

    assert stage.xml_editor.isReadOnly() is True
    assert stage.raw_xml_read_only_reasons() == {RAW_XML_READ_ONLY_CAPTION_MODE}


def test_the_flag_and_the_title_cannot_drift_with_a_reasons_set_either(qtbot):
    """BUG-037's invariant, re-pinned across the generalization: read-only <=>
    the title carries a reason, in both directions, for every set state."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    transitions = (
        (RAW_XML_READ_ONLY_CAPTION_MODE, True),
        (RAW_XML_READ_ONLY_DIFF_MERGE_MODE, True),
        (RAW_XML_READ_ONLY_CAPTION_MODE, False),
        (RAW_XML_READ_ONLY_DIFF_MERGE_MODE, False),
    )
    for reason, active in transitions:
        stage._set_raw_xml_read_only(reason, active=active)
        reasons = stage.raw_xml_read_only_reasons()
        title = stage.tabText(stage.raw_xml_tab_index)
        assert stage.xml_editor.isReadOnly() is bool(reasons)
        assert (title != RAW_XML_TAB_TITLE) is bool(reasons)
        for held in reasons:
            assert held in title


# --- the mode pair (§12) -----------------------------------------------------


def test_enter_diff_merge_mode_reveals_and_focuses_the_tab_and_locks_raw_xml(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.isTabVisible(stage.diff_merge_tab_index) is False

    stage.enter_diff_merge_mode()

    assert stage.isTabVisible(stage.diff_merge_tab_index) is True
    assert stage.currentIndex() == stage.diff_merge_tab_index
    assert stage.xml_editor.isReadOnly() is True
    assert stage.tabText(stage.raw_xml_tab_index) == (
        f"{RAW_XML_TAB_TITLE} (read only in {RAW_XML_READ_ONLY_DIFF_MERGE_MODE})"
    )


def test_leave_diff_merge_mode_hides_the_tab_and_returns_to_an_editable_raw_xml(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_diff_merge_mode()

    stage.leave_diff_merge_mode()

    assert stage.isTabVisible(stage.diff_merge_tab_index) is False
    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert stage.xml_editor.isReadOnly() is False
    assert stage.tabText(stage.raw_xml_tab_index) == RAW_XML_TAB_TITLE


def test_the_mode_outlives_a_tab_switch(qtbot):
    """§12: the lock belongs to the mode, not to the Diff/Merge tab being
    current -- Apply's destroying reload fires whichever tab is showing, so a
    tab-scoped read-only would leave the data-loss window wide open."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_diff_merge_mode()

    stage.setCurrentIndex(stage.raw_xml_tab_index)

    assert stage.xml_editor.isReadOnly() is True
    assert RAW_XML_READ_ONLY_DIFF_MERGE_MODE in stage.tabText(stage.raw_xml_tab_index)


# --- the panel-owned exit (§12) ----------------------------------------------


def test_the_diff_merge_panel_exit_button_leaves_the_mode(qtbot):
    """Before FQ-021 the mode was a one-way door: the Diff/Merge tab is not in
    `_closable` so it has no ✕, and Apply -- an irreversible write -- was the
    only way back to an editable Raw XML."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.enter_diff_merge_mode()

    stage.diff_merge_panel._close_button.click()

    assert stage.isTabVisible(stage.diff_merge_tab_index) is False
    assert stage.xml_editor.isReadOnly() is False


def test_the_exit_is_the_panel_owned_callback_idiom_not_a_tab_close(qtbot):
    """Mirrors Caption Management's `_on_close` seam exactly, so a host that
    later needs a say (a status-bar label, say) can reassign it -- and the tab
    itself stays without a ✕, because a mode is not a tab."""
    from PySide6.QtWidgets import QTabBar

    stage = CenterStage()
    qtbot.addWidget(stage)
    calls = []
    stage.diff_merge_panel._on_close = lambda: calls.append(True)

    stage.diff_merge_panel.close_panel()

    assert calls == [True]
    bar = stage.tabBar()
    assert bar.tabButton(stage.diff_merge_tab_index, QTabBar.ButtonPosition.RightSide) is None
    assert bar.tabButton(stage.diff_merge_tab_index, QTabBar.ButtonPosition.LeftSide) is None


# --- the entry points and the Apply ordering (§12) ---------------------------


def test_every_compare_entry_point_enters_the_mode(qtbot, tmp_path):
    """All three converge on the mode rather than a bare `setCurrentIndex`, so
    Raw XML is locked no matter which gesture started the comparison."""
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    window.open_project_file(source_path)
    page = window._doc_ui.project.pages[0]

    for run in (
        lambda: window._diff_ui.compare_two_files(),
        lambda: window._diff_ui.compare_page_with(page),
        lambda: window._diff_ui.compare_detail_with(page, [page.file_name]),
    ):
        window.center_stage.leave_diff_merge_mode()
        assert window.center_stage.xml_editor.isReadOnly() is False
        with patch(
            "pgtp_editor.ui.modals.QFileDialog.getOpenFileName",
            return_value=(target_path, ""),
        ):
            run()
        assert window.center_stage.currentIndex() == window.center_stage.diff_merge_tab_index
        assert window.center_stage.xml_editor.isReadOnly() is True


def test_apply_leaves_the_mode_before_the_reload(qtbot, tmp_path):
    """§12's ordering rule. `_reload` is `open_project_file`, which
    `setPlainText`s the just-written target into the Raw XML editor -- reloading
    first would drop the fresh document into a widget the user cannot edit."""
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    _compare(window, source_path, target_path)
    leaves = window.center_stage.diff_merge_panel._flattened_leaves()
    assert len(leaves) == 1
    leaves[0].setCheckState(0, Qt.CheckState.Checked)

    read_only_at_reload = []
    real_reload = window._diff_ui._reload
    window._diff_ui._reload = lambda path: (
        read_only_at_reload.append(window.center_stage.xml_editor.isReadOnly()),
        real_reload(path),
    )
    with patch("pgtp_editor.ui.modals.QMessageBox.information"):
        window._diff_ui.apply_changes_to_target()

    assert read_only_at_reload == [False]
    assert window.center_stage.xml_editor.isReadOnly() is False
    assert window.center_stage.isTabVisible(window.center_stage.diff_merge_tab_index) is False


def test_a_refused_apply_keeps_the_mode_so_the_user_can_uncheck_and_retry(qtbot, tmp_path):
    """Only the SUCCESS path leaves. Apply is all-or-nothing (the deep-copy),
    and a refusal must leave the comparison -- and its lock -- exactly as it
    was, or "uncheck the ambiguous ones and re-run" stops being possible."""
    window = MainWindow()
    qtbot.addWidget(window)
    source_path = _write(tmp_path, "source.pgtp", CHANGED_PGTP)
    target_path = _write(tmp_path, "target.pgtp", VALID_PGTP)
    _compare(window, source_path, target_path)

    with patch("pgtp_editor.ui.modals.QMessageBox.information") as mock_info:
        window._diff_ui.apply_changes_to_target()  # nothing checked

    mock_info.assert_called_once()
    assert window.center_stage.xml_editor.isReadOnly() is True
    assert window.center_stage.isTabVisible(window.center_stage.diff_merge_tab_index) is True


# --- FQ-021's third leg: `Navigation`'s three mode-only members (§26) --------
#
# The regression this closes: FQ-020 removed `Apply Changes to Target` from
# `Tools` expecting this leg to rehome it. It never shipped, so between the two
# `DiffMergeController.apply_changes_to_target` was implemented and tested but
# reachable from NO gesture in the app.

_DIFF_MEMBERS = ("Next Difference", "Previous Difference", "Apply Changes to Target")
_BOOKMARK_MEMBERS = (
    "Toggle Bookmark",
    "Next Bookmark",
    "Previous Bookmark",
    "Clear All Bookmarks",
    "List All Bookmarks",
)


def _nav(window):
    from tests.ui._menu_helpers import find_top_menu

    return find_top_menu(window, "Navigation")


def _visible(window, labels):
    from tests.ui._menu_helpers import find_action

    menu = _nav(window)
    return {label: find_action(menu, label).isVisible() for label in labels}


def test_the_three_mode_members_are_hidden_outside_the_mode(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert _visible(window, _DIFF_MEMBERS) == dict.fromkeys(_DIFF_MEMBERS, False)
    # ...and the menu is still there, because the bookmark group is per-EDITOR,
    # not per-mode. A hidden menu would take four always-valid commands with it.
    assert _nav(window).menuAction().isVisible() is True
    assert _visible(window, _BOOKMARK_MEMBERS) == dict.fromkeys(_BOOKMARK_MEMBERS, True)


def test_entering_the_mode_reveals_the_three_and_leaves_the_bookmarks_alone(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    _compare(
        window,
        _write(tmp_path, "source.pgtp", CHANGED_PGTP),
        _write(tmp_path, "target.pgtp", VALID_PGTP),
    )

    assert _visible(window, _DIFF_MEMBERS) == dict.fromkeys(_DIFF_MEMBERS, True)
    assert _visible(window, _BOOKMARK_MEMBERS) == dict.fromkeys(_BOOKMARK_MEMBERS, True)

    window.center_stage.leave_diff_merge_mode()

    assert _visible(window, _DIFF_MEMBERS) == dict.fromkeys(_DIFF_MEMBERS, False)
    assert _visible(window, _BOOKMARK_MEMBERS) == dict.fromkeys(_BOOKMARK_MEMBERS, True)


def test_the_members_hide_when_the_mode_closes_while_raw_xml_is_current(qtbot, tmp_path):
    """The `currentChanged` trap, spelled out.

    The user may tab back to Raw XML mid-comparison (the mode outlives the tab
    switch, above) and then leave from the panel's Close button.
    `leave_diff_merge_mode` ends with `setCurrentIndex(raw_xml_tab_index)`,
    which emits NO `currentChanged` when Raw XML is already current -- so a
    refresh driven by that signal would strand all three members visible with
    no comparison behind them. Visibility hangs off `diff_merge_mode_changed`
    instead, and this is the test that proves it.
    """
    window = MainWindow()
    qtbot.addWidget(window)
    stage = window.center_stage
    _compare(
        window,
        _write(tmp_path, "source.pgtp", CHANGED_PGTP),
        _write(tmp_path, "target.pgtp", VALID_PGTP),
    )
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    assert _visible(window, _DIFF_MEMBERS) == dict.fromkeys(_DIFF_MEMBERS, True)

    changes = []
    stage.currentChanged.connect(changes.append)
    stage.diff_merge_panel._close_button.click()

    assert changes == []  # the gap itself: Qt emitted nothing
    assert stage.diff_merge_mode_active is False
    assert _visible(window, _DIFF_MEMBERS) == dict.fromkeys(_DIFF_MEMBERS, False)


def test_the_mode_flag_reads_the_reasons_set_not_the_current_tab(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.diff_merge_mode_active is False

    stage.enter_diff_merge_mode()
    assert stage.diff_merge_mode_active is True
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    assert stage.diff_merge_mode_active is True

    stage.leave_diff_merge_mode()
    assert stage.diff_merge_mode_active is False


def test_the_mode_signal_fires_both_ways(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    seen = []
    stage.diff_merge_mode_changed.connect(seen.append)

    stage.enter_diff_merge_mode()
    stage.leave_diff_merge_mode()

    assert seen == [True, False]


def test_the_three_actions_survive_a_mode_toggle_as_the_same_objects(qtbot, tmp_path):
    """Built once, only shown/hidden. `ToolbarController._walk_menu_actions`
    never tests `isVisible()`, so a hidden action keeps a stable command id and
    stays in Customize Toolbar's Available list -- recreating them per mode
    would silently break both."""
    from tests.ui._menu_helpers import find_action

    window = MainWindow()
    qtbot.addWidget(window)
    before = [find_action(_nav(window), label) for label in _DIFF_MEMBERS]

    _compare(
        window,
        _write(tmp_path, "source.pgtp", CHANGED_PGTP),
        _write(tmp_path, "target.pgtp", VALID_PGTP),
    )
    window.center_stage.leave_diff_merge_mode()

    after = [find_action(_nav(window), label) for label in _DIFF_MEMBERS]
    assert after == before
    assert window._find_ui.diff_actions == tuple(before)


def test_apply_changes_to_target_menu_action_reaches_the_controller(qtbot, tmp_path):
    """The regression proper: this gesture did not exist anywhere in the app."""
    from tests.ui._menu_helpers import find_action

    window = MainWindow()
    qtbot.addWidget(window)
    _compare(
        window,
        _write(tmp_path, "source.pgtp", CHANGED_PGTP),
        _write(tmp_path, "target.pgtp", VALID_PGTP),
    )
    calls = []
    window._diff_ui.apply_changes_to_target = lambda: calls.append(True)

    find_action(_nav(window), "Apply Changes to Target").trigger()

    assert calls == [True]


def test_caption_mode_gates_the_bookmarks_without_touching_the_diff_members(qtbot, tmp_path):
    """`set_bookmarks_enabled` used to disable the whole `QMenu`, which was only
    equivalent to gating the bookmark group while every member WAS a bookmark
    action. It no longer is -- a comparison loaded during caption work stays
    navigable."""
    from tests.ui._menu_helpers import find_action

    window = MainWindow()
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(VALID_PGTP)
    _compare(
        window,
        _write(tmp_path, "source.pgtp", CHANGED_PGTP),
        _write(tmp_path, "target.pgtp", VALID_PGTP),
    )

    assert window._enter_caption_mode() is True

    menu = _nav(window)
    assert menu.isEnabled() is True
    for label in _BOOKMARK_MEMBERS:
        assert find_action(menu, label).isEnabled() is False, label
    for label in _DIFF_MEMBERS:
        action = find_action(menu, label)
        assert action.isEnabled() is True, label
        # Both modes are on at once, so these stay visible too.
        assert action.isVisible() is True, label
