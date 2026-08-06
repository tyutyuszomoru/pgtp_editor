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

# pgtp_editor/ui/schema_compare_panel.py
"""SchemaComparePanel: §18.3's schema diff/migration viewer.

Reuses `diff_merge_panel.py`'s idiom — a change list on the left, a detail
pane on the right, every entry **default-unchecked so it is skipped** — which
is §12's review discipline: the user opts a change *in*, and never discovers
after the fact that something was included by default.

**This viewer never executes DDL.** It renders `db/schema_diff.py`'s
differences and emits `db/migration_gen.py`'s reviewed SQL text for the user's
own deploy path; there is deliberately no Apply/Execute affordance and nothing
here imports a runner (§18.3's hard non-goal, stated twice there).

**It also never hides what was not compared.** Only `routine` and `trigger`
are diffable today, so `SchemaDiffResult.unsupported` (the tables nobody
looked at) is captured at compare time — before any filtering, per that
class's warning — and shown in the header, and a `table`/`column` entry the
generator refuses surfaces as a named refusal rather than a quietly shortened
script.

Schemas come from outside: a snapshot file, a live connection or (§18.5) a
sandbox are all **injected callables**, so this widget opens no connection,
reads no file and never reaches a modal dialog. Saving is the same — the
generated text goes to an injected `save_migration` callback.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db.migration_gen import UnsupportedDifference, generate_migration
from ..db.schema_diff import SchemaDifference, diff_schemas

DIFFERENCE_ROLE = Qt.ItemDataRole.UserRole

#: The object kinds `db/migration_gen.py` can actually emit. Anything else is
#: listed in the change list all the same — hiding it would be the silent
#: omission §18.3 refuses — and named as a blocker when Save is attempted.
SUPPORTED_OBJECT_KINDS = ("routine", "trigger")

_NOTHING_COMPARED = "No comparison run yet — choose a source and a target to compare."
_NO_DIFFERENCES = "No differences — the two schemas agree on every compared object."

_GROUP_LABEL = {
    "routine": "Routines",
    "trigger": "Triggers",
    "table": "Tables (not compared by this engine)",
    "column": "Columns (not compared by this engine)",
}
_KIND_LABEL = {"added": "added", "removed": "removed", "changed": "changed"}


def difference_label(difference: SchemaDifference) -> str:
    """`pr.f(integer)` — the identity, with a marker for a kind the generator
    cannot emit so an unsupported row is never mistaken for a ready one."""
    if difference.object_kind not in SUPPORTED_OBJECT_KINDS:
        return f"⚠ {difference.identity}"
    return difference.identity


def _monospace(widget: QPlainTextEdit) -> QPlainTextEdit:
    widget.setReadOnly(True)
    font = QFont("Monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    widget.setFont(font)
    widget.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    return widget


class SchemaComparePanel(QWidget):
    """Panel host for one schema comparison session.

    Constructor seams (all optional, all keyword-only):

    * `snapshot_loader(path) -> DatabaseSchema` — §18.3's snapshot-file source.
    * `schema_fetchers` — `{"live": fn(target) -> DatabaseSchema, "sandbox": …}`,
      §18.3's live connection plus §18.5's sandbox.
    * `save_migration(text) -> None` — "Save Migration As…"'s file writing.
    """

    #: Emitted for every user-facing outcome (compared / saved / refused) so a
    #: host can mirror it in the status bar. Never a substitute for
    #: `status_label`, which always holds the current state.
    status_message = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        snapshot_loader: Callable[[str], object] | None = None,
        schema_fetchers: dict[str, Callable[[object], object]] | None = None,
        save_migration: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._snapshot_loader = snapshot_loader
        self._schema_fetchers = dict(schema_fetchers or {})
        self._save_migration = save_migration

        self._compared = False
        self._differences: list[SchemaDifference] = []
        self._unsupported: list[str] = []
        self._source_label = ""
        self._target_label = ""

        self.status_label = QLabel(_NOTHING_COMPARED)
        self.status_label.setWordWrap(True)
        self.unsupported_label = QLabel("")
        self.unsupported_label.setWordWrap(True)
        self.unsupported_label.setVisible(False)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Object", "Change", "Kind"])
        self.tree.setColumnWidth(0, 340)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 90)
        self.tree.setUniformRowHeights(True)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)

        self.detail_stack = QStackedWidget()
        self.placeholder_label = QLabel("Select a change to review its definition.")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setWordWrap(True)
        self.detail_stack.addWidget(self.placeholder_label)

        self.old_def_text = _monospace(QPlainTextEdit())
        self.new_def_text = _monospace(QPlainTextEdit())
        self.old_def_label = QLabel("Target (current)")
        self.new_def_label = QLabel("Source (desired)")
        detail_view = QWidget()
        detail_layout = QHBoxLayout(detail_view)
        for label, text in (
            (self.old_def_label, self.old_def_text),
            (self.new_def_label, self.new_def_text),
        ):
            side = QWidget()
            side_layout = QVBoxLayout(side)
            side_layout.setContentsMargins(0, 0, 0, 0)
            side_layout.addWidget(label)
            side_layout.addWidget(text, 1)
            detail_layout.addWidget(side, 1)
        self.detail_stack.addWidget(detail_view)
        self.detail_stack.setCurrentWidget(self.placeholder_label)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.detail_stack)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)

        # No Apply/Execute button, ever (§18.3): the only outbound action is
        # handing reviewed *text* to the caller.
        self.save_button = QPushButton("Save Migration As…")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.request_save_migration)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.unsupported_label)
        layout.addWidget(self.splitter, 1)
        layout.addLayout(button_row)

    # -- schema sources (injected seams) -------------------------------------

    def load_snapshot(self, path) -> object:
        """Resolve a snapshot path through the injected loader.

        The snapshot format lives in `db/schema_snapshot.py`; this widget only
        knows that *something* returns a `DatabaseSchema` for a path.
        """
        if self._snapshot_loader is None:
            raise RuntimeError("no snapshot loader was injected into SchemaComparePanel")
        return self._snapshot_loader(path)

    def fetch_schema(self, role: str, target=None) -> object:
        """Resolve a live (`role="live"`) or sandbox (`role="sandbox"`) schema."""
        fetcher = self._schema_fetchers.get(role)
        if fetcher is None:
            raise RuntimeError(f"no schema fetcher was injected for role {role!r}")
        return fetcher(target)

    def resolve_source(self, ref: tuple[str, object]) -> object:
        """`("snapshot", path)` / `("live", target)` / `("sandbox", target)`
        → `DatabaseSchema`. One place decides which seam a reference uses, so
        a host can pass user-chosen references straight through."""
        kind, value = ref
        if kind == "snapshot":
            return self.load_snapshot(value)
        return self.fetch_schema(kind, value)

    def compare_sources(
        self, source_ref: tuple[str, object], target_ref: tuple[str, object]
    ) -> None:
        """Resolve both references, then compare them."""
        source = self.resolve_source(source_ref)
        target = self.resolve_source(target_ref)
        self.compare(
            source,
            target,
            source_label=self._ref_label(source_ref),
            target_label=self._ref_label(target_ref),
        )

    @staticmethod
    def _ref_label(ref: tuple[str, object]) -> str:
        kind, value = ref
        return f"{kind}: {value}" if value is not None else kind

    # -- population ----------------------------------------------------------

    def compare(
        self, source, target, *, source_label: str = "", target_label: str = ""
    ) -> None:
        """Diff `source` (desired) against `target` (current) and render it."""
        self.show_result(
            diff_schemas(source, target),
            source_label=source_label,
            target_label=target_label,
        )

    def show_result(
        self, result, *, source_label: str = "", target_label: str = ""
    ) -> None:
        """Render an already-computed `SchemaDiffResult` (or plain difference
        list). `.unsupported` is read **here, first**, before the list is
        walked — `SchemaDiffResult` drops that sidecar through any
        comprehension, and losing it would let this panel present a
        table-blind diff as a complete one."""
        self._unsupported = list(getattr(result, "unsupported", ()))
        self._differences = list(result)
        self._compared = True
        self._source_label = source_label
        self._target_label = target_label
        self._rebuild()

    def clear(self) -> None:
        """Back to the nothing-compared-yet state — distinct from an empty
        diff, which is a real (and reassuring) answer."""
        self._compared = False
        self._differences = []
        self._unsupported = []
        self._source_label = self._target_label = ""
        self._rebuild()

    def _rebuild(self) -> None:
        self.tree.clear()
        self.detail_stack.setCurrentWidget(self.placeholder_label)
        groups: dict[str, QTreeWidgetItem] = {}
        for difference in self._differences:
            group = groups.get(difference.object_kind)
            if group is None:
                label = _GROUP_LABEL.get(
                    difference.object_kind, difference.object_kind
                )
                group = QTreeWidgetItem([label, "", ""])
                group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                self.tree.addTopLevelItem(group)
                group.setExpanded(True)
                groups[difference.object_kind] = group
            group.addChild(self._make_item(difference))
        self._update_status()
        self.save_button.setEnabled(bool(self._differences))

    def _make_item(self, difference: SchemaDifference) -> QTreeWidgetItem:
        item = QTreeWidgetItem(
            [
                difference_label(difference),
                _KIND_LABEL.get(difference.kind, difference.kind),
                difference.object_kind,
            ]
        )
        item.setData(0, DIFFERENCE_ROLE, difference)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        # Default-unchecked = skip (§12 review discipline). Never pre-check.
        item.setCheckState(0, Qt.CheckState.Unchecked)
        return item

    def _update_status(self) -> None:
        if not self._compared:
            text = _NOTHING_COMPARED
        elif not self._differences:
            text = _NO_DIFFERENCES
        else:
            count = len(self._differences)
            noun = "difference" if count == 1 else "differences"
            text = f"{count} {noun} — none selected yet; check the ones to include."
        if self._compared and (self._source_label or self._target_label):
            text = (
                f"Source (desired): {self._source_label or '?'}   →   "
                f"Target (current): {self._target_label or '?'}\n{text}"
            )
        self.status_label.setText(text)

        if self._compared and self._unsupported:
            count = len(self._unsupported)
            noun = "object was" if count == 1 else "objects were"
            self.unsupported_label.setText(
                f"⚠ Not compared: table and column changes are not diffed by this "
                f"engine, so {count} {noun} skipped entirely — "
                f"{', '.join(self._unsupported)}. Review those separately; this "
                f"comparison covers routines and triggers only."
            )
            self.unsupported_label.setVisible(True)
        else:
            self.unsupported_label.setText("")
            self.unsupported_label.setVisible(False)

    # -- properties for hosts and tests -------------------------------------

    @property
    def differences(self) -> list[SchemaDifference]:
        return list(self._differences)

    @property
    def unsupported(self) -> list[str]:
        """The objects `diff_schemas` did not compare, captured at compare
        time. Empty until something has been compared."""
        return list(self._unsupported)

    @property
    def has_compared(self) -> bool:
        return self._compared

    # -- detail pane ---------------------------------------------------------

    def _on_current_item_changed(self, current, _previous) -> None:
        difference = (
            current.data(0, DIFFERENCE_ROLE) if current is not None else None
        )
        if difference is None:
            self.detail_stack.setCurrentWidget(self.placeholder_label)
            return
        self._show_detail(difference)

    def _show_detail(self, difference: SchemaDifference) -> None:
        self.old_def_text.setPlainText(
            difference.old_def
            if difference.old_def is not None
            else "-- (absent from the target schema)"
        )
        self.new_def_text.setPlainText(
            difference.new_def
            if difference.new_def is not None
            else "-- (absent from the source schema)"
        )
        self.old_def_label.setText(f"Target (current) — {difference.identity}")
        self.new_def_label.setText(f"Source (desired) — {difference.identity}")
        self.detail_stack.setCurrentIndex(1)

    def select_difference(self, index: int) -> None:
        """Select the `index`-th entry in change-list order — the seam the
        host's next/previous navigation and the tests both use."""
        items = self._items()
        if 0 <= index < len(items):
            self.tree.setCurrentItem(items[index])

    def _items(self) -> list[QTreeWidgetItem]:
        items: list[QTreeWidgetItem] = []
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            items.extend(group.child(j) for j in range(group.childCount()))
        return items

    # -- review + migration --------------------------------------------------

    def checked_differences(self) -> list[SchemaDifference]:
        """The opted-in subset, in change-list order. Empty by default."""
        return [
            item.data(0, DIFFERENCE_ROLE)
            for item in self._items()
            if item.checkState(0) == Qt.CheckState.Checked
        ]

    def set_checked(self, indexes: Iterable[int]) -> None:
        """Check exactly `indexes` (change-list order) — a host convenience
        for "check all" style actions, and the tests' way in."""
        wanted = set(indexes)
        for position, item in enumerate(self._items()):
            item.setCheckState(
                0,
                Qt.CheckState.Checked
                if position in wanted
                else Qt.CheckState.Unchecked,
            )

    def migration_header(self) -> str:
        """Free-text header for `generate_migration`. Deliberately clock- and
        connection-free: a host that wants a timestamp or a server version
        passes it in the labels."""
        lines = []
        if self._source_label:
            lines.append(f"Source (desired): {self._source_label}")
        if self._target_label:
            lines.append(f"Target (current): {self._target_label}")
        if self._unsupported:
            lines.append(
                "Not compared (tables/columns): " + ", ".join(self._unsupported)
            )
        lines.append("Reviewed selection only — nothing here has been executed.")
        return "\n".join(lines)

    def unsupported_blockers(
        self, differences: Sequence[SchemaDifference] | None = None
    ) -> list[str]:
        """Identities in `differences` (default: the checked subset) whose
        `object_kind` the generator refuses. Pure — lets a host disable or
        explain Save without provoking the exception first."""
        selection = (
            self.checked_differences() if differences is None else list(differences)
        )
        return [
            d.identity for d in selection if d.object_kind not in SUPPORTED_OBJECT_KINDS
        ]

    def migration_text(self) -> str:
        """The reviewed `.sql` text for the **checked** subset.

        Raises `UnsupportedDifference` (from `migration_gen`) if the selection
        contains a table/column change — propagated, never swallowed into a
        partial script.
        """
        return generate_migration(
            self.checked_differences(), header=self.migration_header()
        )

    def request_save_migration(self) -> bool:
        """"Save Migration As…": hand the reviewed text to the injected
        `save_migration` callback. Returns whether text was handed over;
        every refusal path lands in `status_label` and `status_message`."""
        checked = self.checked_differences()
        if not checked:
            self._report(
                "Nothing selected — check the changes to include before saving a "
                "migration."
            )
            return False
        try:
            text = self.migration_text()
        except UnsupportedDifference as error:
            blockers = ", ".join(self.unsupported_blockers(checked))
            self._report(
                f"Refusing to generate a migration: {error}. Blocking object(s): "
                f"{blockers}. Uncheck them, or handle those changes outside this "
                f"viewer — a script that silently omitted them would be worse."
            )
            return False
        if self._save_migration is None:
            self._report("No save destination is wired up for this viewer.")
            return False
        self._save_migration(text)
        count = len(checked)
        noun = "change" if count == 1 else "changes"
        self._report(f"Migration written for {count} reviewed {noun}.")
        return True

    def _report(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_message.emit(message)
