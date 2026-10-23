"""The working tree as a role sees it: the changed paths outside the conductor reports, a mark of the tree a failed
attempt can be compared with and the section that turns a repeat of a writing role into a continuation."""
from __future__ import annotations

from aicore.util.digest import sha256_hex

from orch.conductor import checks as checks_mod, scope as scopes
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import REPORTS


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
