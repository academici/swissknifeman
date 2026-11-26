"""Core model guideline profiles validate against model-guideline.v1 and sync as a pack kind."""

from __future__ import annotations

import tomllib
from pathlib import Path

from contracts.extensions.harness import build_world
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.modules.extensions import public
from skm.modules.extensions.domain.kinds import KIND_SPECS, ResourceKind, locate
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
PACKS_ROOT = ROOT / "resources" / "packs"
GUIDELINES = PACKS_ROOT / "core" / "model-guidelines"
URN = "urn:skm:runtimes:model-guideline:v1"

EXPECTED = frozenset(
    {
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "gpt-6-astra",
        "gpt-6-sol",
        "gpt-6-luna",
        "gemini-4-neon",
        "gemini-4-carbon",
        "gemini-4-argon",
        "gemini-4-hydrogen",
        "gemini-3-8-flash",
        "grok-4-7",
        "gpt-oss-120b",
    }
)


def test_twelve_guideline_profiles_match_the_schema() -> None:
    registry = SchemaRegistry.load_default()
    spec = KIND_SPECS[ResourceKind.MODEL_GUIDELINE]
    assert spec.manifest_urn == URN
    assert spec.layout == "model-guidelines/<key>.toml"
    files = sorted(GUIDELINES.glob("*.toml"))
    assert {path.stem for path in files} == EXPECTED
    for path in files:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        assert registry.validate(URN, document) == (), path.name
        assert document["key"] == path.stem
        assert document["version"] == "2.0.6"
        located = locate(f"model-guidelines/{path.name}")
        assert located is not None
        assert located.kind is ResourceKind.MODEL_GUIDELINE
        assert located.key == path.stem


def test_core_pack_syncs_guideline_profiles() -> None:
    manifest_text = (PACKS_ROOT / "core" / "pack.toml").read_text(encoding="utf-8")
    (core_payload,) = (
        item for item in PackagedBuiltinPacks(PACKS_ROOT).payloads() if item.manifest_text == manifest_text
    )
    world = build_world(core_payload)
    result = world.run(SyncBuiltinPacks())
    manifest = tomllib.loads(manifest_text)
    assert [(pack.slug, pack.version) for pack in result.installed] == [("core", manifest["version"])]
    assert not world.tables().quarantine
    with world.uow() as uow:
        keys = public.known_keys(uow, ResourceKind.MODEL_GUIDELINE, config=world.config(uow))
        assert keys == EXPECTED
