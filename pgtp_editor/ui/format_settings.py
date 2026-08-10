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

# pgtp_editor/ui/format_settings.py
"""Persistence for the autoformatter's configuration (§18.4 part D).

The engines are Qt-free and read a `FormatConfig` / `XmlFormatConfig` handed to
them; this module is the only place those objects meet `QSettings`. Nothing here
formats anything.

WHY QSettings, AND WHY DEC-001 DOES NOT GOVERN
----------------------------------------------
The config lives under the `autoformatter` group of the app's existing
`QSettings("MDS", "PGTP Editor")`, beside `lightTheme` / `toolbarIds` /
`toolbarIconIds` / `shortcutOverrides`.

DEC-001 chose a user-editable JSON file in the app's folder for the **snippet
store** and explicitly rejected QSettings -- but its ground was the *artifact's
shape and purpose*: snippets are multi-line SQL bodies a human hand-authors, and
they must cross between people by an explicit export/import gesture. An ini can
hold neither. Formatter config is neither thing: it is scalars and small flags,
its editor **is** the dialog, and it is a personal preference nobody shares. It
is the same *kind* of state as `shortcutOverrides` -- a small keyed map of
scalars, per-user, dialog-edited -- and that is exactly where `shortcutOverrides`
lives. The app's QSettings is `IniFormat`/`UserScope` on purpose, so it already
IS a hand-editable text file. If sharing a *house* formatting style between
developers ever becomes a requirement, that is an export/import gesture, DEC-001
applies in full, and the location moves to a file.

WHY A MODULE-LEVEL ACCESSOR RATHER THAN CONSTRUCTOR INJECTION
-------------------------------------------------------------
Five surfaces host the Format Selection gesture (two SQL panels and **three**
`XmlEditor` instances, §18.4 C) and they are constructed in four different
places, several of them per-tab and long after startup. Threading a config
through all of them would put a formatting preference in constructors that have
nothing to do with formatting -- and every one of those constructors would then
need re-wiring whenever the dialog saves. So the hosts ask **at gesture time**:
`current_sql_config()` / `current_xml_config()` re-read the store on each
`Ctrl+Alt+F`, which is also why a save takes effect with no notification
plumbing at all. `ui/editor_gutter.py`'s module-level bookmark observer registry
is the precedent for module-level state in `ui/`.

`use_settings()` is the injection seam, mirroring `MainWindow(settings=...)`: a
test that wrote to the developer's real config would be a defect. (Tests under
`tests/ui/` are additionally covered by `conftest.py`'s `_isolated_qsettings`,
which redirects the default IniFormat/UserScope path per test -- the default
store is constructed fresh on every call here, never cached at import, so that
redirection is always honoured.)
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

from ..sql import DEFAULT_FORMAT_CONFIG, FormatConfig
from ..sql.format_config import (
    CLAUSE_STARTERS,
    MAX_INDENT_WIDTH,
    MIN_INDENT_WIDTH,
    ClauseRule,
    KeywordCase,
    indent_unit_for,
)
from ..xmlfmt import DEFAULT_XML_FORMAT_CONFIG, XmlFormatConfig

#: The QSettings group every autoformatter key hangs under -- the convention
#: every other key in this app follows (a constant in its owning module).
AUTOFORMAT_SETTINGS_KEY = "autoformatter"

_KEYWORD_CASE_KEY = f"{AUTOFORMAT_SETTINGS_KEY}/keywordCase"
_INDENT_WIDTH_KEY = f"{AUTOFORMAT_SETTINGS_KEY}/indentWidth"
_INDENT_TAB_KEY = f"{AUTOFORMAT_SETTINGS_KEY}/indentTab"
_JOIN_PHRASE_BREAK_KEY = f"{AUTOFORMAT_SETTINGS_KEY}/joinPhraseBreak"
_CLAUSE_GROUP = f"{AUTOFORMAT_SETTINGS_KEY}/clause"
_XML_INDENT_WIDTH_KEY = f"{AUTOFORMAT_SETTINGS_KEY}/xmlIndentWidth"

#: Set by `use_settings` -- otherwise the app's default store is built per call.
_override: QSettings | None = None


def default_settings() -> QSettings:
    """The app's own store, constructed exactly as `MainWindow` constructs it.

    IniFormat/UserScope, so the location is a plain file -- portable,
    inspectable, and redirectable by tests via `QSettings.setPath`.
    """
    return QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, "MDS", "PGTP Editor"
    )


def use_settings(settings: QSettings | None) -> None:
    """Point this module at `settings` (or back at the app's default with None).

    The injection seam. Call it with a temp-file `QSettings` in any test that
    saves, and with `None` to release it.
    """
    global _override
    _override = settings


def settings() -> QSettings:
    """The store reads and writes go to."""
    return _override if _override is not None else default_settings()


# --------------------------------------------------------------------------
# Load -- never raises, silently clamps (§18.4 B, consequence 2: nothing can be
# lost, so the snippet store's "never overwrite what you could not read" posture
# would be ceremony here).
# --------------------------------------------------------------------------


def _int(store: QSettings, key: str, default: int) -> int:
    try:
        value = store.value(key, default)
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _bool(store: QSettings, key: str, default: bool) -> bool:
    try:
        return bool(store.value(key, default, type=bool))
    except (TypeError, ValueError):
        return default


def _clamped_width(value: int, default: int) -> int:
    if value < MIN_INDENT_WIDTH or value > MAX_INDENT_WIDTH:
        return default
    return value


def load_sql_config(store: QSettings | None = None) -> FormatConfig:
    """The saved SQL formatter config, or the shipped default for anything
    missing, unknown or out of range. Never raises."""
    store = store if store is not None else settings()
    default_width = DEFAULT_FORMAT_CONFIG.indent_width
    width = _clamped_width(_int(store, _INDENT_WIDTH_KEY, default_width), default_width)
    config = FormatConfig(
        indent_unit=indent_unit_for(width, _bool(store, _INDENT_TAB_KEY, False)),
        keyword_case=KeywordCase.parse(store.value(_KEYWORD_CASE_KEY)),
        clause_rules=_load_clause_rules(store),
        join_phrase_break=_bool(
            store, _JOIN_PHRASE_BREAK_KEY, DEFAULT_FORMAT_CONFIG.join_phrase_break
        ),
    )
    # One leniency gate, and it lives in the Qt-free core so the engine's bounds
    # are stated once (`FormatConfig.sanitized`).
    return config.sanitized()


def _load_clause_rules(store: QSettings) -> dict[str, ClauseRule]:
    """Read the SPARSE per-clause grid: `autoformatter/clause/<keyword>/…`.

    Stored as ini groups rather than as one encoded value so the file stays
    hand-readable, and sparsely so that **adding a clause starter to the engine
    later needs no migration of anybody's saved settings** (§18.4 B).
    """
    rules: dict[str, ClauseRule] = {}
    store.beginGroup(_CLAUSE_GROUP)
    try:
        for keyword in store.childGroups():
            if keyword not in CLAUSE_STARTERS:
                continue  # a keyword this engine no longer has: dropped silently
            rules[keyword] = ClauseRule(
                break_before=_bool(store, f"{keyword}/break", True),
                indent_levels=_int(store, f"{keyword}/indent", 0),
            )
    finally:
        store.endGroup()
    return rules


def load_xml_config(store: QSettings | None = None) -> XmlFormatConfig:
    """The saved XML indentation config (indent width only). Never raises."""
    store = store if store is not None else settings()
    default_width = len(DEFAULT_XML_FORMAT_CONFIG.indent_unit)
    width = _clamped_width(_int(store, _XML_INDENT_WIDTH_KEY, default_width), default_width)
    return XmlFormatConfig(indent_unit=" " * width)


# --------------------------------------------------------------------------
# Save
# --------------------------------------------------------------------------


def save_configs(
    sql_config: FormatConfig,
    xml_config: XmlFormatConfig,
    store: QSettings | None = None,
) -> None:
    """Persist both configs, replacing whatever was stored before.

    The group is removed first so the stored grid stays SPARSE: a clause rule the
    user has reset back to the default disappears rather than lingering as an
    explicit entry that would pin the keyword forever.
    """
    store = store if store is not None else settings()
    sql_config = sql_config.sanitized()
    store.remove(AUTOFORMAT_SETTINGS_KEY)
    store.setValue(_KEYWORD_CASE_KEY, sql_config.keyword_case.value)
    store.setValue(_INDENT_TAB_KEY, sql_config.uses_tab)
    store.setValue(_INDENT_WIDTH_KEY, sql_config.indent_width)
    store.setValue(_JOIN_PHRASE_BREAK_KEY, sql_config.join_phrase_break)
    for keyword, rule in sorted(sql_config.clause_rules.items()):
        store.setValue(f"{_CLAUSE_GROUP}/{keyword}/break", rule.break_before)
        store.setValue(f"{_CLAUSE_GROUP}/{keyword}/indent", rule.indent_levels)
    store.setValue(_XML_INDENT_WIDTH_KEY, len(xml_config.indent_unit))
    store.sync()


# --------------------------------------------------------------------------
# What the hosts call, at gesture time
# --------------------------------------------------------------------------


def current_sql_config() -> FormatConfig:
    """The config a `Ctrl+Alt+F` on a SQL surface should use, read now."""
    return load_sql_config()


def current_xml_config() -> XmlFormatConfig:
    """The config a `Ctrl+Alt+F` on an XML surface should use, read now."""
    return load_xml_config()
