"""General utilities: environment, output, parsing flag'ov and frontmatter.

Verbatim common code (die/warn/now_iso/confirm/sanitize + core Env) moved to the
general core; here - only specifics swissknifeman (path-property, parse_flags,
frontmatter, delegation of the environment to host commands, registry constants)."""
import hashlib
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
from core import parse_frontmatter as _core_parse_frontmatter

from .host import host_command, load_host

STATE_DIR = state_dir(HOME)
DB_FILE = STATE_DIR / "projects.json"
DB_VERSION = 1
MARKETPLACE = "swissknifeman"
MANIFEST = ".swissknifeman-manifest.json"
MANIFEST_VERSION = 1
AGENT_DEFAULTS = {"claude": ".claude/skills", "cursor": ".cursor/skills",
                  "generic": ".ai/skills"}
# Skill catalog files that are NOT sent to the consuming project by any channel
# physical transfer (vendor/sync): upstream.json and .claude-plugin — service registry;
# SKILL.*.md — non-canonical localized/reference alternates ("SKILL.*.md" not
# matches itself EN-only "SKILL.md"); evals/ — behavioral tests
# skill; __pycache__/*.pyc — bytecode cache, appears locally when launched manually
# .py-snippets (e.g. snippets/check.py) — found while investigating unstable
# content_sha256 for the skill with .py-snippets (registry --check turned green locally and
# drifted in a clean checkout/CI). THE SINGLE source of truth: vendor.copy_skill and
# skillset.sync copy through it (used to be duplicated and skillset lost
# SKILL.*.md/evals → leak RU-source).
SKILL_IGNORE = ("upstream.json", ".claude-plugin", "SKILL.*.md", "evals",
                "__pycache__", "*.pyc", "*.provider-artifact.bak")
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


# --- frontmatter --------------------------------------------------------------
# Analysis moved to general core.text (single source for every package).
# Here all that remains is to read the file: utf-8-sig cuts BOM, if available (otherwise
# `﻿---` != `---` and all frontmatter would be silently ignored).
def parse_frontmatter(path):
    """Frontmatter skill along the way (core.parse_frontmatter on top utf-8-sig-read)."""
    return _core_parse_frontmatter(Path(path).read_text(encoding="utf-8-sig"))


def parse_frontmatter_fields(skill_md):
    """name + requires from the first ----delimited block."""
    fm = parse_frontmatter(skill_md)
    return {"name": fm.get("name", ""),
            "requires": parse_inline_list(fm.get("requires", ""))}


# --- requires (transitive dependency BFS) --------------------------------------
DEPENDENCY_DIAGNOSTIC_CODES = frozenset({
    "SKILL_REQUIRED_EXCLUDED",
    "SKILL_REQUIRED_UNKNOWN",
})


def aggregate_dependency_diagnostics(diagnostics):
    """Collapse dependency failures into stable machine-readable diagnostics.

    Human warnings remain owned by :func:`resolve_requires_bfs`; this projection is
    deliberately message-free so localization cannot change diagnostic identity.
    Repeated observations of the same ``code``/required skill are represented once,
    with the complete sorted requester set in ``affected_identities``.
    """
    grouped = {}
    for item in diagnostics:
        code = item.get("code")
        required = item.get("required_skill")
        requester = item.get("requester")
        if (code not in DEPENDENCY_DIAGNOSTIC_CODES
                or not isinstance(required, str) or not required
                or not isinstance(requester, str) or not requester):
            continue
        grouped.setdefault((code, required), set()).add(requester)
    return [
        {
            "code": code,
            "severity": "warning",
            "required_skill": required,
            "affected_identities": sorted(requesters),
        }
        for (code, required), requesters in sorted(grouped.items())
    ]


def resolve_requires_bfs(seed, lookup, selected_keys, exclude, *, diagnostics=None):
    """Transitive BFS resolve frontmatter `requires` — SINGLE source for
    vendor.resolve_requires (FS-tuples) and skillset._pull_requires (registry-entry):
    before these were two independent, already diverged bodies (RU/EN texts warn,
    audit V-1). The caller adapts its data model to the dictionary node via `lookup`.

    seed: [(dep_name, requester_key), ...] — start queue (requires already
        selected skills).
    lookup(dep_name) -> {"key", "requires": [str], "exclude_tokens": set[str], ...} | None
        — resolve dependency name to node; None — dependency not found in the registry.
        The node can carry any additional. fields (e.g. "_payload") — the caller reads them himself
        from return.
    selected_keys: mutable set of already selected keys - MUTATES (here
        keys of resolved nodes are added), to call again/recursion not
        doubled what was already selected.
    exclude: many tokens that BEAT addiction (safety-oriented) —
        dependency with intersection exclude_tokens is skipped with warning, even if
        another skill needs it.

    diagnostics: optional mutable list populated with stable dependency records.
        It does not suppress or change the existing human warning text.

    Returns [(node, requester_key), ...] in resolution order - caller himself
    decides how to put nodes in its structure (list of tuples / dict by name)."""
    queue = list(seed)
    resolved = []
    observed_diagnostics = []
    while queue:
        dep, requester = queue.pop(0)
        if dep in selected_keys:
            continue
        node = lookup(dep)
        if node is None:
            warn(f"'{requester}' requires unknown skill '{dep}' — pass")
            observed_diagnostics.append({
                "code": "SKILL_REQUIRED_UNKNOWN",
                "required_skill": dep,
                "requester": requester,
            })
            continue
        if node["exclude_tokens"] & exclude:
            warn(f"'{requester}' requires '{dep}', but he's in exclude — dependency missing")
            observed_diagnostics.append({
                "code": "SKILL_REQUIRED_EXCLUDED",
                "required_skill": dep,
                "requester": requester,
            })
            continue
        selected_keys.add(node["key"])
        resolved.append((node, requester))
        queue.extend((d, node["key"]) for d in node["requires"])
    if diagnostics is not None:
        prior = [
            {
                "code": item.get("code"),
                "required_skill": item.get("required_skill"),
                "requester": requester,
            }
            for item in diagnostics
            for requester in item.get("affected_identities", [])
        ]
        diagnostics[:] = aggregate_dependency_diagnostics(
            prior + observed_diagnostics)
    return resolved


def skill_content_hash(skill_dir):
    """SHA-256 based on the contents of ALL files in the skill catalog - drift detection sync wider,
    than one at a time SKILL.md: catches edits in snippets/ and references/ (which SKILL.md
    may not move). We ignore the same thing that is NOT vendored: upstream.json, language
    alternatives SKILL.*.md (except SKILL.md), .claude-plugin/, __pycache__/*.pyc.
    The relative path of the file is included in the hash (rename protection/movements).
    The order is stable (sorted).

    Full hexdigest, like the others sha256 in the registry/location. Complements, NOT replaces
    field sha256 (by SKILL.md) — old locks without content_sha256 degrade correctly."""
    h = hashlib.sha256()
    skill_dir = Path(skill_dir)
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file():
            continue
        name = f.name
        if name == "upstream.json":
            continue
        if name.startswith("SKILL.") and name.endswith(".md") and name != "SKILL.md":
            continue
        if ".claude-plugin" in f.parts:
            continue
        # __pycache__/*.pyc — bytecode cache when running locally.py-snippets (e.g.
        # snippets/check.py); without exception content_sha256 is unstable between machines
        # (found during drift investigation skills.json — on the developer disk was
        # __pycache__, in a clean checkout/CI it’s not there, the hashes were different).
        if "__pycache__" in f.parts or name.endswith(".pyc"):
            continue
        # evals/ — behavioral tests (eval-first), NOT vendored (see vendor.copy_skill);
        # is excluded from the hash so that editing the test is not considered a drift of the vendor skill.
        if "evals" in f.relative_to(skill_dir).parts:
            continue
        h.update(str(f.relative_to(skill_dir)).encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
    return h.hexdigest()
