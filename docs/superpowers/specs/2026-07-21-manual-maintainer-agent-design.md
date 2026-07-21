# manual-maintainer Agent — Design

**Date:** 2026-07-21

## Goal

Add a subagent, `.claude/agents/manual-maintainer.md`, that is dispatched right
after `feature-tester` reports green on a finished feature and folds that feature
into the bundled user manual, so the manual is always up to date. When a behavior
changes, a menu point moves, or a shortcut is rebound, the manual reflects it.
Both the manual's **text** (prose) and its **tree** (the left-dock Contents tab)
stay current.

## Background / placement

- The manual already exists as a single bundled Markdown file:
  `pgtp_editor/resources/manual.md` (CONSOLIDATED_SPEC §20).
- The manual **tree** is *not* a separate file. The Contents tab is derived at
  runtime from the Markdown ATX headings by `parse_chapters()` in
  `pgtp_editor/ui/manual_panel.py`, rendered by `ManualContentsPanel` /
  `ManualPanel`. Keeping "tree and text" in sync therefore means editing the
  headings + prose of the one `.md` file while preserving its heading structure
  and the "skip fenced code blocks" heading-parsing assumption.
- Closest structural precedent: the `spec-maintainer` agent, which owns exactly
  one Markdown artifact and folds finished work into it as the single source of
  truth. `manual-maintainer` is a near-twin over a *different* artifact —
  user-facing how-to prose vs. the implementation-level spec.
- Placement-gate verdict: **CREATE** the agent (no agent owns `manual.md` today;
  user-facing prose is a distinct concern), **EXTEND** the existing `manual.md`
  (never introduce a second manual or a separate tree file).

## Ownership boundary

`manual-maintainer` owns **exactly one artifact**: `pgtp_editor/resources/manual.md`.

- It does **not** edit `docs/superpowers/CONSOLIDATED_SPEC.md` (that is
  spec-maintainer's sole artifact) and it does **not** edit code.
- Conversely, spec-maintainer does not edit the manual. The two doc-maintainers'
  ownership stays disjoint: implementation-level truth (spec) vs. end-user
  how-to (manual).

## Trigger (CLAUDE.md policy)

Enforced by a CLAUDE.md policy rule parallel to the existing testing policy —
**not** a harness hook. The contract:

> After `feature-tester` reports green **and** the `docs/TEST_LOG.md` entry is
> written, the main session dispatches `manual-maintainer` with the feature
> name, its spec/plan paths under `docs/superpowers/`, and the changed files.

This ordering guarantees the agent documents only shipped, verified behavior
(mirroring "a feature isn't done until tested"). A feature is not fully complete
until the manual has been updated (or the agent has explicitly reported no
manual change was needed).

## What the agent does each run

1. **Read the manual in full** (`pgtp_editor/resources/manual.md`), plus the
   feature's spec/plan (`docs/superpowers/specs/*.md`,
   `docs/superpowers/plans/*.md`) and the changed implementation files. If the
   dispatch prompt omits any of these, discover them (`git diff --stat`,
   `git log --oneline`, Grep the specs directory) — do not ask questions back.
2. **Locate the affected chapter(s)** and update them:
   - New user-visible behavior → add or edit the relevant prose.
   - **A moved menu point or rebound key → fix every reference**: the menu-path
     mentions scattered through the prose (`View ▸ …`, `Tools ▸ …`, etc.) *and*
     the consolidated `## Keyboard Shortcuts` chapter. Cross-check against
     CONSOLIDATED_SPEC §22 (menu bar) and §23 (shortcuts) as the authoritative
     tables.
   - Changed behavior → rewrite the stale description so the manual never holds
     two contradictory statements.
3. **Add a new chapter** (`##` / `###`) only when the feature is a genuinely new
   user-facing surface. Match the existing chapter granularity and keep the
   user-facing, task-oriented voice — not the dense reproducible spec style.
4. **Verify concrete names against reality** before asserting them: menu paths,
   tab names, shortcuts, action labels, dialog titles. Recalled or spec'd names
   may be stale — Grep/Glob the `pgtp_editor/` package to confirm.
5. **No-op gracefully** for purely internal features with no user-visible
   surface (refactors, engine internals, test-only changes): make no edit and
   report "no manual change needed" rather than inventing content.
6. **Preserve the tree contract**: keep the ATX-heading structure intact (one
   `#` H1 title; `##` chapters; `###` sections nested under a `##`) and never
   emit a `#`-prefixed line inside a fenced code block that is meant as content,
   since `parse_chapters()` skips fences. Do not reorder headings gratuitously —
   the Contents tree and the positional scroll model follow heading order.
7. **Verify its own edits** did not break the Contents tree by running the
   targeted manual tests headless:
   `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_manual*.py -q`
   (a fast parse/heading-consistency check; the full suite was already run by
   feature-tester).
8. **Report back** to the caller: which chapters changed (or that no change was
   needed), any menu/shortcut references it re-synced, the manual-test result,
   and any drift it found between the manual and reality that it could not
   resolve unilaterally.

## Change record

**Git history only.** Each manual update is its own commit; the diff and commit
message are the record. No new log artifact (no `MANUAL_LOG.md`, no in-manual
changelog section) — the manual stays the single source of truth with nothing
shadowing it.

## Agent frontmatter

- `name: manual-maintainer`
- `tools: Read, Grep, Glob, Edit, Write, PowerShell` (PowerShell used only to run
  the targeted manual test)
- `model: inherit` (matches the existing agent family)
- `description:` names the trigger (after feature-tester green), the owned
  artifact (`pgtp_editor/resources/manual.md`), and the "keep tree + text current,
  re-sync moved menus/shortcuts" duty, so it is discoverable and used
  PROACTIVELY at feature completion.

## Deliverables

1. `.claude/agents/manual-maintainer.md` — the new agent.
2. A CLAUDE.md edit adding the manual-maintenance gate immediately after the
   existing testing gate (the manual update is part of feature completion).

## Non-goals

- No harness hook / no automatic enforcement outside the CLAUDE.md policy.
- No second manual document and no separate manual-tree file (the tree is
  derived from headings).
- No separate change-log artifact.
- The agent does not write tests, edit code, or edit the consolidated spec.
- Not multi-language — the manual stays English (per the manual's own design).
