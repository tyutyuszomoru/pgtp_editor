"""Database Check support: Qt-free connection/introspection logic.

Validates a `.pgtp` project against a live PostgreSQL database. psycopg is
imported lazily (only inside `introspect.run_queries`) so this package — and the
whole test suite — imports cleanly even when psycopg is not installed.
"""
