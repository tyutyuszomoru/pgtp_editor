"""Tests for `pgtp_editor.db.pg_dump_ddl` -- the FULL-mode DDL layer
(`FQ-260812022749` Part 3).

**No test here spawns a process or reaches a server.** The dump below is
captured `pg_dump --schema-only` output shape, fed to the pure parser; the one
subprocess (`fetch_schema_dump`) is exercised through the injectable
`ProcessRunner` seam that `db/sandbox.py::clone_data` already uses.
"""
import pytest

from pgtp_editor.db.config import ConnectionParams
from pgtp_editor.db.pg_dump_ddl import (
    KIND_CONSTRAINT,
    KIND_INDEX,
    KIND_OTHER,
    KIND_RELATION_EXTRA,
    KIND_ROUTINE,
    KIND_TABLE,
    KIND_VIEW,
    PG_DUMP_SCHEMA_ONLY_ARGS,
    SchemaDumpError,
    fetch_schema_dump,
    parse_pg_dump,
    split_statements,
    unquote_ident,
)

#: A whole-database `pg_dump --schema-only`, in the shape a real one has: a
#: comment/`SET` preamble, one contiguous `CREATE TABLE`, the owned sequence in
#: a DIFFERENT section from the table it belongs to, constraints as standalone
#: `ALTER TABLE ONLY … ADD CONSTRAINT`, a CHECK constraint left INLINE, a
#: dollar-quoted function body containing a semicolon, and a string literal
#: containing one too.
DUMP = '''--
-- PostgreSQL database dump
--

-- Dumped from database version 16.2
-- Dumped by pg_dump version 16.2

SET statement_timeout = 0;
SET client_encoding = 'UTF8';
SELECT pg_catalog.set_config('search_path', '', false);

--
-- Name: pr; Type: SCHEMA; Schema: -; Owner: pg
--

CREATE SCHEMA pr;

--
-- Name: orders; Type: TABLE; Schema: pr; Owner: pg
--

CREATE TABLE pr.orders (
    id integer NOT NULL,
    tag text,
    "Odd Name" text,
    CONSTRAINT orders_tag_check CHECK ((tag <> ''::text))
);

--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: pr; Owner: pg
--

CREATE SEQUENCE pr.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    CACHE 1;

ALTER SEQUENCE pr.orders_id_seq OWNED BY pr.orders.id;

ALTER TABLE ONLY pr.orders ALTER COLUMN id SET DEFAULT nextval('pr.orders_id_seq'::regclass);

--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: pr; Owner: pg
--

ALTER TABLE ONLY pr.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);

CREATE INDEX ix_tag ON pr.orders USING btree (tag);

COMMENT ON TABLE pr.orders IS 'orders; with a semicolon';

CREATE VIEW pr.v_orders AS
 SELECT orders.id,
    orders.tag
   FROM pr.orders;

CREATE MATERIALIZED VIEW pr.m_orders AS
 SELECT orders.id
   FROM pr.orders
  WITH NO DATA;

CREATE FUNCTION pr.calc(x integer) RETURNS integer
    LANGUAGE plpgsql
    AS $$begin return x; end;$$;

CREATE TRIGGER trg AFTER INSERT ON pr.orders FOR EACH ROW EXECUTE FUNCTION pr.calc();
'''


def _kinds(text=DUMP):
    return [statement.kind for statement in parse_pg_dump(text).statements]


# ---------------------------------------------------------------------------
# Statement splitting -- the crux: each statement is individually contiguous.
# ---------------------------------------------------------------------------

def test_a_semicolon_inside_a_string_literal_does_not_end_a_statement():
    statements = split_statements("COMMENT ON TABLE t IS 'a; b';\nSELECT 1;\n")
    assert statements == [["COMMENT ON TABLE t IS 'a; b';"], ["SELECT 1;"]]


def test_a_semicolon_inside_a_dollar_quoted_body_does_not_end_a_statement():
    body = (
        "CREATE FUNCTION f() RETURNS void\n"
        "    LANGUAGE plpgsql\n"
        "    AS $$\n"
        "begin\n"
        "  perform 1;\n"
        "end;\n"
        "$$;\n"
    )
    assert split_statements(body) == [body.splitlines()]


def test_a_tagged_dollar_quote_is_matched_by_ITS_OWN_tag():
    """`$body$ … $$ … $body$` -- an inner `$$` must not close a `$body$`
    block, or every routine using both spellings would split mid-body."""
    text = "CREATE FUNCTION f() RETURNS void AS $body$ select '$$'; $body$;\n"
    assert split_statements(text) == [text.splitlines()]


def test_comment_only_blocks_between_statements_are_dropped():
    """`pg_dump`'s `-- Name: …; Type: TABLE; …` headers and the volatile
    `-- Dumped by pg_dump version …` banner. The buffer writes its own banner
    per object, and the version line is the single most version-dependent text
    in the file."""
    statements = split_statements(DUMP)
    assert all("Dumped by pg_dump" not in "\n".join(block) for block in statements)
    assert all("-- Name:" not in "\n".join(block) for block in statements)


def test_a_comment_INSIDE_a_statement_stays_with_it():
    text = "CREATE TABLE t (\n    id integer -- the key\n);\n"
    assert split_statements(text) == [text.splitlines()]


def test_a_truncated_unterminated_tail_is_still_reported_not_swallowed():
    """Evidence of a truncated dump must survive the split -- the caller's
    attribution check is what decides to refuse, and it cannot decide about
    text this function ate."""
    statements = split_statements("CREATE TABLE t (\n    id integer\n")
    assert statements == [["CREATE TABLE t (", "    id integer"]]


def test_blank_input_yields_no_statements():
    assert split_statements("") == []
    assert parse_pg_dump("").empty


# ---------------------------------------------------------------------------
# Classification and attribution
# ---------------------------------------------------------------------------

def test_every_statement_kind_in_a_real_dump_is_classified():
    assert _kinds() == [
        KIND_OTHER,  # SET statement_timeout
        KIND_OTHER,  # SET client_encoding
        KIND_OTHER,  # SELECT set_config
        KIND_OTHER,  # CREATE SCHEMA
        KIND_TABLE,
        KIND_OTHER,  # CREATE SEQUENCE -- a DIFFERENT section from its table
        KIND_OTHER,  # ALTER SEQUENCE … OWNED BY
        KIND_RELATION_EXTRA,  # ALTER COLUMN … SET DEFAULT nextval(…)
        KIND_CONSTRAINT,
        KIND_INDEX,
        KIND_RELATION_EXTRA,  # COMMENT ON TABLE
        KIND_VIEW,
        "matview",
        KIND_ROUTINE,  # CREATE FUNCTION
        KIND_ROUTINE,  # CREATE TRIGGER
    ]


def test_relations_are_keyed_by_their_CATALOG_spelling():
    """`creates` is keyed exactly as `DatabaseSchema.tables` is, so attributing
    a relation is a dict lookup rather than a second name-rendering."""
    parsed = parse_pg_dump(DUMP)
    assert set(parsed.creates) == {"pr.orders", "pr.v_orders", "pr.m_orders"}


def test_constraints_and_indexes_attach_to_their_owning_relation():
    parsed = parse_pg_dump(DUMP)
    attached = parsed.attachments["pr.orders"]
    assert (KIND_CONSTRAINT, "orders_pkey") in [(s.kind, s.name) for s in attached]
    assert (KIND_INDEX, "ix_tag") in [(s.kind, s.name) for s in attached]


def test_a_multi_line_add_constraint_statement_is_ONE_contiguous_span():
    """The whole point of the statement-boundary approach: `pg_dump` wraps
    `ALTER TABLE ONLY x` / `    ADD CONSTRAINT …` onto two lines, and both
    belong to the constraint."""
    parsed = parse_pg_dump(DUMP)
    pkey = next(
        s for s in parsed.statements
        if s.kind == KIND_CONSTRAINT and s.name == "orders_pkey"
    )
    assert pkey.lines == (
        "ALTER TABLE ONLY pr.orders",
        "    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);",
    )


def test_routines_and_triggers_are_recognised_and_kept_OUT_of_the_indexes():
    """They are rendered from the catalog instead (`RoutineInfo.signature` has
    exactly one source and is never re-rendered -- BUG-018)."""
    parsed = parse_pg_dump(DUMP)
    assert all(s.kind != KIND_ROUTINE for s in parsed.other)
    assert all(
        s.kind != KIND_ROUTINE
        for statements in parsed.attachments.values()
        for s in statements
    )


def test_unrecognised_statements_land_in_other_verbatim_rather_than_vanishing():
    """The bucket is a catch-all, not a whitelist: a statement kind PostgreSQL
    adds later must still reach the reader."""
    parsed = parse_pg_dump("CREATE FUTURE THING pr.x WITH (magic);\n")
    assert [s.kind for s in parsed.statements] == [KIND_OTHER]
    assert parsed.other[0].lines == ("CREATE FUTURE THING pr.x WITH (magic);",)


def test_a_literal_that_LOOKS_like_a_statement_head_does_not_reclassify():
    """Classification is anchored at the statement start, so a decoy inside a
    comment string cannot make a `COMMENT ON` look like a `CREATE TABLE`."""
    parsed = parse_pg_dump("COMMENT ON TABLE pr.t IS 'CREATE TABLE pr.decoy (';\n")
    assert [s.kind for s in parsed.statements] == [KIND_RELATION_EXTRA]
    assert parsed.creates == {}


@pytest.mark.parametrize(
    "statement, kind, relation",
    [
        ("CREATE UNLOGGED TABLE pr.t (id integer);", KIND_TABLE, "pr.t"),
        ("CREATE UNIQUE INDEX ix ON pr.t USING btree (id);", KIND_INDEX, "pr.t"),
        ("ALTER TABLE pr.t ENABLE ROW LEVEL SECURITY;", KIND_RELATION_EXTRA, "pr.t"),
        ("ALTER TABLE ONLY pr.t ATTACH PARTITION pr.t1 DEFAULT;", KIND_RELATION_EXTRA, "pr.t"),
        ("COMMENT ON COLUMN pr.t.id IS 'x';", KIND_RELATION_EXTRA, "pr.t"),
        ("CREATE POLICY p ON pr.t USING (true);", KIND_RELATION_EXTRA, "pr.t"),
    ],
)
def test_the_other_shapes_a_real_dump_emits(statement, kind, relation):
    parsed = parse_pg_dump(statement + "\n")
    assert (parsed.statements[0].kind, parsed.statements[0].relation) == (kind, relation)


def test_a_partitioned_table_is_attributed_like_any_other():
    """The whole reason full mode exists: the synthesized renderer cannot
    express `PARTITION BY`, and `pg_dump` simply does."""
    parsed = parse_pg_dump(
        "CREATE TABLE pr.events (\n"
        "    id integer NOT NULL,\n"
        "    at date NOT NULL\n"
        ")\nPARTITION BY RANGE (at);\n"
    )
    create = parsed.creates["pr.events"]
    assert "PARTITION BY RANGE (at);" in create.lines
    assert set(create.column_offsets) == {"id", "at"}


# ---------------------------------------------------------------------------
# Column / inline-constraint offsets inside one `CREATE TABLE`
# ---------------------------------------------------------------------------

def test_column_offsets_point_at_the_line_that_renders_each_column():
    create = parse_pg_dump(DUMP).creates["pr.orders"]
    for name, offset in create.column_offsets.items():
        assert name in create.lines[offset]


def test_a_quoted_column_name_is_unquoted_to_its_catalog_spelling():
    """Span identities are catalog names; `pg_dump` writes the SQL spelling."""
    create = parse_pg_dump(DUMP).creates["pr.orders"]
    assert "Odd Name" in create.column_offsets
    assert '"Odd Name"' not in create.column_offsets


def test_an_INLINE_check_constraint_gets_an_offset_of_its_own():
    """`pg_dump` splits constraints across two shapes -- CHECK stays inside the
    `CREATE TABLE`, PK/UNIQUE/FK come out as `ALTER TABLE … ADD CONSTRAINT`. A
    parser handling only the second leaves every CHECK unnavigable."""
    create = parse_pg_dump(DUMP).creates["pr.orders"]
    assert set(create.constraint_offsets) == {"orders_tag_check"}
    assert "orders_tag_check" not in create.column_offsets


def test_a_column_QUOTED_as_a_constraint_keyword_is_still_a_column():
    """The quotes are the only thing separating the keyword from a legal
    column name, which is why the test is on the raw token."""
    create = parse_pg_dump(
        'CREATE TABLE pr.t (\n    "CONSTRAINT" text,\n    id integer\n);\n'
    ).creates["pr.t"]
    assert set(create.column_offsets) == {"CONSTRAINT", "id"}
    assert create.constraint_offsets == {}


def test_a_table_with_no_columns_yields_no_offsets():
    create = parse_pg_dump("CREATE TABLE pr.t ();\n").creates["pr.t"]
    assert create.column_offsets == {}


def test_a_type_with_parentheses_does_not_shift_the_offsets():
    create = parse_pg_dump(
        "CREATE TABLE pr.t (\n"
        "    code character varying(20) NOT NULL,\n"
        "    amount numeric(12,2) DEFAULT 0,\n"
        "    tag text\n"
        ");\n"
    ).creates["pr.t"]
    assert create.column_offsets == {"code": 1, "amount": 2, "tag": 3}


# ---------------------------------------------------------------------------
# Purity -- what full mode has INSTEAD of restricted mode's proven determinism
# ---------------------------------------------------------------------------

def test_the_parser_is_pure_same_text_in_identical_statements_out():
    """End-to-end byte-identity in full mode is an ENVIRONMENTAL assumption
    (`pg_dump`'s output varies with the client's version, which no test of ours
    can make untrue). The parser's purity is the part that IS provable, so it
    is pinned here rather than assumed."""
    first = parse_pg_dump(DUMP)
    second = parse_pg_dump(DUMP)
    assert first.statements == second.statements
    assert first.creates == second.creates
    assert first.attachments == second.attachments
    assert first.other == second.other


def test_unquote_ident_round_trips_the_spellings_pg_dump_writes():
    assert unquote_ident("orders") == "orders"
    assert unquote_ident('"Odd Name"') == "Odd Name"
    assert unquote_ident('"say ""hi"""') == 'say "hi"'


# ---------------------------------------------------------------------------
# The ONE subprocess, through the injectable seam
# ---------------------------------------------------------------------------

def _params():
    return ConnectionParams(
        host="db.example", port=5432, database="quality", user="pg", password="s3cret"
    )


class _Result:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_fetch_schema_dump_issues_ONE_whole_database_invocation():
    """One dump per Explorer build -- never per-table `-t`, which would cost a
    subprocess per table against a buffer §18.1 settled as having no cache AND
    would omit the table's owned sequence."""
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _Result(stdout=b"CREATE SCHEMA pr;\n")

    text = fetch_schema_dump(_params(), "/opt/pg/bin/pg_dump", run=run)

    assert text == "CREATE SCHEMA pr;\n"
    assert len(calls) == 1
    argv = calls[0][0]
    assert argv[0] == "/opt/pg/bin/pg_dump"
    assert "-t" not in argv and not any(a.startswith("--table") for a in argv)
    for flag in PG_DUMP_SCHEMA_ONLY_ARGS:
        assert flag in argv


def test_comments_are_NOT_suppressed():
    """`--no-comments` would drop the `COMMENT ON` statements the RESTRICTED
    renderer emits today, making full mode less complete than restricted mode
    in one respect."""
    assert "--no-comments" not in PG_DUMP_SCHEMA_ONLY_ARGS


def test_the_password_never_reaches_argv():
    captured = {}

    def run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs.get("env") or {}
        return _Result(stdout=b"")

    fetch_schema_dump(_params(), "pg_dump", run=run)

    assert "s3cret" not in " ".join(captured["argv"])
    assert captured["env"]["PGPASSWORD"] == "s3cret"


def test_a_nonzero_exit_is_a_NAMED_refusal_carrying_stderr():
    def run(argv, **kwargs):
        return _Result(returncode=1, stderr=b"aborting because of server version mismatch")

    with pytest.raises(SchemaDumpError) as excinfo:
        fetch_schema_dump(_params(), "pg_dump", run=run)
    assert excinfo.value.returncode == 1
    assert "server version mismatch" in str(excinfo.value)


def test_a_timeout_or_spawn_failure_is_the_same_named_refusal():
    def run(argv, **kwargs):
        raise OSError("no such file")

    with pytest.raises(SchemaDumpError) as excinfo:
        fetch_schema_dump(_params(), "pg_dump", run=run)
    assert "no such file" in str(excinfo.value)


def test_a_timeout_is_passed_to_the_runner_so_an_expiry_can_degrade():
    captured = {}

    def run(argv, **kwargs):
        captured.update(kwargs)
        return _Result(stdout=b"")

    fetch_schema_dump(_params(), "pg_dump", run=run, timeout=7)
    assert captured["timeout"] == 7
