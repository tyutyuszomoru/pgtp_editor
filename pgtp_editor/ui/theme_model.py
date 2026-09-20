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

# pgtp_editor/ui/theme_model.py
"""The `Theme` value object — **the one place a colour comes from**
(FQ-260812021715).

**Why this module exists at all.** This codebase grew a second colour table
beside the real one repeatedly; `mode_indicator.py`'s docstring exists purely to
record one of those mistakes, and `FQ-260810165518` had to deliberately reuse
`mode_colors`' existing red rather than derive a third. A rule that says "don't
add another table" is a rule nobody can enforce. A single loader that every
consumer reads through, plus a package-wide test that no module outside this one
declares a `#rrggbb`, makes the second table *impossible* rather than merely
discouraged.

**A theme is COLOURS ONLY, and it is a FILE.** Each theme is one JSON document
under `pgtp_editor/resources/themes/` (bundled) or the user themes directory
(`user_themes_dir()`); dropping a new file in either makes a new selectable
theme, discovered at runtime by `available_themes()`. Nothing about shape,
spacing, border radius or font lives here — those stay at qdarkstyle's defaults
(see `theme.py`).

**Qt-free on purpose.** Nothing in this module imports PySide6 at module scope,
so the colour model can be loaded, validated, diffed and unit-tested without a
`QApplication` — which is also what lets a future Themes pane (FQ-260812021716)
edit a theme as plain data. The single Qt touch, `user_themes_dir()`'s
`QStandardPaths` lookup, is a function-local import.

**The six layers a theme carries**, matching what the app actually paints:

* `chrome`   — qdarkstyle's 16 `COLOR_*` tokens (menus, buttons, tabs, docks,
  scrollbars). See `theme.py::_recolour_qss` for how they are applied, and why
  qdarkstyle's own `palette=` argument could not do it.
* `palette` / `palette_disabled` — the 15 active Qt `QPalette` roles plus the 3
  Disabled-group roles.
* `accents` — app-authored chrome colours that answer to no palette role: the
  vim Command-mode caret pair, the results-strip warning colour, the
  connectivity dots.
* `modes` — the major-mode indicator chips (`mode_indicator.py`).
* `decorations` — per-editor line/selection backgrounds and the gutter pair.
* `syntax` — the 8 syntax roles (3 XML + 5 code), each a `SyntaxRole` carrying
  `color` plus `bold`/`italic`/`underline`. Syntax highlighting is PART OF the
  theme by owner ruling, which is what removes the light-syntax-on-dark-chrome
  mismatch by construction.

**Monospaced-per-role is deliberately absent**: every editor is already
monospaced, and a global editor-font setting is a separate concern, not a theme.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

#: The qdarkstyle colour tokens a theme must carry. Exactly the `COLOR_*`
#: attributes of `qdarkstyle.palette.Palette` that its two shipped palettes
#: define — every NON-colour token (`SIZE_*`, `BORDER_*`, `OPACITY_*`,
#: `PATH_RESOURCES`) stays at the qdarkstyle default and is NOT themeable.
CHROME_KEYS: tuple[str, ...] = (
    "COLOR_BACKGROUND_1",
    "COLOR_BACKGROUND_2",
    "COLOR_BACKGROUND_3",
    "COLOR_BACKGROUND_4",
    "COLOR_BACKGROUND_5",
    "COLOR_BACKGROUND_6",
    "COLOR_TEXT_1",
    "COLOR_TEXT_2",
    "COLOR_TEXT_3",
    "COLOR_TEXT_4",
    "COLOR_ACCENT_1",
    "COLOR_ACCENT_2",
    "COLOR_ACCENT_3",
    "COLOR_ACCENT_4",
    "COLOR_ACCENT_5",
    "COLOR_DISABLED",
)

#: The `QPalette.ColorRole` names a theme sets in the Active/Normal group.
PALETTE_ROLES: tuple[str, ...] = (
    "Window",
    "WindowText",
    "Base",
    "AlternateBase",
    "ToolTipBase",
    "ToolTipText",
    "Text",
    "Button",
    "ButtonText",
    "BrightText",
    "Highlight",
    "HighlightedText",
    "Link",
    "LinkVisited",
    "PlaceholderText",
)

#: The roles a theme additionally sets in the Disabled colour group, so
#: greyed-out controls stay legible under the Fusion style.
DISABLED_ROLES: tuple[str, ...] = ("Text", "WindowText", "ButtonText")

#: The 8 syntax roles, shared across languages for v1 (SQL/PHP/JS all read the
#: `code_*` five; per-language colouring is deliberately out of scope).
SYNTAX_ROLES: tuple[str, ...] = (
    "xml_tag",
    "xml_attr_name",
    "xml_string",
    "code_keyword",
    "code_string",
    "code_comment",
    "code_number",
    "code_variable",
)

#: Editor decoration colours, including the gutter pair shared by every editor
#: carrying the `editor_gutter` mixin.
DECORATION_KEYS: tuple[str, ...] = (
    "current_line",
    "error_line",
    "navigation_highlight",
    "matching_tag",
    "code_region",
    "gutter_background",
    "gutter_foreground",
)

#: App-authored accents that answer to no `QPalette` role.
ACCENT_KEYS: tuple[str, ...] = (
    "command_caret_background",
    "command_caret_foreground",
    "status_warning",
    # The status-bar DEBUG chip, folded in by BUG-260812063745. It was the
    # app's last hardcoded chip (`color: white; background: #b33`), which §7
    # already singled out as forbidden to copy because it does not re-theme;
    # it is a background/foreground PAIR because a chip is not text on chrome.
    "debug_chip_background",
    "debug_chip_foreground",
    "connectivity_unknown",
    "connectivity_not_set_up",
    "connectivity_offline",
    "connectivity_reachable",
)

#: The major-mode chip keys. `"none"` is the JSON spelling of
#: `mode_indicator`'s `None` key ("no launcher column picked yet") — JSON has no
#: null-valued object key, and the indicator maps it back.
MODE_KEYS: tuple[str, ...] = ("none", "standalone", "project", "maintenance")

#: The two bundled themes' file stems. These are the names the legacy persisted
#: `light=true/false` boolean migrates onto.
DARK_THEME = "dark"
LIGHT_THEME = "light"

#: The `QSettings` key holding the selected theme's NAME (its file stem), app-wide
#: and durable. Maintenance-mode settings are app-wide and persistent by owner
#: ruling (FQ-260812021715), which is why the theme is remembered across restarts
#: and new sessions rather than per-session.
SETTINGS_KEY = "themeName"

#: The key this replaced: a `light=true/false` boolean, back when a theme was a
#: binary. Read exactly ONCE per install, by `migrated_theme_name`, and then
#: removed -- a second stored answer to "which theme" is the drift this whole
#: module exists to prevent.
LEGACY_LIGHT_KEY = "lightTheme"


class ThemeError(ValueError):
    """A theme file is missing, malformed, or missing a required colour.

    Loud on purpose: a theme that silently falls back to a default is how a
    half-applied palette ships. Every key listed in the `*_KEYS` tuples above is
    required, so adding a colour to the model makes every theme file that lacks
    it fail immediately rather than paint black.
    """


@dataclass(frozen=True)
class SyntaxRole:
    """One syntax token's appearance: a colour plus the three weight flags.

    The flags are carried even though no bundled theme sets one — they are what
    the Themes pane (FQ-260812021716) edits, and `code_editor`/`xml_editor`
    apply them, so a theme file that turns comments italic works today.
    """

    color: str
    bold: bool = False
    italic: bool = False
    underline: bool = False

    @classmethod
    def from_json(cls, value: Any, *, where: str) -> "SyntaxRole":
        if isinstance(value, str):
            return cls(color=value)
        if not isinstance(value, Mapping) or "color" not in value:
            raise ThemeError(f"{where}: expected a colour or a {{color: ...}} map")
        return cls(
            color=str(value["color"]),
            bold=bool(value.get("bold", False)),
            italic=bool(value.get("italic", False)),
            underline=bool(value.get("underline", False)),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "color": self.color,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
        }


@dataclass(frozen=True)
class Theme:
    """Every colour the application paints, for one theme.

    Immutable, so a consumer that caches one cannot be handed a mutated copy
    behind its back — and `replace()` gives the Themes pane a cheap
    "duplicate an existing one" (the FQ's `new = copy an existing one`).
    """

    name: str
    #: Whether this theme reads as LIGHT. Every consumer still keys off a plain
    #: `light: bool` (that is the app's existing seam, from `apply_theme` down
    #: to `XmlEditor.apply_theme_colors`), so a theme declares which side of
    #: that switch it sits on rather than every call site being rewritten.
    light: bool
    #: Which of qdarkstyle's two compiled stylesheets this theme recolours.
    #: Only `"dark"` and `"light"` exist — the QSS is a precompiled Qt resource
    #: and its ID selects the resource, not the colours (see `theme.py`).
    qdarkstyle_base: str
    chrome: dict[str, str]
    palette: dict[str, str]
    palette_disabled: dict[str, str]
    accents: dict[str, str]
    modes: dict[str, tuple[str, str]]
    decorations: dict[str, str]
    syntax: dict[str, SyntaxRole]
    #: Where it was loaded from, for diagnostics and for the future pane's
    #: "save back". `None` for a theme built in memory.
    source: Path | None = field(default=None, compare=False)

    # -- accessors consumers use --------------------------------------------
    def mode_pair(self, key: str | None) -> tuple[str, str]:
        """The `(background, foreground)` chip pair for a major mode, taking
        `None` for "no column picked yet" exactly as `mode_indicator` does."""
        return self.modes["none" if key is None else key]

    def decoration(self, key: str) -> str:
        return self.decorations[key]

    def accent(self, key: str) -> str:
        return self.accents[key]

    def role(self, key: str) -> SyntaxRole:
        return self.syntax[key]

    # -- serialisation -------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        """The exact shape `from_json` reads — so the Themes pane can round-trip
        a duplicated theme through a file without a second writer."""
        return {
            "name": self.name,
            "light": self.light,
            "qdarkstyle_base": self.qdarkstyle_base,
            "chrome": dict(self.chrome),
            "palette": dict(self.palette),
            "palette_disabled": dict(self.palette_disabled),
            "accents": dict(self.accents),
            "modes": {k: list(v) for k, v in self.modes.items()},
            "decorations": dict(self.decorations),
            "syntax": {k: v.to_json() for k, v in self.syntax.items()},
        }

    @classmethod
    def from_json(cls, data: Any, *, source: Path | None = None) -> "Theme":
        where = str(source) if source is not None else "<theme>"
        if not isinstance(data, Mapping):
            raise ThemeError(f"{where}: a theme file must be a JSON object")

        base = str(data.get("qdarkstyle_base", DARK_THEME))
        if base not in (DARK_THEME, LIGHT_THEME):
            raise ThemeError(
                f"{where}: qdarkstyle_base must be 'dark' or 'light', not {base!r} "
                "-- it selects which precompiled qdarkstyle stylesheet gets "
                "recoloured, not the colours themselves"
            )

        modes_raw = _section(data, "modes", where)
        modes: dict[str, tuple[str, str]] = {}
        for key in MODE_KEYS:
            pair = modes_raw.get(key)
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ThemeError(
                    f"{where}: modes.{key} must be a [background, foreground] pair"
                )
            modes[key] = (_colour(pair[0], f"{where}: modes.{key}[0]"),
                          _colour(pair[1], f"{where}: modes.{key}[1]"))

        syntax_raw = _section(data, "syntax", where)
        syntax: dict[str, SyntaxRole] = {}
        for key in SYNTAX_ROLES:
            if key not in syntax_raw:
                raise ThemeError(f"{where}: syntax.{key} is missing")
            role = SyntaxRole.from_json(syntax_raw[key], where=f"{where}: syntax.{key}")
            _colour(role.color, f"{where}: syntax.{key}.color")
            syntax[key] = role

        return cls(
            name=str(data.get("name") or (source.stem if source else "Unnamed")),
            light=bool(data.get("light", False)),
            qdarkstyle_base=base,
            chrome=_colour_map(data, "chrome", CHROME_KEYS, where),
            palette=_colour_map(data, "palette", PALETTE_ROLES, where),
            palette_disabled=_colour_map(
                data, "palette_disabled", DISABLED_ROLES, where
            ),
            accents=_colour_map(data, "accents", ACCENT_KEYS, where),
            modes=modes,
            decorations=_colour_map(data, "decorations", DECORATION_KEYS, where),
            syntax=syntax,
            source=source,
        )


# ---------------------------------------------------------------------------
# Validation helpers -- every one of these raises rather than defaulting.
# ---------------------------------------------------------------------------

def _section(data: Mapping[str, Any], name: str, where: str) -> Mapping[str, Any]:
    section = data.get(name)
    if not isinstance(section, Mapping):
        raise ThemeError(f"{where}: '{name}' must be an object")
    return section


def _colour(value: Any, where: str) -> str:
    """Validate one colour literal. `#rrggbb` only: `QColor` also accepts SVG
    names and `#rgb`, but a theme file that mixes notations makes every
    contrast test and every diff between two themes harder to read for nothing.
    """
    text = str(value)
    if len(text) != 7 or not text.startswith("#"):
        raise ThemeError(f"{where}: {text!r} is not a #rrggbb colour")
    try:
        int(text[1:], 16)
    except ValueError:
        raise ThemeError(f"{where}: {text!r} is not a #rrggbb colour") from None
    return text


def _colour_map(
    data: Mapping[str, Any], name: str, keys: tuple[str, ...], where: str
) -> dict[str, str]:
    section = _section(data, name, where)
    result: dict[str, str] = {}
    for key in keys:
        if key not in section:
            raise ThemeError(f"{where}: {name}.{key} is missing")
        result[key] = _colour(section[key], f"{where}: {name}.{key}")
    return result


# ---------------------------------------------------------------------------
# Discovery and loading
# ---------------------------------------------------------------------------

def bundled_themes_dir() -> Path:
    """The directory the two shipped themes live in.

    Goes through `importlib.resources` like every other bundled resource in the
    package (`manual.md`, the Breeze icons, the curated schema), so the frozen
    PyInstaller build finds them the same way.
    """
    from importlib.resources import files

    return Path(str(files("pgtp_editor") / "resources" / "themes"))


def user_themes_dir() -> Path | None:
    """The user's own themes directory, or `None` when Qt cannot name one.

    Qt is imported HERE and nowhere else in this module, so the colour model
    stays loadable and testable without a `QApplication`. Uses the same
    `QStandardPaths.AppDataLocation` root as `generation/config.py`,
    `schema_learning/storage.py` and `snippet_controller.py`, so the app has one
    user-data root rather than a fourth convention.
    """
    try:
        from PySide6.QtCore import QStandardPaths
    except Exception:  # pragma: no cover - Qt is a hard dependency in practice
        return None
    root = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    if not root:
        return None
    return Path(root) / "themes"


def theme_search_path() -> list[Path]:
    """Bundled first, user second — so a user file named `dark.json` SHADOWS the
    bundled one (last writer wins in `available_themes`), which is what makes
    "edit the theme you are using" possible without touching the install."""
    dirs = [bundled_themes_dir()]
    user = user_themes_dir()
    if user is not None:
        dirs.append(user)
    return dirs


def available_themes(search_path: list[Path] | None = None) -> dict[str, Path]:
    """`{theme name (the file stem): path}` for every readable theme file.

    A directory scan, performed on every call: "adding a new theme file makes a
    new selectable theme, picked up at runtime" is the feature's requirement, so
    this must NOT be cached. `load_theme` caches the parse instead, keyed by
    path and mtime.
    """
    found: dict[str, Path] = {}
    for directory in search_path if search_path is not None else theme_search_path():
        try:
            entries = sorted(Path(directory).glob("*.json"))
        except OSError:
            continue
        for path in entries:
            found[path.stem] = path
    return found


#: Parsed themes, keyed by `(path, mtime_ns, size)`. Keyed on the file's stat so
#: a theme edited on disk (or by the future pane) is re-read without a restart,
#: while the common case still parses once.
_theme_cache: dict[tuple[str, int, int], Theme] = {}


def load_theme_file(path: Path | str) -> Theme:
    """Parse one theme file. Raises `ThemeError` for anything unreadable."""
    path = Path(path)
    try:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError as exc:
        raise ThemeError(f"{path}: cannot read theme file ({exc})") from exc
    cached = _theme_cache.get(key)
    if cached is not None:
        return cached
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThemeError(f"{path}: cannot read theme file ({exc})") from exc
    theme = Theme.from_json(data, source=path)
    _theme_cache[key] = theme
    return theme


def load_theme(name: str, search_path: list[Path] | None = None) -> Theme:
    """The theme called `name` (a file stem), or `ThemeError` if there is none."""
    themes = available_themes(search_path)
    path = themes.get(name)
    if path is None:
        raise ThemeError(
            f"no theme named {name!r} (found: {', '.join(sorted(themes)) or 'none'})"
        )
    return load_theme_file(path)


#: The theme the running application is currently painted in, set by
#: `theme.py::apply_theme` -- the ONE piece of global state in this module, and
#: the reason `theme_for` can answer a boolean question with a *named* theme.
#: `None` means "nothing applied yet" (a freshly imported process, or a unit test
#: that never touched a `QApplication`), and every reader falls back to the
#: bundled pair in that case.
_active_theme: Theme | None = None


def active_theme() -> Theme | None:
    """The theme `apply_theme` last applied, or `None` before the first apply."""
    return _active_theme


def set_active_theme(theme: Theme | None) -> None:
    """Record which theme the app is painted in. Called by `theme.py::apply_theme`
    and by nothing else -- a second caller would let the recorded theme disagree
    with the applied palette, which is the class of bug the whole consolidation
    removes."""
    global _active_theme
    _active_theme = theme


def theme_for(light: bool) -> Theme:
    """The theme behind the app's `light: bool` seam -- **the single point where
    a boolean becomes a `Theme`**, and therefore where NAME-based selection drops
    in (FQ-260812021716).

    Every colour consumer in the app still asks a boolean question, because that
    boolean is derived from the LIVE palette's lightness at paint time
    (BUG-260811021804's lesson: a resolved colour cached across a theme flip is
    the old theme's). With named themes there can be any number of themes, but
    there is only ever ONE active one, so the mapping is: **if the active theme
    reads the way the caller asked, it IS the answer**; otherwise the caller is
    mid-flip and asking about the side the app is not on, and the bundled theme
    for that side is the honest answer.

    That fallback is not defensive padding. `PaletteChange` fires four times per
    flip and the first two report the OLD lightness, so a consumer WILL ask for
    the other side during a flip; answering with the active theme's colours there
    would paint the new theme's values under the old palette for two events.
    """
    active = _active_theme
    if active is not None and bool(active.light) == bool(light):
        return active
    return load_theme(LIGHT_THEME if light else DARK_THEME)


def migrated_theme_name(stored: Any, legacy_light: Any) -> str:
    """The theme name to start on, given what QSettings holds.

    The migration path off the pre-FQ-260812021715 boolean, in one Qt-free
    function so it can be tested without a `QSettings`: a stored NAME wins; with
    no name, an existing `lightTheme=true` lands the user on the bundled light
    theme (not on a default), and anything else -- `false`, or a genuinely fresh
    install -- lands on dark, which is what `lightTheme`'s own default was.

    Deliberately does NOT validate that the name still exists: a user who deletes
    the theme file they had selected should get a working app (see
    `resolve_theme`), not a startup crash, and that fallback belongs at load time
    rather than in the migration.
    """
    name = str(stored or "").strip()
    if name:
        return name
    return LIGHT_THEME if bool(legacy_light) else DARK_THEME


def resolve_theme(name: str) -> tuple[str, Theme]:
    """`(name actually used, theme)` for a selected theme name.

    Falls back to the bundled dark theme when `name` names nothing loadable --
    the user deleted or broke the JSON file they had selected, and a startup
    crash is a far worse answer than the default theme. The name is returned
    alongside so the caller persists what it actually applied rather than a name
    that resolves to something else on the next start.
    """
    try:
        return name, load_theme(name)
    except ThemeError:
        return DARK_THEME, load_theme(DARK_THEME)


def shared_accent(key: str) -> str:
    """An accent that every bundled theme agrees on, for a THEME-BLIND consumer.

    **It has no production caller, and that is the point.** Its one caller was
    `connectivity.py`'s status-bar dots, which read all four `connectivity_*`
    accents through here while they were theme-blind — a single `_RENDERING`
    table with no palette lookup. BUG-260812103144 ended that: the dots failed
    contrast in every state precisely BECAUSE one value had to serve both themes,
    so they now read per-theme through `theme_for(light).accent(...)` and the
    bundled themes give each dot its own value. The app currently has no
    theme-blind colour consumer left.

    So this is kept as a **mechanism, not a helper**: it **raises** when the
    bundled themes disagree, which is what turns "this consumer quietly ignores
    the theme" from an invisible property into a failing test. The next consumer
    tempted to resolve a colour once — at import, in a constructor, into a cached
    attribute — reads through here and finds out immediately, instead of shipping
    the other theme's pixels. A consumer whose colour must differ per theme must
    NOT use it (see `ui/status_colours.py`); one whose colour genuinely cannot
    differ should, so that assumption is checked rather than assumed.
    """
    values = {theme_for(light).accent(key) for light in (True, False)}
    if len(values) != 1:
        raise ThemeError(
            f"accent {key!r} is not theme-blind ({sorted(values)}) -- its consumer "
            "must read it per-theme"
        )
    return values.pop()


def duplicate(theme: Theme, name: str) -> Theme:
    """A copy of `theme` under a new name and with no `source` — the
    "new = copy an existing one" primitive FQ-260812021716 rides on."""
    return replace(theme, name=name, source=None)


def theme_stem(name: str) -> str:
    """A display name reduced to a legal, unambiguous FILE STEM.

    A theme's identity is its file stem (that is what `available_themes` keys on
    and what QSettings persists), so "My Theme" and "my/theme" must not be able
    to name the same file, escape the themes directory, or produce a name the
    selection cannot round-trip. Lower-cased slug: letters and digits survive in
    any alphabet, everything else collapses to `-`, and an input with nothing
    left is refused loudly rather than becoming `.json`.
    """
    slug = "".join(
        character if character.isalnum() else "-" for character in str(name).strip()
    ).strip("-").lower()
    while "--" in slug:
        slug = slug.replace("--", "-")
    if not slug:
        raise ThemeError(f"{name!r} does not name a theme file")
    return slug


def is_bundled(theme: Theme) -> bool:
    """Whether `theme` was loaded from the install's own themes directory.

    Bundled themes are READ-ONLY: an install directory is not always writable,
    an upgrade would overwrite the edit anyway, and "new = copy an existing one"
    (FQ-260812021716) is the create path precisely so nobody has to edit one.
    """
    if theme.source is None:
        return False
    try:
        return Path(theme.source).parent == bundled_themes_dir()
    except OSError:  # pragma: no cover - a broken resource root
        return False


def save_theme(theme: Theme, stem: str) -> Path:
    """Write `theme` into the USER themes directory as `<stem>.json`, and return
    the path.

    Always the user directory, never `theme.source`: saving a duplicate of a
    bundled theme must not write into the install, and a user theme's own file
    already lives here. Because a user file SHADOWS a bundled one of the same
    name (`theme_search_path`), this is also how "edit the theme you are using"
    works without touching the install.
    """
    directory = user_themes_dir()
    if directory is None:
        raise ThemeError("no user themes directory is available on this platform")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}.json"
    path.write_text(
        json.dumps(theme.to_json(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
