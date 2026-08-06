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
    "_active_bookmark_editor",
    "_active_find_bar",
    "_add_stub_action",
    "_apply_caption_edits",
    "_apply_changes_to_target",
    "_apply_ddl_object_to_sandbox",
    "_apply_history_text",
    "_audit_action",
    "_auto_open_linked_pgtp",
    "_bind_sandbox_controller_to_project",
    "_build_bookmarks_menu",
    "_build_database_menu",
    "_build_edit_menu",
    "_build_file_menu",
    "_build_help_menu",
    "_build_menu_bar",
    "_build_project_status_diagram",
    "_build_tools_menu",
    "_build_view_menu",
    "_cancel_find_all_timer",
    "_caption_apply_filter",
    "_caption_filter_shortcut",
    "_caption_find_replace_dialog",
    "_caption_go_to_line",
    "_caption_replace_all",
    "_caption_replace_shortcut",
    "_caption_shortcut_open_filter",
    "_caption_shortcut_open_replace",
    "_capture_snapshot_now",
    "_check_active_ddl_object",
    "_checkout_and_edit",
    "_clear_find_results",
    "_clear_validation_results",
    "_close_action",
    "_close_caption_mode",
    "_close_ddl_project",
    "_close_ddl_project_action",
    "_close_project",
    "_close_sandbox_session_action",
    "_code_editor_dialog",
    "_coherence_tab_visible",
    "_columns_block_line",
    "_compare_detail_with",
    "_compare_merge_two_files",
    "_compare_page_with",
    "_configured_sandbox_params",
    "_confirm_close",
    "_confirm_close_ddl_object",
    "_confirm_destructive_sandbox_operation",
    "_confirm_sandbox_apply",
    "_connection_dialog",
    "_connection_setup_action",
    "_connection_summary_for",
    "_create_ddl_project",
    "_current_diff_target_path",
    "_current_diff_target_project",
    "_current_project",
    "_current_project_path",
    "_db_ui",
    "_ddl_checkout_relpath",
    "_ddl_explorer_action",
    "_ddl_project_capability_status",
    "_ddl_project_folder",
    "_ddl_project_settings",
    "_ddl_schema",
    "_ddl_schema_index",
    "_ddl_target_probe_error",
    "_debug_label",
    "_debug_log_path",
    "_deploy_pgtp",
    "_dialog_default_dir",
    "_dirty",
    "_editor_find_action",
    "_editor_replace_action",
    "_ensure_project_saved",
    "_enter_caption_mode",
    "_fetch_ddl_schema",
    "_find_all",
    "_find_all_count",
    "_find_all_iter",
    "_find_all_step",
    "_find_all_stop",
    "_find_all_target",
    "_find_all_term",
    "_find_all_timer",
    "_find_next",
    "_finish_find_all",
    "_gen_ui",
    "_generator_config_dir",
    "_handle_parse_failure",
    "_handle_reparse_failure",
    "_history",
    "_history_action",
    "_history_entries",
    "_history_jump",
    "_is_ddl_project_pgtp_working_copy",
    "_is_light_theme",
    "_light_theme_action",
    "_link_pgtp_to_project_if_needed",
    "_lint_on_save_action",
    "_lint_ui",
    "_loading",
    "_make_caption_find_replace_dialog",
    "_mode_label",
    "_navigate_to_ddl_object",
    "_new_ddl_project",
    "_not_implemented",
    "_offer_pgtp_deploy_on_close",
    "_on_audit_item_clicked",
    "_on_ddl_add_trigger_requested",
    "_on_ddl_checkout_requested",
    "_on_ddl_edit_requested",
    "_on_ddl_explorer_toggled",
    "_on_ddl_explorer_visibility_changed",
    "_on_ddl_navigate_requested",
    "_on_ddl_new_routine_requested",
    "_on_ddl_object_close_requested",
    "_on_ddl_table_selected",
    "_on_edit_code_requested",
    "_on_editor_line_clicked",
    "_on_editor_text_changed",
    "_on_find_selected_text",
    "_on_light_theme_toggled",
    "_on_manual_chapter_selected",
    "_on_manual_visibility_changed",
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
    "_open_caption_filter_dialog",
    "_open_caption_replace_dialog",
    "_open_connection_setup",
    "_open_created_ddl_object",
    "_open_ddl_explorer",
    "_open_ddl_project",
    "_open_ddl_project_settings",
    "_open_history_jump_list",
    "_open_log_folder",
    "_open_pgtp_path",
    "_open_project",
    "_open_project_status",
    "_open_sandbox_session",
    "_open_sandbox_session_action",
    "_open_sandbox_sql_console",
    "_owning_table_name",
    "_php_tabs",
    "_place_cursor_in_opening_tag",
    "_populate_find_all_results",
    "_probe_sandbox_capabilities",
    "_project_status_target",
    "_project_status_window",
    "_prompt_missing_connection",
    "_prompt_pgtp_open_mode",
    "_properties_action",
    "_raw_xml_panel_action",
    "_read_raw_text",
    "_redo",
    "_redo_action",
    "_redo_shortcut",
    "_ref_for_created_object",
    "_refresh_project_dependent_actions",
    "_refresh_sandbox_affordances",
    "_refresh_sandbox_console_affordances",
    "_refresh_target_connection_status",
    "_register_created_object",
    "_remind_pending_ddl_deploys_on_close",
    "_reparse_raw_xml",
    "_replace_all",
    "_report_check_findings",
    "_report_check_lines",
    "_report_ddl_checkout_drift",
    "_report_ddl_format_refusal",
    "_report_ddl_project_drift",
    "_require_ddl_project",
    "_resolve_pgtp_project_path",
    "_restore_theme",
    "_restore_window_state",
    "_restoring",
    "_reveal_left_panel",
    "_reveal_raw_xml_tab",
    "_revert_action",
    "_revert_project",
    "_run_async",
    "_run_selection_in_sandbox_console",
    "_sandbox_check_action",
    "_sandbox_console_action",
    "_sandbox_console_available",
    "_sandbox_database_label",
    "_sandbox_session_provider",
    "_save_active_tab",
    "_save_ddl_object_editor",
    "_save_ddl_project_settings",
    "_save_project",
    "_save_project_as",
    "_schema_storage_dir",
    "_set_active_ddl_project",
    "_set_dirty",
    "_set_left_panel_visible",
    "_settings",
    "_shell",
    "_shell_run_async",
    "_shell_status",
    "_show_audit_dock",
    "_show_ddl_project_settings_dialog",
    "_show_find_bar",
    "_show_left_dock",
    "_show_manual",
    "_show_replace_bar",
    "_snapshot_timer",
    "_split_qualified",
    "_stop_find_all",
    "_toolbar_ui",
    "_tree_action",
    "_tree_jump_to_line",
    "_trigger_function_candidates",
    "_trigger_function_for",
    "_undo",
    "_undo_action",
    "_undo_shortcut",
    "_update_title",
    "_validate_project",
    "_wire_ddl_object_apply_seams",
    "_wire_ddl_object_panel_reporting",
    "_write_project_text",
    "_xsd_ui",
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
    "enter_caption_mode_for_field",
    "enter_caption_mode_for_table",
    "enter_caption_mode_for_table_details",
    "left_tabs",
    "manual_contents",
    "open_project_file",
    "project_tab_index",
    "project_tree",
    "properties_dock",
    "properties_panel",
    "refresh_project_capability_status",
    "sandbox_controller",
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
