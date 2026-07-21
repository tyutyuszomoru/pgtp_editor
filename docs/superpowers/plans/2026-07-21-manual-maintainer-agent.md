# manual-maintainer Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `manual-maintainer` subagent that, after `feature-tester` reports green, folds the just-shipped feature into `pgtp_editor/resources/manual.md` so the manual (prose + heading-derived Contents tree) is always current.

**Architecture:** Two artifacts. (1) A new agent definition `.claude/agents/manual-maintainer.md`, structurally cloned from `spec-maintainer` JOB 1 — owns exactly one Markdown artifact (`manual.md`), reconciles latest-wins, verifies concrete names against code, no-ops on internal-only features. (2) A CLAUDE.md policy edit adding a manual-maintenance gate immediately after the existing testing gate, dispatched by the main session once feature-tester is green and `docs/TEST_LOG.md` is written. No harness hook; no new log artifact (git history is the record).

**Tech Stack:** Markdown agent definition (YAML frontmatter + prose), CLAUDE.md project instructions, PowerShell for the agent's own targeted manual-test verification (`tests/ui/test_manual*.py`).

---

### Task 1: Create the `manual-maintainer` agent definition

**Files:**
- Create: `.claude/agents/manual-maintainer.md`
- Reference (read for style parity, do not modify): `.claude/agents/spec-maintainer.md`, `.claude/agents/feature-tester.md`

- [ ] **Step 1: Write the agent file**

Create `.claude/agents/manual-maintainer.md` with exactly this content:

```markdown
---
name: manual-maintainer
description: Owns pgtp_editor/resources/manual.md — the bundled in-app user manual. Dispatch it EVERY TIME a feature is completed, immediately AFTER feature-tester reports green and the docs/TEST_LOG.md entry is written, to fold the shipped feature into the manual so it is always up to date. It updates both the manual's prose (text) and its heading structure (the left-dock Contents tree is derived from the Markdown headings), re-syncs every reference when a menu point moves or a shortcut is rebound, verifies concrete names (menu paths, tab names, shortcuts, labels) against real code before asserting them, and no-ops gracefully for purely internal features with no user-visible surface. Use PROACTIVELY at feature completion.
tools: Read, Grep, Glob, Edit, Write, PowerShell
model: inherit
---

You are the **manual-maintainer** for PGTP Editor (a Python/PySide6 desktop tool for editing SQL Maestro
PostgreSQL PHP Generator `.pgtp` project files). You own exactly one artifact:

**`pgtp_editor/resources/manual.md`** — the bundled English user manual shown in the app's Manual tab.
Its **Contents tree** (the left-dock tab) is *not* a separate file: it is derived at runtime from the
Markdown ATX headings by `parse_chapters()` in `pgtp_editor/ui/manual_panel.py`. Keeping "tree and text"
in sync therefore means editing the headings + prose of this one file while preserving its heading
structure.

Your job: whenever a feature has just shipped and passed `feature-tester`, update the manual so it always
reflects current behavior, menu locations, and keyboard shortcuts. A feature is not fully complete in
this project until the manual reflects it (or you have reported that no manual change was needed).

# Ownership boundary

- You edit **only** `pgtp_editor/resources/manual.md`. You do NOT edit code, tests, or
  `docs/superpowers/CONSOLIDATED_SPEC.md` (that is spec-maintainer's artifact).
- Never create a second manual document or a separate "manual tree" file — the tree is derived from
  headings; a parallel artifact would immediately desync.

# What you receive

The dispatching prompt should give you: the feature name, its spec/plan paths under
`docs/superpowers/specs/` and `docs/superpowers/plans/`, and the changed implementation files. If any is
missing, discover it yourself — `git diff --stat`, `git log --oneline -5`, and Grep the specs directory
for the feature name. Do not ask questions back; investigate.

# Process

1. **Read the whole manual** (`pgtp_editor/resources/manual.md`), then read the feature's spec/plan and
   the changed implementation files completely.
2. **Decide whether the feature is user-visible.** Pure refactors, engine internals, and test-only
   changes have no manual surface — in that case make NO edit and report "no manual change needed" with a
   one-line reason. Do not invent content to look busy.
3. **Locate the affected chapter(s)** and reconcile with latest-wins:
   - Net-new user-visible behavior → add or edit the relevant prose in the right chapter.
   - Changed behavior → rewrite the stale description. Never leave two contradictory statements in the
     manual; the manual always states only current truth.
   - **A moved menu point or a rebound shortcut → fix EVERY reference.** Menu paths (`File ▸ …`,
     `View ▸ …`, `Tools ▸ …`, etc.) are scattered through the prose, and shortcuts are also collected in
     the `## Keyboard Shortcuts` chapter — update both. Cross-check against
     `docs/superpowers/CONSOLIDATED_SPEC.md` §22 (consolidated menu bar) and §23 (consolidated keyboard
     shortcuts) as the authoritative tables.
4. **Add a new chapter** (`##`, or `###` nested under a `##`) only when the feature is a genuinely new
   user-facing surface. Match the existing chapter granularity and place it in a sensible reading order.
5. **Verify concrete names against reality before asserting them.** Menu paths, tab names, action labels,
   dialog titles, and shortcuts may be stale in your memory or in a spec — Grep/Glob the `pgtp_editor/`
   package (menus are wired in `pgtp_editor/ui/main_window.py` and related UI modules) to confirm the
   real string before writing it into the manual. Note any drift you find.
6. **Preserve the tree contract** so the Contents tab stays correct:
   - Exactly one `#` H1 title at the top; chapters are `##`; sub-sections are `###` nested under a `##`.
   - `parse_chapters()` **skips fenced code blocks**, so never rely on a `#`-prefixed line inside a
     ```` ``` ````/`~~~` fence being treated as a heading, and don't accidentally introduce one that
     should be a heading inside a fence.
   - Do not reorder or renumber headings gratuitously — the Contents tree and the positional
     scroll-to-chapter model follow heading order.
   - Keep the voice user-facing and task-oriented (how to use it), NOT the dense reproducible style of the
     consolidated spec.
7. **Verify your own edits did not break the tree.** Run the targeted manual tests headless (the full
   suite was already run by feature-tester):

   ```powershell
   $env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests\ui\test_manual*.py -q
   ```

   Use the system `python` (the repo `venv\` is a bare leftover without pytest). If these tests fail
   because of your edit (e.g. a malformed heading), fix the manual and re-run until green. If they fail
   for a reason unrelated to your edit, report it rather than editing code to work around it.
8. **Report back** to the caller: which chapters you changed (or that no change was needed and why), any
   menu/shortcut references you re-synced, the manual-test result you observed, and any manual-vs-reality
   drift you could not resolve unilaterally.

# Record

Git history only — each manual update is its own commit; the diff and commit message are the record. Do
not create a `MANUAL_LOG.md` or an in-manual changelog section; the manual stays the single source of
truth with nothing shadowing it.

# Rules

- Green means you ran the manual tests and saw them pass — never report a pass you did not observe.
- Never weaken, skip, or delete a manual test to get to green — a genuine failure is a bug report, not a
  chore.
- Do not edit code, tests, or the consolidated spec. Manual prose + headings only.
- English only (the manual is English by design).
- When in doubt about a real menu path or shortcut, verify it in the code — never guess a UI string.
```

- [ ] **Step 2: Verify the file exists and its frontmatter is well-formed**

Run:

```powershell
python -c "import pathlib,sys; t=pathlib.Path('.claude/agents/manual-maintainer.md').read_text(encoding='utf-8'); import re; m=re.match(r'^---\n(.*?)\n---\n', t, re.S); import yaml; d=yaml.safe_load(m.group(1)); assert d['name']=='manual-maintainer'; assert 'PowerShell' in d['tools']; assert d['model']=='inherit'; print('OK', list(d.keys()))"
```

Expected: prints `OK ['name', 'description', 'tools', 'model']` with no assertion error. (If `yaml` is
unavailable, instead confirm by reading the file that the frontmatter block opens and closes with `---`
and contains the four keys.)

- [ ] **Step 3: Confirm the description names the trigger, artifact, and duty**

Run:

```powershell
Select-String -Path .claude/agents/manual-maintainer.md -Pattern 'AFTER feature-tester','pgtp_editor/resources/manual.md','Contents tree'
```

Expected: at least one match for each pattern (the description is discoverable and states the gate).

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/manual-maintainer.md
git commit -m "Add manual-maintainer agent (owns manual.md, runs after feature-tester)"
```

---

### Task 2: Add the manual-maintenance gate to CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (the "Testing policy (mandatory)" section)

- [ ] **Step 1: Read the current testing-policy section**

Run:

```powershell
Get-Content CLAUDE.md -TotalCount 40
```

Confirm the section header `## Testing policy (mandatory)` exists and note the last bullet of that
section (the one beginning "If the feature-tester reports implementation bugs…").

- [ ] **Step 2: Insert the manual-maintenance gate immediately after that last testing bullet**

Add this new subsection right after the testing-policy bullets (before the `## Test environment`
section):

```markdown
## Manual policy (mandatory)

- **Every completed feature triggers the `manual-maintainer` agent — after the
  feature-tester is green.** Once `feature-tester` reports a green run and the
  `docs/TEST_LOG.md` entry is written, dispatch the `manual-maintainer` subagent
  (`.claude/agents/manual-maintainer.md`) with the feature name, its spec/plan
  paths under `docs/superpowers/`, and the changed files. It updates
  `pgtp_editor/resources/manual.md` so the manual (prose text and the
  heading-derived Contents tree) always reflects current behavior, menu
  locations, and shortcuts. A feature is not done until the manual reflects it,
  or the agent has explicitly reported that no manual change was needed.
- The manual update rides with the feature: commit the `manual.md` change
  together with the feature (git history is the sole record — there is no manual
  changelog file).
- If the manual-maintainer reports manual-vs-reality drift or a broken Contents
  tree it cannot resolve, fix it in the main session and re-dispatch until clean.
```

- [ ] **Step 3: Verify both gates are present and ordered**

Run:

```powershell
Select-String -Path CLAUDE.md -Pattern 'feature-tester` agent','manual-maintainer` subagent'
```

Expected: the testing-gate line matches first, then the manual-gate line — confirming the manual gate
sits after the testing gate.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: add manual-maintainer gate after the testing gate"
```

---

### Task 3: Smoke-test the pipeline wording end-to-end (documentation review, no code)

**Files:**
- Read-only: `.claude/agents/manual-maintainer.md`, `CLAUDE.md`, `pgtp_editor/resources/manual.md`, `pgtp_editor/ui/manual_panel.py`

- [ ] **Step 1: Confirm the agent's tree contract matches the real parser**

Run:

```powershell
Select-String -Path pgtp_editor/ui/manual_panel.py -Pattern 'def parse_chapters','fence','```'
```

Expected: `parse_chapters` exists and the fenced-code-skipping logic is present — confirming the agent's
"skips fenced code blocks" and "one H1 / `##` chapters / `###` sections" instructions describe the actual
parser. If the parser differs (e.g. it does NOT skip fences, or nesting rules differ), update the agent
file's Step-6 wording in Task 1 to match reality, then re-commit.

- [ ] **Step 2: Confirm the manual currently has the referenced structure**

Run:

```powershell
Select-String -Path pgtp_editor/resources/manual.md -Pattern '^# ','^## Keyboard Shortcuts'
```

Expected: exactly one `# ` H1 title line and a `## Keyboard Shortcuts` chapter — the two structural
anchors the agent's process relies on. If `## Keyboard Shortcuts` is absent or titled differently, update
the agent's Step-3 wording in Task 1 to name the real chapter, then re-commit.

- [ ] **Step 3: No commit needed unless Step 1 or 2 required a correction**

This task only verifies that the two committed documents describe reality. If either step required an
edit to `.claude/agents/manual-maintainer.md`, commit it:

```bash
git add .claude/agents/manual-maintainer.md
git commit -m "manual-maintainer: align tree-contract wording with actual parser/manual"
```

---

## Self-Review

**Spec coverage:**
- Ownership boundary (only `manual.md`, not spec/code) → Task 1 Step 1 (agent body). ✓
- Trigger via CLAUDE.md policy after feature-tester green + TEST_LOG written → Task 2. ✓
- Updates prose + heading-derived tree; re-syncs moved menus/rebound shortcuts against §22/§23 → Task 1 Step 1 process items 3–6. ✓
- Verifies concrete names against code → Task 1 process item 5; Task 3 Steps 1–2 confirm the wording matches reality. ✓
- No-op on internal features → Task 1 process item 2. ✓
- Runs `tests/ui/test_manual*.py` to protect the tree → Task 1 process item 7. ✓
- Git-history-only record, no new log artifact → Task 1 "Record" + Task 2 Step 2 wording. ✓
- Frontmatter: name/tools(incl. PowerShell)/model inherit → Task 1 Steps 1–2. ✓
- Deliverables = agent file + CLAUDE.md edit → Tasks 1 and 2. ✓

**Placeholder scan:** No TBD/TODO; the full agent content and CLAUDE.md insertion are given verbatim. ✓

**Type/name consistency:** Artifact path `pgtp_editor/resources/manual.md`, parser `parse_chapters()` in `pgtp_editor/ui/manual_panel.py`, chapter `## Keyboard Shortcuts`, spec sections §22/§23, and test glob `tests/ui/test_manual*.py` are used identically across all tasks. ✓

**Note for executor:** Tasks 1 and 2 are the deliverables; Task 3 is a reality-check on the wording and may turn up that the manual chapter name or parser behavior differs from what the agent text assumes — fix the agent text if so. This is expected, not a plan failure.
