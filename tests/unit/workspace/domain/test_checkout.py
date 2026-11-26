"""Checkout binding (workspace §4.3, §5.3): transitions, locator, verify, staleness."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, RepositoryId, WorkspaceId
from skm.modules.workspace.domain.checkout_binding import (
    BINDING_TRANSITIONS,
    BindingState,
    CheckoutBinding,
    CheckoutBindingId,
    ObservedCheckout,
    VerifyReason,
    ensure_transition,
    is_stale,
    new_binding,
    normalize_locator,
    remove,
    require_remotes_match,
    verify,
)
from skm.modules.workspace.domain.remote_url import NormalizedRemote

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)
BINDING = CheckoutBindingId(UUID(int=1))
WS = WorkspaceId(UUID(int=2))
HOST = HostId(UUID(int=3))
REPO = RepositoryId(UUID(int=4))
REMOTE = NormalizedRemote("github.com/a/b")
OTHER = NormalizedRemote("github.com/x/y")
HEAD = "a" * 40
LOCATOR = "/work/repo"


def observed(
    *,
    exists: bool = True,
    toplevel: str | None = LOCATOR,
    remotes: tuple[NormalizedRemote, ...] = (REMOTE,),
    head: str | None = HEAD,
) -> ObservedCheckout:
    return ObservedCheckout(
        exists=exists, toplevel=toplevel, remotes=remotes, head=head, marker=None, observed_at=T1, dirty=False
    )


def binding(state: BindingState = BindingState.ACTIVE) -> CheckoutBinding:
    return CheckoutBinding(BINDING, WS, HOST, REPO, LOCATOR, state, (REMOTE,), HEAD, T0, 3, T0)


# --- transitions ---

_ALLOWED = {
    (BindingState.ACTIVE, BindingState.MISSING),
    (BindingState.ACTIVE, BindingState.MISMATCHED),
    (BindingState.ACTIVE, BindingState.REMOVED),
    (BindingState.MISSING, BindingState.ACTIVE),
    (BindingState.MISSING, BindingState.MISMATCHED),
    (BindingState.MISSING, BindingState.REMOVED),
    (BindingState.MISMATCHED, BindingState.ACTIVE),
    (BindingState.MISMATCHED, BindingState.MISSING),
    (BindingState.MISMATCHED, BindingState.REMOVED),
}


@pytest.mark.parametrize("source", list(BindingState))
@pytest.mark.parametrize("target", list(BindingState))
def test_transition_table(source: BindingState, target: BindingState) -> None:
    allowed = (source, target) in _ALLOWED
    assert (target in BINDING_TRANSITIONS[source]) is allowed
    if allowed:
        ensure_transition(source, target)
    else:
        with pytest.raises(PreconditionFailed) as err:
            ensure_transition(source, target)
        assert err.value.code is ErrorCode.INVALID_TRANSITION
        assert err.value.details == {"from": source.value, "to": target.value}


def test_removed_is_terminal() -> None:
    assert BINDING_TRANSITIONS[BindingState.REMOVED] == frozenset()


# --- locator ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/work/repo", "/work/repo"),
        ("/work/repo/", "/work/repo"),
        ("/work/repo///", "/work/repo"),
        ("/", "/"),
        ("//", "/"),
        ("C:\\work\\repo", "C:\\work\\repo"),
        ("C:\\work\\repo\\", "C:\\work\\repo"),
        ("C:\\", "C:\\"),
        ("c:\\\\", "c:\\"),
        ("/dir with space/é", "/dir with space/é"),
    ],
)
def test_normalize_locator(text: str, expected: str) -> None:
    assert normalize_locator(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "relative/path",
        "./x",
        "~/x",
        "C:relative",
        "C:/forward",
        "1:\\x",
        "/a\0b",
        "/a\nb",
        "/a\rb",
        "/" + "x" * 4096,
    ],
)
def test_normalize_locator_rejects(text: str) -> None:
    with pytest.raises(ValidationFailed) as err:
        normalize_locator(text)
    assert err.value.code is ErrorCode.SCHEMA_INVALID


def test_locator_at_the_length_limit_is_accepted() -> None:
    text = "/" + "x" * 4095
    assert normalize_locator(text) == text


# --- verify ---


def test_verify_ok_replaces_observations_and_bumps_the_version() -> None:
    result = verify(binding(BindingState.MISSING), observed(head="b" * 40), [REMOTE], T1)
    assert result.reason is VerifyReason.OK
    updated = result.binding
    assert updated.state is BindingState.ACTIVE
    assert updated.observed_head == "b" * 40
    assert updated.last_verified_at == T1
    assert updated.row_version == 4


def test_repeated_verify_of_an_active_binding_refreshes_time_only_semantically() -> None:
    first = verify(binding(), observed(), [REMOTE], T1)
    second = verify(first.binding, observed(), [REMOTE], T1 + timedelta(minutes=5))
    assert second.binding.state is BindingState.ACTIVE
    assert second.binding.last_verified_at == T1 + timedelta(minutes=5)
    assert second.binding.row_version == first.binding.row_version + 1


@pytest.mark.parametrize(
    "facts",
    [
        observed(exists=False, toplevel=None, remotes=(), head=None),
        observed(toplevel=None),
        observed(exists=False),
    ],
)
def test_verify_missing(facts: ObservedCheckout) -> None:
    result = verify(binding(), facts, [REMOTE], T1)
    assert (result.binding.state, result.reason) == (BindingState.MISSING, VerifyReason.MISSING)


def test_verify_moved_is_mismatched_and_the_locator_is_kept() -> None:
    result = verify(binding(), observed(toplevel="/elsewhere/repo"), [REMOTE], T1)
    assert (result.binding.state, result.reason) == (BindingState.MISMATCHED, VerifyReason.MOVED)
    assert result.binding.local_locator == LOCATOR  # never rebound by an observation
    assert result.binding.id == BINDING


def test_verify_moved_takes_precedence_over_remotes() -> None:
    result = verify(binding(), observed(toplevel="/elsewhere", remotes=(OTHER,)), [REMOTE], T1)
    assert result.reason is VerifyReason.MOVED


@pytest.mark.parametrize("toplevel", ["relative", "/work/repo\n", "", "/work/other"])
def test_verify_a_toplevel_that_is_not_the_locator_is_moved(toplevel: str) -> None:
    result = verify(binding(), observed(toplevel=toplevel), [REMOTE], T1)
    assert result.reason is VerifyReason.MOVED


def test_verify_trailing_separator_of_the_toplevel_is_not_a_move() -> None:
    assert verify(binding(), observed(toplevel=LOCATOR + "/"), [REMOTE], T1).reason is VerifyReason.OK


def test_verify_remotes_mismatch() -> None:
    result = verify(binding(), observed(remotes=(OTHER,)), [REMOTE], T1)
    assert (result.binding.state, result.reason) == (BindingState.MISMATCHED, VerifyReason.REMOTES)
    assert result.binding.observed_remotes == (OTHER,)


def test_verify_no_observed_remotes_against_a_repository_with_remotes_is_a_mismatch() -> None:
    assert verify(binding(), observed(remotes=()), [REMOTE], T1).reason is VerifyReason.REMOTES


def test_verify_repository_without_remotes_accepts_any_observation() -> None:
    assert verify(binding(), observed(remotes=(OTHER,)), [], T1).reason is VerifyReason.OK


def test_verify_one_shared_remote_among_several_is_enough() -> None:
    assert verify(binding(), observed(remotes=(OTHER, REMOTE)), [REMOTE], T1).reason is VerifyReason.OK


def test_verify_recovers_from_mismatch_when_the_checkout_returns() -> None:
    mismatched = verify(binding(), observed(remotes=(OTHER,)), [REMOTE], T1).binding
    assert verify(mismatched, observed(), [REMOTE], T1).binding.state is BindingState.ACTIVE


def test_verify_never_changes_the_identity_fields() -> None:
    original = binding()
    after = verify(original, observed(toplevel="/elsewhere", remotes=(OTHER,)), [REMOTE], T1).binding
    for field in ("id", "workspace_id", "host_id", "repository_id", "local_locator", "created_at"):
        assert getattr(after, field) == getattr(original, field)


def test_verify_of_a_removed_binding_is_invalid() -> None:
    with pytest.raises(PreconditionFailed) as err:
        verify(binding(BindingState.REMOVED), observed(), [REMOTE], T1)
    assert err.value.code is ErrorCode.INVALID_TRANSITION


def test_verify_is_deterministic() -> None:
    assert verify(binding(), observed(), [REMOTE], T1) == verify(binding(), observed(), [REMOTE], T1)


# --- remove / staleness ---


@pytest.mark.parametrize("state", [BindingState.ACTIVE, BindingState.MISSING, BindingState.MISMATCHED])
def test_remove(state: BindingState) -> None:
    removed = remove(binding(state))
    assert removed.state is BindingState.REMOVED
    assert removed.row_version == 4


def test_remove_twice_is_a_no_op() -> None:
    removed = remove(binding())
    assert remove(removed) is removed


def test_is_stale_is_computed_from_the_last_verification() -> None:
    stale_after = timedelta(days=30)
    assert not is_stale(binding(), T0 + stale_after, stale_after)  # exactly the limit is not stale
    assert is_stale(binding(), T0 + stale_after + timedelta(seconds=1), stale_after)
    assert not is_stale(
        replace(binding(), last_verified_at=T1), T0 + stale_after + timedelta(seconds=1), stale_after
    )


# --- new binding ---


def test_new_binding_takes_its_state_from_verify() -> None:
    result = new_binding(
        binding_id=BINDING,
        workspace_id=WS,
        host_id=HOST,
        repository_id=REPO,
        local_locator="/work/repo/",
        observed=observed(),
        repository_remotes=[REMOTE],
        now=T1,
    )
    assert result.reason is VerifyReason.OK
    created = result.binding
    assert (created.state, created.row_version, created.local_locator) == (BindingState.ACTIVE, 1, LOCATOR)
    assert created.observed_remotes == (REMOTE,)
    assert created.created_at == created.last_verified_at == T1


def test_new_binding_at_a_path_the_toplevel_does_not_match_is_mismatched() -> None:
    result = new_binding(
        binding_id=BINDING,
        workspace_id=WS,
        host_id=HOST,
        repository_id=REPO,
        local_locator="/work/other",
        observed=observed(),
        repository_remotes=[REMOTE],
        now=T1,
    )
    assert (result.binding.state, result.reason) == (BindingState.MISMATCHED, VerifyReason.MOVED)


def test_new_binding_rejects_foreign_remotes() -> None:
    with pytest.raises(PreconditionFailed) as err:
        new_binding(
            binding_id=BINDING,
            workspace_id=WS,
            host_id=HOST,
            repository_id=REPO,
            local_locator=LOCATOR,
            observed=observed(remotes=(OTHER,)),
            repository_remotes=[REMOTE],
            now=T1,
        )
    assert err.value.code is ErrorCode.CHECKOUT_MISMATCH
    assert err.value.details == {"reason": "remotes"}


def test_new_binding_rejects_a_relative_locator() -> None:
    with pytest.raises(ValidationFailed):
        new_binding(
            binding_id=BINDING,
            workspace_id=WS,
            host_id=HOST,
            repository_id=REPO,
            local_locator="repo",
            observed=observed(),
            repository_remotes=[REMOTE],
            now=T1,
        )


def test_require_remotes_match() -> None:
    require_remotes_match([REMOTE], [REMOTE, OTHER])
    require_remotes_match([OTHER], [])  # a repository without remotes accepts any observation
    with pytest.raises(PreconditionFailed):
        require_remotes_match([], [REMOTE])


@pytest.mark.parametrize("head", ["abc", "A" * 40, "g" * 40, "a" * 41, ""])
def test_observed_head_must_be_a_git_object_id(head: str) -> None:
    with pytest.raises(ValidationFailed):
        observed(head=head)


def test_observed_head_accepts_sha1_sha256_and_none() -> None:
    assert observed(head="0" * 64).head == "0" * 64
    assert observed(head=None).head is None


def test_observed_remotes_are_bounded() -> None:
    many = tuple(NormalizedRemote(f"h.example/r{i}") for i in range(33))
    with pytest.raises(ValidationFailed):
        observed(remotes=many)
