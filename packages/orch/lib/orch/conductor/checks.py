"""Deterministic acceptance checks of a candidate and their check-evidence files.

Every ``acceptance`` and ``impact`` command check of the execution-input runs as written (``bash -c``, in its
``cwd`` below the project) with the output kept in the ignored runtime folder. Each check gets an ``exec/v1``
check-evidence document in the item's artifact folder (committed), produced by the engine and bound to the candidate
(``HEAD`` and the digest of the dirty tree). A manual procedure cannot run here: its evidence carries the executor's
reported verdict, produced by the executor. ``live`` checks are not run by the conductor.
"""
from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from orch import contracts

RUN_KINDS = ("acceptance", "impact")
TAIL_LINES = 40


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(project: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=str(project), capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip() or done.returncode}")
    return done.stdout


def head(project: Path) -> str:
    return git(project, "rev-parse", "HEAD").strip()


def untracked(project: Path) -> list:
    return [line for line in git(project, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if line]


def dirty_digest(project: Path) -> str:
    """sha256 of the tracked changes against HEAD and of the untracked files (names and contents)."""
    digest = hashlib.sha256(git(project, "diff", "HEAD", "--binary").encode("utf-8", "surrogateescape"))
    for name in sorted(untracked(project)):
        digest.update(b"\0" + name.encode("utf-8"))
        try:
            digest.update(b"\0" + (project / name).read_bytes())
        except OSError:
            digest.update(b"\0?")
    return digest.hexdigest()


def diff(project: Path, base: str, limit: int = 200_000) -> str:
    """The diff of the working tree against ``base``, plus the untracked files; cut at ``limit`` characters."""
    text = git(project, "diff", base)
    extra = untracked(project)
    if extra:
        text += "\n# untracked files:\n" + "\n".join(f"#   {name}" for name in extra) + "\n"
    if len(text) > limit:
        text = text[:limit] + f"\n# … diff cut at {limit} characters; read the files for the rest\n"
    return text


def subject_of(input_doc: dict) -> str:
    """The qualified reference the evidence proves: the input id without its digest suffix."""
    return str(input_doc.get("input_id", "")).rsplit("@", 1)[0]


def _relative(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path)


def run_checks(input_doc: dict, *, project: Path, evidence_dir: Path, log_dir: Path, timeout_s: int,
               evidence_prefix: str, report: dict | None = None, executor: dict | None = None,
               parallel: int = 1, on_result=None) -> list:
    """Run the checks and write their evidence; one row per acceptance or impact check, in input order.

    A row: ``{id, kind, cmd|procedure, exit|verdict, evidence, log, tail, green}``. ``report`` is the executor's
    stage-report (the source of a manual procedure's verdict); ``executor`` its actor. ``parallel`` command checks run at
    the same time (they must not share files; the order of the rows does not change). ``on_result`` is called with each row
    as soon as its check ends (from a worker thread).
    """
    project = Path(project)
    candidate = {"head": head(project), "dirty_digest": dirty_digest(project)}
    subject = subject_of(input_doc)
    reported = {row["id"]: row for row in (report or {}).get("checks_run", [])}
    wanted = [check for check in (input_doc.get("acceptance") or {}).get("checks", []) if check.get("kind") in RUN_KINDS]

    def run_one(check: dict) -> dict:
        row = run_check(check)
        if on_result is not None:
            on_result(row)
        return row

    def run_check(check: dict) -> dict:
        check_id = check["id"]
        started = _utc()
        row = {"id": check_id, "kind": check["kind"]}
        doc = {"$schema": "urn:swissknifeman:orch:exec:check-evidence:v1", "contract_version": "exec/v1",
               "evidence_id": f"{evidence_prefix}:{check_id}", "check_id": check_id, "subject": subject,
               "candidate": candidate, "started_at": started}
        if check.get("cmd"):
            cwd = (project / check.get("cwd", ".")).resolve()
            log = Path(log_dir) / f"{check_id}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            begin = time.monotonic()
            with open(log, "wb") as out:
                try:
                    done = subprocess.run(["bash", "-c", check["cmd"]], cwd=str(cwd), stdout=out,
                                          stderr=subprocess.STDOUT, timeout=timeout_s, start_new_session=True)
                    code = done.returncode
                except subprocess.TimeoutExpired:
                    code = 124
                    out.write(f"\n[orch] check timed out after {timeout_s} s\n".encode("utf-8"))
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-TAIL_LINES:]
            row.update(cmd=check["cmd"], exit=code, log=str(log), tail="\n".join(tail),
                       seconds=round(time.monotonic() - begin, 1), green=code == 0)
            doc.update(procedure={"cmd": check["cmd"], "cwd": check.get("cwd", ".")}, exit=code,
                       producer={"kind": "engine"})
        else:
            seen = reported.get(check_id)
            verdict = seen.get("verdict") if isinstance(seen, dict) else None
            row.update(procedure=check.get("procedure", ""), verdict=verdict, green=verdict == "pass")
            if verdict is None:  # nothing observed: no evidence is invented
                row["evidence"] = None
                return row
            doc.update(procedure={"procedure": check.get("procedure", "")}, verdict=verdict,
                       observation=f"reported by the executor: {verdict}",
                       producer={"kind": "executor", **({"actor": executor} if executor else {})})
        doc["finished_at"] = _utc()
        issues = [issue for issue in contracts.validate(doc, "check-evidence") if issue.level == "error"]
        if issues:
            raise ValueError(f"check-evidence of {check_id} is outside exec/v1: {issues[0].message}")
        target = Path(evidence_dir) / f"{check_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.{check_id}.tmp")
        temporary.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)
        row["evidence"] = _relative(target, project)
        return row

    if parallel > 1 and len(wanted) > 1:
        with ThreadPoolExecutor(max_workers=min(parallel, len(wanted))) as pool:
            return list(pool.map(run_one, wanted))  # map keeps the order of the input
    return [run_one(check) for check in wanted]
