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
"""The forcing function that stops the god object regrowing.

`main_window.py` became unmaintainable by accretion: nothing ever *left* it, and
no single commit looked unreasonable. The decomposition into collaborator
objects only holds if shrinking is enforced, so this test pins `MainWindow`'s
entire attribute surface — every instance attribute plus every class-level name,
private included — to one checked-in literal, `EXPECTED_HOST_SURFACE`.

**This test is expected to be edited in every decomposition wave, and only
then.** Each wave moves a lane out, so each wave *removes* names from the
literal; a wave that legitimately adds a host-side seam (a `UiShell` accessor, a
new collaborator attribute) adds one or two. Either way the change is an
explicit line-level diff a reviewer sees and can question — which is the whole
point. What it makes impossible is a lane quietly growing five more `self._…`
attributes on the host because that was the path of least resistance.

The failure message prints the two directions separately (unexpected new names
vs. names the literal still claims) so the fix is obvious: move the attribute
onto the collaborator that owns it, or, if it genuinely belongs to the host,
add it here on purpose.

`_LEGACY_DELEGATES` is asserted empty for the same reason. It is the ONE
sanctioned bridge while a lane is mid-extraction (`MainWindow.__getattr__`
serves it; hand-written delegating methods are never allowed), and a wave that
ends with entries in it has not finished moving its callers.

Qt-inherited names are excluded by measuring against a bare `QMainWindow`
instance rather than by listing them, so a PySide version that adds a signal
does not fail this test spuriously.
"""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow

from pgtp_editor.ui.main_window import MainWindow


#: Every name `MainWindow` is allowed to carry. See the module docstring before
#: changing it: additions are a deliberate act, removals are what a wave does.
EXPECTED_HOST_SURFACE = {
    "_LEGACY_DELEGATES",
    "_active_ddl_object_panel_for",
    "_active_deployment_group",
    "_add_stub_action",
    # FQ-019: the Activity Log's host half -- the one `ActivityLog`, its dock
    # and panel, the debounce timer + flush, the project transition, and the two
    # `record(...)` entry points every emit point goes through. Added to the
    # literal on purpose: the journal is a host concern (it spans every lane),
    # and `record_file_activity` is what the document and Compare/Merge lanes
    # are injected with so no lane decides the mode for itself.
    "_activity_action",
    "_activity_error_for_report",
    "_activity_write_timer",
    "_adopt_provisioned_sandbox_settings",
    "_apply_caption_edits",
    "_apply_ddl_object_to_sandbox",
    "_apply_ddl_object_to_target",
    "_apply_history_text",
    "_audit_action",
    "_auto_parse_action",
    "_auto_parse_enabled",
    "_auto_parse_now",
    "_auto_parse_timer",
    "_bind_sandbox_controller_to_project",
    "_bookmark_file_path",
    "_bookmark_store_target",
    "_bookmark_write_timer",
    "_bookmark_writes",
    "_build_database_menu",
    "_build_deployment_menu",
    "_build_editor_menu_bar",
    "_build_file_menu",
    "_build_help_menu",
    "_build_history_menu",
    "_build_menu_bar",
    "_build_parsing_menu",
    "_build_project_status_diagram",
    "_build_select_menu",
    "_build_settings_menu",
    "_build_tools_menu",
    "_build_view_menu",
    "_caption_go_to_line",
    "_capture_snapshot_now",
    "_check_active_ddl_object",
    "_close_action",
    "_close_caption_mode",
    "_code_editor_dialog",
    "_coherence_tab_visible",
    "_columns_block_line",
    "_configured_sandbox_params",
    "_confirm_apply",
    "_confirm_close_ddl_object",
    "_confirm_discard_local_change",
    "_confirm_destructive_sandbox_operation",
    "_connection_dialog",
    "_connection_summary_for",
    "_current_project",
    "_current_project_path",
    # FQ-025: the Alter Table ▸ operations (slice 1's columns, slice 2's
    # constraints, slice 3's indexes/comments/whole-table). Host-owned for the
    # same reason FQ-002's creation handlers are -- they build a dialog, inject
    # data read off `_ddl_schema`, and open a tab through `_edit_ddl_live`.
    # Slice 2 added exactly two names, both of them injection: which dialogs
    # take a constraint list, and where that list comes from. Slice 3 added the
    # same pair for indexes, the column-comment seed, and ONE new handler --
    # `Create Table…`, the only entry in the feature that is not scoped to a
    # clicked table and therefore not on `alter_column_requested`.
    "_ALTER_COLUMN_DIALOGS",
    "_ALTER_CONSTRAINT_LIST_DIALOGS",
    "_ALTER_INDEX_LIST_DIALOGS",
    "_alter_column_comment_for",
    # Its table-mode peer, added deliberately: an unseeded table-comment dialog
    # turned an untouched OK into `COMMENT ON TABLE … IS NULL`, i.e. a silent
    # deletion of the existing comment. Both seeds read `self._ddl_schema`, so
    # both belong to the host that owns it.
    "_alter_table_comment_for",
    "_alter_column_dialog",
    "_alter_column_names_for",
    "_alter_column_table_names",
    "_alter_constraints_for",
    "_alter_indexes_for",
    "_alter_ddl_serial",
    "_database_host_label",
    "_db_ui",
    "_ddl_checked_out_paths",
    "_ddl_checkout_relpath",
    "_ddl_object_is_checked_out",
    "_ddl_browser_panels",
    "_ddl_browser_tab_indexes",
    "_ddl_explorer_action",
    "_ddl_explorer_actions",
    "_ddl_explorer_label",
    "_ddl_explorer_params",
    "_ddl_project_folder",
    "_ddl_project_settings",
    "_ddl_project_ui",
    "_ddl_sandbox_content_facts",
    "_ddl_schema",
    "_ddl_schema_index",
    "_debug_label",
    "_debug_log_path",
    "_deployment_actions",
    "_deployment_menu",
    "_dialog_default_dir",
    "_diff_ui",
    "_dirty",
    "_doc_ui",
    "_edit_ddl_checked_out",
    "_edit_ddl_live",
    "_edit_snippets_action",
    # FQ-033's Settings entry and the menu itself. Both belong to the host on
    # purpose: `Settings` is the maintenance-only menu the mode filter toggles,
    # so the host must hold the QMenu to show/hide it, and the action is kept
    # (not rebuilt) so it stays enumerable for Customize Toolbar even while
    # hidden -- the same reason `_edit_snippets_action` is here.
    "_autoformat_settings_action",
    "_settings_menu",
    # FQ-033 part C's refusal sink. Belongs to the host because the Audit panel
    # does: an editor must not reach it, which is exactly why the draft tabs
    # route through CenterStage's aggregator to get here.
    "_report_xml_format_refusal",
    # BUG-062. Both belong to the host on purpose: the panels emit and never
    # touch a database (§18.5 D1), so the host is the only place that can run
    # the re-introspection, and it is the sole consumer of `reload_requested`
    # for both roles. `reload_ddl_explorer` is public because it is also the
    # Database-menu action's slot.
    "_reload_ddl_action",
    "reload_ddl_explorer",
    "_enter_caption_mode",
    "_fetch_ddl_schema",
    "_file_menu",
    "_find_next_action",
    "_file_activity_source",
    # BUG-061: `View ▸ Findings`, held the same way its two sibling tab-focus
    # entries (`_activity_action`, `_results_action`) are -- the left dock and
    # its tabs are host structure, so its menu entry is a host attribute too.
    "_findings_action",
    "_find_ui",
    "_flush_activity_writes",
    "_flush_bookmark_writes",
    "_gen_ui",
    "_generator_config_dir",
    "_history",
    "_history_action",
    "_history_entries",
    "_history_jump",
    # BUG-048: the project history writes only where it may. The two
    # `*_raw_xml_history` slots scope EVERY keystroke path (the window
    # Ctrl+Z/Ctrl+Y shortcuts and the Raw XML editor's re-emission) to a writable
    # Raw XML tab; the lock helpers state the reason when it is refused. They
    # were `*_from_shortcut` until BUG-064 gave them the second caller and a name
    # that describes the scope rather than the host.
    "_history_write_refused",
    "_identity_in_schema",
    "_import_pgtp_connection_into_target",
    "_inspect_sandbox_provisioning",
    "_install_find_next_action",
    "_is_light_theme",
    "_light_theme_action",
    "_lint_on_save_action",
    "_lint_ui",
    "_live_target_identity",
    "_loading",
    "_mcp_action",
    "_mcp_session",
    "_mcp_start",
    "_mode_label",
    "_navigate_to_ddl_object",
    "_not_implemented",
    "_on_activity_project_changed",
    "_on_audit_item_clicked",
    "_on_auto_parse_toggled",
    "_on_bookmark_project_changed",
    "_on_ddl_add_trigger_requested",
    "_on_ddl_alter_column_requested",
    "_on_ddl_create_table_requested",
    "_on_ddl_discard_local_requested",
    "_on_ddl_edit_requested",
    "_on_ddl_explorer_toggled",
    "_on_ddl_explorer_visibility_changed",
    "_on_ddl_navigate_requested",
    "_on_ddl_new_routine_requested",
    "_on_ddl_object_close_requested",
    "_on_ddl_table_selected",
    "_on_edit_code_requested",
    "_on_editor_block_count_changed",
    "_on_editor_bookmarks_changed",
    # FQ-032, added on purpose. The editing-mode segment of the mode indicator
    # follows the FOCUSED editor, so the host's ONE `_refresh_mode_indicator`
    # gains two triggers -- an editing-mode transition on any editor (published
    # through `vim_mode.add_editing_mode_observer`, the bookmark-observer idiom)
    # and a focus change. Both are indicator refreshes, which is already the
    # host's job, so there is no lane to move them onto.
    "_on_editing_mode_changed",
    "_on_editor_line_clicked",
    "_on_editor_text_changed",
    "_on_focus_changed_refresh_mode",
    "_on_light_theme_toggled",
    "_on_manual_chapter_selected",
    "_on_manual_visibility_changed",
    "_on_mcp_server_toggled",
    "_on_new_project_sandbox_provisioned",
    "_on_read_only_edit_attempted",
    "_on_sandbox_operation_finished",
    "_on_sandbox_session_changed",
    "_on_table_ref_selection",
    "_on_tree_activate_node",
    "_on_tree_add_event_handler",
    "_on_tree_edit_event_code",
    "_on_tree_jump_to_column_visibility",
    "_on_tree_jump_to_xml",
    "_on_tree_see_column_in_caption",
    "_on_tree_see_table_details_in_caption",
    "_on_tree_see_table_in_caption",
    "_on_tree_select_xml_block",
    "_on_tree_selection_changed",
    "_open_connection_setup",
    "_open_created_ddl_object",
    "_open_generated_alter_ddl",
    "_open_ddl_explorer",
    "_open_history_jump_list",
    "_open_log_folder",
    "_open_project_status",
    "_open_sandbox_session",
    "_open_sandbox_sql_console",
    "_owning_table_name",
    "_parsing_menu",
    "_php_tabs",
    "_place_cursor_in_opening_tag",
    "_probe_check_active_ddl_object",
    "_project_status_sandbox_facts",
    "_project_status_target",
    "_project_status_window",
    "_prompt_missing_connection",
    "_prompt_target_password",
    "_properties_action",
    "_provision_new_project_sandbox",
    "_raw_xml_history_lock_reason",
    "_raw_xml_panel_action",
    "_redo",
    "_redo_action",
    "_redo_raw_xml_history",
    "_redo_shortcut",
    "_ref_for_created_object",
    "_refresh_ddl_drift_markers",
    "_refresh_editor_menu_affordances",
    "_refresh_parsing_menu_affordances",
    "_refresh_project_status_sandbox_actions",
    "_refresh_project_status_window",
    "_refresh_ddl_explorer_affordances",
    "_refresh_sandbox_affordances",
    "_refresh_workflow_mode_affordances",
    "_refresh_sandbox_console_affordances",
    "_refresh_sandbox_provisioning_status",
    # FQ-023: the one refusal all five session-gated sandbox gestures share.
    "_refuse_sandbox_gesture",
    "_register_checked_out_object",
    "_register_created_object",
    "_report_check_findings",
    "_record_sandbox_run",
    "_report_check_lines",
    "_report_ddl_checkout_drift",
    "_report_ddl_format_refusal",
    # FQ-030: the editor-gesture refusal reporter, the Audit half of
    # `CodeEditor.expansion_refused` (the widget can only show a tooltip).
    "_report_editor_gesture_refusal",
    # FQ-026 renamed it with the vocabulary it reports in, and added the
    # one-line sandbox-comparison modal beside the gesture that raises it.
    "_report_gesture_unavailable",
    "_show_sandbox_comparison",
    "_restore_editor_bookmarks",
    "_restore_theme",
    "_restore_window_state",
    "_restoring",
    "_reveal_left_panel",
    "_reveal_raw_xml_tab",
    "_run_active_ddl_object_on_quality",
    "_run_active_ddl_object_on_sandbox",
    "_run_async",
    "_run_ladder_on_active_ddl_object",
    "_run_selection_in_sandbox_console",
    "_sandbox_check_action",
    "_sandbox_check_present",
    "_sandbox_console_action",
    "_sandbox_ddl_explorer_action",
    "_sandbox_console_available",
    "_sandbox_database_label",
    "_sandbox_probe_check_action",
    "_sandbox_session_provider",
    # FQ-020: `_save_active_tab` is DELETED, not moved -- it was the four-way save
    # router behind `Ctrl+S` / `File ▸ Save` whose `else` branch wrote the `.pgtp`
    # from six unrelated tabs. Its absence here is part of the §7 invariant.
    "_save_active_ddl_object",
    "_save_active_xsd",
    "_save_ddl_object_editor",
    "_schedule_bookmark_write",
    "_schema_storage_dir",
    "_select_all_action",
    "_select_all_in_active_editor",
    "_select_enclosing_action",
    "_select_enclosing_block",
    "_select_menu",
    # FQ-034: `Select Parent Block` became the repeatable `Expand Selection`
    # (`_select_parent_action`/`_select_parent_block` are gone), and gained the
    # inward twin beside it. Two actions and two slots, on the host because the
    # `Select` menu is the host's.
    "_expand_selection_action",
    "_expand_structural_selection",
    "_shrink_selection_action",
    "_shrink_structural_selection",
    "_session_target_passwords",
    "_set_left_panel_visible",
    "_settings",
    "_shell",
    "_shell_run_async",
    "_shell_status",
    # FQ-012: the host owns the shortcut wiring because the pure rules
    # (`shortcut_registry`) hold no Qt and the dialog holds no `QAction` --
    # somebody has to capture the defaults off the live menu bar and run the
    # `setShortcut()` pass. Added on purpose, reviewed as host growth.
    "_shortcut_commands",
    "_shortcut_defaults",
    "_shortcut_overrides",
    "_apply_shortcut_bindings",
    "_restore_shortcut_overrides",
    "apply_and_save_shortcut_overrides",
    "open_customize_shortcuts_dialog",
    "_customize_shortcuts_dialog",
    "_show_audit_dock",
    "_show_left_dock",
    "_show_manual",
    "_snapshot_timer",
    "_snippet_ui",
    "_split_qualified",
    "_store_project_target",
    "_target_apply_available",
    "_target_database_label",
    "_target_is_configured",
    "_target_params_for_apply",
    "_target_params_for_fetch",
    "_toolbar_ui",
    "_tree_action",
    "_tree_jump_to_line",
    "_trigger_function_candidates",
    "_RETURNS_TRIGGER_RE",
    "_trigger_function_for",
    "_trigger_relation_for",
    "_undo",
    "_undo_action",
    "_undo_raw_xml_history",
    "_undo_shortcut",
    "_update_title",
    "_validate_project_action",
    "_wire_ddl_object_apply_seams",
    "_wire_ddl_object_dirty",
    "_wire_php_tab_activity",
    "_wire_ddl_object_panel_reporting",
    "_workflow_mode",
    "_xsd_ui",
    "active_target_params",
    "_active_minor_mode",
    "_connectivity_timer",
    "_install_toolbar_mode_panel",
    "_poll_connectivity",
    "_quality_dot",
    "_record_audit_notice",
    "_record_notice",
    "_refresh_connectivity_affordances",
    "_refresh_mode_indicator",
    # FQ-032, added on purpose. `focused_editing_mode()` is the third segment's
    # input to `_refresh_mode_indicator`; `vim_command_entries` /
    # `vim_command_action` are the `:` palette's namespace and dispatch, and they
    # are the HOST's because the namespace IS the menu tree -- only the window can
    # enumerate `ToolbarController.collect_menu_commands()`, and asking the
    # top-level window is exactly what makes the palette unavailable in the
    # menu-less `CodeEditorDialog`.
    "focused_editing_mode",
    "_results_action",
    "_reveal_activity_tab",
    "_reveal_findings_tab",
    "_reveal_results_dock_tab",
    "_reveal_results_tab",
    "_sandbox_dot",
    "activity_tab_index",
    "bottom_tabs",
    "changeEvent",
    "current_mode",
    "findings_panel",
    "findings_tab_index",
    "results_panel",
    "results_tab_index",
    "toolbar_mode_indicator",
    # FQ-028: `activity_dock` is GONE -- the Activity Log became a TAB of the
    # one bottom dock (which kept the `audit_dock` objectName so saved layouts
    # survive), and the chrome redesign grew the host these names: the three
    # surface reveals + the router's journal sink (Parts 1/3), the ONE mode
    # source of truth and its single update path (Part 2), and the two
    # connectivity dots with their window-active-gated poll (FQ-018).
    "activity_log",
    "activity_panel",
    "audit_dock",
    "audit_panel",
    "center_stage",
    "closeEvent",
    "coherence_panel",
    "coherence_tab_index",
    "contents_tab_index",
    "ddl_browser_panel",
    "ddl_browser_tab_index",
    "dragEnterEvent",
    "dropEvent",
    "editor_menu_bar",
    "enter_caption_mode_for_field",
    "enter_caption_mode_for_table",
    "enter_caption_mode_for_table_details",
    "left_tabs",
    "manual_contents",
    "in_maintenance_mode",
    "new_session",
    "open_project_file",
    "project_tab_index",
    "project_tree",
    "properties_dock",
    "properties_panel",
    "record_activity",
    "record_file_activity",
    "sandbox_controller",
    "sandbox_ddl_browser_panel",
    "sandbox_ddl_browser_tab_index",
    "set_workflow_mode",
    "show_launcher",
    # FQ-032's `:` palette namespace and its dispatch -- see the note beside
    # `focused_editing_mode` above.
    "vim_command_action",
    "vim_command_entries",
    "workflow_mode",
    "tree_dock",
}


def _host_surface(window) -> set[str]:
    """`window`'s own attribute surface, with Qt's inherited names removed.

    Instance attributes and class-level names are unioned deliberately: from a
    caller's point of view `window._toolbar_ui` and `window._build_menu_bar`
    are the same kind of reachable surface, and a lane can shed either one.
    """
    baseline_instance = set(vars(QMainWindow()))
    names = {n for n in vars(window) if not n.startswith("__")} - baseline_instance
    names |= {
        n
        for n in type(window).__dict__
        if not n.startswith("__") and n != "staticMetaObject"
    }
    return names


def test_mainwindow_surface_matches_the_checked_in_literal(qtbot, tmp_path):
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)

    actual = _host_surface(window)
    added = sorted(actual - EXPECTED_HOST_SURFACE)
    removed = sorted(EXPECTED_HOST_SURFACE - actual)
    assert not added and not removed, (
        "MainWindow's attribute surface drifted from EXPECTED_HOST_SURFACE in "
        "tests/ui/test_mainwindow_surface.py.\n"
        f"  NOT in the literal (the host grew these): {added}\n"
        f"  in the literal but gone (a wave removed these): {removed}\n"
        "The host is supposed to SHRINK with every decomposition wave. If a new "
        "name belongs to a feature lane, move it onto that lane's collaborator "
        "and give the host a UiShell accessor instead; if it genuinely belongs "
        "to the host, add it to the literal on purpose so the growth is "
        "reviewed. If a wave removed names, delete them from the literal."
    )


def test_no_legacy_delegates_remain_at_a_wave_boundary():
    """`_LEGACY_DELEGATES` (served by the single `MainWindow.__getattr__`) is the
    only sanctioned bridge for a half-moved lane, and it must be empty whenever
    a wave lands -- otherwise callers were never migrated, just redirected."""
    assert MainWindow._LEGACY_DELEGATES == {}, (
        "MainWindow._LEGACY_DELEGATES is non-empty: "
        f"{sorted(MainWindow._LEGACY_DELEGATES)}. Bridges are for the middle of "
        "an extraction only -- finish moving the callers to the collaborator's "
        "own API and empty the dict before the wave lands."
    )


def test_the_bridge_mechanism_is_a_single_getattr_not_hand_written_methods():
    """Hand-written delegating methods are invisible to the surface literal's
    intent (they read as host behavior) and never get removed. The bridge must
    stay one `__getattr__` reading one dict."""
    assert "__getattr__" in MainWindow.__dict__
    assert isinstance(MainWindow._LEGACY_DELEGATES, dict)


def test_unknown_attribute_still_raises_attribute_error(qtbot, tmp_path):
    """The bridge must not turn typos into silent Nones."""
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    try:
        window._no_such_attribute_at_all
    except AttributeError:
        pass
    else:  # pragma: no cover - a regression would land here
        raise AssertionError("__getattr__ swallowed an unknown attribute")
