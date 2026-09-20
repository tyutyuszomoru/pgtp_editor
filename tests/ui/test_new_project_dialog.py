# tests/ui/test_new_project_dialog.py
"""Tests for NewProjectDialog (§18.2) — driven entirely by methods.

The dialog is never `.exec()`-ed (modal-hang guardrail); the sandbox Test
calls an injected prober stub, so no real connection is ever opened. The
folder picker is exercised by driving the underlying line edit / accept
logic rather than a real QFileDialog popup.
"""
from PySide6.QtWidgets import QLabel

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import GitConfig
from pgtp_editor.db.sandbox import SandboxCapabilities, SandboxMode
from pgtp_editor.ui.new_project_dialog import NewProjectDialog
from pgtp_editor.ui.status_colours import STATUS_ERROR, STATUS_OK


def _sync_run(fn, on_result, on_error=None):
    """Synchronous stand-in for run_async (same seam style as
    test_connection_setup_dialog.py)."""
    try:
        on_result(fn())
    except Exception as exc:  # noqa: BLE001
        (on_error or (lambda _e: None))(exc)


def test_name_and_description_round_trip(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._name_edit.setText("ERP overhaul")
    dialog._description_edit.setText("Q3 checkout")
    assert dialog.name() == "ERP overhaul"
    assert dialog.description() == "Q3 checkout"


def test_folder_starts_empty(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog.folder() == ""


def test_browse_for_folder_sets_the_field(qtbot, tmp_path, monkeypatch):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "pgtp_editor.ui.new_project_dialog.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(tmp_path)),
    )

    dialog._browse_for_folder()

    assert dialog.folder() == str(tmp_path)


def test_cancelling_the_folder_picker_leaves_the_field_untouched(qtbot, monkeypatch):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText("/already/chosen")
    monkeypatch.setattr(
        "pgtp_editor.ui.new_project_dialog.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: ""),  # Cancel
    )

    dialog._browse_for_folder()

    assert dialog.folder() == "/already/chosen"


def test_accept_without_a_folder_shows_an_error_and_does_not_close(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == []
    assert "folder" in dialog._folder_error_label.text().lower()


def test_accept_with_a_folder_closes_normally(qtbot, tmp_path):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path))
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == [True]


# --- Sandbox connection fields + superuser Test -----------------------------
def test_sandbox_params_round_trip(qtbot):
    """FQ-007: the server connection round-trips, and `database` is EMPTY --
    there is no field for it, because the app creates the database itself."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("localhost")
    dialog._sandbox_port_edit.setText("5432")
    dialog._sandbox_user_edit.setText("dev")
    dialog._sandbox_password_edit.setText("pw")

    params = dialog.sandbox_params()

    assert params == ConnectionParams(
        host="localhost", port="5432", database="", user="dev", password="pw"
    )
    assert not hasattr(dialog, "_sandbox_database_edit")


def test_sandbox_password_field_uses_password_echo_mode(qtbot):
    from PySide6.QtWidgets import QLineEdit

    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog._sandbox_password_edit.echoMode() == QLineEdit.EchoMode.Password


def test_test_sandbox_reports_superuser(qtbot):
    dialog = NewProjectDialog(prober=lambda params: SandboxCapabilities(is_superuser=True))
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "superuser" in dialog._sandbox_status_label.text().lower()
    assert "not a superuser" not in dialog._sandbox_status_label.text().lower()
    assert dialog._sandbox_test_button.isEnabled()


def test_test_sandbox_reports_connected_but_not_superuser(qtbot):
    dialog = NewProjectDialog(prober=lambda params: SandboxCapabilities(is_superuser=False))
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "not a superuser" in dialog._sandbox_status_label.text().lower()
    assert "create extension" in dialog._sandbox_status_label.text().lower()


def test_test_sandbox_reports_probe_error(qtbot):
    dialog = NewProjectDialog(
        prober=lambda params: SandboxCapabilities(probe_error="connection refused")
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "connection refused" in dialog._sandbox_status_label.text()


def test_test_sandbox_reports_an_exception_raised_by_the_prober(qtbot):
    def raising_prober(params):
        raise RuntimeError("no route to host")

    dialog = NewProjectDialog(prober=raising_prober)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "no route to host" in dialog._sandbox_status_label.text()
    assert dialog._sandbox_test_button.isEnabled()


def test_test_sandbox_shows_busy_status_then_result(qtbot):
    captured = {}

    def deferred(fn, on_result, on_error=None):
        captured["fn"] = fn
        captured["on_result"] = on_result

    dialog = NewProjectDialog(prober=lambda params: SandboxCapabilities(is_superuser=True))
    dialog._run_async = deferred
    qtbot.addWidget(dialog)

    dialog.test_sandbox()

    assert "testing" in dialog._sandbox_status_label.text().lower()
    assert not dialog._sandbox_test_button.isEnabled()

    captured["on_result"](captured["fn"]())
    assert "superuser" in dialog._sandbox_status_label.text().lower()
    assert dialog._sandbox_test_button.isEnabled()


def test_uses_the_passed_params_not_stale_ones(qtbot):
    seen = []

    def prober(params):
        seen.append(params)
        return SandboxCapabilities(is_superuser=True)

    dialog = NewProjectDialog(prober=prober)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._sandbox_host_edit.setText("myhost")

    dialog.test_sandbox()

    assert seen[0].host == "myhost"


# --- "with data" / "without data" sandbox clone choice (§18.5 D2a) ----------
def test_sandbox_mode_defaults_to_schema_only(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog.sandbox_mode() == SandboxMode.SCHEMA_ONLY


def test_selecting_with_data_radio_changes_sandbox_mode(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog._sandbox_with_data_radio.setChecked(True)

    assert dialog.sandbox_mode() == SandboxMode.WITH_DATA


def test_reselecting_without_data_radio_reverts_sandbox_mode(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._sandbox_with_data_radio.setChecked(True)

    dialog._sandbox_without_data_radio.setChecked(True)

    assert dialog.sandbox_mode() == SandboxMode.SCHEMA_ONLY


def test_sandbox_mode_radios_are_mutually_exclusive(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog._sandbox_with_data_radio.setChecked(True)

    assert not dialog._sandbox_without_data_radio.isChecked()


def test_with_data_caveat_mentions_one_shot_and_pg_dump_restore(qtbot):
    """§18.5 D2a: cloning is one-shot -- no refresh operation -- and needs
    pg_dump/pg_restore. The dialog must state this, not bury it."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    labels = [child.text() for child in dialog.findChildren(QLabel)]
    combined = " ".join(labels).lower()
    assert "pg_dump" in combined
    assert "pg_restore" in combined
    assert "one-shot" in combined or "destroy and recreate" in combined


def test_test_sandbox_with_data_mode_and_tools_present_reports_superuser(qtbot):
    dialog = NewProjectDialog(
        prober=lambda params: SandboxCapabilities(
            is_superuser=True, pg_dump_path="/usr/bin/pg_dump", pg_restore_path="/usr/bin/pg_restore"
        )
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._sandbox_with_data_radio.setChecked(True)

    dialog.test_sandbox()

    assert "superuser" in dialog._sandbox_status_label.text().lower()
    assert "not found" not in dialog._sandbox_status_label.text().lower()


def test_test_sandbox_with_data_mode_and_missing_tools_reports_named_failure(qtbot):
    """A missing pg_dump/pg_restore must be a named, surfaced failure --
    never silently accepted as if schema-only would kick in instead."""
    dialog = NewProjectDialog(
        prober=lambda params: SandboxCapabilities(
            is_superuser=True, pg_dump_path=None, pg_restore_path=None
        )
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._sandbox_with_data_radio.setChecked(True)

    dialog.test_sandbox()

    status = dialog._sandbox_status_label.text().lower()
    assert "pg_dump" in status
    assert "pg_restore" in status
    assert "not found" in status


def test_test_sandbox_without_data_mode_ignores_missing_clone_tools(qtbot):
    """Schema-only mode needs neither pg_dump nor pg_restore -- a missing
    binary must not be reported as a blocker when "without data" is chosen."""
    dialog = NewProjectDialog(
        prober=lambda params: SandboxCapabilities(
            is_superuser=True, pg_dump_path=None, pg_restore_path=None
        )
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    assert dialog.sandbox_mode() == SandboxMode.SCHEMA_ONLY

    dialog.test_sandbox()

    status = dialog._sandbox_status_label.text().lower()
    assert "superuser" in status
    assert "pg_dump" not in status


# --- Git fields: captured, inert ---------------------------------------------
def test_git_config_round_trips(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._git_server_edit.setText("git.example.com")
    dialog._git_user_edit.setText("dev")
    dialog._git_branch_edit.setText("feature/x")

    assert dialog.git_config() == GitConfig(
        server="git.example.com", user="dev", checkout_branch="feature/x"
    )


def test_git_config_defaults_to_empty(qtbot):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog.git_config() == GitConfig()


def test_git_section_states_it_is_not_yet_used(qtbot):
    """§18.2: git is optional/TBD -- the dialog must not imply otherwise."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    labels = [child.text() for child in dialog.findChildren(QLabel)]
    assert any("not yet" in text.lower() or "later" in text.lower() for text in labels)


# --- The `.pgtp` attach field and the quality section it reveals (FQ-035) -----
_PGTP_WITH_TWO_CONNECTION_ELEMENTS = """<?xml version="1.0" encoding="UTF-8"?>
<PGTPProject>
  <ConnectionOptions host="quality.example.com" port="1111" database="erp"
      login="app_user" password="KZG;MOOYZ^OQ]^C]\\?FVH*K;"/>
  <ScriptConnectionOptions host="script.example.com" port="5579" database="script_db"
      login="script_user" password="KZG;MOOYZ^OQ]^C]\\?FVH*K;"/>
</PGTPProject>
"""


def _pgtp_file(tmp_path, text=_PGTP_WITH_TWO_CONNECTION_ELEMENTS, name="checkout.pgtp"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_pgtp_field_starts_empty_and_the_quality_section_is_hidden(qtbot):
    """§7's rule: with no `.pgtp` there is nothing to populate the quality
    section from, so it is HIDDEN -- not a disabled control being denied."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    assert dialog.pgtp_path() == ""
    assert dialog._quality_group.isVisibleTo(dialog) is False
    assert dialog.target_params() == ConnectionParams()


def test_browse_for_pgtp_uses_an_open_file_dialog_and_reveals_the_section(
    qtbot, tmp_path, monkeypatch
):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    path = _pgtp_file(tmp_path)
    seen = []
    monkeypatch.setattr(
        "pgtp_editor.ui.new_project_dialog.QFileDialog.getOpenFileName",
        staticmethod(lambda *a, **k: seen.append(a) or (path, "")),
    )

    dialog._browse_for_pgtp()

    assert seen, "the attach field must open a FILE dialog, not a folder one"
    assert dialog.pgtp_path() == path
    assert dialog._quality_group.isVisibleTo(dialog) is True


def test_cancelling_the_pgtp_picker_leaves_the_field_and_section_untouched(
    qtbot, monkeypatch
):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "pgtp_editor.ui.new_project_dialog.QFileDialog.getOpenFileName",
        staticmethod(lambda *a, **k: ("", "")),  # Cancel
    )

    dialog._browse_for_pgtp()

    assert dialog.pgtp_path() == ""
    assert dialog._quality_group.isVisibleTo(dialog) is False


def test_attaching_a_pgtp_populates_the_quality_fields_from_connectionoptions(
    qtbot, tmp_path
):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    assert dialog.target_params() == ConnectionParams(
        host="quality.example.com",
        port="1111",
        database="erp",
        user="app_user",
        password="",  # never in the XML -- the user supplies it
    )


def test_attaching_a_pgtp_never_reads_scriptconnectionoptions(qtbot, tmp_path):
    """The vendor writes a second element with a DIFFERENT port (5579 vs 1111);
    picking between two candidates would be a guess about which database a
    project points at."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    params = dialog.target_params()
    assert params.port == "1111"
    assert params.host == "quality.example.com"
    assert "script" not in params.database


def test_attaching_a_pgtp_never_seeds_the_sandbox(qtbot, tmp_path):
    """"That is how a sandbox ends up pointed at production" -- the two groups
    stay independent."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    assert dialog.sandbox_params() == ConnectionParams()


def test_the_quality_password_is_asked_for_and_survives_into_target_params(
    qtbot, tmp_path
):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    dialog._quality_password_edit.setText("typed-by-hand")

    assert dialog.target_params().password == "typed-by-hand"


def test_reattaching_a_different_pgtp_repopulates_rather_than_merges(qtbot, tmp_path):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog.set_pgtp_path(_pgtp_file(tmp_path))
    dialog._quality_password_edit.setText("stale")
    other = _pgtp_file(
        tmp_path,
        text=(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<PGTPProject><ConnectionOptions host="other.example.com" port="2222"'
            ' database="other" login="other_user"/></PGTPProject>\n'
        ),
        name="other.pgtp",
    )

    dialog.set_pgtp_path(other)

    assert dialog.target_params() == ConnectionParams(
        host="other.example.com", port="2222", database="other", user="other_user"
    )


def test_a_pgtp_without_connectionoptions_reveals_the_section_blank_with_a_note(
    qtbot, tmp_path
):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    dialog.set_pgtp_path(
        _pgtp_file(tmp_path, text="<PGTPProject/>\n", name="bare.pgtp")
    )

    assert dialog._quality_group.isVisibleTo(dialog) is True
    assert dialog.target_params() == ConnectionParams()
    assert "connectionoptions" in dialog._quality_status_label.text().lower()


def test_an_unparsable_pgtp_is_tolerated_like_the_open_time_linker(qtbot, tmp_path):
    """Tolerant, not an error dialog: the open-time linker swallows an
    unreadable source too, and the attach must not become an ambush."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    broken = _pgtp_file(tmp_path, text="<PGTPProject><unclosed>", name="broken.pgtp")

    dialog.set_pgtp_path(broken)

    assert dialog.pgtp_path() == broken
    assert dialog._quality_group.isVisibleTo(dialog) is True
    assert dialog.target_params() == ConnectionParams()


def test_attaching_a_pgtp_does_not_gate_accept(qtbot, tmp_path):
    """No gate was added: the quality section may be blank, partial or untested
    and accept must still succeed (DEC-260810134915: a gate here cannot be made
    honest, since the XML never yields the password)."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog.set_pgtp_path(_pgtp_file(tmp_path))
    dialog._quality_host_edit.setText("")
    dialog._quality_user_edit.setText("")
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == [True]


# --- The quality Test button: a DIFFERENT probe from the sandbox one ----------
def test_quality_test_uses_generic_connectivity_not_the_superuser_probe(
    qtbot, tmp_path
):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    probed = []
    tested = []
    dialog = NewProjectDialog(
        prober=lambda params: probed.append(params) or SandboxCapabilities(),
        tester=lambda params: tested.append(params) or (True, "Connected."),
    )
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    dialog.test_quality()

    assert probed == []  # a superuser demand would refuse a valid quality server
    assert len(tested) == 1
    assert tested[0].host == "quality.example.com"
    assert dialog._quality_status_label.text() == "Connected."
    assert dialog._quality_status_label.status_kind() == STATUS_OK


def test_quality_test_reports_a_failure_without_blocking_anything(qtbot, tmp_path):
    """Supersedes the literal `"green"`/`"red"` stylesheet assertion
    BUG-260812063745 removed: those CSS names were theme-blind (`green` 3.10:1
    on the dark chrome, `red` below 4.5:1 on BOTH). The verdict is a status
    KIND now; the colours it resolves to are proved as rendered pixels, in
    both themes and with a presence anchor, in `tests/ui/test_theme.py`.
    """
    dialog = NewProjectDialog(tester=lambda params: (False, "could not connect"))
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    dialog.test_quality()

    assert dialog._quality_status_label.text() == "could not connect"
    assert dialog._quality_status_label.status_kind() == STATUS_ERROR
    got = []
    dialog.accepted.connect(lambda: got.append(True))
    dialog._on_accept_clicked()
    assert got == [True]


def test_quality_test_surfaces_a_broken_seam_and_re_enables_the_button(qtbot, tmp_path):
    def boom(_params):
        raise RuntimeError("driver exploded")

    dialog = NewProjectDialog(tester=boom)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    dialog.test_quality()

    assert "driver exploded" in dialog._quality_status_label.text()
    assert dialog._quality_test_button.isEnabled() is True


# --- The accept-time advisory that stands in for the gate (DEC-260810134915) ---
def test_no_pgtp_means_no_advisory_at_all(qtbot):
    """The section was never shown, so there is no target being described -- a
    sandbox-only project is created as silently as before."""
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)

    assert dialog.quality_advisory() == ""


def test_a_blank_quality_connection_earns_the_advisory(qtbot, tmp_path):
    dialog = NewProjectDialog(connection_reader=lambda path: None)
    qtbot.addWidget(dialog)
    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    advisory = dialog.quality_advisory()

    assert "no quality (target) server" in advisory
    assert "Project Settings" in advisory  # says where to fix it


def test_a_filled_but_untested_quality_connection_earns_the_advisory(qtbot, tmp_path):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    advisory = dialog.quality_advisory()

    assert "never tested" in advisory
    assert "quality.example.com" in advisory  # names what it noticed


def test_any_answered_test_silences_the_advisory_green_or_red(qtbot, tmp_path):
    """A red result is read inline by the user; repeating it is noise, not a
    notice. Both answers count as "it was tried"."""
    for ok, message in ((True, "Connected."), (False, "could not connect")):
        dialog = NewProjectDialog(tester=lambda params: (ok, message))
        dialog._run_async = _sync_run
        qtbot.addWidget(dialog)
        dialog.set_pgtp_path(_pgtp_file(tmp_path))

        dialog.test_quality()

        assert dialog.quality_advisory() == ""


def test_a_broken_seam_also_counts_as_tried(qtbot, tmp_path):
    def boom(_params):
        raise RuntimeError("driver exploded")

    dialog = NewProjectDialog(tester=boom)
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog.set_pgtp_path(_pgtp_file(tmp_path))

    dialog.test_quality()

    assert dialog.quality_advisory() == ""


def test_re_attaching_a_different_pgtp_makes_the_earlier_test_stop_counting(
    qtbot, tmp_path
):
    """The fields were replaced, so the previous answer described a different
    connection."""
    dialog = NewProjectDialog(tester=lambda params: (True, "Connected."))
    dialog._run_async = _sync_run
    qtbot.addWidget(dialog)
    dialog.set_pgtp_path(_pgtp_file(tmp_path))
    dialog.test_quality()
    assert dialog.quality_advisory() == ""

    dialog.set_pgtp_path(
        _pgtp_file(
            tmp_path,
            _PGTP_WITH_TWO_CONNECTION_ELEMENTS.replace("quality.example.com", "other.host"),
            name="other.pgtp",
        )
    )

    assert "never tested" in dialog.quality_advisory()


def test_the_advisory_never_blocks_accept(qtbot, tmp_path):
    dialog = NewProjectDialog()
    qtbot.addWidget(dialog)
    dialog._folder_edit.setText(str(tmp_path / "p"))
    dialog.set_pgtp_path(_pgtp_file(tmp_path))
    got = []
    dialog.accepted.connect(lambda: got.append(True))

    dialog._on_accept_clicked()

    assert got == [True]
    assert dialog.quality_advisory() != ""  # noticed, and still accepted
