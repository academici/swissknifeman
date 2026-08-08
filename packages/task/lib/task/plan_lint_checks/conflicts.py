"""Canon-conflict and git-baseline checks for plan-lint."""
from .common import *
from .policy import *
from .parsing import *
from .engine import *


SKILL_RU_RELPATH = Path("packages/skiller/skills/general/plan-protocol/SKILL.ru.md")


def _find_skill_ru():
    """Канон-SSOT (`SKILL.ru.md`), от расположения ЭТОГО модуля вверх до корня монорепо —
    тот же приём, что `test_canon_literals.py::_find_skill_ru` (не дублируется: тест этого
    item'а импортирует функцию отсюда, см. Implementation Rules). Standalone-раскладка
    (пакет `task` вне монорепо) — `None`, не исключение: `run_conflicts_check` предупреждает
    и выходит зелёным (тот же класс деградации, что `core.term.warn`-фолбэк вверху модуля)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / SKILL_RU_RELPATH
        if candidate.is_file():
            return candidate
    return None


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
    """Класс 1/6: шесть канонических статусов (STATUSES) — SKILL.ru.md §6."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_STATUSES)
    if header_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts статусы: не найден якорь «{CONFLICTS_ANCHOR_STATUSES}» "
                   "(SKILL.ru.md §6) — сверка невозможна")
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
    """Класс 2/6: 16 полей item'а и их порядок (REQUIRED_ITEM_FIELDS) — SKILL.ru.md §5."""
    anchor_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_ITEM_FIELDS)
    if anchor_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts 16-полей: не найден якорь «{CONFLICTS_ANCHOR_ITEM_FIELDS}» "
                   "(SKILL.ru.md §5)")
        return
    joined = " ".join(skill_lines[anchor_idx + 1:anchor_idx + 4])
    m = re.search(r"`([^`]+)`", joined)
    if not m:
        diag.error(skill_path, anchor_idx + 2,
                   "--conflicts 16-полей: бэктик-список после якоря не найден")
        return
    normalized = re.sub(r"\s+", " ", m.group(1)).strip()
    canon_fields = tuple(f.strip() for f in normalized.split(","))
    code_lineno = _own_const_lineno("REQUIRED_ITEM_FIELDS")
    if canon_fields != REQUIRED_ITEM_FIELDS:
        diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                   f"--conflicts 16-полей: канон {skill_path.name}:{anchor_idx + 2} = "
                   f"{canon_fields!r} → реализация plan_lint.py:{code_lineno} = "
                   f"{REQUIRED_ITEM_FIELDS!r}")


def _conflicts_next_forms(skill_lines, skill_path, diag):
    """Класс 3/6: закрытый enum форм `Next` — SKILL.ru.md §8 «Допустимые формы Next» ↔
    альтернация `SEMANTIC_NEXT_RE` (читается у неё самой — не переиздаётся вторым списком)."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_NEXT_FORMS)
    if header_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts формы Next: не найдена шапка таблицы "
                   f"«{CONFLICTS_ANCHOR_NEXT_FORMS}»")
        return
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
    """Класс 4/6: три значения `Context` (CONTEXT_VALUES) — SKILL.ru.md §8 «Session-restart
    discipline». Единственный класс, где реализация ДО этого item'а не существовала вовсе
    (см. комментарий у `CONTEXT_VALUES`) — сверка новая, не переиздание старой."""
    anchor_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_CONTEXT)
    if anchor_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts Context: не найден якорь «{CONFLICTS_ANCHOR_CONTEXT}» "
                   "(SKILL.ru.md §8)")
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
    """Класс 5/6: литералы `i18n-keep` — CANON_LITERALS ⊆ директивы, объявленные в
    SKILL.ru.md (T2 `test_canon_literals.py` уже проверяет то же самое; здесь — тот же
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
    """Класс 6/6: регекс-носители формы launch-block'а (LAUNCH_TABLE_ROW_RE/
    LAUNCH_COMMAND_ROW_RE) — обязаны матчить строки канон-таблицы SKILL.ru.md §8."""
    header_idx = _find_line(skill_lines, CONFLICTS_ANCHOR_LAUNCH_TABLE)
    if header_idx is None:
        diag.error(skill_path, None,
                   f"--conflicts launch-block регекс: не найдена шапка "
                   f"«{CONFLICTS_ANCHOR_LAUNCH_TABLE}»")
        return
    rows = []
    i = header_idx + 1
    while i < len(skill_lines) and skill_lines[i].strip().startswith("|"):
        rows.append((skill_lines[i], i + 1))
        i += 1
    checks = (("LAUNCH_TABLE_ROW_RE", LAUNCH_TABLE_ROW_RE, "Model class"),
             ("LAUNCH_COMMAND_ROW_RE", LAUNCH_COMMAND_ROW_RE, "Команда"))
    for const_name, pattern, label in checks:
        matched = any(pattern.match(row) for row, _ln in rows)
        if not matched:
            code_lineno = _own_const_lineno(const_name)
            diag.error(PLAN_LINT_PUBLIC_PATH, code_lineno,
                       f"--conflicts launch-block регекс: {const_name} не матчит ни одну "
                       f"строку канон-таблицы {skill_path.name}:{header_idx + 2}-{i} "
                       f"(ожидалась строка «{label}») → реализация "
                       f"plan_lint.py:{code_lineno}")


def run_conflicts_check(diag):
    """`--conflicts`: сверка канон↔реализация по шести классам (см. блок-докстринг выше),
    без плана на входе. Standalone-раскладка (SKILL.ru.md недоступен) — предупреждает и
    оставляет `diag` зелёным (та же деградация, что `test_canon_literals.py::skipTest`)."""
    skill_path = _find_skill_ru()
    if skill_path is None:
        # `print` напрямую, не `_core_warn` (T1 `test_canon_literals.py` иначе требует
        # регистрации этой прозы как грепаемого литерала — она им не является, это вывод
        # диагностики; `print` — задокументированное исключение T1, см. его же
        # `test_print_argument_is_not_a_grep_site`).
        print("WARN: --conflicts: standalone-раскладка — SKILL.ru.md (канон plan-protocol) "
             "не найден от расположения plan_lint.py вверх — сверка пропущена", file=sys.stderr)
        return
    skill_lines = _read_lines(skill_path)
    skill_text = skill_path.read_text(encoding="utf-8")
    _conflicts_statuses(skill_lines, skill_path, diag)
    _conflicts_item_fields(skill_lines, skill_path, diag)
    _conflicts_next_forms(skill_lines, skill_path, diag)
    _conflicts_context_values(skill_lines, skill_path, diag)
    _conflicts_i18n_literals(skill_text, skill_lines, skill_path, diag)
    _conflicts_launch_table_regex(skill_lines, skill_path, diag)


# --- --baseline: детерминированный счёт новых ошибок (2026.07.13-PLAN-PROTOCOL-GAP P1.2/B1/D5/D6) ---------

def _git_run(args, cwd, timeout=15):
    """`check=False`, перехватывает `FileNotFoundError`/таймаут — линтер обязан
    работать вне git-репо (гоняют по Brain-vault'у и чужим корням, 2026.07.13-PLAN-PROTOCOL-GAP P1.2 Implementation
    Rules). None — команда не выполнилась вовсе (нет git / таймаут)."""
    try:
        return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                               timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _baseline_diag_keys(root, ref):
    """Прогоняет lint на дереве `ref` для того же `root`-пути (git archive во временный
    каталог, БЕЗ файла-состояния — источник истины git). Возвращает
    `(normalized_keys, None)` либо `(None, причина)` при недоступности baseline —
    graceful degrade (git отсутствует / не репозиторий / ref не найден / archive упал)."""
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

    archive = _git_run(["archive", ref, "--", str(relpath)], cwd=git_root, timeout=30)
    if archive is None or archive.returncode != 0 or not archive.stdout:
        return None, f"«git archive {ref} -- {relpath}» не удался"

    with tempfile.TemporaryDirectory(prefix="plan-lint-baseline-") as tmp:
        tmpdir = Path(tmp)
        try:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r|") as tar:
                tar.extractall(path=tmpdir)
        except tarfile.TarError as exc:
            return None, f"распаковка архива не удалась: {exc}"

        baseline_root = tmpdir / relpath
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


# --- CLI ----------------------------------------------------------------------

__all__ = tuple(name for name in globals() if not name.startswith("__"))
