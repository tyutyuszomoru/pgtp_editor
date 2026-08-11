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
"""BUG-060 — Find All reaches an output surface from EVERY editor tab.

Find All was born as an injected callback, and only two bars were ever wired
(Raw XML, Edit XSD). On the DDL Explorer buffer, an editable DDL object tab, a
§21 PHP tab and an FQ-006 draft fragment the button computed nothing and
appended nothing: a search that appeared to do literally nothing.

What this module pins:

* the results land on the **left-dock Findings tab**, via the same `[Find]`
  prefix and the same `AuditRouter` the Raw XML run always used -- no new
  prefix, no new panel, no second results route;
* an **unwired** bar publishes its request and the find lane answers it
  (`find_replace_bar.add_find_all_observer`), which is what makes a tab kind
  created at runtime work without a per-tab wiring line in the host;
* the row payload comes from `_bookmark_audit_route`, i.e. the SAME table
  `List All Bookmarks` uses -- so `[Find]` and `[Bookmark]` rows cannot
  disagree about which document a row describes. Concretely: a DDL object row
  carries its `DdlObjectRef.key` tuple, a PHP row carries §22's pair, a
  read-only Explorer row carries `DDL_EXPLORER_AUDIT_TARGET` plus its Explorer
  role (BUG-260811232724 -- it used to be inert, see the test that supersedes
  that one), and a draft fragment still gets **roles-less, inert** rows (§7's
  unmapped-line rule -- the router's fallback is Raw XML);
* a **wired** bar still uses its callback and never publishes, so one click
  can never start two runs.
"""
from PySide6.QtCore import Qt

from pgtp_editor.lint.findings import LINT_AUDIT_TARGET
from pgtp_editor.ui.center_stage import DDL_EXPLORER_SANDBOX, DDL_EXPLORER_TARGET
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.find_controller import DDL_EXPLORER_AUDIT_TARGET
from pgtp_editor.ui.main_window import MainWindow

_LINE = Qt.ItemDataRole.UserRole
_TARGET = Qt.ItemDataRole.UserRole + 1
_EXTRA = Qt.ItemDataRole.UserRole + 2


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    return window


def _run(qtbot, bar, term):
    """Drive the REAL button, which is the half that was broken."""
    bar.set_find_text(term)
    bar._find_all_button.click()
    qtbot.waitUntil(lambda: not bar._find_all_running, timeout=5000)


def _findings(window):
    return window.findings_panel.row_texts()


def _rows(window):
    audit = window.audit_panel
    return [audit.item(row) for row in range(audit.count())]


# --- the destination --------------------------------------------------------


def test_a_ddl_object_tabs_find_all_lands_on_the_findings_tab(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    panel = window.center_stage.open_ddl_object_tab(ref, "alpha\nbeta alpha\n")

    _run(qtbot, panel.find_replace_bar, "alpha")

    # The `[Find]` prefix routes to the left-dock Findings tab (FQ-028's
    # disposition table) -- the surface the Raw XML run already used.
    assert _findings(window) == [
        "[Find] line 1: alpha",
        "[Find] line 2: beta alpha",
        '[Find] 2 match(es) for "alpha"',
    ]
    # Nothing leaked onto the accumulating Messages tab.
    assert not any(text.startswith("[Find]") for text in window.results_panel.row_texts())


def test_a_ddl_object_row_carries_its_ref_key_and_navigates_that_tab(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    panel = window.center_stage.open_ddl_object_tab(ref, "alpha\nbeta\ngamma alpha\n")
    stage = window.center_stage
    stage.setCurrentIndex(stage.raw_xml_tab_index)  # look away from the tab

    _run(qtbot, panel.find_replace_bar, "gamma")

    row = _rows(window)[0]
    assert (row.data(_LINE), row.data(_TARGET)) == (3, ref.key)
    assert isinstance(row.data(_TARGET), tuple)  # §18.5 D3a's routing shape

    window._on_audit_item_clicked(row)

    assert stage.currentWidget() is panel
    assert panel.editor.textCursor().blockNumber() == 2


def test_a_php_tabs_find_all_carries_the_php_target_and_its_tab_key(qtbot, tmp_path):
    """§22's payload is a PAIR; omitting the `UserRole+2` key would make every
    PHP row inert."""
    window = _window(qtbot, tmp_path)
    path = tmp_path / "hooks.php"
    path.write_text("<?php\n$alpha = 1;\n", encoding="utf-8")
    tab = window.center_stage.open_php_file_tab(path, "<?php\n$alpha = 1;\n")

    _run(qtbot, tab.find_replace_bar, "alpha")

    row = _rows(window)[0]
    assert row.data(_TARGET) == LINT_AUDIT_TARGET
    assert row.data(_EXTRA) == window.center_stage.php_file_tab_key(tab)
    assert row.data(_LINE) == 2


def test_the_ddl_explorer_buffer_rows_navigate_that_explorer_tab(qtbot, tmp_path):
    """SUPERSEDES `test_the_ddl_explorer_buffer_reports_matches_as_inert_rows`
    (BUG-260811232724).

    BUG-060 left this buffer's rows deliberately roles-less and inert, because
    the router's fallback navigates **Raw XML** and there was NO branch that
    could resolve a row to the read-only `EditorPanel` -- so a routed row would
    have carried the user to a different document (§7's unmapped-line rule).
    That reasoning was about the missing branch, not about the pane: the branch
    now exists, so the rows carry `DDL_EXPLORER_AUDIT_TARGET` plus their
    Explorer **role**, and clicking one moves the caret in that Explorer's own
    buffer -- the same behavior every other Find-All surface has.
    """
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    stage.xml_editor.setPlainText("raw one\nraw two\nraw three")
    stage.show_ddl_explorer()
    panel = stage.ddl_editor_panel
    panel.editor.setPlainText("one\ntwo alpha\nthree")
    stage.setCurrentIndex(stage.raw_xml_tab_index)  # look away from the tab

    _run(qtbot, panel.find_replace_bar, "alpha")

    assert _findings(window) == [
        "[Find] line 2: two alpha",
        '[Find] 1 match(es) for "alpha"',
    ]
    row = _rows(window)[0]
    assert row.data(_LINE) == 2
    assert row.data(_TARGET) == DDL_EXPLORER_AUDIT_TARGET
    assert row.data(_EXTRA) == DDL_EXPLORER_TARGET

    window._on_audit_item_clicked(row)

    assert stage.currentIndex() == stage.ddl_tab_index  # never yanked to Raw XML
    assert panel.editor.textCursor().blockNumber() == 1  # the caret really moved
    assert stage.xml_editor.textCursor().blockNumber() == 0


def test_the_sandbox_explorer_row_navigates_the_sandbox_buffer_not_quality(
    qtbot, tmp_path
):
    """The role RIDES on the row (§18.7): the two Explorer buffers are different
    documents with independent line numbering, so a row found in Sandbox must
    never resolve against whichever Explorer happens to be current."""
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    stage.show_ddl_explorer(DDL_EXPLORER_TARGET)
    stage.show_ddl_explorer(DDL_EXPLORER_SANDBOX)
    quality = stage.ddl_explorer_panel(DDL_EXPLORER_TARGET)
    quality.editor.setPlainText("quality one\nquality two\nquality three")
    sandbox = stage.ddl_explorer_panel(DDL_EXPLORER_SANDBOX)
    sandbox.editor.setPlainText("s one\ns two\ns three alpha")
    stage.setCurrentIndex(stage.ddl_tab_index)  # the OTHER Explorer is current

    _run(qtbot, sandbox.find_replace_bar, "alpha")

    row = _rows(window)[0]
    assert (row.data(_LINE), row.data(_EXTRA)) == (3, DDL_EXPLORER_SANDBOX)

    window._on_audit_item_clicked(row)

    assert stage.currentIndex() == stage.ddl_explorer_tab_index(DDL_EXPLORER_SANDBOX)
    assert sandbox.editor.textCursor().blockNumber() == 2
    assert quality.editor.textCursor().blockNumber() == 0  # untouched


def test_a_draft_fragment_tabs_find_all_reports_inert_rows(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    draft = window.center_stage.open_draft_fragment_tab(
        "trigger", "pr.equipment", "alpha\nbeta\n"
    )

    _run(qtbot, draft.find_replace_bar, "alpha")

    assert _findings(window) == [
        "[Find] line 1: alpha",
        '[Find] 1 match(es) for "alpha"',
    ]
    assert _rows(window)[0].data(_LINE) is None


# --- the seam ---------------------------------------------------------------


def test_an_unwired_bar_publishes_and_a_wired_one_does_not(qtbot, tmp_path):
    """The two bars the host wires by hand keep their callback; every other bar
    reaches the find lane by publishing. If a wired bar published too, one
    click would start the run twice."""
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    panel = window.center_stage.open_ddl_object_tab(ref, "alpha\n")

    assert window.center_stage.find_replace_bar._on_find_all is not None
    assert window.center_stage.xsd_find_replace_bar._on_find_all is not None
    assert panel.find_replace_bar._on_find_all is None

    published = []
    window._find_ui.find_all_in_bar = lambda bar, term: published.append((bar, term))

    window.center_stage.find_replace_bar.set_find_text("alpha")
    window.center_stage.find_replace_bar._find_all_button.click()
    qtbot.waitUntil(
        lambda: not window.center_stage.find_replace_bar._find_all_running, timeout=5000
    )

    assert published == []  # the wired bar went through its callback


def test_the_button_stops_an_in_flight_run_from_an_unwired_bar(qtbot, tmp_path):
    """`Stop` is the same button, and it was as unwired as `Find All`."""
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    panel = window.center_stage.open_ddl_object_tab(ref, "a\n" * 900)
    bar = panel.find_replace_bar

    bar.set_find_text("a")
    bar._find_all_button.click()
    window._find_ui.find_all_timer.stop()
    window._find_ui._find_all_step()  # exactly one batch
    partial = window._find_ui.find_all_count
    assert 0 < partial < 900
    assert bar._find_all_button.text() == "Stop"

    bar._find_all_button.click()  # the Stop press, from the same unwired bar
    window._find_ui._find_all_step()  # observes the stop flag -> finishes

    assert bar._find_all_running is False
    assert bar._find_all_button.text() == "Find All"
    assert window._find_ui.find_all_count == partial


def test_the_run_returns_the_pressed_bars_button_not_the_raw_xml_one(qtbot, tmp_path):
    """With per-tab bars there is no mapping from a target back to a bar, so the
    finished run has to restore the button that was pressed."""
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    panel = window.center_stage.open_ddl_object_tab(ref, "alpha\n")

    _run(qtbot, panel.find_replace_bar, "alpha")

    assert panel.find_replace_bar._find_all_button.text() == "Find All"
    assert window.center_stage.find_replace_bar._find_all_button.text() == "Find All"


def test_a_second_run_from_another_tab_replaces_the_previous_rows(qtbot, tmp_path):
    """Clear-on-rerun is per PREFIX, not per tab: the Findings tab answers one
    question at a time (FQ-028's last-operation-wins)."""
    window = _window(qtbot, tmp_path)
    first = window.center_stage.open_ddl_object_tab(
        DdlObjectRef(kind="function", schema="pr", name="one"), "alpha\n"
    )
    second = window.center_stage.open_ddl_object_tab(
        DdlObjectRef(kind="function", schema="pr", name="two"), "beta\nbeta\n"
    )

    _run(qtbot, first.find_replace_bar, "alpha")
    _run(qtbot, second.find_replace_bar, "beta")

    assert _findings(window) == [
        "[Find] line 1: beta",
        "[Find] line 2: beta",
        '[Find] 2 match(es) for "beta"',
    ]


def test_the_raw_xml_and_xsd_targets_still_route_as_before(qtbot, tmp_path):
    """The two hand-wired tabs are untouched by the generalization: same target
    strings, same click routes."""
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    stage.xml_editor.setPlainText("alpha\nbeta")

    window._find_ui.find_all("alpha")
    qtbot.waitUntil(lambda: not stage.find_replace_bar._find_all_running, timeout=5000)

    row = _rows(window)[0]
    assert (row.data(_LINE), row.data(_TARGET)) == (1, "raw")
    assert window._find_ui.find_all_target == "raw"
