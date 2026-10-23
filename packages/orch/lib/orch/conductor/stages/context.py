"""What an isolated role still needs to know: the rules of the repository instructions for its write set and the
skills of its prompt (named, or chosen by the skills bridge, then checked). The steps are ``orch.conductor.context``
(discover, validate, select, snapshot, rules); this module binds them to the conductor and keeps their effects: the
progress lines, the Stops and the cache in the state of the piece."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from orch.conductor import options as opts
from orch.conductor.context import discover, rules as rules_step, select, snapshot, validate
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.policies import protected_writes


def repo_rules(self, item: Item, role: str) -> str:
    """The instruction sections of ``instructions.module_rules`` from the CLAUDE.md (else AGENTS.md) of the
    repository root and of every folder on the way to a write-set path. An isolated role does not read those
    files, and the rest of them are the rules of a developer's session, not of this role."""
    wanted = item.options["instructions"].get("module_rules") or []
    if not wanted:
        return ""
    write_set = (item.input_doc.get("scope") or {}).get("write_set") or []
    carriers, skipped = validate.rule_texts(self.project, discover.rule_carriers(self.project, write_set))
    for row in skipped:
        self.progress.emit("info", item=item.ref, role=role, reason_code="RULES_PATH_INVALID",
                           message=f"repository rules {row.path} left out of the {role} prompt: {row.reason}")
    return rules_step.module_rules(carriers, wanted, lambda path: self._relative(path))["text"]


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
    answer = discover.bridge_selection(argv, self.project, self.env)
    if answer.chosen is None:
        raise Stop("SKILLS_SELECT_FAILED", f"skills bridge for {role}{answer.failure}")
    chosen = answer.chosen
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
    found = discover.work_paths(self.project, patterns)
    if found.owned > 300:
        self.progress.emit("info", item=item.ref, reason_code="SKILLS_PATHS_CUT",
                           message=f"write set owns {found.owned} files; the first 300 choose the skills")
    return found.paths


def skill_files(self, item: Item, role: str) -> list:
    """``[(name, id, SKILL.md path or None)]`` of the skills a role is given: the skill folders of the project for a
    list of names, the file the bridge named for ``["auto"]`` (its ``id`` is the bridge id, else the name)."""
    result = self._skill_set(item, role)
    found, rejected = snapshot.skill_files(_checked_candidates(self, item, role, result["names"]))
    for skill in rejected:
        _exclude_path(self, item, role, result, skill)
    return found


def skill_body(path: Path) -> str:
    """The text of a ``SKILL.md`` without its front matter; never cut."""
    return snapshot.read_body(path)


def _checked_candidates(self, item: Item, role: str, names=None):
    """The candidates of a role, each read once and checked; the skills the bridge named are asked for here."""
    listed = item.options["skills"].get(role, [])
    if listed == [opts.AUTO_SKILLS]:
        candidates = discover.auto_candidates(self._auto_skills(item, role)["skills"])
    else:
        candidates = discover.skill_candidates(self.project, listed)
    return validate.checked(candidates, names)


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
    """``{"names", "excluded"}``: the skills a role keeps after the checks of ``policies.skills.check_skills`` (what each
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
        candidates.append(select.candidate(skill, weigh))
    budget = int(item.options.get("limits", {}).get("skill_tokens_max", opts.DEFAULT_LIMITS["skill_tokens_max"]))
    chosen = select.select_skills(candidates, tools=self._route_tools(item.routes.get(role)), budget=budget)
    if chosen.conflict:
        first, second = chosen.conflict
        raise Stop("PROMPT_CONFLICT", f"skills {first['id']} and {second['id']} of {role} declare a conflict in their "
                   "selection.json; list only one of them for the role")
    for row in chosen.rows:
        self.progress.emit("info", item=item.ref, role=role, reason_code="SKILL_EXCLUDED",
                           message=f"skill {row['id']} left out of the {role} prompt: {row['reason']}"
                           + (f" ({row['detail']})" if row["detail"] else ""))
    result["names"] = chosen.names
    result["excluded"] += chosen.excluded
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
    found = snapshot.skill_texts(_checked_candidates(self, item, role, result["names"]))
    for skill in found.rejected:
        _exclude_path(self, item, role, result, skill)
    return found.texts
