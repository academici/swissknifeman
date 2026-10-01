#!/usr/bin/env bash
# DEPRECATED (2026-07, audit R-2): logic moved to lib/skiller/registry.py
# (render_graph/write_graph) — cmd_registry no longer calls this script, but
# registry.check_drift now sees graph.md (couldn't do it before - heredoc did not have
# python-functions to compare in-memory). Left in the tree (rm blocked
# environment policy) — safe to remove: git rm scripts/generate-graph.sh.
#
# Generate packages/skiller/docs/guide/graph.md (Mermaid dependency graph) from
# skills.json. Reads requires/produces_for fields (registry v5+); run after
# 'skiller registry' (the registry command calls this automatically).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
import json, sys
from pathlib import Path

root = Path(sys.argv[1])  # package root (skills.json here)
registry = json.loads((root / "skills.json").read_text(encoding="utf-8"))
skills = registry["skills"]

# Docks skiller live in the package itself (packages/skiller/docs/guide) — looking up
# closest directory with docs/guide (is the package itself; fallback — root).
def _docs_root(p):
    for cand in (p, *p.parents):
        if (cand / "docs" / "guide").is_dir():
            return cand
    return p
docs_root = _docs_root(root)

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
    "# Skill dependency graph",
    "",
    "> Generated `scripts/generate-graph.sh` from `skills.json` — cannot be edited manually.",
    "> Reassembly: `skiller registry`.",
    "",
    "Solid arrow `A --> B` — `A` requires `B` (`requires`): `skiller vendor` will last `B`",
    "during installation `A`. Dotted `A -.-> B` — result `A` serves as an input for `B`",
    "(`produces_for`). Only skills participating in the graph are shown; isolated -",
    "in the table below.",
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
    f"**In the column:** {len(connected)} skills, {len(requires_edges)} ribs requires, "
    f"{len(produces_edges)} ribs produces_for.",
    "",
    f"## Isolated skills ({sum(len(v) for v in isolated.values())})",
    "",
    "Skills without connections `requires`/`produces_for` — are self-sufficient.",
    "",
    "| Bucket | Skills |",
    "|---|---|",
]
for bucket in sorted(isolated):
    names = ", ".join(f"`{n}`" for n in sorted(isolated[bucket]))
    lines.append(f"| {bucket} | {names} |")
lines.append("")

out = docs_root / "docs/guide/graph.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Updated {out.relative_to(docs_root)}: {len(connected)} nodes, "
      f"{len(requires_edges) + len(produces_edges)} edges")
PY
