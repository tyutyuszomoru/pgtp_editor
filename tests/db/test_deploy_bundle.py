# tests/db/test_deploy_bundle.py
"""Pure tests for the §18.3 deploy-bundle decision layer (no Qt, no live DB, no git).

Every case is canned `DriftMarkers` data -- the same shape
`ddl_project.compute_drift_markers` returns -- plus canned SQL text, the way
`tests/db/test_schema_diff.py` feeds canned schemas to `diff_schemas`. Nothing
here opens a connection or touches the filesystem.
"""
import dataclasses

import pytest

from pgtp_editor.db.ddl_project import DriftMarkers
from pgtp_editor.db.deploy_bundle import (
    DeployBundle,
    DeployCandidate,
    DeployPlan,
    MissingCandidateSql,
    assemble_deploy_bundle,
    deploy_blockers,
    deploy_candidates,
    git_commit_placeholder,
)


def _markers(**spec):
    """`name="*"`/`"!"`/`"*!"`/`""` -> {relpath: DriftMarkers}, §18.2 markers."""
    return {
        f"ddl/pr.{name}.sql": DriftMarkers(
            locally_edited="*" in marker, live_drifted="!" in marker
        )
        for name, marker in spec.items()
    }


def _sql(*names):
    return {f"ddl/pr.{name}.sql": f"CREATE OR REPLACE FUNCTION pr.{name}() ..." for name in names}


# --- step 1: candidates are exactly the `*` set -------------------------------


def test_only_locally_edited_objects_are_candidates():
    markers = _markers(a="*", b="", c="*", d="!")
    assert deploy_candidates(markers) == ("ddl/pr.a.sql", "ddl/pr.c.sql")


def test_object_with_no_last_deployed_reference_is_not_a_candidate():
    # Absent from compute_drift_markers' output entirely = never deployed;
    # that is not "unchanged" and it is not a candidate either.
    markers = _markers(a="*")
    plan = assemble_deploy_bundle(markers, _sql("a", "never_deployed"))
    assert plan.candidates == ("ddl/pr.a.sql",)
    assert plan.bundle.relpaths == ("ddl/pr.a.sql",)


# --- step 2: the ambiguity gate ----------------------------------------------


def test_single_live_drifted_candidate_blocks_the_whole_batch():
    markers = _markers(a="*", b="*!", c="*")
    plan = assemble_deploy_bundle(markers, _sql("a", "b", "c"))

    assert plan.blocked is True
    assert plan.blocker_paths == ("ddl/pr.b.sql",)
    # All three were candidates -- the refusal is of the batch, not of one object.
    assert plan.candidates == ("ddl/pr.a.sql", "ddl/pr.b.sql", "ddl/pr.c.sql")


def test_blocked_plan_exposes_no_deployable_bundle_at_all():
    plan = assemble_deploy_bundle(_markers(a="*", b="*!"), _sql("a", "b"))
    assert plan.bundle is None


def test_every_blocker_is_named_in_the_refusal_not_just_the_first():
    markers = _markers(a="*!", b="*", c="*!", d="*!", e="")
    plan = assemble_deploy_bundle(markers, _sql("a", "b", "c", "d"))

    assert plan.blocker_paths == ("ddl/pr.a.sql", "ddl/pr.c.sql", "ddl/pr.d.sql")
    message = plan.refusal_message
    for relpath in ("ddl/pr.a.sql", "ddl/pr.c.sql", "ddl/pr.d.sql"):
        assert relpath in message
    # Not a blocker, so not named as one.
    assert "ddl/pr.b.sql" not in message
    # Recovery is stated: resolve, then re-run (§12's gate vocabulary).
    assert "re-run" in message.lower()
    assert "resolve" in message.lower()


def test_blockers_carry_the_18_2_marker_text():
    blockers = deploy_blockers(_markers(a="*!"))
    assert [b.marker_text for b in blockers] == ["*!"]


def test_live_drift_without_a_local_edit_is_not_part_of_the_batch():
    # `!`-only is the ordinary aftermath of a single-object Apply (§18.2): the
    # object is not being deployed, so it blocks nothing.
    markers = _markers(a="*", b="!")
    plan = assemble_deploy_bundle(markers, _sql("a"))

    assert plan.blocked is False
    assert plan.bundle.relpaths == ("ddl/pr.a.sql",)


def test_clean_batch_is_approved_with_no_refusal_text():
    plan = assemble_deploy_bundle(_markers(a="*", b="*"), _sql("a", "b"))

    assert plan.blocked is False
    assert plan.blockers == ()
    assert plan.refusal_message == ""
    assert plan.bundle.relpaths == ("ddl/pr.a.sql", "ddl/pr.b.sql")


# --- empty vs blocked are different states -----------------------------------


def test_empty_candidate_set_is_an_approved_empty_bundle_not_a_block():
    plan = assemble_deploy_bundle(_markers(a="", b="!"), {})

    assert plan.candidates == ()
    assert plan.blocked is False
    assert plan.bundle is not None
    assert plan.bundle.is_empty is True
    assert plan.bundle.sql_text() == ""


def test_blocked_and_empty_are_distinguishable_without_exceptions():
    empty = assemble_deploy_bundle(_markers(a=""), {})
    blocked = assemble_deploy_bundle(_markers(a="*!"), _sql("a"))

    assert (empty.blocked, empty.bundle is None) == (False, False)
    assert (blocked.blocked, blocked.bundle is None) == (True, True)


# --- step 3: order is adjustable, content is not ------------------------------


def test_default_order_is_stable_and_alphabetical():
    markers = _markers(c="*", a="*", b="*")
    first = assemble_deploy_bundle(markers, _sql("a", "b", "c")).bundle
    second = assemble_deploy_bundle(dict(reversed(list(markers.items()))), _sql("a", "b", "c")).bundle

    assert first.relpaths == ("ddl/pr.a.sql", "ddl/pr.b.sql", "ddl/pr.c.sql")
    assert second.relpaths == first.relpaths


def test_bundle_can_be_reordered_and_sql_text_follows_the_new_order():
    bundle = assemble_deploy_bundle(_markers(a="*", b="*"), _sql("a", "b")).bundle
    swapped = bundle.reordered(["ddl/pr.b.sql", "ddl/pr.a.sql"])

    assert swapped.relpaths == ("ddl/pr.b.sql", "ddl/pr.a.sql")
    assert swapped.sql_text().index("pr.b()") < swapped.sql_text().index("pr.a()")
    # Reordering returns a new bundle; the original is untouched.
    assert bundle.relpaths == ("ddl/pr.a.sql", "ddl/pr.b.sql")


def test_reordered_refuses_anything_that_is_not_a_permutation():
    bundle = assemble_deploy_bundle(_markers(a="*", b="*"), _sql("a", "b")).bundle

    with pytest.raises(ValueError):  # dropping a statement
        bundle.reordered(["ddl/pr.a.sql"])
    with pytest.raises(ValueError):  # smuggling one in
        bundle.reordered(["ddl/pr.a.sql", "ddl/pr.b.sql", "ddl/pr.z.sql"])
    with pytest.raises(ValueError):  # duplicating one
        bundle.reordered(["ddl/pr.a.sql", "ddl/pr.a.sql"])


def test_bundle_content_is_immutable_no_edit_api():
    bundle = assemble_deploy_bundle(_markers(a="*"), _sql("a")).bundle

    assert isinstance(bundle, DeployBundle)
    assert dataclasses.is_dataclass(bundle) and bundle.__dataclass_params__.frozen
    assert bundle.entries[0].__dataclass_params__.frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.entries[0].sql = "DROP DATABASE prod;"
    # No mutation surface on the bundle itself.
    assert not [name for name in dir(bundle) if name.startswith("set_")]
    assert isinstance(bundle.entries, tuple)


def test_sql_text_terminates_statements_and_separates_blocks():
    plan = assemble_deploy_bundle(
        _markers(a="*", b="*"),
        {"ddl/pr.a.sql": "SELECT 1", "ddl/pr.b.sql": "SELECT 2;\n"},
    )
    assert plan.bundle.sql_text() == "SELECT 1;\n\nSELECT 2;\n"


# --- misuse is the only exceptional case -------------------------------------


def test_candidate_without_supplied_sql_is_refused_not_dropped():
    with pytest.raises(MissingCandidateSql) as excinfo:
        assemble_deploy_bundle(_markers(a="*", b="*"), _sql("a"))
    assert "ddl/pr.b.sql" in str(excinfo.value)


def test_missing_sql_is_not_even_consulted_for_a_blocked_batch():
    # The gate runs first: a blocked batch is refused before any assembly, so
    # the caller never has to supply SQL it will not use.
    plan = assemble_deploy_bundle(_markers(a="*!", b="*"), {})
    assert plan.blocked is True and plan.bundle is None


# --- hard non-goals ----------------------------------------------------------


def test_git_step_is_an_explicit_no_op_placeholder():
    bundle = assemble_deploy_bundle(_markers(a="*"), _sql("a")).bundle
    assert git_commit_placeholder(bundle) is None


def test_module_never_executes_sql_or_shells_out():
    import ast
    import inspect

    from pgtp_editor.db import deploy_bundle

    tree = ast.parse(inspect.getsource(deploy_bundle))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    # No DB driver, no shelling out to git, no Qt, no filesystem.
    assert imported <= {"__future__", "collections", "dataclasses", "ddl_project"}, imported


def test_plan_is_frozen():
    plan = DeployPlan()
    assert dataclasses.is_dataclass(plan) and plan.__dataclass_params__.frozen
    assert DeployCandidate("ddl/x.sql", "SELECT 1").relpath == "ddl/x.sql"
