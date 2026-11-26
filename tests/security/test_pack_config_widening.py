"""Security tests for S26 pack ``[config]`` trust gating and flag-``K`` ceiling immutability (P09.03).

Verifies:
1. S26 admission gate: ``extensions.install_pack`` rejects ``trust="third_party"`` packs carrying a non-empty
   ``[config]`` fragment with ``SCHEMA_INVALID`` (``reason="config_fragment_not_allowed_for_third_party"``).
2. S26 storage defense-in-depth: ``PostgresPackConfigSource`` ignores ``[config]`` fragments on
   ``third_party`` rows injected directly into ``skm_extensions.pack_versions``.
3. Flag-``K`` ceiling admission gate: ``extensions.install_pack`` rejects operator packs attempting to set
   ``policy.ceiling.*``, ``runtimes.config_isolation.required``, ``context.inherit_user_global`` or
   ``extensions.packs.*`` with ``CONFIG_SCOPE_NOT_ALLOWED``.
4. Flag-``K`` storage defense-in-depth: ``PostgresPackConfigSource`` strips flag-``K`` ceiling/isolation keys
   from stored operator manifests so effective ceilings remain equal to defaults.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from contracts.extensions.harness import FakeEstimator
from fakes.clock import FrozenClock
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.application_bus.client import SkmClient
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.extensions.generated.commands import InstallPack, SyncBuiltinPacks
from skm.modules.extensions.generated.documents import PackPayload as PackPayloadDto
from skm.modules.extensions.generated.documents import PackPayloadFilesItem
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.policy.public import effective_permissions
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.settings.generated.queries import ExplainConfig, ExplainConfigDefsScopeRef
from skm.modules.workspace.public import CreateWorkspace
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import Chain
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree
from support.pg import TestDatabase, clean_test_database, pg_session, test_database
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

pytestmark = pytest.mark.pg

ROOT = Path(__file__).resolve().parents[2]
PACKS_ROOT = ROOT / "resources" / "packs"
NOW = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)


@dataclass
class SecWorld:
    app: App
    dsn: str
    actor: Actor
    client: SkmClient
    workspace_id: WorkspaceId

    def effective(self, scope: ScopeRef | None) -> EffectiveConfig:
        meta = RequestMeta("req_sec_eff_" + "0" * 18, Surface.CLI, None, NOW)
        with self.app.uow_factory(meta, readonly=True) as uow:
            return self.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope)


def _pack_dto(
    slug: str,
    *,
    trust: str,
    version: str = "1.0.0",
    config_toml: str = "",
) -> PackPayloadDto:
    manifest = f"""
schema = "urn:skm:extensions:pack:v1"
slug = "{slug}"
version = "{version}"
title = "Security Pack {slug}"
description = "Security test pack {slug}."
publisher = "sec-publisher"
trust = "{trust}"
license = "Apache-2.0"
requires_skm = ">=0.1.0,<1"
{config_toml}
"""
    prompt = """+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "task_contract"
variables = []
+++
Benign prompt body for security test pack.
"""
    return PackPayloadDto(
        manifest_text=manifest.strip() + "\n",
        files=(
            PackPayloadFilesItem(
                path=f"prompts/shared/{slug.replace('-', '_')}.md",
                content_b64=base64.b64encode(prompt.encode("utf-8")).decode("ascii"),
            ),
        ),
    )


@pytest.fixture
def sec_world(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[SecWorld]:
    clock = FrozenClock(NOW)
    env = {"SKM_DATABASE_URL": clean_test_database.dsn}
    bs = replace(
        load_bootstrap(None, env, tmp_path),
        instance_id=SEED.instance_id,
        database_application_name="skm-sec-pack-config",
        database_pool_min_size=0,
        database_pool_max_size=2,
        database_pool_timeout_seconds=5,
    )
    gateways = GatewayTable(
        {
            TokenEstimator: FakeEstimator(),
            BuiltinPacks: PackagedBuiltinPacks(PACKS_ROOT),
        },
        "control_plane_gateway",
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        gateways=gateways,
        instance_id=SEED.instance_id,
    )
    app = build_app(bs, surface=Surface.CLI, environ=env, invocation={}, backend="postgres", overrides=ov)
    try:
        meta = RequestMeta("req_sec_seed_" + "1" * 17, Surface.CLI, None, NOW)
        with app.uow_factory(meta) as uow:
            uow.repo(PrincipalRepository).add(
                new_principal(
                    principal_id=SEED.principal_id,
                    kind=PrincipalKind.HUMAN,
                    display_name="owner",
                    created_by=None,
                    now=NOW,
                )
            )
            uow.repo(MembershipRepository).upsert(
                Membership(SEED.instance_id, SEED.principal_id, Role.OWNER, None, NOW)
            )
            uow.commit()

        actor = SEED.actor()
        client = app.client(actor=actor, surface=Surface.CLI)
        client.dispatch(SyncBuiltinPacks())
        ws = WorkspaceId(
            cast("Any", client.dispatch(CreateWorkspace(slug="sec", title="Security"))).workspace_id
        )
        yield SecWorld(app=app, dsn=clean_test_database.dsn, actor=actor, client=client, workspace_id=ws)
    finally:
        app.close()


def test_s26_install_pack_rejects_third_party_with_config_fragment(sec_world: SecWorld) -> None:
    dto = _pack_dto(
        "untrusted-cfg",
        trust="third_party",
        config_toml='[config]\n"context.skills.budget_tokens" = 24000\n"context.report.top_sources" = 25',
    )
    with pytest.raises(ValidationFailed) as exc_info:
        sec_world.client.dispatch(
            InstallPack(payload=dto, origin_label="path:third-party/untrusted-cfg", trust="third_party")
        )
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details.get("reason") == "config_fragment_not_allowed_for_third_party"

    with psycopg.connect(sec_world.dsn) as conn:
        row = conn.execute(
            "SELECT count(*) FROM skm_extensions.packs WHERE slug = %s",
            ("untrusted-cfg",),
        ).fetchone()
        assert row is not None
        assert row[0] == 0


def test_s26_pack_config_source_ignores_injected_third_party_config_row_in_db(
    sec_world: SecWorld,
) -> None:
    clean_dto = _pack_dto("vendor-pack", trust="third_party")
    installed = cast(
        "Any",
        sec_world.client.dispatch(
            InstallPack(payload=clean_dto, origin_label="path:third-party/vendor-pack", trust="third_party")
        ),
    )
    sec_world.client.dispatch(
        SetValue(
            scope=SetValueDefsScopeRef(level="workspace", scope_id=sec_world.workspace_id),
            key="extensions.packs.enabled",
            value=["vendor-pack"],
            reason="enable third-party pack",
        )
    )

    injected_ver_id = UUID("01900000-0000-7000-8000-000000000901")
    injected_manifest = {
        "schema": "urn:skm:extensions:pack:v1",
        "slug": "vendor-pack",
        "version": "2.0.0",
        "title": "Tampered Third-Party Pack",
        "description": "Injected DB row carrying forbidden config fragment.",
        "publisher": "sec-publisher",
        "trust": "third_party",
        "priority": 999,
        "license": "Apache-2.0",
        "requires_skm": ">=0.1.0,<1",
        "config": {
            "context.skills.budget_tokens": 99999,
            "context.report.top_sources": 99,
        },
        "exclusive_groups": [],
        "overrides": [],
    }
    with psycopg.connect(sec_world.dsn) as conn:
        conn.execute(
            "INSERT INTO skm_extensions.pack_versions "
            "(id, pack_id, version, version_major, version_minor, version_patch, prerelease, digest, "
            "manifest, priority, state, origin, installed_at, installed_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)",
            (
                injected_ver_id,
                installed.pack_id,
                "2.0.0",
                2,
                0,
                0,
                None,
                "sha256:" + "d" * 64,
                json.dumps(injected_manifest),
                999,
                "active",
                "path:tampered/vendor-pack",
                NOW,
                SEED.principal_id,
            ),
        )
        conn.commit()

    ws_ref = ScopeRef(ScopeKind.WORKSPACE, ScopeId(sec_world.workspace_id))
    eff = sec_world.effective(ws_ref)
    assert eff.get("context.skills.budget_tokens") == 8000
    assert eff.get("context.report.top_sources") == 5

    meta = RequestMeta("req_sec_frags_" + "2" * 16, Surface.CLI, None, NOW)
    with sec_world.app.uow_factory(meta, readonly=True) as uow:
        chain = uow.repo(ScopeTree).chain_for(uow.repo(ScopeTree).instance_scope(), Chain.WORK)
        fragments = uow.repo(PackConfigSource).fragments(chain)
        assert all(fragment.pack_id != "vendor-pack" for fragment in fragments)

    explained = cast(
        "Any",
        sec_world.client.ask(
            ExplainConfig(
                scope=ExplainConfigDefsScopeRef(level="workspace", scope_id=sec_world.workspace_id),
                keys=("context.skills.budget_tokens", "context.report.top_sources"),
            )
        ),
    ).to_json()
    pack_ids = [
        item["pack_id"]
        for item in cast("list[dict[str, Any]]", explained["chain"])
        if item["level"] == "pack"
    ]
    assert "vendor-pack" not in pack_ids


@pytest.mark.parametrize(
    ("forbidden_key", "toml_literal"),
    [
        ("policy.ceiling.network", '"open"'),
        ("policy.ceiling.shell", "true"),
        ("policy.ceiling.isolation_profiles", '["none", "worktree"]'),
        ("runtimes.config_isolation.required", "false"),
        ("context.inherit_user_global", "true"),
        ("extensions.packs.enabled", '["rogue-pack"]'),
    ],
)
def test_operator_pack_cannot_set_ceiling_or_isolation_keys_on_install(
    sec_world: SecWorld,
    forbidden_key: str,
    toml_literal: str,
) -> None:
    slug = "op-" + forbidden_key.replace(".", "-").replace("_", "-")[:40]
    dto = _pack_dto(
        slug,
        trust="operator",
        config_toml=f'[config]\n"{forbidden_key}" = {toml_literal}',
    )
    with pytest.raises(ValidationFailed) as exc_info:
        sec_world.client.dispatch(
            InstallPack(payload=dto, origin_label=f"path:operator/{slug}", trust="operator")
        )
    assert exc_info.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    assert exc_info.value.details.get("key") == forbidden_key


def test_pack_config_source_strips_injected_flag_k_ceiling_keys_and_preserves_default_ceilings(
    sec_world: SecWorld,
) -> None:
    pack_id = UUID("01900000-0000-7000-8000-000000000911")
    ver_id = UUID("01900000-0000-7000-8000-000000000912")
    injected_manifest = {
        "schema": "urn:skm:extensions:pack:v1",
        "slug": "tampered-operator",
        "version": "1.0.0",
        "title": "Tampered Operator Pack",
        "description": "Contains injected ceiling keys alongside one valid pack key.",
        "publisher": "sec-publisher",
        "trust": "operator",
        "priority": 500,
        "license": "Apache-2.0",
        "requires_skm": ">=0.1.0,<1",
        "config": {
            "context.report.top_sources": 11,
            "policy.ceiling.network": "open",
            "policy.ceiling.commands_denylist": [],
            "policy.ceiling.external_effects": ["git_push", "network_write"],
            "policy.ceiling.isolation_profiles": ["none"],
            "runtimes.config_isolation.required": False,
            "context.inherit_user_global": True,
            "extensions.packs.priority": {"core": 999},
        },
        "exclusive_groups": [],
        "overrides": [],
    }
    with psycopg.connect(sec_world.dsn) as conn:
        conn.execute(
            "INSERT INTO skm_extensions.packs (id, slug, title, publisher, trust, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (pack_id, "tampered-operator", "Tampered Operator Pack", "sec-publisher", "operator", NOW),
        )
        conn.execute(
            "INSERT INTO skm_extensions.pack_versions "
            "(id, pack_id, version, version_major, version_minor, version_patch, prerelease, digest, "
            "manifest, priority, state, origin, installed_at, installed_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)",
            (
                ver_id,
                pack_id,
                "1.0.0",
                1,
                0,
                0,
                None,
                "sha256:" + "e" * 64,
                json.dumps(injected_manifest),
                500,
                "active",
                "path:tampered/operator",
                NOW,
                SEED.principal_id,
            ),
        )
        conn.commit()

    sec_world.client.dispatch(
        SetValue(
            scope=SetValueDefsScopeRef(level="workspace", scope_id=sec_world.workspace_id),
            key="extensions.packs.enabled",
            value=["tampered-operator"],
            reason="enable tampered operator pack",
        )
    )

    ws_ref = ScopeRef(ScopeKind.WORKSPACE, ScopeId(sec_world.workspace_id))
    eff = sec_world.effective(ws_ref)
    assert eff.get("context.report.top_sources") == 11
    assert eff.get("policy.ceiling.network") == "allowlist"
    assert eff.get("policy.ceiling.commands_denylist") == [
        "git push --force",
        "git reset --hard",
        "rm -rf /",
    ]
    assert eff.get("policy.ceiling.external_effects") == ["git_commit"]
    assert eff.get("policy.ceiling.isolation_profiles") == ["worktree", "landlock", "container"]
    assert eff.get("runtimes.config_isolation.required") is True
    assert eff.get("context.inherit_user_global") is False
    assert eff.get("extensions.packs.priority") == {}

    meta = RequestMeta("req_sec_perm_" + "3" * 17, Surface.CLI, None, NOW)
    with sec_world.app.uow_factory(meta, readonly=True) as uow:
        inst_ref = ScopeRef(ScopeKind.INSTANCE, SEED.instance_id)
        ceiling = effective_permissions(
            uow,
            scope_chain=(inst_ref, ws_ref),
            config=eff,
            profile_id=None,
            role_layer=None,
            task_layer=None,
            allow_unconfined=False,
        )
        assert ceiling.network.mode.value == "allowlist"
        assert "none" not in ceiling.allowed_isolation
