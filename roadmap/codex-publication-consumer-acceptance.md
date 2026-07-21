# Codex publication → consumer acceptance

**Статус:** ⬜ к внедрению  
**Измеренная проблема:** Azguard, 2026-07-21. Внутренние generator/unit проверки были GREEN,
но свежая Codex-сессия не видела `task-plan-run`/`task-plan-exec`: sibling `task` отсутствовал в
native marketplace, marketplace `source` не принимался Codex, а версия `0.2.0` удерживала
Claude-only cache. Локальные `.agents/skills` маскировали отказ реального consumer path.

## Цель

Сделать внешне наблюдаемый consumer результат обязательным гейтом любой Codex publication:

`semantic source → generated plugin → marketplace discovery → install/cache → clean project → fresh session`

Package-level GREEN без прохождения всей цепочки не является release/plan GREEN.

## Минимальный объём

1. Независимый expected inventory package-owned Codex plugins; renderer не строит собственное
   ожидание.
2. Conformance реальной native marketplace schema и contained plugin paths.
3. Изолированный temp `CODEX_HOME`: marketplace add, plugin add/update, проверка версии и полного
   cache inventory без зависимости от уже установленного пользовательского cache.
4. Clean temp consumer: fresh Codex process подтверждает startup discovery экспортируемых skills;
   для `task` — минимум `task-plan-run` и `task-plan-exec`.
5. Версия publication входит в provenance; изменение export surface без version bump — RED.
6. Claude compatibility остаётся отдельным consumer check; repo-local adapters не могут служить
   доказательством marketplace/install результата.

## Execution circuit breaker

- Один micro-slice → один implementation pass → один focused consumer acceptance.
- Первый RED → один bounded owning-seam repair.
- Повторный RED той же причины → supervisor фиксирует точный missing assertion/line и разрешает
  ровно один минимальный patch; новые абстракции и worker-loop запрещены.
- Bookkeeping начинается только после consumer GREEN.

## Не входит

- переработка `.agents/skills` или канонических skill bodies;
- новый provider framework;
- fleet rollout и push;
- замена provider-neutral semantic contract consumer-specific fixtures.

## Критерий внедрения

Уже сработал: Azguard cold-start обнаружил publication failure после формально GREEN P4/P5.
Внедрять отдельным bounded item до следующего добавления/изменения Codex plugin export surface.

## Текущее частичное исправление

`04be7d9` (`0694379` в P6 chain) исправляет `task` 0.3.0, sibling marketplace publication,
Codex-compatible source shape и version provenance. Системный изолированный acceptance для всех
плагинов остаётся задачей этого roadmap.
