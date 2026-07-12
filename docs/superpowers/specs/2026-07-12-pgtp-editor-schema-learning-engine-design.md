# PGTP Editor — Schema Learning Engine + Auto-Enrich Wiring (Schema Learning Sub-project A of 2) Design Specification

**Date:** 2026-07-12
**Status:** Approved for planning
**Depends on:** the standalone `pgtp_analytics` tool's `pgtp_schema` package (`model.py`, `parser.py`, `types.py`, `xsd_gen.py`) and its own design doc, [`pgtp_analytics/docs/superpowers/specs/2026-07-12-pgtp-xsd-synthesis-design.md`](../../../../pgtp_analytics/docs/superpowers/specs/2026-07-12-pgtp-xsd-synthesis-design.md); the original shell design ([2026-07-11-pgtp-editor-design.md](2026-07-11-pgtp-editor-design.md), §5.1 docked panels including the Audit/Problems panel); `pgtp_editor/ui/main_window.py` (`open_project_file`).

## 1. Context and scope

Schema Learning is a new feature that did not appear among the original four core goals of PGTP Editor. It grew out of a separate, already-built, already-tested standalone tool — `pgtp_analytics`'s `pgtp_schema` package — which reverse-engineers an XSD schema from a corpus of `.pgtp` sample files and can incrementally update that schema as new files are processed. The idea driving this feature: since PGTP Editor already opens real `.pgtp` files as part of its normal workflow, every file a user opens is a free opportunity to keep improving the app's (and, indirectly, the user's) structural knowledge of the still-undocumented `.pgtp` format, with zero extra effort from the user.

This feature is being delivered as two sub-projects:

1. **Schema learning engine + auto-enrich wiring** (this document) — vendors the `pgtp_schema` logic into `pgtp_editor`, extends its `Model` with a human-readable `labels` field, and wires `File → Open` to feed every successfully opened file into a local, ever-growing schema model, reporting findings into the existing Audit panel.
2. **"Annotate Schema Values..." UI** (separate document, written in parallel by another agent) — the menu action and dialog where a user manually attaches labels to the enum values this sub-project's engine discovers. Depends on this document's `labels` field existing on `Model`.

This document covers only sub-project 1. Sub-project 2 is out of scope here except where its dependency on this document's data shape needs to be stated precisely (see §2.2).

### 1.1 Why vendor rather than depend on `pgtp_analytics` as a library

`pgtp_analytics` is a separate git repository, built and tested as a standalone command-line tool with its own CLI (`build`/`update` subcommands) for offline/bulk corpus processing. PGTP Editor needs the same core inference logic (`Model`, `walk_document`, type inference, XSD generation) but invoked in-process from a GUI event handler, not shelled out to as an external process, and without any CLI argument-parsing surface. Vendoring the four logic modules directly into `pgtp_editor/schema_learning/` keeps the dependency simple (no cross-repo import, no packaging of `pgtp_analytics` as an installable dependency) while `pgtp_analytics` itself remains the historical record of how this logic was originally designed and built as a standalone tool — its own spec, plan, and `cli.py` remain there, untouched, for anyone who wants to do bulk/offline corpus building outside the GUI app.

## 2. Scope

### 2.1 In scope

- A new `pgtp_editor/schema_learning/` package containing vendored copies of `model.py`, `parser.py`, `types.py`, and `xsd_gen.py` from `pgtp_analytics/pgtp_schema/`, plus an `__init__.py`.
- Adding `defusedxml` to `pyproject.toml`'s `dependencies`.
- Extending `Model`'s per-attribute entries with an optional `labels: dict[str, str]` field (observed value string → human-readable label), preserved untouched by `merge_element()` under all circumstances, including enum overflow.
- Extending `xsd_gen.generate_xsd` to emit `<xs:annotation><xs:documentation>` for enumeration values that have a label.
- A per-user, non-repo-tracked storage location for `schema_model.json` and a derived `schema.xsd`, using `QStandardPaths.AppDataLocation`.
- A new `MainWindow._enrich_schema_from_file(self, path)` method, called only from the success path of `open_project_file`, that loads the local model, merges the newly opened file's structure into it, saves both artifacts, and reports a summary into `self.audit_panel`.
- Unit tests for `labels` preservation and `xsd_gen` annotation emission; an integration test running the enrichment path end-to-end against the two real sample files in `sample/`; a `pytest-qt` test confirming Audit panel reporting on success and complete non-interference on failure.

### 2.2 Explicitly out of scope

- **The "Annotate Schema Values..." UI itself** (sub-project 2) — this document only adds the `labels` field's storage and preservation semantics to `Model`. There is no way for a user to actually set a label yet; sub-project 2 is the only thing that will ever write into `labels` (see §3.2).
- **Enrichment from any other `load_project` call site.** Only `File → Open` (`open_project_file`) triggers schema learning. The Diff/Merge feature's Source/Target file pickers (`_compare_merge_two_files`, `_compare_page_with`, `_compare_detail_with` in `main_window.py`) call `load_project` directly and are explicitly **not** touched by this sub-project — this was an explicit decision during brainstorming, not an oversight. A file opened only to be diffed against, and never opened via `File → Open`, does not feed the schema model.
- **Any change to `pgtp_editor.model`'s own lxml-based parser** (`pgtp_editor/model/parser.py`, `pgtp_editor/model/nodes.py`). That module parses a `.pgtp` file into a `ProjectModel` for display in the Project Tree and for diffing. This sub-project's parse (`schema_learning/parser.py`'s `walk_document`) is a second, fully independent parse of the same file, using a different XML library (`defusedxml` vs. `lxml`) for a different purpose (structural schema learning vs. building a navigable, diffable object model). Neither parser calls into the other; they do not share code, and nothing here changes `model/parser.py`'s behavior in any way.
- **Any manual/CLI-invoked `build`/`update` commands inside `pgtp_editor`.** `pgtp_schema/cli.py` is deliberately **not** vendored (see §3.1). The original `pgtp_analytics` tool's CLI remains available separately for bulk/offline corpus building if ever needed. This sub-project's automatic in-app enrichment via `File → Open` is the only ingestion path being built here.

## 3. Architecture

### 3.1 Module layout

```
pgtp_editor/
├── schema_learning/
│   ├── __init__.py         # NEW package
│   ├── model.py             # vendored from pgtp_analytics/pgtp_schema/model.py,
│   │                        # + labels field (§3.2)
│   ├── parser.py            # vendored from pgtp_analytics/pgtp_schema/parser.py,
│   │                        # unchanged (walk_document/walk_element, CESU-8 sanitization)
│   ├── types.py             # vendored from pgtp_analytics/pgtp_schema/types.py, unchanged
│   ├── xsd_gen.py           # vendored from pgtp_analytics/pgtp_schema/xsd_gen.py,
│   │                        # + xs:documentation emission (§3.3)
│   └── storage.py           # NEW: schema_model_path()/schema_xsd_path() helpers (§3.4)
├── ui/
│   └── main_window.py       # gains _enrich_schema_from_file, called at the end of
│                             # open_project_file's success path (§3.5)
```

`pgtp_schema/cli.py` is **not** vendored — see §2.2. Everything else is a near-verbatim copy; the only source changes made during vendoring are the `labels` field addition in `model.py` (§3.2) and the annotation emission in `xsd_gen.py` (§3.3). `parser.py` and `types.py` are vendored byte-for-byte (module-level docstrings/comments aside), including `parser.py`'s CESU-8 surrogate-pair sanitization workaround and its use of `defusedxml.ElementTree` rather than stdlib XML.

`pyproject.toml`'s `dependencies` list gains `"defusedxml>=0.7"` alongside the existing `PySide6>=6.6` and `lxml>=5.0` entries — `defusedxml` is needed for the vendored `schema_learning/parser.py`; it is not otherwise a transitive dependency of `PySide6` or `lxml`.

### 3.2 The `labels` field on `Model`

Each attribute entry in `Model.paths[path]["attributes"][attr_name]` — currently `{"type", "values", "overflowed", "attr_seen_count"}` in the vendored source — gains a fifth key:

```python
"labels": {}   # dict[str, str]: observed value string -> human-readable label
```

Set whenever a new attribute entry is created in `merge_element` (both the secret-denylist branch and the normal branch in `_get_or_create_path`'s caller), defaulting to an empty dict. Concretely, in the vendored `model.py`, both attribute-entry literals inside `merge_element` gain the key:

```python
if attr_name not in entry["attributes"]:
    if _looks_like_secret(attr_name):
        entry["attributes"][attr_name] = {
            "type": value_type,
            "values": None,
            "overflowed": True,
            "attr_seen_count": 1,
            "labels": {},
        }
    else:
        entry["attributes"][attr_name] = {
            "type": value_type,
            "values": [value],
            "overflowed": False,
            "attr_seen_count": 1,
            "labels": {},
        }
```

**`merge_element` must never touch, clear, or overwrite `labels`.** It is purely additive, populated exclusively by the future "Annotate Schema Values..." UI (sub-project 2), never by file ingestion. No line in the vendored `merge_element`/`_merge_children` reads or writes `attr_entry["labels"]` — the field is carried through untouched by every merge, exactly like `attr_seen_count`'s sibling fields that `merge_element` doesn't need to inspect for its own bookkeeping.

**Decision — enum overflow and stale labels.** The existing overflow branch in `merge_element` is:

```python
if len(attr_entry["values"]) > ENUM_MAX_VALUES:
    attr_entry["overflowed"] = True
    attr_entry["values"] = None
    events.append({"kind": "enum_overflow", "path": path, "attr": attr_name})
```

This sets `values` to `None` but must **not** touch `labels`. Any labels a user had previously attached to now-orphaned enum values remain in `attr_entry["labels"]`, keyed by value strings that no longer appear in (the now-`None`) `values`, and are simply unused by `xsd_gen` once the attribute is overflowed (see §3.3 — `xsd_gen` only ever consults `labels` for values it is actually about to emit as `xs:enumeration` elements, and an overflowed attribute emits none).

This is a deliberate, considered choice, not an oversight: **leave stale label data around harmlessly, rather than deleting it on overflow.** Reasoning:
- Deleting on overflow would require threading a "does this value still matter" check through the overflow branch specifically to erase user-authored annotation data — extra code whose only effect is destroying data a user manually entered, on a purely incidental structural event (the 11th distinct value showing up in some unrelated file).
- The corpus is one-directional in practice (each `File → Open` only ever adds facts, never removes files from consideration), so overflow is normally permanent. But the model format itself does not forbid rebuilding a fresh model from a smaller/different corpus (e.g. a user's local `schema_model.json` accidentally deleted and rebuilt from only a few files) — in that rebuild scenario, an attribute that overflowed against the old, larger corpus is correctly not-overflowed against the new, smaller one, and any old labels sitting under previously-annotated value strings become relevant again for free, with no re-annotation needed. Deleting them at overflow time would have permanently and unnecessarily lost that possibility.
- A few unused `"labels": {"32": "Full export"}` dict entries sitting inert on an overflowed attribute cost nothing at runtime (they're skipped by `xsd_gen`, and by definition sub-project 2's annotation UI only offers annotation on values the enum still lists, so stale labels are simply invisible in the UI too) and cost negligible storage in a JSON file measured in KB–low MB.

No special-case cleanup code is introduced for this edge case. `labels` participates in `to_dict`/`from_dict`/`save`/`load` exactly like every other dict value already does — no schema versioning or migration logic is needed since `Model.from_dict` already reads whatever keys are present via plain `dict.get`-free direct dict access on `data.get("paths", {})`, and old model files (without the `labels` key) loaded by a newer version of this code would need one small allowance: **`Model.from_dict` itself needs no change** (it just stores whatever `paths` dict it's given), but any code that reads `attr_entry["labels"]` (i.e. `xsd_gen`, and sub-project 2's UI) must use `attr_entry.get("labels", {})` rather than a bare subscript, so a `model.json` written before this sub-project shipped (with no `labels` key at all) doesn't raise `KeyError` on first load. This is the only backward-compatibility concession needed, and it is cheap and local to the two read sites.

### 3.3 `xsd_gen` extension: emitting `xs:documentation`

Current enumeration-emitting code in `xsd_gen.py`'s `_attribute_lines`:

```python
if not attr_entry["overflowed"] and attr_entry["values"]:
    lines = [f"    <xs:attribute name={quoteattr(attr_name)} use={quoteattr(use)}>"]
    lines.append("      <xs:simpleType>")
    lines.append(f"        <xs:restriction base={quoteattr(base_type)}>")
    for value in sorted(attr_entry["values"]):
        lines.append(f"          <xs:enumeration value={quoteattr(value)}/>")
    lines.append("        </xs:restriction>")
    lines.append("      </xs:simpleType>")
    lines.append("    </xs:attribute>")
    return lines
```

The per-value loop changes to emit a nested `xs:annotation`/`xs:documentation` only when a label exists for that value, turning the previously-always-self-closed `<xs:enumeration .../>` into an open/close pair only in that case:

```python
labels = attr_entry.get("labels", {})
for value in sorted(attr_entry["values"]):
    label = labels.get(value)
    if label:
        lines.append(f"          <xs:enumeration value={quoteattr(value)}>")
        lines.append("            <xs:annotation>")
        lines.append(f"              <xs:documentation>{escape(label)}</xs:documentation>")
        lines.append("            </xs:annotation>")
        lines.append("          </xs:enumeration>")
    else:
        lines.append(f"          <xs:enumeration value={quoteattr(value)}/>")
```

(`escape` is already imported at module scope from `xml.sax.saxutils` alongside `quoteattr`, used elsewhere in the same file for the sibling-order-warning comment — no new import is needed.) A value with an empty-string or missing label (`labels.get(value)` falsy) keeps the existing single self-closed `<xs:enumeration value="..."/>` form exactly as today; only values with a genuinely non-empty label gain the documentation child. This is the only change `xsd_gen.py` needs for this sub-project — the rest of `_attribute_lines`, `_complex_type_lines`, and `generate_xsd` are vendored unchanged.

### 3.4 Storage location

A per-user local file, **not** tracked in the `pgtp_editor` git repository (unlike `model.py`/`parser.py`/etc., which are vendored source files that *are* committed — the distinction is between vendored code and the runtime data it produces). New module `pgtp_editor/schema_learning/storage.py`:

```python
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_MODEL_FILENAME = "schema_model.json"
_XSD_FILENAME = "schema.xsd"


def _app_data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def schema_model_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _MODEL_FILENAME


def schema_xsd_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _XSD_FILENAME
```

`QStandardPaths` is already available via the existing `PySide6` dependency — no new dependency is needed for this part. The optional `base_dir` parameter is the test-injection point (see §5): production code calls both functions with no arguments and gets the real per-user `AppDataLocation`; tests pass a `tmp_path`-derived directory so they never read or write the real user's actual AppData directory. This is a deliberately minimal injection mechanism — a plain optional parameter defaulting to the real location — rather than a module-level override global or a settings object, since the only caller that ever needs to override it is a test.

`schema.xsd` is regenerated to the same directory after every successful enrichment, matching the original tool's own "always derivable from the model, safe to regenerate every run" principle (see the `pgtp-xsd-synthesis-design.md`'s description of `schema.xsd` as "not tracked as separate state — always derivable from the model, so it's safe to regenerate and overwrite every run"). `_app_data_dir()` is created if it doesn't yet exist (`base_dir.mkdir(parents=True, exist_ok=True)` called by `_enrich_schema_from_file` before writing — see §3.5) since `QStandardPaths.writableLocation` returns a path that is not guaranteed to already exist on disk.

### 3.5 Auto-enrich wiring in `MainWindow`

`open_project_file` (`pgtp_editor/ui/main_window.py`) currently ends its success path with:

```python
self.project_tree.populate_from_project(project)
self._current_project = project
self._current_project_path = path
self.statusBar().showMessage(f"Opened: {path}", 5000)
```

This sub-project appends one call at the end of that success path — **after** `populate_from_project`/`_current_project`/`_current_project_path` are set, so the primary project-display behavior always completes first and is never gated on schema learning:

```python
self.project_tree.populate_from_project(project)
self._current_project = project
self._current_project_path = path
self.statusBar().showMessage(f"Opened: {path}", 5000)
self._enrich_schema_from_file(path)
```

Critically, this call sits strictly inside the existing `try` block's success path — it is never reached when `load_project` raises and control goes to the `except Exception as exc: QMessageBox.critical(...); return` branch. A broken/unparseable file (one that fails `pgtp_editor.model.parser.load_project`) never touches the schema-learning model, full stop — there is no code path that calls `_enrich_schema_from_file` except this one line, placed after the `except` branch's early `return`.

**`_enrich_schema_from_file(self, path)` body:**

```python
def _enrich_schema_from_file(self, path):
    try:
        model_path = schema_model_path()
        xsd_path = schema_xsd_path()
        model_path.parent.mkdir(parents=True, exist_ok=True)

        if model_path.exists():
            model = Model.load(model_path)
        else:
            model = Model()

        events = []
        for elem_path, attrib, child_tag_counts, has_text in walk_document(path):
            events.extend(model.merge_element(elem_path, attrib, child_tag_counts, has_text))

        model.save(model_path)
        xsd_path.write_text(generate_xsd(model), encoding="utf-8")

        self._report_schema_events(events, path)
    except Exception as exc:
        self.audit_panel.addItem(f"[Schema] Could not update schema knowledge: {exc}")
```

Steps, matching the brainstormed requirements one-to-one:
1. Loads the local `Model` from the per-user path via `schema_model_path()`, creating a fresh empty `Model()` if the file doesn't exist yet (first-run case — no prior `schema_model.json` on this machine).
2. Runs the file through `walk_document(path)` and `model.merge_element(...)` for each yielded `(path, attrib, child_tag_counts, has_text)` tuple, reusing the vendored logic directly — no shelling out to any CLI, since `cli.py` isn't vendored (§2.2).
3. Collects the resulting merge events — the same event dict shape `merge_element` already returns (`{"kind": ..., "path": ..., ...}`, optionally `"attr"`/`"value"` depending on `kind`).
4. Saves both the updated `model.json` and regenerated `schema.xsd` to the per-user directory.
5. Reports into the Audit panel via `_report_schema_events` (below).
6. The entire body is wrapped in `try`/`except Exception` so nothing here can propagate out and interfere with `open_project_file`'s own success (which has already fully completed by the time this method is even called — see the ordering above).

**Reporting into the Audit panel (`_report_schema_events`):**

```python
_SCHEMA_REPORT_TEMPLATES = {
    "new_element": "[Schema] NEW ELEMENT: {path} (first seen in {source})",
    "new_attribute": "[Schema] NEW ATTRIBUTE: {path}@{attr} (first seen in {source})",
    "new_value": '[Schema] NEW ATTR VALUE: {path}@{attr} += "{value}" (from {source})',
    "enum_overflow": "[Schema] ENUM OVERFLOWED: {path}@{attr} now free-form string (from {source})",
    "now_optional": "[Schema] NOW OPTIONAL: {path}@{attr} (previously required, from {source})",
}


def _report_schema_events(self, events, source_path):
    source_name = Path(source_path).name
    if len(events) > 20:
        self.audit_panel.addItem(f"[Schema] Learned {len(events)} new structural facts from {source_name}")
        return
    for event in events:
        template = _SCHEMA_REPORT_TEMPLATES[event["kind"]]
        self.audit_panel.addItem(template.format(source=source_name, **event))
```

This mirrors `pgtp_schema/cli.py`'s own `REPORT_TEMPLATES`/`format_event`, with two adaptations: every line is prefixed `"[Schema] "` so entries are identifiable at a glance in a shared panel that may also carry non-schema audit findings from other features in the future, and the >20-events case collapses to one summary line rather than flooding a shared, general-purpose panel with dozens of lines from a single file open (a threshold picked to match the brainstormed requirement verbatim: "if the enrichment produced more than 20 events, append ONE summary line ... otherwise, append one line per event"). `source` is the file's base name (`Path(path).name`), not the full path, to keep each Audit line short and readable, consistent with the CLI's own use of a short `source` label rather than a full path in its `REPORT_TEMPLATES` strings.

**Decision — what gets reported when schema learning itself fails.** If any exception occurs anywhere in `_enrich_schema_from_file`'s body — a corrupt local `model.json` that fails to parse, a `walk_document` failure on a structurally-unusual or malformed file (note: `schema_learning/parser.py`'s CESU-8 sanitization already handles the one known real-world malformed-encoding case, but an entirely different, unanticipated structural surprise could still raise), a disk I/O error writing the model or XSD, or anything else — a single line is appended to the Audit panel:

```
[Schema] Could not update schema knowledge: <exc>
```

This is a deliberate choice over both alternatives considered:
- **Failing completely silently** was rejected because the Audit panel's whole purpose (per the original design spec's docked-panel layout) is to be the place a user looks to understand what happened during an operation; a user who opens a file and later notices `schema.xsd` looks stale, or wonders why enrichment "isn't working," should have somewhere in the app to see that something went wrong, without needing to attach a debugger or read application logs that don't otherwise exist in this app.
- **Anything more elaborate** (e.g. a full traceback in the Audit panel, or a modal `QMessageBox`) was rejected because schema learning is a best-effort, silent-by-default background enrichment feature from the user's perspective — it must never be allowed to demand attention or interrupt the primary "open a project" workflow the way `open_project_file`'s own `QMessageBox.critical` legitimately does for an actual failed project load. A single terse Audit line is the right weight: discoverable if you look, never interruptive if you don't.

The necessary imports this adds to `main_window.py`: `from pathlib import Path` (if not already imported — it is not, currently), `from pgtp_editor.schema_learning.model import Model`, `from pgtp_editor.schema_learning.parser import walk_document`, `from pgtp_editor.schema_learning.xsd_gen import generate_xsd`, and `from pgtp_editor.schema_learning.storage import schema_model_path, schema_xsd_path`.

## 4. Non-goals recap (see also §2.2)

To avoid any ambiguity for implementers: this sub-project does not add a menu item, dialog, or any other user-facing entry point beyond the automatic `File → Open` wiring and the Audit panel lines it produces. There is no way, after this sub-project ships, for a user to inspect `schema_model.json`/`schema.xsd` from within the app, trigger enrichment manually, or set a `labels` value — all of that is either already possible only via inspecting the files directly on disk (an acceptable state for this sub-project, since it is purely an internal enrichment engine) or is explicitly sub-project 2's job.

## 5. Testing strategy

- **Unit tests for the `labels` field on the vendored `Model`** (`pgtp_editor/schema_learning/model.py`):
  - Setting a label on an attribute's value directly (`model.paths[path]["attributes"][attr]["labels"][value] = "some label"`) and confirming it round-trips through `to_dict`/`from_dict` and `save`/`load`.
  - Confirming `merge_element()` calls never clear or alter existing `labels` across multiple merges of the same attribute — including a merge sequence that pushes an attribute past the enum-overflow threshold (11th distinct value): assert `labels` still contains the pre-overflow entries afterward, even though `values` is now `None` and `overflowed` is `True`.
  - Confirming a freshly created attribute entry (first observation) always has `labels == {}`.
- **Unit tests for `xsd_gen`:**
  - An attribute with one labeled and one unlabeled enum value emits `<xs:annotation><xs:documentation>` only as a child of the labeled value's `<xs:enumeration>`, and the unlabeled value keeps the plain self-closed form.
  - An attribute with no `labels` key at all (simulating a `model.json` written before this sub-project existed) does not raise `KeyError` — confirms the `attr_entry.get("labels", {})` defensive read in `_attribute_lines`.
  - Label text containing XML-special characters (`<`, `&`) is escaped via `escape()` in the emitted `xs:documentation` (i.e. the output is well-formed XML, parseable by `defusedxml.ElementTree`).
- **Integration test** running the auto-enrich path (`walk_document` + `Model.merge_element`, not through any UI) against both real sample files present in this worktree's `sample/` directory — `sample/dev_Ferrara.pgtp` and `sample/Sdman_RencoStrikesBack.i01.r01_FRENCH.pgtp` — end-to-end (both files fed into one shared `Model` instance sequentially, mirroring how a user opening two files in a row would behave) without raising, confirming a non-trivial number of distinct paths (e.g. asserting `len(model.paths) > 10`) get recorded, and confirming `generate_xsd(model)` produces output parseable by `defusedxml.ElementTree`.
- **A `pytest-qt` UI test confirming:**
  - (a) A successful `open_project_file` call (against one of the real sample files) appends at least one entry to `self.audit_panel`, using a `tmp_path`-derived override passed via `schema_model_path(base_dir=...)`/`schema_xsd_path(base_dir=...)` (see §5.1 below for how the test wires this override in) so the test never touches the real user's actual AppData directory.
  - (b) A parse failure (`open_project_file` called with a path to a nonexistent or deliberately malformed file, triggering `load_project`'s existing `except Exception` branch and `QMessageBox.critical`) does **not** touch the schema model or the per-user files at all: the test asserts the model file was never created (if it didn't exist before the call) or, if it did exist beforehand (seeded by the test), that its mtime and content are byte-for-byte unchanged after the failed `open_project_file` call. This directly verifies the ordering guarantee in §3.5 — `_enrich_schema_from_file` is called strictly after the try/except's success path, never from the except branch.

### 5.1 Making the storage location overridable for tests

Per §3.4, `schema_model_path`/`schema_xsd_path` take an optional `base_dir` parameter. `_enrich_schema_from_file` itself, as specified in §3.5, calls them with no arguments (always resolving to the real `AppDataLocation`) — so the UI test needs one additional, minimal seam to inject a test directory without over-engineering a full settings/DI system: `MainWindow.__init__` gains an optional constructor parameter, `schema_storage_dir: Path | None = None`, stored as `self._schema_storage_dir`, and `_enrich_schema_from_file` calls `schema_model_path(self._schema_storage_dir)` / `schema_xsd_path(self._schema_storage_dir)` instead of the zero-argument form. Production code (`main.py`'s app entry point) constructs `MainWindow()` with no argument, exactly as today, and gets the real per-user location; the `pytest-qt` test constructs `MainWindow(schema_storage_dir=tmp_path)`. This is the simplest possible injection point — a single optional constructor parameter threaded through to two existing helper calls — with no new configuration object, no environment variable, and no module-level global to reset between tests.

## 6. Summary of decisions from brainstorming

- Schema Learning is delivered as two sub-projects, not one: this document (vendoring + auto-enrich engine) and a separate, parallel "Annotate Schema Values..." UI document, because the engine's data shape (specifically, the `labels` field's existence on `Model`) needs to be nailed down before the annotation UI can be designed against it, while the two pieces of work are otherwise independent enough to write up in parallel.
- `pgtp_schema/cli.py` is deliberately **not** vendored — the GUI app has no need for a CLI argument-parsing surface, and the original `pgtp_analytics` repo remains the home for offline/bulk corpus building via its own `build`/`update` commands.
- The vendored code moves into `pgtp_editor/schema_learning/`, a fully new, independent package — it shares no code with, and makes no changes to, `pgtp_editor.model`'s existing lxml-based parser, since the two exist for entirely different purposes (schema learning vs. building the navigable/diffable `ProjectModel`).
- `labels` is purely additive and exclusively written by the future annotation UI (sub-project 2) — `merge_element()` is guaranteed to never touch it, including through enum overflow.
- On enum overflow, stale `labels` entries for now-orphaned values are deliberately left in place rather than cleaned up — a conscious simplicity-over-cleanliness call, justified by: the cost of stale entries is negligible (skipped by `xsd_gen`, invisible to the future annotation UI since it only offers annotation on currently-listed enum values), and a rebuild-from-a-smaller-corpus scenario could make an "overflowed" attribute un-overflow again, in which case previously-set labels becoming relevant again for free is a mild positive, not a bug.
- Storage is per-user and explicitly **not** committed to the `pgtp_editor` git repository — `QStandardPaths.AppDataLocation`, matching how a locally-and-continuously-growing artifact (one that differs per machine and grows with whatever files that specific user has opened) should not be versioned alongside the application's own source.
- `schema.xsd` is regenerated in full from the model after every enrichment, never hand-edited or incrementally patched — carrying forward the same "always derivable, safe to regenerate every run" principle the original `pgtp_analytics` design established.
- Only `File → Open` (`open_project_file`) triggers auto-enrichment. The Diff/Merge feature's various file pickers (Source/Target for file-level compare, target pickers for page-level and detail-level compare) do **not** — an explicit scoping decision, not an oversight, made so that files opened transiently just to be compared against don't silently expand the schema model.
- Schema-learning failures are reported as a single terse Audit panel line (`"[Schema] Could not update schema knowledge: <reason>"`) rather than either failing silently or interrupting the user with a modal dialog — matching the feature's overall character as best-effort background enrichment that must never compete for attention with the actually-requested "open a project" action, while still being discoverable for a curious or troubleshooting user via the same Audit panel every other finding in the app already uses.
- Test isolation for the per-user storage path uses the simplest viable seam: an optional `base_dir` parameter on the two path-helper functions, plumbed through a single optional `MainWindow.__init__` constructor parameter (`schema_storage_dir`) — deliberately not a full settings/config-injection system, since no other caller needs to override this path.
