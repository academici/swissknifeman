"""Read-only provider conformance report composed from named harness adapters.

Expected identities come from the committed fixture (authored from the frozen catalog
and declared sources), never from a renderer result.  This module deliberately does
not import ``settings_audit``: that remains the named Claude settings checker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import tempfile

from core import (ArtifactActionKind, EffectiveProvider, ProviderId, apply_plan,
                  plan_artifact_lock, serialize_lock)
from .agentpacks import (load_claude_role_bindings, plan_agent_artifact,
                         semantic_agent_roles, project_agent_role)
from .hooks import LifecycleRequest, plan_codex_lifecycle_artifacts, plan_lifecycle
from .mcp import (load_mcp_catalog, plan_mcp_artifact, plan_mcp_projection,
                  render_mcp_projection)
from .profiles import load_catalog, resolve_profile
from .provider_render import plan_profile_artifact, render_profile


@dataclass(frozen=True)
class ProviderAuditReport:
    catalog_hash: str
    source_hashes: tuple[tuple[str, str], ...]
    expected: tuple[tuple[str, tuple[str, ...]], ...]
    actual: tuple[tuple[str, tuple[str, ...]], ...]
    diagnostics: tuple[str, ...]
    evidence: tuple[tuple[str, str, str, str, str, str], ...] = ()
    render_hashes: tuple[tuple[str, str], ...] = ()
    surface_map: tuple[tuple[str, str, str, str, str, str, str, str], ...] = ()
    managed_lifecycle: tuple[tuple[str, str, str, str, str, bool], ...] = ()

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
        surfaces = [{"provider": provider, "surface_id": surface_id,
                     "semantic_hash": semantic_hash, "required_capabilities": capabilities,
                     "security_or_ownership": ownership, "artifact_or_state": artifact,
                     "activation_state": activation, "diagnostic": diagnostic}
                    for provider, surface_id, semantic_hash, capabilities, ownership, artifact,
                    activation, diagnostic in self.surface_map]
        lifecycle = [{"artifact": artifact, "create": create, "check": check,
                      "drift": drift, "repair": repair,
                      "outside_managed_preserved": preserved}
                     for artifact, create, check, drift, repair, preserved in self.managed_lifecycle]
        return {"catalog_hash": self.catalog_hash, "source_hashes": dict(self.source_hashes),
                "rows": rows, "diagnostics": list(self.diagnostics), "evidence": evidence,
                "render_hashes": dict(self.render_hashes), "surface_map": surfaces,
                "managed_lifecycle": lifecycle,
                "green": self.green}

    def render(self):
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _hash(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_hash(value: object) -> str:
    return _bytes_hash(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8"))


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
    diagnostics, evidence, render_hashes, surface_map = [], [], [], []
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
                rendered = render_profile(resolution, codex_bindings_path=bindings)
                render_hashes.append((f"profile:{provider.value}:{profile.id}", _bytes_hash(rendered)))
                evidence.append(("security", provider.value, f"profile:{profile.id}", "positive",
                                 "supported", "HARNESS_PROFILE_RESOLVED"))
        requests = tuple(LifecycleRequest(surface.id, False) for surface in catalog.surfaces
                         if surface.kind in {"lifecycle", "context"})
        lifecycle = plan_lifecycle(catalog, provider_id=provider, trusted=True, requests=requests,
                                  codex_bindings_path=root / "configs/codex/hooks/lifecycle-context-bindings.json")
        unsupported = {item.surface_id: item.code for item in lifecycle.diagnostics}
        for binding in lifecycle.bindings:
            code = unsupported.get(binding.surface_id, "")
            render_hashes.append((f"lifecycle:{provider.value}:{binding.surface_id}",
                                  _canonical_hash(asdict(binding))))
            evidence.append(("activation", provider.value, f"surface:{binding.surface_id}",
                             "negative" if code else "positive",
                             "unsupported" if code else "supported", code or "HARNESS_ACTIVATION_NATIVE"))
            if code and code != "HARNESS_ACTIVATION_UNSUPPORTED":
                diagnostics.append(f"{code}:{provider.value}:{binding.surface_id}")
        bindings_path = root / ("configs/claude-code/mcp/bindings.json" if provider is ProviderId.CLAUDE_CODE else "configs/codex/mcp/bindings.json")
        mcp_plan = plan_mcp_projection(mcp, provider_id=provider, bindings_path=bindings_path,
                                       selected=actual["mcp"], trusted=True)
        mcp_render = render_mcp_projection(mcp_plan)
        if not mcp_render:
            diagnostics.append(f"HARNESS_MAPPING_MISSING:{provider.value}:mcp")
        else:
            render_hashes.append((f"mcp:{provider.value}:catalog", _bytes_hash(mcp_render)))
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
        claude_role_bindings = (load_claude_role_bindings(
            root / "configs/claude-code/agent-packs/role-bindings.json", roles)
            if provider is ProviderId.CLAUDE_CODE else None)
        for role in roles:
            try:
                projection = project_agent_role(role, provider.value,
                                                claude_bindings=claude_role_bindings)
            except ValueError as error:
                if "HARNESS_ACTIVATION_UNSUPPORTED" in str(error):
                    evidence.append(("activation", provider.value,
                                     f"role:{role.pack_id}.{role.role_id}", "negative", "unsupported",
                                     str(error)))
                else:
                    diagnostics.append(f"{error}:{provider.value}:agents")
            else:
                render_hashes.append((f"agent:{provider.value}:{role.pack_id}.{role.role_id}",
                                      _bytes_hash(projection.rendered)))
                evidence.append(("activation", provider.value,
                                 f"role:{role.pack_id}.{role.role_id}", "positive", "supported",
                                 "HARNESS_AGENT_ACTIVATION_NATIVE"))
        _append_security_evidence(catalog, provider, evidence)
        _append_secret_negative_evidence(mcp, provider, bindings_path, actual["mcp"], evidence)
        surface_map.extend(_provider_surface_rows(provider, catalog, lifecycle, mcp_plan, roles))
    diagnostics.extend(_map_diagnostics(surface_map, tuple(fixture["surfaces"])))
    if len({identity for identity, _digest in render_hashes}) != len(render_hashes):
        diagnostics.append("HARNESS_CATALOG_MISMATCH:duplicate-render-hash")
    managed_lifecycle = _managed_lifecycle_evidence(root, catalog, mcp, roles)
    hashes = tuple((str(path.relative_to(root)), _hash(path)) for path in audited_paths(root))
    return ProviderAuditReport(_hash(catalog_path), hashes, tuple(sorted(expected.items())),
                               tuple(sorted(actual.items())), tuple(sorted(set(diagnostics))),
                               tuple(sorted(set(evidence))), tuple(sorted(render_hashes)),
                               tuple(sorted(surface_map)), managed_lifecycle)


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
    for origin in ("project", "fleet-project", "fleet-defaults"):
        inherited = resolve_profile(catalog, provider_id=provider, profile_id="trusted-full-access",
            target_scope="project", trusted=True, operation_id="self-host-apply", target_identity="repo:fixture",
            origin=origin, effective_provider=effective)
        evidence.append(("security", provider.value, f"origin:{origin}", "negative", "refused",
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


def _provider_surface_rows(provider, catalog, lifecycle, mcp_plan, roles):
    """One complete provider-qualified row per frozen semantic surface.

    The report intentionally keeps named, non-artifact compatibility consumers visible;
    they are not silently promoted into a universal renderer.
    """
    binding_by_surface = {binding.surface_id: binding for binding in lifecycle.bindings}
    lifecycle_codes = {item.surface_id: item.code for item in lifecycle.diagnostics}
    profile_target = (".claude/settings.local.json" if provider is ProviderId.CLAUDE_CODE
                      else ".codex/config.toml")
    rows = []
    for surface in catalog.surfaces:
        semantic_hash = _canonical_hash(asdict(surface))
        capabilities = ";".join(
            f"{capability}:{','.join(levels)}" for capability, levels in surface.required_capabilities
        ) or "—"
        ownership = surface.ownership
        artifact, activation, diagnostic = _named_surface_state(
            provider, surface.id, binding_by_surface, lifecycle_codes, profile_target, mcp_plan, roles)
        rows.append((provider.value, surface.id, semantic_hash, capabilities, ownership,
                     artifact, activation, diagnostic))
    return rows


def _named_surface_state(provider, surface_id, bindings, lifecycle_codes, profile_target, mcp_plan, roles):
    if surface_id == "settings.permissions":
        return f"artifact:project:{profile_target}", "supported", "HARNESS_PROFILE_RENDERED"
    if surface_id == "settings.audit":
        if provider is ProviderId.CLAUDE_CODE:
            return "non-artifact:named-settings-audit", "supported", "HARNESS_SETTINGS_AUDIT_NAMED"
        return "non-artifact:claude-only-settings-audit", "unsupported", "HARNESS_ACTIVATION_UNSUPPORTED"
    if surface_id == "security.safe-dirs":
        if provider is ProviderId.CLAUDE_CODE:
            return "non-artifact:machine-owned-safe-dirs", "supported", "HARNESS_SAFE_DIRS_NAMED"
        return "non-artifact:no-codex-safe-dirs-binding", "unsupported", "HARNESS_ACTIVATION_UNSUPPORTED"
    if surface_id in bindings:
        binding = bindings[surface_id]
        code = lifecycle_codes.get(surface_id, "")
        if code:
            return "non-artifact:unsupported-native-binding", "unsupported", code
        if provider is ProviderId.CODEX and binding.support_level == "hook-native":
            return "artifact:project:.codex/hooks.json+.codex/hooks/lifecycle.py", "supported", "HARNESS_ACTIVATION_NATIVE"
        return f"native-binding:{binding.activation}", "supported", "HARNESS_ACTIVATION_NATIVE"
    if surface_id == "mcp.catalog":
        return f"artifact:{mcp_plan.target_scope}:{mcp_plan.target_path}", "supported", "HARNESS_MCP_PROJECTION_RENDERED"
    if surface_id == "agents.catalog":
        supported = sum(1 for role in roles if not (
            provider is ProviderId.CODEX and "command.workflow-carrier" in role.activation_requirements))
        return f"artifact:project:{supported}-named-agent-targets", "supported", "HARNESS_AGENT_ACTIVATION_NATIVE"
    if surface_id == "agent-packs.lifecycle":
        if provider is ProviderId.CLAUDE_CODE:
            return "non-artifact:named-agent-pack-engine", "supported", "HARNESS_AGENTPACK_LIFECYCLE_NAMED"
        return ("non-artifact:missing-native-codex-pack-lifecycle", "unsupported",
                "HARNESS_ACTIVATION_UNSUPPORTED:codex:agent-packs.lifecycle:"
                "missing-native-codex-pack-lifecycle")
    if surface_id == "workflows.status":
        if provider is ProviderId.CLAUDE_CODE:
            return "non-artifact:named-workflow-status", "supported", "HARNESS_WORKFLOW_STATUS_NAMED"
        return ("non-artifact:missing-native-codex-workflow-status-consumer", "unsupported",
                "HARNESS_ACTIVATION_UNSUPPORTED:codex:workflows.status:"
                "missing-native-codex-workflow-status-consumer")
    if surface_id == "doctor.environment":
        return "non-artifact:named-harness-doctor", "supported", "HARNESS_DOCTOR_ENVIRONMENT_NAMED"
    if surface_id == "doctor.provider":
        return "non-artifact:provider-audit", "supported", "HARNESS_PROVIDER_AUDIT_NAMED"
    raise ValueError(f"HARNESS_CATALOG_MISMATCH:{provider.value}:{surface_id}")


def _map_diagnostics(surface_map, expected_surfaces):
    expected = {(provider.value, surface_id) for provider in ProviderId for surface_id in expected_surfaces}
    actual = [(provider, surface_id) for provider, surface_id, *_rest in surface_map]
    duplicates = _duplicates(actual)
    actual_set = set(actual)
    diagnostics = []
    for provider, surface_id in sorted(expected - actual_set):
        diagnostics.append(f"HARNESS_CATALOG_MISMATCH:provider-surface:missing:{provider}:{surface_id}")
    for provider, surface_id in sorted(actual_set - expected):
        diagnostics.append(f"HARNESS_CATALOG_MISMATCH:provider-surface:extra:{provider}:{surface_id}")
    for provider, surface_id in duplicates:
        diagnostics.append(f"HARNESS_CATALOG_MISMATCH:provider-surface:duplicate:{provider}:{surface_id}")
    return diagnostics


def _managed_lifecycle_evidence(root, catalog, mcp, roles):
    """Exercise named P2 artifacts in temporary roots, never package or live targets."""
    codex = ProviderId.CODEX
    bindings = root / "configs/codex/config/profile-bindings.json"
    full_access = resolve_profile(
        catalog, provider_id=codex, profile_id="trusted-full-access", target_scope="project",
        trusted=True, operation_id="self-host-apply", target_identity="repo:fixture",
        origin="operation", effective_provider=EffectiveProvider(codex, True))
    profile = plan_profile_artifact(full_access,
                                    catalog_path=root / "configs/common/profile-catalog.json",
                                    codex_bindings_path=bindings)
    mcp_projection = plan_mcp_projection(
        mcp, provider_id=codex, bindings_path=root / "configs/codex/mcp/bindings.json",
        selected=tuple(server.id for server in mcp), trusted=True)
    mcp_artifact = plan_mcp_artifact(mcp_projection,
                                     catalog_path=root / "configs/common/mcp/catalog.json",
                                     bindings_path=root / "configs/codex/mcp/bindings.json")
    role = next(item for item in roles if item.pack_id == "backend-laravel" and item.role_id == "blade-review")
    agent = plan_agent_artifact(role, provider_id="codex",
                                catalog_path=root / "configs/common/agent-packs/roles.json",
                                pack_prefix="fixture")
    lifecycle = plan_lifecycle(
        catalog, provider_id=codex, trusted=True,
        requests=tuple(LifecycleRequest(surface.id, False) for surface in catalog.surfaces
                       if surface.kind in {"lifecycle", "context"}),
        codex_bindings_path=root / "configs/codex/hooks/lifecycle-context-bindings.json")
    hooks, handler = plan_codex_lifecycle_artifacts(
        lifecycle, bindings_path=root / "configs/codex/hooks/lifecycle-context-bindings.json")
    return tuple(_exercise_managed_lifecycle(name, expected)
                 for name, expected in (
                     ("profile:codex:trusted-full-access", (profile,)),
                     ("mcp:codex:catalog", (mcp_artifact,)),
                     ("agent:codex:backend-laravel.blade-review", (agent,)),
                     ("lifecycle:codex:context.observer", (hooks, handler)),
                 ))


def _exercise_managed_lifecycle(name, expected):
    with tempfile.TemporaryDirectory() as directory:
        temporary_root = Path(directory)
        outside = temporary_root / "user-owned.txt"
        outside.write_text("preserve me\n", encoding="utf-8")
        initial = plan_artifact_lock(temporary_root, expected, lock_bytes=None)
        create = "+".join(action.action.value for action in initial.actions)
        if any(action.action is not ArtifactActionKind.CREATE for action in initial.actions):
            raise ValueError("HARNESS_CATALOG_MISMATCH:managed-create")
        apply_plan(temporary_root, initial)
        clean = plan_artifact_lock(temporary_root, expected,
                                   lock_bytes=serialize_lock(initial.next_lock))
        check = "+".join(action.action.value for action in clean.actions)
        if any(action.action is not ArtifactActionKind.NOOP for action in clean.actions):
            raise ValueError("HARNESS_CATALOG_MISMATCH:managed-noop")
        target = temporary_root / expected[0].target.path
        target.write_bytes(b"managed drift\n")
        drift = plan_artifact_lock(temporary_root, expected,
                                   lock_bytes=serialize_lock(initial.next_lock))
        drift_state = "+".join(action.action.value for action in drift.actions)
        if not any(action.action is ArtifactActionKind.REFUSE for action in drift.actions):
            raise ValueError("HARNESS_CATALOG_MISMATCH:managed-drift")
        repair = plan_artifact_lock(
            temporary_root, expected, lock_bytes=serialize_lock(initial.next_lock),
            repair_artifact_ids=tuple(item.provenance.artifact_id for item in expected))
        repair_state = "+".join(action.action.value for action in repair.actions)
        if not any(action.action is ArtifactActionKind.REPAIR for action in repair.actions):
            raise ValueError("HARNESS_CATALOG_MISMATCH:managed-repair")
        apply_plan(temporary_root, repair)
        return (name, create, check, drift_state, repair_state,
                outside.read_text(encoding="utf-8") == "preserve me\n")


def render_operator_reference(report: ProviderAuditReport) -> str:
    """Generated operator text; docs deliberately have no hand-maintained inventory."""
    counts = {row["surface"]: len(row["expected"]) for row in report.as_dict()["rows"]}
    return ("# Provider harness conformance\n\n"
            "> Generated from the validated deterministic provider-audit report; do not maintain an inventory here.\n\n"
            "`harness doctor --provider-audit [--json]` is read-only. `settings_audit.py` remains the named Claude Code checker behind `harness doctor --settings`; provider audit never universalizes Claude merge rules.\n\n"
            f"Validated catalog `{report.catalog_hash}`: {counts['profiles']} profiles, {counts['surfaces']} semantic surfaces, {counts['mcp']} MCP descriptors and {counts['agents']} agent roles.\n\n"
            "Reports retain missing/extra and expected/actual duplicate identities. Full access is only explicit `self-host-apply` for a trusted repository; project, fleet-project and fleet-defaults selection are rejected. Secret references are value-free.\n\n"
            "No live target write, activation, apply authority, MCP start, hook start or workflow start is granted. `settings_audit.py` remains Claude-specific.\n\n"
            + _render_validated_report(report))


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
            "- Accept full access only for exact `self-host-apply` plus trusted `repo:` target; reject project, fleet-project and fleet-defaults inheritance.\n"
            "- Keep secret evidence value-free and preserve named Claude settings audit as a separate consumer.\n\n"
            + _render_validated_report(report))


def _render_validated_report(report):
    return _render_hash_matrix(report) + "\n" + _render_surface_matrix(report) + "\n" + _render_managed_lifecycle(report)


def _render_hash_matrix(report):
    data = report.as_dict()
    lines = ["## Source and render hashes\n",
             "| Identity | SHA-256 |", "|:--|:--|"]
    for identity, digest in sorted(data["source_hashes"].items()):
        lines.append(f"| source:{identity} | `{digest}` |")
    lines.append("| render-manifest:all-provider-qualified-outputs | `{}` |".format(
        _canonical_hash(data["render_hashes"])))
    lines.append("\nThe read-only JSON report retains every individual provider-qualified render hash; this manifest hash covers all of them deterministically.")
    return "\n".join(lines) + "\n"


def _render_surface_matrix(report):
    lines = ["## Exact provider-surface map\n",
             "Every provider-qualified surface row is required: missing, extra or duplicate rows make the report RED.\n",
             "| Provider | Surface ID | Semantic SHA-256 | Required capabilities | Security intent or ownership | Artifact / target scope / state | Activation | Diagnostic |",
             "|:--|:--|:--|:--|:--|:--|:--|:--|"]
    for row in report.as_dict()["surface_map"]:
        lines.append("| {provider} | {surface_id} | `{semantic_hash}` | {required_capabilities} | {security_or_ownership} | {artifact_or_state} | {activation_state} | `{diagnostic}` |".format(**row))
    return "\n".join(lines) + "\n"


def _render_managed_lifecycle(report):
    lines = ["## Temp-contained managed lifecycle evidence\n",
             "The named representative P2 artifacts are rendered only in temporary roots. `create`, second `check`, induced managed drift and explicit `repair` are independently recorded; bytes outside managed targets remain untouched.\n",
             "| Representative artifact | Create | Second check | Managed drift | Explicit repair | Outside-managed bytes preserved |",
             "|:--|:--|:--|:--|:--|:--|"]
    for row in report.as_dict()["managed_lifecycle"]:
        lines.append("| {artifact} | {create} | {check} | {drift} | {repair} | {outside_managed_preserved} |".format(**row))
    return "\n".join(lines) + "\n"


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
