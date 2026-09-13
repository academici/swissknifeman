#!/usr/bin/env python3
"""Emit the current normalized plan-session identity."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import hashlib
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "lib"))

from task import session_context  # noqa: E402

def migrated_command_skill(source, relative_path):
    # Current session discovery also runs in Task-only caches; core is needed only
    # by this verifier, which receives the source checkout explicitly.
    repository = Path(source).parent.parent
    if (repository / "core").is_dir():
        sys.path.insert(0, str(repository))
    from core.provider.runtime import codex_migrated_command_skill
    return codex_migrated_command_skill(source, relative_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Показать provider-neutral session context")
    subparsers = parser.add_subparsers(dest="command", required=True)
    current = subparsers.add_parser("current")
    output = current.add_mutually_exclusive_group(required=True)
    output.add_argument("--json", action="store_true")
    output.add_argument("--id", action="store_true")
    prepare = subparsers.add_parser("prepare", help="Read-only snapshot, не разрешение на запись")
    prepare.add_argument("--plan-dir", required=True, type=Path)
    prepare.add_argument("--item", required=True)
    prepare.add_argument("--risk", action="append", required=True,
                         help="Имя риска; none только после оценки воздействия")
    start = subparsers.add_parser("start", help="Durable старт или resume до product write")
    start.add_argument("--plan-dir", required=True, type=Path)
    start.add_argument("--item", required=True)
    start.add_argument("--command", dest="execution_command", required=True,
                       choices=("plan-exec", "plan-run"))
    start.add_argument("--actor", required=True)
    start.add_argument("--session-id")
    start.add_argument("--contract", required=True, type=Path)
    start.add_argument("--batch-receipt", type=Path)
    installed = subparsers.add_parser("installed", help="Сверить выбранную установленную проекцию")
    installed.add_argument("--source", required=True, type=Path)
    installed.add_argument("--installed", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "installed":
            def inventory(root):
                if root.is_symlink():
                    raise ValueError(f"symlink package root: {root}")
                result = {}
                for path in root.rglob("*"):
                    relative = path.relative_to(root)
                    if {"__pycache__", "node_modules", ".git", ".vitepress"} & set(relative.parts):
                        continue
                    if path.is_symlink():
                        raise ValueError(f"symlink package member: {relative.as_posix()}")
                    if path.is_file() and path.suffix not in {".pyc", ".pyo"}:
                        result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
                return result
            if not args.source.is_dir() or not args.installed.is_dir():
                raise ValueError("source/installed не содержит выбранный пакет")
            sources, targets = inventory(args.source), inventory(args.installed)
            if not sources:
                raise ValueError("пустой исходный пакет")
            provider_generated = []
            for path in sorted(targets.keys() - sources.keys()):
                expected = migrated_command_skill(args.source, path)
                target = args.installed / path
                if (expected is not None and not target.is_symlink()
                        and not any(parent.is_symlink() for parent in target.parents
                                    if parent != args.installed.parent)
                        and hashlib.sha256(expected).hexdigest() == targets[path]):
                    provider_generated.append({"path": path, "sha256": targets.pop(path),
                                               "owner": "codex-command-migration"})
            rows = [{"path": path, "source_sha256": sources.get(path),
                     "installed_sha256": targets.get(path)}
                    for path in sorted(sources.keys() | targets.keys())]
            manifest = args.installed / ".codex-plugin/plugin.json"
            version = json.loads(manifest.read_text()).get("version") if manifest.is_file() else None
            mismatches = [row for row in rows if row["source_sha256"] != row["installed_sha256"]]
            print(json.dumps({"source": str(args.source.resolve()),
                              "installed": str(args.installed.resolve()), "version": version,
                              "files": len(rows), "mismatches": mismatches,
                              "provider_generated": provider_generated,
                              "source_digest": hashlib.sha256(json.dumps(
                                  [(r["path"], r["source_sha256"]) for r in rows]).encode()).hexdigest(),
                              "installed_digest": hashlib.sha256(json.dumps(
                                  [(r["path"], r["installed_sha256"]) for r in rows]).encode()).hexdigest()},
                             ensure_ascii=False))
            return 1 if mismatches else 0
        elif args.command == "start":
            from task import plan_recovery
            contract = json.loads(args.contract.read_text(encoding="utf-8"))
            receipt = (json.loads(args.batch_receipt.read_text(encoding="utf-8"))
                       if args.batch_receipt else None)
            verdict = plan_recovery.start(
                args.plan_dir, args.item, command=args.execution_command,
                actor=args.actor, session_id=args.session_id or session_context.current_id(),
                contract=contract, batch_receipt=receipt)
            print(json.dumps(verdict, ensure_ascii=False))
        elif args.command == "prepare":
            from task import plan_context, plan_bundle, plan_evidence, plan_lifecycle, validation_admission, plan_item_state
            risks = set(args.risk)
            if "none" in risks and len(risks) != 1:
                raise ValueError("none несовместим с другими рисками")
            selection = plan_lifecycle.select(plan_lifecycle.LifecycleInput(
                risks=frozenset() if risks == {"none"} else frozenset(risks)))
            from task import plan_recovery
            recovery = plan_recovery.validate_request(args.plan_dir, args.item)
            plan_item_state.build_states(args.plan_dir, item_id=args.item, check=True)
            snapshot = plan_context.capture(args.plan_dir, args.item)
            plan_bundle.build(args.plan_dir, args.item, check=True)
            readiness = plan_bundle.producer_readiness(args.plan_dir, args.item)
            graph = plan_evidence.compile_graph(args.plan_dir, args.item)
            admission = validation_admission.inspect(args.plan_dir, args.item)
            plan_item_state.build_states(args.plan_dir, item_id=args.item, check=True)
            snapshot.assert_live_integrity()
            print(json.dumps({"snapshot_sha256": snapshot.snapshot_sha256,
                              "evidence_graph": graph, "producer_readiness": readiness,
                              "validation": admission,
                              "recovery": recovery,
                              "advice": asdict(selection)}, ensure_ascii=False))
        else:
            print(session_context.current_json() if args.json else session_context.current_id())
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
