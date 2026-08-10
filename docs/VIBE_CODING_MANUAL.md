# The Vibe Coder's Manual

*How PGTP Editor gets built: one orchestrating session, a cast of subagents, and a
handful of queue files that hold the shared state between them.*

This is not a manual for the app (that's `pgtp_editor/resources/manual.md`). This is
the manual for **the way we work** — the human-in-the-loop, agent-driven development
loop. Read it before you start a session, and skim the cheat sheet at the bottom
whenever you forget who owns what.

---

## 1. The one idea everything hangs on

**One session drives. Subagents do the specialized work. Documents hold the truth
between them.**

You (the vibe coder) talk to a single **main implementation session**. That session
is an *orchestrator*, not a lone coder. It writes some code directly, but its real job
is to keep the whole machine coherent: pick up work, dispatch the right specialist
agent at the right moment, relay your answers, and make sure nothing ships without its
spec, its tests, and its manual entry caught up.

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

---

## 2. The cast

Seven specialist agents. Learn what each one *owns* and *when it runs* — the rest is
detail.

### spec-maintainer — the single source of truth
- **Owns:** `CONSOLIDATED_SPEC.md` and `README.md`. It is the **only** thing that
  writes design content anywhere.
- **Does two jobs, always in this order:** first it **harmonizes** (surveys the spec
  against shipped code, finds drift, contradictions, and dead assertions), *then* it
  **authors** (folds a settled design or bugfix into the right section, with a
  Supersession Ledger row for anything it overrides).
- **Dispatch it:** (1) at the *start* of any brainstorm, as the placement gate — it
  says whether an idea EXTENDs an existing feature or CREATEs a new one; (2) whenever a
  design or bugfix is settled, to fold it in; (3) after any batch of work lands, to
  re-align spec and code; (4) retroactively, to file features that shipped differently
  than specified.
- **Load-bearing habit:** the spec must be clean *before* a feature request arrives (so
  nobody designs against ghosts) and clean *before* implementation starts (because a
  contradiction in the spec becomes a deep bug in the code). If it finds the *code* is
  wrong rather than the spec, it dispatches `bug-triager` — it never quietly rewrites
  the requirement to match a bug.
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
  green** and the TEST_LOG entry is written. It folds the shipped behavior into the
  manual — both the prose and the heading structure (the in-app Contents tree is derived
  from the Markdown headings) — and re-syncs every menu path, tab name, and shortcut
  against real code.
- **Boundary:** it no-ops gracefully for purely internal features with no user-visible
  surface — but it must say so explicitly. A feature isn't done until the manual reflects
  it *or* the agent reports no change was needed.

### bug-triager — parallel bug analysis (background)
- **Owns:** `docs/BUGFIX_QUEUE.md`.
- **Dispatch it:** when a bug report lands **while other work is in progress**. Send it
  `run_in_background: true`, one instance per report. It investigates read-only against
  the real code, root-causes the defect, and appends a structured, ready-to-implement
  proposal — it **never** implements the fix or touches source, tests, or specs, so it
  can't collide with whatever the main session is mid-editing.
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
  - **FILE (background):** the moment any session hits a decision it must not make alone
    — a trade-off with no obviously right answer, a ruling that would reverse recorded
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
`Explore` and `Plan` (read-only search and architecture planning), `general-purpose`,
and `feature-tester`'s cousins exist too — but the seven above are the ones that carry
the workflow. Reach for the specialists first.

---

## 3. The main session as orchestrator

A normal "build me this feature" turn runs roughly like this:

1. **Harmonize first.** Dispatch `spec-maintainer` so the spec is clean before you design
   against it. It reconciles spec vs. code and, if reconciliation changed what should be
   built, *restates the feature for implementation* — that restatement supersedes the
   queue entry.
2. **Implement.** Write the code. Run **targeted** tests for the area you touched as you
   go (`QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/<area> -q` on Linux) —
   not the full suite every time.
3. **Test.** Dispatch `feature-tester`. If red, fix in the main session and re-dispatch
   until green. It writes the TEST_LOG entry.
4. **Manual.** Dispatch `manual-maintainer` to fold the feature into `manual.md` (or
   report no change needed).
5. **Re-harmonize + fold.** Dispatch `spec-maintainer` again to fold the shipped design
   into the spec and revisit the README in the same pass.
6. **Commit.** The spec, test-log, and manual changes ride *with* the feature in one
   commit. The full suite runs once, at commit time — in parallel (`-n 10`), never piped
   through `tail` (it eats the failing test's name).

The main session holds the thread; the agents each guarantee one invariant (spec is
right, tests are green, manual is current). You don't have to remember the invariants —
you have to remember to *dispatch the agent that enforces each one.*

### When you have work in flight and something new arrives

This is the whole reason the triage agents exist. New input shouldn't derail the code
you're mid-editing, and it shouldn't collide with it on disk either. So it gets parked in
a queue by an agent that only writes to that queue:

- **A bug report arrives** → `bug-triager`, **background**, one per report. Keep coding.
- **A feature idea arrives** → `feature-triage`, **foreground** (it needs to interrogate
  the idea with you). Then keep coding.
- **You hit a decision that's the owner's to make** → `owner-decision`, **background** to
  file it. Then continue on everything it doesn't block.

Later, in a dedicated pass, you *drain* a queue: read it, do the design-and-build (or
answer, for decisions), and **flip the entry's status in place** — never delete it. The
entries are the record of what was reported/proposed/decided and *why the resolution was
shaped that way.*

---

## 4. How to feed the queues (the part you'll do most)

### Adding a bug report
> "Here's a bug: opening the XSD editor leaves a tab you can't close."

The main session dispatches `bug-triager` in the background. It investigates read-only,
finds the root cause (down to file and line), and appends a `BUG-NNN` entry with
`Status: OPEN`. You are **not** blocked and the resolve happens on a separate pass — often
another thread entirely. Don't ask to fix it right now unless you mean to open the whole
resolve workflow.

**Status lifecycle:** `OPEN` → `RESOLVED (<commit>)`, flipped in place by whoever does the
resolve pass.

### Adding a feature request
> "I want a Test button for *both* connections in Project Settings."

The main session dispatches `feature-triage` in the **foreground**. Expect it to talk
back — "which connection failure state should the button surface?", "should this EXTEND
the existing Connections tab spec (§18.2) rather than be a new feature?" Answer its
questions; it writes one `FQ-NNN` entry with `Status: QUEUED`.

**Status lifecycle:** `QUEUED` → (drain pass: `spec-maintainer` folds it, you build it) →
`PROCESSED (<commit or spec §>)`.

### Filing a decision
When you're mid-build and hit *"should undo cross document boundaries or not?"* — a real
design fork — you don't guess and you don't stall. `owner-decision` files it in the
background; you continue on everything that fork doesn't block. In a later
decisions-only session, `owner-decision` puts it to the owner and records the answer
**with its reasoning**.

**Status lifecycle:** `OPEN` → `ANSWERED (<date>)` / `CLOSED — <reason>` /
`SUPERSEDED BY DEC-NNN`. If an answer implies surface that doesn't exist yet, it doesn't
go straight to code — it's routed through `feature-triage` to be placed and queued.

---

## 5. Rules that keep the machine honest

- **One writer per file.** Never hand-edit a queue or spec another agent owns. Route the
  change through that agent.
- **The spec is the final truth, so it carries the obligation to be right.** Code and
  spec are never left diverged. Stale spec → `spec-maintainer` fixes it. Wrong code →
  `spec-maintainer` files a bug; it does not rewrite the requirement to match the bug.
- **Harmonize before you build, fold after you ship.** A contradiction in the spec becomes
  a deep problem in the code.
- **A feature isn't done** until: feature-tester is green *and* logged, manual-maintainer
  has updated the manual (or explicitly no-op'd), and spec-maintainer has folded it in.
  All three ride in the feature's commit.
- **Triage parks, it never builds.** `bug-triager` / `feature-triage` / `owner-decision`
  only write their own queue. Building and folding happen on a separate, deliberate pass.
- **Filing a decision is not stopping.** Continue on everything the decision doesn't block.
- **Never bury a decision inside an implementation report** — it gets missed, and the
  assumption hardens silently. It goes through `owner-decision` or it doesn't exist.

---

## 6. Cheat sheet

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
