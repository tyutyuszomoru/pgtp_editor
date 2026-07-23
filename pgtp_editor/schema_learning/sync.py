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

"""Qt-free git transport for team schema-model sharing.

The team repo contains ONLY schema model JSONs: models/<username>.json per
user plus master.json. This module shells out to the git CLI through an
injectable ``runner`` (tests pass a fake or drive a local file-path origin);
when a deploy-key path is configured every call gets a scoped
GIT_SSH_COMMAND. All failures raise SyncError with git's stderr — callers
(MainWindow) report via [Schema] audit lines and leave local state alone.
"""
from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class SyncError(Exception):
    pass


@dataclass
class SyncConfig:
    repo_url: str
    clone_dir: Path
    key_path: str | None = None


def default_username() -> str:
    """OS username sanitized to [A-Za-z0-9_-] for use as a filename."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser()) or "user"


def _git(config, args, cwd, runner=subprocess.run):
    env = os.environ.copy()
    if config.key_path:
        env["GIT_SSH_COMMAND"] = (
            f'ssh -i "{config.key_path}" -o IdentitiesOnly=yes '
            "-o StrictHostKeyChecking=accept-new"
        )
    completed = runner(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise SyncError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def ensure_repo(config, runner=subprocess.run) -> Path:
    """Clone the team repo if absent, else pull --rebase. Tolerates a brand
    new EMPTY remote (nothing to pull yet). Sets a local commit identity so
    commits work on machines without global git config."""
    clone_dir = Path(config.clone_dir)
    if not (clone_dir / ".git").exists():
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        _git(config, ["clone", config.repo_url, str(clone_dir)], cwd=None, runner=runner)
    else:
        try:
            _git(config, ["pull", "--rebase"], cwd=clone_dir, runner=runner)
        except SyncError as exc:
            # A just-created bare origin has no branch to pull from yet; the
            # first publish will create it. Anything else is a real failure
            # (e.g. an already-cloned repo whose upstream branch was deleted
            # or force-moved) and must not be swallowed, or fetch_master would
            # silently serve stale data. Distinguish the two deterministically
            # by asking the remote directly instead of pattern-matching
            # stderr: a brand-new remote genuinely has no branches at all.
            try:
                heads = _git(
                    config, ["ls-remote", "--heads", "origin"],
                    cwd=clone_dir, runner=runner,
                )
            except SyncError:
                raise exc from None
            if heads.strip():
                raise
    username = default_username()
    _git(config, ["config", "user.name", f"{username} (pgtp-editor)"],
         cwd=clone_dir, runner=runner)
    _git(config, ["config", "user.email", f"{username}@pgtp-editor.invalid"],
         cwd=clone_dir, runner=runner)
    return clone_dir


def _push_with_retry(config, clone_dir, runner, attempts=3):
    last = None
    for attempt in range(attempts):
        try:
            _git(config, ["push", "-u", "origin", "HEAD"], cwd=clone_dir, runner=runner)
            return
        except SyncError as exc:
            last = exc
            if attempt < attempts - 1:
                _git(config, ["pull", "--rebase"], cwd=clone_dir, runner=runner)
    raise last


def publish_model(config, model_path, username=None, runner=subprocess.run) -> str | None:
    """Copy the local model into models/<username>.json, commit, push (with
    pull-rebase retry). Returns the repo-relative path, or None when the
    published content is identical to what the repo already holds."""
    username = username or default_username()
    clone_dir = ensure_repo(config, runner=runner)
    models_dir = clone_dir / "models"
    models_dir.mkdir(exist_ok=True)
    shutil.copyfile(model_path, models_dir / f"{username}.json")
    rel_path = f"models/{username}.json"
    _git(config, ["add", "models/"], cwd=clone_dir, runner=runner)
    if not _git(
        config, ["status", "--porcelain", "--", rel_path], cwd=clone_dir, runner=runner
    ).strip():
        return None
    _git(config, ["commit", "-m", f"Publish annotations: {username}"],
         cwd=clone_dir, runner=runner)
    _push_with_retry(config, clone_dir, runner)
    return rel_path


def fetch_master(config, runner=subprocess.run) -> Path | None:
    """Pull and return the path to master.json, or None when the team has
    no merged master yet."""
    clone_dir = ensure_repo(config, runner=runner)
    master = clone_dir / "master.json"
    return master if master.exists() else None


def team_model_paths(config, runner=subprocess.run) -> list[Path]:
    """Pull and return every models/*.json, sorted by filename."""
    clone_dir = ensure_repo(config, runner=runner)
    models_dir = clone_dir / "models"
    return sorted(models_dir.glob("*.json")) if models_dir.exists() else []


def push_master(config, master_model, runner=subprocess.run) -> bool:
    """Write ``master_model`` as master.json, commit and push (with retry).
    Returns False when the master is unchanged (nothing pushed)."""
    clone_dir = ensure_repo(config, runner=runner)
    master_model.save(clone_dir / "master.json")
    _git(config, ["add", "master.json"], cwd=clone_dir, runner=runner)
    if not _git(
        config, ["status", "--porcelain", "--", "master.json"], cwd=clone_dir, runner=runner
    ).strip():
        return False
    _git(config, ["commit", "-m", "Merge team models into master"],
         cwd=clone_dir, runner=runner)
    _push_with_retry(config, clone_dir, runner)
    return True
