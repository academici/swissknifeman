"""Pinned S1/S2/S3 slice-manifest compiler; package readers stay process-bound."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


MAX_OUTPUT_BYTES = 1_000_000
PROCESS_TIMEOUT_SECONDS = 30
SOURCE_KEYS = ("repository_root", "base_commit", "plan", "phase", "item", "log", "execution_policy")
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


def observe_sources(repo_root: str | Path, plan_dir: str | Path, item_id: str) -> tuple[dict, dict]:
    """Observe the item JSON through ``plan.py show`` and the harness queue; nothing reads plan files directly."""
    root, plan = Path(repo_root).resolve(), Path(plan_dir).resolve()
    if not _contained(root, plan):
        raise CompileRefusal("SLICE_INPUT_EXTERNAL", str(plan))
    item = _run_json(["python3", "packages/task/scripts/plan.py", "show", str(plan), item_id, "--json"],
                     cwd=root, env=_minimal_env())
    queue = _run_json([str(root / "packages/harness/bin/harness"), "run", plan.name, item_id.split(".", 1)[0], "--dry-run", "--json"],
                      cwd=root, env=_minimal_env())
    return item, queue


def _item(item: dict, item_id: str) -> tuple[str, dict]:
    """Return the phase id and the item JSON, refusing a skeleton item."""
    if not isinstance(item, dict) or item.get("id") != item_id:
        raise CompileRefusal("SKELETON_ITEM", item_id)
    rows = ("task_files", "reads", "validation", "deliverables")
    if (not isinstance(item.get("status"), str) or not item["status"]
            or not all(isinstance(item.get(key), list) and item[key] for key in rows)
            or not isinstance(item.get("route"), dict)):
        raise CompileRefusal("SKELETON_ITEM", item_id)
    return item_id.split(".", 1)[0], item


def _paths(rows: list, *, label: str) -> list[str]:
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    if not paths or any(not isinstance(path, str) or not path for path in paths) or len(paths) != len(set(paths)):
        raise CompileRefusal("SLICE_INPUT_MISSING", label)
    return paths


def _scope(root: Path, item: dict) -> tuple[dict, list[str]]:
    reads = [row for row in item["reads"] if isinstance(row, dict) and row.get("required") is True]
    required_reads = _paths(reads, label="Required Reads")
    files = _paths(item["task_files"], label="Files")
    checks = [row for row in item["validation"] if isinstance(row, dict)]
    ids = [row.get("id") for row in checks]
    validation = [row.get("cmd") for row in checks]
    deliverables = [text for text in item["deliverables"] if isinstance(text, str) and text.strip()]
    if (not checks or not all(isinstance(value, str) and value for value in ids + validation)
            or len(ids) != len(set(ids)) or len(deliverables) != len(item["deliverables"])):
        raise CompileRefusal("SLICE_INPUT_MISSING", "validation/deliverables")
    for relative in required_reads:
        _safe_existing(root, relative)
    for relative in files:
        _safe_output(root, relative)
    return {"required_reads": required_reads, "files": files, "validation": validation,
            "deliverables": deliverables, "evidence_refs": ids}, files


def _source_hashes(root: Path, plan: Path, phase: str, item: dict) -> dict[str, str]:
    try:
        base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, shell=False, check=True,
                                    capture_output=True, text=True, env=_minimal_env()).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CompileRefusal("SOURCE_UNAVAILABLE", "git rev-parse HEAD") from exc
    policy = root / "packages/harness/configs/common/agent-packs/execution-policy.json"
    return {
        "repository_root": sha256_bytes(str(root).encode()), "base_commit": sha256_bytes(base_commit.encode()),
        "plan": sha256_bytes((plan / "plan.json").read_bytes()),
        "phase": sha256_bytes((plan / "phases" / phase / "phase.json").read_bytes()),
        "item": sha256_bytes(canonical_bytes(item)), "log": sha256_bytes((plan / "log.jsonl").read_bytes()),
        "execution_policy": sha256_bytes(policy.read_bytes()),
    }


def compile_slice(repo_root: str | Path, plan_dir: str | Path, item_id: str, *, revision: int = 1,
                  supersedes: str | None = None, sources: tuple[dict, dict] | None = None) -> dict:
    root, plan = Path(repo_root).resolve(), Path(plan_dir).resolve()
    item_json, queue = sources or observe_sources(root, plan, item_id)
    phase, item = _item(item_json, item_id)
    route = {"model_class": item["route"].get("class"), "effort": item["route"].get("effort")}
    if route["model_class"] not in ("economy", "implementation", "frontier") or route["effort"] not in ("low", "medium", "high", "xhigh", "max"):
        raise CompileRefusal("ROUTE_UNRESOLVED", item_id)
    matching = [row for row in queue.get("items", []) if isinstance(row, dict) and row.get("item_id") == item_id]
    if queue.get("degraded") is not False or len(matching) != 1:
        raise CompileRefusal("SOURCE_UNAVAILABLE", "S3 queue")
    queued = matching[0]
    if queued.get("status") != item["status"] or queued.get("route") != route:
        raise CompileRefusal("SOURCE_DRIFT", "item/queue status or route")
    exec_value = queued.get("exec")
    if exec_value != "run":
        raise CompileRefusal("ROUTE_EXEC_MISMATCH", str(exec_value))
    scope, _ = _scope(root, item)
    contract_hash = sha256_bytes(canonical_bytes(item))
    source_hashes = _source_hashes(root, plan, phase, item)
    manifest = {
        "schema_version": "slice-manifest-v1", "manifest_version": "1.0.0",
        "slice_id": f"{plan.name}:{item_id}:r{revision}", "plan_id": plan.name, "item_id": item_id,
        "revision": revision, "content_hash": "", "supersedes": supersedes, "lifecycle": "pending",
        "source_hashes": source_hashes,
        "task_contract": {"schema_version": item.get("$schema"), "content_hash": contract_hash,
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
    if _source_hashes(root, plan, phase, item) != source_hashes:
        raise CompileRefusal("SOURCE_DRIFT")
    return manifest
