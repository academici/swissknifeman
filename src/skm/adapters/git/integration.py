"""Local target writer: projected task deltas, durable epochs, one-use admission and receipt CAS."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID

from skm.adapters.git.commit import author_env, git_vcs
from skm.adapters.git.host_inputs import read_metadata
from skm.adapters.git.integration_candidate import IntegrationCandidate
from skm.adapters.git.integration_process import (
    DurableGitRunner,
    inspect_effect,
    run_owned_git,
    run_ref_transaction,
    writer_ownership,
)
from skm.adapters.git.runner import GitRunner, validate_repository_trust
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.modules.execution.domain.external_effect import (
    GitCommitReceipt,
    GitCommitRequest,
    canonical,
    commit_request,
    effect_digest,
    local_identities_match,
    local_receipt_matches,
    observation_receipt,
    projected_request,
    push_arguments,
    push_rejected,
    receipt_from_document,
    reconciliation_observation,
    request_document,
    require_admission,
    result_report,
)
from skm.modules.execution.domain.ids import ExternalEffectId
from skm.modules.execution.domain.integration import (
    CommitMode,
    IntegrationStrategy,
    validate_mode,
)
from skm.modules.execution.ports import StageClient, Vcs
from skm.modules.workspace.domain.remote_url import remote_endpoint
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock
from skm.platform.process.identity import ProcessIdentity

__all__ = ["git_integration_vcs"]


class GitIntegrator(IntegrationCandidate):
    def __init__(
        self,
        git: GitRunner,
        *,
        worktrees_root: Path,
        now: Callable[[], datetime],
        monotonic: Callable[[], float],
        quiescent: Callable[[Mapping[str, Any]], bool] = lambda _: False,
        repositories: Mapping[str, Path] | None = None,
    ) -> None:
        self.git, self.root, self.now, self.monotonic = DurableGitRunner(git), worktrees_root, now, monotonic
        self.quiescent, self.repositories = quiescent, dict(repositories or {})
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        validate_repository_trust(self.root)
        self.snapshots = git_vcs(git, state_dir=self.root / "_snapshots")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.snapshots, name)

    def _ref(self, repo: Path, ref: str) -> str | None:
        result = self.git.run(repo, ["rev-parse", "--verify", "--quiet", ref], check=False)
        return result.stdout.strip() if result.exit_code == 0 else None

    def _target(self, repo: Path, branch: str, *, create: bool = True) -> tuple[Path, str, str]:
        if self.git.run(repo, ["check-ref-format", "refs/heads/" + branch], check=False).exit_code:
            raise ValueError("invalid target branch")
        key = hashlib.sha256(branch.encode()).hexdigest()
        common = Path(self._text(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"]))
        folder = common / "skm-integration" / key
        if create:
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        validate_repository_trust(folder)
        if folder.stat().st_mode & 0o077:
            raise ValueError("writer journal must be private")
        return folder, "refs/heads/" + branch, "refs/skm/writer-epochs/" + key

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if path.lstat().st_mode & 0o077:
            raise ValueError("writer journal must be private")
        return cast("dict[str, Any]", json.loads(read_metadata(path)))

    @staticmethod
    def _save(path: Path, value: Mapping[str, Any]) -> None:
        atomic_write(path, canonical(value), mode=0o600, private=True)

    def _metadata(self, repo: Path, filename: str, data: Any, *, parent: str | None = None) -> str:
        blob = self.git.run_bytes(
            repo, ["hash-object", "-w", "--stdin"], stdin=canonical(data)
        ).stdout.strip()
        tree = self.git.run_bytes(
            repo, ["mktree"], stdin=b"100644 blob " + blob + b"\t" + filename.encode() + b"\n"
        ).stdout.strip()
        args = ["commit-tree", tree.decode()]
        if parent:
            args += ["-p", parent]
        return (
            self.git.run_bytes(repo, args, env=author_env(None), stdin=b"skm: writer metadata\n")
            .stdout.decode()
            .strip()
        )

    def _pending(self, repo: Path, folder: Path) -> None:
        for path in sorted(folder.glob("*.json")):
            journal = self._load(path)
            if journal["state"] in {"prepared", "consumed", "unknown", "published"}:
                if not journal.get("reaped") and not self.quiescent(journal["ownership"]):
                    raise error_for(ErrorCode.OUTCOME_UNKNOWN, "previous Git helper has no empty proof")
                journal["reaped"] = True
                self._save(path, journal)
                result = self._reconcile(repo, path, journal)
                if result["state"] == "outcome_unknown":
                    raise error_for(ErrorCode.OUTCOME_UNKNOWN, "previous writer requires reconciliation")

    def _epoch(self, repo: Path, ref: str, generation: int) -> str:
        previous = self._ref(repo, ref)
        if previous:
            data = json.loads(self._text(repo, ["show", previous + ":epoch.json"]))
            if generation < data["generation"]:
                raise error_for(ErrorCode.LEASE_LOST, "stale writer generation")
            if generation == data["generation"]:
                return previous
        current = self._metadata(repo, "epoch.json", {"generation": generation}, parent=previous)
        self.git.run(repo, ["update-ref", ref, current, previous or "0" * len(current)])
        return current

    def prepare_integration(
        self,
        repo: Path | str,
        effect_id: ExternalEffectId,
        inputs: Mapping[str, Any],
        *,
        slot: Mapping[str, Any],
    ) -> GitCommitRequest:
        repo = self.repositories.get(str(inputs["repository_id"]), Path(repo))
        strategy = IntegrationStrategy(inputs.get("strategy", "squash"))
        mode = CommitMode(inputs.get("commit_mode", "final_only"))
        validate_mode(strategy, mode)
        UUID(str(effect_id))
        UUID(str(inputs["repository_id"]))
        for sha in [inputs["baseline_sha"], *(o["head_sha"] for o in inputs["outputs"])]:
            if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) is None:
                raise ValueError("integration requires exact commit object IDs")
        folder, target, epoch_ref = self._target(repo, str(inputs["target_branch"]))
        path = folder / (str(effect_id) + ".json")
        with FileLock(folder / "writer.lock").hold(timeout_seconds=1):
            self._pending(repo, folder)
            if path.exists():
                journal = self._load(path)
                if journal["inputs"] != json.loads(canonical(inputs)):
                    raise error_for(ErrorCode.IDEMPOTENCY_KEY_REUSED, "integration inputs changed")
                return commit_request(journal["request"])
            self._verify_outputs(repo, inputs)
            source = inputs.get("source_repo")
            if source and Path(str(source)) != repo:
                validate_repository_trust(Path(str(source)))
                for output in inputs["outputs"]:
                    self.git.run(
                        repo,
                        [
                            "-c",
                            "protocol.file.allow=always",
                            "fetch",
                            "--no-tags",
                            "--",
                            str(source),
                            str(output["head_sha"]),
                        ],
                    )
            worktrees = self.git.run_bytes(repo, ["worktree", "list", "--porcelain", "-z"]).stdout
            if (b"branch " + target.encode() + b"\0") in worktrees:
                raise error_for(ErrorCode.INTEGRATION_BRANCH_BUSY, "target is checked out")
            epoch = self._epoch(repo, epoch_ref, int(slot["fencing_token"]))
            before = self._text(repo, ["rev-parse", "--verify", target + "^{commit}"])
            scratch = (
                self.root
                / "_integration"
                / str(inputs["repository_id"])
                / folder.name
                / "candidate"
                / str(effect_id)
            )
            scratch.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            validate_repository_trust(scratch, allow_missing=True)
            self.git.run(repo, ["worktree", "add", "--detach", str(scratch), before])
            try:
                commits, tree = self._candidate(repo, scratch, before, effect_id, inputs, mode)
            except BaseException as error:
                try:
                    self.git.run(repo, ["worktree", "remove", "--force", str(scratch)])
                except Exception as cleanup:  # noqa: BLE001 - retain both diagnostics
                    error.add_note(f"candidate cleanup failed: {cleanup}")
                raise
            request = projected_request(inputs, before, commits, tree, epoch, int(slot["fencing_token"]))
            self._save(
                path,
                {
                    "state": "candidate",
                    "inputs": inputs,
                    "request": request_document(request),
                    "effect_id": str(effect_id),
                    "request_digest": effect_digest(effect_id, request),
                    "candidate_path": str(scratch),
                    "reaped": True,
                },
            )
            return request

    def publish_integration(
        self,
        repo: Path | str,
        effect_id: ExternalEffectId,
        request: GitCommitRequest,
        *,
        slot: Mapping[str, Any],
        client: StageClient,
    ) -> GitCommitReceipt:
        repo = self.repositories.get(str(request.repository_id), Path(repo))
        folder, target, epoch_ref = self._target(repo, request.target_branch)
        path = folder / (str(effect_id) + ".json")
        with FileLock(folder / "writer.lock").hold(timeout_seconds=1):
            journal = self._load(path)
            if journal["request"] != request_document(request):
                raise error_for(ErrorCode.IDEMPOTENCY_KEY_REUSED, "immutable Git request changed")
            if journal["state"] == "published":
                if self._reconcile(repo, path, journal)["state"] != "succeeded":
                    raise error_for(ErrorCode.OUTCOME_UNKNOWN, "published refs no longer prove the receipt")
                return self._receipt(repo, request, journal)
            if journal["state"] != "candidate":
                raise error_for(ErrorCode.OUTCOME_UNKNOWN, "publication requires reconciliation")
            self._pending(repo, folder)
            if (
                self._ref(repo, epoch_ref) != request.writer_epoch_sha
                or slot["fencing_token"] != request.slot_fencing_token
            ):
                raise error_for(ErrorCode.LEASE_LOST, "stale writer epoch or slot")
            self._verify_outputs(repo, journal["inputs"])
            raw_ownership = journal["inputs"].get("process_ownership")
            if not isinstance(raw_ownership, dict):
                raise ValueError("precreated Git effect ProcessOwnership required")
            ownership = cast("dict[str, Any]", raw_ownership)
            contained = writer_ownership(ownership, effect_id, journal["inputs"]["attempt_id"])
            digest = effect_digest(effect_id, request)
            report: Any = {"effect_id": str(effect_id), "kind": "git_commit", "request_digest": digest}
            client.record_effect({**report, "phase": "intended", "request": request_document(request)})
            raw = request_document(request)
            receipt_doc = {**report, **raw, "request": raw, "at": self.now().isoformat()}
            receipt_commit = self._metadata(repo, "receipt.json", receipt_doc)
            journal.update(
                state="prepared",
                ownership=ownership,
                receipt_commit=receipt_commit,
                receipt_ref="refs/skm/effects/" + str(effect_id),
                reaped=True,
            )
            self._save(path, journal)
            started = self.monotonic()
            result = client.record_effect({**report, "phase": "executing"})
            admission: Any = result.get("admission")
            if not isinstance(admission, dict) or result.get("cached"):
                raise error_for(ErrorCode.LEASE_LOST, "fresh effect admission required")
            self._consume(
                folder, path, journal, cast("Mapping[str, Any]", admission), started, effect_id, request
            )
            transaction = (
                f"start\nverify {epoch_ref} {request.writer_epoch_sha}\n"
                f"update {target} {request.after_sha} {request.before_sha}\n"
                f"create {journal['receipt_ref']} {receipt_commit}\nprepare\ncommit\n"
            )
            journal.update(state="consumed", reaped=False)  # Successor waits for confirmed reap.
            self._save(path, journal)

            def persist_spawn(identity: ProcessIdentity, pgid: int) -> None:
                journal["process"] = {**asdict(identity), "pgid": pgid}
                self._save(path, journal)

            ref_result = run_ref_transaction(
                self.git, repo, contained, transaction.encode(), persist_spawn=persist_spawn
            )
            journal["reaped"] = True
            journal["state"] = "unknown" if ref_result.exit_code else "published"
            self._save(path, journal)
            if ref_result.exit_code:
                if self._ref(repo, journal["receipt_ref"]) is None and self._ref(repo, target) not in (
                    request.before_sha,
                    request.after_sha,
                ):
                    journal["state"] = "failed"
                    self._save(path, journal)
                    raise error_for(ErrorCode.INTEGRATION_CONFLICT, "target CAS mismatch")
                reconciled = self._reconcile(repo, path, journal)
                code = (
                    ErrorCode.INTEGRATION_CONFLICT
                    if reconciled["state"] == "failed"
                    else ErrorCode.OUTCOME_UNKNOWN
                )
                raise error_for(code, "ref transaction refused; no automatic retry")
            receipt = self._receipt(repo, request, journal)
            client.record_effect(
                {
                    **report,
                    "phase": "result",
                    "result": {"succeeded": True, "git_receipt": json.loads(canonical(asdict(receipt)))},
                }
            )
            return receipt

    def _consume(
        self,
        folder: Path,
        path: Path,
        journal: dict[str, Any],
        admission: Mapping[str, Any],
        started: float,
        effect_id: ExternalEffectId,
        request: GitCommitRequest,
    ) -> None:
        require_admission(
            admission,
            str(effect_id),
            journal["request_digest"],
            started,
            self.monotonic(),
            slot_token=request.slot_fencing_token,
        )
        for previous in folder.glob("*.json"):
            if self._load(previous).get("admission_id") == admission["admission_id"]:
                raise error_for(ErrorCode.LEASE_LOST, "writer admission already consumed")
        journal["admission_id"] = admission["admission_id"]
        self._save(path, journal)

    def _receipt(self, repo: Path, request: GitCommitRequest, journal: Mapping[str, Any]) -> GitCommitReceipt:
        data = json.loads(self._text(repo, ["show", str(journal["receipt_commit"]) + ":receipt.json"]))
        return receipt_from_document(request, journal, data)

    def _reconcile(
        self, repo: Path, path: Path, journal: dict[str, Any], *, persist: bool = True
    ) -> dict[str, Any]:
        request = journal["request"]
        if not journal.get("reaped"):
            return {"state": "outcome_unknown", "effect_id": journal["effect_id"]}
        target = self._ref(repo, "refs/heads/" + request["target_branch"])
        receipt = self._ref(repo, "refs/skm/effects/" + journal["effect_id"])
        state = "outcome_unknown"
        if receipt == journal.get("receipt_commit") and receipt and target:
            doc = json.loads(self._text(repo, ["show", receipt + ":receipt.json"]))
            tree = self._text(repo, ["rev-parse", request["after_sha"] + "^{tree}"])
            chain = self._text(
                repo, ["rev-list", "--reverse", request["before_sha"] + ".." + request["after_sha"]]
            ).splitlines()
            if (
                local_receipt_matches(journal, doc, tree, chain)
                and self._identities(repo, journal)
                and self.git.run(
                    repo, ["merge-base", "--is-ancestor", request["after_sha"], target], check=False
                ).exit_code
                == 0
            ):
                state = "succeeded"
        elif target == request["before_sha"] and receipt is None:
            state = "failed"
        journal["state"] = {"succeeded": "published", "failed": "failed"}.get(state, "unknown")
        if persist:
            self._save(path, journal)
        receipt_doc = (
            json.loads(canonical(asdict(self._receipt(repo, commit_request(request), journal))))
            if state == "succeeded"
            else None
        )
        return reconciliation_observation(journal, state, self.now().isoformat(), receipt_doc)

    def _identities(self, repo: Path, journal: Any) -> bool:
        return local_identities_match(
            journal,
            [
                self._text(repo, ["show", "-s", "--format=%B", sha])
                for sha in journal["request"]["commit_shas"]
            ],
        )

    def reconcile_integration(
        self, repo: Path | str, effect_id: ExternalEffectId, request: GitCommitRequest
    ) -> Any:
        repo = self.repositories.get(str(request.repository_id), Path(repo))
        try:
            folder, _, _ = self._target(repo, request.target_branch, create=False)
        except (OSError, ValueError):
            return {"state": "outcome_unknown", "effect_id": str(effect_id)}
        path = folder / (str(effect_id) + ".json")
        if not path.exists():
            return {"state": "outcome_unknown", "effect_id": str(effect_id)}
        with FileLock(folder / "writer.lock").hold(timeout_seconds=1):
            journal = self._load(path)
            if journal["request"] != request_document(request):
                raise error_for(ErrorCode.IDEMPOTENCY_KEY_REUSED, "reconcile request changed")
            if not journal.get("reaped") and self.quiescent(journal["ownership"]):
                journal["reaped"] = True
            return self._reconcile(repo, path, journal, persist=False)

    def _observation(self, effect: str, digest: str, state: str, ref: str, reason: Any = None) -> Any:
        return observation_receipt(effect, digest, state, ref, reason, self.now().isoformat())

    def _push_remote(self, repo: Path, request: Any) -> tuple[str, list[str]]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", request["remote"]):
            raise ValueError("an exact configured remote name is required")
        urls = self._text(repo, ["remote", "get-url", "--push", "--all", request["remote"]]).splitlines()
        if (
            len(urls) != 1
            or self.git.run(
                repo, ["config", "--get-regexp", r"^url\..*\.(insteadof|pushinsteadof)$"], check=False
            ).stdout
        ):
            raise ValueError("ambiguous or rewritten push endpoint")
        url, endpoint = urls[0], request["endpoint"]
        parsed = urlsplit(url)
        remote_identity = remote_endpoint(url)
        actual = (
            {"transport": "file", "hostname": "", "effective_port": 1, "repository_path": parsed.path}
            if parsed.scheme == "file" and not parsed.netloc
            else remote_identity.to_json()
            if remote_identity is not None
            else None
        )
        if (
            actual != endpoint
            or request["binding_identity"]["locator_digest"]
            != "sha256:" + hashlib.sha256(str(repo.resolve()).encode()).hexdigest()
        ):
            raise error_for(ErrorCode.APPROVAL_MISMATCH, "push endpoint or checkout identity changed")
        if self.git.run(repo, ["check-ref-format", request["target_ref"]], check=False).exit_code:
            raise ValueError("invalid push target ref")
        return url, ["-c", "protocol." + str(endpoint["transport"]) + ".allow=always"]

    def _remote_tip(self, repo: Path, request: Any) -> str:
        url, config = self._push_remote(repo, request)
        result = self.git.run(
            repo, [*config, "ls-remote", "--refs", "--", url, request["target_ref"]], timeout_s=30
        )
        rows = [line.split() for line in result.stdout.splitlines()]
        if len(rows) > 1 or (rows and rows[0][1] != request["target_ref"]):
            raise ValueError("ambiguous remote lookup")
        return rows[0][0] if rows else "0" * len(request["after_sha"])

    def push_external(
        self, repo: Path, effect: str, request: Any, digest: str, client: Any, ownership: Any
    ) -> Any:
        """One SHA/ref CAS, gated by durable ownership and a fresh server admission."""
        UUID(effect)
        repo = self.repositories.get(str(request["repository_id"]), repo)
        folder, _, _ = self._target(repo, "_external")
        path = folder / (effect + ".json")
        with FileLock(folder / "writer.lock").hold(timeout_seconds=1):
            if path.exists():
                raise error_for(
                    ErrorCode.OUTCOME_UNKNOWN, "push already admitted; reconcile before any retry"
                )
            if (
                "sha256:" + hashlib.sha256(canonical({"kind": "git_push", "args": request})).hexdigest()
                != digest
            ):
                raise error_for(ErrorCode.APPROVAL_MISMATCH, "push request digest changed")
            url, config = self._push_remote(repo, request)
            before, after = request["before_sha"], request["after_sha"]
            push_args = push_arguments(request, url, config)
            if self._remote_tip(repo, request) != before or (
                set(before) != {"0"}
                and self.git.run(repo, ["merge-base", "--is-ancestor", before, after], check=False).exit_code
            ):
                raise error_for(ErrorCode.INTEGRATION_CONFLICT, "push preconditions changed")
            writer_ownership(ownership, UUID(effect), ownership["owner"]["attempt_id"])
            journal = {
                "effect_id": effect,
                "request": request,
                "request_digest": digest,
                "ownership": ownership,
                "reaped": False,
                "state": "prepared",
            }
            self._save(path, journal)
            started = self.monotonic()
            report = {"effect_id": effect, "kind": "git_push", "request_digest": digest}
            result = client.record_effect({**report, "phase": "executing"})
            admission: Any = result.get("admission") or {}
            require_admission(
                admission, effect, digest, started, self.monotonic(), cached=bool(result.get("cached"))
            )
            journal["admission_id"] = admission["admission_id"]
            self._save(path, journal)

            def spawned(identity: ProcessIdentity, pgid: int) -> None:
                journal["process"] = {**asdict(identity), "pgid": pgid}
                self._save(path, journal)

            actual = run_owned_git(
                self.git,
                repo,
                push_args,
                persist_spawn=spawned,
                before_release=lambda: require_admission(
                    admission, effect, digest, started, self.monotonic()
                ),
            )
            journal.update(
                reaped=True,
                state="observed",
                rejected=push_rejected(actual.exit_code, actual.stdout, False, request["target_ref"]),
            )
            self._save(path, journal)
            if actual.exit_code:
                raise error_for(ErrorCode.OUTCOME_UNKNOWN, "push requires exact remote reconciliation")
            receipt = self._observation(effect, digest, "succeeded", after)
            client.record_effect(result_report(report, receipt))
            return receipt

    def inspect_effect(self, repo: Path, effect: Any, binding: Any, client: Any) -> Any:
        """Admin lookup returns explicit cleanup proof, independent of its effect outcome."""
        return inspect_effect(self, repo, effect, binding, client)

    def inspect_push(self, repo: Path, effect: str, request: Any, digest: str) -> Any:
        UUID(effect)
        repo = self.repositories.get(str(request["repository_id"]), repo)
        unknown = {"state": "outcome_unknown", "effect_id": effect, "request_digest": digest}
        try:
            folder, _, _ = self._target(repo, "_external", create=False)
            with FileLock(folder / "writer.lock").hold(timeout_seconds=1):
                journal = self._load(folder / (effect + ".json"))
                if journal["request"] != request or journal["request_digest"] != digest:
                    return unknown
                if not journal["reaped"] and not self.quiescent(journal["ownership"]):
                    return unknown
                tip = self._remote_tip(repo, request)
                state, reason = "outcome_unknown", None
                if tip == request["after_sha"]:
                    state = "succeeded"
                elif tip == request["before_sha"] and (
                    journal.get("rejected") or not journal.get("admission_id")
                ):
                    state, reason = "failed", "EFFECT_ABSENT"
                elif (
                    self.git.run(
                        repo, ["merge-base", "--is-ancestor", request["after_sha"], tip], check=False
                    ).exit_code
                    == 0
                ):
                    state, reason = "succeeded", "REMOTE_DESCENDANT"
                if state == "outcome_unknown":
                    return unknown
                return {
                    **unknown,
                    "state": state,
                    "reason_code": reason,
                    "receipt": self._observation(effect, digest, state, tip, reason),
                }
        except (OSError, ValueError, SkmError):
            return unknown


def git_integration_vcs(
    git: GitRunner,
    *,
    worktrees_root: Path,
    now: Callable[[], datetime],
    monotonic: Callable[[], float],
    repositories: Mapping[str, Path] | None = None,
    quiescent: Callable[[Mapping[str, Any]], bool] = lambda _: False,
) -> Vcs:
    writer = GitIntegrator(
        git,
        worktrees_root=worktrees_root,
        now=now,
        monotonic=monotonic,
        repositories=repositories,
        quiescent=quiescent,
    )
    return cast("Vcs", writer)
