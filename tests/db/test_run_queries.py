# tests/db/test_run_queries.py
"""Tests for pgtp_editor.db.introspect.run_queries.

Unlike test_introspect.py (which never touches psycopg), these exercise the ONE
function that opens a connection — but psycopg.connect is monkeypatched to a
fake that records kwargs and returns a fake connection/cursor, so NO real
connection is ever opened. The point is to prove ``connect_timeout`` is passed
through, bounding any hang.
"""
from pgtp_editor.db import introspect
from pgtp_editor.db.config import ConnectionParams

_PARAMS = ConnectionParams(host="h", port="5432", database="d", user="u", password="p")


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        self.sql = sql

    def fetchall(self):
        return [(1,)]


class _FakeConnection:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return _FakeCursor()

    def close(self):
        self.closed = True


def _patch_connect(monkeypatch):
    import psycopg

    recorded = {}

    def fake_connect(**kwargs):
        recorded.update(kwargs)
        return _FakeConnection()

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    return recorded


def test_run_queries_passes_default_connect_timeout(monkeypatch):
    recorded = _patch_connect(monkeypatch)
    result = introspect.run_queries(_PARAMS, ["SELECT 1"])
    assert recorded["connect_timeout"] == 10
    assert result == [[(1,)]]


def test_run_queries_connect_timeout_is_overridable(monkeypatch):
    recorded = _patch_connect(monkeypatch)
    introspect.run_queries(_PARAMS, ["SELECT 1"], connect_timeout=3)
    assert recorded["connect_timeout"] == 3


def test_run_queries_passes_params_through(monkeypatch):
    recorded = _patch_connect(monkeypatch)
    introspect.run_queries(_PARAMS, ["SELECT 1"])
    assert recorded["host"] == "h"
    assert recorded["dbname"] == "d"
    assert recorded["user"] == "u"
