"""Snapshot: the texts a prompt carries for the skills of a role. In P5.4 they are read when the prompt is built (the
behaviour of the module this replaced); a snapshot kept for the run is a later piece."""
from __future__ import annotations

from pathlib import Path

from orch.conductor.context import SKILL_BYTES, SkillTexts
from orch.conductor.policies import paths


def body(text: str) -> str:
    """The text of a ``SKILL.md`` without its front matter; never cut."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        text = text[end + 4:] if end != -1 else text
    return text.strip()


def read_body(path: Path) -> str:
    """The text of the ``SKILL.md`` at ``path``; a file that cannot be read within its bounds is an ``OSError``."""
    try:
        return body(paths.read_capped(path, SKILL_BYTES))
    except ValueError as error:
        # The scout fingerprint's legacy reader treats OSError as unavailable. A file that grows or changes
        # encoding between its path check and that read must not crash it; prompt assembly checks it again.
        raise OSError(str(error)) from None


def skill_texts(checked) -> SkillTexts:
    """``texts`` (name to body) of the checked skills that have a file, and the ``rejected`` ones (a ``reason``)."""
    texts, rejected = {}, []
    for skill in checked:
        if skill.get("reason"):
            rejected.append(skill)
        elif skill["path"] is not None:
            texts[skill["name"]] = skill["body"]
    return SkillTexts(texts, rejected)


def skill_files(checked) -> tuple:
    """``(found, rejected)``: ``(name, id, SKILL.md path)`` of each checked skill and the refused ones."""
    found, rejected = [], []
    for skill in checked:
        if skill.get("reason"):
            rejected.append(skill)
        else:
            found.append((skill["name"], skill["id"], skill["path"]))
    return found, rejected
