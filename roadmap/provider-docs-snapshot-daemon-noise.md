# `test-provider-docs.py` снимок всего дерева ловит чужой daemon-шум

**Класс:** `deferred-with-criterion` (P6.3, D70 — измерено, воспроизводится).

## Что

`scripts/test-provider-docs.py::test_committed_outputs_are_exact_and_check_is_no_write`
снимает хеши ВСЕГО дерева репозитория (`snapshot(ROOT)` → `root.rglob("*")`) до и после
прогона `provider_docs.run("check", ROOT)`, чтобы доказать «check — no-write». Снимок не
ограничен поверхностью генератора (`README.md`, `docs/provider-support.md`,
`configs/provider-capabilities.json`) — он ловит ЛЮБОЙ файл, изменённый посторонним
процессом за окно прогона (~20–25 с).

## Как измерено (P6.3, 2026-08-02, `ebd42655`+)

Изолированный прогон `provider_docs.run("check", ROOT)` с адресной диагностикой diff
before/after дал ровно один изменившийся путь:

```
packages/maind/data/state_store.db/mem%3Ahealth.bin
```

— бинарник живого демона mAInd (`:4111`), пишущего health-состояние В РЕПОЗИТОРИЙ во время
теста. Воспроизведено трижды подряд (три прогона теста в изоляции — все `FAILED`). Класс —
средо-зависимая хрупкость снимка, не дрейф манифеста и не баг генератора; second провал
`scripts/test-provider-docs.py`, названный `findings/P6-manifest-drift-2026-07-31.md` §4 как
непроверенный на чистом дереве, — этим измерением проверен и подтверждён.

## Критерий внедрения

Сузить `snapshot()` в `scripts/test-provider-docs.py` до путей, которые `expected_outputs()`
реально производит (`README.md`, `docs/provider-support.md`) плюс вход-манифест, вместо
`root.rglob("*")` по всему дереву — ИЛИ исключить `packages/*/data/**` (даемон-состояние вне
владения генератора) из обхода. Любой из двух убирает ложный провал без ослабления
утверждения «check — no-write» на реальной поверхности генератора.

**Владелец адреса:** следующая содержательная правка `scripts/test-provider-docs.py` (P5.2 —
единственный владелец файла по коллизии D62/D63) ИЛИ отдельный item, если владелец решит не
ждать. Не входит в `P6.3` (Scope Excluded: этот провал измеряется, не чинится).
