"""Tests for pgtp_editor.db.ddl_project -- local DDL-versioning projects
(§18.2): the project-settings JSON, ddl/*.sql path naming, and content-hash
drift comparison. Qt-free, DB-free -- real temp directories only.
"""
from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.ddl_project import (
    SETTINGS_DIRNAME,
    DeployedObject,
    DriftMarkers,
    GitConfig,
    PgtpLink,
    ProjectSettings,
    Reconciliation,
    compute_drift_markers,
    content_hash,
    is_project_dir,
    load_settings,
    parse_checked_out_header,
    reconcile_routine_paths,
    routine_ddl_paths,
    sanitize_filename_component,
    save_settings,
    settings_path,
    trigger_ddl_path,
)
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TriggerInfo
from pgtp_editor.db.sandbox import SandboxMode


def _routine(schema, name, arg_types, **kwargs):
    return RoutineInfo(schema=schema, name=name, arg_types=list(arg_types), **kwargs)


# --- Settings JSON: shape, round-trip, gitignore -----------------------------
def test_settings_path_is_one_file_under_ddlproject(tmp_path):
    assert settings_path(tmp_path) == tmp_path / ".ddlproject" / "settings.json"


def test_load_settings_on_a_brand_new_project_returns_defaults(tmp_path):
    settings = load_settings(tmp_path)
    assert settings == ProjectSettings()
    assert not (tmp_path / ".ddlproject").exists()  # nothing written by loading


# --- BUG-022: the Open-Project validity gate --------------------------------
def test_is_project_dir_false_for_a_brand_new_empty_folder(tmp_path):
    assert is_project_dir(tmp_path) is False


def test_is_project_dir_false_when_ddlproject_dir_exists_but_has_no_settings_file(tmp_path):
    (tmp_path / ".ddlproject").mkdir()
    assert is_project_dir(tmp_path) is False


def test_is_project_dir_true_after_save_settings(tmp_path):
    save_settings(tmp_path, ProjectSettings())
    assert is_project_dir(tmp_path) is True


def test_is_project_dir_false_for_a_nonexistent_path(tmp_path):
    assert is_project_dir(tmp_path / "does-not-exist") is False


def test_save_then_load_round_trips_every_field(tmp_path):
    settings = ProjectSettings(
        name="ERP overhaul",
        description="Q3 checkout",
        pgtp=PgtpLink(
            source_path="/mnt/quality/ERP_J01.pgtp",
            working_copy_path=str(tmp_path / "ERP_J01.pgtp"),
            last_known_source_checksum="abc123",
        ),
        target=ConnectionParams(host="db01", port="5432", database="erp", user="dev", password="s3cr3t"),
        sandbox=ConnectionParams(host="localhost", port="5432", database="sandbox", user="dev", password="local"),
        deployed={
            "ddl/pr.recalc.sql": DeployedObject(content_hash="h1", deployed_commit=None),
            "ddl/pr.fmt_1.sql": DeployedObject(content_hash="h2", deployed_commit="abc1234"),
        },
    )

    save_settings(tmp_path, settings)
    loaded = load_settings(tmp_path)

    assert loaded == settings


def test_settings_file_is_plaintext_and_holds_the_password_verbatim(tmp_path):
    settings = ProjectSettings(target=ConnectionParams(host="h", password="plain-secret"))
    save_settings(tmp_path, settings)

    raw = settings_path(tmp_path).read_text(encoding="utf-8")

    assert "plain-secret" in raw  # gitignored instead of QSettings-hidden, not both


def test_save_settings_creates_a_gitignore_entry_for_ddlproject(tmp_path):
    save_settings(tmp_path, ProjectSettings())

    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")

    assert ".ddlproject/" in gitignore.splitlines()


def test_save_settings_does_not_duplicate_an_existing_gitignore_entry(tmp_path):
    (tmp_path / ".gitignore").write_text("*.pyc\n.ddlproject/\n", encoding="utf-8")

    save_settings(tmp_path, ProjectSettings())

    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".ddlproject/") == 1
    assert "*.pyc" in lines  # untouched


# --- sandbox_mode (§18.5 D2a) -------------------------------------------------
def test_default_sandbox_mode_is_schema_only(tmp_path):
    assert ProjectSettings().sandbox_mode == SandboxMode.SCHEMA_ONLY


def test_sandbox_mode_round_trips_with_data(tmp_path):
    settings = ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA)

    save_settings(tmp_path, settings)
    loaded = load_settings(tmp_path)

    assert loaded.sandbox_mode == SandboxMode.WITH_DATA


def test_sandbox_mode_is_recorded_in_settings_json_as_plain_text(tmp_path):
    save_settings(tmp_path, ProjectSettings(sandbox_mode=SandboxMode.WITH_DATA))

    raw = settings_path(tmp_path).read_text(encoding="utf-8")

    assert '"sandbox_mode": "with_data"' in raw


def test_loading_a_settings_file_with_no_sandbox_mode_key_defaults_to_schema_only(tmp_path):
    """An older settings.json written before D2a existed has no `sandbox_mode`
    key at all -- must default gracefully, never fail to load the project."""
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"name": "legacy", "deployed": {}}', encoding="utf-8")

    loaded = load_settings(tmp_path)

    assert loaded.sandbox_mode == SandboxMode.SCHEMA_ONLY
    assert loaded.name == "legacy"


def test_loading_a_settings_file_with_an_unrecognized_sandbox_mode_defaults_gracefully(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"sandbox_mode": "nonsense"}', encoding="utf-8")

    loaded = load_settings(tmp_path)

    assert loaded.sandbox_mode == SandboxMode.SCHEMA_ONLY


def test_save_settings_preserves_unrelated_gitignore_content(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n__pycache__/\n", encoding="utf-8")

    save_settings(tmp_path, ProjectSettings())

    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "node_modules/" in lines
    assert "__pycache__/" in lines
    assert ".ddlproject/" in lines


def test_git_config_round_trips_as_captured_intent_only(tmp_path):
    """§18.2: git is optional and TBD -- these fields are captured and
    persisted, but nothing in this module ever reads or acts on them."""
    settings = ProjectSettings(
        git=GitConfig(server="git.example.com", user="dev", checkout_branch="feature/x")
    )
    save_settings(tmp_path, settings)
    loaded = load_settings(tmp_path)
    assert loaded.git == GitConfig(server="git.example.com", user="dev", checkout_branch="feature/x")


def test_git_config_defaults_to_empty_when_not_provided():
    assert ProjectSettings().git == GitConfig()


def test_load_settings_tolerates_a_partial_json_missing_newer_fields(tmp_path):
    """Forward-compatible reads: a hand-edited or older settings.json missing
    some keys still loads, defaulting the rest (§18.2's technically-detailed
    dialog implies users may hand-edit this file)."""
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"name": "bare bones"}', encoding="utf-8")

    settings = load_settings(tmp_path)

    assert settings.name == "bare bones"
    assert settings.pgtp == PgtpLink()
    assert settings.target == ConnectionParams()
    assert settings.git == GitConfig()
    assert settings.deployed == {}


# --- Routine ddl/*.sql path naming (the "_1" suffix scheme) -----------------
def test_sole_holder_routine_gets_the_unsuffixed_name():
    routines = {"pr.recalc()": _routine("pr", "recalc", [])}
    assert routine_ddl_paths(routines) == {"pr.recalc()": "ddl/pr.recalc.sql"}


def test_first_overload_in_signature_order_is_unsuffixed_further_ones_get_1_2():
    routines = {
        "pr.fmt(text)": _routine("pr", "fmt", ["text"]),
        "pr.fmt(integer)": _routine("pr", "fmt", ["integer"]),
        "pr.fmt(integer, text)": _routine("pr", "fmt", ["integer", "text"]),
    }
    paths = routine_ddl_paths(routines)
    # Order is f() < f(integer) < f(integer, text) < f(text) -- shorter tuples
    # first on a common prefix, then lexicographic.
    assert paths["pr.fmt(integer)"] == "ddl/pr.fmt.sql"
    assert paths["pr.fmt(integer, text)"] == "ddl/pr.fmt_1.sql"
    assert paths["pr.fmt(text)"] == "ddl/pr.fmt_2.sql"


def test_zero_arg_overload_sorts_before_any_argument_overload():
    routines = {
        "pr.f(integer)": _routine("pr", "f", ["integer"]),
        "pr.f()": _routine("pr", "f", []),
    }
    paths = routine_ddl_paths(routines)
    assert paths["pr.f()"] == "ddl/pr.f.sql"
    assert paths["pr.f(integer)"] == "ddl/pr.f_1.sql"


def test_ordering_is_independent_of_dict_insertion_order():
    """Never taken from introspection row order -- reversing insertion order
    must not change the assignment (§18.2's load-bearing determinism)."""
    forward = {
        "pr.fmt(integer)": _routine("pr", "fmt", ["integer"]),
        "pr.fmt(text)": _routine("pr", "fmt", ["text"]),
    }
    reversed_ = {
        "pr.fmt(text)": _routine("pr", "fmt", ["text"]),
        "pr.fmt(integer)": _routine("pr", "fmt", ["integer"]),
    }
    assert routine_ddl_paths(forward) == routine_ddl_paths(reversed_)


def test_overloads_are_scoped_per_schema_name_pair():
    routines = {
        "pr.fmt(integer)": _routine("pr", "fmt", ["integer"]),
        "other.fmt(integer)": _routine("other", "fmt", ["integer"]),
    }
    paths = routine_ddl_paths(routines)
    assert paths["pr.fmt(integer)"] == "ddl/pr.fmt.sql"
    assert paths["other.fmt(integer)"] == "ddl/other.fmt.sql"  # unsuffixed too


def test_filename_sanitizes_illegal_windows_characters():
    assert sanitize_filename_component('weird"name') == "weird_name"
    assert sanitize_filename_component("a/b\\c") == "a_b_c"
    assert sanitize_filename_component("q:r*s?") == "q_r_s_"


def test_trigger_path_is_always_table_qualified():
    assert trigger_ddl_path("pr", "orders", "trg_audit") == "ddl/pr.orders.trg_audit.sql"


def test_trigger_path_sanitizes_each_component_independently():
    path = trigger_ddl_path("pr", 'weird"table', "trg")
    assert path == "ddl/pr.weird_table.trg.sql"


# --- Header parsing (identity recovery, never from the filename) -----------
def test_parses_a_zero_arg_function_header():
    text = "CREATE FUNCTION pr.recalc() RETURNS void AS $$\nBEGIN\nEND;\n$$ LANGUAGE plpgsql;"
    assert parse_checked_out_header(text) == "pr.recalc()"


def test_parses_create_or_replace_with_named_arguments():
    text = "CREATE OR REPLACE FUNCTION pr.fmt(a integer, b text) RETURNS text AS $$ ... $$;"
    assert parse_checked_out_header(text) == "pr.fmt(integer, text)"


def test_parses_a_procedure_header():
    text = "CREATE OR REPLACE PROCEDURE pr.do_it(x integer) AS $$ ... $$ LANGUAGE plpgsql;"
    assert parse_checked_out_header(text) == "pr.do_it(integer)"


def test_parses_multi_word_type_without_stripping_the_type_itself():
    text = "CREATE FUNCTION pr.fmt(a character varying) RETURNS text AS $$ $$;"
    assert parse_checked_out_header(text) == "pr.fmt(character varying)"


def test_parses_unnamed_argument_type_unchanged():
    text = "CREATE FUNCTION pr.fmt(integer) RETURNS text AS $$ $$;"
    assert parse_checked_out_header(text) == "pr.fmt(integer)"


def test_does_not_split_a_comma_nested_inside_a_parenthesised_type():
    text = "CREATE FUNCTION pr.fmt(a numeric(10,2)) RETURNS text AS $$ $$;"
    assert parse_checked_out_header(text) == "pr.fmt(numeric(10,2))"


def test_parses_quoted_identifiers():
    text = 'CREATE FUNCTION "My Schema"."My Func"(integer) RETURNS void AS $$ $$;'
    assert parse_checked_out_header(text) == "My Schema.My Func(integer)"


def test_unparseable_header_returns_none_never_a_guess():
    assert parse_checked_out_header("-- not a CREATE statement at all\nSELECT 1;") is None
    assert parse_checked_out_header("") is None


# --- Reconciliation (rename detection, never persisted) ---------------------
def test_reconcile_with_no_existing_files_needs_no_renames():
    routines = {"pr.recalc()": _routine("pr", "recalc", [])}
    result = reconcile_routine_paths(routines, existing_files={})
    assert result.paths == {"pr.recalc()": "ddl/pr.recalc.sql"}
    assert result.renames == ()
    assert result.unparseable == ()


def test_reconcile_matches_existing_file_via_its_header_not_its_path():
    """A file already checked out under the OLD naming still resolves to the
    same signature via its header, even if its current on-disk path
    disagrees with the freshly computed one."""
    routines = {"pr.recalc()": _routine("pr", "recalc", [])}
    existing = {"ddl/pr.recalc.sql": "CREATE FUNCTION pr.recalc() RETURNS void AS $$ $$;"}
    result = reconcile_routine_paths(routines, existing)
    assert result.renames == ()  # already at the correct path


def test_reconcile_detects_a_mid_set_overload_insertion_requiring_a_rename():
    """f(text) was checked out alone as the unsuffixed file. Now f(integer)
    (which sorts BEFORE f(text)) exists too -- f(text) must shift to _1."""
    routines = {
        "pr.fmt(text)": _routine("pr", "fmt", ["text"]),
        "pr.fmt(integer)": _routine("pr", "fmt", ["integer"]),
    }
    existing = {"ddl/pr.fmt.sql": "CREATE FUNCTION pr.fmt(a text) RETURNS text AS $$ $$;"}

    result = reconcile_routine_paths(routines, existing)

    assert result.paths["pr.fmt(integer)"] == "ddl/pr.fmt.sql"
    assert result.paths["pr.fmt(text)"] == "ddl/pr.fmt_1.sql"
    assert result.renames == (("ddl/pr.fmt.sql", "ddl/pr.fmt_1.sql"),)


def test_reconcile_leaves_a_dropped_overloads_file_alone_unrenumbered():
    """fmt_1 (text) is dropped from the live routine set; fmt.sql (integer)
    must NOT be touched or renumbered -- the gap is left in place."""
    routines = {"pr.fmt(integer)": _routine("pr", "fmt", ["integer"])}
    existing = {
        "ddl/pr.fmt.sql": "CREATE FUNCTION pr.fmt(a integer) RETURNS text AS $$ $$;",
        "ddl/pr.fmt_1.sql": "CREATE FUNCTION pr.fmt(a text) RETURNS text AS $$ $$;",
    }

    result = reconcile_routine_paths(routines, existing)

    assert result.renames == ()  # fmt.sql already correct; fmt_1.sql untouched
    assert result.paths == {"pr.fmt(integer)": "ddl/pr.fmt.sql"}


def test_reconcile_appending_a_new_overload_that_sorts_last_needs_no_rename():
    """A brand-new f(text) sorting AFTER the existing f(integer) just takes
    the next free suffix -- no existing file shifts."""
    routines = {
        "pr.fmt(integer)": _routine("pr", "fmt", ["integer"]),
        "pr.fmt(text)": _routine("pr", "fmt", ["text"]),
    }
    existing = {"ddl/pr.fmt.sql": "CREATE FUNCTION pr.fmt(a integer) RETURNS text AS $$ $$;"}

    result = reconcile_routine_paths(routines, existing)

    assert result.renames == ()
    assert result.paths["pr.fmt(text)"] == "ddl/pr.fmt_1.sql"


def test_reconcile_reports_an_unparseable_header_and_does_not_crash():
    routines = {"pr.recalc()": _routine("pr", "recalc", [])}
    existing = {"ddl/pr.recalc.sql": "-- corrupted, no CREATE statement here"}

    result = reconcile_routine_paths(routines, existing)

    assert result.unparseable == ("ddl/pr.recalc.sql",)
    assert result.renames == ()  # the unparseable file cannot be matched to rename


def test_reconciliation_is_a_frozen_dataclass_with_stable_field_names():
    result = Reconciliation(paths={}, renames=(), unparseable=())
    assert result.paths == {}
    assert result.renames == ()
    assert result.unparseable == ()


# --- Content hash ------------------------------------------------------------
def test_content_hash_is_deterministic_for_identical_text():
    assert content_hash("CREATE FUNCTION pr.f() ...") == content_hash("CREATE FUNCTION pr.f() ...")


def test_content_hash_differs_for_different_text():
    assert content_hash("a") != content_hash("b")


def test_content_hash_is_sensitive_to_whitespace():
    """Drift comparisons must not silently treat reformatted-but-equivalent
    text as identical -- the hash is over the raw text, not normalized."""
    assert content_hash("a\n") != content_hash("a\n\n")


# --- DriftMarkers -------------------------------------------------------------
def test_marker_text_empty_when_neither_flag_is_set():
    assert DriftMarkers().marker_text == ""


def test_marker_text_star_for_locally_edited_only():
    assert DriftMarkers(locally_edited=True).marker_text == "*"


def test_marker_text_bang_for_live_drifted_only():
    assert DriftMarkers(live_drifted=True).marker_text == "!"


def test_marker_text_combines_both_never_a_third_symbol():
    assert DriftMarkers(locally_edited=True, live_drifted=True).marker_text == "*!"


# --- compute_drift_markers ---------------------------------------------------
def _schema_with_recalc(source="CREATE FUNCTION pr.recalc() ..."):
    return DatabaseSchema(
        routines={
            "pr.recalc()": _routine("pr", "recalc", [], source=source, kind="function"),
        }
    )


def test_no_entry_for_an_object_never_deployed(tmp_path):
    schema = _schema_with_recalc()
    markers = compute_drift_markers(tmp_path, ProjectSettings(), schema)
    assert markers == {}


def test_no_drift_when_local_file_and_live_definition_both_match(tmp_path):
    source = "CREATE FUNCTION pr.recalc() ..."
    (tmp_path / "ddl").mkdir()
    (tmp_path / "ddl" / "pr.recalc.sql").write_text(source, encoding="utf-8")
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash=content_hash(source))}
    )

    markers = compute_drift_markers(tmp_path, settings, _schema_with_recalc(source))

    assert markers["ddl/pr.recalc.sql"] == DriftMarkers()


def test_star_when_local_file_differs_from_deployed_reference(tmp_path):
    deployed_source = "CREATE FUNCTION pr.recalc() ..."
    (tmp_path / "ddl").mkdir()
    (tmp_path / "ddl" / "pr.recalc.sql").write_text("-- hand-edited\n", encoding="utf-8")
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash=content_hash(deployed_source))}
    )

    markers = compute_drift_markers(tmp_path, settings, _schema_with_recalc(deployed_source))

    assert markers["ddl/pr.recalc.sql"] == DriftMarkers(locally_edited=True)


def test_bang_when_live_definition_differs_from_deployed_reference(tmp_path):
    deployed_source = "CREATE FUNCTION pr.recalc() ..."
    (tmp_path / "ddl").mkdir()
    (tmp_path / "ddl" / "pr.recalc.sql").write_text(deployed_source, encoding="utf-8")
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash=content_hash(deployed_source))}
    )
    live_schema = _schema_with_recalc("CREATE FUNCTION pr.recalc() ... -- changed live")

    markers = compute_drift_markers(tmp_path, settings, live_schema)

    assert markers["ddl/pr.recalc.sql"] == DriftMarkers(live_drifted=True)


def test_both_star_and_bang_when_both_diverge_independently(tmp_path):
    deployed_source = "CREATE FUNCTION pr.recalc() ..."
    (tmp_path / "ddl").mkdir()
    (tmp_path / "ddl" / "pr.recalc.sql").write_text("-- hand-edited\n", encoding="utf-8")
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash=content_hash(deployed_source))}
    )
    live_schema = _schema_with_recalc("CREATE FUNCTION pr.recalc() ... -- changed live")

    markers = compute_drift_markers(tmp_path, settings, live_schema)

    assert markers["ddl/pr.recalc.sql"] == DriftMarkers(locally_edited=True, live_drifted=True)


def test_missing_local_file_is_not_treated_as_locally_edited(tmp_path):
    """Never checked out locally at all -- not the same as "edited"."""
    deployed_source = "CREATE FUNCTION pr.recalc() ..."
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash=content_hash(deployed_source))}
    )

    markers = compute_drift_markers(tmp_path, settings, _schema_with_recalc(deployed_source))

    assert markers["ddl/pr.recalc.sql"].locally_edited is False


def test_object_dropped_from_live_schema_is_not_treated_as_live_drifted(tmp_path):
    """No live definition to compare against -- deliberately not a false
    positive; absence is a separate concern from content drift."""
    deployed_source = "CREATE FUNCTION pr.recalc() ..."
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash=content_hash(deployed_source))}
    )
    empty_schema = DatabaseSchema()

    markers = compute_drift_markers(tmp_path, settings, empty_schema)

    assert markers["ddl/pr.recalc.sql"].live_drifted is False


def test_compute_drift_markers_covers_triggers_too(tmp_path):
    deployed_definition = "CREATE TRIGGER trg_audit AFTER INSERT ON pr.orders ..."
    schema = DatabaseSchema(
        triggers={
            "pr.orders.trg_audit": TriggerInfo(
                schema="pr", table="orders", name="trg_audit", timing="after",
                events=["insert"], definition="CREATE TRIGGER trg_audit ... -- changed",
            )
        }
    )
    settings = ProjectSettings(
        deployed={
            "ddl/pr.orders.trg_audit.sql": DeployedObject(content_hash=content_hash(deployed_definition))
        }
    )

    markers = compute_drift_markers(tmp_path, settings, schema)

    assert markers["ddl/pr.orders.trg_audit.sql"].live_drifted is True


def test_compute_drift_markers_only_covers_deployed_objects(tmp_path):
    """A routine that exists live but was never deployed gets no entry --
    there is nothing recorded to compare it against yet."""
    schema = _schema_with_recalc()
    markers = compute_drift_markers(tmp_path, ProjectSettings(), schema)
    assert "ddl/pr.recalc.sql" not in markers


def test_compute_drift_markers_is_recomputed_fresh_not_cached(tmp_path):
    """Calling it twice with different on-disk content produces different
    results -- nothing here is memoized across calls (§18.2 truth model)."""
    deployed_source = "CREATE FUNCTION pr.recalc() ..."
    (tmp_path / "ddl").mkdir()
    ddl_file = tmp_path / "ddl" / "pr.recalc.sql"
    ddl_file.write_text(deployed_source, encoding="utf-8")
    settings = ProjectSettings(
        deployed={"ddl/pr.recalc.sql": DeployedObject(content_hash=content_hash(deployed_source))}
    )
    schema = _schema_with_recalc(deployed_source)

    first = compute_drift_markers(tmp_path, settings, schema)
    ddl_file.write_text("-- now edited\n", encoding="utf-8")
    second = compute_drift_markers(tmp_path, settings, schema)

    assert first["ddl/pr.recalc.sql"].locally_edited is False
    assert second["ddl/pr.recalc.sql"].locally_edited is True


# --- FQ-260812025353: postgres_bin_dir ---------------------------------------
def test_postgres_bin_dir_defaults_to_empty_meaning_path():
    assert ProjectSettings().postgres_bin_dir == ""


def test_postgres_bin_dir_round_trips_through_the_settings_file(tmp_path):
    save_settings(tmp_path, ProjectSettings(postgres_bin_dir="/opt/pg17/bin"))
    assert load_settings(tmp_path).postgres_bin_dir == "/opt/pg17/bin"


def test_a_settings_file_written_before_the_field_existed_loads_as_path(tmp_path):
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"name": "legacy"}', encoding="utf-8")

    settings = load_settings(tmp_path)

    assert settings.name == "legacy"
    assert settings.postgres_bin_dir == ""


def test_the_binaries_folder_is_written_to_the_gitignored_project_store(tmp_path):
    """A machine-specific absolute path must never travel via git; the store
    that already holds the password is exactly where it belongs."""
    save_settings(tmp_path, ProjectSettings(postgres_bin_dir="/opt/pg17/bin"))

    assert "/opt/pg17/bin" in settings_path(tmp_path).read_text(encoding="utf-8")
    assert SETTINGS_DIRNAME in (tmp_path / ".gitignore").read_text(encoding="utf-8")
