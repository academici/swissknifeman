"""Rules of tool intents and approvals without the bus (policy §4.6, §5.12, §15).

Normalization decides what an approval binds; the transition table decides what can happen next. The
negative cases are the ones a reviewer would try first: forced pushes, ref deletion, mirror, an argument no
schema knows, a digest that moves with the order of refspecs or the case of a UUID.
"""

from dataclasses import replace
from datetime import timedelta
from itertools import product
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, ToolIntentId, WorkspaceId
from skm.modules.policy.application.composition import builtin_profiles
from skm.modules.policy.domain.approval import (
    DENY_RECORD_TTL,
    ApprovalDecision,
    ApprovalId,
    approval_matches,
    approve,
    auto_approval,
    consume,
    denial,
    system_approval_holds,
    usable_approval,
)
from skm.modules.policy.domain.permission_set import PermissionLayer, narrow
from skm.modules.policy.domain.tool_intent import (
    ACTIVE_STATES,
    INTENT_TRANSITIONS,
    DeniedReason,
    EffectKind,
    EnforcementMode,
    ForbiddenArgs,
    IntentState,
    RiskClass,
    args_digest,
    deny,
    expire,
    normalize_args,
    propose,
    transition_intent,
)
from skm.platform.jsonc.digest import digest
from unit.policy.application.harness import DIGEST, NOW, commit_args, push_args

PERMS = builtin_profiles()["workspace-contained"].permissions
EXTERNAL_WRITE = {
    "host_id": "01900000-0000-7000-8000-0000000000aa",
    "path": "/export/file",
    "content_digest": DIGEST,
}
ALLOWED = replace(
    PERMS,
    external_effects=frozenset(EffectKind),
    effects_need_approval=frozenset({EffectKind.GIT_PUSH, EffectKind.PR_CREATE}),
)
HUMAN = PrincipalId(UUID(int=7))
IDS = {
    name: UUID(int=index) for index, name in enumerate(("intent", "workspace", "scope", "actor"), start=100)
}


def made(kind: EffectKind = EffectKind.GIT_PUSH, args: dict | None = None, perms=ALLOWED, **overrides):
    values = {
        "kind": kind,
        "raw_args": push_args() if args is None else args,
        "perms": perms,
        "now": NOW,
        "ttl": timedelta(hours=1),
        "intent_id": ToolIntentId(IDS["intent"]),
        "workspace_id": WorkspaceId(IDS["workspace"]),
        "scope_id": ScopeId(IDS["scope"]),
        "subject_ref": "run:1/attempt:1",
        "actor_id": PrincipalId(IDS["actor"]),
        "risk": RiskClass.HIGH,
        "reason": "integrate",
    }
    values.update(overrides)
    return propose(**values)


# ------------------------------------------------------------------------------------------ normalization
FORCING = [
    pytest.param({"force": True}, "force_push", id="force-true"),
    pytest.param({"force": "yes"}, "force_push", id="force-truthy-text"),
    pytest.param({"mirror": True}, "mirror_push", id="mirror-key"),
    pytest.param({"refspecs": ["+refs/heads/a:refs/heads/a"]}, "force_refspec", id="plus-source"),
    pytest.param({"refspecs": ["refs/heads/a:+refs/heads/a"]}, "force_refspec", id="plus-destination"),
    pytest.param({"refspecs": [":refs/heads/a"]}, "ref_deletion", id="empty-source"),
    pytest.param({"refspecs": ["--mirror"]}, "mirror_push", id="mirror-refspec"),
]


@pytest.mark.parametrize(("changes", "reason"), FORCING)
def test_arguments_nobody_may_approve_are_forbidden(changes: dict, reason: str) -> None:
    with pytest.raises(ForbiddenArgs) as caught:
        normalize_args(EffectKind.GIT_PUSH, push_args(**changes))
    assert caught.value.reason == reason


@pytest.mark.parametrize(("changes", "_reason"), FORCING)
def test_forbidden_arguments_make_a_denied_intent_even_when_the_kind_is_permitted(
    changes: dict, _reason: str
) -> None:
    intent = made(args=push_args(**changes))
    assert (intent.state, intent.denied_reason) == (IntentState.DENIED, DeniedReason.FORBIDDEN_ARGS.value)
    assert (
        intent.normalized_args["refspecs"] == push_args(**changes)["refspecs"]
    )  # shown as asked, not repaired
    assert intent.args_digest.startswith("sha256:")


def test_forbidden_arguments_win_over_a_kind_outside_the_ceiling() -> None:
    narrowed = replace(ALLOWED, external_effects=frozenset())
    assert made(args=push_args(force=True), perms=narrowed).denied_reason == "forbidden_args"
    assert made(perms=narrowed).denied_reason == "not_permitted"


def test_a_permitted_well_formed_proposal_waits_for_a_decision() -> None:
    intent = made()
    assert (intent.state, intent.denied_reason, intent.row_version) == (IntentState.PROPOSED, None, 1)
    assert intent.expires_at == NOW + timedelta(hours=1)
    assert intent.normalized_args["force"] is False


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param({"password": "x"}, id="unknown-member"),
        pytest.param(
            {
                "endpoint": {
                    "transport": "https",
                    "hostname": "h",
                    "effective_port": 443,
                    "repository_path": "p",
                    "userinfo": "u:p",
                }
            },
            id="credentials-in-endpoint",
        ),
        pytest.param({"binding_identity": {"binding_id": "x"}}, id="incomplete-binding"),
        pytest.param({"before_sha": "abc"}, id="short-sha"),
        pytest.param({"target_ref": "main"}, id="not-a-full-ref"),
        pytest.param({"refspecs": []}, id="no-refspec"),
        pytest.param({"refspecs": ["refs/tags/v1:refs/tags/v1"]}, id="tag-refspec"),
        pytest.param({"refspecs": ["refs/heads/a"]}, id="no-destination"),
        pytest.param(
            {
                "endpoint": {
                    "transport": "https",
                    "hostname": "h",
                    "effective_port": 0,
                    "repository_path": "p",
                }
            },
            id="port-zero",
        ),
    ],
)
def test_malformed_arguments_are_a_schema_error_not_an_intent(bad: dict) -> None:
    with pytest.raises(ValidationFailed) as caught:
        made(args=push_args(**bad))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_a_missing_member_is_named() -> None:
    document = push_args()
    del document["after_sha"]
    with pytest.raises(ValidationFailed) as caught:
        normalize_args(EffectKind.GIT_PUSH, document)
    assert caught.value.details["field"] == "after_sha"


def test_the_digest_is_stable_against_refspec_order_duplicates_and_uuid_case() -> None:
    first = ["refs/heads/a:refs/heads/a", "refs/heads/b:refs/heads/b"]
    base = args_digest(EffectKind.GIT_PUSH, normalize_args(EffectKind.GIT_PUSH, push_args(refspecs=first)))
    for refspecs in (first[::-1], [*first, first[0]]):
        other = normalize_args(EffectKind.GIT_PUSH, push_args(refspecs=refspecs))
        assert args_digest(EffectKind.GIT_PUSH, other) == base
    upper = push_args(refspecs=first, repository_id=push_args()["repository_id"].upper())
    assert args_digest(EffectKind.GIT_PUSH, normalize_args(EffectKind.GIT_PUSH, upper)) == base


@pytest.mark.parametrize(
    "changes",
    [
        {"after_sha": "d" * 40},
        {"before_sha": "d" * 40},
        {"target_ref": "refs/heads/other"},
        {"refspecs": ["refs/heads/main:refs/heads/other"]},
        {"remote": "github.com/acme/other"},
        {
            "endpoint": {
                "transport": "ssh",
                "hostname": "github.com",
                "effective_port": 443,
                "repository_path": "acme/app.git",
            }
        },
        {
            "endpoint": {
                "transport": "https",
                "hostname": "evil.example",
                "effective_port": 443,
                "repository_path": "acme/app.git",
            }
        },
        {
            "endpoint": {
                "transport": "https",
                "hostname": "github.com",
                "effective_port": 8443,
                "repository_path": "acme/app.git",
            }
        },
        {
            "endpoint": {
                "transport": "https",
                "hostname": "github.com",
                "effective_port": 443,
                "repository_path": "acme/other.git",
            }
        },
    ],
    ids=lambda c: next(iter(c)),
)
def test_every_semantic_argument_moves_the_digest(changes: dict) -> None:
    base = made().args_digest
    assert made(args=push_args(**changes)).args_digest != base


def test_the_digest_binds_the_kind_and_matches_the_platform_serialization() -> None:
    args = normalize_args(EffectKind.GIT_COMMIT, commit_args())
    assert args_digest(EffectKind.GIT_COMMIT, args) == digest({"kind": "git_commit", "args": dict(args)})
    same = {"channel": "c", "recipients": ["é", "a"], "body_digest": DIGEST}
    message = normalize_args(EffectKind.MESSAGE, same)
    assert message["recipients"] == ["a", "é"]
    assert args_digest(EffectKind.MESSAGE, message) == digest({"kind": "message", "args": dict(message)})
    assert args_digest(EffectKind.PUBLISH, {"x": 1}) != args_digest(EffectKind.MESSAGE, {"x": 1})


@pytest.mark.parametrize(
    ("kind", "document"),
    [
        (EffectKind.GIT_COMMIT, commit_args()),
        (EffectKind.MESSAGE, {"channel": "c", "recipients": ["a"], "body_digest": DIGEST}),
        (EffectKind.PUBLISH, {"target": "pypi", "artifact_digest": DIGEST, "version": "1.0.0"}),
        (EffectKind.FS_WRITE_EXTERNAL, EXTERNAL_WRITE),
    ],
)
def test_the_other_kinds_normalize_to_their_schema_and_reject_extras(
    kind: EffectKind, document: dict
) -> None:
    assert dict(normalize_args(kind, document)) == document
    with pytest.raises(ValidationFailed):
        normalize_args(kind, {**document, "extra": 1})
    with pytest.raises(ValidationFailed):
        normalize_args(kind, dict(list(document.items())[1:]))


@pytest.mark.parametrize(
    "path", ["relative/file", "/", "//export/file", "/export/../file", "/export/./file", "/file\x00"]
)
def test_external_write_rejects_noncanonical_paths(path: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        normalize_args(EffectKind.FS_WRITE_EXTERNAL, {**EXTERNAL_WRITE, "path": path})
    assert caught.value.details["field"] == "path"


def test_external_write_digest_binds_host_path_and_content() -> None:
    kind = EffectKind.FS_WRITE_EXTERNAL
    canonical = normalize_args(kind, {**EXTERNAL_WRITE, "host_id": EXTERNAL_WRITE["host_id"].upper()})
    assert canonical == EXTERNAL_WRITE
    base = args_digest(kind, canonical)
    assert base == digest({"kind": kind.value, "args": EXTERNAL_WRITE})
    for field, replacement in (
        ("host_id", str(UUID(int=9))),
        ("path", "/export/other"),
        ("content_digest", "sha256:" + "b" * 64),
    ):
        assert args_digest(kind, normalize_args(kind, {**EXTERNAL_WRITE, field: replacement})) != base


def test_external_write_is_denied_unattended_and_never_auto_approved() -> None:
    kind = EffectKind.FS_WRITE_EXTERNAL
    unattended = made(kind, EXTERNAL_WRITE, mode=EnforcementMode.AGENT_UNATTENDED)
    assert (unattended.state, unattended.denied_reason) == (IntentState.DENIED, "not_permitted")
    interactive = made(kind, EXTERNAL_WRITE)
    assert interactive.state is IntentState.PROPOSED
    assert auto_approval(interactive, ALLOWED, NOW, approval_id=ApprovalId(UUID(int=10))) is None


def test_the_input_is_copied_and_cannot_change_a_stored_intent() -> None:
    document = push_args()
    intent = made(args=document)
    document["refspecs"].append("refs/heads/z:refs/heads/z")
    document["endpoint"]["hostname"] = "evil.example"
    stored: Any = intent.normalized_args
    assert stored["endpoint"]["hostname"] == "github.com"
    assert stored["refspecs"] == ["refs/heads/main:refs/heads/main"]


# ------------------------------------------------------------------------------------------ transitions
@pytest.mark.parametrize(("source", "target"), list(product(IntentState, IntentState)))
def test_the_transition_table_is_the_only_way_to_move(source: IntentState, target: IntentState) -> None:
    intent = replace(made(), state=source, denied_reason="revoked" if source is IntentState.DENIED else None)
    reason = DeniedReason.REVOKED if target is IntentState.DENIED else None
    if target in INTENT_TRANSITIONS[source]:
        moved = transition_intent(intent, target, denied_reason=reason)
        assert (moved.state, moved.row_version) == (target, intent.row_version + 1)
        assert (moved.denied_reason is not None) == (target is IntentState.DENIED)
    else:
        with pytest.raises(PreconditionFailed) as caught:
            transition_intent(intent, target, denied_reason=reason)
        assert caught.value.code is ErrorCode.INVALID_TRANSITION
        assert caught.value.details == {"kind": "tool_intent", "from": source.value, "to": target.value}


def test_terminal_states_have_no_exit_and_the_open_ones_are_the_unique_index_states() -> None:
    for state in (IntentState.DENIED, IntentState.EXPIRED, IntentState.SUCCEEDED, IntentState.FAILED):
        assert INTENT_TRANSITIONS[state] == frozenset()
    assert {IntentState.PROPOSED, IntentState.APPROVED, IntentState.EXECUTING} == ACTIVE_STATES
    assert INTENT_TRANSITIONS[IntentState.OUTCOME_UNKNOWN] == {IntentState.SUCCEEDED, IntentState.FAILED}


def test_a_denial_needs_its_reason_and_only_a_denial_has_one() -> None:
    with pytest.raises(ValueError, match="denied_reason"):
        transition_intent(made(), IntentState.DENIED)
    with pytest.raises(ValueError, match="denied_reason"):
        transition_intent(made(), IntentState.APPROVED, denied_reason=DeniedReason.REVOKED)
    assert deny(made(), DeniedReason.BY_APPROVER).denied_reason == "by_approver"
    assert expire(made()).state is IntentState.EXPIRED


# ------------------------------------------------------------------------------------------ approvals
def human_approval(intent, **changes):
    values = {
        "approval_id": ApprovalId(UUID(int=900)),
        "approver_id": HUMAN,
        "now": NOW,
        "ttl": timedelta(hours=1),
        "single_use": True,
        "reason": "ok",
    }
    values.update(changes)
    return approve(intent, **values)


def test_an_approval_matches_only_its_intent_digest_window_and_use() -> None:
    intent = made()
    approval = human_approval(intent)
    assert approval_matches(approval, intent, NOW)
    assert approval_matches(approval, intent, NOW + timedelta(minutes=59, seconds=59))
    assert not approval_matches(approval, intent, NOW + timedelta(hours=1))  # expired at the boundary
    assert not approval_matches(replace(approval, intent_id=ToolIntentId(UUID(int=1))), intent, NOW)
    assert not approval_matches(replace(approval, args_digest=DIGEST), intent, NOW)
    assert not approval_matches(replace(approval, used_at=NOW), intent, NOW)  # single use, spent
    assert approval_matches(replace(approval, used_at=NOW, single_use=False), intent, NOW)
    refusal = denial(intent, approval_id=ApprovalId(UUID(int=901)), approver_id=HUMAN, now=NOW, reason="no")
    assert refusal.decision is ApprovalDecision.DENY
    assert refusal.expires_at == NOW + DENY_RECORD_TTL
    assert not approval_matches(refusal, intent, NOW)


def test_changed_arguments_never_match_an_older_approval() -> None:
    first = made()
    approval = human_approval(first)
    changed = made(args=push_args(after_sha="d" * 40))
    assert changed.args_digest != first.args_digest
    assert not approval_matches(approval, changed, NOW)


def test_spending_twice_is_refused_and_the_newest_matching_approval_is_chosen() -> None:
    intent = made()
    older = human_approval(intent)
    newer = human_approval(intent, approval_id=ApprovalId(UUID(int=901)), now=NOW + timedelta(seconds=5))
    spent = consume(older, NOW)
    assert spent.used_at == NOW
    with pytest.raises(Forbidden) as caught:
        consume(spent, NOW)
    assert caught.value.code is ErrorCode.APPROVAL_MISMATCH
    assert usable_approval([older, newer], intent, NOW + timedelta(seconds=6)) == newer
    assert usable_approval([spent], intent, NOW) is None


def test_the_system_never_signs_a_human_approval() -> None:
    with pytest.raises(ValueError, match="auto_approval"):
        human_approval(made(), approver_id=SYSTEM_PRINCIPAL_ID)


def test_auto_approval_is_only_for_kinds_that_need_no_human() -> None:
    commit = made(EffectKind.GIT_COMMIT, commit_args())
    automatic = auto_approval(commit, ALLOWED, NOW, approval_id=ApprovalId(UUID(int=950)))
    assert automatic is not None
    assert (automatic.approver_id, automatic.single_use, automatic.expires_at) == (
        SYSTEM_PRINCIPAL_ID,
        True,
        commit.expires_at,
    )
    assert auto_approval(made(), ALLOWED, NOW, approval_id=ApprovalId(UUID(int=951))) is None
    assert system_approval_holds(automatic, commit, ALLOWED)
    stricter = narrow(ALLOWED, PermissionLayer(source="t", effects_need_approval=frozenset(EffectKind)))
    assert not system_approval_holds(automatic, commit, stricter)  # the condition that made it is gone
    assert (
        auto_approval(
            replace(commit, state=IntentState.APPROVED), ALLOWED, NOW, approval_id=ApprovalId(UUID(int=952))
        )
        is None
    )
