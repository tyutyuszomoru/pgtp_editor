# Decision Queue

Decisions that belong to the **owner** and to nobody else.

**Owner:** the `owner-decision` agent (`.claude/agents/owner-decision.md`) is the **sole writer** of this
file. No other session or agent appends entries, records answers, or flips a status here. A session that
hits a decision it must not make alone dispatches `owner-decision` in the **background** to file it, then
carries on with everything that decision does not block.

**To answer these:** in a session dedicated to decisions, dispatch `owner-decision` in the **foreground**.
It sweeps the queue, retires anything already overtaken by shipped code, and puts the live ones as
self-contained questions.

**Statuses:** `OPEN` · `ANSWERED (<date>)` · `CLOSED — <reason>` · `SUPERSEDED BY DEC-NNN`.
Entries are never deleted — what was once uncertain is worth keeping.

> **Seeding note (2026-08-08).** DEC-001…006 were lifted from decisions that had been raised inside
> implementation reports in the main session, where they were easy to miss — the problem this queue
> exists to fix. They carry that provenance rather than a clean filing, so `owner-decision` should
> **re-verify each against current code before asking**; some may already be overtaken.

---

## DEC-001 — Where does the snippet store live: per-user or per-project?

- **Status:** OPEN
- **Raised:** 2026-08-08, by the main session, from FQ-030's remaining scope
- **Blocks:** yes — FQ-030's snippet store and its Maintenance-mode snippet editor cannot be built until
  this is settled. It is the last substantive piece of FQ-030.

**Context.** FQ-030 adds reusable SQL snippets. Everything else in FQ-030 has shipped; the store itself was
deliberately deferred because where it lives determines its file format, its migration story, and whether
the Maintenance-mode editor edits one store or a merged view of two.

This is the same axis the owner already ruled on for `ProfileKey` in §17, and that ruling is the strongest
input here: a single machine-keyed store was rejected, verbatim — *"If I have a single keyed store, I can't
move the project from machine to machine. Project is a movable artifact."* Whether snippets are *part of*
the movable artifact is the open question; the `ProfileKey` ruling settled that project **settings** are,
but snippets are plausibly a property of the person rather than the project.

**Options.**
- **Per-project, inside the `.pgtp` sidecar** — snippets travel with the project, so a team sharing a
  project shares its snippets. *Cost:* a personal shorthand written while working on project A is
  unavailable in project B, which is the common case for a single developer. Also grows the artifact that
  must round-trip byte-for-byte.
- **Per-user, in the app's config dir** — snippets follow the person across every project, which matches
  how editor snippets normally behave. *Cost:* they do not travel with a shared project, and they are
  invisible to a colleague opening the same `.pgtp`.
- **Both, with per-project shadowing per-user** — covers both cases. *Cost:* two stores, a merge rule, a
  precedence rule, and an editor that must show which store an entry came from and let you move it between
  them. Materially more surface than either single option.

**Recommendation:** per-user. A snippet is a typing shortcut, not a property of the schema, and the
`ProfileKey` ruling's reasoning — the project is a *movable artifact* — argues for keeping personal
convenience **out** of that artifact rather than in it. Per-project can be added later as an override
without invalidating a per-user store; the reverse migration is harder.

**Unblocks:** FQ-030's store format, and the Maintenance-mode snippet editor.

---

## DEC-002 — Does `[Project]` routing key on the whole prefix, or on a content marker?

- **Status:** OPEN
- **Raised:** 2026-08-08, by the main session, as BUG-042's sub-decision
- **Blocks:** partially — the routing change is in flight and needs a rule; the wiring agent was told to
  choose by reading the actual emitters, so this may already be answered by the time it is asked.

**Context.** BUG-042 was DECIDED (`dacde0c`) as option C: route close-time `[Project]` narration to the
Messages tab. `audit_router.py:109` currently reads `PROJECT_PREFIX: TO_ACTIVITY` and must change. The open
part is how narrowly to target it.

Not every `[Project]` line is close-time narration. Routing the whole prefix moves lines that may belong in
Activity; routing only marked lines requires the emitters to carry a marker they do not carry today.

**Options.**
- **Route the whole `[Project]` prefix to Messages** — one line of change, no emitter edits. *Cost:* any
  non-close-time `[Project]` line moves too, possibly wrongly.
- **Add a content marker at the emit sites, route on that** — precise. *Cost:* touches every emitter, and a
  future emitter that forgets the marker silently routes to the wrong panel — a failure mode with no test
  that would catch it.

**Recommendation:** whole prefix, unless reading the emitters shows a `[Project]` line that clearly belongs
in Activity. Precision that depends on every future call site remembering a marker is precision that decays.

**Note for whoever implements it:** `tests/ui/test_ddl_project_wiring.py` (~:1203-1212) currently **asserts
the defect as intended behaviour**. It must be rewritten, not extended.

**Unblocks:** closing BUG-042 against a real commit.

---

## DEC-003 — A cloned project arrives without connections and has no re-supply path

- **Status:** OPEN
- **Raised:** 2026-08-08, from a §29 spec sweep
- **Blocks:** no — but it hardens with every feature that assumes a connection exists.

**Context.** §29 specifies that a cloned project arrives without connections, which is correct: credentials
must not travel with a movable artifact. What it does not specify is how the recipient supplies them. There
is no stated path from "opened a clone" to "has a working connection", so the behaviour on opening one is
whatever the code happens to do rather than something designed.

**Options.**
- **Prompt on open when a clone has no connections** — the recipient is told immediately, in the one moment
  they have the context to act. *Cost:* a modal on open, and a rule for what counts as "a clone" versus a
  project whose connections were deliberately cleared.
- **Leave it to Project Settings, and make the refusals point there** — no new surface; every gesture that
  needs a connection already refuses with a reason (FQ-023), so the reason names Project Settings. *Cost:*
  the recipient discovers the gap by hitting it rather than being told.
- **Specify it as intentional and document it in the manual** — cheapest. *Cost:* documentation is not a
  path; it is a description of the absence of one.

**Recommendation:** the second. FQ-023 already built the machinery for a gesture to state its reason instead
of vanishing, and this is exactly that shape — no new modal, and the remedy is named at the moment of need.
The work is verifying the refusals actually name Project Settings.

**Unblocks:** §29 stating a complete path rather than a rule with no exit.

---

## DEC-004 — `Ctrl+Shift+B` is hosted in two places

- **Status:** OPEN
- **Raised:** 2026-08-08, from a shortcut-table sweep
- **Blocks:** no — but it is a live correctness risk, not a tidiness one.

**Context.** The chord is bound in two hosts. The failure mode is specific and silent: when both bindings
are enabled at once, Qt treats the chord as ambiguous and fires **neither**. The user presses the key and
nothing happens, with no error. Whether that is reachable today depends on whether the two hosts are ever
simultaneously enabled — which needs verifying before asking, because if they never are, this is a latent
trap rather than a present bug.

**Options.**
- **Unbind one host** — removes the ambiguity outright. *Cost:* somebody loses a shortcut they may use.
- **Make the binding conditional on context** so only one is ever enabled. *Cost:* the enable/disable logic
  must be exactly right in both directions, and getting it wrong reintroduces the silent-nothing failure.
- **Leave it** — valid if the hosts are provably never both live. *Cost:* the proof has to hold for every
  future mode added.

**Recommendation:** verify reachability first, then unbind one. Conditional binding buys a shortcut back at
the price of the exact failure mode being avoided.

**Unblocks:** an accurate shortcut table, and one fewer silent-failure path.

---

## DEC-005 — `DROP INDEX` applied-bookkeeping identity omits the table

- **Status:** OPEN
- **Raised:** 2026-08-08, from a DDL bookkeeping sweep
- **Blocks:** no — but it is a data-shape decision, so it gets more expensive to change once records exist.

**Context.** Applied-DDL bookkeeping keys each statement by an identity. For `DROP INDEX`, the identity
recorded does not include the table the index belonged to. Postgres index names are unique per schema, not
per table, so this is not immediately ambiguous — but every other statement's identity carries its subject,
and this one's does not, which makes the record inconsistent to query and to display.

**Options.**
- **Add the table to the identity** — consistent with every other statement kind. *Cost:* the table is not
  always cheaply available at the point the identity is computed for a drop, and existing records would have
  a shape the new code does not write.
- **Leave it, and document why** — no migration, no lookup. *Cost:* a permanent exception in a data shape,
  which the next person to read the bookkeeping will treat as a bug and "fix".

**Recommendation:** leave it and document the reason in the spec. A schema-unique name is a genuine identity;
the real defect here is an undocumented exception, not the missing field. But this is squarely the owner's
call, because it is about what the record is *for*.

**Unblocks:** §18's bookkeeping section stating one rule with a stated exception, rather than an
inconsistency a reader must rediscover.

---

## DEC-006 — Maintenance mode hides menus but leaves their shortcuts live

- **Status:** ANSWERED (2026-08-08)
- **Raised:** 2026-08-08, by the main session, during the Maintenance-mode review
- **Answer:** leave it.

**Context.** Maintenance mode was described as filtering what you can do. That is true of the File menu,
which filters to `_MAINTENANCE_FILE_ITEMS = ("New Session", "Exit")`. It is **not** true of View, Database,
Tools and Generation, which hide the whole `QMenu` — and hiding a top-level `QMenu` does not disable its
child actions, so their keyboard shortcuts remain live. A hidden command is still reachable by chord.

**Owner's reasoning:** the mode is a guardrail, not a security boundary. Someone who knows the chord for a
hidden command knows what they are doing; the mode exists to keep the surface calm during maintenance, not
to prevent deliberate use.

**The wider principle this establishes** — and the durable part of the answer: **hiding in this project means
"not in your way", never "prevented"**. Anywhere the spec or the manual describes hiding as prevention, it is
overstating what the code does and should be corrected to match. A future decision to actually *prevent*
something must disable the action, not hide its menu.

**Recorded consequence:** the spec must not claim Maintenance mode restricts what can be executed. There is
no code change.
