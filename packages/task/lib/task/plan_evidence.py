"""Derived spec → product → closure evidence topology for layout-v2 plans.

The module deliberately has no journal or projection writes.  Callers first compile
the graph from committed carriers, then use its small admission/closure functions at
their respective lifecycle boundaries.  This prevents a plan from trying to prove a
fresh bundle with bytes it is about to change.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

from task import plan_bundle, plan_layout, plan_weight


SCHEMA_VERSION = "evidence-graph/v1"
AUDIT_FINALIZATION_VERSION = "audit-finalization/v1"
_BACKTICK_PATH = re.compile(r"`([^`]+)`")


class EvidenceError(ValueError):
    """A graph cannot prove safe execution or closure."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _declared_paths(value: str, *, allow_prose: bool = False) -> tuple[str, ...]:
    matches = list(_BACKTICK_PATH.finditer(value or ""))
    paths = [match.group(1) for match in matches]
    quoted = bool(paths)
    annotations = set()
    for index, match in enumerate(matches):
        prefix = _BACKTICK_PATH.sub("", value[:match.start()])
        if prefix.count("(") > prefix.count(")"):
            annotations.add(index)
    if not paths and value and value.strip() != "—":
        paths = [part.strip() for entry in plan_weight.split_semicolon_entries(value)
                 for part in re.split(r"\s*[·,]\s*", entry) if part.strip()]
    normalized = []
    for index, path in enumerate(paths):
        if (allow_prose or index in annotations) and re.fullmatch(
                r"[A-Za-z_]\w*(?:\\+[A-Za-z_]\w*)+(?:\\+)?", path):
            # Deliverables and parenthetical file annotations can name PHP namespaces.
            # These identifiers are prose, never repository path declarations.
            continue
        if allow_prose and not quoted and any(char.isspace() for char in path):
            continue
        candidate = PurePosixPath(path)
        if (not path or candidate.is_absolute() or ".." in candidate.parts
                or "\\" in path or path.startswith("./")
                or (not quoted and any(char.isspace() for char in path))):
            raise EvidenceError("EVIDENCE_PATH_INVALID", f"некорректный declared path {path!r}; "
                                "обрамите каждый путь backticks, пояснения вынесите за них")
        normalized.append(candidate.as_posix())
    return tuple(sorted(set(normalized)))


def _repository_path(path: str, *, plan_dir: Path, repo_root: Path) -> str:
    """Return one repository-relative identity for a plan or repository input."""
    raw = PurePosixPath(path)
    candidates = (plan_dir / raw, repo_root / raw)
    for candidate in candidates:
        try:
            relative = candidate.resolve().relative_to(repo_root.resolve())
        except ValueError:
            continue
        # Both roots are syntactically inside the repository.  Selecting the plan
        # root just because it can be normalised would turn every repository
        # source (for example ``packages/task/...``) into a missing plan-local
        # path.  Resolve the same way Bundle does: a real plan-local carrier wins,
        # otherwise an existing repository path wins.  A new declared output is
        # repository-owned by default; plan-local new files are represented by an
        # explicit plan carrier and therefore already exist when compiled.
        if candidate.exists() or candidate.is_symlink():
            return relative.as_posix()
    try:
        return (repo_root / raw).resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        pass
    raise EvidenceError("EVIDENCE_PATH_INVALID", f"path leaves repository: {path}")


def _bundle_inputs(bundle: dict, *, plan_dir: Path, repo_root: Path) -> tuple[str, ...]:
    entries = bundle.get("entries")
    if not isinstance(entries, list):
        raise EvidenceError("EVIDENCE_BUNDLE_INVALID", "bundle entries отсутствуют")
    paths = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise EvidenceError("EVIDENCE_BUNDLE_INVALID", "bundle entry не содержит path")
        paths.append(_repository_path(entry["path"], plan_dir=plan_dir, repo_root=repo_root))
    return tuple(sorted(set(paths)))


def _anchor(paths: tuple[str, ...], *, repo_root: Path) -> dict:
    members = []
    for path in paths:
        target = repo_root / path
        if target.is_symlink():
            members.append({"path": path, "state": "symlink", "target": str(target.readlink())})
        elif target.is_file():
            members.append({"path": path, "state": "file", "sha256": _sha(target.read_bytes())})
        else:
            members.append({"path": path, "state": "missing"})
    return {"paths": members, "sha256": _sha(_canonical(members))}


def verify_execution_inputs_ancestor(plan_dir, item_id: str, execution_ref: str) -> tuple[dict, ...]:
    """Prove committed spec and digest inputs existed before product execution."""
    plan_dir = Path(plan_dir).resolve()
    repo_root = plan_weight.repo_root_for(plan_dir)
    spec = plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
    bundle = plan_bundle.model(plan_dir, item_id)
    paths = {spec.relative_to(repo_root).as_posix(),
             plan_layout.carrier_path(plan_dir, "bundle", item_id=item_id).relative_to(repo_root).as_posix(),
             *_bundle_inputs(bundle, plan_dir=plan_dir, repo_root=repo_root)}
    result = []
    for path in sorted(paths):
        source = subprocess.run(("git", "log", "-1", "--format=%H", "HEAD", "--", path),
                                cwd=repo_root, text=True, capture_output=True, check=False)
        commit = source.stdout.strip()
        if source.returncode or not commit:
            raise EvidenceError("EXECUTION_INPUTS_NOT_ANCESTOR", f"нет committed input {path}")
        ancestor = subprocess.run(("git", "merge-base", "--is-ancestor", commit, execution_ref),
                                  cwd=repo_root, capture_output=True, check=False)
        if ancestor.returncode:
            raise EvidenceError(
                "EXECUTION_INPUTS_NOT_ANCESTOR",
                f"{path}@{commit[:12]} не предшествует execution anchor {execution_ref}",
            )
        result.append({"path": path, "commit": commit})
    return tuple(result)


def _carrier_pattern(pattern: str) -> re.Pattern:
    """Translate the registry's closed path template grammar, not shell globs."""
    escaped = re.escape(pattern)
    escaped = escaped.replace(re.escape("<Pn.m>"), r"P[0-9]+\\.[0-9]+")
    escaped = escaped.replace(re.escape("<Pn>"), r"P[0-9]+")
    escaped = escaped.replace(re.escape("<D-id>"), r"D[0-9]+-[^/]+")
    escaped = escaped.replace(re.escape("{current,archive,index}"), r"(?:current|archive|index)")
    escaped = escaped.replace(re.escape("**"), r".*")
    return re.compile(r"^" + escaped + r"$")


def material_product_paths(plan_dir, item_id: str) -> tuple[str, ...]:
    """Exclude audit-owned volatile carriers unless the item declares them as output.

    Ownership comes solely from the layout registry.  A path named in Deliverables is
    intentionally retained: that is the item's explicit declaration that an otherwise
    plan-owned carrier has product semantics for this contract.
    """
    plan_dir = Path(plan_dir).resolve()
    fields = plan_bundle._fields(plan_dir, item_id)
    deliverables = set(_declared_paths(fields.get("Deliverables", ""), allow_prose=True))
    volatile = [
        _carrier_pattern(row["path"])
        for row in plan_layout.registry().values()
        if row.get("mutability") in {"generated-file", "append-only"}
        and row.get("volatility") == "volatile"
    ]
    paths = []
    for raw in _declared_paths(fields.get("Files", "")):
        if any(pattern.fullmatch(raw) for pattern in volatile) and raw not in deliverables:
            continue
        paths.append(raw)
    return tuple(sorted(set(paths)))


def compile_graph(plan_dir, item_id: str, *, execution_ref: str | None = None,
                  bundle: dict | None = None, readiness=None) -> dict:
    """Compile one deterministic graph using only declared plan carriers.

    Bundle entries include Inputs, Required Reads and resolved decisions, which keeps
    this graph from maintaining a second handwritten dependency map.
    """
    plan_dir = Path(plan_dir).resolve()
    if plan_layout.layout_version(plan_dir) != "v2":
        raise EvidenceError("PLAN_LAYOUT_V1_RETIRED", "evidence graph требует Layout v2")
    try:
        spec_path = plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)
    except plan_layout.PlanLayoutError as exc:
        raise EvidenceError("EVIDENCE_ITEM_MISSING", str(exc)) from exc
    repo_root = plan_weight.repo_root_for(plan_dir)
    product_paths = tuple(sorted({_repository_path(path, plan_dir=plan_dir, repo_root=repo_root)
                                  for path in material_product_paths(plan_dir, item_id)}))
    bundle = bundle if bundle is not None else plan_bundle.model(plan_dir, item_id)
    inputs = _bundle_inputs(bundle, plan_dir=plan_dir, repo_root=repo_root)
    collisions = sorted(set(product_paths) & set(inputs))
    readiness = (plan_bundle.producer_readiness(plan_dir, item_id)
                 if readiness is None else tuple(readiness))
    nodes = [
        {"id": "spec", "kind": "item-spec", "path": spec_path.relative_to(plan_dir).as_posix(),
         "sha256": _sha(spec_path.read_bytes())},
        {"id": "bundle", "kind": "bundle", "sha256": bundle["manifest_sha256"],
         "declaration_sha256": bundle["declaration"]["sha256"]},
        {"id": "product", "kind": "declared-files", "anchor": _anchor(product_paths, repo_root=repo_root)},
        {"id": "closure", "kind": "closure-projections", "paths": []},
    ]
    edges = ([{"from": "spec", "to": "product", "kind": "precedes"},
              {"from": "bundle", "to": "product", "kind": "digest-input"},
              {"from": "product", "to": "closure", "kind": "byte-identity"}]
             + [{"from": "bundle", "to": f"producer:{row['producer_item']}",
                 "kind": "producer-readiness", "digest": row["digest"]}
                for row in readiness])
    graph = {
        "schema_version": SCHEMA_VERSION,
        "item_id": item_id,
        "product_paths": list(product_paths),
        "digest_inputs": list(inputs),
        "collisions": collisions,
        "nodes": nodes,
        "edges": edges,
    }
    if execution_ref is not None:
        graph["input_ancestors"] = list(
            verify_execution_inputs_ancestor(plan_dir, item_id, execution_ref))
    graph["sha256"] = _sha(_canonical(graph))
    return graph


def admit_pre_mutation(graph: dict, *, requires_closure_freshness: bool) -> dict:
    """Refuse the real input/write collision before journal or product mutation."""
    if graph.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError("EVIDENCE_GRAPH_INVALID", "неподдерживаемая версия graph")
    collisions = graph.get("collisions")
    if not isinstance(collisions, list):
        raise EvidenceError("EVIDENCE_GRAPH_INVALID", "graph collisions отсутствуют")
    if collisions and requires_closure_freshness:
        raise EvidenceError(
            "SELF_INVALIDATING_EVIDENCE_ANCHOR",
            "Files пересекается с digest inputs: " + ", ".join(collisions)
            + "; выполните product/closure split",
        )
    return {"admission": "allow", "anchor_mode": "split" if collisions else "collapsed",
            "graph_sha256": graph["sha256"]}


def verify_closure(product_anchor: dict, closure_anchor: dict) -> dict:
    """Prove that closure bookkeeping did not alter product bytes."""
    for anchor in (product_anchor, closure_anchor):
        if not isinstance(anchor, dict) or not isinstance(anchor.get("paths"), list):
            raise EvidenceError("EVIDENCE_ANCHOR_INVALID", "anchor.paths обязателен")
        rows = anchor["paths"]
        if not rows or not any(isinstance(row, dict) and row.get("state") == "file"
                               and re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", "")))
                               for row in rows):
            raise EvidenceError("PRODUCT_COVERAGE_MISSING",
                                "anchor не связывает байты ни одного реального product file")
        if (any(not isinstance(row, dict) or not isinstance(row.get("path"), str)
                or not row["path"] for row in rows)
                or len({row["path"] for row in rows}) != len(rows)):
            raise EvidenceError("EVIDENCE_ANCHOR_INVALID", "anchor.paths содержит неверные/повторные пути")
    product = {row.get("path"): row for row in product_anchor["paths"]}
    closure = {row.get("path"): row for row in closure_anchor["paths"]}
    if product != closure:
        raise EvidenceError("PRODUCT_ANCHOR_DRIFT", "product paths изменились между product и closure anchor")
    return {"schema_version": "closure-byte-identity/v1", "status": "green",
            "product_anchor_sha256": product_anchor.get("sha256"),
            "closure_anchor_sha256": closure_anchor.get("sha256")}


def affected_closure(graph: dict, changed_paths) -> tuple[str, ...]:
    """Return the bounded graph nodes impacted by declared path changes."""
    changed = set(changed_paths)
    affected = {"product"} if changed & set(graph.get("product_paths", ())) else set()
    if affected:
        affected.add("closure")
    return tuple(sorted(affected))


def audit_finalization(*, before_candidate: dict, after_candidate: dict,
                       lifecycle_selection: dict, close_admission: str) -> dict:
    """Persistable proof that the regenerated candidate can take its exact close path."""
    if close_admission != "allow":
        raise EvidenceError("AUDIT_FINALIZATION_REFUSED", f"close admission is {close_admission}")
    if not isinstance(lifecycle_selection, dict):
        raise EvidenceError("AUDIT_FINALIZATION_INVALID", "lifecycle selection обязателен")
    return {
        "schema_version": AUDIT_FINALIZATION_VERSION,
        "before_fingerprint": before_candidate.get("fingerprint"),
        "after_fingerprint": after_candidate.get("fingerprint"),
        "lifecycle_selection": lifecycle_selection,
        "close_admission": close_admission,
    }
