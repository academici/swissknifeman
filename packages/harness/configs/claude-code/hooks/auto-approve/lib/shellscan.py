#!/usr/bin/env python3
"""Quote-aware scan of one shell command for the auto-approve hook.

stdin: the command. stdout: first line "1" when the command holds a dynamic construct outside
single quotes (`$(`, a backtick, `<(`, `>(`, `$'`), else "0"; the remaining lines are the command
with literal quoted text blanked and every code-carrying part kept: the body of `$(...)` and of a
backtick pair stays visible even inside double quotes, because the shell runs it there.
"""
import sys

_DYNAMIC = False


def _flag():
    global _DYNAMIC
    _DYNAMIC = True


def _single(s, i):
    j = s.find("'", i)
    return len(s) if j < 0 else j + 1


def _double(s, i):
    out = [" "]
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
        elif c == '"':
            return "".join(out), i + 1
        elif s.startswith("$(", i):
            _flag()
            sub, i = _code(s, i + 2, ")")
            out.append("$(" + sub)
        elif c == "`":
            _flag()
            sub, i = _code(s, i + 1, "`")
            out.append("`" + sub)
        else:
            i += 1
    return "".join(out), n


def _code(s, i, end):
    out = []
    depth = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            out.append(s[i:i + 2])
            i += 2
        elif c == "'":
            out.append(" ")
            i = _single(s, i + 1)
        elif c == '"':
            text, i = _double(s, i + 1)
            out.append(text)
        elif s.startswith("$(", i):
            _flag()
            sub, i = _code(s, i + 2, ")")
            out.append("$(" + sub)
        elif s.startswith("$'", i):
            _flag()
            out.append("$")
            i += 1
        elif c == "`":
            if end == "`":
                return "".join(out) + "`", i + 1
            _flag()
            sub, i = _code(s, i + 1, "`")
            out.append("`" + sub)
        elif s.startswith(("<(", ">("), i):
            _flag()
            out.append(c)
            i += 1
        elif end == ")" and c == "(":
            depth += 1
            out.append(c)
            i += 1
        elif end == ")" and c == ")":
            if depth == 0:
                return "".join(out) + ")", i + 1
            depth -= 1
            out.append(c)
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out), n


def scan(command):
    global _DYNAMIC
    _DYNAMIC = False
    text, _ = _code(command, 0, None)
    return _DYNAMIC, text


def main():
    dynamic, text = scan(sys.stdin.read())
    sys.stdout.write(("1" if dynamic else "0") + "\n" + text)


if __name__ == "__main__":
    main()
