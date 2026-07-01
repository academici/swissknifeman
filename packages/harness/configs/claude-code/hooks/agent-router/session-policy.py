#!/usr/bin/env python3
"""agent-router · SessionStart — инжектит СТАТИЧЕСКУЮ политику роутинга один раз за сессию.

Пара к router.py (UserPromptSubmit — per-turn keyword-подсказка). Политика кладётся в
контекст МОДЕЛИ через hookSpecificOutput.additionalContext.

ВАЖНО (проверено perplexity-web по офиц. докам Claude Code): для SessionStart модель видит
именно `additionalContext` (и/или stdout при exit 0), а `systemMessage` — UI-only, модель
его НЕ видит. Поэтому политику шлём через additionalContext. Доки прямо рекомендуют:
статическая политика → SessionStart, per-turn augmentation → UserPromptSubmit.

Хук никогда не барьер: любая ошибка → exit 0 без вывода.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import read_env  # noqa: E402


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    cwd = payload.get("cwd")
    cfg_dir = Path(__file__).resolve().parent

    try:
        env = read_env(cfg_dir, cwd)
    except Exception:
        sys.exit(0)
    mode = env.get("POLICY", "propose")
    if mode == "off":
        sys.exit(0)

    try:
        cfg = json.loads((cfg_dir / "config.json").read_text(encoding="utf-8"))
    except Exception:
        sys.exit(0)
    policy = (cfg.get("policy") or "").strip()
    if not policy:
        sys.exit(0)
    if mode == "auto_dispatch":
        suffix = (cfg.get("policy_auto_suffix") or "").strip()
        if suffix:
            policy = policy + "\n" + suffix

    out = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                  "additionalContext": policy},
           "suppressOutput": True}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
