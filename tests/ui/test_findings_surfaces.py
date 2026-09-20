# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""FQ-028 Parts 1 and 3 — the three surfaces the one Audit dock became.

§7's nine-prefix reservation rule is dissolved here: a prefix no longer competes
for room in one panel, it names a DESTINATION. What this module pins is that
**nothing is orphaned** — every prefix the app actually produces lands on a
stated surface — and that each surface keeps ONE coherent lifecycle:

* the left-dock **Findings** tab is ephemeral and last-operation-wins,
* the bottom **Results** tab accumulates, separated by dated run rules,
* the bottom **Activity Log** tab is the append-only journal,

plus the two structural facts the restructuring had to get right: the bottom
dock keeps the `audit_dock` objectName so a saved layout survives, and a
`windowState` saved BEFORE this change (one that still names the retired
`activity_dock`) does not break startup.
"""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QListWidgetItem

from pgtp_editor.ui.audit_router import (
    TO_ACTIVITY,
    TO_FINDINGS,
    TO_RESULTS,
    classify,
    prefix_of,
)
from pgtp_editor.ui import toolbar_registry
from pgtp_editor.ui.findings_panel import RUN_RULE, FindingsPanel
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import action_labels, find_action, find_top_menu


def _window(qtbot, tmp_path):
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    return window


def _findings(window):
    return window.findings_panel.row_texts()


def _results(window):
    return window.results_panel.row_texts()


def _journal(window):
    return window.activity_panel.row_texts()


# --- The disposition table: nothing orphaned --------------------------------


def test_every_prefix_the_app_produces_has_a_stated_destination():
    """FQ-028's complete disposition, as a pure classification -- including the
    `[Schema]` split (VERIFY findings vs learning chatter) and the TENTH prefix
    `[Sandbox]`, which the queue entry's nine-row table does not list."""
    assert classify("[Find] line 1: x") == TO_FINDINGS
    assert classify("[Bookmark] line 1: x") == TO_FINDINGS
    assert classify("[Validate] ERROR line 2: x") == TO_RESULTS
    assert classify("[Lint] line 3: x") == TO_RESULTS
    assert classify("[Check] WARNING line 4: x") == TO_RESULTS
    assert classify("[Schema] VERIFY line 5: x") == TO_RESULTS
    assert classify("[Schema] Learned 3 new structural facts") == TO_ACTIVITY
    assert classify("[PHP] Generating page 1") == TO_ACTIVITY
    assert classify("[SQL] line 4: unbalanced dollar quote") == TO_ACTIVITY
    assert classify("[Project] Source .pgtp unchanged") == TO_ACTIVITY
    assert classify("[Sandbox] provision: done.") == TO_RESULTS


def test_an_unprefixed_row_is_not_dropped():
    """A row nobody claimed still has to land somewhere. Results is the closest
    thing to the old dock -- bottom, navigable, kept."""
    assert classify("a bare line") == TO_RESULTS
    assert prefix_of("a bare line") is None


def test_each_prefix_reaches_its_documented_surface_through_the_real_router(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)
    for text in (
        "[Find] line 1: f",
        "[Validate] ERROR line 2: v",
        "[Lint] line 3: l",
        "[Check] WARNING line 4: c",
        "[Schema] VERIFY line 5: s",
        "[Schema] Learned 1 new structural fact",
        "[PHP] Generating page 1",
        "[SQL] line 4: refused",
        "[Project] Source .pgtp unchanged",
        "[Sandbox] provision: done.",
    ):
        window.audit_panel.addItem(text)

    assert _findings(window) == ["[Find] line 1: f"]
    results = _results(window)
    for expected in (
        "[Validate] ERROR line 2: v",
        "[Lint] line 3: l",
        "[Check] WARNING line 4: c",
        "[Schema] VERIFY line 5: s",
        "[Sandbox] provision: done.",
    ):
        assert expected in results
    journal = _journal(window)
    for expected in (
        "[Schema] Learned 1 new structural fact",
        "[PHP] Generating page 1",
        "[SQL] line 4: refused",
        "[Project] Source .pgtp unchanged",
    ):
        assert any(expected in row for row in journal)


# --- Part 1: the left-dock Findings tab -------------------------------------


def test_the_findings_tab_is_in_the_left_dock_and_hidden_until_used(
    qtbot, tmp_path
):
    """NOT the centre pane: a centre tab would hide the editor each hit jumps
    into, which is exactly what stepping through results needs to see."""
    window = _window(qtbot, tmp_path)

    assert window.left_tabs.widget(window.findings_tab_index) is window.findings_panel
    assert window.left_tabs.tabText(window.findings_tab_index) == "Findings"
    assert not window.left_tabs.isTabVisible(window.findings_tab_index)


def test_a_navigable_row_auto_opens_and_focuses_the_findings_tab(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    window.audit_panel.addItem("[Find] line 1: hit")

    assert window.left_tabs.isTabVisible(window.findings_tab_index)
    assert window.left_tabs.currentWidget() is window.findings_panel


def test_the_findings_tab_is_last_operation_wins_across_types(qtbot, tmp_path):
    """One question at a time: bookmarks REPLACE finds rather than piling up
    beside them."""
    window = _window(qtbot, tmp_path)
    window.audit_panel.addItem("[Find] line 1: hit")
    window.audit_panel.addItem('[Find] 1 match(es) for "x"')

    window.audit_panel.addItem("[Bookmark] line 7: seven")

    assert _findings(window) == ["[Bookmark] line 7: seven"]


def test_a_findings_click_still_routes_through_the_one_dispatcher(qtbot, tmp_path):
    """The `Qt.UserRole+N` convention did not move -- only the widget did."""
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("a\nb\ntarget\nd")
    item = QListWidgetItem("[Find] line 3: target")
    item.setData(Qt.ItemDataRole.UserRole, 3)
    window.audit_panel.addItem(item)

    window.findings_panel.itemClicked.emit(window.findings_panel.item(0))

    assert window.center_stage.currentIndex() == window.center_stage.raw_xml_tab_index
    assert window.center_stage.xml_editor.textCursor().blockNumber() + 1 == 3


# --- BUG-061: the View-menu entry that summons it ----------------------------
#
# Owner report: "The 'Findings' tab doesn't exist, it's not in View to turn on
# and off." It DID exist, but its only reveal path was the audit router, so a
# session with no navigable op behind it could never see it.


def test_the_view_menu_offers_findings_beside_its_sibling_tab_entries(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    view_menu = find_top_menu(window, "View")
    labels = action_labels(view_menu)

    assert "Findings" in labels
    # In the run of FOCUS entries, after the two bottom-dock tabs.
    assert labels.index("Findings") == labels.index("Messages") + 1


def test_the_findings_entry_is_a_focus_entry_with_no_shortcut(qtbot, tmp_path):
    """Its two siblings are not checkable (a tab is in view or it is not) and
    carry no built-in shortcut; this one must match rather than invent a third
    posture or claim a key."""
    window = _window(qtbot, tmp_path)
    action = find_action(find_top_menu(window, "View"), "Findings")

    assert action.isCheckable() is False
    assert action.shortcut().isEmpty()
    assert find_action(find_top_menu(window, "View"), "Activity Log").isCheckable() is (
        False
    )


def test_the_findings_entry_reveals_the_tab_through_the_routers_own_path(
    qtbot, tmp_path
):
    """Driven through the real `triggered` signal (BUG-021), and it must reuse
    `_reveal_findings_tab` so the menu and the router can never disagree about
    what "show the findings" means."""
    window = _window(qtbot, tmp_path)
    assert not window.left_tabs.isTabVisible(window.findings_tab_index)
    # The dock carrying the tab may have been closed, so revealing the tab alone
    # is not enough -- hide it first and assert the entry un-hides it too.
    window.tree_dock.setVisible(False)

    find_action(find_top_menu(window, "View"), "Findings").trigger()

    assert window.tree_dock.isHidden() is False
    assert window.left_tabs.isTabVisible(window.findings_tab_index)
    assert window.left_tabs.currentWidget() is window.findings_panel


def test_the_findings_command_is_pinnable_like_its_siblings(qtbot, tmp_path):
    """A brand-new command, so NO `RENAMED_ID_ALIASES` row — but it must
    enumerate into the command universe, which is what makes it pinnable and
    rebindable."""
    window = _window(qtbot, tmp_path)
    known = dict(window._toolbar_ui.collect_menu_commands())

    assert "view.findings" in known
    assert "view.findings" not in toolbar_registry.RENAMED_ID_ALIASES
    assert "view.findings" not in toolbar_registry.RENAMED_ID_ALIASES.values()


# --- Part 3: the bottom dock's two tabs -------------------------------------


def test_the_bottom_dock_hosts_exactly_two_tabs(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    assert window.audit_dock.widget() is window.bottom_tabs
    assert window.bottom_tabs.count() == 2
    assert window.bottom_tabs.tabText(window.activity_tab_index) == "Activity Log"
    assert window.bottom_tabs.tabText(window.results_tab_index) == "Messages"
    assert window.audit_dock.windowTitle() == "Activity Log / Messages"


def test_results_accumulate_across_runs_under_a_dated_rule(qtbot, tmp_path):
    """The owner asked for validation history to be SAVED, so a rerun appends
    under a blank line, a timestamp header and a 40-character dashed rule."""
    window = _window(qtbot, tmp_path)

    window.audit_panel.addItem("[Lint] line 1: first run")
    window.audit_panel.begin_results_run()
    window.audit_panel.addItem("[Lint] line 1: second run")

    rows = _results(window)
    assert "[Lint] line 1: first run" in rows
    assert "[Lint] line 1: second run" in rows
    assert rows.count(RUN_RULE) == 2
    assert len(RUN_RULE) == 40
    # A blank separator line opens every run block but the first.
    assert rows[0] != ""
    assert "" in rows


def test_a_producers_clear_of_its_results_rows_opens_a_run_instead_of_deleting(
    qtbot, tmp_path
):
    """`FindValidateController.clear_validation_results` still says "remove my
    prior rows". On the accumulating Results tab that intent is honoured as a
    RUN BOUNDARY; the rows stay."""
    window = _window(qtbot, tmp_path)
    window.audit_panel.addItem("[Validate] ERROR line 2: first")

    window._find_ui.clear_validation_results()
    window.audit_panel.addItem("[Validate] ERROR line 2: second")

    rows = _results(window)
    assert rows.count("[Validate] ERROR line 2: first") == 1
    assert rows.count("[Validate] ERROR line 2: second") == 1
    assert rows.count(RUN_RULE) == 2


def test_the_run_separator_is_not_a_finding(qtbot, tmp_path):
    """Decoration rows are excluded from the virtual view, so a caller counting
    findings never counts the rule between them -- and a click on one is inert."""
    window = _window(qtbot, tmp_path)

    window.audit_panel.addItem("[Check] WARNING line 1: x")

    assert window.audit_panel.count() == 1
    assert len(_results(window)) == 3  # header + rule + the finding
    assert window.results_panel.finding_items() == [window.audit_panel.item(0)]


def test_the_findings_panel_class_is_shared_and_differs_only_in_accumulation(
    qtbot, tmp_path
):
    window = _window(qtbot, tmp_path)

    assert isinstance(window.findings_panel, FindingsPanel)
    assert isinstance(window.results_panel, FindingsPanel)
    assert window.findings_panel.accumulate is False
    assert window.results_panel.accumulate is True


# --- Persistence: the dock identity -----------------------------------------


def test_the_bottom_dock_keeps_the_audit_object_name(qtbot, tmp_path):
    """`windowState` is restored by `objectName`. Keeping `audit_dock` is what
    carries a user's saved bottom-dock geometry onto the restructured panel."""
    window = _window(qtbot, tmp_path)

    assert window.audit_dock.objectName() == "audit_dock"
    assert "audit_dock".encode("utf-16-be") in bytes(window.saveState())


def test_a_layout_saved_before_this_change_does_not_break_startup(qtbot, tmp_path):
    """A user who saved a layout while FQ-019's separate `activity_dock` existed
    must not end up with a dangling dock or a lost panel. The state names a dock
    that no longer exists; restoring it is a no-op at worst, and every surface
    is still present and reachable afterwards."""
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    legacy = MainWindow(settings=settings)
    qtbot.addWidget(legacy)
    # Forge the pre-FQ-028 shape: a second bottom dock named `activity_dock`.
    from PySide6.QtWidgets import QDockWidget

    stale = QDockWidget("Activity Log", legacy)
    stale.setObjectName("activity_dock")
    legacy.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, stale)
    settings.setValue("windowState", legacy.saveState())
    settings.sync()

    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    assert not hasattr(window, "activity_dock")
    assert window.audit_dock.widget() is window.bottom_tabs
    assert window.bottom_tabs.count() == 2
    assert window.left_tabs.indexOf(window.findings_panel) >= 0
    # And the surviving docks are all still addressable.
    for dock in (window.tree_dock, window.properties_dock, window.audit_dock):
        assert dock.parentWidget() is window
