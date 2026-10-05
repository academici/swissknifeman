"""Structural checks of a v3 plan (dossier §4, §2.5, §2.5.1). Never raises on a broken plan.

``check(plan)`` returns every problem as an ``Issue``; unreadable JSON, schema violations, identity and
reference drift, batches, cycles, completeness, result/status consistency and unit rules are errors, a
few advisory findings are warnings. Staleness of the generated views is added by P1.3.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
import re
from typing import Any, Iterator, NamedTuple

from . import schema as _schema
from . import store
from .model import ITEM_ID, parse_ref

_UNIT_ID = re.compile(r"^U[0-9]+$")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_GLOB = re.compile(r"[*?\[]")
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
    ctx.membership()
    ctx.references()
    ctx.cycles()
    ctx.batches()
    ctx.completeness()
    ctx.decisions()
    ctx.paths()
    ctx.results()
    ctx.units()
    ctx.log()
    ctx.advisories()
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

    def known(self, ref: str) -> bool:
        try:
            parsed = parse_ref(ref)
        except ValueError:
            return True  # a malformed ref is a schema error already
        if parsed.plan is not None:
            return True  # qualified foreign refs are syntax-checked only
        table = {"phase": self.p.phases, "item": self.p.items, "decision": self.p.decisions}[parsed.kind]
        return parsed.target in table

    def check_refs(self, where: str, refs: Any) -> None:
        for index, ref in enumerate(refs if isinstance(refs, list) else []):
            if isinstance(ref, str) and not self.known(ref):
                self.error("ref_unknown", f"{where}/{index}", f"unknown reference {ref}")

    def references(self) -> None:
        p = self.p
        for key, doc in p.items.items():
            rel = self.file_of("item", key)
            self.check_refs(f"{rel}/depends_on", doc.get("depends_on"))
            self.check_refs(f"{rel}/decisions", doc.get("decisions"))
            related = doc.get("related")
            for index, link in enumerate(related if isinstance(related, list) else []):
                if isinstance(link, dict) and isinstance(link.get("ref"), str) and not self.known(link["ref"]):
                    self.error("ref_unknown", f"{rel}/related/{index}/ref", f"unknown reference {link['ref']}")
            result = doc.get("result")
            if isinstance(result, dict) and isinstance(result.get("decision"), str) and not self.known(result["decision"]):
                self.error("ref_unknown", f"{rel}/result/decision", f"unknown reference {result['decision']}")
        for key, doc in p.phases.items():
            self.check_refs(f"{self.file_of('phase', key)}/depends_on", doc.get("depends_on"))
        for key, doc in p.decisions.items():
            rel = self.file_of("decision", key)
            self.check_refs(f"{rel}/applies_to", doc.get("applies_to"))
            self.check_refs(f"{rel}/supersedes", doc.get("supersedes"))
            if isinstance(doc.get("superseded_by"), str) and not self.known(doc["superseded_by"]):
                self.error("ref_unknown", f"{rel}/superseded_by", f"unknown reference {doc['superseded_by']}")
        requirements = p.brief.get("requirements")
        for index, requirement in enumerate(requirements if isinstance(requirements, list) else []):
            if isinstance(requirement, dict):
                self.check_refs(f"brief.json/requirements/{index}/owners", requirement.get("owners"))
        for key, doc in p.units.items():
            rel = self.file_of("unit", key)
            siblings = {k.split("/")[1] for k in p.units if k.split("/")[0] == key.split("/")[0]}
            for index, dep in enumerate(doc.get("depends_on") if isinstance(doc.get("depends_on"), list) else []):
                if isinstance(dep, str) and dep not in siblings:
                    self.error("ref_unknown", f"{rel}/depends_on/{index}", f"unknown unit {dep} in {key.split('/')[0]}")
            item = p.items.get(key.split("/")[0])
            declared = {c["id"] for c in (item or {}).get("validation", []) if isinstance(c, dict) and "id" in c}
            for index, entry in enumerate(doc.get("checks") if isinstance(doc.get("checks"), list) else []):
                if isinstance(entry, str) and item is not None and entry not in declared:
                    self.error("ref_unknown", f"{rel}/checks/{index}", f"unknown item check {entry}")

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
        for item_id in p.items:
            keys = [k for k in p.units if k.startswith(f"{item_id}/")]
            ids = {k.split("/")[1] for k in keys}
            unit_graph = {k.split("/")[1]: [d for d in p.units[k].get("depends_on", []) if d in ids]
                          if isinstance(p.units[k].get("depends_on"), list) else [] for k in keys}
            self.report_cycles("unit", unit_graph, "depends_on", prefix=f"{item_id}/")

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

                def missing(field: str, why: str) -> None:
                    self.error("incomplete", f"{rel}/{field}", f"detailed item {item_id} needs {why}")

                for field in ("summary", "why"):
                    if not item.get(field):
                        missing(field, f"a non-empty {field}")
                scope = item.get("scope")
                if not (isinstance(scope, dict) and scope.get("include")):
                    missing("scope/include", "at least one scope.include entry")
                checks = item.get("validation") if isinstance(item.get("validation"), list) else []
                if not any(isinstance(c, dict) and c.get("kind") == "acceptance" for c in checks):
                    missing("validation", "at least one acceptance check")
                if not item.get("deliverables"):
                    missing("deliverables", "at least one deliverable")
                if not (item.get("reads") or item.get("task_files")):
                    missing("reads", "reads or task_files")

    def decisions(self) -> None:
        for key, doc in self.p.decisions.items():
            rel, status = self.file_of("decision", key), doc.get("status")
            needed = {"open": ("question",), "accepted": ("decision", "rationale")}.get(status, ())
            for field in needed:
                if not doc.get(field):
                    self.error("decision_fields", f"{rel}/{field}", f"a {status} decision needs {field}")

    def paths(self) -> None:
        for kind, key, rel, doc in self.docs():
            for pointer, value in _path_fields(kind, doc):
                parts = re.split(r"[\\/]", value)
                if ".." in parts:
                    self.error("path", f"{rel}{pointer}", f"path {value!r} contains a '..' segment")
                elif value.startswith("/") or _DRIVE.match(value) or value.startswith("~"):
                    self.error("path", f"{rel}{pointer}", f"path {value!r} must be relative to the repository or @plan/")

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
        units = {k.split("/")[1]: self.p.units[k] for k in keys}
        deps = {u: set(d for d in doc.get("depends_on", []) if d in units) if isinstance(doc.get("depends_on"), list) else set()
                for u, doc in units.items()}

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
            for index, read in enumerate(item.get("reads", []) if isinstance(item.get("reads"), list) else []):
                if (isinstance(read, dict) and read.get("required") is True and isinstance(read.get("path"), str)
                        and not _GLOB.search(read["path"]) and not self.exists(read["path"])
                        and read["path"] not in produced):
                    self.warn("read_missing", f"{rel}/reads/{index}/path",
                              f"required read {read['path']} does not exist and no dependency produces it")
            for index, hint in enumerate(item.get("task_files", []) if isinstance(item.get("task_files"), list) else []):
                if (isinstance(hint, dict) and hint.get("change") == "modify" and isinstance(hint.get("path"), str)
                        and not _GLOB.search(hint["path"]) and not self.exists(hint["path"])):
                    self.warn("modify_missing", f"{rel}/task_files/{index}/path",
                              f"{hint['path']} is marked modify but does not exist")

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
        yield from listed("/reads", doc.get("reads"), "path")
        yield from checks("/checks", doc.get("checks"))
        outcome = doc.get("outcome")
        if isinstance(outcome, dict):
            yield from listed("/outcome/changed", outcome.get("changed"))
