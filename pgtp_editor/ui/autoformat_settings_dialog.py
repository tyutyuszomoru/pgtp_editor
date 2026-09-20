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

# pgtp_editor/ui/autoformat_settings_dialog.py
"""The Autoformatter settings surface — the **Autoformatter** pane of
`Settings ▸ Software settings…` (§18.4 part D; relocated there from its own
`Settings ▸ Autoformatter settings…` entry by FQ-260812002827).

Configures **exactly** the settable surface of §18.4's parts A, B and C and
nothing that is not in those tables: the keyword-casing choice, the SQL indent
unit, the per-clause-starter break/indent grid, the JOIN-phrase break, and the
XML indent width.

**Every control is a bounded widget** — a combo, a spin box with min/max, a
checkbox. There is no free-text rule entry anywhere, which is how §18.4's bounded
config space is enforced at the UI as well as in the loader: a user cannot even
express a rule the engine could not prove idempotent.

WHAT THIS PANE INHERITS FROM THE `Settings` MENU (do not "fix" either half)
--------------------------------------------------------------------------
The three rules below were written about this surface's own menu entry. That
entry is gone: the ONE command is now `Settings ▸ Software settings…`, and the
rules apply to it unchanged, because they were always rules of the menu rather
than of this dialog.

1. **No keyboard shortcut**, as a rule of the menu rather than a choice about
   this entry. Hiding a top-level `QMenu` does not disable its child actions
   (DEC-006), so a chord would open a Maintenance-only dialog from outside
   Maintenance mode — the one place the mode's framing would be false.
2. **It IS pinnable to the toolbar** (`ToolbarController._walk_menu_actions`
   never tests `isVisible()`), so a pinned button reaches it outside Maintenance
   mode. That is FQ-027 Q2's recorded trade taken deliberately, not a leak. It
   must not be added to `DEFAULT_TOOLBAR_IDS`.
3. The same walk also makes the command **rebindable** through the keyboard
   shortcuts pane. Rule 1 constrains what the app *ships*, not what a user may
   choose.

House style carried from `customize_shortcuts_dialog.py` /
`edit_snippets_dialog.py`: **never `.exec()`**, so no test ever meets a live
modal, and every mutation has a programmatic seam
(`load_configs`, `set_clause_rule`, `restore_defaults`, `save`) so tests drive it
without synthesising clicks.

**This dialog owns its own persistence** — unlike `CustomizeShortcutsDialog`,
whose host writes QSettings after `accepted`. The reason is scope: a formatter
preference has exactly one writer and one reader (`ui/format_settings.py`), the
host has no business holding it, and the hosts of the gesture re-read the store
at gesture time, so accepting here is the whole of "apply".
"""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..sql import DEFAULT_FORMAT_CONFIG, FormatConfig
from ..sql.format_config import (
    CLAUSE_STARTERS,
    MAX_CLAUSE_INDENT_LEVELS,
    MAX_INDENT_WIDTH,
    MIN_CLAUSE_INDENT_LEVELS,
    MIN_INDENT_WIDTH,
    ClauseRule,
    KeywordCase,
    indent_unit_for,
)
from ..xmlfmt import DEFAULT_XML_FORMAT_CONFIG, XmlFormatConfig
from . import format_settings

#: What this surface is CALLED. It was the `Settings` menu row (deriving the id
#: `settings.autoformatter-settings`) until FQ-260812002827 absorbed it into
#: `Settings ▸ Software settings…`, where the pane is listed as "Autoformatter".
#: There is no menu row any more, so nothing in the product reads this — it is
#: kept as the surface's canonical name for the manual and the spec to quote and
#: for a future settings pane to reuse, not as live wiring. **The name is a
#: leftover; the constant is not the id's source any more.**
MENU_LABEL = "Autoformatter settings…"

#: Combo entries: (label, KeywordCase). `as-is` is FIRST because it is the
#: default and the only option that changes nothing.
_CASE_CHOICES = [
    ("Leave as typed", KeywordCase.AS_IS),
    ("UPPERCASE", KeywordCase.UPPER),
    ("lowercase", KeywordCase.LOWER),
]

_INDENT_KINDS = [("Spaces", False), ("Tab", True)]


class AutoformatSettingsDialog(QDialog):
    """The bounded editor for `FormatConfig` + `XmlFormatConfig`."""

    def __init__(self, parent=None, *, settings: QSettings | None = None):
        super().__init__(parent)
        self.setWindowTitle("Autoformatter settings")
        self._settings = settings
        self._clause_breaks: dict[str, QCheckBox] = {}
        self._clause_indents: dict[str, QSpinBox] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_sql_group())
        layout.addWidget(self._build_clause_group())
        layout.addWidget(self._build_xml_group())
        layout.addWidget(
            QLabel(
                "Format Selection is always explicit (Ctrl+Alt+F or the context "
                "menu) — there is no auto-format mode."
            )
        )

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        self._buttons.accepted.connect(self._on_accepted)
        self._buttons.rejected.connect(self.reject)
        self._buttons.button(
            QDialogButtonBox.StandardButton.RestoreDefaults
        ).clicked.connect(self.restore_defaults)
        layout.addWidget(self._buttons)

        self.load_configs(
            format_settings.load_sql_config(self._settings),
            format_settings.load_xml_config(self._settings),
        )

    # --- construction -----------------------------------------------------
    def _build_sql_group(self) -> QGroupBox:
        group = QGroupBox("SQL / plpgsql")
        form = QFormLayout(group)

        self._case_combo = QComboBox()
        for label, case in _CASE_CHOICES:
            # The item data is the enum's VALUE, not the member: Qt round-trips a
            # `str` Enum through `QVariant` as a plain string, so storing the
            # member and comparing identities on the way back silently fails.
            # `KeywordCase.parse` turns it back into a member.
            self._case_combo.addItem(label, case.value)
        self._case_combo.setToolTip(
            "Applies to SQL/plpgsql KEYWORDS only. Identifiers, types, functions, "
            "literals, strings and comments are never recased: the formatter works "
            "offline with no schema knowledge, and PostgreSQL quoted identifiers "
            "are case-sensitive."
        )
        form.addRow("Keyword case:", self._case_combo)

        self._indent_kind = QComboBox()
        for label, use_tab in _INDENT_KINDS:
            self._indent_kind.addItem(label, use_tab)
        self._indent_width = QSpinBox()
        self._indent_width.setRange(MIN_INDENT_WIDTH, MAX_INDENT_WIDTH)
        self._indent_kind.currentIndexChanged.connect(self._sync_indent_width_enabled)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self._indent_kind)
        row_layout.addWidget(self._indent_width)
        row_layout.addStretch(1)
        form.addRow("One indent level:", row)

        self._join_phrase_break = QCheckBox(
            "Start a new line at a JOIN phrase (“left outer join …”)"
        )
        self._join_phrase_break.setToolTip(
            "Off keeps the whole phrase on the FROM item's line — the flag governs "
            "the phrase as a whole, never one prefix word."
        )
        form.addRow("", self._join_phrase_break)
        return group

    def _build_clause_group(self) -> QGroupBox:
        """The per-clause-starter grid: one bounded row per keyword.

        Sorted alphabetically and built from `CLAUSE_STARTERS` itself, so a
        keyword added to the engine shows up here with no edit — the same reason
        the stored grid is sparse.
        """
        group = QGroupBox("Line breaks per clause keyword")
        outer = QVBoxLayout(group)
        area = QScrollArea()
        area.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        grid.addWidget(QLabel("Keyword"), 0, 0)
        grid.addWidget(QLabel("New line"), 0, 1)
        grid.addWidget(QLabel("Extra indent (levels)"), 0, 2)
        for row, keyword in enumerate(sorted(CLAUSE_STARTERS), start=1):
            grid.addWidget(QLabel(keyword), row, 0)
            check = QCheckBox()
            self._clause_breaks[keyword] = check
            grid.addWidget(check, row, 1)
            spin = QSpinBox()
            spin.setRange(MIN_CLAUSE_INDENT_LEVELS, MAX_CLAUSE_INDENT_LEVELS)
            self._clause_indents[keyword] = spin
            grid.addWidget(spin, row, 2)
        area.setWidget(body)
        outer.addWidget(area)
        outer.addWidget(
            QLabel(
                "Breaks the formatter needs for correctness are not listed: after "
                "“--” comments and “;”, the DECLARE header, and the block keywords."
            )
        )
        return group

    def _build_xml_group(self) -> QGroupBox:
        group = QGroupBox("XML / XSD")
        form = QFormLayout(group)
        self._xml_indent_width = QSpinBox()
        self._xml_indent_width.setRange(MIN_INDENT_WIDTH, MAX_INDENT_WIDTH)
        self._xml_indent_width.setToolTip(
            "The XML formatter changes indentation only. Two spaces by default, "
            "because that is the .pgtp file's own indentation unit."
        )
        form.addRow("One indent level (spaces):", self._xml_indent_width)
        return group

    def _sync_indent_width_enabled(self) -> None:
        self._indent_width.setEnabled(not self._indent_kind.currentData())

    # --- programmatic seams ----------------------------------------------
    def load_configs(self, sql_config: FormatConfig, xml_config: XmlFormatConfig) -> None:
        """Show `sql_config` / `xml_config` in the widgets."""
        index = self._case_combo.findData(KeywordCase.parse(sql_config.keyword_case).value)
        self._case_combo.setCurrentIndex(max(index, 0))
        self._indent_kind.setCurrentIndex(1 if sql_config.uses_tab else 0)
        self._indent_width.setValue(sql_config.indent_width)
        self._sync_indent_width_enabled()
        self._join_phrase_break.setChecked(sql_config.join_phrase_break)
        for keyword in self._clause_breaks:
            rule = sql_config.rule_for(keyword)
            self._clause_breaks[keyword].setChecked(rule.break_before)
            self._clause_indents[keyword].setValue(rule.indent_levels)
        self._xml_indent_width.setValue(
            len(xml_config.indent_unit) or len(DEFAULT_XML_FORMAT_CONFIG.indent_unit)
        )

    def set_clause_rule(self, keyword: str, *, break_before: bool, indent_levels: int) -> None:
        """Set one clause row (the seam tests use instead of clicking)."""
        self._clause_breaks[keyword].setChecked(break_before)
        self._clause_indents[keyword].setValue(indent_levels)

    def set_keyword_case(self, case: KeywordCase) -> None:
        self._case_combo.setCurrentIndex(
            max(self._case_combo.findData(KeywordCase.parse(case).value), 0)
        )

    def sql_config(self) -> FormatConfig:
        """The SQL config the widgets currently describe.

        Sanitized on the way out, which is also what makes the grid SPARSE: a row
        left at the shipped rule contributes no entry.
        """
        rules = {
            keyword: ClauseRule(
                break_before=self._clause_breaks[keyword].isChecked(),
                indent_levels=self._clause_indents[keyword].value(),
            )
            for keyword in self._clause_breaks
        }
        return FormatConfig(
            indent_unit=indent_unit_for(
                self._indent_width.value(), bool(self._indent_kind.currentData())
            ),
            keyword_case=KeywordCase.parse(self._case_combo.currentData()),
            clause_rules=rules,
            join_phrase_break=self._join_phrase_break.isChecked(),
        ).sanitized()

    def xml_config(self) -> XmlFormatConfig:
        return XmlFormatConfig(indent_unit=" " * self._xml_indent_width.value())

    def restore_defaults(self) -> None:
        """Back to the shipped behaviour — including `as-is` casing, which is
        byte-identical to the pre-FQ-033 formatter."""
        self.load_configs(DEFAULT_FORMAT_CONFIG, DEFAULT_XML_FORMAT_CONFIG)

    def save(self) -> None:
        """Persist what the widgets describe (no dialog result involved)."""
        format_settings.save_configs(self.sql_config(), self.xml_config(), self._settings)

    def _on_accepted(self) -> None:
        self.save()
        self.accept()


def build_autoformat_settings_pane(
    parent=None, *, settings: QSettings | None = None
) -> AutoformatSettingsDialog:
    """Build the Autoformatter settings widget — THE one construction site.

    Since FQ-260812002827 this is not a window of its own: it is the
    **Autoformatter** pane of `Settings ▸ Software settings…`, which embeds the
    returned dialog as a plain widget. `Settings ▸ Autoformatter settings…` is
    gone, not duplicated. So this RETURNS rather than shows, and `parent` is the
    pane's container.

    Saving happens on the pane's own OK, into `ui/format_settings.py`'s store;
    both hosts of the gesture re-read that store on the next `Ctrl+Alt+F`, so
    accepting here is the whole of "apply" and the settings host adds no OK of
    its own. The host rebuilds the pane when it finishes, so this is called
    repeatedly and reloads from the store each time.

    Pass `settings=` to honour an injected `QSettings` (`MainWindow._settings`);
    omitted, the app's own IniFormat/UserScope store is used.
    """
    dialog = AutoformatSettingsDialog(parent, settings=settings)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    return dialog
