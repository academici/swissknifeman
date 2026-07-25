#!/usr/bin/env python3
"""Тонкий stdlib CLI-фронт над `command_render.py` planning/apply API (P1.3).

Никакой собственной рендер-логики: только загрузка канонического каталога
(`command_catalog.build_command_catalog`), построение обоих provider-планов
(`plan_claude_command_render`/`plan_codex_command_render`) и их read-only/write
применение (`apply_claude_command_plan`/`plan_codex_command_apply` +
`apply_codex_command_plan`) под явным `--root`.

    python3 packages/task/scripts/render-provider-commands.py --check --root .
    python3 packages/task/scripts/render-provider-commands.py --write --repair-owned --root .
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent       # packages/task
_MONOREPO_ROOT = _PKG_ROOT.parent.parent                 # корень монорепо
sys.path.insert(0, str(_PKG_ROOT / "lib"))
if (_MONOREPO_ROOT / "core").is_dir():
    sys.path.insert(0, str(_MONOREPO_ROOT))

from task.command_catalog import build_command_catalog  # noqa: E402
from task.command_render import (  # noqa: E402
    PROVIDER_LOCK_PATH, apply_claude_command_plan, apply_codex_command_plan,
    mapping_from_catalog, plan_claude_command_render, plan_codex_command_apply,
    plan_codex_command_render,
)


def _build_plans(root: Path):
    command_root = root / "packages/task/commands"
    routing_path = root / "packages/task/configs/command-routing.json"
    catalog = build_command_catalog(command_root, routing_path)
    mappings = {provider_id: mapping_from_catalog(catalog, provider_id)
                for provider_id in ("claude-code", "codex")}
    support = {provider_id: dict(mapping.capability_bindings)
               for provider_id, mapping in mappings.items()}
    plugin_bytes = (root / "packages/task/.claude-plugin/plugin.json").read_bytes()
    claude_plan = plan_claude_command_render(
        catalog, mappings["claude-code"], support["claude-code"], plugin_bytes=plugin_bytes)
    codex_plan = plan_codex_command_render(catalog, mappings["codex"], support["codex"])
    return claude_plan, codex_plan


def _print_diagnostics(label: str, plan) -> None:
    for diagnostic in plan.diagnostics:
        print(f"{label}: {diagnostic.severity} {diagnostic.code} "
              f"{diagnostic.command_id} {diagnostic.path} {diagnostic.message}",
              file=sys.stderr)


def cmd_check(root: Path, claude_plan, codex_plan) -> int:
    claude_drift = apply_claude_command_plan(root, claude_plan, check=True)
    lock_path = root / PROVIDER_LOCK_PATH
    lock_bytes = lock_path.read_bytes() if lock_path.is_file() else None
    codex_artifact_plan = plan_codex_command_apply(root, codex_plan, lock_bytes=lock_bytes)
    codex_drift = tuple(action for action in codex_artifact_plan.actions
                        if action.action.value != "noop")
    if not claude_drift and not codex_drift:
        print("render-provider-commands: check OK (no-op)")
        return 0
    for path in claude_drift:
        print(f"drift: claude-code {path}", file=sys.stderr)
    for action in codex_drift:
        print(f"drift: codex {action.artifact_id} {action.action.value}", file=sys.stderr)
    return 1


def cmd_write(root: Path, claude_plan, codex_plan, *, repair_owned: bool) -> int:
    apply_claude_command_plan(root, claude_plan, check=False)
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
    written = len([action for action in codex_artifact_plan.actions
                  if action.action.value != "noop"])
    print(f"render-provider-commands: wrote {len(claude_plan.artifacts)} Claude artifact(s), "
          f"{written} Codex artifact(s) changed")
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

    claude_plan, codex_plan = _build_plans(root)
    if not claude_plan.ok or not codex_plan.ok:
        _print_diagnostics("claude-code", claude_plan)
        _print_diagnostics("codex", codex_plan)
        return 1

    if args.check:
        return cmd_check(root, claude_plan, codex_plan)
    return cmd_write(root, claude_plan, codex_plan, repair_owned=args.repair_owned)


if __name__ == "__main__":
    raise SystemExit(main())
