"""A throwaway external extension with a GUI contribution, for the plugin tests (stdlib only).

``make_extension`` writes the extension folder (``extension.json``, ``gui.json``, a handler whose behaviour follows the
file ``mode`` next to it, ``bin/sleeper``); ``register`` writes the machine configuration that enables and trusts it
for aicore (``[aicore.plugins.<id>]``), the precondition of starting an extension (D24).
"""
import json
import os
from pathlib import Path

EXT_ID = "xext"
VIEW = "urn:swissknifeman:gui:view-data:v1"

HANDLER = r'''"""Handler of the xext test extension (aicore plugin protocol 1, stdlib only); behaviour: the file ``mode``."""
import hashlib
import json
import sys
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


if request.get("protocol") != "1":
    reply("error", error={"code": "PROTOCOL_UNSUPPORTED", "message": "this handler speaks protocol 1"})
    sys.exit(0)
if request["op"] == "describe":
    reply(output={"$schema": "urn:swissknifeman:aicore:plugin-describe:v1", "protocol": "1", "id": manifest["id"],
                  "kind": manifest["kind"], "version": manifest["version"],
                  "capabilities_digest": "sha256:" + hashlib.sha256(canonical(manifest["provides"])).hexdigest(),
                  "transport": "stdio-json"})
    sys.exit(0)
try:
    mode = (HERE / "mode").read_text(encoding="utf-8").strip()
except OSError:
    mode = "ok"
given = request.get("input") if isinstance(request.get("input"), dict) else {}
if mode == "garbage":
    sys.stdout.write("this is not a plugin response")
elif mode == "domain":
    reply("error", error={"code": "XEXT_DOMAIN", "message": "a domain error of the plugin"})
elif mode == "badview":
    reply(output={"view": "metric-group"})
elif given.get("id") == "xext.status":
    reply(output={"$schema": "urn:swissknifeman:gui:view-data:v1", "view": "metric-group",
                  "metrics": [{"id": "up", "label": "Up", "value": 1, "status": "ok"}]})
else:
    reply(output={"done": True})
'''

SLEEPER = "#!/bin/sh\necho started\nsleep 1000 &\nwait\n"


def contribution(ext_id=EXT_ID, extra_effects=()):
    return {
        "$schema": "urn:swissknifeman:gui:contribution:v1", "owner": ext_id, "version": "0.1.0",
        "gui_protocol": {"min": "1", "max": "1"},
        "requires_contracts": [{"id": "urn:swissknifeman:gui:view-data", "version": "v1"}],
        "handler": {"extension": "extension.json"},
        "queries": [{"id": f"{ext_id}.status", "title": "Status", "scope": "fleet", "returns": "metric-group"}],
        "commands": [
            {"id": f"{ext_id}.net", "title": "Net", "scope": "fleet", "effects": ["network", *extra_effects],
             "risk": "low", "confirmation": "none", "timeout_s": 20, "exec": {"kind": "invoke"}},
            {"id": f"{ext_id}.sleep", "title": "Sleep", "scope": "fleet", "effects": ["process.spawn"],
             "risk": "low", "confirmation": "none", "timeout_s": 120, "supports": ["cancel"],
             "exec": {"kind": "argv", "argv": ["bin/sleeper"], "cwd": "owner"}},
        ],
    }


def make_extension(parent: Path, ext_id: str = EXT_ID, extra_effects=()) -> Path:
    root = Path(os.path.realpath(parent)) / ext_id
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / "extension.json").write_text(json.dumps({
        "$schema": "urn:swissknifeman:aicore:extension:v1", "id": ext_id, "kind": "command", "version": "0.1.0",
        "description": "Test extension with a GUI contribution.", "protocol": {"min": "1", "max": "1"},
        "entrypoint": ["python3", "handler.py"],
        "provides": {"points": ["gui:query", "gui:command"], "gui": "gui.json"}, "timeout_seconds": 30,
        "example_input": {"id": f"{ext_id}.status", "context": {}, "params": {}}}, indent=2), encoding="utf-8")
    (root / "gui.json").write_text(json.dumps(contribution(ext_id, extra_effects), indent=2), encoding="utf-8")
    (root / "handler.py").write_text(HANDLER, encoding="utf-8")
    (root / "bin" / "sleeper").write_text(SLEEPER, encoding="utf-8")
    (root / "bin" / "sleeper").chmod(0o755)
    return root


def set_mode(root: Path, mode: str) -> None:
    (Path(root) / "mode").write_text(mode, encoding="utf-8")


def register(skm_home: Path, root: Path, ext_id: str = EXT_ID, *, trusted: bool = True) -> None:
    """Enable (and trust) the extension in the machine layer of ``[aicore.plugins]``."""
    config = Path(skm_home) / "config" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(f'schema_version = 1\n\n[aicore.plugins.{ext_id}]\nmanifest = "{Path(root) / "extension.json"}"\n'
                      f'enabled = true\ntrusted = {"true" if trusted else "false"}\n', encoding="utf-8")
