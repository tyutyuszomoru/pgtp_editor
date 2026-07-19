from pathlib import Path

from pgtp_editor.generation.re_runner import (
    PANGEN_SUBFOLDER,
    build_analyze_command,
    build_pangen_command,
    pangen_output_dir,
    resolve_re_phpgen_python,
    validate_re_phpgen_root,
)


def test_pangen_output_dir_is_sibling_subfolder():
    assert pangen_output_dir(r"C:\out") == str(Path(r"C:\out") / PANGEN_SUBFOLDER)


def test_resolve_python_prefers_repo_venv(tmp_path):
    venv_python = tmp_path / "venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"")
    assert resolve_re_phpgen_python(str(tmp_path)) == str(venv_python)


def test_resolve_python_falls_back_to_sys_executable(tmp_path):
    import sys
    assert resolve_re_phpgen_python(str(tmp_path)) == sys.executable


def test_validate_root_requires_package_dir(tmp_path):
    assert validate_re_phpgen_root(str(tmp_path)) is False
    (tmp_path / "src" / "re_phpgen").mkdir(parents=True)
    assert validate_re_phpgen_root(str(tmp_path)) is True


def test_build_pangen_command():
    cmd = build_pangen_command("py.exe", r"C:\p.pgtp", r"C:\out")
    assert cmd == ["py.exe", "-m", "re_phpgen", "pangen", r"C:\p.pgtp",
                   "--out", str(Path(r"C:\out") / PANGEN_SUBFOLDER)]


def test_build_analyze_command():
    cmd = build_analyze_command("py.exe", r"C:\p.pgtp", r"C:\out", r"C:\gap.json")
    assert cmd == ["py.exe", "-m", "re_phpgen", "analyze", r"C:\p.pgtp",
                   "--vendor", r"C:\out",
                   "--ours", str(Path(r"C:\out") / PANGEN_SUBFOLDER),
                   "--json", r"C:\gap.json"]
