"""P09.Z acceptance: pinned resources, exact context, real PostgreSQL and local processes."""

import json
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from contracts.context.harness import ctx_side as ctx_side
from contracts.context.test_owner_guard import dispatch, owned_draft
from contracts.execution.harness import exec_side as exec_side
from e2e.test_execution_cli import invoke, result
from e2e.test_review_request import command, request
from e2e.test_review_request import review_side as review_side
from fixtures.e2e.m4.support import ROOT, core, host, overlay
from fixtures.e2e.m4.worker import assert_explanation
from fixtures.execution.harness import recovery as recovery
from fixtures.execution.single_run import run_worker, single_run, successful_script
from integration.research._support import host as research_host
from integration.research._support import spec
from integration.worker.test_context_publication import setup_prompt
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.context import public as context
from skm.modules.context.host.research_query import research_query
from skm.modules.context.ports import ResearchRepository
from skm.modules.execution.host.context_inputs import finalize_stage_context
from skm.modules.execution.ports import BundleRepository, RunRepository, TaskRepository
from skm.modules.extensions import public as extensions
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.planning.generated.queries import ListPlans
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.platform.config.store import ConfigStore, ScopeTree
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

pytestmark = [pytest.mark.e2e, pytest.mark.pg]


def config(side: Any, key: str, value: Any) -> None:
    side.client.dispatch(
        SetValue(scope=SetValueDefsScopeRef(level="instance"), key=key, value=value, confirmed=True),
        idempotency_key=side.client.new_idempotency_key(),
    )


def resolved(side: Any, pins: Any = None) -> Any:
    with side.uow(readonly=True) as uow:
        cfg = side.app.config.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PROJECT, side.proj)
        )
        return tuple(
            extensions.resolve_resource(uow, kind, key, config=cfg, pins=pins)
            for kind, key in (
                (extensions.ResourceKind.PROMPT_BLOCK, "shared/system"),
                (extensions.ResourceKind.RUNTIME_CATALOG, "models"),
                (extensions.ResourceKind.AGENT_PROFILE, "executor"),
            )
        )


@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_active_run_keeps_overlay_catalog_and_exact_prompt(exec_side: Any, tmp_path: Path, monkeypatch: Any):  # noqa: PLR0915 - one continuous acceptance trace
    side = exec_side
    core(side, "1.2.0", "M4 core v1")
    assert result(side, "ext", "sync")["installed"]
    factory = host(side)
    first = overlay(tmp_path / "overlay1", "1.0.0", config='"context.report.top_sources" = 7')
    result(side, "-vv", "ext", "install", str(first), "--trust", "operator", host=factory)
    config(side, "extensions.packs.enabled", ["m4-overlay"])
    explained = result(side, "config", "explain")
    entry = next(row for row in explained["keys"] if row["key"] == "context.report.top_sources")
    assert entry["value"] == 7
    assert entry["winner"] == {"level": "pack", "pack_id": "m4-overlay", "pack_priority": 100}
    case, _, step, draft, ctx, env, claim, begin, inputs = setup_prompt(side, tmp_path, monkeypatch)
    with side.uow(readonly=True) as uow:
        bundle = uow.repo(BundleRepository).get(case.run.id)
    assert step is not None
    assert draft is not None
    pins = bundle.resource_pins.packs
    before = resolved(side, pins)
    catalog_before = catalog(side, pins)
    commands = []

    def capture(raw: Any) -> Any:
        dto = inputs.finalize_dto(raw)
        commands.append(dto)
        return dto

    final = finalize_stage_context(
        ctx, claim, cast(JsonObject, begin), env, replace(inputs, finalize_dto=capture), workspace_id=side.ws
    )
    assert "M4 overlay 1.0.0" in final.rendered_prompt
    core(side, "2.0.0", "M4 core v2")
    result(side, "ext", "sync")
    second = overlay(tmp_path / "overlay2", "2.0.0", config='"context.report.top_sources" = 9')
    result(side, "-vv", "ext", "install", str(second), "--trust", "operator", host=factory)
    assert resolved(side, pins) == before
    assert catalog(side, pins) == catalog_before
    assert catalog(side) != catalog_before
    assert all(
        a.resource_version_id != b.resource_version_id for a, b in zip(before, resolved(side), strict=True)
    )
    assert ctx.client.dispatch(commands[0])
    prompt = result(side, "run", "step-prompt", str(step.id))["text"].encode("utf-8")
    assert prompt == final.rendered_prompt.encode("utf-8")
    with side.uow(readonly=True) as uow:
        manifest = context.require_final(uow, draft.manifest_id)
        assert uow.repo(BundleRepository).get(case.run.id) == bundle
    with side.client.open_file_version_content(manifest.prompt_file_version_id) as stream:
        assert stream.read() == prompt
    assert manifest.prompt_digest == "sha256:" + sha256(prompt).hexdigest()
    explanation = result(side, "run", "step-context", str(step.id), "--blocks")
    assert_explanation(explanation, manifest)
    for block in manifest.blocks:
        assert block.source_kind
        assert block.source_ref
        assert block.reason
        if block.included:
            assert block.content_digest
            assert block.tokens_estimate is not None
    # A new run uses the newly enabled versions, while the original remains immutable.
    next_case = setup_prompt(side, tmp_path / "next", monkeypatch)
    with side.uow(readonly=True) as uow:
        new_bundle = uow.repo(BundleRepository).get(next_case[0].run.id)
    assert new_bundle.resource_pins.packs != pins
    next_final = finalize_stage_context(
        next_case[4],
        next_case[6],
        cast(JsonObject, next_case[7]),
        next_case[5],
        next_case[8],
        workspace_id=side.ws,
    )
    assert "M4 overlay 2.0.0" in next_final.rendered_prompt
    assert next_final.prompt_digest != final.prompt_digest
    # Exact resource pin: quarantine must not fall back to core or a later overlay.
    side.client.dispatch(
        SetValue(
            scope=SetValueDefsScopeRef(level="project", scope_id=side.proj),
            key="extensions.resources.pinned",
            value={"prompt_block:shared/system": before[0].digest},
        ),
        idempotency_key=side.client.new_idempotency_key(),
    )
    result(side, "ext", "quarantine", str(before[0].resource_version_id), "--reason", "M4 revoked")
    with pytest.raises(SkmError) as denied:
        resolved(side, pins)
    assert denied.value.code.value == "RESOURCE_QUARANTINED"


@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
@pytest.mark.parametrize(
    ("trust", "fragment", "code"),
    [
        ("third_party", '"context.report.top_sources" = 7', "SCHEMA_INVALID"),
        ("operator", '"policy.ceiling.network" = "any"', "CONFIG_SCOPE_NOT_ALLOWED"),
        ("operator", '"extensions.packs.enabled" = ["m4-overlay"]', "CONFIG_SCOPE_NOT_ALLOWED"),
        ("operator", '"context.inherit_user_global" = true', "CONFIG_SCOPE_NOT_ALLOWED"),
    ],
)
def test_pack_security_admission_rolls_back(
    exec_side: Any, tmp_path: Path, trust: str, fragment: str, code: str
):
    path = overlay(tmp_path / "bad", "1.0.0", config=fragment, trust=trust)
    status, out, err = invoke(exec_side, "ext", "install", str(path), "--trust", trust, host=host(exec_side))
    assert status != 0, err
    assert json.loads(out)["error"]["code"] == code
    assert "m4-overlay" not in json.dumps(result(exec_side, "ext", "list"))


@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_stale_owner_cannot_publish_or_replay(exec_side: Any):
    case = owned_draft(exec_side)
    from security.test_context_stale_claim import expire

    expire(case)
    with pytest.raises(SkmError) as caught:
        dispatch(case)
    assert caught.value.code.value == "LEASE_LOST"
    with exec_side.uow(readonly=True) as uow:
        assert context.get_manifest(uow, case.draft.manifest_id).state.value == "draft"


@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_review_only_service_revision_is_pinned_hidden_and_idempotent(review_side: Any):
    side = review_side
    key = side.client.new_idempotency_key()
    created = request(side, command(side), key=key)
    assert request(side, command(side), key=key) == created
    from uuid import UUID

    with side.uow(readonly=True) as uow:
        run = uow.repo(RunRepository).get(UUID(created["run_id"]))
        bundle = uow.repo(BundleRepository).get(run.id)
        tasks = uow.repo(TaskRepository).list_for_run(run.id)
    assert run.kind.value == "review_request"
    assert not run.autopilot
    assert len(tasks) == 1
    assert not tasks[0].declared_write_scope
    assert any(p.kind == "workflow" and p.key == "review-only" for p in bundle.resource_pins.resources)
    assert all(p.plan_id != run.plan_id for p in side.client.ask(ListPlans(project_id=side.proj)).items)


@pytest.mark.parametrize("ctx_side", ["postgres"], indirect=True)
def test_research_ladder_real_commands_and_pg_ledger(ctx_side: Any):
    side = ctx_side
    sources: dict[str, Any] = {
        name.replace("_", "-"): {
            "kind": "command",
            "tier": name,
            "argv": [sys.executable, str(ROOT / "tests/fixtures/e2e/m4/research.py"), name],
            "capabilities": ["search", "citations"],
            "trust_cap": "repository",
            "classification": "internal",
        }
        for name in ("local_docs", "codegraph", "external_search", "deep_research")
    }
    config(side, "context.research.sources", sources)
    config(side, "context.research.allow_deep", True)
    ctx = research_host(
        client=side.client,
        clock=side.clock,
        sources=sources,
        settings={"context.research.allow_deep": True, "context.research.min_documents": 10},
    )
    batch = research_query(
        ctx,
        spec(depth="deep", use_cache=False),
        workspace_id=side.ws,
        project_id=side.proj,
        step_ref=None,
        mounts={},
    )
    assert [r.source_id for r in batch.results] == list(sources)
    assert [r.status for r in batch.results] == ["empty", "empty", "ok", "ok"]
    assert not batch.results[0].documents
    assert not batch.results[1].documents
    assert batch.results[2].documents
    assert batch.results[3].documents
    with side.uow(readonly=True) as uow:
        for r in batch.results:
            stored = uow.repo(ResearchRepository).get(r.query_id)
            assert stored["source_id"] == r.source_id
            assert stored["workspace_id"] == str(side.ws)
    # Explicit source choice also uses a real command and persists an honest error.
    sources["deep-research"]["argv"] = ["/nonexistent/m4-source"]
    config(side, "context.research.sources", sources)
    failed = research_query(
        ctx,
        spec(sources=("deep-research",), depth="deep", use_cache=False),
        workspace_id=side.ws,
        project_id=side.proj,
        step_ref=None,
        mounts={},
    )
    assert failed.results[0].status == "error"
    assert failed.results[0].expires_at is None


def test_full_context_m3_worker_keeps_run_pins_after_core_upgrade(recovery: Any, monkeypatch: Any):  # noqa: PLR0915 - two complete real worker traces
    side = recovery
    from fixtures.execution import single_run as single_support

    make_repo = single_support.make_repo

    def repository_with_instructions(path: Any) -> Any:
        created = make_repo(path)
        (path / "AGENTS.md").write_text("M4 runtime observed instructions: café 🧪\n")
        return created

    monkeypatch.setattr(single_support, "make_repo", repository_with_instructions)
    builtin = side.app.gateways.get(BuiltinPacks)
    payload = builtin.current[0]
    old_files = tuple(
        replace(f, content=b"M4 PINNED OLD TEXT\n") if f.path == "prompts/shared/system.md" else f
        for f in payload.files
    )
    payload = replace(
        payload,
        manifest_text=payload.manifest_text.replace('version = "1.3.0"', 'version = "1.4.0"'),
        files=old_files,
    )
    monkeypatch.setattr(builtin, "current", (payload,))
    result(side, "ext", "sync")
    config(side, "extensions.packs.versions", {"core": "1.4.0"})
    case = single_run(side)
    with side.uow(readonly=True) as uow:
        bundle = uow.repo(BundleRepository).get(case.run.id)
    builtin = side.app.gateways.get(BuiltinPacks)
    payload = builtin.current[0]
    upgraded = replace(
        payload,
        manifest_text=payload.manifest_text.replace('version = "1.4.0"', 'version = "2.0.0"'),
        files=tuple(
            replace(f, content=b"M4 ENABLED NEW TEXT\n") if f.path == "prompts/shared/system.md" else f
            for f in payload.files
        ),
    )
    monkeypatch.setattr(builtin, "current", (upgraded,))
    result(side, "ext", "sync")
    config(side, "extensions.packs.versions", {"core": "2.0.0"})
    import subprocess

    popen = subprocess.Popen  # noqa: TID251 - observe the owned worker subprocess without replacing its protocol

    def observed_worker(argv: Any, **kwargs: Any) -> Any:
        if argv[1:3] == ["-m", "fixtures.execution.worker_process"]:
            argv = [argv[0], "-m", "fixtures.e2e.m4.worker", *argv[3:]]
        return popen(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", observed_worker)
    run_worker(side, case, successful_script(side, case.task.display_key))
    from uuid import UUID

    from skm.modules.execution.generated.queries import GetStep

    handoffs = list((side.root / "state/m4-handoff").glob("*.prompt"))
    assert len(handoffs) >= 2
    for handoff in handoffs:
        prompt = handoff.read_bytes()
        assert prompt == result(side, "run", "step-prompt", handoff.stem)["text"].encode()
        explained = result(side, "run", "step-context", handoff.stem, "--blocks")
        assert b"M4 PINNED OLD TEXT" in prompt
        assert b"M4 ENABLED NEW TEXT" not in prompt
        view = side.client.ask(GetStep(step_id=UUID(handoff.stem)))
        with side.uow(readonly=True) as uow:
            saved = context.require_final(uow, view.context_manifest_id)
            assert_explanation(explained, saved)
            assert cast(Any, saved.route["self_loads_observed"])[0]["files"] == ["AGENTS.md"]
        assert (
            json.loads(handoff.with_suffix(".json").read_text())["digest"]
            == "sha256:" + sha256(prompt).hexdigest()
        )
    with side.uow(readonly=True) as uow:
        assert uow.repo(BundleRepository).get(case.run.id) == bundle
        tasks = uow.repo(TaskRepository).list_for_run(case.run.id)
        assert tasks[0].status.value == "accepted"
    assert (
        case.git.run(case.repository, ["show", f"skm/integration/{case.run.id}:src/target.py"]).stdout
        == "answer = 42\n"
    )

    from fixtures.execution.harness import system_dispatch
    from fixtures.execution.m3 import start

    new = start(side, case.run.revision_id, keys=(case.task.display_key,))
    case.git.run(case.repository, ["branch", f"skm/integration/{new.run_id}", "main"])
    system_dispatch(side, "schedule_ready_tasks")
    (side.root / "state").rename(side.root / "old-state")
    run_worker(side, case, successful_script(side, case.task.display_key))
    fresh = list((side.root / "state/m4-handoff").glob("*.prompt"))
    assert len(fresh) >= 2
    for path in fresh:
        raw = path.read_bytes()
        assert b"M4 ENABLED NEW TEXT" in raw
        assert b"M4 PINNED OLD TEXT" not in raw
        assert raw == result(side, "run", "step-prompt", path.stem)["text"].encode()
        view = side.client.ask(GetStep(step_id=UUID(path.stem)))
        with side.uow(readonly=True) as uow:
            saved = context.require_final(uow, view.context_manifest_id)
            assert saved.prompt_digest == "sha256:" + sha256(raw).hexdigest()
            assert_explanation(result(side, "run", "step-context", path.stem, "--blocks"), saved)


def test_skills_reconciliation_matches_porting_report():
    export = json.loads((ROOT / "resources/overlays/exports.json").read_text())
    counts = export["counts"]
    assert counts["packs"] == len(export["packs"])
    assert counts["migrated"] == sum(p["skill_count"] for p in export["packs"])
    assert counts["excluded"] == len(export["excluded_skills"])
    assert counts["source_total"] == counts["migrated"] + counts["excluded"]
    for pack in export["packs"]:
        skills = {skill["key"] for skill in pack["skills"]}
        assert len(skills) == len(pack["skills"]) == pack["skill_count"]
        skill_files = (ROOT / pack["path"]).glob("skills/*/SKILL.md")
        assert skills == {path.parent.name for path in skill_files if path.is_file()}


@pytest.mark.parametrize("ctx_side", ["postgres"], indirect=True)
@pytest.mark.parametrize("failure", ["missing", "overbudget"])
def test_required_context_fails_closed(ctx_side: Any, tmp_path: Path, failure: str):
    from contracts.context.harness import _spec_doc
    from contracts.execution.harness import _publish_revision
    from skm.adapters.git.host_inputs import GitCheckoutReader

    side = ctx_side
    patch: Any = _spec_doc(side.mat_fv_id)
    patch["materials"][1]["required_for"] = ["execution"]
    revision = _publish_revision(
        side.app, side.client, side.owner, side.clock, side.plan_id, patch, "current"
    )
    side = replace(side, rev_id=revision)
    if failure == "overbudget":
        from contracts.context.harness import core_pack
        from skm.modules.extensions.generated.commands import SyncBuiltinPacks

        config(side, "context.max_total_tokens", 4000)
        side.builtin.current = (core_pack("2.0.0", system_body="Mandatory invariant. " * 1200),)
        side.client.dispatch(SyncBuiltinPacks())
        (tmp_path / "src").mkdir()
        (tmp_path / "src/target.py").write_text("answer = 42\n")
    draft = None

    def prepare_and_finalize():
        nonlocal draft
        with side.uow() as uow:
            cfg = side.effective_config(uow)
            draft = context.assemble_draft(
                uow,
                side.app.gateways,
                side.make_request(uow, config=cfg),
                config=cfg,
                owner_ref="step:run:1/step:1",
            )
            uow.commit()
        blocks, facts = context.collect_host_blocks(
            draft.host_inputs,
            GitCheckoutReader({"repo": tmp_path}),
            side.estimator,
            total_max_bytes=2_000_000,
            max_work_paths=100,
            repo_max_files=8,
            path_patterns=(),
            research={},
            draft=draft,
        )
        context.finalize(draft, blocks, facts, side.estimator)

    with pytest.raises(SkmError) as caught:
        prepare_and_finalize()
    assert caught.value.code.value == (
        "CONTEXT_INPUT_MISSING" if failure == "missing" else "CONTEXT_OVER_BUDGET"
    )
    if draft is None:
        assert failure == "overbudget"
        assert cast(int, caught.value.details["mandatory_tokens"]) > cast(
            int, caught.value.details["total_limit"]
        )
    else:
        with side.uow(readonly=True) as uow:
            saved = context.get_manifest(uow, draft.manifest_id)
            assert saved.state.value == "draft"
            assert saved.prompt_file_version_id is None


@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_profile_cannot_widen_instance_ceiling(exec_side: Any):
    from contracts.extensions.harness import pack_payload, profile_toml
    from security.test_extension_permissions import _dto

    config(exec_side, "policy.default_profile", "read-only")
    payload = pack_payload("wide", trust="operator", files={"agent-profiles/wide.toml": profile_toml("wide")})
    with pytest.raises(SkmError) as caught:
        exec_side.client.dispatch(_dto(payload, trust="operator"))
    assert caught.value.code.value == "EXTENSION_WIDENS_PERMISSIONS"
    assert '"slug": "wide"' not in json.dumps(result(exec_side, "ext", "list"))


@pytest.mark.parametrize("ctx_side", ["postgres"], indirect=True)
def test_secret_redaction_and_classification_ceiling(ctx_side: Any):
    from uuid import UUID

    from integration.context.test_research_repository import ask, cache, command, record, seed_actor
    from skm.kernel.actor import PrincipalKind
    from skm.kernel.ids import PrincipalId
    from skm.kernel.ports_uow import Surface
    from skm.modules.access.public import Role

    side = ctx_side
    ctx = research_host(client=side.client, clock=side.clock)
    sources = ctx.config["context.research.sources"]
    sources["docs"]["argv"] = [
        sys.executable,
        str(ROOT / "tests/fixtures/e2e/m4/research.py"),
        "external_search",
    ]
    config(side, "context.research.sources", sources)
    batch = research_query(
        ctx, spec(use_cache=False), workspace_id=side.ws, project_id=side.proj, step_ref=None, mounts={}
    )
    doc = batch.results[0].documents[0]
    assert "very-secret-value" not in doc.excerpt
    assert "redacted" in doc.excerpt
    assert doc.content_digest == "sha256:" + sha256(doc.excerpt.encode()).hexdigest()
    with side.uow(readonly=True) as uow:
        assert "very-secret-value" not in json.dumps(
            uow.repo(ResearchRepository).get(batch.results[0].query_id)
        )
    payload = command(side)
    payload["results"][0]["documents"][0]["classification"] = "confidential"
    record(side, payload)
    viewer = seed_actor(side, PrincipalId(UUID(int=99881)), PrincipalKind.HUMAN, Role.VIEWER)
    limited = replace(side, client=side.app.client(actor=viewer, surface=Surface.CLI))
    assert not cache(limited, payload, max_classification="restricted")["hit"]
    with pytest.raises(SkmError):
        ask(limited, "get_research_query", query_id=payload["results"][0]["query_id"])


@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_core_plan_template_via_cli(exec_side: Any):
    from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks

    side = exec_side
    side.app.gateways.get(BuiltinPacks).current = PackagedBuiltinPacks(ROOT / "resources/packs").payloads()
    result(side, "ext", "sync")
    created = result(
        side,
        "plan",
        "create",
        "M4 template",
        "--template",
        "feature",
        "--input",
        "title=M4 template",
        "--input",
        "goal=Verify core template",
    )
    assert created["plan_id"]
    assert created["draft_id"]


def catalog(side: Any, pins: Any = None) -> Any:
    with side.uow(readonly=True) as uow:
        cfg = side.app.config.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PROJECT, side.proj)
        )
        return extensions.runtime_catalog(uow, (), cfg, pins=pins)


@pytest.mark.parametrize("ctx_side", ["postgres"], indirect=True)
def test_included_excluded_and_self_loaded_manifest_metadata(ctx_side: Any, tmp_path: Path):
    from skm.adapters.git.host_inputs import GitCheckoutReader

    side = ctx_side
    (tmp_path / "AGENTS.md").write_text("M4 runtime instructions")
    with side.uow() as uow:
        cfg = side.effective_config(uow)
        draft = context.assemble_draft(
            uow,
            side.app.gateways,
            side.make_request(uow, config=cfg),
            config=cfg,
            owner_ref="step:run:1/step:1",
        )
        uow.commit()
    blocks, facts = context.collect_host_blocks(
        draft.host_inputs,
        GitCheckoutReader({"repo": tmp_path}),
        side.estimator,
        total_max_bytes=2_000_000,
        max_work_paths=100,
        repo_max_files=8,
        path_patterns=(),
        research={},
        draft=draft,
    )
    final = context.finalize(draft, blocks, facts, side.estimator)
    rows = final.manifest.blocks
    assert any(row.included for row in rows)
    assert any(row.included is False for row in rows)
    assert any(row.reason == "runtime_self_loaded" for row in rows)
    for row in rows:
        assert row.source_kind
        assert row.source_ref
        assert row.trust
        assert row.reason
        if row.included:
            assert row.source_version
            assert row.content_digest
            assert row.tokens_estimate is not None
