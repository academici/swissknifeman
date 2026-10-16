"""E2E handler of the demo unit (aicore plugin protocol 1, stdlib only)."""
import hashlib
import json
import sys
from pathlib import Path

manifest = json.loads((Path(__file__).resolve().parent / "extension.json").read_text(encoding="utf-8"))
request = json.load(sys.stdin)
reply = {"$schema": "urn:swissknifeman:aicore:plugin-response:v1", "protocol": "1",
         "request_id": request.get("request_id", "0" * 32)}
if request.get("protocol") != "1":
    reply.update(status="error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "protocol 1 only"})
elif request.get("op") == "describe":
    provides = json.dumps(manifest["provides"], sort_keys=True, separators=(",", ":")).encode()
    reply.update(status="ok", output={"$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1",
                                      "id": manifest["id"], "kind": manifest["kind"], "version": manifest["version"],
                                      "capabilities_digest": "sha256:" + hashlib.sha256(provides).hexdigest(),
                                      "transport": "stdio-json"})
else:
    reply.update(status="ok", output={"$schema": "urn:swissknifeman:gui:view-data:v1", "view": "metric-group",
                                      "metrics": [{"id": "demo-ready", "label": "Demo ready", "value": 1,
                                                   "status": "ok"}]})
sys.stdout.write(json.dumps(reply))
