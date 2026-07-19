# Test Log

Committed, append-only record of verified test runs. The `feature-tester` agent
(`.claude/agents/feature-tester.md`) appends one entry here every time a feature
is completed, after personally observing the run. Newest entries go at the **top**
of the table. Entries are never rewritten or deleted — red runs are recorded too.

Result format: `PASS — <passed> passed, <skipped> skipped` or
`FAIL — <failed> failed (<test names>)`.

| Date | Feature | Test files added/extended | Targeted result | Full suite result | Commit |
|------|---------|---------------------------|-----------------|-------------------|--------|
| 2026-07-19 | Debug mode (--debug diagnostic logging) | tests/test_debuglog.py (26→33), tests/test_main.py (4→8), tests/ui/test_main_window_debug.py (6→7), tests/generation/test_runner.py (+1 seam test), tests/db/test_introspect.py (redaction, pre-existing) | PASS — 62 passed (targeted files) | PASS — 1315 passed, 32 skipped (30s) | d090b6f + (uncommitted tests) |
