"""Tests for pgtp_editor.db.table_ddl -- the pure `CREATE TABLE` / `CREATE VIEW`
synthesizer (`FQ-260810183812`, §18.1).

No database is reached: the module formats already-introspected rows, which is
exactly why every reconstruction branch is testable here.
"""
from pgtp_editor.db.introspect import ColumnInfo, ConstraintInfo, IndexInfo, TableInfo
from pgtp_editor.db.table_ddl import (
    RECONSTRUCTION_NOTICE,
    RECONSTRUCTION_NOTICE_DETAIL,
    build_relation_ddl,
    build_table_ddl,
    build_view_ddl,
    qualified_ident,
    quote_ident,
)


def _col(
    name,
    data_type="integer",
    *,
    nullable=True,
    default=None,
    comment=None,
    identity=None,
    generated=None,
):
    return ColumnInfo(
        name=name,
        data_type=data_type,
        is_pk=False,
        is_fk=False,
        is_nullable=nullable,
        default=default,
        comment=comment,
        identity=identity,
        generated=generated,
    )


def _table(name="pr.orders", columns=None, **kwargs):
    return TableInfo(name=name, kind="table", columns=list(columns or []), **kwargs)


# --- the correctness requirement: the omission is VISIBLE --------------------


def test_every_table_states_that_it_is_a_reconstruction():
    """The one requirement that is not optional: a synthesized `CREATE TABLE`
    presented as "the table's DDL" is a silent wrong result, so the text says
    what it is."""
    lines = build_table_ddl(_table(columns=[_col("id")])).lines
    assert lines[0] == RECONSTRUCTION_NOTICE
    assert lines[1] == RECONSTRUCTION_NOTICE_DETAIL


def test_the_notice_names_the_two_structural_things_out_of_scope():
    """A stated limit must name what it covers rather than saying "some things
    are missing" -- and after `DEC-260811022536` the list is TWO, both
    structural: inheritance and partitioning."""
    text = RECONSTRUCTION_NOTICE + RECONSTRUCTION_NOTICE_DETAIL
    assert "inheritance" in text
    assert "partitioning" in text


def test_the_notice_no_longer_claims_identity_or_generated_are_missing():
    """`DEC-260811022536` closed the two per-column gaps, so a notice still
    naming them would be a stale limit -- which is worse than no limit, because
    a reader trusts it and concludes a rendered identity column has none."""
    text = RECONSTRUCTION_NOTICE + RECONSTRUCTION_NOTICE_DETAIL
    assert "identity" not in text
    assert "SERIAL" not in text
    assert "GENERATED" not in text


def test_the_notice_is_an_sql_comment():
    """The buffer is read as SQL; a comment is the one thing that cannot be
    mistaken for part of the definition."""
    assert RECONSTRUCTION_NOTICE.startswith("--")
    assert RECONSTRUCTION_NOTICE_DETAIL.startswith("--")


def test_the_notice_is_per_table_not_once_per_buffer():
    """Granularity (open question 6): per table. A tree click lands
    mid-buffer, so a single notice at the top is invisible to exactly the
    gesture this feature adds."""
    one = build_table_ddl(_table("pr.a", [_col("id")])).text
    two = build_table_ddl(_table("pr.b", [_col("id")])).text
    assert one.count(RECONSTRUCTION_NOTICE) == 1
    assert two.count(RECONSTRUCTION_NOTICE) == 1


def test_a_partitioned_looking_table_is_not_given_an_invented_partition_by():
    """"What it must NOT do: guess." A table whose shape v1 cannot read is
    rendered as the columns that WERE read, with the omission named."""
    # The statement itself, i.e. everything below the two notice lines (which
    # legitimately name GENERATED as a thing that is NOT reconstructed).
    body = "\n".join(build_table_ddl(_table(columns=[_col("id")])).lines[2:])
    assert "PARTITION BY" not in body
    assert "INHERITS" not in body
    assert "GENERATED" not in body


# --- columns -----------------------------------------------------------------


def test_columns_render_type_nullability_and_default():
    rendered = build_table_ddl(
        _table(
            columns=[
                _col("id", "integer", nullable=False, default="nextval('s'::regclass)"),
                _col("tag", "text"),
            ]
        )
    )
    assert "    id integer NOT NULL DEFAULT nextval('s'::regclass)," in rendered.lines
    assert "    tag text" in rendered.lines


def test_columns_keep_their_declared_order():
    rendered = build_table_ddl(
        _table(columns=[_col("z"), _col("a"), _col("m")])
    )
    assert list(rendered.column_offsets) == ["z", "a", "m"]


# --- identity / SERIAL / GENERATED columns (`DEC-260811022536`) ---------------


def test_an_identity_always_column_renders_its_identity_clause():
    rendered = build_table_ddl(
        _table(columns=[_col("id", "integer", nullable=False, identity="a")])
    )
    assert "    id integer NOT NULL GENERATED ALWAYS AS IDENTITY" in rendered.lines


def test_an_identity_by_default_column_renders_by_default():
    """`'a'` and `'d'` are different guarantees -- `BY DEFAULT` accepts a
    user-supplied value and `ALWAYS` refuses one -- so collapsing them to one
    clause would misstate the column."""
    rendered = build_table_ddl(
        _table(columns=[_col("id", "bigint", nullable=False, identity="d")])
    )
    assert "    id bigint NOT NULL GENERATED BY DEFAULT AS IDENTITY" in rendered.lines


def test_an_identity_column_does_not_also_render_a_default():
    """Both wrong (PostgreSQL rejects a DEFAULT beside an identity clause) and
    redundant -- the sequence is what the identity clause already means."""
    rendered = build_table_ddl(
        _table(
            columns=[
                _col(
                    "id",
                    "integer",
                    nullable=False,
                    default="nextval('pr.orders_id_seq'::regclass)",
                    identity="a",
                )
            ]
        )
    )
    assert "    id integer NOT NULL GENERATED ALWAYS AS IDENTITY" in rendered.lines
    assert "DEFAULT" not in rendered.text
    assert "nextval" not in rendered.text


def test_a_serial_column_renders_the_catalog_default_not_the_word_serial():
    """The decision recorded in the module docstring: `SERIAL` is a macro for
    integer + sequence + ownership, so emitting it would INFER that the sequence
    behind this column is the one `SERIAL` would have created, and would hide
    WHICH sequence feeds the column. `pg_dump` makes the same call."""
    rendered = build_table_ddl(
        _table(
            columns=[
                _col(
                    "id",
                    "integer",
                    nullable=False,
                    default="nextval('pr.orders_id_seq'::regclass)",
                )
            ]
        )
    )
    assert (
        "    id integer NOT NULL DEFAULT nextval('pr.orders_id_seq'::regclass)"
        in rendered.lines
    )
    assert "SERIAL" not in rendered.text


def test_a_stored_generated_column_renders_its_expression():
    """The expression IS the column's `pg_attrdef` row, i.e.
    `ColumnInfo.default` -- read through `generated == "s"`."""
    rendered = build_table_ddl(
        _table(
            columns=[
                _col("qty", "integer"),
                _col("total", "integer", default="(qty * 2)", generated="s"),
            ]
        )
    )
    assert "    total integer GENERATED ALWAYS AS ((qty * 2)) STORED" in rendered.lines


def test_a_generated_column_does_not_also_render_a_default():
    """The expression replaces the default clause; printing both would render
    the same expression twice and be invalid SQL."""
    text = build_table_ddl(
        _table(columns=[_col("total", "integer", default="(qty * 2)", generated="s")])
    ).text
    assert "DEFAULT" not in text
    assert text.count("(qty * 2)") == 1


def test_a_plain_column_gains_no_identity_or_generated_clause():
    text = build_table_ddl(_table(columns=[_col("tag", "text")])).text
    assert "    tag text" in text
    assert "IDENTITY" not in text
    assert "GENERATED" not in text


def test_an_unknown_attidentity_value_renders_no_identity_clause():
    """Never invent: a catalog value this build does not know renders as the
    plain column it otherwise read, not as a guessed clause."""
    text = build_table_ddl(_table(columns=[_col("id", "integer", identity="?")])).text
    assert "IDENTITY" not in text


def test_identity_and_generated_columns_stay_on_ONE_line():
    """`column_offsets` is a line index and every later offset derives from
    `len(lines)`, so a two-line column rendering would shift every offset below
    it and break click-to-navigate."""
    constraint = ConstraintInfo(
        schema="pr", table="orders", name="pk", kind="primary key",
        columns=["id"], definition="PRIMARY KEY (id)",
    )
    rendered = build_table_ddl(
        _table(
            columns=[
                _col("id", "integer", nullable=False, identity="a"),
                _col("qty", "integer"),
                _col("total", "integer", default="(qty * 2)", generated="s"),
            ]
        ),
        [constraint],
    )
    for name, fragment in (
        ("id", "GENERATED ALWAYS AS IDENTITY"),
        ("qty", "qty integer"),
        ("total", "GENERATED ALWAYS AS ((qty * 2)) STORED"),
    ):
        assert fragment in rendered.lines[rendered.column_offsets[name]]
    assert "CONSTRAINT pk" in rendered.lines[rendered.constraint_offsets["pk"]]
    # No line in the body renders two columns, and none is left dangling.
    body = [line for line in rendered.lines if line.startswith("    ")]
    assert len(body) == 4


def test_rendering_is_byte_identical_across_fetches_with_the_new_fields():
    """Determinism is a hard requirement (BUG-018): identity/generated add no
    ordering or dict iteration of their own."""
    columns = [
        _col("id", "integer", nullable=False, identity="d"),
        _col("total", "integer", default="(qty * 2)", generated="s"),
    ]
    first = build_table_ddl(_table(columns=columns))
    second = build_table_ddl(_table(columns=list(columns)))
    assert first.text == second.text
    assert first.column_offsets == second.column_offsets


def test_a_table_with_no_columns_and_no_constraints_still_renders():
    assert "CREATE TABLE pr.orders ();" in build_table_ddl(_table()).text


# --- constraints: pg_get_constraintdef VERBATIM, inline, no ALTER ------------


def test_constraints_render_inline_using_pg_get_constraintdef_verbatim():
    """Trap 3: re-deriving a constraint's text from its columns is how this
    pane and the schema diff come to disagree about what a constraint IS."""
    constraint = ConstraintInfo(
        schema="pr",
        table="orders",
        name="orders_qty_check",
        kind="check",
        columns=["qty"],
        definition="CHECK ((qty > 0))",
    )
    rendered = build_table_ddl(_table(columns=[_col("qty")]), [constraint])
    assert "    CONSTRAINT orders_qty_check CHECK ((qty > 0))" in rendered.lines


def test_no_alter_statement_is_ever_emitted():
    constraint = ConstraintInfo(
        schema="pr", table="orders", name="pk", kind="primary key",
        columns=["id"], definition="PRIMARY KEY (id)",
    )
    text = build_table_ddl(_table(columns=[_col("id")]), [constraint]).text
    assert "ALTER TABLE" not in text


def test_only_the_last_body_line_has_no_trailing_comma():
    constraint = ConstraintInfo(
        schema="pr", table="orders", name="pk", kind="primary key",
        columns=["id"], definition="PRIMARY KEY (id)",
    )
    lines = build_table_ddl(_table(columns=[_col("id")]), [constraint]).lines
    body = [line for line in lines if line.startswith("    ")]
    assert body[0].endswith(",")
    assert not body[-1].endswith(",")


def test_constraint_order_is_deterministic_across_fetches():
    """BUG-018's determinism rule, which is NOT one of the open questions."""
    def make(name, kind):
        return ConstraintInfo(
            schema="pr", table="orders", name=name, kind=kind,
            columns=[], definition=f"{kind.upper()} (x)",
        )

    forwards = [make("z_check", "check"), make("a_pk", "primary key")]
    first = build_table_ddl(_table(columns=[_col("x")]), forwards).text
    second = build_table_ddl(_table(columns=[_col("x")]), list(reversed(forwards))).text
    assert first == second
    assert first.index("a_pk") < first.index("z_check")


# --- indexes -----------------------------------------------------------------


def test_standalone_indexes_are_appended_verbatim():
    index = IndexInfo(
        schema="pr", table="orders", name="ix_tag", columns=["tag"],
        method="btree", definition="CREATE INDEX ix_tag ON pr.orders USING btree (tag)",
    )
    rendered = build_table_ddl(_table(columns=[_col("tag")]), (), [index])
    assert "CREATE INDEX ix_tag ON pr.orders USING btree (tag);" in rendered.lines
    assert "ix_tag" in rendered.index_offsets


def test_index_order_is_deterministic_across_fetches():
    """The constraint half of this rule is pinned above; the index half was
    not. `pg_index` rows arrive in whatever order the server chose, so two
    fetches of an unchanged table must still render byte-identically."""
    def make(name):
        return IndexInfo(
            schema="pr", table="orders", name=name, columns=["tag"],
            method="btree",
            definition=f"CREATE INDEX {name} ON pr.orders USING btree (tag)",
        )

    forwards = [make("ix_zulu"), make("ix_alpha")]
    table = _table(columns=[_col("tag")])
    first = build_table_ddl(table, (), forwards)
    second = build_table_ddl(table, (), list(reversed(forwards)))
    assert first.text == second.text
    assert first.index_offsets == second.index_offsets
    assert first.text.index("ix_alpha") < first.text.index("ix_zulu")


def test_constraint_backed_indexes_are_not_emitted_as_create_index():
    """PostgreSQL rejects `DROP INDEX` on one and the constraint already
    prints it -- emitting both would print the same object twice."""
    index = IndexInfo(
        schema="pr", table="orders", name="orders_pkey", columns=["id"],
        is_unique=True, is_primary=True, method="btree",
        definition="CREATE UNIQUE INDEX orders_pkey ON pr.orders (id)",
        constraint_name="orders_pkey",
    )
    rendered = build_table_ddl(_table(columns=[_col("id")]), (), [index])
    assert "CREATE UNIQUE INDEX" not in rendered.text
    assert rendered.index_offsets == {}


# --- comments ----------------------------------------------------------------


def test_table_and_column_comments_render_as_comment_on_statements():
    rendered = build_table_ddl(
        _table(columns=[_col("tag", comment="the tag")], comment="every order")
    )
    assert "COMMENT ON TABLE pr.orders IS 'every order';" in rendered.lines
    assert "COMMENT ON COLUMN pr.orders.tag IS 'the tag';" in rendered.lines


def test_a_comment_with_an_apostrophe_is_escaped():
    rendered = build_table_ddl(_table(columns=[_col("id")], comment="it's here"))
    assert "COMMENT ON TABLE pr.orders IS 'it''s here';" in rendered.lines


def test_no_comment_statements_when_nothing_is_commented():
    assert "COMMENT ON" not in build_table_ddl(_table(columns=[_col("id")])).text


# --- views and matviews ------------------------------------------------------


def test_a_view_renders_pg_get_viewdef_verbatim():
    view = TableInfo(name="pr.v", kind="view", view_definition=" SELECT 1;")
    lines = build_view_ddl(view).lines
    assert lines[0] == "CREATE VIEW pr.v AS"
    assert lines[1] == "SELECT 1;"


def test_a_view_carries_no_reconstruction_notice():
    """A view's body is not reconstructed -- PostgreSQL hands back the whole
    SELECT -- so claiming incompleteness there would be its own wrong result."""
    view = TableInfo(name="pr.v", kind="view", view_definition="SELECT 1")
    assert RECONSTRUCTION_NOTICE not in build_view_ddl(view).text


def test_a_matview_is_labelled_materialized_view():
    mv = TableInfo(name="pr.m", kind="matview", view_definition="SELECT 1")
    assert build_view_ddl(mv).lines[0] == "CREATE MATERIALIZED VIEW pr.m AS"


def test_a_view_with_no_definition_says_so_rather_than_inventing_a_body():
    view = TableInfo(name="pr.v", kind="view", columns=[_col("a", "text")])
    text = build_view_ddl(view).text
    assert "definition not available" in text
    assert "SELECT" not in text


def test_build_relation_ddl_dispatches_on_kind():
    table = _table(columns=[_col("id")])
    view = TableInfo(name="pr.v", kind="view", view_definition="SELECT 1")
    assert "CREATE TABLE" in build_relation_ddl(table).text
    assert "CREATE VIEW" in build_relation_ddl(view).text


# --- identifier quoting -------------------------------------------------------


def test_ordinary_identifiers_are_left_unquoted():
    assert quote_ident("orders") == "orders"
    assert qualified_ident("pr.orders") == "pr.orders"


def test_identifiers_needing_quotes_get_them():
    assert quote_ident("Order Lines") == '"Order Lines"'
    assert qualified_ident("Pr.order lines") == '"Pr"."order lines"'


def test_an_embedded_double_quote_is_doubled():
    assert quote_ident('we"ird') == '"we""ird"'


# --- offsets: what the tree navigates by --------------------------------------


def test_offsets_point_at_the_line_that_renders_each_item():
    constraint = ConstraintInfo(
        schema="pr", table="orders", name="pk", kind="primary key",
        columns=["id"], definition="PRIMARY KEY (id)",
    )
    index = IndexInfo(
        schema="pr", table="orders", name="ix_tag", columns=["tag"],
        method="btree", definition="CREATE INDEX ix_tag ON pr.orders (tag)",
    )
    rendered = build_table_ddl(
        _table(columns=[_col("id"), _col("tag", "text")]), [constraint], [index]
    )
    assert rendered.lines[rendered.column_offsets["tag"]].strip().startswith("tag text")
    assert "CONSTRAINT pk" in rendered.lines[rendered.constraint_offsets["pk"]]
    assert rendered.lines[rendered.index_offsets["ix_tag"]].startswith("CREATE INDEX")


# --- the SERIAL/nextval clone hazard (`FQ-260812022749`, warn-only) -----------

from pgtp_editor.db.table_ddl import (  # noqa: E402
    SEQUENCE_CLONE_HAZARD,
    SEQUENCE_CLONE_HAZARD_DETAIL,
    has_sequence_default,
    sequence_clone_hazard_lines,
)


def _serial_table():
    return _table(
        columns=[
            _col(
                "id",
                "integer",
                nullable=False,
                default="nextval('pr.orders_id_seq'::regclass)",
            ),
            _col("tag", "text"),
        ]
    )


def test_a_nextval_default_earns_the_clone_hazard_notice():
    """Part 5 settled what this text is FOR: a clone source. A copy of it under
    a new name still draws from the ORIGINAL table's sequence, so the two draw
    from one counter and dropping the original breaks the clone."""
    rendered = build_table_ddl(_serial_table())
    assert SEQUENCE_CLONE_HAZARD in rendered.lines
    assert SEQUENCE_CLONE_HAZARD_DETAIL in rendered.lines


def test_the_hazard_sits_directly_under_the_reconstruction_notice():
    """Inside the region a whole-object copy takes with it -- a notice the
    reader has scrolled past is a notice that does not exist."""
    rendered = build_table_ddl(_serial_table())
    assert rendered.lines[:4] == [
        RECONSTRUCTION_NOTICE,
        RECONSTRUCTION_NOTICE_DETAIL,
        SEQUENCE_CLONE_HAZARD,
        SEQUENCE_CLONE_HAZARD_DETAIL,
    ]


def test_the_hazard_does_not_shift_the_column_or_constraint_offsets():
    """Offsets are derived from `len(lines)`, so an extra notice line must not
    be able to break click-to-navigate."""
    rendered = build_table_ddl(_serial_table())
    for name, offset in rendered.column_offsets.items():
        assert name in rendered.lines[offset]


def test_a_table_with_no_nextval_default_says_nothing():
    """Warning about every table would train the reader to skip the line."""
    rendered = build_table_ddl(_table(columns=[_col("tag", "text")]))
    assert SEQUENCE_CLONE_HAZARD not in rendered.text


def test_an_IDENTITY_column_is_not_the_hazard():
    """Cloning `GENERATED ... AS IDENTITY` creates a NEW implicit sequence for
    the new table, so the shared-counter hazard does not arise."""
    table = _table(columns=[_col("id", "integer", nullable=False, identity="a")])
    assert not has_sequence_default(table)
    assert sequence_clone_hazard_lines(table) == []


def test_a_generated_column_whose_expression_calls_nextval_is_not_the_hazard():
    """Its `default` IS its expression, not a column default -- and it is not
    what a clone copies wrongly."""
    table = _table(
        columns=[_col("n", "integer", default="nextval('s')", generated="s")]
    )
    assert not has_sequence_default(table)


def test_views_and_matviews_get_no_table_clone_hazard():
    """A view is not cloned by copying a `CREATE TABLE`."""
    view = TableInfo(name="pr.v", kind="view", view_definition="SELECT 1")
    assert sequence_clone_hazard_lines(view) == []
