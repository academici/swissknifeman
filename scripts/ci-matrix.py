#!/usr/bin/env python3
"""ci-matrix.py — the one source of the CI steps of modules and bridges (the same locally and in CI).

Usage:
  ci-matrix.py list [--json] [--step S] [--python V,V]    units of the hub as a matrix {"include": [{unit, kind, tool}]}
  ci-matrix.py steps UNIT [--json]                        the steps of one unit
  ci-matrix.py run (--unit U [--step S]... [--skip S]... | --all [--include-tools]) [--base-ref REF] [--repeat-tests] [--jobs N]
                                                          run steps; one line `ok|fail|skip <unit> <step> <seconds>` each;
                                                          after a green `test` step `validate` runs with
                                                          SKM_VALIDATE_SKIP_TESTS=1 (validate.sh skips its test run);
                                                          --all runs 4 units at the same time (--jobs N, SKM_CI_MATRIX_JOBS)
  ci-matrix.py --check [--strict] [--legacy FILE]         structural check of the workflow against the matrix
Common option: --root DIR (hub root; default: the checkout of this script).

Units are read from packages/*/unit.json and bridges/*/unit.json; `tool` marks the modules named by
configs/ecosystem-units.json standalone.tools (their failure never blocks: the workflow sets continue-on-error).
Steps of a module: lint, test, validate, standalone, cli-smoke, contracts, schema-compat, secrets; of a bridge: test,
contracts. Every step runs with a throwaway HOME and SKM_HOME (lint keeps the real one for the pipx cache).
Exit: 0 ok, 1 a step failed or the check found a problem, 2 usage.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/modules.yml"
TEST_PYTHONS = "3.11,3.13,3.14"
# validate.sh of a module skips its test run when this is set: the `test` step has just run them (the standalone step
# does the same inside its copy, see ecosystem-units.py).
SKIP_TESTS_ENV = "SKM_VALIDATE_SKIP_TESTS"
STEP_ORDER = ("lint", "test", "validate", "standalone", "cli-smoke", "contracts", "schema-compat", "secrets")
# Extra arguments of dev.validate in CI (the plan fleet is checked besides the module itself). Data until unit.json
# gets a field for it.
CI_VALIDATE_ARGS = {"planner": ["--fleet"]}
# Environment variable by which a bridge finds each partner (the layout of the hub: packages/<id>), as test-bridges.sh.
PARTNER_ENV = {
    "planner": ("PLANNER_ROOT",), "orch": ("SKM_ORCH_ROOT",), "skiller": ("SKM_SKILLER_ROOT",),
    "harness": ("SKM_HARNESS_ROOT",), "aicore": ("AICORE_ROOT",),
    "gui": ("SKM_GUI_ROOT",), "workspace": ("SKM_WORKSPACE_MODULE_ROOT",),
}
# The commands of the workflows test.yml and validate.yml that modules.yml replaced; --check proves each is covered.
LEGACY_COMMANDS = [
    "bash packages/skiller/scripts/test.sh -v", "bash packages/harness/scripts/test.sh -v",
    "bash packages/orch/scripts/test.sh -v", "bash packages/aicore/scripts/test.sh -v",
    "python3 scripts/ecosystem-units.py standalone --baseline",
    "python3 scripts/ecosystem-units.py check --strict",
    "bash packages/planner/scripts/validate.sh",
    "bash scripts/lint.sh",
    "python3 -m pip install -r packages/maind/requirements-dev.txt",
    "bash packages/maind/scripts/test.sh -v", "bash packages/analyst/scripts/test.sh -v",
    "bash scripts/test-integration.sh --with-tools",
    "bash packages/skiller/scripts/validate.sh", "bash packages/harness/scripts/validate.sh",
    "bash packages/planner/scripts/validate.sh --fleet", "bash packages/orch/scripts/validate.sh",
    "bash packages/maind/scripts/validate.sh",
]
HUB_COMMANDS = {  # legacy command -> text that the workflow must hold
    "python3 scripts/ecosystem-units.py check --strict": "ecosystem-units.py check --strict",
    "python3 -m pip install -r packages/maind/requirements-dev.txt": "requirements-dev.txt",
    "bash scripts/test-integration.sh --with-tools": "test-integration.sh --with-tools",
}


class Unit:
    def __init__(self, path: Path, doc: dict, kind_dir: str):
        self.root = path.parent
        self.doc = doc
        self.id = doc.get("id") or self.root.name
        self.kind = doc.get("kind", "capability")
        self.bridge = kind_dir == "bridges"

    @property
    def provides(self) -> dict:
        return self.doc.get("provides") or {}

    @property
    def dev(self) -> dict:
        return self.doc.get("dev") or {}


def discover(root: Path) -> dict:
    units = {}
    for kind_dir in ("packages", "bridges"):
        for path in sorted((root / kind_dir).glob("*/unit.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise SystemExit(f"CI_MATRIX_UNIT: {path}: {exc}") from None
            unit = Unit(path, doc, kind_dir)
            units.setdefault(unit.id, unit)
    return units


def tools(root: Path) -> set:
    try:
        config = json.loads((root / "configs/ecosystem-units.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set((config.get("standalone") or {}).get("tools") or ())


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def has_schemas(unit: Unit) -> bool:
    return any((unit.root / "schemas").glob("*/v*/*.schema.json"))


def build_steps(root: Path, unit: Unit) -> list:
    """The ordered steps of a unit: dicts {id, kind: argv|internal, argv, cwd, env, text}."""
    base = rel(root, unit.root)
    out = []
    lint_paths = [f"{base}/{name}" for name in ("lib", "tests") if (unit.root / name).is_dir()]
    if lint_paths and not unit.bridge:
        out.append({"id": "lint", "kind": "argv", "argv": ["bash", "scripts/lint.sh", *lint_paths], "cwd": ".", "env": {}})
    test = unit.dev.get("test")
    if test:
        env = {"SKM_TEST_CLASH": "fail"}
        if unit.bridge:
            env.update(partner_env(root))
        out.append({"id": "test", "kind": "argv", "argv": list(test), "cwd": base, "env": env})
    validate = unit.dev.get("validate")
    if validate:
        out.append({"id": "validate", "kind": "argv", "argv": list(validate) + CI_VALIDATE_ARGS.get(unit.id, []),
                    "cwd": base, "env": {}})
    if not unit.bridge:
        out.append({"id": "standalone", "kind": "argv",
                    "argv": ["python3", "scripts/ecosystem-units.py", "standalone", unit.id], "cwd": ".", "env": {}})
    if unit.provides.get("cli") and not unit.bridge:
        out.append({"id": "cli-smoke", "kind": "internal"})
    out.append({"id": "contracts", "kind": "internal"})
    if not unit.bridge and has_schemas(unit):
        out.append({"id": "schema-compat", "kind": "internal"})
    if not unit.bridge:
        out.append({"id": "secrets", "kind": "internal"})
    for step in out:
        step["text"] = " ".join(step["argv"]) if step["kind"] == "argv" else f"(internal) {step['id']}"
        if step["kind"] == "argv" and step["cwd"] != ".":
            step["text"] = f"cd {step['cwd']} && {step['text']}"
    return out


def partner_env(root: Path) -> dict:
    env = {"SKM_AICORE_EVENTS__DELIVERY": "off"}
    for partner, names in PARTNER_ENV.items():
        for name in names:
            env[name] = str(root / "packages" / partner)
    env["PLANNER_PLAN_PY"] = str(root / "packages/planner/scripts/plan.py")
    return env


def matrix(root: Path, step: str = "", pythons: str = "") -> dict:
    tool_ids = tools(root)
    include = []
    for unit in discover(root).values():
        if step and step not in [s["id"] for s in build_steps(root, unit)]:
            continue
        entry = {"unit": unit.id, "kind": unit.kind, "tool": unit.id in tool_ids}
        if pythons:
            for version in pythons.split(","):
                include.append({**entry, "python": version})
        else:
            include.append(entry)
    return {"include": include}


# ---- running ----------------------------------------------------------------------------------------------------

def temp_env(home: Path, extra: dict) -> dict:
    env = dict(os.environ)
    for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        env.pop(name, None)
    env["HOME"] = str(home)
    env["SKM_HOME"] = str(home / "skm")
    env.update(extra)
    return env


def run_argv(root: Path, step: dict, extra_env: dict | None = None) -> tuple:
    home = Path(tempfile.mkdtemp(prefix="skm-ci-"))
    try:
        env = dict(os.environ) if step["id"] == "lint" else temp_env(home, {})
        env.update(step.get("env") or {})
        env.update(extra_env or {})
        proc = subprocess.run(step["argv"], cwd=str(root / step["cwd"]), env=env)
        if step["id"] == "lint" and proc.returncode == 2 and not os.environ.get("CI"):
            return "skip", "lint tool missing (need pipx or ruff at the pinned version)"
        return ("ok" if proc.returncode == 0 else "fail"), f"exit {proc.returncode}"
    except OSError as exc:
        return "fail", str(exc)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def cli_smoke(root: Path, unit: Unit) -> tuple:
    home = Path(tempfile.mkdtemp(prefix="skm-ci-"))
    empty = Path(tempfile.mkdtemp(prefix="skm-ci-cwd-"))
    try:
        env = temp_env(home, {"SKM_AICORE_EVENTS__DELIVERY": "off"})
        if unit.bridge:
            env.update(partner_env(root))
        for name in unit.provides.get("cli") or []:
            path = unit.root / name
            if not path.is_file():
                return "fail", f"{name}: no such file"
            argv = [sys.executable, str(path), "--help"] if path.suffix == ".py" else ["bash", str(path), "--help"]
            proc = subprocess.run(argv, cwd=str(empty), env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            if proc.returncode != 0:
                sys.stderr.write(proc.stdout.decode("utf-8", "replace")[-2000:])
                return "fail", f"{name} --help exit {proc.returncode}"
        return "ok", ""
    except (OSError, subprocess.SubprocessError) as exc:
        return "fail", str(exc)
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(empty, ignore_errors=True)


def contracts(root: Path, unit: Unit) -> tuple:
    declared = unit.provides.get("contracts") or []
    if not declared:
        return "ok", "no contracts"
    foundation_lib = root / "packages/aicore/lib"
    if str(foundation_lib) not in sys.path:
        sys.path.insert(0, str(foundation_lib))
    try:
        from aicore.util import schema
    except ImportError as exc:
        return "fail", f"aicore is not importable: {exc}"
    problems = []
    for entry in declared:
        directory = unit.root / entry["path"]
        if not directory.is_dir():
            problems.append(f"{entry['path']}: no such directory")
            continue
        files = sorted(directory.glob("*.schema.json"))
        if not re.fullmatch(r"v\d+", directory.name):  # a legacy schema folder: outside the closed profile
            problems += legacy_problems(files, entry["path"])
            continue
        try:
            registry, kind = schema.load_contract(directory)
            kinds = [kind]
            for schema_id, document in schema._read_schemas(directory).items():
                for ref in schema._refs(document):
                    try:
                        registry.resolve(ref, schema_id)
                    except schema.RefError as exc:
                        problems.append(f"{entry['path']}: unresolved reference {ref!r}: {exc}")
        except schema.SchemaProfileError as first:
            try:
                # A set may leave extension slots open (plan/v1 -> orchestration.options, supplied by a bridge): they
                # resolve to a placeholder; any other profile or reference error stays a failure.
                registry, kinds = schema.load_contract_set(directory, open_slots=True)
            except schema.SchemaProfileError as second:
                problems.append(f"{entry['path']}: {second} (first: {first})")
                continue
        if registry is not None and len(kinds) == 1:
            problems += example_problems(schema, registry, kinds[0], directory, entry["path"])
    if problems:
        sys.stderr.write("\n".join(problems) + "\n")
        return "fail", f"{len(problems)} problem(s)"
    return "ok", f"{len(declared)} contract(s)"


def legacy_problems(files: list, label: str) -> list:
    """A folder that is not v<N> (draft-07 documents): each is a JSON object with $schema and local $refs that resolve."""
    problems = []
    if not files:
        return [f"{label}: no schema documents"]
    for file in files:
        try:
            document = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{label}/{file.name}: {exc}")
            continue
        if not isinstance(document, dict) or not isinstance(document.get("$schema"), str):
            problems.append(f"{label}/{file.name}: the root must be an object with $schema")
            continue
        stack = [document]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                ref = node.get("$ref")
                if isinstance(ref, str) and ref.startswith("#") and not pointer_resolves(document, ref[1:]):
                    problems.append(f"{label}/{file.name}: unresolved local $ref {ref!r}")
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return problems


def pointer_resolves(document, pointer: str) -> bool:
    node = document
    for part in [p for p in pointer.split("/") if p]:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return False
    return True


def example_problems(schema, registry, kind: str, directory: Path, label: str) -> list:
    problems = []
    for group, wants_valid in (("valid", True), ("invalid", False)):
        for path in sorted((directory / "examples" / group).glob("*.json")):
            try:
                issues = schema.validate(json.loads(path.read_text(encoding="utf-8")), kind, registry)
            except (OSError, ValueError) as exc:
                problems.append(f"{label}/examples/{group}/{path.name}: {exc}")
                continue
            if wants_valid and issues:
                problems.append(f"{label}/examples/{group}/{path.name}: expected valid, got {issues[0]}")
            if not wants_valid and not issues:
                problems.append(f"{label}/examples/{group}/{path.name}: expected invalid, passed")
    for path in sorted((directory / "examples").glob("*.json")):  # a flat example must pass
        try:
            issues = schema.validate(json.loads(path.read_text(encoding="utf-8")), kind, registry)
        except (OSError, ValueError) as exc:
            problems.append(f"{label}/examples/{path.name}: {exc}")
            continue
        if issues:
            problems.append(f"{label}/examples/{path.name}: {issues[0]}")
    return problems


def schema_compat(root: Path, unit: Unit, base_ref: str) -> tuple:
    if not base_ref:
        return "skip", "no --base-ref"
    base = rel(root, unit.root)
    home = Path(tempfile.mkdtemp(prefix="skm-ci-"))
    try:
        argv = ["bash", "packages/aicore/bin/aicore", "schema", "compat", "--base", base_ref,
                "--root", f"{base}/schemas", "--unit", f"{base}/unit.json"]
        proc = subprocess.run(argv, cwd=str(root), env=temp_env(home, {}), stderr=subprocess.PIPE, text=True)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0 and "SCHEMA_COMPAT_BASE_INVALID" in proc.stderr:
            # The compat loader cannot read the schemas of the base ref (not a change of this commit): report, do not fail.
            return "skip", "base ref not loadable by the compat tool (SCHEMA_COMPAT_BASE_INVALID)"
        return ("ok" if proc.returncode == 0 else "fail"), f"exit {proc.returncode}"
    except OSError as exc:
        return "fail", str(exc)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def secrets(root: Path, unit: Unit) -> tuple:
    """The content and file rules of public-hygiene.py over the tracked files of the module."""
    spec = importlib.util.spec_from_file_location("public_hygiene", root / "scripts/public-hygiene.py")
    if spec is None or spec.loader is None:
        return "fail", "scripts/public-hygiene.py is missing"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prefix = rel(root, unit.root) + "/"
    cwd = os.getcwd()
    os.chdir(root)
    try:
        paths = [p for p in module.list_tracked_files() if p.startswith(prefix)]
        found = module.check(paths) + module.content_violations(paths) + module.plan_reference_violations(paths)
    finally:
        os.chdir(cwd)
    for path, reason in found:
        sys.stderr.write(f"{path} — is prohibited by the rule «{reason}»\n")
    return ("fail", f"{len(found)} violation(s)") if found else ("ok", f"{len(paths)} file(s)")


def execute(root: Path, unit: Unit, step: dict, base_ref: str, extra_env: dict | None = None) -> tuple:
    if step["kind"] == "argv":
        return run_argv(root, step, extra_env)
    name = step["id"]
    if name == "cli-smoke":
        return cli_smoke(root, unit)
    if name == "contracts":
        return contracts(root, unit)
    if name == "schema-compat":
        return schema_compat(root, unit, base_ref)
    return secrets(root, unit)


def cmd_run(args, root: Path) -> int:
    units = discover(root)
    if args.all:
        tool_ids = tools(root)
        chosen = [u for u in units.values() if args.include_tools or u.id not in tool_ids]
    else:
        missing = [u for u in (args.unit or []) if u not in units]
        if missing or not args.unit:
            print(f"ci-matrix: unknown or missing unit: {', '.join(missing) or '(none given)'}", file=sys.stderr)
            return 2
        chosen = [units[u] for u in args.unit]
    plans = []
    for unit in chosen:
        steps = build_steps(root, unit)
        known = [s["id"] for s in steps]
        wanted = args.step or known
        bad = [s for s in wanted if s not in known]
        if bad and not args.all:
            print(f"ci-matrix: {unit.id} has no step {', '.join(bad)} (steps: {', '.join(known)})", file=sys.stderr)
            return 2
        plans.append((unit, [s for s in steps if s["id"] in wanted and s["id"] not in (args.skip or [])]))
    lock = threading.Lock()
    base_ref = args.base_ref or os.environ.get("BASE_REF", "")

    def run_chain(unit: Unit, steps: list) -> bool:
        """A chain of steps of one unit in order (the tests before validate); a line of the report is printed when a step
        ends."""
        red = False
        tests_green = False  # the tests of this unit ran green in this invocation: validate does not run them again
        for step in steps:
            started = time.monotonic()
            extra = {SKIP_TESTS_ENV: "1"} if step["id"] == "validate" and tests_green and not args.repeat_tests else {}
            state, note = execute(root, unit, step, base_ref, extra)
            tests_green = tests_green or (step["id"] == "test" and state == "ok")
            with lock:
                print(f"{state} {unit.id} {step['id']} {time.monotonic() - started:.1f}", flush=True)
                if state == "fail":
                    red = True
                    print(f"  {note}", file=sys.stderr, flush=True)
                elif state == "skip" and note:
                    print(f"  {note}", file=sys.stderr, flush=True)
        return red

    work = [(unit, chain) for unit, steps in plans for chain in chains(steps)]
    jobs = max(1, min(args.jobs if args.jobs else default_jobs(args.all), len(work) or 1))
    if jobs == 1:
        reds = [run_chain(unit, chain) for unit, chain in work]
    else:  # units and their independent steps are independent (each step has a throwaway HOME): the longest chain sets the time
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            reds = list(pool.map(lambda piece: run_chain(*piece), work))
    return 1 if any(reds) else 0


def chains(steps: list) -> list:
    """The steps of a unit as chains that may run at the same time: ``validate`` follows the ``test`` step of its unit (it
    skips the tests that just ran green), every other step stands alone (``standalone`` copies the files and runs
    its own tests, ``lint`` and the checks read only). Chains keep the order of the steps."""
    test = next((s for s in steps if s["id"] == "test"), None)
    follow = next((s for s in steps if s["id"] == "validate"), None) if test else None
    out, joined = [], False
    for step in steps:
        if step is follow:
            continue
        out.append([step, follow] if step is test and follow else [step])
        joined = joined or step is test
    return out


def default_jobs(everything: bool) -> int:
    """``SKM_CI_MATRIX_JOBS``, else 4 for ``--all`` (units and their independent steps side by side)
    and 1 for named units (their order is the order asked for)."""
    given = os.environ.get("SKM_CI_MATRIX_JOBS", "")
    if given.isdigit() and int(given) > 0:
        return int(given)
    return 4 if everything else 1


# ---- check -------------------------------------------------------------------------------------------------------

def workflow_run_lines(text: str) -> list:
    return [m.group(1).strip() for line in text.splitlines() if (m := re.fullmatch(r"\s*(?:-\s*)?run:\s*(.+)", line))]


def covered(root: Path, units: dict, command: str, workflow: str) -> str:
    """Return '' when the legacy command is covered by a step or the hub job, else the reason."""
    if command in HUB_COMMANDS:
        return "" if HUB_COMMANDS[command] in workflow else f"workflow lacks {HUB_COMMANDS[command]!r}"
    script = re.fullmatch(r"bash packages/([A-Za-z0-9_-]+)/scripts/(test|validate)\.sh(?: (.*))?", command)
    if script:
        unit_id, name, flags = script.groups()
        unit = units.get(unit_id)
        if unit is None:
            return f"unit {unit_id} not found"
        steps = {s["id"]: s for s in build_steps(root, unit)}
        step = steps.get(name)
        if step is None or step["argv"][:2] != ["bash", f"scripts/{name}.sh"]:
            return f"{unit_id} has no step {name} running scripts/{name}.sh"
        if flags and flags.strip() not in ("-v", "") and flags.strip() not in step["argv"]:
            return f"step {name} of {unit_id} lacks {flags.strip()}"
        if name == "test" and step["env"].get("SKM_TEST_CLASH") != "fail":
            return "test step does not set SKM_TEST_CLASH=fail"
        return ""
    if command == "bash scripts/lint.sh":
        lacking = [u.id for u in units.values() if (u.root / "lib").is_dir()
                   and "lint" not in [s["id"] for s in build_steps(root, u)]]
        return f"no lint step for {', '.join(lacking)}" if lacking else ""
    if command == "python3 scripts/ecosystem-units.py standalone --baseline":
        lacking = [u.id for u in units.values() if not u.bridge
                   and "standalone" not in [s["id"] for s in build_steps(root, u)]]
        return f"no standalone step for {', '.join(lacking)}" if lacking else ""
    return "no rule maps this command to a step"


def cmd_check(args, root: Path) -> int:
    problems = []
    units = discover(root)
    if not units:
        problems.append("no units found")
    workflow_path = root / WORKFLOW
    workflow = workflow_path.read_text(encoding="utf-8") if workflow_path.is_file() else ""
    if not workflow:
        problems.append(f"{WORKFLOW} is missing")
    else:
        if "ci-matrix.py list --json" not in workflow:
            problems.append(f"{WORKFLOW}: the matrix does not come from `ci-matrix.py list --json`")
        lines = workflow.splitlines()
        for number, line in enumerate(lines, 1):
            in_strategy = any(l.strip() == "strategy:" for l in lines[max(0, number - 4):number - 1])
            if in_strategy and re.fullmatch(r"\s+matrix:\s*\S.*", line) and "fromJSON(" not in line:
                problems.append(f"{WORKFLOW}:{number}: literal matrix (use fromJSON of the list output)")
            if re.fullmatch(r"\s+unit:\s*\[.*", line) or re.fullmatch(r"\s+-\s*unit:\s*\S+", line):
                problems.append(f"{WORKFLOW}:{number}: literal unit list in a matrix")
        runs = workflow_run_lines(workflow)
        if not any("ci-matrix.py run --unit ${{ matrix.unit }}" in r for r in runs):
            problems.append(f"{WORKFLOW}: no job runs `ci-matrix.py run --unit ${{{{ matrix.unit }}}}`")
        for run in runs:  # the steps live in this script only
            if re.search(r"packages/[A-Za-z0-9_-]+/scripts/(test|validate)\.sh|scripts/lint\.sh", run):
                problems.append(f"{WORKFLOW}: duplicates a step command: {run}")
        listed = {entry["unit"] for entry in matrix(root)["include"]}
        for unit_id in units:
            if unit_id not in listed:
                problems.append(f"unit {unit_id} is not in the matrix")
    legacy = list(LEGACY_COMMANDS)
    if args.legacy:
        legacy = json.loads(Path(args.legacy).read_text(encoding="utf-8"))
    for name in ("test.yml", "validate.yml"):  # while an old workflow still exists, every command it runs must be known
        path = root / ".github/workflows" / name
        if path.is_file():
            for run in workflow_run_lines(path.read_text(encoding="utf-8")):
                if run not in legacy:
                    problems.append(f"{name}: command not in the legacy list, cannot prove coverage: {run}")
    for command in legacy:
        reason = covered(root, units, command, workflow)
        if reason:
            problems.append(f"legacy command not covered: {command} ({reason})")
    for problem in problems:
        print(f"ci-matrix: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"ci-matrix: ok ({len(units)} unit(s), {len(legacy)} legacy command(s) covered)")
    return 0


# ---- command line ------------------------------------------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ci-matrix.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=str(HUB))
    p.add_argument("--check", action="store_true", help="structural check of the workflow against the matrix")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--legacy", help="JSON list of commands to prove covered (default: the commands of test.yml and validate.yml)")
    sub = p.add_subparsers(dest="command")
    ls = sub.add_parser("list")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--step", default="")
    ls.add_argument("--python", nargs="?", const=TEST_PYTHONS, default="",
                    help="comma-separated versions; the flag alone uses TEST_PYTHONS "
                         "(3.11,3.13,3.14). Omit the flag for no Python axis")
    st = sub.add_parser("steps")
    st.add_argument("unit")
    st.add_argument("--json", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("--unit", action="append")
    run.add_argument("--step", action="append")
    run.add_argument("--skip", action="append")
    run.add_argument("--all", action="store_true")
    run.add_argument("--include-tools", action="store_true")
    run.add_argument("--repeat-tests", action="store_true",
                     help="validate runs the tests again after a green test step (default: it skips them)")
    run.add_argument("--base-ref", default="")
    run.add_argument("--jobs", type=int, default=0, metavar="N",
                     help="steps at the same time, of different units and the independent steps of one unit (default "
                          "SKM_CI_MATRIX_JOBS, else 4 for --all and 1 otherwise); `validate` stays after the `test` of its unit")
    sub.add_parser("check")
    return p


def main(argv) -> int:
    args = parser().parse_args(argv)
    root = Path(args.root).resolve()
    if args.check or args.command == "check":
        return cmd_check(args, root)
    if args.command == "list":
        data = matrix(root, args.step, args.python)
        if args.json:
            print(json.dumps(data, separators=(",", ":")))
        else:
            for entry in data["include"]:
                print(" ".join(str(v) for v in entry.values()))
        return 0
    if args.command == "steps":
        unit = discover(root).get(args.unit)
        if unit is None:
            print(f"ci-matrix: unknown unit {args.unit}", file=sys.stderr)
            return 2
        steps = build_steps(root, unit)
        if args.json:
            print(json.dumps([{"id": s["id"], "cmd": s["text"]} for s in steps], indent=2))
        else:
            for s in steps:
                print(f"{s['id']}\t{s['text']}")
        return 0
    if args.command == "run":
        return cmd_run(args, root)
    parser().print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
