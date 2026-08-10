"""`pgtp_editor.xmlfmt` must stay a pure, Qt-free core (§18.4 part C + §5's dependency rule).

The twin of `tests/sql/test_package_purity.py`, and for the same reasons: the
XML indenter is meant to be callable from anywhere -- including from code that
must not drag PySide6 in -- and it must never reach upward into `ui/` even
though the construct it lexes is the one `ui/xml_structure.py` also lexes.

Two extra guards specific to this package:

* **`lxml` is forbidden here**, though it is a declared dependency of the app.
  A formatter's normal input is a *fragment*, which is precisely what lxml
  cannot parse, and it normalizes on serialize -- which part C's rules 1-3
  forbid. Keeping the ban mechanical stops a future contributor from
  "simplifying" the scanner away.
* **the dependency direction is one-way**: `xmlfmt` imports `sql` (for the
  shared `FormatResult`/`Issue`), and `sql` must never import `xmlfmt`.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
XMLFMT_PACKAGE = REPO_ROOT / "pgtp_editor" / "xmlfmt"
SQL_PACKAGE = REPO_ROOT / "pgtp_editor" / "sql"

#: Import roots the pure core may never reach for (Qt, DB drivers, network, XML libs).
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
    "lxml",
    "xml",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                found.add("." * node.level + (node.module or ""))
            elif node.module:
                found.add(node.module)
    return found


def test_xmlfmt_package_has_no_forbidden_imports_statically():
    offenders: dict[str, set[str]] = {}
    for py in sorted(XMLFMT_PACKAGE.glob("*.py")):
        bad = {
            name for name in _imported_modules(py) if name.split(".")[0] in _FORBIDDEN_ROOTS
        }
        if bad:
            offenders[py.name] = bad
    assert offenders == {}, offenders


def test_xmlfmt_package_never_imports_upward_into_ui_or_db():
    for py in sorted(XMLFMT_PACKAGE.glob("*.py")):
        for name in _imported_modules(py):
            assert ".ui" not in name, (py.name, name)
            assert ".db" not in name, (py.name, name)
            assert not name.startswith("pgtp_editor.ui"), (py.name, name)
            assert not name.startswith("pgtp_editor.db"), (py.name, name)


def test_the_dependency_runs_one_way_only():
    """`xmlfmt` may import `sql`; `sql` may never import `xmlfmt`."""
    for py in sorted(SQL_PACKAGE.glob("*.py")):
        for name in _imported_modules(py):
            assert "xmlfmt" not in name, (py.name, name)


def test_importing_the_package_loads_no_pyside6_module():
    """A fresh interpreter importing `pgtp_editor.xmlfmt` must stay Qt-free."""
    script = (
        "import sys, json\n"
        "import pgtp_editor.xmlfmt as xmlfmt\n"
        "assert xmlfmt.format_xml_selection('<a><b/></a>', 0, 11).ok\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] "
        "in ('PySide6', 'PyQt5', 'PyQt6', 'shiboken6', 'lxml'))))\n"
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
    import pgtp_editor.xmlfmt as xmlfmt

    assert set(xmlfmt.__all__) == {
        "format_xml_selection",
        "XmlFormatConfig",
        "DEFAULT_XML_FORMAT_CONFIG",
        "FormatResult",
        "Issue",
    }
    for name in xmlfmt.__all__:
        assert hasattr(xmlfmt, name), name


def test_the_shared_refusal_types_are_the_sql_packages_own_objects():
    import pgtp_editor.sql as sql
    import pgtp_editor.xmlfmt as xmlfmt

    assert xmlfmt.FormatResult is sql.FormatResult
    assert xmlfmt.Issue is sql.Issue
