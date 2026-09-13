"""Deterministic release identity over the bytes delivered by both providers."""
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import subprocess

from core import atomic_write_json, find_monorepo_root
from .common import SKILL_IGNORE, die, parse_flags


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def tree_digest(files):
    return digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


class Source:
    def __init__(self, root, ref=None):
        self.root, self.ref = Path(root), ref
        self.paths = None
        if ref:
            result = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref],
                                    cwd=root, check=True, capture_output=True, text=True)
            self.paths = result.stdout.splitlines()
        else:
            result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                    cwd=root, check=True, capture_output=True, text=True)
            self.paths = result.stdout.splitlines()

    def read(self, path):
        if self.ref:
            return subprocess.run(["git", "show", f"{self.ref}:{path}"], cwd=self.root,
                                  check=True, capture_output=True).stdout
        candidate = self.root / path
        if not candidate.resolve().is_relative_to(self.root.resolve()):
            raise ValueError(f"RELEASE_PATH_UNCONTAINED: {path}")
        return candidate.read_bytes()

    def json(self, path):
        return json.loads(self.read(path))

    def files(self, prefix, *, ignore=SKILL_IGNORE):
        prefix = str(Path(prefix)).removeprefix("./")
        if self.paths is not None:
            paths = [p for p in self.paths if p == prefix or p.startswith(prefix + "/")]
        else:
            candidate = self.root / prefix
            paths = ([prefix] if candidate.is_file() else
                     [p.relative_to(self.root).as_posix() for p in candidate.rglob("*")
                      if p.is_file()])
        return sorted(p for p in paths if not any(
            fnmatch.fnmatch(part, pattern) for part in Path(p).parts[len(Path(prefix).parts):]
            for pattern in ignore))


def surface(source, root, roots, *, manifest=None):
    paths = set()
    for folder in roots:
        path = (Path(root) / folder).as_posix()
        paths.update(source.files(path, ignore=SKILL_IGNORE + ("tests", ".git", "node_modules")))
    if manifest:
        paths.add((Path(root) / manifest).as_posix())
    files = {Path(p).relative_to(root).as_posix(): digest(source.read(p))
             for p in sorted(paths)}
    if not files:
        raise ValueError(f"RELEASE_SURFACE_EMPTY: {root}")
    return {"source": root, "files": files, "tree_digest": tree_digest(files)}


def build(root, tag=None, *, ref=None):
    source = Source(root, ref)
    changelog = source.read("CHANGELOG.md").decode()
    headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$",
                          changelog, re.M)
    if not headings:
        raise ValueError("RELEASE_CHANGELOG_MISSING")
    version, date = headings[0]
    if tag and tag != "v" + version:
        raise ValueError("RELEASE_VERSION_MISMATCH")
    codex = source.json(".agents/plugins/marketplace.json")
    claude = {p["name"]: p for p in source.json(".claude-plugin/marketplace.json")["plugins"]}
    units = []
    for entry in sorted(codex["plugins"], key=lambda e: e["name"]):
        name = entry["name"]
        raw = entry["source"]
        codex_root = (raw if isinstance(raw, str) else raw["path"]).removeprefix("./")
        manifest = source.json(codex_root + "/.codex-plugin/plugin.json")
        skill_roots = manifest["skills"]
        if isinstance(skill_roots, str):
            skill_roots = [skill_roots]
        providers = {"codex": surface(source, codex_root, skill_roots,
                                       manifest=".codex-plugin/plugin.json")}
        providers["codex-native"] = surface(source, codex_root, ["."],
                                              manifest=".codex-plugin/plugin.json")
        other = claude.get(name)
        if other:
            claude_root = str(Path(other["source"]))
            if "skills" in other:
                roots = other["skills"]
                claude_manifest = None
            else:
                claude_manifest = ".claude-plugin/plugin.json"
                declaration = source.json(claude_root + "/" + claude_manifest)
                if claude_root.startswith("packages/skiller/skills/"):
                    roots = ["."]
                else:
                    roots = ["lib", "scripts", "references", "configs", "runtime"]
                    for key in ("commands", "skills", "agents"):
                        value = declaration.get(key, [])
                        roots.extend([value] if isinstance(value, str) else value)
            providers["claude-code"] = surface(source, claude_root, roots,
                                                manifest=claude_manifest)
        if name == "core":
            providers["runtime"] = surface(source, "core", ["."],
                                            manifest=None)
        units.append({"id": name, "version": manifest["version"], "providers": providers,
                      "tree_digest": tree_digest({p: s["tree_digest"] for p, s in providers.items()})})
    for package in ("skiller", "harness", "maind", "analyst"):
        package_root = "packages/" + package
        metadata = source.json(package_root + "/package.json")
        runtime = surface(source, package_root, ["lib", "bin", "scripts", "configs", "install.sh", "package.json"])
        units.append({"id": "package." + package, "version": metadata["version"],
                      "providers": {"runtime": runtime}, "tree_digest": runtime["tree_digest"]})
    return {"schema_version": "release-attestation/v1",
            "umbrella": {"version": version, "tag": "v" + version, "date": date},
            "units": sorted(units, key=lambda u: u["id"])}


def check_transition(previous, current):
    old = {u["id"]: u for u in previous["units"]}
    errors = []
    for unit in current["units"]:
        prior = old.get(unit["id"])
        changed = prior and prior["tree_digest"] != unit["tree_digest"]
        if changed and prior.get("providers") and unit.get("providers"):
            # Added proof coverage is not a byte change. The previous source tag
            # is also rebuilt by this algorithm, so new surfaces are compared there.
            changed = any(p not in unit["providers"] or s != unit["providers"][p]
                          for p, s in prior["providers"].items())
        if prior and prior["version"] == unit["version"] and changed:
            errors.append(f"RELEASE_IMMUTABLE_TUPLE: {unit['id']}@{unit['version']}")
    return errors


def check(root, value, *, previous_ref=None):
    errors = []
    if build(root, value["umbrella"]["tag"]) != value:
        errors.append("RELEASE_ATTESTATION_STALE")
    if previous_ref:
        errors.extend(check_transition(build(root, ref=previous_ref), value))
    for path in sorted((Path(root) / "releases").glob("v*.json")):
        historical = json.loads(path.read_text())
        if historical["umbrella"]["tag"] == value["umbrella"]["tag"]:
            tagged = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/" + value["umbrella"]["tag"]],
                                    cwd=root, capture_output=True, check=False)
            if tagged.returncode != 0:
                continue  # A draft can be regenerated; published tuples stay immutable.
        errors.extend(check_transition(historical, value))
    return sorted(set(errors))


def cmd_attest(env, argv):
    opts = parse_flags(argv, {"--release": "str", "--previous": "str", "--check": "bool"})
    if opts["help"]:
        print("skiller attest [--release vX.Y.Z] [--previous vX.Y.Z] [--check]")
        return
    root = find_monorepo_root(env.root) or env.root
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
    root = find_monorepo_root(env.root) or env.root
    value = build(root)
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
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
