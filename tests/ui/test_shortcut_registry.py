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


# -- DEC-014 / DEC-015: the chords every editing surface answers -------------


def test_the_editor_chord_table_maps_to_operations_not_to_booleans():
    """DEC-014: the shared thing must CLASSIFY. A membership test would let a
    caller re-derive the operation itself, which is how a redo becomes an undo
    while the chord still looks claimed. `Ctrl+Z` and `Ctrl+Y` are different
    operations, and after DEC-015 redo has exactly one spelling."""
    from pgtp_editor.ui.shortcut_registry import (
        CLAIMED_NOT_UNDO_REDO,
        EDITOR_UNDO_REDO_CHORDS,
        REDO,
        SUPPRESSED,
        UNDO,
    )

    assert EDITOR_UNDO_REDO_CHORDS["Ctrl+Z"] == UNDO
    assert EDITOR_UNDO_REDO_CHORDS["Ctrl+Y"] == REDO
    # Redo has ONE chord (DEC-015: "Redo is always, on all systems Ctrl+Y").
    assert [
        chord for chord, op in EDITOR_UNDO_REDO_CHORDS.items() if op == REDO
    ] == ["Ctrl+Y"]
    assert EDITOR_UNDO_REDO_CHORDS["Ctrl+Shift+Z"] == CLAIMED_NOT_UNDO_REDO
    assert EDITOR_UNDO_REDO_CHORDS["Alt+Backspace"] == SUPPRESSED
    assert EDITOR_UNDO_REDO_CHORDS["Alt+Shift+Backspace"] == SUPPRESSED


def test_every_chord_the_surfaces_intercept_is_a_reserved_sequence():
    """DEC-014's invariant ties the two artifacts that already exist: *for every
    chord `RESERVED_SEQUENCES` reserves because an editor answers it, every
    editing surface states its answer.* A chord intercepted by the editors but
    missing here would be offered in Customize Shortcuts… as a target that is
    silently swallowed by whichever editor has focus (BUG-050's defect)."""
    from pgtp_editor.ui.shortcut_registry import EDITOR_UNDO_REDO_CHORDS

    for sequence in EDITOR_UNDO_REDO_CHORDS:
        assert sequence in RESERVED_SEQUENCES
        assert normalize_sequence(sequence) == sequence


def test_the_windows_only_native_undo_pair_is_reserved_and_stated_as_dead():
    """The call DEC-014 left open, decided: `Alt+Backspace` / `Alt+Shift+Backspace`
    are Qt's `KB_Win`-ONLY native undo/redo, so under the owner's rule (*a chord
    means the same thing on both systems or is not bound at all*) they cannot be
    left to Qt. They are SUPPRESSED on both platforms — hence reserved, since a
    menu command moved onto one would be swallowed by every editor."""
    for sequence in ("Alt+Backspace", "Alt+Shift+Backspace"):
        assert sequence in RESERVED_SEQUENCES
        reason = RESERVED_SEQUENCES[sequence]
        assert "Windows" in reason
        assert "dead" in reason
        # And it is refused as a rebinding target, never stolen.
        assert refusal_for("file.open", sequence)


def test_the_undo_and_redo_reasons_point_at_their_rebindable_menu_twin():
    """BUG-064: `Undo` named two different commands. The reserved rows are the
    only place the dialog can explain the difference — rebinding
    `History ▸ Undo Project Edit` cannot move `Ctrl+Z`, and a user who reads
    "Undo" twice with no explanation has been told nothing."""
    for sequence, twin in (
        ("Ctrl+Z", "Undo Project Edit"),
        ("Ctrl+Y", "Redo Project Edit"),
    ):
        reason = RESERVED_SEQUENCES[sequence]
        assert twin in reason
        assert "rebindable" in reason
    # Two rows, two reasons: DEC-014 forbids collapsing the two operations into
    # one statement.
    assert RESERVED_SEQUENCES["Ctrl+Z"] != RESERVED_SEQUENCES["Ctrl+Y"]
    # And Ctrl+Y's row records why it is bound by this app at all: Qt binds it on
    # the Windows scheme only.
    assert "platform" in RESERVED_SEQUENCES["Ctrl+Y"]


def test_ctrl_shift_z_is_reserved_beside_the_history_pair():
    """The chord is still reserved after DEC-015 freed it from redo, and for a
    sharper reason: Qt binds it as native `StandardKey.Redo` under
    `KB_Win | KB_X11`, so every editing surface intercepts it to keep Qt's redo
    from firing. A menu command retargeted here would fire only while no editor
    has focus — a focus-dependent silence, worse than a clean loss."""
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


def test_the_clipboard_reasons_name_both_hosts_and_leave_ctrl_x_alone():
    """BUG-260810143057, the same defect as `Ctrl+Alt+F`'s above. Both reasons
    said only *"a Qt built-in inside every editor widget"* while the caption grid
    binds real slots to both chords, and the reason string is what the user is
    shown when Customize Shortcuts… refuses the key."""
    copy = RESERVED_SEQUENCES["Ctrl+C"]
    paste = RESERVED_SEQUENCES["Ctrl+V"]
    for reason in (copy, paste):
        assert "editor widget" in reason  # Qt's built-in, still named
        assert "Caption Management grid" in reason  # and the real host
        assert "(§26/§27)" in reason  # the citation shape every row carries
    # Two operations, two reasons (DEC-014): never one merged clipboard sentence.
    assert copy != paste
    # `Ctrl+X` is deliberately NOT changed for symmetry: nothing in the app hosts
    # a Cut shortcut, so "a Qt built-in" is the whole truth there and naming a
    # host would make the user-facing text a different kind of wrong.
    cut = RESERVED_SEQUENCES["Ctrl+X"]
    assert cut == "Cut — a Qt built-in inside every editor widget (§26/§27)"
    assert "grid" not in cut


def test_the_older_clipboard_spellings_are_reserved():
    """BUG-260810140553 Part 1. `Ctrl+Insert`, `Shift+Insert` and `Shift+Delete`
    are Qt's older chords for Copy/Paste/Cut and are native on **both** keyboard
    schemes, so they are not a platform split and needed no bind-or-suppress
    ruling — but they were free targets in Customize Shortcuts…, and a menu
    command assigned to `Shift+Insert` would have killed paste-by-`Shift+Insert`
    in every editor on every platform."""
    for sequence in ("Ctrl+Insert", "Shift+Insert", "Shift+Delete"):
        assert sequence in RESERVED_SEQUENCES
        # The ledger's canonical spelling, which `docs/KEYBINDINGS.md` and its
        # test compare against verbatim.
        assert normalize_sequence(sequence) == sequence
        reason = RESERVED_SEQUENCES[sequence]
        assert "both keyboard schemes" in reason
        assert "(§26/§27)" in reason
    # Read back through the spelling-insensitive lookup, as the dialog does with
    # whatever the user pressed.
    assert reserved_reason("Shift+Ins") is not None
    assert reserved_reason("ctrl+ins") is not None
    assert reserved_reason("shift+del") is not None


def test_shift_insert_is_refused_as_a_target_not_stolen():
    refusal = refusal_for("file.open", "Shift+Insert")
    assert refusal and "Shift+Insert" in refusal
    with pytest.raises(ValueError):
        assign_shortcut({"file.open": "Ctrl+O"}, "file.open", "shift+ins")


def test_the_app_owns_its_paste_chords_instead_of_inheriting_qts_table():
    """DEC-015, applied to the read-only surfaces' edit-attempt hint.
    `XmlEditor` used to ask `event.matches(StandardKey.Paste)`, which is Qt's
    per-scheme table: the hint fired for `Ctrl+Shift+Insert`/`F18` on Linux and
    for neither on Windows. `EDITOR_PASTE_CHORDS` is the app's own answer."""
    from pgtp_editor.ui.shortcut_registry import EDITOR_PASTE_CHORDS

    assert EDITOR_PASTE_CHORDS == ("Ctrl+V", "Shift+Insert", "Paste")
    for chord in EDITOR_PASTE_CHORDS:
        assert normalize_sequence(chord) == chord
    # Exactly the subset Qt binds on BOTH schemes, so nothing that raised the
    # hint before stopped doing so...
    assert "Ctrl+Shift+Insert" not in EDITOR_PASTE_CHORDS
    assert "F18" not in EDITOR_PASTE_CHORDS
    # ...and the two modifier chords in the set are reserved, so no command can
    # be retargeted onto a chord an editor answers. `Paste` is a media key, not
    # a chord Customize Shortcuts can hand out, so it needs no row.
    assert reserved_reason("Ctrl+V") is not None
    assert reserved_reason("Shift+Insert") is not None


def test_ctrl_w_and_ctrl_o_are_unreserved_on_purpose():
    """BUG-260810143058, and the reason is recorded here because an
    unreserved-on-purpose chord needs an assertion exactly as much as a reserved
    one — a sweep already re-filed this once.

    `Ctrl+S`/`Ctrl+Shift+S` are reserved for a CAPABILITY reason: FQ-020 removed
    the save gesture altogether, so no command may ever sit there. `Ctrl+W` (and
    its twin `Ctrl+O`) lost its default on 2026-08-09 for a narrower reason — no
    single "close" is the obvious default in an app that closes projects, `.pgtp`
    documents, PHP tabs, DDL object tabs, the XSD tab and console tabs — which is
    an argument against a default, not against a user who knows which close they
    mean. `manual.md` invites the user to assign both.
    """
    assert "Ctrl+W" not in RESERVED_SEQUENCES
    assert "Ctrl+O" not in RESERVED_SEQUENCES
    assert reserved_reason("Ctrl+W") is None
    assert reserved_reason("Ctrl+O") is None
    # The distinction, stated: the capability ban IS reserved.
    assert "Ctrl+S" in RESERVED_SEQUENCES
