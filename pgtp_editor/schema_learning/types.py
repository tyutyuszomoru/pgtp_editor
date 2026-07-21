# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
