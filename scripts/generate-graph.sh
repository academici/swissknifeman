#!/usr/bin/env bash
# Generate docs/guide/graph.md (Mermaid dependency graph) from skills.json.
# Reads requires/produces_for fields (registry v5+); run after
# 'swissknifeman registry' (the registry command calls this automatically).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import json, sys
from pathlib import Path

root = Path(sys.argv[1])
registry = json.loads((root / "skills.json").read_text(encoding="utf-8"))
skills = registry["skills"]

by_name = {s["name"]: s for s in skills}

# Edges: requires (solid), produces_for (dotted). A mirrored pair
# (A requires B + B produces_for A) is drawn once, as the requires edge.
requires_edges = set()
produces_edges = set()
for s in skills:
    for dep in s.get("requires", []):
        if dep in by_name:
            requires_edges.add((s["name"], dep))
for s in skills:
    for dst in s.get("produces_for", []):
        if dst in by_name and (dst, s["name"]) not in requires_edges:
            produces_edges.add((s["name"], dst))

connected = {n for e in requires_edges | produces_edges for n in e}

# Group connected nodes by bucket for subgraphs
buckets = {}
for name in sorted(connected):
    buckets.setdefault(by_name[name]["bucket"], []).append(name)

isolated = {}
for s in skills:
    if s["name"] not in connected:
        isolated.setdefault(s["bucket"], []).append(s["name"])


def node_id(name):
    return name.replace("-", "_")


lines = [
    "# Граф зависимостей скиллов",
    "",
    "> Сгенерировано `scripts/generate-graph.sh` из `skills.json` — не редактировать вручную.",
    "> Пересборка: `swissknifeman registry`.",
    "",
    "Сплошная стрелка `A --> B` — `A` требует `B` (`requires`): `swissknifeman vendor` дотянет `B`",
    "при установке `A`. Пунктирная `A -.-> B` — результат `A` служит входом для `B`",
    "(`produces_for`). Показаны только скиллы, участвующие в графе; изолированные —",
    "в таблице ниже.",
    "",
    "```mermaid",
    "flowchart LR",
]

for bucket in sorted(buckets):
    lines.append(f"  subgraph {node_id(bucket)}[\"{bucket}\"]")
    for name in buckets[bucket]:
        lines.append(f"    {node_id(name)}[\"{name}\"]")
    lines.append("  end")

for src, dst in sorted(requires_edges):
    lines.append(f"  {node_id(src)} -->|requires| {node_id(dst)}")
for src, dst in sorted(produces_edges):
    lines.append(f"  {node_id(src)} -.->|feeds| {node_id(dst)}")

lines += [
    "```",
    "",
    f"**В графе:** {len(connected)} скиллов, {len(requires_edges)} рёбер requires, "
    f"{len(produces_edges)} рёбер produces_for.",
    "",
    f"## Изолированные скиллы ({sum(len(v) for v in isolated.values())})",
    "",
    "Скиллы без связей `requires`/`produces_for` — самодостаточны.",
    "",
    "| Бакет | Скиллы |",
    "|---|---|",
]
for bucket in sorted(isolated):
    names = ", ".join(f"`{n}`" for n in sorted(isolated[bucket]))
    lines.append(f"| {bucket} | {names} |")
lines.append("")

out = root / "docs/guide/graph.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Updated {out.relative_to(root)}: {len(connected)} nodes, "
      f"{len(requires_edges) + len(produces_edges)} edges")
PY
