"""The authority of one launch of a role (``conductor/v1`` ``authority-envelope``): where it may write, what reads are
masked, which settings of the provider it loads, the permission rules of orch, the network, Docker and git, its
isolation and what is degraded. One pure function computes it from the route and the facts the caller probed
(``compute``); the command line of the launch is built from the document (``infrastructure/launch_plan.argv_from``), the
document is written before the process starts (``agents/<id>/authority/a<attempt>.json``) and its digest is compared
between the launches of a role (``AUTHORITY_CHANGED``) and kept in the fingerprint of an executor session.

The function reads no file of a provider (``.claude/settings*.json``, ``.codex``, ``.grok``), creates nothing and starts
no process: the sandbox probe, the flags the CLI lists, the isolation plan and the transcripts folder are arguments. The
document holds names of environment variables and path templates only: the HOME of the machine is ``~`` and the
checkout is ``.``, so the same authority on two machines has one digest."""
from __future__ import annotations

import json
import os
from typing import Optional

from aicore.util.digest import sha256_hex

from orch.conductor import options as opts
from orch.conductor.policies import sandbox as sandbox_rules

SCHEMA = "urn:swissknifeman:orch:conductor:authority-envelope:v1"
GUARDS = ("landlock-rw", "landlock-protect", "claude-sandbox", "codex-sandbox", "none")
# The deny rules orch gives every Claude Code role it starts with ``--setting-sources user``: the project settings that
# carried the ask and deny rules of git push, reset --hard and clean are no longer loaded, so these come with the launch
# (the meaning of the shared Claude Code settings presets of a project, without depending on any of them).
ORCH_PERMISSION_RULES = {"deny": ["Bash(git push*)", "Bash(git reset --hard*)", "Bash(git clean*)",
                                  "Bash(git config --global --add *)", "Bash(git config --global --unset*)",
                                  "Bash(git config --global --replace-all *)", "Bash(git config --global --edit*)",
                                  "Bash(git config --global *.* *)", "Bash(sudo *)", "Read(.env)", "Read(.env.*)",
                                  "Bash(cat .env)", "Bash(cat .env.*)",
                                  "Read(**/*.pem)", "Read(**/*.key)", "Read(~/.ssh/**)", "Read(~/.aws/**)"],
                         "ask": []}
NO_RULES = {"deny": [], "ask": []}
SANDBOX_BLOCK = {"enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True}
PROMPT_ROLES = ("executor", "bounded-implementer")  # the writers whose prompt carries the authority block
PROMPT_LINES = 12
# What scripts/ro-run.py leaves writable besides its --rw grants unless --no-default-rw (its DEFAULT_WRITABLE; a test
# keeps the two equal): the guard grants them to every launch it confines.
GUARD_DEFAULT_WRITABLE = ("/tmp", "/var/tmp", "/dev")
CODEX_CONFINED = ("read-only", "workspace-write")


def guard_prefix(argv: list) -> Optional[list]:
    """The ``ro-run.py [--rw DIR | --protect DIR]... --`` prefix of the Landlock guard of ``argv``, ``None`` without one."""
    if "--" not in argv or not any(arg.endswith("ro-run.py") for arg in argv[:2]):
        return None
    return argv[:argv.index("--")]


def sandbox_applies(route: dict, sandbox: dict, *, access: str = "confined", writes: bool = True) -> bool:
    """The Claude Code sandbox confines the commands of the role: a Claude Code role with Bash, ``instructions.sandbox``
    not ``off``, a sandbox that starts and a CLI that lists ``--settings`` (``sandbox`` holds what the caller probed:
    ``mode``, ``available``, ``settings_listed``)."""
    return access != "open" and writes and sandbox.get("mode") != "off" and bool(route.get("argv")) and sandbox_rules.claude_bash(route) \
        and bool(sandbox.get("available")) and bool(sandbox.get("settings_listed"))


def _value(argv: list, flag: str) -> Optional[str]:
    return argv[argv.index(flag) + 1] if flag in argv[:-1] else None


def codex_mode(argv: list) -> Optional[str]:
    """The sandbox mode of a Codex command line: ``--sandbox MODE`` (``codex exec``) or ``-c sandbox_mode="MODE"`` (``codex
    exec resume``, which has no ``--sandbox``); ``None`` when it names none."""
    named = _value(argv, "--sandbox")
    if named:
        return named
    for at, arg in enumerate(argv[:-1]):
        if arg == "-c" and argv[at + 1].startswith("sandbox_mode="):
            return argv[at + 1].split("=", 1)[1].strip("\"'")
    return None


def _expand(path: str, home: str) -> str:
    return home + path[1:] if path == "~" or path.startswith("~/") else path


def tilde(path: str, home: str) -> str:
    """``path`` with the HOME of the machine as ``~``."""
    home = home.rstrip("/")
    if home and (path == home or path.startswith(home + "/")):
        return "~" + path[len(home):]
    return path


def _root(path: str, project: str, home: str) -> str:
    """A write root as a template: ``.`` for the checkout, ``./<rel>`` under it, ``~/...`` under HOME."""
    project = project.rstrip("/")
    if not project:  # a facade without a project (a test of a launch rule): the paths stay as they are
        return tilde(path, home)
    if path == project:
        return "."
    if path.startswith(project + "/"):
        return "./" + path[len(project) + 1:]
    return tilde(path, home)


def compute(role: str, route: dict, *, access: str, sandbox: dict, isolation: dict, declared_network: str,
            sandbox_domains: list, extra_paths: list, transcripts: Optional[str], project: str, home: str,
            writes: bool, listed: Optional[dict] = None, tmpdir: Optional[str] = None,
            protection: Optional[dict] = None) -> dict:
    """The ``authority-envelope`` of a launch of ``role`` on ``route``. ``access`` is ``[orch.launch] access``,
    ``sandbox`` the probed facts of the Claude sandbox (:func:`sandbox_applies`), ``isolation`` the plan of
    ``policies/isolation.plan``, ``declared_network`` ``tools.network`` of the role manifest, ``sandbox_domains`` and
    ``extra_paths`` the options of the piece, ``transcripts`` the folder a guarded Claude Code executor must keep its
    session in (or ``None``), ``writes`` whether the manifest lets the role change files and ``listed`` whether the CLI
    lists ``--setting-sources`` and ``--settings`` (asked for an isolated Claude Code role only). The decisions follow
    the command line the launch catalog gives: (1) the guard, (2) the write roots, (3) the setting sources, (4) the
    permission rules, (5) the network and Docker, (6) git, (7) the isolation."""
    argv, provider = list(route.get("argv") or []), route.get("provider") or ""
    route = {**route, "argv": argv}
    prefix = guard_prefix(argv)
    shell = sandbox_rules.claude_bash(route)  # a Claude Code shell the sandbox can confine (Bash named in --tools)
    # a Claude Code role whose --tools leave Bash out runs no command at all; without --tools it has every tool
    no_shell = provider == "claude-code" and "--tools" in argv[:-1] and not shell
    degraded: list = []
    # (1) the guard: the provider sandbox replaces the Landlock guard it cannot start under
    protected = provider == "claude-code" and not writes
    applies = sandbox_applies(route, sandbox, access=access, writes=writes)
    if protected:
        guard = "landlock-protect"
    elif applies:
        guard = "claude-sandbox"
    elif prefix is not None:
        guard = "landlock-rw" if "--rw" in prefix and "--protect" not in prefix else "landlock-protect"
    elif provider == "claude-code" and writes:
        guard = "landlock-rw"
    elif provider == "codex" and codex_mode(argv) in CODEX_CONFINED:
        guard = "codex-sandbox"
    else:
        guard = "none"
    if shell and writes and access != "open" and sandbox.get("mode") != "off" and guard != "claude-sandbox":
        if not sandbox.get("available"):
            degraded.append({"code": "SANDBOX_UNAVAILABLE",
                             "detail": f"the sandbox cannot start ({sandbox.get('reason') or 'unknown'})"})
        elif not sandbox.get("settings_listed"):
            degraded.append({"code": "SETTINGS_UNSUPPORTED", "detail": "the claude CLI does not list --settings"})
    # (2) where writes may land; the paths of scope.extra_paths and the transcripts are granted by the launch
    roots = []
    if protected:
        if not (protection or {}).get("no_default_rw"):
            roots += [{"path": path, "why": "guard"} for path in GUARD_DEFAULT_WRITABLE]
        else:
            roots.append({"path": "/dev", "why": "guard"})
        if tmpdir:
            roots.append({"path": tilde(tmpdir, home), "why": "tmpdir"})
        if (protection or {}).get("vendor"):
            roots.append({"path": "./vendor", "why": "guard"})
    elif guard == "landlock-rw" and prefix is None:
        roots += [{"path": path, "why": "guard"} for path in GUARD_DEFAULT_WRITABLE]
        roots.append({"path": ".", "why": "checkout"})
    elif prefix is not None and guard != "claude-sandbox":
        # in the order of the guard: its default writable roots (unless --no-default-rw), then its --rw grants
        if "--no-default-rw" not in prefix:
            roots += [{"path": path, "why": "guard"} for path in GUARD_DEFAULT_WRITABLE]
        roots += [{"path": _root(prefix[at + 1], project, home),
                   "why": "checkout" if project and prefix[at + 1].rstrip("/") == project.rstrip("/") else "guard"}
                  for at, arg in enumerate(prefix[:-1]) if arg == "--rw"]
    elif guard == "claude-sandbox" or (guard == "codex-sandbox" and codex_mode(argv) == "workspace-write"):
        roots.append({"path": ".", "why": "checkout"})
    elif guard == "none" and (provider == "codex" or (writes and not no_shell)):
        roots.append({"path": "/", "why": "unconfined"})  # nothing confines the commands of the role
    elif guard == "none" and writes:
        roots.append({"path": ".", "why": "checkout"})  # the file tools of a Claude Code role without a shell
    if role in opts.WRITING_ROLES:
        roots += [{"path": tilde(_expand(path, home), home), "why": "extra_paths"} for path in extra_paths]
    if transcripts:
        roots.append({"path": tilde(transcripts, home), "why": "transcripts"})
    if tmpdir and not protected:
        roots.append({"path": tilde(tmpdir, home), "why": "tmpdir"})
    # (3) the setting sources: an isolated Claude Code role loads only the settings of the user, not those of the project
    named = _value(argv, "--setting-sources")
    setting_sources = named.split(",") if named else None
    rules = NO_RULES
    if provider == "claude-code" and isolation.get("isolated"):
        if (listed or {}).get("--setting-sources") and (listed or {}).get("--settings"):
            setting_sources, rules = ["user"], ORCH_PERMISSION_RULES  # (4) never one without the other
        else:
            degraded.append({"code": "SETTING_SOURCES_UNSUPPORTED",
                             "detail": "the claude CLI does not list --setting-sources and --settings: the settings of "
                                       "the project reach the role"})
    # (5) the network and Docker
    if guard == "claude-sandbox" and declared_network != "allowed":
        domains = list(sandbox_domains or [])
        network = {"declared": declared_network, "effective": "allowlist" if domains else "none",
                   "enforced_by": "claude-sandbox", "allowed_domains": domains}
    elif guard == "codex-sandbox":
        network = {"declared": declared_network, "effective": "none", "enforced_by": "codex-sandbox",
                   "allowed_domains": []}
    elif no_shell:
        network = {"declared": declared_network, "effective": "none", "enforced_by": "claude-tools",
                   "allowed_domains": []}
    else:
        network = {"declared": declared_network, "effective": "open", "enforced_by": None, "allowed_domains": []}
    if declared_network == "none" and network["effective"] == "open":
        degraded.append({"code": "NETWORK_UNENFORCED",
                         "detail": f"{provider or 'the provider'} confines no network of its commands here"})
    docker = "blocked" if guard in ("claude-sandbox", "codex-sandbox") or no_shell else "open"
    # (6) git: the commit is the work source's. push, reset --hard and clean are denied only by a command deny layer
    # (the permission rules of orch) or by a role that runs no command; a filesystem confinement filters no command:
    # what it keeps out is said by write_roots and dot_git_write
    kept_out = guard in ("codex-sandbox", "landlock-protect", "claude-sandbox") or no_shell
    refused = "denied" if rules["deny"] or no_shell else "unenforced"
    git = {"commit": "work-source", "push": refused, "reset_hard": refused, "clean": refused,
           "dot_git_write": not kept_out and any(root["why"] in ("checkout", "unconfined") for root in roots)}
    # (7) the isolation of the profile, by names only
    home_vars = list(((isolation.get("home") or {}).get("vars") or {}))
    env_keys = set(isolation.get("env") or {})
    if provider == "antigravity" and tmpdir:
        home_vars = ["HOME"]
        env_keys.update(("HOME", "TMPDIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"))
    degraded = list(isolation.get("degraded") or []) + degraded
    doc = {"$schema": SCHEMA, "role": role, "provider": provider, "access": access, "guard": guard,
           "write_roots": roots, "read_masks": "provider-settings" if guard == "claude-sandbox" else "none",
           "setting_sources": setting_sources, "permission_mode": "always-proceed" if provider == "antigravity" else _value(argv, "--permission-mode"),
           "permission_rules": {"deny": list(rules["deny"]), "ask": list(rules["ask"])},
           "network": network, "docker": docker, "git": git,
           "isolation": {"profile": provider if isolation.get("isolated") and isolation.get("guarantee") != "none"
                         else None,
                         "guarantee": isolation.get("guarantee") or "none", "args": list(isolation.get("args") or []),
                         "env_keys": sorted(env_keys), "home_var": home_vars[0] if home_vars else None},
           "degraded": degraded}
    doc["digest"] = digest(doc)
    return doc


def digest(doc: dict) -> str:
    """``sha256:`` + sha256 of the canonical JSON of ``doc`` without ``digest`` (keys sorted, no spaces)."""
    body = {key: value for key, value in doc.items() if key != "digest"}
    return "sha256:" + sha256_hex(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def changed_keys(old: Optional[dict], new: dict) -> list:
    """The top-level keys whose values differ between two envelopes (``digest`` aside)."""
    if not old:
        return []
    return sorted(key for key in set(old) | set(new) if key != "digest" and old.get(key) != new.get(key))


def extra_roots(doc: dict, why: str) -> list:
    """The write roots of ``doc`` granted for ``why`` (``extra_paths``, ``transcripts``) as absolute paths."""
    return [os.path.expanduser(root["path"]) for root in doc["write_roots"] if root["why"] == why]


def settings(doc: dict) -> Optional[dict]:
    """The ``--settings`` object of a Claude Code launch: the ``sandbox`` block when the sandbox confines the role (a
    write grant for ``scope.extra_paths``, the allowlist of its network) and the ``permissions`` of orch when the role
    loads only the settings of the user; ``None`` when there is neither."""
    found: dict = {}
    if doc["guard"] == "claude-sandbox":
        block: dict = dict(SANDBOX_BLOCK)
        granted = extra_roots(doc, "extra_paths") + extra_roots(doc, "tmpdir")
        if granted:
            block["filesystem"] = {"allowWrite": granted}
        if doc["network"]["enforced_by"] == "claude-sandbox":
            block["network"] = {"strictAllowlist": True, "allowedDomains": list(doc["network"]["allowed_domains"])}
        found["sandbox"] = block
    rules = doc["permission_rules"]
    if rules["deny"] or rules["ask"]:
        found["permissions"] = {key: list(rules[key]) for key in ("deny", "ask") if rules[key]}
    return found or None


def setting_sources_problem(doc: dict, isolation: dict) -> Optional[str]:
    """``ISOLATION_UNAVAILABLE: ...`` when ``instructions.isolation`` is ``require`` and an isolated Claude Code role
    would still load the settings of the project (the CLI does not list ``--setting-sources``: the surface
    ``project_permissions`` stays on)."""
    if isolation.get("mode") != "require" or not isolation.get("isolated"):
        return None
    if not any(entry["code"] == "SETTING_SOURCES_UNSUPPORTED" for entry in doc["degraded"]):
        return None
    return (f"ISOLATION_UNAVAILABLE: {doc['role']}/{doc['provider']}: the project permissions reach the role (the claude "
            "CLI does not list --setting-sources and --settings); set instructions.isolation = prefer in a trusted layer "
            "or remove the role from isolate_roles")


def prompt_block(doc: dict) -> str:
    """The ``authority`` section of the prompt of a writer (at most ``PROMPT_LINES`` lines), from ``doc`` only: where it
    may write, the network, Docker, what git forbids and what to do when a check needs what it does not have. The
    paths of ``scope.extra_paths`` (named by the write fence of the prompt) and the transcripts folder are said, not
    listed: they are absolute paths of this machine."""
    roots = [root["path"] for root in doc["write_roots"] if root["why"] not in ("extra_paths", "transcripts", "tmpdir")]
    named = [f"`{path}`" for path in roots]
    if any(root["why"] == "extra_paths" for root in doc["write_roots"]):
        named.append("the extra paths of the write fence")
    if any(root["why"] == "transcripts" for root in doc["write_roots"]):
        named.append("the transcripts folder of your session")
    # Every launched agent receives private scratch, even when a preview has no agent directory yet.
    named.append("your TMPDIR")
    where = "anywhere this user can" if "/" in roots else ", ".join(named) or "nowhere"
    network = doc["network"]
    reach = {"none": "none", "open": "open",
             "allowlist": "only " + ", ".join(network["allowed_domains"])}[network["effective"]]
    git = doc["git"]
    forbidden = [name.replace("_", " --") if name == "reset_hard" else name
                 for name in ("push", "reset_hard", "clean") if git[name] == "denied"]
    lines = ["## Authority", "",
             f"- Writes: {where} (guard {doc['guard']}).",
             f"- Network: {reach}" + (f", enforced by {network['enforced_by']}." if network["enforced_by"] else "."),
             "- Docker: " + ("you may use containers, the docker socket and compose." if doc["docker"] == "open"
                             else "not available here: do not start containers or call docker or compose."),
             "- Git: the conductor commits through the work source; do not commit yourself"
             + ("; " + ", ".join(f"git {name}" for name in forbidden) + " are denied." if forbidden else "."),
             "- A check that needs what this authority does not give is not a blocker: name it in an `open_issues` "
             "entry of kind `pending` and go on."]
    return "\n".join(lines[:PROMPT_LINES])
