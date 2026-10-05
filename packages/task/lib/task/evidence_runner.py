"""Candidate-bound validation DAG with exclusive, immutable attempt outputs."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import time
from pathlib import Path
import re
import subprocess

from task import review_packet, file_manifest


def _digest(value):
    return hashlib.sha256(review_packet._json(value)).hexdigest()


def run(root, directory, *, paths, checks: list[dict], attempt_id: str) -> dict:
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if not directory.is_relative_to(root) or directory == root:
        raise ValueError("EVIDENCE_OUTPUT_INVALID: output must be repository-local")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", attempt_id):
        raise ValueError("EVIDENCE_ATTEMPT_INVALID")
    def members():
        concrete = file_manifest.expand(root, paths, base="HEAD", required=True)
        if any((root / path).resolve().is_relative_to(directory)
               or directory.is_relative_to((root / path).resolve()) for path in concrete):
            raise ValueError("EVIDENCE_CANDIDATE_INVALID: validation output overlaps candidate")
        return review_packet._members(root, concrete)
    if not paths:
        raise ValueError("EVIDENCE_CANDIDATE_INVALID: declare product paths, excluding outputs")
    nodes = {}
    for check in checks:
        if (not isinstance(check, dict) or not {"id", "argv", "depends_on"}.issubset(check)
                or set(check) - {"id", "argv", "depends_on", "env", "timeout"}
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(check.get("id", "")))
                or not isinstance(check["argv"], list) or not check["argv"]
                or any(not isinstance(value, str) or not value for value in check["argv"])
                or not isinstance(check["depends_on"], list)
                or any(not isinstance(value, str) for value in check["depends_on"])
                or not isinstance(check.get("env", {}), dict)
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in check.get("env", {}).items())
                or ("timeout" in check and (type(check["timeout"]) not in {int, float} or check["timeout"] <= 0))
                or check["id"] in nodes):
            raise ValueError("EVIDENCE_DAG_INVALID")
        nodes[check["id"]] = check
    ordered, active = [], set()
    def visit(name):
        if name not in nodes or name in active:
            raise ValueError("EVIDENCE_DAG_INVALID: unknown dependency or cycle")
        if name in ordered:
            return
        active.add(name)
        for dependency in nodes[name]["depends_on"]:
            visit(dependency)
        active.remove(name)
        ordered.append(name)
    for name in nodes:
        visit(name)
    if not ordered:
        raise ValueError("EVIDENCE_DAG_INVALID: empty checks")
    candidate = members()
    if not candidate or not any(row.get("sha256") != "directory" for row in candidate):
        raise ValueError("EVIDENCE_CANDIDATE_INVALID: candidate has no product members")
    digest = _digest(candidate)
    attempt = directory / digest / attempt_id
    attempt.mkdir(parents=True, exist_ok=True)
    with (attempt / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("EVIDENCE_WRITER_BUSY: attempt has an active writer") from exc
        receipt_path = attempt / "receipt.json"
        if receipt_path.exists() or (attempt / "started.json").exists():
            raise ValueError("EVIDENCE_ATTEMPT_EXISTS: use a new attempt, preserve original outputs")
        request = {"schema_version": "validation-attempt/v1", "candidate_sha256": digest,
                   "candidate": candidate, "checks": checks, "attempt_id": attempt_id}
        (attempt / "started.json").write_bytes(review_packet._json(request))
        rows = {}
        failed = False
        for name in ordered:
            node = nodes[name]
            if any(rows[dependency]["exit_code"] != 0 for dependency in node["depends_on"]):
                rows[name] = {"exit_code": None, "status": "dependency-failed"}
                continue
            if failed:
                rows[name] = {"exit_code": None, "status": "stopped-after-red"}
                continue
            if members() != candidate:
                rows[name] = {"exit_code": None, "status": "candidate-changed"}
                failed = True
                continue
            with (attempt / (name + ".log")).open("xb") as output:
                try:
                    environment = {**os.environ, "COMPOSER_PROCESS_TIMEOUT": "0", **node.get("env", {})}
                    started = time.monotonic()
                    process = subprocess.Popen(node["argv"], cwd=root, stdout=output,
                        stderr=subprocess.STDOUT, env=environment, start_new_session=True)
                    try:
                        exit_code = process.wait(timeout=node.get("timeout"))
                        status = "green" if exit_code == 0 else "red"
                    except (subprocess.TimeoutExpired, KeyboardInterrupt, SystemExit) as exc:
                        def stop_group(sig):
                            try:
                                os.killpg(process.pid, sig)
                            except ProcessLookupError:
                                pass
                        stop_group(signal.SIGTERM)
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            stop_group(signal.SIGKILL)
                            process.wait()
                        else:
                            stop_group(signal.SIGKILL)
                        if not isinstance(exc, subprocess.TimeoutExpired):
                            raise
                        exit_code, status = process.returncode, "timeout"
                    rows[name] = {"exit_code": exit_code, "status": status,
                                  "wall_seconds": round(time.monotonic() - started, 3)}
                except OSError as exc:
                    rows[name] = {"exit_code": None, "status": "launch-failed", "detail": str(exc)}
            failed = rows[name]["exit_code"] != 0 or rows[name]["status"] != "green"
        fresh = members() == candidate
        receipt = {**request, "results": rows, "candidate_fresh": fresh,
                   "complete": fresh and all(row["exit_code"] == 0 and row["status"] == "green"
                                             for row in rows.values())}
        receipt_path.write_bytes(review_packet._json(receipt))
        return {"complete": receipt["complete"], "candidate_sha256": digest,
                "attempt_id": attempt_id, "receipt": str(receipt_path), "results": rows}
