"""gate — вердикт по item'у волны: GREEN/ATTENTION/RED из ЧЕТЫРЁХ источников признаков
(P4.4, `root/contracts/driver-plan-protocol-v2.md` §5/§7, правка D103–D106).

Источники: (1) класс исхода прогона — приходит от `worker` (P4.3), готовым словарём,
здесь не переразбирается; (2) `plan-lint --baseline <SHA до прогона> --gate new` — S1
(§2 контракта), два процессных вызова, второй парсер плана НЕ заводится; (3)
git-топология закрытия item'а в диапазоне `<SHA>..HEAD` (§5 контракта) — подпись
закрытия, состав коммитов (бандл), чистота каталога плана относительно снимка «до»;
(4) статус и поля item'а ПОСЛЕ прогона — тоже S1 (`--json`), поле `fields` уже отдаёт
готовый читатель, собственного разбора item-тела здесь нет.

Таблица «признак → вердикт» (`TABLE`) — единственный носитель соответствия (Implementation
Rule 1): она ТОТАЛЬНА (D105) — `_classify` добавляет дефолтную строку RED, если не
сматчилась ни одна строка данных. «Любой RED побеждает» и «сомнение → строгий вердикт»
(IR 5/6) реализованы ОДНОЙ функцией приоритета рангов (`_RANK`), а не рассыпанными
`if`: RED хуже ATTENTION хуже GREEN, `_classify` берёт минимальный ранг среди сматчившихся
строк — свойство «любой RED побеждает» и «GREEN требует явного all-clear» следуют из
самого ранжирования, а не из порядка проверки.

**Разбор поля `Files` item'а НЕ производится** (Scope Excluded, P4.4) — это была бы
ТРЕТЬЯ собственная точка разбора; состав коммитов судится ТОЛЬКО бинарным делением
путей на «плановую бухгалтерию» (`plan.md`/`phases/**`/`handoff.md`/`index.md`/
`open-questions.md`/`journal.jsonl`/`closure/**`/`roadmap.md`/`plans/ACTIVE.md`) и
«остальное» (`plan.md` §2, D75) — деление читается как ДАННЫЕ (`_is_bookkeeping`), не
как второй парсер плана.

**Раскрытая находка: новую ERROR-диагностику от новой WARNING линтер отдаёт ТОЛЬКО
комбинированным счётом** (`plan_lint.py --baseline --gate new` считает мультимножество
`(kind, path, msg)` разом, `:2386`); CLI не отдаёт раздельный счёт по `kind`, а заводить
третий разбор diff'а диагностик, дублирующий `Diagnostics.normalized_keys`, здесь
запрещено тем же правилом, что и разбор `Files`. Разрешение — ПРИМЕНЕНИЕ уже названного
правила IR6 «сомнение → строгий вердикт»: если комбинированный счёт нового > 0, а
ТЕКУЩЕЕ дерево (без baseline, `--gate all`) несёт хотя бы одну ERROR где-либо — новое НЕ
отделяется от преэкзистентного без второго носителя правды, значит вердикт обязан
предположить худшее (`new_error_suspected`, RED); если текущих ERROR нет вовсе (`--gate
all` зелёный), новое может быть только WARNING (`new_warning_only`, ATTENTION) — это
не догадка, а логический вывод (не может быть новой ERROR там, где ERROR нет вообще).

**Раскрытая находка: `has_escalation` (сырой блок `> 🔴 ESCALATION Pn.m:` в теле item'а)
не входит в модель `--json`** (`plan_lint.py:2178–2179` отдаёт только `title`/`fields`,
не сырые флаги построчного скана) — читать его отдельно означало бы третий разбор тела
item'а. Не нужно: `lint_plan` САМ гейтит согласованность `is_blocked == en_yes ==
has_escalation` (`plan_lint.py:1866–1870`) как ERROR схемы — расхождение всплывает
источником (2) (новая ERROR), а согласованный случай уже покрыт источниками `Status:
🔴 Blocked` и `Escalation Needed: yes` (обе — самостоятельные строки таблицы). Строка
`ESCALATION-REQUIRED:` читается из ОТЧЁТА ВОРКЕРА (`outcome["result_text"]`, приходит
готовым от P4.3) — это не разбор плана, а подстрока в чужом уже-полученном тексте.

Функции чистые, кроме подпроцессных вызовов git/`plan-lint.py`; исключение
`GateUnavailable` — ТОЛЬКО на структурной невозможности вынести вердикт (git/CLI не
запустились), не бизнес-исход. stdlib-only."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core import find_monorepo_root

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


class GateUnavailable(RuntimeError):
    """git или `plan-lint.py` структурно недоступны (не репозиторий, бинарь не найден,
    таймаут) — вердикт вынести нечем, это отказ ДО оценки, не RED-исход (fail-loud,
    тот же класс, что `WorkerUnavailable` у P4.3 и `degraded` у P4.2 на полном отказе
    источника)."""


# --- git: снимок «до» и топология закрытия (§5 контракта) --------------------

def _git(args, cwd, *, timeout=30):
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateUnavailable(f"git {' '.join(args)} не выполнился: {exc}") from exc


def _resolve_git_root(plan_dir, *, timeout=30):
    proc = _git(["rev-parse", "--show-toplevel"], cwd=plan_dir, timeout=timeout)
    if proc.returncode != 0:
        raise GateUnavailable(
            f"«{plan_dir}» вне git-репозитория (или git не установлен): {proc.stderr.strip()}")
    return Path(proc.stdout.strip())


def _porcelain_lines(git_root, plan_rel, *, timeout=30):
    proc = _git(["status", "--porcelain", "--", plan_rel], cwd=git_root, timeout=timeout)
    if proc.returncode != 0:
        raise GateUnavailable(f"git status --porcelain не выполнился: {proc.stderr.strip()}")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def snapshot_before(plan_dir, *, timeout=30):
    """Снимок ОДНИМ шагом ДО спавна воркера (Implementation Rule 2, D106): `HEAD` —
    baseline линтера item'а; `git status --porcelain` каталога плана — эталон «что уже
    было грязным», чтобы законный чужой дифф владельца не дал ложный RED. Обязателен
    ИМЕННО до — `--baseline HEAD`, взятый ПОСЛЕ прогона, сравнивал бы дерево с самим
    собой."""
    plan_dir = Path(plan_dir)
    git_root = _resolve_git_root(plan_dir, timeout=timeout)
    plan_rel = str(plan_dir.resolve().relative_to(git_root))
    head = _git(["rev-parse", "HEAD"], cwd=git_root, timeout=timeout)
    if head.returncode != 0:
        raise GateUnavailable(f"git rev-parse HEAD не выполнился: {head.stderr.strip()}")
    return {
        "sha": head.stdout.strip(),
        "dirty": _porcelain_lines(git_root, plan_rel, timeout=timeout),
        "git_root": str(git_root),
        "plan_rel": plan_rel,
    }


def _changed_paths(commit_hash, git_root, *, timeout=30):
    proc = _git(["show", "--name-only", "--pretty=format:", commit_hash],
               cwd=git_root, timeout=timeout)
    if proc.returncode != 0:
        raise GateUnavailable(
            f"git show --name-only {commit_hash} не выполнился: {proc.stderr.strip()}")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def _is_bookkeeping(rel_path, plan_rel):
    if rel_path == _BOOKKEEPING_ROOT_FILE:
        return True
    prefix = plan_rel + "/"
    if not rel_path.startswith(prefix):
        return False
    sub = rel_path[len(prefix):]
    return sub in _BOOKKEEPING_LEAVES or sub.startswith(_BOOKKEEPING_DIRS)


def _read_closure(before, phase_id, *, timeout=30):
    """Git-проверка закрытия (§5 контракта): подпись (все три файла — `plan.md`,
    `phases/P<n>.md` фазы item'а, `handoff.md` — закоммичены где-то в диапазоне),
    состав (бандл — бухгалтерия и Scope в одном коммите, D104: число/порядок коммитов
    НЕ проверяются), чистота каталога плана относительно снимка «до» (D106)."""
    git_root = Path(before["git_root"])
    plan_rel = before["plan_rel"]

    log = _git(["log", "--format=%H", f"{before['sha']}..HEAD"], cwd=git_root, timeout=timeout)
    if log.returncode != 0:
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
        "commit_count": len(commits),
        "commits": commits,
        "signature_complete": not missing,
        "missing_signature_paths": missing,
        "bundle": bundle,
        "dirty_remainder": sorted(
            set(_porcelain_lines(git_root, plan_rel, timeout=timeout)) - set(before["dirty"])),
    }


# --- S1: plan-lint.py — счёт новых диагностик + поля item'а после прогона ----

def _run_plan_lint(plan_dir, monorepo_root, extra_args, *, timeout=60):
    script = Path(monorepo_root) / "packages" / "task" / "scripts" / "plan-lint.py"
    try:
        return subprocess.run(["python3", str(script), str(plan_dir), *extra_args],
                              capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateUnavailable(f"plan-lint.py не запустился: {exc}") from exc


def _read_lint_signals(plan_dir, monorepo_root, baseline_sha, *, timeout=60):
    """S1 — `--baseline <SHA до прогона> --gate new` (§2 контракта). Деградация baseline
    (недоступен git-ref) распознаётся по собственному WARNING линтера (`недоступен` в
    stderr, `plan_lint.py:2382-2384`) — GREEN на деградации не выдаётся (Implementation
    Rule 3). Разделение новая-ERROR/новая-WARNING — см. докстринг модуля (IR6, doubt→strict)."""
    baseline = _run_plan_lint(plan_dir, monorepo_root,
                              ["--baseline", baseline_sha, "--gate", "new"], timeout=timeout)
    if "недоступен" in (baseline.stderr or ""):
        return {"degraded": True, "clean": False, "new_error_suspected": False,
                "new_warning_only": False, "lint_class": "degraded",
                "reason": baseline.stderr.strip()[-400:]}
    if baseline.returncode == 0:
        return {"degraded": False, "clean": True, "new_error_suspected": False,
                "new_warning_only": False, "lint_class": "clean", "reason": None}

    # Что-то новое есть (сумма ERROR+WARN, см. докстринг). Дизамбигуация: текущее
    # дерево БЕЗ baseline (`--gate all`) красно ⇔ где-то в плане есть ХОТЯ БЫ одна
    # ERROR (не обязательно новая) — если ERROR нет вовсе, новое может быть только
    # WARNING (логический вывод, не догадка); если ERROR есть — новое от преэкзистентного
    # не отделить без normalized_keys (второй носитель правды запрещён), IR6 велит
    # предположить худшее.
    current = _run_plan_lint(plan_dir, monorepo_root, ["--gate", "all"], timeout=timeout)
    if current.returncode != 0:
        return {"degraded": False, "clean": False, "new_error_suspected": True,
                "new_warning_only": False, "lint_class": "new-error-suspected",
                "reason": ("новая диагностика есть, и в дереве присутствует ERROR — "
                          "сомнение → строгий вердикт (IR6)")}
    return {"degraded": False, "clean": False, "new_error_suspected": False,
            "new_warning_only": True, "lint_class": "new-warning-only", "reason": None}


def _empty_field(value):
    v = (value or "").strip()
    return v in ("", "—")


def _read_item_fields_after(plan_dir, phase_id, item_id, monorepo_root, *, timeout=60):
    """S1 — `--json`, поля item'а ПОСЛЕ прогона (§2 контракта: «Любое из 16 полей
    item'а | S1»). Возвращаемые поля флэттит сам `plan_lint.py` (`:2179`); собственного
    разбора item-тела здесь нет. `available=False` — S1 недоступен (в т.ч. ERROR где-то
    в плане делает `--json` ненулевым по коду, `plan_lint.py:2404`) или item не найден —
    fail-loud факт, не тихая пустая запись."""
    try:
        proc = _run_plan_lint(plan_dir, monorepo_root, ["--json"], timeout=timeout)
    except GateUnavailable as exc:
        return {"available": False, "reason": str(exc)}
    if proc.returncode != 0:
        return {"available": False,
                "reason": (f"plan-lint.py --json завершился кодом {proc.returncode} "
                          f"(схема несёт ERROR — S1 недоступен для чтения полей): "
                          f"{proc.stderr.strip()[-400:]}")}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"available": False, "reason": f"plan-lint.py --json: вывод не JSON: {exc}"}

    plan_key = Path(plan_dir).name
    phase_model = (((data.get("plans") or {}).get(plan_key) or {}).get("phases") or {}).get(phase_id) or {}
    item_model = (phase_model.get("items") or {}).get(item_id)
    if item_model is None:
        return {"available": False, "reason": f"item {item_id} не найден в модели S1 фазы {phase_id}"}

    fields = item_model.get("fields") or {}
    return {
        "available": True,
        "status": fields.get("Status") or None,
        "pending_work_nonempty": not _empty_field(fields.get("Pending Work")),
        "known_deviations_nonempty": not _empty_field(fields.get("Known Deviations")),
        "escalation_needed_yes": (fields.get("Escalation Needed") or "").strip().lower().startswith("yes"),
    }


# --- таблица «признак → вердикт» (D105, ТОТАЛЬНА) -----------------------------

TABLE = (
    # RED — воркер не дал успешный конверт (timeout/transport/quota/error, §6.3 контракта)
    ("outcome-not-ok", RED, lambda s: s["outcome_class"] != "ok"),
    # RED — новая ERROR линтера (в т.ч. подозреваемая, IR6)
    ("lint-new-error", RED, lambda s: s["lint_new_error_suspected"]),
    # RED — коммитов в диапазоне нет вовсе
    ("no-commits", RED, lambda s: s["commit_count"] == 0),
    # RED — подпись закрытия не закоммичена (полностью или частично), D103
    ("closure-signature-incomplete", RED, lambda s: not s["signature_complete"]),
    # RED — незакоммиченный остаток в каталоге плана, которого не было «до», D106
    ("dirty-remainder", RED, lambda s: bool(s["dirty_remainder"])),
    # RED — статус 🔴 Blocked
    ("status-blocked", RED, lambda s: s["item_status"] == "🔴 Blocked"),
    # RED — Escalation Needed: yes
    ("escalation-needed-yes", RED, lambda s: s["escalation_needed_yes"]),
    # RED — маркер ESCALATION-REQUIRED: в отчёте воркера
    ("escalation-in-report", RED, lambda s: "ESCALATION-REQUIRED:" in (s["result_text"] or "")),
    # RED — статус после прогона не терминален (no-op), D105
    ("no-op", RED, lambda s: s["item_status"] in ("🟡 In progress", "⬜ Not started")),
    # RED — поля item'а после прогона не читаются вовсе (S1 недоступен)
    ("item-fields-unavailable", RED, lambda s: not s["item_fields_available"]),
    # ATTENTION — статус 🟠 Done with deviations
    ("status-deviations", ATTENTION, lambda s: s["item_status"] == "🟠 Done with deviations"),
    # ATTENTION — непустой permission_denials
    ("permission-denials", ATTENTION, lambda s: bool(s["permission_denials"])),
    # ATTENTION — непустой Pending Work
    ("pending-work", ATTENTION, lambda s: s["pending_work_nonempty"]),
    # ATTENTION — непустой Known Deviations
    ("known-deviations", ATTENTION, lambda s: s["known_deviations_nonempty"]),
    # ATTENTION — бандл (закрытие закоммичено, состав нарушен), §5 контракта
    ("bundle", ATTENTION, lambda s: s["bundle"]),
    # ATTENTION — только новые WARNING линтера
    ("lint-new-warning-only", ATTENTION, lambda s: s["lint_new_warning_only"]),
    # GREEN — все четыре источника чисты одновременно (правило полноты, §7 контракта)
    ("all-clear", GREEN, lambda s: (
        s["outcome_class"] == "ok" and s["lint_clean"] and s["signature_complete"]
        and not s["dirty_remainder"] and s["commit_count"] > 0
        and s["item_fields_available"] and s["item_status"] == "🟢 Done")),
)


def _classify(signals):
    """Ранжирование `_RANK` (RED=0 < ATTENTION=1 < GREEN=2) реализует ОБА правила поверх
    таблицы разом: «любой RED побеждает» и «сомнение → строгий вердикт» — минимальный
    ранг среди СМАТЧИВШИХСЯ строк, никогда не смягчается остальными. Не сматчилась ни
    одна строка → дефолт `RED` (D105, тотальность), а не молчаливый `else`."""
    matched = [(name, klass) for name, klass, predicate in TABLE if predicate(signals)]
    if not matched:
        matched = [("no-signal-matched-default", RED)]
    _, worst_klass = min(matched, key=lambda m: _RANK[m[1]])
    return worst_klass, [name for name, _ in matched]


# --- публичный API -------------------------------------------------------------

def pre_launch_verdict(queue_item):
    """Ветка «отказ до запуска» (Scope Included P4.4): item НЕ drivable по очереди
    `plan_reader` (P4.2) — `Exec != plan-exec` / `ROUTING-INCONSISTENT` / форма `Next`
    вне enum — RED без спавна воркера. Причина берётся ГОТОВОЙ у P4.2, здесь право
    вождения не переразбирается (D31 — деривация не в компетенции этого модуля)."""
    if queue_item.get("drivable"):
        raise ValueError("pre_launch_verdict вызывается только для НЕ-drivable item'а")
    return {
        "verdict": RED,
        "signals_matched": ["pre-launch-refusal"],
        "lint_class": None,
        "raw": {"refusal": queue_item.get("refusal"), "detail": queue_item.get("refusal_detail")},
    }


def verdict(plan_id, item_id, phase_id, plan_dir, before, outcome, *, monorepo_root=None,
           timeout=60):
    """Вердикт ПОСЛЕ прогона воркера, из четырёх источников (§7 контракта, порядок
    вычисления — Implementation Rule 10): класс исхода прогона (`outcome`, от P4.3) →
    линтер (S1) → git-топология закрытия (§5) → статус/поля item'а после прогона (S1).
    `before` — снимок `snapshot_before()`, взятый ДО спавна воркера. Возвращает
    структуру: класс + поимённый перечень сработавших признаков + класс оценки линтера
    + сырые данные источников (Deliverables P4.4) — одна буква без перечня не результат."""
    plan_dir = Path(plan_dir)
    if monorepo_root is None:
        monorepo_root = find_monorepo_root(plan_dir.resolve())
        if monorepo_root is None:
            raise GateUnavailable(
                f"монорепо-корень не найден от {plan_dir} — пакет `task` недоступен")

    lint = _read_lint_signals(plan_dir, monorepo_root, before["sha"], timeout=timeout)
    closure = _read_closure(before, phase_id, timeout=timeout)
    item_after = _read_item_fields_after(plan_dir, phase_id, item_id, monorepo_root,
                                        timeout=timeout)

    signals = {
        "outcome_class": outcome.get("outcome"),
        "permission_denials": outcome.get("permission_denials"),
        "result_text": outcome.get("result_text"),
        "lint_clean": lint["clean"],
        "lint_new_error_suspected": lint["new_error_suspected"],
        "lint_new_warning_only": lint["new_warning_only"],
        "commit_count": closure["commit_count"],
        "signature_complete": closure["signature_complete"],
        "bundle": closure["bundle"],
        "dirty_remainder": closure["dirty_remainder"],
        "item_fields_available": item_after["available"],
        "item_status": item_after.get("status"),
        "pending_work_nonempty": item_after.get("pending_work_nonempty", False),
        "known_deviations_nonempty": item_after.get("known_deviations_nonempty", False),
        "escalation_needed_yes": item_after.get("escalation_needed_yes", False),
    }
    klass, matched = _classify(signals)
    return {
        "verdict": klass,
        "signals_matched": matched,
        "lint_class": lint["lint_class"],
        "raw": {"outcome": outcome, "lint": lint, "closure": closure, "item_after": item_after,
               "plan_id": plan_id, "item_id": item_id, "phase_id": phase_id},
    }
