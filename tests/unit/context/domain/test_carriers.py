"""Carrier discovery and complete deterministic host planning, independent of the host."""

from dataclasses import replace

import pytest

from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.blocks import BlockType, BudgetClass
from skm.modules.context.domain.carriers import instruction_carrier_dirs, static_prefix
from skm.modules.context.domain.host_inputs import HostInputKind, plan_host_inputs
from skm.modules.context.domain.policy import ContextPolicy


def policy(**changes):
    value = ContextPolicy(
        frozenset((BlockType.REPO_INSTRUCTIONS, BlockType.MATERIALS, BlockType.RESEARCH)),
        50000,
        {BudgetClass.CORE: 12000},
        "full",
        ("Security",),
        65536,
        2,
        ("CLAUDE.md", "AGENTS.md"),
        "none",
        (),
        frozenset(),
        8000,
        3,
        0,
        True,
        "internal",
        True,
        40000,
    )
    return replace(value, **changes)


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("src/skm/**/*.py", "src/skm"),
        ("src/foo.py", "src"),
        ("README.md", ""),
        ("src/", "src"),
        ("src/[ab]/x", "src"),
        ("src/foo?.py", "src"),
        ("src/../private/**", "src"),
        ("**", ""),
        ("./src/**", "src"),
    ],
)
def test_static_prefix_stops_at_glob_filename_or_parent(pattern, expected):
    assert static_prefix(pattern) == expected


def test_all_ancestors_are_deduplicated_and_sorted_by_mount_depth_path():
    assert instruction_carrier_dirs((("z", "a/b/**"), ("a", "src/pkg/file.py"), ("a", "src/**"))) == (
        ("a", ""),
        ("a", "src"),
        ("a", "src/pkg"),
        ("z", ""),
        ("z", "a"),
        ("z", "a/b"),
    )


def test_planning_does_not_cap_directories_by_successful_file_limit():
    requests = plan_host_inputs((("repo", "a/b/c/**"),), (), policy(repo_max_files=1), {})
    assert [r.path for r in requests] == ["", "a/", "a/b/", "a/b/c/"]
    assert [r.request_id for r in requests] == [f"hi:{n}" for n in range(4)]
    assert all(not r.follow_symlinks and r.trust.value == "repository" for r in requests)


@pytest.mark.parametrize("mode", ["none", "constraints", "full"])
def test_repo_mode_and_self_loaded_apply_only_to_primary_root(mode):
    settings: JsonObject = {
        "runtime": {"primary_mount": "main", "self_loaded_instruction_files": ["AGENTS.md"]}
    }
    requests = plan_host_inputs((("other", "x/**"), ("main", "src/**")), (), policy(repo_mode=mode), settings)
    if mode == "none":
        assert requests == ()
    else:
        assert requests[0].skip_if_resolved_in == ("AGENTS.md",)
        assert all(not r.skip_if_resolved_in for r in requests[1:])
        assert requests[0].selector.kind == ("whole" if mode == "full" else "markdown_sections")
        assert "#" in requests[0].source_ref


def test_material_deduplication_preserves_required_and_selector_identity():
    materials = (
        {"kind": "repository_path", "path": "guide.md", "selector": {"kind": "whole"}},
        {"kind": "repository_path", "path": "guide.md", "required": True},
        {
            "kind": "repository_path",
            "path": "guide.md",
            "selector": {"kind": "line_range", "line_from": 1, "line_to": 2},
        },
    )
    requests = plan_host_inputs((), materials, policy(repo_mode="none"), {})
    assert len(requests) == 2
    assert requests[0].required
    assert requests[0].follow_symlinks
    assert requests[1].selector.line_to == 2
    assert "line-range=1-2" in requests[1].source_ref
    required = plan_host_inputs((), materials, policy(repo_mode="none", include_optional_materials=False), {})
    assert len(required) == 1
    assert required[0].required


def test_dependency_manifests_and_research_queries_have_stable_deduplicated_requests():
    requests = plan_host_inputs(
        (("repo", "src/**"), ("repo", "tests/**")),
        (),
        policy(repo_mode="none", skills_mode="auto"),
        {
            "research_queries": [
                {"text": "  why? "},
                {"text": "why?"},
                {"text": "other", "depth": "deep", "max_documents": 3},
            ],
            "host_inputs": {"file_max_bytes": 123, "max_bytes": 999},
        },
    )
    assert [r.path for r in requests[:3]] == ["pyproject.toml", "package.json", "composer.json"]
    assert all(r.block_type is None and r.max_bytes == 123 for r in requests[:3])
    assert len(requests) == 5
    assert requests[-1].kind is HostInputKind.RESEARCH_QUERY
    research = requests[-1].research
    assert research is not None
    assert research.depth == "deep"
    assert research.max_documents == 3
    assert requests[-1].trust.value == "external"
    assert requests[-1].max_bytes == 999


def test_no_disallowed_material_or_research_request_is_planned():
    assert (
        plan_host_inputs(
            (),
            ({"kind": "repository_path", "path": "private"},),
            policy(include=frozenset()),
            {"research_queries": [{"text": "why?"}]},
        )
        == ()
    )
