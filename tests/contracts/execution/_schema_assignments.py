"""Codegen assignment comparison for execution contract tests."""

import json
from typing import Any, cast


def codegen_collisions(documents: dict[str, dict[str, Any]]) -> list[str]:
    """Compare root wire forms assigned to each Python/TypeScript symbol, including aliases."""
    assignments: dict[tuple[str, str, str], tuple[str, str]] = {}
    conflicts: list[str] = []
    annotations = {"$schema", "$id", "title", "description", "x-skm-codegen", "x-skm"}
    for urn, document in documents.items():
        form = document
        seen: set[str] = set()
        while "$ref" in form:
            reference = str(form["$ref"])
            if reference in seen:
                break
            seen.add(reference)
            target, _, fragment = reference.partition("#")
            form = documents[target or urn]
            for key in fragment.split("/")[1:]:
                form = form[key.replace("~1", "/").replace("~0", "~")]
        shape = json.dumps(
            {key: value for key, value in form.items() if key not in annotations}, sort_keys=True
        )
        metadata = document.get("x-skm-codegen", {})
        for language, namespace, symbol in (("python", "module", "class"), ("typescript", "file", "name")):
            target = metadata.get(language)
            if not isinstance(target, dict):
                continue
            binding = cast(dict[str, str], target)
            assignment = (language, binding[namespace], binding[symbol])
            previous = assignments.get(assignment)
            if previous is not None and previous[1] != shape:
                conflicts.append(f"{assignment}: {previous[0]} vs {urn}")
            else:
                assignments[assignment] = (urn, shape)
    return conflicts
