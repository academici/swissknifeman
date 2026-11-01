"""The launch plan of a role process: its command line and environment from the route, the options of the piece and
the decisions of the sandbox and the isolation (the profile of the provider: the arguments, the environment and the
home directories that keep its own settings out, ``policies/isolation.py``; the Landlock guard, the paths granted
beside the project, the transcripts of a resumable session)."""
from __future__ import annotations

import json
import os
import ctypes
import platform
from pathlib import Path
import shutil
import stat
from typing import Optional

from aicore.config import ConfigError
from aicore.state import locations

from orch.conductor import options as opts
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import cli_probe, sessions
from orch import launch
from orch.conductor.policies import authority as authority_rules, isolation as isolation_rules, sandbox as sandbox_rules
from orch.conductor.policies import routing as routing_rules
from orch.settings import ORCH_ROOT

TRANSCRIPT_NAME_MAX = 200  # Claude Code shortens a longer folder name and appends a hash it does not publish
# The XDG defaults under HOME: a variable the conductor does not set keeps its place under the original HOME when an
# isolated launch moves HOME (``home.keep_env``: caches are data, not instructions).
XDG_DEFAULTS = {"XDG_CACHE_HOME": ".cache", "XDG_CONFIG_HOME": ".config", "XDG_DATA_HOME": ".local/share",
                "XDG_STATE_HOME": ".local/state"}


def writes(role: str) -> bool:
    """Whether the role may change files (``tools.filesystem`` of its manifest); a role without a manifest might."""
    try:
        manifest = json.loads((ORCH_ROOT / "roles" / f"{role}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return (manifest.get("tools") or {}).get("filesystem") == "write"


def shell(role: str) -> str:
    """``tools.shell`` of the role manifest (``none``, ``read_only``, ``full``); ``full`` for a role without one."""
    try:
        manifest = json.loads((ORCH_ROOT / "roles" / f"{role}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "full"
    return (manifest.get("tools") or {}).get("shell") or "full"


def isolation_plan(self, item: Item, role: str, route: dict, quiet: bool = False) -> dict:
    """:func:`policies.isolation.plan` of ``role`` on ``route``: the profile of its provider, the flags its CLI lists
    (``role_ports.knows``, which says a missing one once per run), its version, the live probes of this machine for that
    version, a drift an earlier role of the run showed, and ``[orch.isolation.<provider>] auth``; ``quiet`` asks the CLI
    without saying a missing flag. A route whose command
    is not a provider CLI the conductor can name (a wrapper, a stand-in) gets the flags as asked, unconfirmed."""
    instructions = (item.options or {}).get("instructions") or {}
    isolated, mode = role in (instructions.get("isolate_roles") or ()), instructions.get("isolation", "prefer")
    provider = route.get("provider") or ""
    if not isolated or mode == "off":
        return isolation_rules.plan(role, route, isolated=isolated, mode=mode, profile=None)
    profile = isolation_rules.load_profiles(isolation_rules.PROFILES_PATH).get(provider)
    probe = {}
    if profile is not None:
        argv, helper, flags = route.get("argv") or [], profile["probe"]["help"], profile["probe"]["flags"]
        every = not flags or (cli_probe.knows if quiet else self.role_ports.knows)(argv, flags, help_argv=helper)
        noted = (getattr(self, "state", None) or {}).get("isolation_noted") or []
        probe = {"listed": {flag: every or cli_probe.knows(argv, [flag], help_argv=helper) for flag in flags},
                 "failed": not every and cli_probe.failed(argv, help_argv=helper),
                 "confirmed": isolation_rules.confirmed(probes(self), provider, cli_probe.version(argv)),
                 "drift": f"{provider}:ISOLATION_DRIFT" in noted, "unprobed": cli_probe.command(argv) is None}
    return isolation_rules.plan(role, route, isolated=True, mode=mode, profile=profile, probe=probe,
                                auth=auth_mode(self, provider))


def probes(self) -> list:
    """The live isolation probes of this machine (``<state>/orch/isolation-probes.json``); a missing, unreadable or
    invalid file confirms nothing (the guarantee stays as the profile declares it)."""
    path = locations.state_dir("orch", env=getattr(self, "env", None)) / isolation_rules.PROBES_FILE
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return []
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [] if isolation_rules.probes_problems(doc) else doc["probes"]


def auth_mode(self, provider: str) -> Optional[str]:
    """``[orch.isolation.<provider>] auth`` (``link`` or ``copy``), ``None`` without settings."""
    resolved = getattr(getattr(self, "settings", None), "resolved", None)
    try:
        table = resolved.get("isolation") if resolved is not None else None
    except ConfigError:
        return None
    return ((table or {}).get(provider) or {}).get("auth")


def prepare_home(run_dir: Path, provider: str, home: dict, original_env: dict) -> dict:
    """The environment of an isolated home (``home`` of the profile of ``provider``): each variable of ``home.vars``
    gets its folder under ``<run dir>/isolation/`` (0700, empty but for auth), the auth files of the original provider
    home (the first variable in ``original_env``, the environment of the conductor before any change, else
    ``<original HOME>/<home.origin>``) are linked into the new one (``mode`` ``copy``: copied), and ``home.keep_env``
    keeps its values. The auth files are never read here."""
    root = Path(run_dir) / "isolation"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    original_home = original_env.get("HOME") or os.path.expanduser("~")
    first = next(iter(home["vars"]))
    origin = Path(original_env.get(first) or Path(original_home) / home["origin"])
    found = {}
    for variable, name in home["vars"].items():
        folder = root / name
        folder.mkdir(mode=0o700, exist_ok=True)
        os.chmod(folder, 0o700)
        found[variable] = str(folder)
    for name in home["auth"]:
        source, placed = origin / name, Path(found[first]) / name
        if os.path.islink(placed) and os.readlink(placed) == str(source) and home["mode"] == "link":
            continue
        if os.path.lexists(placed):
            placed.unlink()
        if home["mode"] == "copy":
            if source.is_file():
                shutil.copyfile(source, placed)
                os.chmod(placed, 0o600)
        else:
            os.symlink(source, placed)
    for variable in home["keep_env"]:
        value = original_env.get(variable) or (str(Path(original_home) / XDG_DEFAULTS[variable])
                                               if variable in XDG_DEFAULTS else None)
        if value:
            found[variable] = value
    return found


def agy_guarded(argv: list, project: str, writing: bool) -> bool:
    """Check the narrow guard before a permission-skipping AGY launch.

    This verifies only the argv boundary. Kernel support and descendant enforcement
    are checked by ro-run; it does not attest provider plugins or remote tools.
    """
    prefix = authority_rules.guard_prefix(argv)
    wanted = "--rw" if writing else "--protect"
    pairs = list(zip(prefix or [], (prefix or [])[1:]))
    permitted = {os.path.realpath(project), "/dev"}
    roots = [os.path.realpath(os.path.expanduser(value)) for flag, value in pairs if flag == "--rw"]
    trusted_guard = str(ORCH_ROOT / "scripts" / "ro-run.py")
    tail = argv[len(prefix) + 1:] if prefix else []
    trusted_bridge = str(ORCH_ROOT / "scripts" / "agy-transport.py")
    return bool(len(tail) >= 2 and tail[0] == "python3" and os.path.realpath(tail[1]) == os.path.realpath(trusted_bridge) and
                prefix and len(prefix) >= 2 and prefix[0] == "python3" and
                os.path.realpath(prefix[1]) == os.path.realpath(trusted_guard) and
                "--no-default-rw" in prefix and (wanted, project) in pairs and
                "/dev" in roots and all(root in permitted for root in roots))


def agy_authority_problem(doc: dict) -> Optional[str]:
    """Fail closed until the role's network, IPC and host read restrictions are enforced."""
    if doc["network"]["declared"] == "none" and doc["network"]["effective"] != "none":
        return "AGY role declares no network but its tools have network access"
    if doc["docker"] != "blocked":
        return "AGY tools can reach the Docker daemon through IPC"
    if doc["read_masks"] == "none":
        return "AGY tools have no enforced host secret read masks"
    return None


def authority(self, item: Item, role: str, route: dict, *, admit: bool = True, quiet: bool = False) -> dict:
    """The ``authority-envelope`` of a launch of ``role`` on ``route`` (:func:`policies.authority.compute`) over the
    facts probed here: the isolation plan, the Claude sandbox, the flags of the CLI, the transcripts folder of a guarded
    Claude Code executor. Every launch computes it, so this is where ``instructions.isolation = require`` refuses a role
    that would start without the full isolation of its profile (``ISOLATION_UNAVAILABLE``: a drift of an earlier role
    since the preflight, a report-fixer or a batch role the preflight does not see, a CLI that cannot keep the project
    settings out); ``admit`` False only computes it (the dry run). ``quiet`` probes the same facts and says nothing,
    creates no folder (the identity of an executor session)."""
    isolation = isolation_plan(self, item, role, route, quiet=quiet)
    refused = isolation_rules.problem(isolation) if admit else None
    if refused:
        raise Stop("ISOLATION_UNAVAILABLE", refused.split(": ", 1)[1])
    if not quiet:
        self.role_ports.note_isolation(item, isolation)
    found = self.role_ports.launch_facts(item, role, route, quiet=quiet)
    facts = found["sandbox"]
    argv = route.get("argv") or []
    refused = routing_rules.registrar_problem({**route, "role": role}, project=str(getattr(self, "project", "")),
                                              access=found["access"])
    if admit and refused:
        raise Stop("LAUNCH_REFUSED", refused.split(": ", 1)[1])
    protected = route.get("provider") == "claude-code" and not writes(role)
    if admit and route.get("provider") == "antigravity":
        if not launch.agy_executor_opted_in(role):
            raise Stop("AGY_AUTHORITY_UNPROVEN", launch.ANTIGRAVITY_AUTHORITY_PROBLEM.split(": ", 1)[1])
        bridge = ["python3", str(ORCH_ROOT / "scripts" / "agy-transport.py"), "--model", route.get("model"),
                  "--effort", route.get("effort")]
        prefix = authority_rules.guard_prefix(argv)
        tail = argv[len(prefix) + 1:] if prefix else []
        if (route.get("transport") != "jsonl" or not writes(role) or not agent_tmpdir(self)
                or not agy_guarded(argv, str(self.project), True) or tail != bridge
                or route.get("resume_argv") or self._scope_option(item, "extra_paths", [])):
            raise Stop("AGY_GUARD_REQUIRED", "antigravity requires an isolated home and narrow Landlock writer guard")
    protection = protection_facts(self.project) if protected else None
    if protection is not None and admit and not protection["available"]:
        raise Stop("PROTECT_UNAVAILABLE", f"{role}/{route['provider']}: the checkout cannot be made read-only "
                   f"({protection['reason']}); move the checkout out of /tmp or /var/tmp, or use a kernel with Landlock ABI >= 3")
    transcripts = None
    if role == "executor" and route.get("provider") == "claude-code" \
            and sessions.shared_session(self, item, role, route, quiet=quiet):
        # else the guard stops the CLI from saving the session it must resume
        transcripts = transcripts_folder(self.project, Path.home(), persist=not quiet and admit)
    listed = None
    if route.get("provider") == "claude-code" and isolation["isolated"]:
        listed = {flag:cli_probe.knows(argv, [flag]) for flag in ("--setting-sources", "--settings")}
    doc = authority_rules.compute(
        role, route, access=found["access"], sandbox=facts, isolation=isolation,
        declared_network=found["declared_network"],
        sandbox_domains=((item.options or {}).get("instructions") or {}).get("sandbox_domains") or [],
        extra_paths=list(self._scope_option(item, "extra_paths", [])), transcripts=transcripts,
        project=str(getattr(self, "project", None) or ""), home=os.path.expanduser("~"), writes=writes(role),
        listed=listed, tmpdir=agent_tmpdir(self), protection=protection)
    agy_problem = agy_authority_problem(doc) if route.get("provider") == "antigravity" else None
    if admit and agy_problem and not launch.agy_executor_opted_in(role):
        raise Stop("AGY_AUTHORITY_UNPROVEN", agy_problem)
    if route.get("provider") == "antigravity" and launch.agy_executor_opted_in(role):
        doc["degraded"].append({"code": "AGY_UNSAFE_EXECUTOR_OPT_IN",
                                "detail": "Explicit local opt-in: network, IPC (including Docker) and host reads are not isolated; "
                                          "/dev including /dev/shm is writable; Landlock ABI below 3 does not prevent "
                                          "truncation outside writable roots; model class for gemini-4-argon-high is unverified."})
        doc["digest"] = authority_rules.digest(doc)
    refused = authority_rules.setting_sources_problem(doc, isolation) if admit else None
    if refused:
        raise Stop("ISOLATION_UNAVAILABLE", refused.split(": ", 1)[1])
    return doc


def role_argv(self, item: Item, role: str, route: dict, decision: Optional[dict] = None, *, admit: bool = True,
              envelope: Optional[dict] = None, resume: Optional[list] = None) -> list:
    """The command line of a role process, built from the authority envelope of the launch (``envelope``, computed by
    :func:`authority` when not given) and the session of the attempt (``decision``; ``resume``, its resume arguments,
    when the caller already has them); ``admit`` False only builds it (the dry run). A resume command whose authority is
    not the one of the route's command is refused (:func:`resume_problem`)."""
    envelope = envelope if envelope is not None else authority(self, item, role, route, admit=admit)
    if resume is None:
        resume = sessions.resume_args(self, item, role, route, decision)  # the decision of the attempt, as it announced it
        refused = resume_problem(self, item, role, route, resume, envelope) if admit else None
        if refused:
            raise Stop("AUTHORITY_RESUME_MISMATCH", refused)
    return argv_from(envelope, route, resume, shared=sessions.shared_session(self, item, role, route),
                     project=str(getattr(self, "project", "")) or None)


def resume_command(route: dict, resume: list) -> Optional[list]:
    """The command an attempt that continues a session runs instead of ``route["argv"]``: the catalog's own
    ``resume_argv`` with the session filled in; ``None`` when the attempt runs the route's command (a fresh session, or
    a provider that resumes with ``--resume`` added to it)."""
    if not resume or not route.get("resume_argv"):
        return None
    return [arg.replace("{session}", resume[0]) for arg in route["resume_argv"]]


def resume_problem(self, item: Item, role: str, route: dict, resume: list, envelope: dict) -> Optional[str]:
    """Why the resume command of an attempt may not run under ``envelope`` (the authority computed, recorded and
    fingerprinted for the route's command): its own authority differs (another guard, grant, sandbox mode, permission
    mode or setting sources), so the process would get what no record names. ``None`` when they are the same."""
    command = resume_command(route, resume)
    if command is None:
        return None
    resumed = self._authority(item, role, {**route, "argv": command}, admit=False, quiet=True)
    if resumed["digest"] == envelope["digest"]:
        return None
    return (f"{role}/{route.get('provider')}: the resume command of the launch catalog has another authority than its "
            f"command ({', '.join(authority_rules.changed_keys(envelope, resumed)) or 'digest'}); the attempt is not "
            "started: make resume_argv grant what argv grants")


def argv_from(envelope: dict, route: dict, resume: list, *, shared: bool, project: Optional[str] = None) -> list:
    """The command line of ``route`` under ``envelope``: the catalog argv (or its resume command), the guard the provider
    sandbox replaces dropped, the ``--rw`` grants of the guard, the ``--add-dir`` grants, the isolation arguments, the
    setting sources, the resume arguments and one ``--settings`` object (the sandbox block and the permissions of orch)."""
    argv = resume_command(route, resume) or list(route["argv"])  # a catalog entry that names its own resume command
    rebuilt = False
    if shared:  # a session that is not saved cannot be resumed by the next executor
        argv = [arg for arg in argv if arg != "--no-session-persistence"]
    if envelope["guard"] == "claude-sandbox":  # bubblewrap cannot start under the Landlock guard: it replaces the guard
        argv = strip_guard(argv)
    elif route.get("provider") == "claude-code" and envelope["guard"] in ("landlock-rw", "landlock-protect") \
            and (authority_rules.guard_prefix(argv) is None or
                 envelope["guard"] == "landlock-protect" and envelope["role"] not in opts.WRITING_ROLES):
        # Rebuild the guard from its recorded roots, including routes that supply no guard of their own.
        argv = strip_guard(argv)
        if not project:
            raise ValueError("a guarded Claude launch needs its checkout path")
        defaults = [{"path": path, "why": "guard"} for path in authority_rules.GUARD_DEFAULT_WRITABLE]
        has_defaults = all(root in envelope["write_roots"] for root in defaults)
        head = ["python3", str(ORCH_ROOT / "scripts" / "ro-run.py")]
        if not has_defaults:
            head += ["--no-default-rw"]
        if envelope["guard"] == "landlock-protect":
            head += ["--protect", project]
        for root in envelope["write_roots"]:
            if has_defaults and root in defaults:
                continue
            path = root["path"]
            path = project + path[1:] if path == "." or path.startswith("./") else os.path.expanduser(path)
            head += ["--rw", path]
        argv = head + ["--"] + argv
        rebuilt = True
    granted = authority_rules.extra_roots(envelope, "extra_paths")
    scratch = authority_rules.extra_roots(envelope, "tmpdir")
    guarded = granted + authority_rules.extra_roots(envelope, "transcripts") + scratch
    if rebuilt:
        guarded = []  # the guard above already contains every root of the envelope
    if guarded and authority_rules.guard_prefix(argv) is not None:
        at = argv.index("--")
        argv = argv[:at] + [part for path in guarded for part in ("--rw", path)] + argv[at:]
    if granted and route.get("provider") == "codex":  # a confined Codex writes beside the project only where it is told
        argv = codex_add_dirs(argv, granted)
    sources = []
    if envelope["setting_sources"] == ["user"] and envelope["permission_rules"]["deny"]:
        if "--setting-sources" in argv[:-1]:
            at = argv.index("--setting-sources") + 1
            argv = argv[:at] + ["user"] + argv[at + 1:]
        else:
            sources = ["--setting-sources", "user"]
    # a Claude Code role reaches a directory outside the project with its file tools only when it is added; the shell
    # of a sandboxed one is granted the same paths in the sandbox block
    added = [part for path in granted + scratch for part in ("--add-dir", path)] if route.get("provider") == "claude-code" else []
    found = authority_rules.settings(envelope) if route.get("provider") == "claude-code" else None
    tail = ["--settings", json.dumps(found, sort_keys=True)] if found else []
    return argv + list(envelope["isolation"]["args"]) + sources + ([] if route.get("resume_argv") else resume) \
        + added + tail


MATRIX_PROJECT = "/project"  # the checkout of the matrix: every path of it is "." in the envelopes


def authority_matrix(catalog: dict) -> list:
    """The authority of every role and provider of ``catalog`` with ``access`` open and confined, on a reference machine:
    the sandbox starts, every CLI lists the flags of its profile, the default options (every role isolated, ``prefer``,
    no extra paths). One row per launch: ``{role, provider, access, guard, network, enforced_by, docker,
    setting_sources, guarantee}`` (``orch.py roles matrix``; the table of docs/conductor.md "Sandboxes")."""
    profiles =isolation_rules.load_profiles(isolation_rules.PROFILES_PATH)
    defaults = opts.DEFAULT_INSTRUCTIONS
    rows = []
    for launch_role, providers in catalog["launch"].items():
        role = "context-scout" if launch_role == "scout" else launch_role
        for provider, entry in providers.items():
            for access in ("open", "confined"):
                argv = launch.build_argv(catalog, launch_role, provider, model="m", effort=entry["effort"],
                                         cwd=MATRIX_PROJECT, access=access)
                route = {"role": role, "provider": provider, "argv": argv}
                profile = profiles.get(provider)
                flags = profile["probe"]["flags"] if profile else []
                isolation = isolation_rules.plan(
                    role, route, isolated=role in defaults["isolate_roles"], mode=defaults["isolation"], profile=profile,
                    probe={"listed": dict.fromkeys(flags, True), "failed": False, "confirmed": [], "drift": False,
                           "unprobed": False})
                doc = authority_rules.compute(
                    role, route, access=access,
                    sandbox={"mode": defaults["sandbox"], "available": True, "reason": None, "settings_listed": True},
                    isolation=isolation, declared_network=sandbox_rules.declared_network(role),
                    sandbox_domains=list(defaults["sandbox_domains"]), extra_paths=[], transcripts=None,
                    project=MATRIX_PROJECT, home="/home/user", writes=writes(role),
                    listed={"--setting-sources": True, "--settings": True})
                rows.append({"role": role, "provider": provider, "access": access, "guard": doc["guard"],
                             "network": doc["network"]["effective"], "enforced_by": doc["network"]["enforced_by"],
                             "docker": doc["docker"],
                             "setting_sources": ",".join(doc["setting_sources"]) if doc["setting_sources"] else None,
                             "guarantee": doc["isolation"]["guarantee"]})
    return rows


def matrix_markdown(rows: list) -> str:
    """The rows of :func:`authority_matrix` as a Markdown table."""
    lines = ["| role | provider | access | guard | network | enforced by | docker | setting sources | isolation |",
             "|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {row['role']} | {row['provider']} | {row['access']} | {row['guard']} | {row['network']} | "
              f"{row['enforced_by'] or '-'} | {row['docker']} | {row['setting_sources'] or 'all'} | {row['guarantee']} |"
              for row in rows]
    return "\n".join(lines) + "\n"


def granted_paths(self, item: Item, role: str) -> list:
    """``scope.extra_paths`` (``~`` expanded) for a role that writes, none for the others."""
    if role not in opts.WRITING_ROLES:
        return []
    return [os.path.expanduser(path) for path in self._scope_option(item, "extra_paths", [])]


def codex_add_dirs(argv: list, paths: list) -> list:
    """``argv`` of a Codex route with ``--add-dir P`` for every path, right after the ``exec`` token."""
    if "exec" not in argv:
        return argv
    at = argv.index("exec") + 1
    return argv[:at] + [part for path in paths for part in ("--add-dir", path)] + argv[at:]


def strip_guard(argv: list) -> list:
    """``argv`` without the ``ro-run.py [--rw DIR]... --`` prefix of the Landlock filesystem guard. Landlock also
    forbids ``mount`` and writes to ``/proc/<pid>/uid_map``, so the bubblewrap sandbox of Claude Code cannot start
    inside it ("bwrap: setting up uid map: Permission denied"); the sandbox confines the shell commands itself."""
    if "--" not in argv or not any(a.endswith("ro-run.py") for a in argv[:2]):
        return argv
    return argv[argv.index("--") + 1:]


def extra_write_dirs(self, item: Item, role: str, argv: list) -> list:
    """``scope.extra_paths`` for a writer (executor, bounded-implementer) started through ``ro-run.py``: one more ``--rw``
    each, before the ``--``. A route that lost the guard to the provider sandbox gets its grants from ``role_argv`` and
    ``sandbox_args``."""
    paths = list(self._scope_option(item, "extra_paths", []))
    if role not in opts.WRITING_ROLES or "--" not in argv or not any(a.endswith("ro-run.py") for a in argv[:2]):
        return argv
    if role == "executor" and self._shared_session(item, role, {"provider": "claude-code"}) \
            and "claude" in argv[argv.index("--") + 1:][:1]:
        folder = self._claude_transcripts()
        if folder:
            paths.append(folder)
    if not paths:
        return argv
    at = argv.index("--")
    return argv[:at] + [part for path in paths for part in ("--rw", os.path.expanduser(path))] + argv[at:]


def transcript_folder_name(project) -> str:
    """The folder name Claude Code gives a project: every UTF-16 code unit outside [A-Za-z0-9] becomes ``-`` (a character
    outside the basic plane is two units, so two dashes)."""
    return "".join(char if char.isascii() and char.isalnum() else "-" * (2 if ord(char) > 0xFFFF else 1) for char in str(project))


def transcripts_folder(project, home: Path, persist: bool = False) -> Optional[str]:
    """The single transcript directory of a project, never the parent holding other projects.

    Claude hashes long names. Only one existing directory with the known prefix identifies its folder.
    A preview (persist=False) never creates directories.
    """
    root = Path(home) / ".claude" / "projects"
    name = transcript_folder_name(project)
    folder = root / name
    if len(name) > TRANSCRIPT_NAME_MAX:
        try:
            matches = [entry for entry in root.iterdir() if entry.is_dir() and not entry.is_symlink()
                       and entry.name.startswith(name[:TRANSCRIPT_NAME_MAX])]
        except OSError:
            return None
        if len(matches) != 1:
            return None
        folder = matches[0]
    if folder.is_symlink():
        return None
    if persist:
        folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def claude_transcripts(self) -> Optional[str]:
    """:func:`transcripts_folder`, created when it is missing (the guard grants a folder that exists)."""
    return transcripts_folder(self.project, Path.home(), persist=True)


def agent_tmpdir(self) -> Optional[str]:
    """The scratch folder of the active agent of this thread (no agent in a preview)."""
    handle = getattr(getattr(self, "_local", None), "agent", None)
    return str(Path(handle["directory"]) / "tmp") if isinstance(handle, dict) else None


def landlock_abi() -> int:
    """Query the kernel without installing a ruleset or starting a process."""
    if platform.system() != "Linux":
        return -1
    return ctypes.CDLL(None, use_errno=True).syscall(444, None, 0, 1)


def protection_facts(project) -> dict:
    """Probe availability of checkout protection; --no-default-rw handles checkouts beneath temporary roots."""
    real = os.path.realpath(project)
    abi = landlock_abi()
    script = ORCH_ROOT / "scripts" / "ro-run.py"
    reason = "ro-run is unavailable" if not script.is_file() else f"Landlock ABI {abi}" if abi < 3 else None
    return {"available": reason is None, "reason": reason,
            "no_default_rw": any(os.path.commonpath((real, root)) == root for root in ("/tmp", "/var/tmp", "/dev")),
            "vendor": (Path(project) / "vendor").is_dir()}


def scope_option(item: Item, key: str, default):
    return (item.options.get("scope") or {}).get(key, default)


def role_env(self, item: Item, role: str, route: dict) -> Optional[dict]:
    """The environment of a role process. A role named in ``instructions.isolate_roles`` starts without the project
    instructions: they carry the rules of a developer's own session ("quality over speed", "fix every defect even
    beyond the scope"), which contradict the role's own scope rules; every role gets exactly the instructions of its
    own prompt. The environment and the home directories come from the isolation profile of the provider
    (:func:`isolation_plan`): a Codex role gets its own CODEX_HOME and HOME under the run folder (:func:`prepare_home`)."""
    isolation = isolation_plan(self, item, role, route)
    scratch = agent_tmpdir(self)
    original = dict(os.environ if self.env is None else self.env)
    if not isolation["env"] and not isolation["home"] and not scratch and launch.AGY_OPT_IN not in original:
        return self.env
    base = {**original, **isolation["env"]}
    base.pop(launch.AGY_OPT_IN, None)
    if scratch:
        base["TMPDIR"] = scratch
        if route.get("provider") == "antigravity":
            base.update({"HOME": scratch, "XDG_CONFIG_HOME": scratch + "/.config",
                         "XDG_CACHE_HOME": scratch + "/.cache", "XDG_DATA_HOME": scratch + "/.local/share",
                         "XDG_STATE_HOME": scratch + "/.local/state"})
    run_dir = getattr(self, "directory", Path())
    if isolation["home"] and run_dir != Path():  # a run that is not opened (the dry run) makes no folders
        base.update(prepare_home(run_dir, isolation["provider"], isolation["home"], original))
    return base
