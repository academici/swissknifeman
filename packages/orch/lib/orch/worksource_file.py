"""The built-in work source of one execution-input document: work outside the items of a plan.

``orch conduct run --input FILE`` serves a single piece of work, the document ``FILE`` (``orch.py input adhoc`` or a
hand-written ``exec/v1`` execution-input). It speaks the same protocol and the same ``work-source/v1`` contract as the
plugin source: a request orch builds wrongly never reaches it, and its answers are checked against the contract.

- ``claim`` always succeeds for the one input (a repeated claim answers the same piece);
- ``brief`` is the document itself, stored as a content-addressed blob; a file that changed during the run is refused;
- ``register`` records ``stage-report.json`` and ``evidence/V#.json`` in ``.swissknifeman/orch-artifacts/<run>/<input>``
  (never in ``plans/``) after the evidence gate;
- ``commit`` commits nothing unless the run asked for it (the changes stay in the tree); then it commits the given paths
  with the message ``adhoc(<input_id>): <title>``;
- ``release`` is a no-op (a file input keeps no claim) and ``note`` is refused: the journal of a plan belongs to the plan's
  own source;
- ``research`` records ``research-<n>.json`` next to the stage-report.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from aicore.state import blobs
from aicore.util.digest import canonical_json_bytes, sha256_tagged

from orch import contracts
from orch.worksource import WorkSourceError, problems
from aicore.util.proc import run as run_with_timeout

ARTIFACTS = Path(".swissknifeman") / "orch-artifacts"
RECEIPT = "register.json"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_INPUT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]*$")  # one path component: the id names the artifact folder
TITLE_LIMIT = 100


def safe(text: str) -> str:
    return _UNSAFE.sub("-", text).strip("-") or "input"


def title_of(doc: Mapping[str, Any]) -> str:
    """First line of the goal, cut to a commit-subject length."""
    line = str(doc.get("goal") or doc.get("input_id") or "input").strip().splitlines()[0].strip()
    return line if len(line) <= TITLE_LIMIT else line[:TITLE_LIMIT - 1].rstrip() + "…"


def read_input(path: str | Path) -> dict:
    """The execution-input of ``path``; ``WorkSourceError`` ``INPUT_INVALID`` when it is unreadable or outside exec/v1."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WorkSourceError("INPUT_INVALID", f"cannot read the input {path}: {error}") from None
    if not isinstance(doc, dict):
        raise WorkSourceError("INPUT_INVALID", f"the input {path} is not a JSON object")
    errors = [issue for issue in contracts.validate(doc, "execution-input") if issue.level == "error"]
    if not errors and (not _INPUT_ID.match(doc["input_id"]) or ".." in doc["input_id"]):
        raise WorkSourceError("INPUT_INVALID", f"the input {path} has the input_id {doc['input_id']!r}: it names the "
                              "folder of the artifacts and must be one path component of letters, digits, . _ - @")
    if errors:
        raise WorkSourceError("INPUT_INVALID", f"the input {path} is outside exec/v1: "
                              + "; ".join(f"{issue.path or '/'} {issue.code}: {issue.message}" for issue in errors[:3]))
    return doc


class FileWorkSource:
    """The work source of the document ``path``; ``commit`` says whether ``commit`` really commits."""

    def __init__(self, path: str | Path, *, project: str | Path, commit: bool = False):
        self.path = Path(path)
        self.project = Path(project).resolve()
        self.commit_enabled = bool(commit)

    # ------------------------------------------------------------------ the contract

    def call(self, op: str, fields: Mapping[str, Any]) -> dict:
        request = {"op": op, **{key: value for key, value in fields.items() if value is not None}}
        found = problems(request, "input")
        if found:
            raise WorkSourceError("INPUT_INVALID", f"{op} request outside work-source/v1: {'; '.join(found[:3])}",
                                  {"issues": found})
        answer = getattr(self, f"_{op}")(request)
        found = problems(answer, "output")
        if found:
            raise WorkSourceError("WORK_SOURCE_FAILED", f"file source {op} answered outside work-source/v1: "
                                  f"{'; '.join(found[:3])}", {"issues": found})
        return answer

    def claim(self, **fields: Any) -> dict:
        return self.call("claim", fields)

    def brief(self, **fields: Any) -> dict:
        return self.call("brief", fields)

    def register(self, **fields: Any) -> dict:
        return self.call("register", fields)

    def commit(self, **fields: Any) -> dict:
        return self.call("commit", fields)

    def release(self, **fields: Any) -> dict:
        return self.call("release", fields)

    def note(self, **fields: Any) -> dict:
        return self.call("note", fields)

    def research(self, **fields: Any) -> dict:
        return self.call("research", fields)

    # ------------------------------------------------------------------ operations

    def _artifacts(self, run_id: str, doc: Mapping[str, Any]) -> Path:
        return ARTIFACTS / run_id / doc["input_id"]

    def _claim(self, request: dict) -> dict:
        try:
            doc = read_input(self.path)
        except WorkSourceError as error:
            return {"op": "claim", "status": "blocked", "reason_code": error.code, "message": error.message}
        ref = doc["input_id"]
        asked = (request.get("items") or [ref])[0]
        if asked != ref:
            return {"op": "claim", "status": "blocked", "ref": asked, "reason_code": "INPUT_UNKNOWN",
                    "message": f"the input {self.path} holds {ref}, not {asked}"}
        answer = {"op": "claim", "status": "claimed", "ref": ref, "title": title_of(doc),
                  "attempt_id": f"att-{request['run_id']}-{safe(ref)}", "session": request["run_id"]}
        minimum = (doc.get("route") or {}).get("minimum") or {}
        if minimum.get("class") and minimum.get("effort"):
            answer["route"] = {"class": minimum["class"], "effort": minimum["effort"]}
        return answer

    def _brief(self, request: dict) -> dict:
        doc = read_input(self.path)
        if doc["input_id"] != request["ref"]:
            raise WorkSourceError("INPUT_CHANGED", f"the input {self.path} is now {doc['input_id']}, the run holds "
                                  f"{request['ref']}; start a new run for the changed input")
        digest = doc["digest"]
        reused = blobs.blob_path(sha256_tagged(canonical_json_bytes(doc)), project=self.project).is_file()
        stored = blobs.put_json(doc, sensitivity="normal", name=f"brief-{safe(doc['input_id'])}", project=self.project)
        return {"op": "brief", "input_ref": stored, "input_id": doc["input_id"], "digest": digest, "reused": reused,
                "artifact_id": f"brief-{safe(doc['input_id'])}-{digest[:12]}",
                "artifacts_dir": self._artifacts(request["run_id"], doc).as_posix()}

    def _proven(self, check: Mapping[str, Any], evidence: Mapping[str, str]) -> int | None:
        """Exit proven by the evidence file of an acceptance check, or None when it is missing or unusable."""
        path = evidence.get(check["id"])
        if not path:
            return None
        target = Path(path) if Path(path).is_absolute() else self.project / path
        try:
            found = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(found, dict) or found.get("check_id") != check["id"]:
            return None
        if isinstance(found.get("exit"), int):
            return found["exit"]
        if found.get("verdict") in ("pass", "fail"):
            return 0 if found["verdict"] == "pass" else 1
        return None

    def _register(self, request: dict) -> dict:
        doc = read_input(self.path)
        status, evidence = request["status"], request["evidence"]
        checks = {check["id"]: self._proven(check, evidence)
                  for check in (doc.get("acceptance") or {}).get("checks", []) if check.get("kind") == "acceptance"}
        if status == "blocked":
            verdict = "none"
        elif any(value is None for value in checks.values()):
            return {"op": "register", "outcome": "refused", "gate": {"verdict": "missing", "checks": checks},
                    "reason_code": "REGISTER_EVIDENCE_MISSING",
                    "message": "acceptance check(s) without check-evidence: "
                               + ", ".join(sorted(key for key, value in checks.items() if value is None))}
        elif any(value != 0 for value in checks.values()):
            return {"op": "register", "outcome": "refused", "gate": {"verdict": "red", "checks": checks},
                    "reason_code": "REGISTER_EVIDENCE_RED",
                    "message": "acceptance check(s) failed by their evidence: "
                               + ", ".join(sorted(key for key, value in checks.items() if value != 0))}
        else:
            verdict = "pass"
        gate = {"verdict": verdict, "checks": checks}
        folder = self.project / self._artifacts(request["run_id"], doc)
        receipt_path = folder / RECEIPT
        receipt = {"attempt_id": request["attempt_id"], "status": status}
        if receipt_path.is_file():
            try:
                if json.loads(receipt_path.read_text(encoding="utf-8")) == receipt:
                    return {"op": "register", "outcome": "no-op", "gate": gate}
            except ValueError:
                pass
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "stage-report.json").write_text(
            json.dumps({**request["report"], "status": status}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        copied = []
        for check_id, path in sorted(evidence.items()):
            source = Path(path) if Path(path).is_absolute() else self.project / path
            target = folder / "evidence" / f"{check_id}.json"
            if source.is_file() and source.resolve() != target.resolve():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                copied.append(check_id)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"op": "register", "outcome": "recorded", "gate": gate,
                "receipt": {"artifacts": folder.relative_to(self.project).as_posix(), "evidence_copied": copied}}

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        # literal pathspecs: a path such as ``item[1].txt`` is that file, never a pattern that takes foreign files along
        return run_with_timeout(["git", "--literal-pathspecs", "-C", str(self.project), *args], capture_output=True,
                              text=True, check=False, timeout=60)

    def _commit(self, request: dict) -> dict:
        if not self.commit_enabled:
            return {"op": "commit", "outcome": "no-op",
                    "message": "a file input does not commit unless the run asked for it (--commit); the changes stay in the tree"}
        doc = read_input(self.path)
        paths = sorted(set(request["paths"]))
        if not paths:
            return {"op": "commit", "outcome": "no-op", "message": "no paths to commit"}
        staged = set(self._git("diff", "--cached", "--name-only", "-z", "--", *paths).stdout.split("\0"))
        added = self._git("add", "-A", "--", *paths)
        if added.returncode:
            return {"op": "commit", "outcome": "refused", "reason_code": "COMMIT_REFUSED",
                    "message": (added.stderr or added.stdout).strip() or "git add failed"}
        if self._git("diff", "--cached", "--quiet", "--", *paths).returncode == 0:
            return {"op": "commit", "outcome": "no-op", "message": "nothing left to commit"}
        done = self._git("commit", "-q", "-m", f"adhoc({doc['input_id']}): {title_of(doc)}", "--", *paths)
        if done.returncode:
            fresh = [path for path in self._git("diff", "--cached", "--name-only", "-z", "--", *paths).stdout.split("\0")
                     if path and path not in staged]
            if fresh:  # a refused commit (a hook) leaves the index of the owner as it was
                self._git("reset", "-q", "--", *fresh)
            return {"op": "commit", "outcome": "refused", "reason_code": "COMMIT_REFUSED",
                    "message": (done.stderr or done.stdout).strip() or "git commit failed"}
        sha = self._git("rev-parse", "HEAD").stdout.strip()
        return {"op": "commit", "outcome": "committed", "sha": sha}

    def _release(self, request: dict) -> dict:
        return {"op": "release", "outcome": "no-op", "message": "a file input keeps no claim"}

    def _note(self, request: dict) -> dict:
        return {"op": "note", "outcome": "refused", "reason_code": "NOTE_UNSUPPORTED",
                "message": "a file input has no journal; the journal of a plan belongs to the source of that plan"}

    def _research(self, request: dict) -> dict:
        """The result of a research stage is kept next to the other records of the piece: ``research-<n>.json`` in its
        artifact folder (``orch-artifacts``); a repeat of the same result changes nothing."""
        doc = read_input(self.path)
        target = self.project / self._artifacts(request["run_id"], doc) / f"research-{request['number']}.json"
        body = json.dumps(request["result"], ensure_ascii=False, indent=2) + "\n"
        relative = target.relative_to(self.project).as_posix()
        if target.is_file() and target.read_text(encoding="utf-8") == body:
            return {"op": "research", "outcome": "no-op", "path": relative}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return {"op": "research", "outcome": "recorded", "path": relative}
