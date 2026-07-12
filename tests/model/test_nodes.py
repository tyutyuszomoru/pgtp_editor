from pgtp_editor.model.nodes import DetailNode


def test_detail_node_inner_sourceline_defaults_to_none():
    detail = DetailNode(identity="x", attrib={}, sourceline=10)
    assert detail.inner_sourceline is None


def test_detail_node_inner_sourceline_can_be_set():
    detail = DetailNode(identity="x", attrib={}, sourceline=10, inner_sourceline=25)
    assert detail.sourceline == 10
    assert detail.inner_sourceline == 25
