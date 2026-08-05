from pathlib import Path

from pgtp_editor.schema_learning.storage import (
    CURATED_BUNDLED_VERSION,
    bundled_curated_xsd_text,
    curated_xsd_path,
    learned_xsd_path,
    schema_model_path,
)
from pgtp_editor.schema_learning.xsd_load import load_curated
from pgtp_editor.schema_learning.xsd_verify import verify_curated


def test_schema_model_path_uses_given_base_dir(tmp_path):
    result = schema_model_path(tmp_path)
    assert result == tmp_path / "schema_model.json"


def test_schema_model_path_defaults_to_real_app_data_location_when_no_base_dir():
    result = schema_model_path()
    assert result.name == "schema_model.json"
    assert isinstance(result, Path)


def test_schema_model_path_and_learned_xsd_path_share_the_same_directory(tmp_path):
    model_path = schema_model_path(tmp_path)
    xsd_path = learned_xsd_path(tmp_path)
    assert model_path.parent == xsd_path.parent == tmp_path


def test_curated_and_learned_xsd_paths(tmp_path):
    from pgtp_editor.schema_learning.storage import curated_xsd_path, learned_xsd_path
    assert curated_xsd_path(tmp_path) == tmp_path / "curated.xsd"
    assert learned_xsd_path(tmp_path) == tmp_path / "learned.xsd"


def test_curated_bundled_version_constant():
    assert CURATED_BUNDLED_VERSION == "1.2"


def test_bundled_curated_xsd_text_is_present_and_versioned():
    text = bundled_curated_xsd_text()
    assert text is not None
    assert "v1.2" in text
    assert "<xs:schema" in text


def test_bundled_curated_xsd_loads_and_verifies_clean():
    """Guard against shipping a broken bundled schema: it must parse via the
    curated loader and carry no fatal dialect/XML issues."""
    text = bundled_curated_xsd_text()
    schema = load_curated(text)
    assert schema.model.paths  # non-empty structure was parsed
    fatal = [issue for issue in verify_curated(text) if issue.fatal]
    assert fatal == []


def test_bundled_curated_xsd_resolves_edit_ability_mode_label():
    """Regression for BUG-002: editAbilityMode was entirely missing from the
    bundled curated.xsd, so the Properties panel could never show its label
    even though the sibling *AbilityMode attributes resolved fine."""
    from pgtp_editor.schema_learning.settings_index import value_label

    text = bundled_curated_xsd_text()
    schema = load_curated(text)
    chain = "Project/Presentation/Pages/Page"

    assert value_label(schema.model, chain, "editAbilityMode", "3") == "Modal window"
    # Sibling attribute, kept working -- same enumeration/labels.
    assert value_label(schema.model, chain, "viewAbilityMode", "3") == "Modal window"


def test_bundled_curated_xsd_new_edit_ability_mode_block_verifies_cleanly():
    """The new editAbilityMode block itself must not trip the new
    duplicate-attribute-name check (BUG-002 part 2) or any other Verify rule
    -- it's a copy of the viewAbilityMode block's shape, so a copy/paste slip
    (e.g. forgetting to rename it, landing it in the wrong complexType twice)
    would show up here specifically, not just in the overall fatal-issues
    guard `test_bundled_curated_xsd_loads_and_verifies_clean` already has."""
    text = bundled_curated_xsd_text()
    issues = verify_curated(text)
    messages = [i.message for i in issues]
    assert not any("editAbilityMode" in m for m in messages)
    assert not any("duplicate attribute name" in m for m in messages)
