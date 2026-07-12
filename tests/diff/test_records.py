from pgtp_editor.diff.records import Difference


def test_difference_holds_all_fields():
    diff = Difference(
        kind="changed",
        path=["development_equipment"],
        node_kind="page",
        attribute="caption",
        old_value="Old Caption",
        new_value="New Caption",
        ambiguous=False,
    )
    assert diff.kind == "changed"
    assert diff.path == ["development_equipment"]
    assert diff.node_kind == "page"
    assert diff.attribute == "caption"
    assert diff.old_value == "Old Caption"
    assert diff.new_value == "New Caption"
    assert diff.ambiguous is False


def test_difference_ambiguous_defaults_to_false():
    diff = Difference(
        kind="added",
        path=["some_page"],
        node_kind="page",
        attribute=None,
        old_value=None,
        new_value="a page node placeholder",
    )
    assert diff.ambiguous is False
