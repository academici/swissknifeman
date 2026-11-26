"""Runtime evidence is rejected by content even after renaming; exclusions preserve user files."""

import hashlib
from typing import cast

import pytest

from integration.git.test_integration import make_case, prepare, publish, seal
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import UnitOfWork


@pytest.mark.parametrize("name", ["transcript.txt", "src/copied_prompt.py", "renamed-binary"])
def test_artifact_digest_prevents_commit_and_target_publication(tmp_path, name):
    case = make_case(tmp_path)
    evidence = b"private runtime evidence\0\xff"
    path = case.repo / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(evidence)
    case.inputs["outputs"][0]["head_sha"] = seal(case.git, case.repo, case.baseline, tmp_path / "snapshots")
    case.inputs["artifact_digests"] = ["sha256:" + hashlib.sha256(evidence).hexdigest()]
    with pytest.raises(SkmError) as caught:
        prepare(case)
    assert caught.value.code.value == "RUNTIME_ARTIFACT_IN_COMMIT"
    assert case.git.run(case.repo, ["rev-parse", "integration"]).stdout.strip() == case.before
    assert not case.client.calls
    assert path.read_bytes() == evidence
    assert not list((tmp_path / "owned").rglob(".git"))


def test_excluded_runtime_paths_never_enter_canonical_tree(tmp_path):
    case = make_case(tmp_path)
    evidence = case.repo / ".skm" / "logs" / "transcript"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"runtime trace")
    case.inputs["outputs"][0]["head_sha"] = seal(case.git, case.repo, case.baseline, tmp_path / "snapshots")
    request = prepare(case)
    publish(case, request)
    assert ".skm" not in case.git.run(case.repo, ["ls-tree", "-r", request.after_sha]).stdout
    assert evidence.read_bytes() == b"runtime trace"


def test_begin_artifact_guard_includes_checks_reviews_and_earlier_output_evidence(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from skm.modules.artifacts import public as artifacts
    from skm.modules.execution.application._integration_inputs import artifact_digests
    from skm.modules.execution.ports import EvidenceBindingRepository, ExecutionQueries, StageRepository

    attempt, output, earlier, check, review = [uuid4() for _ in range(5)]
    owners = {
        ("attempt", attempt): uuid4(),
        ("output", output): uuid4(),
        ("output", earlier): uuid4(),
        ("check_execution", check): uuid4(),
        ("review", review): uuid4(),
    }
    bindings = SimpleNamespace(for_owner=lambda kind, identity: [(owners[(kind, identity)], None)])
    view = {
        "outputs": [{"output_id": str(earlier)}, {"output_id": str(output)}],
        "checks": [{"check_execution_id": str(check)}],
        "reviews": [{"review_id": str(review)}],
    }
    ports = {
        EvidenceBindingRepository: bindings,
        ExecutionQueries: SimpleNamespace(attempt_view=lambda _: view),
        StageRepository: SimpleNamespace(history=lambda _: SimpleNamespace(entries=())),
    }
    uow = cast("UnitOfWork", SimpleNamespace(repo=lambda port: ports[port]))
    monkeypatch.setattr(
        artifacts, "get_file_version", lambda _, identity: SimpleNamespace(digest=str(identity))
    )
    actual = artifact_digests(
        uow, SimpleNamespace(attempt=SimpleNamespace(id=attempt)), SimpleNamespace(id=output)
    )
    assert actual == sorted(str(identity) for identity in owners.values())
