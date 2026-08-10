---
id: D41
date: 2026-08-07
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Закрытая таксономия отказов bundle — ПЯТЬ кодов с назначенной severity:** `missing_entry` · `stale_vs_spec` · `hash_mismatch` · `unresolvable_entry` (все четыре — ERROR) · `extraneous_entry` (WARNING). `unresolvable_entry` печатается ОТДЕЛЬНО от `hash_mismatch` и объявляется исполнением отложенного правила D16. «Прочее» не заводится.

## Почему

Рекомендованная источником классификация переносится с двумя его же оговорками. Первая дословно: «This is not proof of tampering; emit it separately from a digest mismatch» — у нас тем более, нерезолвленная позиция есть унаследованная проза, а не порча. Вторая дословно: «Treat "extraneous" as a regeneration diff, not automatically as an install-time error» — лишняя запись не делает чтение неверным, она делает его избыточным, а избыточность уже наказана гейтом веса; ERROR давал бы красное после любой правки ТЗ до пересборки. D16 прямо отложил fail-closed на нерезолвленных позициях до гейта — здесь он и вводится. RAG:✅ 2026-08-07 (`findings/08-…` R8.4) + RAG:— (repo-grounded: `phases/P0.md` P0.3, таксономия пробелов)
