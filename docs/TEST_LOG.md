# Test Log

Committed, append-only record of verified test runs. The `feature-tester` agent
(`.claude/agents/feature-tester.md`) appends one entry here every time a feature
is completed, after personally observing the run. Newest entries go at the **top**
of the table. Entries are never rewritten or deleted — red runs are recorded too.

Result format: `PASS — <passed> passed, <skipped> skipped` or
`FAIL — <failed> failed (<test names>)`.

| Date | Feature | Test files added/extended | Targeted result | Full suite result | Commit |
|------|---------|---------------------------|-----------------|-------------------|--------|
| 2026-07-19 | Debug mode (--debug diagnostic logging) | tests/test_debuglog.py (26→33), tests/test_main.py (4→8), tests/ui/test_main_window_debug.py (6→7), tests/generation/test_runner.py (+1 seam test), tests/db/test_introspect.py (redaction, pre-existing) | PASS — 62 passed (targeted files) | PASS — 1315 passed, 32 skipped (30s) | e5a2e34 |
| 2026-07-19 | Ctrl+Space attribute autocomplete with value chaining (re-run after mouse-click-chooses fix in _CompletionPopup) | same as prior entry (tests/ui/test_xml_editor_completion.py 27 tests; tests/schema_learning/test_settings_index.py 33 tests) | PASS — 60 passed, 0 skipped | PASS — 1307 passed, 0 skipped (99s) | ed3c7a0 |
| 2026-07-19 | Ctrl+Space attribute autocomplete with value chaining | tests/ui/test_xml_editor_completion.py (extended, 20→27 tests); tests/schema_learning/test_settings_index.py (extended, +1 test) | FAIL — 1 failed (test_popup_mouse_click_chooses_row; 59 passed) | FAIL — 1 failed (tests/ui/test_xml_editor_completion.py::test_popup_mouse_click_chooses_row), 1306 passed (124s) | 206e01a |
| 2026-07-19 | (baseline — log established) | none (existing suite, 88 test files) | n/a | PASS — 1271 passed, 0 failed (128s) | 9399050 |

