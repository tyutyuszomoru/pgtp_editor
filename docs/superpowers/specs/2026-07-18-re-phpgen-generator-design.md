# Reverse-Engineering the PHP Generator (`re_phpgen`) — Design

**Date:** 2026-07-18

A new, standalone sub-project: reverse-engineer SQL Maestro's PostgreSQL PHP Generator so we can build our **own** generator that turns a `.pgtp` project into the per-page `.php` files the vendor tool produces. This is separate from the `pgtp_editor` (which only ever edits the `.pgtp` XML source and shells out to the vendor tool). Here we reconstruct the `.pgtp` → `.php` transformation itself.

## 1. Goal and phased roadmap

**Ultimate goal:** own the generator so we can eventually modify the generated framework/runtime as well. Today our hands are tied because the contract between generated page code and the vendor runtime is opaque. Owning the generator unties them.

- **Phase 1 — Parity generator (this spec).** Build a generator that emits per-page `.php` that is byte-parity with the vendor's output and runs against the **vendor's existing runtime** (`components/`, `database_engine/`). We do **not** touch the runtime. Deliverable: the generator + a documented runtime-contract map.
- **Phase 2 — Runtime ownership (future).** Using the contract map harvested in Phase 1, begin replacing/modifying runtime framework pieces, re-validating behavior against the vendor runtime as reference. Out of scope for this spec.

The Phase-1 parity milestone is the deliberate wedge into Phase 2: a generator that reproduces the per-page code exactly is, as a byproduct, a complete catalog of what that code demands of the runtime.

## 2. Fidelity target

**Reuse the vendor runtime; match the per-page files.** The generator's job is narrow: parse `.pgtp` → emit the per-page `.php` that instantiates vendor runtime classes, closely enough (byte-identical after normalization) to drop into the runtime the vendor already ships and run identically. The `components/` and `database_engine/` directories are treated as an opaque, reused dependency — never regenerated.

## 3. The oracle and the corpus

The vendor CLI works on this machine (confirmed), making it a **test oracle**: for any `.pgtp` we can produce ground-truth PHP on demand.

```
PgPHPGeneratorPro.exe "<project.pgtp>" -output "<output-folder>" -generate
```

**Corpus:** 37 real production projects (`re_phpgen/input/01.pgtp` … `37.pgtp`), each generated into a sibling folder (`input/01/` …). A generated project = one `components/` runtime dir + ~40 top-level page `.php` files (one per `Page`). Across 37 projects this yields hundreds–low-thousands of matched **(page XML subtree → page `.php`)** pairs — both the study material and the regression suite.

**Hard rule — regenerate, never trust stale pairs.** A `.php` sitting next to a `.pgtp` of unknown vintage is not a valid pair (confirmed: the on-disk `development_equipment.php` sample was 1.31 MB and a different version than the same page freshly generated at 1.04 MB, with at least one caption differing). Only pairs produced by regenerating from the exact `.pgtp` are ground truth.

## 4. Key empirical findings (validated on real data)

**Output is a fixed skeleton + self-labeling per-field blocks.** Each `Page`/`Detail` compiles to a PHP class (`<ancestry_chain>Page extends DetailPage` / `... extends Page`) with the same ~40 methods in the same order every time. Column-context methods (`AddFieldColumns`, `AddEditColumns`, `AddInsertColumns`, `AddMultiEditColumns`, `AddPrintColumns`, `AddExportColumns`, `AddCompareColumns`, `AddSingleRecordViewColumns`, …) each emit one block per field, preceded by a `// <Context> column for <field> field` comment banner. These banners are exact anchors mapping each block to `(context, fieldName)`.

**Almost every PHP token maps 1:1 to an XML attribute.** Example (`foreign_id`, Edit context):

| PHP emitted | Source in XML |
|---|---|
| `new DynamicCombobox('foreign_id_edit', …)` | `<EditProperties type="dynamicCombobox">` |
| `$editor->setAllowClear(true)` | `canSetNull="true"` |
| `new TableDataset(…, '"public"."equip_parts"')` | `<Lookup tableName="public.equip_parts">` |
| `setOrderByField('tag', 'ASC')` | `displayFieldName="tag" useLookupOrdering="true"` |
| `SetReadOnly(true)` / `setVisible(false)` | `readOnly="true"` / `controlVisible="false"` |

**Three token sources.** The generator is a function of more than the page subtree:
1. **Page subtree attributes** — the 1:1 majority.
2. **`DataSources` schema** — e.g. `$lookupDataset->addFields(new StringField('jobcard_id'), …)` is the lookup table's column schema, from the project's `DataSources/DataSource`, not the page.
3. **Derived / generator-internal** — class names and handler names built from the ancestry chain + fieldName; sequential aliases (`'LA1'`, `'LA2'`) auto-numbered per page (counter state we must replicate).

## 5. Method — corpus-first, probe-to-fill

1. **Mine the corpus.** Align each generated `.php` back to its source subtree (anchored by `fileName`/`fieldName`/`tableName`), segment into regions/blocks via the comment banners, and extract what varies with what. Frequency-rank every construct so the common 80% is built first.
2. **Differential probing fills gaps only.** When the corpus can't disambiguate a rule (canonical case: the `AbilityMode` numeric-code enums), mutate one XML attribute, regenerate via the oracle, diff. Targeted, not the bulk method.

## 6. Beachhead — the invariant skeleton first (top-level `Page` variant)

Before reversing any per-field content, reverse the fixed scaffold every page shares. It can be validated to byte-parity independently of the field emitters, making it a clean self-contained first slice.

**Four layers (found by masking the per-field blocks and cross-diffing skeletons across the corpus):**
1. **Globally-constant literals** — byte-identical in every page everywhere (`ATTENTION` banner, runtime `include_once` lines, method signatures, empty unused-hook bodies). Hard-coded template text.
2. **Per-project-constant blocks** — same within a project, differ across (`GetConnectionOptions()` encoding, output path like `/projects/sd2185/`, userspice/lang header). Driven by project-level settings + global event handlers.
3. **Verbatim-copied event-handler code** — `OnGlobalBeforePageExecute` / `OnBeforePageExecute` bodies are the inline PHP text from XML `EventHandlers`, unescaped and pasted in. Global (project) and page-level slots.
4. **Derived identifiers** — class name, base class, handler names, computed from ancestry chain + page type.

**Reverse method:** a Python **skeleton extractor** replaces each per-field block and each handler body with a placeholder token; run it across all corpus pages; cross-diff to sort content into the four layers; rebuild as a parameterized template (literal body + enumerated slots).

**Definition of done for the beachhead:** generate the skeleton for a real top-level `Page`, mask the field-block holes on **both** sides (ours and the vendor's), diff → byte-identical. Proven without any cell emitter existing yet.

**Page-type variants** (`DetailPage`, modal/view-based) share most of the skeleton and are follow-on slices using the same extractor. Start with the top-level separated `Page`.

## 7. Generator architecture (Python)

Pipeline: **parse `.pgtp` → intermediate model → emit per-page PHP.**
- **Parse/model:** evaluate reusing the `pgtp_editor` model layer (`2026-07-11-pgtp-editor-model-design.md`) rather than re-parsing, keeping one source of truth for the XML shape. Must also expose `DataSources` schema (needed for lookup `addFields`).
- **Emit:** template + procedural hybrid — templates (e.g. Jinja2) for the stable skeleton and per-region scaffolding; procedural code for repeated/looped constructs (columns replicated across contexts, arbitrarily-nested `Detail` pages). Organized by region and page type so each maps to an independently testable emitter.

## 8. Runtime contract map (Phase-2 wedge, harvested in Phase 1)

As each region is reversed, catalog every runtime class/function the emitted code touches — constructor signatures, call sites, the `page_includes.php` surface — into a living document. Deliberate output, not a side effect: this is the artifact that enables Phase 2.

## 9. Validation and coverage

- **Oracle-as-test:** each finished slice is done when its normalized output is byte-identical to freshly-regenerated vendor output for the target pages.
- **Normalizer:** first experiment before any generator code — generate one project twice, diff, and fold any non-determinism (timestamps, paths, ordering) into a `normalize(php)` both sides pass through.
- **Coverage metric:** % of corpus pages reproduced at parity, plus per-region parity — turns progress into a number and catches regressions when new features are added.

## 10. Scope boundaries / non-goals

- No regeneration or modification of the vendor runtime (`components/`, `database_engine/`) in Phase 1.
- No new runtime framework (that is Phase 2, separate spec).
- No changes to the `pgtp_editor` behavior; this project only *consumes* its model layer, read-only.
- Not building GUI tooling here — a CLI generator + analysis scripts.

## 11. Open questions / risks

- **Caption localization at generate time** — is the XML caption emitted verbatim, or translated via `Project@localizationFileName`? (The stale-pair `Sub-item`→`Sous-article` mismatch is unresolved; re-check against a fresh pair.) Resolve by corpus/oracle.
- **Counter/alias numbering** (`LA1`, handler suffixes) — exact scheme and reset boundaries must be derived, not guessed.
- **DataSource schema origin** — whether lookup `addFields` come from `DataSources` in the `.pgtp` or from live DB metadata cached at generate time. If the latter, the generator needs the same DB access or a cached schema snapshot.
- **Determinism** — assumed but unverified until the twice-generate diff (step 9) runs.

## 12. Where it lives

New standalone project rooted at `re_phpgen/` (already holds the corpus under `input/`). Design docs tracked with the rest of this repo's specs. Shares the `pgtp_editor` model layer read-only. Its own spec → plan → implementation cycle.
