#!/usr/bin/env python3
"""Thin stdlib CLI-front over `command_render.py` planning/apply API (P1.3).

No custom rendering logic: only loading the canonical directory
(`command_catalog.build_command_catalog`), building both provider-plans
(`plan_claude_command_render`/`plan_codex_command_render`) and their read-only/write
application (`apply_claude_command_plan`/`plan_codex_command_apply` +
`apply_codex_command_plan`) explicitly `--root`. It also writes (`--write`) or checks (`--check`) the snapshot of the aicore
model catalog inside `configs/command-routing.json`. Needs aicore: AICORE_ROOT, `_vendor/aicore` or the sibling `aicore`.

    python3 packages/planner/scripts/render-provider-commands.py --check --root .
    python3 packages/planner/scripts/render-provider-commands.py --write --repair-owned --root .
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# --- aicore locator (python) ---
# Finds the aicore foundation: $AICORE_ROOT, then <module>/_vendor/aicore, then the sibling <module>/../aicore.
# Canonical copy: packages/aicore/scripts/aicore_locator.py; copies must stay identical.
def _aicore_lib(module_root):
    import json
    import os
    from pathlib import Path

    def _ok(root):
        try:
            return json.loads((root / "unit.json").read_text(encoding="utf-8")).get("id") == "aicore"
        except (OSError, ValueError):
            return False

    explicit = os.environ.get("AICORE_ROOT")
    if explicit:
        if not _ok(Path(explicit)):
            raise SystemExit(f"AICORE_NOT_FOUND: AICORE_ROOT={explicit} is not an aicore checkout")
        return Path(explicit).resolve() / "lib"
    for root in (Path(module_root) / "_vendor" / "aicore", Path(module_root).parent / "aicore"):
        if _ok(root):
            return root.resolve() / "lib"
    return None
# --- end aicore locator (python) ---

_PKG_ROOT = Path(__file__).resolve().parent.parent       # packages/planner
sys.path.insert(0, str(_PKG_ROOT / "lib"))
_lib = _aicore_lib(_PKG_ROOT)
if _lib is None:
    print("AICORE_NOT_FOUND: rendering provider projections needs aicore; set AICORE_ROOT", file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(1, str(_lib))
os.environ.setdefault("AICORE_ROOT", str(_lib.parent))

from planner import MODULE_ID  # noqa: E402
from planner.command_catalog import build_command_catalog  # noqa: E402
from planner.integration.models import routing_snapshot, routing_text  # noqa: E402
from planner.command_render import (  # noqa: E402
    PROVIDER_LOCK_PATH, apply_claude_command_plan, apply_codex_command_plan,
    build_provider_command_parity_report, mapping_from_catalog, parse_next_carrier,
    plan_claude_alias_render, plan_claude_command_render, plan_codex_command_apply, plan_codex_command_render,
    plan_cursor_command_render, plan_grok_command_render, render_provider_commands_reference,
    render_provider_model_roles_reference,
)


_PARITY_FIXTURE = Path("packages/planner/tests/fixtures_data/provider-command-parity.json")
_OPERATOR_REFERENCE = Path("packages/planner/docs/reference/provider-commands.md")
_MODEL_ROLES_REFERENCE = Path("packages/planner/docs/reference/provider-model-roles.md")
_CLAUDE_GOLDEN_ROOT = Path("packages/planner/tests/fixtures_data/claude-command-golden")
_ROUTING = Path("packages/planner/configs/command-routing.json")
_ALIAS_PREFIX = "packages/planner/aliases/task/"  # Compatibility alias: remove in the next minor release.


def _routing_snapshot_bytes(root: Path) -> bytes:
    """Routing config with the model selectors and inventory taken from the aicore catalog."""
    routing = json.loads((root / _ROUTING).read_text(encoding="utf-8"))
    return routing_text(routing_snapshot(routing)).encode("utf-8")


def _build_plans(root: Path, *, allow_managed_drift: bool = False):
    command_root = root / "packages/planner/commands"
    routing_path = root / "packages/planner/configs/command-routing.json"
    catalog = build_command_catalog(command_root, routing_path)
    mappings = {provider_id: mapping_from_catalog(catalog, provider_id)
                for provider_id in ("claude-code", "codex", "cursor", "grok")}
    support = {provider_id: dict(mapping.capability_bindings)
               for provider_id, mapping in mappings.items()}
    plugin_bytes = (root / "packages/planner/.claude-plugin/plugin.json").read_bytes()
    if allow_managed_drift:
        plugin_text = plugin_bytes.decode("utf-8")
        plugin_data = json.loads(plugin_text)
        if plugin_data.get("name") == MODULE_ID and plugin_data.get("version") != catalog.plugin_version:
            plugin_text, count = re.subn(
                r'("version"\s*:\s*")[^"]+(")',
                rf'\g<1>{catalog.plugin_version}\2', plugin_text, count=1)
            if count != 1:
                raise ValueError("CMD_SOURCE_DRIFT: Claude plugin version is not replaceable")
            plugin_bytes = plugin_text.encode("utf-8")
    claude_plan = plan_claude_command_render(
        catalog, mappings["claude-code"], support["claude-code"], plugin_bytes=plugin_bytes)
    codex_plan = plan_codex_command_render(catalog, mappings["codex"], support["codex"])
    cursor_plan = plan_cursor_command_render(catalog, mappings["cursor"], support["cursor"])
    grok_plan = plan_grok_command_render(catalog, mappings["grok"], support["grok"])
    if allow_managed_drift and not (claude_plan.ok and codex_plan.ok and cursor_plan.ok
                                    and grok_plan.ok):
        return claude_plan, codex_plan, cursor_plan, grok_plan, None, None
    fixture = json.loads((root / _PARITY_FIXTURE).read_text(encoding="utf-8"))
    report = build_provider_command_parity_report(
        catalog, claude_plan, codex_plan, cursor_plan, grok_plan, mappings,
        expected_command_ids=tuple(row["command_id"] for row in fixture["commands"]),
        next_carriers=tuple(parse_next_carrier(row["valid"])
                            for row in fixture["next_forms"]))
    model_roles_bytes = render_provider_model_roles_reference(catalog)
    return (claude_plan, codex_plan, cursor_plan, grok_plan,
            render_provider_commands_reference(report), model_roles_bytes)


def _build_alias_plan(root: Path):
    # Compatibility alias: remove in the next minor release.
    catalog = build_command_catalog(root / "packages/planner/commands",
                                    root / "packages/planner/configs/command-routing.json")
    plugin_bytes = (root / "packages/planner/.claude-plugin/plugin.json").read_bytes()
    return plan_claude_alias_render(catalog, plugin_bytes=plugin_bytes)


def _alias_golden_projection(alias_plan) -> dict[Path, bytes]:
    """Mirror the compatibility alias plugin into its byte-exact test fixture."""
    return {_CLAUDE_GOLDEN_ROOT / "aliases" / "task" / artifact.path.removeprefix(_ALIAS_PREFIX):
            artifact.managed_bytes for artifact in alias_plan.artifacts}


def _claude_golden_projection(claude_plan) -> dict[Path, bytes]:
    """Mirror the Claude command surface into its byte-exact test fixture."""
    projection = {}
    for artifact in claude_plan.artifacts:
        if artifact.path == "packages/planner/.claude-plugin/plugin.json":
            target = _CLAUDE_GOLDEN_ROOT / "plugin.json"
        elif artifact.path.startswith("packages/planner/commands/"):
            target = _CLAUDE_GOLDEN_ROOT / "commands" / Path(artifact.path).name
        else:  # pragma: no cover - the renderer owns this exact projection surface
            raise ValueError(f"unexpected Claude artifact: {artifact.path}")
        projection[target] = artifact.managed_bytes
    return projection


def _print_diagnostics(label: str, plan) -> None:
    for diagnostic in plan.diagnostics:
        print(f"{label}: {diagnostic.severity} {diagnostic.code} "
              f"{diagnostic.command_id} {diagnostic.path} {diagnostic.message}",
              file=sys.stderr)


def _adapter_drift(root: Path, plan) -> tuple[str, ...]:
    drift = []
    for artifact in plan.artifacts:
        target = root / artifact.path
        try:
            current = target.read_bytes()
        except OSError:
            current = None
        if current != artifact.managed_bytes:
            drift.append(artifact.path)
    return tuple(drift)


def _write_adapter(root: Path, plan) -> int:
    written = 0
    for artifact in plan.artifacts:
        target = root / artifact.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != artifact.managed_bytes:
            target.write_bytes(artifact.managed_bytes)
            written += 1
    return written


def _repair_version_transition(root: Path, claude_plan, codex_plan, cursor_plan, grok_plan) -> int:
    """Repair only generator-owned targets before rebuilding a clean parity report."""
    diagnostics = (*claude_plan.diagnostics, *codex_plan.diagnostics,
                   *cursor_plan.diagnostics, *grok_plan.diagnostics)
    if any(item.code != "CMD_SOURCE_DRIFT" for item in diagnostics):
        return 1
    for artifact in claude_plan.artifacts:
        target = root / artifact.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.managed_bytes)
    lock_path = root / PROVIDER_LOCK_PATH
    lock_bytes = lock_path.read_bytes() if lock_path.is_file() else None
    probe = plan_codex_command_apply(root, codex_plan, lock_bytes=lock_bytes)
    repair_ids = tuple(action.artifact_id for action in probe.actions
                       if action.action.value == "refuse")
    artifact_plan = plan_codex_command_apply(
        root, codex_plan, lock_bytes=lock_bytes, repair_artifact_ids=repair_ids)
    if any(action.action.value == "refuse" for action in artifact_plan.actions):
        return 1
    apply_codex_command_plan(root, artifact_plan)
    _write_adapter(root, cursor_plan)
    _write_adapter(root, grok_plan)
    return 0


def cmd_check(root: Path, claude_plan, codex_plan, cursor_plan, grok_plan, reference_bytes: bytes,
              model_roles_bytes: bytes, alias_plan, routing_bytes: bytes) -> int:
    routing_drift = (root / _ROUTING).read_bytes() != routing_bytes
    claude_drift = (apply_claude_command_plan(root, claude_plan, check=True)
                    + apply_claude_command_plan(root, alias_plan, check=True))
    lock_path = root / PROVIDER_LOCK_PATH
    lock_bytes = lock_path.read_bytes() if lock_path.is_file() else None
    codex_artifact_plan = plan_codex_command_apply(root, codex_plan, lock_bytes=lock_bytes)
    codex_drift = tuple(action for action in codex_artifact_plan.actions
                        if action.action.value != "noop")
    reference_path = root / _OPERATOR_REFERENCE
    reference_drift = (not reference_path.is_file()
                       or reference_path.read_bytes() != reference_bytes)
    model_roles_path = root / _MODEL_ROLES_REFERENCE
    model_roles_drift = (not model_roles_path.is_file()
                         or model_roles_path.read_bytes() != model_roles_bytes)
    golden_drift = tuple(
        path for path, expected in {**_claude_golden_projection(claude_plan),
                                    **_alias_golden_projection(alias_plan)}.items()
        if not (root / path).is_file() or (root / path).read_bytes() != expected
    )
    cursor_drift = _adapter_drift(root, cursor_plan)
    grok_drift = _adapter_drift(root, grok_plan)
    if (not claude_drift and not codex_drift and not cursor_drift and not grok_drift
            and not reference_drift and not routing_drift
            and not model_roles_drift and not golden_drift):
        print("render-provider-commands: check OK (no-op)")
        return 0
    for path in claude_drift:
        print(f"drift: claude-code {path}", file=sys.stderr)
    for action in codex_drift:
        print(f"drift: codex {action.artifact_id} {action.action.value}", file=sys.stderr)
    if routing_drift:
        print(f"drift: model-catalog-snapshot {_ROUTING}", file=sys.stderr)
    if reference_drift:
        print(f"drift: operator-reference {_OPERATOR_REFERENCE}", file=sys.stderr)
    if model_roles_drift:
        print(f"drift: model-roles-reference {_MODEL_ROLES_REFERENCE}", file=sys.stderr)
    for path in golden_drift:
        print(f"drift: claude-golden {path}", file=sys.stderr)
    for path in cursor_drift:
        print(f"drift: cursor {path}", file=sys.stderr)
    for path in grok_drift:
        print(f"drift: grok {path}", file=sys.stderr)
    return 1


def cmd_write(root: Path, claude_plan, codex_plan, cursor_plan, grok_plan, reference_bytes: bytes,
              model_roles_bytes: bytes, alias_plan, *, repair_owned: bool) -> int:
    apply_claude_command_plan(root, claude_plan, check=False)
    apply_claude_command_plan(root, alias_plan, check=False)
    lock_path = root / PROVIDER_LOCK_PATH
    lock_bytes = lock_path.read_bytes() if lock_path.is_file() else None
    repair_ids: tuple[str, ...] = ()
    if repair_owned and lock_bytes is not None:
        probe = plan_codex_command_apply(root, codex_plan, lock_bytes=lock_bytes)
        repair_ids = tuple(action.artifact_id for action in probe.actions
                           if action.action.value == "refuse")
    codex_artifact_plan = plan_codex_command_apply(
        root, codex_plan, lock_bytes=lock_bytes, repair_artifact_ids=repair_ids)
    refused = [action for action in codex_artifact_plan.actions if action.action.value == "refuse"]
    if refused:
        for action in refused:
            print(f"refuse: {action.artifact_id} (pass --repair-owned to repair managed drift)",
                  file=sys.stderr)
        return 1
    apply_codex_command_plan(root, codex_artifact_plan)
    reference_path = root / _OPERATOR_REFERENCE
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    reference_path.write_bytes(reference_bytes)
    model_roles_path = root / _MODEL_ROLES_REFERENCE
    model_roles_path.parent.mkdir(parents=True, exist_ok=True)
    model_roles_path.write_bytes(model_roles_bytes)
    for path, contents in {**_claude_golden_projection(claude_plan),
                           **_alias_golden_projection(alias_plan)}.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
    written = len([action for action in codex_artifact_plan.actions
                  if action.action.value != "noop"])
    cursor_written = _write_adapter(root, cursor_plan)
    grok_written = _write_adapter(root, grok_plan)
    print(f"render-provider-commands: wrote {len(claude_plan.artifacts)} Claude artifact(s), "
          f"{written} Codex artifact(s) changed, {cursor_written} Cursor artifact(s) changed, "
          f"{grok_written} Grok artifact(s) changed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--repair-owned", action="store_true",
                        help="repair managed-drift Codex artifacts (only with --write)")
    args = parser.parse_args(argv)
    if args.repair_owned and not args.write:
        parser.error("--repair-owned requires --write")
    root = Path(args.root).resolve()

    routing_bytes = _routing_snapshot_bytes(root)
    if args.write and (root / _ROUTING).read_bytes() != routing_bytes:
        (root / _ROUTING).write_bytes(routing_bytes)
    try:
        (claude_plan, codex_plan, cursor_plan, grok_plan,
         reference_bytes, model_roles_bytes) = _build_plans(root)
    except ValueError as exc:
        if not (args.write and args.repair_owned and "CMD_SOURCE_DRIFT" in str(exc)):
            raise
        # A publication-version bump makes every owned provider target stale at
        # once. Repair those generated targets first, then rebuild the parity
        # report from a clean projection. Source/catalog validation has already
        # succeeded; only managed output drift reaches this branch.
        claude_plan, codex_plan, cursor_plan, grok_plan, _reference, _roles = _build_plans(
            root, allow_managed_drift=True)
        if _repair_version_transition(root, claude_plan, codex_plan, cursor_plan, grok_plan):
            return 1
        (claude_plan, codex_plan, cursor_plan, grok_plan,
         reference_bytes, model_roles_bytes) = _build_plans(root)
    if not claude_plan.ok or not codex_plan.ok or not cursor_plan.ok or not grok_plan.ok:
        _print_diagnostics("claude-code", claude_plan)
        _print_diagnostics("codex", codex_plan)
        _print_diagnostics("cursor", cursor_plan)
        _print_diagnostics("grok", grok_plan)
        return 1

    alias_plan = _build_alias_plan(root)
    if args.check:
        return cmd_check(root, claude_plan, codex_plan, cursor_plan, grok_plan, reference_bytes,
                          model_roles_bytes, alias_plan, routing_bytes)
    return cmd_write(root, claude_plan, codex_plan, cursor_plan, grok_plan, reference_bytes,
                     model_roles_bytes, alias_plan, repair_owned=args.repair_owned)


if __name__ == "__main__":
    raise SystemExit(main())
