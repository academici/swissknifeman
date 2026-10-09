"""Mustache subset for the generated plan views (stdlib only, no escaping, Markdown output).

Tags: ``{{a.b}}`` lookup through the context stack, ``{{.}}`` current value, ``{{#x}}..{{/x}}`` section
(list: iterate; truthy scalar/dict: once with the value pushed), ``{{^x}}..{{/x}}`` inverted section,
``{{>name}}`` partial, ``{{! comment}}``. A missing key renders ``""``. A line holding only one section,
partial or comment tag plus whitespace is removed with its newline, so table rows built by partials leave
no blank lines; such a partial always renders as complete lines. Anything else is a ``TemplateError``.
"""
from __future__ import annotations

import re
from typing import Any, Callable

_TAG = re.compile(r"\{\{([#^/>!]?)([^{}]*?)\}\}")
_NAME = re.compile(r"^(\.|[A-Za-z_][\w-]*(\.[A-Za-z_][\w-]*)*)$")
_PARTIAL = re.compile(r"^[a-z0-9_-]+$")
_MAX_DEPTH = 10


class TemplateError(ValueError):
    """Unknown tag syntax, unbalanced sections, a missing partial or a non-scalar variable."""


def render(template: str, context: Any, partials_loader: Callable[[str], str]) -> str:
    return _render(_parse(template), [context], partials_loader, 0)


def _tokens(template: str) -> list:
    """``[text, tag, text, ..., text]``; a tag is ``(kind, name[, standalone])``; standalone lines are trimmed."""
    if "{{{" in template or "}}}" in template or re.search(r"\{\{|\}\}", _TAG.sub("", template)):
        raise TemplateError("stray or unsupported brace delimiters (triple braces are not supported)")
    pieces: list = []
    position = 0
    for match in _TAG.finditer(template):
        kind, name = match.group(1), match.group(2).strip()
        if kind == "!":
            name = ""
        elif kind == ">":
            if not _PARTIAL.match(name):
                raise TemplateError(f"invalid partial name {name!r}")
        elif not _NAME.match(name) or (kind and name == "."):
            raise TemplateError(f"invalid tag {match.group(0)!r}")
        pieces += [template[position:match.start()], (kind, name)]
        position = match.end()
    pieces.append(template[position:])
    standalone = []  # decided on the untouched text: trimming one tag must not hide the next tag's line start
    for index in range(1, len(pieces), 2):
        if pieces[index][0] == "":
            continue
        before, after = pieces[index - 1], pieces[index + 1]
        tail, head = before[before.rfind("\n") + 1:], after.split("\n", 1)[0]
        starts_line = index == 1 or "\n" in before
        ends_line = index == len(pieces) - 2 or "\n" in after
        if starts_line and ends_line and not tail.strip() and not head.strip():
            standalone.append((index, len(tail), len(head) + ("\n" in after)))
    for index, tail_length, head_length in standalone:
        pieces[index - 1] = pieces[index - 1][:len(pieces[index - 1]) - tail_length]
        pieces[index + 1] = pieces[index + 1][head_length:]
        pieces[index] = (*pieces[index], True)
    return pieces


def _parse(template: str) -> list:
    pieces = _tokens(template)
    root: list = []
    stack: list[tuple[str, list]] = [("", root)]
    for index, piece in enumerate(pieces):
        nodes = stack[-1][1]
        if index % 2 == 0:
            if piece:
                nodes.append(("text", piece))
            continue
        kind, name = piece[0], piece[1]
        if kind == "":
            nodes.append(("var", name))
        elif kind == ">":
            nodes.append(("partial", name, len(piece) == 3))
        elif kind in ("#", "^"):
            children: list = []
            nodes.append(("section", name, kind == "^", children))
            stack.append((name, children))
        elif kind == "/":
            if len(stack) == 1 or stack[-1][0] != name:
                raise TemplateError(f"unbalanced section close {{{{/{name}}}}}")
            stack.pop()
    if len(stack) != 1:
        raise TemplateError(f"unclosed section {{{{#{stack[-1][0]}}}}}")
    return root


def _lookup(stack: list, name: str) -> Any:
    if name == ".":
        return stack[-1]
    first, *rest = name.split(".")
    for scope in reversed(stack):
        if isinstance(scope, dict) and first in scope:
            value = scope[first]
            break
    else:
        return None
    for part in rest:
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _render(nodes: list, stack: list, loader: Callable[[str], str], depth: int) -> str:
    out: list[str] = []
    for node in nodes:
        kind = node[0]
        if kind == "text":
            out.append(node[1])
        elif kind == "var":
            value = _lookup(stack, node[1])
            if isinstance(value, (list, dict)):
                raise TemplateError(f"variable {{{{{node[1]}}}}} is not a scalar")
            out.append("" if value is None else str(value).lower() if isinstance(value, bool) else str(value))
        elif kind == "partial":
            if depth >= _MAX_DEPTH:
                raise TemplateError("partials nest deeper than 10 levels")
            text = _render(_parse(loader(node[1])), stack, loader, depth + 1)
            out.append(text + "\n" if node[2] and text and not text.endswith("\n") else text)
        else:
            _, name, inverted, children = node
            value = _lookup(stack, name)
            if inverted:
                if not value:
                    out.append(_render(children, stack, loader, depth))
            elif isinstance(value, list):
                for element in value:
                    out.append(_render(children, [*stack, element], loader, depth))
            elif value:
                out.append(_render(children, [*stack, value], loader, depth))
    return "".join(out)
