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

**When an answer forks a NEW FEATURE, route it through `feature-triage`.** An answered decision is a ruling,
not a queued feature. If the ruling implies surface that does not exist yet (a new gesture, dialog, store or
command), the main session dispatches **`feature-triage`** in the foreground to place it EXTEND-vs-CREATE
against `CONSOLIDATED_SPEC.md` and write it into `docs/FEATURE_QUEUE.md`. This file records the *why*; the
feature queue records the *what to build*. `owner-decision` never writes to the feature queue.

> **Seeding note (2026-08-08).** DEC-001…006 were lifted from decisions that had been raised inside
> implementation reports in the main session, where they were easy to miss — the problem this queue
> exists to fix. They carry that provenance rather than a clean filing, so `owner-decision` should
> **re-verify each against current code before asking**; some may already be overtaken.
>
> **Verification sweep (2026-08-10).** That re-verification has now been done against the tree, and it
> confirmed the worry: DEC-002 was overtaken by shipped code, DEC-004's ambiguous-shortcut premise was
> false, and **DEC-005's central factual claim was inverted** — see its CAUTION block, which the answer
> already recorded there must be read against. Entries filed from a report, without a code check, produce
> answers to questions the code was not asking.
>
> **But a false mechanism is not a dead decision (2026-08-10).** DEC-004 was closed on that sweep and has
> since been **reopened and retitled**: the ambiguous-shortcut mechanism it claimed really was false, but
> the underlying dual hosting was real and the owner ruled on it. Refuting how a filing described a problem
> is not the same as disposing of the problem.

---

## DEC-001 — Where does the snippet store live: per-user or per-project?

- **Status:** ANSWERED (2026-08-10)
- **Answer:** **Per-user, with a refined shape.** In the owner's words, the store *"should live in the
  software's folder, editable by the users, exportable and importable for sharing with others."* Concretely:
  - a **single** per-user store, living in the **app's own folder** (not embedded in the `.pgtp` artifact);
  - **user-editable directly** (the Maintenance-mode editor edits this one store);
  - **sharing is via explicit export / import**, a manual gesture — *not* via per-project embedding and
    *not* via an auto-merged two-store model.
- **Owner's reasoning:** consistent with the §17 `ProfileKey` ruling — the project is a *movable artifact*
  and personal convenience stays out of it. A snippet is a typing shortcut, not a property of the schema.
  The "both stores / merge / precedence" option is **explicitly rejected**: sharing is a deliberate act
  (export then import), not an implicit merge, which keeps the store single and its precedence trivial.
- **Wider principle:** where the project must stay portable, personal state lives in the app's folder and
  crosses between people only by an **explicit** export/import gesture — never by silent embedding or merge.
- **Unblocks:** FQ-030's store format (a single per-user file in the app config dir, with export/import),
  and the Maintenance-mode snippet editor (edits one store; add export/import affordances). **This is a
  design refinement to FQ-030 that `spec-maintainer` must fold into the spec before the store is built.**
- **SHIPPED (verified 2026-08-10, sweep).** **FQ-030 is complete (`229dc11`)** and the store was built to
  this answer: `pgtp_editor/sql/snippet_store.py` with `snippets.json` in the app's own folder, a single
  per-user store, with explicit export/import. The verification block below (written when the store did
  not exist) is retained as the record of what was true when the question was put — read it as history,
  not as a description of the tree.
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

**Verification against the tree (2026-08-10), for whoever builds the store.**
- **The store genuinely does not exist.** There is no store module, no JSON file and no QSettings key for
  snippets. The only persistence-adjacent thing is the seam `CodeEditor.set_snippets(snippets)`
  (`pgtp_editor/ui/code_editor.py:444`), which layers a user set over `DEFAULT_SNIPPETS`
  (`pgtp_editor/sql/templates.py:194`) and **has no production caller** — its only caller is
  `tests/ui/test_editor_expansion.py:308`. So the answer above is a decision about a thing still to be
  built, not a description of one that exists.
- **The stated blocker has cleared.** `CONSOLIDATED_SPEC.md:8537-8553` defers the store partly because
  *"FQ-030 sequences the snippet editor into FQ-027's Maintenance mode, which is **unbuilt**"*. Maintenance
  mode **has since shipped** — `_MAINTENANCE_MENU_TITLES` / `_MAINTENANCE_FILE_ITEMS`
  (`pgtp_editor/ui/main_window.py:298`, `:317`) and the manual's *Getting Started ▸ Maintenance mode*. That
  spec sentence is stale and `spec-maintainer` should correct it in the same pass that folds this answer in.
- **Routing:** the answer does not merely settle FQ-030's deferred store — it **forks new feature surface**
  (an export gesture, an import gesture, and a Maintenance-mode editor for a single store). That new surface
  goes through **`feature-triage`** (foreground) so it is placed EXTEND-vs-CREATE against FQ-030 and lands in
  `docs/FEATURE_QUEUE.md` as an elaborated entry. An answer in this file is not a queued feature.

---

## DEC-002 — Does `[Project]` routing key on the whole prefix, or on a content marker?

- **Status:** CLOSED — overtaken by shipped code (2026-08-10). The implementer chose neither option as
  posed. Rather than reroute the whole prefix (which would misroute non-close-time `[Project]` lines) or
  add a per-line content marker (which decays as call sites forget it), they scoped the reroute with a
  **run-state flag**: `AuditRouter.project_closing` (`audit_router.py:217`), set to `True` only for the
  duration of the close in `ddl_project_controller.py:457-463` and restored after. `classify(...,
  project_closing=True)` then returns `TO_ACTIVITY_AND_RESULTS` for a `[Project]` row
  (`audit_router.py:176-177`); the default `DESTINATIONS[PROJECT_PREFIX]` stays `TO_ACTIVITY`
  (`:138`). This targets exactly the close-time window without touching emitters — strictly better than
  either recorded option — so there is no decision left for the owner. The `test_ddl_project_wiring.py`
  concern is also resolved: the tests now assert the corrected behaviour (`:1217` onward, "still readable
  after the close"). BUG-042 is decided in the bug queue (`dacde0c`).
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

- **Status:** ANSWERED (2026-08-10)
- **Answer:** **Rely on Project Settings plus the FQ-023 refusals — no new modal on open.** The path from
  "opened a clone" to "has a working connection" is: a gesture that needs a connection refuses with a
  reason, and the reason names Project Settings, where the recipient supplies one. The remaining work is
  **verifying the refusals actually point at Project Settings** (they do for the sandbox path —
  `manual.md:2744` — but the coverage across every connection-needing gesture must be confirmed).
- **Owner's reasoning:** FQ-023 already built the machinery for a gesture to state its remedy instead of
  vanishing, and this is exactly that shape. A modal on open would add surface and force a rule for what
  counts as "a clone" versus deliberately-cleared connections; the refusal path needs neither.
- **Unblocks:** the spec's open note at `CONSOLIDATED_SPEC.md` (~:3467, *"no policy for re-supplying them
  on clone is specified, and none is invented here"*) is now **resolved to this policy** and must be
  restated by `spec-maintainer` from "none specified" to "re-supply via Project Settings; refusals name it."
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

**Verification against the tree (2026-08-10) — the answered option is largely already built.**
- **The refusals do name Project Settings**, in code, not only in the manual. `GESTURE_UNAVAILABLE_REASONS`
  (`pgtp_editor/ui/ddl_object_editor.py:172-207`) reads *"…could not be reached, or none is set up yet
  (check its connection in **Project Settings**)"* for check-and-commit, and names *"Database ▸ Connection
  Setup… (projectless) or **Project Settings ▸ Connections** (with a project open)"* for apply-to-quality.
  Same remedy in `pgtp_editor/ui/sandbox_controller.py:340`, `:349` and
  `pgtp_editor/ui/sql_console_panel.py:179`.
- **It goes further than the entry claimed:** `MainWindow._prompt_missing_connection`
  (`pgtp_editor/ui/main_window.py:3514-3532`) not only *says* Project Settings with a project open, it
  **opens the dialog** (`self._ddl_project_ui.open_settings()`).
- **Correction to the citation in the answer above:** the anchor should be the code sites listed here.
  `manual.md:2744` is about the sandbox session having no explicit close, not about the refusal wording.
- **Remaining work is therefore a coverage audit, not a build**: confirm every connection-needing gesture
  refuses with a remedy that names Project Settings, and fix the ones that do not.
- The spec sentence to restate is `CONSOLIDATED_SPEC.md:3524-3527` (*"no policy for re-supplying them on
  clone is specified, and none is invented here"*).

---

## DEC-004 — Should `Ctrl+Shift+B` be handled like every other shortcut, or keep its widget-level handler?

- **Status:** ANSWERED (2026-08-10)
- **Raised:** 2026-08-08, from a shortcut-table sweep
- **Retitled 2026-08-10.** This entry was previously titled *"`Ctrl+Shift+B` is hosted in two places"* and
  had been closed as *"premise false, already resolved"*. **That closure disposed of the wrong question.**
  It correctly refuted the *mechanism* the filing claimed (Qt's ambiguous-shortcut failure — see the
  verification note below, which stands), but the dual hosting is real and the owner considers it a defect
  **regardless of the mechanism**. The entry is therefore reopened under the question actually at issue and
  answered below.

**Owner's ruling (2026-08-10, final).** **`Ctrl+Shift+B` must be handled the same as every other keyboard
shortcut: `QShortcut`/`QAction` in the normal run, direct key-press handling only in testing.**

**Owner's reasoning — and the durable part.** The widget-level handler exists because *"`QShortcut`
activation is not guaranteed"* under the offscreen platform the tests run on
(`pgtp_editor/ui/code_editor.py:735-746`). That is a statement about **the harness, not about the
product**. The ruling generalises well beyond this one chord:

> **Wider principle:** *where a design exists to satisfy the test harness rather than the product, the
> harness is what should change.* A production code path whose only justification is how the tests are run
> is not a design; it is a test artifact that escaped into the product.

**The constraint any implementation must solve.** `CodeEditorDialog` (**Edit code…**,
`pgtp_editor/ui/main_window.py:2444-2453`) has **no menu bar**, so the `Select ▸ Select Enclosing Block`
`QAction` (`main_window.py:2416`) does not exist there and the `keyPressEvent` branch is currently the
chord's **only** host in that dialog. Removing it naively kills bracket-select in Edit code…. The likely
shape of the fix is a **`QShortcut` owned by the dialog**, so the dialog hosts the chord the same way the
window does.

**Open mechanical risk, recorded rather than papered over.** If it turns out `QShortcut` genuinely does not
activate under the offscreen platform, then *"key-press only in testing"* **cannot** mean keeping a
production `keyPressEvent` branch that only tests ever exercise — that is dead production code and is not
what the ruling asks for. In that case **the tests must drive the command another way**, at a stated cost
in fidelity: a test that calls `action.trigger()` no longer proves the chord is *bound*, only that the
command works. **`bug-triager` has been dispatched to establish this empirically and to propose the fix.**
**The ruling stands either way** — only the mechanism is contingent on that finding.

**Consequence for the manual (not to be fixed here).** `pgtp_editor/resources/manual.md:3705-3714`
documents the dual hosting as a deliberate caveat of shortcut rebinding — that rebinding
**Select ▸ Select Enclosing Block** moves the *menu* command while `Ctrl+Shift+B` keeps bracket-selecting
inside every code editor. Once the chord is hosted normally it becomes **fully rebindable**, so that caveat
becomes wrong. **`manual-maintainer` owes an update** when the fix lands. `owner-decision` does not edit the
manual.

**SHIPPED (verified 2026-08-10, sweep).** **BUG-046 is RESOLVED (`e8df6c3`)**, exactly as the ruling
required and with the mechanical risk resolved in the ruling's favour: the offscreen premise was
**measured false**, the `Ctrl+Shift+B` branch is gone from `CodeEditor.keyPressEvent` (a tombstone NOTE
stands at `pgtp_editor/ui/code_editor.py:742-752`), and `CodeEditorDialog` owns the chord as its own
`WindowShortcut` (`code_editor.py:940-944`) with the literal-sequence limitation stated in place. **The
manual debt this entry predicted is now real and unpaid** — `resources/manual.md:4109-4114` still tells
the user *"Ctrl+Shift+B is handled in two places"* and that it *"keeps selecting the enclosing bracket
span inside every code editor"* regardless of rebinding, which is false for PHP tabs, DDL object tabs,
both DDL Explorers and the Sandbox SQL console (those follow the rebound `Select ▸ Select Enclosing
Block` now). It remains true **only** for the menu-less **Edit code…** dialog. `manual-maintainer` owes
this; `owner-decision` does not edit the manual.

**Unblocks:** `bug-triager`'s empirical finding converts straight into the fix — remove the `Ctrl+Shift+B`
branch from `CodeEditor.keyPressEvent`, give `CodeEditorDialog` its own `QShortcut`, and rework
`tests/ui/test_select_menu.py:488` (which currently pins the double-delivery) to match whichever driving
mechanism survives.

---

**Superseded prior answers, kept for the record.** Two earlier owner answers are now overridden by the
ruling above and must **not** be implemented:

1. *"Keep both, but make the duplicate conditional on testing mode."* `owner-decision` flagged that this
   assumed the branch was purely a test fallback, when it is also the sole host in the menuless
   `CodeEditorDialog` — an offscreen-only gate would leave the chord dead in Edit code… during normal use.
2. *"Keep both handlers UNCONDITIONAL, and add a one-line comment saying the double delivery is deliberate."*
   This resolved (1)'s collision by accepting the dual hosting. The owner has now reversed it: the dual
   hosting is the defect, and the Edit code… gap is to be closed with a dialog-owned `QShortcut` rather
   than with a widget key handler.

**Verification note (code analysis, still correct and retained deliberately — it prevents the false
mechanism being re-filed).**

**Why the original ambiguity premise is false.** The entry asserted Qt's ambiguous-shortcut failure — two bindings enabled at once, so
the chord fires **neither**. That mechanism does not apply here, because **these are not two shortcuts**:

- one host is a `QAction` shortcut, `Select ▸ Select Enclosing Block`, set at
  `pgtp_editor/ui/main_window.py:2416`;
- the other is not a shortcut at all but a **`keyPressEvent` branch** in
  `pgtp_editor/ui/code_editor.py:735-746`, calling `CodeEditor.select_enclosing_brackets` (`:412`).

Qt's shortcut map consumes the key event **before** it reaches the focused widget, so a `CodeEditor`-hosting
tab does not double-handle and there is no ambiguity to resolve. `main_window.py:2444-2453` records this
under the heading *"The duplicate Ctrl+Shift+B handler, resolved (FQ-015 trap)"* and states it was
**verified, not assumed**.

**The second host was kept for two reasons the code comment gives:** it is the **only** host for the chord
in a `CodeEditorDialog`, which has no menu bar; and it is the reliable path under the offscreen test
platform, where `QShortcut` activation is not guaranteed. Both paths land on the same editor and the
operation is idempotent, so a double delivery is harmless.

**The ruling accepts the first reason and rejects the second.** The Edit code… gap is real and must be
closed (by a dialog-owned `QShortcut`); the offscreen-reliability reason is a property of the harness and is
not a reason for a production code path. "Harmless" is not the test — the test is whether the design would
exist if the tests did not.

**Do not re-file the ambiguity mechanism.** The Qt shortcut-map analysis above is settled: there is no
ambiguous-shortcut failure here, and an entry claiming one should be closed on sight. What is at issue is
the dual hosting itself, and that is answered above.

---

## DEC-005 — `DROP INDEX` applied-bookkeeping identity omits the table

- **Status:** SUPERSEDED BY DEC-007 (2026-08-10)

> **DO NOT ACT ON THE ANSWER BELOW. This entry was answered on a FALSE PREMISE.** The question told the
> owner that a `DROP INDEX` row omits the **table**. The code says the opposite: the table **is** in the key
> (`AlterDdlRef` is built with `table=table_name`, `pgtp_editor/ui/main_window.py:4645-4655`), and the value
> actually missing is the **index name**, which lives in `AlterDdlRef.subject` — a field `CheckRequest` has no
> slot for at all (`pgtp_editor/db/ddl_check.py:528-541`). The owner's reasoning — *"a schema-qualified index
> name is a genuine identity on its own"* — therefore reasons about a value that is **not in the key**, and the
> answer's closing claim that "the empty table slot for a drop-index is now sanctioned" describes a slot that
> is not empty.
>
> **BUG-044 (`docs/BUGFIX_QUEUE.md:3873`) supersedes the whole question**, and makes it much wider than one
> statement kind: `AlterDdlRef.name` defaults to `""` and is never set, so **seventeen** operations on one
> table (the sixteen of `ALTER_TABLE_ALL_ACTIONS` plus `OP_CREATE_TABLE`) all write the single key
> `("alter", schema, "", table)` and overwrite each other via `ON CONFLICT … DO UPDATE`. `DROP INDEX` is
> simply one of the seventeen colliders; its row carries neither the index name nor any other distinguishing
> value. The real question is DEC-007.
>
> **`spec-maintainer` has already been told not to fold this answer into §18.5** — doing so would enshrine a
> description of the code that is false. The owner's original answer and reasoning are preserved unedited
> below for the record only.

- **Original answer (SUPERSEDED — do not implement):** **Leave it, and document why in the spec.** Do not add the table to the identity; instead
  record, in §18's bookkeeping section, that a `DROP INDEX` identity legitimately omits the table.
- **Owner's reasoning:** a Postgres index name is **schema-unique**, so a schema-qualified index name is a
  genuine, unambiguous identity on its own — the table adds nothing to uniqueness. The real defect was never
  the missing field; it was that the exception was **undocumented**, which invites the next reader to
  "fix" a non-bug. Documenting the reason removes the only actual problem.
- **Wider principle:** an identity is judged by whether it uniquely names its subject, not by whether it
  matches the shape of the other identities. A justified, documented exception is preferable to uniformity
  bought with a field that carries no information.
- **Unblocks:** `spec-maintainer` restating §18's bookkeeping section to state one rule **with a stated
  exception** for `DROP INDEX`, rather than an inconsistency a reader must rediscover. The code
  (`working_set_ref = (kind, schema, name, table or "")` in `ddl_check.py:595-601`) stays as-is; the
  empty table slot for a drop-index is now sanctioned, not a bug.
- **Raised:** 2026-08-08, from a DDL bookkeeping sweep
- **Blocks:** no — but it is a data-shape decision, so it gets more expensive to change once records exist.

> **CAUTION — the question was put on a FALSE PREMISE, verified 2026-08-10. Do NOT act on the answer as
> written; it must go back to the owner.** The entry told the owner that `DROP INDEX`'s identity omits the
> **table**. The code says the exact opposite, and the field actually missing is the **index name**:
>
> - The `applied` bookkeeping PRIMARY KEY is `(kind, schema_name, object_name, table_name)`
>   (`pgtp_editor/db/sandbox.py:737-745`), spelled once as `CheckRequest.working_set_ref`
>   (`pgtp_editor/db/ddl_check.py:595-601`) and written by `applied_upsert_sql` (`sandbox.py:777`).
> - A `DROP INDEX` buffer is an `AlterDdlRef` built with `table=table_name`
>   (`pgtp_editor/ui/main_window.py:4645-4655`), so **the table IS in the key**. The index name lives in
>   `AlterDdlRef.subject` (`main_window.py:481`, filled by `alter_ddl_subject`,
>   `pgtp_editor/ui/ddl_buffer_panel.py:277`), and `CheckRequest.from_ref` (`ddl_check.py:528-541`)
>   **never reads `subject`**.
> - So the owner's reasoning — *"a schema-qualified index name is a genuine identity on its own"* — is
>   about a value that is **not in the key at all**. The answer's closing sentence ("the empty table slot
>   for a drop-index is now sanctioned") describes a slot that is not empty.
>
> **And the real asymmetry is wider than one statement.** `AlterDdlRef.name` defaults to `""`
> (`main_window.py:487`) and is never set, so **every** ALTER-family buffer keys as
> `("alter", schema, "", table)`. All sixteen operations on one table — `DROP INDEX`, `CREATE INDEX`,
> `ADD CONSTRAINT`, `COMMENT ON COLUMN`, `DROP TABLE` — share **one** row and overwrite each other's
> `text_sha1`/`applied_at` (`ON CONFLICT … DO UPDATE`, `sandbox.py:796`). Alter tabs do reach this table:
> `MainWindow._apply_ddl_object_to_sandbox` → `CheckRequest.from_ref` → `apply_and_check` with
> `record_applied=True` (`main_window.py:6290`, `ddl_check.py:1429`). The consequence is that the
> stale-buffer caveat (`REASON_ALREADY_APPLIED`, `ddl_check.py:1792`) can compare a buffer's sha1 against a
> row describing a **different statement** — a wrong answer, not an absent one.
>
> **What must happen:** `spec-maintainer` must **not** fold "documented exception for `DROP INDEX`" into
> §18.5 on this basis — it would enshrine a description of the code that is false. The real question to put
> back to the owner is *"should the `applied` key carry the alter statement's subject, given that today all
> sixteen alter operations on a table collide on one row?"*, and the collision itself is plausibly a defect
> for `bug-triager` rather than a data-shape preference. If the corrected answer turns out to fork new
> behaviour rather than fix existing behaviour, route that part through **`feature-triage`** (foreground),
> not straight into the spec.

**Context (as originally filed — the factual claim in this paragraph is FALSE; see the CAUTION above).**
Applied-DDL bookkeeping keys each statement by an identity. For `DROP INDEX`, the identity
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

---

## DEC-007 — What identity should an ALTER statement have in the `applied` bookkeeping table?

- **Status:** ANSWERED (2026-08-10)
- **SHIPPED (verified 2026-08-10, sweep).** The former *"in flight in an isolated worktree"* note is
  retired: **BUG-044 is RESOLVED** (`1c28d33`, merged from the worktree; fix commit `ffbc377`) —
  `CheckRequest.working_set_name` shipped, filled by `_working_set_name_for(ref, buffer_text)`
  (`db/ddl_check.py:450`, `:527`, `:580`). Nothing in this entry is pending; it is now the record of
  **why** the alter half of `applied` is an event log, and the "do not silently fix it later" clause
  below is its live obligation.
- **Answer:** **Key an ALTER by its statement text.** The alter row's identity is
  `db/sandbox.py::text_sha1(buffer_text)`, carried in a **new `CheckRequest.working_set_name`** that feeds
  **only `working_set_ref`** and **never `checked_name`** — the latter is what gates tier 3, so keeping it
  untouched is what stops `plpgsql_check` switching on for ALTERs. It reuses the existing `object_name`
  column, so there is **no DDL migration**. The semantic consequence is **accepted and must be recorded**:
  the alter half of `applied` becomes an **append-only event log**, while the object half stays a
  **desired-state** table — one table, two meanings, stated plainly in §18.5 rather than avoided.
- **The cost was accepted, not overlooked — do not silently "fix" it later.** The alter half grows
  **without bound** (one row per distinct ALTER text ever applied), and the single table carries two
  meanings. Both were weighed and taken. A future reader who finds this untidy and "corrects" it back to an
  object-shaped key reintroduces BUG-044. If the growth ever becomes a real problem, that is a **new
  decision**, not a cleanup.
- **Owner's reasoning:** a **wrong verdict is strictly worse than an untidy table** — silent wrong results
  are the invariant this project holds above all. The **no-migration property is what makes the fix
  deployable to sandboxes that already exist**: `_CREATE_BOOKKEEPING_SQL` is `CREATE TABLE IF NOT EXISTS`
  with no migration path, so the operation+subject alternative (which needs a new key column) could never
  reach an existing sandbox — and it *still* mis-handles two `Drop Column` generations on different columns
  (`subject` is `""` for every `ALTER TABLE` flavour), so it does not even fix the reported defect.
  Statement-text keying is correct for every collider, stays idempotent (identical text upserts in place),
  and needs no migration. The object/event semantic split is **real** — an ALTER genuinely *is* an event,
  not an object — and pretending otherwise is what produced this bug, so it is recorded, not hidden.
- **Docstring caveat to state (owner-specified):** `CAVEAT_STALE_BUFFER` becomes **structurally
  unreachable for `kind == "alter"`**, which is **correct** — an edited ALTER is a *different statement*,
  not a stale version of one object. The docstring must say so, so the next reader does not read the
  unreachability as a bug.
- **Wider principle:** where the same table serves an object identity and an event, do not force one shape
  onto both; record the split explicitly. Correctness of the verdict outranks uniformity of the record.
- **Supersedes:** DEC-005 (whose question was put on a false premise; this is the real question).
- **Blocks:** yes — BUG-044's fix cannot be implemented until this is settled. BUG-044 is a **silent wrong
  result**, the invariant this project holds above all others, so the block is on a correctness fix.

**Context.** The sandbox's `applied` table records what has been committed to the sandbox, keyed
`(kind, schema_name, object_name, table_name)` (`pgtp_editor/db/sandbox.py:735-746`, spelled once as
`CheckRequest.working_set_ref`, `pgtp_editor/db/ddl_check.py:594-601`). That key is an **object** identity, and
an ALTER buffer has no object identity to put in it: `AlterDdlRef.name` defaults to `""`
(`pgtp_editor/ui/main_window.py:487`) and the single construction site
(`main_window.py:4645-4655`) never sets it. The distinguishing value lives in `AlterDdlRef.subject`, which
`CheckRequest` has no field for.

So **every** ALTER buffer on one table writes the same row `("alter", schema, "", table)`, and the upsert is
`ON CONFLICT … DO UPDATE` (`sandbox.py:790-798`) — the second write silently overwrites the first.
**Seventeen** operations collide, not sixteen: the sixteen of `ALTER_TABLE_ALL_ACTIONS` plus `OP_CREATE_TABLE`,
which builds an `AlterDdlRef` through the same path. Two `Drop Column…` generations on different columns of one
table collide with each other too.

The consequence is a **wrong verdict, not a missing one**. `Check Object in Sandbox` compares a buffer's sha1
against a row describing a *different statement*. The sharp case: apply Add Column, then check a
never-applied Drop Column tab on the same table — tier 2 returns `STATUS_PASSED` with
`REASON_ALREADY_APPLIED` for a statement the sandbox has never seen, and `_tier0_outcome` mirrors tier 2, so
tier 0 reads `passed` too.

**The gotcha any fix must respect.** `AlterDdlRef.name` being empty is deliberate and load-bearing:
`build_ladder` gates tier 3 on `request.checked_name`, which derives from `name`, so naively populating `name`
switches `plpgsql_check` on for ALTERs. `tests/ui/test_ddl_creation_wiring.py:507` pins that behaviour.

**Why this is yours and not the implementer's.** The mechanical fix is settled (`bug-triager` proposes a new
`CheckRequest.working_set_name` feeding only `working_set_ref` and never `checked_name`, reusing the existing
`object_name` column). What is not settled is what `applied` **means** afterwards.

**Options.**
- **Key by the statement text (`db/sandbox.py::text_sha1(buffer_text)`).** Correct for every collider,
  including two Drop Columns on different columns; re-applying identical text upserts in place, so it stays
  idempotent; and **no DDL migration is needed**, because it reuses the existing `object_name` column.
  *Cost:* it turns the alter half of `applied` into an append-only **event log** (one row per distinct ALTER
  ever applied, unbounded growth) while the object half remains a **desired-state** table — one table, two
  meanings. It also changes what the not-yet-built deployment generator (the table's only remaining reader,
  `sandbox.py:1026-1032`) will see, and the spec presents `applied` as state. Side effect worth stating in the
  docstring: `CAVEAT_STALE_BUFFER` becomes structurally unreachable for `kind == "alter"`, which is arguably
  right — an edited ALTER is a different statement, not a stale version of one object.
- **Key by `operation` + `subject`.** Keeps desired-state semantics and bounded row counts. *Cost:* still gives
  a wrong answer for two `Drop Column` generations on different columns, because `subject` is `""` for every
  `ALTER TABLE` flavour — so it does not actually fix the reported defect. And **the constraint that rules it
  out**: it needs a real schema change, and `_CREATE_BOOKKEEPING_SQL` is `CREATE TABLE IF NOT EXISTS` with no
  migration mechanism anywhere (`sandbox.py:735-746`), while `reset()` never drops the bookkeeping schema — so
  a fifth key column would never reach a sandbox that already exists.
- **Do not record alters at all** (`record_applied=False` for `kind == "alter"`, with a stated tier-2 reason
  *"an ALTER is not an object; the working set records objects"*). Correct by construction — it removes the
  wrong answer by removing the answer. *Cost:* loses already-applied detection for alters entirely, a feature
  in current use, and the deployment generator would then never see an ALTER at all.

**Recommendation (ADOPTED by the owner): key by statement text.** A wrong verdict is strictly worse than an
untidy table, and the no-migration property is what makes the fix deployable to sandboxes that already
exist — the other correct shape cannot reach them. The semantic split is real and should be *recorded* in
§18.5 rather than avoided: an ALTER genuinely is an event, and pretending otherwise is what produced this
bug.

**Unblocks (with DEC-008): BUG-044.** The two answers together are the whole precondition for that fix —
DEC-007 decides the new key, DEC-008 decides what happens to the rows written under the old one, and they
ship in **one commit**. BUG-044 is a **confirmed silent-wrong-result defect**: a false
`REASON_ALREADY_APPLIED` (`STATUS_PASSED`) for a statement the sandbox has never seen. Concretely unblocked:
`CheckRequest.working_set_name`, the `AlterDdlRef.working_set_name` property, the six new test cases listed
at `docs/BUGFIX_QUEUE.md:4036-4044`, and `spec-maintainer` restating §18.5 D2's working-set section
(~:6906-6931), which describes `applied` purely in terms of objects and predates FQ-025's ALTER buffers.

---

## DEC-008 — What happens to the `applied` rows already written under the colliding alter key?

- **Status:** ANSWERED (2026-08-10)
- **Answer:** **Delete the orphan rows once, at session open**, scoped to the **old empty-name key shape** —
  `DELETE FROM pgtp_editor_sandbox.applied WHERE kind = 'alter' AND object_name = ''`. Ships **with**
  DEC-007's fix, in the same commit.
- **Scoping is a requirement, not a caution.** The delete must be scoped **precisely enough that it is
  provably incapable of touching object rows** — both predicates, `kind = 'alter'` **and**
  `object_name = ''`, and a test that pins it. This is not "be careful"; it is the condition on which the
  answer was given.
- **Owner's reasoning:** same as DEC-007 — those rows can only ever produce a **wrong answer or no answer,
  never a right one**, so **nothing of value is lost** by deleting them. Deleting also **removes the
  standing dependency** on a "no reader constructs the old key" claim holding true forever as the code
  changes around it — the "leave them" option's safety rests entirely on that claim staying true, which is
  a fragile thing to bet correctness on.
- **Why the orphans exist at all — record this, it is the non-obvious part.** `SandboxSession.reset()`
  **deliberately spares** the bookkeeping schema (`pgtp_editor/db/sandbox.py:1050-1067`). So an orphan
  otherwise **survives a reset** and keeps answering *"already applied"* for a sandbox that no longer holds
  the change. The rows are not merely inert clutter; sparing bookkeeping on reset is what turns them into a
  live source of wrong answers.
- **SHIPPED (verified 2026-08-10, sweep).** Landed with DEC-007 in **BUG-044's fix** (`1c28d33` / fix
  commit `ffbc377`), in the one commit this answer required. Nothing pending.
- **Supersedes:** DEC-005's withdrawn cleanup concern is subsumed here.
- **Unblocks (with DEC-007): BUG-044** — the migration/cleanup half of the fix, so it lands in the same
  commit as the new key and leaves no window in which stale rows are still consulted.

**Context.** Whatever DEC-007 decides, the rows already written under the key `("alter", schema, "", table)`
will match no future request. They become inert orphans that read as "not in working set" — honest, since they
cannot be attributed to any statement. But `SandboxSession.reset()` **deliberately spares** the bookkeeping
schema (`pgtp_editor/db/sandbox.py:1050-1067`), so they also survive a sandbox reset: an orphan can keep
answering for a sandbox that no longer holds the change.

**The interaction that makes this not merely cosmetic:** if the orphans are left **and** anything still reads
the old key shape, the original wrong-verdict bug survives the fix. Under the recommended DEC-007 option
nothing does — `working_set_ref` would never again produce an empty `object_name` for an alter — but that claim
must be **verified in the implementation**, not assumed, before "leave them" is safe.

**Options.**
- **Leave them.** No destructive operation against user data, no new code path. *Cost:* dead rows accumulate
  forever in every existing sandbox, and the safety of leaving them rests entirely on the verification above.
- **Delete them once, at session open** (`DELETE FROM pgtp_editor_sandbox.applied WHERE kind = 'alter' AND
  object_name = ''`). Clean; guarantees the old key shape cannot answer anything regardless of what still reads
  it. *Cost:* a destructive one-off against user data, executed silently at open, with no undo — and the
  predicate must be exactly right or it deletes live rows.

**Recommendation (ADOPTED by the owner): delete them at session open,** on the same reasoning as DEC-007 —
the rows can only ever produce a wrong answer or no answer, never a right one, so there is nothing to
preserve, and deleting removes the dependency on a verification claim holding true forever as the code
changes around it. If you prefer to leave them, the fix must carry an explicit test that no reader can still
construct the empty-`object_name` alter key.

**Unblocks:** the migration/cleanup half of BUG-044's fix, so it can ship in one commit rather than leaving a
window in which stale rows are still consulted.

---

## DEC-009 — Does DEC-004's ruling extend to the `Ctrl+Alt+` editor-gesture family?

- **Status:** ANSWERED (2026-08-10)
- **Answer:** **Keep the family as a documented widget-only category — decided now, not deferred.** Keep
  `Ctrl+Alt+E`, `Ctrl+Alt+C`, `Ctrl+Alt+F`, `Ctrl+Alt+J` and `Ctrl+Space` hosted in their widgets; keep
  `RESERVED_SEQUENCES` (`shortcut_registry.py:233-244`) and the manual's non-rebindable list **as they
  are**; and **rewrite the misleading offscreen comments** at the widget sites to state the real *product*
  reason instead. Do **not** convert them to `QShortcut`s.
- **Owner's reasoning:** DEC-004's defect was **two hosts for one gesture**, not "a widget handles a key".
  These gestures have **no menu entry**, so they are widget *behaviours* — like auto-close brackets — and
  hosting them in the widget is a legitimate product decision, not a harness artefact. `Ctrl+Alt+J` and
  `Ctrl+Space` already have **independent product reasons** (`Ctrl+Alt+J` needs a `SchemaIndex`, which no
  editor widget may hold, §18.5 D1; completion is intrinsically a widget behaviour). The offscreen sentence
  in those comments is a **bad justification for a defensible design** — a *documentation* defect, not a
  design one — so the fix is to correct the justification, not the design.
- **SHIPPED (verified 2026-08-10, sweep).** The comment rewrite this answer mandated is **BUG-052,
  RESOLVED (`f533350`)**: the offscreen sentence is gone from `sql_console_panel.py`, `code_editor.py`
  and `ddl_object_editor.py`, replaced by the product reason (see `sql_console_panel.py:507-513`,
  `ddl_object_editor.py:909-917`). `RESERVED_SEQUENCES` and the manual's non-rebindable list are
  unchanged, as directed. **One site was out of BUG-052's scope and is NOT settled by this entry:
  `Ctrl+Alt+F`, which has a command form — see DEC-012.**
- **Wider principle:** DEC-004's rule ("the harness must not shape the product") bites only where the
  harness is the *only* reason a design exists. A widget-hosted gesture with no menu command has a standing
  product reason to live in the widget, so it is not in scope — but where a comment *cites the harness* for
  such a gesture, the comment is wrong and must be rewritten to the real reason, lest the next reader read a
  defensible design as the very defect DEC-004 ruled against.

**Context.** DEC-004 ruled that `Ctrl+Shift+B` must be hosted as a normal shortcut, on the principle that
*a design existing to satisfy the test harness rather than the product means the harness should change*.
The **same offscreen justification is load-bearing for a whole family of gestures**, but the owner's ruling
named only `Ctrl+Shift+B`, so the family's status is genuinely undecided rather than implied.

The family, as it exists in the tree today:

- **`Ctrl+Alt+E`** (Expand Snippet) and **`Ctrl+Alt+C`** (Expand SELECT into its column list) — handled in
  `CodeEditor.keyPressEvent` (`pgtp_editor/ui/code_editor.py:773-788`), under a comment that states the
  reason outright: *"Handled in the widget rather than as QShortcuts for the same reason that one is handled
  twice: QShortcut activation is not reliable under the offscreen platform the tests run on."*
- **`Ctrl+Alt+F`** (Format Selection) and **`Ctrl+Alt+J`** (JOIN-on-FK) — handled in
  `DdlObjectEditor.eventFilter` (`pgtp_editor/ui/ddl_object_editor.py:887-896` and `:906-918`), not in
  `CodeEditor`. `Ctrl+Alt+J` is there because it needs a `SchemaIndex`, which no editor widget may hold
  (§18.5 D1) — a **product** reason, independent of the harness. `Ctrl+Space` (schema-aware completion) sits
  in the same filter with the harness reason spelled out at `:897-899`.
- All of them already have rows in `shortcut_registry.RESERVED_SEQUENCES`
  (`pgtp_editor/ui/shortcut_registry.py:233-244`), precisely so a rebound menu command cannot be retargeted
  onto a key a widget already answers to.

**How they differ from `Ctrl+Shift+B`, in the one way that may matter.** None of them has a menu entry at
all. `Ctrl+Shift+B` was *handled twice* — a `QAction` and a widget branch for the same gesture — which is
the shape the owner called a defect. These are **widget-only**, and a gesture with no menu command may
legitimately belong to the widget rather than the window: it is scoped to the widget that can perform it,
it needs no enable/disable logic tied to focus, and there is no second host to disagree with. Whether the
harness justification *written in the comments* is the real reason, or merely the reason someone wrote
down, is the crux.

**Options.**

- **Convert the family too — `QShortcut`s (widget-scoped) for all of them.** Consistent: one hosting
  mechanism for every chord in the product, and the DEC-004 principle applied without an exception that
  will need re-explaining. Makes them rebindable through **View ▸ Customize Shortcuts…** like everything
  else, which is arguably what a user expects. *Cost:* four gesture sites plus `Ctrl+Space` to convert
  across two files, each with existing tests that drive the key directly; `Ctrl+Alt+J` and `Ctrl+Space`
  live in an `eventFilter` that also handles `ShortcutOverride` to claim sequences from window-level
  shortcuts, so the conversion is not a like-for-like swap. And if `QShortcut` really does not activate
  offscreen, this trades working coverage for a fidelity loss across five gestures instead of one. Making
  them rebindable also means removing their `RESERVED_SEQUENCES` rows, which currently exist *because* they
  are widget-hosted — a user-visible change to what the shortcut dialog shows.
- **Keep widget-only gestures as a deliberate, documented category.** Draw the line where the owner's
  reasoning actually bit: the defect in `Ctrl+Shift+B` was **two hosts for one gesture**, not "a widget
  handles a key". A gesture with no menu command is a widget behaviour, like auto-close brackets or
  tab-stop walking, and hosting it in the widget is a product decision. *Cost:* the category must be
  **written down** — in the spec and in the code comments — with the *product* reason, and the misleading
  offscreen justifications currently in those comments must be rewritten, or the next reader concludes the
  same harness-shaped-the-product defect DEC-004 just ruled against. These gestures also stay
  non-rebindable, which is a real limitation the manual must keep stating.

**Recommendation (ADOPTED by the owner): keep them as a documented widget-only category, and rewrite the comments.** The principle
DEC-004 established is about *the harness shaping the product*, and for `Ctrl+Alt+J` and `Ctrl+Space` there
is already an independent product reason (`SchemaIndex` ownership; completion is intrinsically a widget
behaviour) — the offscreen sentence in those comments is a bad justification for a defensible design, which
is a documentation defect rather than a design one. Converting five gestures to buy consistency in a place
where no second host exists spends real risk on a cosmetic gain. **But this is the owner's call**, because
the alternative reading — that any product code path citing the harness must go, full stop — is a coherent
and stricter reading of the same principle, and the owner is the one who set its scope.

**Unblocks:** either (a) a conversion pass over `code_editor.py` and `ddl_object_editor.py` sized alongside
DEC-004's fix, or (b) a `spec-maintainer` pass recording "widget-only editor gestures" as a named category
with its product rationale, plus a comment rewrite at the four sites and confirmation that
`RESERVED_SEQUENCES` and the manual's non-rebindable list stay as they are.

---

## DEC-010 — Did FQ-026 retire §26's `Apply to Sandbox` / `Apply to Target Database…`, or do they survive as future work?

- **Status:** ANSWERED (2026-08-10)
- **Answer: retired.** §26 stands as it now reads — `spec-maintainer`'s strike is **confirmed, not
  reverted**. No code change; no spec change.
- **Owner's reasoning:** FQ-026's **one home per gesture** rule is recent, deliberate and the owner's
  own, and *a "future work" entry that contradicts a shipped rule is exactly the rot harmonization exists
  to remove*. The stated cost was **accepted, not overlooked**: a struck entry is harder to rediscover
  than a deferred one. It was accepted because if a database-centric route to these operations is
  genuinely wanted, it should be **re-raised through `feature-triage` stating why a second home earns its
  cost** — not inherited by default from a pre-FQ-026 spec.
- **What this entry is FOR, now that it is answered:** it is **the record of why those two §26 entries are
  gone**. That is precisely what the strike put at risk, and why `spec-maintainer` filed the decision
  instead of letting the edit pass as bookkeeping. A future reader who finds §26 silent on a Database
  route to the apply gestures should be sent here, not left to re-derive it.
- **Unblocks:** nothing was blocked (neither entry was ever built). §26 is confirmed as it stands.
- **Raised:** 2026-08-10, by `spec-maintainer`, while folding FQ-030 — it made the judgement, struck the
  entries, and filed this rather than letting the strike pass as bookkeeping.
- **Blocks:** nothing in code — **these two entries were never built**. It decides only what §26 *promises*,
  so the whole cost of a wrong answer is in what future work gets aimed at. It hardens as soon as anyone
  designs a Database-menu feature against §26 as it now reads.
- **Already actioned, so "survive" means reverting:** the strike is **in the spec now** (reported as commit
  `d1722f1`; verified present today at `CONSOLIDATED_SPEC.md:9376-9379`, `:9417`, `:9463`, and summarised in
  the harmonization note at `:32-34`).

**Context.** §26 (the Database menu) carried `Apply to Sandbox` and `Apply to Target Database…` as target
design at three sites, with a "disabled unless a DDL tab is active" posture. FQ-026 then established **one
home per gesture**: eight names collapsed to four operations, `Deployment` became the single apply
affordance, and the duplicate button row and context-menu entries were deleted. Both gestures ship today on
`Deployment`, as `Check and commit to sandbox` and `Apply to quality`.

`spec-maintainer` read FQ-026's rule as retiring the two Database entries and struck them at all three
sites, superseding the "disabled unless a DDL tab is active" posture by §18.5 carve-out 2 (build the reason
instead of the dead control). It offered instead to restore them with the contradiction flagged.

**Options.**
- **Retired — what the spec now says.** Two Database entries duplicating `Deployment` gestures are exactly
  the duplication FQ-026 deleted everywhere else. *Cost:* if the owner did intend a database-centric route
  to these operations — reaching them from the Database menu rather than from a DDL tab — that intent is now
  **erased** rather than **deferred**, and a struck entry is far harder to rediscover than a pending one.
- **Survive as future work.** The entries stay in §26 as unbuilt target design, annotated that when built
  they must not duplicate `Deployment`'s vocabulary. *Cost:* the spec then carries two entry points for
  operations FQ-026 just unified — the ghost-in-the-spec problem the harmonize pass exists to remove. The
  next person designing against §26 sees a Database route the shipped design says should not exist.

**Recommendation: retired**, as `spec-maintainer` judged. FQ-026's rule is recent, deliberate and
owner-driven, and a "future work" entry that contradicts a shipped rule is precisely the rot harmonization
removes. If a Database-menu route is genuinely wanted, it should be **re-raised through `feature-triage`**
stating why a second home is worth its cost — not inherited by default from a pre-FQ-026 spec.

**Unblocks:** either confirming §26 as it now stands (no work; this entry becomes the record of why the
entries are gone), or a `spec-maintainer` pass to restore them with the FQ-026 contradiction flagged.

---

## DEC-011 — Is panGen / rePHPgen (§20) meant to be Windows-only, or must it work on Linux too?

- **Status:** ANSWERED (2026-08-10)
- **Answer:** **Cross-platform.** `resolve_re_phpgen_python` learns **both** layouts —
  `venv/Scripts/python.exe` **and** `venv/bin/python` — and the fix **ships together with BUG-051**, as one
  fix rather than split into two.
- **Owner's reasoning:** re_phpgen is a **separate Python repo**, invoked as `python -m re_phpgen`, and has
  **no inherent Windows dependency** — unlike the vendor's `PgPHPGeneratorPro.exe`, which genuinely is a
  Windows binary. So the tempting argument *"the vendor is Windows-only, therefore §20 is"* **does not
  carry**, and it is recorded here as **explicitly rejected** so nobody re-derives it and reaches the
  opposite conclusion. The current behaviour was judged **the worst of the three options**: on Linux panGen
  silently runs under **the editor's own interpreter** and dies as a bare `panGen failed (exit N)` — a run
  that appears to start and names nothing.
- **Cost accepted:** the project is **now committed to keeping panGen working on Linux**, and **nothing
  currently exercises it there**. `tests/generation/test_re_runner.py:17-26` pins the Windows-only
  behaviour and is being **changed rather than extended**, with a **Linux-layout test added**.
- **Wider principle:** *a platform constraint belongs to the component that actually carries it, and does
  not propagate to its neighbours by association.* The vendor generator is a Windows executable; panGen is
  Python invoked as a module. Sharing a feature section (§20) does not make them share a platform scope —
  each component's scope is decided from its own dependencies. Corollary, consistent with DEC-007 and
  FQ-023: **a refusal that names its reason beats a run that starts and fails anonymously** — whichever
  scope had been chosen, today's silent-wrong-interpreter behaviour was not an acceptable third answer.
- **Unblocks: BUG-051**, and decides that it ships as **one** fix: the two-layout probe in
  `resolve_re_phpgen_python` bundled with the `DEFAULT_RE_PHPGEN_ROOT` removal, in a single commit (the
  splittable step 7 at `docs/BUGFIX_QUEUE.md:4942` is **not** taken). §20 also gains the explicit
  platform-scope sentence it lacks today — *panGen is cross-platform* — which is `spec-maintainer`'s to
  write, along with correcting `CONSOLIDATED_SPEC.md:9045-9046`, which currently documents the
  Windows-only layout (`<root>\venv\Scripts\python.exe` if present else `sys.executable`) **as the design**.
- **SHIPPED (verified 2026-08-10, sweep).** **BUG-051 is RESOLVED (`6454908`)** — as one fix, as this
  answer directed: `DEFAULT_RE_PHPGEN_ROOT` is deleted and `load_re_phpgen_root` returns `None` for every
  distinct failure. Nothing here is pending; what remains is `spec-maintainer`'s §20 platform-scope
  sentence, noted below.
- **Implementation detail as verified when the answer was given.**
  `pgtp_editor/generation/re_runner.py:43-51` now probes both layouts and its docstring names them; the
  root check `validate_re_phpgen_root` (`:63-65`) was already cross-platform (`Path(root) / "src" /
  "re_phpgen"`), so the spec's `src\re_phpgen` spelling at `:9046` is a **prose backslash only**, not a
  second Windows assumption in code. Read this entry as decided-and-being-built.
- **Raised:** 2026-08-10, by `bug-triager` while root-causing BUG-051 — it found the second Windows
  assumption in the same feature and flagged it rather than deciding the platform scope itself.
- **Blocks:** **BUG-051's fix shape.** That fix is written with the venv change bundled but explicitly
  splittable (`docs/BUGFIX_QUEUE.md:4942`, step 7). This answer decides whether BUG-051 ships as one fix or
  two, so it wants answering **before** BUG-051 is implemented, not after. Nothing else is blocked, but the
  assumption hardens with every further §20 change made without a stated scope.

**Context — all verified in the tree today.**

`pgtp_editor/generation/re_runner.py:43-46` resolves the interpreter panGen runs under:

```python
def resolve_re_phpgen_python(root: str) -> str:
    """The re_phpgen repo's venv python if present, else the editor's own."""
    venv_python = Path(root) / "venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.is_file() else sys.executable
```

`venv/Scripts/python.exe` is the **Windows** virtualenv layout. On Linux the runtime's real interpreter at
`venv/bin/python` is never considered, so the branch silently falls through to `sys.executable` — the
**editor's own** interpreter. If a re_phpgen dependency is absent there, the user gets a bare
`panGen failed (exit N)` naming nothing. It is used live at `pgtp_editor/ui/generation_controller.py:386`.

Confirmed alongside it:
- `CONSOLIDATED_SPEC.md:9045-9046` (§20) **documents** the Windows layout as the design
  (`<root>\venv\Scripts\python.exe` if present else `sys.executable`), and **§20 nowhere states a platform
  scope** for the feature as a whole.
- `tests/generation/test_re_runner.py:17-26` pins the current behaviour: one test creates
  `venv/Scripts/python.exe` and expects it, one expects the `sys.executable` fallback. There is **no test
  that exercises the Linux layout**, so nothing would catch it either way.
- This is the **second** Windows-only assumption in the same feature. The first is BUG-051 itself:
  `pgtp_editor/generation/config.py:81` ships `DEFAULT_RE_PHPGEN_ROOT = r"C:\Users\BotondZalai-RuzsicsP\…"`
  as the fallback root for every user.

Two independent Windows assumptions in one feature is either a deliberate platform scope nobody wrote down,
or drift from working only on Windows — and the fix differs completely depending on which.

**One fact that bears on it:** the **vendor** generator is intrinsically Windows (`PgPHPGeneratorPro.exe`,
spec `:516`), but **panGen/re_phpgen is a separate Python repo** invoked as `python -m re_phpgen` — it has
no inherent Windows dependency. So "the vendor is Windows-only" does not by itself settle §20. `CLAUDE.md`
states development happens on **both Windows and Linux**, which is what makes this a real question.

**Options.**

- **Windows-only, stated.** Drop the venv fix; have §20 say plainly that panGen requires Windows, and make
  the four Generation actions **refuse with that reason** on other platforms. *Cost:* a documented
  capability gap on the platform this checkout runs on, and a narrowing of the product — which should be a
  decision, not the description of an accident. It is still strictly better than today (a clear refusal
  beats a silent wrong interpreter), but it forecloses Linux use of the feature.
- **Cross-platform, fixed.** `resolve_re_phpgen_python` learns both layouts — `venv/Scripts/python.exe` and
  `venv/bin/python`. *Cost:* small and mechanical, but it commits the project to keeping panGen working on
  Linux, which means it must be exercised there; nothing currently does, and the existing tests would need
  a Linux-layout case added.
- **Leave it.** *Cost:* the silent-wrong-interpreter behaviour stays, and it fails in the worst available
  way — not a refusal, but a run that appears to start and dies with an exit code that names nothing.
  **Recommend against**; whichever scope is chosen, today's behaviour is not it.

**Recommendation: decide the scope explicitly, and make the code say it.** If the answer is Windows-only,
it must appear **in §20 and in the refusal the user sees**, because the current behaviour is neither
Windows-only nor cross-platform. Between the two real options I lean **cross-platform**: it is the smaller
change and matches a project developed on both platforms. But only the owner knows whether panGen is meant
to run outside Windows at all.

**Unblocks:** BUG-051 gets implemented as one fix (cross-platform: bundle the two-layout probe with the
`DEFAULT_RE_PHPGEN_ROOT` removal) or two (Windows-only: ship the config fix alone and route the platform
refusal + §20 scope statement through `spec-maintainer` and `feature-triage`). Either way §20 gains an
explicit platform-scope sentence it does not have today.

---

## DEC-012 — `Ctrl+Alt+F` has a `QShortcut` **and** an `eventFilter` branch in the DDL object tab: is a context-menu command a "command" for DEC-004's one-host rule?

- **Status:** ANSWERED (2026-08-10)
- **Answer: option (A) — delete the duplicate.** The `QShortcut`
  (`pgtp_editor/ui/ddl_object_editor.py:786-790`) becomes the **only keyboard host**; the `eventFilter`
  `Key_F` branch (`:899-908`) goes. The **context-menu action (`:965`) stays** — it is a separate
  affordance, not a duplicate host.
- **Owner's reasoning:** the duplication has **no surviving justification** — both stated reasons are now
  known false (the offscreen premise was measured false by BUG-046; the `CodeEditorDialog` precedent it
  cites was deleted by BUG-046) — and the **single-host shape for this exact gesture already ships** in
  `SqlConsolePanel` with the same scope and the same selection gate. So this is **applying DEC-004 as
  written, not carving an exception into it**. Option (C) was **rejected as tidier-sounding but empty**:
  even inside DEC-009's family the rule is one host, so the branch goes either way.
- **WIDER PRINCIPLE — the durable part, and it settles a case §8 is currently silent on:**

  > **Any gesture with a command form — menu bar *or* context menu — has exactly one keyboard host.**

  DEC-009's carve-out is unchanged and is **narrower than it may read**: it covers gestures with **no
  command form at all** (`Ctrl+Alt+E`, `Ctrl+Alt+C`, `Ctrl+Alt+J`, `Ctrl+Space`). A context-menu entry is
  a command. Anyone tempted to extend DEC-009 to a gesture that appears on *any* menu is reading it wider
  than the owner drew it.
- **Implementation note, carried forward so it is not lost.**
  `tests/ui/test_ddl_object_editor.py:577` (`test_shortcut_override_claims_ctrl_alt_f`) drives the filter
  directly and must be **rewritten to a real key click on a shown widget — not deleted**; deleting it
  leaves the gesture with **no keyboard coverage at all**. And the key must be sent to
  **`window.windowHandle()`**: `qtbot.keyClick(widget, …)` bypasses `QShortcutMap` and would prove
  nothing about whether the chord is bound.
- **Unblocks:** **BUG-054** (delete `:899-908`, rewrite the dead comment at `:781-785`, rework that test;
  `RESERVED_SEQUENCES` is untouched — `Ctrl+Alt+F`'s row stays), and a **`spec-maintainer`** pass adding
  the context-menu case to §8, which today distinguishes only *no menu command* from *menu-bar command*.
- **Raised:** 2026-08-10, by `bug-triager` as BUG-054 (found while verifying BUG-052's fix at `f533350`;
  not filed by the user). Filed here rather than fixed in the bug queue because it is a live DEC-004
  question and the answer may change behaviour.
- **Blocks:** yes — **BUG-054 (OPEN)** cannot be implemented until this is settled; the entry states both
  branches of the fix and stops at the decision. It also governs every **future context-menu-only
  gesture**, which is why the answer is wider than one chord.

**Context — every fact below verified in the tree today (`main` at `6280025`).**

`Ctrl+Alt+F` (Format Selection) is answered in **three** places for the one `DdlObjectEditorPanel`:

1. `pgtp_editor/ui/ddl_object_editor.py:786-790` — `QShortcut(QKeySequence("Ctrl+Alt+F"), self)` at
   `WidgetWithChildrenShortcut` scope, `activated → format_selection`, and `setEnabled(False)` until a
   selection exists (`_update_format_shortcut_enabled`, `:987-988`).
2. `ddl_object_editor.py:899-908` — an `eventFilter` branch on `Key_F` + `Control|Alt` that claims
   `ShortcutOverride` and calls `format_selection()` on `KeyPress`. **Unconditional** — no selection gate.
3. `ddl_object_editor.py:965` — `menu.addAction("Format Selection", self.format_selection)` in the
   editor's context menu, enabled only with a selection.

Host 3 is a separate affordance and is not at issue. **Hosts 1 and 2 are the duplication.**

**Why DEC-009's carve-out does not cover it.** DEC-009 kept `Ctrl+Alt+E` / `Ctrl+Alt+C` / `Ctrl+Alt+J` /
`Ctrl+Space` widget-hosted *because they have no command form at all* — no second host to disagree with.
`Ctrl+Alt+F` **does** have a command form (the context-menu action), which puts it inside DEC-004's rule
that a gesture with a command has exactly one host. `shortcut_registry.py:236-238` already records it as
*"a context-menu command plus a shortcut … there is no menu-bar action to move"* — i.e. the code already
knows this one sits on the line.

**The precedent in the same codebase.** `SqlConsolePanel` hosts the *same* gesture with the `QShortcut`
alone (`pgtp_editor/ui/sql_console_panel.py:538-544`, same scope, same `setEnabled(False)` selection
gate) and has **no `eventFilter` at all**. So single-hosting this gesture is already shipped and working
elsewhere; the DDL object tab is the outlier.

**The recorded justification is false.** `ddl_object_editor.py:781-785` still reads *"The redundant
eventFilter branch below handles the key directly too, mirroring `CodeEditorDialog`'s Ctrl+S/Ctrl+W
convention — QShortcut activation is not reliable under the offscreen platform in tests."* Both halves
are dead: BUG-046 measured the offscreen premise false (`code_editor.py:742-752` — shortcuts *do*
activate offscreen; what fails is key delivery to a widget never `show()`n), and BUG-046 (`e8df6c3`)
**deleted** the `CodeEditorDialog` double-hosting the comment cites as precedent. `CodeEditorDialog` now
answers neither `Ctrl+S` nor `Ctrl+W` (`manual.md:3902`).

**One thing that is NOT a decision, checked so the owner does not have to weigh it.** BUG-054 warns that
the two hosts behave differently without a selection. They do — but the difference is **invisible**:
`format_selection` (`ddl_object_editor.py:993-1000`) opens with `if not cursor.hasSelection(): return`,
a silent no-op. It is *not* the §18.5 carve-out 4 refusal path (that is for unformattable SQL). So a
selection-less `Ctrl+Alt+F` does nothing today via host 2, and would do nothing via host 1 alone. There
is no user-visible behaviour change hiding in this, and no FQ-023-style "state the reason" question.

**Options.**

- **(A) Single-host it: delete the `eventFilter` `Key_F` branch, leave the `QShortcut`.** Matches
  `SqlConsolePanel` exactly, applies DEC-004 without an exception, and removes a comment that now cites
  two deleted premises. *Cost:* the test `tests/ui/test_ddl_object_editor.py:577`
  (`test_shortcut_override_claims_ctrl_alt_f`) drives `ShortcutOverride` at the filter directly and would
  have to be rewritten to a shown-widget `QTest.keyClick`, not deleted — otherwise the gesture loses its
  only keyboard coverage. `test_ctrl_alt_f_triggers_format_selection` (`:342`) already uses a real
  `QTest.keyClick`, but which of the two hosts is answering it today is unverified, so the implementer
  must confirm it still passes on the `QShortcut` alone rather than assume it.
- **(B) Keep both, and write an honest reason.** Zero behavioural risk, no test churn. *Cost:* it makes
  DEC-004's one-host rule carry a **stated exception**, and that exception needs a real product reason —
  the two available ones are now known false, and "it works" is not one. It also leaves the object tab
  and the console hosting the same gesture two different ways, which is the drift the harmonize pass
  exists to remove.
- **(C) Rule that a context-menu command is not a "command" for DEC-004's purposes, so `Ctrl+Alt+F`
  joins DEC-009's widget-only family.** Consistent as a *rule*, and it answers the general case for
  every future context-menu-only gesture in one stroke. *Cost:* it would license widget-hosting for
  gestures that visibly *are* commands (they appear on a menu with a label), and it still does not
  justify **two** hosts — even inside DEC-009's family, the rule is one host, so the console would then
  be the wrong one and (A)'s deletion happens anyway, just under a different banner.

**Recommendation: (A), with the general rule stated as "any gesture with a command form — menu bar or
context menu — has exactly one keyboard host."** The duplication has no surviving justification, the
single-host shape for this exact gesture is already shipped in `SqlConsolePanel`, and the change is one
branch plus one test rewrite. (C) is the tempting rule because it is tidy, but it buys nothing here:
even under (C) the second host must go.

**Unblocks:** BUG-054's fix (delete `:899-908`, rewrite `:781-785`, rework
`test_shortcut_override_claims_ctrl_alt_f` to a real key click, add nothing to `RESERVED_SEQUENCES` —
`Ctrl+Alt+F`'s row stays either way), and a `spec-maintainer` pass adding the context-menu-command case
to §8's DEC-009 rule, which today distinguishes only *no menu command* from *menu-bar command* and is
silent on the middle case.
