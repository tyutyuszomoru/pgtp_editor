from pgtp_editor.diff.resolve import ResolutionError


def test_resolution_error_holds_segment_index_and_message():
    error = ResolutionError(segment_index=0, message="no Page named 'missing_page'")
    assert error.segment_index == 0
    assert error.message == "no Page named 'missing_page'"
