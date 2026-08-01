"""worker — запуск ОДНОГО item'а плана процессом клиента `-p` под таймаутом (P4.3,
`root/contracts/driver-plan-protocol-v2.md` §6/§9 U1-U3).

Процессный запуск, не Agent tool (`findings/rag-2026-07-31-native-skill-fields.md` §5 —
подавление AgentTool приходит инъецированной системной инструкцией, не версией API) и
СТРОГО один воркер за раз (D8 — CooperBench, там же §6): публичная функция принимает
ровно один item, пула/списка в модуле нет.

argv, селекторы модели/effort и шаблон инвокации ЧИТАЮТСЯ из committed-носителя
`packages/task/configs/command-routing.json` (`mappings.claude-code.class_selectors` /
`effort_selectors` / `invocation_binding.template`) — конкретные имена моделей в этом
модуле не хардкодятся (Implementation Rule 2). Способ запуска и разбора JSON-конверта
взят по образцу `skiller/lib/skiller/quality/eval.py:377-445` (`claude_bin`,
`build_run_cmd`, `_parse_claude_json`) — свой второй носитель правды о вызове клиента
здесь не заводится, включая имя env-override бинаря (тот же `SKM_CLAUDE_BIN`).

Классификация — исход ПРОГОНА, не вердикт по item'у (вердикт выносит `gate`, P4.4, по
четырём источникам): `ok` / `transport` / `timeout` / `quota` / `error`. Успех = дословно
`type=="result"` И `is_error==false` И exit code 0 — НИКОГДА «stdout непустой» (единственное
правило, унаследованное от историчного донора дословно, §6.3 контракта). Любое
неизвестное сочетание полей конверта → `transport` с честной причиной — догадка о классе
запрещена (Implementation Rule 9); `[UNVERIFIED]`-пункты контракта (U1-U3) закрываются
этим модулем НАБЛЮДЕНИЕМ, а не подгонкой парсера под предположение.

Функции чистые (аргументы → dict), кроме `WorkerUnavailable` — она бросается ТОЛЬКО на
предусловии (носитель routing недоступен, бинарь `claude` не найден), до спавна процесса,
и это fail-loud, не тихий дефолт (Implementation Rule 2). Сам прогон исключений наружу не
бросает: таймаут и битый конверт — структурные классы исхода, не падение. stdlib-only."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from core import find_monorepo_root

# --- закрытый enum исходов прогона (не вердикт по item'у — Code Guidance, анти-самообман) --
OUTCOME_OK = "ok"
OUTCOME_TRANSPORT = "transport"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_QUOTA = "quota"
OUTCOME_ERROR = "error"

# Тот же рычаг подмены бинаря, что уже живёт в skiller (quality/eval.py) — один env-override
# на весь зонтик, не второй с другим именем (Code Guidance «запрет второго прибора»).
CLAUDE_BIN_ENV = "SKM_CLAUDE_BIN"

# Провайдер и command_id — из command-routing.json (P4.1 §10: граница провайдера v2 — ровно
# `claude -p`); command_id называет РЕАЛЬНО закрываемую этим воркером команду плана.
PROVIDER_ID = "claude-code"
WORKER_COMMAND_ID = "task:plan-exec"

# Таймаут — предохранитель волны, не среднее время прогона: реальный item несёт
# реализацию + доведение тестов до зелёного + два коммита, поэтому граница взята с большим
# запасом над «служебным» вызовом (0.08-0.17 USD / считанные секунды из
# `findings/P4-headless-envelope-2026-07-31.md`), а не по нему. Флага `--max-turns` у
# клиента нет (§1 того же файла) — ограничение длины прогона обязано быть таймаутом
# процесса, переопределяется параметром `run(..., timeout=...)`.
DEFAULT_TIMEOUT = 1800  # сек (30 минут) на один item волны

# Донорский литерал (D18, единственные два маркера, которые контракт называет по имени;
# `[UNVERIFIED]` U1 — боевая квота не воспроизводилась, наблюдение первого боевого
# исчерпания бампает контракт и, при новом машинном признаке, этот список).
_QUOTA_TEXT_MARKERS = ("session limit", "weekly limit")


class WorkerUnavailable(RuntimeError):
    """Носитель `command-routing.json` недоступен, селектор/шаблон в нём не назван, либо
    бинарь клиента не найден — предусловие прогона, не исход прогона (fail-loud перед
    спавном процесса, Implementation Rule 2)."""


def resolve_claude_bin():
    """Путь к CLI клиента: env-override → PATH. `None`, если не найден ни там, ни там."""
    override = os.environ.get(CLAUDE_BIN_ENV)
    if override:
        p = Path(os.path.expanduser(override))
        return str(p) if p.exists() else None
    return shutil.which("claude")


def _load_routing_config(monorepo_root):
    path = Path(monorepo_root) / "packages" / "task" / "configs" / "command-routing.json"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path} не читается: {exc}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"{path} не JSON: {exc}"


def _first(selectors):
    return selectors[0] if isinstance(selectors, list) and selectors else None


def build_argv(plan_id, item_id, *, model_class, effort, monorepo_root, claude_bin):
    """Argv ОДНОГО прогона — единственная функция сборки (Implementation Rule 1): тест
    сверяет список дословно, строковая конкатенация и `shell=True` не применяются. Селекторы
    и шаблон инвокации берутся ТОЛЬКО из `command-routing.json`; носитель неполон/недоступен
    → `WorkerUnavailable` (fail-loud, не дефолт «наугад»)."""
    routing, reason = _load_routing_config(monorepo_root)
    if routing is None:
        raise WorkerUnavailable(f"носитель маршрутизации недоступен: {reason}")

    mapping = ((routing.get("mappings") or {}).get(PROVIDER_ID)) or {}
    model_selector = _first((mapping.get("class_selectors") or {}).get(model_class))
    effort_selector = _first((mapping.get("effort_selectors") or {}).get(effort))
    template = (mapping.get("invocation_binding") or {}).get("template")

    if model_selector is None:
        raise WorkerUnavailable(
            f"command-routing.json: нет селектора класса {model_class!r} для {PROVIDER_ID!r}")
    if effort_selector is None:
        raise WorkerUnavailable(
            f"command-routing.json: нет селектора effort {effort!r} для {PROVIDER_ID!r}")
    if not template:
        raise WorkerUnavailable(
            f"command-routing.json: нет invocation_binding.template для {PROVIDER_ID!r}")

    invocation = template.format(command_id=WORKER_COMMAND_ID, arguments=f"{plan_id} {item_id}")
    return [claude_bin, "-p", invocation, "--output-format", "json",
            "--model", model_selector, "--effort", effort_selector]


def _capture_client_version(claude_bin_path, *, timeout=10):
    """`claude --version` ДО прогона — вердикт без версии клиента недействителен (правило
    унаследовано от донора и от `plan.md` §2). Best-effort: сбой снятия версии саму попытку
    прогона item'а не блокирует, `None` — честный признак «не снята»."""
    try:
        proc = subprocess.run([claude_bin_path, "--version"], capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout else None


def _is_quota_text(text):
    lowered = text.lower()
    return any(marker in lowered for marker in _QUOTA_TEXT_MARKERS)


def _outcome(kind, *, argv, client_version, reason=None, raw_stdout=None, exit_code=None,
            envelope=None):
    envelope = envelope or {}
    return {
        "outcome": kind,
        "reason": reason,
        "argv": list(argv),
        "client_version": client_version,
        "exit_code": exit_code,
        "session_id": envelope.get("session_id"),
        "total_cost_usd": envelope.get("total_cost_usd"),
        "num_turns": envelope.get("num_turns"),
        "duration_ms": envelope.get("duration_ms"),
        "permission_denials": envelope.get("permission_denials"),
        "subtype": envelope.get("subtype"),
        "stop_reason": envelope.get("stop_reason"),
        "terminal_reason": envelope.get("terminal_reason"),
        "api_error_status": envelope.get("api_error_status"),
        "result_text": envelope.get("result"),
        "raw_stdout": raw_stdout,
    }


def _classify_envelope(proc, argv, client_version):
    """Дефенсивный разбор (§6.3 контракта): успех РОВНО `type=="result"` И `is_error==false`
    И exit code 0. Битый/пустой/не-`result` JSON и любое ДРУГОЕ неизвестное сочетание полей
    → `transport` с честной причиной (Implementation Rule 5/9) — сырой stdout сохраняется
    усечённо, трейсбек наружу не летит."""
    raw = proc.stdout or ""
    try:
        envelope = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        envelope = None

    if not isinstance(envelope, dict) or envelope.get("type") != "result":
        return _outcome(OUTCOME_TRANSPORT, argv=argv, client_version=client_version,
                        reason="конверт битый, пустой или не `result`",
                        raw_stdout=raw[:2000], exit_code=proc.returncode)

    is_error = envelope.get("is_error")
    if is_error is False and proc.returncode == 0:
        return _outcome(OUTCOME_OK, argv=argv, client_version=client_version,
                        exit_code=proc.returncode, envelope=envelope)
    if is_error is True:
        kind = OUTCOME_QUOTA if _is_quota_text(str(envelope.get("result") or "")) else OUTCOME_ERROR
        return _outcome(kind, argv=argv, client_version=client_version,
                        exit_code=proc.returncode, envelope=envelope)

    # `is_error` отсутствует / не булев, либо расходится с exit code — неизвестное
    # сочетание, догадка о классе запрещена (Implementation Rule 9).
    return _outcome(OUTCOME_TRANSPORT, argv=argv, client_version=client_version,
                    reason=f"неизвестное сочетание is_error={is_error!r} / exit={proc.returncode}",
                    raw_stdout=raw[:2000], exit_code=proc.returncode, envelope=envelope)


def run(plan_id, item_id, *, model_class, effort, monorepo_root=None, claude_bin=None,
        timeout=DEFAULT_TIMEOUT):
    """Один прогон `-p "/task:plan-exec <plan_id> <item_id>" --output-format json` под
    таймаутом. `--permission-mode` НЕ выставляется (Scope Excluded — политика прогона
    остаётся окружением владельца; отказ разрешения наблюдается штатно через
    `permission_denials`), `--bare` не применяется (отключил бы хуки/скиллы/`CLAUDE.md`,
    ради которых волна и запускается). Ретрая нет ни одного тира (D9).

    Предусловия (носитель routing, бинарь клиента) недоступны → `WorkerUnavailable`, ДО
    спавна процесса. Сам прогон исключений не бросает: таймаут/битый конверт — структурные
    классы исхода в возвращаемом словаре, не падение вызывающего кода."""
    if monorepo_root is None:
        monorepo_root = find_monorepo_root(Path.cwd())
        if monorepo_root is None:
            raise WorkerUnavailable(
                "монорепо-корень не найден — носитель command-routing.json недоступен "
                "(standalone-раскладка без пакета `task`)")
    monorepo_root = Path(monorepo_root)

    resolved_bin = claude_bin or resolve_claude_bin()
    if resolved_bin is None:
        raise WorkerUnavailable(f"бинарь клиента не найден (env {CLAUDE_BIN_ENV} → PATH)")

    argv = build_argv(plan_id, item_id, model_class=model_class, effort=effort,
                      monorepo_root=monorepo_root, claude_bin=resolved_bin)
    client_version = _capture_client_version(resolved_bin)

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return _outcome(OUTCOME_TIMEOUT, argv=argv, client_version=client_version,
                        reason=f"процесс не завершился за {timeout}s")
    except OSError as exc:
        return _outcome(OUTCOME_TRANSPORT, argv=argv, client_version=client_version,
                        reason=f"процесс не запустился: {exc}")

    return _classify_envelope(proc, argv, client_version)
