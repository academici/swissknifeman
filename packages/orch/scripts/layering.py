#!/usr/bin/env python3
"""Measure conductor facade coupling without importing the conductor.

The baseline is a test fixture, independent of the installed package and providers.
Only gate totals ratchet; moving calls between layers is informational.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ("domain", "infrastructure", "policies", "stages", "application")
TARGETS = {
    "P5.2": {"self_functions.policies": "== 0", "upward_self_calls.policies->stages": "absent",
             "private_facade_access_total": "== 0"},
    "P5.3": {"upward_self_calls.infrastructure->*": "absent", "infrastructure/roles.py": "<= 300 lines"},
    "P5.4": {"oversized_modules.prompts.py": "absent", "oversized_modules.context/*": "absent",
             "oversized_modules.prompts/*": "absent"},
}
COUNT = {"type": "integer", "minimum": 0}
COUNTS = {"type": "object", "additionalProperties": COUNT}
METRIC_PROPERTIES = {
    **dict.fromkeys(("bindings", "staticmethod_bindings", "largest_self_scc", "upward_total",
                     "private_facade_access_total"), COUNT),
    **dict.fromkeys(("upward_self_calls", "facade_calls", "port_calls", "private_facade_access",
                     "oversized_modules", "unlayered_self_functions"), COUNTS),
    "self_functions": {"type": "object", "properties": dict.fromkeys(LAYERS, COUNT),
                       "required": list(LAYERS), "additionalProperties": False},
    "upward_sites": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
}
METRICS_SCHEMA = {"$id": "urn:swissknifeman:orch:layering-metrics:v1", "type": "object",
                  "properties": METRIC_PROPERTIES, "required": list(METRIC_PROPERTIES), "additionalProperties": False}
BASELINE_SCHEMA = {
    "$id": "urn:swissknifeman:orch:layering-baseline:v1", "type": "object",
    "properties": {**{key: value for key, value in METRIC_PROPERTIES.items() if key != "upward_sites"},
                   "$schema": {"type": "string", "enum": ["urn:swissknifeman:orch:layering-baseline:v1"]},
                   "version": {"type": "integer", "enum": [1]}, "measured_at": {"type": "string"},
                   "targets": {"type": "object", "properties": {
                       item: {"type": "object", "properties": {metric: {"type": "string", "enum": [rule]}
                                                               for metric, rule in rules.items()},
                              "required": list(rules), "additionalProperties": False}
                       for item, rules in TARGETS.items()},
                       "required": list(TARGETS), "additionalProperties": False}},
    "required": ["version", "measured_at", "bindings", "staticmethod_bindings", "self_functions",
                 "upward_self_calls", "largest_self_scc", "private_facade_access", "oversized_modules", "targets"],
    "additionalProperties": False,
}


def validate(document, schema: dict, path: str = "$") -> None:
    """Validate the embedded JSON Schemas' closed subset using only the standard library."""
    types = {"integer": int, "object": dict, "array": list, "string": str}
    if type(document) is not types[schema["type"]]:
        raise ValueError(f"{path}: expected {schema['type']}")
    if "enum" in schema and document not in schema["enum"]:
        raise ValueError(f"{path}: expected one of {schema['enum']}")
    if "minimum" in schema and document < schema["minimum"]:
        raise ValueError(f"{path}: expected >= {schema['minimum']}")
    if isinstance(document, dict):
        missing = set(schema.get("required", ())) - document.keys()
        if missing:
            raise ValueError(f"{path}: missing {', '.join(sorted(missing))}")
        for key, value in document.items():
            child = schema.get("properties", {}).get(key, schema.get("additionalProperties", False))
            if child is False:
                raise ValueError(f"{path}.{key}: unexpected property")
            validate(value, child, f"{path}.{key}")
    elif isinstance(document, list):
        for index, value in enumerate(document):
            validate(value, schema["items"], f"{path}[{index}]")


def largest_scc(graph: dict[str, set[str]]) -> int:
    """Iterative Tarjan traversal: singleton components are not coupling cycles."""
    nodes = set(graph).union(*(graph.values())) if graph else set()
    indices, low = {}, {}
    active, members = [], set()
    largest = 0
    for node in sorted(nodes):
        if node in indices:
            continue
        indices[node] = low[node] = len(indices)
        active.append(node)
        members.add(node)
        stack = [(node, iter(sorted(graph.get(node, ()))))]
        while stack:
            current, children = stack[-1]
            child = next(children, None)
            if child is not None:
                if child not in indices:
                    indices[child] = low[child] = len(indices)
                    active.append(child)
                    members.add(child)
                    stack.append((child, iter(sorted(graph.get(child, ())))))
                elif child in members:
                    low[current] = min(low[current], indices[child])
                continue
            stack.pop()
            if stack:
                parent = stack[-1][0]
                low[parent] = min(low[parent], low[current])
            if low[current] == indices[current]:
                size = 0
                while True:
                    member = active.pop()
                    members.remove(member)
                    size += 1
                    if member == current:
                        break
                if size > 1 or current in graph.get(current, ()):
                    largest = max(largest, size)
    return largest


def metrics(conductor_dir: Path) -> dict:
    """Count only module-level self functions, never methods of module-owned classes."""
    conductor_dir = Path(conductor_dir)
    sources = {path.relative_to(conductor_dir).as_posix(): path.read_text(encoding="utf-8")
               for path in sorted(conductor_dir.rglob("*.py"))}
    trees = {name: ast.parse(source, filename=name) for name, source in sources.items()}
    aliases = {}
    for node in trees["engine.py"].body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        prefix = "orch.conductor."
        if not node.module.startswith(prefix):
            continue
        module = node.module[len(prefix):]
        for alias in node.names:
            owner = f"{module}.{alias.name}" if module in LAYERS else module
            aliases[alias.asname or alias.name] = owner
    facade = next(node for node in trees["engine.py"].body
                  if isinstance(node, ast.ClassDef) and node.name == "Conductor")
    own = {node.name for node in facade.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    bindings, statics = {}, 0
    for node in facade.body:
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        static = (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                  and value.func.id == "staticmethod" and len(value.args) == 1)
        if static:
            value = value.args[0]
        if not isinstance(value, ast.Attribute) or not isinstance(value.value, ast.Name):
            continue
        owner = aliases.get(value.value.id)
        if owner is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                bindings[target.id] = owner
                statics += int(static)
    result = {"bindings": len(bindings), "staticmethod_bindings": statics,
              "self_functions": dict.fromkeys(LAYERS, 0), "upward_self_calls": {}, "upward_sites": {},
              "facade_calls": {}, "port_calls": {}, "private_facade_access": {}, "oversized_modules": {},
              "unlayered_self_functions": {}}
    graph = {}
    for name, tree in trees.items():
        module = name.removesuffix(".py").replace("/", ".")
        layer = module.split(".")[0]
        lines = len(sources[name].splitlines())
        if lines > 600:
            result["oversized_modules"][name] = lines
        if "/" not in name and name != "engine.py":
            private = sum(isinstance(node, ast.Attribute) and node.attr.startswith("_")
                          and node.attr in bindings
                          and not (isinstance(node.value, ast.Name) and node.value.id == "self")
                          for node in ast.walk(tree))
            if private:
                result["private_facade_access"][name] = private
        for function in tree.body:
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = function.args.posonlyargs + function.args.args
            if not args or args[0].arg != "self":
                continue
            if layer not in LAYERS:
                result["unlayered_self_functions"][name] = result["unlayered_self_functions"].get(name, 0) + 1
                continue
            result["self_functions"][layer] += 1
            for node in ast.walk(function):
                if not isinstance(node, ast.Attribute):
                    continue
                if (isinstance(node.value, ast.Attribute) and node.value.attr in ("role_ports", "stage_ports")
                        and isinstance(node.value.value, ast.Name) and node.value.value.id == "self"):
                    key = f"{layer}.{node.value.attr}.{node.attr}"
                    result["port_calls"][key] = result["port_calls"].get(key, 0) + 1
                if not isinstance(node.value, ast.Name) or node.value.id != "self":
                    continue
                if node.attr in own:
                    result["facade_calls"][layer] = result["facade_calls"].get(layer, 0) + 1
                owner = bindings.get(node.attr)
                if owner is None or owner.split(".")[0] not in LAYERS:
                    continue
                graph.setdefault(module, set()).add(owner)
                destination = owner.split(".")[0]
                if LAYERS.index(destination) > LAYERS.index(layer):
                    key = f"{layer}->{destination}"
                    result["upward_self_calls"][key] = result["upward_self_calls"].get(key, 0) + 1
                    result["upward_sites"].setdefault(key, []).append(
                        f"{module}:{node.lineno} self.{node.attr} -> {owner}")
    result["largest_self_scc"] = largest_scc(graph)
    result["upward_total"] = sum(result["upward_self_calls"].values())
    result["private_facade_access_total"] = sum(result["private_facade_access"].values())
    validate(result, METRICS_SCHEMA)
    return result


def gates(document: dict) -> dict:
    return {"upward_total": {"total": sum(document["upward_self_calls"].values())},
            "self_functions": {layer: document["self_functions"][layer] for layer in ("domain", "policies")},
            "private_facade_access_total": {"total": sum(document["private_facade_access"].values())},
            "largest_self_scc": {"size": document["largest_self_scc"]},
            "oversized_modules": document["oversized_modules"],
            "unlayered_self_functions": document.get("unlayered_self_functions", {})}


def differences(now: dict, baseline: dict, *, stale: bool) -> bool:
    failed = False
    old_gates = gates(baseline)
    for metric, values in gates(now).items():
        previous = old_gates[metric]
        for key in sorted(values.keys() | previous.keys()):
            actual, old = values.get(key, 0), previous.get(key, 0)
            if (metric == "self_functions" and key == "domain") or metric == "unlayered_self_functions":
                old = 0  # invariants cannot be waived by editing the baseline
            if actual > old:
                sites = now["upward_sites"]
                locations = [site for direction in sorted(sites) for site in sites[direction]][:5]
                print(f"LAYERING_REGRESSION: {metric} {key}: {actual} > {old}; sites: {', '.join(locations)}")
                failed = True
            elif stale and actual < old:
                print(f"LAYERING_BASELINE_STALE: {metric} {key}: {actual} < {old}; run layering.py --update")
                failed = True
    informative = {"bindings": None, "staticmethod_bindings": None,
                   "self_functions": ("infrastructure", "stages", "application"),
                   "upward_self_calls": None, "facade_calls": None, "port_calls": None}
    for metric, keys in informative.items():
        actual, old = now.get(metric, {}), baseline.get(metric, {})
        if isinstance(actual, dict):
            for key in keys or sorted(actual.keys() | old.keys()):
                if actual.get(key, 0) != old.get(key, 0):
                    print(f"layering: info {metric} {key}: {old.get(key, 0)} -> {actual.get(key, 0)}")
        elif actual != old:
            print(f"layering: info {metric} total: {old} -> {actual}")
    return failed


def target_failures(item: str, rules: dict, now: dict, root: Path) -> bool:
    failed = False
    for metric, rule in rules.items():
        if rule == "<= 300 lines":
            path = root / metric
            actual = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
            valid = actual <= 300
        elif rule == "absent":
            collection, key = metric.split(".", 1)
            actual = {name: value for name, value in now[collection].items()
                      if name.startswith(key[:-1])} if key.endswith("*") else now[collection].get(key, 0)
            valid = not actual
        else:
            actual = now
            for part in metric.split("."):
                actual = actual[part]
            valid = actual == 0
        if not valid:
            print(f"LAYERING_TARGET: {item} {metric}: {actual} (want {rule})")
            failed = True
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--json", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT / "lib/orch/conductor")
    parser.add_argument("--baseline", type=Path, default=ROOT / "tests/golden/layering-baseline.json")
    parser.add_argument("--target", choices=tuple(TARGETS))
    args = parser.parse_args()
    if args.target and not args.check:
        parser.error("--target requires --check")
    now = metrics(args.root)
    if args.json:
        print(json.dumps(now, sort_keys=True, indent=1))
        return 0
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else None
        if baseline is not None:
            validate(baseline, BASELINE_SCHEMA)
    except (OSError, ValueError) as error:
        parser.error(f"invalid layering baseline: {error}")
    if baseline is None and not args.update:
        parser.error("baseline is missing; run layering.py --update")
    failed = differences(now, baseline if baseline is not None else now, stale=args.check)
    if args.target:
        failed = target_failures(args.target, baseline["targets"][args.target], now, args.root) or failed
    if failed:
        return 1
    if args.update:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
        document = {key: value for key, value in now.items() if key != "upward_sites"}
        document.update({"$schema": BASELINE_SCHEMA["$id"]})
        document.update(version=1, measured_at=head.stdout.strip() or "unknown",
                        targets=baseline.get("targets", TARGETS) if baseline else TARGETS)
        validate(document, BASELINE_SCHEMA)
        args.baseline.write_text(json.dumps(document, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print("layering: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
