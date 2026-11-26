"""Release attestation commands: `skiller attest` and `skiller version`.

The attestation itself lives in aicore.release.attestation; this module binds it to the location of this
package (its prefix in the host root names the publication-version map and the skill sources released as
their own units) and keeps the historical names.
"""
import json
from pathlib import Path
import subprocess

from aicore.release import attestation as _attestation
from aicore.util.cli import parse_flags
from aicore.util.io import atomic_write_json
from aicore.util.repo import find_repo_root
from aicore.util.term import die
from aicore.util.proc import run as run_with_timeout

# Location of this Skiller package; its prefix in the host root names the
# publication-version map and the skill sources released as their own units.
PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def build(root, tag=None, *, ref=None):
    return _attestation.build(root, tag, ref=ref, package_root=PACKAGE_ROOT)


def check(root, value, *, previous_ref=None):
    return _attestation.check(root, value, previous_ref=previous_ref, package_root=PACKAGE_ROOT)


def cmd_attest(env, argv):
    opts = parse_flags(argv, {"--release": "str", "--previous": "str", "--check": "bool"})
    if opts["help"]:
        print("skiller attest [--release vX.Y.Z] [--previous vX.Y.Z] [--check]")
        return
    root = find_repo_root(env.root) or env.root
    try:
        value = build(root, opts["release"])
        path = root / "releases" / (value["umbrella"]["tag"] + ".json")
        errors = check(root, value, previous_ref=opts["previous"])
        if errors:
            die("; ".join(errors))
        if opts["check"]:
            if not path.is_file() or json.loads(path.read_text()) != value:
                die("RELEASE_ATTESTATION_STALE: " + str(path))
        else:
            atomic_write_json(path, value)
        print(f"{value['umbrella']['tag']}: {len(value['units'])} units; {path}")
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        die(f"RELEASE_ATTESTATION_INVALID: {exc}")


def cmd_version(env, argv):
    opts = parse_flags(argv, {"--json": "bool"})
    root = find_repo_root(env.root) or env.root
    value = build(root)
    result = run_with_timeout(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=60)
    value["umbrella"]["commit"] = result.stdout.strip() or "unknown"
    for unit in value["units"]:
        for projection in unit["providers"].values():
            projection.pop("files")
    if opts["json"]:
        print(json.dumps(value, ensure_ascii=False))
    else:
        print(f"swissknifeman {value['umbrella']['tag']} ({value['umbrella']['commit'][:12]})")
        for unit in value["units"]:
            print(f"  {unit['id']}@{unit['version']} {unit['tree_digest']}")
