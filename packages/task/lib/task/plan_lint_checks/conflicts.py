"""Canon-conflict and git-baseline checks for plan-lint."""
from hashlib import sha256
import json

from .common import *
from .policy import *
from .parsing import *
from .engine import *


SKILL_RELPATH = Path("packages/skiller/skills/general/plan-protocol/SKILL.md")
RUNTIME_SKILL_RELPATH = Path("packages/task/runtime/plan-protocol/SKILL.md")
RUNTIME_PROVENANCE_RELPATH = Path("packages/task/runtime/plan-protocol/provenance.json")


def _find_skill():
    """Find canon SSOT or his digest-locked packaged projection.

    In monorepo, priority remains with handwritten canon `packages/skiller`.
    Standalone Task can only read its own generated projection with exact
    provenance-pair; arbitrary sibling/cache search is intentionally missing.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / SKILL_RELPATH
        if candidate.is_file():
            return candidate
    for parent in here.parents:
        runtime = parent / RUNTIME_SKILL_RELPATH
        provenance = parent / RUNTIME_PROVENANCE_RELPATH
        if not runtime.is_file() or not provenance.is_file():
            continue
        try:
            payload = json.loads(provenance.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        expected = {
            "canonical_source": SKILL_RELPATH.as_posix(),
            "canonical_sha256": "sha256:" + sha256(runtime.read_bytes()).hexdigest(),
        }
        if payload == expected:
            return runtime
        return None
    return None


# Compatibility aliases for consumers of the former helper names. The resolved carrier is
# still the EN-only SKILL.md; new code uses `_find_skill`/`SKILL_RELPATH`.
SKILL_RU_RELPATH = SKILL_RELPATH
_find_skill_ru = _find_skill


def _own_const_lineno(name):
    """Declaration line `NAME = …` in one of bounded implementation modules —
    self-referential reception `test_canon_literals.py`: `--conflicts` does not start a second registry
    «where what is declared», reads the modules themselves."""
    for source in sorted(Path(__file__).parent.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name):
                return node.lineno
    return None


PLAN_LINT_PUBLIC_PATH = Path(__file__).resolve().parents[1] / "plan_lint.py"


def _fence_content(lines, open_idx):
    """Contents ``` fence, open at 0-index row `open_idx`. Returns
    (content_lines, first_content_lineno) — 1-index line of the first line inside the fens."""
    content = []
    i = open_idx + 1
    while i < len(lines) and not CODE_FENCE_RE.match(lines[i]):
        content.append(lines[i])
        i += 1
    return content, open_idx + 2


def _find_line(lines, needle, start=0):
    """Index of the first line containing `needle` (0-index), or `None`."""
    for i in range(start, len(lines)):
        if needle in lines[i]:
            return i
    return None


NEXT_FORM_TABLE_ROW_RE = re.compile(r"^\|\s*([a-z-]+):")
CONTEXT_BULLET_RE = re.compile(r"^-\s+\*\*`([^`]+)`\*\*")


def _conflicts_statuses(skill_lines, skill_path, diag):
    """Class 1/6: six canonical statuses (STATUSES) — SKILL.md §6."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_STATUSES)
    if header_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts statuses: anchor not found «{CONFLICTS_ANCHOR_STATUSES}» "
                   "(SKILL.md §6) — reconciliation impossible")
        return
    fence_idx = _find_line(skill_lines, "```text", header_idx)
    if fence_idx is None:
        diag.error(skill_path, header_idx + 1,
                   "--conflicts statuses: codefence after anchor not found")
        return
    content, content_lineno = _fence_content(skill_lines, fence_idx)
    canon_statuses = tuple(ln for ln in content if ln.strip())
    code_lineno = _own_const_lineno("STATUSES")
    if canon_statuses != STATUSES:
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts statuses: canon {skill_path.name}:{content_lineno} = "
                   f"{canon_statuses!r} → implementation plan_lint.py:{code_lineno} = "
                   f"{STATUSES!r}")


def _conflicts_item_fields(skill_lines, skill_path, diag):
    """Class 2/6: 16 fields item'a and their order (REQUIRED_ITEM_FIELDS) — SKILL.md §5."""
    anchor_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_ITEM_FIELDS)
    if anchor_idx is None:
        # Compact canon deliberately routes the detailed carrier schema to the
        # reference instead of duplicating all 16 names in SKILL.md.  Follow that
        # pointer; treating compaction as schema removal made the consumer red
        # while the canonical source was still complete.
        reference = skill_path.parent / "references" / "plan-layout-v2.md"
        try:
            reference_text = reference.read_text(encoding="utf-8")
        except OSError:
            diag.error(reference, None,
                       "--conflicts 16-fields: compact canon reference not readable")
            return
        spec = re.search(r"The v2 item spec contains exactly the stable fields:\s*\n\s*`([^`]+)`",
                         reference_text)
        state = re.search(r"The generated state contains exactly:\s*\n\s*`([^`]+)`",
                          reference_text)
        if not spec or not state:
            diag.error(reference, None,
                       "--conflicts 16-fields: reference does not carry both exact field lists")
            return
        spec_fields = tuple(part.strip() for part in spec.group(1).split(","))
        state_fields = tuple(part.strip() for part in state.group(1).split(","))
        canon_fields = state_fields[:1] + spec_fields + state_fields[1:]
        canon_ref = reference
        canon_lineno = reference_text[:spec.start()].count("\n") + 1
    else:
        joined = " ".join(skill_lines[anchor_idx + 1:anchor_idx + 4])
        m = re.search(r"`([^`]+)`", joined)
        if not m:
            diag.error(skill_path, anchor_idx + 2,
                       "--conflicts 16-fields: backtick list after anchor not found")
            return
        normalized = re.sub(r"\s+", " ", m.group(1)).strip()
        canon_fields = tuple(f.strip() for f in normalized.split(","))
        canon_ref = skill_path
        canon_lineno = anchor_idx + 2
    code_lineno = _own_const_lineno("REQUIRED_ITEM_FIELDS")
    if canon_fields != REQUIRED_ITEM_FIELDS:
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts 16-fields: canon {canon_ref.name}:{canon_lineno} = "
                   f"{canon_fields!r} → implementation plan_lint.py:{code_lineno} = "
                   f"{REQUIRED_ITEM_FIELDS!r}")


def _conflicts_next_forms(skill_lines, skill_path, diag):
    """Class 3/7: closed `Next` enum — SKILL.md §6 ↔
    alternation `SEMANTIC_NEXT_RE` (is read by her herself - not republished in a second list)."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_NEXT_FORMS)
    if header_idx is None:
        compact_idx = _find_line(skill_lines, "Semantic Next is one of")
        if compact_idx is None:
            diag.error(skill_path, None,
                       "--conflicts forms Next: compact enum not found")
            return
        compact = " ".join(skill_lines[compact_idx:compact_idx + 4])
        canon_forms = re.findall(r"`([a-z][a-z-]+)`", compact.split(";", 1)[0])
        canon_lineno = compact_idx + 1
    else:
        canon_forms = []
        canon_lineno = None
        i = header_idx + 1
        while i < len(skill_lines) and skill_lines[i].strip().startswith("|"):
            m = NEXT_FORM_TABLE_ROW_RE.match(skill_lines[i].strip())
            if m:
                if canon_lineno is None:
                    canon_lineno = i + 1
                canon_forms.append(m.group(1))
            i += 1
    code_lineno = _own_const_lineno("SEMANTIC_NEXT_RE")
    gm = re.search(r"\^\((.*?)\):", SEMANTIC_NEXT_RE.pattern)
    code_forms = gm.group(1).split("|") if gm else []
    if tuple(canon_forms) != tuple(code_forms):
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts forms Next: canon {skill_path.name}:{canon_lineno} = "
                   f"{canon_forms!r} → implementation plan_lint.py:{code_lineno} = "
                   f"{tuple(code_forms)!r}")


def _conflicts_context_values(skill_lines, skill_path, diag):
    """Class 4/7: three layout-v2 `Context` values — SKILL.md §6 ↔
    discipline». The only class where the implementation BEFORE this item'and did not exist at all
    (see comment `CONTEXT_VALUES`) — new verification, not a reissue of the old one."""
    anchor_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_CONTEXT)
    if anchor_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts Context: anchor not found «{CONFLICTS_ANCHOR_CONTEXT}» "
                   "(SKILL.md §8)")
        return
    canon_values = []
    canon_lineno = None
    for i in range(anchor_idx + 1, min(anchor_idx + 20, len(skill_lines))):
        m = CONTEXT_BULLET_RE.match(skill_lines[i])
        if m:
            if canon_lineno is None:
                canon_lineno = i + 1
            canon_values.append(m.group(1))
            if len(canon_values) == 3:
                break
    code_lineno = _own_const_lineno("CONTEXT_VALUES")
    if tuple(canon_values) != CONTEXT_VALUES:
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts Context: canon {skill_path.name}:{canon_lineno} = "
                   f"{canon_values!r} → implementation plan_lint.py:{code_lineno} = "
                   f"{CONTEXT_VALUES!r}")


def _conflicts_i18n_literals(skill_text, skill_lines, skill_path, diag):
    """Class 5/7: `i18n-keep` literals declared in the EN-only canon.
    EN-only SKILL.md (T2 `test_canon_literals.py` checks the same thing; here - the same
    predicate accessible from CLI without starting unittest, Required Reads p. 4 «is expanding, not
    duplicated»: both sides read the same `CANON_LITERALS`/`I18N_KEEP_RE`)."""
    declared = set(I18N_KEEP_RE.findall(skill_text))
    code_lineno = _own_const_lineno("CANON_LITERALS")
    public_module = sys.modules.get("task.plan_lint")
    literals = getattr(public_module, "CANON_LITERALS", CANON_LITERALS)
    for lit in literals:
        if lit in declared:
            continue
        found_idx = _find_line(skill_lines, lit)
        canon_ref = (f"{skill_path.name}:{found_idx + 1} (found in body, WITHOUT directive "
                    f"`i18n-keep`)" if found_idx is not None
                    else f"{skill_path.name}: not found anywhere")
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts i18n-keep: literal «{lit}» — canon {canon_ref} → implementation "
                   f"plan_lint.py:{code_lineno} carries it to CANON_LITERALS without "
                   f"directives `<!-- i18n-keep: {lit} -->`")


def _conflicts_launch_table_regex(skill_lines, skill_path, diag):
    """Class 6/7: canonical launch metadata stays tabular; command stays fenced."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_LAUNCH_TABLE)
    if header_idx is None:
        snippet = skill_path.parent / "snippets" / "launch-block-template.md"
        try:
            source_lines = snippet.read_text(encoding="utf-8").splitlines()
        except OSError:
            diag.error(snippet, None,
                       "--conflicts launch-block regex: canonical snippet not readable")
            return
        header_idx = _find_line(source_lines, CONFLICTS_ANCHOR_LAUNCH_TABLE)
        if header_idx is None:
            diag.error(snippet, None,
                       f"--conflicts launch-block regex: header not found "
                       f"«{CONFLICTS_ANCHOR_LAUNCH_TABLE}»")
            return
        skill_lines, skill_path = source_lines, snippet
    rows = []
    i = header_idx + 1
    while i < len(skill_lines) and skill_lines[i].strip().startswith("|"):
        rows.append((skill_lines[i], i + 1))
        i += 1
    if not any(LAUNCH_TABLE_ROW_RE.match(row) for row, _ln in rows):
        code_lineno = _own_const_lineno("LAUNCH_TABLE_ROW_RE")
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts launch-block regex: LAUNCH_TABLE_ROW_RE does not match any "
                   f"canon-table row {skill_path.name}:{header_idx + 2}-{i} "
                   f"(expected string «Model class») → implementation "
                   f"plan_lint.py:{code_lineno}")
    command_rows = [(row, lineno) for row, lineno in rows if LAUNCH_COMMAND_ROW_RE.match(row)]
    if command_rows:
        code_lineno = _own_const_lineno("LAUNCH_COMMAND_ROW_RE")
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts launch-block form: canon {skill_path.name}:"
                   f"{command_rows[0][1]} carries again `| Command |` in metadata table; "
                   f"LAUNCH_COMMAND_ROW_RE only remains reader-side compatibility → "
                   f"implementation plan_lint.py:{code_lineno}")
    label_idx = _find_line(skill_lines, "**Provider-native command:**", start=i)
    fence_idx = None if label_idx is None else next(
        (index for index in range(label_idx + 1, len(skill_lines))
         if re.fullmatch(r"\s*```(?:bash|text|sh|shell)\s*", skill_lines[index])), None)
    if fence_idx is None:
        code_lineno = _own_const_lineno("CODE_FENCE_RE")
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts launch-block form: canonical snippet {skill_path.name} "
                   f"does not carry `**Provider-native command:**` + fenced command block → "
                   f"implementation plan_lint.py:{code_lineno}")


def _conflicts_layout_v2(skill_lines, skill_path, diag):
    """Class 7/7: the compact canon must route layout-v2 readers to its carrier contract."""
    anchor_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_LAYOUT_V2)
    if anchor_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts layout v2: missing anchor «{CONFLICTS_ANCHOR_LAYOUT_V2}»")
        return
    window = "\n".join(skill_lines[anchor_idx:anchor_idx + 20])
    for carrier in ("phases/<Pn>/<Pn.m>.md", "phases/<Pn>/<Pn.m>.state.md",
                    "bundles/<Pn.m>.json", "phases/<Pn>/<Pn>.closed.md"):
        if carrier not in window:
            diag.error(skill_path, anchor_idx + 1,
                       f"--conflicts layout v2: anchor block lacks carrier «{carrier}»")


def run_conflicts_check(diag):
    """`--conflicts`: canon reconciliation↔six-class implementation.

    Absence canon SSOT — error: green reconciliation without source would be vacuous pass.
    """
    skill_path = _find_skill()
    if skill_path is None:
        diag.error(SKILL_RELPATH, None,
                   "--conflicts: SKILL.md (canon plan-protocol) not found from "
                   "plan_lint.py up - reconciliation impossible")
        return
    skill_lines = _read_lines(skill_path)
    skill_text = skill_path.read_text(encoding="utf-8")
    _conflicts_statuses(skill_lines, skill_path, diag)
    _conflicts_item_fields(skill_lines, skill_path, diag)
    _conflicts_next_forms(skill_lines, skill_path, diag)
    _conflicts_context_values(skill_lines, skill_path, diag)
    _conflicts_i18n_literals(skill_text, skill_lines, skill_path, diag)
    _conflicts_launch_table_regex(skill_lines, skill_path, diag)
    _conflicts_layout_v2(skill_lines, skill_path, diag)


# --- --baseline: deterministic count of new errors ---------

def _git_run(args, cwd, timeout=15):
    """`check=False`, intercepts `FileNotFoundError`/timeout - linter must
    work outside git-repo (are driving around Brain-vault'from other people's roots, Implementation
    Rules). None — command did not execute at all (no git / timeout)."""
    try:
        return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                               timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _baseline_diag_keys(root, ref):
    """Drives away lint in detached worktree `ref` for the same `root`-paths. Returns
    `(normalized_keys, None)` or `(None, reason)` if unavailable baseline —
    graceful degrade (git missing / is not a repository / ref not found / worktree not available)."""
    root = Path(root).resolve()

    proc = _git_run(["rev-parse", "--show-toplevel"], cwd=root)
    if proc is None or proc.returncode != 0:
        return None, "not git-repository (or git not installed)"
    git_root = Path(proc.stdout.decode("utf-8", "replace").strip())

    try:
        relpath = root.relative_to(git_root)
    except ValueError:
        return None, f"path «{root}» out git-repository «{git_root}»"

    verify = _git_run(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=git_root)
    if verify is None or verify.returncode != 0:
        return None, f"ref «{ref}» not found"

    with tempfile.TemporaryDirectory(prefix="plan-lint-baseline-") as tmp:
        baseline_repo = Path(tmp) / "repo"
        checkout = _git_run(
            ["worktree", "add", "--detach", "--quiet", str(baseline_repo), ref],
            cwd=git_root,
            timeout=30,
        )
        if checkout is None or checkout.returncode != 0:
            detail = "" if checkout is None else checkout.stderr.decode("utf-8", "replace").strip()
            return None, f"«git worktree add --detach {ref}» failed: {detail or 'unknown error'}"
        try:
            baseline_root = baseline_repo / relpath
            baseline_dirs = discover_plan_dirs(baseline_root)
            if not baseline_root.exists() or baseline_dirs is None:
                return None, f"path «{relpath}» missing from «{ref}» (new plan?)"

            baseline_diag = Diagnostics()
            models = {}
            for plan_dir in baseline_dirs:
                models[plan_dir.name] = lint_plan(plan_dir, baseline_diag)
            is_root = not (baseline_root / "plan.md").is_file()
            if is_root:
                lint_plans_root(baseline_root, models, baseline_diag)

            return baseline_diag.normalized_keys(baseline_root), None
        finally:
            _git_run(["worktree", "remove", "--force", str(baseline_repo)],
                     cwd=git_root, timeout=30)


# --- CLI ----------------------------------------------------------------------

__all__ = tuple(name for name in globals() if not name.startswith("__"))
