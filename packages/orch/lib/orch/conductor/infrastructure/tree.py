"""The working tree as a role sees it: the changed paths outside the conductor reports, a mark of the tree a failed
attempt can be compared with and the section that turns a repeat of a writing role into a continuation."""
from __future__ import annotations

from aicore.util.digest import sha256_hex

from orch.conductor import checks as checks_mod, scope as scopes
from orch.conductor import options as opts
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import REPORTS


def runtime_snapshot(owner, item: Item) -> dict:
    patterns = owner._scope_option(item, "runtime_paths", opts.DEFAULT_SCOPE["runtime_paths"])
    return {path: digest for path, digest in checks_mod.dirty_files(owner.project).items()
            if scopes.under(path, patterns)}


def runtime_preexisting(project, found: dict, paths: list) -> tuple:
    before = found.get("runtime_before")
    if not isinstance(before, dict):
        return paths, []
    current = checks_mod.dirty_files(project)
    protected_changed = [path for path in paths if path in before and current.get(path) != before[path]]
    return [path for path in paths if path not in before], protected_changed


def runtime_changed(owner, item: Item, before: dict) -> list:
    current = checks_mod.dirty_files(owner.project) if before else {}
    return [path for path in owner._changed_now(item) if path not in before or current.get(path) != before[path]]


def porcelain_paths(project, limit: int = 500) -> list:
    """Sorted porcelain paths, including both names of renames and all untracked files."""
    try:
        entries = checks_mod.git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    except RuntimeError:
        try:
            checks_mod.git(project, "rev-parse", "--git-dir")
        except RuntimeError:
            return []  # a step can also be journalled outside a git repository
        raise
    found, index = set(), 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        found.add(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            if index < len(entries) and entries[index]:
                found.add(entries[index])
                index += 1
    return sorted(found)[:limit]


def dirty_paths(self) -> list:
    """Changed paths of the tree outside the conductor reports."""
    try:
        return scopes.own(scopes.dirty(self.project), [REPORTS.as_posix()])
    except RuntimeError as error:
        raise Stop("PROJECT_NOT_GIT", str(error)) from None


def tree_mark(self) -> str:
    """HEAD and the content of every changed path of the tree: what a failed attempt of a writing role can be
    compared with (the conductor reports are not the role's)."""
    try:
        head = checks_mod.head(self.project)
    except RuntimeError:  # no commit yet
        head = "-"
    parts = [head]
    for path in dirty_paths(self):
        file = self.project / path
        try:
            parts.append(path + ":" + sha256_hex(file.read_bytes() if file.is_file() else b"-"))
        except OSError:
            parts.append(path + ":?")
    return sha256_hex("\n".join(parts).encode("utf-8"))


def continuation(self, item: Item) -> str:
    """The section that turns a repeat of a writing role into a continuation: what is in the tree, what was checked."""
    head = checks_mod.head(self.project)
    status = checks_mod.git(self.project, "status", "--short").strip() or "(clean)"
    stat = checks_mod.git(self.project, "diff", "--stat", "HEAD").strip() or "(no change in tracked files)"
    closed = [f"{name}: {step.get('verdict', 'done')}" for name, step in (item.state.get("steps") or {}).items()
              if name.startswith("checks.") and step.get("status") == "done"]
    return ("\n\n# The previous attempt failed and left changes\n\n"
            "The previous attempt of this step ended with a failure of the provider, not with an answer. Its changes are "
            "still in the working tree and are yours: read them, keep what is right, finish the rest, and end with the "
            "closed block the contract asks for. Do not discard them and do not start over.\n\n"
            f"Base commit: {head}\n\n```\n$ git status --short\n{status}\n\n$ git diff --stat HEAD\n{stat}\n```\n\n"
            f"Checks closed before this step: {', '.join(closed) if closed else 'none'}.\n")
