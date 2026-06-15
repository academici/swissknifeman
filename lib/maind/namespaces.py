"""Namespaces: изоляция межпроектных связей внутри групп проектов.

Проект объявляет принадлежность к namespace полем `namespaces: ["axioma", ...]` в
.maind.json (maind-only поле, как `tags`). Межпроектное ребро A↔B строится, ТОЛЬКО
если A и B делят хотя бы один namespace. Связи внутри namespace работают как раньше,
между namespace — изолированы.

Семантика:
- нет поля / пусто  → неявный namespace `default` (= прежнее поведение: всё связано);
- `["*"]` (wildcard) → связывается со ВСЕМИ namespace (escape для общей инфраструктуры:
  azguard, docvault, botkit, erp-sdk, swissknifeman);
- незарегистрированный таргет (нет записи в projects[], напр. doc-алиас getchat) —
  связь сохраняется: namespace внешнего узла неизвестен, не режем.

Связи изолируются в ТОЧКЕ создания ребра (derive.*), поэтому сторы проектов физически
не содержат меж-namespace мостов и всё ниже (union, index, query, seed) изолируется само.
rebuild_index держит дублирующий гейт как defense-in-depth."""

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
