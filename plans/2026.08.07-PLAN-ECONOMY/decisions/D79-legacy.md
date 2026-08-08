---
id: D79
date: 2026-08-07
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Авторинг скиллов переводится в EN-only: все 230 `SKILL.ru.md` удаляются, канон v2 авторится прямо в `SKILL.md`, а три гейта, анкерящихся на RU-источник, ПЕРЕПРИВЯЗЫВАЮТСЯ на `SKILL.md` с ОТКАЗОМ вместо молчаливой деградации; русские КАНОНИЧЕСКИЕ ЛИТЕРАЛЫ не переводятся, механизм `i18n-keep` сохраняется со сменой носителя объявления.** **Consequences:** отменяется двуязычная модель канона этого плана (`SKILL.ru.md` → `SKILL.md` + маркер `ru-source-sha256`) — вместе с ней выводятся из обращения гейт `check-translations.sh` и промпт `prompts/generate/claude-canon-from-ru.md`, а ссылки на RU-носитель в `validate.sh`, `update-upstreams.sh` и `lib/skiller/{vendor,common,publication}.py` снимаются; платой становится потеря проверки «литерал объявлен, но не употреблён в теле», которая переносится на EN в том же item'е, иначе класс дефекта исчезает вместе с гейтом. Компактификация EN-канонов остальных 229 скиллов и контракт локали НЕ выполняются — они принадлежат плану `2026.08.02-PROVIDER-CONTRACT-LOCALE` (P2.1–P2.3, на паузе).

## Почему

Распоряжение владельца в живой сессии: «в другом плане был отказ от ru-скиллов, поэтому делай только англ., а `.ru` все физически удали, чтобы не отвлекали» — RAG:— (owner-grounded: `brief/01-refinements.md`, блок 2026-08-07); английский как язык-источник уже зафиксирован планом-донором дословно («English is source language; localized text is a rendered overlay, never a second implementation»). Удаление не является housekeeping'ом: `--conflicts` при отсутствии SSOT печатает предупреждение и возвращает 0, литеральные тесты уходят в `skipTest`, а гейт переводов перебирает только скиллы, у которых RU есть, — то есть голое удаление оставило бы репозиторий с тремя зелёными-на-пустом гейтами, ровно тем классом дефекта, который чинит этот план. Литералы не переводятся, потому что они контракт 24 планов флота, читаемый байт-в-байт. RAG:— (repo-grounded: `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/plan.md` `## 2. Execution Rules`; `packages/task/lib/task/plan_lint.py:2581–2588`; `packages/task/tests/test_canon_literals.py` skipTest'ы; `packages/skiller/scripts/check-translations.sh`)
