"""BUG-009: app/window icon and desktop-file identity (main.apply_app_identity).

Covers the fix for KDE/Wayland showing a generic placeholder icon instead of
the app's own icon in the taskbar and title bar, because the app never set a
window/application icon or desktop-file identity. Requires
QT_QPA_PLATFORM=offscreen (a real QApplication is constructed since the
identity setters are genuine QApplication static methods).
"""
from importlib.resources import files

import pytest

from pgtp_editor.main import (
    APPLICATION_NAME,
    DESKTOP_FILE_NAME,
    ORGANIZATION_NAME,
    apply_app_identity,
)


@pytest.fixture
def qapp_instance(qapp):
    # pytest-qt's `qapp` fixture provides a session-scoped QApplication;
    # reset the identity fields it may already carry from another test so
    # each test observes only what apply_app_identity sets.
    qapp.setApplicationName("")
    qapp.setOrganizationName("")
    qapp.setApplicationDisplayName("")
    qapp.setDesktopFileName("")
    qapp.setWindowIcon(__import__("PySide6.QtGui", fromlist=["QIcon"]).QIcon())
    return qapp


def test_apply_app_identity_sets_names(qapp_instance):
    apply_app_identity(qapp_instance)

    assert qapp_instance.applicationName() == APPLICATION_NAME
    assert qapp_instance.organizationName() == ORGANIZATION_NAME
    assert qapp_instance.applicationDisplayName() == APPLICATION_NAME
    assert qapp_instance.desktopFileName() == DESKTOP_FILE_NAME


def test_apply_app_identity_sets_nonnull_window_icon(qapp_instance):
    apply_app_identity(qapp_instance)

    icon = qapp_instance.windowIcon()
    assert not icon.isNull()


def test_apply_app_identity_is_noop_safe_on_fake_app(qapp):
    """A stand-in object without the QApplication API must not raise.

    Mirrors tests/test_main.py's _FakeApp seam: apply_app_identity is called
    from main() on whatever QApplication() returns, including test doubles.
    Depends on pytest-qt's `qapp` fixture (unused directly) purely to
    guarantee a real QApplication already exists in this worker process --
    `_load_app_icon()` builds a genuine QPixmap/QIcon, which requires one,
    even though `apply_app_identity` itself is being exercised against a
    fake `app` argument. In real usage this is always true: `main()`
    constructs a real QApplication before ever calling apply_app_identity.
    """

    class _FakeApp:
        def __init__(self):
            self.icon_set = None

        def setWindowIcon(self, icon):
            self.icon_set = icon

    fake = _FakeApp()
    apply_app_identity(fake)  # must not raise

    assert fake.icon_set is not None
    assert not fake.icon_set.isNull()


def test_app_icon_resource_is_packaged():
    """Packaging sanity check: the icon ships as package data.

    Guards against pyproject.toml's package-data glob silently excluding the
    icon from a built wheel (BUG-009's root cause included the icon existing
    on disk but never being listed in package-data).
    """
    resource = files("pgtp_editor") / "resources" / "app_icon.png"
    assert resource.is_file()
    assert len(resource.read_bytes()) > 0


def test_app_icon_svg_resource_is_packaged():
    resource = files("pgtp_editor") / "resources" / "app_icon.svg"
    assert resource.is_file()
    assert len(resource.read_bytes()) > 0
