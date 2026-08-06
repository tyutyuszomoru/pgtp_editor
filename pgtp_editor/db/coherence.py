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

# pgtp_editor/db/coherence.py
"""The Database/XML Coherence model: one tree answering one question (pure).

**The live database is the truth; the XML is the interface being checked
against it.** That single framing is what collapses three near-duplicate
left-dock surfaces — "Check: XML → Database", "Check: Database → XML" and
"Table references" — into the two branches built here. The "direction" of the
old two menu items was never a real user choice: it was an artifact of showing
one side's state at a time. Show DB state and XML state together per relation
and the choice disappears.

Two branches, one tree:

* **"Tables and Views"** — rooted in the live DB relation list, so it can only
  ever contain relations that really exist. Tables and views get identical
  treatment (introspection fetches both the same way and nothing downstream
  filters by `relkind`). Each relation carries its DB columns and a
  badge-summary of where the XML references it, expandable to the same
  breadcrumbs the old Table References panel showed.
* **"Pages"** — a recursive mirror of the *real* XML structure. Each Page
  carries its own bound table and its own lookup columns, then nests child
  Details that do the same, to whatever depth the XML actually has. The trap
  this module exists to avoid is flattening that to an assumed
  "Page > Details > Detail > Lookups" shape: `visit_detail` in
  `analysis/reused_tables.py` recurses without a depth limit, and a Detail
  nested four levels down with its own lookups is ordinary, not exotic.

Everything here is derived, never recomputed. `collect_table_usages`
(`analysis/reused_tables.py`) is the one page/detail/lookup walk in the
project and stays that way — this module indexes its `TableReference`s by
model node and reads breadcrumbs, source lines and `ref_type` (including the
`"lookup with insert"` distinction, fired by a `<Lookup>` with a child
`<OnTheFlyInsertPage>`) straight off them. Reference *counts* come from
`TableCheck.page_count`/`.detail_count`/`.lookup_count` (BUG-026) and the
calculated-column carve-out from `ColumnCheck.is_calculated` (BUG-006); no
parallel counting logic is introduced. The genuinely new thing is
`CoherenceNode.flagged` and the filter over it — see `flagged` semantics
below. Qt-free, psycopg-free, I/O-free.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

# `_page_label`/`_detail_label` are imported rather than re-derived on purpose:
# the caption/fileName/tableName fallback order they encode is what the Table
# References breadcrumbs already print, and a second spelling of it would drift
# the moment one of them changed. They are private only because nothing outside
# the reference walk needed them until this tree did.
from pgtp_editor.analysis.reused_tables import (
    TableReference,
    _detail_label,
    _page_label,
    collect_table_usages,
)

from .compare import ColumnCheck, TableCheck, check_db_against_xml, check_xml_against_db
from .introspect import DatabaseSchema

TABLES_BRANCH_LABEL = "Tables and Views"
PAGES_BRANCH_LABEL = "Pages"
COLUMNS_GROUP_LABEL = "Database columns"
REFERENCES_GROUP_LABEL = "References"

#: The XML points at a table/view the live DB does not have. On a Pages-branch
#: node this is the renamed/dropped-table error, flagged at the exact reference
#: point; on a column it means the XML names a column the relation lacks.
BADGE_MISSING_IN_DB = "missing in DB"
#: A real DB relation the XML references in no role at all (BUG-026's three
#: role counts all zero).
BADGE_UNREFERENCED = "unreferenced"
#: A DB column no page/detail binds (the old "Database → XML" direction).
BADGE_NOT_IN_XML = "not in XML"
#: `isCalculated="true"` — DB-less by design (BUG-006), never a mismatch.
BADGE_CALCULATED = "calculated"
#: A Page/Detail element with no `tableName` at all — structural, not an error.
BADGE_NO_TABLE = "no table"

#: Role name -> the `TableCheck` rollup attribute holding that role's reference
#: count (BUG-026's role split, the same three numbers the "(P# D# L#)" badge
#: prints). The P>1/D>1/L>1 filters (FQ-008) read these and nothing else — no
#: second counting pass, no re-introspection.
ROLE_COUNT_ATTRS = {"page": "page_count", "detail": "detail_count", "lookup": "lookup_count"}


@dataclass(frozen=True)
class CoherenceNode:
    """One row of the coherence tree, ready to render.

    kind:       "branch" | "relation" | "group" | "column" | "reference" |
                "page" | "detail" | "lookup". The panel maps this to an icon;
                nothing here depends on it.
    label:      the display text for the row.
    badges:     short annotations shown after the label, in a stable order.
    flagged:    this row itself needs attention (see `build_coherence_tree`).
                Containers are never flagged for their children's sake — the
                filter keeps ancestors instead, so the flag always points at
                the exact place the problem lives.
    children:   nested rows, in document order (Pages) or name order (Tables).
    table_name: the relation this row is about, when it is about one.
    line:       1-based source line to jump to in the XML, or None.
    node:       the owning model node (PageNode | DetailNode | ColumnNode) for
                navigation, or None for DB-sourced rows.
    payload:    the record this row was built from (TableCheck | ColumnCheck |
                TableReference), for panels that want more than the badges.
    node_kind:  the Properties-panel kind for `node`, when the row's own `kind`
                is not one (a `"reference"` row's model node is the Page/Detail/
                Column that does the referencing, so Properties must render it
                as `"page"`/`"detail"`/`"column"` — BUG-032). None means "use
                `kind`".
    """

    kind: str
    label: str
    badges: tuple[str, ...] = ()
    flagged: bool = False
    children: tuple["CoherenceNode", ...] = ()
    table_name: str | None = None
    line: int | None = None
    node: object | None = None
    payload: object | None = None
    node_kind: str | None = None


@dataclass(frozen=True)
class CoherenceTree:
    """The two branch roots, kept together so the panel and the mismatch
    toggle have one object to pass around."""

    tables_and_views: CoherenceNode
    pages: CoherenceNode

    @property
    def branches(self) -> tuple[CoherenceNode, CoherenceNode]:
        return (self.tables_and_views, self.pages)

    @property
    def flagged_count(self) -> int:
        return sum(flagged_count(branch) for branch in self.branches)

    @property
    def row_count(self) -> int:
        """Rows in both branches, excluding the two branch roots themselves."""
        return sum(row_count(branch) - 1 for branch in self.branches)

    def filtered(self) -> "CoherenceTree":
        """This tree pruned to flagged nodes and their ancestors.

        The two branch roots always survive (possibly childless) so the panel
        keeps a stable shape when the mismatch toggle finds nothing.
        """
        return CoherenceTree(
            tables_and_views=_prune_branch(self.tables_and_views),
            pages=_prune_branch(self.pages),
        )

    # -- role-count scoping (FQ-008) ----------------------------------------

    def role_qualifying_tables(self, roles: Iterable[str]) -> set[str]:
        """Relation names whose reference count is **> 1 in every** role in
        `roles` (a subset of `ROLE_COUNT_ATTRS`).

        `roles` combine with AND: asking for `("page", "detail")` returns only
        relations used on more than one page *and* in more than one detail —
        checking a second box narrows, never widens (FQ-008).

        The counts come straight off the `TableCheck` each relation row already
        carries (BUG-026's `page_count`/`detail_count`/`lookup_count`); nothing
        is recounted and no schema is touched. An empty `roles` means "no role
        condition", so every named relation qualifies.
        """
        attrs = [ROLE_COUNT_ATTRS[role] for role in roles]
        names: set[str] = set()
        for relation in self.tables_and_views.children:
            if not relation.table_name:
                continue
            check = relation.payload
            if check is None:
                continue
            if all(getattr(check, attr, 0) > 1 for attr in attrs):
                names.add(relation.table_name)
        return names

    def scoped_to_tables(self, names: Iterable[str]) -> "CoherenceTree":
        """This tree narrowed to the relations in `names`, spanning both
        branches (FQ-008's third settled decision).

        The two branches are narrowed differently because they mean different
        things:

        * **Tables and Views** keeps each surviving relation's *whole* subtree —
          its DB columns and its References group are what the row is for, and a
          relation row with its children stripped would answer nothing.
        * **Pages** keeps only the reference points that target a surviving
          relation, plus the ancestors needed to reach them — exactly the
          mismatch toggle's reachability rule. A table excluded here therefore
          also disappears from the Page/Detail/lookup rows that point at it, so
          the two branches never disagree about what is in scope.
        """
        wanted = set(names)

        def in_scope(node: CoherenceNode) -> bool:
            return bool(node.table_name) and node.table_name in wanted

        return CoherenceTree(
            tables_and_views=_prune_branch(
                self.tables_and_views, in_scope, keep_subtree=True
            ),
            pages=_prune_branch(self.pages, in_scope),
        )


# --- pruning predicates ------------------------------------------------------


def flagged_count(node: CoherenceNode) -> int:
    """How many rows in `node`'s subtree (inclusive) are flagged."""
    return int(node.flagged) + sum(flagged_count(child) for child in node.children)


def row_count(node: CoherenceNode) -> int:
    """How many rows `node`'s subtree contains, `node` itself included. Used by
    the panel's active-filter banner to say "showing N of M rows" without a
    second walk of the widget tree."""
    return 1 + sum(row_count(child) for child in node.children)


def has_flagged(node: CoherenceNode) -> bool:
    """Whether `node` or anything below it is flagged."""
    return node.flagged or any(has_flagged(child) for child in node.children)


def is_flagged(node: CoherenceNode) -> bool:
    """The mismatch toggle's predicate, named so it can be passed around like
    any other (FQ-008 turned the one-off toggle into one composable
    mechanism)."""
    return node.flagged


def filter_nodes(
    node: CoherenceNode,
    predicate: Callable[[CoherenceNode], bool],
    *,
    keep_subtree: bool = False,
) -> CoherenceNode | None:
    """Return `node` pruned to the rows `predicate` accepts and the paths that
    reach them, or `None` when the subtree has no accepted row.

    An accepted leaf must stay *reachable*, so every ancestor of a surviving
    row is kept even though the ancestor itself was not accepted; an ancestor's
    rejected siblings are not.

    `keep_subtree=True` keeps an accepted node's children verbatim instead of
    pruning them too — for scoping filters that select a *subject* (a relation)
    rather than a *row* (a mismatch), where stripping the children would leave
    the surviving row unable to answer anything.
    """
    if keep_subtree and predicate(node):
        return node
    kept = tuple(
        pruned
        for pruned in (
            filter_nodes(child, predicate, keep_subtree=keep_subtree) for child in node.children
        )
        if pruned is not None
    )
    if predicate(node) or kept:
        return replace(node, children=kept)
    return None


def filter_flagged(node: CoherenceNode) -> CoherenceNode | None:
    """Return `node` pruned to flagged rows and the paths that reach them
    (`filter_nodes` under the mismatch predicate)."""
    return filter_nodes(node, is_flagged)


def _prune_branch(
    branch: CoherenceNode,
    predicate: Callable[[CoherenceNode], bool] = is_flagged,
    *,
    keep_subtree: bool = False,
) -> CoherenceNode:
    pruned = filter_nodes(branch, predicate, keep_subtree=keep_subtree)
    return pruned if pruned is not None else replace(branch, children=())


# --- construction -----------------------------------------------------------


def _count_badge(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _reference_badges(check: TableCheck) -> tuple[str, ...]:
    """Badge-summarize where the XML uses this relation, from BUG-026's
    existing role rollups — never from a fresh count."""
    if check.page_count == check.detail_count == check.lookup_count == 0:
        return (BADGE_UNREFERENCED,)
    badges = []
    if check.page_count:
        badges.append(_count_badge(check.page_count, "page"))
    if check.detail_count:
        badges.append(_count_badge(check.detail_count, "detail"))
    if check.lookup_count:
        badges.append(_count_badge(check.lookup_count, "lookup"))
    return tuple(badges)


def _db_column_badges(check: ColumnCheck) -> tuple[str, ...]:
    badges: list[str] = []
    info = check.info
    if info is not None:
        badges.append(info.data_type)
        if info.is_pk:
            badges.append("pk")
        if info.is_fk:
            badges.append("fk")
        if not info.is_nullable:
            badges.append("not null")
    if check.is_calculated:
        badges.append(BADGE_CALCULATED)
    return tuple(badges)


def _column_node(check: ColumnCheck, *, missing_badge: str) -> CoherenceNode:
    """One "Database columns" row.

    `check.ok` is name-existence in whichever direction produced the check;
    `is_calculated` overrides it (BUG-006) — a generator-computed column is
    DB-less *by design*, so it is shown and never flagged.
    """
    flagged = not check.ok and not check.is_calculated
    badges = _db_column_badges(check)
    if flagged:
        badges += (missing_badge,)
    return CoherenceNode(
        kind="column",
        label=check.name,
        badges=badges,
        flagged=flagged,
        payload=check,
    )


def _reference_node(ref: TableReference) -> CoherenceNode:
    return CoherenceNode(
        kind="reference",
        label=ref.breadcrumb,
        badges=(ref.ref_type,),
        line=ref.line,
        node=ref.node,
        payload=ref,
        # `TableReference.kind` IS "the Properties-panel node kind"
        # ("page" | "detail" | "column"); carry it so selecting a row under a
        # relation's References group shows the owning node's properties, the
        # way the retired Table References panel did (BUG-032).
        node_kind=ref.kind,
    )


def _build_tables_branch(
    db_checks: list[TableCheck],
    xml_checks_by_name: dict[str, TableCheck],
    usages_by_name: dict[str, list[TableReference]],
    schema: DatabaseSchema,
) -> CoherenceNode:
    relations: list[CoherenceNode] = []
    for check in db_checks:
        info = schema.table(check.name)

        # DB columns first (they are the truth), then the XML-only columns for
        # the same relation, taken from the opposite-direction check so a
        # calculated column still appears somewhere.
        db_column_names = {column.name for column in check.columns}
        column_nodes = [
            _column_node(column, missing_badge=BADGE_NOT_IN_XML) for column in check.columns
        ]
        xml_check = xml_checks_by_name.get(check.name)
        if xml_check is not None:
            column_nodes += [
                _column_node(column, missing_badge=BADGE_MISSING_IN_DB)
                for column in xml_check.columns
                if column.name not in db_column_names
            ]

        reference_nodes = [_reference_node(ref) for ref in usages_by_name.get(check.name, [])]

        relations.append(
            CoherenceNode(
                kind="relation",
                # BUG-026 again: `TableCheck.ok` on the DB side already means
                # "referenced in at least one role", so the unreferenced-relation
                # flag is that flag, not a new count.
                label=check.name,
                badges=((info.kind,) if info is not None else ()),
                flagged=not check.ok,
                table_name=check.name,
                payload=check,
                children=(
                    CoherenceNode(
                        kind="group",
                        label=COLUMNS_GROUP_LABEL,
                        children=tuple(column_nodes),
                    ),
                    CoherenceNode(
                        kind="group",
                        label=REFERENCES_GROUP_LABEL,
                        badges=_reference_badges(check),
                        children=tuple(reference_nodes),
                    ),
                ),
            )
        )
    return CoherenceNode(kind="branch", label=TABLES_BRANCH_LABEL, children=tuple(relations))


def _build_pages_branch(
    project,
    schema: DatabaseSchema,
    refs_by_node: dict[int, TableReference],
) -> CoherenceNode:
    """Mirror the XML's own recursion — Page > (lookups, Details > (lookups,
    Details > ...)) — to whatever depth the document has.

    The structure comes from the model tree because a flat, name-grouped usage
    list cannot express nesting; every *fact* about each node (breadcrumb,
    source line, `ref_type`) still comes from the `TableReference` that
    `collect_table_usages` already produced for it.
    """

    def dangling(table_name: str | None) -> bool:
        return bool(table_name) and not schema.has_table(table_name)

    def binding_badges(table_name: str | None) -> tuple[str, ...]:
        if not table_name:
            return (BADGE_NO_TABLE,)
        if dangling(table_name):
            return (table_name, BADGE_MISSING_IN_DB)
        return (table_name,)

    def lookup_nodes(columns) -> list[CoherenceNode]:
        nodes: list[CoherenceNode] = []
        for column in columns:
            ref = refs_by_node.get(id(column))
            if ref is None:  # no <Lookup tableName="...">: not a reference
                continue
            table_name = column.lookup.attrib.get("tableName")
            # `ref_type` is carried through verbatim so "lookup with insert"
            # (a <Lookup> with a child <OnTheFlyInsertPage>) keeps its own
            # badge instead of collapsing into a generic "lookup".
            badges = (ref.ref_type, table_name)
            if dangling(table_name):
                badges += (BADGE_MISSING_IN_DB,)
            nodes.append(
                CoherenceNode(
                    kind="lookup",
                    label=f"Column '{column.field_name or ''}'",
                    badges=badges,
                    flagged=dangling(table_name),
                    table_name=table_name,
                    line=ref.line,
                    node=column,
                    payload=ref,
                )
            )
        return nodes

    def detail_node(detail) -> CoherenceNode:
        ref = refs_by_node.get(id(detail))
        children = lookup_nodes(detail.columns)
        children += [detail_node(child) for child in detail.details]
        return CoherenceNode(
            kind="detail",
            label=f"Detail '{_detail_label(detail)}'",
            badges=binding_badges(detail.table_name),
            flagged=dangling(detail.table_name),
            children=tuple(children),
            table_name=detail.table_name,
            line=ref.line if ref is not None else detail.sourceline,
            node=detail,
            payload=ref,
        )

    page_nodes: list[CoherenceNode] = []
    for page in project.pages:
        ref = refs_by_node.get(id(page))
        children = lookup_nodes(page.columns)
        children += [detail_node(detail) for detail in page.details]
        page_nodes.append(
            CoherenceNode(
                kind="page",
                label=f"Page '{_page_label(page)}'",
                badges=binding_badges(page.table_name),
                flagged=dangling(page.table_name),
                children=tuple(children),
                table_name=page.table_name,
                line=ref.line if ref is not None else page.sourceline,
                node=page,
                payload=ref,
            )
        )
    return CoherenceNode(kind="branch", label=PAGES_BRANCH_LABEL, children=tuple(page_nodes))


def build_coherence_tree(project, schema: DatabaseSchema) -> CoherenceTree:
    """Build both branches of the coherence view from one project + one schema.

    What `flagged` means — settled with the requester, and deliberately wider
    than "broken":

    * **Pages branch.** A Page/Detail/lookup whose target relation does not
      exist in the live DB is flagged **at that reference point**. This is
      where a renamed or dropped table surfaces. It is explicitly *not*
      surfaced as a synthetic row under "Tables and Views" — that branch is
      purely DB-sourced, and a relation that does not exist has no row there
      to attach anything to.
    * **Tables and Views branch.** A real relation referenced nowhere in the
      XML (`page_count == detail_count == lookup_count == 0`) *is* flagged.
      Note the nuance: an unreferenced table is not a coherence error the way
      a dangling XML reference is — nothing is broken, the XML simply does not
      expose it. The toggle means **"things needing attention"**, not strictly
      "things that are broken", and this case is wanted under that reading.
    * **Columns.** `ColumnCheck.ok is False` folds in, except for calculated
      columns (BUG-006), which are DB-less by design.
    """
    usages = collect_table_usages(project)
    usages_by_name = {usage.name: list(usage.references) for usage in usages}

    # One reference per model node: a page/detail contributes its table
    # binding, a column its lookup. Keyed by identity so the Pages walk can
    # ask "what did the shared analyzer say about this exact node?".
    refs_by_node: dict[int, TableReference] = {}
    for usage in usages:
        for ref in usage.references:
            refs_by_node.setdefault(id(ref.node), ref)

    db_checks = check_db_against_xml(project, schema)
    xml_checks_by_name = {check.name: check for check in check_xml_against_db(project, schema)}

    return CoherenceTree(
        tables_and_views=_build_tables_branch(db_checks, xml_checks_by_name, usages_by_name, schema),
        pages=_build_pages_branch(project, schema, refs_by_node),
    )
