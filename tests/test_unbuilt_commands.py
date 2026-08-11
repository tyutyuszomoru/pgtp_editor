"""No user-facing string anywhere in the app names a command that does not exist.

`BUG-260811021816`: three strings in `ui/ddl_object_editor.py` sent the user to
`Database ▸ Compare Schemas…`, which has never been built (§18.3 is designed and
unshipped -- `db/schema_snapshot.py` has no menu entry, and
`MainWindow._build_database_menu` has no such action). An instruction pointing at
a menu item that is not there is worse than no instruction: the user stops
trusting the ones that are right.

`tests/ui/test_ddl_object_editor.py` pins the module the bug was found in. This
file is the reason the *next* one cannot ship somewhere else -- the same scan,
run over the whole package, because nothing about the defect was specific to that
module.

**How the scan works, and why it is not a grep.** The second offending site was
wrapped mid-phrase across two source lines (`"Database ▸ Compare "` +
`"Schemas… produces…"`), which a grep for the phrase never saw. Parsing with
`ast` joins implicitly concatenated fragments back into one literal, and
whitespace is normalized so a phrase broken *inside* a literal still reads as one
phrase. Docstrings are excluded on purpose: `_precondition_signature`'s docstring
names the unbuilt command precisely to tell the next reader not to re-add it, and
a docstring is not user-facing.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "pgtp_editor"

#: Commands that are specified but have never been built, so no string may send
#: a user to them. Add a row when a spec'd command is quoted before it ships;
#: delete a row when the command actually exists.
#:
#: **A command with a real widget is not on this list, however hard it is to
#: reach.** §18.3's `Save Migration As…` is deliberately absent: it exists as a
#: `QPushButton` in `ui/schema_compare_panel.py`, so a string naming it names
#: something a user can be looking at. The defect this guards is naming a
#: command that has *no* implementation at all, not naming one whose entry point
#: is still missing.
UNBUILT_COMMANDS = ("Compare Schemas", "Save Schema Snapshot")


def _source_files() -> list[Path]:
    return sorted(path for path in PACKAGE.rglob("*.py") if path.is_file())


def _non_docstring_literals(source: str) -> list[str]:
    tree = ast.parse(source)
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node not in docstrings
    ]


@pytest.mark.parametrize("command", UNBUILT_COMMANDS)
def test_no_module_in_the_package_names_an_unbuilt_command(command):
    offenders: list[str] = []
    for path in _source_files():
        for literal in _non_docstring_literals(path.read_text(encoding="utf-8")):
            if command in re.sub(r"\s+", " ", literal):
                offenders.append(f"{path.relative_to(PACKAGE.parent)}: {literal!r}")
    assert offenders == []


def test_the_scan_would_actually_catch_a_reintroduction():
    """The guard's own teeth. An "assert this string is absent" test passes
    forever if the scanner never sees anything -- including if `ast` stopped
    joining wrapped fragments, which is the exact shape that hid the second
    offending site from grep.
    """
    wrapped = (
        'def refuse():\n'
        '    """A docstring naming Compare Schemas is allowed."""\n'
        '    return ("Use Database ▸ Compare "\n'
        '            "Schemas… to sort this out.")\n'
    )
    literals = _non_docstring_literals(wrapped)
    hits = [
        text for text in literals if "Compare Schemas" in re.sub(r"\s+", " ", text)
    ]
    assert hits == ["Use Database ▸ Compare Schemas… to sort this out."]


def test_the_scan_reaches_every_module_not_just_one():
    """A scan over an empty file list is the other way this could be a false
    green."""
    files = _source_files()
    assert len(files) > 50
    assert PACKAGE / "ui" / "ddl_object_editor.py" in files
