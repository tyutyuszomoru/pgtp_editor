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

# pgtp_editor/ui/status_colours.py
"""The app's status colours — **ok / warning / error** — named as *kinds*, and
the label widget that paints one.

**Why this module exists at all** (BUG-260812063745). `status_colour` was born
in `ui/sql_results_panel.py`, where it still lives for its original caller; but
seven dialogs need the same three colours, and *"a dialog importing its colour
from a results panel"* is an arrow nobody would draw on purpose. The function
moved here, whole, and `sql_results_panel` re-exports it — there is exactly one
definition, and the panel's own callers and tests did not move.

**No new colour table.** Every value is read from `resources/themes/*.json`
through the existing readers:

* **error** → `mode_colors(light)[MODE_MAINTENANCE][1]`, the app's one red
  (§18.7) — dark `#F2B8AE` 9.28:1, light `#8B1E1E` 8.74:1.
* **warning** → the `status_warning` accent — dark `#e0a83a` 7.45:1, light
  `#8a5a00` 5.68:1.
* **ok** → `mode_colors(light)[MODE_PROJECT][1]`, the app's one green — dark
  `#B6E3C0` 11.17:1, light `#1B5E20` 7.54:1.

Contrast is measured against the live qdarkstyle chrome (`#19232D` dark,
`#FAFAFA` light), which is what §7 requires and what the bare palette does not
tell you. The three CSS colour names these replaced all failed it: `green`
3.10:1 on dark, `darkorange` 2.23:1 on light, and plain `red` 3.98/3.83 — below
4.5:1 in **both** themes.

**`shared_accent()` is the wrong reader here and must never be used.** It exists
for theme-*blind* consumers and raises unless every bundled theme agrees on the
value. A status colour that is readable in both themes has to differ per theme,
so `shared_accent("status_ok")` would raise on the day these are correct.

**Remember the KIND, never a resolved colour.** A stored colour re-applied after
a theme flip paints the *previous* theme's value — that is a shipped bug
(BUG-260811021804 step 4), not a hypothetical. `StatusLabel` below is the
pattern written once so six dialogs cannot each get it subtly wrong — and, since
BUG-260812103144, so the status bar's connectivity dots inherit it rather than
grow a second copy (they override `_colour_for`, nothing else): it holds
the kind, recomputes from the live palette on every `changeEvent`, and paints
through a **widget-level stylesheet** because the app-wide qdarkstyle sheet
beats `QPalette` for every property it declares (§7, §18.7 — measured: the
palette faithfully reported `#d02020` while zero red pixels were drawn).
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QLabel

from .mode_indicator import MODE_MAINTENANCE, MODE_PROJECT, mode_colors
from .theme_model import theme_for

#: The three attention kinds. A kind is what a call site knows ("this went
#: wrong"); the colour is derived from the live theme at paint time.
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"


def _warning_colour(light: bool) -> str:
    """Warning's per-theme value, read from the theme file's `status_warning`
    accent (FQ-260812021715) rather than spelled here — for the same reason the
    error and ok pairs are imported rather than re-typed."""
    return theme_for(light).accent("status_warning")


def status_colour(kind: str | None, light: bool) -> str | None:
    """The colour for `kind` under the light/dark theme, or None for the
    ordinary status (which must render in the theme's own text colour, i.e.
    with **no** widget stylesheet at all).

    Pure, and the single place a status kind becomes a colour — a test can pin
    the contrast of every pair without touching a widget.
    """
    if kind == STATUS_ERROR:
        return mode_colors(light)[MODE_MAINTENANCE][1]
    if kind == STATUS_WARNING:
        return _warning_colour(light)
    if kind == STATUS_OK:
        return mode_colors(light)[MODE_PROJECT][1]
    return None


class StatusLabel(QLabel):
    """A `QLabel` that remembers a status **kind** and re-derives its colour
    from the live palette whenever the theme flips.

    Drop-in for the plain `QLabel`s the dialogs used to colour with
    `setStyleSheet("color: red;")`: `text()`, `setText()` and every other
    `QLabel` API are unchanged, and `set_status(text, kind)` replaces the
    text-plus-stylesheet pair. `set_status_kind(None)` is the neutral state and
    clears the sheet entirely rather than naming a colour — an empty sheet
    returns the label to the app-wide QSS colour, which is the right neutral in
    both themes.
    """

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._status_kind: str | None = None
        self._applying = False

    def status_kind(self) -> str | None:
        """The kind currently painted — assertable without reading pixels."""
        return self._status_kind

    def set_status(self, text: str, kind: str | None = None) -> None:
        self.setText(text)
        self.set_status_kind(kind)

    def set_status_kind(self, kind: str | None) -> None:
        self._status_kind = kind
        self._apply_status_colour()

    def _palette_is_light(self) -> bool:
        return self.palette().color(QPalette.ColorRole.Base).lightness() > 128

    def _colour_for(self, light: bool) -> str | None:
        """The colour to paint under `light`, or None for "no sheet at all".

        **The one overridable seam, and the reason it exists**
        (BUG-260812103144): `ui/connectivity.py`'s status-bar dots need every
        line of the machinery below — the re-entrancy bound, the queued
        re-apply, the context-bound timer — but derive their colour from a
        connectivity STATE rather than from a status kind. Overriding one pure
        function is what kept `changeEvent` from being written a second time and
        got subtly wrong a third.
        """
        return status_colour(self._status_kind, light)

    def _apply_status_colour(self) -> None:
        """Paint the remembered kind. Idempotent and last-write-wins —
        `changeEvent` fires several times per theme flip and the first ones
        still report the OLD palette, so only recomputing from the live palette
        every time is safe.

        **Both re-entrancy defences below are load-bearing, and one is not
        enough.** Unlike `sql_results_panel`, which colours a CHILD label from
        the panel's `changeEvent`, this widget styles ITSELF from its own — and
        `setStyleSheet` re-polishes, which posts another change event straight
        back here. Writing unconditionally is infinite recursion (measured:
        `RecursionError` from the very first dialog constructed). The equality
        check kills the common case, but **not** the one a HIDDEN label hits:
        an unmapped widget's palette read flip-flops inside the nested polish,
        so the sheet differs at every level and the stack blows anyway — Qt
        catches the `RecursionError` and prints it, so the symptom is 128
        frames on stderr rather than a failure. The `_applying` flag is what
        actually bounds the nesting; the equality check keeps the common path
        from doing pointless work.
        """
        if self._applying:
            return
        colour = self._colour_for(self._palette_is_light())
        sheet = f"QLabel {{ color: {colour}; }}" if colour is not None else ""
        if sheet == self.styleSheet():
            return
        self._applying = True
        try:
            self.setStyleSheet(sheet)
        finally:
            self._applying = False

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Re-derive the colour when the theme flips. Self-detection rather
        than host wiring: there is no generic theme broadcast, and a dialog may
        well be open across a flip now that the Themes pane (FQ-260812021716)
        makes one reachable."""
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.PaletteChange,
        ):
            # Can fire during construction, before `_status_kind` exists.
            if hasattr(self, "_applying"):
                self._apply_status_colour()
                # ...and once more after the flip has fully settled. The
                # re-entrancy guard above suppresses the NESTED change event,
                # and on some flips (measured: dark -> light on an open dialog)
                # that nested event is the first one carrying the NEW palette,
                # so the immediate write above can be the OLD theme's value.
                # A queued re-apply reads a settled palette and is a no-op
                # whenever the immediate write already got it right.
                #
                # **The `self` context argument is mandatory, not tidiness.**
                # `singleShot(0, self._apply_status_colour)` keeps a bound
                # method alive past the widget's C++ deletion, and the timer
                # then fires into a dead object — measured: 272 failures
                # across the suite, all `libshiboken: Internal C++ object
                # (StatusLabel) already deleted` raised from pytest-qt's
                # `processEvents`. With a context object Qt cancels the timer
                # when the context dies.
                QTimer.singleShot(0, self, self._apply_status_colour)
