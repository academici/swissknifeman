"""Read-only admission of named source items; never claim, store a brief or start an agent."""
import argparse
from pathlib import Path

from orch import contracts
from orch.conductor import contract
from orch.worksource import PluginWorkSource, WorkSourceError
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.policies.routing import OPTIONAL_ROLES
from orch.conductor.infrastructure import launch_plan
from orch import launch


def inspect_items(conductor, args) -> dict:
    source = PluginWorkSource(conductor.settings.work_source, project=conductor.project,
                              env=conductor.env, config_file=conductor.config_file)
    conductor.run_id = "cnd-preflight"
    conductor.run_doc = {"options_file": str(args.options) if args.options else None,
                         "scenario": args.scenario, "fence": args.fence, "extra_paths": args.allow_path,
                         "grouped": args.batch}
    rows = []
    for ref in args.items:
        row = {"ref": ref, "admitted": False, "unavailable": {}, "optional_unavailable": {}}
        rows.append(row)
        try:
            inspected = source.inspect(plan=args.plan, plans_root=args.plans_root, ref=ref)
            if inspected["outcome"] != "ok":
                raise Stop(inspected["reason_code"], inspected["message"])
            invalid = [issue for issue in contracts.validate(inspected["input"], "execution-input") if issue.level == "error"]
            if invalid:
                raise Stop("BRIEF_INVALID", "; ".join(str(x) for x in invalid[:3]))
            claim = {key: inspected[key] for key in ("scenario", "options")}
            claim["route"] = (inspected["input"].get("route") or {}).get("minimum") or {}
            if args.scenario:
                claim["scenario"] = args.scenario
            item = Item(ref=ref, orch_run="-", state={}, directory=Path(), claim=claim,
                        input_doc=inspected["input"])
            unavailable = conductor.preview_routes(item)
            row.update(scenario=claim["scenario"], options=item.options, sources=item.sources,
                       routes=item.routes, route_notes=item.route_notes)
            executor, reviewer = item.routes.get("executor"), item.routes.get("reviewer")
            if (executor and reviewer and item.policy.get("review", {}).get("independent_provider")
                    and executor["provider"] == reviewer["provider"]):
                unavailable["reviewer"] = "BINDING_UNMET: independent_provider requires a different review provider"
            for role, route in item.routes.items():
                problem = conductor.admission(item, role, route)
                if problem:
                    unavailable[role] = problem
                # A preview has no private agent directory; validate the static guard requirements here.
                # Runtime still validates its actual scratch, output grants and authority before every launch.
                if route["provider"] == "antigravity" and launch.agy_role_opted_in(role, conductor.env):
                    problem = launch_plan.agy_launch_problem(route, str(conductor.project), role,
                                                             item.options["scope"]["extra_paths"])
                    if problem:
                        unavailable[role] = ": ".join(problem)
            optional = {key for key, value in unavailable.items()
                        if key in OPTIONAL_ROLES or value.startswith("POLICY_STAGE_SKIPPED:")}
            row["unavailable"] = {key: value for key, value in unavailable.items() if key not in optional}
            row["optional_unavailable"] = {key: value for key, value in unavailable.items() if key in optional}
            conductor.check_admission(item)
            row["admitted"] = not row["unavailable"]
        except (Stop, WorkSourceError) as error:
            row["unavailable"]["item"] = f"{error.code}: {error.message}"
    result = {"plan": args.plan, "admitted": bool(rows) and all(row["admitted"] for row in rows),
            "items": rows, "note": "Static admission only: no claims, artifacts or provider requests. "
            "Dependency readiness, live authentication/quota, delivered input and execution remain runtime checks."}
    invalid = contract.problems(result, "preflight-result")
    if invalid:
        raise Stop("PREFLIGHT_INVALID", "; ".join(invalid[:3]))
    return result


def add_parser(verbs) -> None:
    inspect = verbs.add_parser("preflight", help="read source items and check their actual routes before claiming any work")
    inspect.add_argument("--plan", required=True)
    inspect.add_argument("--items", nargs="+", required=True, metavar="REF")
    inspect.add_argument("--plans-root")
    inspect.add_argument("--options", type=Path)
    inspect.add_argument("--scenario")
    inspect.add_argument("--fence", choices=("project", "plan"))
    inspect.add_argument("--allow-path", action="append")
    inspect.add_argument("--batch", action=argparse.BooleanOptionalAction, default=None)
    inspect.set_defaults(frozen=False, dry_run=False, quiet=True)
