#!/usr/bin/env python3
"""Generate/check provider support docs from the validated root manifest."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import (ProviderId, SupportLevel, load_provider_manifest,
                  provider_manifest_sha256, support_for)


MANIFEST_REL = "packages/aicore/configs/provider-capabilities.json"
MANIFEST_PATH = ROOT / MANIFEST_REL
README_PATH = ROOT / "README.md"
GUIDE_PATH = ROOT / "docs/provider-support.md"
BEGIN = "<!-- BEGIN GENERATED PROVIDER CAPABILITIES -->"
END = "<!-- END GENERATED PROVIDER CAPABILITIES -->"
_ALL_LEVELS = frozenset({"native", "adapted", "unsupported"})
# Analytics capabilities are owned by the analyst package and declared here once.
_ANALYTICS_CAPABILITIES = ("analytics.normalized-events", "analytics.run-report", "analytics.legacy-migration")


def independent_inventory(root: Path = ROOT) -> dict[str, object]:
    """Derive the expected common set from terminal semantic catalogs/contracts."""
    planner = json.loads((root / "packages/planner/configs/command-routing.json").read_text())
    planner_ids = {item for command in planner["commands"]
                for item in command["capability_requirements"]}
    mapping_ids = {provider: set(mapping["capability_bindings"])
                   for provider, mapping in planner["mappings"].items()}
    profile = json.loads((root / "packages/harness/configs/common/profile-catalog.json").read_text())
    harness_ids = {surface["id"] for surface in profile["surfaces"]}
    instructions = json.loads((root / "packages/harness/configs/common/instructions/catalog.json").read_text())
    instruction_ids = {item["id"] for item in instructions["capability_requirements"]}
    analytics_ids = set(_ANALYTICS_CAPABILITIES)
    expected = planner_ids | harness_ids | instruction_ids | analytics_ids
    return {
        "expected": tuple(sorted(expected)),
        "contributors": {
            "planner": tuple(sorted(planner_ids)), "harness": tuple(sorted(harness_ids)),
            "instructions": tuple(sorted(instruction_ids)),
            "analytics": tuple(sorted(analytics_ids)),
        },
        "planner_mapping_missing": {
            provider: sorted(planner_ids - values) for provider, values in mapping_ids.items()},
        "task_mapping_extra": {
            provider: sorted(values - planner_ids) for provider, values in mapping_ids.items()},
    }


def production_requirements(root: Path = ROOT) -> tuple[tuple[str, str, str, frozenset[str]], ...]:
    """List named production pre-render/doctor requirements independently of outputs."""
    rows = []
    for provider in ProviderId:
        rows.append(("skiller.publication", provider.value, "skills.repository",
                     frozenset({"native", "adapted"})))
    routing = json.loads((root / "packages/planner/configs/command-routing.json").read_text())
    task_providers = set(routing["mappings"])
    for provider in ProviderId:
        if provider.value not in task_providers:
            continue
        provider_bindings = (routing["mappings"].get(provider.value, {})
                             .get("capability_bindings", {}))
        for command in routing["commands"]:
            requirements = tuple(command["capability_requirements"])
            # Provider command projections are generated only when every required
            # capability is satisfiable for that provider (native|adapted).
            if not all(provider_bindings.get(capability) in {"native", "adapted"}
                       for capability in requirements):
                continue
            for capability in requirements:
                rows.append((f"planner.{command['command_id']}", provider.value, capability,
                             frozenset({"native", "adapted"})))
    profile = json.loads((root / "packages/harness/configs/common/profile-catalog.json").read_text())
    for provider in ProviderId:
        for surface in profile["surfaces"]:
            rows.append(("harness.provider-audit", provider.value, surface["id"], _ALL_LEVELS))
    instructions = json.loads((root / "packages/harness/configs/common/instructions/catalog.json").read_text())
    for provider in ProviderId:
        for requirement in instructions["capability_requirements"]:
            rows.append(("harness.instructions", provider.value, requirement["id"],
                         frozenset(requirement["accepted_levels"])))
        rows.append(("maind.provider-deploy", provider.value, "mcp.catalog",
                     frozenset({"native", "adapted"})))
        for capability in ("analytics.normalized-events", "analytics.run-report",
                           "analytics.legacy-migration"):
            rows.append(("analyst.provider-reader", provider.value, capability, _ALL_LEVELS))
    return tuple(sorted(set(rows), key=lambda row: (row[0], row[1], row[2])))


def conformance(root: Path = ROOT) -> dict[str, object]:
    manifest_path = root / MANIFEST_REL
    manifest = load_provider_manifest(manifest_path)
    inventory = independent_inventory(root)
    actual = tuple(item.capability_id.value for item in manifest.capabilities)
    expected = inventory["expected"]
    duplicates = sorted(item for item in set(actual) if actual.count(item) > 1)
    requirement_failures = []
    requirement_rows = []
    for consumer, provider_text, capability_id, accepted in production_requirements(root):
        try:
            support = support_for(manifest, capability_id, ProviderId(provider_text))
        except ValueError:
            requirement_failures.append(
                f"{consumer}:{provider_text}:{capability_id}:missing")
            continue
        if support.level.value not in accepted:
            requirement_failures.append(
                f"{consumer}:{provider_text}:{capability_id}:level-{support.level.value}")
        requirement_rows.append({"consumer": consumer, "provider": provider_text,
                                 "capability": capability_id,
                                 "accepted_levels": sorted(accepted),
                                 "observed_level": support.level.value})
    matrix = {(row.provider_id.value, capability.capability_id.value)
              for capability in manifest.capabilities for row in capability.support}
    expected_matrix = {(provider.value, capability_id) for provider in ProviderId
                       for capability_id in actual}
    source_bytes = manifest_path.read_bytes()
    report = {
        "contract_version": manifest.contract_version,
        "catalog_version": manifest.catalog_version,
        "canonical_sha256": provider_manifest_sha256(manifest),
        "carrier_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "carrier_terminal_lf": source_bytes.endswith(b"\n"),
        "missing": sorted(set(expected) - set(actual)),
        "extra": sorted(set(actual) - set(expected)),
        "duplicates": duplicates,
        "matrix_missing": sorted(f"{provider}:{capability}"
                                 for provider, capability in expected_matrix - matrix),
        "matrix_extra": sorted(f"{provider}:{capability}"
                               for provider, capability in matrix - expected_matrix),
        "native_extensions": [item.extension_id.value for item in manifest.native_extensions],
        "requirement_failures": requirement_failures,
        "requirements": requirement_rows,
        **{key: value for key, value in inventory.items() if key != "expected"},
    }
    report["green"] = not any((report["missing"], report["extra"], report["duplicates"],
                               report["matrix_missing"], report["matrix_extra"],
                               report["requirement_failures"],
                               *report["planner_mapping_missing"].values(),
                               *report["task_mapping_extra"].values()))
    return report


_PROVIDER_LABELS = {
    ProviderId.CLAUDE_CODE: "Claude Code",
    ProviderId.CODEX: "Codex",
    ProviderId.CURSOR: "Cursor",
    ProviderId.GROK: "Grok",
}


def _matrix(manifest) -> str:
    providers = tuple(manifest.providers)
    header = "| Capability | " + " | ".join(_PROVIDER_LABELS[item] for item in providers) + " |"
    align = "|:--|" + "|".join(":--:" for _ in providers) + "|"
    lines = [header, align]
    for capability in manifest.capabilities:
        levels = {row.provider_id: row.level.value for row in capability.support}
        cells = " | ".join(levels[item] for item in providers)
        lines.append(f"| `{capability.capability_id.value}` | {cells} |")
    return "\n".join(lines)


def render_readme_block(manifest, report) -> str:
    return "\n".join([
        BEGIN,
        "### Provider support (generated)",
        "",
        (f"Single manifest: contract `{manifest.contract_version}`, catalog "
         f"`{manifest.catalog_version}`, canonical SHA-256 "
         f"`{report['canonical_sha256']}`. Manifest ("
         "`packages/aicore/configs/provider-capabilities.json`) — source of truth, hand-edited, no "
         "generator: `root.generated-artifacts` does not apply to it. Details and "
         "operations: [provider support](docs/provider-support.md)."),
        "",
        _matrix(manifest),
        "",
        ("Unsupported reasons legend: `not implemented` (adapter/binding not shipped), "
         "`API-capped` (provider has no suitable project-scoped API), "
         "`not applicable` (intent has no provider object to migrate/read)."),
        END,
    ])


def render_guide(manifest, report) -> bytes:
    lines = [
        "# Provider support",
        "",
        "> Generated by `python3 scripts/provider-docs.py --write`; do not edit manually.",
        "",
        "## Provenance",
        "",
        f"- Contract: `{manifest.contract_version}`",
        f"- Catalog: `{manifest.catalog_version}`",
        f"- Canonical JSON SHA-256 (without carrier LF): `{report['canonical_sha256']}`",
        f"- Carrier SHA-256 (canonical bytes plus one LF): `{report['carrier_sha256']}`",
        f"- Common capabilities: `{len(manifest.capabilities)}`; Native Extensions: `{len(manifest.native_extensions)}`",
        "",
        "Support levels, provider bindings, limitations, evidence and diagnostics below come only from "
        "[`packages/aicore/configs/provider-capabilities.json`](../packages/aicore/configs/provider-capabilities.json). Package catalogs own "
        "semantic intent and requirements, not a second support matrix.",
        "",
        "## Manifest provenance",
        "",
        "`packages/aicore/configs/provider-capabilities.json` is the source of truth, hand-written, with no "
        "generator; it is edited by a human or agent directly. `root.generated-artifacts` "
        "(\"generated manifests and documents are produced by their generator and never "
        "hand-edited\") does not apply to it — the manifest is this page's *input*, not one of "
        "`scripts/provider-docs.py`'s outputs. After editing the manifest: run "
        "`python3 scripts/provider-docs.py --write` to regenerate this page and the README "
        "block, then `python3 scripts/provider-docs.py --check` to confirm both are in sync.",
        "",
        "## Capability matrix",
        "",
        _matrix(manifest),
        "",
        "## Unsupported reason legend",
        "",
        "- `not implemented` — this release does not ship a deterministic adapter or provider binding.",
        "- `API-capped` — provider documentation exposes no suitable project-scoped API surface.",
        "- `not applicable` — the capability intent has no provider object to migrate/read.",
        "",
        "## Provider selection and precedence",
        "",
        "Provider selection uses the frozen precedence `operation > project > fleet-project > fleet-defaults > legacy`. "
        "An absent project carrier is not `unsupported`: legacy compatibility enables Claude Code and leaves Codex "
        "disabled, with explicit provenance. Unknown providers/capabilities and an explicitly enabled unsupported "
        "capability fail before render or write.",
        "",
        "Project example (`.swissknife.json`):",
        "",
        "```json",
        '{"providers":{"contract_version":"1.0.0","selection":{"claude-code":{"enabled":true},"codex":{"enabled":true}}}}',
        "```",
        "",
        "## Security and operations",
        "",
        "Project Trust, Approval Policy and Sandbox Boundary are independent axes. Full access is never a project or "
        "fleet default: it requires a trusted repository plus the explicit `self-host-apply` operation and exact "
        "`repo:` target identity. Provider docs do not grant activation, live apply or repair authority.",
        "",
        "Read-only checks:",
        "",
        "```bash",
        "python3 scripts/provider-docs.py --check",
        "harness doctor --provider-audit --json",
        "skiller connect --dry-run        # Claude Code projection",
        "skiller sync --dry-run           # only inside a project with .swissknifeman/config.json (mode=vendor)",
        "maind sync --project <id> --dry-run --json",
        "```",
        "",
        "Apply/update/repair are separate explicit operations over managed targets:",
        "",
        "```bash",
        "skiller connect                  # Claude Code install/update",
        "skiller sync                     # selected managed skill projections",
        "skiller sync --repair            # explicit managed repair",
        "maind sync --project <id> --mode update",
        "maind sync --project <id> --mode repair",
        "```",
        "",
        "Native planner invocation examples:",
        "",
        "```text",
        "Claude Code: /planner:fix <brief>",
        "Codex:       $ planner:fix <brief>",
        "```",
        "",
        "## Support records",
        "",
    ]
    for capability in manifest.capabilities:
        lines.extend([f"### `{capability.capability_id.value}`", "", escape(capability.intent, quote=False), ""])
        for support in capability.support:
            evidence = "; ".join(
                f"[{item.verified_at}] {escape(item.claim, quote=False)} — "
                f"`{item.source}` ({escape(item.scope, quote=False)})"
                for item in support.evidence)
            binding = (json.dumps(_thaw(support.binding), ensure_ascii=False, sort_keys=True)
                       if support.binding is not None else "—")
            lines.extend([
                f"- **{support.provider_id.value}** — `{support.level.value}`; binding: `{binding}`; "
                f"adapter: `{support.adapter_id or '—'}`.",
                f"  Diagnostic: {escape(support.diagnostic, quote=False)}",
                f"  Limitations: {escape('; '.join(support.limitations) or 'none', quote=False)}.",
                f"  Evidence: {evidence}.",
                "",
            ])
    lines.extend(["## Native Extensions", ""])
    if not manifest.native_extensions:
        lines.append("None in catalog `1.0.0`. Provider-specific instruction sections are not Native Extensions.")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _thaw(value):
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 for item in value):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value


def expected_outputs(root: Path = ROOT) -> dict[Path, bytes]:
    manifest = load_provider_manifest(root / MANIFEST_REL)
    report = conformance(root)
    if not report["green"]:
        raise ValueError("PROVIDER_DOCS_CONFORMANCE_FAILED:" + json.dumps(
            {key: value for key, value in report.items()
             if key.endswith(("missing", "extra", "failures")) and value}, sort_keys=True))
    readme_path = root / "README.md"
    current = readme_path.read_text(encoding="utf-8")
    block = render_readme_block(manifest, report)
    if BEGIN in current or END in current:
        if current.count(BEGIN) != 1 or current.count(END) != 1 or current.index(BEGIN) > current.index(END):
            raise ValueError("PROVIDER_DOCS_README_MARKERS_INVALID")
        start, finish = current.index(BEGIN), current.index(END) + len(END)
        readme = current[:start] + block + current[finish:]
    else:
        anchor = "## Features\n\n"
        if anchor not in current:
            raise ValueError("PROVIDER_DOCS_README_ANCHOR_MISSING")
        readme = current.replace(anchor, anchor + block + "\n\n", 1)
    return {readme_path: readme.encode("utf-8"),
            root / "docs/provider-support.md": render_guide(manifest, report)}


def run(mode: str, root: Path = ROOT) -> int:
    outputs = expected_outputs(root)
    drift = []
    for path, expected in outputs.items():
        current = path.read_bytes() if path.is_file() else None
        if current != expected:
            drift.append(path)
            if mode == "write":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(expected)
    if mode == "check" and drift:
        for path in drift:
            print(f"provider docs drift: {path.relative_to(root)}", file=sys.stderr)
        return 1
    if mode == "write":
        for path in drift:
            print(path.relative_to(root))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    return run("write" if args.write else "check")


if __name__ == "__main__":
    raise SystemExit(main())
