"""Skiller environment: the launch context (`Env`), delegation to host commands and registry
constants. General helpers (output, flags, frontmatter, managed copies) live in `aicore` and are
imported from there directly."""
import subprocess
import sys
from dataclasses import dataclass

from aicore.util.env import BaseEnv
from aicore.state import resolve_with_legacy
from aicore.state import state_dir as _state_dir
from aicore.util.term import warn

from .host import host_command, load_host

DB_VERSION = 1
# CONFIG_KEYS lives HERE named (it is taken by both gates synchronous with the circuit -
# doctor.py and tests/test_schema.py — and documentation), but the value is from 2026-08-02
# (P6.2) OUTPUT from fields skiller.config.ProjectConfig: list of keys
# .swissknife.json has exactly one medium - the config object. There are also comments
# about multi-type memory_brain, reserved shape/stacks/skills_map and
# policy_profile (D11). Import is lazy (PEP 562 module __getattr__): config
# imports common on module-level, therefore feedback is only possible by
# requirement - otherwise import loop.
def __getattr__(name):
    if name == "CONFIG_KEYS":
        from .config import CONFIG_KEYS as derived
        globals()["CONFIG_KEYS"] = derived  # memoization: __getattr__ is no longer called
        return derived
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


HUB_MARKER = "<!-- swissknifeman:hub:start -->"


@dataclass(frozen=True)
class Env(BaseEnv):
    """Launch context swissknifeman: core (root/cmd/home) — from BaseEnv;
    here only path-property registry (state in the aicore.state place)."""

    @property
    def state_dir(self):
        """``<state>/skiller`` (the connected-projects registry)."""
        return _state_dir("skiller", home=self.home)

    @property
    def db_file(self):
        """Connected-projects registry ``<state>/skiller/projects.json``. The legacy
        ``~/.swissknifeman/projects.json`` is used, with one warning, until the new file
        exists (file by file: that directory also holds other modules' files)."""
        return resolve_with_legacy(self.state_dir / "projects.json",
                                   [self.home / ".swissknifeman" / "projects.json"],
                                   home=self.home)


def host_command_text(env, name, *args):
    """Display text of host command `name` (configured argv, unresolved) plus `args`,
    or None without a host command — for `next_command` hints, never executed."""
    command = load_host(env.root).commands.get(name)
    return " ".join((*command.argv, *args)) if command else None


def host_install_suffix(env, name):
    """` (install: <hint>)` from host command `name`, or "" without a hint."""
    command = load_host(env.root).commands.get(name)
    hint = command.install_hint if command else None
    return f" (install: {hint})" if hint else ""


def apply_permissions(env, target, presets="", dry_run=False, settings_file=None):
    """Pour in permissions-presets in .claude targets - delegated to the host's
    `permissions` command (subprocess; environment settings live outside skiller).
    presets="" → stack autodetect. Returns True, if the command started; False (with
    warn) — if it is not configured or not installed (empty host = not installed)."""
    argv = host_command(env, "permissions")
    if argv is None:
        warn("permissions command not configured or not installed - skip permissions"
             + host_install_suffix(env, "permissions"))
        return False
    cmd = [*argv, "--target", str(target)]
    if presets:
        cmd += ["--preset", presets]
    if settings_file:
        cmd += ["--file", settings_file]
    if dry_run:
        cmd.append("--dry-run")
    sys.stdout.flush()
    # timeout: a stuck command (NFS/network) should not freeze `skiller sync` silently.
    # stderr catch in warn; stdout we leave alive (the command prints progress itself).
    try:
        result = subprocess.run(cmd, check=False, timeout=30,
                                stderr=subprocess.PIPE, text=True)
    except subprocess.TimeoutExpired:
        warn("permissions command: timeout exceeded 30s — permissions might not apply")
        return True
    if result.returncode != 0:
        # Previously warn was only when non-empty stderr → silent non-null rc hid that
        # permissions-presets (deny garbage/allow stack) DID NOT lie down. We always inform you.
        detail = result.stderr.strip() if result.stderr else f"exit {result.returncode}"
        warn(f"permissions command did not apply ({detail}) — presets deny/allow might not "
             f"have gone to bed; restart: {' '.join(argv)} --target {target}")
    return True

