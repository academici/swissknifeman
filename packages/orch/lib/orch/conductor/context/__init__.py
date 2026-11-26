"""What an isolated role still needs to know, as a pipeline of typed steps without ``self``:

1. ``discover``: where the rules and skills of a role are (instruction carriers of a write set, skill files, the answer
   of the skills bridge, the files a piece owns);
2. ``validate``: whether each path and file may be used (name, containment, symlinks, size, encoding, digest, sidecar);
3. ``select``: which of the valid skills the role keeps (``policies.skills.check_skills``);
4. ``snapshot``: the texts the prompt carries (skill bodies);
5. ``rules``: the instruction sections of the repository rules, with what the limit dropped.

The steps return data; ``stages/context.py`` binds them to the conductor and keeps every effect (progress lines, Stop,
the state cache). The types and limits shared by the steps live here.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import NamedTuple, Optional, TypedDict

RULE_HEADING = re.compile(r"^## ([A-Za-z0-9_.-]+)[ \t]*$", re.M)
SKILL_NAME = re.compile(r"[a-z0-9][a-z0-9_:-]*(?:[./][a-z0-9][a-z0-9_:-]*)*")
SKILL_BYTES = 64 * 1024
SELECTION_BYTES = 16 * 1024
RULES_BYTES = 256 * 1024
RULES_CHARS = 4000  # repository rules of a prompt, the sum of the section bodies
WORK_PATHS = 300  # files of the write set that choose the skills


class SkillRef(TypedDict, total=False):
    """A skill of a role on its way through the pipeline: found (``name``, ``id``, ``path``, ``roots``; ``auto`` and the
    ``expected`` SKILL.md digest for a skill the bridge named), then checked (``body``, ``selection`` sidecar), or
    refused (``reason``)."""
    name: str
    id: str
    path: Optional[Path]
    roots: list
    auto: bool
    expected: Optional[str]
    reason: str
    selection: dict
    body: str


class RuleCarrier(NamedTuple):
    """An instruction file (CLAUDE.md or AGENTS.md) that passed its checks, with its text."""
    path: Path
    text: str


class RuleSkipped(NamedTuple):
    """An instruction file left out of the prompt, and why (``symlink``, ``outside``, an encoding or size reason)."""
    path: Path
    reason: str


class RulesBlock(TypedDict):
    """``text`` is the "Repository rules" body; ``included`` and ``omitted`` list ``{name, path}`` of the wanted sections
    it holds and those the size limit dropped (an empty section is neither)."""
    text: str
    included: list
    omitted: list


class BridgeAnswer(NamedTuple):
    """The answer of the skills bridge: ``chosen`` is its document, or ``failure`` says what went wrong (the text that
    follows ``skills bridge for <role>`` in the Stop)."""
    chosen: Optional[dict]
    failure: str = ""


class WorkPaths(NamedTuple):
    """The paths that choose the skills (the owned files, cut, then the patterns) and how many files the patterns own."""
    paths: list
    owned: int


class Selection(NamedTuple):
    """The verdict of ``policies.skills.check_skills``: the kept ``names``, the full ``rows`` left out (with their detail),
    those rows as ``{id, reason}`` in ``excluded``, and the first declared ``conflict`` pair, if any."""
    names: list
    rows: list
    excluded: list
    conflict: Optional[tuple]


class SkillTexts(NamedTuple):
    """The checked skills of a role: ``texts`` (name to body) of the usable ones, ``rejected`` the refused ones."""
    texts: dict
    rejected: list
