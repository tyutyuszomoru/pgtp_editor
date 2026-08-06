"""Guard the re-export surface of ``pgtp_editor.ui.modals``.

``modals`` is the single, stable patch target every collaborator reaches modal
Qt through (see the module docstring and ``CLAUDE.md``'s rule that no test may
reach an un-patched modal Qt call). These tests pin that surface so it can
neither silently diverge from Qt — a wrapper or shim sneaking in would break
whole-object patches like ``patch("pgtp_editor.ui.modals.QMessageBox", Fake)``
— nor grow exports nothing actually calls.
"""

from PySide6 import QtGui, QtWidgets

from pgtp_editor.ui import modals

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
