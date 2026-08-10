"""Guard the re-export surface of ``pgtp_editor.ui.modals``.

``modals`` is the single, stable patch target every collaborator reaches modal
Qt through (see the module docstring and ``CLAUDE.md``'s rule that no test may
reach an un-patched modal Qt call). These tests pin that surface so it can
neither silently diverge from Qt — a wrapper or shim sneaking in would break
whole-object patches like ``patch("pgtp_editor.ui.modals.QMessageBox", Fake)``
— nor grow exports nothing actually calls.
"""

import io
import pathlib
import tokenize

from PySide6 import QtGui, QtWidgets

from pgtp_editor.ui import modals

UI_DIR = pathlib.Path(modals.__file__).parent

# The exact modal entry points in use, and where each one really comes from.
EXPECTED = {
    "QDesktopServices": QtGui,
    "QFileDialog": QtWidgets,
    "QInputDialog": QtWidgets,
    "QMessageBox": QtWidgets,
}


def test_every_expected_name_is_present():
    for name in EXPECTED:
        assert hasattr(modals, name), f"modals is missing {name}"


def test_each_name_is_the_identical_qt_object():
    """Re-export, not wrapper: identity with the PySide6 class."""
    for name, source in EXPECTED.items():
        assert getattr(modals, name) is getattr(source, name), (
            f"modals.{name} is not the same object as {source.__name__}.{name}"
        )


def test_all_matches_the_expected_set_exactly():
    """No unused exports, no undeclared ones."""
    assert sorted(modals.__all__) == sorted(EXPECTED)


def test_no_extra_public_qt_names_leak_in():
    public_qt = {
        name
        for name in vars(modals)
        if name.startswith("Q") and not name.startswith("_")
    }
    assert public_qt == set(EXPECTED)


def test_module_docstring_explains_why_it_exists():
    doc = modals.__doc__ or ""
    assert "patch" in doc
    assert "attribute access" in doc.lower()


# --- the decomposition surface really goes through modals -------------------


def _code_tokens(path: pathlib.Path) -> list[tokenize.TokenInfo]:
    """Every token except comments and string literals, so a module explaining
    in prose why it must not name ``QMessageBox`` directly does not fail these
    checks (the same tokenizing rule ``test_collaborator_boundaries.py`` uses)."""
    with path.open("rb") as handle:
        source = handle.read().decode("utf-8")
    return [
        token
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    ]


def _decomposition_modules() -> list[pathlib.Path]:
    """``main_window.py`` plus every collaborator carved out of it, discovered by
    glob so later extraction waves are covered without editing this test."""
    return [UI_DIR / "main_window.py", *sorted(UI_DIR.glob("*_controller.py"))]


def test_the_host_and_its_collaborators_reach_modal_qt_only_through_modals():
    """The load-bearing invariant of the ``ui/modals.py`` conversion: while
    ``main_window.py`` is being split up, a modal name must never be bound
    locally in the host or in a collaborator, because ~200 tests patch these
    through ``modals`` and a local binding would keep them PASSING while
    testing nothing -- and could let an offscreen run reach a real modal.

    Deliberately scoped to the decomposition surface. Six leaf dialogs
    (``about``, ``php_file_tab``, ``new_project_dialog``, ``new_trigger_dialog``,
    ``caption_management_panel``, ``ddl_object_editor``)
    are known to call modal Qt directly and are not covered by this rule.
    """
    offenders: list[str] = []
    for path in _decomposition_modules():
        tokens = _code_tokens(path)
        for index, token in enumerate(tokens):
            if token.type != tokenize.NAME or token.string not in EXPECTED:
                continue
            previous = tokens[index - 1] if index else None
            if previous is not None and previous.string == ".":
                continue  # modals.QMessageBox -- the required form
            offenders.append(f"{path.name}:{token.start[0]} bare {token.string}")
    assert offenders == [], "modal Qt must be reached as modals.<Name>: " + "; ".join(
        offenders
    )


def test_the_guard_covers_main_window_and_the_extracted_controllers():
    """A glob that silently matched nothing would make the rule above vacuous."""
    names = {path.name for path in _decomposition_modules()}
    assert "main_window.py" in names
    assert len(names) > 3
