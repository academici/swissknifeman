"""Pinned S1/S2/S3 slice-manifest compiler; package readers stay process-bound."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


MAX_OUTPUT_BYTES = 1_000_000
PROCESS_TIMEOUT_SECONDS = 30
SOURCE_KEYS = ("repository_root", "base_commit", "plan", "phase", "item", "handoff",
               "task_contract", "execution_policy")
OPERATIONS = ("compile_slice", "supersede_pending", "dispatch_worker", "validate_result",
              "integrate_owned_delta", "project_plan_bookkeeping")


class CompileRefusal(ValueError):
    """A closed slice-manifest refusal, or a fail-loud source observation error."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_existing(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or not _contained(root, path) or not path.exists() or path.is_symlink() or not path.is_file():
        raise CompileRefusal("SLICE_INPUT_EXTERNAL", relative)
    return path


def _safe_output(root: Path, relative: str) -> None:
    path = root / relative
    if Path(relative).is_absolute() or not _contained(root, path):
        raise CompileRefusal("SLICE_INPUT_EXTERNAL", relative)
    probe = path if path.exists() else path.parent
    while not probe.exists() and probe != root:
        probe = probe.parent
    if not _contained(root, probe) or probe.is_symlink() or (path.exists() and path.is_symlink()):
        raise CompileRefusal("SLICE_INPUT_EXTERNAL", relative)


def _minimal_env(extra_pythonpath: str | None = None) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8"}
    if extra_pythonpath:
        env["PYTHONPATH"] = extra_pythonpath
    return env


def _run_json(argv: list[str], *, cwd: Path, env: dict[str, str]) -> dict:
    try:
        completed = subprocess.run(argv, cwd=cwd, env=env, shell=False, timeout=PROCESS_TIMEOUT_SECONDS,
                                   capture_output=True, check=False)
    except subprocess.TimeoutExpired as exc:
        raise CompileRefusal("SOURCE_UNAVAILABLE", f"timeout: {argv[0]}") from exc
    if len(completed.stdout) > MAX_OUTPUT_BYTES or len(completed.stderr) > MAX_OUTPUT_BYTES:
        raise CompileRefusal("SOURCE_UNAVAILABLE", f"oversized output: {argv[0]}")
    if completed.returncode:
        raise CompileRefusal("SOURCE_UNAVAILABLE", f"exit {completed.returncode}: {argv[0]}")
    try:
        result = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompileRefusal("SOURCE_UNAVAILABLE", f"invalid JSON: {argv[0]}") from exc
    if not isinstance(result, dict):
        raise CompileRefusal("SOURCE_UNAVAILABLE", f"JSON object required: {argv[0]}")
    return result


def observe_sources(repo_root: str | Path, plan_dir: str | Path, item_id: str) -> tuple[dict, dict, dict]:
    root, plan = Path(repo_root).resolve(), Path(plan_dir).resolve()
    if not _contained(root, plan):
        raise CompileRefusal("SLICE_INPUT_EXTERNAL", str(plan))
    s1 = _run_json(["python3", "packages/task/scripts/plan-lint.py", str(plan), "--json"],
                   cwd=root, env=_minimal_env())
    s2 = _run_json(["python3", "-m", "task.task_contract", "build", "--plan-dir", str(plan), "--item", item_id],
                   cwd=root, env=_minimal_env(str(root / "packages/task/lib")))
    s3 = _run_json([str(root / "packages/harness/bin/harness"), "run", plan.name, item_id.split(".", 1)[0], "--dry-run", "--json"],
                   cwd=root, env=_minimal_env())
    return s1, s2, s3


def _item(s1: dict, plan_id: str, item_id: str) -> tuple[str, dict]:
    try:
        phase = item_id.split(".", 1)[0]
        item = s1["plans"][plan_id]["phases"][phase]["items"][item_id]
        fields = item["fields"]
    except (KeyError, TypeError) as exc:
        raise CompileRefusal("SKELETON_ITEM", item_id) from exc
    required = ("Status", "Files", "Required Reads", "Validation", "Deliverables")
    if not all(isinstance(fields.get(key), str) and fields[key].strip() not in ("", "—") for key in required):
        raise CompileRefusal("SKELETON_ITEM", item_id)
    return phase, {"title": item.get("title"), "fields": fields}


def _tokens(value: str, *, label: str) -> list[str]:
    import re
    tokens = re.findall(r"`([^`]+)`", value)
    residue = re.sub(r"`[^`]+`", "", value).replace("·", "").strip()
    if not tokens or residue or len(tokens) != len(set(tokens)):
        raise CompileRefusal("SLICE_INPUT_MISSING", label)
    return tokens


def _required_read_tokens(value: str) -> list[str]:
    import re
    tokens = re.findall(r"`([^`]+)`", value)
    residue = re.sub(r"`[^`]+`", "", value)
    residue = re.sub(r"\b[1-9][0-9]*\)\s*", "", residue).strip().rstrip(".").strip()
    if not tokens or residue or len(tokens) != len(set(tokens)):
        raise CompileRefusal("SLICE_INPUT_MISSING", "Required Reads")
    return tokens


def _evidence_paths(s2: dict) -> dict[str, str]:
    rows = s2.get("evidence")
    if not isinstance(rows, list):
        raise CompileRefusal("SLICE_INPUT_MISSING", "Task Contract evidence")
    return {row["id"]: row["path"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("path"), str)}


def _scope(root: Path, item: dict, s2: dict) -> tuple[dict, list[str]]:
    fields, evidence = item["fields"], _evidence_paths(s2)
    reads = s2.get("cold_start", {}).get("reads", [])
    acceptance = s2.get("done", {}).get("public_acceptance", [])
    if not isinstance(reads, list) or not isinstance(acceptance, list) or not reads or not acceptance:
        raise CompileRefusal("SLICE_INPUT_MISSING", "Task Contract reads/acceptance")
    required_reads = [evidence.get(ref) for ref in reads]
    if any(not path for path in required_reads) or len(required_reads) != len(set(required_reads)):
        raise CompileRefusal("SLICE_INPUT_MISSING", "Task Contract cold reads")
    s1_reads = _required_read_tokens(fields["Required Reads"])
    if required_reads != s1_reads:
        raise CompileRefusal("SLICE_INPUT_MISSING", "S1/S2 required reads drift")
    validation = [row.get("check", "") for row in acceptance if isinstance(row, dict)]
    ids = [row.get("id", "") for row in acceptance if isinstance(row, dict)]
    predicates = [row.get("predicate", "") for row in acceptance if isinstance(row, dict)]
    if not all(isinstance(value, str) and value for value in validation + ids + predicates) or len(ids) != len(set(ids)):
        raise CompileRefusal("SLICE_INPUT_MISSING", "Task Contract public acceptance")
    s1_validation = fields["Validation"].split(" · ")
    if validation != s1_validation or any(predicate != fields["Deliverables"] for predicate in predicates):
        raise CompileRefusal("SLICE_INPUT_MISSING", "S1/S2 acceptance drift")
    files = _tokens(fields["Files"], label="Files")
    for relative in required_reads:
        _safe_existing(root, relative)
    for relative in files:
        _safe_output(root, relative)
    return {"required_reads": required_reads, "files": files, "validation": validation,
            "deliverables": [fields["Deliverables"]], "evidence_refs": ids}, files


def _source_hashes(root: Path, plan: Path, phase: str, item: dict, s2: dict) -> dict[str, str]:
    try:
        base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, shell=False, check=True,
                                    capture_output=True, text=True, env=_minimal_env()).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CompileRefusal("SOURCE_UNAVAILABLE", "git rev-parse HEAD") from exc
    policy = root / "packages/harness/configs/common/agent-packs/execution-policy.json"
    return {
        "repository_root": sha256_bytes(str(root).encode()), "base_commit": sha256_bytes(base_commit.encode()),
        "plan": sha256_bytes((plan / "plan.md").read_bytes()), "phase": sha256_bytes((plan / "phases" / f"{phase}.md").read_bytes()),
        "item": sha256_bytes(canonical_bytes(item)), "handoff": sha256_bytes((plan / "handoff.md").read_bytes()),
        "task_contract": s2["version"]["content_hash"], "execution_policy": sha256_bytes(policy.read_bytes()),
    }


def compile_slice(repo_root: str | Path, plan_dir: str | Path, item_id: str, *, revision: int = 1,
                  supersedes: str | None = None, sources: tuple[dict, dict, dict] | None = None) -> dict:
    root, plan = Path(repo_root).resolve(), Path(plan_dir).resolve()
    s1, s2, s3 = sources or observe_sources(root, plan, item_id)
    phase, item = _item(s1, plan.name, item_id)
    route = s2.get("route", {}).get("required", {})
    if route.get("model_class") not in ("economy", "implementation", "frontier") or route.get("effort") not in ("low", "medium", "high", "xhigh", "max"):
        raise CompileRefusal("ROUTE_UNRESOLVED", item_id)
    matching = [row for row in s3.get("items", []) if isinstance(row, dict) and row.get("item_id") == item_id]
    if s3.get("degraded") is not False or len(matching) != 1:
        raise CompileRefusal("SOURCE_UNAVAILABLE", "S3 queue")
    s3_item = matching[0]
    if s3_item.get("status") != item["fields"]["Status"] or s3_item.get("route") != route:
        raise CompileRefusal("SOURCE_DRIFT", "S1/S3 status or route")
    exec_value = s3_item.get("exec")
    if exec_value != "run":
        raise CompileRefusal("ROUTE_EXEC_MISMATCH", str(exec_value))
    scope, _ = _scope(root, item, s2)
    contract_hash = s2.get("version", {}).get("content_hash")
    if not isinstance(contract_hash, str) or len(contract_hash) != 64:
        raise CompileRefusal("TASK_CONTRACT_HASH_MISMATCH")
    source_hashes = _source_hashes(root, plan, phase, item, s2)
    manifest = {
        "schema_version": "slice-manifest-v1", "manifest_version": "1.0.0",
        "slice_id": f"{plan.name}:{item_id}:r{revision}", "plan_id": plan.name, "item_id": item_id,
        "revision": revision, "content_hash": "", "supersedes": supersedes, "lifecycle": "pending",
        "source_hashes": source_hashes,
        "task_contract": {"schema_version": s2.get("schema_version"), "content_hash": contract_hash,
                          "pre_mutation": "allow", "public_acceptance_ids": scope["evidence_refs"]},
        "run": {"contract_id": "supervisor-run-v1", "contract_version": "1.0.0",
                "contract_hash": "c9b7290dc0d30b7fc1c7c20782cec7b4f327ba6673300bed71cadf172ab88e2a",
                "run_id": f"{plan.name}:{item_id}:r{revision}", "attempt": 1,
                "idempotency_key": sha256_bytes(f"{plan.name}:{item_id}:{revision}".encode())},
        "scope": scope, "dependencies": [],
        "route": {"model_class": route["model_class"], "effort": route["effort"], "exec": exec_value,
                  "capabilities": [{"id": "filesystem-write", "support": "native"}]},
        "references": {"authority_contract_id": "authority-policy-v1", "authority_contract_version": "1.0.0",
                       "authority_contract_hash": "ba1ebc2a373f7cd26922e2b8362848cfc11b4d38c78b1d764883a6df3e245b10",
                       "output_contract_id": "worker-envelope-v1", "output_contract_version": "1.0.0",
                       "output_contract_hash": "8492a73facaf0258e96003f1376da962e144acc1f57b87546f606cb77f4c4785"},
        "budgets": {"max_attempts": 2, "max_auto_fix_attempts": 1, "max_parallel_workers": 1,
                    "timeout_seconds": 900, "token_limit": None, "token_limit_unknown_reason": "provider cap unavailable before dispatch"},
        "execution": {"operations": list(OPERATIONS), "writer_mode": "one-writer",
                      "worktree_mode": "current-or-owned-linked", "integration_mode": "serialized"},
    }
    if revision == 1 and supersedes is not None:
        raise CompileRefusal("REPLAN_SUPERSEDES_REQUIRED")
    manifest["content_hash"] = sha256_bytes(canonical_bytes({key: value for key, value in manifest.items() if key != "content_hash"}))
    # Re-observe the pins immediately before returning a publishable manifest.
    if _source_hashes(root, plan, phase, item, s2) != source_hashes:
        raise CompileRefusal("SOURCE_DRIFT")
    return manifest
