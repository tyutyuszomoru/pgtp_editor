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

"""Reading `.pgtp` bytes, repairing a real-world encoding defect on the way in.

Some `.pgtp` files produced by the vendor tool contain emoji (or other
astral-plane characters, e.g. in a caption like `👁 All Materials`) encoded
as **CESU-8**: the character's UTF-16 surrogate pair is written as two
separate 3-byte UTF-8-looking sequences, instead of one proper 4-byte UTF-8
sequence. Each 3-byte sequence is individually valid-looking UTF-8 but
decodes to a lone surrogate codepoint (U+D800..U+DFFF), which the XML spec
forbids -- so `lxml`/expat rejects the whole file with an error like
"Char 0xD83D out of allowed range".

`repair_cesu8_surrogate_pairs` rewrites each such pair into the single real
4-byte UTF-8 character it was meant to be, so the file both parses and keeps
its content. This is a deliberate *repair*, not a strip: the emoji survives
and displays correctly, unlike the structure-only schema-learning parser
which discards these bytes. A consequence: a Diff/Merge write-back of a file
that contained CESU-8 emits the corrected UTF-8 encoding rather than
reproducing the malformed original byte-for-byte -- a benign move toward a
valid file. On a file with no such defect the repair matches nothing and is
a pure no-op, so byte-for-byte round trips of well-formed files are
unaffected.
"""
from __future__ import annotations

import re

# High surrogate (ED A0-AF 80-BF) immediately followed by a low surrogate
# (ED B0-BF 80-BF) -- the CESU-8 encoding of one astral-plane character.
_CESU8_SURROGATE_PAIR_RE = re.compile(
    rb"[\xed][\xa0-\xaf][\x80-\xbf][\xed][\xb0-\xbf][\x80-\xbf]"
)


def _decode_surrogate_pair(match: "re.Match[bytes]") -> bytes:
    b = match.group(0)
    high = ((b[0] & 0x0F) << 12) | ((b[1] & 0x3F) << 6) | (b[2] & 0x3F)
    low = ((b[3] & 0x0F) << 12) | ((b[4] & 0x3F) << 6) | (b[5] & 0x3F)
    codepoint = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
    return chr(codepoint).encode("utf-8")


def repair_cesu8_surrogate_pairs(data: bytes) -> bytes:
    """Rewrite any CESU-8 surrogate pairs in `data` into proper UTF-8.

    A no-op (returns `data` unchanged) when there are none.
    """
    return _CESU8_SURROGATE_PAIR_RE.sub(_decode_surrogate_pair, data)


def read_pgtp_bytes(path) -> bytes:
    """Read the file at `path` and return CESU-8-repaired bytes ready for
    XML parsing. Raises OSError if the file cannot be read."""
    with open(path, "rb") as f:
        return repair_cesu8_surrogate_pairs(f.read())


def read_pgtp_text(path) -> str:
    """Read the file at `path` as CESU-8-repaired UTF-8 text (for display in
    the raw editor). Raises OSError if the file cannot be read."""
    return read_pgtp_bytes(path).decode("utf-8")
