# Test Log

Committed, append-only record of verified test runs. The `feature-tester` agent
(`.claude/agents/feature-tester.md`) appends one entry here every time a feature
is completed, after personally observing the run. Newest entries go at the **top**
of the table. Entries are never rewritten or deleted — red runs are recorded too.

Result format: `PASS — <passed> passed, <skipped> skipped` or
`FAIL — <failed> failed (<test names>)`.

| Date | Feature | Test files added/extended | Targeted result | Full suite result | Commit |
|------|---------|---------------------------|-----------------|-------------------|--------|
| 2026-07-20 | Ctrl+click (matching tag) / Alt+click (parent tag) caret navigation in Raw XML editor | tests/ui/test_xml_structure.py (extended, +6 pure tests: deep 4-level nesting resolves innermost partner & own open, grandchild Alt-target is immediate parent not root, mid-level open-tag parent, attribute-region resolves to close, repeated-sibling correct instance); tests/ui/test_xml_editor_click_nav.py (extended, +6 widget tests: Ctrl+click self-closing no-op, Ctrl+Shift+click & Ctrl+Alt+click fall-through, jump uses updated offsets after edit, jump to correct offset with an inner fold collapsed, Alt+click top-level no-op) | PASS — 55 passed (test_xml_structure.py + test_xml_editor_click_nav.py) | PASS — 1355 passed, 32 skipped (32s) | e4e1884 (feature committed; new tests uncommitted) |
| 2026-07-19 | Cached document-text reuse in matching-tag highlight (nav-lag perf fix, follow-up: per-keystroke toPlainText() full-document copy removed) | tests/ui/test_xml_editor_nav_perf.py (extended, 2→3 tests: +toPlainText()-call-counting regression test proving cursor navigation no longer copies the document text) | PASS — 142 passed (test_xml_editor_nav_perf.py + test_xml_editor.py + test_xml_structure.py + test_xml_editor_completion.py) | PASS — 1326 passed, 32 skipped (43s) | (this commit) |
| 2026-07-19 | Cached tag-span reuse for matching-tag highlight (nav-lag perf fix) | tests/ui/test_xml_editor_nav_perf.py (new, 2 tests: enclosing_tag_span/enclosing_tag_span_from_spans equivalence, and a scan()-call-counting regression test proving cursor navigation no longer rescans); tests/ui/test_xml_editor.py and tests/ui/test_xml_structure.py (unchanged, re-verified) | PASS — 114 passed (tests/ui/test_xml_editor_nav_perf.py + test_xml_editor.py + test_xml_structure.py) | PASS — 1325 passed, 32 skipped (43s) | 5a6d8c7 |
| 2026-07-19 | Debug mode (--debug diagnostic logging) | tests/test_debuglog.py (26→33), tests/test_main.py (4→8), tests/ui/test_main_window_debug.py (6→7), tests/generation/test_runner.py (+1 seam test), tests/db/test_introspect.py (redaction, pre-existing) | PASS — 62 passed (targeted files) | PASS — 1315 passed, 32 skipped (30s) | e5a2e34 |
| 2026-07-19 | Ctrl+Space attribute autocomplete with value chaining (re-run after mouse-click-chooses fix in _CompletionPopup) | same as prior entry (tests/ui/test_xml_editor_completion.py 27 tests; tests/schema_learning/test_settings_index.py 33 tests) | PASS — 60 passed, 0 skipped | PASS — 1307 passed, 0 skipped (99s) | ed3c7a0 |
| 2026-07-19 | Ctrl+Space attribute autocomplete with value chaining | tests/ui/test_xml_editor_completion.py (extended, 20→27 tests); tests/schema_learning/test_settings_index.py (extended, +1 test) | FAIL — 1 failed (test_popup_mouse_click_chooses_row; 59 passed) | FAIL — 1 failed (tests/ui/test_xml_editor_completion.py::test_popup_mouse_click_chooses_row), 1306 passed (124s) | 206e01a |
| 2026-07-19 | (baseline — log established) | none (existing suite, 88 test files) | n/a | PASS — 1271 passed, 0 failed (128s) | 9399050 |

