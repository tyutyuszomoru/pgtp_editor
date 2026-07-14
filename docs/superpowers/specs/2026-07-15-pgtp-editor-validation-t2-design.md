# Validation Tier 2 (structural sanity) — Design

**Date:** 2026-07-15

Implements the Tier-2 structural-sanity portion of §6.7 of the master design, wired to the existing **Tools → Validate Project** stub, reporting into the Audit panel.

## Goal
Run a set of structural sanity checks over the open project and report each finding in the Audit panel, click-to-navigable to the offending line. One hard-error rule (duplicate `Page@fileName`) plus warnings; deliberately low-false-positive.

## Scope

**In scope — three checks:**
1. **Duplicate `Page@fileName` (ERROR)** — the one hard rule. Among top-level `<Page>` elements (direct children of `<Pages>`), every `<Page>` with a non-empty `fileName` must be unique. Each such top-level `<Page>` sharing a duplicated `fileName` is reported (so the user sees all colliding locations), one ERROR per colliding page. Nested `<Detail>` pages legitimately reuse their master page's `fileName` and are excluded.
2. **Missing required attributes (WARNING):**
   - A `<Page>` that is a direct child of `<Pages>` (a top-level page) missing `fileName` or `tableName`.
   - A `<ColumnPresentation>` missing `fieldName`.
3. **Unexpected child of a known container (WARNING):** a non-comment element child that violates a high-confidence containment rule — `<Pages>` may only contain `<Page>`; `<Details>` may only contain `<Detail>`; `<ColumnPresentations>` may only contain `<ColumnPresentation>`. (Only these three containers are checked — they're unambiguous; a broader whitelist is deliberately deferred to avoid false positives.)

**Out of scope:** deep referential integrity (Lookup/FieldMap targets), a full parent→child whitelist for every element, Tier-1 well-formedness (already handled at open/reparse), live-at-edit-time checking (this is an on-demand "Validate Project" run).

## Core — `pgtp_editor/validation/tier2.py` (new, Qt-free, unit-tested)
- `@dataclass(frozen=True) ValidationIssue`: `severity: str` (`"error"` | `"warning"`), `message: str`, `line: int | None` (the offending element's `sourceline`, for navigation).
- `validate_project(project) -> list[ValidationIssue]`: operates on `project.tree.getroot()` (lxml). Returns issues in document order (by line, then a stable order per line). Empty list = clean. If `project` or its tree is None → `[]`.
  - Duplicate fileName: collect `(fileName, element)` for every top-level `<Page>` (parent tag `Pages`) with non-empty `fileName`; for any fileName with >1 element, emit an ERROR per element: `duplicate Page fileName "X"`. Nested `<Detail>` pages are skipped.
  - Missing attrs: iterate; for a `<Page>` whose parent tag is `Pages`, warn on absent/empty `fileName` (`Page missing fileName`) and absent/empty `tableName` (`Page missing tableName`); for every `<ColumnPresentation>`, warn on absent/empty `fieldName` (`ColumnPresentation missing fieldName`).
  - Unexpected children: for each `<Pages>`/`<Details>`/`<ColumnPresentations>` element, any element child (skip comments/PIs) whose tag != the allowed child → warning `unexpected <TAG> inside <CONTAINER>`.
- New package: `pgtp_editor/validation/__init__.py`.

## UI wiring — `pgtp_editor/ui/main_window.py`
- Module constant `_VALIDATION_PREFIX = "[Validate] "`.
- Replace the `_add_stub_action(menu, "Validate Project")` in `_build_tools_menu` with a real action → `self._validate_project`.
- `_validate_project()`:
  - If `self._current_project is None` → `statusBar().showMessage("Open a project to validate.", 5000)` and return.
  - `_clear_validation_results()` (remove prior `[Validate] `-prefixed audit items, bottom-up, like `_clear_find_results`).
  - `issues = validate_project(self._current_project)`.
  - For each issue, add a `QListWidgetItem` `f"{_VALIDATION_PREFIX}{severity.upper()} line {line}: {message}"` (omit `line {line}` when line is None) with the line on `Qt.ItemDataRole.UserRole` (→ existing `_on_audit_item_clicked` navigates to it).
  - Status summary: `f"Validation: {n_err} error(s), {n_warn} warning(s)"`, or `"Validation passed — no issues."` when empty.
- `_clear_validation_results()` mirrors `_clear_find_results` with the validation prefix.
- Existing `_on_audit_item_clicked` already navigates on any `UserRole` line — no change needed.

## Testing
- **`tests/validation/test_tier2.py` (Qt-free, via `load_project_from_text`):** duplicate fileName → one ERROR per colliding Page with correct lines; unique fileNames → none; top-level Page missing fileName/tableName → warnings; nested detail Page without fileName → NOT warned (only top-level Pages under `<Pages>`); ColumnPresentation missing fieldName → warning; unexpected child in each of the three containers → warning; comments inside a container → ignored; a clean small project → `[]`; `project`/tree None → `[]`. Include a real-sample test (skips if `sample/*.pgtp` absent) asserting the known-good `dev_Ferrara.pgtp` produces no ERRORs (warnings allowed/asserted loosely).
- **`tests/ui/test_main_window.py` (pytest-qt):** Validate with no project → info status, empty audit; with a duplicate-fileName project → audit shows `[Validate] ERROR …` items + a status summary with the error count; `_clear_validation_results` removes only `[Validate]` items (leaves e.g. a seeded `[Schema]` entry); clicking a validation item navigates (switches to Raw XML tab + `navigate_to_line`, asserted via cursor block). No modal.
- **`tests/ui/test_menus.py`:** `test_tools_menu_contents` unchanged (label "Validate Project" is the same; only wiring changed). Add a test that triggering the action on an open project populates the audit panel.
- Full suite green, no timeout.
