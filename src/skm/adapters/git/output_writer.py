"""Trusted host binding of immutable worker snapshots and server-issued output identities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

from .host_inputs import CheckoutDescriptor
from .runner import GitRunner

__all__ = ["PreSealSnapshot", "verify_sealed_output"]


def _oid(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        raise ValueError("an exact Git object ID is required")
    return value


def _refs(
    git: GitRunner, checkout: CheckoutDescriptor, *, verify: dict[str, str], create: dict[str, str]
) -> None:
    """Create all refs or verify an exact replay, including the preconditions, under Git's ref locks."""
    checkout.verify()
    if any(
        not re.fullmatch(r"refs/skm/(outputs|output-bindings|sealed)/[0-9a-f-]{36}/[1-9][0-9]*", ref)
        for ref in (*verify, *create)
    ):
        raise ValueError("invalid immutable output ref")
    args = ["-c", "core.fsync=all", f"--git-dir={checkout.git_dir}", "update-ref", "--no-deref", "--stdin"]
    for creating in (True, False) if create else (False,):
        commands = [f"verify {ref} {oid}" for ref, oid in verify.items()]
        commands.extend(f"{'create' if creating else 'verify'} {ref} {oid}" for ref, oid in create.items())
        result = git.run_bytes(
            checkout.root,
            args,
            stdin=("\n".join(["start", *commands, "prepare", "commit", ""])).encode(),
            check=False,
        )
        if result.exit_code == 0:
            return
    raise error_for(ErrorCode.CHECKOUT_BUSY, "immutable output ref or writer binding changed")


def _blob(git: GitRunner, checkout: CheckoutDescriptor, value: dict[str, Any], *, write: bool) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return (
        git.run_bytes(
            checkout.root,
            [
                "-c",
                "core.fsync=all",
                f"--git-dir={checkout.git_dir}",
                "hash-object",
                *(["-w"] if write else []),
                "--stdin",
            ],
            stdin=raw,
        )
        .stdout.decode("ascii")
        .strip()
    )


@dataclass(frozen=True, slots=True)
class PreSealSnapshot:
    attempt_id: UUID
    step_id: UUID
    output_no: int
    mount: str
    checkout: CheckoutDescriptor
    fence: int

    def __post_init__(self) -> None:
        if self.output_no < 1 or self.fence < 1 or not self.mount:
            raise ValueError("snapshot requires a positive sequence, active fence and mount")

    @property
    def ref(self) -> str:
        return f"refs/skm/outputs/{self.attempt_id}/{self.output_no}"

    @property
    def binding_ref(self) -> str:
        return f"refs/skm/output-bindings/{self.attempt_id}/{self.output_no}"

    @property
    def sealed_ref(self) -> str:
        return f"refs/skm/sealed/{self.attempt_id}/{self.output_no}"

    def binding_oid(self, git: GitRunner, head: str, *, write: bool = False) -> str:
        self.checkout.verify()
        return _blob(git, self.checkout, _binding_document(self, head), write=write)

    def write(self, git: GitRunner, head: str) -> None:
        binding = self.binding_oid(git, head, write=True)
        _refs(git, self.checkout, verify={}, create={self.ref: head, self.binding_ref: binding})

    def verify(self, git: GitRunner, head: str) -> None:
        binding = self.binding_oid(git, head)
        _refs(git, self.checkout, verify={self.ref: head, self.binding_ref: binding}, create={})

    def confirm(self, git: GitRunner, head: str, *, output_id: UUID, manifest_digest: str) -> None:
        binding = self.binding_oid(git, head)
        sealed = _blob(
            git,
            self.checkout,
            {"output_id": str(output_id), "manifest_digest": manifest_digest, "binding": binding},
            write=True,
        )
        _refs(
            git,
            self.checkout,
            verify={self.ref: head, self.binding_ref: binding},
            create={self.sealed_ref: sealed},
        )


def _binding_document(snapshot: PreSealSnapshot, head: str) -> dict[str, Any]:
    return {
        "attempt_id": str(snapshot.attempt_id),
        "step_id": str(snapshot.step_id),
        "output_no": snapshot.output_no,
        "mount": snapshot.mount,
        "gitdir": snapshot.checkout.git_dir,
        "checkout": snapshot.checkout.to_json(),
        "ref": snapshot.ref,
        "expected_old": "0" * len(_oid(head)),
        "fence": snapshot.fence,
        "head": head,
    }


def verify_sealed_output(
    git: GitRunner,
    checkout: CheckoutDescriptor,
    *,
    attempt_id: UUID,
    output_no: int,
    mount: str,
    output_id: UUID,
    head: str,
    manifest_digest: str,
) -> None:
    """Match the accepted server identity and SHA to the writer's receipt on this mount."""
    binding_ref = f"refs/skm/output-bindings/{attempt_id}/{output_no}"
    args = [f"--git-dir={checkout.git_dir}"]
    checkout.verify()
    raw = git.run_bytes(checkout.root, [*args, "cat-file", "blob", binding_ref], check=False)
    if raw.exit_code:
        raise error_for(ErrorCode.INVALID_REFERENCE, "sealed output has no pre-seal writer binding")
    try:
        parsed: object = json.loads(raw.stdout)
        if not isinstance(parsed, dict):
            raise ValueError("binding must be a JSON object")
        stored = cast("dict[str, object]", parsed)
        step_id, fence = stored["step_id"], stored["fence"]
        if not isinstance(step_id, str) or type(fence) is not int:
            raise ValueError("binding requires a step UUID and an integer fence")
        snapshot = PreSealSnapshot(attempt_id, UUID(step_id), output_no, mount, checkout, fence)
    except (KeyError, ValueError, RecursionError) as error:
        raise error_for(ErrorCode.INVALID_REFERENCE, "malformed pre-seal writer binding") from error
    document = _binding_document(snapshot, head)
    stored_checkout = stored.get("checkout")
    if (
        not document.keys() <= stored.keys()
        or not isinstance(stored_checkout, dict)
        or not document["checkout"].keys() <= cast("dict[str, object]", stored_checkout).keys()
    ):
        raise error_for(ErrorCode.INVALID_REFERENCE, "incomplete pre-seal writer binding")
    checkout.verify()
    binding = _blob(git, checkout, document, write=False)
    sealed = _blob(
        git,
        checkout,
        {"output_id": str(output_id), "manifest_digest": manifest_digest, "binding": binding},
        write=False,
    )
    _refs(
        git,
        checkout,
        verify={snapshot.ref: head, binding_ref: binding, snapshot.sealed_ref: sealed},
        create={},
    )
