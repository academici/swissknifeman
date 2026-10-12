"""Internal documentation."""
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aicore.config import ConfigError, resolve
from aicore.util.io import safe_load_json
from aicore.util.term import warn

from .hooks_env import SCHEMA_FILE


# lib/harness/settings_audit.py → <package>/configs/claude-code/settings-keys.json.


_SETTINGS_KEYS_PATH = (Path(__file__).resolve().parents[2]
                        / "configs" / "claude-code" / "settings-keys.json")



_SECRET_KEY_RE = re.compile(r"(API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"^(\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|<.*>|changeme)$", re.IGNORECASE)



LAYER_ORDER = ("user", "project", "local", "managed")

CLI_ARGS_NOTE = (
    "CLI-arguments (scope with the highest priority in Claude Code) — is not a file, "
    "doctor'are not visible and are not included in the effective configuration."
)


# (D4, RAG:✅ 2026-07-10 settings.md: «Exception: Permission rules merge across scopes


MERGE_KEYS = ("permissions.allow", "permissions.deny", "permissions.ask", "hooks", "env")




UNVERIFIED_MERGE_KEYS = ("permissions.additionalDirectories",)



_PERMISSIONS_ARRAY_KEYS = ("allow", "deny", "ask")



DEAD_ALLOW_THRESHOLD = 50


@dataclass(frozen=True)
class Layer(object):
    """Internal documentation."""

    name: str
    path: Path
    data: Optional[dict] = None
    error: Optional[str] = None
    error_kind: Optional[str] = None


@dataclass(frozen=True)
class Finding(object):
    """Internal documentation."""

    id: int
    level: str  # "error" | "warn" | "info"
    title: str
    detail: str = ""
    hint: str = ""


def managed_settings_main_path():
    """Internal documentation."""
    if sys.platform.startswith("linux"):
        return Path("/etc/claude-code/managed-settings.json")
    if sys.platform == "darwin":
        return Path("/Library/Application Support/ClaudeCode/managed-settings.json")
    if sys.platform.startswith("win"):
        return Path(r"C:\Program Files\ClaudeCode\managed-settings.json")
    return None


def _managed_paths():
    """Internal documentation."""
    main = managed_settings_main_path()
    if main is None:
        return []
    paths = [main]
    managed_d = main.with_name("managed-settings.d")
    if managed_d.is_dir():
        paths.extend(sorted(managed_d.glob("*.json")))
    return paths


def _load_layer(name, path):
    """Internal documentation."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Layer(name, path, data=None, error=None)
    except (OSError, UnicodeDecodeError) as error:
        return Layer(name, path, data=None, error=str(error), error_kind="unreadable")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return Layer(name, path, data=None, error=str(error), error_kind="malformed")
    if not isinstance(data, dict):
        return Layer(name, path, data=None, error="top level JSON not an object",
                     error_kind="malformed")
    return Layer(name, path, data=data, error=None)


def load_layers(env, target):
    """Internal documentation."""
    target = Path(target)
    layers = [
        _load_layer("user", Path(env.home) / ".claude" / "settings.json"),
        _load_layer("project", target / ".claude" / "settings.json"),
        _load_layer("local", target / ".claude" / "settings.local.json"),
    ]
    for path in _managed_paths():
        layers.append(_load_layer("managed", path))
    return layers


def _hook_entries(entries):
    """Internal documentation."""
    out = []
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        matcher = entry.get("matcher")
        for h in entry.get("hooks") or []:
            if isinstance(h, dict) and "command" in h:
                out.append((matcher, h.get("command")))
    return out


def effective_config(layers):
    """Internal documentation."""
    values = {}
    provenance = {}



    for layer in layers:
        if not layer.data:
            continue
        for key, val in layer.data.items():
            if key in ("permissions", "env", "hooks"):
                continue
            values[key] = val
            provenance[key] = layer.name


    env_present = any(isinstance(l.data, dict) and isinstance(l.data.get("env"), dict)
                       for l in layers)
    if env_present:
        env_values, env_prov = {}, {}
        for layer in layers:
            if not isinstance(layer.data, dict):
                continue
            env = layer.data.get("env")
            if not isinstance(env, dict):
                continue
            for k, v in env.items():
                env_values[k] = v
                env_prov[k] = layer.name
        values["env"] = env_values
        provenance["env"] = env_prov


    hooks_present = any(isinstance(l.data, dict) and isinstance(l.data.get("hooks"), dict)
                         for l in layers)
    if hooks_present:
        hooks_values, hooks_prov = {}, {}
        for layer in layers:
            if not isinstance(layer.data, dict):
                continue
            hooks = layer.data.get("hooks")
            if not isinstance(hooks, dict):
                continue
            for event, entries in hooks.items():
                bucket = hooks_values.setdefault(event, [])
                prov_bucket = hooks_prov.setdefault(event, [])
                seen = {(m, c) for m, c, _ in prov_bucket}
                for matcher, command in _hook_entries(entries):
                    if (matcher, command) in seen:
                        continue
                    seen.add((matcher, command))
                    bucket.append({"matcher": matcher, "command": command})
                    prov_bucket.append((matcher, command, layer.name))
        values["hooks"] = hooks_values
        provenance["hooks"] = hooks_prov


    perms_present = any(isinstance(l.data, dict) and isinstance(l.data.get("permissions"), dict)
                         for l in layers)
    if perms_present:
        perm_values, perm_prov = {}, {}



        for sub in _PERMISSIONS_ARRAY_KEYS:
            ordered, rule_layer = [], {}
            for layer in layers:
                perms = layer.data.get("permissions") if isinstance(layer.data, dict) else None
                rules = perms.get(sub) if isinstance(perms, dict) else None
                if not isinstance(rules, list):
                    continue
                for rule in rules:
                    if rule not in rule_layer:
                        ordered.append(rule)
                    rule_layer[rule] = layer.name
            if ordered:
                perm_values[sub] = ordered
                perm_prov[sub] = [(rule, rule_layer[rule]) for rule in ordered]


        by_layer = {}
        for layer in layers:
            perms = layer.data.get("permissions") if isinstance(layer.data, dict) else None
            dirs = perms.get("additionalDirectories") if isinstance(perms, dict) else None
            if isinstance(dirs, list) and dirs:
                by_layer[layer.name] = dirs
        if by_layer:
            union, seen_dirs = [], set()
            for dirs in by_layer.values():
                for d in dirs:
                    if d not in seen_dirs:
                        seen_dirs.add(d)
                        union.append(d)
            perm_values["additionalDirectories"] = {"by_layer": by_layer, "union": union}



        for layer in layers:
            perms = layer.data.get("permissions") if isinstance(layer.data, dict) else None
            if not isinstance(perms, dict):
                continue
            for sub, val in perms.items():
                if sub in _PERMISSIONS_ARRAY_KEYS or sub == "additionalDirectories":
                    continue
                perm_values[sub] = val
                perm_prov[sub] = layer.name

        values["permissions"] = perm_values
        provenance["permissions"] = perm_prov

    return values, provenance





# `~/.config/Code/User/settings.json`, darwin `~/Library/Application Support/Code/




_JSONC_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _strip_jsonc_comments(text):
    """Internal documentation."""
    out = []
    i, n = 0, len(text)
    in_string = False
    escape = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return _JSONC_TRAILING_COMMA_RE.sub(r"\1", "".join(out))


def _vscode_user_path(env):
    """Internal documentation."""
    home = Path(env.home)
    if sys.platform.startswith("linux"):
        return home / ".config" / "Code" / "User" / "settings.json"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    if sys.platform.startswith("win"):
        return home / "AppData" / "Roaming" / "Code" / "User" / "settings.json"
    return None


def _load_vscode_layer(name, path):
    """Internal documentation."""
    if not path.exists():
        return Layer(name, path, data=None, error=None)
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(_strip_jsonc_comments(text))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return Layer(name, path, data=None, error=str(e))
    if not isinstance(data, dict):
        return Layer(name, path, data=None, error="top level JSON not an object")
    return Layer(name, path, data=data, error=None)


@dataclass(frozen=True)
class VscodeState(object):
    """Internal documentation."""

    layers: tuple
    effective: dict


def load_vscode(env, target):
    """Internal documentation."""
    layers = []
    user_path = _vscode_user_path(env)
    if user_path is not None:
        layers.append(_load_vscode_layer("user", user_path))
    layers.append(_load_vscode_layer("project", Path(target) / ".vscode" / "settings.json"))
    effective = {}
    for layer in layers:
        if isinstance(layer.data, dict):
            effective.update(layer.data)
    return VscodeState(layers=tuple(layers), effective=effective)


@dataclass(frozen=True)
class ProfileState(object):
    """Internal documentation."""

    name: Optional[str] = None
    profile: Optional[dict] = None
    available: tuple = ()


@dataclass(frozen=True)
class Context(object):
    """Internal documentation."""

    layers: list
    values: dict
    provenance: dict
    target: Path
    env: object
    profile: Optional[object] = None
    vscode: Optional[object] = None


def build_context(env, target, profile_name=None):
    """Internal documentation."""
    layers = load_layers(env, target)
    values, provenance = effective_config(layers)
    profile = resolve_profile_state(env, target, profile_name)
    vscode = load_vscode(env, target)
    return Context(layers=layers, values=values, provenance=provenance,
                    target=Path(target), env=env, profile=profile, vscode=vscode)


def _load_settings_keys():
    """Internal documentation."""
    data = safe_load_json(_SETTINGS_KEYS_PATH, default=None)
    if not isinstance(data, dict):
        return {"top_level": [], "permissions": [], "hook_events": [],
                "hook_events_unverified": True, "verified": "?"}
    return data






_POLICY_DIR = (Path(__file__).resolve().parents[2]
               / "configs" / "claude-code" / "policy")


def available_profiles():
    """Internal documentation."""
    if not _POLICY_DIR.is_dir():
        return ()
    return tuple(sorted(p.stem for p in _POLICY_DIR.glob("*.json")))


_LEGACY_WARNED = set()


def read_policy_declaration(target):
    """`policy_profile` of `[harness]` in the project configuration; the legacy
    `.swissknife.json` key is read (one warning) only while the configuration does not set it."""
    try:
        name = resolve("harness", schema=SCHEMA_FILE, project=target,
                       warn=lambda _message: None).get("policy_profile")
    except ConfigError as error:
        warn(f"HARNESS_CONFIG_INVALID: {error}")
        name = None
    if isinstance(name, str) and name:
        return name
    legacy = Path(target) / ".swissknife.json"
    data = safe_load_json(legacy, default=None)
    if not isinstance(data, dict):
        return None
    name = data.get("policy_profile")
    if not (isinstance(name, str) and name):
        return None
    if str(legacy) not in _LEGACY_WARNED:
        _LEGACY_WARNED.add(str(legacy))
        warn(f"HARNESS_LEGACY_POLICY_PROFILE: {legacy} sets policy_profile; "
             "move it to policy_profile under [harness] in .swissknifeman/config.toml")
    return name


def load_profile(env, name):
    """Internal documentation."""
    if not name:
        return None
    data = safe_load_json(_POLICY_DIR / f"{name}.json", default=None)
    return data if isinstance(data, dict) else None


def resolve_profile_state(env, target, explicit_name=None):
    """Internal documentation."""
    name = explicit_name or read_policy_declaration(target)
    available = available_profiles()
    if not name:
        return ProfileState(name=None, profile=None, available=available)
    return ProfileState(name=name, profile=load_profile(env, name), available=available)




def check_1_layer_json_valid(ctx):
    """Internal documentation."""
    findings = []
    for layer in ctx.layers:
        if layer.error:
            unreadable = layer.error_kind == "unreadable"
            findings.append(Finding(
                id=1, level="error",
                title=(f"Layer «{layer.name}» ({layer.path}) not readable"
                       if unreadable else
                       f"Layer «{layer.name}» ({layer.path}) — broken JSON"),
                detail=layer.error,
                hint=("Check the path and permissions - unreadable layer "
                      "is excluded from the effective configuration."
                      if unreadable else
                      "Fix it JSON layer (or delete the file if it is redundant) — entire layer "
                      "is now excluded from the effective configuration."),
            ))
    return findings




def check_2_noncanonical_keys(ctx):
    """Internal documentation."""
    keys = _load_settings_keys()
    known_top = set(keys.get("top_level") or [])
    known_perm = set(keys.get("permissions") or [])
    findings = []
    seen = set()
    for layer in ctx.layers:
        if not isinstance(layer.data, dict):
            continue
        for key in layer.data.keys():
            if key == "$schema" or key in known_top:
                continue
            marker = ("top", key, layer.name)
            if marker in seen:
                continue
            seen.add(marker)
            findings.append(Finding(
                id=2, level="warn",
                title=f"Non-canonical key «{key}» (layer {layer.name})",
                detail="The key is not in the snapshot of canonical keys settings-keys.json — "
                       "Claude Code silently ignores him.",
                hint="Check the current key name in code.claude.com/docs/en/settings.md.",
            ))
        perms = layer.data.get("permissions")
        if not isinstance(perms, dict):
            continue
        for sub in perms.keys():
            if sub in known_perm:
                continue
            marker = ("perm", sub, layer.name)
            if marker in seen:
                continue
            seen.add(marker)
            findings.append(Finding(
                id=2, level="warn",
                title=f"Non-canonical key permissions.{sub} (layer {layer.name})",
                detail="The connection is not in the snapshot permissions.* — Claude Code silently him "
                       "ignores (standard: permissions.autoApprove, D6).",
                hint="Check the current key name in code.claude.com/docs/en/permissions.md.",
            ))
    return findings




def check_3_default_mode_conflict(ctx):
    """Internal documentation."""
    declared = []
    for layer in ctx.layers:
        perms = layer.data.get("permissions") if isinstance(layer.data, dict) else None
        if isinstance(perms, dict) and "defaultMode" in perms:
            declared.append((layer.name, perms["defaultMode"]))
    if len(declared) < 2:
        return []
    effective = (ctx.values.get("permissions") or {}).get("defaultMode")
    chain = ", ".join(f"{name}={mode!r}" for name, mode in declared)
    return [Finding(
        id=3, level="warn",
        title="permissions.defaultMode declared in multiple layers",
        detail=f"Chain in ascending order of priority: {chain}. Effective mode: {effective!r}.",
        hint="The mode is fixed at the START of the session - on-the-fly editing does not work "
             "(restart the session after the change).",
    )]




def check_4_policy_profile_conformance(ctx):
    """Internal documentation."""
    state = ctx.profile
    if state is None or state.name is None:
        avail = ", ".join(state.available) if state and state.available else "—"
        return [Finding(
            id=4, level="info",
            title="policy-project profile not declared",
            detail="policy_profile is not set under [harness] in .swissknifeman/config.toml — "
                   "effective reconciliation configuration with the expected policy is not running.",
            hint=f"Declare the expected policy as `policy_profile` under `[harness]` in "
                 f".swissknifeman/config.toml (available: {avail}).",
        )]
    if state.profile is None:
        avail = ", ".join(state.available) if state.available else "—"
        return [Finding(
            id=4, level="error",
            title=f"Unknown policy-profile «{state.name}»",
            detail=f"Profile not available: {avail}.",
            hint="Check policy_profile under [harness] in .swissknifeman/config.toml or create a profile "
                 "in configs/claude-code/policy/.",
        )]

    findings = []
    expect = state.profile.get("expect") or {}
    perms = ctx.values.get("permissions") or {}


    if "permissions.defaultMode" in expect:
        exp_mode = expect["permissions.defaultMode"]
        act_mode = perms.get("defaultMode")
        if act_mode != exp_mode:
            findings.append(Finding(
                id=4, level="error",
                title="Effective permissions.defaultMode ≠ profile",
                detail=f"Profile «{state.name}» is waiting {exp_mode!r}, effective {act_mode!r}.",
                hint="Bring permissions.defaultMode to profile (writer: harness permissions).",
            ))


    deny_expect = expect.get("permissions.deny")
    if isinstance(deny_expect, dict) and isinstance(deny_expect.get("contains"), list):
        actual_deny = set(perms.get("deny") or [])
        missing = [r for r in deny_expect["contains"] if r not in actual_deny]
        if missing:
            findings.append(Finding(
                id=4, level="error",
                title="In effective permissions.deny no required guardrail-rules",
                detail=f"Profile «{state.name}» requires (⊇), is missing: {', '.join(missing)}.",
                hint="Return deleted items deny-rules - they work guardrail'ohm in ALL "
                     "modes, including bypassPermissions.",
            ))


    hooks_expect = expect.get("hooks")
    if isinstance(hooks_expect, dict):
        eff_hooks = ctx.values.get("hooks") or {}
        for req in hooks_expect.get("required") or []:
            if not isinstance(req, dict):
                continue
            event = req.get("event")
            command = req.get("command")
            entries = eff_hooks.get(event) or []
            present = any(
                command is None or (isinstance(e, dict) and e.get("command") == command)
                for e in entries
            )
            if not present:
                findings.append(Finding(
                    id=4, level="error",
                    title=f"The hook expected by the profile is not registered: {event}",
                    detail=f"Profile «{state.name}» requires a hook {event}"
                           + (f" → {command}" if command else "") + ".",
                    hint="Write a hook (writer: harness hooks) or remove the requirement from the profile.",
                ))




    vscode_expect = expect.get("vscode")
    if isinstance(vscode_expect, dict) and ctx.vscode is not None and ctx.vscode.effective:
        actual = ctx.vscode.effective
        for key, exp_val in vscode_expect.items():
            act_val = actual.get(key)
            if act_val != exp_val:
                findings.append(Finding(
                    id=4, level="error",
                    title=f"VSCode-setting {key} ≠ profile",
                    detail=f"Profile «{state.name}» is waiting {exp_val!r}, fact {act_val!r}.",
                    hint="Bring VSCode user/project settings.json to profile.",
                ))

    return findings





_INTERPRETERS = {"bash", "sh", "zsh", "dash", "python", "python3", "node", "perl", "ruby"}
_CURSOR_HANDLER_MARKER = ".cursor/hooks/lifecycle.py"
_CURSOR_SURFACE_RE = re.compile(r"--surface\s+([A-Za-z0-9._-]+)")
_CLAUDE_COMPAT_SURFACE_HINTS = (
    ("lifecycle.command-log", "pretooluse", "bash", "log-bash-command.sh"),
    ("lifecycle.daemon-safety", "pretooluse", "bash", "daemon-safety/block-daemon-ops.sh"),
    ("lifecycle.review-gate", "subagentstop", "", "review-gate/review-gate.sh"),
    ("lifecycle.run-report", "sessionend", "", "run-report/run-report.py"),
    ("lifecycle.router", "userpromptsubmit", "", "agent-router/router.py"),
    ("lifecycle.memory", "sessionstart", "", "hooks/memory/memory.sh"),
    ("lifecycle.pack-guard", "pretooluse", "", "hooks/pack-guard/pack-guard.py"),
    ("lifecycle.changelog-gate", "pretooluse", "bash", "hooks/changelog-gate/changelog-gate.py"),
    ("lifecycle.plan-guard", "pretooluse", "", "hooks/plan-guard/plan-guard.py"),
    ("lifecycle.plan-regen", "posttooluse", "", "hooks/plan-regen/plan-regen.py"),
    # safe-dirs is embedded into auto-approve on the Claude compatibility path.
    ("security.safe-dirs", "pretooluse", "bash", "auto-approve/auto-approve.sh"),
)


def _resolve_hook_command_path(command, target, home):
    """Internal documentation."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None

    first = tokens[0]
    if "$" in first:
        return None

    requires_exec = True


    if Path(first).name in _INTERPRETERS:
        requires_exec = False
        args = [t for t in tokens[1:] if not t.startswith("-")]
        if not args:
            return None
        first = args[0]
        if "$" in first:
            return None

    if first == "~":
        path = Path(home)
    elif first.startswith("~/"):
        path = Path(home) / first[2:]
    else:
        path = Path(first)
    if not path.is_absolute():
        path = Path(target) / path
    return path, requires_exec


def check_5_hooks(ctx):
    """Internal documentation."""
    keys = _load_settings_keys()
    known_events = set(keys.get("hook_events") or [])
    snapshot_date = keys.get("verified", "?")
    findings = []
    hooks = ctx.values.get("hooks") or {}
    for event, entries in hooks.items():
        if event not in known_events:
            findings.append(Finding(
                id=5, level="info",
                title=f"Hook event «{event}» not in snapshot",
                detail=f"The event is not in the snapshot from {snapshot_date} — check the doc, "
                       "snapshot may be out of date.",
                hint="List completeness hook-events not confirmed by a second source "
                     "(findings, [UNVERIFIED]).",
            ))
        for entry in entries or []:
            command = entry.get("command") if isinstance(entry, dict) else None
            if not command:
                continue
            resolved = _resolve_hook_command_path(command, ctx.target, ctx.env.home)
            if resolved is None:
                findings.append(Finding(
                    id=5, level="info",
                    title=f"Hook {event}: command with placeholder not verified",
                    detail=command,
                    hint="Path contains $VAR-placeholder ($CLAUDE_PROJECT_DIR and "
                         "etc.) — doctor will not resolve it.",
                ))
                continue
            path, requires_exec = resolved
            if not path.exists() or (requires_exec and not os.access(path, os.X_OK)):
                findings.append(Finding(
                    id=5, level="error",
                    title=f"Hook {event}: command not available or not executable",
                    detail=f"{command} → {path}",
                    hint=("Check the path." if not requires_exec
                          else "Check the path and execution rights (chmod +x)."),
                ))
    return findings


def _iter_layer_hook_commands(layer):
    hooks = layer.data.get("hooks") if isinstance(layer.data, dict) else None
    if not isinstance(hooks, dict):
        return
    for event, entries in hooks.items():
        if not isinstance(event, str) or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            matcher = entry.get("matcher")
            matcher = matcher if isinstance(matcher, str) else ""
            for hook in entry.get("hooks") or []:
                command = hook.get("command") if isinstance(hook, dict) else None
                if isinstance(command, str) and command.strip():
                    yield event, matcher, command.strip()


def _load_cursor_hooks(target):
    path = Path(target) / ".cursor" / "hooks.json"
    if not path.exists():
        return None, None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, Finding(
            id=14, level="error",
            title="Failed to read .cursor/hooks.json",
            detail=str(path),
            hint="Fix it JSON and repeat doctor — without it single-writer reconciliation is unreliable.",
        )
    if not isinstance(value, dict):
        return None, Finding(
            id=14, level="error",
            title=".cursor/hooks.json: top level not object",
            detail=str(path),
            hint="Pending JSON object c key hooks.",
        )
    hooks = value.get("hooks")
    if not isinstance(hooks, dict):
        return None, Finding(
            id=14, level="error",
            title=".cursor/hooks.json: missing object hooks",
            detail=str(path),
            hint="Structure expected {\"version\":1,\"hooks\":{...}}.",
        )
    return hooks, None


def _iter_cursor_hook_commands(target):
    hooks, finding = _load_cursor_hooks(target)
    if finding is not None or hooks is None:
        return (), finding
    rows = []
    for event, entries in hooks.items():
        if not isinstance(event, str) or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            matcher = entry.get("matcher")
            matcher = matcher if isinstance(matcher, str) else ""
            command = entry.get("command")
            if isinstance(command, str) and command.strip():
                rows.append((event, matcher, command.strip()))
                continue
            # Tolerate legacy nested shape only for analysis/readability.
            nested = entry.get("hooks")
            if not isinstance(nested, list):
                continue
            for hook in nested:
                command = hook.get("command") if isinstance(hook, dict) else None
                if isinstance(command, str) and command.strip():
                    rows.append((event, matcher, command.strip()))
    return tuple(rows), None


def _surface_from_cursor_command(command):
    if not isinstance(command, str) or _CURSOR_HANDLER_MARKER not in command:
        return None
    match = _CURSOR_SURFACE_RE.search(command)
    return match.group(1) if match else None


def _surface_from_claude_compat(event, matcher, command):
    if not isinstance(command, str):
        return None
    event_key = event.lower()
    matcher_key = matcher.lower()
    command_key = command.lower()
    for surface_id, req_event, req_matcher, token in _CLAUDE_COMPAT_SURFACE_HINTS:
        if req_event and event_key != req_event:
            continue
        if req_matcher and matcher_key != req_matcher:
            continue
        if token in command_key:
            return surface_id
    return None


def _collect_claude_compat_refs(ctx):
    refs = {}
    for layer in ctx.layers:
        if layer.name not in {"project", "user"}:
            continue
        for event, matcher, command in _iter_layer_hook_commands(layer):
            surface_id = _surface_from_claude_compat(event, matcher, command)
            if surface_id is None:
                continue
            refs.setdefault(surface_id, []).append((layer.name, layer.path, event, matcher, command))
    return refs


def check_14_cursor_single_writer_overlap(ctx):
    """Internal documentation."""
    findings = []
    cursor_rows, parse_finding = _iter_cursor_hook_commands(ctx.target)
    if parse_finding is not None:
        findings.append(parse_finding)
        return findings
    cursor_refs = {}
    for event, matcher, command in cursor_rows:
        surface_id = _surface_from_cursor_command(command)
        if surface_id is None:
            continue
        cursor_refs.setdefault(surface_id, []).append((event, matcher, command))
    compat_refs = _collect_claude_compat_refs(ctx)
    for surface_id in sorted(set(cursor_refs) & set(compat_refs)):
        compat_summary = ", ".join(
            f"{layer}:{event}:{matcher or '*'}"
            for layer, _path, event, matcher, _command in compat_refs[surface_id]
        )
        findings.append(Finding(
            id=14, level="warn",
            title=f"Single-writer broken: surface {surface_id} registered twice",
            detail=("Cursor-native .cursor/hooks.json intersects with Claude-compat hooks: "
                    + compat_summary),
            hint=("Leave one registration source surface: remove Claude-compat entry "
                  "or make the handler idempotent (conversation_id, tool_use_id)."),
        ))
    return findings


def check_15_duplicate_hook_registrations(ctx):
    """Internal documentation."""
    findings = []
    counter = {}
    for layer in ctx.layers:
        if layer.name not in {"project", "user"}:
            continue
        for event, matcher, command in _iter_layer_hook_commands(layer):
            key = (str(layer.path), event, matcher, command)
            counter[key] = counter.get(key, 0) + 1
    cursor_rows, parse_finding = _iter_cursor_hook_commands(ctx.target)
    if parse_finding is None:
        cursor_path = ctx.target / ".cursor" / "hooks.json"
        for event, matcher, command in cursor_rows:
            key = (str(cursor_path), event, matcher, command)
            counter[key] = counter.get(key, 0) + 1
    for (path, event, matcher, command), times in sorted(counter.items()):
        if times < 2:
            continue
        findings.append(Finding(
            id=15, level="warn",
            title=(f"Repeated identical hook registration x{times}: "
                   f"{Path(path).name} {event}:{matcher or '*'}"),
            detail=command,
            hint=("Remove duplicates: Cursor executes all matching hooks from all sources, "
                  "so the identical command will work many times."),
        ))
    return findings


def check_16_cursor_compat_binding_notice(ctx):
    """Internal documentation."""
    compat_refs = _collect_claude_compat_refs(ctx)
    if not compat_refs:
        return []
    surfaces = ", ".join(sorted(compat_refs))
    return [Finding(
        id=16, level="info",
        title="Claude-compat hooks in Cursor are not managed binding",
        detail="Found compat-surfaces: " + surfaces,
        hint=("Delivery compat-path depends on user flag "
              "\"Include Third-Party Plugins, Skills, and Other Configs\"."),
    )]


def check_9_secrets(ctx):
    """Internal documentation."""
    findings = []
    env_values = ctx.values.get("env") or {}
    env_prov = ctx.provenance.get("env") or {}
    for key, val in env_values.items():
        if not isinstance(val, str):
            continue
        if not _SECRET_KEY_RE.search(key):
            continue
        if len(val) <= 8:
            continue
        if _PLACEHOLDER_RE.match(val.strip()):
            continue
        findings.append(Finding(
            id=9, level="error",
            title=f"Looks like a plaintext secret: env.{key}",
            detail=f"Layer: {env_prov.get(key, '?')}.",
            hint="Place the value in an environment variable/secret storage, not in settings.json.",
        ))

    local_layer = next((l for l in ctx.layers if l.name == "local"), None)
    if local_layer is not None and local_layer.path.exists():
        gitignore_finding = _check_local_gitignored(ctx.target, local_layer.path)
        if gitignore_finding is not None:
            findings.append(gitignore_finding)
    return findings


def _check_local_gitignored(target, local_path):
    """Internal documentation."""
    try:
        result = subprocess.run(
            ["git", "-C", str(target), "check-ignore", "-q", str(local_path)],
            check=False, timeout=10, capture_output=True,
        )
    except (subprocess.SubprocessError, OSError):
        return Finding(
            id=9, level="info",
            title="Failed to verify gitignore-status settings.local.json",
            detail="git is not available.",
            hint="Check manually: git check-ignore -q .claude/settings.local.json",
        )
    if result.returncode == 0:
        return None
    if result.returncode == 1:
        return Finding(
            id=9, level="error",
            title="settings.local.json NOT in .gitignore",
            detail=str(local_path),
            hint="Add .claude/settings.local.json in .gitignore — file can "
                 "carry secrets/local paths.",
        )
    return Finding(
        id=9, level="info",
        title="Failed to verify gitignore-status settings.local.json",
        detail=f"git check-ignore returned the code {result.returncode} (not git-repository?).",
        hint="Check manually.",
    )




def check_11_ask_rules_when_expected_empty(ctx):
    """Internal documentation."""
    state = ctx.profile
    if state is None or state.name is None or state.profile is None:
        return []
    expect = state.profile.get("expect") or {}
    if "permissions.ask" not in expect:
        return []
    if expect["permissions.ask"]:
        return []
    ask_rules = (ctx.values.get("permissions") or {}).get("ask") or []
    if not ask_rules:
        return []
    ask_prov = dict((ctx.provenance.get("permissions") or {}).get("ask") or [])
    listed = ", ".join(f"{r} ({ask_prov.get(r, '?')})" for r in ask_rules)
    return [Finding(
        id=11, level="error",
        title="ask-rules force prompt under policy «don't ask»",
        detail=f"Profile «{state.name}» requires empty permissions.ask, effectively: {listed}.",
        hint="Remove ask-rules - they force the prompt IN ANY mode, including "
             "bypassPermissions (deny/ask always apply).",
    )]




def _is_exact_bash_rule(rule):
    """Internal documentation."""
    return (isinstance(rule, str) and rule.startswith("Bash(") and rule.endswith(")")
            and "*" not in rule)


def check_6_dead_allow_rules(ctx):
    """Internal documentation."""
    allow = (ctx.values.get("permissions") or {}).get("allow") or []
    exact = [r for r in allow if _is_exact_bash_rule(r)]
    if len(exact) < DEAD_ALLOW_THRESHOLD:
        return []
    return [Finding(
        id=6, level="info",
        title=f"Garbage precision allow-rules Bash(...): {len(exact)} pcs.",
        detail=f"Threshold {DEAD_ALLOW_THRESHOLD}. Top 5 examples: {', '.join(exact[:5])}.",
        hint="Replace the exact one-time rules with wildcard-pattern or run cleaning "
             "(doctor read-only — no auto-cleaning).",
    )]




def check_7_allow_deny_overlap(ctx):
    """Internal documentation."""
    perms = ctx.values.get("permissions") or {}
    allow = {r for r in (perms.get("allow") or []) if isinstance(r, str)}
    deny = {r for r in (perms.get("deny") or []) if isinstance(r, str)}
    return [
        Finding(
            id=7, level="warn",
            title=f"Rule and in allow, and in deny: {rule}",
            detail="Deny wins silently (deny-first) — allow-entry is now dead.",
            hint="Remove a rule from one of the lists - keeping it in both is pointless.",
        )
        for rule in sorted(allow & deny)
    ]




def check_8_additional_directories_missing(ctx):
    """Internal documentation."""
    findings = []
    ad = (ctx.values.get("permissions") or {}).get("additionalDirectories")
    if not isinstance(ad, dict):
        return findings
    for layer_name, dirs in (ad.get("by_layer") or {}).items():
        for d in dirs:
            if not isinstance(d, str):
                continue
            path = Path(d)
            if not path.is_absolute():
                path = ctx.target / path
            if not path.exists():
                findings.append(Finding(
                    id=8, level="warn",
                    title=f"additionalDirectories: path does not exist (layer {layer_name})",
                    detail=f"{d} → {path}",
                    hint="Check the path or remove the entry from additionalDirectories.",
                ))
    return findings




def check_10_bypass_without_skip_dialog(ctx):
    """Internal documentation."""
    perms = ctx.values.get("permissions") or {}
    if perms.get("defaultMode") != "bypassPermissions":
        return []
    if perms.get("skipDangerousModePermissionPrompt"):
        return []
    return [Finding(
        id=10, level="info",
        title="bypassPermissions without skipDangerousModePermissionPrompt",
        detail="Login confirmation bypassPermissions is not disabled. It could be "
               "conscious choice of the operator.",
        hint="Informational: specify if necessary permissions.skipDangerousModePermissionPrompt=true "
             "in user/local settings, not in project settings.",
    )]




def _vscode_parse_errors(ctx):
    """Internal documentation."""
    vscode = ctx.vscode
    if vscode is None:
        return []
    return [
        Finding(
            id=12, level="info",
            title=f"VSCode-layer «{layer.name}» ({layer.path}) did not parse",
            detail=layer.error,
            hint="JSONC-reader is tolerant of comments/with a trailing comma, but not "
                 "to everything - fix the file manually.",
        )
        for layer in vscode.layers
        if layer.error
    ]


def check_12_vscode_initial_mode_mismatch(ctx):
    """Internal documentation."""
    parse_errors = _vscode_parse_errors(ctx)
    if parse_errors:
        return parse_errors
    vscode = ctx.vscode
    if vscode is None:
        return []
    initial = vscode.effective.get("claudeCode.initialPermissionMode")
    if initial is None:
        return []
    effective_mode = (ctx.values.get("permissions") or {}).get("defaultMode")
    if initial == effective_mode:
        return []
    return [Finding(
        id=12, level="warn",
        title="VSCode claudeCode.initialPermissionMode diverges from effective defaultMode",
        detail=f"VSCode: {initial!r}, effective (layers Claude Code): {effective_mode!r}.",
        hint="The extension starts the session from YOUR settings - make it consistent "
             "or accept the discrepancy consciously.",
    )]


def check_13_vscode_bypass_toggle_missing(ctx):
    """Internal documentation."""
    perms = ctx.values.get("permissions") or {}
    if perms.get("defaultMode") != "bypassPermissions":
        return []
    parse_errors = _vscode_parse_errors(ctx)
    if parse_errors:
        return parse_errors
    vscode = ctx.vscode
    if vscode is None or not vscode.effective:
        return []
    if vscode.effective.get("claudeCode.allowDangerouslySkipPermissions") is True:
        return []
    return [Finding(
        id=13, level="warn",
        title="VSCode claudeCode.allowDangerouslySkipPermissions not enabled",
        detail="Effective permissions.defaultMode=bypassPermissions, but toggle "
               "extension is not set in true.",
        hint="Turn on claudeCode.allowDangerouslySkipPermissions:true in VSCode "
             "settings.json — otherwise the mode is not available in the selector.",
    )]






CHECKS = (
    (1, check_1_layer_json_valid),
    (2, check_2_noncanonical_keys),
    (3, check_3_default_mode_conflict),
    (4, check_4_policy_profile_conformance),
    (5, check_5_hooks),
    (6, check_6_dead_allow_rules),
    (7, check_7_allow_deny_overlap),
    (8, check_8_additional_directories_missing),
    (9, check_9_secrets),
    (10, check_10_bypass_without_skip_dialog),
    (11, check_11_ask_rules_when_expected_empty),
    (12, check_12_vscode_initial_mode_mismatch),
    (13, check_13_vscode_bypass_toggle_missing),
)


def run_checks(ctx, checks=CHECKS):
    """Internal documentation."""
    findings = []
    for _id, fn in checks:
        findings.extend(fn(ctx))
    return findings


CURSOR_CHECKS = CHECKS + (
    (14, check_14_cursor_single_writer_overlap),
    (15, check_15_duplicate_hook_registrations),
    (16, check_16_cursor_compat_binding_notice),
)


def run_cursor_checks(ctx, checks=CURSOR_CHECKS):
    """Internal documentation."""
    findings = []
    for _id, fn in checks:
        findings.extend(fn(ctx))
    return findings


# --- Codex settings audit (P2.4, codex-parity-verdicts-v1.md §3.11, bounded closure) ---











# host-owned app request metadata, notification, configuration profile selection,


CODEX_NON_OVERRIDABLE_PROJECT_KEYS = ("model_provider", "auth", "notify", "profile", "otel")


def _load_codex_toml_layer(name, path):
    """Internal documentation."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Layer(name, path, data=None, error=None)
    except (OSError, UnicodeDecodeError) as error:
        return Layer(name, path, data=None, error=str(error), error_kind="unreadable")
    try:
        import tomllib
    except ModuleNotFoundError:
        return Layer(name, path, data=None,
                     error="interpreter < 3.11: tomllib is not available, the layer is not readable",
                     error_kind="unreadable")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return Layer(name, path, data=None, error=str(error), error_kind="malformed")
    if not isinstance(data, dict):
        return Layer(name, path, data=None, error="top level TOML not a table",
                     error_kind="malformed")
    return Layer(name, path, data=data, error=None)


def load_codex_layers(env, target, *, state_dir=".codex"):
    """Load user+project TOML layers for Codex or Grok (same schema, different dir)."""
    target = Path(target)
    return [
        _load_codex_toml_layer("user", Path(env.home) / state_dir / "config.toml"),
        _load_codex_toml_layer("project", target / state_dir / "config.toml"),
    ]


def codex_check_1_layers_readable(layers):
    """Internal documentation."""
    return [Finding(1, "warn", f"layer '{layer.name}' "
                    + ("not readable" if layer.error_kind == "unreadable"
                       else "not parsed"),
                    detail=f"{layer.path}: {layer.error}",
                    hint="layer is reported as unreadable, not conformal")
            for layer in layers if layer.error]


def codex_check_2_project_overrides_machine_local_key(layers):
    """Internal documentation."""
    project = next((layer for layer in layers if layer.name == "project" and layer.data), None)
    if project is None:
        return []
    conflicts = sorted(key for key in CODEX_NON_OVERRIDABLE_PROJECT_KEYS if key in project.data)
    if not conflicts:
        return []
    return [Finding(2, "error", "project layer overrides machine-local key",
                    detail=f"{', '.join(conflicts)} in {project.path}",
                    hint="F10: project-scoped config cannot override provider/auth/"
                         "notification/profile-selection/telemetry — transfer the key(and) in "
                         "~/.codex/config.toml")]


def codex_check_3_hooks_feature_disabled(layers):
    """Internal documentation."""
    effective = {}
    for layer in layers:
        if layer.data:
            effective.update(layer.data)
    features = effective.get("features")
    if isinstance(features, dict) and features.get("hooks") is False:
        return [Finding(3, "info", "features.hooks disabled",
                        detail="effective configuration carries features.hooks=false",
                        hint="rolled out harness hooks --provider codex surfaces "
                             "are not activated until the flag is enabled")]
    return []


CODEX_CHECKS = (
    (1, codex_check_1_layers_readable),
    (2, codex_check_2_project_overrides_machine_local_key),
    (3, codex_check_3_hooks_feature_disabled),
)


def run_codex_checks(layers, checks=CODEX_CHECKS):
    """Internal documentation."""
    findings = []
    for _id, fn in checks:
        findings.extend(fn(layers))
    return findings


def render_codex_text(target, findings):
    """Internal documentation."""
    lines = [f"harness doctor --settings --provider codex (target: {target})"]
    if not findings:
        lines.append("  no findings - the effective configuration is clean.")
    for level in _LEVEL_ORDER:
        for f in (x for x in findings if x.level == level):
            lines.append(f"[{level}] #{f.id} {f.title}")
            if f.detail:
                lines.append(f"    — {f.detail}")
            if f.hint:
                lines.append(f"    → {f.hint}")
    c = counts(findings)
    lines.append(f"errors: {c['error']}, warnings: {c['warn']}, notes: {c['info']}")
    return "\n".join(lines)


def render_provider_text(provider_id, ctx, findings):
    """Render the provider-qualified Claude Code settings report."""
    if provider_id == "codex":
        return render_codex_text(ctx.target, findings)
    name = _profile_name(ctx)
    lines = [
        f"harness doctor --settings --provider {provider_id} (target: {ctx.target})",
        f"policy-profile: {name if name else 'not declared'}",
    ]
    if not findings:
        lines.append("  no findings - the effective configuration is clean.")
    for level in _LEVEL_ORDER:
        for finding in (item for item in findings if item.level == level):
            lines.append(f"[{level}] #{finding.id} {finding.title}")
            if finding.detail:
                lines.append(f"    — {finding.detail}")
            if finding.hint:
                lines.append(f"    → {finding.hint}")
    summary = counts(findings)
    lines.append(f"errors: {summary['error']}, warnings: {summary['warn']}, "
                 f"notes: {summary['info']}")
    return "\n".join(lines)








_LEVEL_ORDER = ("error", "warn", "info")


def counts(findings):
    """Internal documentation."""
    c = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        if f.level in c:
            c[f.level] += 1
    return c


def exit_code(findings):
    """Internal documentation."""
    c = counts(findings)
    if c["error"]:
        return 2
    if c["warn"]:
        return 1
    return 0


def settings_status(findings):
    """Return the stable public status matching the settings-audit exit code."""
    code = exit_code(findings)
    return {0: "clean", 1: "warning", 2: "error"}[code]


def _profile_name(ctx):
    """Internal documentation."""
    prof = getattr(ctx, "profile", None)
    return prof.name if prof is not None else None


def render_text(ctx, findings):
    """Internal documentation."""
    name = _profile_name(ctx)
    lines = [
        f"harness doctor --settings (target: {ctx.target})",
        f"policy-profile: {name if name else 'not declared'}",
    ]
    if not findings:
        lines.append("  no findings - the effective configuration is clean.")
    for level in _LEVEL_ORDER:
        for f in (x for x in findings if x.level == level):
            lines.append(f"[{level}] #{f.id} {f.title}")
            if f.detail:
                lines.append(f"    — {f.detail}")
            if f.hint:
                lines.append(f"    → {f.hint}")
    c = counts(findings)
    lines.append(
        f"errors: {c['error']}, warnings: {c['warn']}, notes: {c['info']}")
    return "\n".join(lines)


def render_json_obj(ctx, findings):
    """Internal documentation."""
    return {
        "target": str(ctx.target),
        "profile": _profile_name(ctx),
        "counts": counts(findings),
        "findings": [
            {"id": f.id, "level": f.level, "title": f.title,
             "detail": f.detail, "hint": f.hint}
            for f in findings
        ],
        "exit": exit_code(findings),
    }


def render_provider_json_obj(provider_id, ctx, findings):
    """Render the stable public provider-qualified settings envelope."""
    return {
        "provider": provider_id,
        "target": str(ctx.target),
        "profile": _profile_name(ctx),
        "status": settings_status(findings),
        "counts": counts(findings),
        "findings": [
            {"id": finding.id, "level": finding.level, "title": finding.title,
             "detail": finding.detail, "hint": finding.hint}
            for finding in findings
        ],
        "exit": exit_code(findings),
    }
