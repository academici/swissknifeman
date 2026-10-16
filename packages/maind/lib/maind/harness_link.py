"""maind's link to harness: its public JSON commands, found through ``aicore.util.partners``.

maind never imports harness and never names a harness path. What it needs from harness is data
(the MCP catalog and bindings, the Codex observer fragment, a profile resolution, the instruction
scopes) and two services (validating a composed hooks document, running an instruction
operation). Pure rendering lives in ``aicore.provider.mcp``. Without harness every function raises
``PartnerUnavailable`` (message ``PARTNER_UNAVAILABLE: harness not found ...``); callers skip their
provider steps.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aicore.artifacts.artifact import ArtifactSource
from aicore.provider.mcp import parse_mcp_catalog, plan_mcp_projection
from aicore.util.partners import (PartnerError, PartnerUnavailable, partner_command,
                                  require_partner, run_partner_json)

PARTNER = "harness"
LEGACY_ENV = ("MAIND_HARNESS_BIN",)
TIMEOUT = 300

__all__ = ["PartnerError", "PartnerUnavailable", "available", "base_projections", "clear_cache",
           "instruction_scopes", "mcp_catalog", "observer_fragment", "resolve_profile",
           "run_instructions", "validate_codex_lifecycle", "InstructionOutcome", "InstructionTarget",
           "ObserverFragment"]

_cache: dict = {}


def available() -> bool:
    return partner_command(PARTNER, legacy_env=LEGACY_ENV) is not None


def clear_cache() -> None:
    _cache.clear()


def _key(args) -> tuple:
    return tuple(require_partner(PARTNER, legacy_env=LEGACY_ENV)) + tuple(args)


def _json(args, *, cached: bool = False):
    if cached:
        key = _key(args)
        if key not in _cache:
            _cache[key] = run_partner_json(PARTNER, args, legacy_env=LEGACY_ENV, timeout=TIMEOUT)
        return _cache[key]
    return run_partner_json(PARTNER, args, legacy_env=LEGACY_ENV, timeout=TIMEOUT)


def _field(document, name: str, kind, command: str):
    value = document.get(name) if isinstance(document, dict) else None
    if not isinstance(value, kind):
        raise PartnerError(f"PARTNER_BAD_OUTPUT: {PARTNER} {command} output lacks {name}")
    return value


def mcp_catalog() -> dict:
    """``harness mcp catalog --json``: catalog, per-provider bindings, lock sources, adapters."""
    document = _json(["mcp", "catalog", "--json"], cached=True)
    for name, kind in (("catalog", dict), ("bindings", dict), ("sources", dict), ("adapters", dict)):
        _field(document, name, kind, "mcp")
    return document


def base_projections(providers) -> tuple:
    """The empty-selection native projection of each provider, from harness data."""
    document = mcp_catalog()
    catalog = parse_mcp_catalog(document["catalog"])
    rows = []
    for provider in providers:
        bindings = document["bindings"].get(provider.value)
        if bindings is None:
            raise ValueError("HARNESS_MAPPING_MISSING")
        rows.append(plan_mcp_projection(catalog, provider_id=provider, bindings=bindings,
                                        selected=(), trusted=True))
    return tuple(rows)


@dataclass(frozen=True)
class ObserverFragment:
    """The native Codex observer registration and its companion handler."""
    target_path: str
    event: str
    group: dict
    handler_bytes: bytes
    source: ArtifactSource


def observer_fragment() -> ObserverFragment:
    """``harness hooks codex-lifecycle fragment --json``."""
    document = _json(["hooks", "codex-lifecycle", "fragment", "--json"], cached=True)
    fragment = _field(document, "fragment", dict, "hooks")
    source = _field(fragment, "source", dict, "hooks")
    try:
        return ObserverFragment(
            _field(fragment, "target_path", str, "hooks"), _field(fragment, "event", str, "hooks"),
            _field(fragment, "group", dict, "hooks"),
            _field(fragment, "handler", str, "hooks").encode("utf-8"),
            ArtifactSource(source["id"], source["path"], source["sha256"]))
    except (KeyError, TypeError, ValueError) as error:
        raise PartnerError(f"PARTNER_BAD_OUTPUT: {PARTNER} hooks fragment source: {error}") from error


def validate_codex_lifecycle(document: bytes, memory_command: str) -> None:
    """``harness hooks codex-lifecycle validate``; a refusal raises ``ValueError(<code>)``."""
    with tempfile.TemporaryDirectory(prefix="maind-lifecycle-") as scratch:
        path = Path(scratch) / "hooks.json"
        path.write_bytes(document)
        result = _json(["hooks", "codex-lifecycle", "validate", "--document", str(path),
                        "--memory-command", memory_command, "--json"])
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        raise PartnerError(f"PARTNER_BAD_OUTPUT: {PARTNER} hooks validate output lacks ok")
    if not result["ok"]:
        raise ValueError(result.get("code") or "HARNESS_D104_LIFECYCLE_INVALID")


def resolve_profile(provider_id: str, profile_id: str, *, target_scope: str, trusted: bool,
                    operation_id=None, target_identity=None, origin: str = "operation",
                    enabled: bool = True) -> dict:
    """``harness profiles resolve --json``: ``{"green": bool, "diagnostics": [{"code", ...}]}``."""
    args = ["profiles", "resolve", "--provider", provider_id, "--profile", profile_id,
            "--target-scope", target_scope, "--origin", origin, "--json"]
    if trusted:
        args.append("--trusted")
    if not enabled:
        args.append("--disabled")
    if operation_id:
        args += ["--operation-id", operation_id]
    if target_identity:
        args += ["--target-identity", target_identity]
    result = _json(args)
    _field(result, "green", bool, "profiles")
    _field(result, "diagnostics", list, "profiles")
    return result


def instruction_scopes() -> dict:
    """``harness instructions scopes --json``: scope ids in catalog order and the versions."""
    document = _json(["instructions", "scopes", "--json"], cached=True)
    _field(document, "scopes", list, "instructions")
    return document


@dataclass(frozen=True)
class InstructionTarget:
    scope_id: str
    provider_id: str
    target_path: str
    observation: str
    action: str
    changed: bool
    diagnostics: tuple
    observed_hash: str | None
    ordered_semantic_ids: tuple


@dataclass(frozen=True)
class InstructionOutcome:
    """The JSON result of ``harness instructions <operation> --json``."""
    provider_ids: tuple
    targets: tuple
    diagnostics: tuple
    green: bool

    @classmethod
    def from_document(cls, document) -> "InstructionOutcome":
        request = _field(document, "request", dict, "instructions")
        targets = tuple(InstructionTarget(
            row["scope_id"], row["provider_id"], row["target_path"], row["observation"],
            row["action"], bool(row["changed"]),
            tuple(item["code"] for item in row["diagnostics"]), row.get("observed_hash"),
            tuple(row["ordered_semantic_ids"]))
            for row in _field(document, "targets", list, "instructions"))
        diagnostics = tuple(item["code"] for item in _field(document, "diagnostics", list, "instructions"))
        return cls(tuple(_field(request, "provider_ids", list, "instructions")), targets,
                   diagnostics, _field(document, "green", bool, "instructions"))

    @property
    def planned(self) -> bool:
        """False when the request itself was refused before any target was planned."""
        return bool(self.targets)

    def writable_paths(self) -> tuple:
        """Target paths a write must be authorized for, in the order the plan applies them."""
        return tuple(sorted(row.target_path for row in self.targets if row.action != "noop"))

    def drift_hashes(self) -> tuple:
        return tuple((row.target_path, row.observed_hash) for row in sorted(
            self.targets, key=lambda row: row.target_path)
            if row.observation == "managed-drift" and row.observed_hash)


def run_instructions(operation: str, target, *, scope_ids, provider_ids, authorized=(),
                     observed=()) -> InstructionOutcome:
    """Run ``harness instructions <operation> --json``; a non-green result is data, not an error."""
    args = ["instructions", operation, "--target", str(target), "--scope", ",".join(scope_ids),
            "--provider", ",".join(provider_ids), "--json"]
    if authorized:
        args += ["--authorize", ",".join(authorized)]
    if observed:
        args += ["--observed-hash", ",".join(f"{path}={digest}" for path, digest in observed)]
    if operation == "repair":
        args += ["--preimage-dir", "adjacent-backup"]
    argv = require_partner(PARTNER, legacy_env=LEGACY_ENV) + args
    done = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    if done.returncode not in (0, 1):
        tail = (done.stderr.strip().splitlines() or [""])[-1]
        raise PartnerError(f"PARTNER_FAILED: {PARTNER} instructions exited {done.returncode}: {tail}")
    try:
        document = json.loads(done.stdout)
    except json.JSONDecodeError as error:
        raise PartnerError(f"PARTNER_BAD_OUTPUT: {PARTNER} instructions: {error}") from error
    try:
        return InstructionOutcome.from_document(document)
    except (KeyError, TypeError) as error:
        raise PartnerError(f"PARTNER_BAD_OUTPUT: {PARTNER} instructions: {error}") from error
