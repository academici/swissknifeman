"""Skill ladder, filter order, requires closure and pinned version evidence."""

from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.ids import ResourceVersionId
from skm.modules.context.domain.blocks import TrustLevel
from skm.modules.context.domain.request import ROLE_NAMES
from skm.modules.context.domain.skill_selection import (
    SkillEntry,
    SkillRequest,
    select_skills,
    skill_filter_reason,
)
from skm.modules.extensions.domain.skill import parse_skill_manifest
from skm.modules.extensions.public import VersionConstraint
from skm.platform.schema.registry import SchemaRegistry

PACKS_DIR = Path(__file__).resolve().parents[4] / "resources" / "packs"


def entry(key="aa", tokens=10, **manifest):
    raw = {
        "key": key,
        "version": "1.2.0",
        "roles": ["executor"],
        "triggers": {"paths": ["src/**/*.py"]},
        **manifest,
    }
    return SkillEntry(
        key, ResourceVersionId(UUID(int=1)), parse_skill_manifest(raw), tokens, TrustLevel.OPERATOR
    )


def request(**changes):
    return replace(
        SkillRequest(
            "executor",
            "codex",
            frozenset(),
            frozenset({"Read"}),
            ("src/foo.py",),
            (),
            (),
            frozenset(),
            "auto",
            50,
        ),
        **changes,
    )


def choose(skills, req, groups=None):
    return cast("dict[str, Any]", select_skills(skills, req, groups or {}))


def test_none_and_allowlist():
    skills = [entry(), entry("bb", roles=["reviewer"])]
    result = choose(skills, request(mode="none"))
    assert result["included"] == result["discoverable"] == []
    assert result["excluded"] == {"aa": "skills_disabled", "bb": "skills_disabled"}
    assert result["trace"]["final_correction"] is False
    result = choose(
        skills, request(mode="allowlist", explicit_plan=(("bb", None),), explicit_profile=("aa",))
    )
    assert result["included"] == ["aa"]
    assert result["excluded"] == {"bb": "role_not_allowed"}
    for explicit in (request(explicit_plan=(("bb", None),)), request(explicit_profile=("bb",))):
        result = choose(skills, explicit)
        assert result["included"] == ["aa"]
        assert result["excluded"] == {"bb": "role_not_allowed"}


def test_path_and_dependency_triggers():
    result = choose([entry(), entry("bb", triggers={"deps": ["pip:pytest"]})], request())
    assert result["included"] == ["aa"]
    assert result["conditional"] == [{"key": "bb", "deps": ["pip:pytest"], "reason": "trigger_dep"}]
    assert result["trace"]["reasons"] == {"aa": "trigger_path", "bb": "trigger_dep"}
    assert result["trace"]["versions"] == {"aa": str(UUID(int=1)), "bb": str(UUID(int=1))}


def test_transitive_cyclic_requires_and_unknown_diagnostics():
    result = choose(
        [
            entry(requires=["bb", "missing"]),
            entry("bb", requires=["cc"], triggers={}),
            entry("cc", requires=["aa"], triggers={}),
        ],
        request(),
    )
    assert result["included"] == ["aa", "bb", "cc"]
    assert result["trace"]["reasons"]["cc"] == "required"
    assert result["trace"]["diagnostics"] == [{"code": "SKILL_REQUIRED_UNKNOWN"}]


def test_conditional_requires_merge_and_promotion():
    skills = [
        entry(triggers={"deps": ["pip:a"]}, requires=["cc"]),
        entry("bb", triggers={"deps": ["pip:b"]}, requires=["cc"]),
        entry("cc", triggers={}),
    ]
    result = choose(skills, request())
    assert next(c for c in result["conditional"] if c["key"] == "cc")["deps"] == ["pip:a", "pip:b"]
    skills.append(entry("dd", requires=["cc"]))
    result = choose(skills, request())
    assert "cc" in result["included"]
    assert not any(c["key"] == "cc" for c in result["conditional"])


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"quarantined": True, "roles": ["other"]}, "quarantined"),
        ({"roles": ["other"], "requires_tools": ["Missing"]}, "role_not_allowed"),
        ({"roles": []}, "role_not_allowed"),
        ({"requires_tools": ["Missing"], "kind": "router"}, "tool_missing"),
        ({"kind": "router", "replaced_by": "executor"}, "kind_not_preloaded"),
        ({"replaced_by": "executor", "adapters": ["other"]}, "duplicated_by_role_contract"),
        ({"adapters": ["other"]}, "adapter_not_supported"),
    ],
)
def test_filter_cascade(meta, expected):
    assert (
        skill_filter_reason({"key": "aa", "roles": ["executor"], **meta}, request(), explicit=False)
        == expected
    )


def test_explicit_exemptions_excludes_and_adapters():
    skill = entry(requires_tools=["Missing"], kind="router", replaced_by="executor")
    assert choose([skill], request(explicit_profile=("aa",)))["included"] == ["aa"]
    assert choose([skill], request(explicit_profile=("aa",), exclude=frozenset({"aa"})))["excluded"] == {
        "aa": "excluded"
    }
    assert choose([entry(adapters=["other"])], request(explicit_profile=("aa",)))["excluded"] == {
        "aa": "adapter_not_supported"
    }


def test_quarantine_has_no_outward_identity_or_count():
    hidden = replace(entry("secret-id"), quarantined=True)
    for mode in ("none", "allowlist", "auto"):
        assert "secret-id" not in str(choose([hidden], request(mode=mode, explicit_profile=("secret-id",))))


def test_exclusive_budget_count_and_discoverable():
    skills = [entry("aa", exclusive_group="style"), entry("bb", exclusive_group="style")]
    result = choose(skills, request(explicit_profile=("bb",)), {"style": {"max": 1}})
    assert result["included"] == ["bb"]
    assert result["excluded"] == {"aa": "exclusive_group"}
    assert choose([entry(tokens=40), entry("bb", tokens=20)], request())["excluded"] == {
        "bb": "over_skill_budget"
    }
    assert choose([entry(), entry("bb")], request(max_count=1))["excluded"] == {"bb": "over_skill_count"}
    result = choose([entry(kind="reference"), entry("bb", kind="persona")], request())
    assert result["discoverable"] == ["aa", "bb"]
    assert result["tokens"] == 0


def test_versions_unknown_and_explicit_budget_exemption():
    result = choose(
        [entry(tokens=100)],
        request(explicit_plan=(("aa", VersionConstraint.parse(">=2")), ("missing", None))),
    )
    assert result["excluded"] == {"aa": "version_unavailable", "missing": "unknown_skill"}
    result = choose([entry(tokens=100)], request(explicit_plan=(("aa", None),), budget=0))
    assert result["included"] == ["aa"]
    assert result["trace"]["skills_remaining"] == 0


def test_discoverable_index_integrates_only_filtered_authorized_skills():
    from dataclasses import replace

    from skm.modules.context.domain.candidates import discover, objects
    from skm.modules.context.domain.policy import effective_policy, role_policy_spec
    from skm.modules.context.domain.selection import select
    from skm.modules.context.domain.validation import validate

    from .test_policy_matrix import core_sources, make_candidate, make_request

    req = make_request()
    policy = effective_policy(replace(role_policy_spec("executor")), {}, req.runtime)
    public = make_candidate(
        "skills",
        "resource:skill:reference",
        key="reference",
        kind="reference",
        paths=["src/**"],
        roles=["executor"],
    )
    hidden = make_candidate(
        "skills", "SECRET-ID", key="SECRET-ID", kind="reference", paths=["src/**"], authorized=False
    )
    result = select(
        validate(discover([*core_sources(), public, hidden], req, policy), policy), req, policy, {}
    )
    index = next(row for row in objects(result["included"]) if row["block_type"] == "skill_index")
    assert index["content"] == "reference"
    assert "SECRET" not in str(result)


@pytest.fixture(scope="module")
def installed_skills() -> dict[str, SkillEntry]:
    entries: dict[str, SkillEntry] = {}
    for idx, path in enumerate(sorted(PACKS_DIR.glob("**/skills/*/manifest.toml")), start=1):
        manifest = parse_skill_manifest(tomllib.loads(path.read_text(encoding="utf-8")))
        key = str(manifest.key)
        assert key not in entries
        entries[key] = SkillEntry(key, ResourceVersionId(UUID(int=idx)), manifest, 10, TrustLevel.OPERATOR)
    return entries


@pytest.mark.parametrize("role", sorted(ROLE_NAMES))
@pytest.mark.parametrize(("mode", "unseeded"), [("auto", "trigger_not_met"), ("allowlist", "excluded")])
def test_installed_skills_require_role_before_expanding_dependencies(installed_skills, role, mode, unseeded):
    result = choose(
        list(installed_skills.values()),
        request(
            role=role,
            mode=mode,
            explicit_plan=(("requirement-critic", None), ("laravel-security-audit", None)),
            explicit_profile=("implement",),
        ),
    )
    parents = ["requirement-critic", "laravel-security-audit"]
    # implement is an executor skill named by the profile. Explicit seeds skip the
    # role-contract replacement, so only a non-executor role refuses it.
    if role == "executor":
        assert "implement" in result["included"]
    else:
        assert result["excluded"]["implement"] == "role_not_allowed"
    if role == "reviewer":
        assert result["included"] == parents
        # The requires targets are considered, then refused: they do not share reviewer.
        assert {result["excluded"][key] for key in ("brd", "static-analysis")} == {"role_not_allowed"}
    else:
        assert not any(key in result["included"] for key in (*parents, "brd", "business-process"))
        assert {result["excluded"][key] for key in parents} == {"role_not_allowed"}
        # A refused parent does not expand, so the authoring chain stays unseeded.
        assert {result["excluded"][key] for key in ("brd", "static-analysis")} == {unseeded}
    assert result["excluded"]["business-process"] == unseeded
    leaked = {"requirement-critic", "laravel-security-audit", "brd", "business-process", "static-analysis"}
    if role != "reviewer":
        leaked = leaked - set()
        assert not leaked.intersection(result["included"])
    conditional_keys = {item["key"] for item in result["conditional"]}
    assert not {"brd", "business-process", "static-analysis", "requirement-critic"}.intersection(
        conditional_keys
    )
    if mode == "allowlist":
        assert not result["conditional"]


def test_unknown_role_cannot_match_manifest_or_seed(installed_skills):
    unknown_role = "other"
    skill = replace(
        installed_skills["code-review"],
        manifest=replace(installed_skills["code-review"].manifest, roles=(unknown_role,)),
    )
    result = choose(
        [skill, installed_skills["research-method"]],
        request(
            role=unknown_role,
            mode="allowlist",
            explicit_plan=(("code-review", None),),
            skills_by_role={unknown_role: ("research-method",)},
        ),
    )
    assert result["included"] == []
    assert result["excluded"] == {"code-review": "role_not_allowed", "research-method": "excluded"}


def test_installed_role_contract_path_excludes_role_eligible_skill(installed_skills):
    skill = installed_skills["implement"]
    manifest = replace(
        skill.manifest, roles=("executor",), triggers=replace(skill.manifest.triggers, paths=("src/**",))
    )
    result = choose([replace(skill, manifest=manifest), installed_skills["tdd-discipline"]], request())
    assert result["included"] == []
    assert result["excluded"]["implement"] == "duplicated_by_role_contract"


@pytest.mark.parametrize(
    ("role", "included", "unseeded"),
    [
        ("reviewer", "code-review", "research-method"),
        ("researcher", "research-method", "code-review"),
    ],
)
def test_installed_role_skills_seed_only_matching_role(installed_skills, role, included, unseeded):
    result = choose(
        list(installed_skills.values()),
        request(
            role=role,
            mode="allowlist",
            skills_by_role={"reviewer": ("code-review",), "researcher": ("research-method",)},
            final_correction=True,
        ),
    )
    assert result["included"] == [included]
    assert result["excluded"][unseeded] == "excluded"
    assert result["trace"]["reasons"] == {included: "explicit_plan"}
    assert result["trace"]["final_correction"] is True


@pytest.mark.parametrize("key", ["code-review", "codex_lab-2:code-review", "a:code-review"])
def test_skill_manifest_schema_accepts_plain_and_prefixed_keys(key):
    urn = "urn:skm:extensions:skill-manifest:v1"
    doc = {"schema": urn, "version": "1.0.0", "key": key, "requires": [key], "conflicts_with": [key]}
    assert SchemaRegistry.load_default().validate(urn, doc) == ()


@pytest.mark.parametrize("key", ["2codex:code-review", "Codex:code-review", "codex:code_review", "codex:"])
def test_skill_manifest_schema_rejects_invalid_prefixed_keys(key):
    urn = "urn:skm:extensions:skill-manifest:v1"
    doc = {"schema": urn, "version": "1.0.0", "key": key, "requires": [key], "conflicts_with": [key]}
    assert len(SchemaRegistry.load_default().validate(urn, doc)) == 3
