"""Конфиг узла maind: config.json в корне монорепо (primary; legacy .maind.json
подхватывается тем же резолвером) + fallback на legacy .projects.json (brain).

Валидация — на stdlib (без jsonschema): декларативные карты типов + difflib-подсказки,
как в swissknifeman/config.py. load_config возвращает (config, source) для совместимости;
Config.load(env) — обёртка над тем же, инкапсулирует path/source/save и доступ к секциям,
чтобы менять логику конфига в одном месте. Config — подкласс dict (старый доступ
config["projects"] продолжает работать)."""
from __future__ import annotations

import copy
import difflib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from core import (ConfigSource, ProviderConfigCatalog, ProviderConfigLayer,
                  ResolvedProviderConfig,
                  load_provider_manifest, provider_config_catalog,
                  resolve_provider_config as resolve_shared_provider_config)
from .common import (detect_project_type, die, docs_visibility_for, sanitize,
                     warn)
from .constants import (CODE_GRAPH_DEFAULTS, DIGEST_BUDGET_CHARS, DIGEST_ITEM_MAX_CHARS,
                        DIGEST_SHARED_MAX, GRAPH_ADAPTERS, HEARTBEAT_DEFAULT_MS,
                        LEGACY_GRAPH_ADAPTERS, MAX_IDLE_DEFAULT_MS, MEMORY_HTTP_PORT,
                        MEMORY_STREAM_PORT, PERPLEXITY_WEB_DEFAULTS, SERVICE_NAME)

# project.id попадает в scope-маркер памяти `[[s:project:<id>]]` (memory.mark_scope) и в
# имя namespace — поэтому ограничиваем безопасным алфавитом, иначе спецсимволы (']', пробел,
# перевод строки) ломают парсинг scope при recall/forget и могут подменить чужой scope.
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Имена doc-папок по умолчанию (когда проект не задал явно).
DEFAULT_DOCS_FOLDER_NAMES = ("docs", "docs-public")


def normalize_docs_folders(raw, default_visibility="private"):
    """Старый плоский список ['docs','docs-public'] И новый список объектов
    {id,vault,repo,visibility} → единый список нормализованных объектов. Зеркало
    brain.folders.normalize_folders (brain — отдельный репо, импортировать нельзя).
    Правило статуса при миграции голого имени: 'docs-public' → public (старый хардкод),
    иначе → default_visibility (по типу проекта). Дубли по id схлопываются."""
    if not raw:
        raw = list(DEFAULT_DOCS_FOLDER_NAMES)
    out, seen = [], set()
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            vis = "public" if name == "docs-public" else (default_visibility or "private")
            fo = {"id": name, "vault": name, "repo": name, "visibility": vis}
        elif isinstance(item, dict):
            vault = (item.get("vault") or item.get("id") or "").strip()
            repo = (item.get("repo") or vault).strip()
            fid = (item.get("id") or vault).strip()
            vis = item.get("visibility")
            if vis not in ("public", "private"):
                vis = "public" if vault == "docs-public" else (default_visibility or "private")
            fo = {"id": fid, "vault": vault, "repo": repo, "visibility": vis}
        else:
            continue
        if fo["id"] in seen:
            continue
        seen.add(fo["id"])
        out.append(fo)
    return out


# Топ-ключи .maind.json (кроме _-мета). Значение — ожидаемый Python-тип.
TOP_KEYS = {
    "node": dict,
    "memory": dict,
    "graph": dict,
    "code_graph": dict,
    "agents": dict,
    "projects": list,
    "namespaces": dict,
    "integrations": dict,
    "mcp": dict,
    "observability": dict,
    "providers": dict,
    "role_packs": dict,        # роль → agent-pack (вариант C: project.roles → авто-доставка пака)
}

NODE_ROLES = {"primary", "secondary", "mirror"}
PROJECT_STATUSES = {"active", "archived", "planning"}
LOG_LEVELS = {"debug", "info", "warn", "error"}
# memory.role (ADR-0001, P4.2): standalone — сегодняшний режим (свой демон, дефолт,
# back-compat) · host — эта машина держит ЕДИНСТВЕННЫЙ живой демон · client — своей
# памяти нет, ходит к memory.url (локальный демон поднимать ЗАПРЕЩЕНО кодом, D27).
MEMORY_ROLES = {"standalone", "host", "client"}
LOOPBACK_HOSTNAMES = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _is_loopback_url(url):
    """True, если хост URL — loopback/wildcard (client с таким url перепутал бы
    удалённый демон со своим собственным)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in LOOPBACK_HOSTNAMES


# ── валидация ───────────────────────────────────────────────────────────────
def _check_section(cfg_file, section, value, types, enums=None):
    """Проверяет dict-секцию: известные ключи — по типу; enum-ключи — по множеству;
    неизвестные ключи — warn (forward-compat, не фатально)."""
    enums = enums or {}
    if not isinstance(value, dict):
        die(f"{cfg_file}: секция '{section}' должна быть объектом")
    for k, v in value.items():
        if k.startswith("_"):
            continue
        if k in enums:
            if v not in enums[k]:
                die(f"{cfg_file}: {section}.{k} = '{v}' — допустимо: "
                    f"{', '.join(sorted(map(str, enums[k])))}")
        elif k in types:
            if not isinstance(v, types[k]):
                die(f"{cfg_file}: {section}.{k} должно быть типа {types[k].__name__}")
        else:
            warn(f"{cfg_file}: неизвестный ключ {section}.{k} (игнорируется)")


def validate_config(config, cfg_file):
    """Бросает die при ошибке схемы. Неизвестные топ-ключи — фатальны (с подсказкой);
    неизвестные вложенные — предупреждение."""
    if not isinstance(config, dict):
        die(f"{cfg_file}: корень конфига должен быть объектом")
    for key in config:
        if key.startswith("_"):
            continue
        if key not in TOP_KEYS:
            hint = difflib.get_close_matches(key, list(TOP_KEYS), n=1)
            suffix = f" — возможно, '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: неизвестный ключ '{key}'{suffix}")
        if not isinstance(config[key], TOP_KEYS[key]):
            want = "массивом" if TOP_KEYS[key] is list else "объектом"
            die(f"{cfg_file}: '{key}' должно быть {want}")

    _check_section(cfg_file, "node", config.get("node", {}),
                   {"id": str, "name": str, "description": str},
                   {"role": NODE_ROLES})
    _check_section(cfg_file, "memory", config.get("memory", {}),
                   {"enabled": bool, "config_path": str, "http_port": int,
                    "stream_port": int, "data_dir": str, "url": str, "digest": dict,
                    "role": str, "secret_file": str},
                   {"role": MEMORY_ROLES})
    mem = config.get("memory") or {}
    if mem.get("role") == "client":
        url = mem.get("url")
        if not url:
            die(f"{cfg_file}: memory.role='client' требует memory.url (адрес хоста памяти) — "
                f"client не поднимает свой демон (D27)")
        if _is_loopback_url(url):
            die(f"{cfg_file}: memory.role='client' — memory.url='{url}' указывает на loopback; "
                f"client обязан указывать адрес ХОСТА памяти, не свой собственный демон")
    _check_section(cfg_file, "graph", config.get("graph", {}),
                   {"enabled": bool, "adapter": str, "persist": bool,
                    "persist_path": str, "store_layout": str})
    # adapter: канонически {federation, disabled}; legacy (memory/graphify/networkx)
    # принимаем с предупреждением (нормализуется в federation в merge_defaults).
    adapter = (config.get("graph") or {}).get("adapter")
    if adapter is not None and adapter not in GRAPH_ADAPTERS:
        if adapter in LEGACY_GRAPH_ADAPTERS:
            warn(f"{cfg_file}: graph.adapter='{adapter}' устарел → используется "
                 f"'federation' (единственная раскладка; graphify — отдельный MCP-слой)")
        else:
            die(f"{cfg_file}: graph.adapter = '{adapter}' — допустимо: "
                f"{', '.join(sorted(GRAPH_ADAPTERS))}")
    _check_section(cfg_file, "agents", config.get("agents", {}),
                   {"registry_enabled": bool, "heartbeat_interval_ms": int,
                    "max_idle_ms": int, "definitions": list})
    _check_section(cfg_file, "observability", config.get("observability", {}),
                   {"service_name": str, "metrics_enabled": bool,
                    "traces_enabled": bool},
                   {"log_level": LOG_LEVELS})
    if "providers" in config and not isinstance(config["providers"].get("defaults"), dict):
        die(f"{cfg_file}: providers.defaults должно быть объектом")
    if "providers" in config and set(config["providers"]) - {"defaults"}:
        die(f"{cfg_file}: providers содержит неизвестный ключ")

    registry = config.get("namespaces") or {}
    for i, proj in enumerate(config.get("projects", [])):
        if not isinstance(proj, dict):
            die(f"{cfg_file}: projects[{i}] должно быть объектом")
        for fld in ("id", "name"):
            if fld in proj and not isinstance(proj[fld], str):
                die(f"{cfg_file}: projects[{i}].{fld} должно быть строкой")
        pid = proj.get("id")
        if isinstance(pid, str) and not PROJECT_ID_RE.match(pid):
            die(f"{cfg_file}: projects[{i}].id = '{pid}' — недопустимый id; разрешены "
                f"только [A-Za-z0-9._-] (id идёт в scope-маркер памяти и namespace)")
        if "status" in proj and proj["status"] not in PROJECT_STATUSES:
            die(f"{cfg_file}: projects[{i}].status = '{proj['status']}' — допустимо: "
                f"{', '.join(sorted(PROJECT_STATUSES))}")
        if "providers" in proj and not isinstance(proj["providers"], dict):
            die(f"{cfg_file}: projects[{i}].providers должно быть объектом")
        if "namespaces" in proj:
            ns = proj["namespaces"]
            if not isinstance(ns, list) or not all(isinstance(x, str) for x in ns):
                die(f"{cfg_file}: projects[{i}].namespaces должно быть списком строк")
            for n in ns:                       # реестр задан → подсказка на опечатки
                if registry and n not in registry and n not in ("*", "default"):
                    warn(f"{cfg_file}: projects[{i}] ссылается на незарегистрированный "
                         f"namespace '{n}' (нет в секции namespaces)")
        if "docs_folders" in proj:
            df = proj["docs_folders"]
            if not isinstance(df, list):
                die(f"{cfg_file}: projects[{i}].docs_folders должно быть списком")
            for j, it in enumerate(df):
                if isinstance(it, str):
                    continue                   # плоская форма (back-compat)
                if not isinstance(it, dict) or not (it.get("vault") or it.get("id")):
                    die(f"{cfg_file}: projects[{i}].docs_folders[{j}] — строка или "
                        f"объект с 'vault' (опц. repo/visibility/id)")
                vis = it.get("visibility")
                if vis is not None and vis not in ("public", "private"):
                    # forward-compat: не валим конфиг, лишь предупреждаем
                    warn(f"{cfg_file}: projects[{i}].docs_folders[{j}].visibility="
                         f"'{vis}' — ожидалось public|private (взят дефолт)")


# ── дефолты ─────────────────────────────────────────────────────────────────
def merge_defaults(config):
    """Заполняет обязательные дефолты, чтобы вызывающий код не ловил KeyError.
    Не мутирует переданный config (глубокая копия в начале) и не делит вложенные
    объекты ни с входом, ни с module-level дефолтами."""
    config = copy.deepcopy(config)

    mem = config.get("memory") or {}
    mem.setdefault("enabled", True)
    mem.setdefault("role", "standalone")   # дефолт back-compat: существующие узлы не меняют поведение
    mem.setdefault("http_port", MEMORY_HTTP_PORT)
    mem.setdefault("stream_port", MEMORY_STREAM_PORT)
    mem.setdefault("config_path", "config/memory/iii-config.yaml")
    mem.setdefault("data_dir", "./data")
    dg = mem.get("digest") or {}
    dg.setdefault("budget_chars", DIGEST_BUDGET_CHARS)
    dg.setdefault("item_max_chars", DIGEST_ITEM_MAX_CHARS)
    dg.setdefault("shared_max", DIGEST_SHARED_MAX)
    mem["digest"] = dg
    config["memory"] = mem

    gr = config.get("graph") or {}
    gr.setdefault("enabled", True)
    gr.setdefault("adapter", "federation")
    # legacy adapter → федерация (единственная раскладка; движок всегда stdlib)
    if gr["adapter"] in LEGACY_GRAPH_ADAPTERS:
        gr["adapter"] = "federation"
    config["graph"] = gr

    # code_graph: политика код-графа из конфига поверх fallback-дефолтов (top-level ключи).
    # copy.deepcopy(v) — чтобы списки/словари дефолтов не делились с CODE_GRAPH_DEFAULTS.
    cg = config.get("code_graph") or {}
    for k, v in CODE_GRAPH_DEFAULTS.items():
        if k not in cg:
            cg[k] = copy.deepcopy(v)
    config["code_graph"] = cg

    ag = config.get("agents") or {}
    ag.setdefault("registry_enabled", True)
    ag.setdefault("heartbeat_interval_ms", HEARTBEAT_DEFAULT_MS)
    ag.setdefault("max_idle_ms", MAX_IDLE_DEFAULT_MS)
    ag.setdefault("definitions", [])
    config["agents"] = ag

    obs = config.get("observability") or {}
    obs.setdefault("service_name", SERVICE_NAME)
    obs.setdefault("log_level", "info")
    obs.setdefault("metrics_enabled", True)
    obs.setdefault("traces_enabled", False)
    config["observability"] = obs

    config["node"] = config.get("node") or {}
    config["projects"] = config.get("projects") or []
    config["namespaces"] = config.get("namespaces") or {}
    config["integrations"] = config.get("integrations") or {}
    mcp = config.get("mcp") or {}
    # perplexity_web — фолбэк-дефолты ТОЛЬКО если секция задана (иначе не раздуваем конфиг
    # тем, кто perplexity-web не включал; disabled-by-default через PERPLEXITY_WEB_DEFAULTS).
    if isinstance(mcp.get("perplexity_web"), dict):
        pw = mcp["perplexity_web"]
        for k, v in PERPLEXITY_WEB_DEFAULTS.items():
            pw.setdefault(k, v)
    config["mcp"] = mcp
    return config


# ── brain .projects.json → maind (реальная схема brain, не из doc'а) ─────────
def _infer_type(local_path):
    """Best-effort тип проекта по маркерам — единый детектор core. Отсутствующий
    путь → 'unknown' (sentinel maind; core всегда отдаёт реальный id)."""
    if not local_path:
        return "unknown"
    p = Path(os.path.expanduser(local_path))
    if not p.is_dir():
        return "unknown"
    return detect_project_type(p)


def map_brain_project(bp):
    """Запись brain .projects.json → запись проекта maind (надмножество).

    brain-схема: {name, enabled, vault_path, repo (путь к коду!), folders}.
    Поля id/local_path/type из doc'а в brain отсутствуют — синтезируем."""
    name = bp.get("name", "")
    slug = sanitize(name)
    local_path = bp.get("repo")  # в brain repo = локальный путь к коду
    return {
        "id": slug,
        "name": name,
        "local_path": local_path,
        "vault_path": bp.get("vault_path"),
        "repo": None,                       # GitHub slug owner/repo — нет в brain-кэше
        "type": _infer_type(local_path),
        "enabled": bp.get("enabled", True),
        # нормализуем в объектную модель; дефолт видимости — по типу проекта
        "docs_folders": normalize_docs_folders(
            bp.get("folders"), docs_visibility_for(_infer_type(local_path))),
        "memory_scope": f"project:{slug}" if slug else None,
        "agents": [],
        "skills": [],
        "tags": [],
        "namespaces": [],                   # maind-only; brain не источник namespace
        "status": "active",
        "dependencies": [],
    }


def load_brain_projects(path):
    """Читает brain .projects.json (файл или каталог с ним) → список проектов maind."""
    path = Path(os.path.expanduser(path))
    if path.is_dir():
        path = path / ".projects.json"
    if not path.is_file():
        die(f"не найден brain .projects.json: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path}: битый JSON: {e}")
    return [map_brain_project(bp) for bp in data.get("projects", [])]


# ── загрузка с приоритетом ──────────────────────────────────────────────────
def load_config(env):
    """Возвращает (config, source). Приоритет: config.json (корень монорепо;
    linked-worktree config.json (read-only, same Git common-dir only) → legacy
    .maind.json подхватывается тем же резолвером env.default_config) →
    legacy .projects.json (brain, read-only, с предупреждением) → пустой конфиг."""
    primary = env.config_read_path
    if primary.is_file():
        try:
            config = json.loads(primary.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{primary}: битый JSON: {e}")
        validate_config(config, primary)
        return merge_defaults(config), ("linked-worktree-config"
                                        if primary != env.default_config else primary.name)

    legacy = env.root / ".projects.json"
    if legacy.is_file():
        warn("config.json не найден — читаю legacy .projects.json (brain) в режиме "
             "read-only; запустите `maind migrate from-brain .projects.json` для "
             "постоянной конфигурации")
        config = {
            "projects": load_brain_projects(legacy),
            "integrations": {"brain": {"enabled": True, "projects_sync": True,
                                       "sync_direction": "import"}},
        }
        return merge_defaults(config), "brain-fallback"

    return merge_defaults({}), "empty"


# ── обёртка над конфигом ─────────────────────────────────────────────────────
class Config(dict):
    """Лёгкая обёртка узлового конфига. Подкласс dict — старый доступ
    (`cfg["projects"]`, `cfg.get(...)`, `cfg.items()`) работает без изменений.
    Сверху: load/save, происхождение (path/source) и аксессоры секций —
    единая точка, где живёт логика конфига (резолв имени файла, валидация, миграция).

    Использование:
        cfg = Config.load(env)          # читает env.default_config (config.json)
        cfg.projects                    # список проектов (или [])
        cfg.project("corex")            # запись проекта по id или None
        cfg.save(env)                   # atomic-запись обратно
    """

    def __init__(self, data=None, *, source="empty", path=None):
        super().__init__(data or {})
        self.source = source        # происхождение: "config.json"|".maind.json"|"brain-fallback"|"empty"
        self.path = path            # Path, откуда прочитан (None для пустого/fallback)

    @classmethod
    def load(cls, env):
        """Прочитать конфиг узла через общий резолвер (config.json в корне монорепо,
        с legacy-fallback). Возвращает Config с заполненными source/path."""
        data, source = load_config(env)
        path = env.config_read_path if source not in ("brain-fallback", "empty") else None
        return cls(data, source=source, path=path)

    def save(self, env):
        """Atomic-запись конфига обратно (через единственного писателя projects.write_config).
        Перед записью — валидация схемы (Config — подкласс dict, прямые мутации снаружи могли
        нарушить инварианты): не пишем заведомо испорченный state."""
        validate_config(self, str(self.path) if self.path else "in-memory")
        from .projects import write_config
        write_config(env, self)

    # ── аксессоры секций (логику фильтрации/поиска держим здесь) ──────────────
    @property
    def projects(self):
        return list(self.get("projects") or [])

    def project(self, project_id):
        """Запись проекта по id, либо None."""
        for p in self.get("projects") or []:
            if p.get("id") == project_id:
                return p
        return None

    def provider_config_layers(self, project_id):
        return provider_config_layers(self, project_id)

    def resolve_provider_config(self, catalog, project_id, *, project_config=None,
                                operation=None):
        return resolve_provider_config(self, catalog, project_id,
                                       project_config=project_config, operation=operation)

    @property
    def namespaces(self):
        return self.get("namespaces") or {}

    @property
    def integrations(self):
        return self.get("integrations") or {}


def provider_config_layers(config, project_id):
    """Return maind-owned fleet layers without changing the loaded legacy carrier."""
    defaults = (config.get("providers") or {}).get("defaults")
    default_layer = None if defaults is None else ProviderConfigLayer(
        ConfigSource("fleet-defaults", "fleet-defaults:config", "config.json", "/providers/defaults"), defaults)
    matches = []
    for index, project in enumerate(config.get("projects") or []):
        if project.get("id") == project_id and "providers" in project:
            matches.append(ProviderConfigLayer(
                ConfigSource("fleet-project", f"fleet-project:{project_id}", "config.json",
                             f"/projects/{index}/providers"), project["providers"]))
    return default_layer, tuple(matches)


def resolve_provider_config(config, catalog: ProviderConfigCatalog | None, project_id, *,
                            project_config=None, operation=None) -> ResolvedProviderConfig:
    """Thin maind carrier adapter; fleet/project precedence is owned by core."""
    if catalog is None:
        manifest_path = Path(__file__).resolve().parents[4] / "configs/provider-capabilities.json"
        catalog = provider_config_catalog(load_provider_manifest(manifest_path))
    defaults, projects = provider_config_layers(config, project_id)
    project_layer = None if project_config is None else ProviderConfigLayer(
        ConfigSource("project", f"project:{project_id}", ".swissknife.json", "/providers"), project_config)
    return resolve_shared_provider_config(catalog=catalog, operation=operation, project=project_layer,
                                          fleet_project=projects, fleet_defaults=defaults)


def render_provider_diagnostic(diagnostic):
    return f"provider config: {diagnostic.code} ({diagnostic.path})"
