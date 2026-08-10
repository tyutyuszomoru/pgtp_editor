# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""`sql/snippet_store.py` — the store's format, its failure modes, its
collision rule. Qt-free, like the module under test; every path is a tmp_path,
so nothing here can reach a real config directory."""
from __future__ import annotations

import json

from pgtp_editor.sql.snippet_store import (
    ORIGIN_DEFAULT,
    ORIGIN_MODIFIED_DEFAULT,
    ORIGIN_USER,
    SNIPPETS_FILENAME,
    apply_import,
    defaults_missing_from,
    load_snippets,
    origin_of,
    parse_snippets,
    plan_import,
    save_snippets,
    serialize_snippets,
)
from pgtp_editor.sql.templates import DEFAULT_SNIPPETS, Snippet, find_snippet

MINE = Snippet("upd", "an update", "UPDATE {{1:t}} SET {{0}};")


# -- format ------------------------------------------------------------------


def test_round_trip_preserves_every_field():
    text = serialize_snippets(DEFAULT_SNIPPETS)
    loaded = parse_snippets(text)
    assert loaded.ok and loaded.from_file
    assert loaded.snippets == DEFAULT_SNIPPETS


def test_the_written_file_is_human_readable_json():
    text = serialize_snippets((MINE,))
    assert text.endswith("\n")
    assert "\n  " in text  # indented, not one line
    data = json.loads(text)
    assert data["version"] == 1
    assert data["snippets"] == [
        {"prefix": "upd", "title": "an update", "template": MINE.template}
    ]


def test_a_bare_json_list_is_accepted():
    """The shape a human most plausibly hand-writes."""
    loaded = parse_snippets('[{"prefix": "x", "template": "SELECT 1"}]')
    assert loaded.ok
    assert loaded.snippets == (Snippet("x", "", "SELECT 1"),)


def test_an_empty_snippet_list_is_a_legitimate_answer():
    loaded = parse_snippets('{"snippets": []}')
    assert loaded.ok and loaded.snippets == ()


# -- failure modes: the defaults survive, and the reason is stated ------------


def test_broken_json_keeps_the_defaults_and_reports_why():
    loaded = parse_snippets("{ not json")
    assert loaded.snippets == DEFAULT_SNIPPETS
    assert loaded.from_file is False
    assert loaded.error and "JSON" in loaded.error


def test_a_row_without_a_trigger_word_is_refused_not_dropped():
    """Silently dropping the bad row would discard a user's snippet."""
    loaded = parse_snippets('{"snippets": [{"prefix": "", "template": "x"}]}')
    assert loaded.error and "trigger word" in loaded.error
    assert loaded.snippets == DEFAULT_SNIPPETS


def test_a_duplicate_trigger_word_is_refused():
    loaded = parse_snippets(
        '{"snippets": [{"prefix": "a", "template": "1"},'
        ' {"prefix": "A", "template": "2"}]}'
    )
    assert loaded.error and "more than once" in loaded.error


def test_missing_file_is_the_defaults_and_no_error(tmp_path):
    loaded = load_snippets(tmp_path / SNIPPETS_FILENAME)
    assert loaded.snippets == DEFAULT_SNIPPETS
    assert loaded.ok and loaded.from_file is False


def test_empty_file_is_treated_as_nothing_stored_yet(tmp_path):
    path = tmp_path / SNIPPETS_FILENAME
    path.write_text("   \n", encoding="utf-8")
    loaded = load_snippets(path)
    assert loaded.snippets == DEFAULT_SNIPPETS and loaded.ok


def test_a_directory_where_the_file_should_be_is_reported_not_raised(tmp_path):
    path = tmp_path / SNIPPETS_FILENAME
    path.mkdir()
    loaded = load_snippets(path)
    assert loaded.error and loaded.snippets == DEFAULT_SNIPPETS


# -- file I/O ----------------------------------------------------------------


def test_save_then_load_is_the_identity(tmp_path):
    path = tmp_path / "nested" / SNIPPETS_FILENAME
    save_snippets(path, (MINE,))
    assert path.exists()
    loaded = load_snippets(path)
    assert loaded.snippets == (MINE,) and loaded.from_file


def test_a_saved_store_drives_the_expansion_engine_unchanged(tmp_path):
    """The store never forks the engine: what comes back off disk is what
    `find_snippet` takes."""
    path = tmp_path / SNIPPETS_FILENAME
    save_snippets(path, (MINE,))
    snippets = load_snippets(path).snippets
    assert find_snippet("UPD", snippets) == MINE
    assert find_snippet("case", snippets) is None  # the file IS the whole set


# -- classification ----------------------------------------------------------


def test_origin_distinguishes_shipped_edited_and_own():
    shipped = DEFAULT_SNIPPETS[0]
    assert origin_of(shipped) == ORIGIN_DEFAULT
    assert origin_of(Snippet(shipped.prefix, shipped.title, "X")) == (
        ORIGIN_MODIFIED_DEFAULT
    )
    assert origin_of(MINE) == ORIGIN_USER


def test_defaults_missing_from_names_what_was_deleted():
    kept = DEFAULT_SNIPPETS[1:]
    assert defaults_missing_from(kept) == (DEFAULT_SNIPPETS[0],)
    assert defaults_missing_from(DEFAULT_SNIPPETS) == ()


# -- the import collision rule -----------------------------------------------


def test_plan_splits_new_prefixes_from_colliding_ones():
    incoming = (MINE, Snippet("CASE", "theirs", "THEIR CASE"))
    plan = plan_import(DEFAULT_SNIPPETS, incoming)
    assert plan.added == (MINE,)
    assert plan.colliding == (incoming[1],)  # case-insensitive, like lookup


def test_import_without_overwrite_adds_new_and_touches_nothing_else():
    incoming = (MINE, Snippet("case", "theirs", "THEIR CASE"))
    result = apply_import(DEFAULT_SNIPPETS, incoming, overwrite=False)
    assert result[: len(DEFAULT_SNIPPETS)] == DEFAULT_SNIPPETS
    assert result[len(DEFAULT_SNIPPETS) :] == (MINE,)


def test_import_with_overwrite_replaces_in_place_keeping_order():
    theirs = Snippet("case", "theirs", "THEIR CASE")
    result = apply_import(DEFAULT_SNIPPETS, (theirs,), overwrite=True)
    assert result[0] == theirs
    assert result[1:] == DEFAULT_SNIPPETS[1:]
    assert len(result) == len(DEFAULT_SNIPPETS)


def test_import_never_removes_an_existing_snippet():
    result = apply_import(DEFAULT_SNIPPETS, (), overwrite=True)
    assert result == DEFAULT_SNIPPETS


def test_duplicates_inside_the_imported_file_keep_the_first():
    plan = plan_import((), (Snippet("a", "1", "1"), Snippet("A", "2", "2")))
    assert plan.added == (Snippet("a", "1", "1"),)
