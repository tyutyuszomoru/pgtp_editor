import re

_BOOL_VALUES = {"true", "false"}
_INT_RE = re.compile(r"^-?\d+$")
_DECIMAL_RE = re.compile(r"^-?\d+\.\d+$")

_TYPE_RANK = {"boolean": 0, "integer": 1, "decimal": 2, "string": 3}


def infer_scalar_type(value):
    if value in _BOOL_VALUES:
        return "boolean"
    if _INT_RE.fullmatch(value):
        return "integer"
    if _DECIMAL_RE.fullmatch(value):
        return "decimal"
    return "string"


def combine_type(type_a, type_b):
    return type_a if _TYPE_RANK[type_a] >= _TYPE_RANK[type_b] else type_b
