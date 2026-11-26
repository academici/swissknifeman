"""Handler of the ext-demo sample extension (aicore plugin protocol 1, stdlib only). It writes nothing to disk.

ext-demo.items answers a two-row list; ext-demo.flaky always breaks the protocol (garbage on stdout), which the
backend counts as a plugin failure; ext-demo.note answers ok.
"""
import hashlib
import json
import sys
from pathlib import Path

manifest = json.loads((Path(__file__).resolve().parent.parent / "extension.json").read_text(encoding="utf-8"))
request = json.load(sys.stdin)


def reply(status="ok", **fields):
    document = {"$schema": "urn:swissknifeman:aicore:plugin-response:v1", "protocol": "1",
                "request_id": request.get("request_id", "0" * 32), "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document))


if request.get("protocol") != "1":
    reply("error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "protocol 1 only"})
elif request.get("op") == "describe":
    provides = json.dumps(manifest["provides"], sort_keys=True, separators=(",", ":")).encode()
    reply(output={"$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1", "id": manifest["id"],
                  "kind": manifest["kind"], "version": manifest["version"],
                  "capabilities_digest": "sha256:" + hashlib.sha256(provides).hexdigest(), "transport": "stdio-json"})
else:
    given = request.get("input") if isinstance(request.get("input"), dict) else {}
    which = given.get("id")
    if which == "ext-demo.flaky":
        sys.stdout.write("this is not a plugin response")
    elif which == "ext-demo.items":
        reply(output={"$schema": "urn:swissknifeman:gui:view-data:v1", "view": "resource-list",
                      "columns": [{"id": "name", "title": "Name", "type": "text"}],
                      "rows": [{"id": "alpha", "cells": {"name": "alpha"}}, {"id": "beta", "cells": {"name": "beta"}}],
                      "total": 2})
    else:
        reply(output={"ok": True})
