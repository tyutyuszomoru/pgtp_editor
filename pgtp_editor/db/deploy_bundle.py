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

# pgtp_editor/db/deploy_bundle.py
"""The deploy bundle's *decision layer* (§18.3 steps 1–4) — which objects are
candidates, whether the batch is blocked, and in what order the approved
statements stand.

Pure: no Qt, no psycopg, no I/O, no clock, no git, no SQL execution. Given the
`*`/`!` drift state `ddl_project.compute_drift_markers` already computed, this
module answers three questions and nothing else:

1. **Candidates** — the `*`-flagged objects (local `ddl/` file differs from the
   last-deployed reference). §18.3 step 1.
2. **Blockers** — the candidates that are *also* `!`-flagged (the live DB drifted
   from that same reference independently). §18.3 step 2: any such object refuses
   the **whole** batch, naming **every** blocker, recovery = resolve then re-run.
   This is deliberately the same ambiguity-gate/all-or-nothing discipline §12's
   Diff/Merge Apply gate already uses (`main_window._apply_changes_to_target`:
   collect *all* ambiguous items, refuse before mutating anything, tell the user
   to resolve and re-run) — not new machinery, and not a partial deploy that
   silently drops the blocked half.
3. **Order** — an approved `DeployBundle` carries its entries as ordered data the
   UI can permute (§18.3 step 3: *statement order is adjustable, content is
   not*). There is no API here that edits a statement's SQL; editing happens
   only in the single-object editor tabs (§18.5).

Blocked-with-blockers is an **expected** outcome the UI renders, not an
exception: `assemble_deploy_bundle` always returns a `DeployPlan`, and a blocked
plan simply exposes no bundle (`plan.bundle is None`) — there is nothing
deployable to hand onward. Exceptions here are reserved for genuine misuse
(a candidate with no SQL supplied, a reorder that is not a permutation).

**Not this module's job, on purpose:** nothing here executes SQL against any
database (§18.3's never-auto-execute rule) and nothing here touches git — §18.3
step 4(a) is an explicit undesigned placeholder, so it appears below only as
`git_commit_placeholder`, a documented no-op seam. What this module produces is
reviewed *data*.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .ddl_project import DriftMarkers


class DeployBundleError(Exception):
    """Base for every refusal in this module -- never raised directly.

    Note the division of labour: a *blocked batch* is not one of these. It is a
    `DeployPlan` the caller renders (§18.3's gate), the same way a Diff/Merge
    ambiguity refusal is a message rather than a crash. These exceptions signal
    that the caller called wrong.
    """


class MissingCandidateSql(DeployBundleError):
    """A `*`-flagged candidate was handed to `assemble_deploy_bundle` with no SQL.

    Refused rather than skipped: a bundle that quietly omits one of the objects
    the user is deploying is precisely the silent-wrong-result class this project
    refuses (same posture as `migration_gen.UnsupportedDifference`).
    """


@dataclass(frozen=True)
class DeployCandidate:
    """One `*`-flagged object's place in the bundle.

    `relpath` is the `ddl/*.sql` project-relative path that is the object's
    identity everywhere in §18.2 (`ProjectSettings.deployed`'s key, and
    `compute_drift_markers`' key). `sql` is the statement text as the caller
    read it -- this module never rewrites it, and nothing in the bundle API
    lets the review UI edit it (§18.3 step 3).
    """

    relpath: str
    sql: str


@dataclass(frozen=True)
class DeployBlocker:
    """One `!`-flagged candidate: the live DB moved under a pending local edit.

    `marker_text` is §18.2's rendered marker for the object (`"*!"` for every
    blocker this module produces, since a blocker is by definition a candidate
    that is also live-drifted), carried so the refusal the user reads speaks the
    same `*`/`!` vocabulary as the `BrowserPanel` tree it came from.
    """

    relpath: str
    marker_text: str


@dataclass(frozen=True)
class DeployBundle:
    """The approved batch: ordered entries, immutable content (§18.3 step 3).

    Order is data -- `reordered` returns a new bundle with the same entries in
    the caller's order. Content is not: there is deliberately no `set_sql`, no
    mutable entry list, and no way to add or drop an entry, because the bundle
    review surface is explicitly not an editor.
    """

    entries: tuple[DeployCandidate, ...] = ()

    @property
    def relpaths(self) -> tuple[str, ...]:
        """The entries' identities, in current statement order."""
        return tuple(entry.relpath for entry in self.entries)

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to deploy (no `*`-flagged object)."""
        return not self.entries

    def reordered(self, order: Sequence[str]) -> DeployBundle:
        """A new bundle with the same entries arranged in `order`.

        `order` must be an exact permutation of `relpaths` -- a missing,
        unknown or duplicated path raises `ValueError`. Reordering is the one
        adjustment §18.3 grants the review surface, so it may not become a
        back door for dropping a statement out of the batch (all-or-nothing)
        or for smuggling a new one in.
        """
        current = self.relpaths
        if sorted(order) != sorted(current):
            raise ValueError(
                "reordered() takes an exact permutation of the bundle's statements; "
                f"got {list(order)!r} for {list(current)!r} -- entries can be "
                "reordered but never added, dropped or duplicated"
            )
        by_path = {entry.relpath: entry for entry in self.entries}
        return DeployBundle(entries=tuple(by_path[relpath] for relpath in order))

    def sql_text(self) -> str:
        """The bundle rendered as one reviewable script, in current order.

        Read-only output for display/save. Nothing here executes it (§18.3's
        never-auto-execute non-goal); statements are `;`-terminated and
        blank-line separated so the text pastes into `psql` unedited, matching
        `migration_gen.generate_migration`'s shape.
        """
        blocks = []
        for entry in self.entries:
            body = entry.sql.strip()
            blocks.append(body if body.endswith(";") else f"{body};")
        return "\n\n".join(blocks) + ("\n" if blocks else "")


@dataclass(frozen=True)
class DeployPlan:
    """The whole answer for one deploy attempt: candidates, blockers, bundle.

    Three outcomes, all distinguishable without catching anything:

    - **blocked** -- `blockers` is non-empty and `bundle is None`. There is no
      deployable artifact at all; the caller renders `refusal_message`.
    - **nothing to deploy** -- `candidates` is empty, `bundle.is_empty` is True.
      Not the same state as blocked, and deliberately not conflated with it.
    - **approved** -- `bundle` carries the ordered entries.
    """

    candidates: tuple[str, ...] = ()
    blockers: tuple[DeployBlocker, ...] = ()
    bundle: DeployBundle | None = field(default=None)

    @property
    def blocked(self) -> bool:
        """True when at least one candidate is `!`-flagged (§18.3 step 2)."""
        return bool(self.blockers)

    @property
    def blocker_paths(self) -> tuple[str, ...]:
        """Every blocker's identity -- all of them, never just the first."""
        return tuple(blocker.relpath for blocker in self.blockers)

    @property
    def refusal_message(self) -> str:
        """The gate's refusal text, naming **every** blocker plus the recovery.

        Mirrors §12's Diff/Merge ambiguity refusal
        (`main_window._apply_changes_to_target`): a `- <identity> (<detail>)`
        line per blocker, then the resolve-and-re-run instruction. Empty string
        when the plan is not blocked -- there is nothing to refuse.
        """
        if not self.blockers:
            return ""
        details = "\n".join(
            f"- {blocker.relpath} ({blocker.marker_text})" for blocker in self.blockers
        )
        return (
            f"{len(self.blockers)} of {len(self.candidates)} objects in this deploy "
            "batch have drifted in the live database since they were last deployed "
            "(`!`), so deploying would overwrite a change made independently there. "
            "The entire batch is refused -- nothing was deployed. Resolve the "
            "objects below (reconcile the live definition with your local edit) and "
            "re-run Deploy:\n\n" + details
        )


def deploy_candidates(markers: Mapping[str, DriftMarkers]) -> tuple[str, ...]:
    """The `*`-flagged objects in `markers` -- §18.3 step 1's candidate set.

    `markers` is `compute_drift_markers`' output as-is: `ddl/*.sql` relpath ->
    `DriftMarkers(locally_edited, live_drifted)`. Objects absent from it (never
    deployed, so nothing to compare against) are not candidates -- that absence
    is §18.2's "no last-deployed reference," not "unchanged," and this module
    does not reinterpret it.

    Ordered alphabetically by relpath: deterministic and stable, which is what
    makes the review surface reproducible. Dependency ordering (routines before
    the triggers referencing them, as `migration_gen` ranks it for the
    schema-compare entry point) is not derivable from a path alone -- that is
    exactly what §18.3 step 3's adjustable order is for.
    """
    return tuple(
        sorted(relpath for relpath, marker in markers.items() if marker.locally_edited)
    )


def deploy_blockers(markers: Mapping[str, DriftMarkers]) -> tuple[DeployBlocker, ...]:
    """Every `*!` object in `markers` -- the batch's blockers (§18.3 step 2).

    A blocker is a *candidate* that is also live-drifted. An object that is
    `!`-only (live DB moved, no pending local edit -- the ordinary aftermath of
    §18.2's single-object Apply) is **not** a blocker: it is not part of the
    batch, nothing would be written over it, and blocking every deploy on it
    would make the gate un-actionable. Sorted by relpath so the refusal reads
    in a stable order.
    """
    candidates = set(deploy_candidates(markers))
    return tuple(
        DeployBlocker(relpath=relpath, marker_text=markers[relpath].marker_text)
        for relpath in sorted(candidates)
        if markers[relpath].live_drifted
    )


def assemble_deploy_bundle(
    markers: Mapping[str, DriftMarkers], sql_by_path: Mapping[str, str]
) -> DeployPlan:
    """Decide one deploy attempt: §18.3 steps 1–3, all-or-nothing.

    `markers` is `compute_drift_markers`' output; `sql_by_path` supplies each
    candidate's statement text (the caller owns reading the `ddl/` files or
    generating the statement -- this module does no I/O). Extra entries in
    `sql_by_path` for non-candidates are ignored; a candidate with no entry is
    refused with `MissingCandidateSql` rather than silently dropped.

    The gate runs **before** any bundle is built, exactly as
    `migration_gen._reject_unsupported` checks up front: if any candidate is
    `!`-flagged the returned plan carries every blocker and `bundle is None`,
    so a blocked batch has no deployable artifact to hand on by accident. A
    clean batch -- including a clean *empty* batch -- returns a bundle.
    """
    candidates = deploy_candidates(markers)
    blockers = deploy_blockers(markers)
    if blockers:
        return DeployPlan(candidates=candidates, blockers=blockers, bundle=None)

    missing = [relpath for relpath in candidates if relpath not in sql_by_path]
    if missing:
        raise MissingCandidateSql(
            "no SQL was supplied for deploy candidate(s): "
            + ", ".join(missing)
            + "; refusing to assemble a bundle that omits an object the user is "
            "deploying"
        )

    bundle = DeployBundle(
        entries=tuple(
            DeployCandidate(relpath=relpath, sql=sql_by_path[relpath])
            for relpath in candidates
        )
    )
    return DeployPlan(candidates=candidates, blockers=(), bundle=bundle)


def git_commit_placeholder(bundle: DeployBundle) -> None:
    """§18.3 step 4(a)'s git commit/push -- an explicit no-op seam, by design.

    The spec calls the git step an *undesigned placeholder, mechanism TBD*
    (§18.2's `GitConfig` records the same captured-intent-only stance), so this
    deliberately does nothing rather than guessing at a mechanism: no
    subprocess, no repository assumptions, no commit id written back. It exists
    only so the call site that will eventually own versioning has one obvious
    place to land, and so no reader mistakes its absence for an oversight.
    """
    return None
