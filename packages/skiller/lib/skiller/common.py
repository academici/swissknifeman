"""General utilities: environment, output, parsing flag'ov and frontmatter.

Verbatim common code (die/warn/now_iso/confirm/sanitize + core Env) moved to the
general core; here - only specifics swissknifeman (path-property, parse_flags,
frontmatter, delegation of the environment to host commands, registry constants)."""
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# General core (connects via PYTHONPATH launcher/test.sh). Re-export for
# package modules, which historically take these names from .common.
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_json, atomic_write_text, confirm, die,
    is_within, is_within_lexical, now_iso, parse_flags,
    parse_inline_list, run_cmd, safe_load_json, sanitize,
    state_dir, warn,
)

# Skill model: moved to aicore.content.skill, re-exported under the historical names
# (after the first ``core`` import, which puts aicore on sys.path).
from aicore.content.skill import (  # noqa: F401
    DEPENDENCY_DIAGNOSTIC_CODES, SKILL_IGNORE, aggregate_dependency_diagnostics,
    resolve_requires_bfs, skill_content_hash,
)
from aicore.content.skill import read_frontmatter as parse_frontmatter  # noqa: F401
from aicore.content.skill import read_frontmatter_fields as parse_frontmatter_fields  # noqa: F401
from aicore.delivery import MARKETPLACE  # noqa: F401

from .host import host_command, load_host

STATE_DIR = state_dir(HOME)
DB_FILE = STATE_DIR / "projects.json"
DB_VERSION = 1
MANIFEST = ".swissknifeman-manifest.json"
MANIFEST_VERSION = 1
AGENT_DEFAULTS = {"claude": ".claude/skills", "cursor": ".cursor/skills",
                  "generic": ".ai/skills"}
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
SKILL_MANAGED_MARKER = "<!-- swissknifeman:managed -->"


def _split_bom(raw):
    """(bom, body) — cut BOM-prefix (if available) without normalizing the rest."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[:3], raw[3:]
    return b"", raw


def _mark_skill_managed(dst):
    """Enter SKILL_MANAGED_MARKER immediately after the closing `---` frontmatter'a
    in `dst/SKILL.md`, BYTE MODE (without text-mode read/normalization `\\r\\n`→`\\n`) —
    old version read the file via `.read_text()`, because of which CRLF-skills
    written bytes diverged from the original ones and `hashlib.sha256(read_bytes())`
    registry (registry.py) detected a false drift on each sync. Idempotent
    (second call - no-op); no file/no frontmatter → quiet no-op (no crash)."""
    path = Path(dst) / "SKILL.md"
    if not path.is_file():
        return
    raw = path.read_bytes()
    bom, body = _split_bom(raw)
    if body.startswith(b"---\r\n"):
        newline = b"\r\n"
    elif body.startswith(b"---\n"):
        newline = b"\n"
    else:
        return  # no frontmatter — not our file, skip
    delim = b"---" + newline
    close_idx = body.find(delim, len(delim))
    if close_idx == -1:
        return  # frontmatter not closed - malformed, pass
    insert_at = close_idx + len(delim)
    marker_bytes = SKILL_MANAGED_MARKER.encode("utf-8")
    if body[insert_at:insert_at + len(marker_bytes)] == marker_bytes:
        return  # already marked - idempotent no-op
    new_body = body[:insert_at] + marker_bytes + newline + body[insert_at:]
    path.write_bytes(bom + new_body)


def strip_skill_managed_marker(data):
    """Reverse to `_mark_skill_managed` — remove marker string from bytes `data`
    (LF or CRLF), returning the original contents byte-for-byte. No marker -
    identity (is not a find, but a regular uninserted file)."""
    marker_bytes = SKILL_MANAGED_MARKER.encode("utf-8")
    for newline in (b"\r\n", b"\n"):
        pattern = marker_bytes + newline
        idx = data.find(pattern)
        if idx != -1:
            return data[:idx] + data[idx + len(pattern):]
    return data


def safe_copy_skill(src, dst, dest_root):
    """Safely copy skill directory src→dst inside dest_root. SINGLE copy path
    for vendor.do_vendor and skillset.sync_skillset (used to be duplicated, diverging into
    security details). Steps: lex. containment (traversal via '../' in name → stop),
    remove existing dst (symlink/file/dir, symlink DO NOT dereference), re-check
    against race (TOCTOU: someone else's process could recreate dst symlink outwards), copytree with
    SKILL_IGNORE. Return True when copying, False when skipping (with warn). is_within/
    is_within_lexical — now from core (re-export above)."""
    if not is_within_lexical(dst, dest_root):
        warn(f"skip: path outside the destination directory: {dst}")
        return False
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        shutil.rmtree(dst)
    if dst.is_symlink() or dst.exists():
        warn(f"pass '{dst.name}': path recreated between deletion and copy (race)")
        return False
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*SKILL_IGNORE))
    return True


def write_skill_manifest(manifest_file, *, profile, agent, layout, installed,
                         support_files=None):
    """ONE writer `.swissknifeman-manifest.json` — common for vendor.do_vendor and
    skillset.sync_skillset (used to be two independent writers with different designs:
    date-only timestamp without `version` y vendor, `now_iso`+`version` y skillset —
    audit V-4, update.detect_vendor_path reads both and could have encountered a discrepancy).
    The unchanged manifest retains the original installed_at and file bytes.
    Atomic (tmp+os.replace), `version` as the first key."""
    stable_data = {
        "profile": profile,
        "agent": agent,
        "layout": layout,
        "skills": installed,
    }
    if support_files is not None:
        stable_data["support_files"] = support_files
    existing = safe_load_json(manifest_file)
    if (isinstance(existing, dict)
            and existing.get("version") == MANIFEST_VERSION
            and isinstance(existing.get("installed_at"), str)
            and existing["installed_at"]
            and {key: value for key, value in existing.items()
                 if key not in {"version", "installed_at"}} == stable_data):
        return
    data = {"installed_at": now_iso(), **stable_data}
    atomic_write_json(manifest_file, data, version=MANIFEST_VERSION)


@dataclass(frozen=True)
class Env(BaseEnv):
    """Launch context swissknifeman: core (root/cmd/home) — from BaseEnv;
    here only path-property registry (state ~/.swissknifeman)."""

    @property
    def state_dir(self):
        return state_dir(self.home)

    @property
    def db_file(self):
        return self.state_dir / "projects.json"

    @property
    def topology_file(self):
        return self.state_dir / "topology.json"


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


# parse_flags — from general core (re-export above); was previously duplicated here.
