---
id: D89
date: 2026-08-07
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**`Files` item'а P6.5 пополняется провайдерской проекцией переписываемого скилла и её локами:** `packages/skiller/adapters/codex/core/skills/general/plan-protocol/{SKILL.md,snippets/}`, `packages/skiller/adapters/codex/core/publication-lock.json`, `packages/skiller/adapters/codex/skm/publication-lock.json`, `.agents/plugins/marketplace.json`. Регенерация обязательна и объявлена, а не вынужденна.

## Почему

Проекцию производит `skiller/lib/skiller/publication.py:render_codex_publication` (через `registry.py`), а `.agents/plugins/marketplace.json` — тот же путь публикации (`publication.py:675`, `doctor.py:610`, покрыт `tests/test_provider_distribution.py:147–166`); сегодня проекция канона байт-в-байт равна источнику (91 329 = 91 329, проверено 2026-08-07). P6.5 переписывает источник, правит семь snippets, добавляет два и удаляет 230 RU — регенерация неизбежна по построению. Без объявления дифф выходит за `Files` и за carve-out `plans/<PLAN-ID>/**`, что по §6/§8 обязывает статус `🟠`: вынужденное отклонение, заложенное дизайном. Fail-open здесь нет — `skiller registry --check` дрейф поймает, — но поймает как красное вместо запланированной работы. Асимметрия видна и внутри фазы: P6.1/P6.2/P6.3 свои codex-проекции и оба лока перечисляют явно. Канон `root.provider-parity` требует того же: провайдерская проекция — аддитивный адаптер над общим контрактом, а не отдельная жизнь. RAG:— (repo-grounded: `publication.py:675`; `doctor.py:610`; побайтовое сравнение источника и проекции; `findings/13-…` F5)
