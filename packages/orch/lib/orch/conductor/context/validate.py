"""Validate: whether a skill name, an instruction path or a skill file may be used (P3.8 checks, moved unchanged): the name
pattern, containment under its roots, no symlink, bounded size and strict UTF-8, the digest of a skill the bridge named,
and the ``selection.json`` sidecar against its schema."""
from __future__ import annotations

import hashlib
from functools import lru_cache
import json
from pathlib import Path
from typing import Iterator

from aicore.util import schema

from orch.conductor.context import (RULES_BYTES, SELECTION_BYTES, SKILL_BYTES, SKILL_NAME, RuleCarrier, RuleSkipped,
                                    SkillRef, snapshot)
from orch.conductor.policies import paths


def path_reason(path: Path) -> str:
    return "symlink" if paths.has_symlink(path) else "outside"


@lru_cache(maxsize=1)
def selection_contract():
    return schema.load_contract(Path(schema.__file__).resolve().parents[3] / "schemas" / "skill-selection" / "v1")


def skill_name_ok(name: str) -> bool:
    return bool(SKILL_NAME.fullmatch(name))


def auto_path(raw) -> tuple:
    """``(path, reason)`` of the SKILL.md the bridge named: an absolute, canonical path of a file called SKILL.md that is
    no symlink; ``path`` is None when it was refused."""
    path = Path(raw) if isinstance(raw, str) and raw else None
    if path is None or not path.is_absolute() or path.name != "SKILL.md":
        return None, "outside"
    try:
        if paths.has_symlink(path):
            raise ValueError("symlink")
        if raw != str(path.resolve(strict=True)):
            raise ValueError("outside")
    except (OSError, RuntimeError, ValueError) as error:
        return None, str(error) if isinstance(error, ValueError) else path_reason(path)
    return path, None


def checked(candidates, names=None) -> Iterator[SkillRef]:
    """Read a bounded candidate once, verifying exactly the bytes used for its body and auto digest. ``names``, when given,
    filters the candidates by name and is looked at again for every candidate."""
    for skill in candidates:
        if names is not None and skill["name"] not in names:
            continue
        skill.update(selection={}, body="")
        path = skill["path"]
        if skill.get("reason") or path is None:
            yield skill
            continue
        try:
            text = paths.read_capped(path, SKILL_BYTES)
            if skill["auto"] and not skill["expected"]:
                raise ValueError("digest_missing")
            if skill["auto"] and hashlib.sha256(text.encode("utf-8")).hexdigest() != skill["expected"]:
                raise ValueError("digest_mismatch")
            skill["body"] = snapshot.body(text)
            sidecar = path.parent / "selection.json"
            if sidecar.exists() or sidecar.is_symlink():
                resolved = paths.contained(sidecar, skill["roots"])
                if resolved is None:
                    raise ValueError(path_reason(sidecar))
                text = paths.read_capped(resolved, SELECTION_BYTES)
                try:
                    selection = json.loads(text)
                except (ValueError, RecursionError):
                    raise ValueError("selection_invalid") from None
                registry, kind = selection_contract()
                if schema.validate(selection, kind, registry):
                    raise ValueError("selection_invalid")
                skill["selection"] = selection
        except (OSError, ValueError) as error:
            skill["reason"] = str(error) if isinstance(error, ValueError) else path_reason(path)
        yield skill


def rule_texts(project: Path, carriers) -> tuple:
    """``(carriers, skipped)``: the instruction files that lie inside the project, are no symlink and read within their
    bounds, as ``RuleCarrier``, and the others as ``RuleSkipped`` with the reason; both in the order of ``carriers``."""
    usable, skipped = [], []
    for carrier in carriers:
        try:
            resolved = paths.contained(carrier, [project])
            if resolved is None:
                raise ValueError(path_reason(carrier))
            text = paths.read_capped(resolved, RULES_BYTES)
        except (OSError, ValueError) as error:
            reason = str(error) if isinstance(error, ValueError) else path_reason(carrier)
            skipped.append(RuleSkipped(carrier, reason))
            continue
        usable.append(RuleCarrier(carrier, text))
    return usable, skipped
