"""Namespace isolation for cross-project links.

Projects opt in through `.maind.json` `namespaces`. A cross-project edge is
allowed only when both registered projects share a namespace; wildcard `*`
matches every namespace. Missing namespaces retain the `default` legacy
behavior, and unregistered targets remain linkable.

Isolation is enforced while deriving edges, so stored graphs contain no
cross-namespace bridges. Memory uses the matching `project:`, `ns:`, and
`global` scopes."""

from .constants import GLOBAL_SCOPE, NS_SCOPE_PREFIX

DEFAULT_NS = "default"
WILDCARD = "*"


def namespaces_of(project):
    """Return project namespaces; missing or empty means {"default"}."""
    ns = project.get("namespaces")
    return set(ns) if ns else {DEFAULT_NS}


def shares(a, b):
    """Whether two project records share a namespace, including wildcard `*`."""
    na, nb = namespaces_of(a), namespaces_of(b)
    return WILDCARD in na or WILDCARD in nb or bool(na & nb)


def find(config, project_id):
    """Return a project record by ID without importing projects.py."""
    for p in config.get("projects") or []:
        if p.get("id") == project_id:
            return p
    return None


def link_allowed(src_project, dst_id, config):
    """Allow a cross-edge for unregistered targets or shared namespaces."""
    dst = find(config, dst_id)
    return True if dst is None else shares(src_project, dst)


def in_namespace(project, namespace):
    """Whether a project belongs to a namespace, including wildcard `*`."""
    ns = namespaces_of(project)
    return WILDCARD in ns or namespace in ns


# ── Memory scopes aligned with graph namespaces ──────────────────────────────
def private_scope(project):
    """Return configured private memory scope or project:<id>."""
    return project.get("memory_scope") or f"project:{project['id']}"


def group_scopes(project):
    """Return shared link-reference scopes; wildcard projects use global."""
    out = []
    for n in sorted(namespaces_of(project)):
        scope = GLOBAL_SCOPE if n == WILDCARD else f"{NS_SCOPE_PREFIX}{n}"
        if scope not in out:
            out.append(scope)
    return out


def recall_scopes(project):
    """Return deduplicated private, group, and global recall scopes."""
    out = [private_scope(project)]
    for s in group_scopes(project) + [GLOBAL_SCOPE]:
        if s not in out:
            out.append(s)
    return out
