# tests/db/test_rename.py
"""Pure tests for targeted-attribute rename in the Raw XML buffer."""
from pgtp_editor.db.rename import rename_field, rename_table


def test_rename_field_replaces_all_and_counts():
    text = '<a fieldName="old"/><b fieldName="old"/>'
    new_text, count = rename_field(text, "old", "new")
    assert count == 2
    assert new_text == '<a fieldName="new"/><b fieldName="new"/>'


def test_rename_table_replaces_all_and_counts():
    text = '<Page tableName="pr.x"/><Detail tableName="pr.x"/>'
    new_text, count = rename_table(text, "pr.x", "pr.y")
    assert count == 2
    assert new_text == '<Page tableName="pr.y"/><Detail tableName="pr.y"/>'


def test_rename_field_only_targets_that_attribute():
    # A tableName that happens to hold the same value must be untouched, and a
    # substring inside other text must not be replaced.
    text = '<c fieldName="id"/><d tableName="id"/><e other="id"/>id'
    new_text, count = rename_field(text, "id", "code")
    assert count == 1
    assert new_text == '<c fieldName="code"/><d tableName="id"/><e other="id"/>id'


def test_rename_table_only_targets_that_attribute():
    text = '<c tableName="t"/><d fieldName="t"/><e caption="t"/>'
    new_text, count = rename_table(text, "t", "u")
    assert count == 1
    assert new_text == '<c tableName="u"/><d fieldName="t"/><e caption="t"/>'


def test_rename_no_match_returns_zero_and_unchanged():
    text = '<a fieldName="x"/>'
    new_text, count = rename_field(text, "missing", "new")
    assert count == 0
    assert new_text == text


def test_rename_does_not_partial_match_longer_names():
    # fieldName="oldish" must not be touched when renaming "old".
    text = '<a fieldName="old"/><b fieldName="oldish"/>'
    new_text, count = rename_field(text, "old", "new")
    assert count == 1
    assert new_text == '<a fieldName="new"/><b fieldName="oldish"/>'
