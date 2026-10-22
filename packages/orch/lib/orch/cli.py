"""Command line: validate exec/v1 documents, read the launch catalog, create ad-hoc input, render prompts, prepare a dry run, explain a launch-plan, list and test run-policy packs, check engine conformance, run the cycle of a work source (claim, brief, prepare, register, commit) and diagnose the project (doctor)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from aicore.config import ConfigError
from aicore.state import ProjectContextRequired, project_state_dir
from aicore.util.digest import canonical_json_bytes, sha256_hex

from orch import (adhoc, catalog, conformance, events, journal, launch, policies, project as project_mod, render,
                  sandbox, settings)
from orch.bindings import BINDINGS, check_skills
from orch.conductor import contract as conductor_contract, records as conductor_records
from orch.contracts import validate
from orch.port import PortError
from orch.schema import SchemaProfileError
from orch.worksource import PluginWorkSource, WorkSourceError
from orch.worksource_file import FileWorkSource
from aicore.util.proc import run as run_with_timeout


def _launch(args: argparse.Namespace) -> int:
    try:
        current = settings.load(project=_project_root(args), config_file=args.config)
        catalog = launch.effective_catalog(current.launch)
        if args.action == "list":
            rows = [{"role": role, "provider": provider, **{k: v for k, v in item.items() if k != "argv"}}
                    for role, providers in catalog["launch"].items() for provider, item in providers.items()]
            print(json.dumps(rows, ensure_ascii=False))
        elif args.action == "show":
            shown = dict(launch.entry(catalog, args.role, args.provider))
            changed = {key: origin for key in shown
                       if (origin := launch.entry_origin(current.launch, args.role, args.provider, key))}
            print(json.dumps({**shown, **({"changed_by": changed} if changed else {})}, ensure_ascii=False))
        else:
            found = launch.entry(catalog, args.role, args.provider)
            result = {"argv": launch.build_argv(catalog, args.role, args.provider, model=args.model,
                                                effort=args.effort, cwd=args.cwd,
                                                access=current.launch["access"]),
                      "transport": found["transport"], "timeout_s": found["timeout_s"]}
            print(json.dumps(result, ensure_ascii=False))
    except launch.LaunchError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    except (ConfigError, settings.SettingsError) as error:
        print(f"{getattr(error, 'code', 'CONFIG_INVALID')}: {error}", file=sys.stderr)
        return 1
    return 0


def _input_adhoc(args: argparse.Namespace) -> int:
    route = {key: value for key, value in (("class", args.model_class), ("effort", args.effort)) if value}
    try:
        provenance = None
        if args.provenance:
            provenance = adhoc.support_provenance(args.provenance, plan=args.plan, phase=args.phase, item=args.item,
                                                  finding=args.finding, event=args.event, question=args.question)
        elif any((args.plan, args.phase, args.item, args.finding, args.event, args.question)):
            raise adhoc.AdhocError("USAGE", "--plan, --phase, --item, --finding, --event and --question need --provenance")
        doc = adhoc.build_adhoc_input(args.goal, args.include or [], args.exclude or [], args.check or [],
                                      args.procedure or [], args.read or [], route=route, review=args.review,
                                      why=args.why, expect=args.expect, provenance=provenance)
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


def _dry_run(input_doc: dict, policy: dict, current: settings.Settings, *, out, provider, binding_flag=None,
             model_catalog=None, roles_dir=None, submission_id=None, skills=None) -> dict:
    """The launch-plan of a dry-run preparation with the configuration read once by the caller."""
    binding, decision = settings.select_engine(current, _primary_role(policy), flag=binding_flag)
    roles = render.load_roles(roles_dir)
    engine = BINDINGS[binding](out, catalog=catalog.Catalog.load(model_catalog, current.launch), roles_dir=roles_dir, settings=current,
                               submission_id=submission_id, skills=skills, engine_decision=decision)
    return engine.prepare(input_doc, policy, roles, provider=provider, dry_run=True)


def _prepare(args: argparse.Namespace) -> int:
    try:
        if not args.dry_run:
            raise PortError("NOT_IMPLEMENTED", "prepare only supports --dry-run in this version")
        input_doc, policy = _load_json(args.input), _load_json(args.policy)
        current = settings.load(project=_project_root(args), config_file=args.config)  # the configuration is read once
        plan = _dry_run(input_doc, policy, current, out=args.out, provider=args.provider, binding_flag=args.binding,
                        model_catalog=args.model_catalog, roles_dir=args.roles_dir,
                        submission_id=args.submission_id, skills=_load_skills(args.skills))
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


def _project_root(args: argparse.Namespace | None = None) -> Path | None:
    """The project of the command: ``--project``, ``SKM_PROJECT_ROOT`` or the nearest ``.git`` or ``.swissknifeman`` above the
    working directory; ``None`` without one."""
    context = project_mod.find(getattr(args, "project", None))
    return context.root if context else None


def _route_explain(args: argparse.Namespace) -> int:
    from orch.conductor import engine, explain
    try:
        context = project_mod.require(getattr(args, "project", None))
        current = settings.load(project=context.root, config_file=args.config)
        found = explain.explain(engine.Conductor(project=context.root, settings=current, config_file=args.config,
                                                 project_resolution=context.resolution),
                                args.role, scenario=args.scenario, plan=args.plan, ref=args.item, run=args.run)
    except ProjectContextRequired as error:
        print(str(error), file=sys.stderr)
        return 1
    except ConfigError as error:
        print(f"CONFIG_INVALID: {error}", file=sys.stderr)
        return 1
    except explain.ExplainError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(explain.text(found))
    return 0


def _policy(args: argparse.Namespace) -> int:
    try:
        current = settings.load(project=_project_root(args), config_file=args.config)
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


def _research(args: argparse.Namespace) -> int:
    from orch import research
    try:
        project = _project_root(args)
        current = settings.load(project=project, config_file=args.config)
        found = research.sources_from(current)
        if args.action == "sources":
            doc = {"policy": current.research["policy"], "sources": [source.describe() for source in found]}
            if args.json:
                print(json.dumps(doc, ensure_ascii=False))
            else:
                print(f"policy\t{doc['policy']}")
                for row in doc["sources"]:
                    print(f"{row['order']}\t{row['id']}\t{row['kind']}\t{','.join(row['capabilities']) or '-'}")
            return 0
        chosen = {source.id: source for source in found}.get(args.source)
        if chosen is None:
            raise research.SourceError("SOURCE_UNKNOWN", f"no source {args.source!r}; configured: "
                                                         f"{', '.join(source.id for source in found) or 'none'}")
        try:
            text = args.query_file.read_text(encoding="utf-8")
        except OSError as error:
            print(f"INPUT_INVALID: {error}", file=sys.stderr)
            return 1
        answer = research.query(chosen, text, cwd=project)
        if args.json:
            print(json.dumps(answer, ensure_ascii=False))
        else:
            print(answer["text"])
            for item in answer["sources"]:
                print(f"source: {item}")
        return 0
    except research.SourceError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    except ConfigError as error:
        print(f"CONFIG_INVALID: {error}", file=sys.stderr)
        return 1


def _stubs(args: argparse.Namespace) -> int:
    """``stubs publish|list|show``: the additional instructions of the roles (``aicore.stubs``)."""
    from aicore import stubs as core
    from aicore.provider import models
    from orch.conductor import stubs
    try:
        project = _project_root(args) if args.action != "publish" or args.scope == "project" else None
        current = settings.load(project=project, config_file=args.config)
        layers = stubs.layers(current.stubs)
        if args.action == "publish":
            if args.scope == "project" and project is None:
                print("PROJECT_CONTEXT_REQUIRED: no project here; pass --project DIR or --scope machine", file=sys.stderr)
                return 1
            root = core.roots(project, layers=(args.scope,))[args.scope]
            rows = core.publish(stubs.targets(), root, dry_run=args.dry_run)
            if args.json:
                print(json.dumps({"root": str(root), "files": rows}, ensure_ascii=False))
            else:
                for row in rows:
                    print(f"{row['status']}\t{row['path']}" + (f"\t{row['reason']}" if row.get("reason") else ""))
            return 1 if any(row["status"] == "refused" for row in rows) else 0
        roles = [args.role] if args.action == "show" else list(stubs.ROLES)
        unknown = [role for role in roles if role not in stubs.ROLES]
        if unknown:
            print(f"STUB_TARGET_UNKNOWN: {unknown[0]!r} has no stub; roles: {', '.join(stubs.ROLES)}", file=sys.stderr)
            return 1
        roots = core.roots(project, layers=layers)
        variants = {stubs.target(role): stubs.discover_variants(roots, role) for role in roles} \
            if current.stubs.get("enabled", True) else {}
        found = core.resolve([stubs.target(role) for role in roles], project, layers=layers, variants=variants) \
            if current.stubs.get("enabled", True) else {}
        provider, model = getattr(args, "provider", None), getattr(args, "model", None)
        if model and not provider:
            print("STUB_TARGET_UNKNOWN: --model requires --provider", file=sys.stderr)
            return 1
        family = stubs.model_family(provider, model) if provider and model else None
        snapshot_doc = {"targets": found}
        doc = {"enabled": current.stubs.get("enabled", True), "layers": list(layers),
               "roots": {name: str(path) for name, path in roots.items()},
               "targets": {target: dict(entry, variants=variants.get(target, []),
                                        block=stubs.text(snapshot_doc, target.rsplit(".", 1)[1], provider, family),
                                        origin=stubs.origin(snapshot_doc, target.rsplit(".", 1)[1], provider, family))
                            for target, entry in found.items()}}
        if args.json:
            print(json.dumps(doc, ensure_ascii=False))
        elif args.action == "list":
            print(f"layers\t{','.join(doc['layers']) or '-'}" + ("" if doc["enabled"] else "\t(disabled)"))
            for target, entry in doc["targets"].items():
                parts = ", ".join(f"{part['layer']}:{part['slot']}" for part in entry["parts"] if "variant" not in part) or "-"
                print(f"{target}\t{len(entry['text'].encode('utf-8'))} bytes\t{parts}")
                for variant in entry["variants"]:
                    selected = [part for part in entry["parts"] if part.get("variant") == variant]
                    files = selected + [row for row in entry.get("skipped", []) if row.get("variant") == variant]
                    origins = ", ".join(dict.fromkeys(f"{row['layer']}:{row['slot']}" for row in files)) or "-"
                    print(f"{target}@{variant}\t{sum(part['bytes'] for part in selected)} bytes\t{origins}")
        else:
            entry = doc["targets"].get(stubs.target(args.role), {"text": "", "parts": [], "skipped": []})
            selected = stubs.parts(snapshot_doc, args.role, provider, family)
            for part in selected:
                print(f"# {part['reason']}: {part['layer']} {part['path']} ({part['bytes']} bytes, {part['sha256'][:12]})")
            for row in entry.get("skipped", []):
                if "variant" in row and row["variant"] not in (provider, f"{provider}--{family}" if family else None):
                    continue
                print(f"# skipped ({row['reason']}): {row['layer']} {row['path']}")
            print(entry.get("block") or "(no additional instructions)")
        return 0
    except models.ModelCatalogError as error:
        print(f"MODEL_CATALOG_UNAVAILABLE: {error}", file=sys.stderr)
        return 1
    except core.StubError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    except ConfigError as error:
        print(f"CONFIG_INVALID: {error}", file=sys.stderr)
        return 1


def _conformance(args: argparse.Namespace) -> int:
    try:
        rows = conformance.run(args.binding)
    except conformance.ConformanceError as error:
        print(f"CONFORMANCE_INVALID: {error}", file=sys.stderr)
        for issue in error.issues:
            print(f"  {issue['scenario']}: {issue['message']}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        for row in rows:
            print(f"{row['status'].upper()}\t{row['binding']}\t{row['scenario']}" + (f"\t{row['reason']}" if row["reason"] else ""))
            for item in row["differences"]:
                print(f"  {item['field']}: expected {json.dumps(item['expected'], ensure_ascii=False)}, "
                      f"got {json.dumps(item['actual'], ensure_ascii=False)}", file=sys.stderr)
    return 1 if any(row["status"] == "fail" for row in rows) else 0


# ---------------------------------------------------------------- doctor

RUNTIME_PROBE = ".swissknifeman/state/orch/conductor/cnd-probe/progress.jsonl"
REPORTS_PROBE = ".swissknifeman/orch/reports/cnd-probe/observer.md"
ARTIFACTS_PROBE = ".swissknifeman/orch-artifacts/cnd-probe/W1/evidence/V1.json"


def _check(check_id: str, status: str, observed: str, *, evidence=(), remediation=None) -> dict:
    doc = {"$schema": "urn:swissknifeman:aicore:check-result:v1", "check_id": check_id, "status": status,
           "category": "config", "observed": observed}
    if evidence:
        doc["evidence"] = list(evidence)
    if remediation:
        doc["remediation"] = remediation
    return doc


def _ignored(project: Path, relative: str) -> bool | None:
    """Whether git ignores ``relative`` in ``project`` (``None`` when git cannot answer)."""
    try:
        done = run_with_timeout(["git", "check-ignore", "-q", "--no-index", relative], cwd=str(project),
                              capture_output=True, text=True, timeout=60)
    except OSError:
        return None
    return {0: True, 1: False}.get(done.returncode)


def _sandbox_check() -> dict:
    probed = sandbox.probe()
    evidence = [f"{row['name']}: {row['detail']}" for row in probed["checked"]]
    if probed["available"]:
        return _check("orch.sandbox", "ok", "the provider sandbox can start", evidence=evidence)
    return _check("orch.sandbox", "warn",
                  f"the provider sandbox cannot start ({probed['reason']}): Codex roles are unavailable and the shell "
                  "commands of Claude Code roles run under the filesystem guard only", evidence=evidence,
                  remediation="install bubblewrap and socat; on Ubuntu 24.04+ an AppArmor profile that allows "
                              "user namespaces for bwrap is needed (a change to the machine, made by its owner); "
                              "scripts/check-env.sh lists every gap, docs/getting-started.md#requirements has the steps")


def doctor_checks(project: Path | None) -> list:
    """The conductor's runtime folder (streams, scout cache, progress) and its observer reports are run output, not
    artifacts of the work: both must be ignored. A piece of work keeps its record in its own artifact folder. The
    sandbox row says whether the providers' own sandboxes can start on this machine."""
    return _gitignore_checks(project) + [_sandbox_check()]


def _gitignore_checks(project: Path | None) -> list:
    if project is None or not (project / ".git").exists():
        return [_check("orch.conductor-gitignore", "skip", "not inside a git repository")]
    rows = []
    runtime_dir = Path(os.path.abspath(project_state_dir(project, "orch")))
    outside = not runtime_dir.is_relative_to(Path(os.path.abspath(project)))
    runtime = None if outside else _ignored(project, RUNTIME_PROBE)
    if outside:  # the marker names a workspace project: the runtime folder is its local/ folder, never in this tree
        rows.append(_check("orch.conductor-gitignore", "ok",
                           "the conductor runtime folder is in the local folder of the workspace project, outside "
                           "this checkout", evidence=[str(runtime_dir)]))
    elif runtime is None:
        rows.append(_check("orch.conductor-gitignore", "skip", "git check-ignore did not answer"))
    elif runtime:
        rows.append(_check("orch.conductor-gitignore", "ok", "the conductor runtime folder is ignored",
                           evidence=[RUNTIME_PROBE]))
    else:
        rows.append(_check("orch.conductor-gitignore", "warn",
                           "the conductor runtime folder is not ignored: role streams, the scout cache and "
                           "progress.jsonl would reach git", evidence=[RUNTIME_PROBE],
                           remediation="add `.swissknifeman/state/` to .gitignore (the shared gitignore policy "
                                       "entry swissknifeman-state)"))
    reports = _ignored(project, REPORTS_PROBE)
    if reports is False:
        rows.append(_check("orch.conductor-reports", "warn",
                           "the conductor reports folder is not ignored: the observer report written at the end of "
                           "every run would leave the tree dirty for the next piece and refuse its commit",
                           evidence=[REPORTS_PROBE],
                           remediation="add `.swissknifeman/orch/` to .gitignore (the shared gitignore policy entry "
                                       "orch-conductor-reports)"))
    elif reports:
        rows.append(_check("orch.conductor-reports", "ok", "the conductor reports folder is ignored",
                           evidence=[REPORTS_PROBE]))
    artifacts = _ignored(project, ARTIFACTS_PROBE)
    if artifacts is False:
        rows.append(_check("orch.conductor-artifacts", "warn",
                           "the local artifact folder of the conductor is not ignored: the records of pieces whose source "
                           "names no artifact folder (check logs with absolute paths) would reach git",
                           evidence=[ARTIFACTS_PROBE],
                           remediation="add `.swissknifeman/orch-artifacts/` to .gitignore (the shared gitignore policy "
                                       "entry orch-artifacts)"))
    elif artifacts:
        rows.append(_check("orch.conductor-artifacts", "ok", "the local artifact folder of the conductor is ignored",
                           evidence=[ARTIFACTS_PROBE]))
    return rows


def _doctor(args: argparse.Namespace) -> int:
    rows = doctor_checks(_project_root(args))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row['status'].upper()}\t{row['check_id']}\t{row['observed']}")
            if row.get("remediation"):
                print(f"  fix: {row['remediation']}")
    return 1 if any(row["status"] == "fail" for row in rows) else 0


# ---------------------------------------------------------------- the cycle of a work source

RUN_DOC = "run.json"
LAUNCH_PLAN_DOC = "launch-plan.json"
REGISTER_RECEIPT = "receipts/register.json"
COMMIT_RECEIPT = "receipts/commit.json"
NOTE_RECEIPT = "receipts/note.json"
RELEASE_RECEIPT = "receipts/release.json"
STAGE_STATUS = {"done": "completed", "done_with_deviations": "completed", "blocked": "failed"}


class SourceRefusal(Exception):
    """A refusal of a ``source`` command: ``CODE: message`` on stderr and ``exit`` (1, or 3 without a source)."""

    def __init__(self, code: str, message: str, exit_code: int = 1):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.exit_code = exit_code


def _actor(text: str) -> dict:
    """``PROVIDER/MODEL[/EFFORT]`` as a work-source actor."""
    parts = text.split("/") if isinstance(text, str) else []
    if len(parts) not in (2, 3) or not all(parts):
        raise argparse.ArgumentTypeError(f"{text!r} must be PROVIDER/MODEL[/EFFORT]")
    return dict(zip(("provider", "model", "effort"), parts))


def _evidence(text: str) -> tuple:
    check_id, sep, path = text.partition("=")
    if not sep or not path or not check_id[:1] == "V" or not check_id[1:].isdigit():
        raise argparse.ArgumentTypeError(f"{text!r} must be V<n>=PATH")
    return check_id, path


def submission_id(plan: str, items: list, actor: dict) -> str:
    """The default submission of a claim: the same plan, items and actor give the same submission (and run)."""
    return "sub-" + sha256_hex(canonical_json_bytes({"plan": plan, "items": list(items), "actor": actor}))[:24]


def run_id_of(submission: str) -> str:
    return "run-" + sha256_hex(submission.encode("utf-8"))[:24]


def _source(current: settings.Settings, project, config_file, doc: dict | None = None):
    """The work source of a claimed run: its input file (``run.json`` ``source``), else the plugin of the configuration."""
    found = (doc or {}).get("source")
    if isinstance(found, dict) and found.get("kind") == "file":
        return FileWorkSource(found["path"], project=project, commit=bool(found.get("commit")))
    return PluginWorkSource(current.work_source, project=project, config_file=config_file)


def _call(source, op: str, **fields) -> dict:
    try:
        return getattr(source, op)(**fields)
    except WorkSourceError as error:
        raise SourceRefusal(error.code, error.message, 3 if error.code == "WORK_SOURCE_UNAVAILABLE" else 1) from None


def _run(run_id: str, project) -> tuple:
    """``(run directory, run.json)`` of a claimed run; ``RUN_UNKNOWN`` when it was never claimed here."""
    directory = journal.run_dir(run_id, project=project)
    doc = journal.read_doc(directory, RUN_DOC)
    if doc is None:
        raise SourceRefusal("RUN_UNKNOWN", f"no claimed run {run_id} in {directory.parent}")
    return directory, doc


def _emit(event_type: str, data: dict, *, subject: str, current, project, config_file) -> None:
    events.emit(event_type, {key: value for key, value in data.items() if value is not None}, subject=subject,
                settings=current, project=project, config_file=config_file)


def _print(doc: dict) -> None:
    print(json.dumps(doc, ensure_ascii=False, indent=2))


def _source_claim(args, current, project) -> int:
    actor, items = args.actor, list(args.item or [])
    file_source = None
    if args.input:
        args.plan = str(Path(args.input).resolve())
        file_source = {"kind": "file", "path": args.plan, "commit": bool(args.commit)}
    elif args.commit:
        raise SourceRefusal("USAGE", "--commit belongs to --input: a plan source commits as its own policy says", 2)
    submission = args.submission_id or submission_id(args.plan, items, actor)
    run_id = run_id_of(submission)
    directory = journal.run_dir(run_id, project=project)
    before = journal.read_doc(directory, RUN_DOC)
    emit = dict(current=current, project=project, config_file=args.config)
    # A repeated claim asks for the run's own item, so a run never moves on to other work once its item is closed.
    asked = [before["ref"]] if before is not None and before.get("ref") else items
    try:
        answer = _call(_source(current, project, args.config, {"source": file_source}), "claim", plan=args.plan,
                       plans_root=args.plans_root,
                       items=asked or None, batch=True if args.batch else None,
                       scenario=getattr(args, "scenario", None), run_id=run_id, submission_id=submission,
                       actor=actor, actor_source=getattr(args, "actor_source", None),
                       actor_fields=getattr(args, "actor_field", None) or None,
                       actor_class=getattr(args, "actor_class", None),
                       orch_config=str(Path(args.config).resolve()) if args.config else None)
    except SourceRefusal as refusal:
        _emit("orch.run.refused", {"submission_id": submission, "step": "claim", "reason_codes": [refusal.code],
                                   "run_id": run_id}, subject=submission, **emit)
        raise
    _print({"run_id": run_id, "submission_id": submission, **answer})
    if answer["status"] == "claimed":
        plugin = "file" if file_source else current.work_source
        doc = {"run_id": run_id, "submission_id": submission, "plugin": plugin, "plan": args.plan,
               "plans_root": args.plans_root, "ref": answer["ref"], "attempt_id": answer["attempt_id"],
               "scenario": answer.get("scenario"), "session": answer.get("session")}
        if answer.get("actor_override") or (before or {}).get("actor_override"):  # the plan's executor the run replaced
            doc["actor_override"] = answer.get("actor_override") or before["actor_override"]
        if file_source:
            doc["source"] = file_source
        if before is not None:  # a repeated claim keeps what later steps recorded (input_ref)
            doc = {**before, **doc}
        journal.write_doc(directory, RUN_DOC, doc)
        if before is None or before.get("attempt_id") != doc["attempt_id"]:
            _emit("orch.run.started", {"run_id": run_id, "submission_id": submission, "attempt_id": doc["attempt_id"],
                                       "source": {"plugin": plugin, "ref": doc["ref"]},
                                       "scenario": doc["scenario"], "config_digest": settings.config_digest(current),
                                       "project_resolution": getattr(args, "project_resolution", None)},
                  subject=run_id, **emit)
        return 0
    if answer["status"] == "blocked":
        _emit("orch.run.refused", {"submission_id": submission, "step": "claim", "run_id": run_id,
                                   "reason_codes": [answer.get("reason_code") or "CLAIM_BLOCKED"],
                                   "ref": answer.get("ref")}, subject=submission, **emit)
        return 1
    return 0


def _source_brief(args, current, project) -> int:
    directory, doc = _run(args.run, project)
    answer = _call(_source(current, project, args.config, doc), "brief", plan=doc["plan"], plans_root=doc.get("plans_root"),
                   ref=doc["ref"], run_id=doc["run_id"])
    journal.write_doc(directory, RUN_DOC, {**doc, "input_ref": answer["input_ref"], "input_id": answer["input_id"]})
    _print(answer)
    return 0


def _brief_doc(doc: dict, project) -> dict:
    from aicore.state import blobs
    if not isinstance(doc.get("input_ref"), dict):
        raise SourceRefusal("RUN_NOT_BRIEFED", f"run {doc['run_id']} has no brief; run source brief first")
    try:
        found = json.loads(blobs.read_bytes(doc["input_ref"], project=project))
    except FileNotFoundError:
        raise SourceRefusal("BRIEF_UNAVAILABLE", f"the brief {doc['input_ref']['digest']} is not in the artifact "
                            "store of this project") from None
    except ValueError as error:
        raise SourceRefusal("BRIEF_UNAVAILABLE", str(error)) from None
    if not isinstance(found, dict):
        raise SourceRefusal("BRIEF_UNAVAILABLE", "the stored brief is not a JSON object")
    return found


def _source_prepare(args, current, project, *, conductor: bool = False) -> int:
    """Bind the briefed run and write ``launch-plan.json``.

    Public ``source prepare`` leaves ``conductor`` false and binds the loaded pack unchanged.
    The conductor passes true and binds a copy that omits the stages it skips. Neither path
    rewrites the pack on disk.
    """
    directory, doc = _run(args.run, project)
    emit = dict(current=current, project=project, config_file=args.config)
    refused = {"submission_id": doc["submission_id"], "step": "prepare", "run_id": doc["run_id"], "ref": doc["ref"],
               "policy_id": doc.get("scenario"), "binding": args.binding}
    try:
        input_doc = _brief_doc(doc, project)
        policy = policies.load(doc.get("scenario") or current.default_profile, current)
        if conductor:
            from orch.preparation import effective_policy
            policy = effective_policy(policy)
        plan = _dry_run(input_doc, policy, current, out=directory / "prepare", provider=args.provider,
                        binding_flag=args.binding, model_catalog=args.model_catalog,
                        submission_id=doc["submission_id"])
    except PortError as error:
        report = error.data.get("launch_plan")
        codes = [error.code] + [item["reason_code"] for item in (report or {}).get("refusals", [])
                                if item.get("reason_code") and item["reason_code"] != error.code]
        _emit("orch.run.refused", {**refused, "reason_codes": codes}, subject=doc["submission_id"], **emit)
        print(f"{error.code}: {error.message}", file=sys.stderr)
        if report:
            _print(report)
        return 1
    except (SourceRefusal, policies.PolicyError, catalog.CatalogError, launch.LaunchError,
            settings.SettingsError) as error:
        _emit("orch.run.refused", {**refused, "reason_codes": [error.code]}, subject=doc["submission_id"], **emit)
        raise SourceRefusal(error.code, error.message if isinstance(error, SourceRefusal) else str(error)) from None
    journal.write_doc(directory, LAUNCH_PLAN_DOC, plan)
    _print(plan)
    return 0


SUPPORT_NOTE_KINDS = ("plan_support", "phase_support")


def _support_note(args, current, project, doc: dict, report: dict) -> dict | None:
    """The journal note of support work for a plan or phase: the file source has no journal, so the note goes to the
    configured work source of the plan. ``{"outcome": recorded | unsupported | refused, "message"?}``, None for other
    work. A source without ``note`` loses the note, never the work (the conductor prints ``WORK_SOURCE_NO_NOTE``)."""
    if not isinstance(doc.get("source"), dict) or doc["source"].get("kind") != "file":
        return None
    try:
        provenance = _brief_doc(doc, project).get("provenance") or {}
    except SourceRefusal:
        return None
    if provenance.get("kind") not in SUPPORT_NOTE_KINDS:
        return None
    text = f"{provenance['kind']} {doc['ref']} ({args.status}): {report.get('summary') or 'no summary'}"
    refs = [provenance["phase"]] if provenance.get("phase") else []
    try:
        answer = PluginWorkSource(current.work_source, project=project, config_file=args.config).note(
            collection=provenance["plan"], text=text, refs=refs, run_id=doc["run_id"], actor=args.actor)
    except WorkSourceError as error:
        return {"outcome": "unsupported", "message": error.message}
    if answer["outcome"] == "refused":
        return {"outcome": "refused", "message": f"{answer.get('reason_code', 'NOTE_REFUSED')}: {answer.get('message', '')}".rstrip(": ")}
    return {"outcome": answer["outcome"]}


def _source_register(args, current, project) -> int:
    directory, doc = _run(args.run, project)
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SourceRefusal("INPUT_INVALID", f"cannot read the report {args.report}: {error}") from None
    evidence = dict(args.evidence or [])
    if len(evidence) != len(args.evidence or []):
        raise SourceRefusal("INPUT_INVALID", "--evidence repeats a check id")
    answer = _source_effect(_source(current, project, args.config, doc), directory, "register", plan=doc["plan"],
                   plans_root=doc.get("plans_root"), ref=doc["ref"], run_id=doc["run_id"],
                   attempt_id=doc["attempt_id"], status=args.status, report=report, evidence=evidence,
                   registrar=args.actor, executed_by=args.executed_by or args.actor)
    if answer["outcome"] == "recorded":
        note = _support_note(args, current, project, doc, report)
        if note:
            journal.write_doc(directory, NOTE_RECEIPT, note)
            answer = {**answer, "note": note}  # printed for the conductor; not part of the work-source answer
    _print(answer)
    emit = dict(current=current, project=project, config_file=args.config)
    if answer["outcome"] == "refused":
        _emit("orch.run.refused", {"submission_id": doc["submission_id"], "step": "register", "run_id": doc["run_id"],
                                   "ref": doc["ref"], "reason_codes": [answer.get("reason_code") or "REGISTER_REFUSED"]},
              subject=doc["submission_id"], **emit)
        return 1
    if answer["outcome"] == "recorded":  # a repeat that changed nothing (no-op) is not a second end of the run
        _emit("orch.run.stage.finished", {"run_id": doc["run_id"], "stage_id": "primary", "attempt": 1,
                                          "status": STAGE_STATUS[args.status], "attempt_id": doc["attempt_id"]},
              subject=doc["run_id"], **emit)
        _emit("orch.run.finished", {"run_id": doc["run_id"], "submission_id": doc["submission_id"], "ref": doc["ref"],
                                    "attempt_id": doc["attempt_id"], "outcome": args.status,
                                    "gate": answer["gate"]["verdict"]}, subject=doc["run_id"], **emit)
    return 0


def _source_commit(args, current, project) -> int:
    directory, doc = _run(args.run, project)
    answer = _source_effect(_source(current, project, args.config, doc), directory, "commit", plan=doc["plan"],
                   plans_root=doc.get("plans_root"), ref=doc["ref"], run_id=doc["run_id"],
                   attempt_id=doc["attempt_id"], paths=list(args.path or []), actor=args.actor)
    _print(answer)
    return 1 if answer["outcome"] == "refused" else 0


def _source_effect(source, directory, kind: str, **fields) -> dict:
    """Persist intent before the effect; bind legacy answers to that exact request before publishing the receipt.

    Replacing the request clears any previous answer digest. A crash cannot pair an old receipt with a new intent.
    The receipt itself remains the unmodified work-source/v1 answer.
    """
    request = {"attempt_id": fields["attempt_id"], "parameters": fields,
               "digest": sha256_hex(canonical_json_bytes(fields))}
    if kind == "commit":
        # A repeat can finish only the workspace part. Retain the already committed product revision before
        # replacing either document, including when another crash happens before the repeated answer is published.
        try:
            prior = journal.read_doc(directory, "receipts/commit-request.json")
            receipt = journal.read_doc(directory, "receipts/commit.json")
        except (OSError, ValueError):
            prior, receipt = None, None
        parameters = prior.get("parameters") if isinstance(prior, dict) else None
        if (isinstance(parameters, dict) and prior.get("attempt_id") == fields["attempt_id"]
                and all(parameters.get(key) == fields.get(key) for key in ("run_id", "ref", "attempt_id"))
                and prior.get("digest") == sha256_hex(canonical_json_bytes(parameters))):
            source_sha = prior.get("source_sha")
            if (isinstance(receipt, dict) and receipt.get("outcome") in ("committed", "no-op")
                    and receipt.get("attempt") in (None, fields["attempt_id"])
                    and receipt.get("repo") != "workspace" and receipt.get("sha")
                    and prior.get("receipt_digest") == sha256_hex(canonical_json_bytes(receipt))):
                source_sha = receipt["sha"]
            if source_sha:
                request["source_sha"] = source_sha
    journal.write_doc(directory, f"receipts/{kind}-request.json", request)
    answer = _call(source, kind, **fields)
    if kind == "commit" and answer.get("outcome") in ("committed", "no-op") \
            and answer.get("attempt") in (None, fields["attempt_id"]) \
            and answer.get("repo") != "workspace" and answer.get("sha"):
        request["source_sha"] = answer["sha"]
    request["receipt_digest"] = sha256_hex(canonical_json_bytes(answer))
    journal.write_doc(directory, f"receipts/{kind}-request.json", request)
    journal.write_doc(directory, f"receipts/{kind}.json", answer)
    return answer


def _source_release(args, current, project) -> int:
    """Give a claimed run back to the source (a piece stopped before any work began), so that a later run can claim it."""
    directory, doc = _run(args.run, project)
    answer = _call(_source(current, project, args.config, doc), "release", plan=doc["plan"], plans_root=doc.get("plans_root"),
                   ref=doc["ref"], run_id=doc["run_id"], reason=args.reason, actor=args.actor)
    journal.write_doc(directory, RELEASE_RECEIPT, answer)
    _print(answer)
    return 1 if answer["outcome"] == "refused" else 0


def _source_research(args, current, project) -> int:
    """Save the research-result of a research stage where the source keeps research (a plan: its research folder; a file
    input: its artifact folder). A source that does not serve it is a refusal; the result is still in the run's artifacts."""
    directory, doc = _run(args.run, project)
    try:
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SourceRefusal("INPUT_INVALID", f"cannot read the result {args.result}: {error}") from None
    answer = _call(_source(current, project, args.config, doc), "research", plan=doc["plan"],
                   plans_root=doc.get("plans_root"), ref=doc["ref"], run_id=doc["run_id"], number=args.number,
                   result=result, actor=args.actor)
    journal.write_doc(directory, f"receipts/research-{args.number}.json", answer)
    _print(answer)
    return 1 if answer["outcome"] == "refused" else 0


def _source_command(args: argparse.Namespace) -> int:
    handler = {"claim": _source_claim, "brief": _source_brief, "prepare": _source_prepare,
               "register": _source_register, "commit": _source_commit, "release": _source_release,
               "research": _source_research}[args.action]
    try:
        context = project_mod.require(getattr(args, "project", None))  # the cycle writes the state of a project
        project = context.root
        args.project_resolution = getattr(args, "named_resolution", None) or context.resolution
        current = settings.load(project=project, config_file=args.config)  # the configuration is read once
        return handler(args, current, project)
    except ProjectContextRequired as error:
        print(str(error), file=sys.stderr)
        return 1
    except SourceRefusal as refusal:
        print(f"{refusal.code}: {refusal.message}", file=sys.stderr)
        return refusal.exit_code
    except PortError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    except ConfigError as error:
        print(f"CONFIG_INVALID: {error}", file=sys.stderr)
        return 1
    except settings.SettingsError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1


def _source_parser(verbs) -> None:
    command = verbs.add_parser("source", help="cycle of a work source: claim, brief, prepare, register, commit, release, research")
    actions = command.add_subparsers(dest="action", required=True)
    claim = actions.add_parser("claim", help="claim one piece of work for a run (repeatable: same arguments, same run)")
    where = claim.add_mutually_exclusive_group(required=True)
    where.add_argument("--plan", help="collection of the work source, such as a plan id or path")
    where.add_argument("--input", type=Path, metavar="FILE",
                       help="the built-in file source: one execution-input document, no plan")
    claim.add_argument("--commit", action="store_true",
                       help="with --input: commit the changed paths of the work (default: they stay in the tree)")
    claim.add_argument("--plans-root", dest="plans_root", metavar="DIR")
    claim.add_argument("--item", action="append", metavar="REF", help="candidate reference (repeatable)")
    claim.add_argument("--batch", action="store_true", help="the claim is part of a batch of one run: a dependency in progress (an earlier piece of the batch) counts as met")
    claim.add_argument("--scenario", metavar="S", help="the scenario of the run: wins over the one the source resolves "
                       "for the piece (a plan source; a file source takes it from the document)")
    claim.add_argument("--actor", required=True, type=_actor, metavar="P/M[/E]", help="who runs the work")
    claim.add_argument("--actor-source", dest="actor_source", choices=("options", "default"),
                       help="options: the run's --options name the executor (it wins over the plan's); default: the source "
                            "may use its own executor (the default without this flag)")
    claim.add_argument("--actor-field", dest="actor_field", action="append", choices=("provider", "model", "effort"),
                       help="with --actor-source options: a field of the actor the run named (repeatable)")
    claim.add_argument("--actor-class", dest="actor_class", choices=("economy", "implementation", "frontier"),
                       help="with --actor-source options: the executor class the run named without a model")
    claim.add_argument("--submission-id", dest="submission_id", metavar="SUB",
                       help="submission key (default: derived from plan, items and actor)")
    brief = actions.add_parser("brief", help="store the brief of a claimed run as an artifact")
    brief.add_argument("--run", required=True, metavar="RUN")
    prepare = actions.add_parser("prepare", help="dry-run launch-plan of a briefed run (launch-plan.json)")
    prepare.add_argument("--run", required=True, metavar="RUN")
    prepare.add_argument("--provider", required=True)
    prepare.add_argument("--binding", choices=sorted(BINDINGS),
                         help="engine; without it the [orch] configuration chooses")
    prepare.add_argument("--model-catalog", type=Path, dest="model_catalog", metavar="FILE",
                         help="model-catalog/v1 file (default: the catalog packaged with aicore)")
    register = actions.add_parser("register", help="register the outcome of a run (fencing and evidence gate)")
    register.add_argument("--run", required=True, metavar="RUN")
    register.add_argument("--report", required=True, type=Path, help="stage-report JSON file")
    register.add_argument("--status", required=True, choices=sorted(STAGE_STATUS))
    register.add_argument("--evidence", action="append", default=[], type=_evidence, metavar="V#=PATH",
                          help="check-evidence file of an acceptance check (repeatable)")
    register.add_argument("--actor", required=True, type=_actor, metavar="P/M[/E]", help="the registrar")
    register.add_argument("--executed-by", dest="executed_by", type=_actor, metavar="P/M[/E]",
                          help="who did the work (default: the registrar)")
    commit = actions.add_parser("commit", help="one commit of a registered run, scoped by the source")
    commit.add_argument("--run", required=True, metavar="RUN")
    commit.add_argument("--path", action="append", default=[], metavar="PATH",
                        help="repository path the commit owns beyond the scope of the work (repeatable)")
    commit.add_argument("--actor", type=_actor, metavar="P/M[/E]", help="who commits (default: the source decides)")
    release = actions.add_parser("release", help="give a claimed run back to the source (no work began), so that a later "
                                                 "run can claim the piece")
    release.add_argument("--run", required=True, metavar="RUN")
    release.add_argument("--reason", metavar="TEXT", help="why, for the source's journal")
    release.add_argument("--actor", type=_actor, metavar="P/M[/E]", help="who releases (default: the source decides)")
    research = actions.add_parser("research", help="save the research-result of a run where the source keeps research")
    research.add_argument("--run", required=True, metavar="RUN")
    research.add_argument("--result", required=True, type=Path, help="research-result JSON file")
    research.add_argument("--number", required=True, type=int, metavar="N", help="ordinal of the research of the piece, from 1")
    research.add_argument("--actor", type=_actor, metavar="P/M[/E]", help="who saves (default: the source decides)")


def _conduct_args(argv: list[str]) -> list[str] | None:
    """The arguments of the conductor when the command is ``orch [--config F] [--project D] conduct ...``, else None."""
    head: list[str] = []
    rest = list(argv)
    while rest and rest[0] in ("--config", "--project") and len(rest) > 1:
        head += rest[:2]
        rest = rest[2:]
    while rest and rest[0].startswith(("--config=", "--project=")):
        head.append(rest.pop(0))
    return head + rest[1:] if rest and rest[0] == "conduct" else None


def main(argv: list[str] | None = None) -> int:
    conduct = _conduct_args(list(sys.argv[1:] if argv is None else argv))
    if conduct is not None:  # one public CLI: the conductor is the `conduct` group of orch
        from orch.conductor.cli import main as conduct_main
        return conduct_main(conduct)
    try:
        return _main(argv)
    except ProjectContextRequired as error:  # a named project that is not a folder, or the cycle without a project
        print(str(error), file=sys.stderr)
        return 1


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orch.py")
    parser.add_argument("--config", type=Path, metavar="FILE", help="configuration file of the invocation layer")
    parser.add_argument("--project", type=Path, metavar="DIR",
                        help="the project; default: SKM_PROJECT_ROOT, else the nearest .git or .swissknifeman above the "
                             "working directory (the run cycle needs one: PROJECT_CONTEXT_REQUIRED)")
    parser.add_argument("--project-resolution", dest="named_resolution",
                        choices=("launcher", "flag", "environment", "marker", "git"),
                        help="with --project: how the caller found the project (the conductor passes its own answer; "
                             "recorded in orch.run.started)")
    verbs = parser.add_subparsers(dest="verb", required=True)
    verbs.add_parser("conduct", help="the conductor: run|resume|settle|release|status|observe|answer|questions|prompt|"
                                     "gates (orch conduct --help)", add_help=False)
    command = verbs.add_parser("validate", help="validate an exec/v1, conductor/v1 or records/v1 JSON document")
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
    command.add_argument("--provenance", choices=sorted(adhoc.SUPPORT_PROVENANCE),
                         help="owner of work outside the items of a plan (default: adhoc)")
    for flag, text in (("plan", "plan id"), ("phase", "phase, such as P6"), ("item", "item, such as P6.1"),
                       ("finding", "finding id"), ("event", "journal event of the deviation"),
                       ("question", "question to research or advise on")):
        command.add_argument("--" + flag, help=f"with --provenance: {text}")
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
    command = verbs.add_parser("route", help="routes of the conductor roles: explain (read-only)")
    actions = command.add_subparsers(dest="action", required=True)
    explain = actions.add_parser("explain", help="why a role runs on its route: the candidates and their availability, "
                                                 "the selected route and the layer of each of its fields")
    explain.add_argument("--role", required=True, help="context-scout, executor, reviewer, triager, registrar or report-fixer")
    explain.add_argument("--plan", help="with --item: the options of the newest conductor run of this plan and item")
    explain.add_argument("--run", help="with --item: recorded routes of this run, separately from availability now")
    explain.add_argument("--item", help="with --plan or --run: the piece of work")
    explain.add_argument("--scenario", help="the scenario to explain (default: default_profile)")
    explain.add_argument("--json", action="store_true")
    command = verbs.add_parser("conformance", help="engine conformance scenarios; covered ones run, declared ones are listed")
    command.add_argument("--binding", choices=sorted(BINDINGS), help="only this binding (default: every binding)")
    command.add_argument("--json", action="store_true")
    _source_parser(verbs)
    command = verbs.add_parser("research", help="research sources of [orch.research]: list them, ask one")
    actions = command.add_subparsers(dest="action", required=True)
    sources = actions.add_parser("sources", help="the configured sources on the ladder (read-only)")
    sources.add_argument("--json", action="store_true")
    ask = actions.add_parser("query", help="ask one source; its argv comes from the machine, invocation or flags layer")
    ask.add_argument("--source", required=True, metavar="ID", help="id of a source of [orch.research.sources]")
    ask.add_argument("--query-file", required=True, type=Path, metavar="FILE", help="the query text")
    ask.add_argument("--json", action="store_true", help="{source, text, sources, raw_ref}")
    command = verbs.add_parser("stubs", help="additional instructions of the roles: publish the files, list them, show one")
    actions = command.add_subparsers(dest="action", required=True)
    publish = actions.add_parser("publish", help="create the missing stub files (never overwrites one)")
    publish.add_argument("--scope", choices=("project", "machine"), default="project",
                         help="project: local/stubs of the project in its workspace, else <project>/.swissknifeman/stubs (default); machine: ~/.local/share/swissknifeman/config/stubs")
    publish.add_argument("--dry-run", action="store_true", help="say what would be created, write nothing")
    publish.add_argument("--json", action="store_true")
    listing = actions.add_parser("list", help="the effective stubs of every role (read-only)")
    listing.add_argument("--json", action="store_true")
    show = actions.add_parser("show", help="the block one role gets and where each part comes from")
    show.add_argument("role", metavar="ROLE")
    show.add_argument("--provider", metavar="P", help="include this provider's stub variant")
    show.add_argument("--model", metavar="M", help="also include the model family's variant (requires --provider)")
    show.add_argument("--json", action="store_true")
    command = verbs.add_parser("doctor", help="diagnose the project: the conductor files git must ignore or keep")
    command.add_argument("--json", action="store_true", help="check-result/v1 documents as a JSON list")
    args = parser.parse_args(argv)
    if args.verb == "doctor":
        return _doctor(args)
    if args.verb == "stubs":
        return _stubs(args)
    if args.verb == "source":
        return _source_command(args)
    if args.verb == "research":
        return _research(args)
    if args.verb == "policy":
        return _policy(args)
    if args.verb == "route":
        return _route_explain(args)
    if args.verb == "conformance":
        return _conformance(args)
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
    if args.kind in conductor_contract.KINDS or args.kind in conductor_records.KINDS:
        # the closed documents of the conductor (schemas/conductor/v1) and its run records (schemas/records/v1)
        found = (conductor_contract.problems(doc, args.kind) if args.kind in conductor_contract.KINDS
                 else conductor_records.problems(doc, args.kind))
        for line in found:
            print(f"SCHEMA_INVALID: {line}", file=sys.stderr)
        if not args.quiet:
            print(json.dumps([{"path": line.split(": ", 1)[0], "code": "SCHEMA_INVALID",
                               "message": line.split(": ", 1)[-1], "level": "error"} for line in found]
                             if found else {"valid": True}, ensure_ascii=False))
        return 1 if found else 0
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
