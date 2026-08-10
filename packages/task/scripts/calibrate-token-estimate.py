#!/usr/bin/env python3
"""Generate the bounded, provider-qualified P0.1 token calibration (v2)."""
import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _SCRIPT_DIR.parent
_REPO_ROOT = _PKG_ROOT.parent.parent
sys.path.insert(0, str(_PKG_ROOT / "lib"))

from task import token_estimate  # noqa: E402
from task.token_probe import ProbeRecordError, ensure_same_target  # noqa: E402
from task.token_probe_codex import (  # noqa: E402
    ADAPTER_ID, PROBE_PROTOCOL_VERSION, CodexExecProbeAdapter,
)

MAX_SAMPLE_BYTES = 16 * 1024
MAX_TOTAL_SAMPLE_BYTES = 128 * 1024
MAX_PROVIDER_CALLS = 12
MAX_PAYLOADS_PER_BRACKET = 3
DELTA_TOKENS = 50
FIXED_MARGIN = 1.05
NNLS_ITERATIONS = 20000
NNLS_LEARNING_RATE = 0.05
ARTIFACT_PATH = _PKG_ROOT / "configs" / "token-estimate-calibration.json"
V1_SNAPSHOT_PATH = _PKG_ROOT / "configs" / "token-estimate-calibration-v1.json"
PROBE_LOG_PATH = _PKG_ROOT / "configs" / "calibration-probe-log-v2.json"

# Exactly eight distinct real sources.  The first three are the measured dense-ASCII artefacts.
CORPUS = (
    _REPO_ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/trial-admission-index-v1.json",
    _REPO_ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P3/package-promotion-manifest-v1.json",
    _REPO_ROOT / "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/trial-admission-index-v3-p5.4-paired.json",
    _PKG_ROOT / "configs" / "token-estimate-calibration-v1.json",
    _PKG_ROOT / "configs" / "read-limit.json",
    _REPO_ROOT / "packages/task/lib/task/token_estimate.py",
    _REPO_ROOT / "packages/task/lib/task/token_probe.py",
    _REPO_ROOT / "packages/task/tests/test_token_estimate.py",
)


class CalibrationError(RuntimeError):
    """A bounded calibration cannot truthfully produce a v2 artifact."""


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _read_sample(path):
    raw = path.read_bytes()
    if len(raw) <= MAX_SAMPLE_BYTES:
        sample = raw
        whole_file = True
    else:
        sample = raw[:MAX_SAMPLE_BYTES]
        while sample:
            try:
                sample.decode("utf-8")
                break
            except UnicodeDecodeError as exc:
                sample = sample[:exc.start]
        if not sample:
            raise CalibrationError(f"sample не удаётся обрезать по UTF-8: {path}")
        whole_file = False
    text = sample.decode("utf-8")
    return {
        "source_path": str(path),
        "full_source_sha256": _sha256(raw),
        "byte_range": {"start": 0, "end_exclusive": len(sample)},
        "sample_sha256": _sha256(sample),
        "sample_bytes": len(sample),
        "whole_file": whole_file,
        "payload": text,
        "full_text": raw.decode("utf-8", errors="replace"),
    }


def collect_samples():
    samples = [_read_sample(path) for path in CORPUS]
    paths = {sample["source_path"] for sample in samples}
    if len(samples) != 8 or len(paths) != 8:
        raise CalibrationError("corpus обязан содержать ровно 8 разных real sources")
    total_bytes = sum(sample["sample_bytes"] for sample in samples)
    if total_bytes > MAX_TOTAL_SAMPLE_BYTES:
        raise CalibrationError(f"corpus sample_bytes={total_bytes} > {MAX_TOTAL_SAMPLE_BYTES}")
    if sum(sample["whole_file"] for sample in samples) < 2:
        raise CalibrationError("corpus обязан нести минимум 2 whole-file samples")
    return samples


def run_brackets(adapter, samples):
    """Run control/payload/control brackets; the core knows no provider JSON fields."""
    accepted, rejected, calls = [], [], []
    left = adapter.probe("")
    calls.append(left)
    for start in range(0, len(samples), MAX_PAYLOADS_PER_BRACKET):
        batch = samples[start:start + MAX_PAYLOADS_PER_BRACKET]
        payload_records = [adapter.probe(sample["payload"]) for sample in batch]
        right = adapter.probe("")
        calls.extend([*payload_records, right])
        try:
            ensure_same_target([left, *payload_records, right])
        except ProbeRecordError as exc:
            raise CalibrationError(str(exc)) from exc
        drift = abs(left.input_tokens_total - right.input_tokens_total)
        for sample, record in zip(batch, payload_records):
            row = dict(sample)
            row.pop("payload")
            row["probe"] = record.as_dict()
            row["left_control_input_tokens"] = left.input_tokens_total
            row["right_control_input_tokens"] = right.input_tokens_total
            row["control_drift"] = drift
            row["true_tokens"] = record.input_tokens_total - (
                left.input_tokens_total + right.input_tokens_total) / 2
            row["counts"] = token_estimate.count_classes(sample["payload"])
            if drift > DELTA_TOKENS:
                row["rejected"] = True
                row["reject_reason"] = f"control drift {drift} > {DELTA_TOKENS}"
                rejected.append(row)
            elif row["true_tokens"] < 0:
                row["rejected"] = True
                row["reject_reason"] = "payload input total меньше среднего controls"
                rejected.append(row)
            else:
                row["rejected"] = False
                row["reject_reason"] = None
                accepted.append(row)
        left = right
    if len(calls) > MAX_PROVIDER_CALLS:
        raise CalibrationError(f"provider calls={len(calls)} > {MAX_PROVIDER_CALLS}")
    return accepted, rejected, calls


def fit_rates(accepted):
    scales = [max(1.0, max(row["counts"][name] for row in accepted))
              for name in token_estimate.CLASSES] + [1.0]
    rows = [[row["counts"][name] / scales[index]
             for index, name in enumerate(token_estimate.CLASSES)] + [1.0]
            for row in accepted]
    truths = [row["true_tokens"] for row in accepted]
    weights = [0.0] * len(scales)
    for _ in range(NNLS_ITERATIONS):
        grad = [0.0] * len(scales)
        for row, truth in zip(rows, truths):
            error = sum(weight * value for weight, value in zip(weights, row)) - truth
            for index in range(len(weights)):
                grad[index] += 2 * error * row[index]
        for index in range(len(weights)):
            weights[index] = max(0.0, weights[index] - NNLS_LEARNING_RATE * grad[index] / len(rows))
    return ({name: weights[index] / scales[index]
             for index, name in enumerate(token_estimate.CLASSES)}, weights[-1])


def bound_and_tighten(accepted, rates, overhead):
    required = []
    for row in accepted:
        raw = sum(row["counts"][name] * rates[name] for name in token_estimate.CLASSES)
        required.append(0.0 if raw <= 0 else max(0.0, (row["true_tokens"] - overhead) / raw))
    observed_max = max(required)
    multiplier = max(1.0, observed_max) * FIXED_MARGIN
    ratios, violations = [], 0
    for row in accepted:
        raw = sum(row["counts"][name] * rates[name] for name in token_estimate.CLASSES)
        estimate = math.ceil(raw * multiplier + overhead)
        if estimate < row["true_tokens"]:
            violations += 1
        ratios.append(estimate / row["true_tokens"] if row["true_tokens"] else 1.0)
    ratios.sort()
    return multiplier, observed_max, violations, {
        "p50": ratios[len(ratios) // 2],
        "p95": ratios[min(len(ratios) - 1, int(round(.95 * (len(ratios) - 1))))],
        "max": ratios[-1],
    }


def preserve_v1_snapshot():
    active = ARTIFACT_PATH.read_bytes()
    if V1_SNAPSHOT_PATH.exists():
        if V1_SNAPSHOT_PATH.read_bytes() != active:
            raise CalibrationError("existing token-estimate-calibration-v1 snapshot отличается от active v1")
        return
    V1_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    V1_SNAPSHOT_PATH.write_bytes(active)


def generate(provider, model, *, smoke_probe=False):
    if provider != "codex":
        raise CalibrationError(f"provider {provider!r} не поддержан; скрытый fallback запрещён")
    adapter = CodexExecProbeAdapter(model)
    if smoke_probe:
        print(json.dumps(adapter.probe("").as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    preserve_v1_snapshot()
    samples = collect_samples()
    accepted, rejected, calls = run_brackets(adapter, samples)
    if len(accepted) != 8:
        raise CalibrationError(f"accepted samples={len(accepted)}, ожидается ровно 8")
    if sum(row["counts"]["dense_ascii"] > 0 for row in accepted) < 3:
        raise CalibrationError("accepted_dense_samples < 3")
    if any(not any(row["counts"][name] for row in accepted) for name in token_estimate.CLASSES):
        raise CalibrationError("corpus не покрывает все пять classifier classes")
    records = [row["probe"] for row in accepted]
    ensure_same_target([adapter_record(row) for row in records])
    rates, overhead = fit_rates(accepted)
    multiplier, observed_max, violations, tightness = bound_and_tighten(accepted, rates, overhead)
    if rates["dense_ascii"] <= 0:
        raise CalibrationError("dense_ascii rate обязан быть положительным")
    if violations != 0 or tightness["p95"] > 1.6:
        raise CalibrationError(f"acceptance не пройден: violations={violations}, p95={tightness['p95']:.3f}")
    target = records[0]
    artifact = {
        "version": "2.0.0", "calibrated_at": _now_iso(),
        "calibration_target": {
            "provider": target["provider"]["id"], "adapter": target["provider"]["adapter"],
            "requested_model_id": target["model"]["requested_id"],
            "probe_protocol_version": target["protocol_version"],
            "usage_semantics": "provider-reported-input-total-v1",
        },
        "classifier": token_estimate.CLASSIFIER, "classes": rates,
        "per_file_overhead_tokens": overhead, "safety_multiplier": multiplier,
        "corpus": {"accepted_samples": len(accepted), "distinct_sources": len({r['source_path'] for r in accepted}),
                   "sample_bytes": sum(r["sample_bytes"] for r in accepted),
                   "whole_file_samples": sum(r["whole_file"] for r in accepted)},
        "bound": {"violations": violations, "max_true_over_estimate": observed_max},
        "tightness": tightness,
        "fingerprints": {"wrapper_sha256": target["wrapper_sha256"],
                         "command_sha256": target["environment"]["command_sha256"]},
        "_generated_by": "packages/task/scripts/calibrate-token-estimate.py — НЕ РЕДАКТИРОВАТЬ РУКАМИ, перегенерировать",
    }
    canary = []
    for row, sample in zip(accepted, samples):
        estimate = token_estimate.estimate_text(sample["full_text"], artifact=artifact)
        canary.append({"source_path": sample["source_path"], "est_tokens": estimate,
                       "passed": estimate >= row["true_tokens"]})
    if not all(row["passed"] for row in canary):
        raise CalibrationError("full-source offline canary обнаружил занижение")
    artifact["corpus"]["full_source_offline_canary"] = canary
    log = {
        "schema_version": "calibration-probe-log-v2", "generated_at": _now_iso(),
        "probe_protocol_version": PROBE_PROTOCOL_VERSION, "provider_calls": len(calls),
        "delta_tokens": DELTA_TOKENS, "accepted_samples": accepted, "rejected_samples": rejected,
        "controls": [calls[0].as_dict(), calls[4].as_dict(), calls[8].as_dict(), calls[11].as_dict()],
        "_generated_by": "packages/task/scripts/calibrate-token-estimate.py — НЕ РЕДАКТИРОВАТЬ РУКАМИ, перегенерировать",
    }
    ARTIFACT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    PROBE_LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OK: accepted_samples=8, sample_bytes={artifact['corpus']['sample_bytes']}, "
          f"provider_calls={len(calls)}, violations=0, p95={tightness['p95']:.3f}")
    return 0


def adapter_record(data):
    """Rehydrate only at the script boundary; fitting itself consumes neutral fields."""
    from task.token_probe import ProbeRecord
    return ProbeRecord(
        schema_version=data["schema_version"], provider_id=data["provider"]["id"],
        provider_adapter=data["provider"]["adapter"], requested_model_id=data["model"]["requested_id"],
        effective_model_id=data["model"]["effective_id"], protocol_version=data["protocol_version"],
        input_tokens_total=data["input_tokens_total"], usage_breakdown=data["usage_breakdown"],
        wrapper_sha256=data["wrapper_sha256"], environment_cli=data["environment"]["cli"],
        environment_version=data["environment"]["version"],
        command_sha256=data["environment"]["command_sha256"],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=("codex",))
    parser.add_argument("--model", required=True)
    parser.add_argument("--smoke-probe", action="store_true")
    args = parser.parse_args(argv)
    try:
        return generate(args.provider, args.model, smoke_probe=args.smoke_probe)
    except (CalibrationError, OSError, ProbeRecordError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
