# Deployment SQL Generation — Implementation Plan

> Use TDD. Steps use checkbox syntax. Modal-hang guardrail applies (no unpatched
> `QMessageBox` / `QDialog.exec()` / `QFileDialog` in tests). Headless offscreen is forced by
> `conftest.py`; QSettings isolated by the autouse fixture. **No live PostgreSQL anywhere in this
> plan** — Tasks 1–3 are pure functions over canned `DatabaseSchema` objects and need no runner at
> all; Task 4 uses the established `runner=` fake pattern.

**Goal:** the sandbox database is the **desired-state reference** for production. Production is
current state. This plan produces the deliverable: **one reviewed `.sql` script that upgrades
production to match the sandbox.**

**Why:** the user's stated endgame — *"our sandbox database is made to properly prepare development
modifications (at the end a deployment sql which is a single sql ran to upgrade the real
database)"*. In DBeaver, editing a function and deploying it are the same keystroke, with no
reviewable artifact in between. The deployment script **is** that artifact.

## Scope boundary — read this first

This plan covers **only** deployment-SQL generation. It was split out of
`2026-08-02-ddl-object-editor-and-sandbox.md` after a cross-session collision on 2026-08-02.

| Owned here | Owned by §18.5 (silly-booth worktree) |
|---|---|
| `db/schema_diff.py` | the editable DDL object tab (`DdlObjectEditorPanel`) |
| `db/migration_gen.py` | `db/apply.py` — the write seam |
| the pre-generate drift check | `db/sandbox.py` — ownership, capabilities, provisioning |
| the preview tab + Save Migration As… | the validation ladder / `[Check]` diagnostics |
| | `db/config.py` profile keying, `ConnectionSetupDialog` |

This plan **consumes** `db/sandbox.py` and the profile scheme; it does not modify them.

**Spec:** `CONSOLIDATED_SPEC.md` **§18.3**, which already fixes the contract verbatim —
`SchemaDifference{kind, object_kind, identity, old_def, new_def}`,
`diff_schemas(source: DatabaseSchema, target: DatabaseSchema) → list[SchemaDifference]`,
`generate_migration(differences) → str`. Tasks 1–3 are therefore **implementing existing spec, not
new design.** What *is* new design — sandbox-as-desired-state, the drift gate, routine/trigger-only
scoping, preview-before-write — lands in the spec once §18.5 is committed and the file is free.

**§18.3 reuse, not a parallel engine.** §18.3's own framing: *"One diff/generation engine, two entry
points — there are not two separate 'assemble SQL' mechanisms."* This plan creates those two modules
and implements **only the routine/trigger cases**. Table/column cases are defined in the type and
raise `UnsupportedDifference`; §18.3 proper fills them in later. Nothing here is thrown away.

**Divergence from §18.3 worth stating:** §18.3 assumed the desired state comes from a checked-in JSON
snapshot (`db/schema_snapshot.py`). A **live sandbox is strictly better** — you can execute against
it, so the desired state is provably coherent before it is diffed. This adds a third source alongside
§18.3's "live connection or snapshot". It does **not** build `db/schema_snapshot.py`; that stays
§18.3's.

**Four tasks.** Tasks 1–3 are pure, Qt-free, DB-free and independently testable — the easiest things
in the whole feature to get right. Task 4 is the UI.

---

## Task 1: `db/schema_diff.py` — the §18.3 shape, routine/trigger cases only

**Files:** create `pgtp_editor/db/schema_diff.py`; test `tests/db/test_schema_diff.py`.

- [ ] `@dataclass(frozen=True) class SchemaDifference: kind: str; object_kind: str; identity: str; old_def: str | None; new_def: str | None`
      — **verbatim §18.3**: `kind ∈ added|removed|changed`, `object_kind ∈ table|column|routine|trigger`.
      Do not "improve" the field names; §18.3's full engine will populate the same type.
- [ ] `diff_schemas(source: DatabaseSchema, target: DatabaseSchema) -> list[SchemaDifference]` —
      §18.3's signature. Pure, Qt-free, no I/O, no runner. Mirrors `diff/differ.py::diff_project`'s
      contract shape but DB-object-keyed rather than XML-node-keyed.
- [ ] **Implemented:** `object_kind="routine"` and `"trigger"`, keyed on `DatabaseSchema.routines` /
      `.triggers`, which `fetch_routines_and_triggers` already populates for any connection —
      sandbox or production — with **no new catalog query**.
- [ ] **Not implemented:** `object_kind="table"`/`"column"`. Skip `source.tables`/`target.tables`
      entirely and record the omission in a returned `unsupported: list[str]`, so the UI can state
      *"table and column changes are not compared — §18.3"* rather than implying the diff was
      complete. **A silently table-blind diff presented as a full migration is exactly the
      silent-wrong-result class this project refuses.**
- [ ] **Routine identity is the full signature** — `schema.name(argtype, argtype)`, built from
      `RoutineInfo.arg_types` (already present, verified). **Never** `schema.name`. Load-bearing;
      see R14.
- [ ] Trigger identity is `schema.table.name`, matching `DatabaseSchema.triggers`' existing key.
- [ ] `changed` is decided by exact text comparison of `RoutineInfo.source` /
      `TriggerInfo.definition`. Both come from `pg_get_functiondef` / `pg_get_triggerdef` on each
      side, so formatting is server-normalized and a cosmetic-only diff is not possible within one
      server version. Cross-version caveat: see R16.
- [ ] **`old_def` is `production_now`, never the baseline.** The script upgrades production *as it
      currently is*, so the diff's `source` argument is a fresh production introspection — the
      baseline (Task 4b) is used **only** by the drift gate, never fed into `diff_schemas`. When the
      gate passes these are identical, so it matters only if the gate is ever relaxed — pin it now so
      the generator cannot quietly emit a diff against a stale reference. Call order is therefore:
      drift gate (baseline) → **then** `diff_schemas(production_now, sandbox)`.
- [ ] Thread `RoutineInfo.language` through onto the difference (a sibling field is fine) —
      Task 3 needs it for the non-plpgsql ordering warning. It already exists on `RoutineInfo`.

Tests (all pure, canned `DatabaseSchema` objects, no runner, no Qt): routine only in sandbox →
`added`; only in production → `removed`; differing source → `changed` carrying both defs; identical
→ absent; **an argument-type change yields `removed` + `added`, never `changed`**; two overloads of
one `schema.name` are two independent identities; a trigger changed on the same table; tables present
on both sides produce **no** differences and **are** listed in `unsupported`; empty-vs-empty → `[]`.

---

## Task 2: `db/migration_gen.py` — routine/trigger emitter

**Files:** create `pgtp_editor/db/migration_gen.py`; test `tests/db/test_migration_gen.py`.

- [ ] `generate_migration(differences, *, header: str = "") -> str` — §18.3's signature. Pure: no
      I/O, no DB, no Qt. **Deterministic** — byte-identical output for identical input, so tests are
      golden-string assertions.
- [ ] Module docstring **opens** with the limitation: this generates *routine and trigger*
      migrations, not table/column ones (R18).
- [ ] Emission order — §18.3's CREATE→ALTER→guarded-DROP, with only the first and last populated:
      1. **Header comment block:** generated-at; sandbox and production connection summaries
         (`user@host:port/db`, **redacted — never a password**, via the `debuglog.redacted` shape);
         both server versions; which content model produced it (Task 4); the explicit
         *"table/column changes not included"* limitation.
      2. `added` + `changed` routines → the `new_def` verbatim (`pg_get_functiondef` already emits
         `CREATE OR REPLACE`).
      3. `added` + `changed` triggers → `DROP TRIGGER IF EXISTS <name> ON <table>;` then the
         `new_def`. Triggers have no portable `OR REPLACE` below PG 14; the drop-then-create pair is
         idempotent on all supported majors and simpler than branching on the target's version.
      4. `removed` routines/triggers → **commented-out** `DROP` statements with a `-- REVIEW:`
         marker. Never live DROP text. An object absent from the sandbox far more likely means *"the
         user never touched it"* than *"delete this from production"* — and under content model (a)
         it is not even reachable.
- [ ] Every statement terminated with `;` and separated by a blank line — copy-pasteable into
      `psql`, diffable in git.
- [ ] `object_kind in ("table", "column")` → raise a module-defined `UnsupportedDifference`
      (psycopg-free, Qt-free). The caller renders the refusal. **Never emit a partial script that
      silently drops table changes on the floor.**

Tests: golden-string output for one added routine, one changed routine, one trigger (asserting
`DROP TRIGGER IF EXISTS` precedes the create), one removed routine (asserting the DROP is commented
and carries `-- REVIEW:`); a `table` difference raises `UnsupportedDifference`; **the header contains
no password**; two runs over identical input produce identical bytes.

---

## Task 3: dependency ordering — the simple answer is the right one

**Files:** modify `pgtp_editor/db/migration_gen.py`; test `tests/db/test_migration_gen.py`.

**Decision: stable alphabetical by identity, routines before triggers. Deployment-SQL generation
must NOT depend on tier 3.**

Why ordering is mostly a non-problem:

- **PL/pgSQL bodies are not resolved at CREATE time.** With `check_function_bodies = on` (the
  default), the validator parses the body's *statement structure* only; SQL expressions inside it —
  including calls to other functions and references to tables — are parsed and planned lazily, at
  first execution. `CREATE OR REPLACE FUNCTION a()` whose body calls `b()` **succeeds when `b()` does
  not exist.** The strongest evidence is this feature's own premise: if CREATE-time validation
  resolved relations and callees, `plpgsql_check` would have nothing to catch. Forward references
  between plpgsql routines need **no** ordering.
- **Exception 1 — `LANGUAGE sql` routines.** These *are* analysed at creation, and PG 14+
  `BEGIN ATOMIC` bodies record real catalog dependencies. A SQL-language function referencing a
  not-yet-created function or table **will** fail at CREATE.
- **Exception 2 — triggers.** `CREATE TRIGGER` resolves its function immediately
  (`pg_trigger.tgfoid` is a hard catalog reference) and the table must exist. "Routines before
  triggers" is a real constraint, not cosmetics.

**Why `plpgsql_show_dependency_tb()` is the wrong tool despite looking perfect.** It returns exactly
the `FUNCTION`/`OPERATOR`/`RELATION` dependency set per routine and would drive a clean topological
sort — but it is a `plpgsql_check` function, so **it only covers plpgsql routines: precisely the
language that does not need ordering.** It cannot see inside the `LANGUAGE sql` routines that do.
Adopting it would make producing the deliverable depend on an optional, per-database,
superuser-gated C extension, in exchange for ordering information about cases that were never at
risk. **Not acceptable.** The deliverable must be producible on a bare PostgreSQL with no extensions.

- [ ] Sort `added`/`changed` by `(object_kind_rank, identity)` — routines rank before triggers, then
      alphabetical. Deterministic, dependency-free, testable.
- [ ] If any emitted routine is non-plpgsql (from the `language` field threaded in Task 1), emit a
      header warning: *"N non-PL/pgSQL routine(s) are included; statement order may need manual
      adjustment (their bodies are resolved at CREATE time)."* Honest, cheap, does not block.
- [ ] Record `plpgsql_show_dependency_tb`-driven topological ordering as a **follow-on** — and only
      ever a supplement to, never a replacement for, handling the SQL-language case.

Tests: three routines and two triggers → routines first, each group alphabetical; a `LANGUAGE sql`
routine present → the header warning appears; an all-plpgsql set → no warning.

---

## Task 4: the drift gate, the preview, and Save Migration As…

**Files:** modify `pgtp_editor/ui/main_window.py::_build_database_menu`;
test `tests/ui/test_deployment_sql_wiring.py` (new).

### 4a — content model (open question, see below)

Default to **(a) the sandbox working set**, from `db/sandbox.py`'s `applied` bookkeeping table.
Written source-agnostic so switching to (b) is a one-line change of which two `DatabaseSchema`
objects reach `diff_schemas`.

### 4b — the mandatory pre-generate drift check

> **R19 resolved (2026-08-02, confirmed with the §18.5 owner).** `db/sandbox.py` retains, per object,
> **both a baseline hash and the baseline definition text**, persisted in a bookkeeping schema
> *inside the sandbox database* (so it survives app restarts and travels with the sandbox). Four
> semantics that constrain this task:
>
> 1. **The baseline is captured by introspecting the TARGET at provisioning time**, as a step
>    distinct from seeding — *not* by snapshotting whatever landed in the sandbox. A sandbox that is
>    a pre-existing local restore may already differ from production, and snapshotting it would make
>    the gate compare production against a stale restore and label the difference "user edits".
> 2. **A missing baseline (target unreachable at provisioning) is a distinguishable state**, never an
>    empty string that compares equal. The gate must then report *"could not check"* — same
>    never-silently-clean rule as the validation ladder.
> 3. Baseline is captured **per object as it first enters the sandbox** — at provisioning or at a
>    later refresh/add — not only in one big-bang initial snapshot.
> 4. **Re-provisioning wipes the bookkeeping and re-captures the baseline.** A fresh sandbox means a
>    fresh reference point.
>
> **Hashing:** consume `db/ddl_project.py::content_hash` — the single implementation §18.2 mandates
> be used identically in all three places (local file, live introspection, stored reference). Do
> **not** write a second; two implementations would make §18.2's `!` markers and this gate disagree.
> Known limitation, recorded rather than papered over: hashing is stable when both sides come from
> `pg_get_functiondef` (which is this gate's case), but *not* when comparing hand-authored local text
> against generator output — §18.4's formatter legitimately changes stored text without changing
> behaviour. Does not affect production-vs-baseline.

- [ ] Before generating, `fetch_routines_and_triggers(production_params)` off-thread — one read-only
      introspection call, **no new code** — and compare **only the objects in the applied set**
      against their baseline definitions from `db/sandbox.py`.
- [ ] **Three-way comparison.** The gate needs all three points to tell these apart:
      | | `prod_now` vs baseline | sandbox vs baseline | verdict |
      |---|---|---|---|
      | user edited it | same | differs | **expected — proceed** |
      | production drifted | differs | same | **block** |
      | both | differs | differs | **block loudly — conflict** |
      With only production-vs-sandbox these are indistinguishable, and the gate is either useless or
      silently overwrites a production hotfix with a stale dev edit.
- [ ] Any object whose baseline is **absent** → report *"could not check"* for that object and block,
      never treat it as unchanged.
- [ ] Any object whose production definition changed since provisioning is a `!` drift blocker.
      Reuse §18.3's *"any `!`-flagged object blocks the batch"* all-or-nothing discipline, itself
      reusing Diff/Merge's §12 ambiguity gate: **refuse the whole script, name every blocker**,
      recovery = re-provision or re-apply, then re-run.
- [ ] **R13/R14 refusal, same pass.** We introspect production anyway, so both signatures are in
      hand. Refuse with a named blocker when, for an object in the applied set:
      - the argument types differ from production's (R14 — a bare `CREATE OR REPLACE` would create a
        *second* function and leave the old one live), or
      - the return type differs, or an input parameter was renamed (R13 — `CREATE OR REPLACE` fails
        outright with *"cannot change return type of existing function"* / *"cannot change name of
        input parameter"*).
      Message names the object and the reason, e.g. *"pr.calc_total(integer): argument types changed
      to (bigint) — a deployment script cannot replace this in place."*
      **This is why "no ALTER logic, no drop guards" holds: the hard cases are refused, not
      handled.** Say so in the code comment.

### 4c — menu, preview, save

- [ ] **Generate Deployment SQL…** in the Database menu, after §18.5's *Sandbox Setup…* /
      *Check DDL Object*. Disabled unless a sandbox profile is configured.
      > **Merge note:** §18.5 also edits `_build_database_menu`. Whoever lands second rebases that
      > hunk rather than merging it.
- [ ] §18.3's **Compare Schemas…** and **Save Migration As…** are **not** built here. This plan
      builds the engine those two will call; their UI is §18.3's job and its *"separate sibling
      command, no-project-required"* framing must not be pre-empted by a §18.5-shaped screen. Put
      that in a code comment so the next reader does not "finish" it wrongly.
- [ ] `_generate_deployment_sql()`: `busy_status` + `self._run_async` around (drift check →
      `diff_schemas` → `generate_migration`). Both introspection calls open connections and must be
      off the GUI thread.
- [ ] Guards, each with a specific message: no sandbox → open Sandbox Setup; empty applied set →
      *"nothing has been applied to the sandbox yet"*; drift/signature blockers → the §12-style
      refusal naming every blocker; `UnsupportedDifference` → the table/column refusal.
- [ ] **Review before write.** Show the script in a **read-only preview tab** reusing
      `CodeEditor(language="sql")` — widget, highlighter and gutter all already exist — with a
      **Save Migration As…** button. Do not write a file the user has not read. This is DDL destined
      for production.
      > **Merge note:** the preview tab is dynamic, as are §18.5's object tabs. `CenterStage`'s fixed
      > indices are load-bearing in five places; append-only creation and tail-only removal only.
- [ ] Save via
      `QFileDialog.getSaveFileName(self, "Save Migration As", f"migration_{ts}.sql", "SQL files (*.sql)")`,
      UTF-8, `newline=""`, mirroring `_save_xsd`. Patched in tests.
- [ ] **The script is never executed.** §18.3's hard non-goal — *"this never auto-executes DDL
      against a live database"* — inherited verbatim. No execute path exists, not even a disabled one.

Tests (patched `_run_async`, patched `getSaveFileName`, fake introspection seams): canned applied set
+ canned schemas → preview shows the expected script; a drifted object → refusal naming it, no
preview, no file; an argument-type change → the R14 refusal; a return-type change → the R13 refusal;
empty applied set → status message, no preview; Save writes exactly the previewed bytes; a `table`
difference → the unsupported refusal; **no modal reached unpatched**.

**Done means:** a user who edited three routines in the sandbox and checked them green gets one
reviewed `.sql` file that upgrades production to match — with an explicit refusal if production moved
underneath them or if a signature change makes in-place replacement unsafe, and an explicit statement
of what the script does not cover.

---

## Risks

**R13 — `CREATE OR REPLACE FUNCTION` is not universally idempotent.** Fails on
*"cannot change return type of existing function"* and *"cannot change name of input parameter"*.
Handled by Task 4b's refusal. Loud failure, not silent.

**R14 — a changed argument type silently creates an overload.** PostgreSQL identifies functions by
`(schema, name, argtypes)`. `calc_total(integer)` → `calc_total(bigint)` means `CREATE OR REPLACE`
**creates a second function and leaves the old one live**; every existing caller keeps hitting the
old one. Silent wrong result in production — the worst place for one. Mitigated in two independent
places: Task 1 keys identity on the full signature so it surfaces as `removed`+`added`, and Task 4b
refuses it outright. **Do not let identity degrade to `schema.name` anywhere in the pipeline.**

**R15 — transaction-wrapping the script is undecided.** PostgreSQL has transactional DDL, so
`BEGIN; … COMMIT;` makes deployment atomic — a strong property here. But it changes how the user's
own deploy tooling must invoke it. Recommend emitting the pair **commented out** in the header with
a one-line explanation, so the user chooses. Open question, not decided here.

**R16 — `pg_get_functiondef` text is not stable across server majors.** Sandbox and production are
frequently different majors. Cosmetic rendering differences surface as phantom `changed` entries →
a script full of no-op replacements. Harmless (idempotent) but noisy and it erodes trust in the diff.
Mitigation: report both server versions in the header and say so prominently when they differ. A
normalizing comparison is a rabbit hole — do not start it.

**R17 — the sandbox baseline is a structural approximation, and that propagates here.** §18.5's
provisioning omits extensions, sequences, constraints, defaults and data. A routine *valid in the
sandbox* may be invalid in production. This does not break routine/trigger deployment (bodies do not
depend on constraints) but it means "green in the sandbox" is a weaker guarantee than it reads. The
header must state which baseline model produced the sandbox.

**R18 — both modules land with their table/column halves deliberately hollow.** The next contributor
sees `db/migration_gen.py` and reasonably assumes it generates migrations. It generates *routine and
trigger* migrations. Docstrings must open with that, and `UnsupportedDifference` must be a real
raised exception rather than a silent skip.

**R19 — RESOLVED (2026-08-02).** The drift check needs baseline-time production definitions.
Confirmed with the §18.5 owner: `db/sandbox.py` retains both a baseline hash and the baseline
definition text, persisted inside the sandbox database, captured by introspecting the **target** at
provisioning (not by snapshotting the seeded sandbox) and per object as each enters the sandbox.
Missing baseline is a distinguishable state, not an empty string. See the block in Task 4b for the
full semantics. No longer a blocker.

---

## Open questions (for the spec once §18.5 is committed)

- **Content model** — working set (a) vs. true diff against production at generate time (b).
  Recommending (a) + the mandatory drift gate: that captures (b)'s single real safety benefit at a
  fraction of the scope, and leaves (b) as a clean later upgrade.
- **R15** — transaction-wrap the script, or leave it to the user?
- **R13/R14 refusal policy** — refuse outright (planned here), or offer a consented guarded
  `DROP FUNCTION` + `CREATE`? The latter cascades into trigger recreation.
- **Apply-to-target vs. the deployment script** — **RESOLVED (2026-08-02).** §18.5 had added a
  confirm-gated direct apply to the target database. After the argument that the deployment script
  removes its justification, the owner's call: it **ships disabled behind an explicit opt-in**,
  surviving only for the body-only-change fast path, off by default — and it gains the R14 signature
  hard-refuse. The deployment script is the default route to production.

---

## Self-review

- **§18.3 reused, not duplicated:** exact `SchemaDifference` field names, exact `diff_schemas` and
  `generate_migration` signatures, exact CREATE→ALTER→guarded-DROP ordering; its Compare-Schemas UI
  explicitly left unbuilt.
- **Invariants held:** both new modules Qt-free and psycopg-free — pure functions over
  `DatabaseSchema`, no runner needed, the easiest things here to test; no new catalog query; no
  password in any generated artifact; nothing auto-executed; every refusal explicit and named rather
  than a silent omission; `.pgtp` never written.
- **No live DB anywhere in this plan.** Tasks 1–3 need no runner at all; Task 4 uses the established
  `runner=` fake pattern.
- **Tasks 1–3 are implementable today** with zero dependency on §18.5 landing. Only Task 4 needs
  `db/sandbox.py` and the profile scheme.
