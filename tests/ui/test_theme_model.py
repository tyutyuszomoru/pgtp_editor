"""The file-based `Theme` object — FQ-260812021715.

Three things are proved here, in this order of importance:

1. **The package-wide guard** (bottom of the file): no module outside the theme
   source declares a colour — a hex in ANY notation, or a CSS colour name in a
   style declaration. (It began as `#rrggbb` only; BUG-260812063745 widened it
   after a `#b8860b` literal was "fixed" by respelling it `darkorange`, which
   made the guard green and left the defect exactly in place.) That is the
   feature's real deliverable — it is
   what makes the next "second colour table beside the real one" impossible
   rather than merely discouraged, which is the mistake `mode_indicator.py`'s
   docstring exists to record and which this codebase has made repeatedly.
2. **Faithful extraction** — every colour in the two bundled theme files equals
   the value that was hardcoded before the consolidation, and the recoloured
   qdarkstyle stylesheet is BYTE-IDENTICAL to the stock one. A refactor that
   changes a pixel is not a refactor.
3. **The file drives the pixels** — colours are asserted as RENDERED pixels
   read back against the value parsed out of the theme JSON, each with a
   presence anchor proving the sampler can see the colour at all.
"""
import ast
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from PySide6.QtGui import QColor

from pgtp_editor.ui import theme as theme_mod
from pgtp_editor.ui import theme_model
from pgtp_editor.ui.theme_model import (
    SyntaxRole,
    Theme,
    ThemeError,
    available_themes,
    bundled_themes_dir,
    duplicate,
    load_theme,
    load_theme_file,
    shared_accent,
    theme_for,
)


def theme_json(name: str) -> dict:
    """The bundled theme file's raw JSON — the file, not the parsed object, so
    an assertion cannot be satisfied by the loader agreeing with itself."""
    return json.loads((bundled_themes_dir() / f"{name}.json").read_text(encoding="utf-8"))


def rendered(colour: str) -> str:
    """A colour spelled the way `QImage.pixelColor().name()` spells it (lower
    case `#rrggbb`). Theme files mix cases, and a raw string comparison against
    a pixel name silently never matches."""
    return QColor(colour).name()


def pixel_counts(widget) -> Counter:
    """`{'#rrggbb': how many pixels}` for what the widget actually renders."""
    image = widget.grab().toImage()
    counts: Counter = Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            counts[image.pixelColor(x, y).name()] += 1
    return counts


# ---------------------------------------------------------------------------
# The model: loading, validating, discovering
# ---------------------------------------------------------------------------

def test_both_bundled_themes_load_and_declare_their_lightness():
    dark = load_theme("dark")
    light = load_theme("light")
    assert (dark.name, dark.light) == ("Dark", False)
    assert (light.name, light.light) == ("Light", True)
    assert dark.qdarkstyle_base == "dark" and light.qdarkstyle_base == "light"


def test_every_bundled_theme_carries_every_required_colour():
    """A theme file missing a key must fail to LOAD, not paint black."""
    for name in ("dark", "light"):
        theme = load_theme(name)
        assert set(theme.chrome) == set(theme_model.CHROME_KEYS)
        assert set(theme.palette) == set(theme_model.PALETTE_ROLES)
        assert set(theme.palette_disabled) == set(theme_model.DISABLED_ROLES)
        assert set(theme.accents) == set(theme_model.ACCENT_KEYS)
        assert set(theme.decorations) == set(theme_model.DECORATION_KEYS)
        assert set(theme.modes) == set(theme_model.MODE_KEYS)
        assert set(theme.syntax) == set(theme_model.SYNTAX_ROLES)
        assert len(theme.syntax) == 8, "the 8 syntax roles are part of the theme"


def test_the_theme_model_is_QT_FREE_at_import():
    """The colour model must be loadable and testable without a QApplication —
    which is also what lets a future Themes pane edit a theme as plain data.
    `user_themes_dir`'s QStandardPaths lookup is a function-local import."""
    source = Path(theme_model.__file__).read_text(encoding="utf-8")
    module_level = [
        line for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "PySide6" in line
    ]
    assert module_level == [], module_level


def test_a_missing_colour_is_a_loud_ThemeError(tmp_path):
    data = theme_json("dark")
    del data["palette"]["Highlight"]
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ThemeError, match="palette.Highlight is missing"):
        load_theme_file(path)


def test_a_non_rrggbb_colour_is_a_loud_ThemeError(tmp_path):
    data = theme_json("dark")
    data["decorations"]["current_line"] = "rebeccapurple"
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ThemeError, match="not a #rrggbb colour"):
        load_theme_file(path)


def test_an_unknown_qdarkstyle_base_is_refused(tmp_path):
    """It selects a PRECOMPILED Qt resource, not a colour — qdarkstyle exits the
    process on an unknown ID, so this must be caught before it gets there."""
    data = theme_json("dark")
    data["qdarkstyle_base"] = "midnight"
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ThemeError, match="qdarkstyle_base"):
        load_theme_file(path)


def test_a_NEW_theme_FILE_becomes_a_selectable_theme_at_runtime(tmp_path):
    """The feature's headline requirement: drop a file in, get a theme — no
    restart, no registration, no code change."""
    assert available_themes([tmp_path]) == {}
    data = theme_json("dark")
    data["name"] = "Midnight"
    data["decorations"]["current_line"] = "#123456"
    (tmp_path / "midnight.json").write_text(json.dumps(data), encoding="utf-8")

    assert set(available_themes([tmp_path])) == {"midnight"}
    loaded = load_theme("midnight", [tmp_path])
    assert loaded.name == "Midnight"
    assert loaded.decoration("current_line") == "#123456"


def test_a_theme_file_edited_on_disk_is_re_read_without_a_restart(tmp_path):
    """The parse is cached on the file's stat, so the Themes pane's save is
    visible immediately — a cache keyed on the path alone would not be."""
    path = tmp_path / "midnight.json"
    data = theme_json("dark")
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_theme_file(path).decoration("current_line") == data["decorations"]["current_line"]

    data["decorations"]["current_line"] = "#abcdef"
    path.write_text(json.dumps(data) + " ", encoding="utf-8")
    assert load_theme_file(path).decoration("current_line") == "#abcdef"


def test_a_user_theme_file_SHADOWS_a_bundled_one_of_the_same_name(tmp_path):
    """Bundled first, user second — which is what makes "edit the theme you are
    using" possible without touching the install."""
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    (bundled / "dark.json").write_text(json.dumps(theme_json("dark")), encoding="utf-8")
    (user / "dark.json").write_text(json.dumps(theme_json("light")), encoding="utf-8")

    assert available_themes([bundled, user])["dark"] == user / "dark.json"


def test_duplicate_is_a_renamed_copy_with_no_source():
    """The `new = copy an existing one` primitive FQ-260812021716 rides on."""
    copy = duplicate(load_theme("dark"), "Midnight")
    assert copy.name == "Midnight"
    assert copy.source is None
    assert copy.chrome == load_theme("dark").chrome


def test_a_theme_round_trips_through_its_own_json(tmp_path):
    path = tmp_path / "round.json"
    original = load_theme("light")
    path.write_text(json.dumps(original.to_json()), encoding="utf-8")
    assert load_theme_file(path).to_json() == original.to_json()


def test_a_syntax_role_carries_the_three_weight_flags(tmp_path):
    data = theme_json("dark")
    data["syntax"]["code_comment"] = {
        "color": "#6a9955", "italic": True, "bold": True, "underline": True,
    }
    path = tmp_path / "flags.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    role = load_theme_file(path).role("code_comment")
    assert role == SyntaxRole("#6a9955", bold=True, italic=True, underline=True)


def test_shared_accent_RAISES_when_the_themes_disagree(monkeypatch):
    """A theme-blind consumer (`connectivity.py`'s dots) may only read an accent
    every theme agrees on. The day one theme gives it its own value, that
    consumer must fail loudly instead of silently painting the other theme's."""
    assert shared_accent("connectivity_offline") == theme_for(False).accent(
        "connectivity_offline"
    )
    divergent = Theme(**{**theme_for(True).to_json(),
                         "modes": theme_for(True).modes,
                         "syntax": theme_for(True).syntax,
                         "accents": {**theme_for(True).accents,
                                     "connectivity_offline": "#010203"}})
    monkeypatch.setattr(
        theme_model, "theme_for", lambda light: divergent if light else theme_for(False)
    )
    with pytest.raises(ThemeError, match="not theme-blind"):
        theme_model.shared_accent("connectivity_offline")


# ---------------------------------------------------------------------------
# Named selection, and the migration off the `lightTheme` boolean
# ---------------------------------------------------------------------------

@pytest.fixture
def _no_active_theme():
    """`theme_for` answers the app's `light: bool` seam with the ACTIVE theme, so
    a test that sets one must put it back or it leaks into every later palette
    assertion."""
    previous = theme_model.active_theme()
    try:
        yield
    finally:
        theme_model.set_active_theme(previous)


def test_theme_for_returns_the_ACTIVE_theme_when_the_lightness_matches(_no_active_theme):
    """The seam where a boolean becomes a `Theme` is where NAME-based selection
    drops in: there can be any number of themes but only one active one, so a
    caller asking about the side the app is on gets the app's actual theme."""
    midnight = theme_model.replace(load_theme("dark"), name="Midnight")
    theme_model.set_active_theme(midnight)
    assert theme_for(False) is midnight


def test_theme_for_falls_back_to_the_BUNDLED_pair_for_the_OTHER_side(_no_active_theme):
    """`PaletteChange` fires four times per flip and the first two report the OLD
    lightness, so a consumer WILL ask about the side the app is not on. Answering
    with the active theme's colours there would paint the new theme under the old
    palette for two events."""
    theme_model.set_active_theme(load_theme("dark"))
    assert theme_for(True).name == load_theme("light").name
    assert theme_for(True).light is True


def test_a_stored_NAME_wins_over_the_legacy_boolean():
    assert theme_model.migrated_theme_name("midnight", True) == "midnight"
    assert theme_model.migrated_theme_name("midnight", False) == "midnight"


def test_the_legacy_boolean_migrates_onto_a_bundled_theme_NAME():
    """The migration for an existing install: someone with `lightTheme=true`
    stored must land on the LIGHT theme, not on a default."""
    assert theme_model.migrated_theme_name(None, True) == "light"
    assert theme_model.migrated_theme_name("", True) == "light"
    assert theme_model.migrated_theme_name(None, False) == "dark"
    assert theme_model.migrated_theme_name(None, None) == "dark"


def test_resolve_theme_falls_back_rather_than_raising():
    """The user deleted or broke the theme file they had selected. The default
    theme is a far better answer than a startup crash — and the name actually
    used comes back, so the caller persists what it applied."""
    assert theme_model.resolve_theme("light")[0] == "light"
    name, theme = theme_model.resolve_theme("no-such-theme")
    assert name == "dark" and theme.light is False


@pytest.mark.parametrize("display,stem", [
    ("My Theme", "my-theme"),
    ("  Solarized   Dark  ", "solarized-dark"),
    ("../../etc/passwd", "etc-passwd"),
    ("Ünïcode 2", "ünïcode-2"),  # letters are kept, whatever alphabet
])
def test_a_display_name_becomes_a_SAFE_file_stem(display, stem):
    """A theme's identity IS its file stem — it is what `available_themes` keys
    on and what QSettings persists — so a name must not be able to escape the
    themes directory or produce a stem selection cannot round-trip."""
    assert theme_model.theme_stem(display) == stem


def test_an_unusable_name_is_refused_rather_than_becoming_dot_json():
    with pytest.raises(ThemeError):
        theme_model.theme_stem("   ")


def test_a_saved_theme_lands_in_the_USER_directory_and_loads_back(monkeypatch, tmp_path):
    """Always the user directory, never `theme.source`: saving a duplicate of a
    bundled theme must not write into the install."""
    monkeypatch.setattr(theme_model, "user_themes_dir", lambda: tmp_path)
    copy = duplicate(load_theme("dark"), "Midnight")
    path = theme_model.save_theme(copy, "midnight")

    assert path == tmp_path / "midnight.json"
    assert theme_model.available_themes()["midnight"] == path
    assert load_theme_file(path).to_json() == copy.to_json()


def test_is_bundled_separates_the_install_from_the_users_own(monkeypatch, tmp_path):
    monkeypatch.setattr(theme_model, "user_themes_dir", lambda: tmp_path)
    assert theme_model.is_bundled(load_theme("dark")) is True
    theme_model.save_theme(duplicate(load_theme("dark"), "Midnight"), "midnight")
    assert theme_model.is_bundled(load_theme("midnight")) is False


# ---------------------------------------------------------------------------
# Faithful extraction: the consolidation changed NO colour
# ---------------------------------------------------------------------------

#: Every colour that was hardcoded in the tree before FQ-260812021715,
#: transcribed from the pre-refactor source. If an extraction ever drifts, this
#: is the assertion that says so — and it must be corrected by fixing the theme
#: file, never by editing the expectation.
PRE_REFACTOR = {
    "dark": {
        ("palette", "Window"): "#2B2B2B",
        ("palette", "Base"): "#1E1E1E",
        ("palette", "Highlight"): "#3874F2",
        ("palette", "Link"): "#6CB6FF",
        ("palette", "BrightText"): "#FF5C5C",
        ("palette_disabled", "Text"): "#6E6E6E",
        ("accents", "command_caret_background"): "#FFA500",
        ("accents", "command_caret_foreground"): "#1E1E1E",
        ("accents", "status_warning"): "#e0a83a",
        ("accents", "connectivity_offline"): "#D02020",
        ("accents", "connectivity_reachable"): "#2E9E4F",
        ("decorations", "current_line"): "#2d2d30",
        ("decorations", "error_line"): "#5a1d1d",
        ("decorations", "navigation_highlight"): "#264f78",
        ("decorations", "matching_tag"): "#3a5f3a",
        ("decorations", "code_region"): "#232a2f",
        ("decorations", "gutter_background"): "#2b2b2b",
        ("decorations", "gutter_foreground"): "#858585",
    },
    "light": {
        ("palette", "Window"): "#F0F0F0",
        ("palette", "Base"): "#FFFFFF",
        ("palette", "Highlight"): "#3874F2",
        ("palette", "Link"): "#0B3D91",
        ("palette", "BrightText"): "#FFFFFF",
        ("palette_disabled", "Text"): "#A0A0A0",
        ("accents", "command_caret_background"): "#E56A00",
        ("accents", "command_caret_foreground"): "#FFFFFF",
        ("accents", "status_warning"): "#8a5a00",
        ("accents", "connectivity_offline"): "#D02020",
        ("accents", "connectivity_reachable"): "#2E9E4F",
        ("decorations", "current_line"): "#eef1f7",
        ("decorations", "error_line"): "#f7d4d4",
        ("decorations", "navigation_highlight"): "#cfe0ff",
        ("decorations", "matching_tag"): "#d3ecd3",
        ("decorations", "code_region"): "#eef2f5",
        ("decorations", "gutter_background"): "#f0f0f0",
        ("decorations", "gutter_foreground"): "#888888",
    },
}

#: The mode-chip pairs as `mode_indicator.py` spelled them.
PRE_REFACTOR_MODES = {
    "light": {
        "none": ("#E8E8E8", "#3A3A3A"),
        "standalone": ("#E3F2FD", "#0D3B66"),
        "project": ("#E6F4EA", "#1B5E20"),
        "maintenance": ("#FDECEA", "#8B1E1E"),
    },
    "dark": {
        "none": ("#3A3A3A", "#D8D8D8"),
        "standalone": ("#1E3A5F", "#CFE3FF"),
        "project": ("#1E3A28", "#B6E3C0"),
        "maintenance": ("#3A2320", "#F2B8AE"),
    },
}

#: The syntax roles as `xml_editor.py` and `code_editor.py` spelled them. The
#: five `code_*` roles were THEME-BLIND (one hardcoded set), so BOTH themes must
#: carry the same values — giving light its own variant is a real colour change
#: and belongs to a follow-up, not to this refactor.
PRE_REFACTOR_SYNTAX = {
    "dark": {
        "xml_tag": "#569cd6", "xml_attr_name": "#9cdcfe", "xml_string": "#ce9178",
        "code_keyword": "#569cd6", "code_string": "#ce9178", "code_comment": "#6a9955",
        "code_number": "#b5cea8", "code_variable": "#9cdcfe",
    },
    "light": {
        "xml_tag": "#0000ff", "xml_attr_name": "#e50000", "xml_string": "#a31515",
        "code_keyword": "#569cd6", "code_string": "#ce9178", "code_comment": "#6a9955",
        "code_number": "#b5cea8", "code_variable": "#9cdcfe",
    },
}


@pytest.mark.parametrize("name", ("dark", "light"))
def test_the_extracted_theme_file_equals_the_pre_refactor_values(name):
    data = theme_json(name)
    for (section, key), expected in PRE_REFACTOR[name].items():
        assert data[section][key] == expected, f"{name}.{section}.{key}"
    for mode, pair in PRE_REFACTOR_MODES[name].items():
        assert tuple(data["modes"][mode]) == pair, f"{name}.modes.{mode}"
    for role, colour in PRE_REFACTOR_SYNTAX[name].items():
        assert data["syntax"][role]["color"] == colour, f"{name}.syntax.{role}"


def test_the_code_syntax_roles_are_IDENTICAL_in_both_themes():
    """The code highlighter was theme-blind, and the consolidation was not
    allowed to change a pixel. Giving the light theme its own code roles is the
    follow-up FQ-260812021715 anticipates — this pins that it has NOT happened
    silently, so the day it does, it is a deliberate, reviewed edit."""
    dark, light = theme_for(False), theme_for(True)
    for role in ("code_keyword", "code_string", "code_comment", "code_number",
                 "code_variable"):
        assert dark.role(role) == light.role(role), role


@pytest.mark.parametrize("name,stock", (("dark", "DarkPalette"), ("light", "LightPalette")))
def test_the_chrome_tokens_equal_qdarkstyles_own(name, stock):
    """The 16 `COLOR_*` tokens were borrowed wholesale from qdarkstyle; the
    extraction copied them, so the chrome cannot have moved."""
    import qdarkstyle.dark.palette
    import qdarkstyle.light.palette

    palette = getattr(
        qdarkstyle.dark.palette if name == "dark" else qdarkstyle.light.palette, stock
    )
    theme = load_theme(name)
    for key in theme_model.CHROME_KEYS:
        assert theme.chrome[key] == getattr(palette, key), key


@pytest.mark.parametrize("light", (True, False))
def test_the_recoloured_stylesheet_is_BYTE_IDENTICAL_to_the_stock_one(qapp, light):
    """The whole "no colour visibly changes" claim, made checkable.

    The bundled themes map every chrome token onto itself, so the substitution
    pass must be a no-op and the app's QSS must still start with exactly the
    string qdarkstyle produces — with only the app-authored focus tail after it.
    """
    import qdarkstyle
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette

    stock = qdarkstyle.load_stylesheet(
        qt_api="pyside6", palette=LightPalette if light else DarkPalette
    )
    produced = theme_mod._qdarkstyle_stylesheet(light)
    assert produced.startswith(stock)
    assert produced[len(stock):] == theme_mod._focus_visible_qss(
        theme_mod._ChromePalette(theme_for(light))
    )


def test_recolouring_ACTUALLY_recolours_when_the_theme_differs(qapp):
    """The identity case above cannot tell a working substitution from a dead
    one, so this drives a real remap — and it is the mechanism that matters,
    because qdarkstyle's own `palette=` argument CANNOT do this (see below)."""
    import qdarkstyle
    from qdarkstyle.dark.palette import DarkPalette

    stock = qdarkstyle.load_stylesheet(qt_api="pyside6", palette=DarkPalette)
    assert DarkPalette.COLOR_BACKGROUND_1.lower() in stock.lower()

    theme = theme_for(False)
    recoloured_theme = Theme(**{
        **theme.to_json(),
        "modes": theme.modes,
        "syntax": theme.syntax,
        "chrome": {**theme.chrome, "COLOR_BACKGROUND_1": "#010203"},
    })
    out = theme_mod._recolour_qss(stock, DarkPalette, recoloured_theme)
    assert "#010203" in out
    assert DarkPalette.COLOR_BACKGROUND_1.lower() not in out.lower()
    # Nothing else moved: another token is untouched.
    assert DarkPalette.COLOR_ACCENT_3.lower() in out.lower()


def test_qdarkstyles_own_palette_argument_does_NOT_recolour(qapp):
    """Documents WHY `_recolour_qss` exists rather than the mechanism the
    feature entry pinned. `qdarkstyle._load_stylesheet` reads a PRECOMPILED Qt
    resource picked by `palette.ID` and then **replaces the caller's palette
    object** with the stock one for that ID — so a subclass's overridden colours
    are discarded before one of them is read. Passing such a subclass silently
    produces the stock sheet, which is a refactor that looks like it worked."""
    import qdarkstyle
    from qdarkstyle.dark.palette import DarkPalette

    class Overridden(DarkPalette):
        COLOR_BACKGROUND_1 = "#010203"

    assert qdarkstyle.load_stylesheet(
        qt_api="pyside6", palette=Overridden
    ) == qdarkstyle.load_stylesheet(qt_api="pyside6", palette=DarkPalette)


# ---------------------------------------------------------------------------
# The file drives the RENDERED pixels
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("light", (True, False))
def test_the_mode_chip_PAINTS_the_theme_files_maintenance_colours(qtbot, qapp, light):
    from pgtp_editor.ui.mode_indicator import MODE_MAINTENANCE, ModeIndicator
    from pgtp_editor.ui.theme import apply_theme

    apply_theme(qapp, light)
    chip = ModeIndicator(light=light)
    qtbot.addWidget(chip)
    chip.set_mode(MODE_MAINTENANCE)
    chip.resize(240, 40)
    chip.show()
    qapp.processEvents()

    background, foreground = theme_json("light" if light else "dark")["modes"]["maintenance"]
    counts = pixel_counts(chip)
    # Presence anchor: the sampler can see the chip's background at all.
    assert counts[rendered(background)] > 100, dict(counts.most_common(4))
    assert counts[rendered(foreground)] > 0, dict(counts.most_common(4))


@pytest.mark.parametrize("light", (True, False))
def test_the_gutter_PAINTS_the_theme_files_gutter_background(qtbot, qapp, light):
    from pgtp_editor.ui.code_editor import CodeEditor
    from pgtp_editor.ui.theme import apply_theme

    apply_theme(qapp, light)
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor.setPlainText("select 1;\nselect 2;\nselect 3;\n")
    editor.resize(420, 160)
    editor.show()
    qapp.processEvents()

    expected = theme_json("light" if light else "dark")["decorations"]["gutter_background"]
    counts = pixel_counts(editor)
    assert counts[rendered(expected)] > 200, dict(counts.most_common(4))


@pytest.mark.parametrize("light", (True, False))
def test_the_xml_editor_PAINTS_the_theme_files_current_line_band(qtbot, qapp, light):
    from pgtp_editor.ui.theme import apply_theme
    from pgtp_editor.ui.xml_editor import XmlEditor

    apply_theme(qapp, light)
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("<a>\n<b/>\n</a>\n")
    editor.resize(420, 160)
    editor.show()
    qapp.processEvents()

    expected = theme_json("light" if light else "dark")["decorations"]["current_line"]
    counts = pixel_counts(editor)
    assert counts[rendered(expected)] > 100, dict(counts.most_common(4))


@pytest.mark.parametrize("light", (True, False))
def test_the_xml_syntax_colours_come_from_the_theme_file(qtbot, qapp, light):
    from pgtp_editor.ui.theme import apply_theme
    from pgtp_editor.ui.xml_editor import XmlEditor

    apply_theme(qapp, light)
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.apply_theme_colors(light)
    expected = theme_json("light" if light else "dark")["syntax"]
    assert editor._highlighter._tag_format.foreground().color().name() == rendered(
        expected["xml_tag"]["color"]
    )
    assert editor._highlighter._string_format.foreground().color().name() == rendered(
        expected["xml_string"]["color"]
    )


@pytest.mark.parametrize("light", (True, False))
def test_the_code_syntax_colours_come_from_the_theme_file(qtbot, qapp, light):
    from pgtp_editor.ui.code_editor import CodeEditor
    from pgtp_editor.ui.theme import apply_theme

    apply_theme(qapp, light)
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor._apply_syntax_theme_colors(light)
    expected = theme_json("light" if light else "dark")["syntax"]
    assert editor._highlighter._keyword_format.foreground().color().name() == rendered(
        expected["code_keyword"]["color"]
    )
    assert editor._highlighter._comment_format.foreground().color().name() == rendered(
        expected["code_comment"]["color"]
    )


def test_a_syntax_roles_italic_flag_reaches_the_text_format(qtbot, tmp_path):
    """The flags are not decoration on the model — they are applied."""
    from PySide6.QtGui import QTextCharFormat

    from pgtp_editor.ui.theme import apply_syntax_role

    fmt = QTextCharFormat()
    apply_syntax_role(fmt, SyntaxRole("#123456", bold=True, italic=True, underline=True))
    assert fmt.foreground().color().name() == "#123456"
    assert fmt.fontItalic() and fmt.fontUnderline()
    assert fmt.fontWeight() > 50

    # ...and cleared again, so "was italic once" cannot become sticky across a
    # theme flip (PaletteChange fires four times per flip).
    apply_syntax_role(fmt, SyntaxRole("#654321"))
    assert not fmt.fontItalic() and not fmt.fontUnderline()


def test_repeated_theme_flips_leave_the_decorations_at_the_LAST_theme(qtbot, qapp):
    """`PaletteChange` fires four times per flip and the first two report the
    OLD lightness, so every colour re-read must be idempotent and last-write-
    wins."""
    from pgtp_editor.ui.theme import apply_theme
    from pgtp_editor.ui.xml_editor import XmlEditor

    apply_theme(qapp, False)
    editor = XmlEditor()
    qtbot.addWidget(editor)
    for light in (True, False, True, True, False, False, True):
        editor.apply_theme_colors(light)
    expected = theme_json("light")["decorations"]["current_line"]
    assert editor._current_line_color.name() == rendered(expected)


# ---------------------------------------------------------------------------
# THE GUARD: colour literals live only in the theme source
# ---------------------------------------------------------------------------

#: Modules still allowed to spell a `#rrggbb`, each with the reason it is not a
#: theme colour or the reason it is not yet folded in. **This list may only ever
#: shrink.** Adding to it means adding a second colour table, which is the exact
#: failure this guard exists to prevent — extend a theme file instead.
COLOUR_LITERAL_EXEMPTIONS = {
    # NOT a colour choice: `#232629` is the literal token Breeze SVGs carry in
    # their embedded `.ColorScheme-Text { color:#232629 }` rule, which
    # `icons.py` SUBSTITUTES with the caller's colour. It is a sentinel being
    # matched, not a colour being painted, and the real colour comes from the
    # palette at the call site.
    "ui/icons.py",
    "ui/icon_picker_dialog.py",
    "ui/customize_toolbar_dialog.py",
    # Theme-BLIND panel colours not yet folded in: out of FQ-260812021715's
    # declared scope (which named the theme module, both editors, the two
    # highlighters, the mode indicator, the results panel and connectivity).
    # They are single hardcoded values with no per-theme variant, so folding
    # them in is a mechanical follow-up — each becomes an `accents` key with
    # the same value in both themes, exactly as the connectivity dots did.
    "ui/coherence_panel.py",
    "ui/caption_management_panel.py",
    "ui/activity_panel.py",
}

#: **Any** hex a module could paint with, not just `#rrggbb` — BUG-260812063745
#: found `#b33` (the status bar's DEBUG chip) sitting in plain sight, invisible
#: to the old `{6}`-only pattern. `{3,8}` covers `#rgb`, `#rgba`, `#rrggbb` and
#: `#rrggbbaa`, which is every notation Qt's stylesheet parser accepts.
_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")

#: One CSS declaration inside a string constant: the property name, then its
#: value up to the next `;` or brace. The guard is **declaration-scoped** for
#: colour NAMES because a bare word list over every string constant is
#: unusable — `tan`, `plum`, `linen`, `gold`, `snow`, `orange` and friends all
#: occur in ordinary prose, and `theme_model.py`'s own error message *"expected
#: a colour or a {color: ...} map"* would trip a naive scan. Scoping to a
#: declaration reduces the false-positive count to zero on the whole package.
_DECLARATION_RE = re.compile(
    r"(?:^|[;{])\s*(?:[-a-z]*color|background[-a-z]*|border[-a-z]*)\s*:\s*([^;{}]*)"
)

#: Tokens inside a declaration's value. `%s`, `{placeholder}` and `...` do not
#: match as bare words, which is what lets `mode_indicator.mode_stylesheet`'s
#: `color: %s` and every f-string hole through untouched — those resolve from
#: the theme at paint time and are the CORRECT shape.
_VALUE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")

#: The CSS named colours. This list lives in the TEST, not in `pgtp_editor/`:
#: it is a list of forbidden tokens, not a colour table, and putting a colour
#: table in the package to enforce "no colour tables in the package" would be
#: the joke writing itself. `transparent`, `currentColor`, `none` and `inherit`
#: are deliberately absent — they name no colour.
_CSS_COLOUR_NAMES = frozenset("""
aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond
blue blueviolet brown burlywood cadetblue chartreuse chocolate coral
cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray
darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey
darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue
firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod
gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon
lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue
lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue
mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen
mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod
palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum
powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon
sandybrown seagreen seashell sienna silver skyblue slateblue slategray
slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet
wheat white whitesmoke yellow yellowgreen
""".split())


def _docstring_ids(tree: ast.Module) -> set[int]:
    """The `Constant` nodes that are docstrings. PROSE about a colour is fine
    and often load-bearing (the contrast measurements in `sql_results_panel.py`
    and `theme.py` are the record of why a colour is what it is); a colour a
    module can PAINT is not."""
    found = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            found.add(id(first.value))
    return found


def colours_in_text(text: str) -> list[str]:
    """Every paintable colour in one string constant.

    **Two detectors, deliberately different in scope** (BUG-260812063745):

    * a **hex of any length**, anywhere in the string — a `#`-prefixed hex
      digit run is never anything but a colour in this package;
    * a **CSS colour NAME**, but only inside a style DECLARATION (`color:`,
      `background:`, `border:`). Unscoped, half the list is ordinary English.

    What this deliberately does NOT catch is the **indirect** form —
    `colour = "green" if ok else "red"` followed by
    `setStyleSheet(f"color: {colour};")`. The string `"green"` is not adjacent
    to any declaration, and telling it apart from any other pair of strings
    needs dataflow analysis, not a regex. **Do not re-open this by making the
    guard cleverer**: the answer is that the indirect form was deleted
    (BUG-260812063745 replaced both sites with a status *kind*), and the way to
    keep it deleted is to review, not to scan.
    """
    found = list(_HEX_RE.findall(text))
    for declaration in _DECLARATION_RE.finditer(text):
        found.extend(
            token
            for token in _VALUE_TOKEN_RE.findall(declaration.group(1))
            if token.lower() in _CSS_COLOUR_NAMES
        )
    return found


def colour_literals_in(path: Path) -> list[tuple[int, str]]:
    """Every colour a module could actually paint with: string literals,
    excluding docstrings. Comments are excluded for free (they are not in the
    AST), which is what lets `#:` documentation keep quoting real values."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_ids(tree)
    return [
        (node.lineno, match)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        for match in colours_in_text(node.value)
    ]


def test_the_colour_DETECTOR_itself_sees_what_it_claims_to():
    """The guard's own widening, verified — a guard that quietly matches
    nothing is precisely the failure mode BUG-260812063745 was about.

    The false-positive half matters as much as the true-positive half: `%s`,
    an f-string hole and `theme_model.py`'s `{color: ...}` prose all sit in
    shipped modules that must stay green without an exemption.
    """
    assert colours_in_text("color: green;") == ["green"]
    assert colours_in_text("color: darkorange;") == ["darkorange"]
    assert colours_in_text(
        "QLabel { color: white; background: #b33; padding: 1px 6px; }"
    ) == ["#b33", "white"]
    assert colours_in_text("#1a9e1a") == ["#1a9e1a"]
    # ...and the shapes that MUST fall through:
    assert colours_in_text("QLabel { color: %s; background: %s; }") == []
    assert colours_in_text("color: {colour};") == []
    assert colours_in_text("expected a colour or a {color: ...} map") == []
    assert colours_in_text("background: rgba(1, 2, 3, 4);") == []
    assert colours_in_text("a tan plum on white linen, snow and gold") == []
    # The indirect form is out of reach BY DESIGN — see `colours_in_text`.
    assert colours_in_text("green") == []


def test_NO_module_outside_the_theme_source_declares_a_colour():
    """**The feature's real deliverable.**

    This codebase grew a second colour table beside the real one repeatedly —
    `mode_indicator.py`'s docstring exists purely to record one of those, and
    FQ-260810165518 had to deliberately reuse `mode_colors`' red rather than
    derive a third. A convention cannot stop that; a failing test can. Colours
    live in `pgtp_editor/resources/themes/*.json` and nowhere else.
    """
    package = Path(theme_model.__file__).parent.parent
    offenders = {}
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(package).as_posix()
        if relative in COLOUR_LITERAL_EXEMPTIONS:
            continue
        found = colour_literals_in(path)
        if found:
            offenders[relative] = found
    assert offenders == {}, (
        "colour literals outside the theme files — add the colour to "
        "pgtp_editor/resources/themes/*.json and read it through theme_model "
        f"instead: {offenders}"
    )


def test_the_theme_MODULES_themselves_hold_no_colour_either():
    """Including `theme.py` and `theme_model.py`: the colours are in the FILES.
    A default baked into the loader is the second table wearing a disguise."""
    for module in (theme_mod, theme_model):
        assert colour_literals_in(Path(module.__file__)) == []


def test_every_exemption_is_REAL():
    """An exemption that no longer has a literal must be deleted, or the list
    stops meaning anything and quietly re-opens the door."""
    package = Path(theme_model.__file__).parent.parent
    stale = [
        relative for relative in COLOUR_LITERAL_EXEMPTIONS
        if not colour_literals_in(package / relative)
    ]
    assert stale == [], f"exemptions with nothing to exempt: {stale}"
