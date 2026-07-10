"""Ядро settings-doctor: слои настроек Claude Code, эффективная конфигурация, Finding.

Читает ЧЕТЫРЕ слоя настроек Claude Code (user → project → local → managed, по
возрастанию приоритета) и строит из них ЭФФЕКТИВНУЮ конфигурацию с провенансом
(из какого слоя пришло каждое итоговое значение). Каркас находки (`Finding`) — тоже
здесь; сами проверки таксономии заводятся поверх этого модуля в P1.2/P1.3/P1.5, CLI —
в P1.4. reader-семантика **fail-soft**: битый слой — это ОТЧЁТ (проверка №1, P1.2), а
не смерть doctor'а — намеренный дубль чтения `.claude/settings*.json` рядом с
`harness.settings.load_settings` (тот `die()`-ает на битом JSON — writer-семантика,
её нельзя чинить, не сломав `permissions`/`hooks`).

Несущие внешние факты (precedence слоёв, merge-режимы, managed-пути) сверены RAG —
см. `plans/SKM-ROADMAP-005/findings/P1-cc-settings-facts.md` (дата сверки зафиксирована
там; при регрессии — пере-сверить, доки Claude Code меняются между версиями CLI).
stdlib-only."""
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
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
# которая когда-нибудь эту величину использует (P1.5 №8 работает per-layer, не от union).
UNVERIFIED_MERGE_KEYS = ("permissions.additionalDirectories",)

# Подключи permissions.*, которые сливаются как union-массивы (не путать с
# additionalDirectories выше и с прочими скалярными подключами вроде defaultMode).
_PERMISSIONS_ARRAY_KEYS = ("allow", "deny", "ask")


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
    """Находка проверки таксономии (P1.2+). Ядро P1.1 только объявляет форму."""

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


@dataclass(frozen=True)
class Context(object):
    """Контекст прогона проверок таксономии (P1.2+): слои + эффективная
    конфигурация + окружение запуска. `profile` — всегда `None` в P1.2 (объявлен,
    чтобы `fn(ctx)` проверок не менялась сигнатурой, когда P1.3 заведёт профили)."""

    layers: list
    values: dict
    provenance: dict
    target: Path
    env: object
    profile: Optional[object] = None


def build_context(env, target, profile=None):
    """Читает слои и строит эффективную конфигурацию — удобный вход для CLI/тестов."""
    layers = load_layers(env, target)
    values, provenance = effective_config(layers)
    return Context(layers=layers, values=values, provenance=provenance,
                    target=Path(target), env=env, profile=profile)


def _load_settings_keys():
    """Снапшот канонических ключей (D13, выжимка не апстрим-схема). Отсутствие/битый
    файл — doctor не падает, но проверки №2/№5 деградируют до пустых списков."""
    data = safe_load_json(_SETTINGS_KEYS_PATH, default=None)
    if not isinstance(data, dict):
        return {"top_level": [], "permissions": [], "hook_events": [],
                "hook_events_unverified": True, "verified": "?"}
    return data


# --- Проверка №1 — валидность JSON слоя (error) -----------------------------

def check_1_layer_json_valid(ctx):
    """Один слой с битым JSON = одна находка error — Layer.error уже несёт текст
    исключения (P1.1, fail-soft: слой исключён из merge, doctor не падает)."""
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


# --- Проверка №5 — хуки: command существует/исполняем; событие известно ------

def _resolve_hook_command_path(command, target):
    """Первый токен command-строки → путь. Плейсхолдеры (`$VAR`/`${VAR}`) НЕ
    резолвим (Implementation Rules) — вернём None, вызывающий даёт `info`."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None
    first = tokens[0]
    if "$" in first:
        return None
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
            path = _resolve_hook_command_path(command, ctx.target)
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


# --- Реестр проверок ----------------------------------------------------------

# Список пар (id, fn); добавление проверки = новая функция + строка здесь, не
# ветвление в мега-функции (Implementation Rules P1.2). Порядок — по возрастанию id.
CHECKS = (
    (1, check_1_layer_json_valid),
    (2, check_2_noncanonical_keys),
    (3, check_3_default_mode_conflict),
    (5, check_5_hooks),
    (9, check_9_secrets),
)


def run_checks(ctx, checks=CHECKS):
    """Прогоняет реестр проверок над `Context`, возвращает плоский список `Finding`."""
    findings = []
    for _id, fn in checks:
        findings.extend(fn(ctx))
    return findings
