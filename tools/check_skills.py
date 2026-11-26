"""Validate skill manifests under resources/packs.

Every ``skills/*/manifest.toml`` must declare a non-empty ``roles`` list drawn from the
seven-role enum and sit next to a ``SKILL.md`` whose frontmatter parses. A ``requires`` edge
names a skill key. A missing target is an error. A target whose roles share nothing with the
parent is a warning: selection will not expand that dependency for the parent's roles, which
is how a reviewer-only audit stays from leaking an authoring skill. The scan root must already
be a directory; a missing path or a non-directory is an error before any scan.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

from skm.adapters.resources.compiled_pack import blob_content, enclosing_lock_root, read_lock
from skm.kernel.errors import ValidationFailed
from skm.modules.context.domain.request import ROLE_NAMES
from skm.modules.extensions.domain.skill import parse_skill_frontmatter

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "resources" / "packs"


def _roles(raw: object) -> tuple[str, ...] | str:
    """Return parsed roles, or an error string."""
    if not isinstance(raw, list) or not raw:
        return "roles must be a non-empty list"
    names: list[str] = []
    for item in raw:
        if not isinstance(item, str) or item not in ROLE_NAMES:
            return f"role {item!r} is outside the 7-role enum"
        if item in names:
            return f"role {item!r} is duplicated"
        names.append(item)
    return tuple(names)


def _skill_aliases(root: Path) -> tuple[Path | None, dict[Path, str]]:
    scope = enclosing_lock_root(root)
    if scope is None or (current := read_lock(scope)) is None:
        return None, {}
    return scope, {
        scope / path: digest
        for path, digest in current[0].aliases.items()
        if (scope / path).is_relative_to(root)
    }


def _load(root: Path) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for every skill manifest under ``root``."""
    if not root.is_dir():
        reason = "does not exist" if not root.exists() else "is not a directory"
        return [f"scan root {reason}: {root}"], []
    errors: list[str] = []
    warnings: list[str] = []
    root = root.resolve()
    try:
        scope, aliases = _skill_aliases(root)
    except (OSError, ValidationFailed) as error:
        return [f"cannot read compiled pack lock: {error}"], []

    def read(path: Path) -> str:
        if path.is_file() or path not in aliases or scope is None:
            return path.read_text(encoding="utf-8")
        return blob_content(scope, aliases[path]).decode("utf-8")

    roles_by_key: dict[str, tuple[str, ...]] = {}
    requires_by_key: dict[str, tuple[str, ...]] = {}
    manifests = set(root.glob("**/skills/*/manifest.toml"))
    manifests.update(path for path in aliases if path.match("skills/*/manifest.toml"))
    for manifest_path in sorted(manifests):
        label = manifest_path.relative_to(root).as_posix()
        try:
            document = tomllib.loads(read(manifest_path))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, ValidationFailed) as error:
            errors.append(f"{label}: cannot read manifest: {error}")
            continue
        key = document.get("key")
        if not isinstance(key, str) or not key:
            errors.append(f"{label}: missing key")
            continue
        if key in roles_by_key:
            errors.append(f"{label}: duplicate skill key {key}")
            continue
        parsed = _roles(document.get("roles"))
        if isinstance(parsed, str):
            errors.append(f"{label}: {parsed}")
            parsed_roles: tuple[str, ...] = ()
        else:
            parsed_roles = parsed
        skill_md = manifest_path.parent / "SKILL.md"
        if not skill_md.is_file() and skill_md not in aliases:
            errors.append(f"{label}: SKILL.md is missing")
        else:
            try:
                parse_skill_frontmatter(read(skill_md), key=key)
            except (OSError, UnicodeError, ValueError, ValidationFailed) as error:
                errors.append(f"{label}: SKILL.md is invalid: {error}")
        raw_requires = document.get("requires", [])
        if not isinstance(raw_requires, list) or not all(isinstance(item, str) for item in raw_requires):
            errors.append(f"{label}: requires must be a list of skill keys")
            requires: tuple[str, ...] = ()
        else:
            requires = tuple(raw_requires)
        roles_by_key[key] = parsed_roles
        requires_by_key[key] = requires
    more_errors, more_warnings = _requires_findings(roles_by_key, requires_by_key)
    errors.extend(more_errors)
    warnings.extend(more_warnings)
    return errors, warnings


def _requires_findings(
    roles_by_key: Mapping[str, tuple[str, ...]], requires_by_key: Mapping[str, tuple[str, ...]]
) -> tuple[list[str], list[str]]:
    """A missing ``requires`` target is an error; a disjoint role set is a warning."""
    errors: list[str] = []
    warnings: list[str] = []
    for key, requires in sorted(requires_by_key.items()):
        parent = set(roles_by_key.get(key, ()))
        for required in requires:
            child = roles_by_key.get(required)
            if child is None:
                errors.append(f"{key}: requires unknown skill {required}")
                continue
            if parent and child and not parent.intersection(child):
                warnings.append(
                    f"{key}: requires {required}, whose roles {list(child)} share none of {sorted(parent)}"
                )
    return errors, warnings


def check_skills(root: Path | None = None) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for skill manifests under ``root`` (repo packs by default)."""
    return _load(PACKS if root is None else root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=PACKS,
        help="packs directory to scan (default: resources/packs)",
    )
    args = parser.parse_args(argv)
    errors, warnings = check_skills(args.root)
    for warning in warnings:
        sys.stderr.write(f"check_skills: warning: {warning}\n")
    if errors:
        sys.stderr.write(f"check_skills: {len(errors)} error(s)\n")
        sys.stderr.write("\n".join(errors) + "\n")
        return 1
    print(f"check_skills: clean ({args.root}); {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
