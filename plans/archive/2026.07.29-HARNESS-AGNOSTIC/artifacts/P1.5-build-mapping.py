#!/usr/bin/env python3
"""P1.5 — построение `source-to-semantic mapping` для `harness instructions adopt`.

Контракт (`provider-instruction-contract.md` §«Drift and repair») требует у принятия
`source-to-semantic mapping`; конкретную форму он не специфицирует — форма
`{"<target>": {"covered_spans": [[start,end], ...]}}` спроектирована P1.4
(`instructions._adoption_spans`). `covered_spans` — байты pre-image, чей смысл переезжает
в управляемые блоки; непокрытые байты механизм сохраняет дословно ПОСЛЕ блоков.

Матрица `research/05-instruction-canon-routing.md` §2 разбирает семь живых руководств
ПОСЕКЦИОННО (единица разбора — заголовок уровня `##`/`###`) и каждой секции назначает дом:
`ID`/`NEW`/`EXT` (в канон), `скилл` (тело в скилле) или `снимается` (§5). Непокрытых секций
матрица не оставляет — поэтому spans строятся по фактическим границам секций живого файла
и в объединении дают весь файл: байтов «вне маркеров, которые назвала матрица», нет.

Запуск (из корня репо):
    python3 plans/archive/2026.07.29-HARNESS-AGNOSTIC/artifacts/P1.5-build-mapping.py
"""
import json
import pathlib
import re

TARGETS = (
    ("CLAUDE.md", "research/05 §2.1"),
    ("AGENTS.md", "research/05 §2.2"),
    ("packages/skiller/CLAUDE.md", "research/05 §2.3"),
    ("packages/harness/CLAUDE.md", "research/05 §2.4"),
    ("packages/maind/CLAUDE.md", "research/05 §2.5"),
    ("packages/analyst/CLAUDE.md", "research/05 §2.6"),
    ("packages/task/CLAUDE.md", "research/05 §2.7"),
)
HEADING = re.compile(rb"(?m)^##[^#\n].*$")
OUT = pathlib.Path("plans/archive/2026.07.29-HARNESS-AGNOSTIC/artifacts/P1.5-mapping.json")


def sections(raw: bytes) -> list[tuple[int, int, str]]:
    """Границы секций живого файла: преамбула + каждый заголовок `## …` до следующего."""
    starts = [0] + [m.start() for m in HEADING.finditer(raw)]
    bounds = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(raw)
        title = raw[start:end].split(b"\n", 1)[0].decode("utf-8").strip()
        bounds.append((start, end, title if title.startswith("##") else "(преамбула)"))
    return bounds


def main() -> int:
    mapping = {}
    for target, matrix in TARGETS:
        raw = pathlib.Path(target).read_bytes()
        bounds = sections(raw)
        mapping[target] = {
            "covered_spans": [[start, end] for start, end, _title in bounds],
            "matrix": matrix,
            "sections": [{"span": [start, end], "heading": title} for start, end, title in bounds],
        }
        assert bounds[0][0] == 0 and bounds[-1][1] == len(raw), target
    OUT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for target, entry in mapping.items():
        print(f"{target}: {len(entry['covered_spans'])} секций, "
              f"{entry['covered_spans'][-1][1]} байт покрыто")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
