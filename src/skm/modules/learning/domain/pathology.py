"""Versioned diagnostic rules over neutral activity metrics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.outcomes import Diagnostic, Severity

from .activity import ACTIVITY_SCHEMA, ActivitySummary, LearningSettings, validate_detector_evidence
from .evidence import DetectorEvidence


class PathologyCode(StrEnum):
    FILE_REREAD = "file_reread"
    TOOL_ERROR_LOOP = "tool_error_loop"
    NO_OP_RUN = "no_op_run"
    NO_VERIFY = "no_verify"
    CACHE_MISS = "cache_miss"
    RETRIEVAL_STUFFING = "retrieval_stuffing"
    PROTECTED_WRITE = "protected_write"
    STATIC_CONTEXT = "static_context"
    FANOUT = "fanout"


@dataclass(frozen=True, slots=True)
class PathologyFinding:
    code: PathologyCode
    severity: Literal["info", "attention"]
    metric: JsonValue
    threshold: JsonValue
    evidence: str
    data: JsonObject


type Decision = Literal["fired", "not_fired", "unknown", "error"]
type FindingSeverity = Literal["info", "attention"]


@dataclass(frozen=True, slots=True)
class PathologyResult:
    findings: tuple[PathologyFinding, ...]
    evidence: tuple[DetectorEvidence, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class PathologyReplay:
    decision: Decision | Literal["version_unavailable"]
    finding: PathologyFinding | None = None


@dataclass(frozen=True, slots=True)
class _Rule:
    metrics: Callable[[ActivitySummary], JsonObject]
    threshold_names: tuple[str, ...]
    evaluate: Callable[[JsonObject, JsonObject], tuple[FindingSeverity | None, JsonValue]]


def _number(data: JsonObject, key: str) -> int | float:
    value = data[key]
    if type(value) not in (int, float):
        raise ValueError(f"Expected a numeric metric for {key}")
    return cast("int | float", value)


def _reread(m: JsonObject, t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    total, unique = _number(m, "reads_total"), _number(m, "reads_unique")
    ratio = (total - unique) / total if total else 0.0
    fired = total >= _number(t, "reread_min_total") and ratio > _number(t, "reread_ratio_max")
    return ("attention" if fired else None), ratio


def _error_loop(m: JsonObject, t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    length = _number(m, "max_error_loop_length")
    if length >= _number(t, "error_loop_attention_len"):
        return "attention", length
    return ("info" if length >= _number(t, "error_loop_info_len") else None), length


def _no_op(m: JsonObject, t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    tools = _number(m, "tools_total")
    fired = tools >= _number(t, "noop_min_tools") and all(
        m[key] == 0 for key in ("files_changed", "checks", "retrieval_calls")
    )
    return ("info" if fired else None), tools


def _no_verify(m: JsonObject, _t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    files = _number(m, "files_changed")
    return ("attention" if files > 0 and m["checks"] == 0 else None), files


def _cache_miss(m: JsonObject, t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    hit = _number(m, "cache_hit")
    total = sum(_number(m, key) for key in ("usage_input", "usage_cache_read", "usage_cache_write"))
    fired = hit < _number(t, "cache_hit_low") and total > _number(t, "cache_miss_min_tokens")
    return ("info" if fired else None), hit


def _retrieval(m: JsonObject, t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    usage = _number(m, "usage_input")
    if not usage:
        return None, None
    ratio = _number(m, "retrieval_result_chars") / _number(t, "chars_per_token") / usage
    if ratio <= _number(t, "retrieval_in_share"):
        return None, ratio
    repeats = m["retrieval_repeated_queries"]
    attention = repeats is not None and _number(m, "retrieval_repeated_queries") >= _number(
        t, "retrieval_repeated_min"
    )
    return ("attention" if attention else "info"), ratio


def _protected_write(m: JsonObject, _t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    count = _number(m, "protected_writes")
    return ("attention" if count > 0 else None), count


def _static_context(m: JsonObject, t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    messages = _number(m, "messages")
    window = _number(m, "context_window_tokens")
    if not messages or not window:
        return None, None
    ratio = (_number(m, "input_tokens") + _number(m, "cache_read_tokens")) / messages / window
    fired = (
        messages >= _number(t, "static_min_msgs")
        and ratio > _number(t, "static_window_share")
        and _number(m, "tools_total") < _number(t, "static_max_tools")
    )
    return ("info" if fired else None), ratio


def _fanout(m: JsonObject, t: JsonObject) -> tuple[FindingSeverity | None, JsonValue]:
    agents = _number(m, "agents")
    fired = agents > _number(t, "fanout_min_agents") and _number(m, "files_changed") < _number(
        t, "fanout_max_files"
    )
    return ("info" if fired else None), agents


def _count(items: tuple[object, ...] | None) -> int | None:
    return len(items) if items is not None else None


def _static_metrics(s: ActivitySummary) -> JsonObject:
    main = next((agent for agent in s.agents or () if agent.label == "main"), None)
    return {
        "messages": main.messages if main is not None else None,
        "input_tokens": main.input_tokens if main is not None else None,
        "cache_read_tokens": main.cache_read_tokens if main is not None else None,
        "context_window_tokens": s.context_window_tokens,
        "tools_total": s.tools_total,
    }


_RULES: dict[PathologyCode, _Rule] = {
    PathologyCode.FILE_REREAD: _Rule(
        lambda s: {"reads_total": s.reads_total, "reads_unique": s.reads_unique},
        ("reread_min_total", "reread_ratio_max"),
        _reread,
    ),
    PathologyCode.TOOL_ERROR_LOOP: _Rule(
        lambda s: {
            "max_error_loop_length": max((loop.length for loop in s.error_loops), default=0)
            if s.error_loops is not None
            else None
        },
        ("error_loop_info_len", "error_loop_attention_len"),
        _error_loop,
    ),
    PathologyCode.NO_OP_RUN: _Rule(
        lambda s: {
            "tools_total": s.tools_total,
            "files_changed": _count(s.files_changed),
            "checks": _count(s.checks),
            "retrieval_calls": s.retrieval_calls,
        },
        ("noop_min_tools",),
        _no_op,
    ),
    PathologyCode.NO_VERIFY: _Rule(
        lambda s: {"files_changed": _count(s.files_changed), "checks": _count(s.checks)},
        (),
        _no_verify,
    ),
    PathologyCode.CACHE_MISS: _Rule(
        lambda s: {
            "cache_hit": s.cache_hit,
            "usage_input": s.usage_input,
            "usage_cache_read": s.usage_cache_read,
            "usage_cache_write": s.usage_cache_write,
        },
        ("cache_hit_low", "cache_miss_min_tokens"),
        _cache_miss,
    ),
    PathologyCode.RETRIEVAL_STUFFING: _Rule(
        lambda s: {
            "usage_input": s.usage_input,
            "retrieval_result_chars": s.retrieval_result_chars,
            "retrieval_repeated_queries": s.retrieval_repeated_queries,
        },
        ("chars_per_token", "retrieval_in_share", "retrieval_repeated_min"),
        _retrieval,
    ),
    PathologyCode.PROTECTED_WRITE: _Rule(
        lambda s: {"protected_writes": _count(s.protected_writes)},
        (),
        _protected_write,
    ),
    PathologyCode.STATIC_CONTEXT: _Rule(
        _static_metrics,
        ("static_min_msgs", "static_window_share", "static_max_tools"),
        _static_context,
    ),
    PathologyCode.FANOUT: _Rule(
        lambda s: {"agents": _count(s.agents), "files_changed": _count(s.files_changed)},
        ("fanout_min_agents", "fanout_max_files"),
        _fanout,
    ),
}


def _evaluate(code: PathologyCode, metrics: JsonObject, thresholds: JsonObject) -> PathologyReplay:
    if any(value is None for key, value in metrics.items() if key != "retrieval_repeated_queries"):
        return PathologyReplay("unknown")
    severity, metric = _RULES[code].evaluate(metrics, thresholds)
    if severity is None:
        return PathologyReplay("unknown" if metric is None else "not_fired")
    return PathologyReplay(
        "fired",
        PathologyFinding(code, severity, metric, thresholds, f"Observed {code.value}", metrics),
    )


def detector_failed(name: str) -> Diagnostic:
    return Diagnostic(
        "LEARNING_DETECTOR_FAILED",
        "Learning detector failed",
        Severity.WARNING,
        details={"detector": name},
    )


def _evidence(
    code: PathologyCode,
    metrics: JsonObject,
    thresholds: JsonObject,
    result: PathologyReplay,
    source_refs: tuple[JsonObject, ...],
) -> DetectorEvidence:
    population: JsonObject = {"activity_count": 1}
    exclusions: JsonObject = {"status": "unknown"}
    alternatives: tuple[str, ...] = ()
    investigation = "Inspect the source activity to verify the pattern and its context."
    if code is PathologyCode.FILE_REREAD:
        population.update(reads_total=metrics.get("reads_total"), reads_unique=metrics.get("reads_unique"))
        exclusions = {"file_version": "unknown", "compaction": "unknown", "reviewer": "unknown"}
        alternatives = (
            "The file changed",
            "Context was compacted",
            "Independent review",
            "The file was read in sections",
        )
        investigation = "Compare file versions, context compaction and the purpose of each read."
    return DetectorEvidence(
        detector_version=f"pathology/{code.value}:v1",
        input_schema_version=ACTIVITY_SCHEMA,
        relevant_metrics=metrics,
        thresholds=thresholds,
        source_refs=source_refs,
        coverage={key: "missing" if value is None else "present" for key, value in metrics.items()},
        decision=result.decision,
        severity=result.finding.severity if result.finding is not None else None,
        population=population,
        exclusions=exclusions,
        alternative_explanations=alternatives,
        suggested_investigation=investigation,
    )


def detect_with_evidence(
    summary: ActivitySummary,
    t: LearningSettings,
    *,
    source_refs: tuple[JsonObject, ...] = (),
) -> PathologyResult:
    findings: list[PathologyFinding] = []
    evidence: list[DetectorEvidence] = []
    diagnostics: list[Diagnostic] = []
    settings = asdict(t.detectors)
    refs: tuple[JsonObject, ...] = (
        {"kind": summary.source_kind.value, "id": summary.source_key},
        *source_refs,
    )
    for code, rule in _RULES.items():
        metrics: JsonObject = {}
        thresholds = {name: cast("JsonValue", settings[name]) for name in rule.threshold_names}
        try:
            metrics = rule.metrics(summary)
            result = _evaluate(code, metrics, thresholds)
        except Exception:  # noqa: BLE001 - isolate detector failures
            diagnostics.append(detector_failed(code.value))
            result = PathologyReplay("error")
        if result.finding is not None:
            findings.append(result.finding)
        evidence.append(_evidence(code, metrics, thresholds, result, refs))
    bundles = tuple(evidence)
    validate_detector_evidence(bundles)
    return PathologyResult(tuple(findings), bundles, tuple(diagnostics))


def detect(summary: ActivitySummary, t: LearningSettings) -> tuple[PathologyFinding, ...]:
    return detect_with_evidence(summary, t).findings


def replay_pathology(bundle: DetectorEvidence) -> PathologyReplay:
    if bundle.input_schema_version != ACTIVITY_SCHEMA:
        return PathologyReplay("version_unavailable")
    for code in _RULES:
        if bundle.detector_version == f"pathology/{code.value}:v1":
            if bundle.decision == "error":
                return PathologyReplay("error")
            return _evaluate(code, bundle.relevant_metrics, bundle.thresholds)
    return PathologyReplay("version_unavailable")
