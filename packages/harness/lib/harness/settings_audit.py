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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core import safe_load_json

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
