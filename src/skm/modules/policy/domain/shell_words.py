"""Simple commands of a supported shell subset (policy §§5.2, 5.2a, port of ``git_guard._simple_commands``).

The parser accepts literal words with quoting, the separators ``; && || | |& &`` and newlines, redirections
(``> >> >| &> &>> < <> <<< N>&M``), prefix assignments, the wrappers of ``WRAPPERS`` with their options (the
directory of ``env -C``/``sudo -D`` is kept in ``chdirs``) and the literal bodies of ``sh -c``, ``eval``,
``find -exec`` and command substitutions, nested at most ``MAX_DEPTH`` deep. Anything else (here-documents,
functions, loops and branches, subshells and groups, brace expansion, ``$'…'``, an unbalanced quote, depth
overflow, an unresolved expansion as a command head, a redirect target or a shell body, ``env -S``, a nested
body behind ``env -C``) makes the whole line unsupported: ``simple_commands`` returns ``None`` and
callers ask instead of reporting that nothing dangerous was found. The result is a preflight of what the
line names, never a proof of what the programs do.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

__all__ = [
    "MAX_DEPTH",
    "SEPARATORS",
    "SHELLS",
    "WRAPPERS",
    "WRAPPER_VALUE_OPTS",
    "ShellParse",
    "ShellWord",
    "SimpleCommand",
    "parse",
    "simple_commands",
]

MAX_DEPTH = 6
SEPARATORS = frozenset({";", "&&", "||", "|", "|&", "&", "\n"})
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash", "yash"})
WRAPPERS = frozenset(
    {
        "sudo",
        "doas",
        "env",
        "timeout",
        "nice",
        "ionice",
        "nohup",
        "setsid",
        "stdbuf",
        "chrt",
        "taskset",
        "xargs",
        "command",
        "builtin",
        "exec",
        "time",
        "unbuffer",
    }
)
# Options of a wrapper that take the next word as their value.
WRAPPER_VALUE_OPTS: dict[str, frozenset[str]] = {
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group"}),
    "doas": frozenset({"-u", "-C"}),
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "ionice": frozenset({"-c", "--class", "-n", "--classdata", "-p", "--pid"}),
    "stdbuf": frozenset({"-i", "-o", "-e", "--input", "--output", "--error"}),
    "chrt": frozenset(),
    "taskset": frozenset({"-c", "--cpu-list"}),
    "xargs": frozenset(
        {"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "--max-args", "--max-procs", "--delimiter"}
    ),
    "time": frozenset({"-f", "--format", "-o", "--output"}),
}
# Options of a wrapper that run the wrapped command in another directory (``SimpleCommand.chdirs``).
_WRAPPER_CHDIR_OPTS: dict[str, frozenset[str]] = {
    "env": frozenset({"-C", "--chdir"}),
    "sudo": frozenset({"-D", "--chdir"}),
}
# ``env -S`` splits its value into the wrapped argv: the command is not a list of literal words.
_WRAPPER_SPLIT_OPTS: dict[str, frozenset[str]] = {"env": frozenset({"-S", "--split-string"})}
# Positional words a wrapper consumes before the wrapped command (``timeout 5 cmd``).
_WRAPPER_POSITIONALS = {"timeout": 1, "chrt": 1, "taskset": 1}
_KEYWORDS_UNSUPPORTED = frozenset(
    {
        "if",
        "then",
        "else",
        "elif",
        "fi",
        "for",
        "while",
        "until",
        "do",
        "done",
        "case",
        "esac",
        "select",
        "function",
        "{",
        "}",
        "[[",
        "]]",
        "coproc",
    }
)
_KEYWORDS_SKIPPED = frozenset({"!"})
_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]")
_FIND_EXEC = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_WRITE_REDIRECTS = frozenset({">", ">>", ">|", "&>", "&>>", "<>"})
_DUP_REDIRECTS = frozenset({">&", "<&"})
_OPERATORS = (
    "&>>",
    "<<<",
    "<<-",
    ";;",
    "&&",
    "||",
    "|&",
    ">>",
    ">|",
    "&>",
    ">&",
    "<&",
    "<>",
    "<<",
    "<(",
    ">(",
    ";",
    "&",
    "|",
    ">",
    "<",
    "(",
    ")",
)


class Unsupported(ValueError):
    """The line leaves the supported subset; the message names the construct."""


@dataclass(frozen=True, slots=True)
class ShellWord:
    value: str
    opaque: bool = False  # holds an expansion whose value is unknown before execution
    glob: bool = False  # holds an unquoted *, ? or [


@dataclass(frozen=True, slots=True)
class SimpleCommand:
    words: tuple[ShellWord, ...]  # argv after assignments and wrappers
    assignments: tuple[str, ...] = ()  # NAME=value of the prefix and of ``env``
    wrappers: tuple[str, ...] = ()  # stripped wrapper programs, as written
    redirect_targets: tuple[str, ...] = ()  # write targets of > >> >| &> &>> <>
    read_targets: tuple[str, ...] = ()  # targets of < and <&file
    connector: str = ""  # separator after the command at its own depth
    depth: int = 0
    text: str = ""
    chdirs: tuple[ShellWord, ...] = ()  # last ``env -C``/``sudo -D`` of each wrapper, outermost first

    @property
    def argv(self) -> tuple[str, ...]:
        return tuple(word.value for word in self.words)

    @property
    def program(self) -> str:
        return self.words[0].value if self.words else ""

    @property
    def head(self) -> str:
        """Basename of the program: a policy/UX label, never proof of the binary's identity (§5.2a)."""
        return posixpath.basename(self.program)


@dataclass(frozen=True, slots=True)
class ShellParse:
    commands: tuple[SimpleCommand, ...]
    error: str | None

    @property
    def supported(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class _Op:
    text: str
    fd: str = ""


@dataclass(frozen=True, slots=True)
class _Word:
    word: ShellWord
    raw: str
    bodies: tuple[str, ...]  # command substitutions to parse one level deeper


def _matching(text: str, start: int, opening: str, closing: str) -> int:
    """Index after the ``closing`` that balances ``text[start]``; quotes and escapes are skipped."""
    depth = 0
    i = start
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "'":
            end = text.find("'", i + 1)
            if end < 0:
                raise Unsupported("unbalanced quote")
            i = end + 1
            continue
        if char == '"':
            i = _double_end(text, i)
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Unsupported(f"unbalanced {opening}")


def _double_end(text: str, start: int) -> int:
    i = start + 1
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
        elif char == '"':
            return i + 1
        elif text.startswith("$(", i):
            i = _matching(text, i + 1, "(", ")")
        elif char == "`":
            i = _backtick_end(text, i)
        else:
            i += 1
    raise Unsupported("unbalanced quote")


def _backtick_end(text: str, start: int) -> int:
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text[i] == "`":
            return i + 1
        else:
            i += 1
    raise Unsupported("unbalanced backtick")


class _Lexer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0
        self.tokens: list[_Op | _Word] = []

    def run(self) -> list[_Op | _Word]:
        text = self.text
        while self.i < len(text):
            char = text[self.i]
            if char in " \t":
                self.i += 1
            elif char == "\\" and text.startswith("\\\n", self.i):
                self.i += 2
            elif char == "\n":
                self.tokens.append(_Op("\n"))
                self.i += 1
            elif char == "#" and self._word_start():
                end = text.find("\n", self.i)
                self.i = len(text) if end < 0 else end
            elif char in ";&|<>()":
                self._operator("")
            else:
                self._word()
        return self.tokens

    def _word_start(self) -> bool:
        return self.i == 0 or self.text[self.i - 1] in " \t\n;&|()<>"

    def _operator(self, fd: str) -> None:
        text = self.text
        for op in _OPERATORS:
            if text.startswith(op, self.i):
                self.i += len(op)
                if op in {"<(", ">("}:
                    end = _matching(text, self.i - 1, "(", ")")
                    body = text[self.i : end - 1]
                    self.i = end
                    self.tokens.append(_Word(ShellWord("/dev/fd/?", opaque=True), op + body + ")", (body,)))
                    return
                self.tokens.append(_Op(op, fd))
                return
        raise Unsupported(f"operator at {self.i}")  # pragma: no cover - every metacharacter is listed

    def _word(self) -> None:
        text = self.text
        start = self.i
        value: list[str] = []
        bodies: list[str] = []
        opaque = glob = False
        while self.i < len(text):
            char = text[self.i]
            if char in " \t\n;&|()<>":
                break
            if char == "\\":
                if self.i + 1 == len(text):
                    raise Unsupported("trailing escape")
                if self.i + 1 < len(text) and text[self.i + 1] != "\n":
                    value.append(text[self.i + 1])
                self.i += 2
            elif char == "'":
                end = text.find("'", self.i + 1)
                if end < 0:
                    raise Unsupported("unbalanced quote")
                value.append(text[self.i + 1 : end])
                self.i = end + 1
            elif char == '"':
                opaque |= self._double(value, bodies)
            elif char == "$":
                opaque |= self._dollar(value, bodies, quoted=False)
            elif char == "`":
                end = _backtick_end(text, self.i)
                bodies.append(text[self.i + 1 : end - 1])
                opaque = True
                self.i = end
            else:
                if char in "*?[":
                    glob = True
                elif char in "{}":
                    self._brace(start)
                value.append(char)
                self.i += 1
        raw = text[start : self.i]
        if raw.isdigit() and self.i < len(text) and text[self.i] in "<>":
            self._operator(raw)
            return
        opaque |= raw.startswith("~") and raw.split("/", 1)[0] != "~"  # ~user, ~+, ~-: passwd, PWD, OLDPWD
        self.tokens.append(_Word(ShellWord("".join(value), opaque, glob), raw, tuple(bodies)))

    def _brace(self, start: int) -> None:
        raw_end = self.i
        while raw_end < len(self.text) and self.text[raw_end] not in " \t\n;&|()<>":
            raw_end += 1
        raw = self.text[start:raw_end]
        if raw in {"{", "}"} or re.search(r"\{[^{}]*(,|\.\.)[^{}]*\}", raw):
            raise Unsupported("brace group or expansion")

    def _double(self, value: list[str], bodies: list[str]) -> bool:
        text = self.text
        opaque = False
        self.i += 1
        while self.i < len(text):
            char = text[self.i]
            if char == '"':
                self.i += 1
                return opaque
            if char == "\\":
                nxt = text[self.i + 1 : self.i + 2]
                if nxt in {"$", "`", '"', "\\"}:
                    value.append(nxt)
                elif nxt != "\n":
                    value.append("\\" + nxt)
                self.i += 2
            elif char == "$":
                opaque |= self._dollar(value, bodies, quoted=True)
            elif char == "`":
                end = _backtick_end(text, self.i)
                bodies.append(text[self.i + 1 : end - 1])
                opaque = True
                self.i = end
            else:
                value.append(char)
                self.i += 1
        raise Unsupported("unbalanced quote")

    def _dollar(self, value: list[str], bodies: list[str], *, quoted: bool) -> bool:
        text, i = self.text, self.i
        if text.startswith("$((", i):
            self.i = _matching(text, i + 1, "(", ")")
            return True
        if text.startswith("$(", i):
            end = _matching(text, i + 1, "(", ")")
            bodies.append(text[i + 2 : end - 1])
            self.i = end
            return True
        if text.startswith("${", i):
            self.i = _matching(text, i + 1, "{", "}")
            return True
        if text.startswith("$'", i) and not quoted:
            raise Unsupported("ANSI-C quoting")
        if text.startswith('$"', i) and not quoted:
            self.i += 1
            return False
        match = _NAME_RE.match(text, i + 1)
        if match is None:
            value.append("$")
            self.i += 1
            return False
        self.i = match.end()
        return True


@dataclass(slots=True)
class _Segment:
    words: list[_Word]
    redirects: list[tuple[_Op, _Word]]
    connector: str = ""


def _segments(tokens: list[_Op | _Word]) -> list[_Segment]:
    segments: list[_Segment] = []
    current = _Segment([], [])
    pending: _Op | None = None
    for token in tokens:
        if pending is not None:
            if not isinstance(token, _Word):
                raise Unsupported(f"redirect {pending.text} without target")
            current.redirects.append((pending, token))
            pending = None
            continue
        if isinstance(token, _Word):
            current.words.append(token)
            continue
        op = token.text
        if op in SEPARATORS:
            if not current.words and not current.redirects:
                if op == "\n":
                    continue
                raise Unsupported(f"empty command before {op!r}")
            current.connector = op
            segments.append(current)
            current = _Segment([], [])
        elif op in {"<<", "<<-"}:
            raise Unsupported("here-document")
        elif op in {"(", ")", ";;"}:
            raise Unsupported(f"compound command {op!r}")
        else:
            pending = token
    if pending is not None:
        raise Unsupported(f"redirect {pending.text} without target")
    if current.words or current.redirects:
        segments.append(current)
    elif segments and segments[-1].connector not in {";", "&", "\n"}:
        raise Unsupported(f"command missing after {segments[-1].connector!r}")
    return segments


class _Parser:
    def __init__(self) -> None:
        self.commands: list[SimpleCommand] = []

    def line(self, text: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise Unsupported("nesting deeper than MAX_DEPTH")
        for segment in _segments(_Lexer(text).run()):
            self._segment(segment, depth)

    def _segment(self, segment: _Segment, depth: int) -> None:
        writes: list[str] = []
        reads: list[str] = []
        for op, target in segment.redirects:
            self._bodies(target, depth)
            if op.text in _DUP_REDIRECTS and (target.word.value.isdigit() or target.word.value == "-"):
                continue
            if target.word.opaque:
                raise Unsupported("unresolved redirect target")
            if op.text in _WRITE_REDIRECTS or op.text == ">&":
                writes.append(target.word.value)
            elif op.text != "<<<":
                reads.append(target.word.value)
        words = list(segment.words)
        for word in words:
            self._bodies(word, depth)
        assignments: list[str] = []
        while words and _ASSIGNMENT_RE.match(words[0].raw):
            if words[0].word.opaque:
                raise Unsupported("unresolved assignment")
            assignments.append(words.pop(0).word.value)
        while words and words[0].raw in _KEYWORDS_SKIPPED:
            words.pop(0)
        if words and words[0].raw in _KEYWORDS_UNSUPPORTED:
            raise Unsupported(f"compound keyword {words[0].raw!r}")
        argv = [word.word for word in words]
        wrappers, stripped, env_assignments, chdirs = _strip_wrappers(argv)
        if stripped and stripped[0].opaque:
            raise Unsupported("unresolved command head")
        command = SimpleCommand(
            words=tuple(stripped),
            assignments=(*assignments, *env_assignments),
            wrappers=tuple(wrappers),
            redirect_targets=tuple(writes),
            read_targets=tuple(reads),
            connector=segment.connector,
            depth=depth,
            text=" ".join(word.raw for word in segment.words),
            chdirs=tuple(chdirs),
        )
        self.commands.append(command)
        self._nested(command, depth)

    def _bodies(self, word: _Word, depth: int) -> None:
        for body in word.bodies:
            self.line(body, depth + 1)

    def _nested(self, command: SimpleCommand, depth: int) -> None:
        head, words = command.head, command.words
        # a body behind ``env -C dir`` starts in ``dir``, which a nested command cannot carry
        moved = "a nested body in the directory of a wrapper" if command.chdirs else ""
        if head in SHELLS:
            body = _shell_body(words)
            if body is not None:
                if body.opaque or moved:
                    raise Unsupported(moved or "unresolved shell body")
                self.line(body.value, depth + 1)
            elif any(word.value == "-c" for word in words[1:]):
                raise Unsupported("shell body missing")
        elif head == "eval" and len(words) > 1:
            if moved or any(word.opaque for word in words[1:]):
                raise Unsupported(moved or "unresolved eval body")
            self.line(" ".join(word.value for word in words[1:]), depth + 1)
        elif head == "find":
            bodies = _find_exec(words)
            if bodies and moved:
                raise Unsupported(moved)
            for nested in bodies:
                self._argv(nested, depth + 1)

    def _argv(self, argv: list[ShellWord], depth: int) -> None:
        if depth > MAX_DEPTH:
            raise Unsupported("nesting deeper than MAX_DEPTH")
        wrappers, stripped, env_assignments, chdirs = _strip_wrappers(argv)
        if not stripped or stripped[0].opaque:
            raise Unsupported("unresolved command head")
        command = SimpleCommand(
            words=tuple(stripped),
            assignments=tuple(env_assignments),
            wrappers=tuple(wrappers),
            depth=depth,
            text=" ".join(word.value for word in argv),
            chdirs=tuple(chdirs),
        )
        self.commands.append(command)
        self._nested(command, depth)


def _shell_body(words: tuple[ShellWord, ...]) -> ShellWord | None:
    """The literal body of ``sh -c BODY`` (also ``bash -lc``, ``sh -e -o pipefail -c``); ``None`` without
    ``-c`` (a script file is an untrusted program like any other)."""
    index = 1
    while index < len(words):
        value = words[index].value
        if value.startswith("--") and value != "--":
            index += 1
            continue
        if not value.startswith(("-", "+")) or value in {"-", "--"}:
            return None
        if value in {"-o", "+o", "-O", "+O"}:
            index += 2
            continue
        if value.startswith("-") and "c" in value[1:]:
            return words[index + 1] if index + 1 < len(words) else None
        index += 1
    return None


def _find_exec(words: tuple[ShellWord, ...]) -> list[list[ShellWord]]:
    result: list[list[ShellWord]] = []
    index = 1
    while index < len(words):
        if words[index].value in _FIND_EXEC:
            end = index + 1
            while end < len(words) and words[end].value not in {";", "+"}:
                end += 1
            if end > index + 1:
                result.append(list(words[index + 1 : end]))
            index = end
        index += 1
    return result


def _strip_wrappers(
    argv: list[ShellWord],
) -> tuple[list[str], list[ShellWord], list[str], list[ShellWord]]:
    """Skip wrappers, their options and their positional words; keep a bare wrapper as the command. The
    directories of ``env -C``/``sudo -D`` are returned, not dropped: the wrapped command runs there."""
    wrappers: list[str] = []
    assignments: list[str] = []
    chdirs: list[ShellWord] = []
    words = list(argv)
    while words and posixpath.basename(words[0].value) in WRAPPERS and not words[0].opaque:
        name = posixpath.basename(words[0].value)
        moved: list[ShellWord] = []
        rest = _skip_wrapper(name, words[1:], assignments, moved)
        if not rest:
            break
        wrappers.append(words[0].value)
        chdirs.extend(moved)
        words = rest
    return wrappers, words, assignments, chdirs


def _wrapper_option(value: str, takes_value: frozenset[str], first: frozenset[str]) -> tuple[str, str | None]:
    """``(option, attached value)`` of a word that takes a value (``""`` when none does): ``-C dir``,
    ``-Cdir``, ``-iC dir``, ``--chdir=dir``. A long abbreviation (getopt_long) counts as the option it
    abbreviates; when it is ambiguous, an option of ``first`` wins (the directory is never lost)."""
    if value.startswith("--"):
        name, sep, rest = value.partition("=")
        if name not in takes_value:
            matches = [option for option in sorted(takes_value) if len(name) > 2 and option.startswith(name)]
            preferred = [option for option in matches if option in first]
            name = (preferred or matches or [""])[0]
            if not name:
                return "", None
        return name, rest if sep else None
    for index, letter in enumerate(value[1:], start=2):
        if "-" + letter in takes_value:
            return "-" + letter, value[index:] or None
    return "", None


def _skip_wrapper(
    name: str, words: list[ShellWord], assignments: list[str], chdirs: list[ShellWord]
) -> list[ShellWord]:
    chdir = _WRAPPER_CHDIR_OPTS.get(name, frozenset[str]())
    split = _WRAPPER_SPLIT_OPTS.get(name, frozenset[str]())
    takes_value = WRAPPER_VALUE_OPTS.get(name, frozenset[str]()) | chdir | split
    index = 0
    while index < len(words):
        word = words[index]
        value = word.value
        if value == "--":
            index += 1
            break
        if name == "env" and _ASSIGNMENT_RE.match(value):
            assignments.append(value)
        elif not value.startswith("-") or value == "-":
            break
        else:
            option, attached = _wrapper_option(value, takes_value, chdir | split)
            if option in split:
                raise Unsupported(f"{name} {option} splits its value into words")
            if option and attached is None:
                index += 1
                argument = words[index] if index < len(words) else ShellWord("", opaque=True)
            else:
                argument = ShellWord(attached or "", word.opaque)
            if option in chdir:  # getopt keeps one directory per invocation: the last option wins,
                # but an opaque one may field-split into other argv words, so it is never dropped
                chdirs[:] = [*(directory for directory in chdirs if directory.opaque), argument]
        index += 1
    return words[index + _WRAPPER_POSITIONALS.get(name, 0) :]


def parse(command: str) -> ShellParse:
    """Every simple command of the line, nested bodies included, or the reason the line is unsupported."""
    parser = _Parser()
    try:
        parser.line(command, 0)
    except (Unsupported, IndexError) as error:
        return ShellParse((), str(error) or "unsupported syntax")
    return ShellParse(tuple(parser.commands), None)


def simple_commands(command: str) -> tuple[SimpleCommand, ...] | None:
    """``None`` when the line leaves the supported subset (§5.2a: the caller asks, never assumes safety)."""
    result = parse(command)
    return result.commands if result.supported else None
