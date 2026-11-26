"""Review receipts are read for each staged tree, independently of policy TTL."""

from dataclasses import replace
from typing import Any, override

import pytest

from integration.integrations.test_hooks import env, git, hook_env, request, set_modes
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.modules.integrations.host.evaluate_hook import run
from skm.modules.integrations.host.hook_state import HookState
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "env", "hook_env", "pg_session", "test_database"]


class ReviewClient:
    def __init__(self, inner: Any, receipt: Any) -> None:
        self.inner, self.receipt = inner, receipt
        self.queries: list[dict[str, Any]] = []

    def ask(self, query: Any) -> Any:
        if getattr(query, "SCHEMA_URN", "") == "urn:skm:execution:query:get-review-receipt:v1":
            self.queries.append(query.to_json())
            if isinstance(self.receipt, Exception):
                raise self.receipt
            return self.receipt
        return self.inner.ask(query)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def staged_digest(env: Any) -> str:
    from skm.modules.workspace.public import ResolveCheckout

    loc = env.client.ask(ResolveCheckout(env.project_id, "main", env.ctx.host_id))
    digest, _ = env.ctx.gateways.get(HookState).staged(str(env.checkout_dir), "main", str(loc.repository_id))
    return digest


def test_fresh_receipt_allows_then_new_staged_tree_denies(hook_env: Any) -> None:
    env = hook_env
    set_modes(env, review_gate="strict")
    (env.checkout_dir / "src/app.py").write_text("reviewed\n")
    git(env.checkout_dir, "add", "src/app.py")
    receipt = {"tree_digest": staged_digest(env), "status": "succeeded", "findings": []}
    client = ReviewClient(env.client, receipt)
    ctx = replace(env.ctx, client=client)
    req = request(env, surface="lifecycle.review_gate", command="git commit -m 'fix: reviewed'")
    assert run(ctx, req)["verdict"] == "none"
    # Unstaged changes do not change the reviewed staged tree.
    (env.checkout_dir / "src/app.py").write_text("unreviewed\n")
    assert run(ctx, req)["verdict"] == "none"
    git(env.checkout_dir, "add", "src/app.py")
    result = run(ctx, req)
    assert result["verdict"] == "deny"
    assert result.get("reason_code") == "REVIEW_RECEIPT_STALE"
    assert len(client.queries) == 3
    assert client.queries[0]["tree_digest"] != client.queries[-1]["tree_digest"]
    assert client.queries[-1]["mount"] == "main"


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (NotFound(ErrorCode.NOT_FOUND, "no review"), "REVIEW_RECEIPT_STALE"),
        (ConnectionError("private backend error"), "HOOK_BACKEND_UNAVAILABLE"),
        (TimeoutError("timeout"), "HOOK_BACKEND_UNAVAILABLE"),
    ],
)
@pytest.mark.parametrize(("mode", "verdict"), [("strict", "deny"), ("warn", "warn")])
def test_missing_or_unavailable_receipt_obeys_mode(
    hook_env: Any, failure: Exception, reason: str, mode: str, verdict: str
) -> None:
    env = hook_env
    set_modes(env, review_gate=mode)
    client = ReviewClient(env.client, failure)
    result = run(
        replace(env.ctx, client=client),
        request(env, surface="lifecycle.review_gate", command="git commit -m 'fix: x'"),
    )
    assert result["verdict"] == verdict
    assert result.get("reason_code") == reason
    assert "private backend" not in str(result)


@pytest.mark.parametrize(
    ("findings", "status"),
    [
        ([{"severity": "blocker", "status": "open"}], "succeeded"),
        ([], "running"),
    ],
)
def test_open_blocker_and_unfinished_review_deny(
    hook_env: Any, findings: list[dict[str, str]], status: str
) -> None:
    env = hook_env
    set_modes(env, review_gate="strict")
    client = ReviewClient(
        env.client, {"tree_digest": staged_digest(env), "status": status, "findings": findings}
    )
    result = run(
        replace(env.ctx, client=client),
        request(env, surface="lifecycle.review_gate", command="git commit -m 'fix: x'"),
    )
    assert result.get("reason_code") == "REVIEW_RECEIPT_STALE"


def test_review_off_and_non_commit_do_not_request_receipt(hook_env: Any) -> None:
    env = hook_env
    set_modes(env, review_gate="off")
    client = ReviewClient(env.client, AssertionError("must not read receipt"))
    ctx = replace(env.ctx, client=client)
    assert (
        run(ctx, request(env, surface="lifecycle.review_gate", command="git commit -m 'fix: x'"))["verdict"]
        == "none"
    )
    assert run(ctx, request(env, surface="lifecycle.review_gate", command="git status"))["verdict"] == "none"
    assert client.queries == []


def test_real_embedded_receipt_lookup_without_review_fails_closed(hook_env: Any) -> None:
    set_modes(hook_env, review_gate="strict")
    result = run(
        hook_env.ctx, request(hook_env, surface="lifecycle.review_gate", command="git commit -m 'fix: x'")
    )
    assert result.get("reason_code") == "REVIEW_RECEIPT_STALE"


@pytest.mark.parametrize(
    "command",
    [
        "git -C /foreign commit -m 'fix: x'",
        "git commit -am 'fix: x'",
        "git commit --all -m 'fix: x'",
        "git commit --only src/app.py -m 'fix: x'",
        "git add src/app.py && git commit -m 'fix: x'",
        "GIT_INDEX_FILE=/foreign/index git commit -m 'fix: x'",
    ],
)
def test_commit_cannot_substitute_the_reviewed_index(hook_env: Any, command: str) -> None:
    env = hook_env
    set_modes(env, review_gate="strict")
    client = ReviewClient(
        env.client, {"tree_digest": staged_digest(env), "status": "succeeded", "findings": []}
    )
    result = run(
        replace(env.ctx, client=client), request(env, surface="lifecycle.review_gate", command=command)
    )
    assert result["verdict"] == "deny"
    assert result.get("reason_code") == "HOOK_BACKEND_UNAVAILABLE"


def test_index_changed_while_reading_receipt_is_stale(hook_env: Any) -> None:
    env = hook_env
    set_modes(env, review_gate="strict")
    receipt = {"tree_digest": staged_digest(env), "status": "succeeded", "findings": []}

    class RacingClient(ReviewClient):
        @override
        def ask(self, query: Any) -> Any:
            if getattr(query, "SCHEMA_URN", "") == "urn:skm:execution:query:get-review-receipt:v1":
                (env.checkout_dir / "src/app.py").write_text("changed during lookup\n")
                git(env.checkout_dir, "add", "src/app.py")
            return super().ask(query)

    ctx = replace(env.ctx, client=RacingClient(env.client, receipt))
    result = run(ctx, request(env, surface="lifecycle.review_gate", command="git commit -m 'fix: x'"))
    assert result.get("reason_code") == "REVIEW_RECEIPT_STALE"


def test_real_output_sealer_receipt_matches_staged_tree(hook_env: Any) -> None:
    from uuid import UUID

    from skm.adapters.git.commit import git_output_sealer
    from skm.adapters.git.runner import GitRunner
    from skm.modules.execution.domain.review_request import ReviewReceipt
    from skm.modules.workspace.public import ResolveCheckout

    env = hook_env
    set_modes(env, review_gate="strict")
    baseline = git(env.checkout_dir, "rev-parse", "HEAD")
    (env.checkout_dir / "src/app.py").write_text("committed since baseline\n")
    git(env.checkout_dir, "add", "src/app.py")
    git(env.checkout_dir, "commit", "-qm", "intermediate")
    (env.checkout_dir / "src/app.py").write_text("reviewed staged content\n")
    git(env.checkout_dir, "add", "src/app.py")
    location = env.client.ask(ResolveCheckout(env.project_id, "main", env.ctx.host_id))
    sealer = git_output_sealer(GitRunner(), state_dir=env.state_dir)
    manifest = sealer.seal(
        env.checkout_dir,
        attempt_id="real-review",
        output_no=1,
        mount="main",
        repository_id=location.repository_id,
        baseline=baseline,
        write_scope=("**",),
    )
    identity = manifest.mounts[0]
    receipt = ReviewReceipt(
        UUID(int=1),
        UUID(int=2),
        "succeeded",
        "green",
        (),
        UUID(int=3),
        manifest.tree_digest,
        identity.base_commit,
        identity.head_commit,
    )
    assert receipt.tree_digest != staged_digest(env), "regression requires a genuine sealed commit identity"
    ctx = replace(env.ctx, client=ReviewClient(env.client, receipt))
    req = request(env, surface="lifecycle.review_gate", command="git commit -m 'fix: reviewed'")
    assert run(ctx, req)["verdict"] == "none"
    (env.checkout_dir / "src/app.py").write_text("changed after review\n")
    git(env.checkout_dir, "add", "src/app.py")
    assert run(ctx, req).get("reason_code") == "REVIEW_RECEIPT_STALE"


@pytest.mark.parametrize("command", ["'git' commit -m 'fix: x'", "git c'om'mit -m 'fix: x'"])
def test_quoted_commit_cannot_bypass_missing_receipt(hook_env: Any, command: str) -> None:
    set_modes(hook_env, review_gate="strict")
    result = run(hook_env.ctx, request(hook_env, surface="lifecycle.review_gate", command=command))
    assert result["verdict"] == "deny"
    assert result.get("reason_code") == "REVIEW_RECEIPT_STALE"
