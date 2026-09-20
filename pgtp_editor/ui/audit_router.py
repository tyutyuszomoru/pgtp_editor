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

# pgtp_editor/ui/audit_router.py
"""`AuditRouter` — the one place a produced Audit row is assigned a surface
(FQ-028).

§7 used to reserve nine prefixes **against one another inside one panel**. That
rule is dissolved: a prefix no longer competes for space, it names a
DESTINATION. This object is that mapping, and it is deliberately the ONLY thing
that changed for the producers — `find_controller`, `lint_controller`,
`xsd_controller`, `generation_controller`, `ddl_project_controller` and the
host's own reporters all still call `audit.addItem(...)` exactly as before,
because the router quacks like the `QListWidget` they were written against.

**The destinations** (FQ-028's complete disposition table):

===============  ==========================  ========================
Prefix           Destination                 Lifecycle
===============  ==========================  ========================
``[Find]``       Findings tab (left dock)    ephemeral, clear-on-new
``[Bookmark]``   Findings tab (left dock)    ephemeral, clear-on-new
``[Validate]``   Messages tab (bottom)       accumulated
``[Lint]``       Messages tab (bottom)       accumulated
``[Check]``      Messages tab (bottom)       accumulated (narrative
                                             rides in the same block)
``[Schema]``     Messages tab **if VERIFY**  accumulated
``[Schema]``     Activity Log otherwise      append-only journal
``[PHP]``        Activity Log                append-only journal
``[SQL]``        Activity Log                append-only journal
``[Project]``    Activity Log                append-only journal
``[Project]``    Activity Log **and** the    journalled *and*
during a close   Messages tab                rendered — see BUG-042
``[Sandbox]``    Messages tab (bottom)       accumulated
``[DDL]``        Messages tab (bottom)       accumulated
===============  ==========================  ========================

``[DDL]`` is an **eleventh** prefix (FQ-260812022749), carrying the dual-mode
DDL verdict -- *full `pg_dump` view* vs. *restricted, catalog-reconstructed
DDL* -- and it is emitted on EVERY DDL open, by owner ruling (*"this way the
choice is clear"*). It goes to the Messages tab because that is the visible,
accumulating surface where `[Check]`/`[Lint]`/`[Validate]` output already
lands. **It must never be routed to the status bar**: `StaticStatusBar.
showMessage` paints nothing (it journals into the Activity Log and
`displayed_message()` is permanently `""`), so that route would repeat
BUG-260812002307 exactly. A new prefix was needed rather than reusing one of
the ten: `[Sandbox]` is the sandbox-operation lane, and an unprefixed row --
which already defaults to `TO_RESULTS` -- cannot be recognised or filtered.

``[Sandbox]`` is a **tenth** prefix (`ui/main_window.py::_SANDBOX_PREFIX`, the
sandbox-operation outcome line) that FQ-028's nine-row table does not mention,
so its home is a decision this implementation had to make and reports rather
than absorb silently. It reads like Activity-Log narration, but it is emitted
DURING a project transition (BUG-040 auto-opens the session inside
`set_active_project`, before `project_changed` fires) and FQ-019's journal
REPLACES its display buffer on that transition — a line filed there would be
wiped off screen by the very open it describes. It is also, in substance, the
outcome of an operation the user asked for. So it rides the Messages tab, which
accumulates and survives the transition.

**BUG-042: the one row with TWO destinations.** ``[Project]`` narration emitted
*during a project close* — today only ``remind_pending_deploys_on_close``'s "N
DDL object(s) have local edits pending a batch deploy" — was written to the
closing project's ``activity.jsonl`` and then wiped off screen by the very
transition that produced it, so the user was told something at the exact moment
they could no longer read it. It cannot be emitted later: it runs upstream of
``project_changed`` and needs the ``_folder``/``_settings`` that close then
clears.

It is the only case where a row goes to two places, and both are deliberate:
the **journal write stays exactly as it was** (the line belongs to the closing
project's history, and an entry never migrates between stores), and the
**Messages tab additionally renders it**, because that tab is not cleared by a
project transition and is therefore the only surface that can still show it.

The split is by ROUTER STATE, not by prefix and not by text — the
``schema_run`` precedent — because "was this emitted during a close?" is the
actual criterion and no wording test can answer it. It is deliberately NOT the
whole ``[Project]`` prefix: of this app's eight ``[Project]`` emit sites, seven
are already fine (the open-time ones run *after* ``project_changed``, which is
why FQ-019's store-switch-first ordering is load-bearing, and the async probe
failures are off-transition entirely). Moving all of them would relocate seven
correct journal lines to fix one broken one.

**The virtual view.** `count()`/`item()`/`takeItem()` present the routed rows
as one list in INSERTION order, excluding both the run-separator furniture and
the rows that went to the Activity Log (which is a journal, not a list of
findings). That is what lets the producers' existing "remove my own prior rows"
loops keep working against the surface their rows actually landed on:

* a `takeItem` of a **Findings** row really removes it — that is Find-All's
  clear-on-rerun;
* a `takeItem` of a **Messages** row is refused and instead CLOSES the current
  run block, because Messages accumulates by design. The producer's intent ("a
  new run of mine is starting") is honoured; its mechanism (delete the old
  rows) is not.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QListWidgetItem

# --- the prefixes ------------------------------------------------------------
FIND_PREFIX = "[Find]"
BOOKMARK_PREFIX = "[Bookmark]"
VALIDATE_PREFIX = "[Validate]"
LINT_PREFIX = "[Lint]"
CHECK_PREFIX = "[Check]"
SCHEMA_PREFIX = "[Schema]"
PHP_PREFIX = "[PHP]"
SQL_PREFIX = "[SQL]"
#: FQ-033's XML formatter. Its SQL twin's refusals are `[SQL]`, and the two are
#: the same kind of event -- one gesture, two engines -- so this routes to the
#: same place for the same reason: a refusal the user just provoked wants a
#: durable home, and splitting the pair across surfaces would only make the
#: history harder to read.
XML_PREFIX = "[XML]"
PROJECT_PREFIX = "[Project]"
SANDBOX_PREFIX = "[Sandbox]"
#: FQ-260812022749's dual-mode DDL verdict. The message text itself is built
#: (Qt-free) by `db/pg_dump_mode.py::DdlModeVerdict.message`; this constant is
#: the prefix's ONE home, so the producer composes `f"{DDL_PREFIX} {message}"`
#: rather than re-spelling the bracket text.
DDL_PREFIX = "[DDL]"

#: The three destinations, as plain strings so a test can name one.
#: `TO_RESULTS` names the bottom dock's tab, which is titled **Messages** since
#: the FQ-028 title collided with the Sandbox SQL Console's genuine results
#: grid. The identifier keeps its spelling on purpose -- it is referenced by
#: every producer test, and a label is not a schema.
TO_FINDINGS = "findings"
TO_RESULTS = "results"
TO_ACTIVITY = "activity"
#: BUG-042's one dual destination: journalled AND rendered on the Messages tab.
#: Not a fourth surface -- a pairing of two of the three above.
TO_ACTIVITY_AND_RESULTS = "activity+results"

#: Prefix -> destination. `[Schema]` is absent because it is the one prefix
#: whose destination depends on the row (`VERIFY` findings vs learning
#: chatter); `classify` resolves it.
DESTINATIONS = {
    FIND_PREFIX: TO_FINDINGS,
    BOOKMARK_PREFIX: TO_FINDINGS,
    VALIDATE_PREFIX: TO_RESULTS,
    LINT_PREFIX: TO_RESULTS,
    CHECK_PREFIX: TO_RESULTS,
    PHP_PREFIX: TO_ACTIVITY,
    SQL_PREFIX: TO_ACTIVITY,
    XML_PREFIX: TO_ACTIVITY,
    PROJECT_PREFIX: TO_ACTIVITY,
    SANDBOX_PREFIX: TO_RESULTS,
    DDL_PREFIX: TO_RESULTS,
}

#: What marks a `[Schema]` row as a Verify XSD finding rather than learning
#: chatter. `xsd_controller` writes both `"[Schema] VERIFY: …"` headline and
#: `"[Schema] line N: …"` issue rows during a verify run, so the run's own
#: state — not the text — decides the issue rows; see `AuditRouter.schema_run`.
SCHEMA_VERIFY_MARKER = "VERIFY"


def prefix_of(text: str) -> str | None:
    """The bracketed prefix `text` opens with, or None."""
    stripped = str(text).lstrip()
    if not stripped.startswith("["):
        return None
    end = stripped.find("]")
    if end < 0:
        return None
    return stripped[: end + 1]


def classify(
    text: str, *, schema_verify: bool = False, project_closing: bool = False
) -> str:
    """Which surface a row with this text belongs on.

    `schema_verify` says a Verify XSD run is in flight, which is what routes a
    bare `[Schema] line N: …` issue row to Messages rather than to the journal.
    `project_closing` says a project close is in flight, which is what adds the
    Messages tab to a `[Project]` row's journal home (BUG-042; the journal is
    still written -- see `TO_ACTIVITY_AND_RESULTS`).
    An unrecognised or unprefixed row goes to **Messages**: it is the closest
    thing to the old dock (bottom, navigable, kept), so nothing is lost.
    """
    prefix = prefix_of(text)
    if prefix == SCHEMA_PREFIX:
        return TO_RESULTS if schema_verify or SCHEMA_VERIFY_MARKER in text else TO_ACTIVITY
    if prefix == PROJECT_PREFIX and project_closing:
        return TO_ACTIVITY_AND_RESULTS
    return DESTINATIONS.get(prefix, TO_RESULTS)


class AuditRouter:
    """Routes produced Audit rows onto the Findings tab, the Messages tab or the
    Activity Log, and presents the first two as one virtual list.

    `activity_sink` takes `(text, prefix)` and journals it; the host supplies
    one that maps onto `MainWindow.record_activity`.
    """

    def __init__(
        self,
        findings,
        results,
        activity_sink: Callable[[str, str | None], None],
        *,
        on_findings: Callable[[], None] | None = None,
        on_results: Callable[[], None] | None = None,
    ) -> None:
        self.findings = findings
        self.results = results
        self._activity_sink = activity_sink
        self._on_findings = on_findings
        self._on_results = on_results
        #: (panel, item) for every routed CONTENT row, in insertion order.
        self._rows: list[tuple[object, QListWidgetItem]] = []
        #: The findings kind currently on screen (`[Find]` vs `[Bookmark]`);
        #: a different one wipes the tab (last-operation-wins).
        self._findings_kind: str | None = None
        #: The results kind of the last routed row, and whether a run block is
        #: open. Together they decide when a separator is written.
        self._results_kind: str | None = None
        self._results_run_open = False
        #: Set while `xsd_controller` is emitting a Verify XSD run.
        self.schema_run = False
        #: Set while `ddl_project_controller` is narrating a project CLOSE
        #: (BUG-042). Rows produced inside that window are journalled as before
        #: AND rendered on the Messages tab, which the close does not clear.
        self.project_closing = False

    # -- the QListWidget surface the producers were written against ----------
    def addItem(self, item) -> None:
        """Route one row. Accepts a `str` or a `QListWidgetItem`, exactly as
        `QListWidget.addItem` does."""
        if not isinstance(item, QListWidgetItem):
            item = QListWidgetItem(str(item))
        text = item.text()
        destination = classify(
            text,
            schema_verify=self.schema_run,
            project_closing=self.project_closing,
        )
        if destination == TO_ACTIVITY:
            self._activity_sink(text, prefix_of(text))
            return
        if destination == TO_ACTIVITY_AND_RESULTS:
            # The journal write is unchanged -- the line belongs to the closing
            # project's history -- and the Messages row is what makes it
            # readable after the transition wipes the panel (BUG-042).
            self._activity_sink(text, prefix_of(text))
            self._route_results(item, prefix_of(text))
            return
        if destination == TO_FINDINGS:
            self._route_findings(item, prefix_of(text))
            return
        self._route_results(item, prefix_of(text))

    def _route_findings(self, item, prefix) -> None:
        if prefix != self._findings_kind:
            # A different navigable op: the tab shows ONE question's answers.
            self.clear_findings()
            self._findings_kind = prefix
        self.findings.addItem(item)
        self._rows.append((self.findings, item))
        if self._on_findings is not None:
            self._on_findings()

    def _route_results(self, item, prefix) -> None:
        if not self._results_run_open or prefix != self._results_kind:
            self.results.begin_run()
            self._results_run_open = True
        self._results_kind = prefix
        self.results.addItem(item)
        self._rows.append((self.results, item))
        if self._on_results is not None:
            self._on_results()

    def count(self) -> int:
        return len(self._rows)

    def item(self, row: int):
        if 0 <= row < len(self._rows):
            return self._rows[row][1]
        return None

    def takeItem(self, row: int):
        """Remove row `row` — for a Findings row. For a Messages row this
        REFUSES the removal and closes the run block instead (see the module
        docstring)."""
        if not (0 <= row < len(self._rows)):
            return None
        panel, item = self._rows[row]
        if panel is self.results:
            self._results_run_open = False
            return None
        index = panel.row(item)
        taken = panel.takeItem(index) if index >= 0 else None
        del self._rows[row]
        if not any(panel is self.findings for panel, _ in self._rows):
            self._findings_kind = None
        return taken

    def clear(self) -> None:
        """Wipe both surfaces. The Activity Log is a journal and is never
        cleared from here."""
        self.clear_findings()
        self.results.clear()
        self._rows = []
        self._results_kind = None
        self._results_run_open = False

    # -- run control the host uses -------------------------------------------
    def clear_findings(self) -> None:
        """Empty the Findings tab (and drop its rows from the virtual view)."""
        self.findings.clear()
        self._rows = [row for row in self._rows if row[0] is not self.findings]
        self._findings_kind = None

    def begin_results_run(self) -> None:
        """The next Messages row opens a new run block."""
        self._results_run_open = False

    #: An explicit alias: a run that has finished is closed, so the next row —
    #: from whichever producer — starts its own block.
    end_results_run = begin_results_run
