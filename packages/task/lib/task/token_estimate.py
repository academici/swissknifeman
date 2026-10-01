"""token_estimate — stdlib-only, deterministic estimation of the number of text tokens TOP
(calibration channel defined package-owned configuration).

Formula (D14): ``estimate(T) = ceil(Σ_c count_c(T)·r_c · safety_multiplier) +
per_file_overhead_tokens`` — security multiplier scales character-by-character only
amount (safe side grows with text), `overhead` — fixed supplement for
file (received as intercept calibration regression, see `calibrate-token-estimate.py`),
so empty text gives exactly `overhead` without distortion by the multiplier.

Character classes are a closed set of `research/02-p0-measurement-design.md` §2:
`ascii_word` (letters/numbers/`_` to U+0080) takes the thickest word-forming ASCII,
`ascii_other` — other ASCII (punctuation/spaces/markup), `cyrillic` — U+0400–U+04FF,
`other` — everything else (protocol status emoji, CJK, pseudographics); `other` not
collapses into `ascii_other`, because there are emojis in every item'e fleet and their
understatement by ASCII-rate would be a systematic error in the most common place.

Bids/overhead/multiplier read ONLY from frozen calibration artifact
(`configs/token-estimate-calibration.json` default) — artifact missing,
is damaged or `bound.violations != 0` → exception, silent default disabled
(P0.1 Implementation Rules)."""
import json
import math
import re
import sys
from pathlib import Path

CLASSES = ("dense_ascii", "ascii_word", "ascii_other", "cyrillic", "other")
DENSE_ASCII_MIN_RUN = 32
DENSE_ASCII_ALPHABET = "0-9A-Za-z+/="
DENSE_ASCII_RUN_RE = re.compile(r"[0-9A-Za-z+/=]{%d,}" % DENSE_ASCII_MIN_RUN)
CLASSIFIER = {
    "version": "dense-ascii-v1",
    "dense_ascii_alphabet": DENSE_ASCII_ALPHABET,
    "dense_ascii_min_run": DENSE_ASCII_MIN_RUN,
}

_ARTIFACT_REQUIRED_FIELDS = (
    "version", "calibrated_at", "calibration_target", "classifier", "corpus", "classes",
    "per_file_overhead_tokens", "safety_multiplier", "bound", "tightness",
)

DEFAULT_ARTIFACT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "token-estimate-calibration.json"
)


class TokenEstimateArtifactError(ValueError):
    """Calibration artifact not available/is invalid - `estimate_text` must fall and not remain silent."""


def classify_char(ch):
    """Closed set of classes `CLASSES` — single point of character classification."""
    cp = ord(ch)
    if cp < 0x80:
        return "ascii_word" if (ch.isalnum() or ch == "_") else "ascii_other"
    if 0x0400 <= cp <= 0x04FF:
        return "cyrillic"
    return "other"


def count_classes(text):
    """Vector of character-by-character counters `CLASSES` — formula input D14 and calibration regression."""
    counts = {c: 0 for c in CLASSES}
    offset = 0
    for match in DENSE_ASCII_RUN_RE.finditer(text):
        _count_non_dense(text[offset:match.start()], counts)
        counts["dense_ascii"] += match.end() - match.start()
        offset = match.end()
    _count_non_dense(text[offset:], counts)
    return counts


def _count_non_dense(text, counts):
    for ch in text:
        counts[classify_char(ch)] += 1


def dense_ascii_share(text):
    """Share of characters captured by the one canonical dense-ASCII classifier."""
    if not text:
        return 0.0
    return count_classes(text)["dense_ascii"] / len(text)


def load_artifact(path=None):
    """Reads and validates the calibration artifact; `TokenEstimateArtifactError` fail-closed."""
    path = Path(path) if path is not None else DEFAULT_ARTIFACT_PATH
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TokenEstimateArtifactError(
            f"calibration artifact is not readable: {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TokenEstimateArtifactError(
            f"calibration artifact - invalid JSON: {path}: {exc}") from exc

    missing = [f for f in _ARTIFACT_REQUIRED_FIELDS if f not in data]
    if missing:
        raise TokenEstimateArtifactError(
            f"calibration artifact: no required fields {missing}: {path}")
    if data["version"] != "2.0.0":
        raise TokenEstimateArtifactError(
            f"calibration artifact: expected active version '2.0.0', received {data['version']!r}: {path}")
    target = data["calibration_target"]
    target_fields = ("provider", "adapter", "requested_model_id", "probe_protocol_version", "usage_semantics")
    if not isinstance(target, dict) or any(not isinstance(target.get(field), str) or not target[field]
                                           for field in target_fields):
        raise TokenEstimateArtifactError(f"calibration artifact: invalid calibration_target: {path}")
    if data["classifier"] != CLASSIFIER:
        raise TokenEstimateArtifactError(
            f"calibration artifact: classifier does not match canonical dense classifier: {path}")
    missing_classes = [c for c in CLASSES if c not in data.get("classes", {})]
    if missing_classes:
        raise TokenEstimateArtifactError(
            f"calibration artifact: no rates for classes {missing_classes}: {path}")
    if not isinstance(data.get("bound"), dict) or data["bound"].get("violations") != 0:
        raise TokenEstimateArtifactError(
            f"calibration artifact: bound.violations={data['bound']['violations']} != 0 — "
            f"it is prohibited to use an artifact with boundary violations: {path}")
    for c in CLASSES:
        if (not isinstance(data["classes"][c], (int, float)) or isinstance(data["classes"][c], bool)
                or data["classes"][c] < 0):
            raise TokenEstimateArtifactError(
                f"calibration artifact: class rate «{c}» negative - violates "
                f"monotonicity evaluation: {path}")
    if (not isinstance(data["per_file_overhead_tokens"], (int, float))
            or not isinstance(data["safety_multiplier"], (int, float))
            or data["per_file_overhead_tokens"] < 0 or data["safety_multiplier"] < 0):
        raise TokenEstimateArtifactError(
            f"calibration artifact: overhead/safety_multiplier must be ≥ 0: {path}")
    return data


def estimate_text(text, artifact=None, artifact_path=None, session_provider=None, session_model_id=None):
    """Evaluating text tokens at the TOP using the formula D14. `artifact` — preloaded dict
    (otherwise read `artifact_path`/default via :func:`load_artifact`). `session_model_id`
    optional: does not match `tokenizer.model_id` artifact - prints WARNING in stderr
    and continues (Code Guidance P0.1: tokenizer changed between generations before ~1.35×,
    but this is not a reason to block the rating)."""
    data = artifact if artifact is not None else load_artifact(artifact_path)
    target = data["calibration_target"]
    if ((session_provider is not None and session_provider != target["provider"])
            or (session_model_id is not None and session_model_id != target["requested_model_id"])):
        print(
            f"WARNING: token_estimate: artifact calibrated to "
            f"«{target['provider']}/{target['requested_model_id']}», session - "
            f"«{session_provider}/{session_model_id}»; estimate may not be accurate",
            file=sys.stderr,
        )
    counts = count_classes(text)
    rates = data["classes"]
    raw = sum(counts[c] * rates[c] for c in CLASSES)
    scaled = raw * data["safety_multiplier"]
    # One ceil() for the entire amount (not only on `scaled`): overhead from calibration - also
    # float (intercept regression), cutting its fractional part down would break
    # «never underestimates»; result always int, and not float.
    return math.ceil(scaled + data["per_file_overhead_tokens"])
