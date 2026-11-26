"""Preserve the files of repeated steps before another attempt writes to their original paths."""
from __future__ import annotations

from pathlib import Path
import shutil


ATTEMPT_DIRS = ("streams", "reports", "prompts", "checks")


def archive(directory: Path, key: str, kept: list[str], number: int, *, copy_files: bool = False) -> list[str]:
    moved = []
    for folder in ATTEMPT_DIRS:
        for path in sorted((directory / folder).glob("*")) if (directory / folder).is_dir() else []:
            name = path.name
            # The logs of step ``checks.N`` are the folder ``checks/N`` (one log per check and the jobs line).
            round_dir = folder == "checks" and key.startswith("checks.") and name == key.split(".", 1)[1]
            if not (round_dir or name == key or name.startswith((key + ".", key + "-"))):
                continue
            if any(name == other or name.startswith((other + ".", other + "-")) for other in kept if len(other) > len(key)):
                continue  # A file of a longer step key that stays (``executor.1-q1`` beside a dropped ``executor.1``).
            target = directory / "attempts" / str(number) / folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if copy_files:
                if path.is_dir():
                    shutil.copytree(path, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(path, target)
            else:
                path.replace(target)
            moved.append(f"{folder}/{name}")
    return moved
