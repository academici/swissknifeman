"""Test handler of the qdemo queries (aicore plugin protocol 1, stdlib only)."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
manifest = json.loads((HERE / "extension.json").read_text(encoding="utf-8"))
request = json.load(sys.stdin)


def reply(status="ok", **fields):
    document = {"$schema": "urn:swissknifeman:aicore:plugin-response:v1", "protocol": "1",
                "request_id": request["request_id"], "status": status}
    document.update(fields)
    sys.stdout.write(json.dumps(document))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


VIEW = "urn:swissknifeman:gui:view-data:v1"
if request.get("protocol") != "1":
    reply("error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "this handler speaks protocol 1"})
    sys.exit(0)
if request["op"] == "describe":
    reply(output={"$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1", "id": manifest["id"],
                  "kind": manifest["kind"], "version": manifest["version"],
                  "capabilities_digest": "sha256:" + hashlib.sha256(canonical(manifest["provides"])).hexdigest(),
                  "transport": "stdio-json"})
    sys.exit(0)
given = request.get("input") if isinstance(request.get("input"), dict) else {}
if os.environ.get("QDEMO_MARKS"):
    with open(os.environ["QDEMO_MARKS"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"input": given, "project_root": request["context"]["project_root"]}) + "\n")
query = given.get("id")
if query == "qdemo.items":
    rows = [{"id": "r1", "cells": {"name": given.get("params", {}).get("filter", "all")}}]
    reply(output={"$schema": VIEW, "view": "resource-list", "columns": [{"id": "name", "title": "Name", "type": "text"}],
                  "rows": rows, "total": 1})
elif query == "qdemo.metrics":
    reply(output={"$schema": VIEW, "view": "metric-group",
                  "metrics": [{"id": "count", "label": "Count", "value": 3, "status": "ok"}]})
elif query == "qdemo.wrong-view":
    reply(output={"$schema": VIEW, "view": "metric-group", "metrics": []})
elif query == "qdemo.broken":
    reply(output={"view": "resource-list"})
elif query == "qdemo.fails":
    reply("error", error={"code": "QDEMO_BROKEN", "message": "the demo fails on purpose"})
elif query == "qdemo.slow":
    time.sleep(5)
    reply(output={"$schema": VIEW, "view": "metric-group", "metrics": []})
elif query == "qdemo.secret":
    secret = os.environ.get("SKM_TEST_SECRET", "")
    reply(output={"$schema": VIEW, "view": "metric-group",
                  "metrics": [{"id": "leak", "label": "token " + secret, "value": 1, "status": "ok"}]})
else:
    reply("error", error={"code": "QDEMO_UNKNOWN", "message": "unknown query"})
