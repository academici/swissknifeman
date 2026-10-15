"""What an isolated role still needs to know: the rules of the repository instructions for its write set and the
skills of its prompt (named, or chosen by the skills bridge, then checked)."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Optional

from orch.conductor import options as opts, prompts, scope as scopes
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop

RULE_HEADING = re.compile(r"^## ([A-Za-z0-9_.-]+)[ \t]*$", re.M)


def repo_rules(self, item: Item, role: str) -> str:
    """The instruction sections of ``instructions.module_rules`` from the CLAUDE.md (else AGENTS.md) of the
    repository root and of every folder on the way to a write-set path. An isolated role does not read those
    files, and the rest of them are the rules of a developer's session, not of this role."""
    wanted = item.options["instructions"].get("module_rules") or []
    if not wanted:
        return ""
    folders = {Path(".")}
    for pattern in (item.input_doc.get("scope") or {}).get("write_set") or []:
        fixed = []
        for part in str(pattern).split("/")[:-1]:
            if any(mark in part for mark in "*?["):
                break
            fixed.append(part)
        for depth in range(1, len(fixed) + 1):
            folders.add(Path(*fixed[:depth]))
    lines, size = [], 0
    for folder in sorted(folders, key=lambda path: (len(path.parts), str(path))):
        carrier = next((self.project / folder / name for name in ("CLAUDE.md", "AGENTS.md")
                        if (self.project / folder / name).is_file()), None)
        if carrier is None:
            continue
        text = carrier.read_text(encoding="utf-8", errors="replace")
        heads = list(RULE_HEADING.finditer(text))
        for index, head in enumerate(heads):
            name = head.group(1)
            if not any(name == rule or name.endswith("." + rule) for rule in wanted):
                continue
            body = text[head.end():heads[index + 1].start() if index + 1 < len(heads) else len(text)]
            body = " ".join(body.split())
            if body and size + len(body) < 4000:
                lines.append(f"- `{name}` ({self._relative(carrier)}): {body}")
                size += len(body)
    return "\n".join(lines)


def skills(self, item: Item, role: str) -> list:
    """The skill names of a role that its prompt keeps: the list of the run options, or for ``["auto"]`` what the skills
    bridge chose from the write set of the piece (once per piece, kept in ``state.skills_auto``), less what the
    checks of :meth:`_skill_set` left out."""
    return list(self._skill_set(item, role)["names"])


def auto_skills(self, item: Item, role: str) -> dict:
    """``{"skills": [{name, id, path, reason, tokens}], "excluded", "discoverable", "tokens"}`` of the skills bridge
    for ``role``: its command is ``[orch.conductor] skills_bridge``, run as a process (orch imports no other module);
    the answer is kept in the state, so a resume and every later round see the same skills."""
    kept = item.state.setdefault("skills_auto", {})
    if role in kept:
        return kept[role]
    bridge = list(self.conductor.get("skills_bridge") or [])
    if not bridge:
        raise Stop("SKILLS_BRIDGE_UNAVAILABLE", f"skills.{role} is [\"auto\"] but [orch.conductor] skills_bridge names no command "
                   "(a command that answers --select, see the bridge docs)")
    provider = opts.stage_route(item.options, role).get("provider") or self.conductor.get("provider") or "claude-code"
    argv = bridge + ["--select", "--role", role, "--provider", provider, "--project", str(self.project)]
    paths = self._work_paths(item)
    if paths:
        argv += ["--paths", *paths]
    try:
        done = subprocess.run(argv, cwd=str(self.project), capture_output=True, text=True, env=self.env, timeout=120)
        chosen = json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise Stop("SKILLS_SELECT_FAILED", f"skills bridge for {role}: {error.__class__.__name__}: {error}") from None
    if done.returncode != 0 or not isinstance(chosen.get("skills"), list):
        raise Stop("SKILLS_SELECT_FAILED", f"skills bridge for {role} exited {done.returncode}: {done.stderr.strip()[:300]}")
    kept[role] = {key: chosen.get(key, []) for key in ("skills", "excluded", "discoverable")} | {"tokens": chosen.get("tokens", 0)}
    self.progress.emit("info", item=item.ref, role=role, reason_code="SKILLS_SELECTED",
                       message=f"skills of {role}: " + (", ".join(row["id"] for row in chosen["skills"]) or "none")
                       + f" ({chosen.get('tokens', 0)} tokens, {len(chosen.get('excluded', []))} excluded)")
    return kept[role]


def work_paths(self, item: Item) -> list:
    """The paths the piece will touch, for the triggers of the skill selection: the files the write set patterns own in
    the repository (the first 300) plus the patterns themselves, so a file the piece creates still counts; a directory pattern with no
    file yet only matches a trigger written for that directory, so name the skills when the piece starts empty."""
    patterns = [p for p in (item.input_doc.get("scope") or {}).get("write_set") or [] if isinstance(p, str) and p]
    if not patterns:
        return []
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=str(self.project), capture_output=True, text=True,
                                 timeout=30).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        tracked = []
    owned = [path for path in tracked if any(scopes.matches(path, pattern) for pattern in patterns)]
    if len(owned) > 300:
        self.progress.emit("info", item=item.ref, reason_code="SKILLS_PATHS_CUT",
                           message=f"write set owns {len(owned)} files; the first 300 choose the skills")
    return list(dict.fromkeys(owned[:300] + patterns))


def skill_files(self, item: Item, role: str) -> list:
    """``[(name, id, SKILL.md path or None)]`` of the skills a role is given: the skill folders of the project for a
    list of names, the file the bridge named for ``["auto"]`` (its ``id`` is the bridge id, else the name)."""
    names = item.options["skills"].get(role, [])
    if names == [opts.AUTO_SKILLS]:
        return [(row["name"], row.get("id") or row["name"], Path(row["path"])) for row in self._auto_skills(item, role)["skills"]]
    return [(name, name, next((path for path in (self.project / folder / name / "SKILL.md"
                                                for folder in (".claude/skills", ".agents/skills")) if path.is_file()), None))
            for name in names]


def skill_body(path: Path) -> str:
    """The text of a ``SKILL.md`` without its front matter; never cut."""
    body = path.read_text(encoding="utf-8", errors="replace")
    if body.startswith("---"):
        end = body.find("\n---", 3)
        body = body[end + 4:] if end != -1 else body
    return body.strip()


def route_tools(route: Optional[dict]) -> Optional[set]:
    """The tools a route names with ``--tools`` (``--tools ""`` is none); None when the route names no list."""
    argv = (route or {}).get("argv") or []
    if "--tools" not in argv[:-1]:
        return None
    return {tool for tool in str(argv[argv.index("--tools") + 1]).split(",") if tool}


def skill_set(self, item: Item, role: str) -> dict:
    """``{"names", "excluded"}``: the skills a role keeps after the checks of ``prompts.check_skills`` (what each
    skill declares in its ``selection.json`` against the tools of the route and the budget; no text is cut and no
    meaning is judged), and the rows ``{id, reason}`` left out. The verdict is made once per piece and kept in
    ``state.skills_checked``, so a resume and every later round see the same skills; every exclusion is a beacon
    ``SKILL_EXCLUDED``, a declared conflict of two kept skills stops the role with ``PROMPT_CONFLICT``."""
    if not item.options["skills"].get(role):
        return {"names": [], "excluded": []}
    kept = item.state.setdefault("skills_checked", {})
    if role in kept:
        return kept[role]
    weigh = role in item.options["instructions"]["isolate_roles"]  # only an isolated role gets the text in its prompt
    candidates = []
    for name, skill_id, path in self._skill_files(item, role):
        selection = {}
        if path is not None:
            try:
                loaded = json.loads((path.parent / "selection.json").read_text(encoding="utf-8"))
                selection = loaded if isinstance(loaded, dict) else {}
            except (OSError, ValueError):
                selection = {}
        tokens = prompts.estimate_tokens(self._skill_body(path)) if weigh and path is not None else None
        candidates.append({"name": name, "id": skill_id, "selection": selection, "tokens": tokens})
    budget = int(item.options.get("limits", {}).get("skill_tokens_max", opts.DEFAULT_LIMITS["skill_tokens_max"]))
    survivors, rows, conflict = prompts.check_skills(candidates, tools=self._route_tools(item.routes.get(role)), budget=budget)
    if conflict:
        first, second = conflict
        raise Stop("PROMPT_CONFLICT", f"skills {first['id']} and {second['id']} of {role} declare a conflict in their "
                   "selection.json; list only one of them for the role")
    for row in rows:
        self.progress.emit("info", item=item.ref, role=role, reason_code="SKILL_EXCLUDED",
                           message=f"skill {row['id']} left out of the {role} prompt: {row['reason']}"
                           + (f" ({row['detail']})" if row["detail"] else ""))
    kept[role] = {"names": [skill["name"] for skill in survivors],
                  "excluded": [{"id": row["id"], "reason": row["reason"]} for row in rows]}
    return kept[role]


def skills_excluded(self, item: Item, role: str) -> list:
    """The rows ``{id, reason}`` of the skills left out of the prompt of a role, for ``manifest.excluded``."""
    return list(self._skill_set(item, role)["excluded"])


def skill_texts(self, item: Item, role: str) -> dict:
    """The text of the skills a role keeps, when the role runs isolated (its provider then loads no skill by name):
    the SKILL.md of the project's skill folders, or for ``["auto"]`` the file the bridge named, without its front
    matter and whole: a text over its budget was left out by :meth:`_skill_set`, not cut."""
    if not item.options["skills"].get(role) or role not in item.options["instructions"]["isolate_roles"]:
        return {}
    kept = set(self._skill_set(item, role)["names"])
    return {name: self._skill_body(path) for name, _id, path in self._skill_files(item, role)
            if name in kept and path is not None}
