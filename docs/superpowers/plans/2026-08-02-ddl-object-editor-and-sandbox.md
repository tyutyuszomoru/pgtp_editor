# §18.5 — Editable DDL Object Editor & Sandbox Validation — Implementation Plan

> Use TDD. Steps use checkbox syntax. Modal-hang guardrail applies (no unpatched
> `QMessageBox` / `QDialog.exec()` / `QFileDialog` / `QMenu.exec()` in tests). Headless
> offscreen is forced by `conftest.py`; QSettings isolated by the autouse fixture.
> **No live PostgreSQL in the default suite** — every DB path takes `runner=` and is
> driven by a fake, exactly as `tests/db/test_introspect.py` does today. The handful of
> facts that genuinely need a server live in one env-gated file (Task 9.1).

**Goal:** the sandbox database is the **desired-state reference** for the production
database. Right-click a routine/trigger in the §18.1 DDL Explorer tree → an editable
single-object tab → apply it to a **stateful, app-provisioned sandbox** that accumulates the
whole set of development modifications → validate with the four-tier ladder → **generate one
deployment SQL script that upgrades production to match the sandbox**. Per-object
`Save As… .sql` is a real secondary output (and the §18.2 precursor), not the headline.
No live/production database is ever written by this tool.

**Why this exists:** in DBeaver — the tool this replaces for PL/pgSQL work — editing a
function and deploying it are the *same keystroke*. `CREATE OR REPLACE` runs against the live
database the moment you save. There is no intermediate state, no preview, no undo. The sandbox
is that missing intermediate: the place where "I changed this" and "production changed" are
finally two different events. Everything else in §18 — git versioning, drift markers, the
reviewed deploy bundle — is downstream of that one separation.

**Spec:** `docs/superpowers/CONSOLIDATED_SPEC.md` §18.5 (with §17 for `db/config.py`,
§18.1 for `BrowserPanel`/`EditorPanel`, §18.3 for the diff/migration engine contract,
§18.4 for the formatter consumer, §22 for the `[Lint]`/`[Check]` prefix reservation).

**Nine phases**, each independently shippable and testable, riskiest/most-foundational first.
Phases 1–4 are Qt-free and land without any UI. Phase 5 ships a useful editor with no sandbox
at all. Phases 6–7 turn on validation. **Phase 8 produces the actual deliverable.** Phase 9 is
the env-gated live-server confirmation.

---

## Settled framing (do not relitigate)

**1. Three outputs, clearly ranked.**

- **(1) Generate Deployment SQL — THE deliverable.** A single reviewed `.sql` script that
  upgrades production to the sandbox's state. Phase 8.
- **(2) The sandbox itself** — a stateful, accumulating working set that *is* the desired
  state, and which you can execute against to prove that desired state is coherent before you
  diff it. Phases 3, 6, 7.
- **(3) `Save As…` per object** — the edited routine source to a user-picked `.sql`. Genuinely
  useful, and it is exactly §18.2's future `ddl/<schema>.<name>.sql` file arriving early.
  **Demoted from headline to convenience.** Phase 5.

No `CREATE OR REPLACE` is ever executed against the live/target database from this tool.
Deployment is a file the user runs on their own deploy path — §18.3's hard non-goal, unchanged.

**2. The sandbox is stateful and accumulates applied edits — that is its purpose.**
Transaction rollback is a *convenience* (the "check without applying" probe), **not** a safety
mechanism. The one safety property that matters is: **the app only ever writes to a database it
provisioned**, enforced by a single ownership gate in a single place
(`db/sandbox.py::open_sandbox`). Rollback discipline is not threaded through the code.

Consequence this plan takes seriously: interdependent edits (edit `A` which calls `B`, also
edit `B`) must be validatable together. A pristine-baseline-per-check model cannot do that.
The stateful working set can.

---

## Phase 1 — `run_queries` grows the capabilities the ladder actually needs

**Why first:** everything downstream depends on it, and — bluntly — **the spec is wrong about
this one**. §18.5 currently says tier 2 "needs *no new write path*: it is the existing runner,
used as-is." That is false in two independent ways (see Risks R1, R2). Nothing works until
this lands.

### Task 1.1: non-row-returning statements

**Files:** modify `pgtp_editor/db/introspect.py::run_queries`; test `tests/db/test_run_queries.py`.

`run_queries` today does `cursor.execute(sql); results.append(cursor.fetchall())` for every
statement. In psycopg 3, `fetchall()` on a statement that produced no result set raises
`ProgrammingError: the last operation didn't produce a result`. Every statement §18.5 needs to
run — `SET`, `CREATE FUNCTION`, `CREATE TRIGGER`, `CREATE EXTENSION`, `CREATE DATABASE`,
`INSERT` — is exactly that.

- [ ] Guard on `cursor.description is None` → append `[]` rather than calling `fetchall()`.
- [ ] The returned list keeps its 1:1 positional correspondence with `sql_list`, so
      `fetch_schema`'s `relation_rows, column_rows, constraint_rows = runner(...)` unpacking is
      untouched.

Tests: fake cursor with `description = None` → `run_queries` returns `[[]]` and never calls
`fetchall`; fake cursor with a description → unchanged behaviour (the three existing tests must
still pass verbatim).

### Task 1.2: `autocommit`

**Files:** modify `run_queries`; test `tests/db/test_run_queries.py`.

- [ ] Add keyword-only `autocommit: bool = False`, passed to `psycopg.connect(autocommit=...)`.
- [ ] Under `autocommit=True`, callers that want atomicity put explicit `"BEGIN"` / `"COMMIT"`
      statements in `sql_list` (psycopg permits this when autocommit is on). That is how
      Phase 3's *apply* stays atomic without `run_queries` growing a `commit()` API.
      `CREATE DATABASE` uses `autocommit=True` with no `BEGIN` (PostgreSQL forbids it in a
      transaction block).
- [ ] `run_queries` remains the sole psycopg call site. No blessed narrow path, no ceremony —
      it is an ordinary parameter.

Tests: default → `connect(autocommit=False)`; `autocommit=True` → passed through.

### Task 1.3: notice capture

**Files:** modify `pgtp_editor/db/introspect.py` (new `Notice` dataclass + `run_queries` param);
test `tests/db/test_run_queries.py`.

Tier 1 (`plpgsql.extra_warnings = 'all'`) does **not** return rows. PostgreSQL emits its
findings as asynchronous `WARNING` messages during `CREATE FUNCTION`. `run_queries` discards
them entirely today, so tier 1 does not exist without this.

- [ ] `@dataclass(frozen=True) class Notice: severity, message, detail=None, hint=None, context=None, sqlstate=None`
      — a psycopg-free normalization, so `db/ddl_check.py` never touches a psycopg object.
- [ ] `run_queries(..., *, notices: list[Notice] | None = None)`: when given, register
      `connection.add_notice_handler(...)` and append a normalized `Notice` per diagnostic
      (duck-typed `getattr` on `severity`/`message_primary`/`context`/`sqlstate`).

Tests: a fake connection whose `add_notice_handler` is invoked with a stub diagnostic → the
list receives a `Notice` with the mapped fields; `notices=None` → handler never registered.

### Task 1.4: `QueryFailure` — which statement failed

**Files:** modify `pgtp_editor/db/introspect.py`; test `tests/db/test_run_queries.py`.

The ladder is necessarily **one** `run_queries` call (the transaction/session must span
`SET` → DDL → check). When it raises, the caller must know *which* statement failed to
attribute the failure to the right tier — misattributing a plpgsql_check call failure to
"your DDL is broken" is precisely the silent-wrong-result class this project refuses.

- [ ] `class QueryFailure(Exception)` defined unconditionally (no psycopg import), carrying
      `index`, `statement`, `message`, `sqlstate`, `detail`, `hint`, `context`, `position`.
- [ ] `run_queries` wraps a per-statement exception: `raise QueryFailure(...) from exc`,
      extracting fields by `getattr(exc, "diag", None)` duck-typing.
- [ ] `__str__` must render the primary message verbatim so `test_connection`'s
      `(False, str(exc))` contract and MainWindow's status-bar strings do not regress.

Tests: fake cursor raising on the 2nd of 3 statements → `QueryFailure.index == 1`, statement
text preserved, `str()` equals the original message, `__cause__` is the original exception;
`test_connection` still returns `(False, <same message>)`.

**Cheaper alternative if this is judged too much:** order the statement list so only the DDL can
plausibly fail, and attribute any exception to tier 2. It is wrong for trigger functions
(plpgsql_check errors with *"missing trigger relation"*), so I recommend against it.

### Task 1.5: widen the `Runner` alias

**Files:** modify `pgtp_editor/db/introspect.py`.

- [ ] `Runner` is `Callable[[ConnectionParams, list[str]], list[Rows]]` — too narrow once call
      sites pass `autocommit=`/`notices=`. Widen to a `Protocol` with the keyword-only params
      defaulted, or to `Callable[..., list[Rows]]`.
- [ ] Every fake runner written in Phases 3–4 must accept `**kwargs`. Existing fakes in
      `tests/db/test_introspect.py` are unaffected (nothing passes the new kwargs to them).

**Done means:** `python -m pytest -q` green; `run_queries` can execute a `SET`, a
`CREATE FUNCTION`, and a `SELECT` in one call, capture warnings, commit when asked, and report
which statement blew up. No behaviour change for any existing caller.

---

## Phase 2 — Named connection profiles without breaking saved settings

**Why here:** independent of everything else, needed by Phase 3, and §18.2 requires the
identical change. Design it once, for both dimensions.

### Task 2.1: the keyed-group scheme

**Files:** modify `pgtp_editor/db/config.py`; test `tests/db/test_config.py`.

`db/config.py` today hardcodes `_GROUP = "db"`. §18.2 needs a **project key**; §18.5 needs a
**profile role** (`target` | `sandbox`). Spec §17 is explicit that these must land as *one*
keying scheme, not two mechanisms.

- [ ] `@dataclass(frozen=True) class ProfileKey: project: str = ""; role: str = "target"`.
      `DEFAULT_PROFILE = ProfileKey()`.
- [ ] `_group_for(key) -> str`:
      - `key == DEFAULT_PROFILE` → **the literal string `"db"`** — the existing group, byte for
        byte.
      - otherwise → `"db_profiles/" + _slug(key.project) + "/" + key.role`, where `_slug` hashes
        the project path (`hashlib.sha1(path.casefold().encode()).hexdigest()[:16]`, `""` →
        `"_global"`) because QSettings group names cannot contain `/` or `\`.
- [ ] `load_connection(settings, key=DEFAULT_PROFILE)`,
      `save_connection(settings, params, key=DEFAULT_PROFILE)`,
      `seed_params(tree, settings, key=DEFAULT_PROFILE)` — all three gain a trailing defaulted
      parameter. Every existing call site keeps working unchanged.

**Why this beats read-fallback-plus-dual-write:** by routing the default profile back to the
*same* group name, existing users' saved connections are not migrated at all — there is nothing
to migrate, nothing to get wrong, and a downgrade to an older build still reads them. The 8
existing tests in `tests/db/test_config.py` pass with zero edits, which is itself the
compatibility proof.

- [ ] `seed_params` for a **sandbox** key must **not** fall back to the project's
      `<ConnectionOptions>` (that is the target database — seeding the sandbox from it is how you
      accidentally point the sandbox at production). Sandbox seeding = saved settings only, else
      blanks with a sensible `localhost`/`5432` default.

Tests: default key writes/reads the `db` group and the pre-existing keys are literally the ones
read; a sandbox key round-trips independently and does not disturb the default; two different
project keys stay independent; `_slug` is stable and case-insensitive on Windows-style paths;
`load_connection` on an absent/garbage group returns `None` and never raises;
`seed_params(tree, settings, sandbox_key)` ignores `<ConnectionOptions>`.

**Done means:** two profiles persist side by side, the old `db` keys are still the default
profile, and `tests/db/test_config.py` is green with only *added* tests.

---

## Phase 3 — `db/sandbox.py`: ownership, capabilities, provisioning, working set

**Why here:** this is where the safety property lives, and Phase 4 cannot be written against a
moving target.

### Task 3.1: `SandboxCapabilities` + the three-state probe

**Files:** create `pgtp_editor/db/sandbox.py`; test `tests/db/test_sandbox.py`.

- [ ] `@dataclass(frozen=True) class SandboxCapabilities: server_version: tuple[int,...] = (); is_superuser: bool = False; installed_extensions: frozenset[str] = frozenset(); available_extensions: frozenset[str] = frozenset(); database: str = ""; owner_marker: str | None = None; probe_error: str | None = None`
- [ ] `plpgsql_check_state` property → `"installed"` / `"installable"` / `"absent"` /
      `"unknown"` (the last when `probe_error` is set — **never** silently `"absent"`).
- [ ] `PROBE_SQL: list[str]` — five statements, module-level constants like `SCHEMA_SQL`:
      `current_setting('server_version_num')`; `current_setting('is_superuser')` (works for
      non-superusers, unlike `pg_user.usesuper`); `SELECT extname FROM pg_extension`;
      `SELECT name FROM pg_available_extensions`;
      `SELECT current_database(), shobj_description(oid,'pg_database') FROM pg_database WHERE datname = current_database()`.
- [ ] `probe(params, runner=run_queries) -> SandboxCapabilities` — never raises; a failure
      becomes `probe_error`.

Tests: canned rows → each of the three plpgsql_check states; runner raising → `probe_error` set
and state `"unknown"`; superuser on/off parsing; version tuple parsing from `170004`.

### Task 3.2: the ownership gate — **one guard, one place**

**Files:** modify `pgtp_editor/db/sandbox.py`; test `tests/db/test_sandbox.py`.

- [ ] `SANDBOX_DB_PREFIX = "pgtp_sandbox_"`, `OWNER_MARKER_PREFIX = "pgtp-editor-sandbox:"`.
- [ ] `is_app_owned(database: str, owner_marker: str | None) -> bool` — pure: the name starts
      with the prefix **and** the `pg_database` comment starts with the marker prefix. The name
      alone is spoofable (a user can name production `pgtp_sandbox_prod`); the comment is written
      only by our own provisioning.
- [ ] `class ForeignDatabaseError(Exception)` — psycopg-free, message names the database and says
      plainly *"PGTP Editor did not create this database and will not write to it."*
- [ ] `open_sandbox(params, runner=run_queries) -> SandboxSession` — probes, checks ownership, and
      **raises `ForeignDatabaseError` if not owned**. This is the *only* gate. Everything that
      writes goes through the returned `SandboxSession`; nothing else in the codebase re-checks
      ownership, and no write path exists that bypasses the session.
- [ ] Reads (probe, listing, provisioning-source introspection of the *target*) are not gated.

Tests: owned/unowned/marker-missing/prefix-missing matrix on the pure predicate; `open_sandbox`
against an unowned probe result raises with the database name in the message; a `SandboxSession`
cannot be constructed for an unowned database (make the constructor private-by-convention and
assert `open_sandbox` is the only builder).

### Task 3.3: baseline provisioning

**Files:** modify `pgtp_editor/db/introspect.py` (new catalog SQL + snapshot fn); modify
`pgtp_editor/db/sandbox.py` (the emitter); tests `tests/db/test_introspect.py`,
`tests/db/test_sandbox.py`.

An **empty** sandbox makes tiers 2 and 3 actively harmful: every routine referencing
`pr.equipment` reports `relation "pr.equipment" does not exist` — a false ERROR, which reads
worse than "could not check". Provisioning is therefore core, not deferred (see R4).

Deliberate simplification, and it is a big one: **plpgsql_check is catalog-based and reads no
rows.** It needs relations, columns and types to *exist*; it does not care about primary keys,
foreign keys, defaults, indexes, or data. So the baseline is:

- [ ] `CREATE SCHEMA` per non-system namespace
- [ ] domains and composite types (new catalog query — `pg_type` where `typtype IN ('d','c')`)
- [ ] tables: columns + `format_type` + `attnotnull` only. **No** PK, **no** FK, **no** defaults
      (which also sidesteps `nextval('seq')` needing sequences to exist)
- [ ] views + matviews via `pg_get_viewdef` (new catalog query — without this, any routine
      touching a view fails to compile)
- [ ] routines via the existing `pg_get_functiondef`, emitted under
      `SET check_function_bodies = off` so one bad pre-existing routine cannot block provisioning
- [ ] triggers via the existing `pg_get_triggerdef`, emitted after routines
- [ ] a reserved bookkeeping schema (Task 3.4)

Order is load-bearing: schemas → types → tables → views → routines → triggers.

- [ ] `snapshot_for_baseline(target_params, runner=run_queries) -> BaselineSnapshot` in
      `introspect.py` (reuses `SCHEMA_SQL` + `ROUTINE_TRIGGER_SQL` + the two new queries).
- [ ] `build_baseline_sql(snapshot) -> list[str]` in `sandbox.py` — **pure, no I/O, no DB**. All
      identifiers quoted via a strict allowlist helper; nothing is string-interpolated from user
      text.

Tests: a canned snapshot → assert exact statement ordering, that no PK/FK/DEFAULT/INDEX text is
emitted, that `check_function_bodies = off` precedes routine creation, and that a schema named
`weird"name` is refused rather than interpolated. All Qt-free, DB-free, pure.

**Honest limitation to surface in the UI's "what was checked" text:** extensions, sequences,
constraints, defaults and data are *not* reproduced. Findings that reference them are unreliable.
This must be stated, not buried.

### Task 3.4: the working set — baseline vs. current

**Files:** modify `pgtp_editor/db/sandbox.py`; test `tests/db/test_sandbox.py`.

Reset is only meaningful against a known baseline, and the user must be able to see what is
currently applied. Kept small on purpose:

- [ ] Provisioning creates schema `pgtp_editor_sandbox` with one table
      `applied(kind text, schema_name text, object_name text, table_name text, applied_at timestamptz, text_sha1 text, primary key (kind, schema_name, object_name, table_name))`.
- [ ] `SandboxSession.apply(ref, ddl_text)` → one `run_queries(..., autocommit=True)` call with
      `["BEGIN", <ddl>, <upsert into applied>, "COMMIT"]`. Atomic, committing, stateful.
- [ ] `SandboxSession.applied() -> list[AppliedObject]` → one `SELECT`.
- [ ] `SandboxSession.reset()` → `DROP SCHEMA <each app schema> CASCADE` + re-run
      `build_baseline_sql`. **Schema-level, not `DROP DATABASE`** — dropping the database fails
      while any session is connected and needs a maintenance-DB connection and `WITH (FORCE)`
      (PG 13+). Schema-level reset avoids all of it and is just as complete for our purposes.
- [ ] `text_sha1` lets the UI say exactly *"this tab has changed since you last applied it"* — the
      alternative (an in-memory list) silently forgets across an app restart while the sandbox
      still holds the edits, which is a silent-wrong-state trap.

Tests: `apply` emits `BEGIN`/`COMMIT` around exactly two statements and passes `autocommit=True`;
`applied()` parses rows into `AppliedObject`s; `reset()` emits a `DROP SCHEMA … CASCADE` per app
schema followed by the full baseline; a fake runner asserts the bookkeeping schema is never
included in the drop list.

### Task 3.5: provisioning a new sandbox database, and the one-click extension install

**Files:** modify `pgtp_editor/db/sandbox.py`; test `tests/db/test_sandbox.py`.

- [ ] `create_sandbox_database(admin_params, name, runner=run_queries)`: `name` must match
      `^pgtp_sandbox_[a-z0-9_]{1,40}$` (validated, not sanitized — refuse anything else); runs
      `["CREATE DATABASE \"…\"", "COMMENT ON DATABASE \"…\" IS 'pgtp-editor-sandbox:<uuid>:<iso8601>'"]`
      with `autocommit=True` against the maintenance database (`postgres`).
- [ ] `install_plpgsql_check(session, runner=run_queries)`:
      `["CREATE EXTENSION IF NOT EXISTS plpgsql_check"]` with `autocommit=True`. Reachable only
      through a `SandboxSession`, which by construction means the database is app-owned.
- [ ] `install_gate(caps) -> tuple[bool, str]` — pure. Offer the install only when
      `plpgsql_check_state == "installable"` **and** `caps.is_superuser`. Otherwise return the
      exact reason string the UI shows:
      - state `"installed"` → *"already installed."*
      - state `"installable"`, not superuser → *"`CREATE EXTENSION` requires superuser; ask your
        DBA, or connect the sandbox profile as a superuser."*
      - state `"absent"` → the platform text: Linux `apt install postgresql-NN-plpgsql-check`
        (PGDG) / `dnf install plpgsql_check_NN`; Windows the ~350 KB DLL drop from `pgsql.cz`
        (2.8.5, PG 17/18, x64 only). **The app cannot fix this — it is a C library on disk.**
        Tier 3 reports unavailable-with-reason, never clean.
      - state `"unknown"` → *"could not probe the server."*

Tests: the four gate states → correct `(bool, reason)`; database-name validator accepts/rejects
the right shapes; `install_plpgsql_check` passes `autocommit=True`.

**Done means:** given a fake runner, the module can probe, refuse a foreign database, emit a
correct baseline, apply and list a working set, reset, and decide whether to offer the install —
all Qt-free, psycopg-free, with no live server.

### Task 3.6: `PostgresBackend`

**Files:** modify `pgtp_editor/db/sandbox.py`.

- [ ] `class PostgresBackend(Protocol)`: `ensure_running() -> ConnectionParams`,
      `capabilities() -> SandboxCapabilities`.
- [ ] `class LocalPostgresBackend`: `__init__(params, runner=run_queries)`; `ensure_running`
      returns the configured params and raises loudly (not silently) if `test_connection` fails;
      `capabilities` delegates to `probe` and caches.
- [ ] Lives here, Qt-free, so a managed/bundled server (§29) can be added later without the
      choice leaking into `ui/`.

---

## Phase 4 — `db/ddl_check.py`: the ladder

### Task 4.1: `CheckFinding`, tier outcomes, `CheckReport`

**Files:** create `pgtp_editor/db/ddl_check.py`; test `tests/db/test_ddl_check.py`.

- [ ] `CheckFinding` **mirrors and extends** `validation/tier2.py::ValidationIssue`'s
      `{severity, message, line}` (the same pattern-extension precedent §18.4 set with
      `xsd_verify.Issue`) and adds `sqlstate, level, position, statement, detail, hint, context,
      tier, object_ref`. **Do not widen `ValidationIssue`** — its three fields are asserted by
      existing tests and it belongs to `.pgtp` structural validation.
- [ ] `TierOutcome`: `status` ∈ `passed | found_issues | unavailable | errored`, plus `reason`
      and `detail`. **The hard rule: an unavailable tier reports "could not check", never
      "clean."**
- [ ] `CheckReport{tier0..tier3: TierOutcome, findings: list[CheckFinding], caveats: list[str]}`.
      `caveats` carries the honest text: the baseline's missing extensions/constraints/data, and
      plpgsql_check's known blind spots (dynamic `EXECUTE`, `refcursor` into `record`, runtime
      temp tables).

### Task 4.2: the line-number mapping — pin it before anything renders a line

**Files:** modify `pgtp_editor/db/ddl_check.py`; test `tests/db/test_ddl_check.py`.

plpgsql reports `lineno` relative to **`prosrc`** (the dollar-quoted body), while the tab's
buffer is **`pg_get_functiondef`** output (header + body). An off-by-header-length line number
is exactly the silent-wrong-result class this project refuses.

- [ ] `body_line_offset(buffer_text) -> int | None`: locate the opening dollar-quote tag (`$$`,
      `$function$`, `$body$`, …) that begins the body; return its **1-based line number** `L`.
- [ ] `map_lineno(buffer_text, lineno) -> int | None` → `L + lineno - 1`. Rationale: `prosrc`
      begins with the newline that terminates the `AS $tag$` line, so `prosrc` line 1 *is* line `L`.
- [ ] **If the opener cannot be found, `lineno` is falsy, or the result is out of range → return
      `None`, and the finding is rendered with no line at all.** Never guess.
- [ ] Tier-2 failures come with a psycopg `position` (a character offset into the statement we
      sent, which *is* the buffer) → `line = buffer_text.count("\n", 0, position) + 1`. Exact, no
      offset needed.
- [ ] Tier-1 warnings arrive as `Notice.context` strings like
      `compilation of PL/pgSQL function "f" near line 3` → regex the line, then apply the same
      `map_lineno`.

Tests: a real `pg_get_functiondef` fixture (captured verbatim into the test file), a
`LANGUAGE sql` variant, a body opened on the same line as `AS $$`, a `$body$`-tagged variant, a
buffer with a `$$` inside a comment before the real opener, and a buffer with no opener at all →
`None`. **Plus Task 9.1's live confirmation before Phase 7 ships.**

### Task 4.3: the ladder driver

**Files:** modify `pgtp_editor/db/ddl_check.py`; test `tests/db/test_ddl_check.py`.

Three entry points matching the three user gestures:

- [ ] `probe_check(session, ref, ddl_text, caps, runner=run_queries) -> CheckReport` — "Check
      without applying." One `run_queries` call, `autocommit=False`, statement list:
      `["SET plpgsql.extra_warnings = 'all'", "SET plpgsql.extra_errors = 'all'", <ddl>, <plpgsql_check select if available>]`,
      with `notices=[]`. Because `run_queries` never commits and closes in a `finally`, this is
      implicitly rolled back — a *convenience*, not a guard.
- [ ] `apply_and_check(session, ref, ddl_text, caps, runner=run_queries) -> CheckReport` — commits
      via `session.apply`, then runs the plpgsql_check select. Tier 2's outcome is the apply's
      outcome.
- [ ] `recheck(session, ref, caps, runner=run_queries) -> CheckReport` — the ladder against the
      sandbox **as it currently stands**, no DDL. Tier 2 reports `passed` with
      *"applied <timestamp>"* from the bookkeeping table. If the caller's buffer hash differs from
      `applied.text_sha1`, the report carries a caveat saying so — never silently check a stale
      version.
- [ ] Tier attribution uses `QueryFailure.index` against the statement list it built.
- [ ] Tier 0 collapses into tier 2 (PostgreSQL's own parser is the syntax checker) and reports
      `unavailable("no sandbox connection")` when there is none. **No `pglast` dependency** — it is
      GPL-3.0-or-later and the spec records it as license-load-bearing.

### Task 4.4: the plpgsql_check call shape

**Files:** modify `pgtp_editor/db/ddl_check.py`; test `tests/db/test_ddl_check.py`.

Every one of these is a call-shape requirement, verified against the shipped
`plpgsql_check--2.10.sql`:

- [ ] `plpgsql_check_function_tb` — **not** `plpgsql_check_function` (`format` exists only on the
      latter). Select list must double-quote `"position"`. 11 columns, mapping 1:1 onto
      `CheckFinding`.
- [ ] **Always named notation.** Positional order is
      `other_warnings, performance_warnings, extra_warnings` — not the README's order.
- [ ] The parameter is misspelled **`anyelememttype`** (`m` for `n`). Use the typo verbatim.
- [ ] `fatal_errors => false` (else exactly one finding per function) and `all_warnings => true`.
- [ ] **Trigger functions require `relid`** — omitting it errors *"missing trigger relation"*.
      Pass the table OID via `to_regclass('<schema>.<table>')`, plus `oldtable`/`newtable` from
      `pg_trigger.tgoldtable`/`tgnewtable` when transition tables are declared.
- [ ] `level` → Audit `SEVERITY`: `error`→`ERROR`; anything starting `warning`→`WARNING`;
      `compatibility`→`NOTE`. Raw string preserved in `CheckFinding.level`.

**Getting the OID of the just-applied object** is specified nowhere in the brief or spec (R6).
Plan: primary = `to_regprocedure(format('%s.%s(%s)', schema, name, argtypes))` built from the
`RoutineInfo` the tree gave us; fallback when the user edited the signature =
`SELECT oid FROM pg_proc WHERE xmin = pg_current_xact_id()::text::xid` inside the apply
transaction (the catalog row we just wrote is the one with our xid). The fallback is clever and
therefore suspect — it must be confirmed by Task 9.1 before it is relied on.

**Trigger objects:** the tab holds `CREATE TRIGGER`, but tier 3 checks *functions*. For a trigger
tab, tier 2 is the `CREATE TRIGGER` itself and tier 3 checks the *referenced* function with
`relid` set. Note also that `CREATE OR REPLACE TRIGGER` only exists on PG 14+; below that the
statement list needs a preceding `DROP TRIGGER IF EXISTS`. Gate on `caps.server_version`.

Tests: golden-string assertions on the generated SQL (typo present, named notation, quoted
`"position"`, `fatal_errors => false`, `relid` present for triggers and absent for plain
functions, `DROP TRIGGER IF EXISTS` emitted only below PG 14); canned 11-column rows →
`CheckFinding`s with correct severity mapping and mapped lines; a fake runner raising
`QueryFailure(index=2)` → tier 2 `found_issues` with the position-derived line and tier 3
`unavailable("the object was never created")`; `notices=[…]` → tier 1 findings; missing extension
→ tier 3 `unavailable` with the platform install text and **no** claim of cleanliness.

**Done means:** the whole ladder is exercisable Qt-free with fake runners, and every tier can be
driven into all four outcome states.

---

## Phase 5 — The editable tab (ships useful with no sandbox at all)

### Task 5.1: `ui/ddl_object_panel.py`

**Files:** create `pgtp_editor/ui/ddl_object_panel.py`; test `tests/ui/test_ddl_object_panel.py`.

**New widget, not a mode on `EditorPanel`.** Justification, and the spec has already settled it
(§18.1: *"`EditorPanel` is read-only permanently, not provisionally"*): `EditorPanel` holds a
regenerated multi-object buffer whose spans are invalidated by every re-fetch, and it is
re-populated wholesale on each DDL Explorer open. Per-object dirty state, per-object save paths,
per-object apply/check and a per-object tab title `*` cannot live on a shared buffer that is
replaced under them. A mode flag would also fight §18.2's file-per-object model. Separate widget.

- [ ] `@dataclass(frozen=True) class DdlObjectRef: kind, schema, name, table, arg_types` with a
      `token` property → `f"{kind}|{schema}|{name}|{table or ''}"` (used by Audit routing).
- [ ] `class DdlObjectPanel(QWidget)`: `CodeEditor(language="sql")` + its own `FindReplaceBar`,
      exactly like `EditorPanel`. Theme needs no wiring — `CodeEditor.changeEvent` already
      re-tints its own gutter.
- [ ] Content injection, per the spec's *"written against an injected load/save pair, not against
      a hard-coded source"*: constructor takes `ref`, initial `text`, and
      `resolve_save_path: Callable[[], Path | None]`.
- [ ] `text()`, `set_text()`, `is_dirty()`, `mark_clean()`, `navigate_to_line(line)`,
      `dirty_changed = Signal(bool)`, `tab_title()` → `f"{schema}.{name}"` (+ `" *"` when dirty).
- [ ] `resolve_save_path()` default in v1 returns the panel's remembered `_save_path` (`None`
      until Save As picks one). **§18.2's change is exactly this one function returning
      `project.ddl_dir / f"{schema}.{name}.sql"`.** No restructure.
- [ ] `applied_sha1` slot so Phase 7 can render "changed since last applied".
- [ ] Wire §18.4's `format_selection` here when it exists — this tab is its designated first
      consumer. Leave a named hook, do not block on §18.4.

Tests: dirty flips on edit and clears on `mark_clean`; `tab_title` carries the `*`;
`navigate_to_line` moves the caret; `resolve_save_path` is honoured; find bar is per-instance.

### Task 5.2: dynamic tabs in `CenterStage`

**Files:** modify `pgtp_editor/ui/center_stage.py`; test `tests/ui/test_center_stage.py`.

`CenterStage` stores **fixed tab indices** (`raw_xml_tab_index`, `xsd_tab_index`,
`ddl_tab_index`, …) which `_active_find_bar`, `_active_bookmark_editor`, `_save_active_tab`,
`_on_ddl_navigate_requested` and every `hide_*` compare against. Dynamic tabs are safe **only**
under append-only creation and tail-only removal (R8).

- [ ] `add_ddl_object_tab(panel, title) -> int` — always `addTab` (appends), never `insertTab`.
- [ ] `ddl_object_panels() -> list[DdlObjectPanel]`.
- [ ] `close_ddl_object_tab(panel)` — `removeTab(indexOf(panel))` + `deleteLater()`.
- [ ] `ddl_object_close_requested = Signal(object)` — emits the panel, so MainWindow owns the
      dirty prompt (same intent-not-action pattern as `xsd_close_requested`).
- [ ] `_on_tab_close_requested` gains a **first** branch:
      `widget = self.widget(index); if isinstance(widget, DdlObjectPanel): emit; return`. It must
      precede the static-index comparisons.
- [ ] `setTabsClosable(True)` is already global, so new tabs get their ✕ for free.

Tests (the invariant test is the important one): open two object tabs, close the first, then
assert `widget(raw_xml_tab_index) is raw_xml_tab`, `widget(xsd_tab_index) is xsd_tab`,
`widget(ddl_tab_index) is ddl_editor_panel`, `widget(manual_tab_index) is manual_panel` — all
still correct; closing an object tab emits the signal and does **not** remove the tab itself.

### Task 5.3: right-click → Edit… in `BrowserPanel`

**Files:** modify `pgtp_editor/ui/ddl_buffer_panel.py`; test `tests/ui/test_ddl_buffer_panel.py`.

- [ ] `edit_requested = Signal(object)` emitting the `DdlObjectSpan`.
- [ ] `self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)` +
      `customContextMenuRequested` → `_on_context_menu(pos)`, following
      `ui/db_check_panel.py`'s precedent (lines 77–78, 232–253).
- [ ] Split out `_context_menu_for(item) -> QMenu | None` so tests build the menu and trigger the
      action **without ever calling `exec()`**. Returns `None` for branch nodes and argument leaves
      (they carry no `_SPAN_ROLE`), matching the existing click behaviour.

Tests: a routine leaf yields a menu whose sole action is "Edit…"; triggering it emits
`edit_requested` with the right span; the "Tables" root and an argument leaf yield `None`.

### Task 5.4: MainWindow — open, save, close

**Files:** modify `pgtp_editor/ui/main_window.py`; test `tests/ui/test_ddl_object_wiring.py` (new).

- [ ] `_open_ddl_explorer`'s `on_result` gains `self._last_ddl_schema = schema` — the span alone
      carries no source text, so the panel's content must come from `RoutineInfo.source` /
      `TriggerInfo.definition`. Mirrors the existing `_last_db_schema` cache.
- [ ] `self._ddl_object_tabs: dict[str, DdlObjectPanel]` keyed by `ref.token`.
- [ ] `_on_ddl_edit_requested(span)`: if the token is already open → `setCurrentWidget` and return
      (never two tabs for one object); else build the ref + text, create the panel, add the tab,
      connect `dirty_changed` → `_update_ddl_tab_title(panel)`.
- [ ] `_save_active_tab` gains a branch **before** the `xsd_tab_index` check:
      `widget = stage.currentWidget(); if isinstance(widget, DdlObjectPanel): return self._save_ddl_object(widget)`.
      (§7's "Ctrl+S is asymmetric" note still holds for the read-only DDL Explorer buffer.)
- [ ] `_save_ddl_object(panel)`: `path = panel.resolve_save_path()`; `None` → `_save_ddl_object_as`;
      else write UTF-8 with `newline=""`, mirroring `_save_xsd` exactly; `OSError` →
      `QMessageBox.critical` (patched in tests); `panel.mark_clean()`; status message.
- [ ] `_save_ddl_object_as(panel)`:
      `QFileDialog.getSaveFileName(self, "Save DDL Object", f"{schema}.{name}.sql", "SQL files (*.sql)")`
      — patched in tests. Remembers the path on the panel so subsequent Ctrl+S is silent.
- [ ] `_confirm_close_ddl_object() -> "save"|"discard"|"cancel"` — a separate patchable method
      mirroring `_confirm_close_xsd`, never a second confirmation mechanism.
- [ ] `_on_ddl_object_close_requested(panel)`: dirty → prompt; `cancel` → return; `save` → save and
      if still dirty (Save As cancelled / write failed) → return; then `close_ddl_object_tab` + drop
      from `_ddl_object_tabs`.
- [ ] `closeEvent`: iterate `ddl_object_panels()`; any dirty → same prompt; `cancel` →
      `event.ignore()`. Runs alongside the existing `_xsd_dirty` block.
- [ ] `_active_find_bar` and `_active_bookmark_editor` each gain the same
      `isinstance(currentWidget(), DdlObjectPanel)` branch — `_active_bookmark_editor` still with no
      tab-switching side effect.

Tests (all with a patched `_fetch_ddl_schema`, `_run_async` stub, and patched
`getSaveFileName`/`QMessageBox`): right-click → tab opens with the routine's source; re-opening the
same object focuses the existing tab; edit → title gains `*`; Ctrl+S with no path calls Save As;
Ctrl+S with a path writes the file and clears `*`; close-while-dirty with `cancel` keeps the tab;
with `discard` drops it; `closeEvent` with a dirty tab and `cancel` ignores the event; Ctrl+F on
the object tab returns *its* bar, not Raw XML's.

**Done means:** a user can open, edit, format, and Save As a routine to a `.sql` file. Zero
sandbox, zero database writes, real value shipped.

---

## Phase 6 — Sandbox Setup: the profile, the probe, the working set

### Task 6.1: `ConnectionSetupDialog` gains a profile dimension — **not a fork**

**Files:** modify `pgtp_editor/ui/connection_setup_dialog.py`;
test `tests/ui/test_connection_setup_dialog.py`.

- [ ] `__init__(..., profile: ProfileKey = DEFAULT_PROFILE, prober=sandbox.probe, installer=sandbox.install_plpgsql_check)`
      — new injectable seams alongside the existing `tester=`, same pattern.
- [ ] A `QComboBox` role selector (Target / Sandbox), preselected from `profile`, emitting
      `profile_changed(role)`. **The dialog stays dumb** — MainWindow reacts by re-seeding via
      `set_params(seed_params(tree, settings, new_key))`. No persistence logic in the dialog.
- [ ] A capability block, visible only for the sandbox role: a status label, a "Probe" button, and
      an "Install plpgsql_check" button whose enabled state and tooltip come straight from
      `sandbox.install_gate(caps)`. The three states render distinctly:
      installed → *"plpgsql_check 2.x installed — tier 3 available"*;
      installable → the enabled install button;
      absent → the platform instructions, install button **disabled with the reason**.
- [ ] A working-set list (a plain `QListWidget`) showing `session.applied()`, plus a
      **Reset Sandbox** button. Deliberately minimal — a list and a button, not a manager.
- [ ] The existing plaintext-password caveat label must show for the sandbox profile too.
- [ ] Probe / install / reset all go through the caller's `_run_async` (the dialog already owns an
      injectable `self._run_async`, line 58). A dead sandbox host must never freeze the dialog.

Tests: role combobox switches and emits; a stub prober returning each of the four capability states
drives the right label text and install-button enablement; a stub installer is called on click and
the label refreshes; the applied list renders canned `AppliedObject`s; **no `.exec()`**.

### Task 6.2: Database menu + MainWindow wiring

**Files:** modify `pgtp_editor/ui/main_window.py::_build_database_menu`;
test `tests/ui/test_database_menu.py`.

- [ ] After the DDL Explorer toggle: `menu.addSeparator()`, then **Sandbox Setup…**
      (`_open_sandbox_setup`) and **Check DDL Object** (`_check_active_ddl_object`), per the spec's
      menu inventory. The one-click install lives **inside** the Sandbox Setup dialog, next to the
      probe result it depends on — not as a fourth menu item.
- [ ] **Check DDL Object** is disabled unless `isinstance(currentWidget(), DdlObjectPanel)`; keep it
      in sync on `center_stage.currentChanged`.
- [ ] No new top-level menu. No "locate binary" action — v1 spawns no external process.
- [ ] Provisioning flow in `_open_sandbox_setup`: if the configured sandbox database is not
      app-owned, `open_sandbox` raises `ForeignDatabaseError` → show the refusal **plus** an explicit
      *"Create a sandbox database for me"* offer (`create_sandbox_database` + `build_baseline_sql`
      from the target profile, off-thread with `busy_status`). The refusal without a way forward is
      the fastest route to the user concluding the tool is broken (R5).

Tests: menu inventory and separator placement (using `tests/ui/_menu_helpers.py`); Check DDL Object
enable/disable follows the active tab; `_open_sandbox_setup` holds the dialog on `self` so it is not
GC'd (the `_connection_dialog` precedent) and shows it non-modally.

---

## Phase 7 — Check wiring and `[Check]` diagnostics

### Task 7.1: the three gestures

**Files:** modify `pgtp_editor/ui/ddl_object_panel.py` (a small button row) and
`pgtp_editor/ui/main_window.py`; test `tests/ui/test_ddl_check_wiring.py` (new).

- [ ] Panel button row: **Apply to Sandbox** / **Check** / **Check without applying**. Each emits a
      signal; MainWindow owns all DB work.
- [ ] `_check_active_ddl_object(mode)` → `busy_status` + `self._run_async` around
      `ddl_check.apply_and_check` / `recheck` / `probe_check`. Every connection-opening call is off
      the GUI thread; a dead sandbox never freezes the window.
- [ ] Guards, each with a specific status message: no sandbox profile configured → open Sandbox
      Setup; `ForeignDatabaseError` → the refusal message; `QueryFailure` → surfaced as findings, not
      as a crash.
- [ ] After `apply_and_check`, refresh `panel.applied_sha1` so the tab can say *"changed since last
      applied"*. **Check** on a tab whose text differs from `applied.text_sha1` emits a `[Check]`
      caveat line saying exactly that — never a silent check of a stale version.

### Task 7.2: Audit panel rendering + routing

**Files:** modify `pgtp_editor/ui/main_window.py`; test `tests/ui/test_ddl_check_wiring.py`.

- [ ] `_CHECK_PREFIX = "[Check] "` beside the existing `_FIND_RESULT_PREFIX` / `_VALIDATION_PREFIX`.
      §22 reserves `[Lint]` for PHP; the two are reserved against each other in both directions.
- [ ] `_clear_check_results()` — the exact `_clear_validation_results` shape (iterate from the bottom
      so removals don't shift unvisited indices). Called at the start of every run.
- [ ] Finding lines: `f"[Check] {SEVERITY} line {N}: {message}"`, or
      `f"[Check] {SEVERITY}: {message}"` when the line could not be established.
- [ ] **One line per tier, always**, stating `passed` / `N issue(s)` / `could not check: <reason>`.
      An unavailable tier is never collapsed into the overall OK state, never hidden behind a
      preference, never a dismissible toast. Plus one line per `report.caveats` entry (the baseline's
      missing extensions/constraints, plpgsql_check's blind spots).
- [ ] `UserRole` = line (`None` → click is already a no-op).
- [ ] `UserRole+1` = **`f"ddl:{ref.token}"`**. The existing convention is `None` → Raw XML and
      `"xsd"` → the XSD tab, so a namespaced string slots in cleanly. A plain string is deliberately
      chosen over stashing the widget: a `QListWidgetItem` outliving a closed tab would hold a
      dangling reference.
- [ ] `_on_audit_item_clicked` gains a branch **before** `target == "xsd"`:
      ```python
      if isinstance(target, str) and target.startswith("ddl:"):
          panel = self._ddl_object_tabs.get(target[4:])
          if panel is None:
              self.statusBar().showMessage("That DDL tab has been closed.", 5000); return
          self.center_stage.setCurrentWidget(panel); panel.navigate_to_line(line); return
      ```
      `setCurrentWidget`, not `setCurrentIndex` — dynamic tabs have no stable index.

Tests: a canned `CheckReport` → exact `[Check]` line texts including the tier-outcome lines; an
unavailable tier renders *"could not check"* and the summary is **not** green; clicking a finding
focuses the right panel and moves its caret; clicking after the tab is closed shows the status
message and does not crash; a finding with `line=None` renders without a line and clicks as a
no-op; `_clear_check_results` leaves `[Find]`/`[Validate]`/`[Schema]` entries untouched; re-running
clears only prior `[Check]` entries.

**Done means:** edit → Apply → Check → click a finding → land on the offending line. And a missing
plpgsql_check produces a visible *"tier 3: could not check — <how to install it>"*, never a clean
bill of health.

---

## Phase 8 — Generate Deployment SQL: the deliverable

**Why here:** it needs the sandbox working set (Phase 3) and is worthless without validation
(Phase 7) — you must not ship a deployment script assembled from routines nobody proved compile.
It is the last thing built and the first thing the user cares about.

**§18.3 reuse, not a parallel engine.** §18.3 already specifies
`db/schema_diff.py::diff_schemas`, `db/migration_gen.py::generate_migration`,
`Database ▸ Compare Schemas…` and `Save Migration As…`, under the explicit framing *"One
diff/generation engine, two entry points — there are not two separate 'assemble SQL' mechanisms."*
Phase 8 **creates those two modules with §18.3's exact dataclass shape** and implements **only the
routine/trigger cases**. The table/column cases are defined in the type and left unimplemented,
raising a clear `UnsupportedDifference` that the caller turns into an honest refusal. §18.3 proper
fills them in later; nothing here is thrown away.

**Divergence from §18.3 worth stating:** §18.3 assumed the desired state comes from a checked-in
JSON snapshot (`db/schema_snapshot.py`). A **live sandbox is a strictly better source** — you can
execute against it, so the desired state is provably coherent before it is diffed. Phase 8
therefore adds a third source alongside §18.3's "live connection or snapshot": the sandbox. It does
**not** build `db/schema_snapshot.py`; that stays §18.3's.

### Task 8.1: `db/schema_diff.py` — the §18.3 shape, routine/trigger cases only

**Files:** create `pgtp_editor/db/schema_diff.py`; test `tests/db/test_schema_diff.py`.

- [ ] `@dataclass(frozen=True) class SchemaDifference: kind: str; object_kind: str; identity: str; old_def: str | None; new_def: str | None`
      — **verbatim §18.3**: `kind ∈ added|removed|changed`,
      `object_kind ∈ table|column|routine|trigger`. Do not "improve" the field names; §18.3's full
      engine will populate the same type.
- [ ] `diff_schemas(source: DatabaseSchema, target: DatabaseSchema) -> list[SchemaDifference]` —
      §18.3's signature. Pure, Qt-free, no I/O. Mirrors `diff/differ.py::diff_project`'s contract
      shape but DB-object-keyed rather than XML-node-keyed.
- [ ] **Implemented:** `object_kind="routine"` and `"trigger"`. Keyed on `DatabaseSchema.routines` /
      `.triggers`, which `fetch_routines_and_triggers` already populates for any connection —
      sandbox or production — with no new catalog query.
- [ ] **Not implemented:** `object_kind="table"`/`"column"`. `diff_schemas` skips
      `source.tables`/`target.tables` entirely and records the omission in a returned
      `unsupported: list[str]` (or a module-level `SUPPORTED_OBJECT_KINDS` the caller checks), so the
      UI can state *"table and column changes are not compared — §18.3"* rather than implying the
      diff was complete. **A silently table-blind diff presented as a full migration is exactly the
      silent-wrong-result class this project refuses.**
- [ ] **Routine identity is the full signature**, `schema.name(argtype, argtype)`, built from
      `RoutineInfo.arg_types` — **not** `schema.name`. This is load-bearing, see R14: a changed
      argument type is a *different function* to PostgreSQL, so it must surface as
      `removed` + `added`, never as `changed`.
- [ ] Trigger identity is `schema.table.name`, matching `DatabaseSchema.triggers`' existing key.
- [ ] `changed` is decided by exact text comparison of `RoutineInfo.source` /
      `TriggerInfo.definition`. Both come from `pg_get_functiondef` / `pg_get_triggerdef` on each
      side, so formatting is server-normalized and a cosmetic-only diff is not possible. Note the
      caveat: different server *majors* can render `pg_get_functiondef` differently, producing
      phantom `changed` entries (R16). Report the two server versions in the script header so the
      user can spot it.

Tests (all pure, canned `DatabaseSchema` objects, no runner, no Qt): routine present only in sandbox
→ `added`; only in production → `removed`; differing source → `changed` with both defs; identical →
absent; **an argument-type change yields `removed` + `added`, not `changed`**; a trigger changed on
the same table; tables present on both sides produce **no** differences and **are** listed in
`unsupported`; empty-vs-empty → `[]`.

### Task 8.2: `db/migration_gen.py` — routine/trigger emitter

**Files:** create `pgtp_editor/db/migration_gen.py`; test `tests/db/test_migration_gen.py`.

- [ ] `generate_migration(differences, *, header: str = "") -> str` — §18.3's signature. Pure: no
      I/O, no DB, no Qt. Deterministic output (byte-identical for identical input) so the tests can
      be golden-string assertions.
- [ ] Emission order — §18.3's CREATE→ALTER→guarded-DROP, with only the first and last stages
      populated in v1:
      1. header comment block: generated-at, sandbox and production connection summaries
         (`user@host:port/db`, **redacted — no password**, via the `debuglog.redacted` shape), the
         two server versions, and the explicit *"table/column changes not included"* limitation
      2. `added` + `changed` routines → `CREATE OR REPLACE FUNCTION …` (the `new_def` verbatim;
         `pg_get_functiondef` already emits `CREATE OR REPLACE`)
      3. `added` + `changed` triggers → `DROP TRIGGER IF EXISTS <name> ON <table>;` followed by the
         `new_def`. Triggers have no portable `OR REPLACE` below PG 14, and the drop-then-create pair
         is idempotent and safe on all supported majors — simpler than branching on the target's
         version.
      4. `removed` routines/triggers → **commented-out** guarded `DROP` statements with a
         `-- REVIEW:` marker. Never live DROP text in v1. An object absent from the sandbox is far
         more likely to mean *"the user never touched it"* than *"delete this from production"*, and
         under output model (a) below it is not even reachable.
- [ ] Every statement terminated with `;` and separated by a blank line, so the script is
      copy-pasteable into `psql` and diffable in git.
- [ ] `object_kind` in `("table", "column")` → raise a module-defined `UnsupportedDifference`
      (psycopg-free, Qt-free). The caller renders the refusal. **Never emit a partial script that
      silently drops table changes on the floor.**

Tests: golden-string output for one added routine, one changed routine, one trigger (asserting the
`DROP TRIGGER IF EXISTS` precedes the create), one removed routine (asserting the emitted DROP is
commented and carries `-- REVIEW:`); a `table` difference raises `UnsupportedDifference`; the header
contains no password; two runs over the same input produce identical bytes.

### Task 8.3: dependency ordering — and why the simple answer is the right one

**Files:** modify `pgtp_editor/db/migration_gen.py`; test `tests/db/test_migration_gen.py`.

**Recommendation: stable alphabetical ordering by identity, routines before triggers. Do not make
deployment-SQL generation depend on tier 3.**

- **PL/pgSQL bodies are not resolved at CREATE time.** With `check_function_bodies = on` (the
  default), the plpgsql validator parses the body's *statement structure* only; the SQL expressions
  and statements inside it — including calls to other functions and references to tables — are
  parsed and planned lazily, at first execution. So `CREATE OR REPLACE FUNCTION a()` whose body
  calls `b()` **succeeds even when `b()` does not exist yet.** The strongest evidence is this
  feature's own premise: if CREATE-time validation resolved relations and callees, tier 3
  (`plpgsql_check`) would have nothing to catch. Forward references between plpgsql routines
  therefore need **no** ordering at all. (Pinned by Task 9.1 fact 7.)
- **Exception 1 — `LANGUAGE sql` routines.** These *are* parsed and analyzed at creation, and
  PG 14+ `BEGIN ATOMIC` bodies additionally record **real catalog dependencies**. A SQL-language
  function referencing a not-yet-created function or table **will** fail at CREATE. These genuinely
  need ordering. (Pinned by Task 9.1 fact 8.)
- **Exception 2 — triggers.** `CREATE TRIGGER` resolves its function immediately
  (`pg_trigger.tgfoid` is a hard catalog reference) and the table must already exist. Hence
  "routines before triggers" is a real constraint, not cosmetics.

**Why `plpgsql_show_dependency_tb()` is the wrong tool here, despite looking perfect.** It returns
exactly the `FUNCTION`/`OPERATOR`/`RELATION` dependency set per routine and would drive a clean
topological sort — but it is a `plpgsql_check` function, so **it only covers plpgsql routines:
precisely the language that does not need ordering.** It cannot see inside the `LANGUAGE sql`
routines that actually do. Adopting it would make generating a deployment script depend on tier 3
being installed — an optional, per-database, superuser-gated C extension — in exchange for ordering
information about the cases that were never at risk. **That dependency is not acceptable.** The
deliverable must be producible on a bare PostgreSQL with no extensions.

- [ ] Sort `added`/`changed` differences by `(object_kind_rank, identity)` where routines rank
      before triggers, then alphabetically by identity. Deterministic, dependency-free, testable.
- [ ] If any emitted routine's `new_def` is non-plpgsql (detectable from `RoutineInfo.language`,
      which `fetch_routines_and_triggers` already populates — thread it onto `SchemaDifference` via
      `new_def` or a sibling field), emit a header warning: *"N non-PL/pgSQL routine(s) are included;
      statement order may need manual adjustment (their bodies are resolved at CREATE time)."*
      Honest, cheap, and it does not block.
- [ ] Record `plpgsql_show_dependency_tb`-driven topological ordering as a **follow-on**, not v1 —
      and note that it would only ever be a supplement to, never a replacement for, handling the
      SQL-language case.

Tests: three routines and two triggers → routines first, each group alphabetical; a `LANGUAGE sql`
routine in the set → the header warning appears; an all-plpgsql set → no warning.

### Task 8.4: the one open fork — what goes in the script

**Do not decide this in code. Flag it, present it, let the user choose.**

| | **(a) Working set** | **(b) True diff vs. production** |
|---|---|---|
| Content | everything in the sandbox `applied` table | `diff_schemas(sandbox, production)` at generate time |
| Source | the bookkeeping table from Task 3.4 — already built | one extra `fetch_routines_and_triggers(production)` — read-only, already built |
| Safety | `CREATE OR REPLACE` is idempotent, so re-applying an unchanged routine is a no-op | same |
| Precision | may contain no-op statements for objects the user touched then reverted | exactly the delta |
| Blind spot | **cannot see production changing underneath the user while they worked** — precisely what §18.2's `!` drift marker exists for | catches it by construction |
| Failure mode | silently overwrites a production hotfix made during the dev cycle | none of note |

**Recommended shape (still a recommendation, not a decision):** ship **(a)** for v1 — it is simple,
it needs no extra connection, and the `applied` table already drives it — **but pair it with a
mandatory pre-generate drift check**, which is cheap because the machinery exists:

- [ ] Before generating, run `fetch_routines_and_triggers(production_params)` off-thread (one
      read-only introspection call, no new code) and compare **only the objects in the applied set**
      against the sandbox's baseline-time definitions.
- [ ] Any object whose production definition changed since provisioning is reported as a `!` drift
      blocker, reusing §18.3's *"any `!`-flagged object blocks the batch"* all-or-nothing discipline,
      which itself reuses Diff/Merge's §12 ambiguity gate. Refuse the whole script, name every
      blocker, recovery = re-provision or re-apply, then re-run.

That combination gets (b)'s single real safety benefit at a fraction of (b)'s scope, and it leaves
(b) as a clean later upgrade: swap the content source, keep the gate. If the user prefers (b)
outright, `diff_schemas` is already written and the change is which two `DatabaseSchema` objects get
passed to it — genuinely a one-line difference at the call site. **That is why Tasks 8.1–8.3 are
written source-agnostic.**

- [ ] Whichever way it goes, the script header must state which model produced it.

### Task 8.5: menu + Save Migration As… flow

**Files:** modify `pgtp_editor/ui/main_window.py::_build_database_menu`;
test `tests/ui/test_deployment_sql_wiring.py` (new).

- [ ] Add **Generate Deployment SQL…** to the Database menu, in the §18.5 group after
      *Sandbox Setup…* / *Check DDL Object*. Disabled unless a sandbox profile is configured.
- [ ] §18.3's **Compare Schemas…** and **Save Migration As…** are **not** built here. Phase 8 builds
      the engine those two will call; building their UI is §18.3's job and its *"separate sibling
      command, no-project-required"* settled framing must not be pre-empted by a §18.5-shaped screen.
      Say so in the code comment so the next reader does not "finish" it wrongly.
- [ ] `_generate_deployment_sql()`: `busy_status` + `self._run_async` around (drift check →
      `diff_schemas` → `generate_migration`). Both introspection calls open connections and must be
      off the GUI thread.
- [ ] Guards, each with a specific message: no sandbox → open Sandbox Setup; empty applied set →
      *"nothing has been applied to the sandbox yet"*; drift blockers → the §12-style refusal naming
      every blocker; `UnsupportedDifference` → the table/column refusal.
- [ ] **Review before write.** Show the generated script in a **new read-only `DdlObjectPanel`-style
      preview tab** (reuse `CodeEditor(language="sql")` — the widget, highlighter and gutter already
      exist) with a **Save Migration As…** button. Do not write a file the user has not read. This is
      DDL destined for production.
- [ ] Save via
      `QFileDialog.getSaveFileName(self, "Save Migration As", f"migration_{ts}.sql", "SQL files (*.sql)")`,
      written UTF-8 with `newline=""`, mirroring `_save_xsd` / `_save_ddl_object` exactly. Patched in
      tests.
- [ ] The script is **never executed**. §18.3's hard non-goal — *"this never auto-executes DDL
      against a live database"* — is inherited verbatim, and v1 has no execute path at all, not even
      a disabled one.

Tests (patched `_run_async`, patched `getSaveFileName`, fake introspection seams): a canned applied
set + canned sandbox/production schemas → the preview tab shows the expected script; an object that
drifted in production → refusal naming it, no preview, no file; an empty applied set → status
message, no preview; Save writes the exact previewed bytes; a `table` difference → the unsupported
refusal; **no modal reached unpatched**.

**Done means:** a user who has edited three routines in the sandbox and checked them green gets one
reviewed `.sql` file that upgrades production to match — with an explicit refusal if production
moved underneath them, and an explicit statement of what the script does not cover.

---

## Phase 9 — Live-server confirmation (env-gated, not in the default suite)

### Task 9.1: `tests/db/test_sandbox_live.py`

**Files:** create `tests/db/test_sandbox_live.py`.

- [ ] Every test
      `@pytest.mark.skipif(not os.environ.get("PGTP_TEST_SANDBOX_DSN"), reason="needs a live PostgreSQL")`.
      The default `python -m pytest -q` run must remain green with psycopg absent entirely.
- [ ] Eight facts that **cannot** honestly be established with a fake and that the design leans on:
      1. `cursor.description is None` for `SET` / `CREATE FUNCTION` / `CREATE EXTENSION` (Task 1.1).
      2. `plpgsql.extra_warnings='all'` actually delivers notices through `add_notice_handler`, and
         the `CONTEXT` string matches the `near line N` regex (Tasks 1.3, 4.2).
      3. **The `prosrc` ↔ `pg_get_functiondef` line offset** (Task 4.2). This is the single
         highest-value live test; do not ship Phase 7 without it.
      4. `plpgsql_check_function_tb`'s 11-column order, the `anyelememttype` typo, and the trigger
         `relid` requirement (Task 4.4).
      5. The `xmin = pg_current_xact_id()` OID-recovery fallback (Task 4.4).
      6. `CREATE DATABASE` requires `autocommit=True`; `DROP SCHEMA … CASCADE` reset works with a
         live connection open (Task 3.4).
      7. **`CREATE OR REPLACE FUNCTION a()` whose plpgsql body calls a nonexistent `b()` succeeds** —
         the load-bearing claim behind Task 8.3's ordering decision.
      8. **The same is *not* true for a `LANGUAGE sql` function**, which should fail (Task 8.3).
- [ ] These run against a throwaway `pgtp_sandbox_test_*` database the test provisions and drops.

---

## Test strategy, summarized

| Layer | How it is tested | Needs Qt? | Needs a DB? |
|---|---|---|---|
| `db/config.py` profiles | injected `QSettings(ini)` (existing pattern) | QtCore only | no |
| `run_queries` | monkeypatched `psycopg.connect` → fake conn/cursor | no | no |
| `db/sandbox.py` | `runner=` fakes returning canned catalog rows; pure predicates (`is_app_owned`, `install_gate`, `build_baseline_sql`) tested directly | no | no |
| `db/ddl_check.py` | `runner=` fakes; golden-string assertions on generated SQL; canned `Notice`/`QueryFailure`/11-column rows | no | no |
| `db/schema_diff.py`, `db/migration_gen.py` | pure functions over canned `DatabaseSchema` — no runner at all, the easiest things here to test | no | no |
| `ui/ddl_object_panel.py` | pytest-qt, offscreen | yes | no |
| `ui/center_stage.py` dynamic tabs | pytest-qt; **the static-index invariant test** | yes | no |
| `ui/connection_setup_dialog.py` | injected `tester=`/`prober=`/`installer=` + sync `_run_async` | yes | no |
| MainWindow wiring | patched `_fetch_ddl_schema`, sync `_run_async`, patched `getSaveFileName`/`QMessageBox`/`_confirm_close_ddl_object` | yes | no |
| the eight facts above | `tests/db/test_sandbox_live.py`, env-gated | no | **yes** |

Seams that **must** be injectable: `runner=` on every new `db/` function; `prober=`/`installer=` on
the dialog; `resolve_save_path` on the panel; `_confirm_close_ddl_object`, `_save_ddl_object_as`,
`_fetch_ddl_schema`, `_open_sandbox_session` on MainWindow; `self._run_async` everywhere a
connection opens.

Modal discipline: `_context_menu_for` returns a `QMenu` rather than exec'ing it; the Sandbox Setup
dialog is `show()`n; `getSaveFileName` and `QMessageBox.critical`/`.question` are patched in every
test that can reach them. The 60 s `--timeout` is the net, not the plan.

---

## Risks and unknowns — read this part

**R1 — The spec is factually wrong that tier 2 needs no runner change.** §18.5 asserts
`run_queries` can be "used as-is" for writes. In psycopg 3, `cursor.fetchall()` after
`CREATE FUNCTION` raises `ProgrammingError: the last operation didn't produce a result`. Tier 2
fails on statement one without Task 1.1.

**R2 — Tier 1 produces no rows at all.** `plpgsql.extra_warnings` findings are asynchronous
`WARNING` messages. `run_queries` has no notice channel and discards them. Without Task 1.3, tier 1
is a table row in a design document and nothing else. Related, unresolved: `SET plpgsql.extra_errors`
with an invalid value errors *at SET time* once plpgsql is loaded, and plpgsql may not be loaded yet
in a fresh session — needs the live check in Task 9.1.

**R3 — Rollback was never the safety property.** The codebase comments and the spec text still say
"always ROLLBACKed"; they need updating alongside the implementation or the next reader will
re-derive the wrong model.

**R4 — Provisioning is not optional.** Without it, tier 2 reports
`relation "pr.equipment" does not exist` for essentially every real routine — a *false ERROR*, which
is strictly worse than "could not check" because it looks like a genuine finding. Phase 3 promotes
provisioning to core. **But the baseline is honestly incomplete**: no extensions, no sequences, no
constraints, no defaults, no data. `DatabaseSchema` also models no view definitions, so Task 3.3
adds a `pg_get_viewdef` query — without it every routine touching a view fails to compile. The
remaining gaps must be stated in the report's caveats, not buried.

**R5 — The ownership rule will collide head-on with the most likely user setup.** The realistic
sandbox is a local restore of production named `myapp_dev`. `open_sandbox` will refuse it, and the
refusal will read as the tool being broken. Task 6.2's "create one for me" offer is the mitigation
and is not optional. A future "adopt this database" flow (stamp the marker after an explicit, typed
confirmation) is worth designing, but it is not in this plan.

**R6 — Recovering the applied object's OID for tier 3 is specified nowhere.** `to_regprocedure`
needs a signature parsed out of the edited text, which is fragile the moment the user changes an
argument; the `xmin = pg_current_xact_id()` catalog trick avoids parsing but is unusual enough that
I would not ship it without Task 9.1 confirming it.

**R7 — Triggers are a second, quieter special case.** The tab holds `CREATE TRIGGER`, tier 3 checks
*functions*, `relid` is mandatory or plpgsql_check errors outright, and `CREATE OR REPLACE TRIGGER`
only exists on PG 14+. Easy to get 80% right and silently wrong on the rest.

**R8 — `CenterStage`'s fixed tab indices are load-bearing in five places.** Dynamic tabs are safe
only under strict append-only creation and tail-only removal. That invariant is currently implicit;
Task 5.2's regression test makes it explicit. It will break the first time someone calls `insertTab`.

**R9 — `db/config.py` is not Qt-free**, despite the spec's dependency-rule sentence listing `db/*`
as Qt-free — it imports `QSettings` at module scope. Pre-existing, not introduced here, but Phase 2
makes it more prominent. Do not "fix" it by inventing a second store; just note the discrepancy to
the spec-maintainer.

**R10 — Two profiles means two plaintext passwords in QSettings.** The existing caveat label must
appear for the sandbox profile too. Worth a moment's thought about whether a sandbox *superuser*
password sitting in plaintext (needed for the one-click `CREATE EXTENSION`) is a trade the user has
actually agreed to.

**R11 — `Runner`'s type alias is too narrow** once the keyword-only params exist. Widening it is
trivial; the trap is a fake runner in a new test that omits `**kwargs` and fails opaquely.

**R12 — §18.4's formatter does not exist yet.** This tab is its designated first consumer. Phase 5
leaves a named hook and does not block on it.

**R13 — `CREATE OR REPLACE FUNCTION` is not as idempotent as the framing assumes.** It fails
outright with *"cannot change return type of existing function"* and *"cannot change name of input
parameter"*. A user who renames a parameter or widens a return type in the sandbox gets a deployment
script that **errors on production halfway through**. Fixing it properly requires `DROP FUNCTION` +
`CREATE`, which cascades into trigger recreation and is exactly the guarded-DROP territory v1 is
trying to avoid. Mitigation for v1: detect the mismatch during Task 8.4's drift check (we introspect
production anyway, so both signatures are in hand) and **refuse with a named blocker** —
*"pr.calc_total: return type changed; a deployment script cannot replace this in place"* — rather
than emitting a script that fails at run time. So "no ALTER logic, no drop guards" holds only
because the hard cases are refused, not because they do not exist.

**R14 — A changed argument type silently creates an overload instead of replacing.** PostgreSQL
identifies functions by `(schema, name, argtypes)`. If the user changes `calc_total(integer)` to
`calc_total(bigint)` in the sandbox, `CREATE OR REPLACE` on production **creates a second function**
and leaves the old one live — and every existing caller keeps hitting the old one. That is a silent
wrong result in production, the worst possible place for one. This is why Task 8.1 keys routine
identity on the full signature and forces the change to surface as `removed` + `added`; the
generator must then refuse (or require explicit consent for the guarded DROP) rather than emit a
bare `CREATE OR REPLACE`. **Do not let identity degrade to `schema.name` anywhere in the pipeline.**

**R15 — Wrapping the deployment script in a transaction is a decision nobody has made.** PostgreSQL
has transactional DDL, so `BEGIN; … COMMIT;` around the whole script makes deployment atomic — a
very strong property for exactly this use case. But it changes how the user's own deploy tooling
must invoke it. Recommend emitting the `BEGIN`/`COMMIT` pair **commented out** in the header with a
one-line explanation, so the user chooses. Flag it; do not decide.

**R16 — `pg_get_functiondef` text is not stable across server majors.** The sandbox and production
are frequently different majors. Purely cosmetic rendering differences will surface as phantom
`changed` differences, producing a deployment script full of no-op replacements. Harmless (they are
idempotent) but noisy and erodes trust in the diff. Mitigation: report both server versions in the
header and, if they differ, say so prominently. A normalizing comparison is a rabbit hole — do not
start it in v1.

**R17 — The baseline's honest incompleteness (R4) now propagates into the deliverable.** A routine
that is *valid in the sandbox* may be invalid in production — for example one that relies on a
`DEFAULT nextval(...)` or a constraint the baseline omitted. The deployment script is generated from
a desired state that is a **structural approximation** of production, not a copy. The script header
must say which baseline model produced the sandbox.

**R18 — Two new modules land with their table/column halves deliberately hollow.** That is the right
call, but it creates a trap: the next contributor sees `db/migration_gen.py` and reasonably assumes
it generates migrations. It generates *routine and trigger* migrations. The module docstrings must
open with that limitation in the first sentence, and `UnsupportedDifference` must exist as a real,
raised exception rather than a silent skip.

---

## Open questions for the spec (not to be improvised in code)

- **Task 8.4's fork** — working set vs. true diff against production.
- **R15** — transaction-wrap the deployment script, or leave it to the user?
- **R13/R14's refusal policy** — refuse a signature change outright, or offer a consented guarded
  `DROP`?
- **Execution against the sandbox** — running a function and seeing its result is not in this plan.
  It is the difference between a validator and an IDE, and the sandbox makes it safe in a way
  DBeaver cannot. Scope it as a follow-on feature or fold it into v1 — undecided.
- **`db/routine_refs.py`** (§18.1's one unbuilt piece) — XML↔routine cross-referencing. Answers
  *"which pgtp pages break if I change this function?"* before the deployment script is generated.
  No other tool can do this. Not in this plan; strong candidate for the next one.

---

## Self-review

- **Spec coverage:** D1 (single-object editable tab, injected load/save, §18.2-ready naming) →
  Phase 5. D2 (BYO local PostgreSQL, `PostgresBackend`, `SandboxCapabilities`, ownership,
  `autocommit`) → Phases 1 and 3. D3 (four tiers, per-tier outcomes, never-silently-clean, tier 0
  collapses into tier 2, no `pglast`) → Phase 4. `[Check]` prefix and Audit routing → Phase 7. Menu
  home, no new top-level menu, no locate-binary → Phase 6. Deployment SQL → Phase 8.
- **§18.3 reused, not duplicated:** exact `SchemaDifference` field names, exact `diff_schemas` and
  `generate_migration` signatures, exact CREATE→ALTER→guarded-DROP ordering, and its Compare-Schemas
  UI explicitly left unbuilt.
- **Invariants held:** `run_queries` sole psycopg call site; `db/` Qt-free (Phases 1–4 and 8 add no
  PySide6 import; `config.py`'s pre-existing `QSettings` noted as R9); off-GUI-thread + busy;
  `debuglog.redacted` (no new params type — `ConnectionParams` is reused for both profiles, so the
  locked redaction test still covers everything); loaders never raise; `.pgtp` never written; tests
  mirror the layout.
- **No live DB and no unpatched modal in the default suite**; the eight facts that genuinely need a
  server are isolated and env-gated.
- **Each phase ships alone:** 1 and 2 are invisible infrastructure; 5 ships a working editor +
  Save As with no sandbox; 6 ships setup and provisioning with no checking; 7 turns the ladder on;
  8 produces the deliverable.
