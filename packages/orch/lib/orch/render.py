"""Deterministic Markdown rendering of an execution-input and of a role prompt.

The task block is the same text for every binding: it never rewrites ``goal`` or the
acceptance checks (commands stay verbatim inside fenced code).
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable

ROLES_DIR = Path(__file__).resolve().parents[2] / "roles"
_BACKTICKS = re.compile(r"`+")


class RenderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fence(text: str, lang: str = "") -> str:
    """Fenced code block that cannot be closed by the content itself."""
    longest = max((len(run) for run in _BACKTICKS.findall(text)), default=0)
    mark = "`" * max(3, longest + 1)
    return f"{mark}{lang}\n{text}\n{mark}"


def _bullets(items: list) -> str:
    return "\n".join(f"- {item}" for item in items)


def _json_block(value: object) -> str:
    return _fence(json.dumps(value, ensure_ascii=False, indent=2), "json")


def _goal(doc: dict) -> str:
    return doc["goal"]


def _why(doc: dict) -> str:
    return doc.get("why", "")


def _scope(doc: dict) -> str:
    scope = doc.get("scope") or {}
    parts = []
    for label, key in (("Include", "include"), ("Exclude", "exclude"), ("Write set", "write_set")):
        if scope.get(key):
            parts.append(f"**{label}**\n{_bullets(scope[key])}")
    if "read_only" in scope:
        parts.append(f"**Read only**: {'yes' if scope['read_only'] else 'no'}")
    return "\n\n".join(parts)


def _constraints(doc: dict) -> str:
    return _bullets([f"{item['text']} (`{item['source']}`)" for item in doc.get("constraints") or []])


def _decisions(doc: dict) -> str:
    blocks = []
    for item in doc.get("decisions") or []:
        title = f"### {item['ref']}" + (f" — {item['title']}" if item.get("title") else "")
        lines = []
        if not item.get("loaded", True):
            lines.append("- loaded: no")
        for key in ("status", "decision", "rationale", "reason"):
            if item.get(key):
                lines.append(f"- {key}: {item[key]}")
        source = item.get("source")
        if source:
            lines.append(f"- source: `{source.get('path', '')}`" + (f" (`{source['sha256']}`)" if source.get("sha256") else ""))
        blocks.append("\n".join([title, *lines]))
    return "\n\n".join(blocks)


def _guidance(doc: dict) -> str:
    return doc.get("guidance", "")


def _sections(doc: dict) -> str:
    blocks = []
    for item in doc.get("sections") or []:
        blocks.append(f"### {item['title']} (`{item['id']}`)" + (f"\n\n{item['text']}" if item["text"] else ""))
    return "\n\n".join(blocks)


def _reads(doc: dict) -> str:
    blocks = []
    for item in doc.get("reads") or []:
        head = f"### `{item['path']}`" + (f" · {item['section']}" if item.get("section") else "")
        lines = [f"- why: {item['why']}", f"- required: {'yes' if item['required'] else 'no'}",
                 f"- exists: {'yes' if item['exists'] else 'no'}"]
        if item.get("sha256"):
            lines.append(f"- sha256: `{item['sha256']}`")
        if item.get("error"):
            lines.append(f"- error: {item['error']}")
        block = "\n".join([head, *lines])
        if "content" in item:
            block += "\n\n" + _json_block(item["content"])
        blocks.append(block)
    return "\n\n".join(blocks)


def _context(doc: dict) -> str:
    lines = []
    for item in doc.get("context_refs") or []:
        line = f"{item['kind']} `{item['ref']}`"
        if item.get("path"):
            line += f" — `{item['path']}`"
        if item.get("sha256"):
            line += f" (`{item['sha256']}`)"
        lines.append(line)
    return _bullets(lines)


def _upstream(doc: dict) -> str:
    blocks = []
    for item in doc.get("upstream") or []:
        lines = [f"### `{item['ref']}` — {item['title']} ({item['status']})"]
        for key in ("summary", "notes"):
            if item.get(key):
                lines.append(f"- {key}: {item[key]}")
        if item.get("deliverables"):
            lines.append("- deliverables: " + ", ".join(item["deliverables"]))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _lessons(doc: dict) -> str:
    lines = []
    for item in doc.get("lessons") or []:
        line = f"[{item['type']}] {item['summary']} ({item['ts']}" + (f", {item['item']}" if item.get("item") else "") + ")"
        for key in ("impact", "next"):
            if item.get(key):
                line += f"; {key}: {item[key]}"
        lines.append(line)
    return _bullets(lines)


def _hints(doc: dict) -> str:
    return _bullets([f"{item['text']} ({item['source']})" for item in doc.get("hints") or []])


def _acceptance(doc: dict) -> str:
    blocks = []
    for check in (doc.get("acceptance") or {}).get("checks") or []:
        lines = [f"### {check['id']} · {check['kind']}", f"- expect: {check['expect']}"]
        if check.get("cwd"):
            lines.append(f"- cwd: `{check['cwd']}`")
        block = "\n".join(lines)
        if "cmd" in check:
            block += "\n\ncommand:\n" + _fence(check["cmd"], "bash")
        else:
            block += "\n\nprocedure:\n" + _fence(check["procedure"], "text")
        blocks.append(block)
    return "\n\n".join(blocks)


def _deliverables(doc: dict) -> str:
    return _bullets((doc.get("acceptance") or {}).get("deliverables") or [])


def _escalation(doc: dict) -> str:
    return _bullets(doc.get("escalation") or [])


def _result_contract(doc: dict) -> str:
    contract = doc["result_contract"]
    report = ", ".join(f"`{field}`" for field in contract["report"])
    return _bullets([f"report: {report}", f"write_authority: `{contract['write_authority']}`",
                     f"commit_owner: `{contract['commit_owner']}`",
                     f"plan_mutation: `{contract['plan_mutation']}`"])


# Fixed order; an empty section is omitted. Context, Upstream, Lessons and Hints carry the fields
# the role texts promise ("You receive") and sit between Reads and Acceptance.
SECTIONS: tuple[tuple[str, Callable[[dict], str]], ...] = (
    ("Goal", _goal), ("Why", _why), ("Scope", _scope), ("Constraints", _constraints),
    ("Decisions", _decisions), ("Guidance", _guidance), ("Sections", _sections), ("Reads", _reads),
    ("Context", _context), ("Upstream", _upstream), ("Lessons", _lessons), ("Hints", _hints),
    ("Acceptance", _acceptance), ("Deliverables", _deliverables), ("Escalation", _escalation),
    ("Result contract", _result_contract),
)


def render_section(input_doc: dict, name: str) -> str:
    """One task-block section with its heading, or an empty string when the section is empty."""
    for title, build in SECTIONS:
        if title == name:
            body = build(input_doc)
            return f"## {title}\n\n{body}\n" if body else ""
    raise RenderError("SECTION_UNKNOWN", f"unknown task-block section: {name!r}")


def render_task_block(input_doc: dict) -> str:
    """Markdown task block of an execution-input; identical for every binding."""
    return "\n".join(block for title, _ in SECTIONS if (block := render_section(input_doc, title)))


def _skills(manifest: dict) -> str:
    skills = manifest.get("skills") or []
    if not skills:
        return ""
    lines = [f"- `{item['name']}` ({'required' if item['required'] else 'optional'}) — {item['why']}"
             for item in skills]
    return "## Skills\n\n" + "\n".join(lines) + "\n"


def check_instructions(manifest: dict, instructions_text: str) -> None:
    """Raise ``INSTRUCTIONS_DRIFT`` when the text differs from the digest the manifest declares."""
    declared = manifest.get("instructions") or []
    if len(declared) != 1 or "sha256" not in declared[0]:
        return
    actual = sha256(instructions_text.encode("utf-8")).hexdigest()
    if actual != declared[0]["sha256"]:
        raise RenderError("INSTRUCTIONS_DRIFT", f"role {manifest.get('role_id')!r} instructions sha256 is "
                          f"{actual}, the manifest declares {declared[0]['sha256']}")


def render_prompt(input_doc: dict, manifest: dict, instructions_text: str) -> str:
    """Role instructions, ``---`` and the task block."""
    check_instructions(manifest, instructions_text)
    head = instructions_text.rstrip("\n") + "\n"
    skills = _skills(manifest)
    if skills:
        head += "\n" + skills
    return f"{head}\n---\n\n{render_task_block(input_doc)}"


def load_role(role: str, roles_dir: str | Path | None = None) -> tuple[dict, str]:
    """Manifest and instruction text of ``role``; instruction files resolve by name inside ``roles_dir``."""
    directory = Path(roles_dir) if roles_dir is not None else ROLES_DIR
    try:
        manifest = json.loads((directory / f"{role}.json").read_text(encoding="utf-8"))
        texts = [(directory / Path(item["path"]).name).read_text(encoding="utf-8")
                 for item in manifest["instructions"]]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RenderError("ROLE_UNREADABLE", f"cannot load role {role!r} from {directory}: {error}") from error
    if len(texts) == 1:  # byte-exact: the manifest digest covers the file as stored
        return manifest, texts[0]
    return manifest, "\n\n".join(text.rstrip("\n") for text in texts) + "\n"
