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

# pgtp_editor/ui/schema_gesture_seam.py
"""Where FQ-030 slice 3's two pure analyzers meet a `SchemaIndex`.

`ui/expand_select_seam.py`'s role, for the two gestures that arrived after it:

- **JOIN-on-FK** (`sql/join_fk.py`). `find_join_site` is pure text work;
  `join_candidates` needs to be TOLD what the foreign keys are. `join_at`
  supplies them, from the columns of exactly the tables the site named.
- **Signature help** (`sql/signature_help.py`). `find_call_site` is pure text
  work; `signature_help` needs to be told what the shop's routines look like.
  `signature_help_at` supplies them.

Both are Qt-free functions over an already-fetched, already-injected index
(§18.5 D1 -- the panel never talks to a database; §18.6 -- nothing on the caret
path may issue a lazy query). `SchemaGestureHostMixin` below is the small Qt
half: the two gestures as the panels expose them, written once because the DDL
object tab and the Sandbox SQL Console want them identically.

WHAT THE INDEX IS ASKED FOR
---------------------------
Both gestures need more than column *names* (`known_columns`) and popup *rows*
(`column_entries`): the join needs `ColumnInfo.fk_target` and signature help
needs each routine's `args`/`return_type`. `SchemaIndex` publishes both --
`column_infos(table)` and `routines()` (BUG-045) -- and this module reads
nothing else off it, so `ui/` never touches a `db/` object's internals.

Everything stays duck-typed and tolerant of absence: a stub index, an index
that predates those accessors, a table the fetch never saw and a schema with no
routines all yield "nothing to offer", never an exception, because this runs
off a keystroke.
"""
from __future__ import annotations

from ..sql.join_fk import (
    JoinCandidate,
    JoinOptions,
    JoinSite,
    find_join_site,
    foreign_keys_from_targets,
    join_candidates,
    render_join,
)
from ..sql.signature_help import (
    SignatureHelp,
    find_call_site,
    routine_signature,
    signature_help,
)

#: Said when the gesture is invoked in a surface that has no schema injected --
#: the same shape of answer `CodeEditor.expand_select_at_caret` gives when its
#: dynamic expander is unwired: state the missing prerequisite, never nothing.
NO_SCHEMA_JOIN = "writing a JOIN needs a database schema, and this editor has none"
NO_SCHEMA_SIGNATURE = (
    "showing a signature needs a database schema, and this editor has none"
)


# --- reading the index ------------------------------------------------------
def table_columns(index, qualified: str) -> list:
    """`qualified`'s `ColumnInfo` list, or `[]` when it is not in the fetch."""
    getter = getattr(index, "column_infos", None)
    if not callable(getter):
        return []
    try:
        return list(getter(qualified) or ())
    except Exception:  # pragma: no cover - defensive at a keypress
        return []


def foreign_keys_for(index, site: JoinSite):
    """Every `ForeignKey` declared on the tables `site` has in scope.

    One `foreign_keys_from_targets` call per `site.qualified_names` key -- the
    only place `ColumnInfo.fk_target`'s `"schema.table.column"` shape is read,
    and it is read there, in `sql/join_fk.py`, not here.
    """
    keys = []
    for qualified in site.qualified_names:
        keys.extend(
            foreign_keys_from_targets(
                qualified,
                [
                    (column.name, getattr(column, "fk_target", None))
                    for column in table_columns(index, qualified)
                ],
            )
        )
    return tuple(keys)


def join_at(index, text: str, pos: int) -> tuple[JoinSite, JoinOptions]:
    """The join site at `pos` and every join the schema's foreign keys imply.

    Never raises and never returns None: a site that cannot be joined at, and
    an empty candidate set, both come back carrying a `reason` fit to show the
    user (FQ-023 -- a gesture that cannot run says why).
    """
    if index is None:
        return JoinSite(reason=NO_SCHEMA_JOIN), JoinOptions(reason=NO_SCHEMA_JOIN)
    site = find_join_site(text, pos)
    if not site:
        return site, JoinOptions(reason=site.reason)
    return site, join_candidates(site, foreign_keys_for(index, site))


# --- signature help ---------------------------------------------------------
def routine_signatures(index) -> tuple:
    """Every fetched routine as a `RoutineSignature`, keyed `"schema.name"`.

    Overloads keep their own entry: `DatabaseSchema.routines` is keyed by
    `RoutineInfo.signature` (name PLUS argument types, §18.1), so two overloads
    are two rows here and `signature_help` ranks them by arity fit.
    """
    getter = getattr(index, "routines", None)
    if not callable(getter):
        return ()
    try:
        routines = tuple(getter() or ())
    except Exception:  # pragma: no cover - defensive at a keypress
        return ()
    return tuple(
        routine_signature(
            f"{routine.schema}.{routine.name}",
            getattr(routine, "args", ()) or (),
            getattr(routine, "return_type", None),
            getattr(routine, "kind", "function"),
        )
        for routine in routines
    )


def signature_help_at(index, text: str, pos: int) -> SignatureHelp:
    """The signature help for the call the caret is inside, or a stated refusal."""
    if index is None:
        return SignatureHelp(reason=NO_SCHEMA_SIGNATURE)
    site = find_call_site(text, pos)
    if not site:
        return SignatureHelp(reason=site.reason)
    return signature_help(site, routine_signatures(index))


def describe_signature(help: SignatureHelp) -> str:
    """The signature help as the caret tooltip's two or three plain-text lines.

    Line 1 is the signature. Line 2 marks the parameter the caret is filling in
    -- the whole point of the gesture, and the one thing a bare signature line
    does not say. A third line appears only when there is more than one
    overload, because saying "1 of 1" is noise.
    """
    if not help:
        return help.reason or "there is no signature to show here"
    lines = [help.label]
    parameter = help.parameter
    if parameter is not None:
        lines.append(f"→ {parameter.label}")
    else:
        lines.append("→ this call has no parameter at that position")
    if len(help.signatures) > 1:
        lines.append(
            f"({help.active_signature + 1} of {len(help.signatures)} overloads)"
        )
    return "\n".join(lines)


# --- the Qt half: both gestures, once ---------------------------------------
class SchemaGestureHostMixin:
    """FQ-030 slice 3's two gestures for a panel that hosts a `CodeEditor`.

    Requirements on the host, all of which both SQL panels already meet: a
    `self.editor` `CodeEditor`, a `self._schema_index` (None when none is
    injected), and `CompletionPopupHostMixin` mixed in -- the ambiguous join is
    offered through **that** popup, never a second list widget.

    Like the other mixins here it has no `__init__`: the two attributes it owns
    are class-level defaults, and the join gesture replaces them wholesale each
    time it offers a choice, so nothing is shared between instances.
    """

    #: The site the currently-offered join candidates were computed for.
    _join_site: JoinSite | None = None
    #: `JoinCandidate.key` -> candidate, for the popup's chosen-key callback.
    _join_choices: dict = {}

    # --- JOIN-on-FK (Ctrl+Alt+J) -------------------------------------------
    def join_on_fk(self) -> bool:
        """Write the `JOIN ... ON ...` the caret's FROM clause already implies.

        One candidate is written straight into the buffer, through
        `CodeEditor.apply_expansion` -- the same single-undo path a snippet and
        an expand-`SELECT` go through, and the only insertion path there is.
        Several candidates are **offered, not guessed at** (`sql/join_fk.py`'s
        rule): the shared completion popup lists each one's rendered `ON`
        clause and the author picks. Nothing to offer is a stated refusal.
        """
        editor = self.editor
        site, options = join_at(
            self._schema_index, editor.toPlainText(), editor.textCursor().position()
        )
        if not options:
            editor.report_refusal(options.reason or site.reason)
            return False
        only = options.only
        if only is not None:
            return editor.apply_expansion(render_join(site, only))
        self._offer_join_choice(site, options)
        return True

    def _offer_join_choice(self, site: JoinSite, options: JoinOptions) -> None:
        """List every candidate join in the shared popup, keyed by identity."""
        self._join_site = site
        self._join_choices = {candidate.key: candidate for candidate in options}
        popup = self._ensure_completion_popup()
        popup.set_items(
            [(candidate.key, candidate.display) for candidate in options]
        )
        self._rewire_popup(popup, self._apply_join_choice)
        self._popup_at_caret(popup)

    def _apply_join_choice(self, key: str) -> bool:
        """Apply the candidate the popup's chosen `key` names."""
        popup = self._completion_popup
        if popup is not None:
            popup.hide()
        self.editor.setFocus()
        site = self._join_site
        candidate: JoinCandidate | None = self._join_choices.get(key)
        if site is None or candidate is None:
            self.editor.report_refusal("that join is no longer available")
            return False
        return self.editor.apply_expansion(render_join(site, candidate))

    # --- Signature help (Ctrl+Shift+Space) ---------------------------------
    def show_signature_help(self) -> bool:
        """Show what the call at the caret expects -- a QUERY, never an insert.

        Nothing is written to the buffer: the answer appears as a transient
        tooltip at the caret (`CodeEditor.show_hint`), which is where the
        author is looking and what an editor hint is everywhere else. A caret
        that is not inside a known call is a stated refusal, not silence.
        """
        editor = self.editor
        help = signature_help_at(
            self._schema_index, editor.toPlainText(), editor.textCursor().position()
        )
        if not help:
            editor.report_refusal(help.reason)
            return False
        editor.show_hint(describe_signature(help))
        return True
