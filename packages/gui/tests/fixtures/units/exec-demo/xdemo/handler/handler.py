"""Test handler of the xdemo invoke commands (aicore plugin protocol 1, stdlib only)."""
import hashlib
import json
import os
import sys
from pathlib import Path

manifest = json.loads((Path(__file__).resolve().parent / "extension.json").read_text(encoding="utf-8"))
request = json.load(sys.stdin)


def reply(status="ok", **fields):
    document = {"$schema": "urn:swissknifeman:aicore:plugin-response:v1", "protocol": "1",
                "request_id": request["request_id"], "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document))


if request.get("protocol") != "1":
    reply("error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "protocol 1 only"})
elif request["op"] == "describe":
    provides = json.dumps(manifest["provides"], sort_keys=True, separators=(",", ":")).encode()
    reply(output={"$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1", "id": manifest["id"],
                  "kind": manifest["kind"], "version": manifest["version"],
                  "capabilities_digest": "sha256:" + hashlib.sha256(provides).hexdigest(), "transport": "stdio-json"})
else:
    given = request.get("input") if isinstance(request.get("input"), dict) else {}
    if given.get("id") == "xdemo.broken":
        reply("error", error={"code": "XDEMO_BROKEN", "message": "fails on purpose"})
    else:
        name = (given.get("input") or {}).get("name", "nobody")
        reply(output={"greeting": f"hello {name}", "token": os.environ.get("SKM_TEST_SECRET", "")})
