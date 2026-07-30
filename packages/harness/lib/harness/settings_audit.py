"""Ядро settings-doctor: слои настроек Claude Code, эффективная конфигурация, Finding.

Читает ЧЕТЫРЕ слоя настроек Claude Code (user → project → local → managed, по
возрастанию приоритета) и строит из них ЭФФЕКТИВНУЮ конфигурацию с провенансом
(из какого слоя пришло каждое итоговое значение). Каркас находки (`Finding`) — тоже
здесь; сами проверки таксономии заводятся поверх этого модуля в 2026.07.10-SKM-ROADMAP-005 P1.2/P1.3/P1.5, CLI —
в P1.4. reader-семантика **fail-soft**: битый слой — это ОТЧЁТ (проверка №1, P1.2), а
не смерть doctor'а — намеренный дубль чтения `.claude/settings*.json` рядом с
`harness.settings.load_settings` (тот `die()`-ает на битом JSON — writer-семантика,
её нельзя чинить, не сломав `permissions`/`hooks`).

Несущие внешние факты (precedence слоёв, merge-режимы, managed-пути) сверены RAG —
см. находки плана 2026.07.10-SKM-ROADMAP-005 (`findings/P1-cc-settings-facts.md`, дата сверки
зафиксирована там; при регрессии — пере-сверить, доки Claude Code меняются между версиями CLI).
stdlib-only."""
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

# Снапшот канонических ключей рядом с пресетами (не апстрим-схема — выжимка, D13):
# lib/harness/settings_audit.py → <package>/configs/claude-code/settings-keys.json.
# Тот же паттерн, что `router._HOOK_CONFIG` — путь module-relative, НЕ env-relative
# (снапшот один на пакет, а не per-target).
_SETTINGS_KEYS_PATH = (Path(__file__).resolve().parents[2]
                        / "configs" / "claude-code" / "settings-keys.json")

# Эвристика проверки №9 (секреты в env.*): имя ключа матчит один из паттернов
# И значение длиннее 8 символов И не похоже на плейсхолдер.
_SECRET_KEY_RE = re.compile(r"(API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"^(\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|<.*>|changeme)$", re.IGNORECASE)

# Порядок слоёв по ВОЗРАСТАНИЮ приоритета (RAG:✅ 2026-07-10 settings.md, 5-tier scope
# system). Пятый scope — CLI-аргументы — файлом не представлен, doctor'у не виден.
LAYER_ORDER = ("user", "project", "local", "managed")

CLI_ARGS_NOTE = (
    "CLI-аргументы (scope с наивысшим приоритетом в Claude Code) — не файл, "
    "doctor'у не видны и в эффективную конфигурацию не входят."
)

# Ключи, которые СЛИВАЮТСЯ across слоёв, а не переопределяются целиком высшим слоем
# (D4, RAG:✅ 2026-07-10 settings.md: «Exception: Permission rules merge across scopes
# rather than override» + hooks.md merge-по-событию). `env` — тоже не «override целиком»,
# а пер-ключевой override (см. `effective_config`).
MERGE_KEYS = ("permissions.allow", "permissions.deny", "permissions.ask", "hooks", "env")

# Семантика слияния НЕ ПОДТВЕРЖДЕНА (D15, findings §«Не подтверждено»): ядро хранит обе
# проекции (per-layer + union) и НЕ выбирает режим — решение остаётся на совести проверки,
# которая когда-нибудь эту величину использует (2026.07.10-SKM-ROADMAP-005 P1.5 №8 работает per-layer, не от union).
UNVERIFIED_MERGE_KEYS = ("permissions.additionalDirectories",)

# Подключи permissions.*, которые сливаются как union-массивы (не путать с
# additionalDirectories выше и с прочими скалярными подключами вроде defaultMode).
_PERMISSIONS_ARRAY_KEYS = ("allow", "deny", "ask")

# Порог проверки №6 (мусорные точные allow-правила) — константа модуля, НЕ флаг
# CLI (Implementation Rules 2026.07.10-SKM-ROADMAP-005 P1.5: вынос во флаг = scope creep).
DEAD_ALLOW_THRESHOLD = 50


@dataclass(frozen=True)
class Layer(object):
    """Один слой настроек: имя, путь файла, распарсенные данные (None — отсутствует
    ИЛИ битый), текст ошибки парсинга (None — файла нет или он валиден)."""

    name: str
    path: Path
    data: Optional[dict] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class Finding(object):
    """Находка проверки таксономии (2026.07.10-SKM-ROADMAP-005 P1.2+). Ядро P1.1 только объявляет форму."""

    id: int
    level: str  # "error" | "warn" | "info"
    title: str
    detail: str = ""
    hint: str = ""


def managed_settings_main_path():
    """Путь к главному managed-файлу для текущей ОС (RAG:✅ 2026-07-10
    server-managed-settings.md). Неизвестная ОС → None (managed-слой не читается)."""
    if sys.platform.startswith("linux"):
        return Path("/etc/claude-code/managed-settings.json")
    if sys.platform == "darwin":
        return Path("/Library/Application Support/ClaudeCode/managed-settings.json")
    if sys.platform.startswith("win"):
        return Path(r"C:\Program Files\ClaudeCode\managed-settings.json")
    return None


def _managed_paths():
    """Главный managed-файл + отсортированные `managed-settings.d/*.json`, если каталог
    существует. Отсутствие ВСЕГО managed-слоя — норма, не находка."""
    main = managed_settings_main_path()
    if main is None:
        return []
    paths = [main]
    managed_d = main.with_name("managed-settings.d")
    if managed_d.is_dir():
        paths.extend(sorted(managed_d.glob("*.json")))
    return paths


def _load_layer(name, path):
    """Один файл слоя → `Layer`, fail-soft: несуществующий файл — норма (data=None,
    error=None); битый/нечитаемый JSON — ОТЧЁТ (data=None, error=текст), но не die()."""
    if not path.exists():
        return Layer(name, path, data=None, error=None)
    errors = []
    data = safe_load_json(path, default=None, on_error=lambda e: errors.append(str(e)))
    if data is not None and not isinstance(data, dict):
        errors.append("верхний уровень JSON не объект")
        data = None
    return Layer(name, path, data=data, error=(errors[0] if errors else None))


def load_layers(env, target):
    """Читает все слои настроек Claude Code для проекта `target`.

    `home` берётся из `env.home` (никаких `Path.home()`/`os.environ["HOME"]` — иначе
    тесты в tmpdir потекут в реальный `~/.claude`), `target` — явный параметр. Возвращает
    список `Layer` в порядке `LAYER_ORDER` (managed может дать 0..N записей — главный
    файл + `managed-settings.d/*.json`)."""
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
    """Разворачивает сырые записи `hooks.<event>` (список `{matcher, hooks:[...]}`) в
    плоские `(matcher, command)`-пары для дедупа/провенанса."""
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
    """Строит эффективную конфигурацию из слоёв (по возрастанию приоритета, как из
    `load_layers`). Возвращает `(values, provenance)`.

    Режимы слияния (D4/D15, RAG:✅ см. модульный докстринг):
    - большинство ключей — override высшим слоем, определившим ключ;
    - `env` — пер-ключевой override (ключи низшего слоя выживают, если не переопределены);
    - `hooks` — merge массивов по событию с дедупом по `(matcher, command)`;
    - `permissions.allow|deny|ask` — union с дедупом, порядок стабильный по возрастанию
      приоритета слоя; провенанс правила — самый приоритетный слой, где оно объявлено;
    - `permissions.additionalDirectories` — семантика **[UNVERIFIED]** (D15): хранится
      per-layer + union, режим слияния НЕ выбирается.
    - прочие подключи `permissions.*` (напр. `defaultMode`) — override, как обычные ключи.

    `provenance` — параллельная структура: для скаляров строка-имя слоя, для merge-ключей —
    структура, специфичная ключу (см. код ниже)."""
    values = {}
    provenance = {}

    # 1) Override-ключи верхнего уровня (всё, кроме permissions/env/hooks — у них своя
    #    merge-семантика ниже).
    for layer in layers:
        if not layer.data:
            continue
        for key, val in layer.data.items():
            if key in ("permissions", "env", "hooks"):
                continue
            values[key] = val
            provenance[key] = layer.name

    # 2) env — пер-ключевой override.
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

    # 3) hooks — merge массивов по событию, дедуп по (matcher, command).
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

    # 4) permissions.* — смешанная семантика подключей.
    perms_present = any(isinstance(l.data, dict) and isinstance(l.data.get("permissions"), dict)
                         for l in layers)
    if perms_present:
        perm_values, perm_prov = {}, {}

        # 4a) allow/deny/ask — union с дедупом, стабильный порядок (первое появление,
        #     слои идут по возрастанию приоритета); провенанс — самый приоритетный слой.
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
                    rule_layer[rule] = layer.name  # самый приоритетный слой выигрывает
            if ordered:
                perm_values[sub] = ordered
                perm_prov[sub] = [(rule, rule_layer[rule]) for rule in ordered]

        # 4b) additionalDirectories — [UNVERIFIED] (D15): per-layer + union, без выбора режима.
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

        # 4c) прочие подключи permissions.* (defaultMode, disableBypassPermissionsMode, …) —
        #     обычный override высшим слоем, определившим подключ.
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


# --- VSCode-слой (2026.07.10-SKM-ROADMAP-005 P1.5): claudeCode.* поверх user/project settings.json -------
# Path юзер-слоя VSCode — **[UNVERIFIED]** (findings §«Не подтверждено» не покрывает
# это отдельно, но это общее знание о VSCode, не Claude Code докой): linux
# `~/.config/Code/User/settings.json`, darwin `~/Library/Application Support/Code/
# User/settings.json`, win32 `~/AppData/Roaming/Code/User/settings.json` (эквивалент
# `%APPDATA%`). Считаем от `env.home`, НЕ `Path.home()` — иначе тесты в tmpdir потекут
# в реальный домашний каталог (тот же принцип, что `load_layers`).

_JSONC_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _strip_jsonc_comments(text):
    """Минимальный толерантный JSONC-препроцессор (stdlib-only, не полноценный
    парсер): убирает `//`- и `/* */`-комментарии ВНЕ строковых литералов и висячие
    запятые перед `}`/`]`. Строки, содержащие `//` (`"url": "https://..."`), не
    ломаются — комментарии распознаются только за пределами `"..."`."""
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
    """Путь юзер-слоя VSCode для текущей ОС, от `env.home` (**[UNVERIFIED]**, см.
    докстринг выше). Неизвестная ОС → None (слой не читается, не находка)."""
    home = Path(env.home)
    if sys.platform.startswith("linux"):
        return home / ".config" / "Code" / "User" / "settings.json"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    if sys.platform.startswith("win"):
        return home / "AppData" / "Roaming" / "Code" / "User" / "settings.json"
    return None


def _load_vscode_layer(name, path):
    """Файл VSCode → `Layer`, JSONC-толерантно. Отсутствующий файл — норма
    (`data=None, error=None`), битый/нечитаемый — `data=None, error=текст` (fail-soft,
    НИКОГДА не die/raise — вызывающая проверка обязана дать `info`, не `error`)."""
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
    """VSCode-слой (user + project), сведённый в эффективный dict (project
    override user — обычная семантика VSCode workspace-настроек, здесь не
    участвует permissions-merge Claude Code). `layers` несёт провенанс/ошибки
    парсинга для info-находок проверок №12/№13."""

    layers: tuple
    effective: dict


def load_vscode(env, target):
    """Читает VSCode user+project `settings.json` (JSONC-толерантно) и строит
    эффективный dict `claudeCode.*`-ключей (project побеждает user)."""
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
    """Разрешённое состояние policy-профиля проекта (2026.07.10-SKM-ROADMAP-005 P1.3). Три случая:
    - НЕ объявлен: `name=None`, `profile=None` → проверки №4/№11 дают один `info`;
    - объявлено НЕИЗВЕСТНОЕ имя: `name="…"`, `profile=None` → №4 даёт `error`;
    - объявлен и загружен: `name`+`profile` заполнены → №4/№11 сверяют факт с `expect`.
    `available` — доступные имена профилей (для сообщения об ошибке)."""

    name: Optional[str] = None
    profile: Optional[dict] = None
    available: tuple = ()


@dataclass(frozen=True)
class Context(object):
    """Контекст прогона проверок таксономии (2026.07.10-SKM-ROADMAP-005 P1.2+): слои + эффективная
    конфигурация + окружение запуска. `profile` — `ProfileState` (P1.3): разрешён
    из декларации `<target>/.swissknife.json:policy_profile` либо явного имени
    (`--profile`, P1.4). До P1.3 был `None`; проверки №4/№11 читают его.
    `vscode` (P1.5) — `VscodeState`; проверки №4 (секция `expect.vscode`)/№12/№13
    читают его, до P1.5 был `None`."""

    layers: list
    values: dict
    provenance: dict
    target: Path
    env: object
    profile: Optional[object] = None
    vscode: Optional[object] = None


def build_context(env, target, profile_name=None):
    """Читает слои, строит эффективную конфигурацию, разрешает policy-профиль и
    VSCode-слой — удобный вход для CLI/тестов. `profile_name` (явное имя из
    `--profile`, 2026.07.10-SKM-ROADMAP-005 P1.4) перекрывает декларацию `<target>/.swissknife.json:policy_profile`;
    None → берётся декларация."""
    layers = load_layers(env, target)
    values, provenance = effective_config(layers)
    profile = resolve_profile_state(env, target, profile_name)
    vscode = load_vscode(env, target)
    return Context(layers=layers, values=values, provenance=provenance,
                    target=Path(target), env=env, profile=profile, vscode=vscode)


def _load_settings_keys():
    """Снапшот канонических ключей (D13, выжимка не апстрим-схема). Отсутствие/битый
    файл — doctor не падает, но проверки №2/№5 деградируют до пустых списков."""
    data = safe_load_json(_SETTINGS_KEYS_PATH, default=None)
    if not isinstance(data, dict):
        return {"top_level": [], "permissions": [], "hook_events": [],
                "hook_events_unverified": True, "verified": "?"}
    return data


# --- Policy-профили (2026.07.10-SKM-ROADMAP-005 P1.3): декларация проекта + сверка «ожидание vs факт» ----
# Профили — пакетный ресурс рядом с пресетами, ПУТЬ module-relative (как снапшот
# ключей выше), НЕ env-relative: снапшот/профили одни на пакет, а тесты гоняют с
# tmp-корнем env (иначе искали бы профиль в tmp/configs и не нашли).
_POLICY_DIR = (Path(__file__).resolve().parents[2]
               / "configs" / "claude-code" / "policy")


def available_profiles():
    """Имена доступных профилей (`configs/claude-code/policy/*.json`), отсортированы.
    Нет каталога — пустой кортеж (не находка: сверка просто не сработает)."""
    if not _POLICY_DIR.is_dir():
        return ()
    return tuple(sorted(p.stem for p in _POLICY_DIR.glob("*.json")))


def read_policy_declaration(target):
    """Декларация ожидаемой политики: `<target>/.swissknife.json:policy_profile`
    (D11 — дом декларации НЕ `.claude/settings.json`, иначе собственная проверка №2
    пометит ключ как неканонический). harness читает файл САМ через `core.safe_load_json`,
    НЕ импортируя skiller — пакеты независимы, общее живёт в `core`. Возвращает имя
    профиля (строку) или None (нет файла / нет ключа / битый JSON — fail-soft)."""
    data = safe_load_json(Path(target) / ".swissknife.json", default=None)
    if not isinstance(data, dict):
        return None
    name = data.get("policy_profile")
    return name if isinstance(name, str) and name else None


def load_profile(env, name):
    """Профиль `configs/claude-code/policy/<name>.json` → dict, или None (пустое имя /
    нет файла / битый / не объект). `env` — для совместимости сигнатуры с 2026.07.10-SKM-ROADMAP-005 P1.4-вызовом
    (`--profile`), путь профиля module-relative (пакетный ресурс, см. `_POLICY_DIR`)."""
    if not name:
        return None
    data = safe_load_json(_POLICY_DIR / f"{name}.json", default=None)
    return data if isinstance(data, dict) else None


def resolve_profile_state(env, target, explicit_name=None):
    """Разрешает `ProfileState` для проекта: явное имя (`--profile`, 2026.07.10-SKM-ROADMAP-005 P1.4) перекрывает
    декларацию `<target>/.swissknife.json`. Имя не задано → состояние «не объявлен»;
    задано, но файла нет → состояние «неизвестный профиль» (обе ветки — не die())."""
    name = explicit_name or read_policy_declaration(target)
    available = available_profiles()
    if not name:
        return ProfileState(name=None, profile=None, available=available)
    return ProfileState(name=name, profile=load_profile(env, name), available=available)


# --- Проверка №1 — валидность JSON слоя (error) -----------------------------

def check_1_layer_json_valid(ctx):
    """Один слой с битым JSON = одна находка error — Layer.error уже несёт текст
    исключения (2026.07.10-SKM-ROADMAP-005 P1.1, fail-soft: слой исключён из merge, doctor не падает)."""
    findings = []
    for layer in ctx.layers:
        if layer.error:
            findings.append(Finding(
                id=1, level="error",
                title=f"Слой «{layer.name}» ({layer.path}) — битый JSON",
                detail=layer.error,
                hint="Почини JSON слоя (или удали файл, если он лишний) — весь слой "
                     "сейчас исключён из эффективной конфигурации.",
            ))
    return findings


# --- Проверка №2 — неканонические ключи (warn) -------------------------------

def check_2_noncanonical_keys(ctx):
    """Ключи верхнего уровня и подключи `permissions.*` каждого слоя сверяются со
    снапшотом `settings-keys.json`. Эталонный кейс — `permissions.autoApprove` (D6:
    ключа нет в доках, Claude Code молча его игнорирует)."""
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


# --- Проверка №3 — конфликт defaultMode между слоями (warn) ------------------

def check_3_default_mode_conflict(ctx):
    """`defaultMode`, объявленный больше чем в одном слое, — не сразу ошибка (нижний
    слой может дублировать верхний намеренно), но это ровно тот конфликт, что дал
    field-case: агент видит local, не зная, что project его уже переопределил."""
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


# --- Проверка №4 — соответствие policy-профилю проекта (error) ---------------

def check_4_policy_profile_conformance(ctx):
    """Эффективная конфигурация vs `expect` объявленного профиля: `defaultMode`
    (равенство), `permissions.deny` (надмножество — проект ВПРАВЕ добавить свои
    guardrails, НЕ вправе урезать), `hooks.required` (событие+команда прописаны).
    `permissions.ask` — не здесь (проверка №11). Секция `vscode` — читается в 2026.07.10-SKM-ROADMAP-005 P1.5
    (в P1.3 объявлена, но молча пропускается). Профиль не объявлен → один `info`;
    объявлено неизвестное имя → `error` (обе ветки несут единственный `info`/`error`
    за пару №4/№11 — №11 в этих случаях молчит)."""
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

    # defaultMode — равенство.
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

    # deny — надмножество (⊇): проект вправе расширить guardrails, не урезать.
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

    # hooks.required — событие+команда присутствуют в эффективной конфигурации.
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

    # vscode — секция профиля (2026.07.10-SKM-ROADMAP-005 P1.3 объявлена, P1.5 читается и сверяется). Сверяем
    # ТОЛЬКО если проект реально несёт VSCode-настройки (хотя бы один слой с данными) —
    # иначе каждый проект без VSCode ловил бы шумный error за неиспользуемый редактор.
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


# --- Проверка №5 — хуки: command существует/исполняем; событие известно ------

# Интерпретаторы: `bash script.sh` — проверять надо СКРИПТ, а не сам `bash`.
_INTERPRETERS = {"bash", "sh", "zsh", "dash", "python", "python3", "node", "perl", "ruby"}


def _resolve_hook_command_path(command, target, home):
    """Токен command-строки → путь к проверяемому файлу. Плейсхолдеры (`$VAR`/`${VAR}`)
    НЕ резолвим (Implementation Rules) — вернём None, вызывающий даёт `info`.

    Два класса, которые наивный «первый токен» ломал ложным `error`:
    - `~/.claude/hooks/x.sh` — тильда обязана раскрываться от явного `env.home`
      (иначе результат зависит от HOME процесса либо клеится к target);
    - `bash /path/x.sh` — первый токен интерпретатор, проверять надо аргумент-скрипт.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None

    first = tokens[0]
    if "$" in first:
        return None

    # `bash script.sh` / `python3 hook.py` → цель проверки — скрипт (второй токен).
    if Path(first).name in _INTERPRETERS:
        args = [t for t in tokens[1:] if not t.startswith("-")]
        if not args:
            return None  # интерпретатор без скрипта (`bash -c …`) — не проверяем
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
    return path


def check_5_hooks(ctx):
    """Событие вне снапшота → `info` (список неполный, D15/findings [UNVERIFIED]).
    Command-файл отсутствует/неисполняем → `error`. Плейсхолдер в команде → `info`."""
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
            path = _resolve_hook_command_path(command, ctx.target, ctx.env.home)
            if path is None:
                findings.append(Finding(
                    id=5, level="info",
                    title=f"Хук {event}: команда с плейсхолдером не проверена",
                    detail=command,
                    hint="Путь содержит $VAR-плейсхолдер ($CLAUDE_PROJECT_DIR и "
                         "т.п.) — doctor его не резолвит.",
                ))
                continue
            if not path.exists() or not os.access(path, os.X_OK):
                findings.append(Finding(
                    id=5, level="error",
                    title=f"Хук {event}: команда недоступна или неисполняема",
                    detail=f"{command} → {path}",
                    hint="Проверь путь и права на исполнение (chmod +x).",
                ))
    return findings


# --- Проверка №9 — секреты в env.* + gitignore-статус local (error) ----------

def check_9_secrets(ctx):
    """Эвристика ТОЛЬКО по `env` (запрещено расширять на permissions.*/тела хуков —
    ложняки взрывают доверие к doctor'у) + gitignore-статус settings.local.json."""
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
    """`git check-ignore -q` — fail-soft: нет git/не репозиторий → `info`, НЕ
    `error` (Implementation Rules). rc=0 игнорируется (норма, без находки),
    rc=1 не игнорируется (error), иначе (напр. 128 «не репозиторий») → info."""
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


# --- Проверка №11 — ask-правила при политике «не спрашивать» (error) ---------

def check_11_ask_rules_when_expected_empty(ctx):
    """Профиль объявил `permissions.ask: []` (семантика «никогда не спрашивать»), а
    эффективный `ask` непуст → `error`: ask-правила форсируют промпт В ЛЮБОМ режиме,
    включая `bypassPermissions` (RAG:✅ 2026-07-10 permissions.md — первопричина
    field-case #2). Профиль не объявлен / неизвестен / не требует пустого ask →
    молчим (первый случай уже отражён проверкой №4 одним `info`/`error`)."""
    state = ctx.profile
    if state is None or state.name is None or state.profile is None:
        return []
    expect = state.profile.get("expect") or {}
    if "permissions.ask" not in expect:
        return []
    if expect["permissions.ask"]:  # профиль ждёт НЕпустой ask — не «не спрашивать»
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


# --- Проверка №6 — мусорные точные allow-правила Bash(...) (info) ------------

def _is_exact_bash_rule(rule):
    """«Точное» правило (Implementation Rules 2026.07.10-SKM-ROADMAP-005 P1.5): `Bash(...)` БЕЗ `*` в теле —
    одноразовый след кнопки «always allow», не покрывает ничего нового."""
    return (isinstance(rule, str) and rule.startswith("Bash(") and rule.endswith(")")
            and "*" not in rule)


def check_6_dead_allow_rules(ctx):
    """Порог `DEAD_ALLOW_THRESHOLD` точных `Bash(...)`-правил в эффективном
    `permissions.allow` → `info` с числом и топ-5 примерами. Дубли уже сведены
    union'ом эффективной конфигурации (2026.07.10-SKM-ROADMAP-005 P1.1) — здесь только объём мусора."""
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


# --- Проверка №7 — противоречия allow/deny (warn) -----------------------------

def check_7_allow_deny_overlap(ctx):
    """Один и тот же ПАТТЕРН (сравнение строк, без семантического glob-матчера —
    Implementation Rules 2026.07.10-SKM-ROADMAP-005 P1.5) объявлен и в allow, и в deny → deny побеждает
    молча (RAG:✅ 2026-07-10 permissions.md, deny-first)."""
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


# --- Проверка №8 — несуществующие additionalDirectories (warn) ---------------

def check_8_additional_directories_missing(ctx):
    """`additionalDirectories` — per-layer (D15, семантика слияния [UNVERIFIED],
    вердикт этой проверки от неё не зависит): путь, объявленный В КАКОМ-ТО слое,
    не существует на диске → `warn` с именем слоя."""
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


# --- Проверка №10 — bypassPermissions без skipDangerousModePermissionPrompt (info) --

def check_10_bypass_without_skip_dialog(ctx):
    """**Ровно `info`, никогда `warn`/`error`** (D3): ключ `skipDangerousModePermissionPrompt`
    НЕ задокументирован — doctor не имеет права краснеть на недокументированном ключе,
    хотя он наблюдался в поле (field-case). Не улучшай уровень."""
    perms = ctx.values.get("permissions") or {}
    if perms.get("defaultMode") != "bypassPermissions":
        return []
    if ctx.values.get("skipDangerousModePermissionPrompt"):
        return []
    return [Finding(
        id=10, level="info",
        title="bypassPermissions без skipDangerousModePermissionPrompt",
        detail="Ключ не задокументирован (сверка 2026-07-10), наблюдался в поле; "
               "отсутствие может быть безвредно.",
        hint="Информационно — doctor не гейтит недокументированный ключ (D3).",
    )]


# --- VSCode-слой: проверки №12/№13 (warn) + info на битый/непарсящийся файл --

def _vscode_parse_errors(ctx):
    """Layer.error непустой (JSONC не распарсился) → `info` (никогда `error`,
    Implementation Rules 2026.07.10-SKM-ROADMAP-005 P1.5). Отсутствующий файл — норма, без находки."""
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
    """`claudeCode.initialPermissionMode` расходится с эффективным
    `permissions.defaultMode` слоёв Claude Code → `warn`: расширение может
    проигнорировать `defaultMode` слоёв на старте сессии (field-case #2)."""
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
    """Эффективный `bypassPermissions`, но `claudeCode.allowDangerouslySkipPermissions`
    не включён в VSCode → `warn`: режим недоступен в селекторе расширения.

    Сверяется ТОЛЬКО когда проект реально несёт VSCode-настройки (хотя бы один
    слой с данными, как №4) — иначе шум на каждый non-VSCode/headless проект
    с рекомендованным bypassPermissions."""
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


# --- Реестр проверок ----------------------------------------------------------

# Список пар (id, fn); добавление проверки = новая функция + строка здесь, не
# ветвление в мега-функции (Implementation Rules 2026.07.10-SKM-ROADMAP-005 P1.2). Порядок — по возрастанию id.
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
    """Прогоняет реестр проверок над `Context`, возвращает плоский список `Finding`."""
    findings = []
    for _id, fn in checks:
        findings.extend(fn(ctx))
    return findings


# --- Codex settings audit (P2.4, codex-parity-verdicts-v1.md §3.11, bounded closure) ---
# Отдельный, МЕНЬШИЙ набор проверок над документированными слоями Codex
# (learn.chatgpt.com/docs/config-file/config-reference, findings/03 Ф10):
# ~/.codex/config.toml → .codex/config.toml → profile, плюс `projects.<path>.trust_level`
# и `features.hooks`. НЕ обобщение 13 Claude-проверок выше — их таксономия
# permission/settings-shape у Codex носителя не имеет. Читалка **fail-soft**, как и
# Claude-сторона: битый/непрочитанный слой — Finding, никогда не «конформно».
# `tomllib` — stdlib только с Python 3.11 (матрица CI 3.9…3.13, D89 п.2): на 3.9/3.10
# слой репортится нечитаемым, второй TOML-парсер не заводится (вне скоупа, запрет
# новых рантайм-зависимостей).

# Ф10: «Project-scoped config can't override machine-local provider, auth,
# host-owned app request metadata, notification, configuration profile selection,
# or telemetry routing keys» — ключи верхнего уровня TOML, которые проектный слой
# переопределять не вправе.
CODEX_NON_OVERRIDABLE_PROJECT_KEYS = ("model_provider", "auth", "notify", "profile", "otel")


def _load_codex_toml_layer(name, path):
    """Слой Codex TOML: отсутствующий файл — норма; неразрешённый интерпретатор
    (`tomllib` < 3.11) и битый TOML — ОТЧЁТ (fail-soft), не исключение."""
    if not path.exists():
        return Layer(name, path, data=None, error=None)
    try:
        import tomllib
    except ModuleNotFoundError:
        return Layer(name, path, data=None,
                     error="интерпретатор < 3.11: tomllib недоступен, слой не читается")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return Layer(name, path, data=None, error=str(error))
    if not isinstance(data, dict):
        return Layer(name, path, data=None, error="верхний уровень TOML не таблица")
    return Layer(name, path, data=data, error=None)


def load_codex_layers(env, target):
    """Два документированных слоя Codex (Ф10), по возрастанию приоритета —
    `user` → `project`; профиль (`profile`) выбирается ВНУТРИ этих слоёв, не
    отдельным файлом, и здесь не разворачивается (вне объёма bounded closure)."""
    target = Path(target)
    return [
        _load_codex_toml_layer("user", Path(env.home) / ".codex" / "config.toml"),
        _load_codex_toml_layer("project", target / ".codex" / "config.toml"),
    ]


def codex_check_1_layers_readable(layers):
    """№1: каждый слой, который существует, обязан быть прочитан; иначе — warn,
    никогда молчаливое "conformant"."""
    return [Finding(1, "warn", f"слой '{layer.name}' не прочитан",
                    detail=f"{layer.path}: {layer.error}",
                    hint="слой репортится нечитаемым, а не конформным")
            for layer in layers if layer.error]


def codex_check_2_project_overrides_machine_local_key(layers):
    """№2: проектный слой не вправе переопределять machine-local ключи (Ф10)."""
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
    """№3: `features.hooks=false` эффективно — задеплоенные `harness hooks
    --provider codex` поверхности не активируются (не ошибка, info)."""
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
    """Прогоняет Codex-реестр проверок над списком `Layer`, тот же плоский
    список `Finding`, что и Claude-сторона (общие `counts`/`exit_code` ниже)."""
    findings = []
    for _id, fn in checks:
        findings.extend(fn(layers))
    return findings


def render_codex_text(target, findings):
    """Человекочитаемый отчёт Codex-аудита — тот же формат, что `render_text`,
    без policy-профиля (Codex-сторона его не резолвит в этом bounded closure)."""
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


# --- Рендер отчёта, счётчики, код возврата (2026.07.10-SKM-ROADMAP-005 P1.4) ----------------------------
# Контракт CLI (`harness doctor --settings`): человекочитаемый отчёт ЛИБО единый
# JSON-документ + exit-code 0/1/2. На `--json` стоит fleet-скан P1.6 — форма ниже
# ЯВЛЯЕТСЯ контрактом, не стилем.

# Порядок вывода уровней в человекочитаемом отчёте (сначала самое важное).
_LEVEL_ORDER = ("error", "warn", "info")


def counts(findings):
    """Счётчики находок по уровням: `{"error": n, "warn": m, "info": k}`."""
    c = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        if f.level in c:
            c[f.level] += 1
    return c


def exit_code(findings):
    """Код возврата по составу находок: `2` — есть error; `1` — есть warn (без
    error); `0` — находок нет либо только `info`. `--json` кода не меняет."""
    c = counts(findings)
    if c["error"]:
        return 2
    if c["warn"]:
        return 1
    return 0


def _profile_name(ctx):
    """Имя разрешённого policy-профиля (из декларации или `--profile`) либо None."""
    prof = getattr(ctx, "profile", None)
    return prof.name if prof is not None else None


def render_text(ctx, findings):
    """Человекочитаемый отчёт: группировка по уровням, на каждую находку строка
    `[level] #id <title>` → `    — <detail>` → `    → <hint>`; финальная сводка."""
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
    """Машинный вид (контракт для 2026.07.10-SKM-ROADMAP-005 P1.6): dict под `json.dumps(..., ensure_ascii=False)`.
    Ровно один такой документ идёт в stdout при `--json`, ничего кроме него."""
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
