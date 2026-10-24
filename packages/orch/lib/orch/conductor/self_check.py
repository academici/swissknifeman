"""The self-check of an executor report the conductor settles without a model round: a command an acceptance check of
the piece already runs is left to that check, the others the conductor runs itself (``SELF_CHECK_COVERED``)."""
from __future__ import annotations

from pathlib import Path
import re
import shlex

from orch.conductor import checks

COMPLETION = ("done", "done_with_deviations", "done_pending_checks")


def gap(item, report: dict) -> list:
    """What a completion report leaves out of the run's ``checks.self_check``: the commands it does not list, and the
    red ones it lists without a deviation that names the failure. Empty when there is nothing to ask again."""
    commands = list(item.options["checks"].get("self_check") or [])
    if not commands or item.options["checks"]["executor_runs_checks"] or report.get("status") not in COMPLETION:
        return []
    claims = {str(row["cmd"]).strip(): row["exit"] for row in report.get("self_check") or [] if isinstance(row, dict)}
    deviations = [str(issue.get("text") or "") for issue in report.get("open_issues") or [] if issue.get("kind") == "deviation"]
    found = {command: claimed(command, claims) for command in commands}
    # a deviation that names the command is an honest account of it, shown in a row or not (a sandbox that cannot run it)
    named = {command for command in commands if any(command in text for text in deviations)}
    return [command for command in commands if command not in named
            and (found[command] is None or (found[command] != 0 and not deviations))]


def claimed(command: str, claims: dict):
    """The exit a report gives for ``command``: its own row, or a row that is the command followed only by a note in
    parentheses (``ruff check . (run as /snap/bin/ruff)``); None when the report does not show it."""
    if command in claims:
        return claims[command]
    for text, code in claims.items():
        rest = text[len(command):].strip() if text.startswith(command + " ") else ""
        if rest.startswith("(") and rest.endswith(")"):
            return code
    return None


ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")  # ``NAME=value`` ahead of a command: its environment, not the command


def segments(command: str) -> list:
    """The words of each simple command of a ``&&``/``;`` chain (``cd x && y``: two); a text shlex cannot split is one."""
    try:
        words = shlex.split(command)
    except ValueError:
        return [command.split()]
    found, current = [], []
    for word in words:
        if word in ("&&", ";"):
            found.append(current)
            current = []
        else:
            current.append(word)
    return [part for part in found + [current] if part]


def covered_by_checks(input_doc: dict, options: dict, command: str) -> bool:
    """Whether an acceptance check of the piece runs ``command`` on the same tree: one of its simple commands, run from the
    project root, is the command itself, perhaps after variable assignments or with more arguments (``affected-tests.py
    --run --base main`` runs ``affected-tests.py --run``). The conductor's own run of it is then the evidence."""
    wanted = segments(command)
    if len(wanted) != 1:
        return False
    for check in ((input_doc or {}).get("acceptance") or {}).get("checks") or []:
        if (not check.get("cmd") or check.get("cwd", ".") not in (".", "./")
                or check.get("kind") not in options.get("kinds", ()) or check.get("cadence", "item") != "item"):
            continue
        for part in segments(check["cmd"]):
            if part[0] == "cd":  # what follows runs in another folder
                break
            while part and ASSIGNMENT.match(part[0]):
                part = part[1:]
            if part[:len(wanted[0])] == wanted[0]:
                return True
    return False


def run(project: Path, folder: Path, commands: list, timeout_s: int) -> dict:
    """``{command: (exit, tail)}``: the self-check commands no acceptance check covers, run by the conductor from the
    project root as it runs a check; one log per command in ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    found = {}
    for number, command in enumerate(commands, 1):
        log = folder / f"{number}.log"
        try:
            with open(log, "wb") as out:
                code = checks._run_command(["bash", "-c", command], cwd=project, out=out, timeout_s=timeout_s, warn_s=0,
                                           env=checks.check_env(project))
        except OSError as error:
            code = 127
            log.write_text(str(error), encoding="utf-8")
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-checks.TAIL_LINES:]
        found[command] = (code, "\n".join(tail))
    return found
