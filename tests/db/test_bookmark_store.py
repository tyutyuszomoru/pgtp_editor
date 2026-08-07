"""Tests for pgtp_editor.db.bookmark_store -- project-local bookmark
persistence (§8 + §18.2, FQ-013): the `.ddlproject/bookmarks.json` sibling
file, project-relative POSIX keying, in-range restore, and degrade-quietly
reads. Qt-free, DB-free -- real temp directories only, never writing outside
`tmp_path`.
"""
import json

from pgtp_editor.db.bookmark_store import (
    BOOKMARKS_VERSION,
    bookmarks_path,
    load_bookmarks,
    load_editor_bookmarks,
    prune_missing_files,
    relative_key,
    save_bookmarks,
    store_editor_bookmarks,
)


def _project(tmp_path, name="proj"):
    """A project folder with one real file under `ddl/`."""
    root = tmp_path / name
    (root / "ddl").mkdir(parents=True)
    (root / "ddl" / "public.foo.sql").write_text("-- ddl\n", encoding="utf-8")
    return root


# --- location and shape -----------------------------------------------------
def test_store_is_a_sibling_of_settings_json(tmp_path):
    assert bookmarks_path(tmp_path) == tmp_path / ".ddlproject" / "bookmarks.json"


def test_on_disk_shape_is_versioned_and_keyed_by_relative_path(tmp_path):
    root = _project(tmp_path)
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", {41, 3, 3})

    raw = json.loads(bookmarks_path(root).read_text(encoding="utf-8"))
    assert raw == {"version": BOOKMARKS_VERSION, "files": {"ddl/public.foo.sql": [3, 41]}}


def test_keys_use_posix_separators_even_for_nested_paths(tmp_path):
    root = _project(tmp_path)
    nested = root / "php" / "inc" / "helpers.php"
    nested.parent.mkdir(parents=True)
    nested.write_text("<?php\n", encoding="utf-8")

    assert relative_key(root, nested) == "php/inc/helpers.php"
    assert "\\" not in relative_key(root, nested)


def test_a_file_outside_the_project_has_no_key_and_storing_is_a_no_op(tmp_path):
    root = _project(tmp_path)
    outsider = tmp_path / "elsewhere.sql"
    outsider.write_text("x\n", encoding="utf-8")

    assert relative_key(root, outsider) is None
    store_editor_bookmarks(root, outsider, {1, 2})
    assert not bookmarks_path(root).exists()
    assert load_editor_bookmarks(root, outsider, 100) == set()


def test_the_project_folder_itself_has_no_key(tmp_path):
    root = _project(tmp_path)
    assert relative_key(root, root) is None


# --- round-trip -------------------------------------------------------------
def test_round_trip_through_the_whole_store(tmp_path):
    root = _project(tmp_path)
    save_bookmarks(root, {"ddl/public.foo.sql": [7, 2], "app.pgtp": {0}})

    assert load_bookmarks(root) == {"ddl/public.foo.sql": [2, 7], "app.pgtp": [0]}


def test_round_trip_for_one_editor(tmp_path):
    root = _project(tmp_path)
    target = root / "ddl" / "public.foo.sql"
    store_editor_bookmarks(root, target, [5, 1])

    assert load_editor_bookmarks(root, target, block_count=100) == {1, 5}


def test_storing_one_editor_leaves_other_keys_alone(tmp_path):
    root = _project(tmp_path)
    save_bookmarks(root, {"other.sql": [9]})
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", [4])

    assert load_bookmarks(root) == {"other.sql": [9], "ddl/public.foo.sql": [4]}


def test_writes_are_idempotent(tmp_path):
    root = _project(tmp_path)
    save_bookmarks(root, {"ddl/public.foo.sql": [3, 1]})
    first = bookmarks_path(root).read_bytes()
    save_bookmarks(root, {"ddl/public.foo.sql": [1, 3]})

    assert bookmarks_path(root).read_bytes() == first


# --- a moved / cloned project still resolves --------------------------------
def test_a_moved_project_keeps_its_bookmarks(tmp_path):
    root = _project(tmp_path, "before")
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", [11])

    moved = tmp_path / "after"
    root.rename(moved)

    assert load_editor_bookmarks(moved, moved / "ddl" / "public.foo.sql", 100) == {11}


def test_a_cloned_project_at_another_path_resolves_the_same_key(tmp_path):
    import shutil

    root = _project(tmp_path, "origin")
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", [2, 6])
    clone = tmp_path / "mount" / "clone"
    shutil.copytree(root, clone)

    assert load_editor_bookmarks(clone, clone / "ddl" / "public.foo.sql", 100) == {2, 6}


# --- stale lines: restore in range, drop out of range -----------------------
def test_out_of_range_lines_are_dropped_on_load(tmp_path):
    root = _project(tmp_path)
    target = root / "ddl" / "public.foo.sql"
    store_editor_bookmarks(root, target, [0, 4, 99])

    assert load_editor_bookmarks(root, target, block_count=5) == {0, 4}


def test_dropping_out_of_range_lines_does_not_rewrite_the_store(tmp_path):
    """Load is read-only -- a shortened document must not silently discard the
    stored lines, which may come back when the file grows again."""
    root = _project(tmp_path)
    target = root / "ddl" / "public.foo.sql"
    store_editor_bookmarks(root, target, [1, 90])
    load_editor_bookmarks(root, target, block_count=3)

    assert load_bookmarks(root)["ddl/public.foo.sql"] == [1, 90]


def test_an_empty_document_restores_nothing(tmp_path):
    root = _project(tmp_path)
    target = root / "ddl" / "public.foo.sql"
    store_editor_bookmarks(root, target, [0])

    assert load_editor_bookmarks(root, target, block_count=0) == set()


# --- empty-set handling -----------------------------------------------------
def test_an_empty_set_removes_the_key_rather_than_storing_it(tmp_path):
    root = _project(tmp_path)
    target = root / "ddl" / "public.foo.sql"
    store_editor_bookmarks(root, target, [3])
    store_editor_bookmarks(root, target, set())

    assert load_bookmarks(root) == {}
    raw = json.loads(bookmarks_path(root).read_text(encoding="utf-8"))
    assert raw == {"version": BOOKMARKS_VERSION, "files": {}}


def test_an_empty_store_is_not_created_for_a_project_nobody_bookmarked_in(tmp_path):
    root = _project(tmp_path)
    save_bookmarks(root, {})
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", [])

    assert not bookmarks_path(root).exists()
    assert load_bookmarks(root) == {}


def test_saving_drops_keys_with_no_lines(tmp_path):
    root = _project(tmp_path)
    save_bookmarks(root, {"a.sql": [1], "b.sql": []})

    assert load_bookmarks(root) == {"a.sql": [1]}


# --- degrading quietly ------------------------------------------------------
def test_a_missing_file_means_no_bookmarks(tmp_path):
    root = _project(tmp_path)
    assert load_bookmarks(root) == {}
    assert load_editor_bookmarks(root, root / "ddl" / "public.foo.sql", 10) == set()


def test_malformed_json_means_no_bookmarks(tmp_path):
    root = _project(tmp_path)
    path = bookmarks_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json at all", encoding="utf-8")

    assert load_bookmarks(root) == {}
    assert load_editor_bookmarks(root, root / "ddl" / "public.foo.sql", 10) == set()


def test_an_unknown_schema_version_means_no_bookmarks(tmp_path):
    root = _project(tmp_path)
    path = bookmarks_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": BOOKMARKS_VERSION + 7, "files": {"a.sql": [1]}}),
        encoding="utf-8",
    )

    assert load_bookmarks(root) == {}


def test_a_wrong_top_level_shape_means_no_bookmarks(tmp_path):
    root = _project(tmp_path)
    path = bookmarks_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    for text in ("[]", '"hello"', json.dumps({"version": BOOKMARKS_VERSION, "files": 3})):
        path.write_text(text, encoding="utf-8")
        assert load_bookmarks(root) == {}


def test_garbage_entries_are_dropped_without_losing_the_good_ones(tmp_path):
    root = _project(tmp_path)
    path = bookmarks_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": BOOKMARKS_VERSION,
                "files": {
                    "good.sql": [2, "x", -1, None, True, 2],
                    "junk.sql": "not a list",
                    "": [1],
                    "empty.sql": [],
                },
            }
        ),
        encoding="utf-8",
    )

    assert load_bookmarks(root) == {"good.sql": [2]}


def test_a_directory_where_the_store_should_be_degrades_quietly(tmp_path):
    root = _project(tmp_path)
    bookmarks_path(root).mkdir(parents=True)

    assert load_bookmarks(root) == {}


# --- gitignore --------------------------------------------------------------
def test_saving_gitignores_the_ddlproject_directory(tmp_path):
    root = _project(tmp_path)
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", [1])

    assert (root / ".gitignore").read_text(encoding="utf-8").splitlines() == [".ddlproject/"]


def test_no_second_redundant_gitignore_entry_is_added(tmp_path):
    """`save_settings` already gitignores `.ddlproject/`, which covers this
    file -- the store must not append a second entry for it."""
    from pgtp_editor.db.ddl_project import ProjectSettings, save_settings

    root = _project(tmp_path)
    save_settings(root, ProjectSettings())
    before = (root / ".gitignore").read_text(encoding="utf-8")
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", [1])
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", [1, 2])

    assert (root / ".gitignore").read_text(encoding="utf-8") == before
    assert before.count(".ddlproject") == 1


# --- pruning ----------------------------------------------------------------
def test_pruning_drops_keys_whose_file_is_gone(tmp_path):
    root = _project(tmp_path)
    save_bookmarks(root, {"ddl/public.foo.sql": [1], "ddl/vanished.sql": [2]})
    prune_missing_files(root)

    assert load_bookmarks(root) == {"ddl/public.foo.sql": [1]}


def test_pruning_is_a_no_op_when_nothing_is_stale(tmp_path):
    root = _project(tmp_path)
    store_editor_bookmarks(root, root / "ddl" / "public.foo.sql", [1])
    before = bookmarks_path(root).read_bytes()
    prune_missing_files(root)

    assert bookmarks_path(root).read_bytes() == before


# --- purity guards ----------------------------------------------------------
def test_module_is_qt_free():
    import inspect

    import pgtp_editor.db.bookmark_store as module

    source = inspect.getsource(module)
    assert "PySide6" not in source
    assert "QtCore" not in source
    assert "QtWidgets" not in source


def test_module_is_unwired():
    """FQ-013's storage lane deliberately ships unwired (the `db/apply.py`
    precedent): no `ui/` module imports it yet. **The UI lane that wires the
    gutter to this store should delete this test as part of wiring it.**"""
    import pathlib

    ui_dir = pathlib.Path(__file__).resolve().parents[2] / "pgtp_editor" / "ui"
    importers = [
        path.name
        for path in ui_dir.rglob("*.py")
        if "bookmark_store" in path.read_text(encoding="utf-8")
    ]
    assert importers == []
