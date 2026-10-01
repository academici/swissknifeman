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
    """Найти canon SSOT либо его digest-locked packaged projection.

    В монорепо приоритет остаётся за handwritten canon `packages/skiller`.
    Standalone Task может читать только собственную generated projection с точной
    provenance-парой; произвольный sibling/cache search намеренно отсутствует.
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
    """Строка объявления `NAME = …` в одном из bounded implementation modules —
    self-referential приём `test_canon_literals.py`: `--conflicts` не заводит второй реестр
    «где что объявлено», читает сами модули."""
    for source in sorted(Path(__file__).parent.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name):
                return node.lineno
    return None


PLAN_LINT_PUBLIC_PATH = Path(__file__).resolve().parents[1] / "plan_lint.py"


def _fence_content(lines, open_idx):
    """Содержимое ``` fence, открытого на 0-индексной строке `open_idx`. Возвращает
    (content_lines, first_content_lineno) — 1-индексная строка первой строки внутри фенса."""
    content = []
    i = open_idx + 1
    while i < len(lines) and not CODE_FENCE_RE.match(lines[i]):
        content.append(lines[i])
        i += 1
    return content, open_idx + 2


def _find_line(lines, needle, start=0):
    """Индекс первой строки, содержащей `needle` (0-индексный), либо `None`."""
    for i in range(start, len(lines)):
        if needle in lines[i]:
            return i
    return None


NEXT_FORM_TABLE_ROW_RE = re.compile(r"^\|\s*([a-z-]+):")
CONTEXT_BULLET_RE = re.compile(r"^-\s+\*\*`([^`]+)`\*\*")


def _conflicts_statuses(skill_lines, skill_path, diag):
    """Класс 1/6: шесть канонических статусов (STATUSES) — SKILL.md §6."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_STATUSES)
    if header_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts статусы: не найден якорь «{CONFLICTS_ANCHOR_STATUSES}» "
                   "(SKILL.md §6) — сверка невозможна")
        return
    fence_idx = _find_line(skill_lines, "```text", header_idx)
    if fence_idx is None:
        diag.error(skill_path, header_idx + 1,
                   "--conflicts статусы: код-фенс после якоря не найден")
        return
    content, content_lineno = _fence_content(skill_lines, fence_idx)
    canon_statuses = tuple(ln for ln in content if ln.strip())
    code_lineno = _own_const_lineno("STATUSES")
    if canon_statuses != STATUSES:
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts статусы: канон {skill_path.name}:{content_lineno} = "
                   f"{canon_statuses!r} → реализация plan_lint.py:{code_lineno} = "
                   f"{STATUSES!r}")


def _conflicts_item_fields(skill_lines, skill_path, diag):
    """Класс 2/6: 16 полей item'а и их порядок (REQUIRED_ITEM_FIELDS) — SKILL.md §5."""
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
                       "--conflicts 16-полей: compact canon reference не читается")
            return
        spec = re.search(r"The v2 item spec contains exactly the stable fields:\s*\n\s*`([^`]+)`",
                         reference_text)
        state = re.search(r"The generated state contains exactly:\s*\n\s*`([^`]+)`",
                          reference_text)
        if not spec or not state:
            diag.error(reference, None,
                       "--conflicts 16-полей: reference не несёт обе exact field lists")
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
                       "--conflicts 16-полей: бэктик-список после якоря не найден")
            return
        normalized = re.sub(r"\s+", " ", m.group(1)).strip()
        canon_fields = tuple(f.strip() for f in normalized.split(","))
        canon_ref = skill_path
        canon_lineno = anchor_idx + 2
    code_lineno = _own_const_lineno("REQUIRED_ITEM_FIELDS")
    if canon_fields != REQUIRED_ITEM_FIELDS:
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts 16-полей: канон {canon_ref.name}:{canon_lineno} = "
                   f"{canon_fields!r} → реализация plan_lint.py:{code_lineno} = "
                   f"{REQUIRED_ITEM_FIELDS!r}")


def _conflicts_next_forms(skill_lines, skill_path, diag):
    """Class 3/7: closed `Next` enum — SKILL.md §6 ↔
    альтернация `SEMANTIC_NEXT_RE` (читается у неё самой — не переиздаётся вторым списком)."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_NEXT_FORMS)
    if header_idx is None:
        compact_idx = _find_line(skill_lines, "Semantic Next is one of")
        if compact_idx is None:
            diag.error(skill_path, None,
                       "--conflicts формы Next: compact enum не найден")
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
                   f"--conflicts формы Next: канон {skill_path.name}:{canon_lineno} = "
                   f"{canon_forms!r} → реализация plan_lint.py:{code_lineno} = "
                   f"{tuple(code_forms)!r}")


def _conflicts_context_values(skill_lines, skill_path, diag):
    """Class 4/7: three layout-v2 `Context` values — SKILL.md §6 ↔
    discipline». Единственный класс, где реализация ДО этого item'а не существовала вовсе
    (см. комментарий у `CONTEXT_VALUES`) — сверка новая, не переиздание старой."""
    anchor_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_CONTEXT)
    if anchor_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts Context: не найден якорь «{CONFLICTS_ANCHOR_CONTEXT}» "
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
                   f"--conflicts Context: канон {skill_path.name}:{canon_lineno} = "
                   f"{canon_values!r} → реализация plan_lint.py:{code_lineno} = "
                   f"{CONTEXT_VALUES!r}")


def _conflicts_i18n_literals(skill_text, skill_lines, skill_path, diag):
    """Class 5/7: `i18n-keep` literals declared in the EN-only canon.
    EN-only SKILL.md (T2 `test_canon_literals.py` проверяет то же самое; здесь — тот же
    предикат, доступный из CLI без запуска unittest, Required Reads п. 4 «расширяется, не
    дублируется»: обе стороны читают один и тот же `CANON_LITERALS`/`I18N_KEEP_RE`)."""
    declared = set(I18N_KEEP_RE.findall(skill_text))
    code_lineno = _own_const_lineno("CANON_LITERALS")
    public_module = sys.modules.get("task.plan_lint")
    literals = getattr(public_module, "CANON_LITERALS", CANON_LITERALS)
    for lit in literals:
        if lit in declared:
            continue
        found_idx = _find_line(skill_lines, lit)
        canon_ref = (f"{skill_path.name}:{found_idx + 1} (найден в теле, БЕЗ директивы "
                    f"`i18n-keep`)" if found_idx is not None
                    else f"{skill_path.name}: нигде не найден")
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts i18n-keep: литерал «{lit}» — канон {canon_ref} → реализация "
                   f"plan_lint.py:{code_lineno} несёт его в CANON_LITERALS без "
                   f"директивы `<!-- i18n-keep: {lit} -->`")


def _conflicts_launch_table_regex(skill_lines, skill_path, diag):
    """Class 6/7: canonical launch metadata stays tabular; command stays fenced."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_LAUNCH_TABLE)
    if header_idx is None:
        snippet = skill_path.parent / "snippets" / "launch-block-template.md"
        try:
            source_lines = snippet.read_text(encoding="utf-8").splitlines()
        except OSError:
            diag.error(snippet, None,
                       "--conflicts launch-block регекс: canonical snippet не читается")
            return
        header_idx = _find_line(source_lines, CONFLICTS_ANCHOR_LAUNCH_TABLE)
        if header_idx is None:
            diag.error(snippet, None,
                       f"--conflicts launch-block регекс: не найдена шапка "
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
                   f"--conflicts launch-block регекс: LAUNCH_TABLE_ROW_RE не матчит ни одну "
                   f"строку канон-таблицы {skill_path.name}:{header_idx + 2}-{i} "
                   f"(ожидалась строка «Model class») → реализация "
                   f"plan_lint.py:{code_lineno}")
    command_rows = [(row, lineno) for row, lineno in rows if LAUNCH_COMMAND_ROW_RE.match(row)]
    if command_rows:
        code_lineno = _own_const_lineno("LAUNCH_COMMAND_ROW_RE")
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts launch-block форма: канон {skill_path.name}:"
                   f"{command_rows[0][1]} снова несёт `| Команда |` в metadata table; "
                   f"LAUNCH_COMMAND_ROW_RE остаётся только reader-side compatibility → "
                   f"реализация plan_lint.py:{code_lineno}")
    label_idx = _find_line(skill_lines, "**Provider-native command:**", start=i)
    fence_idx = None if label_idx is None else next(
        (index for index in range(label_idx + 1, len(skill_lines))
         if re.fullmatch(r"\s*```(?:bash|text|sh|shell)\s*", skill_lines[index])), None)
    if fence_idx is None:
        code_lineno = _own_const_lineno("CODE_FENCE_RE")
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts launch-block форма: canonical snippet {skill_path.name} "
                   f"не несёт `**Provider-native command:**` + fenced command block → "
                   f"реализация plan_lint.py:{code_lineno}")


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
    """`--conflicts`: сверка канон↔реализация по шести классам.

    Отсутствие canon SSOT — ошибка: зелёная сверка без источника была бы vacuous pass.
    """
    skill_path = _find_skill()
    if skill_path is None:
        diag.error(SKILL_RELPATH, None,
                   "--conflicts: SKILL.md (canon plan-protocol) не найден от "
                   "plan_lint.py вверх — сверка невозможна")
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


# --- --baseline: детерминированный счёт новых ошибок ---------

def _git_run(args, cwd, timeout=15):
    """`check=False`, перехватывает `FileNotFoundError`/таймаут — линтер обязан
    работать вне git-репо (гоняют по Brain-vault'у и чужим корням, Implementation
    Rules). None — команда не выполнилась вовсе (нет git / таймаут)."""
    try:
        return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                               timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _baseline_diag_keys(root, ref):
    """Прогоняет lint в detached worktree `ref` для того же `root`-пути. Возвращает
    `(normalized_keys, None)` либо `(None, причина)` при недоступности baseline —
    graceful degrade (git отсутствует / не репозиторий / ref не найден / worktree недоступен)."""
    root = Path(root).resolve()

    proc = _git_run(["rev-parse", "--show-toplevel"], cwd=root)
    if proc is None or proc.returncode != 0:
        return None, "не git-репозиторий (или git не установлен)"
    git_root = Path(proc.stdout.decode("utf-8", "replace").strip())

    try:
        relpath = root.relative_to(git_root)
    except ValueError:
        return None, f"путь «{root}» вне git-репозитория «{git_root}»"

    verify = _git_run(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=git_root)
    if verify is None or verify.returncode != 0:
        return None, f"ref «{ref}» не найден"

    with tempfile.TemporaryDirectory(prefix="plan-lint-baseline-") as tmp:
        baseline_repo = Path(tmp) / "repo"
        checkout = _git_run(
            ["worktree", "add", "--detach", "--quiet", str(baseline_repo), ref],
            cwd=git_root,
            timeout=30,
        )
        if checkout is None or checkout.returncode != 0:
            detail = "" if checkout is None else checkout.stderr.decode("utf-8", "replace").strip()
            return None, f"«git worktree add --detach {ref}» не удался: {detail or 'unknown error'}"
        try:
            baseline_root = baseline_repo / relpath
            baseline_dirs = discover_plan_dirs(baseline_root)
            if not baseline_root.exists() or baseline_dirs is None:
                return None, f"путь «{relpath}» отсутствует в «{ref}» (новый план?)"

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
