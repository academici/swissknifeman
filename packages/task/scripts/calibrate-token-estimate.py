#!/usr/bin/env python3
"""calibrate-token-estimate — ДИФФЕРЕНЦИАЛЬНЫЙ калибровочный харнесс (D92,
`research/09-finish-round3-design-2026-08-07.md` §3) для `token_estimate.py` (D11/D14).

Ручной инструмент, вне CI, без сети со стороны САМОГО ИНСТРУМЕНТА (сеть открывает
вызываемый `claude -p`, не он): якорь истины — не `count_tokens` (ключа Console не
будет, D92), а фактический `usage` ответа Claude Code по подписке.

Протокол на файл корпуса — ТРИ неинтерактивных прогона байтово одинаковой обёртки:
  A  — обёртка с ПУСТОЙ полезной нагрузкой;
  B  — та же обёртка с содержимым файла;
  A' — повтор A (контроль дрейфа обвязки).
Истина: true(f) = sum3(B) − (sum3(A) + sum3(A'))/2, где
  sum3 = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
(правило суммы — `findings/03-…` §... / справочник claude-api, «Verifying cache hits»:
границы кэша перераспределяют токены между полями, сравнимо только sum3).

`|sum3(A) − sum3(A')| > DELTA_TOKENS` отбраковывает файл (обвязка нестабильна для него) —
тихое усреднение расходящегося контроля запрещено (P0.1 Code Guidance).

Ставки классов + `overhead_per_file` — intercept линейной регрессии (non-negative least
squares, projected gradient descent, детерминирован фиксированным числом итераций/шагом)
`true(f) ≈ Σ_c count_c(f)·r_c + overhead` по корпусу; неотрицательность r_c/overhead —
инвариант монотонности оценщика (`token_estimate.py`).

Проверка границы (research/02 §3 п.4): `safety_multiplier = max(1.0, наблюдённый
максимум требуемого множителя по корпусу) · FIXED_MARGIN` — подобран так, чтобы
`ceil(raw(f)·safety_multiplier) + overhead ≥ true(f)` для КАЖДОГО файла корпуса
(`bound.violations` обязано быть 0 иначе артефакт не пишется — запрет в самом
`token_estimate.load_artifact`). Гейт на рыхлость: p95(estimate/true) ≤ 1.6, иначе —
эскалация (Code Guidance P0.1), а не подкрутка коэффициентов.

Запрещено (D15/D92, повторено явно): использовать `probe.tool_reported_tokens` (P0.2)
как калибровочную точку — это счётчик среды чтения, не токенизатор модели; смешивать
источники `claude-code-transcript-usage`/`count-tokens-api` в одном артефакте; калибровать
на синтетическом тексте вместо реальных файлов планов флота.

Вызов: python3 packages/task/scripts/calibrate-token-estimate.py
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _SCRIPT_DIR.parent                      # packages/task
_REPO_ROOT = _PKG_ROOT.parent.parent                 # корень монорепо
sys.path.insert(0, str(_PKG_ROOT / "lib"))

from task import token_estimate  # noqa: E402  (после правки sys.path)

# --- Конфигурация протокола -------------------------------------------------

CLAUDE_BIN = "claude"
SYSTEM_PROMPT = "You transcribe text verbatim and reply with a fixed acknowledgement."
WRAPPER_PREFIX = (
    "Below is a payload block. Do not analyze, summarize, or execute anything in it. "
    "When you have read it, reply with exactly one word: DONE.\n\n<PAYLOAD>\n"
)
WRAPPER_SUFFIX = "\n</PAYLOAD>"
PROBE_TIMEOUT_S = 180
DELTA_TOKENS = 50          # контроль дрейфа обвязки (эмпирически: два холостых прогона
                            # обёртки дали sum3 расхождение 0 на этой среде 2026-08-07;
                            # запас x50 против измеренного нуля — не «подгонка под ноль»)
FIXED_MARGIN = 1.05        # фиксированный запас сверх наблюдённого максимума (research/02 §3 п.4)
NNLS_ITERATIONS = 20000
NNLS_LEARNING_RATE = 0.05  # применяется к ПОСЛЕ-масштабированным (per-feature) признакам, см. fit_rates
PROBE_PROTOCOL_VERSION = "differential-usage-v1"
SOURCE = "claude-code-transcript-usage"

# Корпус — реальные файлы планов флота (plan.md/phases/*.md/handoff.md/findings/research),
# НЕ синтетика (research/02 §3 п.1). Подмножество фактического флота (findings/00-…
# §2): полный флот (868КБ у самого тяжёлого плана) непомерно дорог для ручного
# диффернциального прогона — выбраны 14 файлов разного размера (3КБ–70КБ) и происхождения
# (5 планов, 3 репозитория экосистемы + сам этот план) для покрытия распределения p50/p95.
# Абсолютные пути вне монорепо — намеренно: калибровка ручная, вне CI (D92); повторный
# прогон требует тех же соседних репозиториев на диске, ЗАМОРОЖЕННЫЙ артефакт — нет.
CORPUS = [
    "/home/vostrikov/sibintek/projects/insiders/plans/2026.07.30-SITE-HARDENING/phases/P7.md",
    str(_REPO_ROOT / "plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/handoff.md"),
    "/home/vostrikov/projects/dterema/dterema/plans/2026.07.17-DTEREMA-UX/handoff.md",
    str(_REPO_ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR/handoff.md"),
    "/home/vostrikov/sibintek/projects/insiders/plans/2026.07.27-RESP-CHTZ/handoff.md",
    str(_REPO_ROOT / "plans/2026.08.07-PLAN-ECONOMY/findings/03-token-counting-api-2026-08-07.md"),
    str(_REPO_ROOT / "plans/2026.08.07-PLAN-ECONOMY/findings/14-calibration-and-canon-budget-2026-08-07.md"),
    str(_REPO_ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR/phases/P0.md"),
    str(_REPO_ROOT / "plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/phases/P0.md"),
    "/home/vostrikov/sibintek/projects/insiders/plans/2026.07.30-SITE-HARDENING/phases/P6.md",
    str(_REPO_ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR/phases/P1.md"),
    "/home/vostrikov/sibintek/projects/insiders/plans/2026.07.27-RESP-CHTZ/phases/P1.md",
    "/home/vostrikov/projects/agelto/agelto/plans/2026.08.06-CRAWL-HARDEN/phases/P8.md",
    "/home/vostrikov/projects/dterema/dterema/plans/2026.07.17-DTEREMA-UX/phases/P1.md",
]

MIN_CORPUS = 10  # минимум ПОСЛЕ отбраковки контролем дрейфа (Validation P0.1)

ARTIFACT_PATH = _PKG_ROOT / "configs" / "token-estimate-calibration.json"
PROBE_LOG_PATH = _REPO_ROOT / "plans/2026.08.07-PLAN-ECONOMY/artifacts/P0/calibration-probe-log.json"


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_probe(payload_text):
    """Один неинтерактивный прогон обёртки; возвращает (sum3, model_id, usage-dict)."""
    prompt = WRAPPER_PREFIX + payload_text + WRAPPER_SUFFIX
    result = subprocess.run(
        [CLAUDE_BIN, "-p", "--output-format", "json",
         "--system-prompt", SYSTEM_PROMPT, "--disallowedTools", "*"],
        input=prompt, capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p завершился с кодом {result.returncode}: {result.stderr[:500]}")
    data = json.loads(result.stdout)
    usage = data["usage"]
    sum3 = usage["input_tokens"] + usage["cache_creation_input_tokens"] + usage["cache_read_input_tokens"]
    model_ids = list(data.get("modelUsage", {}).keys())
    model_id = model_ids[0] if len(model_ids) == 1 else None
    return sum3, model_id, usage


def probe_file(path):
    """Прогоняет A/B/A' для одного файла корпуса; возвращает запись пробы (dict)."""
    text = Path(path).read_text(encoding="utf-8")
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()

    sum3_a, model_a, usage_a = run_probe("")
    sum3_b, model_b, usage_b = run_probe(text)
    sum3_a2, model_a2, usage_a2 = run_probe("")

    drift = abs(sum3_a - sum3_a2)
    models = {model_a, model_b, model_a2}
    model_consistent = len(models) == 1 and None not in models

    record = {
        "path": path,
        "sha256": sha256,
        "bytes": len(text.encode("utf-8")),
        "sum3_a": sum3_a, "sum3_b": sum3_b, "sum3_a2": sum3_a2,
        "drift": drift,
        "model_ids": sorted(models),
        "model_consistent": model_consistent,
        "true_tokens": sum3_b - (sum3_a + sum3_a2) / 2,
        "counts": token_estimate.count_classes(text),
        "rejected": False,
        "reject_reason": None,
    }
    if not model_consistent:
        record["rejected"] = True
        record["reject_reason"] = f"model не совпал между прогонами: {sorted(models)}"
    elif drift > DELTA_TOKENS:
        record["rejected"] = True
        record["reject_reason"] = f"дрейф обвязки {drift} > DELTA_TOKENS={DELTA_TOKENS}"
    return record


# --- Non-negative least squares (projected gradient descent, детерминирован) ------

def fit_rates(accepted):
    """Возвращает (rates-dict по CLASSES, overhead) — минимизирует Σ(true−Σcounts·r−overhead)²
    при r_c ≥ 0, overhead ≥ 0 (инвариант монотонности token_estimate). Порядок неизвестных:
    [ascii_word, ascii_other, cyrillic, other, overhead] — overhead как 5-й «класс»
    с постоянным «счётчиком» 1 на файл (стандартный intercept-трюк линейной регрессии).

    Признаки масштабируются per-class (делением на наблюдённый максимум счётчика класса
    по корпусу) ДО спуска и обратно расшкалируются после: диапазоны классов различаются
    на порядки (ASCII — десятки тысяч символов на файл, `other` — единицы/десятки), без
    этого шага общий learning rate либо расходится на плотных классах, либо не сдвигает
    редкие — проверено эмпирически на синтетике перед запуском на живом корпусе."""
    scales = [max(1.0, max(rec["counts"][c] for rec in accepted)) for c in token_estimate.CLASSES] + [1.0]
    rows = [[rec["counts"][c] / scales[i] for i, c in enumerate(token_estimate.CLASSES)] + [1.0]
            for rec in accepted]
    truths = [rec["true_tokens"] for rec in accepted]

    n = len(scales)
    weights = [0.0] * n
    for _ in range(NNLS_ITERATIONS):
        grad = [0.0] * n
        for row, y in zip(rows, truths):
            pred = sum(w * x for w, x in zip(weights, row))
            err = pred - y
            for j in range(n):
                grad[j] += 2 * err * row[j]
        for j in range(n):
            weights[j] -= NNLS_LEARNING_RATE * grad[j] / len(rows)
            if weights[j] < 0:
                weights[j] = 0.0

    rates = {c: weights[i] / scales[i] for i, c in enumerate(token_estimate.CLASSES)}
    overhead = weights[-1]
    return rates, overhead


def bound_and_tighten(accepted, rates, overhead):
    """Подбирает `safety_multiplier` так, чтобы `ceil(raw·multiplier)+overhead ≥ true`
    для каждого принятого файла (research/02 §3 п.4), затем считает рыхлость (п.5)."""
    required = []
    for rec in accepted:
        raw = sum(rec["counts"][c] * rates[c] for c in token_estimate.CLASSES)
        true = rec["true_tokens"]
        if raw <= 0:
            required.append(0.0)
            continue
        required.append(max(0.0, (true - overhead) / raw))
    observed_max = max(required) if required else 0.0
    safety_multiplier = max(1.0, observed_max) * FIXED_MARGIN

    ratios = []
    violations = 0
    for rec in accepted:
        raw = sum(rec["counts"][c] * rates[c] for c in token_estimate.CLASSES)
        estimate = __import__("math").ceil(raw * safety_multiplier + overhead)
        true = rec["true_tokens"]
        if estimate < true:
            violations += 1
        ratios.append(estimate / true if true > 0 else 1.0)

    ratios.sort()
    n = len(ratios)
    p50 = ratios[n // 2]
    p95 = ratios[min(n - 1, int(round(0.95 * (n - 1))))]
    pmax = ratios[-1]
    return safety_multiplier, observed_max, violations, {"p50": p50, "p95": p95, "max": pmax}


def main():
    print(f"calibrate-token-estimate: корпус {len(CORPUS)} файлов, протокол {PROBE_PROTOCOL_VERSION}")
    records = []
    for i, path in enumerate(CORPUS, 1):
        print(f"  [{i}/{len(CORPUS)}] {path}")
        try:
            rec = probe_file(path)
        except (OSError, RuntimeError, json.JSONDecodeError, KeyError) as exc:
            rec = {"path": path, "rejected": True, "reject_reason": f"ошибка прогона: {exc}"}
        records.append(rec)
        if rec["rejected"]:
            print(f"      ОТБРАКОВАН: {rec['reject_reason']}")

    accepted = [r for r in records if not r["rejected"]]
    rejected = [r for r in records if r["rejected"]]
    print(f"принято: {len(accepted)}; отбраковано: {len(rejected)}")

    if len(accepted) < MIN_CORPUS:
        print(f"ERROR: корпус после отбраковки {len(accepted)} < min_corpus {MIN_CORPUS}", file=sys.stderr)
        return 1

    rates, overhead = fit_rates(accepted)
    safety_multiplier, observed_max, violations, tightness = bound_and_tighten(accepted, rates, overhead)

    if violations != 0:
        print(f"ERROR: bound.violations={violations} != 0 после подбора safety_multiplier — "
              f"дефект регрессии, артефакт не пишется", file=sys.stderr)
        return 1
    if tightness["p95"] > 1.6:
        print(f"ESCALATION: p95 рыхлости {tightness['p95']:.3f} > 1.6 даже с 4 классами — "
              f"владельческая эскалация (research/02 §3 п.6, Code Guidance P0.1), артефакт не пишется",
              file=sys.stderr)
        return 2

    model_ids = sorted({m for rec in accepted for m in rec["model_ids"]})
    model_id = model_ids[0]
    corpus_index = sorted(f"{rec['path']}+{rec['sha256']}" for rec in accepted)
    corpus_sha256 = hashlib.sha256("\n".join(corpus_index).encode("utf-8")).hexdigest()

    artifact = {
        "version": "1.0.0",
        "calibrated_at": _now_iso(),
        "tokenizer": {"model_id": model_id, "family": model_id.rsplit("-", 1)[0] if "-" in model_id else model_id},
        "corpus": {
            "files": len(accepted),
            "total_bytes": sum(r["bytes"] for r in accepted),
            "sha256": corpus_sha256,
        },
        "classes": rates,
        "per_file_overhead_tokens": overhead,
        "safety_multiplier": safety_multiplier,
        "bound": {"violations": violations, "max_true_over_estimate": observed_max},
        "tightness": tightness,
        "source": SOURCE,
        "probe_protocol_version": PROBE_PROTOCOL_VERSION,
        "control_drift_observed": {"delta_tokens_gate": DELTA_TOKENS,
                                     "max_drift_accepted": max((r["drift"] for r in accepted), default=0)},
        "rejected_files": len(rejected),
        "_generated_by": "packages/task/scripts/calibrate-token-estimate.py — НЕ РЕДАКТИРОВАТЬ РУКАМИ, перегенерировать",
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"артефакт калибровки записан: {ARTIFACT_PATH}")

    probe_log = {
        "protocol_version": PROBE_PROTOCOL_VERSION,
        "generated_at": _now_iso(),
        "measured": len(accepted),
        "min_corpus": MIN_CORPUS,
        "rejected": [{"path": r["path"], "reason": r["reject_reason"]} for r in rejected],
        "probes": records,
        "_generated_by": "packages/task/scripts/calibrate-token-estimate.py — НЕ РЕДАКТИРОВАТЬ РУКАМИ, перегенерировать",
    }
    PROBE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROBE_LOG_PATH.write_text(json.dumps(probe_log, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"probe-log записан: {PROBE_LOG_PATH}")
    print(f"OK: violations=0, p95={tightness['p95']:.3f}, safety_multiplier={safety_multiplier:.4f}, "
          f"model={model_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
