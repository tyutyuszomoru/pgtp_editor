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
