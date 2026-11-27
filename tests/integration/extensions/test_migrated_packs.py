"""Integration tests for reproducible skill migration and migrated extension packs (P09.06).

Verifies ``tools/migrate_skills.py`` CLI contracts (``--dry-run``, invalid ``--source``,
idempotent deterministic generation, empty ``sha256`` backfill, zero code execution),
``PackagedBuiltinPacks`` isolation, full 218-skill corpus reconciliation against
``resources/overlays/exports.json``, ``CompatVerdict.CLEAN`` across all committed packs,
and end-to-end ``InstallPack`` persistence on PostgreSQL alongside built-in ``core``.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tomllib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from fakes.clock import FrozenClock
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.extensions.application.candidate import DEFAULT_ALLOWED_LICENSES, build_candidate
from skm.modules.extensions.domain.compat import CompatVerdict
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import PackTrust
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.generated.commands import InstallPack, SyncBuiltinPacks
from skm.modules.extensions.generated.documents import PackPayload as PackPayloadDto
from skm.modules.extensions.generated.documents import PackPayloadFilesItem
from skm.modules.extensions.generated.queries import ListResources
from skm.modules.extensions.generated.queries import ResourceKind as QueryResourceKind
from skm.modules.extensions.generated.views import ResourcesView
from skm.modules.extensions.ports import BuiltinPacks
from skm.platform.config.bootstrap import load_bootstrap
from support.pg import TestDatabase, clean_test_database, pg_session, test_database
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

ROOT = Path(__file__).resolve().parents[3]
MIGRATE_SCRIPT = ROOT / "tools" / "migrate_skills.py"
PACKS_ROOT = ROOT / "resources" / "packs"
EXPORTS_PATH = ROOT / "resources" / "overlays" / "exports.json"
NOW = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)

REQUIRED_EXCLUSIONS = frozenset(
    {
        "axioma-doctrine",
        "axioma-glossary",
        "axioma-stack",
        "ecosystem-map",
        "azguard",
        "botkit",
        "swissknifeman-locator",
        "brain-locator",
        "local-topology",
        "cross-project-coordinator",
        "shared-memory",
        "agent-packs",
        "session-observer",
        "plan-protocol",
        "workflow-craft",
        "skills-ssot",
        "mcp-advisor",
        "defensibility",
        "writing-style",
        "code-review",
    }
)
FORBIDDEN_PERSONAL_TOKENS = ("axioma", "azguard", "botkit", "academici")


class _HeuristicEstimator:
    estimator_id = "heuristic-v1"

    def estimate(self, text: str) -> int:
        return max(1, (len(text) + 3) // 4) if text else 0


def _payload_dto(payload: PackPayload) -> PackPayloadDto:
    files = tuple(
        PackPayloadFilesItem(path=f.path, content_b64=base64.b64encode(f.content).decode("ascii"))
        for f in payload.files
    )
    return PackPayloadDto(manifest_text=payload.manifest_text, files=files)


def _write_synthetic_donor(donor: Path) -> None:
    local_skill = donor / "packages" / "skiller" / "skills" / "devops" / "sample-deploy"
    (local_skill / "snippets").mkdir(parents=True)
    (local_skill / "evals").mkdir(parents=True)
    (local_skill / "scripts").mkdir(parents=True)
    (local_skill / "SKILL.md").write_text(
        "---\nname: sample-deploy\nbucket: devops\nversion: 0.2.0\n"
        'description: "Safe deployment checklist."\nrisk: draft\n---\n\n# Sample Deploy\n\nCheck rollout.\n',
        encoding="utf-8",
    )
    (local_skill / "selection.json").write_text(
        json.dumps({"kind": "procedure", "roles": ["executor"], "triggers": {"paths": ["Dockerfile"]}}),
        encoding="utf-8",
    )
    (local_skill / "snippets" / "sentinel.py").write_text(
        'raise RuntimeError("migrator must never import or execute skill files")\n',
        encoding="utf-8",
    )
    (local_skill / "evals" / "case.json").write_text('{"drop": true}\n', encoding="utf-8")
    (local_skill / "scripts" / "run.py").write_text("raise SystemExit(99)\n", encoding="utf-8")

    github_flow = donor / "packages" / "skiller" / "skills" / "general" / "github-flow"
    github_flow.mkdir(parents=True)
    (github_flow / "SKILL.md").write_text(
        "---\nname: github-flow\ndescription: Review and merge changes.\n"
        "requires: [general/git-commit-rules, devops/sample-deploy]\n---\n\nReview the change.\n",
        encoding="utf-8",
    )

    up_skill = donor / "packages" / "skiller" / "skills" / "ai" / "upstream-guide"
    (up_skill / "references").mkdir(parents=True)
    (up_skill / "SKILL.md").write_text(
        '---\nname: upstream-guide\ndescription: "Mirrored guide."\n---\n\nSee references/guide.md.\n',
        encoding="utf-8",
    )
    (up_skill / "references" / "guide.md").write_text("# Upstream Reference\n\nContent.\n", encoding="utf-8")
    (up_skill / "upstream.json").write_text(
        json.dumps(
            {
                "source": "github",
                "repo": "example/skills",
                "strategy": "notify",
                "license": "MIT",
                "files": [
                    {
                        "path": "references/guide.md",
                        "url": "https://raw.githubusercontent.com/example/skills/main/guide.md",
                        "sha256": "",
                        "fetched_at": "2026-07-01",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    for rel in (
        "packages/skiller/skills/axioma/axioma-custom",
        "packages/skiller/skills/quality/code-review",
        "packages/skiller/skills/general/git-commit-rules",
        "packages/skiller/skills/frontend-vue/vue-composition-api",
        "packages/maind/skills/local-topology",
    ):
        d = donor / rel
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {d.name}\ndescription: Excluded.\n---\nBody.\n", encoding="utf-8"
        )


def _open_pg_app(dsn: str, tmp_path: Path) -> App:
    clock = FrozenClock(NOW)
    state_root = tmp_path / "pg_state"
    state_root.mkdir(parents=True, exist_ok=True)
    env = {"SKM_DATABASE_URL": dsn}
    bs = replace(
        load_bootstrap(None, env, state_root),
        instance_id=SEED.instance_id,
        database_application_name="skm-migrated-packs-test",
        database_pool_min_size=0,
        database_pool_max_size=3,
        database_pool_timeout_seconds=5,
    )
    gateways = GatewayTable(
        {TokenEstimator: _HeuristicEstimator(), BuiltinPacks: PackagedBuiltinPacks(PACKS_ROOT)},
        "control_plane_gateway",
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        gateways=gateways,
        instance_id=SEED.instance_id,
    )
    return build_app(bs, surface=Surface.CLI, environ=env, invocation={}, backend="postgres", overrides=ov)


def test_cli_missing_source_fails_cleanly_without_partial_writes(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    out_dir = tmp_path / "out-packs"
    export_path = tmp_path / "overlays" / "exports.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(MIGRATE_SCRIPT),
            "--source",
            str(missing),
            "--output",
            str(out_dir),
            "--overlay-export",
            str(export_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "donor skill root not found" in proc.stderr
    assert not out_dir.exists()
    assert not export_path.exists()


def test_cli_dry_run_and_idempotent_write_on_synthetic_donor(tmp_path: Path) -> None:
    donor = tmp_path / "donor"
    _write_synthetic_donor(donor)
    out_dir = tmp_path / "packs"
    export_path = tmp_path / "overlays" / "exports.json"
    base_cmd = [
        sys.executable,
        str(MIGRATE_SCRIPT),
        "--source",
        str(donor),
        "--output",
        str(out_dir),
        "--overlay-export",
        str(export_path),
    ]

    dry = subprocess.run([*base_cmd, "--dry-run"], capture_output=True, text=True, check=True)
    dry_summary = json.loads(dry.stdout)
    assert dry_summary["dry_run"] is True
    assert dry_summary["counts"] == {"source_total": 8, "migrated": 3, "excluded": 5, "packs": 3}
    assert not out_dir.exists()
    assert not export_path.exists()

    first = subprocess.run(base_cmd, capture_output=True, text=True, check=True)
    first_export = export_path.read_bytes()
    second = subprocess.run(base_cmd, capture_output=True, text=True, check=True)
    assert first.stdout == second.stdout
    assert first_export == export_path.read_bytes()

    export_doc = json.loads(first_export.decode("utf-8"))
    assert [p["digest"] for p in export_doc["packs"]] == [p["digest"] for p in dry_summary["packs"]]

    local_skill_dir = out_dir / "migrated-local" / "migrated-devops" / "skills" / "sample-deploy"
    assert (local_skill_dir / "manifest.toml").is_file()
    assert (local_skill_dir / "snippets" / "sentinel.py").is_file()
    assert not (local_skill_dir / "evals").exists()
    assert not (local_skill_dir / "scripts").exists()

    general_pack = out_dir / "migrated-local" / "migrated-general"
    assert tomllib.loads((general_pack / "pack.toml").read_text(encoding="utf-8"))["version"] == "1.1.0"
    assert not (general_pack / "skills" / "git-commit-rules").exists()
    assert not (out_dir / "migrated-local" / "migrated-frontend").exists()
    flow = tomllib.loads((general_pack / "skills/github-flow/manifest.toml").read_text(encoding="utf-8"))
    assert flow["requires"] == ["sample-deploy"]
    exclusions = {entry["key"]: entry for entry in export_doc["excluded_skills"]}
    assert exclusions["code-review"]["g36"]["extension_point"] == "resources/packs/core/skills/spec-review"

    up_manifest = (
        out_dir / "migrated-upstream" / "migrated-upstream-ai" / "skills" / "upstream-guide" / "manifest.toml"
    ).read_text(encoding="utf-8")
    assert 'source = "upstream"' in up_manifest
    assert 'sha256 = ""' not in up_manifest


def test_builtin_packs_discovery_reads_all_packaged_groups() -> None:
    payloads = PackagedBuiltinPacks(PACKS_ROOT).payloads()
    assert len(payloads) == 29
    manifests = [tomllib.loads(payload.manifest_text) for payload in payloads]
    assert manifests[0]["slug"] == "core"
    assert {manifest["slug"] for manifest in manifests} == {
        tomllib.loads(path.read_text(encoding="utf-8"))["slug"] for path in PACKS_ROOT.rglob("pack.toml")
    }
    assert all(manifest["trust"] == "third_party" for manifest in manifests[1:])


def test_committed_migrated_packs_reconcile_and_pass_compat_clean() -> None:
    assert EXPORTS_PATH.is_file()
    export_doc = json.loads(EXPORTS_PATH.read_text(encoding="utf-8"))
    assert export_doc["source_root"] == "../swissknifeman"

    counts = export_doc["counts"]
    assert counts["source_total"] == 218
    assert counts["migrated"] + counts["excluded"] == counts["source_total"]
    assert counts["migrated"] == 134
    assert counts["excluded"] == 84
    assert counts["packs"] == 18

    excluded = export_doc["excluded_skills"]
    assert len(excluded) == counts["excluded"]
    excluded_keys = {entry["key"] for entry in excluded}
    assert excluded_keys >= REQUIRED_EXCLUSIONS
    for entry in excluded:
        assert entry["reason"]
        g36 = entry["g36"]
        assert set(g36) >= {
            "users_beyond_author",
            "users",
            "extension_point",
            "compatible_without_it",
            "removal_test",
        }

    discovered_dirs = sorted(
        p.parent for tier in PACKS_ROOT.glob("migrated-*") if tier.is_dir() for p in tier.glob("*/pack.toml")
    )
    assert len(discovered_dirs) == counts["packs"]

    reader = FilesystemPackReader()
    estimator = _HeuristicEstimator()
    packaged = {
        tomllib.loads(value.manifest_text)["slug"]: value
        for value in PackagedBuiltinPacks(PACKS_ROOT).payloads()
    }
    packs_by_path = {entry["path"]: entry for entry in export_doc["packs"]}
    assert set(packs_by_path) == {d.relative_to(ROOT).as_posix() for d in discovered_dirs}

    repo_root_str = str(ROOT)
    seen_skill_keys: set[str] = set()
    for pack_dir in discovered_dirs:
        rel_dir = pack_dir.relative_to(ROOT).as_posix()
        meta = packs_by_path[rel_dir]
        payload = reader.read_dir(str(pack_dir))
        cand = build_candidate(
            payload, estimator=estimator, scan=True, allowed_licenses=DEFAULT_ALLOWED_LICENSES
        )
        assert cand.manifest.slug == meta["slug"]
        assert cand.manifest.trust is PackTrust.THIRD_PARTY
        assert cand.manifest.priority == -100
        assert dict(cand.manifest.config) == {}
        packaged_payload = packaged[cand.manifest.slug]
        assert packaged_payload.manifest_text == payload.manifest_text
        assert {item.path: item.content for item in packaged_payload.files} == {
            item.path: item.content for item in payload.files
        }
        assert cand.digest == meta["digest"]
        assert len(cand.resources) == meta["skill_count"]
        assert [
            {"key": res.key, "version": str(res.version), "digest": res.digest} for res in cand.resources
        ] == meta["skills"]

        for pf in payload.files:
            text = pf.content.decode("utf-8")
            assert repo_root_str not in text
            if meta["tier"] == "local":
                low = text.lower()
                for forbidden in FORBIDDEN_PERSONAL_TOKENS:
                    assert forbidden not in low, f"{rel_dir}/{pf.path} leaked {forbidden!r}"

        for res in cand.resources:
            assert res.kind is ResourceKind.SKILL
            assert res.scanned is True
            assert res.compat.verdict is CompatVerdict.CLEAN
            assert res.key not in seen_skill_keys
            seen_skill_keys.add(res.key)

    assert len(seen_skill_keys) == counts["migrated"]
    assert seen_skill_keys.isdisjoint(excluded_keys)


@pytest.mark.pg
def test_committed_migrated_packs_install_into_postgres_alongside_core(
    clean_test_database: TestDatabase, tmp_path: Path
) -> None:
    export_doc = json.loads(EXPORTS_PATH.read_text(encoding="utf-8"))
    app = _open_pg_app(clean_test_database.dsn, tmp_path)
    try:
        with app.uow_factory(RequestMeta("req_seed_" + "1" * 21, Surface.CLI, None, NOW)) as uow:
            owner = new_principal(
                principal_id=SEED.principal_id,
                kind=PrincipalKind.HUMAN,
                display_name="owner",
                created_by=None,
                now=NOW,
            )
            uow.repo(PrincipalRepository).add(owner)
            uow.repo(MembershipRepository).upsert(
                Membership(SEED.instance_id, SEED.principal_id, Role.OWNER, None, NOW)
            )
            uow.commit()

        client = app.client(actor=SEED.actor(), surface=Surface.CLI)
        sync_res: Any = client.dispatch(SyncBuiltinPacks())
        assert len(sync_res.installed) == 29
        assert sync_res.installed[0].slug == "core"
        guidelines = client.ask(ListResources(kind=QueryResourceKind.MODEL_GUIDELINE, limit=100))
        assert isinstance(guidelines, ResourcesView)
        assert len(guidelines.items) == 12
        assert all(item.version == "2.0.6" for item in guidelines.items)

        reader = FilesystemPackReader()
        installed_skills = 0
        for pack_entry in export_doc["packs"]:
            pack_dir = ROOT / pack_entry["path"]
            payload = reader.read_dir(str(pack_dir))
            dto = _payload_dto(payload)
            res: Any = client.dispatch(
                InstallPack(
                    payload=dto,
                    origin_label=f"path:{pack_entry['path']}",
                    trust="third_party",
                    allow_quarantine=False,
                )
            )
            assert res.status == "already_installed"
            assert res.quarantined == ()
            assert res.digest == build_candidate(payload, estimator=_HeuristicEstimator(), scan=True).digest
            installed_skills += len(res.resources)

        assert installed_skills == export_doc["counts"]["migrated"]

        first_entry = export_doc["packs"][0]
        repeat_dto = _payload_dto(reader.read_dir(str(ROOT / first_entry["path"])))
        repeat_res: Any = client.dispatch(
            InstallPack(
                payload=repeat_dto,
                origin_label=f"path:{first_entry['path']}",
                trust="third_party",
                allow_quarantine=False,
            )
        )
        assert repeat_res.status == "already_installed"

        all_items: list[Any] = []
        cursor: str | None = None
        while True:
            page: Any = client.ask(ListResources(kind=QueryResourceKind.SKILL, after=cursor, limit=100))
            all_items.extend(page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        assert len(all_items) == export_doc["counts"]["migrated"] + 11
    finally:
        app.close()
