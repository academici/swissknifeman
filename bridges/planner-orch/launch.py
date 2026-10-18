"""Launch command line of an orch role on a provider (``launch``).

Reads the role's entry from the partner's launch catalog (``orch.py launch``, as a process), resolves its model
class to a model through planner's provider mapping (``class_selectors`` in ``configs/command-routing.json``), and
prints ``{"argv", "transport", "timeout_s", "model", "model_class"}``. Models never come from the catalog.

Run as ``plan.py bridge planner-orch launch <role> <provider> [--model M] [--effort E] [--cwd DIR] [--routing FILE]``.
``--model`` pins the exact model of an owner selector (``reviewer grok/grok-4.7``) instead of the class mapping.
Nothing is started. Errors are ``CODE: message`` on stderr with exit 1.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from partners import require_orch, require_planner_root


def default_routing() -> Path:
    return require_planner_root() / "configs" / "command-routing.json"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plan.py bridge planner-orch launch", description=__doc__.splitlines()[0])
    p.add_argument("role")
    p.add_argument("provider")
    p.add_argument("--model", help="exact model of an owner selector; replaces the class mapping")
    p.add_argument("--effort", help="override the catalog effort")
    p.add_argument("--cwd", default=".")
    p.add_argument("--routing", type=Path, default=None,
                   help="routing file holding the provider mappings (default: the planner's command-routing.json)")
    return p


class LaunchRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")


def _orch(*args: str) -> dict:
    root = require_orch()
    done = subprocess.run([sys.executable, str(root / "scripts" / "orch.py"), "launch", *args],  # no-timeout: the launch is the agent run itself
                          capture_output=True, text=True, encoding="utf-8", check=False)
    if done.returncode:
        raise LaunchRefused(*(done.stderr.strip().split(": ", 1) if ": " in done.stderr else ("LAUNCH_FAILED", done.stderr.strip())))
    return json.loads(done.stdout)


def resolve_model(mapping: dict | None, model_class: str) -> str | None:
    """First ``class_selectors[model_class]`` model of a provider mapping; None when it has none."""
    selectors = (mapping or {}).get("class_selectors", {}).get(model_class)
    return selectors[0] if selectors else None


def resolve_effort(mapping: dict | None, effort: str) -> str:
    selectors = (mapping or {}).get("effort_selectors", {}).get(effort)
    return selectors[0] if selectors else effort


def build(role: str, provider: str, *, effort: str | None, cwd: str, routing: Path, model: str | None = None) -> dict:
    entry = _orch("show", role, provider)
    try:
        mapping = json.loads(routing.read_text(encoding="utf-8")).get("mappings", {}).get(provider)
    except (OSError, ValueError) as error:
        raise LaunchRefused("ROUTING_UNREADABLE", f"{routing}: {error}") from error
    if model is not None and (not model or entry["model_set"] != "supported"):
        raise LaunchRefused("LAUNCH_INVALID", f"role {role!r} on {provider!r} takes no model argument" if model
                            else "--model needs a model id")
    model = model or resolve_model(mapping, entry["model_class"])
    if entry["model_set"] == "supported" and model is None:
        raise LaunchRefused("LAUNCH_MODEL_UNRESOLVED",
                            f"provider {provider!r} has no model for class {entry['model_class']!r} in {routing.name}")
    args = ["argv", role, provider, "--cwd", cwd, "--effort", resolve_effort(mapping, effort or entry["effort"])]
    if model and entry["model_set"] == "supported":
        args += ["--model", model]
    built = _orch(*args)
    return {**built, "model": model, "model_class": entry["model_class"]}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        out = build(args.role, args.provider, effort=args.effort, cwd=args.cwd, routing=args.routing or default_routing(),
                    model=args.model)
    except LaunchRefused as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
