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

"""Light/Dark theme support (Sub-project D, #9) — the Qt half of the theme.

**Every colour this module paints comes from a FILE**, via
`ui/theme_model.py`'s `Theme` object (FQ-260812021715). This module holds no
colour literal of its own and must never grow one: it turns a `Theme` into the
three things Qt understands — a `QPalette`, a recoloured qdarkstyle stylesheet,
and the app-authored focus tail — and `apply_theme` remains the single point
that mutates the running `QApplication`.

Kept pure where it can be: ``light_palette()``/``dark_palette()`` build and
return a `QPalette` without touching any application state, so tests assert
palette roles rather than pixels.

**How chrome recolouring actually works, and why it is NOT qdarkstyle's
`palette=` argument.** The obvious mechanism — subclass `qdarkstyle.Palette`,
override the colours, pass it to `load_stylesheet(palette=...)` — **does not
work in qdarkstyle 3.2.3 and silently does nothing.** Its `_load_stylesheet`
reads the QSS out of a *precompiled Qt resource* chosen by `palette.ID`, and
then **replaces the caller's palette object** with the stock `DarkPalette` or
`LightPalette` for that ID (``elif palette.ID == 'dark': palette =
DarkPalette``). A subclass's overridden colours are therefore discarded before a
single one is read; only the ID survives. So the recolouring is a substitution
pass over the loaded QSS text (`_recolour_qss`), mapping each of the stock
palette's 16 `COLOR_*` literals to the theme's. A theme names which of the two
compiled sheets it starts from (`Theme.qdarkstyle_base`) purely to pick the
resource — never the colours.

Every NON-colour token stays at the qdarkstyle default: no shapes, no border
radii, no padding, no spacing and no hand-authored widget QSS. "We use the
qdarkstyle style, separate the colours, change only colours."
"""
import re

from PySide6.QtGui import QColor, QFont, QPalette

from . import theme_model
from .theme_model import Theme, theme_for


def qpalette_for(theme: Theme) -> QPalette:
    """Build a COMPLETE `QPalette` from `theme`. Pure: constructs and returns a
    fresh palette, mutating nothing.

    Every role the app actually surfaces is set explicitly -- including the
    ``Link`` role (navy in the light theme) so About-box hyperlinks read on
    white instead of inheriting the dark-theme cyan, and the Disabled colour
    group so greyed-out controls stay legible under the Fusion style. The role
    list is `theme_model.PALETTE_ROLES`, and a theme file missing any of them
    fails to load, so a partially-painted palette cannot ship.
    """
    palette = QPalette()
    role = QPalette.ColorRole
    for name in theme_model.PALETTE_ROLES:
        palette.setColor(getattr(role, name), QColor(theme.palette[name]))
    group = QPalette.ColorGroup.Disabled
    for name in theme_model.DISABLED_ROLES:
        palette.setColor(group, getattr(role, name), QColor(theme.palette_disabled[name]))
    return palette


def light_palette() -> QPalette:
    """The bundled Light theme's `QPalette` -- white/near-white backgrounds,
    dark text, navy links."""
    return qpalette_for(theme_for(True))


def dark_palette() -> QPalette:
    """The bundled Dark theme's `QPalette` -- dark backgrounds, light text,
    light-cyan links: the explicit, tested "Light Theme off" state (BUG-004).

    Previously "off" simply restored whatever the native/OS style happened to
    render at startup, which only looked dark on the one platform (Windows) the
    toggle was originally built and tested against; on any other native-style
    baseline, toggling the light theme off produced no reliably-dark result at
    all. Mirrors ``light_palette()``'s structure and role coverage so both
    states are equally complete and tested."""
    return qpalette_for(theme_for(False))


def command_caret_colors(light: bool) -> tuple[str, str]:
    """The `(background, foreground)` for the vim Command-mode block caret.

    Pure -- returns the pair for the theme, mutating nothing, exactly as
    `light_palette()`/`dark_palette()` do with their QPalette and as
    `mode_indicator.mode_colors()` does with its dict.

    Read from the theme file's `accents` (BUG-260812001031 moved it out of
    `vim_mode.py`; FQ-260812021715 moved it out of this module's source), because
    a per-theme colour table anywhere but the theme file is how a theme stops
    being theme-able -- the mistake `mode_indicator.py`'s docstring records.

    Deliberately NOT the selection blue (`Highlight`): the caret must be readable
    AS a mode cue while a selection is on screen beside it, which a second blue
    would not be. No palette role carries this orange, so it is a real accent
    rather than a derivation -- which is why it is in `accents` and not
    `palette`.
    """
    theme = theme_for(light)
    return (
        theme.accent("command_caret_background"),
        theme.accent("command_caret_foreground"),
    )


# Cached QDarkStyleSheet text, one per theme (BUG-010; extended for the light
# QSS below). Loaded lazily -- qdarkstyle warns if loaded before a
# QApplication exists, and apply_theme always runs with one.
_qss_cache: dict[bool, str] = {}

#: Marker selector for the app-authored keyboard-focus rule appended to
#: qdarkstyle's QSS. Tests assert on this rather than re-spelling the text.
FOCUS_RULE_SELECTOR = "QPushButton:focus, QToolButton:focus"

#: Per-edge mapping for the tab-bar focus cue (BUG-260812004649): the QSS edge
#: pseudo-state -> the border side qdarkstyle's matching ``:selected`` rule
#: already paints 3px of accent on (always the side facing the tab pane).
#: The focus rule recolours exactly that border and touches nothing else.
FOCUS_TAB_EDGES: dict[str, str] = {
    "top": "border-bottom",
    "bottom": "border-top",
    "left": "border-right",
    "right": "border-left",
}


def focus_tab_selector(edge: str) -> str:
    """The full selector list the tab focus rule for ``edge`` is emitted under.

    Tests assert on this rather than re-spelling the text -- and it is a list,
    not a single selector, because qdarkstyle scopes a parallel
    ``QDockWidget QTabBar::tab...`` arm throughout for Qt's tabified-dock bars
    (which are ``South``-shaped, hence ``:bottom`` earning its rule even though
    the app calls ``setTabPosition`` nowhere)."""
    return (
        f"QTabBar::tab:{edge}:selected:focus, "
        f"QDockWidget QTabBar::tab:{edge}:selected:focus"
    )


def _focus_visible_tab_qss(pal) -> str:
    """The tab-bar half of the focus tail (BUG-260812004649).

    qdarkstyle ships ``QTabBar::tab:<edge>``, ``:selected``, ``:!selected``,
    ``:!selected:hover`` and the ``:disabled`` variants -- and **no** ``:focus``
    selector of any kind, so a focused tab bar paints identically to an
    unfocused one. Tab-traversal lands on a ``QTabBar`` three times per cycle on
    a real window (the ``CenterStage`` document tabs, the left dock and the
    bottom dock), and nothing tells the user the arrow keys are now live.

    **``:selected:focus``, not ``:focus``, and that is not a style choice.**
    ``QTabBar`` takes focus as a whole widget and Qt sets ``State_HasFocus`` on
    the style option of the **current** tab only -- rendered proof: painting
    ``:selected:focus`` vs ``:!selected:focus`` gives 617px and 0px. The
    pseudo-state cannot reach an unselected tab, and it does not need to:
    selection follows focus in a ``QTabBar`` (arrows move ``currentIndex``
    directly), so "where you are" is always the selected tab. A bare
    ``QTabBar::tab:focus`` is additionally **dead** here -- the same loud rule
    paints 1342px standalone and **0px** once qdarkstyle applies, because its
    ``:<edge>:selected`` outranks it on specificity. That is a rule which passes
    a stylesheet-string test while painting nothing.

    **The box does not move.** Only ONE ``border-<side>`` colour is set, on the
    3px border qdarkstyle's ``:selected`` rule already draws; no ``border``
    shorthand, no ``padding``/``margin``/``outline``. Any of those does move it:
    a naive ``border: 2px`` rule takes tabs from 37px to 41px wide and shifts
    every following tab, and ``padding: 0`` overshoots to 33px (tab padding is
    per-edge and asymmetric, so the button fix's compensation does not transfer).
    Measured with these rules: ``tabRect()`` is identical focused and unfocused,
    with 28 ring pixels appearing on the selected tab's pane-facing edge only.

    **The selection accent is REPLACED while focused, not overlaid -- do not
    "restore" it.** Selected-ness is still carried by the tab background
    (``#54687A`` vs ``#455364`` in dark) and by ``margin-top``, so nothing is
    lost. The colour is ``COLOR_TEXT_1``, the precedent the button rule set:
    4.40:1 dark / 7.97:1 light against the selected tab, 5.98:1 / 9.07:1 against
    its unselected neighbours. ``COLOR_ACCENT_3`` is rejected here for the same
    reason as on buttons -- 1.15:1 / 1.08:1.

    No ``:hover`` interaction to reconcile: qdarkstyle's hover rule is
    ``:!selected:hover`` and this one is ``:selected:focus`` -- disjoint by
    construction. Appended after qdarkstyle's text so it wins by order against
    ``:<edge>:selected`` at equal specificity."""
    return "".join(
        f"\n{focus_tab_selector(edge)} {{\n"
        f"  {side}: 3px solid {pal.COLOR_TEXT_1};\n"
        f"}}\n"
        for edge, side in FOCUS_TAB_EDGES.items()
    )


def _focus_visible_qss(pal) -> str:
    """The app-authored tail appended to qdarkstyle's QSS so a keyboard-focused
    button is VISIBLE (BUG-260812002838) -- and, via
    ``_focus_visible_tab_qss``, so is a keyboard-focused tab bar
    (BUG-260812004649). One tail, one cached string per theme.

    qdarkstyle styles ``QPushButton``/``QToolButton`` with ``outline: none;
    border: none;`` and supplies ``:hover``/``:pressed``/``:checked`` but **no**
    ``:focus`` rule -- so Tab-focusing a button paints it identically to an
    unfocused one (no hover background, and the native focus rectangle is
    suppressed by ``outline: none``). It does style ``:focus`` for text inputs
    (``QLineEdit``/``QTextEdit``/``QComboBox``/the item views) and ships
    focus-variant icons for check boxes and radio buttons, which is why only
    the two button classes are dark here. This adds the missing rule for both,
    for both themes.

    **The colour is the button's own text colour** (``COLOR_TEXT_1``), not the
    accent used for input focus. The bug entry proposed ``COLOR_ACCENT_3`` to
    match ``QLineEdit:focus``, but that accent is chosen to read against an
    *input* background, and measured against a *button* background it fails
    even 3:1 in both themes -- dark ``#1A72BB`` on ``#455364`` is 1.56:1 and
    light ``#73C7FF`` on ``#C0C4C8`` is 1.06:1 (against the hover background it
    is worse still: 1.15:1 / 1.08:1). ``COLOR_TEXT_1`` is the one palette value
    guaranteed by construction to read on the button, because qdarkstyle
    already paints the button's label with it: 5.98:1 dark and 9.07:1 light
    against the resting button, 4.40:1 / 7.97:1 against the hover background.
    It also inverts with the theme for free -- no second, parallel colour table
    (the mistake ``mode_indicator.py`` records).

    **The box does not move.** The base rule is ``padding: 2px; border: none``
    (total 2px); the focus rule is ``padding: 0px; border: 2px`` (total 2px
    again), so focusing a button cannot jitter the layout -- and 2px is the
    thickness WCAG 2.2's focus-appearance guidance asks for, which a 1px
    qdarkstyle-style input border would not give.

    No ``:focus:hover`` companion is needed (the bug entry proposed one):
    qdarkstyle's ``:hover`` rule sets only ``background-color``/``color`` and
    this one sets only ``border``/``padding``, so the two merge per-property and
    a focused-and-hovered button keeps BOTH cues. That merge is not covered by a
    test -- the offscreen platform will not enter the hover state (neither a
    synthesised ``QEnterEvent`` nor ``WA_UnderMouse`` makes the QSS ``:hover``
    rule take), so asserting it would mean asserting nothing.

    ``:checked`` sets ``padding`` at equal specificity, so this rule is appended
    *after* qdarkstyle's text to win by order and keep the box math right for
    checked buttons too."""
    return (
        f"\n\n{FOCUS_RULE_SELECTOR} {{\n"
        f"  border: 2px solid {pal.COLOR_TEXT_1};\n"
        f"  padding: 0px;\n"
        f"}}\n"
    ) + _focus_visible_tab_qss(pal)


def apply_syntax_role(fmt, role) -> None:
    """Paint one `theme_model.SyntaxRole` onto a `QTextCharFormat`.

    The single place a syntax role becomes Qt state, shared by BOTH highlighters
    (`xml_editor.XmlSyntaxHighlighter` and `code_editor._CodeHighlighter`) --
    generalising the `set_colors` seam the XML one already had rather than
    letting the code one grow a second bespoke mechanism.

    Every flag is set EXPLICITLY, including the `False` cases: these formats are
    reused across theme flips, so leaving `bold` alone when a theme does not ask
    for it would make "was italic once" sticky, which is the last-write-wins rule
    a theme flip needs (`PaletteChange` fires four times per flip).
    """
    fmt.setForeground(QColor(role.color))
    fmt.setFontWeight(QFont.Weight.Bold if role.bold else QFont.Weight.Normal)
    fmt.setFontItalic(bool(role.italic))
    fmt.setFontUnderline(bool(role.underline))


class _ChromePalette:
    """A theme's 16 `COLOR_*` chrome tokens, exposed as attributes.

    Only so `_focus_visible_qss` and `_focus_visible_tab_qss` keep reading
    `pal.COLOR_TEXT_1` unchanged: they were written against a qdarkstyle
    `Palette` class, and the tail's whole point is that it inverts with the
    theme for free rather than carrying a second colour table. Not a qdarkstyle
    `Palette` subclass, because qdarkstyle would ignore one anyway (see the
    module docstring).
    """

    def __init__(self, theme: Theme) -> None:
        for key in theme_model.CHROME_KEYS:
            setattr(self, key, theme.chrome[key])


#: Matches one `#rrggbb` in the qdarkstyle QSS. The negative lookahead keeps a
#: longer literal (an 8-digit `#rrggbbaa`, or a hex run inside a resource path)
#: from being truncated into a match.
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}(?![0-9a-fA-F])")


def _recolour_qss(qss: str, base_palette, theme: Theme) -> str:
    """Rewrite `qss`'s chrome colours from `base_palette`'s to `theme`'s.

    **This, not `load_stylesheet(palette=...)`, is how a theme recolours the
    chrome** -- see the module docstring for why qdarkstyle's own argument
    cannot: it discards the caller's palette and reads a precompiled sheet.

    ONE pass, with every replacement resolved from the ORIGINAL text, so a
    theme that maps A->B while some other token maps B->C cannot chain the two
    (a naive sequence of `str.replace` calls does exactly that, and the bug it
    produces is a single wrong-coloured widget nobody traces back). Literals the
    stock palette does not define are left alone -- qdarkstyle's sheet carries a
    few (e.g. inside `border-image` fallbacks) and inventing a mapping for them
    would change pixels this refactor is not allowed to change.

    For the two BUNDLED themes the mapping is the identity, so the output is
    byte-identical to today's stylesheet -- which is what a test asserts, and
    what makes "no colour visibly changes" checkable rather than argued.
    """
    mapping = {
        getattr(base_palette, key).lower(): theme.chrome[key]
        for key in theme_model.CHROME_KEYS
    }
    if all(source == target.lower() for source, target in mapping.items()):
        return qss
    return _HEX_RE.sub(lambda m: mapping.get(m.group(0).lower(), m.group(0)), qss)


def _qdarkstyle_stylesheet(light: bool) -> str:
    """The QDarkStyleSheet QSS (github.com/ColinDuquesnoy/QDarkStyleSheet, the
    `qdarkstyle` package) for the given theme, recoloured from the theme file --
    adopted for BUG-010: Fusion + palette alone left checkable menu indicators
    outlined near-black on the dark menu background (Fusion derives the
    indicator frame from darkened Window/Button roles). Rather than hand-tuning
    per-widget QSS, the maintained stylesheet styles menus (QMenu::indicator
    included) and every other widget consistently -- for BOTH themes:
    qdarkstyle ships a `qdarkstyle.light.palette.LightPalette` alongside its
    `DarkPalette`, so the light theme gets the same professional chrome the dark
    theme always had, at no new dependency cost.

    `Theme.qdarkstyle_base` picks WHICH of those two compiled sheets is loaded
    (all its non-colour styling is what the theme inherits); `_recolour_qss`
    then substitutes the theme's colours into it.
    """
    if light not in _qss_cache:
        import qdarkstyle
        from qdarkstyle.dark.palette import DarkPalette
        from qdarkstyle.light.palette import LightPalette

        theme = theme_for(light)
        base = LightPalette if theme.qdarkstyle_base == "light" else DarkPalette
        # The app-authored focus tail is folded into the CACHED string, so the
        # "one QSS string per theme" invariant and the cache-identity tests
        # hold unchanged, and apply_theme still does a single setStyleSheet.
        # The tail is appended AFTER recolouring: it is app-authored and already
        # spelled in the theme's own colours, so passing it through the
        # substitution could only map one of them onto a chrome token by
        # coincidence.
        _qss_cache[light] = _recolour_qss(
            qdarkstyle.load_stylesheet(qt_api="pyside6", palette=base), base, theme
        ) + _focus_visible_qss(_ChromePalette(theme))
    return _qss_cache[light]


def apply_theme(app, light: bool) -> None:
    """Apply the light or dark theme: Fusion + the theme's ``QPalette`` + the
    matching recoloured QDarkStyleSheet QSS (BUG-010, extended to cover light
    too).

    Symmetric by construction (BUG-004 fix): there is no third "restore
    whatever the native/OS style renders" state; both states are real,
    tested, and platform-independent, and now both carry a stylesheet.
    ``light_palette()``/``dark_palette()`` are still applied under the QSS
    because palette-reading custom widgets (XmlEditor's
    ``apply_theme_colors`` keys off its palette's Base lightness) and any
    non-stylesheet-covered rendering must agree with the stylesheet's look."""
    app.setStyle("Fusion")
    app.setPalette(light_palette() if light else dark_palette())
    app.setStyleSheet(_qdarkstyle_stylesheet(light))
