"""`pgtp_editor.vim` must stay a pure, Qt-free core (FQ-032 §8 + §5's dependency rule).

Two promises, both checked: statically (no Qt/DB/network import statement anywhere
in the package) and at runtime (importing the package in a **fresh interpreter**
loads no PySide6 module at all -- an in-process check would be meaningless because
the rest of the suite imports Qt). The shape is `tests/sql/test_package_purity.py`'s
and `tests/xmlfmt/`'s.

**The `sql/` half of the rule is not incidental tidiness.** `pgtp_editor.vim` must
not import `pgtp_editor.sql` either, because **no v1 motion may consume
`sql/block_spans.py::structure_chain`**: `w`/`b`/`e` are defined by character
class, and the editing-mode layer serves XML, PHP and JS buffers as well as SQL,
so a motion reading a SQL span model would be wrong on four of the six surfaces.
That chain's FQ-032 caller is the DEFERRED text objects, out of v1 scope.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VIM_PACKAGE = REPO_ROOT / "pgtp_editor" / "vim"

#: Import roots the pure core may never reach for (Qt, DB drivers, network, UI).
_FORBIDDEN_ROOTS = {
    "PySide6",
    "PyQt5",
    "PyQt6",
    "psycopg",
    "psycopg2",
    "socket",
    "urllib",
    "requests",
    "http",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.add("." * node.level + (node.module or ""))
            elif node.module:
                found.add(node.module)
    return found


def test_vim_package_has_no_forbidden_imports_statically():
    offenders: dict[str, set[str]] = {}
    for py in sorted(VIM_PACKAGE.glob("*.py")):
        bad = {
            name
            for name in _imported_modules(py)
            if name.split(".")[0] in _FORBIDDEN_ROOTS
        }
        if bad:
            offenders[py.name] = bad
    assert offenders == {}, offenders


def test_vim_package_never_imports_ui_db_or_sql():
    """`ui/` and `db/` for §5's arrow; **`sql/` because no v1 motion may consume
    the span model** (see the module docstring)."""
    for py in sorted(VIM_PACKAGE.glob("*.py")):
        for name in _imported_modules(py):
            assert not name.startswith("pgtp_editor.ui"), (py.name, name)
            assert not name.startswith("pgtp_editor.db"), (py.name, name)
            assert not name.startswith("pgtp_editor.sql"), (py.name, name)


def test_importing_the_package_loads_no_pyside6_module():
    """A fresh interpreter importing `pgtp_editor.vim` must stay Qt-free."""
    script = (
        "import sys, json\n"
        "import pgtp_editor.vim as vim\n"
        "grammar = vim.VimGrammar()\n"
        "assert grammar.feed('4') is None\n"
        "assert grammar.feed('2') is None\n"
        "assert grammar.feed('j').count == 42\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] "
        "in ('PySide6', 'PyQt5', 'PyQt6', 'shiboken6'))))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == []


def test_the_package_does_not_import_sql_at_runtime_either():
    """A static check catches an `import`; this catches a lazy one."""
    script = (
        "import sys, json\n"
        "import pgtp_editor.vim\n"
        "print(json.dumps([m for m in sys.modules if m.startswith('pgtp_editor.sql')]))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == []


def test_the_phrase_normal_mode_is_written_nowhere_in_the_package():
    """**Terminology is owner-agreed and load-bearing.** The two editing modes are
    *Edit mode* and *Command mode*, and the phrase *"normal mode"* is never
    written -- in code, comments or tests -- because it collides with vim's own
    NORMAL and would make every sentence ambiguous about which vocabulary it
    speaks. (The word may appear in a sentence that says exactly this; what is
    forbidden is USING it as the mode's name, and no identifier may carry it.)"""
    for py in sorted(VIM_PACKAGE.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        assert "normal mode" not in text.lower(), py.name
        tree = ast.parse(text, filename=str(py))
        for node in ast.walk(tree):
            name = getattr(node, "name", None) or getattr(node, "id", None)
            if isinstance(name, str):
                assert "normal" not in name.lower(), (py.name, name)


def test_public_api_surface_is_the_documented_one():
    import pgtp_editor.vim as vim

    assert set(vim.__all__) == {
        "CHAR_MOTIONS",
        "CLASS_KEYWORD",
        "CLASS_PUNCTUATION",
        "CLASS_WHITESPACE",
        "Command",
        "INCLUSIVE_MOTIONS",
        "INSERT_ENTRY_ACTIONS",
        "LINEWISE",
        "OPERATORS",
        "REDO_KEY",
        "SIMPLE_MOTIONS",
        "VimGrammar",
        "char_class",
        "word_backward",
        "word_end",
        "word_forward",
    }
    for name in vim.__all__:
        assert hasattr(vim, name), name
