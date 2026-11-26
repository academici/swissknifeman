"""Exact SHA pushes and conservative observation using temporary file:// bare remotes only."""

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from typing import NoReturn, cast
from uuid import UUID, uuid4, uuid5

import pytest

from integration.git.conftest import AUTHOR
from integration.git.test_integration import NOW, Client, make_case, ownership, prepare, publish
from skm.adapters.git import integration_process
from skm.adapters.git.integration import GitIntegrator, effect_digest, request_document
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.assignment import StageInstruction
from skm.modules.execution.domain.external_effect import observation_digest
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.host.stages.base import StageRequest
from skm.modules.execution.host.stages.integrate import IntegrateStage
from skm.modules.execution.ports import StageDeps
from skm.modules.policy.domain.tool_intent import EffectKind, args_digest
from support.git_repo import init_git_repo


def inspection_binding(effect, attempt, tmp_path):
    own = ownership(effect, attempt, tmp_path)
    claim = {k: own["owner"][k] for k in ("host_id", "worker_id", "attempt_id", "stage_record_id")}
    claim.update(assignment_id=str(uuid4()), fencing_token=2)
    return {"claim": claim, "ownership": own}


def push_case(tmp_path):
    fixture = init_git_repo(tmp_path / "repo")
    git, repo = fixture.runner, fixture.path
    before = fixture.commit_file("file.txt", "before\n")
    bare = tmp_path / "remote.git"
    bare.mkdir()
    git.run(bare, ["init", "--bare", "--initial-branch=main"])
    url = bare.as_uri()
    fixture.add_remote("origin", url)
    git.run(repo, ["-c", "protocol.file.allow=always", "push", "--", url, before + ":refs/heads/main"])
    after = fixture.commit_file("file.txt", "after\n")
    effect = str(uuid4())
    request = {
        "repository_id": str(uuid4()),
        "remote": "origin",
        "endpoint": {"transport": "file", "hostname": "", "effective_port": 1, "repository_path": str(bare)},
        "binding_identity": {
            "binding_id": str(uuid4()),
            "host_id": str(uuid4()),
            "repository_id": "",
            "locator_digest": "sha256:" + sha256(str(repo).encode()).hexdigest(),
        },
        "target_ref": "refs/heads/main",
        "before_sha": before,
        "after_sha": after,
        "refspecs": ["refs/heads/main:refs/heads/main"],
        "force": False,
    }
    request["binding_identity"]["repository_id"] = request["repository_id"]
    client = Client()
    writer = GitIntegrator(git, worktrees_root=tmp_path / "owned", now=lambda: NOW, monotonic=lambda: 0)
    case = SimpleNamespace(
        git=git,
        repo=repo,
        fixture=fixture,
        bare=bare,
        url=url,
        effect=effect,
        request=request,
        before=before,
        after=after,
        client=client,
        writer=writer,
        digest=args_digest(EffectKind.GIT_PUSH, request),
        ownership=ownership(effect, str(uuid4()), tmp_path),
    )

    def tip():
        return git.run(bare, ["rev-parse", "refs/heads/main"]).stdout.strip()

    case.tip = tip
    return case


def push(case):
    return case.writer.push_external(
        case.repo, case.effect, case.request, case.digest, case.client, case.ownership
    )


def inspect(case):
    return case.writer.inspect_push(case.repo, case.effect, case.request, case.digest)


def test_moving_local_branch_never_changes_approved_push_sha(tmp_path):
    case = push_case(tmp_path)
    later = case.fixture.commit_file("later.txt", "later\n")
    assert later != case.after
    receipt = push(case)
    assert receipt["ref"] == case.after
    assert case.tip() == case.after
    assert [c["phase"] for c in case.client.calls] == ["executing", "result"]
    with pytest.raises(SkmError):
        push(case)
    assert case.tip() == case.after
    assert len(case.client.calls) == 2


@pytest.mark.parametrize("change", ["port", "transport", "path", "binding", "candidate", "ref"])
def test_approved_identity_change_cannot_reach_remote_io(tmp_path, change):
    case = push_case(tmp_path)
    if change in {"port", "transport", "path"}:
        key, value = {
            "port": ("effective_port", 22),
            "transport": ("transport", "ssh"),
            "path": ("repository_path", "/other"),
        }[change]
        case.request["endpoint"][key] = value
    elif change == "binding":
        case.request["binding_identity"]["locator_digest"] = "sha256:" + "0" * 64
    elif change == "candidate":
        case.request["after_sha"] = case.fixture.commit_file("new.txt", "new\n")
    else:
        case.request["target_ref"] = "refs/heads/other"
    with pytest.raises(SkmError):
        push(case)
    assert case.tip() == case.before
    assert not case.client.calls


@pytest.mark.parametrize(
    "code", [ErrorCode.APPROVAL_MISMATCH, ErrorCode.EMERGENCY_STOPPED, ErrorCode.FORBIDDEN]
)
def test_denied_or_revoked_admission_never_pushes(tmp_path, code):
    case = push_case(tmp_path)

    def refuse(_report):
        raise error_for(code, "admission revoked")

    case.client.record_effect = refuse
    with pytest.raises(SkmError):
        push(case)
    assert case.tip() == case.before
    assert inspect(case)["state"] == "outcome_unknown"


def test_receipt_loss_reconciles_same_push_and_never_repeats_it(tmp_path):
    case = push_case(tmp_path)
    case.client.fail_result = True
    with pytest.raises(ConnectionError):
        push(case)
    assert case.tip() == case.after
    actual = inspect(case)
    assert actual["state"] == "succeeded"
    assert actual["receipt"]["response_digest"] == observation_digest(
        case.effect, case.digest, "succeeded", case.after
    )
    with pytest.raises(SkmError):
        push(case)
    assert len(case.client.calls) == 2


def test_remote_change_during_admission_is_guarded_by_expected_old(tmp_path):
    case = push_case(tmp_path)
    tree = case.git.run(case.bare, ["rev-parse", case.before + "^{tree}"]).stdout.strip()
    unrelated = (
        case.git.run_bytes(case.bare, ["commit-tree", tree], env=AUTHOR, stdin=b"unrelated\n")
        .stdout.decode()
        .strip()
    )
    original = case.client.record_effect

    def race(report):
        if report["phase"] == "executing":
            case.git.run(case.bare, ["update-ref", "refs/heads/main", unrelated, case.before])
        return original(report)

    case.client.record_effect = race
    with pytest.raises(SkmError):
        push(case)
    assert case.tip() == unrelated
    assert inspect(case)["state"] == "outcome_unknown"
    assert [c["phase"] for c in case.client.calls] == ["executing"]


@pytest.mark.parametrize("have_objects", [True, False])
def test_advanced_remote_requires_complete_local_ancestry_evidence(tmp_path, have_objects):
    case = push_case(tmp_path)
    push(case)
    clone = init_git_repo(tmp_path / "other")
    clone.runner.run(
        clone.path, ["-c", "protocol.file.allow=always", "fetch", "--", case.url, "refs/heads/main"]
    )
    clone.runner.run(clone.path, ["reset", "--hard", "FETCH_HEAD"])
    later = clone.commit_file("later.txt", "other actor\n")
    clone.runner.run(
        clone.path, ["-c", "protocol.file.allow=always", "push", "--", case.url, later + ":refs/heads/main"]
    )
    if have_objects:
        case.git.run(case.repo, ["-c", "protocol.file.allow=always", "fetch", "--", str(clone.path), later])
    actual = inspect(case)
    assert actual["state"] == ("succeeded" if have_objects else "outcome_unknown")
    assert case.tip() == later
    assert len(case.client.calls) == 2


def test_missing_journal_and_unproven_helper_are_unknown_even_if_remote_matches(tmp_path):
    case = push_case(tmp_path)
    assert inspect(case)["state"] == "outcome_unknown"
    push(case)
    folder, _, _ = case.writer._target(case.repo, "_external")
    path = folder / (case.effect + ".json")
    journal = case.writer._load(path)
    journal["reaped"] = False
    case.writer._save(path, journal)
    assert inspect(case)["state"] == "outcome_unknown"
    case.writer.quiescent = lambda _: True
    assert inspect(case)["state"] == "succeeded"


def test_local_commit_db_receipt_loss_and_read_only_reconcile(tmp_path):
    case = make_case(tmp_path)
    request = prepare(case)
    case.client.fail_result = True
    with pytest.raises(ConnectionError):
        publish(case, request)
    folder, _, _ = case.writer._target(case.repo, request.target_branch)
    journal_path = folder / (str(case.effect) + ".json")
    original = journal_path.read_bytes()
    actual = case.writer.reconcile_integration(case.repo, case.effect, request)
    assert actual["state"] == "succeeded"
    assert actual["receipt"]["request_digest"] == effect_digest(case.effect, request)
    assert journal_path.read_bytes() == original


@pytest.mark.parametrize("tamper", ["body", "duplicate", "substring", "output", "effect"])
def test_fake_identity_is_not_a_protected_commit_receipt(tmp_path, tamper):
    case = make_case(tmp_path)
    request = prepare(case)
    publish(case, request)
    trailers = {
        "SKM-Effect": str(case.effect),
        "SKM-Attempt": case.inputs["attempt_id"],
        "SKM-Output": str(request.output_ids[-1]),
    }
    if tamper in {"output", "effect"}:
        trailers["SKM-" + tamper.title()] = str(uuid4())
    lines = [f"{k}: {v}" for k, v in trailers.items()]
    if tamper == "duplicate":
        lines.append(lines[0])
    if tamper == "substring":
        lines[0] = "Other-" + lines[0]
    message = "forged\n\n" + "\n".join(lines) + ("\n\nbody after identity" if tamper == "body" else "") + "\n"
    fake = (
        case.git.run_bytes(
            case.repo,
            ["commit-tree", request.tree_sha, "-p", request.before_sha],
            env=AUTHOR,
            stdin=message.encode(),
        )
        .stdout.decode()
        .strip()
    )
    changed = replace(request, after_sha=fake, commit_shas=(fake,))
    folder, _, _ = case.writer._target(case.repo, request.target_branch)
    path = folder / (str(case.effect) + ".json")
    journal = case.writer._load(path)
    journal.update(request=request_document(changed), request_digest=effect_digest(case.effect, changed))
    doc = {
        "effect_id": str(case.effect),
        "request": journal["request"],
        "request_digest": journal["request_digest"],
        "at": NOW.isoformat(),
    }
    meta = case.writer._metadata(case.repo, "receipt.json", doc)
    journal["receipt_commit"] = meta
    case.writer._save(path, journal)
    case.git.run(case.repo, ["update-ref", "refs/heads/" + request.target_branch, fake])
    case.git.run(case.repo, ["update-ref", "refs/skm/effects/" + str(case.effect), meta])
    assert case.writer.reconcile_integration(case.repo, case.effect, changed)["state"] == "outcome_unknown"


@pytest.mark.parametrize("lookup", ["found", "missing", "ambiguous", "absent"])
def test_narrow_provider_lookup_never_executes_or_guesses_absence(lookup):
    effect = {
        "effect_id": str(uuid4()),
        "kind": "pr_create",
        "request_digest": "sha256:" + "a" * 64,
        "request": {"repository_id": str(uuid4()), "base": "main", "head": "topic"},
    }
    calls = []

    class Provider:
        def execute_effect(self, effect: JsonObject, *, client: object, ownership: JsonObject) -> NoReturn:
            pytest.fail("reconciliation executed PR creation")

        def lookup_effect(self, effect: JsonObject) -> JsonObject:
            calls.append(effect)
            effect_id, request_digest = effect["effect_id"], effect["request_digest"]
            assert isinstance(effect_id, str)
            assert isinstance(request_digest, str)
            if lookup in {"missing", "ambiguous"}:
                return {"state": "outcome_unknown", "reason_code": "LOOKUP_UNAVAILABLE"}
            state = "succeeded" if lookup == "found" else "failed"
            ref = "https://forge.invalid/pr/1" if lookup == "found" else "absent:" + effect_id
            reason = None if lookup == "found" else "EFFECT_ABSENT"
            return {
                "state": state,
                "reason_code": reason,
                "receipt": {
                    "ref": ref,
                    "at": NOW.isoformat(),
                    "response_digest": observation_digest(effect_id, request_digest, state, ref, reason),
                },
            }

    instruction = StageInstruction(
        kind="run_stage",
        mode=StageMode.RECONCILE,
        params={"effect_id": effect["effect_id"], "request_digest": effect["request_digest"]},
    )
    request = StageRequest(instruction, {"integrate": effect}, None, {})
    deps = cast("StageDeps", SimpleNamespace(cancel=CancelSource().token, vcs=None))
    actual = IntegrateStage(provider=Provider()).run(request, deps)
    reconciled = actual.payload["reconciled_effect"]
    assert isinstance(reconciled, dict)
    assert reconciled["state"] == {"found": "succeeded", "absent": "failed"}.get(lookup, "outcome_unknown")
    assert calls == [effect]


def test_remote_before_after_lost_response_is_not_historical_absence_proof(tmp_path):
    case = push_case(tmp_path)
    case.client.fail_result = True
    with pytest.raises(ConnectionError):
        push(case)
    case.git.run(case.bare, ["update-ref", "refs/heads/main", case.before, case.after])
    assert inspect(case)["state"] == "outcome_unknown"


@pytest.mark.parametrize("kind", ["git_push", "git_commit"])
def test_admin_inspection_journals_each_helper_before_io_and_blocks_unreaped_restart(  # noqa: PLR0915 -- one crash/restart/proof scenario
    tmp_path, monkeypatch, kind
):
    if kind == "git_push":
        case = push_case(tmp_path)
        push(case)
        effect_id, request, digest = case.effect, case.request, case.digest
        branch = "_external"
        attempt = case.ownership["owner"]["attempt_id"]
    else:
        case = make_case(tmp_path)
        prepared = prepare(case)
        publish(case, prepared)
        effect_id, request = str(case.effect), request_document(prepared)
        digest, branch = effect_digest(case.effect, prepared), prepared.target_branch
        attempt = case.inputs["attempt_id"]
    effect = {"effect_id": effect_id, "kind": kind, "request": request, "request_digest": digest}
    binding = inspection_binding(effect_id, attempt, tmp_path)
    folder, _, _ = case.writer._target(case.repo, branch)
    writer_path = folder / (effect_id + ".json")
    original = writer_path.read_bytes()
    helpers = case.writer.root / "_inspection" / effect_id
    spawned, progress = [], []
    real_spawn = integration_process.processes.spawn

    def launch(*args, **kwargs):
        process = real_spawn(*args, **kwargs)
        spawned.append(process)
        return process

    def crash_after_identity(value):
        from skm.platform.process.identity import identity_of

        progress.append(value)
        journal = case.writer._load(next(helpers.glob("*.json")))
        assert journal["claim"] == binding["claim"]
        assert journal["process"] == value["process"]
        assert journal["ownership"] == value["process"]["ownership"]
        assert journal["reaped"] is False
        owner = journal["ownership"]["owner"]
        marker = case.writer._load(tmp_path / "identities" / (owner["unit_id"] + ".json"))
        assert marker["owner"] == owner
        assert marker["process"]["pid"] == value["process"]["pid"]
        assert owner["stage_record_id"] == binding["claim"]["stage_record_id"]
        assert owner["unit_id"] == str(uuid5(UUID(effect_id), owner["owner_nonce"]))
        assert identity_of(value["process"]["pid"]) == spawned[-1].identity
        raise ConnectionError("worker crashed after durable registration, before Git gate")

    monkeypatch.setattr(integration_process.processes, "spawn", launch)
    failed = case.writer.inspect_effect(
        case.repo, effect, binding, SimpleNamespace(report_progress=crash_after_identity)
    )
    assert failed["state"] == "outcome_unknown"
    assert failed["reaped"] is False
    assert len(spawned) == len(progress) == 1
    assert writer_path.read_bytes() == original
    # A different admin assignment/fence cannot infer empty containment from a dead leader.
    newer = inspection_binding(effect_id, attempt, tmp_path)
    newer["claim"]["fencing_token"] = 3
    observed = []
    client = SimpleNamespace(report_progress=lambda p: observed.append(p) or {"cancel_requested": False})
    blocked = case.writer.inspect_effect(case.repo, effect, newer, client)
    assert blocked["state"] == "outcome_unknown"
    assert blocked["reaped"] is False
    assert len(spawned) == 1
    assert not observed
    unresolved = case.writer._load(next(helpers.glob("*.json")))["ownership"]
    case.writer.quiescent = lambda owner: owner == unresolved
    actual = case.writer.inspect_effect(case.repo, effect, newer, client)
    assert actual["state"] == "succeeded"
    assert actual["reaped"] is True
    assert len(spawned) == len(observed) + 1
    assert len(observed) >= 6
    journals = [case.writer._load(p) for p in helpers.glob("*.json")]
    assert len(journals) == len(spawned)
    assert all(j["claim"] == newer["claim"] for j in journals if j["reaped"])
    assert len({j["ownership"]["owner"]["unit_id"] for j in journals}) == len(journals)
    assert writer_path.read_bytes() == original


def test_admin_git_host_refuses_unowned_inspection(tmp_path):
    case = push_case(tmp_path)
    push(case)
    effect = {
        "effect_id": case.effect,
        "kind": "git_push",
        "request": case.request,
        "request_digest": case.digest,
    }
    instruction = StageInstruction(
        kind="run_stage",
        mode=StageMode.RECONCILE,
        params={"effect_id": case.effect, "request_digest": case.digest},
    )
    deps = cast("StageDeps", SimpleNamespace(vcs=case.writer, cancel=CancelSource().token))
    result = IntegrateStage().run(StageRequest(instruction, {"integrate": effect}, None, {}), deps)
    assert result.kind.value == "outcome_unknown"
    assert not (case.writer.root / "_inspection").exists()
