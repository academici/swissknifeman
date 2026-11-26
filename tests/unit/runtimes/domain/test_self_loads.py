"""``explain_self_loads``: what the CLI loads by itself under a config mode (runtimes §4.3.1 rules 2/5/7)."""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Literal

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.runtimes.domain.admission import ADMISSION_DEFAULTS, AdmissionFacts, Operation, admit
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
    SelfLoad,
    SelfLoadKind,
    SelfLoadView,
    explain_self_loads,
)
from skm.modules.runtimes.domain.catalog import ModelCatalog, ModelEntry, ModelStatus, RuntimeCatalogEntry
from skm.modules.runtimes.domain.classes import Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.routing import RouteConfig, RouteDecision, RouteRequest, route

Suppressor = Literal["config_isolation", "never"]


def load(kind: SelfLoadKind, locator: str, suppressed_by: Suppressor = "config_isolation") -> SelfLoad:
    return SelfLoad(kind=kind, locator=locator, files=(), when="start", suppressed_by=suppressed_by, note="")


# The claude_code declaration behind examples/runtimes/routing-explain.json.
CLAUDE_LOADS = (
    load(SelfLoadKind.USER_CONFIG, "~/.claude (settings, CLAUDE.md, memory)"),
    load(SelfLoadKind.PLUGINS, "~/.claude plugins, hooks, MCP servers"),
    load(SelfLoadKind.SKILLS, "~/.claude/skills, <workdir>/.claude/skills, <workdir>/.claude/agents"),
    load(SelfLoadKind.PROJECT_INSTRUCTIONS, "<workdir>/CLAUDE.md and parents up to the worktree root"),
    load(SelfLoadKind.PROJECT_SETTINGS, "<workdir>/.claude/settings.json", "never"),
)
# Codex: AGENTS.md is read from cwd upwards even with an isolated CODEX_HOME.
CODEX_LOADS = (
    load(SelfLoadKind.USER_CONFIG, "~/.codex/config.toml, ~/.codex/AGENTS.md"),
    load(
        SelfLoadKind.PROJECT_INSTRUCTIONS, "<workdir>/AGENTS.md and parents up to the worktree root", "never"
    ),
    load(SelfLoadKind.PROJECT_SETTINGS, "<workdir>/.codex/config.toml"),
)


def caps(
    loads: tuple[SelfLoad, ...], isolation: CapabilityStatus | None = CapabilityStatus.NATIVE
) -> RuntimeCapabilities:
    records = {}
    if isolation is not None:
        records[Capability.CONFIG_ISOLATION] = CapabilityRecord(
            capability=Capability.CONFIG_ISOLATION,
            status=isolation,
            evidence="fixture:claude_code/isolation.jsonl",
            tested_runtime_version="2.1.0",
            limitations="",
            last_verified_at=date(2026, 10, 1),
        )
    return RuntimeCapabilities(
        runtime_id="claude_code",
        adapter_version="1.0.0",
        records=records,
        self_loads=loads,
        read_only_network=True,
        config_isolation=None,
    )


def summary(views: tuple[SelfLoadView, ...]) -> list[tuple[str, bool, str]]:
    return [(view.kind.value, view.active, view.reason) for view in views]


def test_routing_explain_example() -> None:
    views = explain_self_loads(caps(CLAUDE_LOADS), "isolated")
    assert [(v.kind.value, v.locator, v.when, v.active, v.reason) for v in views] == [
        ("user_config", "~/.claude (settings, CLAUDE.md, memory)", "start", False, "isolated"),
        ("plugins", "~/.claude plugins, hooks, MCP servers", "start", False, "isolated"),
        (
            "skills",
            "~/.claude/skills, <workdir>/.claude/skills, <workdir>/.claude/agents",
            "start",
            False,
            "isolated",
        ),
        (
            "project_instructions",
            "<workdir>/CLAUDE.md and parents up to the worktree root",
            "start",
            False,
            "isolated",
        ),
        ("project_settings", "<workdir>/.claude/settings.json", "start", True, "cannot_suppress"),
    ]


def test_isolated_suppresses_user_loads_and_keeps_unsuppressible_project_loads() -> None:
    assert summary(explain_self_loads(caps(CODEX_LOADS), "isolated")) == [
        ("user_config", False, "isolated"),
        ("project_instructions", True, "cannot_suppress"),
        ("project_settings", False, "untrusted_suppressed"),
    ]


def test_inherit_keeps_user_loads_active_but_never_worktree_settings() -> None:
    """§15 summarizes inherit as "everything active"; rules 5/7 keep project settings suppressed."""
    assert summary(explain_self_loads(caps(CODEX_LOADS), "inherit")) == [
        ("user_config", True, "inherited"),
        ("project_instructions", True, "cannot_suppress"),
        ("project_settings", False, "untrusted_suppressed"),
    ]
    claude = explain_self_loads(caps(CLAUDE_LOADS), "inherit")
    assert all(view.active for view in claude)
    assert {view.reason for view in claude} == {"inherited", "cannot_suppress"}


@pytest.mark.parametrize("status", [CapabilityStatus.UNKNOWN, CapabilityStatus.UNSUPPORTED, None])
@pytest.mark.parametrize("mode", ["isolated", "inherit"])
def test_without_proven_isolation_nothing_counts_as_suppressed(
    status: CapabilityStatus | None, mode: Literal["isolated", "inherit"]
) -> None:
    """An unverified (unknown) or unsupported config_isolation suppresses nothing: the worst case is shown."""
    views = explain_self_loads(caps(CODEX_LOADS, status), mode)
    assert all(view.active for view in views)
    by_kind = {view.kind: view.reason for view in views}
    assert by_kind[SelfLoadKind.PROJECT_SETTINGS] == "not_isolated"
    assert by_kind[SelfLoadKind.PROJECT_INSTRUCTIONS] == "cannot_suppress"
    assert by_kind[SelfLoadKind.USER_CONFIG] == ("not_isolated" if mode == "isolated" else "inherited")


def test_adapted_isolation_suppresses_like_native() -> None:
    views = explain_self_loads(caps(CODEX_LOADS, CapabilityStatus.ADAPTED), "isolated")
    assert summary(views)[0] == ("user_config", False, "isolated")


def test_views_keep_declaration_order_and_fields() -> None:
    on_access = SelfLoad(
        kind=SelfLoadKind.SKILLS,
        locator="~/.grok/skills",
        files=("SKILL.md",),
        when="on_access",
        suppressed_by="config_isolation",
        note="read lazily",
    )
    assert explain_self_loads(caps((on_access,)), "isolated") == (
        SelfLoadView(
            kind=SelfLoadKind.SKILLS,
            locator="~/.grok/skills",
            when="on_access",
            active=False,
            reason="isolated",
        ),
    )
    assert explain_self_loads(caps(()), "isolated") == ()


def test_unknown_config_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="config mode"):
        explain_self_loads(caps(CODEX_LOADS), "shared")  # pyright: ignore[reportArgumentType]


def route_scout(
    codex: RuntimeCapabilities,
    mode: Literal["isolated", "inherit"],
    *,
    required: bool = True,
    allow: frozenset[Capability] = frozenset(),
) -> RouteDecision:
    """The real ``route`` of a scout onto ``codex``, its only allowed runtime."""
    catalog = ModelCatalog(
        catalog_version="1.0.0",
        resource_version_ids=(),
        digest="sha256:" + "c" * 64,
        runtimes={
            "codex": RuntimeCatalogEntry(
                runtime_id="codex",
                class_selectors={ModelClass.ECONOMY: ("gpt-6-mini",)},
                effort_selectors={},
                models=(
                    ModelEntry(
                        id="gpt-6-mini",
                        runtime_id="codex",
                        display_name="mini",
                        classes=frozenset({ModelClass.ECONOMY}),
                        suited_roles=frozenset(),
                        context_window_tokens=100_000,
                        max_output_tokens=None,
                        pricing=None,
                        patterns=(),
                        status=ModelStatus.CONFIRMED,
                        verified_at=date(2026, 10, 1),
                        source="test",
                        notes="",
                    ),
                ),
            )
        },
    )
    admission = admit(
        AdmissionFacts(
            Operation.RESEARCH, RoleId.SCOUT, None, None, None, None, "sha256:" + "a" * 64, None, None, None
        ),
        ADMISSION_DEFAULTS,
    )
    req = RouteRequest(
        role=RoleId.SCOUT,
        required_capabilities=frozenset(),
        optional_capabilities=frozenset(),
        model_class=ModelClass.ECONOMY,
        effort=Effort.LOW,
        explicit_runtime=None,
        explicit_model=None,
        host_id=None,
        admission=admission,
        config_mode=mode,
        excluded_routes=frozenset(),
        network_read_only=False,
    )
    cfg = RouteConfig(
        allowed=frozenset({"codex"}),
        preference=("codex",),
        role_routing={},
        degraded_allow=allow,
        config_isolation_required=required,
    )
    return route(req, cfg, catalog, {"codex": codex}, {}, frozenset({"codex"}))


def codex_caps(isolation: CapabilityStatus | None = CapabilityStatus.NATIVE) -> RuntimeCapabilities:
    return dataclasses.replace(caps(CODEX_LOADS, isolation), runtime_id="codex")


@pytest.mark.parametrize("mode", ["isolated", "inherit"])
def test_route_explains_the_self_loads_of_the_chosen_runtime(mode: Literal["isolated", "inherit"]) -> None:
    """``RouteDecision.self_loads`` is ``explain_self_loads(caps[runtime], config_mode)`` of the decision."""
    codex = codex_caps()
    decision = route_scout(codex, mode)
    assert (decision.runtime_id, decision.config_mode) == ("codex", mode)
    assert decision.self_loads == explain_self_loads(codex, mode)
    assert summary(decision.self_loads) == [
        ("user_config", mode == "inherit", "inherited" if mode == "inherit" else "isolated"),
        ("project_instructions", True, "cannot_suppress"),
        ("project_settings", False, "untrusted_suppressed"),
    ]


@pytest.mark.parametrize("status", [CapabilityStatus.UNKNOWN, CapabilityStatus.UNSUPPORTED, None])
@pytest.mark.parametrize("mode", ["isolated", "inherit"])
def test_route_never_decides_with_active_worktree_project_settings(
    status: CapabilityStatus | None, mode: Literal["isolated", "inherit"]
) -> None:
    """Rule 7: the view of an unproven isolation shows the worktree settings active (``not_isolated``), so
    ``route`` refuses that runtime instead of deciding with them, whatever degraded.allow/required say."""
    codex = codex_caps(status)
    project = [view for view in explain_self_loads(codex, mode) if view.kind is SelfLoadKind.PROJECT_SETTINGS]
    assert summary(tuple(project)) == [("project_settings", True, "not_isolated")]
    for required, allow in ((True, frozenset({Capability.CONFIG_ISOLATION})), (False, frozenset())):
        with pytest.raises(CapabilityUnavailable) as caught:
            route_scout(codex, mode, required=required, allow=allow)
        assert caught.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
        assert caught.value.details["rejected"] == [
            {
                "runtime_id": "codex",
                "model": "gpt-6-mini",
                "source": "preference",
                "reason": "capability_missing:config_isolation",
                "detail": "project_settings_not_suppressible",
            }
        ]
