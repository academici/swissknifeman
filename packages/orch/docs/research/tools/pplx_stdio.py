#!/usr/bin/env python3
"""Minimal stdio MCP client for the local perplexity-web-mcp server (default pool).

Use when the perplexity-web MCP server is not attached to the current agent session.
Usage:
  pplx_stdio.py list
  pplx_stdio.py <search|search_advanced|search_deep> <query.txt> <out.json>
Server path: $PERPLEXITY_WEB_MCP_BIN or ~/projects/packages/perplexity-web-mcp/start.sh.
The out.json keeps the query, UTC timestamps and the unmodified tool result.
"""
import json
import os
import subprocess
import sys
import time

BIN = os.environ.get("PERPLEXITY_WEB_MCP_BIN",
                     os.path.expanduser("~/projects/packages/perplexity-web-mcp/start.sh"))


def main(argv):
    proc = subprocess.Popen([BIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv(msg_id):
        while True:
            line = proc.stdout.readline()
            if not line:
                raise SystemExit("server closed stdout")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == msg_id:
                return msg

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "pplx-stdio", "version": "1"}}})
        recv(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        if argv[1] == "list":
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            print(json.dumps(recv(2), ensure_ascii=False, indent=1))
            return 0
        tool, query_file, out_file = argv[1], argv[2], argv[3]
        query = open(query_file, encoding="utf-8").read().strip()
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": tool, "arguments": {"query": query}}})
        reply = recv(3)
        doc = {"route": f"perplexity-web-mcp stdio, default pool; {tool}", "started": started,
               "completed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "query": query, "result": reply.get("result", reply)}
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
        text = "".join(c.get("text", "") for c in doc["result"].get("content", []))
        print(text or json.dumps(doc["result"], ensure_ascii=False))
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
