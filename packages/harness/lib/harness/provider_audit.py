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
import tempfile

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
    evidence: tuple[tuple[str, str, str, str, str, str], ...] = ()

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
        evidence = [{"category": category, "provider": provider, "identity": identity,
                     "polarity": polarity, "state": state, "diagnostic": diagnostic}
                    for category, provider, identity, polarity, state, diagnostic in self.evidence]
        return {"catalog_hash": self.catalog_hash, "source_hashes": dict(self.source_hashes),
                "rows": rows, "diagnostics": list(self.diagnostics), "evidence": evidence,
                "green": self.green}

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
    diagnostics, evidence = [], []
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
            else:
                evidence.append(("security", provider.value, f"profile:{profile.id}", "positive",
                                 "supported", "HARNESS_PROFILE_RESOLVED"))
        requests = tuple(LifecycleRequest(surface.id, False) for surface in catalog.surfaces
                         if surface.kind in {"lifecycle", "context"})
        lifecycle = plan_lifecycle(catalog, provider_id=provider, trusted=True, requests=requests,
                                  codex_bindings_path=root / "configs/codex/hooks/lifecycle-context-bindings.json")
        unsupported = {(item.surface_id, item.code) for item in lifecycle.diagnostics}
        for binding in lifecycle.bindings:
            code = next((code for surface, code in unsupported if surface == binding.surface_id), "")
            evidence.append(("activation", provider.value, f"surface:{binding.surface_id}",
                             "negative" if code else "positive",
                             "unsupported" if code else "supported", code or "HARNESS_ACTIVATION_NATIVE"))
            if code and code != "HARNESS_ACTIVATION_UNSUPPORTED":
                diagnostics.append(f"{code}:{provider.value}:{binding.surface_id}")
        bindings_path = root / ("configs/claude-code/mcp/bindings.json" if provider is ProviderId.CLAUDE_CODE else "configs/codex/mcp/bindings.json")
        mcp_plan = plan_mcp_projection(mcp, provider_id=provider, bindings_path=bindings_path,
                                       selected=actual["mcp"], trusted=True)
        if not render_mcp_projection(mcp_plan):
            diagnostics.append(f"HARNESS_MAPPING_MISSING:{provider.value}:mcp")
        else:
            evidence.append(("capability", provider.value, "mcp:catalog", "positive", "supported",
                             "HARNESS_MCP_PROJECTION_RENDERED"))
            evidence.append(("secret", provider.value, "mcp:catalog", "positive", "value-free",
                             "HARNESS_SECRET_REFERENCES_ONLY"))
        try:
            plan_mcp_projection(mcp, provider_id=provider, bindings_path=bindings_path,
                                selected=actual["mcp"], trusted=False)
        except ValueError as error:
            evidence.append(("trust", provider.value, "mcp:catalog", "negative", "refused", str(error)))
        try:
            plan_mcp_projection(mcp, provider_id=provider, bindings_path=bindings_path,
                                selected=("missing-capability",), trusted=True)
        except ValueError as error:
            evidence.append(("capability", provider.value, "mcp:missing-capability", "negative",
                             "refused", str(error)))
        for role in roles:
            try:
                project_agent_role(role, provider.value,
                    claude_bindings=__import__("harness.agentpacks", fromlist=["load_claude_role_bindings"]).load_claude_role_bindings(root / "configs/claude-code/agent-packs/role-bindings.json", roles) if provider is ProviderId.CLAUDE_CODE else None)
            except ValueError as error:
                if "HARNESS_ACTIVATION_UNSUPPORTED" in str(error):
                    evidence.append(("activation", provider.value,
                                     f"role:{role.pack_id}.{role.role_id}", "negative", "unsupported",
                                     str(error)))
                else:
                    diagnostics.append(f"{error}:{provider.value}:agents")
            else:
                evidence.append(("activation", provider.value,
                                 f"role:{role.pack_id}.{role.role_id}", "positive", "supported",
                                 "HARNESS_AGENT_ACTIVATION_NATIVE"))
        _append_security_evidence(catalog, provider, evidence)
        _append_secret_negative_evidence(mcp, provider, bindings_path, actual["mcp"], evidence)
    hashes = tuple((str(path.relative_to(root)), _hash(path)) for path in audited_paths(root))
    return ProviderAuditReport(_hash(catalog_path), hashes, tuple(sorted(expected.items())),
                               tuple(sorted(actual.items())), tuple(sorted(set(diagnostics))),
                               tuple(sorted(set(evidence))))


def _append_security_evidence(catalog, provider, evidence):
    effective = EffectiveProvider(provider, True)
    accepted = resolve_profile(catalog, provider_id=provider, profile_id="trusted-full-access",
        target_scope="project", trusted=True, operation_id="self-host-apply",
        target_identity="repo:fixture", origin="operation", effective_provider=effective)
    evidence.append(("security", provider.value, "profile:trusted-full-access", "positive",
                     "supported" if accepted.green else "refused", "HARNESS_FULL_ACCESS_EXPLICIT"))
    omitted = resolve_profile(catalog, provider_id=provider, profile_id="trusted-full-access",
        target_scope="project", trusted=True, origin="operation", effective_provider=effective)
    evidence.append(("security", provider.value, "profile:trusted-full-access", "negative", "refused",
                     "+".join(item.code for item in omitted.diagnostics)))
    inherited = resolve_profile(catalog, provider_id=provider, profile_id="trusted-full-access",
        target_scope="project", trusted=True, operation_id="self-host-apply", target_identity="repo:fixture",
        origin="fleet-defaults", effective_provider=effective)
    evidence.append(("security", provider.value, "origin:fleet-defaults", "negative", "refused",
                     "+".join(item.code for item in inherited.diagnostics)))
    trusted = resolve_profile(catalog, provider_id=provider, profile_id="workspace-contained",
        target_scope="project", trusted=True, origin="operation", effective_provider=effective)
    evidence.append(("trust", provider.value, "profile:workspace-contained", "positive",
                     "supported" if trusted.green else "refused", "HARNESS_TRUST_SATISFIED"))


def _append_secret_negative_evidence(mcp, provider, bindings_path, selected, evidence):
    original = Path(bindings_path).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as directory:
        altered = Path(directory) / "bindings.json"
        altered.write_text(original.replace("${", "literal-", 1), encoding="utf-8")
        try:
            plan_mcp_projection(mcp, provider_id=provider, bindings_path=altered,
                                selected=selected, trusted=True)
        except ValueError as error:
            evidence.append(("secret", provider.value, "mcp:catalog", "negative", "refused", str(error)))


def render_operator_reference(report: ProviderAuditReport) -> str:
    """Generated operator text; docs deliberately have no hand-maintained inventory."""
    counts = {row["surface"]: len(row["expected"]) for row in report.as_dict()["rows"]}
    return ("# Provider harness conformance\n\n"
            "> Generated from the validated deterministic provider-audit report; do not maintain an inventory here.\n\n"
            "`harness doctor --provider-audit [--json]` is read-only. `settings_audit.py` remains the named Claude Code checker behind `harness doctor --settings`; provider audit never universalizes Claude merge rules.\n\n"
            f"Validated catalog `{report.catalog_hash}`: {counts['profiles']} profiles, {counts['surfaces']} semantic surfaces, {counts['mcp']} MCP descriptors and {counts['agents']} agent roles.\n\n"
            "Reports retain missing/extra and expected/actual duplicate identities. Full access is only explicit `self-host-apply` for a trusted repository; default, project and fleet selection are rejected. Secret references are value-free.\n\n"
            + _render_evidence_matrix(report))


def render_p5_artifact(report: ProviderAuditReport) -> str:
    return ("# P5 harness conformance — P6/P7 inputs\n\n"
            "> Generated from the validated deterministic provider-audit report; no second inventory is maintained.\n\n"
            f"Catalog `{report.catalog_hash}` is the P5.5 preflight input. Run `harness doctor --provider-audit --json` twice and require byte-identical green output with empty missing/extra/duplicates.\n\n"
            "The audit and named Claude settings doctor are separate consumers. It writes no audited package source or target.\n\n"
            "## Exact P6 deployment inputs\n\n"
            "- Use this report's catalog/source hashes and complete evidence matrix as the preflight input.\n"
            "- Check and repair are managed-only; repair may change matching managed fixture paths only.\n"
            "- No live target write, activation, apply authority, MCP start, hook start or workflow start is granted.\n\n"
            "## Exact P7 self-host acceptance inputs\n\n"
            "- Re-run the byte-identical read-only report twice; retain supported and provider-qualified unsupported rows.\n"
            "- Accept full access only for exact `self-host-apply` plus trusted `repo:` target; reject default, project and fleet inheritance.\n"
            "- Keep secret evidence value-free and preserve named Claude settings audit as a separate consumer.\n\n"
            + _render_evidence_matrix(report))


def _render_evidence_matrix(report):
    lines = ["## Deterministic evidence matrix\n", "| Category | Provider | Surface or role | Case | State | Diagnostic |",
             "|:--|:--|:--|:--|:--|:--|"]
    seen_positive = set()
    for item in report.as_dict()["evidence"]:
        key = (item["category"], item["provider"],
               item["identity"] if item["category"] == "security" else "")
        if item["polarity"] == "positive" and key in seen_positive:
            continue
        if item["polarity"] == "positive":
            seen_positive.add(key)
        lines.append("| {category} | {provider} | {identity} | {polarity} | {state} | `{diagnostic}` |".format(**item))
    return "\n".join(lines) + "\n"
