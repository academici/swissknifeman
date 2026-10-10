"""External plan checks: plugins registered at the ``planner:check`` extension point.

``plan.py check`` calls the point after its own checks. The planner registers nothing: a plugin is registered in
the machine configuration of aicore (``[aicore.plugins.<id>]``). Without aicore, or with ``checks.external``
off, no plugin runs. Input and output follow ``schemas/check-plugin/v1``. A plugin that fails, times out or
answers with an invalid output is one ``EXTERNAL_CHECK_FAILED`` finding of the severity ``checks.external_failure``
names; it never stops the other plugins or the built-in checks.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, NamedTuple

from . import status

PLANNER_ROOT = Path(__file__).resolve().parents[3]
POINT = "planner:check"
MODULE = "planner"
SCHEMA_DIR = PLANNER_ROOT / "schemas" / "check-plugin" / "v1"
MAX_ISSUES = 500
FAILED = "EXTERNAL_CHECK_FAILED"


class Finding(NamedTuple):
    """One finding of the external checks, in the shape of a plan check issue."""

    level: str  # "error" | "warning"
    code: str
    where: str
    message: str


def planner_version() -> str:
    return json.loads((PLANNER_ROOT / "unit.json").read_text(encoding="utf-8"))["version"]


def build_input(*, plan_id: str, short_id: str, plan_dir: Path, plans_root: Path,
                project_root: Path | None) -> dict[str, Any]:
    """The input of the point for one plan (``input.schema.json``)."""
    from planner.plan import schema
    return {"plan_id": plan_id, "short_id": short_id, "plan_dir": str(Path(plan_dir).resolve()),
            "plans_root": str(Path(plans_root).resolve()),
            "project_root": None if project_root is None else str(Path(project_root).resolve()),
            "planner_version": planner_version(), "schema_urn_prefix": schema.SCHEMA_URN_PREFIX}


def output_problems(output: Any) -> list[str]:
    """Why ``output`` is not a valid ``output.schema.json`` document (empty when it is)."""
    from planner.plan import schema
    registry = schema.load_registry(SCHEMA_DIR)
    root, root_id = registry.resolve("urn:swissknifeman:planner:check-plugin:output:v1", "")
    problems = [issue.message for issue in schema.validate_node(registry, root, root_id, output)]
    if not problems and len(output["issues"]) > MAX_ISSUES:
        problems.append(f"/issues: more than {MAX_ISSUES} issues")
    return problems


def run_checks(plan_input: Mapping[str, Any], *, project: str | Path | None = None,
               failure: str = "warning") -> list[Finding]:
    """Call every plugin of ``planner:check`` and return their findings in plugin order.

    ``failure`` is the severity of ``EXTERNAL_CHECK_FAILED``. Returns nothing without aicore, without
    registered plugins, or when the call itself cannot be made (the reason is one ``EXTERNAL_CHECK_FAILED``).
    """
    if status()["aicore"] != "available":
        return []
    from aicore.ext import plugins
    from aicore.ext.errors import ExtError
    from aicore.ext.units import UnitDoc, discover_units
    from planner.plan import settings
    units = discover_units()
    if MODULE not in units:  # a standalone checkout: the module declares its own point
        unit_file = PLANNER_ROOT / "unit.json"
        units[MODULE] = UnitDoc(MODULE, PLANNER_ROOT, json.loads(unit_file.read_text(encoding="utf-8")))
    try:
        from aicore.ext import settings as ext_settings
        loaded = ext_settings.load(project, config_file=settings.invocation_file())
        registrations, _problems = plugins.registered_plugins(loaded, units=units)
        results = [plugins.invoke_one(registration, POINT, plan_input, project=project)
                   for registration in registrations
                   if registration.enabled and registration.manifest is not None
                   and registration.manifest.kind == "command" and POINT in registration.manifest.points]
    except ExtError as exc:
        return [Finding(failure, FAILED, "aicore", f"{exc.code}: {exc.message}")]
    findings: list[Finding] = []
    for result in results:
        findings.extend(_findings(result, failure))
    return findings


def _findings(result, failure: str) -> list[Finding]:
    if result.status == "skipped":
        return []
    if result.status != "ok":
        return [Finding(failure, FAILED, result.plugin, result.code or result.error or "the plugin failed")]
    problems = output_problems(result.output)
    if problems:
        return [Finding(failure, FAILED, result.plugin, f"INVALID_OUTPUT: {problems[0]}")]
    return [Finding(item["severity"], item["code"], item.get("path") or item.get("ref") or "plan",
                    f"[{result.plugin}] {item['message']}")
            for item in result.output["issues"]]
