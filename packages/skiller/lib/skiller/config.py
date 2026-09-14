"""Project config (.swissknife.json), профили и выбор скиллов/плагинов."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path

from core import (ConfigSource, ProviderConfigCatalog, ProviderConfigLayer,
                  ResolvedProviderConfig, detect_project_type, load_provider_manifest,
                  provider_config_catalog,
                  resolve_provider_config as resolve_shared_provider_config)

from .common import (AGENT_DEFAULTS, confirm, die,
                     parse_frontmatter_fields, warn)

# CORE-политика раздачи: токен-экономные скиллы, которые swissknifeman кладёт в
# КАЖДЫЙ проект по умолчанию (см. deep_analysis §5–§6). Каналы разной гранулярности:
#   connect (marketplace) — bucket-granular → CORE_BUCKETS;
#   vendor (физ. копия)    — skill-granular → CORE_SKILLS + DEFAULT_EXCLUDE.
# DEFAULT_EXCLUDE убирает из авто-раздачи скиллы, дублирующие хаб maind
# (shared-memory ← agent-memory MCP) и ручные инструменты (cross-project-coordinator).
# Отключается флагом --no-core у connect/vendor.
# CORE хранит только общую дисциплину исполнения. Onboarding, поиск, GitHub review
# и стиль ответа подключаются предметно; plan-protocol поставляется runtime Task.
def _load_core_policy():
    """CORE-политика из configs/core-policy.json (декларативно) с фолбэком на встроенные дефолты.
    Самолокация через __file__ → работает на import-time (потребители budget/connect/vendor/registry
    берут константы модульного уровня). Standalone-safe, stdlib-only: нет файла/битый → дефолты."""
    defaults = {
        "skills": ["general/context-economy", "general/anti-drift",
                   "general/session-handoff", "general/verify-claims"],
        "resident_budget_target": 750,
        "core_plugin": "core",
        "core_buckets": ["general", "oss-dev"],
        "default_command_plugins": ["task"],
        "default_exclude": ["system/shared-memory", "system/cross-project-coordinator"],
    }
    try:
        p = Path(__file__).resolve().parents[2] / "configs" / "core-policy.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k in defaults:
                if k in data:
                    defaults[k] = data[k]
    except Exception:
        pass  # standalone/битый файл → встроенные дефолты
    return defaults


_CORE_POLICY = _load_core_policy()

CORE_SKILLS = list(_CORE_POLICY["skills"])
# Имя курируемого marketplace-плагина (connect-канал), несущего РОВНО CORE_SKILLS.
# «Умное подключение»: вместо целых бакетов general(19)+oss-dev(10) ≈ 1956 резидентных
# токенов в КАЖДОМ проекте connect пушит этот лёгкий плагин — экономия даже с текущим
# составом. Точное число скиллов/токенов — `len(CORE_SKILLS)` и `skiller budget
# --check-core` (не хардкодь снапшот в комментариях: «7 ≈ 480» протухло при росте
# CORE_SKILLS до 8, см. аудит Т-2). Скиллы физически остаются в своих бакетах (плагин
# ссылается на них путём, без копий — marketplace-запись source:"./" + явный skills[]).
# См. registry.py.
CORE_PLUGIN = _CORE_POLICY["core_plugin"]
# Целевой потолок РЕЗИДЕНТНОГО (⊕ tier-0) бюджета CORE_SKILLS: name+description каждого CORE-скилла
# грузится в КАЖДЫЙ запрос (постоянный налог). `skiller budget --check-core` сверяет фактический резидент
# с этим таргетом — гейт против тихого роста ядра (добавил скилл в CORE → раздул резидент → сигнал).
RESIDENT_BUDGET_TARGET = _CORE_POLICY["resident_budget_target"]
# Бакеты, которые раньше пушила CORE-политика connect целиком (теперь — лёгкий CORE_PLUGIN).
# Сохранены для back-compat/миграции: connect видит их в settings онбордженных проектов и
# подсказывает снять (иначе двойная загрузка). Vendor-канал по-прежнему берёт CORE_SKILLS пофайлово.
CORE_BUCKETS = list(_CORE_POLICY["core_buckets"])
# Командные плагины (НЕ бакеты скиллов), которые connect включает в КАЖДЫЙ проект по умолчанию.
# `task` — интент-команды /task:design|dev|review|research|fix (пакет task, commands-only): раздаём
# везде, т.к. intent-router политика предлагает именно их — без плагина предложение не резолвится.
# Как и CORE_PLUGIN: объявлены в marketplace и тихо пропускаются на старом marketplace / в тест-реестре
# (там marketplace.json = {}). Codex публикует команды как скиллы, поэтому их описания
# входят в его listing budget. Отключить точечно — enabledPlugins[...]=false
# (connect уважает явный false, как и для бакетов).
DEFAULT_COMMAND_PLUGINS = list(_CORE_POLICY["default_command_plugins"])
DEFAULT_EXCLUDE = list(_CORE_POLICY["default_exclude"])
# Минимальный безопасный набор для НЕРАСПОЗНАННОГО типа проекта (autodetect → standalone).
# НЕ разворачиваем `["*"]` (= все бакеты) по умолчанию — это «бездушный дамп всего». Явный
# `--profile standalone` («поставь всё») остаётся доступен; авто-фолбэк ставит только ядро.
# == CORE_BUCKETS (канал-независимая консистентность): раньше сюда входил бакет `system`
# целиком, но он несёт system/shared-memory и system/cross-project-coordinator — ровно те
# дубли хаба maind, что CORE-политика гонит через DEFAULT_EXCLUDE. Фолбэк не должен втягивать
# их обратно, поэтому он совпадает с CORE_BUCKETS.
MINIMAL_BUCKETS = list(CORE_BUCKETS)


def core_skill_tuples(env, exclude):
    """CORE_SKILLS → [(bucket, rel, dir, fm_name)]; пропускает excluded и
    отсутствующие. Формат кортежа совпадает с vendor.collect_skills."""
    out = []
    for path in CORE_SKILLS:
        bucket, _, rel = path.partition("/")
        d = env.root / "skills" / bucket / rel
        md = d / "SKILL.md"
        if not md.is_file():
            continue
        fm_name = parse_frontmatter_fields(md)["name"]
        if {fm_name, d.name, path} & exclude:
            continue
        out.append((bucket, rel, d, fm_name))
    return out


# --- типизированный носитель .swissknife.json --------------------------------
@dataclass(frozen=True, eq=False)
class ProjectConfig(Mapping):
    """Конфиг проекта `.swissknife.json` как объект: типизированный доступ вместо
    голого `dict` (аудит `audits/skm.md` §4, план 2026.07.31-SKM-LEAN P6.2).

    **Единственный носитель перечня ключей.** Раньше ключи жили в трёх местах
    (`CONFIG_KEYS` в `common.py`, `schema/swissknife.schema.json`, код); поля этого
    объекта стали бы четвёртым, поэтому `CONFIG_KEYS` теперь ВЫВОДИТСЯ отсюда —
    `metadata["json_type"]` каждого поля несёт тот Python-тип, которым `isinstance`
    валидирует значение (кортеж = мульти-тип, в схеме `oneOf`). Оба гейта синхрона
    (`skiller doctor` и `tests/test_schema.py`) читают производный `CONFIG_KEYS`
    и не правятся.

    **Почему НЕ подкласс `dict`** (в отличие от `maind.config.Config`, обёртки конфига
    УЗЛА): подкласс оставляет мутацию открытой (`cfg["agent"] = …`) и обесценивает
    типизацию — атрибут и ключ разошлись бы молча. Здесь `frozen=True` плюс
    read-only Mapping-проекция на `raw`: старый доступ (`cfg.get("agent")`,
    `cfg["agent"]`, `if cfg:`) продолжает работать байт-в-байт для потребителей,
    ещё не переведённых на атрибуты, но записи нет ни у кого.

    `raw` — ИСХОДНЫЙ словарь как есть (провайдерная ветка, `_`/`$`-ключи, back-compat
    файлов из репозиториев флота): нормализации/копии нет, иначе объект стал бы
    вторым источником истины о содержимом файла.
    """

    project_type: str = field(default="", metadata={"json_type": str})
    buckets: list = field(default_factory=list, metadata={"json_type": list})
    # Exact marketplace plugin set; `core`/`task` can be declared explicitly
    # for projects that intentionally need no profile buckets.
    plugins: list = field(default_factory=list, metadata={"json_type": list})
    exclude: list = field(default_factory=list, metadata={"json_type": list})
    presets: list = field(default_factory=list, metadata={"json_type": list})
    skills_path: str = field(default="", metadata={"json_type": str})
    agent: str = field(default="", metadata={"json_type": str})
    # None ≠ {}: провайдерная ветка отличает «ключа нет» (слой не заводится) от
    # «есть пустой слой» — ровно то, что делал config.get("providers").
    providers: dict | None = field(default=None, metadata={"json_type": dict})
    # Строка (путь, back-compat memory-хука) ИЛИ объект {path, sync?} — мульти-тип
    # уезжает в CONFIG_KEYS кортежем и в схему как oneOf (см. common.CONFIG_KEYS).
    memory_brain: str | dict | None = field(default=None, metadata={"json_type": (str, dict)})
    coordinator_ignore: list = field(default_factory=list, metadata={"json_type": list})
    shape: str = field(default="", metadata={"json_type": str})
    stacks: list = field(default_factory=list, metadata={"json_type": list})
    skills_map: dict = field(default_factory=dict, metadata={"json_type": dict})
    policy_profile: str = field(default="", metadata={"json_type": str})
    # Не ключ конфига: без "json_type" в metadata поле не попадает в CONFIG_KEYS.
    raw: Mapping = field(default_factory=dict, repr=False)

    # Mapping-проекция на raw — read-only back-compat поверхность для потребителей
    # (и тестов), передающих/читающих конфиг словарём. Значения берутся из raw, а не
    # из полей: `.get("x")` обязан вернуть ровно то, что лежит в файле.
    def __getitem__(self, key):
        return self.raw[key]

    def __iter__(self):
        return iter(self.raw)

    def __len__(self):
        return len(self.raw)

    @classmethod
    def from_raw(cls, data):
        """Собрать объект из прочитанного JSON БЕЗ валидации (её делает
        `validate_config` до сборки) и без нормализации значений."""
        known = {f.name: f for f in fields(cls) if "json_type" in f.metadata}
        return cls(raw=data, **{name: data[name] for name in known if name in data})

    @classmethod
    def coerce(cls, config):
        """`ProjectConfig` → как есть; словарь (легаси-вызов, тест, ветка без файла)
        → типизированный объект. Точка нормализации для функций, которые исторически
        принимали `dict` и обязаны продолжать его принимать."""
        if isinstance(config, cls):
            return config
        return cls.from_raw(config or {})

    @classmethod
    def load(cls, env, target):
        """Прочитать `.swissknife.json` проекта: те же сообщения `die`, тот же порядок
        проверок и тот же пустой конфиг при отсутствии файла, что у прежнего
        `load_config` — меняется носитель, не поведение."""
        cfg_file = target / ".swissknife.json"
        if not cfg_file.exists():
            return cls()
        try:
            config = json.loads(cfg_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{cfg_file}: invalid JSON: {e}")
        validate_config(env, config, cfg_file)
        return cls.from_raw(config)


# Производное от полей ProjectConfig (P6.2): имя-носитель одно, значение собирается.
# Реэкспортируется как `skiller.common.CONFIG_KEYS` — исторический дом имени, откуда
# его берут оба гейта синхрона со схемой и документация.
CONFIG_KEYS = {f.name: f.metadata["json_type"]
               for f in fields(ProjectConfig) if "json_type" in f.metadata}


def _type_label(pytype):
    """Человекочитаемая метка ожидаемого типа для сообщения об ошибке. Кортеж типов
    (напр. memory_brain = (str, dict)) → «string or object»."""
    names = {str: "string", list: "list of strings", dict: "object",
             int: "integer", bool: "boolean"}
    if isinstance(pytype, tuple):
        return " or ".join(names.get(t, t.__name__) for t in pytype)
    return names.get(pytype, pytype.__name__)


def validate_config(env, config, cfg_file):
    import difflib
    profile_names = sorted(p.stem for p in (env.root / "profiles").glob("*.json"))
    for key, value in config.items():
        if key.startswith(("_", "$")):  # _comment / $schema — DX, не валидируем
            continue
        if key not in CONFIG_KEYS:
            hint = difflib.get_close_matches(key, CONFIG_KEYS, n=1)
            suffix = f" — did you mean '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: unknown key '{key}'{suffix}")
        if not isinstance(value, CONFIG_KEYS[key]):
            die(f"{cfg_file}: '{key}' must be a {_type_label(CONFIG_KEYS[key])}")
        if CONFIG_KEYS[key] is list and not all(isinstance(v, str) for v in value):
            die(f"{cfg_file}: '{key}' must be a list of strings")
    # memory_brain-объект: path обязателен (строчная форма — просто путь, back-compat).
    mb = config.get("memory_brain")
    if isinstance(mb, dict) and not (isinstance(mb.get("path"), str) and mb["path"]):
        die(f"{cfg_file}: 'memory_brain' object must have a non-empty 'path'")
    if config.get("project_type") and config["project_type"] not in profile_names:
        die(f"{cfg_file}: unknown project_type '{config['project_type']}' "
            f"(available: {', '.join(profile_names)})")
    if config.get("agent") and config["agent"] not in AGENT_DEFAULTS:
        die(f"{cfg_file}: unknown agent '{config['agent']}' "
            f"(available: {', '.join(AGENT_DEFAULTS)})")
    # Ключи объявлены в CONFIG_KEYS (валидируются для back-compat .swissknife.json),
    # но НЕ читаются логикой connect/vendor — не молчим, иначе пользователь пропишет
    # и не поймёт, почему нет эффекта. (project_type/buckets/exclude/agent/skills_path/
    # memory_brain — реально потребляются, сюда не входят.)
    _RESERVED = {
        "skills_map": "зарезервирован, но ещё не реализован — игнорируется",
        "shape": "зарезервирован под agent-packs, ещё не реализован — игнорируется",
        "stacks": "зарезервирован под agent-packs, ещё не реализован — игнорируется",
        "coordinator_ignore": "legacy-ключ без потребителя — игнорируется",
    }
    for _key, _msg in _RESERVED.items():
        if config.get(_key):
            warn(f"{cfg_file}: '{_key}' {_msg}")


def load_config(env, target):
    """Историческое имя фабрики (15 сайтов в пакете + внешние тесты) — теперь
    возвращает `ProjectConfig`, а не голый `dict`."""
    return ProjectConfig.load(env, target)


def provider_config_layer(config, project_id="local"):
    """Return the project-owned provider layer, or ``None`` when it is absent."""
    value = ProjectConfig.coerce(config).providers
    if value is None:
        return None
    return ProviderConfigLayer(
        ConfigSource("project", f"project:{project_id}", ".swissknife.json", "/providers"),
        value,
    )


def resolve_provider_config(config, catalog: ProviderConfigCatalog, *, project_id="local",
                            operation=None, fleet_project=None, fleet_defaults=None) -> ResolvedProviderConfig:
    """Thin skiller carrier adapter; selection/delivery semantics stay unchanged."""
    return resolve_shared_provider_config(catalog=catalog, operation=operation,
                                          project=provider_config_layer(config, project_id),
                                          fleet_project=fleet_project,
                                          fleet_defaults=fleet_defaults)


def resolve_distribution_providers(config, *, project_id="local", manifest_path=None):
    """Resolve selected skill-distribution providers through the frozen P1 adapter."""
    manifest_path = Path(manifest_path) if manifest_path is not None else (
        Path(__file__).resolve().parents[4] / "configs/provider-capabilities.json")
    catalog = provider_config_catalog(load_provider_manifest(manifest_path))
    return resolve_provider_config(config, catalog, project_id=project_id)


def render_provider_diagnostic(diagnostic):
    """Package-owned Russian text while preserving the shared diagnostic envelope."""
    return f"provider config: {diagnostic.code} ({diagnostic.path})"


def autodetect(target):
    """Тип проекта (== имя профиля) — единый детектор core. Каждый возвращаемый id
    обязан иметь profiles/<id>.json (гейт покрытия в validate.sh)."""
    return detect_project_type(target)


def load_profile(env, name):
    f = env.root / "profiles" / f"{name}.json"
    if not f.exists():
        available = ", ".join(
            sorted(p.stem for p in (env.root / "profiles").glob("*.json")))
        die(f"unknown profile '{name}' (available: {available})")
    return json.loads(f.read_text(encoding="utf-8"))


def all_buckets(env):
    return sorted(d.name for d in (env.root / "skills").iterdir() if d.is_dir())


def _expand_presets_buckets(env, config):
    """Развернуть `presets[]` из .swissknife.json в список бакетов (переиспользуя
    skillset.resolve_presets — extends/cycle-detection единожды, без дубля).

    Каналы .swissknife.json (connect + legacy vendor) — bucket-granular, поэтому берём
    ТОЛЬКО bucket-компонент пресетов; их skill-granular `include` тут не имеет смысла
    (в connect игнорируется, как и `exclude`). Если пресет несёт лишь `include` без
    `buckets` — предупреждаем, чтобы пустой эффект не выглядел молчаливым багом.
    Ленивый импорт: skillset импортит config → на module-level был бы цикл."""
    names = ProjectConfig.coerce(config).presets or []
    if not names:
        return []
    from .skillset import resolve_presets  # lazy: избегаем циклического импорта
    pre_buckets, pre_include, _skipped = resolve_presets(env, names)
    if pre_include and not pre_buckets:
        warn(".swissknife.json: presets содержат только skill-granular 'include' без "
             "'buckets' — в bucket-granular каналах (connect/legacy vendor) эффекта нет; "
             "для skill-level используйте vendor sync (.swissknifeman/config.json)")
    return list(dict.fromkeys(pre_buckets))


def resolve_selection(env, target, config, flag_profile, flag_items):
    """Shared precedence: flags > .swissknife.json > autodetect.
    Returns (items, profile_name, profile_source, source_label, include_meta).

    В ветке .swissknife.json `presets[]` разворачиваются в бакеты (через
    skillset.resolve_presets) и объединяются с явными `buckets`, затем вычитается
    `exclude`: buckets = (resolve_presets(presets) ∪ buckets) − exclude. Формула
    симметрична vendor sync (resolve_skillset), но на уровне бакетов (каналы
    .swissknife.json bucket-granular). Точность precedence сохранена: presets
    действуют только когда выбор идёт из .swissknife.json (не из flags/профиля)."""
    config = ProjectConfig.coerce(config)
    buckets = all_buckets(env)
    if flag_items:
        return flag_items, None, "items", "flags", False
    if flag_profile:
        prof = load_profile(env, flag_profile)
        items = buckets if prof["buckets"] == ["*"] else prof["buckets"]
        return items, flag_profile, "flag", "--profile", prof.get("include_meta", False)
    if config.plugins:
        return list(config.plugins), None, "config", ".swissknife.json plugins", False
    preset_buckets = _expand_presets_buckets(env, config)
    if config.buckets or preset_buckets:
        # (presets ∪ buckets) − exclude. exclude в bucket-granular каналах skill-level
        # (connect его игнорит с NOTE), но на уровне имён бакетов вычитаем корректно —
        # симметрично формуле vendor sync; дедуп сохраняет порядок (presets раньше buckets).
        merged = list(dict.fromkeys(preset_buckets + list(config.buckets or [])))
        excl = set(config.exclude or [])
        items = [b for b in merged if b not in excl]
        label = (".swissknife.json presets+buckets" if preset_buckets and config.buckets
                 else ".swissknife.json presets" if preset_buckets
                 else ".swissknife.json buckets")
        return items, None, "config", label, False
    if config.project_type:
        prof = load_profile(env, config.project_type)
        items = buckets if prof["buckets"] == ["*"] else prof["buckets"]
        return (items, config.project_type, "config",
                ".swissknife.json project_type", prof.get("include_meta", False))
    name = autodetect(target)
    prof = load_profile(env, name)
    # Тип не распознан (фолбэк-профиль standalone = `["*"]`) → НЕ ставим всё подряд:
    # отдаём минимальное ядро и маркер источника `autodetect-fallback`, чтобы вызывающий
    # (connect/vendor) предупредил и предложил указать профиль явно. Явный `--profile
    # standalone` сюда не попадает (обрабатывается веткой flag_profile выше).
    if prof["buckets"] == ["*"]:
        items = [b for b in MINIMAL_BUCKETS if b in buckets]
        return items, name, "autodetect-fallback", "autodetect-fallback", False
    return prof["buckets"], name, "autodetect", "autodetect", prof.get("include_meta", False)


def resolve_profile_name(target, config, flag_profile):
    """Имя профиля по той же иерархии, что resolve_selection: --profile >
    .swissknife.json project_type > autodetect. None — если выбор задан явными
    buckets (профиля нет)."""
    config = ProjectConfig.coerce(config)
    if flag_profile:
        return flag_profile
    if config.buckets:
        return None
    if config.project_type:
        return config.project_type
    return autodetect(target)


# --- project root discovery ----------------------------------------------------
def find_project_root(env, start=None):
    """Nearest dir upward containing .swissknife.json, .claude/ or .git."""
    p = (start or Path.cwd()).resolve()
    home = env.home.resolve()
    while True:
        if str(p) == p.root:
            return None, None
        if (p / ".swissknife.json").is_file():
            return p, ".swissknife.json"
        if (p / ".swissknifeman" / "config.json").is_file():
            return p, ".swissknifeman/config.json"
        if (p / ".claude").is_dir():
            return p, ".claude/"
        if (p / ".git").exists():  # dir or file (worktree/submodule)
            return p, ".git"
        if p == home:
            return None, None
        p = p.parent


def resolve_target(env, opts, allow_home_confirm=False):
    """--target wins; otherwise walk up from CWD. Refuses the registry repo."""
    if opts.get("target"):
        target = Path(os.path.expanduser(opts["target"])).resolve()
        if not target.is_dir():
            die(f"каталог не найден: {target}")
        via = "--target"
    else:
        target, via = find_project_root(env)
        if target is None:
            die("корень проекта не найден выше CWD (искал .swissknife.json, "
                ".claude/, .git). Перейдите в проект или создайте "
                ".swissknife.json в его корне.")
        if target == env.home.resolve() and allow_home_confirm:
            print("Корень проекта определился как домашняя директория.")
            if not confirm(f"Продолжить с {target}?"):
                die("отменено — перейдите в проект или укажите --target")
    if target == env.root.resolve() and env.cmd in ("connect", "vendor", "update", "sync", "init"):
        die("вы внутри самого реестра swissknifeman — перейдите в "
            "потребляющий проект")
    return target, via
