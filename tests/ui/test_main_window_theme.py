"""MainWindow Light/Dark theme toggle: switches the app to Fusion + an
explicit light or dark palette either way (BUG-004: both states are real,
tested QPalettes -- there is no third "native/OS passthrough" state), keeping
the toolbar icons legible either way."""
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.theme import dark_palette, light_palette


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


@pytest.fixture
def _reset_app_theme():
    """Restore the app's original style + palette after each test so an
    app-global theme change here cannot leak into other tests."""
    app = QApplication.instance()
    original_style = app.style().objectName()
    original_palette = QPalette(app.palette())
    try:
        yield
    finally:
        app.setStyle(original_style)
        app.setPalette(original_palette)


def test_toggle_light_switches_to_fusion_and_keeps_icons(qtbot, _reset_app_theme, monkeypatch):
    """Fusion is genuinely requested via QApplication.setStyle("Fusion") --
    asserted via a spy rather than a post-hoc style().objectName() read-back,
    which is unreliable once ANY non-empty app-global stylesheet is applied
    (Qt wraps the style in an internal QStyleSheetStyle proxy whose
    objectName() is "" regardless of the underlying style). This is true for
    light now too, since the light theme also carries a qdarkstyle QSS
    (previously only the dark theme did, so this quirk was already present
    for dark and simply never exercised for light)."""
    calls = []
    monkeypatch.setattr(QApplication, "setStyle", lambda self, name: calls.append(name))
    window = MainWindow()
    qtbot.addWidget(window)
    calls.clear()  # only care about the toggle below, not MainWindow() construction

    window._on_light_theme_toggled(True)

    app = QApplication.instance()
    assert calls == ["Fusion"]
    assert app.palette().color(QPalette.ColorRole.Window).lightness() > 200
    icons = [action.icon() for action in window._toolbar_ui.command_actions]
    assert icons and all(not icon.isNull() for icon in icons)


def test_toggle_light_off_applies_real_dark_palette(qtbot, _reset_app_theme):
    """BUG-004: toggling off applies the app's own explicit dark_palette(),
    not whatever the native/OS style happened to render before Light Theme
    was ever turned on."""
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_light_theme_toggled(True)
    window._on_light_theme_toggled(False)

    app = QApplication.instance()
    # Dark mode wraps the style in QStyleSheetStyle (empty objectName) via the
    # qdarkstyle QSS (BUG-010) -- assert the dark state through stylesheet +
    # palette instead of the style name.
    assert app.styleSheet()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.WindowText):
        assert app.palette().color(role).rgb() == dark_palette().color(role).rgb()


def test_fresh_window_defaults_to_explicit_dark_palette(qtbot, _reset_app_theme):
    """A fresh install (no saved 'lightTheme' setting, default False) must
    start on the real dark_palette() too, not whatever the native style
    happened to already be rendering (BUG-004) -- _restore_theme applies the
    theme unconditionally now, for both True and False."""
    window = MainWindow()
    qtbot.addWidget(window)

    app = QApplication.instance()
    assert window._light_theme_action.isChecked() is False
    assert app.styleSheet()  # dark QSS applied (see note above)
    assert app.palette().color(QPalette.ColorRole.Window).rgb() == dark_palette().color(
        QPalette.ColorRole.Window
    ).rgb()


# -- BUG-004 gap coverage: persistence round-trip of the "lightTheme" bool ----


def test_toggle_on_persists_and_restores_light_theme(qtbot, tmp_path, _reset_app_theme, monkeypatch):
    """Toggling Light Theme on writes lightTheme=True; a NEW window reading
    the same settings restores the light state (checked action + light
    palette), i.e. the preference survives an app restart. Fusion is
    asserted via a setStyle spy rather than style().objectName() read-back,
    which is unreliable once a non-empty app-global stylesheet is applied
    (true for light now too -- see test_toggle_light_switches_to_fusion_and_keeps_icons)."""
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._light_theme_action.setChecked(True)  # fires _on_light_theme_toggled
    settings.sync()

    settings2 = _ini_settings(tmp_path)
    assert settings2.value("lightTheme", False, type=bool) is True

    calls = []
    monkeypatch.setattr(QApplication, "setStyle", lambda self, name: calls.append(name))
    window2 = MainWindow(settings=settings2)
    qtbot.addWidget(window2)
    app = QApplication.instance()
    assert window2._light_theme_action.isChecked() is True
    assert "Fusion" in calls
    assert app.palette().color(QPalette.ColorRole.Window).rgb() == light_palette().color(
        QPalette.ColorRole.Window
    ).rgb()


def test_toggle_off_persists_false_and_restores_dark(qtbot, tmp_path, _reset_app_theme):
    """On -> off round-trip: the stored bool flips back to False and a new
    window restores the explicit dark_palette() (BUG-004: not a native
    passthrough)."""
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._light_theme_action.setChecked(True)
    window._light_theme_action.setChecked(False)
    settings.sync()

    settings2 = _ini_settings(tmp_path)
    assert settings2.value("lightTheme", True, type=bool) is False

    window2 = MainWindow(settings=settings2)
    qtbot.addWidget(window2)
    app = QApplication.instance()
    assert window2._light_theme_action.isChecked() is False
    assert app.palette().color(QPalette.ColorRole.Window).rgb() == dark_palette().color(
        QPalette.ColorRole.Window
    ).rgb()


def test_restore_theme_from_preseeded_light_setting(qtbot, tmp_path, _reset_app_theme, monkeypatch):
    """A settings file that already says lightTheme=true (written by a prior
    session) makes a fresh window start light with the menu action checked.
    Fusion is asserted via a setStyle spy (see note on
    test_toggle_light_switches_to_fusion_and_keeps_icons for why
    style().objectName() is unreliable here)."""
    seed = _ini_settings(tmp_path)
    seed.setValue("lightTheme", True)
    seed.sync()

    calls = []
    monkeypatch.setattr(QApplication, "setStyle", lambda self, name: calls.append(name))
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    app = QApplication.instance()
    assert window._light_theme_action.isChecked() is True
    assert "Fusion" in calls
    assert app.palette().color(QPalette.ColorRole.Window).rgb() == light_palette().color(
        QPalette.ColorRole.Window
    ).rgb()


# -- BUG-004 gap coverage: toolbar icons re-tint to the applied theme --------


def _first_icon_image(window):
    actions = window._toolbar_ui.toolbar.actions()
    assert actions
    pixmap = actions[0].icon().pixmap(22, 22)
    assert not pixmap.isNull()
    return pixmap.toImage()


def _colored_pixels(image, want, tol=60):
    """Count opaque pixels within `tol` per channel of `want` (a QColor) --
    same tolerance scheme as tests/ui/test_icons.py."""
    n = 0
    for x in range(image.width()):
        for y in range(image.height()):
            px = QColor(image.pixelColor(x, y))
            if px.alpha() == 0:
                continue
            if (
                abs(px.red() - want.red()) <= tol
                and abs(px.green() - want.green()) <= tol
                and abs(px.blue() - want.blue()) <= tol
            ):
                n += 1
    return n


def test_toolbar_icons_tinted_light_text_in_dark_theme(qtbot, _reset_app_theme):
    """Fresh window (dark default): icons are tinted to the dark palette's
    light WindowText, not the light theme's near-black."""
    window = MainWindow()
    qtbot.addWidget(window)
    image = _first_icon_image(window)
    light_text = dark_palette().color(QPalette.ColorRole.WindowText)  # 0xE0E0E0
    dark_text = light_palette().color(QPalette.ColorRole.WindowText)  # 0x1E1E1E
    assert _colored_pixels(image, light_text) > 0
    assert _colored_pixels(image, dark_text) == 0


def test_toolbar_icons_retint_dark_text_when_toggled_light(qtbot, _reset_app_theme):
    """Toggling Light Theme on re-tints existing toolbar icons to the light
    palette's dark WindowText -- the re-tint half of the BUG-004 fix."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._on_light_theme_toggled(True)
    image = _first_icon_image(window)
    dark_text = light_palette().color(QPalette.ColorRole.WindowText)
    light_text = dark_palette().color(QPalette.ColorRole.WindowText)
    assert _colored_pixels(image, dark_text) > 0
    assert _colored_pixels(image, light_text) == 0


def test_toolbar_icons_retint_back_when_toggled_off(qtbot, _reset_app_theme):
    """Light -> dark toggle re-tints icons back to the light-on-dark color."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._on_light_theme_toggled(True)
    window._on_light_theme_toggled(False)
    image = _first_icon_image(window)
    light_text = dark_palette().color(QPalette.ColorRole.WindowText)
    dark_text = light_palette().color(QPalette.ColorRole.WindowText)
    assert _colored_pixels(image, light_text) > 0
    assert _colored_pixels(image, dark_text) == 0


# -- BUG-004 gap coverage: the tests/ui/conftest.py autouse reset ------------
# These two tests exercise the autouse _reset_app_style_and_palette fixture
# directly: the first deliberately does NOT use the local _reset_app_theme
# fixture and leaves the app on the dark theme; the second (running after it
# in definition order) proves the mutation did not leak. This is the exact
# leakage that broke test_menus.py before the conftest reset existed.


def test_mainwindow_mutates_app_theme_without_local_reset(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    app = QApplication.instance()
    assert app.palette().color(QPalette.ColorRole.Window).rgb() == dark_palette().color(
        QPalette.ColorRole.Window
    ).rgb()


def test_previous_tests_theme_mutation_did_not_leak(qapp):
    """Runs after the deliberately-leaky test above: the autouse conftest
    fixture must already have restored the original app palette, so the app is
    NOT still on dark_palette()'s window color."""
    window_color = qapp.palette().color(QPalette.ColorRole.Window)
    assert window_color.rgb() != dark_palette().color(QPalette.ColorRole.Window).rgb()
