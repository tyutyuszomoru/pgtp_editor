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

# pgtp_editor/ui/lint_controller.py
"""The host side of PHP lint integration (spec §22).

What was missing
----------------
`pgtp_editor/lint/` shipped whole -- `config.py` (the `lint_executable_path`
key, stored in §19's *existing* `generator_config.json`), `runner.py` (the one
injectable spawn), `findings.py` (pure text → `LintOutcome` → ready-to-append
`[Lint]` rows) and `service.py` (`LintService.lint_text`, which never raises) --
and `PhpFileTab` already consumed all of it. What did not exist was any way to
*reach* it: no Tools ▸ Lint Current File, no Locate PHP Linter…, no on-save
toggle, and `lint_reported` reached no Audit panel. This collaborator is exactly
that host side and nothing more; it re-implements none of `lint/`.

One service, every tab
----------------------
The controller owns **one** :class:`~pgtp_editor.lint.service.LintService` for
the window's lifetime and hands that same instance to every PHP tab. The
configured path is read *inside* the service on each lint, so Locate PHP
Linter… takes effect on already-open tabs with no re-wiring -- which is why
there is one service rather than one per tab.

Advisory, structurally
----------------------
§22 is advisory-only: a lint failure must never unwind a save. Three properties
preserve that through this lane, and all three are easy to break by accident:

* `LintService.lint_text` never raises, and this module never wraps it in
  anything that could (the run happens inside `PhpFileTab.request_lint`, on a
  `run_async` worker).
* the on-save hook is the *last* thing `PhpFileTab.save()` does, after the bytes
  are written -- nothing here may move it earlier.
* :meth:`report` is a slot. It swallows nothing important but must not raise,
  because it runs on the marshalled-back result of a worker: a `[Lint]` row that
  cannot be rendered is a log line, not a traceback out of the save path.

Audit panel, not a new panel
----------------------------
§22 forbids a diagnostics panel of its own: findings go to the existing Audit
list with the reserved `[Lint]` prefix (never `[Check]`, which is §18.5's
SQL/plpgsql channel, and never `[SQL]`, §18.4's formatter refusals). The row
text comes from `lint/findings.py::audit_lines` and is appended **verbatim** --
re-formatting it here would fork the wording of the "php -l stops at the FIRST
error" warning away from the module that owns it.

Click-to-navigate uses `[Check]`'s convention (`_report_check_findings`): the
1-based line on `UserRole`, a routing target on `UserRole + 1` -- here the
string `lint/findings.py::LINT_AUDIT_TARGET`. A `[Lint]` row additionally needs
to say *which* PHP tab it belongs to (unlike `[Check]`, whose `UserRole + 1`
tuple is itself the object key), so the tab key rides on `UserRole + 2`. That
slot is Verify XSD's `mode`, but the host only reads it when the target is
`"xsd"`, so the two never collide.

This lane never imports `ui/php_tab_controller.py` (collaborators do not import
collaborators): the host connects that lane's `tab_opened` to
:meth:`attach_tab`, and routes an Audit click back to it.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QListWidgetItem

from pgtp_editor.lint.config import load_lint_executable_path, save_lint_executable_path
from pgtp_editor.lint.findings import LINT_AUDIT_TARGET, LINT_PREFIX
from pgtp_editor.lint.service import LintService
from pgtp_editor.ui import modals
from pgtp_editor.ui.file_filters import executable_filter
from pgtp_editor.ui.software_settings_dialog import EXTERNAL_TOOLS_SETTINGS_PATH
from pgtp_editor.ui.ui_shell import UiShell

_log = logging.getLogger(__name__)

#: QSettings key behind Tools ▸ Lint on Save. A per-user preference like
#: `lightTheme`, in the same store, read with `type=bool` for the same reason
#: (an ini backend hands back the string "false" otherwise, which is truthy).
LINT_ON_SAVE_SETTINGS_KEY = "lintOnSave"

#: The three Audit item roles -- see the module docstring for why the tab key
#: needs a third slot that `[Check]` does not.
LINT_LINE_ROLE = Qt.ItemDataRole.UserRole
LINT_TARGET_ROLE = Qt.ItemDataRole.UserRole + 1
LINT_TAB_KEY_ROLE = Qt.ItemDataRole.UserRole + 2


class LintController(QObject):
    """Tools ▸ Lint Current File / Lint on Save, plus the linter location (§22).

    The location's own menu item is gone: `Locate PHP Linter…` MOVED to
    `Settings ▸ Software settings… ▸ External tools` (FQ-260812025705), which
    drives :meth:`locate_linter` from there. In exchange, the two Tools entries
    are now GATED on a configured linter (:meth:`refresh_tool_affordances`)
    instead of being always enabled and reporting `NOT RUN` at trigger time.
    """

    def __init__(
        self,
        shell: UiShell,
        parent: QObject | None = None,
        *,
        service: LintService | None = None,
        config_dir: Path | None = None,
        choose_executable: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._shell = shell
        self._settings = shell.settings
        #: Where `generator_config.json` lives -- the host's injected
        #: `generator_config_dir` (a tmp_path under test). §22 reuses §19's
        #: file, so this is the SAME override, never a second one.
        self._config_dir = config_dir
        self._service = service if service is not None else LintService(
            executable_provider=lambda: load_lint_executable_path(config_dir)
        )
        self._choose_executable = choose_executable or self._default_choose_executable
        self._lint_on_save = bool(
            self._settings.value(LINT_ON_SAVE_SETTINGS_KEY, False, type=bool)
        )
        #: The Tools entries FQ-260812025705 greys while no linter is configured.
        #: The host BUILDS them (they live on its Tools menu) and registers them
        #: here, so this lane owns the *rule* without owning the menu -- the same
        #: split as `tab_lint_settings`, and the reason the pane can stay out of
        #: both.
        self._dependent_actions: list = []

    # -- read-only surface ----------------------------------------------------

    @property
    def service(self) -> LintService:
        """The ONE service, shared by every PHP tab (see the module docstring)."""
        return self._service

    @property
    def lint_on_save(self) -> bool:
        return self._lint_on_save

    def tab_lint_settings(self) -> tuple:
        """`(service, lint_on_save)` -- what the §21 lane passes straight into
        `CenterStage.open_php_file_tab`. The host wires this as that lane's
        `lint_settings` seam, which is how the service reaches a tab without
        either controller importing the other."""
        return self._service, self._lint_on_save

    # -- the linter location, and what depends on it ---------------------------

    def linter_executable_path(self) -> str | None:
        """The stored `php` path, or None. Read-only surface for the
        `External tools` settings pane, so the pane never learns which file the
        path is stored in."""
        return load_lint_executable_path(base_dir=self._config_dir)

    def linter_is_configured(self) -> bool:
        """Whether a linter path is stored at all.

        Deliberately NOT "and the file still exists": §22 is advisory, and its
        `EXECUTABLE_MISSING` outcome already reports a vanished binary as a
        `[Lint]` row. Greying on existence would make a lint run's own diagnosis
        unreachable, which is the opposite of stating the reason.
        """
        return self.linter_executable_path() is not None

    def register_dependent_actions(self, *actions) -> None:
        """Hand over the Tools entries that need a linter, and gate them now."""
        self._dependent_actions = [action for action in actions if action is not None]
        self.refresh_tool_affordances()

    def refresh_tool_affordances(self) -> None:
        """Re-evaluate the registered entries' enabled state.

        Called on registration (so startup is gated, not only a later change)
        and by `locate_linter`, which is what makes setting the linter in the
        settings pane light the Tools entries up LIVE.
        """
        enabled = self.linter_is_configured()
        for action in self._dependent_actions:
            action.setEnabled(enabled)
            # A greyed entry states its reason (FQ-023's principle): the Locate
            # item that used to be the only pointer has moved, so the tooltip
            # has to carry the address.
            action.setToolTip(
                ""
                if enabled
                else "Unavailable: no PHP linter is configured. Set it in "
                f"{EXTERNAL_TOOLS_SETTINGS_PATH}."
            )

    # -- the on-save toggle ---------------------------------------------------

    def set_lint_on_save(self, enabled) -> None:
        """Tools ▸ Lint on Save. Persisted, and applied to tabs that are
        ALREADY open -- a preference the user flips must not need every tab
        reopened to take effect."""
        self._lint_on_save = bool(enabled)
        self._settings.setValue(LINT_ON_SAVE_SETTINGS_KEY, self._lint_on_save)
        for tab in self._shell.stage.php_file_tabs().values():
            tab.set_lint_on_save(self._lint_on_save)

    # -- per-tab wiring -------------------------------------------------------

    def attach_tab(self, tab, key) -> None:
        """Give one freshly opened PHP tab the service, the current toggle and
        the `lint_reported` → Audit connection.

        Connected by the host to `PhpTabController.tab_opened`. The tab is only
        ever announced once per key there, so this cannot double-connect."""
        tab.set_lint_service(self._service)
        tab.set_lint_on_save(self._lint_on_save)
        tab.lint_reported.connect(lambda lines, key=key: self.report(lines, key))

    # -- Tools ▸ Lint Current File -------------------------------------------

    def lint_active_file(self) -> bool:
        """Lint the active PHP tab's CURRENT buffer (dirty or Untitled included
        -- `request_lint` lints the buffer, not the file on disk).

        With no PHP tab active this is not silent: §22's whole failure mode is a
        user reading nothing and concluding "clean", so the reason lands in the
        Audit panel as a `[Lint]` row like every other non-run outcome."""
        tab = self._shell.stage.active_php_file_tab()
        if tab is None:
            self._append_row(
                f"{LINT_PREFIX}NOT RUN: no custom-PHP tab is active — open one "
                f"with File ▸ Open PHP File… first."
            )
            self._shell.status("Lint: no custom-PHP tab is active", 5000)
            return False
        if tab.lint_service is None:
            # A tab opened before this lane existed (or by a caller that passed
            # no service) still lints -- the service is a window-level fact.
            tab.set_lint_service(self._service)
        return bool(tab.request_lint())

    # -- locating the linter (driven by Software settings ▸ External tools) ----

    def locate_linter(self) -> None:
        """Point `lint_executable_path` at a `php` executable.

        No longer a `Tools` menu item: FQ-260812025705 MOVED it into
        `Settings ▸ Software settings… ▸ External tools`, which is now its sole
        entry point and calls this method. How it persists did not change.

        Writes through `lint/config.py`, which persists into §19's existing
        `generator_config.json` preserving its other keys -- there is
        deliberately no second config store for §22."""
        path = self._choose_executable()
        if not path:
            return
        try:
            save_lint_executable_path(path, base_dir=self._config_dir)
        except OSError as exc:
            modals.QMessageBox.critical(
                self._shell.window,
                "Could Not Save Setting",
                f"The PHP linter path could not be stored:\n\n{exc}",
            )
            return
        # Live gating: the pane calls this, so the Tools entries must un-grey
        # without a restart.
        self.refresh_tool_affordances()
        self._shell.status(f"PHP linter set: {Path(path).name}", 5000)

    def _default_choose_executable(self) -> str:
        path, _filter = modals.QFileDialog.getOpenFileName(
            self._shell.window,
            "Locate PHP Linter",
            self._shell.default_dir(),
            executable_filter(),
        )
        return path or ""

    # -- lint_reported → the Audit panel -------------------------------------

    def report(self, lines, key=None) -> None:
        """Append one lint attempt's `[Lint]` rows to the Audit panel.

        `lines` are `lint/findings.py::LintAuditLine`s, already carrying the
        `[Lint]` prefix and the line to navigate to -- appended VERBATIM. A row
        whose `line` is None is left role-less and therefore inert, which is the
        `[Validate]`/`[Check]` convention for a narrative row.

        Never raises: this runs on a worker result marshalled back to the GUI
        thread from inside a completed save (§22 is advisory)."""
        for line in lines or ():
            try:
                text = str(getattr(line, "text", line))
                number = getattr(line, "line", None)
            except Exception:  # noqa: BLE001 -- a malformed row is not fatal
                _log.exception("Unrenderable [Lint] row dropped")
                continue
            self._append_row(text, number, key)

    def _append_row(self, text: str, line=None, key=None) -> None:
        item = QListWidgetItem(text)
        if line is not None:
            item.setData(LINT_LINE_ROLE, line)
            item.setData(LINT_TARGET_ROLE, LINT_AUDIT_TARGET)
            item.setData(LINT_TAB_KEY_ROLE, key)
        self._shell.audit.addItem(item)
