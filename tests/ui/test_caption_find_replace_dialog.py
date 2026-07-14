"""Phase 4: CaptionFindReplaceDialog. Driven via methods only — NO test calls
`.exec()` (the offscreen harness would hang on a blocking modal)."""
from pgtp_editor.ui.caption_find_replace_dialog import CaptionFindReplaceDialog


def _filter_dialog(qtbot, **kwargs):
    calls = []
    dialog = CaptionFindReplaceDialog(
        on_filter=lambda *a: calls.append(a), **kwargs
    )
    qtbot.addWidget(dialog)
    return dialog, calls


def test_filter_mode_hides_replace_field(qtbot):
    dialog, _ = _filter_dialog(qtbot)
    assert dialog.replace_field.isVisible() is False
    assert dialog.replace_field.isEnabled() is False


def test_replace_mode_shows_replace_field_and_scope(qtbot):
    dialog = CaptionFindReplaceDialog(
        on_filter=lambda *a: None,
        on_replace_all=lambda *a: None,
        replace_enabled=True,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.replace_field.isVisibleTo(dialog) is True
    assert dialog._scope_box.isVisibleTo(dialog) is True
    assert hasattr(dialog, "replace_all_button")


def test_do_filter_calls_callback_with_fields(qtbot):
    dialog, calls = _filter_dialog(qtbot)
    dialog.find_field.setText("hello")
    dialog.set_mode("regular")
    dialog.match_case_checkbox.setChecked(True)
    dialog._do_filter()
    assert calls == [("hello", "regular", True)]


def test_do_filter_reads_extended_mode_and_case_off(qtbot):
    dialog, calls = _filter_dialog(qtbot)
    dialog.find_field.setText("x")
    dialog.set_mode("extended")
    dialog.match_case_checkbox.setChecked(False)
    dialog._do_filter()
    assert calls == [("x", "extended", False)]


def test_default_mode_is_normal(qtbot):
    dialog, _ = _filter_dialog(qtbot)
    assert dialog.selected_mode() == "normal"


def test_initial_find_prefills_field(qtbot):
    dialog, _ = _filter_dialog(qtbot, initial_find="preloaded")
    assert dialog.find_field.text() == "preloaded"


def test_do_replace_all_calls_callback_with_fields(qtbot):
    calls = []
    dialog = CaptionFindReplaceDialog(
        on_filter=lambda *a: None,
        on_replace_all=lambda *a: calls.append(a),
        replace_enabled=True,
    )
    qtbot.addWidget(dialog)
    dialog.find_field.setText("foo")
    dialog.replace_field.setText("bar")
    dialog.set_mode("normal")
    dialog.match_case_checkbox.setChecked(True)
    # default scope = In selection
    dialog._do_replace_all()
    assert calls == [("foo", "bar", "normal", True, True)]


def test_replace_all_global_scope(qtbot):
    calls = []
    dialog = CaptionFindReplaceDialog(
        on_filter=lambda *a: None,
        on_replace_all=lambda *a: calls.append(a),
        replace_enabled=True,
    )
    qtbot.addWidget(dialog)
    dialog.find_field.setText("f")
    dialog.replace_field.setText("g")
    dialog.global_radio.setChecked(True)
    dialog._do_replace_all()
    assert calls[0][4] is False  # in_selection is False for Global scope


def test_default_scope_is_in_selection(qtbot):
    dialog = CaptionFindReplaceDialog(
        on_filter=lambda *a: None,
        on_replace_all=lambda *a: None,
        replace_enabled=True,
    )
    qtbot.addWidget(dialog)
    assert dialog.in_selection() is True


def test_invalid_regex_shows_inline_error_no_crash(qtbot):
    def raising_filter(find, mode, case):
        raise ValueError("Invalid regular expression: bad")

    dialog = CaptionFindReplaceDialog(on_filter=raising_filter)
    qtbot.addWidget(dialog)
    dialog.find_field.setText("(")
    dialog.set_mode("regular")
    dialog._do_filter()  # must not raise
    assert "Invalid regular expression" in dialog.error_label.text()


def test_error_cleared_on_next_successful_filter(qtbot):
    state = {"raise": True}

    def maybe_raise(find, mode, case):
        if state["raise"]:
            raise ValueError("boom")

    dialog = CaptionFindReplaceDialog(on_filter=maybe_raise)
    qtbot.addWidget(dialog)
    dialog._do_filter()
    assert dialog.error_label.text() == "boom"
    state["raise"] = False
    dialog._do_filter()
    assert dialog.error_label.text() == ""
