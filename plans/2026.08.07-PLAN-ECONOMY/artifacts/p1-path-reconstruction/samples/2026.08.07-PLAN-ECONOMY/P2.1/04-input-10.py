GREEN = "GREEN"
ATTENTION = "ATTENTION"
RED = "RED"
_RANK = {RED: 0, ATTENTION: 1, GREEN: 2}

# Плановая бухгалтерия (`plan.md` §2, D75) — ТОЛЬКО bookkeeping-коммит, даже если
# названа в `Files`. Всё остальное внутри `plans/<ID>/**` (артефакты) и всё вне
# `plans/<ID>/**` — «Scope»-класс для целей детекта бандла (D104), Files не читается.
_BOOKKEEPING_LEAVES = ("plan.md", "handoff.md", "index.md", "open-questions.md",
                       "journal.jsonl", "roadmap.md")
_BOOKKEEPING_DIRS = ("phases/", "closure/")
_BOOKKEEPING_ROOT_FILE = "plans/ACTIVE.md"

def _is_bookkeeping(rel_path, plan_rel):
    if rel_path == _BOOKKEEPING_ROOT_FILE:
        return True
    prefix = plan_rel + "/"
    if not rel_path.startswith(prefix):
        return False
    sub = rel_path[len(prefix):]
    return sub in _BOOKKEEPING_LEAVES or sub.startswith(_BOOKKEEPING_DIRS)

        raise GateUnavailable(f"git log не выполнился: {log.stderr.strip()}")
    commits = [ln for ln in log.stdout.splitlines() if ln.strip()]

    union_paths = set()
    bundle = False
    for commit in commits:
        paths = _changed_paths(commit, git_root, timeout=timeout)
        union_paths.update(paths)
        has_bookkeeping = any(_is_bookkeeping(p, plan_rel) for p in paths)
        has_scope = any(not _is_bookkeeping(p, plan_rel) for p in paths)
        if has_bookkeeping and has_scope:
            bundle = True

    required = {f"{plan_rel}/plan.md", f"{plan_rel}/phases/{phase_id}.md",
                f"{plan_rel}/handoff.md"}
    missing = sorted(required - union_paths)

    return {
