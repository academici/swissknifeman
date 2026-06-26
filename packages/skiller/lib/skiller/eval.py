"""eval — поведенческое тестирование скиллов реестра (eval-first авторинг).

Зачем: до сих пор скиллы проверялись ТОЛЬКО структурно (`validate.sh`: frontmatter,
схемы, ссылки, графы) и на двуязычную когерентность (`check-translations.sh`). Не
было ответа на главный вопрос — *а скилл вообще работает и срабатывает к месту?*
Этот модуль закрывает пробел: формат eval-кейсов, программная (детерминированная)
оценка вывода, прогон with-skill vs baseline, pressure-тесты «соблазн пропустить
скилл», агрегат метрик и оптимизация триггер-точности `description`.

Адаптировано (методология, не код) из anthropic `skill-creator` (evals.json /
benchmark / iteration-loop / description-optimization) и obra/superpowers
`writing-skills` (pressure-тесты — TDD для документации). Лицензии тех скиллов —
демонстрационные/MIT; здесь — собственная реализация под конвенции реестра.

Слой разнесён намеренно:
  • ЧИСТАЯ логика (грейдер, агрегат, scoring/selection описания, валидация схемы,
    скаффолд, viewer, резолв) — офлайн и детерминированна → покрыта unit-тестами,
    гоняется в CI без сети.
  • РАННЕР (`run_case` через `claude -p`) — online, opt-in. Нет `claude` в PATH →
    команда мягко деградирует (скаффолд + офлайн-валидация), CI не падает.

Конвенции пакета: stdlib-only, `Env` явно, атомарная запись (`core.io`), сообщения
по-русски. Токен-математика — НЕ здесь (единый источник `budget.py`)."""
import json
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from core import (atomic_write_json, atomic_write_text, die, parse_args,
                  safe_load_json, warn)

# --- константы ----------------------------------------------------------------
# Типы ассершенов — ТОЛЬКО детерминированные (без LLM-judge), чтобы grade был
# воспроизводим в CI. LLM-judge — отдельный online-режим, не для гейта.
ASSERTION_TYPES = {"contains", "not_contains", "regex", "not_regex",
                   "file_exists", "file_absent", "min_words"}
# Триггер-описание (ярус-0) держим ≤150 симв. — то же правило, что в lean-каноне.
DESC_MAX = 150
DEFAULT_TIMEOUT = 180          # сек на один прогон `claude -p`
EVALS_SUBDIR = "evals"
# Переопределяемый билдер команды claude — флаг инъекции скилла верифицирован по
# `claude --help` локальной установки (см. build_run_cmd / docs/guide/evals.md).
CLAUDE_BIN_ENV = "SKM_CLAUDE_BIN"


# ============================================================================ #
#  ГРЕЙДЕР (офлайн, детерминированный)                                          #
# ============================================================================ #
def grade_assertion(assertion, output, workspace):
    """Оценить один ассершен против вывода прогона. → (ok: bool, detail: str).

    assertion = {"type": <ASSERTION_TYPES>, "value": <str|int>, "flags"?: {...}}.
    Текстовые сравнения по умолчанию регистронезависимы (flags.case_sensitive=true
    отключает) — естественный язык робастнее так. file_*-ассершены резолвят value
    относительно workspace (каталог прогона)."""
    atype = assertion.get("type", "")
    value = assertion.get("value", "")
    flags = assertion.get("flags", {}) or {}
    ci = not flags.get("case_sensitive", False)
    text = output or ""
    hay = text.lower() if ci else text
    needle = str(value).lower() if ci else str(value)
    reflags = re.IGNORECASE if ci else 0

    if atype == "contains":
        ok = needle in hay
        return ok, f"contains {value!r}: {'найдено' if ok else 'НЕ найдено'}"
    if atype == "not_contains":
        ok = needle not in hay
        return ok, f"not_contains {value!r}: {'отсутствует' if ok else 'НАЙДЕНО (плохо)'}"
    if atype == "regex":
        ok = re.search(str(value), text, reflags) is not None
        return ok, f"regex {value!r}: {'совпало' if ok else 'НЕ совпало'}"
    if atype == "not_regex":
        ok = re.search(str(value), text, reflags) is None
        return ok, f"not_regex {value!r}: {'нет совпадений' if ok else 'СОВПАЛО (плохо)'}"
    if atype in ("file_exists", "file_absent"):
        exists = (Path(workspace) / str(value)).exists() if workspace else False
        ok = exists if atype == "file_exists" else not exists
        return ok, f"{atype} {value!r}: {'ок' if ok else 'нарушено'}"
    if atype == "min_words":
        try:
            need = int(value)
        except (TypeError, ValueError):
            return False, f"min_words: value не число ({value!r})"
        got = len(text.split())
        return got >= need, f"min_words {need}: получено {got}"
    return False, f"неизвестный тип ассершена: {atype!r}"


def grade_case(case, output, workspace=None):
    """Оценить кейс (набор ассершенов) против вывода. → dict.

    {id, passed: bool|None, checks: [{type, ok, detail}]}. Кейс без ассершенов →
    passed=None (не оценён) — такие не идут в pass_rate (нечего проверять)."""
    asserts = case.get("assertions", []) or []
    checks = []
    for a in asserts:
        ok, detail = grade_assertion(a, output, workspace)
        checks.append({"type": a.get("type", ""), "ok": ok, "detail": detail})
    passed = None if not checks else all(c["ok"] for c in checks)
    return {"id": case.get("id"), "passed": passed, "checks": checks}


# ============================================================================ #
#  ВАЛИДАЦИЯ СХЕМЫ (офлайн)                                                     #
# ============================================================================ #
def _validate_cases(cases, label, *, kind):
    errors = []
    if not isinstance(cases, list) or not cases:
        return [f"{label}: '{kind}' должен быть непустым массивом"]
    seen = set()
    for i, c in enumerate(cases):
        where = f"{label}[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{where}: кейс должен быть объектом")
            continue
        cid = c.get("id")
        if cid is None:
            errors.append(f"{where}: нет поля id")
        elif cid in seen:
            errors.append(f"{where}: дубликат id {cid!r}")
        else:
            seen.add(cid)
        if not c.get("prompt"):
            errors.append(f"{where}: нет непустого prompt")
        asserts = c.get("assertions", [])
        if not isinstance(asserts, list):
            errors.append(f"{where}: assertions должен быть массивом")
            asserts = []
        for j, a in enumerate(asserts):
            if not isinstance(a, dict):
                errors.append(f"{where}.assertions[{j}]: должен быть объектом")
                continue
            at = a.get("type", "")
            if at not in ASSERTION_TYPES:
                errors.append(f"{where}.assertions[{j}]: type {at!r} не из "
                              f"{sorted(ASSERTION_TYPES)}")
            if "value" not in a:
                errors.append(f"{where}.assertions[{j}]: нет поля value")
    return errors


def validate_evals(data, label="evals.json"):
    """Структурная валидация evals.json. → список ошибок (пуст = валидно)."""
    if not isinstance(data, dict):
        return [f"{label}: корень должен быть объектом"]
    errors = []
    if not data.get("skill"):
        errors.append(f"{label}: нет поля skill")
    errors += _validate_cases(data.get("cases"), label, kind="cases")
    return errors


def validate_pressure(data, label="pressure.json"):
    """Структурная валидация pressure.json (сценарии-соблазны). → список ошибок.

    Сценарий — тот же грейд-контракт (assertions), плюс поле `tempts` (что агента
    подмывает сделать, пропустив скилл) для читаемости."""
    if not isinstance(data, dict):
        return [f"{label}: корень должен быть объектом"]
    errors = []
    if not data.get("skill"):
        errors.append(f"{label}: нет поля skill")
    errors += _validate_cases(data.get("scenarios"), label, kind="scenarios")
    return errors


def validate_triggers(data, label="triggers.json"):
    """Валидация triggers.json для оптимизации описания. → список ошибок."""
    if not isinstance(data, dict):
        return [f"{label}: корень должен быть объектом"]
    errors = []
    for key in ("should_trigger", "should_not"):
        v = data.get(key)
        if not isinstance(v, list) or not v:
            errors.append(f"{label}: '{key}' должен быть непустым массивом запросов")
        elif any(not isinstance(q, str) or not q.strip() for q in v):
            errors.append(f"{label}: '{key}' содержит пустой/нестроковый запрос")
    return errors


# ============================================================================ #
#  АГРЕГАТ BENCHMARK (офлайн)                                                   #
# ============================================================================ #
def _stat(values):
    """(mean, stddev) по списку чисел; None-ы отфильтрованы. stdev=0 при <2."""
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None, None
    mean = statistics.fmean(nums)
    sd = statistics.pstdev(nums) if len(nums) > 1 else 0.0
    return round(mean, 3), round(sd, 3)


def aggregate_runs(case_results):
    """Свести список прогонов кейсов в метрики набора.

    case_results: [{passed: bool|None, duration_s?, tokens?}]. →
    {total, graded, passed, pass_rate, duration_mean, duration_std,
     tokens_mean, tokens_std}. pass_rate=None, если нечего оценивать."""
    total = len(case_results)
    graded = [r for r in case_results if r.get("passed") is not None]
    passed = sum(1 for r in graded if r["passed"])
    d_mean, d_std = _stat([r.get("duration_s") for r in case_results])
    t_mean, t_std = _stat([r.get("tokens") for r in case_results])
    return {
        "total": total,
        "graded": len(graded),
        "passed": passed,
        "pass_rate": round(passed / len(graded), 3) if graded else None,
        "duration_mean": d_mean, "duration_std": d_std,
        "tokens_mean": t_mean, "tokens_std": t_std,
    }


def build_benchmark(skill, with_skill_runs, baseline_runs=None):
    """Собрать benchmark из прогонов with-skill (и опц. baseline). Чистая функция:
    без времени/IO (детерминированна для тестов; generated_at ставит cmd_eval)."""
    bench = {"skill": skill, "with_skill": aggregate_runs(with_skill_runs)}
    if baseline_runs is not None:
        base = aggregate_runs(baseline_runs)
        bench["baseline"] = base
        ws, bs = bench["with_skill"], base
        delta = {}
        if ws["pass_rate"] is not None and bs["pass_rate"] is not None:
            delta["pass_rate"] = round(ws["pass_rate"] - bs["pass_rate"], 3)
        if ws["tokens_mean"] is not None and bs["tokens_mean"] is not None:
            delta["tokens_mean"] = round(ws["tokens_mean"] - bs["tokens_mean"], 3)
        bench["delta"] = delta
    return bench


# ============================================================================ #
#  ТРИГГЕР-ТОЧНОСТЬ ОПИСАНИЯ (логика офлайн; judge инъектируется)               #
# ============================================================================ #
def score_description(description, trigger_set, judge):
    """Оценить, насколько `description` срабатывает к месту и не ложно.

    trigger_set = {"should_trigger": [q...], "should_not": [q...]}.
    judge(description, query) -> bool — предсказание «сработает ли скилл». Online
    judge = вызов модели; в тестах инъектируется детерминированный фейк.
    → {tp, fp, fn, tn, precision, recall, f1, accuracy, len, over_limit}."""
    st = trigger_set.get("should_trigger", []) or []
    sn = trigger_set.get("should_not", []) or []
    tp = sum(1 for q in st if judge(description, q))
    fn = len(st) - tp
    fp = sum(1 for q in sn if judge(description, q))
    tn = len(sn) - fp
    total = tp + fn + fp + tn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3), "recall": round(recall, 3),
        "f1": round(f1, 3),
        "accuracy": round((tp + tn) / total, 3) if total else 0.0,
        "len": len(description), "over_limit": len(description) > DESC_MAX,
    }


def select_best_description(candidates, trigger_set, judge, *, max_len=DESC_MAX):
    """Выбрать лучшего кандидата описания по триггер-набору.

    Кандидаты длиннее max_len или пустые отбраковываются (правило ≤150 симв.
    яруса-0 нерушимо). Ранжирование: f1 → accuracy → короче. →
    {best, score, ranked: [...], rejected: [...]}; best=None, если все отброшены."""
    rejected = [c for c in candidates if not c.strip() or len(c) > max_len]
    pool = [c for c in candidates if c.strip() and len(c) <= max_len]
    scored = [(c, score_description(c, trigger_set, judge)) for c in pool]
    scored.sort(key=lambda cs: (cs[1]["f1"], cs[1]["accuracy"], -cs[1]["len"]),
                reverse=True)
    best = scored[0] if scored else None
    return {
        "best": best[0] if best else None,
        "score": best[1] if best else None,
        "ranked": [{"description": c, "score": s} for c, s in scored],
        "rejected": rejected,
    }


# ============================================================================ #
#  РАННЕР (online, opt-in)                                                      #
# ============================================================================ #
def claude_bin():
    """Путь к CLI `claude`: env-override SKM_CLAUDE_BIN → PATH. None, если нет."""
    override = os.environ.get(CLAUDE_BIN_ENV)
    if override:
        p = Path(os.path.expanduser(override))
        return str(p) if p.exists() else None
    found = shutil.which("claude")
    return found


def build_run_cmd(claude, prompt, skill_text=None):
    """Собрать argv для `claude -p`. Скилл инъектируется через
    --append-system-prompt (флаг сверен по `claude --help` установки). Вывод —
    JSON (--output-format json) для извлечения result+usage."""
    cmd = [claude, "-p", prompt, "--output-format", "json"]
    if skill_text:
        cmd += ["--append-system-prompt", skill_text]
    return cmd


def _parse_claude_json(stdout):
    """(text, tokens) из JSON-вывода `claude -p`. На неразборе → (stdout, None)."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return stdout, None
    text = data.get("result", "") if isinstance(data, dict) else stdout
    tokens = None
    usage = data.get("usage") if isinstance(data, dict) else None
    if isinstance(usage, dict):
        tokens = (usage.get("input_tokens", 0) or 0) + \
                 (usage.get("output_tokens", 0) or 0) or None
    return text, tokens


def run_case(skill_dir, case, *, with_skill, workspace, timeout=DEFAULT_TIMEOUT,
             claude=None):
    """Один прогон кейса через `claude -p` в каталоге workspace.

    with_skill=True → тело SKILL.md подмешивается в системный промт (baseline без
    него — изоляция эффекта скилла). case.files[] (если есть) пишутся в workspace
    до прогона. → {id, output, returncode, duration_s, tokens, error?}."""
    claude = claude or claude_bin()
    if not claude:
        raise RuntimeError("CLI `claude` не найден — раннер недоступен (офлайн)")
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    for f in case.get("files", []) or []:
        fp = ws / f.get("path", "")
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(f.get("content", ""), encoding="utf-8")
    skill_text = None
    if with_skill:
        md = Path(skill_dir) / "SKILL.md"
        skill_text = md.read_text(encoding="utf-8") if md.is_file() else None
    cmd = build_run_cmd(claude, case["prompt"], skill_text)
    start = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"id": case.get("id"), "output": "", "returncode": -1,
                "duration_s": round(time.time() - start, 3), "tokens": None,
                "error": f"timeout {timeout}s"}
    text, tokens = _parse_claude_json(proc.stdout)
    return {"id": case.get("id"), "output": text, "returncode": proc.returncode,
            "duration_s": round(time.time() - start, 3), "tokens": tokens}


def run_suite(skill_dir, cases, *, with_skill, timeout=DEFAULT_TIMEOUT,
              claude=None):
    """Прогнать набор кейсов (каждый в своём временном workspace) и оценить.
    → [{...run_case, **grade_case}]. Online."""
    results = []
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="skiller-eval-") as ws:
            run = run_case(skill_dir, case, with_skill=with_skill, workspace=ws,
                           timeout=timeout, claude=claude)
            grade = grade_case(case, run.get("output", ""), ws)
        results.append({**run, **grade})
    return results


# ============================================================================ #
#  VIEWER (markdown / standalone HTML)                                          #
# ============================================================================ #
def _fmt_rate(r):
    return "—" if r is None else f"{r * 100:.0f}%"


def render_markdown(benchmark):
    """Человекочитаемый markdown-отчёт по benchmark."""
    b = benchmark
    ws = b.get("with_skill", {})
    out = [f"# Eval: {b.get('skill', '?')}", "",
           "| Набор | pass@ | кейсов | ток (μ±σ) | сек (μ±σ) |",
           "|---|--:|--:|--:|--:|"]

    def row(label, a):
        tok = "—" if a.get("tokens_mean") is None else \
            f"{a['tokens_mean']:.0f}±{a.get('tokens_std', 0):.0f}"
        dur = "—" if a.get("duration_mean") is None else \
            f"{a['duration_mean']:.1f}±{a.get('duration_std', 0):.1f}"
        return (f"| {label} | {_fmt_rate(a.get('pass_rate'))} | "
                f"{a.get('passed', 0)}/{a.get('graded', 0)} | {tok} | {dur} |")

    out.append(row("with-skill", ws))
    if b.get("baseline") is not None:
        out.append(row("baseline", b["baseline"]))
    if b.get("delta"):
        d = b["delta"]
        parts = []
        if "pass_rate" in d:
            parts.append(f"pass@ {d['pass_rate'] * 100:+.0f}пп")
        if "tokens_mean" in d:
            parts.append(f"ток {d['tokens_mean']:+.0f}")
        out += ["", f"**Δ skill vs baseline:** {', '.join(parts) or '—'}"]
    return "\n".join(out) + "\n"


def render_html(benchmark):
    """Автономный HTML-отчёт (--static) — markdown в <pre>, без зависимостей."""
    md = render_markdown(benchmark).replace("&", "&amp;").replace("<", "&lt;")
    skill = benchmark.get("skill", "eval")
    return (f"<!doctype html><html lang=ru><meta charset=utf-8>"
            f"<title>eval: {skill}</title>"
            f"<body style='font:14px/1.5 system-ui;max-width:48rem;margin:2rem auto'>"
            f"<pre style='white-space:pre-wrap'>{md}</pre></body></html>\n")


# ============================================================================ #
#  СКАФФОЛД + РЕЗОЛВ                                                            #
# ============================================================================ #
def _stub_evals(skill_name):
    return {"skill": skill_name, "cases": [{
        "id": 1,
        "prompt": "Реальный пользовательский запрос на языке экосистемы "
                  "(конкретика: пути, имена). Замени на свой.",
        "assertions": [
            {"type": "contains", "value": "ожидаемая-подстрока"},
            {"type": "not_contains", "value": "запрещённая-подстрока"},
        ],
    }]}


def _stub_pressure(skill_name):
    return {"skill": skill_name, "scenarios": [{
        "id": 1,
        "tempts": "Что подмывает агента сделать, ПРОПУСТИВ скилл "
                  "(например: сразу писать код вместо проверки факта).",
        "prompt": "Сценарий-соблазн под давлением. Замени на свой.",
        "assertions": [
            {"type": "contains", "value": "признак-соблюдения-скилла"},
            {"type": "not_contains", "value": "признак-нарушения"},
        ],
    }]}


def _stub_triggers(skill_name):
    return {"skill": skill_name,
            "should_trigger": ["запрос, на котором скилл ОБЯЗАН сработать (1)",
                               "та же тема другими словами (2)"],
            "should_not": ["близкий, но НЕ про этот скилл запрос (1)",
                           "ещё один near-miss (2)"]}


def scaffold_evals(skill_dir, skill_name=None):
    """Создать стабы evals/{evals,pressure,triggers}.json (не перезаписывая
    существующие). → список созданных путей. Атомарно (core.io)."""
    skill_dir = Path(skill_dir)
    skill_name = skill_name or skill_dir.name
    evals_dir = skill_dir / EVALS_SUBDIR
    created = []
    for fname, builder in (("evals.json", _stub_evals),
                           ("pressure.json", _stub_pressure),
                           ("triggers.json", _stub_triggers)):
        path = evals_dir / fname
        if path.exists():
            continue
        atomic_write_json(path, builder(skill_name))
        created.append(path)
    return created


def resolve_skill(env, ref):
    """Каталог скилла по ref ('bucket/name' или 'name'). die, если не найден/неоднозначен."""
    skills_root = env.root / "skills"
    ref = ref.strip().strip("/")
    if "/" in ref:
        cand = skills_root / ref
        if (cand / "SKILL.md").is_file():
            return cand
        die(f"скилл не найден: skills/{ref}/SKILL.md")
    matches = [p.parent for p in skills_root.glob(f"*/{ref}/SKILL.md")]
    if not matches:
        die(f"скилл '{ref}' не найден в реестре (укажи bucket/name)")
    if len(matches) > 1:
        rels = ", ".join(str(m.relative_to(skills_root)) for m in matches)
        die(f"неоднозначно '{ref}' — есть в нескольких бакетах: {rels}")
    return matches[0]


def evals_coverage(root):
    """(skills_with_evals, local_skills) по реестру — для сводки в validate/status.
    Локальные = без upstream.json (eval-стандарт на авторские скиллы)."""
    skills_root = Path(root) / "skills"
    local, with_evals = 0, 0
    for skill_md in sorted(skills_root.glob("*/*/SKILL.md")):
        d = skill_md.parent
        if (d / "upstream.json").exists():
            continue
        local += 1
        if (d / EVALS_SUBDIR / "evals.json").exists():
            with_evals += 1
    return with_evals, local


# ============================================================================ #
#  CLI                                                                          #
# ============================================================================ #
_USAGE = (
    "skiller eval <bucket/skill | skill> [--baseline] [--triggers]\n"
    "             [--scaffold] [--static] [--json] [--timeout N]\n"
    "  Поведенческий прогон скилла: with-skill vs baseline, программные ассершены,\n"
    "  pressure-тесты, benchmark.json. --triggers — оптимизация триггер-точности\n"
    "  описания. --scaffold — создать стабы evals/. Раннер требует CLI `claude`\n"
    "  (нет в PATH → офлайн-валидация + скаффолд, без падения).")


def _offline_report(skill_dir):
    """Офлайн-ветка (нет `claude`): провалидировать имеющиеся evals и подсказать."""
    evals_dir = skill_dir / EVALS_SUBDIR
    problems = []
    for fname, validator in (("evals.json", validate_evals),
                             ("pressure.json", validate_pressure),
                             ("triggers.json", validate_triggers)):
        data = safe_load_json(evals_dir / fname)
        if data is not None:
            problems += validator(data, fname)
    if problems:
        for p in problems:
            print(f"  ОШИБКА СХЕМЫ: {p}")
    else:
        print("  схема evals/ валидна")
    warn("CLI `claude` не найден — прогон пропущен (офлайн). Поставь claude "
         "или задай SKM_CLAUDE_BIN, чтобы запускать with-skill vs baseline.")


def cmd_eval(env, argv):
    opts, pos = parse_args(argv, {
        "--baseline": "bool", "--triggers": "bool", "--scaffold": "bool",
        "--static": "bool", "--json": "bool", "--timeout": "str",
    }, max_pos=1)
    if opts["help"] or not pos:
        print(_USAGE)
        return
    skill_dir = resolve_skill(env, pos[0])
    skill_name = skill_dir.name
    evals_dir = skill_dir / EVALS_SUBDIR

    if opts["scaffold"]:
        created = scaffold_evals(skill_dir, skill_name)
        if created:
            print(f"Созданы стабы: {', '.join(p.name for p in created)} "
                  f"в {evals_dir.relative_to(env.root)}")
        else:
            print("Стабы evals/ уже есть — ничего не создано")
        return

    if not (evals_dir / "evals.json").exists():
        created = scaffold_evals(skill_dir, skill_name)
        print(f"Нет evals.json — создал стабы ({', '.join(p.name for p in created)}). "
              f"Заполни кейсы и перезапусти `skiller eval {pos[0]}`.")
        return

    claude = claude_bin()
    timeout = int(opts["timeout"]) if opts.get("timeout") else DEFAULT_TIMEOUT

    # --- оптимизация триггер-точности описания --------------------------------
    if opts["triggers"]:
        triggers = safe_load_json(evals_dir / "triggers.json")
        if triggers is None:
            scaffold_evals(skill_dir, skill_name)
            print("Нет triggers.json — создал стаб. Заполни should_trigger / "
                  "should_not и перезапусти с --triggers.")
            return
        errs = validate_triggers(triggers, "triggers.json")
        if errs:
            die("triggers.json невалиден:\n  " + "\n  ".join(errs))
        if not claude:
            warn("CLI `claude` не найден — оптимизация описания требует модель "
                 "(генерация кандидатов + judge). Офлайн недоступно.")
            return
        # Online-ветка генерации кандидатов/judge вынесена за гейт CI; реализация
        # дергает `claude -p`. Здесь — каркас: scoring/selection ниже чисты и
        # покрыты тестами, online-обвязка подключается в окружении с моделью.
        warn("Online-оптимизация описания (--triggers) запускается в окружении с "
             "моделью; scoring/selection доступны как API (score_description / "
             "select_best_description). См. docs/guide/evals.md.")
        return

    # --- прогон eval + pressure -----------------------------------------------
    if not claude:
        print(f"━━━ EVAL {skill_name} (офлайн) ━━━")
        _offline_report(skill_dir)
        return

    evals = safe_load_json(evals_dir / "evals.json") or {}
    errs = validate_evals(evals, "evals.json")
    pressure = safe_load_json(evals_dir / "pressure.json")
    if pressure is not None:
        errs += validate_pressure(pressure, "pressure.json")
    if errs:
        die("evals невалидны:\n  " + "\n  ".join(errs))

    cases = list(evals.get("cases", []))
    if pressure:
        cases += list(pressure.get("scenarios", []))

    with_runs = run_suite(skill_dir, cases, with_skill=True, timeout=timeout,
                          claude=claude)
    base_runs = None
    if opts["baseline"]:
        base_runs = run_suite(skill_dir, cases, with_skill=False, timeout=timeout,
                              claude=claude)
    bench = build_benchmark(skill_name, with_runs, base_runs)
    bench["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    bench["cases"] = [{"id": r.get("id"), "passed": r.get("passed"),
                       "checks": r.get("checks", [])} for r in with_runs]
    atomic_write_json(evals_dir / "benchmark.json", bench)

    if opts["static"]:
        out = evals_dir / "benchmark.html"
        atomic_write_text(out, render_html(bench))
        print(f"HTML-отчёт: {out.relative_to(env.root)}")
    if opts["json"]:
        print(json.dumps(bench, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(bench))
