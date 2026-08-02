# tests/db/test_deployment_engine.py
"""The seam between `schema_diff` and `migration_gen` (deployment SQL, §18.3).

The two modules are unit-tested next door; what is checked here is what only
shows up when they are wired together the way Task 4's UI will wire them:
two `DatabaseSchema` objects in, one reviewable script out. Three of this
feature's load-bearing guarantees are only observable end-to-end --

* R14: an argument-type change must reach the script as *create the new
  signature* + *commented DROP of the old one*, never a bare CREATE OR REPLACE
  that leaves the old overload live in production;
* the table/column omission must be visible to the caller (via
  `.unsupported`) at the same time the script is produced, so the refusal and
  the script cannot drift apart;
* byte-determinism has to hold across *processes*, not just across two calls
  in one -- both modules iterate sets, whose order depends on PYTHONHASHSEED.

Pure: canned schemas, no runner, no live database, no Qt widgets.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
)
from pgtp_editor.db.migration_gen import UnsupportedDifference, generate_migration
from pgtp_editor.db.schema_diff import SchemaDifference, diff_schemas

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_MODULES = ("schema_diff.py", "migration_gen.py")


def _routine(name, arg_types=(), source="BODY", language="plpgsql", schema="pr"):
    return RoutineInfo(
        schema=schema,
        name=name,
        arg_types=list(arg_types),
        return_type="void",
        language=language,
        source=source,
    )


def _trigger(name, table="t", definition="CREATE TRIGGER", schema="pr"):
    return TriggerInfo(
        schema=schema,
        table=table,
        name=name,
        timing="before",
        events=["insert"],
        function_name="pr.f",
        definition=definition,
    )


def _schema(routines=(), triggers=(), tables=()):
    return DatabaseSchema(
        tables={t.name: t for t in tables},
        routines={f"{r.schema}.{r.name}#{i}": r for i, r in enumerate(routines)},
        triggers={f"{t.schema}.{t.table}.{t.name}": t for t in triggers},
    )


def _script(source, target, **kwargs):
    return generate_migration(diff_schemas(source, target), **kwargs)


# --- R14 end-to-end: the overload trap --------------------------------------


def test_argument_type_change_creates_the_new_signature_and_only_comments_the_old_drop():
    sandbox = _schema(
        routines=[
            _routine(
                "calc_total",
                ["bigint"],
                source="CREATE OR REPLACE FUNCTION pr.calc_total(bigint)",
            )
        ]
    )
    production = _schema(
        routines=[
            _routine(
                "calc_total",
                ["integer"],
                source="CREATE OR REPLACE FUNCTION pr.calc_total(integer)",
            )
        ]
    )
    sql = _script(sandbox, production)

    assert "CREATE OR REPLACE FUNCTION pr.calc_total(bigint);" in sql
    # The old signature appears only inside the commented review block.
    assert "-- DROP ROUTINE pr.calc_total(integer);" in sql
    for line in sql.splitlines():
        if "calc_total(integer)" in line:
            assert line.startswith("--"), line
    # And nothing pretends the old overload was replaced.
    assert "CREATE OR REPLACE FUNCTION pr.calc_total(integer);" not in sql


def test_two_live_overloads_are_migrated_independently():
    sandbox = _schema(
        routines=[
            _routine("f", ["integer"], source="INT-NEW"),
            _routine("f", ["text"], source="TEXT-SAME"),
        ]
    )
    production = _schema(
        routines=[
            _routine("f", ["integer"], source="INT-OLD"),
            _routine("f", ["text"], source="TEXT-SAME"),
        ]
    )
    sql = _script(sandbox, production)
    assert "INT-NEW;" in sql
    assert "TEXT-SAME" not in sql  # untouched overload is not re-emitted
    assert "REVIEW" not in sql


def test_body_change_of_one_overload_leaves_the_other_out_of_the_script():
    sandbox = _schema(
        routines=[_routine("f", ["integer"], source="A"), _routine("f", ["text"], source="B")]
    )
    production = _schema(
        routines=[_routine("f", ["integer"], source="A"), _routine("f", ["text"], source="B2")]
    )
    (difference,) = diff_schemas(sandbox, production)
    assert difference.identity == "pr.f(text)"
    assert "pr.f(integer)" not in _script(sandbox, production)


# --- the whole pipeline, ordered --------------------------------------------


def test_full_pipeline_orders_routines_then_triggers_then_review_blocks():
    sandbox = _schema(
        routines=[_routine("z", source="RZ"), _routine("a", source="RA")],
        triggers=[_trigger("b_trg", definition="TB"), _trigger("a_trg", definition="TA")],
    )
    production = _schema(routines=[_routine("gone", source="OLD")])
    sql = _script(sandbox, production, header="sandbox -> production")

    positions = [
        sql.index("RA;"),
        sql.index("RZ;"),
        sql.index("TA;"),
        sql.index("TB;"),
        sql.index("-- REVIEW:"),
    ]
    assert positions == sorted(positions)
    assert sql.startswith("-- sandbox -> production\n")
    assert sql.endswith("\n")


def test_pipeline_over_identical_schemas_yields_only_the_header_note():
    schema = _schema(
        routines=[_routine("f", source="F")], triggers=[_trigger("trg", definition="T")]
    )
    sql = _script(schema, schema)
    assert "CREATE" not in sql
    assert "DROP" not in sql
    assert "18.3" in sql  # the "not included" note is always present


def test_pipeline_warns_once_per_emitted_sql_language_routine():
    sandbox = _schema(
        routines=[
            _routine("plain", source="P", language="plpgsql"),
            _routine("sqlish", source="S", language="sql"),
        ]
    )
    sql = _script(sandbox, _schema())
    assert "-- WARNING: 1 non-PL/pgSQL routine(s) are included" in sql


# --- table/column changes are never silently skipped ------------------------


def test_table_differences_never_reach_the_script_but_are_reported_to_the_caller():
    table = TableInfo(
        name="pr.orders",
        kind="table",
        columns=[ColumnInfo("id", "integer", True, False, False, None)],
    )
    sandbox = _schema(routines=[_routine("f", source="F")], tables=[table])
    production = _schema(tables=[])

    result = diff_schemas(sandbox, production)
    sql = generate_migration(result)

    assert "pr.orders" not in sql  # not emitted as DDL...
    assert result.unsupported == ["pr.orders"]  # ...but the caller is told
    assert "table and column changes are NOT included" in sql


def test_a_table_difference_fed_to_the_generator_refuses_the_whole_script():
    # Task 4's caller must never be able to paper over a table change by mixing
    # it into a routine batch: the refusal wins, no partial script is produced.
    differences = [
        SchemaDifference("changed", "routine", "pr.f()", "OLD", "NEW", "plpgsql"),
        SchemaDifference("added", "column", "pr.orders.total", None, "numeric"),
    ]
    with pytest.raises(UnsupportedDifference) as excinfo:
        generate_migration(differences)
    assert "pr.orders.total" in str(excinfo.value)


def test_caller_can_report_the_omission_after_filtering_the_slice_it_shows():
    # The realistic UI path: take the sidecar and a subset of the differences.
    tables = [TableInfo(name="pr.a", kind="table", columns=[])]
    sandbox = _schema(
        routines=[_routine("f", source="F"), _routine("g", source="G")], tables=tables
    )
    result = diff_schemas(sandbox, _schema())
    shown = result[:1]
    assert shown.unsupported == ["pr.a"]
    sql = generate_migration(shown)
    assert "F;" in sql
    assert "G;" not in sql
    assert "table and column changes are NOT included" in sql


# --- determinism across processes -------------------------------------------

_DETERMINISM_SCRIPT = """
import sys
sys.path.insert(0, {repo!r})
from pgtp_editor.db.introspect import DatabaseSchema, RoutineInfo, TableInfo, TriggerInfo
from pgtp_editor.db.schema_diff import diff_schemas
from pgtp_editor.db.migration_gen import generate_migration

def routine(name, args, src, lang="plpgsql"):
    return RoutineInfo("pr", name, list(args), "void", lang, src)

def trigger(name, table, definition):
    return TriggerInfo("pr", table, name, "before", ["insert"], "pr.f", definition)

names = ["m", "a", "z", "q", "b", "k"]
src_routines = [routine(n, ["integer"], "NEW-" + n) for n in names]
src_routines.append(routine("sqlish", [], "SQLISH", "sql"))
tgt_routines = [routine(n, ["integer"], "OLD-" + n) for n in names[:3]]
tgt_routines.append(routine("gone", [], "GONE"))
src_triggers = [trigger("t" + n, "tbl" + n, "TRG-" + n) for n in names]
tables = [TableInfo("pr." + n, "table", []) for n in names]

source = DatabaseSchema(
    tables={{t.name: t for t in tables}},
    routines={{"%s#%d" % (r.name, i): r for i, r in enumerate(src_routines)}},
    triggers={{"%s.%s" % (t.table, t.name): t for t in src_triggers}},
)
target = DatabaseSchema(
    tables={{}},
    routines={{"%s#%d" % (r.name, i): r for i, r in enumerate(tgt_routines)}},
    triggers={{}},
)
result = diff_schemas(source, target)
sys.stdout.write(generate_migration(result, header="h") + "|" + ",".join(result.unsupported))
"""


def _run_engine(hash_seed: str) -> str:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, "-c", _DETERMINISM_SCRIPT.format(repo=str(REPO_ROOT))],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=50,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_output_is_byte_identical_across_processes_with_different_hash_seeds():
    # Both modules iterate sets (`set(source) | set(target)`, the unsupported
    # union); set order varies with PYTHONHASHSEED, so an in-process "run it
    # twice" check cannot see a non-deterministic ordering. This can.
    first = _run_engine("0")
    second = _run_engine("12345")
    assert first != ""
    assert first.encode("utf-8") == second.encode("utf-8")


# --- purity: no Qt, no psycopg, no upward imports ---------------------------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.add("." * node.level + (node.module or ""))
            elif node.module:
                found.add(node.module)
    return found


@pytest.mark.parametrize("module_name", ENGINE_MODULES)
def test_engine_module_imports_no_qt_no_driver_and_not_db_config(module_name):
    # `db/config.py` imports QSettings, so reaching for it -- even for
    # `ConnectionParams` -- would drag Qt into the engine; `connection_summary`
    # is duck-typed for exactly this reason.
    imported = _imported_modules(REPO_ROOT / "pgtp_editor" / "db" / module_name)
    forbidden = {"PySide6", "PyQt5", "PyQt6", "psycopg", "psycopg2", "socket", "urllib"}
    assert {name for name in imported if name.split(".")[0] in forbidden} == set()
    assert ".config" not in imported
    assert "pgtp_editor.db.config" not in imported
    for name in imported:
        assert not name.startswith("pgtp_editor.ui"), name
        assert ".ui" not in name, name


@pytest.mark.parametrize("module_name", ENGINE_MODULES)
def test_engine_module_does_no_file_or_clock_access(module_name):
    # "Deterministic, caller supplies the timestamp" is only true if the
    # modules cannot read a clock or the filesystem themselves.
    imported = _imported_modules(REPO_ROOT / "pgtp_editor" / "db" / module_name)
    for banned in ("datetime", "time", "pathlib", "os", "io"):
        assert banned not in imported, (module_name, banned)


def _fresh_import_loads(top_level_packages: tuple[str, ...]) -> str:
    """Import both engine modules in a *fresh* interpreter and report which of
    `top_level_packages` ended up in `sys.modules`.

    The static `_imported_modules` checks above read only each module's own
    `import` lines, so a *transitive* edge -- `schema_diff` -> `introspect` ->
    `config` -> `QSettings` -- is structurally invisible to them. Only a real
    import in a clean process can see it.
    """
    script = (
        "import sys\n"
        "import pgtp_editor.db.schema_diff, pgtp_editor.db.migration_gen\n"
        f"print(sorted({{m.split('.')[0] for m in sys.modules}} "
        f"& set({top_level_packages!r})))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=50,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_importing_the_engine_in_a_fresh_interpreter_loads_no_psycopg():
    assert _fresh_import_loads(("psycopg", "psycopg2")) == "[]"


def test_importing_the_engine_in_a_fresh_interpreter_loads_no_pyside6():
    # `schema_diff` uses `DatabaseSchema`/`RoutineInfo`/`TriggerInfo` in
    # annotations only, so its `.introspect` import is `TYPE_CHECKING`-guarded
    # -- otherwise it pulls in `db/config.py`'s module-scope `QSettings` and
    # both modules' "Pure: no Qt" docstrings become false.
    assert _fresh_import_loads(("PySide6", "shiboken6")) == "[]"
