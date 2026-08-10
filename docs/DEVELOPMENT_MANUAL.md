# PGTP Editor — Development Manual

*Everything about how this project gets built: the operational loop (git pull →
open Claude → branch → PR), the agent-driven build model that runs in the middle,
and how pull requests are reviewed and merged by the owner.*

This is the manual for **the way we work** — the human-in-the-loop, agent-driven
development loop. It is not the app's user manual (that's
`pgtp_editor/resources/manual.md`). Read it before you start a session; skim the cheat
sheets whenever you forget who owns what.

- **Repo:** `https://github.com/tyutyuszomoru/pgtp_editor.git`
- **Default branch:** `main`
- **Local path (this machine):** `/home/zrb/Projects/pgtp_editor`

**How to read this doc.** Part I is the mechanics *around* the work — git, Claude Code,
branches, PRs. Part II is the mechanics *of* the work — the orchestrating session and its
subagents. Part I sends you into Part II at step 4 ("do the work") and picks back up at
step 5 ("open the PR").

---

# Part I — The operational loop

## 0. One-time setup (only on a fresh machine)

Skip this section if the repo is already cloned and Claude Code is installed.

```bash
# 1. Clone
git clone https://github.com/tyutyuszomoru/pgtp_editor.git
cd pgtp_editor

# 2. Python environment (Linux: the repo venv carries the test deps)
python -m venv venv
venv/bin/python -m pip install -e .            # editable install of the package
venv/bin/python -m pip install pytest pytest-qt pytest-xdist pytest-timeout

# 3. Sanity check — both should import cleanly
venv/bin/python -c "import pytest, PySide6; print('ok')"
```

> **Platform note.** On Windows it's the reverse: the test deps usually live in the
> **system `python`**, and the repo's `venv\` is a bare leftover. Confirm with the import
> check above before trusting either interpreter. (See CLAUDE.md → *Test environment*.)

Claude Code itself: install the CLI once (`npm i -g @anthropic-ai/claude-code` or your
platform's installer) and authenticate with `claude` the first time.

## 1. Start the day: sync `main`

Always begin from an up-to-date `main`. Never start work on a stale tree.

```bash
cd /home/zrb/Projects/pgtp_editor

git checkout main            # make sure you're on main
git pull origin main         # fast-forward to the latest
git status                   # expect: "working tree clean"
```

If `git status` is **not** clean, stop and deal with it before pulling — commit, stash
(`git stash`), or discard. Pulling onto a dirty tree invites conflicts you don't want
mixed into new work.

> **Watch the shared docs.** The queue files (`docs/BUGFIX_QUEUE.md`,
> `docs/FEATURE_QUEUE.md`, `docs/DECISION_QUEUE.md`) and the spec change often and from
> multiple threads. `git pull` first so you're triaging/resolving against the current
> state, not a version another session already moved past.

## 2. Point Claude at the folder and open Claude Code

Claude Code works from **your current directory** — the folder you `cd` into becomes the
project root it reads, searches, and edits. So "pointing Claude at the folder" is just:

```bash
cd /home/zrb/Projects/pgtp_editor    # the repo root — where CLAUDE.md lives
claude                               # launches the interactive session here
```

Because you launched it from the repo root:

- It automatically loads `CLAUDE.md` (the project's mandatory instructions).
- It can see the whole tree — `pgtp_editor/`, `tests/`, `docs/`, `.claude/agents/`.
- The specialist agents in `.claude/agents/` become available to dispatch.

**Launch from the root, not a subfolder.** If you `cd pgtp_editor/ui && claude`, Claude
starts scoped to `ui/` and won't see `CLAUDE.md`, the agents, or the queues. Always open
it at `/home/zrb/Projects/pgtp_editor`.

Your first message frames the session. Typical openers:

> "Pick up the feature queue." — drains `docs/FEATURE_QUEUE.md`.
> "Here's a bug report: …" — triages it into `docs/BUGFIX_QUEUE.md`.
> "Build feature X." — a normal implementation turn.

## 3. Start a new branch for the work

**Never commit new work directly to `main`.** Every change — feature, bugfix batch, spec
pass — gets its own branch, so `main` stays releasable and each unit of work becomes one
reviewable PR. (Docs-only touch-ups to the queues are the practical exception this repo's
history already makes — small `docs(...)` commits land on `main` directly.)

Cut the branch from a freshly-pulled `main`:

```bash
git checkout main
git pull origin main
git checkout -b <branch-name>
```

### Branch naming

Follow the conventions already in this repo's history — short, kebab-case, describing the
work:

| Kind of work | Pattern | Real examples from this repo |
|--------------|---------|------------------------------|
| A feature | `feature/<slug>` or `<slug>` | `feature/edit-autoxsd-curated-v1.2`, `ddl-editing`, `table-references-tab` |
| A bug or batch of bugs | `bugfix-<ids>` | `bugfix-021-026-027-028` |
| A targeted fix | `fix-<slug>` | `fix-large-file-open` |
| A review/spec sweep | `dev_review_NN` | `dev_review_01` |

Keep one branch to one coherent unit of work. A bug batch can carry several `BUG-NNN`
fixes; a feature branch should carry one feature (plus its tests, spec fold, and manual
update — those ride *with* it, they don't get their own branch).

> **You can let the session do this.** Claude Code will create the branch for you when it
> starts work — its standing rule is *if on the default branch, branch first*. Either way,
> confirm you're **off `main`** before the first code commit (`git branch --show-current`).

## 4. Do the work

The actual build follows the agent loop in **Part II** below — harmonize the spec,
implement, test until green, update the manual, fold back into the spec. Two mechanics to
keep in hand while you're in it:

- **Run targeted tests while iterating**, the full suite only at commit time:
  ```bash
  # while iterating — just the area you touched
  QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/<area> -q

  # at commit time — full suite, in parallel, ~2.5 min
  QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10 | grep -E "passed|failed|^FAILED"
  ```
- **Commits ride together.** A feature's code, its tests, its `TEST_LOG.md` entry, its
  `manual.md` update, and its spec fold go in *one* commit (or one tight series) on the
  branch — not scattered.

Commit messages follow a `type(scope): summary` shape (`docs(DEC-015 answered): …`,
`chore(release): 0.4.0`, `merge(BUG-044): …`). Claude appends its `Co-Authored-By`
trailer automatically. Commit and push only when you ask — the session won't push on its
own.

→ **Go read Part II now if you haven't.** Then come back here for step 5.

## 5. Push the branch and open the PR

When the work is done and the full suite is green:

```bash
git push -u origin <branch-name>
```

Then open the pull request against `main`. The session can do this with the GitHub CLI:

```bash
gh pr create --base main --head <branch-name> \
  --title "type(scope): what this delivers" \
  --body  "Summary, what changed, test result, and any BUG-/FQ-/DEC- ids it closes."
```

A good PR body for this repo states:

- **What** shipped (the feature/bugfix, in one or two lines).
- **Which queue entries it closes** — `BUG-051`, `FQ-026`, etc. — so the owner can flip
  their statuses.
- **Test result** — the full-suite figure (`N passed, M skipped`), matching the
  `TEST_LOG.md` entry.
- **Anything the owner must decide** — but if it's a real design decision, it should
  already be a `DEC-NNN` in the decision queue, not buried in the PR.

Leave the PR at that. **You (the dev session) open it; you do not merge it.**

## 6. How PRs are handled — the owner's side

Merging is the **owner's** job, not the session's. This is the deliberate handoff point:
the dev session proposes; the owner disposes.

1. **Review on GitHub.** Open the PR at
   `https://github.com/tyutyuszomoru/pgtp_editor/pulls`. Read the diff, the PR body's
   claimed test result, and the queue-entry ids it says it closes.

2. **Ask for changes in-thread if needed.** If something's off, request changes on the
   PR. The dev session pushes follow-up commits to the *same branch* — the PR updates
   automatically. Re-review.

3. **Merge when satisfied.** Use GitHub's **Merge pull request** button. This repo's
   history uses merge commits (`Merge pull request #15 from …/dev_review_01`), so a
   standard merge keeps that lineage. Squash is fine for small single-purpose branches if
   you prefer a clean line — your call as owner.

4. **After merge, flip the queue statuses** *in place* (never delete an entry):
   - `docs/BUGFIX_QUEUE.md`: `Status: OPEN` → `RESOLVED (<merge-commit>)`
   - `docs/FEATURE_QUEUE.md`: `Status: QUEUED` → `PROCESSED (<commit or spec §>)`
   - `docs/DECISION_QUEUE.md`: handled by `owner-decision`, not by hand.

   In practice you hand this back to a session — *"PR #16 merged, close out its queue
   entries"* — and it does the flips (through the owning agent where one applies).

5. **Pull `main` locally.** Back in the terminal, `git checkout main && git pull` so your
   local tree includes the merge before you cut the next branch. Delete the merged branch
   if you like: `git branch -d <branch-name>` (local) and
   `git push origin --delete <branch-name>` (remote).

**Why the owner merges and the session doesn't:** a merge to `main` is an outward-facing,
hard-to-reverse action. The session's rule is to *propose* it and let you approve — the
same reason it files owner-only decisions instead of guessing them. You are the gate on
`main`.

## Part I condensed

```
git checkout main && git pull origin main       # 1. sync
cd /home/zrb/Projects/pgtp_editor && claude      # 2. open Claude at the root
git checkout -b feature/<slug>                   # 3. branch off main
  … build via the agent loop (Part II) …         # 4. do the work
QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10   #    green full suite
git push -u origin feature/<slug>                # 5. push
gh pr create --base main …                       #    open PR — do NOT merge
  … owner reviews & merges on GitHub …           # 6. owner's gate
git checkout main && git pull                     # 7. sync, then next branch
```

---

# Part II — The agent-driven build model

## The one idea everything hangs on

**One session drives. Subagents do the specialized work. Documents hold the truth
between them.**

You (the vibe coder) talk to a single **main implementation session**. That session is an
*orchestrator*, not a lone coder. It writes some code directly, but its real job is to
keep the whole machine coherent: pick up work, dispatch the right specialist agent at the
right moment, relay your answers, and make sure nothing ships without its spec, its tests,
and its manual entry caught up.

Everything the agents need to coordinate lives in **files**, not in memory or chat:

| File | Single owner | What it holds |
|------|-------------|---------------|
| `docs/superpowers/CONSOLIDATED_SPEC.md` | `spec-maintainer` | The one authoritative design. |
| `README.md` | `spec-maintainer` | What the project *is*, today and ahead. |
| `pgtp_editor/resources/manual.md` | `manual-maintainer` | The in-app user manual. |
| `docs/TEST_LOG.md` | `feature-tester` | Append-only record of verified test runs. |
| `docs/BUGFIX_QUEUE.md` | `bug-triager` | Root-caused, ready-to-fix bug proposals. |
| `docs/FEATURE_QUEUE.md` | `feature-triage` | Challenged, well-placed feature proposals. |
| `docs/DECISION_QUEUE.md` | `owner-decision` | Decisions only *you* can make. |

The golden rule of the queues: **each file has exactly one writer agent.** The main
session reads all of them, but never hand-edits a file another agent owns. That's what
keeps parallel work from colliding.

## The cast

Seven specialist agents. Learn what each one *owns* and *when it runs* — the rest is
detail.

### spec-maintainer — the single source of truth
- **Owns:** `CONSOLIDATED_SPEC.md` and `README.md`. It is the **only** thing that writes
  design content anywhere.
- **Does two jobs, always in this order:** first it **harmonizes** (surveys the spec
  against shipped code, finds drift, contradictions, and dead assertions), *then* it
  **authors** (folds a settled design or bugfix into the right section, with a Supersession
  Ledger row for anything it overrides).
- **Dispatch it:** (1) at the *start* of any brainstorm, as the placement gate — it says
  whether an idea EXTENDs an existing feature or CREATEs a new one; (2) whenever a design
  or bugfix is settled, to fold it in; (3) after any batch of work lands, to re-align spec
  and code; (4) retroactively, to file features that shipped differently than specified.
- **Load-bearing habit:** the spec must be clean *before* a feature request arrives (so
  nobody designs against ghosts) and clean *before* implementation starts (a contradiction
  in the spec becomes a deep bug in the code). If it finds the *code* is wrong rather than
  the spec, it dispatches `bug-triager` — it never quietly rewrites the requirement to
  match a bug.
- **Never** invent design silently: don't hand-write into the spec, and don't add new
  dated files under `docs/superpowers/specs/` — that folder is frozen history.

### feature-tester — nothing is done without a green run
- **Owns:** `docs/TEST_LOG.md`.
- **Does:** writes unit tests for the finished feature (under `tests/`, mirroring the
  package layout), runs them plus the full suite, iterates until green, and appends the
  verified result to the log.
- **Dispatch it:** *every time* a feature's implementation is finished — before you call
  it done, before you commit it as finished, before you move on. Also mid-feature to get
  early coverage on a completed sub-component.
- **Boundary:** it reports implementation bugs *back to you*; it does not change feature
  behavior to make a test pass. If it's red, you fix the code in the main session and
  re-dispatch until it's green.

### manual-maintainer — the app documents itself
- **Owns:** `pgtp_editor/resources/manual.md`.
- **Dispatch it:** every time a feature is done, **immediately after feature-tester is
  green** and the TEST_LOG entry is written. It folds the shipped behavior into the manual
  — both the prose and the heading structure (the in-app Contents tree is derived from the
  Markdown headings) — and re-syncs every menu path, tab name, and shortcut against real
  code.
- **Boundary:** it no-ops gracefully for purely internal features with no user-visible
  surface — but it must say so explicitly. A feature isn't done until the manual reflects
  it *or* the agent reports no change was needed.

### bug-triager — parallel bug analysis (background)
- **Owns:** `docs/BUGFIX_QUEUE.md`.
- **Dispatch it:** when a bug report lands **while other work is in progress**. Send it
  `run_in_background: true`, one instance per report. It investigates read-only against the
  real code, root-causes the defect, and appends a structured, ready-to-implement proposal
  — it **never** implements the fix or touches source, tests, or specs, so it can't collide
  with whatever the main session is mid-editing.
- **You do not resolve the queue reflexively.** Registering a bug and fixing it are
  separate passes; a resolve pass happens later (often in another thread). Don't offer to
  drain the queue just because it has entries.

### feature-triage — parallel idea capture (foreground)
- **Owns:** `docs/FEATURE_QUEUE.md`.
- **Dispatch it:** when a new feature idea, change request, or improvement surfaces while
  other work is in progress — or as the settled output of a brainstorm. **Foreground, not
  background**: unlike `bug-triager`, it is *expected to push back*. It asks clarifying and
  challenging questions, argues against weak ideas, proposes better alternatives, and
  recommends EXTEND-vs-CREATE placement against the spec. You relay its questions to the
  user and its answers back before it writes the single, elaborated entry.
- **Boundary:** it never folds the idea into the spec or implements it. That's a later
  design-and-build pass.

### owner-decision — the decisions only the owner can make
- **Owns:** `docs/DECISION_QUEUE.md`, as sole writer.
- **Two modes:**
  - **FILE (background):** the moment any session hits a decision it must not make alone —
    a trade-off with no obviously right answer, a ruling that would reverse recorded
    design, or a question whose wrong answer is expensive — dispatch it in the background
    to record the decision with full context. Then **carry on with everything that
    decision doesn't block.** Filing is never a reason to stop.
  - **ASK (foreground):** in a session dedicated to decisions, dispatch it in the
    foreground. It sweeps the queue, retires entries already overtaken by shipped code,
    puts the live ones as self-contained questions, and writes your answers back **with
    your reasoning** — because an answer without its *why* just gets re-litigated later.
- **Don't file trivia:** anything the code can answer (go read it), anything the spec
  already settles, or a choice with an obviously right answer. Make those and say you did.
  Filing trivia trains the owner to skim the queue, which recreates the whole problem.

### The generic helpers
`Explore` and `Plan` (read-only search and architecture planning), `general-purpose`, and
others exist too — but the seven above carry the workflow. Reach for the specialists first.

## The main session as orchestrator

A normal "build me this feature" turn runs roughly like this:

1. **Harmonize first.** Dispatch `spec-maintainer` so the spec is clean before you design
   against it. It reconciles spec vs. code and, if reconciliation changed what should be
   built, *restates the feature for implementation* — that restatement supersedes the queue
   entry.
2. **Implement.** Write the code. Run **targeted** tests for the area you touched as you go
   — not the full suite every time.
3. **Test.** Dispatch `feature-tester`. If red, fix in the main session and re-dispatch
   until green. It writes the TEST_LOG entry.
4. **Manual.** Dispatch `manual-maintainer` to fold the feature into `manual.md` (or report
   no change needed).
5. **Re-harmonize + fold.** Dispatch `spec-maintainer` again to fold the shipped design
   into the spec and revisit the README in the same pass.
6. **Commit.** The spec, test-log, and manual changes ride *with* the feature in one
   commit. The full suite runs once, at commit time — in parallel (`-n 10`), never piped
   through `tail` (it eats the failing test's name).

The main session holds the thread; the agents each guarantee one invariant (spec is right,
tests are green, manual is current). You don't have to remember the invariants — you have
to remember to *dispatch the agent that enforces each one.*

### When you have work in flight and something new arrives

This is the whole reason the triage agents exist. New input shouldn't derail the code
you're mid-editing, and it shouldn't collide with it on disk either. So it gets parked in a
queue by an agent that only writes to that queue:

- **A bug report arrives** → `bug-triager`, **background**, one per report. Keep coding.
- **A feature idea arrives** → `feature-triage`, **foreground** (it needs to interrogate
  the idea with you). Then keep coding.
- **You hit a decision that's the owner's to make** → `owner-decision`, **background** to
  file it. Then continue on everything it doesn't block.

Later, in a dedicated pass, you *drain* a queue: read it, do the design-and-build (or
answer, for decisions), and **flip the entry's status in place** — never delete it. The
entries are the record of what was reported/proposed/decided and *why the resolution was
shaped that way.*

## How to feed the queues (the part you'll do most)

### Adding a bug report
> "Here's a bug: opening the XSD editor leaves a tab you can't close."

The main session dispatches `bug-triager` in the background. It investigates read-only,
finds the root cause (down to file and line), and appends a `BUG-<YYMMDDHHMMSS>` entry with
`Status: OPEN`. You are **not** blocked and the resolve happens on a separate pass — often
another thread entirely. Don't ask to fix it right now unless you mean to open the whole
resolve workflow.

**Bug ids are timestamps, not sequential.** The id is a `date +%y%m%d%H%M%S` snapshot
taken at the moment of filing — e.g. `BUG-260810143025` — never a running counter. This is
deliberate: two people can triage bugs on two machines at once and their entries never
collide on the same number, so git merges the two appends cleanly in either direction with
no renumbering. (The legacy `BUG-001`…`BUG-064` predate this rule and stay exactly as they
are — never renumber an existing entry.) Feature-queue ids (`FQ-NNN`) and decision ids
(`DEC-NNN`) remain sequential for now; only the bug queue is timestamp-keyed.

**Status lifecycle:** `OPEN` → `RESOLVED (<commit>)`, flipped in place by whoever does the
resolve pass.

### Adding a feature request
> "I want a Test button for *both* connections in Project Settings."

The main session dispatches `feature-triage` in the **foreground**. Expect it to talk back
— "which connection failure state should the button surface?", "should this EXTEND the
existing Connections tab spec (§18.2) rather than be a new feature?" Answer its questions;
it writes one `FQ-NNN` entry with `Status: QUEUED`.

**Status lifecycle:** `QUEUED` → (drain pass: `spec-maintainer` folds it, you build it) →
`PROCESSED (<commit or spec §>)`.

### Filing a decision
When you're mid-build and hit *"should undo cross document boundaries or not?"* — a real
design fork — you don't guess and you don't stall. `owner-decision` files it in the
background; you continue on everything that fork doesn't block. In a later
decisions-only session, `owner-decision` puts it to the owner and records the answer **with
its reasoning**.

**Status lifecycle:** `OPEN` → `ANSWERED (<date>)` / `CLOSED — <reason>` /
`SUPERSEDED BY DEC-NNN`. If an answer implies surface that doesn't exist yet, it doesn't go
straight to code — it's routed through `feature-triage` to be placed and queued.

## Rules that keep the machine honest

- **One writer per file.** Never hand-edit a queue or spec another agent owns. Route the
  change through that agent.
- **The spec is the final truth, so it carries the obligation to be right.** Code and spec
  are never left diverged. Stale spec → `spec-maintainer` fixes it. Wrong code →
  `spec-maintainer` files a bug; it does not rewrite the requirement to match the bug.
- **Harmonize before you build, fold after you ship.** A contradiction in the spec becomes
  a deep problem in the code.
- **A feature isn't done** until: feature-tester is green *and* logged, manual-maintainer
  has updated the manual (or explicitly no-op'd), and spec-maintainer has folded it in. All
  three ride in the feature's commit.
- **Triage parks, it never builds.** `bug-triager` / `feature-triage` / `owner-decision`
  only write their own queue. Building and folding happen on a separate, deliberate pass.
- **Filing a decision is not stopping.** Continue on everything the decision doesn't block.
- **Never bury a decision inside an implementation report** — it gets missed, and the
  assumption hardens silently. It goes through `owner-decision` or it doesn't exist.

## Part II cheat sheet

| When… | Dispatch | Mode | It writes |
|-------|----------|------|-----------|
| Starting a brainstorm / design | `spec-maintainer` (placement gate) | fg | *(reports placement)* |
| Design or bugfix is settled | `spec-maintainer` (harmonize → fold) | fg | spec, README |
| Feature implementation finished | `feature-tester` | fg | TEST_LOG.md |
| …and it's green | `manual-maintainer` | fg | manual.md |
| Bug report arrives mid-work | `bug-triager` (one per report) | **bg** | BUGFIX_QUEUE.md |
| Feature idea arrives mid-work | `feature-triage` | **fg** | FEATURE_QUEUE.md |
| Hit an owner-only decision | `owner-decision` (FILE) | **bg** | DECISION_QUEUE.md |
| Dedicated decisions session | `owner-decision` (ASK) | fg | DECISION_QUEUE.md |

**Queue statuses:** BUG `OPEN → RESOLVED (<commit>)` · FQ `QUEUED → PROCESSED (<commit/§>)`
· DEC `OPEN → ANSWERED/CLOSED/SUPERSEDED`. Flip in place, never delete.

**Tests (Linux):** `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/<area> -q`
while iterating; full suite `-n 10` once at commit time. Filter output with
`grep -E "passed|failed|^FAILED"` — never `tail`.
