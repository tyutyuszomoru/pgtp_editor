"""`pgtp_editor.sql` must stay a pure, Qt-free core (spec §18.4 + §5's dependency rule).

The formatter core is meant to be callable from anywhere -- including from code
that must not drag PySide6 in -- and §18.4 relocated `SQL_KEYWORDS` out of
`ui/code_editor.py` precisely so `sql/` never imports upward into `ui/`. Both
halves of that promise are checked here: statically (no Qt/DB/network import
statement anywhere in the package) and at runtime (importing the package in a
**fresh interpreter** loads no PySide6 module at all -- an in-process check
would be meaningless because the rest of the suite imports Qt).
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_PACKAGE = REPO_ROOT / "pgtp_editor" / "sql"

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
            if node.level:  # relative import inside pgtp_editor.sql
                found.add("." * node.level + (node.module or ""))
            elif node.module:
                found.add(node.module)
    return found


def test_sql_package_has_no_forbidden_imports_statically():
    offenders: dict[str, set[str]] = {}
    for py in sorted(SQL_PACKAGE.glob("*.py")):
        bad = {
            name
            for name in _imported_modules(py)
            if name.split(".")[0] in _FORBIDDEN_ROOTS
        }
        if bad:
            offenders[py.name] = bad
    assert offenders == {}, offenders


def test_sql_package_never_imports_upward_into_ui_or_db():
    for py in sorted(SQL_PACKAGE.glob("*.py")):
        for name in _imported_modules(py):
            assert ".ui" not in name, (py.name, name)
            assert ".db" not in name, (py.name, name)
            assert not name.startswith("pgtp_editor.ui"), (py.name, name)
            assert not name.startswith("pgtp_editor.db"), (py.name, name)


def test_importing_the_package_loads_no_pyside6_module():
    """A fresh interpreter importing `pgtp_editor.sql` must stay Qt-free."""
    script = (
        "import sys, json\n"
        "import pgtp_editor.sql\n"
        "assert pgtp_editor.sql.format_selection('select 1').ok\n"
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


def test_public_api_surface_is_the_documented_one():
    import pgtp_editor.sql as sql

    # FQ-033 widened the pinned surface to SIX: both hosts and the Autoformatter
    # settings dialog construct a config, and the facade is where they read it
    # from. The per-rule record types (`KeywordCase`, `ClauseRule`) deliberately
    # stay off it, reached through `pgtp_editor.sql.format_config` the way
    # `tokenize`/`Token` are reached through `pgtp_editor.sql.tokenizer`.
    assert set(sql.__all__) == {
        "format_selection",
        "FormatResult",
        "Issue",
        "SQL_KEYWORDS",
        "FormatConfig",
        "DEFAULT_FORMAT_CONFIG",
    }
    for name in sql.__all__:
        assert hasattr(sql, name), name
