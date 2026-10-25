"""The part of a prompt (``Block``), how parts are joined and rendered, and the digest of a full prompt's task."""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
from typing import Optional

from aicore.util.digest import sha256_hex

from orch.conductor.prompts.contracts import _PROGRESS


KINDS = ("role_text", "input", "repository_rules", "skill", "skill_names", "context_map", "verification", "run_rules",
         "correction", "answers", "progress", "result_contract", "expected_paths", "candidate", "review_scope", "diff",
         "findings", "instruction", "research", "stub", "resumed", "interrupted", "changed", "authority")
CONDUCTOR = "conductor"
# The blocks of a full executor prompt that carry no task: what a round asks (correction, answers, interrupted, changed)
# and what only names the round (``progress``) or the state of the batch (the ``batch`` run rule). The rest is the task
# and the instructions of the session; their digest says whether a session already holds them (``task_digest``).
ROUND_KINDS = frozenset({"correction", "answers", "interrupted", "changed", "progress"})
BATCH_ID = "batch"


@dataclass(frozen=True)
class Block:
    """A part of a prompt: what it is (``kind``), where it came from (``origin``: a role file, ``input.json``,
    ``skill:<id>``, ``scout-cache:<rel>``, ``conductor``), its exact text with the separator that follows it, and ``id``
    for a block that stands for one named thing (a skill)."""
    kind: str
    origin: str
    text: str
    id: Optional[str] = None


def render(blocks) -> str:
    """The prompt: the texts of the blocks one after the other."""
    return "".join(block.text for block in blocks)


def _join(groups: list) -> list:
    """The blocks of the parts of a prompt: parts are separated by a blank line and the prompt ends with one newline;
    each separator is part of the last block it follows."""
    blocks = []
    for number, group in enumerate(groups):
        group = list(group)
        group[-1] = replace(group[-1], text=group[-1].text.rstrip() + ("\n" if number == len(groups) - 1 else "\n\n"))
        blocks += group
    return blocks


def _then(blocks: list, block: Block) -> None:
    """``block`` after the last of ``blocks``, a blank line between them."""
    blocks[-1] = replace(blocks[-1], text=blocks[-1].text + "\n\n")
    blocks.append(block)


def task_digest(blocks) -> str:
    """sha256 of the canonical JSON of the task and instruction blocks of a full prompt, ``[kind, origin, text]`` each: every
    block but those of ``ROUND_KINDS`` and the batch note. A session that received a full prompt with this digest holds the
    task, the rules and the result contract, so a later round may send the delta prompt (``executor_resumed``); an input
    rebuilt, other skills, stubs or repository rules change the digest and the next round is sent in full."""
    rows = [[block.kind, block.origin, block.text] for block in blocks
            if block.kind not in ROUND_KINDS and block.id != BATCH_ID]
    return sha256_hex(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _fence(text: str, tag: str = "") -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    mark = "`" * max(3, longest + 1)
    return f"{mark}{tag}\n{text.rstrip()}\n{mark}"


def _progress(item: str, step: str) -> Block:
    return Block("progress", CONDUCTOR, _PROGRESS.format(item=item, step=step))
