"""`docs/KEYBINDINGS.md` and the code agree, in both directions.

**Why this test is the deliverable and the document is not.**
`shortcut_registry.RESERVED_SEQUENCES` was already meant to be the register of
every chord in the app, and its own docstring says it was *"transcribed from
§27"*. That transcription silently lost `Ctrl+Shift+Z` until BUG-050 found it the
expensive way. A ledger nobody verifies is a second document, so this test exists
to make the ledger the kind of thing that cannot rot quietly:

* **Code -> ledger.** Every chord any of the six keystroke mechanisms binds must
  have a row, and that row must name the *file* that binds it. Add a shortcut in
  a new module and this fails until the ledger names the module.
* **Ledger -> code.** Every row must correspond to something real: a derived
  binding, a module that genuinely does key handling, a Qt `StandardKey` that
  genuinely carries the chord, or -- for a row that claims a chord is
  deliberately dead -- the *absence* of any binding for it.

**The code side is derived, never restated.** An AST walk finds every
`setShortcut(...)` / `QShortcut(...)`, `EDITOR_CHORDS` supplies the
editor chord set, the set of surfaces that call `classify_editor_chord`
supplies "which editing surfaces state their answer", and Qt's own binding table
is read with `QKeySequence.keyBindings`. A test that hardcoded the same list a
second time would prove only that someone typed it twice.

**Two facts built in rather than rediscovered.** The offscreen platform reports
Qt's **Windows** keyboard scheme, so a Linux-only dead key is invisible to the
whole suite -- Appendix A's per-scheme table is therefore checked against
whichever scheme is live, detected rather than assumed, and the other column
stands as the measured record from the machine it was measured on. And nothing
here drives real key presses: what is asserted is the app's stated host, never
Qt's native answer.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pgtp_editor.ui.shortcut_registry import (
    EDITOR_CHORDS,
    RESERVED_SEQUENCES,
    normalize_sequence,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "pgtp_editor"
LEDGER_PATH = REPO_ROOT / "docs" / "KEYBINDINGS.md"

QACTION = "QAction"
QSHORTCUT = "QShortcut"
QSHORTCUT_STANDARD_KEY = "QShortcut(StandardKey)"
KEY_PRESS_EVENT = "keyPressEvent"
EVENT_FILTER = "eventFilter"
QT_DEFAULT = "Qt default"
UNBOUND = "unbound"

MECHANISMS = {
    QACTION,
    QSHORTCUT,
    QSHORTCUT_STANDARD_KEY,
    KEY_PRESS_EVENT,
    EVENT_FILTER,
    QT_DEFAULT,
    UNBOUND,
}

GATES = {"DEC-009", "DEC-012", "DEC-014", "DEC-015", "Qt", "bare-key", "dead"}

WIDGET_MECHANISMS = {KEY_PRESS_EVENT, EVENT_FILTER}

#: What makes a module named by a row plausible as a keyboard host even when the
#: chord itself is not a literal in that file: the shared editor-chord matcher, the
#: shared per-tab focus-shortcut installer, a `Key_*` branch, or a `StandardKey`
#: test. Deliberately loose -- the strong direction is code -> ledger; this only
#: catches a row naming a module that has nothing to do with the keyboard.
KEY_HANDLING_EVIDENCE = (
    "classify_editor_chord",
    "install_focus_shortcuts",
    "Key_",
    "StandardKey",
    "keyPressEvent",
    "eventFilter",
)

_BACKTICKED = re.compile(r"`([^`]+)`")
_PY_REFERENCE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*\.py)`")
_QT_MARKER = re.compile(r"\[qt:([A-Za-z]+)\]")


# --------------------------------------------------------------------------
# the ledger side: parse docs/KEYBINDINGS.md
# --------------------------------------------------------------------------


@dataclass
class LedgerRow:
    chord: str
    raw_chord: str
    command: str
    mechanisms: set[str]
    surfaces: str
    gates: set[str]
    reserved: bool
    notes: str
    line_number: int
    files: set[str] = field(default_factory=set)
    standard_keys: set[str] = field(default_factory=set)

    @property
    def text(self) -> str:
        return " | ".join(
            (self.command, self.surfaces, self.notes)
        )


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _table_after(lines: list[str], heading: str) -> list[tuple[int, list[str]]]:
    """The first pipe table that follows `heading`, as (line number, cells)."""
    start = next(
        index for index, line in enumerate(lines) if line.strip() == heading
    )
    rows: list[tuple[int, list[str]]] = []
    seen_header = False
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip().startswith("|"):
            if rows:
                break
            continue
        cells = _split_row(line)
        if not seen_header:
            seen_header = True
            continue
        if set("".join(cells)) <= set("- :"):
            continue  # the header separator
        rows.append((index + 1, cells))
    return rows


def _first_backticked(cell: str) -> str:
    match = _BACKTICKED.search(cell)
    assert match is not None, f"expected a backticked value in {cell!r}"
    return match.group(1)


def load_ledger() -> list[LedgerRow]:
    lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    rows: list[LedgerRow] = []
    for line_number, cells in _table_after(lines, "## The register"):
        assert len(cells) == 7, (
            f"{LEDGER_PATH.name}:{line_number}: expected 7 columns "
            f"(chord, command, mechanism, surfaces, gate, reserved, notes), "
            f"got {len(cells)}"
        )
        raw_chord = _first_backticked(cells[0])
        row = LedgerRow(
            chord=normalize_sequence(raw_chord),
            raw_chord=raw_chord,
            command=cells[1],
            mechanisms=set(_BACKTICKED.findall(cells[2])),
            surfaces=cells[3],
            gates=set(_BACKTICKED.findall(cells[4])),
            reserved=cells[5].strip().lower() == "yes",
            notes=cells[6],
            line_number=line_number,
        )
        row.files = set(_PY_REFERENCE.findall(" | ".join(cells)))
        row.standard_keys = set(_QT_MARKER.findall(" | ".join(cells)))
        assert cells[5].strip().lower() in ("yes", "no"), (
            f"{LEDGER_PATH.name}:{line_number}: the Reserved column for "
            f"{raw_chord} must be 'yes' or 'no', not {cells[5]!r}"
        )
        rows.append(row)
    assert rows, "the register table is empty"
    return rows


def load_scheme_table() -> dict[str, dict[str, set[str]]]:
    """Appendix A as `{StandardKey: {"windows": {...}, "kde": {...}}}`."""
    lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    table: dict[str, dict[str, set[str]]] = {}
    for line_number, cells in _table_after(
        lines, "## Appendix A — Qt's own binding table, per scheme"
    ):
        assert len(cells) == 4, (
            f"{LEDGER_PATH.name}:{line_number}: Appendix A needs 4 columns"
        )
        name = _first_backticked(cells[0])
        table[name] = {
            "windows": {
                normalize_sequence(chord)
                for chord in _BACKTICKED.findall(cells[1])
            },
            "kde": {
                normalize_sequence(chord)
                for chord in _BACKTICKED.findall(cells[2])
            },
        }
    assert table, "Appendix A is empty"
    return table


# --------------------------------------------------------------------------
# the code side: derive it, never restate it
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Binding:
    mechanism: str
    #: A literal chord for `QAction`/`QShortcut`; a `StandardKey` name for
    #: `QShortcut(StandardKey)`, because its chords come from Qt's table and
    #: therefore depend on the running keyboard scheme.
    value: str
    filename: str
    line_number: int


def _standard_key_name(node: ast.AST) -> str | None:
    """`QKeySequence.StandardKey.Copy` -> `"Copy"`."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return parts[0] if "StandardKey" in parts else None


def _sequence_argument(node: ast.AST | None) -> tuple[str, str] | None:
    """`("literal", "Ctrl+G")` / `("standardkey", "Copy")` / None.

    None covers every form that cannot be read statically -- most importantly
    `setShortcut(QKeySequence())` (the clear-first pass of
    `MainWindow._apply_shortcut_bindings`) and `setShortcut(QKeySequence(seq))`
    for a resolved user override, neither of which is a *default* binding and
    neither of which belongs in the ledger.
    """
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return ("literal", node.value)
    name = _standard_key_name(node)
    if name is not None:
        return ("standardkey", name)
    if isinstance(node, ast.Call):
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if called == "QKeySequence" and node.args:
            return _sequence_argument(node.args[0])
    return None


def derive_bindings() -> list[Binding]:
    """Every statically declared `QAction`/`QShortcut` binding in the package."""
    bindings: list[Binding] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = (
                func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            )
            if called in ("setShortcut", "setShortcuts"):
                mechanism = QACTION
            elif called == "QShortcut":
                mechanism = QSHORTCUT
            else:
                continue
            if not node.args:
                continue
            parsed = _sequence_argument(node.args[0])
            if parsed is None:
                continue
            kind, value = parsed
            if kind == "standardkey":
                assert mechanism == QSHORTCUT, (
                    f"{path.name}:{node.lineno}: a QAction bound to a "
                    f"StandardKey is a mechanism this ledger does not model yet"
                )
                mechanism = QSHORTCUT_STANDARD_KEY
            else:
                value = normalize_sequence(value)
                if not value:
                    continue
            bindings.append(
                Binding(mechanism, value, path.name, node.lineno)
            )
    return bindings


def derive_editor_chord_surfaces() -> set[str]:
    """The modules that state an answer for the reserved editor chord set."""
    return {
        path.name
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        if "classify_editor_chord(" in path.read_text(encoding="utf-8")
        and path.name != "shortcut_registry.py"
    }


def source_of(filename: str) -> str:
    matches = list(PACKAGE_ROOT.rglob(filename))
    assert matches, f"{filename} is named by the ledger but does not exist"
    return matches[0].read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ledger() -> list[LedgerRow]:
    return load_ledger()


@pytest.fixture(scope="module")
def by_chord(ledger) -> dict[str, LedgerRow]:
    return {row.chord: row for row in ledger}


@pytest.fixture(scope="module")
def bindings() -> list[Binding]:
    return derive_bindings()


@pytest.fixture(scope="module")
def scheme_table() -> dict[str, dict[str, set[str]]]:
    return load_scheme_table()


@pytest.fixture(scope="module")
def live_scheme(qapp) -> str:
    """`"windows"` or `"kde"` -- which of Appendix A's columns this run can
    verify. Detected, never assumed: the offscreen platform reports Qt's
    Windows scheme, and `Ctrl+Y` as a native Redo binding is what distinguishes
    it (BUG-056/DEC-015 turn on exactly that fact)."""
    from PySide6.QtGui import QKeySequence

    redo = {
        normalize_sequence(sequence.toString())
        for sequence in QKeySequence.keyBindings(QKeySequence.StandardKey.Redo)
    }
    return "windows" if "Ctrl+Y" in redo else "kde"


@pytest.fixture(scope="module")
def qt_bindings(qapp):
    """`{StandardKey name: {chord, ...}}` as the running scheme reports it."""
    from PySide6.QtGui import QKeySequence

    def read(name: str) -> set[str]:
        key = getattr(QKeySequence.StandardKey, name, None)
        assert key is not None, f"{name} is not a QKeySequence.StandardKey"
        return {
            normalize_sequence(sequence.toString())
            for sequence in QKeySequence.keyBindings(key)
        }

    return read


# --------------------------------------------------------------------------
# hygiene: the ledger is parseable and speaks the stated vocabulary
# --------------------------------------------------------------------------


def test_every_chord_is_in_canonical_spelling(ledger):
    for row in ledger:
        assert row.chord == row.raw_chord, (
            f"{LEDGER_PATH.name}:{row.line_number}: chord {row.raw_chord!r} is "
            f"not in the ledger's canonical spelling -- write {row.chord!r} "
            f"(the form normalize_sequence produces), or comparisons against "
            f"the code silently miss it"
        )
        assert row.chord, f"{LEDGER_PATH.name}:{row.line_number}: empty chord"


def test_no_chord_has_two_rows(ledger):
    seen: dict[str, int] = {}
    for row in ledger:
        assert row.chord not in seen, (
            f"{row.chord} has two rows ({LEDGER_PATH.name}:{seen[row.chord]} "
            f"and :{row.line_number}). One row per chord -- a chord with two "
            f"rows is how two different answers both look documented"
        )
        seen[row.chord] = row.line_number


def test_mechanism_and_gate_vocabulary_is_closed(ledger):
    for row in ledger:
        assert row.mechanisms, (
            f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} names no host "
            f"mechanism"
        )
        unknown = row.mechanisms - MECHANISMS
        assert not unknown, (
            f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} names unknown "
            f"mechanism(s) {sorted(unknown)}; the vocabulary is "
            f"{sorted(MECHANISMS)}"
        )
        assert row.gates, (
            f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} has no gate. "
            f"The gate is the classification the policy turns on -- a row "
            f"without one cannot be reasoned about"
        )
        unknown_gates = row.gates - GATES
        assert not unknown_gates, (
            f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} names unknown "
            f"gate(s) {sorted(unknown_gates)}; the vocabulary is {sorted(GATES)}"
        )


# --------------------------------------------------------------------------
# code -> ledger
# --------------------------------------------------------------------------


def test_every_literal_binding_in_the_code_has_a_row(bindings, by_chord):
    missing: list[str] = []
    for binding in bindings:
        if binding.mechanism == QSHORTCUT_STANDARD_KEY:
            continue
        row = by_chord.get(binding.value)
        if row is None:
            missing.append(
                f"{binding.value} is bound as a {binding.mechanism} at "
                f"{binding.filename}:{binding.line_number} and has NO row in "
                f"{LEDGER_PATH.name}"
            )
            continue
        if binding.mechanism not in row.mechanisms:
            missing.append(
                f"{binding.value} is bound as a {binding.mechanism} at "
                f"{binding.filename}:{binding.line_number}, but its row "
                f"({LEDGER_PATH.name}:{row.line_number}) lists only "
                f"{sorted(row.mechanisms)} as its host mechanism"
            )
        if binding.filename not in row.files:
            missing.append(
                f"{binding.value} is bound at {binding.filename}:"
                f"{binding.line_number}, but its row "
                f"({LEDGER_PATH.name}:{row.line_number}) does not name "
                f"`{binding.filename}` -- a host the ledger does not name is a "
                f"host the next chord question will miss"
            )
    assert not missing, "the code binds chords the ledger does not state:\n" + "\n".join(
        missing
    )


def test_every_standard_key_host_has_a_row(bindings, by_chord, qt_bindings):
    """A `QShortcut(StandardKey)` host answers *every* chord Qt gives that key,
    so every one of them needs a row -- this is where `Ctrl+Insert` and the
    `Copy` media key come from, and pretending the host answers only `Ctrl+C`
    is how an alias chord ends up bindable by Customize Shortcuts."""
    missing: list[str] = []
    for binding in bindings:
        if binding.mechanism != QSHORTCUT_STANDARD_KEY:
            continue
        for chord in sorted(qt_bindings(binding.value)):
            row = by_chord.get(chord)
            if row is None:
                missing.append(
                    f"{chord} is answered by the StandardKey."
                    f"{binding.value} shortcut at {binding.filename}:"
                    f"{binding.line_number} and has NO row in "
                    f"{LEDGER_PATH.name}"
                )
                continue
            if QSHORTCUT_STANDARD_KEY not in row.mechanisms:
                missing.append(
                    f"{chord}'s row ({LEDGER_PATH.name}:{row.line_number}) "
                    f"does not list `{QSHORTCUT_STANDARD_KEY}` as a host "
                    f"mechanism, but StandardKey.{binding.value} at "
                    f"{binding.filename}:{binding.line_number} answers it"
                )
            if binding.value not in row.standard_keys:
                missing.append(
                    f"{chord}'s row ({LEDGER_PATH.name}:{row.line_number}) "
                    f"carries no [qt:{binding.value}] marker, so nothing ties "
                    f"it to the scheme table it depends on"
                )
            if binding.filename not in row.files:
                missing.append(
                    f"{chord}'s row ({LEDGER_PATH.name}:{row.line_number}) "
                    f"does not name `{binding.filename}`, which hosts it via "
                    f"StandardKey.{binding.value}"
                )
    assert not missing, (
        "Qt's StandardKey table hands the code chords the ledger does not "
        "state:\n" + "\n".join(missing)
    )


def test_every_reserved_sequence_has_a_row_marked_reserved(by_chord):
    """`RESERVED_SEQUENCES` and the Reserved column are the same set.

    Both directions, because both failures are real: a reservation with no row
    is the BUG-050 shape (`Ctrl+Shift+Z` reserved in code, absent from the
    register), and a row claiming to be reserved while the dialog would happily
    hand the chord out is worse -- it reads as protection that is not there.
    """
    reserved_in_code = {normalize_sequence(chord) for chord in RESERVED_SEQUENCES}
    reserved_in_ledger = {chord for chord, row in by_chord.items() if row.reserved}
    for chord in sorted(reserved_in_code - reserved_in_ledger):
        pytest.fail(
            f"{chord} is in shortcut_registry.RESERVED_SEQUENCES but "
            f"{LEDGER_PATH.name} does not mark it reserved (missing row, or "
            f"Reserved = no)"
        )
    for chord in sorted(reserved_in_ledger - reserved_in_code):
        pytest.fail(
            f"{LEDGER_PATH.name} marks {chord} reserved but it is NOT in "
            f"shortcut_registry.RESERVED_SEQUENCES, so Customize Shortcuts "
            f"would accept it as a rebinding target"
        )


def test_editor_chord_set_rows_state_the_operation_and_every_surface(by_chord):
    """DEC-014's invariant, verified against the ledger: for every chord the
    editor chord set claims, the row names the operation *and* every surface
    that states an answer -- the surface list derived from the code, not typed
    out here."""
    surfaces = derive_editor_chord_surfaces()
    assert len(surfaces) >= 6, (
        f"only {sorted(surfaces)} call classify_editor_chord; the six "
        f"editing surfaces are the premise of DEC-014"
    )
    for chord, operation in EDITOR_CHORDS.items():
        normalized = normalize_sequence(chord)
        row = by_chord.get(normalized)
        assert row is not None, (
            f"{normalized} is in EDITOR_CHORDS and has no row in "
            f"{LEDGER_PATH.name}"
        )
        assert operation.lower() in row.text.lower(), (
            f"{LEDGER_PATH.name}:{row.line_number}: {normalized} is classified "
            f"{operation!r} by EDITOR_CHORDS but the row never says "
            f"so -- a chord whose row does not state its operation is how a "
            f"redo becomes an undo"
        )
        for surface in sorted(surfaces):
            assert surface in row.files, (
                f"{LEDGER_PATH.name}:{row.line_number}: {normalized} is "
                f"answered in `{surface}` (it calls classify_editor_chord) "
                f"but the row does not name that surface"
            )
        assert row.mechanisms & WIDGET_MECHANISMS, (
            f"{LEDGER_PATH.name}:{row.line_number}: {normalized} is answered "
            f"inside widget key handling, so its mechanism must include "
            f"{sorted(WIDGET_MECHANISMS)}"
        )


# --------------------------------------------------------------------------
# ledger -> code
# --------------------------------------------------------------------------


def test_every_row_names_only_real_and_relevant_modules(ledger, bindings):
    derived: dict[tuple[str, str], list[Binding]] = defaultdict(list)
    for binding in bindings:
        derived[(binding.value, binding.filename)].append(binding)
    problems: list[str] = []
    for row in ledger:
        for filename in sorted(row.files):
            matches = list(PACKAGE_ROOT.rglob(filename))
            if not matches:
                problems.append(
                    f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} names "
                    f"`{filename}`, which does not exist in the package"
                )
                continue
            if (row.chord, filename) in derived:
                continue
            source = matches[0].read_text(encoding="utf-8")
            if any(marker in source for marker in KEY_HANDLING_EVIDENCE):
                continue
            if row.standard_keys and "StandardKey" in source:
                continue
            problems.append(
                f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} names "
                f"`{filename}`, but that module neither binds the chord nor "
                f"does any key handling at all"
            )
    assert not problems, "\n".join(problems)


def test_pure_shortcut_rows_are_backed_by_a_real_binding(ledger, bindings):
    """A row whose only mechanisms are `QAction`/`QShortcut` is a claim that a
    literal binding exists somewhere. Verify it does -- otherwise a deleted
    shortcut leaves a row saying the chord still works."""
    literal = {
        binding.value
        for binding in bindings
        if binding.mechanism in (QACTION, QSHORTCUT)
    }
    for row in ledger:
        if row.mechanisms <= {QACTION, QSHORTCUT}:
            assert row.chord in literal, (
                f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} is listed "
                f"as a {sorted(row.mechanisms)} binding, but no "
                f"setShortcut/QShortcut in the package binds it -- either the "
                f"binding was deleted or the mechanism column is wrong"
            )


def test_widget_rows_name_a_module_that_really_handles_keys(ledger):
    for row in ledger:
        if not row.mechanisms & WIDGET_MECHANISMS:
            continue
        hosts = [
            filename
            for filename in sorted(row.files)
            if any(
                token in source_of(filename)
                for token in ("def keyPressEvent", "def eventFilter")
            )
        ]
        assert hosts, (
            f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} claims to be "
            f"answered in widget key handling, but none of the modules it "
            f"names ({sorted(row.files)}) defines keyPressEvent or eventFilter"
        )


def test_rows_claiming_a_chord_is_dead_are_bound_by_nothing(ledger, bindings, qt_bindings):
    """`unbound` is a real, load-bearing state here (`Ctrl+S` since FQ-020), and
    the only way it stays true is by checking that nothing has quietly bound it
    again -- including through a `StandardKey` host."""
    bound: set[str] = set()
    for binding in bindings:
        if binding.mechanism == QSHORTCUT_STANDARD_KEY:
            bound |= qt_bindings(binding.value)
        else:
            bound.add(binding.value)
    for row in ledger:
        if UNBOUND not in row.mechanisms:
            continue
        assert row.chord not in bound, (
            f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} is documented "
            f"as deliberately unbound, but the package binds it. Either a "
            f"decision was reversed by accident or the ledger is stale"
        )
        assert "dead" in row.gates, (
            f"{LEDGER_PATH.name}:{row.line_number}: an `unbound` row must "
            f"carry the `dead` gate"
        )


def test_qt_default_rows_point_at_a_standard_key_that_carries_the_chord(
    ledger, scheme_table
):
    """A row that says "Qt answers this one" must say *which* standard key, and
    that key's Appendix A row must really carry the chord on at least one
    scheme. This is the check that stops a plausible-sounding but wrong "Qt
    handles it" from entering the register."""
    for row in ledger:
        if not row.mechanisms & {QT_DEFAULT, UNBOUND}:
            continue
        assert row.standard_keys, (
            f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} is attributed "
            f"to Qt's own handling but carries no [qt:StandardKey] marker"
        )
        for name in sorted(row.standard_keys):
            assert name in scheme_table, (
                f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} points at "
                f"[qt:{name}], which has no row in Appendix A"
            )
            schemes = scheme_table[name]
            assert row.chord in schemes["windows"] | schemes["kde"], (
                f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} claims to "
                f"come from StandardKey.{name}, but Appendix A shows that key "
                f"binding {sorted(schemes['windows'] | schemes['kde'])} on "
                f"neither scheme"
            )


def test_widget_hosted_modifier_chords_are_reserved(ledger):
    """The policy, as a test: *"answered inside a widget's key handling? It must
    be in RESERVED_SEQUENCES"*. Scoped to `Ctrl`/`Alt`/`Meta` chords, because a
    bare key (`Tab`, `Return`, `Escape`) is not a rebinding target the dialog
    could hand out in the first place -- which is what the `bare-key` gate
    records.

    A row that IS reserved satisfies the rule whatever shape its chord has, and
    is checked first: the `bare-key` branch exists only to excuse an *unreserved*
    row, so demanding that gate from a reserved one would force a `Shift+Insert`
    (a real rebinding target, reserved since BUG-260810140553) to claim it is a
    bare key.
    """
    for row in ledger:
        if not row.mechanisms & WIDGET_MECHANISMS:
            continue
        if row.reserved:
            continue
        if not any(
            row.chord.startswith(prefix) or f"+{prefix}" in row.chord
            for prefix in ("Ctrl", "Alt", "Meta")
        ):
            assert "bare-key" in row.gates, (
                f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} is "
                f"answered in widget key handling and carries no modifier, so "
                f"it needs the `bare-key` gate to say the reservation rule "
                f"does not reach it"
            )
            continue
        assert row.reserved, (
            f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} is answered "
            f"inside a widget's key handling, so under DEC-014 it must be "
            f"reserved -- otherwise Customize Shortcuts can hand it to a menu "
            f"command that the focused widget will then swallow (BUG-050)"
        )


def test_dec014_and_dec015_gates_are_used_consistently(ledger, by_chord):
    editor_chords = {
        normalize_sequence(chord) for chord in EDITOR_CHORDS
    }
    for row in ledger:
        if "DEC-014" in row.gates:
            assert row.chord in editor_chords, (
                f"{LEDGER_PATH.name}:{row.line_number}: {row.chord} carries "
                f"the DEC-014 gate, which is the fixed chord set every editing "
                f"surface must answer -- but it is not in "
                f"EDITOR_CHORDS"
            )
    for chord in sorted(editor_chords):
        row = by_chord[chord]
        assert {"DEC-014", "DEC-015"} <= row.gates, (
            f"{LEDGER_PATH.name}:{row.line_number}: {chord} is in the editor "
            f"chord set, so its gate is DEC-014 (every surface states its "
            f"answer) *and* DEC-015 (the app binds or suppresses it on both "
            f"schemes, never inherits Qt's answer)"
        )


# --------------------------------------------------------------------------
# Appendix A: Qt's table, measured rather than recalled
# --------------------------------------------------------------------------


def test_appendix_a_matches_the_running_keyboard_scheme(
    scheme_table, live_scheme, qt_bindings
):
    """The half of Appendix A this run can see must be exact.

    Only half: the offscreen platform reports Qt's **Windows** scheme, so a
    Linux-only binding is invisible here (and vice versa on a real Linux
    desktop). The other column stands as the measured record from the machine
    it was measured on -- which is the whole reason it is written down.
    """
    wrong: list[str] = []
    for name, columns in sorted(scheme_table.items()):
        expected = columns[live_scheme]
        actual = qt_bindings(name)
        if expected != actual:
            wrong.append(
                f"StandardKey.{name}: Appendix A's {live_scheme} column says "
                f"{sorted(expected)}, Qt reports {sorted(actual)} "
                f"(missing from the ledger: {sorted(actual - expected)}; "
                f"claimed but not bound: {sorted(expected - actual)})"
            )
    assert not wrong, (
        f"Appendix A no longer matches the {live_scheme} keyboard scheme Qt "
        f"reports on this run:\n" + "\n".join(wrong)
    )


def test_the_platform_conditional_facts_the_policy_turns_on_still_hold(
    scheme_table,
):
    """The three measured facts every keyboard decision in this project rests
    on, asserted against Appendix A so a Qt upgrade that changes them cannot
    pass silently: `Ctrl+Y` is a native Redo on Windows only (hence DEC-015's
    explicit binding), the `Alt+Backspace` pair is Windows-only (hence
    suppressing it on both), and `Ctrl+Shift+Z` is a native Redo on *both*
    (hence every surface must intercept it)."""
    redo = scheme_table["Redo"]
    undo = scheme_table["Undo"]
    assert "Ctrl+Y" in redo["windows"] and "Ctrl+Y" not in redo["kde"]
    assert (
        "Alt+Shift+Backspace" in redo["windows"]
        and "Alt+Shift+Backspace" not in redo["kde"]
    )
    assert (
        "Alt+Backspace" in undo["windows"] and "Alt+Backspace" not in undo["kde"]
    )
    assert "Ctrl+Shift+Z" in redo["windows"] and "Ctrl+Shift+Z" in redo["kde"], (
        "Ctrl+Shift+Z is a native Qt Redo on both schemes -- if that ever "
        "stops being true, every editing surface's interception of it is no "
        "longer load-bearing and DEC-015's reasoning changes"
    )
