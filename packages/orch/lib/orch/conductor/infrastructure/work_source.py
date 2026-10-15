"""The work source as the conductor reaches it: the verbs of this package's own ``orch.py source`` (claim, brief, prepare,
release, research, register, commit), never the plan itself, and the artifact folder of a piece.

The one place of the conductor that writes into the artifact folder (``artifacts_dir`` of the brief, or
``.swissknifeman/orch-artifacts/<run>/<work>/`` for a source without one) or builds and runs an ``orch.py source``
command line (knowledge/p11-refactor#fs; ``tests/test_boundaries.py`` keeps it so)."""
from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Optional

from aicore.state import blobs

from orch.conductor import checks as checks_mod, options as opts
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import safe, write_json
from orch.settings import ORCH_ROOT

FALLBACK_ARTIFACTS = Path(".swissknifeman") / "orch-artifacts"  # committed records of a source without artifacts_dir


def run_orch(self, *args: str) -> tuple:
    """``(exit, JSON stdout or None, stderr)`` of this package's own ``orch.py``."""
    argv = [sys.executable, str(ORCH_ROOT / "scripts" / "orch.py"), "--project", str(self.project)]
    if self.project_resolution:  # the child is told the project; it records how the conductor found it
        argv += ["--project-resolution", self.project_resolution]
    if self.config_file:
        argv += ["--config", str(self.config_file)]
    done = subprocess.run(argv + list(args), cwd=str(self.project), capture_output=True, text=True,
                          env=self.env)
    try:
        doc = json.loads(done.stdout) if done.stdout.strip() else None
    except ValueError:
        doc = None
    return done.returncode, doc, done.stderr.strip()


def claim(self, key: str, asked: list, batch: bool = False) -> Optional[dict]:
    actor = self._claim_actor()
    kept = (self.state["claims"].get(key) or {}).get("submission")
    submission = kept or f"sub-{safe(self.run_id)}-{safe(key)}"[:120]
    file_source = self.run_doc.get("source") or {}
    where = ["--input", file_source["path"]] + (["--commit"] if file_source.get("commit") else []) \
        if file_source.get("kind") == "file" else ["--plan", self.run_doc["plan"]]
    args = ["source", "claim", *where, "--actor", actor, "--submission-id", submission]
    if self.run_doc.get("plans_root"):
        args += ["--plans-root", self.run_doc["plans_root"]]
    for ref in asked:
        args += ["--item", ref]
    if batch:
        args.append("--batch")
    code, answer, err = self._orch(*args)
    if code == 3:
        raise Stop("WORK_SOURCE_UNAVAILABLE", err or "no work source")
    if not isinstance(answer, dict):
        raise Stop("WORK_SOURCE_FAILED", err or "claim printed no answer")
    if answer.get("status") == "none":
        self.progress.emit("info", message="the work source has no ready piece of work")
        return None
    if answer.get("status") != "claimed":
        raise Stop("CLAIM_BLOCKED", f"{answer.get('ref', '-')}: {answer.get('reason_code', '-')}: "
                                    f"{answer.get('message', err)}")
    self.state["claims"][key] = {"ref": answer["ref"], "orch_run": answer["run_id"], "submission": submission,
                                 **({"title": answer["title"]} if answer.get("title") else {})}
    self._save()
    return answer


def release_claim(self, ref: str, state: dict, reason: str) -> bool:
    """Give the claim of ``ref`` back to the work source (``orch.py source release``), so that a later run can claim
    the piece. A source that does not serve ``release`` or refuses it keeps the claim: the stop is reported anyway."""
    code, answer, err = self._orch("source", "release", "--run", state["orch_run"], "--reason", reason)
    released = code == 0 and isinstance(answer, dict) and answer.get("outcome") in ("released", "no-op")
    state.setdefault("released", []).append({"at": clock.utc_now(), "reason": reason, "ok": released})
    self._save()
    self.progress.emit("info", item=ref, reason_code="CLAIM_RELEASED" if released else "CLAIM_KEPT",
                       message=(f"the claim of {ref} is given back to the work source" if released else
                                f"the claim of {ref} stays with run {state['orch_run']}: "
                                f"{(answer or {}).get('message') or err or 'the source refused'}"))
    return released


def brief(self, item: Item) -> dict:
    code, answer, err = self._orch("source", "brief", "--run", item.orch_run)
    if code != 0 or not isinstance(answer, dict):
        raise Stop("BRIEF_REFUSED", err or "brief printed no answer")
    try:
        doc = json.loads(blobs.read_bytes(answer["input_ref"], project=self.project))
    except (OSError, ValueError, KeyError) as error:
        raise Stop("BRIEF_UNAVAILABLE", str(error)) from None
    path = write_json(item.directory / "input.json", doc)
    artifacts = answer.get("artifacts_dir") or (FALLBACK_ARTIFACTS / self.run_id / safe(item.ref)).as_posix()
    try:
        base = checks_mod.head(self.project)  # the review compares the candidate with this revision
    except RuntimeError as error:
        raise Stop("PROJECT_NOT_GIT", str(error)) from None
    return {"input_path": str(path), "input_id": answer.get("input_id"), "artifacts_dir": artifacts,
            "base": base}


def prepare(self, item: Item) -> dict:
    provider = opts.stage_route(item.options, "executor").get("provider") or self.conductor.get("provider") \
        or "claude-code"
    args = ["source", "prepare", "--run", item.orch_run, "--provider", provider]
    if self.model_catalog:
        args += ["--model-catalog", str(self.model_catalog)]
    code, plan, err = self._orch(*args)
    if code != 0 or not isinstance(plan, dict):
        first = (err or "prepare refused").splitlines()[0]
        raise Stop("PREPARE_REFUSED", first)
    return {"stages": [{key: stage.get(key) for key in ("stage_id", "role", "provider", "model", "effort")}
                       for stage in plan.get("stages", [])],
            "refusals": [{key: item_.get(key) for key in ("stage_id", "reason_code")}
                         for item_ in plan.get("refusals", [])]}


def refresh_input(self, item: Item) -> None:
    """A plan amended during the piece (a wider write set, a fixed check) reaches the next executor round: the brief
    is asked again and, when its digest changed, replaces the input of every later step."""
    code, answer, _ = self._orch("source", "brief", "--run", item.orch_run)
    if code != 0 or not isinstance(answer, dict) or not answer.get("input_ref"):
        return
    try:
        doc = json.loads(blobs.read_bytes(answer["input_ref"], project=self.project))
    except (OSError, ValueError, KeyError):
        return
    if doc.get("digest") and doc.get("digest") != item.input_doc.get("digest"):
        write_json(item.directory / "input.json", doc)
        item.input_doc = doc
        self.progress.emit("info", item=item.ref, reason_code="INPUT_REBUILT",
                           message=f"the plan changed during the piece: input {answer.get('input_id', '-')} is used from now on")


def research_save(self, item: Item, number: int, found: dict) -> dict:
    result_file = self.project / found["file"]
    code, answer, err = self._orch("source", "research", "--run", item.orch_run, "--result", str(result_file),
                                   "--number", str(number), "--actor", self.conductor.get("registrar") or "orch/conductor")
    if code == 0 and isinstance(answer, dict) and answer.get("outcome") in ("recorded", "no-op"):
        return {"outcome": answer["outcome"], "path": answer.get("path")}
    if isinstance(answer, dict) and answer.get("outcome") == "refused":
        why = f"{answer.get('reason_code', 'RESEARCH_REFUSED')}: {answer.get('message', '')}".rstrip(": ")
    else:
        why = err or "the work source printed no answer"
    kept = write_json(item.artifacts / f"research-{number}.json", found["result"])
    self.progress.emit("info", item=item.ref, stage=f"research-save.{number}", reason_code="RESEARCH_NOT_SAVED",
                       message=f"the work source did not take the research result ({why}); kept in {self._relative(kept)}"[:300])
    return {"outcome": "kept", "path": self._relative(kept), "reason": why[:300]}


def register(self, item: Item, args: list) -> dict:
    """``orch.py source register`` with the arguments ``finish`` built: ``{outcome, gate}``, or a ``Stop``."""
    code, answer, err = self._orch(*args)
    if code == 3:
        raise Stop("WORK_SOURCE_UNAVAILABLE", err or "no work source")
    if not isinstance(answer, dict) or answer.get("outcome") not in ("recorded", "no-op"):
        reason = (answer or {}).get("reason_code") or "REGISTER_REFUSED"
        raise Stop("REGISTER_REFUSED", f"{reason}: {(answer or {}).get('message') or err}")
    note = answer.get("note")
    if isinstance(note, dict) and note.get("outcome") != "recorded":  # the work is registered; only its note is lost
        self.progress.emit("info", item=item.ref, reason_code="WORK_SOURCE_NO_NOTE",
                           message=f"the work source of the plan did not take the note: {note.get('message') or note.get('outcome')}")
    return {"outcome": answer["outcome"], "gate": (answer.get("gate") or {}).get("verdict")}


def commit(self, item: Item, paths: list) -> dict:
    """``orch.py source commit`` of ``paths``: ``{outcome, sha}``, or a ``Stop``."""
    args = ["source", "commit", "--run", item.orch_run]
    for path in paths:
        args += ["--path", path]
    code, answer, err = self._orch(*args)
    if code == 3:
        raise Stop("WORK_SOURCE_UNAVAILABLE", err or "no work source")
    if not isinstance(answer, dict) or answer.get("outcome") not in ("committed", "no-op"):
        reason = (answer or {}).get("reason_code") or "COMMIT_REFUSED"
        raise Stop("COMMIT_REFUSED", f"{reason}: {(answer or {}).get('message') or err}")
    return {"outcome": answer["outcome"], "sha": answer.get("sha")}


def open_artifacts(self, item: Item, brief: dict) -> None:
    """The artifact folder of the piece, as the brief named it."""
    item.artifacts = self.project / brief["artifacts_dir"]


def write_artifact(self, item: Item, name: str, doc) -> Path:
    """``doc`` as ``<artifacts>/<name>``: a committed record of the piece (stage-report, review-verdict, advice)."""
    return write_json(item.artifacts / name, doc)


def evidence_dir(item: Item) -> Path:
    """The folder of the evidence files the acceptance checks of the piece leave."""
    return item.artifacts / "evidence"


def register_args(item: Item, report_path: Path, status: str, actor: str, executed_by: str, evidence: dict) -> list:
    """The arguments of ``orch.py source register`` for the result of the piece."""
    args = ["source", "register", "--run", item.orch_run, "--report", str(report_path), "--status", status,
            "--actor", actor, "--executed-by", executed_by]
    for check_id, path in sorted(evidence.items()):
        args += ["--evidence", f"{check_id}={path}"]
    return args


def closer_command(self, args: list) -> str:
    """The one command a model registrar runs to record the result. ``python3`` as a bare name: the launch catalog
    allows the registrar exactly ``python3 *orch.py source register *``; an invocation config before the verb is
    outside that allowance, so such a closer is refused and the conductor records."""
    argv = ["python3", str(ORCH_ROOT / "scripts" / "orch.py"), *args]
    if self.config_file:
        argv[2:2] = ["--config", str(self.config_file)]
    return shlex.join(argv)
