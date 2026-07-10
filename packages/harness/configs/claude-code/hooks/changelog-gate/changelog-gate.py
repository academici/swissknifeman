#!/usr/bin/env python3
"""changelog-gate · PreToolUse (matcher Bash) — ловит `git commit` содержательного типа
(feat/fix/perf/refactor) без правки CHANGELOG среди застейдженных файлов. warning В КОНТЕКСТ
модели (НЕ блок) — дефолт-режим warn; strict — блокирует (exit 2). Опциональный, по умолчанию
НЕ устанавливается: включается явно `harness hooks --target . --changelog-gate warn|strict`.

Детекция (D33, RAG:✅ 2026-07-11 code.claude.com/docs/en/hooks.md — PreToolUse non-blocking
warning доставляется через stdout JSON `hookSpecificOutput.additionalContext` + exit 0, в паре
с `permissionDecision:"allow"`; strict — exit 2 + stderr):
- тип коммита и skip-маркер парсятся ТОЛЬКО из `-m`-сообщения команды (editor-сообщение без
  `-m` не парсится — нет `-m` → exit 0, не угадываем);
- содержательный тип — РОВНО feat/fix/perf/refactor; docs/chore/test/style/ci/build/иной
  префикс → авто-skip (exit 0, без warning);
- `[changelog-skip]` в сообщении → skip без warning (осознанное исключение);
- «CHANGELOG затронут» = среди `git diff --cached --name-only` есть путь `(?i)changelog`
  (любой CHANGELOG — корневой либо per-package, монорепо);
- репо без ЕДИНОГО CHANGELOG в дереве (`git ls-files` не находит `(?i)changelog`) → exit 0
  (проект не ведёт дисциплину — безопасный no-op, как pack-guard без lock).

Дисциплина pack-guard ОБЯЗАТЕЛЬНА: любая ошибка / битый JSON / отсутствие полей / сбой
subprocess → `sys.exit(0)`, НИКОГДА не блокирует из-за внутренней ошибки. Stdlib-only."""
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

_DEFAULT_MODE = "off"
_MODES = ("off", "warn", "strict")
_CONTENT_TYPES = ("feat", "fix", "perf", "refactor")
_TYPE_RE = re.compile(r"^(feat|fix|perf|refactor)(\([^)]*\))?!?:\s")
_SKIP_MARKER = "[changelog-skip]"
_CHANGELOG_RE = re.compile(r"changelog", re.IGNORECASE)
_SEGMENT_RE = re.compile(r"&&|\|\||;|\|")


def _read_mode(cwd):
    """MODE из <cwd>/.claude/changelog-gate.env.ini (файл пишет `harness hooks
    --changelog-gate`). Нет файла / битый / неизвестное значение → off (безопасный дефолт —
    хук по умолчанию НЕ установлен ни в одном проекте)."""
    if not cwd:
        return _DEFAULT_MODE
    f = Path(cwd) / ".claude" / "changelog-gate.env.ini"
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        return _DEFAULT_MODE
    mode = _DEFAULT_MODE
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        if k == "MODE":
            v = v.lower()
            mode = v if v in _MODES else _DEFAULT_MODE
    return mode


def _commit_messages(command):
    """Список значений `-m` из СЕГМЕНТА команды с `git commit` (сегменты разделены
    `&&`/`;`/`|`/`||` — чтобы не подхватить `-m` соседней команды в цепочке). Пусто/ошибка
    разбора (кривые кавычки) → []."""
    if not isinstance(command, str) or not command.strip():
        return []
    for segment in _SEGMENT_RE.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        for i in range(len(tokens) - 1):
            if tokens[i] == "git" and tokens[i + 1] == "commit":
                rest = tokens[i + 2:]
                return [rest[j + 1] for j in range(len(rest) - 1) if rest[j] == "-m"]
    return []


def _git(cwd, *args):
    """`git <args>` в cwd → список строк stdout. Любой сбой (нет git / не репо / таймаут) →
    None (вызывающий код трактует как «не знаю» → безопасный no-op)."""
    try:
        out = subprocess.run(["git", "-C", cwd, *args], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=10, check=False)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    try:
        text = out.stdout.decode("utf-8", errors="replace")
    except Exception:
        return None
    return [line for line in text.splitlines() if line]


def _has_changelog_in_tree(cwd):
    files = _git(cwd, "ls-files")
    if files is None:
        return False
    return any(_CHANGELOG_RE.search(f) for f in files)


def _changelog_staged(cwd):
    files = _git(cwd, "diff", "--cached", "--name-only")
    if files is None:
        return False
    return any(_CHANGELOG_RE.search(f) for f in files)


def _warn_json(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": "changelog-gate: warn — не блокирую",
        "additionalContext": reason,
    }}))


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None

    cwd = payload.get("cwd") or os.getcwd()
    mode = _read_mode(cwd)
    if mode == "off":
        sys.exit(0)

    messages = _commit_messages(command)
    if not messages:
        sys.exit(0)  # не git commit в команде, либо нет -m — не угадываем

    full_text = "\n".join(messages)
    if _SKIP_MARKER in full_text:
        sys.exit(0)  # осознанное исключение

    m = _TYPE_RE.match(messages[0])
    if not m:
        sys.exit(0)  # docs/chore/test/style/ci/build/иной префикс — авто-skip
    commit_type = m.group(1)

    if not _has_changelog_in_tree(cwd):
        sys.exit(0)  # проект не ведёт CHANGELOG-дисциплину — no-op
    if _changelog_staged(cwd):
        sys.exit(0)  # CHANGELOG уже среди застейдженных файлов

    reason = (
        f"changelog-gate: коммит `{commit_type}:` содержательный, но `[Unreleased]` не "
        f"тронут. Добавь строку в CHANGELOG нужной группы Keep a Changelog (или пометь "
        f"`[changelog-skip]`, если запись не нужна). Дисциплина — скилл "
        f"`oss-dev/release-engineering`."
    )
    if mode == "strict":
        sys.stderr.write(reason + "\n")
        sys.exit(2)  # PreToolUse: exit 2 блокирует вызов, stderr — причина
    _warn_json(reason)
    sys.exit(0)  # warn: подсказка в контекст модели, не блок


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # хук никогда не ломает сессию
