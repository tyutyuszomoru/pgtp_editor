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

---

## DEC-013 — Where must a refusal appear: is the journal enough, or must it reach a surface the user is already looking at?

- **Status:** ANSWERED (2026-08-10)
- **Answer: option (C) — tier it by kind.** Keystroke-answering refusals get the immediate surface;
  background and non-gesture notices stay journal-only.
- **The boundary, verbatim — this is the durable part of the answer, and (C) decays back into today's
  three-way inconsistency without it:**

  > **did the user just press a key and get declined?**
  > **YES → tooltip at the caret + Audit row**
  > **NO → journal only**

  **The test is the user's action** — not the severity of the reason, and not which subsystem raised it. A
  refusal that answers a keystroke is immediate; anything the app decided on its own is a notice. A future
  call site classifies itself by asking that one question.
- **Owner's reasoning: this extends a mechanism rather than inventing one.**
  `CodeEditor.report_refusal` → `show_hint(..., refusal=True)` (`code_editor.py:596-625`) already ships
  exactly this tiering for editor gestures, and its docstring argues the case: *"a dock row alone would make
  a Ctrl+Alt+E that matched no snippet look like nothing happened; a tooltip alone would vanish before it
  could be re-read."* Both blanket rules were rejected **for stated reasons**: **(A)** leaves a declined
  keystroke silent, which is the failure FQ-023 exists to prevent, and consistency under (A) would argue for
  **quietening** the two implementations that already work; **(B)** has no answer for a refusal with no caret
  to anchor a tooltip to.
- **Wider principle — judged to be real, and wider than refusals.** The owner's reasoning does establish
  one, and the `report_refusal` docstring is its evidence from both ends:

  > **Feedback belongs where the action happened; the record belongs in the journal; the two are not
  > substitutes.**

  What that forbids concretely: a call site picking one surface **instead of** the other (the immediate hint
  does not excuse the missing Audit row, and the Audit row does not excuse the missing hint), and any rule
  that decides immediacy by **severity** or by **which subsystem spoke**. Only *did the user just act?*
  selects the tier.
- **Carry-forward, all three unchanged by this answer.**
  1. **FQ-028 is untouched.** The status bar stays closed as a message board. This chose between the
     **journal** and the **at-the-caret hint** — never the status bar.
  2. **The ~15-site change is NEW SURFACE.** It routes through **`feature-triage`** (foreground) into
     `docs/FEATURE_QUEUE.md`, not straight into the spec.
  3. **`spec-maintainer` owes §7 and §18.5 a restatement, and the distinction matters.** Those sections
     currently present the *"reach a surface the user is looking at"* rule as **settled design when it was a
     proposal**. It is now settled — but as **(C), tiered**, *not* as the unconditional rule those sections
     describe. Restating it as unconditional would be a second overstatement replacing the first.
- **Note for whoever implements it (a stale docstring the fix will likely rewrite anyway):**
  `MainWindow._report_gesture_unavailable`'s docstring still reads *"State why a gesture cannot run, in the
  Audit panel and on the status bar"* (`pgtp_editor/ui/main_window.py:6416`) — the status bar has not been a
  surface since FQ-028.
- **Unblocks:** **BUG-055's remaining scope** (OPEN with a withdrawn plan) can now be re-scoped: classify the
  ~15 `showMessage` refusal sites against the boundary above, route the keystroke-answering ones through
  `report_refusal`/`show_hint` **plus** their Audit row, and leave the rest journal-only. And
  `spec-maintainer`'s §7 / §18.5 restatement per carry-forward 3.
- **Raised:** 2026-08-10, by `bug-triager` from **BUG-055**, which established that the bug's original
  premise (that these refusals are lost) is **false**, and that what remains is genuinely the owner's call
  rather than a defect to fix.
- **Blocks:** **BUG-055's remaining scope** — the entry is OPEN with its implementation plan withdrawn, and
  cannot be re-scoped until this is settled. It also blocks a **`spec-maintainer`** correction: §7 and §18.5
  currently carry the "reach a surface the user is looking at" rule **as settled design when it is only a
  proposal** (that overstatement is being corrected in parallel; this decides what the corrected text says).

**Context — all facts verified in the tree today.**

FQ-028 closed the status bar as a message board, by owner ruling. `StaticStatusBar.showMessage` does not
paint; it **journals** (`pgtp_editor/ui/status_bar.py:131-136`). Nothing is lost: `showMessage` →
`notice_sink` → `MainWindow._record_notice` (`main_window.py:642`, `:2179`) → `record_activity`
(`:1764`) → the Activity Log tab, where the row appears immediately.

So the refusals that route this way are **journal-only, not surface-less**. The open question is whether
that is enough. The row may land on a non-current tab or in a hidden dock with nothing revealing it, so a
user who presses a key and is declined can see **no response at all**, while the reason is faithfully
recorded. (For scale: 38 `showMessage` call sites across `pgtp_editor/ui/`; BUG-055 identifies roughly
fifteen of them as refusals.)

**Why this is unsettled rather than simply wrong.** FQ-023 established that a gesture must **state why** it
is unavailable rather than vanishing — but it says *why*, not *where*. Its own reference implementations
disagree with each other, and all three ship:

1. `MainWindow._report_gesture_unavailable` (`main_window.py:6415-6428`) — dual-routes: a `[Check]` line
   **plus** the journal. The `[Check]` line's destination constant is `TO_RESULTS`
   (`audit_router.py:135`, `CHECK_PREFIX: TO_RESULTS`), which is the bottom dock tab **titled `Messages`**
   in the UI (`audit_router.py:116-119`). So this refusal is visible on the **Messages** tab — a surface,
   not a results grid.
2. `MainWindow._refuse_sandbox_gesture` (`main_window.py:5750`) — raises a **`QMessageBox`** with an
   `Open` button.
3. The remaining ~15 — **journal only**.

That three-way inconsistency is the thing to settle.

> **Corrected 2026-08-10 (fact, not scope).** As first filed, this entry said implementation 1 "routes to
> Results, not Messages". That was wrong in the way that matters here: `TO_RESULTS` is the **identifier**,
> and the tab it names has been **titled `Messages`** since the FQ-028 title collided with the Sandbox SQL
> Console's genuine results grid — the identifier deliberately kept its old spelling, because "a label is
> not a schema" (`audit_router.py:116-119`). One surface, two names. Read the old wording literally and you
> would think one of the three implementations targeted a different surface than it does, in a decision
> that is entirely about *where a refusal appears*. This is the **same one-surface-two-names confusion that
> produced BUG-042**, tripped over again while documenting that bug's aftermath — so whenever `TO_RESULTS`
> is cited anywhere, name the tab title alongside it. Status, options, recommendation and the FQ-028
> boundary are unchanged by this correction.

**A fourth mechanism already exists and is the natural home for the "immediate" answer:**
`CodeEditor.report_refusal` (`code_editor.py:596-610`) → `show_hint(..., refusal=True)` (`:612-625`) — a
transient tooltip **at the caret**, plus an `expansion_refused` signal that files an Audit row. Its
docstring already argues this decision's case in miniature: *"a dock row alone would make a Ctrl+Alt+E that
matched no snippet look like nothing happened; a tooltip alone would vanish before it could be re-read."*

**Options.**

- **(A) The journal is enough.** No code change; FQ-028's ruling stands untouched and the Activity Log is
  the single place reasons live. *Cost:* a declined keystroke can produce no visible response at all —
  the exact failure FQ-023 exists to prevent. It also makes the two louder implementations (1 and 2 above)
  the anomalies, so consistency would argue for quietening them, which is a behaviour regression nobody has
  asked for.
- **(B) A refusal must reach a surface the user is already looking at.** The rule `spec-maintainer` drafted:
  immediate feedback at the point of action, via `report_refusal` / `show_hint` for editor gestures.
  *Cost:* changes ~15 shipped refusals — that is a **feature**, not a correction, and routes through
  `feature-triage`. It also needs a stated answer for refusals raised where **there is no caret to anchor a
  tooltip to** (project-level and background gestures), which the option as drafted does not supply.
- **(C) Tier it by kind.** Keystroke-answering refusals get the immediate surface; background and
  non-gesture notices stay journal-only. *Cost:* someone must classify all ~15, and the boundary must be
  stated well enough that a **future** call site knows which side it is on. An unclear rule here recreates
  exactly today's three-way inconsistency, one call site at a time.

**Recommendation (ADOPTED by the owner): (C).** The distinction the code is already groping toward is *did the user just do
something and get declined?* — which is precisely when silence is wrong, and precisely when a caret exists
to anchor a hint to. A blanket rule in either direction either leaves keystrokes silent (A) or turns
routine notices into interruptions (B).

**Boundary, whichever is chosen: this must not reopen FQ-028.** The status bar stays closed as a message
board. This decides between the **journal** and the **at-the-caret hint** — not between the journal and the
status bar.

**Unblocks:** BUG-055's remaining scope (currently OPEN with a withdrawn plan retained), and a
`spec-maintainer` pass restating §7 and §18.5 to say what was actually decided instead of presenting the
proposal as settled design. If the answer is (B) or (C), the ~15-site change is **new surface** and goes
through **`feature-triage`** (foreground) into `docs/FEATURE_QUEUE.md`, not straight into the spec.

---

## DEC-014 — Must every surface that claims `Ctrl+Z`/`Ctrl+Y` also claim `Ctrl+Shift+Z`, or is `PhpFileTab` correctly excluded?

> **CAUTION (2026-08-10, added after this entry was answered) — the INVARIANT stands; the WORKED EXAMPLE has
> been RE-RULED by DEC-015.** Minutes after this was answered the owner said `Ctrl+Z` and `Ctrl+Shift+Z` are
> *"totally different"* and that `Ctrl+Shift+Z` should be the **counterpart of `Ctrl+Shift+A`** (shrink the
> structural selection), not a second redo chord. **DEC-015 is now ANSWERED (2026-08-10):** *"Redo is always,
> on all systems Ctrl+Y"* — `Ctrl+Y` explicitly bound on every platform, `Ctrl+Shift+Z` freed from redo. So
> this is **settled, not contested**.
>
> - **Unaffected — read this entry's answer as written.** The invariant — *"for every chord
>   `RESERVED_SEQUENCES` reserves because an editor answers it, every editing surface states its answer"* — is
>   about **reserved chords generally**, sourced from the registry rather than any literal chord list.
>   `Ctrl+Shift+Z` remains reserved and every surface must still state its answer; **only the answer changes,
>   from "redo" to "not redo; this is shrink"** — and each surface must keep actively intercepting the chord,
>   because Qt's binding table carries it as native `Redo` under `KB_Win | KB_X11`.
> - **Simplified, not weakened:** with redo down to a single chord the set is symmetric across the two
>   operations, so the classify-not-boolean constraint holds with one less member on the redo side. This entry's
>   *"the undo/redo chords"* phrasing now means `Ctrl+Z` and `Ctrl+Y`.
> - **`Alt+Backspace` / `Alt+Shift+Backspace` remains the open implementation call** this answer flagged, and
>   DEC-015 sharpens it: under *"a chord is bound by this app, not inherited from Qt's platform table"*, a
>   native Qt undo/redo chord left unclaimed is the same defect as Linux's missing `Ctrl+Y`.
> - **BUG-056's hold is LIFTED; the bug is RESCOPED** to *bind `Ctrl+Y` explicitly on all platforms*. Its
>   **step 2 (adding `Ctrl+Shift+Z` redo branches to `PhpFileTab`) is WITHDRAWN** by DEC-015. Its step 4 shared
>   matcher survives unchanged in principle.
> - **DEC-014 is not reopened.** Its answer stands as given; DEC-015 rules on what the chord *means*.

- **Status:** ANSWERED (2026-08-10)
- **Raised:** 2026-08-10, by `spec-maintainer`'s placement gate, which found the spec contradicting **itself**
  on this and refused to pick a winner rather than editing one side away as bookkeeping.
- **Blocks:** yes, and with a deadline. It decides the **data shape** of the keyboard-hosting feature the
  placement gate just recommended (EXTEND §8): if the rule is *"the three chords"*, the shared thing is a
  **fixed set**; if it is *"the chords this surface opted into"*, the shared thing is **parameterised**. That
  cannot be deferred past design. **And BUG-056 is OPEN with a proposed fix whose step 2 adds the
  `Ctrl+Shift+Z` branch to `PhpFileTab` and whose step 4 proposes the shared matcher** — so if the bug queue
  is resolved before this is answered, the rule gets settled by implementation, one surface at a time,
  without ever being stated. Answer it **before** BUG-056 is implemented, not after.

**The contradiction — both sides are current body text, verified in the tree today.**

- **The rule.** A Supersession Ledger row (2026-08-10, commits `e8df6c3`/`f533350`,
  `CONSOLIDATED_SPEC.md:10331`) closes with: *"wherever a surface claims `Ctrl+Z`/`Ctrl+Y` it must claim
  `Ctrl+Shift+Z` too."* The same rule is stated **again in §18.5 carve-out 1's body**
  (`CONSOLIDATED_SPEC.md:6499-6503`): *"**`Ctrl+Shift+Z` is part of the claim, not a separate chord.**
  Wherever a surface matches `Ctrl+Z` / `Ctrl+Y` it must match the second redo chord too."* That same
  carve-out's surface table lists **PHP file tab | yes | the same `eventFilter` shape** (`:6489`) — so by its
  own rule the PHP tab owes the third chord.
- **The exception.** §27's `Ctrl+Shift+Z` row (`CONSOLIDATED_SPEC.md:10019`) says the opposite for that very
  surface: *"**It is dead on `PhpFileTab`, the Sandbox SQL Console and `CodeEditorDialog`**, which is what
  the manual says."*
- **The code agrees with §27's exclusion, not with the rule.** `PhpFileTab.eventFilter`
  (`pgtp_editor/ui/php_file_tab.py:396-399`) matches `Ctrl+Z` and `Ctrl+Y` only:

  ```python
  if ctrl and key == Qt.Key.Key_Z:
      handler = self.editor.undo
  elif ctrl and key == Qt.Key.Key_Y:
      handler = self.editor.redo
  ```

  Two body sections asserting opposite rules about the same surface is the spec **contradicting itself**, not
  being stale — there is no later-wins reading that disposes of one.

**One measured fact that reframes the question, so it is not answered as the wrong one.** BUG-056
(`docs/BUGFIX_QUEUE.md:5578`, OPEN) measured the behaviour and §27's *"dead on `PhpFileTab`"* claim is
**false**: `Ctrl+Shift+Z` **redoes a PHP tab natively on both platforms**, because `QPlainTextEdit`'s own
`StandardKey.Redo` handling answers it and the compiled Qt binding table carries `Ctrl+Shift+Z` under
`KB_Win | KB_X11` (BUG-056 M1–M4). So the question is **not** *"should the PHP tab answer this chord"* — it
already does. It is *"must the surface **state** that it answers it, or may it leave the answer to Qt's
platform table?"*

**The platform dimension, which is the strongest argument in the whole entry.** BUG-056 also measured
`Ctrl+Y` to be **`KB_Win`-only** — it is not a redo chord on Linux at all. That is why `Ctrl+Y` is a **dead
key in the Sandbox SQL Console on Linux** and works on Windows from the same source: the console claims no
undo/redo chord, so on Linux the key falls through to `MainWindow`'s window-level `Ctrl+Y` `QShortcut`, which
returns immediately because the tab is not Raw XML (BUG-048's scoping) — *"no redo, no refusal, no journal
line"*. So *"claim all three everywhere"* is not tidiness: **explicit claiming is what makes the app's answer
platform-independent and stated**, and leaving chords to Qt is what produced the one real divergence found.

**And a fact that cuts the other way, so the fixed set is not mistaken for a closed one.** Qt's Windows
scheme also binds **`Alt+Backspace` (native Undo)** and **`Alt+Shift+Backspace` (native Redo)** on every
`CodeEditor`/`XmlEditor` (BUG-056's binding table). Neither is in `RESERVED_SEQUENCES` and neither is claimed
anywhere. So *"the three chords"* is a triple **Qt itself does not agree with**, and any rule phrased as a
literal triple is already incomplete on the day it is written.

**Options.**

- **(A) Fixed set — every text-editing surface claims the same undo/redo chords explicitly, and the shared
  matcher takes no per-surface parameter.** Makes the app's answer *stated* rather than derived from a
  platform table, which is exactly what closes BUG-056's console divergence; the shared thing is a plain
  function (`DdlEditorPanel._is_undo_redo_chord` is already its extracted form) and every new editing surface
  is correct by construction with one call. Also removes the §27-vs-§18.5 contradiction by deleting the
  exception. *Cost:* it hardcodes a set that is provably incomplete (the `Alt+Backspace` pair above), so the
  rule needs a stated source of truth for *which* chords rather than a literal three; and it forces the claim
  onto surfaces where nothing can steal the key anyway — `CodeEditorDialog` is a short-lived modal no window
  `QShortcut` can reach, so its claim buys only uniformity.
- **(B) Parameterised opt-in — the shared matcher takes the set of chords a given surface claims, and §27's
  per-surface table stays authoritative.** Honest about what ships today, needs no change to `PhpFileTab`,
  and lets a surface that genuinely wants Qt's native behaviour say so. *Cost:* per-surface variation is
  **precisely how BUG-053 happened** — the object editor answered a `RESERVED_SEQUENCES` chord differently
  from its read-only sibling — and this option institutionalises the variation instead of removing it. Every
  new surface becomes a fresh decision, and the app's answer to a reserved chord stays *"whatever this
  surface's author chose, plus whatever Qt decided on this platform."*
- **(C) Rule by hazard, not by chord set — a surface must claim every chord a window-level shortcut could
  steal, and may leave the rest to Qt.** The tightest rule on offer: it derives the requirement from the
  actual danger (§18.5 carve-out 1's real hazard is `MainWindow`'s window-scoped `Ctrl+Z` rewriting the Raw
  XML project buffer under a user looking at SQL), and it covers the console's `Ctrl+Y` case, which **is** a
  theft on Linux. Under this rule **`PhpFileTab` is correctly excluded and the Ledger row is the side that is
  wrong**: there is no window-level `Ctrl+Shift+Z` `QShortcut` at all (§27 states this outright), so nothing
  can steal that chord from any surface. *Cost:* the rule's input is the window's shortcut list, so **adding
  one window shortcut retroactively obliges every editing surface** — a coupling nothing in the code
  currently expresses or tests. It also leaves each surface's answer to the *unstolen* chords resting on Qt's
  platform table, which is the condition BUG-056 exists to end, and it re-opens the `Ctrl+Shift+Z` reservation's
  own justification (`shortcut_registry.py:220`), which reserves the chord *because widgets answer it*.

**Recommendation: (A), with the set sourced from `RESERVED_SEQUENCES` rather than written out as a literal
triple.** The invariant worth having is the one BUG-056 names — *for every chord the registry reserves
because an editor answers it, every editing surface states its answer* — which ties two artifacts that
already exist to each other instead of inventing a third list. That makes the shared thing a fixed set
**and** gives the `Alt+Backspace` pair a decidable home: either it enters `RESERVED_SEQUENCES` and is
claimed, or it is deliberately left out — a stated decision either way, which is what neither of the other
options produces. (C) is the more elegant rule and I want to record that it is genuinely arguable, but it
makes correctness depend on a window-level list nobody consults when adding a surface, and it leaves the
platform table as the app's answer of last resort.

**What an answer unblocks, concretely.**
1. The **§8 keyboard-hosting feature** the placement gate recommended can be designed: fixed-set matcher (A),
   parameterised matcher (B), or hazard-derived rule (C). This is the design input it is waiting on.
2. **`spec-maintainer`** removes the self-contradiction — either §27's *"dead on `PhpFileTab`…"* sentence
   goes (A/B: and it must go regardless, since BUG-056 measured it false as a *behaviour* claim), or §18.5
   carve-out 1's `:6499` rule and the `:10331` Ledger row are narrowed to what (C) actually requires.
   `owner-decision` does not edit the spec.
3. **BUG-056** gets a rule to implement against instead of a per-surface judgement — in particular whether
   its step 2 (`PhpFileTab` gains the branch) and step 4 (the shared matcher, currently written assuming a
   fixed three-chord set) are right as proposed.

### Answer (2026-08-10)

**Option (A) — fixed set, with the set sourced from `RESERVED_SEQUENCES` rather than written out as a literal
triple.**

**The invariant, verbatim — this is the durable part:**

> For every chord `RESERVED_SEQUENCES` reserves *because an editor answers it*, every editing surface states
> its answer.

**Owner's reasoning.** It ties two artifacts that already exist to each other instead of inventing a third
list, and it makes the app's answer **stated** rather than derived from Qt's platform table — which is the
condition BUG-056 exists to end. The shared matcher is therefore a plain function taking **no per-surface
parameter**.

**Constraint on the shared matcher — `Ctrl+Z` and `Ctrl+Shift+Z` are different operations.** `Ctrl+Z` is
**undo**; `Ctrl+Shift+Z` and `Ctrl+Y` are **redo**. The phrase *"the undo/redo chords"* used throughout this
entry treats them as one set, and the existing extracted form invites exactly that collapse:
`DdlEditorPanel._is_undo_redo_chord` returns a **bool** — *"is this one of the three?"* — which tells a caller
nothing about *which* operation to run.

> The fixed set governs **which chords a surface intercepts**. It does **not** unify what they do. The shared
> matcher must **classify** — undo versus redo — and never return a bare *"is an undo/redo chord"* boolean. A
> caller that trusts such a boolean and re-derives the operation itself is how a redo becomes an undo.

Not hypothetical: BUG-053's fix had to keep them apart explicitly, and the shipped code does
(`pgtp_editor/ui/ddl_object_editor.py:904-922`):

```python
is_undo = key == Qt.Key.Key_Z and mods == ctrl
is_redo = (key == Qt.Key.Key_Y and mods == ctrl) or (
    key == Qt.Key.Key_Z and mods == (ctrl | shift)
)
...
self.editor.undo() if is_undo else self.editor.redo()
```

Any extraction that flattens those two into one predicate loses the distinction the fix just established, and
the loss is **silent**: the chord is still claimed, so nothing looks broken, and the wrong operation runs.

**The platform wrinkle this interacts with, same subject.** `Ctrl+Y` is **Windows-only** in Qt's binding table
(BUG-056 measured this), so *redo* has two spellings of which one is platform-conditional while *undo* has
one. That asymmetry is a second reason the matcher must return the **operation** rather than a membership
test — the set is not symmetric across the two operations.

**Consequences, recorded explicitly.**

- **§27's `PhpFileTab` exception is deleted.** That also resolves the §18.5-vs-§27 body-vs-body contradiction
  **in §18.5's favour**. Note that §27's *"dead on `PhpFileTab`"* sentence had to go **regardless** of which
  option won, since BUG-056 measured it false as a behaviour claim.
- **The `Alt+Backspace` / `Alt+Shift+Backspace` pair now has a decidable home**: either it enters
  `RESERVED_SEQUENCES` and is claimed, or it is deliberately left out — a stated decision either way, which
  is what neither other option produced. This is a **required call during implementation**, not an open
  question to defer.
- **Accepted cost.** The claim is forced onto surfaces where nothing can steal the key — `CodeEditorDialog` is
  a short-lived modal no window `QShortcut` reaches, so its claim buys only uniformity. The owner accepted
  that.
- **Why (C) was rejected, though it is the more elegant rule** — *arguable and rejected*, recorded so it is
  not re-proposed later as an improvement: it makes correctness depend on a window-level shortcut list nobody
  consults when adding a surface, and it leaves unstolen chords resting on Qt's platform table.

**Unblocks.** **BUG-056**, including its **step 4 shared matcher**, which was assuming a fixed triple and now
has a sanctioned source for the set. The race recorded in this entry is **closed**: the rule was stated before
the implementation settled it, which is what this register exists to do.

**For `spec-maintainer`.** Both **§27** and **§18.5** need this fold, and §27's false behaviour claim
(*"dead on `PhpFileTab`, the Sandbox SQL Console and `CodeEditorDialog`"*) must be removed.

---

## DEC-015 — If `Ctrl+Shift+Z` becomes shrink-selection, what happens to redo's second spelling — and to redo on Linux, where `Ctrl+Y` does not exist?

- **Status:** ANSWERED (2026-08-10)
- **Raised:** 2026-08-10, by the main session, from three unprompted owner messages during BUG-056 work.
- **Blocks:** **BUG-056 (OPEN) is held on this** — its step 2 adds a `Ctrl+Shift+Z` redo branch to
  `PhpFileTab`, which would foreclose the reassignment by shipping it. It also contests **DEC-014**'s worked
  example (a CAUTION is recorded there; DEC-014's invariant survives untouched). And it settles **FQ-034's
  open question (1)**, the shrink chord, which is queued and undesigned.

**This entry reverses recorded design.** That is the cost, and it is the point of filing rather than deciding.

**What the owner said, verbatim, across three messages.**

> *"hey Ctrl+Z and Ctrl+shift+Z are totally different!"* · *"Ctrl+shift+Z is the counterpart of Ctrl+shift+A,
> Ctrl+Z is undo"* · *"(ctrlshiftA being the select incrementally the structures)"*

**The reading this entry rests on — stated as a reading, PENDING CONFIRMATION, not as settled.** `Ctrl+Shift+A`
grows the selection outward one structural level per press; the owner wants **`Ctrl+Shift+Z` as its inverse —
shrink the selection back inward** — and therefore **not** as a redo chord. `Ctrl+Z` remains undo; redo remains
`Ctrl+Y`. If that reading is wrong, everything below is moot and the entry closes.

**Current state, verified in the tree today (2026-08-10).**

- `pgtp_editor/ui/shortcut_registry.py:220` reserves the chord *as redo*:
  `"Ctrl+Shift+Z": "project history Redo, the second chord — answered inside every XML editor's own key
  handling…"`. Under the reassignment that reason string is **wrong**, not merely dated.
- `pgtp_editor/ui/main_window.py:2552` binds `Ctrl+Shift+B` → `Select Enclosing Block` (innermost);
  `:2556` binds `Ctrl+Shift+A` → `Select Parent Block` (one nesting level up).
- **`Ctrl+Shift+A` is XML-only today.** `_select_parent_block` (`main_window.py:2604-2616`) exists only for
  `XmlEditor`, and the menu entry is **hidden** on `CodeEditor` tabs — which also drops the chord there, since
  Qt keeps a shortcut live only while its action is enabled *and* visible. So *"select incrementally the
  structures"* describes **FQ-034's proposed SQL behaviour**, not shipped behaviour; today it is a single
  parent-walk in the XML editors, not a repeatable ladder.
- **No shrink / contract-selection operation exists anywhere.** Grep for shrink/contract/narrow-selection and
  an expansion stack across `pgtp_editor/` returns nothing in the selection code — the only hits are FQ-034's
  own queue text. The inverse the owner is naming has no implementation to rebind.
- `pgtp_editor/ui/ddl_object_editor.py:904-922` **answers `Ctrl+Shift+Z` as redo** (BUG-053, RESOLVED).
- Spec and manual both describe it as redo: `CONSOLIDATED_SPEC.md` §18.5 (`:6544` — *"`Ctrl+Shift+Z` is part
  of the claim, not a separate chord"*), §27 (`:10064`), plus the §27 Ledger row; and
  `pgtp_editor/resources/manual.md` at `:750`, `:1952`, `:3823`, `:3949`, `:4158` (*"Ctrl+Shift+Z is a second
  redo key"*).

**What the reassignment reverses — enumerated, because the cost IS the decision.**

- **BUG-050 (RESOLVED)** reserved the chord *as a redo chord*; its registry reason string becomes wrong.
- **BUG-053 (RESOLVED)** implemented it *as redo* in the DDL object tab. That implementation would be
  **withdrawn, not extended** — a resolved bug's fix partly undone.
- **DEC-014 (ANSWERED today)** used it as the worked example throughout. **The invariant survives** (it is
  sourced from `RESERVED_SEQUENCES` generally); the example does not, and the `Alt+Backspace` reasoning may
  shift, since if redo loses its second spelling the native Alt pair stops being a tidy-up and becomes the
  platform-coverage question itself.
- **BUG-056 (OPEN)** is built entirely on the redo reading; its step 2 adds a `Ctrl+Shift+Z` redo branch to
  `PhpFileTab`. **Held pending this.**
- **Spec §27 + §18.5 and five manual passages** would need refolding by `spec-maintainer` /
  `manual-maintainer`. Not touched here.

**The question is not "redo or shrink" — the owner has said. It is what happens to redo's SECOND SPELLING.**

**Options.**

- **(A) Redo becomes `Ctrl+Y` only.** Cleanest: one spelling per operation, the chord is freed for shrink, and
  the registry reason string becomes true again. *Cost, and it needs answering in the same breath:* `Ctrl+Y` is
  **`KB_Win`-only in Qt's compiled binding table** (BUG-056 measured this, M1–M4), so **on Linux redo would
  have no chord at all** unless one is explicitly bound. That is a live regression on the owner's own dev
  machine, and it is the same mechanism that already makes `Ctrl+Y` a dead key in the Sandbox SQL Console on
  Linux. Choosing (A) therefore also requires naming Linux's redo chord — or accepting that redo is
  Windows-only-by-keyboard.
- **(B) Redo keeps a second spelling under a different chord** (e.g. an explicitly bound alternate claimed by
  the same shared matcher on every surface). Preserves two-spelling redo and cross-platform coverage without
  contesting the owner's intent. *Cost:* the app invents a redo chord no platform convention supplies, so it
  must be discoverable — manual, `Select ▸`/menu surfacing, and `RESERVED_SEQUENCES` all have to carry it —
  and users' muscle memory for `Ctrl+Shift+Z` now does something visually dramatic (a selection jump) instead
  of nothing.
- **(C) Shrink takes a different chord; `Ctrl+Shift+Z` stays redo.** No reversal at all: BUG-050/BUG-053 stand,
  BUG-056 proceeds as written, spec and manual are untouched, DEC-014's example survives. *Cost:* it
  **contradicts the owner's stated intent** — recorded as an option so the trade is visible rather than assumed
  away — and it gives up the mnemonic pairing (`Ctrl+Shift+A` out / `Ctrl+Shift+Z` in) that motivated the
  request. Note FQ-034 already treats the shrink chord as open, so (C) costs nothing structurally; it costs
  only the pairing.

**Recommendation: (B), and only after the reading above is confirmed.** The reassignment itself is the owner's
to make and they have effectively made it; what should not be swallowed silently is the Linux consequence.
(A) is more elegant but its measured cost is *"redo has no keyboard on this machine"*, and discovering that
after the withdrawal of BUG-053's branch is the expensive order to discover it in. (C) is the cheapest in work
and the only option with zero reversal, which is exactly why it is recorded — but buying zero reversal by
overriding a clearly stated preference is not a trade an agent should make on the owner's behalf.

**A fact that shrinks the work considerably — the shrink feature is already queued.** Shrink-selection is new
surface (it does not exist today), so it would normally route through `feature-triage`; **it already has.**
`docs/FEATURE_QUEUE.md` **FQ-034** (QUEUED, 2026-08-10) is *"Structural expand-selection for plpgsql/SQL
editors — a repeatable Ctrl+Shift+A that grows the selection … plus a shrink counterpart"*, placed as EXTEND
§8 (the `Select ▸` menu and its keybindings) plus a new Qt-free span model in `sql/`, and it names FQ-032's
deferred motion/text-object work as a future consumer of the same span model. Its **open question (1) is
"exact default chord for shrink"**. So confirming this reading does not create a feature — it **answers
FQ-034's open question 1**, and the shrink operation is designed there, not here. This entry deliberately does
not design it.

**What an answer unblocks, concretely.**
1. **BUG-056** comes off hold — either implemented as written (C) or with step 2's `Ctrl+Shift+Z` branch
   removed and, under (A)/(B), a redo-chord decision folded in.
2. **FQ-034's open question 1** is settled, so its keybinding section can be designed.
3. **`spec-maintainer`** gets a ruling to fold into §27 and §18.5, and `manual-maintainer` a list of five
   manual passages to correct — or an explicit "no change", under (C).
4. **DEC-014's worked example** can be restated (its invariant needs no change).
5. Under (A)/(B), the **`shortcut_registry.py:220` reason string** is rewritten and BUG-053's redo branch in
   `ddl_object_editor.py:904-922` is withdrawn — work that must not start before this is answered.

### Answer (2026-08-10)

**Option (A) — one chord per operation, on every platform.** The reading this entry rests on is **confirmed**.

**The ruling, verbatim:**

> Redo is always, on all systems Ctrl+Y

So: **`Ctrl+Z` = undo. `Ctrl+Y` = redo, EXPLICITLY BOUND on every platform** rather than inherited from Qt's
platform table. **`Ctrl+Shift+Z` is freed from redo** and reserved for the shrink-selection counterpart to
`Ctrl+Shift+A`.

**Owner's reasoning — why this is a good trade and not merely a preference.** `Ctrl+Y` is **`KB_Win`-only** in
Qt's compiled binding table, which is *exactly the defect BUG-056 is open for* (dead redo key on Linux).
Binding `Ctrl+Y` explicitly on all platforms therefore **resolves that bug rather than adding work**, and it
makes redo **stated rather than derived** — which is the invariant DEC-014 adopted and the condition BUG-056
exists to end. The reassignment pays for itself: the chord the owner wants for shrink is freed *by the same
change that fixes the platform hole*. One chord per operation, everywhere.

**The wider principle, and it is the durable part.** *An operation's chord is bound by this app on every
platform, not inherited from Qt's platform table.* Two spellings of one operation were how the platform table
got to decide, and the platform table is what produced the only measured divergence in this area. This
generalises past redo: any future gesture that relies on Qt answering a chord natively is relying on a
per-platform table nobody in this repo reads.

**Owner's constraint on the change:** *"not the underlying logics, just the keys"* — **no undo/redo logic
changes**, only which keys reach which handler.

**Mechanical scope, verified.** Three code sites each carry the second-chord condition —
`pgtp_editor/ui/ddl_object_editor.py:913`, `pgtp_editor/ui/xml_editor.py:1178`,
`pgtp_editor/ui/ddl_editor_panel.py:164` — plus one `RESERVED_SEQUENCES` reason row
(`shortcut_registry.py:220`), 14 test lines across 3 files, 8 spec references and 7 manual references.

**THE GOTCHA — this is not a three-line deletion, and getting it wrong silently defeats the whole
reassignment.** BUG-056 measured Qt's compiled binding table: the `Ctrl+Shift+Z` → `StandardKey.Redo` row
carries **`KB_Win | KB_X11`**, so `QPlainTextEdit` **redoes on that chord natively on both platforms**. If the
three sites merely *drop* their condition, the chord falls through to Qt and still redoes — and shrink-selection
would be bound to a chord that also redoes.

> Every editing surface must **actively intercept `Ctrl+Shift+Z` and refuse to let Qt's native redo run.** The
> chord stays **reserved** and every surface still **states its answer** — fully coherent with DEC-014's
> invariant — but the answer changes from *"redo"* to *"not redo; this is shrink"*.

That is the difference between deleting a condition and changing one. The condition at each of the three sites
is **re-routed, not removed**.

**Sequencing — the two halves are separable, and the keys half ships now.**

1. **The keybinding change can ship immediately**: bind `Ctrl+Y` explicitly on all platforms, free
   `Ctrl+Shift+Z` from redo, keep intercepting it so Qt's native redo cannot fire, and rewrite the registry
   reason. This *is* BUG-056, rescoped.
2. **Shrink-selection itself is new feature surface that does not exist today** (verified: no shrink / contract
   / narrow-selection operation anywhere in `pgtp_editor/`), so it routes through **`feature-triage`** into
   `docs/FEATURE_QUEUE.md`, and it plausibly belongs with `Select ▸` and FQ-032's motion work rather than
   standing alone. **Not designed here.** Note for whoever dispatches that: **FQ-034 already exists** and
   already contains the shrink counterpart with *"exact default chord for shrink"* as its open question (1) —
   this ruling **answers that question**, so `feature-triage` is extending FQ-034, not creating a sibling.
   `owner-decision` does not write the feature queue.

**Consequences, recorded explicitly.**

- **BUG-056's hold is LIFTED and the bug is RESCOPED.** Its **step 2 — adding `Ctrl+Shift+Z` redo branches to
  `PhpFileTab` — is WITHDRAWN by this ruling.** What remains is: bind `Ctrl+Y` explicitly on all platforms.
  Its step 4 shared matcher survives (see below).
- **BUG-050 (RESOLVED)** keeps its reservation of the chord; only the **reason** changes — reserved now because
  every surface must refuse Qt's native redo on it, not because our editors answer it as redo.
- **BUG-053 (RESOLVED)** loses the redo arm of its fix. Its *distinction* — undo and redo are different
  operations — is what survives and is exactly what the owner restated as *"totally different"*.
- **DEC-014's invariant is unaffected**, and its worked example is now **settled rather than contested**:
  `Ctrl+Shift+Z` remains a reserved chord every surface must answer; the answer is no longer redo. DEC-014's
  classify-not-boolean constraint still holds and now has one less member on the redo side — which is a
  *simplification*, since redo becomes a single chord and the set is symmetric again.
- **`Alt+Backspace` / `Alt+Shift+Backspace`** remain the open call DEC-014 flagged, and this ruling sharpens
  it: under *"bound by this app, not inherited"*, a native Qt undo/redo chord left unclaimed is the same defect
  as Linux's missing `Ctrl+Y`.

**For `spec-maintainer` / `manual-maintainer` — 8 spec and 7 manual references now diverge.**
`CONSOLIDATED_SPEC.md` §18.5 (`:6544` — *"`Ctrl+Shift+Z` is part of the claim, not a separate chord"* — the
claim survives, the redo meaning does not), §27 (`:10064`) and the §27 Ledger row; `manual.md:750`, `:1952`,
`:3823`, `:3949` (*"Ctrl+Shift+Z is a second redo key"*), `:4158`. `owner-decision` does not edit either
document.

---

## DEC-260810134914 — Does an attached `.pgtp` get copied when New Project is accepted, or is the copy deferred to the existing open-time copier?

- **Status:** ANSWERED (2026-08-10)
- **Answer: option (A) — copy at accept, sharing one copier.** Make `link_pgtp_if_needed`'s body callable with
  an **explicit source path** (rather than only the open document's path) and call it from `create_project`. On
  copy failure, **create the project with no `pgtp` link at all** and report the failure in the Audit panel —
  so the broken-link state (a recorded `working_copy_path` pointing at nothing) **never exists**, and the user
  can still attach the file later by opening it, which is the path that ships today.
- **Owner's reasoning.** **One definition of linking**, which §18.2 requires outright (*"or the two ways of
  linking would age apart"*). And the objection that killed (A) on paper **did not survive inspection**:
  `create_project` already `mkdir`s, writes `settings.json` and **creates a database** on accept, so one more
  side effect is a member of an existing category, not a new one — and that method's own comment already
  supplies the ordering rule for it (the sandbox step goes **last**, *"so a failed sandbox never costs the user
  the project"*). The copy is ordered the same way, before `ProjectSettings` is constructed, so the link is
  recorded only if the copy succeeded.
- **Wider principle (consistent with DEC-007/DEC-008, and worth stating because it decided this):** *a
  recorded identity that points at nothing is worse than no record at all.* Options (C) and (D) were both ways
  of shipping a partial link; the deciding question was not which was tidier but which states can exist. **The
  failure path is designed so the bad state is unreachable, rather than tolerated and documented.**
- **READY TO IMPLEMENT — this is the one hole left in shipped FQ-035 code, not pending design.** The change is
  local: `_new_project_pgtp_link(dialog)` (`ddl_project_controller.py:127-155`) gains a `folder` parameter at
  its single call site (`:350`), does the copy, and returns the full three-field `PgtpLink`. Its docstring
  already says the copy *"GOES IN THIS FUNCTION AND NOWHERE ELSE"* and names this entry as the open call —
  that docstring is now answered and must be rewritten to state the ruling.
- **The guard that must NOT be relaxed, restated because the answer makes it load-bearing:**
  `link_pgtp_if_needed` opens with `if self._settings.pgtp.working_copy_path: return` — *"never silently
  relinked."* Under (A) that guard is what makes a second link attempt a no-op rather than a silent overwrite.
  A refactor that moves the copy body out must keep the guard on the *entry point*, not lose it in the split.
- **Raised:** 2026-08-10, by `spec-maintainer` while folding **FQ-035** into `CONSOLIDATED_SPEC.md` §18.2.
  Flagged there rather than decided (see the ⚠ banner at `CONSOLIDATED_SPEC.md:5665-5684`).
- **Blocks:** **FQ-035's implementation.** FQ-035 is folded into the spec but **unbuilt**, and §18.2's status
  banner says so — this gates writing the code, not a shipped behaviour. Everything else in FQ-035 (the
  attach field, the XML parse, the reveal, the auto-population, the two probes, the settings write) is
  explicitly implementable without an answer; only *what `create_project` does with the file* waits.

**The situation, for someone who has not seen FQ-035.** FQ-035 adds a `.pgtp` attach field to the New Project
dialog. Attaching one also reveals a quality-server section auto-populated from that file (that is
`DEC-260810134915`, filed separately). A `.pgtp` attached at creation must end up **linked** to the new
project the same way one opened into an existing project already does: §18.2 treats the `.pgtp` as a
checked-out artifact — the source lives on an sshfs-mounted quality server, and the project keeps a **local
working copy** that the editor edits and `Deploy .pgtp` writes back. The link is
`PgtpLink(source_path, working_copy_path, last_known_source_checksum)`
(`pgtp_editor/db/ddl_project.py:67-77`).

So the dialog's accept path either performs that copy itself, or records the intent and lets the existing
copier do it later.

**What the code actually says — this is the substance of the entry, and it corrects the framing the
ambiguity was filed with.**

1. **"The existing copier" is `DdlProjectController.link_pgtp_if_needed()`
   (`pgtp_editor/ui/ddl_project_controller.py:660-697`), and it is the only code in the tree that writes a
   working copy.** It reads the open document's path as the source, writes
   `self._folder / source_path.name`, and records the three-field link.

2. **It early-returns when `working_copy_path` is already set** (`ddl_project_controller.py:672-673`:
   `if self._settings.pgtp.working_copy_path: return`, *"never silently relinked"*). **This falsifies the
   deferral option as stated.** Recording a `working_copy_path` at accept time and expecting the existing
   copier to fill it in later cannot work — the recorded path is precisely what permanently disables the
   copier. Deferral would have to mean recording `source_path` only and leaving `working_copy_path=None`,
   which is a *different* and weaker proposal: it produces a two-field link where the spec requires creation
   to produce the same three fields the open-time path produces, and it makes
   `report_project_drift` (`:614-639`, which keys on `source_path` alone) start reporting checksum drift for
   a project that has no working copy at all.

3. **"A file write on a dialog's accept path, which nothing else in this dialog does" is not accurate.**
   `create_project` (`ddl_project_controller.py:308-324`) already does, on accept and unguarded:
   `folder.mkdir(parents=True, exist_ok=True)`, then `save_settings(folder, settings)` (which writes
   `.ddlproject/settings.json`), then `self._provision_sandbox(dialog)` — which **creates a database**.
   Accept can therefore already fail for filesystem reasons today. The precedent is also already recorded in
   that method's own comment: the sandbox step is deliberately ordered **last**, *"so a failed sandbox never
   costs the user the project (§18's tier-2 degrade)."* One more side effect is not a new category; it is a
   member of an existing one, with an existing rule about where to put it.

4. **What a set-but-missing `working_copy_path` would actually do — all six consumers checked. Nothing
   crashes; three misbehave silently.**
   - `auto_open_linked_pgtp` (`:373-377`) — guarded by `Path(...).exists()`, but on a missing file it
     **`return`s instead of falling through** to the "scan the folder for a single `.pgtp`" branch. So the
     project silently opens with nothing loaded, *and* the fallback that would have rescued it is suppressed.
   - `resolve_pgtp_path` (`:643-658`) — a pure string comparison, no existence check. It would **redirect an
     open of the real source to the nonexistent working copy**. This is the sharp edge.
   - `link_pgtp_if_needed` (`:672`) — permanently no-op, as above.
   - `offer_pgtp_deploy_on_close` (`:501-508`) — `try/except OSError: return`. Tolerant, silent.
   - `deploy_pgtp` (`:699-718`) — `try/except OSError` → a *"Deploy Failed"* critical box. Visible failure on
     a user gesture; no crash.
   - `pgtp_working_copy_path` (`:270-276`) → `main_window.py:1288` → `pgtp_document_controller.py:584-586` —
     string comparison only. Tolerant.

**Options.**

- **(A) Copy at accept, sharing one copier.** Refactor `link_pgtp_if_needed` so its body is callable with an
  **explicit source path** (rather than only the open document's path), and have `create_project` call it.
  *Cost:* a real refactor of a method three other paths depend on, and one more failure mode on accept.
  *Mitigation already precedented:* attempt the copy **before** constructing `ProjectSettings`, so the link
  is recorded only if the copy succeeded; on failure surface via the Audit panel and create the project with
  **no** `pgtp` link — the user can attach it later by opening it, which is the path that exists today. The
  missing-path state then never occurs at all.
- **(B) Copy at accept, duplicating the copy logic in `create_project`.** *Cost:* two definitions of "what
  linking means", which §18.2 explicitly warns against (*"or the two ways of linking would age apart"*).
  Cheap now, and the two drift the first time either changes.
- **(C) Defer: record `source_path` only, `working_copy_path=None`.** *Cost:* not the three-field link the
  spec requires of creation; `report_project_drift` fires on a project with no working copy; and the copy
  only ever happens if the user later opens that exact source file — which, given `resolve_pgtp_path` passes
  unlinked paths through, does work, but means "attached at creation" and "linked" are different states with
  nothing telling the user which one they are in.
- **(D) Defer with a full `PgtpLink` whose `working_copy_path` does not exist yet.** **Ruled out by the code,
  not by taste:** `link_pgtp_if_needed`'s early return at `:672` means the copy would never happen, and the
  three consumers in (4) above would misbehave forever rather than transiently.

**Recommendation: (A).** The two claimed costs of copying at accept both fail on inspection — the accept path
already writes files and already creates a database, and the tier-2-degrade ordering rule for exactly this
situation is already written in the method. The one real cost is the refactor, and (C)/(D) do not avoid it so
much as pay for it in a worse currency: a project whose recorded link points at nothing. (A) also keeps a
single definition of linking, which is the constraint §18.2 states outright.

**What an answer unblocks.** FQ-035's `create_project` change becomes writable: the exact call sequence in
`ddl_project_controller.py:308-324`, whether `link_pgtp_if_needed` grows an explicit-source parameter, and
what happens when the copy fails. Nothing else in FQ-035 waits on it.

> **RESTATED 2026-08-10 (ASK sweep, `main` at `a1bd869`) — THIS IS NO LONGER "BEFORE IMPLEMENTATION". IT IS A
> HOLE IN SHIPPED CODE, AND THE COST OF LEAVING IT OPEN HAS CHANGED.** `82f2be6` shipped FQ-035's entire
> buildable remainder: the attach field, the XML parse, the reveal, the quality form, both `Test` probes, the
> settings write. **The deferred copy is now the two-field link this entry called option (C)**, living in
> exactly one place — `_new_project_pgtp_link(dialog)` (`pgtp_editor/ui/ddl_project_controller.py:127-155`),
> called from the single `ProjectSettings(...)` site at `:350`, returning `PgtpLink(source_path=…)` with
> `working_copy_path` and `last_known_source_checksum` empty and a docstring that names this entry as open.
> So (C)'s costs listed above are **live behaviour today**, not a hypothetical: a project created with an
> attached `.pgtp` is in the "attached but not linked" state until the user happens to open that exact source
> file, and nothing tells them which state they are in. The implementer left the hole in the one function
> where the fix belongs and said so, which is the good version of this — but the answer now *changes shipped
> behaviour* rather than deciding unwritten code.

**Three corrections `spec-maintainer` recorded that stand regardless of this answer** (`CONSOLIDATED_SPEC.md`
§18.2, superseding FQ-035's queue text — noted here only so this entry reads complete, not for decision):
(i) there is **no reusable connection-field widget** — `ConnectionSetupDialog`, `ProjectSettingsDialog` and
`NewProjectDialog` each build their own `QFormLayout`, and `ProjectSettingsDialog._build_connection_form` /
`_add_test_row` are **private statics on a `QDialog` subclass**; extracting a shared widget is out of scope
for FQ-035. (ii) The **two `Test` buttons are deliberately different probes** — sandbox `Test` is
`db/sandbox.py::probe` (superuser + `pg_dump`/`pg_restore`), quality `Test` is
`db/introspect.py::test_connection` (can we connect at all). (iii)
`MainWindow._import_pgtp_connection_into_target`'s empty-host guard (`main_window.py:3968`,
`if … or settings.target.host: return`) is **vacuous at creation** — the target is always empty there — but
**must not be relaxed**, because it is what stops a target supplied at creation from being silently
overwritten from the XML on first open.

---

## DEC-260810134915 — May New Project be accepted with the quality connection left blank, or filled but never tested?

- **Status:** ANSWERED (2026-08-10)
- **Answer: option (D) — no gate, plus one advisory. Explicitly NOT the bare ratification of what shipped.**
  Accept always succeeds. If the quality connection is **blank or was never tested**, say so **once** at
  creation. The `Test` button and its inline status label already ship (`new_project_dialog.py:487-501`), so the
  **only new thing is the accept-time notice** — and the placeholder comment at `:344-353` that names this
  entry as open is replaced by the ruling.
- **Owner's reasoning.** Two reasons, in the order that decided it. First, **a gate here cannot be made
  honest**: `connection_from_tree` returns `password=""` unconditionally — the `.pgtp`'s obfuscated password is
  never read by this codebase — so *"fully populated"* is not a bar the source data can ever clear, and any
  gate is either unsatisfiable offline (a green `Test`) or checks the wrong thing (a non-empty host, which
  gates the safe case and misses a wrong host entirely). Second, **detection already exists**:
  `refresh_target_connection_status` re-probes the target with a real query on **every project open**, and
  already reasons that *"a host-less profile has not failed — it has not been tried."* So a gate would buy
  **earliness, not detection** — and creation should not be the one gesture in this app refusable for a network
  condition.
- **Why (D) and not (A), given (A) is what shipped:** the shipped behaviour is right and the *silence* is the
  gap. The user attached a `.pgtp`, was shown a connection section, and left it blank or untested; saying so
  once costs nothing and no refusal is ever wrong.
- **Wider principle — this is the FQ-023/DEC-013 shape applied to a non-refusal:** *where the app declines to
  gate something, it still owes the user a statement of what it noticed.* An advisory is the alternative to a
  gate, not the absence of one.
- **The sub-question is answered with it:** a `.pgtp` attached and then the revealed fields **cleared** means
  **"no target", not an error** — and the code makes that the graceful outcome rather than merely the lenient
  one. `_import_pgtp_connection_into_target` fires **only when `settings.target.host` is still empty**, so a
  project created with the fields cleared has its target re-imported from the XML on first open, and one
  created with them supplied has that import suppressed by the same guard. Both branches are coherent and
  neither can silently overwrite the other. **That guard stays vacuous-at-creation and must not be relaxed.**
- **Raised:** 2026-08-10, by `spec-maintainer` while folding **FQ-035** into `CONSOLIDATED_SPEC.md` §18.2.
  Flagged there rather than decided (⚠ banner at `CONSOLIDATED_SPEC.md:5665-5684`, ambiguity 2).
- **Blocks:** **FQ-035's implementation** — specifically the dialog's accept-time validation rule. FQ-035 is
  folded into the spec but **unbuilt** (§18.2's status banner says so), and the spec explicitly instructs the
  implementer **not to invent a validation rule to unblock themselves**. So this gates code, not a shipped
  behaviour. Everything else in FQ-035 proceeds without it.

**The situation.** FQ-035 makes attaching a `.pgtp` in New Project reveal a **quality-server connection**
section, auto-populated from that file's `<ConnectionOptions>`. The question is what the dialog does when the
user clicks OK with that section **empty**, or **filled but never `Test`ed**.

**The constraint that shapes every option, verified in code.** `db/config.py::connection_from_tree`
(`pgtp_editor/db/config.py:45-69`) maps `host`/`port`/`database` and renames `login` → `user`, and returns
**`password=""` always** (`config.py:68`; docstring: *"The password is always blank (the XML stores it
obfuscated; we never use it)"*). The XML does carry a `password` attribute — SQL Maestro's obfuscated blob —
and **nothing in this codebase reads or de-obfuscates it, anywhere**. That is *why* the section earns its
place at creation: the one field the XML can never supply is the one the user has in mind at that moment.
It also means **"fully populated" is not an achievable gate** — auto-population is complete by construction
except for the field that decides whether a connection works.

Two further standing rules, restated because this dialog is the one place both connections are on screen at
once: **`<ScriptConnectionOptions>` must never be read** — the vendor writes a second element with the same
attributes and, in the repo's own fixture, **a different port**, so choosing between them is a guess about
which database to point a project at — and the **sandbox must never be seeded from `<ConnectionOptions>`**,
which §17 defines as the *target* (`main_window.py:3962-3964`: *"seeding a sandbox from it is how a sandbox
ends up pointed at production"*). The two groups stay independent.

**What the dialog validates today.** Exactly one thing, and it is not blocking in the strong sense:
`NewProjectDialog._on_accept_clicked` (`pgtp_editor/ui/new_project_dialog.py:222-226`) sets the inline label
*"Choose a project folder first."* and returns without accepting. There is no other validation of any field —
the sandbox connection can be blank, and `refresh_capability_status` handles that case explicitly
(`ddl_project_controller.py:551`, `sandbox_configured = bool(sandbox_params.host)`).

**What already handles an unverified or absent quality connection, verified.**
`refresh_target_connection_status` (`ddl_project_controller.py:575-612`) **re-probes the target on every
project open**, off the GUI thread, and returns early when there is no host — with the reason recorded in
place: *"a host-less profile has not failed — it has not been tried."* §18.8's Quality node already has a
`NOT_SET_UP` state to describe exactly this. So the "unconfirmed setting fails much later" cost is real but
bounded: it surfaces on the next project open, in a surface built for it.

**Options.**

- **(A) No gate at all** — blank is fine, untested is fine. *Cost:* a project can be created naming a
  quality server nobody has reached, and the user learns that later. *But* later is "next project open", via
  a probe and a status node that already exist.
- **(B) Gate accept on a green `Test`.** *Cost:* this becomes the dialog's **first blocking validation**, and
  it **refuses an offline user** — someone creating a project on a train cannot reach the quality server.
  Worse, it is a gate the data can never satisfy unaided: the password is never in the XML, so every user
  must type one before they may create *any* project from a `.pgtp`.
- **(C) Gate on non-empty fields only** (host present), no probe required. *Cost:* still a blocking
  validation, still refuses a user who intends to fill it in later in Project Settings, and buys nothing —
  an empty `target.host` is a state the whole app already handles (see above), while a non-empty but wrong
  host is not detected by this gate at all. It gates the case that is safe and misses the case that is not.
- **(D) No gate, plus a non-blocking advisory.** Accept always succeeds; if the quality connection is blank
  or was never tested, say so once — inline in the dialog and/or as an Audit line on creation — and let the
  user proceed. *Cost:* one more message the user can ignore; no refusal is ever wrong.

**On the sub-question — "attached a `.pgtp` but then cleared the revealed fields":** recommend **"no
target", not an error**, and the code makes this the graceful outcome rather than merely the lenient one.
`_import_pgtp_connection_into_target` fires **only when `settings.target.host` is still empty**
(`main_window.py:3968`). So a project created with the fields cleared has its target **re-imported from the
XML on first open**; a project created with them supplied has that import suppressed by the same guard.
Both branches are coherent, and neither can silently overwrite the other.

**Recommendation: (D)** — (A)'s behaviour with an advisory. Two reasons, in order of weight. First, **a gate
here cannot be made honest**: the password is structurally absent from the source data, so any gate is either
unsatisfiable offline (B) or checks the wrong thing (C). Second, **the late-failure cost is already paid for
elsewhere** — the target is re-probed on every project open and §18.8 has a state for "not set up" — so the
gate would buy earliness, not detection. Creation should not be the one gesture in this app that can be
refused for a network condition.

**What an answer unblocks.** `NewProjectDialog._on_accept_clicked` gets its final form (unchanged, or one new
branch), the quality `Test` button's role becomes settled (advisory versus gating), and the cleared-fields
case gets a defined meaning — after which FQ-035's dialog work is fully specified. It also tells
`spec-maintainer` what to write in place of §18.2's ⚠ banner.

> **RESTATED 2026-08-10 (ASK sweep, `main` at `a1bd869`) — OPTION (A) HAS SHIPPED AS THE DE-FACTO ANSWER, SO
> THIS IS NOW RATIFY-OR-REVERSE.** `82f2be6` shipped the dialog with **no gate**:
> `NewProjectDialog._on_accept_clicked` (`pgtp_editor/ui/new_project_dialog.py:344-353`) still has the folder
> check as its only blocking validation, with a comment stating outright that *"FQ-035 adds no gate: the
> quality section may be blank, partial or untested and accept must succeed anyway … (Whether it should be
> gated is DEC-260810134915, open; a gate invented here would be an answer to it.)"* The quality section also
> ships with a live `Test` button writing an inline status label (`:487-501`) — so the *advisory surface*
> option (D) wants already exists; what does not exist is any notice on accept when the section was left
> blank or never tested. The decision therefore reduces to: **ratify (A)** (delete that comment, keep the
> behaviour), **add (D)'s one advisory**, or **reverse to a gate**, which now removes a shipped capability.

**The same three FQ-035 corrections apply here and stand regardless of this answer:** no reusable
connection-field widget (three dialogs each build their own form; `ProjectSettingsDialog`'s builders are
private statics, and extracting a shared widget is out of scope); the two `Test` buttons are deliberately
different probes (`db/sandbox.py::probe` for the sandbox, `db/introspect.py::test_connection` for quality —
a superuser demand on a quality connection would refuse a correctly-configured project); and
`_import_pgtp_connection_into_target`'s empty-host guard is vacuous at creation but must not be relaxed.

---

## DEC-260810143559 — Is `Ctrl+W` (with `Ctrl+O`) *pinned dead* like `Ctrl+S`, or *no default, yours to assign*?

- **Status:** ANSWERED (2026-08-10)
- **Answer: option (B) — reserve NEITHER, and pin the invitation with a test.** Nothing in
  `RESERVED_SEQUENCES` changes; nothing in `pgtp_editor/` changes. A new case in
  `tests/ui/test_shortcut_registry.py` asserts `"Ctrl+W" not in RESERVED_SEQUENCES` **and** `"Ctrl+O" not in
  RESERVED_SEQUENCES`, **with the reason in its docstring**. The manual's invitation stands, and the ten
  fixtures that use `CommandBinding("file.close", …, "Ctrl+W")` as a freely-assignable example keep working.
- **Owner's reasoning.** The two chords are **not in `Ctrl+S`'s state**, and the register already says so.
  `Ctrl+S`/`Ctrl+Shift+S` are reserved because FQ-020 removed the **capability** — there is no save gesture
  anywhere, so no command may ever sit there. `Ctrl+W` lost its `File ▸ Close` binding for a narrower reason:
  this app closes six different things, so **no single "close" is the obvious default**. That is an argument
  against a default, not against a user who knows which close they mean. Reserving it would contradict a
  documented invitation and spend two of the few genuinely free conventional chords the dialog can offer.
- **The durable part — and it is why this entry produced work rather than nothing:**

  > **An unreserved-on-purpose chord is defended by a test, exactly as a reserved one is.**

  The *absence* of that assertion is precisely what let this reach the queue: a deliberate non-reservation
  looked identical to an oversight, so a sweep read it as a bug and filed it. The test is the difference
  between "nobody reserved this" and "this is not reserved, on purpose, for this reason."
- **Consequences recorded.** `docs/KEYBINDINGS.md`'s Known gap 4 already states this position in prose
  (rewritten in `d0a0804`), so **no register correction is owed** — the ruling ratifies it, and gap 4 can now be
  struck rather than narrowed. The gate vocabulary still has **no token** for *"no default, freely
  assignable"*: `Ctrl+W` carries `dead` and says the rest in its Notes. Whether to add a token is a separate,
  smaller call and is **not** decided here. `spec-maintainer` owes §27 the weaker category, which today pins
  `Ctrl+S`/`Ctrl+Shift+S` as deliberately dead and is silent on "no default, assignable" — that omission is what
  let the sweep read the two cases as one.
- **Option C (split the pair) stays ruled out**, and the ruling makes it permanent: the manual states the two
  as the same case in two places, and reserving one alone would break a symmetry the app tells the user about.
- **Raised:** 2026-08-10, by `bug-triager` while triaging **BUG-260810143058**, itself raised by the
  `docs/KEYBINDINGS.md` ledger sweep (Known gap 4).
- **Blocks:** nothing shipped. It blocks **BUG-260810143058's direction** — whether
  `shortcut_registry.RESERVED_SEQUENCES` gains rows for `Ctrl+W`/`Ctrl+O`. Two documentation fixes in that
  entry are unblocked and ship regardless (listed at the end). The cost of *not* answering is that the two
  documents keep contradicting each other and the next keyboard sweep re-files it a third time.

**The situation.** On 2026-08-09 the owner unbound `Ctrl+W` (`File ▸ Close`) and `Ctrl+O` app-wide, and on the
same day removed `CodeEditorDialog`'s last local `Ctrl+S`/`Ctrl+W` carve-out. The new ledger's Known gap 4
reads that as an oversight — *"dead but unreserved"* — and concludes that `Customize Shortcuts…` can quietly
reverse a deliberate decision by handing `Ctrl+W` to a menu command. **Triage refuted that framing, and this
entry rests on the refutation:** `Ctrl+W` was not unbound for the `Ctrl+S` reason, and the app currently tells
the user, in the manual, that it is free to assign.

**Verified in the tree at filing time (all three re-read, not inherited):**

- `pgtp_editor/ui/shortcut_registry.py:209-212` reserves `Ctrl+S`/`Ctrl+Shift+S` with the reason
  *"deliberately unbound app-wide — every save is a named Deployment menu click (§27)"*. That is a
  **capability** ruling (FQ-020): there is no save gesture anywhere, so no command may ever sit there.
- `pgtp_editor/ui/main_window.py:3068-3072` gives `Ctrl+W` a **different** reason: *"this app closes
  projects, `.pgtp` documents, PHP tabs, DDL object tabs, the XSD tab and console tabs, so one `Ctrl+W` has to
  pick which 'close' it means — and the one it meant was the rarest, closing the whole project."* That is an
  argument against a **default**, not against the chord existing.
- `pgtp_editor/resources/manual.md:3850` states the consequence to the user outright: *"**Ctrl+O** /
  **Ctrl+W** — **Nothing.** Both were unbound rather than moved, and both are free for you to assign"*, and
  `:4066` expands it (*"Ctrl+W is in exactly the same position"*). So the pair is **symmetric and documented**
  — and the ledger's gap-4 prose never mentions `Ctrl+O` at all.
- Neither `Ctrl+W` nor `Ctrl+O` is a key in `RESERVED_SEQUENCES` (grepped: no `Ctrl+O` anywhere in
  `shortcut_registry.py`). No binding for either chord exists anywhere in `pgtp_editor/` — every remaining hit
  is a comment or a manual line.

**The options.**

- **A — Reserve both `Ctrl+W` and `Ctrl+O`** (treat them as pinned dead, like `Ctrl+S`). Protects the
  2026-08-09 decision from being reversed through the customize dialog. Costs: it **contradicts a documented
  invitation** (`manual.md:3850`, `:4066` must be rewritten by `manual-maintainer` to say the opposite); it
  spends two of the handful of genuinely free, conventional chords the dialog can offer; and the test blast
  radius is **ten uses of `"Ctrl+W"`** across `tests/ui/test_customize_shortcuts_dialog.py:20, 99, 122, 159,
  219` and `tests/ui/test_shortcut_registry.py:32, 95, 102, 118, 216`, all of which use
  `CommandBinding("file.close", …, "Ctrl+W")` as a fixture default and *assign or steal it freely* — under A
  every one becomes a refusal and must change chord. That breadth is itself evidence the chord is treated as
  live and assignable throughout the suite.
- **B — Reserve neither, and pin the invitation with a test** (the triage recommendation). Nothing in
  `pgtp_editor/` changes; the **ledger's prose is what was wrong**, not the code. A new case in
  `tests/ui/test_shortcut_registry.py` asserts `"Ctrl+W" not in RESERVED_SEQUENCES and "Ctrl+O" not in
  RESERVED_SEQUENCES` with the reason in its docstring, so an unreserved-on-purpose chord is defended exactly
  as a reserved one is — the missing assertion is precisely why this reached the queue. Cost: a user who
  assigns a command to `Ctrl+W` gets a second, differently-scoped "close" gesture, which the owner may find
  confusing; and the gate vocabulary at `KEYBINDINGS.md:47-57` has **no token** for "no default, freely
  assignable" (`dead` means *deliberately answered by nothing, app-wide*), so B needs either a new gate token
  or the row's Notes carrying the distinction.
- **C — Split the pair** (reserve one, not the other). Ruled out unless the owner supplies a reason the two
  differ: the manual states them as the same case in two places and
  `tests/ui/test_launcher_dialog.py:627` records the same pairing.

**Recommendation: B.** The 2026-08-09 reason was *no single close is the obvious default* — that is an
argument about a default, not a ban on the capability. `Ctrl+S` is different in kind: FQ-020 removed the
*ability to save by gesture*, so a command on `Ctrl+S` would contradict the design rather than exercise it.
`RESERVED_SEQUENCES`' own docstring (`shortcut_registry.py:195-198`) draws that exact line — reserved means
*something the dialog does not own already answers it, or the spec pins it as deliberately dead* — and nothing
answers `Ctrl+W`, while "pinned dead" is a stronger claim than the 2026-08-09 decision made.

**A live constraint on whichever way this goes.** `docs/KEYBINDINGS.md` is now machine-verified by
`tests/test_keybindings_ledger.py`, whose `test_every_reserved_sequence_has_a_row_marked_reserved` (`:508`)
asserts `RESERVED_SEQUENCES` and the ledger's **Reserved** column are the *same set in both directions*. So
**any change to `RESERVED_SEQUENCES` must edit the ledger in the same commit** or the suite reddens — under A
that means flipping `KEYBINDINGS.md:117` to Reserved `yes` and adding a `Ctrl+O` row. This tripwire has
already fired once in a merge; treat it as a hard constraint, not a nicety.

**Two edits that ship regardless of the ruling** (recorded here so they are not held hostage to it):

1. `pgtp_editor/ui/main_window.py:3074-3077` is **stale** — it says *"This does NOT touch
   `CodeEditorDialog`'s own `Ctrl+W`, which is a dialog-local Cancel bound as a `QShortcut`"*, but
   `code_editor.py:979-985` removed exactly that the same day (*"this dialog was the last carve-out for either
   chord"*), `manual.md:3978` agrees, and `tests/ui/test_code_editor.py:567` asserts `"Ctrl+W" not in bound`.
   The comment sends the next reader looking for a shortcut that does not exist; replace it with a pointer to
   `code_editor.py:979-985`.
2. `docs/KEYBINDINGS.md` Known gap 4 (`:185-188`) is **itself wrong** — it asserts the `Ctrl+S` rationale for
   `Ctrl+W` and calls the non-reservation an oversight. Its machine-checked columns are right (`:117` says
   Reserved `no`, matching the code); only the prose is wrong, and prose is the part no test covers.

**What an answer unblocks.** BUG-260810143058 becomes implementable in one pass: either the no-op-plus-test of
option B, or the coordinated reserve-both change (code + ledger + manual + ten fixtures) of option A. It also
tells `spec-maintainer` what to write in §27, which today pins `Ctrl+S`/`Ctrl+Shift+S` as deliberately dead and
says nothing about the weaker "no default, assignable" category — that omission is what let the sweep read the
two cases as one.

**Re-verified 2026-08-10 (ASK sweep, `main` at `a1bd869`). NARROWED TO THE RULING ALONE — the groundwork has
shipped.** `d0a0804` landed **both** of the "ships regardless" edits listed above: the stale
`CodeEditorDialog` comment at the `File ▸ Close` site is rewritten (`main_window.py:3107-3109` now says the
dialog's local `Ctrl+W` Cancel *"used to"* exist and points at `code_editor.py`), and `KEYBINDINGS.md`'s Known
gap 4 (`:188-203`) is rewritten to the corrected framing — it now states in the register itself that the two
chords have *no default and are deliberately assignable*, that this is **not** `Ctrl+S`'s state, and that the
gate vocabulary has no token for the second state. **Nothing else moved:** `Ctrl+W` and `Ctrl+O` are still
absent from `RESERVED_SEQUENCES` (grepped — no `Ctrl+W`, no `Ctrl+O` anywhere in `shortcut_registry.py`),
`KEYBINDINGS.md:117` still reads Reserved `no`, and the manual still invites the user to assign both. So the
only thing left in this entry is the **reserve-vs-assignable ruling**, and one consequence of the shipped
prose is worth stating: the register now *documents* option B's position, so choosing A means correcting the
register a second time in the same week.

---

## DEC-260810143600 — `F14` and `Ctrl+D`/`Ctrl+K`/`Ctrl+U`: suppress on both platforms, bind on both, or reserve-only?

- **Status:** ANSWERED (2026-08-10) — **ruled as one package with `DEC-260810164600`; both entries carry the
  answer.**
- **Answer, this entry's half:**
  - **`F14` → covered by the PHYSICALLY-ABSENT-KEYS CARVE-OUT, granted and to be written into §27**: the
    uniformity rule does not reach keys no keyboard in use actually has. No `EDITOR_UNDO_REDO_CHORDS` row, no
    reservation. **Its undo-routing bypass is knowingly accepted as unreachable, not overlooked** — see the
    trigger for revisiting it in `DEC-260810164600`.
  - **`Ctrl+D` / `Ctrl+K` / `Ctrl+U` → BIND ON BOTH PLATFORMS.** The app implements delete-character,
    delete-to-end-of-line and delete-complete-line **itself, at all six editing surfaces**, and **Windows gains
    three gestures it never had**.
- **⚠ THE OWNER CHOSE AGAINST THE RECOMMENDATION HERE, and deliberately took the fullest option.**
  `owner-decision` recommended **reserve-only as the floor** — purely subtractive, stopping `Customize
  Shortcuts…` from handing out a chord that would work on one of the owner's two machines and be silently eaten
  on the other, while leaving the *editing behaviour* split in place. The owner rejected the floor and chose to
  bind. **The cost is accepted, not overlooked, and is recorded plainly so nobody later "simplifies" it back:**
  - it is **the most work of the three options** — three gestures × six surfaces, plus reserved-sequence rows,
    plus `docs/KEYBINDINGS.md` rows in the same commit;
  - **the app takes ownership of editing primitives it currently gets from Qt for free**, and owns their edge
    cases forever (what delete-line does on the last line, with a selection, at a document end, in a read-only
    buffer — each now the app's answer, not Qt's);
  - in exchange, **the uniformity rule is fully honoured for this family rather than partly**, which the floor
    option explicitly was not. That was the deciding property: reserve-only would have left a stated rule
    half-applied, and a half-applied rule is what the next sweep re-files.
- **Why these are not the F-keys, in one line:** `Ctrl+D`/`Ctrl+K`/`Ctrl+U` are **letter chords on keys every
  user has**, live on Linux, dead on Windows, and readline/Emacs line-editing a Linux user may reach for from
  muscle memory. The carve-out cannot reach them, so the rule applies in full.
- **Wider principle established by the pair of rulings:** *where the uniformity rule bites, it is applied in
  full — the app binds the gesture on both platforms rather than merely preventing the chord being
  reassigned.* Reserving a chord protects the customize dialog; **binding it protects the user.** A "floor"
  that leaves the behaviour split is a mitigation, not a resolution, and this project does not settle for one
  where the keys are reachable.
- **Implementation scope this creates — `BUG-260810143059` and `BUG-260810140553` Part 2 must now cover it
  TOGETHER**, since they touch the same table, the same six surfaces and the same ledger in one commit:
  three new editing gestures at six surfaces, the `Ctrl+Shift+Insert` binding, the `RESERVED_SEQUENCES` rows,
  the `docs/KEYBINDINGS.md` rows (the Reserved column is a **set equality** against `RESERVED_SEQUENCES` — this
  tripwire has fired in a merge before), the §27 carve-out text, and the striking of Known gap 5. **Two
  mechanical notes carried forward:** `EDITOR_UNDO_REDO_CHORDS` and `classify_undo_redo_chord` are **named for
  undo/redo**, so clipboard and line-editing chords need a rename or a second table while keeping *"every
  intercepted chord is reserved"* true (`tests/ui/test_code_editor.py:442`,
  `tests/ui/test_shortcut_registry.py:318`); and `tests/ui/test_shortcut_registry.py:150-154` uses **`Ctrl+U`
  as its example of a free chord** — move the example to a still-free chord, never weaken the assertion.
- **Raised:** 2026-08-10, by `bug-triager` while triaging **BUG-260810143059** (the non-clipboard remainder of
  the `docs/KEYBINDINGS.md` sweep's Known gap 5).
- **Blocks:** **BUG-260810143059's implementation** — the mechanism is settled either way, only the direction
  is not. Nothing shipped is blocked. What hardens with time is the `Ctrl+D`/`Ctrl+K`/`Ctrl+U` half: they are
  free rebinding targets today, so every day the customize dialog can hand one to a menu command that then
  works on Windows and is silently swallowed on Linux.
- **Must be ruled together with `BUG-260810140553` Part 2** (`Ctrl+Shift+Insert` and the `F16`/`F18`/`F20`
  clipboard trio). Both halves apply the *same* uniformity rule to X11-only chords; ruled separately, the two
  answers will diverge and the rule stops being a rule.

**The situation.** Qt's `StandardKey` table is not uniform across platforms. On the Linux/KDE scheme Qt answers
chords inside every text widget that the Windows scheme leaves unbound — measured, and recorded in
`docs/KEYBINDINGS.md` Appendix A (`:133-157`), which `test_appendix_a_matches_the_running_keyboard_scheme`
re-measures:

| `StandardKey` | Windows scheme | Linux/KDE scheme | What the app's silence produces |
|---|---|---|---|
| `Undo` | `Ctrl+Z`, `Alt+Backspace`, `Undo` | `Ctrl+Z`, **`F14`**, `Undo` | `F14` runs `QPlainTextEdit`'s **native** undo on Linux |
| `Delete` | `Delete` | `Delete`, **`Ctrl+D`** | deletes a character on Linux, nothing on Windows |
| `DeleteEndOfLine` | *(nothing)* | **`Ctrl+K`** | deletes to end of line on Linux, nothing on Windows |
| `DeleteCompleteLine` | *(nothing)* | **`Ctrl+U`** | deletes the line on Linux, nothing on Windows |

`F14` is the correctness half: it **bypasses the app's undo routing entirely** — no re-emission into the
project's snapshot history, no read-only refusal in Caption Mode, no journal line. That is the same defect
BUG-056 fixed for `Ctrl+Shift+Z`. Verified: `shortcut_registry.EDITOR_UNDO_REDO_CHORDS` (`:368-374`) contains
exactly five chords — `Ctrl+Z`, `Ctrl+Y`, `Ctrl+Shift+Z`, `Alt+Backspace`, `Alt+Shift+Backspace` — and `F14` is
not among them, so it falls through to Qt at all six surfaces. `Ctrl+D`/`Ctrl+K`/`Ctrl+U` are the reachability
half: nothing in the app binds them, none is in `RESERVED_SEQUENCES`, and they are physically present on every
keyboard.

**Why this is a genuinely new application of the owner's rule, not a repeat.** The rule (2026-08-10: *a chord
means the same thing on every system, so the app binds or suppresses on both — never inherits from Qt*) was set
on `Alt+Backspace`/`Alt+Shift+Backspace`, and the reasoning that decided them was **discoverability**: legacy
spellings, in no menu, no manual page, no shortcut table, so binding them on the other platform would be
*inventing* a keybinding (`shortcut_registry.py:246-263` records this verbatim). `F14` fits that reasoning
exactly. `Ctrl+D`/`Ctrl+K`/`Ctrl+U` do **not**: they are **letter chords** on keys every user has, and they are
readline/Emacs line-editing that a Linux user may reach for from muscle memory. This is the first time the rule
meets a family where suppressing removes a *working, reachable* gesture.

**The options — the two families can be answered separately, and probably should be.**

*For `F14`:*

- **Suppress on both** (recommended). One row, `"F14": SUPPRESSED`, in `EDITOR_UNDO_REDO_CHORDS` reaches all
  six surfaces through `classify_undo_redo_chord` — BUG-056's mechanism, reused rather than reinvented. Closes
  the routing bypass. Cost: nothing a user will notice, on a key essentially no keyboard in use has.
- **Bind it as undo on both.** Also closes the bypass; identical mechanism, `UNDO` instead of `SUPPRESSED`.
  Cost: it *invents* a second undo spelling on Windows, against DEC-015's settled one-chord-per-operation
  (*"redo is always, on all systems, `Ctrl+Y`"*), for a key nobody can press.
- **Leave it** — ruled out by the owner's own 2026-08-10 rule, which forbids inheriting a platform-conditional
  chord from Qt. Only survives if the carve-out below is granted.

*For `Ctrl+D`/`Ctrl+K`/`Ctrl+U`:*

- **Reserve-only, as the floor** (recommended, and it can be done regardless of what goes on top). Accepts the
  platform difference for plain built-in editing keys, but stops `Customize Shortcuts…` handing the chord to a
  command. Purely subtractive; removes the one outcome that is **unambiguously a bug** — a rebinding that works
  on one of the owner's two machines and is silently eaten on the other. Cost: the platform split in the
  *editing behaviour* remains, so the uniformity rule is honoured only partly, and that partiality must be
  written down or the next sweep re-files it.
- **Suppress on both.** Fully uniform. Cost: takes three working editing keys away from Linux users, including
  the owner's own machine.
- **Bind on both.** Fully uniform in the other direction, and adds three real gestures on Windows. Cost: the
  most work, and the app takes ownership of delete-line/delete-to-EOL behaviour it currently gets from Qt for
  free, at six surfaces.

**The open sub-question that would settle several rows at once.** `KEYBINDINGS.md:17-23` and the `DEC-015` gate
token state the uniformity rule with **no carve-out for keys no keyboard in use actually has**. `F13`–`F20` are
the test case: `F14` here, and `F16`/`F18`/`F20` in BUG-260810140553's Part 2. If the owner rules *"the
uniformity rule does not reach physically-absent keys"*, all four retire in one line — but that carve-out must
be **stated in the spec**, not left implicit, or the next sweep re-files every one of them. Answering this once
is cheaper than answering four rows in turn.

**One tripwire to record, because it will look like a regression.**
`tests/ui/test_shortcut_registry.py:150-154` (`test_reserved_lookup_is_spelling_insensitive`) asserts
`reserved_reason("Ctrl+U") is None` — it uses `Ctrl+U` as its example of a *free* chord. Reserving `Ctrl+U`
reddens that test, and the correct fix is to **move the example to a chord that is still free**, never to weaken
the assertion.

**And the ledger constraint, which is live.** `docs/KEYBINDINGS.md` is machine-verified by
`tests/test_keybindings_ledger.py`: `test_every_reserved_sequence_has_a_row_marked_reserved` (`:508`) makes
`RESERVED_SEQUENCES` and the Reserved column one set in both directions, and
`test_editor_chord_set_rows_state_the_operation_and_every_surface` (`:532`) requires every
`EDITOR_UNDO_REDO_CHORDS` row to have a ledger row naming its **operation** and **all six surfaces**. So each
chord this ruling touches needs a full new ledger row **in the same commit** (`Ctrl+D`/`Ctrl+K`/`Ctrl+U` have
none today; `F14` appears only in Appendix A at `:135`), and Known gap 5 (`:189-197`) must be struck or narrowed
to whatever the ruling leaves open. This tripwire has already fired once in a merge — it is a hard constraint,
not a nicety.

**Recommendation, in one line:** `SUPPRESSED` for `F14`, and **reserve-only as the floor** for
`Ctrl+D`/`Ctrl+K`/`Ctrl+U`, with suppress-vs-bind on top of that floor being the only thing genuinely left to
the owner — plus the physically-absent-keys carve-out answered yes or no, once, for both entries.

**What an answer unblocks.** BUG-260810143059 becomes implementable: one `EDITOR_UNDO_REDO_CHORDS` row for
`F14` (verify the `QKeySequence("F14")[0]` round-trip first — the one mechanical risk), the matching
`RESERVED_SEQUENCES` rows, the ledger rows, and the per-surface cases at the five surface test files.
BUG-260810140553's Part 2 unblocks with it. And `spec-maintainer` gets the text for §27, which today states the
`Alt+Backspace` suppression and DEC-015's redo rule but says nothing about any X11-only chord and has no
`Ctrl+D`/`Ctrl+K`/`Ctrl+U` row.

**Re-verified 2026-08-10 (ASK sweep, `main` at `a1bd869`). Still fully open; the groundwork under it shipped.**
`d0a0804` landed the keyboard batch — `Ctrl+Insert`/`Shift+Insert`/`Shift+Delete` reserved with ledger rows
(`shortcut_registry.py:342-348`), the `StandardKey` inheritance removed at both app-owned sites, the
caption-panel scope fix, the `Ctrl+C`/`Ctrl+V` reason strings. **None of it touched this ruling's subject:**
`EDITOR_UNDO_REDO_CHORDS` (`shortcut_registry.py:399-401`) still holds exactly three rows — `Ctrl+Shift+Z`
(`CLAIMED_NOT_UNDO_REDO`), `Alt+Backspace`, `Alt+Shift+Backspace` (`SUPPRESSED`) — with **no `F14`**, and
`Ctrl+D`/`Ctrl+K`/`Ctrl+U` appear nowhere in `shortcut_registry.py` at all. `KEYBINDINGS.md`'s Known gap 5
(`:204-217`) was **narrowed, not closed**: no *app-owned* binding inherits an X11-only chord any more, so what
is left is purely Qt's own widget-internal answer — which is exactly what this entry rules on.

**Its other half is now filed as `DEC-260810164600`** (the clipboard chords `Ctrl+Shift+Insert` and
`F16`/`F18`/`F20`). The two are **one uniformity rule applied to two families and must be answered together**;
see that entry's cross-reference back here.

---

## DEC-260810164600 — `Ctrl+Shift+Insert` and the `F16`/`F18`/`F20` clipboard trio: bind on both platforms, suppress on both, or carve physically-absent keys out of the uniformity rule?

- **Status:** ANSWERED (2026-08-10) — **ruled as one package with `DEC-260810143600`, which carries the same
  answer block. Read them together; they were deliberately not ruled apart.**
- **Answer, this entry's half:**
  - **`Ctrl+Shift+Insert` → BIND EXPLICITLY ON BOTH PLATFORMS** (option A). Installed unconditionally —
    redundant on X11, new on Windows — exactly the shape DEC-015 used for `Ctrl+Y`.
  - **`F16` / `F18` / `F20` → the physically-absent-keys CARVE-OUT IS GRANTED**, and **must be written into
    §27** rather than left implicit.
- **Owner's reasoning.** `Ctrl+Shift+Insert` is the **opposite case to `Alt+Backspace`** and the analogy must
  not be applied mechanically: that pair was suppressed because it was **dead on the machine the owner uses**,
  whereas this chord is **live on Linux today**, so suppressing it would *remove a working paste gesture*.
  Binding is both the cheaper and the less destructive side of the same rule. For the F-trio — dedicated Sun/HP
  Copy/Paste/Cut keys, on no keyboard in use, in no menu, no manual page, no shortcut table — the rule simply
  has nothing to protect.
- **THE CARVE-OUT, as it must be stated in §27:** *the uniformity rule does not reach keys no keyboard in use
  actually has.* It retires `F16`/`F18`/`F20` **and `F14`** (`DEC-260810143600`) in one line.
- **Recorded so a future sweep does not re-file it: `F14`'s undo-routing bypass is KNOWINGLY ACCEPTED AS
  UNREACHABLE, not overlooked.** `F14` runs `QPlainTextEdit`'s native undo — no re-emission into project
  snapshot history, no read-only refusal in Caption Mode, no journal line — which is a *correctness* gap being
  closed by a *hardware* argument. The owner was told this explicitly and accepted it on the ground that no
  reachable key fires it. **If a keyboard with an `F14`…`F20` block ever comes into use, this is a live defect
  again and the carve-out is what must be revisited — not the rule.**
- **Wider principle:** *a rule about platform uniformity is about what a user can actually press.* The
  uniformity rule exists because a chord that works on one machine and is dead on another is a bug; a chord no
  machine can produce is not a divergence anyone can experience. But the carve-out is **a stated exception with
  a stated trigger for its own review**, not a softening of the rule.
- **Raised:** 2026-08-10, by the main session, lifting **BUG-260810140553 Part 2** out of the bug queue. Part 2
  is an explicitly labelled *"OWNER CALL, do not decide it in the implementation pass"* that has been sitting
  **inside `docs/BUGFIX_QUEUE.md`** (`:6229-6233`) — a decision living where nobody sweeps for decisions, which
  is the exact failure this register exists to prevent. The bug entry's own text says *"the caller has said they
  will file it; do not write to `docs/DECISION_QUEUE.md` from a bug-fix pass either."* This is that filing.
- **MUST BE RULED TOGETHER WITH `DEC-260810143600`** (`F14` and `Ctrl+D`/`Ctrl+K`/`Ctrl+U`). Both halves apply
  the **same** uniformity rule to X11-only chords that Qt answers inside every text widget; ruled apart, the two
  answers diverge and the rule stops being a rule. That entry carries the reciprocal cross-reference.
- **Blocks:** **BUG-260810140553's Part 2** — Part 1 shipped (`d0a0804`), Part 2 is untouched. Nothing shipped
  is blocked. What hardens is nothing much: unlike the `Ctrl+D`/`Ctrl+K`/`Ctrl+U` half, none of these four is a
  plausible rebinding target, so the cost of delay is that the ledger keeps a Known gap open and the next
  keyboard sweep re-files it.

**The situation.** Qt's `StandardKey` table differs per platform. Measured on this checkout (BUG-260810140553,
and re-confirmed in `docs/KEYBINDINGS.md` Appendix A `:137-139`, which
`test_appendix_a_matches_the_running_keyboard_scheme` re-measures):

| `StandardKey` | Windows scheme | Linux/KDE scheme | The app's answer today |
|---|---|---|---|
| `Paste` | `Ctrl+V`, `Shift+Insert`, `Paste` | + **`Ctrl+Shift+Insert`**, **`F18`** | left to Qt inside the widgets |
| `Copy` | `Ctrl+C`, `Ctrl+Insert`, `Copy` | + **`F16`** | left to Qt inside the widgets |
| `Cut` | `Ctrl+X`, `Shift+Delete`, `Cut` | + **`F20`** | left to Qt inside the widgets |

So `Ctrl+Shift+Insert` pastes on Linux and does nothing on Windows, and the F-trio likewise — which contradicts
DEC-015's ruling that *an operation's chord is bound by this app on every platform, never inherited from Qt's
platform table*.

**What Part 1 already fixed, so this is not re-litigated.** `d0a0804` removed every **app-owned** inheritance:
the caption grid's `QShortcut(QKeySequence.StandardKey.Copy, …)` pair became the spelled chords `Ctrl+C`/`Ctrl+V`
(a `StandardKey` argument installs *every* chord the running scheme lists — that was the mechanism by which an
app binding differed per platform), `XmlEditor`'s read-only-hint test now matches an app-owned
`EDITOR_PASTE_CHORDS = ("Ctrl+V", "Shift+Insert", "Paste")` (`shortcut_registry.py:422`) which **deliberately
excludes `Ctrl+Shift+Insert`**, and `Ctrl+Insert`/`Shift+Insert`/`Shift+Delete` are now reserved
(`:342-348`) so the customize dialog refuses them. **What remains is purely Qt's own widget-internal answer**,
which is what `KEYBINDINGS.md` Known gap 5 (`:204-217`) now says in so many words.

**The two families inside this entry are not symmetric, and that is the whole decision.**

*`Ctrl+Shift+Insert` — the opposite case to `Alt+Backspace`, and the analogy must not be applied mechanically.*
The `Alt+Backspace` pair was suppressed on both platforms because it was **dead on the machine the owner uses**:
a legacy Windows-only spelling in no menu, no manual page and no shortcut table, so binding it on Linux would
have been *inventing* a keybinding (`shortcut_registry.py:246-263` records that reasoning verbatim).
`Ctrl+Shift+Insert` is the reverse — **live on Linux today, on this project's own development platform** — so
suppressing it *removes a working paste gesture*.

*`F16`/`F18`/`F20` — these genuinely are the `Alt+Backspace` case.* Dedicated Sun/HP `Copy`/`Paste`/`Cut` keys,
absent from essentially every keyboard in use, no presence anywhere in the app, no discoverability.

**Options.**

- **(A) Bind `Ctrl+Shift+Insert` explicitly on both platforms** — install it unconditionally (redundant on X11,
  new on Windows), exactly the shape DEC-015 used for `Ctrl+Y`. *Cost:* a third paste spelling that appears in
  no menu and must be added to the manual's chord table and the ledger; and the app takes ownership of a
  clipboard gesture it currently gets from Qt free.
- **(B) Suppress `Ctrl+Shift+Insert` on both platforms** — a `SUPPRESSED` row consumed at every editing surface.
  *Cost:* **a capability regression on Linux**, i.e. on the owner's own machine, plus interception code at six
  surfaces *and* the two non-`CodeEditor` editing surfaces (`caption_management_panel`'s `QTableWidget`,
  `XmlEditor`) each needing a stated answer. Strictly more work than (A) to achieve strictly less.
- **(C) Suppress the `F16`/`F18`/`F20` trio on both** — mechanism already exists and must be reused, not
  reinvented: rows in `EDITOR_UNDO_REDO_CHORDS` consumed through `code_editor.classify_undo_redo_chord`.
  *Cost:* the table and its matcher are **named for undo/redo**, so clipboard chords need a rename or a second
  table; the DEC-014 invariant tests (`tests/ui/test_code_editor.py:442`,
  `tests/ui/test_shortcut_registry.py:318`) key off that table and must keep *"every intercepted chord is
  reserved"* true. Real refactoring for keys nobody can press.
- **(D) Carve physically-absent keys out of the uniformity rule, and state the carve-out in the spec.** *"The
  rule does not reach keys no keyboard in use actually has."* This retires `F16`/`F18`/`F20` **and `F14`** (in
  `DEC-260810143600`) in one line. *Cost:* the rule gains its first exception, and the exception's boundary is
  a judgement about hardware that ages — so it must be written into §27, not left implicit, or every sweep
  re-files these four rows. `KEYBINDINGS.md:17-23` states the rule today with **no** such carve-out.

**Recommendation: (A) + (D).** Bind `Ctrl+Shift+Insert` on both — binding is the cheaper *and* less destructive
side of the same rule, and suppressing a paste key that works on the owner's machine to buy uniformity is the
one outcome nobody wants. And grant the physically-absent-keys carve-out **explicitly in the spec**, which
disposes of `F16`/`F18`/`F20` here and `F14` next door without pretending the rule was never violated.

**One consequence of (D) worth seeing before granting it:** `F14` in `DEC-260810143600` is *not* purely
cosmetic the way `F16`/`F18`/`F20` are — it runs `QPlainTextEdit`'s **native undo**, bypassing the app's undo
routing (no re-emission into project history, no read-only refusal in Caption Mode, no journal line). Under (D)
that bypass is knowingly accepted on the grounds that no reachable key triggers it. That is a defensible call,
but it is a *correctness* gap being closed by a *hardware* argument, so it should be made deliberately.

**What an answer unblocks.** BUG-260810140553 Part 2 becomes implementable in one pass with
BUG-260810143059: the `Ctrl+Shift+Insert` binding (or suppression row), the `RESERVED_SEQUENCES` rows, the
`docs/KEYBINDINGS.md` rows **in the same commit** (`test_every_reserved_sequence_has_a_row_marked_reserved`
makes the reserved set and the ledger's Reserved column one set in both directions — this tripwire has fired in
a merge before), the striking or narrowing of Known gap 5, and `spec-maintainer`'s §27 text, which today states
the `Alt+Backspace` suppression and DEC-015's rule but says nothing about any X11-only chord.

---

## DEC-260810164601 — What does `Shrink Selection` do when there is no expansion stack — refuse, or derive a target from the current selection?

- **Status:** ANSWERED (2026-08-10)
- **Answer: option (b) — DERIVE.** With an empty stack, `Shrink Selection` selects the **largest
  `structure_chain` member lying strictly inside the current selection**. Not a refusal, not a silent no-op.
- **Owner's reasoning — the deciding property is subsumption, not preference.** (b) **contains** the
  conservative option wherever that one is right: at the innermost span there is nothing strictly inside the
  selection, so (b) *is* a no-op there — **with no special case**. So choosing (a) would have bought a refusal
  path and an extra branch to get behaviour (b) already has. And the project's usual tie-breaker does not
  reach this: *never a silent wrong result* is about **destroying work**, and (b) replaces a **selection**, not
  text.
- **Accepted cost, recorded because it is real.** Shrink now **behaves differently depending on invisible
  state** — pop the stack if there is one, derive if there is not. The user cannot see which mode they are in.
  This was weighed and taken; the mitigation is that both modes move the selection *inward*, so the gesture's
  direction never surprises even when its exact target does.
- **The owner was told the rebinding asymmetry before ruling, and it did not change the answer.** Grow keeps a
  rebindable `QAction`; **shrink's carries no shortcut at all**, because `Ctrl+Shift+Z` is
  `CLAIMED_NOT_UNDO_REDO` (`shortcut_registry.py:399`) and all six editing surfaces intercept it so Qt's native
  redo cannot fire. **So a user who dislikes this behaviour cannot rebind away from it**, and
  `Ctrl+Shift+Z` cannot be handed to anything else either. That raised the cost of choosing wrong and is part
  of why the subsuming option won.
- **One boundary the implementation must honour:** where the selection is **not a superset of any span**, this
  is a **no-op — never an arbitrary selection**. Deriving is not licence to jump somewhere the selection does
  not contain.
- **Unblocks:** FQ-034 **part 3** — `shrink_structural_selection`'s body and its empty-stack branch. No refusal
  path is needed, so DEC-013's *"keystroke-answering refusals get the caret tooltip"* boundary **does not come
  into play here**; there is nothing to refuse. `spec-maintainer` replaces the first §29 FQ-034 item
  (`CONSOLIDATED_SPEC.md:11775-11784`) with this rule stated in §8.
- **Raised:** 2026-08-10, by `spec-maintainer` while folding **FQ-034** into `CONSOLIDATED_SPEC.md` §8
  (`a1bd869`). Flagged into §29 rather than decided (`CONSOLIDATED_SPEC.md:11775-11784`), because the answer is
  a product call.
- **Blocks:** nothing yet, and that is deliberate — **FQ-034 parts 1 and 2 (the stack, and grow extended to the
  SQL editors) ship without it**, and the two candidate behaviours are identical once a stack exists. What it
  blocks is **part 3, shrink itself**: the `shrink_structural_selection` method cannot be written without it.

**The situation, for someone who has not read FQ-034.** FQ-034 turns today's stateless single parent-walk
(`Ctrl+Shift+A`, XML-only, hidden on every `CodeEditor` tab) into a repeatable structural ladder with an
**expansion stack**, extends grow to the SQL editors, and adds a **`Shrink Selection`** counterpart on
`Ctrl+Shift+Z` (settled by DEC-015, which freed that chord from redo). Shrink pops the stack. The question is
what it does when the stack is **empty** — which is the case after a mouse drag, after any edit (the stack is
invalidated on a document revision change), and on the very first press.

**Two candidates, genuinely different products.**

- **(a) Refuse or no-op.** The conservative reading, and consistent with `Select Parent Block`'s existing
  behaviour at the document root — where it already does nothing. *Cost:* the chord does nothing after a mouse
  selection, which is a common way to arrive at a selection; and if it is a *silent* no-op the user cannot tell
  a refusal from a ladder that has stopped advancing. Making it a **stated** refusal costs an FQ-023-style
  reason, which under DEC-013's boundary — *did the user just press a key and get declined? → tooltip at the
  caret + Audit row* — means it must use `CodeEditor.report_refusal`, not a journal line alone.
- **(b) Derive** the largest `structure_chain` member lying strictly inside the current selection. What
  expand-region implementations elsewhere do, and it makes the chord useful immediately after a mouse
  selection. *Cost:* shrink then does two different things depending on invisible state (stack present vs not),
  and after a mouse selection it may jump somewhere the user did not choose.

**Why the project's usual tie-breaker does not settle it** — and this is the reason the spec refused to decide:
*never a silent wrong result* is about **destroying work**, and (b) replaces a **selection**, not text. Nothing
is lost either way, so the invariant that decides most questions here is silent.

**One price the owner has not been told, and it bears directly on this.** FQ-034's DEC-012 reconciliation makes
the pair **asymmetrically rebindable**: grow keeps a normal `QAction` with `setShortcut` (measured: neither
scheme's `QPlainTextEdit` claims `Ctrl+Shift+A`), but **shrink's `QAction` carries no shortcut at all**.
`Ctrl+Shift+Z` is classified `CLAIMED_NOT_UNDO_REDO` (`shortcut_registry.py:399`) and intercepted by all six
editing surfaces so Qt's native redo cannot fire, so FQ-034 gives that existing claim an answer rather than
binding the chord afresh. **Consequence: grow can be moved through `Customize Shortcuts…`; shrink cannot, and
`Ctrl+Shift+Z` cannot be handed to anything else either.** A user who finds shrink's empty-stack behaviour
annoying therefore **cannot rebind away from it** — which argues for whichever behaviour is least likely to
surprise, and raises the cost of choosing wrong.

**Recommendation: (b), derive.** Three reasons. The tie-breaker that would favour caution is inapplicable
(nothing is destroyed); a chord that does nothing on its most likely first use teaches the user it is broken;
and (b) subsumes (a) in the only case where (a) is clearly right — at the innermost span there is nothing
strictly inside the selection, so (b) *is* a no-op there, without a special case. The one thing (b) must not
do is jump when the selection is not a superset of any span: state that as a no-op, not as an arbitrary
selection.

**What an answer unblocks.** FQ-034 part 3: `shrink_structural_selection`'s body, its empty-stack branch, and —
under (a) — whether the refusal is silent or routed through `report_refusal` per DEC-013. It also lets
`spec-maintainer` replace §29's flagged item with a stated rule in §8.

---

## DEC-260810164602 — Where do FQ-034's *clause* and *parameter* rungs stop: is a whole signature parameter its own rung, and is there a clause rung for statements with no clause starters?

- **Status:** ANSWERED (2026-08-10)
- **Answer: NO parameter rung; the clause rung is emitted ONLY where a clause starter exists** (a **sparse**
  rung). `structure_chain` goes *word → paren group* inside a routine signature, and emits a clause member only
  for statements that actually contain a SQL clause starter.
- **Owner's reasoning — the spec's own criterion held, and it cuts the two sub-questions in opposite
  directions.** The criterion is *a rung that sometimes selects nothing new is worse than one rung fewer*,
  because the user presses again and cannot tell whether the ladder advanced or ended. A **sparse clause rung
  never selects nothing** — it is simply **absent** in `RAISE NOTICE …` or an assignment, and every press that
  *does* happen advances, so the ladder stays legible. A **parameter rung** would exist only inside a routine
  signature, making press counts differ by syntactic context for a much smaller payoff — and it is **the rung
  most easily added later, since the chain is a list**: inserting a member is a widening, not a redesign.
- **Wider principle:** *a ladder rung may be absent, but it may never be present-and-empty.* Varying **chain
  length** by construct is acceptable; a rung that fires and changes nothing is not. That is the test any future
  rung proposal must pass, and it is why "add it now in case" was rejected in favour of "add it when the chain
  needs it."
- **Recorded:** the same rebinding asymmetry noted in `DEC-260810164601` applies — grow is rebindable, **shrink
  is not** — so the ladder's rung count is felt through a chord the user cannot move, in both directions. The
  owner ruled with that in view.
- **Unblocks:** `sql/block_spans.py`'s `structure_chain` gets its final rung list, and with it the
  `StructureSpan.kind` vocabulary and the corpus test pinning the ladder against §18.4's adversarial SQL.
  `spec-maintainer` moves §29's second FQ-034 item (`CONSOLIDATED_SPEC.md:11785-11792`) into §8's rung table.
- **Raised:** 2026-08-10, by `spec-maintainer` while folding **FQ-034** into `CONSOLIDATED_SPEC.md` §8
  (`a1bd869`), flagged into §29 (`CONSOLIDATED_SPEC.md:11785-11792`) rather than decided.
- **Blocks:** the **rung table** of FQ-034's ladder — i.e. what `structure_chain(text, pos)` in the new Qt-free
  `sql/block_spans.py` returns for a caret inside a routine signature, and for a caret in a plpgsql statement
  with no SQL clause in it. The stack, the menu entries, the chords and the grow/shrink hosting are all settled
  and buildable; this decides the *contents* of the chain, which is the model's public shape.

**The situation.** The owner's request named the bottom rung *"the parameter/word we're on"*, and the ladder as
folded collapses *parameter* and *word* into one rung. Two boundaries were left undecided.

1. **Is a whole parameter declaration its own rung?** In `p_id integer DEFAULT 0`, is there a rung between
   *word* (`p_id`) and *paren group* (the whole argument list) that selects the three tokens as one unit?
2. **Is there a *clause* rung at all for plpgsql statements with no SQL clause starters?** In `RAISE NOTICE
   '…', x;` or a bare assignment there is no `SELECT`/`FROM`/`WHERE` to anchor a clause on, so rung 3 would
   either collapse into rung 4 (the statement) or select something arbitrary.

**The constraint the spec states, and it is the strongest input here:** *a rung that sometimes selects nothing
new is worse than one rung fewer* — because the user presses again and cannot tell whether the ladder advanced
or the ladder ended. The ladder's whole value is that each press visibly does something.

**Options — these are two sub-questions and may be answered differently, but they are one judgement about how
fine the ladder should be.**

*Parameter rung:*
- **Yes, add it.** Selecting a whole parameter declaration is a genuinely useful unit when editing a signature
  (retype a type, move a default). *Cost:* it exists only inside a routine signature, so the ladder has a rung
  that is present in one syntactic context and absent everywhere else — the user's press count to reach the
  paren group differs depending on where they started. Also needs signature-position awareness in a
  token-level span model that otherwise reasons about brackets and block keywords.
- **No, word → paren group.** Uniform rung count everywhere. *Cost:* editing a signature takes an extra manual
  selection, which is exactly the case the owner's example (*"the parameter/word we're on"*) came from.

*Clause rung for clause-less statements:*
- **Emit it only where a clause starter exists** (sparse rung). Honest: the rung appears when there is
  something for it to select. *Cost:* the chain length varies by statement kind, so press counts are not
  predictable across a function body — the same objection as the parameter rung, in a more common context.
- **Never emit a clause rung; go word → statement.** Uniform and simple. *Cost:* inside a long `SELECT` the
  jump from a word to the entire statement is a big one, and clause-level selection is one of the more useful
  things the ladder could offer in SQL specifically.

**Recommendation: no parameter rung; clause rung emitted only where a clause starter exists.** The two answers
differ deliberately, on the spec's own criterion — a rung must never select nothing new. A clause rung that
appears in SQL statements and not in `RAISE NOTICE` **never selects nothing**; it is simply absent, and the
ladder stays legible because every press that happens still advances. A parameter rung buys one convenience in
one context at the price of the same variability with a much smaller payoff, and it is the rung most easily
added later — the chain is a list, so inserting a member is a widening, not a redesign.

**Note the asymmetric-rebindability price applies here too** (see `DEC-260810164601`): grow keeps a rebindable
`QAction`, **shrink's carries no shortcut at all** because `Ctrl+Shift+Z` is claimed by all six editing
surfaces. So the ladder's rung count is felt through a chord the user cannot move, in both directions.

**What an answer unblocks.** `sql/block_spans.py`'s `structure_chain` gets its final rung list, and with it the
`StructureSpan.kind` vocabulary and the corpus test that pins the ladder against §18.4's adversarial SQL. It
also lets `spec-maintainer` move §29's second FQ-034 item into §8's rung table.

---

## DEC-260810193637 — Does Command mode leave `Ctrl+D` / `Ctrl+K` / `Ctrl+U` as the app's line-editing gestures, or must they be freed for a later vim binding?

- **Status:** ANSWERED (2026-08-10)
- **Answer: FREED in Command mode — consumed and INERT.** Command mode consumes all three and does nothing
  with them, **reserving them for later vim scrolling**. So **the same keystroke deletes a line in Edit mode
  and is inert in Command mode.** The owner went **against the recommendation**, which was to keep them as
  the app's gestures in both modes.
- **This is a QUALIFICATION of `DEC-260810143600`, not a reversal, and the distinction is the record's.**
  The three chords **stay bound, reserved and app-implemented at all six surfaces in Edit mode**; Windows
  keeps the three gestures it gained in `55c2538`; `apply_editor_operation` remains their one implementation
  and every boundary answer in its docstring still governs. **Only Command mode declines them.**
  `DEC-260810143600` therefore gets **no `SUPERSEDED BY` line** — it is narrowed in one mode, not overturned.
- **Consequence 1 — the decline lives in `apply_editor_operation` once, not in six `eventFilter`s.** Six
  copies of a mode test is six chances to drift, which is the same argument that centralised these chords
  into one function to begin with. `EDITOR_CHORDS` keeps classifying all three identically at all six
  surfaces: **what is mode-conditional is the APPLICATION, not the classification.** `PASTE` is untouched —
  the ruling freed exactly three operations, so `Ctrl+V` and `Ctrl+Shift+Insert` keep pasting in Command mode.
- **Consequence 2 — the mode-dependent silence is a STATED, OWNER-ACCEPTED EXCEPTION to FQ-023/DEC-013.**
  A swallowed keystroke that does nothing and says nothing is normally exactly what those forbid. The owner
  **accepted the stated cost verbatim: a mode-dependent hole with no visible reason.** So **a future sweep
  meeting an inert `Ctrl+U` in Command mode closes against this paragraph rather than re-filing a swallowed
  keystroke.** The only mitigation is the mode indicator, which is the one thing on screen explaining why
  the key did nothing.
- **Owner's reasoning:** the vim vocabulary's completeness outweighs keeping three chords uniform across
  modes — the same weighting that decided `DEC-260810193638` and `DEC-260810193639`. See *the pattern across
  all three*, below.
- **Unblocks:** §8's vim block stating the freeing as a rule (**folded, `50fe22b`**, at
  `CONSOLIDATED_SPEC.md` *"`Ctrl+D` / `Ctrl+K` / `Ctrl+U` are FREED in Command mode"*, ~:4090); the
  `apply_editor_operation` refusal branch; and **`docs/KEYBINDINGS.md` owes the three rows a Notes amendment**
  (their behaviour is now mode-conditional). No `RESERVED_SEQUENCES` change, so no ledger-test breakage.
- **⚠ RECORDING GAP (2026-08-10).** This answer was given, and folded into the spec (**`50fe22b`**), **hours
  before it was written here** — the answering session never dispatched `owner-decision`, so the entry still
  read `OPEN` while the spec already stated the ruling as settled design. That is precisely the
  *"decision believed filed"* failure the last pass wrote a rule about (§29's *Filing history* note), in the
  mirror image: not a decision believed filed, but an **answer believed recorded**. **The rule generalises:
  the queue is the record, and a ruling that exists only in the spec is a ruling this file will re-ask.**
- **Raised:** 2026-08-10, by `spec-maintainer`, while folding FQ-032 (vim editing mode) into
  `CONSOLIDATED_SPEC.md` §8 as target design
- **Blocks:** nothing. None of the three chords is in FQ-032's v1 command set, so there is **no defect
  today** and the rest of FQ-032 can be built without this answer. It hardens with time: once a v2 command
  set is designed against whichever answer the code happens to imply, reversing it costs a re-map.
- **Id provenance:** the `DEC-` timestamp was assigned from an observed clock reading supplied by the
  dispatching session, not from the moment of writing — do not read the exact second as the filing instant.

**Context.** FQ-032 gives every EDITABLE editor a transient, per-tab **Command mode** entered with `Esc`
(vim NORMAL), beside the default **Edit mode** (vim INSERT) — no setting, no persistence; in read-only
editors the vim layer is inactive entirely. As folded, **v1 Command mode claims only bare keys and no
`Ctrl` chord at all**, which is what turns the queue entry's headline risk ("whatever Command mode steals
must be restored or copy-paste / find-focus silently break") into a non-problem rather than a managed one.

The three chords at issue are already the app's. Since `55c2538` `Ctrl+D`, `Ctrl+K` and `Ctrl+U` are
**app-implemented at all six editing surfaces on both platforms** — `DELETE_CHARACTER`,
`DELETE_TO_END_OF_LINE`, `DELETE_LINE`, mapped at `pgtp_editor/ui/shortcut_registry.py:504-506`, with one
implementation in `code_editor.apply_editor_operation`, all three carrying `RESERVED_SEQUENCES` rows
(`shortcut_registry.py:392-403`) and all three with `docs/KEYBINDINGS.md` rows. That state is the owner's
own ruling **DEC-260810143600**, taken deliberately **against** the reserve-only recommendation, on the
ground that a half-applied uniformity rule is what the next sweep re-files.

In vim, `Ctrl+D` is page-down and `Ctrl+U` is scroll-up. So the question is not about today's behaviour but
about what a future extension of Command mode may claim.

**Options.**
- **They stay the app's, in BOTH editing modes.** Nothing to build, nothing to restore, and the three
  shipped editing primitives keep working identically whichever mode the editor is in. *Cost:* vim's scroll
  meanings are permanently unavailable in Command mode, and a vim user will press `Ctrl+D` expecting a page
  down and delete a character instead — a destructive surprise, albeit an undoable one.
- **Free them for a later vim binding.** Command mode could then offer vim's scrolling vocabulary. *Cost:*
  it **reverses DEC-260810143600**, which the owner took deliberately days ago — that entry would then need
  a `SUPERSEDED BY` line, and `docs/KEYBINDINGS.md` plus the manual's non-rebindable list would need
  revising; it re-opens the steal/restore problem the v1 "no `Ctrl` chord" rule closes; and it either removes
  three shipped editing primitives from Command mode (so the same key does different things in the two modes,
  in the destructive direction) or removes them app-wide.

**Recommendation: they stay the app's, in both editing modes**, and vim's scroll meanings stay permanently
unavailable. `PageUp`/`PageDown` exist on every keyboard; three shipped editing primitives do not have a
second spelling. This is put to the owner rather than settled in the spec because answering "free them"
would reverse an owner ruling, and the spec does not reverse the owner's rulings for itself.

**Unblocks:** a one-line rule in §8's vim block stating that the `Ctrl+D`/`Ctrl+K`/`Ctrl+U` family is
mode-independent (or, on the other answer, a `feature-triage` entry for the re-map plus a revision of
DEC-260810143600, `docs/KEYBINDINGS.md` and the manual's non-rebindable list).

**Cross-references:** `CONSOLIDATED_SPEC.md` §8, *"Vim editing mode — Edit mode and Command mode over BOTH
editor families"* (~:3820, note at ~:3991), and §29's three FQ-032 items, which state the same
recommendation.

---

## DEC-260810193638 — Is vim's `Ctrl-R` redo dropped PERMANENTLY, or merely deferred?

- **Status:** ANSWERED (2026-08-10)
- **Answer: neither — `Ctrl+R` is built, as COMMAND-MODE-ONLY redo.** In Command mode `Ctrl+R` is redo. **Edit
  mode leaves it unbound as redo**, keeping its existing meaning (focus the Replace field), so **redo is not
  reachable by `Ctrl-R` while typing**. **`Ctrl+Y` remains the app's redo everywhere** (DEC-015, unchanged).
  Also **against the recommendation**, which was to drop it permanently.
- **This makes `Ctrl+R` the app's FIRST MODE-CONDITIONAL CHORD** — a **fourth shape cutting across §27's
  three states** (**bound** · **reserved** · **no default, freely assignable**). The owner's *"not licence for
  others"* is **binding**: **any second mode-conditional chord is a new decision**, not an extension of this
  one. Do not cite this entry as precedent for `Ctrl+V` block-visual or anything else.
- **Consequence 1 — it REQUIRES a `ShortcutOverride` interposer.** `Ctrl+R` is a `QShortcut`
  (`find_replace_bar.install_focus_shortcuts`, `WidgetWithChildrenShortcut`, six `FindReplaceBar` hosts plus
  the caption panel's own pair), and **a `QShortcut` outranks `keyPressEvent`** — so Replace-focus would
  otherwise win and Command mode could never see the chord. The only mechanism is **accepting the
  `ShortcutOverride` event while Command mode holds**, which is the idiom the six surfaces already use for
  `Ctrl+Shift+Z`. This **corrects the spec's earlier claim that no event filter was needed in v1**, and it
  re-opens the queue entry's headline steal/restore risk exactly as FQ-032 stated it.
- **Consequence 2 — the single mode-reset path becomes a CORRECTNESS GUARANTEE, not tidiness.** While Command
  mode holds, **Replace-focus is dead on that editor.** A mode left set — a missed `focusOutEvent`, a
  read-only transition, a document swap — is a **silently broken `Ctrl+R`** with nothing on screen saying why
  but the indicator. **The spec therefore requires a test per exit trigger, all six** (insert-entry command ·
  focus loss · buffer becoming read-only · document swap · a focus-changing `:` command · tab switch),
  each asserting Replace-focus is restored.
- **Also owed:** `Ctrl+R` stays reserved, and its `RESERVED_SEQUENCES` reason must now state **both**
  meanings — *"focuses the Replace field"* alone is half the truth, and a user refused a chord is owed the
  real reason. `Ctrl+F` is untouched in both modes; no other find or clipboard chord is claimed.
- **Owner's reasoning:** *do not withdraw an existing capability* — here, do not withdraw the vim redo
  reflex — with the vim vocabulary's completeness weighed above cross-mode uniformity. See *the pattern
  across all three*, below.
- **Unblocks:** §8's Mode-D restatement rewritten from *"`Ctrl-R` is not built, do not implement it"* to the
  mode-conditional rule (**folded, `50fe22b`**, ~:4114 and the v1 command-set table ~:4173); the
  `ShortcutOverride` branch; the six exit-trigger tests; and closing FQ-032's `Ctrl-R` item as **in scope**
  rather than as future work.
- **⚠ RECORDING GAP (2026-08-10).** Answered and folded into the spec (**`50fe22b`**) before being written
  here; the answering session did not dispatch `owner-decision`, so this entry read `OPEN` while the spec
  stated the ruling as settled. See the same note on `DEC-260810193637`.
- **Raised:** 2026-08-10, by `spec-maintainer`, while folding FQ-032 into `CONSOLIDATED_SPEC.md` §8
- **Blocks:** nothing. That `Ctrl-R` is **not built in v1** already follows from what shipped, and the spec
  has restated it that way. What is open is only whether it is ever revisited.
- **Id provenance:** the `DEC-` timestamp was assigned from an observed clock reading supplied by the
  dispatching session, not from the moment of writing — do not read the exact second as the filing instant.

**Context.** FQ-032 lists "`u` / `Ctrl-R`" for undo/redo and describes `Ctrl+R` as a "redo/redraw"
collision. That is wrong about this app. `Ctrl+R` is a **reserved, per-tab `WidgetWithChildrenShortcut`
`QShortcut` that focuses the Replace field**, installed at six `FindReplaceBar` hosts by
`find_replace_bar.install_focus_shortcuts` (`pgtp_editor/ui/find_replace_bar.py:345-377`), plus the caption
panel's own pair, and reserved at `shortcut_registry.py:278`.

Claiming it for vim redo would need an `eventFilter` accepting `ShortcutOverride` (the shape the six
surfaces already use for `Ctrl+Shift+Z`) and would **remove Replace-focus for as long as Command mode
holds** — to buy a second spelling of an operation the app already answers uniformly with `Ctrl+Y` on both
platforms (DEC-015).

The property at stake is bigger than the one chord: **the first `Ctrl` chord Command mode claims re-opens
the whole steal/restore problem**, which the v1 "bare keys only" rule currently closes outright.

**Options.**
- **Permanent.** Redo in Command mode is `Ctrl+Y`. Command mode never touches a `Ctrl` chord, so no
  `ShortcutOverride` filter, no restore logic, and `Ctrl+F`/`Ctrl+R` mean the same thing in both modes
  everywhere. *Cost:* a vim user's muscle memory for `Ctrl-R` is dead, and the mode is that much less
  faithful to vim.
- **Deferred, to be revisited.** Leaves the door open to full vim fidelity. *Cost:* the door is the
  expensive part — as soon as it opens, Command mode is a keyboard *thief* rather than a bare-key layer,
  and every future `Ctrl` chord request ("what about `Ctrl+V` block visual?") arrives with precedent. It
  also means Replace-focus becomes conditional on an editing mode, which is a user-visible inconsistency
  across six surfaces.

**Recommendation: permanent.** Redo in Command mode is `Ctrl+Y`. Fidelity to vim is not worth converting a
"claims no `Ctrl` chord ever" rule into a "claims some `Ctrl` chords" rule; the former is a property that
can be stated and tested, the latter is a standing negotiation.

**Unblocks:** §8 stating the no-`Ctrl`-chord rule as an invariant of the vim layer rather than as a v1
scope note, and closing FQ-032's `Ctrl-R` item for good rather than leaving it as future work.

**Cross-references:** `CONSOLIDATED_SPEC.md` §8's *Mode D restatement* (~:3981 and the header note at :34),
and §29's three FQ-032 items. DEC-015 is the recorded ruling that `Ctrl+Y` is redo on both platforms.

---

## DEC-260810193639 — Is the vim layer INACTIVE in `CodeEditorDialog` (the "Edit code…" PHP/JS event-handler dialog)?

- **Status:** ANSWERED (2026-08-10)
- **Answer: no — `CodeEditorDialog` DOES get Command mode**, with a **mode indicator and an exit hint added
  to the dialog**. Also **against the recommendation**, which was that the layer be inactive there.
- **The chrome is LOAD-BEARING, NOT COSMETIC — it is the condition the ruling rests on.** FQ-032's entire
  safety argument is that **the indicator plus the exit hint is the ONLY guard** for someone who enters
  Command mode by accident. **Shipping the mode there without them ships the version the owner declined.**
  So the chrome is a **precondition**, not a follow-up: an implementation that lands Command mode in that
  dialog and defers the indicator has not implemented this ruling.
- **It becomes a THIRD `ModeIndicator` surface** — the first **outside the main window** and the first **not
  driven by `MainWindow._refresh_mode_indicator()`**, which the dialog cannot reach. It renders **the
  editing-mode segment only** (`Edit`, or `Command — press i to type`), not major/minor modes. This **applies**
  §7's one-source-of-truth rule rather than excepting it: §7's accessor answers major and minor, while the
  **editing mode's source of truth is the editor itself**, so a local render of a local fact is not a rival
  indicator. §7's *"two surfaces, one call"* framing is amended.
- **⚠ TWO COSTS THE RULING DID NOT NAME — flagged in the spec and carried here, not decided.**
  1. **`Esc` no longer cancels that dialog.** It was **its only keyboard cancel** since `Ctrl+S`/`Ctrl+W` were
     removed there on 2026-08-09. From Edit mode `Esc` now enters Command mode; from Command mode it clears
     pending state and stays. **Cancel survives via the button box and the window close** (and `Return` still
     accepts), so nothing is trapped, but a keyboard-only user loses a gesture. **The ruling's stated reason
     was the accidental-entry risk, not this** — the two are different costs, which is why this is recorded
     as a flag. A **two-press escape** (`Esc` in Command mode with nothing pending falling through to the
     dialog's reject) would restore it and is the obvious candidate, but it is vim-inauthentic and is **not
     specified**. This is the one genuinely live item left by the FQ-032 fold.
  2. **`:` is unavailable in that dialog, and must SAY SO.** The palette's namespace **is** the menu tree
     (`collect_menu_commands()`); a menu-less dialog has no tree to derive from. Per refuse-don't-guess it
     **states that** rather than opening an empty palette — an empty command line is the dead-control posture
     §7 forbids. Every other Command-mode gesture works there normally.
- **Owner's reasoning:** *do not withdraw an existing capability* — do not deny one editable surface the
  editing vocabulary every other editable surface has — with the accidental-entry risk answered by the
  chrome rather than by exclusion. See *the pattern across all three*, below.
- **Unblocks:** §27's `Escape` row 6 corrected (`CodeEditorDialog` no longer reaches it) and its
  *"Return / Escape — OK / Cancel"* row for that dialog corrected; §8's *"The dialog's new chrome"* block
  (**folded, `50fe22b`**, ~:4025); the FQ-032 implementation knowing `VimModeMixin` installs at this host too;
  and a `ModeIndicator` render path that does not depend on `MainWindow`. **`manual-maintainer` owes the
  dialog's `Esc`-cancel change**, since the manual currently describes `Escape` as that dialog's cancel.
- **⚠ RECORDING GAP (2026-08-10).** Answered and folded into the spec (**`50fe22b`**) before being written
  here; the answering session did not dispatch `owner-decision`, so this entry read `OPEN` while the spec
  stated the ruling as settled. See the same note on `DEC-260810193637`.
- **Raised:** 2026-08-10, by `spec-maintainer`, while folding FQ-032 into `CONSOLIDATED_SPEC.md` §8
- **Blocks:** nothing in the rest of FQ-032 — but it blocks that dialog specifically: if the layer is active
  there and nobody notices, the dialog ships with one fewer exit than it has today.
- **Id provenance:** the `DEC-` timestamp was assigned from an observed clock reading supplied by the
  dispatching session, not from the moment of writing — do not read the exact second as the filing instant.

**Context.** With FQ-032 folded, `Esc` has **six** meanings, ordered in §8 (~:3918). Five are free of
conflict: the completion popup takes focus, so the editor never sees the key; a Find bar field is a
different widget; tab-stop mode is a narrower state; read-only means the layer is off.

The **one genuine collision is `CodeEditorDialog`** (`pgtp_editor/ui/code_editor.py:1108`), the
**Edit code…** dialog for a PHP/JS event-handler body. Its `Esc` is Qt's dialog cancel, and since
`Ctrl+S`/`Ctrl+W` were deleted there on 2026-08-09 (owner decision, recorded in the comment at
`code_editor.py:1139-1148`) it is **that dialog's only keyboard cancel at all** — the comment says so
explicitly: OK/Cancel remain reachable "by the button box, by `Return`/`Escape`". A Command mode that
consumed `Esc` there would **delete an exit path**.

**Options.**
- **Vim layer inactive in `CodeEditorDialog`.** `Esc` keeps meaning cancel; no exit is lost. *Cost:* one
  editable editor surface behaves unlike the others, which the manual and the spec must both state, and a
  user who has learned Command mode loses it in that dialog.
- **Command mode active there; cancel only via the button box (or `Alt`-mnemonic).** Uniform vim coverage
  across every editable editor. *Cost:* it removes the dialog's only keyboard cancel, which is a real
  regression for a modal, and it does so on the one surface with **no menu bar** — so the `:` command
  palette has nothing to derive commands from and the mode is a stunted version of itself anyway.

**Recommendation: inactive in that dialog.** It edits a PHP/JS handler body, has no menu bar for the `:`
palette to derive commands from, and is the one editor host whose `Esc` means something irreplaceable. The
alternative is legal but pays a real exit for a keyboard vocabulary that surface's users did not ask for.

**Unblocks:** §8's `Esc` precedence list gaining a stated sixth-case exclusion (a named host where the layer
is off, alongside "read-only"), and the FQ-032 implementation knowing at which hosts to install
`VimModeMixin`.

**Cross-references:** `CONSOLIDATED_SPEC.md` §8's `Esc` ordering (~:3918) and §29's three FQ-032 items.

---

## The pattern across `DEC-260810193637` / `-38` / `-39` — an assumption, not something to re-argue

**Three of three recommendations lost.** All three FQ-032 decisions were answered against
`owner-decision`'s recommendation on the same day, and **two of them (`-38`'s `Ctrl-R` and `-39`'s dialog)
were argued from *"do not withdraw an existing capability"*** — a vim reflex in one case, the editing
vocabulary of one editable surface in the other. **The owner weighed the vim vocabulary's completeness higher
both times.**

**Record it as an assumption for future vim questions.** A filing that recommends *narrow the vim layer to
keep the app uniform* is arguing against a preference the owner has now stated three times, and should say so
and weigh accordingly rather than re-deriving the trade-off per chord.

**The per-chord exception `DEC-260810193638` requires stands above this pattern.** *"Not licence for others"*
means a **second mode-conditional chord is still its own decision** — the pattern predicts how the owner is
likely to weigh it, and does not answer it. Predicting an answer is not having one.

**The mirror-image process failure, recorded once.** All three were **answered, folded into
`CONSOLIDATED_SPEC.md` (`50fe22b`), and left reading `OPEN` here** because the answering session never
dispatched `owner-decision`. The previous pass had just written a rule against a *decision believed filed*;
this is an *answer believed recorded*, and it happened immediately after. **Both failures have one shape: a
queue state inferred from work done elsewhere.** The queue is the record — a ruling that lives only in the
spec is a ruling this file will re-ask, and a sweep would have re-put all three to the owner as open.

---

## DEC-260811022536 — Is the synthesized `CREATE TABLE`'s four-gap incompleteness permanent, or a v1 stopgap to be closed?

- **Status:** ANSWERED (2026-08-11) — **PARTIAL BY INTENT; the deferred half is `DEC-260811094437`.**
- **Answer: close the per-column two now — identity/`SERIAL` and `GENERATED` columns. Inheritance and
  partitioning are ruled on SEPARATELY, later, when a feature actually needs them.** Neither
  *"accept all four permanently"* nor *"close all four"* was taken.
- **Owner's reasoning.** Identity/`SERIAL` and `GENERATED` **extend the existing column rendering rather than
  restructure the statement** — the column data is already in hand — and they are what an ordinary schema
  actually hits, since nearly every table has a surrogate key. Inheritance and partitioning **restructure the
  statement** (partition key, partition-of clauses, per-partition rendering, `INHERITS` with inherited columns
  suppressed) and closing them now would mean **paying for partitioning support before any feature consumes
  it**.
- **The banner therefore STAYS, naming two remaining gaps rather than four**, and — this is the part that must
  not be lost — **it is not to be read as an unfinished job.** The narrower boundary is deliberate: the two
  cheap, common gaps are closed because they are cheap and common, and the two structural ones remain
  **genuinely open** rather than accepted. A future reader finding a two-gap notice should read *"decided
  boundary, pending a consumer"*, not *"someone stopped halfway"*.
- **Wider principle:** a completeness question may be answered per-gap rather than wholesale. Where closing a
  gap restructures the artifact, the gap waits for a feature that consumes the artifact; where it merely
  extends what is already rendered, it is closed on the spot. Cost-to-close and frequency-in-practice are both
  legitimate inputs, and a disclosed boundary is not the same as an unfinished one.
- **THE DEFERRED HALF IS NOW `DEC-260811094437`** (filed 2026-08-11, `OPEN`): *"Do the synthesized `CREATE
  TABLE`'s inheritance and partitioning gaps get closed, and what triggers closing them?"* — trigger
  condition as stated in this answer, the first feature that consumes this buffer as anything other than a
  read-only view. **This entry is fully answered; the open half lives there, not here.** Read
  `DEC-260811094437` before acting on the two remaining gaps.
- **Unblocks:**
  - the per-column half → the main session dispatches **`feature-triage`** to place a follow-up against §18.1
    in `docs/FEATURE_QUEUE.md`: render identity/`SERIAL` and `GENERATED` column attributes in
    `pgtp_editor/db/table_ddl.py`, and shorten the two-line banner (the `"NOT reconstructed: identity/SERIAL,
    GENERATED columns, inheritance, partitioning"` notice) to name **inheritance and partitioning only**;
  - **`spec-maintainer`** records in §18.1 that the boundary is now **two structural gaps, deliberately
    pending a consumer** — not four, and not permanent — so a sweep neither re-files the closed two nor
    enshrines the open two as accepted;
  - **`manual-maintainer`** follows the banner wording wherever the manual quotes it;
  - and it settles the standing question of **how much weight future features may put on this buffer**: it
    round-trips ordinary tables once the per-column work lands, and still does **not** round-trip inherited or
    partitioned ones, so nothing may treat it as a deployment source until that half is ruled on.
- **Raised:** 2026-08-11, by the main session, from `FQ-260810183812` (shipped today, spec §18.1, merge
  commit `9d93fd8`)
- **Blocks:** **nothing today.** The feature is shipped, tested (7357 passed / 51 skipped) and states its own
  limits to the user. This is a **direction call**, and it hardens: every future feature that treats the
  read-only DDL pane as a source of truth raises the cost of closing the gaps later.

**Context.** `FQ-260810183812` gave the **Quality DDL Explorer's read-only pane** a `CREATE TABLE` for every
table (plus views and matviews), so every tree item jumps to its own DDL. The statement is **synthesized from
`pg_catalog`**, not fetched — Postgres does not hand back a `CREATE TABLE` for an existing table — and the
reconstruction covers columns, types, defaults, constraints, indexes and comments.

It has **four known blind spots**, stated in the module docstring at `pgtp_editor/db/table_ddl.py:30-38`:
**identity / `SERIAL` sequences, `GENERATED` columns, table inheritance, and partitioning.** A table using any
of them renders a `CREATE TABLE` missing that clause.

**This is not hidden, and nothing is guessed.** Every table's buffer opens with two SQL-comment lines naming
all four gaps (`table_ddl.py:65-73`, verbatim: *"this is NOT the original CREATE statement. NOT reconstructed:
identity/SERIAL, GENERATED columns, inheritance, partitioning."*). A partitioned or inherited table renders as
the plain table it resembles — no invented `PARTITION BY`, no invented `INHERITS`. The pane is **read-only and
explicitly not a deployment artifact**, so an incomplete statement cannot silently deploy anything wrong.

**Options.**

- **Accept the four gaps permanently.** The buffer's job is *"show me this object"*, the omission is disclosed
  at the top of every buffer, and the read-only boundary means an incomplete statement cannot cause a wrong
  deployment. *Cost:* it caps what the pane can ever be trusted for. The project's stated direction is
  `.pgtp` ↔ database synchronization; if this buffer ever feeds a generated migration, a `CREATE TABLE` that
  cannot round-trip a partitioned or identity-column table stops being cosmetic and becomes a correctness
  bug — and the notice, which reads as temporary today, would have to be rewritten to state the boundary as
  intentional.
- **Close all four.** The pane round-trips any table, and the notice goes away. *Cost:* inheritance and
  partitioning need **additional catalog queries** and **change the statement's structure** (partition key,
  partition-of clauses, per-partition rendering, `INHERITS` with the inherited columns suppressed) — this is
  materially more than the per-column work, and it multiplies the shapes the tests must pin.
- **Close only the per-column two (identity/`SERIAL` and `GENERATED`).** These are **column attributes
  adjacent to what is already fetched**, so they extend the existing column rendering rather than restructure
  the statement — the cheapest correctness-per-effort, and they are also the two most common in ordinary
  schemas (nearly every table has a surrogate key). *Cost:* the notice stays, now naming two gaps instead of
  four, and the harder two remain a standing ceiling; a reader may reasonably read a two-gap notice as an
  unfinished job rather than a boundary.

**Recommendation: close the per-column two now, and rule on inheritance/partitioning separately once
something actually needs them.** Identity and `GENERATED` are the gaps a user will hit on an ordinary schema,
they are cheap because the column data is already in hand, and closing them shrinks the notice to the two
genuinely structural cases — which is the honest place to draw a permanent boundary if one is to be drawn.
Committing now to all four means paying for partitioning support before any feature consumes it; committing
to none means the pane's first impression on a routine table is *"this is incomplete"*.

**What the answer converts into.**
- *"Acceptable permanently"* → no follow-up FQ; the banner text at `table_ddl.py:65-73` is reworded from a
  list of missing things into a **stated intentional boundary**, and `spec-maintainer` records that boundary
  in §18.1 so nobody re-files it as a bug.
- *"Close them"* (all four, or the per-column two) → the main session dispatches **`feature-triage`** to place
  a follow-up against §18.1 in `docs/FEATURE_QUEUE.md`, and the banner becomes explicitly temporary until it
  lands.
- Either way it settles **how much weight future features may put on this buffer**, which is the reason to
  answer it before more is built on it rather than after.

---

## DEC-260811023646 — What are the transaction semantics for a multi-statement run in the Quality SQL Console?

- **Status:** ANSWERED (2026-08-11)
- **Answer: option C — run inside a transaction, show the results, require a deliberate commit gesture.**
  The run goes through `db/apply.py::apply_ddl(..., commit=False)`, the user sees what happened while it is
  still uncommitted, and only an explicit commit gesture makes it durable. Chosen over **B** (per-statement
  commit — what *"mirror the sandbox exactly"* literally means today) and over **A** (one auto-committing
  transaction).
- **Owner's reasoning.** Every *other* guard on this feature had already been ruled away — no
  Maintenance-mode gate, no per-run confirmation beyond the existing object-change dialog, full read/write
  against quality — so **the one remaining safety property must be the strong form, not the inherited one**.
  And *"show me what it did before it is permanent"* is the precise claim `README.md` makes over DBeaver:
  shipping per-statement commit against production would have imported the very behaviour this project
  exists to replace, onto the one surface where it does the most damage. The owner deliberately took the
  option that **adds surface** rather than the one that inherits behaviour.
- **Wider principle:** where a feature's other guards have been deliberately removed, the guard that remains
  is chosen on its own merits and never by analogy to a surface with a different blast radius. Consistency
  with the sandbox is not an argument on a target that has no `reset()`.
- **The held-open connection is accepted as real new surface, and its edges are a REQUIREMENT of the
  implementation, not an open question.** Neither existing seam holds a connection between calls (both
  `SandboxExecutor.fetch` and `apply_ddl` open and close per call), so the quality console must, and it must
  have a **defined, tested behaviour on tab close, on window close, and on connection loss** with an
  uncommitted run outstanding. Whoever implements it decides those three behaviours as part of the work —
  they are not a further decision to file.
- **Unblocks:** `FQ-260811020328`'s last open seam, and therefore the whole feature. Concretely: the quality
  execution path calls `apply_ddl(..., commit=False)`; the console gains a commit/rollback affordance; the
  results grid gains an uncommitted-state representation; the three lifecycle behaviours above are defined.
  Because this is **new surface** rather than a variation of the shipped panel, the main session routes it
  through **`feature-triage`** against `FQ-260811020328` rather than straight into implementation.
- **`spec-maintainer` owes:** the two consoles now differ, deliberately — **one panel class, two commit
  policies** — which must be recorded in §18.5's console section with this reasoning, against the corrected
  D4 paragraph (`CONSOLIDATED_SPEC.md` §18.5, *"Multiple statements, transactions, and what commits"*, the
  ⚠ CORRECTED TO WHAT SHIPPED block) rather than against the spec's superseded letter.
  **`manual-maintainer` owes:** the manual's running-SQL sections must state which console commits when.
- **Load-bearing for `DEC-260811025132`:** that entry's answer (keep `Ctrl+Return`) is conditional on this
  one. See the dependency recorded there.
- **Raised:** 2026-08-11, by the main session, from `FQ-260811020328` (Quality SQL Console), which flags this
  as the one place where its own *"mirror the sandbox console exactly"* directive may be the wrong instinct
  and explicitly leaves it here.
- **Blocks:** **one seam, not the feature.** Everything else in `FQ-260811020328` — the tab, the menu action,
  the availability gate, the connection source, the shared console widget, completion, the results grid and
  the danger marking — is being implemented now, with the commit behaviour isolated behind the single
  execution seam so the answer drops into one place. **Do not read this entry as a reason to stall the
  feature.**

### ⚠ Correction to the MECHANISM named in this entry — not to the answer (recorded 2026-08-12)

**The ruling shipped exactly as decided and is not reopened.** Option C — run into an uncommitted
transaction, inspect, then an explicit Commit gesture — is what `FQ-260811020328` shipped (commit
`6258349`, full suite green). The owner's answer, reasoning and status above stand unchanged. **This note is
not a question and needs no owner attention.**

**What is wrong is the implementation mechanism this entry names.** Several places above say the run goes
through `db/apply.py::apply_ddl(..., commit=False)` — the Answer bullet, the Unblocks bullet, consequence 2
of the premise correction, option C's description, and "What the answer converts into". **It does not, and
it cannot.** `apply_ddl` commits or rolls back **before it returns** (`pgtp_editor/db/apply.py:347-352`), so
it can never hold a transaction open between the Run and the Commit gesture — which is the entire substance
of option C. The entry contradicts itself internally: option C's own cost line already says the connection
"must be **held open** between the run and the commit gesture, which neither existing seam does".

**What actually shipped.** `db/apply.py` was **not touched**. The path is a new
`pgtp_editor/db/quality_query.py` with a `QualitySession` (`:395`) that holds the connection and the
transaction across calls, exposing `run` (`:481`), `commit` (`:554`) and `close` (`:600`) — the last
covering the tab-close / window-close / connection-loss behaviours this entry required. A future reader
following `apply_ddl` will look for a transaction it never holds; read `quality_query.py` instead.

**Whose error this was.** The `apply_ddl` sentence was written by the filing session into the question put
to the owner. It is a mistake in the framing, not in the ruling.

**The durable rule, and why this note exists at all.** `spec-maintainer` folded the correction into
`CONSOLIDATED_SPEC.md` §18.5 with a Supersession Ledger row, and recorded the general principle: **"a
decision entry names an OUTCOME authoritatively and a MECHANISM only provisionally."** Read every decision
entry that way — the owner rules on what must be true, and any seam, function or file named alongside it is
the filing session's best guess at the time and may be superseded by implementation without reopening the
decision.

**Already settled by the owner, and NOT in question here.** The console is **full read/write** against
quality, and it is **always available** whenever a quality connection with a password exists — no
Maintenance-mode gate, no extra per-run confirmation beyond the existing object-change dialog.

### ⚠ Correction to the premise the question arrived with — verified in the tree, 2026-08-11

The filing request stated that the sandbox console *"runs all statements of a submission in one committing
transaction"*, which would make "inherit the sandbox" and "one transaction" the same answer. **The code says
the opposite, and the two must not be conflated.**

- `SqlConsolePanel` **splits the submission** (`split_statements`) and runs the statements **one at a time**,
  **stopping at the first failure** (`pgtp_editor/ui/sql_console_panel.py:774`, `:789-802`). Its own comment
  states the semantics outright: *"each `run_query` call is one `SandboxExecutor.fetch`, i.e. **its own
  committing transaction**, so continuing past a failure would pile more committed changes on top of a broken
  Run."*
- That is accurate at the seam: `_PsycopgSandboxExecutor.fetch` opens **its own connection per statement** and
  commits it (`pgtp_editor/db/sandbox.py:965-1003`, `connection.commit()` at `:997`, rollback-and-raise at
  `:999`).

**So the sandbox console is ALREADY per-statement commit.** "Mirror the sandbox exactly" therefore means
**option B below**, not option A. Option A is a *departure* from the sandbox, not the conservative inheritance
it looked like. The owner should answer knowing which way the consistency argument actually points.

**Two consequences of the correction, also verified.**
1. Option B's follow-on question — *what do we report when statement N of M fails after N−1 committed?* — is
   **already answered by shipped behaviour**, not open: the run stops at the failure and reports the statements
   that ran out of the total (`RunReport(runs=..., total=len(statements))`, `sql_console_panel.py:802`).
   Choosing B costs no new reporting design.
2. Options A and C **cannot use the `fetch` seam at all** (one connection per statement, so a submission
   cannot share a transaction). They must run through `db/apply.py::apply_ddl`, which **already does exactly
   what they need**: *"Run `statements` as **one transaction** against `target`… per statement"*, where
   `target` is any `ConnectionParams`, and it already carries a **`commit=False`** mode that runs the
   identical list and rolls it back (`pgtp_editor/db/apply.py:568-609`). So A and C are cheaper than they
   look — the machinery exists and is quality-capable today.

**Context.** The two settled rulings above removed every other guard on this feature: no mode gate, no extra
confirmation, full DDL/DML against a production-adjacent database. **Commit semantics are therefore the last
remaining safety property**, and picking it by analogy to the sandbox would decide the feature's actual risk
profile as a side effect of a consistency argument. It also cuts against the project's stated identity:
`README.md` describes a safe/fast IDE that closes DBeaver's *"the only option is to break the DB"* gap —
option B imports DBeaver's behaviour, option C goes further than DBeaver in the safe direction, option A is
neither and is defensible on its own terms.

**Options.**

- **A — One committing transaction for the whole submission.** All-or-nothing: a run that fails halfway
  leaves **nothing** behind, which is the strongest automatic protection for a production database and needs
  no new UI. *Cost:* it **diverges from the sandbox console** (see the correction above), so one console
  behaves unlike the other and both the manual and the spec must say why; it forbids statements PostgreSQL
  cannot run inside a transaction block (`CREATE DATABASE`, `CREATE INDEX CONCURRENTLY`, `VACUUM`), which
  simply fail in quality where they would have worked per-statement; and a long submission holds locks for
  its whole duration on a live database.
- **B — Per-statement commit, stopping at the first failure (what the sandbox does today).** Identical
  behaviour across both consoles, matches DBeaver and therefore the user's muscle memory, no new reporting
  design (point 1 above), and the smallest implementation. *Cost:* a failure halfway leaves the database
  **partially applied** — precisely the outcome this project exists to prevent — and unlike the sandbox there
  is no `reset()` to undo it. The blast radius that is acceptable on a disposable sandbox is being inherited,
  unexamined, by a database that is not disposable.
- **C — Run inside a transaction, show the results, require a deliberate commit gesture.** Strongest safety:
  the user sees what happened before anything is durable, and a bad run is a rollback rather than an incident.
  `apply_ddl(commit=False)` already supports the "run and roll back" half. *Cost:* a real departure from
  "mirror the sandbox exactly" and **new UI the sandbox console does not have** — a commit/rollback affordance
  plus a results grid that must represent an uncommitted state; the connection must be **held open** between
  the run and the commit gesture, which neither existing seam does (both open a connection per call and close
  it); and it introduces a state the app must handle on tab close, window close and connection loss.

**Recommendation: C, with A as the fallback if the held-open connection proves too much surface for this
feature.** The settled rulings deliberately removed every other guard, so the remaining one should be the
strong form rather than the inherited one; and *"show me what it did before it is permanent"* is exactly the
capability the README claims over DBeaver, on the one surface where the claim is tested. **B is the option to
be most careful about**, because it is the one that arrives by default: it is what "mirror the sandbox" now
literally means, it is the cheapest to build, and it is the only option whose failure mode is a
half-applied production schema. If C's surface is judged too large for a first version, **A** buys most of
the safety for none of the UI — but it is a divergence from the sandbox console and must be stated as one,
not slipped in as consistency.

**What the answer converts into.**
- **A** → the quality execution path runs the split statements through `db/apply.py::apply_ddl(...,
  commit=True)` in one call; results render from `ApplyOutcome`'s per-statement attribution. No new UI.
- **B** → the quality path is a near-copy of `run_sandbox_query`/`fetch` against quality params; the existing
  `RunReport` rendering is reused unchanged. Smallest diff, and the console's per-statement-commit comment
  must be restated for a non-disposable target.
- **C** → `apply_ddl(..., commit=False)` for the run, plus a held-open connection, a commit/rollback
  affordance on the console, an uncommitted-state representation in the results grid, and a rule for what
  happens to an uncommitted run on tab/window close. This is **new surface**, so the main session routes it
  through **`feature-triage`** against `FQ-260811020328` rather than straight into implementation.
- Any answer other than B means the two consoles differ, which **`spec-maintainer`** must record in the
  console section (one console, two commit policies, with the reason) and **`manual-maintainer`** must state
  where the manual describes running SQL.

---

## DEC-260811025132 — Should `Ctrl+Return` (Run) be live on the Quality SQL Console at all?

- **Status:** ANSWERED (2026-08-11)
- **Answer: option 1 — keep `Ctrl+Return`, identical to the sandbox console.** The shared panel's
  `_run_shortcut` (`pgtp_editor/ui/sql_console_panel.py`, the `QShortcut` built immediately after
  `_format_shortcut` in `__init__`) stays unconditional; no construction-time flag, no per-instance
  divergence row in `docs/KEYBINDINGS.md`.
- **Owner's reasoning — and this is CONDITIONAL ON `DEC-260811023646` BEING ANSWERED A3/C, not a standalone
  preference.** Under C the **commit gesture is the point of no return, not the Run key**. Pressing
  `Ctrl+Return` therefore executes into an *uncommitted* transaction the user then inspects — so it does not
  put an irreversible outward effect one keystroke away. The app's rule (§18.5; `README.md:50`; the
  no-shortcuts-on-Deployment invariant pinned by `tests/ui/test_ddl_object_editor.py`'s Deployment-menu
  shortcut assertion) is **preserved in substance rather than waived**, which is exactly why option 1 is not
  a reversal of it.
- **⚠ DEPENDENCY, recorded as a dependency and not a preference — read this before changing the commit
  model.** If the Quality SQL Console's commit model is ever changed to **per-statement commit** or to a
  **whole-run auto-commit**, this answer's justification **collapses**: `Ctrl+Return` would then be one
  keystroke from a durable production change, and the chord **must be revisited** (options 2 and 3 in this
  entry are the alternatives on the table). A future session must not read "`Ctrl+Return` is live on the
  quality console" as settled independently of C. The two rulings ship and stand together.
- **Wider principle:** a shortcut's admissibility is a property of **what the gesture makes durable**, not of
  what it is called. The same chord can be legitimate on one host and not on another, and when a host's
  durability model changes, every chord justified by that model is reopened.
- **Still required regardless of this ruling, and NOT optional.** The recorded justification for the
  `Ctrl+Return` carve-out contains the sentence *"there is no target-database Run to reach with or without a
  key"*, which becomes **false the moment `FQ-260811020328` ships**. It exists in **three** places, all
  verified 2026-08-11, and all three must be replaced with the A3/C-based justification above (*"the commit
  gesture, not the Run key, is the point of no return"*):
  1. `pgtp_editor/ui/sql_console_panel.py` — the comment block above `self._run_shortcut = QShortcut(...)`;
  2. `docs/KEYBINDINGS.md` — the `Ctrl+Return` row, whose Notes end *"The sandbox is disposable and
     `reset()`-able, so this does not reopen 'an irreversible outward effect must not be one keystroke
     away'."* The row's **Surfaces/description also still says "Sandbox SQL Console" only** and must be
     widened to both consoles;
  3. `pgtp_editor/ui/shortcut_registry.py` — the `RESERVED_SEQUENCES` value
     `"Run, on the Sandbox SQL Console tab (§27)"`, same widening.
  `owner-decision` does not edit those files: **`spec-maintainer`** owns the spec/§27 justification and the
  ledger row, the **main session** owns the code comment and the registry string, and
  **`manual-maintainer`** owns the manual's `Ctrl+Return` mentions.
- **Unblocks:** the chord needs no work at all — it already exists in the shared panel and simply is not
  withheld. What this converts into is purely the three-site wording correction above, which lands with
  `FQ-260811020328`.
- **Raised:** 2026-08-11, by the main session, from `FQ-260811020328` (Quality SQL Console) as folded into
  `CONSOLIDATED_SPEC.md` §18.5 **D4b**, and independently flagged by `spec-maintainer` on the fold
  (`CONSOLIDATED_SPEC.md:57-63`).
- **Blocks:** **nothing.** D4b can be built now with Run on the button; the chord is three lines in one
  place (`sql_console_panel.py:579-583`) and is added or withheld once this is answered. Do not stall the
  feature on it.
- **Answer with `DEC-260811023646`.** The two compound (see below) and are best put to the owner together.

**Already settled by the owner and NOT in question here.** The quality console is **full read/write**
against the production database, and it is **always available** whenever a quality connection with a
password exists — no Maintenance-mode gate, no per-run confirmation beyond the existing object-change
dialog for DDL/unknown statements.

**Context.** D4b mirrors the Sandbox SQL Console (`pgtp_editor/ui/sql_console_panel.py`) but executes
against production. The feature entry's keyboard analysis concluded that `Ctrl+Return` needs **no new
chord, no `RESERVED_SEQUENCES` entry and no ledger row**: it is the same panel class answering the same
chord under DEC-009, hosted as a `QShortcut` with `WidgetWithChildrenShortcut` scope so two open consoles
cannot contend. **That analysis is correct about mechanism** and is not what is being asked. The question
is whether the chord *should* be there, and this is the one place where "mirror the sandbox exactly" is
worth interrogating rather than inheriting.

**Verified in the tree, and this is the crux.** The app's rule is *"an irreversible outward effect must not
be one keystroke away"* (§18.5; `README.md:50`; no Deployment-menu item carries a shortcut, pinned by
`tests/ui/test_ddl_object_editor.py:1655`). `Ctrl+Return` is the **single stated exception**, and every
place that records it justifies the exception with **two premises, both of which D4b falsifies**:

- `pgtp_editor/ui/sql_console_panel.py:570-578` — *"the sandbox is disposable and `reset()`-able, so this
  does not reopen the 'an irreversible outward effect must not be one keystroke away' rule — **and there is
  no target-database Run to reach with or without a key**."*
- `docs/KEYBINDINGS.md:78` and `pgtp_editor/ui/shortcut_registry.py:326` carry the same reason, verbatim in
  the ledger row.

D4b **is** the target-database Run the comment says does not exist, and it is not disposable and has no
`reset()`. So this is not a new carve-out being requested; it is an existing carve-out whose stated reason
stops holding for one of its two hosts. Whichever way the owner rules, that wording must be corrected.

**The concrete exposure.** Every other guard on this feature has been deliberately removed by owner ruling.
For a plain `UPDATE`/`DELETE` with no `WHERE`, `Ctrl+Return` is the entire distance between a typo and a
committed production change — on a visually similar tab, using a chord the user's fingers already know from
the sandbox console.

**Compounding with `DEC-260811023646` (multi-statement transaction semantics).** If that is answered
**B — per-statement commit** (which, note, is what "mirror the sandbox" *literally* means today, verified
there), a single stray `Ctrl+Return` can leave production **half-changed**. If it is answered **C —
confirm/commit gesture**, a stray `Ctrl+Return` is far less consequential and option 1 below becomes much
easier to accept. Answering this one without that one decides risk twice.

**Options.**

- **1 — Keep it, identical to the sandbox.** Lowest friction, no new mechanism, nothing to explain to a
  user moving between the two consoles; the danger marking and the distinct tab title carry the warning.
  *Cost:* the app's one shortcut-carrying execution gesture becomes a production write, and its recorded
  justification has to be rewritten from "the sandbox is disposable" into an argument that a production
  write **is** acceptable one keystroke away — which is a reversal of a rule stated in the README, the spec,
  the manual and a test.
- **2 — Keep it, but require the Run *button* for the first run of a session on that tab** (thereafter the
  chord works). Muscle memory cannot fire blind on a freshly opened tab; the chord still serves the user who
  has consciously engaged with the surface. *Cost:* a stateful, invisible rule — the same keystroke works or
  does nothing depending on history the user cannot see, which is exactly the kind of behaviour that reads
  as a bug; a new "has run once" state to define, test and document; and it does nothing about the
  **second** typo, which is as expensive as the first.
- **3 — Do not bind it on the quality console; Run is button-only there.** The asymmetry is itself the
  signal: the gesture that means *go* in the sandbox deliberately does nothing here, which is the same
  device already used for the Deployment menu. Keeps the "one keystroke away" rule intact and its recorded
  reason true. *Cost:* breaks "mirror the sandbox exactly", so `docs/KEYBINDINGS.md` needs a stated
  per-instance divergence (one chord, live on one host of the panel class and inert on the other — the
  ledger has no such row shape today) and the manual must say so; and a user who has learned the chord will
  press it and get silence, which must be worth more than the friction it costs.

**Recommendation: 3 — button-only on the quality console**, unless `DEC-260811023646` is answered **C**, in
which case **1** is acceptable because the commit gesture, not the chord, becomes the point of no return.
The reasoning is that the exception's own recorded justification is a statement about disposability, and
disposability is precisely what the quality console does not have; a rule that survives only by rewriting
its reason was not the rule. Option 2 buys the least: it keeps the failure mode and adds hidden state.

**What the answer converts into (one place, either way).**
- **1** → keep the `QShortcut` block in the shared panel unconditional; `spec-maintainer` rewrites the
  §18.5 D4/§27 justification and `docs/KEYBINDINGS.md:78`, and `shortcut_registry.py:326`'s description
  ("Sandbox SQL Console" only) must be widened; `manual-maintainer` updates
  `resources/manual.md:4694, 4922-4928`.
- **2** → same, plus a per-tab "first run has happened" gate on the shortcut's `setEnabled`, with a test.
- **3** → the shared panel gains one construction-time flag controlling whether `_run_shortcut` is created
  at all (the quality console passes it off); `docs/KEYBINDINGS.md:78` gains the stated divergence;
  `resources/manual.md`'s three `Ctrl+Return` sites gain *"Sandbox console only"*.
- Either way, **the falsified sentence *"there is no target-database Run to reach with or without a key"*
  must be removed** from `sql_console_panel.py:573-574` — it is untrue the moment D4b ships, independent of
  this ruling.

---

## DEC-260811025733 — Is `Add Trigger…` deliberately offered on view and matview nodes, or is that an oversight?

- **Status:** ANSWERED (2026-08-11)
- **Answer: option 1 — intended for views, excluded for matviews, and the dialog is gated by relation kind.**
  `Add Trigger…` stays offered for `kind in ("table", "view")` and is excluded for `matview`; and
  `NewTriggerDialog` becomes kind-aware — a **view** target offers `INSTEAD OF` only, a **table** target
  offers `BEFORE`/`AFTER` only. The largest of the three options was chosen because it is the only one that
  makes the gesture *actually correct* on a view.
- **Owner's reasoning.** **The split is PostgreSQL's, not a preference:** `INSTEAD OF` on a view is the
  standard way to make a view updatable and is squarely in scope for this app, while materialized views
  support no triggers at all. And per-kind reasoning is the **established local pattern rather than a new
  one** — the two neighbouring gestures in the same context-menu builder already answer *"does this gesture
  mean something on a view?"* per gesture: `Create Table…` includes a view's node with an explicit comment
  (*"what you create is a table regardless of what you clicked"*), and `_add_alter_table_submenu` excludes
  views and matviews with an explicit early return. `Add Trigger…` was the one branch expressing no intent.
- **This closes a LIVE DEFECT, not a tidiness item — record it as such.** Today, from a view node, a user can
  pick `BEFORE INSERT` and get a rendered, authoritative-looking statement the server rejects. Verified
  2026-08-11: `NewTriggerDialog.__init__` takes `table: str` and never learns the kind; it fills its timing
  combo with the unfiltered `db/ddl_skeleton.py::TRIGGER_TIMINGS = ("BEFORE", "AFTER", "INSTEAD OF")`;
  `trigger_skeleton` validates only against that same tuple, its docstring saying *"`INSTEAD OF` is view-only
  in Postgres; that is the caller's constraint to enforce, not this emitter's"* — **and no such caller
  existed.** Option 2 (document today's behaviour) was rejected for exactly this reason: it is the one state
  `_add_alter_table_submenu`'s own docstring principle rejects — *not offered* rather than *offered and
  broken*.
- **Wider principle:** where a shared tree role spans several relation kinds, each gesture on that role must
  state its own per-kind answer. A branch that expresses no intent is the shape by which a narrow rule gets
  widened by analogy — which has already cost this project twice in the shortcut area (BUG-052, BUG-063).
  And **the emitter's disclaimer is only honest if the caller it names exists**: a docstring delegating a
  constraint to "the caller" with no caller is a defect, not a division of labour.
- **Unblocks — the implied work, for the main session to route:**
  1. the `kind` check on the `Add Trigger…` branch in `pgtp_editor/ui/ddl_buffer_panel.py::_context_menu_for`,
     with a docstring stating the intent as `Create Table…`'s neighbouring comment does;
  2. the relation kind threaded into `NewTriggerDialog`, with the timing list filtered per kind;
  3. `tests/ui/test_new_trigger_dialog.py`'s assertion that the combo equals `TRIGGER_TIMINGS` verbatim
     becomes **kind-conditional**;
  4. `db/ddl_skeleton.py`'s `TRIGGER_TIMINGS` / `trigger_skeleton` docstrings **stop disclaiming a check that
     now has a caller**;
  5. **`spec-maintainer`** settles the spec's explicit either/or (§18's trigger dialog note, *"the dialog's to
     enforce or to leave to the database"* — it is now **the dialog's**);
  6. **`manual-maintainer`** reconciles the three inconsistent manual lines (`resources/manual.md`: *"right-click
     a **table** node"* vs. the two passages saying a view's and a matview's node still offer `Add Trigger…`).
- **Raised:** 2026-08-11, by `manual-maintainer`, while recounting the `Alter Table ▸` submenu against
  `pgtp_editor/ui/ddl_buffer_panel.py`. Verified against the tree before filing.
- **Blocks:** **nothing** — nothing is mid-build on this path. It hardens with time: the code currently
  expresses *no intent* at this one branch while both of its neighbours state theirs, so the next person to
  read it will guess, and a guess written as a comment is how a narrow rule gets widened by analogy (this
  has already happened twice in the shortcut area, BUG-052 and BUG-063).

**Context — what the code actually does today (all verified).**

Since `FQ-260810183812` widened the DDL Explorer's **Tables** branch to views and materialized views,
every relation node carries `_TABLE_ROLE` regardless of kind (`ddl_buffer_panel.py:1195-1206`;
`introspect.TableInfo.kind ∈ {"table","view","matview"}`, set from `relkind` in `('r','p','v','m')`).
Inside the single context-menu builder `_context_menu_for`, three adjacent gestures treat that uniformly-set
role three different ways:

- **`Add Trigger…`** (`ddl_buffer_panel.py:1556-1565`) keys on `_TABLE_ROLE` with **no `kind` check** and no
  comment about kinds. So it is offered on table, view **and** matview nodes.
- **`Create Table…`** (`:1566-1573`) has the same reach and its comment **explicitly justifies** including a
  view's node: *"what you create is a table regardless of what you clicked"*.
- **`Alter Table ▸`** (`_add_alter_table_submenu`, `:1631-1667`) opens with
  `if getattr(table_info, "kind", "table") != "table": return None`, under a docstring paragraph headed
  *"Views and materialized views get no submenu"*.

So within one function: one gesture reasons about views explicitly, one excludes them explicitly, and this
one does neither.

**Why this is a decision and not an obvious bug.** PostgreSQL genuinely supports `INSTEAD OF` triggers on
views — the standard way to make a view updatable, squarely within what this app is for. Offering the
gesture on a view may be correct and valuable.

**But the surface behind it is kind-blind, and that is the sharp edge.** `NewTriggerDialog.__init__` takes
`table: str` and nothing else (`pgtp_editor/ui/new_trigger_dialog.py:97-116`) — it never learns the relation
kind — and it fills its timing combo with `TRIGGER_TIMINGS` unfiltered, i.e. `("BEFORE", "AFTER",
"INSTEAD OF")` (`db/ddl_skeleton.py:104`). `trigger_skeleton` validates the timing against that same tuple
and no further (`ddl_skeleton.py:155-158`), its docstring saying *"`INSTEAD OF` is view-only in Postgres;
that is the caller's constraint to enforce, not this emitter's."* **Nothing downstream is that caller.** So
from a view node today the user can pick `BEFORE INSERT` and get a rendered, authoritative-looking statement
Postgres will reject — the worst of the three possible states, because it looks supported.

**The spec does not settle it.** `CONSOLIDATED_SPEC.md:7037-7038` says the `INSTEAD OF` constraint is *"the
**dialog's** to enforce or to leave to the database"* — an explicit unresolved either/or, not a ruling.

**Matviews are a third case.** PostgreSQL supports **no** triggers on materialized views at all. The tree
does distinguish them (`kind == "matview"`), so a per-kind answer is expressible; the current branch simply
does not ask.

**The manual is already inconsistent with itself**, which is a symptom rather than a separate problem:
`resources/manual.md:2381` says *"right-click a **table** node"* for this gesture, while `:2518` says
*"A view's node still offers the two creation entries, **Add Trigger…** and **Create Table…**"* and `:2644`
repeats it for views and matviews. Whichever way this is answered, one of those lines is wrong.

**Options.**

- **1 — Intended for views, excluded for matviews.** Keep the gesture on `kind in ("table", "view")`, add
  the `kind` check only for `matview`, and make the dialog kind-aware: a view target offers `INSTEAD OF`
  only, a table target offers `BEFORE`/`AFTER` only. *Cost:* `NewTriggerDialog` gains a parameter it does
  not have today (a signature change with existing tests over the offered timings —
  `tests/ui/test_new_trigger_dialog.py:99` asserts the combo equals `TRIGGER_TIMINGS` verbatim, so that
  assertion has to become kind-conditional), plus the docstring, the spec's open either/or and two manual
  lines. It is the largest of the three, and it is the only one that makes the gesture *actually* correct
  on a view.
- **2 — Intended for views, dialog left unfiltered** (i.e. today's behaviour, merely documented). *Cost:*
  keeps the state where a view node leads to a statement the server refuses; the spec's "or to leave to the
  database" sentence covers it, but the refusal surfaces only at execution, long after the user believed the
  app had offered them the option. Cheapest to write, most expensive to use.
- **3 — Oversight, remove it.** Add `if kind != "table"` to the `Add Trigger…` branch, exactly mirroring
  `_add_alter_table_submenu`'s existing exclusion, and fix `manual.md:2518, 2644`. *Cost:* the app then has
  **no** path to an `INSTEAD OF` trigger from the tree, so making a view updatable — a real, in-scope
  Postgres technique — must be done by hand or via a later feature. The exclusion would be honest about
  scope but would withdraw a capability that partly works today (the dialog does render a correct
  `INSTEAD OF` statement if the user picks it).

**Recommendation: 1.** The two neighbouring gestures show the codebase already treats "does this gesture
mean something on a view?" as a question worth answering per gesture rather than per role, and for triggers
the honest answer is *yes for views, no for matviews* — that is Postgres, not a preference. Option 2 is the
one state the `Alter Table ▸` docstring's own principle rejects (*"offering a table mutation on a view would
generate DDL the server refuses… not offered rather than offered and broken"*); applying that principle here
means either fixing the timings or removing the gesture, not documenting the breakage. Option 3 is
defensible and cheap if `INSTEAD OF` triggers are out of scope for v1 — but that is the owner's call about
product scope, which is why this is filed rather than decided.

**What becomes possible once answered.**
- **1** → one `kind` check at `ddl_buffer_panel.py:1556`, a kind argument threaded into `NewTriggerDialog`
  with the timing list filtered, an updated `tests/ui/test_new_trigger_dialog.py:99`, a docstring at the
  menu branch stating the intent as `Create Table…`'s does, `spec-maintainer` closing §18's open either/or
  at `CONSOLIDATED_SPEC.md:7037-7038`, and `manual-maintainer` reconciling `manual.md:2381` with `:2518/2644`.
- **2** → docstring + spec sentence + the manual reconciliation only; no code change.
- **3** → the `kind` check alone, plus the manual reconciliation; `manual.md:2381` becomes correct as written.

---

## DEC-260811094437 — Do the synthesized `CREATE TABLE`'s inheritance and partitioning gaps get closed, and what triggers closing them?

- **Status:** ANSWERED (2026-08-12) — **but SUPERSEDED IN DIRECTION: the owner rejected the frame of the
  question rather than choosing an option. See the answer below and `FQ-260812022749`. The three options
  survive as the FALLBACK if the `pg_dump` route is rejected at design time.**
- **Raised:** 2026-08-11, by the main session — this is the **deferred half of `DEC-260811022536`**, split out
  as that entry's answer directed. `DEC-260811022536` is otherwise ANSWERED and closed.
- **Blocks:** ~~**nothing today.** Nothing in the tree consumes the synthesized `CREATE TABLE` as anything but
  read-only text. It **hardens** with every feature built on that buffer, and unlike most deferred items it
  has a **named trigger**, so it can be answered in advance rather than only in hindsight.~~
  **SUPERSEDED BY THE 2026-08-12 CORRECTION BELOW — this is no longer "blocks nothing". It blocks the
  restricted-mode half of `FQ-260812022749`'s design.** See **CORRECTION (2026-08-12) — the trigger
  condition, restated** at the end of this entry.

**Context (written for a cold reader).** §18.1's DDL Explorer shows a single read-only buffer containing a
`CREATE TABLE` for every table, **synthesized from `pg_catalog`** by `pgtp_editor/db/table_ddl.py` — Postgres
has no `pg_get_tabledef`, so it is a reconstruction from columns, types, defaults, constraints, indexes and
comments. Four things it does not reconstruct: identity/`SERIAL`, `GENERATED` columns, table **inheritance**,
and **partitioning**. Nothing is ever guessed — a partitioned table renders as the plain table it resembles,
with no invented `PARTITION BY` — and every table's text carries a two-line SQL-comment notice naming the
gaps (`table_ddl.py:67-74`).

On 2026-08-11 the owner answered `DEC-260811022536` **partially and by intent**: close the two **per-column**
gaps now (identity/`SERIAL`, `GENERATED`), because they extend the existing column rendering rather than
restructure the statement and they are what an ordinary schema actually hits — nearly every table has a
surrogate key. The two **structural** gaps were deferred, with the reason stated: closing them now means
**paying for partitioning support before any feature consumes it**. This entry is that deferred half.

**Verified state of the tree at filing time.** `RECONSTRUCTION_NOTICE_DETAIL` at `table_ddl.py:71-74` still
names **all four** gaps verbatim — the per-column work is in flight in the main session and has not landed.
That does **not** affect this entry's premise: the structural pair is deferred by the owner's recorded ruling,
not by the state of the banner. When the per-column work lands the banner shortens to name **inheritance and
partitioning only**, and this decision is unchanged either way.

**Why the trigger is a real question and not hypothetical, but also not imminent.** *(⚠ The trigger stated in
this paragraph was written under the migration-generator framing and **has been restated** — see
**CORRECTION (2026-08-12)** at the end of this entry. Read that first; the paragraph below is kept for the
record of how the condition was originally derived.)* `DEC-260811022536`'s answer names the condition: *the
first feature that consumes this buffer as anything other than a read-only view.* While the text is only ever shown, an omitted `PARTITION BY` is incomplete but harmless and the notice
says so; the moment it becomes an **input** — a generated migration, a deployment script, a `.pgtp` ↔ database
sync step, a diff — the omission becomes a wrong answer that looks authoritative. Two verified facts sharpen
this:

- **§18.5's `Generate Deployment SQL` is the spec's rank-1 unbuilt deliverable**, so a consumer is coming.
- But it is specified to be built on `db/schema_diff.py` + `db/migration_gen.py`, **not** on this buffer, and
  `migration_gen.py` today **refuses table and column differences outright** (`UnsupportedDifference`; its
  docstring: *"Emit routine and trigger migration SQL — NOT table or column migrations"*, and its emitted
  script carries `_NOTE` saying so). So the trigger is not `Generate Deployment SQL` shipping — it is
  **`migration_gen` gaining `object_kind="table"` support**, at which point it needs a table renderer and
  `table_ddl.py` is the only pure one in the tree. That is the concrete, greppable trigger.

**Options.**

1. **Close them when the first consuming feature is designed, not before.** Keeps the cost where the benefit
   is; the notice names the two gaps in the meantime. *Cost:* the consuming feature carries the work as a
   dependency and is that much larger, and **whoever designs it must notice the dependency** — the notice
   lives in the buffer, not in the spec section they will be reading. That is a real failure mode, not a
   theoretical one.
2. **Close them pre-emptively, before any consumer exists.** Removes the dependency and the notice entirely;
   the pane round-trips any table. *Cost:* exactly the *"paying for partitioning before anything consumes
   it"* the owner already declined — extra catalog queries, a restructured statement (partition key,
   partition-of clauses, `INHERITS` with inherited columns suppressed), and the largest test-shape growth of
   any option.
3. **Close them never; make the boundary permanent and structural.** §18.1 documents the pane as showing a
   *representation*, and any consuming feature is **required** to source its DDL elsewhere. *Cost:*
   forecloses the cheapest path for a future migration generator (it would have to grow a second table
   renderer, i.e. the drift `table_ddl.py`'s own docstring warns about for constraint text), and the boundary
   has to be asserted somewhere a future designer will actually hit.

**Recommendation: option 1, plus one addition that costs almost nothing and fixes its only real weakness.**
Record the dependency in `CONSOLIDATED_SPEC.md` **§18.1** *and* in **§18.5's `Generate Deployment SQL`**
section, so a designer reading either one encounters it — rather than relying on someone noticing two
SQL-comment lines inside a buffer. Option 2 spends now what the owner just declined to spend. Option 3 is
defensible but buys permanence at the price of guaranteeing a duplicate renderer later, and it is the one
option that cannot be reversed cheaply once a second renderer exists.

**What becomes possible once answered.**
- **1** → `spec-maintainer` writes the dependency into §18.1 and §18.5 (*"table DDL synthesis does not cover
  inheritance or partitioning; any feature consuming it as an input must close those first"*); no code change
  today, and the notice's remaining two lines are then explained by the spec rather than only by themselves.
- **2** → `feature-triage` places an FQ against §18.1 to extend `table_ddl.py` with partitioning and
  inheritance (plus the catalog queries in `introspect.py`), and the notice is deleted when it lands.
- **3** → `spec-maintainer` states the boundary as permanent in §18.1, rewords the notice from a list of
  missing things into an intentional boundary, and adds the sourcing constraint to §18.5 so no future
  migration generator reaches for this buffer.

### ANSWER (2026-08-12) — **none of the three; the approach itself is redirected**

The owner picked **no option**. They rejected the premise that the two structural gaps should be closed by
extending the hand-rolled synthesizer at all. **Verbatim:**

> *"serial in postgres is an int4 with default value at nextval('[any sequence]');. Defaults should show, so
> serial shows. creating a table column as serial (or bigserial) or uuid, is not an issue as postgres
> silently handles the creation of sequence and defaulting to nextval(). for the complete ddl you don't need
> any special treatment, just a pg_dump. we can easily make this dependency... we can only create table ddls
> if the correctly versioned pg_dump is on the local machine. this probably would simplify many many
> problems. indeed, would simplify all ddl issues, if psycopg can't do it."*

There are **two distinct things** in that answer, and they are recorded separately because only one of them
supersedes this entry.

**(1) A confirmation of shipped behaviour — `SERIAL` needs no special casing.** `SERIAL` is not a type: it is
`int4` with a `DEFAULT nextval('…')`, so **rendering the default IS rendering `SERIAL`**, and the same holds
for `bigserial`; Postgres creates the sequence and the default silently on the way in. This endorses what
shipped in `69473cd`, where an implementer's judgement made that call. It now has an owner's ruling behind
it and should not be revisited as an open question. **The durable form:** where Postgres expresses sugar as
an ordinary catalog fact, reconstruct the fact, not the sugar.

**(2) A change of approach that supersedes the question — get complete DDL from `pg_dump`.** Rather than
growing `db/table_ddl.py` to cover inheritance and partitioning, source table DDL from the **`pg_dump`
binary**, accepting a hard dependency: *table DDL is available only when a correctly-versioned `pg_dump` is
on the local machine.* The owner's reasoning is that this does not merely close these two gaps — it
*"would simplify all ddl issues"*, i.e. it removes the entire class of reconstruct-it-ourselves fidelity
problems of which inheritance and partitioning are two instances, rather than paying them off one at a time.
The conditional in the quote is load-bearing: *"if psycopg can't do it"* — an in-process route is preferred
where one exists.

**Verified fact recorded with the answer (checked in this sweep, both directions).** The dependency is
already half-present: `pgtp_editor/db/sandbox.py` probes both binaries on `PATH` (`DATA_CLONE_TOOLS =
("pg_dump", "pg_restore")`, `which("pg_dump")`/`which("pg_restore")` at `:172-173`, surfaced as
`pg_dump_path`/`pg_restore_path` on the capability record) behind an **injectable `subprocess.run` seam**
(`:77`), for sandbox data cloning — so the binary probe, the seam and the offline test discipline all exist
and would be reused, not invented.

**But the change is one of KIND, and the entry says so rather than presenting the dependency as free.**
Today that dependency is **optional and degrades**: a sandbox without `pg_dump` simply cannot clone data,
and §18.5 D2a already specifies its absence as *"a named, surfaced failure"*. Under the proposed route a
**shipped, currently-working feature** — §18.1's table DDL pane, which renders today with no external binary
at all — becomes **unavailable without a correctly-versioned local `pg_dump`**. That is the honest cost, and
it is the thing design must answer: what the pane shows when the binary is missing or version-mismatched.

**What this entry's status now means.** The question *"do the gaps get closed and what triggers it"* is
**superseded in direction**, not answered by an option. The three options above are **not withdrawn** — they
remain the recorded fallback if the `pg_dump` route is rejected at design time, and their costs still stand
as analysed.

**Unblocks.**
- The `pg_dump`-sourced DDL approach is filed as **`FQ-260812022749`**, which is where the design work now
  lives: version matching, the missing-binary surface, whether `psycopg` can do it in-process first, and
  whether this replaces or supplements `db/table_ddl.py`.
- `spec-maintainer` should record `SERIAL` needing no special treatment as settled (§18.1), and should
  **re-point** §18.5's existing bold dependency warning — which today names `DEC-260811094437` as the place
  the gaps get closed — at `FQ-260812022749` instead, since closing them is no longer expected to happen in
  `table_ddl.py`.
- No change to `db/table_ddl.py` today. Its two-gap notice stays true and stays accurate under either route.

### CORRECTION (2026-08-12) — the trigger condition, restated

**No change to the answer or the status.** This corrects the *trigger condition* only, which the shipped
framing made incoherent.

**The old trigger.** *"The first feature that consumes this buffer as anything other than a read-only view"* —
concretely, `db/migration_gen.py` gaining `object_kind="table"` support. That was written when the expected
consumer was **the app itself**, reading the synthesized `CREATE TABLE` to diff or to generate a migration.

**Why it can no longer fire.** The area was redirected (see the answer above and `FQ-260812022749`), and the
framing that shipped is **clone-source**: the complete DDL exists so a *developer* can read it, edit the text
by hand under a new name, and run it to create a new table. Under that framing **nothing in the app ever
consumes the buffer — a human does.** The old trigger therefore waits for an event that is no longer on the
roadmap, while reading like a live guard. **A trigger condition that cannot fire is worse than no trigger at
all**, because it makes an unguarded area look guarded: nobody re-derives the risk, since the entry appears
to have already thought about it.

**The restated trigger:**

> **The first feature that INVITES this buffer to be used as a source.**

It fires on **invitation**, not on programmatic consumption. The app handing a developer text it *knows* to be
incomplete, in a context that says "clone from this", is precisely the case the guard is for.

**And the harm is worse under the new framing, not milder.** Read as a *view*, the inheritance and
partitioning gaps are disclosed incompleteness — the buffer's own notice names them and nothing acts on the
text. Read as a *clone template*, the same gaps are a **defect generator**: a developer who clones a
partitioned or inherited table from restricted-mode DDL gets a plain table that looks right, and runs it.
That is a silent wrong result reaching a real database, produced by someone acting in good faith on text the
app handed them. The failure has no error, no diff, no exception — only a table that is quietly the wrong
shape.

**Context: the gap-question is broader than inheritance and partitioning.** Triage found a hazard that applies
to **both** modes and that this entry never mentioned. A `SERIAL` column renders as
`DEFAULT nextval('orders_id_seq'::regclass)` — correct as a *description* of the original table (and the
`SERIAL`-needs-no-special-casing ruling above stands), but as a *clone template* it means the clone, created
under a new name, **draws from the original table's sequence**: a shared counter, and dropping the original
breaks the clone. Restricted mode never emits `CREATE SEQUENCE` at all; full `pg_dump` mode emits it, but in
a different section, so copying just the `CREATE TABLE` still misses it. **Neither mode is clone-safe for
`SERIAL` today.** This is recorded as context only — it is design detail belonging to `FQ-260812022749`, not
a second question, and it is **not** being filed as one.

**Judgement: this entry now BLOCKS, and specifically it blocks part of `FQ-260812022749`.** That feature is
the invitation — it frames the complete DDL as a clone source for tables and matviews — so the restated
trigger **is already fired**. What it blocks is not the whole feature, only its **restricted-mode half**: the
full `pg_dump` mode closes inheritance and partitioning on its own, so nothing is owed there, but the
restricted fallback hands the developer a knowingly incomplete template under the same clone-source framing.
The unanswered question is therefore now sharper than the one this entry was filed with:

> When `pg_dump` is absent or version-mismatched, may the restricted buffer be offered as a clone source at
> all — with a warning (`FQ-260812022749` already proposes wording: *"do not clone a partitioned or inherited
> table from this text"*), or must inheritance and partitioning be closed in `table_ddl.py` first (option 2
> above), or must restricted mode refuse the clone framing and present itself as a view only (option 3's
> boundary, applied to the mode rather than to the whole pane)?

The rest of `FQ-260812022749` — probe, version matching, the `[DDL]` Messages row, the full-mode buffer — is
untouched by this and should proceed.

---

## DEC-260812004358 — Confirm the trade: after the move, toolbar and shortcut customization are Maintenance-only

- **Status:** ANSWERED (2026-08-12)
- **Raised:** 2026-08-12, by the main session, from `FQ-260812002827` (consolidated two-pane **Software
  settings** dialog), which flags this itself as *"owner to answer at design time"*.
- **Blocks:** **nothing.** The feature is being implemented now with the default below, structured so an
  answer drops into one place (the menu-building code that today creates the two `View` entries). Reversing
  it later is re-adding two `View` actions that open the dialog on a given pane. **Do not read this entry as
  a reason to stall the feature.**
- **Default being shipped:** the trade as designed — **Maintenance-only, no `View` entries** — because the
  owner settled the move explicitly and this follows from it.

**Context (for a cold reader).** `FQ-260812002827` consolidates six settings categories into one two-pane
**Software settings** dialog, opened by a single new command that appears as one Maintenance-launcher button
and one `Settings`-menu entry. The owner settled, verbatim, that *"relocating means moving, so they won't be
anymore where they were before"* — so `View ▸ Customize Toolbar…` and `View ▸ Customize Shortcuts…` are
**removed** from `View` and become panes inside the new dialog. That part is settled and is **not** reopened
here.

The consequence needing explicit confirmation is a reachability change. The `Settings` menu is
Maintenance-only (`_MAINTENANCE_ONLY_MENU_TITLES = ("Settings",)`, `pgtp_editor/ui/main_window.py:356`,
per FQ-027/DEC-006). Both customize surfaces are reachable at **any** time today via `View`. After the move,
a user **cannot rebind a keyboard shortcut or customize the toolbar outside Maintenance mode**.

This is consistent with FQ-027's design that the app is *configured* in Maintenance mode — that is exactly
why the `Settings` menu is gated that way — so it is very likely intended. But it is a real reduction in
reachability for two surfaces that never had it, and toolbar/shortcut customization is the kind of thing a
user reaches for mid-work rather than in a dedicated configuration session.

**Options.**
1. **Accept the trade as designed.** One settings home, one entry point, exactly what the consolidation was
   for; nothing to explain to a future reader about why a surface has two doors. *Cost:* changing a chord or
   a toolbar button now requires entering Maintenance mode, i.e. a mode switch in the middle of ordinary
   work. Note the escape hatch is partial at best: DEC-006 established that Maintenance mode **hides** rather
   than prevents, so an existing chord still fires — but the customize *dialogs* have no chord of their own,
   so there is genuinely no non-Maintenance path to them.
2. **Keep a `View` entry for the two customize surfaces as a second entry point into the same dialog pane.**
   Preserves today's reachability at no functional cost — the pane is the same object, opened focused on that
   category. *Cost:* weakens "one settings home", which is the stated point of the consolidation; two of six
   categories then have a privileged second door, and a reader has to be told why those two and not the other
   four.

**Recommendation: option 1, accept the trade.** The owner settled the move on the principle that the app is
configured in Maintenance mode, and a second `View` door reintroduces the scattering the feature exists to
remove. If mid-work rebinding turns out to matter in practice, option 2 is a small, additive change later —
whereas shipping both doors now makes removing one a user-visible regression.

**What becomes possible once answered.** Confirmation = nothing to do, the shipped default stands and
`spec-maintainer` records the reachability trade in the Supersession Ledger rows for the two relocated
surfaces. Reversal = re-add two `View` actions that open the Software Settings dialog on the Customize
Toolbar / Keyboard Shortcuts pane, and state in the spec why those two categories are exempt from the
Maintenance gate.

### ANSWER (2026-08-12) — option 1, **CONFIRMED as shipped**

The owner confirmed the trade exactly as built: **no `View` entries; toolbar and keyboard-shortcut
customization are reachable only in Maintenance mode**, through the `Settings ▸ Software settings…` pane.

**Reasoning, and the durable part.** This was confirmed as the direct consequence of the owner's own earlier
ruling that *"relocating means moving, so they won't be anymore where they were before"*, and of FQ-027's
design that **the app is configured in Maintenance mode** — which is why the `Settings` menu is gated that
way in the first place. A second `View` door would reintroduce precisely the scattering the consolidation
existed to remove.

**Status of this entry's own options.** It was filed as *"confirm the shipped default"*, and the
confirmation converts it: this is now **settled design, not a default pending an answer**. Option 2 (a
`View` second door) is **no longer a live option** and its recorded reversal cost is historical. Anyone who
wants it must reopen this decision explicitly rather than treating it as still-open latitude.

**Unblocks.** Nothing to implement. `spec-maintainer` records the reachability trade as settled design in
the Supersession Ledger rows for the two relocated surfaces, phrased as a ruling rather than as a default.

### SECOND RULING RECORDED IN THE SAME SWEEP (2026-08-12) — **absorption degrades as deletion**

Raised during the 2026-08-12 sweep by the main session, about a call it had made alone while implementing
`FQ-260812002827` and recorded only in a commit message. Filed here rather than as its own entry because it
is a consequence of *this* relocation; cite it as **`DEC-260812004358`'s second ruling**.

**The situation.** Four absorbed command ids — `View ▸ Customize Toolbar…`, `View ▸ Customize Shortcuts…`,
`Settings ▸ Edit Snippets…`, `Settings ▸ Autoformatter settings…` — were given **no
`toolbar_registry.RENAMED_ID_ALIASES` rows**, on the reasoning that they were *absorbed, not renamed*: there
is no successor id meaning "customize the toolbar" for a stored id to resolve onto. The precedents point
both ways — deletions (`file.save`, `database.deploy-this-edit`) deliberately get no row and are dropped by
`resolve_ids`, while moves do get one (`database.project-status` → `file.project-status` kept its button
when §18.8's screen changed menus). Absorption is neither: the *capability* survives behind a different
door. The alternative considered was aliasing all four onto `settings.software-settings`, which
`valid_ids`' de-duplication would collapse to a single button rather than four.

**ANSWER: keep it as shipped — no alias rows.**

**Reasoning, verbatim in substance:** *a pinned button for a command that no longer exists must not open a
dialog that does five other things.* The owner accepted **both** silent consequences, explicitly:

1. a customized toolbar containing any of those four buttons **loses that button** on next launch, and
2. a **custom keyboard override** stored against any of those four ids is **also dropped** — verified in
   this sweep at `pgtp_editor/ui/shortcut_registry.py:805-816`, which runs stored overrides through the
   **same** `LEGACY_ID_ALIASES` → `RENAMED_ID_ALIASES` pair that `resolve_ids` uses.

Consequence (2) was **not** weighed when the implementing session made the call alone — it was found during
this sweep — and the owner's answer covers it knowingly. That is why the call is recorded here as a ruling
rather than left in a commit message: the decision as originally made was not the decision as it stood.

**THE DURABLE PART — a rule wider than these four ids.** **Absorption degrades as deletion.** An id whose
*capability* survives behind a different door still gets **no alias row**. An alias table row is a claim
that a command **moved**, and a command that was folded into a larger surface did not move — it stopped
existing as a command. `resolve_ids` dropping the id is the honest degradation, and the same applies to the
stored shortcut override. Only a genuine rename or menu-move earns a row.

**Unblocks.** No code change. The next absorption follows the rule without re-asking, and
`spec-maintainer` should carry the rule into §7's account of `RENAMED_ID_ALIASES`, where the
deletion-vs-move distinction is already documented but the third case was not.

---

## DEC-260812004359 — Is the Software Settings dialog modal, given the shortcuts editor is non-modal today?

- **Status:** ANSWERED (2026-08-12)
- **Raised:** 2026-08-12, by the main session, from `FQ-260812002827`, which flags this itself as *"owner to
  answer at design time"*.
- **Blocks:** **nothing.** The dialog is being built now with the default below; modality is one call on the
  dialog (`setModal(...)`) plus its single-instance handling, so an answer drops into one place. **Not a
  reason to stall the feature.**
- **Default being shipped:** the Software Settings dialog is **non-modal**, preserving the existing
  behaviour of the shortcuts editor, because it is the choice that changes nothing about a shipped surface.

**Context (for a cold reader).** `pgtp_editor/ui/customize_shortcuts_dialog.py` is **non-modal** today
(`View ▸ Customize Shortcuts…`, FQ-012). `FQ-260812002827` re-hosts it as a pane inside the consolidated
Software Settings dialog. Re-hosting changes its parent window, and therefore its modality is now the
*host's* property rather than its own.

Why it matters concretely: a **non-modal** shortcut editor lets the user try a chord against the live
application while the editor is open. Inside a **modal** settings dialog they cannot, so rebinding becomes
edit → close → test → reopen. Whether that live-preview property was load-bearing or merely incidental to
how the dialog happened to be written is the owner's call — it is a product property, not an implementation
detail. For reference, the app already ships modal dialogs of this kind (`ui/launcher_dialog.py:222`
`setModal(True)`) and non-modal panels (`ui/project_status_panel.py:499` `setModal(False)`), so both shapes
have precedent.

**Options.**
1. **Non-modal settings dialog** (the default being shipped). Preserves the shortcuts editor's live-preview
   behaviour exactly; no shipped behaviour changes. *Cost:* a non-modal dialog can sit behind the main window
   and be re-opened, so it needs **single-instance handling** (raise-and-focus the existing instance rather
   than spawning a second) — the app already does this for other dialogs, so the cost is small but real. It
   also means settings changes can land while the user is editing, so each pane must apply cleanly at any
   moment rather than assuming a quiet application.
2. **Modal settings dialog.** Simpler lifecycle: one instance by construction, no raise-and-focus logic, no
   question about changes landing mid-edit; matches the launcher's shape. *Cost:* removes live chord
   preview from shortcut rebinding — a small but genuine regression of a shipped surface — and blocks the
   whole app while someone browses six settings categories.

**Recommendation: option 1, non-modal.** It is the only option that changes nothing about a surface that
already ships, and the cost it carries (single-instance handling) is a pattern already present in the
codebase. Going modal trades a real user-facing property for implementation tidiness, which is the wrong
direction for a surface whose whole job is configuration.

**What becomes possible once answered.** Confirmation = the shipped default stands; `spec-maintainer`
records "the Software Settings dialog is non-modal, single-instance, because the shortcuts pane's live chord
preview is load-bearing" so the next reader does not "tidy" it to modal. Reversal = one `setModal(True)`,
drop the single-instance raise logic, and the manual notes that chords are tested after closing settings.

### ANSWER (2026-08-12) — option 1, **CONFIRMED as shipped**

The Software Settings dialog is **non-modal and single-instance**, as built.

**Reasoning.** The confirmation was given on the ground that the shipped surfaces it absorbed were already
non-modal, and that the keyboard-shortcuts pane's **live chord preview** — trying a key against the running
application while the editor is open — is a real product property, not an artifact of how the dialog
happened to be written. Modality would have traded that property for implementation tidiness, which is the
wrong direction for a surface whose entire job is configuration.

**Verified shipped shape at the time of answering** (`pgtp_editor/ui/main_window.py:3810`,
`open_software_settings_dialog`): opened with `show()`, never `exec()`; no `setModal` call anywhere in
`pgtp_editor/ui/software_settings_dialog.py`; a stored handle makes a second request **raise and focus the
existing window** rather than build a rival, and the handle is dropped on `finished` so the next open
rebuilds panes against current state rather than showing yesterday's values.

**Non-modal and single-instance are ONE decision, not two.** A non-modal window that can be opened twice is
two windows editing the same stores. Anyone removing the raise-and-focus logic must go modal in the same
change, or reintroduce that bug.

**Status of this entry's own options.** Now **settled design, not a shipped default awaiting confirmation**.
Option 2 (modal) is no longer a live option; its recorded reversal cost is historical unless someone
reopens this decision.

**Unblocks.** Nothing to implement. `spec-maintainer` records *"the Software Settings dialog is non-modal
and single-instance, because the shortcuts pane's live chord preview is load-bearing"* so a later reader
does not "tidy" it to modal.

---

## DEC-260812004400 — Do the two unimplemented settings panes appear disabled, or not at all?

- **Status:** ANSWERED (2026-08-12)
- **Raised:** 2026-08-12, by the main session, from `FQ-260812002827`, which flags this itself as *"owner to
  answer at design time"*.
- **Blocks:** **nothing**, and this is the least load-bearing of the three filed from this feature — it is
  trivially reversible (two rows in the category list). It is filed because the project has a **recorded
  precedent pointing the other way**, so choosing silently would either contradict that precedent or quietly
  narrow it. **Not a reason to stall the feature.**
- **Default being shipped:** **four panes**, the two unimplemented ones omitted.

**Context (for a cold reader).** The consolidated Software Settings dialog (`FQ-260812002827`) has six
categories in the owner's own list. Four re-host working surfaces (snippets, customize toolbar, autoformatter
settings, keyboard shortcuts). Panes 5 (**syntax highlight colors**, `FQ-260812002828`) and 6 (**color
scheme**, `FQ-260812002829`) do not exist: the owner's instruction was that they *"must be skipped, because
needs owner description to implement"*, and both queue entries are `QUEUED — BLOCKED: DO NOT IMPLEMENT`.

So the question is only what the dialog's left-hand category list shows: **six entries with two
disabled/"coming soon"**, or **four entries** until the descriptions land.

**The precedent that makes this worth asking.** FQ-023 shipped the principle that a gesture should **state
its reason rather than vanish** — `Add Trigger…` on a matview appears as a **disabled entry stating why**,
on the argument that a silent absence reads as the app having forgotten. If that principle extends to
settings categories, six-with-two-disabled is the consistent answer. Against that, the project has elsewhere
treated visibly dead controls in a shipped surface as a defect.

**Options.**
1. **Four panes, two omitted** (the default being shipped). No dead controls in a shipped dialog; the list is
   exactly what the dialog can do. *Cost:* a user who expects colour settings finds nothing and cannot tell
   whether they are absent, elsewhere, or unbuilt — the exact "silent absence" FQ-023 argued against.
2. **Six panes, two disabled with a stated reason** ("not yet available"). Communicates the roadmap, matches
   the FQ-023 shape, and pre-empts "where are the colour settings?". *Cost:* ships two permanently inert rows
   in a brand-new dialog, and they stay inert until two blocked features get owner descriptions of unknown
   date — a "coming soon" with no date is a promise the app cannot keep.

**Recommendation: option 1, four panes.** The FQ-023 precedent applies to a gesture whose **siblings are
present** — `Add Trigger…` exists on other object kinds, so its absence on a matview reads as a bug and must
be explained. A settings category nobody has ever been told about carries no such expectation; there is
nothing for the absence to contradict. And the reversal is two list rows, so shipping the smaller surface
first costs nothing if the owner disagrees.

**What becomes possible once answered.** Confirmation = the shipped default stands; the child entries
`FQ-260812002828`/`FQ-260812002829` add their pane *and* its list row when their descriptions land. Reversal
= add two disabled rows with a stated reason, and decide (a second, smaller question) whether selecting one
shows an explanatory panel or nothing.

### ANSWER (2026-08-12) — option 1, **CONFIRMED as shipped**

**Four panes.** The two unbuilt colour categories are **omitted, not stubbed**.

**Verified shipped shape:** `software_settings_dialog.SETTINGS_PANES` is a four-tuple —
`snippets`, `toolbar`, `autoformatter`, `shortcuts` — carrying the comment *"FOUR, not six"*.

**Reasoning, and the boundary it draws on FQ-023.** The confirmation keeps the FQ-023 principle (*a gesture
states its reason rather than vanishing*) **scoped to gestures whose siblings are present**: `Add Trigger…`
exists on other object kinds, so its absence on a matview reads as a bug and must be explained. A settings
category the user has never been told about carries no such expectation — there is nothing for its absence
to contradict — so a disabled row would be a "coming soon" with no date, i.e. a promise the app cannot keep.
**This narrows FQ-023 deliberately rather than contradicting it, and that narrowing is the durable part.**

**Status of this entry's own options.** Settled design, not a default pending an answer. Option 2 (six rows,
two disabled) is no longer a live option unless someone reopens this.

**Unblocks.** Nothing to implement. `FQ-260812002828` (syntax highlight colours) and `FQ-260812002829`
(colour scheme) each add their pane **and** its category-list row in the same change, when the owner's
descriptions land — neither adds a row ahead of a working pane.
