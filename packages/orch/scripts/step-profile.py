#!/usr/bin/env python3
"""Where the time of one role run went, from its stream-json file (``.../streams/<step>.jsonl``); markdown on stdout.

Splits the wall time into model time (between a tool result and the next assistant message) and tool time (a tool call
until its result), lists the longest commands, repeated commands and the share of test runs:

    step-profile.py STREAM.jsonl [--top N]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import datetime

TESTS = re.compile(r"(unittest|pytest|test\.sh|validate\.sh|test-[a-z-]+\.py|ecosystem-units|golden\.py|public-hygiene|test-integration)")
READS = re.compile(r"^\s*(cat|sed|head|tail|grep|rg|ls|find|wc|git (diff|status|log|show|grep))\b")


def ts(value) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def load(path: str) -> list:
    events = []
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stream")
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args(argv)
    events = load(args.stream)
    started: dict = {}
    spans = []          # (name, command, seconds)
    last_result = None
    first = last = None
    model_s = 0.0
    turns = 0
    out_tokens = 0
    for event in events:
        when = ts(event.get("timestamp"))
        if when is not None:
            first = when if first is None else first
            last = when
        kind = event.get("type")
        content = (event.get("message") or {}).get("content")
        if kind == "assistant" and isinstance(content, list):
            turns += 1
            if when is not None and last_result is not None:
                model_s += max(0.0, when - last_result)
            for block in content:
                if block.get("type") == "tool_use":
                    started[block["id"]] = (when, block.get("name"), (block.get("input") or {}))
        elif kind == "user" and isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_result" and block.get("tool_use_id") in started:
                    begin, name, data = started.pop(block["tool_use_id"])
                    if when is not None and begin is not None:
                        spans.append((name, str(data.get("command") or data.get("file_path") or data.get("description") or "")[:160], max(0.0, when - begin)))
            if when is not None:
                last_result = when
    wall = (last - first) if first and last else 0.0
    tool_s = sum(span[2] for span in spans)
    names = collections.Counter(span[0] for span in spans)
    test_s = sum(span[2] for span in spans if span[0] == "Bash" and TESTS.search(span[1]))
    test_n = sum(1 for span in spans if span[0] == "Bash" and TESTS.search(span[1]))
    waits = [span for span in spans if span[0] == "Bash" and "until " in span[1] and "sleep" in span[1]]
    wait_s = sum(span[2] for span in waits)
    read_n = sum(1 for span in spans if span[0] == "Bash" and READS.search(span[1]))
    repeats = collections.Counter(span[1] for span in spans if span[0] == "Bash")
    print(f"### {args.stream}\n")
    print(f"- Всего {wall / 60:.1f} мин; ходов модели {turns}; вызовов инструментов {sum(names.values())}: "
          + ", ".join(f"{k} {v}" for k, v in names.most_common()))
    print(f"- Время модели (ожидание ответа) ≈ {model_s / 60:.1f} мин ({100 * model_s / wall:.0f}%), время команд ≈ "
          f"{tool_s / 60:.1f} мин ({100 * tool_s / wall:.0f}%)" if wall else "- нет меток времени")
    print(f"- Прогоны тестов/проверок: {test_n} шт., {test_s / 60:.1f} мин ({100 * test_s / wall:.0f}% шага)" if wall else "")
    print(f"- Ожидание фоновых запусков (`until … sleep`): {len(waits)} шт., {wait_s / 60:.1f} мин ({100 * wait_s / wall:.0f}% шага)" if wall else "")
    print(f"- Команды чтения/поиска через Bash (cat/sed/grep/…): {read_n} из {names.get('Bash', 0)}")
    dup = [(c, n) for c, n in repeats.items() if n > 1 and len(c) > 20]
    print(f"- Повторяющиеся одинаковые команды: {len(dup)} видов, лишних запусков {sum(n - 1 for _, n in dup)}")
    print("\n| # | Время | Команда |\n| --- | --- | --- |")
    for index, (name, command, seconds) in enumerate(sorted(spans, key=lambda s: -s[2])[: args.top], 1):
        print(f"| {index} | {seconds:.0f} с | {name}: {command.replace('|', '/')[:120]} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
