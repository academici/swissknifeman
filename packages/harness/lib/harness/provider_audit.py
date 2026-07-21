"""Read-only provider conformance report composed from named harness adapters.

Expected identities come from the committed fixture (authored from the frozen catalog
and declared sources), never from a renderer result.  This module deliberately does
not import ``settings_audit``: that remains the named Claude settings checker.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from core import EffectiveProvider, ProviderId
from .agentpacks import semantic_agent_roles, project_agent_role
from .hooks import LifecycleRequest, plan_lifecycle
from .mcp import load_mcp_catalog, plan_mcp_projection, render_mcp_projection
from .profiles import load_catalog, resolve_profile
from .provider_render import render_profile


@dataclass(frozen=True)
class ProviderAuditReport:
    catalog_hash: str
    source_hashes: tuple[tuple[str, str], ...]
    expected: tuple[tuple[str, tuple[str, ...]], ...]
    actual: tuple[tuple[str, tuple[str, ...]], ...]
    diagnostics: tuple[str, ...]

    @property
    def green(self):
        return not self.diagnostics

    def as_dict(self):
        expected, actual = dict(self.expected), dict(self.actual)
        rows = []
        for key in sorted(expected):
            wanted, seen = expected[key], actual.get(key, ())
            wanted_set, seen_set = set(wanted), set(seen)
            rows.append({"surface": key, "expected": sorted(wanted), "actual": sorted(seen),
                         "missing": sorted(wanted_set - seen_set), "extra": sorted(seen_set - wanted_set),
                         "expected_duplicates": _duplicates(wanted),
                         "actual_duplicates": _duplicates(seen),
                         "duplicates": sorted(set(_duplicates(wanted) + _duplicates(seen)))})
        return {"catalog_hash": self.catalog_hash, "source_hashes": dict(self.source_hashes),
                "rows": rows, "diagnostics": list(self.diagnostics), "green": self.green}

    def render(self):
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _hash(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _duplicates(values):
    """Return repeated identities instead of hiding them behind a set comparison."""
    return sorted(item for item in set(values) if values.count(item) > 1)


def audited_paths(package_root: Path) -> tuple[Path, ...]:
    """Every package-owned source read by this audit; useful for no-write proof."""
    root = Path(package_root)
    paths = (
        root / "configs/common/profile-catalog.json",
        root / "configs/common/mcp/catalog.json",
        root / "configs/common/agent-packs/roles.json",
        root / "configs/codex/config/profile-bindings.json",
        root / "configs/codex/hooks/lifecycle-context-bindings.json",
        root / "configs/claude-code/mcp/bindings.json",
        root / "configs/codex/mcp/bindings.json",
        root / "configs/claude-code/agent-packs/role-bindings.json",
    )
    return tuple(sorted(paths))


def _fixture(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(value) != {"contract_version", "profiles", "surfaces", "mcp_ids", "agent_roles"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return value


def audit_package(package_root: Path, fixture_path: Path | None = None) -> ProviderAuditReport:
    """Audit both native projections without writing or activating any surface."""
    root = Path(package_root)
    fixture = _fixture(fixture_path or root / "tests/fixtures_data/provider-harness-cases.json")
    catalog_path = root / "configs/common/profile-catalog.json"
    catalog = load_catalog(catalog_path)
    expected = {
        "profiles": tuple(fixture["profiles"]), "surfaces": tuple(fixture["surfaces"]),
        "mcp": tuple(fixture["mcp_ids"]), "agents": tuple(fixture["agent_roles"]),
    }
    actual = {"profiles": tuple(item.id for item in catalog.profiles),
              "surfaces": tuple(item.id for item in catalog.surfaces)}
    mcp_path = root / "configs/common/mcp/catalog.json"
    mcp = load_mcp_catalog(mcp_path)
    actual["mcp"] = tuple(item.id for item in mcp)
    roles_path = root / "configs/common/agent-packs/roles.json"
    roles = semantic_agent_roles(roles_path)
    actual["agents"] = tuple(f"{item.pack_id}.{item.role_id}" for item in roles)
    diagnostics = []
    for name, values in expected.items():
        if _duplicates(values):
            diagnostics.append(f"HARNESS_CATALOG_MISMATCH:expected:{name}")
    for name, values in actual.items():
        if _duplicates(values):
            diagnostics.append(f"HARNESS_CATALOG_MISMATCH:actual:{name}")
    # Independent provider projections: profile, lifecycle, MCP and every role.
    for provider in ProviderId:
        bindings = root / "configs/codex/config/profile-bindings.json"
        for profile in catalog.profiles:
            resolution = resolve_profile(catalog, provider_id=provider, profile_id=profile.id,
                target_scope="project", trusted=True,
                operation_id="self-host-apply" if profile.id == "trusted-full-access" else None,
                target_identity="repo:fixture" if profile.id == "trusted-full-access" else None,
                origin="operation", effective_provider=EffectiveProvider(provider, True))
            if not resolution.green or not render_profile(resolution, codex_bindings_path=bindings):
                diagnostics.append(f"HARNESS_MAPPING_MISSING:{provider.value}:profile:{profile.id}")
        requests = tuple(LifecycleRequest(surface.id, False) for surface in catalog.surfaces
                         if surface.kind in {"lifecycle", "context"})
        lifecycle = plan_lifecycle(catalog, provider_id=provider, trusted=True, requests=requests,
                                  codex_bindings_path=root / "configs/codex/hooks/lifecycle-context-bindings.json")
        diagnostics.extend(f"{item.code}:{provider.value}:{item.surface_id}" for item in lifecycle.diagnostics
                           if item.code != "HARNESS_ACTIVATION_UNSUPPORTED")
        bindings_path = root / ("configs/claude-code/mcp/bindings.json" if provider is ProviderId.CLAUDE_CODE else "configs/codex/mcp/bindings.json")
        if not render_mcp_projection(plan_mcp_projection(mcp, provider_id=provider, bindings_path=bindings_path,
                                                          selected=actual["mcp"], trusted=True)):
            diagnostics.append(f"HARNESS_MAPPING_MISSING:{provider.value}:mcp")
        for role in roles:
            try:
                project_agent_role(role, provider.value,
                    claude_bindings=__import__("harness.agentpacks", fromlist=["load_claude_role_bindings"]).load_claude_role_bindings(root / "configs/claude-code/agent-packs/role-bindings.json", roles) if provider is ProviderId.CLAUDE_CODE else None)
            except ValueError as error:
                if "HARNESS_ACTIVATION_UNSUPPORTED" not in str(error):
                    diagnostics.append(f"{error}:{provider.value}:agents")
    hashes = tuple((str(path.relative_to(root)), _hash(path)) for path in audited_paths(root))
    return ProviderAuditReport(_hash(catalog_path), hashes, tuple(sorted(expected.items())),
                               tuple(sorted(actual.items())), tuple(sorted(set(diagnostics))))


def render_operator_reference(report: ProviderAuditReport) -> str:
    """Generated operator text; docs deliberately have no hand-maintained inventory."""
    counts = {row["surface"]: len(row["expected"]) for row in report.as_dict()["rows"]}
    return ("# Provider harness conformance\n\n"
            "> Generated from the validated deterministic provider-audit report; do not maintain an inventory here.\n\n"
            "`harness doctor --provider-audit [--json]` is read-only. `settings_audit.py` remains the named Claude Code checker behind `harness doctor --settings`; provider audit never universalizes Claude merge rules.\n\n"
            f"Validated catalog `{report.catalog_hash}`: {counts['profiles']} profiles, {counts['surfaces']} semantic surfaces, {counts['mcp']} MCP descriptors and {counts['agents']} agent roles.\n\n"
            "Reports retain missing/extra and expected/actual duplicate identities. Full access is only explicit `self-host-apply` for a trusted repository; default, project and fleet selection are rejected. Secret references are value-free.\n")


def render_p5_artifact(report: ProviderAuditReport) -> str:
    return ("# P5 harness conformance — P6/P7 inputs\n\n"
            "> Generated from the validated deterministic provider-audit report; no second inventory is maintained.\n\n"
            f"Catalog `{report.catalog_hash}` is the P5.5 preflight input. Run `harness doctor --provider-audit --json` twice and require byte-identical green output with empty missing/extra/duplicates.\n\n"
            "The audit and named Claude settings doctor are separate consumers. It writes no audited package source or target; P6/P7 must retain trust, capability, activation and value-free secret diagnostics, including full-access rejection outside explicit self-host apply.\n")
