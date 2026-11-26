"""Discover: where the rules and skills of a role are: the instruction files on the way to a write set, the skill folders
of the project, the answer of the skills bridge and the files a piece owns. Nothing here reads a file's text."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from orch.conductor import scope as scopes
from orch.conductor.context import WORK_PATHS, BridgeAnswer, SkillRef, WorkPaths, validate
from orch.conductor.policies import paths

CARRIER_NAMES = ("CLAUDE.md", "AGENTS.md")  # the first that exists in a folder carries its rules
SKILL_FOLDERS = (".claude/skills", ".agents/skills")  # searched in this order


def rule_carriers(project: Path, write_set) -> list:
    """The instruction file (CLAUDE.md, else AGENTS.md) of the project root and of every folder on the way to a path of
    ``write_set``, shallowest first; a folder without one adds nothing. Patterns are walked only up to their first
    wildcard, and only inside the project."""
    folders = {Path(".")}
    for pattern in write_set or []:
        fixed = []
        for part in str(pattern).split("/")[:-1]:
            if any(mark in part for mark in "*?[") or part in ("..", "") or part.startswith("/"):
                break  # only folders inside the project are walked
            fixed.append(part)
        for depth in range(1, len(fixed) + 1):
            folders.add(Path(*fixed[:depth]))
    carriers = []
    for folder in sorted(folders, key=lambda path: (len(path.parts), str(path))):
        carrier = next((project / folder / name for name in CARRIER_NAMES
                        if (project / folder / name).exists() or (project / folder / name).is_symlink()), None)
        if carrier is not None:
            carriers.append(carrier)
    return carriers


def _agents_skills_json_map(project: Path) -> dict[str, tuple[Path, Path]]:
    """Map ``skill_name -> (skill_md_path, allowed_root)`` from ``<project>/.agents/skills.json``."""
    cfg_path = project / ".agents" / "skills.json"
    if not cfg_path.is_file() or cfg_path.is_symlink():
        return {}
    try:
        entries = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(entries, list):
        return {}
    mapping: dict[str, tuple[Path, Path]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_root = entry.get("path")
        include_only = entry.get("include_only")
        if not isinstance(raw_root, str) or not raw_root:
            continue
        root = Path(raw_root).expanduser()
        if not root.is_absolute():
            root = project / root
        if isinstance(include_only, list):
            for sname in include_only:
                if isinstance(sname, str) and sname and sname not in mapping:
                    mapping[sname] = (root / sname / "SKILL.md", root)
    return mapping


def skill_candidates(project: Path, names) -> list:
    """The skills of a list of names: the SKILL.md of each in the skill folders of the project (``.claude`` before
    ``.agents``, then ``.agents/skills.json``). A name that breaks the pattern, or a file that leaves its folder, carries a ``reason``."""
    found = []
    json_map = None
    for name in names:
        skill = SkillRef(name=name, id=name, path=None, auto=False)
        if not validate.skill_name_ok(name):  # defence for callers with already-merged options
            found.append(dict(skill, reason="outside"))
            continue
        matched = False
        for folder in SKILL_FOLDERS:
            root = project / folder
            path = root / name / "SKILL.md"
            if not path.exists() and not paths.has_symlink(path):
                continue
            resolved = paths.contained(path, [root])
            if resolved is None:
                skill["reason"] = validate.path_reason(path)
            else:
                skill.update(path=resolved, roots=[root])
            matched = True
            break
        if not matched:
            if json_map is None:
                json_map = _agents_skills_json_map(project)
            if name in json_map:
                path, root = json_map[name]
                if path.exists() or paths.has_symlink(path):
                    resolved = paths.contained(path, [root])
                    if resolved is None:
                        skill["reason"] = validate.path_reason(path)
                    else:
                        skill.update(path=resolved, roots=[root])
        found.append(skill)
    return found


def auto_candidates(rows) -> list:
    """The skills the bridge named (rows of its answer): the bridge id (else the name), the file it named and the digest it
    expects. A path that is not an absolute, canonical, symlink-free SKILL.md carries a ``reason``."""
    found = []
    for row in rows:
        skill = SkillRef(name=row["name"], id=row.get("id") or row["name"], path=None, auto=True,
                         expected=row.get("skill_md_sha256"))
        path, reason = validate.auto_path(row.get("path"))
        if reason:
            skill["reason"] = reason
        else:
            skill.update(path=path, roots=[path.parent])
        found.append(skill)
    return found


def bridge_selection(argv, cwd, env, timeout: int = 120) -> BridgeAnswer:
    """Run the skills bridge (``argv`` answers ``--select`` with a JSON document) as a process, orch imports no other
    module. ``failure`` is set when it could not run, answered no JSON, exited non-zero or sent no ``skills`` list."""
    try:
        done = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, env=env, timeout=timeout)
        chosen = json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return BridgeAnswer(None, f": {error.__class__.__name__}: {error}")
    if done.returncode != 0 or not isinstance(chosen.get("skills"), list):
        return BridgeAnswer(None, f" exited {done.returncode}: {done.stderr.strip()[:300]}")
    return BridgeAnswer(chosen)


def work_paths(project: Path, patterns) -> WorkPaths:
    """The paths a piece will touch, for the triggers of the skill selection: the files the write set patterns own in the
    repository (``git ls-files``; the first ``WORK_PATHS``) plus the patterns themselves, so a file the piece creates still
    counts. ``owned`` is the number of files the patterns own before the cut."""
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=str(project), capture_output=True, text=True,
                                 timeout=30).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        tracked = []
    owned = [path for path in tracked if any(scopes.matches(path, pattern) for pattern in patterns)]
    return WorkPaths(list(dict.fromkeys(owned[:WORK_PATHS] + list(patterns))), len(owned))
