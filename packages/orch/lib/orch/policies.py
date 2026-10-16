"""Run-policy packs: discovery, loading and the test cases that ship with them (docs/run-policies.md).

A pack is a folder ``<policy_id>/`` holding ``policy.json`` (a run-policy with a ``version``) and
``cases/<case>.json``. The packs shipped with orch come first; folders listed in ``profiles.dirs`` follow in order,
and the first pack with an id wins.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import json
from pathlib import Path
import re
import sys
import tempfile

from orch import catalog as _catalog
from orch import contracts, render
from orch.bindings import BINDINGS
from orch.port import PortError
from orch.settings import ORCH_ROOT, Settings

SHIPPED_DIR = ORCH_ROOT / "configs" / "run-policies"
POLICY_FILE = "policy.json"
CASES_DIR = "cases"
POLICY_ID = re.compile(r"^[a-z][a-z0-9-]*$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
CASE_KEYS = {"description", "input", "provider", "binding", "expect"}
EXPECT_KEYS = {"result", "error", "stages", "refusals", "policy_decision"}


class PolicyError(Exception):
    """``POLICY_UNKNOWN`` for an id without a pack, ``POLICY_INVALID`` for a pack that does not hold together."""

    def __init__(self, code: str, message: str, issues: list | None = None):
        super().__init__(message)
        self.code = code
        self.issues = issues or []


def _stderr_warning(message: str) -> None:
    print(message, file=sys.stderr)


def discover(settings: Settings, *, warn: Callable[[str], None] = _stderr_warning) -> dict[str, Path]:
    """Pack folders by policy id, in discovery order.

    A repeated id keeps the first pack and warns ``POLICY_SHADOWED``; a listed folder that is missing warns
    ``POLICY_DIR_MISSING``. A subfolder without ``policy.json`` or with a name that is not an id is not a pack.
    """
    found: dict[str, Path] = {}
    for base in (SHIPPED_DIR, *settings.profiles_dirs):
        if not base.is_dir():
            if base != SHIPPED_DIR:
                warn(f"POLICY_DIR_MISSING: {base} is not a folder")
            continue
        for pack in sorted(base.iterdir()):
            if not (pack / POLICY_FILE).is_file() or not POLICY_ID.match(pack.name):
                continue
            if pack.name in found:
                warn(f"POLICY_SHADOWED: {pack.name} in {base} is shadowed by {found[pack.name].parent}")
            else:
                found[pack.name] = pack
    return found


def _read_json(path: Path, what: str) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PolicyError("POLICY_INVALID", f"cannot read {what} {path}: {error}") from error
    if not isinstance(doc, dict):
        raise PolicyError("POLICY_INVALID", f"{what} {path} is not a JSON object")
    return doc


def _locate(policy_id: str, settings: Settings, warn: Callable[[str], None]) -> Path:
    pack = discover(settings, warn=warn).get(policy_id)
    if pack is None:
        raise PolicyError("POLICY_UNKNOWN", f"no run-policy pack {policy_id!r}")
    return pack


def _load_pack(pack: Path) -> dict:
    doc = _read_json(pack / POLICY_FILE, "policy")
    issues = [issue._asdict() for issue in contracts.validate(doc, "run-policy") if issue.level == "error"]
    if issues:
        raise PolicyError("POLICY_INVALID", f"{pack / POLICY_FILE} does not match exec/v1 run-policy", issues)
    if doc["policy_id"] != pack.name:
        raise PolicyError("POLICY_INVALID", f"policy_id {doc['policy_id']!r} differs from the pack folder {pack.name!r}")
    if not SEMVER.match(str(doc.get("version", ""))):
        raise PolicyError("POLICY_INVALID", f"{pack / POLICY_FILE} needs a semantic version (MAJOR.MINOR.PATCH)")
    return doc


def load(policy_id: str, settings: Settings, *, warn: Callable[[str], None] = _stderr_warning) -> dict:
    """The run-policy of a pack. ``POLICY_UNKNOWN`` without a pack, ``POLICY_INVALID`` for an invalid one."""
    return _load_pack(_locate(policy_id, settings, warn))


def describe(policy_id: str, settings: Settings, *, warn: Callable[[str], None] = _stderr_warning) -> dict:
    """``{policy_id, version, description, source, cases}`` of a pack (for ``policy list``)."""
    pack = _locate(policy_id, settings, warn)
    doc = _load_pack(pack)
    return {"policy_id": policy_id, "version": doc["version"], "description": doc["description"],
            "source": "shipped" if pack.parent == SHIPPED_DIR else str(pack.parent),
            "cases": len(_case_files(pack))}


def _case_files(pack: Path) -> list[Path]:
    return sorted((pack / CASES_DIR).glob("*.json"))


def _check_case(case: dict, path: Path) -> None:
    unknown = sorted(set(case) - CASE_KEYS)
    expect = case.get("expect")
    if unknown or not isinstance(case.get("input"), str) or not isinstance(expect, dict) \
            or expect.get("result") not in ("ok", "refused") or set(expect) - EXPECT_KEYS \
            or case.get("binding", "native") not in BINDINGS:
        raise PolicyError("POLICY_INVALID", f"case {path} needs input, expect.result (ok|refused), a known binding "
                          f"and only the keys {sorted(CASE_KEYS)} / {sorted(EXPECT_KEYS)}")


def _input_path(name: str, pack: Path) -> Path:
    """An input reference: absolute, else relative to the pack, else relative to the orch package."""
    path = Path(name)
    if path.is_absolute():
        return path
    return pack / path if (pack / path).is_file() else ORCH_ROOT / path


def _prepare(case: dict, pack: Path, policy: dict, catalog: _catalog.Catalog, roles: Mapping[str, dict]) -> dict:
    """What a dry-run preparation of the case yields: ``{result, error, stages, refusals, policy_decision}``."""
    input_doc = _read_json(_input_path(case["input"], pack), "input")
    with tempfile.TemporaryDirectory(prefix="orch-case-") as out:
        engine = BINDINGS[case.get("binding", "native")](out, catalog=catalog)
        try:
            plan, code = engine.prepare(input_doc, policy, roles, provider=case.get("provider"), dry_run=True), None
        except PortError as error:
            plan, code = error.data.get("launch_plan") or {}, error.code
    decision = (plan.get("policy_decision") or {}).get("decision") or ("allow" if code is None else "refuse")
    return {"result": "ok" if code is None else "refused", "error": code,
            "stages": [stage["stage_id"] for stage in plan.get("stages", [])],
            "refusals": [{"stage_id": item["stage_id"], "capability": item["capability"]}
                         for item in plan.get("refusals", [])],
            "policy_decision": decision}


def run_cases(policy_id: str, settings: Settings, *, model_catalog: str | Path | None = None,
              warn: Callable[[str], None] = _stderr_warning) -> list[dict]:
    """Run the cases of a pack through a dry-run preparation and compare each with its expectation.

    One row per case: ``{policy_id, case, status: pass|fail, differences}``. A pack without cases is one failed row.
    The model catalog is the one packaged with aicore unless ``model_catalog`` names another.
    """
    pack = _locate(policy_id, settings, warn)
    policy = _load_pack(pack)
    files = _case_files(pack)
    if not files:
        return [{"policy_id": policy_id, "case": None, "status": "fail",
                 "differences": [{"field": "cases", "expected": "at least one case", "actual": "none"}]}]
    try:
        catalog = _catalog.Catalog.load(model_catalog)
    except _catalog.CatalogError as error:
        raise PolicyError("POLICY_INVALID", f"{error.code}: {error}") from error
    roles = render.load_roles()
    rows = []
    for path in files:
        case = _read_json(path, "case")
        _check_case(case, path)
        actual = _prepare(case, pack, policy, catalog, roles)
        differences = [{"field": key, "expected": value, "actual": actual[key]}
                       for key, value in case["expect"].items() if actual[key] != value]
        rows.append({"policy_id": policy_id, "case": path.stem, "status": "fail" if differences else "pass",
                     "differences": differences})
    return rows
