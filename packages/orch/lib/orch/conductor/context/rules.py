"""Rules: the instruction sections a role keeps from the repository rules, and the ones the limit dropped."""
from __future__ import annotations

from orch.conductor.context import RULE_HEADING, RULES_CHARS, RulesBlock


def module_rules(carriers, wanted, relative) -> RulesBlock:
    """The sections of ``wanted`` (``instructions.module_rules``; a heading ``## <name>`` matches a rule that is the name or
    its dotted suffix) in the text of each carrier, one line ``- `name` (path): body`` each, with the body on one line, in
    the order of ``carriers``. A section that would take the sum of the bodies to ``RULES_CHARS`` or more is not in
    ``text``; it is listed in ``omitted``, as the kept ones are in ``included`` (``{name, path}``, ``relative`` names the
    path of a carrier)."""
    lines, included, omitted, size = [], [], [], 0
    for carrier in carriers:
        heads = list(RULE_HEADING.finditer(carrier.text))
        for index, head in enumerate(heads):
            name = head.group(1)
            if not any(name == rule or name.endswith("." + rule) for rule in wanted):
                continue
            body = carrier.text[head.end():heads[index + 1].start() if index + 1 < len(heads) else len(carrier.text)]
            body = " ".join(body.split())
            if not body:
                continue
            where = relative(carrier.path)
            if size + len(body) < RULES_CHARS:
                lines.append(f"- `{name}` ({where}): {body}")
                included.append({"name": name, "path": where})
                size += len(body)
            else:
                omitted.append({"name": name, "path": where})
    return RulesBlock(text="\n".join(lines), included=included, omitted=omitted)
