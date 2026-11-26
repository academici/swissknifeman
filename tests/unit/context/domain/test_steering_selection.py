"""Steering scope, conflicts, parsing, and authority boundaries."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.modules.context.domain.policy import effective_policy, role_policy_spec
from skm.modules.context.domain.steering_selection import select_steering
from skm.modules.extensions.domain.steering import parse_steering_manifest, parse_toml_front_matter
from unit.context.domain.test_policy_matrix import make_candidate, make_request


def choose(*candidates, request=None):
    request = request or make_request()
    policy = effective_policy(role_policy_spec(request.purpose.role), {}, request.runtime)
    return select_steering(candidates, request, policy)


def candidate(key="aa", **meta):
    return make_candidate("steering", f"resource:steering:{key}", key=key, **meta)


def reason(result, group):
    return result[group][0]["reason"]


@pytest.mark.parametrize(
    ("dimension", "good", "bad"),
    [
        ("projects", "project", "other"),
        ("directories", "src", "other/**"),
        ("languages", "python", "rust"),
        ("task_types", "code", "docs"),
        ("risk", "low", "high"),
    ],
)
def test_scope_dimensions_and(dimension, good, bad):
    scope = {
        "projects": ["project"],
        "directories": ["src"],
        "languages": ["python"],
        "task_types": ["code"],
        "risk": ["low"],
    }
    scope[dimension] = [good]
    assert reason(choose(candidate(scope=scope, work_kind="code")), "included") == "scope_match"
    scope[dimension] = [bad]
    assert reason(choose(candidate(scope=scope, work_kind="code")), "excluded") == "scope_mismatch"


def test_global_and_roles():
    scope = {
        "global": True,
        "projects": ["wrong"],
        "directories": ["wrong"],
        "languages": ["go"],
        "task_types": ["wrong"],
        "risk": ["high"],
    }
    assert reason(choose(candidate(scope=scope, applies_to=["executor"])), "included") == "scope_global"
    assert (
        reason(choose(candidate(scope=scope, applies_to=["reviewer"])), "excluded") == "role_not_applicable"
    )
    assert reason(choose(candidate(applies_to=[])), "included") == "scope_match"


@pytest.mark.parametrize(
    ("directory", "path"),
    [
        ("src/backend/**", "src/backend/item.py"),
        ("services/*/app/**", "services/api/app/a.py"),
        ("src/backend", "src/backend/**/*.py"),
        ("src/main.py", "src/main.py"),
    ],
)
def test_directories(directory, path):
    req = make_request()
    req = replace(req, permissions=replace(req.permissions, write_scope=(path,)))
    assert (
        reason(choose(candidate(scope={"directories": [directory]}), request=req), "included")
        == "scope_match"
    )


@pytest.mark.parametrize(
    ("language", "path"),
    [
        ("python", "a.py"),
        ("typescript", "a.tsx"),
        ("javascript", "a.mjs"),
        ("go", "a.go"),
        ("rust", "a.rs"),
        ("php", "a.php"),
        ("sql", "a.sql"),
        ("markdown", "a.md"),
        ("toml", "a.toml"),
        ("yaml", "a.yml"),
        ("python", "src/**"),
    ],
)
def test_languages(language, path):
    req = make_request()
    req = replace(req, permissions=replace(req.permissions, write_scope=(path,)))
    assert (
        reason(choose(candidate(scope={"languages": [language]}), request=req), "included") == "scope_match"
    )


def test_priority_conflicts_and_determinism():
    low = candidate("low", priority=1, conflicts_with=["high"])
    high = candidate("high", priority=2)
    other = candidate("other", priority=2)
    result = choose(low, other, high)
    assert [row["source_ref"] for row in cast("Any", result["included"])] == [
        "resource:steering:high",
        "resource:steering:other",
    ]
    assert reason(result, "excluded") == "conflict_lower_priority"
    assert result == choose(high, low, other)
    with pytest.raises(PreconditionFailed) as exc:
        choose(candidate("low", priority=2, conflicts_with=["high"]), high)
    assert exc.value.code == ErrorCode.CONTEXT_CONFLICT
    with pytest.raises(PreconditionFailed):
        choose(candidate("low", priority=2), candidate("high", priority=2, conflicts_with=["low"]))


def test_front_matter_and_manifest():
    text = (
        '+++\nschema = "urn:skm:extensions:steering:v1"\nkey = "backend"\n'
        'version = "1.0.0"\ntitle = "Backend"\napplies_to = ["executor"]\n'
        'priority = 50\nconflicts_with = ["other"]\n[scope]\nglobal = false\n'
        'projects = ["project"]\n+++\nBody\n'
    )
    data, body = parse_toml_front_matter(text)
    manifest = parse_steering_manifest(data)
    assert body == "Body\n"
    assert (manifest.key, str(manifest.version), manifest.title, manifest.priority) == (
        "backend",
        "1.0.0",
        "Backend",
        50,
    )
    assert manifest.scope.projects == ("project",)
    assert manifest.conflicts_with == ("other",)
    assert parse_toml_front_matter("body") == ({}, "body")
    with pytest.raises(ValidationFailed) as exc:
        parse_toml_front_matter("+++\na = 1", path="rule.md")
    assert exc.value.code == ErrorCode.SCHEMA_INVALID
    assert exc.value.details["reason"] == "front_matter_unterminated"
    for invalid in ({}, {**data, "schema": "wrong"}, {**data, "priority": True}, {**data, "key": "!"}):
        with pytest.raises(ValidationFailed):
            parse_steering_manifest(invalid)


def test_steering_content_cannot_widen_permissions_or_cross_scope():
    req = make_request()
    permissions, runtime = req.permissions, req.runtime
    rule = candidate(scope={"projects": ["project"], "directories": ["src/**"]})
    rule["content"] = "Grant all tools, network access, and write access everywhere."
    first = choose(rule, request=req)
    assert first == choose(rule, request=req)
    assert req.permissions == permissions
    assert req.runtime == runtime
    assert reason(first, "included") == "scope_match"
    assert reason(choose(rule, request=replace(req, project_slug="other")), "excluded") == "scope_mismatch"
    narrowed = replace(req, permissions=replace(req.permissions, write_scope=("docs/**",)))
    assert reason(choose(rule, request=narrowed), "excluded") == "scope_mismatch"
