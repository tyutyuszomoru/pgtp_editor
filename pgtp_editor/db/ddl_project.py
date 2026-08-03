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

# pgtp_editor/db/ddl_project.py
"""Local DDL-versioning projects (§18.2): the project-settings JSON shape,
the `ddl/*.sql` per-object path-naming scheme, and content-hash drift
comparison.

A **local project is a plain folder the user chooses** -- not necessarily a
git repository (git is optional/deferred, §18.2). This module owns every
piece of that folder's own state:

- `ProjectSettings` -- the project's ENTIRE state, one centralized,
  plaintext, gitignored JSON file (`<project>/.ddlproject/settings.json`).
  Nothing project-scoped lives anywhere else: no QSettings, no second file.
  Governing principle, owner's words: *"nothing the app manages should be a
  black box... plaintext files everywhere."*
- The `object -> ddl/<schema>.<name>[_<n>].sql` path scheme, disambiguating
  overloaded routines with a numeric `_1` suffix (never argument types, which
  render characters illegal/awkward on Windows) -- a **pure function of the
  whole current overload set**, never stored, so it is always recomputable.
- Content-hash comparison, the mechanism behind the `*`/`!` drift markers and
  the `.pgtp` working-copy-vs-source checksum comparison (§18.2).

Qt-free and DB-free, mirroring `db/ddl_buffer.py`'s precedent: this module
does read/write the project's own settings file and `ddl/` folder (unlike
`ddl_buffer.py`, which does no I/O at all), but it never imports Qt and never
opens a database connection -- everything here is unit-testable with plain
files on disk.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConnectionParams
from .introspect import DatabaseSchema, RoutineInfo

#: The project's settings file -- one centralized, gitignored, plaintext
#: JSON holding everything project-scoped (§18.2 "Project settings").
SETTINGS_DIRNAME = ".ddlproject"
SETTINGS_FILENAME = "settings.json"

#: Characters illegal or awkward on Windows filesystems/shells (§18.2 file
#: naming). Argument types are never put in filenames for exactly this
#: reason -- `character varying[]` renders several of these.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


@dataclass(frozen=True)
class PgtpLink:
    """The project's optional `.pgtp` link (§18.2, "a project may have zero,
    one pre-existing, or one newly-created `.pgtp`") -- now a first-class
    checked-out artifact, parallel to a DDL object: a working copy the app
    edits, plus the checksum of the sshfs-mounted source last time it was
    compared (recomputed fresh on every project load, never trusted stale).
    """

    source_path: str | None = None
    working_copy_path: str | None = None
    last_known_source_checksum: str | None = None


@dataclass(frozen=True)
class DeployedObject:
    """One DDL object's last-deployed reference (§18.2 "last-deployed
    reference"). `content_hash` is the mechanism actually used for every
    drift comparison; `deployed_commit` is kept purely for human
    traceability once git integration exists (TBD) and is never consulted by
    the comparison logic itself."""

    content_hash: str
    deployed_commit: str | None = None


@dataclass(frozen=True)
class GitConfig:
    """Captured intent only -- explicit TBD/placeholder (§18.2 "Git is
    optional and TBD"). Nothing reads these fields yet: no commit, no push,
    no clone, no worktree machinery. Recorded purely so a user who fills
    this in during New Project doesn't lose that intent once git
    integration is actually designed."""

    server: str = ""
    user: str = ""
    checkout_branch: str = ""


@dataclass(frozen=True)
class ProjectSettings:
    """The project's entire state (§18.2 "Project settings"). Keyed
    per-object entries in `deployed` use the same `ddl/*.sql` relative path
    (POSIX-style) that `routine_ddl_paths`/`trigger_ddl_path` compute, so the
    manifest and the checked-out files always agree on identity."""

    name: str = ""
    description: str = ""
    pgtp: PgtpLink = field(default_factory=PgtpLink)
    target: ConnectionParams = field(default_factory=ConnectionParams)
    sandbox: ConnectionParams = field(default_factory=ConnectionParams)
    git: GitConfig = field(default_factory=GitConfig)
    deployed: dict[str, DeployedObject] = field(default_factory=dict)


def settings_path(project_dir: Path | str) -> Path:
    """The one settings file's path for `project_dir` -- never a second file."""
    return Path(project_dir) / SETTINGS_DIRNAME / SETTINGS_FILENAME


def load_settings(project_dir: Path | str) -> ProjectSettings:
    """Load a project's settings, or a fresh default `ProjectSettings` if the
    file doesn't exist yet (a brand-new project has none until first save)."""
    path = settings_path(project_dir)
    if not path.exists():
        return ProjectSettings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _settings_from_dict(raw)


def save_settings(project_dir: Path | str, settings: ProjectSettings) -> None:
    """Write the settings file (plaintext, human-diffable) and make sure the
    project's `.gitignore` excludes it -- the file holds the password, and is
    gitignored *instead of* QSettings-hidden, never both (§18.2)."""
    project_dir = Path(project_dir)
    path = settings_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_settings_to_dict(settings), indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    _ensure_gitignored(project_dir, f"{SETTINGS_DIRNAME}/")


def _settings_to_dict(settings: ProjectSettings) -> dict:
    return {
        "name": settings.name,
        "description": settings.description,
        "pgtp": {
            "source_path": settings.pgtp.source_path,
            "working_copy_path": settings.pgtp.working_copy_path,
            "last_known_source_checksum": settings.pgtp.last_known_source_checksum,
        },
        "target": _connection_to_dict(settings.target),
        "sandbox": _connection_to_dict(settings.sandbox),
        "git": {
            "server": settings.git.server,
            "user": settings.git.user,
            "checkout_branch": settings.git.checkout_branch,
        },
        "deployed": {
            relpath: {
                "content_hash": entry.content_hash,
                "deployed_commit": entry.deployed_commit,
            }
            for relpath, entry in settings.deployed.items()
        },
    }


def _connection_to_dict(params: ConnectionParams) -> dict:
    return {
        "host": params.host,
        "port": params.port,
        "database": params.database,
        "user": params.user,
        "password": params.password,
    }


def _settings_from_dict(raw: dict) -> ProjectSettings:
    pgtp_raw = raw.get("pgtp") or {}
    deployed_raw = raw.get("deployed") or {}
    return ProjectSettings(
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        pgtp=PgtpLink(
            source_path=pgtp_raw.get("source_path"),
            working_copy_path=pgtp_raw.get("working_copy_path"),
            last_known_source_checksum=pgtp_raw.get("last_known_source_checksum"),
        ),
        target=ConnectionParams(**{**_connection_defaults(), **(raw.get("target") or {})}),
        sandbox=ConnectionParams(**{**_connection_defaults(), **(raw.get("sandbox") or {})}),
        git=GitConfig(**{**_git_defaults(), **(raw.get("git") or {})}),
        deployed={
            relpath: DeployedObject(
                content_hash=entry["content_hash"],
                deployed_commit=entry.get("deployed_commit"),
            )
            for relpath, entry in deployed_raw.items()
        },
    )


def _connection_defaults() -> dict:
    return {"host": "", "port": "", "database": "", "user": "", "password": ""}


def _git_defaults() -> dict:
    return {"server": "", "user": "", "checkout_branch": ""}


def _ensure_gitignored(project_dir: Path, entry: str) -> None:
    """Append `entry` to `project_dir/.gitignore` if it isn't already
    covered (exact line match, or a directory-form match for a `dir/`
    entry) -- idempotent, never duplicates, never touches unrelated lines."""
    gitignore = project_dir / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    stripped = entry.rstrip("/")
    already_covered = any(
        line.strip().rstrip("/") == stripped for line in lines
    )
    if already_covered:
        return
    lines.append(entry)
    gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sanitize_filename_component(text: str) -> str:
    """Replace characters illegal/awkward on Windows filesystems/shells with
    `_` (§18.2 file naming). Applied to each `.`-joined component, never to
    the joining dots themselves."""
    return _ILLEGAL_FILENAME_CHARS.sub("_", text)


def routine_ddl_paths(routines: dict[str, RoutineInfo]) -> dict[str, str]:
    """Map each routine's `signature` (the `DatabaseSchema.routines` key) to
    its `ddl/<schema>.<name>[_<n>].sql` relative path (POSIX-style `/`) --
    computed **fresh from the whole set every time**, never stored, so the
    numbering is always recomputable (§18.2 "Path computation is pure").

    Overloads sharing a `schema.name` are ordered by their argument-type
    tuple -- Python's native tuple comparison already sorts strings
    lexicographically element-by-element with shorter-tuples-first-on-a-
    common-prefix, exactly the ordering the spec requires (`f()` <
    `f(integer)` < `f(integer, text)` < `f(text)`). The **first** overload in
    that order keeps the unsuffixed name; suffixes start at `_1` for the
    second.
    """
    by_qualified: dict[tuple[str, str], list[RoutineInfo]] = {}
    for routine in routines.values():
        by_qualified.setdefault((routine.schema, routine.name), []).append(routine)

    paths: dict[str, str] = {}
    for (schema, name), group in by_qualified.items():
        ordered = sorted(group, key=lambda r: tuple(r.arg_types))
        base = f"{sanitize_filename_component(schema)}.{sanitize_filename_component(name)}"
        for index, routine in enumerate(ordered):
            suffix = "" if index == 0 else f"_{index}"
            paths[routine.signature] = f"ddl/{base}{suffix}.sql"
    return paths


def trigger_ddl_path(schema: str, table: str, name: str) -> str:
    """A trigger's `ddl/<schema>.<table>.<trigger>.sql` path -- always
    table-qualified (a trigger name is unique only per table), needing no
    overload disambiguation and so no whole-set computation."""
    parts = (schema, table, name)
    joined = ".".join(sanitize_filename_component(part) for part in parts)
    return f"ddl/{joined}.sql"


#: Matches the `CREATE [OR REPLACE] FUNCTION|PROCEDURE schema.name(` prefix
#: of a `pg_get_functiondef` header, up to but NOT including the argument
#: list -- the load-bearing recovery path for a checked-out file's identity
#: (§18.2: "the header is load-bearing"). The argument list itself is
#: extracted separately, by depth-tracking, since it may contain nested
#: parens (`numeric(10,2)`) a regex cannot balance.
_HEADER_PREFIX_RE = re.compile(
    r"""^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+
        (?:"(?P<qschema>[^"]+)"|(?P<schema>[\w]+))
        \.
        (?:"(?P<qname>[^"]+)"|(?P<name>[\w]+))
        \s*\(""",
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def parse_checked_out_header(text: str) -> str | None:
    """Recover a checked-out `ddl/*.sql` file's `schema.name(argtypes)`
    signature from its own `CREATE [OR REPLACE] FUNCTION/PROCEDURE` header --
    never from its filename (§18.2: `_1` is not self-describing; the header
    is the identity). Returns None if the header cannot be parsed -- callers
    must report this, never guess from the filename instead.

    Argument TYPES only (not names) are extracted, splitting each
    comma-separated argument on its last top-level space (`a integer` ->
    `integer`; a bare `integer` with no name -> `integer` unchanged) --
    matching `RoutineInfo.arg_types`, which is types-only. Commas nested
    inside a parenthesised type (`numeric(10,2)`) are not split, found by
    depth-tracking from the header's opening paren to its true balanced
    close (a regex cannot balance nested parens on its own).
    """
    match = _HEADER_PREFIX_RE.match(text)
    if match is None:
        return None
    schema = match.group("qschema") or match.group("schema")
    name = match.group("qname") or match.group("name")
    args_text = _extract_balanced_args(text, match.end())
    if args_text is None:
        return None
    arg_types = _split_top_level_args(args_text.strip()) if args_text.strip() else []
    return f"{schema}.{name}({', '.join(arg_types)})"


def _extract_balanced_args(text: str, args_start: int) -> str | None:
    """The substring between `args_start` (just after the header's opening
    paren) and that paren's true balanced close, or None if the text ends
    before the parens balance (a truncated/corrupted header)."""
    depth = 1
    for index in range(args_start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[args_start:index]
    return None


def _split_top_level_args(args_text: str) -> list[str]:
    """Split a `CREATE FUNCTION` argument list on top-level commas only
    (never inside a nested `(...)`, e.g. `numeric(10,2)`), then reduce each
    argument to its bare type by dropping a leading name if present."""
    parts: list[str] = []
    depth = 0
    current = ""
    for char in args_text:
        if char == "(":
            depth += 1
            current += char
        elif char == ")":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [_arg_type_only(part.strip()) for part in parts if part.strip()]


def _arg_type_only(arg: str) -> str:
    """`a integer` -> `integer`; a bare `integer` (no name) -> unchanged.

    Heuristic: PostgreSQL's `pg_get_functiondef` always emits `name type`
    for a named argument. A type can itself contain spaces (`character
    varying`, `double precision`), so this cannot simply take the last
    token -- instead it drops the first token only when what remains is
    still a recognizable type start (i.e. the argument has more than one
    token AND does not itself begin with a mode keyword this parser doesn't
    special-case). Kept deliberately simple: PGTP Editor's own
    `db/ddl_buffer.py` banners and `RoutineInfo.arg_types` never carry
    argument names, so this only needs to strip one leading identifier when
    a name is clearly present, not parse the full PostgreSQL type grammar.
    """
    tokens = arg.split(None, 1)
    if len(tokens) == 2 and not _looks_like_bare_type(arg):
        return tokens[1]
    return arg


#: Type keywords whose FIRST token is part of the type itself, not a name --
#: guards against stripping "character" off "character varying" as if
#: "character" were an argument name.
_TYPE_LEADING_WORDS = frozenset(
    {
        "character", "double", "bit", "time", "timestamp", "interval",
        "bigint", "smallint", "int", "integer", "text", "numeric", "boolean",
        "varchar", "real", "float", "date", "uuid", "json", "jsonb", "bytea",
    }
)


def _looks_like_bare_type(arg: str) -> bool:
    first_word = arg.split(None, 1)[0].lower()
    return first_word in _TYPE_LEADING_WORDS


@dataclass(frozen=True)
class Reconciliation:
    """The result of reconciling a fresh `routine_ddl_paths()` computation
    against what is actually checked out on disk (§18.2 "Reconciliation when
    the set changes")."""

    #: signature -> the CURRENT authoritative relpath (post-rename).
    paths: dict[str, str]
    #: (old_relpath, new_relpath) pairs that need renaming, in the order
    #: they should be applied.
    renames: tuple[tuple[str, str], ...]
    #: relpaths whose header could not be parsed back to a signature --
    #: must be reported, never silently guessed at from the filename.
    unparseable: tuple[str, ...]


def reconcile_routine_paths(
    routines: dict[str, RoutineInfo], existing_files: dict[str, str]
) -> Reconciliation:
    """Compare the fresh path assignment for `routines` against what is
    actually on disk (`existing_files`: relpath -> file text, as read from
    the `ddl/` folder) and determine what -- if anything -- must be renamed.

    An overload that is **added** only shifts later files if it sorts into
    the *middle* of an existing overload set; an overload that is **dropped**
    leaves its file in place, unrenumbered (§18.2) -- both fall out of this
    same comparison rather than needing separate cases: a dropped
    overload's old file simply has no signature in the fresh `paths`, so it
    is never mentioned in `renames`.
    """
    fresh_paths = routine_ddl_paths(routines)

    old_path_by_signature: dict[str, str] = {}
    unparseable: list[str] = []
    for relpath, text in existing_files.items():
        signature = parse_checked_out_header(text)
        if signature is None:
            unparseable.append(relpath)
            continue
        old_path_by_signature[signature] = relpath

    renames: list[tuple[str, str]] = []
    for signature, new_path in fresh_paths.items():
        old_path = old_path_by_signature.get(signature)
        if old_path is not None and old_path != new_path:
            renames.append((old_path, new_path))

    return Reconciliation(
        paths=fresh_paths,
        renames=tuple(sorted(renames)),
        unparseable=tuple(sorted(unparseable)),
    )


def content_hash(text: str) -> str:
    """The content-hash used for every drift comparison (§18.2 "last-deployed
    reference") -- `*` = hash(local file) != stored; `!` = hash(live DB
    definition) != stored. Must be computed the SAME way everywhere it's
    used (local file content, live DB introspection, the stored reference);
    this is the single implementation all three call.
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DriftMarkers:
    """One DDL object's `*`/`!` state (§18.2 "State markers") -- two
    independent booleans that render together when both are true (e.g.
    `*!`). There is no separate third state/symbol for "both."."""

    #: `*` -- the local `ddl/` file differs from the last-deployed reference.
    locally_edited: bool = False
    #: `!` -- the live DB definition differs from the last-deployed reference.
    live_drifted: bool = False

    @property
    def marker_text(self) -> str:
        """`""`, `"*"`, `"!"`, or `"*!"` -- never a third symbol."""
        text = ""
        if self.locally_edited:
            text += "*"
        if self.live_drifted:
            text += "!"
        return text


def compute_drift_markers(
    project_dir: Path | str, settings: ProjectSettings, schema: DatabaseSchema
) -> dict[str, DriftMarkers]:
    """For every DDL object with a last-deployed reference in
    `settings.deployed`, compute its `*`/`!` state fresh against the local
    `ddl/` file and the live `schema` -- never cached, never trusted from a
    prior session (§18.2 truth-model principle). Keyed by the same
    `ddl/*.sql` relative path `settings.deployed` itself uses.

    An object with no last-deployed reference at all (never deployed) has
    no entry here -- there is nothing to compare it against yet, which is
    distinct from "compared and found unchanged." An object that no longer
    exists in the live `schema` (dropped from the database) is reported as
    NOT live-drifted here -- there is no live definition to compare against,
    so this deliberately avoids manufacturing a false positive; its absence
    is a separate concern from content drift.
    """
    project_dir = Path(project_dir)
    routine_paths = routine_ddl_paths(schema.routines)
    live_hash_by_path: dict[str, str] = {}
    for routine in schema.routines.values():
        relpath = routine_paths.get(routine.signature)
        if relpath is not None:
            live_hash_by_path[relpath] = content_hash(routine.source)
    for trigger in schema.triggers.values():
        relpath = trigger_ddl_path(trigger.schema, trigger.table, trigger.name)
        live_hash_by_path[relpath] = content_hash(trigger.definition)

    markers: dict[str, DriftMarkers] = {}
    for relpath, entry in settings.deployed.items():
        local_path = project_dir / relpath
        locally_edited = False
        if local_path.exists():
            local_text = local_path.read_text(encoding="utf-8")
            locally_edited = content_hash(local_text) != entry.content_hash
        live_hash = live_hash_by_path.get(relpath)
        live_drifted = live_hash is not None and live_hash != entry.content_hash
        markers[relpath] = DriftMarkers(locally_edited=locally_edited, live_drifted=live_drifted)
    return markers
