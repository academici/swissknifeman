"""Read dependency facts from inert manifest text; malformed manifests prove no facts."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from typing import cast


def _object(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def project_deps(manifest_texts: Mapping[str, str]) -> frozenset[str]:
    result: set[str] = set()

    def pip(requirement: object) -> None:
        match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", str(requirement))
        if match:
            result.add("pip:" + re.sub(r"[-_.]+", "-", match[1]).lower())

    for path, text in manifest_texts.items():
        name = path.rsplit("/", 1)[-1]
        try:
            raw = _object(tomllib.loads(text) if name == "pyproject.toml" else json.loads(text))
        except (ValueError, TypeError):
            continue
        if name == "pyproject.toml":
            project = _object(raw.get("project"))
            groups = [project.get("dependencies"), _object(raw.get("build-system")).get("requires")]
            groups.extend(_object(project.get("optional-dependencies")).values())
            for group in groups:
                if isinstance(group, list):
                    for requirement in cast("list[object]", group):
                        pip(requirement)
            poetry = _object(_object(raw.get("tool")).get("poetry"))
            poetry_groups = [poetry, *(_object(g) for g in _object(poetry.get("group")).values())]
            for group in poetry_groups:
                for key in (*_object(group.get("dependencies")), *_object(group.get("dev-dependencies"))):
                    if key != "python":
                        pip(key)
        elif name in {"package.json", "composer.json"}:
            keys = (
                ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
                if name == "package.json"
                else ("require", "require-dev")
            )
            for key in keys:
                for dependency in _object(raw.get(key)):
                    if name == "package.json":
                        result.add(f"npm:{dependency}")
                    elif "/" in dependency:
                        result.add(f"composer:{dependency}")
    return frozenset(result)
