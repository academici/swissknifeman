"""Attach decision (workspace §5.2): marker, then remotes, then a new repository; never "the first one"."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.kernel.outcomes import Severity
from skm.modules.workspace.domain.attach import (
    MARKER_FOREIGN_INSTANCE,
    MARKER_STALE,
    AttachDecision,
    AttachInput,
    CreateRepository,
    MarkerTarget,
    Refuse,
    RepositoryMatchView,
    UseExistingRepository,
    UseMarker,
    decide_attach,
    decide_attach_with_diagnostics,
)
from skm.modules.workspace.domain.checkout_binding import ObservedCheckout
from skm.modules.workspace.domain.checkout_marker import CheckoutMarker
from skm.modules.workspace.domain.mount import MountName
from skm.modules.workspace.domain.remote_url import NormalizedRemote

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
INSTANCE = UUID(int=1)
OTHER_INSTANCE = UUID(int=2)
WS = WorkspaceId(UUID(int=10))
OTHER_WS = WorkspaceId(UUID(int=11))
P1 = ProjectId(UUID(int=20))
P2 = ProjectId(UUID(int=21))
R1 = RepositoryId(UUID(int=30))
R2 = RepositoryId(UUID(int=31))
REMOTE_A = NormalizedRemote("github.com/a/one")
REMOTE_B = NormalizedRemote("github.com/a/two")


def observed(
    *,
    remotes: tuple[NormalizedRemote, ...] = (REMOTE_A,),
    marker: CheckoutMarker | None = None,
    exists: bool = True,
    toplevel: str | None = "/work/one",
) -> ObservedCheckout:
    return ObservedCheckout(
        exists=exists,
        toplevel=toplevel,
        remotes=remotes,
        head=None,
        marker=marker,
        observed_at=NOW,
        dirty=False,
    )


def marker(
    *,
    instance: UUID = INSTANCE,
    workspace: WorkspaceId = WS,
    project: ProjectId = P1,
    repository: RepositoryId = R1,
) -> CheckoutMarker:
    return CheckoutMarker(instance, workspace, project, repository, MountName("main"))


def view(
    repository: RepositoryId, *projects: ProjectId, remote: NormalizedRemote = REMOTE_A
) -> RepositoryMatchView:
    return RepositoryMatchView(repository, f"repo-{repository.int}", (remote,), tuple(projects))


def make(**changes: object) -> AttachInput:
    base = AttachInput(
        instance_id=INSTANCE,
        workspace_id=WS,
        requested_project_id=None,
        observed=observed(),
        known_repositories=(),
        marker_target=None,
        assume_yes=False,
    )
    return replace(base, **changes)


def refusal(decision: AttachDecision) -> Refuse:
    assert isinstance(decision, Refuse)
    return decision


# --- row 1 ---


@pytest.mark.parametrize(
    "facts",
    [observed(exists=False), observed(toplevel=None), observed(exists=False, toplevel=None)],
)
def test_not_a_git_checkout_is_refused_before_anything_else(facts: ObservedCheckout) -> None:
    target = MarkerTarget(WS, P1, R1)
    decision = decide_attach(
        make(observed=replace(facts, marker=marker()), marker_target=target, known_repositories=(view(R1),))
    )
    assert refusal(decision) == Refuse(ErrorCode.CHECKOUT_MISMATCH.value, {"reason": "not_a_git_checkout"})


# --- rows 2-4a: the marker ---


def test_marker_with_existing_target_is_used() -> None:
    inp = make(observed=observed(marker=marker()), marker_target=MarkerTarget(WS, P1, R1))
    assert decide_attach(inp) == UseMarker(P1, R1, MountName("main"))


def test_marker_wins_over_remote_candidates() -> None:
    inp = make(
        observed=observed(marker=marker()),
        marker_target=MarkerTarget(WS, P1, R1),
        known_repositories=(view(R1), view(R2)),
    )
    assert decide_attach(inp) == UseMarker(P1, R1, MountName("main"))


def test_marker_of_another_instance_is_ignored_with_a_diagnostic() -> None:
    inp = make(
        observed=observed(marker=marker(instance=OTHER_INSTANCE)),
        marker_target=MarkerTarget(WS, P1, R1),  # even a target that exists is not trusted
        known_repositories=(view(R2, P2),),
        requested_project_id=P2,
    )
    outcome = decide_attach_with_diagnostics(inp)
    assert outcome.decision == UseExistingRepository(R2, P2, needs_confirmation=False)
    (diagnostic,) = outcome.diagnostics
    assert diagnostic.code == MARKER_FOREIGN_INSTANCE
    assert diagnostic.severity is Severity.WARNING


def test_foreign_instance_marker_falls_through_to_create() -> None:
    inp = make(observed=observed(marker=marker(instance=OTHER_INSTANCE)), requested_project_id=P1)
    assert decide_attach(inp) == CreateRepository(REMOTE_A)


def test_marker_of_another_workspace_is_refused() -> None:
    inp = make(
        observed=observed(marker=marker(workspace=OTHER_WS)),
        marker_target=MarkerTarget(OTHER_WS, P1, R1),
        known_repositories=(view(R2),),
    )
    assert refusal(decide_attach(inp)).details == {"reason": "marker_other_workspace"}
    assert refusal(decide_attach(inp)).code == ErrorCode.CHECKOUT_MISMATCH.value


def test_marker_with_another_requested_project_is_refused() -> None:
    inp = make(
        observed=observed(marker=marker()), marker_target=MarkerTarget(WS, P1, R1), requested_project_id=P2
    )
    assert refusal(decide_attach(inp)).details == {"reason": "marker_other_project"}


def test_marker_with_the_same_requested_project_is_used() -> None:
    inp = make(
        observed=observed(marker=marker()), marker_target=MarkerTarget(WS, P1, R1), requested_project_id=P1
    )
    assert decide_attach(inp) == UseMarker(P1, R1, MountName("main"))


def test_stale_marker_falls_through_with_a_diagnostic() -> None:
    inp = make(observed=observed(marker=marker()), marker_target=None, known_repositories=(view(R2, P2),))
    outcome = decide_attach_with_diagnostics(inp)
    assert outcome.decision == UseExistingRepository(R2, P2, needs_confirmation=True)
    assert [d.code for d in outcome.diagnostics] == [MARKER_STALE]


@pytest.mark.parametrize(
    "target", [MarkerTarget(WS, P2, R1), MarkerTarget(WS, P1, R2), MarkerTarget(OTHER_WS, P1, R1)]
)
def test_a_target_that_is_not_the_marker_triple_is_stale_not_trusted(target: MarkerTarget) -> None:
    outcome = decide_attach_with_diagnostics(make(observed=observed(marker=marker()), marker_target=target))
    assert not isinstance(outcome.decision, UseMarker)
    assert [d.code for d in outcome.diagnostics] == [MARKER_STALE]


# --- rows 5-7: remotes ---


def test_two_repositories_with_the_remote_are_ambiguous_and_neither_is_chosen() -> None:
    inp = make(known_repositories=(view(R2, P2), view(R1, P1)))
    decision = refusal(decide_attach(inp))
    assert decision.code == ErrorCode.AMBIGUOUS_REFERENCE.value
    candidates = decision.details["candidates"]
    assert isinstance(candidates, list)
    assert [c["repository_id"] for c in candidates] == [str(R1), str(R2)]  # type: ignore[index]


def test_ambiguity_does_not_depend_on_the_order_of_the_input() -> None:
    forward = decide_attach(make(known_repositories=(view(R1), view(R2))))
    backward = decide_attach(make(known_repositories=(view(R2), view(R1))))
    assert forward == backward


def test_ambiguity_is_not_resolved_by_a_requested_project_or_assume_yes() -> None:
    inp = make(known_repositories=(view(R1, P1), view(R2, P1)), requested_project_id=P1, assume_yes=True)
    assert refusal(decide_attach(inp)).code == ErrorCode.AMBIGUOUS_REFERENCE.value


def test_same_title_repositories_are_not_merged_by_title() -> None:
    twin_a = replace(view(R1), title="same")
    twin_b = replace(view(R2), title="same")
    assert refusal(decide_attach(make(known_repositories=(twin_a, twin_b)))).code == (
        ErrorCode.AMBIGUOUS_REFERENCE.value
    )


def test_one_repository_listed_twice_is_one_candidate() -> None:
    decision = decide_attach(make(known_repositories=(view(R1, P1), view(R1, P1)), assume_yes=True))
    assert decision == UseExistingRepository(R1, P1, needs_confirmation=False)


def test_one_repository_needs_confirmation_unless_yes_or_a_project_is_named() -> None:
    known = (view(R1, P1),)
    assert decide_attach(make(known_repositories=known)) == UseExistingRepository(R1, P1, True)
    assert decide_attach(make(known_repositories=known, assume_yes=True)) == UseExistingRepository(
        R1, P1, False
    )
    assert decide_attach(make(known_repositories=known, requested_project_id=P2)) == UseExistingRepository(
        R1, P2, False
    )


def test_the_project_is_the_only_mounted_one_never_a_guess_among_several() -> None:
    assert decide_attach(make(known_repositories=(view(R1),))) == UseExistingRepository(R1, None, True)
    assert decide_attach(make(known_repositories=(view(R1, P1, P2),))) == UseExistingRepository(
        R1, None, True
    )
    assert decide_attach(make(known_repositories=(view(R1, P1, P1),))) == UseExistingRepository(R1, P1, True)


def test_a_candidate_without_a_shared_remote_is_not_a_match() -> None:
    stranger = view(R2, P2, remote=REMOTE_B)
    assert decide_attach(make(known_repositories=(stranger,), requested_project_id=P1)) == CreateRepository(
        REMOTE_A
    )
    assert decide_attach(make(known_repositories=(stranger, view(R1, P1)), assume_yes=True)) == (
        UseExistingRepository(R1, P1, False)
    )


def test_no_candidates_creates_a_repository_with_the_first_observed_remote() -> None:
    facts = observed(remotes=(REMOTE_B, REMOTE_A))
    assert decide_attach(make(observed=facts, requested_project_id=P1)) == CreateRepository(REMOTE_B)


def test_no_candidates_and_no_remotes_creates_a_local_repository() -> None:
    assert decide_attach(make(observed=observed(remotes=()), requested_project_id=P1)) == CreateRepository(
        None
    )


def test_creating_requires_an_explicit_project() -> None:
    decision = refusal(decide_attach(make()))
    assert decision.code == ErrorCode.SCHEMA_INVALID.value
    assert decision.details == {"reason": "project_required"}


def test_decide_attach_is_pure_and_repeatable() -> None:
    inp = make(known_repositories=(view(R1, P1),))
    assert decide_attach(inp) == decide_attach(inp)
