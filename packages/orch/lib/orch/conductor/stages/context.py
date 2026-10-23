"""What an isolated role still needs to know: the rules of the repository instructions for its write set and the
skills of its prompt (named, or chosen by the skills bridge, then checked)."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Optional

from aicore.util import schema

from orch.conductor import options as opts, prompts, scope as scopes
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.policies import paths, protected_writes

RULE_HEADING = re.compile(r"^## ([A-Za-z0-9_.-]+)[ \t]*$", re.M)
SKILL_NAME = re.compile(r"[a-z0-9][a-z0-9_:-]*(?:[./][a-z0-9][a-z0-9_:-]*)*")
SKILL_BYTES = 64 * 1024
SELECTION_BYTES = 16 * 1024
RULES_BYTES = 256 * 1024


def _path_reason(path: Path) -> str:
    return "symlink" if paths.has_symlink(path) else "outside"


@lru_cache(maxsize=1)
def _selection_contract():
    return schema.load_contract(Path(schema.__file__).resolve().parents[3] / "schemas" / "skill-selection" / "v1")


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
            if any(mark in part for mark in "*?[") or part in ("..", "") or part.startswith("/"):
                break  # only folders inside the project are walked
            fixed.append(part)
        for depth in range(1, len(fixed) + 1):
            folders.add(Path(*fixed[:depth]))
    lines, size = [], 0
    for folder in sorted(folders, key=lambda path: (len(path.parts), str(path))):
        carrier = next((self.project / folder / name for name in ("CLAUDE.md", "AGENTS.md")
                        if (self.project / folder / name).exists() or (self.project / folder / name).is_symlink()), None)
        if carrier is None:
            continue
        try:
            resolved = paths.contained(carrier, [self.project])
            if resolved is None:
                raise ValueError(_path_reason(carrier))
            text = paths.read_capped(resolved, RULES_BYTES)
        except (OSError, ValueError) as error:
            reason = str(error) if isinstance(error, ValueError) else _path_reason(carrier)
            self.progress.emit("info", item=item.ref, role=role, reason_code="RULES_PATH_INVALID",
                               message=f"repository rules {carrier} left out of the {role} prompt: {reason}")
            continue
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
    # Prompt arguments are evaluated names first, texts second. Keep the same list so a file rejected on the
    # second read is removed from the pending prompt's names too, rather than falling back to provider loading.
    return self._skill_set(item, role)["names"]


def auto_skills(self, item: Item, role: str) -> dict:
    """``{"skills": [{name, id, path, reason, tokens, digest, skill_md_sha256}], "excluded", "discoverable", "tokens"}`` of the skills bridge
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
    result = self._skill_set(item, role)
    found = []
    for skill in _checked_candidates(self, item, role, result["names"]):
        if skill.get("reason"):
            _exclude_path(self, item, role, result, skill)
        else:
            found.append((skill["name"], skill["id"], skill["path"]))
    return found


def skill_body(path: Path) -> str:
    """The text of a ``SKILL.md`` without its front matter; never cut."""
    try:
        return _body(paths.read_capped(path, SKILL_BYTES))
    except ValueError as error:
        # The scout fingerprint's legacy reader treats OSError as unavailable. A file that grows or changes
        # encoding between its path check and that read must not crash it; prompt assembly checks it again.
        raise OSError(str(error)) from None


def _body(body: str) -> str:
    if body.startswith("---"):
        end = body.find("\n---", 3)
        body = body[end + 4:] if end != -1 else body
    return body.strip()


def _candidate_paths(self, item: Item, role: str):
    """Preserve the three-tuple file API, keeping validation details private to this module."""
    names = item.options["skills"].get(role, [])
    if names == [opts.AUTO_SKILLS]:
        for row in self._auto_skills(item, role)["skills"]:
            skill = {"name": row["name"], "id": row.get("id") or row["name"], "path": None,
                     "auto": True, "expected": row.get("skill_md_sha256")}
            raw = row.get("path")
            path = Path(raw) if isinstance(raw, str) and raw else None
            if path is None or not path.is_absolute() or path.name != "SKILL.md":
                skill["reason"] = "outside"
            else:
                try:
                    if paths.has_symlink(path):
                        raise ValueError("symlink")
                    if raw != str(path.resolve(strict=True)):
                        raise ValueError("outside")
                    skill.update(path=path, roots=[path.parent])
                except (OSError, RuntimeError, ValueError) as error:
                    skill["reason"] = str(error) if isinstance(error, ValueError) else _path_reason(path)
            yield skill
        return
    for name in names:
        skill = {"name": name, "id": name, "path": None, "auto": False}
        if not SKILL_NAME.fullmatch(name):  # defence for callers with already-merged options
            yield dict(skill, reason="outside")
            continue
        for folder in (".claude/skills", ".agents/skills"):
            root = self.project / folder
            path = root / name / "SKILL.md"
            if not path.exists() and not paths.has_symlink(path):
                continue
            resolved = paths.contained(path, [root])
            if resolved is None:
                skill["reason"] = _path_reason(path)
            else:
                skill.update(path=resolved, roots=[root])
            break
        yield skill


def _checked_candidates(self, item: Item, role: str, names=None):
    """Read a bounded candidate once, verifying exactly the bytes used for its body and auto digest."""
    for skill in _candidate_paths(self, item, role):
        if names is not None and skill["name"] not in names:
            continue
        skill.update(selection={}, body="")
        path = skill["path"]
        if skill.get("reason") or path is None:
            yield skill
            continue
        try:
            text = paths.read_capped(path, SKILL_BYTES)
            if skill["auto"] and not skill["expected"]:
                raise ValueError("digest_missing")
            if skill["auto"] and hashlib.sha256(text.encode("utf-8")).hexdigest() != skill["expected"]:
                raise ValueError("digest_mismatch")
            skill["body"] = _body(text)
            sidecar = path.parent / "selection.json"
            if sidecar.exists() or sidecar.is_symlink():
                resolved = paths.contained(sidecar, skill["roots"])
                if resolved is None:
                    raise ValueError(_path_reason(sidecar))
                text = paths.read_capped(resolved, SELECTION_BYTES)
                try:
                    selection = json.loads(text)
                except (ValueError, RecursionError):
                    raise ValueError("selection_invalid") from None
                registry, kind = _selection_contract()
                if schema.validate(selection, kind, registry):
                    raise ValueError("selection_invalid")
                skill["selection"] = selection
        except (OSError, ValueError) as error:
            skill["reason"] = str(error) if isinstance(error, ValueError) else _path_reason(path)
        yield skill


def _exclude_path(self, item: Item, role: str, result: dict, skill: dict) -> None:
    row = {"id": skill["id"], "reason": skill["reason"]}
    result["names"][:] = [name for name in result["names"] if name != skill["name"]]
    if row not in result["excluded"]:
        result["excluded"].append(row)
        self.progress.emit("info", item=item.ref, role=role, reason_code="SKILL_PATH_INVALID",
                           message=f"skill {skill['id']} ({skill['name']}) left out of the {role} prompt: {skill['reason']}")


def route_tools(route: Optional[dict]) -> Optional[set]:
    """The tools a route names with ``--tools`` (``--tools ""`` is none); None when the route names no list."""
    argv = (route or {}).get("argv") or []
    if "--tools" not in argv[:-1]:
        return None
    return {tool for tool in str(argv[argv.index("--tools") + 1]).split(",") if tool}


def file_tools_rule(self, item: Item) -> bool:
    """Whether the executor prompt tells the model to use the file tools instead of Bash for reading and editing
    (``instructions.file_tools_rule``, and the route offers Read and Edit)."""
    if not item.options["instructions"].get("file_tools_rule", True):
        return False
    return {"Read", "Edit"} <= (self._route_tools(item.routes.get("executor")) or set())


def write_protected(self, item: Item) -> list:
    """The write-set patterns of the piece that the provider of its executor route refuses to write without a prompt
    (``policies.protected_writes``); the executor prompt names them and where their content goes instead."""
    route = item.routes.get("executor") or {}
    return protected_writes.protected(route.get("provider", ""), route.get("argv"),
                                      (item.input_doc.get("scope") or {}).get("write_set"))


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
        # Cached semantic verdicts never waive path, size, encoding or auto-integrity checks on a later read.
        for skill in _checked_candidates(self, item, role, kept[role]["names"]):
            if skill.get("reason"):
                _exclude_path(self, item, role, kept[role], skill)
        return kept[role]
    weigh = role in item.options["instructions"]["isolate_roles"]  # only an isolated role gets the text in its prompt
    candidates, result = [], {"names": [], "excluded": []}
    for skill in _checked_candidates(self, item, role):
        if skill.get("reason"):
            _exclude_path(self, item, role, result, skill)
            continue
        tokens = prompts.estimate_tokens(skill["body"]) if weigh and skill["path"] is not None else None
        candidates.append({"name": skill["name"], "id": skill["id"], "selection": skill["selection"], "tokens": tokens})
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
    result["names"] = [skill["name"] for skill in survivors]
    result["excluded"] += [{"id": row["id"], "reason": row["reason"]} for row in rows]
    kept[role] = result
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
    result = self._skill_set(item, role)
    texts = {}
    for skill in _checked_candidates(self, item, role, result["names"]):
        if skill.get("reason"):
            _exclude_path(self, item, role, result, skill)
        elif skill["path"] is not None:
            texts[skill["name"]] = skill["body"]
    return texts
