"""Immutable, content-addressed executor input snapshots for Layout v2 plans."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from task import plan_layout


TERMINAL_MARKER = "plan-context-terminal-v1"
_ROLES = ("plan-core", "phase-context", "item-spec", "bundle", "item-state")
_ITEM = re.compile(r"^P\d+\.\d+$")


class PlanContextError(ValueError):
    """A five-carrier executor context is incomplete or changed."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class SnapshotMember:
    role: str
    path: Path
    content: bytes
    sha256: str


@dataclass(frozen=True)
class PlanContextSnapshot:
    """One in-memory snapshot; chunks never source their content from the worktree."""

    plan_dir: Path
    item_id: str
    members: tuple[SnapshotMember, ...]
    snapshot_sha256: str

    def receipt(self) -> dict:
        return {
            "schema_version": "plan-context-receipt/v1",
            "item_id": self.item_id,
            "snapshot_sha256": self.snapshot_sha256,
            "members": [
                {"role": member.role,
                 "path": member.path.relative_to(self.plan_dir).as_posix(),
                 "sha256": member.sha256,
                 "bytes": len(member.content)}
                for member in self.members
            ],
        }

    def _member(self, role: str) -> SnapshotMember:
        for member in self.members:
            if member.role == role:
                return member
        raise PlanContextError("PLAN_CONTEXT_TRUNCATED", f"неизвестный носитель {role!r}")

    def assert_live_integrity(self) -> None:
        """Refuse continuation if the live source stopped matching the snapshot."""
        for member in self.members:
            try:
                current = member.path.read_bytes()
            except OSError as exc:
                raise PlanContextError(
                    "PLAN_CONTEXT_DIGEST_MISMATCH",
                    f"носитель изменился или не читается: {member.path}") from exc
            if sha256(current).hexdigest() != member.sha256:
                raise PlanContextError(
                    "PLAN_CONTEXT_DIGEST_MISMATCH",
                    f"носитель изменился после snapshot: {member.path}")

    def chunk(self, role: str, *, offset: int, limit: int) -> dict:
        """Return a byte-addressed chunk plus a terminal proof when it is complete."""
        member = self._member(role)
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise PlanContextError("PLAN_CONTEXT_TRUNCATED", "offset должен быть неотрицательным int")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise PlanContextError("PLAN_CONTEXT_TRUNCATED", "limit должен быть положительным int")
        if offset > len(member.content):
            raise PlanContextError("PLAN_CONTEXT_TRUNCATED", "offset выходит за пределы snapshot")
        self.assert_live_integrity()
        next_offset = min(offset + limit, len(member.content))
        complete = next_offset == len(member.content)
        result = {
            "schema_version": "plan-context-chunk/v1",
            "role": role,
            "path": member.path.relative_to(self.plan_dir).as_posix(),
            "snapshot_sha256": self.snapshot_sha256,
            "member_sha256": member.sha256,
            "offset": offset,
            "next_offset": next_offset,
            "complete": complete,
            "content": member.content[offset:next_offset],
        }
        if complete:
            result["terminal_marker"] = TERMINAL_MARKER
        return result


def _snapshot_sha(members: tuple[SnapshotMember, ...], plan_dir: Path) -> str:
    digest = sha256()
    for member in members:
        digest.update(member.role.encode("utf-8"))
        digest.update(b"\0")
        digest.update(member.path.relative_to(plan_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(member.sha256.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _paths(plan_dir: Path, item_id: str) -> tuple[tuple[str, Path], ...]:
    if plan_layout.layout_version(plan_dir) != "v2":
        raise PlanContextError("PLAN_LAYOUT_V1_RETIRED", "исполняется только Layout v2")
    if not _ITEM.fullmatch(item_id):
        raise PlanContextError("PLAN_CONTEXT_TRUNCATED", "item должен иметь форму Pn.m")
    phase_id = item_id.split(".")[0]
    return (
        ("plan-core", plan_layout.plan_core_path(plan_dir)),
        ("phase-context", plan_layout.carrier_path(plan_dir, "phase-index", phase_id=phase_id)),
        ("item-spec", plan_layout.carrier_path(plan_dir, "item-spec", item_id=item_id)),
        ("bundle", plan_layout.carrier_path(plan_dir, "bundle", item_id=item_id)),
        ("item-state", plan_layout.carrier_path(plan_dir, "item-state", item_id=item_id)),
    )


def capture(plan_dir, item_id: str) -> PlanContextSnapshot:
    """Capture every executor carrier before exposing a byte of any one carrier."""
    root = Path(plan_dir)
    if _ITEM.fullmatch(item_id) and plan_layout.layout_version(root) == "v2":
        from task import plan_recovery
        plan_recovery.validate_request(root, item_id)
    members = []
    for role, path in _paths(root, item_id):
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise PlanContextError(
                "PLAN_CONTEXT_TRUNCATED", f"носитель не читается: {path}") from exc
        members.append(SnapshotMember(role, path, content, sha256(content).hexdigest()))
    frozen = tuple(members)
    return PlanContextSnapshot(root, item_id, frozen, _snapshot_sha(frozen, root))


def validate_chunks(snapshot: PlanContextSnapshot, chunks: list[dict]) -> None:
    """Prove a complete contiguous stream for every member before journal mutation."""
    by_role = {role: [] for role in _ROLES}
    for chunk in chunks:
        if not isinstance(chunk, dict) or chunk.get("snapshot_sha256") != snapshot.snapshot_sha256:
            raise PlanContextError("PLAN_CONTEXT_TRUNCATED", "chunk не связан с snapshot")
        role = chunk.get("role")
        if role not in by_role:
            raise PlanContextError("PLAN_CONTEXT_TRUNCATED", "chunk содержит неизвестный носитель")
        by_role[role].append(chunk)
    for role, expected in by_role.items():
        if not expected:
            raise PlanContextError("PLAN_CONTEXT_TRUNCATED", f"нет chunk для {role}")
        cursor = 0
        for chunk in expected:
            content = chunk.get("content")
            if chunk.get("offset") != cursor or not isinstance(content, bytes):
                raise PlanContextError("PLAN_CONTEXT_TRUNCATED", f"gap или transport truncation в {role}")
            cursor = chunk.get("next_offset")
        member = snapshot._member(role)
        terminal = expected[-1]
        if (cursor != len(member.content) or not terminal.get("complete")
                or terminal.get("terminal_marker") != TERMINAL_MARKER):
            raise PlanContextError("PLAN_CONTEXT_TRUNCATED", f"нет terminal marker для {role}")
    snapshot.assert_live_integrity()
