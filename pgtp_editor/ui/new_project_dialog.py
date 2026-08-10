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

# pgtp_editor/ui/new_project_dialog.py
"""The New Project dialog (§18.2).

A local project is a **folder the user chooses** -- not necessarily a git
repository. This dialog collects that folder plus two OPTIONAL sections:

- **Local sandbox** -- a Postgres **server** connection (host/port/user/
  password) whose **Test** button has one specific job: verifying the
  connected user is a **superuser** (sandbox provisioning needs
  `CREATE EXTENSION`), reusing `db/sandbox.py::probe` as the same capability
  probe the later sandbox lane uses -- not a second, ad hoc superuser check.
  This step also presents the **"with data" / "without data"** provisioning
  choice (§18.5 D2a, settled 2026-08-05): "without data" (the default) is the
  existing schema-only baseline path; "with data" clones the target database
  via `pg_dump`/`pg_restore` instead, once, at creation time -- never
  re-toggled later.

  **There is deliberately no "Database:" field (FQ-007).** The app does not ask
  for an existing database and does not accept a typed name: the sandbox
  database is **created** by the app, with a name it generates itself
  (`ui/sandbox_controller.py::generate_sandbox_database_names`), because §18.5
  D2's ownership convention -- `pgtp_sandbox_*` **plus** the
  `pgtp-editor-sandbox:` `pg_database` comment marker -- is the only thing that
  makes a sandbox safe to wipe, and `open_sandbox` refuses anything without
  both. A user-typed name cannot satisfy it. `sandbox_params()` therefore
  carries an **empty** `database`, and the created name is recorded into
  `ProjectSettings.sandbox.database` by the host once provisioning succeeds.
  The **Test** button probes the *maintenance* database
  (`MAINTENANCE_DATABASE`), which is exactly the connection
  `create_sandbox_database` will use.
- **The project's `.pgtp`** (FQ-035, §18.2) -- an optional open-file field. Empty
  is **today's behaviour byte for byte**: a sandbox-only project, no `PgtpLink`,
  no target. Attaching one **reveals the quality (target) server section and
  populates it** from the file's first `<ConnectionOptions>` element through
  `db/config.py::connection_from_tree` -- the same function the first-open path
  (`MainWindow._import_pgtp_connection_into_target`) already uses, so the two
  ways of learning a project's target cannot age apart.

  `<ScriptConnectionOptions>` is **never** read: the vendor writes a second
  element with the same attribute set and, in this repo's own fixture, a
  DIFFERENT port -- picking between two candidates would be a guess about which
  database a project points at. The sandbox is **never** seeded from
  `<ConnectionOptions>` either; that is how a sandbox ends up pointed at
  production (§18.2). The two groups stay independent.
- **Quality (target) server** -- host/port/database/user/password plus its own
  **Test** button, **hidden (not disabled) while no `.pgtp` is attached** (§7's
  rule: a control with no subject is not a denied control -- there would be
  nothing to populate it from). Its `Test` is
  `db/introspect.py::test_connection` (*"can we connect at all?"*), deliberately
  NOT the sandbox's superuser `probe`: the quality database is only ever read,
  and a superuser demand there would refuse a correctly-configured project.

  `connection_from_tree` returns `password=""` unconditionally (the XML stores
  it obfuscated and this app never de-obfuscates it), so the one field the
  attach can never supply is exactly the one a `Test` most depends on -- which
  is *why* this section earns a place at creation time, and why no completeness
  gate could ever be sound here.
- **Git** -- server/user/checkout-branch fields, captured but **inert**
  (§18.2: "explicit TBD/placeholder only, not designed"). No Test button,
  no validation beyond being present -- nothing reads these fields yet
  except `db/ddl_project.py::GitConfig`'s round-trip through the project's
  own settings JSON.

Shown non-modally (`show()`, never `.exec()`), same convention as
`ConnectionSetupDialog`: callers read back the collected fields via getters
after `accepted` fires and perform the actual folder-creation / settings-
write themselves -- this dialog persists nothing on its own.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.db.config import ConnectionParams, connection_from_tree
from pgtp_editor.db.ddl_project import GitConfig
from pgtp_editor.db.introspect import test_connection
from pgtp_editor.db.sandbox import (
    SANDBOX_DB_PREFIX,
    SandboxCapabilities,
    SandboxMode,
    probe,
)
from pgtp_editor.model.parser import PgtpParseError, load_project
from pgtp_editor.ui.async_task import run_async
from pgtp_editor.ui.sandbox_controller import (
    MAINTENANCE_DATABASE,
    generate_sandbox_database_names,
)

Prober = Callable[[ConnectionParams], SandboxCapabilities]
Tester = Callable[[ConnectionParams], "tuple[bool, str]"]
ConnectionReader = Callable[[str], "ConnectionParams | None"]

#: The `*.pgtp` filter for the attach field's open-file dialog.
PGTP_FILE_FILTER = "PGTP projects (*.pgtp);;All files (*)"


def read_pgtp_connection(path: str) -> ConnectionParams | None:
    """The attached `.pgtp`'s target connection, or None when it cannot be read.

    Parses the file the app's one way (`model/parser.py::load_project`, which
    also repairs CESU-8 emoji) and reads the FIRST `<ConnectionOptions>` element
    through `db/config.py::connection_from_tree` -- never
    `<ScriptConnectionOptions>`, which the vendor writes with a different port.

    **Tolerant, like the open-time linker** (§18.2's `link_pgtp_if_needed`
    swallows an unreadable source rather than raising a modal at the user): an
    unparsable or connection-less file yields None, which the dialog reports
    inline. Attaching a bad file is never an error the user must clear.
    """
    try:
        project = load_project(path)
    except PgtpParseError:
        return None
    return connection_from_tree(project.tree)


class NewProjectDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        prober: Prober = probe,
        tester: Tester = test_connection,
        connection_reader: ConnectionReader = read_pgtp_connection,
    ) -> None:
        super().__init__(parent)
        self._prober = prober
        # FQ-035: two DIFFERENT probes on purpose -- `probe` asks "is this user a
        # superuser?" for the sandbox, `test_connection` asks "can we connect at
        # all?" for the quality server. Not an inconsistency to tidy up.
        self._tester = tester
        self._connection_reader = connection_reader
        # Off-thread executor seam, same convention as ConnectionSetupDialog:
        # tests replace this with a synchronous stub for determinism.
        self._run_async = run_async
        # Last sandbox capability probe result, kept so a caller (e.g.
        # MainWindow) can read it after `accepted` fires without re-probing.
        self._last_probe: SandboxCapabilities | None = None
        # DEC-260810134915: whether the quality `Test` button has ever produced
        # an ANSWER (green, red or a broken seam -- all three are "it was
        # tried"). Read only by `quality_advisory`, which says so once at accept
        # when the section was left blank or never tried. Never a gate.
        self._quality_tested = False
        self.setWindowTitle("New Project")

        identity_form = QFormLayout()
        self._name_edit = QLineEdit()
        self._description_edit = QLineEdit()
        identity_form.addRow("Name:", self._name_edit)
        identity_form.addRow("Description:", self._description_edit)

        self._folder_edit = QLineEdit()
        self._folder_edit.setReadOnly(True)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_for_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder_edit, 1)
        folder_row.addWidget(browse_button)
        folder_form = QFormLayout()
        folder_form.addRow("Project folder:", folder_row)

        # -- the `.pgtp` attach field (FQ-035) --------------------------------
        # The folder row's exact shape, with `getOpenFileName` in place of
        # `getExistingDirectory`.
        self._pgtp_edit = QLineEdit()
        self._pgtp_edit.setReadOnly(True)
        pgtp_browse_button = QPushButton("Browse…")
        pgtp_browse_button.clicked.connect(self._browse_for_pgtp)
        pgtp_row = QHBoxLayout()
        pgtp_row.addWidget(self._pgtp_edit, 1)
        pgtp_row.addWidget(pgtp_browse_button)
        folder_form.addRow("Project .pgtp (optional):", pgtp_row)
        pgtp_caveat = QLabel(
            "Attaching the .pgtp this project is a checkout of links it to the"
            " project and fills in the quality server below from its"
            " <ConnectionOptions>. Leave it empty for a project with no .pgtp —"
            " you can still open one later, which links it the same way."
        )
        pgtp_caveat.setWordWrap(True)
        folder_form.addRow(pgtp_caveat)

        # -- the quality (target) server, revealed by the attach (FQ-035) -----
        # HIDDEN, not disabled, until a `.pgtp` is attached (§7): with no
        # `.pgtp` there is nothing to populate it from, so it is not a control
        # being denied -- it is a control with no subject.
        self._quality_group = QGroupBox("Quality (target) server")
        self._quality_host_edit = QLineEdit()
        self._quality_port_edit = QLineEdit()
        self._quality_database_edit = QLineEdit()
        self._quality_user_edit = QLineEdit()
        self._quality_password_edit = QLineEdit()
        self._quality_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        # Built here rather than reusing `ProjectSettingsDialog`'s form: there is
        # no shared connection-field widget in this codebase (its
        # `_build_connection_form`/`_add_test_row` are private statics on a
        # QDialog subclass), and extracting one would touch all three dialogs --
        # explicitly out of scope for a UX sequencing feature (§18.2, FQ-035).
        quality_form = QFormLayout(self._quality_group)
        quality_form.addRow("Host:", self._quality_host_edit)
        quality_form.addRow("Port:", self._quality_port_edit)
        quality_form.addRow("Database:", self._quality_database_edit)
        quality_form.addRow("User:", self._quality_user_edit)
        quality_form.addRow("Password:", self._quality_password_edit)
        self._quality_test_button = QPushButton("Test")
        self._quality_test_button.clicked.connect(self.test_quality)
        self._quality_status_label = QLabel("")
        quality_test_row = QHBoxLayout()
        quality_test_row.addWidget(self._quality_test_button)
        quality_test_row.addWidget(self._quality_status_label, 1)
        quality_form.addRow(quality_test_row)
        quality_note = QLabel(
            "This is the quality/staging database the DDL Explorer and the"
            " database checks read while this project is open. Host, port,"
            " database and user come from the attached .pgtp; the PASSWORD is"
            " never in the XML (it is stored obfuscated there and never read),"
            " so it is the one field to supply here."
        )
        quality_note.setWordWrap(True)
        quality_form.addRow(quality_note)
        self._quality_group.setVisible(False)

        sandbox_group = QGroupBox("Local sandbox (optional)")
        self._sandbox_host_edit = QLineEdit()
        self._sandbox_port_edit = QLineEdit()
        self._sandbox_user_edit = QLineEdit()
        self._sandbox_password_edit = QLineEdit()
        self._sandbox_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        sandbox_form = QFormLayout()
        sandbox_form.addRow("Host:", self._sandbox_host_edit)
        sandbox_form.addRow("Port:", self._sandbox_port_edit)
        sandbox_form.addRow("User:", self._sandbox_user_edit)
        sandbox_form.addRow("Password:", self._sandbox_password_edit)
        # FQ-007: no "Database:" row on purpose -- see the module docstring. The
        # app creates the sandbox database itself, auto-named, so the ownership
        # convention (`pgtp_sandbox_*` + marker comment) always holds.
        self._sandbox_database_caveat = QLabel(
            "PGTP Editor CREATES the sandbox database on this server itself, "
            f"named '{SANDBOX_DB_PREFIX}…' with its own ownership marker, and "
            "provisions it (plus plpgsql_check) when the project is created. "
            "It only ever writes to a database it created, so there is nothing "
            "to name or create by hand — and no existing database is touched."
        )
        self._sandbox_database_caveat.setWordWrap(True)
        sandbox_form.addRow(self._sandbox_database_caveat)
        self._sandbox_test_button = QPushButton("Test")
        self._sandbox_test_button.clicked.connect(self.test_sandbox)
        self._sandbox_status_label = QLabel("")
        sandbox_test_row = QHBoxLayout()
        sandbox_test_row.addWidget(self._sandbox_test_button)
        sandbox_test_row.addWidget(self._sandbox_status_label, 1)

        # "with data" / "without data" clone choice (§18.5 D2a) -- chosen
        # once, here, at sandbox-creation time; never re-toggled later. Recorded
        # verbatim into ProjectSettings.sandbox_mode by the caller.
        self._sandbox_without_data_radio = QRadioButton("Without data (schema only, default)")
        self._sandbox_without_data_radio.setChecked(True)
        self._sandbox_with_data_radio = QRadioButton(
            "With data (clones the target database via pg_dump/pg_restore)"
        )
        mode_caveat = QLabel(
            "One-shot: cloning happens once, at creation. To refresh data later,"
            " destroy and recreate the sandbox. \"With data\" additionally needs"
            " pg_dump/pg_restore on PATH."
        )
        mode_caveat.setWordWrap(True)
        sandbox_mode_layout = QVBoxLayout()
        sandbox_mode_layout.addWidget(self._sandbox_without_data_radio)
        sandbox_mode_layout.addWidget(self._sandbox_with_data_radio)
        sandbox_mode_layout.addWidget(mode_caveat)

        sandbox_layout = QVBoxLayout(sandbox_group)
        sandbox_layout.addLayout(sandbox_form)
        sandbox_layout.addLayout(sandbox_test_row)
        sandbox_layout.addLayout(sandbox_mode_layout)

        git_group = QGroupBox("Git (optional -- not yet used)")
        self._git_server_edit = QLineEdit()
        self._git_user_edit = QLineEdit()
        self._git_branch_edit = QLineEdit()
        git_form = QFormLayout()
        git_form.addRow("Server:", self._git_server_edit)
        git_form.addRow("User:", self._git_user_edit)
        git_form.addRow("Checkout branch:", self._git_branch_edit)
        git_caveat = QLabel(
            "Recorded for later -- git integration is not yet built. Nothing"
            " is cloned, committed, or pushed."
        )
        git_caveat.setWordWrap(True)
        git_layout = QVBoxLayout(git_group)
        git_layout.addLayout(git_form)
        git_layout.addWidget(git_caveat)

        self._folder_error_label = QLabel("")
        self._folder_error_label.setStyleSheet("color: red;")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept_clicked)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(identity_form)
        layout.addLayout(folder_form)
        layout.addWidget(self._quality_group)
        layout.addWidget(sandbox_group)
        layout.addWidget(git_group)
        layout.addWidget(self._folder_error_label)
        layout.addWidget(buttons)

    # --- Folder picking -----------------------------------------------------
    def _browse_for_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "New Project Folder", self._folder_edit.text())
        if not folder:
            return
        self._folder_edit.setText(folder)
        self._folder_error_label.setText("")

    def _on_accept_clicked(self) -> None:
        # The folder is still this dialog's ONLY blocking validation. FQ-035 adds
        # no gate: the quality section may be blank, partial or untested and
        # accept must succeed anyway -- exactly as it does today for a blank
        # sandbox connection (DEC-260810134915: a gate here cannot be made
        # honest, because `connection_from_tree` never yields the password, so
        # "fully populated" is not a bar the source data can clear). What the
        # ruling adds instead is `quality_advisory()`, which the creating caller
        # says once after accept -- an advisory is the ALTERNATIVE to a gate, not
        # the absence of one.
        if not self.folder():
            self._folder_error_label.setText("Choose a project folder first.")
            return
        self.accept()

    # --- The `.pgtp` attach, and the reveal it drives (FQ-035) ---------------
    def _browse_for_pgtp(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Attach the project's .pgtp",
            self._pgtp_edit.text(),
            PGTP_FILE_FILTER,
        )
        if not path:
            return
        self.set_pgtp_path(path)

    def set_pgtp_path(self, path: str) -> None:
        """Attach `path` (or detach, with `""`), revealing and re-populating the
        quality section. The programmatic seam behind `Browse…`, so nothing has
        to drive a file dialog to exercise the reveal."""
        self._pgtp_edit.setText(path)
        self._populate_quality_from_pgtp()

    def _populate_quality_from_pgtp(self) -> None:
        path = self.pgtp_path()
        # A (re-)attach replaces the fields, so any earlier `Test` answered a
        # different connection and no longer counts as having tried this one.
        self._quality_tested = False
        if not path:
            self._quality_group.setVisible(False)
            return
        self._quality_group.setVisible(True)
        self._quality_status_label.setText("")
        self._quality_status_label.setStyleSheet("")
        params = self._connection_reader(path)
        # Re-attaching REPLACES what the previous file put here rather than
        # merging: the fields describe the attached file, and a leftover host
        # from a different .pgtp is worse than a blank one.
        self._quality_host_edit.setText(params.host if params else "")
        self._quality_port_edit.setText(params.port if params else "")
        self._quality_database_edit.setText(params.database if params else "")
        self._quality_user_edit.setText(params.user if params else "")
        # `connection_from_tree` returns password="" unconditionally -- always
        # cleared, never populated, by construction.
        self._quality_password_edit.setText("")
        if params is None:
            self._quality_status_label.setText(
                "No <ConnectionOptions> could be read from this .pgtp — fill the"
                " fields in by hand if you want a quality connection."
            )
            return
        self._quality_status_label.setText(
            "Filled in from the .pgtp — enter the password (the XML never carries it)."
        )

    # --- Getters (read after `accepted` fires) -------------------------------
    def name(self) -> str:
        return self._name_edit.text()

    def description(self) -> str:
        return self._description_edit.text()

    def folder(self) -> str:
        return self._folder_edit.text()

    def pgtp_path(self) -> str:
        """The attached `.pgtp`'s **source** path, or `""` when none was attached
        (FQ-035). This is the sshfs-mounted source, not a working copy -- see
        `DdlProjectController.create_project` for what creation records from it."""
        return self._pgtp_edit.text()

    def target_params(self) -> ConnectionParams:
        """The quality (target) connection as currently typed, or an EMPTY
        `ConnectionParams` when no `.pgtp` is attached -- with the section hidden
        there is no target being described, and a fresh project must land at
        exactly today's empty default (§18.2). May be blank or partial with a
        file attached too: nothing gates on it (DEC-260810134915 -- creation is
        never refusable for a network condition; see `quality_advisory`)."""
        if not self.pgtp_path():
            return ConnectionParams()
        return ConnectionParams(
            host=self._quality_host_edit.text(),
            port=self._quality_port_edit.text(),
            database=self._quality_database_edit.text(),
            user=self._quality_user_edit.text(),
            password=self._quality_password_edit.text(),
        )

    def quality_advisory(self) -> str:
        """The **one** accept-time notice about the quality (target) section, or
        `""` when there is nothing to say (DEC-260810134915).

        Accept is never gated on this section -- but *where the app declines to
        gate something, it still owes the user a statement of what it noticed*
        (the FQ-023/DEC-013 shape applied to a non-refusal). Two things are worth
        saying exactly once, at creation:

        * a `.pgtp` was attached, the section was therefore shown, and the
          connection was left **blank**;
        * it was filled in but the `Test` button was **never tried**, so nothing
          has ever established that the host answers.

        Nothing is said when no `.pgtp` is attached -- the section was never
        shown, so there is no target being described and a sandbox-only project
        is created as silently as before. Nothing is said after a test either,
        red included: the user saw that answer inline, and repeating a failure
        they already read is noise, not a notice.

        The caller decides where this lands; `DdlProjectController.create_project`
        files it as a `[Project]` journal row.
        """
        if not self.pgtp_path():
            return ""
        params = self.target_params()
        if not params.host:
            return (
                "Created with no quality (target) server: a .pgtp was attached but"
                " the connection was left blank, so the DDL Explorer and the"
                " database checks have nothing to read until it is filled in"
                " (File > Project Settings…). Opening this project re-imports the"
                " target from the .pgtp while the host is still empty."
            )
        if not self._quality_tested:
            return (
                f"The quality (target) server ({params.host}) was never tested, so"
                " it is recorded as typed -- nothing here has established that it"
                " answers. It is re-probed on every project open, and Project"
                " Status reports the result."
            )
        return ""

    def sandbox_params(self) -> ConnectionParams:
        """The sandbox **server** connection. `database` is deliberately empty
        (FQ-007): the database does not exist yet and is not named by the user --
        the host fills this in with whatever `provision_new_database` created."""
        return ConnectionParams(
            host=self._sandbox_host_edit.text(),
            port=self._sandbox_port_edit.text(),
            database="",
            user=self._sandbox_user_edit.text(),
            password=self._sandbox_password_edit.text(),
        )

    def sandbox_admin_params(self) -> ConnectionParams:
        """The same connection pointed at the **maintenance** database -- what
        `create_sandbox_database` needs, since PostgreSQL forbids
        `CREATE DATABASE` inside the database being created. No separate
        admin-connection field exists on purpose (FQ-007 Q3)."""
        return replace(self.sandbox_params(), database=MAINTENANCE_DATABASE)

    def sandbox_database_names(self) -> list[str]:
        """The auto-generated `pgtp_sandbox_*` candidate names for this project,
        in the order the host should try them: the first one free on the server
        is created, a taken one is skipped (never reused, never dropped)."""
        return generate_sandbox_database_names(self.name())

    def sandbox_mode(self) -> SandboxMode:
        """The sandbox provisioning choice (§18.5 D2a) -- "without data"
        (`SandboxMode.SCHEMA_ONLY`) is the default and stays selected unless
        the user explicitly picks "with data"."""
        if self._sandbox_with_data_radio.isChecked():
            return SandboxMode.WITH_DATA
        return SandboxMode.SCHEMA_ONLY

    def git_config(self) -> GitConfig:
        return GitConfig(
            server=self._git_server_edit.text(),
            user=self._git_user_edit.text(),
            checkout_branch=self._git_branch_edit.text(),
        )

    # --- Quality (target) connectivity Test (FQ-035) --------------------------
    def test_quality(self) -> None:
        """*"Can we connect at all?"* -- `db/introspect.py::test_connection`,
        identical to `ConnectionSetupDialog.test` and
        `ProjectSettingsDialog.test_target`, run off the GUI thread so an
        unreachable host can't freeze the dialog.

        Deliberately **not** the sandbox's superuser `probe`: the quality
        database is only ever read (DDL Explorer, the checks), and a superuser
        demand here would refuse a correctly-configured project. A red result is
        informational -- accept is not gated on it."""
        self._quality_test_button.setEnabled(False)
        self._quality_status_label.setStyleSheet("")
        self._quality_status_label.setText("Testing connection…")
        params = self.target_params()

        def on_result(result: "tuple[bool, str]") -> None:
            ok, message = result
            # Tried, and answered -- so `quality_advisory` has nothing left to
            # say about it, red included: the user is reading that answer here.
            self._quality_tested = True
            self._quality_status_label.setText(message)
            self._quality_status_label.setStyleSheet(
                "color: green;" if ok else "color: red;"
            )
            self._quality_test_button.setEnabled(True)

        def on_error(exc: BaseException) -> None:
            self._quality_tested = True
            self._quality_status_label.setText(str(exc))
            self._quality_status_label.setStyleSheet("color: red;")
            self._quality_test_button.setEnabled(True)

        self._run_async(
            lambda: self._tester(params),
            on_result=on_result,
            on_error=on_error,
        )

    # --- Sandbox superuser Test ----------------------------------------------
    def test_sandbox(self) -> None:
        """Verify the sandbox connection specifically for **superuser**, not
        merely "can connect" -- sandbox provisioning needs `CREATE EXTENSION`
        (§18.5 D2). Reuses `db/sandbox.py::probe`, run off the GUI thread so
        an unreachable host can't freeze the dialog.

        Probes the **maintenance** database (FQ-007), because that is the exact
        connection project creation will use to `CREATE DATABASE`: there is no
        sandbox database to probe yet."""
        self._sandbox_test_button.setEnabled(False)
        self._sandbox_status_label.setStyleSheet("")
        self._sandbox_status_label.setText("Testing…")
        params = self.sandbox_admin_params()

        def on_result(caps: SandboxCapabilities) -> None:
            self._apply_sandbox_probe_result(caps)

        def on_error(exc: BaseException) -> None:
            self._sandbox_status_label.setText(str(exc))
            self._sandbox_status_label.setStyleSheet("color: red;")
            self._sandbox_test_button.setEnabled(True)

        self._run_async(
            lambda: self._prober(params),
            on_result=on_result,
            on_error=on_error,
        )

    def _apply_sandbox_probe_result(self, caps: SandboxCapabilities) -> None:
        self._sandbox_test_button.setEnabled(True)
        self._last_probe = caps
        if caps.probe_error is not None:
            self._sandbox_status_label.setText(caps.probe_error)
            self._sandbox_status_label.setStyleSheet("color: red;")
            return
        if not caps.is_superuser:
            self._sandbox_status_label.setText(
                "Connected, but NOT a superuser — sandbox provisioning needs CREATE EXTENSION."
            )
            self._sandbox_status_label.setStyleSheet("color: red;")
            return
        if self.sandbox_mode() is SandboxMode.WITH_DATA and not caps.data_clone_available:
            missing = [
                name
                for name, path in (("pg_dump", caps.pg_dump_path), ("pg_restore", caps.pg_restore_path))
                if path is None
            ]
            self._sandbox_status_label.setText(
                "Connected — superuser, but 'with data' needs "
                f"{' and '.join(missing)} on PATH (not found)."
            )
            self._sandbox_status_label.setStyleSheet("color: red;")
            return
        self._sandbox_status_label.setText("Connected — superuser.")
        self._sandbox_status_label.setStyleSheet("color: green;")
