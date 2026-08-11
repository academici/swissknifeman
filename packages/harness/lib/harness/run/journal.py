"""journal — дозапись в `plans/<ID>/journal.jsonl` СУЩЕСТВУЮЩИМ CLI ровно тех событий,
которых воркер физически записать не мог.

Живой driver/journal contract — `packages/harness/docs/reference/exec-wave.md` и
Task plan-protocol; D32 сохранён ниже как provenance правила single-writer.

`/task:plan-exec` (и его `plan-run`-форма) пишет журнал САМ: старт-запись `in-progress` и
финал-запись `closed-green`/`closed-deviations`/`escalated`/`blocked` (`plan-exec.md` шаги 3
и 7). Драйвер, пишущий СВОЮ строку на каждый прогон, удвоил бы историю плана. Правило (D32):
драйвер пишет строку РОВНО там, где сессии воркера не было или она не дошла до
close-протокола — то есть когда исход прогона (`harness.run.worker`) не `ok`, ИЛИ статус
item'а после прогона остался нетерминальным (`🟡 In progress`/`⬜ Not started` — тот же
предикат, что и `_TABLE`-строка `no-op` в `harness.run.gate`, не второй его носитель).
Дискриминатор строк драйвера — штатное поле схемы `run_id` (у строк воркера оно `null`,
`plan-exec.md` его не передаёт), плюс префикс `[wave <run_id>]` в `note`.

Формат журнала не изобретается: `result`/`friction` берутся ТОЛЬКО из закрытых enum'ов
`task.journal` (`RESULT_VALUES`/`FRICTION_VALUES`) — неизвестное сочетание отказывает писать
строку (`JournalWriteRefused`), а не подбирает похожее значение (Implementation Rule 3):
журнал append-only, а schema-invalid строку нельзя переписать (`plan-protocol` §2, D51).

Межпакетная граница — процесс, а не импорт (D29, тот же принцип, что у `plan_reader`/`worker`/
`gate`): запись идёт вызовом `python3 -m task.journal append …` под PYTHONPATH,
СОБРАННЫМ ИЗ ОТДЕЛЬНЫХ СЕГМЕНТОВ ПУТИ (не как склеенный литерал — та же дисциплина, что
`harness.run.gate._run_plan_lint` уже применяет к пути `plan-lint.py`); прямого импорта
пакета-владельца здесь нет ни строкой.

Функции чистые, кроме явного процессного вызова CLI; `JournalUnavailable` — структурная
невозможность вызвать `task.journal` (монорепо-корень не найден, CLI не запустился/не
уложился в таймаут), `JournalCallFailed` — CLI запустился, но вернул ненулевой код
(Implementation Rule 4: волна ОСТАНАВЛИВАЕТСЯ, тихая потеря записи в durable-истории плана
запрещена). stdlib-only."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from core import find_monorepo_root

from harness.run import worker

# --- закрытый набор категорий драйверской строки и «кто пишет» (D32, Scope Included) ---
DRIVER = "driver"
WORKER = "worker"

CATEGORY_ROUTING_BLOCKED = "routing-blocked"
CATEGORY_NO_OP = "no-op"
CATEGORY_OK_TERMINAL = "ok-terminal"

# «исход → кто пишет строку» — ДАННЫЕ модуля (Scope Included), не рассыпанные if:
# воркер пишет свою финал-запись САМ РОВНО когда прогон дал `ok` И статус item'а после
# него терминален (`plan-exec.md` self-closing дошёл до конца); во всех прочих случаях
# сессии либо не было (`routing-blocked`), либо она не дошла до close-протокола.
WHO_WRITES = (
    (CATEGORY_ROUTING_BLOCKED, DRIVER),
    (worker.OUTCOME_TIMEOUT, DRIVER),
    (worker.OUTCOME_TRANSPORT, DRIVER),
    (worker.OUTCOME_QUOTA, DRIVER),
    (worker.OUTCOME_ERROR, DRIVER),
    (CATEGORY_NO_OP, DRIVER),
    (CATEGORY_OK_TERMINAL, WORKER),
)
_WHO_WRITES = dict(WHO_WRITES)

# «категория драйверской строки → (result, friction)» ТОЛЬКО из закрытых enum'ов
# `task.journal` (`RESULT_VALUES`/`FRICTION_VALUES`) — проверено против CLI живьём в
# тестах (`--help`), здесь не переиздаётся вторым enum'ом, а называется буквально теми же
# строками. Технические сбои прогона (timeout/transport/quota/error) не несут отдельного
# friction-значения — ни одно значение закрытого enum'а их не описывает честно, а
# подбирать ближайшее запрещено (Implementation Rule 3); "blocked" описывает их всех
# одинаково честно: сессия не дошла до close-протокола.
_RESULT_FRICTION = {
    CATEGORY_ROUTING_BLOCKED: ("blocked", ("routing-blocked",)),
    worker.OUTCOME_TIMEOUT: ("blocked", ()),
    worker.OUTCOME_TRANSPORT: ("blocked", ()),
    worker.OUTCOME_QUOTA: ("blocked", ()),
    worker.OUTCOME_ERROR: ("blocked", ()),
    CATEGORY_NO_OP: ("no-op", ("no-op",)),
}

# Статус item'а, при котором close-протокол заведомо не дошёл до конца (тот же предикат,
# что строка `no-op` таблицы `harness.run.gate.TABLE` — не второй носитель правды о
# статусах, повторение ДВУХ конкретных литералов оттуда, а не импорт таблицы целиком).
_NON_TERMINAL_STATUSES = frozenset({"🟡 In progress", "⬜ Not started"})

# Команда, которую всегда запускает воркер (`harness.run.worker.WORKER_COMMAND_ID`,
# `"task:plan-exec"`) — тот же литерал без префикса семейства, не второй носитель.
_DRIVER_COMMAND = worker.WORKER_COMMAND_ID.rsplit(":", 1)[-1]


class JournalUnavailable(RuntimeError):
    """Монорепо-корень не найден или процессный CLI `task.journal` структурно не
    запустился/не уложился в таймаут — отказ ДО оценки исхода записи (fail-loud, тот же
    класс, что `WorkerUnavailable`/`GateUnavailable` у P4.3/P4.4)."""


class JournalWriteRefused(RuntimeError):
    """Неизвестное сочетание исхода прогона / статуса item'а — строка НЕ пишется вовсе
    (Implementation Rule 3): append-only журнал не даёт переписать неверную строку, поэтому
    при сомнении она честно не появляется, а не подбирается по ближайшему enum-значению."""


class JournalCallFailed(RuntimeError):
    """`task.journal append` запустился, но вернул ненулевой код — волна ОСТАНАВЛИВАЕТСЯ
    (Implementation Rule 4): тихая потеря записи в durable-истории плана запрещена."""


def classify(*, pre_launch, outcome=None, item_status=None):
    """Категория строки волны по D32 (`WHO_WRITES`). `pre_launch=True` — item не
    запускался вовсе (отказ `plan_reader`/`gate.pre_launch_verdict`, P4.2/P4.4), `outcome`/
    `item_status` не читаются. Иначе — по исходу прогона (`outcome["outcome"]`, закрытый
    enum `harness.run.worker`) и терминальности статуса item'а ПОСЛЕ прогона. Возвращает
    `(category, who)`; `who == WORKER` — драйвер строку НЕ пишет."""
    if pre_launch:
        return CATEGORY_ROUTING_BLOCKED, _WHO_WRITES[CATEGORY_ROUTING_BLOCKED]

    kind = (outcome or {}).get("outcome")
    if kind == worker.OUTCOME_OK:
        terminal = item_status not in _NON_TERMINAL_STATUSES
        category = CATEGORY_OK_TERMINAL if terminal else CATEGORY_NO_OP
        return category, _WHO_WRITES[category]
    if kind in _WHO_WRITES:
        return kind, _WHO_WRITES[kind]
    raise JournalWriteRefused(
        f"неизвестный исход прогона {kind!r} — строка НЕ пишется (Implementation Rule 3)")


# --- процессный вызов `task.journal append` ------------------------------------

def _build_argv(*, plan_dir, plan_id, item_id, run_id, attempt, actor, result, friction, note,
                session_id=None, cost_usd=None, num_turns=None, duration_ms=None):
    argv = ["python3", "-m", "task.journal", "append",
           "--plan-dir", str(plan_dir), "--plan", plan_id, "--item", item_id,
           "--command", _DRIVER_COMMAND, "--result", result, "--actor", actor,
           "--run-id", run_id, "--attempt", str(attempt)]
    if friction:
        argv += ["--friction", ",".join(friction)]
    if session_id is not None:
        argv += ["--session-id", session_id]
    if cost_usd is not None:
        argv += ["--cost-usd", str(cost_usd)]
    if num_turns is not None:
        argv += ["--num-turns", str(num_turns)]
    if duration_ms is not None:
        argv += ["--duration-ms", str(duration_ms)]
    if note is not None:
        argv += ["--note", note]
    return argv


def _task_lib_path(monorepo_root):
    # Сегменты по отдельности, не единый склеенный литерал пути — та же дисциплина, что
    # `harness.run.gate._run_plan_lint` уже применяет к пути `plan-lint.py` (докстринг
    # модуля, P4.2 Completion Notes: грep на литерал не должен ловить объяснение правила).
    return Path(monorepo_root).joinpath("packages", "task", "lib")


def _resolve_monorepo_root(monorepo_root, plan_dir):
    if monorepo_root is not None:
        return Path(monorepo_root)
    root = find_monorepo_root(Path(plan_dir).resolve())
    if root is None:
        raise JournalUnavailable(
            "монорепо-корень не найден — процессный CLI журнала недоступен "
            "(standalone-раскладка без пакета-владельца)")
    return root


def _run_cli(argv, *, monorepo_root, plan_dir, timeout):
    root = _resolve_monorepo_root(monorepo_root, plan_dir)
    env = dict(os.environ)
    lib_path = str(_task_lib_path(root))
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = lib_path if not existing else os.pathsep.join([lib_path, existing])
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise JournalUnavailable(f"процессный CLI журнала не выполнился: {exc}") from exc


def _build_note(run_id, category, *, outcome=None, refusal_detail=None):
    prefix = f"[wave {run_id}]"
    if category == CATEGORY_ROUTING_BLOCKED:
        return f"{prefix} routing-blocked: {refusal_detail or 'item не запускался'}"
    if category == CATEGORY_NO_OP:
        return f"{prefix} прогон завершился, но статус item'а не сдвинулся (no-op)"
    reason = (outcome or {}).get("reason") or category
    return f"{prefix} {category}: {reason}"


# --- публичный API ---------------------------------------------------------------

def maybe_write(plan_dir, plan_id, item_id, *, run_id, attempt, actor, pre_launch=False,
                refusal_detail=None, outcome=None, item_status=None, monorepo_root=None,
                timeout=30):
    """Пишет драйверскую строку журнала РОВНО когда `classify()` относит исход к `DRIVER`
    (Implementation Rule 1); когда воркер уже закрыл item сам — не пишет вовсе и
    возвращает `None` (Implementation Rule «двойной записи нет»). `run_id` ОБЯЗАН быть
    задан — это дискриминатор строк драйвера (Implementation Rule 2), пустое значение
    ломало бы отличимость от строк воркера. Возвращает записанную строку как `dict`
    (категория/`result`/`friction`/`note`/`argv`) либо `None`. `JournalWriteRefused` —
    неизвестное сочетание, строка не пишется вовсе (не вызывает CLI). `JournalCallFailed` —
    CLI вернул ненулевой код, волна обязана остановиться."""
    if not run_id:
        raise ValueError("run_id обязателен для драйверской строки (дискриминатор IR2)")

    category, who = classify(pre_launch=pre_launch, outcome=outcome, item_status=item_status)
    if who == WORKER:
        return None

    result, friction = _RESULT_FRICTION[category]
    note = _build_note(run_id, category, outcome=outcome, refusal_detail=refusal_detail)
    argv = _build_argv(
        plan_dir=plan_dir, plan_id=plan_id, item_id=item_id, run_id=run_id, attempt=attempt,
        actor=actor, result=result, friction=friction, note=note,
        session_id=(outcome or {}).get("session_id"),
        cost_usd=(outcome or {}).get("total_cost_usd"),
        num_turns=(outcome or {}).get("num_turns"),
        duration_ms=(outcome or {}).get("duration_ms"))

    proc = _run_cli(argv, monorepo_root=monorepo_root, plan_dir=plan_dir, timeout=timeout)
    if proc.returncode != 0:
        raise JournalCallFailed(
            f"task.journal append вернул {proc.returncode}: {(proc.stderr or '').strip()[-400:]}")
    return {"category": category, "result": result, "friction": list(friction), "note": note,
           "argv": argv}


def summarize_wave(run_id, records):
    """Сводка волны КАК ДАННЫЕ (Deliverables P4.5) — из уже посчитанного вызывающим
    (P4.6), второй параллельный счётчик здесь не заводится (Implementation Rule 5).
    `records` — по одному на каждый item очереди, в порядке прогона: `{"item_id": str,
    "verdict": "GREEN"|"ATTENTION"|"RED", "outcome": dict|None, "wrote_driver_line":
    bool}` — те же структуры, что уже вернули `worker.run()`/`gate.verdict()`/
    `maybe_write()`. Числа сводки несут якорь `run_id`/`client_versions` (Implementation
    Rule 7); якорь коммита добавляет печатающий слой P4.6, здесь его нет."""
    counts = {"GREEN": 0, "ATTENTION": 0, "RED": 0}
    interventions = 0
    cost_total, cost_seen = 0.0, False
    duration_total, duration_seen = 0.0, False
    client_versions = set()

    for record in records:
        verdict = record["verdict"]
        counts[verdict] = counts.get(verdict, 0) + 1
        if record.get("wrote_driver_line"):
            interventions += 1
        outcome = record.get("outcome") or {}
        cost = outcome.get("total_cost_usd")
        if cost is not None:
            cost_total += cost
            cost_seen = True
        duration = outcome.get("duration_ms")
        if duration is not None:
            duration_total += duration
            duration_seen = True
        client_version = outcome.get("client_version")
        if client_version:
            client_versions.add(client_version)

    return {
        "run_id": run_id,
        "queued": len(records),
        "green": counts["GREEN"],
        "attention": counts["ATTENTION"],
        "red": counts["RED"],
        "interventions": interventions,
        "cost_usd_total": cost_total if cost_seen else None,
        "duration_ms_total": duration_total if duration_seen else None,
        "client_versions": sorted(client_versions),
        "verdicts": [{"item_id": r["item_id"], "verdict": r["verdict"]} for r in records],
    }
