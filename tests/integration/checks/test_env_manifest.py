"""Synthetic immutable facts test the pure canonical rule, never prove a host toolchain."""

from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest

from skm.adapters.checks.registry import can_reuse, check_fingerprint
from skm.kernel.ids import AttemptId, EntityId, RunId, TaskId, WorkspaceId
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.ids import CheckExecutionId, OutputId

TREE = "sha256:" + "1" * 64
SPEC = "sha256:" + "2" * 64


def complete_manifest():
    return {
        "host_id": "host-1",
        "checkout_binding": {"root_inode": 101, "git_inode": 102},
        "executable": {"digest": "sha256:binary", "immutable": True},
        "toolchain": {"closure": "sha256:closure"},
        "dependencies": [{"lock": "sha256:lock", "immutable": True}],
        "path": "/immutable/bin",
        "environment": {"PATH": "/immutable/bin", "LANG": "C", "BUILD_MODE": "release"},
        "isolation_profile": "container",
        "backend": {"id": "backend", "version": "1"},
        "image": "image@sha256:immutable",
        "network": {"mode": "none", "hosts": []},
        "credentials": [{"role": "build", "version": "version-1"}],
        "external_inputs": [{"digest": "sha256:input"}],
        "immutable": True,
        "closure_verified": True,
        "path_immutable": True,
    }


def passed(fingerprint):
    return CheckExecution(
        CheckExecutionId(uuid4()),
        WorkspaceId(uuid4()),
        RunId(uuid4()),
        TaskId(uuid4()),
        AttemptId(uuid4()),
        OutputId(uuid4()),
        EntityId(uuid4()),
        "check",
        CheckKind.COMMAND,
        True,
        CheckState.PASSED,
        0,
        "ok",
        None,
        None,
        fingerprint,
        None,
        None,
        1,
    )


def test_equal_complete_current_closure_reuses_only_passed_scoped_receipt():
    manifest = complete_manifest()
    fingerprint = check_fingerprint(TREE, SPEC, manifest, trusted_current_closure=True)
    assert fingerprint is not None
    source = passed(fingerprint)
    project = uuid4()
    options = {
        "project_id": project,
        "source_project_id": project,
        "workspace_id": source.workspace_id,
        "check_spec_id": source.check_spec_id,
        "fingerprint": fingerprint,
        "evidence_available": True,
        "post_integration": False,
    }
    assert can_reuse(source, **options)
    assert not can_reuse(source, **{**options, "workspace_id": uuid4()})
    assert not can_reuse(source, **{**options, "project_id": uuid4()})
    assert not can_reuse(source, **{**options, "check_spec_id": uuid4()})
    assert not can_reuse(source, **{**options, "evidence_available": False})
    assert not can_reuse(source, **{**options, "post_integration": True})
    assert not can_reuse(replace(source, state=CheckState.FAILED, exit_code=1), **options)
    for kind in (CheckKind.MANUAL, CheckKind.EXTERNAL):
        assert not can_reuse(replace(source, kind=kind), **options)
        assert can_reuse(replace(source, kind=kind), attested=True, **options)


@pytest.mark.parametrize(
    "field", sorted(complete_manifest().keys() - {"immutable", "closure_verified", "path_immutable"})
)
def test_every_identity_change_requires_fresh_check(field):
    original = complete_manifest()
    changed = deepcopy(original)
    changed[field] = (
        {"changed": "new immutable value"} if field != "environment" else {"PATH": "/other/immutable/bin"}
    )
    before = check_fingerprint(TREE, SPEC, original, trusted_current_closure=True)
    after = check_fingerprint(TREE, SPEC, changed, trusted_current_closure=True)
    assert before is not None
    assert after != before


@pytest.mark.parametrize("field", sorted(complete_manifest().keys()))
def test_missing_or_unknown_facts_cannot_authorize_reuse(field):
    manifest = complete_manifest()
    del manifest[field]
    assert check_fingerprint(TREE, SPEC, manifest, trusted_current_closure=True) is None
    manifest[field] = None
    assert check_fingerprint(TREE, SPEC, manifest, trusted_current_closure=True) is None


@pytest.mark.parametrize("flag", ["immutable", "closure_verified", "path_immutable"])
def test_dynamic_dependencies_mutable_path_and_unproved_closure_are_fresh(flag):
    manifest = complete_manifest()
    manifest[flag] = False
    assert check_fingerprint(TREE, SPEC, manifest, trusted_current_closure=True) is None


def test_worker_manifest_and_post_integration_are_always_fresh_without_current_proof():
    manifest = complete_manifest()
    assert check_fingerprint(TREE, SPEC, manifest) is None
    assert (
        check_fingerprint(TREE, SPEC, manifest, trusted_current_closure=True, post_integration=True) is None
    )
    baseline = check_fingerprint(TREE, SPEC, manifest, trusted_current_closure=True)
    manifest["environment"]["SKM_CHECK_ID"] = "new-check-id"
    assert check_fingerprint(TREE, SPEC, manifest, trusted_current_closure=True) == baseline
    manifest["environment"]["BUILD_MODE"] = "debug"
    assert check_fingerprint(TREE, SPEC, manifest, trusted_current_closure=True) != baseline
