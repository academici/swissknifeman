#!/usr/bin/env python3
"""Гигиена публичного дерева: запрещённые суффиксы/имена/префиксы в ОТСЛЕЖИВАЕМОМ дереве.

Ловит СЕКРЕТ/АРТЕФАКТ (имена путей), не сканирует содержимое файлов — не сканер секретов.
Источник списка — `git ls-files` (индекс), не `os.walk` (P8.6, перенос raytsystem
public_hygiene.py).
"""
import hashlib
import re
import subprocess
import sys

# Правила — ДАННЫМИ, каждое с названной причиной; расширение "на всякий случай" запрещено
# (Code Guidance P8.6): нерасшифрованная причина ⇒ гейт начнёт краснить на легальных файлах.
SUFFIX_RULES = [
    (".sqlite", "SQLite-база — приватный артефакт, не публикуется"),
    (".log", "лог-файл — рантайм-артефакт, не публикуется"),
    (".pem", "приватный ключ/сертификат"),
    (".key", "приватный ключ"),
    (".zip", "архив — бинарный артефакт вне дерева исходников"),
    (".tar", "архив — бинарный артефакт вне дерева исходников"),
    (".tar.gz", "архив — бинарный артефакт вне дерева исходников"),
    (".tgz", "архив — бинарный артефакт вне дерева исходников"),
    (".rar", "архив — бинарный артефакт вне дерева исходников"),
    (".7z", "архив — бинарный артефакт вне дерева исходников"),
]

# *.example — исключение из ЛЮБОГО суффиксного/имённого правила ниже (фикстуры/шаблоны обязаны
# проходить: гигиена ловит секрет, а не расширение).
EXAMPLE_SUFFIX = ".example"

ENV_BASENAME = ".env"
ENV_REASON = "секретный конфиг окружения (.env) — не публикуется, кроме *.example"

COMPONENT_RULES = [
    ("__pycache__", "скомпилированный кэш Python — рантайм-артефакт"),
    (".venv", "виртуальное окружение Python — не публикуется"),
    ("node_modules", "зависимости npm — не публикуется"),
]


# Содержимое: абсолютный путь рабочего окружения конкретной машины (домашний каталог + типовая
# раскладка проектов/конфигов). Синтетические примеры (`/home/user/…`, `/home/example/…`) не ловятся — только то, что
# ломает установку на другом компьютере и светит имя пользователя.
CONTENT_RULES = [
    (re.compile(r"(?:/home|/Users)/(?!(?:user|users|example|alice|bob|dev|operator|u|someone|you|me|name"
                r"|username|runner|ci|test)\b)[A-Za-z0-9_.-]+/(?:projects|Vaults|sibintek|Documents|Desktop"
                r"|Downloads|\.config|\.claude|\.codex|\.cursor|\.maind|\.swissknifeman)\b"
                r"|[A-Za-z]:\\+Users\\+(?!(?:user|users|example|alice|bob|dev|operator|u|someone|you|me|name"
                r"|username|runner|ci|test)\b)[A-Za-z0-9_.-]+"),
     "абсолютный путь рабочего окружения (используйте относительный путь, `<REPO_ROOT>` или `~`)"),
]
CONTENT_MAX_BYTES = 2_000_000
# Файлы, чьи байты зафиксированы sha256 в коде: переписать путь = сломать цепочку. Только с причиной.
CONTENT_EXEMPT = {
    "packages/maind/tests/test_provider_deploy.py":
        "точный исторический preimage D108/D115, sha256 которого закреплён в provider_deploy.py",
}
# Sealed measurement evidence: its text is the measured input, so rewriting it would falsify the measurement.
CONTENT_PLAN_EXEMPT = {
    "packages/task/configs/calibration-probe-log-v2.json":
        "sealed provider-probe measurement; sample text is hash-bound input",
}
# The exemption holds only while the sealed file is byte-identical to the reviewed one.
CONTENT_PLAN_EXEMPT_SHA256 = {
    "packages/task/configs/calibration-probe-log-v2.json": "16cacebfb6d44dc51d678d875fccef1fd427f0e8c9f1c4bc70f4b30650242d14",
}

# Working documents are local-only; nothing tracked may live under or point into them.
WORKING_DOC_DIRS = ("plans/", "roadmap/", "tasks/", ".cursor/plans/")
# Concrete plan identity: dated plan ID, Short-ID citation, or a link into the working directories.
# Synthetic fixture IDs are namespaced `DEMO...` and are allowed.
PLAN_REFERENCE_RULES = [
    (re.compile(r"20\d\d\.[01]\d\.[0-3]\d-(?:№\d+-)?(?!DEMO(?:-|\b))[A-Z]"), "concrete plan ID"),
    (re.compile(r"PLAN\d+\.[DPF]\d"), "Short-ID plan citation"),
    (re.compile(r"(?<![\w<{./-])(?:roadmap|tasks)/(?![<{])[\w.№-]"), "link into a working directory"),
    (re.compile(r"(?<![\w<{./-])plans/(?:archive/)?(?:20\d\d\.[01]\d\.[0-3]\d-(?:№\d+-)?)?(?!DEMO)[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"),
     "path into a plan directory"),
]


def plan_reference_violations(paths, read=None):
    """Tracked files must not sit in working directories or reference concrete plans."""
    read = read or _read_text
    found = [(path, "tracked working document (plans/, roadmap/, tasks/, .cursor/plans/ are local-only)")
             for path in paths if path.startswith(WORKING_DOC_DIRS)]
    for path in paths:
        if path.startswith(WORKING_DOC_DIRS):
            continue
        text = read(path)
        if path in CONTENT_PLAN_EXEMPT:
            if text is not None and hashlib.sha256(text.encode("utf-8")).hexdigest() != CONTENT_PLAN_EXEMPT_SHA256[path]:
                found.append((path, "sealed measurement changed; exemption no longer applies"))
            continue
        if text is None:
            continue
        for pattern, reason in PLAN_REFERENCE_RULES:
            match = pattern.search(text)
            if match:
                found.append((f"{path} ({match.group(0)})", reason))
    return found


def content_violations(paths, read=None):
    """Нарушения по содержимому tracked-текстовых файлов; бинарные и крупные пропускаются."""
    read = read or _read_text
    found = []
    for path in paths:
        if path in CONTENT_EXEMPT:
            continue
        text = read(path)
        if text is None:
            continue
        for pattern, reason in CONTENT_RULES:
            match = pattern.search(text)
            if match:
                found.append((f"{path} ({match.group(0)})", reason))
    return found


def _read_text(path):
    try:
        with open(path, "rb") as stream:
            data = stream.read(CONTENT_MAX_BYTES + 1)
    except OSError:
        return None
    if len(data) > CONTENT_MAX_BYTES or b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", "replace")


def list_tracked_files():
    try:
        out = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"git ls-files недоступен: {exc}", file=sys.stderr)
        sys.exit(2)
    return [line for line in out.stdout.splitlines() if line]


def violation_reason(path):
    if path.endswith(EXAMPLE_SUFFIX):
        return None
    basename = path.rsplit("/", 1)[-1]
    if basename == ENV_BASENAME:
        return ENV_REASON
    for suffix, reason in SUFFIX_RULES:
        if path.endswith(suffix):
            return reason
    parts = path.split("/")
    for name, reason in COMPONENT_RULES:
        if name in parts:
            return reason
    return None


def check(paths):
    violations = []
    for path in paths:
        reason = violation_reason(path)
        if reason:
            violations.append((path, reason))
    return violations


def main(argv):
    paths = list_tracked_files()
    violations = check(paths) + content_violations(paths) + plan_reference_violations(paths)
    if violations:
        for path, reason in violations:
            print(f"{path} — запрещено правилом «{reason}»")
        return 1
    print("public-hygiene: 0 нарушений")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
