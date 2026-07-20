# re_phpgen: Template Variant Generalization + Master-Detail Emission — Design

**Date:** 2026-07-19

Second parity slice for the `re_phpgen` generator (repo `C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen`), building on the skeleton beachhead (`2026-07-18-re-phpgen-generator-design.md`) and driven by the gap-JSON workflow (`2026-07-19-pgtp-editor-pangen-gap-analysis-design.md`). Scope was set empirically by the master-detail deep-dive (`docs/findings/master_detail_analysis.md` in the re_phpgen repo, commit `a4c76da`) and confirmed on the user's own project-09 comparison (`tests/_origen` vs `tests/_pangen`: 0/99 pages ok; the simplest plain page diffs on exactly two hunks — the global-handler block and one `GetEnable*` flag line).

## 1. Purpose

Two bundled capabilities that share the same template surgery:

1. **Template variant generalization** — replace the beachhead's fixed-variant template content with derived slots: the project **global-handler block**, the per-page **`GetEnable*` feature-flag set**, and per-page skeleton **parameters** (`SetRowsPerPage(N)`-class values). These are the shared bottleneck: 363/432 pure master-detail pages carry a global handler and 119 a non-fixed flag combo, and 47/99 project-09 pages fail on *only* these.
2. **Master-detail emission** — multi-class page files: recursively emitted `DetailPage` classes + the master `Page` class, per the deep-dive's verified rules.

Measured stakes: master-detail alone would unlock ~5 pages; bundled, the pure-master-detail ceiling is **397/432 (~92%)**, plus every plain page currently failing only on handler/flags/parameters (project 09 alone: ~47 plain + ~40 master-detail pages come into reach; charts and partitions stay out of scope).

## 2. Scope

**In scope (all in the re_phpgen repo):**
- Template decomposition: one **file frame** (header with global-handler slot … footer) + one **class template** used for both master and detail classes (justified in §4).
- Derived slots: `EXTENDS` (`Page`/`DetailPage`), `GetEnable*` flag block, global-handler block, `CreateMasterDetailRecordGrid` block (present/absent), page parameters (`SetRowsPerPage` etc. as identified when the diff data demands them).
- Detail-tree walker in `catalog.py` (recursive `Details/Detail/Page`, arbitrary depth) including the **FK-validity emission filter** (§5.3).
- Detail class naming with file-global post-order ordinals; multi-class assembly in emission order.
- `pangen.emit_project` unchanged in contract (still best-effort per page; a page now emits a multi-class file).
- Parity gates on real project-09 pages + regression gates on the project-03 beachhead pages; corpus coverage re-measured.

**Out of scope (documented follow-up slices):**
- `ViewBasedPage`/`NestedFormPage`/`ModalViewPage` classes (the 91 mixed master-detail pages stay `diff`; only 4 corpus pages are view-based-only).
- Charts, partitions (own cause buckets; small counts).
- Unmasking any hole (handler content, `DoBeforeCreate`, column emitters) — comparison stays `masked-skeleton-v1`.
- The deep-dive's 8 unresolved edge pages (master-stem ordinal ×6, FK-valid-junction drop ×1, deep self-referential collision ×1) — excluded from gates, listed in findings with their disambiguation experiments.

## 3. Verified derivation rules (from the deep-dive; bake in as implemented behavior)

1. **Emission predicate per Detail:** a `Details/Detail/Page` emits a DetailPage class **iff its FK is valid** — every `FieldMap@foreginColumnName` (vendor's spelling) in the Detail's `MasterForeignKeyColumnMap` names a field that exists in the detail page's own field set. Invalid FK ⇒ the whole detail subtree is dropped (page may degrade to a plain page). Explains 47 "master-detail in XML, plain in PHP" corpus pages.
2. **Class order in the file:** depth-first **post-order** over emitting details — children before their parent detail, siblings in document order — master `Page` class **last**. (100% of 432 pure pages.)
3. **Detail class naming:** `"_".join(sanitize_table_name(t) for t in ancestry_chain) + "Page"`, chain rooted at the master's stem. Duplicate full stems get 2-digit ordinals assigned in **emission (post-order) order, tracked file-globally**. First ctor argument = class name minus `"Page"`. (Reproduces 471/479 detail lists; the 8 misses are the parked edge pages.)
4. **DetailPage skeleton = master skeleton − `CreateMasterDetailRecordGrid` + `extends DetailPage`.** Same method inventory; constructor and `GetForeignKeyFields` are inherited, never emitted. (898 detail classes analyzed; dominant skeleton covers 475; the variance is the same flag/handler/parameter variance being parameterized in this slice.)
5. **`CreateMasterDetailRecordGrid`** is carried by exactly the classes that have emitting child details (masters and intermediate details; never leaves). All wiring (`$detailPage = new …`) lives in `doRegisterHandlers` — already a masked hole. The only master-detail content visible to the masked comparison is: class declarations, and the `CreateMasterDetailRecordGrid()` declaration + hole braces.
6. **Global-handler block:** emitted into every page of a project that defines the corresponding project-level handler (e.g. `OnGlobalBeforePageExecute`) as a `// On<Name> event handler` comment + the pasted code (masked to `@@HANDLER@@` at comparison time). Slot value derives from the project-level `EventHandlers` children: for each defined global handler, emit its marker comment + code; empty slot otherwise.
7. **`GetEnable*` flags:** one-liner methods present per page as a function of the page's ability-mode attributes (`viewAbilityMode`, `editAbilityMode`, `insertAbilityMode`, `copyAbilityMode`, …). **The exact attribute→flag mapping is derived by corpus correlation** — the corpus provides 1000+ (page XML attributes, emitted flag set) pairs; the implementation fits the mapping from data and validates it against every corpus page. If correlation leaves residual ambiguity, the fallback is a manual GUI differential probe (change one dropdown, save, re-generate manually, diff) — flagged to the user rather than guessed.
8. **Page parameters:** values like `SetRowsPerPage(N)` map 1:1 from page attributes (e.g. `recordsPerPage`); each parameter added only when the gap data shows it varying (54 corpus pages differ on `SetRowsPerPage` alone). Same corpus-correlation validation as flags.

## 4. Architecture

**Single class template, two frame slots — not separate master/detail templates.** Deep-dive rule 4 makes master vs detail a two-slot difference (`EXTENDS`, `CMDRG` block), so one `templates/page_class.php.tmpl` serves both, eliminating an entire template to keep in sync. The existing dumb slot engine (`@@SLOT:NAME@@` replace) stays; **all conditionality lives in Python slot-computation** (a slot's value is a complete text block or empty), never in the template language.

```
templates/
├── file_frame.php.tmpl      # header (incl. @@SLOT:GLOBAL_HANDLERS@@) + @@SLOT:CLASSES@@ + footer
└── page_class.php.tmpl      # one class: @@SLOT:CLASS_NAME@@ / @@SLOT:EXTENDS@@ / @@SLOT:CMDRG@@ / @@SLOT:FLAGS@@ / …

src/re_phpgen/
├── catalog.py    # + detail_tree(pgtp, page) -> DetailNode tree (ancestry, FK-validity, doc order)
├── skeleton.py   # + emission-order class naming (post-order, file-global ordinals);
│                 #   emit_page_file(pgtp, page) -> str assembles frame + N classes
│                 #   slot computation: flags, global handlers, CMDRG, parameters
└── pangen.py     # unchanged contract; calls emit_page_file
```

Both templates are re-derived from real vendor output with the existing extractor method (mask, cross-diff), not hand-written. The current `page_skeleton.php.tmpl` is retired once the gates pass.

**Data flow:** `.pgtp` → catalog (top-level page + detail tree, FK-filtered) → per-file class list in post-order + names/ordinals → per-class slot computation → class template fills → frame fill → file text. Best-effort error handling unchanged: a page whose emission raises is skipped with a stderr note; a *detail* whose data is malformed drops per rule 1 semantics (matching the vendor) rather than erroring.

## 5. Validation

- **Regression gate:** the existing project-03 parity tests must stay green untouched (the generalized templates must reproduce the beachhead pages).
- **New parity gates (real vendor files, masked comparison):** (a) a plain project-09 page (proves global-handler + flags slots), (b) a single-detail master-detail page, (c) a page with ≥3 details including one nested ≥2 deep (proves ordering + naming + recursive assembly), (d) a page with an FK-invalid detail that must emit as a plain page (proves rule 1).
- **Rule-validation tests (corpus-wide, data-driven):** class-name/order model reproduces the detail list for ≥471/479 corpus master-detail pages (the 8 parked pages excluded and asserted as the *only* exclusions — regression on the deep-dive's result); flag mapping reproduces every corpus page's flag set.
- **Coverage checkpoints (measured, not DoD):** re-run `skeleton_coverage.py` and the project-09 gap JSON; expect project 09 to move from 0/99 to the ~85/99 region (charts/partitions remain) and corpus coverage from <1% to a number in the hundreds of pages. Record both in the findings doc; the DoD is the gates above plus strictly-improved coverage with zero regressions.

## 6. Risks / open items

- **Flag-mapping ambiguity** (rule 7 fallback): if two ability-code values never co-occur with distinguishing output in the corpus, the mapping stays partially unconfirmed; handled by flagging affected pages in the findings doc and, if the user opts in, one manual GUI probe session.
- The 8 parked edge pages cap corpus master-detail reproduction at 471/479 until their follow-ups run.
- Template re-derivation must preserve the beachhead's byte-level fidelity — the regression gate exists precisely because this is the riskiest step.
- `gap.py` cause buckets: pages fixed by this slice leave the `master-detail` bucket; the bucket itself stays (view-based/mixed pages still report it) — no gap-JSON schema change.

## 7. Where it lives

Implementation entirely in the re_phpgen repo (own commits on `master`). Spec/plan tracked here in pgtp_editor docs per house convention. The editor integration needs no changes — panGen/rePHPgen pick up the improved generator through the subprocess boundary automatically.
