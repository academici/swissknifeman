"""``aicore project`` (``swissknifeman project``): the project-local launcher and the invocation context.

    init    [--marker-only] [--adopt] [--dry-run] [--json]   write .swissknifeman/launcher.py and its lock
            [--project CODE [--workspace CODE] [--plans-store workspace|legacy]]   and the marker project.json
    sync    [--adopt] [--dry-run] [--json]                   bring the managed files to the hub template (no-op if equal)
    verify  [--json] [--no-roundtrip]                        read-only checks of the managed files and the launcher chain
    context [--json]                                         where this command runs and how the project was found
    migrate [--dry-run] [--json]                             move config.toml, state, backups, stubs of the checkout
                                                             into projects/<code>/local/ of the workspace
    doctor  [--json]                                         verify plus the project config, the local folder, leftovers,
                                                             the SKM environment snippet and variables
    exec    -- <group> [args...]                             run a group through this project's launcher

No command takes a target path: the project is the one the launcher bound, else the nearest ``.git``/``.swissknifeman``
above the working directory. Text mode prints ``CODE: message`` on stderr; ``--json`` prints one document on stdout.
Exit codes: 0 done, 1 refused or a check failed, 2 usage.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, TextIO, Tuple

from . import artifacts, migrate
from aicore.state import (LauncherError, ProjectContextRequired, read_invocation_context, require_project_path,
                          resolve_project, shellenv)
from aicore.state.invocation import (LAUNCHER_PROTOCOL, MIN_LAUNCHER_PROTOCOL, launcher_file, lock_file,
                                     read_lock)
from aicore.state.locations import (LAUNCHER_ENV, LOCAL_DIRNAME, PROJECT_DIRNAME, project_config_file,
                                    project_local_dir)

CHECK_SCHEMA = "urn:swissknifeman:aicore:check-result:v1"
SYNC_SCHEMA = "urn:swissknifeman:aicore:project-sync:v1"


def _require_document(document: dict, contract: str, code: str) -> None:
    """Refuse a document the module is about to emit when it leaves its schema."""
    from aicore.util.schema import load_contract, validate
    directory = Path(__file__).resolve().parents[3] / "schemas" / contract / "v1"
    registry, kind = load_contract(directory)
    issues = validate(document, kind, registry)
    if issues:
        raise LauncherError(code, "; ".join(issue.message for issue in issues[:5]))
USAGE = __doc__.split("\n\n")[1]


class _Usage(Exception):
    pass


def _check(check_id: str, status: str, observed: str, category: str = "state",
           remediation: Optional[str] = None) -> Dict[str, Any]:
    doc = {"$schema": CHECK_SCHEMA, "check_id": check_id, "status": status, "category": category, "observed": observed}
    if remediation and status in ("warn", "fail"):
        doc["remediation"] = remediation
    return doc


def _flags(args: Sequence[str], allowed: Sequence[str]) -> Dict[str, bool]:
    found = {name: False for name in allowed}
    for arg in args:
        if arg not in found:
            raise _Usage(f"unknown argument {arg!r}")
        found[arg] = True
    return found


def _project(env: Mapping[str, str], cwd: Path) -> Path:
    context = resolve_project(cwd, env=env)
    if context is None:
        raise ProjectContextRequired(cwd, f"no project above {cwd} (no .git or .swissknifeman); go into the project "
                                          f"and run `swissknifeman project init`")
    return context.root


def _clean_env(env: Mapping[str, str]) -> Dict[str, str]:
    result = dict(env)
    for name in LAUNCHER_ENV:
        result.pop(name, None)
    return result


def verify_checks(root: Path, env: Mapping[str, str], *, roundtrip: bool = True, timeout: float = 60.0) -> List[Dict]:
    """Read-only checks of a project's launcher: file, lock, digest, protocol, hub on PATH, the round trip."""
    checks: List[Dict[str, Any]] = []
    launcher = launcher_file(root)
    if launcher.is_symlink():
        checks.append(_check("project.launcher", "fail", f"{launcher} is a symlink (LAUNCHER_SYMLINK_FORBIDDEN)",
                             remediation="replace it with a regular file: swissknifeman project sync --adopt"))
    elif not launcher.is_file():
        checks.append(_check("project.launcher", "fail", f"{launcher} is missing",
                             remediation="swissknifeman project init"))
    else:
        checks.append(_check("project.launcher", "ok", f"{launcher} is a regular file"))
    try:
        lock = read_lock(root)
    except LauncherError as exc:
        lock = None
        checks.append(_check("project.lock", "fail", str(exc), remediation="swissknifeman project sync"))
    else:
        if lock is None:
            checks.append(_check("project.lock", "fail", f"{lock_file(root)} is missing (LAUNCHER_LOCK_MISSING)",
                                 remediation="swissknifeman project sync"))
        else:
            protocol = lock.get("protocol")
            if not isinstance(protocol, int) or protocol < MIN_LAUNCHER_PROTOCOL:
                checks.append(_check("project.lock", "fail", f"lock protocol {protocol!r} is no longer supported "
                                     f"(LAUNCHER_PROTOCOL_TOO_OLD)", remediation="swissknifeman project sync"))
            elif protocol > LAUNCHER_PROTOCOL:
                checks.append(_check("project.lock", "fail", f"lock protocol {protocol} is newer than this hub "
                                     f"({LAUNCHER_PROTOCOL}; LAUNCHER_PROTOCOL_NEWER)", remediation="update swissknifeman"))
            else:
                checks.append(_check("project.lock", "ok", f"lock protocol {protocol}"))
    template = artifacts.sha256(artifacts.template_bytes())
    current = artifacts._file_digest(launcher) if launcher.is_file() and not launcher.is_symlink() else None
    if current is None:
        checks.append(_check("project.digest", "skip", "no launcher to compare"))
    elif lock is not None and current != lock.get("template_sha256"):
        checks.append(_check("project.digest", "fail", f"launcher sha256 {current[:12]} differs from its lock "
                             f"(LAUNCHER_DIGEST_MISMATCH)", remediation="swissknifeman project sync --adopt"))
    elif current == template or current in artifacts.COMPATIBLE_DIGESTS:
        checks.append(_check("project.digest", "ok", f"launcher matches the hub template ({current[:12]})"))
    elif lock is not None:
        checks.append(_check("project.digest", "warn", f"launcher {current[:12]} is an older template; hub has "
                             f"{template[:12]} (LAUNCHER_UPDATE_AVAILABLE)", remediation="swissknifeman project sync"))
    else:
        checks.append(_check("project.digest", "fail", f"launcher {current[:12]} is not a hub template "
                             f"(FOREIGN_LAUNCHER)", remediation="swissknifeman project sync --adopt"))
    hub = shutil.which("swissknifeman", path=env.get("PATH"))
    if hub is None:
        checks.append(_check("project.hub", "fail", "swissknifeman is not on PATH (HUB_NOT_INSTALLED)", "environment",
                             "install Swiss Knife Man or add its bin directory to PATH"))
    else:
        checks.append(_check("project.hub", "ok", f"swissknifeman is {hub}", "environment"))
    if not roundtrip:
        return checks
    if hub is None or not launcher.is_file() or launcher.is_symlink():
        checks.append(_check("project.roundtrip", "skip", "needs the launcher and swissknifeman on PATH", "integration"))
        return checks
    try:
        done = subprocess.run([sys.executable, "-I", str(launcher), "project", "context", "--json"], cwd=str(root),
                              env=_clean_env(env), capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
        doc = json.loads(done.stdout) if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        done, doc = None, None
        checks.append(_check("project.roundtrip", "fail", f"launcher did not answer: {exc.__class__.__name__}",
                             "integration", "run: python3 -I .swissknifeman/launcher.py project context --json"))
        return checks
    if not isinstance(doc, dict):
        reason = (done.stderr.strip().splitlines() or ["no output"])[-1]
        checks.append(_check("project.roundtrip", "fail", f"exit {done.returncode}: {reason[:300]}", "integration",
                             "run: python3 -I .swissknifeman/launcher.py project context --json"))
    elif doc.get("resolution") != "launcher" or doc.get("project_root") != str(root.resolve()):
        checks.append(_check("project.roundtrip", "fail", f"launcher bound {doc.get('project_root')} "
                             f"({doc.get('resolution')}), expected {root.resolve()}", "integration",
                             "swissknifeman project sync"))
    else:
        checks.append(_check("project.roundtrip", "ok", f"launcher -> swissknifeman -> {doc['project_root']}",
                             "integration"))
    return checks


def plans_store_of(root: Path, env: Mapping[str, str]):
    """``(plans_root, plans_store document, error)`` of the project marker. A store that cannot be resolved (invalid
    marker, workspace folder missing) keeps ``<root>/plans`` and names the error in ``plans_store``."""
    from aicore.workspace import WorkspaceError, resolve_plans_store
    try:
        store = resolve_plans_store(root, env)
    except (WorkspaceError, ValueError) as exc:
        code = exc.code if isinstance(exc, WorkspaceError) else exc.__class__.__name__
        return root / "plans", {"kind": "unresolved", "project_id": None, "reason": "error", "error": code,
                                "workspace": None}, exc
    return store.plans_root, {"kind": store.kind, "project_id": store.project_id, "reason": store.reason,
                              "workspace": store.workspace}, None


def local_checks(root: Path, env: Mapping[str, str]) -> List[Dict[str, Any]]:
    """``project.local`` (the ``projects/<code>/local/`` folder the marker names, its config and ``repo.path``) and
    ``project.checkout-layer`` (project-layer files that still sit in the checkout and are no longer read)."""
    from aicore.workspace import WorkspaceError, read_local_config, read_marker
    try:
        marker = read_marker(root)
    except WorkspaceError:
        return []  # project.plans-store reports an unusable marker
    if marker is None:
        return [_check("project.local", "skip", f"no {PROJECT_DIRNAME}/project.json: the project layer stays in the "
                       f"checkout", "config")]
    workspace, project_id = marker["workspace"], marker["project_id"]
    local = project_local_dir(root, env=env)
    if local is None:
        return [_check("project.local", "warn", f"the workspace {workspace} has no project {project_id} on this machine; "
                       f"the project layer stays in {PROJECT_DIRNAME}/", "config",
                       "run `swissknifeman workspace clone <url>` or `swissknifeman workspace project attach`")]
    checks: List[Dict[str, Any]] = []
    try:
        document = read_local_config(local.parents[2], project_id)
    except WorkspaceError as exc:
        checks.append(_check("project.local", "fail", exc.message[:400], "config",
                             f"fix {local / 'config.toml'}"))
    else:
        repo = (document or {}).get("repo", {}).get("path")
        if repo is not None and os.path.realpath(repo) != str(root.resolve()):
            checks.append(_check("project.local", "warn", f"{local}: repo.path is {repo}, this checkout is {root}",
                                 "config", "swissknifeman workspace project bind, or run from the checkout it names"))
        else:
            checks.append(_check("project.local", "ok", f"{local}" + (f" (repo.path {repo})" if repo else ""), "config"))
    left = migrate.leftovers(root)
    if left:
        checks.append(_check("project.checkout-layer", "warn", f"{', '.join(left)} in {PROJECT_DIRNAME}/ are no longer "
                             f"read; the project layer is {local}", "config", "swissknifeman project migrate"))
    else:
        checks.append(_check("project.checkout-layer", "ok", f"{PROJECT_DIRNAME}/ holds no project layer files", "config"))
    return checks


def links_check(root: Path, env: Mapping[str, str]) -> Dict[str, Any]:
    """``project.links``: the optional links ``plans/`` and ``tasks/`` of the checkout (``workspace project link``). A link
    that points to the workspace folder of the project and is listed in ``.git/info/exclude`` is ``ok``; a dangling link, a
    link to another place and a link missing from the exclude file are ``warn``. A real folder is not a finding (it is never
    replaced); no link at all is ``skip``."""
    from aicore.workspace import WorkspaceError, inspect_folders
    from aicore.workspace.links import exclude_file, read_exclude
    try:
        found = inspect_folders(root, env)
    except WorkspaceError:
        return _check("project.links", "skip", "the project marker is unusable (project.plans-store reports it)", "plans")
    if found is None:
        return _check("project.links", "skip", f"no {PROJECT_DIRNAME}/project.json: nothing to link", "plans")
    problems: List[str] = []
    linked: List[str] = []
    listed = read_exclude(root) if exclude_file(root) is not None else None
    for item in found:
        name = item["name"]
        if item["state"] == "foreign":
            problems.append(f"{name}/ is a link to {item['points_to']}, not to {item['target']}; it is left alone")
        elif item["state"] == "linked":
            linked.append(name)
            if item["dangling"]:
                problems.append(f"{name}/ points to {item['target']}, which does not exist")
            elif listed is not None and name not in listed:
                problems.append(f"{name}/ is not listed in .git/info/exclude")
    remedy = "swissknifeman workspace project link (it repairs the links it owns), or remove the stray link"
    if problems:
        return _check("project.links", "warn", "; ".join(problems)[:400], "plans", remedy)
    if not linked:
        return _check("project.links", "skip", "plans/ and tasks/ are not linked to the workspace", "plans")
    return _check("project.links", "ok", f"{', '.join(linked)} linked to the workspace project folder", "plans")


def doctor_checks(root: Path, env: Mapping[str, str]) -> List[Dict[str, Any]]:
    """:func:`verify_checks` plus the project configuration and the write boundary of the project folders."""
    checks = verify_checks(root, env)
    config = project_config_file(root, env=env)
    if not config.exists():
        checks.append(_check("project.config", "skip", f"{config} does not exist (defaults apply)", "config"))
    else:
        from aicore.config import toml
        from aicore.config.model import CONFIG_FILE_VERSION
        try:
            data = toml.loads(config.read_text(encoding="utf-8"), source=str(config))
            version = data.get("schema_version")
            if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= CONFIG_FILE_VERSION:
                checks.append(_check("project.config", "fail", f"{config}: schema_version {version!r} is not "
                                     f"supported (1..{CONFIG_FILE_VERSION})", "config",
                                     f"set schema_version = {CONFIG_FILE_VERSION}"))
            else:
                checks.append(_check("project.config", "ok", f"{config} schema_version {version}", "config"))
        except Exception as exc:  # any parse error is a finding, not a crash of the doctor
            checks.append(_check("project.config", "fail", f"{config}: {exc}"[:400], "config",
                                 "fix the TOML: swissknifeman config explain"))
    checks.extend(local_checks(root, env))
    checks.append(links_check(root, env))
    checks.extend(shellenv.doctor_checks("project", env))
    from aicore.workspace import WorkspaceError, is_workspace_link, resolve_plans_store
    store = None
    store_error = None
    try:
        store = resolve_plans_store(root, env)
    except (WorkspaceError, ValueError) as exc:
        store_error = exc
    # A workspace store lives outside the project by design; only a legacy store must stay inside it.
    # The state and the backups stay inside the project folder that holds them: the checkout, or the project folder of the
    # workspace when the marker names one (``local/``).
    local = project_local_dir(root, env=env)
    home = local.parent if local is not None else root
    boundary = [f"{LOCAL_DIRNAME}/state", f"{LOCAL_DIRNAME}/backups"] if local is not None else \
        [f"{PROJECT_DIRNAME}/state", f"{PROJECT_DIRNAME}/backups"]
    checked = [(home, home / relative) for relative in boundary]
    if (store is None or store.kind == "legacy") and not is_workspace_link(root, "plans", env):
        # a link to the workspace folder of this project (workspace project link) is the workspace store, not an escape
        boundary.append("plans")
        checked.append((root, root / "plans"))
    escaped = []
    for base, candidate in checked:
        try:
            require_project_path(base, candidate)
        except LauncherError as exc:
            escaped.append(str(exc))
    checks.append(_check("project.write-boundary", "fail" if escaped else "ok",
                         "; ".join(escaped) or f"{', '.join(boundary)} stay inside the project", "state",
                         "replace the symlink that leads out of the project with a folder"))
    if store_error is not None:
        observed = str(store_error) if isinstance(store_error, WorkspaceError) else \
            f"{store_error.__class__.__name__}: {store_error}"
        checks.append(_check("project.plans-store", "fail", observed[:400], "plans",
                             "run `swissknifeman workspace clone <url>` or `swissknifeman workspace sync --pull`, "
                             "or fix .swissknifeman/project.json"))
    else:
        checks.append(_check("project.plans-store", "ok",
                             f"{store.kind} store ({store.reason}): {store.plans_root}", "plans"))
    from aicore.workspace.integration import check_project
    findings = check_project(root, env)
    order = ("fail", "warn", "ok", "skip")
    worst = min((item["status"] for item in findings), key=order.index)
    notable = [item for item in findings if item["status"] in ("fail", "warn")] or findings
    checks.append(_check("project.workspace", worst, "; ".join(item["observed"] for item in notable)[:600], "plans",
                         "; ".join(item["remedy"] for item in notable if item["remedy"])[:400]))
    return checks


def _print_checks(checks: List[Dict[str, Any]], as_json: bool, out: TextIO) -> int:
    failed = any(item["status"] == "fail" for item in checks)
    if as_json:
        out.write(json.dumps(checks, indent=2, ensure_ascii=False) + "\n")
    else:
        for item in checks:
            out.write(f"{item['status']} {item['check_id']}: {item['observed']}\n")
        for item in checks:
            if item.get("remediation"):
                out.write(f"  fix {item['check_id']}: {item['remediation']}\n")
    return 1 if failed else 0


def _sync(root: Path, flags: Dict[str, bool], env: Mapping[str, str], out: TextIO, err: TextIO,
          verb: str, marker: Optional[Tuple[str, str, str]] = None) -> int:
    plan = artifacts.plan_sync(root, adopt=flags["--adopt"], marker=marker)
    result = {"$schema": SYNC_SCHEMA, "root": str(root), "dry_run": flags["--dry-run"], **plan}
    refused = [item for item in plan["actions"] if item["action"] == "refused"]
    changes = [item for item in plan["actions"] if item["action"] in ("create", "update")]
    # A marker that cannot be written is a wrong request, not a drift of managed files: nothing is written then.
    blocked = any(item["path"] == artifacts.MARKER for item in refused)
    if not flags["--dry-run"] and changes and not blocked:
        result.update(artifacts.apply_sync(root, plan))
        refused = [item for item in result["actions"] if item["action"] == "refused"]
    _require_document(result, "project-sync", "PROJECT_SYNC_INVALID")
    if flags["--json"]:
        out.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    else:
        for item in result["actions"]:
            note = f" ({item['code']}: {item['reason']})" if item.get("code") else ""
            out.write(f"{'would ' if flags['--dry-run'] and item['action'] in ('create', 'update') else ''}"
                      f"{item['action']} {item['path']}{note}\n")
        if not changes and not refused:
            out.write(f"project {verb}: up to date ({root})\n")
    if refused:
        for item in refused:
            err.write(f"{item['code']}: {item['path']}: {item.get('reason', '')}\n")
        return 1
    if verb == "init" and not flags["--dry-run"] and not flags["--json"]:
        out.write(f"launcher ready: python3 -I {PROJECT_DIRNAME}/launcher.py <group> <args...>  (root {root})\n")
        if marker is not None and project_local_dir(root, env=env) is None:
            out.write(f"note: the workspace {marker[0]} has no project {marker[1]} on this machine; run "
                      f"`swissknifeman workspace project attach` to create it\n")
    return 0


_VALUE_OPTIONS = ("--workspace", "--project", "--plans-store")


def _options(args: Sequence[str], flags: Sequence[str], values: Sequence[str]) -> Tuple[Dict[str, bool], Dict[str, str]]:
    """Split ``args`` into the boolean ``flags`` and the ``values`` options (``--name VALUE`` or ``--name=VALUE``)."""
    found = {name: False for name in flags}
    given: Dict[str, str] = {}
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        name, _equals, inline = arg.partition("=")
        if name in values:
            if inline:
                given[name] = inline
            elif rest and not rest[0].startswith("--"):
                given[name] = rest.pop(0)
            else:
                raise _Usage(f"{name} needs a value")
        elif arg in found:
            found[arg] = True
        else:
            raise _Usage(f"unknown argument {arg!r}")
    return found, given


def _marker_request(root: Path, given: Mapping[str, str], env: Mapping[str, str]) -> Optional[Tuple[str, str, str]]:
    """``(workspace, project_id, plans_store)`` the options ask for, ``None`` when they ask for no marker. The workspace is
    the selected one of this machine; the plans store is ``legacy`` while the checkout holds plan folders, else ``workspace``."""
    if "--project" not in given:
        if given:
            raise _Usage(f"{', '.join(sorted(given))} only goes with --project CODE")
        return None
    from aicore.state import WorkspaceSelectionError, is_code, selected_workspace
    project = given["--project"]
    if not is_code(project):
        raise _Usage(f"--project {project!r} is not a code: lowercase letters, digits and single hyphens, starting with "
                     f"a letter, at most 40 characters")
    workspace = given.get("--workspace")
    if workspace is None:
        try:
            workspace = selected_workspace(env)
        except WorkspaceSelectionError as exc:
            raise LauncherError(exc.code, exc.message) from None
        except ValueError as exc:
            raise _Usage(str(exc)) from None
    elif not is_code(workspace):
        raise _Usage(f"--workspace {workspace!r} is not a code")
    store = given.get("--plans-store")
    if store is None:
        try:
            store = "legacy" if any(child.is_dir() for child in (root / "plans").iterdir()) else "workspace"
        except OSError:
            store = "workspace"
    elif store not in ("workspace", "legacy"):
        raise _Usage("--plans-store is workspace or legacy")
    return workspace, project, store


def _init(args: Sequence[str], env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    flags, given = _options(args, ("--marker-only", "--adopt", "--dry-run", "--json"), _VALUE_OPTIONS)
    context = resolve_project(cwd, env=env)
    if context is None:
        if not flags["--marker-only"]:
            raise ProjectContextRequired(cwd, f"{cwd} is not inside a git repository; run init in the project, or pass "
                                              f"--marker-only to make {cwd} a project with only {PROJECT_DIRNAME}/")
        root = cwd.resolve()
    else:
        root = context.root.resolve()
    return _sync(root, flags, env, out, err, "init", _marker_request(root, given, env))


def _sync_cmd(args: Sequence[str], env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    flags = _flags(args, ("--adopt", "--dry-run", "--json"))
    root = _project(env, cwd).resolve()
    if not launcher_file(root).exists() and not launcher_file(root).is_symlink() and not lock_file(root).exists():
        raise LauncherError("PROJECT_NOT_INITIALIZED", f"{root} has no launcher; run `swissknifeman project init`")
    return _sync(root, flags, env, out, err, "sync")


def _verify(args: Sequence[str], env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    flags = _flags(args, ("--json", "--no-roundtrip"))
    root = _project(env, cwd).resolve()
    return _print_checks(verify_checks(root, env, roundtrip=not flags["--no-roundtrip"]), flags["--json"], out)


MIGRATE_SCHEMA = "urn:swissknifeman:aicore:project-migrate:v1"


def _migrate(args: Sequence[str], env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    flags = _flags(args, ("--dry-run", "--json"))
    root = _project(env, cwd).resolve()
    if flags["--dry-run"]:
        result = migrate.run(root, env, dry_run=True)
    else:
        with artifacts._SyncLock(root):
            result = migrate.run(root, env)
    result = {"$schema": MIGRATE_SCHEMA, "root": str(root), "dry_run": flags["--dry-run"], **result}
    _require_document(result, "project-migrate", "PROJECT_MIGRATE_INVALID")
    blocked = [item for item in result["items"] if item["action"] in ("conflict", "refused")]
    if flags["--json"]:
        out.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    else:
        for item in result["items"]:
            note = f" ({item.get('code') or 'conflict'}: {item['reason']})" if item.get("reason") else ""
            would = "would " if flags["--dry-run"] and item["action"] in ("move", "drop") else ""
            out.write(f"{would}{item['action']} {PROJECT_DIRNAME}/{item['path']}{note}\n")
        if not result["items"]:
            out.write(f"project migrate: nothing to move ({root})\n")
        elif result["applied"] and not blocked:
            out.write(f"moved into {result['local']}; commit the removal of the old files from {PROJECT_DIRNAME}/ "
                      f"if git tracked them\n")
    if blocked:
        for item in blocked:
            err.write(f"{item.get('code') or 'PROJECT_MIGRATE_CONFLICT'}: {PROJECT_DIRNAME}/{item['path']}: "
                      f"{item['reason']}\n")
        return 1
    return 0


def _doctor(args: Sequence[str], env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    flags = _flags(args, ("--json",))
    root = _project(env, cwd).resolve()
    return _print_checks(doctor_checks(root, env), flags["--json"], out)


def _context(args: Sequence[str], env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    flags = _flags(args, ("--json",))
    context = read_invocation_context(cwd, env=env)
    if context.project_root is not None:
        plans_root, plans_store, _error = plans_store_of(context.project_root, env)
        doc = context.to_json(plans_root, plans_store, env=env)
    else:
        doc = context.to_json(env=env)
    if doc["launcher"] is not None and context.project_root is not None:
        try:
            lock = read_lock(context.project_root)
        except LauncherError:
            lock = None
        digest = artifacts._file_digest(launcher_file(context.project_root))
        doc["launcher"]["verified"] = bool(lock) and digest == lock.get("template_sha256") and digest in (
            artifacts.sha256(artifacts.template_bytes()), *artifacts.COMPATIBLE_DIGESTS)
    if flags["--json"]:
        out.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        return 0
    for key in ("project_root", "invocation_cwd", "resolution", "config", "plans_root"):
        out.write(f"{key}: {doc[key]}\n")
    if doc["launcher"]:
        out.write(f"launcher: {doc['launcher']['path']} (protocol {doc['launcher']['protocol']}, "
                  f"verified {str(doc['launcher'].get('verified')).lower()})\n")
    return 0


def _exec(args: Sequence[str], env: Mapping[str, str], cwd: Path, out: TextIO, err: TextIO) -> int:
    rest = list(args[1:] if args and args[0] == "--" else args)
    if not rest:
        raise _Usage("exec needs a command group: swissknifeman project exec -- <group> [args...]")
    root = _project(env, cwd)
    launcher = launcher_file(root)
    if not launcher.is_file():
        raise LauncherError("PROJECT_NOT_INITIALIZED", f"{root} has no launcher; run `swissknifeman project init`")
    out.flush()
    os.execve(sys.executable, [sys.executable, "-I", str(launcher), *rest], _clean_env(env))
    return 1  # not reached


_COMMANDS = {"init": _init, "sync": _sync_cmd, "verify": _verify, "context": _context, "doctor": _doctor,
             "migrate": _migrate, "exec": _exec}


def main(argv: Optional[Sequence[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         cwd: Optional[Path] = None, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    err = err or sys.stderr
    environment = os.environ if env is None else env
    if not args or args[0] in ("-h", "--help", "help"):
        (out if args else err).write(f"usage: swissknifeman project <command>\n\n{USAGE}\n")
        return 0 if args else 2
    command = _COMMANDS.get(args[0])
    if command is None:
        err.write(f"swissknifeman project: unknown command {args[0]!r}\n\n{USAGE}\n")
        return 2
    as_json = "--json" in args[1:]
    try:
        return command(args[1:], environment, Path(cwd) if cwd else Path.cwd(), out, err)
    except _Usage as exc:
        err.write(f"swissknifeman project {args[0]}: {exc}\n\n{USAGE}\n")
        return 2
    except LauncherError as exc:
        if as_json:
            out.write(json.dumps(exc.envelope(), indent=2, ensure_ascii=False) + "\n")
        err.write(f"{exc}\n")
        return 1
    except ProjectContextRequired as exc:
        if as_json:
            out.write(json.dumps({"ok": False, "error": {"code": exc.code, "message": str(exc), "details": {}}},
                                 indent=2, ensure_ascii=False) + "\n")
        err.write(f"{exc}\n")
        return 1
    except OSError as exc:
        err.write(f"PROJECT_IO_ERROR: {exc}\n")
        return 1
