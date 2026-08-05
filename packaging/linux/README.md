# Linux desktop integration (BUG-009)

`pip install` (editable or wheel) does **not** place a `.desktop` file or icon
theme entries anywhere a desktop shell looks — those live outside the Python
package's installed files, in freedesktop.org-standard user/system data
directories. This directory holds the pieces needed for KDE (and other
freedesktop-compliant desktops) to show the real PGTP Editor icon in the
taskbar and window decorations instead of a generic placeholder, plus the
manual steps to install them.

Files here:

- `pgtp-editor.desktop` — the application launcher entry. Its basename
  (`pgtp-editor`) must match the `QApplication.setDesktopFileName("pgtp-editor")`
  call in `pgtp_editor/main.py` — that match is what lets KDE/Wayland
  associate the running window with this `.desktop` file's `Icon=` entry.
- `icons/hicolor/scalable/apps/pgtp-editor.svg` and
  `icons/hicolor/256x256/apps/pgtp-editor.png` — the app icon, laid out in
  the standard [hicolor icon theme](https://specifications.freedesktop.org/icon-theme-spec/icon-theme-spec-latest.html)
  directory structure so `Icon=pgtp-editor` resolves.

## Manual install (per-user, no root required)

```sh
# 1. Install the package itself (adjust as appropriate, e.g. inside a venv
#    or with pipx):
pip install .

# 2. Copy the desktop entry:
mkdir -p ~/.local/share/applications
cp packaging/linux/pgtp-editor.desktop ~/.local/share/applications/

# 3. Copy the icon into the user's hicolor icon theme:
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
mkdir -p ~/.local/share/icons/hicolor/256x256/apps
cp packaging/linux/icons/hicolor/scalable/apps/pgtp-editor.svg \
   ~/.local/share/icons/hicolor/scalable/apps/
cp packaging/linux/icons/hicolor/256x256/apps/pgtp-editor.png \
   ~/.local/share/icons/hicolor/256x256/apps/

# 4. Refresh the icon cache and desktop database (optional but recommended;
#    harmless if either tool is missing):
gtk-update-icon-cache ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

After this, the app should show its own icon in the taskbar and window
title bar rather than a generic placeholder, as long as `Exec=pgtp-editor`
resolves on `PATH` (e.g. via a console-script entry point or a wrapper you
install alongside the package).

## Notes / v1 limitations

- The app icon (`app_icon.png` / `app_icon.svg` under
  `pgtp_editor/resources/`) is derived from the existing `docs/pgtpeditor.ico`
  (256x256 frame). `app_icon.svg` is a raster image *wrapped* in an SVG
  container (a `data:` URI `<image>`), not real vector artwork — this was
  the only source art available. It is good enough to resolve
  `Icon=pgtp-editor` at any size via the hicolor theme's scaling, but it will
  not look as crisp as true vector art at very large sizes. Replace with a
  proper vector icon if/when better source art exists.
- Nothing in this repo automates steps 2-4 above (no postinst script, no
  system packaging). This is a plain, documented manual step; a future
  packaging pass (e.g. a `.deb`/`.rpm`/Flatpak build, or a
  `pip install`-time hook) could automate it.
