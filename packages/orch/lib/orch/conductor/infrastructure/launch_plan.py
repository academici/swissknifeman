"""The launch plan of a role process: its command line and environment from the route, the options of the piece and
the decisions of the sandbox and the isolation (the profile of the provider: the arguments, the environment and the
home directories that keep its own settings out, ``policies/isolation.py``; the Landlock guard, the paths granted
beside the project, the transcripts of a resumable session)."""
from __future__ import annotations

import json
import os
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
    transcripts = None
    if role == "executor" and authority_rules.guard_prefix(argv) is not None \
            and not authority_rules.sandbox_applies(route, facts) and "claude" in argv[argv.index("--") + 1:][:1] \
            and self._shared_session(item, role, {"provider": "claude-code"}):
        # else the guard stops the CLI from saving the session it must resume
        transcripts = transcripts_folder(self) if quiet else self._claude_transcripts()
    listed = None
    if route.get("provider") == "claude-code" and isolation["isolated"]:
        listed = {flag:cli_probe.knows(argv, [flag]) for flag in ("--setting-sources", "--settings")}
    doc = authority_rules.compute(
        role, route, access=found["access"], sandbox=facts, isolation=isolation,
        declared_network=found["declared_network"],
        sandbox_domains=((item.options or {}).get("instructions") or {}).get("sandbox_domains") or [],
        extra_paths=list(self._scope_option(item, "extra_paths", [])), transcripts=transcripts,
        project=str(getattr(self, "project", None) or ""), home=os.path.expanduser("~"), writes=writes(role),
        listed=listed)
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
    return argv_from(envelope, route, resume, shared=sessions.shared_session(self, item, role, route))


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


def argv_from(envelope: dict, route: dict, resume: list, *, shared: bool) -> list:
    """The command line of ``route`` under ``envelope``: the catalog argv (or its resume command), the guard the provider
    sandbox replaces dropped, the ``--rw`` grants of the guard, the ``--add-dir`` grants, the isolation arguments, the
    setting sources, the resume arguments and one ``--settings`` object (the sandbox block and the permissions of orch)."""
    argv = resume_command(route, resume) or list(route["argv"])  # a catalog entry that names its own resume command
    if shared:  # a session that is not saved cannot be resumed by the next executor
        argv = [arg for arg in argv if arg != "--no-session-persistence"]
    if envelope["guard"] == "claude-sandbox":  # bubblewrap cannot start under the Landlock guard: it replaces the guard
        argv = strip_guard(argv)
    granted = authority_rules.extra_roots(envelope, "extra_paths")
    guarded = granted + authority_rules.extra_roots(envelope, "transcripts")
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
    added = [part for path in granted for part in ("--add-dir", path)] if route.get("provider") == "claude-code" else []
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
        paths.append(self._claude_transcripts())  # else the guard stops the CLI from saving the session it must resume
    if not paths:
        return argv
    at = argv.index("--")
    return argv[:at] + [part for path in paths for part in ("--rw", os.path.expanduser(path))] + argv[at:]


def transcript_folder_name(project) -> str:
    """The folder name Claude Code gives a project: every UTF-16 code unit outside [A-Za-z0-9] becomes ``-`` (a character
    outside the basic plane is two units, so two dashes)."""
    return "".join(char if char.isascii() and char.isalnum() else "-" * (2 if ord(char) > 0xFFFF else 1) for char in str(project))


def transcripts_folder(self) -> str:
    """The folder where Claude Code keeps the transcripts of this project: ``~/.claude/projects/<path with every
    character outside [A-Za-z0-9] as -``. It is the one place besides the project that a resumable session needs. A
    path whose folder name would pass ``TRANSCRIPT_NAME_MAX`` gets a name with a hash suffix that is not known here: the
    whole ``~/.claude/projects`` is then writable for the executor (the transcripts of the other projects too)."""
    root = Path.home() / ".claude" / "projects"
    name = transcript_folder_name(self.project)
    return str(root if len(name) > TRANSCRIPT_NAME_MAX else root / name)


def claude_transcripts(self) -> str:
    """:func:`transcripts_folder`, created when it is missing (the guard grants a folder that exists)."""
    folder = Path(transcripts_folder(self))
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def scope_option(item: Item, key: str, default):
    return (item.options.get("scope") or {}).get(key, default)


def role_env(self, item: Item, role: str, route: dict) -> Optional[dict]:
    """The environment of a role process. A role named in ``instructions.isolate_roles`` starts without the project
    instructions: they carry the rules of a developer's own session ("quality over speed", "fix every defect even
    beyond the scope"), which contradict the role's own scope rules; every role gets exactly the instructions of its
    own prompt. The environment and the home directories come from the isolation profile of the provider
    (:func:`isolation_plan`): a Codex role gets its own CODEX_HOME and HOME under the run folder (:func:`prepare_home`)."""
    isolation = isolation_plan(self, item, role, route)
    if not isolation["env"] and not isolation["home"]:
        return self.env
    original = dict(os.environ if self.env is None else self.env)  # the environment of the conductor, before any change
    base = {**original, **isolation["env"]}
    run_dir = getattr(self, "directory", Path())
    if isolation["home"] and run_dir != Path():  # a run that is not opened (the dry run) makes no folders
        base.update(prepare_home(run_dir, isolation["provider"], isolation["home"], original))
    return base
