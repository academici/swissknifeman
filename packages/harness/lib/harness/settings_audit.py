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

from core import safe_load_json


# lib/harness/settings_audit.py → <package>/configs/claude-code/settings-keys.json.


_SETTINGS_KEYS_PATH = (Path(__file__).resolve().parents[2]
                        / "configs" / "claude-code" / "settings-keys.json")



_SECRET_KEY_RE = re.compile(r"(API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"^(\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|<.*>|changeme)$", re.IGNORECASE)



LAYER_ORDER = ("user", "project", "local", "managed")

CLI_ARGS_NOTE = (
    "CLI-аргументы (scope с наивысшим приоритетом в Claude Code) — не файл, "
    "doctor'у не видны и в эффективную конфигурацию не входят."
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
        return Layer(name, path, data=None, error="верхний уровень JSON не объект",
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
        return Layer(name, path, data=None, error="верхний уровень JSON не объект")
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


def read_policy_declaration(target):
    """Internal documentation."""
    data = safe_load_json(Path(target) / ".swissknife.json", default=None)
    if not isinstance(data, dict):
        return None
    name = data.get("policy_profile")
    return name if isinstance(name, str) and name else None


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
                title=(f"Слой «{layer.name}» ({layer.path}) не читается"
                       if unreadable else
                       f"Слой «{layer.name}» ({layer.path}) — битый JSON"),
                detail=layer.error,
                hint=("Проверь путь и права доступа — нечитаемый слой "
                      "исключён из эффективной конфигурации."
                      if unreadable else
                      "Почини JSON слоя (или удали файл, если он лишний) — весь слой "
                      "сейчас исключён из эффективной конфигурации."),
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
                title=f"Неканонический ключ «{key}» (слой {layer.name})",
                detail="Ключа нет в снапшоте канонических ключей settings-keys.json — "
                       "Claude Code молча его игнорирует.",
                hint="Сверь актуальное имя ключа в code.claude.com/docs/en/settings.md.",
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
                title=f"Неканонический ключ permissions.{sub} (слой {layer.name})",
                detail="Подключа нет в снапшоте permissions.* — Claude Code молча его "
                       "игнорирует (эталон: permissions.autoApprove, D6).",
                hint="Сверь актуальное имя ключа в code.claude.com/docs/en/permissions.md.",
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
        title="permissions.defaultMode объявлен в нескольких слоях",
        detail=f"Цепочка по возрастанию приоритета: {chain}. Эффективный режим: {effective!r}.",
        hint="Режим фиксируется на СТАРТЕ сессии — правка на лету не действует "
             "(перезапусти сессию после смены).",
    )]




def check_4_policy_profile_conformance(ctx):
    """Internal documentation."""
    state = ctx.profile
    if state is None or state.name is None:
        avail = ", ".join(state.available) if state and state.available else "—"
        return [Finding(
            id=4, level="info",
            title="policy-профиль проекта не объявлен",
            detail="В .swissknife.json нет ключа policy_profile — сверка эффективной "
                   "конфигурации с ожидаемой политикой не выполняется.",
            hint=f"Объяви ожидаемую политику ключом policy_profile в .swissknife.json "
                 f"(доступны: {avail}).",
        )]
    if state.profile is None:
        avail = ", ".join(state.available) if state.available else "—"
        return [Finding(
            id=4, level="error",
            title=f"Неизвестный policy-профиль «{state.name}»",
            detail=f"Профиля нет среди доступных: {avail}.",
            hint="Проверь имя в .swissknife.json:policy_profile или заведи профиль "
                 "в configs/claude-code/policy/.",
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
                title="Эффективный permissions.defaultMode ≠ профилю",
                detail=f"Профиль «{state.name}» ждёт {exp_mode!r}, эффективно {act_mode!r}.",
                hint="Приведи permissions.defaultMode к профилю (writer: harness permissions).",
            ))


    deny_expect = expect.get("permissions.deny")
    if isinstance(deny_expect, dict) and isinstance(deny_expect.get("contains"), list):
        actual_deny = set(perms.get("deny") or [])
        missing = [r for r in deny_expect["contains"] if r not in actual_deny]
        if missing:
            findings.append(Finding(
                id=4, level="error",
                title="В эффективном permissions.deny нет обязательных guardrail-правил",
                detail=f"Профиль «{state.name}» требует (⊇), не хватает: {', '.join(missing)}.",
                hint="Верни удалённые deny-правила — они работают guardrail'ом во ВСЕХ "
                     "режимах, включая bypassPermissions.",
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
                    title=f"Ожидаемый профилем хук не прописан: {event}",
                    detail=f"Профиль «{state.name}» требует хук {event}"
                           + (f" → {command}" if command else "") + ".",
                    hint="Пропиши хук (writer: harness hooks) или сними требование из профиля.",
                ))




    vscode_expect = expect.get("vscode")
    if isinstance(vscode_expect, dict) and ctx.vscode is not None and ctx.vscode.effective:
        actual = ctx.vscode.effective
        for key, exp_val in vscode_expect.items():
            act_val = actual.get(key)
            if act_val != exp_val:
                findings.append(Finding(
                    id=4, level="error",
                    title=f"VSCode-настройка {key} ≠ профилю",
                    detail=f"Профиль «{state.name}» ждёт {exp_val!r}, факт {act_val!r}.",
                    hint="Приведи VSCode user/project settings.json к профилю.",
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
    ("lifecycle.terminal-admission", "stop", "", "terminal-admission/terminal-admission.py"),
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
                title=f"Хук-событие «{event}» не в снапшоте",
                detail=f"События нет в снапшоте от {snapshot_date} — сверь доку, "
                       "снапшот мог устареть.",
                hint="Полнота списка hook-событий не подтверждена вторым источником "
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
                    title=f"Хук {event}: команда с плейсхолдером не проверена",
                    detail=command,
                    hint="Путь содержит $VAR-плейсхолдер ($CLAUDE_PROJECT_DIR и "
                         "т.п.) — doctor его не резолвит.",
                ))
                continue
            path, requires_exec = resolved
            if not path.exists() or (requires_exec and not os.access(path, os.X_OK)):
                findings.append(Finding(
                    id=5, level="error",
                    title=f"Хук {event}: команда недоступна или неисполняема",
                    detail=f"{command} → {path}",
                    hint=("Проверь путь." if not requires_exec
                          else "Проверь путь и права на исполнение (chmod +x)."),
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
            title="Не удалось прочитать .cursor/hooks.json",
            detail=str(path),
            hint="Почини JSON и повтори doctor — без этого single-writer сверка недостоверна.",
        )
    if not isinstance(value, dict):
        return None, Finding(
            id=14, level="error",
            title=".cursor/hooks.json: верхний уровень не объект",
            detail=str(path),
            hint="Ожидается JSON object c ключом hooks.",
        )
    hooks = value.get("hooks")
    if not isinstance(hooks, dict):
        return None, Finding(
            id=14, level="error",
            title=".cursor/hooks.json: отсутствует объект hooks",
            detail=str(path),
            hint="Ожидается структура {\"version\":1,\"hooks\":{...}}.",
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
            title=f"Single-writer нарушен: surface {surface_id} зарегистрирован дважды",
            detail=("Cursor-native .cursor/hooks.json пересекается с Claude-compat hooks: "
                    + compat_summary),
            hint=("Оставь один источник регистрации surface: сними Claude-compat запись "
                  "или сделай обработчик идемпотентным по (conversation_id, tool_use_id)."),
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
            title=(f"Повторная идентичная регистрация хука x{times}: "
                   f"{Path(path).name} {event}:{matcher or '*'}"),
            detail=command,
            hint=("Убери дубликаты: Cursor выполняет все совпавшие hooks из всех источников, "
                  "поэтому идентичная команда сработает многократно."),
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
        title="Claude-compat hooks в Cursor не являются управляемым binding",
        detail="Найдены compat-surfaces: " + surfaces,
        hint=("Доставка compat-пути зависит от пользовательского флага "
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
            title=f"Похоже на секрет плейнтекстом: env.{key}",
            detail=f"Слой: {env_prov.get(key, '?')}.",
            hint="Вынеси значение в переменную окружения/секрет-хранилище, не в settings.json.",
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
            title="Не удалось проверить gitignore-статус settings.local.json",
            detail="git недоступен.",
            hint="Проверь вручную: git check-ignore -q .claude/settings.local.json",
        )
    if result.returncode == 0:
        return None
    if result.returncode == 1:
        return Finding(
            id=9, level="error",
            title="settings.local.json НЕ в .gitignore",
            detail=str(local_path),
            hint="Добавь .claude/settings.local.json в .gitignore — файл может "
                 "нести секреты/локальные пути.",
        )
    return Finding(
        id=9, level="info",
        title="Не удалось проверить gitignore-статус settings.local.json",
        detail=f"git check-ignore вернул код {result.returncode} (не git-репозиторий?).",
        hint="Проверь вручную.",
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
        title="ask-правила форсируют промпт при политике «не спрашивать»",
        detail=f"Профиль «{state.name}» требует пустой permissions.ask, эффективно: {listed}.",
        hint="Убери ask-правила — они форсируют промпт В ЛЮБОМ режиме, включая "
             "bypassPermissions (deny/ask применяются всегда).",
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
        title=f"Мусорные точные allow-правила Bash(...): {len(exact)} шт.",
        detail=f"Порог {DEAD_ALLOW_THRESHOLD}. Топ-5 примеров: {', '.join(exact[:5])}.",
        hint="Замени точные разовые правила на wildcard-паттерн или прогони чистку "
             "(doctor read-only — авто-чистки нет).",
    )]




def check_7_allow_deny_overlap(ctx):
    """Internal documentation."""
    perms = ctx.values.get("permissions") or {}
    allow = {r for r in (perms.get("allow") or []) if isinstance(r, str)}
    deny = {r for r in (perms.get("deny") or []) if isinstance(r, str)}
    return [
        Finding(
            id=7, level="warn",
            title=f"Правило и в allow, и в deny: {rule}",
            detail="Deny побеждает молча (deny-first) — allow-запись сейчас мертва.",
            hint="Убери правило из одного из списков — держать в обоих бессмысленно.",
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
                    title=f"additionalDirectories: путь не существует (слой {layer_name})",
                    detail=f"{d} → {path}",
                    hint="Проверь путь или убери запись из additionalDirectories.",
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
        title="bypassPermissions без skipDangerousModePermissionPrompt",
        detail="Подтверждение входа в bypassPermissions не отключено. Это может быть "
               "осознанным выбором оператора.",
        hint="Информационно: при необходимости задай permissions.skipDangerousModePermissionPrompt=true "
             "в user/local settings, не в project settings.",
    )]




def _vscode_parse_errors(ctx):
    """Internal documentation."""
    vscode = ctx.vscode
    if vscode is None:
        return []
    return [
        Finding(
            id=12, level="info",
            title=f"VSCode-слой «{layer.name}» ({layer.path}) не распарсился",
            detail=layer.error,
            hint="JSONC-reader толерантен к комментариям/висячим запятым, но не "
                 "ко всему — почини файл вручную.",
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
        title="VSCode claudeCode.initialPermissionMode расходится с эффективным defaultMode",
        detail=f"VSCode: {initial!r}, эффективно (слои Claude Code): {effective_mode!r}.",
        hint="Расширение стартует сессию из СВОЕЙ настройки — приведи в соответствие "
             "или прими расхождение осознанно.",
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
        title="VSCode claudeCode.allowDangerouslySkipPermissions не включён",
        detail="Эффективный permissions.defaultMode=bypassPermissions, но toggle "
               "расширения не выставлен в true.",
        hint="Включи claudeCode.allowDangerouslySkipPermissions:true в VSCode "
             "settings.json — иначе режим недоступен в селекторе.",
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
                     error="интерпретатор < 3.11: tomllib недоступен, слой не читается",
                     error_kind="unreadable")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return Layer(name, path, data=None, error=str(error), error_kind="malformed")
    if not isinstance(data, dict):
        return Layer(name, path, data=None, error="верхний уровень TOML не таблица",
                     error_kind="malformed")
    return Layer(name, path, data=data, error=None)


def load_codex_layers(env, target):
    """Internal documentation."""
    target = Path(target)
    return [
        _load_codex_toml_layer("user", Path(env.home) / ".codex" / "config.toml"),
        _load_codex_toml_layer("project", target / ".codex" / "config.toml"),
    ]


def codex_check_1_layers_readable(layers):
    """Internal documentation."""
    return [Finding(1, "warn", f"слой '{layer.name}' "
                    + ("не читается" if layer.error_kind == "unreadable"
                       else "не распарсен"),
                    detail=f"{layer.path}: {layer.error}",
                    hint="слой репортится нечитаемым, а не конформным")
            for layer in layers if layer.error]


def codex_check_2_project_overrides_machine_local_key(layers):
    """Internal documentation."""
    project = next((layer for layer in layers if layer.name == "project" and layer.data), None)
    if project is None:
        return []
    conflicts = sorted(key for key in CODEX_NON_OVERRIDABLE_PROJECT_KEYS if key in project.data)
    if not conflicts:
        return []
    return [Finding(2, "error", "проектный слой переопределяет machine-local ключ",
                    detail=f"{', '.join(conflicts)} в {project.path}",
                    hint="Ф10: project-scoped config не может переопределять provider/auth/"
                         "notification/profile-selection/telemetry — перенеси ключ(и) в "
                         "~/.codex/config.toml")]


def codex_check_3_hooks_feature_disabled(layers):
    """Internal documentation."""
    effective = {}
    for layer in layers:
        if layer.data:
            effective.update(layer.data)
    features = effective.get("features")
    if isinstance(features, dict) and features.get("hooks") is False:
        return [Finding(3, "info", "features.hooks выключен",
                        detail="эффективная конфигурация несёт features.hooks=false",
                        hint="раскатанные harness hooks --provider codex поверхности "
                             "не активируются, пока флаг не включён")]
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
        lines.append("  находок нет — эффективная конфигурация чистая.")
    for level in _LEVEL_ORDER:
        for f in (x for x in findings if x.level == level):
            lines.append(f"[{level}] #{f.id} {f.title}")
            if f.detail:
                lines.append(f"    — {f.detail}")
            if f.hint:
                lines.append(f"    → {f.hint}")
    c = counts(findings)
    lines.append(f"ошибок: {c['error']}, предупреждений: {c['warn']}, заметок: {c['info']}")
    return "\n".join(lines)


def render_provider_text(provider_id, ctx, findings):
    """Render the provider-qualified Claude Code settings report."""
    if provider_id == "codex":
        return render_codex_text(ctx.target, findings)
    name = _profile_name(ctx)
    lines = [
        f"harness doctor --settings --provider {provider_id} (target: {ctx.target})",
        f"policy-профиль: {name if name else 'не объявлен'}",
    ]
    if not findings:
        lines.append("  находок нет — эффективная конфигурация чистая.")
    for level in _LEVEL_ORDER:
        for finding in (item for item in findings if item.level == level):
            lines.append(f"[{level}] #{finding.id} {finding.title}")
            if finding.detail:
                lines.append(f"    — {finding.detail}")
            if finding.hint:
                lines.append(f"    → {finding.hint}")
    summary = counts(findings)
    lines.append(f"ошибок: {summary['error']}, предупреждений: {summary['warn']}, "
                 f"заметок: {summary['info']}")
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
        f"policy-профиль: {name if name else 'не объявлен'}",
    ]
    if not findings:
        lines.append("  находок нет — эффективная конфигурация чистая.")
    for level in _LEVEL_ORDER:
        for f in (x for x in findings if x.level == level):
            lines.append(f"[{level}] #{f.id} {f.title}")
            if f.detail:
                lines.append(f"    — {f.detail}")
            if f.hint:
                lines.append(f"    → {f.hint}")
    c = counts(findings)
    lines.append(
        f"ошибок: {c['error']}, предупреждений: {c['warn']}, заметок: {c['info']}")
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
