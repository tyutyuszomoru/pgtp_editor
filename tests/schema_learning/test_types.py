from pgtp_editor.schema_learning.types import infer_scalar_type, combine_type


def test_infer_boolean():
    assert infer_scalar_type("true") == "boolean"
    assert infer_scalar_type("false") == "boolean"


def test_infer_integer():
    assert infer_scalar_type("42") == "integer"
    assert infer_scalar_type("-7") == "integer"


def test_infer_decimal():
    assert infer_scalar_type("3.14") == "decimal"
    assert infer_scalar_type("-0.5") == "decimal"


def test_infer_string_fallback():
    assert infer_scalar_type("hello") == "string"
    assert infer_scalar_type("") == "string"
    assert infer_scalar_type("1573119") == "integer"
    assert infer_scalar_type("R:\\var\\www\\html") == "string"


def test_combine_type_widens_toward_string():
    assert combine_type("boolean", "integer") == "integer"
    assert combine_type("integer", "boolean") == "integer"
    assert combine_type("integer", "decimal") == "decimal"
    assert combine_type("decimal", "string") == "string"
    assert combine_type("string", "boolean") == "string"
    assert combine_type("boolean", "boolean") == "boolean"
