"""Deterministic acceptance checks of a candidate and their check-evidence files.

Every ``acceptance`` and ``impact`` command check of the execution-input runs as written (``bash -c``, in its
``cwd`` below the project) with the output kept in the ignored runtime folder. Each check gets an ``exec/v1``
check-evidence document in the item's artifact folder (committed), produced by the engine and bound to the candidate
(``HEAD`` and the digest of the dirty tree). A manual procedure cannot run here: its evidence carries the executor's
reported verdict, produced by the executor. ``live`` checks are not run by the conductor.
"""
from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import glob
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional

from aicore.util.io import durable_replace

from orch import contracts
from aicore.util.proc import run as run_with_timeout

RUN_KINDS = ("acceptance", "impact")
TAIL_LINES = 40


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(project: Path, *args: str) -> str:
    done = run_with_timeout(["git", *args], cwd=str(project), capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip() or done.returncode}")
    return done.stdout


def head(project: Path) -> str:
    return git(project, "rev-parse", "HEAD").strip()


def untracked(project: Path) -> list:
    return [line for line in git(project, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if line]


def _under(name: str, folders) -> bool:
    return any(name == folder or name.startswith(folder.rstrip("/") + "/") for folder in folders)


def dirty_digest(project: Path, exclude=()) -> str:
    """sha256 of the tracked changes against HEAD and of the untracked files (names and contents). ``exclude`` names
    folders (relative to the project) that are output of the checks themselves, not part of the candidate."""
    exclude = [folder for folder in exclude if folder and not os.path.isabs(folder)]
    digest = hashlib.sha256(git(project, "diff", "HEAD", "--binary",
                                *(["--", ":/", *[f":(exclude){folder}" for folder in exclude]] if exclude else [])
                                ).encode("utf-8", "surrogateescape"))
    for name in sorted(untracked(project)):
        if _under(name, exclude):
            continue
        digest.update(b"\0" + name.encode("utf-8"))
        try:
            digest.update(b"\0" + (project / name).read_bytes())
        except OSError:
            digest.update(b"\0?")
    return digest.hexdigest()


def diff(project: Path, base: str, limit: int = 200_000, paths: Optional[list] = None) -> str:
    """The diff of the working tree against ``base``, plus the untracked files; cut at ``limit`` characters. ``paths``
    (names relative to the project) limits both to those paths and what lies under them; no path gives no diff."""
    if paths is None:
        text = git(project, "diff", base)
        extra = untracked(project)
    elif not paths:
        return ""
    else:
        text = git(project, "diff", base, "--", *[f":(literal){name}" for name in paths])
        extra = [name for name in untracked(project) if _under(name, paths)]
    if extra:
        text += "\n# untracked files:\n" + "\n".join(f"#   {name}" for name in extra) + "\n"
    if len(text) > limit:
        text = text[:limit] + f"\n# … diff cut at {limit} characters; read the files for the rest\n"
    return text


def subject_of(input_doc: dict) -> str:
    """The qualified reference the evidence proves: the input id without its digest suffix."""
    return str(input_doc.get("input_id", "")).rsplit("@", 1)[0]


def _relative(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path)


POLL_S = 5


# The install roots of the orchestrator the conductor runs from. A check tests the PROJECT, so it must not see them when
# they lead outside it (a frozen or installed copy of the orchestrator would be tested instead of the project's own code).
INSTALL_ROOTS = ("AICORE_ROOT", "SKM_ORCH_ROOT", "PLANNER_ROOT", "PLANNER_PLAN_PY")


def jobs_budget(environ=None) -> int:
    """The upper jobs budget of the checks: the owner's ``SKM_TEST_JOBS`` when it is a positive integer, else the CPUs."""
    try:
        value = int((os.environ if environ is None else environ).get("SKM_TEST_JOBS") or 0)
    except ValueError:
        value = 0
    return value if value >= 1 else max(1, os.cpu_count() or 2)


def check_env(cwd: Path, environ=None, run_env=None, parallel: int = 1) -> dict:
    """The environment of a check command: the conductor's, without install roots that lie outside the project, and with
    unbuffered Python output (a Python test runner writing to the log file shows its progress, so the silence ceiling
    ``check_idle_timeout_s`` measures a hang, not a buffer). ``run_env`` adds the names of the run (``SKM_CHECK_*``).
    ``SKM_TEST_JOBS`` is the share of the jobs budget of one of ``parallel`` checks that run together: the owner's value
    (else the CPUs) divided between them, never more than the owner gave."""
    base = dict(os.environ if environ is None else environ)
    base.setdefault("PYTHONUNBUFFERED", "1")
    project = Path(cwd).resolve()
    for name in INSTALL_ROOTS:
        value = base.get(name)
        if not value:
            continue
        try:
            Path(value).resolve().relative_to(project)
        except ValueError:
            base.pop(name)
    base.update(run_env or {})
    base["SKM_TEST_JOBS"] = str(max(1, jobs_budget(base) // max(1, parallel)))
    return base


# What a fingerprint leaves out of the environment: names that differ between two processes of one run.
VOLATILE_ENV = ("PWD", "OLDPWD", "SHLVL", "_", "COLUMNS", "LINES", "SKM_CHECK_ROUND", "SKM_TEST_JOBS")
FILE_CAP = 64 * 1024 * 1024  # a data file larger than this is not hashed: its content is then not known
_WORD = re.compile(r"(?:[A-Za-z0-9_./+~@%${}-]|\\ )+")  # a word; a backslash-escaped space stays inside it
_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")
_VARIABLE = re.compile(r"\$(\w+)|\$\{(\w+)\}")
MAX_WORDS = 256
MAX_GLOB = 4096  # a glob that matches more files than this is not followed: its inputs are then not known
PATTERN_PROGRAMS = ("find", "fd", "fdfind")  # programs that expand a quoted pattern against the folders they walk
_CASE = re.compile(r"(?<![\w$./-])case\b(.*?)\bin\b(.*?)\besac\b", re.S)


def _digest_file(path: Path, known: Optional[dict]) -> Optional[str]:
    """sha256 of a file (read once while its size and time stay as they were); None when it cannot be read or is huge."""
    info = path.stat()
    key = (str(path), info.st_size, info.st_mtime_ns)
    if known is not None and key in known:
        return known[key]
    value = None
    if info.st_size <= FILE_CAP:
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            value = digest.hexdigest()
        except OSError:
            value = None
    if known is not None:
        known[key] = value
    return value


def _names(text: str, found: list, depth: int = 0, spelled: Optional[set] = None) -> None:
    """Candidate file names of a command line: its words, and every quoted string as a whole (spaces kept) at any depth.
    ``spelled`` collects the names the line spells out as such: not the stretch of a word that a glob character cuts
    (``/dir/`` of ``/dir/*.txt`` is the start of a pattern, not an argument)."""
    for word in _WORD.finditer(text):
        name = word.group(0).replace("\\ ", " ")
        found.append(name)
        if spelled is not None and not (word.start() and text[word.start() - 1] in "*?[]") \
                and not (word.end() < len(text) and text[word.end()] in "*?[]"):
            spelled.add(name)
    if depth < 5:
        for single, double in _QUOTED.findall(text):
            inner = single or double
            if inner:
                found.append(inner)
                if spelled is not None:
                    spelled.add(inner)
                _names(inner, found, depth + 1, spelled)


def _case_patterns(cmd: str) -> bool:
    """Whether the line holds a ``case`` whose branch patterns spell a path, a glob or a variable: the shell matches them as
    text, so what they stand for is not a file the line names."""
    for found in _CASE.finditer(cmd):
        for branch in re.split(r";;&?|;&", found.group(2)):
            if re.search(r"[*?\[/$~{]", branch.split(")", 1)[0]):
                return True
    return False


def _pattern_folder(pattern: str, cwd: Path) -> bool:
    """Whether the folder in front of the first glob character of a quoted pattern exists: the program that expands the
    pattern reads files of it that the line does not name."""
    cut = re.search(r"[*?\[]", pattern)
    folder = os.path.dirname(pattern[:cut.start()]) if cut else ""
    if not folder:
        return False
    try:
        return (cwd / Path(folder).expanduser()).is_dir()
    except (OSError, RuntimeError, ValueError):
        return True


def _ignored(project: Path, path: Path, known: Optional[dict]) -> Optional[bool]:
    """Whether git ignores ``path`` (below the project); None when git cannot say."""
    relative = path.relative_to(project.resolve()).as_posix()
    key = ("ignored", relative)
    if known is not None and key in known:
        return known[key]
    done = run_with_timeout(["git", "check-ignore", "-q", "--", relative], cwd=str(project), capture_output=True, text=True,
                            timeout=60)
    value = True if done.returncode == 0 else False if done.returncode == 1 else None
    if known is not None:
        known[key] = value
    return value


def _close(text: str, start: int) -> int:
    """Index of the bracket that closes ``text[start]`` (``(`` or ``{``), -1 when there is none."""
    opener = text[start]
    closer = ")" if opener == "(" else "}"
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opener:
            depth += 1
        elif text[index] == closer:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _lex(text: str, out: list, mode: str = "top", depth: int = 0) -> bool:
    """Split a shell line into words for ``out``: ``(mode, parts)`` with ``parts`` of ``[kind, value, quoted]``; kind is
    ``lit`` (text), ``var`` (``$NAME``/``${NAME}``), ``subst`` (``$(...)`` or backticks, the inner text is split too) or
    ``opaque`` (any other expansion). A quoted string is split again as a line of its own (``bash -c '...'``): ``mode`` is
    ``top`` for the line itself and its substitutions, ``single`` or ``double`` for the text of such a string. False when
    the line cannot be read (an open quote or bracket, too deep or too long)."""
    if depth > 5 or len(out) > 4096:
        return False
    word, quote, index, size = [], "", 0, len(text)

    def lit(char: str, quoted: bool) -> None:
        if word and word[-1][0] == "lit" and word[-1][2] == quoted:
            word[-1][1] += char
        else:
            word.append(["lit", char, quoted])

    def flush() -> None:
        if word:
            out.append((mode, [list(part) for part in word]))
            word.clear()

    inner_mode = mode if mode != "top" else None  # a substitution is read as the line it stands in

    def quoted_mode(quote: str) -> str:
        return "double" if quote == '"' or mode == "double" else "single"

    while index < size:
        char = text[index]
        if quote == "'":
            if char == "'":
                if not _lex(text[start:index], out, quoted_mode("'"), depth + 1):
                    return False
                quote = ""
            else:
                lit(char, True)
            index += 1
            continue
        if char == "\\" and index + 1 < size:
            if text[index + 1] != "\n":
                lit(text[index + 1], True)
            index += 2
            continue
        if char == "'" and not quote:
            quote, start = "'", index + 1
            index += 1
            continue
        if char == '"':
            if quote:
                if not _lex(text[start:index], out, quoted_mode('"'), depth + 1):
                    return False
                quote = ""
            else:
                quote, start = '"', index + 1
            index += 1
            continue
        quoted = bool(quote)
        if char == "$" and index + 1 < size:
            following = text[index + 1]
            if following == "(" and text.startswith("$((", index):
                end = _close(text, index + 1)
                if end < 0:
                    return False
                word.append(["opaque", text[index:end + 1], quoted])
                index = end + 1
                continue
            if following == "(":
                end = _close(text, index + 1)
                if end < 0:
                    return False
                word.append(["subst", text[index + 2:end], quoted])
                if not _lex(text[index + 2:end], out, inner_mode or "top", depth + 1):
                    return False
                index = end + 1
                continue
            if following == "{":
                end = _close(text, index + 1)
                if end < 0:
                    return False
                name = text[index + 2:end]
                if re.fullmatch(r"[A-Za-z_]\w*", name):
                    word.append(["var", name, quoted])
                else:
                    word.append(["opaque", text[index:end + 1], quoted])
                index = end + 1
                continue
            named = re.match(r"[A-Za-z_]\w*", text[index + 1:])
            if named:
                word.append(["var", named.group(0), quoted])
                index += 1 + len(named.group(0))
                continue
            if following in "?*@#!$-0123456789":
                word.append(["opaque", text[index:index + 2], quoted])
                index += 2
                continue
        if char == "`":
            end = text.find("`", index + 1)
            if end < 0:
                return False
            word.append(["subst", text[index + 1:end], quoted])
            if not _lex(text[index + 1:end], out, inner_mode or "top", depth + 1):
                return False
            index = end + 1
            continue
        if not quote and (char.isspace() or char in ";|&()<>"):
            flush()
        else:
            lit(char, quoted)
        index += 1
    if quote:
        return False
    flush()
    return True


def _braces(chars: list) -> Optional[list]:
    """Bash brace expansion of the unquoted braces of ``chars`` (``(char, active)`` pairs); None when a list is too large
    or a range cannot be read. A brace pair with no comma or range stays as it is."""
    start = None
    for index, (char, active) in enumerate(chars):
        if active and char == "{":
            start = index
        elif active and char == "}" and start is not None:
            inner, depth, cuts = chars[start + 1:index], 0, []
            for place, (letter, live) in enumerate(inner):
                if live and letter == "{":
                    depth += 1
                elif live and letter == "}":
                    depth -= 1
                elif live and letter == "," and depth == 0:
                    cuts.append(place)
            options = []
            if cuts:
                bounds = [-1, *cuts, len(inner)]
                options = [inner[bounds[n] + 1:bounds[n + 1]] for n in range(len(bounds) - 1)]
            else:
                text = "".join(letter for letter, _ in inner)
                found = re.fullmatch(r"(-?\d+)\.\.(-?\d+)(?:\.\.(-?\d+))?", text) or re.fullmatch(
                    r"([A-Za-z])\.\.([A-Za-z])(?:\.\.(-?\d+))?", text)
                if found and all(live for _, live in inner):
                    first, last, step = found.group(1), found.group(2), int(found.group(3) or 1) or 1
                    numeric = first.lstrip("-").isdigit()
                    low, high = (int(first), int(last)) if numeric else (ord(first), ord(last))
                    values = range(low, high + 1, abs(step)) if low <= high else range(low, high - 1, -abs(step))
                    if len(values) > MAX_WORDS:
                        return None
                    options = [[(c, True) for c in (str(v) if numeric else chr(v))] for v in values]
                else:
                    start = None
                    continue
            results = []
            for option in options:
                rest = _braces(chars[:start] + option + chars[index + 1:])
                if rest is None:
                    return None
                results += rest
                if len(results) > MAX_WORDS:
                    return None
            return results
    return [chars]


def _expansions(cmd: str, env: dict, cwd: Path) -> Optional[tuple]:
    """The files a line names through shell expansion that its words do not spell: ``(names, matched)``, the paths that
    unquoted globs (``*`` ``?`` ``[`` and ``**``), brace lists and ``=value`` suffixes of words reach, as bash would
    expand them in ``cwd`` with the variables of ``env``; ``matched`` is the set of the glob matches. None when a path of
    the line cannot be established: a word that mixes a command substitution into a path, or an expansion that holds an
    unset variable or a computed value (in the text of a quoted string: skipped, as it is only guessed to be a command)."""
    words = []
    if not _lex(cmd, words):
        return None
    if _case_patterns(cmd):
        return None  # a case branch is matched by the shell as text, a path in it is not a file the line names
    expander = any(len(parts) == 1 and parts[0][0] == "lit" and os.path.basename(parts[0][1]) in PATTERN_PROGRAMS
                   for _, parts in words)
    names, matched = [], set()
    for mode, parts in words:
        relaxed = mode != "top"
        for kind, value, quoted in parts:
            if kind == "lit" and quoted and re.search(r"[*?\[]", value):
                if expander:
                    return None  # find -name '*.txt': the program, not the shell, expands the pattern
                if not re.search(r"\s", value) and any(_pattern_folder(piece, cwd) for piece in value.split(":")):
                    return None  # a quoted path pattern (or a list of them) into a folder whose files are not known
        literal = any(kind == "lit" and "/" in value for kind, value, _ in parts)
        if any(kind == "subst" for kind, _, _ in parts) and not (mode == "double"):
            unquoted = any(kind == "subst" and not quoted for kind, _, quoted in parts)
            assignment = bool(parts[0][0] == "lit" and not parts[0][2] and re.match(r"[A-Za-z_]\w*=", parts[0][1]))
            if literal or (unquoted and not assignment):
                return None  # a path built by a command: nothing says which file it is
        chars, unknown = [], False
        for kind, value, quoted in parts:
            if kind == "lit":
                chars += [(char, not quoted) for char in value]
            elif kind == "var" and value in env:
                chars += [(char, not quoted) for char in env[value]]
            else:
                unknown = True
        if not any(active and (char in "*?[" or char in "{") for char, active in chars) and not unknown:
            continue
        if unknown:
            if relaxed or not any(kind == "lit" and not quoted and re.search(r"[*?\[{]", value) for kind, value, quoted in parts):
                continue
            return None  # an unset variable or a computed value in a word that globs or expands braces
        variants = [chars]
        cut = next((place for place, (char, active) in enumerate(chars) if active and char == "="), None)
        if cut is not None:
            variants.append(chars[cut + 1:])  # NAME=pattern and --option=pattern: the program may expand the value
        for variant in variants:
            expanded = _braces(variant)
            if expanded is None:
                if relaxed:
                    continue
                return None
            for item in expanded:
                text = "".join(char for char, _ in item)
                if not any(active and char in "*?[" for char, active in item):
                    names.append(text)
                    continue
                if ":" in text and "/" in text:
                    return None  # a PATH-like list of patterns: the program splits it, the shell would glob it as one word
                pattern = "".join(char if active else glob.escape(char) for char, active in item)
                if item and item[0] == ("~", True):
                    pattern = os.path.expanduser(pattern)
                try:
                    found = glob.glob(pattern, root_dir=str(cwd), recursive=True)
                except (OSError, ValueError, re.error):
                    return None
                if len(found) > MAX_GLOB:
                    return None
                for match in found:
                    full = os.path.normpath(os.path.join(str(cwd), match))
                    names.append(full)
                    matched.add(full)
    return names, matched


def _ignored_among(project: Path, paths: list, known: Optional[dict]) -> bool:
    """Fill ``known`` with whether git ignores each of ``paths`` (below the project) in one call; False when git cannot say."""
    root = project.resolve()
    pending = []
    for path in paths:
        try:
            relative = Path(path).resolve().relative_to(root).as_posix()
        except (OSError, RuntimeError, ValueError):
            continue
        if relative != "." and (known is None or ("ignored", relative) not in known):
            pending.append(relative)
    if not pending:
        return True
    done = run_with_timeout(["git", "check-ignore", "-z", "--stdin"], cwd=str(project), input="\0".join(pending) + "\0",
                            capture_output=True, text=True, timeout=60)
    if done.returncode not in (0, 1):
        return False
    hit = {name for name in done.stdout.split("\0") if name}
    if known is not None:
        for relative in pending:
            known[("ignored", relative)] = relative in hit
    return True


def _inputs(cmd: str, env: dict, cwd: Path, project: Path, known: Optional[dict] = None, skip=()) -> Optional[list]:
    """What a command reads that the candidate does not carry, as far as its line and environment show it: the programs
    it names (resolved on the PATH of the check; real path, size and time) and every other existing file it names or that
    an environment value points to (real path and content: fixtures, configuration), outside the project or git-ignored
    inside it. Tracked and untracked files of the project are part of the candidate; ``skip`` folders (the evidence and
    logs of the checks) are output. None when an input cannot be established (a file that cannot be read, a path built from
    an unset variable, an existing folder that the line names or a glob reaches wherever it lies, a line with too many
    names): nothing is then reused. A folder that only the environment holds is context, not a named input."""
    found, root = {}, project.resolve()
    names, spelled = ["bash"], set()
    _names(cmd, names, spelled=spelled)
    names = list(dict.fromkeys(names))
    if len(names) > MAX_WORDS:
        return None
    arguments = set()  # what the line names as an argument (a folder among them is an unknown input), not an env default
    for index, name in enumerate(names):
        given = name in spelled
        if "$" in name and "/" in name:
            for _ in range(3):
                name = _VARIABLE.sub(lambda m: env.get(m.group(1) or m.group(2), m.group(0)), name)
            if _VARIABLE.search(name):
                return None  # a path built from a variable that is not set here
            names[index] = name
        if given:
            arguments.add(name)
    for found_variable in _VARIABLE.finditer(cmd):  # a variable that holds a path (or a list of them) the line passes on
        name = found_variable.group(1) or found_variable.group(2)
        before, after = cmd[:found_variable.start()][-1:], cmd[found_variable.end():][:1]
        if (before and (before in "/." or before.isalnum())) or (after and (after in "/*?[{." or after.isalnum())):
            continue  # part of a longer word or path: the file it names is followed on its own
        if name in env and name not in VOLATILE_ENV and name != "PATH" and not name.endswith("_PY"):
            arguments.update(piece for piece in env[name].split(":") if piece.startswith("/") and "\n" not in piece)
    expanded = _expansions(cmd, env, cwd)
    if expanded is None:
        return None  # a glob, a brace list or a computed path whose files cannot be established
    extra, matched = expanded
    matched = {name: Path(name).resolve() for name in matched}
    carried = [name for name, path in matched.items() if path == root or root in path.parents]
    if carried:
        if not _ignored_among(project, carried, known):
            return None
        # a match the candidate carries (tracked or untracked) is not an input of its own
        extra = [name for name in extra if name not in carried or _ignored(project, matched[name], known)]
    names += extra
    arguments.update(extra)
    names = list(dict.fromkeys(names))
    if len(names) > MAX_WORDS:
        return None
    arguments.update(piece for name in list(arguments) for piece in name.split(":") if piece.startswith("/"))
    names += sorted(arguments - set(names))
    names += [value for key, value in sorted(env.items())
              if key not in VOLATILE_ENV and not key.endswith(("_ROOT", "_PY")) and value.startswith("/")
              and "\n" not in value and ":" not in value][:64]
    reached = set(matched.values())
    skipped = [Path(folder).resolve() for folder in skip]

    def output(path: Path) -> bool:
        return any(path == folder or folder in path.parents for folder in skipped)

    for path in reached:
        if path.is_dir() and not output(path):
            return None  # a folder a glob reaches, in the project or outside: its listing and content are not known
    for name in names:
        try:
            paths = []
            if "/" in name or name.startswith("~"):
                path = Path(name).expanduser()
                paths.append((path if path.is_absolute() else cwd / path).resolve())
            else:
                located = shutil.which(name, path=env.get("PATH"))
                if located:
                    paths.append(Path(located).resolve())
                paths.append((cwd / name).resolve())
            for path in dict.fromkeys(paths):
                if output(path):
                    continue
                if path.is_dir() and name in arguments:
                    return None  # a folder the line names, wherever it lies: its listing and content are not fingerprinted
                inside = path == root or root in path.parents
                if inside and path != root:
                    if not (path.is_file() or path.is_dir()):
                        continue
                    ignored = _ignored(project, path, known)
                    if ignored is None or (ignored and path.is_dir()):
                        return None
                    if not ignored:
                        continue  # tracked or untracked: the candidate carries it
                elif inside or not path.is_file():
                    continue
                if not path.is_file():
                    continue
                if not inside and os.access(path, os.X_OK):
                    info = path.stat()
                    found[str(path)] = ["program", info.st_size, info.st_mtime_ns]
                else:
                    content = _digest_file(path, known)
                    if content is None:
                        return None
                    found[str(path)] = ["file", content]
        except (OSError, RuntimeError, ValueError):
            continue
    return [[name, *found[name]] for name in sorted(found)]


def _external_state(path: Path, known: Optional[dict] = None) -> Optional[str]:
    """The state of a partner root outside the project: HEAD and dirty digest of its repository (read once per
    repository when ``known`` is given). None: not known."""
    try:
        top = Path(git(path if path.is_dir() else path.parent, "rev-parse", "--show-toplevel").strip())
        if known is not None and str(top) in known:
            return known[str(top)]
        state = head(top) + ":" + dirty_digest(top)
    except (OSError, RuntimeError):
        state = None
        top = None
    if known is not None and top is not None:
        known[str(top)] = state
    return state


def fingerprint(check: dict, *, cwd: Path, project: Path, candidate: dict, subject: str, run_id: str, env: dict,
                partners: Optional[dict] = None, inputs: Optional[list] = None) -> Optional[str]:
    """sha256 of everything that makes a green result of a command check the result of the next run: the check as
    written, its working directory, the candidate, the run, the environment (names and values, never stored), the
    ``inputs`` it reads outside the project, the Python of the conductor and the state of the partner roots outside the
    project that the environment points to. None when part of that is not known: nothing is then reused."""
    if inputs is None:
        return None
    root, external = project.resolve(), {}
    for name in sorted(env):
        if not (name.endswith("_ROOT") or name.endswith("_PY")) or not env[name]:
            continue
        path = Path(env[name])
        try:
            inside = path.resolve() == root or root in path.resolve().parents
        except OSError:
            return None
        if inside or not path.exists():
            continue
        state = _external_state(path, partners)
        if state is None:
            return None
        external[name] = state
    document = {"v": 1, "run": run_id, "subject": subject, "candidate": candidate,
                "check": {key: value for key, value in check.items() if key != "cwd"},  # the directory is normalised below
                "cwd": cwd.relative_to(root).as_posix() if cwd != root else ".",
                "env": {name: value for name, value in sorted(env.items()) if name not in VOLATILE_ENV},
                "inputs": inputs, "partners": external,
                "python": platform.python_version(), "platform": sys.platform}
    return hashlib.sha256(json.dumps(document, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _run_command(argv: list, *, cwd: Path, out, timeout_s: int, warn_s: int, on_slow=None, idle_s: int = 0,
                 env: Optional[dict] = None) -> int:
    """Exit code of ``argv``; 124 after ``timeout_s`` or ``idle_s`` seconds without output (0: no ceiling).
    ``on_slow(elapsed, pid)`` every ``warn_s``."""
    # stdin is /dev/null: a check never gets the input of the conductor (a pipe that stays open), so a command that reads it
    # (`docker buildx bake --file -`, `cat`, a prompt) ends at once instead of waiting for ever.
    process = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                               start_new_session=True, env=check_env(cwd) if env is None else env)
    try:
        return _wait_command(process, out=out, timeout_s=timeout_s, warn_s=warn_s, on_slow=on_slow, idle_s=idle_s)
    except BaseException:  # an interrupted run must not leave the check (a test run with workers) running
        _kill_group(process)
        raise
    finally:
        try:  # what the command left in its group (workers of a test runner) dies with it
            os.killpg(process.pid, 9)
        except OSError:
            pass


def _kill_group(process) -> None:
    try:
        os.killpg(process.pid, 15)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, 9)
        except OSError:
            pass
        process.wait()


def stopped(pid: int) -> bool:
    """Whether the process is stopped (SIGSTOP, as an observer does to a check while the disk is freed): its state ``T``."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] in ("T", "t")
    except (OSError, IndexError):
        return False


def _size(out) -> int:
    try:
        return os.fstat(out.fileno()).st_size
    except (OSError, ValueError, AttributeError):
        return -1


def _wait_command(process, *, out, timeout_s: int, warn_s: int, on_slow, idle_s: int = 0) -> int:
    """Wait for a check. The time a stopped check spends stopped is not counted: neither the ``CHECK_SLOW`` beacon nor the
    ceilings ``check_timeout_s`` and ``check_idle_timeout_s`` (silence of the log) run while somebody holds it."""
    began, next_warn, paused, last = time.monotonic(), warn_s, 0.0, time.monotonic()
    size, quiet = _size(out), 0.0  # seconds of silence, without the stopped time
    while True:
        try:
            return process.wait(timeout=POLL_S)
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic()
        held = stopped(process.pid)
        if held:
            paused += now - last
        current = _size(out)
        quiet = 0.0 if current != size else quiet + (0.0 if held else now - last)
        size, last = current, now
        elapsed = now - began - paused
        if timeout_s and elapsed > timeout_s:
            _kill_group(process)
            out.write(f"\n[orch] check timed out after {timeout_s} s\n".encode("utf-8"))
            return 124
        if idle_s and quiet > idle_s:
            _kill_group(process)
            out.write(f"\n[orch] check stopped: no output for {idle_s} s\n".encode("utf-8"))
            return 124
        if warn_s and on_slow is not None and elapsed >= next_warn:
            next_warn += warn_s
            on_slow(elapsed, process.pid)


def run_checks(input_doc: dict, *, project: Path, evidence_dir: Path, log_dir: Path, timeout_s: int,
               evidence_prefix: str, report: dict | None = None, executor: dict | None = None,
               parallel: int = 1, on_result=None, first=(), kinds=RUN_KINDS, cadence=("item", "phase"),
               warn_s: int = 0, on_slow=None, idle_s: int = 0, on_changed=None, previous=(), fail_fast: bool = True,
               reuse: bool = True, run_env: dict | None = None, run_id: str = "", on_budget=None) -> list:
    """Run the checks and write their evidence; one row per acceptance or impact check, in input order.

    A row: ``{id, kind, cmd|procedure, exit|verdict, evidence, log, tail, green}``. ``report`` is the executor's
    stage-report (the source of a manual procedure's verdict); ``executor`` its actor. ``parallel`` command checks run at
    the same time (they must not share files; the order of the rows does not change). ``on_result`` is called with each row
    as soon as its check ends (from a worker thread). ``kinds`` limits the run to these kinds (a quick pass
    runs ``acceptance`` only; the ``impact`` checks wait for the full pass). ``cadence`` limits it to the checks of
    these cadences (a check without one is ``item``; ``phase`` checks run in the closing piece of a phase).
    ``timeout_s`` 0 sets no ceiling on a check; ``idle_s`` stops a check whose log has not grown that long (a hang, not a
    long run); ``on_slow(check_id, elapsed, pid)`` is called every ``warn_s`` seconds of a running check, so a long run is
    reported, not cut. ``on_changed(paths)`` is called once when the checks changed files of the project (their own
    evidence and logs aside): the evidence proves the candidate as it was before them.

    The order is ``schedule``: the checks that were red (``first``) ahead, then the cheapest by the ``seconds`` of the
    rows of earlier rounds (``previous``); with ``fail_fast`` no check is started after one went red (``skipped``,
    ``skip_reason`` ``fail_fast``), and the ``phase`` checks wait for item checks that are all green (else ``skipped``,
    ``skip_reason`` ``phase_after_red``). With ``reuse`` (and a ``run_id``) a command check whose green evidence of the same
    run, candidate, command, directory and fingerprint is there is not run again (``reused``). ``run_env`` is added to the
    environment of every check; ``on_budget`` is called with the jobs budget of each batch of command checks
    (``requested``, ``parallel``, ``effective``).
    """
    project = Path(project)
    root = project.resolve()
    own = [rel for rel in (_relative(Path(folder), project) for folder in (evidence_dir, log_dir))
           if not os.path.isabs(rel)]
    candidate = {"head": head(project), "dirty_digest": dirty_digest(project, exclude=own)}
    reusing = bool(reuse and run_id)
    before = dirty_files(project) if on_changed is not None or reusing else None
    subject = subject_of(input_doc)
    reported = {row["id"]: row for row in (report or {}).get("checks_run", [])}
    wanted = [check for check in (input_doc.get("acceptance") or {}).get("checks", [])
              if check.get("kind") in kinds and check.get("cadence", "item") in cadence]
    batch = {"parallel": 1}  # the checks that run together now; their share of the jobs budget
    partners, digests = {}, {}
    skipped_folders = [Path(evidence_dir), Path(log_dir)]  # the output of the checks themselves: not an input

    def run_one(check: dict) -> dict:
        row = run_check(check)
        if on_result is not None:
            on_result(row)
        return row

    def moved() -> list:
        return [path for path in changed_files(before, dirty_files(project)) if not _under(path, own)]

    def tree_moved() -> bool:
        """Whether the tree or HEAD is no longer the candidate of this round (a check generated, or committed, files)."""
        try:
            return bool(moved()) or head(project) != candidate["head"]
        except RuntimeError:
            return True

    def run_check(check: dict) -> dict:
        check_id = check["id"]
        started = _utc()
        row = {"id": check_id, "kind": check["kind"]}
        doc = {"$schema": "urn:swissknifeman:orch:exec:check-evidence:v1", "contract_version": "exec/v1",
               "evidence_id": f"{evidence_prefix}:{check_id}", "check_id": check_id, "subject": subject,
               "candidate": candidate, "started_at": started}
        target = Path(evidence_dir) / f"{check_id}.json"
        if check.get("cmd"):
            cwd = (project / check.get("cwd", ".")).resolve()
            if cwd != root and root not in cwd.parents:  # ``cwd: ../x`` (or a symlink out) would run it elsewhere
                raise ValueError(f"check {check_id}: cwd {check.get('cwd')!r} leads outside the project ({cwd})")
            print_of = inputs = None
            if reusing:
                lookup_env = check_env(cwd, run_env=run_env)
                inputs = _inputs(check["cmd"], lookup_env, cwd, project, digests, skip=skipped_folders)
                print_of = fingerprint(check, cwd=cwd, project=project, candidate=candidate, subject=subject, run_id=run_id,
                                       env=lookup_env, partners=partners, inputs=inputs)
                found = _reusable(target, check, cwd=cwd, root=root, candidate=candidate, subject=subject,
                                  run_id=run_id, print_of=print_of)
                # the candidate was taken at the start of the round: once a check changed the tree it proves nothing
                if found is not None and not tree_moved():
                    return dict(row, cmd=check["cmd"], exit=0, evidence=_relative(target, project), green=True, reused=True,
                                seconds=0, **found)
            log = Path(log_dir) / f"{check_id}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            begin = time.monotonic()
            with open(log, "wb") as out:
                code = _run_command(["bash", "-c", check["cmd"]], cwd=cwd, out=out, timeout_s=timeout_s, warn_s=warn_s,
                                    idle_s=idle_s, env=check_env(cwd, run_env=run_env, parallel=batch["parallel"]),
                                    on_slow=None if on_slow is None else
                                    (lambda elapsed, pid, check_id=check_id: on_slow(check_id, elapsed, pid)))
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-TAIL_LINES:]
            row.update(cmd=check["cmd"], exit=code, log=str(log), tail="\n".join(tail),
                       seconds=round(time.monotonic() - begin, 1), green=code == 0)
            doc.update(procedure={"cmd": check["cmd"], "cwd": check.get("cwd", ".")}, exit=code,
                       producer={"kind": "engine"})
            # a result is reusable only when nothing it read moved while the check ran
            if print_of is not None and code == 0 and not tree_moved() \
                    and _inputs(check["cmd"], lookup_env, cwd, project, digests, skip=skipped_folders) == inputs:
                doc["environment"] = {"platform": sys.platform, "python": platform.python_version(), "env_digest": print_of}
        else:
            seen = reported.get(check_id)
            verdict = seen.get("verdict") if isinstance(seen, dict) else None
            row.update(procedure=check.get("procedure", ""), verdict=verdict, green=verdict == "pass")
            if verdict is None:  # nothing observed: no evidence is invented
                row["evidence"] = None
                return row
            doc.update(procedure={"procedure": check.get("procedure", "")}, verdict=verdict,
                       observation=f"reported by the executor: {verdict}",
                       producer={"kind": "executor", **({"actor": executor} if executor else {})})
        doc["finished_at"] = _utc()
        issues = [issue for issue in contracts.validate(doc, "check-evidence") if issue.level == "error"]
        if issues:
            raise ValueError(f"check-evidence of {check_id} is outside exec/v1: {issues[0].message}")
        durable_replace(target, (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), mode=0o644)
        row["evidence"] = _relative(target, project)
        return row

    def begin_batch(commands: list) -> int:
        budget = jobs_budget()
        workers = max(1, min(parallel, len(commands), budget))
        batch["parallel"] = workers
        if commands and on_budget is not None:
            on_budget({"requested": budget, "parallel": workers, "effective": max(1, budget // workers)})
        return workers

    rows = _run_round(wanted, run_one, previous=previous, first=first, fail_fast=fail_fast, on_result=on_result,
                      begin=begin_batch)
    if before is not None and on_changed is not None:
        changed = moved()
        if changed:
            on_changed(changed)
    return rows


def _reusable(target: Path, check: dict, *, cwd: Path, root: Path, candidate: dict, subject: str, run_id: str,
              print_of: Optional[str]) -> Optional[dict]:
    """The row fields of an earlier green evidence file that proves this check on this candidate again, or None (a miss:
    no file, a damaged one, another run, candidate, command, directory or fingerprint)."""
    if print_of is None:
        return None
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or any(issue.level == "error" for issue in contracts.validate(doc, "check-evidence")):
        return None
    found, procedure, owner = doc.get("candidate") or {}, doc.get("procedure") or {}, doc.get("producer") or {}
    exit_code = doc.get("exit")
    if not (isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code == 0) \
            or owner.get("kind") != "engine" or doc.get("check_id") != check["id"] or doc.get("subject") != subject \
            or not str(doc.get("evidence_id", "")).startswith(f"{run_id}:") \
            or found.get("head") != candidate["head"] or found.get("dirty_digest") != candidate["dirty_digest"] \
            or procedure.get("cmd") != check["cmd"] \
            or (doc.get("environment") or {}).get("env_digest") != print_of:
        return None
    try:
        if (root / procedure.get("cwd", ".")).resolve() != cwd:
            return None
        seconds = (datetime.strptime(doc["finished_at"], "%Y-%m-%dT%H:%M:%SZ")
                   - datetime.strptime(doc["started_at"], "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
    except (OSError, ValueError, KeyError):
        return None
    return {"reused_from": doc["evidence_id"], "original_seconds": max(0, int(seconds)), "tail": ""}


def dirty_files(project: Path) -> dict:
    """``{path: sha256}`` of the tracked files that differ from HEAD and of the untracked ones (None: deleted)."""
    names = [line for line in git(project, "diff", "HEAD", "--name-only", "-z").split("\0") if line] + untracked(project)
    found = {}
    for name in names:
        try:
            found[name] = hashlib.sha256((project / name).read_bytes()).hexdigest()
        except OSError:
            found[name] = None
    return found


def changed_files(before: dict, after: dict) -> list:
    """Paths whose state differs between two ``dirty_files`` maps (a path back to HEAD counts as changed too)."""
    return sorted(name for name in set(before) | set(after) if before.get(name, "-") != after.get(name, "-"))


def schedule(wanted: list, previous_rows=(), red_first_ids=()) -> tuple:
    """``(item_order, phase_list)``: the item checks of ``wanted`` in the order they run and its ``phase`` checks as they
    came. Checks named in ``red_first_ids`` (red in the round before) go first; each group by ascending ``seconds`` of the
    latest earlier row of the check (``previous_rows``, oldest first; a skipped row says nothing, a reused one counts with
    the time of the run it stands for); checks without a known time follow the known ones, in the order they came."""
    seconds = {}
    for row in previous_rows or ():
        if not isinstance(row, dict) or row.get("skipped") or "id" not in row:
            continue
        value = row.get("original_seconds") if row.get("reused") else row.get("seconds")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            seconds[row["id"]] = value
    red = set(red_first_ids or ())
    items = [check for check in wanted if check.get("cadence", "item") != "phase"]
    phase = [check for check in wanted if check.get("cadence", "item") == "phase"]
    order = {id(check): number for number, check in enumerate(items)}
    items.sort(key=lambda check: (0 if check["id"] in red else 1, 0 if check["id"] in seconds else 1,
                                  seconds.get(check["id"], 0), order[id(check)]))
    return items, phase


def _dispatch(commands: list, run_one, workers: int, fail_fast: bool) -> tuple:
    """``(rows by id, checks never started)``: ``workers`` command checks at a time, in order; once a check is red (and
    ``fail_fast``) no further one is started and those that run meanwhile end."""
    done = {}
    if workers <= 1 or len(commands) <= 1:
        for number, check in enumerate(commands):
            done[check["id"]] = row = run_one(check)
            if fail_fast and not row["green"]:
                return done, commands[number + 1:]
        return done, []
    gate = threading.Lock()  # admission of a check and publication of a red result never interleave
    failure = {"red": False}

    def guarded(check: dict) -> dict:
        row = run_one(check)
        if fail_fast and not row["green"]:
            with gate:
                failure["red"] = True
        return row

    index = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        running = {}
        while True:
            while index < len(commands) and len(running) < workers:
                with gate:
                    if failure["red"]:
                        break
                    running[pool.submit(guarded, commands[index])] = commands[index]
                index += 1
            if not running:
                return done, commands[index:]
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                check = running.pop(future)
                done[check["id"]] = future.result()


def _run_round(wanted: list, run_one, *, previous, first, fail_fast: bool, on_result, begin) -> list:
    """The rows of ``wanted`` in input order. Item checks run in ``schedule`` order; the ``phase`` checks only when every
    item check is green. A procedure check (a verdict the executor reports) cannot be mended by running it again: it is
    never skipped, and it neither goes ahead nor holds the command checks back, or a missing verdict would keep every
    other check from ever running."""
    items, phase = schedule(wanted, previous, first)
    done = {}

    def skip(check: dict, reason: str) -> None:
        row = {"id": check["id"], "kind": check["kind"], "skipped": True, "skip_reason": reason, "green": False,
               "evidence": None, "cmd": check.get("cmd"), "procedure": check.get("procedure")}
        if on_result is not None:
            on_result(row)
        done[check["id"]] = row

    def stage(checks: list) -> None:
        for check in checks:
            if not check.get("cmd"):
                done[check["id"]] = run_one(check)
        commands = [check for check in checks if check.get("cmd")]
        rows, unstarted = _dispatch(commands, run_one, begin(commands), fail_fast)
        done.update(rows)
        for check in unstarted:
            skip(check, "fail_fast")

    stage(items)
    if all(done[check["id"]]["green"] for check in items):
        stage(phase)
    else:
        for check in phase:
            if check.get("cmd"):
                skip(check, "phase_after_red")
            else:
                done[check["id"]] = run_one(check)
    return [done[check["id"]] for check in wanted]
