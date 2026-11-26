"""Range bounds from immutable integration effects; Git object proofs belong to the host (§5.18)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Never, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.external_effect import EffectKind, EffectState
from skm.modules.execution.domain.readiness import canonical_digest
from skm.modules.execution.domain.task import TaskStatus

if TYPE_CHECKING:
    from skm.kernel.ids import TaskId
    from skm.modules.execution.domain.external_effect import ExternalEffect
    from skm.modules.execution.domain.output import Output
    from skm.modules.execution.domain.task import Task


@dataclass(frozen=True, slots=True)
class RangeBound:
    repository_id: str
    base: str
    head: str
    tree_sha: str
    effects: tuple[ExternalEffect, ...]

    def to_json(self) -> JsonObject:
        return {
            "repository_id": self.repository_id,
            "base": self.base,
            "head": self.head,
            "tree_sha": self.tree_sha,
            "effects": [
                {
                    "effect_id": str(e.id),
                    "request_digest": e.request_digest,
                    "request": e.request,
                    "receipt": e.receipt,
                }
                for e in self.effects
            ],
        }


def mismatch(message: str) -> Never:
    raise error_for(ErrorCode.CHECKOUT_MISMATCH, message)


def range_bounds(  # noqa: PLR0912, PLR0915 -- receipt integrity and chain checks
    members: Sequence[Task],
    outputs: Sequence[Output],
    effects: Sequence[ExternalEffect],
    *,
    heads: Mapping[str, str] | None = None,
    carried_sources: Mapping[TaskId, Task] | None = None,
) -> tuple[RangeBound, ...]:
    """Prove membership, output binding and the before/after chain, including intervening effects.

    Never substitute a manifest base or a trailer for an absent receipt. The host must additionally
    verify each admitted candidate's tree/parents and Git ancestry before sealing the range output.
    """
    if not members:
        mismatch("a range requires integration members")
    run_ids = {m.run_id for m in members}
    workspace_ids = {m.workspace_id for m in members}
    if len(run_ids) != 1 or len(workspace_ids) != 1:
        mismatch("range members belong to one run and workspace")
    accepted = {m.id: m for m in members if m.status is TaskStatus.ACCEPTED}
    for target_id, source in (carried_sources or {}).items():
        target = accepted.get(target_id)
        if (
            target is None
            or target.accepted_output_id is not None
            or source.status is not TaskStatus.ACCEPTED
            or source.workspace_id != target.workspace_id
            or source.spec_entity_id != target.spec_entity_id
            or source.run_id == target.run_id
        ):
            mismatch("carry-forward does not bind an accepted member to its source")
        accepted[target_id] = source
        run_ids.add(source.run_id)
    output_by_id = {o.id: o for o in outputs}
    valid: list[ExternalEffect] = []
    for effect in effects:
        if effect.run_id not in run_ids or effect.workspace_id not in workspace_ids:
            continue
        if effect.kind is not EffectKind.GIT_COMMIT or effect.state is not EffectState.SUCCEEDED:
            continue
        request, receipt = effect.request, effect.receipt
        if receipt is None:
            mismatch("successful integration effect has no receipt")
        fields = (
            "before_sha",
            "after_sha",
            "tree_sha",
            "target_branch",
            "output_ids",
            "commit_shas",
            "writer_epoch_sha",
        )
        if (
            any(key not in request or receipt.get(key) != request[key] for key in fields)
            or receipt.get("ref") != request["after_sha"]
            or receipt.get("request_digest") != effect.request_digest
            or not receipt.get("receipt_ref")
            or not receipt.get("receipt_commit_sha")
            or canonical_digest({"effect_id": str(effect.id), "kind": effect.kind.value, "request": request})
            != effect.request_digest
            or (not receipt["commit_shas"] and receipt["before_sha"] != receipt["after_sha"])
        ):
            mismatch("integration receipt differs from its admitted effect")
        valid.append(effect)
    wanted: dict[str, list[ExternalEffect]] = {}
    distinct_sources = {member.id: member for member in accepted.values()}
    for member in distinct_sources.values():
        output = None if member.accepted_output_id is None else output_by_id.get(member.accepted_output_id)
        if output is None or (output.task_id, output.run_id, output.attempt_id) != (
            member.id,
            member.run_id,
            member.accepted_attempt_id,
        ):
            mismatch("range member has no accepted output proof")
        for mount in output.manifest.mounts:
            matches = [
                e
                for e in valid
                if e.task_id == member.id
                and e.attempt_id == member.accepted_attempt_id
                and str(e.request.get("repository_id")) == str(mount.repository_id)
                and isinstance(e.request.get("output_ids"), list)
                and str(output.id) in cast("list[object]", e.request["output_ids"])
            ]
            if len(matches) != 1:
                mismatch("range member has no unique immutable integration receipt")
            effect = matches[0]
            ids, digests = effect.request["output_ids"], effect.request.get("output_digests")
            if not isinstance(ids, list) or not isinstance(digests, list) or len(ids) != len(digests):
                mismatch("effect output digests are missing")
            if digests[ids.index(str(output.id))] != output.manifest_digest:
                mismatch("effect does not bind the accepted output digest")
            wanted.setdefault(str(mount.repository_id), []).append(effect)
    if not wanted:
        mismatch("no integrated member proves the range bounds")
    result: list[RangeBound] = []
    for repo_id, selected in sorted(wanted.items()):
        chain = sorted(
            (e for e in valid if str(e.request.get("repository_id")) == repo_id),
            key=lambda e: (e.updated_at, str(e.id)),
        )
        start = min(chain.index(e) for e in selected)
        chain = chain[start:]
        if heads is not None:
            target = heads.get(repo_id)
            ends = [i for i, e in enumerate(chain) if e.request["after_sha"] == target]
            if not ends:
                mismatch("pinned range head has no integration receipt")
            chain = chain[: max(ends) + 1]
        if not all(e in chain for e in selected):
            mismatch("range head precedes an accepted member")
        branch = chain[0].request["target_branch"]
        for left, right in pairwise(chain):
            if (
                left.request["after_sha"] != right.request["before_sha"]
                or right.request["target_branch"] != branch
            ):
                mismatch("integration receipt chain has a gap or changes target")
        base, head = str(chain[0].request["before_sha"]), str(chain[-1].request["after_sha"])
        if all(e.request["before_sha"] == e.request["after_sha"] for e in selected):
            # Other integrations may advance the pinned head, but no-op members add no range.
            base = head
        result.append(RangeBound(repo_id, base, head, str(chain[-1].request["tree_sha"]), tuple(chain)))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class GitObject:
    tree: str
    parents: tuple[str, ...]


def verify_range_objects(bounds: Sequence[RangeBound], objects: Mapping[str, GitObject]) -> None:
    """Verify host-observed candidate trees/parents and ancestry before any range is sealed.

    ``objects`` is a bounded snapshot read by the host's VCS gateway from the pinned commits. Missing
    Git facts fail closed; neither an effect receipt nor a matching trailer proves object ancestry.
    """
    for bound in bounds:
        for effect in bound.effects:
            before, after = str(effect.request["before_sha"]), str(effect.request["after_sha"])
            candidate = objects.get(after)
            if candidate is None or candidate.tree != effect.request["tree_sha"]:
                mismatch("range candidate tree is missing or differs from its receipt")
            commits = effect.request["commit_shas"]
            if not isinstance(commits, list):
                mismatch("range candidate commit chain is missing")
            previous = before
            for sha in commits:
                commit = objects.get(str(sha))
                if commit is None or previous not in commit.parents:
                    mismatch("range candidate parents differ from the receipt chain")
                previous = str(sha)
            if previous != after or not _ancestor(before, after, objects):
                mismatch("range receipt does not prove candidate ancestry")
        if not _ancestor(bound.base, bound.head, objects):
            mismatch("range base is not an ancestor of pinned integration head")


def _ancestor(base: str, head: str, objects: Mapping[str, GitObject]) -> bool:
    seen: set[str] = set()
    pending = [head]
    while pending:
        sha = pending.pop()
        if sha == base:
            return True
        if sha in seen:
            continue
        seen.add(sha)
        commit = objects.get(sha)
        if commit is not None:
            pending.extend(commit.parents)
    return False
