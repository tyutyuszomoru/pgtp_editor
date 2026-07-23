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

import shutil
import subprocess

import pytest

from pgtp_editor.schema_learning import sync
from pgtp_editor.schema_learning.model import Model
from pgtp_editor.schema_learning.storage import team_repo_dir

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git CLI not available"
)


@pytest.fixture
def origin(tmp_path):
    origin_dir = tmp_path / "origin.git"
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "--bare", str(origin_dir)],
        check=True, capture_output=True,
    )
    return origin_dir


def _config(tmp_path, origin, name="clone"):
    return sync.SyncConfig(
        repo_url=str(origin), clone_dir=tmp_path / name, key_path=None
    )


def _model_file(tmp_path):
    model = Model()
    model.paths = {"Root": {
        "attributes": {}, "children": {}, "instance_count": 1,
        "order": [], "order_stable": True, "has_text": False,
    }}
    path = tmp_path / "schema_model.json"
    model.save(path)
    return path


def test_publish_then_visible_from_second_clone(tmp_path, origin):
    model_path = _model_file(tmp_path)
    published = sync.publish_model(
        _config(tmp_path, origin, "clone_a"), model_path, username="alice"
    )
    assert published == "models/alice.json"
    config_b = _config(tmp_path, origin, "clone_b")
    assert [p.name for p in sync.team_model_paths(config_b)] == ["alice.json"]


def test_publish_unchanged_returns_none(tmp_path, origin):
    model_path = _model_file(tmp_path)
    config = _config(tmp_path, origin)
    assert sync.publish_model(config, model_path, username="alice") is not None
    assert sync.publish_model(config, model_path, username="alice") is None


def test_fetch_master_roundtrip(tmp_path, origin):
    config = _config(tmp_path, origin, "admin")
    assert sync.fetch_master(config) is None
    master = Model.load(_model_file(tmp_path))
    assert sync.push_master(config, master) is True
    other = _config(tmp_path, origin, "user")
    fetched = sync.fetch_master(other)
    assert fetched is not None
    assert Model.load(fetched).paths.keys() == master.paths.keys()


def test_push_retry_rebases_on_concurrent_push(tmp_path, origin):
    model_path = _model_file(tmp_path)
    config_a = _config(tmp_path, origin, "clone_a")
    config_b = _config(tmp_path, origin, "clone_b")
    sync.publish_model(config_a, model_path, username="alice")
    # B clones, then A advances origin again -> B's push must rebase+retry.
    sync.ensure_repo(config_b)
    sync.publish_model(config_a, model_path, username="alice2")
    assert sync.publish_model(config_b, model_path, username="bob") == "models/bob.json"
    assert {p.name for p in sync.team_model_paths(config_a)} == {
        "alice.json", "alice2.json", "bob.json"
    }


def test_bad_url_raises_sync_error(tmp_path):
    config = sync.SyncConfig(
        repo_url=str(tmp_path / "missing.git"),
        clone_dir=tmp_path / "clone",
        key_path=None,
    )
    with pytest.raises(sync.SyncError):
        sync.ensure_repo(config)


def test_default_username_is_sanitized(monkeypatch):
    monkeypatch.setattr(sync.getpass, "getuser", lambda: "büro user!")
    assert sync.default_username() == "b_ro_user_"


def test_key_path_sets_git_ssh_command(tmp_path):
    recorded = {}

    def runner(args, **kwargs):
        recorded["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    config = sync.SyncConfig(
        repo_url="git@example:x.git", clone_dir=tmp_path / "c", key_path="k.pem"
    )
    sync._git(config, ["version"], cwd=None, runner=runner)
    assert 'ssh -i "k.pem"' in recorded["env"]["GIT_SSH_COMMAND"]
