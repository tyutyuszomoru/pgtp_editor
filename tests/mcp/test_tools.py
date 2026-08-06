# tests/mcp/test_tools.py
"""Unit tests for the §23 MCP tool adapter.

No live database and no live GUI: the model comes from real `.pgtp` files
written to tmp_path (or from a fake "live" provider), and the database tools
get an injected introspector returning canned `DatabaseSchema` objects — the
same discipline `tests/db/test_introspect.py` applies with `runner=`.
"""
import json

import pytest

from pgtp_editor.db.introspect import (
    ColumnInfo,
    DatabaseSchema,
    RoutineInfo,
    TableInfo,
    TriggerInfo,
)
from pgtp_editor.mcp.providers import (
    FileProjectProvider,
    LiveProjectProvider,
    ProjectUnavailableError,
)
from pgtp_editor.mcp.tools import ToolArgumentError, UnknownToolError, build_registry
from pgtp_editor.model.parser import load_project

PROJECT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="orders.php" tableName="sales.orders" caption="Orders">
        <ColumnPresentations>
          <ColumnPresentation fieldName="id" caption="ID"/>
          <ColumnPresentation fieldName="customer_id" caption="Customer">
            <Lookup tableName="sales.customers" fieldName="name"/>
          </ColumnPresentation>
        </ColumnPresentations>
        <EventHandlers>
          <OnBeforePageLoad>echo 'hi';</OnBeforePageLoad>
        </EventHandlers>
        <Details>
          <Detail caption="Lines">
            <Page fileName="lines.php" tableName="sales.order_lines" caption="Lines"/>
          </Detail>
        </Details>
      </Page>
      <Page fileName="customers.php" tableName="sales.customers" caption="Customers"/>
    </Pages>
  </Presentation>
</Project>
"""

OTHER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Presentation>
    <Pages>
      <Page fileName="orders.php" tableName="sales.orders" caption="Order list"/>
    </Pages>
  </Presentation>
</Project>
"""

SECRET = "hunter2-do-not-leak"
CONNECTION = {
    "host": "db.example.org",
    "port": "5432",
    "database": "erp",
    "user": "botond",
    "password": SECRET,
}


@pytest.fixture
def project_path(tmp_path):
    path = tmp_path / "demo.pgtp"
    path.write_text(PROJECT_XML, encoding="utf-8")
    return str(path)


@pytest.fixture
def other_path(tmp_path):
    path = tmp_path / "other.pgtp"
    path.write_text(OTHER_XML, encoding="utf-8")
    return str(path)


def _schema():
    """A canned two-object schema — no database, no psycopg."""
    return DatabaseSchema(
        tables={
            "sales.orders": TableInfo(
                name="sales.orders",
                kind="table",
                columns=[
                    ColumnInfo("id", "integer", True, False, False, None),
                    ColumnInfo(
                        "customer_id", "integer", False, True, True, None,
                        fk_target="sales.customers.id", comment="owner",
                    ),
                ],
            ),
            "sales.open_orders": TableInfo(
                name="sales.open_orders",
                kind="view",
                columns=[],
                view_definition="SELECT 1",
            ),
        },
        routines={
            "sales.recalc(integer)": RoutineInfo(
                schema="sales",
                name="recalc",
                arg_types=["integer"],
                return_type="void",
                language="plpgsql",
                source="CREATE FUNCTION sales.recalc(integer) ...",
                kind="function",
                args=[("order_id", "integer")],
            )
        },
        triggers={
            "sales.orders.trg_touch": TriggerInfo(
                schema="sales",
                table="orders",
                name="trg_touch",
                timing="before",
                events=["insert", "update"],
                function_name="sales.touch",
                definition="CREATE TRIGGER trg_touch ...",
            )
        },
    )


def _registry(**kwargs):
    kwargs.setdefault("introspector", lambda params: _schema())
    return build_registry(FileProjectProvider(), **kwargs)


# ---------------------------------------------------------------------------
# the six tools
# ---------------------------------------------------------------------------

def test_registry_serves_exactly_the_six_spec_tools():
    assert sorted(_registry().names) == [
        "diff_projects",
        "get_node",
        "list_db_routines",
        "list_db_tables",
        "list_pages",
        "read_project",
    ]


def test_read_project_returns_pages_and_referenced_tables(project_path):
    result = _registry().call("read_project", {"path": project_path})

    assert result["path"] == project_path
    assert result["page_count"] == 2
    orders = result["pages"][0]
    assert orders["identity"] == "orders.php"
    assert orders["table_name"] == "sales.orders"
    assert orders["column_count"] == 2
    assert orders["detail_count"] == 1
    assert orders["event_count"] == 1
    assert [t["name"] for t in result["tables"]] == [
        "sales.customers",
        "sales.order_lines",
        "sales.orders",
    ]
    customers = next(t for t in result["tables"] if t["name"] == "sales.customers")
    assert customers["reference_count"] == 2
    assert "Column 'customer_id' (lookup)" in customers["references"][0]["breadcrumb"]


def test_list_pages_returns_summaries_only(project_path):
    result = _registry().call("list_pages", {"path": project_path})

    assert [p["file_name"] for p in result["pages"]] == ["orders.php", "customers.php"]
    assert all("columns" not in p for p in result["pages"])


def test_get_node_returns_page_with_children(project_path):
    result = _registry().call(
        "get_node", {"path": project_path, "identity": "orders.php"}
    )
    node = result["node"]

    assert node["kind"] == "page"
    assert node["attrib"]["caption"] == "Orders"
    assert [c["field_name"] for c in node["columns"]] == ["id", "customer_id"]
    assert [d["identity"] for d in node["details"]] == ["orders.php/sales.order_lines"]


def test_get_node_finds_nested_column_detail_and_event(project_path):
    registry = _registry()

    column = registry.call(
        "get_node", {"path": project_path, "identity": "orders.php/customer_id"}
    )["node"]
    assert column["kind"] == "column"
    assert column["lookup"]["attrib"]["tableName"] == "sales.customers"

    detail = registry.call(
        "get_node",
        {"path": project_path, "identity": "orders.php/sales.order_lines"},
    )["node"]
    assert detail["kind"] == "detail"

    event = registry.call(
        "get_node", {"path": project_path, "identity": "orders.php/OnBeforePageLoad"}
    )["node"]
    assert event["kind"] == "event"
    assert event["side"] == "C"
    assert event["text"] == "echo 'hi';"


def test_get_node_unknown_identity_is_an_argument_error(project_path):
    with pytest.raises(ToolArgumentError, match="no node with identity"):
        _registry().call("get_node", {"path": project_path, "identity": "nope"})


def test_diff_projects_reports_the_caption_change(project_path, other_path):
    result = _registry().call(
        "diff_projects", {"source": project_path, "target": other_path}
    )

    assert result["source"] == project_path
    assert result["target"] == other_path
    changed = [d for d in result["differences"] if d["attribute"] == "caption"]
    assert changed[0]["kind"] == "changed"
    # differ.py's convention: old_value is the TARGET's value, new_value the
    # SOURCE's (see _compare_attributes) -- passed through verbatim.
    assert changed[0]["old_value"] == "Order list"
    assert changed[0]["new_value"] == "Orders"
    # customers.php exists only in the source -> "added", carrying the whole
    # PageNode, which serializes to its page summary rather than a repr.
    added = [d for d in result["differences"] if d["kind"] == "added"]
    assert any(
        isinstance(d["new_value"], dict)
        and d["new_value"].get("file_name") == "customers.php"
        for d in added
    )


def test_list_db_tables_returns_tables_with_columns():
    result = _registry().call("list_db_tables", {"connection": CONNECTION})

    assert result["connection"] == "botond@db.example.org:5432/erp"
    assert result["table_count"] == 2
    assert [t["name"] for t in result["tables"]] == [
        "sales.open_orders",
        "sales.orders",
    ]
    orders = result["tables"][1]
    assert orders["kind"] == "table"
    assert orders["columns"][1]["fk_target"] == "sales.customers.id"
    assert orders["columns"][1]["comment"] == "owner"


def test_list_db_routines_returns_routines_and_triggers():
    result = _registry().call("list_db_routines", {"connection": CONNECTION})

    assert result["connection"] == "botond@db.example.org:5432/erp"
    assert result["routine_count"] == 1
    routine = result["routines"][0]
    assert routine["signature"] == "sales.recalc(integer)"
    assert routine["args"] == [["order_id", "integer"]]
    assert result["triggers"][0]["events"] == ["insert", "update"]


def test_db_tools_pass_the_real_connection_params_to_the_introspector():
    seen = {}

    def introspector(params):
        seen["params"] = params
        return _schema()

    build_registry(FileProjectProvider(), introspector=introspector).call(
        "list_db_tables", {"connection": CONNECTION}
    )

    assert seen["params"].host == "db.example.org"
    assert seen["params"].password == SECRET  # reaches the driver, never the wire


# ---------------------------------------------------------------------------
# password never leaves
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool", ["list_db_tables", "list_db_routines"])
def test_no_password_in_any_serialized_db_output(tool):
    payload = _registry().call(tool, {"connection": CONNECTION})
    assert SECRET not in json.dumps(payload, default=str)


def test_no_password_in_tool_descriptors_or_error_text():
    registry = _registry()
    assert SECRET not in json.dumps(registry.descriptors())

    with pytest.raises(ToolArgumentError) as excinfo:
        registry.call("list_db_tables", {"connection": {**CONNECTION, "sslmode": "x"}})
    assert SECRET not in str(excinfo.value)


def test_connection_params_repr_hides_the_password():
    from pgtp_editor.mcp.tools import _connection_from

    params = _connection_from(CONNECTION)
    assert SECRET not in repr(params)


# ---------------------------------------------------------------------------
# argument handling
# ---------------------------------------------------------------------------

def test_unknown_tool_name_is_rejected_cleanly():
    with pytest.raises(UnknownToolError) as excinfo:
        _registry().call("drop_everything", {})
    assert "drop_everything" in str(excinfo.value)


def test_missing_required_argument_is_rejected():
    with pytest.raises(ToolArgumentError, match="missing required argument"):
        _registry().call("diff_projects", {"source": "a.pgtp"})


def test_unexpected_argument_is_rejected():
    with pytest.raises(ToolArgumentError, match="unexpected argument"):
        _registry().call("list_pages", {"path": "a.pgtp", "sql": "DROP TABLE t"})


def test_connection_must_be_an_object():
    with pytest.raises(ToolArgumentError, match="must be an object"):
        _registry().call("list_db_tables", {"connection": "postgres://x"})


# ---------------------------------------------------------------------------
# providers: headless vs. shared live model
# ---------------------------------------------------------------------------

def test_headless_provider_requires_a_path():
    with pytest.raises(ProjectUnavailableError, match="required"):
        _registry().call("list_pages", {})


def test_headless_provider_rejects_a_missing_file(tmp_path):
    with pytest.raises(ProjectUnavailableError, match="no such"):
        _registry().call("list_pages", {"path": str(tmp_path / "gone.pgtp")})


def test_live_provider_shares_the_open_model_without_a_path(project_path):
    open_project = load_project(project_path)
    provider = LiveProjectProvider(lambda: ("/somewhere/open.pgtp", open_project))
    registry = build_registry(provider, introspector=lambda p: _schema())

    result = registry.call("list_pages", {})

    assert result["path"] == "/somewhere/open.pgtp"
    assert result["page_count"] == 2


def test_live_provider_falls_back_to_the_file_for_another_path(project_path, other_path):
    open_project = load_project(other_path)
    provider = LiveProjectProvider(lambda: (other_path, open_project))
    registry = build_registry(provider, introspector=lambda p: _schema())

    result = registry.call("list_pages", {"path": project_path})

    assert result["path"] == project_path
    assert result["page_count"] == 2


def test_live_provider_with_nothing_open_behaves_like_headless(project_path):
    provider = LiveProjectProvider(lambda: (None, None))
    registry = build_registry(provider, introspector=lambda p: _schema())

    assert registry.call("list_pages", {"path": project_path})["page_count"] == 2
    with pytest.raises(ProjectUnavailableError):
        registry.call("list_pages", {})
