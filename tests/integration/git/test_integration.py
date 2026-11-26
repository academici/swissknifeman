"""Real local Git projection, CAS receipts and durable no-push history."""

from datetime import UTC, datetime, timedelta
from importlib import util
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest

from integration.git.conftest import AUTHOR, make_repo
from skm.adapters.git.commit import ExcludeRules, snapshot_commit
from skm.adapters.git.host_inputs import capture_checkout
from skm.adapters.git.integration import GitIntegrator, effect_digest
from skm.adapters.git.output_writer import PreSealSnapshot
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.assignment import StageInstruction
from skm.modules.execution.domain.ids import ExternalEffectId
from skm.modules.execution.host.stages.base import StageRequest
from skm.modules.execution.host.stages.integrate import IntegrateStage

_TRAILER_CHECK = Path(__file__).resolve().parents[3] / "tools" / "check_trailers.py"
_SPEC = util.spec_from_file_location("check_trailers", _TRAILER_CHECK)
assert _SPEC is not None
assert _SPEC.loader is not None
_check_trailers = util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_check_trailers)
check_message = _check_trailers.check_message

NOW = datetime(2026, 11, 16, tzinfo=UTC)


def ownership(effect, attempt, root):
    return {
        "kind": "pgroup_best_effort",
        "ref": f"pgroup:{effect}",
        "owner": {
            "host_id": str(uuid4()),
            "worker_id": str(uuid4()),
            "attempt_id": attempt,
            "stage_record_id": str(uuid4()),
            "unit_kind": "git_effect",
            "unit_id": str(effect),
            "owner_nonce": uuid4().hex,
            "identity_dir": str(root / "identities"),
        },
    }


class Client:
    def __init__(self, *, clock=None):
        self.calls = []
        self.clock = clock or [0.0]
        self.delay = 0
        self.admission = {}
        self.fail_result = False
        self.released = []

    def acquire_integration_slot(self, repository_id, target_branch):
        return {
            "slot_id": str(uuid4()),
            "fencing_token": 1,
            "expires_at": (NOW + timedelta(minutes=2)).isoformat(),
        }

    def release_integration_slot(self, slot):
        self.released.append(slot)

    def record_effect(self, report):
        self.calls.append(report)
        if report["phase"] == "executing":
            self.clock[0] += self.delay
            return {
                "state": "executing",
                "admission": {
                    "admission_id": str(uuid4()),
                    "effect_id": report["effect_id"],
                    "request_digest": report["request_digest"],
                    "slot_fencing_token": 1,
                    "server_now": NOW.isoformat(),
                    "admit_until": (NOW + timedelta(seconds=5)).isoformat(),
                    **self.admission,
                },
            }
        if report["phase"] == "result" and self.fail_result:
            raise ConnectionError("lost DB receipt reply")
        return {"state": report["phase"]}


def seal(git, repo, base, state):
    return snapshot_commit(
        git, repo, base, state_dir=state, message="sealed output\n", exclude=ExcludeRules(())
    ).commit


def make_case(tmp_path, *, dirty=False):
    repo = tmp_path / "repo"
    git, _ = make_repo(repo)
    lines = [f"line {i}\n" for i in range(40)]
    (repo / "file.txt").write_text("".join(lines))
    git.run(repo, ["add", "file.txt"])
    git.run_bytes(repo, ["commit", "-m", "large baseline"], env=AUTHOR)
    before = git.run(repo, ["rev-parse", "HEAD"]).stdout.strip()
    git.run(repo, ["update-ref", "refs/heads/integration", before])
    if dirty:
        lines[1] = "user dirty hunk\n"
        (repo / "file.txt").write_text("".join(lines))
    baseline = seal(git, repo, before, tmp_path / "snapshots")
    lines[-2] = "agent accepted hunk\n"
    (repo / "file.txt").write_text("".join(lines))
    head = seal(git, repo, baseline, tmp_path / "snapshots")
    effect_id = ExternalEffectId(uuid4())
    inputs = {
        "repository_id": str(uuid4()),
        "target_branch": "integration",
        "mount": "repo",
        "baseline_sha": baseline,
        "run_id": str(uuid4()),
        "plan_id": str(uuid4()),
        "revision_no": 3,
        "task_key": "T1",
        "attempt_id": str(uuid4()),
        "assignment_fencing_token": 1,
        "outputs": [
            {
                "output_id": str(uuid4()),
                "output_digest": "sha256:" + "a" * 64,
                "head_sha": head,
                "output_no": 1,
                "review_round": 1,
            }
        ],
    }
    inputs["process_ownership"] = ownership(effect_id, inputs["attempt_id"], tmp_path)
    clock = [0.0]
    writer = GitIntegrator(
        git, worktrees_root=tmp_path / "owned", now=lambda: NOW, monotonic=lambda: clock[0]
    )
    client = Client(clock=clock)
    slot = client.acquire_integration_slot(None, None)
    return SimpleNamespace(
        repo=repo,
        git=git,
        before=before,
        baseline=baseline,
        head=head,
        inputs=inputs,
        effect=effect_id,
        clock=clock,
        writer=writer,
        client=client,
        slot=slot,
        tmp=tmp_path,
    )


def bind_outputs(case, inputs):
    for output in inputs["outputs"]:
        writer = PreSealSnapshot(
            UUID(inputs["attempt_id"]),
            uuid5(UUID(inputs["attempt_id"]), str(output["output_no"])),
            output["output_no"],
            inputs["mount"],
            capture_checkout(case.repo),
            inputs["assignment_fencing_token"],
        )
        writer.write(case.git, output["head_sha"])
        writer.confirm(
            case.git,
            output["head_sha"],
            output_id=UUID(output["output_id"]),
            manifest_digest=output["output_digest"],
        )


def prepare(case):
    bind_outputs(case, case.inputs)
    return case.writer.prepare_integration(case.repo, case.effect, case.inputs, slot=case.slot)


def publish(case, request):
    return case.writer.publish_integration(
        case.repo, case.effect, request, slot=case.slot, client=case.client
    )


@pytest.mark.parametrize("strategy", ["squash", "rebase", "merge"])
def test_dirty_hunks_project_only_task_delta_with_exact_receipt(tmp_path, strategy):
    case = make_case(tmp_path, dirty=True)
    case.inputs["strategy"] = strategy
    dirty_bytes = (case.repo / "file.txt").read_bytes()
    user_head = case.git.run(case.repo, ["rev-parse", "HEAD"]).stdout
    index = (case.repo / ".git/index").read_bytes()
    request = prepare(case)
    receipt = publish(case, request)
    content = case.git.run(case.repo, ["show", request.after_sha + ":file.txt"]).stdout
    assert "user dirty" not in content
    assert "agent accepted" in content
    assert case.git.run(case.repo, ["rev-parse", request.after_sha + "^1"]).stdout.strip() == case.before
    assert (
        case.git.run(
            case.repo, ["merge-base", "--is-ancestor", case.baseline, request.after_sha], check=False
        ).exit_code
        == 1
    )
    assert (case.repo / "file.txt").read_bytes() == dirty_bytes
    assert (case.repo / ".git/index").read_bytes() == index
    assert case.git.run(case.repo, ["rev-parse", "HEAD"]).stdout == user_head
    assert receipt.request_digest == effect_digest(case.effect, request)
    assert receipt.receipt_ref == "refs/skm/effects/" + str(case.effect)
    metadata = case.git.run(case.repo, ["show", receipt.receipt_ref + ":receipt.json"]).stdout
    assert '"receipt_commit_sha"' not in metadata
    assert [c["phase"] for c in case.client.calls] == ["intended", "executing", "result"]
    assert case.writer.reconcile_integration(case.repo, case.effect, request)["state"] == "succeeded"
    calls = len(case.client.calls)
    assert publish(case, request) == receipt
    assert len(case.client.calls) == calls


@pytest.mark.parametrize("strategy", ["rebase", "merge"])
@pytest.mark.parametrize("mode", ["final_only", "implementation_and_fixes", "per_stage_attributed"])
def test_fixes_project_chain_and_final_only_collapses(tmp_path, strategy, mode):
    case = make_case(tmp_path)
    (case.repo / "fix.txt").write_bytes(b"review fix\n")
    fixed = seal(case.git, case.repo, case.head, tmp_path / "snapshots")
    case.inputs["strategy"] = strategy
    case.inputs["commit_mode"] = mode
    case.inputs["outputs"].append(
        {
            "output_id": str(uuid4()),
            "output_digest": "sha256:" + "b" * 64,
            "head_sha": fixed,
            "output_no": 2,
            "review_round": 2,
        }
    )
    request = prepare(case)
    assert len(request.commit_shas) == (1 if mode == "final_only" else 2)
    assert len(request.output_ids) == len(request.commit_shas)
    publish(case, request)
    for index, sha in enumerate(request.commit_shas, 1):
        message = case.git.run(case.repo, ["show", "-s", "--format=%B", sha]).stdout
        assert f"SKM-Output-No: {2 if mode == 'final_only' else index}" in message
        assert "SKM-Effect: " + str(case.effect) in message
    assert (
        case.git.run(
            case.repo, ["merge-base", "--is-ancestor", case.head, request.after_sha], check=False
        ).exit_code
        == 1
    )


def test_per_stage_attributed_skips_noop_and_keeps_the_reviewer_fix_identity(tmp_path):
    case = make_case(tmp_path)
    ref = f"skm:revision:{uuid4()}#entity:{uuid4()}"
    digest = "sha256:" + "d" * 64
    case.inputs.update(
        commit_mode="per_stage_attributed",
        strategy="rebase",
        task_spec_ref=ref,
        task_spec_digest=digest,
        task_spec="Private spec text",
        plan="skm",
        plan_ref="T1",
    )
    initial, noop, fixed = (str(uuid4()) for _ in range(3))
    finding = "fk-" + "a" * 16
    review_id = str(uuid4())
    first = {
        **case.inputs["outputs"][0],
        "output_id": initial,
        "review_id": review_id,
        "findings": [finding],
        "producers": [
            {"plan_role": "executor", "plan_actor": "codex/assigned/high", "executed_by": "codex/actual/high"}
        ],
    }
    (case.repo / "fix.txt").write_text("review fix\n")
    fixed_head = seal(case.git, case.repo, case.head, tmp_path / "snapshots")
    case.inputs["outputs"] = [
        first,
        {**first, "output_id": noop, "output_no": 2, "output_digest": "sha256:" + "b" * 64},
        {
            **first,
            "output_id": fixed,
            "output_no": 3,
            "output_digest": "sha256:" + "c" * 64,
            "head_sha": fixed_head,
            "review_id": str(uuid4()),
            "review_round": 2,
            "producers": [
                {
                    "plan_role": "reviewer",
                    "plan_actor": "gemini/assigned/medium",
                    "executed_by": "gemini/actual/medium",
                    "executor_session": "fix-session",
                }
            ],
            "reviewed_by": "codex/actual/high",
            "reviewer_session": "fresh-review-session",
        },
    ]
    request = prepare(case)
    assert tuple(str(output_id) for output_id in request.output_ids) == (initial, noop, fixed)
    assert len(request.commit_shas) == 2
    assert publish(case, request).commit_shas == request.commit_shas
    first_message, fixed_message = [
        case.git.run(case.repo, ["show", "-s", "--format=%B", sha]).stdout for sha in request.commit_shas
    ]
    assert f"SKM-Output: {initial}\n" in first_message
    assert "Plan-Role: executor\n" in first_message
    assert f"SKM-Output: {fixed}\n" in fixed_message
    assert "SKM-Output-No: 3\n" in fixed_message
    assert "SKM-Review-Round: 2\n" in fixed_message
    assert f"SKM-Findings: {finding}\n" in fixed_message
    assert "Plan-Role: reviewer\n" in fixed_message
    assert "Plan-Actor: gemini/assigned/medium\n" in fixed_message
    assert "Executed-By: gemini/actual/medium\n" in fixed_message
    assert "Executor-Session: fix-session\n" in fixed_message
    assert "Reviewed-By: codex/actual/high\nReviewer-Session: fresh-review-session\n" in fixed_message
    for message in (first_message, fixed_message):
        assert not check_message(message)
        assert f"Task-Spec-Ref: {ref}\nTask-Spec-Digest: {digest}\n" in message
        assert noop not in message
        assert "Private spec text" not in message


def test_final_only_preserves_repeated_contributor_trailers_in_git(tmp_path):
    case = make_case(tmp_path)
    case.inputs["outputs"][0].pop("review_round")
    case.inputs["outputs"][0]["producers"] = [
        {"plan_role": "executor", "executed_by": "codex/actual/high", "executor_session": "original"},
        {"plan_role": "reviewer", "executed_by": "codex/actual/high", "executor_session": "correction"},
    ]
    request = prepare(case)
    publish(case, request)
    message = case.git.run(case.repo, ["show", "-s", "--format=%B", request.after_sha]).stdout
    assert check_message(message) == ()
    assert message.count("Executed-By: codex/actual/high\n") == 2
    assert message.index("Executor-Session: original") < message.index("Plan-Role: reviewer")
    assert message.index("Plan-Role: reviewer") < message.index("Executor-Session: correction")


@pytest.mark.parametrize("line", ["  task-spec-ref: forged", "Plan-Role: reviewer", "sKm-Review: forged"])
def test_registrar_message_cannot_supply_managed_attribution(tmp_path, line):
    case = make_case(tmp_path)
    case.inputs["message"] = "fix: candidate message\n\n" + line
    with pytest.raises(ValueError, match="registrar message contains identity trailers"):
        prepare(case)


def test_cas_conflict_does_not_rewrite_target_or_receipt(tmp_path):
    case = make_case(tmp_path)
    request = prepare(case)
    case.git.run(case.repo, ["update-ref", "refs/heads/integration", case.head, case.before])
    with pytest.raises(SkmError) as caught:
        publish(case, request)
    # Confirmed CAS refusal creates neither a publication nor an effect receipt.
    assert caught.value.code.value == "INTEGRATION_CONFLICT"
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.head
    assert (
        case.git.run(
            case.repo,
            ["rev-parse", "--verify", "--quiet", "refs/skm/effects/" + str(case.effect)],
            check=False,
        ).exit_code
        == 1
    )


def test_checked_out_target_refused_before_candidate(tmp_path):
    case = make_case(tmp_path)
    case.inputs["target_branch"] = "main"
    with pytest.raises(SkmError) as caught:
        prepare(case)
    assert caught.value.code.value == "INTEGRATION_BRANCH_BUSY"
    assert not list((tmp_path / "owned").rglob("candidate"))


def test_two_unpushed_tasks_survive_restart_and_preserve_history(tmp_path):
    case = make_case(tmp_path)
    first = prepare(case)
    publish(case, first)
    case.writer = GitIntegrator(
        case.git, worktrees_root=tmp_path / "owned", now=lambda: NOW, monotonic=lambda: 0
    )
    # Next attempt starts from the local integration tip, although the remote/main never advanced.
    local = case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip()
    case.git.run(case.repo, ["read-tree", "--reset", "-u", local])
    (case.repo / "second.txt").write_bytes(b"task B\n")
    case.effect = ExternalEffectId(uuid4())
    case.slot["fencing_token"] = 2
    case.client.admission["slot_fencing_token"] = 2
    next_attempt = str(uuid4())
    case.inputs = {
        **case.inputs,
        "attempt_id": next_attempt,
        "baseline_sha": local,
        "task_key": "T2",
        "process_ownership": ownership(case.effect, next_attempt, tmp_path),
        "outputs": [
            {
                "output_id": str(uuid4()),
                "output_digest": "sha256:" + "c" * 64,
                "output_no": 1,
                "head_sha": seal(case.git, case.repo, local, tmp_path / "snapshots"),
            }
        ],
    }
    second = prepare(case)
    publish(case, second)
    assert second.before_sha == first.after_sha
    assert (
        case.git.run(case.repo, ["rev-list", "--count", case.before + "..integration"]).stdout.strip() == "2"
    )
    assert case.git.run(case.repo, ["rev-parse", "main"]).stdout.strip() == case.before


def test_projection_preserves_deletes_modes_and_binary_bytes(tmp_path):
    case = make_case(tmp_path)
    (case.repo / "file.txt").unlink()
    (case.repo / "binary").write_bytes(b"\0\xff\x01content")
    (case.repo / "run.sh").write_text("#!/bin/sh\nexit 0\n")
    (case.repo / "run.sh").chmod(0o755)
    case.inputs["outputs"][0]["head_sha"] = seal(case.git, case.repo, case.baseline, tmp_path / "snapshots")
    request = prepare(case)
    publish(case, request)
    entries = case.git.run(case.repo, ["ls-tree", request.after_sha]).stdout
    assert "file.txt" not in entries
    assert "100755" in entries
    assert (
        case.git.run_bytes(case.repo, ["show", request.after_sha + ":binary"]).stdout == b"\0\xff\x01content"
    )


@pytest.mark.parametrize("refusal", ["conflict", "refused", "unknown", "host_mismatch"])
def test_multi_target_partial_success_replay_never_repeats_first(tmp_path, refusal):
    first_root, second_root = tmp_path / "a", tmp_path / "b"
    first_root.mkdir()
    second_root.mkdir()
    a, b = make_case(first_root), make_case(second_root)
    # Each target has its own repository and stable effect; order is explicit in trusted stage input.
    a.inputs["repository_id"], b.inputs["repository_id"] = str(UUID_ZERO), str(UUID_ONE)
    b.inputs["outputs"][0]["output_id"] = a.inputs["outputs"][0]["output_id"]
    targets: Any = [
        {**a.inputs, "mount": "a", "effect_id": str(a.effect)},
        {**b.inputs, "mount": "b", "effect_id": str(b.effect)},
    ]

    for case, target in zip((a, b), targets, strict=True):
        bind_outputs(case, target)

    class Gateway:
        def prepare_integration(self, repo, effect, inputs, *, slot):
            item = a if repo == a.repo else b
            return item.writer.prepare_integration(repo, effect, inputs, slot=slot)

        def publish_integration(self, repo, effect, request, *, slot, client):
            item = a if repo == a.repo else b
            if item is b:
                from skm.kernel.error_codes import ErrorCode
                from skm.kernel.errors import error_for

                code = {
                    "conflict": ErrorCode.INTEGRATION_CONFLICT,
                    "refused": ErrorCode.LEASE_LOST,
                    "unknown": ErrorCode.OUTCOME_UNKNOWN,
                    "host_mismatch": ErrorCode.INTEGRATION_HOST_MISMATCH,
                }[refusal]
                raise error_for(code, "B refuses")
            return item.writer.publish_integration(repo, effect, request, slot=slot, client=client)

    environment = SimpleNamespace(
        mounts={"a": a.repo, "b": b.repo},
        baseline=[
            SimpleNamespace(mount="a", repository_id=UUID_ZERO),
            SimpleNamespace(mount="b", repository_id=UUID_ONE),
        ],
    )
    req = StageRequest(
        StageInstruction("run_stage"),
        {"accepted_output_id": a.inputs["outputs"][0]["output_id"], "integration_targets": targets},
        None,
        {},
    )
    deps: Any = SimpleNamespace(
        environment=environment,
        vcs=Gateway(),
        worker=a.client,
        cancel=SimpleNamespace(cancelled=False, raise_if_cancelled=lambda: None),
        monotonic=SimpleNamespace(monotonic=lambda: 0),
        config=SimpleNamespace(get=lambda _: None),
    )
    result = IntegrateStage().run(req, deps)
    from skm.platform.schema.registry import SchemaRegistry

    SchemaRegistry.load_default().require_valid(
        "urn:skm:execution:stage-outcome-integrate:v1", dict(result.payload)
    )
    assert result.kind.value == {"conflict": "conflict", "unknown": "outcome_unknown"}.get(
        refusal, "runtime_error"
    )
    completed = result.payload["integration_receipts"]
    assert isinstance(completed, list)
    assert len(completed) == 1
    first_tip = a.git.run(a.repo, ["rev-parse", "integration"]).stdout
    a.writer = GitIntegrator(a.git, worktrees_root=a.tmp / "owned", now=lambda: NOW, monotonic=lambda: 0)
    phases = len(a.client.calls)
    repeated = IntegrateStage().run(req, deps)
    assert repeated.payload == result.payload
    assert len(a.client.calls) == phases
    assert a.git.run(a.repo, ["rev-parse", "integration"]).stdout == first_tip
    if refusal == "unknown":
        from dataclasses import replace

        from skm.modules.execution.domain.workflow.stage_inputs import StageMode

        reconcile = replace(req, instruction=StageInstruction("run_stage", mode=StageMode.RECONCILE))
        blocked = IntegrateStage().run(reconcile, deps)
        assert blocked.kind.value == "outcome_unknown"
        # An unbound vector cannot admit inspection; no helper process was started.
        assert blocked.reaped is True
        assert blocked.payload == {"error_code": "OUTCOME_UNKNOWN"}
        assert len(a.client.calls) == phases
        assert a.git.run(a.repo, ["rev-parse", "integration"]).stdout == first_tip


UUID_ZERO = UUID(int=1)
UUID_ONE = UUID(int=2)


@pytest.mark.parametrize("strategy", ["squash", "rebase", "merge"])
@pytest.mark.parametrize("cancelled_chain", [False, True])
def test_empty_final_only_delta_has_no_commits_and_an_exact_noop_receipt(tmp_path, strategy, cancelled_chain):
    case = make_case(tmp_path, dirty=True)
    case.inputs["strategy"] = strategy
    final = {**case.inputs["outputs"][0], "head_sha": case.baseline, "output_id": str(uuid4())}
    final["output_no"] = 2 if cancelled_chain else 1
    case.inputs["outputs"] = [*case.inputs["outputs"], final] if cancelled_chain else [final]
    request = prepare(case)
    assert request.before_sha == request.after_sha == case.before
    assert request.commit_shas == ()
    receipt = publish(case, request)
    assert receipt.before_sha == receipt.after_sha == case.before
    assert receipt.commit_shas == ()
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.before
    assert case.writer.reconcile_integration(case.repo, case.effect, request)["state"] == "succeeded"
    assert publish(case, request) == receipt


@pytest.mark.parametrize("strategy", ["rebase", "merge"])
@pytest.mark.parametrize("changed_outputs", [1, 2])
def test_final_only_changed_output_then_accepted_noop_uses_accepted_trailers(
    tmp_path, strategy, changed_outputs
):
    case = make_case(tmp_path)
    case.inputs.update(strategy=strategy, commit_mode="final_only", review_id=str(uuid4()))
    outputs = case.inputs["outputs"]
    if changed_outputs == 2:
        (case.repo / "fix.txt").write_bytes(b"review fix\n")
        outputs.append(
            {
                **outputs[-1],
                "output_id": str(uuid4()),
                "output_digest": "sha256:" + "b" * 64,
                "head_sha": seal(case.git, case.repo, case.head, tmp_path / "snapshots"),
                "output_no": 2,
                "review_round": 2,
            }
        )
    previous = outputs[-1]
    tree = case.git.run(case.repo, ["rev-parse", previous["head_sha"] + "^{tree}"]).stdout.strip()
    noop_head = (
        case.git.run_bytes(
            case.repo,
            ["commit-tree", tree, "-p", previous["head_sha"]],
            env=AUTHOR,
            stdin=b"accepted no-op\n",
        )
        .stdout.decode()
        .strip()
    )
    accepted = {
        **previous,
        "output_id": str(uuid4()),
        "output_digest": "sha256:" + "c" * 64,
        "head_sha": noop_head,
        "output_no": changed_outputs + 1,
        "review_round": changed_outputs + 1,
    }
    outputs.append(accepted)
    request = prepare(case)
    assert request.before_sha != request.after_sha
    assert len(request.commit_shas) == 1
    assert tuple(str(value) for value in request.output_ids) == (accepted["output_id"],)
    assert request.output_digests == (accepted["output_digest"],)
    assert request.tree_sha == tree
    message = case.git.run(case.repo, ["show", "-s", "--format=%B", request.after_sha]).stdout
    assert f"SKM-Output: {accepted['output_id']}\n" in message
    assert previous["output_id"] not in message
    assert f"SKM-Effect: {case.effect}\n" in message
    assert f"SKM-Review: {case.inputs['review_id']}\n" in message
    assert f"SKM-Output-No: {accepted['output_no']}\n" in message
    assert f"SKM-Review-Round: {accepted['review_round']}\n" in message
    assert case.git.run(case.repo, ["rev-parse", request.after_sha + "^1"]).stdout.strip() == case.before
    receipt = publish(case, request)
    assert receipt.output_ids == request.output_ids
    assert case.writer.reconcile_integration(case.repo, case.effect, request)["state"] == "succeeded"


def test_every_candidate_epoch_and_receipt_write_enables_full_fsync(tmp_path, monkeypatch):
    from skm.adapters.git import integration_process

    case = make_case(tmp_path)
    commands = []
    run = case.git.run_bytes
    spawn = integration_process.processes.spawn

    def durable(repo, args, **kwargs):
        commands.append(list(args))
        return run(repo, args, **kwargs)

    def owned(argv, **kwargs):
        commands.append(list(argv))
        return spawn(argv, **kwargs)

    monkeypatch.setattr(case.git, "run_bytes", durable)
    monkeypatch.setattr(integration_process.processes, "spawn", owned)
    publish(case, prepare(case))
    for command in ("apply", "write-tree", "commit-tree", "hash-object", "mktree", "update-ref"):
        matching = [args for args in commands if command in args]
        assert matching, command
        assert all("core.fsync=all" in args for args in matching), command


def test_reconcile_mode_refuses_all_publication_and_slot_calls(tmp_path):
    from skm.modules.execution.domain.workflow.stage_inputs import StageMode

    class NoPublication:
        def __getattr__(self, name):
            pytest.fail(f"reconcile invoked {name}")

    req = StageRequest(
        StageInstruction("run_stage", mode=StageMode.RECONCILE),
        {"integrate": {"integration_targets": [{"effect_id": str(uuid4())}]}},
        None,
        {},
    )
    deps: Any = SimpleNamespace(environment=object(), vcs=NoPublication(), worker=NoPublication())
    result = IntegrateStage().run(req, deps)
    assert result.kind.value == "outcome_unknown"
    assert result.payload == {"error_code": "OUTCOME_UNKNOWN"}
    assert result.reaped  # No inspection started, independently of the unknown effect outcome.
