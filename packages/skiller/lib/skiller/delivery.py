"""Explicit post-tag delivery with preimage recovery and durable readback receipts."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import uuid

from core import atomic_write_json, find_monorepo_root
from core.provider.lock import LOCK_RELATIVE_PATH, parse_lock, replace_owner_records, serialize_lock, _writer_guard, _contained_target
from core import atomic_write_text
from .common import die, parse_flags
from .release_attestation import build, check, digest
from .state import load_db
from .update import update_one


def release_history(root, current_release):
    """Load attested history from snapshots committed at matching release tags."""
    result = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-version:refname"],
        cwd=root, capture_output=True, text=True, check=True,
    )
    history = []
    for ref in result.stdout.splitlines():
        if ref == current_release:
            continue
        snapshot = subprocess.run(
            ["git", "show", f"{ref}:releases/{ref}.json"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        if snapshot.returncode != 0:
            continue
        try:
            value = json.loads(snapshot.stdout)
        except json.JSONDecodeError:
            continue
        if value.get("umbrella", {}).get("tag") == ref and isinstance(value.get("units"), list):
            commit = subprocess.run(
                ["git", "rev-parse", f"{ref}^{{commit}}"], cwd=root,
                capture_output=True, text=True, check=False,
            )
            if commit.returncode == 0:
                value["_tag_commit"] = commit.stdout.strip()
            history.append(value)
    return history


def _provider_references(env):
    """Return provider-declared cache roots; failure to inspect never authorizes deletion."""
    references = {"claude": set(), "codex": set()}
    inspected = {"claude": False, "codex": False}
    installed = env.home / ".claude/plugins/installed_plugins.json"
    try:
        plugins = json.loads(installed.read_text()).get("plugins", {})
        for identifier, entries in plugins.items():
            if identifier.endswith("@swissknifeman"):
                references["claude"].update(Path(entry["installPath"]).resolve()
                                             for entry in entries if entry.get("installPath"))
        inspected["claude"] = True
    except (OSError, TypeError, ValueError):
        pass
    if shutil.which("codex"):
        try:
            result = subprocess.run(["codex", "plugin", "list", "--json"],
                                    capture_output=True, text=True, check=True)
            for entry in json.loads(result.stdout).get("installed", []):
                if entry.get("marketplaceName") != "swissknifeman":
                    continue
                path = entry.get("source", {}).get("path")
                if path:
                    references["codex"].add(Path(path).resolve())
            inspected["codex"] = True
        except (OSError, TypeError, ValueError, subprocess.CalledProcessError):
            pass
    return references, inspected


def prune_provider_caches(env, attestation, history, *, dry_run=False):
    """Prune only unreferenced caches whose attested provider bytes are exact-known."""
    references, inspected = _provider_references(env)
    current = {unit["id"]: unit for unit in attestation["units"]}
    known = {}
    for snapshot in history:
        for unit in snapshot["units"]:
            known.setdefault((unit["id"], unit["version"]), []).append(unit)
            commit = snapshot.get("_tag_commit", "")
            if commit:
                known.setdefault((unit["id"], commit[:12]), []).append(unit)
    rows = []
    providers = (
        ("claude", env.home / ".claude/plugins/cache/swissknifeman", "claude-code"),
        ("codex", env.home / ".codex/plugins/cache/swissknifeman", "codex-native"),
    )
    for provider, cache_root, projection_name in providers:
        if cache_root.is_symlink():
            rows.append({"provider": provider, "path": str(cache_root), "unit": "*",
                         "version": "*", "action": "preserve",
                         "classification": "modified-or-unknown", "status": "blocked",
                         "errors": ["symlink-cache-root"], "readback": {"exists": True}})
            continue
        if not cache_root.is_dir():
            continue
        for unit_root in sorted(cache_root.iterdir()):
            if unit_root.is_symlink():
                rows.append({"provider": provider, "path": str(unit_root),
                             "unit": unit_root.name, "version": "*", "action": "preserve",
                             "classification": "modified-or-unknown", "status": "blocked",
                             "errors": ["symlink-unit-root"], "readback": {"exists": True}})
                continue
            if not unit_root.is_dir():
                continue
            for candidate in sorted(unit_root.iterdir()):
                if candidate.is_symlink():
                    rows.append({"provider": provider, "path": str(candidate),
                                 "unit": unit_root.name, "version": candidate.name,
                                 "action": "preserve", "classification": "modified-or-unknown",
                                 "status": "blocked", "errors": ["symlink-cache-entry"],
                                 "readback": {"exists": True}})
                    continue
                if not candidate.is_dir():
                    continue
                resolved = candidate.resolve()
                row = {"provider": provider, "path": str(candidate), "unit": unit_root.name,
                       "version": candidate.name, "action": "preserve", "readback": {"exists": True}}
                now = current.get(unit_root.name)
                if now and candidate.name == now["version"]:
                    row["classification"] = "current"
                elif any(resolved == ref or ref.is_relative_to(resolved)
                         for ref in references[provider]):
                    row["classification"] = "referenced"
                elif not inspected[provider]:
                    row.update({"classification": "reference-state-unavailable",
                                "status": "blocked", "errors": ["provider-state-unavailable"]})
                else:
                    current_projection = (now.get("providers", {}).get(projection_name)
                                          or (now.get("providers", {}).get("codex")
                                              if now and provider == "codex" else None)) if now else None
                    if current_projection and not verify_surface(candidate, current_projection):
                        row.update({"classification": "exact-current-superseded",
                                    "status": "planned" if dry_run else "pruned",
                                    "action": "prune", "digest": current_projection["tree_digest"]})
                        if not dry_run:
                            shutil.rmtree(candidate)
                            row["readback"] = {"exists": candidate.exists()}
                        rows.append(row)
                        continue
                    matches = known.get((unit_root.name, candidate.name), [])
                    projections = [unit["providers"].get(projection_name)
                                   or (unit["providers"].get("codex")
                                       if provider == "codex" else None)
                                   for unit in matches if unit.get("providers")]
                    projection = next((item for item in projections
                                       if item and not verify_surface(candidate, item)), None)
                    if not projection:
                        row.update({"classification": "modified-or-unknown", "status": "blocked",
                                    "errors": (["unknown-version"] if not projections
                                               else sorted(set(error for item in projections if item
                                                               for error in verify_surface(candidate, item))))})
                    else:
                        row.update({"classification": "exact-known-superseded",
                                    "status": "planned" if dry_run else "pruned",
                                    "action": "prune", "digest": projection["tree_digest"]})
                        if not dry_run:
                            shutil.rmtree(candidate)
                            row["readback"] = {"exists": candidate.exists()}
                rows.append(row)
    return rows


def verify_surface(root, surface, *, reject_extras=False):
    root = Path(root)
    errors = []
    for relative, expected in surface["files"].items():
        path = root / relative
        if (not path.is_file() or path.is_symlink() or
                any(p.is_symlink() for p in path.parents if p == root or root in p.parents) or
                digest(path.read_bytes()) != expected):
            errors.append(relative)
    if reject_extras:
        from .common import SKILL_IGNORE
        import fnmatch
        for path in root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if path.is_file() and relative not in surface["files"] and not any(
                    fnmatch.fnmatch(part, pattern) for part in path.relative_to(root).parts
                    for pattern in SKILL_IGNORE + ("tests",)):
                allowed = False
                source = Path(__file__).resolve().parents[4] / surface.get("source", "")
                if relative.startswith(".codex-plugin/migrated-command-skills/"):
                    from core.provider.runtime import codex_migrated_command_skill
                    expected = codex_migrated_command_skill(source, relative)
                    allowed = expected is not None and not path.is_symlink() and path.read_bytes() == expected
                if not allowed:
                    errors.append("unknown-extra:" + relative)
    return sorted(set(errors))


def recover_lock(target, attestation, history, backup, *, dry_run=False):
    """Restore lost SKM ownership only for attested bytes; never adopt modifications."""
    with _writer_guard(Path(target)):
        return _recover_lock_locked(target, attestation, history, backup, dry_run=dry_run)


def _recover_lock_locked(target, attestation, history, backup, *, dry_run=False):
    from .publication import _distribution_artifact
    target = Path(target)
    lock_path = _contained_target(target, LOCK_RELATIVE_PATH)
    lock = parse_lock(lock_path.read_bytes()) if lock_path.is_file() else None
    records = {r.target_path: r for r in lock.records} if lock else {}
    additions, rows = [], []
    units = {u["id"]: u for u in attestation["units"]}
    bundles = target / ".agents/plugins/bundles"
    if bundles.is_dir():
        for bundle in sorted(bundles.iterdir()):
            unit = units.get(bundle.name)
            if not bundle.is_dir() or not unit or "codex" not in unit["providers"]:
                continue
            known = [u["providers"]["codex"] for snapshot in [attestation] + history
                     for u in snapshot["units"] if u["id"] == bundle.name and "codex" in u["providers"]]
            for path in sorted(bundle.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(target).as_posix()
                if relative in records:
                    continue
                local = path.relative_to(bundle).as_posix()
                if path.is_symlink() or any(p.is_symlink() for p in path.parents if p == target or target in p.parents):
                    rows.append({"path": relative, "classification": "modified-or-unknown", "before": "symlink"})
                    continue
                observed = digest(path.read_bytes())
                match = next((s for s in known if s["files"].get(local) == observed), None)
                row = {"path": relative, "before": observed,
                       "classification": ("exact-current" if unit["providers"]["codex"]["files"].get(local) == observed
                                          else "exact-known-old") if match else "modified-or-unknown"}
                rows.append(row)
                if match:
                    artifact = _distribution_artifact(target, path, path.read_bytes(),
                                                     match["source"] + "/" + local, path.read_bytes())
                    additions.append(artifact.provenance)
    marketplace = _contained_target(target, ".agents/plugins/marketplace.json")
    if marketplace.is_file() and marketplace.relative_to(target).as_posix() not in records:
        value = json.loads(marketplace.read_text())
        entries = value.get("plugins", [])
        valid = (value.get("name") == "swissknifeman" and
                 value.get("interface") == {"displayName": "swissknifeman"} and
                 set(value) == {"name", "interface", "plugins"} and
                 isinstance(entries, list) and len({e.get("name") for e in entries}) == len(entries))
        for entry in entries:
            name = entry.get("name")
            valid = valid and name in units and entry.get("source") == {
                "source": "local", "path": "./.agents/plugins/bundles/" + str(name)} and entry.get("policy") == {
                    "installation": "AVAILABLE", "authentication": "ON_INSTALL"} and set(entry) == {
                        "name", "source", "policy", "category"}
        rows.append({"path": ".agents/plugins/marketplace.json", "before": digest(marketplace.read_bytes()),
                     "classification": "provider-generated" if valid else "modified-or-unknown"})
        if valid:
            artifact = _distribution_artifact(target, marketplace, marketplace.read_bytes(),
                                             ".agents/plugins/marketplace.json", marketplace.read_bytes())
            additions.append(artifact.provenance)
    blocked = [r for r in rows if r["classification"] == "modified-or-unknown"]
    if blocked or dry_run or not additions:
        return rows, blocked
    backup.mkdir(parents=True, exist_ok=True)
    if lock_path.is_file():
        shutil.copy2(lock_path, backup / "provider-artifacts.lock.json")
    else:
        atomic_write_json(backup / "lock-preimage.json", {"absent": True})
    own = [r for r in records.values() if r.artifact_id.startswith("skiller.codex.connect.")]
    merged = replace_owner_records(lock, "skiller.codex.connect", own + additions)
    atomic_write_text(lock_path, serialize_lock(merged).decode())
    return rows, []


def project_readback(target, value):
    target = Path(target)
    units = {u["id"]: u for u in value["units"]}
    surfaces = []
    source_root = Path(__file__).resolve().parents[4]
    for filename in ("settings.json", "settings.local.json"):
        settings_path = target / ".claude" / filename
        if not settings_path.is_file():
            continue
        settings = json.loads(settings_path.read_text())
        declaration = settings.get("extraKnownMarketplaces", {}).get("swissknifeman")
        if not declaration:
            continue
        source = declaration.get("source", {})
        location = Path(source.get("path", ""))
        enabled = [name.split("@")[0] for name, flag in settings.get("enabledPlugins", {}).items()
                   if name.endswith("@swissknifeman") and flag is True]
        errors = []
        if source.get("source") != "directory" or location.resolve() != source_root.resolve():
            errors.append("marketplace-source-mismatch")
        for name in enabled:
            unit = units.get(name)
            if not unit or "claude-code" not in unit["providers"]:
                errors.append("unattested-plugin:" + name)
                continue
            projection = unit["providers"]["claude-code"]
            errors.extend(name + "/" + p for p in verify_surface(source_root / projection["source"], projection))
        surfaces.append({"surface": "claude-activation/" + filename, "status": "blocked" if errors else "current", "errors": errors})
    marker = target / ".agents/plugins/marketplace.json"
    if marker.is_file():
        for entry in json.loads(marker.read_text())["plugins"]:
            name = entry["name"]
            surface = units[name]["providers"]["codex"]
            errors = verify_surface(target / ".agents/plugins/bundles" / name, surface,
                                    reject_extras=True)
            surfaces.append({"surface": "codex/" + name, "digest": surface["tree_digest"],
                             "status": "blocked" if errors else "current", "errors": errors})
    lock_path = target / LOCK_RELATIVE_PATH
    if lock_path.is_file():
        lock = parse_lock(lock_path.read_bytes())
        errors = [r.target_path for r in lock.records if r.artifact_id.startswith("skiller.codex.connect.")
                  and (not (target / r.target_path).is_file() or
                       digest((target / r.target_path).read_bytes()) != r.rendered_hash)]
        surfaces.append({"surface": "provider-lock", "status": "blocked" if errors else "current", "errors": errors})
    # Vendor manifests carry source paths, allowing byte readback independently of version strings.
    from .common import MANIFEST, SKILL_IGNORE, strip_skill_managed_marker
    import fnmatch
    folders = {".claude/skills", ".ai/skills", ".cursor/skills", ".agents/skills"}
    for config_path in (target / ".swissknife.json", target / ".swissknifeman/config.json"):
        if config_path.is_file():
            config = json.loads(config_path.read_text())
            if config.get("skills_path"):
                folders.add(config["skills_path"])
    for folder in sorted(folders):
        manifest_path = target / folder / MANIFEST
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text())
        errors = []
        records = manifest.get("skills", [])
        if isinstance(records, dict):
            records = list(records.values())
        for record in records:
            if not isinstance(record, dict):
                errors.append("unverifiable:manifest-record")
                continue
            source = record.get("source_path") or record.get("source")
            name = record.get("flat_name") or record.get("path") or record.get("name")
            if not source or not name:
                errors.append("unverifiable:manifest-record")
                continue
            candidate = Path(source)
            if not candidate.is_absolute():
                candidate = Path(__file__).resolve().parents[2] / candidate
            if not candidate.is_dir():
                errors.append("unverifiable:" + name)
                continue
            for path in candidate.rglob("*"):
                relative = path.relative_to(candidate)
                if path.is_file() and not any(fnmatch.fnmatch(part, pattern) for part in relative.parts for pattern in SKILL_IGNORE):
                    dest = target / folder / name / relative
                    actual = strip_skill_managed_marker(dest.read_bytes()) if dest.is_file() and path.name == "SKILL.md" else dest.read_bytes() if dest.is_file() else None
                    if (not dest.is_file() or dest.is_symlink() or actual != path.read_bytes()):
                        errors.append(name + "/" + relative.as_posix())
        for relative in manifest.get("support_files", []):
            source = Path(__file__).resolve().parents[2] / "skills" / relative
            dest = target / folder / relative
            if not source.is_file() or not dest.is_file() or source.read_bytes() != dest.read_bytes():
                errors.append(relative)
        surfaces.append({"surface": folder, "status": "blocked" if errors else "current", "errors": errors})
    return surfaces


def _run(command, *, cwd=None):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return result.returncode == 0, (result.stderr or result.stdout).strip()[-3000:]


def deliver(env, release, *, all_projects=False, target=None, dry_run=False, native=True):
    root = find_monorepo_root(env.root) or env.root
    path = root / "releases" / (release + ".json")
    value = json.loads(path.read_text())
    errors = check(root, value)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    tagged = subprocess.run(["git", "rev-parse", release + "^{commit}"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    if errors or head != tagged:
        raise ValueError("DELIVERY_SOURCE_MISMATCH: " + "; ".join(errors))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    receipt_path = env.home / ".swissknifeman/receipts/delivery" / release / (run_id + ".json")
    backup = receipt_path.parent / (run_id + "-preimages")
    receipt = {"schema_version": "delivery-receipt/v1", "release": value["umbrella"], "commit": head,
               "attestation_digest": digest(path.read_bytes()), "dry_run": dry_run, "status": "PARTIAL",
               "targets": [], "session": "restart-required", "receipt": str(receipt_path)}
    def save():
        if not dry_run:
            atomic_write_json(receipt_path, receipt)
    save()
    history = release_history(root, release)
    roots = ([Path(r["path"]) for r in load_db(env)["projects"]] if all_projects else [Path(target)] if target else [])
    for index, project in enumerate(sorted(set(roots))):
        if project.resolve() == root.resolve():
            continue
        row = {"root": str(project), "surface": "project", "status": "blocked"}
        receipt["targets"].append(row)
        save()
        try:
            if not project.is_dir():
                raise ValueError("DELIVERY_TARGET_MISSING")
            row["recovery"], blocked = recover_lock(project, value, history, backup / str(index), dry_run=dry_run)
            if blocked:
                raise ValueError("DELIVERY_MODIFIED_PREIMAGE")
            if not dry_run:
                # Preserve the actual old managed bytes before update, including deletions.
                preimage = backup / str(index)
                preimage.mkdir(parents=True, exist_ok=True)
                lock_preimage = _contained_target(project, LOCK_RELATIVE_PATH)
                if lock_preimage.is_file():
                    shutil.copy2(lock_preimage, preimage / "provider-lock-before-update.json")
                managed = project / ".agents/plugins"
                if managed.is_dir():
                    shutil.copytree(managed, preimage / "agents-plugins", symlinks=True, dirs_exist_ok=True)
                for manifest_path in project.glob(".*/skills/" + ".swissknifeman-manifest.json"):
                    shutil.copytree(manifest_path.parent, preimage / manifest_path.parent.relative_to(project), symlinks=True, dirs_exist_ok=True)
                config_path = project / ".swissknife.json"
                if config_path.is_file():
                    custom = json.loads(config_path.read_text()).get("skills_path")
                    if custom:
                        folder = _contained_target(project, custom)
                        if (folder / ".swissknifeman-manifest.json").is_file():
                            shutil.copytree(folder, preimage / "custom-skills", symlinks=True, dirs_exist_ok=True)
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                ok = update_one(env, project, dry_run=dry_run)
            row["log"] = output.getvalue()
            if not ok:
                raise ValueError("DELIVERY_NO_PROJECT_MARKERS")
            row["readback"] = project_readback(project, value) if not dry_run else []
            if not dry_run and (not row["readback"] or any(s["status"] != "current" for s in row["readback"])):
                raise ValueError("DELIVERY_READBACK_FAILED")
            row["status"] = "planned" if dry_run else "updated"
        except (Exception, SystemExit) as exc:
            row["reason"] = str(exc)
        save()
    if native and not dry_run:
        from .publication import run_codex_native_install
        units = {u["id"]: u for u in value["units"]}
        if shutil.which("codex"):
            listed = subprocess.run(["codex", "plugin", "list", "--json"], capture_output=True, text=True, check=True)
            installed = json.loads(listed.stdout)["installed"]
            for entry in installed:
                name = entry.get("name")
                if entry.get("marketplaceName") != "swissknifeman" or not entry.get("enabled") or name not in units:
                    continue
                row = {"surface": "codex-cache/" + name, "status": "blocked"}
                receipt["targets"].append(row)
                save()
                ok, detail = run_codex_native_install(repo_root=root, plugin=name, dry_run=False)
                row["reason"] = detail
                cache = env.home / ".codex/plugins/cache/swissknifeman" / name / units[name]["version"]
                projection = units[name]["providers"].get("codex-native", units[name]["providers"]["codex"])
                # A native cache is a package checkout.  Its attested projection must
                # match exactly, while unrelated package files and provider-generated
                # state are valid cache contents.
                row["readback"] = verify_surface(cache, projection)
                if ok and not row["readback"]:
                    row["status"] = "updated"
                    row["digest"] = projection["tree_digest"]
                save()
            marketplaces = subprocess.run(["codex", "plugin", "marketplace", "list", "--json"], capture_output=True, text=True, check=True)
            roots = [Path(m["root"]) for m in json.loads(marketplaces.stdout).get("marketplaces", []) if m.get("name") == "swissknifeman"]
            row = {"surface": "codex-marketplace-runtime", "status": "blocked", "readback": []}
            receipt["targets"].append(row)
            for runtime_root in roots:
                for unit in value["units"]:
                    projection = unit["providers"].get("runtime")
                    if unit["id"] == "task":
                        projection = unit["providers"].get("claude-code")
                    if projection:
                        row["readback"].extend(unit["id"] + "/" + p for p in verify_surface(runtime_root / projection["source"], projection))
            if len(roots) == 1 and not row["readback"]:
                row["status"] = "current"
            save()
        installed_path = env.home / ".claude/plugins/installed_plugins.json"
        if shutil.which("claude") and installed_path.is_file():
            ok, detail = _run(["claude", "plugin", "marketplace", "update", "swissknifeman"])
            names = [n for n in json.loads(installed_path.read_text()).get("plugins", {}) if n.endswith("@swissknifeman")]
            for identifier in names:
                name = identifier.split("@")[0]
                if name not in units or "claude-code" not in units[name]["providers"]:
                    continue
                installs = json.loads(installed_path.read_text())["plugins"].get(identifier, [])
                for installation in installs:
                    scope = installation.get("scope", "user")
                    project_path = installation.get("projectPath")
                    row = {"surface": "claude-cache/" + name, "scope": scope, "project": project_path, "status": "blocked"}
                    receipt["targets"].append(row)
                    save()
                    if project_path and not Path(project_path).is_dir():
                        row["reason"] = "DELIVERY_TARGET_MISSING"
                        save()
                        continue
                    updated, message = _run(["claude", "plugin", "update", identifier, "--scope", scope, "--yes"], cwd=project_path) if ok else (False, detail)
                    current = json.loads(installed_path.read_text())["plugins"].get(identifier, [])
                    current = [i for i in current if i.get("scope", "user") == scope and i.get("projectPath") == project_path]
                    row["readback"] = [{"root": i["installPath"], "errors": verify_surface(i["installPath"], units[name]["providers"]["claude-code"])} for i in current]
                    row["reason"] = message
                    if updated and row["readback"] and not any(i["errors"] for i in row["readback"]):
                        row["status"] = "updated"
                    save()
    receipt["cache_gc"] = prune_provider_caches(env, value, history, dry_run=dry_run) if native else []
    cache_blocked = any(row.get("status") == "blocked" for row in receipt["cache_gc"])
    receipt["status"] = ("GREEN" if receipt["targets"] and not cache_blocked
                         and all(t["status"] in {"updated", "current"} for t in receipt["targets"])
                         else "PARTIAL")
    if dry_run:
        receipt["status"] = "DRY-RUN"
    save()
    return receipt


def cmd_deliver(env, argv):
    opts = parse_flags(argv, {"--release": "str", "--all": "bool", "--target": "str", "--dry-run": "bool", "--no-native": "bool"})
    if opts["help"]:
        print("skiller deliver --release vX.Y.Z [--all | --target PATH] [--dry-run] [--no-native]")
        return
    if not opts["release"]:
        die("DELIVERY_RELEASE_REQUIRED")
    try:
        receipt = deliver(env, opts["release"], all_projects=opts["all"], target=opts["target"], dry_run=opts["dry_run"], native=not opts["no_native"])
    except (Exception, SystemExit) as exc:
        die(f"DELIVERY_FAILED: {exc}")
    for target in receipt["targets"]:
        print(f"{target['status']:8} {target.get('root', target['surface'])} {target.get('reason', '')[:200]}")
    for cache in receipt.get("cache_gc", []):
        status = cache.get("status", "preserve")
        print(f"{status:8} {cache['path']} {cache['classification']}")
    print(f"{receipt['status']}; session=restart-required; receipt={receipt['receipt']}")
    if receipt["status"] == "PARTIAL":
        raise SystemExit(1)
