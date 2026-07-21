"""Guard the PyInstaller exclusion list in optimized_build.py.

The build shrinks the bundle by excluding PySide6 submodules the app never
imports. The failure mode is asymmetric and silent: excluding a module the code
*does* import doesn't fail the build -- it produces an app that crashes (or, as
happened with QtSvg, silently loses its toolbar icons because the import error
is swallowed). This test statically discovers every PySide6 submodule the
pgtp_editor package imports and asserts none of them are on the exclude list.
"""
import ast
import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "pgtp_editor"


def _load_build_module():
    spec = importlib.util.spec_from_file_location(
        "optimized_build", REPO_ROOT / "optimized_build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pyside_submodules_imported() -> set[str]:
    """Every ``PySide6.<Sub>`` referenced by an import in the package source."""
    found: set[str] = set()
    for py in PACKAGE_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("PySide6."):
                    found.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("PySide6."):
                        found.add(alias.name)
    return found


def _top_level_modules_imported() -> set[str]:
    """Every top-level module name referenced by an import in the package source.

    ``import numpy.foo`` and ``from yaml import x`` both contribute their root
    (``numpy`` / ``yaml``) so this can be matched against EXCLUDED_MODULES.
    """
    found: set[str] = set()
    for py in PACKAGE_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
    return found


def test_no_imported_pyside_module_is_excluded():
    build = _load_build_module()
    excluded = set(build.EXCLUDED_QT_MODULES)
    imported = _pyside_submodules_imported()

    clash = imported & excluded
    assert not clash, (
        f"optimized_build.EXCLUDED_QT_MODULES excludes PySide6 module(s) the "
        f"app actually imports: {sorted(clash)}. Excluding an imported module "
        f"ships a broken bundle -- remove it from the exclude list."
    )


def test_guard_actually_sees_pyside_imports():
    # Sanity check that the static scan finds real imports (so the guard above
    # can't pass vacuously) -- QtSvg is imported by ui/icons.py.
    imported = _pyside_submodules_imported()
    assert "PySide6.QtSvg" in imported
    assert "PySide6.QtWidgets" in imported


def test_excluded_third_party_modules_not_imported():
    # numpy/yaml are excluded on the premise the app never imports them directly
    # (they're only reachable through optional branches of our dependencies).
    # If a future feature adds a direct import, excluding it would ship a broken
    # bundle -- flag that here so the exclusion gets revisited.
    build = _load_build_module()
    imported = _top_level_modules_imported()
    clash = set(build.EXCLUDED_MODULES) & imported
    assert not clash, (
        f"optimized_build.EXCLUDED_MODULES excludes module(s) the app now "
        f"imports directly: {sorted(clash)}. Excluding an imported module ships "
        f"a broken bundle -- remove it from EXCLUDED_MODULES."
    )


def test_excluded_modules_are_wired_into_build_args():
    # Both exclude lists must actually reach PyInstaller as --exclude-module
    # args; a list that isn't consumed silently stops shrinking the bundle.
    build = _load_build_module()
    src = inspect.getsource(build.build)
    assert "EXCLUDED_QT_MODULES" in src
    assert "EXCLUDED_MODULES" in src
    assert "--exclude-module" in src
