"""Structural checks of a v4 plan (dossier §4, §2.5, §2.5.1). Never raises on a broken plan.

``check(plan)`` returns every problem as an ``Issue``; unreadable JSON, schema violations, identity and
reference drift, batches, cycles, completeness, result/status consistency and unit rules are errors, a
few advisory findings are warnings. Human-view freshness is checked separately by ``render --check``.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
import json
import re
from typing import Any, Iterator, NamedTuple

from . import context as _context
from . import edges as _edges
from . import schema as _schema
from . import settings, store
from .model import ITEM_ID, TERMINAL, parse_ref

_UNIT_ID = re.compile(r"^U[0-9]+$")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_GLOB = re.compile(r"[*?\[{]")
_READ_PATH = re.compile(r"^@plan/(knowledge|decisions)/([^/]+)\.json$")
_TARGETED_EVENTS = frozenset({"start", "finish", "design_done", "phase_closed", "deviation", "blocker",
                              "difficulty", "assumption"})


class Issue(NamedTuple):
    level: str  # "error" | "warning"
    code: str
    where: str  # file, optionally followed by a JSON pointer
    message: str


def check(plan: store.Plan) -> list[Issue]:
    """All errors and warnings of ``plan``; an empty list means the plan is structurally sound."""
    issues: list[Issue] = []
    ctx = _Context(plan, issues)
    ctx.load_problems()
    ctx.schemas()
    ctx.identity()
    ctx.plan_state()
    ctx.membership()
    ctx.references()
    ctx.cycles()
    ctx.deadlock()
    ctx.batches()
    ctx.completeness()
    ctx.validation_shapes()
    ctx.authority()
    ctx.decisions()
    ctx.paths()
    ctx.results()
    ctx.closures()
    ctx.units()
    ctx.orchestration()
    ctx.log()
    ctx.advisories()
    ctx.context_scope()
    return issues


class _Context:
    def __init__(self, plan: store.Plan, out: list[Issue]):
        self.p = plan
        self.out = out

    # ---- helpers
    def error(self, code: str, where: str, message: str) -> None:
        self.out.append(Issue("error", code, where, message))

    def warn(self, code: str, where: str, message: str) -> None:
        self.out.append(Issue("warning", code, where, message))

    def docs(self) -> Iterator[tuple[str, str, str, dict]]:
        """``(kind, key, relative file, doc)`` for every loaded document."""
        p = self.p
        yield "plan", "", "plan.json", p.plan
        yield "brief", "", "brief.json", p.brief
        for key, doc in p.phases.items():
            yield "phase", key, p.rel(store.phase_path(p.root, key)), doc
        for key, doc in p.items.items():
            yield "item", key, p.rel(store.item_path(p.root, key)), doc
        for key, doc in p.decisions.items():
            yield "decision", key, p.rel(store.decision_path(p.root, key)), doc
        for key, doc in p.units.items():
            item_id, unit_id = key.split("/")
            yield "unit", key, p.rel(store.unit_path(p.root, item_id, unit_id)), doc
        for key, doc in p.documents.items():
            yield "document", key, f"knowledge/{key}.json", doc

    def file_of(self, kind: str, key: str) -> str:
        return self.p.rel(self.p.path(kind, key or None))

    def items_of(self, phase_id: str) -> list[str]:
        return [key for key in self.p.items if key.startswith(f"{phase_id}.")]

    # ---- checks
    def load_problems(self) -> None:
        for rel, message in self.p.problems:
            self.error("json", rel, message)

    def schemas(self) -> None:
        for kind, _key, rel, doc in self.docs():
            if not doc:
                continue  # an unreadable file is already reported as `json`
            for issue in _schema.validate(doc, kind):
                self.error("schema", f"{rel}{issue.path}", issue.message)

    def identity(self) -> None:
        p = self.p
        if p.plan.get("id") != p.root.name:
            self.error("id_mismatch", "plan.json/id",
                       f"plan id {p.plan.get('id')!r} differs from directory name {p.root.name!r}")
        for kind, key, rel, doc in self.docs():
            if kind in ("plan", "brief") or not doc:
                continue
            expected = key.split("/")[-1]
            if doc.get("id") != expected:
                self.error("id_mismatch", f"{rel}/id", f"{kind} id {doc.get('id')!r} differs from file name {expected!r}")
            if kind == "unit" and doc.get("item") != key.split("/")[0]:
                self.error("id_mismatch", f"{rel}/item",
                           f"unit item {doc.get('item')!r} differs from workspace {key.split('/')[0]!r}")

    def plan_state(self) -> None:
        status, pause = self.p.plan.get("status"), self.p.plan.get("pause")
        if status == "paused" and not (isinstance(pause, dict) and pause.get("reason")):
            self.error("plan_state", "plan.json/pause", "paused plan needs pause.reason")
        if status != "paused" and pause is not None:
            self.error("plan_state", "plan.json/pause", "only a paused plan may carry pause state")

    def membership(self) -> None:
        p = self.p
        listed = [x for x in p.plan.get("phases", []) if isinstance(x, str)] \
            if isinstance(p.plan.get("phases"), list) else []
        for phase_id in listed:
            if phase_id not in p.phases:
                self.error("phase_list", "plan.json/phases", f"phase {phase_id} is listed but has no phases/{phase_id}/phase.json")
        for phase_id in p.phases:
            if phase_id not in listed:
                self.error("phase_list", "plan.json/phases", f"phase directory {phase_id} is not listed in plan.phases")
        for phase_id, doc in p.phases.items():
            rel = self.file_of("phase", phase_id)
            declared = [x for x in doc.get("items", []) if isinstance(x, str)] if isinstance(doc.get("items"), list) else []
            for item_id in declared:
                if item_id not in p.items:
                    self.error("phase_items", f"{rel}/items", f"item {item_id} is listed but has no file")
            for item_id in self.items_of(phase_id):
                if item_id not in declared:
                    self.error("phase_items", f"{rel}/items", f"item file {item_id} is not listed in {phase_id}.items")
        for item_id in p.items:
            owner = item_id.split(".", 1)[0]
            if ITEM_ID.fullmatch(item_id) and owner not in p.phases:
                self.error("phase_items", self.file_of("item", item_id), f"item {item_id} lies in unknown phase {owner}")

    def references(self) -> None:
        p = self.p
        for field, edge in _edges.tagged(p):
            self.check_edge(field, edge)
        self.backlinks()
        self.artifacts()
        for key, item in p.items.items():
            rel = self.file_of("item", key)
            for index, read in enumerate(item.get("reads") if isinstance(item.get("reads"), list) else []):
                self.check_read_ref(f"{rel}/reads/{index}", read)
        for key, doc in p.units.items():
            rel = self.file_of("unit", key)
            item = p.items.get(key.split("/")[0])
            declared = {c["id"] for c in (item or {}).get("validation", []) if isinstance(c, dict) and "id" in c}
            for index, entry in enumerate(doc.get("checks") if isinstance(doc.get("checks"), list) else []):
                if isinstance(entry, str) and item is not None and entry not in declared:
                    self.error("ref_unknown", f"{rel}/checks/{index}", f"unknown item check {entry}")

    def check_edge(self, field: _edges.LinkField, edge: _edges.Edge) -> None:
        """Resolve one table link: its kind must be allowed by the field and a local target must exist."""
        if edge.kind == "parent":
            return  # a missing or self parent is reported as unit_parent
        try:
            parsed = parse_ref(edge.target)
        except ValueError:
            return  # a malformed ref is a schema error already
        if field.targets is not None and parsed.kind not in field.targets:
            self.error("ref_kind", edge.where, f"{edge.target} is a {parsed.kind}, expected {' or '.join(field.targets)}")
        elif parsed.plan is None and _edges.locate(self.p, edge.target) is None:
            what = f"unit {edge.target.split('/')[1]} in {edge.target.split('/')[0]}" if parsed.kind == "unit" \
                else f"reference {edge.target}"
            self.error("ref_unknown", edge.where, f"unknown {what}")

    def check_read_ref(self, where: str, read: Any) -> None:
        """``reads[].ref`` names data of this plan and carries its section in the ref or in ``section``, not both."""
        if not (isinstance(read, dict) and isinstance(read.get("ref"), str)):
            return
        try:
            parsed = parse_ref(read["ref"])
        except ValueError:
            return
        if parsed.plan is not None:
            self.error("reads_ref", f"{where}/ref", f"read ref {read['ref']} must name data of this plan")
        if parsed.section and read.get("section"):
            self.error("reads_ref", f"{where}/section", "a read ref with #section takes no section key")
        if parsed.plan is None and parsed.kind == "knowledge" and not parsed.section and read.get("section"):
            doc = self.p.documents.get(parsed.target)
            sections = doc.get("sections") if isinstance(doc, dict) else None
            if isinstance(sections, list) and not any(
                    isinstance(s, dict) and read["section"] in (s.get("id"), s.get("title")) for s in sections):
                self.error("ref_unknown", f"{where}/section",
                           f"unknown section {read['section']!r} in {read['ref']}")

    def backlinks(self) -> None:
        """A stored back-pointer must be matched by the forward field of the document it names, and vice versa."""
        docs = list(_edges.documents(self.p))
        for (kind, field), (_fwd_kind, fwd_field) in _edges.BACKLINKS.items():
            by_key = {key: doc for k, key, _name, doc in docs if k == kind and isinstance(doc, dict)}
            for key, doc in by_key.items():
                rel = self.file_of(kind, key)
                back = doc.get(field)
                if isinstance(back, str):
                    other = by_key.get(back)
                    if other is None:
                        self.error("ref_unknown", f"{rel}/{field}", f"unknown reference {back}")
                    elif key not in _strings(other.get(fwd_field)):
                        self.error("backlink_mismatch", f"{rel}/{field}",
                                   f"{key} names {back} in {field}, but {back} does not list {key} in {fwd_field}")
                for index, ref in enumerate(_strings(doc.get(fwd_field))):
                    other = by_key.get(ref)
                    if other is not None and other.get(field) != key:
                        self.error("backlink_mismatch", f"{rel}/{fwd_field}/{index}",
                                   f"{key} lists {ref} in {fwd_field}, but {ref} does not name {key} in {field}")

    def artifacts(self) -> None:
        """An output declares an artifact id once per plan; an input that cites it names the same path."""
        outputs: dict[str, tuple[str, dict]] = {}
        for ident, item_id, entry in _edges.declared_artifacts(self.p):
            if entry.get("role") != "output":
                continue
            if ident in outputs:
                self.error("artifact_duplicate", self.artifact_where(item_id, entry),
                           f"artifact id {ident} is already declared as an output of {outputs[ident][0]}")
            else:
                outputs[ident] = (item_id, entry)
        for ident, item_id, entry in _edges.declared_artifacts(self.p):
            declared = outputs.get(ident)
            if entry.get("role") == "input" and declared and entry.get("path") != declared[1].get("path"):
                self.error("artifact_path", self.artifact_where(item_id, entry),
                           f"input artifact {ident} names {entry.get('path')!r}, its output names {declared[1].get('path')!r}")

    def artifact_where(self, item_id: str, entry: dict) -> str:
        entries = self.p.items[item_id].get("artifacts")
        index = next(i for i, e in enumerate(entries) if e is entry)
        return f"{self.file_of('item', item_id)}/artifacts/{index}/id"

    def cycles(self) -> None:
        p = self.p
        graph = {key: [d for d in doc.get("depends_on", []) if d in p.items] if isinstance(doc.get("depends_on"), list)
                 else [] for key, doc in p.items.items()}
        self.report_cycles("item", graph, "depends_on")
        order = [x for x in p.plan.get("phases", []) if isinstance(x, str) and x in p.phases] \
            if isinstance(p.plan.get("phases"), list) else []
        phases = {}
        for index, phase_id in enumerate(order):
            declared = p.phases[phase_id].get("depends_on")
            if isinstance(declared, list):
                phases[phase_id] = [d for d in declared if d in p.phases]
            else:
                phases[phase_id] = [order[index - 1]] if index else []  # default: the previous phase
        self.report_cycles("phase", phases, "depends_on")

    def deadlock(self) -> None:
        """Wait cycles through a phase dependency; pure item and pure phase cycles belong to ``cycles``."""
        from . import parallel
        for found in parallel.deadlocks(self.p):
            self.error("dependency_deadlock", self.file_of("item", found.items[0]),
                       f"{found.render()} never becomes ready")

    def report_cycles(self, label: str, graph: dict[str, list[str]], field: str, prefix: str = "") -> None:
        state: dict[str, int] = {}
        reported: set[frozenset] = set()

        def visit(node: str, trail: list[str]) -> None:
            state[node] = 1
            for nxt in graph.get(node, ()):
                if state.get(nxt) == 1:
                    cycle = trail[trail.index(nxt):] + [nxt]
                    if frozenset(cycle) not in reported:
                        reported.add(frozenset(cycle))
                        self.error("cycle", f"{prefix}{cycle[0]}", f"{label} dependency cycle: " + " -> ".join(cycle))
                elif nxt not in state:
                    visit(nxt, [*trail, nxt])
            state[node] = 2

        for node in graph:
            if node not in state:
                visit(node, [node])

    def batches(self) -> None:
        p = self.p
        for phase_id, doc in p.phases.items():
            rel = self.file_of("phase", phase_id)
            declared = [x for x in doc.get("items", []) if isinstance(x, str)] if isinstance(doc.get("items"), list) else []
            batches = [b for b in doc.get("batches", []) if isinstance(b, dict)] if isinstance(doc.get("batches"), list) else []
            seen_ids: set[str] = set()
            membership: dict[str, list[str]] = {}
            for index, batch in enumerate(batches):
                batch_id = batch.get("id")
                if batch_id in seen_ids:
                    self.error("batch_id", f"{rel}/batches/{index}/id", f"duplicate batch id {batch_id}")
                seen_ids.add(batch_id)
                for item_id in batch.get("items", []) if isinstance(batch.get("items"), list) else []:
                    if not isinstance(item_id, str):
                        continue
                    if not ITEM_ID.fullmatch(item_id) or item_id.split(".", 1)[0] != phase_id or item_id not in declared:
                        self.error("batch_foreign", f"{rel}/batches/{index}/items",
                                   f"batch {batch_id} lists {item_id}, which does not belong to {phase_id}")
                        continue
                    membership.setdefault(item_id, []).append(str(batch_id))
            for item_id in declared:
                found = membership.get(item_id, [])
                if len(found) != 1:
                    self.error("batch_coverage", f"{rel}/batches",
                               f"item {item_id} is in {len(found)} batches" + (f" ({', '.join(found)})" if found else "")
                               + ", expected exactly 1")

    def completeness(self) -> None:
        p = self.p
        for phase_id, phase in p.phases.items():
            if phase.get("design") != "detailed":
                continue
            for item_id in self.items_of(phase_id):
                item, rel = p.items[item_id], self.file_of("item", item_id)
                if not item:
                    continue

                def missing(field: str, why: str, *, rel=rel, item_id=item_id) -> None:
                    self.error("incomplete", f"{rel}/{field}", f"detailed item {item_id} needs {why}")

                for field in ("summary", "why"):
                    if not item.get(field):
                        missing(field, f"a non-empty {field}")
                scope = item.get("scope")
                if not (isinstance(scope, dict) and scope.get("include")):
                    missing("scope/include", "at least one scope.include entry")
                checks = item.get("validation") if isinstance(item.get("validation"), list) else []
                if not any(isinstance(c, dict) and c.get("kind") == "acceptance"
                           and bool(c.get("cmd") or c.get("procedure")) for c in checks):
                    missing("validation", "at least one acceptance check")
                if not item.get("deliverables"):
                    missing("deliverables", "at least one deliverable")
                if not (item.get("reads") or item.get("task_files") or item.get("guidance") or item.get("sections")):
                    missing("reads", "reads, task_files, guidance or self-contained sections")

    def validation_shapes(self) -> None:
        for kind, _key, rel, doc in self.docs():
            checks = doc.get("validation") if kind in ("item", "phase") else None
            for index, entry in enumerate(checks if isinstance(checks, list) else []):
                if not isinstance(entry, dict):
                    continue
                carriers = [name for name in ("cmd", "procedure") if entry.get(name)]
                if len(carriers) != 1:
                    self.error("validation_carrier", f"{rel}/validation/{index}",
                               "validation needs exactly one of cmd or procedure")
        for key, unit in self.p.units.items():
            command = unit.get("command")
            if isinstance(command, dict) and not command.get("cmd"):
                self.error("validation_carrier", f"{self.file_of('unit', key)}/command",
                           "a command unit needs an exact cmd")

    def authority(self) -> None:
        for key, item in self.p.items.items():
            authority = item.get("authority")
            if not isinstance(authority, dict) or authority.get("kind") not in {"owner_gate", "external_gate"}:
                continue
            kind = authority["kind"]
            identities = [name for name in ("gate", "label") if authority.get(name)]
            if len(identities) != 1:
                self.error("authority_identity", f"{self.file_of('item', key)}/authority",
                           f"{kind} needs exactly one of gate or label")
            if not authority.get("scope"):
                self.error("authority_scope", f"{self.file_of('item', key)}/authority/scope",
                           f"{kind} needs its source scope")

    def decisions(self) -> None:
        for key, doc in self.p.decisions.items():
            rel, status = self.file_of("decision", key), doc.get("status")
            needed = {"open": ("question",), "proposed": ("decision", "rationale"),
                      "accepted": ("decision", "rationale")}.get(status, ())
            for field in needed:
                if not doc.get(field):
                    self.error("decision_fields", f"{rel}/{field}", f"a {status} decision needs {field}")

    def paths(self) -> None:
        from . import context
        for kind, _key, rel, doc in self.docs():
            for pointer, value in _path_fields(kind, doc):
                parts = re.split(r"[\\/]", value)
                if ".." in parts:
                    self.error("path", f"{rel}{pointer}", f"path {value!r} contains a '..' segment")
                elif value.startswith("/") or _DRIVE.match(value) or value.startswith("~"):
                    self.error("path", f"{rel}{pointer}", f"path {value!r} must be relative to the repository or @plan/")
                elif kind in ("item", "unit") and pointer.startswith(("/reads/", "/examples/")) and context.human_view(self.p, value):
                    self.error("human_view", f"{rel}{pointer}", "plan Markdown and human views cannot be agent inputs")

    def results(self) -> None:
        for key, doc in self.p.items.items():
            rel, status = self.file_of("item", key), doc.get("status")
            result = doc.get("result")
            result = result if isinstance(result, dict) else {}
            if status in ("done", "done_with_deviations") and not result.get("finished_at"):
                self.error("result_status", f"{rel}/result", f"status {status} needs result.finished_at")
            if status == "in_progress" and not result.get("started_at"):
                self.error("result_status", f"{rel}/result", "status in_progress needs result.started_at")
            if status == "skipped" and not result.get("decision"):
                self.error("result_status", f"{rel}/result", "status skipped needs result.decision")

    def closures(self) -> None:
        """Closure drift after parallel trees merged: terminal but unclosed, or closed with open items."""
        p = self.p
        for phase_id, phase in p.phases.items():
            declared = phase.get("items") if isinstance(phase.get("items"), list) else []
            members = [i for i in declared if isinstance(i, str) and i in p.items]
            if not members:
                continue
            where = f"{self.file_of('phase', phase_id)}/closed"
            open_items = [i for i in members if p.items[i].get("status", "todo") not in TERMINAL]
            if not phase.get("closed") and not open_items:
                self.warn("phase_unclosed", where, f"every item of {phase_id} is terminal but the phase is not closed; "
                                                   f"run plan.py reconcile {p.plan.get('id', p.root.name)}")
            elif phase.get("closed") and open_items:
                self.warn("phase_closure_stale", where, f"{phase_id} is closed but {', '.join(open_items)} "
                                                        f"{'is' if len(open_items) == 1 else 'are'} not terminal; "
                                                        f"reopen or finish {open_items[0]}")

    def units(self) -> None:
        p = self.p
        for key in p.units:
            if key.split("/")[0] not in p.items:
                self.error("units_list", self.file_of("unit", key), f"unit workspace {key.split('/')[0]} has no item file")
        for item_id, item in p.items.items():
            keys = [k for k in p.units if k.startswith(f"{item_id}/")]
            ids = {k.split("/")[1] for k in keys}
            rel = self.file_of("item", item_id)
            declared = [u for u in item.get("units", []) if isinstance(u, str)] if isinstance(item.get("units"), list) else []
            for unit_id in declared:
                if unit_id not in ids:
                    self.error("units_list", f"{rel}/units", f"unit {unit_id} is listed but has no file in {item_id}/")
            for unit_id in sorted(ids - set(declared)):
                self.error("units_list", f"{rel}/units", f"unit file {item_id}/{unit_id} is not listed in {item_id}.units")
            self.unit_overlap(item_id, keys)
            hints = [t.get("path") for t in item.get("task_files", []) if isinstance(t, dict) and isinstance(t.get("path"), str)] \
                if isinstance(item.get("task_files"), list) else []
            for key in keys:
                files = p.units[key].get("files")
                for index, path in enumerate(files if isinstance(files, list) else []):
                    if hints and isinstance(path, str) and not any(path == h or fnmatchcase(path, h) for h in hints):
                        self.warn("unit_files_uncovered", f"{self.file_of('unit', key)}/files/{index}",
                                  f"{path} is not covered by the task_files of {item_id}")

    def unit_overlap(self, item_id: str, keys: list[str]) -> None:
        from . import units as work_units
        units = {k.split("/")[1]: self.p.units[k] for k in keys}
        deps = {u: set(work_units.dependencies(self.p, item_id, u)) for u in units}

        def reaches(start: str, goal: str) -> bool:
            stack, seen = list(deps[start]), set()
            while stack:
                node = stack.pop()
                if node == goal:
                    return True
                if node not in seen:
                    seen.add(node)
                    stack.extend(deps.get(node, ()))
            return False

        names = sorted(units)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if reaches(a, b) or reaches(b, a):
                    continue
                for fa in _files(units[a]):
                    for fb in _files(units[b]):
                        if globs_overlap(fa, fb):
                            self.error("unit_overlap", f"{item_id}/{a}",
                                       f"independent units {a} and {b} both own {fa!r} / {fb!r}")

    def orchestration(self) -> None:
        from . import units
        for _kind, _key, rel, doc in self.docs():
            setting = doc.get("orchestration")
            if isinstance(setting, dict) and "max_parallel" in setting:
                value = setting["max_parallel"]
                if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    self.error("orchestration", f"{rel}/orchestration/max_parallel", "must be a positive integer")
            route = doc.get("route")
            if isinstance(route, dict) and bool(route.get("provider")) != bool(route.get("model")):
                self.error("route", f"{rel}/route", "explicit provider and model must be supplied together")
            sections = doc.get("sections")
            section_ids = [s["id"] for s in sections if isinstance(s, dict) and isinstance(s.get("id"), str)] if isinstance(sections, list) else []
            if len(section_ids) != len(set(section_ids)):
                self.error("sections", f"{rel}/sections", "section ids must be unique within a document")
        for key, doc in self.p.units.items():
            item_id, uid = key.split("/")
            parent = doc.get("parent")
            if parent and (parent == uid or f"{item_id}/{parent}" not in self.p.units):
                self.error("unit_parent", key, "parent must name another unit in this item")
            if doc.get("kind") == "command" and not doc.get("command"):
                self.error("unit_command", key, "a command unit needs a command check")
        for item_id in self.p.items:
            graph = {u: units.dependencies(self.p, item_id, u) for u in units.unit_ids(self.p, item_id)}
            self.report_cycles("unit", graph, "depends_on", prefix=f"{item_id}/")

    def log(self) -> None:
        p = self.p
        for number, event, error in store.log_lines(p.root):
            where = f"{store.LOG}:{number}"
            if error is not None:
                self.error("json", where, error)
                continue
            for issue in _schema.validate(event, "log-event"):
                self.error("schema", f"{where}{issue.path}", issue.message)
            if event.get("type") in _TARGETED_EVENTS and not (event.get("item") or event.get("phase")):
                self.error("log_target", where, f"{event.get('type')} event needs item or phase")
            if isinstance(event.get("item"), str) and event["item"] not in p.items:
                self.error("ref_unknown", f"{where}/item", f"unknown item {event['item']}")
            if isinstance(event.get("phase"), str) and event["phase"] not in p.phases:
                self.error("ref_unknown", f"{where}/phase", f"unknown phase {event['phase']}")

    def advisories(self) -> None:
        p = self.p
        title = p.plan.get("title")
        for field in ("context", "goal"):
            if title and p.plan.get(field) == title:
                self.warn("context_default", f"plan.json/{field}", f"plan {field} still equals the title; write it")
        for key, item in p.items.items():
            rel = self.file_of("item", key)
            produced = self.produced_paths(key)
            externally_gated = (item.get("authority") or {}).get("kind") == "external_gate"
            dependencies_ready = all(
                dep not in p.items or p.items[dep].get("status") in TERMINAL
                for dep in item.get("depends_on", [])
            ) if isinstance(item.get("depends_on"), list) else True
            produced_here = lambda path, produced=produced: path in produced or any(
                output.endswith("/") and path.startswith(output) for output in produced)
            for index, read in enumerate(item.get("reads", []) if isinstance(item.get("reads"), list) else []):
                if (isinstance(read, dict) and read.get("required") is True and isinstance(read.get("path"), str)
                        and not _GLOB.search(read["path"]) and not self.exists(read["path"])
                        and item.get("status") not in TERMINAL and not externally_gated and dependencies_ready
                        and not produced_here(read["path"])):
                    self.warn("read_missing", f"{rel}/reads/{index}/path",
                              f"required read {read['path']} does not exist and no dependency produces it")
            for index, hint in enumerate(item.get("task_files", []) if isinstance(item.get("task_files"), list) else []):
                if (isinstance(hint, dict) and hint.get("change") == "modify" and isinstance(hint.get("path"), str)
                        and not _GLOB.search(hint["path"]) and not self.exists(hint["path"])):
                    self.warn("modify_missing", f"{rel}/task_files/{index}/path",
                              f"{hint['path']} is marked modify but does not exist")

    def read_targets(self) -> tuple[set[str], set[str]]:
        """Knowledge ids and decision ids that some item reads or (decisions) names, from plan data only."""
        documents: set[str] = set()
        decisions: set[str] = set()
        for item in self.p.items.values():
            if not isinstance(item, dict):
                continue
            for read in item.get("reads", []) if isinstance(item.get("reads"), list) else []:
                if not isinstance(read, dict):
                    continue
                ref, path = read.get("ref"), read.get("path")
                if isinstance(ref, str):
                    base = ref.split("#", 1)[0]
                    if base.startswith("knowledge/"):
                        documents.add(base[len("knowledge/"):])
                    elif re.fullmatch(r"D[0-9]+", base):
                        decisions.add(base)
                match = _READ_PATH.match(path) if isinstance(path, str) else None
                if match:
                    (documents if match[1] == "knowledge" else decisions).add(match[2])
            for ref in item.get("decisions", []) if isinstance(item.get("decisions"), list) else []:
                if isinstance(ref, str):
                    decisions.add(ref)
        return documents, decisions

    def context_scope(self) -> None:
        """Binding of knowledge and decisions to context packs, and brief/plan text that rides in every pack."""
        p = self.p
        mode = _context.pack_mode(p)
        read_documents, read_decisions = self.read_targets()
        fix = "plan.py link <plan> {ref} <Pn|Pn.m> --kind applies_to"
        for kind, entries, reached in (("document", p.documents, read_documents), ("decision", p.decisions, read_decisions)):
            for key, doc in entries.items():
                if not isinstance(doc, dict):
                    continue
                where = self.file_of(kind, key)
                applies = doc.get("applies_to")
                if doc.get("global") is True and applies:
                    self.error("scope_ambiguous", f"{where}/global", "global and applies_to together are ambiguous; keep one")
                    continue
                if applies or doc.get("global") is True or (kind == "decision" and doc.get("status") != "accepted"):
                    continue
                ref = f"knowledge/{key}" if kind == "document" else key
                if mode == "legacy":
                    size = max(1, len(json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")) // 1024) if kind == "document" else None
                    sized = f" ({size} KB)" if size else ""
                    self.warn("context_unbound", f"{where}/applies_to",
                              f"{ref}{sized} has no applies_to and enters every context pack; bind it "
                              f"({fix.format(ref=ref)}) or set global: true")
                elif key not in reached:
                    self.warn("context_unbound", f"{where}/applies_to",
                              f"{ref} reaches no context pack: bind it ({fix.format(ref=ref)}), set global: true, "
                              "or read it from an item")
        brief = p.brief if isinstance(p.brief, dict) else {}
        texts: list[tuple[str, int, str]] = []
        for field in ("messages", "sections"):
            for index, entry in enumerate(brief.get(field, []) if isinstance(brief.get(field), list) else []):
                if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                    texts.append((field, index, entry["text"]))
        seen: dict[str, tuple[str, int]] = {}
        for field, index, text in texts:
            first = seen.setdefault(text.strip(), (field, index))
            if first != (field, index) and (field == "sections" or first[0] == "messages"):
                self.warn("brief_duplicate", f"brief.json/{field}/{index}",
                          f"duplicates brief.json/{first[0]}/{first[1]}; every pack carries both")
        sections = p.plan.get("sections") if isinstance(p.plan, dict) else None
        plan_texts = [("plan.json", "sections", i, e) for i, e in enumerate(sections if isinstance(sections, list) else [])
                      if isinstance(e, dict)]
        heavy_bytes = settings.for_plan(p).get("check.heavy_text_kb") * 1024
        for where, field, index, entry in [("brief.json", f, i, {"text": t}) for f, i, t in texts] + plan_texts:
            text = entry.get("text")
            size = len(text.encode("utf-8")) if isinstance(text, str) else 0
            if size > heavy_bytes:
                self.warn("context_heavy", f"{where}/{field}/{index}",
                          f"{max(1, size // 1024)} KB enters every context pack; move phase-specific records to "
                          "knowledge/<id>.json with applies_to")
        for where, field, index, entry in plan_texts:
            if any(isinstance(entry.get(k), str) and entry[k].lower().startswith("legacy-") for k in ("id", "title")):
                self.warn("context_legacy", f"{where}/{field}/{index}",
                          "legacy projection enters every context pack; move what is still current to knowledge, "
                          "drop the rest")

    def exists(self, path: str) -> bool:
        base = self.p.root if path.startswith("@plan/") else self.p.repo_root
        return (base / path.removeprefix("@plan/")).exists()

    def produced_paths(self, item_id: str) -> set[str]:
        """Output artifacts of the dependencies (transitively) of ``item_id``."""
        produced: set[str] = set()
        seen: set[str] = set()
        stack = list(self.p.items[item_id].get("depends_on", [])) if isinstance(self.p.items[item_id].get("depends_on"), list) else []
        while stack:
            dep = stack.pop()
            if dep in seen or dep not in self.p.items:
                continue
            seen.add(dep)
            doc = self.p.items[dep]
            for artifact in doc.get("artifacts", []) if isinstance(doc.get("artifacts"), list) else []:
                if isinstance(artifact, dict) and artifact.get("role") == "output" and isinstance(artifact.get("path"), str):
                    produced.add(artifact["path"])
            for hint in doc.get("task_files", []) if isinstance(doc.get("task_files"), list) else []:
                if isinstance(hint, dict) and isinstance(hint.get("path"), str):
                    produced.add(hint["path"])
            if isinstance(doc.get("depends_on"), list):
                stack.extend(doc["depends_on"])
        return produced


def _files(unit: dict) -> list[str]:
    return [f for f in unit.get("files", []) if isinstance(f, str)] if isinstance(unit.get("files"), list) else []


def globs_overlap(a: str, b: str) -> bool:
    """Conservative overlap of two path globs: every shared leading segment must be able to match.

    A directory prefix such as ``lib/x`` overlaps ``lib/x/y.py`` — parallel units must not share either.
    """
    for left, right in zip(a.split("/"), b.split("/")):
        if not (left == right or fnmatchcase(left, right) or fnmatchcase(right, left)):
            return False
    return True


def _strings(value: Any) -> list[str]:
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def _path_fields(kind: str, doc: dict) -> Iterator[tuple[str, str]]:
    """``(pointer, path)`` for every path-typed field of a document."""
    def listed(pointer: str, value: Any, key: str | None = None) -> Iterator[tuple[str, str]]:
        for index, entry in enumerate(value if isinstance(value, list) else []):
            target = entry.get(key) if key and isinstance(entry, dict) else entry
            if isinstance(target, str):
                yield (f"{pointer}/{index}/{key}" if key else f"{pointer}/{index}"), target

    def checks(pointer: str, value: Any) -> Iterator[tuple[str, str]]:
        for index, entry in enumerate(value if isinstance(value, list) else []):
            if isinstance(entry, dict) and isinstance(entry.get("cwd"), str):
                yield f"{pointer}/{index}/cwd", entry["cwd"]

    if kind == "phase":
        yield from listed("/supporting", doc.get("supporting"))
        yield from checks("/validation", doc.get("validation"))
    elif kind == "item":
        for field in ("reads", "task_files", "artifacts", "examples"):
            yield from listed(f"/{field}", doc.get(field), "path")
        yield from checks("/validation", doc.get("validation"))
        rag = doc.get("rag")
        if isinstance(rag, dict):
            yield from listed("/rag/captures", rag.get("captures"))
    elif kind == "unit":
        yield from listed("/files", doc.get("files"))
        yield from listed("/outputs", doc.get("outputs"))
        yield from listed("/reads", doc.get("reads"), "path")
        yield from checks("/checks", doc.get("checks"))
        outcome = doc.get("outcome")
        if isinstance(outcome, dict):
            yield from listed("/outcome/changed", outcome.get("changed"))
        command = doc.get("command")
        if isinstance(command, dict) and isinstance(command.get("cwd"), str):
            yield "/command/cwd", command["cwd"]
