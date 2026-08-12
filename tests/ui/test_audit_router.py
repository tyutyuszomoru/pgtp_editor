# tests/ui/test_audit_router.py
"""Tests for `ui/audit_router.py`'s `[DDL]` destination (FQ-260812022749).

The router's older behaviour is exercised through its producers; this file
covers the eleventh prefix, whose whole point is that the dual-mode DDL
verdict lands on a surface the user can actually read.
"""
from pgtp_editor.ui import audit_router


class _Panel:
    """The bare `QListWidget`-ish surface the router writes to."""

    def __init__(self):
        self.items = []
        self.runs = 0

    def addItem(self, item):
        self.items.append(item)

    def begin_run(self):
        self.runs += 1

    def clear(self):
        self.items = []

    def row(self, item):
        return self.items.index(item) if item in self.items else -1

    def takeItem(self, index):
        return self.items.pop(index)

    def texts(self):
        return [item.text() for item in self.items]


def test_ddl_prefix_routes_to_the_messages_tab():
    """Owner-settled: the notice goes to the visible, accumulating Messages
    tab -- never the status bar, which paints nothing (BUG-260812002307)."""
    assert audit_router.DESTINATIONS[audit_router.DDL_PREFIX] == audit_router.TO_RESULTS
    assert audit_router.classify("[DDL] Full DDL via pg_dump 17.2 (server 16.0.3).") == (
        audit_router.TO_RESULTS
    )


def test_ddl_prefix_is_its_own_prefix_not_a_reuse_of_sandbox():
    assert audit_router.DDL_PREFIX == "[DDL]"
    assert audit_router.DDL_PREFIX != audit_router.SANDBOX_PREFIX


def test_a_ddl_verdict_row_lands_on_messages_with_both_version_numbers():
    from pgtp_editor.db.pg_dump_mode import decide_ddl_mode

    verdict = decide_ddl_mode((16, 0, 3), "/usr/bin/pg_dump", (15, 6))
    text = f"{audit_router.DDL_PREFIX} {verdict.message}"
    findings, results = _Panel(), _Panel()
    router = audit_router.AuditRouter(findings, results, lambda *_: None)

    router.addItem(text)

    assert results.texts() == [text]
    assert findings.texts() == []
    assert "15.6" in results.texts()[0]
    assert "16.0.3" in results.texts()[0]


def test_a_full_mode_verdict_row_also_lands_on_messages():
    from pgtp_editor.db.pg_dump_mode import decide_ddl_mode

    verdict = decide_ddl_mode((16, 0, 3), "/usr/bin/pg_dump", (17, 2))
    findings, results = _Panel(), _Panel()
    router = audit_router.AuditRouter(findings, results, lambda *_: None)

    router.addItem(f"{audit_router.DDL_PREFIX} {verdict.message}")

    assert len(results.items) == 1
    assert "17.2" in results.texts()[0] and "16.0.3" in results.texts()[0]


def test_a_ddl_row_is_never_journalled_to_the_activity_log():
    journalled = []
    findings, results = _Panel(), _Panel()
    router = audit_router.AuditRouter(
        findings, results, lambda text, prefix: journalled.append(text)
    )

    router.addItem("[DDL] Restricted DDL — pg_dump not found (server 16.0.3).")

    assert journalled == []
    assert len(results.items) == 1


def test_repeated_ddl_rows_accumulate_rather_than_replacing_each_other():
    """The notice is emitted on EVERY DDL open by owner ruling -- the
    repetition is accepted on purpose, so the surface must accumulate."""
    findings, results = _Panel(), _Panel()
    router = audit_router.AuditRouter(findings, results, lambda *_: None)

    router.addItem("[DDL] Full DDL via pg_dump 17.2 (server 16.0.3).")
    router.addItem("[DDL] Full DDL via pg_dump 17.2 (server 16.0.3).")

    assert len(results.items) == 2
