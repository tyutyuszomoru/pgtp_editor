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

# pgtp_editor/ui/php_tab_controller.py
"""The custom-PHP editing lane's entry points (spec §21).

What was missing
----------------
`ui/php_file_tab.py::PhpFileTab` and `CenterStage`'s dynamic PHP tab map both
shipped complete, but **nothing in the running app could reach them**: there was
no File ▸ "Open PHP File…", no drag-and-drop anywhere in the package, and
`CenterStage.php_file_close_requested` was emitted into the void, so clicking a
PHP tab's ✕ did literally nothing. This collaborator is the whole of the
missing host side, and it deliberately adds no editor behavior — every gesture
below ends in an API `PhpFileTab`/`CenterStage` already offered.

What it owns
------------
The three gestures that make the tab type exist for a user (Open, drop, close),
the read side of the filesystem (the tab is documented never to touch disk
behind its caller's back, so the *caller* reads), and the save reporting the tab
emits but cannot act on (`saved` → the status bar, `save_failed` → a modal the
widget is forbidden to show itself).

Deliberately NOT owned here
---------------------------
* **Linting.** §22 lives in `ui/lint_controller.py`. This lane never imports it
  (collaborators do not import collaborators): it asks an injected
  :attr:`lint_settings` callable what to hand `open_php_file_tab`, and announces
  each new tab on :attr:`tab_opened` for the host to route. Both seams default
  to inert, so a PHP tab opens perfectly well with no lint lane at all.
* **`.pgtp` files.** A dropped `.pgtp` is a *project* open, not a text open —
  routing it here would bypass §18.2's "New Project / Open Project / Edit
  Standalone" chooser and silently strand the user in standalone mode. It goes
  to the injected :attr:`open_pgtp` seam (the host's own project-open path); with
  no seam injected a dropped `.pgtp` is refused out loud rather than mis-opened
  as PHP source.
* **The three host routers.** `_save_active_tab` / `_active_find_bar` /
  `_active_bookmark_editor` dispatch across *every* tab type, so they stay on
  the host; this lane only supplies :meth:`save_active_tab` for the PHP branch
  of the first one to call.

Drop policy (decided here, and narrow on purpose)
-------------------------------------------------
A drag-and-drop is a gesture a user can make **by accident** onto the wrong
window, so the drop path classifies rather than trusts:

* ``.pgtp`` → the project-open seam (see above).
* anything else that reads as text → a PHP tab.
* a directory, an unreadable file, or a file containing a NUL byte in its first
  block → **refused with a status-bar message naming the file**, and nothing
  opens. Silently opening a JPEG as "PHP source" and then letting Ctrl+S write
  the mangled result back is data loss, not convenience.
* a file that is not valid UTF-8 → also refused, for the same reason: decoding
  it with replacement characters would make the very first save corrupt the
  file. This is stricter than Notepad++ and is a deliberate data-safety
  trade-off, not an oversight.

File ▸ "Open PHP File…" is *not* filtered this way beyond the same
text/UTF-8 safety check: a path the user typed into a file dialog is an explicit
choice, and the dialog offers "All files (*)".
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from pgtp_editor.ui import modals
from pgtp_editor.ui.php_file_tab import PhpFileTab, php_tab_key
from pgtp_editor.ui.ui_shell import UiShell

_log = logging.getLogger(__name__)

#: The Open PHP File… dialog's filter. PHP first, then everything -- §21 says
#: "any `.php`/text file", so the extension list is a convenience, not a gate.
PHP_OPEN_FILTER = (
    "PHP files (*.php *.phtml *.phps *.inc);;"
    "Text files (*.txt *.js *.css *.html *.htm *.json *.xml *.md *.sql);;"
    "All files (*)"
)

#: How many bytes the text/binary sniff looks at. Enough to catch any real
#: binary's header; small enough that a drag-enter over a huge file is free.
_SNIFF_BYTES = 8192


def read_php_text(path: Path) -> str:
    """Read `path` as UTF-8 text -- the default `reader` seam.

    Raises `OSError` (unreadable / a directory) or `UnicodeDecodeError` (not
    UTF-8). Both are refusals the controller reports; neither is swallowed into
    a lossy `errors="replace"` decode, because the tab's very next Ctrl+S would
    write those replacement characters back over the user's file.
    """
    return path.read_text(encoding="utf-8")


def looks_like_text(path: Path) -> bool:
    """Cheap "is this plausibly a text file" sniff for the drop path.

    A NUL byte in the first block is the classic binary marker and costs one
    small read. A full UTF-8 validation is deliberately NOT done here -- that
    happens in :func:`read_php_text` on the actual open, where the error can
    name the real reason.
    """
    try:
        if path.is_dir():
            return False
        with path.open("rb") as handle:
            return b"\x00" not in handle.read(_SNIFF_BYTES)
    except OSError:
        return False


class PhpTabController(QObject):
    """File ▸ Open PHP File…, drag-and-drop, and the PHP tab ✕ (spec §21)."""

    #: Emitted once per newly created tab, with the tab and its `CenterStage`
    #: map key. The host routes this to the §22 lane so `lint_reported` reaches
    #: the Audit panel -- this lane must not import that one.
    tab_opened = Signal(object, str)

    def __init__(
        self,
        shell: UiShell,
        parent: QObject | None = None,
        *,
        reader: Callable[[Path], str] = read_php_text,
        writer: Callable[[Path, str], None] | None = None,
        confirm_close: Callable[[str], str] | None = None,
        choose_open_paths: Callable[[], list[str]] | None = None,
        open_pgtp: Callable[[Path], None] | None = None,
        lint_settings: Callable[[], tuple] | None = None,
    ) -> None:
        super().__init__(parent)
        self._shell = shell
        #: Filesystem read seam -- injected in tests so no real file is needed.
        self._reader = reader
        #: Passed straight through to `PhpFileTab`; None keeps the tab's own
        #: default writer (`path.write_text`).
        self._writer = writer
        #: "save" / "discard" / "cancel" -- the unsaved-changes prompt. Never a
        #: bare QMessageBox at a call site; tests replace this attribute.
        self._confirm_close = confirm_close or self._default_confirm_close
        self._choose_open_paths = choose_open_paths or self._default_choose_open_paths
        #: Host's project-open path for a dropped `.pgtp` (see the docstring).
        self.open_pgtp: Callable[[Path], None] | None = open_pgtp
        #: () -> (lint_service, lint_on_save). Wired by the host to the §22
        #: lane; the default means "no linting", which is a valid app.
        self.lint_settings: Callable[[], tuple] = lint_settings or (lambda: (None, False))
        #: Keys whose signals are already connected, so a re-open (which
        #: focuses the existing tab) cannot double-wire it.
        self._wired: set[str] = set()

    # -- File ▸ Open PHP File… ------------------------------------------------

    def open_php_file_dialog(self) -> list:
        """File ▸ "Open PHP File…": pick one or more files and open a tab each.

        Plural on purpose -- §21: "Multiple files open concurrently as ordinary
        tabs". Returns the tabs actually opened (a refused or unreadable file
        contributes nothing but a status-bar message)."""
        tabs = []
        for raw in self._choose_open_paths():
            if not raw:
                continue
            tab = self.open_path(raw)
            if tab is not None:
                tabs.append(tab)
        return tabs

    def open_path(self, path) -> PhpFileTab | None:
        """Open (or focus) a PHP tab for `path`. None means it was refused.

        Focusing an already-open file short-circuits BEFORE the read: re-opening
        must not silently discard unsaved edits by reloading from disk.
        """
        path = Path(path)
        try:
            key = php_tab_key(path)
        except OSError:  # pragma: no cover -- a path resolve() itself rejects
            self._refuse(path, "the path could not be resolved")
            return None
        existing = self._shell.stage.php_file_tab(key)
        if existing is not None:
            self._shell.stage.setCurrentWidget(existing)
            return existing

        try:
            text = self._reader(path)
        except OSError as exc:
            self._refuse(path, str(exc))
            return None
        except UnicodeDecodeError:
            self._refuse(
                path,
                "it is not valid UTF-8 text — opening it would corrupt it on save",
            )
            return None

        lint_service, lint_on_save = self._lint_settings()
        tab = self._shell.stage.open_php_file_tab(
            path,
            text,
            writer=self._writer,
            lint_service=lint_service,
            lint_on_save=lint_on_save,
        )
        actual_key = self._shell.stage.php_file_tab_key(tab) or key
        self._wire(tab, actual_key)
        self._shell.status(f"Opened {path}", 5000)
        return tab

    def _lint_settings(self) -> tuple:
        """Ask the injected §22 seam what to hand `open_php_file_tab`.

        Tolerant of a seam that raises: §22 is advisory, so a broken lint lane
        must degrade to "no linting", never to "no PHP editing"."""
        try:
            service, on_save = self.lint_settings()
        except Exception:  # noqa: BLE001 -- advisory feature, never fatal
            _log.exception("Lint settings seam failed; opening the tab unlinted")
            return None, False
        return service, bool(on_save)

    def _wire(self, tab: PhpFileTab, key: str) -> None:
        """Connect one tab's outward signals, exactly once per key."""
        if key in self._wired:
            return
        self._wired.add(key)
        tab.dirty_changed.connect(
            lambda _dirty, key=key: self._shell.stage.update_php_file_tab(key)
        )
        tab.saved.connect(lambda path, key=key: self._on_saved(path, key))
        tab.save_failed.connect(self._on_save_failed)
        self.tab_opened.emit(tab, key)

    # -- Save reporting -------------------------------------------------------

    def save_active_tab(self) -> bool:
        """The PHP branch of the host's `_save_active_tab` router (Ctrl+S /
        File ▸ Save). False when there is no PHP tab active, or the save was
        cancelled/failed -- the same contract `_save_ddl_object_editor` has."""
        tab = self._shell.stage.active_php_file_tab()
        if tab is None:
            return False
        return tab.save()

    def _on_saved(self, path: str, key: str) -> None:
        """`PhpFileTab.saved`: the title may have changed (a Save As… renames
        the tab), and the status bar says so -- the same message and timeout
        `_save_ddl_object_editor` uses, so a PHP save reads identically."""
        self._shell.stage.update_php_file_tab(key)
        self._shell.status(f"Saved {path}", 5000)

    def _on_save_failed(self, message: str) -> None:
        """`PhpFileTab.save_failed`: the tab is forbidden to show a modal, so
        the host side does -- `_save_ddl_object_editor`'s modal, verbatim."""
        modals.QMessageBox.critical(
            self._shell.window, "Save Failed", f"Could not save:\n\n{message}"
        )

    # -- The ✕ on a PHP tab ---------------------------------------------------

    def on_close_requested(self, key: str) -> None:
        """`CenterStage.php_file_close_requested`, which previously reached
        nothing at all.

        Mirrors `_on_ddl_object_close_requested`: a dirty tab prompts, and a
        *failed or cancelled* save ABORTS the close rather than discarding the
        buffer -- `PhpFileTab.save()` returns False for both, and both must be
        treated exactly like Cancel."""
        tab = self._shell.stage.php_file_tab(key)
        if tab is None:
            return
        if tab.is_dirty():
            choice = self._confirm_close(tab.tab_tooltip())
            if choice == "cancel":
                return
            if choice == "save" and not tab.save():
                return
        self._shell.stage.close_php_file_tab(key)
        self._wired.discard(key)

    def _default_confirm_close(self, name: str) -> str:
        """The unsaved-changes prompt, split out so tests replace the method
        instead of ever driving a real modal (`_confirm_close_ddl_object`'s
        idiom)."""
        result = modals.QMessageBox.question(
            self._shell.window,
            "Unsaved Changes",
            f"{name} has unsaved changes. Save before closing?",
            modals.QMessageBox.StandardButton.Save
            | modals.QMessageBox.StandardButton.Discard
            | modals.QMessageBox.StandardButton.Cancel,
        )
        if result == modals.QMessageBox.StandardButton.Save:
            return "save"
        if result == modals.QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def _default_choose_open_paths(self) -> list[str]:
        paths, _filter = modals.QFileDialog.getOpenFileNames(
            self._shell.window,
            "Open PHP File",
            self._shell.default_dir(),
            PHP_OPEN_FILTER,
        )
        return list(paths or [])

    # -- Drag and drop --------------------------------------------------------

    @staticmethod
    def dropped_paths(mime) -> list[Path]:
        """Local filesystem paths carried by a drag's `QMimeData` (remote URLs
        yield an empty `toLocalFile()` and are dropped here)."""
        if mime is None or not mime.hasUrls():
            return []
        paths = []
        for url in mime.urls():
            local = url.toLocalFile()
            if local:
                paths.append(Path(local))
        return paths

    @staticmethod
    def can_accept_drop(paths) -> bool:
        """Whether the window should accept this drag at all.

        Deliberately cheap -- existence, not content: a drag-enter fires while
        the user is still moving the mouse, so the expensive text/UTF-8
        classification waits for :meth:`handle_dropped_paths`, where a refusal
        can be *explained* instead of silently making the cursor say no."""
        return any(path.is_file() for path in paths)

    def handle_dropped_paths(self, paths) -> None:
        """Route a completed drop: `.pgtp` to the project seam, text to a PHP
        tab, anything else to a spoken refusal (see the module docstring)."""
        for path in paths:
            if path.suffix.lower() == ".pgtp":
                if self.open_pgtp is None:
                    self._refuse(path, "project files are not opened by this lane")
                else:
                    self.open_pgtp(path)
                continue
            if not looks_like_text(path):
                self._refuse(path, "it is a folder or a binary file")
                continue
            self.open_path(path)

    # -- [Lint] click-to-navigate target -------------------------------------

    def navigate_to(self, key, line) -> None:
        """Focus the PHP tab filed under `key` and place the caret on `line`.

        What a `[Lint]` Audit row's click resolves to (§22). A key with no open
        tab does NOTHING -- exactly `_navigate_to_ddl_object`'s rule: falling
        back to Raw XML would navigate a different document, and reopening
        would resurrect a tab the user closed."""
        if not key or line is None:
            return
        tab = self._shell.stage.php_file_tab(key)
        if tab is None:
            return
        self._shell.stage.setCurrentWidget(tab)
        tab.navigate_to_line(line)

    # -- Refusals -------------------------------------------------------------

    def _refuse(self, path, reason: str) -> None:
        """Say out loud why a file was not opened. A silent no-op on a drop
        reads as "the app is broken"; §21's whole point is a file opening."""
        self._shell.status(f"Cannot open {Path(path).name}: {reason}", 8000)
