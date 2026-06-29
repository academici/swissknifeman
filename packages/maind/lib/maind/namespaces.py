"""Namespaces: изоляция межпроектных связей внутри групп проектов.

Проект объявляет принадлежность к namespace полем `namespaces: ["axioma", ...]` в
.maind.json (maind-only поле, как `tags`). Межпроектное ребро A↔B строится, ТОЛЬКО
если A и B делят хотя бы один namespace. Связи внутри namespace работают как раньше,
между namespace — изолированы.

Семантика:
- нет поля / пусто  → неявный namespace `default` (= прежнее поведение: всё связано);
- `["*"]` (wildcard) → связывается со ВСЕМИ namespace (escape для общей инфраструктуры:
  azguard, vaulter, botkit, erp-sdk, swissknifeman);
- незарегистрированный таргет (нет записи в projects[], напр. doc-алиас getchat) —
  связь сохраняется: namespace внешнего узла неизвестен, не режем.

Связи изолируются в ТОЧКЕ создания ребра (derive.*), поэтому сторы проектов физически
не содержат меж-namespace мостов и всё ниже (union, index, query, seed) изолируется само.
rebuild_index держит дублирующий гейт как defense-in-depth.

Память следует той же модели через scope-бакеты (см. constants): приватный `project:<id>`,
общий на группу `ns:<имя>`, экосистемный `global` (wildcard '*' → global)."""

from .constants import GLOBAL_SCOPE, NS_SCOPE_PREFIX

DEFAULT_NS = "default"
WILDCARD = "*"


def namespaces_of(project):
    """Множество namespace проекта. Нет поля / пусто → {"default"}."""
    ns = project.get("namespaces")
    return set(ns) if ns else {DEFAULT_NS}


def shares(a, b):
    """Делят ли две записи проектов namespace (с учётом wildcard '*')."""
    na, nb = namespaces_of(a), namespaces_of(b)
    return WILDCARD in na or WILDCARD in nb or bool(na & nb)


def find(config, project_id):
    """Запись проекта по id или None (без импорта projects.py — избегаем связности)."""
    for p in config.get("projects") or []:
        if p.get("id") == project_id:
            return p
    return None


def link_allowed(src_project, dst_id, config):
    """Разрешено ли cross-ребро src_project → dst_id. Незарегистрированный dst → True
    (внешний узел, namespace неизвестен). Иначе — делят ли стороны namespace."""
    dst = find(config, dst_id)
    return True if dst is None else shares(src_project, dst)


def in_namespace(project, namespace):
    """Входит ли проект в namespace (учитывая wildcard '*' у проекта)."""
    ns = namespaces_of(project)
    return WILDCARD in ns or namespace in ns


# ── память: scope-бакеты по namespace'ам (паритет с графом) ──────────────────
def private_scope(project):
    """Приватный бакет памяти проекта: memory_scope из конфига или project:<id>."""
    return project.get("memory_scope") or f"project:{project['id']}"


def group_scopes(project):
    """Общие бакеты, в которые проект кладёт cross-ref о связях: ns:<имя> на каждый
    namespace (wildcard '*' → global, т.к. инфраструктура видна всей экосистеме)."""
    out = []
    for n in sorted(namespaces_of(project)):
        scope = GLOBAL_SCOPE if n == WILDCARD else f"{NS_SCOPE_PREFIX}{n}"
        if scope not in out:
            out.append(scope)
    return out


def recall_scopes(project):
    """Бакеты, релевантные проекту при recall: приватный + общие группы + global
    (global всегда — чтобы видеть инфраструктуру/экосистемные факты). Без дублей."""
    out = [private_scope(project)]
    for s in group_scopes(project) + [GLOBAL_SCOPE]:
        if s not in out:
            out.append(s)
    return out
