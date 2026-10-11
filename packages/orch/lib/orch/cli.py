"""Command line: validate exec/v1 documents, read the launch catalog, create ad-hoc input, render prompts, prepare a dry run, explain a launch-plan, list and test run-policy packs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from aicore.config import ConfigError

from orch import adhoc, catalog, launch, policies, render, settings
from orch.bindings import BINDINGS, check_skills
from orch.contracts import validate
from orch.port import PortError
from orch.schema import SchemaProfileError


def _launch(args: argparse.Namespace) -> int:
    try:
        catalog = launch.load_catalog()
        if args.action == "list":
            rows = [{"role": role, "provider": provider, **{k: v for k, v in item.items() if k != "argv"}}
                    for role, providers in catalog["launch"].items() for provider, item in providers.items()]
            print(json.dumps(rows, ensure_ascii=False))
        elif args.action == "show":
            print(json.dumps(launch.entry(catalog, args.role, args.provider), ensure_ascii=False))
        else:
            found = launch.entry(catalog, args.role, args.provider)
            result = {"argv": launch.build_argv(catalog, args.role, args.provider, model=args.model,
                                                effort=args.effort, cwd=args.cwd),
                      "transport": found["transport"], "timeout_s": found["timeout_s"]}
            print(json.dumps(result, ensure_ascii=False))
    except launch.LaunchError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    return 0


def _input_adhoc(args: argparse.Namespace) -> int:
    route = {key: value for key, value in (("class", args.model_class), ("effort", args.effort)) if value}
    try:
        doc = adhoc.build_adhoc_input(args.goal, args.include or [], args.exclude or [], args.check or [],
                                      args.procedure or [], args.read or [], route=route, review=args.review,
                                      why=args.why, expect=args.expect)
    except adhoc.AdhocError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2 if error.code == "USAGE" else 1
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0


def _render_prompt(args: argparse.Namespace) -> int:
    try:
        doc = json.loads(args.input.read_text(encoding="utf-8"))
        issues = [issue for issue in validate(doc, "execution-input") if issue.level == "error"]
        if issues:
            for issue in issues:
                print(f"{issue.code}: {issue.path or '/'} {issue.message}", file=sys.stderr)
            return 1
        manifest, text = render.load_role(args.role, args.roles_dir)
        sys.stdout.write(render.render_prompt(doc, manifest, text))
    except (OSError, ValueError) as error:
        print(f"INPUT_INVALID: {error}", file=sys.stderr)
        return 1
    except render.RenderError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    return 0


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PortError("INPUT_INVALID", f"cannot read {path}: {error}") from error


def _load_skills(path: Path | None) -> dict | None:
    """``--skills FILE``: ``{role_id: [{name, digest}]}``, the output of the skill bridge for every role."""
    if path is None:
        return None
    found = _load_json(path)
    if not isinstance(found, dict):
        raise PortError("INPUT_INVALID", f"{path} must be a JSON object mapping role ids to lists of {{name, digest}}")
    try:
        check_skills(found)
    except PortError as error:
        raise PortError("INPUT_INVALID", f"{path}: {error.message}") from error
    return found


def _primary_role(policy: dict) -> str:
    """The role whose engine setting chooses the engine of the run: the primary stage's role."""
    stages = policy.get("stages") if isinstance(policy, dict) else None
    for stage in stages if isinstance(stages, list) else []:
        if isinstance(stage, dict) and stage.get("kind") == "primary" and isinstance(stage.get("role"), str):
            return stage["role"]
    return "executor"


def _prepare(args: argparse.Namespace) -> int:
    try:
        if not args.dry_run:
            raise PortError("NOT_IMPLEMENTED", "prepare only supports --dry-run in this version")
        input_doc, policy = _load_json(args.input), _load_json(args.policy)
        current = settings.load(project=_project_root(), config_file=args.config)  # the configuration is read once
        binding, decision = settings.select_engine(current, _primary_role(policy), flag=args.binding)
        roles = render.load_roles(args.roles_dir)
        engine = BINDINGS[binding](args.out, catalog=catalog.Catalog.load(args.model_catalog),
                                   roles_dir=args.roles_dir, settings=current, submission_id=args.submission_id,
                                   skills=_load_skills(args.skills), engine_decision=decision)
        plan = engine.prepare(input_doc, policy, roles, provider=args.provider, dry_run=True)
    except PortError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        for issue in error.data.get("issues", []):
            print(f"  {issue['code']}: {issue['path'] or '/'} {issue['message']}", file=sys.stderr)
        if "launch_plan" in error.data:  # the refusal report
            print(json.dumps(error.data["launch_plan"], ensure_ascii=False, indent=2))
        return 1
    except (catalog.CatalogError, launch.LaunchError, settings.SettingsError) as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    except ConfigError as error:
        print(f"CONFIG_INVALID: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:  # an unreadable role manifest
        print(f"INPUT_INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def _explanation(plan: dict) -> dict:
    """The parts of a launch-plan that say what was decided and why."""
    return {"binding": plan["binding"], "decisions": plan.get("decisions", []), "stages": plan["stages"],
            "refusals": plan["refusals"], "digests": plan.get("digests", {}), "config": plan.get("config", {}),
            "policy_decision": plan.get("policy_decision"), "warnings": plan.get("proof", {}).get("warnings", [])}


def _explain_text(found: dict) -> str:
    lines = []
    engine = next((item for item in found["decisions"] if item["kind"] == "binding"), None)
    why = ", ".join(code for item in (engine or {}).get("considered", []) if item["accepted"]
                    for code in item.get("reason_codes", []))
    lines.append(f"engine: {found['binding']}" + (f" ({why})" if why else ""))
    for item in (engine or {}).get("considered", []):
        if not item["accepted"]:
            lines.append(f"  not chosen: {item['candidate']} ({', '.join(item.get('reason_codes', []))})")
    lines.append("stages:")
    for stage in found["stages"]:
        parts = [stage.get("provider", "-"), stage.get("model", "-"), stage.get("effort", "-")]
        lines.append(f"  {stage['stage_id']}: role {stage['role']}, {', '.join(parts)}")
    if not found["stages"]:
        lines.append("  (none prepared)")
    lines.append("considered:")
    for decision in (item for item in found["decisions"] if item["kind"] != "binding"):
        lines.append(f"  {decision['stage_id']}: chosen {decision['chosen']}"
                     + (f" (tie-break {decision['tie_break']})" if "tie_break" in decision else ""))
        for item in decision["considered"]:
            verdict = "accepted" if item["accepted"] else "refused"
            codes = ", ".join(item.get("reason_codes", []))
            lines.append(f"    {item['candidate']}: {verdict}" + (f" ({codes})" if codes else ""))
    lines.append("refusals:")
    for item in found["refusals"]:
        lines.append(f"  {item['stage_id']}: {item['capability']}: {item['reason']}"
                     + (f" [{item['reason_code']}]" if "reason_code" in item else ""))
        for link in item.get("chain", []):
            lines.append(f"    because {link['capability']}: {link['reason']}")
    if not found["refusals"]:
        lines.append("  (none)")
    lines.append("digests:")
    for name, value in found["digests"].items():
        lines.append(f"  {name}: {value}")
    lines.append(f"config {found['config'].get('digest', '-')}:")
    for key, value in found["config"].get("values", {}).items():
        lines.append(f"  {key} = {json.dumps(value, ensure_ascii=False)}")
    decision = found["policy_decision"] or {}
    codes = ", ".join(decision.get("reason_codes", []))
    lines.append(f"policy decision: {decision.get('decision', '-')}" + (f" ({codes})" if codes else ""))
    lines.append("warnings:")
    lines.extend(f"  {item['code']}: {item['message']}" for item in found["warnings"])
    if not found["warnings"]:
        lines.append("  (none)")
    return "\n".join(lines) + "\n"


def _explain(args: argparse.Namespace) -> int:
    """Read-only: validates the launch-plan, prints why it looks the way it does, writes nothing."""
    try:
        plan = _load_json(args.file)
    except PortError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    issues = [issue for issue in validate(plan, "launch-plan") if issue.level == "error"]
    if issues:
        for issue in issues:
            print(f"{issue.code}: {issue.path or '/'} {issue.message}", file=sys.stderr)
        return 1
    found = _explanation(plan)
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(_explain_text(found))
    return 0


def _project_root() -> Path | None:
    """The project the working directory belongs to: a git repository or a folder with ``.swissknifeman``."""
    from aicore.state import find_project_root
    root = find_project_root(Path.cwd())
    return root if (root / ".git").exists() or (root / ".swissknifeman").is_dir() else None


def _policy(args: argparse.Namespace) -> int:
    try:
        current = settings.load(project=_project_root(), config_file=args.config)
        if args.action == "list":
            rows = [policies.describe(policy_id, current) for policy_id in policies.discover(current)]
            if args.json:
                print(json.dumps(rows, ensure_ascii=False))
            else:
                for row in rows:
                    print(f"{row['policy_id']}\t{row['version']}\t{row['cases']} cases\t{row['source']}\t{row['description']}")
        elif args.action == "show":
            print(json.dumps(policies.load(args.policy_id, current), ensure_ascii=False, indent=2))
        else:
            ids = args.policy_id or list(policies.discover(current))
            rows = [row for policy_id in ids for row in policies.run_cases(policy_id, current)]
            if args.json:
                print(json.dumps(rows, ensure_ascii=False))
            else:
                for row in rows:
                    print(f"{row['status'].upper()}\t{row['policy_id']}\t{row['case'] or '-'}")
                    for item in row["differences"]:
                        print(f"  {item['field']}: expected {json.dumps(item['expected'], ensure_ascii=False)}, "
                              f"got {json.dumps(item['actual'], ensure_ascii=False)}", file=sys.stderr)
            return 1 if any(row["status"] != "pass" for row in rows) else 0
    except policies.PolicyError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        for issue in error.issues:
            print(f"  {issue['code']}: {issue['path'] or '/'} {issue['message']}", file=sys.stderr)
        return 1
    except ConfigError as error:
        print(f"CONFIG_INVALID: {error}", file=sys.stderr)
        return 1
    except settings.SettingsError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orch.py")
    parser.add_argument("--config", type=Path, metavar="FILE", help="configuration file of the invocation layer")
    verbs = parser.add_subparsers(dest="verb", required=True)
    command = verbs.add_parser("validate", help="validate an exec/v1 JSON document")
    command.add_argument("kind")
    command.add_argument("file", type=Path)
    command.add_argument("--quiet", action="store_true", help="suppress JSON output")
    command = verbs.add_parser("launch", help="read the launch catalog (role x provider)")
    actions = command.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="every entry without its argv")
    show = actions.add_parser("show", help="one entry as JSON")
    build = actions.add_parser("argv", help="command line of one entry; the process is not started")
    for sub in (show, build):
        sub.add_argument("role")
        sub.add_argument("provider")
    build.add_argument("--model", help="required when the entry's model_set is supported")
    build.add_argument("--effort")
    build.add_argument("--cwd", default=".")
    command = verbs.add_parser("input", help="create an execution-input without a plan")
    command = command.add_subparsers(dest="kind", required=True).add_parser(
        "adhoc", help="ad-hoc input, or a read-only review with --review BASE..HEAD")
    command.add_argument("--goal")
    command.add_argument("--why")
    command.add_argument("--include", nargs="+", action="extend")
    command.add_argument("--exclude", nargs="+", action="extend")
    command.add_argument("--check", action="append", metavar="V1=CMD", help="command check, expects exit 0")
    command.add_argument("--procedure", action="append", metavar="V2=TEXT", help="manual check, expects observed")
    command.add_argument("--expect", help="expected outcome of every --check (default: exit 0)")
    command.add_argument("--read", nargs="+", action="extend", metavar="PATH")
    command.add_argument("--class", dest="model_class", choices=("economy", "implementation", "frontier"))
    command.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max", "ultra"))
    command.add_argument("--review", metavar="BASE..HEAD")
    command = verbs.add_parser("render-prompt", help="role prompt for a Claude-only run (Markdown)")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--role", required=True)
    command.add_argument("--roles-dir", type=Path)
    command = verbs.add_parser("prepare", help="launch-plan of a run; --dry-run writes projection files only")
    command.add_argument("--binding", choices=sorted(BINDINGS),
                         help="engine; without it the [orch] configuration chooses (engine_by_role, engine)")
    command.add_argument("--provider")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--policy", type=Path, required=True)
    command.add_argument("--out", type=Path, required=True, help="directory for prompts and profiles")
    command.add_argument("--dry-run", action="store_true")
    command.add_argument("--model-catalog", type=Path, dest="model_catalog", metavar="FILE",
                         help="model-catalog/v1 file (default: the catalog packaged with aicore)")
    command.add_argument("--roles-dir", type=Path)
    command.add_argument("--submission-id", dest="submission_id", metavar="ID",
                         help="submission the launch-plan belongs to; must differ from the run id")
    command.add_argument("--skills", type=Path, metavar="FILE",
                         help="JSON {role_id: [{name, digest}]}: skills delivered per role (skill bridge output)")
    command = verbs.add_parser("explain", help="why a launch-plan looks as it does (read-only)")
    command.add_argument("file", type=Path)
    command.add_argument("--json", action="store_true")
    command = verbs.add_parser("policy", help="run-policy packs: list, show, test")
    actions = command.add_subparsers(dest="action", required=True)
    listing = actions.add_parser("list", help="every pack with version, case count and source")
    listing.add_argument("--json", action="store_true")
    show = actions.add_parser("show", help="the run-policy of a pack as JSON")
    show.add_argument("policy_id")
    test = actions.add_parser("test", help="run the cases of packs (all packs without an id)")
    test.add_argument("policy_id", nargs="*")
    test.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.verb == "policy":
        return _policy(args)
    if args.verb == "launch":
        return _launch(args)
    if args.verb == "input":
        return _input_adhoc(args)
    if args.verb == "render-prompt":
        return _render_prompt(args)
    if args.verb == "prepare":
        return _prepare(args)
    if args.verb == "explain":
        return _explain(args)
    try:
        doc = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"INPUT_INVALID: {exc}", file=sys.stderr)
        return 1
    try:
        issues = validate(doc, args.kind)
    except SchemaProfileError as exc:
        print(f"SCHEMA_PROFILE: {exc}", file=sys.stderr)
        return 1
    for issue in issues:
        print(f"{issue.code}: {issue.message}", file=sys.stderr)
    if not args.quiet:
        result = [issue._asdict() for issue in issues]
        print(json.dumps(result if issues else {"valid": True}, ensure_ascii=False))
    return 1 if any(issue.level == "error" for issue in issues) else 0
