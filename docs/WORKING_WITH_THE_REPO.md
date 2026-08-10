# Working With the Repo — Start to PR

*The practical, step-by-step loop: from `git pull` on a clean morning, to pointing
Claude Code at the folder, to opening a branch, to handing a PR to the owner.*

This is the **operational** companion to [`VIBE_CODING_MANUAL.md`](VIBE_CODING_MANUAL.md).
That doc explains *who* does the work (the orchestrating session and its subagents).
**This** doc explains the mechanics *around* it — git, Claude Code, branches, and how
pull requests get reviewed and merged.

- **Repo:** `https://github.com/tyutyuszomoru/pgtp_editor.git`
- **Default branch:** `main`
- **Local path (this machine):** `/home/zrb/Projects/pgtp_editor`

---

## 0. One-time setup (only if this is a fresh machine)

Skip this whole section if the repo is already cloned and Claude Code is installed.

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

---

## 1. Start the day: sync `main`

Always begin from an up-to-date `main`. Never start work on a stale tree.

```bash
cd /home/zrb/Projects/pgtp_editor

git checkout main            # make sure you're on main
git pull origin main         # fast-forward to the latest
git status                   # expect: "working tree clean"
```

If `git status` is **not** clean, stop and deal with it before pulling — either commit,
stash (`git stash`), or discard. Pulling onto a dirty tree invites conflicts you don't
want mixed into new work.

> **Watch the shared docs.** The queue files (`docs/BUGFIX_QUEUE.md`,
> `docs/FEATURE_QUEUE.md`, `docs/DECISION_QUEUE.md`) and the spec change often and from
> multiple threads. `git pull` first so you're triaging/resolving against the current
> state, not a version another session already moved past.

---

## 2. Point Claude at the folder and open Claude Code

Claude Code works from **your current directory** — the folder you `cd` into becomes the
project root it reads, searches, and edits. So "pointing Claude at the folder" is just:

```bash
cd /home/zrb/Projects/pgtp_editor    # the repo root — where CLAUDE.md lives
claude                               # launches the interactive session here
```

That's the whole trick. Because you launched it from the repo root:

- It automatically loads `CLAUDE.md` (the project's mandatory instructions).
- It can see the whole tree — `pgtp_editor/`, `tests/`, `docs/`, `.claude/agents/`.
- The specialist agents in `.claude/agents/` become available to dispatch.

**Launch from the root, not a subfolder.** If you `cd pgtp_editor/ui && claude`, Claude
starts scoped to `ui/` and won't see `CLAUDE.md`, the agents, or the queues. Always open
it at `/home/zrb/Projects/pgtp_editor`.

Once you're in, your first message frames the session. Typical openers:

> "Pick up the feature queue." — drains `docs/FEATURE_QUEUE.md`.
> "Here's a bug report: …" — triages it into `docs/BUGFIX_QUEUE.md`.
> "Build feature X." — a normal implementation turn.

---

## 3. Start a new branch for the work

**Never commit new work directly to `main`.** Every change — feature, bugfix batch, spec
pass — gets its own branch, so `main` stays releasable and each unit of work becomes one
reviewable PR.

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
> starts work — its standing rule is *if on the default branch, branch first*. You can
> also do it by hand as above; either way, confirm you're **off `main`** before the first
> commit (`git branch --show-current`).

---

## 4. Do the work (this is where the agent loop lives)

The actual build follows [`VIBE_CODING_MANUAL.md`](VIBE_CODING_MANUAL.md) — harmonize the
spec, implement, `feature-tester` until green, `manual-maintainer`, fold back into the
spec. Nothing about that changes here. Two mechanics worth repeating:

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

Commit messages in this repo follow a `type(scope): summary` shape
(`docs(DEC-015 answered): …`, `chore(release): 0.4.0`, `merge(BUG-044): …`). Claude
appends its `Co-Authored-By` trailer automatically. Commit and push only when you ask —
the session won't push on its own.

---

## 5. Push the branch and open the PR

When the work is done and the full suite is green:

```bash
git push -u origin <branch-name>
```

Then open the pull request against `main`. The session can do this for you with the
GitHub CLI:

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

---

## 6. How PRs are handled — the owner's side

Merging is the **owner's** job, not the session's. This is the deliberate handoff point:
the dev session proposes; the owner disposes. Here's how it goes on your (the owner's) end.

1. **Review on GitHub.** Open the PR at
   `https://github.com/tyutyuszomoru/pgtp_editor/pulls`. Read the diff, the PR body's
   claimed test result, and check the queue-entry ids it says it closes.

2. **Ask for changes in-thread if needed.** If something's off, request changes on the
   PR. The dev session pushes follow-up commits to the *same branch* — the PR updates
   automatically. Re-review.

3. **Merge when satisfied.** Use GitHub's **Merge pull request** button. This repo's
   history uses merge commits (`Merge pull request #15 from …/dev_review_01`), so a
   standard merge keeps that lineage. Squash is fine for small single-purpose branches if
   you prefer a clean line — your call as owner.

4. **After merge, flip the queue statuses.** A merged PR is the trigger to mark its work
   done *in place* (never delete the entry):
   - `docs/BUGFIX_QUEUE.md`: `Status: OPEN` → `RESOLVED (<merge-commit>)`
   - `docs/FEATURE_QUEUE.md`: `Status: QUEUED` → `PROCESSED (<commit or spec §>)`
   - `docs/DECISION_QUEUE.md`: handled by `owner-decision`, not by hand.

   In practice you hand this back to a session — *"PR #16 merged, close out its queue
   entries"* — and it does the flips (through the owning agent where one applies).

5. **Pull `main` locally.** Back in the terminal, `git checkout main && git pull` so your
   local tree includes the merge before you cut the next branch. Delete the merged branch
   if you like: `git branch -d <branch-name>` (local) and `git push origin --delete
   <branch-name>` (remote).

**Why the owner merges and the session doesn't:** a merge to `main` is an
outward-facing, hard-to-reverse action. The session's rule is to *propose* it and let you
approve — the same reason it files owner-only decisions instead of guessing them. You are
the gate on `main`.

---

## 7. The loop, condensed

```
git checkout main && git pull origin main      # 1. sync
cd /home/zrb/Projects/pgtp_editor && claude     # 2. open Claude at the root
git checkout -b feature/<slug>                  # 3. branch off main
  … build via the agent loop (VIBE_CODING_MANUAL) …
QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest -q -n 10   # green full suite
git push -u origin feature/<slug>               # 5. push
gh pr create --base main …                      #    open PR — do NOT merge
  … owner reviews & merges on GitHub …          # 6. owner's gate
git checkout main && git pull                   # 7. sync, then next branch
```

**Golden rules:**
- Start every branch from a freshly-pulled `main`.
- Launch `claude` from the repo **root** so it loads `CLAUDE.md` and the agents.
- One branch = one coherent unit of work; spec/tests/manual ride *with* it.
- The session opens the PR; **the owner reviews and merges.**
- A merge is the cue to flip queue statuses in place — never delete entries.
