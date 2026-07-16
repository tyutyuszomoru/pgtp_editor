# tests/db/test_config.py
"""Tests for pgtp_editor.db.config — ConnectionParams, connection_from_tree,
seed_params, and the save/load round-trip via an injected QSettings.

No live database and no psycopg import here: config is pure aside from QSettings.
"""
from lxml import etree
from PySide6.QtCore import QSettings

from pgtp_editor.db.config import (
    ConnectionParams,
    connection_from_tree,
    load_connection,
    save_connection,
    seed_params,
)


def _tree(xml: str):
    return etree.ElementTree(etree.fromstring(xml.encode("utf-8")))


def _settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def test_connection_from_tree_reads_attributes_password_always_blank():
    tree = _tree(
        '<Project><ConnectionOptions host="h" port="5432" login="u" '
        'password="XXX" database="d"/></Project>'
    )
    params = connection_from_tree(tree)
    assert params == ConnectionParams(
        host="h", port="5432", database="d", user="u", password=""
    )


def test_connection_from_tree_missing_element_returns_none():
    tree = _tree("<Project><Other/></Project>")
    assert connection_from_tree(tree) is None


def test_connection_from_tree_none_tree_returns_none():
    assert connection_from_tree(None) is None


def test_save_load_round_trip(tmp_path):
    settings = _settings(tmp_path)
    params = ConnectionParams(
        host="h", port="5432", database="d", user="u", password="secret"
    )
    save_connection(settings, params)

    # Fresh QSettings on the same file to prove persistence.
    reloaded = load_connection(_settings(tmp_path))
    assert reloaded == params


def test_load_connection_absent_returns_none(tmp_path):
    assert load_connection(_settings(tmp_path)) is None


def test_seed_params_saved_wins_over_tree(tmp_path):
    # Once a connection is saved (e.g. host corrected localhost -> 127.0.0.1),
    # those values win over the project's <ConnectionOptions> on reopen.
    settings = _settings(tmp_path)
    save_connection(
        settings,
        ConnectionParams(
            host="127.0.0.1", port="1111", database="sd", user="su", password="pw"
        ),
    )
    tree = _tree(
        '<Project><ConnectionOptions host="localhost" port="2222" login="tu" '
        'password="ignored" database="td"/></Project>'
    )
    seeded = seed_params(tree, settings)
    assert seeded == ConnectionParams(
        host="127.0.0.1", port="1111", database="sd", user="su", password="pw"
    )


def test_seed_params_uses_tree_when_nothing_saved(tmp_path):
    settings = _settings(tmp_path)
    tree = _tree(
        '<Project><ConnectionOptions host="th" port="2222" login="tu" '
        'password="ignored" database="td"/></Project>'
    )
    seeded = seed_params(tree, settings)
    assert seeded == ConnectionParams(
        host="th", port="2222", database="td", user="tu", password=""
    )


def test_seed_params_falls_back_to_settings_when_no_tree(tmp_path):
    settings = _settings(tmp_path)
    save_connection(
        settings,
        ConnectionParams(
            host="sh", port="1111", database="sd", user="su", password="pw"
        ),
    )
    seeded = seed_params(None, settings)
    assert seeded == ConnectionParams(
        host="sh", port="1111", database="sd", user="su", password="pw"
    )


def test_seed_params_blanks_when_nothing_available(tmp_path):
    seeded = seed_params(None, _settings(tmp_path))
    assert seeded == ConnectionParams(
        host="", port="", database="", user="", password=""
    )
