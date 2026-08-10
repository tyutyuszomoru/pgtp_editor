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

# pgtp_editor/db/activity_log.py
"""The Activity Log's pure core (FQ-019): a timestamped journal of every file
and database action, persisted per project as `<project>/.ddlproject/
activity.jsonl` and kept session-only when no project is open.

**Qt-free on purpose.** This module is the whole of the feature's logic --
the entry shape, the source taxonomy, the JSONL store and the dynamic
timestamp format -- so all of it is unit-testable without a widget. The dock
panel, the debounce `QTimer` and the `CodeEditorDialog` click-through viewer
are a thin layer on top; nothing here imports or knows about them.

**Not derived from `debuglog`.** The log is emitted explicitly at each action's
completion point through `ActivityLog.record(...)`. Scraping the developer
logging stream for `"file: save %s"`-shaped records was considered and rejected
as fragile string-parsing.

**The source label doubles as the persistence indicator.** The four sources
encode a mode distinction, not a file-type one:

===============  =======================================  ==================
source           meaning                                  persistence
===============  =======================================  ==================
`Quality DB`     the target connection (`settings.target`) project-scoped
                                                          *when* a project is
                                                          open; occurs in
                                                          either mode
`Sandbox DB`     the sandbox connection                   project-scoped
`Project files`  files under a DDL project, saved via     project-scoped
                 the standard deployment pipeline
`Quality files`  standalone editing -- a `.pgtp` or       session-only,
                 `.php` opened directly with no project   **never written**
===============  =======================================  ==================

That relationship is encoded here in `is_persistable` rather than left to each
of the ~8 call sites to remember: a `Quality files` entry is refused by the
writer even if a project happens to be open, and nothing at all is written
while `ActivityLog.project_dir` is `None`. A caller may therefore `record(...)`
unconditionally and never think about the mode.

**Full text is retained, previews are derived.** The panel shows only the first
20 characters of the DDL and of an error message, but clicking a row opens the
untruncated text in a read-only viewer -- so the store keeps `ddl_full` and
`error_full` verbatim and `ddl_preview`/`error_preview` are computed from them
(`ActivityEntry.ddl_preview`). Deriving rather than storing them is the one
place this module departs from the queue entry's literal field list: two copies
of the same string in a persisted record can only drift, and the derivation is
total. A reader still accepts (and ignores) stored preview keys.

**The timestamp format is a property of the SET, not of an entry.** `HH:MM`
while the whole displayed log's oldest and newest entry fall in the same
calendar day; `YYYY-MM-DD HH:MM` as soon as they do not. Hence
`timestamp_format(entries)` takes the collection and every row of one render
must be formatted with its single answer -- recomputed when a new entry extends
the span. No seconds: two actions in the same minute render identically, which
is acceptable for a human journal.

**On-disk shape** -- JSONL, one object per line, appended in chronological
order, no envelope and no version header (a line is self-describing and a
reader that meets an unknown key ignores it):

    {"timestamp": "2026-08-08T14:03:11.482", "source": "Sandbox DB",
     "verb": "Apply to Sandbox", "ddl_full": "CREATE OR REPLACE ...",
     "file_verb": null, "status": "error", "error_full": "syntax error ..."}

Timestamps are naive local-time ISO-8601 (`datetime.isoformat`), matching how
the user reads the panel; the store is per project and never shared across
machines, so no timezone conversion is attempted.

**Reads never raise, and loading never rewrites.** Following
`db/bookmark_store.py`: a missing, unreadable or malformed file, a line that is
not JSON, a line that is not an object, a bad timestamp or an unknown source
all degrade to "that entry does not exist" -- and if nothing survives, to "no
history". A load that drops half the file leaves the file exactly as it was;
only `record` + a flush ever write. A raise here would land in a UI callback at
the end of a successful deployment, which is the worst possible moment.

**Writes are append-only on the happy path.** `ActivityLog.flush()` appends
just the entries recorded since the last flush -- the debounced write the host
drives from a timer, plus a synchronous flush on project transition and in
`closeEvent`, exactly the bookmark store's cadence. `save_activity` rewrites
the whole file and exists for the rare full-rewrite case (pruning); the normal
path never reads the file back to write it.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .ddl_project import SETTINGS_DIRNAME, _ensure_gitignored

#: The journal's filename -- a sibling of `settings.json` and `bookmarks.json`
#: inside the project's already-gitignored `.ddlproject/` directory.
ACTIVITY_FILENAME = "activity.jsonl"

# --- the source taxonomy (four values, one per entry) ------------------------
#: The target DB connection (`ProjectSettings.target`; the §18.8 "Quality" node).
SOURCE_QUALITY_DB = "Quality DB"
#: The sandbox DB connection (`ProjectSettings.sandbox`).
SOURCE_SANDBOX_DB = "Sandbox DB"
#: Files saved locally as part of a DDL project via the deployment pipeline.
SOURCE_PROJECT_FILES = "Project files"
#: Standalone mode -- a `.pgtp` or `.php` opened directly, with no project.
SOURCE_QUALITY_FILES = "Quality files"

SOURCES = (
    SOURCE_QUALITY_DB,
    SOURCE_SANDBOX_DB,
    SOURCE_PROJECT_FILES,
    SOURCE_QUALITY_FILES,
)

#: The one source that is session-only by definition: it *means* "no project is
#: open", so it can never have a project store to be written to.
SESSION_ONLY_SOURCES = frozenset({SOURCE_QUALITY_FILES})

# --- the action set ----------------------------------------------------------
#: An ad-hoc run against the sandbox (`db/sandbox_query.py`).
VERB_RAN = "ran"
#: A check/lint pass (`db/ddl_check.py`).
VERB_LINTED = "linted"

#: `VERB_APPLY_SANDBOX` / `VERB_APPLY_TARGET` are DELIBERATELY GONE (BUG-047).
#:
#: They held `"Apply to Sandbox"` and `"Apply to Target"` -- two of the eight
#: user-visible names FQ-026 retired -- so the journal printed a vocabulary no
#: menu, dialog or manual page spoke. They are not "verbs the journal owns":
#: they are the NAMES OF TWO GESTURES, and FQ-026's invariant (stated at
#: `ui/ddl_object_editor.py::GESTURE_LABELS`) is *one name per operation, used
#: identically across every surface* -- the Activity Log verb included.
#:
#: Do NOT restore them, not even re-pointed at the current names. This module is
#: Qt-free on purpose and `GESTURE_LABELS` lives in `ui/`, which imports PySide6;
#: `db/` must not import `ui/`. A constant here could therefore only ever be a
#: SECOND literal copy of a gesture name, free to drift again -- precisely the
#: defect FQ-026 exists to end. The gesture names are passed in from the call
#: sites in `ui/main_window.py`, which read `GESTURE_LABELS` directly.
#:
#: `VERB_RAN` / `VERB_LINTED` stay: they are not gesture names but lowercase
#: descriptions of what happened, so the invariant does not reach them.

DB_VERBS = (VERB_RAN, VERB_LINTED)

FILE_VERB_SAVED = "Saved"
FILE_VERB_OPENED = "Opened"
FILE_VERB_REVERTED = "Reverted"
FILE_VERB_MERGED = "Merged"
FILE_VERB_LINTED = "Linted"

FILE_VERBS = (
    FILE_VERB_SAVED,
    FILE_VERB_OPENED,
    FILE_VERB_REVERTED,
    FILE_VERB_MERGED,
    FILE_VERB_LINTED,
)

# --- status ------------------------------------------------------------------
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

STATUSES = (STATUS_SUCCESS, STATUS_ERROR)

# --- rendering ---------------------------------------------------------------
#: How many characters of the DDL / of an error message the panel shows before
#: the click-through viewer is needed.
PREVIEW_CHARS = 20
#: Appended when a preview was truncated (a single character, not "...").
PREVIEW_ELLIPSIS = "…"

#: The ONE timestamp shape, on every row, always (owner decision 2026-08-09).
#:
#: FQ-019 originally specified a DYNAMIC format -- `HH:MM` while the log's
#: oldest and newest entry fell on one calendar day, `YYYY-MM-DD HH:MM` the
#: moment they did not -- which made the format a property of the SET rather
#: than of an entry. That is an awkward contract to hold: one entry arriving
#: after midnight silently reshapes every row already on screen, so a panel
#: could never cache a rendered row and had to re-render the whole list on
#: every append. The owner dropped it for one unambiguous format.
#:
#: `TIME_FORMAT_SAME_DAY` is deliberately GONE rather than kept unused -- a
#: second format string in this module is what would invite the dynamic
#: behaviour back.
TIME_FORMAT = "%Y-%m-%d %H:%M"

#: The pre-decision name, aliased so nothing that already reached for it breaks.
#: New code should use `TIME_FORMAT`.
TIME_FORMAT_MULTI_DAY = TIME_FORMAT


def preview(text: str | None) -> str:
    """The first `PREVIEW_CHARS` characters of `text`, plus an ellipsis when
    something was cut off. `None` and `""` both give `""`.

    Truncation is by **character**, not byte, so a multi-byte character is
    never split (Python slices `str` by code point -- this is a property worth
    naming because the store round-trips through UTF-8 bytes). Runs of
    whitespace -- overwhelmingly the newlines and indentation of a `CREATE OR
    REPLACE FUNCTION` body -- collapse to single spaces first, so a preview is
    always one line's worth of signal rather than 20 characters of leading
    indentation.
    """
    if not text:
        return ""
    flat = " ".join(str(text).split())
    if len(flat) <= PREVIEW_CHARS:
        return flat
    return flat[:PREVIEW_CHARS] + PREVIEW_ELLIPSIS


def is_persistable(source: str, project_open: bool) -> bool:
    """Whether an entry from `source` belongs in a project's `activity.jsonl`.

    The single encoding of the queue entry's "the source label doubles as the
    persistence indicator" rule, so no call site has to remember it: nothing is
    persisted without a project, and `Quality files` -- which *means* standalone
    -- is refused even if one is somehow open.
    """
    return bool(project_open) and source not in SESSION_ONLY_SOURCES


@dataclass(frozen=True)
class ActivityEntry:
    """One journalled action: what happened, when, on which connection or in
    which mode, and whether it succeeded.

    Exactly one of `verb` (a DB action) and `file_verb` (a file action) is
    normally set -- the DB rows carry a DDL payload, the file rows carry the
    verb *as* the payload -- but the shape does not enforce it: a future action
    that is both is representable, and a row that is neither still renders.
    `ddl_full` and `error_full` hold the **untruncated** text; the previews the
    panel shows are derived (see the module docstring).
    """

    timestamp: datetime
    source: str
    verb: str | None = None
    ddl_full: str | None = None
    file_verb: str | None = None
    status: str = STATUS_SUCCESS
    error_full: str | None = None

    @property
    def ddl_preview(self) -> str:
        """The panel's 20-character DDL cell (`""` for a file row)."""
        return preview(self.ddl_full)

    @property
    def error_preview(self) -> str:
        """The panel's 20-character error cell (`""` on success)."""
        return preview(self.error_full)

    @property
    def failed(self) -> bool:
        return self.status == STATUS_ERROR

    @property
    def session_only(self) -> bool:
        """True when this entry can never be persisted, whatever the mode."""
        return self.source in SESSION_ONLY_SOURCES

    def to_json_dict(self) -> dict[str, object]:
        """The stored form: full text, no previews (they are derived on read)."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "verb": self.verb,
            "ddl_full": self.ddl_full,
            "file_verb": self.file_verb,
            "status": self.status,
            "error_full": self.error_full,
        }

    def to_json_line(self) -> str:
        """One JSONL line, no trailing newline. `ensure_ascii=False` keeps
        non-ASCII DDL and error text readable in the file."""
        return json.dumps(self.to_json_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json_dict(cls, raw: object) -> "ActivityEntry | None":
        """Rebuild an entry, or `None` if `raw` is not a usable record.

        Never raises. A non-object, a missing/unparseable timestamp, or a
        source outside the taxonomy all yield `None` -- the caller drops that
        line and keeps the rest. Unknown keys (including `ddl_preview` /
        `error_preview` written by a future or foreign writer) are ignored.
        """
        if not isinstance(raw, dict):
            return None
        stamp = _parse_timestamp(raw.get("timestamp"))
        if stamp is None:
            return None
        source = raw.get("source")
        if source not in SOURCES:
            return None
        status = raw.get("status")
        if status not in STATUSES:
            status = STATUS_SUCCESS
        return cls(
            timestamp=stamp,
            source=source,
            verb=_text_or_none(raw.get("verb")),
            ddl_full=_text_or_none(raw.get("ddl_full")),
            file_verb=_text_or_none(raw.get("file_verb")),
            status=status,
            error_full=_text_or_none(raw.get("error_full")),
        )


# --- the timestamp format ----------------------------------------------------
def timestamp_format(entries: Iterable[ActivityEntry] = ()) -> str:
    """`TIME_FORMAT`, whatever is passed.

    It still accepts `entries` so call sites written against the dynamic design
    keep working, but the argument is ignored and there is no set-wide state
    left: a row's text depends only on that row, so a panel may render on append
    and cache freely.
    """
    del entries  # the format no longer depends on the collection
    return TIME_FORMAT


def format_timestamp(stamp: datetime, fmt: str = TIME_FORMAT) -> str:
    """One timestamp cell."""
    return stamp.strftime(fmt)


def format_timestamps(entries: Sequence[ActivityEntry]) -> list[str]:
    """Every entry's timestamp cell."""
    return [format_timestamp(entry.timestamp) for entry in entries]


def render_row(entry: ActivityEntry, fmt: str = TIME_FORMAT) -> str:
    """The settled rendered form, `[timestamp] - [source] [verb] [payload]
    [status]`, as plain text -- what a QListWidget row shows and what a copy of
    the panel yields.

    `fmt` used to have to come from `timestamp_format` over the whole displayed
    set; since the format is fixed it defaults, and a row can be rendered on its
    own without knowing what else is on screen.

    The payload is the DDL preview for a DB row and the file verb for a file
    row; on error the error preview is appended after the status.
    """
    parts = [format_timestamp(entry.timestamp, fmt), "-", entry.source]
    if entry.verb:
        parts.append(entry.verb)
    if entry.ddl_preview:
        parts.append(entry.ddl_preview)
    if entry.file_verb:
        parts.append(entry.file_verb)
    parts.append(entry.status)
    if entry.error_preview:
        parts.append(entry.error_preview)
    return " ".join(parts)


def render_rows(entries: Sequence[ActivityEntry]) -> list[str]:
    """Every row of one render, sharing one timestamp format."""
    fmt = timestamp_format(entries)
    return [render_row(entry, fmt) for entry in entries]


# --- JSONL (de)serialization -------------------------------------------------
def serialize_entries(entries: Iterable[ActivityEntry]) -> str:
    """The entries as JSONL text, one object per line, each line newline
    terminated (so an empty log serializes to `""` and appending is a plain
    concatenation)."""
    return "".join(entry.to_json_line() + "\n" for entry in entries)


def parse_jsonl(text: str) -> list[ActivityEntry]:
    """Every usable entry in `text`, in file order.

    Never raises. Blank lines are skipped; a line that is not JSON, not an
    object, or not a usable record is dropped -- including a half-written final
    line from a process killed mid-flush -- and the surviving lines are still
    returned. Nothing is rewritten as a side effect.
    """
    entries: list[ActivityEntry] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        entry = ActivityEntry.from_json_dict(raw)
        if entry is not None:
            entries.append(entry)
    return entries


# --- the per-project store ---------------------------------------------------
def activity_path(project_dir: Path | str) -> Path:
    """The journal's path for `project_dir`."""
    return Path(project_dir) / SETTINGS_DIRNAME / ACTIVITY_FILENAME


def load_activity(project_dir: Path | str) -> list[ActivityEntry]:
    """That project's persisted history, oldest first.

    Never raises and never writes: a missing or unreadable file, or one whose
    every line is junk, is "no history". Undecodable bytes are read with
    `errors="replace"` rather than discarding the whole file -- a single
    corrupted byte should cost at most the line it is on.
    """
    path = activity_path(project_dir)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return []
    return parse_jsonl(text)


def append_activity(project_dir: Path | str, entries: Iterable[ActivityEntry]) -> None:
    """Append entries to the project's journal, creating it if needed.

    The normal write path -- the debounced flush -- because JSONL appends
    without reading the file back. Entries whose source is session-only are
    dropped (see `is_persistable`), and a call with nothing left to write
    creates no file.
    """
    writable = [entry for entry in entries if is_persistable(entry.source, True)]
    if not writable:
        return
    project_dir = Path(project_dir)
    path = activity_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(serialize_entries(writable))
    _ensure_gitignored(project_dir, f"{SETTINGS_DIRNAME}/")


def save_activity(project_dir: Path | str, entries: Iterable[ActivityEntry]) -> None:
    """Rewrite the whole journal -- for the rare full-rewrite case (pruning, a
    deliberate clear). The append path above is what routine logging uses.

    An empty result truncates an existing file and does *not* create one that
    is absent: a project nobody acted in carries no journal at all.
    """
    writable = [entry for entry in entries if is_persistable(entry.source, True)]
    project_dir = Path(project_dir)
    path = activity_path(project_dir)
    if not writable and not path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_entries(writable), encoding="utf-8")
    _ensure_gitignored(project_dir, f"{SETTINGS_DIRNAME}/")


class ActivityLog:
    """The in-memory journal every emit point calls, and the only thing that
    decides whether anything reaches disk.

    One instance lives for the app's lifetime. `record(...)` is the single
    entry point (~8 call sites: file save/open/revert, merge, sandbox run,
    check, and the two Apply actions); it appends unconditionally and is safe
    in any mode. The host then drives `flush()` from a debounce timer and
    synchronously on project transition and app close -- the cadence
    `db/bookmark_store.py` established.

    **Mode lives in `project_dir`.** `None` means standalone: entries stay in
    the buffer, `flush` writes nothing, and `close_project` / `open_project`
    discard them -- the queue entry's "dies with the session". With a project
    open, `flush` appends everything recorded since the last flush.
    """

    def __init__(self, project_dir: Path | str | None = None):
        self._project_dir: Path | None = Path(project_dir) if project_dir else None
        self._entries: list[ActivityEntry] = []
        self._pending: list[ActivityEntry] = []
        if self._project_dir is not None:
            self._entries = load_activity(self._project_dir)

    # -- state ---------------------------------------------------------------
    @property
    def project_dir(self) -> Path | None:
        """The open project's folder, or `None` in standalone mode."""
        return self._project_dir

    @property
    def entries(self) -> tuple[ActivityEntry, ...]:
        """The whole displayed log, oldest first (persisted history plus this
        session's entries). This is what `timestamp_format` is computed over."""
        return tuple(self._entries)

    @property
    def has_pending_writes(self) -> bool:
        """Whether a flush would write anything -- the debounce timer's guard."""
        return bool(self._pending) and self._project_dir is not None

    def __len__(self) -> int:
        return len(self._entries)

    # -- recording -----------------------------------------------------------
    def record(
        self,
        source: str,
        verb: str | None = None,
        *,
        ddl: str | None = None,
        file_verb: str | None = None,
        status: str = STATUS_SUCCESS,
        error: str | None = None,
        timestamp: datetime | None = None,
    ) -> ActivityEntry:
        """Journal one completed action and return the entry.

        `timestamp` defaults to now (injectable so tests -- and a replayed
        batch -- are deterministic). Passing an `error` implies
        `status=STATUS_ERROR`, so a caller cannot report a failure that renders
        as a success. The entry is appended to the display buffer and queued
        for the next flush; whether that flush writes is decided later, by the
        mode, not here.
        """
        if error:
            status = STATUS_ERROR
        entry = ActivityEntry(
            timestamp=timestamp or datetime.now(),
            source=source,
            verb=verb,
            ddl_full=ddl,
            file_verb=file_verb,
            status=status if status in STATUSES else STATUS_SUCCESS,
            error_full=error or None,
        )
        self._entries.append(entry)
        self._pending.append(entry)
        return entry

    # -- persistence ---------------------------------------------------------
    def flush(self) -> bool:
        """Write everything recorded since the last flush; return whether
        anything reached disk.

        In standalone mode the pending queue is simply cleared -- the entries
        stay visible in `entries` for the rest of the session but were never
        destined for a file. Safe to call at any time, including when nothing
        is pending.
        """
        pending, self._pending = self._pending, []
        if self._project_dir is None or not pending:
            return False
        writable = [e for e in pending if is_persistable(e.source, True)]
        if not writable:
            return False
        append_activity(self._project_dir, writable)
        return True

    def open_project(self, project_dir: Path | str) -> None:
        """Project transition: flush what the previous mode owed, then replace
        the buffer with the new project's persisted history.

        Standalone entries do not follow the user into the project -- they
        belong to a session that had no project -- which is also why the flush
        above cannot leak them into the new store.
        """
        self.flush()
        self._project_dir = Path(project_dir)
        self._entries = load_activity(self._project_dir)
        self._pending = []

    def close_project(self) -> None:
        """The other half of the transition: flush, then drop back to a clean
        standalone buffer."""
        self.flush()
        self._project_dir = None
        self._entries = []
        self._pending = []

    # -- rendering helpers ---------------------------------------------------
    def timestamp_format(self) -> str:
        """`TIME_FORMAT`. Kept as a method so a caller need not import the
        constant; there is nothing per-set left to compute."""
        return timestamp_format(self._entries)

    def rendered_rows(self) -> list[str]:
        """Every row as plain text, all sharing one timestamp format."""
        return render_rows(self._entries)


def _parse_timestamp(raw: object) -> datetime | None:
    """A stored ISO-8601 timestamp, or `None` if it is missing or unparseable."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _text_or_none(raw: object) -> str | None:
    """A stored optional string, normalising anything else (including `null`
    and a number a foreign writer put there) to `None`."""
    return raw if isinstance(raw, str) and raw else None
