#!/usr/bin/env python3
"""A fake MCP stdio server for the research tests (JSON-RPC lines: initialize, tools/list, tools/call).

Usage: fake_mcp.py [--tool NAME] [--busy-file FILE --busy N] [--sleep SECONDS] [--log FILE]
``--busy`` answers the first N tools/call requests with BROWSER_BUSY (the count lives in ``--busy-file``, so it
survives a restart of the server: the client starts a new process for every attempt); ``--sleep`` delays every
tools/call. The shape of the messages follows packages/orch/docs/research/tools/pplx_stdio.py.
"""
import argparse
import json
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--tool", default="search")
parser.add_argument("--busy", type=int, default=0)
parser.add_argument("--busy-file")
parser.add_argument("--sleep", type=float, default=0)
parser.add_argument("--log")
options = parser.parse_args()


def reply(msg_id, result=None, error=None):
    doc = {"jsonrpc": "2.0", "id": msg_id}
    doc["error" if error else "result"] = error or result
    sys.stdout.write(json.dumps(doc) + "\n")
    sys.stdout.flush()


def busy_now():
    if not options.busy_file:
        return False
    try:
        with open(options.busy_file, encoding="utf-8") as fh:
            used = int(fh.read() or 0)
    except OSError:
        used = 0
    with open(options.busy_file, "w", encoding="utf-8") as fh:
        fh.write(str(used + 1))
    return used < options.busy


sys.stdout.write("starting fake server (not JSON)\n")
sys.stdout.flush()
for line in sys.stdin:
    msg = json.loads(line)
    method, msg_id = msg.get("method"), msg.get("id")
    if options.log:
        with open(options.log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(msg) + "\n")
    if method == "initialize":
        reply(msg_id, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                       "serverInfo": {"name": "fake-mcp", "version": "1"}})
    elif method == "tools/list":
        reply(msg_id, {"tools": [{"name": options.tool}]})
    elif method == "tools/call":
        time.sleep(options.sleep)
        params = msg["params"]
        if params["name"] != options.tool:
            reply(msg_id, error={"code": -32602, "message": "unknown tool " + params["name"]})
        elif busy_now():
            reply(msg_id, {"isError": True, "content": [{"type": "text", "text": "BROWSER_BUSY: no free tab"}]})
        else:
            query = params["arguments"]["query"]
            reply(msg_id, {"content": [{"type": "text", "text": f"Answer to: {query}\nSee https://example.org/a and "
                                                              "https://example.org/b, again https://example.org/a."}]})
