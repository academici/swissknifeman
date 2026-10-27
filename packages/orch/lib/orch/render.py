"""Deterministic Markdown rendering of an execution-input and of a role prompt.

The task block is the same text for every binding: it never rewrites ``goal`` or the
acceptance checks (commands stay verbatim inside fenced code).
"""
from __future__ import annotations

import copy
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


def load_roles(directory: str | Path | None = None) -> dict[str, dict]:
    """Role manifests by id (file stem) from ``directory`` (default: the packaged ``roles``)."""
    base = Path(directory) if directory else ROLES_DIR
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(base.glob("*.json"))}


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
        if item.get("delivery") == "supplement":
            if "content" not in item:
                raise RenderError("CONTEXT_MISSING", "supplement delivery requires inline content")
            content, _ = _context_supplement(doc, item["content"])
            lines[-1] += ("\n\nSource context; scope and result-contract authority still apply. "
                          "Already supplied values refer to text in this same task, never to an external plan file.\n\n"
                          + _json_block(content))
    return _bullets(lines)


def _context_supplement(doc: dict, content: object) -> tuple[object, list]:
    """Retain all context fields; reuse only exact strings already visible in another task section.

    The input and its full pack stay unchanged. The private provenance pairs let tests reconstruct every replaced
    value; workers see ordinary section labels, not a JSON-pointer protocol or an inaccessible ``@plan`` dependency.
    """
    visible_sections = {name: build(doc) for name, build in SECTIONS if name != "Context"}
    headings = {"goal": "Goal", "why": "Why", "scope": "Scope", "constraints": "Constraints",
                "decisions": "Decisions", "guidance": "Guidance", "sections": "Sections", "reads": "Reads",
                "upstream": "Upstream", "lessons": "Lessons", "hints": "Hints", "acceptance": "Acceptance",
                "escalation": "Escalation", "result_contract": "Result contract"}

    def walk(value, path):
        if isinstance(value, str):
            yield path, value
        elif isinstance(value, dict):
            for key, child in value.items():
                yield from walk(child, (*path, key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from walk(child, (*path, index))

    supplied = {}
    for key, title in headings.items():
        for path, value in walk(doc.get(key), (key,)):
            label = title
            if key in ("reads", "decisions") and len(path) > 1:
                entry = doc[key][path[1]]
                label += " — " + str(entry.get("path") or entry.get("ref"))
                if entry.get("section"):
                    label += " · " + entry["section"]
            note = f"Already supplied in {label} (identical text)."
            # No semantic matching, substring cutting, budget truncation or reference to text the renderer omitted.
            visible = visible_sections[title]
            if len(value) > len(note) and (value in visible or json.dumps(value, ensure_ascii=False)[1:-1] in visible):
                supplied.setdefault(value, (path, note))
    reused = []

    def project(value, path=()):
        if isinstance(value, str) and value in supplied:
            source, note = supplied[value]
            reused.append((path, source))
            return note
        if isinstance(value, dict):
            return {key: project(child, (*path, key)) for key, child in value.items()}
        if isinstance(value, list):
            return [project(child, (*path, index)) for index, child in enumerate(value)]
        return value

    return project(content), reused


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
        if check.get("withheld"):
            block += "\n\ncommand: withheld; the conductor runs this check itself after your report"
        elif "cmd" in check:
            block += "\n\ncommand:\n" + _fence(check["cmd"], "bash")
        else:
            block += "\n\nprocedure:\n" + _fence(check["procedure"], "text")
        blocks.append(block)
    return "\n\n".join(blocks)


def withhold_commands(doc: dict) -> dict:
    """A copy of the input whose acceptance checks keep their id, kind and expectation but not their command or
    procedure (``withheld``): for a role that must not run them, so its prompt carries no command to try."""
    checks = [{key: value for key, value in check.items() if key not in ("cmd", "procedure", "cwd")} | {"withheld": True}
              for check in (doc.get("acceptance") or {}).get("checks") or []]
    result = {**doc, "acceptance": {**(doc.get("acceptance") or {}), "checks": checks}}
    # A supplemental source pack can repeat typed validation checks. It must not reintroduce commands withheld above.
    def withhold(value):
        if isinstance(value, dict):
            if {"id", "kind", "expect"} <= value.keys() and ("cmd" in value or "procedure" in value):
                return {key: child for key, child in value.items()
                        if key not in ("cmd", "procedure", "cwd")} | {"withheld": True}
            return {key: withhold(child) for key, child in value.items()}
        return [withhold(child) for child in value] if isinstance(value, list) else value
    if any(item.get("delivery") == "supplement" for item in doc.get("context_refs") or []):
        result["context_refs"] = copy.deepcopy(doc["context_refs"])
        for item in result["context_refs"]:
            if item.get("delivery") == "supplement" and "content" in item:
                content = item["content"]
                if isinstance(content, str):
                    try:
                        decoded = json.loads(content)  # bridges may carry non-canonical numeric JSON as text
                    except ValueError:
                        pass
                    else:
                        if isinstance(decoded, (dict, list)):
                            content = json.dumps(withhold(decoded), ensure_ascii=False, sort_keys=True,
                                                 separators=(",", ":"))
                item["content"] = withhold(content)
    return result


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


def _role_file(path: str) -> Path:
    """Part of a module-relative instruction path below the roles folder; other shapes are refused."""
    parts = Path(path).parts
    if len(parts) < 2 or parts[0] != "roles" or ".." in parts or Path(path).is_absolute():
        raise ValueError(f"instruction path must be module-relative under roles/: {path!r}")
    return Path(*parts[1:])


def load_role(role: str, roles_dir: str | Path | None = None) -> tuple[dict, str]:
    """Manifest and instruction text of ``role``; instruction paths are module-relative (``roles/<id>.md``) and resolve inside ``roles_dir``."""
    directory = Path(roles_dir) if roles_dir is not None else ROLES_DIR
    try:
        manifest = json.loads((directory / f"{role}.json").read_text(encoding="utf-8"))
        texts = [(directory / _role_file(item["path"])).read_text(encoding="utf-8")
                 for item in manifest["instructions"]]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RenderError("ROLE_UNREADABLE", f"cannot load role {role!r} from {directory}: {error}") from error
    if len(texts) == 1:  # byte-exact: the manifest digest covers the file as stored
        return manifest, texts[0]
    return manifest, "\n\n".join(text.rstrip("\n") for text in texts) + "\n"
