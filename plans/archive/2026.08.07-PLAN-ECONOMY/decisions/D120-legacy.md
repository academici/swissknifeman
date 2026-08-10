---
id: D120
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Time-to-field важнее исчерпывающих предварительных прогонов, пока shared boundary не меняется.** P0.1 ограничивает active Codex calibration восемью принятыми реальными файлами (≥3 dense) и bracket-controls после не более трёх payload probes: при зелёном пути ≤12 provider calls вместо `3 × N`; строгие bound/tightness остаются на измеренном corpus. P2.8 self-hosts реальный план, P3.7 добавляет read-only canary текущего layout-v2 плана и временной dry-run проекции одного fleet-плана; найденные adapter/fixture defects чинятся вперёд в owning item. **Consequences:** `supersedes D92` в части per-file A/B/A′ schedule и D117 в части подразумеваемого полного повторения прежнего 14-файлового corpus; сохранность v1, ≥3 dense, violations=0 и p95≤1.6 сохраняются. Расширение corpus того же qualified target — обычная регенерация, redesign нужен только при смене shared schema/classifier/public contract.

## Почему

Владелец потребовал перестать тормозить старт прогонами и раньше тестировать реальные проекты при надёжной основе. Восемь точек покрывают шесть параметров fitter (пять ставок + overhead) с двумя дополнительными наблюдениями; это bounded engineering pilot, не заявление статистической полноты флота. RAG:— (stable math + owner decision + repo-grounded corpus; `research/16-…` §3–§4).
