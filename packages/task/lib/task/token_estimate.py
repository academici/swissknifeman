"""token_estimate — stdlib-only, детерминированная оценка числа токенов текста СВЕРХУ
(2026.08.07-PLAN-ECONOMY D11/D14, канал калибровки — D92).

Формула (D14): ``estimate(T) = ceil(Σ_c count_c(T)·r_c · safety_multiplier) +
per_file_overhead_tokens`` — множитель безопасности масштабирует только посимвольную
сумму (безопасная сторона растёт с текстом), `overhead` — фиксированная добавка за
файл (получена как intercept калибровочной регрессии, см. `calibrate-token-estimate.py`),
поэтому пустой текст даёт ровно `overhead` без искажения множителем.

Классы символов — закрытый набор из `research/02-p0-measurement-design.md` §2:
`ascii_word` (буквы/цифры/`_` до U+0080) толще всего берёт словообразующий ASCII,
`ascii_other` — прочий ASCII (пунктуация/пробелы/разметка), `cyrillic` — U+0400–U+04FF,
`other` — всё остальное (эмодзи статусов протокола, CJK, псевдографика); `other` не
схлопывается в `ascii_other`, потому что эмодзи стоят в каждом item'е флота и их
занижение по ASCII-ставке было бы систематической ошибкой в самом частом месте.

Ставки/overhead/множитель читаются ТОЛЬКО из замороженного артефакта калибровки
(`configs/token-estimate-calibration.json` по умолчанию) — артефакт отсутствует,
повреждён или несёт `bound.violations != 0` → исключение, молчаливый дефолт запрещён
(P0.1 Implementation Rules)."""
import json
import math
import sys
from pathlib import Path

CLASSES = ("ascii_word", "ascii_other", "cyrillic", "other")

_ARTIFACT_REQUIRED_FIELDS = (
    "version", "calibrated_at", "tokenizer", "corpus", "classes",
    "per_file_overhead_tokens", "safety_multiplier", "bound", "tightness",
    "source", "probe_protocol_version",
)

DEFAULT_ARTIFACT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "token-estimate-calibration.json"
)


class TokenEstimateArtifactError(ValueError):
    """Артефакт калибровки недоступен/невалиден — `estimate_text` обязана падать, не молчать."""


def classify_char(ch):
    """Закрытый набор классов `CLASSES` — единственная точка классификации символа."""
    cp = ord(ch)
    if cp < 0x80:
        return "ascii_word" if (ch.isalnum() or ch == "_") else "ascii_other"
    if 0x0400 <= cp <= 0x04FF:
        return "cyrillic"
    return "other"


def count_classes(text):
    """Вектор посимвольных счётчиков по `CLASSES` — вход формулы D14 и калибровочной регрессии."""
    counts = {c: 0 for c in CLASSES}
    for ch in text:
        counts[classify_char(ch)] += 1
    return counts


def load_artifact(path=None):
    """Читает и валидирует артефакт калибровки; `TokenEstimateArtifactError` fail-closed."""
    path = Path(path) if path is not None else DEFAULT_ARTIFACT_PATH
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TokenEstimateArtifactError(
            f"артефакт калибровки не читается: {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TokenEstimateArtifactError(
            f"артефакт калибровки — невалидный JSON: {path}: {exc}") from exc

    missing = [f for f in _ARTIFACT_REQUIRED_FIELDS if f not in data]
    if missing:
        raise TokenEstimateArtifactError(
            f"артефакт калибровки: нет обязательных полей {missing}: {path}")
    missing_classes = [c for c in CLASSES if c not in data.get("classes", {})]
    if missing_classes:
        raise TokenEstimateArtifactError(
            f"артефакт калибровки: нет ставок для классов {missing_classes}: {path}")
    if data["bound"]["violations"] != 0:
        raise TokenEstimateArtifactError(
            f"артефакт калибровки: bound.violations={data['bound']['violations']} != 0 — "
            f"артефакт с нарушениями границы использовать запрещено: {path}")
    for c in CLASSES:
        if data["classes"][c] < 0:
            raise TokenEstimateArtifactError(
                f"артефакт калибровки: ставка класса «{c}» отрицательна — нарушает "
                f"монотонность оценки: {path}")
    if data["per_file_overhead_tokens"] < 0 or data["safety_multiplier"] < 0:
        raise TokenEstimateArtifactError(
            f"артефакт калибровки: overhead/safety_multiplier обязаны быть ≥ 0: {path}")
    return data


def estimate_text(text, artifact=None, artifact_path=None, session_model_id=None):
    """Оценка токенов текста СВЕРХУ по формуле D14. `artifact` — предзагруженный dict
    (иначе читается `artifact_path`/дефолт через :func:`load_artifact`). `session_model_id`
    опционален: не совпадает с `tokenizer.model_id` артефакта — печатает WARNING в stderr
    и продолжает (Code Guidance P0.1: токенизатор менялся между поколениями до ~1.35×,
    но это не повод блокировать оценку)."""
    data = artifact if artifact is not None else load_artifact(artifact_path)
    if session_model_id is not None and session_model_id != data["tokenizer"]["model_id"]:
        print(
            f"WARNING: token_estimate: артефакт калиброван под "
            f"«{data['tokenizer']['model_id']}», сессия — «{session_model_id}»; "
            f"оценка может быть неточной (токенизатор меняется между поколениями)",
            file=sys.stderr,
        )
    counts = count_classes(text)
    rates = data["classes"]
    raw = sum(counts[c] * rates[c] for c in CLASSES)
    scaled = raw * data["safety_multiplier"]
    # Один ceil() на всю сумму (не только на `scaled`): overhead из калибровки — тоже
    # float (intercept регрессии), обрезание его дробной части вниз нарушило бы
    # «никогда не занижает»; итог всегда int, а не float.
    return math.ceil(scaled + data["per_file_overhead_tokens"])
