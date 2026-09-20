# tests/ui/test_status_colours.py
"""`ui/status_colours.py` — the three status KINDS, and the label that paints
one (BUG-260812063745).

The colours' *values* are proved as rendered pixels and as contrast ratios in
`tests/ui/test_theme.py`; what is proved HERE is the mechanism that keeps them
right over time — that a kind is remembered rather than a colour, that a theme
flip repaints, and that a widget which styles itself from its own
`changeEvent` does not recurse.
"""
import pytest
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.mode_indicator import (
    MODE_MAINTENANCE,
    MODE_PROJECT,
    mode_colors,
)
from pgtp_editor.ui.status_colours import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_WARNING,
    StatusLabel,
    status_colour,
)
from pgtp_editor.ui.theme import apply_theme
from pgtp_editor.ui.theme_model import theme_for


@pytest.mark.parametrize("light", [True, False], ids=["light", "dark"])
def test_no_status_colour_is_a_NEW_colour(light):
    """Every kind resolves to a value the theme file already owns. A fourth
    red, or a green spelled only here, is the "second colour table beside the
    real one" this project keeps re-growing (§18.7)."""
    assert status_colour(STATUS_ERROR, light) == mode_colors(light)[MODE_MAINTENANCE][1]
    assert status_colour(STATUS_OK, light) == mode_colors(light)[MODE_PROJECT][1]
    assert status_colour(STATUS_WARNING, light) == theme_for(light).accent(
        "status_warning"
    )


@pytest.mark.parametrize("kind", [STATUS_OK, STATUS_WARNING, STATUS_ERROR])
def test_every_kind_is_a_DIFFERENT_value_in_the_two_themes(kind):
    """If a kind ever resolved to one value for both themes, `shared_accent`
    would have been the right reader and this whole module would be
    unnecessary. It does not: each kind is a per-theme pair, which is exactly
    why `shared_accent` (which RAISES unless the themes agree) must not be
    used here."""
    assert status_colour(kind, True) != status_colour(kind, False)


def test_the_ordinary_status_has_no_colour_of_its_own():
    """Neutral clears the sheet rather than naming a colour, so the label falls
    back to the app-wide QSS text colour — the right neutral in both themes."""
    assert status_colour(None, True) is None
    assert status_colour(None, False) is None


def test_a_status_label_remembers_the_KIND_not_the_colour(qtbot):
    """The stored value must be re-resolvable. A stored `QColor` re-applied
    after a theme flip paints the PREVIOUS theme's value — a shipped bug
    (BUG-260811021804 step 4), not a hypothetical."""
    label = StatusLabel("something went wrong")
    qtbot.addWidget(label)
    label.set_status_kind(STATUS_ERROR)
    assert label.status_kind() == STATUS_ERROR
    label.set_status_kind(None)
    assert label.status_kind() is None
    assert label.styleSheet() == ""


def test_a_theme_flip_REPAINTS_an_open_dialogs_status_label(qtbot, qapp):
    """The gotcha this widget exists to make unrepeatable: the Themes pane
    (FQ-260812021716) makes a flip-while-a-dialog-is-open reachable, and a
    label that kept the old theme's red would be unreadable rather than merely
    wrong.

    Both directions are exercised. Only dark -> light regressed in
    development, because the change event carrying the NEW palette is the
    NESTED one there, which the re-entrancy guard suppresses — hence the queued
    re-apply in `_apply_status_colour`'s caller.
    """
    apply_theme(qapp, True)
    label = StatusLabel("connection refused")
    qtbot.addWidget(label)
    label.show()
    qtbot.waitExposed(label)
    label.set_status_kind(STATUS_ERROR)
    assert status_colour(STATUS_ERROR, True) in label.styleSheet()

    for light in (False, True, False):
        apply_theme(qapp, light)
        QApplication.processEvents()
        assert status_colour(STATUS_ERROR, light) in label.styleSheet(), (
            f"stale colour after flipping to {'light' if light else 'dark'}"
        )
    apply_theme(qapp, False)


def test_a_HIDDEN_status_label_survives_a_theme_flip_without_recursing(qtbot, qapp):
    """A dialog that has been closed but is still alive keeps receiving palette
    changes, and this widget styles ITSELF from its own `changeEvent` —
    `setStyleSheet` re-polishes, which posts the event straight back.

    Measured before the `_applying` guard: `RecursionError` at ~128 frames on
    every flip. Qt CATCHES that and prints it, so the failure mode is silent
    stack thrash, not a red test — which is why this test asserts on
    `sys.setrecursionlimit`-independent evidence (it simply completes) and on
    the final value still being correct.
    """
    apply_theme(qapp, True)
    label = StatusLabel("boom")
    qtbot.addWidget(label)
    label.show()
    qtbot.waitExposed(label)
    label.set_status_kind(STATUS_ERROR)
    label.hide()

    for light in (False, True, False, True):
        apply_theme(qapp, light)
        QApplication.processEvents()

    assert label.status_kind() == STATUS_ERROR
    assert status_colour(STATUS_ERROR, True) in label.styleSheet()
    apply_theme(qapp, False)
