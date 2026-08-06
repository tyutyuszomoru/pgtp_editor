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
"""The three rules that make the `main_window.py` decomposition a decomposition
and not a rename.

Moving code out of a god object achieves nothing if the moved code still reaches
back through a window reference — you get the same tangle spread over more files,
which is strictly worse. So every ``pgtp_editor/ui/*_controller.py`` module is
checked, by source inspection, against three structural rules:

1. **No attribute access through the window.** ``UiShell.window`` is a DIALOG
   PARENT ONLY (see ``ui/ui_shell.py``); one ``self._shell.window.some_panel``
   re-creates the god object with extra steps, and the next lane copies it.
2. **No dependency on ``MainWindow``.** A collaborator that imports or names the
   host cannot be constructed, read or tested without it — which is the property
   the decomposition exists to remove. Collaborators construct headless.
3. **No collaborator imports another collaborator.** Cross-lane traffic is
   injected callables and Qt signals, decided by the host. Direct imports would
   re-introduce the lane-to-lane coupling one layer down, and would make the
   import graph cyclic the moment the traffic went both ways.

Source inspection, not import-time introspection, on purpose: these are rules
about how the code is *written*, and a violation must fail even on a code path
no test happens to execute. Comments and string literals are tokenized away
first, so a docstring may freely *discuss* ``MainWindow`` or show the forbidden
``self._shell.window.panel`` shape as the counter-example it is.

The test discovers modules by glob, so every collaborator added by a later wave
is covered automatically — nothing to remember, nothing to edit.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parents[2] / "pgtp_editor" / "ui"

#: The single allowed collaborator-to-collaborator import: the sandbox UI lane
#: OWNS the `SandboxController` object (it constructs it and drives its
#: lifecycle), so that is composition, not cross-lane coupling. Anything else
#: must go through injected callables/signals wired by the host.
ALLOWED_CONTROLLER_IMPORTS = {
    "sandbox_ui_controller": {"sandbox_controller"},
}

#: Rule 1. Matches an attribute access *through* the window reference, in either
#: spelling a collaborator might use. `shell.window` passed as a bare argument
#: (`Dialog(..., self._shell.window, ...)`) has no trailing dot and is fine.
WINDOW_DEREF = re.compile(r"(_shell\.window|self\._window)\s*\.")

#: Rule 3.
CONTROLLER_IMPORT = re.compile(
    r"^\s*(?:from\s+\S*\bui\.(\w+_controller)\b|import\s+\S*\bui\.(\w+_controller)\b)",
    re.MULTILINE,
)


def _code_only(source: str) -> str:
    """`source` with every comment and string literal blanked out, line numbers
    and layout preserved.

    The rules below are about executable references. Without this, a docstring
    that explains *why* dereferencing the window is forbidden would itself trip
    the check — punishing exactly the code that documents the rule.
    """
    lines = source.splitlines()
    kill: dict[int, list[tuple[int, int]]] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (start_row, start_col), (end_row, end_col) = token.start, token.end
        for row in range(start_row, end_row + 1):
            begin = start_col if row == start_row else 0
            finish = end_col if row == end_row else len(lines[row - 1])
            kill.setdefault(row, []).append((begin, finish))
    out = []
    for number, line in enumerate(lines, start=1):
        for begin, finish in kill.get(number, ()):
            line = line[:begin] + " " * (finish - begin) + line[finish:]
        out.append(line)
    return "\n".join(out)


def _controller_modules() -> list[Path]:
    return sorted(UI_DIR.glob("*_controller.py"))


def _module_ids() -> list[str]:
    return [path.stem for path in _controller_modules()]


@pytest.fixture(params=_controller_modules(), ids=_module_ids())
def controller_source(request) -> tuple[str, str]:
    """(module name, its source with comments and string literals blanked)."""
    path: Path = request.param
    return path.stem, _code_only(path.read_text(encoding="utf-8"))


def test_at_least_one_collaborator_is_discovered():
    """A glob that silently matches nothing would make every rule below vacuous."""
    assert _module_ids(), (
        "No pgtp_editor/ui/*_controller.py modules found — this file's rules "
        "would be silently enforcing nothing. Check the glob, not the code."
    )


def test_no_attribute_access_through_the_window(controller_source):
    name, source = controller_source
    offenders = [
        line.strip() for line in source.splitlines() if WINDOW_DEREF.search(line)
    ]
    assert not offenders, (
        f"{name}.py dereferences the host window: {offenders}\n"
        "UiShell.window is a DIALOG PARENT ONLY — it may appear solely as a "
        "parent argument to a Qt dialog constructor or modal static, e.g. "
        "modals.QMessageBox.question(self._shell.window, ...). Reading anything "
        "*off* the window rebuilds the god object one attribute at a time, and "
        "the next lane copies whatever this one did. If you need host state or "
        "behavior, add a named field to UiShell (a bound host method) and use "
        "that instead."
    )


def test_no_dependency_on_mainwindow(controller_source):
    name, source = controller_source
    assert "from pgtp_editor.ui.main_window import" not in source, (
        f"{name}.py imports from main_window. A collaborator must not depend on "
        "its host: that is exactly the dependency the decomposition removes, and "
        "it makes the import graph cyclic (main_window imports the collaborator)."
    )
    assert not re.search(r"\bMainWindow\b", source), (
        f"{name}.py names MainWindow. A collaborator must construct, read and "
        "test headless — knowing the host's type means it cannot. Type-annotate "
        "against UiShell (or QWidget for a dialog parent) instead."
    )


def test_no_collaborator_imports_another_collaborator(controller_source):
    name, source = controller_source
    imported = {
        match.group(1) or match.group(2) for match in CONTROLLER_IMPORT.finditer(source)
    } - {name}
    unexpected = imported - ALLOWED_CONTROLLER_IMPORTS.get(name, set())
    assert not unexpected, (
        f"{name}.py imports {sorted(unexpected)}. Collaborators do not talk to "
        "each other directly — cross-lane traffic is injected callables and Qt "
        "signals, wired by the host, which is what keeps each lane replaceable "
        "and the import graph acyclic. The only sanctioned exception is a lane "
        f"that OWNS the other object's lifecycle: {ALLOWED_CONTROLLER_IMPORTS}. "
        "Widen that allow-list only for genuine ownership, never for "
        "convenience."
    )


# -- the UiShell contract the rules above assume ----------------------------
def test_every_shell_callable_is_a_bound_method_of_the_host(qtbot, tmp_path):
    """`UiShell`'s callable fields must be LATE-BOUND — bound methods of the
    host that resolve its state when invoked.

    A field captured at construction (a lambda closing over a value, or the
    target function itself) freezes whatever the host happened to hold while
    `__init__` was still running. That silently breaks the suite's established
    seam-injection convention, where a test replaces a seam on the *finished*
    window. Requiring `__self__ is window` makes the mistake impossible to make
    by accident.
    """
    from PySide6.QtCore import QSettings

    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)

    shell = window._shell
    callables = {
        field: getattr(shell, field)
        for field in shell.__dataclass_fields__
        if callable(getattr(shell, field)) and field != "window"
    }
    assert callables
    not_bound = {
        field: value
        for field, value in callables.items()
        if getattr(value, "__self__", None) is not window
    }
    assert not not_bound, (
        f"UiShell fields are not bound host methods: {sorted(not_bound)}. Hand "
        "over `self._some_method`, never a lambda or a captured target — see "
        "pgtp_editor/ui/ui_shell.py, 'Late binding'."
    )


def test_shell_run_async_honours_post_construction_injection(qtbot, tmp_path):
    """The specific failure the trampoline exists to prevent: ~13 tests assign
    `window._run_async = _sync_run` AFTER the window is built. A shell that had
    captured the original would keep marshalling to the threadpool, so those
    tests would hang or assert on results that never arrived."""
    from PySide6.QtCore import QSettings

    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow(
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    )
    qtbot.addWidget(window)
    run_async = window._shell.run_async          # captured the way a collaborator does

    seen = []

    def _sync_run(fn, on_result, on_error=None, **kwargs):
        seen.append(fn)
        on_result(fn())

    window._run_async = _sync_run                # injected AFTER construction

    delivered = []
    run_async(lambda: 42, delivered.append)
    assert delivered == [42]
    assert len(seen) == 1


def test_the_window_deref_regex_actually_matches_a_violation():
    """The rules are only worth as much as the pattern behind them — a typo that
    made this regex match nothing would let every violation through silently."""
    assert WINDOW_DEREF.search("x = self._shell.window.center_stage")
    assert WINDOW_DEREF.search("self._window.statusBar()")
    # A bare parent argument is the sanctioned use and must NOT match.
    assert not WINDOW_DEREF.search(
        "dialog = CustomizeToolbarDialog(pairs, ids, self._shell.window, icons)"
    )
    assert not WINDOW_DEREF.search("modals.QMessageBox.question(self._shell.window, 'a')")
