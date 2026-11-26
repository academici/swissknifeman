"""Shared repository and monorepo root discovery helpers. stdlib-only."""
import os
import shutil
from pathlib import Path


def find_repo_root(start):
    """Return the nearest ancestor containing ``.git``, or ``None``."""
    start = Path(start)
    for cand in (start, *start.parents):
        if (cand / ".git").exists():
            return cand
    return None


def find_monorepo_root(start, *, markers=("packages",)):
    """Return the nearest ancestor containing a configured monorepo marker."""
    start = Path(start)
    for cand in (start, *start.parents):
        if any((cand / m).is_dir() for m in markers):
            return cand
    return None


def resolve_plan_dir(repo_root, plan_id):
    """Return a live or archived plan directory, otherwise raise ``FileNotFoundError``.

    The plans folder comes from the project marker (``aicore.workspace.resolve_plans_store``): ``<repo>/plans`` without
    a marker or with a legacy store, the portable workspace folder otherwise. A store that cannot be resolved raises
    ``aicore.workspace.WorkspaceError``."""
    from aicore.workspace import resolve_plans_store
    repo_root = Path(repo_root)
    plans_root = resolve_plans_store(repo_root).plans_root
    live = plans_root / plan_id
    archived = plans_root / "archive" / plan_id
    if live.is_dir():
        return live
    if archived.is_dir():
        return archived
    raise FileNotFoundError(
        f"plan {plan_id} not found in any {live}, neither {archived}")


def sibling_bin(pkg, *, env_var=None, monorepo_root=None, use_path=True):
    """Resolve a sibling-package launcher from environment, PATH, or monorepo.

    Return ``None`` when no candidate exists. stdlib-only.
    """
    if env_var:
        override = os.environ.get(env_var)
        if override:
            p = Path(os.path.expanduser(override))
            return p if p.exists() else None
    if use_path:
        which = shutil.which(pkg)
        if which:
            return Path(which)
    if monorepo_root is not None:
        cand = Path(monorepo_root) / "packages" / pkg / "bin" / pkg
        if cand.exists():
            return cand
    return None
