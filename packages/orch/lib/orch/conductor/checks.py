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


POLL_S = 5


# The install roots of the orchestrator the conductor runs from. A check tests the PROJECT, so it must not see them when
# they lead outside it (a frozen or installed copy of the orchestrator would be tested instead of the project's own code).
INSTALL_ROOTS = ("AICORE_ROOT", "SKM_ORCH_ROOT", "PLANNER_ROOT", "PLANNER_PLAN_PY")


def check_env(cwd: Path, environ=None) -> dict:
    """The environment of a check command: the conductor's, without install roots that lie outside the project."""
    base = dict(os.environ if environ is None else environ)
    project = Path(cwd).resolve()
    for name in INSTALL_ROOTS:
        value = base.get(name)
        if not value:
            continue
        try:
            Path(value).resolve().relative_to(project)
        except ValueError:
            base.pop(name)
    return base


def _run_command(argv: list, *, cwd: Path, out, timeout_s: int, warn_s: int, on_slow=None) -> int:
    """Exit code of ``argv``; 124 after ``timeout_s`` (0: no ceiling). ``on_slow(elapsed, pid)`` every ``warn_s``."""
    process = subprocess.Popen(argv, cwd=str(cwd), stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
                               env=check_env(cwd))
    try:
        return _wait_command(process, out=out, timeout_s=timeout_s, warn_s=warn_s, on_slow=on_slow)
    except BaseException:  # an interrupted run must not leave the check (a test run with workers) running
        _kill_group(process)
        raise
    finally:
        try:  # what the command left in its group (workers of a test runner) dies with it
            os.killpg(process.pid, 9)
        except OSError:
            pass


def _kill_group(process) -> None:
    try:
        os.killpg(process.pid, 15)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, 9)
        except OSError:
            pass
        process.wait()


def _wait_command(process, *, out, timeout_s: int, warn_s: int, on_slow) -> int:
    began, next_warn = time.monotonic(), warn_s
    while True:
        try:
            return process.wait(timeout=POLL_S)
        except subprocess.TimeoutExpired:
            pass
        elapsed = time.monotonic() - began
        if timeout_s and elapsed > timeout_s:
            _kill_group(process)
            out.write(f"\n[orch] check timed out after {timeout_s} s\n".encode("utf-8"))
            return 124
        if warn_s and on_slow is not None and elapsed >= next_warn:
            next_warn += warn_s
            on_slow(elapsed, process.pid)


def run_checks(input_doc: dict, *, project: Path, evidence_dir: Path, log_dir: Path, timeout_s: int,
               evidence_prefix: str, report: dict | None = None, executor: dict | None = None,
               parallel: int = 1, on_result=None, first=(), kinds=RUN_KINDS, cadence=("item", "phase"),
               warn_s: int = 0, on_slow=None) -> list:
    """Run the checks and write their evidence; one row per acceptance or impact check, in input order.

    A row: ``{id, kind, cmd|procedure, exit|verdict, evidence, log, tail, green}``. ``report`` is the executor's
    stage-report (the source of a manual procedure's verdict); ``executor`` its actor. ``parallel`` command checks run at
    the same time (they must not share files; the order of the rows does not change). ``on_result`` is called with each row
    as soon as its check ends (from a worker thread). ``first`` names checks (the ones that were red before) to run before
    all others: when one of them is still red the others are not run (``skipped``) — a correction that did not mend the
    red check does not need a half-hour run of everything else. ``kinds`` limits the run to these kinds (a quick pass
    runs ``acceptance`` only; the ``impact`` checks wait for the full pass). ``cadence`` limits it to the checks of
    these cadences (a check without one is ``item``; ``phase`` checks run in the closing piece of a phase).
    ``timeout_s`` 0 sets no ceiling on a check; ``on_slow(check_id, elapsed, pid)`` is called every ``warn_s`` seconds of
    a running check, so a long run is reported, not cut.
    """
    project = Path(project)
    candidate = {"head": head(project), "dirty_digest": dirty_digest(project)}
    subject = subject_of(input_doc)
    reported = {row["id"]: row for row in (report or {}).get("checks_run", [])}
    wanted = [check for check in (input_doc.get("acceptance") or {}).get("checks", [])
              if check.get("kind") in kinds and check.get("cadence", "item") in cadence]

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
                code = _run_command(["bash", "-c", check["cmd"]], cwd=cwd, out=out, timeout_s=timeout_s, warn_s=warn_s,
                                    on_slow=None if on_slow is None else
                                    (lambda elapsed, pid, check_id=check_id: on_slow(check_id, elapsed, pid)))
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

    def run_all(checks: list) -> list:
        if parallel > 1 and len(checks) > 1:
            with ThreadPoolExecutor(max_workers=min(parallel, len(checks))) as pool:
                return list(pool.map(run_one, checks))  # map keeps the order of the input
        return [run_one(check) for check in checks]

    ahead = [check for check in wanted if check["id"] in set(first)]
    if not ahead or len(ahead) == len(wanted):
        return run_all(wanted)
    done = {row["id"]: row for row in run_all(ahead)}
    if all(row["green"] for row in done.values()):
        done.update({row["id"]: row for row in run_all([check for check in wanted if check["id"] not in done])})
    else:
        for check in wanted:
            if check["id"] not in done:
                skipped = {"id": check["id"], "kind": check["kind"], "skipped": True, "green": False, "evidence": None,
                           "cmd": check.get("cmd"), "procedure": check.get("procedure")}
                if on_result is not None:
                    on_result(skipped)
                done[check["id"]] = skipped
    return [done[check["id"]] for check in wanted]
