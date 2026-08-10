"""Tests for pgtp_editor.db.activity_log -- the Activity Log's pure core
(FQ-019): the entry shape and its full-text/preview split, the four-value
source taxonomy that doubles as the persistence indicator, JSONL round-trips
that keep the untruncated DDL and error text, the set-wide dynamic timestamp
format, and the degrade-quietly `.ddlproject/activity.jsonl` store. Qt-free,
DB-free -- real temp directories only, never writing outside `tmp_path`.
"""
import json
from datetime import datetime, timedelta

from pgtp_editor.db import activity_log as activity_log_module
from pgtp_editor.db.activity_log import (
    ACTIVITY_FILENAME,
    FILE_VERB_MERGED,
    FILE_VERB_OPENED,
    FILE_VERB_SAVED,
    PREVIEW_CHARS,
    PREVIEW_ELLIPSIS,
    SOURCE_PROJECT_FILES,
    SOURCE_QUALITY_DB,
    SOURCE_QUALITY_FILES,
    SOURCE_SANDBOX_DB,
    SOURCES,
    STATUS_ERROR,
    STATUS_SUCCESS,
    TIME_FORMAT,
    VERB_RAN,
    ActivityEntry,
    ActivityLog,
    activity_path,
    append_activity,
    is_persistable,
    load_activity,
    parse_jsonl,
    preview,
    render_row,
    render_rows,
    save_activity,
    serialize_entries,
    timestamp_format,
)

# BUG-047: a local fixture payload, NOT an import from `db.activity_log`. The
# apply verbs are gesture NAMES owned by `ui.ddl_object_editor::GESTURE_LABELS`
# and are passed in by the `ui/` call sites; `db/` deliberately defines none, so
# these tests spell one out rather than reaching across the layer for it.
APPLY_VERB = "Apply to quality"

#: The pre-BUG-047 spelling, still present in journals written by older builds.
LEGACY_APPLY_VERB = "Apply to Target"

# A long, multi-line DDL body: the realistic payload, and the reason previews
# collapse whitespace before truncating.
LONG_DDL = (
    "CREATE OR REPLACE FUNCTION public.recalculate_totals(p_id integer)\n"
    "RETURNS void LANGUAGE plpgsql AS $$\n"
    "BEGIN\n"
    "    UPDATE orders SET total = 0 WHERE id = p_id;\n"
    "END;\n$$;\n"
)
LONG_ERROR = (
    'ERROR:  syntax error at or near "FROM"\nLINE 3:   SELECT * FROM;\n'
    "                          ^\nSQLSTATE: 42601\n"
)

AT = datetime(2026, 8, 8, 14, 3, 11)


def _entry(**kwargs):
    """An entry with sensible defaults; override whatever the test is about."""
    base = dict(
        timestamp=AT,
        source=SOURCE_SANDBOX_DB,
        verb=VERB_RAN,
        ddl_full=LONG_DDL,
        file_verb=None,
        status=STATUS_SUCCESS,
        error_full=None,
    )
    base.update(kwargs)
    return ActivityEntry(**base)


def _project(tmp_path, name="proj"):
    root = tmp_path / name
    root.mkdir(parents=True)
    return root


# --- the source taxonomy as the persistence indicator ------------------------
def test_the_four_sources_are_exactly_the_settled_taxonomy():
    assert SOURCES == (
        "Quality DB",
        "Sandbox DB",
        "Project files",
        "Quality files",
    )


def test_quality_files_is_session_only_even_with_a_project_open():
    # The label *means* standalone; it can never be persisted.
    assert is_persistable(SOURCE_QUALITY_FILES, project_open=True) is False
    assert _entry(source=SOURCE_QUALITY_FILES).session_only is True


def test_project_scoped_sources_persist_only_with_a_project_open():
    for source in (SOURCE_PROJECT_FILES, SOURCE_SANDBOX_DB, SOURCE_QUALITY_DB):
        assert is_persistable(source, project_open=True) is True
        assert is_persistable(source, project_open=False) is False
        assert _entry(source=source).session_only is False


# --- preview truncation ------------------------------------------------------
def test_preview_boundary_at_exactly_nineteen_twenty_and_twenty_one_chars():
    assert PREVIEW_CHARS == 20
    assert preview("A" * 19) == "A" * 19
    assert preview("A" * 20) == "A" * 20          # exactly at the limit: no ellipsis
    assert preview("A" * 21) == "A" * 20 + PREVIEW_ELLIPSIS


def test_preview_of_empty_and_missing_text_is_empty():
    assert preview(None) == ""
    assert preview("") == ""


def test_preview_never_splits_a_multi_byte_character():
    # 25 accented characters: truncation is by code point, so the 20th
    # character comes back whole and the string still round-trips through UTF-8.
    text = "á" * 25
    cut = preview(text)
    assert cut == "á" * 20 + PREVIEW_ELLIPSIS
    assert len(cut) == 21
    assert cut.encode("utf-8").decode("utf-8") == cut
    # Astral-plane characters (surrogate-pair territory) survive too.
    assert preview("🐘" * 21) == "🐘" * 20 + PREVIEW_ELLIPSIS


def test_preview_collapses_whitespace_so_a_row_stays_one_line():
    assert "\n" not in preview(LONG_DDL)
    assert preview(LONG_DDL) == "CREATE OR REPLACE FU" + PREVIEW_ELLIPSIS


def test_previews_are_derived_from_the_full_text_that_the_entry_retains():
    entry = _entry(status=STATUS_ERROR, error_full=LONG_ERROR)
    assert entry.ddl_full == LONG_DDL              # untruncated, for the viewer
    assert entry.error_full == LONG_ERROR
    assert len(entry.ddl_preview) == PREVIEW_CHARS + 1
    assert len(entry.error_preview) == PREVIEW_CHARS + 1
    assert entry.failed is True


def test_a_file_row_has_no_ddl_preview_and_a_success_row_no_error_preview():
    entry = _entry(verb=None, ddl_full=None, file_verb=FILE_VERB_SAVED,
                   source=SOURCE_PROJECT_FILES)
    assert entry.ddl_preview == ""
    assert entry.error_preview == ""


# --- JSONL round-trip --------------------------------------------------------
def test_round_trip_preserves_the_full_ddl_and_the_full_error():
    entry = _entry(verb=APPLY_VERB, source=SOURCE_QUALITY_DB,
                   status=STATUS_ERROR, error_full=LONG_ERROR)
    (restored,) = parse_jsonl(serialize_entries([entry]))

    assert restored == entry
    assert restored.ddl_full == LONG_DDL
    assert restored.error_full == LONG_ERROR
    assert restored.timestamp == AT


def test_round_trip_preserves_non_ascii_payloads_verbatim():
    entry = _entry(ddl_full="SELECT 'árvíztűrő tükörfúrógép — 🐘';")
    (restored,) = parse_jsonl(serialize_entries([entry]))
    assert restored.ddl_full == entry.ddl_full


def test_the_stored_line_is_one_json_object_with_full_text_and_no_previews():
    line = _entry(status=STATUS_ERROR, error_full=LONG_ERROR).to_json_line()
    raw = json.loads(line)

    assert "\n" not in line
    assert raw["ddl_full"] == LONG_DDL
    assert raw["error_full"] == LONG_ERROR
    assert raw["timestamp"] == AT.isoformat()
    assert "ddl_preview" not in raw and "error_preview" not in raw


def test_a_reader_ignores_stored_preview_keys_from_a_foreign_writer():
    raw = _entry().to_json_dict()
    raw["ddl_preview"] = "something stale"
    raw["unknown_future_key"] = 7
    assert ActivityEntry.from_json_dict(raw) == _entry()


def test_an_empty_log_serializes_and_reloads_cleanly(tmp_path):
    assert serialize_entries([]) == ""
    assert parse_jsonl("") == []

    root = _project(tmp_path)
    save_activity(root, [])
    assert not activity_path(root).exists()      # nothing written for an empty log
    assert load_activity(root) == []


# --- the timestamp format (ONE shape, always) --------------------------------
# FQ-019 originally specified a dynamic format that depended on the whole set's
# calendar span. The owner dropped it (2026-08-09) for one unambiguous shape, so
# what is pinned here is the ABSENCE of set-dependence: the tests below exist to
# fail if anyone reintroduces it.
def test_every_row_uses_the_one_dated_format():
    entries = [_entry(timestamp=AT), _entry(timestamp=AT + timedelta(hours=5))]
    assert timestamp_format(entries) == TIME_FORMAT
    assert [row.split(" - ")[0] for row in render_rows(entries)] == [
        "2026-08-08 14:03",
        "2026-08-08 19:03",
    ]


def test_the_format_does_not_depend_on_the_set():
    """The whole point of the simplification: an empty log, a single entry, one
    day's worth and a set spanning weeks all render the same way, so a panel can
    render a row on append and cache it."""
    spanning = [
        _entry(timestamp=datetime(2026, 8, 8, 23, 59)),
        _entry(timestamp=datetime(2026, 8, 9, 0, 0)),
        _entry(timestamp=datetime(2026, 9, 1, 8, 15)),
    ]
    assert (
        timestamp_format([])
        == timestamp_format([_entry()])
        == timestamp_format(spanning)
        == TIME_FORMAT
    )


def test_a_row_renders_identically_alone_and_in_a_set():
    """The property that lets the panel append without re-rendering: a row's
    text is a function of that row only."""
    lone = _entry(timestamp=datetime(2026, 8, 8, 9, 0))
    later = _entry(timestamp=datetime(2026, 9, 1, 8, 15))
    assert render_rows([lone])[0] == render_rows([lone, later])[0]
    assert render_row(lone) == render_rows([lone, later])[0]


def test_a_new_entry_never_reshapes_the_existing_rows():
    log = ActivityLog()
    log.record(SOURCE_QUALITY_FILES, file_verb=FILE_VERB_OPENED,
               timestamp=datetime(2026, 8, 8, 23, 59))
    first = log.rendered_rows()[0]
    log.record(SOURCE_QUALITY_FILES, file_verb=FILE_VERB_SAVED,
               timestamp=datetime(2026, 8, 9, 0, 1))
    assert log.rendered_rows()[0] == first
    assert log.timestamp_format() == TIME_FORMAT


# --- the rendered row --------------------------------------------------------
def test_a_db_row_renders_timestamp_source_verb_preview_status():
    row = render_rows([_entry()])[0]
    assert row == "2026-08-08 14:03 - Sandbox DB ran CREATE OR REPLACE FU… success"


def test_a_failed_row_appends_the_error_preview():
    row = render_rows([_entry(status=STATUS_ERROR, error_full=LONG_ERROR)])[0]
    assert row.endswith("error ERROR: syntax error …")


def test_a_file_row_uses_its_verb_as_the_payload():
    row = render_rows(
        [_entry(source=SOURCE_PROJECT_FILES, verb=None, ddl_full=None,
                file_verb=FILE_VERB_MERGED)]
    )[0]
    assert row == "2026-08-08 14:03 - Project files Merged success"


# --- malformed / absent / partial input degrades to no history ---------------
def test_absent_store_is_no_history_and_is_not_created(tmp_path):
    root = _project(tmp_path)
    assert load_activity(root) == []
    assert not activity_path(root).exists()


def test_unparseable_file_degrades_to_no_history_without_rewriting(tmp_path):
    root = _project(tmp_path)
    path = activity_path(root)
    path.parent.mkdir(parents=True)
    junk = "not json at all\n{{{\n[1, 2, 3]\n"
    path.write_text(junk, encoding="utf-8")

    assert load_activity(root) == []
    assert path.read_text(encoding="utf-8") == junk   # loading never rewrites


def test_a_directory_where_the_store_should_be_degrades_instead_of_raising(tmp_path):
    root = _project(tmp_path)
    activity_path(root).mkdir(parents=True)
    assert load_activity(root) == []


def test_partial_jsonl_keeps_the_good_lines_and_drops_the_rest(tmp_path):
    root = _project(tmp_path)
    good = _entry()
    path = activity_path(root)
    path.parent.mkdir(parents=True)
    path.write_text(
        good.to_json_line() + "\n"
        + "\n"                                   # blank line
        + "{ half written, killed mid-flush\n"
        + '"a bare string"\n'
        + json.dumps({"timestamp": "not-a-date", "source": SOURCE_SANDBOX_DB}) + "\n"
        + json.dumps({"source": SOURCE_SANDBOX_DB}) + "\n"      # no timestamp
        + json.dumps({"timestamp": AT.isoformat(), "source": "Martian DB"}) + "\n"
        + good.to_json_line() + "\n",
        encoding="utf-8",
    )
    assert load_activity(root) == [good, good]


def test_an_unknown_status_falls_back_to_success_rather_than_dropping_the_row():
    raw = _entry().to_json_dict()
    raw["status"] = "maybe"
    assert ActivityEntry.from_json_dict(raw).status == STATUS_SUCCESS


def test_non_string_optional_fields_normalise_to_none():
    raw = _entry().to_json_dict()
    raw.update(verb=17, ddl_full=[], file_verb="", error_full=None)
    restored = ActivityEntry.from_json_dict(raw)
    assert (restored.verb, restored.ddl_full, restored.file_verb,
            restored.error_full) == (None, None, None, None)


def test_from_json_dict_rejects_non_objects():
    for raw in (None, [], "x", 3):
        assert ActivityEntry.from_json_dict(raw) is None


def test_undecodable_bytes_cost_at_most_their_own_line(tmp_path):
    root = _project(tmp_path)
    good = _entry()
    path = activity_path(root)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe garbage bytes\n" + good.to_json_line().encode("utf-8") + b"\n")
    assert load_activity(root) == [good]


# --- the store ---------------------------------------------------------------
def test_the_store_is_a_sibling_of_settings_json(tmp_path):
    assert activity_path(tmp_path) == tmp_path / ".ddlproject" / ACTIVITY_FILENAME


def test_append_creates_the_store_and_round_trips_through_disk(tmp_path):
    root = _project(tmp_path)
    first = _entry()
    second = _entry(timestamp=AT + timedelta(minutes=2), verb=APPLY_VERB,
                    source=SOURCE_QUALITY_DB, status=STATUS_ERROR,
                    error_full=LONG_ERROR)

    append_activity(root, [first])
    append_activity(root, [second])

    assert load_activity(root) == [first, second]           # chronological
    assert load_activity(root)[1].error_full == LONG_ERROR  # full text survived
    assert (root / ".gitignore").read_text(encoding="utf-8").strip() == ".ddlproject/"


def test_appending_only_session_only_entries_creates_no_file(tmp_path):
    root = _project(tmp_path)
    append_activity(root, [_entry(source=SOURCE_QUALITY_FILES)])
    assert not activity_path(root).exists()


def test_save_activity_rewrites_and_can_truncate_an_existing_store(tmp_path):
    root = _project(tmp_path)
    append_activity(root, [_entry(), _entry()])
    save_activity(root, [_entry()])
    assert load_activity(root) == [_entry()]

    save_activity(root, [])
    assert activity_path(root).exists()
    assert activity_path(root).read_text(encoding="utf-8") == ""
    assert load_activity(root) == []


# --- ActivityLog: recording, flushing, project transitions -------------------
def test_record_returns_the_entry_and_appends_it_to_the_displayed_log():
    log = ActivityLog()
    entry = log.record(SOURCE_SANDBOX_DB, VERB_RAN, ddl=LONG_DDL, timestamp=AT)
    assert log.entries == (entry,)
    assert len(log) == 1
    assert entry.ddl_full == LONG_DDL


def test_recording_an_error_implies_the_error_status():
    log = ActivityLog()
    entry = log.record(SOURCE_QUALITY_DB, APPLY_VERB, ddl=LONG_DDL,
                       error=LONG_ERROR)
    assert entry.status == STATUS_ERROR and entry.failed


def test_standalone_entries_stay_in_memory_and_flush_writes_nothing(tmp_path):
    root = _project(tmp_path)
    log = ActivityLog()                                   # no project
    log.record(SOURCE_QUALITY_FILES, file_verb=FILE_VERB_SAVED, timestamp=AT)

    assert log.project_dir is None
    assert log.has_pending_writes is False
    assert log.flush() is False
    assert len(log.entries) == 1                          # still displayed
    assert not activity_path(root).exists()


def test_a_project_log_flushes_pending_entries_once(tmp_path):
    root = _project(tmp_path)
    log = ActivityLog(root)
    log.record(SOURCE_PROJECT_FILES, file_verb=FILE_VERB_SAVED, timestamp=AT)

    assert log.has_pending_writes is True
    assert log.flush() is True
    assert log.has_pending_writes is False
    assert log.flush() is False                           # nothing left to write
    assert len(load_activity(root)) == 1                  # not written twice


def test_a_new_log_loads_that_projects_persisted_history(tmp_path):
    root = _project(tmp_path)
    first = ActivityLog(root)
    first.record(SOURCE_SANDBOX_DB, VERB_RAN, ddl=LONG_DDL, timestamp=AT)
    first.flush()

    second = ActivityLog(root)                            # a later session
    assert [e.ddl_full for e in second.entries] == [LONG_DDL]


def test_a_session_only_entry_is_never_written_even_with_a_project_open(tmp_path):
    root = _project(tmp_path)
    log = ActivityLog(root)
    log.record(SOURCE_QUALITY_FILES, file_verb=FILE_VERB_SAVED, timestamp=AT)
    log.flush()
    assert load_activity(root) == []
    assert len(log.entries) == 1


def test_opening_a_project_flushes_then_replaces_the_buffer(tmp_path):
    old = _project(tmp_path, "old")
    new = _project(tmp_path, "new")
    log = ActivityLog(old)
    log.record(SOURCE_PROJECT_FILES, file_verb=FILE_VERB_SAVED, timestamp=AT)

    log.open_project(new)

    assert load_activity(old)[0].file_verb == FILE_VERB_SAVED  # owed write landed
    assert log.project_dir == new
    assert log.entries == ()                                   # new project's history
    assert not activity_path(new).exists()


def test_standalone_entries_do_not_follow_the_user_into_a_project(tmp_path):
    root = _project(tmp_path)
    log = ActivityLog()
    log.record(SOURCE_QUALITY_FILES, file_verb=FILE_VERB_OPENED, timestamp=AT)

    log.open_project(root)

    assert log.entries == ()
    assert load_activity(root) == []


def test_closing_a_project_flushes_and_drops_back_to_standalone(tmp_path):
    root = _project(tmp_path)
    log = ActivityLog(root)
    log.record(SOURCE_SANDBOX_DB, VERB_RAN, ddl=LONG_DDL, timestamp=AT)

    log.close_project()

    assert len(load_activity(root)) == 1
    assert log.project_dir is None
    assert log.entries == ()


def test_rendered_rows_of_a_log_share_one_format():
    log = ActivityLog()
    log.record(SOURCE_QUALITY_FILES, file_verb=FILE_VERB_OPENED,
               timestamp=datetime(2026, 8, 8, 9, 0))
    log.record(SOURCE_QUALITY_FILES, file_verb=FILE_VERB_SAVED,
               timestamp=datetime(2026, 8, 9, 9, 0))
    assert log.rendered_rows() == [
        "2026-08-08 09:00 - Quality files Opened success",
        "2026-08-09 09:00 - Quality files Saved success",
    ]


# --- BUG-047: the journal speaks the app's vocabulary, and only the app's -----
def test_this_module_defines_no_ddl_object_gesture_name():
    """`db/activity_log.py` must define NO string that is a DDL-object gesture
    name. Those names are owned once, by `ui.ddl_object_editor::GESTURE_LABELS`
    (FQ-026's one-name-per-operation invariant), and are passed in from the
    `ui/` call sites; a copy in this Qt-free module could only ever be a second
    literal free to drift -- which is exactly what BUG-047 was. The deletion
    guard, mirroring FQ-026's own.
    """
    from pgtp_editor.ui.ddl_object_editor import GESTURE_LABELS

    defined: set[str] = set()
    for name, value in vars(activity_log_module).items():
        if name.startswith("__"):
            continue
        if isinstance(value, str):
            defined.add(value)
        elif isinstance(value, (tuple, frozenset, set)):
            defined.update(v for v in value if isinstance(v, str))

    assert not defined & set(GESTURE_LABELS.values())


def test_a_journal_written_before_the_rename_still_loads_and_renders(tmp_path):
    """The rename is WRITE-TIME, with no migration: `activity.jsonl` is
    append-only and rows already on disk keep the name the app used when the
    user clicked. That is only defensible if those rows keep working, so it is
    asserted here rather than left as an assumption.
    """
    root = _project(tmp_path)
    path = activity_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "timestamp": AT.isoformat(),
                "source": SOURCE_QUALITY_DB,
                "verb": LEGACY_APPLY_VERB,
                "ddl_full": LONG_DDL,
                "status": STATUS_SUCCESS,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    entries = load_activity(root)

    assert [e.verb for e in entries] == [LEGACY_APPLY_VERB]
    assert LEGACY_APPLY_VERB in render_row(entries[0])
