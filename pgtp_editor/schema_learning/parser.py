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

import io
import re

import defusedxml.ElementTree as ET

# Matches CESU-8 encoded UTF-16 surrogate pairs: some real-world .pgtp files
# contain emoji in free-text element content (e.g. embedded PHP/JS source)
# that tools have mis-encoded as two 3-byte UTF-8 sequences representing a
# surrogate pair, instead of one proper 4-byte UTF-8 sequence. Each 3-byte
# sequence is syntactically valid UTF-8 but decodes to a lone/paired
# surrogate codepoint, which is forbidden by the XML spec and makes expat
# reject the file as "not well-formed". Since this tool only cares about
# document structure (not the exact text of free-form content), we strip
# these sequences before parsing rather than trying to recover the emoji.
_CESU8_SURROGATE_PAIR_RE = re.compile(
    rb"[\xed][\xa0-\xaf][\x80-\xbf][\xed][\xb0-\xbf][\x80-\xbf]"
)


def _read_sanitized_bytes(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    return _CESU8_SURROGATE_PAIR_RE.sub(b"", data)


def walk_document(file_path):
    data = _read_sanitized_bytes(file_path)
    root = ET.parse(io.BytesIO(data)).getroot()
    yield from walk_element(root, root.tag)


def walk_element(elem, path):
    child_tag_counts = {}
    for child in elem:
        child_tag_counts[child.tag] = child_tag_counts.get(child.tag, 0) + 1

    has_text = bool(elem.text and elem.text.strip())

    yield path, dict(elem.attrib), child_tag_counts, has_text

    for child in elem:
        yield from walk_element(child, f"{path}/{child.tag}")
