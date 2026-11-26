"""Attach decision: marker, then remotes, then a new repository (workspace §5.2).

``decide_attach`` is a pure function of the facts a host op observed plus what the server found in its own
tables. It writes nothing and looks at no file system. Port of the *order* of
``workspace/projects.py::_attach_locked`` (REWRITE-KEEP-IDEA): the marker is only a hint, a remote match is
only a candidate, and when the facts do not point to exactly one repository the decision is a refusal —
never "the first one"."""

from dataclasses import dataclass
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.outcomes import Diagnostic, Severity

from .checkout_binding import ObservedCheckout
from .mount import MountName
from .remote_url import NormalizedRemote

__all__ = [
    "MARKER_FOREIGN_INSTANCE",
    "MARKER_STALE",
    "AttachDecision",
    "AttachInput",
    "AttachOutcome",
    "CreateRepository",
    "MarkerTarget",
    "Refuse",
    "RepositoryMatchView",
    "UseExistingRepository",
    "UseMarker",
    "decide_attach",
    "decide_attach_with_diagnostics",
]

MARKER_FOREIGN_INSTANCE = "MARKER_FOREIGN_INSTANCE"
MARKER_STALE = "MARKER_STALE"


@dataclass(frozen=True, slots=True)
class UseMarker:
    project_id: ProjectId
    repository_id: RepositoryId
    mount_name: MountName


@dataclass(frozen=True, slots=True)
class UseExistingRepository:
    repository_id: RepositoryId
    project_id: ProjectId | None
    needs_confirmation: bool


@dataclass(frozen=True, slots=True)
class CreateRepository:
    canonical_remote: NormalizedRemote | None


@dataclass(frozen=True, slots=True)
class Refuse:
    code: str
    details: JsonObject


type AttachDecision = UseMarker | UseExistingRepository | CreateRepository | Refuse


@dataclass(frozen=True, slots=True)
class RepositoryMatchView:
    """A repository of the workspace that shares remotes with the observed checkout (``match_remotes``)."""

    repository_id: RepositoryId
    title: str
    matched_remotes: tuple[
        NormalizedRemote, ...
    ]  # its remotes that were looked up; re-checked by the decision
    project_ids: tuple[ProjectId, ...]  # projects the repository is already mounted in


@dataclass(frozen=True, slots=True)
class MarkerTarget:
    """The ``(workspace, project, repository)`` of the marker, as found in the server's own tables."""

    workspace_id: WorkspaceId
    project_id: ProjectId
    repository_id: RepositoryId


@dataclass(frozen=True, slots=True)
class AttachInput:
    instance_id: UUID
    workspace_id: WorkspaceId
    requested_project_id: ProjectId | None  # explicit project (--project)
    observed: ObservedCheckout
    known_repositories: tuple[RepositoryMatchView, ...]
    marker_target: MarkerTarget | None  # None: the target named by the marker does not exist
    assume_yes: bool


@dataclass(frozen=True, slots=True)
class AttachOutcome:
    decision: AttachDecision
    diagnostics: tuple[Diagnostic, ...]


def _mismatch(reason: str) -> Refuse:
    return Refuse(ErrorCode.CHECKOUT_MISMATCH.value, {"reason": reason})


def _marker_decision(inp: AttachInput, diagnostics: list[Diagnostic]) -> AttachDecision | None:
    """Rows 2-4a. ``None`` means: no usable marker, go on with the remotes."""
    marker = inp.observed.marker
    if marker is None:
        return None
    if marker.instance_id != inp.instance_id:
        diagnostics.append(
            Diagnostic(
                MARKER_FOREIGN_INSTANCE,
                "the checkout marker belongs to another instance and is ignored",
                Severity.WARNING,
                details={"marker_instance_id": str(marker.instance_id)},
            )
        )
        return None
    if marker.workspace_id != inp.workspace_id:
        return _mismatch("marker_other_workspace")
    target = inp.marker_target
    exists = (
        target is not None
        and target.workspace_id == marker.workspace_id
        and target.project_id == marker.project_id
        and target.repository_id == marker.repository_id
    )
    if not exists:
        diagnostics.append(
            Diagnostic(
                MARKER_STALE,
                "the project or repository named by the checkout marker no longer exists",
                Severity.WARNING,
                details={"project_id": str(marker.project_id), "repository_id": str(marker.repository_id)},
            )
        )
        return None
    if inp.requested_project_id is not None and inp.requested_project_id != marker.project_id:
        return _mismatch("marker_other_project")
    return UseMarker(marker.project_id, marker.repository_id, marker.mount_name)


def _candidates(inp: AttachInput) -> tuple[RepositoryMatchView, ...]:
    """Distinct repositories that really share a remote with the observation, in a stable order."""
    observed = set(inp.observed.remotes)
    unique = {
        view.repository_id: view
        for view in inp.known_repositories
        if observed.intersection(view.matched_remotes)
    }
    return tuple(sorted(unique.values(), key=lambda view: str(view.repository_id)))


def _candidate(view: RepositoryMatchView) -> JsonObject:
    projects: list[JsonValue] = [str(project_id) for project_id in sorted(set(view.project_ids), key=str)]
    return {"repository_id": str(view.repository_id), "title": view.title, "project_ids": projects}


def _ambiguous(candidates: tuple[RepositoryMatchView, ...]) -> Refuse:
    listed: list[JsonValue] = [_candidate(view) for view in candidates]
    return Refuse(
        ErrorCode.AMBIGUOUS_REFERENCE.value,
        {"reason": "remotes_match_several_repositories", "candidates": listed},
    )


def decide_attach_with_diagnostics(inp: AttachInput) -> AttachOutcome:
    """The decision of §5.2 together with the marker diagnostics it passed on the way."""
    diagnostics: list[Diagnostic] = []
    if not inp.observed.is_git_checkout:
        return AttachOutcome(_mismatch("not_a_git_checkout"), ())
    from_marker = _marker_decision(inp, diagnostics)
    if from_marker is not None:
        return AttachOutcome(from_marker, tuple(diagnostics))
    found = _candidates(inp)
    if len(found) >= 2:
        return AttachOutcome(_ambiguous(found), tuple(diagnostics))
    if len(found) == 1:
        view = found[0]
        mounted = set(view.project_ids)
        project_id = inp.requested_project_id
        if project_id is None and len(mounted) == 1:
            (project_id,) = mounted
        decision = UseExistingRepository(
            view.repository_id,
            project_id,
            needs_confirmation=not inp.assume_yes and inp.requested_project_id is None,
        )
        return AttachOutcome(decision, tuple(diagnostics))
    if inp.requested_project_id is None:
        refusal = Refuse(ErrorCode.SCHEMA_INVALID.value, {"reason": "project_required"})
        return AttachOutcome(refusal, tuple(diagnostics))
    canonical = inp.observed.remotes[0] if inp.observed.remotes else None
    return AttachOutcome(CreateRepository(canonical), tuple(diagnostics))


def decide_attach(inp: AttachInput) -> AttachDecision:
    return decide_attach_with_diagnostics(inp).decision
