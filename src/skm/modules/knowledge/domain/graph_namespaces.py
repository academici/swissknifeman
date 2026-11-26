"""Graph namespace matching for projects in the same workspace."""


def shares(a: frozenset[str], b: frozenset[str]) -> bool:
    return "*" in a or "*" in b or not a.isdisjoint(b)


def link_allowed(
    src_project_namespaces: frozenset[str], dst_project_namespaces: frozenset[str] | None
) -> bool:
    return dst_project_namespaces is None or shares(src_project_namespaces, dst_project_namespaces)
