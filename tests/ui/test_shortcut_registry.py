"""FQ-012 -- the pure shortcut rules (Qt-free).

Everything here runs without a QApplication, which is the point: the conflict
rule, the reserved tables and the persistence shape are decidable from plain
data, so they are unit-tested rather than exercised through a widget.
"""
import pytest

from pgtp_editor.ui.shortcut_registry import (
    RESERVED_BINDINGS,
    RESERVED_COMMAND_IDS,
    RESERVED_SEQUENCES,
    SHORTCUT_OVERRIDES_SETTINGS_KEY,
    CommandBinding,
    assign_shortcut,
    commands_holding,
    default_bindings,
    detect_conflicts,
    is_rebindable,
    normalize_sequence,
    overrides_for,
    parse_shortcut_overrides,
    refusal_for,
    reserved_reason,
    resolve_bindings,
    resolve_shortcut_overrides,
    serialize_shortcut_overrides,
)

COMMANDS = [
    CommandBinding("file.open", "File › Open", "Ctrl+O"),
    CommandBinding("file.close", "File › Close", "Ctrl+W"),
    CommandBinding("navigation.next-bookmark", "Navigation › Next Bookmark", "F2"),
    CommandBinding("help.manual", "Help › Manual", "F1"),
    CommandBinding("tools.next-difference", "Tools › Next Difference", ""),
]


# -- normalization -----------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ctrl+s", "Ctrl+S"),
        ("Shift+Ctrl+S", "Ctrl+Shift+S"),
        ("CTRL+ALT+f", "Ctrl+Alt+F"),
        ("shift+f2", "Shift+F2"),
        ("f10", "F10"),
        # Qt spells these two ways and the spec table a third; they must
        # compare equal or every reserved-key check below is defeated.
        ("esc", "Escape"),
        ("Escape", "Escape"),
        ("ctrl+enter", "Ctrl+Return"),
        ("Ctrl+Return", "Ctrl+Return"),
        ("", ""),
        (None, ""),
        ("  ", ""),
    ],
)
def test_normalize_sequence(raw, expected):
    assert normalize_sequence(raw) == expected


def test_normalize_sequence_is_idempotent():
    for raw in ("ctrl+shift+alt+meta+x", "shift+f2", "esc"):
        once = normalize_sequence(raw)
        assert normalize_sequence(once) == once


def test_normalize_sequence_keeps_a_trailing_modifier_as_the_key():
    # "Ctrl+Shift" is a real (if useless) sequence; the last token is the key.
    assert normalize_sequence("ctrl+shift") == "Ctrl+Shift"


# -- the conflict rule -------------------------------------------------------


def test_detect_conflicts_finds_the_qt_fires_neither_hazard():
    # Qt resolves two enabled shortcuts on one chord by firing NEITHER (see
    # find_replace_bar.install_focus_shortcuts). So a duplicate is not "the
    # first one wins" -- it deletes both commands from the keyboard, which is
    # why this must be detectable at all.
    conflicts = detect_conflicts(
        {"file.open": "Ctrl+O", "file.close": "ctrl+o", "a.b": "F2"}
    )
    assert conflicts == {"Ctrl+O": ["file.close", "file.open"]}


def test_detect_conflicts_ignores_unbound_commands():
    assert detect_conflicts({"a.b": "", "c.d": "", "e.f": "F2"}) == {}


def test_assign_shortcut_steals_and_never_leaves_a_duplicate():
    bindings = {"file.open": "Ctrl+O", "file.close": "Ctrl+W"}
    result, stolen = assign_shortcut(bindings, "file.close", "ctrl+o")
    assert stolen == ["file.open"]
    # The loser is left UNBOUND, not deleted -- the row stays, it has no key.
    assert result == {"file.open": "", "file.close": "Ctrl+O"}
    assert detect_conflicts(result) == {}
    # The input map is untouched.
    assert bindings == {"file.open": "Ctrl+O", "file.close": "Ctrl+W"}


def test_assign_shortcut_to_an_unheld_key_steals_nothing():
    result, stolen = assign_shortcut({"file.open": "Ctrl+O"}, "file.open", "Ctrl+U")
    assert stolen == []
    assert result == {"file.open": "Ctrl+U"}


def test_assign_shortcut_can_unbind():
    result, stolen = assign_shortcut({"file.open": "Ctrl+O"}, "file.open", "")
    assert result == {"file.open": ""}
    assert stolen == []


def test_commands_holding_excludes_the_command_being_assigned():
    bindings = {"file.open": "Ctrl+O", "file.close": "Ctrl+W"}
    assert commands_holding(bindings, "Ctrl+O") == ["file.open"]
    assert commands_holding(bindings, "Ctrl+O", exclude="file.open") == []
    assert commands_holding(bindings, "") == []


# -- reserved bindings -------------------------------------------------------


def test_reserved_sequences_encode_what_section_27_pins():
    # The four non-menu / context-gated keys FQ-012 decision 1 names...
    for sequence in ("Ctrl+Z", "Ctrl+Y", "Ctrl+F", "Ctrl+R"):
        assert sequence in RESERVED_SEQUENCES
    # ...the two §27 states as deliberately unbound app-wide (FQ-020)...
    for sequence in ("Ctrl+S", "Ctrl+Shift+S"):
        assert sequence in RESERVED_SEQUENCES
    # ...the window-level commands with no menu entry, which the menu walk
    # cannot enumerate and this dialog therefore cannot move...
    for sequence in ("F3", "Ctrl+L", "Ctrl+Alt+F", "Ctrl+Return", "Ctrl+Space"):
        assert sequence in RESERVED_SEQUENCES
    # ...and F1.
    assert "F1" in RESERVED_SEQUENCES
    # Every reason is a sentence a user can be shown.
    assert all(reason.strip() for reason in RESERVED_SEQUENCES.values())


def test_reserved_bindings_mirror_the_reserved_table():
    assert [entry.sequence for entry in RESERVED_BINDINGS] == list(
        RESERVED_SEQUENCES
    )


def test_reserved_lookup_is_spelling_insensitive():
    assert reserved_reason("ctrl+f") is not None
    assert reserved_reason("esc") is not None
    assert reserved_reason("Ctrl+U") is None
    assert reserved_reason("") is None


def test_a_reserved_key_is_refused_as_a_target_not_stolen():
    # Ctrl+F is a per-tab focus shortcut at six sites. The dialog owns menu
    # QActions only, so it cannot clear those; binding a menu command to
    # Ctrl+F would make Qt fire neither. Hence refusal, not a steal.
    refusal = refusal_for("file.open", "Ctrl+F")
    assert refusal and "Ctrl+F" in refusal
    with pytest.raises(ValueError):
        assign_shortcut({"file.open": "Ctrl+O"}, "file.open", "ctrl+f")


def test_a_reserved_command_may_not_be_rebound():
    assert "help.manual" in RESERVED_COMMAND_IDS
    assert not is_rebindable("help.manual")
    assert is_rebindable("file.open")
    assert refusal_for("help.manual", "Ctrl+U") is not None
    with pytest.raises(ValueError):
        assign_shortcut({"help.manual": "F1"}, "help.manual", "Ctrl+U")


def test_a_free_key_is_not_refused():
    assert refusal_for("file.open", "Ctrl+U") is None
    assert refusal_for("file.open", "") is None


# -- resolve / round-trip ----------------------------------------------------


def test_default_bindings_normalize():
    assert default_bindings([CommandBinding("a.b", "A › B", "ctrl+o")]) == {
        "a.b": "Ctrl+O"
    }


def test_resolve_bindings_applies_overrides_over_defaults():
    bindings = resolve_bindings(COMMANDS, {"file.close": "Ctrl+U"})
    assert bindings["file.close"] == "Ctrl+U"
    assert bindings["file.open"] == "Ctrl+O"
    assert bindings["tools.next-difference"] == ""


def test_resolve_bindings_never_installs_an_ambiguous_pair():
    # A hand-edited settings file that gives Close the key Open defaults to
    # must not produce two commands on Ctrl+O -- the override wins and the
    # defaulting command is left unbound, the same steal the dialog made.
    bindings = resolve_bindings(COMMANDS, {"file.close": "Ctrl+O"})
    assert bindings["file.close"] == "Ctrl+O"
    assert bindings["file.open"] == ""
    assert detect_conflicts(bindings) == {}


def test_resolve_bindings_ignores_unknown_and_refused_overrides():
    bindings = resolve_bindings(
        COMMANDS,
        {
            "no.such.command": "Ctrl+U",
            "file.close": "Ctrl+F",  # reserved sequence
            "help.manual": "Ctrl+U",  # reserved command
        },
    )
    assert bindings["file.close"] == "Ctrl+W"
    assert bindings["help.manual"] == "F1"
    assert "no.such.command" not in bindings


def test_rebinding_round_trip_through_the_pure_mapping():
    # The whole loop the wiring pass will run: defaults -> user rebinds ->
    # minimal override map -> QSettings strings -> back -> the same bindings.
    bindings = resolve_bindings(COMMANDS, None)
    bindings, stolen = assign_shortcut(bindings, "file.close", "Ctrl+O")
    assert stolen == ["file.open"]

    overrides = overrides_for(COMMANDS, bindings)
    # Only what differs from the default is stored -- and the cleared loser is
    # stored as an EMPTY value, which is a different state from "absent".
    assert overrides == {"file.close": "Ctrl+O", "file.open": ""}
    assert "navigation.next-bookmark" not in overrides

    stored = serialize_shortcut_overrides(overrides)
    assert stored == ["file.close=Ctrl+O", "file.open="]

    loaded = resolve_shortcut_overrides(
        parse_shortcut_overrides(stored), [c.command_id for c in COMMANDS]
    )
    assert resolve_bindings(COMMANDS, loaded) == bindings


def test_overrides_for_is_empty_when_everything_is_on_its_default():
    assert overrides_for(COMMANDS, resolve_bindings(COMMANDS, None)) == {}


# -- persistence -------------------------------------------------------------


def test_settings_key_is_a_sibling_of_the_toolbar_keys():
    assert SHORTCUT_OVERRIDES_SETTINGS_KEY == "shortcutOverrides"


def test_parse_shortcut_overrides_tolerates_what_qsettings_returns():
    assert parse_shortcut_overrides(None) == {}
    assert parse_shortcut_overrides("file.open=ctrl+u") == {"file.open": "Ctrl+U"}
    assert parse_shortcut_overrides(["garbage", "file.open=Ctrl+U"]) == {
        "file.open": "Ctrl+U"
    }
    assert parse_shortcut_overrides({"file.open": "ctrl+u"}) == {
        "file.open": "Ctrl+U"
    }
    # The empty value survives -- "the user cleared this" is not "no override".
    assert parse_shortcut_overrides(["file.open="]) == {"file.open": ""}


def test_resolve_shortcut_overrides_prunes_and_maps_ids():
    known = ["file.open", "navigation.next-bookmark", "parsing.validate-project"]
    resolved = resolve_shortcut_overrides(
        {
            "open": "Ctrl+U",  # legacy id (pre-BUG-027)
            "bookmarks.next-bookmark": "F4",  # renamed by FQ-021
            "validate": "F9",  # legacy -> renamed, both tables
            "gone.command": "F8",  # no longer exists
            "file.open ": "F7",  # not a thing after the alias tables
        },
        known,
    )
    assert resolved["file.open"] == "Ctrl+U"
    assert resolved["navigation.next-bookmark"] == "F4"
    assert resolved["parsing.validate-project"] == "F9"
    assert "gone.command" not in resolved


def test_resolve_shortcut_overrides_drops_a_hand_written_reserved_key():
    # A settings file is editable by hand; a Ctrl+F written into it would
    # install exactly the ambiguity this module exists to prevent.
    assert resolve_shortcut_overrides({"file.open": "Ctrl+F"}, ["file.open"]) == {}


# -- BUG-050: the second redo chord ------------------------------------------


def test_ctrl_shift_z_is_reserved_beside_the_history_pair():
    """`XmlEditor.keyPressEvent` answers Ctrl+Shift+Z as a second redo and
    CONSUMES it, so a menu command retargeted here would fire only while no XML
    editor has focus — a focus-dependent silence, which is worse than a clean
    loss and exactly what this table exists to prevent."""
    assert "Ctrl+Shift+Z" in RESERVED_SEQUENCES
    assert RESERVED_SEQUENCES["Ctrl+Shift+Z"].strip()
    # Grouped with the pair it belongs to, which the dict's order is meant to
    # show: the reader must find the three history chords together.
    keys = list(RESERVED_SEQUENCES)
    assert keys.index("Ctrl+Shift+Z") == keys.index("Ctrl+Y") + 1


def test_ctrl_shift_z_is_refused_as_a_target_not_stolen():
    refusal = refusal_for("file.open", "Ctrl+Shift+Z")
    assert refusal and "Ctrl+Shift+Z" in refusal
    with pytest.raises(ValueError):
        assign_shortcut({"file.open": "Ctrl+O"}, "file.open", "ctrl+shift+z")


def test_the_format_selection_reason_names_its_shortcut_hosts():
    """The reason string is USER-FACING text in the dialog's greyed row, and it
    used to say only "a context-menu command" — Ctrl+Alt+F is additionally a
    QShortcut in the SQL Console and the DDL object tabs."""
    reason = RESERVED_SEQUENCES["Ctrl+Alt+F"]
    assert "context-menu" in reason
    assert "SQL Console" in reason
