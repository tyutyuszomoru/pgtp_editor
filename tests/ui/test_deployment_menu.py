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
"""The Editor bar's `Deployment` menu (FQ-020, §7/§26) — the one home for every
save and every outward push, replacing `File ▸ Save`/`Save As…`, `Ctrl+S` and the
four-way router behind them.

Three things here are invariants rather than behaviour checks, and each has a
recorded reason:

* **Contents are per ACTIVE TAB KIND** — the §26 table, all five rows including
  the *"anything else"* row that shows **nothing**. That last row is where the
  deleted router's `else` branch used to write the `.pgtp` from six unrelated
  tabs, so it is asserted per tab kind rather than in aggregate.
* **Every action is built ONCE at startup and only `setVisible`-toggled.**
  `ToolbarController._walk_menu_actions` never tests `isVisible()`, so a hidden
  action stays pinnable with a stable id — but one that does not *exist* at
  enumeration time vanishes from Customize Toolbar's Available list (and from
  queued FQ-012's shortcut list). Per-tab rebuilding would make the pinnable
  universe depend on the active tab.
* **No member carries a shortcut** — §18.5 for the two `Run on …` entries (*an
  irreversible outward effect must not be one keystroke away*), and the FQ-020
  ruling itself for the saves.
"""
from unittest.mock import patch

from PySide6.QtCore import QSettings
from lxml import etree

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui import modals
from tests.ui._menu_helpers import action_labels, find_action, find_top_menu
from tests.ui._sandbox_stubs import fake_session, sync_run

_REF = DdlObjectRef(kind="function", schema="pr", name="recalc")
_SOURCE = "CREATE OR REPLACE FUNCTION pr.recalc() RETURNS void AS $$ BEGIN END $$;"

#: The §26 per-tab table, verbatim.
RAW_XML = ["Compare/Merge pgtp", "Save pgtp", "Save as new pgtp", "Deploy .pgtp"]
# FQ-026 renamed two of the three: `Run on sandbox` -> `Check and commit to
# sandbox`, `Run on quality` -> `Apply to quality`. Each label is now the ONE
# name its operation has, shared with the confirmation title and the Audit line.
DDL_OBJECT = ["Save in Project", "Check and commit to sandbox", "Apply to quality"]
XSD = ["Save XSD"]
PHP = ["Save PHP File"]
ALL_ENTRIES = RAW_XML + DDL_OBJECT + XSD + PHP


def _window(qtbot, tmp_path):
    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    # BUG-043: the window-wide off-thread seam, stubbed for the whole file
    # rather than per test. `_shell_run_async` re-reads it at call time, and
    # since BUG-043 the sandbox controller is routed through that trampoline
    # too, so this single line covers every lane a test in here can start --
    # the capability probe, the target connection test, and `open_session`.
    # This file is where BUG-043 was found: one test set a sandbox `database`,
    # BUG-040's auto-open dialled it for real on a worker thread, and the
    # failure landed in whichever test was running when the TCP attempt gave
    # up -- a different name every run.
    window._run_async = sync_run
    return window


def _menu(window):
    return find_top_menu(window, "Deployment")


def _visible(window):
    return [
        action.text()
        for action in _menu(window).actions()
        if not action.isSeparator() and action.isVisible()
    ]


class _FakeProject:
    def __init__(self, tree):
        self.tree = tree


def _pgtp_with_connection():
    return _FakeProject(
        etree.ElementTree(
            etree.fromstring(
                b'<Project><ConnectionOptions host="db01" port="5432" login="u" '
                b'database="prod"/></Project>'
            )
        )
    )


# -- membership --------------------------------------------------------------


def test_every_entry_exists_at_startup_in_the_table_order(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert action_labels(_menu(window)) == ALL_ENTRIES


def test_no_entry_carries_a_keyboard_shortcut(qtbot, tmp_path):
    """§18.5 for the two `Run on …` entries, and the FQ-020 ruling for the four
    saves. Also asserts there are no separators: only one group is ever visible,
    so a separator would render as a stray line rather than as grouping."""
    window = _window(qtbot, tmp_path)
    for action in _menu(window).actions():
        assert action.isSeparator() is False
        assert action.shortcut().isEmpty(), action.text()
        assert action.shortcuts() == []


def test_the_raw_xml_tab_shows_the_four_pgtp_entries(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    assert _visible(window) == RAW_XML


def test_the_edit_xsd_tab_shows_only_save_xsd(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.center_stage.show_edit_xsd()
    assert _visible(window) == XSD


def test_a_ddl_object_tab_shows_the_three_destinations(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    assert _visible(window) == DDL_OBJECT


def test_a_php_tab_shows_only_save_php_file(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = tmp_path / "x.php"
    path.write_text("<?php", encoding="utf-8")
    window._php_tabs.open_path(path)
    assert _visible(window) == PHP


def test_the_tab_kinds_with_no_save_path_show_NOTHING(qtbot, tmp_path):
    """§26's *"anything else"* row, and the direct replacement for the deleted
    router's defect: `Ctrl+S` on any of these used to write the `.pgtp`.

    Asserted per tab kind, not in aggregate, so a future tab kind that leaks into
    one of the groups is named by the failure.
    """
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    # The Sandbox SQL Console (§18.5 D4) and an FQ-006 draft fragment tab -- the
    # two the spec calls out as never saving anywhere.
    console = stage.open_sandbox_sql_tab(session_provider=lambda: None)
    assert _visible(window) == []
    draft = stage.open_draft_fragment_tab("page", "orders", "<Page/>")
    assert _visible(window) == []
    assert console is not None and draft is not None

    for index in (
        stage.diff_merge_tab_index,
        stage.ddl_tab_index,
        stage.sandbox_ddl_tab_index,
        stage.manual_tab_index,
        stage.caption_management_tab_index,
    ):
        stage.setTabVisible(index, True)
        stage.setCurrentIndex(index)
        assert _visible(window) == [], stage.tabText(index)


def test_switching_tabs_flips_visibility_without_rebuilding_the_actions(
    qtbot, tmp_path
):
    """The build-once invariant, measured by IDENTITY: the same QAction objects
    survive a tab switch. Rebuilding would leave `ToolbarController` holding dead
    QActions and would drop a pinned button's id."""
    window = _window(qtbot, tmp_path)
    before = list(_menu(window).actions())
    window._on_ddl_edit_requested(_REF, _SOURCE)
    window.center_stage.show_edit_xsd()
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)
    after = list(_menu(window).actions())
    assert [id(a) for a in after] == [id(a) for a in before]


def test_hidden_entries_stay_pinnable_with_stable_ids(qtbot, tmp_path):
    """Why the build-once rule is a correctness constraint and not tidiness:
    `_walk_menu_actions` never tests `isVisible()`, so Customize Toolbar's
    Available list must offer every `Deployment` command on EVERY tab. If the menu
    were rebuilt per tab this list would shrink to the active tab's members and
    saved `toolbarIds` for the others would be silently dropped."""
    window = _window(qtbot, tmp_path)
    expected = {
        "deployment.compare-merge-pgtp",
        "deployment.save-pgtp",
        "deployment.save-as-new-pgtp",
        "deployment.deploy-pgtp",
        "deployment.save-in-project",
        # FQ-026 renamed both; the id is the whole menu path, so the ids moved
        # with the labels and `RENAMED_ID_ALIASES` carries a row for each.
        "deployment.check-and-commit-to-sandbox",
        "deployment.apply-to-quality",
        "deployment.save-xsd",
        "deployment.save-php-file",
    }
    # On Raw XML, where five of the nine are hidden.
    ids = {command_id for command_id, _label in window._toolbar_ui.all_menu_commands()}
    assert expected <= ids
    # ...and on a DDL object tab, where a different five are hidden.
    window._on_ddl_edit_requested(_REF, _SOURCE)
    ids = {command_id for command_id, _label in window._toolbar_ui.all_menu_commands()}
    assert expected <= ids

    # A pinned, currently-hidden entry keeps its button (the accepted FQ-015
    # trade-off is that the BUTTON comes and goes, not that the id dies).
    window._toolbar_ui.apply_ids(["deployment.save-php-file"])
    assert window._toolbar_ui.command_ids == ["deployment.save-php-file"]


def test_closing_the_object_tab_hands_the_menu_back_to_the_raw_xml_group(
    qtbot, tmp_path
):
    """The refresh must run on every `currentChanged`, not only when a tab is
    opened: a stale `ddl-object` group left behind by a closed tab would offer
    `Apply to quality` with no object to send."""
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = stage.ddl_object_tab(_REF.key)
    assert _visible(window) == DDL_OBJECT

    stage.removeTab(stage.indexOf(panel))

    assert _visible(window) == RAW_XML


def test_the_group_follows_the_tab_in_both_directions(qtbot, tmp_path):
    """Round trip, because a one-way test passes even if the refresh only ever
    ADDS a group: each switch must hide the previous tab kind's entries too."""
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    path = tmp_path / "x.php"
    path.write_text("<?php", encoding="utf-8")
    php_tab = window._php_tabs.open_path(path)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = stage.ddl_object_tab(_REF.key)

    for widget, expected in (
        (php_tab, PHP),
        (panel, DDL_OBJECT),
        (php_tab, PHP),
    ):
        stage.setCurrentWidget(widget)
        assert _visible(window) == expected


def test_a_shown_entry_is_never_merely_GREYED_OUT(qtbot, tmp_path):
    """§7 keeps exactly two postures — present or absent. A greyed-out entry
    would be a third, so whatever is on offer on a tab must be clickable there;
    the reasons an unavailable destination cannot run are STATED on trigger
    (FQ-023), never expressed as a dead entry.

    (Qt disables an action as a side effect of `setVisible(False)`, so this is
    asserted over the visible members only — the hidden ones' enabled state is
    Qt's bookkeeping, not a posture.)
    """
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    window._on_ddl_edit_requested(_REF, _SOURCE)
    panel = stage.ddl_object_tab(_REF.key)
    stage.show_edit_xsd()
    for target in (stage.raw_xml_tab_index, panel, stage.xsd_tab_index):
        if isinstance(target, int):
            stage.setCurrentIndex(target)
        else:
            stage.setCurrentWidget(target)
        shown = [a for a in _menu(window).actions() if a.isVisible()]
        assert shown
        for action in shown:
            assert action.isEnabled() is True, action.text()


# -- wiring ------------------------------------------------------------------


def test_compare_merge_pgtp_is_the_relabelled_tools_entry(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    with patch.object(window._diff_ui, "compare_two_files") as compare:
        find_action(_menu(window), "Compare/Merge pgtp").trigger()
    assert compare.call_count == 1


def test_deploy_pgtp_is_wired_to_the_project_lane(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    with patch.object(window._ddl_project_ui, "deploy_pgtp") as deploy:
        find_action(_menu(window), "Deploy .pgtp").trigger()
    assert deploy.call_count == 1


def test_save_in_project_off_a_ddl_tab_reports_instead_of_no_opping(qtbot, tmp_path):
    """Reachable from a pinned toolbar button (the entry is hidden, the button is
    not gone), so it must state why rather than silently doing nothing."""
    window = _window(qtbot, tmp_path)
    find_action(_menu(window), "Save in Project").trigger()
    assert "Save in Project runs on an open DDL object tab" in (
        window.statusBar().currentMessage()
    )


def test_save_pgtp_is_wired_to_the_in_place_writer(qtbot, tmp_path):
    """`Deployment ▸ Save pgtp` is the surviving in-place `.pgtp` save — the one
    the deleted router reached through its `else`, now reachable only by name."""
    window = _window(qtbot, tmp_path)
    with patch.object(window._doc_ui, "save_project") as save_project:
        find_action(_menu(window), "Save pgtp").trigger()
    assert save_project.call_count == 1


def test_save_as_new_pgtp_is_wired_to_save_as(qtbot, tmp_path):
    """`Ctrl+Shift+S` is deleted; the capability survives under this name only."""
    window = _window(qtbot, tmp_path)
    with patch.object(window._doc_ui, "save_as") as save_as:
        find_action(_menu(window), "Save as new pgtp").trigger()
    assert save_as.call_count == 1


def test_save_xsd_is_wired_to_the_xsd_controller(qtbot, tmp_path):
    """A relabel of the router's first branch, not new code."""
    window = _window(qtbot, tmp_path)
    window.center_stage.show_edit_xsd()
    with patch.object(window._xsd_ui, "save") as save:
        find_action(_menu(window), "Save XSD").trigger()
    assert save.call_count == 1


def test_save_xsd_off_the_xsd_tab_refuses_instead_of_TRUNCATING_curated_xsd(
    qtbot, tmp_path
):
    """`XsdController.save` writes `stage.xsd_editor.toPlainText()` to
    `curated.xsd` unconditionally, so an off-tab trigger used to overwrite the
    file with the empty buffer. The entry is hidden here and Qt will not trigger
    a hidden QAction, so this is reached the way FQ-012 will reach it — by
    calling the slot the shortcut would be bound to."""
    window = _window(qtbot, tmp_path)
    with patch.object(window._xsd_ui, "save") as save:
        assert window._save_active_xsd() is False
    assert save.call_count == 0
    assert "Save XSD runs on the Edit XSD tab" in window.statusBar().currentMessage()


def test_save_php_file_is_wired_to_the_php_tab_controller(qtbot, tmp_path):
    """A relabel of the router's PHP branch. The tab's own `Ctrl+S` filter was
    removed with it (see `tests/ui/test_php_file_tab.py`), so this menu entry is
    now the ONLY way a PHP buffer reaches disk."""
    window = _window(qtbot, tmp_path)
    path = tmp_path / "x.php"
    path.write_text("<?php", encoding="utf-8")
    window._php_tabs.open_path(path)
    with patch.object(window._php_tabs, "save_active_tab") as save:
        find_action(_menu(window), "Save PHP File").trigger()
    assert save.call_count == 1


def test_no_entry_other_than_the_two_pgtp_saves_can_write_the_pgtp(qtbot, tmp_path):
    """The mandatory FQ-020 test, stated as the invariant it defends: **no code
    path saves the `.pgtp` except `Save pgtp` and `Save as new pgtp`** (plus
    `Deploy .pgtp`'s outward push, patched here).

    Every other entry is triggered — including the four that are hidden on this
    tab, which is precisely how the deleted router's `else` used to be reached —
    and `save_project` must stay untouched. A future entry wired to the wrong
    writer fails here rather than silently writing the project file.
    """
    window = _window(qtbot, tmp_path)
    others = [
        "Compare/Merge pgtp",
        "Deploy .pgtp",
        "Save in Project",
        "Check and commit to sandbox",
        "Apply to quality",
        "Save XSD",
        "Save PHP File",
    ]
    with patch.object(window._doc_ui, "save_project") as save_project, patch.object(
        window._doc_ui, "save_as"
    ) as save_as, patch.object(window._diff_ui, "compare_two_files"), patch.object(
        window._ddl_project_ui, "deploy_pgtp"
    ), patch.object(
        window._xsd_ui, "save"
    ):
        for label in others:
            find_action(_menu(window), label).trigger()
    assert save_project.call_count == 0
    assert save_as.call_count == 0


def test_a_php_tab_cannot_reach_the_pgtp_writers(qtbot, tmp_path):
    """The wrong-target failure the router had, checked from the other side: on
    a PHP tab the two `.pgtp` writers are not merely un-triggered, they are not
    on offer at all."""
    window = _window(qtbot, tmp_path)
    path = tmp_path / "x.php"
    path.write_text("<?php", encoding="utf-8")
    window._php_tabs.open_path(path)
    for label in ("Save pgtp", "Save as new pgtp", "Deploy .pgtp"):
        assert find_action(_menu(window), label).isVisible() is False


def test_save_php_file_off_a_php_tab_writes_nothing(qtbot, tmp_path):
    """The classifier's "none" case reached at the WRITER: with no PHP tab
    active the controller returns False instead of falling through to some other
    buffer."""
    window = _window(qtbot, tmp_path)
    path = tmp_path / "x.php"
    path.write_text("<?php", encoding="utf-8")
    window._php_tabs.open_path(path)
    window.center_stage.setCurrentIndex(window.center_stage.raw_xml_tab_index)

    assert window._php_tabs.save_active_tab() is False
    assert path.read_text(encoding="utf-8") == "<?php"


def test_run_on_sandbox_off_a_ddl_tab_reports_instead_of_no_opping(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    find_action(_menu(window), "Check and commit to sandbox").trigger()
    assert "Check and commit to sandbox runs on an open DDL object tab" in (
        window.statusBar().currentMessage()
    )


def test_run_on_quality_off_a_ddl_tab_reports_before_touching_a_database(
    qtbot, tmp_path, monkeypatch
):
    """The missing tab is reported BEFORE any target is resolved — an outward
    push must not prompt for a password, or connect, to discover it has nothing
    to send."""
    window = _window(qtbot, tmp_path)
    monkeypatch.setattr(
        modals.QInputDialog,
        "getText",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("prompted"))),
    )
    find_action(_menu(window), "Apply to quality").trigger()
    assert "Apply to quality runs on an open DDL object tab" in (
        window.statusBar().currentMessage()
    )


def test_run_on_sandbox_with_no_session_states_the_reason(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._on_ddl_edit_requested(_REF, _SOURCE)
    find_action(_menu(window), "Check and commit to sandbox").trigger()
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("Check and commit to sandbox is unavailable" in line for line in lines)
    # The reason is the destination picker's sentence, which names neither the
    # deleted `Open Sandbox Session` entry nor the deleted `Sandbox Setup…` one.
    assert any("no sandbox session is open" in line for line in lines)
    assert not any("Open Sandbox Session" in line for line in lines)
    # Under `[Check]`, the existing apply/ladder channel -- no new prefix.
    assert all(line.startswith("[Check] ") for line in lines)


# -- `Apply to quality`, projectless (§18.5, owner ruling) ---------------------


def _projectless_quality_window(qtbot, tmp_path, monkeypatch, password="secret"):
    """A window with NO project, a `.pgtp` whose `<ConnectionOptions>` names the
    quality target, and an open object tab -- the owner's fast-bugfix scenario."""
    window = _window(qtbot, tmp_path)
    window._current_project = _pgtp_with_connection()
    assert window._ddl_project_settings is None  # projectless, by construction
    monkeypatch.setattr(
        modals.QInputDialog,
        "getText",
        staticmethod(lambda *a, **k: (password, bool(password))),
    )
    monkeypatch.setattr(
        window,
        "_fetch_ddl_schema",
        lambda params: DatabaseSchema(
            routines={
                "pr.recalc()": RoutineInfo(schema="pr", name="recalc", arg_types=[])
            }
        ),
    )
    window._on_ddl_edit_requested(_REF, _SOURCE)
    return window, window.center_stage.ddl_object_tab(_REF.key)


def test_run_on_quality_is_offered_projectless(qtbot, tmp_path, monkeypatch):
    """The owner's deliberate posture change, reaffirmed after being challenged:
    open a `.pgtp` with no project, edit an object, push it straight to quality.
    Projectless the target is DERIVED (`seed_params` merges the app-level saved
    connection with the `.pgtp`'s `<ConnectionOptions>`)."""
    window, panel = _projectless_quality_window(qtbot, tmp_path, monkeypatch)
    assert panel.has_target_apply is True
    action = find_action(_menu(window), "Apply to quality")
    assert action.isVisible() is True


def test_the_quality_confirmation_names_the_database_AND_the_host(
    qtbot, tmp_path, monkeypatch
):
    """The seam's own docstring has always documented `"prod on db01:5432"`, but
    both shipped label providers returned the bare database name. It matters most
    projectless, where the target is derived and the user may not know which
    server it resolved to -- writing DDL to the wrong server is the failure mode.
    """
    window, panel = _projectless_quality_window(qtbot, tmp_path, monkeypatch)
    assert window._target_database_label() == "prod on db01:5432"

    seen = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(
            lambda parent, title, text, *a, **k: seen.append((title, text))
            or modals.QMessageBox.StandardButton.No
        ),
    )
    panel.apply_to_target()
    # Precondition 2's override comes first (the buffer was never checked), then
    # the apply confirmation -- both name the resolved destination.
    assert seen
    assert all("prod on db01:5432" in text for _title, text in seen)


def test_the_sandbox_confirmation_also_names_the_host_now(qtbot, tmp_path):
    """The same drift, fixed on both labels in one pass (`_sandbox_database_label`
    documented the host format and did not produce it)."""
    window = _window(qtbot, tmp_path)
    from pgtp_editor.db.ddl_project import ProjectSettings, save_settings
    from pgtp_editor.db.sandbox import SandboxCapabilities

    project_dir = tmp_path / "proj"
    settings = ProjectSettings(
        sandbox=ConnectionParams(host="localhost", port="5433", database="sbox")
    )
    save_settings(project_dir, settings)
    # Opening a project starts an off-thread capability probe AND, because this
    # project's sandbox names a `database`, BUG-040's automatic `open_session`.
    # `_window` makes both synchronous via `window._run_async`; this test only
    # has to stop the probe reaching a real server. It used to stub
    # `window._ddl_project_ui._run_async` by hand, which covered the probe and
    # not the session -- see BUG-043, and `_window`'s comment.
    window._ddl_project_ui.probe_sandbox_capabilities = (
        lambda params: SandboxCapabilities(is_superuser=True)
    )
    # The probe passing means `open_session` proceeds to `_opener`, which is the
    # real `db/sandbox.py::open_sandbox` -- the thing that was actually dialling
    # localhost:5433. Now that the lane is synchronous the dial would merely
    # block this test instead of poisoning a later one; stub it so no test in
    # this file reaches a server at all.
    window.sandbox_controller._opener = lambda params, **kwargs: fake_session(params)
    window._ddl_project_ui.set_active_project(project_dir, settings)
    assert window._sandbox_database_label() == "sbox on localhost:5433"


def test_a_projectless_quality_apply_runs_and_reports_under_check(
    qtbot, tmp_path, monkeypatch
):
    """The write goes through `db/apply.py::apply_ddl` -- the ONE write seam --
    off the GUI thread, and the outcome lands in the Audit panel under the
    existing `[Check]` prefix naming object + database + host, so a projectless
    session still leaves a record where the user already looks."""
    window, panel = _projectless_quality_window(qtbot, tmp_path, monkeypatch)
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.Yes),
    )
    applied = []

    def fake_apply_ddl(params, statements):
        from pgtp_editor.db.apply import ApplyOutcome

        applied.append((params, list(statements)))
        return ApplyOutcome.succeeded((), committed=True)

    monkeypatch.setattr("pgtp_editor.ui.main_window.apply_ddl", fake_apply_ddl)
    # Synchronous stand-in for the off-thread runner, the project's convention.
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.run_async",
        lambda parent, work, on_result, on_error=None: on_result(work()),
    )

    window.center_stage.setCurrentWidget(panel)
    find_action(_menu(window), "Apply to quality").trigger()

    assert len(applied) == 1
    params, statements = applied[0]
    assert (params.host, params.database, params.password) == (
        "db01",
        "prod",
        "secret",
    )
    assert statements == [panel.text()]
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any(
        "applied pr.recalc() to quality database prod on db01:5432." in line
        for line in lines
    )
    assert all(line.startswith("[Check] ") for line in lines)


def test_a_projectless_password_is_session_only_and_never_persisted(
    qtbot, tmp_path, monkeypatch
):
    """Verified prerequisite, not a caveat: `_target_params_for_fetch`
    short-circuits projectless (BUG-034's prompt is project-only) and
    `connection_from_tree` forces `password=""`, so without a prompt the apply
    would fail on authentication AFTER a confirmation that named a production
    host — the worst of the three outcomes.

    The prompt is therefore raised here, and its answer is kept **in memory for
    this session only**: there is no `.ddlproject/settings.json` to persist into,
    and writing it into the app-level QSettings store would be exactly the
    silently-substituted-credential confusion BUG-034 was about.
    """
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._current_project = _pgtp_with_connection()
    prompts = []
    monkeypatch.setattr(
        modals.QInputDialog,
        "getText",
        staticmethod(lambda *a, **k: prompts.append(a) or ("secret", True)),
    )

    assert window._target_params_for_apply().password == "secret"
    # Asked ONCE; the second resolution reuses the session-held answer.
    assert window._target_params_for_apply().password == "secret"
    assert len(prompts) == 1

    settings.sync()
    stored = " ".join(
        str(settings.value(key)) for key in settings.allKeys()
    )
    assert "secret" not in stored

    # A second window shares nothing -- the class-level default is None, never a
    # mutable dict that would hand one window's secrets to the next.
    other = MainWindow(settings=settings)
    qtbot.addWidget(other)
    assert other._session_target_passwords is None


def test_a_cancelled_password_prompt_refuses_BEFORE_the_confirmation(
    qtbot, tmp_path, monkeypatch
):
    """The stated refusal the spec demands as the alternative to a prompt.
    Nothing may be confirmed, and no connection may be attempted, when there is
    no password to connect with."""
    window, panel = _projectless_quality_window(
        qtbot, tmp_path, monkeypatch, password=""
    )
    confirmations = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(
            lambda *a, **k: confirmations.append(a)
            or modals.QMessageBox.StandardButton.Yes
        ),
    )
    applied = []
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.apply_ddl",
        lambda params, statements: applied.append(params),
    )

    window.center_stage.setCurrentWidget(panel)
    find_action(_menu(window), "Apply to quality").trigger()

    assert applied == []
    assert confirmations == []
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("no quality target with a password is available" in l for l in lines)


def _mismatched_live_catalog(window, monkeypatch):
    """Make the live catalog hold `pr.recalc(integer)` while the open tab's
    buffer declares `pr.recalc()` -- the renamed/signature-changed case."""
    monkeypatch.setattr(
        window,
        "_fetch_ddl_schema",
        lambda params: DatabaseSchema(
            routines={
                "pr.recalc(integer)": RoutineInfo(
                    schema="pr", name="recalc", arg_types=["integer"]
                )
            }
        ),
    )


def test_a_changed_signature_warns_and_then_runs_the_sql_projectless(
    qtbot, tmp_path, monkeypatch
):
    """BUG-260810193333, end to end on the wired leg. Owner ruling 2026-08-10:
    *"trust the user that they know what they are doing, run the sql."*

    This used to be the one gate with no override -- and that is exactly what
    made `Apply to quality` look like it succeeded and do nothing while `Check
    and commit to sandbox` ran the same buffer. It is now a confirm-gated
    override; the write seam really is reached.
    """
    window, panel = _projectless_quality_window(qtbot, tmp_path, monkeypatch)
    _mismatched_live_catalog(window, monkeypatch)
    applied = []

    def fake_apply_ddl(params, statements):
        from pgtp_editor.db.apply import ApplyOutcome

        applied.append(params)
        return ApplyOutcome.succeeded((), committed=True)

    monkeypatch.setattr("pgtp_editor.ui.main_window.apply_ddl", fake_apply_ddl)
    # Synchronous stand-in for the off-thread runner, the project's convention.
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.run_async",
        lambda parent, work, on_result, on_error=None: on_result(work()),
    )
    seen = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(
            lambda parent, title, text, *a, **k: seen.append((title, text))
            or modals.QMessageBox.StandardButton.Yes
        ),
    )

    assert panel.apply_to_target() is True

    assert applied, "the buffer's SQL must actually reach the target"
    # The mismatch is put FIRST, before precondition 2's override, and it names
    # both identities plus the second-object consequence.
    _title, text = seen[0]
    assert "pr.recalc()" in text and "pr.recalc(integer)" in text
    assert "second object" in text.lower()
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("proceeding despite identity mismatch" in line for line in lines)


def test_declining_the_signature_warning_applies_nothing_and_is_not_silent(
    qtbot, tmp_path, monkeypatch
):
    """The other half of the ruling: a declined warning aborts -- but SAYS so.
    A deploy gesture that returns without a trace is the defect this fixed."""
    window, panel = _projectless_quality_window(qtbot, tmp_path, monkeypatch)
    _mismatched_live_catalog(window, monkeypatch)
    applied = []
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.apply_ddl",
        lambda params, statements: applied.append(params),
    )
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.No),
    )

    assert panel.apply_to_target() is False

    assert applied == []
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("cancelled at the signature mismatch" in line for line in lines)


def test_an_unreadable_catalog_is_a_refusal_never_a_cleared_precondition(
    qtbot, tmp_path, monkeypatch
):
    """`live_identity` must RAISE on a lookup failure. Reporting it as `None`
    would read as *"the target does not have this object"* and silently clear
    precondition 1 against an unreachable database."""
    window, panel = _projectless_quality_window(qtbot, tmp_path, monkeypatch)

    def boom(params):
        raise OSError("connection refused")

    monkeypatch.setattr(window, "_fetch_ddl_schema", boom)
    applied = []
    monkeypatch.setattr(
        "pgtp_editor.ui.main_window.apply_ddl",
        lambda params, statements: applied.append(params),
    )

    assert panel.apply_to_target() is False
    assert applied == []
    lines = [
        window.audit_panel.item(i).text() for i in range(window.audit_panel.count())
    ]
    assert any("could not read the live object's identity" in line for line in lines)
