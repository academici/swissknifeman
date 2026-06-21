"""Вывод и завершение — дословный общий код swissknifeman/maind/brain.

die() здесь — надмножество (с code) обоих исторических вариантов:
swissknifeman вызывал die(msg) → code=1 по умолчанию, поведение не меняется."""
import sys
from datetime import datetime, timezone


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"WARN: {msg}", file=sys.stderr)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def confirm(prompt):
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
