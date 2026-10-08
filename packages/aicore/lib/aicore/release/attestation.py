"""Deterministic release identity over the bytes delivered by both providers."""
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import subprocess

from ..content.skill import SKILL_IGNORE

POLICY_PATH = "configs/release-units.json"
POLICY_SCHEMA = "release-unit-policy/v1"


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
            self.paths = [path for path in result.stdout.splitlines()
                          if self._present_in_worktree(path)]

    def _present_in_worktree(self, path):
        # The index retains unstaged deletions. Exclude only genuinely absent
        # entries; lstat keeps dangling/external links for read() to reject.
        candidate = self.root / path
        try:
            candidate.lstat()
        except FileNotFoundError:
            # A missing target below a replaced symlink is not evidence of a
            # deleted tracked file. Preserve it for the containment/read gate.
            return any((self.root / parent).is_symlink()
                       for parent in Path(path).parents if parent != Path("."))
        return True

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

    def exists(self, path):
        path = str(Path(path)).removeprefix("./")
        return path in self.paths if self.paths is not None else (self.root / path).is_file()

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


def _package_rel(root, package_root):
    """The package's POSIX prefix inside the host root ("" when it is the root or `package_root` is None).

    `package_root` is the location of the package that owns the publication-version map and the
    skill sources released as their own units; its prefix in the host root names them.
    """
    if package_root is None:
        return ""
    try:
        relative = Path(package_root).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return ""
    return "" if relative == "." else relative


def _in_package(relative, root, package_root):
    prefix = _package_rel(root, package_root)
    return f"{prefix}/{relative}" if prefix else relative


def _checked_policy(value):
    if not isinstance(value, dict) or value.get("schema_version") != POLICY_SCHEMA:
        raise ValueError("RELEASE_UNIT_POLICY_INVALID")
    return value


def _worktree_policy(root):
    """The host's current policy file, the authority for layout a historical ref lacks."""
    path = Path(root) / POLICY_PATH
    if not path.is_file():
        return None
    return _checked_policy(json.loads(path.read_text(encoding="utf-8")))


def _release_unit_policy(source):
    """Return the independent version owner for every release plugin unit.

    Historical refs predate the explicit policy file.  They use the host's
    `legacy_policy` from the current working tree: the same stable ownership rule,
    so old releases remain comparable without becoming an authority for the
    current expected version.
    """
    if source.exists(POLICY_PATH):
        return _checked_policy(source.json(POLICY_PATH))
    current = _worktree_policy(source.root)
    legacy = current.get("legacy_policy") if current else None
    if legacy is None:
        raise ValueError("RELEASE_UNIT_POLICY_MISSING")
    return _checked_policy(legacy)


def _layout(source, policy, name, key):
    """Layout field `key` of plugin rule `name`: the ref's policy, else the host's
    current policy (`plugins`, then `legacy_policy`).  Older policy files predate
    layout fields; the current host is the same authority the code used to hardcode."""
    rule = policy.get("plugins", {}).get(name, {})
    if key in rule:
        return rule[key]
    current = _worktree_policy(source.root) or {}
    for candidate in (current, current.get("legacy_policy") or {}):
        rule = candidate.get("plugins", {}).get(name, {})
        if key in rule:
            return rule[key]
    return None


def _package_units(source, policy):
    """Runtime package units {id: path}: the ref's policy, else the host's current one."""
    units = policy.get("package_units")
    if units is None:
        units = (_worktree_policy(source.root) or {}).get("package_units", {})
    if not isinstance(units, dict) or not all(
            isinstance(path, str) and path for path in units.values()):
        raise ValueError("RELEASE_UNIT_POLICY_INVALID: package_units")
    return units


def _expected_plugin_version(source, policy, name, umbrella_version, package_root=None):
    rule = policy.get("plugins", {}).get(name, {})
    owner = rule.get("version_owner", policy.get("default_plugin_version_owner"))
    if owner == "umbrella":
        return umbrella_version, "umbrella"
    if owner == "package":
        path = _layout(source, policy, name, "path")
        if not isinstance(path, str) or not path:
            raise ValueError(f"RELEASE_UNIT_POLICY_INVALID: {name}: path missing")
        package_path = f"{path}/package.json"
        return source.json(package_path)["version"], package_path
    if owner == "explicit":
        expected = rule.get("expected_version")
        if not isinstance(expected, str) or not expected:
            raise ValueError(f"RELEASE_UNIT_POLICY_INVALID: {name}: explicit version missing")
        return expected, POLICY_PATH
    if owner == "skiller-publication-map":
        path = _in_package("configs/publication-versions.json", source.root, package_root)
        versions = source.json(path)
        expected = versions.get("units", {}).get(name, versions["default_unit_version"])
        return expected, path
    raise ValueError(f"RELEASE_UNIT_POLICY_INVALID: {name}: {owner}")


def version_errors(value):
    """Validate version freshness independently from release snapshot bytes."""
    errors = []
    for unit in value.get("units", []):
        expected = unit.get("expected_version")
        if expected is None:
            continue
        actual = unit.get("version")
        source = unit.get("version_source", "unknown")
        if actual != expected:
            errors.append(
                f"RELEASE_EXPECTED_VERSION_MISMATCH: {unit['id']} expected {expected} "
                f"from {source}, got {actual}")
        provider_versions = unit.get("provider_versions", {})
        for provider, provider_version in sorted(provider_versions.items()):
            if provider_version != expected:
                errors.append(
                    f"RELEASE_VERSION_SURFACE_MISMATCH: {unit['id']} {provider}="
                    f"{provider_version}, expected {expected}")
        for provider in unit.get("required_providers", []):
            if provider not in unit.get("providers", {}):
                errors.append(f"RELEASE_PROVIDER_MISSING: {unit['id']} {provider}")
    return errors


def build(root, tag=None, *, ref=None, package_root=None):
    source = Source(root, ref)
    changelog = source.read("CHANGELOG.md").decode()
    headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$",
                          changelog, re.M)
    if not headings:
        raise ValueError("RELEASE_CHANGELOG_MISSING")
    version, date = headings[0]
    if tag and tag != "v" + version:
        raise ValueError("RELEASE_VERSION_MISMATCH")
    codex = {p["name"]: p for p in source.json(".agents/plugins/marketplace.json")["plugins"]}
    claude = {p["name"]: p for p in source.json(".claude-plugin/marketplace.json")["plugins"]}
    policy = _release_unit_policy(source)
    units = []
    for name in sorted(set(codex) | set(claude)):
        entry = codex.get(name)
        providers = {}
        provider_versions = {}
        if entry:
            raw = entry["source"]
            codex_root = (raw if isinstance(raw, str) else raw["path"]).removeprefix("./")
            manifest = source.json(codex_root + "/.codex-plugin/plugin.json")
            skill_roots = manifest["skills"]
            if isinstance(skill_roots, str):
                skill_roots = [skill_roots]
            providers["codex"] = surface(source, codex_root, skill_roots,
                                           manifest=".codex-plugin/plugin.json")
            providers["codex-native"] = surface(source, codex_root, ["."],
                                                  manifest=".codex-plugin/plugin.json")
            provider_versions["codex"] = manifest["version"]
            # A `grok_native` plugin is installed by Grok as the package itself,
            # which discovers its native slash commands from `commands/`.  It is a
            # separate native delivery surface sharing the plugin's package root.
            if _layout(source, policy, name, "grok_native") is True:
                providers["grok"] = surface(source, codex_root, ["commands"],
                                             manifest=".claude-plugin/plugin.json")
                provider_versions["grok"] = manifest["version"]
        other = claude.get(name)
        if other:
            claude_root = str(Path(other["source"]))
            if "skills" in other:
                roots = other["skills"]
                claude_manifest = None
            else:
                claude_manifest = ".claude-plugin/plugin.json"
                declaration = source.json(claude_root + "/" + claude_manifest)
                if declaration.get("version"):
                    provider_versions["claude-code"] = declaration["version"]
                if claude_root.startswith(_in_package("skills/", source.root, package_root)):
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
        expected, version_source = _expected_plugin_version(source, policy, name, version, package_root)
        actual = (provider_versions.get("codex") or provider_versions.get("claude-code")
                  or expected)
        units.append({"id": name, "version": actual, "expected_version": expected,
                      "version_source": version_source,
                      "required_providers": policy.get("plugins", {}).get(name, {}).get(
                          "required_providers", []),
                      "provider_versions": provider_versions, "providers": providers,
                      "tree_digest": tree_digest({p: s["tree_digest"] for p, s in providers.items()})})
    for package, package_path in sorted(_package_units(source, policy).items()):
        metadata = source.json(package_path + "/package.json")
        runtime = surface(source, package_path, ["lib", "bin", "scripts", "configs", "install.sh", "package.json"])
        units.append({"id": "package." + package, "version": metadata["version"],
                      "expected_version": metadata["version"],
                      "version_source": package_path + "/package.json",
                      "required_providers": [], "provider_versions": {},
                      "providers": {"runtime": runtime}, "tree_digest": runtime["tree_digest"]})
    return {"schema_version": "release-attestation/v1",
            "version_policy": {"source": POLICY_PATH,
                               "digest": digest(json.dumps(policy, sort_keys=True,
                                                           separators=(",", ":")).encode())},
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


def check(root, value, *, previous_ref=None, package_root=None):
    errors = []
    if build(root, value["umbrella"]["tag"], package_root=package_root) != value:
        errors.append("RELEASE_SNAPSHOT_STALE")
    errors.extend(version_errors(value))
    if previous_ref:
        errors.extend(check_transition(build(root, ref=previous_ref, package_root=package_root), value))
    for path in sorted((Path(root) / "releases").glob("v*.json")):
        historical = json.loads(path.read_text())
        if historical["umbrella"]["tag"] == value["umbrella"]["tag"]:
            tagged = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "refs/tags/" + value["umbrella"]["tag"]],
                                    cwd=root, capture_output=True, check=False)
            if tagged.returncode != 0:
                continue  # A draft can be regenerated; published tuples stay immutable.
        errors.extend(check_transition(historical, value))
    return sorted(set(errors))

