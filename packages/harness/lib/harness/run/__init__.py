"""run — драйвер exec-волны.

Живой public contract описан в `packages/harness/docs/reference/exec-wave.md`;
plan-carrier semantics принадлежит plan-protocol, а не архивному плану-донору.

Четыре модуля разделяют очередь (`plan_reader`), запуск (`worker`), вердикт
(`gate`) и durable журнал/сводку (`journal`). CLI-склейка `cmd_run(env, argv)`:
регистрируется в `cli.COMMANDS["run"]`, ничего из четырёх модулей не
переразбирает — только вызывает их публичный API в порядке очередь → воркер →
вердикт → журнал, последовательно (D8), с остановкой волны на первом RED
(Implementation Rule 3 P4.6) и продолжением на ATTENTION.

`--dry-run` не спавнит воркера и не пишет журнал (read-only, Implementation
Rule 2): печатает очередь `plan_reader.queue()` как есть, плюс — для КАЖДОГО
item'а — точный argv, который дал бы `worker.build_argv()` (или причину, по
которой argv не собрать: клиент не найден / носитель маршрутизации неполон),
без обращения к `worker.run()`.

Межпакетная граница воспроизведена ЗДЕСЬ так же, как в trех модулях-донорах
(D29): `plans_root` — где искать `<PLAN-ID>/plan.md` (по умолчанию
`<монорепо>/plans`, флаг `--plans-root` — единственное переопределение, нужен
приёмке P4.6 на изолированной фикстуре); `monorepo_root` — где искать сам
пакет `task` (`packages/task/...`) — резолвится ОТ `env.root` (корень пакета
`harness`, ВСЕГДА внутри монорепо-владельца), а не от `plan_dir`: фикстурный
план физически лежит в другом git-репозитории, но инструментарий (`plan-lint.py`,
`task.task_contract`, `task.journal`, `command-routing.json`) остаётся ОДНИМ —
тем же паттерном уже пользуются тесты `test_run_gate.py`/`test_run_worker.py`
(`monorepo_root=REPO_ROOT`, явно переданный поверх любого расположения фикстуры)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from core import find_monorepo_root

from ..common import die, parse_args
from . import plan_reader  # noqa: F401  (порядок важен — см. докстринг `journal`, D29)
from . import worker
from . import gate
from . import journal

RUN_USAGE = (
    "harness run <PLAN-ID> <Pn> [--dry-run] [--limit N] [--timeout S]\n"
    "                            [--plans-root PATH] [--json]\n"
    "  <PLAN-ID>          план (каталог `<plans-root>/<PLAN-ID>`)\n"
    "  <Pn>               фаза (например P4)\n"
    "  --dry-run          только очередь/маршруты/argv/причины отказов, БЕЗ спавна и\n"
    "                     БЕЗ единой записи (read-only, проверяется `git status --porcelain`)\n"
    "  --limit N          максимум item'ов волны (дефолт — вся очередь)\n"
    f"  --timeout S        таймаут ОДНОГО прогона воркера, секунды (дефолт {worker.DEFAULT_TIMEOUT})\n"
    "  --plans-root PATH  каталог, где искать `<PLAN-ID>/plan.md` (дефолт — `<монорепо>/plans`)\n"
    "  --json             та же сводка машинно (valid JSON, ensure_ascii=False)\n"
    "Волна последовательная (D8) и останавливается на ПЕРВОМ RED; ATTENTION не\n"
    "останавливает волну, но выносится в сводку поимённо. Ретрая нет ни одного тира (D9).\n"
    "exit-code: 0 — волна отработала (RED в середине волны — вердикт, не ошибка\n"
    "использования); ненулевой — ТОЛЬКО отказ разбора флагов / структурная недоступность\n"
    "(монорепо-корень / очередь не резолвятся)."
)


def _resolve_plan_dir(env, opts, plan_id):
    monorepo_root = find_monorepo_root(env.root)
    if monorepo_root is None:
        die("монорепо-корень не найден — пакет `task` недоступен (standalone-раскладка)")
        return None, None
    plans_root = Path(opts["plans_root"]) if opts["plans_root"] else monorepo_root / "plans"
    return monorepo_root, plans_root / plan_id


def _dry_run_argv(plan_id, item, *, monorepo_root, claude_bin):
    """Точный argv одного item'а БЕЗ спавна (Implementation Rule 2) — та же сборка,
    что `worker.build_argv`, здесь не переизобретается вторым носителем. Отсутствие
    клиента/носителя маршрутизации — честная причина в `argv_error`, не тихий null."""
    if not item["drivable"]:
        return None, None
    if claude_bin is None:
        return None, f"клиент claude не найден ({worker.CLAUDE_BIN_ENV} / PATH)"
    route = item["route"]
    try:
        argv = worker.build_argv(plan_id, item["item_id"], model_class=route["model_class"],
                                 effort=route["effort"], monorepo_root=monorepo_root,
                                 claude_bin=claude_bin)
    except worker.WorkerUnavailable as exc:
        return None, str(exc)
    return argv, None


def _print_dry_run(queue, plan_id, phase_id, *, monorepo_root, as_json):
    claude_bin = worker.resolve_claude_bin()
    items = []
    for item in queue["items"]:
        argv, argv_error = _dry_run_argv(plan_id, item, monorepo_root=monorepo_root,
                                         claude_bin=claude_bin)
        items.append({**item, "argv": argv, "argv_error": argv_error})
    payload = {
        "mode": "dry-run", "plan_id": plan_id, "phase_id": phase_id,
        "degraded": queue["degraded"], "degraded_reasons": queue["degraded_reasons"],
        "next_form": queue["next_form"], "client_bin": claude_bin,
        "items": items, "excluded_terminal": queue["excluded_terminal"],
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"dry-run: {plan_id} {phase_id} (клиент: {claude_bin or 'НЕ НАЙДЕН'})")
    if queue["degraded"]:
        print(f"  ОЧЕРЕДЬ НЕДОСТУПНА: {'; '.join(queue['degraded_reasons'])}")
        return
    print(f"  next_form: {queue['next_form']['kind']!r} ({queue['next_form']['declaring_line']!r})")
    print(f"  терминальных (исключены из очереди): {len(queue['excluded_terminal'])}")
    for item in items:
        marker = "ВОЖДЕНИЕ" if item["drivable"] else "ОТКАЗ"
        print(f"  [{marker}] {item['item_id']} — status={item['status']!r} exec={item['exec']!r}")
        if item["route"]:
            print(f"      route: {item['route']['model_class']}/{item['route']['effort']}")
        if not item["drivable"]:
            print(f"      причина: {item['refusal']} — {item['refusal_detail']}")
        elif item["argv"]:
            print(f"      argv: {item['argv']}")
        elif item["argv_error"]:
            print(f"      argv недоступен: {item['argv_error']}")
    for excl in queue["excluded_terminal"]:
        print(f"  [ТЕРМИНАЛЕН] {excl['item_id']} — status={excl['status']!r}")


def _item_actor(item):
    route = item.get("route")
    return f"{route['model_class']}/{route['effort']}" if route else "driver"


def _run_wave(env, opts, plan_id, phase_id, monorepo_root, plan_dir, *, limit, timeout):
    queue = plan_reader.queue(plan_dir, phase_id, monorepo_root=monorepo_root)
    if queue["degraded"]:
        die(f"очередь недоступна: {'; '.join(queue['degraded_reasons'])}")
        return None

    items = queue["items"]
    if limit is not None:
        items = items[:limit]

    run_id = f"wave-{plan_id}-{phase_id}-{uuid.uuid4().hex[:12]}"
    records = []
    for item in items:
        item_id = item["item_id"]
        actor = _item_actor(item)

        if not item["drivable"]:
            verdict = gate.pre_launch_verdict(item)
            jrec = journal.maybe_write(
                plan_dir, plan_id, item_id, run_id=run_id, attempt=1, actor=actor,
                pre_launch=True, refusal_detail=item.get("refusal_detail"),
                monorepo_root=monorepo_root)
            records.append({"item_id": item_id, "verdict": verdict["verdict"],
                            "outcome": None, "wrote_driver_line": jrec is not None,
                            "verdict_detail": verdict})
        else:
            before = gate.snapshot_before(plan_dir)
            outcome = worker.run(plan_id, item_id, model_class=item["route"]["model_class"],
                                 effort=item["route"]["effort"], monorepo_root=monorepo_root,
                                 timeout=timeout)
            verdict = gate.verdict(plan_id, item_id, phase_id, plan_dir, before, outcome,
                                   monorepo_root=monorepo_root)
            item_status = (verdict["raw"]["item_after"] or {}).get("status")
            jrec = journal.maybe_write(
                plan_dir, plan_id, item_id, run_id=run_id, attempt=1, actor=actor,
                pre_launch=False, outcome=outcome, item_status=item_status,
                monorepo_root=monorepo_root)
            records.append({"item_id": item_id, "verdict": verdict["verdict"],
                            "outcome": outcome, "wrote_driver_line": jrec is not None,
                            "verdict_detail": verdict})

        if records[-1]["verdict"] == gate.RED:
            break

    return run_id, records


def _print_wave(run_id, records, plan_id, phase_id, *, as_json):
    summary = journal.summarize_wave(run_id, records)
    if as_json:
        print(json.dumps({**summary, "plan_id": plan_id, "phase_id": phase_id,
                          "records": records}, ensure_ascii=False, indent=2, default=str))
        return

    print(f"волна {run_id} — {plan_id} {phase_id}")
    print(f"  ведено {summary['queued']} — GREEN {summary['green']} / "
         f"ATTENTION {summary['attention']} / RED {summary['red']}")
    print(f"  вмешательств драйвера: {summary['interventions']}")
    if summary["cost_usd_total"] is not None:
        print(f"  cost_usd: {summary['cost_usd_total']:.4f}")
    if summary["duration_ms_total"] is not None:
        print(f"  duration_ms: {summary['duration_ms_total']:.0f}")
    if summary["client_versions"]:
        print(f"  client_versions: {', '.join(summary['client_versions'])}")
    for v in summary["verdicts"]:
        print(f"  [{v['verdict']}] {v['item_id']}")


def cmd_run(env, argv):
    """`harness run <PLAN-ID> <Pn> ...` (P4.6) — последовательная волна
    `plan_reader.queue()` → (`worker.run()` → `gate.verdict()`) → `journal.maybe_write()`
    по items фазы `Pn` плана `PLAN-ID`; печатает сводку (`journal.summarize_wave()`).
    `--dry-run` — только чтение, см. `_print_dry_run`."""
    opts, positionals = parse_args(argv, {
        "--dry-run": "bool", "--limit": "str", "--timeout": "str",
        "--plans-root": "str", "--json": "bool",
    }, max_pos=2)
    if opts["help"] or not positionals:
        print(RUN_USAGE)
        return
    if len(positionals) != 2:
        die(f"ожидается ровно 2 позиционных аргумента: <PLAN-ID> <Pn>, получено: {positionals!r}")
        return
    plan_id, phase_id = positionals

    limit = None
    if opts["limit"]:
        try:
            limit = int(opts["limit"])
        except ValueError:
            die(f"--limit ожидает целое число, получено: {opts['limit']!r}")
            return

    timeout = worker.DEFAULT_TIMEOUT
    if opts["timeout"]:
        try:
            timeout = float(opts["timeout"])
        except ValueError:
            die(f"--timeout ожидает число секунд, получено: {opts['timeout']!r}")
            return

    monorepo_root, plan_dir = _resolve_plan_dir(env, opts, plan_id)
    if monorepo_root is None:
        return

    if opts["dry_run"]:
        queue = plan_reader.queue(plan_dir, phase_id, monorepo_root=monorepo_root)
        _print_dry_run(queue, plan_id, phase_id, monorepo_root=monorepo_root,
                       as_json=opts["json"])
        return

    result = _run_wave(env, opts, plan_id, phase_id, monorepo_root, plan_dir,
                       limit=limit, timeout=timeout)
    if result is None:
        return
    run_id, records = result
    _print_wave(run_id, records, plan_id, phase_id, as_json=opts["json"])
