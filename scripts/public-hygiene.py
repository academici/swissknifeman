#!/usr/bin/env python3
"""Гигиена публичного дерева: запрещённые суффиксы/имена/префиксы в ОТСЛЕЖИВАЕМОМ дереве.

Ловит СЕКРЕТ/АРТЕФАКТ (имена путей), не сканирует содержимое файлов — не сканер секретов.
Источник списка — `git ls-files` (индекс), не `os.walk` (P8.6, перенос raytsystem
public_hygiene.py).
"""
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
    violations = check(paths)
    if violations:
        for path, reason in violations:
            print(f"{path} — запрещено правилом «{reason}»")
        return 1
    print("public-hygiene: 0 нарушений")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
