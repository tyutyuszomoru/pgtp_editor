# tests/ui/test_ddl_explorer_sandbox.py
"""§18.7 (FQ-022): the SECOND, sandbox-scoped DDL Explorer instance.

The load-bearing claims pinned here, in the order they can break:

* **Session-free.** The sandbox Explorer fetches over the project's sandbox
  `ConnectionParams` and never touches `SandboxController`: opening it opens no
  session, and closing a session does not close it. §18.5 D2 gates *writes*
  behind `open_sandbox` and exempts reads, so wiring this into
  `_refresh_sandbox_affordances`' session-keyed visibility set (the instinctive
  move) would be a regression, not a refinement.
* **No dead control.** The entry is ABSENT until the open project has a sandbox
  with a host, and disappears again with the project.
* **Two independent instances.** Divergent object sets, separate reveals,
  separate closes, each tree navigating its own buffer.
* **Nothing target-scoped is repointed by a sandbox fetch** — not §18.2's drift
  markers (whose reference point is the *deployed target* definition) and not
  §18.6's completion index.
* **Browse-only** (§18.7's sharpest correctness risk): no `Edit DDL` from the
  sandbox tree or buffer, so it cannot reach MainWindow's checkout branch and
  seed `ddl/*.sql` from the sandbox.

No live DB (the `_fetch_ddl_schema` seam is patched, as in
test_ddl_explorer_wiring.py) and no modal calls anywhere.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo
from pgtp_editor.ui.center_stage import (
    DDL_EXPLORER_SANDBOX,
    DDL_EXPLORER_TARGET,
    CenterStage,
)
from pgtp_editor.ui.main_window import MainWindow

from ._menu_helpers import find_action, find_top_menu

SANDBOX_ENTRY = "DDL Explorer (Sandbox)"
QUALITY_ENTRY = "DDL Explorer (Quality)"


def _routine(schema, name, source):
    return RoutineInfo(
        schema=schema,
        name=name,
        arg_types=[],
        return_type="void",
        language="plpgsql",
        source=source,
        kind="function",
    )


def _target_schema():
    return DatabaseSchema(
        routines={"pr.on_target()": _routine("pr", "on_target", "CREATE FUNCTION pr.on_target() ...")},
        triggers={},
        tables={},
    )


def _sandbox_schema():
    """Deliberately a DIFFERENT object set from the target's (§18.7: the trees
    must tolerate genuine divergence, with no cross-referencing)."""
    return DatabaseSchema(
        routines={
            "pr.only_in_sandbox()": _routine(
                "pr", "only_in_sandbox", "CREATE FUNCTION pr.only_in_sandbox() ..."
            )
        },
        triggers={},
        tables={},
    )


def _sync_run(fn, on_result, on_error=None):
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def _empty_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _window(qtbot, tmp_path):
    window = MainWindow(settings=_empty_settings(tmp_path))
    qtbot.addWidget(window)
    window._run_async = _sync_run
    # One fetch seam for both roles, answering per connection -- which is the
    # only thing that distinguishes the two instances.
    window._fetch_ddl_schema = lambda params: (
        _sandbox_schema() if params.host == "sandbox-host" else _target_schema()
    )
    return window


def _open_project(window, tmp_path, sandbox_host="sandbox-host"):
    """Open a project whose target and sandbox are both configured. The
    capability probe is stubbed so `set_active_project` attempts no connection.

    The target carries a password on purpose: BUG-034 raises a one-time
    `QInputDialog` at the first target fetch of a password-less project profile,
    and an un-patched modal in a test hangs the run.
    """
    from pgtp_editor.db.sandbox import SandboxCapabilities

    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        target=ConnectionParams(
            host="target-host", database="quality", password="pw"
        ),
        sandbox=(
            ConnectionParams(host=sandbox_host, database="pgtp_sandbox_x")
            if sandbox_host
            else ConnectionParams()
        ),
    )
    save_settings(project_dir, settings)
    window._ddl_project_ui.probe_sandbox_capabilities = (
        lambda params, **kw: SandboxCapabilities(is_superuser=True)
    )
    window._ddl_project_ui.set_active_project(project_dir, settings)
    return settings


def _all_items(tree):
    """Every item in `tree`, depth-first -- so a menu assertion covers the whole
    tree rather than one guessed row."""
    items = []

    def _walk(item):
        items.append(item)
        for i in range(item.childCount()):
            _walk(item.child(i))

    for i in range(tree.topLevelItemCount()):
        _walk(tree.topLevelItem(i))
    return items


def _sandbox_action(window):
    return find_action(find_top_menu(window, "Database"), SANDBOX_ENTRY)


# --- presence: no dead control -------------------------------------------


def test_both_entries_exist_and_only_quality_is_visible_projectless(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    menu = find_top_menu(window, "Database")

    quality = find_action(menu, QUALITY_ENTRY)
    sandbox = find_action(menu, SANDBOX_ENTRY)

    assert quality is not None and quality.isVisible() is True
    # The action EXISTS (so `_walk_menu_actions` keeps enumerating it for
    # Customize Toolbar) but is not shown -- absent, not disabled.
    assert sandbox is not None
    assert sandbox.isCheckable() is True
    assert sandbox.isVisible() is False


def test_sandbox_entry_appears_when_a_project_with_a_sandbox_opens(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    _open_project(window, tmp_path)

    assert _sandbox_action(window).isVisible() is True


def test_sandbox_entry_stays_absent_for_a_project_with_no_sandbox_host(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    _open_project(window, tmp_path, sandbox_host=None)

    # `ProjectSettings.sandbox` is never None (default_factory), so the gate has
    # to be "has a host" -- the same convention `_target_is_configured` uses.
    assert _sandbox_action(window).isVisible() is False


def test_entry_and_open_tab_go_away_when_the_project_closes(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    _sandbox_action(window).setChecked(True)
    stage = window.center_stage
    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX))

    window._ddl_project_ui.close_project()

    assert _sandbox_action(window).isVisible() is False
    # Left open, the tree would still be showing the closed project's sandbox.
    assert not stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX))
    assert not window.left_tabs.isTabVisible(window.sandbox_ddl_browser_tab_index)


def test_a_sandbox_added_later_by_provisioning_reveals_the_entry(qtbot, tmp_path):
    """§18.7's "or a sandbox added later" case -- the one transition that does
    not go through `_bind_sandbox_controller_to_project`. Its source is now a
    provisioning gesture in Project Settings (`Sandbox Setup…` is deleted), so
    what is adopted is the dialog's `recorded_settings()`: what it actually
    wrote to disk, never the live, possibly half-typed field state."""
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path, sandbox_host=None)
    assert _sandbox_action(window).isVisible() is False

    class _Dialog:
        def recorded_settings(self):
            return ProjectSettings(
                target=ConnectionParams(
                    host="target-host", database="quality", password="pw"
                ),
                sandbox=ConnectionParams(host="sandbox-host", database="sb"),
            )

    window._adopt_provisioned_sandbox_settings(_Dialog())

    assert _sandbox_action(window).isVisible() is True


# --- session-free ---------------------------------------------------------


def test_opening_the_sandbox_explorer_opens_no_session(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    opened = []
    window.sandbox_controller._opener = lambda *a, **k: opened.append(a)

    _sandbox_action(window).setChecked(True)

    assert opened == []
    assert window.sandbox_controller.has_session is False


def test_the_fetch_uses_the_sandbox_params_not_the_target_ones(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    seen = []
    window._fetch_ddl_schema = lambda params: (
        seen.append(params) or _sandbox_schema()
    )

    _sandbox_action(window).setChecked(True)

    assert [p.host for p in seen] == ["sandbox-host"]


def test_closing_a_session_does_not_close_the_sandbox_explorer(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    _sandbox_action(window).setChecked(True)
    stage = window.center_stage

    # The session-keyed refresh runs on every session-state change; the
    # Explorer must survive it untouched (§18.7's corollary).
    window._refresh_sandbox_affordances()

    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX))
    assert _sandbox_action(window).isChecked() is True


# --- two independent instances -------------------------------------------


def test_sandbox_toggle_populates_only_the_sandbox_panel_and_tree(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage

    _sandbox_action(window).setChecked(True)

    sandbox_text = stage.ddl_explorer_panel(DDL_EXPLORER_SANDBOX).editor.toPlainText()
    assert "only_in_sandbox" in sandbox_text
    # The target instance was never fetched, so its buffer and tree stay empty:
    # each tree is built from its own connection's introspection alone.
    assert stage.ddl_editor_panel.editor.toPlainText() == ""
    assert window.sandbox_ddl_browser_panel.tree.topLevelItemCount() > 0
    assert window.ddl_browser_panel.tree.topLevelItemCount() == 0
    assert stage.currentIndex() == stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)
    assert window.left_tabs.isTabVisible(window.sandbox_ddl_browser_tab_index)
    assert not window.left_tabs.isTabVisible(window.ddl_browser_tab_index)


def test_both_instances_can_be_open_at_once_with_divergent_object_sets(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage

    window._ddl_explorer_action.setChecked(True)
    _sandbox_action(window).setChecked(True)

    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_TARGET))
    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX))
    assert "on_target" in stage.ddl_editor_panel.editor.toPlainText()
    assert "only_in_sandbox" not in stage.ddl_editor_panel.editor.toPlainText()
    sandbox_text = stage.ddl_explorer_panel(DDL_EXPLORER_SANDBOX).editor.toPlainText()
    assert "only_in_sandbox" in sandbox_text
    assert "on_target" not in sandbox_text


def test_closing_one_instance_leaves_the_other_open(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage
    window._ddl_explorer_action.setChecked(True)
    _sandbox_action(window).setChecked(True)

    stage.tabCloseRequested.emit(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX))

    assert not stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX))
    assert _sandbox_action(window).isChecked() is False
    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_TARGET))
    assert window._ddl_explorer_action.isChecked() is True
    assert window.left_tabs.isTabVisible(window.ddl_browser_tab_index)


def test_each_tree_navigates_its_own_buffer(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage
    _sandbox_action(window).setChecked(True)
    window._ddl_explorer_action.setChecked(True)
    assert stage.currentIndex() == stage.ddl_explorer_tab_index(DDL_EXPLORER_TARGET)

    window.sandbox_ddl_browser_panel.navigate_requested.emit(1)

    # The sandbox tree's line numbers index the sandbox's synthesized text, so
    # the jump must land on the sandbox tab, never the target one.
    assert stage.currentIndex() == stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)


# --- nothing target-scoped is repointed by a sandbox fetch ---------------


def test_sandbox_fetch_computes_no_drift_markers(qtbot, tmp_path, monkeypatch):
    """§18.2's markers compare against `ProjectSettings.deployed`, a
    deployed-to-TARGET reference point: running them over the sandbox's
    introspection would answer the target's question about the wrong database."""
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    calls = []
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.compute_drift_markers",
        lambda folder, settings, schema: calls.append(schema) or {},
    )

    _sandbox_action(window).setChecked(True)
    assert calls == []

    window._ddl_explorer_action.setChecked(True)
    assert len(calls) == 1  # the target instance still computes its own


def test_sandbox_fetch_does_not_repoint_the_completion_index(qtbot, tmp_path):
    """§18.6's index (and FQ-002's raw-schema candidate list) describes the lane
    an edit will be applied to; a browse of a different database must not
    silently change what an open object tab completes against."""
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    window._ddl_explorer_action.setChecked(True)
    target_index = window._ddl_schema_index
    assert target_index is not None

    _sandbox_action(window).setChecked(True)

    assert window._ddl_schema_index is target_index
    assert "pr.on_target()" in window._ddl_schema.routines


# --- honest degradation --------------------------------------------------


def test_unreachable_sandbox_reports_and_springs_the_toggle_back(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)

    def _boom(params):
        raise RuntimeError("could not connect to server")

    window._fetch_ddl_schema = _boom

    _sandbox_action(window).setChecked(True)

    message = window.statusBar().currentMessage()
    assert "DDL Explorer (Sandbox) failed" in message
    assert "could not connect to server" in message
    assert _sandbox_action(window).isChecked() is False
    stage = window.center_stage
    # No empty tree that would read as an empty database.
    assert not stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX))


def test_open_with_no_sandbox_configured_states_the_fact_and_opens_no_modal(
    qtbot, tmp_path, monkeypatch
):
    """Reachable only by a race (the entry is absent without a sandbox), so it
    must not fall through to the TARGET's Connection Setup prompt."""
    window = _window(qtbot, tmp_path)
    prompted = []
    monkeypatch.setattr(
        window, "_prompt_missing_connection", lambda: prompted.append(True)
    )

    window._open_ddl_explorer(DDL_EXPLORER_SANDBOX)

    assert prompted == []
    assert "No sandbox configured" in window.statusBar().currentMessage()
    assert _sandbox_action(window).isChecked() is False


# --- browse-only (the FQ-024 interaction) --------------------------------


def test_the_sandbox_tree_offers_no_context_menu_on_an_object_row(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    _sandbox_action(window).setChecked(True)
    panel = window.sandbox_ddl_browser_panel

    for item in _all_items(panel.tree):
        assert panel._menu_for_item(item) is None

    # The target tree still offers it -- browse-only is per instance, so this is
    # the control that proves the suppression is not just an empty tree.
    window._ddl_explorer_action.setChecked(True)
    target = window.ddl_browser_panel
    offered = [
        [a.text() for a in menu.actions()]
        for menu in (target._menu_for_item(i) for i in _all_items(target.tree))
        if menu is not None
    ]
    assert ["Edit DDL"] in offered


def test_the_sandbox_buffer_offers_no_edit_ddl_entry(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    _sandbox_action(window).setChecked(True)
    panel = window.center_stage.ddl_explorer_panel(DDL_EXPLORER_SANDBOX)
    # Put the caret inside the one object's span, where the target panel would
    # offer the entry.
    panel.navigate_to_line(1)

    menu = panel._build_context_menu_at(panel.editor.rect().topLeft())

    assert not any("Edit DDL" in a.text() for a in menu.actions())
    # Still a usable read-only menu (copy / select all) -- reading is the point.
    assert menu.actions()


def test_no_edit_signal_from_the_sandbox_tree_can_reach_the_checkout_branch(
    qtbot, tmp_path
):
    """The belt to the browse-only braces: even if a future context menu grew an
    entry, nothing connects the sandbox tree's `edit_requested` to MainWindow, so
    no sandbox definition can be checked out into `ddl/*.sql` (§18.2's drift
    baseline is the deployed TARGET definition)."""
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    from pgtp_editor.ui.ddl_object_editor import DdlObjectRef

    ref = DdlObjectRef(kind="function", schema="pr", name="only_in_sandbox")
    window.sandbox_ddl_browser_panel.edit_requested.emit(ref, "CREATE FUNCTION ...")

    assert window.center_stage.ddl_object_tab(ref.key) is None


# --- CenterStage's role plumbing ----------------------------------------


def test_center_stage_exposes_both_explorer_tabs_hidden_and_role_addressed(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)

    for role in (DDL_EXPLORER_TARGET, DDL_EXPLORER_SANDBOX):
        index = stage.ddl_explorer_tab_index(role)
        assert stage.isTabVisible(index) is False
        assert stage.widget(index) is stage.ddl_explorer_panel(role)
        assert stage.ddl_explorer_role_at(index) == role
    assert stage.ddl_explorer_panel() is stage.ddl_editor_panel
    assert stage.ddl_explorer_role_at(stage.raw_xml_tab_index) is None
    assert set(stage.ddl_explorer_panels()) == {
        DDL_EXPLORER_TARGET,
        DDL_EXPLORER_SANDBOX,
    }


def test_hiding_one_role_emits_only_that_role(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.show_ddl_explorer(DDL_EXPLORER_TARGET)
    stage.show_ddl_explorer(DDL_EXPLORER_SANDBOX)
    got = []
    stage.ddl_explorer_visibility_changed.connect(
        lambda role, visible: got.append((role, visible))
    )

    stage.hide_ddl_explorer(DDL_EXPLORER_SANDBOX)

    assert got == [(DDL_EXPLORER_SANDBOX, False)]
    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_TARGET))


# --- per-tab routing follows the active Explorer ------------------------


def test_find_and_bookmark_routing_follow_the_active_explorer(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage
    _sandbox_action(window).setChecked(True)
    sandbox_panel = stage.ddl_explorer_panel(DDL_EXPLORER_SANDBOX)

    assert window._find_ui.active_find_bar() is sandbox_panel.find_replace_bar
    assert window._find_ui.active_bookmark_editor() is sandbox_panel.editor

    window._ddl_explorer_action.setChecked(True)

    assert window._find_ui.active_find_bar() is stage.ddl_editor_panel.find_replace_bar
    assert window._find_ui.active_bookmark_editor() is stage.ddl_editor_panel.editor


def test_a_direct_sandbox_open_from_the_unchecked_state_introspects_once(
    qtbot, tmp_path
):
    """BUG-260812071208 is role-parameterized exactly like the path it lives on
    (§18.7), so the sandbox instance gets its own regression case rather than a
    copy of the target one. A bare `_open_ddl_explorer(DDL_EXPLORER_SANDBOX)`
    runs from the unchecked state, which is the reproducing condition -- driving
    the menu toggle would be green before and after the fix, because
    `QAction::activate` checks the action before emitting `toggled`.
    """
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    seen = []
    window._fetch_ddl_schema = lambda params: (
        seen.append(params) or _sandbox_schema()
    )
    assert _sandbox_action(window).isChecked() is False

    window._open_ddl_explorer(DDL_EXPLORER_SANDBOX)

    assert [p.host for p in seen] == ["sandbox-host"]
    assert _sandbox_action(window).isChecked() is True


# --- BUG-260812110307: a close during an in-flight fetch wins, per role ------

def _deferred(window):
    """Record the task instead of running it, so a gesture can happen "while the
    fetch is in flight". Returns the list of `(work, on_result)` pairs."""
    queued = []
    window._run_async = lambda fn, on_result, on_error=None: queued.append(
        (fn, on_result)
    )
    return queued


def _land(entry):
    fn, on_result = entry
    on_result(fn())


def test_closing_the_sandbox_explorer_mid_fetch_leaves_it_closed(qtbot, tmp_path):
    """§18.7 parameterizes the whole path by role, so the resurrection was
    role-parameterized too — and so is its fix. The epoch is per role: closing
    the sandbox tree must not also discard the quality one's fetch."""
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage
    queued = _deferred(window)

    _sandbox_action(window).setChecked(True)
    _sandbox_action(window).setChecked(False)
    _land(queued[0])

    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)) is False
    assert window.left_tabs.isTabVisible(window.sandbox_ddl_browser_tab_index) is False
    assert _sandbox_action(window).isChecked() is False


def test_closing_the_sandbox_explorer_does_not_discard_the_quality_fetch(
    qtbot, tmp_path
):
    """The epoch is a per-role dict, not one counter: two independent instances
    (§18.7) must not supersede each other."""
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage
    queued = _deferred(window)

    window._ddl_explorer_action.setChecked(True)  # quality fetch out
    _sandbox_action(window).setChecked(True)  # sandbox fetch out
    _sandbox_action(window).setChecked(False)  # only the sandbox is closed
    _land(queued[1])  # the sandbox result: discarded
    _land(queued[0])  # the quality result: still wanted

    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_TARGET)) is True
    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)) is False


def test_a_project_switch_mid_flight_cannot_reveal_the_old_sandbox(qtbot, tmp_path):
    """The row of the report that escapes the close funnel entirely.

    `_refresh_ddl_explorer_affordances` hides the sandbox tab only when it is
    ALREADY VISIBLE, so a fetch launched from the unchecked state (a bare open,
    or `Reload DDL` with the Explorer closed) never reaches
    `_on_ddl_explorer_visibility_changed`. Without an unconditional bump there,
    the previous project's sandbox schema reveals itself over the new project.
    """
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage
    queued = _deferred(window)
    window._open_ddl_explorer(DDL_EXPLORER_SANDBOX)  # from the UNCHECKED state
    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)) is False

    _open_project(window, tmp_path / "second", sandbox_host=None)
    _land(queued[0])

    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)) is False
    assert _sandbox_action(window).isVisible() is False


def test_a_normal_sandbox_open_still_reveals_the_tab(qtbot, tmp_path):
    """The sandbox half of the guard against the visibility shortcut: at
    `on_result` time the tab is still hidden, because `show_ddl_explorer` is
    what reveals it, so a `isTabVisible` gate would suppress every open."""
    window = _window(qtbot, tmp_path)
    _open_project(window, tmp_path)
    stage = window.center_stage
    queued = _deferred(window)

    _sandbox_action(window).setChecked(True)
    _land(queued[0])

    assert stage.isTabVisible(stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)) is True
    assert _sandbox_action(window).isChecked() is True
