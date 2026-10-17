#!/usr/bin/env python3
"""The plans migrator of the portable workspace: the plugin of the extension point ``workspace:plans-migrator`` (protocol 1).

The workspace module starts this file through ``aicore.ext.plugins`` with one request on stdin (``op: describe`` or
``op: invoke``) and reads one ``plugin-response/v1`` document from stdout. ``invoke`` carries one of three inputs (the
contract is ``schemas/plans-migrator/v1`` of the workspace module):

- ``inspect``: classify ``<project_root>/plans`` (v4 plans, legacy folders, loose top-level files), list every file with
  its size and sha256, name the items in progress and the symlinks that block a migration;
- ``apply``: the critical section of the migration (move the folders of the manifest into the workspace under the
  ``PlanLock`` of every plan, then switch the project marker); a refusal is an answer (``result: refused`` with ``code``,
  ``message`` and the ``phase`` it stopped at), never a protocol error;
- ``verify``: load the plans of a folder through the planner store and compare the errors of ``check`` with a baseline.

A long call (hundreds of megabytes) reports its progress on stderr. The bridge prints no file content and no secret:
answers hold paths relative to ``plans/``, sizes and digests. stdlib, aicore and the planner library only.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import partners

POINT = "workspace:plans-migrator"
RESPONSE = "urn:swissknifeman:aicore:plugin-response:v1"
DESCRIBE = "urn:swissknifeman:aicore:plugin-describe:v1"
OPS = ("inspect", "apply", "verify")


class InputInvalid(Exception):
    pass


def reply(request_id: str, status: str = "ok", **fields) -> None:
    document = {"$schema": RESPONSE, "protocol": "1", "request_id": request_id, "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document, ensure_ascii=False))


def describe(request_id: str) -> None:
    from aicore.util.digest import digest_json
    manifest = json.loads((partners.BRIDGE / "extension.json").read_text(encoding="utf-8"))
    reply(request_id, output={"$schema": DESCRIBE, "protocol": "1", "id": manifest["id"], "kind": manifest["kind"],
                              "version": manifest["version"], "capabilities_digest": digest_json(manifest["provides"]),
                              "transport": "stdio-json"})


def _folder(fields: dict, key: str) -> Path:
    value = fields.get(key)
    path = Path(value) if isinstance(value, str) and value else None
    if path is None or not path.is_absolute() or not path.is_dir():
        raise InputInvalid(f"{key} must be an existing absolute folder")
    return path


def op_inspect(fields: dict) -> dict:
    import inspector
    root = _folder(fields, "project_root")
    return inspector.inspect(root, inspector.stderr_progress)


def op_apply(fields: dict) -> dict:
    import apply
    return apply.run(fields)


def op_verify(fields: dict) -> dict:
    import verify
    plans_root = _folder(fields, "plans_root")
    baseline = fields.get("compare_to")
    baseline_root = _folder(fields, "compare_to") if baseline is not None else None
    return verify.compare_roots(plans_root, baseline_root, unbound=bool(fields.get("unbound", False)),
                                baseline_unbound=bool(fields.get("compare_to_unbound", False)))


def invoke(request_id: str, request: dict) -> None:
    fields = request.get("input")
    if request.get("point") != POINT or not isinstance(fields, dict) or fields.get("op") not in OPS:
        reply(request_id, "error", error={"code": "INPUT_INVALID",
                                          "message": f"expected point {POINT} with op {' | '.join(OPS)}"})
        return
    handler = {"inspect": op_inspect, "apply": op_apply, "verify": op_verify}[fields["op"]]
    try:
        output = handler(fields)
    except InputInvalid as exc:
        reply(request_id, "error", error={"code": "INPUT_INVALID", "message": str(exc)})
        return
    except OSError as exc:
        reply(request_id, "error", error={"code": "MIGRATION_IO_ERROR",
                                          "message": exc.strerror or exc.__class__.__name__})
        return
    reply(request_id, output=output)


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except ValueError:
        reply("0" * 32, "error", error={"code": "REQUEST_INVALID", "message": "the request is not JSON"})
        return 0
    request_id = request.get("request_id") if isinstance(request, dict) else None
    request_id = request_id if isinstance(request_id, str) and request_id else "0" * 32
    if not isinstance(request, dict) or request.get("protocol") != "1":
        reply(request_id, "error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "this plugin speaks protocol 1"})
        return 0
    try:
        partners.use_aicore()
        if request.get("op") == "describe":
            describe(request_id)
        elif request.get("op") == "invoke":
            invoke(request_id, request)
        else:
            reply(request_id, "error", error={"code": "OP_UNSUPPORTED", "message": "op is describe or invoke"})
    except SystemExit as stop:  # a partner was not found: partners printed CODE: message on stderr
        code = {2: "AICORE_NOT_FOUND", 3: "BRIDGE_PARTNER_UNAVAILABLE"}.get(stop.code, "PLUGIN_FAILED")
        reply(request_id, "error", error={"code": code, "message": f"{code}: see the plugin's stderr"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
