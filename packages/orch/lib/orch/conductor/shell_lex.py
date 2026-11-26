"""Shell word scanning used by check input discovery."""

import re


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
    # `start` is assigned with the opening quote. The initial 0 is never read: `quote` begins empty.
    word, quote, start, index, size = [], "", 0, 0, len(text)

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
