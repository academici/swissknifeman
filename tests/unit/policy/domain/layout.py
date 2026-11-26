"""One attempt layout shared by the policy domain tests: roots, observed path facts, an empty authority and
a configuration reader holding the catalog defaults of the ``policy`` section."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

from skm.kernel.json_types import JsonValue
from skm.modules.policy.domain.operations import PathOrigin, StaticPathFacts, TaskAuthority
from skm.modules.policy.domain.paths import ScopeRoots

WT = "/w/attempt/repo"
HOME = "/home/dev"
ROOTS = ScopeRoots(
    worktrees={"main": WT},
    materials="/w/attempt/materials",
    tmp="/w/attempt/tmp",
    home=HOME,
    safe_dirs=("/opt/cache",),
    protected=("/var/lib/skm", "/w"),
    remote_hosts=frozenset({"github.com"}),
)
TRACKED = frozenset({PathOrigin.TRACKED})
OWN = frozenset({PathOrigin.OWN_UNTRACKED})
FOREIGN = frozenset({PathOrigin.FOREIGN_UNTRACKED})
FACTS = StaticPathFacts(
    origins_by_path={
        f"{WT}/src/app.py": TRACKED,
        f"{WT}/src/util.py": TRACKED,
        f"{WT}/README.md": TRACKED,
        f"{WT}/build/out.o": OWN,
        f"{WT}/build/tmp.log": frozenset({PathOrigin.IGNORED}),
        f"{WT}/notes.txt": FOREIGN,
        f"{WT}/.git": frozenset({PathOrigin.GIT_INTERNAL}),
        f"{WT}/.git/config": frozenset({PathOrigin.GIT_INTERNAL}),
        f"{WT}/gone.txt": frozenset({PathOrigin.ABSENT}),
    },
    links={f"{WT}/escape": "/etc", f"{WT}/state": "/var/lib/skm"},
    home=HOME,
)
EMPTY = TaskAuthority(write_scope=None, delete_scope=(), operations=frozenset(), capabilities=frozenset())


@cache
def catalog_defaults() -> Mapping[str, JsonValue]:
    """``policy.*`` key → default, read from the section schema ``urn:skm:settings:policy:v1``."""
    found: dict[str, JsonValue] = {}

    def walk(node: Mapping[str, Any], prefix: str) -> None:
        for name, child in node.get("properties", {}).items():
            if "default" in child:
                found[f"{prefix}.{name}"] = child["default"]
            elif child.get("type") == "object":
                walk(child, f"{prefix}.{name}")

    schema = resources.files("skm.schemas").joinpath("settings", "policy.v1.json").read_text("utf-8")
    walk(json.loads(schema), "policy")
    return found


@dataclass(frozen=True)
class CatalogConfig:
    """A ``ConfigReader`` of composition: catalog defaults with ``overrides`` on top."""

    overrides: Mapping[str, JsonValue] = field(default_factory=dict[str, JsonValue])

    def get(self, key: str) -> JsonValue | None:
        return self.overrides[key] if key in self.overrides else catalog_defaults().get(key)
