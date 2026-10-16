"""profiles — the project-type profiles delivered with skiller (read-only; --json)."""
import json

from aicore.util.cli import parse_flags
from aicore.util.term import die

SCHEMA = "urn:swissknifeman:skiller:profiles-list:v1"


def load_profiles(env):
    """Return {profile id: document} for every ``profiles/*.json`` of the module."""
    out = {}
    for path in sorted((env.root / "profiles").glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            die(f"profile {path.name} is unreadable: {exc}")
        if isinstance(doc, dict):
            out[path.stem] = doc
    return out


def cmd_profiles(env, argv):
    opts = parse_flags(argv, {"--json": "bool"})
    if opts["help"]:
        print("skiller profiles [--json]")
        return
    profiles = load_profiles(env)
    if opts["json"]:
        print(json.dumps({"$schema": SCHEMA, "profiles": profiles}, ensure_ascii=False,
                         indent=2, sort_keys=True))
        return
    for name, doc in profiles.items():
        print(f"{name:20} {doc.get('description', '')}")
