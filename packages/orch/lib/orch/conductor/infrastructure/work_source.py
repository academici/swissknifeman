"""The work source as the conductor reaches it: the verbs of this package's own ``orch.py source`` (claim, brief,
release, research, register, commit), never the plan itself, and the artifact folder of a piece. ``prepare`` is the
exception: it binds the launch-plan in this process so a public ``source prepare`` stays strict.

The one place of the conductor that writes into the artifact folder (``artifacts_dir`` of the brief, or
``.swissknifeman/orch-artifacts/<run>/<work>/`` for a source without one) or builds and runs an ``orch.py source``
command line (knowledge/p11-refactor#fs; ``tests/test_boundaries.py`` keeps it so)."""
from __future__ import annotations

import json
import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import shlex
import sys
from typing import Callable, Optional

from aicore.state import blobs
from aicore.util import timefmt
from aicore.util.digest import canonical_json_bytes, sha256_hex
from aicore.workspace import WorkspaceError, read_marker

from orch import contracts, journal
from orch.conductor import checks as checks_mod, options as opts
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import safe, write_json
from orch.settings import ORCH_ROOT
from orch.port import PortError
from orch.worksource import problems as source_problems
from aicore.util.proc import run as run_with_timeout

# Local records of a source without artifacts_dir (not committed: ignored like the state folder); a plan source keeps the
# evidence of its items with the plan at register.
FALLBACK_ARTIFACTS = Path(".swissknifeman") / "orch-artifacts"
ORCH_TRANSPORT: Optional[Callable] = None


def inprocess_transport(argv, cwd, env):
    """Test transport for the source CLI; restore process state even on an exception.

    This seam is process-global and belongs to sequential tests within a worker only.
    Production always uses the subprocess transport.
    """
    global ORCH_TRANSPORT
    previous_env, previous_cwd = dict(os.environ), os.getcwd()
    previous_transport = ORCH_TRANSPORT
    out, err = io.StringIO(), io.StringIO()
    try:
        os.environ.clear()
        os.environ.update(previous_env if env is None else env)
        os.chdir(cwd)
        with redirect_stdout(out), redirect_stderr(err):
            from orch import cli
            try:
                code = cli.main(list(argv[2:]))
            except SystemExit as exc:
                code = exc.code
                if code is not None and not isinstance(code, int):
                    print(code, file=sys.stderr)
                    code = 1
        return code or 0, out.getvalue(), err.getvalue()
    finally:
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_env)
        ORCH_TRANSPORT = previous_transport


def _subprocess_transport(argv, cwd, env):
    done = run_with_timeout(argv, cwd=cwd, capture_output=True, text=True, env=env, timeout=600)
    return done.returncode, done.stdout, done.stderr


def read_receipt(item: Item, kind: str, *, project=None) -> Optional[dict]:
    """Read the work-source run, never the conductor item folder. Broken documents authorize only a repeat.

    Private metadata accompanies the raw answer for recovery; it never becomes a step result.
    ``project`` is the same project passed to the source CLI (machine state is used only without a project).
    """
    if not item.orch_run:
        return None
    kind = "register" if kind == "close" else kind
    try:
        directory = journal.run_dir(item.orch_run, project=project)
        doc = journal.read_doc(directory, f"receipts/{kind}.json")
        request = journal.read_doc(directory, f"receipts/{kind}-request.json")
        request_mtime_ns = (directory / f"receipts/{kind}-request.json").stat().st_mtime_ns \
            if isinstance(request, dict) else None
        run_doc = journal.read_doc(directory, "run.json") or {}
        marker = read_marker(project) if project is not None else None
    except (OSError, ValueError, PortError, WorkspaceError):
        return None
    if not isinstance(doc, dict) or not isinstance(run_doc, dict):
        return None
    source = run_doc.get("source") or {}
    if not isinstance(source, dict):
        return None
    file_source = source.get("kind") == "file"
    workspace = not file_source and bool(marker and marker.get("plans_store") == "workspace")
    source_sha = None
    parameters = request.get("parameters") if isinstance(request, dict) else None
    if (isinstance(parameters, dict) and request.get("attempt_id") == item.claim.get("attempt_id")
            and parameters.get("attempt_id") == request.get("attempt_id")
            and parameters.get("run_id") == item.orch_run and parameters.get("ref") == item.ref
            and request.get("digest") == sha256_hex(canonical_json_bytes(parameters))):
        candidate = request.get("source_sha")
        if isinstance(candidate, str) and not source_problems({"op": "commit", "outcome": "committed", "sha": candidate}, "output"):
            source_sha = candidate
    return {**doc, "_request": request, "_request_mtime_ns": request_mtime_ns,
            "_workspace_required": workspace, "_source_sha": source_sha}


def receipt_closes(kind: str, doc: Optional[dict], item: Item, *, state_saved_ns: Optional[int] = None) -> tuple:
    """L11: successful outcome, this attempt, and a finished workspace part. Git history is never authority."""
    step = item.state.get("steps", {}).get(kind, {})
    kind = "register" if kind == "close" else kind
    if not isinstance(doc, dict) or doc.get("op") != kind:
        return False, "repeated: receipt missing"
    if doc.get("outcome") not in (("recorded", "no-op") if kind == "register" else ("committed", "no-op")):
        return False, "repeated: receipt refused"
    # The fields recovered into a step obey the same contract as a live source answer.
    # Workspace completion has its own L11 rules below, including historical success statuses.
    fields = ("op", "outcome", "gate") if kind == "register" else ("op", "outcome", "sha", "message", "attempt")
    if source_problems({key: doc[key] for key in fields if key in doc}, "output"):
        return False, "repeated: receipt missing"
    recovering = step.get("status") == "started"
    if recovering:
        # started_at has second precision in existing journals. The publication of state.json also fences a retry
        # within that same second; a later state save can conservatively require an idempotent repeat.
        try:
            started = timefmt.parse_rfc3339(step["started_at"])
            if started is None:
                raise ValueError("started_at is not a timestamp")
            boundary = max(int(started.timestamp() * 1_000_000_000), state_saved_ns or 0)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return False, "repeated: receipt of another attempt"
        request_mtime = doc.get("_request_mtime_ns")
        if not isinstance(request_mtime, int) or request_mtime < boundary:
            return False, "repeated: receipt of another attempt"
    expected = item.claim.get("attempt_id")
    receipt = doc.get("receipt")
    if receipt is not None and not isinstance(receipt, dict):
        return False, "repeated: receipt missing"
    attempt = doc.get("attempt") or (receipt or {}).get("attempt_id")
    if not attempt or recovering:
        request = doc.get("_request")
        if not isinstance(request, dict) or not isinstance(request.get("parameters"), dict):
            return False, "repeated: receipt missing"
        parameters = request["parameters"]
        raw = {key: value for key, value in doc.items() if not key.startswith("_")}
        if (request.get("digest") != sha256_hex(canonical_json_bytes(parameters))
                or request.get("receipt_digest") != sha256_hex(canonical_json_bytes(raw))
                or parameters.get("run_id") != item.orch_run
                or parameters.get("ref") != item.ref
                or parameters.get("attempt_id") != request.get("attempt_id")):
            return False, "repeated: receipt missing"
        if attempt and attempt != request.get("attempt_id"):
            return False, "repeated: receipt of another attempt"
        attempt = request.get("attempt_id")
    if not expected or attempt != expected:
        return False, "repeated: receipt of another attempt"
    if kind == "commit" and not workspace_complete(doc, required=bool(doc.get("_workspace_required"))):
        return False, "repeated: workspace part incomplete"
    return True, "closed from receipt"


def workspace_complete(answer: dict, *, required: bool = False) -> bool:
    split = answer.get("workspace_commit")
    if not required and not any(key in answer for key in ("workspace_commit", "workspace_sha", "repo")):
        return True
    return isinstance(split, dict) and split.get("status") in ("committed", "no-op", "skipped-legacy", "skipped-no-git")


def receipt_result(kind: str, answer: dict) -> dict:
    """The same result shapes for live calls and recovered steps (finish reads close['by'])."""
    if kind == "close":
        return {"by": "closer", "answer": "registration recovered from receipt"}
    if kind == "register":  # ``evidence``: where the source keeps the evidence for good (a workspace plan)
        return {"outcome": answer["outcome"], "gate": (answer.get("gate") or {}).get("verdict"),
                **({"evidence": answer["evidence"]} if answer.get("evidence") else {})}
    kept = {"outcome": answer["outcome"], "sha": answer.get("sha")}
    if answer.get("repo") == "workspace":
        kept["sha"] = answer.get("_source_sha")
        if not kept["sha"]:
            kept["message"] = f"workspace commit {answer.get('sha')}; source commit unknown"
    if answer.get("message"):
        kept["message"] = "; ".join(filter(None, (kept.get("message"), answer["message"])))
    return kept


def run_orch(self, *args: str) -> tuple:
    """``(exit, JSON stdout or None, stderr)`` of this package's own ``orch.py``."""
    argv = [sys.executable, str(ORCH_ROOT / "scripts" / "orch.py"), "--project", str(self.project)]
    if self.project_resolution:  # the child is told the project; it records how the conductor found it
        argv += ["--project-resolution", self.project_resolution]
    if self.config_file:
        argv += ["--config", str(self.config_file)]
    code, out, err = (ORCH_TRANSPORT or _subprocess_transport)(argv + list(args), str(self.project), self.env)
    try:
        doc = json.loads(out) if out.strip() else None
    except ValueError:
        doc = None
    return code, doc, err.strip()


OWNED_HINT = ("; the conductor never takes a piece over: free it from the run that holds it (`orch conduct release --run RUN "
              "--item REF` before any work began, `settle` after the owner finished it) or hand it over by hand with the "
              "take-over command of the source itself")


def owned_hint(answer: dict) -> str:
    """What to do about a piece another session holds (the refusal of the source names no conductor verb)."""
    return OWNED_HINT if "ITEM_OWNED" in f"{answer.get('reason_code', '')} {answer.get('message', '')}" else ""


def claim(self, key: str, asked: list, batch: bool = False, *, actor: str, actor_source: tuple) -> Optional[dict]:
    """Claim ``asked`` (the source picks when empty) as ``actor``; ``actor_source`` is ``(source, fields, model_class)``
    of that actor (``claim_actor`` and ``claim_actor_source`` of the run)."""
    kept = (self.state["claims"].get(key) or {}).get("submission")
    submission = kept or f"sub-{safe(self.run_id)}-{safe(key)}"[:120]
    file_source = self.run_doc.get("source") or {}
    where = ["--input", file_source["path"]] + (["--commit"] if file_source.get("commit") else []) \
        if file_source.get("kind") == "file" else ["--plan", self.run_doc["plan"]]
    args = ["source", "claim", *where, "--actor", actor, "--submission-id", submission]
    source, named, model_class = actor_source
    args += ["--actor-source", source] + [arg for name in named or [] for arg in ("--actor-field", name)]
    if model_class:
        args += ["--actor-class", model_class]
    if self.run_doc.get("plans_root"):
        args += ["--plans-root", self.run_doc["plans_root"]]
    for ref in asked:
        args += ["--item", ref]
    if batch:
        args.append("--batch")
    if self.run_doc.get("scenario") and file_source.get("kind") != "file":
        args += ["--scenario", self.run_doc["scenario"]]
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
                                    f"{answer.get('message', err)}{owned_hint(answer)}")
    # the plan's executor the run replaced: kept in the snapshot of the run; a repeated claim of a closed piece (a group
    # review) answers without it, and the record stays
    override = answer.get("actor_override") or (self.state["claims"].get(key) or {}).get("actor_override")
    self.state["claims"][key] = {"ref": answer["ref"], "orch_run": answer["run_id"], "submission": submission,
                                 **({"title": answer["title"]} if answer.get("title") else {}),
                                 **({"actor_override": override} if override else {})}
    self._save()
    if answer.get("actor_override"):
        self.progress.emit("info", item=answer["ref"], reason_code="ACTOR_OVERRIDE",
                           message=answer["actor_override"]["message"])
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


def input_errors(doc) -> list:
    """``path code: message`` of every error of ``doc`` as an exec/v1 execution-input (schema and semantics)."""
    if not isinstance(doc, dict):
        return ["/ type: the brief is not a JSON object"]
    return [f"{issue.path or '/'} {issue.code}: {issue.message}" for issue in contracts.validate(doc, "execution-input")
            if issue.level == "error"]


def brief(self, item: Item) -> dict:
    code, answer, err = self._orch("source", "brief", "--run", item.orch_run)
    if code != 0 or not isinstance(answer, dict):
        raise Stop("BRIEF_REFUSED", err or "brief printed no answer")
    try:
        doc = json.loads(blobs.read_bytes(answer["input_ref"], project=self.project))
    except (OSError, ValueError, KeyError) as error:
        raise Stop("BRIEF_UNAVAILABLE", str(error)) from None
    errors = input_errors(doc)
    if errors:  # the run executes only what the file source would accept too
        raise Stop("BRIEF_INVALID", f"{item.ref}: the brief {answer.get('input_id') or answer['input_ref']} is outside "
                   f"exec/v1 execution-input: {'; '.join(errors[:3])}")
    path = write_json(item.directory / "input.json", doc)
    artifacts = answer.get("artifacts_dir") or (FALLBACK_ARTIFACTS / self.run_id / safe(item.ref)).as_posix()
    try:
        base = checks_mod.head(self.project)  # the review compares the candidate with this revision
    except RuntimeError as error:
        raise Stop("PROJECT_NOT_GIT", str(error)) from None
    return {"input_path": str(path), "input_id": answer.get("input_id"), "artifacts_dir": artifacts,
            "base": base}


def check_brief_size(item: Item, doc: Optional[dict] = None) -> None:
    """``budgets.brief_max_bytes`` of the run policy (0 or absent: no limit) against the execution-input of the piece (``doc``
    when it is a rebuilt one), the embedded context pack and the files it reads included; checked once the options are
    resolved, before any role runs, and again when the input is rebuilt."""
    limit = int(((item.policy or {}).get("budgets") or {}).get("brief_max_bytes") or 0)
    size = len(json.dumps(item.input_doc if doc is None else doc).encode("utf-8")) if limit else 0
    if limit and size > limit:
        raise Stop("BRIEF_TOO_LARGE", f"{item.ref}: execution-input is {size} bytes > budgets.brief_max_bytes {limit} of the "
                   f"run policy {(item.policy or {}).get('policy_id', '-')}; split the item or raise the budget in the policy")


def prepare(self, item: Item) -> dict:
    """The launch-plan of the piece, with the stages this conductor skips already omitted.

    Public ``source prepare`` binds the pack as stored, including an optional role it does not
    run. Calling that verb from here would either drop the role for every client or refuse a
    skipped stage that has no manifest. This path writes the same ``launch-plan.json`` and
    refusal events, and it does not add a public flag.
    """
    check_brief_size(item)  # after the brief and the options, before the first role
    from types import SimpleNamespace
    provider = opts.stage_route(item.options, "executor").get("provider") or self.conductor.get("provider") \
        or "claude-code"
    args = SimpleNamespace(run=item.orch_run, provider=provider, binding=None, model_catalog=self.model_catalog,
                           config=self.config_file)
    out, err = io.StringIO(), io.StringIO()
    previous = os.getcwd()
    previous_env = dict(os.environ) if self.env is not None else None
    try:
        os.chdir(self.project)
        if previous_env is not None:
            os.environ.clear()
            os.environ.update(self.env)
        from orch import cli
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = cli._source_prepare(args, self.settings, self.project, conductor=True)
            except cli.SourceRefusal as refusal:
                code, err = refusal.exit_code, io.StringIO(f"{refusal.code}: {refusal.message}")
    finally:
        if previous_env is not None:
            os.environ.clear()
            os.environ.update(previous_env)
        os.chdir(previous)
    text = out.getvalue()
    try:
        plan = json.loads(text) if text.strip() else None
    except ValueError:
        plan = None
    message = err.getvalue().strip()
    if code != 0 or not isinstance(plan, dict):
        first = (message or "prepare refused").splitlines()[0]
        raise Stop("PREPARE_REFUSED", first)
    return {"stages": [{key: stage.get(key) for key in ("stage_id", "role", "provider", "model", "effort")}
                       for stage in plan.get("stages", [])],
            "refusals": [{key: item_.get(key) for key in ("stage_id", "reason_code")}
                         for item_ in plan.get("refusals", [])]}


def refresh_input(self, item: Item) -> None:
    """A plan amended during the piece (a wider write set, a fixed check) reaches the next executor round: the brief
    is asked again and, when its digest changed, replaces the input of every later step."""
    code, answer, err = self._orch("source", "brief", "--run", item.orch_run)
    if code != 0 or not isinstance(answer, dict) or not answer.get("input_ref"):
        self.progress.emit("info", item=item.ref, reason_code="INPUT_REFRESH_FAILED",
                           message=f"the brief could not be asked again ({(err or 'no answer').splitlines()[0][:160]}); "
                                   "the next round keeps the earlier input")
        return
    try:
        doc = json.loads(blobs.read_bytes(answer["input_ref"], project=self.project))
    except (OSError, ValueError, KeyError):
        self.progress.emit("info", item=item.ref, reason_code="INPUT_REFRESH_FAILED",
                           message="the re-asked brief cannot be read; the next round keeps the earlier input")
        return
    errors = input_errors(doc)
    if errors:
        self.progress.emit("info", item=item.ref, reason_code="INPUT_REFRESH_FAILED",
                           message=f"the re-asked brief is outside exec/v1 ({errors[0][:160]}); the next round keeps "
                                   "the earlier input")
        return
    if doc.get("digest") and doc.get("digest") != item.input_doc.get("digest"):
        check_brief_size(item, doc)
        write_json(item.directory / "input.json", doc)
        previous, item.input_doc = item.input_doc.get("digest"), doc
        self._beacon_event("orch.input.rebuilt", item, {"previous_digest": previous, "digest": doc["digest"]})
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
    return receipt_result("register", answer)


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
    if not workspace_complete(answer):
        raise Stop("COMMIT_REFUSED", "workspace part incomplete; resume repeats the commit without undoing the source part")
    if answer.get("repo") == "workspace":
        receipt = read_receipt(item, "commit", project=self.project)
        answer = {**answer, "_source_sha": (receipt or {}).get("_source_sha")}
    return receipt_result("commit", answer)


def open_artifacts(self, item: Item, brief: dict) -> None:
    """The artifact folder of the piece, as the brief named it."""
    folder = (self.project / brief["artifacts_dir"]).resolve()
    try:
        folder.relative_to(self.project.resolve())
    except ValueError:
        raise Stop("ARTIFACTS_OUTSIDE_PROJECT", f"artifacts_dir {brief['artifacts_dir']!r} of {item.ref} leads outside the project") from None
    item.artifacts = self.project / brief["artifacts_dir"]


def write_artifact(self, item: Item, name: str, doc) -> Path:
    """``doc`` as ``<artifacts>/<name>``: a record of the piece (stage-report, review-verdict, advice), committed with the
    piece when the source named the folder, local in the fallback folder otherwise."""
    return write_json(item.artifacts / name, doc)


def artifact_path(item: Item, name: str) -> Path:
    """The source-owned location of an item artifact, without assuming a plan's folder layout."""
    return item.artifacts / name


def stray_dir(item: Item) -> Path:
    """Where the runtime artifacts an executor left in the tree are set aside: ``<artifacts>/stray/<original path>``."""
    return (item.artifacts or item.directory) / "stray"


def protected_dir(item: Item) -> Path:
    """Where the executor stages the content of a path its provider refuses to write: ``<artifacts>/protected/<path>``."""
    return (item.artifacts or item.directory) / "protected"


def local_records(self, item: Item) -> bool:
    """The artifact folder of the piece is the local fallback (the source named none): it is not committed."""
    try:
        (self.project / item.artifacts).resolve().relative_to((self.project / FALLBACK_ARTIFACTS).resolve())
    except ValueError:
        return False
    return True


def evidence_dir(item: Item) -> Path:
    """The folder of the evidence files the acceptance checks of the piece leave."""
    return item.artifacts / "evidence"


def review_receipt(item: Item) -> Optional[Path]:
    """The completed review receipt, when the piece has one."""
    path = item.artifacts / "review-receipt.json"
    return path if path.is_file() else None


def register_args(item: Item, report_path: Path, status: str, actor: str, executed_by: str, evidence: dict,
                  review_receipt: Optional[str] = None) -> list:
    """The arguments of ``orch.py source register`` for the result of the piece."""
    args = ["source", "register", "--run", item.orch_run, "--report", str(report_path), "--status", status,
            "--actor", actor, "--executed-by", executed_by]
    for check_id, path in sorted(evidence.items()):
        args += ["--evidence", f"{check_id}={path}"]
    if review_receipt:
        args += ["--review-receipt", review_receipt]
    return args


def closer_command(self, args: list) -> str:
    """The one command a model registrar runs to record the result. ``python3`` as a bare name: the launch catalog
    allows the registrar exactly ``python3 *orch.py source register *``; an invocation config before the verb is
    outside that allowance, so such a closer is refused and the conductor records."""
    argv = ["python3", str(ORCH_ROOT / "scripts" / "orch.py"), *args]
    if self.config_file:
        argv[2:2] = ["--config", str(self.config_file)]
    return shlex.join(argv)


def brief_doc(self, answer: dict) -> dict:
    """The execution-input of a claimed piece, asked without starting it (the facts the review strategist reads); ``{}`` when the
    source cannot answer."""
    code, found, _ = self._orch("source", "brief", "--run", answer["run_id"])
    if code != 0 or not isinstance(found, dict) or not found.get("input_ref"):
        return {}
    try:
        return json.loads(blobs.read_bytes(found["input_ref"], project=self.project))
    except (OSError, ValueError, KeyError):
        return {}
