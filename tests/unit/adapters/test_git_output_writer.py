import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from integration.git.conftest import make_repo
from skm.adapters.git import integration, runner
from skm.adapters.git.commit import GitOutputSealer
from skm.adapters.git.host_inputs import capture_checkout
from skm.adapters.git.output_writer import PreSealSnapshot, verify_sealed_output
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import RepositoryId


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    root = tmp_path / "repo"

    # Unit boundary: the temporary repo is the entire host checkout. Keep its Git metadata
    # checks and real ref transactions independent of any repository enclosing pytest's tempdir.
    def trust_fixture_repo(path, *, allow_missing=False):
        assert Path(path).is_relative_to(tmp_path)
        runner._validate_dot_git(Path(path), Path(path) / ".git")
        return True

    def execute(_runner, argv, *, cwd, env, timeout_s, stdin=None):
        assert cwd.is_relative_to(tmp_path)
        done = subprocess.run(
            argv, cwd=cwd, env=env, timeout=timeout_s, input=stdin, capture_output=True, check=False
        )
        return SimpleNamespace(
            exit_code=done.returncode,
            stdout=done.stdout,
            stderr=done.stderr,
            stdout_truncated=False,
            stderr_truncated=False,
            duration_seconds=0,
        )

    monkeypatch.setattr(runner.GitRunner, "_execute", execute)
    monkeypatch.setattr(runner, "validate_repository_trust", trust_fixture_repo)
    monkeypatch.setattr(integration, "validate_repository_trust", trust_fixture_repo)
    git, baseline = make_repo(root)
    writer = PreSealSnapshot(uuid4(), uuid4(), 1, "main", capture_checkout(root), 3)
    return git, root, baseline, writer


def test_preseal_seal_and_publication_use_distinct_identities(tmp_path, snapshot):
    git, root, baseline, writer = snapshot
    (root / "file.txt").write_text("accepted bytes")
    (root / ".skm-dev").mkdir()
    (root / ".skm-dev/note").write_text("scratch")
    manifest = GitOutputSealer(git, state_dir=tmp_path / "snapshots").seal(
        root,
        attempt_id=str(writer.attempt_id),
        output_no=1,
        mount="main",
        repository_id=RepositoryId(uuid4()),
        baseline=baseline,
        write_scope=("file.txt",),
        writer=writer,
    )
    head = manifest.mounts[0].head_commit
    assert [p.path for p in manifest.changed_paths] == ["file.txt"]
    writer.write(git, head)  # replay of the same create-only transaction
    record = json.loads(git.run(root, ["cat-file", "blob", writer.binding_ref]).stdout)
    assert {k: v for k, v in record.items() if k != "checkout"} == {
        "attempt_id": str(writer.attempt_id),
        "step_id": str(writer.step_id),
        "output_no": 1,
        "mount": "main",
        "gitdir": str(root / ".git"),
        "ref": writer.ref,
        "expected_old": "0" * len(head),
        "fence": 3,
        "head": head,
    }
    assert "output_id" not in record
    assert git.run(root, ["rev-parse", writer.ref]).stdout.strip() == head
    assert not git.run(root, ["for-each-ref", "refs/skm/sealed"]).stdout

    output_id, digest = uuid4(), "sha256:" + "a" * 64
    accepted = {
        "attempt_id": writer.attempt_id,
        "output_no": 1,
        "mount": "main",
        "output_id": output_id,
        "head": head,
        "manifest_digest": digest,
    }
    with pytest.raises(SkmError):
        verify_sealed_output(git, writer.checkout, **accepted)
    for _ in range(2):
        writer.confirm(git, head, output_id=output_id, manifest_digest=digest)
    verify_sealed_output(git, writer.checkout, **accepted)
    with pytest.raises(SkmError):
        writer.confirm(git, head, output_id=uuid4(), manifest_digest=digest)
    for changed in ({"head": baseline}, {"output_id": uuid4()}, {"mount": "other"}, {"manifest_digest": "x"}):
        with pytest.raises(SkmError):
            verify_sealed_output(git, writer.checkout, **{**accepted, **changed})


@pytest.mark.parametrize("changes", [{"fence": 4}, {"step_id": UUID(int=7)}, {"mount": "other"}])
def test_same_sha_cannot_be_rebound_even_for_empty_output(snapshot, changes):
    git, root, baseline, writer = snapshot
    writer.write(git, baseline)
    other = replace(writer, **changes)
    with pytest.raises(SkmError):
        other.write(git, baseline)
    with pytest.raises(SkmError):
        other.confirm(git, baseline, output_id=uuid4(), manifest_digest="sha256:" + "a" * 64)
    assert not git.run(root, ["for-each-ref", "refs/skm/sealed"]).stdout


def test_preexisting_ref_fails_create_cas_without_creating_binding(snapshot):
    git, root, baseline, writer = snapshot
    git.run(root, ["update-ref", writer.ref, baseline])
    with pytest.raises(SkmError):
        writer.write(git, baseline)
    assert not git.run(root, ["for-each-ref", writer.binding_ref]).stdout


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b"{}",
        b"null",
        b'{"step_id":"invalid","fence":3}',
        b'{"step_id":"00000000-0000-0000-0000-000000000001","fence":0}',
        b'{"step_id":"00000000-0000-0000-0000-000000000001","fence":true}',
        b'{"step_id":"00000000-0000-0000-0000-000000000001","fence":3}',
    ],
)
def test_malformed_sealed_output_binding_reports_invalid_reference(snapshot, monkeypatch, payload):
    git, _, head, writer = snapshot
    read_binding = Mock(return_value=SimpleNamespace(exit_code=0, stdout=payload))
    monkeypatch.setattr(git, "run_bytes", read_binding)
    with pytest.raises(SkmError) as caught:
        verify_sealed_output(
            git,
            writer.checkout,
            attempt_id=writer.attempt_id,
            output_no=writer.output_no,
            mount=writer.mount,
            output_id=uuid4(),
            head=head,
            manifest_digest="sha256:" + "a" * 64,
        )
    assert caught.value.code == ErrorCode.INVALID_REFERENCE
    read_binding.assert_called_once()


def test_worker_confirms_server_identity_after_the_verified_snapshot(tmp_path, snapshot):
    from skm.bootstrap.worker_stages import seal_worker_snapshot

    git, root, baseline, writer = snapshot
    (root / "file.txt").write_text("executor output")
    mount = SimpleNamespace(mount="main", repository_id=RepositoryId(uuid4()), commit_sha=baseline)
    env = SimpleNamespace(environment_id=uuid4(), locator="owned", mounts={"main": root}, baseline=[mount])
    manager = Mock()
    manager.reopen.return_value = env
    request = Mock()
    request.begin = {"stage_record_id": str(uuid4()), "step": {"step_id": str(writer.step_id)}}
    request.task = {
        "attempt_id": str(writer.attempt_id),
        "assignment_fencing_token": writer.fence,
        "declared_write_scope": ["main:file.txt"],
    }
    deps = Mock()
    deps.environment = env
    deps.worker.report_progress.return_value = {}
    response = {"output_id": str(uuid4()), "manifest_digest": "sha256:" + "b" * 64, "seq": 1}
    heads = []

    def seal_output(manifest, patch):
        assert patch is None
        head = manifest["mounts"][0]["head_commit"]
        writer.verify(git, head)
        if not heads:
            assert not git.run(root, ["for-each-ref", "refs/skm/sealed"]).stdout
        heads.append(head)
        return response

    deps.worker.seal_output.side_effect = seal_output
    state = tmp_path / "state"
    assert seal_worker_snapshot(git, state, manager, request, deps) == response["output_id"]
    (root / "file.txt").write_text("subsequent workspace edits")
    assert seal_worker_snapshot(git, state, manager, request, deps) == response["output_id"]
    assert heads[0] == heads[1]
    verify_sealed_output(
        git,
        writer.checkout,
        attempt_id=writer.attempt_id,
        output_no=1,
        mount="main",
        output_id=UUID(response["output_id"]),
        head=heads[0],
        manifest_digest=response["manifest_digest"],
    )
    request.task["assignment_fencing_token"] += 1
    with pytest.raises(SkmError):
        seal_worker_snapshot(git, state, manager, request, deps)
    assert deps.worker.seal_output.call_count == 2


def test_worker_review_seals_only_a_changed_tree(tmp_path, snapshot):
    from skm.bootstrap.worker_stages import seal_worker_snapshot

    git, root, baseline, writer = snapshot
    path = root / "file.txt"
    path.write_text("implementation")
    mount = SimpleNamespace(mount="main", repository_id=RepositoryId(uuid4()), commit_sha=baseline)
    env = SimpleNamespace(environment_id=uuid4(), locator="owned", mounts={"main": root}, baseline=[mount])
    manager, request, deps = Mock(), Mock(), Mock()
    manager.reopen.return_value = deps.environment = env
    deps.worker.report_progress.return_value = {}
    first, fixed = str(uuid4()), str(uuid4())
    deps.worker.seal_output.side_effect = [
        {"output_id": first, "manifest_digest": "sha256:" + "a" * 64, "seq": 1},
        {"output_id": fixed, "manifest_digest": "sha256:" + "b" * 64, "seq": 2},
        {"output_id": fixed, "manifest_digest": "sha256:" + "b" * 64, "seq": 2},
    ]
    request.task = {
        "attempt_id": str(writer.attempt_id),
        "assignment_fencing_token": writer.fence,
        "declared_write_scope": ["main:file.txt"],
    }
    request.begin = {"stage_record_id": str(uuid4()), "step": {"step_id": str(writer.step_id)}}
    state = tmp_path / "state"
    assert seal_worker_snapshot(git, state, manager, request, deps) == first
    request.begin = {
        "stage_record_id": str(uuid4()),
        "step": {"step_id": str(uuid4())},
        "review": {"reviewer_with_fix": True},
    }
    assert seal_worker_snapshot(git, state, manager, request, deps) is None
    assert deps.worker.seal_output.call_count == 1
    path.write_text("fixed implementation")
    assert seal_worker_snapshot(git, state, manager, request, deps) == fixed
    assert seal_worker_snapshot(git, state, manager, request, deps) == fixed
    assert deps.worker.seal_output.call_count == 3


def test_publication_rechecks_sealed_ref_after_candidate_preparation(tmp_path, snapshot):
    from skm.modules.execution.domain.ids import ExternalEffectId

    git, root, head, writer = snapshot
    git.run(root, ["update-ref", "refs/heads/integration", head])
    output_id, digest = uuid4(), "sha256:" + "c" * 64
    writer.write(git, head)
    writer.confirm(git, head, output_id=output_id, manifest_digest=digest)
    adapter = integration.GitIntegrator(
        git, worktrees_root=tmp_path / "integration", now=Mock(), monotonic=lambda: 0.0
    )
    effect = ExternalEffectId(uuid4())
    slot = {"fencing_token": 1}
    request = adapter.prepare_integration(
        root,
        effect,
        {
            "attempt_id": str(writer.attempt_id),
            "mount": writer.mount,
            "repository_id": str(uuid4()),
            "target_branch": "integration",
            "baseline_sha": head,
            "assignment_fencing_token": writer.fence,
            "outputs": [
                {"output_id": str(output_id), "output_no": 1, "head_sha": head, "output_digest": digest}
            ],
        },
        slot=slot,
    )
    git.run(root, ["update-ref", "-d", writer.sealed_ref])
    client = Mock()
    with pytest.raises(SkmError, match="immutable output ref"):
        adapter.publish_integration(root, effect, request, slot=slot, client=client)
    client.record_effect.assert_not_called()
    assert git.run(root, ["rev-parse", "refs/heads/integration"]).stdout.strip() == head
