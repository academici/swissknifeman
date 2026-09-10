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
    installed = subparsers.add_parser("installed", help="Сверить выбранную установленную проекцию")
    installed.add_argument("--source", required=True, type=Path)
    installed.add_argument("--installed", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "installed":
            def inventory(root):
                return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in root.rglob("*") if path.is_file()
                        and not {"__pycache__", "node_modules", ".git", ".vitepress"} & set(path.parts)
                        and path.suffix not in {".pyc", ".pyo"}}
            if not args.source.is_dir() or not args.installed.is_dir():
                raise ValueError("source/installed не содержит выбранный пакет")
            sources, targets = inventory(args.source), inventory(args.installed)
            if not sources:
                raise ValueError("пустой исходный пакет")
            rows = [{"path": path, "source_sha256": sources.get(path),
                     "installed_sha256": targets.get(path)}
                    for path in sorted(sources.keys() | targets.keys())]
            manifest = args.installed / ".codex-plugin/plugin.json"
            version = json.loads(manifest.read_text()).get("version") if manifest.is_file() else None
            mismatches = [row for row in rows if row["source_sha256"] != row["installed_sha256"]]
            print(json.dumps({"source": str(args.source.resolve()),
                              "installed": str(args.installed.resolve()), "version": version,
                              "files": len(rows), "mismatches": mismatches,
                              "source_digest": hashlib.sha256(json.dumps(
                                  [(r["path"], r["source_sha256"]) for r in rows]).encode()).hexdigest(),
                              "installed_digest": hashlib.sha256(json.dumps(
                                  [(r["path"], r["installed_sha256"]) for r in rows]).encode()).hexdigest()},
                             ensure_ascii=False))
            return 1 if mismatches else 0
        elif args.command == "prepare":
            from task import plan_context, plan_bundle, plan_evidence, plan_lifecycle, validation_admission, plan_item_state
            risks = set(args.risk)
            if "none" in risks and len(risks) != 1:
                raise ValueError("none несовместим с другими рисками")
            selection = plan_lifecycle.select(plan_lifecycle.LifecycleInput(
                risks=frozenset() if risks == {"none"} else frozenset(risks)))
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
                              "advice": asdict(selection)}, ensure_ascii=False))
        else:
            print(session_context.current_json() if args.json else session_context.current_id())
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
