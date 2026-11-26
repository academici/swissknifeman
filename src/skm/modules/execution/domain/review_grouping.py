"""Group review selection on ``start_run`` (execution §5.9; port of ``review_strategy.py`` ``rules()``).

With ``review_grouping = none`` (default) no group review exists. With ``groups``, neighbouring tasks (by
position) whose write scopes work in common folders share a group of at most ``MAX_GROUP`` tasks. A task
whose scope touches ``solo_paths`` or whose route is of class ``frontier`` is reviewed alone; a waived task
is in no group; all waived or a single task gives ``none``. A group review adds coverage and never
replaces a task's own required review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from skm.kernel.ids import TaskId
from skm.modules.execution.domain.task import ReviewMode, TaskKind

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from skm.modules.execution.domain.contracts import ExecutionPolicy
    from skm.modules.execution.domain.task import PathPattern, Task

__all__ = ["EFFORT_MARKERS", "MAX_GROUP", "ReviewGrouping", "choose_grouping"]

MAX_GROUP: Final = 4
EFFORT_MARKERS: Final = ("security", "secret", "permission", "auth", "redact", "sandbox", "guard")
_GROUPED_KINDS: Final = frozenset({TaskKind.UNIT, TaskKind.ITEM})
_GLOB: Final = frozenset("*?[{")
_TOP_DEPTH: Final = 3


@dataclass(frozen=True, slots=True)
class ReviewGrouping:
    mode: Literal["none", "groups"]
    groups: tuple[tuple[TaskId, ...], ...]
    reviewer_effort: Literal["medium", "high"]
    reason: str


def choose_grouping(
    tasks: Sequence[Task],
    policy: ExecutionPolicy,
    *,
    solo_paths: Sequence[str] = (),
    frontier: Collection[TaskId] = (),
) -> ReviewGrouping:
    """``policy["review_grouping"]``; ``solo_paths`` is ``execution.review.solo_paths``; ``frontier`` are
    the tasks routed to a ``frontier`` class."""
    if policy.get("review_grouping", "none") != "groups":
        return ReviewGrouping("none", (), "medium", "grouping is off")
    candidates = sorted(
        (task for task in tasks if task.kind in _GROUPED_KINDS),
        key=lambda task: (task.position, str(task.id)),
    )
    reviewed = [task for task in candidates if task.review_mode is not ReviewMode.WAIVED]
    if not reviewed:
        return ReviewGrouping("none", (), "medium", "every task is waived")
    if len(reviewed) == 1:
        return ReviewGrouping("none", (), "medium", "a single task")
    groups: list[list[Task]] = []
    for task in reviewed:
        alone = _solo(task, solo_paths, frontier)
        current = groups[-1] if groups else None
        if (
            current is not None
            and not alone
            and not _solo(current[-1], solo_paths, frontier)
            and len(current) < MAX_GROUP
            and _shares_folder(current, task)
        ):
            current.append(task)
        else:
            groups.append([task])
    effort: Literal["medium", "high"] = "high" if any(_marked(task) for task in reviewed) else "medium"
    sizes = ", ".join(str(len(group)) for group in groups)
    return ReviewGrouping(
        "groups",
        tuple(tuple(task.id for task in group) for group in groups),
        effort,
        f"{len(groups)} groups by shared folders (sizes {sizes})",
    )


def _solo(task: Task, solo_paths: Sequence[str], frontier: Collection[TaskId]) -> bool:
    if task.id in frontier:
        return True
    scope = task.declared_write_scope or ()
    return any(_may_overlap(pattern.pattern, glob) for pattern in scope for glob in solo_paths)


def _may_overlap(left: str, right: str) -> bool:
    """Scopes are disjoint only when their fixed path components disagree before any glob.

    A wildcard may cover a protected descendant (``src/**`` vs ``src/auth/**``). Treat an uncertain
    overlap conservatively, including character classes and braces, without importing planning's
    private scope algebra. The configured solo paths apply in every mount.
    """
    prefixes: list[list[str]] = []
    for pattern in (left, right):
        fixed: list[str] = []
        for part in pattern.strip().replace("\\", "/").removeprefix("./").split("/"):
            if _GLOB & set(part):
                break
            if part:
                fixed.append(part)
        prefixes.append(fixed)
    return all(a == b for a, b in zip(*prefixes, strict=False))


def _shares_folder(group: Sequence[Task], task: Task) -> bool:
    tops = {top for member in group for top in _tops(member.declared_write_scope)}
    return any(_related(left, right) for left in tops for right in _tops(task.declared_write_scope))


def _tops(scope: tuple[PathPattern, ...] | None) -> set[tuple[str, tuple[str, ...]]]:
    """Fixed prefix of each pattern up to three folders, without its glob part; a file gives its folder.

    An undeclared scope (``None``) has no folders and joins no group.
    """
    found: set[tuple[str, tuple[str, ...]]] = set()
    for pattern in scope or ():
        parts = [part for part in pattern.pattern.strip("/").split("/") if part]
        fixed: list[str] = []
        for part in parts:
            if _GLOB & set(part):
                break
            fixed.append(part)
        if len(fixed) == len(parts) and fixed:
            fixed = fixed[:-1]  # a literal path names a file: its folder
        found.add((pattern.mount, tuple(fixed[:_TOP_DEPTH])))
    return found


def _related(left: tuple[str, tuple[str, ...]], right: tuple[str, tuple[str, ...]]) -> bool:
    if left[0] != right[0]:
        return False
    shorter, longer = sorted((left[1], right[1]), key=len)
    return longer[: len(shorter)] == shorter


def _marked(task: Task) -> bool:
    words = " ".join([task.display_key, *(pattern.pattern for pattern in task.declared_write_scope or ())])
    lowered = words.casefold()
    return any(marker in lowered for marker in EFFORT_MARKERS)
